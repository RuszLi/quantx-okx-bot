import pandas as pd

from src.reports.okx_public_probe import build_probe_payload


def test_build_probe_payload_assembles_public_api_observations():
    instruments = [{"instId": "BTC-USDT-SWAP", "ctVal": "0.01", "lotSz": "0.01", "minSz": "0.01", "tickSz": "0.1"}]
    announcements = [{"announcement_id": "1", "title": "listing", "published_at": "2026-06-25T00:00:00Z"}]
    candles = pd.DataFrame({"open": [1, 2], "close": [1, 2]})
    funding = pd.DataFrame({"funding_rate": [0.001], "funding_time": [pd.Timestamp("2026-06-25T00:00:00Z")]})
    oi = pd.DataFrame({"open_interest_contracts": [1], "ts": [pd.Timestamp("2026-06-25T00:00:00Z")]})

    payload = build_probe_payload(instruments, announcements, candles, funding, oi)

    assert payload["instruments"]["ok"] is True
    assert payload["announcements"]["count"] == 1
    assert payload["candles"]["ok"] is True
    assert payload["funding"]["ok"] is True
    assert payload["oi"]["ok"] is True
