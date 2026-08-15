from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from exagium.core.errors import WorkspaceError


async def _git(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        process.returncode or 0,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


@dataclass(slots=True)
class RunWorkspace:
    source_repo: Path
    path: Path
    keep: bool = False

    async def cleanup(self) -> None:
        if self.keep or not self.path.exists():
            return
        code, _, stderr = await _git(
            "-C", str(self.source_repo), "worktree", "remove", "--force", str(self.path)
        )
        if code != 0:
            raise WorkspaceError(f"Could not remove worktree {self.path}: {stderr.strip()}")


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def prepare(
        self,
        *,
        run_id: UUID,
        source_repo: Path,
        base_ref: str,
        keep: bool,
    ) -> RunWorkspace:
        self.root.mkdir(parents=True, exist_ok=True)
        code, _, stderr = await _git("-C", str(source_repo), "rev-parse", "--git-dir")
        if code != 0:
            raise WorkspaceError(
                f"Task repo is not a Git repository: {source_repo}: {stderr.strip()}"
            )
        code, _, stderr = await _git(
            "-C", str(source_repo), "rev-parse", "--verify", f"{base_ref}^{{commit}}"
        )
        if code != 0:
            raise WorkspaceError(
                f"Base ref does not resolve to a commit: {base_ref}: {stderr.strip()}"
            )
        path = (self.root / str(run_id)).resolve()
        code, _, stderr = await _git(
            "-C",
            str(source_repo),
            "worktree",
            "add",
            "--detach",
            str(path),
            base_ref,
        )
        if code != 0:
            raise WorkspaceError(f"Could not create worktree {path}: {stderr.strip()}")
        return RunWorkspace(source_repo=source_repo, path=path, keep=keep)

    async def capture_diff(self, workspace: RunWorkspace) -> str:
        code, _, stderr = await _git("-C", str(workspace.path), "add", "--intent-to-add", "--", ".")
        if code != 0:
            raise WorkspaceError(f"Could not include untracked files in git diff: {stderr.strip()}")
        code, stdout, stderr = await _git(
            "-C", str(workspace.path), "diff", "--binary", "--no-ext-diff", "HEAD"
        )
        if code != 0:
            raise WorkspaceError(f"Could not capture git diff: {stderr.strip()}")
        return stdout
