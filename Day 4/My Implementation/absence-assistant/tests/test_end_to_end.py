"""The whole thing: queue, worker, supervisor, specialists, crash, replay."""
import pytest

from app.providers import demo_providers
from app.worker import Worker
from tests.conftest import SimulatedCrash

BALANCE_QUERY = "What's my leave balance?"


def ask(store, employee_id, text):
    thread = store.create_thread(employee_id)
    return thread, store.enqueue(thread, text, "mock")


def test_a_question_goes_all_the_way_through(store, db):
    thread, run_id = ask(store, "E001", BALANCE_QUERY)
    assert Worker(store, db, demo_providers(), worker_id="w").run_until_idle() == [(run_id, "succeeded")]
    run = store.get_run(run_id)
    assert [s["tool_name"] for s in run["steps"] if s["kind"] == "tool"] == ["ask_info"]
    assert "15 days annual" in store.load_history(thread)[-1]["text"]


def test_policy_refusal_is_a_normal_answer(store, db):
    thread, run_id = ask(store, "E002", "Can I apply for 5 days annual leave from October 1 to October 5?")
    Worker(store, db, demo_providers(), worker_id="w").run_until_idle()
    assert store.get_run(run_id)["status"] == "succeeded"
    assert "don't have enough" in store.load_history(thread)[-1]["text"] or "0 days" in store.load_history(thread)[-1]["text"]
    assert db.count("leave_request") == 1 and db.count("notification") == 0  # seed has 1 request


def test_crash_inside_specialist_after_apply_does_not_duplicate(store, db, clock):
    """Crash right after apply_leave commits. Worker B resumes and doesn't duplicate."""
    from app.providers import ModelTurn, PositionalMock, ToolCall

    # Custom scripted model that applies leave
    def _call(name, **args):
        return ModelTurn(text=None, tool_calls=[ToolCall(name, args)], tokens_in=100, tokens_out=10)

    providers = {
        "supervisor": PositionalMock([
            _call("ask_desk", request="Apply for 3 days casual leave from 2026-10-10 to 2026-10-12 and notify manager.")
        ]),
        "info": PositionalMock([]),
        "desk": PositionalMock([
            _call("check_can_apply", leave_type="casual", days=3),
            ModelTurn(text=None, tool_calls=[
                ToolCall("apply_leave", {"leave_type": "casual", "start_date": "2026-10-10", "end_date": "2026-10-12", "days": 3}),
                ToolCall("notify_manager", {"message": "Employee E001 applied for 3 days casual leave"})
            ]),
            ModelTurn(text="(mock) Leave applied and manager notified.")
        ])
    }

    _, run_id = ask(store, "E001", "Apply 3 days casual leave")
    real_once = db.once

    def once_then_die(key, tool_name, effect):
        result = real_once(key, tool_name, effect)
        if tool_name == "apply_leave":
            raise SimulatedCrash()
        return result

    db.once = once_then_die
    with pytest.raises(SimulatedCrash):
        Worker(store, db, providers, worker_id="A", lease_seconds=30).run_once()
    db.once = real_once

    # Check leave was applied
    assert db.count("leave_request") == 2  # seed has 1
    assert store.get_run(run_id)["status"] == "running"

    # Worker B resumes
    clock.advance(31)
    assert Worker(store, db, providers, worker_id="B", lease_seconds=30).run_until_idle() == [(run_id, "succeeded")]
    # Should still be only 2 requests, not duplicated
    assert db.count("leave_request") == 2
    assert db.count("notification") == 1
    emp = db.get_employee("E001")
    assert emp["casual_leave"] == 2  # 5 - 3


def test_asking_twice_still_one_request(store, db):
    from app.providers import ModelTurn, PositionalMock, ToolCall

    def _call(name, **args):
        return ModelTurn(text=None, tool_calls=[ToolCall(name, args)], tokens_in=100, tokens_out=10)

    providers = {
        "supervisor": PositionalMock([
            _call("ask_desk", request="Apply for 2 days sick leave from 2026-10-15 to 2026-10-16.")
        ]),
        "info": PositionalMock([]),
        "desk": PositionalMock([
            _call("check_can_apply", leave_type="sick", days=2),
            _call("apply_leave", leave_type="sick", start_date="2026-10-15", end_date="2026-10-16", days=2),
            ModelTurn(text="(mock) Leave applied.")
        ])
    }

    for _ in range(2):
        ask(store, "E001", "Apply 2 days sick leave")
    Worker(store, db, providers, worker_id="w").run_until_idle()
    # Should still be only 2 requests total (1 seed + 1 new)
    assert db.count("leave_request") == 2
