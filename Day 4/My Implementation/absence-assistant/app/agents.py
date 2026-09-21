"""Day 4: three agents. A supervisor talks to the employee and delegates to two specialists.

    employee ──▶ supervisor ──ask_info──▶ info agent  (get_leave_balance, list_holidays)
                            └─ask_desk──▶ desk agent   (get_employee, check_can_apply,
                                                        apply_leave, withdraw_leave, notify_manager)

Each specialist is an ordinary agent loop with its own system prompt and its own small tool set.
To the supervisor, a specialist is just a tool: "agent as tool", the simplest multi-agent pattern.
"""
import time
from collections.abc import Callable

from app.idempotency import idempotency_key
from app.leave_db import LeaveDb
from app.providers import AgentError
from app.tools.leave_tools import InfoTools, DeskTools, Toolset

SPECIALIST_MAX_STEPS = 6

SUPERVISOR_SYSTEM = """You are the Absence Assistant, talking to the employee with ID {employee_id}.
You never check balances or apply for leave yourself. Delegate:
- ask_info for checking leave balances and holiday calendars;
- ask_desk for anything about this employee's leave requests, applications or notifications.
Give each specialist a complete, specific request, including request IDs once you know them.
Then answer the employee briefly, using only what the specialists reported."""

INFO_SYSTEM = """You are the information specialist of an absence management system. Check leave balances
and list holidays. You cannot apply for leave or make any changes. Be brief."""

DESK_SYSTEM = """You are the leave desk specialist, acting for employee {employee_id} only.
Always call check_can_apply before apply_leave. Never decide policy yourself: report the reasons
the tools give. Confirm a successful leave application with notify_manager. Report what you did, briefly."""


def run_tool(toolset: Toolset, db: LeaveDb, key: str, name: str, args: dict) -> tuple[dict, bool]:
    """Run one tool call for any agent. Returns (result, replayed). Never raises, except AgentError.

    Side effects run at most once per key (Day 3); replayed is True when the stored result was returned
    and nothing was done. Delegations hand the key down, so the specialist's side effects get keys
    derived from it: a replayed delegation replays its side effects safely too.
    """
    try:
        if name in toolset.DELEGATES:
            return toolset.delegate(name, args, key), False
        if name in toolset.SIDE_EFFECTS:
            result, fresh = db.once(key, name, lambda: toolset.call(name, args))
            return result, not fresh
        return toolset.call(name, args), False
    except AgentError:
        raise
    except NotImplementedError:
        return {"error": "not_implemented", "hint": f"{name} is not available yet."}, False
    except Exception as e:
        return {"error": "tool_failed", "hint": f"{name} failed ({type(e).__name__}). Try another way or tell the user."}, False


def run_specialist(agent: str, system: str, toolset: Toolset, *, db: LeaveDb, provider, task: str,
                   parent_key: str, on_step: Callable[[dict], None] | None = None) -> dict:
    """A specialist's whole agent loop, run inside one tool call of the supervisor."""
    contents = [{"role": "user", "text": task}]
    functions = list(toolset.functions().values())
    used = []
    seq = 0
    while seq < SPECIALIST_MAX_STEPS:
        turn = provider.generate(system, contents, functions)
        seq += 1
        if not turn.tool_calls:
            return {"agent": agent, "answer": turn.text or "", "tools_used": used}
        contents.append({"role": "model", "text": turn.text, "raw": turn.raw,
                         "tool_calls": [{"name": c.name, "args": c.args} for c in turn.tool_calls]})
        for call in turn.tool_calls:
            seq += 1
            key = idempotency_key(parent_key, seq, call.name, call.args)
            started = time.perf_counter()
            result, replayed = run_tool(toolset, db, key, call.name, call.args)
            used.append(call.name)
            if on_step:
                on_step({"agent": agent, "kind": "tool", "tool": call.name, "args": call.args, "result": result,
                         "ok": "error" not in result, "replayed": replayed,
                         "ms": round((time.perf_counter() - started) * 1000)})
            contents.append({"role": "tool", "name": call.name, "result": result})
    return {"agent": agent, "error": "specialist_step_limit", "tools_used": used,
            "hint": "The specialist could not finish. Tell the employee to try a simpler request."}


class SupervisorTools(Toolset):
    """The supervisor's only tools are the two specialists."""

    TOOL_NAMES = ("ask_info", "ask_desk")
    DELEGATES = ("ask_info", "ask_desk")

    def __init__(self, db: LeaveDb, providers: dict, employee_id: str, on_step=None):
        self.db, self.providers, self.employee_id, self.on_step = db, providers, employee_id, on_step

    def ask_info(self, question: str) -> dict:
        """Ask the information specialist to check leave balances or list holidays.

        Use for "how many leaves do I have", "what's my balance", "list holidays". It cannot apply for leave.

        Args:
            question: A complete request, e.g. "What is the leave balance for employee E001?"

        Returns:
            {"agent": "info", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def ask_desk(self, request: str) -> dict:
        """Ask the leave desk specialist to act on this employee's account. It CAN CHANGE DATA:
        apply for leave, withdraw requests and send manager notifications.

        Use for applications, withdrawals, "what leaves do I have pending", and confirmations.
        Include the request_id from get_employee when withdrawing. The desk always acts for the current employee only.

        Args:
            request: A complete instruction, e.g. "Apply for 5 days annual leave from 2026-10-01 to 2026-10-05 and notify manager."

        Returns:
            {"agent": "desk", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def delegate(self, name: str, args: dict, key: str) -> dict:
        bad = self.call_check(name, args)
        if bad:
            return bad
        if self.on_step:
            self.on_step({"agent": "supervisor", "kind": "delegate", "tool": name, "args": args})
        if name == "ask_info":
            return run_specialist("info", INFO_SYSTEM, InfoTools(self.db), db=self.db,
                                  provider=self.providers["info"], task=args["question"],
                                  parent_key=key, on_step=self.on_step)
        return run_specialist("desk", DESK_SYSTEM.format(employee_id=self.employee_id), DeskTools(self.db, self.employee_id),
                              db=self.db, provider=self.providers["desk"], task=args["request"],
                              parent_key=key, on_step=self.on_step)

    def call_check(self, name: str, args: dict) -> dict | None:
        """Validate a delegation's arguments the same way dispatch validates any tool call."""
        field = "question" if name == "ask_info" else "request"
        if set(args) != {field} or not isinstance(args[field], str) or not args[field].strip():
            return {"error": "invalid_arguments", "hint": f"{name} takes one non-empty string: {field}."}
        return None
