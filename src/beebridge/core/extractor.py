"""Turn a raw conversation transcript into facts + actionable todos.

Deliberately rule-based and deterministic so the demo and tests work
offline with no LLM. When AWS Bedrock is configured, the Bedrock
summarizer (beebridge.aws.bedrock) refines the *summary wording* —
extraction itself never depends on a network call.
"""
from __future__ import annotations

import hashlib
import re

from .models import Conversation, Fact, Todo, TodoKind

_MED_PATTERNS = [
    re.compile(r"\b(?:take|taking)\s+(?:your\s+|the\s+)?([A-Z][a-z]+(?:\s+[A-Z])?(?:\s+\d+\s?mg)?)", re.I),
    re.compile(r"\b([A-Z][a-z]+)\s+(\d+\s?mg)\b"),
]
_DUE_RE = re.compile(
    r"\b(today|tonight|tomorrow(?:\s+(?:morning|afternoon|evening))?|"
    r"(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"(?:\s+(?:morning|afternoon|evening))?(?:\s+at\s+\d{1,2}(?::\d{2})?\s?(?:am|pm))?|"
    r"at\s+\d{1,2}(?::\d{2})?\s?(?:am|pm)|"
    r"in\s+\d+\s+(?:days?|weeks?))\b", re.I)
_APPT_NEXT_RE = re.compile(r"next appointment is\b", re.I)
_TODO_CUES = [
    (re.compile(r"\b(?:pick up|buy|get)\s+(.+?)(?:\.|,| and | before |$)", re.I), TodoKind.SHOPPING),
    (re.compile(r"\b(?:call|phone)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.I), TodoKind.CALL),
    (re.compile(r"\bappointment\s+(?:with\s+)?(.+?)(?:\.|,| on | at |$)", re.I), TodoKind.APPOINTMENT),
    (re.compile(r"\b(?:see|visit)\s+(Dr\.?\s+[A-Z][a-z]+|the\s+(?:doctor|dentist|clinic))", re.I), TodoKind.APPOINTMENT),
    (re.compile(r"\b(?:package|parcel|delivery)\b.*?\b(?:arriv\w+|expected|coming)\b", re.I), TodoKind.DELIVERY),
    (re.compile(r"\bremember to\s+(.+?)(?:\.|$)", re.I), TodoKind.GENERAL),
]
_FACT_CUES = re.compile(
    r"\b(?:your|the)\s+(blood pressure|cholesterol|blood sugar|weight|test results?|diagnosis)"
    r"\b[^.]*", re.I)
_HEALTH_WORDS = ("blood", "cholesterol", "sugar", "weight", "pressure", "normal", "improved", "results")


def _uid(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.sha1(text.encode()).hexdigest()[:10]}"


def _sentences(transcript: str) -> list[str]:
    # protect honorifics so "Dr. Patel said…" stays one sentence
    protected = re.sub(r"\b(Dr|Mr|Mrs|Ms)\.\s", r"\1 ", transcript.strip())
    return [s for s in re.split(r"(?<=[.!?])\s+", protected) if s.strip()]


def extract(conv: Conversation) -> tuple[list[Fact], list[Todo]]:
    facts: list[Fact] = []
    todos: list[Todo] = []

    for sent in _sentences(conv.transcript):
        low = sent.lower()
        due = _DUE_RE.search(sent)
        due_text = due.group(0) if due else None

        # explicit "your next appointment is on Friday at 10am"
        if _APPT_NEXT_RE.search(sent):
            todos.append(Todo(id=_uid("todo", conv.id + sent + "appt"),
                              conversation_id=conv.id, text="Doctor appointment",
                              kind=TodoKind.APPOINTMENT, due_text=due_text))
            continue

        # medication
        med_done = False
        for pat in _MED_PATTERNS:
            m = pat.search(sent)
            if m:
                name = " ".join(g for g in m.groups() if g).strip()
                todos.append(Todo(
                    id=_uid("todo", conv.id + sent + "med"),
                    conversation_id=conv.id,
                    text=f"Take {name}" + (f" — {sent.strip()}" if len(sent) < 140 else ""),
                    kind=TodoKind.MEDICATION, due_text=due_text))
                med_done = True
                break
        if med_done:
            continue

        # health facts
        if (_FACT_CUES.search(sent) or "doctor said" in low or "patel said" in low) \
                and any(k in low for k in _HEALTH_WORDS):
            facts.append(Fact(id=_uid("fact", conv.id + sent), conversation_id=conv.id,
                              text=sent.strip(), category="health"))

        for pat, kind in _TODO_CUES:
            m = pat.search(sent)
            if m:
                label = (m.group(1).strip() if m.groups() and m.group(1) else sent.strip())
                if kind == TodoKind.APPOINTMENT and label.lower() in ("is", "on", "at"):
                    continue
                text = {
                    TodoKind.SHOPPING: f"Pick up / buy {label}",
                    TodoKind.CALL: f"Call {label}",
                    TodoKind.APPOINTMENT: f"Appointment: {label}",
                    TodoKind.DELIVERY: "Package expected — watch for delivery",
                    TodoKind.GENERAL: label[0].upper() + label[1:],
                }[kind]
                todos.append(Todo(id=_uid("todo", conv.id + sent + kind.value),
                                  conversation_id=conv.id, text=text, kind=kind, due_text=due_text))
                break

    seen: set[str] = set()
    uniq: list[Todo] = []
    for t in todos:
        key = t.text.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    return facts, uniq
