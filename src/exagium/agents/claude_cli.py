from __future__ import annotations

import asyncio
import json
import time

from exagium.agents.base import EventEmitter
from exagium.agents.executable import resolve_command
from exagium.core.events import EventDraft, EventType
from exagium.core.models import (
    AgentDoctorResult,
    AgentMetadata,
    AgentRunRequest,
    AgentRunResult,
)
from exagium.runner.process import process_group_options, terminate_process_tree
from exagium.trace.normalizer import ClaudeEventNormalizer


class ClaudeCliAdapter:
    name = "claude"

    def __init__(
        self,
        executable: str = "claude",
        *,
        print_prefix: tuple[str, ...] = (
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--permission-mode",
            "acceptEdits",
            "--no-session-persistence",
            "--no-chrome",
        ),
        extra_args: tuple[str, ...] = (),
    ) -> None:
        self.executable = executable
        self.print_prefix = print_prefix
        self.extra_args = extra_args
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def doctor(self) -> AgentDoctorResult:
        command_prefix = resolve_command(self.executable)
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
        return AgentMetadata(
            name=self.name,
            version=result.version,
            metadata={"transport": "claude-code-stream-json"},
        )

    async def run(self, request: AgentRunRequest, emit: EventEmitter) -> AgentRunResult:
        started = time.perf_counter()
        command_prefix = resolve_command(self.executable) or (self.executable,)
        command = [*command_prefix, *self.print_prefix, *self.extra_args]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=request.workspace,
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
        normalizer = ClaudeEventNormalizer()

        # 两个输出流必须并发排空，避免长时间 Agent 运行因管道写满而停住。
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
                for event in normalizer.normalize(raw_event):
                    await emit(event)

        async def read_stderr() -> None:
            assert process.stderr is not None
            async for raw_line in process.stderr:
                line = raw_line.decode(errors="replace")
                stderr_parts.append(line)
                await emit(
                    EventDraft(
                        type=EventType.SYSTEM_NOTE,
                        source="claude",
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
