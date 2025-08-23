#!/usr/bin/env python3
"""
Advanced Portfolio Management System
Optimization tools, attribution analysis, and risk management
Based on modern portfolio theory and institutional practices
"""

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats
from scipy.optimize import minimize

warnings.filterwarnings("ignore")


@dataclass
class Position:
    symbol: str
    shares: float
    avg_cost: float
    current_price: float
    market_value: float
    weight: float
    unrealized_pnl: float
    realized_pnl: float
    sector: str

    @property
    def total_return(self) -> float:
        return (self.current_price - self.avg_cost) / self.avg_cost


@dataclass
class PortfolioMetrics:
    total_value: float
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    var_95: float  # Value at Risk 95%
    beta: float
    alpha: float
    tracking_error: float
    information_ratio: float


@dataclass
class AttributionResult:
    asset_allocation: Dict[str, float]
    security_selection: Dict[str, float]
    interaction: Dict[str, float]
    total_excess_return: float
    benchmark_return: float
    portfolio_return: float


class Portfolio:
    """
    Advanced Portfolio Management Class
    Handles position tracking, optimization, and performance analysis
    """

    def __init__(self, cash: float = 100000.0, benchmark: str = "SPY"):
        self.cash = cash
        self.initial_value = cash
        self.positions: Dict[str, Position] = {}
        self.transactions: List[Dict] = []
        self.benchmark = benchmark
        self.creation_date = datetime.now()

        # Performance tracking
        self.historical_values: List[Tuple[datetime, float]] = [(datetime.now(), cash)]
        self.daily_returns: List[float] = []
        self.benchmark_returns: List[float] = []

    def add_position(
        self,
        symbol: str,
        shares: float,
        price: float,
        transaction_date: Optional[datetime] = None,
    ) -> bool:
        """Add or update a position in the portfolio"""
        try:
            if transaction_date is None:
                transaction_date = datetime.now()

            cost = shares * price

            # Check if enough cash
            if cost > self.cash:
                return False

            # Get current price and sector info
            ticker = yf.Ticker(symbol)
            current_price = self._get_current_price(symbol)
            sector = self._get_sector(ticker)

            if symbol in self.positions:
                # Update existing position
                existing = self.positions[symbol]
                total_shares = existing.shares + shares
                total_cost = (existing.shares * existing.avg_cost) + cost
                new_avg_cost = total_cost / total_shares if total_shares > 0 else 0

                self.positions[symbol] = Position(
                    symbol=symbol,
                    shares=total_shares,
                    avg_cost=new_avg_cost,
                    current_price=current_price,
                    market_value=total_shares * current_price,
                    weight=0.0,  # Will be calculated later
                    unrealized_pnl=(current_price - new_avg_cost) * total_shares,
                    realized_pnl=existing.realized_pnl,
                    sector=sector,
                )
            else:
                # New position
                self.positions[symbol] = Position(
                    symbol=symbol,
                    shares=shares,
                    avg_cost=price,
                    current_price=current_price,
                    market_value=shares * current_price,
                    weight=0.0,
                    unrealized_pnl=(current_price - price) * shares,
                    realized_pnl=0.0,
                    sector=sector,
                )

            # Update cash
            self.cash -= cost

            # Record transaction
            self.transactions.append(
                {
                    "date": transaction_date,
                    "symbol": symbol,
                    "action": "BUY",
                    "shares": shares,
                    "price": price,
                    "value": cost,
                }
            )

            # Update portfolio weights
            self._update_weights()

            return True

        except Exception as e:
            print(f"Error adding position {symbol}: {e}")
            return False

    def remove_position(
        self,
        symbol: str,
        shares: float,
        price: float,
        transaction_date: Optional[datetime] = None,
    ) -> bool:
        """Remove shares from a position"""
        try:
            if symbol not in self.positions:
                return False

            if transaction_date is None:
                transaction_date = datetime.now()

            position = self.positions[symbol]

            if shares > position.shares:
                return False  # Can't sell more than owned

            # Calculate realized P&L
            realized_pnl = (price - position.avg_cost) * shares

            # Update position
            remaining_shares = position.shares - shares

            if remaining_shares > 0:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    shares=remaining_shares,
                    avg_cost=position.avg_cost,
                    current_price=self._get_current_price(symbol),
                    market_value=remaining_shares * self._get_current_price(symbol),
                    weight=0.0,
                    unrealized_pnl=(self._get_current_price(symbol) - position.avg_cost)
                    * remaining_shares,
                    realized_pnl=position.realized_pnl + realized_pnl,
                    sector=position.sector,
                )
            else:
                # Position closed
                del self.positions[symbol]

            # Update cash
            self.cash += shares * price

            # Record transaction
            self.transactions.append(
                {
                    "date": transaction_date,
                    "symbol": symbol,
                    "action": "SELL",
                    "shares": shares,
                    "price": price,
                    "value": shares * price,
                    "realized_pnl": realized_pnl,
                }
            )

            # Update weights
            self._update_weights()

            return True

        except Exception as e:
            print(f"Error removing position {symbol}: {e}")
            return False

    def get_portfolio_value(self) -> float:
        """Calculate current portfolio value"""
        total_value = self.cash

        for position in self.positions.values():
            total_value += position.market_value

        return total_value

    def get_portfolio_metrics(self) -> PortfolioMetrics:
        """Calculate comprehensive portfolio metrics"""
        try:
            current_value = self.get_portfolio_value()

            # Update historical values and returns
            self._update_performance_data()

            if len(self.daily_returns) < 2:
                # Insufficient data for calculations
                return PortfolioMetrics(
                    total_value=current_value,
                    total_return=0.0,
                    annualized_return=0.0,
                    volatility=0.0,
                    sharpe_ratio=0.0,
                    max_drawdown=0.0,
                    var_95=0.0,
                    beta=0.0,
                    alpha=0.0,
                    tracking_error=0.0,
                    information_ratio=0.0,
                )

            returns = np.array(self.daily_returns)
            benchmark_returns = np.array(self.benchmark_returns)

            # Basic metrics
            total_return = (current_value - self.initial_value) / self.initial_value
            mean_return = np.mean(returns)
            volatility = np.std(returns) * np.sqrt(252)  # Annualized
            annualized_return = mean_return * 252

            # Risk-free rate (approximate)
            risk_free_rate = 0.02  # 2% assumption

            # Sharpe ratio
            excess_returns = returns - (risk_free_rate / 252)
            sharpe_ratio = (
                np.mean(excess_returns) / np.std(returns) * np.sqrt(252)
                if np.std(returns) > 0
                else 0
            )

            # Maximum drawdown
            max_drawdown = self._calculate_max_drawdown()

            # Value at Risk (95%)
            var_95 = np.percentile(returns, 5) * current_value

            # Beta and Alpha vs benchmark
            if len(benchmark_returns) == len(returns) and len(returns) > 1:
                beta, alpha = self._calculate_beta_alpha(
                    returns, benchmark_returns, risk_free_rate
                )
                tracking_error = np.std(returns - benchmark_returns) * np.sqrt(252)
                information_ratio = (
                    (mean_return - np.mean(benchmark_returns))
                    / np.std(returns - benchmark_returns)
                    * np.sqrt(252)
                    if np.std(returns - benchmark_returns) > 0
                    else 0
                )
            else:
                beta = alpha = tracking_error = information_ratio = 0.0

            return PortfolioMetrics(
                total_value=current_value,
                total_return=total_return,
                annualized_return=annualized_return,
                volatility=volatility,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                var_95=var_95,
                beta=beta,
                alpha=alpha,
                tracking_error=tracking_error,
                information_ratio=information_ratio,
            )

        except Exception as e:
            print(f"Error calculating portfolio metrics: {e}")
            return PortfolioMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    def optimize_portfolio(
        self,
        expected_returns: Dict[str, float],
        covariance_matrix: pd.DataFrame,
        risk_aversion: float = 1.0,
    ) -> Dict[str, float]:
        """
        Optimize portfolio weights using Modern Portfolio Theory

        Args:
            expected_returns: Expected returns for each asset
            covariance_matrix: Covariance matrix of returns
            risk_aversion: Risk aversion parameter (higher = more conservative)

        Returns:
            Optimal weights for each asset
        """
        try:
            symbols = list(expected_returns.keys())
            n_assets = len(symbols)

            if n_assets == 0:
                return {}

            # Convert to numpy arrays
            mu = np.array([expected_returns[symbol] for symbol in symbols])
            sigma = covariance_matrix.loc[symbols, symbols].values

            # Objective function: minimize -utility = -expected_return + 0.5 * risk_aversion * variance
            def objective(weights):
                portfolio_return = np.dot(weights, mu)
                portfolio_variance = np.dot(weights, np.dot(sigma, weights))
                return -portfolio_return + 0.5 * risk_aversion * portfolio_variance

            # Constraints
            constraints = [
                {"type": "eq", "fun": lambda x: np.sum(x) - 1.0},  # Weights sum to 1
            ]

            # Bounds (no short selling, max 25% in any single asset)
            bounds = [(0.0, 0.25) for _ in range(n_assets)]

            # Initial guess (equal weights)
            x0 = np.array([1.0 / n_assets] * n_assets)

            # Optimize
            result = minimize(
                objective, x0, method="SLSQP", bounds=bounds, constraints=constraints
            )

            if result.success:
                optimal_weights = dict(zip(symbols, result.x))
                # Filter out very small weights
                optimal_weights = {k: v for k, v in optimal_weights.items() if v > 0.01}
                return optimal_weights
            else:
                print("Optimization failed")
                return {}

        except Exception as e:
            print(f"Error in portfolio optimization: {e}")
            return {}

    def performance_attribution(
        self,
        benchmark_weights: Dict[str, float],
        start_date: datetime,
        end_date: datetime,
    ) -> AttributionResult:
        """
        Perform Brinson attribution analysis
        Decomposes excess return into allocation and selection effects
        """
        try:
            # Get portfolio and benchmark returns for the period
            portfolio_returns = self._get_period_returns(start_date, end_date)
            benchmark_returns = self._get_benchmark_returns(start_date, end_date)

            # Current portfolio weights
            current_weights = {
                pos.symbol: pos.weight for pos in self.positions.values()
            }

            # Initialize attribution components
            asset_allocation = {}
            security_selection = {}
            interaction = {}

            for symbol in set(
                list(current_weights.keys()) + list(benchmark_weights.keys())
            ):
                wp = current_weights.get(symbol, 0.0)  # Portfolio weight
                wb = benchmark_weights.get(symbol, 0.0)  # Benchmark weight
                rp = portfolio_returns.get(symbol, 0.0)  # Portfolio return
                rb = benchmark_returns.get(symbol, 0.0)  # Benchmark return

                # Asset allocation effect: (wp - wb) * rb
                asset_allocation[symbol] = (wp - wb) * rb

                # Security selection effect: wb * (rp - rb)
                security_selection[symbol] = wb * (rp - rb)

                # Interaction effect: (wp - wb) * (rp - rb)
                interaction[symbol] = (wp - wb) * (rp - rb)

            # Calculate total excess return
            portfolio_return = sum(
                current_weights.get(s, 0) * portfolio_returns.get(s, 0)
                for s in current_weights.keys()
            )
            benchmark_return = sum(
                benchmark_weights.get(s, 0) * benchmark_returns.get(s, 0)
                for s in benchmark_weights.keys()
            )

            total_excess_return = portfolio_return - benchmark_return

            return AttributionResult(
                asset_allocation=asset_allocation,
                security_selection=security_selection,
                interaction=interaction,
                total_excess_return=total_excess_return,
                benchmark_return=benchmark_return,
                portfolio_return=portfolio_return,
            )

        except Exception as e:
            print(f"Error in performance attribution: {e}")
            return AttributionResult({}, {}, {}, 0.0, 0.0, 0.0)

    def get_risk_metrics(self) -> Dict:
        """Calculate comprehensive risk metrics"""
        try:
            # Sector concentration risk
            sector_weights = {}
            for position in self.positions.values():
                sector = position.sector
                if sector not in sector_weights:
                    sector_weights[sector] = 0.0
                sector_weights[sector] += position.weight

            # Concentration risk (HHI)
            hhi = sum(w**2 for w in sector_weights.values())

            # Position concentration
            position_weights = [pos.weight for pos in self.positions.values()]
            max_position_weight = max(position_weights) if position_weights else 0

            # Diversification ratio
            individual_vol = self._calculate_individual_volatilities()
            portfolio_vol = self._calculate_portfolio_volatility()

            if portfolio_vol > 0 and individual_vol:
                diversification_ratio = (
                    sum(w * vol for w, vol in zip(position_weights, individual_vol))
                    / portfolio_vol
                )
            else:
                diversification_ratio = 1.0

            return {
                "sector_concentration": sector_weights,
                "herfindahl_index": hhi,
                "max_position_weight": max_position_weight,
                "diversification_ratio": diversification_ratio,
                "number_of_positions": len(self.positions),
                "cash_weight": self.cash / self.get_portfolio_value(),
            }

        except Exception as e:
            print(f"Error calculating risk metrics: {e}")
            return {}

    def rebalance_portfolio(self, target_weights: Dict[str, float]) -> List[Dict]:
        """
        Rebalance portfolio to target weights
        Returns list of suggested trades
        """
        try:
            current_value = self.get_portfolio_value()
            current_weights = {
                pos.symbol: pos.weight for pos in self.positions.values()
            }

            trades = []

            for symbol, target_weight in target_weights.items():
                current_weight = current_weights.get(symbol, 0.0)
                weight_diff = target_weight - current_weight

                if abs(weight_diff) > 0.01:  # Only rebalance if difference > 1%
                    target_value = target_weight * current_value
                    current_value_symbol = (
                        current_weights.get(symbol, 0.0) * current_value
                    )
                    trade_value = target_value - current_value_symbol

                    current_price = self._get_current_price(symbol)
                    shares_to_trade = trade_value / current_price

                    trades.append(
                        {
                            "symbol": symbol,
                            "action": "BUY" if shares_to_trade > 0 else "SELL",
                            "shares": abs(shares_to_trade),
                            "estimated_price": current_price,
                            "estimated_value": abs(trade_value),
                            "weight_change": weight_diff,
                        }
                    )

            return trades

        except Exception as e:
            print(f"Error in rebalancing: {e}")
            return []

    # Helper methods
    def _update_weights(self):
        """Update position weights based on current values"""
        total_value = self.get_portfolio_value()

        for position in self.positions.values():
            position.current_price = self._get_current_price(position.symbol)
            position.market_value = position.shares * position.current_price
            position.weight = (
                position.market_value / total_value if total_value > 0 else 0
            )
            position.unrealized_pnl = (
                position.current_price - position.avg_cost
            ) * position.shares

    def _get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")
            if not data.empty:
                return data["Close"].iloc[-1]
        except:
            pass
        return 100.0  # Fallback price

    def _get_sector(self, ticker) -> str:
        """Get sector for a ticker"""
        try:
            info = ticker.info
            return info.get("sector", "Unknown")
        except:
            return "Unknown"

    def _update_performance_data(self):
        """Update historical performance data"""
        current_value = self.get_portfolio_value()
        current_date = datetime.now()

        # Add current value to history
        self.historical_values.append((current_date, current_value))

        # Calculate daily return if we have previous data
        if len(self.historical_values) > 1:
            prev_value = self.historical_values[-2][1]
            daily_return = (current_value - prev_value) / prev_value
            self.daily_returns.append(daily_return)

        # Get benchmark return (simplified)
        try:
            spy = yf.Ticker(self.benchmark)
            spy_data = spy.history(period="2d")
            if len(spy_data) >= 2:
                benchmark_return = (
                    spy_data["Close"].iloc[-1] - spy_data["Close"].iloc[-2]
                ) / spy_data["Close"].iloc[-2]
                self.benchmark_returns.append(benchmark_return)
        except:
            self.benchmark_returns.append(0.0)

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown"""
        if len(self.historical_values) < 2:
            return 0.0

        values = [v[1] for v in self.historical_values]
        peak = values[0]
        max_dd = 0.0

        for value in values:
            if value > peak:
                peak = value

            drawdown = (peak - value) / peak
            if drawdown > max_dd:
                max_dd = drawdown

        return max_dd

    def _calculate_beta_alpha(
        self, returns: np.array, benchmark_returns: np.array, risk_free_rate: float
    ) -> Tuple[float, float]:
        """Calculate beta and alpha vs benchmark"""
        try:
            # Excess returns
            excess_returns = returns - risk_free_rate / 252
            excess_benchmark = benchmark_returns - risk_free_rate / 252

            # Beta calculation
            covariance = np.cov(excess_returns, excess_benchmark)[0, 1]
            benchmark_variance = np.var(excess_benchmark)

            beta = covariance / benchmark_variance if benchmark_variance > 0 else 0

            # Alpha calculation (Jensen's alpha)
            alpha = np.mean(excess_returns) - beta * np.mean(excess_benchmark)
            alpha *= 252  # Annualized

            return beta, alpha

        except:
            return 0.0, 0.0

    def _get_period_returns(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, float]:
        """Get returns for portfolio positions over a period"""
        returns = {}

        for symbol in self.positions.keys():
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.history(start=start_date, end=end_date)

                if len(data) >= 2:
                    period_return = (
                        data["Close"].iloc[-1] - data["Close"].iloc[0]
                    ) / data["Close"].iloc[0]
                    returns[symbol] = period_return
                else:
                    returns[symbol] = 0.0
            except:
                returns[symbol] = 0.0

        return returns

    def _get_benchmark_returns(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, float]:
        """Get benchmark returns for comparison (simplified)"""
        # Simplified - would normally use actual benchmark constituent returns
        returns = {}

        for symbol in self.positions.keys():
            # Mock benchmark return
            returns[symbol] = (
                0.08 / 252 * (end_date - start_date).days
            )  # 8% annual return assumption

        return returns

    def _calculate_individual_volatilities(self) -> List[float]:
        """Calculate individual asset volatilities"""
        volatilities = []

        for position in self.positions.values():
            try:
                ticker = yf.Ticker(position.symbol)
                data = ticker.history(period="1y")

                if len(data) > 20:
                    returns = data["Close"].pct_change().dropna()
                    vol = returns.std() * np.sqrt(252)
                    volatilities.append(vol)
                else:
                    volatilities.append(0.2)  # Default volatility
            except:
                volatilities.append(0.2)

        return volatilities

    def _calculate_portfolio_volatility(self) -> float:
        """Calculate portfolio volatility"""
        if len(self.daily_returns) > 1:
            return np.std(self.daily_returns) * np.sqrt(252)
        else:
            return 0.2  # Default


def main():
    """Example usage of portfolio management system"""
    print("Advanced Portfolio Management System")
    print("=" * 40)

    # Create portfolio
    portfolio = Portfolio(cash=100000.0)

    # Add some positions
    portfolio.add_position("AAPL", 100, 150.0)
    portfolio.add_position("MSFT", 80, 300.0)
    portfolio.add_position("GOOGL", 30, 2500.0)

    print(f"Portfolio Value: ${portfolio.get_portfolio_value():,.2f}")
    print(f"Cash: ${portfolio.cash:,.2f}")

    print("\nPositions:")
    for symbol, position in portfolio.positions.items():
        print(f"  {symbol}: {position.shares} shares @ ${position.avg_cost:.2f}")
        print(
            f"    Current: ${position.current_price:.2f}, Weight: {position.weight:.1%}"
        )
        print(f"    P&L: ${position.unrealized_pnl:,.2f}")

    # Get portfolio metrics
    metrics = portfolio.get_portfolio_metrics()
    print(f"\nPortfolio Metrics:")
    print(f"  Total Return: {metrics.total_return:.1%}")
    print(f"  Volatility: {metrics.volatility:.1%}")
    print(f"  Sharpe Ratio: {metrics.sharpe_ratio:.2f}")

    # Risk metrics
    risk_metrics = portfolio.get_risk_metrics()
    print(f"\nRisk Metrics:")
    print(f"  Number of Positions: {risk_metrics['number_of_positions']}")
    print(f"  Max Position Weight: {risk_metrics['max_position_weight']:.1%}")
    print(f"  Diversification Ratio: {risk_metrics['diversification_ratio']:.2f}")


if __name__ == "__main__":
    main()
