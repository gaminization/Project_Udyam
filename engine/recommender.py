"""Rule-grounded bundle recommender. The LLM (or the chat UI) only *talks*; every product that can
appear in a recommendation must pass `eligible()` against product_catalogue.csv."""
import csv, math

def load_catalogue(path):
    rows = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        r["tiers"] = [int(x) for x in r["available_city_tiers"].split(";")]
        r["need_one"] = [x for x in r["requires_one_of"].split("|") if x]
        for k in ("price_min_inr_per_month", "price_max_inr_per_month", "one_time_setup_inr", "min_contract_months", "min_employees", "min_sites", "typical_install_days"):
            r[k] = int(r[k])
        rows[r["product_id"]] = r
    return rows

def eligible(p, prof, bundle_ids=()):
    """Returns (ok, reason). prof: tier, employees, sites, has_gstin"""
    if prof["tier"] not in p["tiers"]: return False, f"not sold in Tier-{prof['tier']} cities"
    if prof["employees"] < p["min_employees"]: return False, f"for businesses with {p['min_employees']}+ staff"
    if prof["sites"] < p["min_sites"]: return False, f"for {p['min_sites']}+ locations"
    if p["requires_gstin"] == "Y" and not prof["has_gstin"]: return False, "needs an active GSTIN"
    if p["need_one"] and not any(x in bundle_ids for x in p["need_one"]): return False, "needs an internet plan first"
    return True, ""

WANT_MAP = {  # need -> (product, qty rule)
    "whatsapp": ("P15", lambda e: 1), "sms": ("P14", lambda e: 1), "email": ("P16", lambda e: e), "storage": ("P17", lambda e: 1),
    "pos": ("P19", lambda e: 1), "cctv": ("P23", lambda e: 1), "security": ("P20", lambda e: e), "wifi": ("P22", lambda e: 1),
    "website": ("P18", lambda e: 1), "failover": ("P09", lambda e: 1), "telephony": ("P12", lambda e: 1), "tollfree": ("P13", lambda e: 1),
    "iot": ("P24", lambda e: max(1, e // 10)), "fleet": ("P25", lambda e: max(1, e // 10)), "firewall": ("P21", lambda e: 1), "sdwan": ("P10", lambda e: prof_sites(e)),
}
def prof_sites(_): return 1

def pick_internet(prof, cat):
    e, g = prof["employees"], prof["has_gstin"]
    order = ["P06"] if e >= 150 else ["P05"] if e >= 50 else ["P03"] if (e >= 15 and prof["tier"] == 1) else ["P02"] if e >= 5 else ["P01"]
    for pid in order + ["P02", "P01"]:
        if eligible(cat[pid], prof)[0]: return pid
    return "P01"

def price_for(p, contract_months):
    lo, hi = p["price_min_inr_per_month"], p["price_max_inr_per_month"]
    # longer commitment -> lower end of the published range
    f = {12: 1.0, 24: 0.5, 36: 0.0}.get(contract_months, 1.0)
    return round(lo + (hi - lo) * f)

def recommend(prof, wants, cat, contract_months=12):
    items, excluded, ids = [], [], []
    def add(pid, qty, why):
        ok, reason = eligible(cat[pid], prof, ids)
        if ok: items.append({"pid": pid, "qty": qty, "why": why}); ids.append(pid)
        else: excluded.append({"pid": pid, "reason": reason})
    if "internet" in wants or not wants:
        pid = pick_internet(prof, cat)
        add(pid, prof["sites"], f"Right-sized for {prof['employees']} staff" + (f" across {prof['sites']} sites" if prof['sites'] > 1 else ""))
    if prof.get("sims"):
        pid = "P08" if prof["employees"] >= 5 else "P07"
        add(pid, prof["sims"], "Business SIMs on one bill")
    for w in wants:
        if w in WANT_MAP:
            pid, q = WANT_MAP[w]; qty = q(prof["employees"]) if not cat[pid]["unit"].startswith("per site") else prof["sites"]
            add(pid, qty, cat[pid]["product_name"])
    return items, excluded

def total(items, cat, contract_months=12):
    monthly = sum(price_for(cat[i["pid"]], contract_months) * i["qty"] for i in items)
    setup = sum(cat[i["pid"]]["one_time_setup_inr"] * (i["qty"] if cat[i["pid"]]["unit"].startswith("per site") else 1) for i in items)
    days = max([cat[i["pid"]]["typical_install_days"] for i in items] or [0])
    return monthly, setup, days
