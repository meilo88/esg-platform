import fitz
import os
import re

def verify(pdf_path, page, label, val_str):
    if not os.path.exists(pdf_path):
        return False, "File missing"
    doc = fitz.open(pdf_path)
    if page < 1 or page > len(doc):
        return False, "Page out of range"
    text = doc[page - 1].get_text()
    def clean(s):
        return re.sub(r"[\s\u3000\xa0\n\r\t，。；：、（）()]+", "", s).lower()
    c_page = clean(text)
    c_label = clean(label)
    c_val = clean(val_str)
    
    label_ok = c_label in c_page
    val_ok = c_val in c_page
    return (label_ok and val_ok), f"label({label_ok}), val({val_ok})"

print("Quote check module ready")
