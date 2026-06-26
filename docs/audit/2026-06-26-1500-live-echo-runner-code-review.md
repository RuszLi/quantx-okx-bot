# Live Echo Runner Code Review 报告

**审查对象 commit：** `d477d23`
**审查日期：** 2026-06-26
**审查人：** AI Reviewer
**审查结论：** **FAIL**

***

## 审查结论说明

存在 1 项 Blocking 问题，必须修复后才能实盘。

根据治理规范，**禁止进入持续实盘模式**。

***

## 1. 设计-实现一致性核对

| 设计文档条目                                           | 实现状态    | 备注                                                 |
| :----------------------------------------------- | :------ | :------------------------------------------------- |
| 架构：startup → main loop → exit                    | ✅ 一致    | <br />                                             |
| 信号管道提取到 `src/paper/pipeline.py`                  | ✅ 一致    | <br />                                             |
| `compute_ensemble_signals()` 函数签名                | ✅ 一致    | 计划文档中拼写为 `compute_ensemble_signants`（typo），实现已修正   |
| 下单参数 `tdMode=cross, posSide=net, ordType=market` | ✅ 一致    | <br />                                             |
| RiskGuard 运行时检查                                  | ⚠️ 部分一致 | 设计文档 6.3 要求 `can_trade()` 检查，`execute_entries` 未调用 |
| 退出条件 stop/target/time                            | ✅ 一致    | 数值与设计一致                                            |
| 持久化 trades.csv / state.json                      | ✅ 一致    | <br />                                             |
| paper\_ensemble 重构引用 pipeline                    | ⚠️ 部分一致 | 仍有本地重复函数                                           |

***

## 2. 逐项发现

### Major

**M1.** **`execute_entries()`** **未调用** **`RiskGuard.can_trade()`**

[run\_live\_echo.py](file:///d:/codes/okx-bot/scripts/run_live_echo.py#L170-L194) `execute_entries` 函数没有在开仓前检查 `risk_guard.can_trade()`。虽然 `run_once` 在信号计算后检查了 `risk_guard.is_halted`，但如果 `check_exits` 中触发了 halt（例如平仓后回撤达标），后续的 `execute_entries` 仍会继续开仓。

**修复：** 在 `execute_entries` 内部或 `run_once` 中 `check_exits` 之后、`execute_entries` 之前增加 `can_trade()` 守卫。

**M2.** **`run_paper_ensemble.py`** **未完全引用 pipeline 共享函数**

[run\_paper\_ensemble.py](file:///d:/codes/okx-bot/scripts/run_paper_ensemble.py#L82-L84) 在本地重新定义了 `load_csv()`，未使用 `pipeline.append_csv()` 和 `pipeline.load_csv()`，而是内联实现了 CSV 追加逻辑（L69-72）。这与设计文档 §8 中"消除重复代码"的目标矛盾。

**M3.** **`run_loop()`** **启动时无条件重置** **`halted`** **状态**

[run\_live\_echo.py](file:///d:/codes/okx-bot/scripts/run_live_echo.py#L237-L239)：

```python
state["halted"] = False
state["halt_reason"] = None
```

如果脚本因风控触发 halted 后崩溃/被杀，重启后 halted 状态被清零。虽然 `RiskGuard` 实例是新建的（内存中不保留历史），但 `state.json` 的 halted 字段被覆盖会丢失审计线索。

**建议：** 启动时读取上一次 halted 状态并打印警告，而非静默覆盖。

**M4.** **`trade_pnl_r`** **语义不匹配**

`check_exits()` 将 `upl`（USDT 绝对值）传入 `risk_guard.update_equity(trade_pnl_r=upl)`。`RiskGuard` 内部用 `>= 0` 判断胜负方向——正负判断正确，但参数名 `trade_pnl_r` 暗示 R-multiple 语义。当前不会导致逻辑错误，但会误导后续维护者。

***

### Minor

**m1.** **`append_trades()`** **重复实现**

[run\_live\_echo.py](file:///d:/codes/okx-bot/scripts/run_live_echo.py#L68-L72) 的 `append_trades()` 与 `pipeline.append_csv()` 逻辑完全相同，可直接复用。

**m2.** **`state.json`** **不记录持仓明细**

重启后虽然能从 OKX `get_positions()` 恢复仓位，但 `state.json` 中没有记录任何持仓信息（哪些 symbol、方向、开仓时间），降低了离线排查能力。

**m3. 日志 emoji 使用不一致**

`run_live_echo.py` 使用了 ✅/❌/⛔/⬅/➡ 等 emoji，`pipeline.py` 和 `run_paper_ensemble.py` 未使用。建议统一。

***

### Question

**Q1. Time Stop 5 小时 vs 1H bar 策略**

策略信号基于 1H K 线，但 time stop 设为 5 小时。这意味着一笔交易最多跨越 5 根 bar。这个数值是如何确定的？是否考虑过与策略持仓周期的匹配性？

**Q2.** **`SYMBOL_MAP`** **24 个 target 是否经过筛选**

$7 权益下大部分 symbol 的 `sz` 计算结果为 0（名义本金不足），实际可交易的可能只有少数几个。是否做过可交易子集筛选？

***

## 3. OKX API 合规核对

| 检查项                            | 结论                             |
| :----------------------------- | :----------------------------- |
| 统一通过 `src/okx_sdk.py` 获取客户端    | ✅ 通过                           |
| `tdMode="cross"` 全仓模式          | ✅ 正确                           |
| `posSide="net"` 净仓模式           | ✅ 正确（SWAP 默认）                  |
| `ordType="market"` 市价单         | ✅ 正确                           |
| 平仓方向：多头 sell / 空头 buy          | ✅ 正确（net 模式反向下单）               |
| `flag` 通过 `OKX_FLAG` 环境变量控制    | ✅ 通过                           |
| 凭证通过环境变量注入                     | ✅ 通过                           |
| `get_equity()` 使用 `totalEq` 字段 | ✅ 正确（`data[0].totalEq` 为账户总权益） |

***

## 4. 验收准则逐项

| #  | 准则                            | 结论                                              |
| :- | :---------------------------- | :---------------------------------------------- |
| 2  | OKX 下单参数经 SDK 文档核验无误          | ✅                                               |
| 3  | 退出条件数值在 $6 权益下具备基本合理性         | ✅                                               |
| 4  | 网络故障和 API 异常不会导致未处理崩溃         | ⚠️ `run_once` 有 try/catch，但 `startup_check` 无保护 |
| 5  | 脚本重启后能从 OKX 查询持仓              | ✅ `get_positions()` 每次从 API 拉取                  |
| 6  | `get_equity()` 字段在所有可用余额场景下有效 | ✅ `totalEq` 覆盖交易+资金账户                           |
| 7  | 已发现问题以 NOTE/FIXME 标注或记录在案     | ❌ 未见标注                                          |
| 8  | 输出审查小结                        | ✅ 本报告                                           |

***

## 5. 修复优先级

1. **\[Major] M1** — `execute_entries` 前增加 `risk_guard.can_trade()` 检查
2. **\[Major] M2** — `run_paper_ensemble.py` 改用 `pipeline.load_csv` / `pipeline.append_csv`
3. **\[Major] M3** — 启动时保留 halted 审计线索
4. **\[Major] M4** — 在 `RiskGuard.update_equity` 调用处添加注释说明 `trade_pnl_r` 此处为 USDT 值

***

## 6. 下一步行动

修复 B1 + M1 后可重新审查。

根据治理规范：

- 审查结论为 FAIL 时，禁止进入持续实盘模式
- 必须修复 Blocking 问题后重新审查
- Major 问题应在下一轮审查前关闭

***

**审查人签字：** AI Reviewer
**审查日期：** 2026-06-26
