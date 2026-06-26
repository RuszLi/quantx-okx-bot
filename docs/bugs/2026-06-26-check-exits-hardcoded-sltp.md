# Bug: check_exits 使用写死 USDT 金额而非方案设计的 ATR/价格止损

**日期：** 2026-06-26
**严重性：** 严重（与方案 §2.3/§7 设计不符，导致退出逻辑与开仓逻辑矛盾）
**影响范围：** `scripts/run_live_echo.py` 持仓退出逻辑
**关联方案：** `docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md` §2.3、§7
**关联脚本：** `scripts/run_live_echo.py` 第 50-53 行、第 262-297 行

---

## 一、现象

`run_live_echo.py` 中存在两套退出机制：

1. **交易所 SL/TP algo 单**（第 349-357 行）：基于信号的 `stop_price` / `target_price`，符合方案设计
2. **脚本内 `check_exits`**（第 262-297 行）：基于写死的 USDT 金额，不符合方案设计

```python
# 第 50-53 行：写死的参数
STOP_LOSS_USDT = -1.0      # 固定 -1 USDT
TAKE_PROFIT_USDT = 3.0     # 固定 +3 USDT
TIME_STOP_HOURS = 8        # 固定 8 小时
MAX_LEVERAGE = 1
```

## 二、方案设计对照

### 2.1 止损设计（方案 §2.3）

| 策略 | 硬止损 | 时间止损 | 1R = |
|------|--------|---------|------|
| A 上市 fade | 破前高 × 1.02（A1）/ × 1.005（A2） | 30min（A1）/ 20min（A2） | 30% equity |
| B funding 反转 | 反向 1.5×ATR(4h) | 24h | 20% equity |
| C β decoupling | 偏离的 1.2 倍 | 90min | 20% equity |
| D 周末 wick | 1.0×ATR(5m) | 60min | 15% equity |
| E pre-funding unwind | 1.0×ATR(1h) | 90min | 18% equity |
| H OI velocity | 1.0×ATR(5m) | 15min | 18% equity |

### 2.2 暴击流仓位状态机（方案 §7）

- 1R = `R_pct × equity`（单笔最大损失）
- 止损基于 **ATR 或价格结构**，非固定金额
- 时间止损因策略而异（15min ~ 24h）

### 2.3 代码实际

| 维度 | 方案 | 代码 |
|------|------|------|
| 止损 | 基于 ATR/价格结构 | 固定 -1 USDT |
| 止盈 | 基于信号的 `target_price` | 固定 +3 USDT |
| 时间止损 | 15min ~ 24h 不等 | 固定 8h |
| R 单位 | equity × R_pct | 无 R 概念 |

## 三、根因

`check_exits` 函数是在早期开发阶段编写的简化实现，当时尚未完成各策略的 ATR/价格止损计算。后续修复计划（`docs/plans/2026-06-26-live-echo-runner-fix.md`）专注于修复下单语义缺陷（Bug-1/Bug-2），未覆盖 `check_exits` 的参数对齐。

## 四、后果

1. **退出逻辑与开仓逻辑矛盾**：开仓时通过 `attach_sltp_via_algo_order` 使用信号的 `stop_price`/`target_price`（基于 ATR/价格），但 `check_exits` 又用固定金额做二次判断
2. **不同合约效果差异巨大**：-1 USDT 对 BTC（面值 0.01 BTC ≈ $600）和 DOGE（面值 10 DOGE ≈ $1.5）意义完全不同
3. **与方案设计严重不符**：方案明确要求基于 ATR/价格结构的动态止损

## 五、修复方向

删除 `check_exits` 函数及其调用，完全依赖：

1. **交易所 SL/TP algo 单**：基于信号的 `stop_price`/`target_price`（已实现）
2. **RiskGuard 熔断**：全局风控闸门（已恢复）

理由：
- 交易所 algo 单已在开仓时挂载，是第一道防线
- RiskGuard 是全局熔断，是第二道防线
- `check_exits` 是冗余且错误的第三道防线，应删除

## 六、验证方法

修复后需验证：

- [ ] `check_exits` 函数已删除
- [ ] `STOP_LOSS_USDT`、`TAKE_PROFIT_USDT`、`TIME_STOP_HOURS` 常量已删除
- [ ] `run_once` 不再调用 `check_exits`
- [ ] 交易所 algo 单正常工作（已有单元测试覆盖）
- [ ] RiskGuard 熔断正常工作（已有单元测试覆盖）

## 七、预防措施

1. **新增退出逻辑时必须对照方案 §2.3 参数表**：止损/止盈/时间止损的阈值必须从方案文档推导，不能写死
2. **共享 `pipeline.py` 只解决信号计算一致性，执行层一致性需单独守护**：`check_exits` 是执行层逻辑，未被 pipeline 覆盖

## 八、相关文件

- `scripts/run_live_echo.py` — 退出逻辑
- `docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md` — 方案 §2.3、§7
- `docs/bugs/2026-06-26-live-echo-runner-order-semantics.md` — 关联缺陷（下单语义）
