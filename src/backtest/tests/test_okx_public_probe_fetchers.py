import json

from src.reports.okx_public_probe import fetch_public_candles, fetch_public_instruments


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_public_instruments_parses_okx_payload(monkeypatch):
    payload = {"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "lotSz": "0.01"}]}
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=15.0: _FakeResponse(payload))

    rows = fetch_public_instruments()

    assert rows[0]["instId"] == "BTC-USDT-SWAP"


def test_fetch_public_candles_parses_okx_payload(monkeypatch):
    payload = {"code": "0", "data": [["1718841600000", "100", "101", "99", "100.5", "10", "1000", "1000", "1"]]}
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=15.0: _FakeResponse(payload))

    frame = fetch_public_candles("BTC-USDT-SWAP", limit=1)

    assert len(frame) == 1
    assert float(frame.iloc[0]["open"]) == 100.0
