"""OCR + field extraction for the 4 KYC document types.
Pipeline: remove watermark (min-channel) -> upscale/sharpen -> Tesseract -> regex parse.
We try several preprocessing variants and keep the one that yields the most fields."""
import re, subprocess, tempfile, os
from PIL import Image, ImageFilter, ImageOps

FIELDS = {
    "gst_certificate": {"gstin": r"GSTIN\s*([0-9A-Z]{15})", "legal_name": r"Legal name\s*(.+)",
        "trade_name": r"Trade name\s*(.+)", "constitution": r"Constitution\s*(.+)",
        "registration_date": r"Date of liability\s*(\d{4}-\d{2}-\d{2})"},
    "udyam_certificate": {"udyam_number": r"(UDYAM\s*-\s*[A-Z]{2}\s*-\s*\d{2}\s*-\s*\d{7})", "enterprise_name": r"Enterprise name\s*(.+)",
        "city": r"City\s*(.+)", "state": r"State\s*(.+)", "registration_date": r"Date of registration\s*(\d{4}-\d{2}-\d{2})"},
    "signatory_id": {"name": r"Name\s*\n?\s*(.+)", "designation": r"Designation\s*\n?\s*(.+)",
        "business": r"For business\s*\n?\s*(.+)", "id_no": r"(SYN-ID-\d{6})", "valid_till": r"Valid till\s*\n?\s*(\d{4}-\d{2}-\d{2})"},
    "address_proof": {"billed_to": r"Billed to\s*(.+)", "bill_date": r"Bill date\s*(\d{4}-\d{2}-\d{2})",
        "consumer_no": r"Consumer no\.?\s*(\d+)"},
}

def preprocess(path, variant):
    im = Image.open(path).convert("RGB")
    r, g, b = im.split()
    from PIL import ImageChops
    g1 = ImageChops.darker(ImageChops.darker(r, g), b)  # min channel: pink watermark -> light, black text stays dark
    if variant == "plain":
        return g1
    scale = {"x2": 2, "x3": 3}.get(variant, 2)
    g1 = g1.resize((g1.width * scale, g1.height * scale), Image.LANCZOS)
    g1 = ImageOps.autocontrast(g1, cutoff=2).filter(ImageFilter.UnsharpMask(radius=3, percent=250, threshold=2))
    if variant == "x3":
        g1 = g1.point(lambda p: 255 if p > 150 else 0)
    return g1

def run_tesseract(img, psm=6):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img.save(f.name)
    try:
        out = subprocess.run(["tesseract", f.name, "-", "--psm", str(psm)], capture_output=True, text=True).stdout
    finally:
        os.unlink(f.name)
    return out

def parse(doc_type, text):
    # join address continuation lines for readability
    text = re.sub(r"[ \t]+", " ", text)
    res = {}
    for k, pat in FIELDS[doc_type].items():
        m = re.search(pat, text, re.I if k not in ("gstin",) else 0)
        if m: res[k] = m.group(1).strip()
    if "udyam_number" in res: res["udyam_number"] = re.sub(r"\s+", "", res["udyam_number"])
    if doc_type == "gst_certificate":
        m = re.search(r"Address of principal\s*(.+?)\n\s*place of business\s*(.+?)\n", text + "\n", re.S)
        if m: res["address"] = (m.group(1).strip() + " " + m.group(2).strip()).strip()
    if doc_type == "address_proof":
        m = re.search(r"Supply address\s*(.+?)\n(.+?)\n(?:Bill date)", text, re.S)
        if m: res["address"] = (m.group(1).strip() + " " + m.group(2).strip()).strip()
    return res

def extract(path, doc_type):
    """Return (fields, meta). Tries variants until all expected fields found."""
    best, best_n, best_v = {}, -1, None
    for v in ("plain", "x2", "x3"):
        txt = run_tesseract(preprocess(path, v))
        f = parse(doc_type, txt)
        n = len(f) + (1 if "address" in f else 0)
        if n > best_n: best, best_n, best_v = f, n, v
        if len(f) >= len(FIELDS[doc_type]): break
    return best, {"variant": best_v, "fields_found": best_n, "fields_expected": len(FIELDS[doc_type])}
