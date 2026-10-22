"""Alexa+ Agent Skill — Lambda handler (backup / classic Alexa path).

The primary Alexa+ integration is the MCP server in mcp_server.py.
This handler exposes the same BeeBridge memory to a classic Alexa
skill / Agent Skill runtime: intents map 1:1 to service.ask() calls.

Deploy: zip this file with beebridge/ on the Lambda path, set
BEEBRIDGE_API_URL to your hosted BeeBridge /api/ask endpoint, or run
in-process when the Lambda bundles the full service.
"""
from __future__ import annotations

import json
import os

import urllib.request


def _ask_beebridge(question: str) -> str:
    url = os.environ.get("BEEBRIDGE_API_URL")
    if url:
        req = urllib.request.Request(
            url.rstrip("/") + "/api/ask",
            data=json.dumps({"question": question}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["answer"]
    # in-process fallback (Lambda bundles the app)
    from ..core.service import BeeBridgeService
    from ..core.store import MemoryStore
    svc = BeeBridgeService(store=MemoryStore(os.environ.get("BEEBRIDGE_DB", ":memory:")))
    svc.sync_from_bee()
    return svc.ask(question)["answer"]


def _response(text: str, end: bool = True) -> dict:
    return {"version": "1.0", "response": {
        "outputSpeech": {"type": "PlainText", "text": text},
        "shouldEndSession": end}}


INTENT_QUESTIONS = {
    "DoctorIntent": "What did the doctor say about my appointment and medication?",
    "MedicationIntent": "What medication do I need to take?",
    "TodayIntent": "What do I need to do today?",
    "FamilyIntent": "What did Mom say in our last family conversation?",
}


def handler(event, context=None):
    req = event.get("request", {})
    rtype = req.get("type")
    if rtype == "LaunchRequest":
        return _response("Welcome to BeeBridge. Ask me what the doctor said, "
                         "what medication to take, or what you need to do today.", end=False)
    if rtype == "IntentRequest":
        intent = req.get("intent", {}).get("name", "")
        if intent == "AMAZON.StopIntent" or intent == "AMAZON.CancelIntent":
            return _response("Goodbye. BeeBridge will keep listening with your Bee, with your permission.")
        slots = req.get("intent", {}).get("slots", {})
        free = slots.get("question", {}).get("value")
        question = free or INTENT_QUESTIONS.get(intent, "What do I need to do today?")
        return _response(_ask_beebridge(question))
    return _response("BeeBridge is ready.")
