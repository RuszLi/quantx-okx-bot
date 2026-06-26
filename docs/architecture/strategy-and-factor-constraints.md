# 策略与因子约束吸引子

> **文档定位：** 架构级约束文档，限制策略和因子的挖掘方向，作为工程级别的吸引子（Attractor），避免 LLM 生成的策略和因子超出工程限制与预期。

---

## 1. 核心目标

本文件定义策略与因子挖掘的**边界条件**，所有新增策略、因子、信号必须满足以下约束才能进入工程实现阶段：

- **现代化方法**：采用统计学、计量经济学、机器学习、深度学习等现代量化方法
- **市场适配**：符合加密货币（Crypto）市场的交易特征，而非传统金融市场的简单移植
- **工程可行**：在现有硬件约束下可执行，避免理想化设计

---

## 2. 非目标（Anti-Targets）

以下类别**禁止**作为策略或因子的核心逻辑，无论其形式如何包装：

### 2.1 传统技术指标

| 类别 | 示例 | 禁止原因 |
|:---|:---|:---|
| 动量指标 | RSI、MACD、KDJ、Stochastic | 在高效市场中已被充分套利，Alpha 衰减至零 |
| 趋势指标 | MA、EMA、Bollinger Bands、ADX | 滞后性强，无法适应 Crypto 市场的 regime 快速切换 |
| 波动率指标 | ATR、Historical Volatility | 仅描述历史波动，无法预测未来波动率的结构性变化 |
| 成交量指标 | OBV、VWAP（作为独立信号） | 在 Crypto 市场中成交量数据噪声大，信号不稳定 |

### 2.2 传统交易策略

- **趋势跟踪**（Trend Following）：基于均线交叉、突破等传统方法
- **均值回归**（Mean Reversion）：基于布林带、Z-Score 等传统阈值
- **动量策略**（Momentum）：基于过去 N 日收益率排序的多空组合
- **配对交易**（Pairs Trading）：基于协整关系的传统统计套利

### 2.3 信号组合的层级堆叠

- 传统信号 → 传统信号组合 → 传统信号组合的组合
- 任何层级的组合，只要底层信号属于非目标类别，整体仍属于非目标
- **例外**：如果组合中引入了现代方法（如机器学习权重优化、动态 regime 切换），且核心 Alpha 来源来自现代方法，则不属于非目标

---

## 3. 目标（Targets）

以下类别的策略与因子**鼓励**挖掘，但需通过工程可行性审查：

### 3.1 市场微观结构（Market Microstructure）

| 方向 | 方法示例 | 适用场景 |
|:---|:---|:---|
| 订单流分析 | Order Flow Imbalance (OFI)、Volume Delta、Trade Arrival Rate | 短期价格冲击预测、流动性消耗监测 |
| 清算级联 | Liquidation Cascade Detection、Forced Liquidation Flow | 极端行情下的反向交易机会 |
| 订单簿动力学 | Book Imbalance、Depth Ratio、Cancel Rate | 短期价格方向预测、做市策略 |
| 信息不对称 | Informed Trading Probability (PIN)、Toxic Flow | 识别知情交易者，避免逆向选择 |

### 3.2 统计学与计量经济学

| 方向 | 方法示例 | 适用场景 |
|:---|:---|:---|
| 时间序列建模 | ARIMA-GARCH、State-Space Models、Kalman Filter | 波动率预测、趋势提取 |
| 协整与误差修正 | Dynamic OLS、Regime-Switching Cointegration | 跨品种价差交易 |
| 结构变化检测 | Chow Test、CUSUM、Bayesian Changepoint Detection | 市场 regime 切换识别 |
| 极值理论 | EVT、POT (Peaks Over Threshold)、Hill Estimator | 尾部风险建模、极端行情预测 |

### 3.3 机器学习与深度学习

| 方向 | 方法示例 | 适用场景 |
|:---|:---|:---|
| 监督学习 | XGBoost、LightGBM、Random Forest | 多因子非线性组合、信号权重优化 |
| 序列模型 | LSTM、GRU、Temporal Fusion Transformer | 时序特征提取、多步预测 |
| 强化学习 | DQN、PPO、SAC | 动态仓位管理、执行优化 |
| 图神经网络 | GNN、Graph Attention Network | 跨品种关联建模、传染效应预测 |
| 生成模型 | VAE、GAN、Diffusion Models | 合成数据增强、压力测试场景生成 |

### 3.4 Crypto 市场特有特征

| 特征 | 可利用的方法 | 数据来源 |
|:---|:---|:---|
| 资金费率（Funding Rate） | Funding Rate Arbitrage、Mean Reversion with Regime | OKX/Binance Funding Rate API |
| 清算数据 | Liquidation Cascade Fade、Forced Flow Analysis | OKX Liquidation Orders、Coinglass |
| 新币上市效应 | New Listing Volatility Harvest、Pump-then-Fade | OKX Instrument Listing Announcements |
| 周末流动性枯竭 | Weekend Wick Strategy、Liquidity-Adjusted Volatility | Historical K-line Data |
| 链上数据 | Whale Movement Tracking、Exchange Inflow/Outflow | Glassnode、Dune Analytics |

---

## 4. 硬件约束

### 4.1 网络延迟

| 约束项 | 数值 | 影响 |
|:---|:---|:---|
| 本机 → 交易所 RTT | 200-400 ms | 无法参与高频做市（HFT）、无法抢点火点 |
| 延迟不可优化 | 硬件级别瓶颈 | 策略设计必须**延迟无关**（Delay-Insensitive）或**延迟容忍**（Delay-Tolerant） |

### 4.2 延迟适配策略

**禁止的设计模式：**

- ❌ 假设零延迟的市价单策略
- ❌ 依赖微秒级时间优势的套利策略
- ❌ 需要频繁挂单撤单的做市策略

**推荐的设计模式：**

- ✅ **Fade 策略**：等待事件尘埃落定后做反向交易（如清算反弹）
- ✅ **Post-Only Limit**：使用 post-only 限价单，避免被逆向选择
- ✅ **时间窗口宽松**：信号有效期 > 1 分钟，允许延迟执行
- ✅ **异步执行**：信号生成与订单执行解耦，容忍秒级延迟

### 4.3 数据频率约束

| 数据类型 | 最大可用频率 | 设计启示 |
|:---|:---|:---|
| K 线（K-line） | 1 分钟 | 策略信号周期 ≥ 5 分钟 |
| 订单簿（Order Book） | 实时（WebSocket） | 可用于微观结构分析，但执行延迟需考虑 |
| 成交数据（Trades） | 实时（WebSocket） | 可用于订单流分析，但需过滤噪声 |
| 清算数据 | 实时（WebSocket） | 事件驱动策略的核心数据源 |

---

## 5. 数据约束

### 5.1 数据质量要求

- **存活者偏差**（Survivorship Bias）：必须包含已退市品种的历史数据
- **前视偏差**（Look-Ahead Bias）：严格禁止使用未来数据，所有特征必须 point-in-time
- **过拟合风险**（Overfitting Risk）：小样本场景（如新币上市）需使用交叉验证或合成数据增强

### 5.2 数据源优先级

| 优先级 | 数据源 | 用途 |
|:---|:---|:---|
| P0 | OKX WebSocket（实时） | 执行层数据、实时信号计算 |
| P1 | OKX REST API（历史） | 回测、特征工程 |
| P2 | 第三方数据（Coinglass、Glassnode） | 辅助验证、链上特征 |

---

## 6. 工程实现约束

### 6.1 SDK 与代理

- 所有 OKX 交互必须通过 `python-okx` SDK，遵循 `okx-sdk-rules.md`
- 所有外部请求必须通过本地代理，遵循 `sys-proxy-rules.md`

### 6.2 执行层约束

- **仓位管理**：单笔风险 ≤ 20% 权益，避免满仓操作
- **杠杆限制**：10-15x（30x 在 200ms 延迟下会被滑点和维持保证金吃掉）
- **订单类型**：优先使用 post-only limit，市价单仅用于紧急退出

### 6.3 验证要求

所有新增策略必须通过：

1. **回测验证**：至少 3 个月历史数据，包含不同市场 regime
2. **统计显著性**：夏普比率（Sharpe Ratio）> 1.5，最大回撤（Max Drawdown）< 30%
3. **执行可行性**：考虑 200ms 延迟、滑点、手续费后的净期望仍为正
4. **压力测试**：在极端行情（如 2022-05 LUNA 崩盘、2023-03 FTX 事件）下不爆仓

---

## 7. 防止过拟合设计

在强化学习（RL）交易中，过拟合常表现为Agent过度拟合训练环境的特定细节，而非学习到普适的交易规则。例如：

- 记忆特定序列：Agent可能记住了训练数据中某次特定价格波动的完整序列，并据此做出决策，但这种序列在实盘中不可能完全重现。
- 利用环境bug：在模拟环境中，可能存在一些微小的“bug”或非现实设定（如无限流动性），Agent会学会利用这些漏洞获得高奖励，但在真实市场中这些条件不存在，策略就会失效。
- 对噪声敏感：策略对输入数据的微小变化（如几个点的价格差异）反应剧烈，说明它学习的是噪声而非规律。

非目标：
Agent会“跑着跑着就适配了最近行情”——它找到了最近行情中的某种特定模式（甚至是噪声），并对此进行了优化。

如何有效避免过拟合？核心验证协议
以下是构建稳健策略必须遵循的验证协议，其核心思想是模拟策略在未知市场中的表现。

验证阶段	核心做法	目的与效果
样本内优化 (IS)	在训练集上寻找最优参数。但关键不是找到单一最优解，而是寻找参数的稳定区间，避免对噪声过拟合 book118.com 。	确保策略逻辑在历史上是有效的，但不过度依赖特定参数。
组合式剔除交叉验证 (CPCV)	将数据分成多个块，组合成多个训练集和验证集。在训练集和验证集之间设置“剔除带”，斩断时间维度上的信息泄露，防止模型记住短期模式 csdn.net 。	比传统的时序交叉验证更严格，能更彻底地暴露和防止过拟合。
向前分析 (WFA)	使用滚动窗口，不断在一段历史上训练，在下一段未见过数据上测试，模拟实盘交易过程 arxiv.org 。	最接近实盘的回测方式，能检验策略在不同市场环境下的适应性和稳定性。
样本外测试 (OOS)	在一段完全未用于任何优化的最新数据上测试策略，模拟“实盘”环境。这是最终验收测试 arxiv.org 。	确认策略在最新市场环境下的有效性，防止对最近行情过拟合。

---

## 相关文档

- [okx-sdk-rules.md](./okx-sdk-rules.md) — OKX SDK 使用规范
- [sys-proxy-rules.md](./sys-proxy-rules.md) — 本地代理规范
- [strategy_plan_v2.md](../design/strategy_plan_v2.md) — 清算反弹猎手策略方案
- [2026-06-26-live-echo-runner.md](../design/2026-06-26-live-echo-runner.md) — V3 实盘运行器设计

