"""
Model Governance & Tracking

Manages model lifecycle: registration, parameter versioning, A/B testing, alpha decay.

Tracks:
- Model registry with git commit, parameters, and performance
- Config audit log of all parameter changes
- Champion/Challenger A/B test results
- Information Coefficient (signal quality decay detection)
"""

import psycopg2
import os
import json
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
from scipy import stats
import numpy as np

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


class ModelGovernance:
    """Track and manage model lifecycle and governance."""

    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"ModelGovernance: DB connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def register_model(self, strategy_name: str, git_commit: str, param_snapshot: Dict,
                     backtest_metrics: Dict, deployed_by: str, notes: str = '') -> int:
        """Register a new model deployment in the registry.

        Args:
            strategy_name: Name of strategy
            git_commit: Git commit hash
            param_snapshot: Current config parameters
            backtest_metrics: Backtest Sharpe, max_dd, win_rate, WFE
            deployed_by: User deploying the model
            notes: Optional deployment notes

        Returns:
            registry_id of the new model
        """
        try:
            self.connect()

            self.cur.execute(
                """
                INSERT INTO algo_model_registry (
                    strategy_name, git_commit_hash, param_snapshot,
                    backtest_sharpe, backtest_max_dd, backtest_win_rate,
                    walk_forward_efficiency,
                    deployed_at, deployed_by, status, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING registry_id
                """,
                (
                    strategy_name,
                    git_commit,
                    json.dumps(param_snapshot),
                    backtest_metrics.get('sharpe_ratio'),
                    backtest_metrics.get('max_drawdown_pct'),
                    backtest_metrics.get('win_rate_pct'),
                    backtest_metrics.get('wfe'),
                    datetime.now(),
                    deployed_by,
                    'active',
                    notes,
                )
            )
            registry_id = self.cur.fetchone()[0]
            self.conn.commit()

            print(f"Model registered: {registry_id} ({git_commit[:8]}) deployed by {deployed_by}")
            return registry_id

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"ModelGovernance: register_model error: {e}")
            raise
        finally:
            self.disconnect()

    def audit_config_change(self, key: str, old_value: str, new_value: str,
                           changed_by: str, reason: str):
        """Log a configuration parameter change.

        Args:
            key: Config parameter name
            old_value: Previous value
            new_value: New value
            changed_by: User making the change
            reason: Reason for change
        """
        try:
            self.connect()

            self.cur.execute(
                """
                INSERT INTO algo_config_audit (
                    config_key, old_value, new_value, changed_by, change_reason
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (key, str(old_value), str(new_value), changed_by, reason)
            )
            self.conn.commit()

            print(f"Config change audited: {key} {old_value} → {new_value} ({reason})")

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"ModelGovernance: audit_config_change error: {e}")
        finally:
            self.disconnect()

    def run_champion_challenger_test(self, champion_registry_id: int,
                                     challenger_registry_id: int,
                                     test_date: Optional[date] = None) -> Dict[str, Any]:
        """Run statistical A/B test comparing champion vs. challenger strategy.

        Routes 10% of qualifying signals to challenger, compares P&L using Welch's t-test.

        Args:
            champion_registry_id: Registry ID of champion model
            challenger_registry_id: Registry ID of challenger model
            test_date: Date to report results (default today)

        Returns:
            dict with test results and winner
        """
        try:
            if not test_date:
                test_date = date.today()

            self.connect()

            # Fetch champion and challenger trades for comparison
            self.cur.execute(
                """
                SELECT strategy_version, profit_loss_pct FROM algo_trades
                WHERE status = 'closed'
                  AND strategy_version = %s
                  AND exit_date >= %s - INTERVAL '30 days'
                """,
                (champion_registry_id, test_date)
            )
            champion_trades = [float(row[1]) for row in self.cur.fetchall()]

            self.cur.execute(
                """
                SELECT strategy_version, profit_loss_pct FROM algo_trades
                WHERE status = 'closed'
                  AND strategy_version = %s
                  AND exit_date >= %s - INTERVAL '30 days'
                """,
                (challenger_registry_id, test_date)
            )
            challenger_trades = [float(row[1]) for row in self.cur.fetchall()]

            if len(champion_trades) < 5 or len(challenger_trades) < 5:
                return {
                    'status': 'insufficient_data',
                    'champion_trades': len(champion_trades),
                    'challenger_trades': len(challenger_trades),
                }

            # Welch's t-test (unequal variance)
            t_stat, p_value = stats.ttest_ind(challenger_trades, champion_trades, equal_var=False)

            champion_pnl = np.mean(champion_trades)
            challenger_pnl = np.mean(challenger_trades)

            winner = 'CHALLENGER' if p_value < 0.05 and challenger_pnl > champion_pnl else 'CHAMPION'

            self.cur.execute(
                """
                INSERT INTO algo_champion_challenger (
                    trial_date, champion_registry_id, challenger_registry_id,
                    champion_trades, challenger_trades,
                    champion_pnl_pct, challenger_pnl_pct,
                    t_statistic, p_value, winner
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    test_date, champion_registry_id, challenger_registry_id,
                    len(champion_trades), len(challenger_trades),
                    round(champion_pnl, 2), round(challenger_pnl, 2),
                    round(t_stat, 4), round(p_value, 6), winner
                )
            )
            self.conn.commit()

            return {
                'status': 'success',
                'test_date': test_date,
                'champion_trades': len(champion_trades),
                'challenger_trades': len(challenger_trades),
                'champion_pnl_pct': round(champion_pnl, 2),
                'challenger_pnl_pct': round(challenger_pnl, 2),
                't_statistic': round(t_stat, 4),
                'p_value': round(p_value, 6),
                'statistical_significance': 'YES' if p_value < 0.05 else 'NO',
                'winner': winner,
                'recommendation': f'Promote {winner} to champion' if winner == 'CHALLENGER' else 'Keep champion',
            }

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"ModelGovernance: champion_challenger error: {e}")
            return {'status': 'error', 'message': str(e)}
        finally:
            self.disconnect()

    def compute_information_coefficient(self, lookback_days: int = 60) -> Dict[str, Any]:
        """Compute Information Coefficient (IC) — correlation between signal and forward returns.

        IC > 0.05: Meaningful signal
        IC declining to 0: Alpha decay
        IC < 0: Signal degradation

        Args:
            lookback_days: Days to compute IC over

        Returns:
            dict with IC metrics and interpretation
        """
        try:
            self.connect()

            # Get swing scores and subsequent returns for correlation
            self.cur.execute(
                """
                SELECT ss.symbol, ss.score, pd.close,
                       (SELECT close FROM price_daily WHERE symbol = ss.symbol
                        AND date = ss.date + INTERVAL '5 days'
                        ORDER BY date DESC LIMIT 1) as future_price
                FROM swing_trader_scores ss
                JOIN price_daily pd ON ss.symbol = pd.symbol AND ss.date = pd.date
                WHERE ss.date >= CURRENT_DATE - INTERVAL '%d days'
                """ % lookback_days
            )
            rows = self.cur.fetchall()

            if not rows or len(rows) < 10:
                return {
                    'status': 'insufficient_data',
                    'data_points': len(rows) if rows else 0,
                }

            signals = []
            forward_returns = []

            for symbol, score, price, future_price in rows:
                if price and future_price:
                    signals.append(float(score))
                    ret = (float(future_price) - float(price)) / float(price)
                    forward_returns.append(ret)

            if len(signals) < 10:
                return {'status': 'insufficient_data', 'data_points': len(signals)}

            # Compute Pearson and Spearman correlation
            ic_pearson, p_pearson = stats.pearsonr(signals, forward_returns)
            ic_spearman, p_spearman = stats.spearmanr(signals, forward_returns)

            if ic_pearson > 0.05:
                interpretation = 'MEANINGFUL (>0.05)'
            elif ic_pearson > 0.02:
                interpretation = 'WEAK (0.02-0.05)'
            elif ic_pearson > 0:
                interpretation = 'MINIMAL (0-0.02)'
            else:
                interpretation = 'DEGRADED (<0)'

            result = {
                'status': 'success',
                'ic_date': date.today(),
                'data_points': len(signals),
                'lookback_days': lookback_days,
                'ic_pearson': round(ic_pearson, 4),
                'ic_spearman': round(ic_spearman, 4),
                'p_value_pearson': round(p_pearson, 6),
                'ic_interpretation': interpretation,
                'alert': 'Alpha decay warning: IC trending below 0.05' if ic_pearson < 0.05 else None,
            }

            # Store in database
            self.cur.execute(
                """
                INSERT INTO algo_information_coefficient (
                    ic_date, signal_name, lookback_days, ic_pearson, ic_spearman, ic_interpretation
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (date.today(), 'swing_score', lookback_days, ic_pearson, ic_spearman, interpretation)
            )
            self.conn.commit()

            return result

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"ModelGovernance: information_coefficient error: {e}")
            return {'status': 'error', 'message': str(e)}
        finally:
            self.disconnect()

    def get_active_models(self) -> list:
        """Get list of active deployed models.

        Returns:
            list of active model records
        """
        try:
            self.connect()

            self.cur.execute(
                """
                SELECT registry_id, strategy_name, git_commit_hash, deployed_at,
                       backtest_sharpe, deployed_by
                FROM algo_model_registry
                WHERE status = 'active'
                ORDER BY deployed_at DESC
                """
            )
            rows = self.cur.fetchall()

            models = []
            for row in rows:
                models.append({
                    'registry_id': row[0],
                    'strategy_name': row[1],
                    'git_commit': row[2][:8],
                    'deployed_at': row[3].isoformat() if row[3] else None,
                    'backtest_sharpe': float(row[4]) if row[4] else None,
                    'deployed_by': row[5],
                })

            return models

        except Exception as e:
            print(f"ModelGovernance: get_active_models error: {e}")
            return []
        finally:
            self.disconnect()
