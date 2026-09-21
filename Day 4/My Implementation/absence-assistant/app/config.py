import os

AGENT_DB = os.environ.get("AGENT_DB", "agent.db")
LEAVE_DB = os.environ.get("LEAVE_DB", "leave.db")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# Supabase configuration
USE_SUPABASE = os.environ.get("USE_SUPABASE", "false").lower() == "true"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")


def open_stores():
    """Open database stores. Returns (RunStore, LeaveDb)."""
    from app.memory import RunStore

    if USE_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
        print(f"🔗 Connecting to Supabase: {SUPABASE_URL}")
        from app.supabase_client import SupabaseLeaveDb

        # Agent DB stays as SQLite (for now)
        store = RunStore(AGENT_DB)
        store.migrate()

        # Leave DB uses Supabase
        db = SupabaseLeaveDb(SUPABASE_URL, SUPABASE_KEY)
        db.migrate()

        print("✅ Supabase connection established")
        return store, db
    else:
        print("📁 Using local SQLite databases")
        from app.leave_db import LeaveDb

        store = RunStore(AGENT_DB)
        db = LeaveDb(LEAVE_DB)
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
    return {"supervisor": gemini, "info": gemini, "desk": gemini}
