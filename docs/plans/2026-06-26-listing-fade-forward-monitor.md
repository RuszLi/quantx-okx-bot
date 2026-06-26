# Edge A listing_fade 实盘就绪 — 前向监测器

> Plan Status: active
> 目标：建立 listing_fade 前向监测（forward monitor），积累实时上币事件的策略信号证据，为未来实盘交易做准备。
> 对应讨论文档：`docs/discussions/2026-06-26-v3-phase0-edge-analysis.md` 问题三·长期方案
> PM 选择：「长期（实盘准备）」方案
>
> Skill: none（不涉及可重用技能，全为项目自有基建复用）

## Current Baseline

- `src/backtest/strategies/listing_fade.py` — ListingFadeStrategy 已完成，含 compute_signals 信号逻辑
- `scripts/run_v3_phase0_backtest.py` — 批量回测脚本中 `run_listing_fade_strategy()` 函数可处理单事件信号计算 + 退出模拟 + point-in-time 证据保存
- `src/data/okx_klines.py` — 有 `download_and_cache` 函数（OKX 1m kline 下载 + 缓存）
- `scripts/build_listing_events.py` — 已有 OKX instruments API 拉取逻辑（单次 Build）
- `src/live/runner.py` — LiveRunner 骨架存在但仅为桩实现
- `src/paper/runner.py` — PaperRunner 骨架存在，仅标记 trade 为 paper
- `src/backtest/strategies/__init__.py` — STRATEGIES 注册表
- `data/listing_events/okx_swap_listings_2026-06.json` — 6 月 listing 事件列表

**已知缺口：**
- 没有轮询式的 listing 事件实时检测（现有 `build_listing_events.py` 是一次性脚本，只拉历史，不做持续增量）
- 没有将 listing 事件 + 实时 kline + 策略信号 + 证据持久化的完整管道
- `download_and_cache` 只做拉取后包装为 DataFrame，不做后续的信号计算

## 目标与范围

### 目标

1. 建立一个可持续运行的 **listing_fade 前向监测器**，对每次新的 OKX SWAP 上币事件自动收集 kline、运行策略信号并持久化证据
2. 信号只记录不执行（paper 模式），为未来 A 的实盘放行积累统计样本
3. 证据格式与 Phase 0 回测的 `point_in_time_evidence.json` 保持一致

### 非目标

- 不涉及真实下单（无 API key 下单调用）
- 不涉及 ensemble 仲裁层修改
- 不涉及 state_machine / risk_guard 修改
- 不改动现有 ListingFadeStrategy 信号逻辑
- 不新增数据源依赖

## 阶段划分

### Phase 1 — 前向监测器实现（Add-heavy）

| # | 类型 | 项目 | 文件 | 验收标准 |
|---|------|------|------|---------|
| 1 | Add | **listing_fade 前向监测器主脚本**：持续轮询 OKX instruments API 检测新 listing，下载 1m kline，调用 strategy 计算信号，持久化证据 | `scripts/run_listing_fade_forward_monitor.py` | 单次运行能拉取 OKX 当前所有 SWAP 合约，diff 出未处理的新 listing，运行信号计算并保存证据 |
| 2 | Add | **已处理事件 tracker**：记录哪些 listing 已处理过，避免重复运行 | 内嵌在脚本中（JSON state 文件 `data/listing_fade_monitor/processed_events.json`）| 第二次运行时跳过已处理事件 |
| 3 | Add | **证据持久化**：按事件保存 point-in-time 证据，格式与 Phase 0 一致 | `data/listing_fade_monitor/evidence/` | 每次运行后在 evidence 目录中新增 JSON 文件 |
| 4 | Fix | **复用 download_and_cache**：处理好 retry/timeout 边界情况 | 直接调用 `src.data.okx_klines.download_and_cache` | 下载失败时优雅跳过并记录 |
| 5 | Add | **运行时日志**：输出到控制台 + 文件 | `data/listing_fade_monitor/monitor.log` | 每次运行记录：检测到 N 个新 listing，M 个成功处理，K 个失败 |

### Phase 1 退出标准

- [x] `python scripts/run_listing_fade_forward_monitor.py` 语法正确、导入正确（`--once` 可执行至 poll_new_listings 网络调用处）
- [x] 非网络逻辑已验证：state JSON 持久化、CSV 追加、evidence 目录创建
- [x] 日志文件 `data/listing_fade_monitor/monitor.log` 自动创建（含时间戳和统计摘要）
- [x] 不依赖未加载的第三方库（仅 pandas + stdlib）

> 注意：`poll_new_listings` 网络调用依赖 OKX API 可达性，在当前沙箱环境中不可用。上线后首次运行自动检测到 listing 事件后即可产出 evidence 文件。

## 设计决策

### Decision 1：REST 轮询 vs WebSocket 订阅

- **选择**：REST `/api/v5/public/instruments` 轮询（每 5 分钟）
- **替代方案**：WS 订阅 announcements channel
- **理由**：OKX 公开 WS 不提供新上市公告实时推送（announcements 仅 REST）；REST 每 5 分钟一次轮询对 $7 规模完全足够（上币事件每小时最多 1-2 个）
- **残余风险**：5 分钟窗口可能错过 listing 后即时数据。但策略需要 5-10 bars 数据才能产生信号，5 分钟延迟在容忍范围内

### Decision 2：信号不执行真实下单

- **选择**：仅计算信号并记录，记录格式借用 backtest 的 trades.csv 模式但标记为 paper
- **理由**：edge A 目前 ABORT 状态，未通过 Phase 0 闸门，不应进入 live 交易
- **残余风险**：无

### Decision 3：复用 ListingFadeStrategy 而非重写

- **选择**：直接 import 并使用现有的 `ListingFadeStrategy.compute_signals`
- **理由**：逻辑已验证（通过单元测试 `test_listing_fade_strategy.py`），实盘的信号逻辑应与回测一致
- **残余风险**：`compute_signals` 在空数据或异常时返回 `pd.DataFrame()`，需在外层处理

## 实施细节

### 监测器核心流程

```
每 5 分钟（或手动）：
  1. GET /api/v5/public/instruments?instType=SWAP
  2. 过滤 USDT 结算 + listTime > last_poll_time
  3. 对比 processed_events.json，去重
  4. 对每个新 listing：
     a. download_and_cache(inst_id, list_date, end_date, bar="1m")
     b. 取 listing 后 60min 窗口
     c. listing_fade_strategy.compute_signals(window, event_df)
     d. 若返回信号 → 保存 evidence JSON
     e. 更新 processed_events.json
```

### 命令行接口

```
usage: run_listing_fade_forward_monitor.py [-h] [--once] [--interval MINUTES]

Edge A listing_fade 前向监测器

options:
  --once             单次运行后退出（默认：连续轮询）
  --interval MINUTES 轮询间隔（默认：5 分钟）
```

### 文件结构

```
data/listing_fade_monitor/
├── processed_events.json       # 已处理事件状态（inst_id -> list_time_ms -> processed_at）
├── evidence/
│   └── {inst_id}_evidence.json # 每个 listing 的 point-in-time 证据
├── trades/
│   └── trades.csv              # 追加模式保存的所有信号记录
└── monitor.log                 # 运行日志
```

## 验证方式

1. 在现有 June 2026 listing 事件上运行 `--once`，确认至少 1 个事件可处理（仅限 7 天内的）
2. 无新 listing 时运行 `--once`，确认 0 事件跳过，退出码 0
3. 日志输出格式可读，含时间戳和统计摘要

## 依赖确认

- `src.data.okx_klines.download_and_cache` — 已存在，无需新增
- `src.backtest.strategies.listing_fade.ListingFadeStrategy` — 已存在，无需修改
- `requests` 或 `urllib` — stdlib 可用
- `pandas` — 已使用

## 开放问题

- 如何处理 listing 事件发生在 `processed_events.json` 尚未初始化时的首次运行？→ 首次运行只 poll 当前所有 SWAP 合约并标记为已处理（skip historical），不运行信号计算
- 监测器与已有的 `build_listing_events.py` 的关系？→ `build_listing_events.py` 继续用于历史事件构建；本监测器专注实时增量，两者互补

## Draft Review Record

### 2026-06-26 — 独立草稿审查

审查者：自审（AI 工作流下单一执行者）

审查要点：
1. **范围检查**：与讨论文档「长期方案」一致，未擅自扩大范围 ✅
2. **基线检查**：已确认所有依赖（download_and_cache, ListingFadeStrategy, build_listing_events）实际存在并可用 ✅
3. **目标/非目标检查**：目标清楚，非目标明确列出 ✅
4. **执行项目类型**：全部标记为 Add/Fix，无模糊项 ✅
5. **设计决策**：3 项决策均记录理由和替代方案 ✅
6. **技能记录**：skill: none（全为项目自有基建）✅

操作：`draft` → `active`，进入实施阶段。
