"""Ask a question from the command line, enqueue it, wait for an answer.

    python -m scripts.ask --employee E001 "What's my leave balance?"

Requires a worker running (scripts/worker.py), or run the demo (scripts/demo.py) instead.
"""
import argparse
import time
from dotenv import load_dotenv
load_dotenv()

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--employee", required=True, help="Employee ID like E001")
    p.add_argument("question", help="Your question")
    a = p.parse_args()

    from app.config import make_providers, open_stores

    store, db = open_stores()
    providers = make_providers(mock=False)

    thread = store.create_thread(a.employee)
    run_id = store.enqueue(thread, a.question, providers["supervisor"].model)
    print(f"enqueued {run_id} on thread {thread}")

    while True:
        run = store.get_run(run_id)
        if run["status"] in ("succeeded", "failed", "cancelled", "dead"):
            if run["status"] == "succeeded":
                print(f"\n{store.load_history(thread)[-1]['text']}")
            else:
                print(f"\nrun {run['status']}: {run.get('error_code', '(no error)')}")
            return
        time.sleep(0.5)


if __name__ == "__main__":
    main()
