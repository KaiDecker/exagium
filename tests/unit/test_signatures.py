from exagium.core.status import RunStatus
from exagium.trace.signatures import SemanticSignature, classify_command, normalize_event_sequence


def test_normalizes_events_into_semantic_operations_and_pairs_lifecycle_events() -> None:
    events = [
        {"seq": 1, "type": "RUN_STARTED", "payload": {}},
        {
            "seq": 2,
            "type": "COMMAND_STARTED",
            "payload": {"id": "search-1", "command": 'rg "needle" src'},
        },
        {
            "seq": 3,
            "type": "COMMAND_COMPLETED",
            "payload": {"id": "search-1", "command": 'rg "needle" src', "exit_code": 0},
        },
        {"seq": 4, "type": "FILE_CHANGED", "payload": {"path": "src/app.py"}},
        {
            "seq": 5,
            "type": "COMMAND_STARTED",
            "payload": {"id": "test-1", "command": "python -m pytest"},
        },
        {
            "seq": 6,
            "type": "COMMAND_FAILED",
            "payload": {"id": "test-1", "command": "python -m pytest", "exit_code": 1},
        },
        {"seq": 7, "type": "VALIDATION_COMPLETED", "payload": {"status": "FAILED"}},
    ]

    steps = normalize_event_sequence(events, RunStatus.FAILED)

    assert [step.signature for step in steps] == [
        SemanticSignature.SEARCH,
        SemanticSignature.EDIT,
        SemanticSignature.TEST,
        SemanticSignature.FAIL,
    ]
    assert steps[0].event_type == "COMMAND_COMPLETED"
    assert steps[0].outcome == "PASSED"
    assert steps[2].outcome == "FAILED"


def test_classifies_powershell_read_and_tool_operations() -> None:
    events = [
        {
            "seq": 1,
            "type": "COMMAND_COMPLETED",
            "payload": {"command": "Get-Content src/app.py", "exit_code": 0},
        },
        {
            "seq": 2,
            "type": "TOOL_COMPLETED",
            "payload": {"name": "apply_patch"},
        },
    ]

    steps = normalize_event_sequence(events)

    assert [step.signature for step in steps] == [
        SemanticSignature.READ,
        SemanticSignature.EDIT,
    ]


def test_search_command_wins_when_its_pattern_mentions_test_tools() -> None:
    command = 'pwsh -Command rg -n "unittest|pytest|token" fixtures/buggy_auth_service'

    assert classify_command(command) == SemanticSignature.SEARCH
