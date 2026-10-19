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


def build_fuzzy(kg: KG, used_ids: set[str], seed: int = 42) -> list[dict]:
    """5 extra questions with damaged property names (D22), appended as Q31-Q35 so
    Q01-Q30 stay comparable with earlier runs. Own RNG stream, so they never shift
    the original 30.

    4 resolvable (dropped brand word, typo, '&' -> 'and', missing last word) and
    1 ambiguous, where the right behaviour is to abstain / ask which property.
    """
    rng = random.Random(f"{seed}-golden-fuzzy")
    props = {p["id"]: p for p in kg.properties}
    brand_name = {b["id"]: b["name"] for b in kg.brands}
    chain_word = {c["id"]: c["name"].removesuffix(" Hotels") for c in kg.chains}
    chain_of = {b["id"]: b["chain_id"] for b in kg.brands}
    free = sorted(set(props) - used_ids)

    def typo(word: str) -> str:
        i = rng.randrange(len(word) - 1)
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]

    def by_brand_city(pid):
        p = props[pid]
        return [q for q in props.values() if q["brand_id"] == p["brand_id"] and q["city"] == p["city"]]

    qs = []

    def add(qtype, pid, shown_name, kind):
        pol = kg.resolve("property", pid)
        if kind == "time":
            q = {"question": f"What is the earliest check-in time at {shown_name}?",
                 "expected": {"kind": "time", "value": pol["check_in_time"]["value"]}}
        else:
            d = CHECKIN_BASE + timedelta(days=rng.randrange(60))
            q = {"question": f"A guest checks in at {shown_name} on {d.isoformat()}. "
                             "Until when can they cancel free of charge?",
                 "expected": {"kind": "datetime", "value": _deadline(
                     d, pol["check_in_time"]["value"], pol["cancel_window_hours"]["value"])}}
        qs.append({"type": qtype, "property_id": pid, "shown_name": shown_name, **q,
                   "evidence_docs": [pid]})
        free.remove(pid)

    # Dropped brand word: "Aurelia Suites Hamburg Park" -> "Aurelia Hamburg Park".
    pid = rng.choice(free)
    p = props[pid]
    short = p["name"].replace(brand_name[p["brand_id"]], chain_word[chain_of[p["brand_id"]]])
    add("fuzzy_dropped_brand_word", pid, short, "datetime")

    # Transposed letters in the last word.
    pid = rng.choice(free)
    words = props[pid]["name"].split(" ")
    add("fuzzy_typo", pid, " ".join(words[:-1] + [typo(words[-1])]).lower(), "time")

    # '&' written as 'and' (only Harbor & Pine has one).
    pid = rng.choice([x for x in free if "&" in props[x]["name"]])
    add("fuzzy_ampersand", pid, props[pid]["name"].replace("&", "and"), "datetime")

    # Missing last word, but still unique within brand + city.
    pid = rng.choice([x for x in free if len(by_brand_city(x)) == 1])
    p = props[pid]
    add("fuzzy_missing_last_word", pid, f"{brand_name[p['brand_id']]} {p['city']}", "time")

    # Ambiguous: chain + city where the chain has several properties in that city.
    groups: dict[tuple[str, str], list[str]] = {}
    for x in props.values():
        groups.setdefault((chain_of[x["brand_id"]], x["city"]), []).append(x["id"])
    chain_id, city = rng.choice(sorted(k for k, v in groups.items() if len(v) >= 3))
    qs.append({"type": "fuzzy_ambiguous", "property_id": None,
               "candidates": sorted(groups[(chain_id, city)]),
               "shown_name": f"the {chain_word[chain_id]} hotel in {city}",
               "question": f"What is the earliest check-in time at the {chain_word[chain_id]} hotel in {city}?",
               "expected": {"kind": "abstain", "value": None}, "evidence_docs": []})
    return qs


ASKED_KEY = {"datetime": "cancel_window_hours", "eur": "pet_fee_eur"}


def add_governing(q: dict, kg: KG) -> dict:
    """The evidence that actually establishes the answer (D19). An answer that is
    value-correct but cites none of it scores as `unsupported`.

    docs:  the document that states the value. For by-reference questions that is
           the brand doc (2-hop) or the chain doc (3-hop), not the property doc
           that defers.
    facts: the KG fact ID for the asked key, on the property (or the rate plan).
    """
    kind, pid = q["expected"]["kind"], q["property_id"]
    if kind == "abstain":
        q["governing"] = {"docs": [], "facts": []}
        return q
    if q["type"].startswith("exception_by_reference"):
        docs = [q["evidence_docs"][-1]]
    else:
        docs = [pid]
    if kind == "no_free_cancellation":
        facts = [f"kg:{q['rate_plan_id']}:refundable"]
    elif kind == "time":
        facts = [f"kg:{pid}:{'check_out_time' if 'check_out' in q['type'] else 'check_in_time'}"]
    else:
        facts = [f"kg:{pid}:{ASKED_KEY[kind]}"]
    q["governing"] = {"docs": docs, "facts": facts}
    return q
