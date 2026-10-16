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
