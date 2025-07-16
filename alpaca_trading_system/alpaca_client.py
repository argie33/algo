"""
Enhanced Alpaca Client for Algorithmic Trading
Production-ready client with comprehensive error handling and monitoring
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
import json
import time
from enum import Enum

try:
    import alpaca_trade_api as tradeapi
    from alpaca_trade_api.rest import APIError, TimeFrame
    from alpaca_trade_api.common import URL
except ImportError:
    print("Installing alpaca-trade-api...")
    import subprocess
    subprocess.check_call(["pip", "install", "alpaca-trade-api"])
    import alpaca_trade_api as tradeapi
    from alpaca_trade_api.rest import APIError, TimeFrame
    from alpaca_trade_api.common import URL

from config import ALPACA_CONFIG, TRADING_CONFIG, MONITORING_CONFIG

class OrderStatus(Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    DONE_FOR_DAY = "done_for_day"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

@dataclass
class Position:
    """Position data structure"""
    symbol: str
    qty: float
    side: str
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_plpc: float
    current_price: float
    avg_entry_price: float
    
    @classmethod
    def from_alpaca(cls, position):
        """Create Position from Alpaca position object"""
        return cls(
            symbol=position.symbol,
            qty=float(position.qty),
            side=position.side,
            market_value=float(position.market_value),
            cost_basis=float(position.cost_basis),
            unrealized_pl=float(position.unrealized_pl),
            unrealized_plpc=float(position.unrealized_plpc),
            current_price=float(position.current_price),
            avg_entry_price=float(position.avg_entry_price)
        )

@dataclass
class Order:
    """Order data structure"""
    id: str
    symbol: str
    qty: float
    side: str
    order_type: str
    time_in_force: str
    status: str
    created_at: datetime
    filled_at: Optional[datetime] = None
    filled_qty: float = 0
    filled_avg_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    
    @classmethod
    def from_alpaca(cls, order):
        """Create Order from Alpaca order object"""
        return cls(
            id=order.id,
            symbol=order.symbol,
            qty=float(order.qty),
            side=order.side,
            order_type=order.order_type,
            time_in_force=order.time_in_force,
            status=order.status,
            created_at=pd.to_datetime(order.created_at),
            filled_at=pd.to_datetime(order.filled_at) if order.filled_at else None,
            filled_qty=float(order.filled_qty or 0),
            filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            limit_price=float(order.limit_price) if order.limit_price else None,
            stop_price=float(order.stop_price) if order.stop_price else None
        )

class AlpacaClient:
    """Enhanced Alpaca client with comprehensive trading capabilities"""
    
    def __init__(self, config=None):
        self.config = config or ALPACA_CONFIG
        self.logger = logging.getLogger(__name__)
        
        # Initialize Alpaca API
        self.api = tradeapi.REST(
            self.config.api_key,
            self.config.api_secret,
            self.config.base_url,
            api_version='v2'
        )
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
        self.request_count = 0
        self.daily_request_limit = 200 * 60 * 24  # 200 requests per minute
        
        # Cache for market data
        self.price_cache = {}
        self.cache_expiry = 60  # 1 minute cache
        
        # Initialize connection
        self._validate_connection()
    
    def _validate_connection(self):
        """Validate API connection and credentials"""
        try:
            account = self.api.get_account()
            self.logger.info(f"Connected to Alpaca {self.config.environment.value} account")
            self.logger.info(f"Account status: {account.status}")
            self.logger.info(f"Buying power: ${float(account.buying_power):,.2f}")
            self.logger.info(f"Portfolio value: ${float(account.portfolio_value):,.2f}")
            
            # Check if account is restricted
            if account.trading_blocked:
                raise Exception("Trading is blocked on this account")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Alpaca: {e}")
            raise
    
    def _rate_limit(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.request_count += 1
        
        if self.request_count > self.daily_request_limit:
            self.logger.warning("Daily request limit reached")
    
    def get_account(self) -> Dict:
        """Get account information"""
        self._rate_limit()
        try:
            account = self.api.get_account()
            return {
                'id': account.id,
                'status': account.status,
                'currency': account.currency,
                'buying_power': float(account.buying_power),
                'regt_buying_power': float(account.regt_buying_power),
                'daytrading_buying_power': float(account.daytrading_buying_power),
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'equity': float(account.equity),
                'last_equity': float(account.last_equity),
                'multiplier': int(account.multiplier),
                'initial_margin': float(account.initial_margin),
                'maintenance_margin': float(account.maintenance_margin),
                'sma': float(account.sma),
                'daytrade_count': int(account.daytrade_count),
                'trading_blocked': account.trading_blocked,
                'transfers_blocked': account.transfers_blocked,
                'account_blocked': account.account_blocked,
                'created_at': pd.to_datetime(account.created_at),
                'pattern_day_trader': account.pattern_day_trader,
                'crypto_status': account.crypto_status
            }
        except Exception as e:
            self.logger.error(f"Error getting account: {e}")
            raise
    
    def get_positions(self) -> List[Position]:
        """Get all positions"""
        self._rate_limit()
        try:
            positions = self.api.list_positions()
            return [Position.from_alpaca(pos) for pos in positions]
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol"""
        self._rate_limit()
        try:
            position = self.api.get_position(symbol)
            return Position.from_alpaca(position)
        except APIError as e:
            if "position does not exist" in str(e).lower():
                return None
            self.logger.error(f"Error getting position for {symbol}: {e}")
            raise
    
    def get_orders(self, status: str = "all", limit: int = 100) -> List[Order]:
        """Get orders"""
        self._rate_limit()
        try:
            orders = self.api.list_orders(status=status, limit=limit, nested=True)
            return [Order.from_alpaca(order) for order in orders]
        except Exception as e:
            self.logger.error(f"Error getting orders: {e}")
            return []
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get specific order"""
        self._rate_limit()
        try:
            order = self.api.get_order(order_id)
            return Order.from_alpaca(order)
        except Exception as e:
            self.logger.error(f"Error getting order {order_id}: {e}")
            return None
    
    def place_order(self, 
                   symbol: str,
                   qty: float,
                   side: str,
                   order_type: str = "market",
                   time_in_force: str = "day",
                   limit_price: Optional[float] = None,
                   stop_price: Optional[float] = None,
                   trail_price: Optional[float] = None,
                   trail_percent: Optional[float] = None) -> Optional[Order]:
        """Place an order"""
        self._rate_limit()
        
        # Validate inputs
        if side not in ["buy", "sell"]:
            raise ValueError(f"Invalid side: {side}")
        
        if order_type not in ["market", "limit", "stop", "stop_limit", "trailing_stop"]:
            raise ValueError(f"Invalid order type: {order_type}")
        
        # Check position size limits
        account = self.get_account()
        order_value = qty * self.get_current_price(symbol)
        
        if order_value > account['buying_power']:
            raise ValueError(f"Insufficient buying power: ${order_value:,.2f} > ${account['buying_power']:,.2f}")
        
        position_pct = order_value / account['portfolio_value']
        if position_pct > TRADING_CONFIG.max_position_size:
            raise ValueError(f"Position too large: {position_pct:.2%} > {TRADING_CONFIG.max_position_size:.2%}")
        
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=order_type,
                time_in_force=time_in_force,
                limit_price=limit_price,
                stop_price=stop_price,
                trail_price=trail_price,
                trail_percent=trail_percent
            )
            
            result = Order.from_alpaca(order)
            self.logger.info(f"Order placed: {side} {qty} {symbol} at {order_type}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            raise
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        self._rate_limit()
        try:
            self.api.cancel_order(order_id)
            self.logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """Cancel all orders"""
        self._rate_limit()
        try:
            self.api.cancel_all_orders()
            self.logger.info("All orders cancelled")
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling all orders: {e}")
            return False
    
    def get_current_price(self, symbol: str) -> float:
        """Get current price for symbol with caching"""
        current_time = time.time()
        
        # Check cache
        if symbol in self.price_cache:
            cached_price, cached_time = self.price_cache[symbol]
            if current_time - cached_time < self.cache_expiry:
                return cached_price
        
        self._rate_limit()
        try:
            # Get latest trade
            trade = self.api.get_latest_trade(symbol)
            price = float(trade.price)
            
            # Update cache
            self.price_cache[symbol] = (price, current_time)
            return price
            
        except Exception as e:
            self.logger.error(f"Error getting current price for {symbol}: {e}")
            
            # Fallback to bars
            try:
                bars = self.api.get_bars(symbol, TimeFrame.Minute, limit=1)
                if bars:
                    price = float(bars[0].c)
                    self.price_cache[symbol] = (price, current_time)
                    return price
            except Exception as e2:
                self.logger.error(f"Error getting bars for {symbol}: {e2}")
                raise
    
    def get_historical_data(self, 
                          symbol: str,
                          timeframe: str = "1Day",
                          start: Optional[datetime] = None,
                          end: Optional[datetime] = None,
                          limit: int = 1000) -> pd.DataFrame:
        """Get historical price data"""
        self._rate_limit()
        
        # Default to 1 year of data
        if not start:
            start = datetime.now() - timedelta(days=365)
        if not end:
            end = datetime.now()
        
        try:
            # Map timeframe strings to TimeFrame enum
            timeframe_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, "Min"),
                "15Min": TimeFrame(15, "Min"),
                "1Hour": TimeFrame.Hour,
                "1Day": TimeFrame.Day,
                "1Week": TimeFrame.Week,
                "1Month": TimeFrame.Month
            }
            
            tf = timeframe_map.get(timeframe, TimeFrame.Day)
            
            bars = self.api.get_bars(
                symbol,
                tf,
                start=start,
                end=end,
                limit=limit
            ).df
            
            if bars.empty:
                return pd.DataFrame()
            
            # Standardize column names
            bars.columns = ['open', 'high', 'low', 'close', 'volume', 'trade_count', 'vwap']
            
            # Add calculated fields
            bars['returns'] = bars['close'].pct_change()
            bars['hl_pct'] = (bars['high'] - bars['low']) / bars['close']
            bars['volume_ma'] = bars['volume'].rolling(20).mean()
            bars['volume_ratio'] = bars['volume'] / bars['volume_ma']
            
            return bars
            
        except Exception as e:
            self.logger.error(f"Error getting historical data for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_portfolio_performance(self) -> Dict:
        """Get portfolio performance metrics"""
        try:
            account = self.get_account()
            positions = self.get_positions()
            
            # Calculate portfolio metrics
            total_value = account['portfolio_value']
            total_pl = sum(pos.unrealized_pl for pos in positions)
            total_pl_pct = total_pl / (total_value - total_pl) if total_value > total_pl else 0
            
            # Position breakdown
            long_value = sum(pos.market_value for pos in positions if pos.side == 'long')
            short_value = sum(abs(pos.market_value) for pos in positions if pos.side == 'short')
            
            # Sector allocation (simplified)
            sector_allocation = {}
            for pos in positions:
                # This would need a sector mapping in production
                sector = "Unknown"
                if pos.symbol in ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "NFLX"]:
                    sector = "Technology"
                elif pos.symbol in ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "AXP"]:
                    sector = "Financials"
                
                sector_allocation[sector] = sector_allocation.get(sector, 0) + abs(pos.market_value)
            
            return {
                'timestamp': datetime.now(),
                'total_value': total_value,
                'cash': account['cash'],
                'buying_power': account['buying_power'],
                'total_pl': total_pl,
                'total_pl_pct': total_pl_pct,
                'long_value': long_value,
                'short_value': short_value,
                'net_exposure': long_value - short_value,
                'gross_exposure': long_value + short_value,
                'num_positions': len(positions),
                'sector_allocation': sector_allocation,
                'positions': [asdict(pos) for pos in positions]
            }
            
        except Exception as e:
            self.logger.error(f"Error getting portfolio performance: {e}")
            return {}
    
    def is_market_open(self) -> bool:
        """Check if market is open"""
        try:
            clock = self.api.get_clock()
            return clock.is_open
        except Exception as e:
            self.logger.error(f"Error checking market status: {e}")
            return False
    
    def get_market_calendar(self, start: datetime, end: datetime) -> List[Dict]:
        """Get market calendar"""
        try:
            calendar = self.api.get_calendar(start=start, end=end)
            return [
                {
                    'date': day.date,
                    'open': day.open,
                    'close': day.close,
                    'session_open': day.session_open,
                    'session_close': day.session_close
                }
                for day in calendar
            ]
        except Exception as e:
            self.logger.error(f"Error getting market calendar: {e}")
            return []
    
    def close_all_positions(self) -> bool:
        """Close all positions"""
        try:
            self.api.close_all_positions()
            self.logger.info("All positions closed")
            return True
        except Exception as e:
            self.logger.error(f"Error closing all positions: {e}")
            return False
    
    def close_position(self, symbol: str) -> bool:
        """Close specific position"""
        try:
            self.api.close_position(symbol)
            self.logger.info(f"Position {symbol} closed")
            return True
        except Exception as e:
            self.logger.error(f"Error closing position {symbol}: {e}")
            return False

# Example usage and testing
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize client
    client = AlpacaClient()
    
    # Test basic functionality
    print("=== Account Information ===")
    account = client.get_account()
    print(f"Status: {account['status']}")
    print(f"Buying Power: ${account['buying_power']:,.2f}")
    print(f"Portfolio Value: ${account['portfolio_value']:,.2f}")
    
    print("\n=== Market Status ===")
    print(f"Market Open: {client.is_market_open()}")
    
    print("\n=== Positions ===")
    positions = client.get_positions()
    for pos in positions:
        print(f"{pos.symbol}: {pos.qty} shares, P&L: ${pos.unrealized_pl:.2f}")
    
    print("\n=== Recent Orders ===")
    orders = client.get_orders(limit=5)
    for order in orders:
        print(f"{order.symbol}: {order.side} {order.qty} @ {order.order_type} - {order.status}")
    
    print("\n=== Portfolio Performance ===")
    performance = client.get_portfolio_performance()
    print(f"Total P&L: ${performance.get('total_pl', 0):.2f}")
    print(f"Total P&L %: {performance.get('total_pl_pct', 0):.2%}")
    
    # Test getting historical data
    print("\n=== Historical Data Test ===")
    data = client.get_historical_data("AAPL", limit=5)
    if not data.empty:
        print(f"AAPL data shape: {data.shape}")
        print(f"Latest close: ${data['close'].iloc[-1]:.2f}")
    
    print("\n=== Current Price Test ===")
    try:
        price = client.get_current_price("AAPL")
        print(f"AAPL current price: ${price:.2f}")
    except Exception as e:
        print(f"Error getting price: {e}")