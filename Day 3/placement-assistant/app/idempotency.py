"""Stable fingerprints for side effects. Hashing, used for exactly-once."""
import hashlib  # noqa: F401
import json  # noqa: F401
import uuid
from datetime import date


def canonical_json(value) -> str:
    def normalize(v):
        if isinstance(v, float) and v.is_integer():
            return int(v)

        if isinstance(v, dict):
            return {k: normalize(val) for k, val in v.items()}

        if isinstance(v, list):
            return [normalize(item) for item in v]

        return v

    return json.dumps(
        normalize(value),
        sort_keys=True,
        separators=(",", ":"),
    )


def idempotency_key(run_id: str, step_seq: int, tool_name: str, args: dict) -> str:
    payload = canonical_json([run_id, step_seq, tool_name, args])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def notification_dedupe_key(roll_no: str, message: str, day: date) -> str:
    """TODO (Part 3.3): the same message to the same student on the same day is one notification.
    SHA-256 hex of canonical_json([roll_no, message with runs of whitespace collapsed and trimmed, day.isoformat()]).

    Today it returns a random value, so nothing is ever deduplicated.
    """
    normalized_message = " ".join(message.split())

    payload = canonical_json([
        roll_no,
        normalized_message,
        day.isoformat(),
    ])

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
