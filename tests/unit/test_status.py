import pytest

from exagium.core.errors import InvalidStatusTransition
from exagium.core.status import RunStatus, require_transition


def test_valid_run_lifecycle() -> None:
    require_transition(RunStatus.QUEUED, RunStatus.PREPARING)
    require_transition(RunStatus.PREPARING, RunStatus.RUNNING)
    require_transition(RunStatus.RUNNING, RunStatus.VALIDATING)
    require_transition(RunStatus.VALIDATING, RunStatus.PASSED)


def test_terminal_status_cannot_transition() -> None:
    with pytest.raises(InvalidStatusTransition):
        require_transition(RunStatus.PASSED, RunStatus.RUNNING)
