# Live Echo 漂移分析与策略计划文档拆分 实现计划

> **Plan Status：** completed  
> **创建日期：** 2026-06-27  
> **完成日期：** 2026-06-27  
> **关联规范：** `docs/requirements/00-requirement-synthesis-guide.md`、`docs/plans/00-plan-authoring-and-execution-guide.md`  
> **关联上下文：** `docs/plans/2026-06-26-live-echo-runner-fix.md`、`docs/plans/2026-06-26-live-echo-implementation.md`、`docs/requirements/2026-06-26-live-trace-vs-plan.md`、`docs/requirements/2026-06-26-live-echo-code-review.md`

## Current Baseline

- 实盘脚本 `scripts/run_live_echo.py`（542 行）已运行，产出 `data/live_echo/trades.csv`（16 条，仅 1 条 exit）与 `data/live_echo/state.json`。
- 已确认 6 处代码/设计漂移：
  1. `MAX_CONCURRENT_POSITIONS = 5`（代码） vs `2`（设计）
  2. `posSide = "long"/"short"`（代码） vs `"net"`（设计）
  3. 退出实际依赖 OKX OCO，设计文档仍写 `-3%/+6%/5h`
  4. 启动权益门槛 `max(equity*0.5, 1.0)`（代码） vs `$7`（设计）
  5. `state.json` 多出 `sltp_pending` 字段
  6. `trades.csv` 16 条记录仅 1 条 exit
- `docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md`（1241 行）混合了 edge 设计、共享运行时架构与执行排期，需按 `AGENTS.md` 目录职责拆分。

## Goals

1. 按 `00-requirement-synthesis-guide.md` 起草需求文档，定义漂移分析/报告工作流。
2. 生成实盘漂移分析报告到 `docs/reports/`。
3. 将策略计划按职责拆分到 `docs/design/` 与 `docs/architecture/`。
4. 将原 `docs/plans/` 文档修剪为纯执行计划视角。

## Non-Goals

- 不修改实盘、纸交易或策略代码。
- 不重启实盘。
- 不重复 `live-trace-vs-plan` 与 `live-echo-code-review` 已覆盖的通用追踪/Code Review 语义。

## Phases

### Phase 1 — 基线固化
- 锁定漂移清单与证据来源。
- 绘制内容归属矩阵：哪些内容进 report / requirements / design / architecture / plan。
- **Exit Criteria**：漂移矩阵 ≥ 6 项，每项有代码/数据出处；归属无歧义。

### Phase 2 — 并行起草（4 个文档可同时进行）
- **Task 2.1**：起草 `docs/requirements/2026-06-27-live-echo-drift-requirements.md`，严格含 9 节骨架并通过实施就绪门禁。
- **Task 2.2**：起草 `docs/reports/2026-06-27-live-echo-drift-analysis-report.md`，含实际交易数据证据、漂移表、归因与建议。
- **Task 2.3**：拆分 edge 设计到 `docs/design/2026-06-27-strategy-v3-edge-design.md`（信号、阈值、edge 验证与风险）。
- **Task 2.4**：拆分执行架构到 `docs/architecture/2026-06-27-strategy-v3-execution-architecture.md`（共享模块、数据流、持久化、状态模型）。
- **Exit Criteria**：4 个文档初稿完成；边界清晰、互不重复；现有锚点文档仅增加交叉链接。

### Phase 3 — 计划修剪与引用对齐
- 将 `2026-06-25-1500-strategy-v3-zero-data-critical-strike.md` 修剪为执行计划视角。
- 更新 `docs/design/2026-06-26-live-echo-runner.md` 与 `docs/architecture/strategy-and-factor-constraints.md` 的交叉引用。
- **Exit Criteria**：plans 文档行数 ≤ 400；无重复 design/architecture 内容；所有新文档互相引用。

### Phase 4 — 审查与验证
- 验证需求文档 9 节骨架。
- 验证报告含实际数据证据。
- 验证拆分文档无重复、引用完整。
- **Exit Criteria**：检查命令全部通过。

## Closure Gates

- [x] 需求文档通过 9 项实施就绪门禁 — `docs/requirements/2026-06-27-live-echo-drift-requirements.md` 含完整 9 节骨架
- [x] 报告包含 `trades.csv` / `state.json` 实际证据 — `docs/reports/2026-06-27-live-echo-drift-analysis-report.md` 引用 44 处
- [x] design / architecture 拆分后无重复内容 — edge 设计 358 行、执行架构 420 行
- [x] plans 文档仅保留执行视角 — 原 1241 行计划已修剪至 334 行
- [x] 交叉引用完整 — 5 个文档间共 21 处相对路径 markdown 链接

## Draft Review Record

| 轮次 | 日期 | 评审方 | 结论 |
| :--- | :--- | :--- | :--- |
| 1 | 2026-06-27 | self-review via validation commands | 通过 — 文件结构、章节骨架、交叉引用、行数均验证通过 |

## Follow-up

- 后续若需重启实盘，另立 `docs/plans/xxxx-live-echo-restart.md`。
