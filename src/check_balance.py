import asyncio
import os
import json
from dotenv import load_dotenv
from okx_client import OKXClient

async def check():
    load_dotenv()
    client = OKXClient(
        os.getenv("OKX_API_KEY", ""),
        os.getenv("OKX_API_SECRET", ""),
        os.getenv("OKX_PASSPHRASE", ""),
        use_proxy=True
    )

    r1 = await client._rest_request("GET", "/api/v5/asset/balances?ccy=USDT")
    print("=== Funding Account USDT ===")
    print(json.dumps(r1.get("data", []), indent=2))

    r2 = await client._rest_request("GET", "/api/v5/account/balance")
    d = r2["data"][0]
    print(f"\n=== Trading Account ===")
    print(f"  adjEq:   {d.get('adjEq', 'N/A')}")
    print(f"  totalEq: {d.get('totalEq', 'N/A')}")
    for detail in d.get("details", []):
        print(f"  [{detail['ccy']}] availBal={detail['availBal']}  disEq={detail['disEq']}")

    # DOGE 当前价
    r3 = await client._rest_request("GET", "/api/v5/market/ticker?instId=DOGE-USDT-SWAP")
    price = r3["data"][0]["last"]
    print(f"\nDOGE-USDT-SWAP price: {price}")

    # 不同杠杆下的最大可买数量
    for lever in [10, 20, 50]:
        r4 = await client._rest_request(
            "GET", f"/api/v5/account/max-size?instId=DOGE-USDT-SWAP&tdMode=cross&lever={lever}"
        )
        mb = r4.get("data", [{}])[0].get("maxBuy", "err") if r4.get("code") == "0" else r4
        print(f"  maxBuy cross  {lever}x: {mb}")

    for lever in [10, 20, 50]:
        r5 = await client._rest_request(
            "GET", f"/api/v5/account/max-size?instId=DOGE-USDT-SWAP&tdMode=isolated&lever={lever}"
        )
        mb = r5.get("data", [{}])[0].get("maxBuy", "err") if r5.get("code") == "0" else r5
        print(f"  maxBuy isolated {lever}x: {mb}")

if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check())
