"""Traces to Arize Phoenix over OTLP (PLAN M5).

LangChainInstrumentor covers the LangGraph run (one span per node); AnthropicInstrumentor
covers the LLM call itself (prompt, output, token counts). We call the Anthropic SDK
directly inside nodes (not through LangChain), so both are needed.
Traces contain full prompts: fine for a local Phoenix, a data-handling decision anywhere else.
"""

from __future__ import annotations

import os

_done = False


def setup(service: str) -> None:
    global _done
    if _done or os.environ.get("POLICYGROUND_TRACING", "1") == "0":
        return
    from openinference.instrumentation.anthropic import AnthropicInstrumentor
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import register

    provider = register(project_name="policyground",
                        endpoint=os.environ.get("PHOENIX_OTLP", "http://localhost:6006/v1/traces"),
                        batch=True, set_global_tracer_provider=True, verbose=False)
    LangChainInstrumentor().instrument(tracer_provider=provider)
    AnthropicInstrumentor().instrument(tracer_provider=provider)
    _done = True
