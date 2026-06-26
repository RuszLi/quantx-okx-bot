# live runner post_only 入场 + R 仓位模型（高风险）

> **Plan Status:** draft
> **日期:** 2026-06-26 22:35
> **设计人:** 算法工程师视角
> **结果表面:** scripts/run_live_echo.py 的入场执行路径 + 仓位计算 + 与已修缺陷的回归交互
> **拆分来源:** 由初版拆出的第三份。**高风险**（真实资金下单）：须单独草审 + 单独关闭审计，不与其他计划共用结案。
> **依赖:** 入场费率/成交率假设依赖「回测费用分腿化」计划提供的口径；sizing 标定依赖 echo 阶段实测。

---

## 1. 背景

实盘 runner 现状两处与方案不符且影响真实资金：

1. **入场吃 taker**：`place_market_entry` 用 `ordType="market"`，方案（v3 §3.3/4.3/5.2）规定 `post-only limit at mid`（maker 0.02%）。
2. **sizing 脱离 R 模型**：`compute_sz` 按固定名义（`NOTIONAL_MULTIPLE × equity`），方案 §7.4 要求按 SL 距离反推使每笔真实风险 = 固定 1R。

第一轮独立草审对本表面指出 3 条高风险交互（第 3/4/5 条），本计划须全部纳入，不得遗漏。

## 2. Current Baseline（实时基线，已读源码）

| 位置 | 现状 | 问题 |
|---|---|---|
| `run_live_echo.py:204 place_market_entry` | `ordType="market"` | 吃 taker；改 post_only 后"下单即有仓"前提不再成立 |
| `run_live_echo.py:137 get_ticker_prices` | 仅取 `last`，无 bidPx/askPx | post_only 挂 mid 价无数据源（草审第 5 条） |
| `run_live_echo.py:239 get_fill_px` | 按 ordId 轮询 avgPx（5×0.3s） | 对未成交挂单返回 None，post_only 下语义需重构（草审第 3 条） |
| `run_live_echo.py:300/349/372 sltp_pending 状态机` | 假设市价单立即成仓 | post_only 下需区分 已挂未成交/已成交/超时撤单/部分成交 四态（草审第 3 条） |
| `run_live_echo.py:362-368 开仓前实时价方向校验` | 用 last 价在信号时刻校验 | post_only 成交延后，信号时刻校验过期；须改为成交确认后用 fill 价校验（草审第 3 条） |
| `run_live_echo.py:147 compute_sz` | 固定名义 `equity×NOTIONAL_MULTIPLE` | 与 SL 距离脱钩，真实风险≠1R |
| `NOTIONAL_MULTIPLE=10` (54) | 名义倍数常量 | R 模型接管后应废弃或降级为杠杆保护 |
| C SL≈1.5% (beta_decouple.py:59), cap=10x | — | R=30% 需 20×名义 > 10×cap → 实际 R 被钳到 15%（草审第 4 条） |
| D SL≈1% (weekend_wick.py:44), cap=7x | — | R=30% 需 30×名义 > 7×cap → 实际 R 钳到 7%（草审第 4 条） |
| 部分成交 | 设计列为非目标 | 限价单天然部分成交，与"不处理"自相矛盾（草审第 5 条） |

## 3. 目标 / 非目标

**目标：**
1. 入场改 post-only limit at mid + 超时撤单放弃，使实盘费率与方案一致。
2. 重构入场后状态机为四态（已挂未成交/已成交/超时撤单/部分成交），适配延后成交。
3. 成交确认后用实际 fill 价重做方向校验（替代信号时刻的 last 价校验）。
4. compute_sz 改 R 模型（SL 距离反推），受杠杆上限约束，并诚实披露杠杆钳制下 1R 失真。
5. NOTIONAL_MULTIPLE 去留决策 + 同步设计文档 §4.4/§4.5。

**非目标：**
- 不改回测（独立计划）。
- 不改 D 策略 TP（独立计划）。
- 不引入 WebSocket。

## 4. 执行阶段

### Phase 1 — BBO 数据源 + post_only 入场状态机（Fix-heavy，高风险）

`Skill: none`

- [ ] **Add** `get_ticker_prices` 或新函数抓 bidPx/askPx，计算 mid 价。
- [ ] **Decision | Fix** `place_market_entry` 改 post_only：挂 limit at mid（`ordType="post_only"`, px=mid），返回 ordId。
  - 处理 post_only 被拒（mid 可成交时 OKX 拒单，51xxx）。
- [ ] **Fix** 新增成交轮询：`get_order` 查 state（live/partially_filled/filled/canceled），超时未成交 → `cancel_order` 放弃。
- [ ] **Decision | Fix** sltp_pending 状态机重构为四态；部分成交时以实际成交 sz 挂 OCO（重新评估"不处理部分成交"非目标）。
- [ ] **Fix** 方向校验时机后移：成交确认后用实际 fill 价校验 SL/TP 方向（保留 attach_sltp 内 270-281 的校验，调整 sequencing）。

**Exit Criteria:**
- [ ] mid 价有数据源；post_only 入场 + 拒单处理 + 超时撤单落地。
- [ ] 四态状态机；部分成交对账正确。
- [ ] 成交后方向校验，干跑日志验证限价单挂出与撤单。

### Phase 2 — R 仓位模型 + 杠杆钳制披露（Fix，高风险）

`Skill: none`

- [ ] **Decision | Fix** compute_sz 改 R 模型：`notional = (risk_pct×equity)/(|entry−stop|/entry)`，受 `equity×leverage_cap` 上限，对齐 lotSz/minSz。
- [ ] **Proof** 数值披露表：每个候选合约算"目标 1R 所需名义 / 杠杆上限 / minSz"冲突结果，标注哪些合约在 $2-7 下开不出或 R 被钳低。诚实写入残余风险（草审第 4 条）。
- [ ] **Add/Fix** 单测：exit at stop ⇒ 损失 = min(risk_pct, cap×stop_dist_pct) × equity。
- [ ] **Decision** NOTIONAL_MULTIPLE 去留：R 模型接管后废弃或降级为杠杆保护；同步 `docs/design/2026-06-26-live-echo-runner.md` §4.4/§4.5。

**Exit Criteria:**
- [ ] compute_sz 按 R 模型，单测验证风险等式（含杠杆钳制分支）。
- [ ] 杠杆钳制数值披露表落地。
- [ ] 设计文档 §4 同步更新（改公共执行契约，No owner-doc update required 不适用）。

## 5. Closure Gates

- [ ] Phase 1/2 全部 Exit Criteria `[x]`。
- [ ] 干跑（dry-run / 模拟）验证 post_only 入场→成交/撤单→OCO 挂载全链路，不在主网真单验证前不得标 completed。
- [ ] 与已修缺陷的回归：OCO ordType、avgPx 查询、方向校验三处确认未被破坏（草审第 3 条）。
- [ ] 文本一致性 + `docs/logs/`。
- [ ] **独立草审 + 独立关闭审计**（高风险强制，不可单独冷重播回退）。

## 6. Closure（待填）

## 7. Draft Review Record

- 第一轮独立草审（针对初版）已识别本表面 3 条高风险交互（第 3/4/5 条），本计划 §2/§4 已全部纳入。待本计划自身的独立草审。
