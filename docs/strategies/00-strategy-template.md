# 策略研究与晋升模板

> **用途：** 为每条策略提供统一的研究、回测、晋升候选描述骨架。
> **适用范围：** `docs/strategies/` 下所有正式策略文档。

---

## 1. 基本信息

- **策略 ID：**
- **策略名称：**
- **所属阶段：** `idea / research candidate / backtest candidate / promotion candidate / rejected`
- **Owner：**
- **关联输入：**
- **关联设计 / 架构 / 计划：**

## 2. 研究问题

- 这条策略试图捕捉什么行为偏差？
- 该偏差为什么在 Crypto 市场中可能存在，而不是传统指标重包装？
- 哪些证据支持继续研究，哪些证据会直接否决它？

## 3. 对象定义

- **执行对象：** 单 edge / ensemble / pair / 其它
- **symbol universe：**
- **市场类型：** `SWAP / spot / 其它`
- **时间粒度：** `bar_freq =`
- **是否 event-driven：**

## 4. 数据来源与点时约束

| 数据 | 来源 | 粒度 | point-in-time 可得性 | 备注 |
| --- | --- | --- | --- | --- |
| K 线 |  |  |  |  |
| Funding |  |  |  |  |
| OI |  |  |  |  |
| 公告 / 事件 |  |  |  |  |

- 明确写出哪些字段是 live 可见，哪些字段仅为事后结算或回放可见。
- 若任一关键字段存在前视偏差风险，必须写清拒绝条件。

## 5. 信号定义

- **入场条件：**
- **方向逻辑：**
- **止损逻辑：**
- **止盈逻辑：**
- **时间止损：**
- **风险单位（1R）：**

> 若策略名与实际信号定义存在差异（例如名字写 wick，实际却在算 close z-score），必须在本节显式解释；不能让命名误导后续 review。

## 6. 回测编排契约

这是强制章节，不能省略。

| 项目 | 当前值 | 说明 |
| --- | --- | --- |
| `bar_freq` |  | 策略声明频率 |
| `exit_klines_freq` |  | `simulate_exits()` 实际输入频率 |
| `time_stop_bars` |  | 最大持仓 bar 数 |
| `实际时间止损` |  | `time_stop_bars × exit_klines_freq_duration` |
| `is_event_driven` |  | 是否保留分钟级 exit |

- **硬规则 1：** `exit_klines_freq` 必须与策略声明一致；若不一致，文档状态必须是 `rejected`。
- **硬规则 2：** 如果策略使用自定义 exit 频率，必须说明理由和验证证据。
- **硬规则 3：** 所有依赖 funding / OI / event 的策略，必须写明回测中如何模拟字段发布时间与执行延迟。

## 7. 风险语义

- **账户模式假设：** `cross / isolated / net / long_short_mode`
- **杠杆假设：**
- **并发持仓上限：**
- **liquidation 是否已建模：**
- **哪些 live 过滤条件只存在于执行侧：**

若这里任何一项没有建模，只能停留在 `research candidate` 或 `backtest candidate`，不得晋升。

## 8. 证据与验收

- **必备报告：**
- **必备测试：**
- **必备输出文件：**
- **拒绝条件：**

建议至少包括：

1. `trades.csv`
2. `summary.json`
3. `sensitivity_grid.csv`
4. 分组表（symbol / hour / weekday / exit_reason）
5. 如适用，point-in-time 证据样本

## 9. Review 结论

- **当前结论：** `PASS / REPARAM / ABORT / NEEDS-INVESTIGATION`
- **主要风险：**
- **能否进入 promotion candidate：** `yes / no`
- **若不能，卡在什么 gate：**

## 10. 变更记录

| 日期 | 变更 | 原因 |
| --- | --- | --- |
|  |  |  |

---

## 使用规则

1. 每条策略一份独立文档，不与执行计划混写。
2. `第 6 节 回测编排契约` 是强制项，不能删除。
3. 任何策略在进入 `promotion candidate` 前，必须补全 `第 7 节 风险语义`。
4. 若策略已被证伪，应保留文档并将阶段改为 `rejected`，不要直接删除。
