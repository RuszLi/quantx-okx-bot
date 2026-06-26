# sys-proxy-rules

## 系统吸引子：统一本地代理

> **强制规则**：所有与外部接口请求的脚本，都必须统一走本地代理，禁止直连。

## 代理配置

代理地址通过 `.env` 文件中的 `OKX_PROXY` 配置，禁止在代码中硬编码。

| 常见端口         | 代理地址                       | 说明                                           |
| :--------- | :------------------------- | :------------------------------------------- |
| Clash Mixed（当前） | `http://127.0.0.1:7897` | Clash Verge Rev 默认混合端口 |
| Clash HTTP       | `http://127.0.0.1:7890`    | Clash 传统 HTTP 端口                                |
| SOCKS5       | `socks5h://127.0.0.1:7897`    | 走 SOCKS5 协议                               |

## 适用范围

- **通讯·网络库**（Network Library）：`requests`、`urllib`、`httpx`、`aiohttp` 等会发起 HTTP/S 请求的第三方包
- **SDK 客户端**：`python-okx` SDK 的所有客户端实例同样适用，代理通过 `src/okx_sdk.py` 统一注入
- **适用目录**：`scripts/`、`src/`、`tests/` 等目录下所有文件
- **例外场景**：本地开发、测试环境无代理时，需在代码中显式关闭代理或添加开关，而非删除默认配置

## 实现规范

### 1. 代理地址解析规则

代理地址由 `src/okx_sdk.py` 中的 `_proxy()` 函数统一解析，优先级如下：

| 优先级   | 来源                  | 说明 |
| :---- | :------------------ | :-- |
| 1（最高） | 环境变量 `HTTP_PROXY`   | 系统级覆盖 |
| 2     | 环境变量 `HTTPS_PROXY`  | 系统级覆盖 |
| 3     | 环境变量 `OKX_PROXY`    | 项目专用，配置在 `.env` |
| 4（默认） | `None`（不使用代理） | 无代理直连 |

```python
def _proxy() -> str | None:
    return os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("OKX_PROXY")
```

配置方式：在 `.env` 文件中添加 `OKX_PROXY=http://127.0.0.1:7897`，切换代理时只需修改 `.env`，无需改代码。

### 2. 代理开关

代理由 `.env` 中的 `OKX_PROXY` 控制。如需临时禁用代理，可设置 `OKX_PROXY=`（空值）或注释掉该行。

### 3. 网络库适配示例

| <br />             | 代理参数 示例                                                        |
| :----------------- | :------------------------------------------------------------- |
| **requests**       | `requests.get(url, proxies={"http": PROXY, "https": PROXY})`   |
| **httpx**          | `httpx.Client(proxy=PROXY)` / `httpx.AsyncClient(proxy=PROXY)` |
| **aiohttp**        | `session.get(url, proxy=PROXY)`                                |
| **urllib**         | `urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})` |
| **python-okx SDK** | 通过 `src/okx_sdk.py` 统一注入，无需各模块自行配置                             |

## 4. SDK 客户端代理集成

`python-okx` SDK 底层使用 `httpx`，代理参数通过 `src/okx_sdk.py` 统一注入：

### 4.1 从 .env 读取代理

```python
# src/okx_sdk.py 内部逻辑
def _proxy() -> str | None:
    return os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("OKX_PROXY")
```

### 4.2 各模块无需自行配置代理

SDK 客户端初始化已包含代理配置，业务模块**禁止**重复设置代理：

```python
# ✅ 正确：通过 SDK 工厂获取客户端，代理已内置
from src.okx_sdk import market_api
client = market_api()

# ❌ 禁止：业务模块自行创建 SDK 实例并配置代理
from okx import MarketData
client = MarketData.MarketAPI(proxy="http://127.0.0.1:7890")
```

### 4.3 公共数据客户端也走代理

即使是无需凭证的 `MarketAPI()` 和 `PublicAPI()`，也应确保通过统一工厂获取以保证代理覆盖。
