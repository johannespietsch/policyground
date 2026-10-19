"""Answer graphs.

rag (M1 baseline, kept for comparison): retrieve -> answer. Plain RAG on purpose.
kg  (M2): route -> kg_lookup -> retrieve -> answer. Validate/regenerate/abstain
          is added next (PLAN M2).
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from policyground.kg.lookup import match_property, property_context
from policyground.llm import answer_question, answer_with_facts
from policyground.retrieve import search

TOP_K = 5


class State(TypedDict, total=False):
    tenant: str
    question: str
    property_id: str | None
    property_name: str
    match_reason: str
    facts: list[dict]
    lineage_docs: list[str]
    chunks: list[dict]
    answer: str
    citations: list[str]
    abstain: bool
    input_tokens: int
    output_tokens: int


# ---- shared nodes

def _chunks(hits) -> list[dict]:
    return [{"id": h.chunk_id, "text": h.text, "distance": h.distance} for h in hits]


def _known_ids(state: State) -> set[str]:
    return {c["id"] for c in state.get("chunks", [])} | {f["id"] for f in state.get("facts", [])}


def _answer_update(state: State, result) -> State:
    known = _known_ids(state)
    return {
        "answer": result.answer.answer,
        # Drop citations to evidence we never showed the model (invented IDs).
        "citations": [c for c in result.answer.citations if c in known],
        "abstain": result.answer.abstain,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }


# ---- rag graph (M1)

def rag_retrieve(state: State) -> State:
    return {"chunks": _chunks(search(state["tenant"], state["question"], k=TOP_K))}


def rag_answer(state: State) -> State:
    return _answer_update(state, answer_question(
        state["question"], [(c["id"], c["text"]) for c in state["chunks"]]))


def build_rag():
    g = StateGraph(State)
    g.add_node("retrieve", rag_retrieve)
    g.add_node("answer", rag_answer)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "answer")
    g.add_edge("answer", END)
    return g.compile()


# ---- kg graph (M2)

def route(state: State) -> State:
    m = match_property(state["tenant"], state["question"])
    return {"property_id": m.property_id, "match_reason": m.reason}


def abstain_unresolved(state: State) -> State:
    """No (unique) property: ask rather than guess. No LLM call."""
    return {"answer": f"Which property do you mean? ({state['match_reason']})",
            "citations": [], "abstain": True, "chunks": [], "facts": [],
            "input_tokens": 0, "output_tokens": 0}


def kg_lookup(state: State) -> State:
    name, facts, lineage = property_context(state["tenant"], state["property_id"])
    rendered = []
    for f in facts:
        scope = "this property" if f.entity_id == state["property_id"] else f"rate plan {f.entity_id}"
        rendered.append({"id": f.fact_id, "entity_id": f.entity_id, "key": f.key, "value": f.value,
                         "text": f"{f.key} = {f.value} (applies to {scope}; set at {f.source_type} level)"})
    return {"property_name": name, "facts": rendered, "lineage_docs": lineage}


def kg_retrieve(state: State) -> State:
    hits = search(state["tenant"], state["question"], k=TOP_K, doc_ids=state["lineage_docs"])
    return {"chunks": _chunks(hits)}


def kg_answer(state: State) -> State:
    return _answer_update(state, answer_with_facts(
        state["question"], state["property_name"],
        [(f["id"], f["text"]) for f in state["facts"]],
        [(c["id"], c["text"]) for c in state["chunks"]]))


def build_kg():
    g = StateGraph(State)
    g.add_node("route", route)
    g.add_node("abstain_unresolved", abstain_unresolved)
    g.add_node("kg_lookup", kg_lookup)
    g.add_node("retrieve", kg_retrieve)
    g.add_node("answer", kg_answer)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: "kg_lookup" if s["property_id"] else "abstain_unresolved")
    g.add_edge("abstain_unresolved", END)
    g.add_edge("kg_lookup", "retrieve")
    g.add_edge("retrieve", "answer")
    g.add_edge("answer", END)
    return g.compile()


GRAPHS = {"rag": build_rag, "kg": build_kg}
build = build_kg  # what the API serves
