from src.reports.probe_okx import build_api_checks, build_execution_rows


def test_build_api_checks_from_probe_payloads():
    payload = {
        "instruments": {"count": 120, "ok": True},
        "announcements": {"count": 55, "ok": True},
        "candles": {"gap_pct": 0.2, "ok": True},
    }

    checks = build_api_checks(payload)

    assert checks["instruments"]["status"] == "PASS"
    assert checks["announcements"]["status"] == "PASS"
    assert checks["candles"]["status"] == "PASS"


def test_build_execution_rows_from_instrument_probe():
    instruments = [
        {
            "instId": "BTC-USDT-SWAP",
            "minSz": "0.01",
            "lotSz": "0.01",
            "tickSz": "0.1",
            "ctVal": "0.01",
            "maxLeverage": "10",
        }
    ]

    rows = build_execution_rows(instruments)

    assert rows[0]["instId"] == "BTC-USDT-SWAP"
    assert rows[0]["can_open_position"] is True
