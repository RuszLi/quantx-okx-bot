# 研究结论与实盘执行一致性根修复 实现计划

> **Plan Status：** draft\
> **创建日期：** 2026-06-27\
> **关联规范：** `docs/plans/00-plan-authoring-and-execution-guide.md`、`docs/requirements/00-requirement-synthesis-guide.md`\
> **关联上下文：** `scripts/run_live_echo.py`、`scripts/run_v3_phase0_backtest.py`、`src/paper/pipeline.py`、`docs/reports/2026-06-27-live-echo-drift-analysis-report.md`、`docs/retrospectives/2026-06-26-live-echo-runner-implementation-drift.md`

## Current Baseline

- `scripts/run_live_echo.py` 当前实盘运行对象是 `compute_ensemble_signals()` 产出的 `ensemble_C` / `ensemble_D`，不是 `reports/v3_output/per_strategy/weekend_wick/*` 这类单 edge 报告。
- `data/live_echo/trades.csv` 本地仅落盘了 14 条 entry 与 1 条 exit，但直接查询 OKX `orders_history`、`fills_history`、`account_bills` 可确认：后续真实平仓已发生，本地账本未完整回写。
- 2026-06-27 02:22:40.904 UTC 的 7 笔同步平仓，在 OKX `orders_history` 中明确标记为 `category = full_liquidation`；说明 live 面对的是账户级 cross 风险，而当前研究报告未把这层语义建模为 promotion gate（准入闸门）。
- `run_live_echo.py` 存在 live 专属入场过滤：实时价若已脱离 `stop_price / target_price` 区间则直接跳过，因此 live 实际成交样本与 backtest 样本不是同一批。
- `scripts/run_v3_phase0_backtest.py` 之前已修复一处回测 exit bar 频率错配，证明研究链路自身也存在语义漂移风险；但该修复仅收紧了 `weekend_wick` 单 edge 结论，并未解决“研究对象与实盘对象不一致仍可被错误晋升”的根问题。
- 当前仓库缺少一个不可绕过的 promotion gate：没有任何机制强制校验「研究对象、执行语义、账户风险语义、记账语义」四层是否与 live 完全对齐。
- 2026-06-27 按当前代码基线重新执行 `python scripts/run_v3_phase0_backtest.py --strategies B C E K H --skip-funding-download` 后，五条非事件驱动策略全部变为 `ABORT`：`B=-0.1434R / C=-0.1523R / E=-0.1780R / K=-0.3035R / H=0 trade`。其中 `C(beta_decouple)` 从旧报告 `PASS / EV=0.6108R / PF=82.5135 / avg_holding_bars=0.00` 翻转为当前 `ABORT / EV=-0.1523R / PF=0.3454 / avg_holding_bars=1.91`，说明不只是 `weekend_wick`，既有研究结论本身也需要重新审查。

## Goals

1. 建立一条不可绕过的 **research admission gate（研究准入闸门）**，阻止未完成研究设计、数据审查、对象定义和回测语义声明的策略直接流入实现。
2. 建立一条不可绕过的 promotion gate，阻止语义不一致的研究结果被当成实盘可执行结论。
3. 让 research / paper / live 明确绑定到同一个 `promotion candidate`（晋升候选对象），避免单 edge 报告和 ensemble live 混用。
4. 为 live 增加 exchange 对账与退出回写能力，使本地账本能够完整反映真实开仓、平仓、强平与已实现盈亏。
5. 明确建模并验证账户级风险语义（cross、杠杆、并发持仓、liquidation），禁止未建模情况下直接晋升 live。

## Non-Goals

- 不在本计划中直接优化某一条策略因子的 alpha（超额收益）本身。
- 不讨论新的策略创意，也不扩展新的交易品种或新 edge。
- 不把本计划拆成多个相互独立的小计划；本计划只处理“研究结论可否晋升实盘”的根语义问题。

## Invariants

- **Invariant 1：研究先于实现。** 任何策略若没有完整研究设计、数据来源说明、对象定义、风险声明与回测语义声明，不允许进入实现阶段。
- **Invariant 2：对象一致性。** 任何可晋升结论必须唯一指向一个明确的 live 执行对象；单 edge 报告不能直接代表 ensemble live。
- **Invariant 3：执行一致性。** live 专属过滤（实时价门槛、下单挂单语义、退出语义）若未在研究/回放中显式建模，则结论不可晋升。
- **Invariant 4：风险一致性。** 若 live 使用 cross、动态杠杆、并发持仓、账户级 liquidation 风险，则研究侧必须建模或显式阻断。
- **Invariant 5：记账一致性。** exchange 真实 fill / exit / liquidation 必须完整回写本地账本；本地账本不完整时，任何表现结论均无效。
- **Invariant 6：失败默认阻断。** 任一准入或一致性校验失败时，gate 必须 fail closed（默认阻断），不能降级为 warning。
- **Invariant 7：回测语义一致性。** 回测引擎的 exit klines 频率必须与策略声明的 `bar_freq` 严格对齐；非 event-driven 策略若使用与自身 bar 频率不一致的 exit klines，必须被 gate 阻断。此 invariant 源于 2026-06-27 `weekend_wick` 回测修复事件（详见 §Historical Context）。

## Phases

### Phase 0 — 研究准入治理（Decision | Fix | Proof）

- **Task 0.1 — Decision | 定义 research admission contract**\
  任何策略在进入实现前，必须先有：研究问题定义、目标对象定义、数据来源清单、数据适用边界、回测执行语义、账户风险假设、拒绝条件。
- **Task 0.2 — Fix | 研究工件模板化**\
  为策略研究引入统一模板，强制区分 `idea / research candidate / backtest candidate / live promotion candidate` 四个阶段，禁止跳级。
- **Task 0.3 — Fix | 未满足 research contract 时阻止实现**\
  若策略没有通过 research admission gate，就不能生成可被 signoff / promotion 消费的报告，也不能推进实现状态。
- **Task 0.4 — Proof | 补失败测试**\
  构造“只有回测结果、没有完整研究定义”的策略案例，验证 admission gate 直接失败。
- **Exit Criteria：** 仓库内存在独立的研究准入闸门；没有完整研究设计的策略，无法继续进入实现或晋升流程。

### Phase 1 — Promotion Candidate 基线收口（Fix-heavy）

- **Task 1.1 — Decision | 定义 promotion candidate 契约**\
  约束一个研究结论最小必须包含：策略对象 ID、edge 集合、symbol universe、bar 频率、entry 语义、exit 语义、风险语义、报告时间窗、验证状态。
- **Task 1.2 — Fix | 研究输出与 live 执行对象绑定**\
  把 `reports/v3_output/*` 与 `run_live_echo.py` 的执行对象对齐到统一的 candidate 描述，禁止单 edge 报告直接映射到 ensemble live。
- **Task 1.3 — Proof | 补失败测试**\
  当报告对象是 `weekend_wick`、live 执行对象是 `ensemble_C/D` 时，promotion gate 必须失败。
- **Exit Criteria：** 存在唯一候选对象契约；对象不一致的报告无法通过 gate。

### Phase 2 — 执行语义一致性门禁（Fix-heavy）

- **Task 2.1 — Fix | 明确建模 live 专属实时价门槛**\
  把 `run_live_echo.py` 中「实时价脱离 `stop/target` 区间则跳过」的执行语义提升为 candidate 必须声明的语义，不再允许隐藏在实盘脚本里。
- **Task 2.2 — Fix | 明确建模 live 下单/挂 SLTP 语义**\
  将 market entry、成交价回查、SL/TP attach 成功与失败路径纳入 candidate 执行契约。
- **Task 2.3 — Proof | 补失败测试**\
  若某个候选报告未声明 live 专属 price gate / attach 语义，则 gate 失败。
- **Exit Criteria：** live 专属入场与挂单差异被显式声明；未声明时无法晋升。

### Phase 3 — 账户风险语义一致性（Fix-heavy）

- **Task 3.1 — Fix | 把账户级风险暴露纳入 candidate**\
  候选对象必须声明 `tdMode`、杠杆设置策略、名义仓位分配规则、并发持仓上限、liquidation 是否已建模。
- **Task 3.2 — Fix | liquidation 风险未建模时阻断晋升**\
  若 report 只证明单笔 trade 级别逻辑、未覆盖 cross / multi-position / liquidation，则 gate 明确失败。
- **Task 3.3 — Proof | 补失败测试**\
  构造“研究报告无账户级风险建模，但 live 使用 cross + 多仓位”的场景，验证 gate 拒绝通过。
- **Exit Criteria：** 账户级风险是否已建模可被机器判断；未建模时不允许晋升。

### Phase 4 — exchange 对账与本地记账修复（Fix-heavy）

- **Task 4.1 — Fix | 增加 live 对账模块**\
  新增 exchange 对账逻辑，统一拉取真实 `positions / orders_history / fills_history / account_bills`，恢复完整持仓与已实现盈亏状态。
- **Task 4.2 — Fix | 本地 trade ledger 完整化**\
  本地账本必须记录：intent（意图）、entry ack、entry fill、SLTP attach、normal exit、forced close、full\_liquidation、final realized pnl。
- **Task 4.3 — Fix | 重启恢复语义**\
  runner 重启后若本地账本与 exchange 不一致，必须先 reconcile（对账）或 halt（阻断），不能继续裸跑。
- **Task 4.4 — Proof | 补失败测试**\
  模拟 exchange 端已平仓但本地账本无 exit 的场景，验证账本会补齐或 runner 停止。
- **Exit Criteria：** 本地账本可以完整反映 exchange 真实退出；重启后不再出现“只开不平”的假象。

### Phase 5 — Promotion Gate 落地与文档闭环（Decision | Add | Proof）

- **Task 5.1 — Fix | 在 state machine / signoff 中引入硬 gate**\
  `approved-for-gated-live` 之类状态必须依赖 candidate 对齐、执行语义对齐、账户风险对齐、账本对账完成四类证据。
- **Task 5.2 — Add | 生成根因与准入报告**\
  补一份 owner 文档，明确“什么报告可以驱动实盘、什么报告只能停留在研究层”。
- **Task 5.3 — Proof | 端到端验收**\
  用当前这次 `weekend_wick` vs `ensemble_C` 案例做反例，证明 gate 会拒绝错误晋升。
- **Exit Criteria：** 这类错晋升链路被仓库级门禁阻断；新报告若对象不一致无法进入 live。

## File Map

### 治理文档（核心产出）

- **新增：`docs/architecture/research-promotion-gate-framework.md`** — 晋升闸门框架总览：定义 research admission → promotion candidate → live execution 三阶段状态流转、各阶段准入契约、阻断条件与异常处理
- **新增：`docs/requirements/research-admission-contract-spec.md`** — 研究准入契约规范：策略进入实现前必须满足的 7 项必要条件（研究问题、对象定义、数据来源、回测语义、风险假设、拒绝条件、owner）
- **新增：`docs/requirements/promotion-candidate-contract-spec.md`** — 晋升候选契约规范：研究结论晋升实盘前必须满足的 6 项一致性校验（对象一致性、执行语义、账户风险、记账完整性、鲁棒性、owner signoff）
- **新增：`docs/design/promotion-state-machine.md`** — 晋升状态机设计：定义 `draft → research_review → admitted → backtest_candidate → promotion_candidate → approved_for_gated_live → live` 状态流转、状态间迁移条件、阻断与恢复机制
- **新增：`docs/design/live-execution-contract.md`** — 实盘执行契约：明确 live 专属过滤（实时价门槛、挂单语义、SL/TP attach）、账户级风险建模要求、exchange 对账与记账回写义务
- **更新：`docs/architecture/` 下相关 owner 文档** — 在实现落地后按实际行为补充

### 契约与状态机实现（核心产出）

- **新增：`src/research/admission_contract.py`** — `ResearchAdmissionContract` 数据类：定义准入契约的 7 项字段、校验方法、缺失项报告
- **新增：`src/research/promotion_contract.py`** — `PromotionCandidateContract` 数据类：定义晋升契约的 6 项一致性校验、对象对齐检查、执行语义声明
- **新增：`src/research/state_machine.py`** — `PromotionStateMachine` 状态机：管理策略从 idea 到 live 的状态流转、校验当前状态是否满足迁移条件、阻断非法迁移
- **新增：`src/research/gate_enforcer.py`** — `GateEnforcer` 闸口执行器：在关键节点（生成报告、signoff、启动 live）前强制调用契约校验，fail closed
- **修改：`src/backtest/metrics.py`** — 回测指标输出层：增加 `promotion_candidate_metadata` 字段，绑定契约 ID、校验状态、owner
- **修改：`src/reports/signoff.py`** — signoff 输出层：在生成报告前调用 `GateEnforcer`，未通过契约校验时阻断报告生成
- **修改：`scripts/run_live_echo.py`** — live 执行入口：启动前校验 `approved_for_gated_live` 状态，未通过时 halt
- **修改：`src/live/runner.py`** — live 执行包装层：增加 exchange 对账触发点、账本完整性校验、状态机状态回写

### 对账与记账修复（核心产出）

- **新增：`src/live/reconciliation.py`** — `ExchangeReconciliator` 对账模块：拉取 OKX positions/orders_history/fills_history/account_bills，与本地账本比对，生成差异报告
- **新增：`src/live/ledger.py`** — `TradeLedger` 完整记账：支持 intent / entry_ack / entry_fill / SLTP_attach / normal_exit / forced_close / full_liquidation / final_realized_pnl 全生命周期
- **修改：`src/live/risk_guard.py`** — 增加账本完整性校验：本地账本与 exchange 不一致时触发 halt

### 测试侧（验证用，非产出主体）

- `src/backtest/tests/test_research_admission_gate.py` — 验证准入契约校验逻辑
- `src/backtest/tests/test_promotion_candidate_parity.py` — 验证对象一致性检查
- `src/backtest/tests/test_live_semantic_contract.py` — 验证执行语义声明
- `src/live/tests/test_reconciliation.py` — 验证 exchange 对账逻辑
- `src/live/tests/test_trade_ledger_reconciliation.py` — 验证账本完整性校验
- `src/backtest/tests/test_hard_promotion_gate.py` — 验证端到端 gate 阻断

> 注：测试侧仅用于验证治理逻辑正确性，**不是本计划的主要产出物**。核心产出是上方"治理文档"与"契约/状态机实现"。

## Closure Gates

- [ ] research admission gate 生效：缺少研究问题定义 / 数据来源边界 / 对象定义 / 风险声明的策略无法推进到实现
- [ ] 对象一致性 gate 生效：单 edge 报告无法直接代表 ensemble live
- [ ] 执行语义 gate 生效：live 专属实时价门槛 / 挂单语义未声明时，晋升失败
- [ ] 账户风险 gate 生效：未建模 cross / leverage / liquidation 时，晋升失败
- [ ] 账本一致性 gate 生效：exchange-side exit / liquidation 未回写本地账本时，结论无效
- [ ] 回测语义一致性 gate 生效：exit klines 频率与策略 `bar_freq` 不一致时，回测被阻断
- [ ] `weekend_wick` vs `ensemble_C` 当前案例可被 gate 自动拒绝，而不是靠人工发现
- [ ] 重启后对账要么成功补齐本地账本，要么明确 halt

## Historical Context

### 2026-06-27 `weekend_wick` 回测修复事件

**事件摘要：**
- `scripts/run_v3_phase0_backtest.py` 中 `run_strategy_on_universe()` 对所有策略统一使用 `1m` klines 作为 `simulate_exits()` 的输入，但 `weekend_wick` 策略声明 `bar_freq="1h"` 且 `time_stop_bars=2`。
- 这导致回测时实际持仓约 2 分钟而非 2 小时，产生虚假高收益（`EV=1.2113R / PF=56.2137` → 修正后 `EV=0.0441R / PF=1.0934`）。

**修复措施：**
- 代码：`run_strategy_on_universe()` 改为仅对 `is_event_driven=False` 的策略按 `strategy.config.bar_freq` resample exit klines；`listing_fade` 仍保持 `1m` exit 路径不变。
- 测试：新增 `src/backtest/tests/test_v3_phase0_exit_alignment.py`，锁定「非 event-driven 策略必须按自身 bar 频率做 exit 模拟」约束。
- 日志：`docs/logs/2026/06-27.md` 记录。

**治理教训：**
- 此事件证明回测引擎的 exit klines 频率必须与策略声明的 `bar_freq` 严格对齐，否则会产生系统性虚假收益。
- 该约束已固化为 **Invariant 7：回测语义一致性**，并在 `PromotionCandidateContract` 中强制校验 `exit_klines_freq == strategy.bar_freq`。
- 未来任何新增策略或修改回测框架时，`GateEnforcer` 会自动阻断频率不一致的回测执行。

### 2026-06-27 非事件驱动策略复跑结论

**事件摘要：**
- 按输入文档要求，对 `B / C / E / K / H` 五条非事件驱动策略执行当前基线复跑。
- 新生成的 `reports/v3_output/v3_phase0_combo.md` 明确给出：`A 或 E 至少 1 条 PASS = FAIL`、`至少 2 条 strategy 单独 PASS = FAIL`、`❌ 禁止进入` ensemble。

**治理结论：**
- promotion gate 不能只校验“研究对象与 live 对象是否一致”，还必须承认一个更前置的事实：**当前研究输出本身可能已经失真**。
- 因此本计划后续所有 gate 设计，都必须把“旧报告是否仍然能被当前代码基线复现”作为 admission / promotion 前提之一。

## Proof Commands

- `python -m pytest src/backtest/tests/test_research_admission_gate.py -q`
- `python -m pytest src/backtest/tests/test_promotion_candidate_parity.py -q`
- `python -m pytest src/backtest/tests/test_live_semantic_contract.py -q`
- `python -m pytest src/live/tests/test_reconciliation.py src/live/tests/test_trade_ledger_reconciliation.py -q`
- `python -m pytest src/backtest/tests/test_hard_promotion_gate.py src/backtest/tests/test_signoff_report.py -q`
- `python scripts/run_live_echo.py --once`（安全 dry-run / mock 环境）
- 使用当前 `weekend_wick` 报告 + `ensemble_C` live 配置跑一次 promotion gate proof，预期明确失败
- `python scripts/run_v3_phase0_backtest.py --strategies B C E K H --skip-funding-download`（验证非事件驱动策略在当前基线下全部重算并沉淀最新报告）

## Draft Review Record

| 轮次 | 日期         | 评审方                                | 结论                         |
| :- | :--------- | :--------------------------------- | :------------------------- |
| 1  | 2026-06-27 | self-review + plan-agent synthesis | 初稿完成，待进入独立草稿审查后再转 `active` |

## Follow-up

- 若本计划落地后仍发现某些交易所返回字段不足以区分“用户手动平仓”与“系统触发强平”，再新增后继计划专门处理 OKX 事件分类细化；不在本计划第一版中扩 scope。
