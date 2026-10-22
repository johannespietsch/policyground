# Incidents

Format: Symptom / Hypothesis / Actual cause / Fix / Prevention at scale / Time lost.
Recorded when found, never backfilled. Planned traps are labelled as planned.

---

## #1 Retrieval returns the wrong property (M1, 2026-10-18)

**Found in:** the first eval run, `run-20261018-113345` (correct 0.76, hit@5 0.72).

**Symptom:** 7 of 25 answerable questions failed. In all 7, none of the question's
evidence docs were in the top-5 chunks. For Q01 ("Aurelia Suites Hamburg Park"), search
returned P094, P025, P002, P130 and P023: other Hamburg or Aurelia properties, but not
P046. Every one of the 7 was a correct abstention ("the excerpts don't cover this
property"). None was a confident wrong answer.

**Hypothesis (from the plan):** The naive 800-char chunker splits the cancellation rule
from the non-refundable exception, so exception questions fail confidently.

**Actual cause:** Retrieval fails before chunking matters. Policy paragraphs are
near-identical across 150 properties, so for bge-small the hotel name contributes almost
nothing to the embedding, and nearest neighbours are whatever property has the most
similar wording. Both non-refundable questions (Q21, Q22) missed their property doc
entirely, so **the planned chunk-boundary trap was never exercised**. The model never
saw the doc that would have split.

**Fix:** None in M1, on purpose: this is the baseline. M2's `route → kg_lookup` resolves
the property by name/ID in the KG before any retrieval. Retrieval then only supplies
explanation and citations, and can be filtered to the resolved property's docs.

**Prevention at scale:** Never rely on embedding similarity to identify *which entity*
a question is about when the corpus holds many near-duplicate entities. Resolve the
entity deterministically first (KG, ID or metadata filter), then retrieve within it.
Measure hit@5 per question type from day one; it separates "the model failed" from
"the model was never shown the answer".

**Time lost:** about 20 min to diagnose (two spot checks, then the eval breakdown).
Planned M1 work, not lost.

**Note for the M2 before/after:** The chunk-boundary trap needs a retrieval that
reaches the right doc. Measure it after the KG route fixes entity resolution, on the
non-refundable questions where the split happens (78% of NR docs, D13).

---

## #2 Correct for the wrong reason: Q24 (M1, 2026-10-18)

**Symptom:** Q24 (`exception_by_reference_2hop`, property P042) scored **correct**,
but hit@5 was false: the brand doc `brand-C5-B1` that the property defers to was not
retrieved.

**Actual cause:** P042's doc says "Cancellation follows the Meridian Urban brand
standard policy". The model got `chain-C5` instead and applied the chain terms (72h).
The Meridian Urban brand "override" is also 72h, the no-op override case accepted in
the D13/D14 review, so the unsupported inference landed on the right number. The
answer cites `chain-C5#0`, which isn't the governing document.

**Why it matters:** Value-only scoring can't tell a supported answer from a lucky one.
An eval that counts this as correct overstates how well the system reasons through
by-reference docs.

**Fix:** Not yet; needs a decision. Options: exclude no-op overrides when picking
exception questions, or add a "citation supports answer" check (the M2 validator
already needs one).

**Prevention at scale:** Score evidence as well as values. A correct value with
non-governing citations should count as a separate outcome, not as correct.

**Time lost:** about 5 min.

---

## #3 Validator passes a wrong deadline that equals another backed value (M2, 2026-10-19)

**Found by:** fault injection on run `20261019-171800`. 110/111 faults were caught; this
is the one that wasn't.

**Symptom:** Q33 (24h window, check-in 2026-11-25 at 16:00). The deadline was changed
from "2026-11-24 at 16:00" to "2026-11-25 at 16:00", i.e. the check-in moment itself,
and the validator still passed it.

**Hypothesis:** A bug in the date-shift injection.

**Actual cause:** A design limitation. The validator checks each value against a
*set* of backed values: question dates, derived deadline dates, dates in cited chunks.
The check-in date is in the question, so it's "backed". The validator never checks the
*claim*: that this particular date and time is the free-cancellation deadline. Any
wrong deadline that happens to equal some other legitimate value passes. That's most
likely with 24h windows, where deadline + 1 day is the check-in date.

**Fix (2026-10-22):** A claim-level check. Each deadline phrase ("until / by / no later
than <date> <time>", cut at "before / prior / hours / …" so the restated arrival isn't
read as the claim) must equal a deadline computed from the cited window and check-in
time. Value-level checks stay for everything else. Fault injection re-run on the same
answers: 111/111 caught, 0/29 false positives.

**Prevention at scale:** Value-set validation is necessary but not sufficient.
Validate the relation an answer asserts (this value *is* the deadline), not just that
each value appears somewhere in the evidence. Injected-fault testing is what surfaces
this. Real traffic would only show it as a rare wrong answer.

**Time lost:** about 10 min.
