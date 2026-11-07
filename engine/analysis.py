"""Funnel analysis + propensity model on smb_leads.csv. Outputs JSON used by the app and the deck."""
import pandas as pd, numpy as np, json, sys
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
d = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else "data/smb_leads.csv")
d["act"] = (d.outcome == "Activated").astype(int)
out = {}
# 1. funnel
stages = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
order = {s: i for i, s in enumerate(stages)}
d["lvl"] = d.stage_reached.map(order)
out["funnel"] = [int((d.lvl >= i).sum()) for i in range(6)]
# 2. avoidable drops: reasons a digital journey directly removes
fix = {"Owner had no time for a visit": "Self-serve (no visit)", "Visit not scheduled by sales": "Self-serve (no visit)",
       "Quote too complex to understand": "Single clear price", "Quote took too long to arrive": "Instant quote",
       "Found paperwork too long": "Smart KYC", "Missing GST or Udyam document": "Smart KYC", "Document details did not match": "Smart KYC",
       "Authorised signatory not available": "e-sign / owner OTP", "Installation delayed beyond 21 days": "Tracker + partner SLA",
       "Wrong or invalid number": "OTP-verified capture", "Unreachable after 3 attempts": "WhatsApp/App re-engage"}
dr = d[d.outcome == "Dropped"].copy()
dr["lever"] = dr.drop_reason.map(fix).fillna("Not addressed")
out["drops_by_lever"] = dr.lever.value_counts().to_dict()
out["drops_by_reason"] = dr.groupby(["stage_reached", "drop_reason"]).size().reset_index(name="n").to_dict("records")
# 3. segment economics
a = d[d.act == 1]
seg = d.groupby("segment").agg(leads=("act", "size"), act=("act", "sum"), conv=("act", "mean"), cac_lead=("acquisition_cost_inr", "mean"), spend=("acquisition_cost_inr", "sum"))
seg["cac_per_act"] = seg.spend / seg.act
seg = seg.join(a.groupby("segment").agg(mrr=("monthly_bundle_value_inr", "mean"), setup=("one_time_setup_inr", "mean"), days=("days_lead_to_activation", "mean"),
      churn=("churned_within_6_months", lambda x: (x == "Y").mean()), nps=("nps_score", "mean")))
seg["payback_months"] = seg.cac_per_act / seg.mrr
seg["ltv_6m_margin"] = seg.mrr * 6 * (1 - seg.churn / 2)
out["segments"] = seg.round(3).reset_index().to_dict("records")
out["sources"] = d.groupby("lead_source").agg(leads=("act", "size"), conv=("act", "mean"), cac_lead=("acquisition_cost_inr", "mean"), spend=("acquisition_cost_inr", "sum"), act=("act", "sum")).round(3).reset_index().to_dict("records")
# 4. propensity (stretch)
feat = ["segment", "lead_source", "current_internet", "has_gstin", "has_udyam", "city_tier", "preferred_language"]
X = pd.get_dummies(d[feat].astype(str)); X["log_emp"] = np.log1p(d.employee_count); X["sites"] = d.num_sites; X["log_spend"] = np.log1p(d.monthly_telecom_spend_inr)
Xtr, Xte, ytr, yte = train_test_split(X, d.act, test_size=0.3, random_state=7, stratify=d.act)
m = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced").fit(Xtr, ytr)
out["auc"] = round(roc_auc_score(yte, m.predict_proba(Xte)[:, 1]), 3)
d["score"] = m.predict_proba(X)[:, 1]
# lift in top decile on holdout
te = X.loc[Xte.index]; p = m.predict_proba(te)[:, 1]; k = len(p) // 10
out["top_decile_conv"] = round(float(yte.values[np.argsort(-p)[:k]].mean()), 3); out["base_conv"] = round(float(yte.mean()), 3)
coef = pd.Series(m.coef_[0], index=X.columns).sort_values()
out["top_drivers"] = coef.tail(6).round(2).to_dict(); out["bottom_drivers"] = coef.head(5).round(2).to_dict()
cand = d[(d.act == 0) & d.stage_reached.isin(["Needs assessed", "Quote accepted"])].sort_values("score", ascending=False).head(25)
out["call_list"] = cand[["lead_id", "business_name", "business_type", "city", "employee_count", "lead_source", "stage_reached", "drop_reason", "score"]].round(3).to_dict("records")
out["n"] = len(d); out["gst_conv"] = d.groupby("has_gstin").act.mean().round(3).to_dict()
out["median_bundle"] = float(a.monthly_bundle_value_inr.median()); out["avg_days"] = float(a.days_lead_to_activation.mean())
json.dump(out, open("data/analysis.json", "w"), indent=1, default=float)
print(json.dumps({k: out[k] for k in ["funnel", "drops_by_lever", "auc", "top_decile_conv", "base_conv", "top_drivers", "gst_conv", "median_bundle"]}, indent=1))
print(pd.DataFrame(out["segments"])[["segment", "leads", "act", "conv", "cac_per_act", "mrr", "churn", "payback_months"]])
print(pd.DataFrame(out["sources"]))
