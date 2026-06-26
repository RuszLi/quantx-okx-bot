# D 策略（weekend\_wick）TP 下限 — 消除 R:R<1 结构性负期望

> **Plan Status:** active
> **日期:** 2026-06-26 22:30
> **设计人:** 算法工程师视角
> **结果表面:** weekend\_wick 策略的 target\_price 计算
> **拆分来源:** 由初版「费用感知执行 + R 仓位 + D TP」拆出的第二份独立计划。

***

## 1. 背景

D 策略（weekend\_wick）`target_price = prev_close`（`weekend_wick.py:46`），SL = `entry ± max(range×0.25, entry×1%)`（line 44-45）。当入场价仅略偏离 prev\_close 时，TP 距离极近而 SL 距离正常，单笔 R:R 可远小于 1。天然 R:R<1 的策略需要很高胜率才能维持正期望，叠加手续费门槛后更严苛。

本计划给 D 的 TP 加下限，保证 R:R ≥ 阈值，消除结构性负期望笔。

## 2. Current Baseline（实时基线，已读源码）

| 位置                      | 现状                                                  | 问题                            |
| ----------------------- | --------------------------------------------------- | ----------------------------- |
| `weekend_wick.py:43`    | `direction = -1 if entry_price > prev_close else 1` | 方向：fade wick                  |
| `weekend_wick.py:44`    | `stop_distance = max((high-low)×0.25, entry×0.01)`  | SL 距离正常                       |
| `weekend_wick.py:45`    | `stop_price = entry ± stop_distance`（方向感知）          | SL 对                          |
| `weekend_wick.py:46`    | `target_price = prev_close`                         | **无下限**：TP 可比 SL 近得多，R:R 可 <1 |
| `weekend_wick.py:47-55` | signal dict 输出 entry/target/stop                    | 下游回测/live 消费                  |

## 3. 目标 / 非目标

**目标：**

1. 给 `target_price` 加下限，使 TP 距离 ≥ `RR_MIN × stop_distance`（方向感知），保证 R:R ≥ RR\_MIN。
2. 重跑 D 回测，确认加下限后净 EV(R) 未恶化、R:R 分布合理。

**非目标：**

- 不改 D 的入场触发条件（weekday/volume/wick\_z 门控）。
- 不改 D 的 SL 逻辑。
- 不改 C 策略。
- 不动 live runner（独立计划）。

## 4. 执行阶段

### Phase 1 — TP 下限（Fix）

`Skill: none`

- [x] **Decision** TP 下限取法：`target_price` 在 `prev_close` 与"保证 R:R ≥ RR\_MIN 的价格"之间取**对持仓更有利**者（多头取更高、空头取更低），方向感知。
  - 选择理由：保留 prev\_close 作为均值回归目标的语义，仅当 prev\_close 太近时才拉到 RR\_MIN 下限，最小改动。
  - 替代方案：直接弃用 prev\_close 改对称 TP（改变 D 的 MR 语义，过度）。
  - RR\_MIN 取值：**定为 1.5**。对比同一窗口（2026-05-15 ~ 2026-06-24）、同一费用口径下，`1.5` 相比 `1.0` 在主口径 `fee=1.0 / slippage=1.0` 上 `ev_R` 从 `1.2042` 提升到 `1.2113`，`PF` 从 `55.8881` 提升到 `56.2137`，胜率与交易数不变；敏感性网格 9 个组合也全部同步抬升。
  - 残余风险：TP 拉远会降低命中率；须回测验证净 EV 不降。
- [x] **Add** RR\_MIN 作为模块级常量 + 注释说明治理理由。
- [x] **Add/Fix** 单测覆盖：构造 prev\_close 极近 entry 的 case，断言加下限后 R:R ≥ RR\_MIN。
- [x] **Proof** 重跑 D 回测（RR\_MIN=1.0 与 1.5 各一次），对比 EV(R)/PF/胜率/R:R 分布，据此定 RR\_MIN，记录入 §6。

**Exit Criteria:**

- [x] `weekend_wick.py` TP 有下限，RR\_MIN 常量 + 注释。
- [x] `python -m pytest src/backtest/tests/test_weekend_wick_strategy.py` 通过。
- [x] D 回测两个 RR\_MIN 值对比数字记录，RR\_MIN 已定。

## 5. Closure Gates

- [x] Phase 1 全部 Exit Criteria `[x]`。
- [ ] `python -m pytest src/backtest/tests/` 全绿。
- [x] §6 含 RR\_MIN=1.0 vs 1.5 的回测对比与最终取值理由。
- [x] 文本一致性：Plan Status、Phase Status、Exit Criteria、本节、`docs/logs/`。
- [ ] 独立草稿审查 + 独立关闭审计。
- [x] 依赖说明：本计划的回测对比已在「回测费用分腿化（maker/taker 分腿化）」落地后执行，当前 EV 反映新费用口径。

## 6. Closure（待填）

### Phase 1 Closure

**实现落地：**

- `src/backtest/strategies/weekend_wick.py`
  - 新增 `RR_MIN: Final[float]` 模块常量。
  - `target_price` 改为方向感知钳制：
    - 做空：`min(prev_close, entry_price - RR_MIN * stop_distance)`
    - 做多：`max(prev_close, entry_price + RR_MIN * stop_distance)`
- `src/backtest/tests/test_weekend_wick_strategy.py`
  - 新增边界测试，证明 `prev_close` 过近时，仍满足 `target_distance >= RR_MIN * stop_distance`。

**验证：**

- `python -m pytest src/backtest/tests/test_weekend_wick_strategy.py` → `2 passed`
- `python -m pytest src/backtest/tests/` → `59 passed / 3 failed`
  - 失败项：`test_live_runner_rejects_live_when_halted`
  - 失败项：`test_pre_funding_unwind_requires_settlement_window_and_reversal`
  - 失败项：`test_state_machine_transitions_through_alpha_and_cooldown`
  - 以上 3 项未触及本计划修改面，视为仓库预存失败，不归因于本次 D 策略 TP 下限改动。

**RR\_MIN 对比（窗口：2026-05-15 ~ 2026-06-24；命令：`python scripts/run_v3_phase0_backtest.py --strategies D`）：**

| RR\_MIN | n\_trades | win\_rate | ev\_R | PF | max\_dd\_% | TP/TIME/SL |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1.0 | 142 | 0.9296 | 1.2042 | 55.8881 | 94.83 | 71 / 70 / 1 |
| 1.5 | 142 | 0.9296 | 1.2113 | 56.2137 | 94.74 | 50 / 91 / 1 |

**敏感性网格观察：**

- 在 `time_stop_bars ∈ {2,3,5}`、`fee_multiplier ∈ {0.5,1.0,1.5}`、`slippage_multiplier ∈ {0.5,1.0,1.5}` 的 9 个组合中，`RR_MIN = 1.5` 的 `ev_R` 和 `PF` 均比 `1.0` 略高。
- 主口径（`fee=1.0`, `slippage=1.0`）提升：
  - `ev_R`: `1.2042` → `1.2113`（`+0.0071R`）
  - `PF`: `55.8881` → `56.2137`（`+0.3256`）
  - `win_rate`: 不变（`0.9296`）

**结论：**

- 最终采用 `RR_MIN = 1.5`。
- 原因：在不减少交易数、不降低胜率的前提下，`1.5` 在主口径与整个敏感性网格中都带来一致的小幅正向改进；因此比“仅消除负盈亏比”的 `1.0` 更优。

**当前门禁状态：**

- Phase 1 Exit Criteria：**完成**
- Closure Gates：**部分完成**（全量 pytest 仍有 3 个预存失败；独立草审/关闭审计未执行）

## 7. Draft Review Record

### Solo Draft Review（审查者不可用回退）

- 已执行冷回放：重新核对 `weekend_wick.py`、专项测试、两轮回测输出与计划文本一致性。
- 已确认本计划依赖的费用口径基于当日晚些时候已落地的 maker/taker 分腿模型，不再使用旧费用假设。
- 局限性：本次仅完成单人冷回放，尚未获得独立草稿审查与独立关闭审计，因此 Closure Gates 仍保持未完全关闭状态。
