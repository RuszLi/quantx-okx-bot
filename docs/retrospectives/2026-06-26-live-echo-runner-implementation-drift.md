# Live Echo Runner 实现偏差复盘

> **日期：** 2026-06-26
> **关联计划：** [docs/plans/2026-06-26-live-echo-implementation.md](../plans/2026-06-26-live-echo-implementation.md)
> **关联脚本：** `scripts/run_live_echo.py`
> **关联管道：** `src/paper/pipeline.py`
> **现象：** Live Echo Runner 在实盘运行中表现为「每分钟都有订单信号产生」，与计划预期的信号频率严重不符；账户权益从 $7 跌至 $5.83 仍未停机。

> **2026-06-26 勘误：** 偏差 1 / 偏差 2 的根因推断已于本日实测 `account_api().get_account_config()` 后更正。账户实际持仓模式为 `long_short_mode`（双向持仓），并非本文原推断的「计划用 `net` 模式、实际被改成 `long/short`」。同时实盘最新日志显示当前主路阻塞已从平仓 51169 迁移为开仓侧 `attachAlgoOrds` 触发 `sCode 51053`（SL 方向校验失败）。完整更正与新缺陷记录见：
> - [docs/discussions/2026-06-26-live-echo-runner-drift-fix.md](../discussions/2026-06-26-live-echo-runner-drift-fix.md)
> - [docs/bugs/2026-06-26-live-echo-runner-order-semantics.md](../bugs/2026-06-26-live-echo-runner-order-semantics.md)
>
> 下文保留原始复盘内容，**偏差 1 / 偏差 2 的根因与后果描述以更正文档为准**。

---

## 一、复盘动机

按 `AGENTS.md` 规则 9，当最终实现与原型出现重大偏差时，必须把偏差原因记录到 `docs/retrospectives/`，不能直接忽略差异继续推进。本次 Live Echo Runner 在实盘运行中暴露出三类异常现象，经对照计划文档与实际代码后确认存在多处重大偏差，特此复盘。

## 二、现象描述

实盘运行日志（`data/live_echo/runner.log`，2026-06-26 13:20–13:21 片段）显示：

1. **每轮循环都在尝试下单**：约每 60 秒一轮，每轮都触发 `check_exits` → 下平仓单 → 失败 → 下一轮再次触发，形成「每分钟订单信号」的假象。
2. **平仓单持续失败**：OKX 返回 `sCode 51169`，错误信息为 `Order failed because you don't have any positions in this direction for this contract to reduce or close`。
3. **algo 订单 400**：每轮仍在调用 `place_algo_order` 挂 SL/TP（Stop Loss / Take Profit，止损止盈），返回 `HTTP 400 Bad Request`。
4. **账户权益持续下降但未停机**：从 $7 跌至 $5.98、$5.83、$6.23，runner 持续运行，无任何 halt（停机）机制介入。

## 三、偏差清单

对照计划 `docs/plans/2026-06-26-live-echo-implementation.md` 与实际代码 `scripts/run_live_echo.py`，确认以下偏差：

### 偏差 1（致命）：平仓单缺失 reduceOnly 语义

> **2026-06-26 勘误：** 本节原推断「账户为 `net` 模式、代码被改成 `long/short` 模式」与实测账户配置不符。账户实际 `posMode="long_short_mode"`（双向持仓），代码传 `posSide="long"`/`"short"` 的方向符合账户语义。真正根因是：双向持仓模式下，`check_exits` 平仓调用与 `attachAlgoOrds` 均未附带 `reduceOnly=True`，OKX 视为新开反向仓而拒绝。详见 [docs/bugs/2026-06-26-live-echo-runner-order-semantics.md](../bugs/2026-06-26-live-echo-runner-order-semantics.md)。

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| `place_market_order` 签名 | `place_market_order(inst_id, side, sz)`，固定 `posSide="net"` | `place_market_order(inst_id, side, sz, pos_side, ...)`，`pos_side` 由调用方传入 `"long"` / `"short"` |
| `check_exits` 平仓调用 | 直接 `place_market_order(inst_id, side, sz)` | `place_market_order(inst_id, side, sz, pos_side=pos_side)`，未传 `reduceOnly=True` |

**后果（更正）：** 双向持仓模式下，平仓单未携带 `reduceOnly` 让 OKX 误判为新开反向仓，返回 `sCode 51169`（无对应方向持仓可平）。平仓永远失败 → 持仓一直挂着 → 每轮 `check_exits` 都重新触发 stop_loss 又都下失败单。这是「每分钟订单信号」的直接根因。

### 偏差 2（致命）：attach_sltp_to_existing 仍每轮调用

> **2026-06-26 勘误：** 本日代码 + 最新实盘日志核验显示，`run_once` 与 `startup_check` 实际均未调用 `attach_sltp_to_existing`，最新日志中也不见 `place_algo_order` 痕迹。原描述「日志显示每轮仍在调 `place_algo_order`」可能对应早期版本代码状态，当前版本已不每轮调用。但 `attach_sltp_to_existing` 函数定义仍残留为死代码，且其 SL/TP 价格反推逻辑未与新发现的 51053 缺陷对齐，建议直接删除。详见 [docs/bugs/2026-06-26-live-echo-runner-order-semantics.md](../bugs/2026-06-26-live-echo-runner-order-semantics.md)。

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| SL/TP 挂载方式 | 开仓时随 `attachAlgoOrds` 一起挂，无独立函数 | 新增 `attach_sltp_to_existing` 函数，`run_once` 注释写「不再每轮调用」；当前版本确已不每轮调用，但函数定义仍残留为死代码 |

**后果（更正）：** 死代码残留 + 死代码内部 SL/TP 反推逻辑未对齐 51053 修复方向，属潜在陷阱；原描述的「每轮 400 噪声」已不出现。

### 偏差 3（严重）：execute_entries 开仓逻辑被改写

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| 已持仓处理 | per-symbol 跳过（`if inst_id in open_positions: continue`），一轮可开多笔 | `if open_positions: return []`，有任何持仓就全部跳过 |
| 单轮开仓数量 | 可开多笔 | `break` / `return` 只开一笔就停 |
| 信号有效期 | 无 | 新增 `valid_until_ts` 过期检查 |

**后果：** 开仓被过度抑制（只要有一笔持仓就不再开任何新单），但行为与计划完全不同，回测/纸交易与实盘的开仓语义不一致，无法用纸交易结果验证实盘表现。

### 偏差 4（严重）：RiskGuard 风控闸门完全移除

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| `compute_ensemble_signants` 末尾 | `if risk_guard.is_halted: return pd.DataFrame()` | 删除 |
| `run_once` 开头 | `if risk_guard.is_halted: return` | 删除 |
| `check_exits` 平仓后 | `risk_guard.update_equity(equity, trade_pnl_r=upl)` | 删除 |
| `run_loop` 风控触发 | `break` 停机 | 删除 |
| import | `from src.live.risk_guard import RiskGuard` | 完全没有 |

**后果：** 账户从 $7 跌至 $5.83 仍继续运行，无任何 halt 机制。这是最危险的偏差——风控闸门整体消失，实盘账户在没有保护的状态下运行。

### 偏差 5（严重）：startup_check 移除 equity ≥ $7 校验

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| 权益下限校验 | `if equity < 7.0: sys.exit(1)` | 删除 |

**后果：** $5.98 权益也能启动 runner，与计划的 $7 最低权益门槛不符。配合偏差 4，账户可在低权益状态下无保护运行。

### 偏差 6（轻微）：run_loop 默认间隔漂移

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| `run_loop` 默认 `interval_seconds` | 60 | 5 |

**后果：** `main` 仍传 `default=60`，实际运行表现正常，但函数默认值已漂移，直接调用 `run_loop()` 会变成 5 秒轮询。

### 偏差 7（轻微）：get_instrument_map 数据源变更

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| API | `account_api().get_instruments` | `public_api().get_instruments` |
| 字段 | `ctVal`、`lotSz`、`ctMult` | `ctVal`、`lotSz`、`lever`（`ctMult` 丢失） |

**后果：** 字段集合变化，下游 `compute_sz` 依赖的字段需同步调整。

### 偏差 8（轻微）：compute_sz 签名与公式变更

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| 签名 | `compute_sz(inst_info, equity)` | `compute_sz(info, equity, price)` |
| 公式 | `equity * MAX_LEVERAGE / ct_val` | 依赖 `price` |

**后果：** 开仓张数计算逻辑与计划不一致。

### 偏差 9（轻微）：函数名拼写修正

| 维度 | 计划 | 实际 |
|:---|:---|:---|
| 函数名 | `compute_ensemble_signants`（拼写错误） | `compute_ensemble_signals` |

**后果：** 计划文档中的拼写错误被修正，属于正向偏差，但意味着计划文档与实际代码的函数名不一致。

## 四、根因链

```
偏差 1（平仓单 reduceOnly 缺失）
    ↓
SOL 持仓平不掉
    ↓
每轮 check_exits 重复下失败单  ← 「每分钟订单信号」的直接来源
    +
偏差 2（attach SL/TP 每轮重试 400）
    ↓
无效请求噪声淹没日志
    ↓
偏差 4（RiskGuard 移除）+ 偏差 5（equity 校验移除）
    ↓
账户在无保护状态下持续运行
    ↓
偏差 3（execute_entries 改写）
    ↓
开仓被过度抑制，掩盖了「风控缺失」本应暴露的开仓侧风险
```

## 五、教训

1. **平仓单方向语义必须显式验证**：OKX 在不同持仓模式（净持仓 `net` vs 双向 `long/short`）下对 `posSide` 和 `reduceOnly` 的要求不同。计划用 `net` 模式，实际改成 `long/short` 却没同步处理 `reduceOnly`，导致平仓永远失败。这类交易所 API 的模式耦合必须在实现时显式验证，不能靠注释「以为」对了。

2. **注释不能替代代码**：`run_once` 里写「不再每轮调用」，但函数仍在被调用。注释与代码行为不一致是最难发现的漂移——读代码的人会信注释，看日志的人会信行为，两边对不上时问题已经发生。自解释代码优于注释承诺。

3. **风控闸门是不可降级的需求**：RiskGuard 在计划里出现 4 处，实际代码 0 处。这是最危险的偏差类型——风控一旦缺失，其他所有偏差的后果都会被放大且无法兜底。风控相关的实现偏差应作为最高优先级阻断项，不允许「先注释掉 later 再说」。

4. **实盘与纸交易/回测的语义一致性必须显式守护**：偏差 3 让实盘的开仓逻辑（有一笔持仓就全部跳过）与纸交易（per-symbol 跳过）完全不同。这意味着纸交易的任何验证结果都无法外推到实盘。共享 `pipeline.py` 只解决了信号计算的一致性，执行层的一致性仍需保障。

5. **计划文档拼写错误会被「悄悄修正」**：偏差 9 是正向修正，但说明计划文档与代码之间没有强约束关系。拼写可以修，但逻辑偏差也容易被同样的「悄悄改对」心态掩盖——区别在于拼写修了无害，逻辑改错了无风控兜底。

## 六、待跟进事项

- [x] 按 `AGENTS.md` 规则 8，将偏差 1（实测更正后为「双向持仓模式下平仓单缺失 reduceOnly 语义」）+ 新发现的开仓侧 `sCode 51053` 录入 [docs/bugs/2026-06-26-live-echo-runner-order-semantics.md](../bugs/2026-06-26-live-echo-runner-order-semantics.md)。
- [x] 待澄清问题已固化到 [docs/discussions/2026-06-26-live-echo-runner-drift-fix.md](../discussions/2026-06-26-live-echo-runner-drift-fix.md)，含 5 项待决策项（D1–D5）。
- [x] 按 `AGENTS.md` 规则 15，评估是否需要把「实盘与计划的一致性校验」「OKX 双向持仓模式下单语义校验」沉淀为可复用的审计清单（`docs/audit/`），避免同类偏差在后续策略上线时再次发生。结论：本次修复已把核心语义约束写入 `docs/architecture/okx-sdk-rules.md` §4；待同类问题再次出现时，再升级为 `docs/audit/` 下独立审计手册。
- [x] 修复方案已制定并执行：[docs/plans/2026-06-26-live-echo-runner-fix.md](../plans/2026-06-26-live-echo-runner-fix.md)。

## 七、修复状态（2026-06-26）

按 [docs/plans/2026-06-26-live-echo-runner-fix.md](../plans/2026-06-26-live-echo-runner-fix.md) 执行后，偏差状态更新如下：

| 偏差 | 修复状态 | 说明 |
|:---|:---|:---|
| 1（平仓单 reduceOnly 语义） | ✅ 已修复 | `place_market_close` 强制 `reduceOnly=True`；SL/TP 通过 `place_algo_order` 也强制 `reduceOnly=True`。 |
| 2（`attach_sltp_to_existing` 死代码） | ✅ 已删除 | 函数定义已移除。 |
| 3（`execute_entries` 改写） | ✅ 已还原 | per-symbol 跳过、一轮可开多笔、无 `valid_until_ts` 过期检查。 |
| 4（RiskGuard 移除） | ✅ 已恢复 | `pipeline.py`、`run_live_echo.py`、`run_paper_ensemble.py` 均已接入。 |
| 5（`startup_check` equity 校验移除） | ✅ 已恢复 | 门槛改为 `max(equity * 0.5, $1.0)`，不再写死 $7。 |
| 6（`run_loop` 默认间隔 5s） | ✅ 已还原 | 函数默认值与 `--interval` 默认均改为 60。 |
| 7（`get_instrument_map` 数据源） | ✅ 已还原 | 改回 `account_api().get_instruments`，补回 `ctMult`。 |
| 8（`compute_sz` 签名与公式） | ✅ 已还原 | 签名 `compute_sz(inst_info, equity)`，公式 `equity * MAX_LEVERAGE / ct_val`。 |
| 9（函数名拼写） | ✅ 已同步 | 计划文档 `2026-06-26-live-echo-implementation.md` 已标注 superseded 并修正函数名。 |
| 10（check_exits 写死 USDT 金额） | ✅ 已修复 | 删除 `check_exits` 函数及 `STOP_LOSS_USDT`/`TAKE_PROFIT_USDT`/`TIME_STOP_HOURS` 常量，完全依赖交易所 algo 单 + RiskGuard 熔断。 |

### Paper 与 Live 下单侧残留差异

`scripts/run_paper_ensemble.py` 作为纸交易/信号记录器，本身不执行下单，因此不存在 `place_market_entry` / `place_market_close` / `place_algo_order` 等函数，与实盘代码的差异是**职责差异**而非**语义漂移**。两者已实现的风控对齐：

- 均通过 `src.live.risk_guard.RiskGuard` 接入同一套 halt 闸门。
- `pipeline.compute_ensemble_signals` 在纸交易与实盘中均支持 `risk_guard` 参数，halt 时返回空 DataFrame。

实盘独有的下单层语义已按 `docs/architecture/okx-sdk-rules.md` §4 约束实现，未来若纸交易扩展为「模拟成交」，应直接复用 `run_live_echo.py` 中的 `place_market_entry` / `place_market_close` / `attach_sltp_via_algo_order` 骨架。

### 偏差 10（严重）：check_exits 使用写死 USDT 金额而非方案设计的 ATR/价格止损

**发现日期：** 2026-06-26（代码审查）

| 维度 | 方案（§2.3/§7） | 实际 |
|:---|:---|:---|
| 止损 | 基于 ATR/价格结构（如 `1.5×ATR(4h)`、`破前高×1.02`） | 固定 `-1 USDT` |
| 止盈 | 基于信号的 `target_price` | 固定 `+3 USDT` |
| 时间止损 | 因策略而异（15min ~ 24h） | 固定 `8h` |
| R 单位 | `equity × R_pct`（A=30%, B/C=20%, D=15%, E/H=18%） | 无 R 概念 |

**根因：** `check_exits` 是早期开发阶段的简化实现，后续修复计划专注于下单语义缺陷（Bug-1/Bug-2），未覆盖退出参数对齐。

**后果：**
1. 退出逻辑与开仓逻辑矛盾：开仓用信号的 `stop_price`/`target_price`（ATR/价格），`check_exits` 用固定金额
2. 不同合约效果差异巨大：-1 USDT 对 BTC（~$600）和 DOGE（~$1.5）意义完全不同
3. 与方案设计严重不符

**修复方向：** 删除 `check_exits` 及其常量，完全依赖交易所 algo 单 + RiskGuard 熔断。

**缺陷记录：** [docs/bugs/2026-06-26-check-exits-hardcoded-sltp.md](../bugs/2026-06-26-check-exits-hardcoded-sltp.md)
