"""A long-running worker that polls the queue and executes runs.

    python -m scripts.worker

In another terminal:
    python -m scripts.ask --employee E001 "What's my leave balance?"
"""
import logging
import sys
from dotenv import load_dotenv
load_dotenv()

from scripts._term import CYAN, DIM, GREEN, RED, RESET

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")


def print_step(s: dict) -> None:
    if s.get("kind") == "delegate":
        print(f"  {CYAN}→ {s['tool']}{RESET} {DIM}{s['args']}{RESET}")
    elif s.get("kind") == "tool":
        agent = s.get("agent", "?")
        colour = GREEN if s.get("ok") else RED
        replay = " (replayed)" if s.get("replayed") else ""
        print(f"    {agent} {colour}{s['tool']}{RESET}{replay} {DIM}{s.get('ms')}ms{RESET}")
    elif s.get("kind") == "model" and s.get("text"):
        print(f"  {s['agent']} says: {s['text'][:80]}")


def main() -> None:
    from app.config import make_providers, open_stores
    from app.worker import Worker

    store, db = open_stores()
    providers = make_providers(mock=False)
    worker = Worker(store, db, providers, on_step=print_step)
    print(f"worker {worker.worker_id} polling every second (Ctrl-C to stop)")
    try:
        worker.run_forever(poll_seconds=1.0)
    except KeyboardInterrupt:
        print("\nstopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
