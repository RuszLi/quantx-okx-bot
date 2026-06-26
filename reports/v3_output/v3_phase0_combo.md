# V3 Phase 0 Combo Report

> §18.4 横向汇总  |  生成时间: 2026-06-26T04:49:34.513001+00:00

## 1. 单 edge 决策一览

| edge | strategy | n_trades | win_rate | ev_R | PF | max_consec_losses | decision |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| A | listing_fade | 0 | 0.0000 | 0.0000 | 0.0000 | 0 | **ABORT** |
| B | funding_extreme | 354 | 0.0282 | -0.3401 | 0.0062 | 157 | **ABORT** |
| C | beta_decouple | 6020 | 0.9065 | 0.4402 | 37.3060 | 4 | **PASS** |
| D | weekend_wick | 142 | 0.9296 | 1.1644 | 48.2210 | 1 | **PASS** |
| E | pre_funding_unwind | 60 | 0.2167 | -0.1650 | 0.1249 | 8 | **ABORT** |
| K | pair_mr | 2098 | 0.5129 | -0.3195 | 0.3903 | 19 | **ABORT** |
| H | oi_velocity | 0 | 0.0000 | 0.0000 | 0.0000 | 0 | **ABORT** |

## 2. §18.4 硬约束达成情况

- **A 或 E 至少 1 条 PASS**: ❌ FAIL
  - A/E PASS 列表: 无
- **至少 2 条 strategy 单独 PASS**: ✅ PASS
  - PASS 列表: C:beta_decouple, D:weekend_wick

## 3. Ensemble 候选

通过 §18.4 单 edge 闸门的策略:

- **C (beta_decouple)**: EV=0.4402R, PF=37.3060, n=6020
- **D (weekend_wick)**: EV=1.1644R, PF=48.2210, n=142

## 4. 进入 Day 3 Ensemble 仲裁层的资格

**❌ 禁止进入**

判定逻辑:
- A 或 E 至少 1 条 PASS
- 且至少 2 条 strategy 单独 PASS

## 5. K/H 替代 A/E 路径 (用户选择)

若 A/E 均 ABORT,根据用户决策「推进 K/H 替代 A/E」:
- K/H 仍按真实历史数据回测,产出报告 (本文件 §1 已包含)
- **K/H PASS 仅作为研究输出,不进入 live α 阶段**
- 即便 K/H 都 PASS,也必须等 A/E 中至少 1 条 PASS 才允许启动 $7 → $50 live

## 6. 与计划的偏差记录

- 留在 master 推进 (用户决策,偏离 §17 分支策略)
- Binance 跨所源替代 OKX 1m kline/OI 深度不足 (§13.1 松绑)
- K/H 替代 A/E 仅作研究输出,不进入 live (用户决策)
