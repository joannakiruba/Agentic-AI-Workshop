-- leave.db: the leave management system's own data. The agent's memory is in agent.db.

CREATE TABLE IF NOT EXISTS employee (
    id            INTEGER PRIMARY KEY,
    employee_id   TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    dept          TEXT NOT NULL,
    annual_leave  INTEGER NOT NULL DEFAULT 0 CHECK (annual_leave >= 0),      -- days remaining
    sick_leave    INTEGER NOT NULL DEFAULT 0 CHECK (sick_leave >= 0),        -- days remaining
    casual_leave  INTEGER NOT NULL DEFAULT 0 CHECK (casual_leave >= 0)       -- days remaining
);

CREATE TABLE IF NOT EXISTS holiday (
    id         INTEGER PRIMARY KEY,
    date       TEXT NOT NULL UNIQUE,           -- ISO format YYYY-MM-DD
    name       TEXT NOT NULL,
    type       TEXT NOT NULL CHECK (type IN ('public', 'optional'))
);

-- Business rules live in data, not in prompts (Day 2).
CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS leave_request (
    id          INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employee (id),
    leave_type  TEXT NOT NULL CHECK (leave_type IN ('annual', 'sick', 'casual')),
    start_date  TEXT NOT NULL,              -- ISO format YYYY-MM-DD
    end_date    TEXT NOT NULL,              -- ISO format YYYY-MM-DD
    days        INTEGER NOT NULL CHECK (days > 0),
    status      TEXT NOT NULL CHECK (status IN ('pending', 'withdrawn')),
    created_at  REAL NOT NULL,
    UNIQUE (employee_id, start_date, end_date, leave_type)
);

CREATE TABLE IF NOT EXISTS notification (
    id          INTEGER PRIMARY KEY,
    recipient   TEXT NOT NULL,              -- employee_id or 'manager'
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);

-- Day 3: keys live next to the side effects they guard.
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  REAL NOT NULL
);
