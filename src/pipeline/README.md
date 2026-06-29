# Edge Discovery Pipeline（自动化 edge 发现管道）

> 本文档对应 `docs/plans/2026-06-28-1000-strategy-v3.2-automated-edge-discovery-pipeline.md`。
> 当前仓库已完成 Phase 4～6 的最小可运行实现：funding 家族支持 dry-run 与 full-run，validator / promoter / graveyard 已接通；多家族扩展与独立结案审计仍在后续范围内。

---

## 1. 模块概述

### 核心模块（`src/pipeline/`）

| 模块 | 职责 |
|------|------|
| `candidate.py` | 候选信号/策略的声明结构。包含 `Candidate` 数据类，记录 ID、信号族（signal family）、参数快照、数据依赖、假设陈述。 |
| `search_space.py` | 参数搜索空间定义与采样。提供笛卡尔积（grid）、随机采样（random）和贝叶斯优化（预留）接口。每个信号族暴露默认网格。 |
| `validator.py` | 验证引擎。实现 IS gate（快速过滤）、CPCV（组合交叉验证）、WFA（walk-forward 分析）、DSR（多重测试校正）、PBO（回测过拟合概率）评估。 |
| `promoter.py` | 晋升器。对通过全部闸口的候选生成策略档案文档，自动注册到 `src/backtest/strategies/__init__.py` 和 V3 编排器配置，触发回归测试更新。 |
| `graveyard.py` | 墓地。对未通过候选生成结构化"死亡记录"（negative evidence），存入 `docs/strategies/`，阶段标记为 `rejected`。 |
| `_strategy_artifacts.py` | 策略模块、策略文档、注册表与索引写入工具。 |
| `data_layer.py` | 统一数据接口。封装 klines、funding rate、open interest（OI）、order book snapshot、liquidation 等免费数据的批量获取与本地 parquet 缓存。 |
| `executor.py` | 执行器。接收候选列表，调用现有回测引擎（`simulate()` 或 V3 编排器），输出 trades + summary，再喂给 validator。 |

### 生成器子包（`generators/`）

共 5 个信号族生成器，每个暴露 `generate(params: dict) -> Strategy` 接口：

| 文件 | 信号族 | 示例参数 |
|------|--------|----------|
| `funding_generator.py` | Funding（资金费率）族 | regime 分位数、z-score 阈值、R/R 比 |
| `oi_generator.py` | OI（未平仓量）族 | OI-price divergence 窗口、OI 变化率阈值 |
| `orderbook_generator.py` | Order Book（订单簿）族 | OBI 深度档位、spread change 阈值 |
| `calendar_generator.py` | Calendar（日历）族 | day-of-week、month、funding-time proximity |
| `liquidation_generator.py` | Liquidation（清算）族 | 清算簇邻近度、瀑布预测窗口 |

生成器返回的对象满足 `Strategy` Protocol（见第 3 节），可直接送入 executor 进行回测。

---

## 2. 输入/输出契约

| 模块 | 输入 | 输出 |
|------|------|------|
| `candidate.py` | 无（数据类定义） | `Candidate` 实例：`candidate_id`、`family`、`params`、`strategy_class`、`hypothesis` |
| `search_space.py` | 信号族名称、搜索模式（grid/random）、可选边界 | 参数迭代器 / `dict` 列表，每项为 `{param_name: value}` |
| `generators/*.py` | `params: dict`，数据依赖项 | 满足 `Strategy` Protocol 的类或类引用 |
| `executor.py` | `Candidate` 列表、训练数据窗口 | `pd.DataFrame`（trades）、`dict`（summary 指标） |
| `validator.py` | trades DataFrame + summary + 参数路径 | `Verdict`：`PASS / REPARAM / ABORT` + 原因 + 统计证据 |
| `promoter.py` | PASS 候选（含通过验证的 trades/summary） | `src/backtest/strategies/<id>.py`、`docs/strategies/<id>.md`、`__init__.py` 增量、编排器配置增量 |
| `graveyard.py` | ABORT 候选（含失败原因） | `docs/strategies/<id>.md`（阶段=rejected），策略索引更新 |
| `data_layer.py` | 数据种类、symbol、时间范围 | 对齐的 `pd.DataFrame`（UTC 时间戳索引，含 `point_in_time` 标记列） |

---

## 3. 与 Strategy Protocol 的对接

管道生成的候选策略最终必须满足 `src/backtest/strategies/base.py` 中定义的 `Strategy` Protocol：

```python
class Strategy(Protocol):
    config: StrategyConfig          # 名称、杠杆、风险R、交易品种范围
    def compute_signals(market_data, external_events) -> pd.DataFrame: ...
    def required_data() -> dict[str, list[str]]: ...
```

- 每个 generator 的 `generate(params)` 返回的类或实例必须实现以上接口。
- `required_data()` 的返回值决定 executor 在回测前需要从 `data_layer.py` 加载哪些数据。
- `StrategyConfig` 中的 `metadata` 字段用于携带 signal family、param hash 等管道元信息，供 promoter/graveyard 审计。

---

## 4. 与 V3 编排器的对接

管道通过 `scripts/run_v3_phase0_backtest.py` 中现有的 `StrategyRunConfig` 机制驱动回测：

- executor 将候选包装为 `StrategyRunConfig`，调用编排器的批量回测逻辑。
- 敏感性网格（time_stop × fee_mult × slippage_mult 的 3×3×3 组合）复用编排器的网格生成逻辑。
- **训练/holdout 窗口**：管道内部固定训练窗口默认 `2024-01-01 至 2025-01-01（不含）`，holdout 窗口固定 `2025-01-01 至今`。外部 `--end` 参数仅控制训练数据终点，不可覆盖 holdout 窗口。

---

## 5. 数据流

一个候选的完整生命周期：

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
validator.py ── IS gate → CPCV → DSR → holdout → Verdict
    │
    ├── PASS ──→ promoter.py ──→ 文档生成 + 自动注册
    │
    └── ABORT ─→ graveyard.py ──→ 死亡记录归档
        (REPARAM → 返回 search_space 重新采样)
```

- IS gate 作为快速过滤器，淘汰明显不可用的候选（WR < 0.45、EV < 0.15R、PF < 1.3、max_consec_losses > 6）。
- CPCV 使用 `n_groups=8, n_test_groups=2, embargo_pct=0.01, label_horizon=5`。
- PBO 阈值 ≤ 0.40，fraction-positive ≥ 0.65。
- DSR p-value ≤ 0.05。
- WFA 作为增强证据，不单独阻塞晋升。
- REPARAM 候选重新进入搜索空间进行下一轮参数调整。

---

## 6. 自动注册安全规则

晋升器（promoter）在以下条件下才会修改注册文件和编排器配置：

1. **仅在 validator 返回 PASS 后**执行注册。任何 REPARAM 或 ABORT 候选不触发注册逻辑。
2. **回归测试门**：注册前运行 `python -m pytest src/backtest/tests/test_v3_phase0_exit_alignment.py -v`，该测试必须通过。若测试失败，promoter 中止并输出错误原因，不提交任何文件修改。
3. **增量修改**：`promoter.py` 在 `src/backtest/strategies/__init__.py` 的 `STRATEGIES` 字典和 `__all__` 列表中追加新条目，不删除或重写现有条目。V3 编排器配置同理。
4. **审计痕迹**：每次自动注册在 `docs/logs/` 生成一条日志记录，包含候选 ID、注册时间戳、通过的验证门列表、触发测试的 SHA。
5. **当前实现状态**：本轮已验证 ABORT 路径会生成 rejected 档案与索引；PASS 路径已有自动生成代码，并且注册前会执行 `src/backtest/tests/test_v3_phase0_exit_alignment.py` 回归测试门，但尚未有真实 PASS 样本。

> 参考：`docs/plans/2026-06-28-1000-strategy-v3.2-automated-edge-discovery-pipeline.md` §1.4 决策 D3。

---

## 7. 验证命令

```bash
# 1. 确认包结构存在
python -c "import pipeline; print(pipeline.__file__)"

# 2. 模块可导入（空占位阶段不报语法错误）
python -c "from pipeline.candidate import Candidate; print('OK')"

# 3. 现有回归测试不退化
python -m pytest src/backtest/tests/ -v

# 4. 管道 dry-run
python scripts/run_edge_discovery_pipeline.py --families funding,oi --dry-run

# 5. 管道 full-run（当前只支持 funding 家族）
python scripts/run_edge_discovery_pipeline.py --families funding --mode random --n-samples 2 --start 2026-06-12 --end 2026-06-24 --out-dir reports/pipeline_output/manual_full_run

# 6. 包结构测试
python -m pytest src/pipeline/tests/ -v
```

---

*本文件随管道实现进展持续更新。下一阶段：补齐非 funding 家族的 full-run 数据装配，并在出现首个 PASS 候选后验证自动注册路径的真实运行证据。*
