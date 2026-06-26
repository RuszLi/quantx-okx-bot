# OKX SDK 迁移实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将所有自定义 HTTP 实现的 OKX API 调用迁移至官方 `python-okx` SDK（v0.4.1），消除手动签名、自建 WebSocket 管理等底层逻辑。

**架构：** 创建 `src/okx_sdk.py` 集中管理 SDK 客户端初始化与凭证注入；各模块直接调用 SDK 方法（同步调用走 `asyncio.to_thread` 适配到 async 上下文）；WebSocket 切换为 SDK 内置的 `WsPublicAsync`/`WsPrivateAsync`。

**技术栈：** `python-okx==0.4.1`，同步 REST 在 async 上下文用 `asyncio.to_thread()` 桥接

---

## 当前基线

### 待迁移文件清单

| # | 文件 | 当前方案 | SDK 方法 |
|---|------|----------|----------|
| G1 | `src/okx_client.py` | `aiohttp` + 手动 HMAC-SHA256 签名 + 自建 WS | 整体替换 |
| G2 | `src/main.py` | 依赖 `OKXClient` | 改用 SDK |
| G3 | `src/strategy.py` | 通过 `self.client` 调用 `place_order`/`cancel_all_orders` | 保持接口兼容 |
| G4 | `src/test_order.py` | 依赖 `OKXClient` | 改用 SDK |
| G5 | `src/check_balance.py` | 依赖 `OKXClient` + 直接 `_rest_request` | 改用 SDK |
| D1 | `src/data/okx_klines.py` | `urllib.request` → `/market/candles` | `MarketAPI.get_candlesticks()` |
| D2 | `src/data/okx_funding.py` | `urllib.request` → `/public/funding-rate-history` | `PublicAPI.funding_rate_history()` |
| D3 | `src/data/okx_oi.py` | `urllib.request` → `/rubik/stat/contracts/open-interest-history` | ⚠️ SDK 未覆盖（见下方说明） |
| D4 | `src/data/okx_announcements.py` | `urllib.request` → `/support/announcements` | ⚠️ SDK 未覆盖（见下方说明） |
| R1 | `src/reports/okx_public_probe.py` | `urllib.request` → `/public/instruments` + `/market/candles` | `PublicAPI.get_instruments()` + `MarketAPI.get_candlesticks()` |
| S1 | `scripts/probe_okx_endpoints.py` | `urllib.request` → 10 个公共端点 | 各自 SDK 方法 |
| S2 | `scripts/probe_okx_depth.py` | `urllib.request` + `httpx` | `PublicAPI.get_instruments()` + `MarketAPI.get_history_candlesticks()` |
| S3 | `scripts/probe_execution_feasibility.py` | `httpx` → `/instruments`, `/tickers`, `/books` | `PublicAPI.get_instruments()` + `MarketAPI.get_tickers()` + `MarketAPI.get_orderbook()` |
| S4 | `scripts/build_listing_events.py` | `urllib.request` → `/public/instruments` | `PublicAPI.get_instruments()` |
| S5 | `scripts/run_paper_ensemble.py` | `urllib.request` → `/market/candles` | `MarketAPI.get_candlesticks()` |
| S6 | `scripts/run_listing_fade_forward_monitor.py` | `urllib.request` → `/public/instruments` | `PublicAPI.get_instruments()` |
| T1 | `src/backtest/tests/test_okx_public_probe_fetchers.py` | monkeypatch `urllib.request.urlopen` | 需改为 SDK mock 测试 |

### SDK 覆盖缺口

以下端点 `python-okx` v0.4.1 未提供 SDK 方法，**保持现状**并在迁移完成后提交 GitHub issue：

- `/api/v5/rubik/stat/contracts/open-interest-history` — `okx_oi.py` 使用
- `/api/v5/support/announcements` — `okx_announcements.py` 使用
- 这些文件仅迁移其中由 SDK 覆盖的部分，未覆盖端点通过 SDK 的通用 `_request()` 方法调用（不自行实现签名/HTTP）

### SDK 同步/async 适配策略

`python-okx` 的 REST API 为**同步**实现，WebSocket 为**async**实现。适配规则：

| 上下文 | 方案 |
|--------|------|
| 脚本/数据模块（同步） | 直接调用 SDK 方法 |
| async 交易代码 | 使用 `asyncio.to_thread()` 包装 SDK 同步调用 |
| WebSocket | 使用 `WsPublicAsync`/`WsPrivateAsync` |

---

## 任务分解

### 任务 1：创建 SDK 初始化模块 `src/okx_sdk.py`

**文件：**
- 创建：`src/okx_sdk.py`
- 修改：`.env`（不修改，但读取 `OKX_FLAG`）

**职责：** 集中管理 SDK 客户端创建、凭证注入、代理配置，不封装业务逻辑。

- [ ] **步骤 1：编写 `src/okx_sdk.py`**

```python
"""OKX SDK 客户端初始化与生命周期管理.

提供统一的 SDK 客户端工厂方法，禁止各业务模块自行创建客户端。
REST API 为同步调用，async 上下文中使用 asyncio.to_thread 桥接。
"""
from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Any

from dotenv import load_dotenv
from okx import Account, MarketData, PublicData, Trade
from okx.websocket import WsPrivateAsync, WsPublicAsync

load_dotenv()


def _proxy() -> str | None:
    return os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or None


def _flag() -> str:
    return os.environ.get("OKX_FLAG", "1")


def _api_key() -> str:
    return os.environ.get("OKX_API_KEY", "")


def _api_secret() -> str:
    return os.environ.get("OKX_API_SECRET", "")


def _passphrase() -> str:
    return os.environ.get("OKX_PASSPHRASE", "")


def _creds() -> tuple[str, str, str]:
    return _api_key(), _api_secret(), _passphrase()


# --- 公共数据客户端（无需凭证） ---

def market_api() -> MarketData.MarketAPI:
    proxy = _proxy()
    if proxy:
        return MarketData.MarketAPI(proxy=proxy)
    return MarketData.MarketAPI()


def public_api() -> PublicData.PublicAPI:
    proxy = _proxy()
    if proxy:
        return PublicData.PublicAPI(proxy=proxy)
    return PublicData.PublicAPI()


# --- 鉴权客户端（需凭证） ---

def trade_api() -> Trade.TradeAPI:
    key, secret, phrase = _creds()
    proxy = _proxy()
    return Trade.TradeAPI(
        api_key=key, api_secret_key=secret,
        passphrase=phrase, flag=_flag(),
        proxy=proxy,
    )


def account_api() -> Account.AccountAPI:
    key, secret, phrase = _creds()
    proxy = _proxy()
    return Account.AccountAPI(
        api_key=key, api_secret_key=secret,
        passphrase=phrase, flag=_flag(),
        proxy=proxy,
    )


# --- async 桥接（用于 async 上下文调用同步 SDK） ---

async def async_market_api() -> MarketData.MarketAPI:
    return await asyncio.to_thread(market_api)


async def async_public_api() -> PublicData.PublicAPI:
    return await asyncio.to_thread(public_api)


async def async_trade_api() -> Trade.TradeAPI:
    return await asyncio.to_thread(trade_api)


async def async_account_api() -> Account.AccountAPI:
    return await asyncio.to_thread(account_api)


def call_sync[T](func, *args, **kwargs) -> T:
    """在 async 上下文中执行同步 SDK 调用.

    使用: result = await call_sync(client.get_account_balance, ccy="USDT")
    """
    return asyncio.to_thread(partial(func, *args, **kwargs))


async def call_in_thread[T](fn, *args, **kwargs) -> T:
    """在独立线程中执行同步 SDK 调用."""
    return await asyncio.to_thread(partial(fn, *args, **kwargs))


# --- WebSocket（原生 async） ---

def ws_public() -> WsPublicAsync:
    proxy = _proxy()
    url = os.environ.get(
        "OKX_WS_PUBLIC_URL",
        "wss://ws.okx.com:8443/ws/v5/public"
    )
    return WsPublicAsync(url)


def ws_private() -> WsPrivateAsync:
    key, secret, phrase = _creds()
    proxy = _proxy()
    url = os.environ.get(
        "OKX_WS_PRIVATE_URL",
        "wss://ws.okx.com:8443/ws/v5/private"
    )
    return WsPrivateAsync(
        apiKey=key, passphrase=phrase, secretKey=secret,
        url=url,
    )
```

- [ ] **步骤 2：验证导入与编译**

运行：`python -c "from src.okx_sdk import market_api, public_api, trade_api, account_api, ws_public, ws_private; print('OK')"`

---

### 任务 2：迁移 `src/data/okx_klines.py` → SDK

**文件：**
- 修改：`src/data/okx_klines.py`
- 测试：`test_download.py`

- [ ] **步骤 1：重构 `_http_get` 替换为 SDK 调用**

修改 `fetch_candle_page` 和 `fetch_candles_range`，用 `MarketAPI.get_candlesticks()` 替换 `urllib.request`。

```python
from src.okx_sdk import market_api


def _get_candlesticks(
    inst_id: str,
    bar: str = "1m",
    limit: int = 300,
    after: int | None = None,
) -> list[list[str]]:
    params: dict[str, object] = {"instId": inst_id, "bar": bar, "limit": limit}
    if after is not None:
        params["after"] = after
    client = market_api()
    result = client.get_candlesticks(**params)
    if result.get("code") == "0":
        return result.get("data") or []
    return []


def fetch_candle_page(
    inst_id: str,
    bar: str = "1m",
    limit: int = 300,
    after: int | None = None,
) -> pd.DataFrame:
    rows = _get_candlesticks(inst_id, bar=bar, limit=limit, after=after)
    return candle_rows_to_frame(rows)


def fetch_candles_range(
    inst_id: str,
    start: date,
    end: date,
    bar: str = "1m",
    limit: int = 300,
    delay: float = RATE_LIMIT_SEC,
) -> pd.DataFrame:
    # same body as before, just calling fetch_candle_page (now SDK-backed)
    ...
```

- [ ] **步骤 2：删除不再需要的导入**

删除文件顶部的 `import urllib.parse`, `import urllib.request`, `OKX_BASE` 常量。

- [ ] **步骤 3：验证同步调用**

运行：`python -c "from src.data.okx_klines import fetch_candle_page; print(fetch_candle_page('BTC-USDT-SWAP').shape)"`

预期：输出 `(n, 7)` 其中 n > 0

---

### 任务 3：迁移 `src/data/okx_funding.py` → SDK

**文件：**
- 修改：`src/data/okx_funding.py`

- [ ] **步骤 1：替换 `_http_get_json` 为 SDK 调用**

```python
from src.okx_sdk import public_api


def fetch_funding_history(inst_id: str, limit: int = 100, timeout: float = 15.0) -> pd.DataFrame:
    client = public_api()
    result = client.funding_rate_history(instId=inst_id, limit=limit)
    rows = result.get("data") or []
    # ...rest of the function unchanged
```

- [ ] **步骤 2：删除 `urllib.parse`, `urllib.request`, `OKX_BASE_URL`**

- [ ] **步骤 3：验证**

运行：`python -c "from src.data.okx_funding import fetch_funding_history; print(fetch_funding_history('BTC-USDT-SWAP').shape)"`

---

### 任务 4：处理 `src/data/okx_oi.py`（SDK 缺口）

**文件：**
- 修改：`src/data/okx_oi.py`

**说明：** `/api/v5/rubik/stat/contracts/open-interest-history` 不在 SDK 中。保持当前 `_http_get_json` 实现，但通过 SDK 的通用 `_request` 方法调用，不自建签名/HTTP。

- [ ] **步骤 1：保持现状，添加 `# TODO: submit python-okx issue for rubik OI history endpoint` 注释**

无需修改代码，仅添加注释标记缺口。

---

### 任务 5：处理 `src/data/okx_announcements.py`（SDK 缺口）

**文件：**
- 修改：`src/data/okx_announcements.py`

**说明：** `/api/v5/support/announcements` 不在 SDK 中。同样保持现状+标记。

- [ ] **步骤 1：添加注释标记缺口**

---

### 任务 6：迁移 `src/okx_client.py` + 交易路由

**文件：**
- 修改：`src/okx_client.py`（重写，保留接口兼容性）
- 修改：`src/main.py`（改用 SDK）
- 修改：`src/strategy.py`（`self.client` 接口保持不变，底层已换）
- 修改：`src/test_order.py`（改用 SDK）
- 修改：`src/check_balance.py`（改用 SDK）

- [ ] **步骤 1：重写 `src/okx_client.py`**

将 OKXClient 改为基于 SDK 的实现，保留对外的 `place_order`, `cancel_all_orders`, `subscribe`, `start`, `stop`, `get_tickers`, `get_all_instruments`, `get_account_balance`, `set_leverage`, `get_positions` 等接口。

```python
"""OKX 客户端 — 基于 python-okx SDK 实现.

保持对外接口兼容性，底层已替换为官方 SDK。
"""
import asyncio
import json
import logging
from typing import Callable

from okx.websocket import WsPrivateAsync, WsPublicAsync

from src.okx_sdk import account_api, market_api, public_api, trade_api

logger = logging.getLogger(__name__)


class OKXClient:
    def __init__(self, api_key: str = "", api_secret: str = "",
                 passphrase: str = "", use_proxy: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase

        self.callbacks: dict[str, Callable] = {}
        self.msg_queue: asyncio.Queue = asyncio.Queue()
        self.worker_task = None
        self.public_ws = None
        self.private_ws = None

        # SDK 客户端（懒初始化）
        self._market_api = None
        self._public_api = None
        self._trade_api = None
        self._account_api = None

    def _lazy_market(self):
        if self._market_api is None:
            self._market_api = market_api()
        return self._market_api

    def _lazy_public(self):
        if self._public_api is None:
            self._public_api = public_api()
        return self._public_api

    def _lazy_trade(self):
        if self._trade_api is None:
            self._trade_api = trade_api()
        return self._trade_api

    def _lazy_account(self):
        if self._account_api is None:
            self._account_api = account_api()
        return self._account_api

    async def get_tickers(self, instType: str = "SWAP") -> list:
        result = await asyncio.to_thread(
            self._lazy_market().get_tickers, instType=instType)
        if result.get("code") == "0":
            return result.get("data") or []
        logger.error(f"get_tickers failed: {result}")
        return []

    async def get_all_instruments(self, instType: str = "SWAP") -> list:
        result = await asyncio.to_thread(
            self._lazy_public().get_instruments, instType=instType)
        if result.get("code") == "0":
            return result.get("data") or []
        logger.error(f"get_all_instruments failed: {result}")
        return []

    async def get_account_balance(self, ccy: str = "USDT") -> float:
        result = await asyncio.to_thread(
            self._lazy_account().get_account_balance)
        if result.get("code") == "0":
            for detail in result.get("data", [{}])[0].get("details", []):
                if detail["ccy"] == ccy:
                    return float(detail.get("availBal", 0))
        logger.error(f"get_account_balance failed: {result}")
        return 0.0

    async def set_leverage(self, instId: str, lever: int,
                           mgnMode: str = "cross",
                           posSide: str = "long") -> bool:
        result = await asyncio.to_thread(
            self._lazy_account().set_leverage,
            instId=instId, lever=str(lever),
            mgnMode=mgnMode, posSide=posSide)
        if result.get("code") == "0":
            return True
        logger.error(f"set_leverage failed: {result}")
        return False

    async def get_positions(self, instType: str = "SWAP") -> list:
        result = await asyncio.to_thread(
            self._lazy_account().get_positions, instType=instType)
        if result.get("code") == "0":
            return [p for p in result.get("data", [])
                    if float(p.get("pos", "0")) != 0]
        logger.error(f"get_positions failed: {result}")
        return []

    async def place_order(self, instId: str, side: str, sz: str,
                          ordType: str = "market", px: str = "",
                          posSide: str = "", slTriggerPx: str = "",
                          slOrdPx: str = "", tpTriggerPx: str = "",
                          tpOrdPx: str = "", tdMode: str = "cross"):
        """使用 SDK TradeAPI.place_order 下单."""
        params = {
            "instId": instId, "tdMode": tdMode,
            "side": side, "ordType": ordType, "sz": sz,
        }
        if posSide:
            params["posSide"] = posSide
        if ordType in ("limit", "post_only") and px:
            params["px"] = px
        if slTriggerPx or tpTriggerPx:
            algo = {}
            if slTriggerPx:
                algo["slTriggerPx"] = slTriggerPx
                algo["slTriggerPxType"] = "last"
                algo["slOrdPx"] = slOrdPx or "-1"
            if tpTriggerPx:
                algo["tpTriggerPx"] = tpTriggerPx
                algo["tpTriggerPxType"] = "last"
                algo["tpOrdPx"] = tpOrdPx or "-1"
            params["attachAlgoOrds"] = [algo]

        logger.warning(f"🚀 PLACING {ordType.upper()} ORDER (SDK): "
                       f"{side} {sz} {instId}")
        result = await asyncio.to_thread(
            self._lazy_trade().place_order, **params)
        if result.get("code") == "0":
            logger.info(f"✅ Order placed via SDK: {result}")
        else:
            logger.error(f"❌ Order failed via SDK: {result}")
            if "order_error" in self.callbacks:
                self.msg_queue.put_nowait(("order_error", "GLOBAL"))

    async def cancel_all_orders(self, instId: str):
        """撤销该合约的所有挂单."""
        result = await asyncio.to_thread(
            self._lazy_trade().get_order_list,
            instId=instId, state="live")
        if result.get("code") != "0":
            return
        orders = result.get("data") or []
        if not orders:
            return
        ids = [{"instId": instId, "ordId": o["ordId"]} for o in orders]
        cancel_res = await asyncio.to_thread(
            self._lazy_trade().cancel_multiple_orders, ids)
        logger.info(f"cancel_all_orders response: {cancel_res}")

    async def subscribe(self, channels: list[dict], callback: Callable):
        """使用 SDK WebSocket 订阅."""
        for ch in channels:
            self.callbacks[ch["channel"]] = callback
        if self.public_ws:
            await self.public_ws.subscribe(channels)

    async def start(self):
        self.worker_task = asyncio.create_task(self._process_ws_messages())

        # 使用 SDK WebSocket
        self.public_ws = WsPublicAsync(
            "wss://ws.okx.com:8443/ws/v5/public")
        self.public_ws_coro = asyncio.create_task(
            self.public_ws.start(self._ws_callback))

        if self.api_key:
            self.private_ws = WsPrivateAsync(
                apiKey=self.api_key, passphrase=self.passphrase,
                secretKey=self.api_secret,
                url="wss://ws.okx.com:8443/ws/v5/private")
            self.private_ws_coro = asyncio.create_task(
                self.private_ws.start(self._ws_callback))

    async def _ws_callback(self, data):
        """SDK WebSocket 回调分发."""
        if "arg" in data and "channel" in data["arg"]:
            channel = data["arg"]["channel"]
            if channel in self.callbacks:
                self.msg_queue.put_nowait((channel, data))
        # Handle order events
        if "arg" in data and data["arg"].get("channel") == "orders":
            if "orders" in self.callbacks:
                self.msg_queue.put_nowait(("orders", data))

    async def _process_ws_messages(self):
        """Worker: 队列分发."""
        import asyncio
        while True:
            try:
                channel, data = await self.msg_queue.get()
                if channel in self.callbacks:
                    await self.callbacks[channel](data)
                self.msg_queue.task_done()
            except Exception as e:
                logger.error(f"WS process error: {e}")

    def stop(self):
        if hasattr(self, 'public_ws_coro'):
            self.public_ws_coro.cancel()
        if hasattr(self, 'private_ws_coro'):
            self.private_ws_coro.cancel()
```

- [ ] **步骤 2：简化 `src/check_balance.py`**

移除直接 `_rest_request` 调用，改用 SDK。

```python
import asyncio
import json
import os
from dotenv import load_dotenv
from src.okx_sdk import account_api, market_api

async def check():
    load_dotenv()
    # SDK 同步调用需要在线程中执行
    import asyncio

    acc = account_api()
    mkt = market_api()

    # 资金账户
    r1 = acc.get_balances(ccy="USDT")
    print("=== Funding Account USDT ===")
    print(json.dumps(r1.get("data", []), indent=2))

    # 交易账户
    r2 = acc.get_account_balance()
    d = r2["data"][0]
    ...  # rest unchanged

if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check())
```

- [ ] **步骤 3：验证 `main.py` 启动**

运行：`python -c "import asyncio; from src.okx_client import OKXClient; c=OKXClient(); print('OK')"`

---

### 任务 7：迁移 `src/reports/okx_public_probe.py` → SDK

**文件：**
- 修改：`src/reports/okx_public_probe.py`

- [ ] **步骤 1：替换 `_http_get_json` 和 `fetch_public_instruments`/`fetch_public_candles`**

```python
from src.okx_sdk import market_api, public_api


def fetch_public_instruments(inst_type: str = "SWAP") -> list[dict[str, object]]:
    result = public_api().get_instruments(instType=inst_type)
    return list(result.get("data") or [])


def fetch_public_candles(inst_id: str, limit: int = 10) -> pd.DataFrame:
    result = market_api().get_candlesticks(
        instId=inst_id, bar="1m", limit=limit)
    rows = result.get("data") or []
    # ...rest unchanged
```

- [ ] **步骤 2：删除 `urllib.parse`, `urllib.request`, `OKX_BASE_URL`**

- [ ] **步骤 3：验证**

运行：`python -m src.reports.okx_public_probe --inst-id BTC-USDT-SWAP --out-dir C:\Users\Rusz\AppData\Local\Temp\probe_test`

---

### 任务 8：迁移脚本 S1-S6

**文件：**
- 修改：`scripts/probe_okx_endpoints.py`
- 修改：`scripts/probe_okx_depth.py`
- 修改：`scripts/probe_execution_feasibility.py`
- 修改：`scripts/build_listing_events.py`
- 修改：`scripts/run_paper_ensemble.py`
- 修改：`scripts/run_listing_fade_forward_monitor.py`

**共用模式：** 每个脚本的 `_http_get` / `http_get_json` / `http_get` 函数替换为 SDK 调用。

- [ ] **步骤 1：迁移 `scripts/build_listing_events.py`**

最简单的独立脚本，先迁移验证：

```python
from src.okx_sdk import public_api


def main():
    result = public_api().get_instruments(instType="SWAP")
    insts = result.get("data") or []
    # ...rest unchanged
```

- [ ] **步骤 2：迁移 `scripts/probe_execution_feasibility.py`**

替换 `http_get_json` → SDK 调用。

```python
from src.okx_sdk import market_api, public_api


def fetch_instruments(inst_type: str = "SWAP") -> list[dict]:
    result = public_api().get_instruments(instType=inst_type)
    return result.get("data") or []


def fetch_tickers() -> dict[str, dict]:
    result = market_api().get_tickers(instType="SWAP")
    out = {}
    for x in result.get("data") or []:
        out[x.get("instId")] = x
    return out


def fetch_book(inst_id: str, sz: int = 5) -> dict | None:
    result = market_api().get_orderbook(instId=inst_id, sz=sz)
    data = result.get("data") or []
    return data[0] if data else None
```

删除文件顶部的 `urllib.*` 和 `httpx` 导入。

- [ ] **步骤 3：迁移 `scripts/run_paper_ensemble.py`**

替换 `_http_get` 为 `market_api().get_candlesticks()`。

```python
from src.okx_sdk import market_api


def fetch_recent_1h_candles(inst_id: str, limit: int = 96) -> pd.DataFrame:
    result = market_api().get_candlesticks(
        instId=inst_id, bar="1H", limit=limit)
    rows = result.get("data") or []
    # ...rest unchanged
```

删除 `urllib.*` 导入和 `OKX_BASE` 常量。

- [ ] **步骤 4：迁移 `scripts/run_listing_fade_forward_monitor.py`**

替换 `_http_get` → `public_api().get_instruments()`。

```python
from src.okx_sdk import public_api


def poll_new_listings() -> list[dict[str, Any]]:
    result = public_api().get_instruments(instType="SWAP")
    insts = result.get("data") or []
    # ...rest unchanged
```

删除 `urllib.*` 导入和 `OKX_BASE` 常量。

- [ ] **步骤 5：迁移 `scripts/probe_okx_endpoints.py`**

替换所有 `http_get` 调用为对应的 SDK 方法：

```python
from src.okx_sdk import market_api, public_api


def probe_instruments() -> dict:
    result = public_api().get_instruments(instType="SWAP")
    data = result.get("data") or []
    # ...rest unchanged


def probe_candles(inst_id: str = "BTC-USDT-SWAP") -> dict:
    result = market_api().get_candlesticks(
        instId=inst_id, bar="1m", limit=300)
    data = result.get("data") or []
    # ...rest unchanged
```

对于 SDK 未覆盖的端点（`/support/announcements`, `/rubik/stat/contracts/open-interest-history`），保留 `urllib.request` 版本，添加标记注释。

- [ ] **步骤 6：迁移 `scripts/probe_okx_depth.py`**

类似方案，替换 `/public/instruments` 和 `/market/history-candles` 为 SDK 调用。

---

### 任务 9：更新测试

**文件：**
- 修改：`src/backtest/tests/test_okx_public_probe_fetchers.py`

- [ ] **步骤 1：重写测试，mock SDK 而不是 urlopen**

```python
from unittest.mock import patch
from src.reports.okx_public_probe import fetch_public_instruments


def test_fetch_public_instruments_parses_okx_payload():
    fake_result = {"code": "0", "data": [{"instId": "BTC-USDT-SWAP"}]}
    with patch("src.reports.okx_public_probe.public_api") as mock_factory:
        mock_api = mock_factory.return_value
        mock_api.get_instruments.return_value = fake_result
        rows = fetch_public_instruments()
    assert rows[0]["instId"] == "BTC-USDT-SWAP"
```

- [ ] **步骤 2：运行测试确认通过**

运行：`python -m pytest src/backtest/tests/test_okx_public_probe_fetchers.py -v`

---

### 任务 10：最终清理与审计

- [ ] **步骤 1：搜索残留的自定义 OKX HTTP 调用**

```bash
rg -l "OK-ACCESS-SIGN|hmac\.new|aiohttp.*okx|wss://ws\.okx\.com|urllib\.request.*okx" --type py src/ scripts/
```

预期：只留下 `docs/plan/` 中的文档引用和 `okx_sdk.py` 中的合理引用。

- [ ] **步骤 2：验证 `strategy.py` 的 `self.client` 接口未破坏**

检查 `strategy.py` 中调用的所有方法 (`place_order`, `cancel_all_orders`) 在 `OKXClient` 中仍然存在。

- [ ] **步骤 3：提交 GitHub issue 给 python-okx**

针对 SDK 未覆盖的端点（announcements, rubik OI history）创建 issue。

---

## 技能使用记录

| 阶段 | 技能 |
|:-----|:-----|
| 全计划 | Skill: `chinese-documentation` — 计划使用中文文档写作规范 |

## 关闭门

- [ ] 所有 `src/data/` 模块不再包含 `urllib.request` / `aiohttp` 直接调用（SDK 缺口除外）
- [ ] `src/okx_client.py` 中无自建签名逻辑
- [ ] `src/main.py` 不直接使用任何自定义 HTTP 调用
- [ ] `scripts/` 下所有脚本的 HTTP 调用已替换为 SDK
- [ ] 测试通过
- [ ] 残留自定义调用搜索返回空
