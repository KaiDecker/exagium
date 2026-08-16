from __future__ import annotations

import json
import sys
from pathlib import Path


def emit(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


if "--version" in sys.argv:
    print("2.1.220 (Claude Code)")
    raise SystemExit(0)

prompt = sys.stdin.read()
emit(
    {
        "type": "system",
        "subtype": "init",
        "model": "claude-test",
        "session_id": "test-session",
    }
)
emit(
    {
        "type": "assistant",
        "message": {
            "model": "claude-test",
            "content": [
                {"type": "text", "text": f"收到任务：{prompt}"},
                {
                    "type": "tool_use",
                    "id": "edit-1",
                    "name": "Edit",
                    "input": {"file_path": "result.txt"},
                },
            ],
            "usage": {"input_tokens": 12, "output_tokens": 4},
        },
    }
)
Path("result.txt").write_text("fixed by claude", encoding="utf-8")
emit(
    {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "edit-1",
                    "content": "updated",
                }
            ]
        },
    }
)
emit(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 20,
        "num_turns": 1,
        "result": "Implemented the fix.",
        "total_cost_usd": 0.01,
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }
)
