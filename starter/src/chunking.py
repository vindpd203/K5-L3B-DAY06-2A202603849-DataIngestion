"""Fixed-size (strategy A) and structure-aware (strategy B/C) chunking.

Both keep document_id, source, page, plus `chapter` / `article` metadata for filtering.
Self-check:  python -m src.chunking --selftest
Stats:       python -m src.chunking results/pages_TT-91-2026.jsonl 1-32
"""
import re
import sys
from bisect import bisect_right
from pathlib import Path
from statistics import mean, median

from .models import Chunk, DocumentPage

# Article -> chapter for TT-91-2026, read from the PDF headings (OCR misreads "Chương II/III" as "H"/"HỊ").
CHAPTER_STARTS = [(1, "I"), (3, "II"), (17, "III"), (21, "IV"), (24, "V")]
# Article heading at line start: "Điều 7. Tiêu chí ..." (OCR sometimes gives "Điều 19, Ký hiệu ...").
ARTICLE_RE = re.compile(r"^Điều (\d+)[.,] +(\w)", re.M)  # group 2 must be uppercase (checked in annotate)


def chapter_of(article: int | None) -> str | None:
    if article is None:
        return None  # preamble before Điều 1 (quốc hiệu, căn cứ)
    return [ch for start, ch in CHAPTER_STARTS if article >= start][-1]


def body_text(page: DocumentPage) -> str:
    """Drop the printed page number line ("12", "I0", "l 4", "-") at the top of a page."""
    first, _, rest = page.text.partition("\n")
    return rest.lstrip("\n") if len(first.strip()) <= 4 else page.text


def annotate(pages: list[DocumentPage]) -> list[tuple[DocumentPage, str, list[int], list[int | None]]]:
    """Per page: body text and the offsets where the current article changes.

    Article numbers must increase by 1-3, so cross-references such as "Điều 8 Thông tư này"
    wrapped to a line start are not mistaken for headings.
    """
    out, current = [], None
    for page in sorted(pages, key=lambda p: p.page):
        body = body_text(page)
        starts, arts = [0], [current]
        for m in ARTICLE_RE.finditer(body):
            n = int(m.group(1))
            if not m.group(2).isupper():
                continue
            if (current is None and n == 1) or (current is not None and current < n <= current + 3):
                current = n
                starts.append(m.start())
                arts.append(n)
        out.append((page, body, starts, arts))
    return out


def _meta(page: DocumentPage, article: int | None, strategy: str, pages: list[int]) -> dict:
    return {**page.metadata, "strategy": strategy, "article": article,
            "chapter": chapter_of(article), "pages": pages}


def fixed_size(pages: list[DocumentPage], size: int = 360, overlap: int = 36) -> list[Chunk]:
    """Strategy A: character windows within each page; article/chapter taken at the window start."""
    assert 0 <= overlap < size
    chunks = []
    for page, body, starts, arts in annotate(pages):
        for i, pos in enumerate(range(0, max(len(body) - overlap, 1), size - overlap)):
            text = body[pos:pos + size].strip()
            if not text:
                continue
            article = arts[bisect_right(starts, pos) - 1]
            chunks.append(Chunk(f"{page.document_id}:A:p{page.page:03d}:{i:02d}", page.document_id,
                                page.source, page.page, text,
                                _meta(page, article, f"fixed{size}o{overlap}", [page.page])))
    return chunks


def by_paragraph(pages: list[DocumentPage], max_size: int = 360) -> list[Chunk]:
    """Strategy B: group paragraphs of the same article up to max_size, never crossing an article.

    A paragraph cut by a page break continues into the next page (metadata["pages"] lists both).
    Paragraphs longer than max_size are split at sentence/clause boundaries.
    """
    # 1. paragraphs with (page, article); a page break inside a paragraph joins the halves
    paras: list[list] = []  # [text, article, pages]
    for page, body, starts, arts in annotate(pages):
        bounds = starts[1:] + [len(body)]
        for k, (s, e) in enumerate(zip(starts, bounds)):
            for j, para in enumerate(p.strip() for p in body[s:e].split("\n\n")):
                if not para:
                    continue
                continues = (j == 0 and k == 0 and paras and paras[-1][1] == arts[k]
                             and not paras[-1][0].rstrip().endswith((".", ":", ";")))
                if continues:
                    paras[-1][0] += "\n" + para
                    paras[-1][2].append(page.page)
                else:
                    paras.append([para, arts[k], [page.page]])

    # 2. pack paragraphs into chunks within one article
    by_page = {p.page: p for p in pages}
    chunks, buf, buf_pages, buf_art = [], [], [], object()

    def flush():
        if buf:
            first = by_page[buf_pages[0]]
            uniq = sorted(set(buf_pages))
            chunks.append(Chunk(f"{first.document_id}:B:p{uniq[0]:03d}:{len(chunks):03d}", first.document_id,
                                first.source, uniq[0], "\n\n".join(buf),
                                _meta(first, buf_art, f"paragraph{max_size}", uniq)))
            buf.clear(); buf_pages.clear()

    for text, article, pgs in paras:
        for piece in _split_long(text, max_size):
            if article != buf_art or len("\n\n".join(buf + [piece])) > max_size:
                flush()
                buf_art = article
            buf.append(piece)
            buf_pages.extend(pgs)
    flush()
    return chunks


def _split_long(text: str, max_size: int) -> list[str]:
    """Split an oversized paragraph at '. ' / '; ' boundaries; hard-cut only if a sentence is too long."""
    if len(text) <= max_size:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.;:])\s+", text):
        if cur and len(cur) + 1 + len(sent) > max_size:
            parts.append(cur)
            cur = ""
        while len(sent) > max_size:  # ponytail: hard cut for run-on sentences, rare in this corpus
            parts.append(sent[:max_size]); sent = sent[max_size:]
        cur = f"{cur} {sent}".strip()
    return parts + ([cur] if cur else [])


def stats(chunks: list[Chunk]) -> dict:
    lens = sorted(len(c.text) for c in chunks)
    return {"chunks": len(chunks), "chars_total": sum(lens), "len_min": lens[0], "len_median": median(lens),
            "len_mean": round(mean(lens)), "len_max": lens[-1],
            "multi_page": sum(len(c.metadata["pages"]) > 1 for c in chunks),
            "no_article": sum(c.metadata["article"] is None for c in chunks)}


def _selftest() -> None:
    p1 = DocumentPage("D", "d.pdf", 1, "1\nMở đầu.\n\nChương I\n\nĐiều 1. Phạm vi\n\nNội dung một, xem Điều 3\nThông tư này.\n\nĐiều 2. Đối tượng\n\nNội dung hai", {})
    p2 = DocumentPage("D", "d.pdf", 2, "2\ntiếp tục câu.\n\nĐiều 3. Ủy nhiệm\n\n" + "Câu dài. " * 40 + "\n\nĐiều 8 Thông tư này không phải heading.", {})
    a = annotate([p1, p2])
    assert a[0][1].startswith("Mở đầu") and a[0][3] == [None, 1, 2], a[0][3]   # page number dropped
    assert a[1][3] == [2, 3], a[1][3]                                          # "Điều 8 Thông tư" rejected
    assert chapter_of(2) == "I" and chapter_of(3) == "II" and chapter_of(20) == "III" and chapter_of(None) is None
    A = fixed_size([p1, p2], size=60, overlap=10)
    assert all(len(c.text) <= 60 for c in A) and A[0].metadata["pages"] == [1]
    B = by_paragraph([p1, p2], max_size=120)
    assert all(len(c.text) <= 120 for c in B), [len(c.text) for c in B]
    assert len({c.metadata["article"] for c in B if "Nội dung hai" in c.text}) == 1
    joined = [c for c in B if "Nội dung hai" in c.text][0]
    assert "tiếp tục câu." in joined.text and joined.metadata["pages"] == [1, 2]  # page-break paragraph joined
    assert not any("Nội dung hai" in c.text and "Ủy nhiệm" in c.text for c in B)  # never crosses articles
    print("selftest OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        from .ingestion import load_pages
        lo, hi = map(int, sys.argv[2].split("-"))
        pages = [p for p in load_pages(Path(sys.argv[1])) if lo <= p.page <= hi]
        for name, chunks in [("A fixed 360/36", fixed_size(pages)), ("B paragraph 360", by_paragraph(pages))]:
            print(name, stats(chunks))
