"""Render one Markdown policy document per property, with varied wording.

Section order follows a typical hotel fact sheet: overview, check-in/out,
cancellation, pets, rate plans. The cancellation rule and the non-refundable
exception therefore live in different sections, as they do in real documents.
That distance is what the M1 naive chunker trips over.
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
        "refunded on cancellation, at any time. The cancellation window above does not apply.",
    ],
}


def render_property(kg: KG, property_id: str, rng: random.Random) -> str:
    prop = kg._by_id("properties", property_id)
    brand = kg._by_id("brands", prop["brand_id"])
    chain = kg._by_id("chains", brand["chain_id"])
    pol = {k: v["value"] for k, v in kg.resolve("property", property_id).items()}

    fmt = {"name": prop["name"], "city": prop["city"], "brand": brand["name"],
           "chain": chain["name"], "adj": rng.choice(ADJECTIVES), "feature": rng.choice(FEATURES)}
    overview = rng.choice(OVERVIEW).format(**fmt) + " " + " ".join(rng.sample(AMENITIES, 3))

    pets = (rng.choice(PETS_YES).format(fee=pol["pet_fee_eur"]) if pol["pets_allowed"]
            else rng.choice(PETS_NO))

    plans = [p for p in kg.rate_plans if p["property_id"] == property_id]
    plan_lines = "\n".join(f"- {rng.choice(PLAN_TEXT[p['kind']])} (rate plan {p['id']})" for p in plans)

    return f"""# {prop['name']}

Property ID: {property_id} · Brand: {brand['name']} · Chain: {chain['name']}

## Overview

{overview}

## Check-in and check-out

{rng.choice(CHECKIN).format(check_in=pol['check_in_time'], check_out=pol['check_out_time'])}

## Cancellation

{rng.choice(CANCEL).format(hours=pol['cancel_window_hours'], fee=FEE_TEXT[pol['late_cancel_fee']])}

## Pets

{pets}

## Rate plans

{plan_lines}
"""
