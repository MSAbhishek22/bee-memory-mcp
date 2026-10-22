# Bee Memory MCP — open-source MCP server for Bee wearable memory

**An additional open-source project (MIT), built during the Amazon Developer Hackathon 2026 window as the companion to BeeBridge.**

Your Bee wearable remembers your conversations. This project makes that memory **queryable by any MCP client** — Alexa+, desktop AI agents, or your own tools — through a small, self-hostable MCP server (Streamable HTTP, protocol **2025-11-25**).

## What it does
- Ingests Bee conversations via the **Bee CLI** (`bee sync`, `bee today`), **Bee sync exports**, or **Bee's MCP server** (`BEE_MCP_URL`).
- Extracts facts, medication, appointments, and to-dos.
- Serves them over MCP tools: `beebridge_ask`, `beebridge_today`, `beebridge_todos`, `beebridge_sync_bee`, `beebridge_ring_simulate`.
- Optional Amazon Bedrock rephrasing for plain-language summaries.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=src uvicorn bee_memory_mcp.server:app --app-dir src --port 8100
curl -s localhost:8100/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"What did the doctor say about my next appointment?"}'
pytest   # tests included
```
Bundled sample Bee exports in `data/bee_sample/` make it runnable with no device; point `BEE_EXPORT_DIR` at a real Bee sync folder to use your own data.

## Why it matters
Ambient memory shouldn't be locked inside one app. By exposing Bee memory over the open MCP standard, any assistant can help a user recall what was said — with the user's data staying on a server they control. Built for accessibility use cases (seniors, ADHD, hearing loss) and reusable by any developer.

## License
MIT — see `LICENSE`.
