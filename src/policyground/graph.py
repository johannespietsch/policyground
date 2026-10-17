"""M1 answer graph: retrieve -> answer. Plain RAG on purpose: the "before" picture.

M2 adds route -> kg_lookup and validate -> (regenerate <= 1 | abstain).
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from policyground.llm import answer_question
from policyground.retrieve import search

TOP_K = 5


class State(TypedDict, total=False):
    tenant: str
    question: str
    chunks: list[dict]
    answer: str
    citations: list[str]
    abstain: bool
    input_tokens: int
    output_tokens: int


def retrieve(state: State) -> State:
    hits = search(state["tenant"], state["question"], k=TOP_K)
    return {"chunks": [{"id": h.chunk_id, "text": h.text, "distance": h.distance} for h in hits]}


def answer(state: State) -> State:
    result = answer_question(state["question"], [(c["id"], c["text"]) for c in state["chunks"]])
    retrieved = {c["id"] for c in state["chunks"]}
    return {
        "answer": result.answer.answer,
        # Drop citations to excerpts we never showed the model (invented IDs).
        "citations": [c for c in result.answer.citations if c in retrieved],
        "abstain": result.answer.abstain,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }


def build():
    g = StateGraph(State)
    g.add_node("retrieve", retrieve)
    g.add_node("answer", answer)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "answer")
    g.add_edge("answer", END)
    return g.compile()
