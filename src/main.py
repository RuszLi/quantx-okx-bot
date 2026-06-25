import asyncio
import logging
import os
from dotenv import load_dotenv
from okx_client import OKXClient
from strategy import VultureStrategy

# 配置日志，追求极速，日志级别可以调高
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# 全局交易锁：确保同一时间只有一个品种在持仓 (因为是 All-in 策略)
global_trade_lock = asyncio.Lock()

async def main():
    load_dotenv()
    
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    
    if not api_key:
        logger.warning("No API credentials found in .env. Running in READ-ONLY mode.")
        
    # 初始化客户端 (默认使用 127.0.0.1:7890 代理)
    client = OKXClient(api_key, api_secret, passphrase, use_proxy=True)
    
    # 启动客户端连接
    asyncio.create_task(client.start())
    
    # 等待公共频道连接成功
    while not client.public_ws:
        await asyncio.sleep(0.1)
        
    logger.info("Fetching market data to select top symbols...")
    
    # 1. 获取所有 SWAP 的 tickers，按 24h 交易量排序，选出 Top 20
    tickers = await client.get_tickers("SWAP")
    if not tickers:
        logger.error("Failed to get tickers. Exiting.")
        return
        
    # 过滤掉 USDC 交易对，只保留 USDT 交易对
    usdt_tickers = [t for t in tickers if t["instId"].endswith("-USDT-SWAP")]
    # 按 24h 交易量 (volCcy24h) 降序排序
    usdt_tickers.sort(key=lambda x: float(x.get("volCcy24h", 0)), reverse=True)
    
    top_n = 20
    target_instIds = [t["instId"] for t in usdt_tickers[:top_n]]
    logger.info(f"Selected Top {top_n} symbols by 24h volume: {target_instIds}")
    
    # 2. 获取所有合约信息，提取面值 / lotSz / minSz
    instruments = await client.get_all_instruments("SWAP")
    ctVal_map  = {inst["instId"]: float(inst.get("ctVal",  1.0))  for inst in instruments}
    lotSz_map  = {inst["instId"]: float(inst.get("lotSz",  0.01)) for inst in instruments}
    minSz_map  = {inst["instId"]: float(inst.get("minSz",  0.01)) for inst in instruments}

    # 3. 获取账户余额 (availBal，适用于逐仓模式)
    balance = await client.get_account_balance("USDT")
    logger.info(f"Current USDT availBal: {balance}")

    # 4. 为所有目标品种提前设置逐仓杠杆 (BUG 2/4: 下单前必须先设置)
    # 各品种有不同的最大杠杆上限，依次尝试 20x → 10x → 5x
    LEVERAGE = 20
    actual_leverage: dict = {}
    logger.info(f"Setting isolated leverage up to {LEVERAGE}x for {len(target_instIds)} symbols...")
    for instId in target_instIds:
        for lever in [LEVERAGE, 10, 5]:
            ok = await client.set_leverage(instId, lever, mgnMode="isolated", posSide="long")
            if ok:
                await client.set_leverage(instId, lever, mgnMode="isolated", posSide="short")
                actual_leverage[instId] = lever
                break
        else:
            actual_leverage[instId] = 5

    # 5. 为每个品种初始化独立的策略实例
    strategies = {}
    for instId in target_instIds:
        strategies[instId] = VultureStrategy(
            client, instId, global_trade_lock,
            contract_val=ctVal_map.get(instId, 1.0),
            lot_sz=lotSz_map.get(instId, 0.01),
            min_sz=minSz_map.get(instId, 0.01),
            initial_balance=balance,
            leverage=actual_leverage.get(instId, LEVERAGE),
        )

    # 6. 同步交易所现有持仓，防止重启后状态错乱 (BUG 5)
    existing_positions = await client.get_positions("SWAP")
    for pos in existing_positions:
        inst = pos.get("instId", "")
        if inst in strategies:
            strategies[inst].set_position_from_exchange(
                pos_side=pos.get("posSide", ""),
                avg_px=float(pos.get("avgPx", 0)),
            )
            if not global_trade_lock.locked():
                await global_trade_lock.acquire()  # 有持仓就占住全局锁
    
    # 批量订阅数据频道
    channels = []
    for instId in target_instIds:
        channels.extend([
            {"channel": "trades", "instId": instId},
            {"channel": "open-interest", "instId": instId},
            {"channel": "bbo-tbt", "instId": instId}
        ])
    
    # 统一的数据分发回调
    async def dispatch_ws_data(data: dict):
        if "arg" in data and "instId" in data["arg"]:
            instId = data["arg"]["instId"]
            if instId in strategies:
                await strategies[instId].handle_ws_data(data)
        elif "arg" in data and data["arg"].get("channel") == "orders":
            for order in data.get("data", []):
                instId = order.get("instId")
                if instId in strategies:
                    await strategies[instId].handle_order_update(order)
                    
    async def dispatch_order_error(instId: str):
        if instId == "GLOBAL":
            # 如果是全局错误，释放所有策略的锁
            if global_trade_lock.locked():
                global_trade_lock.release()
            for strategy in strategies.values():
                strategy.is_trading = False
                strategy.has_pending_exit_order = False
        elif instId in strategies:
            strategies[instId].handle_order_error()
                
    # 将分发方法注册为回调
    await client.subscribe(channels, dispatch_ws_data)
    client.callbacks["orders"] = dispatch_ws_data
    client.callbacks["order_error"] = dispatch_order_error
    
    # 7. 为每个品种启动 watchdog，防止持仓超时锁死 (BUG 4)
    for instId, strat in strategies.items():
        asyncio.create_task(strat._watchdog())

    logger.info(f"🦅 Vulture Strategy started for {len(target_instIds)} symbols. Hunting for liquidations...")
    
    # 保持主程序运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        client.stop()

if __name__ == "__main__":
    # 针对 Windows 的 asyncio 优化
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
