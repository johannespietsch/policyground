---
name: onboard-tenant
description: Onboard a new business area (tenant) into PolicyGround - write its spec.yaml, seed adapter and golden set, then pass the mandatory done-check. Use when asked to add a tenant, business area or policy domain.
---

# Onboard a tenant

A tenant is a business area whose policies PolicyGround answers questions about, for
example hotel partner policies. The core is generic: it reads a tenant's **spec** and calls
its **adapter**. Onboarding means writing exactly these files and nothing else:

```
src/policyground/tenants/<name>/__init__.py   # empty
src/policyground/tenants/<name>/spec.yaml     # data: hierarchy, facts, deadline rules, wording
src/policyground/tenants/<name>/adapter.py    # code: generate, render, golden
```

`src/policyground/tenants/hotels/` is the reference implementation: read its `spec.yaml`
and `adapter.py` first. Its generator, renderer and golden builder live next to it.

## Inputs (from whoever asks you)

1. **Tenant name**: lowercase, `[a-z_]+`, also the directory name.
2. **Domain brief**: the hierarchy (root to leaf), which level questions are about (the
   *subject*), optional options below it (the *variant*), the policy facts, and at least
   one deadline rule ("X days after Y", "N hours before Z").

If the brief is missing something you need, choose something sensible and say what you
chose in your final report. Don't stop and ask.

## Outputs

The three files above. A passing done-check, which writes `data/<name>/kg.json`,
`corpus/<name>/<date>/*.md`, `data/<name>/golden.json` and `data/<name>/eval/run-*.json`,
and appends to `data/<name>/onboarding-attempts.jsonl`. A short report: what you built,
the choices you made, every done-check failure and how you fixed it.

## Rules

- Only add files under `src/policyground/tenants/<name>/`. **Don't edit the core, the
  tests, the done-check, its thresholds, or `hotels`.** If the core can't express what the
  domain needs, stop and report the gap. That's a finding, not a failure.
- Never run `make seed` or `make check-tenant` for `hotels`: its data is a measured record.
- Deterministic: same seed, same `kg.json`, corpus and golden set. Use `random.Random(...)`
  with explicit seeds. Never use the global `random` module or the current time.
- All data is synthetic and fictional: no real companies, people or products.
- Don't push, open PRs, or call external services beyond what the done-check itself does.

## Step 1: spec.yaml

Every key, as the core reads it (`policyground/tenant.py` validates them):

```yaml
tenant: <name>                 # must equal the directory name
levels: [root, ..., leaf]      # >= 2 unique level names, root first; each entity's parent
                               # must be of the previous level
subject: <level>               # the level questions name; matched by fuzzy name, so
                               # subject entities need unique, distinctive names
variant: <level>               # optional; must be the level directly below subject.
                               # Facts set on a variant apply only to that option and override
                               # the subject's (hotels: a non-refundable rate plan)
doc_ids:
  subject: "{id}"              # corpus file name of a subject's document
  other: "{level}-{id}"        # every other level that has a document
facts:                         # every fact key the KG may hold
  <key>:
    type: int|float|time|bool|enum|str
    unit: hours|days|EUR       # optional; amounts and durations are validated by unit
    values: [..]               # enum only
    level: variant             # optional: the fact only exists on variants
    meaning: "..."             # optional but strongly recommended: goes verbatim into the
                               # LLM's fact glossary. Say what the value means.
deadlines:                     # how a deadline follows from facts (validator + scorer)
  - name: <name>
    anchor_date: question      # the date stated in the question
    anchor_time: <time fact>   # optional; omit for date-only deadlines
    anchor_text_hints: [..]    # optional; words marking the anchor-time sentence in docs
    offset: <fact with unit hours|days>
    direction: before|after
chunking:
  keep_together: [<section>, ...]  # "## " sections merged into one chunk (rule + exception)
prompt:
  audience: "..."              # "You answer questions from <audience>."
  subject_noun: "..."          # how to call a subject in text
  variant_noun: "..."          # how to call a variant
```

## Step 2: adapter.py

Three functions. Look at `tenants/hotels/adapter.py` for working versions.

```python
def generate(seed: int, snapshot_date: str) -> dict:
    """kg.json content. Required keys:
    {"tenant": <name>, "seed": seed, "snapshot_date": snapshot_date,
     "entities":     [{"id", "type" (a level), "parent_id" (None for root), "name", "attrs": {}}],
     "policy_facts": [{"entity_type", "entity_id", "key", "value", "valid_from", "version": 1}]}
    Defaults at upper levels, overrides lower down: that inheritance is the point."""

def render(data: dict, chooser) -> tuple[dict[str, str], dict]:
    """({doc_id: markdown}, manifest). doc_id follows spec doc_ids. EVERY random choice
    (wording variant, layout) goes through the chooser, never through random directly:
        chooser.for_entity(doc_id)            # once per document
        chooser.choice("name", options)       # pick one option
        chooser.sample("name", options, k)    # pick k
        chooser.random("name")                # float in [0, 1)
    This keeps unchanged documents identical across snapshots. The manifest is free-form
    per-document metadata (e.g. which docs defer terms to a parent level)."""

def golden(data: dict, manifest: dict, seed: int) -> list[dict]:
    """Golden questions with answers derived from the KG, never from text."""
```

**Document format** (the structural chunker and the citations depend on it):

```markdown
# <Entity name>

<Level> ID: <id> · <parent level>: <parent name> · ...

## <Section>

<prose that states the facts in words, with varied phrasing>
```

Subject documents state their effective policy. Upper levels get their own documents
with their defaults. Like hotels, some subject docs may defer to a parent's "standard
terms", but only for inherited values: an override must always be stated in the doc.

**Golden item format**, at least 10 items, at least 2 of them unanswerable:

```json
{"id": "Q01", "type": "<your label, e.g. plain_deadline>", "subject_id": "<subject entity id>",
 "question": "<natural question that names the subject>",
 "expected": {"kind": "...", ...},
 "evidence_docs": ["<doc_id>", ...],
 "governing": {"docs": ["<doc that states the value>"], "facts": ["kg:<entity_id>:<key>"]},
 "evidence_text": "<exact text that governing doc contains, e.g. '30 days'>"}
```

`expected.kind`, scored deterministically by `policyground/eval/score.py`:
`datetime` ("YYYY-MM-DD HH:MM"), `date` ("YYYY-MM-DD"), `time` ("HH:MM"),
`amount` (number, EUR), `duration` ({"value": N, "unit": "days"|"hours"}),
`phrase` ({"patterns": [regex], "reject": [regex]}), `abstain` (unanswerable: no
subject_id/evidence_text needed, `evidence_docs: []`, `governing: {"docs": [], "facts": []}`).

Unanswerable means asking about something the KG never holds, worded so that it can't
appear anywhere in the corpus. Include deadline questions (a date in the question) and
at least one variant-override question, because those are where systems fail.

## Step 3: the mandatory done-check

```
make check-tenant TENANT=<name>
```

It validates the spec, seeds through your adapter, checks the golden set (evidence_text
must be in the governing doc), loads the KG, compares the SQL resolver with the Python
resolver, ingests the corpus, runs the whole test suite, and runs the LLM eval through
the knowledge-graph route (correct >= 0.8, abstention >= 0.8).

**You're done only when it prints `DONE-CHECK PASSED`.** Not before, and not on your own
judgement. Every run counts as an attempt and is recorded automatically. Read the failure
message, fix *your* files, run it again. Stop after 6 attempts and report what blocks you.

## Report back

1. The tenant, its hierarchy, facts and deadline rule(s), in a few lines.
2. Your choices where the brief was silent.
3. The attempt log (`data/<name>/onboarding-attempts.jsonl`): each failure, its cause, your fix.
4. Anything in the core that got in your way, or this skill didn't tell you.
