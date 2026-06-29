"""Generator protocols — contract for producing ``Strategy`` instances.

Each signal-family generator implements ``SignalGenerator`` (Protocol) or
subclasses ``AbstractSignalGenerator`` for reuse.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from src.backtest.strategies.base import Strategy


@runtime_checkable
class SignalGenerator(Protocol):
    """Protocol for a parameterised signal generator.

    Every concrete generator (funding, OI, order-book, …) must satisfy
    this protocol.
    """

    def generate(self, params: dict[str, Any]) -> Strategy:
        """Produce a ``Strategy`` instance from a parameter snapshot.

        The returned object must satisfy the ``Strategy`` Protocol
        (``compute_signals`` + ``required_data``).
        """
        ...

    def default_search_space(self) -> dict[str, list[Any]]:
        """Return the default parameter grid for this family.

        Keys are parameter names, values are lists of candidate values.
        """
        ...

    def required_data(self) -> list[str]:
        """Return the list of required data-field names."""
        ...

    @property
    def family_name(self) -> str:
        """Return the signal-family identifier (e.g. ``"funding"``)."""
        ...


class AbstractSignalGenerator(ABC):
    """Abstract base that partially implements ``SignalGenerator``.

    Subclasses only need to override ``generate()``.
    """

    def __init__(
        self,
        family_name: str,
        default_params: dict[str, list[Any]] | None = None,
    ) -> None:
        self._family_name = family_name
        self._default_params = default_params or {}

    @property
    def family_name(self) -> str:
        return self._family_name

    def default_search_space(self) -> dict[str, list[Any]]:
        return dict(self._default_params)

    def required_data(self) -> list[str]:
        return ["klines"]

    @abstractmethod
    def generate(self, params: dict[str, Any]) -> Strategy:
        ...
