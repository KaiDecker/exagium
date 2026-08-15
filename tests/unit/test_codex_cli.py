import os
import shutil

import pytest

from exagium.agents.codex_cli import _resolve_command


@pytest.mark.skipif(os.name != "nt", reason="Windows command shim behavior")
def test_resolve_command_preserves_path_precedence_and_ignores_extensionless_shim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", r"C:\shim;C:\native")

    def fake_which(command: str, *, path: str | None = None) -> str | None:
        if path == r"C:\shim" and command == "codex.cmd":
            return r"C:\shim\codex.cmd"
        if path == r"C:\native" and command == "codex.exe":
            return r"C:\native\codex.exe"
        return None

    monkeypatch.setattr(shutil, "which", fake_which)

    command = _resolve_command("codex")

    assert command is not None
    assert command[-1] == r"C:\shim\codex.cmd"


@pytest.mark.skipif(os.name != "nt", reason="Windows command shim behavior")
def test_resolve_command_wraps_cmd_shim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", r"C:\tools")

    def fake_which(command: str, *, path: str | None = None) -> str | None:
        return r"C:\tools\codex.cmd" if command == "codex.cmd" else None

    monkeypatch.setattr(shutil, "which", fake_which)

    command = _resolve_command("codex")

    assert command is not None
    assert command[:4] == (os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c")
    assert command[-1] == r"C:\tools\codex.cmd"
