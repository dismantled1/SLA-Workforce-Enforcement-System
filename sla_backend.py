#!/usr/bin/env python3
"""
SLA Workforce Enforcement System - Backend
Handles complaint registration, SLA timers, and escalation logic.
"""

import json
import uuid
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import threading

# ─── SLA Configuration ────────────────────────────────────────────────────────

class Priority(str, Enum):
    CRITICAL = "critical"   # 1 hour
    HIGH     = "high"       # 24 hours
    MEDIUM   = "medium"     # 72 hours
    LOW      = "low"        # 168 hours (7 days)

SLA_HOURS = {
    Priority.CRITICAL: 1,
    Priority.HIGH:     24,
    Priority.MEDIUM:   72,
    Priority.LOW:      168,
}

class Status(str, Enum):
    OPEN        = "open"
    IN_PROGRESS = "in_progress"
    ESCALATED   = "escalated"       # Passed to supervisor
    CRITICAL_ESC= "admin_escalated" # Passed to admin
    RESOLVED    = "resolved"
    CLOSED      = "closed"

class Role(str, Enum):
    AGENT      = "agent"
    SUPERVISOR = "supervisor"
    ADMIN      = "admin"

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class EscalationEvent:
    timestamp: str
    from_role: str
    to_role: str
    reason: str

@dataclass
class Complaint:
    id: str
    title: str
    description: str
    priority: str
    status: str
    created_at: str
    deadline: str
    assigned_to: Optional[str]
    resolved_at: Optional[str]
    escalations: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @property
    def deadline_dt(self) -> datetime:
        return datetime.fromisoformat(self.deadline)

    @property
    def created_dt(self) -> datetime:
        return datetime.fromisoformat(self.created_at)

    @property
    def sla_hours(self) -> int:
        return SLA_HOURS[Priority(self.priority)]

    @property
    def elapsed_seconds(self) -> float:
        return (datetime.now() - self.created_dt).total_seconds()

    @property
    def remaining_seconds(self) -> float:
        return (self.deadline_dt - datetime.now()).total_seconds()

    @property
    def is_breached(self) -> bool:
        return datetime.now() > self.deadline_dt and self.status != Status.RESOLVED

    @property
    def progress_pct(self) -> float:
        total = self.sla_hours * 3600
        elapsed = self.elapsed_seconds
        return min(100.0, (elapsed / total) * 100)


# ─── In-Memory Store (replace with DB in production) ──────────────────────────

class ComplaintStore:
    def __init__(self):
        self._complaints: dict[str, Complaint] = {}
        self._lock = threading.Lock()
        self._seed_data()

    def _seed_data(self):
        """Seed with some example complaints for demo."""
        samples = [
            ("Login portal completely down", "All agents unable to authenticate to the CRM system since 08:00", Priority.CRITICAL, -0.5),
            ("Report export broken", "Monthly compliance report fails with a 500 error", Priority.HIGH, -6),
            ("Slow dashboard load", "Dashboard takes 25+ seconds to load after login", Priority.MEDIUM, -48),
            ("Typo in email template", "Welcome email has incorrect company address", Priority.LOW, -120),
        ]
        for title, desc, priority, hours_ago in samples:
            created = datetime.now() + timedelta(hours=hours_ago)
            sla_h = SLA_HOURS[priority]
            deadline = created + timedelta(hours=sla_h)
            c = Complaint(
                id=str(uuid.uuid4())[:8].upper(),
                title=title,
                description=desc,
                priority=priority.value,
                status=Status.OPEN.value,
                created_at=created.isoformat(),
                deadline=deadline.isoformat(),
                assigned_to="agent_01",
                resolved_at=None,
                escalations=[],
                notes=[],
            )
            # Auto-escalate breached ones
            if c.is_breached:
                c.status = Status.ESCALATED.value
                c.escalations.append(asdict(EscalationEvent(
                    timestamp=deadline.isoformat(),
                    from_role=Role.AGENT.value,
                    to_role=Role.SUPERVISOR.value,
                    reason=f"SLA breached: {sla_h}h window expired"
                )))
            self._complaints[c.id] = c

    def register(self, title: str, description: str, priority: str) -> Complaint:
        with self._lock:
            p = Priority(priority)
            now = datetime.now()
            deadline = now + timedelta(hours=SLA_HOURS[p])
            c = Complaint(
                id=str(uuid.uuid4())[:8].upper(),
                title=title,
                description=description,
                priority=priority,
                status=Status.OPEN.value,
                created_at=now.isoformat(),
                deadline=deadline.isoformat(),
                assigned_to=None,
                resolved_at=None,
            )
            self._complaints[c.id] = c
            return c

    def get(self, complaint_id: str) -> Optional[Complaint]:
        return self._complaints.get(complaint_id)

    def all(self) -> list[Complaint]:
        return list(self._complaints.values())

    def update_status(self, complaint_id: str, status: str, note: str = "") -> Optional[Complaint]:
        with self._lock:
            c = self._complaints.get(complaint_id)
            if not c:
                return None
            c.status = status
            if status == Status.RESOLVED.value:
                c.resolved_at = datetime.now().isoformat()
            if note:
                c.notes.append({"timestamp": datetime.now().isoformat(), "text": note})
            return c

    def escalate(self, complaint_id: str, from_role: str, to_role: str, reason: str) -> Optional[Complaint]:
        with self._lock:
            c = self._complaints.get(complaint_id)
            if not c:
                return None
            new_status = Status.CRITICAL_ESC.value if to_role == Role.ADMIN.value else Status.ESCALATED.value
            c.status = new_status
            c.escalations.append(asdict(EscalationEvent(
                timestamp=datetime.now().isoformat(),
                from_role=from_role,
                to_role=to_role,
                reason=reason,
            )))
            return c

    def run_sla_check(self):
        """Background thread: auto-escalate breached SLAs."""
        with self._lock:
            for c in self._complaints.values():
                if c.status in (Status.RESOLVED.value, Status.CLOSED.value, Status.CRITICAL_ESC.value):
                    continue
                if not c.is_breached:
                    continue
                # First breach → escalate to supervisor
                if c.status == Status.OPEN.value or c.status == Status.IN_PROGRESS.value:
                    c.status = Status.ESCALATED.value
                    c.escalations.append(asdict(EscalationEvent(
                        timestamp=datetime.now().isoformat(),
                        from_role=Role.AGENT.value,
                        to_role=Role.SUPERVISOR.value,
                        reason="Automatic SLA breach escalation"
                    )))
                # Already with supervisor and still breached → escalate to admin
                elif c.status == Status.ESCALATED.value:
                    grace = timedelta(hours=SLA_HOURS[Priority(c.priority)] * 0.25)
                    if datetime.now() > c.deadline_dt + grace:
                        c.status = Status.CRITICAL_ESC.value
                        c.escalations.append(asdict(EscalationEvent(
                            timestamp=datetime.now().isoformat(),
                            from_role=Role.SUPERVISOR.value,
                            to_role=Role.ADMIN.value,
                            reason="Supervisor resolution timeout — escalated to Admin"
                        )))

    def stats(self) -> dict:
        all_c = self.all()
        return {
            "total": len(all_c),
            "open": sum(1 for c in all_c if c.status == Status.OPEN.value),
            "in_progress": sum(1 for c in all_c if c.status == Status.IN_PROGRESS.value),
            "escalated": sum(1 for c in all_c if c.status == Status.ESCALATED.value),
            "admin_escalated": sum(1 for c in all_c if c.status == Status.CRITICAL_ESC.value),
            "resolved": sum(1 for c in all_c if c.status == Status.RESOLVED.value),
            "breached": sum(1 for c in all_c if c.is_breached),
            "by_priority": {
                p.value: sum(1 for c in all_c if c.priority == p.value)
                for p in Priority
            }
        }


# ─── Simple HTTP API (stdlib only) ────────────────────────────────────────────

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

store = ComplaintStore()

def sla_checker():
    while True:
        store.run_sla_check()
        time.sleep(30)

threading.Thread(target=sla_checker, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/complaints":
            complaints = [c.to_dict() for c in store.all()]
            # Enrich with live timer data
            for cd in complaints:
                c = store.get(cd["id"])
                cd["remaining_seconds"] = max(0, c.remaining_seconds)
                cd["progress_pct"] = c.progress_pct
                cd["is_breached"] = c.is_breached
            self.send_json(complaints)

        elif path.startswith("/api/complaints/"):
            cid = path.split("/")[-1]
            c = store.get(cid)
            if c:
                d = c.to_dict()
                d["remaining_seconds"] = max(0, c.remaining_seconds)
                d["progress_pct"] = c.progress_pct
                d["is_breached"] = c.is_breached
                self.send_json(d)
            else:
                self.send_json({"error": "Not found"}, 404)

        elif path == "/api/stats":
            self.send_json(store.stats())

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/complaints":
            required = {"title", "description", "priority"}
            if not required.issubset(body):
                self.send_json({"error": "Missing fields"}, 400)
                return
            if body["priority"] not in [p.value for p in Priority]:
                self.send_json({"error": "Invalid priority"}, 400)
                return
            c = store.register(body["title"], body["description"], body["priority"])
            self.send_json(c.to_dict(), 201)

        elif path.startswith("/api/complaints/") and path.endswith("/escalate"):
            cid = path.split("/")[-2]
            c = store.escalate(cid, body.get("from_role", "agent"), body.get("to_role", "supervisor"), body.get("reason", "Manual escalation"))
            self.send_json(c.to_dict() if c else {"error": "Not found"}, 200 if c else 404)

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path.startswith("/api/complaints/"):
            cid = path.split("/")[-1]
            c = store.update_status(cid, body.get("status", ""), body.get("note", ""))
            self.send_json(c.to_dict() if c else {"error": "Not found"}, 200 if c else 404)
        else:
            self.send_json({"error": "Not found"}, 404)


if __name__ == "__main__":
    port = 8765
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"SLA Backend running on http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
