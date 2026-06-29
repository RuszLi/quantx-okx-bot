"""Family-registry tests — verify all 5 families are defined."""

from src.pipeline.families import (
    CALENDAR_FAMILY,
    FAMILY_REGISTRY,
    FUNDING_FAMILY,
    LIQUIDATION_FAMILY,
    OI_FAMILY,
    ORDERBOOK_FAMILY,
    SignalFamily,
)


class TestFamilyDefinitions:
    def test_funding_family(self):
        assert isinstance(FUNDING_FAMILY, SignalFamily)
        assert "funding_zscore" in FUNDING_FAMILY.signals
        assert "funding_flip" in FUNDING_FAMILY.signals

    def test_oi_family(self):
        assert "oi_price_divergence" in OI_FAMILY.signals
        assert "oi_change_rate" in OI_FAMILY.signals

    def test_orderbook_family(self):
        assert "obi_top5" in ORDERBOOK_FAMILY.signals
        assert "spread_change" in ORDERBOOK_FAMILY.signals

    def test_calendar_family(self):
        assert "day_of_week" in CALENDAR_FAMILY.signals
        assert "funding_time_proximity" in CALENDAR_FAMILY.signals

    def test_liquidation_family(self):
        assert "liquidation_cluster_proximity" in LIQUIDATION_FAMILY.signals

    def test_registry_contains_all(self):
        assert "funding" in FAMILY_REGISTRY
        assert "oi" in FAMILY_REGISTRY
        assert "orderbook" in FAMILY_REGISTRY
        assert "calendar" in FAMILY_REGISTRY
        assert "liquidation" in FAMILY_REGISTRY

    def test_registry_size(self):
        assert len(FAMILY_REGISTRY) == 5
