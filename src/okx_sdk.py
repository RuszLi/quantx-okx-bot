"""OKX SDK 客户端工厂 — 统一的 SDK 初始化入口.

所有模块必须通过此模块获取 SDK 客户端，禁止自行导入 okx 创建实例。
"""
from __future__ import annotations

import asyncio
import os
import time
from functools import partial

from dotenv import load_dotenv
from okx import Account, Funding, MarketData, PublicData, Trade

load_dotenv()


# ── 凭证读取 ──────────────────────────────────────────

def _proxy() -> str | None:
    return os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("OKX_PROXY")


def _flag() -> str:
    return os.environ.get("OKX_FLAG", "1")


def _api_key() -> str:
    return os.environ.get("OKX_API_KEY", "")


def _api_secret() -> str:
    return os.environ.get("OKX_API_SECRET", "")


def _passphrase() -> str:
    return os.environ.get("OKX_PASSPHRASE", "")


# ── 公共数据客户端（无需凭证） — 模块级 singleton ──────


_MARKET_API: MarketData.MarketAPI | None = None
_PUBLIC_API: PublicData.PublicAPI | None = None


def market_api() -> MarketData.MarketAPI:
    global _MARKET_API
    if _MARKET_API is None:
        proxy = _proxy()
        _MARKET_API = MarketData.MarketAPI(proxy=proxy) if proxy else MarketData.MarketAPI()
    return _MARKET_API


def public_api() -> PublicData.PublicAPI:
    global _PUBLIC_API
    if _PUBLIC_API is None:
        proxy = _proxy()
        _PUBLIC_API = PublicData.PublicAPI(proxy=proxy) if proxy else PublicData.PublicAPI()
    return _PUBLIC_API


# ── 鉴权客户端（需 API Key） — 模块级 singleton ────────


_TRADE_API: Trade.TradeAPI | None = None
_ACCOUNT_API: Account.AccountAPI | None = None
_FUNDING_API: Funding.FundingAPI | None = None


def trade_api() -> Trade.TradeAPI:
    global _TRADE_API
    if _TRADE_API is None:
        _TRADE_API = Trade.TradeAPI(
            api_key=_api_key(), api_secret_key=_api_secret(),
            passphrase=_passphrase(), flag=_flag(),
            proxy=_proxy(),
        )
    return _TRADE_API


def account_api() -> Account.AccountAPI:
    global _ACCOUNT_API
    if _ACCOUNT_API is None:
        _ACCOUNT_API = Account.AccountAPI(
            api_key=_api_key(), api_secret_key=_api_secret(),
            passphrase=_passphrase(), flag=_flag(),
            proxy=_proxy(),
        )
    return _ACCOUNT_API


def funding_api() -> Funding.FundingAPI:
    global _FUNDING_API
    if _FUNDING_API is None:
        _FUNDING_API = Funding.FundingAPI(
            api_key=_api_key(), api_secret_key=_api_secret(),
            passphrase=_passphrase(), flag=_flag(),
            proxy=_proxy(),
        )
    return _FUNDING_API


# ── async 桥接 ────────────────────────────────────────


async def async_market_api() -> MarketData.MarketAPI:
    return await asyncio.to_thread(market_api)


async def async_public_api() -> PublicData.PublicAPI:
    return await asyncio.to_thread(public_api)


async def async_trade_api() -> Trade.TradeAPI:
    return await asyncio.to_thread(trade_api)


async def async_account_api() -> Account.AccountAPI:
    return await asyncio.to_thread(account_api)


async def async_funding_api() -> Funding.FundingAPI:
    return await asyncio.to_thread(funding_api)


async def call_in_thread(fn, *args, **kwargs):
    """在独立线程中执行同步 SDK 调用，返回结果."""
    import asyncio
    return await asyncio.to_thread(partial(fn, *args, **kwargs))
