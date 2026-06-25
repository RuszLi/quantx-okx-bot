from __future__ import annotations

import pandas as pd


class PaperRunner:
    def run(self, signals: pd.DataFrame) -> pd.DataFrame:
        if signals.empty:
            return pd.DataFrame()
        result = signals.copy()
        result["mode"] = "paper"
        result["status"] = "recorded"
        return result
