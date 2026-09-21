"""The leave system's tools, split between two specialist agents. Descriptions are prompts (Day 2)."""
from datetime import datetime, timezone

from app.idempotency import notification_dedupe_key
from app.leave_db import LeaveDb
from app.tools.dispatch import dispatch


class Toolset:
    SIDE_EFFECTS: tuple[str, ...] = ()     # run through LeaveDb.once with an idempotency key (Day 3)
    DELEGATES: tuple[str, ...] = ()        # hand work to another agent (Day 4)
    TOOL_NAMES: tuple[str, ...] = ()

    def functions(self) -> dict:
        return {n: getattr(self, n) for n in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)


class InfoTools(Toolset):
    """Read-only. The info agent can look, never change."""

    TOOL_NAMES = ("get_leave_balance", "list_holidays")

    def __init__(self, db: LeaveDb):
        self.db = db

    def get_leave_balance(self, employee_id: str) -> dict:
        """Get an employee's current leave balance for all leave types.

        Use when the employee asks "how many leaves do I have", "what's my balance", or similar.
        Read-only: changes nothing. To apply for leave, that is the desk's job, not this tool.

        Args:
            employee_id: Employee ID like "E001".

        Returns:
            {"employee_id", "name", "annual_leave", "sick_leave", "casual_leave"} in days.
        """
        balance = self.db.get_leave_balance(employee_id)
        if balance is None:
            return {"error": "unknown_employee", "hint": "Employee not found in the system."}
        return balance

    def list_holidays(self, start_date: str | None = None, end_date: str | None = None) -> dict:
        """List public and optional holidays, optionally filtered by date range.

        Use when the employee asks "what are the holidays", "is <date> a holiday", or to check
        if their leave dates overlap with holidays. Read-only: changes nothing.

        Args:
            start_date: Optional ISO date (YYYY-MM-DD) to filter from.
            end_date: Optional ISO date (YYYY-MM-DD) to filter to.

        Returns:
            {"holidays": [{"date", "name", "type"}]} sorted by date.
        """
        holidays = self.db.list_holidays(start_date, end_date)
        return {"holidays": holidays}


class DeskTools(Toolset):
    """The leave desk, bound to ONE employee. The model cannot pick a different employee_id."""

    TOOL_NAMES = ("get_employee", "check_can_apply", "apply_leave", "withdraw_leave", "notify_manager")
    SIDE_EFFECTS = ("apply_leave", "withdraw_leave", "notify_manager")

    def __init__(self, db: LeaveDb, employee_id: str, clock=lambda: datetime.now(timezone.utc)):
        self.db, self.employee_id, self.clock = db, employee_id, clock

    def _employee(self) -> dict:
        emp = self.db.get_employee(self.employee_id)
        if emp is None:
            raise LookupError(f"employee {self.employee_id} not found")
        return emp

    def get_employee(self) -> dict:
        """Get the current employee's leave record: name, department, balances and pending requests.

        Use for "what leaves do I have pending", "show my details". Read-only: changes nothing.

        Returns:
            {"employee_id", "name", "dept", "annual_leave", "sick_leave", "casual_leave",
             "pending_requests": [{"id", "leave_type", "start_date", "end_date", "days", "status"}]}.
        """
        emp = self._employee()
        return {
            "employee_id": emp["employee_id"],
            "name": emp["name"],
            "dept": emp["dept"],
            "annual_leave": emp["annual_leave"],
            "sick_leave": emp["sick_leave"],
            "casual_leave": emp["casual_leave"],
            "pending_requests": self.db.active_leave_requests(emp["id"])
        }

    def check_can_apply(self, leave_type: str, days: int) -> dict:
        """Check if the current employee can apply for leave of given type and duration.

        Use BEFORE apply_leave, and whenever the employee asks "can I apply". The decision comes from
        the employee's current balance and policy table: never decide it yourself. Read-only: changes nothing.

        Args:
            leave_type: One of "annual", "sick", "casual".
            days: Number of days requested.

        Returns:
            {"can_apply": bool, "reasons": [str], "current_balance": int}.
            Every reason is a rule the request currently breaks.
        """
        emp = self._employee()
        reasons = []
        balance_field = f"{leave_type}_leave"
        current_balance = emp[balance_field]

        if current_balance < days:
            reasons.append(f"insufficient {leave_type} leave: {current_balance} days available, {days} requested")

        max_days = self.db.policy("max_continuous_days")
        if days > max_days:
            reasons.append(f"requested {days} days exceeds policy maximum of {max_days} continuous days")

        return {"can_apply": not reasons, "reasons": reasons, "current_balance": current_balance}

    def apply_leave(self, leave_type: str, start_date: str, end_date: str, days: int) -> dict:
        """Apply for leave for the current employee. CHANGES DATA: deducts from leave balance.

        Use only when the employee has asked to apply for leave and check_can_apply allowed it.
        Applying again for the same dates is safe and returns the existing request.

        Args:
            leave_type: One of "annual", "sick", "casual".
            start_date: ISO date YYYY-MM-DD.
            end_date: ISO date YYYY-MM-DD.
            days: Number of working days in this leave period.

        Returns:
            {"status": "applied" | "already_applied", "request_id", "days_deducted"?}, or an error:
            not_allowed (with reasons), insufficient_balance, or unknown_employee.
        """
        verdict = self.check_can_apply(leave_type, days)
        if not verdict["can_apply"]:
            return {"error": "not_allowed", "reasons": verdict["reasons"],
                    "hint": "Explain the reasons to the employee. Do not retry."}

        emp = self._employee()
        result = self.db.apply_leave(emp["id"], leave_type, start_date, end_date, days)

        if result["status"] == "insufficient_balance":
            return {"error": "insufficient_balance",
                    "hint": f"Only {result['available']} days available, {result['requested']} requested."}

        return result

    def withdraw_leave(self, request_id: int) -> dict:
        """Withdraw a pending leave request for the current employee. CHANGES DATA: restores balance.

        Use when the employee asks to cancel or withdraw a leave request. Safe to repeat.

        Args:
            request_id: The leave request ID from get_employee or apply_leave.

        Returns:
            {"status": "withdrawn" | "already_withdrawn", "request_id", "days_restored"?}, or
            {"status": "not_found"} if the request doesn't exist.
        """
        result = self.db.withdraw_leave(request_id)
        if result["status"] == "not_found":
            return {"error": "not_found", "hint": "No such leave request. Check the request_id."}
        return result

    def notify_manager(self, message: str) -> dict:
        """Send the manager a notification message. CHANGES DATA: a message goes out.

        Use to notify manager when a leave is applied or withdrawn. The same message on the
        same day is sent only once. Never use it to answer a question; reply in the chat instead.

        Args:
            message: 1 to 200 characters.

        Returns:
            {"notification_id", "status": "queued", "duplicate": bool}.
        """
        if not message.strip() or len(message) > 200:
            return {"error": "invalid_message", "hint": "message must be 1 to 200 characters."}
        key = notification_dedupe_key("manager", message, self.clock().date())
        notification_id, created = self.db.record_notification("manager", message, key)
        return {"notification_id": notification_id, "status": "queued", "duplicate": not created}
