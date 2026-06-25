# Strategy V3.1 Zero-Data-Cost 暴击流组合审核结论

> 审核时间：2026-06-25 20:46\
> 审核角色：量化算法专家 / 加密货币自动交易算法专家\
> 审核对象：`docs/plan/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md`\
> 审核结论：**不通过**\
> 建议状态：`rejected-for-live` / `research-only-until-phase0-pass`

## 1. 总结判断

该方案相较 V1/V2 的方向切换是正确的：放弃低延迟清算追逐、放弃付费清算流、转向 0 数据成本的散户行为型 edge，符合当前资金 / 数据 / 延迟硬约束。

但它**不能作为实盘启动方案审核通过**。原因不是单一策略想法必然无效，而是当前文档把大量未验证假设、可能不可用的数据端点、未建模的小账户执行约束、以及高度相关的均值回归策略打包成“条件通过”。在自动交易语境下，这会把研究计划误标为可签收的交易计划。

本审核建议：**保留为 research plan，禁止进入 live α 阶段；先完成最小可证伪的 Phase 0.5 回测与 paper 验证后再复审。**

## 2. 主要优点

- \[值得保留] 方案明确承认 `$7 → $50 / 7 天` 不是稳定复利目标，而是右尾路径目标，避免了把娱乐预算包装成稳定 alpha。
- \[值得保留] 明确排除 V1 低延迟追清算与 V2 付费清算流路径，和 `docs/report/PHASE_0_REPORT.md` 的 ABORT 结论一致。
- \[值得保留] 引入统一 R 单位、最大连亏、日内 DD、冷却、echo test、paper trading 等风控概念，方向正确。
- \[值得保留] 把“先回测、再 paper、再小额 live”的阶段门写入方案，具备转成工程任务的基础。

## 3. 必须修复问题

### \[必须修复] 顶部状态与实际证据不匹配

原文顶部已经写成 `Status：conditionally-approved`，但当前文档没有任何一条新 edge 的真实回测结果、paper 结果、滑点实测、下单链路实测或最小订单验证。

这在交易系统里属于状态语义错误：`conditionally-approved` 容易被后续执行者理解为“可以在修复项后启动实盘”，但实际更准确的状态应是 `research-draft` 或 `pending-phase0-validation`。

本次按用户要求未修改原文件状态，因为审核未通过分支要求落审计文档；但后续建议单独把原文件状态改为 `rejected-for-live` 或 `research-only`。

### \[必须修复] 7 条 edge 没有任何实证结果，不能合并签收

文档把 A/B/C/D/E/K/H 同时作为组合策略讨论，但当前证据级别仍停留在假说、引用和经验观察。尤其 E/K/H 是 V3.1 新增策略，没有样本数、胜率、EV(R)、PF、最大连亏、交易成本后收益、敏感性扫描。

自动交易审核不能接受“多 edge 分散”作为替代证据。若每条 edge 都未经验证，组合后不是分散风险，而是叠加未知风险。最低通过条件应改为：每条 edge 独立产生 `trades.csv + summary.json + sensitivity_grid.csv + report.md`，且至少 2 条独立 PASS 后才允许进入 ensemble。

### \[必须修复] OKX 数据端点与点时可得性未签核

方案多处依赖 OKX funding、OI、announcements、leverage cap 和 historical listing events，但没有逐项确认 API 是否存在、是否免费、是否有历史深度、是否分页完整、是否有延迟、字段是否 point-in-time 可用。

高风险点包括：

- `open-interest-history` endpoint 名称与 OKX 官方常见接口命名不一致，需用实测请求确认；不能在方案里直接当作可用历史 1h 数据源。
- funding 回测必须区分“当时可见的预测 funding / next funding”与“事后 settled funding history”，否则 B/E 会产生 lookahead bias。
- announcements 历史公告接口不一定能稳定覆盖 6 个月新上市事件，且公告时间、上线交易时间、合约实际可交易时间需要单独对齐。
- `account/max-leverage` 是账户态接口，受用户账户、币种、保证金模式、风险限额影响，不能直接当作历史 leverage cap 回测字段。

### \[必须修复] `$7` 小账户可执行性没有建模

方案的核心约束是 `$7`，但没有证明 OKX 永续在目标标的上满足：最小下单张数、最小名义价值、合约面值、价格 tick、数量 lot、保证金模式、手续费、止损单精度、post-only 撤单重挂、两腿最小仓位。

这会直接影响策略是否可交易，特别是：

- K 是两腿 pair trade，`$7` 权益下双腿同时满足最小下单单位的概率很低，且任一腿未成交后的回滚成本可能吞掉 1R 的显著比例。
- A/E/H 使用高杠杆和短窗口，post-only 入场可能频繁错过成交；若改 taker，手续费和滑点会改变 EV。
- 多个 alt 新上市或低流动性标的的 spread 可能远大于文档假设的 0.10% per side。

在完成 `min_order_notional / lot_size / tick_size / margin_required / fee / spread` 实测表之前，不能批准实盘。

### \[必须修复] K 策略把 z-score ratio 当成 cointegration 证据

K 的核心假说是同主题 alt cointegrated，但实现规格只计算 7 天 rolling log-ratio z-score，没有 ADF/Engle-Granger 检验、half-life 估计、相关性稳定性、beta hedge ratio、structural break 检测。

这会把“同涨同跌的高相关资产”误判为“均值回归 pair”。在 crypto narrative 切换中，高相关资产最容易共同趋势化，`abs(z) ≥ 2` 可能不是套利点，而是信息扩散初期。K 不能在当前形态进入实盘候选，只能先作为研究项。

### \[必须修复] E/B funding 策略未计入 funding cashflow 与强趋势尾部

B/E 的收益目标围绕 funding 回归和价格 MR，但没有明确把实际 funding payment 计入 PnL，也没有说明在结算跨越时点的仓位是否支付/收取 funding。

如果策略在高正 funding 时做空，方向上可能收 funding；在极负 funding 时做多也可能收 funding。但若时点、交易所结算规则、mark price 与 position close 时间处理错误，回测会严重偏差。E 尤其依赖结算前后窗口，必须做 point-in-time settlement simulator，而不是简单价格回归模拟。

### \[必须修复] H 策略的数据粒度与交易窗口冲突

H 试图用 1h OI velocity 预测 5-15m 爆发后回归，但文档同时承认 OKX OI 数据为 1h 粒度且可能滞后。若 Stage 1 信号在数据更新后才可见，许多 5-15m burst 在 live 中已经发生，回测若按 bar timestamp 使用 OI 会产生时序错配。

H 必须在回测中强制加入 API 发布延迟、轮询延迟、bar close 延迟、计算延迟，并证明信号在 live 可交易时仍存在。否则不能纳入组合频次估算。

## 4. 建议修改问题

### \[建议修改] 频次估算过乐观

方案声称 7 条 edge 合计 `80-150 setup/周`，但这是从假设触发率累加而来，不是历史扫描结果。E 的 `5-15 setup/天`、K 的 `3-10 setup/天`、H 的 `3-8 setup/天` 均未给出历史 hit-rate 分布。

建议把所有频次表述从承诺语气改为待验证假设，并要求报告输出：原始触发数、成交数、过滤后交易数、错过成交数、被风控拦截数。

### \[建议修改] 多策略相关性没有约束

B/E/H 都显著依赖 OI/funding/短期 MR，C/K/D 也偏 mean reversion。组合看似 7 条 edge，实际可能在 alt 风险偏好反转、宏观冲击、交易所流动性骤降时同向亏损。

ensemble 闸门不应只看 `EV ≥ +0.4R` 与 `max DD ≤ 70%`，还需要输出策略间收益相关矩阵、同一小时内共同亏损分布、macro day 排除前后的表现差异。

### \[建议修改] 风控目标与破产概率不匹配

单日 DD `50%`、ensemble 最大 DD `70%` 对 `$7` 小账户几乎等于破产前才刹车。若目标是把 `$7` 当娱乐预算，这可以接受；若目标是自动交易框架验证，应把 live α 阶段降到 `1x + 最小仓位 + dry-run comparison`，只验证执行链路，不验证收益目标。

### \[建议修改] 文献引用不能替代可交易 edge

文档引用 microstructure、funding、perps pricing 文献是有帮助的，但多处引用只支持“市场存在某类现象”，不支持“OKX、这些币、这个窗口、这个成本模型、这个账户规模下可盈利”。建议在每条 edge 的报告里加入“引用支持什么 / 不支持什么”的边界段。

## 5. 复审通过条件

若要重新申请审核通过，建议满足以下最小条件：

1. 将原方案状态改为 `pending-phase0-validation`，避免误导执行。
2. 先只选 2 条最高优先级策略进入 Phase 0.5：A listing fade 与 E pre-funding unwind；不要同时工程化 7 条。
3. 为每条策略生成真实回测报告，至少包含样本数、胜率、EV(R)、PF、最大连亏、最大 DD、交易成本、滑点敏感性、参数敏感性、按 symbol/hour 分组。
4. 单独生成 OKX API 可用性报告，列出 endpoint、请求样例、返回字段、历史深度、限速、延迟、point-in-time 可用性。
5. 单独生成 `$7 execution feasibility` 报告，覆盖每个候选币的最小下单、lot/tick、手续费、spread、保证金、止损可下单性。
6. Paper 至少运行 24 小时，比较 live signal 与回测重放一致性，吻合度达到方案所写的 80% 以上。
7. echo test 只能验证链路，不得被当作策略盈利证据。

## 6. 最终结论

**审核不通过。**

该文档可以作为 V3.1 研究路线图保留，但不能作为自动交易实盘签收方案。当前最危险的问题是：它用“多 edge + 条件通过”的叙事掩盖了所有 edge 尚未被实证验证这一事实。

建议下一步不是继续扩频到更多策略，而是收缩到 A/E 两条，完成严格、可复现、含真实执行约束的 Phase 0.5。只有在至少 2 条策略独立 PASS 且 `$7` 小账户执行可行后，才允许重新审核 live α 阶段。

<br />

## 7. PM 批注

- [x] 把 live α 阶段降到 `1x + 最小仓位 + dry-run comparison`：那是下个阶段需要做的，现阶段就是 $7 -> $50，快速积累。

处理：已在计划 §18.6 中采纳 PM 批注，保留 `$7 → $50` 与 α 阶段设计 R；echo test 只验证链路，不改变暴击流目标。对应约束改为“§18 闸门不过则禁止实盘”，而不是“降级为 1x dry-run 实盘”。
