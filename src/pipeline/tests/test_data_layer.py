from __future__ import annotations

import pandas as pd

from src.data import okx_funding
from src.pipeline import data_layer


def test_get_funding_handles_duplicate_settlement_rows(monkeypatch) -> None:
    funding = pd.DataFrame(
        {
            "funding_time": [
                pd.Timestamp("2026-06-12 08:00:00", tz="UTC"),
                pd.Timestamp("2026-06-12 08:00:00", tz="UTC"),
                pd.Timestamp("2026-06-12 16:00:00", tz="UTC"),
            ],
            "funding_rate": [0.0010, 0.0012, -0.0008],
        }
    )

    monkeypatch.setattr(data_layer, "_okx_funding", lambda inst_id, limit=200: funding)

    result = data_layer.get_funding(
        "BTC-USDT-SWAP",
        pd.Timestamp("2026-06-12 00:00:00", tz="UTC"),
        pd.Timestamp("2026-06-12 23:59:00", tz="UTC"),
    )

    assert not result.empty
    assert result.index.is_unique
    assert "funding_rate" in result.columns
    assert result.loc[pd.Timestamp("2026-06-12 08:00:00", tz="UTC"), "funding_rate"] == 0.0012


def test_fetch_funding_history_parses_millisecond_strings(monkeypatch) -> None:
    class _FakePublicApi:
        def funding_rate_history(self, instId: str, limit: str):
            _ = instId, limit
            return {
                "data": [
                    {
                        "fundingRate": "0.0013191189652252",
                        "realizedRate": "0.0013191189652252",
                        "fundingTime": "1782662400000",
                        "method": "current_period",
                    },
                    {
                        "fundingRate": "0.0001",
                        "realizedRate": "0.0001",
                        "fundingTime": "1782633600000",
                        "method": "current_period",
                    },
                ]
            }

    monkeypatch.setattr(okx_funding, "public_api", lambda: _FakePublicApi())

    result = okx_funding.fetch_funding_history("BTC-USDT-SWAP", limit=2)

    assert list(result["funding_rate"]) == [0.0001, 0.0013191189652252]
    assert result["funding_time"].notna().all()
    assert result["funding_time"].is_monotonic_increasing
