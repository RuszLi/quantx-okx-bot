# V3 实施变更日志

> 根据 `docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md` §17 对内承诺，实施过程中任何阈值或设计变更必须记录于此。

| 日期 | 变更 | 触发原因 | 影响范围 | 状态 |
|---|---|---|---|---|
| 2026-06-26 | **移除 `EnsembleStrategy.min_equity`** — 取消 $7 最低权益闸门，子策略产生信号后直接进入 ensemble 仲裁，不做权益过滤 | 实盘权益 $6.24 低于 $7.0 门槛，导致所有信号被静默丢弃，连续 2h 无订单 | `src/backtest/strategies/ensemble.py`: 移除 `min_equity` 字段；`resolve_conflicts` 不再检查权益 | 已实施 |
