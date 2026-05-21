# SLA Workforce Enforcement System
 
A lightweight, full-stack SLA (Service Level Agreement) monitoring and escalation dashboard for complaint management. Built with a pure Python backend (zero dependencies) and a single-file vanilla JS frontend.
 
---
 
## Overview
 
This system tracks complaints through their full lifecycle — from registration to resolution — while automatically enforcing SLA deadlines. When a complaint breaches its SLA window, it is automatically escalated through a role-based chain: **Agent → Supervisor → Admin**.
 
### SLA Windows by Priority
 
| Priority | SLA Window |
|----------|-----------|
| 🔴 Critical | 1 hour |
| 🟠 High | 24 hours |
| 🟡 Medium | 72 hours |
| 🟢 Low | 168 hours (7 days) |
 
---
 
## Features
 
- **Live SLA Timers** — countdown timers update in real-time for every open complaint
- **Automatic Escalation** — background thread checks every 30 seconds and escalates breached SLAs without manual intervention
- **Two-Stage Escalation** — breached complaints go to Supervisor first; if still unresolved after a 25% grace period, they escalate to Admin
- **Role-Based Views** — switch between Agent, Supervisor, and Admin perspectives; alert banners and action permissions adapt accordingly
- **Complaint Registration** — submit new complaints with title, description, and priority
- **Manual Escalation** — agents and supervisors can manually escalate complaints with a reason
- **Analytics Report** — summary view with breach rate, resolution rate, and priority distribution
- **Live Backend Sync** — frontend polls the backend every 10 seconds and falls back to local state if the server is unreachable
- **Responsive UI** — works on desktop and mobile with a bottom navigation bar on smaller screens
---
 
## Tech Stack
 
| Layer | Technology |
|-------|-----------|
| Backend | Python 3 (stdlib only — `http.server`, `threading`, `uuid`, `dataclasses`) |
| Frontend | Vanilla HTML/CSS/JavaScript (single file) |
| Fonts | IBM Plex Sans + IBM Plex Mono (Google Fonts) |
| Storage | In-memory (dict) with thread-safe locking |
 
No pip installs. No npm. No frameworks.
 
---
 
## Project Structure
 
```
sla-enforcement/
├── sla_backend.py   # Python HTTP API server
└── index.html       # Frontend dashboard (single file)
```
 
---
 
## Getting Started
 
### 1. Run the Backend
 
```bash
python3 sla_backend.py
```
 
The server starts on `http://localhost:8765`. On first run it seeds four example complaints across all priority levels.
 
### 2. Open the Frontend
 
Open `index.html` directly in your browser. No build step or local server required.
 
The frontend auto-detects the backend at `http://localhost:8765` and syncs every 10 seconds. If the backend is offline, it operates in local-only mode.
 
---
 
## API Reference
 
All endpoints return JSON. CORS is open (`*`) for local development.
 
### Complaints
 
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/complaints` | List all complaints (with live timer data) |
| `GET` | `/api/complaints/:id` | Get a single complaint |
| `POST` | `/api/complaints` | Register a new complaint |
| `PUT` | `/api/complaints/:id` | Update status / add a note |
| `POST` | `/api/complaints/:id/escalate` | Manually escalate a complaint |
 
### Stats
 
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stats` | Aggregate counts by status and priority |
 
### Example — Register a Complaint
 
```bash
curl -X POST http://localhost:8765/api/complaints \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Payment gateway timeout",
    "description": "Customers unable to complete checkout since 14:30",
    "priority": "critical"
  }'
```
 
### Example — Escalate a Complaint
 
```bash
curl -X POST http://localhost:8765/api/complaints/ABC12345/escalate \
  -H "Content-Type: application/json" \
  -d '{
    "from_role": "agent",
    "to_role": "supervisor",
    "reason": "Customer threatening chargeback"
  }'
```
 
---
 
## Complaint Lifecycle
 
```
OPEN → IN_PROGRESS → RESOLVED → CLOSED
          ↓ (SLA breach)
       ESCALATED (Supervisor)
          ↓ (grace period exceeded)
    ADMIN_ESCALATED (Admin)
```
 
Escalation events are recorded on the complaint with a timestamp, from/to roles, and reason — forming a full audit trail.
 
---
 
## Production Notes
 
The backend uses an in-memory store that resets on restart. For production use, replace `ComplaintStore` with a persistent database (PostgreSQL, SQLite, etc.). The data model uses Python `dataclasses` and is straightforward to adapt to any ORM.
 
---
 

 
