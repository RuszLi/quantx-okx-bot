# V3 非事件驱动策略复跑结论报告

> **日期：** 2026-06-27
> **输入来源：** `docs/input/2026-06-27-1700-pm-source.md`
> **执行命令：** `python scripts/run_v3_phase0_backtest.py --strategies B C E K H --skip-funding-download`
> **代码基线：** `scripts/run_v3_phase0_backtest.py` 已包含 2026-06-27 的 exit klines 频率对齐修复

---

## 1. 目的

本报告只回答一件事：在当前代码基线下，`B / C / E / K / H` 五条**非事件驱动策略**重新回测后，是否仍然支持进入后续 `ensemble` 或实盘推进。

结论是：**不支持。** 五条策略全部为 `ABORT`，其中 `C（beta_decouple）` 从旧报告的乐观 `PASS` 翻转为当前 `ABORT`，证明此前研究结论存在不可接受的误导风险。

---

## 2. 复跑背景

`docs/input/2026-06-27-1700-pm-source.md` 已明确指出：

1. `weekend_wick` 的回测与实现存在严重漂移；
2. 同类问题不只影响 `D`，还可能影响 `C` 及所有非 `event-driven` 策略；
3. 立即动作应包含：重新回测 `B / C / E / K / H`，并基于新结果重新判断是否还能继续推进。

当前代码基线中，`scripts/run_v3_phase0_backtest.py` 已按 `is_event_driven` 分流：

- `event-driven=True` 的策略保留 `1m` exit 路径；
- `event-driven=False` 的策略会先按 `strategy.config.bar_freq` 进行 resample，再送入 `simulate_exits()`。

这意味着本次复跑已经覆盖了 2026-06-27 已知的 exit 频率错配修复。

---

## 3. 当前复跑结果

| Edge | Strategy | n_trades | win_rate | ev_R | profit_factor | avg_holding_bars | decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| B | `funding_extreme` | 238 | 0.3992 | -0.1434 | 0.6131 | 2.58 | `ABORT` |
| C | `beta_decouple` | 23 | 0.3478 | -0.1523 | 0.3454 | 1.91 | `ABORT` |
| E | `pre_funding_unwind` | 60 | 0.3500 | -0.1780 | 0.4628 | 2.80 | `ABORT` |
| K | `pair_mr` | 2091 | 0.5141 | -0.3035 | 0.4120 | 1.00 | `ABORT` |
| H | `oi_velocity` | 0 | 0.0000 | 0.0000 | 0.0000 | 0.00 | `ABORT` |

同时，`reports/v3_output/v3_phase0_combo.md` 已重新生成，并给出：

- `A 或 E 至少 1 条 PASS` → `FAIL`
- `至少 2 条 strategy 单独 PASS` → `FAIL`
- `进入 Day 3 Ensemble 仲裁层资格` → `❌ 禁止进入`

---

## 4. 与旧结论的关键差异

最重要的变化发生在 `C（beta_decouple）`：

| 口径 | n_trades | win_rate | ev_R | profit_factor | avg_holding_bars | decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 旧结果（事故前遗留） | 24 | 0.9583 | 0.6108 | 82.5135 | 0.00 | `PASS` |
| 当前复跑 | 23 | 0.3478 | -0.1523 | 0.3454 | 1.91 | `ABORT` |

这说明此前最具误导性的不是单纯的参数波动，而是**研究语义与回测语义本身不可信**。旧结果里的 `avg_holding_bars = 0.00` 也与策略声明的小时级持仓不一致，不能作为任何推进依据。

---

## 5. 诊断解读

### 5.1 可以确认的事实

1. `D` 的 exit 频率问题不是孤例，复跑后 `C` 也已从乐观结论翻为 `ABORT`。
2. 当前 `B / C / E / K / H` 五条非事件驱动策略在现代码基线下全部不能通过单 edge 闸门。
3. `H` 没有任何交易，说明它在当前数据与阈值设定下连可用样本都不足。
4. `K` 虽然交易数很多，但 `EV(R)` 与 `PF` 明显为负，属于“高频亏损放大器”，不是可晋升候选。

### 5.2 不能再继续假设的前提

以下前提现在都应视为**无效**：

- “修完 `weekend_wick` 之后，其他策略大概率还能继续推进”；
- “`beta_decouple` 仍然是当前 live / paper 的可靠主线”；
- “只要补一个 gate，就能保住原先的 V3 研究结论”。

本次复跑表明，至少对非事件驱动策略集合而言，**研究层结论本身需要重新审查，不只是实现层补闸门。**

---

## 6. 处置建议

### 6.1 立即结论

1. 暂停把 `B / C / E / K / H` 中任何一个作为 `ensemble` 或实盘晋升依据。
2. 将 `docs/plans/2026-06-27-research-live-promotion-parity-root-fix.md` 中的当前基线补入本次复跑证据。
3. 将 `docs/strategies/` 建为独立目录，用统一模板约束后续每条策略必须显式声明：
   - 研究对象；
   - 回测编排路径；
   - `bar_freq` 与 `exit_klines_freq`；
   - promotion gate 依赖的证据。

### 6.2 当前不做

- 本报告**不**直接改动策略参数；
- 本报告**不**直接尝试把任意 `ABORT` 策略修到 `PASS`；
- 本报告**不**重新开放 `ensemble` 或 live 推进。

---

## 7. 关联证据

- 事故输入：`docs/input/2026-06-27-1700-pm-source.md`
- 根修复计划：`docs/plans/2026-06-27-research-live-promotion-parity-root-fix.md`
- 横向汇总：`reports/v3_output/v3_phase0_combo.md`
- 单策略报告：
  - `reports/v3_output/v3_funding_extreme.md`
  - `reports/v3_output/v3_beta_decouple.md`
  - `reports/v3_output/v3_pre_funding_unwind.md`
  - `reports/v3_output/v3_pair_mr.md`
  - `reports/v3_output/v3_oi_velocity.md`

---

## 8. 一句话结论

2026-06-27 的非事件驱动策略复跑已经足够证明：**当前 V3 研究结论不能继续沿用，必须先重建策略文档与晋升闸门，再谈下一轮研究推进。**
