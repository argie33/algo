"""Market exposure factor strategy implementations.

Each factor implements MarketFactorStrategy and computes one component
of the overall market exposure score independently.

DEAD CODE - CONFIRMED UNUSED (2026-08-10): grepping the whole repo (algo/, tests/,
dashboard/, lambda/, scripts/) for every class name exported below turns up zero
imports outside this package - only two stray comment/docstring mentions in
dashboard/panels/exposure.py and tests/test_put_call_ratio_yfinance.py, neither of
which actually imports or instantiates anything here. The real, live implementation
that MarketExposure.compute() actually calls (via `self.calculator.naaim(...)`,
`.vix_regime(...)`, etc.) is the separate MarketFactorCalculator class in
algo/risk/market_factor_calculator.py - a full independent reimplementation of the
same ~12 factors that has silently diverged from this package.

This is not a hypothetical risk: git history shows real "fix:" commits landing on
these dead classes over time (e.g. "fix: Complete AAII sentiment factor overhaul",
"fix: Critical bug in put_call_ratio factor - cursor type handling") under the
apparent belief they affected production. They never did. Before touching anything
in this directory, check whether the same fix is needed in
algo/risk/market_factor_calculator.py instead - that's the one real trades depend on.
"""

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
