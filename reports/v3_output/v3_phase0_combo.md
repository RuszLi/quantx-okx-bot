# V3 Phase 0 Combo Report

> §18.4 横向汇总  |  生成时间: 2026-06-27T12:25:58.989103+00:00

## 1. 单 edge 决策一览

| edge | strategy | n_trades | win_rate | ev_R | PF | max_consec_losses | decision |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| B | funding_extreme | 238 | 0.3992 | -0.1434 | 0.6131 | 12 | **ABORT** |
| C | beta_decouple | 23 | 0.3478 | -0.1523 | 0.3454 | 6 | **ABORT** |
| E | pre_funding_unwind | 60 | 0.3500 | -0.1780 | 0.4628 | 5 | **ABORT** |
| K | pair_mr | 2091 | 0.5141 | -0.3035 | 0.4120 | 19 | **ABORT** |
| H | oi_velocity | 0 | 0.0000 | 0.0000 | 0.0000 | 0 | **ABORT** |

## 2. §18.4 硬约束达成情况

- **A 或 E 至少 1 条 PASS**: ❌ FAIL
  - A/E PASS 列表: 无
- **至少 2 条 strategy 单独 PASS**: ❌ FAIL
  - PASS 列表: 无

## 3. Ensemble 候选

> 无任何策略 PASS,不能进入 ensemble 仲裁层。

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
