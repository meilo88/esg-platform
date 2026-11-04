import os
import fitz
from pathlib import Path

def test_quote_exists(pdf_path, page, quote):
    if not os.path.exists(pdf_path):
        return False, f"File not found: {pdf_path}"
    doc = fitz.open(pdf_path)
    if page < 1 or page > len(doc):
        return False, f"Page {page} out of range (1..{len(doc)})"
    text = doc[page - 1].get_text()
    norm_text = "".join(text.split())
    norm_quote = "".join(quote.split())
    if norm_quote in norm_text:
        return True, "OK"
    # Try finding sub-string if quote has ellipses or multiple parts
    return False, f"Quote '{quote}' not found on P{page}"

if __name__ == "__main__":
    print("Test quote runner ready")
