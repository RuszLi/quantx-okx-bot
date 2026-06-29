"""Archive rejected candidates as structured negative evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._strategy_artifacts import StrategyDocContext, render_strategy_doc, upsert_strategy_index


@dataclass(frozen=True, slots=True)
class GraveyardPaths:
    strategies_docs_dir: Path


class Graveyard:
    """Persist rejected-candidate docs and maintain the strategy index."""

    def __init__(self, *, strategies_docs_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        docs_dir = strategies_docs_dir or root / "docs" / "strategies"
        self._paths = GraveyardPaths(strategies_docs_dir=docs_dir)
        self._index_path = docs_dir / "README.md"

    def bury(
        self,
        candidate_id: str,
        family: str,
        params: dict,
        metrics: dict,
        failure_reasons: list[str],
        *,
        strategy_name: str = "",
        bar_freq: str = "",
        is_event_driven: bool = False,
        leverage_cap: float = 0.0,
        risk_per_trade_r: float = 0.0,
    ) -> str:
        self._paths.strategies_docs_dir.mkdir(parents=True, exist_ok=True)
        doc_path = self._paths.strategies_docs_dir / f"{candidate_id}.md"
        context = StrategyDocContext(
            candidate_id=candidate_id,
            family=family,
            stage="rejected",
            params=dict(params),
            metrics=dict(metrics),
            failure_reasons=tuple(failure_reasons),
            strategy_name=strategy_name,
            bar_freq=bar_freq,
            is_event_driven=is_event_driven,
            leverage_cap=leverage_cap,
            risk_per_trade_r=risk_per_trade_r,
        )
        doc_path.write_text(render_strategy_doc(context), encoding="utf-8")
        upsert_strategy_index(self._index_path, candidate_id, "rejected", family, doc_path.name)
        return str(doc_path)
