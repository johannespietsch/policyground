"""Traces to Arize Phoenix over OTLP (PLAN M5).

LangChainInstrumentor covers the LangGraph run (one span per node); AnthropicInstrumentor
covers the LLM call itself (prompt, output, token counts). We call the Anthropic SDK
directly inside nodes (not through LangChain), so both are needed. FastAPI (0.14x) adds
its own request spans as soon as a tracer provider exists.

The sampler drops two kinds of span at creation (INCIDENTS #14):
  - Prometheus scrapes of /metrics: one trace every 15s, burying real requests.
  - the inner `anthropic.messages.create` span that `messages.parse` makes; both are
    LLM spans carrying the same token counts, so Phoenix totals would count every call twice.

Traces contain full prompts: fine for a local Phoenix, a data-handling decision anywhere else.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.trace.sampling import Decision, ParentBased, Sampler, SamplingResult

_done = False


class _DropNoise(Sampler):
    def should_sample(self, parent_context, trace_id, name, kind=None, attributes=None, links=None,
                      trace_state=None):
        path = (attributes or {}).get("url.path") or (attributes or {}).get("http.target") or ""
        if str(path).startswith("/metrics") or name.startswith("GET /metrics"):
            return SamplingResult(Decision.DROP)
        parent = trace.get_current_span(parent_context)
        if name == "anthropic.messages.create" and getattr(parent, "name", "") == "messages.parse":
            return SamplingResult(Decision.DROP)
        return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes)

    def get_description(self) -> str:
        return "DropNoise(/metrics scrapes, duplicate LLM span)"


class _Sampler(ParentBased):
    """ParentBased keeps whole traces together; the noise check also runs for child spans
    (the duplicate LLM span is a child), so delegate every decision to _DropNoise first."""

    def __init__(self):
        super().__init__(root=_DropNoise())
        self._noise = _DropNoise()

    def should_sample(self, parent_context, trace_id, name, *args, **kwargs):
        result = self._noise.should_sample(parent_context, trace_id, name, *args, **kwargs)
        if result.decision == Decision.DROP:
            return result
        return super().should_sample(parent_context, trace_id, name, *args, **kwargs)


def setup(service: str) -> None:
    global _done
    if _done or os.environ.get("POLICYGROUND_TRACING", "1") == "0":
        return
    from openinference.instrumentation.anthropic import AnthropicInstrumentor
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import PROJECT_NAME, BatchSpanProcessor, Resource, TracerProvider

    endpoint = os.environ.get("PHOENIX_OTLP", "http://localhost:6006/v1/traces")
    provider = TracerProvider(resource=Resource({PROJECT_NAME: "policyground", "service.name": service}),
                              sampler=_Sampler(), verbose=False)
    provider.add_span_processor(BatchSpanProcessor(endpoint=endpoint))
    trace.set_tracer_provider(provider)
    LangChainInstrumentor().instrument(tracer_provider=provider)
    AnthropicInstrumentor().instrument(tracer_provider=provider)
    _done = True
