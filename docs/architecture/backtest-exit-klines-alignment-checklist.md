# 回测语义一致性检查清单

> **用途：** 在新增策略、修改回测引擎或 review 回测报告时，强制检查 exit klines 频率是否与策略声明的 `bar_freq` 对齐。
>
> **触发时机：**
> - 新增策略时（`src/backtest/strategies/*.py`）
> - 修改 `simulate_exits()` 或相关回测编排逻辑时
> - 策略回测报告 review 时
> - 任何涉及 `bar_freq`、`time_stop_bars`、`exit_klines` 的变更

## 检查项

### 1. 策略声明检查

- [ ] 策略 `config.bar_freq` 已明确声明（`1m` / `5m` / `10m` / `1h` / 其他）
- [ ] 策略 `config.is_event_driven` 已明确声明（`True` / `False`）
- [ ] 策略 `config.time_stop_bars` 已明确声明

### 2. Exit Klines 频率对齐检查

- [ ] 非 event-driven 策略：`simulate_exits()` 的 `klines` 参数必须按 `strategy.config.bar_freq` resample
- [ ] event-driven 策略：`simulate_exits()` 的 `klines` 参数保持 `1m`（或策略声明的 event 级别频率）
- [ ] 若策略使用自定义 exit 频率（如 `listing_fade` 的固定 5min），必须在策略文档中显式声明并说明理由

### 3. 时间止损语义检查

- [ ] `time_stop_bars` 的语义已明确：在 `bar_freq` 频率下，最大持仓 `time_stop_bars` 个 bar
- [ ] 实际持仓时间 ≈ `time_stop_bars × bar_freq_duration`（如 `2 × 1h = 2 小时`）
- [ ] 若实际持仓时间与预期不符（如 `2 × 1m = 2 分钟`），必须排查 exit klines 频率错配

### 4. 回归测试检查

- [ ] 新增策略必须配套 `test_v3_phase0_exit_alignment.py` 中的频率对齐测试
- [ ] 测试必须验证：非 event-driven 策略的 exit klines 频率 == `strategy.config.bar_freq`
- [ ] 测试必须验证：event-driven 策略的 exit klines 频率 == `1m`（或声明的 event 级别频率）

### 5. 报告元数据检查

- [ ] 回测报告的 `promotion_candidate_metadata` 中必须包含 `exit_klines_freq` 字段
- [ ] `exit_klines_freq` 必须与 `strategy.config.bar_freq` 一致
- [ ] 若不一致，`GateEnforcer` 必须阻断报告生成

## 历史案例

### 2026-06-27 `weekend_wick` 回测修复事件

**问题：**
- `weekend_wick` 策略声明 `bar_freq="1h"`、`time_stop_bars=2`
- 但 `run_strategy_on_universe()` 统一使用 `1m` klines 作为 `simulate_exits()` 输入
- 实际持仓 ≈ 2 分钟，而非预期的 2 小时
- 产生虚假高收益：`EV=1.2113R / PF=56.2137`

**修复：**
- `run_strategy_on_universe()` 按 `strategy.config.bar_freq` resample exit klines
- 修正后：`EV=0.0441R / PF=1.0934`（ABORT）

**教训：**
- 此检查清单正是为了防止此类问题重复发生
- 任何涉及 `bar_freq` 或 `exit_klines` 的变更，都必须经过此清单检查

## 相关文件

- `src/backtest/tests/test_v3_phase0_exit_alignment.py` — 频率对齐回归测试
- `src/research/gate_enforcer.py` — `GateEnforcer` 闸口执行器
- `docs/plans/2026-06-27-research-live-promotion-parity-root-fix.md` — 根修复计划（Invariant 7）
- `docs/logs/2026/06-27.md` — 事件日志
