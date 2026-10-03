"""MCP tool servers for the travel agents.

Each module is a standalone FastMCP server that talks stdio, so it can be launched with
``python -m src.mcp_servers.<name>`` by the app's MCP client (see ``src/tools/mcp_client.py``)
or by any other MCP host, such as Claude Code through ``.mcp.json``.

The package is deliberately not called ``mcp``: a local ``mcp`` package would shadow the
PyPI ``mcp`` SDK that these servers import.
"""
