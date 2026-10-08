"""
Ingest PDFs / text files into the knowledge_documents table.

For PDFs: uses Tesseract OCR with Sinhala language pack, because the
source PDFs use legacy fonts that don't expose real Unicode text.

Usage (from backend/):
    py.bat scripts/ingest_knowledge.py --path "E:\\HEX_HIVE\\agritech\\knowledge"
    py.bat scripts/ingest_knowledge.py --path mydoc.pdf --crop chili --topic disease
    py.bat scripts/ingest_knowledge.py --path folder --language si --force

What it does:
    1. Finds .pdf / .txt / .md files under the given path.
    2. For each PDF: renders each page to an image, OCRs it with Tesseract.
       For text files: reads them directly.
    3. Splits the text into ~1800-char chunks with overlap.
    4. Embeds all chunks via BGE-M3.
    5. Inserts into knowledge_documents. Skips files whose sha256 is
       already present (unless --force).

Re-running is safe: duplicates are skipped by source_hash.
"""
import argparse
import hashlib
import logging
import sys
from pathlib import Path
from uuid import uuid4

import fitz  # PyMuPDF — for rendering PDF pages to images
import pytesseract
from PIL import Image
from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models.knowledge_document import KnowledgeDocument
from app.services.embedding_service import embed_documents


# --- Tesseract configuration ------------------------------------------------
#
# Windows installs tesseract outside PATH by default. Point pytesseract
# at the executable directly. If you installed tesseract elsewhere,
# change this path.
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ingest")


SUPPORTED_EXTS = {".pdf", ".txt", ".md"}

# Chunking config (character-based; multilingual tokenizers average ~3-4
# chars per token, so 1800 chars ≈ 450-550 tokens).
CHUNK_CHARS = 1800
CHUNK_OVERLAP = 200

# OCR rendering DPI. 300 is the accepted sweet spot for Tesseract:
# high enough for accuracy, low enough to be reasonably fast.
OCR_DPI = 300

# Map our --language flags to tesseract language codes.
# 'si' uses Sinhala, 'ta' Tamil, 'en' English. We always combine
# with English so embedded scientific names ("Erwinia spp.") are
# read correctly too.
TESSERACT_LANG_MAP = {
    "si": "sin+eng",
    "ta": "tam+eng",
    "en": "eng",
}


def find_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_EXTS else []
    files: list[Path] = []
    for ext in SUPPORTED_EXTS:
        files.extend(root.rglob(f"*{ext}"))
    return sorted(set(files))


def ocr_pdf(path: Path, language: str) -> list[str]:
    """
    Return per-page OCR text from a PDF.

    Renders each page to a 300 DPI image, runs Tesseract with the
    configured language pack, and collects the text.
    """
    tess_lang = TESSERACT_LANG_MAP.get(language, "eng")

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        log.warning(f"Cannot open PDF {path.name}: {e}")
        return []

    pages: list[str] = []
    total = len(doc)
    log.info(f"  OCR'ing {total} pages (lang={tess_lang}, dpi={OCR_DPI})…")

    for i in range(total):
        try:
            page = doc[i]
            # Render page to an image at the target DPI
            pix = page.get_pixmap(dpi=OCR_DPI)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # Run OCR
            text = pytesseract.image_to_string(img, lang=tess_lang)
            pages.append(text or "")

            # Log progress every 10 pages so the user sees movement
            if (i + 1) % 10 == 0 or (i + 1) == total:
                log.info(f"  …{i + 1}/{total} pages OCR'd")
        except Exception as e:
            log.warning(f"  {path.name} page {i}: {e}")
            pages.append("")

    doc.close()
    return pages


def extract_pages(path: Path, language: str = "si") -> list[str]:
    """Return per-page text. Uses OCR for PDFs, direct read for .txt/.md."""
    if path.suffix.lower() == ".pdf":
        return ocr_pdf(path, language)
    else:
        try:
            return [path.read_text(encoding="utf-8", errors="replace")]
        except Exception as e:
            log.warning(f"Cannot read {path.name}: {e}")
            return []


def split_into_chunks(
    text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """
    Character-based chunker with overlap.
    Tries to end chunks on paragraph or sentence boundaries.
    """
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window_start = max(start + int(size * 0.8), start)
            best = -1
            for sep in ("\n\n", "\n", ". ", "。", "। "):
                idx = text.rfind(sep, window_start, end)
                if idx > best:
                    best = idx + len(sep)
            if best > 0:
                end = best
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def already_ingested(db, source_hash: str) -> bool:
    row = db.execute(
        select(KnowledgeDocument.id)
        .where(KnowledgeDocument.source_hash == source_hash)
        .limit(1)
    ).first()
    return row is not None


def ingest_file(
    db,
    path: Path,
    *,
    crop: str | None,
    topic: str | None,
    language: str,
    force: bool,
) -> int:
    """Ingest one file. Returns number of chunks inserted (0 = skipped)."""
    h = file_hash(path)
    if not force and already_ingested(db, h):
        log.info(f"SKIP {path.name} — already ingested (hash {h[:12]}…)")
        return 0

    log.info(f"Processing {path.name}…")
    pages = extract_pages(path, language=language)
    if not pages or not any(p.strip() for p in pages):
        log.warning(
            f"SKIP {path.name} — no extractable text "
            f"(OCR failed? wrong tesseract path?)"
        )
        return 0

    all_chunks: list[tuple[int, str]] = []
    for page_num, page_text in enumerate(pages, start=1):
        for chunk in split_into_chunks(page_text):
            all_chunks.append((page_num, chunk))

    if not all_chunks:
        log.warning(f"SKIP {path.name} — zero chunks after splitting")
        return 0

    log.info(f"Embedding {len(all_chunks)} chunks from {path.name}…")
    texts = [c for _, c in all_chunks]
    vectors = embed_documents(texts)

    for idx, ((page_num, chunk_text), vec) in enumerate(zip(all_chunks, vectors)):
        doc = KnowledgeDocument(
            id=uuid4(),
            source=path.name,
            source_type="pdf-ocr" if path.suffix.lower() == ".pdf" else path.suffix.lstrip(".").lower(),
            source_hash=h,
            title=path.stem,
            language=language,
            crop=crop,
            topic=topic,
            chunk_index=idx,
            content=chunk_text,
            token_count=max(1, len(chunk_text) // 4),
            embedding=vec,
            metadata_={"page": page_num, "path": str(path)},
        )
        db.add(doc)

    db.commit()
    log.info(f"✓ {path.name}: inserted {len(all_chunks)} chunks")
    return len(all_chunks)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Ingest knowledge documents into Postgres (OCR for PDFs)."
    )
    ap.add_argument("--path", required=True, help="File or folder to ingest")
    ap.add_argument("--crop", default=None, help="Crop tag, e.g. chili, tomato")
    ap.add_argument("--topic", default=None, help="Topic tag, e.g. disease, pest")
    ap.add_argument("--language", default="si", help="Language: en, si, ta")
    ap.add_argument("--force", action="store_true", help="Re-ingest even if hash matches")
    args = ap.parse_args()

    # Verify tesseract is reachable before doing any work
    if not Path(TESSERACT_CMD).exists():
        print(f"ERROR: Tesseract not found at {TESSERACT_CMD}")
        print("Edit TESSERACT_CMD at the top of this script to point to tesseract.exe")
        sys.exit(1)

    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"Path not found: {root}")
        sys.exit(1)

    files = find_files(root)
    if not files:
        print(f"No supported files (.pdf, .txt, .md) under {root}")
        sys.exit(1)

    print(f"Found {len(files)} file(s) under {root}")
    print(f"OCR mode: tesseract with lang={TESSERACT_LANG_MAP.get(args.language, 'eng')}")
    print()

    db = SessionLocal()
    total_inserted = 0
    total_files = 0
    try:
        for f in files:
            ins = ingest_file(
                db, f,
                crop=args.crop,
                topic=args.topic,
                language=args.language,
                force=args.force,
            )
            if ins:
                total_files += 1
                total_inserted += ins
    finally:
        db.close()

    print()
    print("=" * 60)
    print(f"Done. {total_files} file(s) ingested, {total_inserted} chunks total.")
    print("=" * 60)


if __name__ == "__main__":
    main()