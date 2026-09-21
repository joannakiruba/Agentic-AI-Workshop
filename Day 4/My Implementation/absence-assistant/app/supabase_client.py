"""Supabase client for leave management system using supabase-py library."""
import os
import json
import time
from collections.abc import Callable
from typing import Any

try:
    from supabase import create_client, Client
except ImportError:
    raise ImportError(
        "supabase library not installed. Run: pip install supabase"
    )


class SupabaseLeaveDb:
    """Leave database using Supabase Python client."""

    def __init__(self, url: str, key: str, clock: Callable[[], float] = time.time):
        """
        Initialize Supabase client.

        Args:
            url: Supabase project URL
            key: Supabase anon key or service role key
            clock: Time function for timestamps
        """
        self.client: Client = create_client(url, key)
        self.clock = clock

    # ------------------------------------------------------------------ reads

    def get_employee(self, employee_id: str) -> dict | None:
        """Get employee by employee_id."""
        try:
            response = self.client.table("employee").select("*").eq("employee_id", employee_id).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error getting employee: {e}")
            return None

    def policy(self, name: str) -> int:
        """Get policy value by name."""
        response = self.client.table("policy").select("value").eq("name", name).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["value"]
        raise ValueError(f"Policy {name} not found")

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
        response = self.client.table("leave_request").select("*").eq(
            "employee_id", emp_id
        ).eq("status", "pending").order("start_date").execute()
        return response.data

    def list_holidays(self, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
        """List holidays, optionally filtered by date range."""
        query = self.client.table("holiday").select("date, name, type").order("date")

        if start_date and end_date:
            query = query.gte("date", start_date).lte("date", end_date)

        response = query.execute()
        return response.data

    def get_leave_request(self, request_id: int) -> dict | None:
        """Get a specific leave request."""
        response = self.client.table("leave_request").select("*").eq("id", request_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None

    def count(self, table):
        response = (
            self.client
            .table(table)
            .select("*", count="exact")
            .limit(1)
            .execute()
        )
        return response.count or 0

    # ------------------------------------------------------------------ safe writes

    def apply_leave(self, emp_id: int, leave_type: str, start_date: str, end_date: str, days: int) -> dict:
        """
        Apply for leave. Returns status dict. Safe to repeat (checks for duplicate).

        Note: This implementation has limitations compared to SQL transactions.
        For production, use PostgreSQL functions or RPC calls.
        """
        try:
            # Check if already applied
            existing = self.client.table("leave_request").select("id").match({
                "employee_id": emp_id,
                "start_date": start_date,
                "end_date": end_date,
                "leave_type": leave_type
            }).execute()

            if existing.data and len(existing.data) > 0:
                return {"status": "already_applied", "request_id": existing.data[0]["id"]}

            # Get current balance
            emp_response = self.client.table("employee").select("*").eq("id", emp_id).execute()
            if not emp_response.data:
                return {"status": "employee_not_found"}

            emp = emp_response.data[0]
            balance_field = f"{leave_type}_leave"
            current_balance = emp[balance_field]

            if current_balance < days:
                return {"status": "insufficient_balance", "available": current_balance, "requested": days}

            # Deduct balance
            new_balance = current_balance - days
            self.client.table("employee").update({balance_field: new_balance}).eq("id", emp_id).execute()

            # Create request
            request_data = {
                "employee_id": emp_id,
                "leave_type": leave_type,
                "start_date": start_date,
                "end_date": end_date,
                "days": days,
                "status": "pending"
            }
            response = self.client.table("leave_request").insert(request_data).execute()

            if response.data and len(response.data) > 0:
                return {"status": "applied", "request_id": response.data[0]["id"], "days_deducted": days}
            else:
                return {"status": "error", "message": "Failed to create leave request"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def withdraw_leave(self, request_id: int) -> dict:
        """Withdraw a pending leave request. Returns status dict. Safe to repeat."""
        try:
            # Get request
            req_response = self.client.table("leave_request").select("*").eq("id", request_id).execute()
            if not req_response.data or len(req_response.data) == 0:
                return {"status": "not_found"}

            req = req_response.data[0]

            if req["status"] == "withdrawn":
                return {"status": "already_withdrawn"}

            # Restore balance
            balance_field = f"{req['leave_type']}_leave"
            emp = self.client.table("employee").select(balance_field).eq("id", req["employee_id"]).execute().data[0]
            new_balance = emp[balance_field] + req["days"]

            self.client.table("employee").update({balance_field: new_balance}).eq("id", req["employee_id"]).execute()

            # Mark as withdrawn
            self.client.table("leave_request").update({"status": "withdrawn"}).eq("id", request_id).execute()

            return {"status": "withdrawn", "request_id": request_id, "days_restored": req["days"]}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def record_notification(self, recipient: str, message: str, dedupe_key: str) -> tuple[int, bool]:
        """Record a notification. Returns (notification_id, fresh). Safe to repeat."""
        try:
            # Check if already exists
            existing = self.client.table("notification").select("id").eq("dedupe_key", dedupe_key).execute()
            if existing.data and len(existing.data) > 0:
                return existing.data[0]["id"], False

            # Insert new notification
            response = self.client.table("notification").insert({
                "recipient": recipient,
                "message": message,
                "dedupe_key": dedupe_key
            }).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]["id"], True
            else:
                raise Exception("Failed to insert notification")

        except Exception as e:
            print(f"Error recording notification: {e}")
            raise

    def once(self, key: str, tool_name: str, effect: Callable[[], dict]) -> tuple[dict, bool]:
        """
        Run a side effect at most once per idempotency key.

        Note: This is not truly atomic without database-level transactions.
        For production, implement as a PostgreSQL stored procedure.
        """
        try:
            # Check if key exists
            existing = self.client.table("idempotency").select("result").eq("key", key).execute()
            if existing.data and len(existing.data) > 0:
                return json.loads(existing.data[0]["result"]), False

            # Execute effect
            result = effect()

            # Store key and result
            self.client.table("idempotency").insert({
                "key": key,
                "tool_name": tool_name,
                "result": json.dumps(result, default=str)
            }).execute()

            return result, True

        except Exception as e:
            print(f"Error in idempotency check: {e}")
            # If there's a conflict (race condition), try to fetch the existing result
            try:
                existing = self.client.table("idempotency").select("result").eq("key", key).execute()
                if existing.data and len(existing.data) > 0:
                    return json.loads(existing.data[0]["result"]), False
            except:
                pass
            raise

    def migrate(self) -> None:
        """
        Migration placeholder.
        For Supabase, run the schema in the SQL Editor instead.
        This method checks if tables exist.
        """
        try:
            # Simple check if employee table exists
            self.client.table("employee").select("id").limit(1).execute()
            print("✅ Supabase tables already exist")
        except Exception as e:
            print(f"⚠️  Warning: Could not verify tables exist: {e}")
            print("Please run the schema in Supabase SQL Editor (see SUPABASE_SETUP.md)")
