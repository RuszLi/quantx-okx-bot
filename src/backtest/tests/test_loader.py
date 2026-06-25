"""
test_loader.py — Tests for loader module.
"""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date

from src.backtest import loader


def test_load_klines_parses_sample():
    """Smoke: loader can parse the sample_klines fixture without error."""
    # We test via build_raw on a fixture-based path by temporarily
    # overriding DATA_ROOT. But since it's hardwired, we test the
    # internal _read_csv_with_header_detect directly.
    import zipfile
    from io import BytesIO

    csv_content = b"1718841600000,100.00,100.50,99.80,100.20,1000.0,1718841659999,100100.0,50,600.0,60060.0,0\n"
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr("test.csv", csv_content)
    buf.seek(0)

    with zipfile.ZipFile(buf) as zf:
        df = loader._read_csv_with_header_detect(zf, "test.csv")

    assert len(df) == 1
    assert float(df.iloc[0, 0]) == 1718841600000


def test_header_detection():
    """Auto-detect CSV header row."""
    import zipfile
    from io import BytesIO

    csv_with_header = b"open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote,ignore\n1718841600000,100.00,100.50,99.80,100.20,1000.0,1718841659999,100100.0,50,600.0,60060.0,0\n"
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr("with_header.csv", csv_with_header)
    buf.seek(0)

    with zipfile.ZipFile(buf) as zf:
        df = loader._read_csv_with_header_detect(zf, "with_header.csv")

    assert len(df) == 1
    assert "open_time" in df.columns or float(df.iloc[0, 0]) == 1718841600000


def test_day_range():
    """_day_range yields inclusive dates."""
    days = list(loader._day_range(date(2026, 6, 20), date(2026, 6, 22)))
    assert len(days) == 3
    assert days[0] == date(2026, 6, 20)
    assert days[-1] == date(2026, 6, 22)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
