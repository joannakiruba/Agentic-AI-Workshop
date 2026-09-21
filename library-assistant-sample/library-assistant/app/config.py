import os

from app.library_db import LibraryDb
from app.memory import RunStore

AGENT_DB = os.environ.get("AGENT_DB", "agent.db")
LIBRARY_DB = os.environ.get("LIBRARY_DB", "library.db")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


def open_stores() -> tuple[RunStore, LibraryDb]:
    store, db = RunStore(AGENT_DB), LibraryDb(LIBRARY_DB)
    store.migrate()
    db.migrate()
    return store, db


def make_providers(mock: bool, slow: float = 0.0) -> dict:
    """One provider per agent. With Gemini all three share one client; each keeps its own prompt and tools."""
    if mock:
        from app.providers import demo_providers

        return demo_providers(slow)
    from app.providers import GeminiProvider

    gemini = GeminiProvider(GEMINI_MODEL)
    return {"supervisor": gemini, "catalogue": gemini, "desk": gemini}