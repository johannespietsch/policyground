"""Insurance adapter: travel-insurance coverage policies for claims-support agents.

Hierarchy: insurer -> product -> tier -> policy -> coverage_option.
Insurers set every default, products and tiers override some, individual policies
override a few more. Coverage options (medical, baggage, trip_cancellation) carry one
fact, `excluded`: an excluded option is not covered at all, whatever the other terms.

All names are fictional. Deterministic: seeded random.Random, render choices via the Chooser.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from policyground.kgmodel import GenericKG
from policyground.render_choices import Chooser

TENANT = "insurance"
N_POLICIES = 60
PRODUCTS_PER_INSURER = 2
TIERS = ["Basic", "Plus", "Premium"]
OPTIONS = ["medical", "baggage", "trip_cancellation"]
OPTION_LABEL = {"medical": "Medical expenses", "baggage": "Baggage", "trip_cancellation": "Trip cancellation"}
OPTION_WORDS = {"medical": "medical", "baggage": "baggage", "trip_cancellation": "trip cancellation"}

INSURERS = ["Halcyon Assurance", "Corvane Mutual", "Brightwater Insurance"]
PRODUCT_WORDS = ["Voyager", "Wayfarer", "Globetrotter", "Nomad", "Compass", "Horizon"]
NAME_WORDS = ["Marrowby", "Vellacott", "Tamsford", "Quenby", "Dunmere", "Esterly", "Pennick",
              "Ashgrove", "Fenwright", "Lindqvar", "Brannock", "Harlowe", "Oakhurst", "Selwyth",
              "Thornacre", "Wrexley", "Calloway", "Ivormead", "Rosling", "Glenmarch"]
TRIP_WORDS = ["Alpine", "Coastal", "Island", "Lakeside", "Highland", "Riviera", "Fjord", "Desert"]

CLAIM_WINDOWS = [30, 45, 60, 90]
DEDUCTIBLES = [75, 100, 150, 200, 250]
WAITING = [5, 10, 14, 21]

P_PRODUCT_OVERRIDE = 0.5
P_TIER_OVERRIDE = 0.4
P_POLICY_OVERRIDE = 0.2
P_EXCLUDED = {"medical": 0.08, "baggage": 0.3, "trip_cancellation": 0.25}
P_DEFER = 0.3   # share of inherited policy-doc sections that defer to the tier's standard terms

KEYS = ["claim_window_days", "deductible_eur", "waiting_period_days"]
VALUES = {"claim_window_days": CLAIM_WINDOWS, "deductible_eur": DEDUCTIBLES, "waiting_period_days": WAITING}
SECTION = {"claim_window_days": "Claims", "deductible_eur": "Deductible", "waiting_period_days": "Waiting period"}


# ---------------------------------------------------------------- generate

def generate(seed: int, snapshot_date: str) -> dict:
    rng = random.Random(f"{seed}-insurance")
    entities: list[dict] = []
    facts: list[dict] = []

    def entity(eid, etype, parent, name, attrs=None):
        entities.append({"id": eid, "type": etype, "parent_id": parent, "name": name, "attrs": attrs or {}})

    def fact(etype, eid, key, value):
        facts.append({"entity_type": etype, "entity_id": eid, "key": key, "value": value,
                      "valid_from": snapshot_date, "version": 1})

    tiers = []
    product_words = rng.sample(PRODUCT_WORDS, len(INSURERS) * PRODUCTS_PER_INSURER)
    for i, insurer in enumerate(INSURERS, start=1):
        iid = f"I{i}"
        entity(iid, "insurer", None, insurer)
        for key in KEYS:  # insurers set every default
            fact("insurer", iid, key, rng.choice(VALUES[key]))
        for p in range(1, PRODUCTS_PER_INSURER + 1):
            pid = f"{iid}-P{p}"
            pname = f"{insurer.split()[0]} {product_words[(i - 1) * PRODUCTS_PER_INSURER + p - 1]}"
            entity(pid, "product", iid, pname)
            for key in KEYS:
                if rng.random() < P_PRODUCT_OVERRIDE:
                    fact("product", pid, key, rng.choice(VALUES[key]))
            for t, tier in enumerate(TIERS, start=1):
                tid = f"{pid}-T{t}"
                entity(tid, "tier", pid, f"{pname} {tier}", {"tier": tier})
                tiers.append(tid)
                for key in KEYS:
                    if rng.random() < P_TIER_OVERRIDE:
                        fact("tier", tid, key, rng.choice(VALUES[key]))

    taken: set[str] = set()
    for n in range(1, N_POLICIES + 1):
        pol = f"POL{n:03d}"
        tid = rng.choice(tiers)
        while True:  # unique names: questions identify policies by name
            name = f"{rng.choice(NAME_WORDS)} {rng.choice(TRIP_WORDS)} Policy"
            if name not in taken:
                break
        taken.add(name)
        entity(pol, "policy", tid, name)
        for key in KEYS:
            if rng.random() < P_POLICY_OVERRIDE:
                fact("policy", pol, key, rng.choice(VALUES[key]))
        for o, opt in enumerate(OPTIONS, start=1):
            oid = f"{pol}-O{o}"
            entity(oid, "coverage_option", pol, None, {"option": opt})
            fact("coverage_option", oid, "excluded", rng.random() < P_EXCLUDED[opt])

    return {"tenant": TENANT, "seed": seed, "snapshot_date": snapshot_date,
            "entities": entities, "policy_facts": facts}


def _kg(data: dict) -> GenericKG:
    return GenericKG(tenant=data["tenant"], entities=data["entities"], policy_facts=data["policy_facts"],
                     seed=data.get("seed", 0), snapshot_date=data.get("snapshot_date", ""))


# ---------------------------------------------------------------- render

CLAIM_TEXT = [
    "Claims must be filed within {n} days of the incident date.",
    "A claim has to reach the claims team no later than {n} days after the incident.",
    "Customers have {n} days from the date of the incident to submit a claim.",
]
DEDUCTIBLE_TEXT = [
    "A deductible of EUR {n} applies to each claim.",
    "Each claim is subject to an excess (deductible) of EUR {n}.",
    "The customer pays the first EUR {n} of every claim themselves (deductible).",
]
WAITING_TEXT = [
    "Cover applies {n} days after the policy start date.",
    "There is a waiting period of {n} days from the policy start before cover begins.",
    "Incidents during the first {n} days after the policy starts are not covered (waiting period).",
]
TEXTS = {"claim_window_days": CLAIM_TEXT, "deductible_eur": DEDUCTIBLE_TEXT, "waiting_period_days": WAITING_TEXT}
DEFER_TEXT = [
    "The standard {tier} terms apply to this policy.",
    "This follows the {tier} plan's standard terms.",
]
OPTION_COVERED = [
    "**{label}** — covered on the policy's standard terms (coverage option {id}).",
    "**{label}** — included; the usual claim terms apply (coverage option {id}).",
]
OPTION_EXCLUDED = [
    "**{label}** — excluded on this policy: not covered at all (coverage option {id}).",
    "**{label}** — not covered. This option is excluded from the policy, so no claim under it "
    "is accepted (coverage option {id}).",
]
OVERVIEW = [
    "{name} is a {tier} policy issued by {insurer}, taken out for {trip}.",
    "Issued by {insurer} under the {tier} plan, {name} was arranged for {trip}.",
    "{name} belongs to the {tier} plan of {insurer} and covers {trip}.",
]
TRIPS = ["a two-week family holiday", "a city break", "a business trip", "a hiking trip",
         "a sailing holiday", "a visit to relatives abroad", "a study semester abroad", "a beach holiday"]


def _terms(pol: dict, ch: Chooser, keys=KEYS) -> list[tuple[str, str]]:
    return [(SECTION[k], ch.choice(k, TEXTS[k]).format(n=pol[k]["value"])) for k in keys]


def _upper_doc(kg: GenericKG, eid: str, ch: Chooser) -> str:
    e = kg.by_id[eid]
    ch.for_entity(f"{e['type']}-{eid}")
    pol = kg.resolve(eid)
    lineage = kg.lineage(eid)
    parents = " · ".join(f"{a['type'].capitalize()}: {a['name']}" for a in reversed(lineage[:-1]))
    children = ", ".join(c["name"] for c in kg.children(eid)) if e["type"] != "tier" else ""
    header = f"{e['type'].capitalize()} ID: {eid}"
    if parents:
        header += f" · {parents}"
    if children:
        header += f" · Includes: {children}"
    title = {"insurer": "standard claim terms", "product": "product terms", "tier": "plan terms"}[e["type"]]
    body = "\n\n".join(f"## {t}\n\n{text}" for t, text in _terms(pol, ch))
    return f"# {e['name']} — {title}\n\n{header}\n\n{body}\n"


def _policy_doc(kg: GenericKG, pid: str, ch: Chooser) -> tuple[str, dict]:
    ch.for_entity(pid)
    e = kg.by_id[pid]
    tier, product, insurer = (kg.by_id[x["id"]] for x in reversed(kg.lineage(pid)[:-1]))
    pol = kg.resolve(pid)
    overview = ch.choice("overview", OVERVIEW).format(
        name=e["name"], tier=tier["name"], insurer=insurer["name"], trip=ch.choice("trip", TRIPS))
    sections = [("Overview", overview)]
    defer = {}
    for key in KEYS:
        # Only inherited values may be deferred to the tier; an override is always stated.
        defer[key] = pol[key]["source_type"] != "policy" and ch.random(f"defer:{key}") < P_DEFER
        text = (ch.choice(f"defer_text:{key}", DEFER_TEXT).format(tier=tier["name"]) if defer[key]
                else ch.choice(key, TEXTS[key]).format(n=pol[key]["value"]))
        sections.append((SECTION[key], text))
    lines = []
    for o in kg.children(pid):
        excluded = kg.resolve(o["id"])["excluded"]["value"]
        tpl = ch.choice(f"opt:{o['id']}", OPTION_EXCLUDED if excluded else OPTION_COVERED)
        lines.append("- " + tpl.format(label=OPTION_LABEL[o["attrs"]["option"]], id=o["id"]))
    sections.append(("Coverage options", "\n".join(lines)))
    body = "\n\n".join(f"## {t}\n\n{text}" for t, text in sections)
    doc = (f"# {e['name']}\n\nPolicy ID: {pid} · Tier: {tier['name']} · Product: {product['name']} "
           f"· Insurer: {insurer['name']}\n\n{body}\n")
    return doc, {"defer": defer}


def render(data: dict, chooser: Chooser) -> tuple[dict[str, str], dict]:
    kg = _kg(data)
    docs, manifest = {}, {}
    for e in kg.entities:
        if e["type"] in ("insurer", "product", "tier"):
            docs[f"{e['type']}-{e['id']}"] = _upper_doc(kg, e["id"], chooser)
        elif e["type"] == "policy":
            docs[e["id"]], manifest[e["id"]] = _policy_doc(kg, e["id"], chooser)
    return docs, manifest


# ---------------------------------------------------------------- golden

DATE_BASE = date(2026, 11, 1)
UNANSWERABLE = [
    ("price", "What was the purchase price of the {name}?"),
    ("item_limit", "What is the maximum reimbursement for a single lost item under the {name}?"),
    ("hotline", "Which phone number should the customer call for emergency assistance under the {name}?"),
    ("age_limit", "Up to what age can someone be insured under the {name}?"),
    ("exchange_rate", "Which currency exchange rate is used to reimburse expenses paid abroad under the {name}?"),
]


def _date_patterns(d: date) -> list[str]:
    """Regexes for a date in the formats normalize.dates reads (ISO, '3 December 2026', 'December 3, 2026')."""
    mon = d.strftime("%B")
    return [d.isoformat(), rf"\b{d.day}(?:st|nd|rd|th)?\s+(?:of\s+)?{mon[:3]}\w*\.?,?\s+{d.year}",
            rf"\b{mon[:3]}\w*\.?\s+{d.day}(?:st|nd|rd|th)?,?\s+{d.year}"]


def golden(data: dict, manifest: dict, seed: int) -> list[dict]:
    rng = random.Random(f"{seed}-golden")
    kg = _kg(data)
    policies = [e for e in kg.entities if e["type"] == "policy"]
    pol = {p["id"]: kg.resolve(p["id"]) for p in policies}
    name = {p["id"]: p["name"] for p in policies}
    tier_of = {p["id"]: p["parent_id"] for p in policies}
    options = {p["id"]: {o["attrs"]["option"]: o for o in kg.children(p["id"])} for p in policies}
    excluded = {pid: {opt for opt, o in opts.items() if kg.resolve(o["id"])["excluded"]["value"]}
                for pid, opts in options.items()}

    def governing_doc(pid, key):
        return f"tier-{tier_of[pid]}" if manifest[pid]["defer"][key] else pid

    def evidence_docs(pid, key):
        return [pid] if not manifest[pid]["defer"][key] else [pid, f"tier-{tier_of[pid]}"]

    used: set[str] = set()

    def pick(cands):
        pid = rng.choice(sorted(set(cands) - used))
        used.add(pid)
        return pid

    def some_date():
        return DATE_BASE + timedelta(days=rng.randrange(90))

    def item(qtype, pid, question, expected, key, evidence_text, facts=None):
        return {"type": qtype, "subject_id": pid, "question": question, "expected": expected,
                "evidence_docs": evidence_docs(pid, key),
                "governing": {"docs": [governing_doc(pid, key)], "facts": facts or [f"kg:{pid}:{key}"]},
                "evidence_text": evidence_text}

    def claim_q(qtype, pid):
        covered = sorted(set(OPTIONS) - excluded[pid])
        opt = rng.choice(covered)
        d = some_date()
        n = pol[pid]["claim_window_days"]["value"]
        q = (f"A customer with the {name[pid]} wants to claim {OPTION_WORDS[opt]} costs. "
             f"The incident happened on {d.isoformat()}. By which date must the claim be filed?")
        return item(qtype, pid, q, {"kind": "date", "value": (d + timedelta(days=n)).isoformat()},
                    "claim_window_days", f"{n} days")

    def src(pid, key):
        return pol[pid][key]["source_type"]

    plain = [p for p in pol if not any(manifest[p]["defer"].values())]
    overridden = [p for p in pol if src(p, "claim_window_days") == "policy"
                  and kg.resolve(tier_of[p])["claim_window_days"]["value"] != pol[p]["claim_window_days"]["value"]]
    deferred = [p for p in pol if manifest[p]["defer"]["claim_window_days"]]
    with_excl = [p for p in pol if excluded[p]]
    has_covered = [p for p in pol if set(OPTIONS) - excluded[p]]

    qs: list[dict] = []
    # --- plain: the value is stated in the policy's own document.
    for _ in range(6):
        qs.append(claim_q("plain_claim_deadline", pick(set(plain) & set(has_covered))))
    for _ in range(3):
        pid = pick(plain)
        n = pol[pid]["deductible_eur"]["value"]
        qs.append(item("plain_deductible", pid, f"How much is the deductible per claim on the {name[pid]}?",
                       {"kind": "amount", "value": n}, "deductible_eur", f"EUR {n}"))
    for _ in range(3):
        pid = pick(plain)
        n = pol[pid]["waiting_period_days"]["value"]
        qs.append(item("plain_waiting_period", pid,
                       f"How long is the waiting period on the {name[pid]} before cover applies?",
                       {"kind": "duration", "value": {"value": n, "unit": "days"}},
                       "waiting_period_days", f"{n} days"))
    for _ in range(2):
        pid = pick(plain)
        d = some_date()
        n = pol[pid]["waiting_period_days"]["value"]
        qs.append(item("plain_cover_start", pid,
                       f"The {name[pid]} started on {d.isoformat()}. From which date does cover apply?",
                       {"kind": "date", "value": (d + timedelta(days=n)).isoformat()},
                       "waiting_period_days", f"{n} days"))

    # --- exceptions: variant override (excluded option), policy override, deferred terms.
    for _ in range(3):
        pid = pick(with_excl)
        opt = rng.choice(sorted(excluded[pid]))
        d = some_date()
        deadline = d + timedelta(days=pol[pid]["claim_window_days"]["value"])
        oid = options[pid][opt]["id"]
        qs.append({"type": "exception_excluded_option", "subject_id": pid,
                   "question": (f"A customer with the {name[pid]} wants to claim {OPTION_WORDS[opt]} costs. "
                                f"The incident happened on {d.isoformat()}. By which date must the claim be filed?"),
                   "expected": {"kind": "phrase",
                                "patterns": [r"not covered", r"\bexcluded\b", r"no cover(?:age)?\b",
                                             r"isn't covered", r"not included"],
                                # Giving the filing deadline that would apply without the exclusion.
                                "reject": _date_patterns(deadline)},
                   "evidence_docs": [pid], "governing": {"docs": [pid], "facts": [f"kg:{oid}:excluded"]},
                   "evidence_text": "excluded"})
    for _ in range(2):
        qs.append(claim_q("exception_policy_override", pick(set(overridden) & set(has_covered))))
    for _ in range(2):
        qs.append(claim_q("exception_by_reference", pick(set(deferred) & set(has_covered))))

    # --- unanswerable: the KG never holds these, and the corpus never mentions them.
    for topic, template in UNANSWERABLE:
        pid = pick(pol)
        qs.append({"type": f"unanswerable_{topic}", "question": template.format(name=name[pid]),
                   "expected": {"kind": "abstain"}, "evidence_docs": [],
                   "governing": {"docs": [], "facts": []}})

    return [{"id": f"Q{i:02d}", **q} for i, q in enumerate(qs, start=1)]
