"""Search space — parameter grid and sampling strategies.

Supports cartesian-product grid search and random sampling.  Bayesian
optimisation is reserved as a future extension point (Phase 4+).
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal


@dataclass
class ParameterSpace:
    """Definition of a parameter search space.

    Attributes:
        params:        Dict mapping parameter name to a list of candidate values.
        sampling:      Sampling strategy (default ``"grid"``).
        random_samples: Number of random samples (only relevant for ``"random"``).
        seed:          RNG seed for reproducibility.
    """

    params: dict[str, list[Any]] = field(default_factory=dict)
    sampling: Literal["grid", "random", "bayesian"] = "grid"
    random_samples: int | None = None
    seed: int = 42

    def iter_grid(self) -> Iterator[dict[str, Any]]:
        """Yield all cartesian-product combinations.

        Example:
            >>> ps = ParameterSpace(params={"a": [1, 2], "b": [3]})
            >>> list(ps.iter_grid())
            [{"a": 1, "b": 3}, {"a": 2, "b": 3}]
        """
        keys = list(self.params)
        for values in itertools.product(*[self.params[k] for k in keys]):
            yield dict(zip(keys, values))

    def iter_samples(self, n: int | None = None) -> Iterator[dict[str, Any]]:
        """Yield *n* random samples from the parameter space.

        If ``n`` is None, uses ``self.random_samples`` (or falls back to
        10).  Sampling is with replacement; duplicate results may occur.
        """
        n = n or self.random_samples or 10
        rng = random.Random(self.seed)
        keys = list(self.params)
        for _ in range(n):
            vals = [self.params[k] for k in keys]
            yield {k: rng.choice(v) for k, v in zip(keys, vals)}
