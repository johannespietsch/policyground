# Decisions

Each entry is recorded at the moment it was made. Format: Context / Options / Chosen /
Why / Revisit if.

---

## D1 Domain / first tenant

**Date:** 2026-10-16

**Context:** Need a first tenant whose wrong answers carry an obvious, concrete cost, so
the hallucination-management story doesn't need explaining.

**Options:**
- (a) Partner-policy Q&A for customer-support agents in travel/hospitality.
- (b) Back-office policy bot (travel & expense, HR).
- (c) Public regulatory corpus.

**Chosen:** (a) Travel/hospitality partner-policy Q&A.

**Why:** A wrong cancellation deadline or a missed non-refundable exception costs real
money and an angry customer. The domain also has natural nesting (chain → brand →
property → rate plan) and exceptions, which is exactly the shape that breaks naive RAG.

**Revisit if:** The nesting turns out too shallow to show the chunk-boundary failure, or
the domain starts to read as tied to one specific company.

---

## D2 Corpus

**Date:** 2026-10-16

**Context:** Evaluation needs ground truth, and the drift story needs controlled,
injectable changes.

**Options:**
- (a) Synthetic corpus generated from the KG.
- (b) Real public documents.

**Chosen:** (a) Synthetic, generated from the KG with a seeded RNG.

**Why:** The KG is the ground truth, so golden answers come for free and drift can be
injected on purpose (`make mutate`). It also avoids any appearance of using real
third-party or partner data.

**Revisit if:** Generated text is too uniform to be a fair test of retrieval. Counter by
varying the wording templates before switching to real data.

---

## D3 KG store

**Date:** 2026-10-16

**Context:** The KG has to resolve policy inheritance (chain → property, with property
overrides winning) and sit next to the vector index.

**Options:**
- (a) Postgres with recursive CTEs.
- (b) Neo4j.

**Chosen:** (a) Postgres (same instance as pgvector).

**Why:** One database to run, back up and secure, with role separation (`ingest_rw` /
`api_ro`) in one place. A `WITH RECURSIVE` resolver for policy inheritance is a useful
SQL-depth signal in its own right. Neo4j would read more loudly as "graph" but adds a
service and a query language without any measured benefit for a shallow hierarchy.

**Revisit if:** Queries need multi-hop traversal beyond the inheritance chain (e.g.
arbitrary relationship paths), where Cypher would be clearly simpler.

---

## D4 Agent framework

**Date:** 2026-10-16

**Context:** The answer path has explicit branches: route → kg_lookup → retrieve → answer
→ validate → (retry ≤1 | abstain).

**Options:**
- (a) LangGraph.
- (b) LangChain only.
- (c) Hand-rolled loop on a raw SDK.

**Chosen:** (a) LangGraph.

**Why:** The validate/retry/abstain branching maps directly onto an explicit state graph,
which makes the retry cap and abstain path visible and testable rather than buried in
loop logic. It also shows fluency with a widely used orchestration framework.

**Revisit if:** Framework overhead or version churn costs more time than the graph saves.
The M1 fallback is a plain function, with the framework added in M2.

---

## D5 Airflow version

**Date:** 2026-10-16

**Context:** Nightly ingestion needs a sensor, retries, a deadline and a backfill.

**Options:**
- (a) Airflow 3.x: current, with Deadline Alerts replacing SLAs.
- (b) Airflow 2.10.x: has `sla` literally, but is near the end of its support window.

**Chosen:** (a) Airflow 3.x.

**Why:** It's the current line, and building on a version near end of support would look
dated. SLAs were removed in 3.x and replaced by Deadline Alerts. Being able to explain
that change is part of the point.

**Revisit if:** Deadline Alerts turn out immature or poorly documented in the pinned
version. Fall back to a plain task-level timeout plus an alerting callback.

---

## D6 Breadth slot (~2h)

**Date:** 2026-10-16

**Context:** One extra system to show breadth beyond model + pipeline.

**Options:**
- (a) Kafka (via Redpanda).
- (b) Snowflake trial.
- (c) AWS Lambda + S3 free tier.

**Chosen:** (a) Kafka-compatible streaming via Redpanda.

**Why:** It creates the project's best failure surface, the staleness race. The KG updates
in seconds from events while vectors only update nightly, so the two visibly disagree,
and that gap is detectable. It runs locally in compose, with no account and no expiry.

**Revisit if:** Redpanda's compose setup eats the time budget. The M4 fallback writes
mutations straight to the KG and keeps the drift story.

---

## D7 Answer LLM

**Date:** 2026-10-16

**Context:** The plan allows a single LLM provider. Cost per question and the M2
retry-blowup trap have to be measurable.

**Options:**
- (a) Claude Haiku 5.5 (`claude-haiku-5-5`).
- (b) Claude Sonnet 5.5.
- (c) Local model via Ollama.

**Chosen:** (a) Claude Haiku 5.5.

**Why:** It's cheap and fast enough to run the eval often. A smaller model makes more of
the mistakes the validator exists to catch, so the grounding story shows up in the
numbers instead of being hidden by a stronger model.

**Revisit if:** Correctness stays low even with the right facts in context. That would
be a model-capability ceiling, not a grounding problem.

---

## D8 Primary embedding model

**Date:** 2026-10-16

**Context:** M1 needs a small local embedder. M2 compares two embedders × two chunkers
on hit@5.

**Options:**
- (a) `BAAI/bge-small-en-v1.5` (384-dim).
- (b) `all-MiniLM-L6-v2` (384-dim).
- (c) `nomic-embed-text-v1.5` (768-dim).

**Chosen:** (a) bge-small-en-v1.5.

**Why:** Strong retrieval for its size, runs on CPU, no API key or rate limit. The
second M2 model is still to be decided.

**Revisit if:** hit@5 is poor even with structural chunking.

---

## D9 Python tooling

**Date:** 2026-10-16

**Options:**
- (a) uv.
- (b) Poetry.
- (c) pip + venv + requirements.txt.

**Chosen:** (a) uv.

**Why:** Fast, lockfile-based and reproducible. It also handles the separate Airflow venv
(installed against Airflow's constraints file) in M3 without fighting the main project's
resolver.

**Revisit if:** Airflow's constraints install conflicts with uv's resolver.

---

## D10 Abstention signal

**Context:** 5 of the 30 golden questions are unanswerable. The system has to signal
abstention in a way the eval can score deterministically.

**Date:** 2026-10-16

**Options:**
- (a) Structured output: `{answer, citations[], abstain: bool}`.
- (b) Sentinel string in free text.
- (c) Retrieval-score threshold before the LLM call.

**Chosen:** (a) Structured output field.

**Why:** Deterministic to score and parse. Citations arrive as data, not prose. In M2 the
validator can force `abstain=true` regardless of what the model said. A score threshold
would conflate "no relevant text" with "relevant text that doesn't answer the question".

**Revisit if:** The model over-abstains. Check the prompt before moving the decision.

---

## D11 Brand level in the hierarchy

**Date:** 2026-10-16

**Context:** The plan contradicted itself: D3 described chain → brand → property, while
the M2 table list had no brand.

**Options:**
- (a) chain → brand → property → rate_plan.
- (b) chain → property → rate_plan.

**Chosen:** (a) Include brand.

**Why:** Without brand, inheritance is a plain join, and calling the resolver a
recursive CTE (D3) would be hard to defend. Three levels also allow an override of an
override (chain sets X, brand changes it, property changes it back), which makes a
harder exception case for the golden set.

**Revisit if:** Never. This is a modelling choice the rest depends on.

---

## D12 KG representation in M1

**Date:** 2026-10-16

**Context:** M1 retrieval is plain RAG (the "before" picture) and doesn't query the KG.
The golden set still needs a ground-truth source.

**Options:**
- (a) The generator emits `kg.json` in M1. Postgres KG tables arrive in M2.
- (b) Create the KG tables in M1 and have the golden set query them.

**Chosen:** (a) `kg.json` in M1.

**Why:** Keeps M1 inside its 3h and keeps the milestone boundary clean. M2 loads the same
`kg.json` into tables, and the SQL resolver can be tested against the Python resolver
that produced the golden answers.

**Revisit if:** The JSON and SQL resolvers diverge in ways that are hard to reconcile.

---

## D13 Document layout variation

**Date:** 2026-10-16

**Context:** With one fixed fact-sheet layout, an 800-char chunker separated the
cancellation rule from the non-refundable exception in 62 of 62 docs. M1 exception
questions would fail every time, and the M2 fix would look rigged.

**Options:**
- (a) Keep the fixed layout (100% split).
- (b) Shuffle the sections after the overview.
- (c) Two layouts: the standard fact sheet, or "booking terms first" (cancellation and
  rate plans adjacent at the top).

**Chosen:** (c), with 30% of docs booking-first.

**Why:** (b) was tried and measured at 95% split. The roughly 400-char overview pushes
almost any order across the 800-char boundary, so shuffling barely changed anything.
(c) measured 43/62 = 69% split, inside the 60–80% target. Both layouts are realistic. The
manifest records the layout per doc, so the eval can show failures concentrating in the
split docs.

**Revisit if:** The chunk size changes. The split rate depends on it.

**Amended 2026-10-17:** Fixing duplicate property names (see D18) changed the RNG
stream. Re-measured: 42/54 = 78% split. Still in range.

---

## D14 Standard-terms references and chain/brand docs

**Date:** 2026-10-16

**Context:** Every property doc stated its own values in full, so a single chunk could
always answer a question. The KG was convenient, not necessary.

**Options:**
- (a) Keep self-contained property docs.
- (b) Some property docs defer cancellation to "the standard {brand} terms". Brand docs
  either state their override or defer to the chain. One doc per chain states the
  defaults.

**Chosen:** (b). 40% of eligible property docs defer (35/150 at seed 42). 7 of those need
3 hops: property → brand → chain.

**Why:** Mirrors how real policy text is written, and creates questions that plain
retrieval can only answer by chaining 2–3 documents, while the KG resolves them in one
query. That makes the grounding story structural, not just a matter of chunking.
Property-level overrides are never deferred, since an override must be stated (tested).

**Revisit if:** There are too few 3-hop cases to say anything about. Raise the
brand-defers-to-chain share. Only cancellation is deferred so far; pets could follow the
same pattern.

**Amended 2026-10-17:** After the duplicate-name fix (D18), 45/150 docs defer, and 14 of
them need 3 hops. That's enough to keep 3-hop as a separate tagged question type.

---

## D15 Database roles from M1

**Date:** 2026-10-16

**Context:** PLAN §4 has only the ingest path writing; the API connects read-only.

**Options:**
- (a) Create `ingest_rw` / `api_ro` in M1.
- (b) Start with one superuser and split later.

**Chosen:** (a) Three roles from the start: an admin that owns the schema and runs
migrations, `ingest_rw` (read and write data, but no DDL), and `api_ro` (SELECT only).

**Why:** About 10 lines of SQL now, against retrofitting grants later. With
`ALTER DEFAULT PRIVILEGES`, every table created afterwards picks up the right grants
automatically. Smoke-tested: `ingest_rw` can write but not `CREATE TABLE`, and `api_ro`
can `SELECT` but not `INSERT` or `DELETE`.

**Revisit if:** Not expected to change.

**Notes:** The init script is baked into a small image, not bind-mounted, because Docker
Desktop can't mount from `~/Documents` without a macOS privacy grant. Role names can't
start with `pg_` (reserved), so the admin role is `pgadmin`. Postgres is published on
host port 5433 to avoid clashing with other local projects.

---

## D16 Embedding column for multiple embedders

**Date:** 2026-10-16

**Context:** M2 compares chunkers × embedders. The second embedder may not be 384-dim.

**Options:**
- (a) One table with an untyped `vector` column, using exact scan.
- (b) A typed `vector(384)` column with an HNSW index.
- (c) One table per embedder.

**Chosen:** (a). One `chunks` table with `chunker` and `embedder` columns.

**Why:** Leaves the choice of second embedder open. Untyped vectors can't take an HNSW
index, but at around 1k chunks an exact scan takes milliseconds. Exact search also keeps
approximate-nearest-neighbour error out of the hit@5 comparison, so differences come
from the chunker and embedder alone.

**Revisit if:** The corpus grows to where exact scan shows up in p95 latency. Then add a
typed column per embedder, or a partial index on a dimension cast.

---

## D17 Idempotency key deferred to M3 (deliberate)

**Date:** 2026-10-16

**Context:** PLAN M3's trap: a non-idempotent upsert makes backfill duplicate chunks,
which inflates hit@5 while the system actually gets worse.

**Options:**
- (a) Add the unique key now.
- (b) Leave it out. M1 ingest truncates and reloads; M3 backfill hits the bug for real.

**Chosen:** (b), stated openly in a comment in `001_chunks.sql`.

**Why:** Same approach as the M1 chunk-boundary trap. The M3 incident should be measured,
not described hypothetically. The `INCIDENTS.md` entry must say the gap was left on
purpose and record what the metric did, so the story stays honest.

**Revisit if:** Anything other than the M3 backfill starts writing chunks before M3.

---

## D18 Golden set design

**Date:** 2026-10-17

**Context:** The M1 eval needs 30 Q/A pairs (20 plain, 5 exception, 5 unanswerable),
scored deterministically with no LLM judge (PLAN §6).

**Options considered:**
- Cancellation answers as a window in hours vs. an exact deadline timestamp.
- Unanswerable questions as non-existent properties vs. facts the KG never holds.

**Chosen:**
- Cancellation questions give a check-in date and expect the last free-cancellation
  moment as `YYYY-MM-DD HH:MM`, i.e. check-in date + check-in time − window.
- Typed expected answers: `datetime`, `time`, `eur`, `no_free_cancellation`, `abstain`.
- Plain questions (20): 8 cancellation deadlines (stated in the property doc, no
  override), 4 check-in times, 4 check-out times, 4 pet fees.
- Exception questions (5), each tagged by type: 2 non-refundable, 1 by-reference 2-hop,
  1 by-reference 3-hop, 1 property override that differs from the brand value.
- Unanswerable questions (5): parking, shuttle, minimum age, city tax, late-check-out
  fee. A test checks these words never appear in the corpus.
- Each question records `evidence_docs`, which M2 hit@5 will use. A test checks that
  every expected answer is derivable from its evidence docs.

**Why:** A timestamp turns "48h" into something the validator can check exactly, and it
forces date arithmetic, where models slip. Facts the KG never holds are a harder
abstention test than a missing property: retrieval still returns a confident-looking,
on-topic chunk.

**Found while building:** The generator produced 6 duplicate property names, which would
have made those questions ambiguous. Fixed by redrawing until the name is unique, and
tested. This changed the RNG stream, so the corpus numbers in D13 and D14 were
re-measured.

**Revisit if:** 30 questions turn out too few to separate the exception types. Expect
the noise band (M4) to answer that.

---

## D19 "Unsupported" as its own scoring outcome

**Date:** 2026-10-19

**Context:** INCIDENTS #2. Q24 scored correct, but on the chain doc, when the property
defers to its brand. Value-only scoring can't tell a supported answer from a lucky one.

**Options:**
- (a) Keep no-op overrides in the golden set. Score a correct value whose citations don't
  include the governing evidence as a separate outcome, `unsupported`.
- (b) Exclude no-op overrides when picking exception questions.

**Chosen:** (a).

**Why:** No-op overrides are realistic, and hiding them would hide a real reasoning
failure. A separate outcome keeps `correct` honest. It also gives the M2 validator a
concrete thing to catch: a value that's right but cited from a non-governing document.

**Revisit if:** "Governing evidence" proves too fuzzy to define deterministically. Fall
back to "cites at least one evidence doc".

---

## D20 Reframe the pitch around measured failure (over-abstention)

**Date:** 2026-10-19

**Context:** The plan's pitch assumed plain RAG fails by confident hallucination. In the
M1 baseline, all 7 failures were retrieval misses that the model correctly abstained on.
There were no confident wrong answers, and the chunk-boundary trap was never reached.

**Options:**
- (a) Reframe: plain RAG's measured cost is over-abstention (24%). The KG route turns
  abstentions into correct answers, and the validator is a guardrail whose catch rate is
  measured.
- (b) Keep the original hallucination framing and look for hallucinations once
  retrieval returns the right but split chunks.

**Chosen:** (a). PLAN §2 rewritten accordingly.

**Why:** The project's credibility rests on reporting what was measured. A pitch that
claims a failure mode the baseline didn't show would be the first thing to fall apart
under questioning. The hallucination hypothesis stays open and is tested in M2, after
entity resolution; if it shows up there, it's reported as a finding.

**Revisit if:** M2 shows confident wrong answers once the split chunks are reachable.

---

## D21 KG schema: adjacency list

**Date:** 2026-10-19

**Context:** D3 claims a recursive CTE resolves policy inheritance. The table layout
decides whether that claim holds.

**Options:**
- (a) One `entity` table with `parent_id`, plus `policy_fact`. Resolve with
  `WITH RECURSIVE`.
- (b) Typed tables (chain/brand/property/rate_plan) with real FKs. The resolver is fixed
  joins.
- (c) Hybrid: an adjacency table plus typed detail tables.

**Chosen:** (a). `db/migrations/002_kg.sql`, with the SQL function `resolve_policy`.

**Why:** Recursion is then the natural way to walk the hierarchy, not decoration. Adding
a level (e.g. region) needs no schema change. With (b), calling the resolver "recursive"
would be hard to defend. Cost: type-specific fields (city, rate-plan kind) live in
`attrs jsonb` with weaker constraints. Accepted at this size.

**Details:**
- `policy_fact` holds one current value per (entity, key), with `valid_from`, ready for
  M4's out-of-order guard.
- The CTE caps depth at 10 as a cycle guard.
- Tested: the SQL resolver equals the Python resolver for all 150 properties and 302
  rate plans, and the test was shown to fail when a brand fact is changed.

**Revisit if:** Typed constraints start mattering, e.g. invalid `attrs` slipping in.
That would point to (c).

---

## D22 Route: fuzzy property matching with pg_trgm

**Date:** 2026-10-19

**Context:** INCIDENTS #1. Embeddings can't tell near-identical properties apart, so
the KG route needs to work out which property a question is about.

**Options:**
- (a) Exact name match. 100% on this data only because the generator puts exact names
  in every question.
- (b) `pg_trgm` `word_similarity`, with a score threshold and a margin over the
  runner-up. Abstain and ask otherwise.
- (c) An LLM extracts the property name, then a lookup runs.

**Chosen:** (b). Resolve if best ≥ 0.60 and best − second ≥ 0.05, otherwise answer
"Which property do you mean?" with no LLM call.

**Why:** Deterministic, typo-tolerant, lives in SQL, and costs no model call.
`word_similarity` scores the name against its best-matching span of the question, so a
long question doesn't dilute the score.

**Measured:**
- Exact names: best 1.00, runner-up ≤ 0.90, minimum gap 0.10.
- Hand probes: dropped brand word 0.75, gap 0.20; typo 0.86, gap **0.07** (thin);
  "Meridian hotel in Hamburg" 0.49, so it abstains.
- The thresholds were chosen from these probes, so 5 golden questions (Q31–Q35) were
  generated from *other* properties with the same kinds of damage, as a partly held-out
  check. Result: 5/5 under the KG graph.
- Q01–Q30 are unchanged, and headline metrics use only those, so rows stay comparable.

**Revisit if:** Real names are less distinctive than synthetic ones, or the typo
margin causes wrong matches. Then fall back to (c) for low-confidence cases only.

---

## D23 Validator evaluation strategy

**Date:** 2026-10-19

**Context:** The M2 KG graph scored 1.00 on the golden set, which is now saturated. The
validator had nothing to catch, so its catch rate would read 0/0.

**Options:**
- (1) Harder questions.
- (2) Validator measured with injected faults.
- (3) Both.
- (4) Wait for M4's staleness contradictions.

**Chosen:** (3), and measure the real catch rate again in M4.

**Why:** Injected faults prove the validator catches what it claims to: wrong dates,
times, amounts, uncited values. Harder questions show whether the model errs at all
on this data. If it doesn't, that's reported as a finding, not hidden.

**Revisit if:** Not expected to change.

---

## D24 Validator strictness: values must trace to *cited* evidence

**Date:** 2026-10-19

**Context:** The validator checks every date, time, EUR amount and "N hours" in an
answer. The question is what counts as backing.

**Options:**
- (a) Strict: backing must be a cited KG fact, a cited chunk's text, or the question.
  Deadlines count as backed when they're derived from a cited window plus a backed
  check-in time.
- (b) Lenient: any fact or chunk the model was shown, cited or not.

**Chosen:** (a).

**Why:** It enforces citation discipline, and catches D19-style lucky answers at
validation time, not only in the eval. The cost is more rejections and retries, which is
measurable and is exactly what the retry-cap trap needs.

**Measured (first run):** 0 rejections on 30 real answers. Fault injection: 110/111
caught, 0/29 false positives (METRICS, "Validator fault injection"). The one miss is
INCIDENTS #3.

**Revisit if:** The false-positive rate rises on harder questions, i.e. correct
answers rejected because the model cites loosely.

---

## D25 Second embedder: e5-base-v2

**Date:** 2026-10-22

**Context:** M2 compares two embedders. The second should be more capable than
bge-small, and 768-dim to exercise D16's mixed-dimension column.

**Options:**
- (a) e5-base-v2.
- (b) bge-base-en-v1.5.
- (c) nomic-embed-text-v1.5.

**Chosen:** (a).

**Why:** A different model family from bge, so the comparison says more than "bigger
model, same recipe". No `trust_remote_code`: nomic would execute Python code from its
model repo at load time, which is a supply-chain risk to defend for no measured gain.
e5 needs `query: ` / `passage: ` prefixes, now handled per model in `embed.py`.

**Revisit if:** Retrieval quality becomes the bottleneck again.

---

## D26 Structural chunker: sections, booking terms merged, title header

**Date:** 2026-10-22

**Context:** The plan says "one chunk per policy section, exceptions kept with their
rule".

**Options:**
- (a) Sections, with Cancellation and Rate plans merged, and every chunk prefixed with
  the doc's title/ID line.
- (b) The same without the header.
- (c) Both, as separate chunkers.

**Chosen:** (a), as `structural-v1`.

**Why:** The header also targets INCIDENTS #1 (wrong-property retrieval). Accepted
trade-off: the comparison measures both effects together, so the gain over naive can't
be split between "kept the exception with its rule" and "chunk names its property".
The NR-together column isolates the first effect; doc@5 mixes both.

**Revisit if:** The write-up needs the two effects separated. Then add (b) as
`structural-noheader` (cheap, no API cost).

---

## D27 Loop and request backstops

**Date:** 2026-10-22

**Context:** INCIDENTS #6. With the retry cap removed, only LangGraph's default
recursion limit (10007 in 1.2.16) would stop a regenerate loop. The Anthropic SDK's
default timeout is 10 min, with 2 retries.

**Options:**
- (a) Rely on the retry cap alone.
- (b) Add an explicit step limit and a client timeout as independent backstops.

**Chosen:** (b). `RECURSION_LIMIT = 20` via `graph.ask()`, which converts hitting it
into an abstention, plus a 60s request timeout.

**Why:** A bug in one guard shouldn't turn into a $2.50, 3-hour question. Both
backstops are cheap and tested, and they don't affect the normal path (≤ 8 steps,
a ~2–5s request).

**Revisit if:** Prompts grow enough that 60s becomes tight. Then switch to streaming,
not a longer timeout.

---

## D28 Airflow integration (M3)

**Date:** 2026-10-23

**Context:** Airflow 3.3.2 (current, 2026-09-17) has to run the ingestion pipeline. It
must be installed against its own constraints file (D9), so it can't share the
project's venv.

**Chosen:**
1. **Tasks call our code as subprocesses** (`uv run python -m policyground.…`), not
   `ExternalPythonOperator`. This keeps the two dependency sets fully separate. Each
   step is a CLI we can also run by hand. Accepted cost: Airflow only sees exit codes
   and logs, not Python objects.
2. **Airflow metadata in its own `airflow` database on the project Postgres**, owned
   by a separate `airflow_meta` role, not SQLite. More realistic, allows the
   LocalExecutor to run tasks in parallel, and keeps Airflow's tables out of the app's
   schema and roles.
3. **A real Deadline Alert**, with the explicit caveat that Deadline Alerts are
   documented as *experimental* in 3.3.2 (introduced in 3.1). If it proves unusable:
   task timeouts plus a failure callback, the PLAN M3 fallback.

**Why:** Each choice keeps a boundary that's easy to explain (dependency sets,
databases, roles) at little cost for a single-machine demo.

**Revisit if:** Subprocess overhead or opaque failures make debugging slow. Then use
`ExternalPythonOperator` against the project venv.

---

## D29 DAG task granularity and the DAG's eval task

**Date:** 2026-10-23

**Context:** The M1 `ingest` command chunked, embedded and wrote in one process. Airflow
retries per task, and tasks are separate processes that can't share memory.

**Options:**
- Granularity: (a) `chunk → embed → upsert`, passing staging files; (b) one task.
- Eval: (a) retrieval-only (free, deterministic); (b) the full LLM eval on every run.

**Chosen:** (a) and (a).
- Steps hand data through `data/<tenant>/staging/<date>/<chunker>__<embedder>/`
  (`chunks.jsonl`, `embeddings.npy`), not XCom, which is meant for small values.
- The DAG's `eval` task writes retrieval metrics plus the slice's row count to the
  `eval_runs` table. The LLM eval stays manual (`make eval`).

**Why:** A failed embed retries alone. Demonstrated: three simulated 429s, then success;
`chunk` didn't re-run. Waits were 22/44/77s, exponential with Airflow's jitter. A
deterministic, free eval suits a scheduled job. Whether the LLM eval should run on a
schedule is revisited in M4, once the noise band is measured.

**Revisit if:** M4's drift detection needs the LLM eval on a schedule.

---

## D30 Idempotent upsert: overwrite the slice, plus a unique key

**Date:** 2026-10-23

**Context:** INCIDENTS #7. Re-running the backfill doubled every chunk.

**Options:**
- (a) Delete the (tenant, snapshot, chunker, embedder) slice and insert it again in
  one transaction, plus a unique key as a safety net.
- (b) A unique key with `ON CONFLICT DO UPDATE`.
- (c) A key on `chunk_hash` with `ON CONFLICT DO NOTHING`.

**Chosen:** (a). Migration 005 dedups the existing rows and adds `chunks_slice_key`.

**Why:** It's the standard "insert overwrite partition" pattern. One transaction means
readers never see a half-written slice. Unlike (b), it leaves no orphan rows when a doc
yields fewer chunks. Unlike (c), it never keeps a stale version next to a changed one,
which is the failure M4 is about. The unique key turns any future regression into a
loud error, not silent duplication.

**Revisit if:** Slices grow large enough that delete-and-insert is slow. Then use
partitioned tables and swap partitions.

---

## D31 Production retrieval: structural-v1 × e5-base-v2

**Date:** 2026-10-23

**Context:** The app and the DAG still used the M1 baseline (naive-800 × bge-small). The
M2 comparison: KG-filtered fact@5 was 1.00 under every configuration. For plain RAG,
structural × e5 was best (fact@5 0.89 vs 0.65), and only the structural chunker keeps
the non-refundable exception with its rule (2/2 vs 0/2).

**Options:** (a) Keep the baseline. (b) Switch production to structural-v1 × e5-base-v2.

**Chosen:** (b). `policyground.config` holds `PRODUCTION` (kg graph, API, ingest, DAG
default) and `BASELINE` (pinned for `GRAPH=rag`, so earlier rows stay comparable).

**Why:** It doesn't change answer correctness through the KG, but it improves what gets
cited. The chunk the model cites now contains the rule *and* its exception, and names
its property. That makes citations better evidence for a support agent, and it makes the
`unsupported` check and the validator's cited-text backing more meaningful.

**Cost:** e5-base is about 2× slower to embed than bge-small (768-dim). That shows in
ingest time and in per-question query embedding (measured in the next eval row).

**Revisit if:** Query latency matters more than citation quality.

---

## D32 Kafka client: confluent-kafka

**Date:** 2026-10-23

**Options:** (a) confluent-kafka; (b) aiokafka; (c) kafka-python.

**Chosen:** (a), pinned to 2.16.0. The broker is Redpanda v26.2.4 (Kafka-compatible,
single binary).

**Why:** It wraps librdkafka, the de-facto production client, with correct
consumer-group, manual-commit and keyed-partitioner semantics. Its synchronous API suits
a simple consume → write → commit loop.

**Revisit if:** The consumer has to live inside an async service.

---

## D33 Mutations: property-level, and ground truth moves with them

**Date:** 2026-10-23

**Options:** (a) Property-level changes only. (b) Property and brand level.

**Chosen:** (a). `make mutate` plays the partner system:
- It changes ~10% of properties (cancel window and/or pet fee) in the partner's state
  (`kg.json`).
- It publishes one `policy.changed` event per fact, keyed by `property_id`.
- It writes the next day's snapshot from the new state, for the DAG.

Golden answers are re-derived from the new truth, so a stale answer counts as a wrong
answer.

**Why:** It keeps "key = property_id" (PLAN M4) coherent. A brand-level change would fan
out to ~10 properties and need a different partition key. That's a known extension,
not built.

**Revisit if:** We want the fan-out case, keyed by brand, with downstream re-resolution.

---

## D34 Out-of-order guard: a per-fact version number

**Date:** 2026-10-23

**Context:** `policy_fact.valid_from` is a DATE, so two changes on the same day would tie.

**Options:**
- (a) A partner-assigned, monotonically increasing version per (entity, key).
- (b) A `changed_at` timestamp.
- (c) `valid_from` as is.

**Chosen:** (a). The event carries `version`, `policy_fact` stores it, and the upsert
applies only when the incoming version is greater than the stored one.

**Why:** Exact and independent of clocks: no ties, no skew. It's the standard
optimistic-concurrency pattern, and it makes the consumer idempotent under re-delivery
(an equal version is a no-op).

**Revisit if:** The partner can't supply versions. Then use (b) plus `event_id` dedup.

---

## D35 Drift measurement: probe set plus a noise band

**Date:** 2026-10-23

**Options:** (a) A probe set about exactly the mutated properties, LLM eval, noise band
from 3 runs. (b) Only the re-derived golden set.

**Chosen:** (a). The noise band is mean ± 2σ over 3 runs on an unchanged corpus.
Nothing inside it counts as drift.

**Why:** Only ~3 golden questions would touch mutated properties, too few for a drop to
clear the noise band. A probe set aims the measurement at the change. Cost: about $0.01
per run.

**Revisit if:** The noise band is so wide that 3 runs are too few. Then use more runs or
more probes.

---

## D36 Stale-value false positives: fix the prompt, keep the validator strict

**Date:** 2026-10-25

**Context:** INCIDENTS #10. During staleness the model correctly answered from the KG fact,
but mentioned the stale excerpt value without citing that excerpt, so the strict validator
(D24) rejected correct answers.

**Options:**
- (a) A prompt rule: cite an excerpt whenever you mention its value; otherwise don't
  restate conflicting values.
- (b) The validator treats values present in shown-but-uncited evidence as warnings.
- (c) Leave it: abstaining on conflict is safe.

**Chosen:** (a).

**Why:** It fixes the cause (loose citing) without weakening the guardrail. The
validator's injected-fault results (149/150) stay valid as they are. Measured by the
2026-10-22 drift run.

**Revisit if:** The model doesn't follow the rule. Then use (b).

---

## D37 Noise band floor: the eval set's sampling error

**Date:** 2026-10-25

**Context:** INCIDENTS #11. Three identical baseline runs gave σ = 0, a zero-width band.

**Options:** (a) σ = max(run σ, √(p(1−p)/n)); (b) 10 baseline runs; (c) both.

**Chosen:** (a), with p clamped to [1/n, 1−1/n] so p = 1.0 doesn't collapse the floor to
zero again. With n = 15: kg band [0.87, 1.13], rag at 0.80 gives [0.59, 1.01].

**Why:** Standard, free, and honest when runs happen to agree. Re-scoring 2026-10-21 under
it: rag's drop (0.80 → 0.00) is still drift; kg's dip (→ 0.91) is within the band. That
matches the diagnosis, since the dip was validator false positives (#10), not wrong
answers.

**Revisit if:** More probes get added. The floor shrinks with n.

---

## D38 Stable rendering: replay per-entity render choices

**Date:** 2026-10-25

**Context:** INCIDENTS #13. A shared RNG stream meant mutating 15 properties re-worded
133 others.

**Options:**
- (a) Store choices per entity and replay them in later snapshots.
- (b) A per-entity RNG seed.
- (c) Per-entity seeds plus a full regeneration.

**Chosen:** (a).

**Why:** It keeps the 10-16 corpus and the golden set's semantics: recording reproduced
10-16 byte-for-byte. It's also realistic, since partners change numbers, not templates.
(b) would re-roll every doc's layout and deferral and silently invalidate the golden
labels; (c) would discard the measured history.

**Revisit if:** Templates themselves should change over time (a "partner redesign" event).

---

## D39 Logs: JSON files tailed by Grafana Alloy into Loki

**Date:** 2026-10-25

**Options:** (a) Grafana Alloy tails JSON log files. (b) The app pushes to Loki over HTTP.
(Promtail, the classic shipper, has reached end of life; Alloy is its successor.)

**Chosen:** (a). The API, consumer and exporter write JSON lines to
`~/Library/Logs/policyground/*.jsonl`. That path, not the repo, because Docker Desktop
can't bind-mount from `~/Documents` (D15) but can from `~/Library/Logs` (tested).

**Why:** The app knows nothing about the log backend. If Loki is down, logs stay on disk
and Alloy catches up.

**Revisit if:** Services move into containers. Then log to stdout and let Alloy read
Docker's logs.

---

## D40 Dashboard scope: API plus pipeline health

**Date:** 2026-10-25

**Options:** (a) API panels plus consumer lag/events, KG/vector disagreement, newest
snapshot age. (b) API panels only, as planned.

**Chosen:** (a). Skipped DAG runs show up as snapshot age (a skipped night means no new
snapshot), so Grafana needs no access to Airflow's database.

**Why:** M5's goal is "diagnose an M4 incident from the dashboard alone". The M4
staleness incident is visible only through disagreement and snapshot age.

**Revisit if:** The dashboard gets too noisy to use. Split it into "request path" and
"pipeline".

---

## D41 Metric labels: low-cardinality from the start

**Date:** 2026-10-25

**Options:** (a) Reproduce the cardinality trap (property_id as a label), measure, fix.
(b) Do it right from the start.

**Chosen:** (b). Labels only from a closed set: `tenant`, `route`, `outcome`, `reason`,
`direction`, `partition`. IDs (property, request, rate plan) go only into logs and
traces. A test fails if a metric declares any other label.

**Why:** Your call: the trap is well understood, and building it right was preferred over
spending time reproducing it. Consequence: the PLAN M5 incident becomes a description,
not a measurement. Say so if asked.

**Revisit if:** Not expected to change.

---

## D42 Grafana's database role: grafana_ro

**Date:** 2026-10-25

**Options:** (a) A new `grafana_ro` role with SELECT on `eval_runs` and `chunks` only.
(b) Reuse `api_ro`.

**Chosen:** (a).

**Why:** Least privilege. The dashboard can't read the KG or anything added later by
default. It's a fourth role, easy to explain alongside admin, `ingest_rw` and `api_ro`
(D15).

**Revisit if:** The dashboard needs other tables. Grant them explicitly.
