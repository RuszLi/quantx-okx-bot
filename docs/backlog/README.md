# Backlog — 待修复/待优化项

> 按优先级排序。高优先级项在修复计划中处理，低优先级项在对应阶段完成后统一清理。

---

## P1 — 策略 PASS 后必须修复（阻塞正式上线）

### [BUG] 策略止损逻辑使用百分比距离而非 ATR 倍数

- **发现日期：** 2026-06-26
- **关联方案：** `docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md` §2.3
- **关联代码：**
  - `src/backtest/strategies/beta_decouple.py:59-61`
  - `src/backtest/strategies/weekend_wick.py:44-46`
- **当前实现：**
  - C 策略：`stop_distance = max(abs(alt_deviation) * 0.25, entry_price * 0.015)`
  - D 策略：`stop_distance = max((high - low) * 0.25, entry_price * 0.01)`
- **方案设计：**
  - C 策略：硬止损 = 偏离的 1.2 倍（z 走到 ±3.0）
  - D 策略：硬止损 = `1.0×ATR(5m)`
- **影响：** 回测结果与实盘止损逻辑必须一致，否则回测 EV 无法外推到实盘
- **触发条件：** 策略通过 §18.4 单 edge 证据闸门后，统一修复止损计算逻辑
- **不阻塞：** 当前 $7 压力测试阶段，百分比止损已能保护仓位

---

## P2 — 优化项（不阻塞上线，有空再做）

*（暂无）*

---

## P3 — Nice to have

*（暂无）*
