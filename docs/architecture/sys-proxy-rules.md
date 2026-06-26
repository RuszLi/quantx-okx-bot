# sys-proxy-rules

## 系统吸引子：统一本地代理

> **强制规则**：所有与外部接口请求的脚本，都必须统一走本地代理，禁止直连。

## 代理配置

| 协议         | 代理地址                       | 说明                                           |
| :--------- | :------------------------- | :------------------------------------------- |
| SOCKS5（推荐） | `socks5h://127.0.0.1:34982` | HTTP/HTTPS 全协议走 SOCKS5，避免 HTTPS CONNECT 隧道问题 |
| HTTP       | `http://127.0.0.1:7890`    | 仅 HTTP，兼容遗留配置                                |
| HTTPS       | `https://127.0.0.1:7890`    | 仅 HTTPS，兼容遗留配置                                |
| 混合       | `http://127.0.0.1:7897`    | 混合端口                               |

## 适用范围

- **通讯·网络库**（Network Library）：`requests`、`urllib`、`httpx`、`aiohttp` 等会发起 HTTP/S 请求的第三方包
- **SDK 客户端**：`python-okx` SDK 的所有客户端实例同样适用，代理通过 `src/okx_sdk.py` 统一注入
- **适用目录**：`scripts/`、`src/`、`tests/` 等目录下所有文件
- **例外场景**：本地开发、测试环境无代理时，需在代码中显式关闭代理或添加开关，而非删除默认配置

## 实现规范

### 1. 代理地址解析规则

代理地址由 `src/okx_sdk.py` 中的 `_proxy()` 函数统一解析，优先级如下：

| 优先级   | 来源                  |
| :---- | :------------------ |
| 1（最高） | 环境变量 `HTTP_PROXY`   |
| 2     | 环境变量 `HTTPS_PROXY`  |
| 3（默认） | 硬编码 `DEFAULT_PROXY` |

```python
def _proxy() -> str | None:
    return os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or DEFAULT_PROXY
```

默认值为 `socks5h://127.0.0.1:34982`，SOCKS5 在传输层统一处理 HTTP/HTTPS，避免 HTTP CONNECT 隧道带来的 TLS 握手不稳定问题。可通过环境变量 `HTTP_PROXY` 或 `HTTPS_PROXY` 覆盖为 HTTP 代理。

### 2. 代理开关

对于需要灵活切换的场景，提供显式开关：

```python
def __init__(self, use_proxy: bool = True):
    self.proxy = "http://127.0.0.1:7890" if use_proxy else None
```

> 注意：默认值必须为 `use_proxy=True`。

### 4. 网络库适配示例

| <br />             | 代理参数 示例                                                        |
| :----------------- | :------------------------------------------------------------- |
| **requests**       | `requests.get(url, proxies={"http": PROXY, "https": PROXY})`   |
| **httpx**          | `httpx.Client(proxy=PROXY)` / `httpx.AsyncClient(proxy=PROXY)` |
| **aiohttp**        | `session.get(url, proxy=PROXY)`                                |
| **urllib**         | `urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})` |
| **python-okx SDK** | 通过 `src/okx_sdk.py` 统一注入，无需各模块自行配置                             |

## 5. SDK 客户端代理集成

`python-okx` SDK 底层使用 `httpx`，代理参数通过 `src/okx_sdk.py` 统一注入：

### 5.1 自动读取环境变量

```python
# src/okx_sdk.py 内部逻辑
proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or None
MarketData.MarketAPI(proxy=proxy)
```

### 5.2 各模块无需自行配置代理

SDK 客户端初始化已包含代理配置，业务模块**禁止**重复设置代理：

```python
# ✅ 正确：通过 SDK 工厂获取客户端，代理已内置
from src.okx_sdk import market_api
client = market_api()

# ❌ 禁止：业务模块自行创建 SDK 实例并配置代理
from okx import MarketData
client = MarketData.MarketAPI(proxy="http://127.0.0.1:7890")
```

### 5.3 公共数据客户端也走代理

即使是无需凭证的 `MarketAPI()` 和 `PublicAPI()`，也应确保通过统一工厂获取以保证代理覆盖。|
