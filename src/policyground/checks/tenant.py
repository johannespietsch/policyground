"""`python -m policyground.checks.tenant <name>` (make check-tenant TENANT=<name>): the
MANDATORY done-check for onboarding a tenant (.claude/skills/onboard-tenant/SKILL.md, D45).

Runs every step end to end and exits non-zero at the first failure. Onboarding is done
only when this prints DONE-CHECK PASSED, never on the agent's own judgement.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from policyground import tenant as tenants
from policyground.kgmodel import GenericKG

MIN_QUESTIONS, MIN_UNANSWERABLE = 10, 2
# Tenants whose data is a measured record (M1-M5): never re-seeded by the check, because
# seeding regenerates the world and would wipe mutation history and render choices.
PROTECTED = {"hotels"}
MIN_CORRECT, MIN_ABSTAIN = 0.8, 0.8
GOLDEN_KINDS = {"datetime", "date", "time", "amount", "eur", "duration", "phrase", "abstain",
                "no_free_cancellation", "fee", "no_charge"}


class Failed(Exception):
    pass


def step(n: int, title: str) -> None:
    CURRENT["step"] = f"{n}: {title}"
    print(f"\n[{n}] {title}", flush=True)


def run(cmd: list[str]) -> str:
    print("    $ " + " ".join(cmd), flush=True)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-25:])
        raise Failed(f"command failed (exit {p.returncode}): {' '.join(cmd)}\n{tail}")
    return p.stdout


def check_golden(name: str, golden: list[dict]) -> None:
    from policyground.eval.retrieval import needle, subject_of

    data = json.loads((Path("data") / name / "kg.json").read_text())
    if len(golden) < MIN_QUESTIONS:
        raise Failed(f"golden set has {len(golden)} questions, need >= {MIN_QUESTIONS}")
    n_abst = sum(q["expected"]["kind"] == "abstain" for q in golden)
    if n_abst < MIN_UNANSWERABLE:
        raise Failed(f"golden set has {n_abst} unanswerable questions, need >= {MIN_UNANSWERABLE}")
    latest = max((Path("corpus") / name).iterdir())
    for q in golden:
        for key in ("id", "type", "question", "expected", "evidence_docs", "governing"):
            if key not in q:
                raise Failed(f"{q.get('id', '?')}: missing field '{key}'")
        kind = q["expected"].get("kind")
        if kind not in GOLDEN_KINDS:
            raise Failed(f"{q['id']}: expected.kind {kind!r} not one of {sorted(GOLDEN_KINDS)}")
        if kind == "abstain":
            continue
        if not subject_of(q):
            raise Failed(f"{q['id']}: answerable question needs subject_id")
        needed = needle(q, data, name)
        if not needed:
            raise Failed(f"{q['id']}: answerable question needs evidence_text (text the governing doc must contain)")
        text = "\n".join((latest / f"{d}.md").read_text() for d in q["governing"]["docs"])
        if needed.lower() not in text.lower():
            raise Failed(f"{q['id']}: evidence_text {needed!r} not found in governing docs "
                         f"{q['governing']['docs']} of snapshot {latest.name}")
    print(f"    {len(golden)} questions ({n_abst} unanswerable); every evidence_text found in its governing doc")


def reset_tenant_rows(name: str) -> None:
    """A re-seeded tenant may have different generated values. The version guard (D34)
    would keep the old version-1 facts, so the DB would silently disagree with kg.json.
    Non-protected tenants are therefore cleared before every load (eval history stays)."""
    from policyground.db import connect

    if name in PROTECTED:
        return
    with connect("ingest_rw") as conn:
        for table in ("chunks", "policy_fact", "entity"):
            n = conn.execute(f"DELETE FROM {table} WHERE tenant = %s", (name,)).rowcount
            if n:
                print(f"    cleared {n} old {table} rows for '{name}'")


def check_resolver(name: str) -> None:
    from policyground.db import connect

    kg = GenericKG.load(Path("data") / name / "kg.json")
    spec = tenants.spec(name)
    targets = [e["id"] for e in kg.entities if e["type"] in (spec.subject, spec.variant)]
    bad = []
    with connect("api_ro") as conn:
        for eid in targets:
            sql = {k: {"value": v, "source_type": st, "source_id": sid}
                   for k, v, sid, st, _ in conn.execute("SELECT * FROM resolve_policy(%s, %s)", (name, eid))}
            if sql != kg.resolve(eid):
                bad.append(eid)
    if bad:
        raise Failed(f"SQL resolver disagrees with kg.json for {len(bad)} entities, e.g. {bad[:5]}")
    print(f"    SQL resolve_policy == Python resolver for all {len(targets)} subjects/variants")


def record_attempt(name: str, passed: bool, failed_step: str | None, error: str | None) -> int:
    """Every run of the done-check is one onboarding attempt (METRICS: skill attempts). The
    check counts them itself, so the number doesn't depend on the agent reporting it."""
    from datetime import datetime, timezone

    path = Path("data") / name / "onboarding-attempts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "passed": passed,
                            "failed_step": failed_step, "error": (error or "")[:500]}) + "\n")
    return sum(1 for _ in open(path))


CURRENT = {"step": None}


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        step(1, f"spec: src/policyground/tenants/{name}/spec.yaml")
        s = tenants.spec(name)
        tenants.adapter(name)
        print(f"    levels {list(s.levels)}, subject {s.subject}, {len(s.facts)} facts, "
              f"{len(s.deadlines)} deadline rule(s)")

        step(2, "seed: kg.json, corpus snapshot, golden set (via the adapter)")
        if name in PROTECTED:
            print(f"    '{name}' is a protected record: not re-seeded, checking its existing data")
        else:
            run(["uv", "run", "python", "-m", "policyground.seed", "--tenant", name])
        check_golden(name, json.loads((Path("data") / name / "golden.json").read_text()))

        step(3, "load the KG (levels and fact keys validated against the spec)")
        reset_tenant_rows(name)
        run(["uv", "run", "python", "-m", "policyground.kg", "--tenant", name])

        step(4, "SQL resolver vs Python resolver")
        check_resolver(name)

        step(5, "ingest the latest snapshot (production chunker x embedder)")
        latest = max((Path("corpus") / name).iterdir()).name
        run(["uv", "run", "python", "-m", "policyground.ingest", "--tenant", name, "--date", latest])

        step(6, "test suite")
        run(["uv", "run", "pytest", "-q"])
        print("    all tests pass")

        step(7, f"LLM eval through the kg graph (correct >= {MIN_CORRECT}, abstention >= {MIN_ABSTAIN})")
        out = run(["uv", "run", "python", "-m", "policyground.eval", "--tenant", name, "--graph", "kg"])
        summary = json.loads(next(l for l in reversed(out.splitlines()) if l.startswith("SUMMARY "))[8:])
        print(f"    correct {summary['correct']:.2f}, abstention {summary['abst_acc']:.2f} "
              f"over {summary['n']} questions (run {summary['run']})")
        if summary["correct"] < MIN_CORRECT or summary["abst_acc"] < MIN_ABSTAIN:
            raise Failed(f"eval below threshold: correct {summary['correct']:.2f}, abstention {summary['abst_acc']:.2f}")
    except Exception as e:  # any failure is a failed attempt, recorded, with the step it happened in
        n = record_attempt(name, False, CURRENT["step"], f"{type(e).__name__}: {e}") if name else 0
        print(f"\nDONE-CHECK FAILED (attempt {n}) at step {CURRENT['step']}: {type(e).__name__}: {e}", flush=True)
        sys.exit(1)
    n = record_attempt(name, True, None, None)
    print(f"\nDONE-CHECK PASSED for tenant '{name}' (attempt {n})", flush=True)


if __name__ == "__main__":
    main()
