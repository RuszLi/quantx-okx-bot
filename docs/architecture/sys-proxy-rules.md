# sys-proxy-rules

## 系统吸引子：统一本地代理

> **强制规则**：所有与外部接口请求的脚本，都必须统一走本地代理，禁止直连。

## 代理配置

| 协议 | 代理地址 | 说明 |
|:-----|:---------|:-----|
| HTTP 代理 | `http://127.0.0.1:7890` | 明文 HTTP 请求走代理 |
| SOCKS5 代理 | `socks5://127.0.0.1:7897` | SOCKS5 | 混合代理端口  |
| HTTPS 代理 | `http://127.0.0.1:7890` | TLS 加密请求复用同一端口 |

## 适用范围

- **通讯·网络库**（Network Library）：`requests`、`urllib`、`httpx`、`aiohttp` 等会发起 HTTP/S 请求的第三方包
- **SDK 客户端**：`python-okx` SDK 的所有客户端实例同样适用，代理通过 `src/okx_sdk.py` 统一注入
- **适用目录**：`scripts/`、`src/`、`tests/` 等目录下所有文件
- **例外场景**：本地开发、测试环境无代理时，需在代码中显式关闭代理或添加开关，而非删除默认配置

## 实现规范

### 1. 默认启用

新建外部请求相关代码时，应**默认启用代理**，而非被动读取环境变量：

```python
# ✅ 推荐：硬编码默认代理，可在需要时覆盖
DEFAULT_PROXY = "http://127.0.0.1:7890"

# ❌ 禁止：无默认值、依赖开发者手动设置环境变量
proxy = os.getenv("HTTP_PROXY") or ""
```

### 2. 环境变量覆盖（可选）

支持通过环境变量覆盖默认代理，便于 CI/CD 或特殊机器部署：

```python
# 优先级：环境变量 > 硬编码默认
PROXY = os.getenv("HTTP_PROXY") or os.getenv("ALL_PROXY") or "http://127.0.0.1:7890"
```

### 3. 代理开关

对于需要灵活切换的场景，提供显式开关：

```python
def __init__(self, use_proxy: bool = True):
    self.proxy = "http://127.0.0.1:7890" if use_proxy else None
```

> 注意：默认值必须为 `use_proxy=True`。

### 4. 网络库适配示例

| 代理参数 示例 |
|:------------|
| **requests** | `requests.get(url, proxies={"http": PROXY, "https": PROXY})` |
| **httpx** | `httpx.Client(proxy=PROXY)` / `httpx.AsyncClient(proxy=PROXY)` |
| **aiohttp** | `session.get(url, proxy=PROXY)` |
| **urllib** | `urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})` |
| **python-okx SDK** | 通过 `src/okx_sdk.py` 统一注入，无需各模块自行配置 |

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
