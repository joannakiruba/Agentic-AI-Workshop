"""Unit tests for the leave tools."""


def test_get_leave_balance(db):
    from app.tools.leave_tools import InfoTools

    tools = InfoTools(db)
    result = tools.get_leave_balance("E001")
    assert result["employee_id"] == "E001"
    assert result["name"] == "Priya Raman"
    assert result["annual_leave"] == 15
    assert result["sick_leave"] == 10
    assert result["casual_leave"] == 5


def test_list_holidays(db):
    from app.tools.leave_tools import InfoTools

    tools = InfoTools(db)
    result = tools.list_holidays()
    assert len(result["holidays"]) == 5
    assert result["holidays"][0]["date"] == "2026-01-26"
    assert result["holidays"][0]["name"] == "Republic Day"


def test_check_can_apply_sufficient_balance(db):
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E001")
    result = tools.check_can_apply("annual", 5)
    assert result["can_apply"] is True
    assert result["current_balance"] == 15


def test_check_can_apply_insufficient_balance(db):
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E002")
    result = tools.check_can_apply("annual", 5)
    assert result["can_apply"] is False
    assert "insufficient annual leave" in result["reasons"][0]


def test_apply_leave_success(db):
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E001")
    result = tools.apply_leave("annual", "2026-10-01", "2026-10-05", 5)
    assert result["status"] == "applied"
    assert result["days_deducted"] == 5
    # Check balance deducted
    emp = db.get_employee("E001")
    assert emp["annual_leave"] == 10  # 15 - 5


def test_apply_leave_insufficient_balance(db):
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E002")
    result = tools.apply_leave("annual", "2026-10-01", "2026-10-05", 5)
    assert "error" in result
    assert result["error"] == "not_allowed"


def test_apply_leave_idempotency(db):
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E001")
    # Apply first time
    result1 = tools.apply_leave("annual", "2026-10-01", "2026-10-05", 5)
    assert result1["status"] == "applied"
    # Apply again with same params
    result2 = tools.apply_leave("annual", "2026-10-01", "2026-10-05", 5)
    assert result2["status"] == "already_applied"
    # Balance should only be deducted once
    emp = db.get_employee("E001")
    assert emp["annual_leave"] == 10


def test_withdraw_leave(db):
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E003")
    # E003 has a pending leave (request id 1 from seed)
    result = tools.withdraw_leave(1)
    assert result["status"] == "withdrawn"
    assert result["days_restored"] == 3
    # Check balance restored
    emp = db.get_employee("E003")
    assert emp["annual_leave"] == 23  # was 20, no change in seed, but now withdrawn request


def test_notify_manager(db):
    from app.tools.leave_tools import DeskTools

    tools = DeskTools(db, "E001")
    result = tools.notify_manager("Employee E001 applied for 5 days leave")
    assert result["status"] == "queued"
    assert result["duplicate"] is False
    # Second time same day
    result2 = tools.notify_manager("Employee E001 applied for 5 days leave")
    assert result2["duplicate"] is True
