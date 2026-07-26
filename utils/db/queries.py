#!/usr/bin/env python3
"""Consolidated database query utilities to eliminate 95+ duplicate query patterns.

Provides single-source-of-truth for common queries across algo_positions, algo_trades,
buy_sell_daily, stock_scores tables. Reduces duplication, improves maintainability,
enables query optimization at one point.
"""

from utils.db.context import DatabaseContext


class AlgoPositionsQueries:
    """Consolidated queries for algo_positions table."""

    @staticmethod
    def count_open_positions() -> int:
        """Get count of currently open positions."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
            return cur.fetchone()[0]

    @staticmethod
    def get_open_position_symbols() -> set[str]:
        """Get set of symbols in currently open positions."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT DISTINCT symbol FROM algo_positions WHERE status = 'open'")
            return {row[0] for row in cur.fetchall()}

    @staticmethod
    def get_position_count() -> int:
        """Get total count of positions (for inventory checks)."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM algo_positions")
            return cur.fetchone()[0]

    @staticmethod
    def get_total_position_value() -> float:
        """Get sum of all open position values."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COALESCE(SUM(position_value), 0) FROM algo_positions WHERE status = 'open'")
            result = cur.fetchone()[0]
            return float(result) if result else 0.0

    @staticmethod
    def get_position_symbols(status: str = "open") -> set[str]:
        """Get symbols for positions with given status."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT DISTINCT symbol FROM algo_positions WHERE status = %s", (status,))
            return {row[0] for row in cur.fetchall()}


class AlgoTradesQueries:
    """Consolidated queries for algo_trades table."""

    @staticmethod
    def get_trade_ids() -> list[str]:
        """Get list of all trade IDs."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT trade_id FROM algo_trades")
            return [row[0] for row in cur.fetchall()]

    @staticmethod
    def count_trades() -> int:
        """Get count of total trades."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM algo_trades")
            return cur.fetchone()[0]

    @staticmethod
    def get_trade_count_by_status(status: str) -> int:
        """Get count of trades with given status."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = %s", (status,))
            return cur.fetchone()[0]


class BuySellDailyQueries:
    """Consolidated queries for buy_sell_daily table."""

    @staticmethod
    def count_signals() -> int:
        """Get count of signals."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM buy_sell_daily")
            return cur.fetchone()[0]

    @staticmethod
    def get_latest_date() -> str | None:
        """Get most recent date in buy_sell_daily."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT MAX(date) FROM buy_sell_daily")
            result = cur.fetchone()[0]
            return str(result) if result else None

    @staticmethod
    def get_buy_signals_count_for_date(date_: str) -> int:
        """Get count of BUY signals for a specific date."""
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal_type = 'BUY'",
                (date_,),
            )
            return cur.fetchone()[0]


class StockScoresQueries:
    """Consolidated queries for stock_scores table."""

    @staticmethod
    def get_latest_update_time() -> str | None:
        """Get most recent update timestamp."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT MAX(updated_at) FROM stock_scores")
            result = cur.fetchone()[0]
            return str(result) if result else None

    @staticmethod
    def get_scores_for_symbols(symbols: list[str]) -> dict[str, float]:
        """Get composite scores for given symbols."""
        if not symbols:
            return {}
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT symbol, composite_score FROM stock_scores WHERE symbol = ANY(%s)",
                (symbols,),
            )
            return {row[0]: float(row[1]) for row in cur.fetchall() if row[1] is not None}
