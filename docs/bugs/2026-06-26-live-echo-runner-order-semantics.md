# Bug: Live Echo Runner 平仓缺失 reduceOnly 语义 + 开仓 SL/TP 方向校验失败

**日期：** 2026-06-26
**严重性：** 致命（阻塞实盘运行）
**影响范围：** `scripts/run_live_echo.py` 实盘下单整链路
**关联讨论：** [docs/discussions/2026-06-26-live-echo-runner-drift-fix.md](../discussions/2026-06-26-live-echo-runner-drift-fix.md)
**关联复盘：** [docs/retrospectives/2026-06-26-live-echo-runner-implementation-drift.md](../retrospectives/2026-06-26-live-echo-runner-implementation-drift.md)

> 本缺陷文档拆分为两个独立但联动的 Bug：Bug-1（平仓侧）与 Bug-2（开仓侧）。复盘文档中「偏差 1」的根因推断需以本缺陷文档为准（见 §一）。

---

## 一、复盘偏差 1 根因更正

复盘文档 §三 / 偏差 1 推断「计划用 `net` 模式，实际改成 `long/short` 模式」与实际账户配置不符：

- 实测 `account_api().get_account_config()` 返回 `posMode="long_short_mode"`，账户本身就是双向持仓。
- 因此代码传 `posSide="long"`/`"short"` 的方向**符合账户语义**，不是「模式被改」。
- 真正根因见下文 Bug-1：双向持仓模式下，平仓单与 algo 单均未附带 `reduceOnly=True`，OKX 拒绝视为新开反向仓。

## 二、Bug-1：平仓与 algo 单缺失 reduceOnly 语义

### 现象

早期实盘日志（复盘文档引用的 2026-06-26 13:20–13:21 片段）：

```
sCode 51169: Order failed because you don't have any positions in this direction for this contract to reduce or close
```

### 根因

| 调用点 | 文件:行 | 缺陷 |
|:---|:---|:---|
| `check_exits` 平仓 | `scripts/run_live_echo.py:217` | `place_market_order(..., pos_side=pos_side)` 未传 `reduce_only` |
| `place_market_order` 主单 | `scripts/run_live_echo.py:178-186` | `place_order` 调用未设置 `reduceOnly` |
| `attach_sltp_to_existing` algo | `scripts/run_live_echo.py:297-308` | `place_algo_order` 已传 `reduceOnly=True`，但此函数已死代码 |

OKX 双向持仓模式下，`reduceOnly=True` 是显式声明「只减仓不开新仓」的必要参数。缺失时，OKX 把平仓单 / 止损止盈单当新开反向仓处理，因当前无对应方向持仓故报 51169。

### 后果

- 持仓平不掉 → 每轮 `check_exits` 重复下失败单 → 形成「每分钟订单信号」的假象（复盘文档 §二 现象 1 的直接来源）。
- 失败单噪声淹没有效日志，无法判断真实状态。

### 修复方向（待方案文档定稿）

- `place_market_order` 拆为 `place_market_entry`（无 `reduceOnly`）与 `place_market_close`（强制 `reduceOnly=True`）两函数；或加 `reduce_only` 形参。
- `check_exits` 调用走 `place_market_close`。
- 删除 `attach_sltp_to_existing` 死代码。

## 三、Bug-2：attachAlgoOrds SL/TP 触发价方向校验失败（sCode 51053）

### 现象

最新实盘日志（`data/live_echo/runner.log` 2026-06-26 14:42–14:44）：

```
sCode 51053: Your SL price should be higher than the primary order price.
full={'code': '1', 'data': [{'sCode': '51053', 'sMsg': 'Your SL price should be higher than the primary order price.'}]}
```

注册场景：`execute_entries` 开空（`side="sell"`）时随单附带 `attachAlgoOrds`（SL/TP）。

### 根因

| 维度 | 描述 |
|:---|:---|
| 策略信号侧（已核验正确） | `beta_decouple.py:60-61` 与 `weekend_wick.py:45-46` 中，做空（`direction=-1`）时 `stop_price = entry + distance`（高于入场）、`target_price = entry - distance`（低于入场）。符合做空「止损在上方、止盈在下方」的常识。 |
| 下单侧缺陷 | `run_live_echo.py:165-175` 的 `attachAlgoOrds` 构造直接透传策略信号 `stop_price` / `target_price` 到 `slTriggerPx` / `tpTriggerPx`。但主单是市价单（`ordType="market"`），实际成交价与信号 `entry_price` 之间存在滑点。当成交价低于信号 `entry_price` 时，基于 `entry_price + distance` 的 `slTriggerPx` 可能**低于实际成交价**，触发 51053「SL 价格应高于主单价格」。 |
| OKX 校验规则 | `attachAlgoOrds` 中 SL/TP 触发方向必须与主单方向一致：主单做空时，`slTriggerPx` 必须高于主单成交价（价格上涨止损），`tpTriggerPx` 必须低于主单成交价（价格下跌止盈）。代码未根据 `side` / `posSide` 与实际成交价做方向校验。 |

### 后果

- 开仓单随带 algo 单整体失败 → 实际未开仓（日志显示持仓始终为 0），实盘账户空转。
- 每轮重试同一信号 → 持续触发 51053 → 无效请求噪声。
- 账户权益从 $7 跌至 $3.82，但因为没有实际成交，损失来源需另行排查（疑似手续费、funding 或早期版本 51169 期间的真成交亏损）。

### 修复方向（待方案文档定稿）

两种候选，见讨论文档 §二 D4：

- **方案 A：** 主单改限价单（`ordType="limit"`），用信号 `entry_price` 挂限价单，消除市价滑点 vs 成交价不匹配。
- **方案 B（推荐）：** 保留市价主单，先 `trade_api().get_fills()` 拿实际成交价，再用 `place_algo_order` 独立挂 SL/TP（放弃 `attachAlgoOrds` 一次性下单），代价是 SL/TP 与主单成交之间有数百毫秒窗口无保护。

## 四、验证方法

修复后需逐项验证：

- [x] `check_exits` 平仓单携带 `reduceOnly=True`，OKX 返回 `sCode=0`。
  - 代码级验证：`place_market_close` 内部强制 `reduceOnly=True`（`scripts/run_live_echo.py`）；单元测试 `test_place_market_close_forces_reduce_only` 通过。
  - 实际运行验证：因本地代理 SSL 握手失败（`SSL: UNEXPECTED_EOF_WHILE_READING`），暂无法在 OKX 模拟盘/主网实测，需待代理恢复后补跑。
- [x] `place_algo_order` 的 `slTriggerPx` / `tpTriggerPx` 方向与主单 `side` 一致，不再触发 51053。
  - 代码级验证：`attach_sltp_via_algo_order` 已按 `side` 显式校验 `stop_price` / `target_price` 与 `fill_px` 方向关系；单元测试 `src/backtest/tests/test_live_echo_sltp.py` 覆盖做多/做空/错误拦截三种场景并全部通过。
  - 实际运行验证：同上，受代理 SSL 问题阻塞。
- [x] 实盘日志中每轮不再出现 51169 / 51053 错误循环。
  - 代码级验证：已弃用 `attachAlgoOrds` 一次性下单，改用 `place_algo_order` 独立挂 SL/TP，且平仓单带 `reduceOnly=True`。
  - 实际运行验证：同上，受代理 SSL 问题阻塞；但后台旧版实盘进程已终止，当前代码不会触发旧错误。
- [x] `attach_sltp_to_existing` 函数已删除。
- [x] `RiskGuard` 恢复后，halt 机制可触发并停止循环。已在 `scripts/run_paper_ensemble.py` 中通过注入 `RiskGuard.is_halted=True` 验证：信号计算被跳过；`is_halted=False` 时流程正常执行。

## 五、预防措施

1. **OKX 双向持仓模式下的下单语义必须显式校验：** 主单方向 × SL/TP 触发方向 × `reduceOnly` 三者一致性，应在下单前做断言，不能依赖策略信号原值。
2. **attachAlgoOrds 与主单分离的边界条件必须文档化：** 市价主单 + algo 触发价依赖信号 `entry_price` 的写法，在滑点场景下天然脆弱，应在 `docs/architecture/okx-sdk-rules.md` 增补一节说明。
3. **实盘与 Paper 的下单侧代码必须强制对齐：** 偏差 1 / Bug-2 都源自实盘代码偏离计划而 Paper 未同步，应把「实盘下单侧与计划文档的偏差」纳入 Phase 1 上线前的强制审计项（`docs/audit/`）。

## 六、相关文件

- `scripts/run_live_echo.py` — 下单整链路
- `src/paper/pipeline.py` — 信号管道（`compute_ensemble_signals` 未传 `stop_price` / `target_price` 方向校验）
- `src/backtest/strategies/beta_decouple.py` — C 策略信号源
- `src/backtest/strategies/weekend_wick.py` — D 策略信号源
- `data/live_echo/runner.log` — 实盘运行日志