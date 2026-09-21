"""Pytest fixtures for all tests."""
import time

import pytest


class SimulatedCrash(BaseException):
    """Like a SIGKILL: nothing ordinary catches it."""


class FakeClock:
    """A clock you can advance by hand. Used to test lease expiry and reaping."""

    def __init__(self):
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(clock):
    from app.memory import RunStore

    s = RunStore(":memory:", clock=clock)
    s.migrate()
    return s


@pytest.fixture
def db(clock):
    from app.leave_db import LeaveDb

    d = LeaveDb(":memory:", clock=clock)
    d.migrate()
    return d
