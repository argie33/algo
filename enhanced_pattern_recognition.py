#!/usr/bin/env python3
"""
Enhanced Pattern Recognition Service with AI/ML Integration
Uses modern techniques including deep learning, ensemble methods, and real-time analysis
"""

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import asyncio
import concurrent.futures
from abc import ABC, abstractmethod

# ML/AI imports
try:
    import tensorflow as tf
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler, MinMaxScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    import joblib
    HAS_ML = True
except ImportError:
    HAS_ML = False
    print("Warning: ML libraries not available. Install tensorflow, scikit-learn for full functionality")

# Technical analysis imports
try:
    import talib
    import ta
    HAS_TA = True
except ImportError:
    HAS_TA = False
    print("Warning: TA libraries not available. Install TA-Lib, ta for technical indicators")

# Database imports
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
import boto3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PatternResult:
    """Enhanced pattern detection result with ML confidence scoring"""
    pattern_name: str
    category: str
    confidence: float
    ml_confidence: Optional[float]
    traditional_confidence: float
    signal_strength: str
    direction: str
    start_date: datetime
    end_date: Optional[datetime]
    target_price: Optional[float]
    stop_loss: Optional[float]
    risk_reward_ratio: Optional[float]
    pattern_data: Dict[str, Any]
    key_levels: Dict[str, float]
    volume_confirmation: bool
    momentum_confirmation: bool

class PatternDetector(ABC):
    """Abstract base class for pattern detectors"""
    
    @abstractmethod
    def detect(self, data: pd.DataFrame) -> List[PatternResult]:
        pass
    
    @abstractmethod
    def get_pattern_info(self) -> Dict[str, Any]:
        pass

class MLPatternDetector(PatternDetector):
    """AI/ML-based pattern detector using multiple models"""
    
    def __init__(self, model_config: Dict[str, Any] = None):
        self.model_config = model_config or {}
        self.models = {}
        self.scalers = {}
        self.feature_extractors = {}
        self.confidence_threshold = 0.75
        
        if HAS_ML:
            self._initialize_models()
    
    def _initialize_models(self):
        """Initialize ML models for pattern detection"""
        
        # CNN for image-like pattern recognition
        if 'cnn' in self.model_config.get('enabled_models', ['rf', 'gb', 'mlp']):
            self.models['cnn'] = self._create_cnn_model()
        
        # Random Forest for feature-based detection
        self.models['random_forest'] = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        
        # Gradient Boosting for complex patterns
        self.models['gradient_boost'] = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=6,
            random_state=42
        )
        
        # Neural Network for non-linear patterns
        self.models['mlp'] = MLPClassifier(
            hidden_layer_sizes=(128, 64, 32),
            activation='relu',
            solver='adam',
            max_iter=500,
            random_state=42
        )
        
        # Initialize scalers
        for model_name in self.models:
            self.scalers[model_name] = StandardScaler()
    
    def _create_cnn_model(self):
        """Create CNN model for pattern recognition"""
        if not HAS_ML:
            return None
            
        model = tf.keras.Sequential([
            tf.keras.layers.Conv1D(64, 3, activation='relu', input_shape=(50, 5)),  # OHLCV
            tf.keras.layers.MaxPooling1D(2),
            tf.keras.layers.Conv1D(32, 3, activation='relu'),
            tf.keras.layers.MaxPooling1D(2),
            tf.keras.layers.Conv1D(16, 3, activation='relu'),
            tf.keras.layers.GlobalMaxPooling1D(),
            tf.keras.layers.Dense(50, activation='relu'),
            tf.keras.layers.Dropout(0.3),
            tf.keras.layers.Dense(25, activation='relu'),
            tf.keras.layers.Dense(3, activation='softmax')  # bullish, bearish, neutral
        ])
        
        model.compile(
            optimizer='adam',
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        
        return model
    
    def extract_features(self, data: pd.DataFrame) -> np.ndarray:
        """Extract comprehensive features for ML models"""
        features = []
        
        # Price-based features
        if len(data) >= 50:
            # Moving averages
            data['ma_5'] = data['close'].rolling(5).mean()
            data['ma_10'] = data['close'].rolling(10).mean()
            data['ma_20'] = data['close'].rolling(20).mean()
            data['ma_50'] = data['close'].rolling(50).mean()
            
            # Price ratios
            features.extend([
                (data['close'].iloc[-1] / data['ma_5'].iloc[-1]) if pd.notna(data['ma_5'].iloc[-1]) else 1,
                (data['close'].iloc[-1] / data['ma_10'].iloc[-1]) if pd.notna(data['ma_10'].iloc[-1]) else 1,
                (data['close'].iloc[-1] / data['ma_20'].iloc[-1]) if pd.notna(data['ma_20'].iloc[-1]) else 1,
                (data['close'].iloc[-1] / data['ma_50'].iloc[-1]) if pd.notna(data['ma_50'].iloc[-1]) else 1,
            ])
            
            # Volatility features
            data['returns'] = data['close'].pct_change()
            volatility_5 = data['returns'].rolling(5).std()
            volatility_20 = data['returns'].rolling(20).std()
            features.extend([
                volatility_5.iloc[-1] if pd.notna(volatility_5.iloc[-1]) else 0,
                volatility_20.iloc[-1] if pd.notna(volatility_20.iloc[-1]) else 0,
                volatility_5.iloc[-1] / volatility_20.iloc[-1] if pd.notna(volatility_20.iloc[-1]) and volatility_20.iloc[-1] > 0 else 1
            ])
        
        # Technical indicators if available
        if HAS_TA and len(data) >= 20:
            try:
                # RSI
                rsi = talib.RSI(data['close'].values, timeperiod=14)
                features.append(rsi[-1] if not np.isnan(rsi[-1]) else 50)
                
                # MACD
                macd, macd_signal, macd_hist = talib.MACD(data['close'].values)
                features.extend([
                    macd[-1] if not np.isnan(macd[-1]) else 0,
                    macd_signal[-1] if not np.isnan(macd_signal[-1]) else 0,
                    macd_hist[-1] if not np.isnan(macd_hist[-1]) else 0
                ])
                
                # Bollinger Bands
                bb_upper, bb_middle, bb_lower = talib.BBANDS(data['close'].values)
                bb_position = (data['close'].iloc[-1] - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1]) if not np.isnan(bb_upper[-1]) else 0.5
                features.append(bb_position)
                
                # Stochastic
                stoch_k, stoch_d = talib.STOCH(data['high'].values, data['low'].values, data['close'].values)
                features.extend([
                    stoch_k[-1] if not np.isnan(stoch_k[-1]) else 50,
                    stoch_d[-1] if not np.isnan(stoch_d[-1]) else 50
                ])
                
            except Exception as e:
                logger.warning(f"Error calculating technical indicators: {e}")
                # Fill with default values
                features.extend([50, 0, 0, 0, 0.5, 50, 50])
        
        # Volume features
        if 'volume' in data.columns and len(data) >= 20:
            vol_ma_20 = data['volume'].rolling(20).mean()
            vol_ratio = data['volume'].iloc[-1] / vol_ma_20.iloc[-1] if pd.notna(vol_ma_20.iloc[-1]) and vol_ma_20.iloc[-1] > 0 else 1
            features.append(vol_ratio)
            
            # Price-volume correlation
            pv_corr = data['close'].rolling(20).corr(data['volume'])
            features.append(pv_corr.iloc[-1] if pd.notna(pv_corr.iloc[-1]) else 0)
        else:
            features.extend([1, 0])  # Default volume features
        
        # Candlestick features
        if len(data) >= 5:
            # Body size ratios
            recent_data = data.tail(5)
            body_sizes = abs(recent_data['close'] - recent_data['open']) / (recent_data['high'] - recent_data['low'])
            features.append(body_sizes.mean())
            
            # Upper/lower shadow ratios
            upper_shadows = (recent_data['high'] - recent_data[['open', 'close']].max(axis=1)) / (recent_data['high'] - recent_data['low'])
            lower_shadows = (recent_data[['open', 'close']].min(axis=1) - recent_data['low']) / (recent_data['high'] - recent_data['low'])
            features.extend([upper_shadows.mean(), lower_shadows.mean()])
        else:
            features.extend([0.5, 0.25, 0.25])  # Default candlestick features
        
        # Ensure we have at least 20 features for consistency
        while len(features) < 20:
            features.append(0)
        
        return np.array(features[:20])  # Limit to first 20 features for consistency
    
    def detect(self, data: pd.DataFrame) -> List[PatternResult]:
        """Detect patterns using ML models"""
        if not HAS_ML or len(data) < 20:
            return []
        
        try:
            # Extract features
            features = self.extract_features(data)
            
            # Make predictions with all models
            predictions = {}
            confidences = {}
            
            for model_name, model in self.models.items():
                if model_name == 'cnn':
                    # Prepare CNN input (sequence of OHLCV)
                    if len(data) >= 50:
                        cnn_input = data[['open', 'high', 'low', 'close', 'volume']].tail(50).values
                        cnn_input = cnn_input.reshape(1, 50, 5)
                        cnn_input = self.scalers[model_name].fit_transform(cnn_input.reshape(-1, 5)).reshape(1, 50, 5)
                        pred = model.predict(cnn_input, verbose=0)
                        predictions[model_name] = np.argmax(pred[0])
                        confidences[model_name] = np.max(pred[0])
                else:
                    # Traditional ML models
                    if hasattr(model, 'predict_proba'):
                        features_scaled = self.scalers[model_name].fit_transform(features.reshape(1, -1))
                        prob = model.predict_proba(features_scaled)[0] if hasattr(model, 'predict_proba') else [0.33, 0.33, 0.34]
                        predictions[model_name] = np.argmax(prob)
                        confidences[model_name] = np.max(prob)
            
            # Ensemble prediction
            if predictions:
                ensemble_pred = max(set(predictions.values()), key=list(predictions.values()).count)
                ensemble_confidence = np.mean(list(confidences.values()))
                
                if ensemble_confidence >= self.confidence_threshold:
                    direction_map = {0: 'bullish', 1: 'bearish', 2: 'neutral'}
                    strength_map = {
                        (0.75, 1.0): 'very_strong',
                        (0.65, 0.75): 'strong',
                        (0.55, 0.65): 'moderate',
                        (0.0, 0.55): 'weak'
                    }
                    
                    signal_strength = next(
                        strength for (low, high), strength in strength_map.items()
                        if low <= ensemble_confidence < high
                    )
                    
                    return [PatternResult(
                        pattern_name=f"ML {direction_map[ensemble_pred].title()} Pattern",
                        category='ml_based',
                        confidence=ensemble_confidence,
                        ml_confidence=ensemble_confidence,
                        traditional_confidence=0.0,
                        signal_strength=signal_strength,
                        direction=direction_map[ensemble_pred],
                        start_date=data.index[-20] if len(data) >= 20 else data.index[0],
                        end_date=data.index[-1],
                        target_price=None,
                        stop_loss=None,
                        risk_reward_ratio=None,
                        pattern_data={
                            'model_predictions': predictions,
                            'model_confidences': confidences,
                            'ensemble_confidence': ensemble_confidence,
                            'features_used': features.tolist()
                        },
                        key_levels={},
                        volume_confirmation=features[-3] > 1.2 if len(features) > 3 else False,
                        momentum_confirmation=features[0] > 1.02 if len(features) > 0 else False
                    )]
            
        except Exception as e:
            logger.error(f"Error in ML pattern detection: {e}")
        
        return []
    
    def get_pattern_info(self) -> Dict[str, Any]:
        return {
            'name': 'ML Pattern Detector',
            'type': 'ml_based',
            'models': list(self.models.keys()),
            'confidence_threshold': self.confidence_threshold,
            'requires_training': True
        }

class CandlestickPatternDetector(PatternDetector):
    """Enhanced candlestick pattern detector with volume and momentum confirmation"""
    
    def detect(self, data: pd.DataFrame) -> List[PatternResult]:
        patterns = []
        
        if len(data) < 3:
            return patterns
        
        # Get recent candles
        recent = data.tail(5)
        
        # Doji patterns
        doji_patterns = self._detect_doji_patterns(recent)
        patterns.extend(doji_patterns)
        
        # Engulfing patterns
        if len(recent) >= 2:
            engulfing = self._detect_engulfing_patterns(recent.tail(2))
            patterns.extend(engulfing)
        
        # Star patterns
        if len(recent) >= 3:
            star_patterns = self._detect_star_patterns(recent.tail(3))
            patterns.extend(star_patterns)
        
        # Hammer patterns
        hammer_patterns = self._detect_hammer_patterns(recent)
        patterns.extend(hammer_patterns)
        
        return patterns
    
    def _detect_doji_patterns(self, data: pd.DataFrame) -> List[PatternResult]:
        patterns = []
        last_candle = data.iloc[-1]
        
        # Calculate body size as percentage of range
        body_size = abs(last_candle['close'] - last_candle['open'])
        candle_range = last_candle['high'] - last_candle['low']
        
        if candle_range == 0:
            return patterns
        
        body_percentage = body_size / candle_range
        
        # Doji: small body (< 5% of range)
        if body_percentage < 0.05:
            upper_shadow = last_candle['high'] - max(last_candle['open'], last_candle['close'])
            lower_shadow = min(last_candle['open'], last_candle['close']) - last_candle['low']
            
            # Classify doji type
            if upper_shadow > 2 * lower_shadow:
                pattern_name = "Dragonfly Doji"
                direction = "bullish"
                confidence = 0.72
            elif lower_shadow > 2 * upper_shadow:
                pattern_name = "Gravestone Doji"
                direction = "bearish"
                confidence = 0.72
            else:
                pattern_name = "Classic Doji"
                direction = "neutral"
                confidence = 0.65
            
            # Volume confirmation
            volume_conf = self._check_volume_confirmation(data, 'reversal')
            momentum_conf = self._check_momentum_confirmation(data)
            
            # Adjust confidence based on confirmations
            if volume_conf:
                confidence += 0.05
            if momentum_conf:
                confidence += 0.05
            
            patterns.append(PatternResult(
                pattern_name=pattern_name,
                category='candlestick',
                confidence=min(confidence, 0.95),
                ml_confidence=None,
                traditional_confidence=confidence,
                signal_strength=self._get_signal_strength(confidence),
                direction=direction,
                start_date=data.index[-1],
                end_date=data.index[-1],
                target_price=None,
                stop_loss=None,
                risk_reward_ratio=None,
                pattern_data={
                    'body_percentage': body_percentage,
                    'upper_shadow_ratio': upper_shadow / candle_range,
                    'lower_shadow_ratio': lower_shadow / candle_range
                },
                key_levels={
                    'resistance': last_candle['high'],
                    'support': last_candle['low']
                },
                volume_confirmation=volume_conf,
                momentum_confirmation=momentum_conf
            ))
        
        return patterns
    
    def _detect_engulfing_patterns(self, data: pd.DataFrame) -> List[PatternResult]:
        patterns = []
        
        if len(data) < 2:
            return patterns
        
        prev_candle = data.iloc[-2]
        curr_candle = data.iloc[-1]
        
        prev_body_size = abs(prev_candle['close'] - prev_candle['open'])
        curr_body_size = abs(curr_candle['close'] - curr_candle['open'])
        
        # Check for bullish engulfing
        if (prev_candle['close'] < prev_candle['open'] and  # Previous red
            curr_candle['close'] > curr_candle['open'] and  # Current green
            curr_candle['open'] < prev_candle['close'] and  # Opens below prev close
            curr_candle['close'] > prev_candle['open'] and  # Closes above prev open
            curr_body_size > prev_body_size * 1.1):  # Larger body
            
            confidence = 0.75
            volume_conf = self._check_volume_confirmation(data, 'reversal')
            momentum_conf = self._check_momentum_confirmation(data)
            
            if volume_conf:
                confidence += 0.05
            if momentum_conf:
                confidence += 0.05
            
            patterns.append(PatternResult(
                pattern_name="Bullish Engulfing",
                category='candlestick',
                confidence=min(confidence, 0.95),
                ml_confidence=None,
                traditional_confidence=confidence,
                signal_strength=self._get_signal_strength(confidence),
                direction='bullish',
                start_date=data.index[-2],
                end_date=data.index[-1],
                target_price=curr_candle['close'] + (curr_candle['close'] - prev_candle['open']),
                stop_loss=min(prev_candle['low'], curr_candle['low']),
                risk_reward_ratio=None,
                pattern_data={
                    'prev_body_size': prev_body_size,
                    'curr_body_size': curr_body_size,
                    'size_ratio': curr_body_size / prev_body_size if prev_body_size > 0 else 0
                },
                key_levels={
                    'resistance': max(prev_candle['high'], curr_candle['high']),
                    'support': min(prev_candle['low'], curr_candle['low'])
                },
                volume_confirmation=volume_conf,
                momentum_confirmation=momentum_conf
            ))
        
        # Check for bearish engulfing
        elif (prev_candle['close'] > prev_candle['open'] and  # Previous green
              curr_candle['close'] < curr_candle['open'] and  # Current red
              curr_candle['open'] > prev_candle['close'] and  # Opens above prev close
              curr_candle['close'] < prev_candle['open'] and  # Closes below prev open
              curr_body_size > prev_body_size * 1.1):  # Larger body
            
            confidence = 0.75
            volume_conf = self._check_volume_confirmation(data, 'reversal')
            momentum_conf = self._check_momentum_confirmation(data)
            
            if volume_conf:
                confidence += 0.05
            if momentum_conf:
                confidence += 0.05
            
            patterns.append(PatternResult(
                pattern_name="Bearish Engulfing",
                category='candlestick',
                confidence=min(confidence, 0.95),
                ml_confidence=None,
                traditional_confidence=confidence,
                signal_strength=self._get_signal_strength(confidence),
                direction='bearish',
                start_date=data.index[-2],
                end_date=data.index[-1],
                target_price=curr_candle['close'] - (prev_candle['open'] - curr_candle['close']),
                stop_loss=max(prev_candle['high'], curr_candle['high']),
                risk_reward_ratio=None,
                pattern_data={
                    'prev_body_size': prev_body_size,
                    'curr_body_size': curr_body_size,
                    'size_ratio': curr_body_size / prev_body_size if prev_body_size > 0 else 0
                },
                key_levels={
                    'resistance': max(prev_candle['high'], curr_candle['high']),
                    'support': min(prev_candle['low'], curr_candle['low'])
                },
                volume_confirmation=volume_conf,
                momentum_confirmation=momentum_conf
            ))
        
        return patterns
    
    def _detect_star_patterns(self, data: pd.DataFrame) -> List[PatternResult]:
        patterns = []
        
        if len(data) < 3:
            return patterns
        
        first = data.iloc[-3]
        star = data.iloc[-2]
        third = data.iloc[-1]
        
        # Check for morning star (bullish)
        if (first['close'] < first['open'] and  # First candle is red
            abs(star['close'] - star['open']) / (star['high'] - star['low']) < 0.3 and  # Star has small body
            star['high'] < min(first['low'], third['low']) and  # Star gaps down
            third['close'] > third['open'] and  # Third candle is green
            third['close'] > (first['open'] + first['close']) / 2):  # Third closes above midpoint of first
            
            confidence = 0.78
            volume_conf = self._check_volume_confirmation(data, 'reversal')
            
            patterns.append(PatternResult(
                pattern_name="Morning Star",
                category='candlestick',
                confidence=min(confidence + (0.05 if volume_conf else 0), 0.95),
                ml_confidence=None,
                traditional_confidence=confidence,
                signal_strength=self._get_signal_strength(confidence),
                direction='bullish',
                start_date=data.index[-3],
                end_date=data.index[-1],
                target_price=third['close'] + (third['close'] - first['close']),
                stop_loss=min(star['low'], third['low']),
                risk_reward_ratio=None,
                pattern_data={
                    'gap_size': min(first['low'], third['low']) - star['high'],
                    'star_body_ratio': abs(star['close'] - star['open']) / (star['high'] - star['low']) if star['high'] != star['low'] else 0
                },
                key_levels={
                    'resistance': max(first['high'], star['high'], third['high']),
                    'support': min(first['low'], star['low'], third['low'])
                },
                volume_confirmation=volume_conf,
                momentum_confirmation=self._check_momentum_confirmation(data)
            ))
        
        # Check for evening star (bearish)
        elif (first['close'] > first['open'] and  # First candle is green
              abs(star['close'] - star['open']) / (star['high'] - star['low']) < 0.3 and  # Star has small body
              star['low'] > max(first['high'], third['high']) and  # Star gaps up
              third['close'] < third['open'] and  # Third candle is red
              third['close'] < (first['open'] + first['close']) / 2):  # Third closes below midpoint of first
            
            confidence = 0.78
            volume_conf = self._check_volume_confirmation(data, 'reversal')
            
            patterns.append(PatternResult(
                pattern_name="Evening Star",
                category='candlestick',
                confidence=min(confidence + (0.05 if volume_conf else 0), 0.95),
                ml_confidence=None,
                traditional_confidence=confidence,
                signal_strength=self._get_signal_strength(confidence),
                direction='bearish',
                start_date=data.index[-3],
                end_date=data.index[-1],
                target_price=third['close'] - (first['close'] - third['close']),
                stop_loss=max(star['high'], third['high']),
                risk_reward_ratio=None,
                pattern_data={
                    'gap_size': star['low'] - max(first['high'], third['high']),
                    'star_body_ratio': abs(star['close'] - star['open']) / (star['high'] - star['low']) if star['high'] != star['low'] else 0
                },
                key_levels={
                    'resistance': max(first['high'], star['high'], third['high']),
                    'support': min(first['low'], star['low'], third['low'])
                },
                volume_confirmation=volume_conf,
                momentum_confirmation=self._check_momentum_confirmation(data)
            ))
        
        return patterns
    
    def _detect_hammer_patterns(self, data: pd.DataFrame) -> List[PatternResult]:
        patterns = []
        last_candle = data.iloc[-1]
        
        body_size = abs(last_candle['close'] - last_candle['open'])
        candle_range = last_candle['high'] - last_candle['low']
        
        if candle_range == 0:
            return patterns
        
        body_percentage = body_size / candle_range
        upper_shadow = last_candle['high'] - max(last_candle['open'], last_candle['close'])
        lower_shadow = min(last_candle['open'], last_candle['close']) - last_candle['low']
        
        # Hammer: small body in upper part, long lower shadow
        if (body_percentage < 0.3 and
            lower_shadow > 2 * body_size and
            upper_shadow < body_size):
            
            # Determine if it's a hammer (bullish) or hanging man (bearish) based on trend
            if len(data) >= 10:
                trend = self._determine_trend(data.tail(10))
                if trend == 'downtrend':
                    pattern_name = "Hammer"
                    direction = "bullish"
                    confidence = 0.72
                elif trend == 'uptrend':
                    pattern_name = "Hanging Man"
                    direction = "bearish"
                    confidence = 0.68
                else:
                    pattern_name = "Hammer/Hanging Man"
                    direction = "neutral"
                    confidence = 0.60
            else:
                pattern_name = "Hammer"
                direction = "bullish"
                confidence = 0.65
            
            volume_conf = self._check_volume_confirmation(data, 'reversal')
            if volume_conf:
                confidence += 0.05
            
            patterns.append(PatternResult(
                pattern_name=pattern_name,
                category='candlestick',
                confidence=min(confidence, 0.95),
                ml_confidence=None,
                traditional_confidence=confidence,
                signal_strength=self._get_signal_strength(confidence),
                direction=direction,
                start_date=data.index[-1],
                end_date=data.index[-1],
                target_price=None,
                stop_loss=None,
                risk_reward_ratio=None,
                pattern_data={
                    'body_percentage': body_percentage,
                    'lower_shadow_ratio': lower_shadow / candle_range,
                    'upper_shadow_ratio': upper_shadow / candle_range
                },
                key_levels={
                    'resistance': last_candle['high'],
                    'support': last_candle['low']
                },
                volume_confirmation=volume_conf,
                momentum_confirmation=self._check_momentum_confirmation(data)
            ))
        
        # Shooting star: small body in lower part, long upper shadow
        elif (body_percentage < 0.3 and
              upper_shadow > 2 * body_size and
              lower_shadow < body_size):
            
            confidence = 0.70
            volume_conf = self._check_volume_confirmation(data, 'reversal')
            if volume_conf:
                confidence += 0.05
            
            patterns.append(PatternResult(
                pattern_name="Shooting Star",
                category='candlestick',
                confidence=min(confidence, 0.95),
                ml_confidence=None,
                traditional_confidence=confidence,
                signal_strength=self._get_signal_strength(confidence),
                direction='bearish',
                start_date=data.index[-1],
                end_date=data.index[-1],
                target_price=None,
                stop_loss=None,
                risk_reward_ratio=None,
                pattern_data={
                    'body_percentage': body_percentage,
                    'upper_shadow_ratio': upper_shadow / candle_range,
                    'lower_shadow_ratio': lower_shadow / candle_range
                },
                key_levels={
                    'resistance': last_candle['high'],
                    'support': last_candle['low']
                },
                volume_confirmation=volume_conf,
                momentum_confirmation=self._check_momentum_confirmation(data)
            ))
        
        return patterns
    
    def _check_volume_confirmation(self, data: pd.DataFrame, pattern_type: str) -> bool:
        """Check if volume confirms the pattern"""
        if 'volume' not in data.columns or len(data) < 20:
            return False
        
        recent_volume = data['volume'].iloc[-1]
        avg_volume = data['volume'].tail(20).mean()
        
        # For reversal patterns, we want higher than average volume
        if pattern_type == 'reversal':
            return recent_volume > avg_volume * 1.2
        
        return False
    
    def _check_momentum_confirmation(self, data: pd.DataFrame) -> bool:
        """Check if momentum indicators confirm the pattern"""
        if len(data) < 10:
            return False
        
        # Simple momentum check - compare recent close to average
        recent_close = data['close'].iloc[-1]
        avg_close = data['close'].tail(10).mean()
        
        return abs(recent_close - avg_close) / avg_close > 0.01
    
    def _determine_trend(self, data: pd.DataFrame) -> str:
        """Determine the current trend"""
        if len(data) < 5:
            return 'neutral'
        
        first_close = data['close'].iloc[0]
        last_close = data['close'].iloc[-1]
        
        if last_close > first_close * 1.02:
            return 'uptrend'
        elif last_close < first_close * 0.98:
            return 'downtrend'
        else:
            return 'neutral'
    
    def _get_signal_strength(self, confidence: float) -> str:
        """Convert confidence to signal strength"""
        if confidence >= 0.85:
            return 'very_strong'
        elif confidence >= 0.75:
            return 'strong'
        elif confidence >= 0.65:
            return 'moderate'
        else:
            return 'weak'
    
    def get_pattern_info(self) -> Dict[str, Any]:
        return {
            'name': 'Candlestick Pattern Detector',
            'type': 'candlestick',
            'patterns': ['doji', 'hammer', 'engulfing', 'star', 'shooting_star'],
            'requires_volume': False,
            'min_bars': 1
        }

class EnhancedPatternRecognitionService:
    """Main service orchestrating multiple pattern detection methods"""
    
    def __init__(self, db_config: Dict[str, Any] = None):
        self.db_config = db_config
        self.connection_pool = None
        self.detectors = {
            'candlestick': CandlestickPatternDetector(),
            'ml': MLPatternDetector() if HAS_ML else None
        }
        
        # Remove None detectors
        self.detectors = {k: v for k, v in self.detectors.items() if v is not None}
        
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database connection"""
        if self.db_config:
            try:
                self.connection_pool = ThreadedConnectionPool(
                    1, 10,
                    host=self.db_config['host'],
                    port=self.db_config['port'],
                    database=self.db_config['database'],
                    user=self.db_config['user'],
                    password=self.db_config['password']
                )
                logger.info("Database connection pool initialized")
            except Exception as e:
                logger.error(f"Failed to initialize database: {e}")
    
    async def scan_symbol(self, symbol: str, timeframe: str = '1d', limit: int = 200) -> List[PatternResult]:
        """Scan a symbol for patterns across all detectors"""
        
        # Get price data
        data = await self._get_price_data(symbol, timeframe, limit)
        if data is None or len(data) < 10:
            logger.warning(f"Insufficient data for {symbol}")
            return []
        
        all_patterns = []
        
        # Run all detectors concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.detectors)) as executor:
            future_to_detector = {
                executor.submit(detector.detect, data): name 
                for name, detector in self.detectors.items()
            }
            
            for future in concurrent.futures.as_completed(future_to_detector):
                detector_name = future_to_detector[future]
                try:
                    patterns = future.result()
                    all_patterns.extend(patterns)
                    logger.info(f"{detector_name} detector found {len(patterns)} patterns for {symbol}")
                except Exception as e:
                    logger.error(f"Error in {detector_name} detector for {symbol}: {e}")
        
        # Filter and rank patterns
        filtered_patterns = self._filter_and_rank_patterns(all_patterns)
        
        # Store patterns in database
        if filtered_patterns and self.connection_pool:
            await self._store_patterns(symbol, timeframe, filtered_patterns)
        
        return filtered_patterns
    
    async def _get_price_data(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Get price data from database"""
        if not self.connection_pool:
            logger.error("No database connection available")
            return None
        
        conn = None
        try:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Determine table based on timeframe
            if timeframe == '1d':
                table = 'technical_data_daily'
            elif timeframe == '1w':
                table = 'technical_data_weekly'
            elif timeframe == '1m':
                table = 'technical_data_monthly'
            else:
                table = 'technical_data_daily'
            
            cursor.execute(f"""
                SELECT date_time, open_price as open, high_price as high, 
                       low_price as low, close_price as close, volume
                FROM {table}
                WHERE symbol = %s
                ORDER BY date_time DESC
                LIMIT %s
            """, (symbol, limit))
            
            rows = cursor.fetchall()
            
            if not rows:
                logger.warning(f"No data found for {symbol} in {table}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame([dict(row) for row in rows])
            df['date_time'] = pd.to_datetime(df['date_time'])
            df.set_index('date_time', inplace=True)
            df.sort_index(inplace=True)
            
            # Ensure numeric columns
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching price data for {symbol}: {e}")
            return None
        finally:
            if conn:
                self.connection_pool.putconn(conn)
    
    def _filter_and_rank_patterns(self, patterns: List[PatternResult]) -> List[PatternResult]:
        """Filter and rank patterns by confidence and other criteria"""
        
        # Filter by minimum confidence
        filtered = [p for p in patterns if p.confidence >= 0.60]
        
        # Remove duplicates (same pattern type detected multiple times)
        seen_patterns = {}
        unique_patterns = []
        
        for pattern in filtered:
            key = f"{pattern.pattern_name}_{pattern.direction}_{pattern.start_date}"
            if key not in seen_patterns or pattern.confidence > seen_patterns[key].confidence:
                seen_patterns[key] = pattern
        
        unique_patterns = list(seen_patterns.values())
        
        # Sort by confidence descending
        unique_patterns.sort(key=lambda x: x.confidence, reverse=True)
        
        return unique_patterns[:10]  # Return top 10 patterns
    
    async def _store_patterns(self, symbol: str, timeframe: str, patterns: List[PatternResult]):
        """Store detected patterns in database"""
        if not self.connection_pool:
            return
        
        conn = None
        try:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            
            for pattern in patterns:
                # Get pattern type ID
                cursor.execute("SELECT id FROM pattern_types WHERE name = %s", (pattern.pattern_name,))
                result = cursor.fetchone()
                
                if not result:
                    logger.warning(f"Pattern type '{pattern.pattern_name}' not found in database")
                    continue
                
                pattern_type_id = result[0]
                
                # Insert detected pattern
                cursor.execute("""
                    INSERT INTO detected_patterns (
                        symbol, pattern_type_id, timeframe, detection_date, start_date, end_date,
                        confidence_score, ml_confidence, traditional_confidence, signal_strength,
                        direction, target_price, stop_loss, risk_reward_ratio, pattern_data,
                        key_levels, volume_confirmation, momentum_confirmation
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    symbol, pattern_type_id, timeframe, datetime.now(), pattern.start_date,
                    pattern.end_date, pattern.confidence, pattern.ml_confidence,
                    pattern.traditional_confidence, pattern.signal_strength, pattern.direction,
                    pattern.target_price, pattern.stop_loss, pattern.risk_reward_ratio,
                    json.dumps(pattern.pattern_data), json.dumps(pattern.key_levels),
                    pattern.volume_confirmation, pattern.momentum_confirmation
                ))
            
            conn.commit()
            logger.info(f"Stored {len(patterns)} patterns for {symbol}")
            
        except Exception as e:
            logger.error(f"Error storing patterns: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                self.connection_pool.putconn(conn)
    
    async def get_patterns_for_symbol(self, symbol: str, timeframe: str = '1d', 
                                    limit: int = 50) -> List[Dict[str, Any]]:
        """Get stored patterns for a symbol"""
        if not self.connection_pool:
            return []
        
        conn = None
        try:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            cursor.execute("""
                SELECT dp.*, pt.name as pattern_name, pt.category, pt.description
                FROM detected_patterns dp
                JOIN pattern_types pt ON dp.pattern_type_id = pt.id
                WHERE dp.symbol = %s AND dp.timeframe = %s
                ORDER BY dp.detection_date DESC, dp.confidence_score DESC
                LIMIT %s
            """, (symbol, timeframe, limit))
            
            return [dict(row) for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error fetching patterns for {symbol}: {e}")
            return []
        finally:
            if conn:
                self.connection_pool.putconn(conn)
    
    async def bulk_scan(self, symbols: List[str], timeframe: str = '1d') -> Dict[str, List[PatternResult]]:
        """Scan multiple symbols concurrently"""
        results = {}
        
        async def scan_single(symbol):
            try:
                patterns = await self.scan_symbol(symbol, timeframe)
                return symbol, patterns
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                return symbol, []
        
        # Create tasks for all symbols
        tasks = [scan_single(symbol) for symbol in symbols]
        
        # Execute with limited concurrency
        for i in range(0, len(tasks), 10):  # Process 10 at a time
            batch = tasks[i:i+10]
            batch_results = await asyncio.gather(*batch)
            
            for symbol, patterns in batch_results:
                results[symbol] = patterns
        
        return results
    
    def close(self):
        """Clean up resources"""
        if self.connection_pool:
            self.connection_pool.closeall()

# Example usage and testing
async def main():
    """Example usage of the enhanced pattern recognition service"""
    
    # Database configuration (replace with your actual config)
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'stocks',
        'user': 'your_user',
        'password': 'your_password'
    }
    
    # Initialize service
    service = EnhancedPatternRecognitionService(db_config)
    
    try:
        # Scan single symbol
        patterns = await service.scan_symbol('AAPL', '1d')
        print(f"Found {len(patterns)} patterns for AAPL")
        
        for pattern in patterns:
            print(f"  {pattern.pattern_name}: {pattern.confidence:.3f} confidence, {pattern.direction}")
        
        # Bulk scan multiple symbols
        symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN']
        bulk_results = await service.bulk_scan(symbols)
        
        for symbol, symbol_patterns in bulk_results.items():
            print(f"{symbol}: {len(symbol_patterns)} patterns detected")
        
    finally:
        service.close()

if __name__ == "__main__":
    asyncio.run(main())