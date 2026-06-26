import asyncio
import json
import os
from dotenv import load_dotenv

from src.okx_sdk import funding_api, account_api, market_api


async def check():
    load_dotenv()

    print("=== Funding Account USDT ===")
    funding = funding_api()
    r1 = await asyncio.to_thread(funding.get_balances, ccy="USDT")
    print(json.dumps(r1.get("data", []), indent=2))

    print("\n=== Trading Account ===")
    account = account_api()
    r2 = await asyncio.to_thread(account.get_account_balance)
    d = r2["data"][0]
    print(f"  adjEq:   {d.get('adjEq', 'N/A')}")
    print(f"  totalEq: {d.get('totalEq', 'N/A')}")
    for detail in d.get("details", []):
        avail = detail.get("availBal", "N/A")
        disEq = detail.get("disEq", "N/A")
        print(f"  [{detail['ccy']}] availBal={avail}  disEq={disEq}")

    print("\nDOGE-USDT-SWAP price:")
    market = market_api()
    r3 = await asyncio.to_thread(market.get_ticker, instId="DOGE-USDT-SWAP")
    price = r3["data"][0]["last"]
    print(f"DOGE-USDT-SWAP price: {price}")

    for lever in [10, 20, 50]:
        r4 = await asyncio.to_thread(
            account.get_max_size,
            instId="DOGE-USDT-SWAP", tdMode="cross", lever=str(lever),
        )
        mb = r4.get("data", [{}])[0].get("maxBuy", "err") if r4.get("code") == "0" else r4
        print(f"  maxBuy cross  {lever}x: {mb}")

    for lever in [10, 20, 50]:
        r5 = await asyncio.to_thread(
            account.get_max_size,
            instId="DOGE-USDT-SWAP", tdMode="isolated", lever=str(lever),
        )
        mb = r5.get("data", [{}])[0].get("maxBuy", "err") if r5.get("code") == "0" else r5
        print(f"  maxBuy isolated {lever}x: {mb}")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check())
