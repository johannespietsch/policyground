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
    response = client().messages.parse(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": EFFORT},
        system=SYSTEM,
        messages=[{"role": "user", "content": f"{context}\n\nQuestion: {question}"}],
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
