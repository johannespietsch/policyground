"""D41: no metric may carry a high-cardinality label (the PLAN M5 trap)."""

from prometheus_client import REGISTRY

from policyground.obs import metrics


def test_only_allowed_labels():
    ours = [c for c in REGISTRY._collector_to_names if getattr(c, "_name", "").startswith("policyground_")]
    assert ours, "no policyground metrics registered"
    for c in ours:
        bad = set(c._labelnames) - metrics.ALLOWED_LABELS
        assert not bad, f"{c._name} has disallowed labels {bad}"
