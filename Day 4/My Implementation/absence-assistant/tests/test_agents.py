"""Unit tests for agent delegation and tool routing."""
import pytest

from app.agents import SupervisorTools
from app.providers import ModelTurn, PositionalMock, ToolCall


def test_supervisor_delegates_to_info(db):
    from app.providers import demo_providers

    providers = demo_providers()
    tools = SupervisorTools(db, providers, "E001")
    result = tools.delegate("ask_info", {"question": "What is the leave balance for employee E001?"}, "test-key")
    assert result["agent"] == "info"
    assert "15 days annual" in result["answer"]


def test_supervisor_delegates_to_desk(db):
    from app.providers import demo_providers

    providers = demo_providers()
    tools = SupervisorTools(db, providers, "E002")
    result = tools.delegate("ask_desk", {"request": "Apply for 5 days annual leave from 2026-10-01 to 2026-10-05 and notify manager."}, "test-key")
    assert result["agent"] == "desk"
    assert "Cannot apply" in result["answer"]


def test_info_agent_is_read_only(db):
    from app.tools.leave_tools import InfoTools

    tools = InfoTools(db)
    assert tools.SIDE_EFFECTS == ()
    assert "apply_leave" not in tools.TOOL_NAMES
    assert "withdraw_leave" not in tools.TOOL_NAMES


def test_desk_agent_has_side_effects(db):
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E001")
    assert "apply_leave" in tools.SIDE_EFFECTS
    assert "withdraw_leave" in tools.SIDE_EFFECTS
    assert "notify_manager" in tools.SIDE_EFFECTS


def test_desk_enforces_check_before_apply(db):
    """The apply_leave tool internally calls check_can_apply, enforcing the rule even if the model skips it."""
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E002")  # E002 has 0 annual leave
    # Model tries to apply without checking
    result = tools.apply_leave("annual", "2026-10-01", "2026-10-05", 5)
    assert "error" in result
    assert result["error"] == "not_allowed"
    assert "insufficient" in result["reasons"][0]
