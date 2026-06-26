from unittest.mock import MagicMock, patch

import pandas as pd

from src.reports.okx_public_probe import fetch_public_candles, fetch_public_instruments


def mock_public_api(get_instruments=None):
    client = MagicMock()
    client.get_instruments.return_value = get_instruments or {"code": "0", "data": []}
    return client


def mock_market_api(get_candlesticks=None):
    client = MagicMock()
    client.get_candlesticks.return_value = get_candlesticks or {"code": "0", "data": []}
    return client


def test_fetch_public_instruments_parses_okx_payload():
    payload = {"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "lotSz": "0.01"}]}
    client = mock_public_api(payload)

    with patch("src.reports.okx_public_probe.public_api", return_value=client):
        rows = fetch_public_instruments()

    assert rows[0]["instId"] == "BTC-USDT-SWAP"


def test_fetch_public_candles_parses_okx_payload():
    payload = {"code": "0", "data": [["1718841600000", "100", "101", "99", "100.5", "10", "1000", "1000", "1"]]}
    client = mock_market_api(payload)

    with patch("src.reports.okx_public_probe.market_api", return_value=client):
        frame = fetch_public_candles("BTC-USDT-SWAP", limit=1)

    assert len(frame) == 1
    assert float(frame.iloc[0]["open"]) == 100.0
