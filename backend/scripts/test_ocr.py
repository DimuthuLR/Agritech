"""Quick OCR test on page 5 of Chili-Book.pdf."""
import fitz
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

doc = fitz.open(r"E:\HEX_HIVE\agritech\knowledge\Chili-Book.pdf")
page = doc[10]  # page 11 (0-indexed)
pix = page.get_pixmap(dpi=300)
img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
text = pytesseract.image_to_string(img, lang="sin+eng")
print(text[:1500])