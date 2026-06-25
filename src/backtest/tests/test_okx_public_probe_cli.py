import json
from pathlib import Path

from src.reports.okx_public_probe import fetch_public_instruments, build_probe_payload
from src.data.okx_announcements import normalize_announcement


def test_probe_cli_functions_write_non_empty_instrument_payload(tmp_path: Path):
    instruments = fetch_public_instruments("SWAP")
    announcements = [
        normalize_announcement(
            {"id": "1", "title": "OKX lists DOGE", "publishedAt": "2026-06-25T08:00:00Z"}
        ).raw
    ]

    import pandas as pd
    candles = pd.DataFrame({"open": [100.0], "close": [100.5]})
    funding = pd.DataFrame({"funding_rate": [0.001]})
    oi = pd.DataFrame({"open_interest_contracts": [1]})

    payload = build_probe_payload(instruments, announcements, candles, funding, oi)

    out_dir = Path(tmp_path)
    (out_dir / "probe_payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "instrument_payload.json").write_text(json.dumps(instruments, indent=2, ensure_ascii=False), encoding="utf-8")

    assert len(instruments) > 0
    assert "instId" in instruments[0]
    assert payload["instruments"]["ok"] is True
