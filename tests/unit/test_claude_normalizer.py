from exagium.core.events import EventType
from exagium.trace.normalizer import ClaudeEventNormalizer


def test_normalizes_claude_text_tool_lifecycle_and_usage() -> None:
    normalizer = ClaudeEventNormalizer()
    assistant = {
        "type": "assistant",
        "message": {
            "model": "claude-test",
            "content": [
                {"type": "text", "text": "我来修改文件。"},
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Edit",
                    "input": {"file_path": "result.txt"},
                },
            ],
            "usage": {"input_tokens": 8, "output_tokens": 3},
        },
    }

    started = normalizer.normalize(assistant)
    completed = normalizer.normalize(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": "updated",
                    }
                ]
            },
        }
    )

    assert [event.type for event in started] == [
        EventType.AGENT_MESSAGE,
        EventType.TOOL_STARTED,
        EventType.USAGE_REPORTED,
    ]
    assert [event.type for event in completed] == [
        EventType.TOOL_COMPLETED,
        EventType.FILE_CHANGED,
    ]
    assert completed[0].payload["name"] == "Edit"
    assert completed[1].payload["path"] == "result.txt"


def test_normalizes_claude_bash_and_failed_result() -> None:
    normalizer = ClaudeEventNormalizer()
    started = normalizer.normalize(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "bash-1",
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                    }
                ]
            },
        }
    )
    completed = normalizer.normalize(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "bash-1",
                        "is_error": True,
                        "content": "tests failed",
                    }
                ]
            },
        }
    )

    assert started[0].type == EventType.COMMAND_STARTED
    assert started[0].payload["command"] == "pytest -q"
    assert completed[0].type == EventType.COMMAND_FAILED
    assert completed[0].payload["tool_use_id"] == "bash-1"


def test_normalizes_powershell_as_a_command_on_windows() -> None:
    event = ClaudeEventNormalizer().normalize(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "pwsh-1",
                        "name": "PowerShell",
                        "input": {"command": "Get-ChildItem"},
                    }
                ]
            },
        }
    )[0]

    assert event.type == EventType.COMMAND_STARTED
    assert event.payload["command"] == "Get-ChildItem"


def test_preserves_unknown_claude_event() -> None:
    raw = {"type": "future", "payload": {"kept": True}}

    event = ClaudeEventNormalizer().normalize(raw)[0]

    assert event.type == EventType.SYSTEM_NOTE
    assert event.raw_event == raw
