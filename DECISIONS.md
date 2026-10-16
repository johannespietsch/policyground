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
