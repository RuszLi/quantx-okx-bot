# Live Echo Runner 偏差澄清与修复决策 — 2026-06-26

> 来源：`docs/input/2026-06-26-pm-source.md`
> 关联复盘：`docs/retrospectives/2026-06-26-live-echo-runner-implementation-drift.md`
> 关联计划：`docs/plans/2026-06-26-live-echo-implementation.md`
> 状态：已决策并执行

本文档固化 `docs/input/2026-06-26-pm-source.md` 中四项待澄清问题的事实结论与修复方向，作为后续制定修复方案的输入。**本文档不触发代码修改**，修复方案另行制定（见 AGENTS.md 规则 5）。

---

## 一、已澄清事实

### 1.1 偏差 1（致命）：账户持仓模式实际为双向，复盘根因推断需更正

**验证手段：** 调用 OKX `account_api().get_account_config()` 实测主网账户配置。

**实测结果：**

| 字段 | 值 | 含义 |
|:---|:---|:---|
| `posMode` | `long_short_mode` | 双向持仓模式（可同时持 long/short 仓） |
| `acctStpMode` | `cancel_maker` | 自成交防范策略 |
| `ctIsoMode` | `automatic` | 自动逐仓 |

**结论：**

- 复盘文档 §三 / 偏差 1 中「计划用 `net` 模式，实际改成 `long/short`」的前提**与账户实际配置不符**。账户本身就是 `long_short_mode`，因此代码里 `posSide="long"` / `"short"` 的传入方向**符合账户语义**，不是「模式被悄悄改掉」。
- 但复盘指出的**后果属实**：`check_exits` 平仓时调用 `place_market_order(..., pos_side=pos_side)` **未传 `reduceOnly=True`**（见 `scripts/run_live_echo.py:217`）。在双向持仓模式下，`reduceOnly` 是显式声明「只减仓不开新仓」的必要语义，缺失会导致 OKX 把平仓单当成新开反向仓处理，从而报 `sCode 51169`（无对应方向持仓可平）。
- 实盘日志（`data/live_echo/runner.log` 2026-06-26 14:42–14:44）已证实：账户权益 $3.82、持仓 0，每轮仍尝试挂 algo 单并失败 `sCode 51053`，未看到 51169 的平仓失败日志（因为持仓已为 0，平仓侧不触发；问题集中在开仓侧）。

**真正根因更正：**

> 偏差 1 不是「持仓模式被改」，而是「双向持仓模式下平仓单 / 止损止盈单未按 OKX 规则随单附带 `reduceOnly` 语义」，叠加策略信号 `stop_price` / `target_price` 与市价成交价之间的方向校验缺失（见 §1.2）。

### 1.2 偏差 1 关联新缺陷：开仓侧 attachAlgoOrds 触发 `sCode 51053`

实盘最新日志显示当前主路阻塞已从「平仓失败 51169」迁移为「开仓失败 51053」：

```
sCode 51053: Your SL price should be higher than the primary order price.
```

**触发场景：** `execute_entries` 调 `place_market_order` 开空（`side="sell"`），随单附带 `attachAlgoOrds`（SL/TP，止损止盈）。

**策略信号侧（已核验为正确）：** `beta_decouple.py:60-61` 与 `weekend_wick.py:45-46` 中，做空（`direction=-1`）时 `stop_price = entry + distance`（高于入场）、`target_price = entry - distance`（低于入场），符合「做空止损在上方、止盈在下方」的常识。

**缺陷定位：** `run_live_echo.py:165-175` 的 `attachAlgoOrds` 构造直接把策略信号 `stop_price` / `target_price` 原值透传给 OKX 的 `slTriggerPx` / `tpTriggerPx`，但：

1. 主单是市价单（`ordType="market"`），实际成交价与信号 `entry_price` 之间存在滑点。当成交价低于信号 `entry_price` 时，基于 `entry_price + distance` 计算的 `slTriggerPx` 可能**低于实际成交价**，触发 51053。
2. OKX 对 `attachAlgoOrds` 的 SL/TP 方向约束：**主单方向 × SL/TP 触发方向必须一致**。代码未根据 `side` / `posSide` 显式校验 `slTriggerPx` 与成交价方向关系，依赖策略信号原值易在市价滑点下翻车。

**这是开仓侧新缺陷，原复盘文档未覆盖，需在 `docs/bugs/` 单独录入。**

### 1.3 偏差 2（致命）：`attach_sltp_to_existing` 实际未被每轮调用

**代码核验：**

- `run_once`（`run_live_echo.py:336`）注释明确写「不再每轮都尝试挂载 SL/TP」，函数体内**确未调用** `attach_sltp_to_existing`。
- `startup_check`（`run_live_echo.py:331`）注释写「不再调用 `attach_sltp_to_existing`」，函数体内也**未调用**。
- 最新实盘日志（14:42–14:44）中**未出现** `place_algo_order` 调用痕迹，只看到 `place_order`（带 `attachAlgoOrds`）的 51053 失败。

**结论：**

- 复盘文档 §三 / 偏差 2 中「日志显示每轮仍在调 `place_algo_order`」的描述，与当前代码 + 最新日志**不一致**。该描述可能对应早期版本代码状态，当前版本已修复至「不每轮调用」。
- 剩余问题：`attach_sltp_to_existing` 函数定义仍残留在文件中（`run_live_echo.py:277-310`），且自身仍用 `STOP_LOSS_USDT / (sz * ct_val)` 反推价格，逻辑未与 §1.2 的 SL/TP 方向问题对齐，属于**死代码 + 潜在陷阱**，应删除。

### 1.4 偏差 3（严重）：`execute_entries` 开仓逻辑被改写，且 $3 账户规模下开仓逻辑需重定

**代码核验（`run_live_echo.py:230-274`）：**

| 计划行为 | 实际行为 | 偏离 |
|:---|:---|:---|
| per-symbol 已持仓跳过 | 任一持仓即 `return []` 全跳过 | ✅ 偏离 |
| 一轮可开多笔 | `return` / `break` 只开一笔 | ✅ 偏离 |
| 无有效期检查 | 新增 `valid_until_ts` 过期检查 | ✅ 偏离 |

**$3 账户规模开仓逻辑决策（待评审）：**

账户实测权益 $3.82，距离原计划门槛 $7、复盘文档中 $50 退场目标均更远。`docs/discussions/2026-06-25-okx-algo.md` §5 已经明确指出「$7 → $50（700% / 7 天）隐含 daily edge ≈ 33%，地球上没有任何稳定策略能复利出这个数」，并定义了退场条件：

> 如果 3 条 zero-cost 策略全部 Phase 0 FAIL，就承认「$7 量化」这件事在 2026 年的市场结构下不成立。

当前账户已从 $7 亏损至 $3，正好踩在该退场条件边界。需要先决策「是否继续 $3 实盘」再做开仓逻辑修复：

- **选项 A（暂停实盘）：** 停 runner，把剩余 $3 视作已耗损娱乐预算，后续只在 Paper / 回测层验证策略 EV，不再投实盘经费。符合 okx-algo §5「彩蛋目标」与「退场条件」。
- **选项 B（继续实盘）：** 接受 $3 账户，把开仓逻辑改为「单仓制 + 保守仓位」，并先把 §1.2 的 51053 与偏差 1 的 reduceOnly 修通，再观察 paper→live 一致性。

**推荐：选项 A**。理由：① 偏差 4（风控完全移除）未修前，$3 实盘等同于无保护裸奔；② 偏差 3 + §1.2 联动下，paper 与 live 开仓语义已不一致，paper 的任何验证都无法外推到 live；③ $3 距 $50 退场目标过远，继续实盘是给 OKX 交学费。

### 1.5 偏差 4（严重）：RiskGuard 风控闸门完全移除，恢复优先级最高

**代码核验：** `run_live_echo.py` 全文未导入 `RiskGuard`，`src/paper/pipeline.py` 的 `compute_ensemble_signals` 也已删除 `risk_guard.is_halted` 检查（对比计划版本 `compute_ensemble_signants` 末尾有 `if risk_guard.is_halted: return pd.DataFrame()`）。

**恢复优先级：** 最高。在风控缺失状态下，账户从 $7 跌至 $3 仍持续运行，已构成无保护裸奔。任何其他修复都应排在 RiskGuard 恢复之后。

**恢复范围（按计划版本回填）：**

| 位置 | 计划版本 | 当前缺失 |
|:---|:---|:---|
| `pipeline.compute_ensemble_signals` 末尾 | `if risk_guard.is_halted: return pd.DataFrame()` | 删除 |
| `run_once` 开头 | `if risk_guard.is_halted: return` | 删除 |
| `check_exits` 平仓后 | `risk_guard.update_equity(equity, trade_pnl_r=upl)` | 删除 |
| `run_loop` 风控触发 | `if risk_guard.is_halted: break` | 删除 |
| 顶层 import | `from src.live.risk_guard import RiskGuard` | 删除 |
| `startup_check` | `if equity < 7.0: sys.exit(1)`（偏差 5） | 删除 |

注意 `RiskGuard` 默认 `daily_max_drawdown_pct=0.15`，$3 账户下 15% 回撤阈值约 $0.45，距 anchor $7 的回撤阈值约 $1.05。$3 已远超 $7 anchor 的 15% 回撤线（$5.95），若按 $7 为 anchor 会立即 halt；恢复时需重新决策 anchor 取值（重启时刻权益 vs 历史峰值）。

### 1.6 剩余偏差（5/6/7/8/9）状态

按复盘文档 §三 偏差 5–9 罗列，均为次要或正向偏差，随主修复批次一并处理即可，无需单独澄清：

| 偏差 | 状态 | 处理方式 |
|:---|:---|:---|
| 5（`startup_check` 删除 equity ≥ $7 校验） | 待修 | 随偏差 4 一并恢复；阈值需结合 §1.4 决策重定 |
| 6（`run_loop` 默认间隔 60 → 5） | 待修 | 还原默认 60 |
| 7（`get_instrument_map` 改 public_api） | 待修 | 还原 `account_api`，并补回 `ctMult` 字段 |
| 8（`compute_sz` 签名 + 公式变更） | 待修 | 还原 `compute_sz(inst_info, equity)`，公式 `equity * MAX_LEVERAGE / ct_val`；当前依赖 `price` 的版本与计划不一致 |
| 9（函数名 `compute_ensemble_signants` → `compute_ensemble_signals`） | 正向偏差 | 计划文档需同步更正拼写，代码不动 |

---

## 二、待决策清单（评审通过后进入修复方案）

- [x] **决策 D1：** 已定。采纳选项 A（暂停 $3 实盘），转回 Paper / 回测层验证，符合 `docs/discussions/2026-06-25-okx-algo.md` §5 退场条件。
- [x] **决策 D2：** 已定。`startup_check` 权益门槛改为 `max(equity * 0.5, $1.0)`（$3 账户下门槛 $1.5，留 50% 缓冲给手续费/滑点）；`RiskGuard.anchor_equity` 取重启时刻权益（不再回溯历史 $7）。
- [x] **决策 D3：** 已定。`place_market_order` 拆为 `place_market_entry`（无 `reduceOnly`）与 `place_market_close`（强制 `reduceOnly=True`）两函数。
- [x] **决策 D4：** 已定。采纳方案 B（主单保留市价单，下单后 `get_fills` 拿成交价，独立 `place_algo_order` 挂 SL/TP），残余风险为数百毫秒无保护窗口，缓解措施：`sltp_pending` 标志位 + state 持久化 + 最大损失估算（$3 账户下 < $0.50）。
- [x] **决策 D5：** 已定。`attach_sltp_to_existing` 死代码直接删除。

---

## 三、后续动作（不在本讨论文档范围内）

1. 本文档评审通过后，按 AGENTS.md 规则 5 触发执行方案编写：`docs/plans/2026-06-26-live-echo-runner-fix.md`。
2. 按 AGENTS.md 规则 8，偏差 1（实际根因）+ §1.2 新缺陷录入 `docs/bugs/`。
3. 复盘文档 §三 / 偏差 1 / 偏差 2 的根因描述需按本文更正（见 §1.1 / §1.3）。
4. 修复完成后再决定是否按选项 B 重启实盘。