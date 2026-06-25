import asyncio
import json
import logging
import time
import hmac
import base64
import aiohttp
from typing import List, Dict, Callable, Optional

logger = logging.getLogger(__name__)

class OKXClient:
    def __init__(self, api_key: str = "", api_secret: str = "", passphrase: str = "", use_proxy: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        
        # OKX URLs
        self.public_ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.private_ws_url = "wss://ws.okx.com:8443/ws/v5/private"
        self.rest_url = "https://www.okx.com"
        
        # 代理设置
        self.proxy = "http://127.0.0.1:7890" if use_proxy else None
        
        self.public_ws = None
        self.private_ws = None
        self.session = None
        
        # 回调函数字典: channel -> callback
        self.callbacks: Dict[str, Callable] = {}
        
        self.running = False
        self.msg_queue = asyncio.Queue()
        self.worker_task = None

    async def _process_ws_messages(self):
        """后台 Worker：从队列中取出 WS 消息并分发，防止 Task 风暴"""
        while self.running:
            try:
                channel, data = await self.msg_queue.get()
                if channel in self.callbacks:
                    await self.callbacks[channel](data)
                self.msg_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing WS message: {e}")

    def _get_iso_timestamp(self) -> str:
        """生成严格符合 OKX 要求的 ISO 8601 时间戳"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z'

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        message = timestamp + method + request_path + body
        mac = hmac.new(bytes(self.api_secret, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
        d = mac.digest()
        return base64.b64encode(d).decode('utf-8')

    async def _rest_request(self, method: str, path: str, body: str = "") -> dict:
        """发送 REST API 请求"""
        timestamp = self._get_iso_timestamp()
        
        sign = self._generate_signature(timestamp, method, path, body)
        
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }
        
        url = self.rest_url + path
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.request(method, url, headers=headers, proxy=self.proxy) as response:
                    return await response.json()
            else:
                async with session.request(method, url, headers=headers, data=body, proxy=self.proxy) as response:
                    return await response.json()

    async def set_leverage(self, instId: str, lever: int, mgnMode: str = "cross", posSide: str = "long") -> bool:
        """设置合约杠杆"""
        import json as _json
        body = _json.dumps({"instId": instId, "lever": str(lever), "mgnMode": mgnMode, "posSide": posSide})
        try:
            res = await self._rest_request("POST", "/api/v5/account/set-leverage", body=body)
            if res.get("code") == "0":
                logger.info(f"Leverage set to {lever}x for {instId} ({posSide}): {res}")
                return True
            logger.error(f"Failed to set leverage: {res}")
            return False
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
            return False

    async def get_account_balance(self, ccy: str = "USDT") -> float:
        """获取账户实际可用余额 (availBal，适用于逐仓模式；cross 模式下 availEq 对 USDT 可能为 0)"""
        try:
            res = await self._rest_request("GET", f"/api/v5/account/balance?ccy={ccy}")
            if res["code"] == "0" and res["data"]:
                for detail in res["data"][0].get("details", []):
                    if detail["ccy"] == ccy:
                        return float(detail["availBal"])
            logger.error(f"Failed to get balance: {res}")
            return 0.0
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0

    async def get_positions(self, instType: str = "SWAP") -> list:
        """获取当前所有非零持仓"""
        try:
            res = await self._rest_request("GET", f"/api/v5/account/positions?instType={instType}")
            if res["code"] == "0":
                return [p for p in res["data"] if float(p.get("pos", "0")) != 0]
            logger.error(f"Failed to get positions: {res}")
            return []
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    async def get_instrument_info(self, instId: str) -> dict:
        """获取合约面值等信息"""
        try:
            res = await self._rest_request("GET", f"/api/v5/public/instruments?instType=SWAP&instId={instId}")
            if res["code"] == "0" and res["data"]:
                return res["data"][0]
            logger.error(f"Failed to get instrument info: {res}")
            return {}
        except Exception as e:
            logger.error(f"Error getting instrument info: {e}")
            return {}

    async def get_all_instruments(self, instType: str = "SWAP") -> list:
        """获取所有合约信息"""
        try:
            res = await self._rest_request("GET", f"/api/v5/public/instruments?instType={instType}")
            if res["code"] == "0" and res["data"]:
                return res["data"]
            logger.error(f"Failed to get all instruments: {res}")
            return []
        except Exception as e:
            logger.error(f"Error getting all instruments: {e}")
            return []

    async def get_tickers(self, instType: str = "SWAP") -> list:
        """获取所有 ticker 信息 (用于按交易量排序)"""
        try:
            res = await self._rest_request("GET", f"/api/v5/market/tickers?instType={instType}")
            if res["code"] == "0" and res["data"]:
                return res["data"]
            logger.error(f"Failed to get tickers: {res}")
            return []
        except Exception as e:
            logger.error(f"Error getting tickers: {e}")
            return []

    async def connect_public(self):
        """连接公共频道 (Trades, BBO, Open Interest)"""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        while self.running:
            try:
                logger.info(f"Connecting to OKX Public WS... (Proxy: {self.proxy})")
                async with self.session.ws_connect(self.public_ws_url, proxy=self.proxy, heartbeat=20) as ws:
                    self.public_ws = ws
                    logger.info("OKX Public WS Connected.")
                    await self._listen(ws, "public")
            except Exception as e:
                logger.error(f"Public WS Error: {e}. Reconnecting in 1s...")
                self.public_ws = None
                await asyncio.sleep(1)

    async def connect_private(self):
        """连接私有频道 (下单, 账户信息)"""
        if not self.api_key:
            logger.warning("No API Key provided, skipping private WS connection.")
            return
            
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        while self.running:
            try:
                logger.info(f"Connecting to OKX Private WS... (Proxy: {self.proxy})")
                async with self.session.ws_connect(self.private_ws_url, proxy=self.proxy, heartbeat=20) as ws:
                    self.private_ws = ws
                    
                    # 登录
                    timestamp = str(time.time()).split('.')[0] # WebSocket 登录使用 Unix 秒级时间戳
                    sign = self._generate_signature(timestamp, 'GET', '/users/self/verify')
                    login_msg = {
                        "op": "login",
                        "args": [{
                            "apiKey": self.api_key,
                            "passphrase": self.passphrase,
                            "timestamp": timestamp,
                            "sign": sign
                        }]
                    }
                    await ws.send_json(login_msg)
                    
                    logger.info("OKX Private WS Connected and Login sent.")
                    
                    await self._listen(ws, "private")
            except Exception as e:
                logger.error(f"Private WS Error: {e}. Reconnecting in 1s...")
                self.private_ws = None
                await asyncio.sleep(1)

    async def _listen(self, ws, ws_type: str):
        """监听 WebSocket 消息"""
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    logger.debug(f"Received WS data: {data}")
                    
                    if "event" in data:
                        if data["event"] == "login":
                            logger.info(f"Login successful: {data}")
                            if ws_type == "private":
                                # 登录成功后订阅订单频道
                                sub_msg = {
                                    "op": "subscribe",
                                    "args": [{"channel": "orders", "instType": "SWAP"}]
                                }
                                await ws.send_json(sub_msg)
                        elif data["event"] == "error":
                            logger.error(f"WS Error Event: {data}")
                        continue
                        
                    # 处理订单回报 (下单成功/失败)
                    if "op" in data and data["op"] == "order":
                        for item in data.get("data", []):
                            clOrdId = item.get("clOrdId", "")
                            sCode = item.get("sCode", "")
                            sMsg = item.get("sMsg", "")
                            if sCode == "0":
                                logger.info(f"✅ Order placed successfully: {item}")
                            else:
                                logger.error(f"❌ Order placement failed: {sMsg} ({item})")
                                # 提取 instId 并通知策略
                                # clOrdId 格式为 DOGEUSDTSWAP1782365022179
                                # 我们无法直接从中提取 instId，所以直接发送一个全局的 order_error
                                if "order_error" in self.callbacks:
                                    self.msg_queue.put_nowait(("order_error", "GLOBAL"))
                        continue
                    
                    if "arg" in data and "channel" in data["arg"]:
                        channel = data["arg"]["channel"]
                        if channel in self.callbacks:
                            # 将消息放入队列，由 Worker 处理
                            self.msg_queue.put_nowait((channel, data))
                            
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning(f"{ws_type.capitalize()} WS Connection Closed by Server.")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"{ws_type.capitalize()} WS Connection Error.")
                    break
                        
        except Exception as e:
            logger.error(f"Error in _listen ({ws_type}): {e}")

    async def subscribe(self, channels: List[Dict], callback: Callable):
        """
        订阅频道
        channels: [{"channel": "trades", "instId": "WIF-USDT-SWAP"}, ...]
        """
        if not self.public_ws:
            logger.warning("Public WS not connected yet. Waiting...")
            while not self.public_ws:
                await asyncio.sleep(0.5)
                
        sub_msg = {
            "op": "subscribe",
            "args": channels
        }
        
        # 注册回调
        for ch in channels:
            self.callbacks[ch["channel"]] = callback
            
        await self.public_ws.send_json(sub_msg)
        logger.info(f"Subscribed to: {channels}")

    async def place_order(self, instId: str, side: str, sz: str, ordType: str = "market", px: str = "", posSide: str = "", slTriggerPx: str = "", slOrdPx: str = "", tpTriggerPx: str = "", tpOrdPx: str = "", tdMode: str = "cross"):
        """
        发送订单
        ordType: "market" (市价), "limit" (限价), "post_only" (只做maker)
        """
        if not self.private_ws:
            logger.error("Private WS not connected. Cannot place order.")
            return
            
        args = {
            "instId": instId,
            "tdMode": tdMode,
            "side": side,
            "ordType": ordType,
            "sz": sz
        }
        
        if posSide:
            args["posSide"] = posSide
        
        # 只有在不附加止盈止损时，才使用自定义 clOrdId
        # 如果附加了止盈止损，让 OKX 自动生成主订单 ID，我们只传 attachAlgoOrds
        # 实际上，OKX 似乎对 clOrdId 的格式有非常严格且未文档化的要求
        # 为了稳定，我们完全不传 clOrdId，让 OKX 自动生成
        # args["clOrdId"] = clOrdId
        
        if ordType in ["limit", "post_only"] and px:
            args["px"] = px
            
        if slTriggerPx or tpTriggerPx:
            # OKX API 要求 attachAlgoOrds 必须是 JSON 数组
            algo_ord = {}
            if slTriggerPx:
                algo_ord["slTriggerPx"] = slTriggerPx
                algo_ord["slTriggerPxType"] = "last"
                algo_ord["slOrdPx"] = slOrdPx
            if tpTriggerPx:
                algo_ord["tpTriggerPx"] = tpTriggerPx
                algo_ord["tpTriggerPxType"] = "last"
                algo_ord["tpOrdPx"] = tpOrdPx
                
            # 尝试不传 attachAlgoClOrdId
            args["attachAlgoOrds"] = [algo_ord]
            
        logger.warning(f"🚀 PLACING {ordType.upper()} ORDER (REST): {side} {sz} {instId} @ {px if px else 'MARKET'} | SL: {slTriggerPx} | TP: {tpTriggerPx}")
        logger.debug(f"Order payload: {json.dumps(args)}")
        
        try:
            res = await self._rest_request("POST", "/api/v5/trade/order", body=json.dumps(args))
            if res.get("code") == "0":
                logger.info(f"✅ Order placed successfully via REST: {res}")
            else:
                logger.error(f"❌ Order placement failed via REST: {res}")
                if "order_error" in self.callbacks:
                    self.msg_queue.put_nowait(("order_error", "GLOBAL"))
        except Exception as e:
            logger.error(f"Error placing order via REST: {e}")
            if "order_error" in self.callbacks:
                self.msg_queue.put_nowait(("order_error", "GLOBAL"))

    async def cancel_all_orders(self, instId: str):
        """撤销该合约的所有挂单"""
        if not self.private_ws:
            return
            
        # OKX API 撤销所有订单的正确操作是 cancel-all-after 或者通过 REST API
        # 但在 WebSocket 中，通常需要指定具体的 order ID。
        # 为了简化，如果只是想撤销当前品种的挂单，我们可以使用 REST API 或者
        # 记录下我们发出的 clOrdId 然后批量撤销。
        # 这里我们先尝试使用 REST API 来撤销该品种的所有挂单，因为 WS 的 batch-cancel 需要具体的 ID。
        try:
            # 先获取所有挂单
            res = await self._rest_request("GET", f"/api/v5/trade/orders-pending?instId={instId}")
            if res.get("code") == "0" and res.get("data"):
                orders_to_cancel = [{"instId": instId, "ordId": order["ordId"]} for order in res["data"]]
                if orders_to_cancel:
                    cancel_res = await self._rest_request("POST", "/api/v5/trade/cancel-batch-orders", body=json.dumps(orders_to_cancel))
                    logger.info(f"Cancel all orders response: {cancel_res}")
        except Exception as e:
            logger.error(f"Error canceling all orders: {e}")

    async def start(self):
        self.running = True
        self.worker_task = asyncio.create_task(self._process_ws_messages())
        await asyncio.gather(
            self.connect_public(),
            self.connect_private()
        )
        
    def stop(self):
        self.running = False
        if self.session:
            asyncio.create_task(self.session.close())
