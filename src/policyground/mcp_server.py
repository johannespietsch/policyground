"""`python -m policyground.mcp_server` — read-only MCP server over stdio (PLAN M6).

Tools:
  list_tenants()                     tenants with a spec, and what each one's subject is
  get_subject_policy(tenant, name)   resolved KG policy for one subject (fuzzy name match, D22),
                                     every fact with the level it was inherited from
  ask_policy(tenant, question)       the full kg graph: cited, validated answer or abstention

Read-only by construction: the KG is read as api_ro (D15), no tool writes anything.

stdio trap (PLAN M6): stdout IS the protocol channel; one stray print() from any library
corrupts the session. Logs go to stderr and a file (obs/logs.py), and every tool call
runs with stdout redirected to stderr as a second guard (tests/test_mcp.py proves it).
"""

from __future__ import annotations

import contextlib
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from policyground import tenant as tenants  # noqa: E402
from policyground.obs import logs, tracing  # noqa: E402

log = logs.setup("mcp")
tracing.setup("mcp")
server = MCPServer(name="policyground", version="0.1.0",
                   instructions="Policy Q&A grounded in a knowledge graph. Read-only. Call list_tenants first.")
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
_graph = None


@contextlib.contextmanager
def _guard(tool: str, **fields):
    """stdout -> stderr for the duration of the call, plus a request id for logs/traces."""
    token = logs.request_id.set(f"mcp-{uuid.uuid4().hex[:12]}")
    try:
        with contextlib.redirect_stdout(sys.stderr):
            logs.event(log, f"tool {tool}", **fields)
            yield logs.request_id.get()
    finally:
        logs.request_id.reset(token)


@server.tool(annotations=READ_ONLY)
def list_tenants() -> list[dict]:
    """Tenants this server can answer for, with their hierarchy and the subject level
    that questions name (e.g. hotels: property; a policy for insurance)."""
    with _guard("list_tenants"):
        out = []
        for name in tenants.known():
            s = tenants.spec(name)
            out.append({"tenant": name, "levels": list(s.levels), "subject": s.subject,
                        "facts": sorted(s.facts)})
        return out


@server.tool(annotations=READ_ONLY)
def get_subject_policy(tenant: str, name: str) -> dict:
    """Resolved policy for one subject (e.g. a hotel property), found by fuzzy name match.
    Each fact says which level it was inherited from (most specific wins). If the name is
    ambiguous or unknown, returns the closest candidates instead."""
    from policyground.kg.lookup import match_subject, subject_context

    with _guard("get_subject_policy", tenant=tenant, name=name):
        m = match_subject(tenant, name)
        if not m.subject_id:
            return {"resolved": False, "reason": m.reason,
                    "candidates": [{"id": i, "name": n, "score": round(s, 2)} for i, n, s in m.candidates]}
        subject_name, facts, docs = subject_context(tenant, m.subject_id)
        return {"resolved": True, "subject_id": m.subject_id, "name": subject_name, "documents": docs,
                "facts": [{"id": f.fact_id, "applies_to": f.entity_id, "key": f.key, "value": f.value,
                           "inherited_from": f"{f.source_type} {f.source_id}"} for f in facts]}


@server.tool(annotations=READ_ONLY)
def ask_policy(tenant: str, question: str) -> dict:
    """Answer a policy question through the knowledge-graph route: resolves the subject,
    retrieves its documents, answers with citations, and validates every date/amount
    against cited evidence. Abstains rather than guesses."""
    global _graph
    from policyground.graph import ask, build

    with _guard("ask_policy", tenant=tenant, question=question) as rid:
        if _graph is None:
            _graph = build()
        state = ask(_graph, tenant, question)
        logs.event(log, "ask", tenant=tenant, subject_id=state.get("subject_id"), abstain=state["abstain"],
                   attempts=state.get("attempts", 0))
        return {"answer": state["answer"], "citations": state["citations"], "abstain": state["abstain"],
                "subject_id": state.get("subject_id"), "request_id": rid}


if __name__ == "__main__":
    server.run("stdio")
