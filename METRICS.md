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
| fuzzy | Correct answers on Q31–Q35: damaged property names, 4 resolvable plus 1 ambiguous, where abstaining is correct (D22). Added 2026-10-19. |

**Defined now, measured from later milestones:**

| Metric | Definition | From |
|---|---|---|
| hallucinated-number rate | Share of non-abstained answers containing a date, time or EUR amount that matches no KG fact for the property and appears in no cited chunk (date arithmetic from a KG window counts as backed). | M2 |
| validator rejection rate | Share of answers the validator rejects on the first attempt. | M2 |
| fallback rate | Share of questions that needed the regenerate path or ended in a validator-forced abstain. | M2 |
| hit@5 per chunker × embedder | hit@5 as above, retrieval only (no LLM), for each combination. Separate table. | M2 |
| DAG retry count | Task retries per DAG run, by task. | M3 |
| eval noise band | Mean ± 2σ of `correct` over 3 runs on an unchanged corpus. Nothing counts as drift inside it. | M4 |
| staleness window (min) | Time from a `policy.changed` event being applied to the KG until the matching chunks are re-embedded. | M4 |
| KG/vector disagreement rate | Share of properties whose resolved KG policy differs from what the latest chunks state. | M4 |
| skill attempts | Attempts the agent needed, following `SKILL.md`, before the second tenant's eval passes. | M6 |

## Eval runs

| run | commit | ms | tenant | chunker | embedder | model | n | correct | abst-acc | false-abst | hit@5 | $/q | p50 s | p95 s | graph | unsupported | fuzzy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261018-113345 | 57c655c | M1 | hotels | naive-800 | bge-small-en-v1.5 | claude-haiku-5-5 | 30 | 0.76 | 1.00 | 0.24 | 0.72 | 0.00031 | 1.5 | 3.2 |
