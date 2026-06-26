# Bug: 信号选择偏向 universe 中靠前的 symbol

**日期**: 2026-06-26  
**严重性**: 高  
**影响范围**: 实盘交易信号选择

## 问题描述

实盘运行时，系统总是选择 SOL-USDT-SWAP 开仓，即使其他 symbol 也有有效信号。

日志显示每轮都尝试为 SOL 挂载 SL/TP 订单，导致交易所返回 400 Bad Request。

## 根因分析

### 1. 信号生成逻辑缺陷

`src/backtest/strategies/beta_decouple.py` 的 `compute_signals` 方法遍历所有历史 bar（96 根 K 线），为每个满足条件的 bar 都生成信号：

```python
for idx in range(5, len(frame)):  # 遍历所有历史 bar
    # 如果满足条件，生成信号
    signals.append({...})
```

这导致每个 symbol 可能产生多个历史信号。

### 2. 信号选择逻辑缺陷

`src/paper/pipeline.py` 的 `compute_ensemble_signals` 将所有 symbol 的信号合并后，按 `entry_ts` 和 `priority` 分组：

```python
ranked = ranked.sort_values(["entry_ts", "priority"], ascending=[True, False])
for _, group in ranked.groupby(["entry_ts", "symbol"], sort=False):
    winners.append(group.iloc[0])
```

问题：
- SOL 排在 `OKX_INST_IDS` 第一个
- SOL 的历史信号最多（因为遍历所有 bar）
- 当多个 symbol 在同一时间戳有信号时，SOL 的信号总是被优先选中

### 3. 缺少信号质量评分

信号没有质量评分机制，无法区分"强信号"和"弱信号"。所有满足 `abs(z) >= 2.0` 的信号被视为等价。

## 修复方案

### 1. 只取最新 bar 的信号

修改 `beta_decouple.py`，从最新 bar 向前遍历，找到第一个满足条件的 bar 后立即返回：

```python
for idx in range(len(frame) - 1, 4, -1):  # 从最新到最旧
    # 如果满足条件，生成信号
    signals.append({...})
    break  # 只取最新一根
```

### 2. 添加信号质量评分

在 `pipeline.py` 中添加 `_compute_signal_score` 函数，从三个维度评估信号质量：

1. **z-score 绝对值**（权重 10）：越大越极端，信号越强
2. **止损距离百分比**（权重 -100）：越小越好，风险更可控
3. **风险收益比**（权重 5）：TP/SL 距离比，越高越好

```python
def _compute_signal_score(signal_row, current_price):
    score = 0.0
    # 1. z-score 贡献
    alt_z = signal_row.get("alt_z", 0)
    if not pd.isna(alt_z):
        score += abs(alt_z) * 10
    
    # 2. 止损距离百分比
    sl_distance_pct = abs(entry_price - stop_price) / entry_price
    score -= sl_distance_pct * 100
    
    # 3. 风险收益比
    rr_ratio = tp_distance / sl_distance
    score += rr_ratio * 5
    
    return score
```

### 3. 按 score 降序排序

在 `resolve_conflicts` 之前，按 `score` 降序排序：

```python
all_raw = all_raw.sort_values("score", ascending=False)
result = ensemble.resolve_conflicts(all_raw, available_equity=equity)
```

## 验证方法

1. 运行 `scripts/run_live_echo.py`，观察日志
2. 检查是否每轮都选择不同的 symbol（而非总是 SOL）
3. 检查信号日志中是否显示 `score` 字段
4. 确认交易所不再返回 400 Bad Request

## 预防措施

1. **信号生成时避免历史堆积**：只生成最新 bar 的信号，或为每个信号添加 `valid_until_ts` 过期时间
2. **信号选择时引入质量评分**：避免随机选择或按固定顺序选择
3. **定期审计信号分布**：统计每个 symbol 被选中的频率，检查是否存在偏向

## 相关文件

- `src/backtest/strategies/beta_decouple.py`
- `src/backtest/strategies/weekend_wick.py`
- `src/paper/pipeline.py`
- `scripts/run_live_echo.py`
