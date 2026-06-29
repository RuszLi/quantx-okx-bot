"""Structural tests — verify the src/pipeline/ package tree."""

import pathlib


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_package_tree_exists():
    """Every expected module file must exist (may be empty stub)."""
    expected = [
        "__init__.py",
        "candidate.py",
        "search_space.py",
        "validator.py",
        "promoter.py",
        "graveyard.py",
        "data_layer.py",
        "executor.py",
        "families.py",
        "protocol.py",
        "generators/__init__.py",
        "generators/base.py",
        "generators/funding_generator.py",
        "generators/oi_generator.py",
        "generators/orderbook_generator.py",
        "generators/calendar_generator.py",
        "generators/liquidation_generator.py",
    ]
    for rel in expected:
        full = PACKAGE_ROOT / rel
        assert full.exists(), f"Missing file: {full}"


def test_top_level_import():
    from src.pipeline import Candidate  # noqa: F811
    from src.pipeline import IS_GATE, CPCV_PARAMS  # noqa: F811
    assert Candidate is not None


def test_candidate_dataclass():
    from src.pipeline.candidate import Candidate
    c = Candidate(candidate_id="test", family="funding", params={"a": 1})
    assert c.candidate_id == "test"
    assert c.family == "funding"
    assert c.params == {"a": 1}
    assert isinstance(c.data_deps, list)
