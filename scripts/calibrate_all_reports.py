import os
import sys
import fitz
import re
import unicodedata
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.pdf_parser import PDFParser

def test_quote(pdf_path, page, quote):
    parser = PDFParser(pdf_path)
    return parser.verify_quote_in_page(quote, page)

print("Calibrator ready.")
