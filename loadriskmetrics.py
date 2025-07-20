#!/usr/bin/env python3
import sys
import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import math

import boto3
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf
from scipy import stats
from sklearn.preprocessing import StandardScaler

# ─── Logging setup ───────────────────────────────────────────────────────────────
logging.basicConfig(stream=sys.stdout, level=logging.INFO
                    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger()

# ─── Environment variables ──────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "loadfundamentals-secrets")

def get_db_creds():
    """Fetch DB creds from Secrets Manager."""
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return (
        sec.get("username", sec.get("user"))
        sec["password"]
        sec["host"]
        int(sec["port"])
        sec["dbname"]
    )

class RiskCalculator:
    def __init__(self):
        self.risk_free_rate = 0.02  # 2% annual risk-free rate
        self.trading_days = 252
        
    def calculate_portfolio_returns(self, holdings: List[Dict], price_data: Dict) -> np.ndarray:
        """Calculate portfolio returns based on holdings and price data."""
        portfolio_returns = []
        
        # Get the minimum length across all price series
        min_length = min(len(data['returns']) for data in price_data.values() if data['returns'])
        
        if min_length == 0:
            return np.array([])
        
        for i in range(min_length):
            portfolio_return = 0
            for holding in holdings:
                symbol = holding['symbol']
                weight = holding['weight']
                
                if symbol in price_data and price_data[symbol]['returns']:
                    if i < len(price_data[symbol]['returns']):
                        portfolio_return += price_data[symbol]['returns'][i] * weight
            
            portfolio_returns.append(portfolio_return)
        
        return np.array(portfolio_returns)
    
    def calculate_volatility(self, returns: np.ndarray) -> float:
        """Calculate annualized volatility."""
        if len(returns) < 2:
            return 0.0
        return np.std(returns) * np.sqrt(self.trading_days)
    
    def calculate_var(self, returns: np.ndarray, confidence_level: float = 0.95) -> float:
        """Calculate Value at Risk using historical simulation."""
        if len(returns) == 0:
            return 0.0
        
        return -np.percentile(returns, (1 - confidence_level) * 100)
    
    def calculate_expected_shortfall(self, returns: np.ndarray, confidence_level: float = 0.95) -> float:
        """Calculate Expected Shortfall (Conditional VaR)."""
        if len(returns) == 0:
            return 0.0
        
        var_threshold = -self.calculate_var(returns, confidence_level)
        tail_returns = returns[returns <= var_threshold]
        
        if len(tail_returns) == 0:
            return 0.0
        
        return -np.mean(tail_returns)
    
    def calculate_sharpe_ratio(self, returns: np.ndarray) -> float:
        """Calculate Sharpe ratio."""
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns - (self.risk_free_rate / self.trading_days)
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns)
        
        if std_excess == 0:
            return 0.0
        
        return (mean_excess * self.trading_days) / (std_excess * np.sqrt(self.trading_days))
    
    def calculate_max_drawdown(self, returns: np.ndarray) -> float:
        """Calculate maximum drawdown."""
        if len(returns) == 0:
            return 0.0
        
        cumulative_returns = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max
        
        return -np.min(drawdown)
    
    def calculate_beta(self, asset_returns: np.ndarray, market_returns: np.ndarray) -> float:
        """Calculate beta relative to market."""
        if len(asset_returns) == 0 or len(market_returns) == 0:
            return 1.0
        
        min_length = min(len(asset_returns), len(market_returns))
        asset_returns = asset_returns[:min_length]
        market_returns = market_returns[:min_length]
        
        if np.var(market_returns) == 0:
            return 1.0
        
        return np.cov(asset_returns, market_returns)[0, 1] / np.var(market_returns)
    
    def calculate_correlation_matrix(self, holdings: List[Dict], price_data: Dict) -> Dict:
        """Calculate correlation matrix for portfolio holdings."""
        symbols = [h['symbol'] for h in holdings]
        returns_matrix = []
        
        for symbol in symbols:
            if symbol in price_data and price_data[symbol]['returns']:
                returns_matrix.append(price_data[symbol]['returns'])
        
        if len(returns_matrix) < 2:
            return {}
        
        # Make all return series the same length
        min_length = min(len(returns) for returns in returns_matrix)
        returns_matrix = [returns[:min_length] for returns in returns_matrix]
        
        # Calculate correlation matrix
        correlation_matrix = np.corrcoef(returns_matrix)
        
        # Convert to dictionary format
        correlation_dict = {}
        for i, symbol1 in enumerate(symbols):
            correlation_dict[symbol1] = {}
            for j, symbol2 in enumerate(symbols):
                if i < len(correlation_matrix) and j < len(correlation_matrix[i]):
                    correlation_dict[symbol1][symbol2] = float(correlation_matrix[i][j])
        
        return correlation_dict
    
    def calculate_concentration_risk(self, holdings: List[Dict]) -> Dict:
        """Calculate concentration risk metrics."""
        weights = [h['weight'] for h in holdings]
        
        # Herfindahl Index
        herfindahl_index = sum(w * w for w in weights)
        
        # Effective number of holdings
        effective_holdings = 1 / herfindahl_index if herfindahl_index > 0 else 0
        
        # Concentration risk level
        if herfindahl_index > 0.25:
            risk_level = 'high'
        elif herfindahl_index > 0.15:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        return {
            'herfindahl_index': herfindahl_index
            'effective_number_of_holdings': effective_holdings
            'concentration_risk_level': risk_level
            'largest_holding_weight': max(weights) if weights else 0
            'top_5_concentration': sum(sorted(weights, reverse=True)[:5])
        }
    
    def calculate_sector_exposure(self, holdings: List[Dict]) -> Dict:
        """Calculate sector exposure risk."""
        sector_exposure = {}
        
        for holding in holdings:
            sector = holding.get('sector', 'Unknown')
            weight = holding['weight']
            
            if sector in sector_exposure:
                sector_exposure[sector] += weight
            else:
                sector_exposure[sector] = weight
        
        return sector_exposure
    
    def perform_stress_test(self, holdings: List[Dict], price_data: Dict, scenarios: List[Dict]) -> Dict:
        """Perform stress testing on portfolio."""
        stress_results = []
        
        for scenario in scenarios:
            scenario_pnl = 0
            scenario_name = scenario['name']
            shock_type = scenario['type']
            magnitude = scenario['magnitude']
            
            for holding in holdings:
                symbol = holding['symbol']
                weight = holding['weight']
                current_price = holding.get('current_price', 100)
                
                # Apply stress scenario
                if shock_type == 'market_shock':
                    # Apply uniform market shock
                    shock_return = magnitude
                elif shock_type == 'sector_shock':
                    # Apply sector-specific shock
                    sector = holding.get('sector', 'Unknown')
                    if sector in scenario.get('affected_sectors', []):
                        shock_return = magnitude
                    else:
                        shock_return = magnitude * 0.5  # Reduced impact
                elif shock_type == 'volatility_shock':
                    # Increase volatility
                    if symbol in price_data and price_data[symbol]['returns']:
                        vol = np.std(price_data[symbol]['returns'])
                        shock_return = -vol * magnitude
                    else:
                        shock_return = magnitude * 0.1
                else:
                    shock_return = magnitude
                
                # Calculate P&L impact
                position_pnl = weight * shock_return
                scenario_pnl += position_pnl
            
            stress_results.append({
                'scenario_name': scenario_name
                'scenario_type': shock_type
                'portfolio_pnl': scenario_pnl
                'portfolio_pnl_percent': scenario_pnl * 100
            })
        
        return {
            'scenarios': stress_results
            'worst_case_pnl': min(s['portfolio_pnl'] for s in stress_results)
            'best_case_pnl': max(s['portfolio_pnl'] for s in stress_results)
            'average_pnl': np.mean([s['portfolio_pnl'] for s in stress_results])
        }

def get_historical_prices(symbols: List[str], period: str = '1y') -> Dict:
    """Get historical price data for symbols."""
    price_data = {}
    
    for symbol in symbols:
        try:
            logger.info(f"Fetching price data for {symbol}")
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            
            if hist.empty:
                logger.warning(f"No price data found for {symbol}")
                continue
            
            # Calculate returns
            prices = hist['Close'].values
            returns = np.diff(prices) / prices[:-1]
            
            price_data[symbol] = {
                'prices': prices.tolist()
                'returns': returns.tolist()
                'dates': hist.index.tolist()
            }
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            continue
    
    return price_data

def get_market_data(period: str = '1y') -> Dict:
    """Get market benchmark data (S&P 500)."""
    try:
        spy = yf.Ticker('SPY')
        hist = spy.history(period=period)
        
        if hist.empty:
            return {'returns': []}
        
        prices = hist['Close'].values
        returns = np.diff(prices) / prices[:-1]
        
        return {
            'prices': prices.tolist()
            'returns': returns.tolist()
            'dates': hist.index.tolist()
        }
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
        return {'returns': []}

def main():
    try:
        # Connect to database
        user, pwd, host, port, db = get_db_creds()
        conn = psycopg2.connect(
            host=host
            port=port
            dbname=db
            user=user
            password=pwd
            
        )
        cur = conn.cursor()

        # Create risk tables
        logger.info("Creating risk tables...")
        
        # Portfolio risk metrics table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_risk_metrics (
                id SERIAL PRIMARY KEY
                portfolio_id INTEGER NOT NULL
                volatility DECIMAL(10,6)
                var_95 DECIMAL(10,6)
                var_99 DECIMAL(10,6)
                expected_shortfall DECIMAL(10,6)
                sharpe_ratio DECIMAL(10,6)
                max_drawdown DECIMAL(10,6)
                beta DECIMAL(10,6)
                correlation_data JSONB
                concentration_metrics JSONB
                sector_exposure JSONB
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                UNIQUE(portfolio_id)
            );
        """)
        
        # Risk alerts table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS risk_alerts (
                id SERIAL PRIMARY KEY
                user_id VARCHAR(255) NOT NULL
                portfolio_id INTEGER
                alert_type VARCHAR(50) NOT NULL
                severity VARCHAR(20) NOT NULL
                title VARCHAR(255) NOT NULL
                description TEXT
                metric_name VARCHAR(100)
                current_value DECIMAL(10,6)
                threshold_value DECIMAL(10,6)
                symbol VARCHAR(10)
                status VARCHAR(20) DEFAULT 'active'
                acknowledged_at TIMESTAMP
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Risk limits table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS risk_limits (
                id SERIAL PRIMARY KEY
                portfolio_id INTEGER NOT NULL
                metric_name VARCHAR(100) NOT NULL
                threshold_value DECIMAL(10,6) NOT NULL
                warning_threshold DECIMAL(10,6)
                threshold_type VARCHAR(20) DEFAULT 'greater_than'
                is_active BOOLEAN DEFAULT true
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                UNIQUE(portfolio_id, metric_name)
            );
        """)
        
        # Market risk indicators table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS market_risk_indicators (
                id SERIAL PRIMARY KEY
                indicator_name VARCHAR(100) NOT NULL
                current_value DECIMAL(10,6)
                risk_level VARCHAR(20)
                description TEXT
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                UNIQUE(indicator_name)
            );
        """)
        
        # Stress test results table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stress_test_results (
                id SERIAL PRIMARY KEY
                portfolio_id INTEGER NOT NULL
                scenario_name VARCHAR(100) NOT NULL
                scenario_type VARCHAR(50)
                portfolio_pnl DECIMAL(10,6)
                portfolio_pnl_percent DECIMAL(8,4)
                test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_risk_metrics_portfolio_id ON portfolio_risk_metrics(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_risk_alerts_user_id ON risk_alerts(user_id);
            CREATE INDEX IF NOT EXISTS idx_risk_alerts_portfolio_id ON risk_alerts(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_risk_alerts_status ON risk_alerts(status);
            CREATE INDEX IF NOT EXISTS idx_risk_limits_portfolio_id ON risk_limits(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_market_risk_indicators_name ON market_risk_indicators(indicator_name);
            CREATE INDEX IF NOT EXISTS idx_stress_test_results_portfolio_id ON stress_test_results(portfolio_id);
        """)
        
        conn.commit()
        logger.info("Risk tables created successfully")

        # Initialize risk calculator
        risk_calculator = RiskCalculator()
        
        # Get market data for beta calculation
        market_data = get_market_data()
        
        # Get all portfolios with holdings
        cur.execute("""
            SELECT DISTINCT p.id, p.user_id, p.name, p.total_value
            FROM portfolios p
            JOIN portfolio_holdings ph ON p.id = ph.portfolio_id
            WHERE ph.quantity > 0
        """)
        
        portfolios = cur.fetchall()
        logger.info(f"Found {len(portfolios)} portfolios to analyze")
        
        for portfolio in portfolios:
            portfolio_id, user_id, portfolio_name, total_value = portfolio
            
            try:
                logger.info(f"Calculating risk for portfolio {portfolio_id}: {portfolio_name}")
                
                # Get portfolio holdings
                cur.execute("""
                    SELECT 
                        ph.symbol
                        ph.quantity
                        ph.average_cost
                        ph.current_price
                        ph.market_value
                        ph.weight
                        COALESCE(sse.sector, 'Unknown') as sector
                        COALESCE(sse.industry, 'Unknown') as industry
                    FROM portfolio_holdings ph
                    LEFT JOIN stock_symbols_enhanced sse ON ph.symbol = sse.symbol
                    WHERE ph.portfolio_id = %s AND ph.quantity > 0
                """, (portfolio_id,))
                
                holdings_data = cur.fetchall()
                
                if not holdings_data:
                    logger.warning(f"No holdings found for portfolio {portfolio_id}")
                    continue
                
                # Convert to list of dictionaries
                holdings = []
                symbols = []
                for holding in holdings_data:
                    holding_dict = {
                        'symbol': holding[0]
                        'quantity': float(holding[1])
                        'average_cost': float(holding[2])
                        'current_price': float(holding[3])
                        'market_value': float(holding[4])
                        'weight': float(holding[5])
                        'sector': holding[6]
                        'industry': holding[7]
                    }
                    holdings.append(holding_dict)
                    symbols.append(holding[0])
                
                # Get historical price data
                logger.info(f"Fetching price data for {len(symbols)} symbols")
                price_data = get_historical_prices(symbols)
                
                if not price_data:
                    logger.warning(f"No price data available for portfolio {portfolio_id}")
                    continue
                
                # Calculate portfolio returns
                portfolio_returns = risk_calculator.calculate_portfolio_returns(holdings, price_data)
                
                if len(portfolio_returns) == 0:
                    logger.warning(f"Could not calculate returns for portfolio {portfolio_id}")
                    continue
                
                # Calculate risk metrics
                volatility = risk_calculator.calculate_volatility(portfolio_returns)
                var_95 = risk_calculator.calculate_var(portfolio_returns, 0.95)
                var_99 = risk_calculator.calculate_var(portfolio_returns, 0.99)
                expected_shortfall = risk_calculator.calculate_expected_shortfall(portfolio_returns, 0.95)
                sharpe_ratio = risk_calculator.calculate_sharpe_ratio(portfolio_returns)
                max_drawdown = risk_calculator.calculate_max_drawdown(portfolio_returns)
                
                # Calculate beta
                beta = 1.0
                if market_data.get('returns'):
                    beta = risk_calculator.calculate_beta(portfolio_returns, np.array(market_data['returns']))
                
                # Calculate correlation matrix
                correlation_matrix = risk_calculator.calculate_correlation_matrix(holdings, price_data)
                
                # Calculate concentration risk
                concentration_metrics = risk_calculator.calculate_concentration_risk(holdings)
                
                # Calculate sector exposure
                sector_exposure = risk_calculator.calculate_sector_exposure(holdings)
                
                # Store risk metrics
                cur.execute("""
                    INSERT INTO portfolio_risk_metrics (
                        portfolio_id, volatility, var_95, var_99, expected_shortfall
                        sharpe_ratio, max_drawdown, beta, correlation_data
                        concentration_metrics, sector_exposure, calculated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (portfolio_id) DO UPDATE SET
                        volatility = EXCLUDED.volatility
                        var_95 = EXCLUDED.var_95
                        var_99 = EXCLUDED.var_99
                        expected_shortfall = EXCLUDED.expected_shortfall
                        sharpe_ratio = EXCLUDED.sharpe_ratio
                        max_drawdown = EXCLUDED.max_drawdown
                        beta = EXCLUDED.beta
                        correlation_data = EXCLUDED.correlation_data
                        concentration_metrics = EXCLUDED.concentration_metrics
                        sector_exposure = EXCLUDED.sector_exposure
                        calculated_at = EXCLUDED.calculated_at
                """, (
                    portfolio_id
                    volatility
                    var_95
                    var_99
                    expected_shortfall
                    sharpe_ratio
                    max_drawdown
                    beta
                    json.dumps(correlation_matrix)
                    json.dumps(concentration_metrics)
                    json.dumps(sector_exposure)
                ))
                
                # Perform stress testing
                stress_scenarios = [
                    {'name': 'Market Crash', 'type': 'market_shock', 'magnitude': -0.2}
                    {'name': 'Sector Rotation', 'type': 'sector_shock', 'magnitude': -0.15, 'affected_sectors': ['Technology', 'Consumer Discretionary']}
                    {'name': 'Volatility Spike', 'type': 'volatility_shock', 'magnitude': 2.0}
                    {'name': 'Interest Rate Shock', 'type': 'market_shock', 'magnitude': -0.1}
                ]
                
                stress_results = risk_calculator.perform_stress_test(holdings, price_data, stress_scenarios)
                
                # Store stress test results
                cur.execute("DELETE FROM stress_test_results WHERE portfolio_id = %s", (portfolio_id,))
                
                for scenario in stress_results['scenarios']:
                    cur.execute("""
                        INSERT INTO stress_test_results (
                            portfolio_id, scenario_name, scenario_type
                            portfolio_pnl, portfolio_pnl_percent, test_date
                        ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (
                        portfolio_id
                        scenario['scenario_name']
                        scenario['scenario_type']
                        scenario['portfolio_pnl']
                        scenario['portfolio_pnl_percent']
                    ))
                
                conn.commit()
                logger.info(f"✓ Risk metrics calculated for portfolio {portfolio_id}")
                
            except Exception as e:
                logger.error(f"Error calculating risk for portfolio {portfolio_id}: {e}")
                conn.rollback()
                continue
        
        # Update market risk indicators
        logger.info("Updating market risk indicators...")
        
        try:
            # VIX (volatility index)
            vix_data = yf.Ticker('^VIX').history(period='1d')
            if not vix_data.empty:
                vix_value = float(vix_data['Close'].iloc[-1])
                vix_risk_level = 'high' if vix_value > 30 else 'medium' if vix_value > 20 else 'low'
                
                cur.execute("""
                    INSERT INTO market_risk_indicators (
                        indicator_name, current_value, risk_level, description, last_updated
                    ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (indicator_name) DO UPDATE SET
                        current_value = EXCLUDED.current_value
                        risk_level = EXCLUDED.risk_level
                        last_updated = EXCLUDED.last_updated
                """, (
                    'VIX'
                    vix_value
                    vix_risk_level
                    'CBOE Volatility Index - Market fear gauge'
                ))
            
            # 10-Year Treasury Yield
            tnx_data = yf.Ticker('^TNX').history(period='1d')
            if not tnx_data.empty:
                tnx_value = float(tnx_data['Close'].iloc[-1])
                tnx_risk_level = 'high' if tnx_value > 5.0 else 'medium' if tnx_value > 3.0 else 'low'
                
                cur.execute("""
                    INSERT INTO market_risk_indicators (
                        indicator_name, current_value, risk_level, description, last_updated
                    ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (indicator_name) DO UPDATE SET
                        current_value = EXCLUDED.current_value
                        risk_level = EXCLUDED.risk_level
                        last_updated = EXCLUDED.last_updated
                """, (
                    '10Y_TREASURY'
                    tnx_value
                    tnx_risk_level
                    '10-Year Treasury Yield - Interest rate risk indicator'
                ))
            
            conn.commit()
            logger.info("✓ Market risk indicators updated")
            
        except Exception as e:
            logger.error(f"Error updating market risk indicators: {e}")
            conn.rollback()
        
        # Clean up
        cur.close()
        conn.close()
        
        logger.info("Risk metrics calculation completed successfully")

    except Exception as e:
        logger.exception("Risk metrics calculation failed")
        try:
            cur.close()
            conn.close()
        except:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()