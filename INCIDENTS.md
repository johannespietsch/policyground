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

---

## #4 Wrong governing evidence for deferring properties in hard questions (M2, 2026-10-22)

**Symptom:** In the first retrieval comparison, "fact@5 filtered" was exactly 0.92 for
all four chunker × embedder combinations. A metric that doesn't move at all when both
the chunker and the embedder change is suspicious.

**Hypothesis:** Filtered retrieval is easy enough to saturate.

**Actual cause:** A measurement bug in the golden set. `add_governing` used the
property doc as governing evidence unless the question *type* was by-reference. Three
of the new hard questions (Q39, Q41, Q42) were about properties whose docs only say
"standard {brand} terms apply". Their fact text lives in the brand doc, so no
retrieval could ever "hit" them. The same bug left those questions' `evidence_docs`
without the brand doc.

**Fix:** The governing doc is now derived from the render manifest for every
cancellation-related question (`stating_doc`), and evidence paths are extended to it.
A new test asserts that every answerable question's fact text appears in its governing
doc. Q01–Q35 were unchanged, verified byte-for-byte. The four affected rows in METRICS
are kept and marked superseded, and the comparison was re-run.

**Prevention at scale:** Test the eval's own ground truth (the evidence must contain
the answer), not just the system under test. A metric that is flat across
configurations that should differ is a signal to inspect the measurement first.

**Impact on earlier results:** The eval table's headline (Q01–Q30) and `unsupported`
are unaffected. The `hard` column only checks values, so it's unaffected too.

**Time lost:** about 15 min.

---

## #5 Fixing a validator false positive opened a false negative (M2, 2026-10-22)

**Symptom:** The validator rejected Q43's correct answer ("nothing is charged", "EUR 0",
"96 hours before"). That cost a regenerate. After the fix (allow EUR 0 with a
no-charge phrase, and allow hour gaps derived from the question's timestamps), fault
injection dropped from 111/111 to 148/150.

**Actual cause:** The derived-gap allowance applied to *every* hours mention. In Q42
the guest cancels exactly 72h before arrival, so a wrong window ("free cancellation
runs until **72** hours before", true value 48) matched the derived gap and passed.
It's the same class as #3: a value-set check accepts a wrong claim that coincides with
some other legitimate number.

**Fix:** Hours stated *as the window* ("until / up to / at least N hours", "N-hour
window") must match a cited window. Other hour mentions may also be derived gaps.
Result: 149/150 caught, 0/37 false positives. The one remaining "miss" is Q43's
mutation, "cancelling more than **96** hours before … is free", which is still a
**true** statement for a 72h window. It's counted as uncaught but isn't a validator
error.

**Prevention at scale:** Every validator relaxation is a potential false negative.
Re-run the fault-injection suite after each change, as here. It's what caught the
regression within minutes.

**Time lost:** about 10 min.

---

## #6 Retry-cost trap (INDUCED), and LangGraph's real recursion limit (M2, 2026-10-22)

**Planned trap (PLAN M2):** An uncapped regenerate-on-reject loop blows up cost per
question.

**Not reproduced on real data:** Of the 4 rejections in run `20261022-200858`, every one
recovered on the first regenerate. On this data an uncapped loop would have cost
nothing extra.

**Induced demonstration** (`python -m policyground.eval.retry_demo`): The validator was
replaced with one that always rejects (a persistent false positive), on Q01.
- Cap = 1: 2 LLM calls, $0.00092, then a validator-forced abstention.
- Cap removed, bounded at 60 steps for the demo: 29 calls, $0.01468, **16×** and
  rising linearly (about 2.4k input + 0.5k output tokens per call, about 2.7s each).

**The real finding: my assumed backstop didn't exist.** I expected LangGraph's
recursion limit (25 in older versions) to stop the loop. In the installed LangGraph
1.2.16, `DEFAULT_RECURSION_LIMIT` is **10007**. An unbounded run was observed passing
38 LLM calls in 115s before I killed it. Projected to the default limit, that's about
5,000 calls, **about $2.53 and over 3 hours for one question**. Only the
application-level cap stood between a validator bug and that bill.

**A second finding on the way:** The first demo attempts appeared to hang. A
`faulthandler` stack dump showed the process blocked inside `messages.parse`, waiting
for response headers. The Anthropic SDK's default timeout is 10 minutes, retried twice,
so one stalled request can block a caller for about 30 minutes. (A Docker Desktop
auto-update that stopped Postgres mid-run muddied the first diagnosis.)

**Fix:**
- An explicit client timeout of 60s (`llm.REQUEST_TIMEOUT_S`). The SDK still retries
  429/5xx/timeouts twice.
- An independent step backstop: `graph.RECURSION_LIMIT = 20` (the longest legitimate
  path is 8 steps), applied in `graph.ask()`. Hitting it becomes an abstention with
  `recursion_limited=True`, not a crash. Tested.
- The retry cap stays at 1.

**Prevention at scale:** Bound every loop at two independent levels (the app's retry
cap and the framework's step limit), and alert on cost per question, not just totals.
Never rely on a framework default you haven't checked in the installed version. Set
explicit timeouts on every network client.

**Time lost:** about 45 min, mostly the "hang" diagnosis.

---

## #7 Re-run backfill duplicates every chunk (PLANNED trap, M3, 2026-10-23)

**Planned:** D17 left `chunks` without a unique key on purpose, and the DAG's `upsert` task
is a plain `INSERT`. The question was what a re-run does, and what the metric shows.

**Trigger:** `airflow backfill create … --from-date 2026-10-12 --to-date 2026-10-16
--reprocess-behavior completed`, i.e. re-running days that had already succeeded.
That's exactly what an operator does after fixing a bug in a downstream task.
(Reprocessed backfill runs reuse their run IDs, `backfill__<date>`, so the run list
alone doesn't show that anything ran twice.)

**Symptom:** Every snapshot went from 315 rows to 630, with 315 exact duplicates. All
Airflow runs were green.

**Hypothesis (PLAN M3):** Duplicates *inflate* hit@5 while the system gets worse.

**Actual effect (eval_runs, same days, before → after):**
- doc@5: 0.68 → 0.62.
- fact@5 unfiltered: 0.65 → 0.59.
- fact@5 KG-filtered: **1.00 → 0.92**.

Duplicates *lowered* our metrics. Each chunk occupies two of the five slots, so the
top 5 holds only about 3 distinct chunks and second-best evidence is crowded out. The
plan's "inflation" holds for a precision-style metric (the share of the top 5 from the
right doc), not for presence-style hit@5. Both mislead; the direction depends on the
metric.

**Actual cause:** A non-idempotent write in a task that Airflow is designed to re-run.
Retries, `airflow tasks clear`, and backfill reprocessing all re-execute `upsert` with
the same inputs.

**Fix:** See D30.

**Prevention at scale:** Every task must be safe to run twice with the same logical
date. Make that a constraint the database enforces (a unique key), not a convention.
Record row counts per slice next to quality metrics (`eval_runs.chunk_rows`): the
doubling was obvious there long before the quality dip would have been.

**Time lost:** 0 (planned). About 5 min to measure.
