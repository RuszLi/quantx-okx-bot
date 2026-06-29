"""Promote PASS candidates into durable repo artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Callable

from src.backtest.strategies.base import StrategyConfig

from ._strategy_artifacts import (
    StrategyDocContext,
    candidate_class_name,
    render_strategy_doc,
    render_strategy_module,
    update_runner_cfg,
    update_strategy_registry,
    upsert_strategy_index,
)


@dataclass(frozen=True, slots=True)
class PromoterPaths:
    project_root: Path
    strategies_dir: Path
    strategies_init_path: Path
    runner_config_path: Path
    strategies_docs_dir: Path


def _run_exit_alignment_gate(project_root: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "src/backtest/tests/test_v3_phase0_exit_alignment.py",
        "-q",
    ]
    completed = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stdout.strip() or completed.stderr.strip() or "exit alignment gate failed"
        raise RuntimeError(f"Promotion blocked by exit alignment gate: {message}")


class Promoter:
    """Promote validated candidates into strategies, docs, and runner config."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        strategies_dir: Path | None = None,
        strategies_init_path: Path | None = None,
        runner_config_path: Path | None = None,
        strategies_docs_dir: Path | None = None,
        preflight_check: Callable[[Path], None] | None = None,
    ) -> None:
        root = project_root or Path(__file__).resolve().parents[2]
        docs_dir = strategies_docs_dir or root / "docs" / "strategies"
        self._paths = PromoterPaths(
            project_root=root,
            strategies_dir=strategies_dir or root / "src" / "backtest" / "strategies",
            strategies_init_path=strategies_init_path or root / "src" / "backtest" / "strategies" / "__init__.py",
            runner_config_path=runner_config_path or root / "scripts" / "run_v3_phase0_backtest.py",
            strategies_docs_dir=docs_dir,
        )
        self._index_path = docs_dir / "README.md"
        self._preflight_check = preflight_check or _run_exit_alignment_gate


    def register_strategy(
        self,
        strategy_class: type,
        strategy_config: StrategyConfig,
        candidate_id: str,
    ) -> None:
        module_stem = candidate_id
        family = str(strategy_config.metadata.get("generator", candidate_id.split("_")[0]))
        class_name, module_text = render_strategy_module(candidate_id, family, strategy_config.metadata.get("params", {}))
        self._preflight_check(self._paths.project_root)

        self._paths.strategies_dir.mkdir(parents=True, exist_ok=True)
        self._paths.strategies_docs_dir.mkdir(parents=True, exist_ok=True)
        module_path = self._paths.strategies_dir / f"{module_stem}.py"
        module_path.write_text(module_text, encoding="utf-8")

        update_strategy_registry(self._paths.strategies_init_path, candidate_id, class_name, module_stem)
        update_runner_cfg(
            self._paths.runner_config_path,
            candidate_id,
            is_event_driven=strategy_config.is_event_driven,
            required_funding="funding" in strategy_class().required_data(),
            required_oi="oi" in strategy_class().required_data(),
            universe=strategy_config.universe_fn(None),
            time_stop_bars=int(strategy_config.metadata.get("time_stop_bars", 3)),
            risk_per_trade_r=float(strategy_config.risk_per_trade_R),
        )

        strategy_doc = self.generate_strategy_doc(
            candidate_id,
            {
                "family": family,
                "params": strategy_config.metadata.get("params", {}),
                "strategy_name": strategy_config.name,
                "bar_freq": strategy_config.bar_freq,
                "is_event_driven": strategy_config.is_event_driven,
                "leverage_cap": strategy_config.leverage_cap,
                "risk_per_trade_R": strategy_config.risk_per_trade_R,
            },
            {},
        )
        doc_path = self._paths.strategies_docs_dir / f"{candidate_id}.md"
        doc_path.write_text(strategy_doc, encoding="utf-8")
        upsert_strategy_index(self._index_path, candidate_id, "promotion candidate", family, doc_path.name)

    def generate_strategy_doc(
        self,
        candidate_id: str,
        candidate_config: dict,
        metrics: dict,
    ) -> str:
        context = StrategyDocContext(
            candidate_id=candidate_id,
            family=str(candidate_config.get("family", candidate_id.split("_")[0])),
            stage="promotion candidate",
            params=dict(candidate_config.get("params", {})),
            metrics=metrics,
            strategy_name=str(candidate_config.get("strategy_name", candidate_id)),
            bar_freq=str(candidate_config.get("bar_freq", "")),
            is_event_driven=bool(candidate_config.get("is_event_driven", False)),
            leverage_cap=float(candidate_config.get("leverage_cap", 0.0)),
            risk_per_trade_r=float(candidate_config.get("risk_per_trade_R", 0.0)),
        )
        return render_strategy_doc(context)
