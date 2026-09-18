import threading

from app.memory import RunStore
from app.placement_db import PlacementDb
from app.providers import ModelTurn, PositionalMock, ToolCall
from app.worker import Worker


def test_two_workers_two_runs_one_slot(db_files):
    """
    Two independent workers process two independent runs.

    Both runs should complete successfully, but only one student
    can obtain interview slot 3.
    """
    agent_db, placement_db = db_files

    # Independent connections
    store_a = RunStore(agent_db)
    store_b = RunStore(agent_db)

    placement_a = PlacementDb(placement_db)
    placement_b = PlacementDb(placement_db)

    turns_a = [
        ModelTurn(
            text=None,
            tool_calls=[
                ToolCall(
                    "apply_to_drive",
                    {"student_id": "22IT017", "drive_id": 2},
                )
            ],
        ),
        ModelTurn(
            text=None,
            tool_calls=[
                ToolCall(
                    "book_interview_slot",
                    {"student_id": "22IT017", "slot_id": 3},
                )
            ],
        ),
        ModelTurn(text="done"),
    ]

    turns_b = [
        ModelTurn(
            text=None,
            tool_calls=[
                ToolCall(
                    "apply_to_drive",
                    {"student_id": "22CS045", "drive_id": 2},
                )
            ],
        ),
        ModelTurn(
            text=None,
            tool_calls=[
                ToolCall(
                    "book_interview_slot",
                    {"student_id": "22CS045", "slot_id": 3},
                )
            ],
        ),
        ModelTurn(text="done"),
    ]

    thread_a = store_a.create_thread("22IT017")
    thread_b = store_b.create_thread("22CS045")

    run_a = store_a.enqueue(thread_a, "apply and book", "mock")
    run_b = store_b.enqueue(thread_b, "apply and book", "mock")

    worker_a = Worker(
        store=store_a,
        placement=placement_a,
        provider=PositionalMock(turns_a),
        worker_id="worker-a",
    )

    worker_b = Worker(
        store=store_b,
        placement=placement_b,
        provider=PositionalMock(turns_b),
        worker_id="worker-b",
    )

    t1 = threading.Thread(target=worker_a.run_until_idle)
    t2 = threading.Thread(target=worker_b.run_until_idle)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    run_a_data = store_a.get_run(run_a)
    run_b_data = store_b.get_run(run_b)

    # Losing the race is not a run failure.
    assert run_a_data["status"] == "succeeded"
    assert run_b_data["status"] == "succeeded"

    slot_results = []

    for run_data in (run_a_data, run_b_data):
        for step in run_data["steps"]:
            if step["tool_name"] == "book_interview_slot":
                slot_results.append(step["result"])

    assert len(slot_results) == 2

    booked = sum(
        result.get("status") == "booked"
        for result in slot_results
    )

    slot_taken = sum(
        result.get("error") == "slot_taken"
        for result in slot_results
    )

    assert booked == 1
    assert slot_taken == 1

    row = placement_a.conn.execute(
        """
        SELECT student_id
        FROM interview_slot
        WHERE id = 3
        """
    ).fetchone()

    assert row["student_id"] is not None


def test_truly_concurrent_claims_have_one_winner(db_files):
    """
    Eight threads attempt to claim the same slot at the same moment.

    All threads use separate database connections.
    Exactly one claim should succeed.
    """
    _, placement_db = db_files

    setup_db = PlacementDb(placement_db)

    version = setup_db.conn.execute(
        """
        SELECT version
        FROM interview_slot
        WHERE id = 3
        """
    ).fetchone()["version"]

    barrier = threading.Barrier(8)

    results = []
    results_lock = threading.Lock()
    errors = []

    def attempt(student_id):
        db = PlacementDb(placement_db)

        barrier.wait()

        try:
            success = db.claim_slot(
                slot_id=3,
                student_id=student_id,
                expected_version=version,
            )

            with results_lock:
                results.append(success)

        except Exception as e:
            with results_lock:
                errors.append(e)

    student_ids = [1, 2, 3, 4, 1, 2, 3, 4]

    threads = [
        threading.Thread(target=attempt, args=(sid,))
        for sid in student_ids
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert not errors
    assert results.count(True) == 1
    assert results.count(False) == 7

    new_version = setup_db.conn.execute(
        """
        SELECT version
        FROM interview_slot
        WHERE id = 3
        """
    ).fetchone()["version"]

    assert new_version == version + 1