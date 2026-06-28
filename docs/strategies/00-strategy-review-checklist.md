# 策略 Review 检查清单

> **用途：** 在策略研究、回测报告评审、晋升候选审核时，强制补齐最容易遗漏的灰色地带。

---

## 1. 对象一致性

- [ ] 报告对象和执行对象是同一个 candidate，而不是“单 edge 报告”替代“ensemble / live 对象”
- [ ] `symbol universe`、`bar_freq`、`time_stop_bars`、`risk_R` 在策略文档、回测脚本和输出报告中一致
- [ ] 策略文档没有把“研究对象”和“实盘对象”混写在同一段表述里

## 2. 回测编排一致性

- [ ] 策略文档已显式写出 `exit_klines_freq`
- [ ] `exit_klines_freq == strategy.bar_freq`，或已书面说明 event-driven 例外
- [ ] `time_stop_bars × exit_klines_freq_duration` 与文档宣称的实际持仓时间一致
- [ ] 若看到 `avg_holding_bars = 0`、分钟级持仓却宣称小时级策略、异常高胜率等信号，已追查回测编排而不是只看策略文件
- [ ] `src/backtest/tests/test_v3_phase0_exit_alignment.py` 已覆盖该策略所属路径，或新增了同等级回归测试

## 3. 信号定义一致性

- [ ] 策略名字与实际信号定义一致，不存在“名叫 wick，实际算 close z-score”之类名实不符
- [ ] 方向逻辑不是过度简化的单根 K 线反转假设，除非文档明确承认并说明原因
- [ ] 止损、止盈、时间止损三者的组合在持仓窗口内是可实现的，而不是天然制造大量 `TIME` 退出

## 4. 点时可得性

- [ ] 所有 funding / OI / 公告字段都写明了 live 是否可见
- [ ] 若字段只在结算后可见，回测没有把它当成实时可见信息使用
- [ ] 若存在发布时间延迟，回测中已显式模拟该延迟

## 5. 风险语义

- [ ] 文档已说明 `cross / isolated / net / long_short_mode` 假设
- [ ] 文档已说明并发持仓上限与 liquidation 是否建模
- [ ] 若 live 使用账户级风控，而研究只验证单笔 trade 逻辑，已明确阻断晋升

## 6. 报告可信度

- [ ] `summary.json` 的核心指标没有出现明显自相矛盾（例如高胜率 + 极端低持仓 + 异常高 PF）
- [ ] 费用、滑点、funding cashflow 已拆分列示，而不是只给一个总 PnL
- [ ] 分组表（symbol / hour / weekday / exit_reason）已输出且可回查
- [ ] 对 `PASS` 结论给出了足够样本数与稳健性证据，而不是只看一次漂亮回测

## 7. 晋升判定

- [ ] 当前策略可以明确归类为 `PASS / REPARAM / ABORT / NEEDS-INVESTIGATION`
- [ ] 若策略未通过，文档已明确写出阻断原因，而不是模糊写“可后续优化”
- [ ] 若策略已被证伪，已更新到 `docs/strategies/`，而不是继续让旧报告误导后续实现

---

## 必问问题

评审时至少追问以下 5 个问题：

1. 这份报告对应的到底是哪一个执行对象？
2. 这条策略声明的 `bar_freq`，在 exit 模拟里真的是同样频率吗？
3. 这条策略依赖的字段，在 live 当下真的能看到吗？
4. 这份回测如果进入 cross 账户、多仓位并发环境，还成立吗？
5. 这份结论如果是错的，会误导哪一层：研究、实现、还是实盘？
