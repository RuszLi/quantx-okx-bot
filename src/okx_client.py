import asyncio
import json
import logging
import time
import aiohttp
from typing import List, Dict, Callable, Optional

from src.okx_sdk import market_api, trade_api, account_api

logger = logging.getLogger(__name__)

class OKXClient:
    def __init__(self, api_key: str = "", api_secret: str = "", passphrase: str = "", use_proxy: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase

        self.public_ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.private_ws_url = "wss://ws.okx.com:8443/ws/v5/private"
        self.proxy = "http://127.0.0.1:7890" if use_proxy else None

        self.public_ws = None
        self.private_ws = None
        self.session = None

        self.callbacks: Dict[str, Callable] = {}

        self.running = False
        self.msg_queue = asyncio.Queue()
        self.worker_task = None

    # ── REST 方法：全部委托给 SDK ──────────────────────────

    async def set_leverage(self, instId: str, lever: int, mgnMode: str = "cross", posSide: str = "long") -> bool:
        try:
            client = account_api()
            result = await asyncio.to_thread(
                client.set_leverage,
                instId=instId, lever=str(lever), mgnMode=mgnMode, posSide=posSide,
            )
            if result.get("code") == "0":
                logger.info(f"Leverage set to {lever}x for {instId} ({posSide}): {result}")
                return True
            logger.error(f"Failed to set leverage: {result}")
            return False
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
            return False

    async def get_account_balance(self, ccy: str = "USDT") -> float:
        try:
            client = account_api()
            result = await asyncio.to_thread(client.get_account_balance)
            if result["code"] == "0" and result["data"]:
                for detail in result["data"][0].get("details", []):
                    if detail["ccy"] == ccy:
                        return float(detail["availBal"])
            logger.error(f"Failed to get balance: {result}")
            return 0.0
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0

    async def get_positions(self, instType: str = "SWAP") -> list:
        try:
            client = account_api()
            result = await asyncio.to_thread(client.get_positions, instType=instType)
            if result["code"] == "0":
                return [p for p in result["data"] if float(p.get("pos", "0")) != 0]
            logger.error(f"Failed to get positions: {result}")
            return []
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    async def get_instrument_info(self, instId: str) -> dict:
        try:
            client = market_api()
            result = await asyncio.to_thread(
                client.get_instruments, instType="SWAP", instId=instId,
            )
            if result["code"] == "0" and result["data"]:
                return result["data"][0]
            logger.error(f"Failed to get instrument info: {result}")
            return {}
        except Exception as e:
            logger.error(f"Error getting instrument info: {e}")
            return {}

    async def get_all_instruments(self, instType: str = "SWAP") -> list:
        try:
            client = market_api()
            result = await asyncio.to_thread(client.get_instruments, instType=instType)
            if result["code"] == "0" and result["data"]:
                return result["data"]
            logger.error(f"Failed to get all instruments: {result}")
            return []
        except Exception as e:
            logger.error(f"Error getting all instruments: {e}")
            return []

    async def get_tickers(self, instType: str = "SWAP") -> list:
        try:
            client = market_api()
            result = await asyncio.to_thread(client.get_tickers, instType=instType)
            if result["code"] == "0" and result["data"]:
                return result["data"]
            logger.error(f"Failed to get tickers: {result}")
            return []
        except Exception as e:
            logger.error(f"Error getting tickers: {e}")
            return []

    # ── WebSocket ────────────────────────────────────────

    async def connect_public(self):
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

                    timestamp = str(time.time()).split('.')[0]
                    sign = self._generate_signature(timestamp, 'GET', '/users/self/verify')
                    login_msg = {
                        "op": "login",
                        "args": [{
                            "apiKey": self.api_key,
                            "passphrase": self.passphrase,
                            "timestamp": timestamp,
                            "sign": sign,
                        }]
                    }
                    await ws.send_json(login_msg)

                    logger.info("OKX Private WS Connected and Login sent.")
                    await self._listen(ws, "private")
            except Exception as e:
                logger.error(f"Private WS Error: {e}. Reconnecting in 1s...")
                self.private_ws = None
                await asyncio.sleep(1)

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        import hmac, base64
        message = timestamp + method + request_path + body
        mac = hmac.new(bytes(self.api_secret, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
        return base64.b64encode(mac.digest()).decode('utf-8')

    async def _listen(self, ws, ws_type: str):
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    logger.debug(f"Received WS data: {data}")

                    if "event" in data:
                        if data["event"] == "login":
                            logger.info(f"Login successful: {data}")
                            if ws_type == "private":
                                sub_msg = {
                                    "op": "subscribe",
                                    "args": [{"channel": "orders", "instType": "SWAP"}]
                                }
                                await ws.send_json(sub_msg)
                        elif data["event"] == "error":
                            logger.error(f"WS Error Event: {data}")
                        continue

                    if "op" in data and data["op"] == "order":
                        for item in data.get("data", []):
                            clOrdId = item.get("clOrdId", "")
                            sCode = item.get("sCode", "")
                            sMsg = item.get("sMsg", "")
                            if sCode == "0":
                                logger.info(f"✅ Order placed successfully: {item}")
                            else:
                                logger.error(f"❌ Order placement failed: {sMsg} ({item})")
                                if "order_error" in self.callbacks:
                                    self.msg_queue.put_nowait(("order_error", "GLOBAL"))
                        continue

                    if "arg" in data and "channel" in data["arg"]:
                        channel = data["arg"]["channel"]
                        if channel in self.callbacks:
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
        if not self.public_ws:
            logger.warning("Public WS not connected yet. Waiting...")
            while not self.public_ws:
                await asyncio.sleep(0.5)

        sub_msg = {"op": "subscribe", "args": channels}
        for ch in channels:
            self.callbacks[ch["channel"]] = callback
        await self.public_ws.send_json(sub_msg)
        logger.info(f"Subscribed to: {channels}")

    async def place_order(self, instId: str, side: str, sz: str, ordType: str = "market", px: str = "",
                          posSide: str = "", slTriggerPx: str = "", slOrdPx: str = "",
                          tpTriggerPx: str = "", tpOrdPx: str = "", tdMode: str = "cross"):
        args = {
            "instId": instId,
            "tdMode": tdMode,
            "side": side,
            "ordType": ordType,
            "sz": sz,
        }
        if posSide:
            args["posSide"] = posSide
        if ordType in ["limit", "post_only"] and px:
            args["px"] = px
        if slTriggerPx or tpTriggerPx:
            algo_ord = {}
            if slTriggerPx:
                algo_ord["slTriggerPx"] = slTriggerPx
                algo_ord["slTriggerPxType"] = "last"
                algo_ord["slOrdPx"] = slOrdPx
            if tpTriggerPx:
                algo_ord["tpTriggerPx"] = tpTriggerPx
                algo_ord["tpTriggerPxType"] = "last"
                algo_ord["tpOrdPx"] = tpOrdPx
            args["attachAlgoOrds"] = [algo_ord]

        logger.warning(f"🚀 PLACING {ordType.upper()} ORDER (REST): {side} {sz} {instId} @ {px if px else 'MARKET'} | SL: {slTriggerPx} | TP: {tpTriggerPx}")
        logger.debug(f"Order payload: {json.dumps(args)}")

        try:
            client = trade_api()
            result = await asyncio.to_thread(client.place_order, **args)
            if result.get("code") == "0":
                logger.info(f"✅ Order placed successfully via SDK: {result}")
            else:
                logger.error(f"❌ Order placement failed via SDK: {result}")
                if "order_error" in self.callbacks:
                    self.msg_queue.put_nowait(("order_error", "GLOBAL"))
        except Exception as e:
            logger.error(f"Error placing order via SDK: {e}")
            if "order_error" in self.callbacks:
                self.msg_queue.put_nowait(("order_error", "GLOBAL"))

    async def cancel_all_orders(self, instId: str):
        if not self.private_ws:
            return
        try:
            client = trade_api()
            pending = await asyncio.to_thread(client.get_order_list, instId=instId, state="live")
            if pending.get("code") == "0" and pending.get("data"):
                orders_to_cancel = [{"instId": instId, "ordId": order["ordId"]} for order in pending["data"]]
                if orders_to_cancel:
                    cancel_res = await asyncio.to_thread(client.cancel_multiple_orders, orders_to_cancel)
                    logger.info(f"Cancel all orders response: {cancel_res}")
        except Exception as e:
            logger.error(f"Error canceling all orders: {e}")

    async def _process_ws_messages(self):
        while self.running:
            try:
                channel, data = await self.msg_queue.get()
                if channel in self.callbacks:
                    await self.callbacks[channel](data)
                self.msg_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing WS message: {e}")

    async def start(self):
        self.running = True
        self.worker_task = asyncio.create_task(self._process_ws_messages())
        await asyncio.gather(
            self.connect_public(),
            self.connect_private(),
        )

    def stop(self):
        self.running = False
        if self.session:
            asyncio.create_task(self.session.close())
