# Live Echo Runner — V3 实盘最小运行器设计

> **版本：** v1
> **日期：** 2026-06-26
> **状态：** 设计定稿

---

## 1. 背景与目标

V3 Phase 0 已完成回测验证，策略 C（Beta Decouple）和 D（Weekend Wick）在回测中表现为正期望。当前 paper runner 已能通过 OKX SDK 获取实时 kline 并计算 ensemble 信号。

**目标：** 以 $7 最小权益在 OKX 主网上运行策略 C/D 的 ensemble 信号，实现最小可行的实盘下单、持仓跟踪、退出管理全链路。

**约束条件：**

- 无模拟盘过渡
- 复用现有策略计算代码
- 通过 OKX SDK 下单（`python-okx`）
- 所有外网请求通过本地代理 `http://127.0.0.1:7890`

**非目标：**

- 不做 WebSocket 订阅
- 不做部分成交处理
- 不做滑点保护
- 不做收益归因分析

---

## 2. 整体架构

```
scripts/run_live_echo.py
├── startup 阶段
│   ├── 验证 OKX 连接（get_account_balance）
│   ├── 检查权益 >= $7
│   ├── 获取可交易合约列表（get_instruments）
│   └── 过滤 sz_min * ctVal <= max_notional 的 symbol
│
├── main loop (periodic_poll, 60s)
│   ├── fetch_and_compute_signals()
│   │   ├── 获取 1h kline
│   │   ├── 构造 C/D 特征数据
│   │   ├── strategy_c.compute_signals()
│   │   ├── strategy_d.compute_signals()
│   │   └── ensemble.resolve_conflicts()
│   │
│   ├── execute_entry_signals()
│   │   ├── RiskGuard.can_trade() 检查
│   │   └── trade_api().place_order() × N
│   │
│   ├── manage_positions()
│   │   ├── account_api().get_positions()
│   │   └── stop / target / time 退出条件判断
│   │
│   └── persist_state()
│       ├── trades.csv 追加
│       └── state.json 更新
│
└── exit 阶段
    ├── 输出运行摘要
    └── 如有开放仓位，打印警告
```

---

## 3. 信号管道

策略计算逻辑沿用现有实现，提取为共享模块 `src/paper/pipeline.py`：

| 函数 | 来源 | 说明 |
|------|------|------|
| `fetch_1h_candles(inst_id)` | 从 paper_ensemble 提取 | 带重试的 kline 获取 |
| `build_c_market_data(kline)` | 从 paper_ensemble 提取 | Beta Decouple 特征构造 |
| `build_d_market_data(kline)` | 从 paper_ensemble 提取 | Weekend Wick 特征构造 |
| `validate_symbols(inst_ids)` | 从 paper_ensemble 提取 | OKX 合约存在性校验 |
| `compute_ensemble_signals(inst_ids)` | **新增** | 完整管道一键调用 |
| `OKX_INST_IDS` | 从 paper_ensemble 提取 | 24 个 target symbol 列表 |

`compute_ensemble_signals()` 封装完整流程：获取 kline → 构造特征 → 策略 C/D 分别计算 → ensemble 冲突消解 → 返回信号 DataFrame。

### 信号输出格式

| 字段 | 类型 | 说明 |
|------|------|------|
| `symbol` | str | SOL-USDT-SWAP 格式 |
| `edge` | str | "C" 或 "D" |
| `signal` | int | 1=long, -1=short |
| `entry_price` | float | 当前市价（最新 close） |
| `direction_label` | str | "long" / "short" |
| `weight` | float | ensemble 权重 |

---

## 4. 下单执行

### 4.1 下单参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 订单类型 | `market` | 市价单，最小实现 |
| 保证金模式 | `cross` | 全仓，共用账户权益 |
| 持仓模式 | `long_short_mode` | 双向持仓，实测账户配置为 `long_short_mode`（开仓须带 `posSide=long/short`） |
| 交易所杠杆 | **每合约最大值** | 见 §4.5；解耦于真实敞口 |
| 名义敞口 | **权益 × `NOTIONAL_MULTIPLE`** | 见 §4.5；`NOTIONAL_MULTIPLE=10` |

> **2026-06-26 修订**：原 §4.1 记录"持仓模式 net / 杠杆 1x"，与实测账户配置（`long_short_mode`）及小资金可开仓约束冲突。持仓模式修订见复盘文档偏差 1；杠杆与仓位计算修订见 §4.5。

### 4.2 开仓

```python
trade_api().place_order(
    instId=inst_id,
    tdMode="cross",
    side="buy" if signal == 1 else "sell",
    posSide="net",
    ordType="market",
    sz=str(sz)
)
```

### 4.3 平仓

在 net 模式下，平仓即朝反方向开仓（OKX 自动减少净头寸）：

```python
trade_api().place_order(
    instId=inst_id,
    tdMode="cross",
    side="sell" if pos > 0 else "buy",
    posSide="net",
    ordType="market",
    sz=str(abs(pos))
)
```

### 4.4 仓位大小计算

仓位大小由**目标名义敞口**驱动，且必须考虑当前价格（单张名义 = `ctVal × price`）：

```python
# 获取合约信息
ct_val = float(instrument["ctVal"])   # 合约面值（基础币数量）
lot_sz = float(instrument["lotSz"])   # 最小下单步长
min_sz = float(instrument["minSz"])   # 最小下单量

target_notional = equity * NOTIONAL_MULTIPLE   # 目标名义敞口（USDT）
raw_sz = target_notional / (ct_val * price)     # 价格感知
sz = floor(raw_sz / lot_sz) * lot_sz            # 向下对齐到 lotSz 网格
# sz < min_sz 则跳过该合约
```

若 `sz < minSz`，则该合约跳过（资金不足以达到最小下单量）。

> **2026-06-26 修订（关键）**：原实现 `sz = int(max_notional / ctVal)` **忽略价格**，导致同一 `sz` 在不同币种代表的真实敞口相差悬殊（如 SOL `sz=2` ≈ $137，SUI `sz=2` ≈ $1.35）。在 1x + $3.66 权益下，高价合约名义远超权益，OKX 报 `51008 Insufficient USDT margin`。同时 `int(lotSz)` 会把 SOL 的 `lotSz=0.01` 截断为 0。本次改为价格感知 + lotSz 网格对齐，见 §4.5。

### 4.5 杠杆与名义敞口治理（不可漂移）

本运行器将**两个独立概念**显式解耦，禁止再用单一常量同时表达二者：

| 概念 | 取值 | 控制变量 | 作用 |
|------|------|---------|------|
| 交易所杠杆 | 每个合约 `instruments.lever` 字段的**最大值**（如 SOL=100x，多数=50x） | `setup_leverage` 按合约设置 | 降低保证金占用，让小资金能开出仓位 |
| 真实名义敞口 | 权益 × `NOTIONAL_MULTIPLE`（当前 `=10`） | `compute_sz` | 控制实际风险敞口 |

**决策依据：**

- 账户权益极小（~$3.66）。若交易所杠杆设为 1x，高价合约（SOL/AVAX/LINK）的单笔最小名义即超过权益，保证金不足无法开仓。
- 将交易所杠杆设为合约最大值后，保证金占用降到几美分级别，所有目标合约均可开仓；真实敞口仍由 `NOTIONAL_MULTIPLE` 独立、统一地约束。
- `NOTIONAL_MULTIPLE=10`：每笔目标名义 ≈ 权益 × 10（当前 ≈ $35），保证金占用 $0.35–0.70/笔，远低于权益。

**禁止漂移：** 不得退回 `MAX_LEVERAGE=1` 这种"杠杆=仓位倍数"的单常量模型。修改 `NOTIONAL_MULTIPLE` 即修改真实风险敞口，须同步更新本节并记录依据。代码常量与注释见 `scripts/run_live_echo.py` 顶部 `NOTIONAL_MULTIPLE`。

### 4.6 同时持仓上限（集中而非分散）

| 概念 | 取值 | 控制变量 | 作用 |
|------|------|---------|------|
| 同时持仓数 | `MAX_CONCURRENT_POSITIONS`（当前 `=2`） | `execute_entries` 按 `score` 降序取 top-N，已有持仓计入名额 | 集中下注，避免手续费与相关性侵蚀小资金 |

**决策依据（目标：小资金快速复利，非风控视角）：**

- **手续费侵蚀**：OKX taker ≈ 0.05%，一次 round-trip（开 + SL/TP 平）≈ 名义 × 0.1%。$35 名义 × 多仓，全开 16 仓单轮手续费 ≈ $0.56 ≈ 总资金 15%；集中 1–2 仓则 ≈ 1–2%。这是决定性因素。
- **相关性使"分散"失效**：SOL/AVAX/LINK/OP/INJ/SUI 等高度随 BTC 同向。16 个同向 alt 仓位不是 16 个独立下注，而是 1 个 beta 下注付 16 倍手续费；逆行时全部同时亏损、共用同一 cross 保证金池，反而更易一起爆仓。
- **保证金名额**：每仓需 ~$0.35–0.70 保证金，$3.66 权益无法支撑全开，多余信号必然报 `51008`。
- **取舍**：top-2 若恰为一多一空，相关 beta 部分对冲，接近市场中性配对；纯同向 top-N 仅是手续费倍增的 beta。N=2 在"集中"与"保留一次对冲可能"间取平衡。

**信号排序**：`compute_ensemble_signals` 已产出 `score`（z-score 极端度 + R:R + 紧止损）。注意 `resolve_conflicts` 会按 `entry_ts/priority` 重排，故 `execute_entries` 取 top-N 前须显式按 `score` 降序还原。

**禁止漂移**：不得回退到"每个信号都开仓"的无上限模型。修改 `MAX_CONCURRENT_POSITIONS` 须同步更新本节并记录依据。代码常量与注释见 `scripts/run_live_echo.py` 顶部 `MAX_CONCURRENT_POSITIONS`。

---

## 5. 持仓管理与退出

### 5.1 持仓数据源

通过 `account_api().get_positions()` 轮询获取：

| 字段 | 类型 | 说明 |
|------|------|------|
| `instId` | str | 合约 ID |
| `pos` | str | 持仓张数（正=多，负=空） |
| `upl` | str | 未实现盈亏（USDT） |
| `avgPx` | str | 开仓均价 |
| `cTime` | str | 开仓时间戳（ms） |
| `lever` | str | 杠杆倍数 |

### 5.2 退出条件

| 条件 | 阈值 | 触发动作 |
|------|------|---------|
| Stop Loss | `upl <= -0.21`（ -3% of $7） | 市价单平仓 |
| Take Profit | `upl >= +0.42`（ +6% of $7） | 市价单平仓 |
| Time Stop | 持仓 > 5 小时 | 市价单平仓 |

**顺序：** 每轮循环先检查已有持仓的退出条件，再处理新信号的开仓。

### 5.3 平仓后处理

- 从 `account_api().get_account_balance()` 获取最新权益
- 调用 `RiskGuard.update_equity(new_equity, trade_pnl_r)`
- 若 `RiskGuard.is_halted`，脚本退出

---

## 6. 风控

### 6.1 RiskGuard 参数

| 参数 | 值 | $7 等价 |
|------|-----|---------|
| 最大回撤 | 15% | $1.05 |
| 最大连续亏损 | 3 笔 | - |
| 每日最大交易 | 5 笔 | - |

### 6.2 启动前检查

- `account_api().get_account_balance()` 返回 `totalEq >= 7.0`
- `_flag() == "0"`，打印醒目警告
- 可交易合约数量 > 0

### 6.3 运行时防护

- 同 symbol 已有持仓时，不重复开仓
- 信号与当前持仓同向时跳过（不加仓）
- 信号为空或 RiskGuard 触发时跳过整轮

---

## 7. 持久化

### trades.csv

```
timestamp,symbol,action,price,sz,pnl,reason
2026-06-26T10:00:00Z,SOL-USDT-SWAP,enter_long,142.50,3,0.0,ensemble_signal
2026-06-26T12:30:00Z,SOL-USDT-SWAP,exit_long,145.20,3,2.70,take_profit
```

### state.json

```json
{
  "session_start": "2026-06-26T10:00:00Z",
  "cycle_count": 42,
  "total_trades": 5,
  "peak_equity": 7.42,
  "halted": false,
  "halt_reason": null
}
```

---

## 8. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/paper/pipeline.py` | **新建** | 共享信号管道（~100 行） |
| `scripts/run_paper_ensemble.py` | **重构** | 导入 pipeline.py，消除重复代码 |
| `scripts/run_live_echo.py` | **新建** | 实盘最小运行器（~200 行） |
| `src/live/risk_guard.py` | **不改** | 现有风控，接口不变 |

数据文件（自动创建）：

| 路径 | 说明 |
|------|------|
| `data/live_echo/trades.csv` | 交易流水 |
| `data/live_echo/state.json` | 运行状态 |

---

## 9. 风险声明

- $7 为最小测试金额，即使全部损失也在可控范围
- 直接上 OKX 主网（`flag=0`），无模拟盘过渡
- 市价单无滑点保护，小资金（1-3 张）下影响有限
- 若 OKX API 异常（网络、限频、凭证失效），脚本打印错误后继续下一轮
- 脚本无驻留进程守护，重启后依赖 OKX 持仓数据恢复状态
