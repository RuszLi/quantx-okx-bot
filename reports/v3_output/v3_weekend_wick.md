# V3 Strategy D — weekend_wick

> §18.4 单 edge 证据闸门报告  |  生成时间: 2026-06-26T04:48:49.459083+00:00

## 1. 决策结论

- **DECISION**: `PASS`
- **ROBUSTNESS**: `HIGH`
- **n_trades**: 142
- **win_rate**: 0.9296
- **EV(R)**: 1.1644
- **profit_factor**: 48.2210
- **max_consec_losses**: 1
- **max_drawdown_pct**: 94.36%

## 2. 数据来源与点时证据

- **回测窗口**: 2026-05-15 ~ 2026-06-24 (41 天)
- **universe 大小**: 24 个候选 symbol
- **kline 源**: Binance USDⓈ-M 1m kline (跨所松绑 §13.1)
- **funding 源**: OKX `/api/v5/public/funding-rate-history` (94 天深度)
- **OI 源**: Binance metrics (5min 频率,30+ 天深度)

### 2.1 point-in-time 证据样本

> 该策略不依赖 funding/OI/announcement 的点时字段 (bar-driven 策略)

## 3. PnL 分解 (per-trade R 单位)

- **price_pnl_R_total**: 178.8649
- **fee_slippage_R_total**: 21.6432
- **funding_pnl_R_total**: 0.0000

## 4. 执行模拟参数

- fee_taker_per_side: 0.0005
- fee_maker_per_side: 0.0002
- slippage_per_side: 0.0003
- initial_equity: $7.0
- 进出场默认 taker (保守估计;live 用 post-only + taker fallback)

## 5. exit_reason 分布

| exit_reason | count |
|:---|:---|
| TP | 97 |
| TIME | 44 |
| SL | 1 |

## 6. 分组表

见同目录下:
- `group_by_symbol.csv`
- `group_by_hour_utc.csv`
- `group_by_weekday.csv`
- `group_by_exit_reason.csv`

## 7. 敏感性网格

见 `sensitivity_grid.csv` (共 142 笔交易,3x3x3=27 cells)
ROBUSTNESS 评级: `HIGH`

## 8. 文件清单

- `per_strategy/weekend_wick/trades.csv`
- `per_strategy/weekend_wick/summary.json`
- `per_strategy/weekend_wick/sensitivity_grid.csv`
- `per_strategy/weekend_wick/group_by_*.csv`
- `per_strategy/weekend_wick/point_in_time_evidence.json` (event-driven 策略)
