import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from bee_memory_mcp.server import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_mcp_initialize_2025_11_25():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2025-11-25"}})
    assert r.json()["result"]["protocolVersion"] == "2025-11-25"


def test_mcp_ask_returns_bee_memory():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "beebridge_ask",
                                             "arguments": {"question": "What medication do I take?"}}})
    assert "Metformin" in r.json()["result"]["content"][0]["text"]


def test_rest_ask():
    r = client.post("/api/ask", json={"question": "What do I need to do today?"})
    assert r.status_code == 200 and r.json()["answer"]
