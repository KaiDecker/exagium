from __future__ import annotations

import os
import shutil
from pathlib import Path


def command_for_path(path: str | Path) -> tuple[str, ...]:
    resolved = str(path)
    if os.name == "nt" and Path(resolved).suffix.lower() in {".bat", ".cmd"}:
        return (os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", resolved)
    return (resolved,)


def resolve_command(executable: str) -> tuple[str, ...] | None:
    explicit = Path(executable)
    if explicit.is_file():
        return command_for_path(explicit)

    if os.name == "nt" and not explicit.suffix and explicit.parent == Path("."):
        # npm 会把无扩展名的 POSIX shim 放在 .cmd 前面，但 Windows 无法直接执行它。
        # 这里仍按 PATH 的目录顺序查找，同时优先选择 Windows 能启动的包装文件。
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                continue
            for extension in (".exe", ".com", ".cmd", ".bat"):
                candidate = f"{executable}{extension}"
                if resolved := shutil.which(candidate, path=directory.strip('"')):
                    return command_for_path(resolved)

    if resolved := shutil.which(executable):
        return command_for_path(resolved)
    return None
