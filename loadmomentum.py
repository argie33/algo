#!/usr/bin/env python3
"""
Advanced Momentum Metrics Loader Script

This script implements comprehensive momentum analysis including:
- Jegadeesh-Titman 12-1 month momentum calculation (academic standard)
- Fundamental momentum (earnings revisions, estimate changes)
- Volume analysis and order flow momentum
- Cross-sectional momentum ranking
- Momentum persistence and mean reversion analysis

Academic References:
- Jegadeesh and Titman (1993) - Returns to Buying Winners and Selling Losers
- Asness, Moskowitz, and Pedersen (2013) - Value and Momentum Everywhere
- Novy-Marx (2012) - Is momentum really momentum?

Author: Financial Dashboard System
"""

import sys
import time
import logging
import json
import os
import gc
import resource
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

# Script configuration
SCRIPT_NAME = "loadmomentum.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def log_mem(stage: str):
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mb = usage / 1024 if sys.platform.startswith("linux") else usage / (1024 * 1024)
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

def get_db_config():
    """Get database configuration"""
    try:
        import boto3
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception:
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

def safe_float(value, default=None):
    """Convert to float safely"""
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def sanitize_result(result: Dict) -> Dict:
    """Recursively convert all numpy/pandas types to native Python types for database insertion"""
    if not isinstance(result, dict):
        return result

    sanitized = {}
    for key, value in result.items():
        try:
            if value is None:
                sanitized[key] = None
            elif isinstance(value, bool):
                # Check bool before numbers since bool is a subclass of int
                sanitized[key] = bool(value)
            elif isinstance(value, np.bool_):
                sanitized[key] = bool(value)
            elif isinstance(value, (np.integer, int)):
                sanitized[key] = int(value)
            elif isinstance(value, (np.floating, float)):
                sanitized[key] = float(value)
            elif isinstance(value, (np.ndarray, list)):
                sanitized[key] = None  # Skip array values
            elif isinstance(value, (datetime, date)):
                sanitized[key] = value if isinstance(value, date) else value.date()
            elif isinstance(value, pd.Timestamp):
                sanitized[key] = value.date()
            elif isinstance(value, str):
                sanitized[key] = str(value)
            elif hasattr(value, 'item'):
                # numpy scalar with .item() method
                try:
                    sanitized[key] = float(value.item())
                except (ValueError, TypeError):
                    try:
                        sanitized[key] = int(value.item())
                    except (ValueError, TypeError):
                        sanitized[key] = None
            else:
                # Last resort: try converting to native Python type
                try:
                    if hasattr(value, '__float__'):
                        sanitized[key] = float(value)
                    elif hasattr(value, '__int__'):
                        sanitized[key] = int(value)
                    else:
                        logging.warning(f"Unknown type for key '{key}': {type(value)} = {value}")
                        sanitized[key] = None
                except Exception as e:
                    logging.warning(f"Failed to convert key '{key}' (type {type(value)}): {e}")
                    sanitized[key] = None
        except Exception as e:
            logging.warning(f"Error sanitizing key '{key}': {e}")
            sanitized[key] = None

    return sanitized

class MomentumCalculator:
    """Calculate comprehensive momentum metrics using academic methodologies"""

    def __init__(self, symbol: str, conn):
        self.symbol = symbol
        self.conn = conn
        try:
            self.ticker = yf.Ticker(symbol)
        except Exception as e:
            logging.warning(f"Failed to initialize Ticker for {symbol}: {e}")
            self.ticker = None

    def get_price_momentum_data(self, conn) -> Optional[Dict]:
        """Get comprehensive price momentum analysis from database"""
        try:
            # Get historical price data from price_daily table (need 2+ years for proper momentum calculation)
            try:
                logging.debug(f"Creating cursor for {self.symbol}")
                cur = conn.cursor(cursor_factory=RealDictCursor)
            except Exception as e:
                logging.error(f"Cursor creation failed for {self.symbol}: {e}")
                return None

            try:
                logging.debug(f"Executing SELECT for {self.symbol}, symbol type={type(self.symbol)}")
                cur.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM price_daily
                    WHERE symbol = %s
                    ORDER BY date ASC
                """, (self.symbol,))
            except Exception as e:
                logging.error(f"Execute query failed for {self.symbol}: {type(e).__name__}: {e}")
                cur.close()
                return None

            rows = cur.fetchall()
            cur.close()

            if not rows or len(rows) < 252:  # Need at least 1 year of data
                logging.warning(f"Insufficient price data for {self.symbol}: {len(rows) if rows else 0} records")
                return None

            # Convert to DataFrame with proper column names from RealDictCursor results
            # RealDictCursor returns dictionaries, so we can construct DataFrame directly
            hist = pd.DataFrame(list(rows))

            # Ensure column names are lowercase to match database column names
            hist.columns = [col.lower() for col in hist.columns]

            # Convert date to datetime
            hist['date'] = pd.to_datetime(hist['date'])

            # Set index to date
            hist = hist.set_index('date')

            # Convert numeric columns to float
            for col in ['close', 'volume', 'open', 'high', 'low']:
                if col in hist.columns:
                    hist[col] = pd.to_numeric(hist[col], errors='coerce')

            # Calculate returns
            hist['returns'] = hist['close'].pct_change()
            hist['log_returns'] = np.log(hist['close'] / hist['close'].shift(1))

            # Get latest date and price
            latest_date = hist.index[-1]
            current_price = hist['close'].iloc[-1]

            # Ensure date is properly converted to Python date
            try:
                if hasattr(latest_date, 'date'):
                    date_val = latest_date.date()
                elif hasattr(latest_date, 'to_pydatetime'):
                    date_val = latest_date.to_pydatetime().date()
                else:
                    date_val = date.today()
            except Exception as date_err:
                logging.warning(f"Date conversion error for {self.symbol}: {date_err}, using today")
                date_val = date.today()

            result = {
                'symbol': str(self.symbol),
                'date': date_val,
                'current_price': float(current_price) if pd.notna(current_price) else 0.0
            }

            # Calculate Jegadeesh-Titman momentum (12-1 month)
            try:
                jt_momentum = self.calculate_jegadeesh_titman_momentum(hist)
                if jt_momentum:
                    result.update(jt_momentum)
            except Exception as e:
                logging.warning(f"JT momentum calc failed for {self.symbol}: {e}")

            # Calculate additional momentum metrics
            try:
                momentum_metrics = self.calculate_momentum_metrics(hist)
                if momentum_metrics:
                    result.update(momentum_metrics)
            except Exception as e:
                logging.warning(f"Momentum metrics calc failed for {self.symbol}: {e}")

            # Calculate volume momentum
            try:
                volume_momentum = self.calculate_volume_momentum(hist)
                if volume_momentum:
                    result.update(volume_momentum)
            except Exception as e:
                logging.warning(f"Volume momentum calc failed for {self.symbol}: {e}")

            # Calculate momentum quality metrics
            try:
                quality_metrics = self.calculate_momentum_quality(hist)
                if quality_metrics:
                    result.update(quality_metrics)
            except Exception as e:
                logging.warning(f"Quality metrics calc failed for {self.symbol}: {e}")

            # Sanitize result to ensure all values are native Python types BEFORE returning
            sanitized = sanitize_result(result)

            # Final validation - ensure all values can be serialized
            for key, val in sanitized.items():
                if val is not None and not isinstance(val, (str, int, float, bool, date, datetime)):
                    logging.warning(f"After sanitization, {key} is still type {type(val)}")
                    sanitized[key] = None

            return sanitized

        except Exception as e:
            logging.error(f"Error calculating price momentum for {self.symbol}: {type(e).__name__}: {e}")
            import traceback
            logging.debug(traceback.format_exc())
            return None
    
    def calculate_jegadeesh_titman_momentum(self, hist: pd.DataFrame) -> Dict:
        """
        Calculate Jegadeesh-Titman 12-1 month momentum
        
        Academic methodology:
        - 12-month cumulative return excluding most recent month
        - Skip most recent month to avoid short-term reversal effects
        - This is the standard academic momentum calculation
        """
        result = {}
        
        try:
            if len(hist) < 252:  # Need at least 1 year
                return result
            
            current_price = hist['close'].iloc[-1]
            
            # Standard Jegadeesh-Titman: 12-1 month momentum
            # t-252 to t-21 (11 months, skipping most recent month)
            if len(hist) >= 252:
                price_12m_ago = hist['close'].iloc[-252]  # 12 months ago
                price_1m_ago = hist['close'].iloc[-21]    # 1 month ago
                
                jt_momentum = (price_1m_ago - price_12m_ago) / price_12m_ago
                result['jt_momentum_12_1'] = safe_float(jt_momentum)
                
                # Calculate statistical significance
                returns_11m = hist['returns'].iloc[-252:-21]  # 11 months of returns
                if len(returns_11m) > 20:
                    momentum_vol = returns_11m.std() * math.sqrt(252)
                    momentum_sharpe = jt_momentum / momentum_vol if momentum_vol > 0 else 0
                    result['jt_momentum_sharpe'] = safe_float(momentum_sharpe)
                    result['jt_momentum_volatility'] = safe_float(momentum_vol)
            
            # Alternative momentum horizons for robustness
            horizons = {
                '6_1': (126, 21),   # 6-1 month
                '9_1': (189, 21),   # 9-1 month  
                '3_1': (63, 21),    # 3-1 month
                '12_3': (252, 63)   # 12-3 month
            }
            
            for name, (long_period, skip_period) in horizons.items():
                if len(hist) >= long_period:
                    price_long_ago = hist['close'].iloc[-long_period]
                    price_skip_ago = hist['close'].iloc[-skip_period]
                    
                    momentum = (price_skip_ago - price_long_ago) / price_long_ago
                    result[f'momentum_{name}'] = safe_float(momentum)
            
            # Risk-adjusted momentum (Sharpe ratio based)
            if len(hist) >= 252:
                returns_12m = hist['returns'].iloc[-252:]
                if len(returns_12m) > 20:
                    mean_return = returns_12m.mean() * 252  # Annualized
                    vol_return = returns_12m.std() * math.sqrt(252)  # Annualized
                    
                    risk_adj_momentum = mean_return / vol_return if vol_return > 0 else 0
                    result['risk_adjusted_momentum'] = safe_float(risk_adj_momentum)
                    
                    # Downside deviation (semi-volatility)
                    negative_returns = returns_12m[returns_12m < 0]
                    if len(negative_returns) > 5:
                        downside_vol = negative_returns.std() * math.sqrt(252)
                        sortino_momentum = mean_return / downside_vol if downside_vol > 0 else 0
                        result['sortino_momentum'] = safe_float(sortino_momentum)
            
        except Exception as e:
            logging.error(f"Error in Jegadeesh-Titman calculation for {self.symbol}: {e}")
        
        return result
    
    def calculate_momentum_metrics(self, hist: pd.DataFrame) -> Dict:
        """Calculate additional momentum metrics"""
        result = {}
        
        try:
            # Short-term momentum (1 week, 1 month)
            if len(hist) >= 21:
                current_price = hist['close'].iloc[-1]
                price_1w = hist['close'].iloc[-5] if len(hist) >= 5 else current_price
                price_1m = hist['close'].iloc[-21]
                
                result['momentum_1w'] = safe_float((current_price - price_1w) / price_1w)
                result['momentum_1m'] = safe_float((current_price - price_1m) / price_1m)
            
            # Medium-term momentum
            if len(hist) >= 63:
                price_3m = hist['close'].iloc[-63]
                result['momentum_3m'] = safe_float((current_price - price_3m) / price_3m)
            
            if len(hist) >= 126:
                price_6m = hist['close'].iloc[-126]
                result['momentum_6m'] = safe_float((current_price - price_6m) / price_6m)
            
            # Momentum persistence (consistency)
            if len(hist) >= 63:
                # Calculate rolling 1-month returns
                monthly_returns = []
                for i in range(21, len(hist), 21):  # Every ~month
                    if i < len(hist):
                        ret = (hist['close'].iloc[i] - hist['close'].iloc[i-21]) / hist['close'].iloc[i-21]
                        monthly_returns.append(ret)
                
                if len(monthly_returns) >= 3:
                    monthly_returns = np.array(monthly_returns)
                    
                    # Momentum persistence (% of positive months)
                    positive_months = np.sum(monthly_returns > 0) / len(monthly_returns)
                    result['momentum_persistence'] = safe_float(positive_months)
                    
                    # Momentum consistency (negative of coefficient of variation)
                    if monthly_returns.std() > 0:
                        momentum_consistency = -abs(monthly_returns.std() / monthly_returns.mean())
                        result['momentum_consistency'] = safe_float(momentum_consistency)
            
            # Maximum drawdown during momentum period
            if len(hist) >= 252:
                prices_12m = hist['close'].iloc[-252:]
                rolling_max = prices_12m.expanding().max()
                drawdowns = (prices_12m - rolling_max) / rolling_max
                max_drawdown = drawdowns.min()
                result['momentum_max_drawdown'] = safe_float(max_drawdown)
                
                # Recovery factor (momentum return / max drawdown)
                if 'jt_momentum_12_1' in result and max_drawdown < 0:
                    recovery_factor = result['jt_momentum_12_1'] / abs(max_drawdown)
                    result['momentum_recovery_factor'] = safe_float(recovery_factor)
            
        except Exception as e:
            logging.error(f"Error calculating momentum metrics for {self.symbol}: {e}")
        
        return result
    
    def calculate_volume_momentum(self, hist: pd.DataFrame) -> Dict:
        """Calculate volume-based momentum indicators"""
        result = {}
        
        try:
            if 'volume' not in hist.columns:
                return result

            volume = hist['volume']
            returns = hist['returns']
            
            # Volume-weighted momentum
            if len(hist) >= 63:
                recent_period = 63  # 3 months
                recent_returns = returns.iloc[-recent_period:]
                recent_volume = volume.iloc[-recent_period:]
                
                # Volume-weighted average return
                total_volume = recent_volume.sum()
                if total_volume > 0:
                    vwap_return = (recent_returns * recent_volume).sum() / total_volume
                    result['volume_weighted_momentum'] = safe_float(vwap_return)
            
            # On-Balance Volume momentum
            if len(hist) >= 126:
                # Calculate OBV
                obv = volume.copy()
                for i in range(1, len(hist)):
                    if hist['close'].iloc[i] > hist['close'].iloc[i-1]:
                        obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
                    elif hist['close'].iloc[i] < hist['close'].iloc[i-1]:
                        obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
                    else:
                        obv.iloc[i] = obv.iloc[i-1]
                
                # OBV momentum (6-month change)
                obv_6m_ago = obv.iloc[-126]
                obv_current = obv.iloc[-1]
                if obv_6m_ago != 0:
                    obv_momentum = (obv_current - obv_6m_ago) / abs(obv_6m_ago)
                    result['obv_momentum'] = safe_float(obv_momentum)
            
            # Volume trend analysis
            if len(hist) >= 63:
                recent_volume = volume.iloc[-63:]  # 3 months
                older_volume = volume.iloc[-126:-63] if len(hist) >= 126 else recent_volume
                
                recent_avg_vol = recent_volume.mean()
                older_avg_vol = older_volume.mean()
                
                if older_avg_vol > 0:
                    volume_trend = (recent_avg_vol - older_avg_vol) / older_avg_vol
                    result['volume_trend'] = safe_float(volume_trend)
                
                # Volume-price correlation
                if len(recent_returns) > 20:
                    recent_returns_clean = recent_returns.iloc[-63:].dropna()
                    recent_volume_clean = recent_volume.iloc[-len(recent_returns_clean):]
                    
                    if len(recent_returns_clean) > 20 and len(recent_volume_clean) == len(recent_returns_clean):
                        vol_price_corr = np.corrcoef(recent_returns_clean, recent_volume_clean)[0, 1]
                        if not np.isnan(vol_price_corr):
                            result['volume_price_correlation'] = safe_float(vol_price_corr)
            
        except Exception as e:
            logging.error(f"Error calculating volume momentum for {self.symbol}: {e}")
        
        return result
    
    def calculate_momentum_quality(self, hist: pd.DataFrame) -> Dict:
        """Calculate momentum quality and sustainability metrics"""
        result = {}

        try:
            returns = hist['returns'].dropna()
            
            if len(returns) < 60:
                return result
            
            # Momentum quality based on return distribution
            if len(returns) >= 252:
                # Skewness (positive skewness indicates momentum quality)
                returns_12m = returns.iloc[-252:]
                skewness = returns_12m.skew()
                result['momentum_skewness'] = safe_float(skewness)
                
                # Kurtosis (excess kurtosis)
                kurtosis = returns_12m.kurtosis()
                result['momentum_kurtosis'] = safe_float(kurtosis)
                
                # Momentum strength (% of days with positive returns)
                positive_days = np.sum(returns_12m > 0) / len(returns_12m)
                result['momentum_strength'] = safe_float(positive_days)
                
                # Momentum smoothness (1 / volatility of rolling monthly returns)
                if len(returns_12m) >= 63:
                    rolling_monthly = []
                    for i in range(21, len(returns_12m), 21):
                        if i < len(returns_12m):
                            monthly_ret = returns_12m.iloc[i-21:i].sum()
                            rolling_monthly.append(monthly_ret)
                    
                    if len(rolling_monthly) >= 3:
                        monthly_vol = np.std(rolling_monthly)
                        momentum_smoothness = 1 / (1 + monthly_vol) if monthly_vol >= 0 else 0
                        result['momentum_smoothness'] = safe_float(momentum_smoothness)
            
            # Momentum acceleration (second derivative)
            if len(hist) >= 126:
                prices = hist['close']
                
                # Calculate momentum over different periods
                mom_1m = (prices.iloc[-21] - prices.iloc[-42]) / prices.iloc[-42] if len(hist) >= 42 else 0
                mom_2m = (prices.iloc[-42] - prices.iloc[-63]) / prices.iloc[-63] if len(hist) >= 63 else 0
                mom_3m = (prices.iloc[-63] - prices.iloc[-84]) / prices.iloc[-84] if len(hist) >= 84 else 0
                
                # Momentum acceleration (momentum is accelerating if recent > older)
                if mom_2m != 0:
                    momentum_acceleration = (mom_1m - mom_2m) / abs(mom_2m)
                    result['momentum_acceleration'] = safe_float(momentum_acceleration)
            
        except Exception as e:
            logging.error(f"Error calculating momentum quality for {self.symbol}: {e}")
        
        return result
    
    def get_fundamental_momentum(self) -> Optional[Dict]:
        """Get fundamental momentum based on earnings revisions and estimates"""
        result = {
            'symbol': self.symbol,
            'date': str(date.today())
        }
        
        try:
            # Get analyst estimates and recommendations
            info = self.ticker.info
            
            # Earnings estimate revisions (proxy using forward estimates)
            if info:
                current_eps = safe_float(info.get('trailingEps'))
                forward_eps = safe_float(info.get('forwardEps'))
                
                if current_eps and forward_eps and current_eps != 0:
                    eps_growth_expected = (forward_eps - current_eps) / abs(current_eps)
                    result['expected_eps_growth'] = eps_growth_expected
                
                # Revenue estimate momentum
                current_revenue = safe_float(info.get('totalRevenue'))
                # Note: yfinance doesn't provide forward revenue estimates directly
                # In production, this would come from dedicated earnings estimate APIs
                
                # Recommendation trend (simplified)
                recommendation_mean = safe_float(info.get('recommendationMean'))
                if recommendation_mean:
                    # Convert 1-5 scale to momentum score (1=Strong Buy, 5=Strong Sell)
                    recommendation_momentum = (6 - recommendation_mean) / 5  # Invert and normalize
                    result['recommendation_momentum'] = recommendation_momentum
                
                # Price target momentum
                target_high = safe_float(info.get('targetHighPrice'))
                target_low = safe_float(info.get('targetLowPrice'))
                target_mean = safe_float(info.get('targetMeanPrice'))
                current_price = safe_float(info.get('currentPrice'))
                
                if target_mean and current_price and current_price > 0:
                    price_target_upside = (target_mean - current_price) / current_price
                    result['price_target_momentum'] = price_target_upside
                
                if target_high and target_low and target_high > target_low:
                    target_range = (target_high - target_low) / target_low
                    result['price_target_dispersion'] = target_range
            
            # Get earnings history for fundamental momentum calculation
            earnings = self.ticker.quarterly_earnings
            if earnings is not None and not earnings.empty and len(earnings) >= 4:
                # Calculate earnings surprise momentum
                recent_earnings = earnings.head(4)  # Last 4 quarters
                
                # Look for earnings acceleration
                if len(recent_earnings) >= 4:
                    earnings_values = recent_earnings['Actual'].values
                    if not any(pd.isna(earnings_values)):
                        # Simple trend calculation
                        q1, q2, q3, q4 = earnings_values
                        
                        # Quarter-over-quarter growth rates
                        qoq_growth = []
                        for i in range(1, len(earnings_values)):
                            if earnings_values[i-1] != 0:
                                growth = (earnings_values[i] - earnings_values[i-1]) / abs(earnings_values[i-1])
                                qoq_growth.append(growth)
                        
                        if qoq_growth:
                            avg_qoq_growth = np.mean(qoq_growth)
                            result['earnings_momentum_qoq'] = safe_float(avg_qoq_growth)
                            
                            # Earnings acceleration (improving growth rate)
                            if len(qoq_growth) >= 2:
                                recent_growth = np.mean(qoq_growth[-2:])  # Last 2 quarters
                                older_growth = np.mean(qoq_growth[:-2])    # Earlier quarters
                                
                                earnings_acceleration = recent_growth - older_growth
                                result['earnings_acceleration'] = safe_float(earnings_acceleration)
        
        except Exception as e:
            logging.error(f"Error calculating fundamental momentum for {self.symbol}: {e}")
        
        return result

def process_symbol_momentum(symbol: str, conn=None) -> Optional[Dict]:
    """Process comprehensive momentum analysis for a symbol"""
    try:
        # Create fresh connection for each symbol to avoid thread-safety issues
        if conn is None:
            import os
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5432)),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "password"),
                database=os.getenv("DB_NAME", "stocks")
            )
            should_close = True
        else:
            should_close = False

        calculator = MomentumCalculator(symbol, conn)

        # Get price momentum data from database
        price_momentum = calculator.get_price_momentum_data(conn)
        if not price_momentum:
            return None

        # Get fundamental momentum data
        fundamental_momentum = calculator.get_fundamental_momentum()

        # Combine results
        result = {**price_momentum}
        if fundamental_momentum:
            # Add fundamental momentum metrics (exclude duplicate symbol/date)
            for key, value in fundamental_momentum.items():
                if key not in ['symbol', 'date']:
                    result[key] = value

        # Sanitize entire result to ensure all types are native Python types
        result = sanitize_result(result)

        # Close connection if we created it
        if should_close:
            try:
                conn.close()
            except:
                pass

        return result

    except Exception as e:
        logging.error(f"Error processing momentum for {symbol}: {e}")
        # Close connection if we created it
        if 'should_close' in locals() and should_close:
            try:
                conn.close()
            except:
                pass
        return None

def create_momentum_metrics_table(cur, conn):
    """Create momentum metrics table - drop and recreate to ensure fresh schema"""
    logging.info("Dropping existing momentum_metrics table (if any)...")
    try:
        cur.execute("DROP TABLE IF EXISTS momentum_metrics CASCADE;")
        conn.commit()
        logging.info("✅ Dropped existing momentum_metrics table")
    except Exception as e:
        logging.warning(f"Could not drop existing table: {e}")
        conn.rollback()

    logging.info("Creating momentum_metrics table...")

    create_sql = """
    CREATE TABLE momentum_metrics (
        symbol VARCHAR(20),
        date DATE,
        current_price DECIMAL(12,4),

        -- Jegadeesh-Titman Momentum (Academic Standard)
        jt_momentum_12_1 DECIMAL(10,4),
        jt_momentum_sharpe DECIMAL(10,4),
        jt_momentum_volatility DECIMAL(10,4),

        -- Alternative Momentum Horizons
        momentum_6_1 DECIMAL(10,4),
        momentum_9_1 DECIMAL(10,4),
        momentum_3_1 DECIMAL(10,4),
        momentum_12_3 DECIMAL(10,4),

        -- Risk-Adjusted Momentum
        risk_adjusted_momentum DECIMAL(10,4),
        sortino_momentum DECIMAL(10,4),

        -- Short to Medium Term Momentum
        momentum_1w DECIMAL(10,4),
        momentum_1m DECIMAL(10,4),
        momentum_3m DECIMAL(10,4),
        momentum_6m DECIMAL(10,4),

        -- Momentum Quality Metrics
        momentum_persistence DECIMAL(10,4),
        momentum_consistency DECIMAL(10,4),
        momentum_max_drawdown DECIMAL(10,4),
        momentum_recovery_factor DECIMAL(10,4),
        momentum_skewness DECIMAL(10,4),
        momentum_kurtosis DECIMAL(10,4),
        momentum_strength DECIMAL(10,4),
        momentum_smoothness DECIMAL(10,4),
        momentum_acceleration DECIMAL(10,4),
        
        -- Volume-Based Momentum
        volume_weighted_momentum DECIMAL(10,4),
        obv_momentum DECIMAL(10,4),
        volume_trend DECIMAL(10,4),
        volume_price_correlation DECIMAL(10,4),

        -- Fundamental Momentum
        expected_eps_growth DECIMAL(10,4),
        recommendation_momentum DECIMAL(10,4),
        price_target_momentum DECIMAL(10,4),
        price_target_dispersion DECIMAL(10,4),
        earnings_momentum_qoq DECIMAL(10,4),
        earnings_acceleration DECIMAL(10,4),
        
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """
    
    cur.execute(create_sql)
    
    # Create indexes for performance
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_momentum_symbol ON momentum_metrics(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_momentum_date ON momentum_metrics(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_momentum_jt_12_1 ON momentum_metrics(jt_momentum_12_1 DESC);",
        "CREATE INDEX IF NOT EXISTS idx_momentum_risk_adj ON momentum_metrics(risk_adjusted_momentum DESC);",
        "CREATE INDEX IF NOT EXISTS idx_momentum_persistence ON momentum_metrics(momentum_persistence DESC);",
        "CREATE INDEX IF NOT EXISTS idx_momentum_volume ON momentum_metrics(volume_weighted_momentum DESC);",
        "CREATE INDEX IF NOT EXISTS idx_momentum_fundamental ON momentum_metrics(earnings_acceleration DESC);",
        "CREATE INDEX IF NOT EXISTS idx_momentum_quality ON momentum_metrics(momentum_strength DESC);"
    ]
    
    for index_sql in indexes:
        cur.execute(index_sql)
    
    conn.commit()
    logging.info("Momentum metrics table created successfully")

def load_momentum_batch(symbols: List[str], conn, cur, batch_size: int = 12) -> Tuple[int, int]:
    """Load momentum metrics in batches with parallel processing"""
    total_processed = 0
    total_inserted = 0
    failed_symbols = []

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        logging.info(f"Processing momentum batch {batch_num}/{total_batches}: {len(batch)} symbols (parallel)")
        log_mem(f"Momentum batch {batch_num} start")

        # Process in parallel with ThreadPoolExecutor (3 worker threads)
        momentum_data = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(process_symbol_momentum, symbol, conn): symbol for symbol in batch}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    data = future.result()
                    if data:
                        momentum_data.append(data)
                    else:
                        failed_symbols.append(symbol)
                    total_processed += 1
                except Exception as e:
                    failed_symbols.append(symbol)
                    logging.error(f"Exception processing momentum for {symbol}: {e}")
                    total_processed += 1
        
        # Insert to database
        if momentum_data:
            try:
                insert_data = []
                for item in momentum_data:
                    insert_data.append((
                        item['symbol'], item['date'], item.get('current_price'),
                        
                        # Jegadeesh-Titman momentum
                        item.get('jt_momentum_12_1'), item.get('jt_momentum_sharpe'), 
                        item.get('jt_momentum_volatility'),
                        
                        # Alternative horizons
                        item.get('momentum_6_1'), item.get('momentum_9_1'),
                        item.get('momentum_3_1'), item.get('momentum_12_3'),
                        
                        # Risk-adjusted
                        item.get('risk_adjusted_momentum'), item.get('sortino_momentum'),
                        
                        # Short to medium term
                        item.get('momentum_1w'), item.get('momentum_1m'),
                        item.get('momentum_3m'), item.get('momentum_6m'),
                        
                        # Quality metrics
                        item.get('momentum_persistence'), item.get('momentum_consistency'),
                        item.get('momentum_max_drawdown'), item.get('momentum_recovery_factor'),
                        item.get('momentum_skewness'), item.get('momentum_kurtosis'),
                        item.get('momentum_strength'), item.get('momentum_smoothness'),
                        item.get('momentum_acceleration'),
                        
                        # Volume-based
                        item.get('volume_weighted_momentum'), item.get('obv_momentum'),
                        item.get('volume_trend'), item.get('volume_price_correlation'),
                        
                        # Fundamental
                        item.get('expected_eps_growth'), item.get('recommendation_momentum'),
                        item.get('price_target_momentum'), item.get('price_target_dispersion'),
                        item.get('earnings_momentum_qoq'), item.get('earnings_acceleration')
                    ))
                
                insert_query = """
                    INSERT INTO momentum_metrics (
                        symbol, date, current_price,
                        jt_momentum_12_1, jt_momentum_sharpe, jt_momentum_volatility,
                        momentum_6_1, momentum_9_1, momentum_3_1, momentum_12_3,
                        risk_adjusted_momentum, sortino_momentum,
                        momentum_1w, momentum_1m, momentum_3m, momentum_6m,
                        momentum_persistence, momentum_consistency, momentum_max_drawdown,
                        momentum_recovery_factor, momentum_skewness, momentum_kurtosis,
                        momentum_strength, momentum_smoothness, momentum_acceleration,
                        volume_weighted_momentum, obv_momentum, volume_trend, volume_price_correlation,
                        expected_eps_growth, recommendation_momentum, price_target_momentum,
                        price_target_dispersion, earnings_momentum_qoq, earnings_acceleration
                    ) VALUES %s
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        current_price = EXCLUDED.current_price,
                        jt_momentum_12_1 = EXCLUDED.jt_momentum_12_1,
                        risk_adjusted_momentum = EXCLUDED.risk_adjusted_momentum,
                        momentum_persistence = EXCLUDED.momentum_persistence,
                        volume_weighted_momentum = EXCLUDED.volume_weighted_momentum,
                        earnings_acceleration = EXCLUDED.earnings_acceleration,
                        updated_at = CURRENT_TIMESTAMP
                """
                
                execute_values(cur, insert_query, insert_data)
                conn.commit()
                total_inserted += len(momentum_data)
                logging.info(f"Momentum batch {batch_num} inserted {len(momentum_data)} symbols successfully")
                
            except Exception as e:
                logging.error(f"Database insert error for momentum batch {batch_num}: {e}")
                conn.rollback()
        
        # Cleanup
        del momentum_data
        gc.collect()
        log_mem(f"Momentum batch {batch_num} end")
        time.sleep(2)
    
    if failed_symbols:
        logging.warning(f"Failed to process momentum for {len(failed_symbols)} symbols: {failed_symbols[:5]}...")
    
    return total_processed, total_inserted

if __name__ == "__main__":
    log_mem("startup")
    
    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create table
    create_momentum_metrics_table(cur, conn)
    
    # Get symbols to process - get ALL symbols from stock_scores that have price data
    cur.execute("""
        SELECT DISTINCT ss.symbol
        FROM stock_scores ss
        WHERE ss.symbol IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM price_daily pd
            WHERE pd.symbol = ss.symbol
        )
        ORDER BY ss.symbol
    """)
    symbols = [row['symbol'] for row in cur.fetchall()]

    if not symbols:
        logging.warning("No symbols found in stock_scores table with price data.")
        sys.exit(1)
    
    logging.info(f"Loading momentum metrics for {len(symbols)} symbols")
    
    # Load momentum data
    start_time = time.time()
    processed, inserted = load_momentum_batch(symbols, conn, cur)
    end_time = time.time()
    
    # Final statistics
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM momentum_metrics")
    total_symbols = cur.fetchone()[0]
    
    logging.info("=" * 60)
    logging.info("MOMENTUM METRICS LOADING COMPLETE")
    logging.info("=" * 60)
    logging.info(f"Symbols processed: {processed}")
    logging.info(f"Symbols with momentum data: {inserted}")
    logging.info(f"Total symbols in momentum_metrics table: {total_symbols}")
    logging.info(f"Processing time: {(end_time - start_time):.1f} seconds")
    log_mem("completion")
    
    # Sample results
    cur.execute("""
        SELECT m.symbol, se.company_name,
               m.jt_momentum_12_1, m.risk_adjusted_momentum, m.momentum_persistence,
               m.volume_weighted_momentum, m.earnings_acceleration,
               m.momentum_strength, m.price_target_momentum
        FROM momentum_metrics m
        JOIN stock_symbols_enhanced se ON m.symbol = se.symbol
        WHERE m.jt_momentum_12_1 IS NOT NULL
        AND m.date = (SELECT MAX(date) FROM momentum_metrics WHERE symbol = m.symbol)
        ORDER BY m.jt_momentum_12_1 DESC NULLS LAST
        LIMIT 10
    """)
    
    logging.info("\nTop 10 Stocks by Jegadeesh-Titman 12-1 Momentum:")
    for row in cur.fetchall():
        logging.info(f"  {row['symbol']} ({row['company_name'][:25]}): "
                    f"JT={row['jt_momentum_12_1']:.1%}, Risk-Adj={row['risk_adjusted_momentum']:.2f}, "
                    f"Persist={row['momentum_persistence']:.2f}, Vol-Wtd={row['volume_weighted_momentum']:.1%}, "
                    f"Earn-Accel={row['earnings_acceleration']:.2f}")
    
    # Sync momentum_score to stock_scores table (normalize jt_momentum_12_1 to 0-100 scale)
    logging.info("\nSyncing momentum scores to stock_scores table...")
    try:
        cur.execute("""
            UPDATE stock_scores ss
            SET momentum_score = ROUND(
                CASE
                    WHEN m.jt_momentum_12_1 IS NULL THEN 0.0
                    ELSE GREATEST(0, LEAST(100, 50 + (m.jt_momentum_12_1 / 2 * 100)))
                END::NUMERIC, 2),
                last_updated = CURRENT_TIMESTAMP
            FROM momentum_metrics m
            WHERE ss.symbol = m.symbol
            AND m.date = (
                SELECT MAX(date) FROM momentum_metrics
                WHERE symbol = m.symbol
            )
        """)
        conn.commit()
        updated_count = cur.rowcount
        logging.info(f"✅ Updated {updated_count} momentum_score values in stock_scores")
    except Exception as e:
        logging.error(f"Error syncing momentum_score to stock_scores: {e}")
        conn.rollback()

    # Final verification
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN momentum_score > 0 THEN 1 END) as with_score,
            ROUND(AVG(momentum_score)::NUMERIC, 2) as avg_score,
            MIN(momentum_score) as min_score,
            MAX(momentum_score) as max_score
        FROM stock_scores
        WHERE momentum_score IS NOT NULL
    """)
    stats = cur.fetchone()
    logging.info(f"\nStock Scores Momentum Update Summary:")
    logging.info(f"  Total stocks with momentum: {stats['total']}")
    logging.info(f"  Stocks with score > 0: {stats['with_score']}")
    logging.info(f"  Average momentum score: {stats['avg_score']}")
    logging.info(f"  Score range: {stats['min_score']:.2f} - {stats['max_score']:.2f}")

    cur.close()
    conn.close()
    logging.info("\n✅ Database connection closed")