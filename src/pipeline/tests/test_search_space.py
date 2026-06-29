from __future__ import annotations

from src.pipeline.search_space import ParameterSpace


def test_iter_samples_returns_requested_count() -> None:
    space = ParameterSpace(
        params={"a": [1, 2], "b": [3, 4]},
        sampling="random",
        random_samples=3,
        seed=7,
    )

    samples = list(space.iter_samples())

    assert len(samples) == 3
    assert all(set(sample) == {"a", "b"} for sample in samples)
