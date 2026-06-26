# 回测费用模型分腿化（maker/taker 按出场原因计费）

> **Plan Status:** completed
> **日期:** 2026-06-26 21:40（独立草审后修订）/ 22:10 第二轮草审通过改 active / 23:25 独立关闭审计通过改 completed
> **设计人:** 算法工程师视角
> **结果表面:** C/D 回测的费用计算口径
> **拆分说明:** 本计划由初版「费用感知执行 + R 仓位 + D TP」拆出。初版被独立草审判定范围过宽且 Phase 1 锁错函数。另两份独立成案：D 策略 TP 下限、live runner post_only 执行 + R sizing（高风险，单独草审与结案）。

---

## 1. 背景

实盘 100 条订单复盘：毛 PnL ≈ -0.22 USDT，手续费 ≈ -1.13 USDT，手续费/毛PnL ≈ 5.1x——但绝大部分是 SL/TP 挂载失败导致的"开仓→秒平"空转，非策略盈亏（OCO `ordType` 已修）。

独立议题：C/D 回测的费用口径不可信。需先把回测费用模型修正到能反映真实 maker/taker 结构，否则后续任何基于回测 EV 的决策都建立在错误数字上。

**费率档（用户决策）：** 普通档保守值 maker 0.02% / taker 0.05%。

## 2. Current Baseline（实时基线，已逐行核对源码）

**关键纠正（初版 Baseline 错误，独立草审发现）：** C/D 回测**不走** `src/backtest/engine.py:simulate`，而走 `scripts/run_v3_phase0_backtest.py:simulate_exits`。该编排脚本从不 import `engine.simulate`、从不实例化 `ExecParams`。两套模拟器互相独立。

| 位置 | 现状（已核对） | 问题 |
|---|---|---|
| `run_v3_phase0_backtest.py:simulate_exits` (201) | C/D 实际回测路径，调用点在 481 与 564 | 这才是要改的函数 |
| `run_v3_phase0_backtest.py:303` | `fee_cost = FEE_TAKER_PER_SIDE * 2` 双腿全 taker | 入场实为 post_only maker（方案设计），SL taker、TP 取决于撮合 |
| `run_v3_phase0_backtest.py:65` | `FEE_MAKER_PER_SIDE = 0.0002` | **非死代码**：在 877 行打印进报告，但从未进入 303 行计费。"报告印 maker、实算 taker"是更隐蔽的误导 |
| `simulate_exits` `exit_reason` (272/277/283/288/294) | 已区分 "SL"/"TP"/"TIME" | 可作为出场计费分流键，计费点 303 处该变量已在作用域 |
| `save_sensitivity_grid:777` | `net_ret = raw_ret - fee * 2`（`base_fee=FEE_TAKER_PER_SIDE`，762 行） | **第二费用表面**（lead 核实补入）：敏感性网格也用双腿全 taker。仅改 303 行会导致主回测与敏感性网格口径不一致。须同步修正 |
| `src/backtest/engine.py:simulate` (27) `ExecParams` (15) | 独立模拟器，仅 `test_engine.py` 与 `run.py` 调用 | **本计划不改**；它不是 C/D 路径，改它对 C/D 零影响 |

## 3. 目标 / 非目标

**目标：**
1. `simulate_exits` 的费用计算按腿分流：入场 maker、出场按 `exit_reason` 分流（SL/TIME → taker，TP → taker 保守建模）。
2. `FEE_MAKER_PER_SIDE` 真正进入计费，消除"报告印 maker 实算 taker"的口径错位。
3. 重跑 C/D，记录费用模型变更前后 EV(R)/PF 对比。

**非目标：**
- 不改 `engine.py:simulate` 与 `ExecParams`（非 C/D 路径）。
- 不改 live runner 执行（独立成案）。
- 不改 D 策略 TP（独立成案）。
- **不把 TP 出场建模为 maker**（见 §4 Decision：OCO 触发型限价单不可靠为 maker，保守按 taker 计）。
- 不审计 C/D lookahead bias（独立 Follow-up）。

## 4. 执行阶段

### Phase 1 — simulate_exits 分腿计费（Fix）

`Skill: none`

- [ ] **Decision** 出场计费口径：入场 maker（post_only 设计），SL/TIME 出场 taker（市价确定成交），**TP 出场也按 taker 保守计**。
  - 选择理由：OCO 止盈是触发型限价单，触发瞬间市价已到触发价，同向限价单大概率立即撮合成 taker，或挂簿不成交（TP 落空）。"TP 吃 maker 且不损命中"在工程上不成立（独立草审第 2 条），故回测保守按 taker。
  - 替代方案：TP 建模为 maker（乐观，与实盘不符）；给 TP 加成交概率建模（复杂度过高，超本计划范围）。
  - 残余风险：入场假设 100% maker 成交本身偏乐观——存在逆向选择（mid 挂单优先在价格朝不利方向走时成交），bar 级回测无法精确建模。此为进 live 前已知盲区，在 §5 以保守下限场景说明，不在本计划内消除。
- [x] **Fix** `simulate_exits:303` 改为 `fee_cost = FEE_MAKER_PER_SIDE + FEE_TAKER_PER_SIDE`（入场 maker + 出场 taker），并更新该行注释为真实口径。
- [x] **Fix** 同步更新第 877 行报告展示文案，使"报告印的费率"与"实际计费口径"一致（注明入场 maker / 出场 taker）。
- [x] **Fix** `save_sensitivity_grid:777` 的 `net_ret = raw_ret - fee * 2` 同步改为分腿口径（入场 maker + 出场 taker），使敏感性网格基准与主回测一致。注意网格的 `fee_multipliers` 仍对总费用做 ±50% 缩放，缩放对象改为"分腿后的基准费用"。
- [x] **Proof** 重跑 C/D 回测，对比费用模型变更前后 EV(R)/PF/净 PnL，数字写入 §6 Closure。

**Exit Criteria:**
- [x] `simulate_exits` 费用 = maker(入场) + taker(出场)，注释口径正确。
- [x] `FEE_MAKER_PER_SIDE` 进入计费，报告文案与计费一致。
- [x] C/D 回测可重跑，EV(R)/PF 变更前后对比数字已记录。
- [x] 改公共回测口径，所属文档核查：v3 计划 `2026-06-25-1500-...` 第 1089-1090 行已记载 taker 0.05% / maker 0.02%（post-only 入场），费率事实与本次实现口径一致 → `No owner-doc update required`（本次仅让回测代码追上既有文档口径）。

## 5. Closure Gates

- [x] Phase 1 全部 Exit Criteria `[x]`。
- [x] 回测测试：`python -m pytest src/backtest/tests/` 58 passed / 3 failed。3 个失败经 git stash 验证为预存失败（test_state_machine / test_live_runner / test_pre_funding_unwind），不在本次改动文件内、不涉及费用模型（详见 §6.4）。本次改动无新增失败。
- [x] C/D 在新费用口径下重跑，EV(R)/PF/净 PnL 对比记录在 §6.1。
- [x] §6.2 给出"入场成交率打折"的保守下限场景说明（覆盖逆向选择盲区）。
- [x] 文本一致性：Plan Status、Phase Status、Exit Criteria、本节、`docs/logs/2026/06-26.md` 一致。
- [x] 独立草稿审查（已完成，§7：plan-reviewer + fee-implementer 双审）+ 独立关闭审计（trading-devs/tester 执行，六点全核验、C/D EV 独立复现匹配，2026-06-26 通过）。

## 6. Closure

### 6.1 费用模型变更前后对比（2026-06-26 22:50 重跑，窗口 2026-05-15 ~ 06-24）

| 策略 | n | 旧口径（双腿 taker，`fee*2`=0.10%） | 新口径（maker 入 + taker 出 = 0.07%） | 变化 |
|---|---|---|---|---|
| C beta_decouple | 24 | EV=0.5908R / PF=71.95 / WR=95.83% | EV=0.6108R / PF=82.51 / WR=95.83% | EV +0.020R，PF +10.6 |
| D weekend_wick | 142 | EV=1.1644R / PF=48.22 / WR=92.96% | EV=1.1929R / PF=53.91 / WR=92.96% | EV +0.029R，PF +5.7 |

费用从 0.10% 降到 0.07%（入场 maker 省 0.03%/腿），EV 微升、PF 上升，方向符合预期。胜率不变（费用只改每笔盈亏幅度，不改命中方向）。

### 6.2 保守下限场景（覆盖 post-only 逆向选择盲区）

回测假设 post-only 入场 100% 以 maker 成交，实盘存在两类乐观偏差，无法在 bar 级回测内精确建模：

1. **未成交流失**：mid 挂单超时未成交 → 信号被跳过，回测把这些"理论有利单"也计入。
2. **逆向选择**：mid 挂单优先在价格朝不利方向走时成交，即更可能被填在随后继续走反的单子上。

**保守下限估计**：若假设入场成交率打 7 折、且成交的单子里 EV 因逆向选择折损 30%，C 的 EV 从 0.61R 降至约 0.43R，D 从 1.19R 降至约 0.83R。两者仍 > Phase 0 的 +0.3R 门槛，但**该估计的前提是回测胜率本身可信**——见 6.3。

### 6.3 关键风险标记（必须先于任何 live 处置）

C/D 的回测胜率 95.83% / 92.96% 异常高，且费用修正前后纹丝不动。加密 1h 均值回归不可能有此胜率，这是 **lookahead bias 或样本内过拟合的强信号**。本计划只修正费用口径，**未触及该问题**。§8 Follow-up「审计 C/D lookahead bias」的触发条件（胜率 >85%）已成立，进任何 live 前必须先审计。

### 6.4 验证证据

- `simulate_exits:303` 与 `save_sensitivity_grid:763/778` 均改为分腿口径（maker 入 + taker 出），877 行报告文案同步。
- `python -m pytest src/backtest/tests/`：58 passed，3 failed。3 个失败（test_state_machine / test_live_runner / test_pre_funding_unwind）经 git stash 验证为**改动前已存在的预存失败**，均不在本次改动文件内、不涉及费用模型。
- 本次改动仅触及 `scripts/run_v3_phase0_backtest.py`（11 行）+ `.gitignore`，无回归。
- C/D 重跑数字见 6.1。

### 6.5 关闭审计

- 独立关闭审计由 trading-devs/tester 执行（2026-06-26 23:25 通过）：六点全核验，独立重跑 C/D 回测复现 §6.1 数字（C 0.6108R/82.51、D 1.1929R/53.91 完全匹配），确认 3 个失败测试为预存失败、877 报告文案一致、§6.3 lookahead 风险已如实记录。

## 7. Draft Review Record

- **2026-06-26 21:00 初版（被否决）：** 初版含 Phase 1（回测）+ Phase 2（D TP）+ Phase 3（live 执行 + sizing），范围过宽。
- **2026-06-26 21:30 独立草审（general 子代理）裁定「必须先修订，不可 active」，7 条问题：**
  1. 【严重】Phase 1 锁错函数——C/D 走 `simulate_exits:303` 非 `engine.simulate:128`。→ 本次重写 Baseline 与 Phase 1 已修正到正确函数。
  2. 【严重】TP 经 OCO 吃 maker 不成立。→ 本计划改为 TP 出场保守按 taker 建模。
  3. 【必改】post_only 破坏已修缺陷（get_fill_px / sltp_pending / 方向校验）。→ 属 live 执行范畴，移入独立成案。
  4. 【必改】R sizing 受杠杆上限钳制导致 1R 失真（C 在 10x 下最高 15% 非 30%）。→ 属 sizing 范畴，移入独立成案。
  5. 【应改】post_only 工程量（BBO/mid、拒单、轮询、cancel、部分成交）。→ 移入独立成案。
  6. 【应改】范围过宽应拆分。→ 已拆为三份独立计划，本份仅回测费用。
  7. 【小修】行号 247→260；"死代码"→"仅报告展示未计费"。→ 已在 Baseline 修正。
- **裁定：** 本份（仅回测费用）已针对第 1、2、6、7 条修订；第 3、4、5 条移交独立计划。待第二轮独立草审确认后改 active。
- **2026-06-26 22:10 第二轮独立草审（plan-reviewer/atlas + fee-implementer/sisyphus 双审）裁定「可改 active」。** lead 复核时另行核实并补入第二费用表面（`save_sensitivity_grid:777` 同样双腿全 taker），加进 §2 Baseline 与 Phase 1。方案改为 active。

## 8. Follow-up（命名触发条件）

- **审计 C/D lookahead bias**：触发——本计划落地、费用口径修正后，若 C/D EV 仍异常高（胜率 >85%），进任何 live 前必须审计 `build_c_market_data` 与策略滚动窗口对齐。
- **D 策略 TP 下限**：独立计划 `docs/plans/2026-06-26-XXXX-weekend-wick-tp-floor.md`（待建）。
- **live post_only 执行 + R sizing**：独立高风险计划（待建），需单独草审 + 单独结案。
