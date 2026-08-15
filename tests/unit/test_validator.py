import sys
from pathlib import Path

import pytest

from exagium.core.models import CommandSpec
from exagium.validation.command import CommandValidator


def skip_if_process_creation_is_blocked(status: str, stderr: str) -> None:
    if status == "ERROR" and ("WinError 5" in stderr or "拒绝访问" in stderr):
        pytest.skip("The execution sandbox blocks subprocess creation from tests")


@pytest.mark.asyncio
async def test_command_validator_passes_only_on_expected_exit_code(sandbox_path: Path) -> None:
    spec = CommandSpec(command=f'"{sys.executable}" -c "raise SystemExit(0)"')

    outcome = await CommandValidator(use_workspace_as_cwd=False).run(spec, sandbox_path)
    skip_if_process_creation_is_blocked(outcome.status, outcome.stderr)

    assert outcome.status == "PASSED"
    assert outcome.exit_code == 0


@pytest.mark.asyncio
async def test_command_validator_records_failure_output(sandbox_path: Path) -> None:
    script = "import sys; print('bad', file=sys.stderr); raise SystemExit(3)"
    spec = CommandSpec(command=f'"{sys.executable}" -c "{script}"')

    outcome = await CommandValidator(use_workspace_as_cwd=False).run(spec, sandbox_path)
    skip_if_process_creation_is_blocked(outcome.status, outcome.stderr)

    assert outcome.status == "FAILED"
    assert outcome.exit_code == 3
    assert "bad" in outcome.stderr
