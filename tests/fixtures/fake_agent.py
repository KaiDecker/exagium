from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def emit(event: dict[str, object]) -> None:
    print(json.dumps(event), flush=True)


if "-C" in sys.argv:
    os.chdir(sys.argv[sys.argv.index("-C") + 1])

emit({"type": "run.started"})
emit(
    {
        "type": "item.started",
        "item": {"id": "cmd-1", "type": "command_execution", "command": "inspect files"},
    }
)
emit(
    {
        "type": "item.completed",
        "item": {
            "id": "cmd-1",
            "type": "command_execution",
            "command": "inspect files",
            "exit_code": 0,
        },
    }
)
Path("result.txt").write_text("fixed", encoding="utf-8")
emit(
    {
        "type": "item.completed",
        "item": {"id": "change-1", "type": "file_change", "path": "result.txt"},
    }
)
emit(
    {
        "type": "item.completed",
        "item": {"id": "message-1", "type": "agent_message", "text": "Implemented the fix."},
    }
)
emit(
    {
        "type": "turn.completed",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }
)
print("a future non-json event", flush=True)
emit({"type": "run.completed"})
