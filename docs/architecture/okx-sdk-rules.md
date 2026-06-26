# okx-sdk-rules

## 系统吸引子：统一使用 `python-okx` 官方 SDK

> **强制规则**：所有与 OKX 交易所的交互，必须通过 `python-okx` SDK 实现。禁止在业务脚本中自行封装请求签名、WebSocket 连接管理等底层逻辑。

| 属性          | 值                                      |
| :---------- | :------------------------------------- |
| **PyPI 包名** | `python-okx`                           |
| **安装命令**    | `pip install python-okx`               |
| **官方文档**    | <https://okx.com/docs-v5/>             |
| **源码仓库**    | <https://github.com/okxapi/python-okx> |
| **最低版本**    | `>=0.4.1`                              |

***

## 1. 客户端初始化

### 1.1 统一通过 `src/okx_sdk.py` 获取客户端

所有模块**必须**通过 `src/okx_sdk.py` 提供的工厂方法获取 SDK 客户端，禁止自行 `import okx` 创建实例：

```python
# ✅ 正确：通过项目标准入口获取
from src.okx_sdk import market_api, public_api, trade_api, account_api

client = market_api()

# ❌ 禁止：自行创建 SDK 实例
from okx import MarketData
client = MarketData.MarketAPI()
```

### 1.2 客户端类型

| 函数              | 返回类型                   | 凭证        | 用途                   |
| :-------------- | :--------------------- | :-------- | :------------------- |
| `market_api()`  | `MarketData.MarketAPI` | 无需        | 行情数据（K 线、Ticker、订单簿） |
| `public_api()`  | `PublicData.PublicAPI` | 无需        | 公共信息（合约信息、资金费率）      |
| `trade_api()`   | `Trade.TradeAPI`       | 需 API Key | 下单、撤单、订单查询           |
| `account_api()` | `Account.AccountAPI`   | 需 API Key | 账户余额、持仓、杠杆设置         |
| `funding_api()` | `Funding.FundingAPI`   | 需 API Key | 资金账户（转账、资产查询）        |
| `ws_public()`   | `WsPublicAsync`        | 无需        | 公共 WebSocket 订阅      |
| `ws_private()`  | `WsPrivateAsync`       | 需 API Key | 私有 WebSocket（订单推送）   |

### 1.3 `flag` 参数

SDK 客户端通过 `OKX_FLAG` 环境变量控制交易环境：

| 值     | 含义        | 默认        |
| :---- | :-------- | :-------- |
| `"1"` | 模拟交易（测试网） | ✅ 默认值     |
| `"0"` | 实盘交易      | 确认无误后手动切换 |

> **警告**：所有脚本默认使用模拟盘（`flag="1"`），切换实盘前必须审查代码。

### 1.4 禁止行为

- ❌ 禁止自行拼接 `OK-ACCESS-SIGN`、`OK-ACCESS-TIMESTAMP` 等请求头
- ❌ 禁止基于 `requests`/`aiohttp`/`httpx` 重新封装签名逻辑
- ❌ 禁止绕过 SDK 直接操作底层 HTTP 连接
- ❌ 禁止修改 SDK 源码或 monkey-patch 内部方法

***

## 2. 凭证与代理

### 2.1 凭证管理

| 规则         | 说明                                              |
| :--------- | :---------------------------------------------- |
| **禁止硬编码**  | API Key、Secret Key、Passphrase 不得出现在任何 `.py` 文件中 |
| **环境变量注入** | 通过 `.env` 加载，参见 `src/okx_sdk.py` 实现             |
| **最小权限**   | 仅授予脚本运行所需的最小权限                                  |
| **禁止提币**   | 交易脚本绝不启用提币权限                                    |

### 2.2 代理配置

所有外部请求必须通过本地代理，遵循 `sys-proxy-rules.md`。SDK 客户端已内置代理支持：

```python
# src/okx_sdk.py 内部自动从环境变量读取代理
# 优先级：HTTP_PROXY > HTTPS_PROXY > DEFAULT_PROXY (socks5://127.0.0.1:7897)
def _proxy() -> str | None:
    return os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or DEFAULT_PROXY
```

***

## 3. REST API 使用规范

### 3.1 sync/async 适配

`python-okx` 的 REST API 为同步实现。在 async 上下文中使用 `asyncio.to_thread()` 桥接：

```python
# 同步脚本中直接调用
result = market_api().get_candlesticks(instId="BTC-USDT-SWAP", bar="1m")

# async 上下文中使用 asyncio.to_thread
result = await asyncio.to_thread(
    market_api().get_candlesticks,
    instId="BTC-USDT-SWAP", bar="1m",
)
```

### 3.2 常用方法对照

| 功能     | SDK 方法                                                 |
| :----- | :----------------------------------------------------- |
| K 线数据  | `MarketAPI.get_candlesticks()`                         |
| 历史 K 线 | `MarketAPI.get_history_candlesticks()`                 |
| Ticker | `MarketAPI.get_ticker()` / `get_tickers()`             |
| 订单簿    | `MarketAPI.get_orderbook()`                            |
| 合约信息   | `PublicAPI.get_instruments()`                          |
| 资金费率   | `PublicAPI.get_funding_rate()`                         |
| 资金费率历史 | `PublicAPI.funding_rate_history()`                     |
| 标记价格   | `PublicAPI.get_mark_price()`                           |
| 账户余额   | `AccountAPI.get_account_balance()`                     |
| 持仓查询   | `AccountAPI.get_positions()`                           |
| 设置杠杆   | `AccountAPI.set_leverage()`                            |
| 下单     | `TradeAPI.place_order()`                               |
| 撤单     | `TradeAPI.cancel_order()` / `cancel_multiple_orders()` |
| 查询订单   | `TradeAPI.get_order_list()`                            |
| 成交明细   | `TradeAPI.get_fills()`                                 |
| 转账     | `FundingAPI.funds_transfer()`                          |
| 资金余额   | `FundingAPI.get_balances()`                            |

***

## 4. 下单语义约束

### 4.1 双向持仓模式下的 `reduceOnly`

账户 `posMode="long_short_mode"`（双向持仓）模式下：

| 操作 | `reduceOnly` 要求 | 缺省后果 |
|------|-------------------|----------|
| 平仓 | **必须传 `True`** | 视为新开反向仓 |
| 止损/止盈单 | **必须传 `True`** | 视为新开反向仓 |
| 开仓 | 不传 | — |

> **强制规则**：所有平仓调用（包括 `check_exits` 触发的平仓、SL/TP 触发的平仓）必须携带 `reduceOnly=True`。

### 4.2 SL/TP 挂载与方向校验

**问题**：策略信号直接透传 `stop_price`/`target_price` 到 `slTriggerPx`/`tpTriggerPx`，未按实际成交价做方向校验，触发 `sCode 51053`（触发价方向错误）。

**规则**：

1. **开仓时同步将 SL/TP 提交到交易所**，禁止本地轮询价格被动止损。提交方式二选一：
   - **方式一（原子）**：主单通过 `attachAlgoOrds` 一次性携带 SL/TP。
   - **方式二（市价单）**：主单为市价单时，成交后立即调用 `trade_api().get_fills()` 取实际成交价，再用 `place_algo_order` 独立挂 SL/TP；挂成功前须设置 `sltp_pending` 标志位阻止新开仓。
2. **方向校验**：SL/TP 触发价方向必须与主单方向一致：
   - **做空**：`slTriggerPx > fill_px`（止损在上方），`tpTriggerPx < fill_px`（止盈在下方）
   - **做多**：`slTriggerPx < fill_px`（止损在下方），`tpTriggerPx > fill_px`（止盈在上方）
3. **市价单必须先取成交价再校验**：`fill_px` 来自 `get_fills()`，不得使用信号 `entry_price` 代替。

### 4.3 禁止本地主动止盈止损

**强制规则**：开单时**必须同步**将止盈止损挂载到交易所（通过 `attachAlgoOrds` 或 `place_algo_order`），不得依靠本地轮询价格主动平仓代替 SL/TP。

**理由**：
- 本地轮询存在延迟，极端行情下可能错过止损价位
- 本地进程崩溃时，持仓将无保护裸奔
- 交易所 SL/TP 是服务端撮合，可靠性远高于本地监控

**唯一例外**：`check_exits` 中的**时间止损**（持仓超过 N 小时平仓）属于主动平仓，不在此限制内。

### 4.4 下单函数拆分

| 函数 | 用途 | `reduceOnly` | 可带 SL/TP |
|------|------|--------------|------------|
| `place_market_entry()` | 开仓 | 不传 | ✅ 必须同步挂载 |
| `place_market_close()` | 平仓/止损/止盈 | **强制 `True`** | ❌ 不需要 |

> **禁止**：单个 `place_market_order` 函数同时处理开仓和平仓两种语义，容易误调用。

***

## 5. SDK 缺口处理

当 SDK 未覆盖某个官方 API 端点时，按以下优先级处理：

### 5.1 优先升级 SDK

```bash
pip install --upgrade python-okx
```

### 5.2 使用 SDK 内部请求方法

若升级后仍未覆盖，**必须**通过 SDK 客户端的 `_request()` 方法调用，以复用 SDK 的签名、代理、基础 URL 等能力：

### 5.3 禁止行为

- ❌ 禁止在 SDK 之外自行封装 HTTP 调用
- ❌ 禁止使用 `urllib.request`、`requests`、`aiohttp` 直接请求 OKX 端点（无论是否携带签名）

***

## 6. WebSocket 规范

### 6.1 公共频道

```python
from src.okx_sdk import ws_public

ws = ws_public()
await ws.subscribe([{"channel": "tickers", "instId": "BTC-USDT-SWAP"}])
await ws.start(callback)
```

### 6.2 私有频道

```python
from src.okx_sdk import ws_private

ws = ws_private()
await ws.subscribe([{"channel": "orders", "instType": "SWAP"}])
await ws.start(callback)
```

### 6.3 禁止行为

- ❌ 禁止在 SDK 之外重写 WebSocket 心跳逻辑
- ❌ 禁止在 SDK 之外重写重连逻辑
- ❌ 禁止在 SDK 之外重写订阅恢复逻辑
- ❌ 禁止绕过 SDK 直接使用 `websockets` 库连接 OKX

***

## 7. 审计检查清单

- [ ] 是否使用 `python-okx` SDK 而非自行封装的 HTTP 客户端？
- [ ] SDK 是否保持最新版本？
- [ ] API Key / Secret / Passphrase 是否通过环境变量注入？
- [ ] 是否避免了自行实现签名算法？
- [ ] SDK 缺口是否通过 `_request()` 调用而非 `urllib`/`requests`？
- [ ] WebSocket 是否使用 SDK 的内置机制？
- [ ] 代理配置是否通过 `sys-proxy-rules.md` 规范设置？
- [ ] `flag` 参数是否通过 `OKX_FLAG` 环境变量控制？
- [ ] 平仓/SL/TP 单是否携带 `reduceOnly=True`？
- [ ] SL/TP 触发价方向是否与主单方向一致？
- [ ] 开仓时是否同步挂载 SL/TP 到交易所（不依赖本地监控）？
- [ ] 下单函数是否拆分为 `place_market_entry` / `place_market_close`？

***

## 相关文档

- [sys-proxy-rules.md](./sys-proxy-rules.md) — 统一本地代理规范
- [src/okx\_sdk.py](../../src/okx_sdk.py) — SDK 客户端工厂
- [OKX 官方文档](https://okx.com/docs-v5/)
- [python-okx GitHub 仓库](https://github.com/okxapi/python-okx)

