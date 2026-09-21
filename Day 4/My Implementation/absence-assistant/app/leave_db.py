"""leave.db: employees, leave requests, holidays. Every SQL statement for the leave system lives here."""
import json
import time
from collections.abc import Callable
from pathlib import Path

from app.db import connect, transaction

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "leave.sql"


class LeaveDb:
    def __init__(self, path: str = ":memory:", clock: Callable[[], float] = time.time):
        self.conn = connect(path)
        self.clock = clock

    def transaction(self):
        return transaction(self.conn)

    def migrate(self) -> None:
        self.conn.executescript(SCHEMA.read_text())
        if self.conn.execute("SELECT count(*) FROM employee").fetchone()[0]:
            return
        with self.transaction() as c:
            # Seed employees
            c.executemany("INSERT INTO employee VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (1, "E001", "Priya Raman", "Engineering", 15, 10, 5),
                (2, "E002", "Arjun Kumar", "Marketing", 0, 12, 3),      # no annual leave
                (3, "E003", "Divya Sekar", "Sales", 20, 10, 5)])

            # Seed holidays (2026)
            c.executemany("INSERT INTO holiday VALUES (?, ?, ?, ?)", [
                (1, "2026-01-26", "Republic Day", "public"),
                (2, "2026-03-08", "Holi", "public"),
                (3, "2026-08-15", "Independence Day", "public"),
                (4, "2026-10-02", "Gandhi Jayanti", "public"),
                (5, "2026-12-25", "Christmas", "public")])

            # Seed policies
            c.executemany("INSERT INTO policy VALUES (?, ?)", [
                ("min_notice_days", 3),
                ("max_continuous_days", 30)])

            # Seed one existing leave for E003
            c.execute("INSERT INTO leave_request (employee_id, leave_type, start_date, end_date, days, status, created_at) "
                     "VALUES (3, 'annual', '2026-09-25', '2026-09-27', 3, 'pending', ?)", (self.clock(),))

    # ------------------------------------------------------------------ reads

    def get_employee(self, employee_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM employee WHERE employee_id = ?", (employee_id,)).fetchone()
        return dict(r) if r else None

    def policy(self, name: str) -> int:
        return self.conn.execute("SELECT value FROM policy WHERE name = ?", (name,)).fetchone()[0]

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

    def active_leave_requests(self, emp_id: int) -> list[dict]:
        """Get all pending leave requests for an employee."""
        rows = self.conn.execute(
            "SELECT id, leave_type, start_date, end_date, days, status FROM leave_request"
            " WHERE employee_id = ? AND status = 'pending' ORDER BY start_date", (emp_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_holidays(self, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
        """List holidays, optionally filtered by date range."""
        if start_date and end_date:
            rows = self.conn.execute(
                "SELECT date, name, type FROM holiday WHERE date BETWEEN ? AND ? ORDER BY date",
                (start_date, end_date)).fetchall()
        else:
            rows = self.conn.execute("SELECT date, name, type FROM holiday ORDER BY date").fetchall()
        return [dict(r) for r in rows]

    def get_leave_request(self, request_id: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM leave_request WHERE id = ?", (request_id,)).fetchone()
        return dict(r) if r else None

    def count(self, table: str) -> int:
        assert table.isidentifier()
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    # ------------------------------------------------------------------ safe writes (Day 3)

    def apply_leave(self, emp_id: int, leave_type: str, start_date: str, end_date: str, days: int) -> dict:
        """Apply for leave. Returns status dict. Safe to repeat (checks for duplicate)."""
        with self.transaction() as c:
            # Check if already applied
            existing = c.execute(
                "SELECT id FROM leave_request WHERE employee_id = ? AND start_date = ? AND end_date = ? AND leave_type = ?",
                (emp_id, start_date, end_date, leave_type)).fetchone()
            if existing:
                return {"status": "already_applied", "request_id": existing["id"]}

            # Get current balance
            emp = c.execute("SELECT * FROM employee WHERE id = ?", (emp_id,)).fetchone()
            balance_field = f"{leave_type}_leave"
            current_balance = emp[balance_field]

            if current_balance < days:
                return {"status": "insufficient_balance", "available": current_balance, "requested": days}

            # Deduct balance
            c.execute(f"UPDATE employee SET {balance_field} = {balance_field} - ? WHERE id = ?", (days, emp_id))

            # Create request
            cur = c.execute(
                "INSERT INTO leave_request (employee_id, leave_type, start_date, end_date, days, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (emp_id, leave_type, start_date, end_date, days, self.clock()))

            return {"status": "applied", "request_id": cur.lastrowid, "days_deducted": days}

    def withdraw_leave(self, request_id: int) -> dict:
        """Withdraw a pending leave request. Returns status dict. Safe to repeat."""
        with self.transaction() as c:
            req = c.execute("SELECT * FROM leave_request WHERE id = ?", (request_id,)).fetchone()
            if req is None:
                return {"status": "not_found"}

            if req["status"] == "withdrawn":
                return {"status": "already_withdrawn"}

            # Restore balance
            balance_field = f"{req['leave_type']}_leave"
            c.execute(f"UPDATE employee SET {balance_field} = {balance_field} + ? WHERE id = ?",
                     (req["days"], req["employee_id"]))

            # Mark as withdrawn
            c.execute("UPDATE leave_request SET status = 'withdrawn' WHERE id = ?", (request_id,))

            return {"status": "withdrawn", "request_id": request_id, "days_restored": req["days"]}

    def record_notification(self, recipient: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        """Record a notification. Returns (notification_id, fresh). Safe to repeat."""
        cur = self.conn.execute(
            "INSERT INTO notification (recipient, message, dedupe_key, created_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (dedupe_key) DO NOTHING", (recipient, message, dedupe_key, self.clock()))
        if cur.rowcount == 1:
            return cur.lastrowid, True
        return self.conn.execute("SELECT id FROM notification WHERE dedupe_key = ?", (dedupe_key,)).fetchone()[0], False

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        """Run a side effect at most once per idempotency key; the effect and its key commit together."""
        with self.transaction() as c:
            row = c.execute("SELECT result FROM idempotency WHERE key = ?", (key,)).fetchone()
            if row is not None:
                return json.loads(row["result"]), False
            result = effect()
            c.execute("INSERT INTO idempotency (key, tool_name, result, created_at) VALUES (?, ?, ?, ?)",
                      (key, tool_name, json.dumps(result, default=str), self.clock()))
            return result, True
