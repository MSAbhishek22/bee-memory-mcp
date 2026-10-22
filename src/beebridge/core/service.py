"""BeeBridge service: ingest Bee conversations, answer questions about them."""
from __future__ import annotations

import re

from ..aws.bedrock import BedrockSummarizer
from ..bee.client import BeeClient
from .extractor import extract
from .models import Conversation
from .store import MemoryStore


class BeeBridgeService:
    def __init__(self, store: MemoryStore, bee: BeeClient | None = None,
                 summarizer: BedrockSummarizer | None = None):
        self.store = store
        self.bee = bee or BeeClient()
        self.summarizer = summarizer or BedrockSummarizer()

    # -- ingestion -------------------------------------------------------
    def sync_from_bee(self) -> dict:
        note = self.bee.sync()
        convs = self.bee.load_conversations()
        added = 0
        for conv in convs:
            if not self.store.get_conversation(conv.id):
                added += 1
            self.ingest(conv)
        return {"sync_note": note, "conversations_seen": len(convs),
                "conversations_new": added, "counts": self.store.counts()}

    def ingest(self, conv: Conversation) -> dict:
        self.store.add_conversation(conv)
        facts, todos = extract(conv)
        for f in facts:
            self.store.add_fact(f)
        for t in todos:
            self.store.add_todo(t)
        return {"conversation_id": conv.id, "facts": len(facts), "todos": len(todos)}

    # -- queries -----------------------------------------------------------
    def today_summary(self) -> dict:
        todos = self.store.list_todos()
        convs = self.store.list_conversations(10)
        alerts = self.store.list_alerts(5)
        lines = []
        if todos:
            lines.append("Today you have: " + "; ".join(
                t.text + (f" ({t.due_text})" if t.due_text else "") for t in todos[:6]) + ".")
        if convs:
            lines.append(f"You had {len(convs)} conversation(s) captured by Bee, most recently: {convs[0].title}.")
        if alerts:
            lines.append("Latest alert: " + alerts[0].text)
        raw = " ".join(lines)
        # Only let Bedrock rephrase when AWS is actually configured; offline we
        # keep the clear, deterministic wording (better for senior users anyway).
        import os
        summary = self.summarizer.summarize(raw) if (lines and os.environ.get("AWS_ACCESS_KEY_ID")) \
            else (raw or "Nothing captured yet today.")
        return {"summary": summary, "todos": [t.model_dump(mode="json") for t in todos],
                "conversations": [c.model_dump(mode="json") for c in convs],
                "alerts": [a.model_dump(mode="json") for a in alerts]}

    def ask(self, question: str) -> dict:
        """Answer a natural question from Bee memory. This is what Alexa+ calls."""
        q = question.lower()

        wants_meds = any(k in q for k in ("medication", "medicine", "pill", "tablet", "dose"))
        wants_doctor = any(k in q for k in ("doctor", "dr.", "appointment", "clinic"))

        if wants_meds and not wants_doctor:
            meds = [t for t in self.store.list_todos(include_done=True) if t.kind.value == "medication"]
            if meds:
                return {"answer": "About your medication: " + "; ".join(t.text for t in meds),
                        "sources": [t.conversation_id for t in meds]}
            return {"answer": "I don't have any medication notes from your Bee conversations yet.", "sources": []}

        if wants_doctor:
            convs = self.store.search_conversations("doctor appointment")
            found = self.store.search_facts(question)
            health = [f for f in self.store.list_facts() if f.category == "health"]
            seen, facts = set(), []
            for f in health + found:  # health facts lead — that's what "doctor said" means
                if f.id not in seen:
                    seen.add(f.id)
                    facts.append(f)
            facts = facts[:3]
            todos = [t for t in self.store.list_todos(include_done=True) if t.kind.value == "appointment"]
            parts = []
            if todos:
                parts.append("Appointments: " + "; ".join(
                    t.text + (f" ({t.due_text})" if t.due_text else "") for t in todos))
            if facts:
                parts.append("From the doctor: " + " ".join(f.text for f in facts))
            if wants_meds:
                meds = [t for t in self.store.list_todos(include_done=True) if t.kind.value == "medication"]
                if meds:
                    parts.append("Medication: " + "; ".join(t.text for t in meds))
            if not parts and convs:
                parts.append(self.summarizer.summarize(convs[0].transcript))
            if parts:
                return {"answer": ". ".join(parts), "sources": [c.id for c in convs]}
            return {"answer": "I couldn't find a doctor conversation in your Bee memory yet.", "sources": []}

        if any(k in q for k in ("today", "to do", "todo", "need to do", "tasks", "schedule")):
            s = self.today_summary()
            return {"answer": s["summary"], "sources": [c["id"] for c in s["conversations"]]}

        if "mom" in q or "mother" in q or "family" in q or "daughter" in q or "son" in q:
            term = "Mom" if ("mom" in q or "mother" in q) else "family"
            convs = self.store.search_conversations(term)
            if not convs:
                convs = [c for c in self.store.list_conversations(50)
                         if term.lower() in c.title.lower()
                         or any(term.lower() in p.lower() for p in c.participants)]
            pick = convs
            if pick:
                return {"answer": f"From '{pick[0].title}': " + self.summarizer.summarize(pick[0].transcript),
                        "sources": [pick[0].id]}
            return {"answer": "I couldn't find a family conversation about that in your Bee memory.", "sources": []}

        # general search
        convs = self.store.search_conversations(question)
        facts = self.store.search_facts(question)
        if facts:
            return {"answer": " ".join(f.text for f in facts), "sources": [f.conversation_id for f in facts]}
        if convs:
            return {"answer": f"From '{convs[0].title}': " + self.summarizer.summarize(convs[0].transcript),
                    "sources": [convs[0].id]}
        return {"answer": "I couldn't find that in the conversations your Bee captured. "
                          "Try asking about your doctor, your medication, or what you need to do today.",
                "sources": []}
