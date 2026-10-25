"""The MCP server over a real stdio transport (PLAN M6), including the stdout trap."""

import asyncio
import json
import sys

import psycopg
import pytest

from policyground.db import connect

try:
    connect("api_ro").close()
except psycopg.OperationalError:
    pytest.skip("postgres not running (make up)", allow_module_level=True)

from mcp import Client, StdioServerParameters  # noqa: E402

PARAMS = StdioServerParameters(command=sys.executable, args=["-m", "policyground.mcp_server"],
                               env={"POLICYGROUND_TRACING": "0", "PATH": "/usr/bin:/bin"})


def _text(result):
    """Tool output. MCP SDK 2.x: a list return arrives as structured {"result": [...]};
    a dict return as JSON text content."""
    if result.is_error:
        raise AssertionError(f"tool error: {result.content[0].text}")
    sc = result.structured_content
    if sc is not None:
        return sc["result"] if set(sc) == {"result"} else sc
    return json.loads(result.content[0].text)


def run(coro):
    return asyncio.run(coro)


def test_tools_are_listed_and_read_only():
    async def go():
        async with Client(PARAMS) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            assert set(tools) == {"list_tenants", "get_subject_policy", "ask_policy"}
            assert all(t.annotations.read_only_hint for t in tools.values())
    run(go())


def test_get_subject_policy_resolves_and_survives_stdout_noise(monkeypatch):
    async def go():
        async with Client(PARAMS) as c:
            tenants = _text(await c.call_tool("list_tenants", {}))
            assert any(t["tenant"] == "hotels" for t in tenants)
            # The policy tool imports and runs code that is free to print(); the session
            # must survive (stdout is redirected to stderr inside every tool call).
            r = _text(await c.call_tool("get_subject_policy",
                                        {"tenant": "hotels", "name": "Meridian Urban Munich Central"}))
            assert r["resolved"] and r["subject_id"] == "P042"
            assert any(f["key"] == "cancel_window_hours" for f in r["facts"])
            # A second call on the same session proves the transport wasn't corrupted.
            r2 = _text(await c.call_tool("get_subject_policy", {"tenant": "hotels", "name": "the Solstice hotel"}))
            assert r2["resolved"] is False and r2["candidates"]
    run(go())


NOISY = StdioServerParameters(command=sys.executable, args=["tests/fixtures/noisy_mcp_server.py"],
                              env={"POLICYGROUND_TRACING": "0", "PATH": "/usr/bin:/bin"})


def test_stdout_trap_guarded_tool_survives():
    """PLAN M6 trap: the guarded tool prints and the session carries on."""
    async def go():
        async with Client(NOISY, read_timeout_seconds=10) as c:
            assert _text(await c.call_tool("guarded", {}))["ok"]
            assert _text(await c.call_tool("guarded", {}))["ok"]  # same session, still healthy
    run(go())


def test_stdout_trap_junk_line_is_skipped_by_this_client():
    """A whole junk line: SDK 2.x's client logs a parse error and skips it. Survivable
    with this client; older or stricter clients may not be as forgiving."""
    async def go():
        async with Client(NOISY, read_timeout_seconds=10) as c:
            return _text(await c.call_tool("unguarded_line", {}))["ok"]
    assert run(go())
