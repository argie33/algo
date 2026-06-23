#!/usr/bin/env python3
"""
Position Sizer - Calculates trade size based on risk management rules

Rules:
- Base risk: 0.75% of portfolio per trade
- Drawdown defense: reduce risk at -5%, -10%, -15%, -20%
- Max position size: 8% of portfolio
- Max concentration: 50% in single position
- Max positions: 12 concurrent
"""

import decimal
import logging
import os
from datetime import date as _date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import psycopg2

from algo.infrastructure import get_alpaca_timeout
from algo.trading.exceptions import (
    ConfigurationError,
    DatabaseError,
    DataUnavailableError,
    PortfolioValueError,
)
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

PORTFOLIO_SNAPSHOT_LOCK_ID = 2147483647


class PositionSizer:
    """Calculate position sizes based on risk parameters."""

    def __init__(self, config: Any) -> None:
        if config is None:
            raise ValueError("PositionSizer config cannot be None")
        if not isinstance(config, dict):
            raise TypeError(f"PositionSizer config must be a dict, got {type(config).__name__}")
        self.config = config

        required_config_keys = [
            "base_risk_pct",
            "max_positions",
            "risk_reduction_at_minus_5",
            "risk_reduction_at_minus_10",
            "risk_reduction_at_minus_15",
            "vix_caution_threshold",
            "vix_max_threshold",
            "vix_caution_risk_reduction",
        ]
        missing_keys = [k for k in required_config_keys if k not in config or config[k] is None]
        if missing_keys:
            raise ConfigurationError(
                f"CRITICAL: PositionSizer config missing required keys: {', '.join(missing_keys)}. "
                f"Cannot proceed with position sizing without explicit risk configuration."
            )

    def _with_cursor(self, operation: Any) -> Any:
        """Execute an operation with a cursor via DatabaseContext."""
        with DatabaseContext("read") as cur:
            return operation(cur)

    # Type: Any to accommodate various operation return types

    def get_portfolio_value(self) -> Decimal:
        """Get current portfolio value.

        Priority:
        1. Live Alpaca account (most accurate)
        2. Latest portfolio snapshot (up to 2 days old)

        CRITICAL: Does NOT fall back to default $100k. If neither is available,
        raises RuntimeError to fail-closed. Position sizing requires accurate
        portfolio value  -" guessing is worse than not trading.

        THREAD SAFETY: Uses PostgreSQL advisory lock to prevent race condition
        where Phase 6 (position sizing) reads while Phase 7 (reconciliation) updates.
        """
        try:
            alpaca_value = self._fetch_live_alpaca_equity()
            if alpaca_value is not None:
                logger.info(f"[PORTFOLIO] Using live Alpaca value: ${alpaca_value:,.2f}")
                return alpaca_value
        except RuntimeError as e:
            logger.critical(f"Live Alpaca portfolio value fetch CRITICAL FAILURE: {e}")
            raise RuntimeError(
                "[POSITION_SIZE] Failed to fetch current portfolio equity from Alpaca "
                "(cannot size positions without current value)"
            ) from e

        def fetch_snapshot(cur):
            cur.execute("SELECT pg_advisory_lock(%s)", (PORTFOLIO_SNAPSHOT_LOCK_ID,))
            cur.fetchone()
            try:
                cur.execute("""
                    SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                return cur.fetchone()
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (PORTFOLIO_SNAPSHOT_LOCK_ID,))

        try:
            result = self._with_cursor(fetch_snapshot)
            if result is not None and result[0] is not None:
                snapshot_value = Decimal(str(result[0]))
                snapshot_date = result[1]
                age_days = (_date.today() - snapshot_date).days if snapshot_date else 999
                if age_days <= 1:
                    logger.info(
                        f"[PORTFOLIO] Using snapshot from {age_days}d ago (threshold: 1 day): ${snapshot_value:,.2f}"
                    )
                    return snapshot_value
                # CRITICAL: Snapshot is too stale. Stricter 1-day threshold prevents position
                # sizing on multi-day-old data when Phase 7 fails. Better to halt than risk
                # thousands of dollars in wrong position sizes.
                error_msg = (
                    f"Portfolio snapshot too stale ({age_days}d old, threshold 1 day). "
                    "Phase 7 must run daily. Position sizing halted."
                )
                logger.critical(error_msg)
                raise PortfolioValueError(error_msg)
        except PortfolioValueError:
            raise
        except DatabaseError as e:
            logger.error(f"Database error fetching portfolio snapshot: {e}")
            raise PortfolioValueError(f"Portfolio snapshot unavailable due to database error: {e}") from e
        except (ValueError, RuntimeError) as e:
            logger.error(f"Error processing portfolio snapshot: {e}")
            raise PortfolioValueError(f"Portfolio snapshot processing failed: {e}") from e

        # CRITICAL: No valid portfolio value available. Fail-closed.
        error_msg = (
            "CRITICAL: Portfolio value unavailable. "
            "Cannot execute trades without knowing account size. "
            "Check: (1) Is Alpaca API reachable? (2) Did Phase 7 run yesterday? "
            "(3) Is there a recent portfolio snapshot in the database? "
            "Phase 6 entry execution will be halted."
        )
        logger.critical(error_msg)
        raise PortfolioValueError(error_msg)

    def _fetch_live_alpaca_equity(self) -> Decimal:
        """Fetch live portfolio equity from Alpaca with retries. Raises on credential/API failure."""
        import time

        import requests

        try:
            from config.credential_manager import get_credential_manager as _get_cm

            _creds = _get_cm().get_alpaca_credentials()
            key = _creds.get("key")
            secret = _creds.get("secret")
        except (ImportError, AttributeError, KeyError) as e:
            logger.debug(f"Failed to get credentials from credential manager, falling back to env vars: {e}")
            key = os.getenv("APCA_API_KEY_ID")
            secret = os.getenv("APCA_API_SECRET_KEY")
        base = os.getenv("APCA_API_BASE_URL")
        if not base:
            try:
                from config.api_endpoints import get_alpaca_base_url

                base = get_alpaca_base_url()
            except (ImportError, AttributeError) as cfg_e:
                raise ValueError(f"Alpaca config unavailable: {cfg_e}") from cfg_e
        if not key or not secret:
            raise RuntimeError("CRITICAL: Alpaca credentials not found. Cannot fetch portfolio value.")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f"{base}/v2/account",
                    headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                    timeout=get_alpaca_timeout(),
                )
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except ValueError as e:
                        raise RuntimeError(f"Invalid JSON response from Alpaca portfolio API: {e}") from e

                    if "portfolio_value" in data and data["portfolio_value"] is not None:
                        pv = data["portfolio_value"]
                        return Decimal(str(pv))

                    if "equity" in data and data["equity"] is not None:
                        pv = data["equity"]
                        return Decimal(str(pv))

                    raise ValueError(
                        f"Portfolio value fields missing or null in Alpaca response. Expected 'portfolio_value' or 'equity', got: {list(data.keys())}"
                    )
                elif response.status_code in (429, 503):
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.debug(
                            f"Alpaca API rate limited/unavailable (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    raise RuntimeError(
                        f"Alpaca API unavailable after {max_retries} attempts (status {response.status_code})"
                    )
                else:
                    raise RuntimeError(f"Alpaca portfolio API error (status {response.status_code})")
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.debug(
                        f"Alpaca API transient error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                    continue
                raise RuntimeError(f"Portfolio value retrieval failed after {max_retries} attempts: {e}") from e
            except RuntimeError:
                raise
            except requests.RequestException as e:
                raise RuntimeError(f"Alpaca API error: {type(e).__name__}: {e}") from e
        # Should never reach here (all paths raise or return above)
        raise RuntimeError("CRITICAL: Alpaca portfolio value retrieval exhausted all retries without a result.")

    def get_current_drawdown(self) -> Decimal:
        """Calculate current drawdown from peak.

        Fails fast  -" raises if any data missing. Position sizing requires accurate
        drawdown to adjust risk multiplier correctly. Guessing is worse than not trading.
        """

        def calc_drawdown(cur: Any) -> Decimal:
            cur.execute("SELECT COUNT(*) FROM algo_portfolio_snapshots")
            count_result = cur.fetchone()
            if not count_result or count_result[0] == 0:
                raise RuntimeError(
                    "No portfolio snapshots found. Phase 7 must run daily to maintain drawdown tracking."
                )

            cur.execute("""
                SELECT
                    MAX(total_portfolio_value) as peak,
                    (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                     ORDER BY snapshot_date DESC LIMIT 1) as current
                FROM algo_portfolio_snapshots
            """)
            result = cur.fetchone()
            if not result or not result[0] or not result[1]:
                raise RuntimeError(
                    "Portfolio snapshot data inconsistent. Cannot calculate drawdown for position sizing."
                )

            peak = Decimal(str(result[0]))
            current = Decimal(str(result[1]))
            if peak == 0:
                raise RuntimeError("Peak portfolio value is zero. Portfolio snapshots data is invalid.")

            drawdown_pct = ((peak - current) / peak) * Decimal(100)
            return max(Decimal(0), drawdown_pct)

        result: Any = self._with_cursor(calc_drawdown)
        if result is not None:
            return cast(Decimal, result)
        raise RuntimeError(
            "Could not fetch drawdown from database. Cannot calculate risk adjustment for position sizing."
        )

    def get_risk_adjustment(self) -> Decimal:
        """Get risk adjustment factor based on drawdown.

        Combined with market_exposure_pct multiplier for dynamic risk:
            effective_risk = base_risk x dd_adjustment x (exposure_pct / 100)

        Config keys validated at init; assumes all risk thresholds are present.
        """
        dd = self.get_current_drawdown()

        if dd >= 20:
            logger.critical(
                "CIRCUIT BREAKER TRIGGERED: Portfolio drawdown >= 20%. "
                "Position sizing halted. All entries blocked until recovery."
            )
            return Decimal(0)
        elif dd >= 15:
            return Decimal(str(self.config["risk_reduction_at_minus_15"]))
        elif dd >= 10:
            return Decimal(str(self.config["risk_reduction_at_minus_10"]))
        elif dd >= 5:
            return Decimal(str(self.config["risk_reduction_at_minus_5"]))
        else:
            return Decimal(1)

    def get_market_exposure_multiplier(self) -> Decimal:
        """Look up the most recent market exposure pct (0-100). Returns multiplier 0.0-1.0.

        Fail-fast  -" if data unavailable, raises exception. Position sizing requires
        current market exposure to avoid over-committing during risk-off periods.
        """

        def fetch_exposure(cur: Any) -> Decimal:
            cur.execute("SELECT exposure_pct FROM market_exposure_daily ORDER BY date DESC LIMIT 1")
            row = cur.fetchone()
            if not row or row[0] is None:
                raise ValueError("Market exposure data unavailable. Phase must run daily to maintain this.")
            return Decimal(str(row[0])) / Decimal(100)

        result: Any = self._with_cursor(fetch_exposure)
        if result is not None:
            return cast(Decimal, result)
        raise RuntimeError("Could not fetch market exposure from database. Cannot calculate safe position size.")

    def get_vix_caution_multiplier(self) -> Decimal:
        """Reduce risk if VIX is in caution zone (caution_threshold < VIX < max_threshold).

        Returns risk multiplier: 1.0 if VIX is normal, reduced multiplier if in caution zone.
        Fail-fast  -" if data unavailable, raises exception.

        VIX thresholds validated at init; assumes all config keys are present.
        """

        def fetch_vix(cur: Any) -> Decimal:
            cur.execute(
                "SELECT vix_level FROM market_health_daily WHERE vix_level IS NOT NULL ORDER BY date DESC LIMIT 1"
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                raise ValueError(
                    "VIX level unavailable from market_health_daily. Cannot adjust position size for volatility."
                )
            vix = Decimal(str(row[0]))
            caution_threshold = Decimal(str(self.config["vix_caution_threshold"]))
            max_threshold = Decimal(str(self.config["vix_max_threshold"]))
            if vix > caution_threshold and vix <= max_threshold:
                return Decimal(str(self.config["vix_caution_risk_reduction"]))
            return Decimal(1)

        result: Any = self._with_cursor(fetch_vix)
        if result is not None:
            return cast(Decimal, result)
        raise RuntimeError("Could not fetch VIX from database. Cannot calculate safe position size.")

    def get_phase_size_multiplier(self) -> float:
        """Stage-2 phase mult: always 1.0 (DB schema has no late/climax phase column)."""
        return 1.0

    def get_position_size_multiplier_from_regime(self, signal_date: Any = None) -> float:
        """Get position size multiplier from current market regime.

        Fail-fast  -" if regime cannot be determined, raises exception. Position sizing
        must account for current market regime to avoid inappropriate sizing.
        """
        try:
            from algo.orchestration import RegimeManager

            regime_mgr = RegimeManager()
            regime_mult = regime_mgr.get_position_size_multiplier(signal_date)
            if regime_mult is None:
                raise ValueError("Regime multiplier is None")
            return regime_mult
        except ValueError:
            raise
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Could not load RegimeManager: {e}") from e
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Regime multiplier calculation failed: {type(e).__name__}: {e}") from e

    def get_active_positions_value(self) -> Decimal:
        """Get sum of active position values.

        B13: Fail-closed  -" on error, assume high value to prevent over-sizing.
        """

        def fetch_positions_value(cur: Any) -> Decimal:
            cur.execute("""
                SELECT COALESCE(SUM(position_value), 0) as total
                FROM algo_positions
                WHERE status = 'open'
            """)
            result = cur.fetchone()
            return Decimal(str(result[0])) if result else Decimal(0)

        try:
            result: Any = self._with_cursor(fetch_positions_value)
            if result is not None:
                return cast(Decimal, result)
            raise RuntimeError("Portfolio value query returned no data")
        except (RuntimeError, ValueError) as e:
            logger.error(f"Could not fetch position values: {e}")
            raise DataUnavailableError(f"Portfolio value unavailable - cannot calculate safe position size: {e}") from e
        except DatabaseError as e:
            logger.error(f"Database error fetching position values: {e}")
            raise DataUnavailableError(f"Portfolio value unavailable due to database error: {e}") from e

    def get_position_count(self) -> int:
        """Get count of active positions (Issue #26: Now checks capital, not just count).

        Fail-fast  -" if data unavailable, raises exception. Cannot size positions
        without knowing how many are already open.
        """

        def fetch_position_count(cur: Any) -> int:
            cur.execute("""
                SELECT COUNT(*) as count FROM algo_positions WHERE status = 'open'
            """)
            result = cur.fetchone()
            if result is None:
                raise ValueError("Position count query returned None")
            return result[0]

        result: Any = self._with_cursor(fetch_position_count)
        if result is not None:
            return cast(int, result)
        raise RuntimeError("Could not fetch position count from database. Cannot calculate safe position size.")

    def get_active_positions_capital_pct(self) -> Decimal:
        """Issue #26: Get total capital invested as % of portfolio.

        Returns capital-based position limit, not just count-based.
        Fail-fast  -" if data unavailable, raises exception.
        """
        portfolio_value = self.get_portfolio_value()
        if portfolio_value <= 0:
            raise ValueError(f"Invalid portfolio value for capital calculation: {portfolio_value}")

        def fetch_capital_pct(cur: Any) -> Decimal:
            cur.execute("""
                SELECT SUM(position_value) FROM algo_positions WHERE status = 'open'
            """)
            result = cur.fetchone()
            if result is None:
                raise ValueError("Position capital query returned None")
            total_value = Decimal(str(result[0])) if result[0] is not None else Decimal(0)
            return (total_value / portfolio_value * Decimal(100)) if portfolio_value > 0 else Decimal(0)

        result: Any = self._with_cursor(fetch_capital_pct)
        if result is not None:
            return cast(Decimal, result)
        raise RuntimeError("Could not fetch capital percentage from database. Cannot calculate safe position size.")

    def calculate_position_size(
        self,
        symbol: Any,
        entry_price: Any,
        stop_loss_price: Any,
        signal_date: Any = None,
        portfolio_value: Any = None,
    ) -> dict[str, Any]:
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
            return self._calculate_with_external_cursor(
                symbol,
                entry_price,
                stop_loss_price,
                signal_date,
                portfolio_value=portfolio_value,
            )
        except (DataUnavailableError, ConfigurationError, ValueError) as e:
            logger.error(f"Position sizing calculation failed: {type(e).__name__}: {e}")
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "error",
                "reason": str(e),
            }
        except (ZeroDivisionError, TypeError) as e:
            logger.exception(f"Unexpected error in position sizing: {type(e).__name__}: {e}")
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "error",
                "reason": f"Unexpected error: {type(e).__name__}",
            }

    def _calculate_with_external_cursor(
        self,
        symbol: Any,
        entry_price: Any,
        stop_loss_price: Any,
        signal_date: Any = None,
        portfolio_value: Any = None,
    ) -> dict[str, Any]:
        """Internal method for position calculation."""
        try:
            assert symbol and isinstance(symbol, str), f"Symbol must be non-empty string, got {symbol}"
            entry_dec = Decimal(str(entry_price))
            assert entry_dec > 0, f"Entry price must be > 0, got {entry_price}"
            stop_dec = Decimal(str(stop_loss_price))
            assert stop_dec > 0, f"Stop loss must be > 0, got {stop_loss_price}"
            assert stop_dec < entry_dec, f"Stop {stop_dec} must be < entry {entry_dec}"

            if portfolio_value is None:
                portfolio_value = self.get_portfolio_value()
            pv_dec = Decimal(str(portfolio_value))
            assert pv_dec > 0, f"Portfolio value must be > 0, got {portfolio_value}"

            risk_adjustment = self.get_risk_adjustment()
            assert risk_adjustment is not None, "Risk adjustment cannot be None"
            assert Decimal(str(risk_adjustment)) >= 0, f"Risk adjustment must be >= 0, got {risk_adjustment}"

            active_positions = self.get_position_count()
            assert isinstance(active_positions, int), f"Active positions must be int, got {type(active_positions)}"
            active_position_value = self.get_active_positions_value()

            max_positions = int(self.config["max_positions"])
            if max_positions <= 0:
                raise ValueError(f"max_positions must be > 0, got {max_positions}")
            if active_positions >= max_positions:
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "no_room",
                    "reason": f"{active_positions} open positions >= {max_positions} max",
                }

            if risk_adjustment == 0:
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "drawdown_halt",
                    "reason": "Drawdown >= 20%, trading halted",
                }

            base_risk_pct = Decimal(str(self.config["base_risk_pct"])) / Decimal(100)
            exposure_mult = self.get_market_exposure_multiplier()
            phase_mult = self.get_phase_size_multiplier()
            vix_mult = self.get_vix_caution_multiplier()
            regime_mult = self.get_position_size_multiplier_from_regime(signal_date)

            adjusted_risk_pct = (
                base_risk_pct
                * risk_adjustment
                * exposure_mult
                * Decimal(str(phase_mult))
                * vix_mult
                * Decimal(str(regime_mult))
            )
            risk_dollars = (portfolio_value * adjusted_risk_pct).quantize(Decimal("0.01"), ROUND_HALF_UP)

            if phase_mult == 0.0:
                logger.warning(
                    f"Position sizing halted for {symbol}: Stage-2 climax phase detected. "
                    "No new entries until stock exits climax conditions."
                )
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "phase_climax",
                    "reason": f"{symbol} in Stage-2 climax phase - skip entry",
                }

            if entry_price <= 0 or stop_loss_price >= entry_price:
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "invalid",
                    "reason": "Invalid entry or stop price",
                }

            min_risk_val = self.config.get("min_risk_pct_floor")
            if min_risk_val is None:
                raise ValueError(
                    "CRITICAL: min_risk_pct_floor config missing. Cannot enforce minimum position risk floor."
                )
            min_risk_floor = Decimal(str(min_risk_val)) / Decimal(100)
            has_safety_reduction = exposure_mult < 0.8 or vix_mult < 1.0 or risk_adjustment < 1.0
            if adjusted_risk_pct < min_risk_floor and not has_safety_reduction:
                adjusted_risk_pct = min_risk_floor
                risk_dollars = portfolio_value * adjusted_risk_pct

            risk_per_share = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
            shares = (
                int((risk_dollars / risk_per_share).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                if risk_per_share > 0
                else 0
            )

            if shares < 1:
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "too_small",
                    "reason": f"Position too small: risk_dollars=${risk_dollars:.2f}, risk_per_share=${risk_per_share:.2f}",
                }

            position_value = Decimal(shares) * Decimal(str(entry_price))
            max_pos_pct_val = self.config.get("max_position_size_pct")
            if max_pos_pct_val is None:
                raise ValueError("CRITICAL: max_position_size_pct config missing. Cannot enforce position size cap.")
            try:
                max_position_pct = Decimal(str(max_pos_pct_val)) / Decimal(100)
                if max_position_pct <= 0 or max_position_pct > Decimal(1):
                    raise ValueError(f"max_position_size_pct must be between 0 and 100, got {max_pos_pct_val}")
            except (ValueError, TypeError, decimal.InvalidOperation) as e:
                raise ValueError(
                    f"CRITICAL: max_position_size_pct config has invalid value '{max_pos_pct_val}': {e}"
                ) from None
            max_position_value = portfolio_value * max_position_pct

            if position_value > max_position_value:
                shares = int(
                    (max_position_value / Decimal(str(entry_price))).quantize(Decimal(1), rounding=ROUND_HALF_UP)
                )
                position_value = Decimal(shares) * Decimal(str(entry_price))
                risk_dollars = risk_per_share * Decimal(shares)

            position_pct_of_portfolio = (
                (position_value / Decimal(str(portfolio_value)) * Decimal(100)) if portfolio_value > 0 else Decimal(0)
            )
            max_conc_val = self.config.get("max_concentration_pct")
            if max_conc_val is None:
                raise ValueError("CRITICAL: max_concentration_pct config missing. Cannot enforce concentration limit.")
            max_concentration = Decimal(str(max_conc_val))

            if position_pct_of_portfolio > max_concentration:
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "concentration",
                    "reason": f"Position would be {position_pct_of_portfolio:.1f}% > {max_concentration:.0f}% portfolio",
                }

            total_invested = Decimal(str(active_position_value)) + position_value
            max_inv_val = self.config.get("max_total_invested_pct")
            if max_inv_val is None:
                raise ValueError(
                    "CRITICAL: max_total_invested_pct config missing. Cannot enforce total investment limit."
                )
            max_invested_pct = Decimal(str(max_inv_val))
            if (
                portfolio_value > 0
                and (total_invested / Decimal(str(portfolio_value)) * Decimal(100)) > max_invested_pct
            ):
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "no_room",
                    "reason": f"Total invested would be {(total_invested / Decimal(str(portfolio_value)) * Decimal(100)):.0f}% > {max_invested_pct:.0f}%",
                }

            return {
                "shares": shares,
                "position_size_pct": position_pct_of_portfolio,
                "risk_dollars": risk_dollars,
                "position_value": position_value,
                "status": "ok",
                "reason": f"{shares} shares @ ${entry_price:.2f} = ${float(position_value):.2f} ({float(position_pct_of_portfolio):.1f}%)",
            }

        except (
            DataUnavailableError,
            ConfigurationError,
            ValueError,
            RuntimeError,
        ) as e:
            logger.error(f"Position calculation failed: {type(e).__name__}: {e}")
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "error",
                "reason": str(e),
            }
        except (ZeroDivisionError, TypeError) as e:
            logger.exception(f"Unexpected error during position calculation: {type(e).__name__}: {e}")
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "error",
                "reason": f"Unexpected error: {type(e).__name__}",
            }
