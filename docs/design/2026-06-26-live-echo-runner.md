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
| 保证金模式 | `cross` | 全仓，共用 $7 |
| 持仓模式 | `net` | 净仓，OKX SWAP 默认 |
| 杠杆 | 1x | $7 不设杠杆，降低爆仓风险 |

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

```python
# 获取合约信息
ctVal = float(instrument["ctVal"])   # 合约面值（USDT）
lotSz = float(instrument["lotSz"])   # 最小下单量
max_notional = equity * leverage      # 最大名义本金
sz = int(max_notional / ctVal)
sz = max(sz, int(lotSz))             # 不低于最小 lot
```

若 `sz < lotSz`，则该合约跳过（$7 不足以交易）。

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
