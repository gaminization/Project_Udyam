import sys, json
from engine import kyc
gst, udy = kyc.load_registries("data")
ids = [f"K{i:02d}" for i in range(1, 13)] if sys.argv[1:] in (["all"], []) else sys.argv[1:]
for k in ids:
    docs = kyc.read_applicant("data/kyc_documents", k); F = kyc.validate(docs, gst, udy)
    print(f"\n{k}: {kyc.verdict(F)}")
    for x in F: print(f"  [{x['severity']}] {x['message']}" + (f"  -> {x['fix']}" if x['fix'] else ""))
