"""Read and normalize source data, with OCR for scanned pages.

Run OCR once and cache it as JSONL (one page per line):
    python -m src.ingestion ../data/raw/Thông-tư-91-2026-TT-BTC.pdf TT-91-2026 results/pages_TT-91-2026.jsonl
Self-check:
    python -m src.ingestion --selftest
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from dataclasses import asdict
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

DEFAULT_TESSDATA = Path(__file__).resolve().parents[1] / "tessdata"
DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
MIN_CHARS = 200  # a page under this after OCR is logged as low-text (cover, signature, blank)


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract the text layer of each physical page (1-based page numbers).

    Pages without a text layer keep text="" and metadata["empty"]=True; ocr_pages() fills them.
    """
    reader = PdfReader(str(path))
    pages = []
    for i, p in enumerate(reader.pages, start=1):
        text = normalize_text(p.extract_text() or "")
        pages.append(DocumentPage(document_id, source, i, text,
                                  {"extraction": "text_layer", "empty": not text}))
    return pages


def find_tesseract() -> str:
    """TESSERACT_CMD env, then PATH, then the default Windows install folder."""
    cmd = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract") or DEFAULT_TESSERACT
    if not Path(cmd).exists() and not shutil.which(cmd):
        raise FileNotFoundError(f"Tesseract not found ({cmd}); set TESSERACT_CMD")
    return cmd


def ocr_pages(path: Path, pages: list[DocumentPage], lang: str = "vie", dpi: int = 300,
              psm: int = 6, tessdata: Path | None = None) -> list[DocumentPage]:
    """OCR every page whose text layer is empty. Fails loudly if OCR is unavailable.

    PyMuPDF only renders the page to PNG; the installed Tesseract CLI does the OCR.
    (PyMuPDF's bundled Tesseract dropped spaces after accented Vietnamese words.)
    """
    import pymupdf  # imported here so text-only PDFs do not need it

    tessdata = Path(tessdata or os.environ.get("TESSDATA_PREFIX") or DEFAULT_TESSDATA)
    if not (tessdata / f"{lang}.traineddata").exists():
        raise FileNotFoundError(f"Missing {lang}.traineddata in {tessdata}")
    cmd = find_tesseract()
    version = subprocess.run([cmd, "--version"], capture_output=True, text=True).stdout.split("\n")[0]

    doc = pymupdf.open(str(path))
    for page in pages:
        if not page.metadata.get("empty"):
            continue
        t0 = time.perf_counter()
        png = doc[page.page - 1].get_pixmap(dpi=dpi).tobytes("png")
        run = subprocess.run([cmd, "stdin", "stdout", "--tessdata-dir", str(tessdata),
                              "-l", lang, "--psm", str(psm)], input=png, capture_output=True)
        if run.returncode != 0:
            raise RuntimeError(f"Tesseract failed on page {page.page}: {run.stderr.decode(errors='replace')}")
        page.text = normalize_text(run.stdout.decode("utf-8"))
        page.metadata.update({
            "extraction": "ocr", "ocr_engine": version, "ocr_lang": lang, "ocr_dpi": dpi,
            "ocr_psm": psm, "ocr_seconds": round(time.perf_counter() - t0, 2),
            "empty": not page.text, "low_text": len(page.text) < MIN_CHARS,
        })
        print(f"  page {page.page}: {len(page.text)} chars, {page.metadata['ocr_seconds']}s", flush=True)
    return pages


def normalize_text(text: str) -> str:
    """NFC Unicode, unify line endings, collapse spaces; keep line breaks (Chuong/Dieu/Khoan)."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")  # non-breaking space, zero-width space
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows, mode: str = "w") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def save_pages(pages: list[DocumentPage], out: Path) -> None:
    write_jsonl(out, map(asdict, pages))


def load_pages(path: Path) -> list[DocumentPage]:
    return [DocumentPage(**r) for r in read_jsonl(path)]


def _selftest() -> None:
    nfc = "\u0110i\u1ec1u 1."  # "Dieu 1." with Vietnamese accents
    nfd = unicodedata.normalize("NFD", nfc)  # decomposed accents, as some PDFs emit
    assert nfd != nfc
    assert normalize_text(nfd + "\r\n\r\n\r\n  Kho\u1ea3n  1 ") == nfc + "\n\nKho\u1ea3n 1"
    assert normalize_text("a\u00a0 \u00a0 b\n \n \n \nc") == "a b\n\nc"
    assert normalize_text("") == ""
    print("selftest OK")


def main(argv: list[str]) -> None:
    if argv == ["--selftest"]:
        return _selftest()
    if len(argv) != 3:
        sys.exit("usage: python -m src.ingestion <pdf> <document_id> <out.jsonl>")
    pdf, doc_id, out = Path(argv[0]), argv[1], Path(argv[2])
    t0 = time.perf_counter()
    pages = load_pdf(pdf, doc_id, pdf.name)
    empty = sum(p.metadata["empty"] for p in pages)
    print(f"{pdf.name}: {len(pages)} pages, {empty} without text layer")
    if empty:
        pages = ocr_pages(pdf, pages)
    save_pages(pages, out)
    low = [p.page for p in pages if p.metadata.get("low_text") or p.metadata.get("empty")]
    print(f"saved {out} | total chars {sum(len(p.text) for p in pages)} | "
          f"low-text/empty pages {low} | {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
