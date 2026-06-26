from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


class PaperRunner:
    def __init__(self, output_dir: str | Path = "data/paper_ensemble") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.trades_path = self.output_dir / "ensemble.csv"

    def _load_existing(self) -> pd.DataFrame:
        if self.trades_path.exists():
            return pd.read_csv(self.trades_path)
        return pd.DataFrame()

    def run(self, signals: pd.DataFrame) -> pd.DataFrame:
        if signals.empty:
            return pd.DataFrame()
        result = signals.copy()
        result["mode"] = "paper"
        result["status"] = "recorded"
        result["recorded_at"] = datetime.now(timezone.utc).isoformat()
        existing = self._load_existing()
        if not existing.empty:
            all_trades = pd.concat([existing, result], ignore_index=True)
        else:
            all_trades = result
        all_trades.to_csv(self.trades_path, index=False)
        return result
