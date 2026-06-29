"""V3.2 automated edge discovery pipeline.

See ``README.md`` for module boundaries and data-flow overview.
"""

from __future__ import annotations

from .candidate import Candidate
from .protocol import (
    CPCV_PARAMS,
    DSR_P_VALUE_MAX,
    HOLDOUT_WINDOW_START,
    IS_GATE,
    PBO_FRACTION_POSITIVE_MIN,
    PBO_MAX,
    REPARAM_GATE,
    TRAIN_WINDOW_END,
    TRAIN_WINDOW_START,
)

__all__ = [
    "Candidate",
    "CPCV_PARAMS",
    "DSR_P_VALUE_MAX",
    "HOLDOUT_WINDOW_START",
    "IS_GATE",
    "PBO_FRACTION_POSITIVE_MIN",
    "PBO_MAX",
    "REPARAM_GATE",
    "TRAIN_WINDOW_END",
    "TRAIN_WINDOW_START",
]
