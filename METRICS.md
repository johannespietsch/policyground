# Metrics

Every column is defined here before it has numbers (PLAN §7). Rows are appended by
`make eval` and are never edited or deleted. Bad early rows are the point.

## Definitions

**Eval rows (table below), written by `make eval`:**

| Column | Definition |
|---|---|
| run | `YYYYMMDD-HHMMSS` of the run. Full per-question results are in `data/<tenant>/eval/run-<run>.json`. |
| commit | Short git SHA at run time, with `+dirty` if the tree had uncommitted changes. |
| ms | Milestone the code was at. |
| chunker / embedder | Retrieval configuration (`chunks.chunker`, `chunks.embedder`). |
| n | Golden questions in the headline metrics: the original 30 (Q01–Q30). The fuzzy-name questions are reported separately in `fuzzy`, so rows stay comparable. |
| correct | Correct answers over the **answerable** questions (plain + exception), scored by `eval/score.py`. |
| abst-acc | Abstention accuracy: share of **unanswerable** questions where `abstain=true`. |
| false-abst | Share of **answerable** questions where the system abstained. High means over-cautious; it trades against `correct`. |
| hit@5 | Share of answerable questions where **every** evidence doc (`golden.json` `evidence_docs`) has at least one chunk in the top-5 retrieved. Measured on the retrieval the answer node actually saw. |
| $/q | Mean cost per question in USD, from API token usage × list price. Excludes local embedding. |
| p50 / p95 s | End-to-end latency per question (graph invoke), in seconds. Runs sequentially. |
| graph | `rag` = M1 retrieve → answer; `kg` = M2 route → kg_lookup → retrieve → answer (→ validate). Added 2026-10-19; rows before that are `rag`. |
| unsupported | Share of **answerable** questions that are value-correct but cite none of the governing evidence (`golden.json` `governing`, D19). Counted inside `correct`, not subtracted from it. Added 2026-10-19. |
| val-rej | Validator rejection rate: share of headline questions that reached the answer node whose **first** answer the validator rejected (D24, strict). `—` for the rag graph, which has no validator. Added 2026-10-19. |
| fallback | Share of those questions that needed a regenerate or ended in a validator-forced abstain. Added 2026-10-19. |
| hard | Correct answers on Q36–Q43: month/year boundaries, a rate plan named only by ID, late-cancellation fee, cancelling inside the free window (D23). Not in the headline. Added 2026-10-22. |
| fuzzy | Correct answers on Q31–Q35: damaged property names, 4 resolvable plus 1 ambiguous, where abstaining is correct (D22). Added 2026-10-19. |

**Defined now, measured from later milestones:**

| Metric | Definition | From |
|---|---|---|
| validator catch rate (injected) | Share of injected faults (wrong date / time / window / amount, uncited value, invented citation) applied to real answers that the validator rejects. False-positive rate = share of the unmodified answers it rejects. `python -m policyground.eval.faults`, separate table. | M2 |
| hallucinated-number rate | Share of non-abstained answers containing a date, time or EUR amount that matches no KG fact for the property and appears in no cited chunk (date arithmetic from a KG window counts as backed). | M2 |
| hit@5 per chunker × embedder | hit@5 as above, retrieval only (no LLM), for each combination. Separate table. | M2 |
| DAG retry count | Task retries per DAG run, by task. | M3 |
| eval noise band | Mean ± 2σ of `correct` over 3 runs on an unchanged corpus. Nothing counts as drift inside it. | M4 |
| staleness window (min) | Time from a `policy.changed` event being applied to the KG until the matching chunks are re-embedded. | M4 |
| KG/vector disagreement rate | Share of properties whose resolved KG policy differs from what the latest chunks state. | M4 |
| skill attempts | Attempts the agent needed, following `SKILL.md`, before the second tenant's eval passes. | M6 |

## Eval runs

| run | commit | ms | tenant | chunker | embedder | model | n | correct | abst-acc | false-abst | hit@5 | $/q | p50 s | p95 s | graph | unsupported | fuzzy | val-rej | fallback | hard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261018-113345 | 57c655c | M1 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 0.76 | 1.00 | 0.24 | 0.72 | 0.00031 | 1.5 | 3.2 |
| 20261019-170456 | 5c79f8f | M1 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 0.76 | 1.00 | 0.24 | 0.72 | 0.00031 | 1.6 | 3.5 | rag | 0.04 | 4/5 |
| 20261019-170614 | 5c79f8f+dirty | M2 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00031 | 1.8 | 2.8 | kg | 0.00 | 5/5 |
| 20261019-171800 | 8bc8bac | M2 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00031 | 1.8 | 3.3 | kg | 0.00 | 5/5 | 0.00 | 0.00 |
| 20261022-200858 | bd81d01 | M2 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00038 | 2.3 | 4.9 | kg | 0.00 | 5/5 | 0.07 | 0.07 | 8/8 |
| 20261022-212452 | 11e291a | M2 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00034 | 2.2 | 5.3 | kg | 0.00 | 5/5 | 0.00 | 0.00 | 8/8 |

## Validator fault injection

Written by `python -m policyground.eval.faults`: injected faults on the correct answers of one kg eval run, validated offline. Cells are caught/applied.

| source run | answers | false pos | date+1d | time+1h | window+24h | amount+5 | no citations | invented citation | overall |
|---|---|---|---|---|---|---|---|---|---|
| 20261019-171800 | 29 | 0/29 | 12/13 | 23/23 | 13/13 | 4/4 | 29/29 | 29/29 | 0.99 |
| 20261019-171800 | 29 | 0/29 | 13/13 | 23/23 | 13/13 | 4/4 | 29/29 | 29/29 | 1.00 |

## Retrieval: hit@5 per chunker × embedder

Written by `python -m policyground.eval.retrieval`. Retrieval only, no LLM. Over all
answerable golden questions (headline, fuzzy and hard), top-5.

| Column | Definition |
|---|---|
| doc@5 | Every evidence doc has a chunk in the top 5 (unfiltered). Same definition as hit@5 in the eval table. Blind to chunk boundaries. |
| fact@5 unf. | A top-5 chunk from the governing doc **contains the fact text** (e.g. "48 hours", "non-refundable", "EUR 25"). Unfiltered: the plain-RAG setting. |
| fact@5 filt. | Same, with search restricted to the resolved property's lineage docs: what the kg graph sees. |
| NR together | Non-refundable questions where one retrieved (filtered) chunk holds **both** the cancellation rule and the exception, i.e. the chunk boundary didn't separate them. |

| date | chunker | embedder | n | doc@5 | fact@5 unf. | fact@5 filt. | NR together |
|---|---|---|---|---|---|---|---|
| 2026-10-22 ⚠ superseded (INCIDENTS #4) | naive-800 | bge-small-en-v1.5 | 37 | 0.73 | 0.65 | 0.92 | 0/3 |
| 2026-10-22 ⚠ superseded (INCIDENTS #4) | naive-800 | e5-base-v2 | 37 | 0.89 | 0.81 | 0.92 | 0/3 |
| 2026-10-22 ⚠ superseded (INCIDENTS #4) | structural-v1 | bge-small-en-v1.5 | 37 | 0.89 | 0.84 | 0.92 | 2/3 |
| 2026-10-22 ⚠ superseded (INCIDENTS #4) | structural-v1 | e5-base-v2 | 37 | 0.95 | 0.89 | 0.92 | 2/3 |
| 2026-10-22 | naive-800 | bge-small-en-v1.5 | 37 | 0.68 | 0.65 | 1.00 | 0/2 |
| 2026-10-22 | naive-800 | e5-base-v2 | 37 | 0.84 | 0.84 | 1.00 | 0/2 |
| 2026-10-22 | structural-v1 | bge-small-en-v1.5 | 37 | 0.84 | 0.84 | 1.00 | 2/2 |
| 2026-10-22 | structural-v1 | e5-base-v2 | 37 | 0.86 | 0.89 | 1.00 | 2/2 |
| 20261022-200858 | 37 | 0/37 | 20/20 | 31/31 | 19/21 | 4/4 | 37/37 | 37/37 | 0.99 |
| 20261022-200858 | 37 | 0/37 | 20/20 | 31/31 | 19/21 | 4/4 | 37/37 | 37/37 | 0.99 |
| 20261022-200858 | 37 | 0/37 | 20/20 | 31/31 | 20/21 | 4/4 | 37/37 | 37/37 | 0.99 |
