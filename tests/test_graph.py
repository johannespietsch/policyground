"""The step backstop (INCIDENTS #6) must turn a runaway loop into an abstention."""

from policyground import graph as graph_mod


def test_recursion_limit_becomes_abstention(monkeypatch):
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(graph_mod.State)
    g.add_node("spin", lambda s: {"attempts": s.get("attempts", 0) + 1})
    g.add_edge(START, "spin")
    g.add_conditional_edges("spin", lambda s: "spin" if s["attempts"] < 1000 else END)
    state = graph_mod.ask(g.compile(), "hotels", "q")
    assert state["abstain"] and state["recursion_limited"]
