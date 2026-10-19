"""The single LLM call (D7) with structured output (D10).

The output is untrusted: in M2 a deterministic validator checks every date and
amount in `answer` against the KG / cited chunks before it reaches a user.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic
from pydantic import BaseModel

MODEL = "claude-haiku-5-5"
# USD per million tokens, for prompts up to 100K tokens (cached pricing table, 2026-10-06).
PRICE_IN_PER_MTOK = 0.10
PRICE_OUT_PER_MTOK = 0.50
# Explicit, because Haiku 5.5's default is "medium" too; changing it is a cost lever (M2).
EFFORT = "medium"

SYSTEM = """You answer questions from customer-support agents about hotel policies.

Use ONLY the policy excerpts provided in the user message. Each excerpt has an ID.
- Cite the ID of every excerpt your answer relies on.
- If the excerpts don't contain enough information to answer, set abstain to true \
and say briefly what is missing. Never guess, and never use outside knowledge.
- When the question asks for a deadline, give the exact date and time it falls on.
- Keep the answer to one or two sentences."""


class Answer(BaseModel):
    answer: str
    citations: list[str]
    abstain: bool


@dataclass
class LLMResult:
    answer: Answer
    input_tokens: int
    output_tokens: int
    stop_reason: str


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY; only this process has it
    return _client


def answer_question(question: str, excerpts: list[tuple[str, str]]) -> LLMResult:
    context = "\n\n".join(f'<excerpt id="{cid}">\n{text}\n</excerpt>' for cid, text in excerpts)
    return _call(SYSTEM, f"{context}\n\nQuestion: {question}")

SYSTEM_KG = """You answer questions from customer-support agents about hotel policies.

You get two kinds of evidence in the user message, each with an ID:
- <fact> elements: the authoritative policy from the knowledge graph, already resolved
  for this property (most specific level wins). Facts on a rate plan apply only to
  bookings on that rate plan and override the property's facts for them.
- <excerpt> elements: policy text, for wording and context. If an excerpt disagrees
  with a fact, the fact wins.

Fact keys:
- cancel_window_hours: free cancellation until this many hours before check-in on the
  arrival day (check-in time = check_in_time).
- late_cancel_fee: what is charged after the window (first_night, full_stay, 50_percent).
- refundable = false on a rate plan: that booking can never be cancelled free of charge.
- pet_fee_eur: per night, only relevant if pets_allowed is true.

Rules:
- Use ONLY the facts and excerpts given. Never guess or use outside knowledge.
- Cite the ID of every fact and excerpt your answer relies on.
- If they don't contain the information asked for, set abstain to true and say what
  is missing.
- When the question asks for a deadline, compute and state the exact date and time.
- Keep the answer to one or two sentences."""


def answer_with_facts(question: str, property_name: str, facts: list[tuple[str, str]],
                      excerpts: list[tuple[str, str]]) -> LLMResult:
    """facts: (fact_id, rendered "key = value (applies to ...)") pairs."""
    fact_xml = "\n".join(f'<fact id="{fid}">{text}</fact>' for fid, text in facts)
    excerpt_xml = "\n\n".join(f'<excerpt id="{cid}">\n{text}\n</excerpt>' for cid, text in excerpts)
    content = (f"Property: {property_name}\n\n<facts>\n{fact_xml}\n</facts>\n\n"
               f"<excerpts>\n{excerpt_xml}\n</excerpts>\n\nQuestion: {question}")
    return _call(SYSTEM_KG, content)


def _call(system: str, content: str) -> LLMResult:
    response = client().messages.parse(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": EFFORT},
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=Answer,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        # No server-side fallback on Haiku 5.5; treat as an abstention, keep the reason.
        parsed = Answer(answer=f"(no answer: stop_reason={response.stop_reason})",
                        citations=[], abstain=True)
    else:
        parsed = response.parsed_output
    return LLMResult(parsed, response.usage.input_tokens, response.usage.output_tokens,
                     response.stop_reason)
