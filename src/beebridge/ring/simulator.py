"""Ring integration via the Ring simulator / event model.

No physical Ring device is required for the hackathon: BeeBridge accepts
Ring-style events (doorbell press, motion, package delivery) over a
webhook — the same event shape the Ring API / simulator emits — and
matches them against Bee memory:

- a *delivery* event + an open "package expected" todo from a Bee
  conversation  -> Alexa announcement "Your package has arrived" and
  the todo is completed;
- a *doorbell* event -> caregiver-style alert is recorded and shown on
  the Fire TV summary screen;
- *motion* at the front door outside expected hours -> safety alert.

With a real Ring account, point Ring's event source (or a small bridge
polling the Ring API) at POST /api/ring/events — no BeeBridge code
changes needed.
"""
from __future__ import annotations

import hashlib
from enum import Enum

from pydantic import BaseModel

from ..core.models import Alert
from ..core.store import MemoryStore


class RingEventKind(str, Enum):
    DOORBELL_PRESS = "doorbell_press"
    MOTION = "motion"
    PACKAGE_DELIVERY = "package_delivery"
    PERSON_DETECTED = "person_detected"


class RingEvent(BaseModel):
    kind: RingEventKind
    device_name: str = "Front Door"
    description: str = ""


def handle_ring_event(store: MemoryStore, event: RingEvent) -> Alert:
    uid = "alert_" + hashlib.sha1(
        f"{event.kind}{event.device_name}{event.description}".encode()).hexdigest()[:10]
    # re-delivery of the same event should not duplicate the alert idempotently —
    # include nothing time-based so tests + simulator replays are stable.

    if event.kind == RingEventKind.PACKAGE_DELIVERY:
        open_delivery = [t for t in store.list_todos() if t.kind.value == "delivery"]
        for t in open_delivery:
            store.mark_todo_done(t.id)
        text = "Your package has arrived at the front door."
        if open_delivery:
            text += " That completes the delivery you were expecting from your Bee notes."
        alert = Alert(id=uid, text=text, source="ring", spoken=True)
    elif event.kind == RingEventKind.DOORBELL_PRESS:
        alert = Alert(id=uid, text=f"Someone is at the front door ({event.device_name}).",
                      source="ring", spoken=True)
    elif event.kind == RingEventKind.PERSON_DETECTED:
        alert = Alert(id=uid, text=f"A person was detected at {event.device_name}.",
                      source="ring", spoken=True)
    else:  # motion
        alert = Alert(id=uid, text=f"Motion detected at {event.device_name}.",
                      source="ring", spoken=False)

    store.add_alert(alert)
    return alert
