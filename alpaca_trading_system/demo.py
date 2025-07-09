#!/usr/bin/env python3
"""
Alpaca Trading System Demo
Demonstrates the trading system with simulated data
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from strategies.momentum_strategy import MomentumBreakoutStrategy
from strategies.base_strategy import StrategyManager

def generate_sample_data(symbol: str, days: int = 100, trend: str = 'bullish') -> pd.DataFrame:
    """Generate realistic sample market data"""
    
    # Start with base price
    if symbol == 'AAPL':
        start_price = 150
    elif symbol == 'GOOGL':
        start_price = 2500
    elif symbol == 'MSFT':
        start_price = 300
    else:
        start_price = 100
    
    dates = pd.date_range(start=datetime.now() - timedelta(days=days), periods=days, freq='D')
    
    # Generate price data with trend
    np.random.seed(42)  # For reproducible results
    
    prices = [start_price]
    volumes = []
    
    for i in range(1, days):
        # Base volatility
        volatility = 0.02  # 2% daily volatility
        
        # Add trend
        if trend == 'bullish':
            drift = 0.0005  # Slight upward drift
        elif trend == 'bearish':
            drift = -0.0005  # Slight downward drift
        else:
            drift = 0.0  # No trend
        
        # Add some momentum patterns
        if i > 50 and i < 70:  # Create consolidation
            volatility *= 0.5
            drift *= 0.2
        elif i > 70:  # Create breakout
            if trend == 'bullish':
                drift *= 3
                volatility *= 1.5
        
        # Generate price change
        change = np.random.normal(drift, volatility)
        new_price = prices[-1] * (1 + change)
        prices.append(new_price)
        
        # Generate volume (higher volume during breakouts)
        base_volume = 1000000
        if i > 70:  # Breakout volume
            volume_multiplier = np.random.uniform(1.5, 3.0)
        else:
            volume_multiplier = np.random.uniform(0.8, 1.2)
        
        volume = int(base_volume * volume_multiplier)
        volumes.append(volume)
    
    # Create OHLC data
    data = []
    for i, (date, close) in enumerate(zip(dates, prices)):
        if i == 0:
            continue
            
        # Generate OHLC from close price
        open_price = prices[i-1] * np.random.uniform(0.995, 1.005)
        high_price = max(open_price, close) * np.random.uniform(1.0, 1.015)
        low_price = min(open_price, close) * np.random.uniform(0.985, 1.0)
        
        data.append({
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close,
            'volume': volumes[i-1]
        })
    
    return pd.DataFrame(data, index=dates[1:])

def demo_strategy_signals():
    """Demonstrate strategy signal generation"""
    print("🎯 Demo: Strategy Signal Generation")
    print("=" * 50)
    
    # Create momentum strategy
    strategy = MomentumBreakoutStrategy()
    
    # Generate sample data for multiple symbols
    sample_data = {}
    symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA']
    
    for symbol in symbols:
        # Generate bullish data to trigger breakout signals
        df = generate_sample_data(symbol, days=100, trend='bullish')
        sample_data[symbol] = df
        print(f"✓ Generated {len(df)} days of data for {symbol}")
    
    # Generate signals
    signals = strategy.generate_signals(sample_data)
    
    print(f"\n📊 Generated {len(signals)} signals:")
    print("-" * 80)
    
    for signal in signals:
        print(f"Symbol: {signal.symbol}")
        print(f"  Signal: {signal.signal_type.value.upper()}")
        print(f"  Strength: {signal.strength:.3f}")
        print(f"  Confidence: {signal.confidence:.3f}")
        print(f"  Price: ${signal.price:.2f}")
        print(f"  Target: ${signal.target_price:.2f}")
        print(f"  Stop Loss: ${signal.stop_loss:.2f}")
        print(f"  R/R Ratio: {(signal.target_price - signal.price) / (signal.price - signal.stop_loss):.2f}")
        print(f"  Metadata: {json.dumps(signal.metadata, indent=2)}")
        print("-" * 80)
    
    # Strategy performance
    print(f"\n📈 Strategy Performance:")
    state = strategy.get_strategy_state()
    print(f"  Total Signals: {state['metrics']['total_signals']}")
    print(f"  Configuration: {json.dumps(state['config'], indent=2)}")
    
    return signals

def demo_strategy_manager():
    """Demonstrate strategy manager with multiple strategies"""
    print("\n🎯 Demo: Strategy Manager")
    print("=" * 50)
    
    # Create strategy manager
    manager = StrategyManager()
    
    # Add momentum strategy
    momentum_strategy = MomentumBreakoutStrategy()
    manager.add_strategy(momentum_strategy, weight=0.6)
    
    # Could add more strategies here
    print(f"✓ Added {len(manager.strategies)} strategies")
    
    # Generate sample data
    sample_data = {
        'AAPL': generate_sample_data('AAPL', days=100, trend='bullish'),
        'GOOGL': generate_sample_data('GOOGL', days=100, trend='bullish'),
    }
    
    # Get signals from all strategies
    all_signals = manager.get_all_signals(sample_data)
    
    # Aggregate signals
    aggregated_signals = manager.aggregate_signals(all_signals)
    
    print(f"📊 Raw signals: {len(all_signals)}")
    print(f"📊 Aggregated signals: {len(aggregated_signals)}")
    
    # Show strategy performance
    performance = manager.get_strategy_performance()
    print(f"\n📈 Strategy Performance:")
    for name, perf in performance.items():
        print(f"  {name}:")
        print(f"    Weight: {perf['weight']:.2f}")
        print(f"    Active: {perf['state']['is_active']}")
        print(f"    Signals: {perf['state']['signals_count']}")
    
    return aggregated_signals

def demo_risk_management():
    """Demonstrate risk management features"""
    print("\n🎯 Demo: Risk Management")
    print("=" * 50)
    
    # Import here to avoid circular imports
    from trading_engine import RiskManager
    
    # Create risk manager
    risk_manager = RiskManager()
    
    # Demo portfolio
    portfolio_value = 100000  # $100K portfolio
    
    # Create sample signal
    from strategies.base_strategy import Signal, SignalType
    
    signal = Signal(
        symbol='AAPL',
        signal_type=SignalType.BUY,
        strength=0.8,
        confidence=0.7,
        timestamp=datetime.now(),
        price=150.0,
        target_price=159.0,
        stop_loss=147.0
    )
    
    # Create sample positions
    from alpaca_client import Position
    
    # Mock position data
    class MockPosition:
        def __init__(self, symbol, qty, side, market_value, unrealized_pl, unrealized_plpc):
            self.symbol = symbol
            self.qty = qty
            self.side = side
            self.market_value = market_value
            self.unrealized_pl = unrealized_pl
            self.unrealized_plpc = unrealized_plpc
    
    positions = [
        MockPosition('MSFT', 100, 'long', 30000, 500, 0.017),
        MockPosition('GOOGL', 10, 'long', 25000, -200, -0.008),
    ]
    
    # Test risk checks
    print("🛡️ Risk Management Tests:")
    
    # 1. Pre-trade risk check
    risk_ok, risk_msg = risk_manager.check_pre_trade_risk(signal, portfolio_value, positions)
    print(f"  Pre-trade risk check: {'✓ PASS' if risk_ok else '✗ FAIL'}")
    print(f"  Message: {risk_msg}")
    
    # 2. Position sizing
    position_size = risk_manager.calculate_position_size(signal, portfolio_value)
    print(f"  Recommended position size: {position_size:.2f} shares")
    print(f"  Position value: ${position_size * signal.price:,.2f}")
    print(f"  Portfolio allocation: {(position_size * signal.price) / portfolio_value:.2%}")
    
    # 3. Portfolio risk calculation
    portfolio_risk = risk_manager.calculate_portfolio_risk(signal, positions, portfolio_value)
    print(f"  Portfolio risk: {portfolio_risk:.2%}")
    
    # 4. Update risk metrics
    risk_manager.update_risk_metrics(portfolio_value, positions)
    print(f"  Current drawdown: {risk_manager.current_drawdown:.2%}")
    print(f"  Daily P&L: ${risk_manager.daily_pnl:.2f}")
    
    return risk_manager

def demo_data_analysis():
    """Demonstrate data analysis capabilities"""
    print("\n🎯 Demo: Data Analysis")
    print("=" * 50)
    
    # Generate sample data
    df = generate_sample_data('AAPL', days=100, trend='bullish')
    
    # Create strategy to preprocess data
    strategy = MomentumBreakoutStrategy()
    processed_df = strategy.preprocess_data(df)
    
    print(f"📊 Data Analysis for AAPL:")
    print(f"  Data points: {len(processed_df)}")
    print(f"  Date range: {processed_df.index[0].strftime('%Y-%m-%d')} to {processed_df.index[-1].strftime('%Y-%m-%d')}")
    
    # Calculate statistics
    latest = processed_df.iloc[-1]
    
    print(f"\n📈 Latest Market Data:")
    print(f"  Close Price: ${latest['close']:.2f}")
    print(f"  Volume: {latest['volume']:,}")
    print(f"  Daily Return: {latest['returns']:.2%}")
    print(f"  Volatility (20d): {latest['volatility']:.2%}")
    
    print(f"\n📊 Technical Indicators:")
    print(f"  RSI: {latest['rsi']:.2f}")
    print(f"  MACD: {latest['macd']:.4f}")
    print(f"  MACD Signal: {latest['macd_signal']:.4f}")
    print(f"  SMA 20: ${latest['sma_20']:.2f}")
    print(f"  SMA 50: ${latest['sma_50']:.2f}")
    
    print(f"\n📈 Volume Analysis:")
    print(f"  Volume Ratio: {latest['volume_ratio']:.2f}")
    print(f"  Volume MA: {latest['volume_ma']:.0f}")
    
    # Show last 5 days of data
    print(f"\n📅 Last 5 Days:")
    print(processed_df[['close', 'volume', 'returns', 'rsi', 'volume_ratio']].tail().round(4))
    
    return processed_df

def demo_backtesting():
    """Demonstrate simple backtesting"""
    print("\n🎯 Demo: Simple Backtesting")
    print("=" * 50)
    
    # Generate historical data
    df = generate_sample_data('AAPL', days=200, trend='bullish')
    
    # Create strategy
    strategy = MomentumBreakoutStrategy()
    
    # Simple backtesting loop
    signals = []
    trades = []
    
    # Split data into training and testing
    train_size = int(len(df) * 0.8)
    train_data = df.iloc[:train_size]
    test_data = df.iloc[train_size:]
    
    print(f"📊 Backtesting Setup:")
    print(f"  Total data points: {len(df)}")
    print(f"  Training period: {train_size} days")
    print(f"  Testing period: {len(test_data)} days")
    
    # Run strategy on test data
    for i in range(50, len(test_data)):  # Need sufficient lookback
        window_data = test_data.iloc[i-50:i+1]
        
        # Generate signals
        test_signals = strategy.generate_signals({'AAPL': window_data})
        
        if test_signals:
            signal = test_signals[0]
            signals.append(signal)
            
            # Simulate trade execution
            entry_price = signal.price
            exit_price = signal.target_price if np.random.random() > 0.3 else signal.stop_loss
            
            trade_return = (exit_price - entry_price) / entry_price
            trades.append({
                'date': window_data.index[-1],
                'symbol': signal.symbol,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'return': trade_return,
                'profit': trade_return > 0
            })
    
    # Calculate performance metrics
    if trades:
        total_return = sum(trade['return'] for trade in trades)
        profitable_trades = sum(1 for trade in trades if trade['profit'])
        win_rate = profitable_trades / len(trades)
        avg_return = total_return / len(trades)
        
        print(f"\n📈 Backtesting Results:")
        print(f"  Total signals: {len(signals)}")
        print(f"  Total trades: {len(trades)}")
        print(f"  Win rate: {win_rate:.2%}")
        print(f"  Average return: {avg_return:.2%}")
        print(f"  Total return: {total_return:.2%}")
        
        # Show recent trades
        print(f"\n📊 Recent Trades:")
        for trade in trades[-5:]:
            profit_status = "✓" if trade['profit'] else "✗"
            print(f"  {profit_status} {trade['date'].strftime('%Y-%m-%d')}: "
                  f"${trade['entry_price']:.2f} → ${trade['exit_price']:.2f} "
                  f"({trade['return']:+.2%})")
    
    return trades

async def main():
    """Main demo function"""
    print("🚀 Alpaca Trading System Demo")
    print("=" * 60)
    print("This demo showcases the trading system capabilities using simulated data.")
    print("In production, this would connect to real Alpaca API and market data.")
    print("")
    
    # Run demos
    signals = demo_strategy_signals()
    
    aggregated_signals = demo_strategy_manager()
    
    risk_manager = demo_risk_management()
    
    processed_data = demo_data_analysis()
    
    trades = demo_backtesting()
    
    print(f"\n🎉 Demo Complete!")
    print("=" * 60)
    print("Next steps:")
    print("1. Set up your Alpaca API keys in .env file")
    print("2. Run 'python validate_config.py' to test configuration")
    print("3. Run 'python start_trading.py' to start paper trading")
    print("4. Monitor performance with 'python monitor.py'")
    print("\nRemember: Always test with paper trading first!")

if __name__ == "__main__":
    asyncio.run(main())