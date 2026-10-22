"""Client for Bee's own MCP server.

If BEE_MCP_URL is set (Bee exposes conversation data over MCP), BeeBridge
can query Bee directly instead of reading sync files. This is the same
MCP/JSON-RPC wire format BeeBridge's own Alexa+ server speaks.
"""
from __future__ import annotations

import os

import httpx


class BeeMcpClient:
    def __init__(self, url: str | None = None):
        self.url = url or os.environ.get("BEE_MCP_URL", "")
        self._id = 0

    def available(self) -> bool:
        return bool(self.url)

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        if not self.available():
            raise RuntimeError("BEE_MCP_URL is not set")
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments or {}}}
        resp = httpx.post(self.url, json=payload, timeout=30,
                          headers={"Accept": "application/json, text/event-stream"})
        resp.raise_for_status()
        return resp.json()
