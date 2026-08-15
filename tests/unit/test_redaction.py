from exagium.core.redaction import redact, redact_text


def test_redacts_secret_keys_recursively() -> None:
    value = {"nested": {"api_key": "top-secret", "safe": "visible"}}

    assert redact(value) == {"nested": {"api_key": "[REDACTED]", "safe": "visible"}}


def test_redacts_bearer_tokens_and_assignments_in_text() -> None:
    value = "Authorization: Bearer abcdefghijklmnop token=really-secret"

    redacted = redact_text(value)

    assert "abcdefghijklmnop" not in redacted
    assert "really-secret" not in redacted
