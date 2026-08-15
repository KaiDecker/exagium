from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from exagium.agents.base import EventEmitter
from exagium.core.events import EventDraft, EventType
from exagium.core.models import (
    AgentDoctorResult,
    AgentMetadata,
    AgentRunRequest,
    AgentRunResult,
)
from exagium.runner.process import process_group_options, terminate_process_tree
from exagium.trace.normalizer import normalize_codex_event


def _command_for_path(path: str | Path) -> tuple[str, ...]:
    resolved = str(path)
    if os.name == "nt" and Path(resolved).suffix.lower() in {".bat", ".cmd"}:
        return (os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", resolved)
    return (resolved,)


def _resolve_command(executable: str) -> tuple[str, ...] | None:
    explicit = Path(executable)
    if explicit.is_file():
        return _command_for_path(explicit)

    if os.name == "nt" and not explicit.suffix and explicit.parent == Path("."):
        # npm installs an extensionless POSIX shim before its .cmd wrapper. CreateProcess
        # cannot execute that shim. Preserve PATH directory precedence while selecting a
        # Windows-native executable or command wrapper from each directory.
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                continue
            for extension in (".exe", ".com", ".cmd", ".bat"):
                if resolved := shutil.which(f"{executable}{extension}", path=directory.strip('"')):
                    return _command_for_path(resolved)

    if resolved := shutil.which(executable):
        return _command_for_path(resolved)
    return None


class CodexCliAdapter:
    name = "codex"

    def __init__(
        self,
        executable: str = "codex",
        *,
        exec_prefix: tuple[str, ...] = ("exec",),
        extra_args: tuple[str, ...] = (),
    ) -> None:
        self.executable = executable
        self.exec_prefix = exec_prefix
        self.extra_args = extra_args
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def doctor(self) -> AgentDoctorResult:
        command_prefix = _resolve_command(self.executable)
        if command_prefix is None:
            return AgentDoctorResult(
                available=False,
                executable=self.executable,
                error=f"Executable not found: {self.executable}",
            )
        try:
            process = await asyncio.create_subprocess_exec(
                *command_prefix,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except (OSError, TimeoutError) as exc:
            return AgentDoctorResult(
                available=False,
                executable=command_prefix[-1],
                error=str(exc),
            )
        output = (stdout or stderr).decode(errors="replace").strip()
        return AgentDoctorResult(
            available=process.returncode == 0,
            executable=command_prefix[-1],
            version=output or None,
            error=None if process.returncode == 0 else output,
        )

    async def metadata(self) -> AgentMetadata:
        result = await self.doctor()
        return AgentMetadata(name=self.name, version=result.version)

    async def run(self, request: AgentRunRequest, emit: EventEmitter) -> AgentRunResult:
        started = time.perf_counter()
        command_prefix = _resolve_command(self.executable) or (self.executable,)
        command = [
            *command_prefix,
            *self.exec_prefix,
            "--json",
            "--color",
            "never",
            "--sandbox",
            "workspace-write",
            "-C",
            str(request.workspace),
            *self.extra_args,
            "-",
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **process_group_options(),
        )
        self._processes[str(request.run_id)] = process
        assert process.stdin is not None
        process.stdin.write(request.prompt.encode())
        await process.stdin.drain()
        process.stdin.close()
        stderr_parts: list[str] = []

        # 必须并发读 stdout和stderr，否则可能会出现死锁
        async def read_stdout() -> None:
            assert process.stdout is not None
            async for raw_line in process.stdout:
                line = raw_line.decode(errors="replace").rstrip("\r\n")
                if not line:
                    continue
                try:
                    raw_event = json.loads(line)
                except json.JSONDecodeError:
                    raw_event = line
                if not isinstance(raw_event, (dict, str)):
                    raw_event = {"value": raw_event}
                await emit(normalize_codex_event(raw_event))

        async def read_stderr() -> None:
            assert process.stderr is not None
            async for raw_line in process.stderr:
                line = raw_line.decode(errors="replace")
                stderr_parts.append(line)
                await emit(
                    EventDraft(
                        type=EventType.SYSTEM_NOTE,
                        source="codex",
                        source_event_type="stderr",
                        payload={"stream": "stderr", "text": line.rstrip("\r\n")},
                        raw_event=line.rstrip("\r\n"),
                    )
                )

        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())
        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=request.timeout_seconds)
        except TimeoutError:
            timed_out = True
            await terminate_process_tree(process)
        finally:
            await asyncio.gather(stdout_task, stderr_task)
            self._processes.pop(str(request.run_id), None)

        return AgentRunResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            duration_ms=int((time.perf_counter() - started) * 1000),
            stderr="".join(stderr_parts),
            timed_out=timed_out,
        )

    async def cancel(self, run_id: str) -> None:
        process = self._processes.get(run_id)
        if process and process.returncode is None:
            await terminate_process_tree(process)
