"""Market exposure factor strategy implementations.

Each factor implements MarketFactorStrategy and computes one component
of the overall market exposure score independently.
"""

from algo.risk.factors.aaii_sentiment_factor import AAIISentimentFactor
from algo.risk.factors.ad_line_factor import ADLineFactor
from algo.risk.factors.breadth_50dma_factor import Breadth50DMAFactor
from algo.risk.factors.breadth_200dma_factor import Breadth200DMAFactor
from algo.risk.factors.credit_appetite_factor import CreditAppetiteFactor
from algo.risk.factors.credit_spread_factor import CreditSpreadFactor
from algo.risk.factors.growth_vs_value_factor import GrowthVsValueFactor
from algo.risk.factors.inflation_risk_factor import InflationRiskFactor
from algo.risk.factors.momentum_factor import MomentumFactor
from algo.risk.factors.naaim_factor import NAAIMFactor
from algo.risk.factors.new_highs_lows_factor import NewHighsLowsFactor
from algo.risk.factors.put_call_ratio_factor import PutCallRatioFactor
from algo.risk.factors.russell_vs_spy_factor import RussellVsSpyFactor
from algo.risk.factors.selling_pressure_factor import SellingPressureFactor
from algo.risk.factors.short_term_momentum_factor import ShortTermMomentumFactor
from algo.risk.factors.trend_30wk_factor import Trend30WkFactor
from algo.risk.factors.vix_mean_reversion_factor import VixMeanReversionFactor
from algo.risk.factors.vix_regime_factor import VixRegimeFactor
from algo.risk.factors.volume_trend_factor import VolumeTrendFactor
from algo.risk.factors.yield_curve_factor import YieldCurveFactor

__all__ = [
    # Core 12 factors
    "AAIISentimentFactor",
    "ADLineFactor",
    "Breadth50DMAFactor",
    "Breadth200DMAFactor",
    # Expanded 8 new factors
    "CreditAppetiteFactor",
    "CreditSpreadFactor",
    "GrowthVsValueFactor",
    "InflationRiskFactor",
    "MomentumFactor",
    "NAAIMFactor",
    "NewHighsLowsFactor",
    "PutCallRatioFactor",
    "RussellVsSpyFactor",
    "SellingPressureFactor",
    "ShortTermMomentumFactor",
    "Trend30WkFactor",
    "VixMeanReversionFactor",
    "VixRegimeFactor",
    "VolumeTrendFactor",
    "YieldCurveFactor",
]
