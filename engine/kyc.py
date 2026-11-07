"""Smart KYC: OCR -> validate against mock registries -> cross-document checks.
Every finding has a severity: BLOCK (cannot proceed), REVIEW (human/ask user), INFO."""
import csv, re, datetime as dt, difflib, os
from . import ocr, gstin as G
from PIL import Image, ImageFilter, ImageChops
import numpy as np

TODAY = dt.date(2026, 7, 15)          # per README
ADDRESS_MAX_AGE_DAYS = 90
DOC_TYPES = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]
DOC_LABEL = {"gst_certificate": "GST certificate", "udyam_certificate": "Udyam certificate",
             "signatory_id": "Signatory ID", "address_proof": "Address proof"}

def load_registries(data_dir):
    gst = {r["gstin"]: r for r in csv.DictReader(open(os.path.join(data_dir, "mock_gstin_registry.csv"), encoding="utf-8"))}
    udy = {r["udyam_number"]: r for r in csv.DictReader(open(os.path.join(data_dir, "mock_udyam_registry.csv"), encoding="utf-8"))}
    return gst, udy

def norm(s):
    s = re.sub(r"\(prop\.?,?\s*", " ", (s or "").lower()); s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())
def sim(a, b):
    a, b = norm(a), norm(b)
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0
def name_in_legal(person, legal):  # proprietor name appears inside "Name (Prop. Shop)"
    return norm(person) in norm(legal) or sim(person, legal.split("(")[0]) > 0.85
def mask(v, keep=4):
    return "*" * max(len(v) - keep, 0) + v[-keep:] if v else v

def blur_score(path):
    """Variance of Laplacian on the text area; low = blurry photo."""
    g = np.asarray(Image.open(path).convert("L"), dtype=float)[150:700, 40:1200]
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())

def read_applicant(doc_dir, kid):
    docs = {}
    for t in DOC_TYPES:
        p = os.path.join(doc_dir, f"{kid}_{t}.png")
        if not os.path.exists(p): docs[t] = None; continue
        fields, meta = ocr.extract(p, t)
        meta["blur"] = round(blur_score(p), 1)
        docs[t] = {"fields": fields, "meta": meta, "file": os.path.basename(p)}
    return docs

def validate(docs, gst_reg, udy_reg):
    F = []  # findings
    def add(sev, code, doc, msg, fix=None): F.append({"severity": sev, "code": code, "doc": doc, "message": msg, "fix": fix})
    f = {t: (docs[t]["fields"] if docs[t] else {}) for t in DOC_TYPES}

    # 1 completeness and readability
    for t in DOC_TYPES:
        d = docs[t]
        if d is None:
            add("BLOCK", "DOC_MISSING", t, f"{DOC_LABEL[t]} was not uploaded.", f"Upload your {DOC_LABEL[t]}."); continue
        need = len(ocr.FIELDS[t])
        found = len(d["fields"]) - (1 if "address" in d["fields"] else 0)
        if found < need - 1 or (t == "gst_certificate" and "gstin" not in d["fields"] and found < need):
            if d["meta"]["blur"] < 200 or found < need - 1:
                add("BLOCK", "DOC_UNREADABLE", t, f"We couldn't read your {DOC_LABEL[t]} clearly (photo looks blurry or tilted).",
                    "Retake the photo in good light, flat on a table, all four corners visible.")

    # 2 GSTIN
    gs = f["gst_certificate"].get("gstin"); g_rec = None
    if gs:
        fixed, repaired = G.repair(gs)
        if not G.valid(fixed): fixed, repaired = G.repair_with_registry(gs, gst_reg)
        if not G.valid(fixed): add("BLOCK", "GSTIN_INVALID", "gst_certificate", f"GSTIN {mask(gs)} fails the format/checksum test.", "Check the number on your certificate.")
        else:
            if repaired: add("INFO", "GSTIN_OCR_FIXED", "gst_certificate", "We auto-corrected look-alike characters misread from the photo; please confirm your GSTIN on screen.")
            gs = fixed; f["gst_certificate"]["gstin"] = fixed
            g_rec = gst_reg.get(fixed)
            if not g_rec: add("BLOCK", "GSTIN_NOT_FOUND", "gst_certificate", f"GSTIN {mask(fixed)} is not in the GST registry.", "Re-enter your GSTIN or contact your CA.")
            else:
                if g_rec["status"] != "Active":
                    add("BLOCK", "GSTIN_NOT_ACTIVE", "gst_certificate", f"GSTIN is {g_rec['status']} in the registry. Products that need GST can't be sold.", "Choose products that don't need GST, or reactivate your GSTIN.")
                if sim(g_rec["legal_name"], f["gst_certificate"].get("legal_name", "")) < 0.8:
                    add("BLOCK", "GST_NAME_MISMATCH", "gst_certificate", f"Legal name on certificate ('{f['gst_certificate'].get('legal_name')}') differs from registry ('{g_rec['legal_name']}').", "Upload the latest certificate.")
    elif docs["gst_certificate"]:
        cand = [r for r in gst_reg.values() if f["gst_certificate"].get("trade_name") and sim(r["trade_name"], f["gst_certificate"]["trade_name"]) > 0.92]
        if cand: add("REVIEW", "GSTIN_SUGGEST", "gst_certificate", f"GSTIN unreadable. Is your GSTIN {mask(cand[0]['gstin'], 5)}? ({cand[0]['trade_name']}, {cand[0]['state']})", "Confirm or type your GSTIN.")

    # 3 Udyam
    un = f["udyam_certificate"].get("udyam_number")
    if docs["udyam_certificate"] and not un:
        add("BLOCK", "UDYAM_NUMBER_MISSING", "udyam_certificate", "No Udyam registration number found on the certificate.", "Upload the full Udyam certificate showing the number.")
    if un:
        u = udy_reg.get(un)
        if not u: add("BLOCK", "UDYAM_NOT_FOUND", "udyam_certificate", f"Udyam number {mask(un)} not found in the Udyam registry.", "Check the number or re-download the certificate from udyamregistration.gov.in.")
        else:
            if sim(u["enterprise_name"], f["udyam_certificate"].get("enterprise_name", "")) < 0.8:
                add("BLOCK", "UDYAM_NAME_MISMATCH", "udyam_certificate", f"Enterprise name on certificate differs from registry ('{u['enterprise_name']}').")
            if u["city"].lower() != f["udyam_certificate"].get("city", "").lower():
                add("REVIEW", "UDYAM_CITY_MISMATCH", "udyam_certificate", f"City on certificate ({f['udyam_certificate'].get('city')}) differs from registry ({u['city']}).")

    # 4 cross-document: business identity
    biz_names = {}
    if g_rec: biz_names["GST registry"] = g_rec["trade_name"]
    elif f["gst_certificate"].get("trade_name"): biz_names["GST certificate"] = f["gst_certificate"]["trade_name"]
    if f["udyam_certificate"].get("enterprise_name"): biz_names["Udyam certificate"] = f["udyam_certificate"]["enterprise_name"]
    if f["signatory_id"].get("business"): biz_names["Signatory ID"] = f["signatory_id"]["business"]
    if f["address_proof"].get("billed_to"): biz_names["Address proof"] = f["address_proof"]["billed_to"]
    ref_k = next(iter(biz_names), None)
    if ref_k:
        for k, v in biz_names.items():
            if k != ref_k and sim(v, biz_names[ref_k]) < 0.85:
                add("BLOCK", "BUSINESS_NAME_MISMATCH", "cross", f"Business name differs: {k} says '{v}' but {ref_k} says '{biz_names[ref_k]}'.", "Upload documents that carry the same business name.")

    # 5 signatory
    sid = f["signatory_id"]
    if sid.get("valid_till"):
        if dt.date.fromisoformat(sid["valid_till"]) < TODAY:
            add("BLOCK", "ID_EXPIRED", "signatory_id", f"Signatory ID expired on {sid['valid_till']}.", "Upload a valid ID.")
    legal = (g_rec or {}).get("legal_name") or f["gst_certificate"].get("legal_name")
    if sid.get("name") and legal and "(prop" in legal.lower() and not name_in_legal(sid["name"], legal):
        add("BLOCK", "SIGNATORY_NAME_MISMATCH", "cross", f"Name on ID ('{sid['name']}') doesn't match the proprietor on the GST certificate ('{legal}').", "Use the proprietor's ID, or add an authorisation letter.")
    if (g_rec or {}).get("constitution") and "(prop" not in (legal or "").lower() and sid.get("designation") and sid["designation"].lower() not in ("owner", "partner", "director", "manager", "proprietor", "office admin"):
        add("REVIEW", "SIGNATORY_ROLE", "signatory_id", f"Designation '{sid['designation']}' may not be authorised to sign.")
    if sid.get("designation", "").lower() in ("office admin", "manager", "accountant") :
        add("REVIEW", "SIGNATORY_AUTH", "signatory_id", f"Signatory is '{sid['designation']}'. We need an authorisation letter or the owner to e-sign.", "Owner e-signs via Aadhaar OTP, or upload an authorisation letter.")

    # 6 address proof
    ap = f["address_proof"]
    if ap.get("bill_date"):
        age = (TODAY - dt.date.fromisoformat(ap["bill_date"])).days
        if age > ADDRESS_MAX_AGE_DAYS:
            add("BLOCK", "ADDRESS_PROOF_STALE", "address_proof", f"Bill is {age} days old (limit {ADDRESS_MAX_AGE_DAYS}).", "Upload a bill dated within the last 90 days.")
    addr_ref = (g_rec or {}).get("principal_place_of_business") or f["gst_certificate"].get("address")
    if ap.get("address") and addr_ref:
        s = sim(ap["address"], addr_ref)
        if s < 0.9:
            add("BLOCK" if s < 0.7 else "REVIEW", "ADDRESS_MISMATCH", "cross", f"Address on bill differs from the GST address (match {int(s*100)}%).", "Upload a bill for the registered address, or update the GST address.")
    return F

def verdict(findings):
    if any(x["severity"] == "BLOCK" for x in findings): return "ACTION_REQUIRED"
    if any(x["severity"] == "REVIEW" for x in findings): return "NEEDS_REVIEW"
    return "VERIFIED"
