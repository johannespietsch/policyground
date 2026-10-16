from policyground.seed.generate import generate


def test_same_seed_is_byte_identical():
    assert generate(seed=7).to_json() == generate(seed=7).to_json()


def test_most_specific_level_wins():
    kg = generate()
    for f in kg.policy_facts:
        if f.entity_type == "property" and f.key == "cancel_window_hours":
            resolved = kg.resolve("property", f.entity_id)["cancel_window_hours"]
            assert resolved == {"value": f.value, "source_type": "property", "source_id": f.entity_id}
            return
    raise AssertionError("seed produced no property-level override")


def test_rate_plan_inherits_from_chain():
    kg = generate()
    plan = kg.rate_plans[0]
    resolved = kg.resolve("rate_plan", plan["id"])
    assert {"cancel_window_hours", "check_in_time", "refundable"} <= resolved.keys()
    assert resolved["refundable"]["source_type"] == "rate_plan"
