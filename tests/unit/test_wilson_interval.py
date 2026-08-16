import pytest

from exagium.statistics.intervals import wilson_interval


def test_wilson_interval_matches_known_small_sample_result() -> None:
    interval = wilson_interval(14, 20)

    assert interval is not None
    assert interval.lower == pytest.approx(0.48102718)
    assert interval.upper == pytest.approx(0.85452276)
    assert interval.confidence_level == 0.95


@pytest.mark.parametrize(
    ("successes", "total", "expected_lower", "expected_upper"),
    [
        (0, 10, 0.0, 0.2775328),
        (10, 10, 0.7224672, 1.0),
        (1, 1, 0.20654931, 1.0),
    ],
)
def test_wilson_interval_handles_boundary_rates(
    successes: int,
    total: int,
    expected_lower: float,
    expected_upper: float,
) -> None:
    interval = wilson_interval(successes, total)

    assert interval is not None
    assert interval.lower == pytest.approx(expected_lower, abs=1e-8)
    assert interval.upper == pytest.approx(expected_upper, abs=1e-8)


def test_wilson_interval_returns_none_without_evaluable_runs() -> None:
    assert wilson_interval(0, 0) is None


def test_wilson_interval_respects_configured_confidence_level() -> None:
    interval = wilson_interval(14, 20, confidence_level=0.9)

    assert interval is not None
    assert interval.lower == pytest.approx(0.51619628)
    assert interval.upper == pytest.approx(0.83614058)


@pytest.mark.parametrize(
    ("successes", "total"),
    [(-1, 10), (11, 10), (0, -1)],
)
def test_wilson_interval_rejects_invalid_counts(successes: int, total: int) -> None:
    with pytest.raises(ValueError):
        wilson_interval(successes, total)


@pytest.mark.parametrize("confidence_level", [0.0, 1.0, -0.1, 1.1])
def test_wilson_interval_rejects_invalid_confidence_level(confidence_level: float) -> None:
    with pytest.raises(ValueError):
        wilson_interval(1, 2, confidence_level=confidence_level)
