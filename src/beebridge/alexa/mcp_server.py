"""Alexa+ integration: BeeBridge as a self-hosted MCP server.

Implements the Model Context Protocol over **Streamable HTTP**
(spec revision **2025-11-25**, the minimum Alexa+ requires):

  POST /mcp   JSON-RPC 2.0: initialize, ping, tools/list, tools/call,
              notifications/initialized
  GET  /mcp   405 (this server is stateless; no server-initiated stream)

Alexa+ (or any MCP client, e.g. the Bee MCP tooling) connects to /mcp,
negotiates protocolVersion 2025-11-25, and calls:

  beebridge_ask            — answer a question from Bee memory
  beebridge_today          — today's summary, todos, alerts
  beebridge_todos          — open todos extracted from Bee conversations
  beebridge_sync_bee       — run Bee sync + ingest new conversations
  beebridge_ring_simulate  — fire a Ring simulator event (demo/testing)
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..core.service import BeeBridgeService
from ..ring.simulator import RingEvent, handle_ring_event

PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "beebridge", "title": "BeeBridge — Memory Companion for Seniors", "version": "0.1.0"}

TOOLS = [
    {"name": "beebridge_ask",
     "description": "Answer a natural-language question using conversations captured by the user's Bee wearable (doctor instructions, family updates, medication, appointments).",
     "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}},
    {"name": "beebridge_today",
     "description": "Get today's BeeBridge summary: open todos, recent Bee conversations, and Ring alerts, in senior-friendly language.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "beebridge_todos",
     "description": "List open todos BeeBridge extracted from Bee conversations (medication, appointments, shopping, calls, deliveries).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "beebridge_sync_bee",
     "description": "Sync with Bee (bee CLI / Bee exports) and ingest any new conversations into BeeBridge memory.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "beebridge_ring_simulate",
     "description": "Simulate a Ring event (doorbell_press, motion, package_delivery, person_detected) and return the resulting BeeBridge alert.",
     "inputSchema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["doorbell_press", "motion", "package_delivery", "person_detected"]}},
        "required": ["kind"]}},
]


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _text(payload) -> dict:
    import json
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}], "isError": False}


def build_mcp_router(service: BeeBridgeService) -> APIRouter:
    router = APIRouter()

    @router.get("/mcp")
    async def mcp_get():
        return JSONResponse({"error": "BeeBridge MCP is stateless; POST JSON-RPC to /mcp"},
                            status_code=405)

    @router.post("/mcp")
    async def mcp_post(request: Request):
        body = await request.json()
        method = body.get("method", "")
        req_id = body.get("id")
        params = body.get("params") or {}

        # notifications have no id and expect no body
        if req_id is None:
            return JSONResponse(status_code=202, content={})

        if method == "initialize":
            requested = (params.get("protocolVersion") or PROTOCOL_VERSION)
            version = requested if requested <= PROTOCOL_VERSION else PROTOCOL_VERSION
            return _result(req_id, {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": "BeeBridge answers questions from the user's Bee-captured "
                                  "conversations. Use beebridge_ask for free questions, "
                                  "beebridge_today for a daily summary."})
        if method == "ping":
            return _result(req_id, {})
        if method == "tools/list":
            return _result(req_id, {"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                if name == "beebridge_ask":
                    return _result(req_id, _text(service.ask(args.get("question", ""))))
                if name == "beebridge_today":
                    return _result(req_id, _text(service.today_summary()))
                if name == "beebridge_todos":
                    return _result(req_id, _text([t.model_dump(mode="json") for t in service.store.list_todos()]))
                if name == "beebridge_sync_bee":
                    return _result(req_id, _text(service.sync_from_bee()))
                if name == "beebridge_ring_simulate":
                    alert = handle_ring_event(service.store, RingEvent(kind=args.get("kind", "motion")))
                    return _result(req_id, _text(alert.model_dump(mode="json")))
                return _error(req_id, -32602, f"Unknown tool: {name}")
            except Exception as exc:  # tool errors go back as isError content per MCP
                return _result(req_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        return _error(req_id, -32601, f"Method not found: {method}")

    return router
