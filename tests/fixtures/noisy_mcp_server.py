"""Test-only MCP server for the PLAN M6 stdio trap: one tool prints to stdout unguarded,
one prints inside the same guard policyground.mcp_server uses."""

import sys

from mcp.server.mcpserver import MCPServer

from policyground.mcp_server import _guard

server = MCPServer(name="noisy")


@server.tool()
def unguarded_line() -> dict:
    print("progress: 50%", flush=True)  # a whole junk line on the protocol channel
    return {"ok": True}



@server.tool()
def guarded() -> dict:
    with _guard("guarded"):
        print("progress: 50% ... a library chatting on stdout")  # redirected to stderr
    return {"ok": True}


if __name__ == "__main__":
    server.run("stdio")
