"""
Base Strategy Class for Algorithmic Trading
Provides a foundation for all trading strategies with common functionality
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging
from enum import Enum

class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"

class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"

@dataclass
class Signal:
    """Trading signal data structure"""
    symbol: str
    signal_type: SignalType
    strength: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    price: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    position_size: Optional[float] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class StrategyMetrics:
    """Strategy performance metrics"""
    total_signals: int = 0
    profitable_signals: int = 0
    avg_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    last_updated: datetime = None

class BaseStrategy(ABC):
    """Base class for all trading strategies"""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"strategy.{name}")
        
        # Strategy state
        self.is_active = True
        self.last_update = None
        self.signals_generated = []
        self.metrics = StrategyMetrics()
        
        # Data storage
        self.data_cache = {}
        self.indicators_cache = {}
        
        # Configuration
        self.min_volume = self.config.get('min_volume', 100000)
        self.min_price = self.config.get('min_price', 5.0)
        self.max_price = self.config.get('max_price', 1000.0)
        self.lookback_period = self.config.get('lookback_period', 20)
        
        self.logger.info(f"Strategy {name} initialized")
    
    @abstractmethod
    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """Generate trading signals from market data"""
        pass
    
    @abstractmethod
    def calculate_position_size(self, signal: Signal, portfolio_value: float) -> float:
        """Calculate position size for a signal"""
        pass
    
    def preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Preprocess market data before analysis"""
        if data.empty:
            return data
        
        # Ensure we have required columns
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in data.columns:
                self.logger.error(f"Missing required column: {col}")
                return pd.DataFrame()
        
        # Calculate basic indicators
        data = data.copy()
        
        # Price-based indicators
        data['hl_pct'] = (data['high'] - data['low']) / data['close']
        data['co_pct'] = (data['close'] - data['open']) / data['open']
        data['returns'] = data['close'].pct_change()
        data['log_returns'] = np.log(data['close'] / data['close'].shift(1))
        
        # Volume indicators
        data['volume_ma'] = data['volume'].rolling(window=20).mean()
        data['volume_ratio'] = data['volume'] / data['volume_ma']
        data['volume_sma'] = data['volume'].rolling(window=10).mean()
        
        # Volatility indicators
        data['volatility'] = data['returns'].rolling(window=20).std()
        data['atr'] = self.calculate_atr(data)
        
        # Trend indicators
        data['sma_20'] = data['close'].rolling(window=20).mean()
        data['sma_50'] = data['close'].rolling(window=50).mean()
        data['ema_12'] = data['close'].ewm(span=12).mean()
        data['ema_26'] = data['close'].ewm(span=26).mean()
        
        return data
    
    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = data['high'] - data['low']
        high_close = np.abs(data['high'] - data['close'].shift(1))
        low_close = np.abs(data['low'] - data['close'].shift(1))
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.rolling(window=period).mean()
    
    def calculate_rsi(self, data: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = data.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_macd(self, data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD"""
        ema_fast = data.ewm(span=fast).mean()
        ema_slow = data.ewm(span=slow).mean()
        
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        histogram = macd - signal_line
        
        return macd, signal_line, histogram
    
    def calculate_bollinger_bands(self, data: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return upper_band, sma, lower_band
    
    def calculate_stochastic(self, data: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """Calculate Stochastic Oscillator"""
        lowest_low = data['low'].rolling(window=k_period).min()
        highest_high = data['high'].rolling(window=k_period).max()
        
        k_percent = 100 * (data['close'] - lowest_low) / (highest_high - lowest_low)
        d_percent = k_percent.rolling(window=d_period).mean()
        
        return k_percent, d_percent
    
    def is_valid_signal(self, signal: Signal, data: pd.DataFrame) -> bool:
        """Validate signal against basic criteria"""
        if data.empty:
            return False
        
        latest_data = data.iloc[-1]
        
        # Price filters
        if latest_data['close'] < self.min_price or latest_data['close'] > self.max_price:
            return False
        
        # Volume filter
        if latest_data['volume'] < self.min_volume:
            return False
        
        # Confidence filter
        if signal.confidence < 0.5:
            return False
        
        # Check for excessive volatility
        if 'volatility' in data.columns and latest_data['volatility'] > 0.1:  # 10% daily volatility
            return False
        
        return True
    
    def calculate_stop_loss(self, signal: Signal, data: pd.DataFrame) -> float:
        """Calculate stop loss price"""
        if data.empty:
            return signal.price * 0.98  # Default 2% stop loss
        
        latest_data = data.iloc[-1]
        atr = latest_data.get('atr', 0)
        
        if signal.signal_type == SignalType.BUY:
            # For long positions, stop loss below entry
            if atr > 0:
                return signal.price - (2 * atr)  # 2 ATR stop loss
            else:
                return signal.price * 0.98  # 2% stop loss
        else:
            # For short positions, stop loss above entry
            if atr > 0:
                return signal.price + (2 * atr)  # 2 ATR stop loss
            else:
                return signal.price * 1.02  # 2% stop loss
    
    def calculate_target_price(self, signal: Signal, data: pd.DataFrame) -> float:
        """Calculate target price"""
        if data.empty:
            return signal.price * 1.06  # Default 6% target
        
        latest_data = data.iloc[-1]
        atr = latest_data.get('atr', 0)
        
        if signal.signal_type == SignalType.BUY:
            # For long positions, target above entry
            if atr > 0:
                return signal.price + (3 * atr)  # 3 ATR target
            else:
                return signal.price * 1.06  # 6% target
        else:
            # For short positions, target below entry
            if atr > 0:
                return signal.price - (3 * atr)  # 3 ATR target
            else:
                return signal.price * 0.94  # 6% target
    
    def update_metrics(self, signal: Signal, actual_return: float):
        """Update strategy performance metrics"""
        self.metrics.total_signals += 1
        
        if actual_return > 0:
            self.metrics.profitable_signals += 1
            self.metrics.avg_win = (self.metrics.avg_win * (self.metrics.profitable_signals - 1) + actual_return) / self.metrics.profitable_signals
        else:
            losing_signals = self.metrics.total_signals - self.metrics.profitable_signals
            self.metrics.avg_loss = (self.metrics.avg_loss * (losing_signals - 1) + actual_return) / losing_signals
        
        # Update win rate
        self.metrics.win_rate = self.metrics.profitable_signals / self.metrics.total_signals
        
        # Update average return
        self.metrics.avg_return = (self.metrics.avg_return * (self.metrics.total_signals - 1) + actual_return) / self.metrics.total_signals
        
        # Update profit factor
        if self.metrics.avg_loss != 0:
            self.metrics.profit_factor = (self.metrics.avg_win * self.metrics.profitable_signals) / abs(self.metrics.avg_loss * (self.metrics.total_signals - self.metrics.profitable_signals))
        
        self.metrics.last_updated = datetime.now()
        
        self.logger.debug(f"Metrics updated: Win Rate: {self.metrics.win_rate:.2%}, Avg Return: {self.metrics.avg_return:.2%}")
    
    def get_strategy_state(self) -> Dict[str, Any]:
        """Get current strategy state"""
        return {
            'name': self.name,
            'is_active': self.is_active,
            'last_update': self.last_update,
            'signals_count': len(self.signals_generated),
            'metrics': {
                'total_signals': self.metrics.total_signals,
                'win_rate': self.metrics.win_rate,
                'avg_return': self.metrics.avg_return,
                'profit_factor': self.metrics.profit_factor,
                'sharpe_ratio': self.metrics.sharpe_ratio
            },
            'config': self.config
        }
    
    def reset_strategy(self):
        """Reset strategy state"""
        self.signals_generated = []
        self.metrics = StrategyMetrics()
        self.data_cache = {}
        self.indicators_cache = {}
        self.last_update = None
        self.logger.info(f"Strategy {self.name} reset")
    
    def update_config(self, new_config: Dict[str, Any]):
        """Update strategy configuration"""
        self.config.update(new_config)
        
        # Update derived parameters
        self.min_volume = self.config.get('min_volume', 100000)
        self.min_price = self.config.get('min_price', 5.0)
        self.max_price = self.config.get('max_price', 1000.0)
        self.lookback_period = self.config.get('lookback_period', 20)
        
        self.logger.info(f"Strategy {self.name} configuration updated")
    
    def __str__(self):
        return f"Strategy({self.name})"
    
    def __repr__(self):
        return f"Strategy(name='{self.name}', active={self.is_active}, signals={len(self.signals_generated)})"

class StrategyManager:
    """Manager for multiple trading strategies"""
    
    def __init__(self):
        self.strategies = {}
        self.strategy_weights = {}
        self.logger = logging.getLogger("strategy_manager")
    
    def add_strategy(self, strategy: BaseStrategy, weight: float = 1.0):
        """Add a strategy to the manager"""
        self.strategies[strategy.name] = strategy
        self.strategy_weights[strategy.name] = weight
        self.logger.info(f"Added strategy: {strategy.name} with weight {weight}")
    
    def remove_strategy(self, strategy_name: str):
        """Remove a strategy from the manager"""
        if strategy_name in self.strategies:
            del self.strategies[strategy_name]
            del self.strategy_weights[strategy_name]
            self.logger.info(f"Removed strategy: {strategy_name}")
    
    def get_all_signals(self, market_data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """Get signals from all active strategies"""
        all_signals = []
        
        for name, strategy in self.strategies.items():
            if strategy.is_active:
                try:
                    signals = strategy.generate_signals(market_data)
                    
                    # Apply strategy weight to signal strength
                    weight = self.strategy_weights.get(name, 1.0)
                    for signal in signals:
                        signal.strength *= weight
                        signal.metadata['strategy'] = name
                        signal.metadata['weight'] = weight
                    
                    all_signals.extend(signals)
                    
                except Exception as e:
                    self.logger.error(f"Error generating signals for {name}: {e}")
        
        return all_signals
    
    def aggregate_signals(self, signals: List[Signal]) -> List[Signal]:
        """Aggregate signals for the same symbol"""
        signal_dict = {}
        
        for signal in signals:
            symbol = signal.symbol
            
            if symbol not in signal_dict:
                signal_dict[symbol] = signal
            else:
                # Combine signals for the same symbol
                existing = signal_dict[symbol]
                
                # Average the strength and confidence
                total_weight = existing.strength + signal.strength
                existing.strength = total_weight
                existing.confidence = (existing.confidence + signal.confidence) / 2
                
                # Merge metadata
                existing.metadata.setdefault('strategies', []).append(signal.metadata.get('strategy', 'unknown'))
        
        return list(signal_dict.values())
    
    def get_strategy_performance(self) -> Dict[str, Dict]:
        """Get performance metrics for all strategies"""
        performance = {}
        
        for name, strategy in self.strategies.items():
            performance[name] = {
                'metrics': strategy.metrics,
                'state': strategy.get_strategy_state(),
                'weight': self.strategy_weights.get(name, 1.0)
            }
        
        return performance
    
    def rebalance_weights(self, new_weights: Dict[str, float]):
        """Rebalance strategy weights"""
        # Normalize weights to sum to 1
        total_weight = sum(new_weights.values())
        if total_weight > 0:
            for name in new_weights:
                new_weights[name] /= total_weight
        
        self.strategy_weights.update(new_weights)
        self.logger.info(f"Strategy weights rebalanced: {new_weights}")

# Example usage
if __name__ == "__main__":
    # This would be implemented by concrete strategy classes
    pass