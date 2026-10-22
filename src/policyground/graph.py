"""Answer graphs.

rag (M1 baseline, kept for comparison): retrieve -> answer. Plain RAG on purpose.
kg  (M2): route -> kg_lookup -> retrieve -> answer -> validate
          -> (done | regenerate, at most MAX_REGENERATE times | abstain).
"""

from __future__ import annotations

import os
from typing import TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

from policyground.kg.lookup import match_property, property_context
from policyground.llm import answer_question, answer_with_facts
from policyground.retrieve import search
from policyground.validate import validate as run_validator

TOP_K = 5
# Retry cap (PLAN M2 trap: uncapped regenerate-on-reject blows up cost per question).
MAX_REGENERATE = int(os.environ.get("POLICYGROUND_MAX_REGENERATE", "1"))
# Second, independent backstop (INCIDENTS #6). LangGraph 1.x's default recursion limit
# is 10007 steps, not 25: without this, a bug in the retry cap could loop ~5000 LLM
# calls on one question. The longest legitimate kg path is 8 steps.
RECURSION_LIMIT = 20


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
    raw_citations: list[str]
    abstain: bool
    input_tokens: int
    output_tokens: int
    attempts: int                 # LLM answer calls made
    validator_problems: list[list[str]]  # one entry per rejected attempt
    validator_warnings: list[str]
    validator_ok: bool
    forced_abstain: bool          # validator rejected every allowed attempt


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
        "raw_citations": result.answer.citations,
        "abstain": result.answer.abstain,
        # Accumulate across regenerate attempts: cost per question is the sum.
        "input_tokens": state.get("input_tokens", 0) + result.input_tokens,
        "output_tokens": state.get("output_tokens", 0) + result.output_tokens,
        "attempts": state.get("attempts", 0) + 1,
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
    rejected = state.get("validator_problems") or []
    return _answer_update(state, answer_with_facts(
        state["question"], state["property_name"],
        [(f["id"], f["text"]) for f in state["facts"]],
        [(c["id"], c["text"]) for c in state["chunks"]],
        feedback=rejected[-1] if rejected else None))


def validate(state: State) -> State:
    v = run_validator(state["question"], state["answer"], state["abstain"],
                      state["raw_citations"], state["facts"], state["chunks"])
    update: State = {"validator_ok": v.ok, "validator_warnings": v.warnings}
    if not v.ok:
        update["validator_problems"] = (state.get("validator_problems") or []) + [v.problems]
    return update


def after_validate(state: State) -> str:
    if state["validator_ok"]:
        return "done"
    if state["attempts"] <= MAX_REGENERATE:
        return "regenerate"
    return "abstain"


def abstain_unvalidated(state: State) -> State:
    """Every allowed attempt failed validation: refuse rather than pass it on."""
    return {"answer": "I can't confirm this from the policy data; please check the property's terms directly.",
            "citations": [], "abstain": True, "forced_abstain": True}


def build_kg():
    g = StateGraph(State)
    g.add_node("route", route)
    g.add_node("abstain_unresolved", abstain_unresolved)
    g.add_node("kg_lookup", kg_lookup)
    g.add_node("retrieve", kg_retrieve)
    g.add_node("answer", kg_answer)
    g.add_node("validate", validate)
    g.add_node("abstain_unvalidated", abstain_unvalidated)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: "kg_lookup" if s["property_id"] else "abstain_unresolved")
    g.add_edge("abstain_unresolved", END)
    g.add_edge("kg_lookup", "retrieve")
    g.add_edge("retrieve", "answer")
    g.add_edge("answer", "validate")
    g.add_conditional_edges("validate", after_validate,
                            {"done": END, "regenerate": "answer", "abstain": "abstain_unvalidated"})
    g.add_edge("abstain_unvalidated", END)
    return g.compile()


def ask(graph, tenant: str, question: str) -> State:
    """Invoke with the step backstop. Hitting it is a bug, not an answer: abstain."""
    try:
        return graph.invoke({"tenant": tenant, "question": question},
                            config={"recursion_limit": RECURSION_LIMIT})
    except GraphRecursionError:
        return {"tenant": tenant, "question": question, "chunks": [], "facts": [],
                "answer": "I can't confirm this from the policy data (step limit reached).",
                "citations": [], "raw_citations": [], "abstain": True, "forced_abstain": True,
                "input_tokens": 0, "output_tokens": 0, "attempts": 0, "recursion_limited": True}


GRAPHS = {"rag": build_rag, "kg": build_kg}
build = build_kg  # what the API serves
