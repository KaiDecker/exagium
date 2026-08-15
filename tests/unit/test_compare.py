from exagium.experiments.compare import find_first_divergence
from exagium.trace.signatures import SemanticSignature, SemanticStep


def step(number: int, signature: SemanticSignature, detail: str | None = None) -> SemanticStep:
    return SemanticStep(step=number, signature=signature, detail=detail)


def test_find_first_divergence_compares_semantic_signatures() -> None:
    run_a = [
        step(1, SemanticSignature.SEARCH),
        step(2, SemanticSignature.READ),
        step(3, SemanticSignature.EDIT),
        step(4, SemanticSignature.TEST),
    ]
    run_b = [
        step(1, SemanticSignature.SEARCH),
        step(2, SemanticSignature.READ),
        step(3, SemanticSignature.EDIT),
        step(4, SemanticSignature.EDIT),
    ]

    divergence = find_first_divergence(run_a, run_b)

    assert divergence is not None
    assert divergence.step == 4
    assert divergence.run_a is not None
    assert divergence.run_a.signature == SemanticSignature.TEST
    assert divergence.run_b is not None
    assert divergence.run_b.signature == SemanticSignature.EDIT


def test_command_details_do_not_create_false_semantic_divergence() -> None:
    run_a = [step(1, SemanticSignature.SEARCH, 'rg "first"')]
    run_b = [step(1, SemanticSignature.SEARCH, 'rg "second"')]

    assert find_first_divergence(run_a, run_b) is None
