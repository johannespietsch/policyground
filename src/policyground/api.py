"""`POST /ask {tenant, question}` -> cited answer.  `GET /metrics` for Prometheus.

Observability (PLAN M5): one JSON log line per question (request_id, property_id,
route, outcome, tokens, validator problems), Prometheus metrics with low-cardinality
labels only (D41), and a Phoenix trace per question tagged with the same request_id.
"""

from __future__ import annotations

import time
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from prometheus_client import make_asgi_app
from pydantic import BaseModel

load_dotenv()

from openinference.instrumentation import using_attributes  # noqa: E402

from policyground.graph import ask, build  # noqa: E402  (needs env loaded first)
from policyground.llm import PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK  # noqa: E402
from policyground.obs import logs, metrics, tracing  # noqa: E402

log = logs.setup("api")
tracing.setup("api")
metrics.init_series("api")
app = FastAPI(title="PolicyGround")
app.mount("/metrics", make_asgi_app())
graph = build()


@app.middleware("http")
async def request_ids(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = logs.request_id.set(rid)
    try:
        response = await call_next(request)
    finally:
        logs.request_id.reset(token)
    response.headers["x-request-id"] = rid
    return response


class AskRequest(BaseModel):
    tenant: str
    question: str


class AskResponse(BaseModel):
    answer: str
    citations: list[str]
    abstain: bool
    input_tokens: int
    output_tokens: int
    request_id: str


def _abstain_reason(state) -> str | None:
    if not state["abstain"]:
        return None
    if state.get("recursion_limited"):
        return "step_limit"
    if state.get("forced_abstain"):
        return "validator"
    if not state.get("property_id"):
        return "unresolved_property"
    return "model"


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest) -> AskResponse:
    rid = logs.request_id.get()
    t0 = time.perf_counter()
    try:
        with using_attributes(session_id=rid, metadata={"request_id": rid, "tenant": req.tenant}):
            state = ask(graph, req.tenant, req.question)
    except Exception:
        metrics.REQUESTS.labels(req.tenant, "kg", "error").inc()
        log.exception("ask failed", extra={"fields": {"tenant": req.tenant}})
        raise
    seconds = time.perf_counter() - t0

    route = "kg" if state.get("property_id") else "unresolved"
    reason = _abstain_reason(state)
    tin, tout = state.get("input_tokens", 0), state.get("output_tokens", 0)
    cost = (tin * PRICE_IN_PER_MTOK + tout * PRICE_OUT_PER_MTOK) / 1e6
    rejected = len(state.get("validator_problems") or [])

    metrics.REQUESTS.labels(req.tenant, route, "abstained" if reason else "answered").inc()
    metrics.LATENCY.labels(req.tenant, route).observe(seconds)
    metrics.TOKENS.labels(req.tenant, "in").inc(tin)
    metrics.TOKENS.labels(req.tenant, "out").inc(tout)
    metrics.COST.labels(req.tenant).inc(cost)
    metrics.LLM_CALLS.labels(req.tenant).inc(state.get("attempts", 0))
    metrics.VALIDATOR_REJECTIONS.labels(req.tenant).inc(rejected)
    if reason:
        metrics.ABSTENTIONS.labels(req.tenant, reason).inc()

    logs.event(log, "ask", tenant=req.tenant, question=req.question,
               property_id=state.get("property_id"), route=route,
               outcome="abstained" if reason else "answered", abstain_reason=reason,
               attempts=state.get("attempts", 0), validator_problems=state.get("validator_problems") or [],
               citations=state.get("citations", []), input_tokens=tin, output_tokens=tout,
               cost_usd=round(cost, 6), latency_s=round(seconds, 3))
    return AskResponse(answer=state["answer"], citations=state["citations"], abstain=state["abstain"],
                       input_tokens=tin, output_tokens=tout, request_id=rid)
