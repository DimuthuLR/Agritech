"""Test which PDF extractor produces readable Sinhala."""
import sys
from pathlib import Path

import fitz  # PyMuPDF


def extract_page(pdf_path: str, page_num: int = 5) -> None:
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    text = page.get_text()
    doc.close()
    print(f"\n=== Page {page_num+1} of {Path(pdf_path).name} ===\n")
    print(text[:800])


if __name__ == "__main__":
    extract_page(sys.argv[1] if len(sys.argv) > 1 else "E:/HEX_HIVE/agritech/knowledge/Chili-Book.pdf")