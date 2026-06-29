from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
import re


_INDEX_HEADER = "\n".join(
    (
        "# 策略索引",
        "",
        "| 策略 ID | 阶段 | 家族 | 文档 |",
        "| --- | --- | --- | --- |",
    )
)


@dataclass(frozen=True, slots=True)
class StrategyDocContext:
    candidate_id: str
    family: str
    stage: str
    params: dict[str, object]
    metrics: dict[str, object]
    failure_reasons: tuple[str, ...] = ()
    strategy_name: str = ""
    bar_freq: str = ""
    is_event_driven: bool = False
    leverage_cap: float = 0.0
    risk_per_trade_r: float = 0.0


def candidate_class_name(candidate_id: str) -> str:
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", candidate_id) if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) + "Strategy"


def ensure_strategy_index(readme_path: Path) -> None:
    if readme_path.exists():
        return
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(_INDEX_HEADER + "\n", encoding="utf-8")


def upsert_strategy_index(
    readme_path: Path,
    candidate_id: str,
    stage: str,
    family: str,
    doc_filename: str,
) -> None:
    ensure_strategy_index(readme_path)
    text = readme_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    row = f"| {candidate_id} | {stage} | {family} | `{doc_filename}` |"
    prefix = f"| {candidate_id} |"
    replaced = False
    updated_lines: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            updated_lines.append(row)
            replaced = True
            continue
        updated_lines.append(line)
    if not replaced:
        updated_lines.append(row)
    readme_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def render_strategy_doc(context: StrategyDocContext) -> str:
    metrics_json = json.dumps(context.metrics, ensure_ascii=False, indent=2, sort_keys=True)
    params_json = json.dumps(context.params, ensure_ascii=False, indent=2, sort_keys=True)
    failure_block = (
        "\n".join(f"- {reason}" for reason in context.failure_reasons)
        if context.failure_reasons
        else "- none"
    )
    stage_line = context.stage
    strategy_name = context.strategy_name or context.candidate_id
    object_kind = "single edge"
    event_driven_text = "yes" if context.is_event_driven else "no"
    verdict = "PASS" if context.stage == "promotion candidate" else "ABORT"
    promote_flag = "yes" if context.stage == "promotion candidate" else "no"
    gate_text = "ready for promotion" if context.stage == "promotion candidate" else "rejected by pipeline"
    lines = [
        f"# {context.candidate_id}",
        "",
        "## 1. 基本信息",
        "",
        f"- **策略 ID：** `{context.candidate_id}`",
        f"- **策略名称：** `{strategy_name}`",
        f"- **所属阶段：** `{stage_line}`",
        "- **Owner：** `edge-discovery-pipeline`",
        "- **关联输入：** `docs/plans/2026-06-28-1000-strategy-v3.2-automated-edge-discovery-pipeline.md`",
        "- **关联设计 / 架构 / 计划：** `docs/pipeline-user-guide.md`",
        "",
        "## 2. 研究问题",
        "",
        "- 这条策略试图捕捉什么行为偏差？ funding（资金费率）拥挤与波动率 regime（市场波动状态）切换下的非对称反应。",
        "- 该偏差为什么在 Crypto 市场中可能存在，而不是传统指标重包装？ 因为它直接使用 funding cashflow（资金费率现金流）与波动率分位，而不是 RSI / MA 这类传统技术指标。",
        "- 哪些证据支持继续研究，哪些证据会直接否决它？ 由 pipeline 的 IS gate、CPCV、DSR、holdout 与鲁棒性评级共同给出。",
        "",
        "## 3. 对象定义",
        "",
        f"- **执行对象：** `{object_kind}`",
        "- **symbol universe：** `BTCUSDT`",
        "- **市场类型：** `SWAP`",
        f"- **时间粒度：** `bar_freq = {context.bar_freq or 'unknown'}`",
        f"- **是否 event-driven：** `{event_driven_text}`",
        "",
        "## 4. 数据来源与点时约束",
        "",
        "| 数据 | 来源 | 粒度 | point-in-time 可得性 | 备注 |",
        "| --- | --- | --- | --- | --- |",
        f"| K 线 | Binance/本地缓存 | `1m → {context.bar_freq or 'N/A'}` | 是 | 由 `src/pipeline/data_layer.py` 聚合 |",
        "| Funding | OKX funding history | `1m 对齐` | 依 `point_in_time` 列判断 | 进入 settlement（结算时点）后才可视 |",
        "| OI | none | N/A | N/A | 当前候选未使用 |",
        "| 公告 / 事件 | none | N/A | N/A | 当前候选未使用 |",
        "",
        "- 参数快照：",
        "",
        "```json",
        *params_json.splitlines(),
        "```",
        "",
        "## 5. 信号定义",
        "",
        "- **入场条件：** funding z-score 超过阈值，且波动率 regime 已进入 `LOW / HIGH`。",
        "- **方向逻辑：** `LOW` regime 做反转，`HIGH` regime 做顺势。",
        "- **止损逻辑：** 使用参数化 `stop_distance_pct`。",
        "- **止盈逻辑：** 使用参数化 `r_to_r`。",
        f"- **时间止损：** `time_stop_bars = {context.params.get('time_stop_bars', 'unknown')}`",
        f"- **风险单位（1R）：** `{context.risk_per_trade_r:.2f}`",
        "",
        "## 6. 回测编排契约",
        "",
        "| 项目 | 当前值 | 说明 |",
        "| --- | --- | --- |",
        f"| `bar_freq` | `{context.bar_freq or 'unknown'}` | 策略声明频率 |",
        f"| `exit_klines_freq` | `{context.bar_freq or 'unknown'}` | `simulate_exits()` 输入频率 |",
        f"| `time_stop_bars` | `{context.params.get('time_stop_bars', 'unknown')}` | 最大持仓 bar 数 |",
        f"| `实际时间止损` | `time_stop_bars × {context.bar_freq or 'unknown'}` | 依策略频率解释 |",
        f"| `is_event_driven` | `{event_driven_text}` | 是否保留分钟级 exit |",
        "",
        "## 7. 风险语义",
        "",
        "- **账户模式假设：** `cross`",
        f"- **杠杆假设：** `{context.leverage_cap:.2f}`",
        "- **并发持仓上限：** `1`",
        "- **liquidation 是否已建模：** `no`",
        "- **哪些 live 过滤条件只存在于执行侧：** `none documented yet`",
        "",
        "## 8. 证据与验收",
        "",
        "- **必备报告：** `reports/pipeline_output/<run_id>/results.csv`",
        "- **必备测试：** `src/pipeline/tests/test_validator.py`、`src/pipeline/tests/test_executor.py`",
        f"- **必备输出文件：** `docs/strategies/{context.candidate_id}.md`",
        "- **拒绝条件：** 任何 gate 返回失败，或 holdout `ev_R <= 0`",
        "",
        "```json",
        *metrics_json.splitlines(),
        "```",
        "",
        "## 9. Review 结论",
        "",
        f"- **当前结论：** `{verdict}`",
        "- **主要风险：**",
        *failure_block.splitlines(),
        f"- **能否进入 promotion candidate：** `{promote_flag}`",
        f"- **若不能，卡在什么 gate：** `{gate_text}`",
        "",
        "## 10. 变更记录",
        "",
        "| 日期 | 变更 | 原因 |",
        "| --- | --- | --- |",
        f"| {date.today().isoformat()} | Pipeline auto-generated record | Phase 5 automation |",
    ]
    return "\n".join(lines) + "\n"


def render_strategy_module(
    candidate_id: str,
    family: str,
    params: dict[str, object],
) -> tuple[str, str]:
    generator_class = candidate_class_name(f"{family}_generator")[:-8]
    class_name = candidate_class_name(candidate_id)
    params_json = json.dumps(params, ensure_ascii=False, indent=4, sort_keys=True)
    module_text = "\n".join(
        (
            "from __future__ import annotations",
            "",
            f"from src.pipeline.generators.{family}_generator import {generator_class}",
            "",
            "",
            f"_PARAMS = {params_json}",
            f"_BaseStrategy = {generator_class}().generate(_PARAMS)",
            "",
            "",
            f"class {class_name}(_BaseStrategy):",
            '    """Auto-generated promoted strategy from edge discovery pipeline."""',
            "",
            "    pass",
            "",
        )
    )
    return class_name, module_text


def update_strategy_registry(
    init_path: Path,
    candidate_id: str,
    class_name: str,
    module_stem: str,
) -> None:
    text = init_path.read_text(encoding="utf-8")
    import_line = f"from .{module_stem} import {class_name}"
    if import_line not in text:
        import_lines = re.findall(r"^from \. .*?$", text, flags=re.MULTILINE)
        if import_lines:
            last_import = import_lines[-1]
            text = text.replace(last_import, last_import + "\n" + import_line)
        else:
            text = import_line + "\n" + text

    registry_entry = f'    "{candidate_id}": {class_name},'
    if registry_entry not in text:
        text = re.sub(
            r"(STRATEGIES\s*=\s*\{\n)(.*?)(\n\})",
            lambda match: match.group(1) + match.group(2) + ("\n" if match.group(2) else "") + registry_entry + match.group(3),
            text,
            count=1,
            flags=re.DOTALL,
        )

    all_entry = f'    "{class_name}",' 
    if all_entry not in text:
        text = re.sub(
            r"(__all__\s*=\s*\[\n)(.*?)(\n\])",
            lambda match: match.group(1) + match.group(2) + ("\n" if match.group(2) else "") + all_entry + match.group(3),
            text,
            count=1,
            flags=re.DOTALL,
        )

    init_path.write_text(text, encoding="utf-8")


def update_runner_cfg(
    runner_path: Path,
    candidate_id: str,
    *,
    is_event_driven: bool,
    required_funding: bool,
    required_oi: bool,
    universe: list[str],
    time_stop_bars: int,
    risk_per_trade_r: float,
) -> None:
    text = runner_path.read_text(encoding="utf-8")
    cfg_entry = (
        f'    "{candidate_id}": StrategyRunConfig('
        f'"{candidate_id}", "{candidate_id}", is_event_driven={is_event_driven}, '
        f'required_funding={required_funding}, required_oi={required_oi}, '
        f'universe={universe!r}, time_stop_bars={time_stop_bars}, '
        f'risk_per_trade_R={risk_per_trade_r:.2f}),'
    )
    if cfg_entry in text:
        return
    text = re.sub(
        r"(cfgs\s*=\s*\{\n)(.*?)(\n\s*\})",
        lambda match: match.group(1) + match.group(2) + ("\n" if match.group(2) else "") + cfg_entry + match.group(3),
        text,
        count=1,
        flags=re.DOTALL,
    )
    runner_path.write_text(text, encoding="utf-8")
