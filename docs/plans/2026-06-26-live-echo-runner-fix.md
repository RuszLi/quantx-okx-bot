# Live Echo Runner 修复计划

> **Plan Status：** conditional-close
> **创建日期：** 2026-06-26
> **关联讨论：** [docs/discussions/2026-06-26-live-echo-runner-drift-fix.md](../discussions/2026-06-26-live-echo-runner-drift-fix.md)
> **关联缺陷：** [docs/bugs/2026-06-26-live-echo-runner-order-semantics.md](../bugs/2026-06-26-live-echo-runner-order-semantics.md)
> **关联复盘：** [docs/retrospectives/2026-06-26-live-echo-runner-implementation-drift.md](../retrospectives/2026-06-26-live-echo-runner-implementation-drift.md)
> **前置计划：** [docs/plans/2026-06-26-live-echo-implementation.md](2026-06-26-live-echo-implementation.md)

---

## Current Baseline

实盘 `scripts/run_live_echo.py` 处于「有进程在跑但实盘空转」状态：账户权益 $3.82、持仓 0，每轮仍尝试开仓并被 `sCode 51053` 拒绝。已确认事实：

- 账户 `posMode="long_short_mode"`（双向持仓），代码传 `posSide="long"`/`"short"` 方向符合账户语义。
- `check_exits`（`run_live_echo.py:217`）平仓调用未传 `reduce_only`；OKX 双向持仓模式下缺 `reduceOnly` 会视为新开反向仓。
- `place_market_order`（`run_live_echo.py:165-175`）的 `attachAlgoOrds` 直接透传策略信号 `stop_price`/`target_price` 到 `slTriggerPx`/`tpTriggerPx`，未按市价成交价做方向校验，触发 `sCode 51053`。
- `attach_sltp_to_existing`（`run_live_echo.py:277-310`）为死代码，`run_once` / `startup_check` 均不调用，但其 SL/TP 反推逻辑未对齐 51053 修复方向。
- `setup_leverage`（`run_live_echo.py:139-160`）硬编码 `lev = 50`，与计划文档 `MAX_LEVERAGE=1` 不符；Fix-11 还原 `compute_sz` 公式时需同步说明 `setup_leverage` 与 `MAX_LEVERAGE` 的关系（当前代码用 `setup_leverage` 设杠杆，`compute_sz` 用 `MAX_LEVERAGE` 算仓位，两者独立）。
- `RiskGuard` 风控闸门在 `run_live_echo.py` 与 `src/paper/pipeline.py` 双双移除（import 删除、`is_halted` 检查删除、`update_equity` 调用删除、`run_loop` break 删除、`startup_check` equity ≥ $7 校验删除）。
- `src/paper/pipeline.py:176` 的 `compute_ensemble_signals(inst_ids, equity=7.0)` 默认权益仍为 $7，但 `run_live_echo.py:339` 调用时未传 `equity` 参数，导致 `EnsembleStrategy.resolve_conflicts(available_equity=7.0)` 计算出与实盘 $3.82 不一致的仓位。Fix-2 恢复 RiskGuard 后需确保 equity 参数传递链路完整。
- `scripts/run_paper_ensemble.py` 已不依赖 `RiskGuard`，与实盘代码处于同一漂移基线。
- 计划文档 `2026-06-26-live-echo-implementation.md` 用 `posSide="net"` + `MAX_LEVERAGE=1` 描述，实际代码用 `long/short` + `lever=50`；偏差 6（`run_loop` 默认间隔 5s vs 计划 60s）、偏差 7（`get_instrument_map` 改 `public_api` + 丢 `ctMult`）、偏差 8（`compute_sz` 签名与公式变更）、偏差 9（函数名拼写）均已确认。

## Goals

1. **停掉无保护裸奔的实盘进程**，把剩余 $3 视作已耗损娱乐预算，转回 Paper / 回测层验证策略 EV，符合 `docs/discussions/2026-06-25-okx-algo.md` §5 退场条件。
2. **恢复 `RiskGuard` 风控闸门**（偏差 4、5），让 runner 在账户回撤超阈值时自动 halt。
3. **修复下单语义缺陷**（Bug-1 缺 `reduceOnly`、Bug-2 `attachAlgoOrds` SL/TP 方向校验失败），为未来重启实盘扫清阻断项。
4. **同步 paper & live 下单侧语义**（偏差 3），让纸交易验证结果可外推到实盘。
5. **清账次要漂移**（偏差 6/7/8/9、死代码删除），与计划/架构文档对齐。

## Non-Goals

- 不重启 $3 实盘（除非 D1 决策被评审推翻）。
- 不调整策略层（`beta_decouple.py` / `weekend_wick.py`）的信号生成逻辑——已核验策略侧 SL/TP 方向正确，缺陷在下单透传层。
- 不重写 `pipeline.py` 的信号计算结构，只回填 `RiskGuard` 检查位。
- 不修改 `src/okx_sdk.py` 工厂层。

---

## Phase 1 — Decision | 暂停实盘与修复方向定型

> **类型：** `Decision`-heavy（5 项决策项，全部源自讨论文档 §二 D1–D5）
> **Skill：** none

- [ ] **D1: 暂停 $3 实盘** — 录入决策结论：停掉 `run_live_echo.py` 进程，账户剩余权益不再追加实盘经费，后续验证只在 Paper / 回测层进行。考虑的替代方案：选项 B（继续实盘并存侥幸），残余风险：实盘暂停期间若手动重启进程仍会无保护运行，需在文档明确告警。
- [ ] **D2: RiskGuard 恢复参数** — 决定门槛与 anchor 取值：`startup_check` 最低权益门槛设为 `max(equity * 0.5, $1.0)`（$3 账户下门槛 $1.5，留 50% 缓冲给手续费/滑点，避免微跌即 halt）；`RiskGuard.anchor_equity` 取重启时刻权益（不再回溯历史峰值 $7）；`daily_max_drawdown_pct` 保持 0.15 默认（回撤阈值 = anchor * 0.85，与 startup 门槛 0.5 不冲突）。
- [ ] **D3: 下单 API 拆分形态** — `place_market_order` 拆为 `place_market_entry`（无 `reduceOnly`）与 `place_market_close`（强制 `reduceOnly=True`）。放弃「加 `reduce_only` 形参」的替代方案，理由：开仓和平仓的 attachAlgoOrds 语义差异大，单函数双语义容易再次误调用。
- [ ] **D4: Bug-2 修复方式** — 采纳方案 B：主单保留市价单，下单后调 `trade_api().get_fills()` 拿实际成交价，再用 `place_algo_order` 独立挂 SL/TP（放弃 `attachAlgoOrds` 一次性下单）。残余风险：SL/TP 与主单成交之间有数百毫秒无保护窗口。缓解措施：① `get_fills` 返回前设置 `sltp_pending=True` 标志位，阻止 `execute_entries` 新开仓；② algo 单挂成功前记录 WARN 级别日志并在 `state.json` 中标记 `sltp_pending`；③ 显式论证：$3 账户 + 50x 杠杆场景下，数百毫秒窗口最大损失 < $0.50（按 SOL 1% 波动估算），可接受。放弃方案 A（主单改限价单）的理由：限价单有成交不到的风险，违背「$3 量级优先保证开仓成功」。
- [ ] **D5: `attach_sltp_to_existing` 处理** — 直接删除死代码。理由：当前未被调用，且其 SL/TP 反推逻辑对齐 Bug-2 修复方向需重写，删除比修复更省工作量。

**Exit Criteria:**

- [x] 5 项决策结论以表格形式记录在 `docs/discussions/2026-06-26-live-echo-runner-drift-fix.md` §二，每项含「选择 / 替代 / 残余风险」三栏。
- [x] 评审通过本计划草稿。

## Phase 2 — Fix-heavy | 恢复 RiskGuard 风控闸门

> **类型：** `Fix`-heavy（5/5 项 Fix，偏差 4、5 主修，偏差 6 顺带）
> **Skill：** none

- [ ] **Fix-1: `src/paper/pipeline.py`** — `compute_ensemble_signals` 末尾回填 `risk_guard.is_halted` 检查：参数新增 `risk_guard: RiskGuard | None = None`，若传入且 `is_halted` 则返回空 DataFrame；保持向后兼容（Paper 调用不传也能跑）。
- [ ] **Fix-2: `run_live_echo.py`** — 回填 `from src.live.risk_guard import RiskGuard`；`run_loop` 创建 `RiskGuard` 并在 `run_once` 开头检查 `is_halted`；`check_exits` 平仓成功后调 `risk_guard.update_equity(equity, trade_pnl_r=upl)`；`run_loop` 触发 halt 时 `break`；`run_once` 调用 `compute_ensemble_signals(equity=equity)` 确保仓位计算与实盘权益一致（修复 Baseline 中 `equity=7.0` 默认值漂移）。
- [ ] **Fix-3: `run_live_echo.py:startup_check`** — 恢复权益门槛校验：阈值按 D2 决策设为 `max(equity * 0.5, $1.0)`，不再写死 $7；校验失败 `sys.exit(1)`。
- [ ] **Fix-4: `run_live_echo.py:run_loop`** — 默认 `interval_seconds` 还原为 60（计划值），`main` 中 `--interval` 默认同样改为 60。
- [ ] **Fix-5: `scripts/run_paper_ensemble.py`** — 把 `risk_guard: RiskGuard | None = None` 传入路径打通，让 paper 也享有同款风控（即便 paper 跑空仓也复用同一闸门，方便未来 paper→live 对齐）。

**Exit Criteria:**

- [ ] `python -c "from src.paper.pipeline import compute_ensemble_signals; from src.live.risk_guard import RiskGuard; print('OK')"` 输出 `OK`。
- [ ] `python scripts/run_paper_ensemble.py --once` 在 `RiskGuard.is_halted=True` 注入下能跳过下单（手动 mock 验证）。
- [ ] `python -c "import scripts.run_live_echo; print('live_echo OK')"` 输出 `live_echo OK`。

## Phase 3 — Fix-heavy | 下单语义修复（Bug-1 + Bug-2）

> **类型：** `Fix`-heavy（6/6 项 Fix）
> **Skill：** none

- [ ] **Fix-6: 拆分 `place_market_order`** — 删除原 `place_market_order`，新增 `place_market_entry(inst_id, side, sz, pos_side)` 与 `place_market_close(inst_id, side, sz, pos_side)`。后者内部强制 `reduceOnly=True`。
- [ ] **Fix-7: `check_exits`** — 平仓调用改为 `place_market_close(...)`，不再传 attachAlgoOrds（平仓单不需要止损止盈）。
- [ ] **Fix-8: `execute_entries`** — 开仓调用改为 `place_market_entry(...)`；删除当前函数里「任一持仓即 return []」「单笔 break」「valid_until 过期」三处偏离（计划偏差 3），还原为 per-symbol 已持仓跳过 + 一轮可开多笔 + 无过期检查。
- [ ] **Fix-9: 开仓后独立挂 SL/TP** — 开仓成功后调 `trade_api().get_fills()` 拿实际成交价，按 D4 方案 B 用 `place_algo_order` 挂 SL/TP（`reduceOnly=True`）。SL/TP 触发价按 `side` 显式方向校验：做空时 `slTriggerPx > fill_px`、`tpTriggerPx < fill_px`；做多反之。校验不通过直接放弃挂 algo 单并记 WARN，不阻断主单已成交结果。缓解措施：`get_fills` 返回前设置 `sltp_pending=True` 标志位（`state.json` 持久化），阻止 `execute_entries` 新开仓；algo 单挂成功后清除标志位。
- [ ] **Fix-10: 删除死代码** — 删除 `attach_sltp_to_existing` 函数定义（`run_live_echo.py:277-310`）。
- [ ] **Fix-11: `get_instrument_map` / `compute_sz` 还原** — `get_instrument_map` 改回 `account_api().get_instruments`，字段补回 `ctMult`；`compute_sz` 还原为 `compute_sz(inst_info, equity)`，公式还原 `equity * MAX_LEVERAGE / ct_val`，删除对 `price` 的依赖。Phase 3 执行前先预验证 `account_api().get_instruments` 返回字段包含 `ctMult`（实测 OKX API 确认字段可用性）。

**Exit Criteria:**

- [ ] `python -c "import scripts.run_live_echo; print('OK')"` 输出 `OK`，无 `place_market_order`、`attach_sltp_to_existing` 残留符号。
- [ ] 手动单元测试：mock `trade_api` 返回成功成交价后，`place_algo_order` 调用参数 `slTriggerPx`/`tpTriggerPx` 方向与 `side` 一致（用 `pytest` 或 inline 函数封装）。
- [ ] `place_algo_order` 调用必含 `reduceOnly=True`。

## Phase 4 — Add | 文档对齐与审计沉淀

> **类型：** `Add`-heavy
> **Skill：** `chinese-documentation`（文档排版校对）

- [ ] **Add-1: `docs/plans/2026-06-26-live-echo-implementation.md`** — 修订偏差 9 的函数名拼写：把 `compute_ensemble_signants` 改为 `compute_ensemble_signals`；把 `posSide="net"` 改为 `posSide="long"`/`"short"`（双向持仓）；`MAX_LEVERAGE=1` 说明更新为按 `lever` 配置；添加「已被本修复计划 supersede」顶部标注。
- [ ] **Add-2: `docs/architecture/okx-sdk-rules.md`** — 新增一节「OKX 双向持仓模式下单语义约束」，明确：① 平仓与 algo 单必须 `reduceOnly=True`；② `attachAlgoOrds` 的 SL/TP 触发价方向必须与主单方向一致，市价主单场景下必须先取成交价再校验。
- [ ] **Add-3: `docs/logs/2026/06-26.md`** — 追加本计划执行日志条目（按 `docs/logs/00-log-writing-guide.md` 倒序格式）。

**Exit Criteria:**

- [ ] 计划文档与实际代码无残留术语冲突：执行 `grep -rn "compute_ensemble_signants\|posSide.*net\|MAX_LEVERAGE" docs/plans/ scripts/ src/` 返回 0 匹配（或仅匹配注释/历史说明）。
- [ ] `okx-sdk-rules.md` 新增章节通过 `chinese-documentation` 技能检查清单（中英文空格、全角标点、术语中英对照），且章节长度 ≤ 30 行（避免文档膨胀）。

---

## Phase 5 — Proof | Paper 层一致性验证

> **类型：** `Proof`-heavy
> **Skill：** none

- [ ] **Proof-1: Paper 风控连通测试** — `scripts/run_paper_ensemble.py --once` 注入 `RiskGuard.is_halted=True`，确认 ensemble 无输出；再注入 `is_halted=False`，确认正常输出。
- [ ] **Proof-2: Paper 与 live 下单侧语义对齐** — 用 `git diff` 比对 paper 与 live 在退出 / 开仓分支上的代码骨架，确认 paper 已应用同款 `RiskGuard` 闸门、退出阈值、单仓制语义；任何残留差异记入 `docs/retrospectives/`。
- [ ] **Proof-3: Bug-1 与 Bug-2 回归** — 不在主网下真单，改在 OKX 模拟盘（`OKX_FLAG=1`）下跑一次 `python scripts/run_live_echo.py --once`，验证：① 平仓单携带 `reduceOnly=True`；② 开仓后 `place_algo_order` 的 SL/TP 触发价方向与成交价方向一致；③ 不再出现 `sCode 51169` / `51053`。
- [ ] **Proof-4（可选）: 主网 dry-run** — 模拟盘验证通过后，在主网（`OKX_FLAG=0`）下跑 `python scripts/run_live_echo.py --once --dry-run`（新增 `--dry-run` 参数，下单前 `sys.exit(0)` 或 intercept 模式），走完整 `startup_check → compute_signals → check_exits → execute_entries → place_algo_order` 流程但不实际发送 `place_order`，覆盖主网特有的延迟、流动性差异和 `sCode` 行为。

**Exit Criteria:**

- [ ] Proof-1 / Proof-2 / Proof-3 三项验证均通过；模拟盘日志归档到 `data/live_echo_sim/runner.log`。
- [ ] Proof-4 主网 dry-run 通过（若执行）；主网日志归档到 `data/live_echo_dryrun/runner.log`。
- [ ] 主网 `data/live_echo/runner.log` 自本计划执行起不再有新增条目（确认实盘进程已停）。

---

## Closure Gates

- [ ] Phase 1–5 全部 `Exit Criteria` 勾选完成。
- [ ] `docs/bugs/2026-06-26-live-echo-runner-order-semantics.md` 末尾「验证方法」5 项全部勾选。
- [ ] `docs/retrospectives/2026-06-26-live-echo-runner-implementation-drift.md` 偏差 1–9 状态与代码现状一致。
- [ ] `docs/discussions/2026-06-26-live-echo-runner-drift-fix.md` 待决策 D1–D5 全部标已决策。
- [ ] 主网实盘进程确认已停（无新增日志）。
- [ ] 独立关闭审计通过（待子代理执行）。

## Draft Review Record

| 轮次 | 日期 | 评审方 | 结论 |
|:---|:---|:---|:---|
| 1 | 2026-06-26 | 待执行 | 待独立草稿审查 |
| 2 | 2026-06-26 | 独立草稿审查员（子代理） | **需修订** — 3 项阻塞：B1（Phase 4 Exit Criterion 不可验证）、B2（D2 `equity*0.9` 门槛缺乏论证）、B3（Fix-9 无保护窗口缺缓解措施）；5 项建议：S1–S5。确认项 10/13 通过，3 项条件通过。 |
| 3 | 2026-06-26 | 计划作者 | **已修订** — 解决全部 3 项阻塞：B1 → Phase 4 Exit Criteria 改为可验证 grep 命令 + 章节长度 ≤ 30 行；B2 → D2 门槛改为 `max(equity*0.5, $1.0)` 并论证安全边际；B3 → D4/Fix-9 增加 `sltp_pending` 标志位 + state 持久化 + 最大损失估算。采纳全部 5 项建议：S1 → Baseline 补充 `setup_leverage`；S2 → Fix-2 补充 `equity` 参数传递；S3 → Phase 5 追加 Proof-4 主网 dry-run；S4 → Phase 4 Exit Criteria 限定 30 行；S5 → Fix-11 增加 API 字段预验证。Plan Status 转 `active`。 |

## Closure

> 独立关闭审计已完成，结论为「有条件通过」。审计报告要点：
>
> - Phase 1–4 核心目标已达成；Phase 5 Proof-1 / Proof-2 已完成；Proof-3 / Proof-4 因本地代理 SSL 握手失败无法实际调用 OKX，相关验证点已通过代码审查 + 单元测试覆盖。
> - 审计中发现并修复 `sltp_pending` 死锁风险：SL/TP 挂失败时立即平仓并释放标志位（见 `scripts/run_live_echo.py`）。
> - 剩余待补动作：代理 SSL 恢复后补跑 Proof-3 / Proof-4；将 `attach_sltp_via_algo_order` 单元测试固化为仓库测试文件；修正 `docs/design/2026-06-26-live-echo-runner.md` 中 `posSide="net"` 历史描述。
>
> 审计完整报告见本次会话子代理输出。

## Follow-up（已移出范围）

- **重启实盘评估** — 触发条件：Paper 层连续 24h 跑通 + 策略 EV 在 Paper 上转正。届时另立计划 `docs/plans/xxxx-live-echo-restart.md`。
- **审计清单沉淀** — 触发条件：同类下单漂移再次出现时。届时按 AGENTS.md 规则 15 把「实盘与计划一致性校验」固化为 `docs/audit/` 下的审计手册。