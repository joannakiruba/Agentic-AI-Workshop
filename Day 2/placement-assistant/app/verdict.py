from collections.abc import Callable

from pydantic import BaseModel, Field, ValidationError, model_validator  # noqa: F401


class FailedRule(BaseModel):
    rule_id: int
    rule: str
    actual: str | float


class EligibilityVerdict(BaseModel):
    student_id: str = Field(pattern=r"^\d{2}[A-Z]{2}\d{3}$")
    drive_id: int
    eligible: bool
    failed_rules: list[FailedRule]
    summary: str = Field(min_length=1, max_length=280)

    @model_validator(mode="after")
    def validate_consistency(self):
        if self.eligible and self.failed_rules:
            raise ValueError(
                "eligible flag contradicts failed_rules"
            )

        if not self.eligible and not self.failed_rules:
            raise ValueError(
                "eligible flag contradicts failed_rules"
            )

        return self


class VerdictInvalid(Exception):
    def __init__(self, attempts: int, last_errors: list):
        super().__init__(f"no valid verdict after {attempts} attempts")
        self.attempts = attempts
        self.last_errors = last_errors


Generate = Callable[[list[str]], str]


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()


def structured_verdict(
    generate: Generate,
    prompt: str,
    max_retries: int = 2
) -> EligibilityVerdict:

    messages = [prompt]
    last_errors = ""

    for _ in range(max_retries + 1):
        raw = generate(messages)

        try:
            return EligibilityVerdict.model_validate_json(
                _strip_fences(raw)
            )

        except ValidationError as e:
            last_errors = str(e)

            messages.append(raw)
            messages.append(
                f"failed validation: {last_errors}"
            )

    raise VerdictInvalid(
        "Could not obtain a valid EligibilityVerdict",
        last_errors
    )