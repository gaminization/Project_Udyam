"""Packs catalogue, registries, OCR output, thumbnails and analysis into one JSON for the static demo app."""
import json, csv, base64, io, os, sys
sys.path.insert(0, ".")
from PIL import Image
from engine import kyc
gst, udy = kyc.load_registries("data")
cat = list(csv.DictReader(open("data/product_catalogue.csv", encoding="utf-8")))
ocr_out = {}
thumbs = {}
for i in range(1, 13):
    k = f"K{i:02d}"; docs = kyc.read_applicant("data/kyc_documents", k)
    ocr_out[k] = {t: (None if d is None else {"fields": d["fields"], "meta": d["meta"]}) for t, d in docs.items()}
    for t, d in docs.items():
        if d is None: continue
        im = Image.open(f"data/kyc_documents/{d['file']}").convert("RGB"); im = im.resize((360, int(im.height * 360 / im.width)))
        b = io.BytesIO(); im.save(b, "JPEG", quality=55); thumbs[f"{k}_{t}"] = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
blob = {"catalogue": cat,
        "gst": [[g, r["legal_name"], r["trade_name"], r["principal_place_of_business"], r["status"]] for g, r in gst.items()],
        "udyam": [[u, r["enterprise_name"], r["city"]] for u, r in udy.items()],
        "ocr": ocr_out, "thumbs": thumbs, "analysis": json.load(open("data/analysis.json"))}
json.dump(blob, open("app/data.json", "w"), separators=(",", ":"))
tmpl = open("app/template.html", encoding="utf-8").read()
open("app/index.html", "w", encoding="utf-8").write(tmpl.replace("__DATA__", json.dumps(blob, separators=(",", ":"))))
print(f"Packed app/data.json ({os.path.getsize('app/data.json') / 1e6:.2f} MB) and app/index.html ({os.path.getsize('app/index.html') / 1e6:.2f} MB)")
