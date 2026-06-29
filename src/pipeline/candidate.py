"""Candidate — the declaration object that flows through the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Candidate:
    """A single edge-discovery candidate carrying its full context.

    Attributes:
        candidate_id:  Unique identifier (e.g. ``"funding_zscore_v01"``).
        family:        Signal family name (e.g. ``"funding"``).
        params:        Parameter snapshot that produced this candidate.
        strategy_class:  Fully qualified class name (importable path).
        hypothesis:    Human-readable hypothesis statement.
        data_deps:     Required data-field names (copied from family definition).
    """

    candidate_id: str
    family: str
    params: dict = field(default_factory=dict)
    strategy_class: str = ""
    hypothesis: str = ""
    data_deps: list[str] = field(default_factory=list)
