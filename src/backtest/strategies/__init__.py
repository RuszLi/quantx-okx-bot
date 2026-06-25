"""Strategy registry for V3 backtests."""

from .base import StrategyConfig
from .beta_decouple import BetaDecoupleStrategy
from .ensemble import EnsembleStrategy
from .funding_extreme import FundingExtremeStrategy
from .listing_fade import ListingFadeStrategy
from .oi_velocity import OIVelocityStrategy
from .pair_mr import PairMRStrategy
from .pre_funding_unwind import PreFundingUnwindStrategy
from .weekend_wick import WeekendWickStrategy


STRATEGIES = {
    "listing_fade": ListingFadeStrategy,
    "funding_extreme": FundingExtremeStrategy,
    "ensemble": EnsembleStrategy,
    "pre_funding_unwind": PreFundingUnwindStrategy,
    "beta_decouple": BetaDecoupleStrategy,
    "weekend_wick": WeekendWickStrategy,
    "pair_mr": PairMRStrategy,
    "oi_velocity": OIVelocityStrategy,
}


__all__ = [
    "StrategyConfig",
    "BetaDecoupleStrategy",
    "EnsembleStrategy",
    "FundingExtremeStrategy",
    "ListingFadeStrategy",
    "OIVelocityStrategy",
    "PairMRStrategy",
    "PreFundingUnwindStrategy",
    "WeekendWickStrategy",
    "STRATEGIES",
]
