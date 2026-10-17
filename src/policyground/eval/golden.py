"""Golden Q/A pairs derived from the KG itself (D2): 20 plain, 5 exception,
5 unanswerable. Every expected answer comes from `KG.resolve`, never from text.

Expected answers are typed so scoring is deterministic (no LLM judge, PLAN §6):
  datetime  "YYYY-MM-DD HH:MM"     last moment of free cancellation
  time      "HH:MM"                check-in / check-out
  eur       int                    pet fee per night
  no_free_cancellation  None       non-refundable rate plan
  abstain   None                   the KG has no such fact
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from policyground.seed.kg import KG

CHECKIN_BASE = date(2026, 11, 1)

UNANSWERABLE = [
    ("parking", "How much does parking cost per day at {name}?"),
    ("shuttle", "Does {name} offer an airport shuttle, and what does it cost?"),
    ("min_age", "What is the minimum age to check in at {name}?"),
    ("city_tax", "How much city tax per night is charged at {name}?"),
    ("late_checkout", "What is the fee for a late check-out until 15:00 at {name}?"),
]


def _deadline(checkin: date, check_in_time: str, window_hours: int) -> str:
    hh, mm = map(int, check_in_time.split(":"))
    dt = datetime(checkin.year, checkin.month, checkin.day, hh, mm) - timedelta(hours=window_hours)
    return dt.strftime("%Y-%m-%d %H:%M")


def build(kg: KG, manifest: dict, seed: int = 42) -> list[dict]:
    rng = random.Random(f"{seed}-golden")
    props = {p["id"]: p for p in kg.properties}
    pol = {pid: kg.resolve("property", pid) for pid in props}
    brand_of = {p["id"]: p["brand_id"] for p in kg.properties}
    chain_of = {b["id"]: b["chain_id"] for b in kg.brands}

    def by_reference_docs(pid):
        docs = [pid, f"brand-{brand_of[pid]}"]
        if pol[pid]["cancel_window_hours"]["source_type"] == "chain":
            docs.append(f"chain-{chain_of[brand_of[pid]]}")
        return docs

    def checkin_date():
        return CHECKIN_BASE + timedelta(days=rng.randrange(60))

    def cancel_q(pid, qtype):
        d = checkin_date()
        p = pol[pid]
        return {
            "type": qtype,
            "property_id": pid,
            "question": f"A guest checks in at {props[pid]['name']} on {d.isoformat()}. "
                        "Until when can they cancel free of charge?",
            "expected": {"kind": "datetime", "value": _deadline(
                d, p["check_in_time"]["value"], p["cancel_window_hours"]["value"])}
        }

    used: set[str] = set()

    def pick(candidates):
        pid = rng.choice(sorted(set(candidates) - used))
        used.add(pid)
        return pid

    stated = [pid for pid in props if not manifest[pid]["cancel_by_reference"]]
    by_ref = [pid for pid in props if manifest[pid]["cancel_by_reference"]]
    by_ref_3hop = [pid for pid in by_ref if pol[pid]["cancel_window_hours"]["source_type"] == "chain"]
    overridden = [pid for pid in props if pol[pid]["cancel_window_hours"]["source_type"] == "property"
                  and kg.resolve("brand", brand_of[pid])["cancel_window_hours"]["value"]
                  != pol[pid]["cancel_window_hours"]["value"]]
    nonref = {p["property_id"]: p["id"] for p in kg.rate_plans if p["kind"] == "non_refundable"}
    pets = [pid for pid in props if pol[pid]["pets_allowed"]["value"]]

    qs: list[dict] = []

    # --- 20 plain: the answer is stated in the property's own doc.
    plain_stated = [pid for pid in stated if pid not in overridden]
    for _ in range(8):
        qs.append(cancel_q(pick(plain_stated), "plain_cancel_deadline"))
    for key, label in [("check_in_time", "earliest check-in time"), ("check_out_time", "latest check-out time")]:
        for _ in range(4):
            pid = pick(props)
            qs.append({"type": f"plain_{key}", "property_id": pid,
                       "question": f"What is the {label} at {props[pid]['name']}?",
                       "expected": {"kind": "time", "value": pol[pid][key]["value"]}})
    for _ in range(4):
        pid = pick(pets)
        qs.append({"type": "plain_pet_fee", "property_id": pid,
                   "question": f"How much is the pet fee per night at {props[pid]['name']}?",
                   "expected": {"kind": "eur", "value": pol[pid]["pet_fee_eur"]["value"]}})

    # --- 5 exception.
    for _ in range(2):
        pid = pick(nonref)
        d = checkin_date()
        qs.append({"type": "exception_non_refundable", "property_id": pid, "rate_plan_id": nonref[pid],
                   "question": f"A guest booked the non-refundable rate at {props[pid]['name']}, "
                               f"checking in on {d.isoformat()}. Until when can they cancel free of charge?",
                   "expected": {"kind": "no_free_cancellation", "value": None}})
    qs.append(cancel_q(pick(by_ref_3hop), "exception_by_reference_3hop"))
    qs.append(cancel_q(pick(set(by_ref) - set(by_ref_3hop)), "exception_by_reference_2hop"))
    qs.append(cancel_q(pick(overridden), "exception_property_override"))

    # --- 5 unanswerable: plausible questions about facts the KG never holds.
    for topic, template in UNANSWERABLE:
        pid = pick(props)
        qs.append({"type": f"unanswerable_{topic}", "property_id": pid,
                   "question": template.format(name=props[pid]["name"]),
                   "expected": {"kind": "abstain", "value": None}})

    for q in qs:
        pid = q["property_id"]
        if q["type"].startswith("exception_by_reference"):
            q["evidence_docs"] = by_reference_docs(pid)
        elif q["type"].startswith("unanswerable"):
            q["evidence_docs"] = []
        else:
            q["evidence_docs"] = [pid]
    for i, q in enumerate(qs, start=1):
        q["id"] = f"Q{i:02d}"
    return [{"id": q.pop("id"), **q} for q in qs]
