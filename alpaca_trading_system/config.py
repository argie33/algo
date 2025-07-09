"""
Alpaca Trading System Configuration
Production-ready configuration for algorithmic trading
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

class Environment(Enum):
    PAPER = "paper"
    LIVE = "live"

class RiskLevel(Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

@dataclass
class AlpacaConfig:
    """Alpaca API configuration"""
    api_key: str
    api_secret: str
    base_url: str
    environment: Environment
    
    @classmethod
    def from_env(cls, env: Environment = Environment.PAPER):
        """Load config from environment variables"""
        if env == Environment.PAPER:
            return cls(
                api_key=os.getenv("ALPACA_PAPER_API_KEY", ""),
                api_secret=os.getenv("ALPACA_PAPER_API_SECRET", ""),
                base_url=os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets"),
                environment=Environment.PAPER
            )
        else:
            return cls(
                api_key=os.getenv("ALPACA_LIVE_API_KEY", ""),
                api_secret=os.getenv("ALPACA_LIVE_API_SECRET", ""),
                base_url=os.getenv("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets"),
                environment=Environment.LIVE
            )

@dataclass
class TradingConfig:
    """Trading system configuration"""
    # Account settings
    max_position_size: float = 0.05  # 5% of portfolio per position
    max_portfolio_risk: float = 0.02  # 2% portfolio risk per trade
    max_daily_loss: float = 0.10  # 10% daily loss limit
    max_drawdown: float = 0.20  # 20% maximum drawdown
    
    # Strategy settings
    enabled_strategies: List[str] = None
    strategy_weights: Dict[str, float] = None
    rebalance_frequency: str = "daily"  # daily, weekly, monthly
    
    # Risk management
    risk_level: RiskLevel = RiskLevel.MODERATE
    stop_loss_pct: float = 0.02  # 2% stop loss
    take_profit_pct: float = 0.06  # 6% take profit
    trailing_stop_pct: float = 0.015  # 1.5% trailing stop
    
    # Order execution
    order_timeout: int = 300  # 5 minutes
    slippage_tolerance: float = 0.001  # 0.1% slippage tolerance
    min_order_size: float = 100  # Minimum $100 order
    
    # Market conditions
    allowed_market_hours: bool = True
    extended_hours_trading: bool = False
    min_volume: int = 100000  # Minimum daily volume
    min_price: float = 5.0  # Minimum stock price
    max_price: float = 1000.0  # Maximum stock price
    
    # Performance tracking
    performance_window: int = 252  # 1 year lookback
    benchmark_symbol: str = "SPY"
    
    def __post_init__(self):
        if self.enabled_strategies is None:
            self.enabled_strategies = [
                "momentum_breakout",
                "mean_reversion",
                "pattern_recognition",
                "technical_signals"
            ]
        
        if self.strategy_weights is None:
            self.strategy_weights = {
                "momentum_breakout": 0.3,
                "mean_reversion": 0.25,
                "pattern_recognition": 0.25,
                "technical_signals": 0.2
            }

@dataclass
class MonitoringConfig:
    """System monitoring configuration"""
    # Logging
    log_level: str = "INFO"
    log_file: str = "trading_system.log"
    max_log_size: int = 10 * 1024 * 1024  # 10MB
    
    # Alerts
    email_alerts: bool = True
    slack_alerts: bool = False
    discord_alerts: bool = False
    
    # Performance monitoring
    performance_update_interval: int = 60  # seconds
    risk_check_interval: int = 30  # seconds
    
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "trading_system"
    db_user: str = "postgres"
    db_password: str = "password"

# Global configuration instances
ALPACA_CONFIG = AlpacaConfig.from_env()
TRADING_CONFIG = TradingConfig()
MONITORING_CONFIG = MonitoringConfig()

# Trading universe - high-quality, liquid stocks
TRADING_UNIVERSE = [
    # Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "NFLX",
    # Finance
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "AXP",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "TMO", "DHR", "CVS",
    # Consumer
    "WMT", "HD", "PG", "KO", "PEP", "NKE", "SBUX", "MCD",
    # Industrial
    "BA", "CAT", "GE", "MMM", "HON", "LMT", "RTX", "UPS",
    # ETFs for diversification
    "SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "VIX"
]

# Market regime indicators
MARKET_INDICATORS = {
    "trend": ["SPY", "QQQ", "IWM"],
    "volatility": ["VIX", "VXST", "VXMT"],
    "bonds": ["TLT", "SHY", "HYG"],
    "commodities": ["GLD", "SLV", "USO"],
    "currencies": ["UUP", "FXE", "FXY"]
}

# Strategy parameters
STRATEGY_PARAMS = {
    "momentum_breakout": {
        "lookback_period": 20,
        "volume_threshold": 1.5,
        "price_change_threshold": 0.02,
        "confirmation_period": 3
    },
    "mean_reversion": {
        "lookback_period": 14,
        "std_dev_threshold": 2.0,
        "rsi_oversold": 30,
        "rsi_overbought": 70
    },
    "pattern_recognition": {
        "min_pattern_confidence": 0.7,
        "volume_confirmation": True,
        "lookback_days": 60
    },
    "technical_signals": {
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "rsi_period": 14,
        "bb_period": 20,
        "bb_std": 2.0
    }
}

# Risk management parameters
RISK_PARAMS = {
    "max_correlation": 0.7,  # Maximum correlation between positions
    "sector_concentration": 0.3,  # Maximum sector allocation
    "single_stock_limit": 0.1,  # Maximum single stock allocation
    "var_confidence": 0.95,  # VaR confidence level
    "var_lookback": 252,  # VaR lookback period
    "stress_test_scenarios": [
        {"name": "2008_crisis", "spy_return": -0.37},
        {"name": "covid_crash", "spy_return": -0.34},
        {"name": "tech_bubble", "spy_return": -0.49}
    ]
}

def get_config():
    """Get complete system configuration"""
    return {
        "alpaca": ALPACA_CONFIG,
        "trading": TRADING_CONFIG,
        "monitoring": MONITORING_CONFIG,
        "universe": TRADING_UNIVERSE,
        "indicators": MARKET_INDICATORS,
        "strategy_params": STRATEGY_PARAMS,
        "risk_params": RISK_PARAMS
    }

def update_config(updates: Dict):
    """Update configuration with new values"""
    global TRADING_CONFIG, MONITORING_CONFIG
    
    if "trading" in updates:
        for key, value in updates["trading"].items():
            if hasattr(TRADING_CONFIG, key):
                setattr(TRADING_CONFIG, key, value)
    
    if "monitoring" in updates:
        for key, value in updates["monitoring"].items():
            if hasattr(MONITORING_CONFIG, key):
                setattr(MONITORING_CONFIG, key, value)

def validate_config():
    """Validate configuration settings"""
    errors = []
    
    # Validate Alpaca config
    if not ALPACA_CONFIG.api_key:
        errors.append("Alpaca API key is required")
    if not ALPACA_CONFIG.api_secret:
        errors.append("Alpaca API secret is required")
    
    # Validate trading config
    if TRADING_CONFIG.max_position_size > 0.2:
        errors.append("Position size too large (max 20%)")
    if TRADING_CONFIG.max_portfolio_risk > 0.05:
        errors.append("Portfolio risk too high (max 5%)")
    
    # Validate strategy weights
    total_weight = sum(TRADING_CONFIG.strategy_weights.values())
    if abs(total_weight - 1.0) > 0.01:
        errors.append(f"Strategy weights must sum to 1.0, got {total_weight}")
    
    return errors

if __name__ == "__main__":
    # Test configuration
    errors = validate_config()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Configuration is valid")
        
    # Print configuration summary
    config = get_config()
    print(f"\nTrading Environment: {config['alpaca'].environment.value}")
    print(f"Enabled Strategies: {', '.join(config['trading'].enabled_strategies)}")
    print(f"Trading Universe: {len(config['universe'])} symbols")
    print(f"Risk Level: {config['trading'].risk_level.value}")