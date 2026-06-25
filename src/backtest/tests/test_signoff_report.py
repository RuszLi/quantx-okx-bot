from pathlib import Path

from src.reports.signoff import write_api_signoff_report, write_execution_feasibility_report


def test_write_api_signoff_report_contains_required_datasets(tmp_path: Path):
    checks = {
        "instruments": {"status": "PASS", "evidence": "swap universe loaded"},
        "announcements": {"status": "PASS", "evidence": "6m rebuilt"},
        "candles": {"status": "PASS", "evidence": "1m gap <= 0.5%"},
    }
    out_path = tmp_path / "v3_api_signoff.md"

    write_api_signoff_report(checks, out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "# V3 API Signoff" in text
    assert "instruments" in text
    assert "announcements" in text


def test_write_execution_feasibility_report_contains_symbol_table(tmp_path: Path):
    rows = [
        {
            "instId": "BTC-USDT-SWAP",
            "minSz": 0.01,
            "lotSz": 0.01,
            "tickSz": 0.1,
            "ctVal": 0.01,
            "can_open_position": True,
            "can_place_hard_stop": True,
            "can_post_only_fill": True,
        }
    ]
    out_path = tmp_path / "v3_execution_feasibility.md"

    write_execution_feasibility_report(rows, out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "BTC-USDT-SWAP" in text
    assert "can_open_position" in text
