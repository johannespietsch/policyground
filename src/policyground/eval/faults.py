"""`python -m policyground.eval.faults` — validator catch rate on injected faults (D23).

Takes the correct, non-abstained answers from the latest kg eval run, applies one
fault at a time, and re-runs the validator offline (no API calls). A fault only
applies where the answer has something to break (e.g. no EUR amount -> no amount
fault), so each type reports its own n.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from datetime import date, timedelta
from pathlib import Path

from policyground.validate import validate

ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
HHMM = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")
HOURS = re.compile(r"\b(\d{1,3})(\s*(?:-\s*)?hours?)\b", re.I)
EUR = re.compile(r"(EUR\s*|€\s*)(\d+)", re.I)


def _shift_date(text, question):
    q_dates = set(ISO.findall(question))
    for m in ISO.finditer(text):
        if m.groups() not in q_dates:  # break the answer's own date, not the restated check-in
            d = date(*map(int, m.groups())) + timedelta(days=1)
            return text[:m.start()] + d.isoformat() + text[m.end():]
    return None


def _shift_time(text, _):
    m = HHMM.search(text)
    if not m:
        return None
    h = (int(m[1]) + 1) % 24
    return text[:m.start()] + f"{h:02d}:{m[2]}" + text[m.end():]


def _change_window(text, _):
    m = HOURS.search(text)
    if not m:
        return None
    return text[:m.start()] + str(int(m[1]) + 24) + m[2] + text[m.end():]


def _change_amount(text, _):
    m = EUR.search(text)
    if not m:
        return None
    return text[:m.start()] + m[1] + str(int(m[2]) + 5) + text[m.end():]


TEXT_FAULTS = {"date+1d": _shift_date, "time+1h": _shift_time,
               "window+24h": _change_window, "amount+5": _change_amount}
CITATION_FAULTS = {
    "no citations": lambda cites: [],
    "invented citation": lambda cites: cites + ["P999#0"],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--run", help="eval run file (default: latest kg run)")
    args = ap.parse_args()

    runs = [args.run] if args.run else sorted(glob.glob(f"data/{args.tenant}/eval/run-*.json"))
    run = next(r for r in (json.loads(Path(p).read_text()) for p in reversed(runs)) if r.get("graph") == "kg")
    base = [r for r in run["results"] if r["correct"] and not r["abstain"] and r["attempts"]]

    def check(r, answer, cites):
        return validate(r["question"], answer, False, cites, r["facts"], r["chunk_texts"]).ok

    false_pos = sum(not check(r, r["answer"], r["raw_citations"]) for r in base)
    rows = {}
    for name, fault in TEXT_FAULTS.items():
        applied = [(r, broken) for r in base if (broken := fault(r["answer"], r["question"]))]
        rows[name] = (sum(not check(r, b, r["raw_citations"]) for r, b in applied), len(applied))
    for name, fault in CITATION_FAULTS.items():
        rows[name] = (sum(not check(r, r["answer"], fault(r["raw_citations"])) for r in base), len(base))

    caught = sum(c for c, _ in rows.values())
    total = sum(n for _, n in rows.values())
    print(f"source run {run['run']}: {len(base)} correct non-abstained answers")
    print(f"false positives on unmodified answers: {false_pos}/{len(base)}")
    for name, (c, n) in rows.items():
        print(f"  {name:18s} caught {c}/{n}")
    print(f"overall catch rate: {caught}/{total} = {caught / total:.2f}")

    metrics = Path("METRICS.md")
    text = metrics.read_text()
    header = "## Validator fault injection"
    cols = list(rows)
    if header not in text:
        text += (f"\n{header}\n\nWritten by `python -m policyground.eval.faults`: injected faults on the "
                 "correct answers of one kg eval run, validated offline. Cells are caught/applied.\n\n"
                 f"| source run | answers | false pos | {' | '.join(cols)} | overall |\n"
                 f"|{'---|' * (len(cols) + 4)}\n")
    text += (f"| {run['run']} | {len(base)} | {false_pos}/{len(base)} | "
             + " | ".join(f"{c}/{n}" for c, n in rows.values())
             + f" | {caught / total:.2f} |\n")
    metrics.write_text(text)


if __name__ == "__main__":
    main()
