from engine import kyc, gstin as G
from engine.recommender import load_catalogue, recommend, eligible
import csv, pandas as pd
gst, udy = kyc.load_registries("data"); cat = load_catalogue("data/product_catalogue.csv")
def codes(k): return {x["code"] for x in kyc.validate(kyc.read_applicant("data/kyc_documents", k), gst, udy) if x["severity"] != "INFO"}
# planted KYC problems
assert "GSTIN_NOT_ACTIVE" in codes("K01") and "UDYAM_NUMBER_MISSING" in codes("K01")
assert "DOC_UNREADABLE" in codes("K02") and "DOC_UNREADABLE" in codes("K04")
assert "DOC_MISSING" in codes("K05") and "ADDRESS_PROOF_STALE" in codes("K11")
assert not codes("K03") and not codes("K12")
# all registry GSTINs pass checksum (X entity-type accepted)
assert all(G.valid(g) for g in gst), "registry GSTIN checksum"
# recommender never emits an ineligible product, on every real lead profile
d = pd.read_csv("data/smb_leads.csv"); bad = 0
for r in d.itertuples():
    prof = dict(tier=r.city_tier, employees=r.employee_count, sites=r.num_sites, has_gstin=r.has_gstin == "Y", sims=2)
    items, _ = recommend(prof, ["internet", "whatsapp", "email", "storage", "cctv", "pos", "firewall", "iot", "sdwan", "failover"], cat)
    ids = []
    for i in items:
        assert eligible(cat[i["pid"]], prof, ids)[0]; ids.append(i["pid"])
print("all tests passed on", len(d), "lead profiles")
