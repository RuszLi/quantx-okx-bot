from __future__ import annotations

from pathlib import Path

from src.pipeline.generators.funding_generator import FundingGenerator
from src.pipeline.graveyard import Graveyard
from src.pipeline.promoter import Promoter


def _seed_repo_layout(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    strategies_dir = tmp_path / "src" / "backtest" / "strategies"
    scripts_dir = tmp_path / "scripts"
    docs_dir = tmp_path / "docs" / "strategies"
    strategies_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)
    docs_dir.mkdir(parents=True)

    init_path = strategies_dir / "__init__.py"
    init_path.write_text(
        "\n".join(
            [
                '"""Strategy registry for tests."""',
                "",
                "from .base import StrategyConfig",
                "",
                "STRATEGIES = {",
                '    "listing_fade": object,',
                "}",
                "",
                "__all__ = [",
                '    "StrategyConfig",',
                '    "STRATEGIES",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    runner_path = scripts_dir / "run_v3_phase0_backtest.py"
    runner_path.write_text(
        "\n".join(
            [
                "from dataclasses import dataclass, field",
                "",
                "@dataclass(frozen=True)",
                "class StrategyRunConfig:",
                "    name: str",
                "    edge: str",
                "    is_event_driven: bool",
                "    required_funding: bool = False",
                "    required_oi: bool = False",
                "    universe: list[str] = field(default_factory=list)",
                "    time_stop_bars: int = 3",
                "    risk_per_trade_R: float = 0.20",
                "",
                "cfgs = {",
                '    "A": StrategyRunConfig("listing_fade", "A", is_event_driven=True),',
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    readme_path = docs_dir / "README.md"
    readme_path.write_text(
        "\n".join(
            [
                "# 策略索引",
                "",
                "| 策略 ID | 阶段 | 家族 | 文档 |",
                "| --- | --- | --- | --- |",
            ]
        ),
        encoding="utf-8",
    )
    return strategies_dir, init_path, runner_path, docs_dir


def test_promoter_register_strategy_writes_module_registry_and_doc(tmp_path: Path) -> None:
    strategies_dir, init_path, runner_path, docs_dir = _seed_repo_layout(tmp_path)
    params = {
        "z_score_threshold": 2.0,
        "r_to_r": 5.0,
        "stop_distance_pct": 0.003,
        "time_stop_bars": 12,
        "rv_window": 4,
        "regime_quantile_low": 0.40,
        "regime_quantile_high": 0.70,
        "funding_window": 720,
    }
    strategy_class = FundingGenerator().generate(params)
    promoter = Promoter(
        project_root=tmp_path,
        strategies_dir=strategies_dir,
        strategies_init_path=init_path,
        runner_config_path=runner_path,
        strategies_docs_dir=docs_dir,
        preflight_check=lambda _: None,
    )

    promoter.register_strategy(strategy_class, strategy_class.config, "funding_promoted_case")

    module_path = strategies_dir / "funding_promoted_case.py"
    doc_path = docs_dir / "funding_promoted_case.md"
    assert module_path.exists()
    assert doc_path.exists()

    module_text = module_path.read_text(encoding="utf-8")
    assert "FundingGenerator().generate" in module_text
    assert "FundingPromotedCaseStrategy" in module_text

    init_text = init_path.read_text(encoding="utf-8")
    assert "from .funding_promoted_case import FundingPromotedCaseStrategy" in init_text
    assert '"funding_promoted_case": FundingPromotedCaseStrategy,' in init_text

    runner_text = runner_path.read_text(encoding="utf-8")
    assert '"funding_promoted_case": StrategyRunConfig(' in runner_text
    assert 'name="funding_promoted_case"' not in runner_text
    assert 'StrategyRunConfig("funding_promoted_case", "funding_promoted_case", is_event_driven=False' in runner_text
    assert "required_funding=True" in runner_text

    doc_text = doc_path.read_text(encoding="utf-8")
    assert "## 1. 基本信息" in doc_text
    assert "## 10. 变更记录" in doc_text
    assert "promotion candidate" in doc_text


def test_promoter_aborts_without_writing_when_preflight_fails(tmp_path: Path) -> None:
    strategies_dir, init_path, runner_path, docs_dir = _seed_repo_layout(tmp_path)
    params = {
        "z_score_threshold": 2.0,
        "r_to_r": 5.0,
        "stop_distance_pct": 0.003,
        "time_stop_bars": 12,
        "rv_window": 4,
        "regime_quantile_low": 0.40,
        "regime_quantile_high": 0.70,
        "funding_window": 720,
    }
    strategy_class = FundingGenerator().generate(params)
    promoter = Promoter(
        project_root=tmp_path,
        strategies_dir=strategies_dir,
        strategies_init_path=init_path,
        runner_config_path=runner_path,
        strategies_docs_dir=docs_dir,
        preflight_check=lambda _: (_ for _ in ()).throw(RuntimeError("gate failed")),
    )

    try:
        promoter.register_strategy(strategy_class, strategy_class.config, "funding_gate_blocked")
    except RuntimeError as exc:
        assert "gate failed" in str(exc)
    else:
        raise AssertionError("register_strategy should fail when preflight gate fails")

    assert not (strategies_dir / "funding_gate_blocked.py").exists()
    assert not (docs_dir / "funding_gate_blocked.md").exists()
    assert "funding_gate_blocked" not in init_path.read_text(encoding="utf-8")
    assert "funding_gate_blocked" not in runner_path.read_text(encoding="utf-8")


def test_graveyard_bury_writes_rejected_doc_and_updates_index(tmp_path: Path) -> None:
    _, _, _, docs_dir = _seed_repo_layout(tmp_path)
    graveyard = Graveyard(strategies_docs_dir=docs_dir)

    doc_path = Path(
        graveyard.bury(
            candidate_id="funding_rejected_case",
            family="funding",
            params={"z_score_threshold": 3.0},
            metrics={"win_rate": 0.25, "ev_R": -0.12, "profit_factor": 0.8},
            failure_reasons=["holdout ev_R=-0.1000 <= 0", "robustness=LOW"],
        )
    )

    assert doc_path.exists()
    text = doc_path.read_text(encoding="utf-8")
    assert "rejected" in text
    assert "holdout ev_R=-0.1000 <= 0" in text
    assert "## 9. Review 结论" in text

    readme_text = (docs_dir / "README.md").read_text(encoding="utf-8")
    assert "funding_rejected_case" in readme_text
    assert "rejected" in readme_text
