from __future__ import annotations

import pandas as pd


class LiveRunner:
    def run(self, signals: pd.DataFrame) -> pd.DataFrame:
        if signals.empty:
            return pd.DataFrame()

        result = signals.copy()
        result["mode"] = "live"
        result["status"] = "queued"
        return result
