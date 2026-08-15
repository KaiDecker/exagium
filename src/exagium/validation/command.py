from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from exagium.core.models import CommandSpec, ValidationOutcome
from exagium.runner.process import process_group_options, terminate_process_tree


class CommandValidator:
    def __init__(self, *, use_workspace_as_cwd: bool = True) -> None:
        self.use_workspace_as_cwd = use_workspace_as_cwd

    async def run(self, spec: CommandSpec, workspace: Path) -> ValidationOutcome:
        started = time.perf_counter()
        environment = os.environ.copy()
        environment["EXAGIUM_WORKSPACE"] = str(workspace)
        try:
            process = await asyncio.create_subprocess_shell(
                spec.command,
                cwd=workspace if self.use_workspace_as_cwd else None,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **process_group_options(),
            )
        except OSError as exc:
            return ValidationOutcome(
                name=spec.name or spec.command,
                command=spec.command,
                status="ERROR",
                exit_code=None,
                duration_ms=int((time.perf_counter() - started) * 1000),
                stdout="",
                stderr=str(exc),
            )
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=spec.timeout_seconds
            )
        except TimeoutError:
            timed_out = True
            await terminate_process_tree(process)
            stdout, stderr = await process.communicate()
        duration_ms = int((time.perf_counter() - started) * 1000)
        exit_code = process.returncode
        passed = not timed_out and exit_code == spec.expected_exit_code
        return ValidationOutcome(
            name=spec.name or spec.command,
            command=spec.command,
            status="PASSED" if passed else "FAILED",
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            timed_out=timed_out,
        )
