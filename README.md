# Project Udyam Digital – prototype

Self-serve acquisition and onboarding for small businesses: Advisor → Quote → Smart KYC → Tracker.
All data is synthetic (supplied with the case).

## Run it
```
pip install pandas scikit-learn pillow numpy       # plus: apt install tesseract-ocr
python engine/analysis.py data/smb_leads.csv       # funnel, segments, lead-score model -> data/analysis.json
python run_kyc.py K01                              # OCR + validate one applicant (or: python run_kyc.py all)
python tests.py                                    # rule + KYC checks against the planted problems
python engine/build_app_data.py                    # pack data for the web app
# open app/index.html in a browser (single file, no server needed)
```

## Layout
- `engine/ocr.py` – watermark removal, upscale, Tesseract, field parsing (4 document types)
- `engine/gstin.py` – GSTIN format + checksum, look-alike character repair (registry-assisted)
- `engine/kyc.py` – registry lookups, cross-document checks, verdict (VERIFIED / NEEDS_REVIEW / ACTION_REQUIRED)
- `engine/recommender.py` – catalogue eligibility rules (tier, size, sites, GSTIN, dependencies) and bundle builder
- `engine/analysis.py` – funnel, segment economics, propensity model
- `app/template.html` – the 5-tab web app (EN/HI); `app/index.html` is the built single file
- `docs/architecture.dot|png` – architecture diagram

## Honest limits
- The web demo replays OCR output computed by the Python engine for the 12 specimen applicants and re-runs every
  validation live in the browser. Uploading arbitrary photos needs the Python service.
- The advisor is rules-driven. In production an LLM may phrase the advice; eligibility and price stay in rules.
- Registries are the supplied mock files. DigiLocker, e-sign, WhatsApp and partner APIs are production integrations.
- Prices: 12 months = top of catalogue range, 24 months = mid-point, 36 months = bottom.
