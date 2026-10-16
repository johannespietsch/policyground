"""Seeded synthetic KG generator (D2).

Same seed -> byte-identical kg.json. All names are fictional.
"""

from __future__ import annotations

import random

from policyground.seed.kg import KG, PolicyFact

N_CHAINS = 5
BRANDS_PER_CHAIN = (2, 3)
N_PROPERTIES = 150

# Override probabilities per level. Brand and property overrides are what make
# questions "exception" questions; non-refundable rate plans are the other kind.
P_BRAND_OVERRIDE = 0.5
P_PROPERTY_OVERRIDE = 0.3
P_NON_REFUNDABLE = 0.4
P_BREAKFAST = 0.6

CHAIN_WORDS = ["Aurelia", "Northwind", "Solstice", "Harbor & Pine", "Meridian", "Lumen", "Calder"]
BRAND_WORDS = ["Suites", "Urban", "Resorts", "Express", "Collection", "Lodge", "Signature"]
PROPERTY_WORDS = ["Garden", "Riverside", "Central", "Old Town", "Airport", "Harbour", "Park", "Station"]
CITIES = ["Lisbon", "Porto", "Seville", "Valencia", "Lyon", "Bordeaux", "Munich", "Hamburg",
          "Vienna", "Prague", "Krakow", "Milan", "Florence", "Amsterdam", "Copenhagen"]

CANCEL_WINDOWS = [24, 48, 72]
LATE_CANCEL_FEES = ["first_night", "full_stay", "50_percent"]
CHECK_IN_TIMES = ["14:00", "15:00", "16:00"]
CHECK_OUT_TIMES = ["10:00", "11:00", "12:00"]
PET_FEES_EUR = [15, 20, 25, 30, 40]


def generate(seed: int = 42, tenant: str = "hotels", snapshot_date: str = "2026-10-16") -> KG:
    rng = random.Random(seed)
    kg = KG(tenant=tenant, seed=seed, snapshot_date=snapshot_date)

    def fact(entity_type: str, entity_id: str, key: str, value) -> None:
        kg.policy_facts.append(PolicyFact(entity_type, entity_id, key, value, snapshot_date))

    for c in range(1, N_CHAINS + 1):
        chain_id = f"C{c}"
        chain_name = CHAIN_WORDS[c - 1] + " Hotels"
        kg.chains.append({"id": chain_id, "name": chain_name})
        # Chains set every default.
        fact("chain", chain_id, "cancel_window_hours", rng.choice(CANCEL_WINDOWS))
        fact("chain", chain_id, "late_cancel_fee", rng.choice(LATE_CANCEL_FEES))
        fact("chain", chain_id, "check_in_time", rng.choice(CHECK_IN_TIMES))
        fact("chain", chain_id, "check_out_time", rng.choice(CHECK_OUT_TIMES))
        fact("chain", chain_id, "pets_allowed", rng.random() < 0.6)
        fact("chain", chain_id, "pet_fee_eur", rng.choice(PET_FEES_EUR))

        for b, word in enumerate(rng.sample(BRAND_WORDS, rng.randint(*BRANDS_PER_CHAIN)), start=1):
            brand_id = f"{chain_id}-B{b}"
            kg.brands.append({"id": brand_id, "chain_id": chain_id,
                              "name": f"{CHAIN_WORDS[c - 1]} {word}"})
            if rng.random() < P_BRAND_OVERRIDE:
                fact("brand", brand_id, "cancel_window_hours", rng.choice(CANCEL_WINDOWS))
            if rng.random() < P_BRAND_OVERRIDE / 2:
                fact("brand", brand_id, "pets_allowed", rng.random() < 0.5)

    for p in range(1, N_PROPERTIES + 1):
        prop_id = f"P{p:03d}"
        brand = rng.choice(kg.brands)
        city = rng.choice(CITIES)
        kg.properties.append({
            "id": prop_id, "brand_id": brand["id"], "city": city,
            "name": f"{brand['name']} {city} {rng.choice(PROPERTY_WORDS)}",
        })
        if rng.random() < P_PROPERTY_OVERRIDE:
            # May coincide with the chain value after a brand override: an
            # "override of an override" that lands back on the original.
            fact("property", prop_id, "cancel_window_hours", rng.choice(CANCEL_WINDOWS))
        if rng.random() < P_PROPERTY_OVERRIDE / 2:
            fact("property", prop_id, "pet_fee_eur", rng.choice(PET_FEES_EUR))
        if rng.random() < P_PROPERTY_OVERRIDE / 2:
            fact("property", prop_id, "check_out_time", rng.choice(CHECK_OUT_TIMES))

        # Every property has a flexible plan; the others are optional.
        kinds = ["flexible"]
        if rng.random() < P_BREAKFAST:
            kinds.append("breakfast_included")
        if rng.random() < P_NON_REFUNDABLE:
            kinds.append("non_refundable")
        for r, kind in enumerate(kinds, start=1):
            plan_id = f"{prop_id}-R{r}"
            kg.rate_plans.append({"id": plan_id, "property_id": prop_id, "kind": kind})
            fact("rate_plan", plan_id, "refundable", kind != "non_refundable")
            fact("rate_plan", plan_id, "breakfast_included", kind == "breakfast_included")

    return kg
