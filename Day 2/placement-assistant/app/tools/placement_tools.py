import operator
from datetime import datetime, timezone

from app.domain import AlreadyApplied, Rule, Student
from app.data import InMemoryPlacementRepo
from app.tools.dispatch import dispatch

OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "in": lambda actual, allowed: actual in allowed.split(","),
}


def _passes(rule: Rule, student_value) -> bool:
    return OPS[rule.op](student_value, rule.typed_value())


def _unknown_student(roll_no: str) -> dict:
    return {"error": "unknown_student",
            "hint": f"No student with roll number {roll_no!r}. Ask the user for their roll number, e.g. 22CS045."}


def _unknown_drive(drive_id: int) -> dict:
    return {"error": "unknown_drive",
            "hint": f"No drive with id {drive_id}. Call list_open_drives to get valid ids."}


class PlacementTools:
    """Every method named in TOOL_NAMES is exposed to the model. Its docstring IS the prompt.

    Two tools are complete samples: check_eligibility (read-only) and apply_to_drive (side effect).
    Copy their patterns for the tools marked TODO.
    """

    READ_ONLY = ("list_open_drives", "get_student", "check_eligibility", "list_my_applications")
    SIDE_EFFECTS = ("apply_to_drive", "book_interview_slot", "notify_student")
    TOOL_NAMES = READ_ONLY + SIDE_EFFECTS

    def __init__(self, repo: InMemoryPlacementRepo, notifier, clock=lambda: datetime.now(timezone.utc)):
        self.repo = repo
        self.notifier = notifier
        self.clock = clock

    def functions(self) -> dict:
        return {name: getattr(self, name) for name in self.TOOL_NAMES}

    def call(self, name: str, args: dict) -> dict:
        return dispatch(self.functions(), name, args)

    # ================================================================== SAMPLE 1 (given): read-only

    def _evaluate(self, s: Student, drive_id: int) -> list[dict]:
        # The business rule lives in data (placement.eligibility_rule), not in the prompt or an if.
        failed = []
        for rule in self.repo.rules_for_drive(drive_id):
            actual = getattr(s, rule.field)
            if not _passes(rule, actual):
                failed.append({"rule_id": rule.id, "rule": str(rule), "actual": actual})
        return failed

    def check_eligibility(self, student_id: str, drive_id: int) -> dict:
        """Decide whether ONE student may apply to ONE drive, using the drive's eligibility rules.

        Use before apply_to_drive, or when the user asks "can I apply", "am I eligible for
        <company>", or "why can't I apply". Do NOT use to find drives; use list_open_drives.
        Read-only: changes nothing.

        Args:
            student_id: Roll number, e.g. "22CS045".
            drive_id: Integer id returned by list_open_drives. Never a company name.

        Returns:
            {"student_id", "drive_id", "eligible", "failed_rules": [{"rule_id", "rule", "actual"}]}.
            Explain every failed rule to the user; do not invent rules that are not listed.
        """
        # Failures are returned, never raised: a stable code plus a hint telling the model what to do next.
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        if self.repo.get_drive(drive_id) is None:
            return _unknown_drive(drive_id)
        # Every failed rule, not just the first: the model explains the verdict, it never decides it.
        failed = self._evaluate(s, drive_id)
        return {"student_id": s.roll_no, "drive_id": drive_id,
                "eligible": not failed, "failed_rules": failed}

    # ================================================================== SAMPLE 2 (given): side effect

    def apply_to_drive(self, student_id: str, drive_id: int) -> dict:
        """Submit a placement application for ONE student to ONE drive.

        Side effect: creates an application record the placement cell will act on. Call it only
        when the user clearly asks to apply or register ("apply me", "sign me up"), never to
        check or explore. Eligibility is re-checked here, but call check_eligibility first so
        you can explain the result.

        Args:
            student_id: Roll number, e.g. "22CS045".
            drive_id: Integer id returned by list_open_drives.

        Returns:
            {"application_id", "student_id", "drive_id", "status": "applied",
             "available_slots": [{"slot_id", "starts_at"}]}. Offer the slots to the user;
            book one only when they choose.
        """
        # Side effects check in a fixed order and stop at the first failure.
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)
        d = self.repo.get_drive(drive_id)
        if d is None:
            return _unknown_drive(drive_id)
        if d.status != "open" or d.deadline <= self.clock():
            return {"error": "drive_closed",
                    "hint": f"{d.company} is not accepting applications. Call list_open_drives for open ones."}
        # Re-check even though the description says "call check_eligibility first".
        # An instruction asks; code enforces. The model may have skipped it.
        failed = self._evaluate(s, drive_id)
        if failed:
            return {"error": "not_eligible", "failed_rules": failed,
                    "hint": "Explain the failed rules to the user. Do not retry."}
        try:
            application_id = self.repo.create_application(s.id, drive_id)
        except AlreadyApplied:
            return {"error": "already_applied",
                    "hint": "The student has already applied to this drive. Tell the user; do not retry."}
        # Return what the next step needs: the model will want to offer interview slots.
        slots = self.repo.free_slots(drive_id)
        return {"application_id": application_id, "student_id": s.roll_no, "drive_id": drive_id,
                "status": "applied",
                "available_slots": [{"slot_id": sl.id, "starts_at": sl.starts_at.isoformat()} for sl in slots]}

    # ================================================================== YOUR TOOLS

    def get_student(self, student_id: str) -> dict:
        """Get the profile details of ONE student using their roll number.

        Use when the user asks for their student information, such as "what's my
        CGPA", "show my profile", "how many backlogs do I have", or "what is my
        graduation year". Do NOT use to determine whether a student can apply for
        a drive; use check_eligibility for that. Read-only: changes nothing.

        Args:
            student_id: Roll number, e.g. "22CS045".

        Returns:
            {"student_id", "name", "branch", "cgpa", "backlogs", "grad_year"}.
            student_id in the result is the roll number, not the database id.
        """
        s = self.repo.get_student(student_id)

        if s is None:
            return _unknown_student(student_id)

        return {
            "student_id": s.roll_no,
            "name": s.name,
            "branch": s.branch,
            "cgpa": s.cgpa,
            "backlogs": s.backlogs,
            "grad_year": s.grad_year
        }

    def list_open_drives(self, branch: str | None = None, grad_year: int | None = None) -> dict:
        """List all currently open placement drives.

        Use when the user wants to explore available opportunities, such as
        "show open drives", "what companies are hiring", or "list drives for
        my branch". Do NOT use to determine whether a specific student may apply;
        use check_eligibility for that. Read-only: changes nothing.

        Args:
            branch: Optional branch filter, e.g. "CSE". If provided, exclude
                drives whose branch eligibility rules do not allow that branch.
            grad_year: Optional graduation year filter, e.g. 2026. If provided,
                exclude drives whose graduation-year eligibility rules do not
                allow that year.

        Returns:
            {"drives": [{"drive_id", "company", "role", "ctc_lpa", "deadline"}]}.
            deadline is returned as YYYY-MM-DD. Only drives with status "open"
            and a deadline after self.clock() are included, ordered by the
            nearest deadline first.
        """
        drives = self.repo.list_open_drives(self.clock())

        result = []

        for drive in drives:
            rules = self.repo.rules_for_drive(drive.id)

            if branch is not None:
                branch_rule = next((r for r in rules if r.field == "branch"), None)

                if branch_rule is not None:
                    allowed = [b.strip() for b in branch_rule.value.split(",")]
                    if branch not in allowed:
                        continue

            if grad_year is not None:
                grad_rule = next((r for r in rules if r.field == "grad_year"), None)

                if grad_rule is not None and int(grad_rule.value) != grad_year:
                    continue

            result.append({
                "drive_id": drive.id,
                "company": drive.company,
                "role": drive.role,
                "ctc_lpa": drive.ctc_lpa,
                "deadline": drive.deadline.date().isoformat()
            })

        return {"drives": result}

    def book_interview_slot(self, student_id: str, slot_id: int) -> dict:
        """Book an interview slot for ONE student after they have applied to a drive.

        Side effect: reserves an interview slot that the placement cell will use
        for scheduling. Call it only when the user clearly chooses a specific slot,
        never to check availability or explore options. The student must already
        have an application for the drive associated with the slot.

        Args:
            student_id: Roll number, e.g. "22CS045".
            slot_id: Integer slot id returned by apply_to_drive.

        Returns:
            {"slot_id", "drive_id", "starts_at", "status": "booked"}.
            starts_at is returned as an ISO-8601 datetime string.
        """
        # Failures are checked in a fixed order and stop at the first failure.
        s = self.repo.get_student(student_id)
        if s is None:
            return _unknown_student(student_id)

        slot = self.repo.get_slot(slot_id)
        if slot is None:
            return {
                "error": "unknown_slot",
                "hint": f"No interview slot exists with id {slot_id}."
            }

        if not self.repo.has_application(s.id, slot.drive_id):
            return {
                "error": "no_application",
                "hint": "The student must apply to this drive before booking an interview slot."
            }

        if not self.repo.claim_slot(slot_id, s.id):
            remaining_slots = self.repo.free_slots(slot.drive_id)

            return {
                "error": "slot_taken",
                "available_slots": [
                    {
                        "slot_id": sl.id,
                        "starts_at": sl.starts_at.isoformat()
                    }
                    for sl in remaining_slots
                ],
                "hint": "Offer one of the remaining available slots."
            }

        booked_slot = self.repo.get_slot(slot_id)

        return {
            "slot_id": booked_slot.id,
            "drive_id": booked_slot.drive_id,
            "starts_at": booked_slot.starts_at.isoformat(),
            "status": "booked"
        }

    def notify_student(self, student_id: str, message: str) -> dict:
        """Send a notification message to ONE student.

        Side effect: queues and sends a notification through the configured
        notifier. Call it only when the user explicitly asks to send, notify,
        message, or alert a student. Never use it to draft, preview, edit,
        summarize, or discuss a message without actually sending it.

        Args:
            student_id: Roll number, e.g. "22CS045".
            message: Notification text to send. Must be 1–160 characters.

        Returns:
            {"notification_id", "status": "queued"}.
            status is always "queued" when the notification is accepted.
        """
        s = self.repo.get_student(student_id)

        if s is None:
            return _unknown_student(student_id)

        if not message or len(message.strip()) == 0 or len(message) > 160:
            return {
                "error": "invalid_message",
                "hint": "Message must contain 1 to 160 characters."
            }

        notification_id = self.notifier.send(student_id, message)

        return {
            "notification_id": notification_id,
            "status": "queued"
        }

    def list_my_applications(self, student_id: str) -> dict:
        """List all applications submitted by a student.

        Use when the student asks questions such as:
        - "Where have I applied?"
        - "Show my applications"
        - "What companies did I apply to?"
        - "When is my interview?"

        Read-only: changes nothing.

        Args:
            student_id: Student roll number, e.g. "22CS045".

        Returns:
            {"applications": [
                {
                    "application_id",
                    "drive_id",
                    "company",
                    "role",
                    "status",
                    "applied_on",
                    "interview_at"
                }
            ]}

            Applications are returned oldest first.
            Timestamps are returned as ISO-8601 strings.
        """
        student = self.repo.get_student(student_id)

        if student is None:
            return {"error": "unknown_student"}

        applications = self.repo.list_applications(student.id)

        return {
            "applications": [
                {
                    "application_id": app["application_id"],
                    "drive_id": app["drive_id"],
                    "company": app["company"],
                    "role": app["role"],
                    "status": app["status"],
                    "applied_on": app["created_at"].isoformat(),
                    "interview_at": (
                        app["interview_at"].isoformat()
                        if app["interview_at"] is not None
                        else None
                    ),
                }
                for app in applications
            ]
        }
