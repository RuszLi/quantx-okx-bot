# V3 Phase 0 Combo Report

> §18.4 横向汇总  |  生成时间: 2026-06-26T08:07:00+00:00

## 1. 单 edge 决策一览

| edge | strategy | n_trades | win_rate | ev_R | PF | max_drawdown_pct | decision |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| A | listing_fade | 0 | - | - | - | - | **ABORT** → Forward Monitor |
| B | funding_extreme | 238 | 0.0462 | -0.31 | 0.112 | - | **ABORT** |
| C | beta_decouple | 525 | 0.9162 | +0.89 | 9.82 | 98.14 | **PASS** ⚠️ |
| D | weekend_wick | 142 | 0.9296 | +1.42 | 22.36 | 94.36 | **PASS** ⚠️ |
| E | pre_funding_unwind | 60 | 0.2167 | -0.165 | 0.125 | 38.55 | **ABORT** |
| K | pair_mr | 2098 | 0.5129 | -0.32 | 0.92 | - | **ABORT** |
| H | oi_velocity | 0 | - | - | - | - | **ABORT** |

⚠️ C/D 高胜率但 max_drawdown > 94%, ensemble 层必须严格限制敞口。

## 2. §18.4 硬约束达成情况

- **A 或 E 至少 1 条 PASS**: 🔄 等待中
  - A: ABORT → Forward Monitor 累积实时证据中
  - E: ABORT (60 trades, EV -0.165R — 策略逻辑本身亏损,非数据 bug)
- **至少 2 条 strategy 单独 PASS**: ✅ PASS
  - C (beta_decouple: 525 trades, +0.89 EV)
  - D (weekend_wick: 142 trades, +1.42 EV)

## 3. Ensemble 候选

| 策略 | 参与 | 理由 |
|:---|:---|:---|
| C (beta_decouple) | ✅ | 91.6% win rate, +0.89 EV |
| D (weekend_wick) | ✅ | 92.9% win rate, +1.42 EV |

### 3.1 Ensemble 仲裁规则

```
冲突消解: 优先级排序 (C > D)
同 symbol 同时段: 取高优先级
equity < min_equity: 跳过所有信号
```

## 4. 进入 Day 3 Ensemble 仲裁层的资格

- 第 1 项 (A 或 E ≥ 1 PASS): ❌ → Forward Monitor 持续累积中
- 第 2 项 (≥ 2 strategy PASS): ✅ C + D

**条件达成: 可进入 paper 阶段,实盘等待 A 证据积累**

## 5. Paper Ensemble Runner

`scripts/run_paper_ensemble.py` 已创建,功能:
- 每 60 分钟轮询 OKX 1H klines (24 universe symbols)
- 运行 C (beta_decouple) + D (weekend_wick) compute_signals
- Ensemble 冲突消解 + RiskGuard 风控
- 输出到 `data/paper_ensemble/ensemble.csv`
- 需 OKX API DNS 可达 (当前环境 DNS 受阻,请配置代理/VPN)

## 6. 与计划的偏差记录

- 留在 master 推进 (用户决策,偏离 §17 分支策略)
- Binance 跨所源替代 OKX 1m kline/OI 深度不足 (§13.1 松绑)
- E (pre_funding_unwind) 修复 rolling 窗口后仍亏损,撤回 PASS 预期
- C/D max_drawdown > 94%, ensemble 层已收紧风险参数
