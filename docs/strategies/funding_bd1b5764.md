# funding_bd1b5764

## 1. 基本信息

- **策略 ID：** `funding_bd1b5764`
- **策略名称：** `funding_z_1.5_rr_3.0`
- **所属阶段：** `rejected`
- **Owner：** `edge-discovery-pipeline`
- **关联输入：** `docs/plans/2026-06-28-1000-strategy-v3.2-automated-edge-discovery-pipeline.md`
- **关联设计 / 架构 / 计划：** `docs/pipeline-user-guide.md`

## 2. 研究问题

- 这条策略试图捕捉什么行为偏差？ funding（资金费率）拥挤与波动率 regime（市场波动状态）切换下的非对称反应。
- 该偏差为什么在 Crypto 市场中可能存在，而不是传统指标重包装？ 因为它直接使用 funding cashflow（资金费率现金流）与波动率分位，而不是 RSI / MA 这类传统技术指标。
- 哪些证据支持继续研究，哪些证据会直接否决它？ 由 pipeline 的 IS gate、CPCV、DSR、holdout 与鲁棒性评级共同给出。

## 3. 对象定义

- **执行对象：** `single edge`
- **symbol universe：** `BTCUSDT`
- **市场类型：** `SWAP`
- **时间粒度：** `bar_freq = 1h`
- **是否 event-driven：** `no`

## 4. 数据来源与点时约束

| 数据 | 来源 | 粒度 | point-in-time 可得性 | 备注 |
| --- | --- | --- | --- | --- |
| K 线 | Binance/本地缓存 | `1m → 1h` | 是 | 由 `src/pipeline/data_layer.py` 聚合 |
| Funding | OKX funding history | `1m 对齐` | 依 `point_in_time` 列判断 | 进入 settlement（结算时点）后才可视 |
| OI | none | N/A | N/A | 当前候选未使用 |
| 公告 / 事件 | none | N/A | N/A | 当前候选未使用 |

- 参数快照：

```json
{
  "funding_window": 480,
  "r_to_r": 3.0,
  "regime_quantile_high": 0.6,
  "regime_quantile_low": 0.3,
  "rv_window": 3,
  "stop_distance_pct": 0.005,
  "time_stop_bars": 12,
  "z_score_threshold": 1.5
}
```

## 5. 信号定义

- **入场条件：** funding z-score 超过阈值，且波动率 regime 已进入 `LOW / HIGH`。
- **方向逻辑：** `LOW` regime 做反转，`HIGH` regime 做顺势。
- **止损逻辑：** 使用参数化 `stop_distance_pct`。
- **止盈逻辑：** 使用参数化 `r_to_r`。
- **时间止损：** `time_stop_bars = 12`
- **风险单位（1R）：** `0.20`

## 6. 回测编排契约

| 项目 | 当前值 | 说明 |
| --- | --- | --- |
| `bar_freq` | `1h` | 策略声明频率 |
| `exit_klines_freq` | `1h` | `simulate_exits()` 输入频率 |
| `time_stop_bars` | `12` | 最大持仓 bar 数 |
| `实际时间止损` | `time_stop_bars × 1h` | 依策略频率解释 |
| `is_event_driven` | `no` | 是否保留分钟级 exit |

## 7. 风险语义

- **账户模式假设：** `cross`
- **杠杆假设：** `8.00`
- **并发持仓上限：** `1`
- **liquidation 是否已建模：** `no`
- **哪些 live 过滤条件只存在于执行侧：** `none documented yet`

## 8. 证据与验收

- **必备报告：** `reports/pipeline_output/<run_id>/results.csv`
- **必备测试：** `src/pipeline/tests/test_validator.py`、`src/pipeline/tests/test_executor.py`
- **必备输出文件：** `docs/strategies/funding_bd1b5764.md`
- **拒绝条件：** 任何 gate 返回失败，或 holdout `ev_R <= 0`

```json
{
  "avg_holding_bars": 0.0,
  "ev_R": 0.0,
  "is_gate": {
    "reasons": [
      "n_trades=0 < 10 (insufficient sample)"
    ],
    "verdict": "ABORT"
  },
  "max_consec_losses": 0,
  "max_drawdown_R": 0.0,
  "n_trades": 0,
  "profit_factor": 0.0,
  "win_rate": 0.0
}
```

## 9. Review 结论

- **当前结论：** `ABORT`
- **主要风险：**
- n_trades=0 < 10 (insufficient sample)
- **能否进入 promotion candidate：** `no`
- **若不能，卡在什么 gate：** `rejected by pipeline`

## 10. 变更记录

| 日期 | 变更 | 原因 |
| --- | --- | --- |
| 2026-06-29 | Pipeline auto-generated record | Phase 5 automation |
