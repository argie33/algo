#!/usr/bin/env python3
"""
Budget Alpha HFT System - Alpha Generation Engine
Advanced signal generation using ML and market microstructure analysis
Designed to compete with institutional alpha at fraction of the cost
"""

import asyncio
import time
import json
import logging
import os
import pickle
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import numpy as np
import pandas as pd
import redis
import xgboost as xgb
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.ensemble import IsolationForest
from sklearn.metrics import accuracy_score, precision_score, recall_score
import talib
import scipy.stats as stats
from concurrent.futures import ThreadPoolExecutor
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AlphaSignal:
    """Standardized alpha signal structure"""
    symbol: str
    timestamp: int
    signal_strength: float  # -1.0 to 1.0 (sell to buy)
    confidence: float      # 0.0 to 1.0
    strategy_name: str
    features: Dict[str, float]
    expected_return: float  # Expected return over next period
    risk_score: float      # Risk assessment 0.0 to 1.0
    time_horizon: int      # Expected signal duration in seconds
    
@dataclass
class MarketRegime:
    """Market regime classification"""
    regime_type: str       # 'trending', 'mean_reverting', 'volatile', 'calm'
    confidence: float
    volatility: float
    correlation: float
    volume_profile: str    # 'low', 'normal', 'high', 'surge'

class FeatureEngine:
    """Advanced feature engineering for alpha generation"""
    
    def __init__(self):
        self.lookback_periods = [5, 10, 20, 50, 100]
        self.volume_periods = [10, 30, 60]
        self.scalers = {}
        
    def extract_features(self, price_history: List[Dict], 
                        current_tick: Dict) -> Dict[str, float]:
        """Extract comprehensive feature set for ML models"""
        try:
            if len(price_history) < 100:
                return {}
                
            # Convert to arrays for vectorized operations
            prices = np.array([h['price'] for h in price_history])
            volumes = np.array([h['volume'] for h in price_history])
            timestamps = np.array([h['timestamp'] for h in price_history])
            bids = np.array([h.get('bid', h['price'] * 0.999) for h in price_history])
            asks = np.array([h.get('ask', h['price'] * 1.001) for h in price_history])
            
            features = {}
            
            # === PRICE FEATURES ===
            
            # 1. Returns at multiple timeframes
            for period in self.lookback_periods:
                if len(prices) > period:
                    ret = (prices[-1] - prices[-period]) / prices[-period]
                    features[f'return_{period}'] = ret
                    
                    # Log returns
                    log_ret = np.log(prices[-1] / prices[-period])
                    features[f'log_return_{period}'] = log_ret
            
            # 2. Technical indicators
            if len(prices) >= 50:
                # Moving averages
                sma_20 = talib.SMA(prices, timeperiod=20)[-1]
                ema_20 = talib.EMA(prices, timeperiod=20)[-1]
                features['sma_20_ratio'] = prices[-1] / sma_20 - 1
                features['ema_20_ratio'] = prices[-1] / ema_20 - 1
                
                # Bollinger Bands
                bb_upper, bb_middle, bb_lower = talib.BBANDS(prices, timeperiod=20)
                features['bb_position'] = (prices[-1] - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1])
                features['bb_width'] = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
                
                # RSI
                rsi = talib.RSI(prices, timeperiod=14)[-1]
                features['rsi'] = (rsi - 50) / 50  # Normalize to [-1, 1]
                
                # MACD
                macd, macd_signal, macd_hist = talib.MACD(prices)
                features['macd_signal'] = macd_hist[-1] if not np.isnan(macd_hist[-1]) else 0
                
                # ATR (volatility)
                high_prices = np.maximum(prices, np.roll(prices, 1))
                low_prices = np.minimum(prices, np.roll(prices, 1))
                atr = talib.ATR(high_prices, low_prices, prices, timeperiod=14)[-1]
                features['atr_ratio'] = atr / prices[-1]
            
            # 3. Volatility features
            for period in [10, 20, 50]:
                if len(prices) > period:
                    returns = np.diff(np.log(prices[-period:]))
                    vol = np.std(returns) * np.sqrt(390)  # Annualized
                    features[f'volatility_{period}'] = vol
                    
                    # Skewness and kurtosis
                    if len(returns) > 10:
                        features[f'skewness_{period}'] = stats.skew(returns)
                        features[f'kurtosis_{period}'] = stats.kurtosis(returns)
            
            # === VOLUME FEATURES ===
            
            # 4. Volume analysis
            for period in self.volume_periods:
                if len(volumes) > period:
                    avg_vol = np.mean(volumes[-period:])
                    if avg_vol > 0:
                        features[f'volume_ratio_{period}'] = volumes[-1] / avg_vol
                        
                        # Volume trend
                        vol_trend = np.polyfit(range(period), volumes[-period:], 1)[0]
                        features[f'volume_trend_{period}'] = vol_trend / avg_vol
            
            # Price-volume correlation
            if len(prices) >= 20 and len(volumes) >= 20:
                pv_corr = np.corrcoef(prices[-20:], volumes[-20:])[0, 1]
                features['price_volume_corr'] = pv_corr if not np.isnan(pv_corr) else 0
            
            # === MICROSTRUCTURE FEATURES ===
            
            # 5. Bid-ask spread analysis
            spreads = asks - bids
            if len(spreads) > 10:
                current_spread = spreads[-1] / prices[-1]
                avg_spread = np.mean(spreads[-10:]) / np.mean(prices[-10:])
                features['spread_ratio'] = current_spread
                features['spread_vs_avg'] = current_spread / avg_spread if avg_spread > 0 else 1
            
            # 6. Time-based features
            current_time = datetime.fromtimestamp(timestamps[-1] / 1_000_000)
            
            # Time of day (market hours effect)
            market_open = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = current_time.replace(hour=16, minute=0, second=0, microsecond=0)
            
            if market_open <= current_time <= market_close:
                minutes_from_open = (current_time - market_open).total_seconds() / 60
                minutes_to_close = (market_close - current_time).total_seconds() / 60
                features['time_from_open'] = minutes_from_open / 390  # Normalize to [0, 1]
                features['time_to_close'] = minutes_to_close / 390
            else:
                features['time_from_open'] = 0
                features['time_to_close'] = 0
            
            # Day of week
            features['day_of_week'] = current_time.weekday() / 6  # Normalize to [0, 1]
            
            # === MOMENTUM FEATURES ===
            
            # 7. Multi-timeframe momentum
            for period in [5, 15, 30]:
                if len(prices) > period:
                    momentum = talib.MOM(prices, timeperiod=period)[-1]
                    features[f'momentum_{period}'] = momentum / prices[-period] if prices[-period] > 0 else 0
            
            # Rate of change
            for period in [5, 10, 20]:
                if len(prices) > period:
                    roc = talib.ROC(prices, timeperiod=period)[-1]
                    features[f'roc_{period}'] = roc / 100  # Normalize percentage
            
            # === MEAN REVERSION FEATURES ===
            
            # 8. Distance from various means
            for period in [10, 20, 50]:
                if len(prices) > period:
                    mean_price = np.mean(prices[-period:])
                    distance = (prices[-1] - mean_price) / mean_price
                    features[f'distance_from_mean_{period}'] = distance
            
            # Z-score
            if len(prices) >= 20:
                z_score = (prices[-1] - np.mean(prices[-20:])) / np.std(prices[-20:])
                features['z_score_20'] = np.clip(z_score, -5, 5) / 5  # Normalize to [-1, 1]
            
            return features
            
        except Exception as e:
            logger.error(f"Feature extraction error: {e}")
            return {}

class MarketRegimeDetector:
    """Detect market regime for strategy selection"""
    
    def __init__(self):
        self.lookback = 100
        self.regime_history = deque(maxlen=1000)
    
    def detect_regime(self, price_data: Dict[str, List[Dict]]) -> MarketRegime:
        """Detect current market regime across symbols"""
        try:
            if not price_data:
                return MarketRegime('unknown', 0.0, 0.0, 0.0, 'normal')
            
            # Analyze SPY as market proxy
            spy_data = price_data.get('SPY', [])
            if len(spy_data) < self.lookback:
                return MarketRegime('unknown', 0.0, 0.0, 0.0, 'normal')
            
            prices = np.array([d['price'] for d in spy_data[-self.lookback:]])
            volumes = np.array([d['volume'] for d in spy_data[-self.lookback:]])
            
            # Calculate regime indicators
            returns = np.diff(np.log(prices))
            volatility = np.std(returns) * np.sqrt(390)  # Annualized
            
            # Trend strength
            trend_strength = abs(np.polyfit(range(len(prices)), prices, 1)[0]) / np.mean(prices)
            
            # Mean reversion tendency
            mean_reversion = self._calculate_mean_reversion(prices)
            
            # Volume profile
            avg_volume = np.mean(volumes)
            recent_volume = np.mean(volumes[-10:])
            volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
            
            # Correlation with other symbols
            correlations = self._calculate_cross_correlations(price_data)
            avg_correlation = np.mean(list(correlations.values())) if correlations else 0
            
            # Classify regime
            regime_type, confidence = self._classify_regime(
                volatility, trend_strength, mean_reversion, volume_ratio
            )
            
            # Volume profile classification
            if volume_ratio > 2.0:
                volume_profile = 'surge'
            elif volume_ratio > 1.5:
                volume_profile = 'high'
            elif volume_ratio < 0.7:
                volume_profile = 'low'
            else:
                volume_profile = 'normal'
            
            regime = MarketRegime(
                regime_type=regime_type,
                confidence=confidence,
                volatility=volatility,
                correlation=avg_correlation,
                volume_profile=volume_profile
            )
            
            self.regime_history.append(regime)
            return regime
            
        except Exception as e:
            logger.error(f"Regime detection error: {e}")
            return MarketRegime('unknown', 0.0, 0.0, 0.0, 'normal')
    
    def _calculate_mean_reversion(self, prices: np.ndarray) -> float:
        """Calculate mean reversion tendency"""
        # Hurst exponent estimation
        if len(prices) < 20:
            return 0.5
        
        lags = range(2, min(20, len(prices) // 4))
        tau = [np.sqrt(np.std(np.subtract(prices[lag:], prices[:-lag]))) for lag in lags]
        
        # Linear regression on log-log plot
        if len(tau) > 5:
            poly = np.polyfit(np.log(lags), np.log(tau), 1)
            hurst = poly[0]
            
            # Convert to mean reversion score
            # Hurst < 0.5: mean reverting, Hurst > 0.5: trending
            return max(0, 1 - 2 * hurst)  # Higher score = more mean reverting
        
        return 0.5
    
    def _calculate_cross_correlations(self, price_data: Dict[str, List[Dict]]) -> Dict[str, float]:
        """Calculate correlations between symbols"""
        correlations = {}
        
        # Reference symbols for correlation
        ref_symbols = ['SPY', 'QQQ', 'IWM']
        available_refs = [s for s in ref_symbols if s in price_data]
        
        if not available_refs:
            return correlations
        
        ref_symbol = available_refs[0]
        ref_prices = [d['price'] for d in price_data[ref_symbol][-50:]]
        
        for symbol, data in price_data.items():
            if symbol == ref_symbol or len(data) < 50:
                continue
                
            symbol_prices = [d['price'] for d in data[-50:]]
            if len(symbol_prices) == len(ref_prices):
                corr = np.corrcoef(ref_prices, symbol_prices)[0, 1]
                if not np.isnan(corr):
                    correlations[symbol] = corr
        
        return correlations
    
    def _classify_regime(self, volatility: float, trend_strength: float, 
                        mean_reversion: float, volume_ratio: float) -> Tuple[str, float]:
        """Classify market regime based on indicators"""
        
        # Thresholds (these would be optimized based on historical data)
        high_vol_threshold = 0.25
        low_vol_threshold = 0.15
        strong_trend_threshold = 0.002
        strong_mean_reversion_threshold = 0.7
        
        confidence = 0.5  # Base confidence
        
        if volatility > high_vol_threshold:
            if trend_strength > strong_trend_threshold:
                regime_type = 'trending'
                confidence = min(0.9, 0.5 + volatility + trend_strength)
            else:
                regime_type = 'volatile'
                confidence = min(0.9, 0.5 + volatility)
        elif volatility < low_vol_threshold:
            if mean_reversion > strong_mean_reversion_threshold:
                regime_type = 'mean_reverting'
                confidence = min(0.9, 0.5 + mean_reversion)
            else:
                regime_type = 'calm'
                confidence = min(0.9, 0.5 + (1 - volatility))
        else:
            # Mixed regime
            if trend_strength > mean_reversion:
                regime_type = 'trending'
                confidence = 0.4 + trend_strength
            else:
                regime_type = 'mean_reverting'
                confidence = 0.4 + mean_reversion
        
        return regime_type, confidence

class MLAlphaEngine:
    """Machine learning based alpha generation"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.models = {}
        self.scalers = {}
        self.feature_names = []
        self.training_data = deque(maxlen=10000)
        self.prediction_history = deque(maxlen=1000)
        self.performance_metrics = {}
        
        # Model parameters
        self.xgb_params = {
            'objective': 'reg:squarederror',
            'max_depth': 6,
            'learning_rate': 0.1,
            'n_estimators': 100,
            'random_state': 42,
            'n_jobs': 2
        }
        
        self.lgb_params = {
            'objective': 'regression',
            'max_depth': 6,
            'learning_rate': 0.1,
            'n_estimators': 100,
            'random_state': 42,
            'n_jobs': 2,
            'verbose': -1
        }
    
    def prepare_training_data(self, historical_data: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare training data for ML models"""
        try:
            if len(historical_data) < 200:
                return None, None
            
            feature_engine = FeatureEngine()
            X, y = [], []
            
            # Create features and labels
            for i in range(100, len(historical_data) - 10):  # Need lookback and forward window
                price_history = historical_data[:i+1]
                current_tick = historical_data[i]
                
                # Extract features
                features = feature_engine.extract_features(price_history, current_tick)
                if not features:
                    continue
                
                # Calculate future return (label)
                current_price = historical_data[i]['price']
                future_price = historical_data[i + 10]['price']  # 10-period forward return
                future_return = (future_price - current_price) / current_price
                
                X.append(list(features.values()))
                y.append(future_return)
                
                # Store feature names from first iteration
                if not self.feature_names:
                    self.feature_names = list(features.keys())
            
            if len(X) < 50:
                return None, None
            
            X = np.array(X)
            y = np.array(y)
            
            # Remove outliers
            outlier_detector = IsolationForest(contamination=0.1, random_state=42)
            outlier_mask = outlier_detector.fit_predict(X) == 1
            
            X = X[outlier_mask]
            y = y[outlier_mask]
            
            return X, y
            
        except Exception as e:
            logger.error(f"Training data preparation error for {self.symbol}: {e}")
            return None, None
    
    def train_models(self, X: np.ndarray, y: np.ndarray):
        """Train ensemble of ML models"""
        try:
            if X is None or y is None or len(X) < 50:
                return
            
            # Split data
            split_idx = int(len(X) * 0.8)
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]
            
            # Scale features
            scaler = RobustScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            self.scalers['main'] = scaler
            
            # Train XGBoost
            xgb_model = xgb.XGBRegressor(**self.xgb_params)
            xgb_model.fit(X_train_scaled, y_train)
            self.models['xgboost'] = xgb_model
            
            # Train LightGBM
            lgb_model = lgb.LGBMRegressor(**self.lgb_params)
            lgb_model.fit(X_train_scaled, y_train)
            self.models['lightgbm'] = lgb_model
            
            # Evaluate models
            for name, model in self.models.items():
                y_pred = model.predict(X_test_scaled)
                
                # Calculate metrics
                mse = np.mean((y_test - y_pred) ** 2)
                corr = np.corrcoef(y_test, y_pred)[0, 1] if len(y_test) > 1 else 0
                
                # Directional accuracy
                direction_accuracy = np.mean(np.sign(y_test) == np.sign(y_pred))
                
                self.performance_metrics[name] = {
                    'mse': mse,
                    'correlation': corr if not np.isnan(corr) else 0,
                    'direction_accuracy': direction_accuracy,
                    'samples': len(y_test)
                }
            
            logger.info(f"Models trained for {self.symbol}: "
                       f"XGB corr={self.performance_metrics.get('xgboost', {}).get('correlation', 0):.3f}, "
                       f"LGB corr={self.performance_metrics.get('lightgbm', {}).get('correlation', 0):.3f}")
            
        except Exception as e:
            logger.error(f"Model training error for {self.symbol}: {e}")
    
    def generate_prediction(self, features: Dict[str, float]) -> Tuple[float, float]:
        """Generate prediction from ensemble of models"""
        try:
            if not self.models or not features:
                return 0.0, 0.0
            
            # Prepare feature vector
            feature_vector = []
            for name in self.feature_names:
                feature_vector.append(features.get(name, 0.0))
            
            if len(feature_vector) == 0:
                return 0.0, 0.0
            
            X = np.array(feature_vector).reshape(1, -1)
            
            # Scale features
            if 'main' in self.scalers:
                X_scaled = self.scalers['main'].transform(X)
            else:
                X_scaled = X
            
            # Get predictions from each model
            predictions = []
            weights = []
            
            for name, model in self.models.items():
                try:
                    pred = model.predict(X_scaled)[0]
                    predictions.append(pred)
                    
                    # Weight by model performance
                    corr = self.performance_metrics.get(name, {}).get('correlation', 0)
                    dir_acc = self.performance_metrics.get(name, {}).get('direction_accuracy', 0)
                    weight = max(0.1, (corr + dir_acc) / 2)  # Minimum weight of 0.1
                    weights.append(weight)
                    
                except Exception as e:
                    logger.debug(f"Prediction error for model {name}: {e}")
                    continue
            
            if not predictions:
                return 0.0, 0.0
            
            # Ensemble prediction (weighted average)
            weights = np.array(weights)
            weights = weights / np.sum(weights)  # Normalize weights
            
            ensemble_prediction = np.average(predictions, weights=weights)
            confidence = np.std(predictions) if len(predictions) > 1 else 0.5
            confidence = max(0.1, 1.0 - confidence)  # Higher std = lower confidence
            
            return ensemble_prediction, confidence
            
        except Exception as e:
            logger.error(f"Prediction error for {self.symbol}: {e}")
            return 0.0, 0.0

class AlphaGenerationEngine:
    """Main alpha generation engine coordinating all strategies"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis_client = redis.Redis(
            host=config.get('redis_host', 'localhost'),
            port=config.get('redis_port', 6379),
            decode_responses=True
        )
        
        # Core components
        self.feature_engine = FeatureEngine()
        self.regime_detector = MarketRegimeDetector()
        self.ml_engines = {}  # symbol -> MLAlphaEngine
        
        # Strategy weights based on market regime
        self.strategy_weights = {
            'trending': {'ml_momentum': 0.4, 'breakout': 0.3, 'mean_reversion': 0.1, 'microstructure': 0.2},
            'mean_reverting': {'ml_momentum': 0.1, 'breakout': 0.1, 'mean_reversion': 0.5, 'microstructure': 0.3},
            'volatile': {'ml_momentum': 0.2, 'breakout': 0.2, 'mean_reversion': 0.3, 'microstructure': 0.3},
            'calm': {'ml_momentum': 0.3, 'breakout': 0.2, 'mean_reversion': 0.2, 'microstructure': 0.3}
        }
        
        # Performance tracking
        self.signal_history = defaultdict(lambda: deque(maxlen=1000))
        self.performance_metrics = defaultdict(dict)
        
        # Thread pool for parallel processing
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    async def generate_alpha_signals(self, symbols: List[str]) -> Dict[str, AlphaSignal]:
        """Generate alpha signals for all symbols"""
        try:
            # Get market data for all symbols
            price_data = await self._get_price_data(symbols)
            
            # Detect market regime
            current_regime = self.regime_detector.detect_regime(price_data)
            
            # Generate signals for each symbol
            signals = {}
            tasks = []
            
            for symbol in symbols:
                if symbol in price_data and len(price_data[symbol]) > 100:
                    task = asyncio.create_task(
                        self._generate_symbol_signal(symbol, price_data[symbol], current_regime)
                    )
                    tasks.append((symbol, task))
            
            # Wait for all signals
            for symbol, task in tasks:
                try:
                    signal = await task
                    if signal and signal.confidence > 0.1:  # Filter low-confidence signals
                        signals[symbol] = signal
                except Exception as e:
                    logger.error(f"Signal generation error for {symbol}: {e}")
            
            logger.info(f"Generated {len(signals)} signals in {current_regime.regime_type} regime")
            return signals
            
        except Exception as e:
            logger.error(f"Alpha signal generation error: {e}")
            return {}
    
    async def _get_price_data(self, symbols: List[str]) -> Dict[str, List[Dict]]:
        """Get recent price data for symbols from Redis"""
        price_data = {}
        
        for symbol in symbols:
            try:
                # Get time-series data from Redis
                ts_key = f"ts:{symbol}"
                raw_data = self.redis_client.zrevrange(ts_key, 0, 999, withscores=True)
                
                if raw_data:
                    symbol_data = []
                    for data_json, timestamp in raw_data:
                        tick_data = json.loads(data_json)
                        symbol_data.append({
                            'timestamp': int(timestamp),
                            'price': float(tick_data['last_price']),
                            'volume': int(tick_data.get('last_size', 0)),
                            'bid': float(tick_data.get('bid', tick_data['last_price'])),
                            'ask': float(tick_data.get('ask', tick_data['last_price']))
                        })
                    
                    # Sort by timestamp (oldest first)
                    symbol_data.sort(key=lambda x: x['timestamp'])
                    price_data[symbol] = symbol_data
                    
            except Exception as e:
                logger.debug(f"Error getting price data for {symbol}: {e}")
        
        return price_data
    
    async def _generate_symbol_signal(self, symbol: str, price_history: List[Dict], 
                                     regime: MarketRegime) -> Optional[AlphaSignal]:
        """Generate comprehensive alpha signal for a symbol"""
        try:
            if len(price_history) < 100:
                return None
            
            current_tick = price_history[-1]
            
            # Extract features
            features = self.feature_engine.extract_features(price_history, current_tick)
            if not features:
                return None
            
            # Initialize ML engine if not exists
            if symbol not in self.ml_engines:
                self.ml_engines[symbol] = MLAlphaEngine(symbol)
                
                # Train model if we have enough historical data
                if len(price_history) > 500:
                    X, y = self.ml_engines[symbol].prepare_training_data(price_history)
                    if X is not None:
                        await asyncio.get_event_loop().run_in_executor(
                            self.executor,
                            self.ml_engines[symbol].train_models,
                            X, y
                        )
            
            # Generate ML prediction
            ml_prediction, ml_confidence = self.ml_engines[symbol].generate_prediction(features)
            
            # Generate rule-based signals
            momentum_signal = self._generate_momentum_signal(features, regime)
            mean_reversion_signal = self._generate_mean_reversion_signal(features, regime)
            breakout_signal = self._generate_breakout_signal(features, regime)
            microstructure_signal = self._generate_microstructure_signal(features, regime)
            
            # Combine signals based on regime
            weights = self.strategy_weights.get(regime.regime_type, self.strategy_weights['calm'])
            
            combined_signal = (
                weights['ml_momentum'] * ml_prediction +
                weights['breakout'] * breakout_signal +
                weights['mean_reversion'] * mean_reversion_signal +
                weights['microstructure'] * microstructure_signal
            )
            
            # Calculate confidence
            signal_confidences = [ml_confidence, 0.7, 0.6, 0.8]  # Confidence for each strategy
            weighted_confidence = sum(w * c for w, c in zip(weights.values(), signal_confidences))
            
            # Adjust for regime confidence
            final_confidence = weighted_confidence * regime.confidence
            
            # Risk assessment
            risk_score = self._calculate_risk_score(features, regime)
            
            # Expected return estimation
            expected_return = combined_signal * 0.001  # Scale to reasonable return expectation
            
            # Time horizon based on signal strength and regime
            if abs(combined_signal) > 0.5:
                time_horizon = 300  # 5 minutes for strong signals
            elif abs(combined_signal) > 0.2:
                time_horizon = 900  # 15 minutes for medium signals
            else:
                time_horizon = 1800  # 30 minutes for weak signals
            
            signal = AlphaSignal(
                symbol=symbol,
                timestamp=current_tick['timestamp'],
                signal_strength=np.clip(combined_signal, -1.0, 1.0),
                confidence=min(final_confidence, 1.0),
                strategy_name=f"ensemble_{regime.regime_type}",
                features=features,
                expected_return=expected_return,
                risk_score=risk_score,
                time_horizon=time_horizon
            )
            
            # Store signal history for performance tracking
            self.signal_history[symbol].append(signal)
            
            return signal
            
        except Exception as e:
            logger.error(f"Symbol signal generation error for {symbol}: {e}")
            return None
    
    def _generate_momentum_signal(self, features: Dict[str, float], regime: MarketRegime) -> float:
        """Generate momentum-based signal"""
        try:
            momentum_features = [
                'momentum_5', 'momentum_15', 'momentum_30',
                'roc_5', 'roc_10', 'roc_20'
            ]
            
            momentum_values = [features.get(f, 0) for f in momentum_features]
            momentum_signal = np.mean(momentum_values)
            
            # Adjust for regime
            if regime.regime_type == 'trending':
                momentum_signal *= 1.2  # Amplify in trending markets
            elif regime.regime_type == 'mean_reverting':
                momentum_signal *= 0.5  # Reduce in mean-reverting markets
            
            return np.clip(momentum_signal, -1.0, 1.0)
            
        except Exception as e:
            logger.error(f"Momentum signal error: {e}")
            return 0.0
    
    def _generate_mean_reversion_signal(self, features: Dict[str, float], regime: MarketRegime) -> float:
        """Generate mean reversion signal"""
        try:
            # Use z-score and distance from means
            z_score = features.get('z_score_20', 0)
            distance_means = [
                features.get('distance_from_mean_10', 0),
                features.get('distance_from_mean_20', 0),
                features.get('distance_from_mean_50', 0)
            ]
            
            avg_distance = np.mean(distance_means)
            
            # Mean reversion signal is opposite of deviation
            reversion_signal = -(z_score * 0.5 + avg_distance * 0.5)
            
            # Adjust for regime
            if regime.regime_type == 'mean_reverting':
                reversion_signal *= 1.5
            elif regime.regime_type == 'trending':
                reversion_signal *= 0.3
            
            return np.clip(reversion_signal, -1.0, 1.0)
            
        except Exception as e:
            logger.error(f"Mean reversion signal error: {e}")
            return 0.0
    
    def _generate_breakout_signal(self, features: Dict[str, float], regime: MarketRegime) -> float:
        """Generate breakout signal"""
        try:
            # Bollinger band position and volatility
            bb_position = features.get('bb_position', 0.5)
            bb_width = features.get('bb_width', 0)
            atr_ratio = features.get('atr_ratio', 0)
            volume_surge = features.get('volume_surge', 1)
            
            # Breakout conditions
            if bb_position > 0.9:  # Near upper band
                breakout_signal = 0.5 * (bb_position - 0.9) * 10  # Scale
            elif bb_position < 0.1:  # Near lower band
                breakout_signal = -0.5 * (0.1 - bb_position) * 10
            else:
                breakout_signal = 0
            
            # Amplify with volume
            if volume_surge > 1.5:
                breakout_signal *= min(volume_surge, 3.0)
            
            # Adjust for volatility
            if atr_ratio > 0.02:  # High volatility
                breakout_signal *= 1.2
            
            return np.clip(breakout_signal, -1.0, 1.0)
            
        except Exception as e:
            logger.error(f"Breakout signal error: {e}")
            return 0.0
    
    def _generate_microstructure_signal(self, features: Dict[str, float], regime: MarketRegime) -> float:
        """Generate microstructure-based signal"""
        try:
            # Order book imbalance
            ob_imbalance = features.get('order_book_imbalance', 0)
            
            # Spread analysis
            spread_ratio = features.get('spread_ratio', 0)
            spread_vs_avg = features.get('spread_vs_avg', 1)
            
            # Price-volume correlation
            pv_corr = features.get('price_volume_corr', 0)
            
            # Time-based effects
            time_from_open = features.get('time_from_open', 0)
            time_to_close = features.get('time_to_close', 0)
            
            # Microstructure signal components
            micro_signal = 0
            
            # Order book imbalance (primary signal)
            micro_signal += ob_imbalance * 0.4
            
            # Tight spreads favor momentum, wide spreads favor reversion
            if spread_vs_avg < 0.8:  # Tight spread
                micro_signal += 0.2
            elif spread_vs_avg > 1.2:  # Wide spread
                micro_signal -= 0.2
            
            # Price-volume correlation
            micro_signal += pv_corr * 0.2
            
            # Time effects (higher activity at open/close)
            if time_from_open < 0.1 or time_to_close < 0.1:  # First/last hour
                micro_signal *= 1.2
            
            return np.clip(micro_signal, -1.0, 1.0)
            
        except Exception as e:
            logger.error(f"Microstructure signal error: {e}")
            return 0.0
    
    def _calculate_risk_score(self, features: Dict[str, float], regime: MarketRegime) -> float:
        """Calculate risk score for the signal"""
        try:
            # Volatility-based risk
            volatility_features = [f'volatility_{p}' for p in [10, 20, 50]]
            avg_volatility = np.mean([features.get(f, 0) for f in volatility_features])
            
            # Spread-based risk
            spread_risk = features.get('spread_ratio', 0) * 100  # Convert to bps
            
            # Volume risk (low volume = higher risk)
            volume_risk = 1.0 / max(features.get('volume_ratio_30', 1), 0.1)
            
            # Time-based risk (closer to close = higher risk)
            time_risk = 1.0 - features.get('time_to_close', 1)
            
            # Regime-based risk
            regime_risk = 1.0 - regime.confidence
            
            # Combine risk factors
            total_risk = (
                avg_volatility * 0.3 +
                min(spread_risk, 1.0) * 0.2 +
                min(volume_risk, 1.0) * 0.2 +
                time_risk * 0.1 +
                regime_risk * 0.2
            )
            
            return min(total_risk, 1.0)
            
        except Exception as e:
            logger.error(f"Risk calculation error: {e}")
            return 0.5

async def main():
    """Test the alpha generation engine"""
    config = {
        'redis_host': os.getenv('REDIS_HOST', 'localhost'),
        'redis_port': int(os.getenv('REDIS_PORT', 6379))
    }
    
    # Test symbols
    test_symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'TSLA']
    
    # Initialize engine
    engine = AlphaGenerationEngine(config)
    
    # Generate signals
    logger.info("Generating alpha signals...")
    signals = await engine.generate_alpha_signals(test_symbols)
    
    # Display results
    for symbol, signal in signals.items():
        logger.info(f"{symbol}: Signal={signal.signal_strength:.3f}, "
                   f"Confidence={signal.confidence:.3f}, "
                   f"Strategy={signal.strategy_name}")

if __name__ == "__main__":
    asyncio.run(main())