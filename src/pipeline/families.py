"""Seed signal family registry for the V3.2 edge discovery pipeline.

Each ``SignalFamily`` groups related concrete signals that share a common
data dependency and generator module.  The registry is the single source
of truth for Phase 1.3 of the automated edge discovery plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SignalFamily:
    """A family of related trading signals.

    Attributes:
        name: Short family identifier (e.g. ``"funding"``).
        signals: Concrete signal names belonging to this family.
        required_data_fields: Data fields the family's generators need.
        default_universe: Default instrument universe for backtesting.
        generator_module: Dotted import path to the generator module.
    """

    name: str
    signals: list[str] = field(default_factory=list)
    required_data_fields: list[str] = field(default_factory=list)
    default_universe: list[str] = field(default_factory=lambda: ["BTC-USDT-SWAP"])
    generator_module: str = ""


# ---------------------------------------------------------------------------
# Family instances (Phase 1.3 seed pool)
# ---------------------------------------------------------------------------

FUNDING_FAMILY = SignalFamily(
    name="funding",
    signals=[
        "funding_zscore",
        "funding_flip",
        "cross_exchange_spread",
        "fr_switch_regime",
    ],
    required_data_fields=["funding_rate", "klines"],
    generator_module="src.pipeline.generators.funding_generator",
)

OI_FAMILY = SignalFamily(
    name="oi",
    signals=[
        "oi_price_divergence",
        "oi_change_rate",
        "oi_volume_ratio",
    ],
    required_data_fields=["open_interest", "klines"],
    generator_module="src.pipeline.generators.oi_generator",
)

ORDERBOOK_FAMILY = SignalFamily(
    name="orderbook",
    signals=[
        "obi_top5",
        "obi_top10",
        "obi_top20",
        "spread_change",
        "depth_imbalance_delta",
    ],
    required_data_fields=["order_book", "klines"],
    generator_module="src.pipeline.generators.orderbook_generator",
)

CALENDAR_FAMILY = SignalFamily(
    name="calendar",
    signals=[
        "day_of_week",
        "month",
        "funding_time_proximity",
    ],
    required_data_fields=["klines", "funding_rate"],
    generator_module="src.pipeline.generators.calendar_generator",
)

LIQUIDATION_FAMILY = SignalFamily(
    name="liquidation",
    signals=[
        "liquidation_cluster_proximity",
        "cascade_prediction",
    ],
    required_data_fields=["liquidations", "klines"],
    generator_module="src.pipeline.generators.liquidation_generator",
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FAMILY_REGISTRY: dict[str, SignalFamily] = {
    FUNDING_FAMILY.name: FUNDING_FAMILY,
    OI_FAMILY.name: OI_FAMILY,
    ORDERBOOK_FAMILY.name: ORDERBOOK_FAMILY,
    CALENDAR_FAMILY.name: CALENDAR_FAMILY,
    LIQUIDATION_FAMILY.name: LIQUIDATION_FAMILY,
}
