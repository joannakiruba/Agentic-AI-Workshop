# Absence Assistant: Employee Leave Request Management System

SoDak EduTech, Agentic AI Track, Day 4. Weekend project: a complete agent service for managing
employee leave requests with multi-agent architecture, durable execution, and idempotency.

An employee asks a question in plain English. A **supervisor** agent delegates to two **specialist**
agents: an info specialist that can only look, and a desk specialist that can apply/withdraw leave
and send manager notifications. The run is a job on a queue, and a worker that dies halfway through
doesn't apply leave twice.

```
employee ─▶ queue (agent.db) ─▶ worker ─▶ supervisor ──ask_info──▶ info agent ─▶ get_leave_balance, list_holidays
                                                     └─ask_desk──▶ desk agent ──▶ get_employee, check_can_apply,
                                                                                   apply_leave*, withdraw_leave*, notify_manager*
                                                                        * side effects: run once per key
```

## Domain: Leave Request Management

**Features:**
- Display leave balance (annual, sick, casual)
- Display holiday calendar
- Apply for leave
- Withdraw applied leave
- Notify manager

**Critical constraint**: Leave balance can never go negative (enforced by business rule in data)

## Run it (no API key needed)

### Python backend demo

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m scripts.demo            # two questions, scripted models, every step printed
python -m scripts.demo --crash    # the worker dies right after applying; a second worker finishes: PASS
pytest                            # 15+ tests, under a second
```

With Gemini (`export GEMINI_API_KEY=...`):

```bash
python -m scripts.demo --real                                      # same questions, real models
python -m scripts.worker                                           # terminal 1
python -m scripts.ask --employee E001 "What's my leave balance?"  # terminal 2
```

### React frontend UI

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 4173
```

Then open:

```text
http://localhost:4173/
```

The frontend is a premium single-page assistant UI for the leave system. It lets the user switch employees, ask leave questions, and see a chat-style conversation in one window while the backend remains the Python agent service.

One question costs about 5–7 model calls with three agents, so the free tier runs out quickly.
Use the scripted models for everything except a final check.

## Where each day shows up

| Day | Idea | Where to look |
|---|---|---|
| 1 | The agent loop, self-healing tool errors | `app/agents.py` `run_specialist` |
| 2 | Tool descriptions are prompts; rules live in data; schema | `app/tools/leave_tools.py`, `schema/leave.sql` (`policy` table) |
| 2 | Agent memory apart from business data | `agent.db` vs `leave.db` |
| 3 | A run is a job: queue, lease, heartbeat, reaper | `app/memory.py`, `app/worker.py`, `app/runner.py` |
| 3 | Idempotency keys; safe writes | `LeaveDb.once`, `LeaveDb.apply_leave`, `record_notification` |
| 4 | Supervisor and specialists ("agent as tool") | `app/agents.py` `SupervisorTools` |
| 4 | Least privilege per agent | info has no write tools; `DeskTools` is bound to one employee_id |
| 4 | Keys passed down to specialists | `run_tool` hands the delegation's key to `run_specialist` |

## Seed data

| Employee | Annual | Sick | Casual | What happens |
|---|---|---|---|---|
| E001 Priya Raman | 15 days | 10 days | 5 days | Can apply |
| E002 Arjun Kumar | 0 days | 12 days | 3 days | Refused: insufficient annual leave |
| E003 Divya Sekar | 20 days | 10 days | 5 days | Has 1 pending leave |

Holidays: Republic Day (2026-01-26), Holi, Independence Day, Gandhi Jayanti, Christmas.

Policies: `min_notice_days = 3`, `max_continuous_days = 30` (enforced by business rules in data, not in prompts).

## Architecture

**Two databases:**
- `agent.db`: Thread history, run queue, steps (reusable framework)
- `leave.db`: Employees, leave requests, holidays, notifications (domain-specific)

**Three agents:**
- **Supervisor**: Delegates to specialists, never checks balances or applies leave itself
- **Info Agent**: Read-only specialist (get_leave_balance, list_holidays)
- **Desk Agent**: Write specialist bound to ONE employee (apply_leave, withdraw_leave, notify_manager)

**Idempotency:**
- Every side effect runs through `LeaveDb.once()` with SHA256 key = hash(run_id, step_seq, tool_name, args)
- Keys stored atomically with effects in `idempotency` table
- Safe-to-repeat operations handle duplicates gracefully (e.g., `apply_leave` checks for existing request)

**Durable execution:**
- Every step recorded before proceeding
- Crash recovery via `rebuild()` - reconstructs state from database
- Worker lease expiry triggers requeue
- Max 3 attempts before dead-lettering

## Project structure

```
absence-assistant/
├── schema/
│   ├── agent.sql       # Agent memory & queue (reusable)
│   └── leave.sql       # Domain data (leave-specific)
├── app/
│   ├── db.py           # SQLite connection helper (reusable)
│   ├── memory.py       # RunStore: queue, lease, reap (reusable)
│   ├── worker.py       # Worker: claim, execute, record (reusable)
│   ├── idempotency.py  # Key generation (reusable)
│   ├── runner.py       # Execute run with crash recovery (adapted)
│   ├── agents.py       # Multi-agent system (leave-specific)
│   ├── leave_db.py     # Domain database access (leave-specific)
│   ├── providers.py    # Model providers & scripted mocks (adapted)
│   ├── config.py       # Environment config (adapted)
│   └── tools/
│       ├── dispatch.py # Tool call dispatcher (reusable)
│       └── leave_tools.py  # Domain tools (leave-specific)
├── scripts/
│   ├── demo.py         # End-to-end demo
│   ├── worker.py       # Long-running worker
│   └── ask.py          # CLI question tool
├── frontend/
│   ├── src/            # React single-page UI
│   ├── package.json    # Frontend dependencies/scripts
│   └── vite.config.js # Vite config
├── tests/
│   ├── conftest.py     # Test fixtures
│   ├── test_tools.py   # Tool unit tests
│   ├── test_agents.py  # Agent delegation tests
│   └── test_end_to_end.py  # Integration tests with crash replay
├── requirements.txt
├── pytest.ini
└── README.md
```

## Known limits (on purpose, for later days)

- A specialist's inner steps are not stored; only the delegation and its answer are. After a crash the
  specialist runs again, and keys keep its side effects single. Storing them is checkpointing (Day 5).
- Keys only match if the model repeats the same call. The scripted models always do; real models
  usually do at temperature 0. The leave application and notification are also safe to repeat on their own.
- No approval step before a side effect (Day 5), no guardrails or metrics (Day 6), no MCP (Day 7).

## Design decisions

1. **Leave balance as constraint**: The `check_can_apply` tool reads from the employee's current balance
   and policy table, enforcing the "balance never negative" rule even if the model skips the check.

2. **Optimistic locking**: Leave requests use unique constraint on (employee_id, start_date, end_date, 
   leave_type) to prevent duplicate applications in race conditions.

3. **Least privilege**: Info agent has ZERO write tools; desk agent is bound to ONE employee_id at
   construction time, so the model cannot apply leave for someone else.

4. **Business rules in data**: Policy table stores `min_notice_days` and `max_continuous_days` as rows,
   not hardcoded in prompts. Tools read from this table, making rules auditable and changeable.

5. **Safe-to-repeat operations**: `apply_leave` checks for existing request and returns `already_applied`;
   `withdraw_leave` checks status and returns `already_withdrawn`; `record_notification` uses dedupe key.

## What was implemented

✅ Two SQLite databases (agent.db, leave.db) with seed data  
✅ Five tools: 2 read-only (info agent), 3 side effects (desk agent)  
✅ Business rule in data (`policy` table enforced by `check_can_apply`)  
✅ Queue with worker, lease, heartbeat, reaper  
✅ Idempotency keys for all side effects  
✅ Multi-agent: supervisor + 2 specialists, info agent has no write tools  
✅ Works without API key: scripted models, crash demo (PASS), pytest with 15+ tests  
✅ Crash-and-replay test validates idempotency  

## Testing

```bash
pytest -v                           # All tests with verbose output
pytest tests/test_tools.py          # Tool unit tests only
pytest tests/test_end_to_end.py -k crash  # Crash replay test only
python -m scripts.demo --crash      # Visual crash demo
```

All tests pass without an API key using scripted models.

## Next steps (not implemented)

- Retry with exponential backoff (lab 2)
- Cancel from second terminal (lab 1) 
- Race condition test with threads
- Successful run on real Gemini (requires API key)
- Date validation (ensure leave dates are in future, not on holidays)
- Approval workflow (manager approval before finalizing leave)

---

**Submitted by**: Joanna Kiruba (312314104128)
**Domain**: Leave Request Management  
**Date**: 2026-09-20
