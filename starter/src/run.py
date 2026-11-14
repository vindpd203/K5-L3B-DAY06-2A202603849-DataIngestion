"""Day 06 pipeline entry point.

    python -m src.run ingest      # chunk A/B, embed, upsert into pgvector; appends results/ingest_log.jsonl
    python -m src.run benchmark dev    # top-3 for A, B, C; results/traces_dev.jsonl + metrics_dev.json
    python -m src.run benchmark test   # run ONCE, after choosing the strategy on dev

Strategy C = strategy-B chunks + `chapter` filter, applied only to questions that carry a filter.
"""
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .chunking import annotate, by_paragraph, fixed_size, stats
from .embeddings import SentenceTransformerEmbedder
from .evaluation import contains_evidence, evaluate_query, squash, summarize
from .ingestion import load_pages, read_jsonl, write_jsonl
from .store import PgVectorStore

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
# Content pages per data/manifest.yaml (counted_pages); appendix pages 34-97 are excluded.
CORPUS = [("TT-91-2026", RESULTS / "pages_TT-91-2026.jsonl", range(1, 33))]
# 360 chars = largest size where no chunk exceeds the model's 128-token limit (checked on dev run, before any test).
# First version used A 500/50 and B 1000: 98/173 and 85/98 chunks were truncated by the embedder.
CHUNK_SIZE, OVERLAP = 360, 36
CHUNKERS = {
    "A": lambda pages: fixed_size(pages, size=CHUNK_SIZE, overlap=OVERLAP),
    "B": lambda pages: by_paragraph(pages, max_size=CHUNK_SIZE),
}


def load_corpus():
    pages = []
    for doc_id, path, keep in CORPUS:
        got = [p for p in load_pages(path) if p.document_id == doc_id and p.page in keep]
        if len(got) != len(keep):
            raise RuntimeError(f"{doc_id}: expected {len(keep)} content pages, found {len(got)}")
        pages += got
    if len(pages) < 30:
        raise RuntimeError(f"only {len(pages)} content pages (<30)")
    return pages


def get_store(dimensions: int) -> PgVectorStore:
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL missing in starter/.env")
    return PgVectorStore(url, dimensions)


def ingest() -> None:
    pages = load_corpus()
    t0 = time.perf_counter()
    embedder = SentenceTransformerEmbedder()
    model_load_s = time.perf_counter() - t0
    store = get_store(embedder.dimensions)
    store.create_schema()
    for name, chunker in CHUNKERS.items():
        t = time.perf_counter()
        chunks = chunker(pages)
        t_chunk = time.perf_counter() - t
        tokens = embedder.token_counts([c.text for c in chunks])
        t = time.perf_counter()
        vectors = embedder.embed_documents([c.text for c in chunks])
        t_embed = time.perf_counter() - t
        t = time.perf_counter()
        result = store.upsert(name, chunks, vectors)
        t_store = time.perf_counter() - t
        record = {
            "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "strategy": name,
            "pages": len(pages), **stats(chunks),
            "tokens_total": sum(tokens), "tokens_max": max(tokens),
            "chunks_over_max_seq_len": sum(n > embedder.max_seq_length for n in tokens),
            "model": embedder.model_name, "dimensions": embedder.dimensions,
            "max_seq_length": embedder.max_seq_length, "sentence_transformers": embedder.library_version,
            "model_load_s": round(model_load_s, 2), "chunk_s": round(t_chunk, 3),
            "embed_s": round(t_embed, 2), "store_s": round(t_store, 2), **result,
            "rows_in_db": store.count(name), "cost_usd": 0,
        }
        RESULTS.mkdir(exist_ok=True)
        write_jsonl(RESULTS / "ingest_log.jsonl", [record], mode="a")
        print(json.dumps(record, ensure_ascii=False))
        if record["rows_in_db"] != len(chunks):
            raise RuntimeError(f"{name}: {record['rows_in_db']} rows in DB but {len(chunks)} chunks")


# strategy -> (stored rows to search, apply question filter?)
STRATEGIES = {"A": ("A", False), "B": ("B", False), "C": ("B", True)}
QUESTIONS = ROOT.parent / "benchmark" / "questions.jsonl"


def benchmark(split: str) -> None:
    """Top-3 for every question of one split with A, B, C. Writes traces + metrics for that split only."""
    if split not in ("dev", "test"):
        sys.exit("split must be dev or test")
    qs = [q for q in read_jsonl(QUESTIONS) if q["split"] == split]
    embedder = SentenceTransformerEmbedder()
    store = get_store(embedder.dimensions)
    for rows in {r for r, _ in STRATEGIES.values()}:
        if store.count(rows) == 0:
            sys.exit(f"no rows for strategy {rows}; run `python -m src.run ingest` first")
    traces = []
    qvecs = embedder.embed_documents([q["question"] for q in qs])  # one batch; same model/normalization as embed_query
    for q, qvec in zip(qs, qvecs):
        for name, (rows, use_filter) in STRATEGIES.items():
            flt = q.get("filter") if use_filter else None
            t = time.perf_counter()
            hits = store.search(rows, qvec, top_k=3, filters=flt)
            ms = (time.perf_counter() - t) * 1000
            ev = evaluate_query(q, hits)  # filter compliance measured for A/B too (shows drift without a filter)
            traces.append({
                "strategy": name, "split": split, "id": q["id"], "type": q["type"], "question": q["question"],
                "filter_applied": flt, "gold_page": q["gold_page"], "evidence_quote": q["evidence_quote"],
                "search_ms": round(ms, 1), "eval": ev,
                "top3": [{"rank": i + 1, "chunk_id": h["chunk_id"], "page": h["page"], "pages": h["pages"],
                          "chapter": h["chapter"], "article": h["article"], "score": round(h["score"], 4),
                          "evidence_hit": ev["hit_flags"][i], "text": h["text"]} for i, h in enumerate(hits)],
            })
    metrics = {"split": split, "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "model": embedder.model_name, "chunkers": {"A": f"fixed {CHUNK_SIZE}/{OVERLAP}", "B": f"paragraph max {CHUNK_SIZE}",
                                                          "C": "B + chapter filter when the question has one"},
               "summary": summarize(traces)}
    write_jsonl(RESULTS / f"traces_{split}.jsonl", traces)
    (RESULTS / f"metrics_{split}.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"split={split}  (n/N)")
    for name, per in metrics["summary"].items():
        s = per[split]
        print(f"  {name}: Hit@1 {s['hit_at_1_str']}  Evidence Hit@3 {s['hit_at_3_str']}  filter {s['filter_str']}")
    for t in traces:
        print(f"  {t['strategy']} {t['id']}: hit@3={t['eval']['hit_at_3']} rank={t['eval']['first_hit_rank']} "
              f"top3={[h['chunk_id'].split(':', 1)[1] for h in t['top3']]}")


AUDIT = RESULTS / "audit"


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel shows Vietnamese correctly
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _suffix_overlap(text: str, anchor: str) -> int:
    """Length of the longest anchor prefix (>= 3 chars) that the chunk text ends with; 0 if none."""
    t = squash(text)
    return max((n for n in range(3, len(anchor)) if t.endswith(squash(anchor[:n]))), default=0)


def audit() -> None:
    """Sheets for manual labels (GUIDE §4). Labels stay blank: they are filled by a human, not inferred.

    Coherence positions are fixed by rule before looking at scores: pages 1-10, anchor = the 60 characters
    starting at the middle of each page body (snapped to the next line start).
    """
    AUDIT.mkdir(parents=True, exist_ok=True)
    labelled = [p.name for p in AUDIT.glob("*.csv") if "annotator" in p.read_text(encoding="utf-8-sig").split("\n")[0]]
    if labelled and "--force" not in sys.argv:
        sys.exit(f"{labelled} already contain labels; back them up and rerun with --force to overwrite")
    pages = load_corpus()
    chunks = {name: chunker(pages) for name, chunker in CHUNKERS.items()}

    # 1. chunk coherence: 10 source positions x A, B (C uses B's chunks -> same label, listed for completeness)
    rows = []
    for page, body, _, _ in annotate([p for p in pages if p.page <= 10]):
        mid = body.find("\n", len(body) // 2) + 1 or len(body) // 2
        anchor = body[mid:mid + 60]
        for name, (stored_as, _) in STRATEGIES.items():
            src = chunks[stored_as]
            # chunk containing the whole 60-char anchor (unique on the page); if a chunk boundary falls inside
            # the anchor, take the chunk whose END matches the longest anchor prefix (the start of the position)
            on_page = [c for c in src if page.page in c.metadata["pages"]]
            hit = next((c for c in on_page if contains_evidence(c.text, anchor)), None)
            boundary = hit is None
            if boundary:
                hit = max(on_page, key=lambda c: _suffix_overlap(c.text, anchor))
            rows.append([f"pos{page.page:02d}", page.page, anchor.replace("\n", " "), name, hit.chunk_id,
                         hit.metadata["article"], boundary, hit.text,
                         "" if name != "C" else "= nhãn B (cùng chunk)", ""])
    _write_csv(AUDIT / "coherence.csv", ["position", "page", "anchor_60_chars", "strategy", "chunk_id", "article",
                                         "boundary_inside_anchor", "chunk_text", "score_0_1_2", "reason"], rows)

    # 2-3. metadata (5 test x top-3 x A/B/C) and grounding (5 test x A/B/C) from the saved test traces
    traces = read_jsonl(RESULTS / "traces_test.jsonl")
    qs = {q["id"]: q for q in read_jsonl(QUESTIONS)}
    by_id = {c.chunk_id: c for cs in chunks.values() for c in cs}
    meta_rows, ground_rows = [], []
    for t in traces:
        for h in t["top3"]:
            stored = by_id[h["chunk_id"]]
            meta_rows.append([t["strategy"], t["id"], h["rank"], h["chunk_id"],
                              f"{stored.document_id} | {stored.source}", h["page"],
                              " ".join(map(str, h["pages"])), h["chapter"], h["article"],
                              json.dumps(t["filter_applied"] or qs[t["id"]].get("filter"), ensure_ascii=False),
                              h["text"][:200], "", "", "", "", ""])
        ground_rows.append([t["strategy"], t["id"], t["question"], qs[t["id"]]["expected_answer"],
                            " ".join(map(str, t["gold_page"])), t["eval"]["hit_at_3"],
                            "\n\n---\n\n".join(f"[{h['rank']}] p{h['pages']} Đ{h['article']}: {h['text']}"
                                               for h in t["top3"]), "", ""])
    _write_csv(AUDIT / "metadata.csv", ["strategy", "id", "rank", "chunk_id", "source", "page", "pages", "chapter",
                                        "article", "question_filter", "text_200", "source_ok", "page_ok",
                                        "chapter_ok", "article_ok", "note"], meta_rows)
    _write_csv(AUDIT / "grounding.csv", ["strategy", "id", "question", "expected_answer", "gold_page",
                                         "auto_evidence_hit_at_3", "top3_text", "score_0_1_2", "reason"], ground_rows)
    print(f"coherence {len(rows)} rows, metadata {len(meta_rows)} rows, grounding {len(ground_rows)} rows -> {AUDIT}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "ingest":
        return ingest()
    if cmd == "audit":
        return audit()
    if cmd == "benchmark" and len(sys.argv) == 3:
        return benchmark(sys.argv[2])
    sys.exit("usage: python -m src.run ingest | python -m src.run benchmark dev|test")


if __name__ == "__main__":
    main()
