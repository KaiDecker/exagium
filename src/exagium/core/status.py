from enum import StrEnum

from exagium.core.errors import InvalidStatusTransition


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = {
    RunStatus.PASSED,
    RunStatus.FAILED,
    RunStatus.ERROR,
    RunStatus.CANCELLED,
}

_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.PREPARING, RunStatus.CANCELLED, RunStatus.ERROR},
    RunStatus.PREPARING: {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.ERROR},
    RunStatus.RUNNING: {RunStatus.VALIDATING, RunStatus.CANCELLED, RunStatus.ERROR},
    RunStatus.VALIDATING: {
        RunStatus.PASSED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.ERROR,
    },
    RunStatus.PASSED: set(),
    RunStatus.FAILED: set(),
    RunStatus.ERROR: set(),
    RunStatus.CANCELLED: set(),
}


def require_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidStatusTransition(f"Cannot transition a run from {current} to {target}")
