"""
Momentum Breakout Strategy
Identifies stocks breaking out of consolidation patterns with strong momentum
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

from .base_strategy import BaseStrategy, Signal, SignalType, StrategyMetrics

class MomentumBreakoutStrategy(BaseStrategy):
    """
    Momentum breakout strategy that identifies stocks breaking out of consolidation
    with strong volume and momentum confirmation
    """
    
    def __init__(self, config: Dict = None):
        default_config = {
            'lookback_period': 20,
            'volume_threshold': 1.5,  # Volume must be 1.5x average
            'price_change_threshold': 0.02,  # 2% price change
            'consolidation_period': 10,  # Days to check for consolidation
            'breakout_confirmation': 3,  # Days to confirm breakout
            'rsi_threshold': 60,  # RSI must be above 60 for momentum
            'min_volume': 500000,  # Minimum daily volume
            'atr_multiplier': 2.0,  # ATR multiplier for stop loss
            'reward_risk_ratio': 2.0,  # Risk/reward ratio
            'max_position_size': 0.05  # Maximum 5% position size
        }
        
        if config:
            default_config.update(config)
        
        super().__init__("momentum_breakout", default_config)
        
        # Strategy-specific parameters
        self.lookback_period = self.config['lookback_period']
        self.volume_threshold = self.config['volume_threshold']
        self.price_change_threshold = self.config['price_change_threshold']
        self.consolidation_period = self.config['consolidation_period']
        self.breakout_confirmation = self.config['breakout_confirmation']
        self.rsi_threshold = self.config['rsi_threshold']
        self.atr_multiplier = self.config['atr_multiplier']
        self.reward_risk_ratio = self.config['reward_risk_ratio']
        
        self.logger.info(f"Momentum breakout strategy initialized with config: {self.config}")
    
    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """Generate momentum breakout signals"""
        signals = []
        
        for symbol, df in data.items():
            try:
                if df.empty or len(df) < self.lookback_period + 10:
                    continue
                
                # Preprocess data
                df = self.preprocess_data(df)
                
                # Calculate additional indicators
                df = self._calculate_momentum_indicators(df)
                
                # Check for breakout pattern
                breakout_signal = self._detect_breakout(df, symbol)
                
                if breakout_signal:
                    signals.append(breakout_signal)
                    
            except Exception as e:
                self.logger.error(f"Error processing {symbol}: {e}")
                continue
        
        self.last_update = datetime.now()
        self.signals_generated.extend(signals)
        
        self.logger.info(f"Generated {len(signals)} momentum breakout signals")
        return signals
    
    def _calculate_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate momentum-specific indicators"""
        df = df.copy()
        
        # RSI
        df['rsi'] = self.calculate_rsi(df['close'])
        
        # MACD
        df['macd'], df['macd_signal'], df['macd_histogram'] = self.calculate_macd(df['close'])
        
        # Bollinger Bands
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = self.calculate_bollinger_bands(df['close'])
        
        # Support and Resistance levels
        df['resistance'] = df['high'].rolling(window=self.lookback_period).max()
        df['support'] = df['low'].rolling(window=self.lookback_period).min()
        
        # Price relative to moving averages
        df['price_vs_sma20'] = df['close'] / df['sma_20']
        df['price_vs_sma50'] = df['close'] / df['sma_50']
        
        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(window=self.lookback_period).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        # Momentum indicators
        df['momentum'] = df['close'] / df['close'].shift(self.lookback_period)
        df['price_velocity'] = df['close'].pct_change(5)  # 5-day rate of change
        
        # Volatility squeeze detection
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        df['bb_squeeze'] = df['bb_width'] < df['bb_width'].rolling(window=20).mean()
        
        return df
    
    def _detect_breakout(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """Detect momentum breakout pattern"""
        if len(df) < self.lookback_period + 10:
            return None
        
        latest = df.iloc[-1]
        recent_data = df.iloc[-self.consolidation_period:]
        
        # Check basic filters
        if not self._basic_filters(latest, df):
            return None
        
        # 1. Consolidation detection
        if not self._detect_consolidation(recent_data):
            return None
        
        # 2. Breakout detection
        breakout_score = self._calculate_breakout_score(df, latest)
        if breakout_score < 0.6:
            return None
        
        # 3. Volume confirmation
        if not self._volume_confirmation(latest):
            return None
        
        # 4. Momentum confirmation
        if not self._momentum_confirmation(latest):
            return None
        
        # 5. Technical confirmation
        if not self._technical_confirmation(latest):
            return None
        
        # Calculate signal strength and confidence
        strength = min(breakout_score, 1.0)
        confidence = self._calculate_confidence(df, latest)
        
        # Create signal
        signal = Signal(
            symbol=symbol,
            signal_type=SignalType.BUY,
            strength=strength,
            confidence=confidence,
            timestamp=datetime.now(),
            price=latest['close'],
            metadata={
                'strategy': self.name,
                'breakout_score': breakout_score,
                'volume_ratio': latest['volume_ratio'],
                'rsi': latest['rsi'],
                'momentum': latest['momentum'],
                'resistance_level': latest['resistance'],
                'pattern': 'momentum_breakout'
            }
        )
        
        # Set stop loss and target
        signal.stop_loss = self._calculate_stop_loss(signal, df)
        signal.target_price = self._calculate_target_price(signal, df)
        
        return signal
    
    def _basic_filters(self, latest: pd.Series, df: pd.DataFrame) -> bool:
        """Apply basic filtering criteria"""
        # Price filters
        if latest['close'] < self.min_price or latest['close'] > self.max_price:
            return False
        
        # Volume filter
        if latest['volume'] < self.min_volume:
            return False
        
        # Trend filter - price above 20-day SMA
        if latest['close'] < latest['sma_20']:
            return False
        
        # Volatility filter - not too volatile
        if latest['volatility'] > 0.08:  # 8% daily volatility
            return False
        
        return True
    
    def _detect_consolidation(self, recent_data: pd.DataFrame) -> bool:
        """Detect if stock has been consolidating"""
        if len(recent_data) < self.consolidation_period:
            return False
        
        # Calculate range of recent prices
        high = recent_data['high'].max()
        low = recent_data['low'].min()
        avg_price = recent_data['close'].mean()
        
        # Range should be relatively small (consolidation)
        price_range = (high - low) / avg_price
        
        # Check if price has been range-bound
        if price_range > 0.15:  # 15% range is too wide
            return False
        
        # Check if volume has been declining (coiling)
        volume_trend = recent_data['volume'].iloc[-3:].mean() / recent_data['volume'].iloc[:3].mean()
        
        # Volume should be declining during consolidation
        if volume_trend > 1.2:  # Volume increasing too much
            return False
        
        return True
    
    def _calculate_breakout_score(self, df: pd.DataFrame, latest: pd.Series) -> float:
        """Calculate breakout score based on multiple factors"""
        score = 0.0
        
        # 1. Price breakout above resistance (30% weight)
        if latest['close'] > latest['resistance']:
            breakout_magnitude = (latest['close'] - latest['resistance']) / latest['resistance']
            score += min(breakout_magnitude * 10, 0.3)  # Cap at 30%
        
        # 2. Volume surge (25% weight)
        if latest['volume_ratio'] > self.volume_threshold:
            volume_score = min((latest['volume_ratio'] - 1) * 0.5, 0.25)
            score += volume_score
        
        # 3. RSI momentum (20% weight)
        if latest['rsi'] > self.rsi_threshold:
            rsi_score = min((latest['rsi'] - 50) / 50 * 0.2, 0.2)
            score += rsi_score
        
        # 4. MACD confirmation (15% weight)
        if latest['macd'] > latest['macd_signal'] and latest['macd_histogram'] > 0:
            score += 0.15
        
        # 5. Moving average alignment (10% weight)
        if latest['sma_20'] > latest['sma_50']:
            score += 0.1
        
        return score
    
    def _volume_confirmation(self, latest: pd.Series) -> bool:
        """Check volume confirmation for breakout"""
        return latest['volume_ratio'] >= self.volume_threshold
    
    def _momentum_confirmation(self, latest: pd.Series) -> bool:
        """Check momentum confirmation"""
        # RSI should show momentum
        if latest['rsi'] < self.rsi_threshold:
            return False
        
        # Price should be above recent average
        if latest['momentum'] < 1.02:  # 2% momentum over lookback period
            return False
        
        # Price velocity should be positive
        if latest['price_velocity'] < 0.01:  # 1% velocity
            return False
        
        return True
    
    def _technical_confirmation(self, latest: pd.Series) -> bool:
        """Check technical confirmation"""
        # MACD should be bullish
        if latest['macd'] <= latest['macd_signal']:
            return False
        
        # Price should be above middle Bollinger Band
        if latest['close'] < latest['bb_middle']:
            return False
        
        # Should not be extremely overbought
        if latest['rsi'] > 85:
            return False
        
        return True
    
    def _calculate_confidence(self, df: pd.DataFrame, latest: pd.Series) -> float:
        """Calculate signal confidence"""
        confidence = 0.0
        
        # Volume confidence (30%)
        if latest['volume_ratio'] > 2.0:
            confidence += 0.3
        elif latest['volume_ratio'] > self.volume_threshold:
            confidence += 0.2
        
        # Price action confidence (25%)
        if latest['close'] > latest['resistance'] * 1.01:  # 1% above resistance
            confidence += 0.25
        elif latest['close'] > latest['resistance']:
            confidence += 0.15
        
        # Momentum confidence (25%)
        if latest['rsi'] > 70:
            confidence += 0.25
        elif latest['rsi'] > self.rsi_threshold:
            confidence += 0.15
        
        # Technical confirmation (20%)
        if (latest['macd'] > latest['macd_signal'] and 
            latest['close'] > latest['bb_middle'] and
            latest['sma_20'] > latest['sma_50']):
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _calculate_stop_loss(self, signal: Signal, df: pd.DataFrame) -> float:
        """Calculate stop loss for momentum breakout"""
        latest = df.iloc[-1]
        
        # Use ATR-based stop loss
        if 'atr' in df.columns and latest['atr'] > 0:
            stop_loss = signal.price - (self.atr_multiplier * latest['atr'])
        else:
            # Fallback to percentage-based stop loss
            stop_loss = signal.price * 0.97  # 3% stop loss
        
        # Also consider support level
        if 'support' in df.columns:
            support_stop = latest['support'] * 0.98  # 2% below support
            stop_loss = max(stop_loss, support_stop)
        
        return stop_loss
    
    def _calculate_target_price(self, signal: Signal, df: pd.DataFrame) -> float:
        """Calculate target price for momentum breakout"""
        latest = df.iloc[-1]
        
        # Use ATR-based target
        if 'atr' in df.columns and latest['atr'] > 0:
            stop_distance = signal.price - signal.stop_loss
            target_price = signal.price + (self.reward_risk_ratio * stop_distance)
        else:
            # Fallback to percentage-based target
            target_price = signal.price * 1.06  # 6% target
        
        return target_price
    
    def calculate_position_size(self, signal: Signal, portfolio_value: float) -> float:
        """Calculate position size based on risk"""
        # Risk-based position sizing
        risk_amount = portfolio_value * 0.02  # 2% portfolio risk
        
        if signal.stop_loss:
            price_risk = signal.price - signal.stop_loss
            if price_risk > 0:
                position_size = risk_amount / price_risk
                max_position_value = portfolio_value * self.config['max_position_size']
                position_size = min(position_size, max_position_value / signal.price)
                return position_size
        
        # Fallback to percentage-based sizing
        return (portfolio_value * self.config['max_position_size']) / signal.price
    
    def get_strategy_description(self) -> str:
        """Get strategy description"""
        return """
        Momentum Breakout Strategy:
        - Identifies stocks breaking out of consolidation patterns
        - Requires volume confirmation (>1.5x average volume)
        - Uses RSI > 60 for momentum confirmation
        - Employs ATR-based stop losses and targets
        - Filters for liquid stocks with proper risk management
        """

# Example usage and backtesting
if __name__ == "__main__":
    import logging
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Create strategy
    strategy = MomentumBreakoutStrategy()
    
    # Example data (in real use, this would come from data feed)
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    
    # Create sample data for AAPL
    np.random.seed(42)
    price = 150
    data = []
    
    for i in range(100):
        # Simulate price movement
        change = np.random.normal(0, 0.02)
        price = price * (1 + change)
        
        # Add some trend and breakout pattern
        if i > 50:
            price += 0.5  # Simulate breakout
        
        volume = np.random.normal(1000000, 200000)
        if i > 60:  # Volume surge during breakout
            volume *= 2
        
        data.append({
            'open': price * 0.995,
            'high': price * 1.01,
            'low': price * 0.99,
            'close': price,
            'volume': volume
        })
    
    sample_data = pd.DataFrame(data, index=dates)
    
    # Test signal generation
    signals = strategy.generate_signals({'AAPL': sample_data})
    
    print(f"Generated {len(signals)} signals")
    for signal in signals:
        print(f"Signal: {signal.symbol} {signal.signal_type.value} "
              f"Strength: {signal.strength:.2f} Confidence: {signal.confidence:.2f}")
        print(f"Price: ${signal.price:.2f} Target: ${signal.target_price:.2f} "
              f"Stop: ${signal.stop_loss:.2f}")
    
    # Print strategy state
    print(f"\nStrategy State: {strategy.get_strategy_state()}")