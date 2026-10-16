"""Render one Markdown policy document per property, with varied wording.

Section order mostly follows a typical fact sheet (overview, check-in/out,
cancellation, pets, rate plans), so the cancellation rule and the
non-refundable exception usually sit in different sections, as in real
documents. That distance is what the M1 naive chunker trips over. Some docs
use a "booking terms first" layout with cancellation and rate plans adjacent
at the top (D13), so the split is common but not guaranteed.

Some property docs don't state their cancellation terms at all; they defer to
the brand's standard terms, and brand docs may in turn defer to the chain
(D14). Answering those needs 2-3 documents, or the KG.
"""

from __future__ import annotations

import random

from policyground.seed.kg import KG

FEE_TEXT = {
    "first_night": "the first night's rate",
    "full_stay": "the full cost of the stay",
    "50_percent": "50% of the total booking value",
}

OVERVIEW = [
    "{name} is a {adj} property in {city}, part of the {brand} brand of {chain}. "
    "Guests appreciate its {feature} and easy access to the city's main sights.",
    "Located in {city}, {name} belongs to {chain} and operates under the {brand} brand. "
    "The hotel is known for its {feature} and a {adj} atmosphere.",
    "Part of the {brand} portfolio of {chain}, {name} offers a {adj} stay in {city}, "
    "with a particular focus on its {feature}.",
]
ADJECTIVES = ["modern", "family-friendly", "quiet", "business-oriented", "boutique", "recently renovated"]
FEATURES = ["rooftop terrace", "24-hour front desk", "on-site restaurant", "fitness room",
            "meeting facilities", "courtyard garden", "bicycle rental", "spa area"]
AMENITIES = [
    "Free Wi-Fi is available throughout the building.",
    "Luggage storage is offered at the front desk.",
    "Housekeeping is provided daily.",
    "Accessible rooms are available on request.",
    "Reception staff speak English and the local language.",
    "Daily newspapers are available in the lobby.",
]

CHECKIN = [
    "Check-in starts at {check_in}. Check-out is until {check_out}.",
    "Guests may check in from {check_in} and are asked to check out by {check_out}.",
    "Rooms are available from {check_in} on the day of arrival; please vacate by {check_out} on departure.",
]
CANCEL = [
    "Reservations can be cancelled free of charge up to {hours} hours before the scheduled check-in. "
    "Later cancellations and no-shows are charged {fee}.",
    "Free cancellation is possible until {hours} hours prior to arrival. "
    "If you cancel after that point, or do not arrive, {fee} will be charged.",
    "Guests who cancel at least {hours} hours before check-in pay nothing. "
    "Cancellations within {hours} hours of arrival incur a charge of {fee}.",
]
PETS_YES = [
    "Pets are welcome for a fee of EUR {fee} per night.",
    "Dogs and cats are allowed; a charge of EUR {fee} per night applies.",
    "This property is pet-friendly. A pet supplement of EUR {fee} per night is added to the bill.",
]
PETS_NO = [
    "Pets are not allowed, with the exception of assistance animals.",
    "Unfortunately, pets cannot be accommodated. Assistance animals are welcome.",
]
PLAN_TEXT = {
    "flexible": [
        "**Flexible Rate** — the standard cancellation policy applies.",
        "**Flexible Rate** — cancellable under the property's usual terms.",
    ],
    "breakfast_included": [
        "**Breakfast Included** — breakfast for all guests; the standard cancellation policy applies.",
        "**Bed & Breakfast** — includes daily breakfast; usual cancellation terms apply.",
    ],
    "non_refundable": [
        "**Non-Refundable Rate** — paid in full at booking. This rate cannot be cancelled or "
        "changed, and no refund is given regardless of when you cancel.",
        "**Saver Rate (non-refundable)** — the full amount is charged at booking and is not "
        "refunded on cancellation, at any time. The standard cancellation window does not apply.",
    ],
}


# Share of property docs using the "booking terms first" layout (D13).
P_BOOKING_FIRST = 0.3
# Share of eligible property docs that defer cancellation terms to the brand (D14).
P_CANCEL_BY_REFERENCE = 0.4

CANCEL_BY_REFERENCE = [
    "The standard {brand} cancellation terms apply to this property.",
    "Cancellation follows the {brand} brand standard policy.",
]
BRAND_FOLLOWS_CHAIN = [
    "{brand} hotels follow the {chain} group cancellation policy.",
    "Cancellation terms for {brand} are the standard {chain} terms.",
]


def cancel_text(pol: dict, rng: random.Random) -> str:
    return rng.choice(CANCEL).format(hours=pol["cancel_window_hours"]["value"],
                                     fee=FEE_TEXT[pol["late_cancel_fee"]["value"]])


def render_chain(kg: KG, chain_id: str, rng: random.Random) -> str:
    chain = kg._by_id("chains", chain_id)
    pol = kg.resolve("chain", chain_id)
    brands = ", ".join(b["name"] for b in kg.brands if b["chain_id"] == chain_id)
    return f"""# {chain['name']} — group policy

Chain ID: {chain_id} · Brands: {brands}

## Cancellation

{cancel_text(pol, rng)}
"""


def render_brand(kg: KG, brand_id: str, rng: random.Random) -> str:
    brand = kg._by_id("brands", brand_id)
    chain = kg._by_id("chains", brand["chain_id"])
    pol = kg.resolve("brand", brand_id)
    if pol["cancel_window_hours"]["source_type"] == "chain":
        body = rng.choice(BRAND_FOLLOWS_CHAIN).format(brand=brand["name"], chain=chain["name"])
    else:
        body = cancel_text(pol, rng)
    return f"""# {brand['name']} — brand policy

Brand ID: {brand_id} · Chain: {chain['name']}

## Cancellation

{body}
"""


def render_property(kg: KG, property_id: str, rng: random.Random) -> tuple[str, dict]:
    """Return (markdown, manifest entry). The manifest records how the doc was
    rendered so the eval can break results down by question difficulty."""
    prop = kg._by_id("properties", property_id)
    brand = kg._by_id("brands", prop["brand_id"])
    chain = kg._by_id("chains", brand["chain_id"])
    resolved = kg.resolve("property", property_id)
    pol = {k: v["value"] for k, v in resolved.items()}

    fmt = {"name": prop["name"], "city": prop["city"], "brand": brand["name"],
           "chain": chain["name"], "adj": rng.choice(ADJECTIVES), "feature": rng.choice(FEATURES)}
    overview = rng.choice(OVERVIEW).format(**fmt) + " " + " ".join(rng.sample(AMENITIES, 3))

    pets = (rng.choice(PETS_YES).format(fee=pol["pet_fee_eur"]) if pol["pets_allowed"]
            else rng.choice(PETS_NO))

    # Only inherited terms can be deferred; a property-level override must be stated.
    cancel_by_reference = (resolved["cancel_window_hours"]["source_type"] != "property"
                           and rng.random() < P_CANCEL_BY_REFERENCE)
    cancellation = (rng.choice(CANCEL_BY_REFERENCE).format(brand=brand["name"])
                    if cancel_by_reference else cancel_text(resolved, rng))

    plans = [p for p in kg.rate_plans if p["property_id"] == property_id]
    plan_lines = "\n".join(f"- {rng.choice(PLAN_TEXT[p['kind']])} (rate plan {p['id']})" for p in plans)

    overview_section = ("Overview", overview)
    checkin = ("Check-in and check-out",
               rng.choice(CHECKIN).format(check_in=pol["check_in_time"], check_out=pol["check_out_time"]))
    cancel = ("Cancellation", cancellation)
    pets_section = ("Pets", pets)
    plans_section = ("Rate plans", plan_lines)

    booking_first = rng.random() < P_BOOKING_FIRST
    sections = ([cancel, plans_section, checkin, pets_section, overview_section] if booking_first
                else [overview_section, checkin, cancel, pets_section, plans_section])

    body = "\n\n".join(f"## {title}\n\n{text}" for title, text in sections)
    doc = f"""# {prop['name']}

Property ID: {property_id} · Brand: {brand['name']} · Chain: {chain['name']}

{body}
"""
    manifest = {"cancel_by_reference": cancel_by_reference, "booking_first": booking_first}
    return doc, manifest
