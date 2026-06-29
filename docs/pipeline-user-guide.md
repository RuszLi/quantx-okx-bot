# V3.2 自动化 Edge Discovery Pipeline — 使用指南

## 概述

Edge Discovery Pipeline 是一条从假设生成、信号搜索、回测验证到晋升/淘汰的自动化管道。它替代了 V3.1 的手工逐条试错模式，能够批量生成候选策略、执行参数网格搜索，并通过统计验证门（IS Gate → CPCV → DSR → Holdout）自动判定策略的可用性。

## 当前状态 — v0.2（funding 家族 MVP 已交付）

| 模块 | 完成度 | 说明 |
|------|--------|------|
| `src/pipeline/` 包结构 | 100% | 8 核心模块 + 5 生成器 + 契约文档 |
| `search_space.py` | 100% | Grid / Random 搜索 |
| `funding_generator.py` | 100% | 8 维参数化的 funding-switch 策略生成器 |
| `data_layer.py` | 100% | 统一数据接口（klines / funding / OI / liq） |
| `protocol.py` | 100% | 验证协议常数（IS gate / CPCV / DSR / PBO） |
| `validator.py` | 100% | IS gate、CPCV、WFA、DSR、holdout verdict 已落地 |
| `executor.py` | 100% | 单候选回测、summary、敏感性网格与 robustness 评级已落地 |
| `promoter.py` / `graveyard.py` | 100% | PASS 候选晋升、ABORT 候选归档、策略索引更新已落地 |
| 入口脚本 `run_edge_discovery_pipeline.py` | 100% | dry-run 与 non-dry-run 均已验证 |

## 快速开始

### 环境要求

- Python 3.11+
- 依赖：激活项目 `venv` 后执行 `pip install -r requirements.txt`

### Dry-Run 模式

列出候选策略配置，不运行回测：

```bash
# Funding 族，grid 搜索
python scripts/run_edge_discovery_pipeline.py --families funding --mode grid --dry-run

# 指定输出目录
python scripts/run_edge_discovery_pipeline.py --families funding --mode random --n-samples 20 --dry-run --out-dir reports/my_first_run
```

**输出：**
- `reports/pipeline_output/<run_id>/candidates.csv` — 所有候选配置（含 ID、参数快照）
- `reports/pipeline_output/<run_id>/dry_run_report.md` — 人类可读的汇总报告

### 预期输出示例

```bash
python scripts/run_edge_discovery_pipeline.py --families funding --mode grid --dry-run
# → 生成 11,664 个候选
# → candidates.csv 11,664 行 × 4 列
# → dry_run_report.md: 汇总表 + 前 5 个候选样本 + 完整模式说明
```

## 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--families` | str | `"funding"` | 逗号分隔的信号族名称（当前仅 `funding` 可用） |
| `--mode` | str | `"grid"` | 搜索模式：`grid`（笛卡尔积）或 `random`（随机采样） |
| `--n-samples` | int | 10 | random 模式的采样数量 |
| `--start` | str | `"2024-01-01"` | 训练窗口起始日期 |
| `--end` | str | `"2025-01-01"` | 训练窗口结束日期（不含） |
| `--dry-run` | flag | — | 仅生成候选列表，跳过回测与验证 |
| `--out-dir` | str | auto | 输出目录（自动生成时在 `reports/pipeline_output/` 下） |

> **注意：** holdout 窗口固定为 `2025-01-01` 至今，不可通过 CLI 覆盖（参见方案 §1.2）。

### Full Pipeline 模式

执行候选生成、回测、验证和归档：

```bash
# Funding 族，小样本 random 搜索
python scripts/run_edge_discovery_pipeline.py --families funding --mode random --n-samples 2 --start 2026-06-12 --end 2026-06-24 --out-dir reports/pipeline_output/my_full_run
```

**输出：**
- `reports/pipeline_output/<run_id>/candidates.csv` — 候选列表
- `reports/pipeline_output/<run_id>/results.csv` — 候选 verdict（判定结果）与原因
- `reports/pipeline_output/<run_id>/promoted/` — PASS 候选档案副本
- `reports/pipeline_output/<run_id>/rejected/` — ABORT / REPARAM 候选档案副本

当前仓库中已验证的真实产物路径：

- `reports/pipeline_output/ulw_dry_run/`
- `reports/pipeline_output/ulw_full_run/`
- `reports/pipeline_output/ulw_full_run_two/`

## 架构概览

```
信号族选择（families.py）
    │
    ▼
search_space.py ── 参数网格 / 随机采样
    │
    ▼
generators/*.py ── generate(params) → Strategy 类
    │
    ▼
executor.py ── 调用回测引擎 → trades + summary
    │
    ▼
validator.py ── IS gate → CPCV → DSR → Holdout → Verdict
    │
    ├── PASS ──→ promoter.py ──→ 文档生成 + 自动注册
    │
    └── ABORT ─→ graveyard.py ──→ 死亡记录归档
        (REPARAM → 返回参数搜索重新采样)
```

**当前可用的数据流：** 信号族 → 参数搜索 → 候选生成 → 回测执行 → validator 判定 → promoter / graveyard 归档，已经能在 funding 族上端到端运行。

## 文件结构

```
src/pipeline/
├── __init__.py         包入口，导出核心符号
├── README.md           模块边界与 I/O 契约文档
├── candidate.py        候选数据结构
├── protocol.py         验证协议常数
├── families.py         5 族信号注册表
├── search_space.py     参数搜索空间
├── data_layer.py       统一数据接口
├── executor.py         回测执行器（已实现）
├── validator.py        验证引擎（已实现）
├── promoter.py         自动晋升器（已实现）
├── graveyard.py        死亡记录归档（已实现）
├── _strategy_artifacts.py 策略模块 / 文档 / 注册表写入工具
├── generators/
│   ├── base.py         生成器 Protocol + 抽象基类
│   ├── funding_generator.py  参数化 funding 生成器（✅ 可用）
│   ├── oi_generator.py        OI 生成器（占位）
│   ├── orderbook_generator.py Orderbook 生成器（占位）
│   ├── calendar_generator.py  Calendar 生成器（占位）
│   └── liquidation_generator.py 清算生成器（占位）
└── tests/
    ├── __init__.py
    ├── test_protocol.py  验证协议常数测试
    ├── test_families.py  信号族注册表测试
    └── test_structure.py 包结构测试

scripts/
└── run_edge_discovery_pipeline.py  入口脚本（✅ 可用）
```

## 扩展指南：添加新的信号族

1. 在 `src/pipeline/families.py` 的 `FAMILY_REGISTRY` 中添加新族条目
2. 在 `src/pipeline/generators/` 下创建生成器，继承 `AbstractSignalGenerator`
3. 实现 `generate(params) -> Strategy`（返回满足 `Strategy` Protocol 的类）
4. 在 `scripts/run_edge_discovery_pipeline.py` 的 `_get_generator()` 注册表中添加映射
5. 若要支持 full-run，补齐 `_load_market_bundle()` 所需的数据装配逻辑

## 验证命令

```bash
# Pipeline 全部测试
python -m pytest src/pipeline/tests/ -v

# 现有回归测试（当前基线：65 PASS / 4 预存失败）
python -m pytest src/backtest/tests/ -v

# Dry-run
python scripts/run_edge_discovery_pipeline.py --families funding --mode random --n-samples 1 --dry-run --out-dir reports/pipeline_output/manual_dry_run

# Full-run
python scripts/run_edge_discovery_pipeline.py --families funding --mode random --n-samples 2 --start 2026-06-12 --end 2026-06-24 --out-dir reports/pipeline_output/manual_full_run
```

## 当前限制

- 当前 full-run 仅支持 `funding` 家族；`oi / orderbook / calendar / liquidation` 仍停留在生成器占位阶段。
- `promoter.py` 目前会为 PASS 候选生成策略模块、注册表条目和策略文档，但本次真实运行样本全部落入 ABORT，因此尚无 PASS 证据。
- `src/backtest/tests/` 仍有 4 个预存失败：`test_live_runner.py`、`test_pre_funding_unwind_strategy.py`、`test_run_strategy_mode.py`、`test_state_machine.py`，与本次 pipeline 交付无关。
- 活动计划的总体状态仍由 `docs/plans/2026-06-28-1000-strategy-v3.2-automated-edge-discovery-pipeline.md` 管理；本轮交付完成的是 Phase 4～6 的 funding 家族切片，不代表多家族扩展与独立结案审计已经完成。

## 后续路线图

| 里程碑 | 预计会话 | 关键交付 |
|--------|----------|----------|
| Phase 7 — 多家族接线 | 后续 | `oi / orderbook / calendar / liquidation` 数据装配与 full-run |
| Phase 8 — PASS 候选晋升 | 后续 | 产出首个 PASS 候选并触发 paper/live 新计划 |
| 独立关闭审计 | 当前会话内 | Reviewer gate + 关闭计划 |
