# 特性：Live Echo Runner Code Review

## 目的

对本轮会话（2026-06-26）交付的 Live Echo Runner 全链路进行正式 Code Review。
涵盖方案设计（设计文档）、代码实现、风险暴露三个层面，发现阻断性问题与可改进
点，为进入持续实盘运行提供质量门禁。

## 范围内

### 审查对象

| 文件 | 职责 |
|------|------|
| `docs/design/2026-06-26-live-echo-runner.md` | 设计方案 |
| `docs/plans/2026-06-26-live-echo-implementation.md` | 实施计划 |
| `src/paper/pipeline.py` | 共享信号管道 |
| `scripts/run_paper_ensemble.py` | 纸交易运行器（重构版） |
| `scripts/run_live_echo.py` | 实盘运行器 |

### 审查维度

1. **架构正确性** — 设计方案与实现是否一致，抽象边界是否合理
2. **OKX API 合规** — 下单参数（`tdMode`、`posSide`、`ordType`）是否正确，
   是否符合 [okx-sdk-rules.md](../architecture/okx-sdk-rules.md)
3. **风险控制** — `RiskGuard` 参数是否能在 $6.24 权益下有效保护账户，退出
   条件（stop/target/time）是否合理
4. **错误处理** — 网络故障、API 异常、空数据等场景是否有兜底
5. **状态恢复** — 脚本重启后能否从 OKX 重建仓位状态，state.json 是否完备
6. **权益（Equity）计算** — `get_equity()` 是否正确读取 OKX 响应字段
7. **滑动/延迟影响** — 市价单在 $6.24 小资金下是否可能产生意外行为
8. **代码质量** — 命名、结构、冗余、可维护性

## 范围外

- 策略因子本身（Beta Decouple / Weekend Wick）的逻辑正确性（已在 V3 Phase 0
  验证）
- `RiskGuard` 单元测试覆盖度
- `okx_sdk.py` 层连接池与代理稳定性
- Paper 运行器的持续运行可靠性（不阻断实盘）
- 日志轮转与磁盘空间管理
- 运维监控告警

## 主要审查流程

1. 阅读设计文档，对照实现代码逐项核对
2. 逐文件阅读实现代码，标注每项发现
3. 分类标注严重程度：
   - **Blocking** — 可能导致资金损失或无法恢复的错误，必须修复后才能实盘
   - **Major** — 可能在特定条件下产生问题，建议修复
   - **Minor** — 代码风格、命名、注释等非功能性建议
   - **Question** — 需作者确认的行为或意图
4. 输出审查小结，给出审查结论：
   - PASS — 无 Blocking 问题，可进入持续实盘
   - PASS-WITH-NOTES — 无 Blocking，但建议修复指定 Major 项
   - FAIL — 存在 Blocking 问题，需修复后重新审查

## 业务规则

- 审查结论为 FAIL 时，禁止进入持续实盘模式
- 审查结论为 PASS-WITH-NOTES 时，Major 项应在下一轮审查前关闭
- OKX API 调用参数不得与官方文档或 SDK 约束矛盾
- `RiskGuard` 触发后不得自动重置，必须人工介入
- `OKX_FLAG=0` 下单即产生真实资金变动，审查必须覆盖

## 角色与权限

| 角色 | 职责 |
|------|------|
| 审查人（Reviewer） | 逐项检查代码，输出审查结论 |
| 作者（Author） | 解答审查人的 Question，修复 Blocking / Major 问题 |
| 决策人（Decider） | 基于审查结论决定是否进入持续实盘 |

本轮会话中，三者均为同一人（PM）。

## 边缘情况

- OKX 账户余额在运行中被外部提现或充值
- `get_positions()` 返回空但 state.json 中有未清理的持仓记录
- `place_order()` 成功但 `get_positions()` 后续轮询未立即反映（延迟）
- 市价单实际成交价与 `entry_price`（信号中的 close 价）存在偏差
- 多笔信号针对同一 symbol 先后触发（当前已跳过，但需确认逻辑覆盖）
- 脚本进程被 kill 后，state.json 可能处于写入中间状态

## 未解决问题

- 实盘退出时用 `trade_pnl_r=upl` 传入 `RiskGuard.update_equity()`，但 `upl`
  是绝对 USDT 值而非 R-multiple，`RiskGuard` 内部用 `>= 0` 判断盈亏方向。
  当前不会导致逻辑错误（正负判断正确），但语义不准确。
- `compute_ensemble_signals()` 内部创建独立的 `RiskGuard` 实例，与
  `run_live_echo.py` 主循环的 `RiskGuard` 实例不同。前者仅用于防 ensemble
  级联挂起，后者用于实盘风控。两者关系需要在审查中确认是否清晰。

## 验收准则

- [ ] 设计文档与实现代码之间无矛盾
- [ ] OKX 下单参数（`tdMode`、`posSide`、`ordType`、`side`）经 SDK 文档核验无误
- [ ] 退出条件数值（stop loss / take profit / time stop）在 $6 权益下具备基本合理性
- [ ] 网络故障和 API 异常场景不会导致未处理的崩溃
- [ ] 脚本重启后能从 OKX 查询持仓而非仅依赖本地 state.json
- [ ] `get_equity()` 使用的 OKX 响应字段在所有可用余额场景下有效
- [ ] 已发现的问题全部以 `# NOTE:` 或 `# FIXME:` 形式标注或记录在案
- [ ] 输出审查小结，包含 PASS / PASS-WITH-NOTES / FAIL 结论
