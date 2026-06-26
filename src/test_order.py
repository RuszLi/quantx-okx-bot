import asyncio
import json
import os
import logging
from dotenv import load_dotenv
from okx_client import OKXClient
from src.okx_sdk import account_api

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

async def test_order():
    load_dotenv()
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")

    if not api_key:
        logger.error("No API Key found in .env. Aborting.")
        return

    client = OKXClient(api_key, api_secret, passphrase, use_proxy=True)
    asyncio.create_task(client.start())

    logger.info("Waiting for Private WS to connect...")
    while not client.private_ws:
        await asyncio.sleep(0.1)

    logger.info("Private WS connected. Waiting 2s for login to complete...")
    await asyncio.sleep(2)

    instId = "DOGE-USDT-SWAP"
    sz = "0.01"

    logger.info(f"[STEP 0] Setting isolated leverage 10x for {instId}")
    await client.set_leverage(instId, 10, mgnMode="isolated", posSide="long")
    await client.set_leverage(instId, 10, mgnMode="isolated", posSide="short")

    account = account_api()
    raw_max = await asyncio.to_thread(
        account.get_max_size, instId=instId, tdMode="isolated", lever="10",
    )
    logger.info(f"Max order size (isolated 10x): {json.dumps(raw_max['data'])}")

    logger.info(f"[STEP 1] Opening long: BUY {sz} {instId} (isolated)")
    await client.place_order(instId, "buy", sz, ordType="market", posSide="long", tdMode="isolated")

    logger.info("Waiting 5s for fill confirmation...")
    await asyncio.sleep(5)

    logger.info(f"[STEP 2] Closing long: SELL {sz} {instId} (isolated)")
    await client.place_order(instId, "sell", sz, ordType="market", posSide="long", tdMode="isolated")

    logger.info("Waiting 3s for close confirmation...")
    await asyncio.sleep(3)

    client.stop()
    logger.info("Test finished. Check logs above for ✅ / ❌ results.")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_order())
