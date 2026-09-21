# Supabase Database Setup Guide

## What is Supabase?

Supabase is an open-source Firebase alternative that provides a PostgreSQL database with real-time capabilities, authentication, storage, and edge functions. For this project, we're using it as a production-grade database replacement for SQLite.

**Why Supabase for this project?**
- ✅ PostgreSQL backend (more robust than SQLite for production)
- ✅ Built-in connection pooling
- ✅ Real-time subscriptions (future feature)
- ✅ Free tier with 500MB database
- ✅ Web dashboard for database management
- ✅ REST API auto-generated from schema
- ✅ Row-level security (RLS) for data protection

---

## 1. Create a Supabase Project

### Step 1: Sign up for Supabase
1. Go to [https://supabase.com](https://supabase.com)
2. Click "Start your project" and sign up (GitHub OAuth recommended)
3. Verify your email address

### Step 2: Create a new project
1. Click "New Project" in your organization
2. Fill in the details:
   - **Name**: `absence-assistant` (or any name you prefer)
   - **Database Password**: Generate a strong password (SAVE THIS!)
   - **Region**: Choose closest to your location (e.g., `ap-southeast-1` for Singapore)
   - **Pricing Plan**: Free (sufficient for this project)
3. Click "Create new project"
4. Wait 2-3 minutes for provisioning

### Step 3: Get your connection details
1. Go to **Project Settings** (gear icon in sidebar)
2. Navigate to **Database** section
3. Note down:
   - **Host**: `db.xxxxx.supabase.co`
   - **Database name**: `postgres`
   - **Port**: `5432`
   - **User**: `postgres`
   - **Password**: (the one you set during creation)
   - **Connection String** (we'll use this)

---

## 2. Database Schema Migration

### Understanding the differences: SQLite vs PostgreSQL

| Feature | SQLite | PostgreSQL (Supabase) |
|---------|--------|----------------------|
| Data types | Limited | Rich (JSONB, arrays, etc.) |
| Transactions | File locking | MVCC (concurrent) |
| Constraints | Basic | Advanced (CHECK, EXCLUDE) |
| Auto-increment | `INTEGER PRIMARY KEY` | `SERIAL` or `GENERATED ALWAYS` |
| Date/time | TEXT | `TIMESTAMP`, `DATE`, `TIME` |

### Create the schema in Supabase

1. Open **SQL Editor** in Supabase dashboard
2. Create a new query
3. Copy and paste the PostgreSQL-adapted schema below

#### Agent Database Schema (PostgreSQL)

```sql
-- agent database: conversation history and job queue
-- Run this in Supabase SQL Editor

-- Thread table (employee conversations)
CREATE TABLE IF NOT EXISTS thread (
    id          TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Message table (append-only conversation log)
CREATE TABLE IF NOT EXISTS message (
    id          SERIAL PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES thread(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'model')),
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (thread_id, seq)
);

-- Prevent updates/deletes on message (append-only)
CREATE OR REPLACE FUNCTION prevent_message_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'message table is append-only: % rejected', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER message_no_update
    BEFORE UPDATE ON message
    FOR EACH ROW EXECUTE FUNCTION prevent_message_modification();

CREATE TRIGGER message_no_delete
    BEFORE DELETE ON message
    FOR EACH ROW EXECUTE FUNCTION prevent_message_modification();

-- Run table (job queue)
CREATE TABLE IF NOT EXISTS run (
    id                TEXT PRIMARY KEY,
    thread_id         TEXT NOT NULL REFERENCES thread(id) ON DELETE CASCADE,
    status            TEXT NOT NULL CHECK (status IN 
                          ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'dead')),
    model             TEXT NOT NULL,
    tokens_in         INTEGER NOT NULL DEFAULT 0,
    tokens_out        INTEGER NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 3,
    available_at      TIMESTAMPTZ NOT NULL,
    lease_owner       TEXT,
    lease_until       TIMESTAMPTZ,
    cancel_requested  BOOLEAN NOT NULL DEFAULT FALSE,
    error_code        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS run_claimable_idx ON run (status, available_at);

-- Run step table (execution trace)
CREATE TABLE IF NOT EXISTS run_step (
    id          SERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('model', 'tool')),
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    text        TEXT,
    tool_calls  JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

-- Tool call table (individual tool executions)
CREATE TABLE IF NOT EXISTS tool_call (
    id               SERIAL PRIMARY KEY,
    run_step_id      INTEGER NOT NULL UNIQUE REFERENCES run_step(id) ON DELETE CASCADE,
    tool_name        TEXT NOT NULL,
    args             JSONB NOT NULL,
    result           JSONB NOT NULL,
    ok               BOOLEAN NOT NULL,
    latency_ms       INTEGER NOT NULL,
    idempotency_key  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enable Row Level Security (optional, for future multi-tenancy)
ALTER TABLE thread ENABLE ROW LEVEL SECURITY;
ALTER TABLE message ENABLE ROW LEVEL SECURITY;
ALTER TABLE run ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_step ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_call ENABLE ROW LEVEL SECURITY;

-- Allow all operations for authenticated users (adjust as needed)
CREATE POLICY "Allow all for authenticated users" ON thread
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON message
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON run
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON run_step
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON tool_call
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
```

#### Leave Database Schema (PostgreSQL)

```sql
-- leave database: employee leave management
-- Run this in Supabase SQL Editor (separate schema or database)

-- Employee table
CREATE TABLE IF NOT EXISTS employee (
    id            SERIAL PRIMARY KEY,
    employee_id   TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    dept          TEXT NOT NULL,
    annual_leave  INTEGER NOT NULL DEFAULT 0 CHECK (annual_leave >= 0),
    sick_leave    INTEGER NOT NULL DEFAULT 0 CHECK (sick_leave >= 0),
    casual_leave  INTEGER NOT NULL DEFAULT 0 CHECK (casual_leave >= 0)
);

-- Holiday calendar
CREATE TABLE IF NOT EXISTS holiday (
    id         SERIAL PRIMARY KEY,
    date       DATE NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    type       TEXT NOT NULL CHECK (type IN ('public', 'optional'))
);

-- Policy table (business rules as data)
CREATE TABLE IF NOT EXISTS policy (
    name   TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

-- Leave request table
CREATE TABLE IF NOT EXISTS leave_request (
    id          SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employee(id) ON DELETE CASCADE,
    leave_type  TEXT NOT NULL CHECK (leave_type IN ('annual', 'sick', 'casual')),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    days        INTEGER NOT NULL CHECK (days > 0),
    status      TEXT NOT NULL CHECK (status IN ('pending', 'withdrawn')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (employee_id, start_date, end_date, leave_type)
);

-- Notification table
CREATE TABLE IF NOT EXISTS notification (
    id          SERIAL PRIMARY KEY,
    recipient   TEXT NOT NULL,
    message     TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotency table (prevent duplicate side effects)
CREATE TABLE IF NOT EXISTS idempotency (
    key         TEXT PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    result      JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS leave_request_employee_idx ON leave_request(employee_id);
CREATE INDEX IF NOT EXISTS leave_request_status_idx ON leave_request(status);
CREATE INDEX IF NOT EXISTS notification_recipient_idx ON notification(recipient);

-- Enable RLS
ALTER TABLE employee ENABLE ROW LEVEL SECURITY;
ALTER TABLE holiday ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE leave_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency ENABLE ROW LEVEL SECURITY;

-- RLS policies (allow all for authenticated)
CREATE POLICY "Allow all for authenticated users" ON employee
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON holiday
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON policy
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON leave_request
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON notification
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Allow all for authenticated users" ON idempotency
    FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');

-- Seed data
INSERT INTO employee (employee_id, name, dept, annual_leave, sick_leave, casual_leave) VALUES
    ('E001', 'Priya Raman', 'Engineering', 15, 10, 5),
    ('E002', 'Arjun Kumar', 'Marketing', 0, 12, 3),
    ('E003', 'Divya Sekar', 'Sales', 20, 10, 5)
ON CONFLICT (employee_id) DO NOTHING;

INSERT INTO holiday (date, name, type) VALUES
    ('2026-01-26', 'Republic Day', 'public'),
    ('2026-03-08', 'Holi', 'public'),
    ('2026-08-15', 'Independence Day', 'public'),
    ('2026-10-02', 'Gandhi Jayanti', 'public'),
    ('2026-12-25', 'Christmas', 'public')
ON CONFLICT (date) DO NOTHING;

INSERT INTO policy (name, value) VALUES
    ('min_notice_days', 3),
    ('max_continuous_days', 30)
ON CONFLICT (name) DO NOTHING;

INSERT INTO leave_request (employee_id, leave_type, start_date, end_date, days, status, created_at) VALUES
    (3, 'annual', '2026-09-25', '2026-09-27', 3, 'pending', NOW())
ON CONFLICT DO NOTHING;
```

---

## 3. Connection Setup in Code

### Install PostgreSQL driver

```bash
pip install psycopg2-binary python-dotenv
```

### Create environment file

Create `.env` file in project root:

```env
# Supabase Connection
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=your-anon-or-service-key
SUPABASE_DB_URL=postgresql://postgres:your-password@db.xxxxx.supabase.co:5432/postgres

# Gemini API
GEMINI_API_KEY=your-gemini-api-key

# Environment
USE_SUPABASE=true
```

### Create Supabase database adapter

Create `app/supabase_db.py`:

```python
"""Supabase PostgreSQL database adapter for the leave management system."""
import os
import json
import time
from collections.abc import Callable
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool


class SupabaseConnection:
    """Manages PostgreSQL connection pool to Supabase."""
    
    def __init__(self, connection_string: str, min_conn: int = 1, max_conn: int = 10):
        self.pool = psycopg2.pool.ThreadedConnectionPool(
            min_conn, max_conn, connection_string, cursor_factory=RealDictCursor
        )
    
    def get_conn(self):
        """Get a connection from the pool."""
        return self.pool.getconn()
    
    def put_conn(self, conn):
        """Return a connection to the pool."""
        self.pool.putconn(conn)
    
    @contextmanager
    def connection(self):
        """Context manager for connection."""
        conn = self.get_conn()
        try:
            yield conn
        finally:
            self.put_conn(conn)
    
    @contextmanager
    def transaction(self, conn=None):
        """Context manager for transactions."""
        own_conn = conn is None
        if own_conn:
            conn = self.get_conn()
        
        try:
            with conn:
                with conn.cursor() as cursor:
                    yield cursor
            if own_conn:
                conn.commit()
        except Exception:
            if own_conn:
                conn.rollback()
            raise
        finally:
            if own_conn:
                self.put_conn(conn)


class SupabaseLeaveDb:
    """Leave database on Supabase PostgreSQL."""
    
    def __init__(self, connection_string: str, clock: Callable[[], float] = time.time):
        self.db = SupabaseConnection(connection_string)
        self.clock = clock
    
    def get_employee(self, employee_id: str) -> dict | None:
        """Get employee by employee_id."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM employee WHERE employee_id = %s", (employee_id,))
                row = cur.fetchone()
                return dict(row) if row else None
    
    def policy(self, name: str) -> int:
        """Get policy value by name."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM policy WHERE name = %s", (name,))
                return cur.fetchone()["value"]
    
    def get_leave_balance(self, employee_id: str) -> dict | None:
        """Get employee's current leave balance."""
        emp = self.get_employee(employee_id)
        if emp is None:
            return None
        return {
            "employee_id": emp["employee_id"],
            "name": emp["name"],
            "annual_leave": emp["annual_leave"],
            "sick_leave": emp["sick_leave"],
            "casual_leave": emp["casual_leave"]
        }
    
    def apply_leave(self, emp_id: int, leave_type: str, start_date: str, 
                    end_date: str, days: int) -> dict:
        """Apply for leave with transaction safety."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                # Check for duplicate
                cur.execute(
                    """SELECT id FROM leave_request 
                       WHERE employee_id = %s AND start_date = %s 
                       AND end_date = %s AND leave_type = %s""",
                    (emp_id, start_date, end_date, leave_type)
                )
                existing = cur.fetchone()
                if existing:
                    return {"status": "already_applied", "request_id": existing["id"]}
                
                # Get current balance
                cur.execute("SELECT * FROM employee WHERE id = %s FOR UPDATE", (emp_id,))
                emp = cur.fetchone()
                balance_field = f"{leave_type}_leave"
                current_balance = emp[balance_field]
                
                if current_balance < days:
                    return {"status": "insufficient_balance", 
                            "available": current_balance, "requested": days}
                
                # Deduct balance
                cur.execute(
                    f"UPDATE employee SET {balance_field} = {balance_field} - %s WHERE id = %s",
                    (days, emp_id)
                )
                
                # Create request
                cur.execute(
                    """INSERT INTO leave_request 
                       (employee_id, leave_type, start_date, end_date, days, status, created_at)
                       VALUES (%s, %s, %s, %s, %s, 'pending', NOW()) RETURNING id""",
                    (emp_id, leave_type, start_date, end_date, days)
                )
                request_id = cur.fetchone()["id"]
                conn.commit()
                
                return {"status": "applied", "request_id": request_id, "days_deducted": days}
    
    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        """Run a side effect at most once per idempotency key."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                # Check if key exists
                cur.execute("SELECT result FROM idempotency WHERE key = %s", (key,))
                row = cur.fetchone()
                if row is not None:
                    return json.loads(row["result"]), False
                
                # Execute effect
                result = effect()
                
                # Store key and result
                cur.execute(
                    """INSERT INTO idempotency (key, tool_name, result, created_at)
                       VALUES (%s, %s, %s, NOW())""",
                    (key, tool_name, json.dumps(result, default=str))
                )
                conn.commit()
                
                return result, True
    
    # Add other methods as needed (withdraw_leave, record_notification, etc.)
```

### Update config to support both SQLite and Supabase

```python
# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

USE_SUPABASE = os.environ.get("USE_SUPABASE", "false").lower() == "true"

def open_stores():
    if USE_SUPABASE:
        from app.supabase_db import SupabaseLeaveDb, SupabaseRunStore
        from app.memory import RunStore
        
        db_url = os.environ.get("SUPABASE_DB_URL")
        if not db_url:
            raise ValueError("SUPABASE_DB_URL not set in environment")
        
        # For now, keep RunStore as SQLite (or implement Supabase version)
        store = RunStore("agent.db")
        db = SupabaseLeaveDb(db_url)
        
        store.migrate()
        return store, db
    else:
        # Original SQLite implementation
        from app.memory import RunStore
        from app.leave_db import LeaveDb
        
        store = RunStore(os.environ.get("AGENT_DB", "agent.db"))
        db = LeaveDb(os.environ.get("LEAVE_DB", "leave.db"))
        
        store.migrate()
        db.migrate()
        return store, db
```

---

## 4. Testing the Connection

### Test script

Create `scripts/test_supabase.py`:

```python
"""Test Supabase connection and basic operations."""
import os
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    from app.supabase_db import SupabaseLeaveDb
    
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("❌ SUPABASE_DB_URL not set")
        return False
    
    try:
        db = SupabaseLeaveDb(db_url)
        
        # Test 1: Get employee
        emp = db.get_employee("E001")
        assert emp is not None, "Employee E001 not found"
        assert emp["name"] == "Priya Raman", f"Expected Priya Raman, got {emp['name']}"
        print("✅ Test 1: Get employee - PASSED")
        
        # Test 2: Get policy
        min_notice = db.policy("min_notice_days")
        assert min_notice == 3, f"Expected 3, got {min_notice}"
        print("✅ Test 2: Get policy - PASSED")
        
        # Test 3: Get leave balance
        balance = db.get_leave_balance("E001")
        assert balance["annual_leave"] == 15
        print("✅ Test 3: Get leave balance - PASSED")
        
        print("\n🎉 All tests passed! Supabase connection is working.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_connection()
```

Run the test:

```bash
python scripts/test_supabase.py
```

---

## 5. Deployment Checklist

- [ ] Supabase project created
- [ ] Database schema deployed (both agent and leave tables)
- [ ] Seed data inserted
- [ ] `.env` file configured with correct connection string
- [ ] `psycopg2-binary` installed
- [ ] Connection test passes
- [ ] RLS policies configured (if needed)
- [ ] Connection pooling tested under load
- [ ] Backup strategy defined (Supabase auto-backups daily)

---

## 6. Monitoring and Maintenance

### View logs in Supabase
1. Go to **Database** → **Logs** in Supabase dashboard
2. Filter by severity (ERROR, WARNING, INFO)
3. Check for connection issues, slow queries

### Query performance
1. Go to **Database** → **Query Performance**
2. Identify slow queries
3. Add indexes as needed

### Database size
- Free tier: 500MB database
- Monitor in **Database** → **Database Size**

---

## 7. Troubleshooting

### Connection errors

**Error**: `psycopg2.OperationalError: could not connect`
- Check if your IP is allowed (Supabase allows all by default)
- Verify connection string format
- Check if database password is correct

**Error**: `SSL connection required`
```python
# Add to connection string
?sslmode=require
```

### Permission errors

**Error**: `permission denied for table`
- Check RLS policies
- Use service role key for backend operations
- Anon key is for client-side only

### Schema sync issues
- Run migrations in SQL Editor
- Check for conflicting constraints
- Use `DROP TABLE IF EXISTS ... CASCADE` to reset (⚠️ destroys data)

---

## 8. Next Steps

1. **Implement full Supabase adapter** for all database methods
2. **Add connection pooling** configuration
3. **Set up real-time subscriptions** for live updates
4. **Implement proper RLS** for multi-tenant security
5. **Add database migrations** system (e.g., `alembic`)
6. **Set up CI/CD** to auto-deploy schema changes
7. **Monitor query performance** and add indexes

---

## Resources

- [Supabase Documentation](https://supabase.com/docs)
- [PostgreSQL psycopg2 docs](https://www.psycopg.org/docs/)
- [Row Level Security Guide](https://supabase.com/docs/guides/auth/row-level-security)
- [Connection Pooling Best Practices](https://supabase.com/docs/guides/database/connecting-to-postgres#connection-pool)

---

**Note**: This guide provides the foundation for Supabase integration. The full implementation requires completing the adapter methods for all database operations currently in `leave_db.py`.
