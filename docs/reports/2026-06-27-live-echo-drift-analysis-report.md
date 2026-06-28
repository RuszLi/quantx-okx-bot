# Live Echo 实盘漂移分析报告

> **版本：** v1
> **日期：** 2026-06-27
> **分析范围：** `scripts/run_live_echo.py` vs `docs/design/2026-06-26-live-echo-runner.md`
> **数据来源：** `data/live_echo/trades.csv`（16 条记录）、`data/live_echo/state.json`、`scripts/run_live_echo.py`（542 行）

---

## 1. 摘要

实盘运行器 `run_live_echo.py` 与设计基线 `2026-06-26-live-echo-runner.md` 之间存在 **6 项可确认的漂移**，其中 3 项风险等级为「高」、2 项为「中」、1 项为「低」。最关键的漂移集中在退出机制（依赖 OKX OCO 而非设计规定的主动 -3%/+6%/5h 阈值判断）和最大并发持仓数（代码 `5` vs 设计 `2`）。此外，`data/live_echo/trades.csv` 显示 **16 笔交易中仅 1 笔 exit**（SOLUSDT，+3.4% take_profit），其余 15 笔处于未平仓状态，说明退出覆盖存在严重缺口。

---

## 2. 分析范围

| 维度 | 描述 |
|------|------|
| 设计基线 | `docs/design/2026-06-26-live-echo-runner.md` v1 |
| 代码实现 | `scripts/run_live_echo.py`（当前 542 行） |
| 运行数据 | `data/live_echo/trades.csv`（16 条交易记录） |
| 状态快照 | `data/live_echo/state.json`（933 轮 cycle、峰值权益 $9.51） |
| 计划文档 | V3.1 Strategy Edge 清单（C/D/E/A/B/K/H 共 7 条 edge） |

未纳入本次分析的范围：信号计算逻辑（`src/paper/pipeline.py`）、风控模块（`src/live/risk_guard.py`）、OKX SDK 适配层。

---

## 3. 漂移矩阵

### 3.1 汇总表

| # | 漂移点 | 设计文档值 | 代码实际值 | 证据 | 风险等级 |
|---|--------|-----------|-----------|------|---------|
| 1 | 最大并发持仓 | `MAX_CONCURRENT_POSITIONS = 2`（§4.6） | `MAX_CONCURRENT_POSITIONS = 5`（代码 line 61） | 设计明确 N=2，代码常量 5 | **高** |
| 2 | 退出机制 | 主动阈值判断：-3%/+6%/5h（§5.2） | 完全依赖 OKX OCO 止盈止损 algo 单（`attach_sltp_via_algo_order`） | 代码无任何 `upl` 比较或时间检查逻辑 | **高** |
| 3 | exit 覆盖不足 | 预期成对进出（entry → exit 完整 round-trip） | 16 笔交易仅 1 笔 exit（SOLUSDT exit_long） | trades.csv：15 enter : 1 exit | **高** |
| 4 | 启动权益门槛 | `totalEq >= 7.0`（§6.2） | `min_equity = max(equity * 0.5, 1.0)`（代码 line 430） | 动态门槛而非固定 $7 | **中** |
| 5 | 持仓方向模式 | `posSide="net"`（§4.2/§4.3） | `posSide = "long" if signal == 1 else "short"`（代码 line 352） | 代码使用 `long_short_mode` 而非 net | **中** |
| 6 | state 多出字段 | state.json 无 `sltp_pending`（§7） | state.json 含 `"sltp_pending": false`（代码 line 78） | load_state 默认字典多出一个字段 | **低** |

### 3.2 各漂移点详细证据

#### 漂移 1：最大并发持仓（高）

```
设计文档 §4.6：
  同时持仓数 | MAX_CONCURRENT_POSITIONS（当前 = 2）

代码 line 61：
  MAX_CONCURRENT_POSITIONS = 5
```

设计文档 §4.6 用了约 400 字论证 N=2 的必要性：手续费侵蚀、相关性使分散失效、保证金名额限制。代码实际值 5 意味着：
- 单轮 round-trip 手续费从 ~1-2%（N=2）提升至 ~3-4%（N=5）
- 高度相关的 alt 仓位并排放大 beta 暴露

**值得注意的是：** design §4.6 原文写了"N=2 在'集中'与'保留一次对冲可能'间取平衡"，但并未将设计值约束到代码层面（无 CI 检查或单元测试）。这可能解释了为什么开发者选择了更激进的 5。

#### 漂移 2：退出机制（高）

```
设计文档 §5.2：
  Stop Loss  | upl <= -0.21（-3% of $7） | 市价单平仓
  Take Profit| upl >= +0.42（+6% of $7） | 市价单平仓
  Time Stop  | 持仓 > 5 小时             | 市价单平仓

代码实现：
  无任何 upl 轮询或持仓时间检查
  退出仅依赖 place_algo_order(ordType="oco") 挂载的 SL/TP
```

代码中的 `manage_positions()` 函数在设计架构图（§2）中是一个独立步骤，但实际代码中完全不存在。退出完全委外给 OKX 的 OCO algo 单。OCO 的止盈止损参数来自信号自身携带的 `stop_price` / `target_price`，而非设计文档定义的固定百分比（-3%/+6%）。

OCO 机制本身是合理替代方案，但存在以下差异：
- **触发条件不同**：设计文档基于未实现盈亏（`upl`），OCO 基于价格触发——两者在杠杆场景下不等价（20x 杠杆下 2% 价格变化 ≈ 40% 权益变化）
- **缺乏 Time Stop**：OCO 没有时间维度；若持仓既不触发 SL 也不触发 TP，将无限期持有
- **挂单失败无保护**：代码 line 394-402 实现了"挂 OCO 失败则立即市价平仓"，但若 OCO 挂单成功后被部分成交或撤销，代码不检测

#### 漂移 3：exit 覆盖不足（高）

```
trades.csv 数据：
  总记录：16
  enter_long / enter_short：15 笔
  exit_long：仅 1 笔（SOLUSDT，price=66.53，pnl=+3.4%，reason=take_profit）

  未平仓明细：
  - SOLUSDT enter_short @ 68.24（约 38h 未平）
  - DOGEUSDT enter_long @ 0.07386（约 14h 未平）
  - OPUSDT enter_long @ 0.10322（约 14h 未平）
  - DOGEUSDT enter_short × 2（约 9h / 2.8h 未平）
  - ADAUSDT enter_short × 2（约 9h / 2.8h 未平）
  - XRPUSDT enter_short × 2（约 8.5h / 2.8h 未平）
  - SOLUSDT enter_long @ 72.39（约 2.8h 未平）
  - NEARUSDT enter_short @ 1.81（约 2.8h 未平）
  - LTCUSDT enter_short @ 41.9（约 2.4h 未平）
  - LINKUSDT enter_short @ 7.331（约 2.2h 未平）
```

可能的解释：
1. OCO 已成功挂载但当前价格未触发任一阈值——无 Time Stop 意味着无限期等待
2. 部分仓位的 OCO 挂载失败但被重试逻辑处理为立即平仓——但平仓交易未记录到 trades.csv（说明平仓操作可能成功了但没有被记录）
3. 这些未平仓实际上可能是"幽灵持仓"（exchange 端已无仓位但本地认为还有），脚本重启后不会恢复 OCO 状态

#### 漂移 4：启动权益门槛（中）

```
设计文档 §6.2：
  account_api().get_account_balance() 返回 totalEq >= 7.0

代码 line 430-433：
  min_equity = max(equity * 0.5, 1.0)
  if equity < min_equity:
      logger.error(f"权益不足 ${min_equity:.2f}（当前 ${equity:.2f}）")
      sys.exit(1)
```

**影响：** 设计文档要求最低 $7 才能启动。代码采用 `max(equity * 0.5, 1.0)`——当 equity ≈ $9.5（state.json 记录的 peak_equity），门槛为 $4.75；当 equity ≈ $3（假设大幅回撤后），门槛仅为 $1.50。这实际上让权益可以回撤到接近于零才停止，与设计文档 $7 的严格门槛严重不符。风险是：连续亏损可以让账户权益从 $9.50 跌至 $1.50 才触发停止，此时总回撤约 84%，远超设计允许的 15%。

#### 漂移 5：持仓方向模式（中）

```
设计文档 §4.2：
  posSide="net"

代码 line 352：
  pos_side = "long" if is_long else "short"
```

代码使用 `long_short_mode`（OKX 双向持仓模式），而非设计指定的 `net` 模式。设计文档 §4.1 的注释（2026-06-26 修订）提到该修订是因为"实测账户配置为 `long_short_mode`"，因此设计文档本身知道此分歧但尚未统一。代码的 `posSide` 传参与账户配置一致，但设计文档的 §4.2/§4.3 代码示例仍使用 `posSide="net"`，属于设计文档未及时更新。

#### 漂移 6：state 多出 sltp_pending 字段（低）

```
设计文档 §7 state.json 结构：
  { session_start, cycle_count, total_trades, peak_equity, halted, halt_reason }

实际 state.json：
  {"session_start":"...","cycle_count":933,"total_trades":15,
   "peak_equity":9.5066,"halted":false,"halt_reason":null,
   "sltp_pending":false}  ← 多出字段
```

该字段用于 `execute_entries` 函数中的互斥逻辑（line 314）：当 `sltp_pending == true` 时，跳过所有新开仓，避免在前一轮 OCO 挂载完成前再开新仓。这是一个合理的运行保护字段，但不属于设计基线，应补充到设计文档。

---

## 4. 根因分析

### 4.1 直接原因

| # | 漂移 | 最可能的根因 |
|---|------|------------|
| 1 | MAX_CONCURRENT_POSITIONS = 5 | 开发阶段为保证信号被充分执行而放宽限制；设计文档无自动化校验，人工审阅遗漏 |
| 2 | 退出机制依赖 OCO | 开发发现 OCO 可以复用信号自带的 stop_price/target_price，比重新计算 upl 更简单，但未同步更新设计文档 |
| 3 | exit 覆盖率低 | OCO 挂单后不做存活检测；缺少 Time Stop 兜底；部分仓位可能是 ghost positions |
| 4 | 启动权益门槛动态化 | 开发者意图让脚本在权益波动时更灵活，避免频繁重启；但未评估极端回撤场景 |
| 5 | posSide=long/short | 账户实际配置为 `long_short_mode`（见设计文档 §4.1 修订注释）；设计文档的 net 代码示例未更新 |
| 6 | sltp_pending 字段 | 实现 OCO 互斥锁的工程需要，设计阶段未预见 |

### 4.2 深层原因

1. **设计文档与代码开发异步迭代**：设计文档 v1 定稿后，实盘开发过程中发现问题并做了调整（如 OCO 替代主动退出、posSide 适配 `long_short_mode`），但调整未追溯更新设计基线。
2. **缺乏自动合规检查**：设计文档中的常量（`MAX_CONCURRENT_POSITIONS`、权益门槛）没有对应的单元测试或 lint 规则来验证代码值与设计值一致。
3. **手动漂移容忍文化**：§4.5 的注释提到"禁止漂移回 MAX_LEVERAGE=1"，§4.6 提到"禁止漂移回无上限模型"——说明团队意识到漂移风险，但仅停留在注释层面，未引入工程约束。

### 4.3 策略 edge 覆盖分析

V3.1 计划文档列出 7 条 edge（A/B/C/D/E/K/H），当前实盘 runner 仅执行 C/D ensemble：

```
代码 line 448-450：
  live_strategy_edges():
    return {"C", "D"}  # 周末
    return {"C"}       # 工作日
```

所有 16 笔交易记录均标注 `ensemble_C`，策略 D 未产生任何信号。这可能是因为策略 D（Weekend Wick）的触发条件在分析期间未被满足，也可能是 `pipeline.py` 中的 D 信号计算存在问题。待确认。

---

## 5. 风险影响

### 5.1 资金风险

| 风险项 | 概率 | 影响 | 量化 |
|--------|------|------|------|
| OCO 失效导致无限期持仓 | 中 | 高 | 15/16 仓位无退出记录，合计名义敞口约 $35/仓，总敞口可能达到 $175（5 仓 × $35） |
| Time Stop 缺失 | 中 | 中 | 最长持仓已超过 38h（SOLUSDT enter_short），设计预期 5h 内退出 |
| 启动门槛过低 | 低 | 高 | 若权益跌至 $1.50 才停止，总回撤 ≈ 84%，远超 15% 限制 |
| 并发 5 仓手续费侵蚀 | 确定 | 中 | 每轮 round-trip 手续费 ≈ 名义 × 0.1%，5 仓 = $0.175，$3 级别本金仅够 17 轮 |

### 5.2 合规与治理风险

| 风险项 | 说明 |
|--------|------|
| 设计文档失效 | 设计文档不再是代码的可靠描述，新成员 onboarding 会产生认知偏差 |
| 决策记录不完整 | `MAX_CONCURRENT_POSITIONS` 为什么从 2 变成 5 没有文档记录，未来无法回溯 |
| 验证盲区 | 无 CI 检查确保代码常量和设计常量一致 |

### 5.3 运营风险

- **session 断连恢复**：state.json 的 `sltp_pending` 仅表示 OCO 挂载状态，不记录实际挂载的 algoId。脚本重启后无法恢复 OCO 状态跟踪。
- **多 session 数据污染**：state.json 记录 `session_start` 和 `last_run` 跨越不同时间窗口（trades.csv 最早记录 06-26T03:26，state 的 session_start 是 06-27T00:08），说明至少有两轮独立 session，但 state 只保留最后一个 session 的信息。

---

## 6. 建议措施

### 6.1 立即措施（高优先级）

| # | 措施 | 负责方 | 验收标准 |
|---|------|--------|---------|
| R1 | **统一 MAX_CONCURRENT_POSITIONS**：与团队确认目标值（2 或 5），同步更新代码常量和设计文档 §4.6；添加单元测试验证值 | 开发者 | 代码常量 = 设计文档值，测试通过 |
| R2 | **修复退出机制漂移**：在 `manage_positions` 中添加 Time Stop 检查（持仓 > 5h 触发市价平仓），为 OCO 补充存活检测；设计方案二选一并在文档中记录 | 开发者 | 持仓 >5h 后自动平仓；OCO 存活检测验证 |
| R3 | **清理未平仓**：逐一确认 15 笔未平仓的 OCO 状态，对缺乏 OCO 保护且持仓时间 >5h 的仓位执行手动平仓 | 运营者 | 未平仓减少到合理数量 |

### 6.2 短期措施（中优先级）

| # | 措施 | 负责方 |
|---|------|--------|
| R4 | **修正启动权益门槛**：将代码改为固定值 `>= 7.0`，或经团队讨论后更新设计文档为新的动态策略并明确该策略的止损行为 | 开发者 |
| R5 | **更新 posSide 设计文档**：在 §4.2/§4.3 中将 `posSide="net"` 改为 `posSide="long"/"short"`，匹配账户实际配置 | 开发者 |
| R6 | **补充 sltp_pending 到 state schema**：在设计文档 §7 的 state.json 示例中添加 `sltp_pending` 字段并说明用途 | 开发者 |
| R7 | **添加设计合规 CI 检查**：创建 `tests/test_live_design_compliance.py`，检查代码中的关键常量（`MAX_CONCURRENT_POSITIONS`、`NOTIONAL_MULTIPLE` 等）是否与设计文档一致 | 开发者 |

### 6.3 长期措施（低优先级）

| # | 措施 | 说明 |
|---|------|------|
| R8 | **引入设计文档版本化**：每次代码漂移后更新设计文档版本号（v1→v2），保留变更日志 | 提升文档可信度 |
| R9 | **引入策略 edge 覆盖监控**：跟踪 C/D/E/A/B/K/H 每条 edge 在实盘中的信号产生率和胜率 | 验证策略有效性的前提 |
| R10 | **实现 Ghost Position 检测**：在 startup 阶段对比本地 trade log 与 exchange 持仓，自动平仓那些本地记录了 entry 但 exchange 端已无对应持仓的异常仓位 | 防范未知状态 |

---

## 7. 附录

### A. trades.csv 原始数据摘要

| 序号 | 时间 (UTC) | Symbol | 操作 | 价格 | 张数 | PnL | 来源 |
|------|-----------|--------|------|------|------|-----|------|
| 1 | 06-26 03:26 | SOLUSDT | enter_long | 66.14 | 4.0 | 0 | ensemble_C |
| 2 | 06-26 03:40 | SOLUSDT | **exit_long** | 66.53 | 4.0 | **+3.4** | take_profit |
| 3 | 06-26 04:35 | SOLUSDT | enter_short | 68.24 | 5.0 | 0 | ensemble_C |
| 4 | 06-26 12:37 | DOGEUSDT | enter_long | 0.07386 | 0.28 | 0 | ensemble_C |
| 5 | 06-26 12:37 | OPUSDT | enter_long | 0.10322 | 207.0 | 0 | ensemble_C |
| 6 | 06-26 15:46 | DOGEUSDT | enter_short | 0.07501 | 0.31 | 0 | ensemble_C |
| 7 | 06-26 15:46 | ADAUSDT | enter_short | 0.1476 | 1.6 | 0 | ensemble_C |
| 8 | 06-26 16:01 | XRPUSDT | enter_short | 1.0501 | 0.17 | 0 | ensemble_C |
| 9 | 06-27 00:04 | DOGEUSDT | enter_short | 0.07573 | 0.2 | 0 | ensemble_C |
| 10 | 06-27 00:04 | ADAUSDT | enter_short | 0.1484 | 1.0 | 0 | ensemble_C |
| 11 | 06-27 00:08 | SOLUSDT | enter_long | 72.39 | 0.2 | 0 | ensemble_C |
| 12 | 06-27 00:08 | NEARUSDT | enter_short | 1.81 | 0.8 | 0 | ensemble_C |
| 13 | 06-27 00:08 | XRPUSDT | enter_short | 1.0509 | 0.13 | 0 | ensemble_C |
| 14 | 06-27 00:09 | LTCUSDT | enter_short | 41.9 | 0.3 | 0 | ensemble_C |
| 15 | 06-27 00:09 | LTCUSDT | enter_short | 41.9 | 0.3 | 0 | ensemble_C |
| 16 | 06-27 00:31 | LINKUSDT | enter_short | 7.331 | 2.4 | 0 | ensemble_C |

> 注：LTCUSDT 在 00:09 出现了两条完全相同的 enter_short 记录，可能是信号消歧逻辑重复入列或数据写入时的 bug（待确认）。

### B. state.json 原始数据

```json
{
  "session_start": "2026-06-27T00:08:01.565187+00:00",
  "cycle_count": 933,
  "total_trades": 15,
  "peak_equity": 9.5066,
  "halted": false,
  "halt_reason": null,
  "last_run": "2026-06-27T02:55:02.786646+00:00",
  "sltp_pending": false
}
```

### C. 代码常量对照表

| 常量 | 设计文档 | 代码 | 是否一致 |
|------|---------|------|---------|
| `NOTIONAL_MULTIPLE` | 10（§4.5） | 10（line 54） | ✅ |
| `MAX_CONCURRENT_POSITIONS` | 2（§4.6） | 5（line 61） | ❌ |
| `POSITION_SIZE_USD` | 无明确定义（§4.4 动态计算） | 7.0（line 58，未使用） | ⚠️ 悬空常量 |
| OCO 止盈 % | 无（设计用固定 upl +$0.42） | 3.4%（`OCO_TP_PCT` line 55） | ❌ |
| OCO 止损 % | 无（设计用固定 upl -$0.21） | 2.5%（`OCO_SL_PCT` line 56） | ❌ |
| Trailing SL % | 设计未提及 | 2.0%（`TRAILING_SL_PCT` line 57，代码中未引用） | ⚠️ 悬空常量 |
| 启动门槛 | `>= 7.0`（§6.2） | `max(equity*0.5, 1.0)`（line 430） | ❌ |

### D. 已确认一致的设计点

以下设计文档约定在代码中正确实施，未发现漂移：

| 设计点 | 状态 |
|--------|------|
| 市价单下单（`ordType="market"`） | ✅ |
| 全仓保证金（`tdMode="cross"`） | ✅ |
| 每合约设最大交易所杠杆（`setup_leverage`） | ✅ |
| 名义敞口解耦于杠杆（`NOTIONAL_MULTIPLE`） | ✅ |
| 价格感知仓位计算（`compute_sz`） | ✅ |
| trades.csv / state.json 持久化路径 | ✅ |
| RiskGuard 集成（`risk_guard.update_equity`） | ✅ |
| 代理配置复用 `src/okx_sdk.py` | ✅ |
| 轮询间隔 60s | ✅ |
| `--once` / 持续循环双模式 | ✅ |

---

*本报告基于 2026-06-27 02:55 UTC 的数据快照编写，后续代码或数据变更可能导致部分结论失效。*

---

## 相关文档

- [漂移分析需求](../requirements/2026-06-27-live-echo-drift-requirements.md) — 定义本报告的触发条件、流程与验收标准
- [执行计划：V3.1 暴击流组合](../plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md) — 漂移分析所对照的策略执行计划
- [Edge 信号设计](../design/2026-06-27-strategy-v3-edge-design.md) — 被对照的 edge 设计基线
- [共享执行架构](../architecture/2026-06-27-strategy-v3-execution-architecture.md) — 被对照的运行时架构基线
