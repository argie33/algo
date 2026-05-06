#!/usr/bin/env python3
"""
Phase 9: Model Registry & Governance

Tracks model lifecycle:
- Model registry: version control, parameter snapshots, performance baselines
- Config audit log: all parameter changes with reason and approver
- Champion/challenger: A/B test improvements against current model
- Information coefficient: signal quality decay detection

Implements SR 11-7 light governance for trading strategies.
"""

import os
import psycopg2
import json
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date
from typing import Dict, Any, Optional

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class ModelRegistry:
    """Track model versions, parameters, and performance."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def register_model(
        self,
        strategy_name: str,
        param_snapshot: Dict[str, Any],
        backtest_sharpe: float,
        backtest_max_dd: float,
        backtest_win_rate: float,
        deployed_by: str = "system",
        notes: str = "",
    ) -> int:
        """
        Register a new model version.

        Args:
            strategy_name: Name of strategy (e.g., "swing_trader_v2")
            param_snapshot: Dict of all config params at deployment
            backtest_sharpe: Backtest Sharpe ratio
            backtest_max_dd: Backtest max drawdown
            backtest_win_rate: Backtest win rate
            deployed_by: Who deployed (user/system)
            notes: Deployment notes

        Returns:
            registry_id of new entry
        """
        self.connect()
        try:
            # Get current git commit
            try:
                git_commit = subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=Path(__file__).parent,
                    text=True,
                ).strip()[:40]
            except:
                git_commit = "unknown"

            self.cur.execute(
                """
                INSERT INTO algo_model_registry (
                    strategy_name, git_commit_hash, param_snapshot,
                    backtest_sharpe, backtest_max_dd, backtest_win_rate,
                    deployed_by, status, notes, deployed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING registry_id
                """,
                (
                    strategy_name,
                    git_commit,
                    json.dumps(param_snapshot),
                    backtest_sharpe,
                    backtest_max_dd,
                    backtest_win_rate,
                    deployed_by,
                    'active',
                    notes,
                )
            )
            registry_id = self.cur.fetchone()[0]
            self.conn.commit()

            print(f"[OK] Model registered: {strategy_name} (ID: {registry_id})")
            print(f"     Git Commit: {git_commit}")
            print(f"     Backtest Sharpe: {backtest_sharpe:.3f}")

            return registry_id

        finally:
            self.disconnect()

    def get_active_model(self) -> Optional[Dict[str, Any]]:
        """Get current active model."""
        self.connect()
        try:
            self.cur.execute("""
                SELECT registry_id, strategy_name, git_commit_hash, param_snapshot,
                       backtest_sharpe, deployed_at
                FROM algo_model_registry
                WHERE status = 'active'
                ORDER BY deployed_at DESC
                LIMIT 1
            """)
            row = self.cur.fetchone()

            if row:
                return {
                    'registry_id': row[0],
                    'strategy_name': row[1],
                    'git_commit': row[2],
                    'params': json.loads(row[3]),
                    'backtest_sharpe': row[4],
                    'deployed_at': row[5],
                }
            return None

        finally:
            self.disconnect()

    def retire_model(self, registry_id: int, reason: str = ""):
        """Retire a model (move to 'retired' status)."""
        self.connect()
        try:
            self.cur.execute(
                """
                UPDATE algo_model_registry
                SET status = 'retired'
                WHERE registry_id = %s
                """,
                (registry_id,)
            )
            self.conn.commit()
            print(f"[OK] Model {registry_id} retired")

        finally:
            self.disconnect()


class ConfigAuditLog:
    """Track all configuration parameter changes."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def log_change(
        self,
        config_key: str,
        old_value: str,
        new_value: str,
        changed_by: str,
        change_reason: str = "",
    ):
        """Log a parameter change."""
        self.connect()
        try:
            self.cur.execute(
                """
                INSERT INTO algo_config_audit (
                    config_key, old_value, new_value,
                    changed_by, change_reason, changed_at
                ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (config_key, old_value, new_value, changed_by, change_reason)
            )
            self.conn.commit()

        finally:
            self.disconnect()

    def get_change_history(self, config_key: str, limit: int = 10) -> list:
        """Get change history for a parameter."""
        self.connect()
        try:
            self.cur.execute(
                """
                SELECT old_value, new_value, changed_by, change_reason, changed_at
                FROM algo_config_audit
                WHERE config_key = %s
                ORDER BY changed_at DESC
                LIMIT %s
                """,
                (config_key, limit)
            )
            return self.cur.fetchall()

        finally:
            self.disconnect()


class ChampionChallengerTest:
    """A/B test challenger strategy against champion."""

    def __init__(self, champion_id: int):
        """
        Args:
            champion_id: Registry ID of champion model
        """
        self.champion_id = champion_id
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def log_test_result(
        self,
        challenger_id: int,
        champion_pnl: float,
        challenger_pnl: float,
        test_period_days: int,
        champion_trades: int,
        challenger_trades: int,
        p_value: float,
        recommendation: str,
    ):
        """Log champion/challenger test results."""
        self.connect()
        try:
            self.cur.execute(
                """
                INSERT INTO algo_champion_challenger (
                    champion_registry_id, challenger_registry_id,
                    test_period_days, champion_pnl, challenger_pnl,
                    champion_trades, challenger_trades,
                    statistical_p_value, recommendation, tested_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    self.champion_id,
                    challenger_id,
                    test_period_days,
                    champion_pnl,
                    challenger_pnl,
                    champion_trades,
                    challenger_trades,
                    p_value,
                    recommendation,
                )
            )
            self.conn.commit()

            # Print result
            print(f"\n[CHAMPION/CHALLENGER TEST]")
            print(f"  Champion (ID {self.champion_id}): ${champion_pnl:,.0f} ({champion_trades} trades)")
            print(f"  Challenger (ID {challenger_id}): ${challenger_pnl:,.0f} ({challenger_trades} trades)")
            print(f"  Statistical Significance: p={p_value:.3f}")
            print(f"  Recommendation: {recommendation}")

        finally:
            self.disconnect()


class InformationCoefficient:
    """Track information coefficient (signal quality decay)."""

    @staticmethod
    def calculate_ic(signal_scores: list, forward_returns: list) -> float:
        """
        Calculate information coefficient (Pearson correlation between
        signal scores and subsequent forward returns).

        IC > 0.05: Meaningful signal
        IC declining toward 0: Alpha decay
        IC < 0: Negative signal quality

        Args:
            signal_scores: List of signal quality scores (0-100)
            forward_returns: List of realized 5-day forward returns (%)

        Returns:
            Pearson correlation coefficient
        """
        if len(signal_scores) < 10:
            return 0.0

        import statistics

        # Compute Pearson correlation
        n = len(signal_scores)
        mean_signal = statistics.mean(signal_scores)
        mean_return = statistics.mean(forward_returns)

        cov = sum(
            (signal_scores[i] - mean_signal) * (forward_returns[i] - mean_return)
            for i in range(n)
        ) / n

        std_signal = statistics.stdev(signal_scores)
        std_return = statistics.stdev(forward_returns)

        if std_signal == 0 or std_return == 0:
            return 0.0

        return cov / (std_signal * std_return)

    @staticmethod
    def compute_rolling_ic(lookback_days: int = 60) -> Dict[str, float]:
        """
        Compute rolling information coefficient from trades.

        Args:
            lookback_days: Days to look back (default 60)

        Returns:
            Dict with ic_current, ic_previous, ic_decay_rate
        """
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        try:
            # Get recent closed trades with signal scores and returns
            cur.execute(
                """
                SELECT at.swing_score, at.profit_loss_pct
                FROM algo_trades at
                WHERE at.status = 'closed'
                  AND at.exit_date >= CURRENT_DATE - INTERVAL '%d days'
                ORDER BY at.exit_date DESC
                LIMIT 60
                """ % lookback_days
            )
            rows = cur.fetchall()

            if len(rows) < 10:
                return {
                    'ic_current': 0.0,
                    'ic_previous': 0.0,
                    'ic_decay_rate': 0.0,
                    'data_points': len(rows),
                }

            signal_scores = [row[0] if row[0] else 50 for row in rows]
            forward_returns = [row[1] if row[1] else 0 for row in rows]

            ic_current = InformationCoefficient.calculate_ic(signal_scores, forward_returns)

            # Previous period (60 days before that)
            cur.execute(
                """
                SELECT at.swing_score, at.profit_loss_pct
                FROM algo_trades at
                WHERE at.status = 'closed'
                  AND at.exit_date >= CURRENT_DATE - INTERVAL '%d days'
                  AND at.exit_date < CURRENT_DATE - INTERVAL '%d days'
                ORDER BY at.exit_date DESC
                LIMIT 60
                """ % (lookback_days * 2, lookback_days)
            )
            prev_rows = cur.fetchall()

            ic_previous = 0.0
            if len(prev_rows) > 10:
                prev_signal = [row[0] if row[0] else 50 for row in prev_rows]
                prev_returns = [row[1] if row[1] else 0 for row in prev_rows]
                ic_previous = InformationCoefficient.calculate_ic(prev_signal, prev_returns)

            ic_decay_rate = ic_previous - ic_current if ic_previous != 0 else 0

            return {
                'ic_current': round(ic_current, 4),
                'ic_previous': round(ic_previous, 4),
                'ic_decay_rate': round(ic_decay_rate, 4),
                'data_points': len(rows),
                'status': (
                    'HEALTHY' if ic_current > 0.05
                    else 'CAUTION' if ic_current > 0.0
                    else 'DECAY'
                ),
            }

        finally:
            cur.close()
            conn.close()


if __name__ == '__main__':
    print(f"\nModel Governance Tools:")
    print(f"  ModelRegistry: Track model versions and parameters")
    print(f"  ConfigAuditLog: Audit all parameter changes")
    print(f"  ChampionChallengerTest: A/B test improvements")
    print(f"  InformationCoefficient: Monitor signal decay\n")

    # Example: Calculate IC
    ic_result = InformationCoefficient.compute_rolling_ic()
    print(f"Current Information Coefficient:")
    for k, v in ic_result.items():
        print(f"  {k}: {v}")
