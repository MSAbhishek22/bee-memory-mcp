"""Bee Memory MCP — standalone open-source MCP server for Bee wearable memory.

Turns Bee conversations (Bee CLI / Bee sync exports / Bee MCP) into a
queryable memory that ANY MCP client can use — Alexa+, desktop agents,
or your own tooling. This is the open-source companion project to
BeeBridge (Amazon Developer Hackathon 2026).

Run:  uvicorn bee_memory_mcp.server:app --app-dir src --port 8100
MCP:  POST /mcp   (Streamable HTTP, protocol 2025-11-25)
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel

from beebridge.alexa.mcp_server import build_mcp_router
from beebridge.bee.client import BeeClient
from beebridge.core.service import BeeBridgeService
from beebridge.core.store import MemoryStore

store = MemoryStore(os.environ.get("BEE_MEMORY_DB", ":memory:"))
service = BeeBridgeService(store=store, bee=BeeClient())
service.sync_from_bee()

app = FastAPI(title="Bee Memory MCP", version="0.1.0")
app.include_router(build_mcp_router(service))


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok", "counts": store.counts()}


@app.post("/api/ask")
def ask(req: AskRequest):
    return service.ask(req.question)


@app.get("/api/today")
def today():
    return service.today_summary()
