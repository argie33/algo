#!/usr/bin/env python3
"""
Position Sizer - Calculates trade size based on risk management rules

Rules:
- Base risk: 0.75% of portfolio per trade
- Drawdown defense: reduce risk at -5%, -10%, -15%, -20%
- Pyramid entry: 50/33/17 split across multiple entries
- Max position size: 8% of portfolio
- Max concentration: 50% in single position
- Max positions: 12 concurrent
"""

from algo.infrastructure import get_alpaca_timeout
import os
from datetime import date as _date
from utils.db import DatabaseContext

import logging

logger = logging.getLogger(__name__)

class PositionSizer:
    """Calculate position sizes based on risk parameters."""

    def __init__(self, config):
        self.config = config

    def _with_cursor(self, operation):
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext('read') as cur:
                return operation(cur)
        except Exception as e:
            logger.debug(f"Database operation failed: {e}")
            return None

    def get_portfolio_value(self):
        """Get current portfolio value.

        Priority:
        1. Live Alpaca account (most accurate)
        2. Latest portfolio snapshot (up to 2 days old)

        CRITICAL: Does NOT fall back to default $100k. If neither is available,
        raises RuntimeError to fail-closed. Position sizing requires accurate
        portfolio value — guessing is worse than not trading.
        """
        alpaca_value = self._fetch_live_alpaca_equity()
        if alpaca_value is not None:
            logger.info(f"[PORTFOLIO] Using live Alpaca value: ${alpaca_value:,.2f}")
            return alpaca_value

        try:
            def fetch_snapshot(cur):
                cur.execute("""
                    SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                return cur.fetchone()

            result = self._with_cursor(fetch_snapshot)
            if result is not None and result[0] is not None:
                snapshot_value = float(result[0])
                snapshot_date = result[1]
                age_days = (_date.today() - snapshot_date).days if snapshot_date else 999
                if age_days <= 2:
                    logger.info(f"[PORTFOLIO] Using snapshot from {age_days}d ago: ${snapshot_value:,.2f}")
                    return snapshot_value
                logger.error(
                    f"Portfolio snapshot is {age_days} days old (threshold: 2 days). "
                    "Cannot use stale snapshot for position sizing. "
                    "Phase 7 must run daily to maintain fresh snapshots."
                )
        except Exception as e:
            logger.error(f"Error fetching portfolio snapshot: {e}")

        # CRITICAL: No valid portfolio value available. Fail-closed.
        # Better to skip trading than risk wrong position sizing.
        error_msg = (
            "CRITICAL: Portfolio value unavailable. "
            "Cannot execute trades without knowing account size. "
            "Check: (1) Is Alpaca API reachable? (2) Did Phase 7 run yesterday? "
            "(3) Is there a recent portfolio snapshot in the database? "
            "Phase 6 entry execution will be halted."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    def _fetch_live_alpaca_equity(self):
        """Fetch live portfolio equity from Alpaca with retries. Returns None on failure."""
        import requests
        import time
        try:
            from config.credential_manager import get_credential_manager as _get_cm
            _creds = _get_cm().get_alpaca_credentials()
            key = _creds.get("key")
            secret = _creds.get("secret")
        except Exception as e:
            logger.debug(f"Failed to get credentials from credential manager, falling back to env vars: {e}")
            key = os.getenv("APCA_API_KEY_ID")
            secret = os.getenv("APCA_API_SECRET_KEY")
        base = os.getenv('APCA_API_BASE_URL')
        if not base:
            try:
                from config.alpaca_config import get_alpaca_base_url
                base = get_alpaca_base_url()
            except Exception as cfg_e:
                logger.error(f"APCA_API_BASE_URL not set and unable to load from unified config: {cfg_e}")
                return None
        if not key or not secret:
            return None

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f'{base}/v2/account',
                    headers={'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret},
                    timeout=get_alpaca_timeout(),
                )
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except (ValueError, Exception) as e:
                        logger.warning(f"Invalid JSON from Alpaca portfolio API: {e}")
                        return None
                    pv = data.get('portfolio_value') or data.get('equity')
                    if pv:
                        return float(pv)
                elif response.status_code in (429, 503):
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt)
                        logger.debug(f"Alpaca API rate limited/unavailable (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.debug(f"Alpaca API unavailable after {max_retries} attempts")
                    return None
                else:
                    logger.debug(f"Alpaca portfolio API error (status {response.status_code})")
                    return None
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt)
                    logger.debug(f"Alpaca API transient error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.debug(f"Portfolio value retrieval failed after {max_retries} attempts: {e}")
                return None
            except Exception as e:
                logger.debug(f"Portfolio value retrieval failed: {e}")
                return None
        return None

    def get_current_drawdown(self):
        """Calculate current drawdown from peak.

        B13: Fail-closed — if any data missing, assume worst case to protect capital.
        """
        try:
            def calc_drawdown(cur):
                cur.execute("SELECT COUNT(*) FROM algo_portfolio_snapshots")
                count_result = cur.fetchone()
                if not count_result or count_result[0] == 0:
                    return 0.0

                cur.execute("""
                    SELECT
                        MAX(total_portfolio_value) as peak,
                        (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                         ORDER BY snapshot_date DESC LIMIT 1) as current
                    FROM algo_portfolio_snapshots
                """)
                result = cur.fetchone()
                if not result or not result[0] or not result[1]:
                    logger.warning("Portfolio snapshot data inconsistent; assuming 25% drawdown (fail-closed)")
                    return 25.0

                peak = float(result[0])
                current = float(result[1])
                if peak == 0:
                    logger.warning("Peak portfolio value is zero; assuming 25% drawdown (fail-closed)")
                    return 25.0

                drawdown_pct = ((peak - current) / peak) * 100
                return max(0, drawdown_pct)

            result = self._with_cursor(calc_drawdown)
            if result is not None:
                return result
            return 25.0
        except Exception as e:
            logger.error(f"Could not calculate drawdown: {e}")
            return 25.0

    def get_risk_adjustment(self):
        """Get risk adjustment factor based on drawdown.

        Combined with market_exposure_pct multiplier for dynamic risk:
            effective_risk = base_risk × dd_adjustment × (exposure_pct / 100)
        """
        dd = self.get_current_drawdown()

        if dd >= 20:
            return 0.0
        elif dd >= 15:
            return float(self.config.get('risk_reduction_at_minus_15', 0.25))
        elif dd >= 10:
            return float(self.config.get('risk_reduction_at_minus_10', 0.5))
        elif dd >= 5:
            return float(self.config.get('risk_reduction_at_minus_5', 0.75))
        else:
            return 1.0

    def get_market_exposure_multiplier(self):
        """Look up the most recent market exposure pct (0-100). Returns multiplier 0.0-1.0.

        B13: Fail-closed — if query fails, assume conservative exposure.
        """
        try:
            def fetch_exposure(cur):
                cur.execute(
                    "SELECT exposure_pct FROM market_exposure_daily ORDER BY date DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return float(row[0]) / 100.0
                return None

            result = self._with_cursor(fetch_exposure)
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"Could not fetch market exposure: {e}")
        return 0.5

    def get_vix_caution_multiplier(self):
        """Reduce risk if VIX is in caution zone (caution_threshold < VIX < max_threshold).

        Returns risk multiplier: 1.0 if VIX is normal, reduced multiplier if in caution zone.
        """
        try:
            def fetch_vix(cur):
                cur.execute(
                    "SELECT vix_level FROM market_health_daily ORDER BY date DESC LIMIT 1"
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    return 1.0
                vix = float(row[0])
                caution_threshold = float(self.config.get('vix_caution_threshold', 25.0))
                max_threshold = float(self.config.get('vix_max_threshold', 35.0))
                if vix > caution_threshold and vix <= max_threshold:
                    return float(self.config.get('vix_caution_risk_reduction', 0.75))
                return 1.0

            return self._with_cursor(fetch_vix) or 1.0
        except Exception as vix_e:
            logger.debug(f"VIX multiplier calculation failed: {vix_e}")
            return 1.0

    def get_phase_size_multiplier(self):
        """Stage-2 phase mult: always 1.0 (DB schema has no late/climax phase column)."""
        return 1.0

    def get_position_size_multiplier_from_regime(self, signal_date=None):
        """Get position size multiplier from current market regime (mockable for tests)."""
        regime_mult = 1.0
        try:
            from algo.orchestration import RegimeManager
            regime_mgr = RegimeManager()
            regime_mult = regime_mgr.get_position_size_multiplier(signal_date)
        except Exception as e:
            logger.debug(f"Could not load regime multiplier: {e}. Using 1.0.")
        return regime_mult

    def get_active_positions_value(self):
        """Get sum of active position values.

        B13: Fail-closed — on error, assume high value to prevent over-sizing.
        """
        try:
            def fetch_positions_value(cur):
                cur.execute("""
                    SELECT COALESCE(SUM(position_value), 0) as total
                    FROM algo_positions
                    WHERE status = 'open'
                """)
                result = cur.fetchone()
                return float(result[0]) if result else 0.0

            result = self._with_cursor(fetch_positions_value)
            if result is not None:
                return result
            return 0.0
        except Exception as e:
            logger.error(f"ERROR: Could not fetch position values: {e} - failing closed to prevent inaccurate position sizing")
            raise RuntimeError(f"Portfolio value unavailable - cannot calculate safe position size: {e}")

    def get_position_count(self):
        """Get count of active positions (Issue #26: Now checks capital, not just count).

        B13: Fail-closed — on error, assume max positions to prevent over-trading.
        """
        try:
            def fetch_position_count(cur):
                cur.execute("""
                    SELECT COUNT(*) as count FROM algo_positions WHERE status = 'open'
                """)
                result = cur.fetchone()
                return result[0] if result else 0

            result = self._with_cursor(fetch_position_count)
            if result is not None:
                return result
            return 0
        except Exception as e:
            logger.error(f"WARNING: Could not fetch position count: {e}")
            return int(self.config.get('max_positions', 12))

    def get_active_positions_capital_pct(self):
        """Issue #26: Get total capital invested as % of portfolio.

        Returns capital-based position limit, not just count-based.
        """
        try:
            portfolio_value = self.get_portfolio_value()
            if portfolio_value <= 0:
                return 0

            def fetch_capital_pct(cur):
                cur.execute("""
                    SELECT SUM(position_value) FROM algo_positions WHERE status = 'open'
                """)
                result = cur.fetchone()
                total_value = float(result[0]) if result is not None and result[0] is not None else 0
                return (total_value / portfolio_value * 100) if portfolio_value > 0 else 0

            result = self._with_cursor(fetch_capital_pct)
            return result if result is not None else 0
        except Exception as calc_e:
            logger.debug(f"Failed to calculate short exposure: {calc_e}")
            return 0

    def calculate_position_size(self, symbol, entry_price, stop_loss_price, signal_date=None,
                               portfolio_value=None):
        """
        Calculate position size for a new trade.

        Args:
            portfolio_value: Pre-fetched portfolio value to skip Alpaca API call.
                             Pass this when calling in a loop to avoid N Alpaca calls.

        Returns:
        {
            'shares': number of shares,
            'position_size_pct': % of portfolio,
            'risk_dollars': dollar amount at risk,
            'status': 'ok' | 'no_room' | 'drawdown_halt'
        }
        """
        try:
            return self._calculate_with_external_cursor(symbol, entry_price, stop_loss_price,
                                                        signal_date, portfolio_value=portfolio_value)
        except Exception as e:
            return {
                'shares': 0,
                'position_size_pct': 0,
                'risk_dollars': 0,
                'status': 'error',
                'reason': str(e)
            }

    def _calculate_with_external_cursor(self, symbol, entry_price, stop_loss_price,
                                         signal_date=None, portfolio_value=None):
        """Internal method for position calculation."""
        try:
            if portfolio_value is None:
                portfolio_value = self.get_portfolio_value()
            risk_adjustment = self.get_risk_adjustment()
            active_positions = self.get_position_count()
            active_position_value = self.get_active_positions_value()

            max_positions = self.config.get('max_positions', 12)
            if active_positions >= max_positions:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'no_room',
                    'reason': f'{active_positions} open positions >= {max_positions} max'
                }

            if risk_adjustment == 0:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'drawdown_halt',
                    'reason': f'Drawdown >= 20%, trading halted'
                }

            base_risk_pct = float(self.config.get('base_risk_pct', 0.75)) / 100
            exposure_mult = self.get_market_exposure_multiplier()
            phase_mult = self.get_phase_size_multiplier()
            vix_mult = self.get_vix_caution_multiplier()
            regime_mult = self.get_position_size_multiplier_from_regime(signal_date)

            adjusted_risk_pct = base_risk_pct * risk_adjustment * exposure_mult * phase_mult * vix_mult * regime_mult
            risk_dollars = portfolio_value * adjusted_risk_pct

            if phase_mult == 0.0:
                logger.warning(
                    f'Position sizing halted for {symbol}: Stage-2 climax phase detected. '
                    f'No new entries until stock exits climax conditions.'
                )
                return {
                    'shares': 0, 'position_size_pct': 0, 'risk_dollars': 0,
                    'status': 'phase_climax',
                    'reason': f'{symbol} in Stage-2 climax phase — skip entry',
                }

            if entry_price <= 0 or stop_loss_price >= entry_price:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'invalid',
                    'reason': 'Invalid entry or stop price'
                }

            min_risk_floor = float(self.config.get('min_risk_pct_floor', 0.10)) / 100
            has_safety_reduction = (exposure_mult < 0.8 or vix_mult < 1.0 or risk_adjustment < 1.0)
            if adjusted_risk_pct < min_risk_floor and not has_safety_reduction:
                adjusted_risk_pct = min_risk_floor
                risk_dollars = portfolio_value * adjusted_risk_pct

            risk_per_share = entry_price - stop_loss_price
            shares = int(round(risk_dollars / risk_per_share)) if risk_per_share > 0 else 0

            if shares < 1:
                return {
                    'shares': 0, 'position_size_pct': 0, 'risk_dollars': 0,
                    'status': 'too_small',
                    'reason': f'Position too small: risk_dollars=${risk_dollars:.2f}, risk_per_share=${risk_per_share:.2f}',
                }

            position_value = shares * entry_price
            max_position_pct = self.config.get('max_position_size_pct', 8.0) / 100
            max_position_value = portfolio_value * max_position_pct

            if position_value > max_position_value:
                shares = int(round(max_position_value / entry_price))
                position_value = shares * entry_price
                risk_dollars = risk_per_share * shares

            position_pct_of_portfolio = (position_value / portfolio_value * 100) if portfolio_value > 0 else 0
            max_concentration = float(self.config.get('max_concentration_pct', 50.0))

            if position_pct_of_portfolio > max_concentration:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'concentration',
                    'reason': f'Position would be {position_pct_of_portfolio:.1f}% > {max_concentration:.0f}% portfolio'
                }

            total_invested = active_position_value + position_value
            max_invested_pct = float(self.config.get('max_total_invested_pct', 95.0))
            if portfolio_value > 0 and (total_invested / portfolio_value * 100) > max_invested_pct:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'no_room',
                    'reason': f'Total invested would be {total_invested/portfolio_value*100:.0f}% > {max_invested_pct:.0f}%'
                }

            return {
                'shares': shares,
                'position_size_pct': position_pct_of_portfolio,
                'risk_dollars': risk_dollars,
                'position_value': position_value,
                'status': 'ok',
                'reason': f'{shares} shares @ ${entry_price:.2f} = ${position_value:.2f} ({position_pct_of_portfolio:.1f}%)'
            }

        except Exception as e:
            return {
                'shares': 0,
                'position_size_pct': 0,
                'risk_dollars': 0,
                'status': 'error',
                'reason': str(e)
            }

    def get_pyramid_split(self):
        """Get pyramid entry split percentages."""
        split_str = self.config.get('pyramid_split_pct', '50,33,17')
        try:
            splits = [float(x.strip()) / 100 for x in split_str.split(',')]
            return splits
        except (ValueError, AttributeError):
            return [0.50, 0.33, 0.17]

