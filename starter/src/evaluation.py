"""Evaluate retrieved evidence (Hit@1, Evidence Hit@3, filter compliance) and verify the benchmark.

Verify benchmark evidence against the OCR pages before any retrieval run:
    python -m src.evaluation --verify ../benchmark/questions.jsonl results/pages_TT-91-2026.jsonl
"""
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .ingestion import load_pages, read_jsonl


def squash(s: str) -> str:
    """Collapse all whitespace runs to one space (OCR line breaks fall mid-sentence)."""
    return " ".join(s.split())


def contains_evidence(text: str, quote: str) -> bool:
    """Exact match after collapsing whitespace."""
    return squash(quote) in squash(text)


def verify_benchmark(questions_path: str, pages_path: str) -> list[str]:
    """Check counts, split, filters, and that each evidence quote is on its gold page."""
    qs = read_jsonl(Path(questions_path))
    pages = {(p.document_id, p.page): p.text for p in load_pages(Path(pages_path))}
    errors = []
    for q in qs:
        found = [pg for pg in q["gold_page"] if contains_evidence(pages.get((q["gold_source_id"], pg), ""), q["evidence_quote"])]
        if not found:
            errors.append(f"{q['id']}: evidence not found on {q['gold_source_id']} p{q['gold_page']}")
    split = Counter(q["split"] for q in qs)
    filt = Counter(q["split"] for q in qs if q.get("filter"))
    if len(qs) < 20: errors.append(f"only {len(qs)} questions (<20)")
    if split["dev"] < 15 or split["test"] < 5: errors.append(f"split {dict(split)} (need >=15 dev, >=5 test)")
    if sum(filt.values()) < 3 or filt["test"] < 1: errors.append(f"filter questions {dict(filt)} (need >=3, >=1 test)")
    if len({q["id"] for q in qs}) != len(qs): errors.append("duplicate ids")
    print(f"{len(qs)} questions | split {dict(split)} | filter {dict(filt)} | errors {len(errors)}")
    return errors


def is_evidence_hit(question: dict[str, Any], hit: dict[str, Any]) -> bool:
    """Gold source + a gold page among the chunk's pages + the whole evidence quote in the chunk text.

    Alternative evidence: `question["alt_evidence"]` may list extra {"page": [...], "quote": "..."} entries.
    """
    options = [{"page": question["gold_page"], "quote": question["evidence_quote"]}]
    options += question.get("alt_evidence", [])
    pages = set(hit.get("pages") or [hit["page"]])
    return hit["document_id"] == question["gold_source_id"] and any(
        pages & set(o["page"]) and contains_evidence(hit["text"], o["quote"]) for o in options)


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Automatic labels only (Hit@1, Evidence Hit@3, filter compliance).

    Grounding and chunk coherence are manual labels; they are not inferred from string match.
    """
    flags = [is_evidence_hit(question, h) for h in hits[:3]]
    flt = question.get("filter") or {}
    return {
        "hit_at_1": bool(flags) and flags[0],
        "hit_at_3": any(flags),
        "first_hit_rank": flags.index(True) + 1 if any(flags) else None,
        "hit_flags": flags,
        # Only meaningful for questions that carry a filter; None otherwise (not counted as 100%).
        "filter_compliant": all(flt.items() <= h.items() for h in hits[:3]) if flt else None,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Hit@1 / Evidence Hit@3 / filter compliance as n/N per strategy and split."""
    out: dict[str, Any] = {}
    for t in traces:
        s = out.setdefault(t["strategy"], {}).setdefault(t["split"], {"N": 0, "hit_at_1": 0, "hit_at_3": 0,
                                                                     "filter_N": 0, "filter_ok": 0})
        s["N"] += 1
        s["hit_at_1"] += t["eval"]["hit_at_1"]
        s["hit_at_3"] += t["eval"]["hit_at_3"]
        if t["eval"]["filter_compliant"] is not None:
            s["filter_N"] += 1
            s["filter_ok"] += t["eval"]["filter_compliant"]
    for per_split in out.values():
        for s in per_split.values():
            s["hit_at_1_str"] = f"{s['hit_at_1']}/{s['N']}"
            s["hit_at_3_str"] = f"{s['hit_at_3']}/{s['N']}"
            s["filter_str"] = f"{s['filter_ok']}/{s['filter_N']}" if s["filter_N"] else "N/A"
    return out


def _selftest() -> None:
    q = {"id": "x", "gold_source_id": "D", "gold_page": [5], "evidence_quote": "hai thành phần",
         "filter": {"chapter": "III"}}
    good = {"document_id": "D", "page": 4, "pages": [4, 5], "chapter": "III", "text": "gồm hai\nthành phần"}
    wrong_page = {**good, "pages": [6], "page": 6}
    wrong_ch = {**good, "chapter": "II", "text": "khác"}
    assert is_evidence_hit(q, good) and not is_evidence_hit(q, wrong_page)
    e = evaluate_query(q, [wrong_ch, good, wrong_page])
    assert (e["hit_at_1"], e["hit_at_3"], e["first_hit_rank"], e["filter_compliant"]) == (False, True, 2, False)
    assert evaluate_query({**q, "filter": None}, [good])["filter_compliant"] is None
    s = summarize([{"strategy": "C", "split": "dev", "eval": e}])["C"]["dev"]
    assert (s["hit_at_1_str"], s["hit_at_3_str"], s["filter_str"]) == ("0/1", "1/1", "0/1")
    print("selftest OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest(); sys.exit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "--verify":
        errs = verify_benchmark(sys.argv[2], sys.argv[3])
        print("\n".join(errs) if errs else "benchmark OK")
        sys.exit(1 if errs else 0)
    sys.exit("usage: python -m src.evaluation --verify <questions.jsonl> <pages.jsonl>")
