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
| 20261023-154620 | 7cfdb74 | M1 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 0.76 | 1.00 | 0.24 | 0.72 | 0.00034 | 1.7 | 5.3 | rag | 0.04 | 4/5 | — | — | 2/8 |
| 20261023-154802 | 7cfdb74 | M2 | hotels | structural-v1 | e5-base-v2 | claude-haiku-5-5 | 30 | 1.00 | 1.00 | 0.00 | 0.96 | 0.00034 | 2.1 | 3.4 | kg | 0.00 | 5/5 | 0.03 | 0.03 | 8/8 |
| 20261025-111248 | 7c15943 | M2 | hotels | structural-v1 | e5-base-v2 | claude-haiku-5-5 | 30 | 1.00 | 1.00 | 0.00 | 0.96 | 0.00036 | 2.2 | 5.7 | kg | 0.00 | 5/5 | 0.00 | 0.00 | 8/8 |
| 20261025-163605 | 2b6bd73 | M2 | hotels | structural-v1 | e5-base-v2 | claude-haiku-5-5 | 30 | 1.00 | 1.00 | 0.00 | 0.96 | 0.00036 | 2.4 | 3.9 | kg | 0.00 | 5/5 | 0.03 | 0.03 | 8/8 |
| 20261025-163751 | 2b6bd73 | M1 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 0.72 | 1.00 | 0.28 | 0.72 | 0.00033 | 1.7 | 4.0 | rag | 0.04 | 4/5 | — | — | 3/8 |
| 20261025-165256 | c0e8dc0+dirty | M2 | hotels | structural-v1 | e5-base-v2 | claude-haiku-5-5 | 30 | 1.00 | 1.00 | 0.00 | 0.96 | 0.00035 | 2.1 | 3.5 | kg | 0.00 | 5/5 | 0.00 | 0.00 | 8/8 |
| 20261025-192912 | 6d23893 | M2 | insurance | structural-v1 | e5-base-v2 | claude-haiku-5-5 | 26 | 1.00 | 1.00 | 0.00 | 0.90 | 0.00035 | 1.7 | 3.6 | kg | 0.00 | — | 0.00 | 0.00 | — |

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

## Airflow DAG runs (M3)

Notable runs of `ingest_policies`, recorded by hand from the metadata DB
(`task_instance_history`) and `eval_runs`.

| Column | Definition |
|---|---|
| runs | Which DAG runs (logical dates, run type). |
| purpose | What the run demonstrates. |
| result | Final run state; row counts per snapshot afterwards. |
| retries | Task retries in the run (the "DAG retry count" metric), by task, with waits between attempts. |
| eval (doc@5 / fact@5 filt.) | From `eval_runs`, per snapshot. |

| date | runs | purpose | result | retries | eval (doc@5 / fact@5 filt.) |
|---|---|---|---|---|---|
| 2026-10-23 | backfill 10-12…10-16 | first load | 5 × success; 315 rows/snapshot, 0 dups | 0 | 0.68 / 1.00 |
| 2026-10-23 | scheduled 10-23 | no snapshot that day | success with every task skipped (sensor soft-fail at 6 min); deadline alert at +4 min | 0 | — |
| 2026-10-23 | manual 10-17, fail_rate=0.6 | random 429 | success; the 429 didn't trigger (p = 0.4) | 0 | — |
| 2026-10-23 | manual 10-18, fail_first_tries=3 | forced 429s | success | embed: 3 (waits 22s / 44s / 77s); chunk not re-run | — |
| 2026-10-23 | backfill 10-12…10-16, reprocess=completed | re-run, naive upsert (INCIDENTS #7) | 5 × success; **630 rows/snapshot, 315 dups** | 0 | **0.62 / 0.92** |
| 2026-10-23 | backfill 10-12…10-16, reprocess=completed | re-run, idempotent upsert (D30) | 5 × success; 315 rows/snapshot, 0 dups | 0 | 0.68 / 1.00 |

## Drift (M4)

Written by `python -m policyground.drift` (D35). One row per measurement.

| Column | Definition |
|---|---|
| at | UTC time of the measurement. |
| mutation | The `make mutate` date whose changes are measured (= the new snapshot's date). |
| phase | `baseline`: changes published but not yet applied, so KG and vectors are both still old (the noise band comes from here). `stale`: KG updated by the consumer, vectors still old (the staleness window). `refreshed`: the DAG has ingested the new snapshot. |
| graph / n | rag (M1 baseline graph) or kg (production graph); number of probe questions (about exactly the mutated properties). |
| truth | Which answers are scored as correct: `expected_old` (before the change) or `expected` (after). |
| runs / mean | Correct share per run, and the mean. |
| band | Noise band = mean ± 2σ of the baseline runs, per graph. Anything inside it is noise, not drift. |
| verdict | `DRIFT (below band)` if the mean falls below the band, otherwise `within band`. |
| disagreement | Share (and count) of properties whose KG value (cancellation window, pet fee) differs from what the latest production chunks state. |
| staleness | Minutes from the KG applying the mutation's facts to that snapshot's chunks being ingested (`open` = not yet). |

| at | mutation | phase | graph | n | truth | runs | mean | band | verdict | disagreement | staleness |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-23 14:13 |  | pre-mutation | — | — | — | — | — | — | — | 0.000 (0) |  |
| 2026-10-23 14:13 | 2026-10-21 | baseline | rag | 15 | expected_old | 0.80 / 0.80 / 0.80 | 0.80 | [0.80, 0.80] | — |  |  |
| 2026-10-23 14:13 | 2026-10-21 | baseline | kg | 15 | expected_old | 1.00 / 1.00 / 1.00 | 1.00 | [1.00, 1.00] | — |  |  |
| 2026-10-23 14:17 | 2026-10-21 | stale | — | — | — | — | — | — | — | 0.100 (15) |  |
| 2026-10-23 14:17 | 2026-10-21 | stale | — | — | — | — | — | — | — |  | open: 0.3 min so far |
| 2026-10-23 14:18 | 2026-10-21 | stale | rag | 15 | expected | 0.00 / 0.00 / 0.00 | 0.00 | [0.80, 0.80] | DRIFT (below band) |  |  |
| 2026-10-23 14:18 | 2026-10-21 | stale | kg | 15 | expected | 0.87 / 0.87 / 1.00 | 0.91 | [1.00, 1.00] | DRIFT (below band) |  |  |
| 2026-10-23 14:22 | 2026-10-21 | stale | — | — | — | — | — | — | — |  | open: 4.9 min so far |
| 2026-10-23 14:26 | 2026-10-21 | refreshed | — | — | — | — | — | — | — |  | 8.2 min |
| 2026-10-23 14:26 | 2026-10-21 | refreshed | — | — | — | — | — | — | — | 0.000 (0) |  |
| 2026-10-23 14:46 | 2026-10-21 | refreshed | rag | 15 | expected | 0.87 / 0.80 / 0.87 | 0.84 | [0.80, 0.80] | above band |  |  |
| 2026-10-23 14:46 | 2026-10-21 | refreshed | kg | 15 | expected | 1.00 / 1.00 / 1.00 | 1.00 | [1.00, 1.00] | within band |  |  |
| 2026-10-25 09:57 | 2026-10-22 | baseline | rag | 15 | expected_old | 0.73 / 0.80 / 0.73 | 0.76 | [0.53, 0.98] | — (wrong stated 0/45, val-rej 0, forced abstain 0) |  |  |
| 2026-10-25 09:57 | 2026-10-22 | baseline | kg | 15 | expected_old | 1.00 / 1.00 / 1.00 | 1.00 | [0.87, 1.13] | — (wrong stated 0/45, val-rej 0, forced abstain 0) |  |  |
| 2026-10-25 10:02 | 2026-10-22 | stale | — | — | — | — | — | — | — | 0.100 (15) |  |
| 2026-10-25 10:02 | 2026-10-22 | stale | rag | 15 | expected | 0.00 / 0.00 / 0.00 | 0.00 | [0.53, 0.98] | DRIFT (below band) (wrong stated 36/45, val-rej 0, forced abstain 0) |  |  |
| 2026-10-25 10:02 | 2026-10-22 | stale | kg | 15 | expected | 1.00 / 1.00 / 1.00 | 1.00 | [0.87, 1.13] | within band (wrong stated 0/45, val-rej 1, forced abstain 0) |  |  |
| 2026-10-25 10:08 | 2026-10-22 | refreshed | — | — | — | — | — | — | — |  | 5.1 min |
| 2026-10-25 10:08 | 2026-10-22 | refreshed | — | — | — | — | — | — | — | 0.000 (0) |  |
| 2026-10-25 10:08 | 2026-10-22 | refreshed | rag | 15 | expected | 0.93 / 0.93 / 0.93 | 0.93 | [0.53, 0.98] | within band (wrong stated 0/45, val-rej 0, forced abstain 0) |  |  |
| 2026-10-25 10:08 | 2026-10-22 | refreshed | kg | 15 | expected | 1.00 / 1.00 / 1.00 | 1.00 | [0.87, 1.13] | within band (wrong stated 0/45, val-rej 0, forced abstain 0) |  |  |

## Tenant onboarding via SKILL.md (M6)

Each run: a fresh Claude Code subagent in its own git worktree, with only AGENTS.md,
`.claude/skills/onboard-tenant/SKILL.md` and a domain brief (D45). Attempts are counted
by the done-check itself (`data/<tenant>/onboarding-attempts.jsonl`), not reported by the
agent.

| Column | Definition |
|---|---|
| attempts | Runs of `make check-tenant` until `DONE-CHECK PASSED` (the "skill attempts" metric). |
| correct / abst-acc | The done-check's LLM eval through the kg graph (thresholds 0.8 / 0.8). |
| agent time / tokens | Subagent wall time and tokens, from the harness. |

| date | run | base commit | tenant | attempts | n | correct | abst-acc | agent time | tokens | outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-25 | 1 | 76f2e3b (skill v1) | insurance | 1 | 28 | 0.87 | 1.00 | 8.8 min | 143k | passed. Found: scorer crash on `phrase` without `value`; deadline rules not bindable to a question date; hotel wording in prompt; skill gaps. Exclusion answers gave a deadline (Q20/21). Not merged. |
| 2026-10-25 | 2 | 62af47e (skill v2 + fixes) | insurance | 1 | 26 | 1.00 | 1.00 | 7.5 min | 131k | passed. Used `anchor_date_hints`, `variant_scope`, `prompt.rules`; exclusion answers give no deadline. **Merged** (6d23893); regenerated byte-identically on main. |
