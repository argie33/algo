"""
Advanced Trading Engine
Orchestrates the entire algorithmic trading process with risk management and monitoring
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
import json
import time
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from pathlib import Path

from alpaca_client import AlpacaClient, Order, Position
from strategies.base_strategy import BaseStrategy, Signal, SignalType, StrategyManager
from strategies.momentum_strategy import MomentumBreakoutStrategy
from config import TRADING_CONFIG, TRADING_UNIVERSE, MONITORING_CONFIG

class TradingMode(Enum):
    LIVE = "live"
    PAPER = "paper"
    BACKTEST = "backtest"
    SIMULATION = "simulation"

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

@dataclass
class TradingSession:
    """Trading session information"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    mode: TradingMode = TradingMode.PAPER
    total_trades: int = 0
    profitable_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    
class RiskManager:
    """Comprehensive risk management system"""
    
    def __init__(self, config=None):
        self.config = config or TRADING_CONFIG
        self.logger = logging.getLogger("risk_manager")
        
        # Risk limits
        self.max_position_size = self.config.max_position_size
        self.max_portfolio_risk = self.config.max_portfolio_risk
        self.max_daily_loss = self.config.max_daily_loss
        self.max_drawdown = self.config.max_drawdown
        
        # Tracking
        self.daily_pnl = 0.0
        self.peak_portfolio_value = 0.0
        self.current_drawdown = 0.0
        self.position_limits = {}
        
        # Risk metrics
        self.var_95 = 0.0
        self.beta = 1.0
        self.correlation_matrix = pd.DataFrame()
        
    def check_pre_trade_risk(self, signal: Signal, portfolio_value: float, 
                           positions: List[Position]) -> Tuple[bool, str]:
        """Comprehensive pre-trade risk checks"""
        
        # 1. Position size check
        position_value = signal.price * self.calculate_position_size(signal, portfolio_value)
        if position_value > portfolio_value * self.max_position_size:
            return False, f"Position size exceeds limit: {position_value/portfolio_value:.2%} > {self.max_position_size:.2%}"
        
        # 2. Portfolio risk check
        portfolio_risk = self.calculate_portfolio_risk(signal, positions, portfolio_value)
        if portfolio_risk > self.max_portfolio_risk:
            return False, f"Portfolio risk exceeds limit: {portfolio_risk:.2%} > {self.max_portfolio_risk:.2%}"
        
        # 3. Daily loss check
        if self.daily_pnl < -portfolio_value * self.max_daily_loss:
            return False, f"Daily loss limit exceeded: {self.daily_pnl/portfolio_value:.2%} > {self.max_daily_loss:.2%}"
        
        # 4. Drawdown check
        if self.current_drawdown > self.max_drawdown:
            return False, f"Drawdown limit exceeded: {self.current_drawdown:.2%} > {self.max_drawdown:.2%}"
        
        # 5. Concentration check
        sector_concentration = self.calculate_sector_concentration(signal, positions)
        if sector_concentration > 0.3:  # 30% sector limit
            return False, f"Sector concentration too high: {sector_concentration:.2%}"
        
        # 6. Correlation check
        correlation_risk = self.calculate_correlation_risk(signal, positions)
        if correlation_risk > 0.7:  # 70% correlation limit
            return False, f"Position correlation too high: {correlation_risk:.2%}"
        
        return True, "Risk check passed"
    
    def calculate_position_size(self, signal: Signal, portfolio_value: float) -> float:
        """Calculate optimal position size using Kelly criterion and risk parity"""
        
        # Base position size (percentage of portfolio)
        base_size = portfolio_value * self.max_position_size
        
        # Kelly criterion adjustment
        if hasattr(signal, 'win_probability') and hasattr(signal, 'avg_win_loss_ratio'):
            kelly_fraction = (signal.win_probability * signal.avg_win_loss_ratio - (1 - signal.win_probability)) / signal.avg_win_loss_ratio
            kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
            base_size *= kelly_fraction
        
        # Risk-adjusted sizing
        if signal.stop_loss:
            risk_per_share = signal.price - signal.stop_loss
            if risk_per_share > 0:
                # Risk-based position sizing
                risk_amount = portfolio_value * self.max_portfolio_risk
                shares = risk_amount / risk_per_share
                risk_size = shares * signal.price
                base_size = min(base_size, risk_size)
        
        # Volatility adjustment
        if hasattr(signal, 'volatility') and signal.volatility > 0:
            vol_adjustment = 0.02 / signal.volatility  # Target 2% volatility
            base_size *= min(vol_adjustment, 2.0)  # Cap adjustment
        
        return base_size / signal.price  # Convert to shares
    
    def calculate_portfolio_risk(self, signal: Signal, positions: List[Position], 
                               portfolio_value: float) -> float:
        """Calculate portfolio-level risk"""
        
        # Current portfolio risk
        current_risk = sum(abs(pos.unrealized_pl) for pos in positions) / portfolio_value
        
        # New position risk
        if signal.stop_loss:
            new_position_risk = abs(signal.price - signal.stop_loss) / signal.price
        else:
            new_position_risk = 0.02  # Default 2% risk
        
        position_weight = self.calculate_position_size(signal, portfolio_value) * signal.price / portfolio_value
        new_risk = new_position_risk * position_weight
        
        return current_risk + new_risk
    
    def calculate_sector_concentration(self, signal: Signal, positions: List[Position]) -> float:
        """Calculate sector concentration"""
        # Simplified sector mapping (in production, use proper sector data)
        sector_map = {
            'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology',
            'AMZN': 'Technology', 'META': 'Technology', 'TSLA': 'Technology',
            'JPM': 'Financials', 'BAC': 'Financials', 'WFC': 'Financials'
        }
        
        signal_sector = sector_map.get(signal.symbol, 'Unknown')
        
        # Calculate current sector exposure
        sector_exposure = {}
        total_value = 0
        
        for pos in positions:
            sector = sector_map.get(pos.symbol, 'Unknown')
            sector_exposure[sector] = sector_exposure.get(sector, 0) + abs(pos.market_value)
            total_value += abs(pos.market_value)
        
        if total_value == 0:
            return 0
        
        current_sector_pct = sector_exposure.get(signal_sector, 0) / total_value
        return current_sector_pct
    
    def calculate_correlation_risk(self, signal: Signal, positions: List[Position]) -> float:
        """Calculate position correlation risk"""
        # Simplified correlation (in production, use historical correlation matrix)
        high_corr_pairs = {
            ('AAPL', 'MSFT'): 0.8,
            ('AAPL', 'GOOGL'): 0.7,
            ('JPM', 'BAC'): 0.9,
            ('SPY', 'QQQ'): 0.85
        }
        
        max_correlation = 0
        for pos in positions:
            pair = tuple(sorted([signal.symbol, pos.symbol]))
            correlation = high_corr_pairs.get(pair, 0.3)  # Default low correlation
            max_correlation = max(max_correlation, correlation)
        
        return max_correlation
    
    def update_risk_metrics(self, portfolio_value: float, positions: List[Position]):
        """Update risk metrics"""
        # Update peak and drawdown
        if portfolio_value > self.peak_portfolio_value:
            self.peak_portfolio_value = portfolio_value
        
        if self.peak_portfolio_value > 0:
            self.current_drawdown = (self.peak_portfolio_value - portfolio_value) / self.peak_portfolio_value
        
        # Update daily P&L (simplified)
        self.daily_pnl = sum(pos.unrealized_pl for pos in positions)
        
        # Calculate VaR (simplified)
        if positions:
            portfolio_returns = [pos.unrealized_plpc for pos in positions if pos.unrealized_plpc]
            if portfolio_returns:
                self.var_95 = np.percentile(portfolio_returns, 5)

class TradingEngine:
    """Main trading engine that orchestrates everything"""
    
    def __init__(self, mode: TradingMode = TradingMode.PAPER):
        self.mode = mode
        self.logger = logging.getLogger("trading_engine")
        
        # Initialize components
        self.alpaca_client = AlpacaClient()
        self.strategy_manager = StrategyManager()
        self.risk_manager = RiskManager()
        
        # Trading state
        self.is_running = False
        self.current_session = None
        self.last_update = None
        
        # Data storage
        self.market_data = {}
        self.active_signals = {}
        self.order_history = []
        self.performance_history = []
        
        # Database for persistence
        self.db_path = Path("trading_data.db")
        self.init_database()
        
        # Initialize strategies
        self.init_strategies()
        
        self.logger.info(f"Trading engine initialized in {mode.value} mode")
    
    def init_database(self):
        """Initialize SQLite database for storing trading data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trading_sessions (
                session_id TEXT PRIMARY KEY,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                mode TEXT,
                total_trades INTEGER,
                profitable_trades INTEGER,
                total_pnl REAL,
                max_drawdown REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                symbol TEXT,
                signal_type TEXT,
                strength REAL,
                confidence REAL,
                timestamp TIMESTAMP,
                price REAL,
                target_price REAL,
                stop_loss REAL,
                metadata TEXT,
                executed BOOLEAN DEFAULT FALSE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                symbol TEXT,
                side TEXT,
                quantity REAL,
                price REAL,
                timestamp TIMESTAMP,
                order_id TEXT,
                pnl REAL,
                strategy TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp TIMESTAMP,
                portfolio_value REAL,
                cash REAL,
                positions_value REAL,
                daily_pnl REAL,
                total_pnl REAL,
                drawdown REAL,
                var_95 REAL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def init_strategies(self):
        """Initialize trading strategies"""
        # Add momentum breakout strategy
        momentum_strategy = MomentumBreakoutStrategy()
        self.strategy_manager.add_strategy(momentum_strategy, weight=0.4)
        
        # Add more strategies here as they're developed
        # mean_reversion = MeanReversionStrategy()
        # self.strategy_manager.add_strategy(mean_reversion, weight=0.3)
        
        self.logger.info("Strategies initialized")
    
    def start_trading_session(self) -> str:
        """Start a new trading session"""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.current_session = TradingSession(
            session_id=session_id,
            start_time=datetime.now(),
            mode=self.mode
        )
        
        # Store session in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trading_sessions 
            (session_id, start_time, mode, total_trades, profitable_trades, total_pnl, max_drawdown)
            VALUES (?, ?, ?, 0, 0, 0.0, 0.0)
        ''', (session_id, self.current_session.start_time, self.mode.value))
        conn.commit()
        conn.close()
        
        self.is_running = True
        self.logger.info(f"Trading session {session_id} started")
        
        return session_id
    
    def stop_trading_session(self):
        """Stop the current trading session"""
        if self.current_session:
            self.current_session.end_time = datetime.now()
            
            # Update session in database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trading_sessions 
                SET end_time = ?, total_trades = ?, profitable_trades = ?, 
                    total_pnl = ?, max_drawdown = ?
                WHERE session_id = ?
            ''', (
                self.current_session.end_time,
                self.current_session.total_trades,
                self.current_session.profitable_trades,
                self.current_session.total_pnl,
                self.current_session.max_drawdown,
                self.current_session.session_id
            ))
            conn.commit()
            conn.close()
            
            self.logger.info(f"Trading session {self.current_session.session_id} ended")
        
        self.is_running = False
        self.current_session = None
    
    async def run_trading_loop(self):
        """Main trading loop"""
        self.logger.info("Starting trading loop")
        
        while self.is_running:
            try:
                # Check if market is open
                if not self.alpaca_client.is_market_open():
                    self.logger.info("Market is closed, sleeping...")
                    await asyncio.sleep(300)  # 5 minutes
                    continue
                
                # 1. Fetch market data
                await self.fetch_market_data()
                
                # 2. Generate signals
                signals = self.generate_signals()
                
                # 3. Execute trades
                await self.execute_trades(signals)
                
                # 4. Monitor positions
                await self.monitor_positions()
                
                # 5. Update performance
                await self.update_performance()
                
                # 6. Risk management
                await self.risk_management_check()
                
                # Sleep before next iteration
                await asyncio.sleep(60)  # 1 minute
                
            except Exception as e:
                self.logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(60)
    
    async def fetch_market_data(self):
        """Fetch market data for all symbols"""
        self.logger.debug("Fetching market data")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            for symbol in TRADING_UNIVERSE:
                future = executor.submit(
                    self.alpaca_client.get_historical_data,
                    symbol, 
                    timeframe="1Day",
                    limit=100
                )
                futures.append((symbol, future))
            
            for symbol, future in futures:
                try:
                    data = future.result(timeout=30)
                    if not data.empty:
                        self.market_data[symbol] = data
                except Exception as e:
                    self.logger.warning(f"Failed to fetch data for {symbol}: {e}")
        
        self.last_update = datetime.now()
        self.logger.debug(f"Market data updated for {len(self.market_data)} symbols")
    
    def generate_signals(self) -> List[Signal]:
        """Generate trading signals from all strategies"""
        if not self.market_data:
            return []
        
        # Generate signals from all strategies
        all_signals = self.strategy_manager.get_all_signals(self.market_data)
        
        # Aggregate signals for same symbol
        aggregated_signals = self.strategy_manager.aggregate_signals(all_signals)
        
        # Filter and validate signals
        valid_signals = []
        for signal in aggregated_signals:
            symbol_data = self.market_data.get(signal.symbol, pd.DataFrame())
            
            if not symbol_data.empty:
                # Check if signal is valid
                for strategy in self.strategy_manager.strategies.values():
                    if strategy.is_valid_signal(signal, symbol_data):
                        valid_signals.append(signal)
                        break
        
        # Store signals in database
        if valid_signals:
            self.store_signals(valid_signals)
        
        self.logger.info(f"Generated {len(valid_signals)} valid signals")
        return valid_signals
    
    def store_signals(self, signals: List[Signal]):
        """Store signals in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for signal in signals:
            cursor.execute('''
                INSERT INTO signals 
                (session_id, symbol, signal_type, strength, confidence, timestamp, 
                 price, target_price, stop_loss, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.current_session.session_id if self.current_session else 'test',
                signal.symbol,
                signal.signal_type.value,
                signal.strength,
                signal.confidence,
                signal.timestamp,
                signal.price,
                signal.target_price,
                signal.stop_loss,
                json.dumps(signal.metadata) if signal.metadata else '{}'
            ))
        
        conn.commit()
        conn.close()
    
    async def execute_trades(self, signals: List[Signal]):
        """Execute trades based on signals"""
        if not signals:
            return
        
        # Get current account and positions
        account = self.alpaca_client.get_account()
        positions = self.alpaca_client.get_positions()
        
        portfolio_value = account['portfolio_value']
        
        for signal in signals:
            try:
                # Risk check
                risk_ok, risk_msg = self.risk_manager.check_pre_trade_risk(
                    signal, portfolio_value, positions
                )
                
                if not risk_ok:
                    self.logger.warning(f"Risk check failed for {signal.symbol}: {risk_msg}")
                    continue
                
                # Calculate position size
                position_size = self.risk_manager.calculate_position_size(signal, portfolio_value)
                
                if position_size < 1:  # Minimum 1 share
                    self.logger.warning(f"Position size too small for {signal.symbol}: {position_size}")
                    continue
                
                # Place order
                order = self.place_order(signal, position_size)
                
                if order:
                    self.logger.info(f"Order placed: {signal.symbol} {signal.signal_type.value} {position_size} shares")
                    
                    # Store trade
                    self.store_trade(signal, order)
                    
                    # Update session stats
                    if self.current_session:
                        self.current_session.total_trades += 1
                
            except Exception as e:
                self.logger.error(f"Error executing trade for {signal.symbol}: {e}")
    
    def place_order(self, signal: Signal, position_size: float) -> Optional[Order]:
        """Place order with proper order management"""
        try:
            # Determine order side
            side = "buy" if signal.signal_type == SignalType.BUY else "sell"
            
            # Place market order for immediate execution
            order = self.alpaca_client.place_order(
                symbol=signal.symbol,
                qty=position_size,
                side=side,
                order_type="market",
                time_in_force="day"
            )
            
            # Place stop loss order if specified
            if signal.stop_loss and order:
                stop_side = "sell" if side == "buy" else "buy"
                stop_order = self.alpaca_client.place_order(
                    symbol=signal.symbol,
                    qty=position_size,
                    side=stop_side,
                    order_type="stop",
                    time_in_force="gtc",
                    stop_price=signal.stop_loss
                )
                
                if stop_order:
                    self.logger.info(f"Stop loss order placed for {signal.symbol} at ${signal.stop_loss}")
            
            return order
            
        except Exception as e:
            self.logger.error(f"Error placing order for {signal.symbol}: {e}")
            return None
    
    def store_trade(self, signal: Signal, order: Order):
        """Store trade in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades 
            (session_id, symbol, side, quantity, price, timestamp, order_id, pnl, strategy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            self.current_session.session_id if self.current_session else 'test',
            signal.symbol,
            order.side,
            order.qty,
            order.filled_avg_price or signal.price,
            order.filled_at or datetime.now(),
            order.id,
            0.0,  # PnL calculated later
            signal.metadata.get('strategy', 'unknown')
        ))
        
        conn.commit()
        conn.close()
    
    async def monitor_positions(self):
        """Monitor existing positions and manage exits"""
        positions = self.alpaca_client.get_positions()
        
        for position in positions:
            try:
                # Check for exit conditions
                symbol_data = self.market_data.get(position.symbol, pd.DataFrame())
                
                if symbol_data.empty:
                    continue
                
                current_price = symbol_data['close'].iloc[-1]
                
                # Check profit target (simplified)
                profit_pct = (current_price - position.avg_entry_price) / position.avg_entry_price
                
                if position.side == 'long':
                    if profit_pct > 0.06:  # 6% profit target
                        await self.close_position(position, "profit_target")
                    elif profit_pct < -0.03:  # 3% stop loss
                        await self.close_position(position, "stop_loss")
                else:  # short position
                    if profit_pct < -0.06:  # 6% profit target for short
                        await self.close_position(position, "profit_target")
                    elif profit_pct > 0.03:  # 3% stop loss for short
                        await self.close_position(position, "stop_loss")
                
            except Exception as e:
                self.logger.error(f"Error monitoring position {position.symbol}: {e}")
    
    async def close_position(self, position: Position, reason: str):
        """Close a position"""
        try:
            success = self.alpaca_client.close_position(position.symbol)
            
            if success:
                self.logger.info(f"Position closed: {position.symbol} - {reason}")
                
                # Update session stats
                if self.current_session and position.unrealized_pl > 0:
                    self.current_session.profitable_trades += 1
                    self.current_session.total_pnl += position.unrealized_pl
                
        except Exception as e:
            self.logger.error(f"Error closing position {position.symbol}: {e}")
    
    async def update_performance(self):
        """Update performance metrics"""
        try:
            account = self.alpaca_client.get_account()
            positions = self.alpaca_client.get_positions()
            
            portfolio_value = account['portfolio_value']
            cash = account['cash']
            positions_value = sum(pos.market_value for pos in positions)
            
            # Update risk metrics
            self.risk_manager.update_risk_metrics(portfolio_value, positions)
            
            # Store performance
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO performance 
                (session_id, timestamp, portfolio_value, cash, positions_value, 
                 daily_pnl, total_pnl, drawdown, var_95)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.current_session.session_id if self.current_session else 'test',
                datetime.now(),
                portfolio_value,
                cash,
                positions_value,
                self.risk_manager.daily_pnl,
                sum(pos.unrealized_pl for pos in positions),
                self.risk_manager.current_drawdown,
                self.risk_manager.var_95
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error updating performance: {e}")
    
    async def risk_management_check(self):
        """Perform risk management checks"""
        try:
            account = self.alpaca_client.get_account()
            positions = self.alpaca_client.get_positions()
            
            portfolio_value = account['portfolio_value']
            
            # Check daily loss limit
            daily_pnl = sum(pos.unrealized_pl for pos in positions)
            if daily_pnl < -portfolio_value * TRADING_CONFIG.max_daily_loss:
                self.logger.warning("Daily loss limit exceeded - closing all positions")
                self.alpaca_client.close_all_positions()
                self.alpaca_client.cancel_all_orders()
                return
            
            # Check maximum drawdown
            if self.risk_manager.current_drawdown > TRADING_CONFIG.max_drawdown:
                self.logger.warning("Maximum drawdown exceeded - stopping trading")
                self.stop_trading_session()
                return
            
            # Check position concentration
            for position in positions:
                position_pct = abs(position.market_value) / portfolio_value
                if position_pct > TRADING_CONFIG.max_position_size * 1.5:  # 50% buffer
                    self.logger.warning(f"Position {position.symbol} too large: {position_pct:.2%}")
                    # Could implement partial closing logic here
            
        except Exception as e:
            self.logger.error(f"Error in risk management check: {e}")
    
    def get_performance_summary(self) -> Dict:
        """Get comprehensive performance summary"""
        if not self.current_session:
            return {}
        
        try:
            account = self.alpaca_client.get_account()
            positions = self.alpaca_client.get_positions()
            
            # Calculate metrics
            portfolio_value = account['portfolio_value']
            total_pnl = sum(pos.unrealized_pl for pos in positions)
            
            return {
                'session_id': self.current_session.session_id,
                'start_time': self.current_session.start_time,
                'portfolio_value': portfolio_value,
                'cash': account['cash'],
                'buying_power': account['buying_power'],
                'total_pnl': total_pnl,
                'daily_pnl': self.risk_manager.daily_pnl,
                'total_trades': self.current_session.total_trades,
                'profitable_trades': self.current_session.profitable_trades,
                'win_rate': self.current_session.profitable_trades / max(self.current_session.total_trades, 1),
                'current_drawdown': self.risk_manager.current_drawdown,
                'max_drawdown': self.current_session.max_drawdown,
                'var_95': self.risk_manager.var_95,
                'positions': len(positions),
                'strategies': self.strategy_manager.get_strategy_performance()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting performance summary: {e}")
            return {}

# Example usage
async def main():
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create trading engine
    engine = TradingEngine(TradingMode.PAPER)
    
    # Start trading session
    session_id = engine.start_trading_session()
    print(f"Started trading session: {session_id}")
    
    try:
        # Run for a short time (in production this would run continuously)
        await asyncio.wait_for(engine.run_trading_loop(), timeout=300)  # 5 minutes
        
    except asyncio.TimeoutError:
        print("Trading loop timed out")
    
    finally:
        # Stop trading session
        engine.stop_trading_session()
        
        # Print performance summary
        performance = engine.get_performance_summary()
        print("\nPerformance Summary:")
        for key, value in performance.items():
            if isinstance(value, float):
                if 'pnl' in key.lower():
                    print(f"{key}: ${value:.2f}")
                elif 'rate' in key.lower() or 'drawdown' in key.lower():
                    print(f"{key}: {value:.2%}")
                else:
                    print(f"{key}: {value:.2f}")
            else:
                print(f"{key}: {value}")

if __name__ == "__main__":
    asyncio.run(main())