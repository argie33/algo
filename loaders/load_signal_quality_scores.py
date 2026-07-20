#!/usr/bin/env python3
"""Signal Quality Scores Loader - Signal strength confirmation from multiple sources.

Computes signal quality scores (0-100) combining buy/sell signal, technical confirmation, and trend.
Required by Phase 1 data freshness check as tier-2 gate for filtering.

Run: python3 load_signal_quality_scores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import argparse  # noqa: E402
import logging  # noqa: E402
from datetime import date, timedelta  # noqa: E402
from typing import Any  # noqa: E402

import pandas as pd  # noqa: E402
import psycopg2  # noqa: E402

from utils.db.context import DatabaseContext  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402
from utils.loaders.config import get_default_parallelism  # noqa: E402
from utils.loaders.helpers import get_active_symbols  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402
from utils.validation import safe_parse_date  # noqa: E402

logger = logging.getLogger(__name__)


class SignalQualityScoresLoader(OptimalLoader):
    table_name = "signal_quality_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def _prepare_batch_context(self) -> None:
        """Load shared data once to avoid N+1 queries."""
        """Load shared data once to avoid N+1 queries (ROOT CAUSE #4 FIX).

        Caches end_date, buy_sell_daily signal count, and watermarks for all symbols
        to avoid per-symbol computation.

        ISSUE #27 FIX: Check that buy_sell_daily is not RUNNING/PENDING before proceeding.
        If buy_sell_daily loader is stuck, sets _batch_context = {"_blocked": True} and returns.
        This signals to fetch_incremental() to raise an error — callers MUST NOT ignore this.
        See fetch_incremental() for the enforcement of the _blocked flag.

        AUTO-POPULATE VCP PATTERNS (NEW): If VCP patterns table exists but is empty,
        auto-populate VCP data from technical_data_daily. This unblocks signal_quality_scores
        when VCP patterns have not been pre-loaded (fixes 1.4% coverage issue).
        """
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

        self._batch_context: dict[str, Any] = {}
        try:
            with DatabaseContext("read") as cur:
                # AUTO-POPULATE VCP PATTERNS if missing (ISSUE FIX: VCP coverage)
                self._ensure_vcp_patterns_populated(cur)

                # Check if buy_sell_daily is ready (ISSUE #27 FIX)
                cur.execute("SELECT status FROM data_loader_status WHERE table_name = 'buy_sell_daily'")
                result = cur.fetchone()
                if result is None:
                    raise RuntimeError(
                        "CRITICAL: data_loader_status has no record for buy_sell_daily. "
                        "Upstream loader not found. Cannot verify dependency readiness."
                    )
                if len(result) < 1:
                    raise RuntimeError(
                        f"CRITICAL: Upstream status query returned invalid row structure. "
                        f"Expected 1 column, got {len(result)}."
                    )
                bs_status = result[0]

                # CRITICAL: Validate upstream loader is actually COMPLETED
                if bs_status not in ("COMPLETED", "success", "OK"):
                    raise RuntimeError(
                        f"CRITICAL: buy_sell_daily upstream loader not ready. "
                        f"Status: {bs_status}. Expected COMPLETED/success/OK. "
                        f"Cannot compute signal quality scores without complete upstream signals."
                    )

                now_utc = datetime.now(timezone.utc)
                now_et = now_utc.astimezone(EASTERN_TZ)
                end: date = now_et.date()

                while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                    end = end - timedelta(days=1)

                cur.execute(
                    "SELECT MAX(date) FROM buy_sell_daily WHERE signal_type IN ('BUY', 'SELL') AND date <= %s",
                    (end,),
                )
                row = cur.fetchone()
                last_bs_date = row[0] if row is not None and row[0] is not None else None
                if last_bs_date:
                    last_bs = safe_parse_date(last_bs_date, "buy_sell_daily max date")
                    if last_bs and last_bs < end:
                        end = last_bs

                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE date = %s AND signal_type IN ('BUY', 'SELL')",
                    (end,),
                )
                cur_row = cur.fetchone()
                if cur_row is None or cur_row[0] is None:
                    raise ValueError(
                        f"Signal count query returned NULL for {end} — cannot determine signal availability for batch validation"
                    )
                actual_symbols = int(cur_row[0])

                cur.execute("SELECT symbol, MAX(date) FROM signal_quality_scores GROUP BY symbol")
                watermarks = {row[0]: row[1] for row in cur.fetchall()}

            self._batch_context = {
                "end_date": end,
                "bs_signal_count": actual_symbols,
                "watermarks": watermarks,
            }
            logger.debug(f"Batch context: end={end}, bs_signals={actual_symbols}, watermarks={len(watermarks)} symbols")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[BATCH_CONTEXT] Failed to prepare batch context for signal_quality_scores: {e}. "
                "Cannot proceed without end_date and signal availability verification."
            ) from e

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Compute signal quality scores from buy/sell signals and technical confirmation."""
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

        # ISSUE #27 FIX: Fail if buy_sell_daily is blocked
        if self._batch_context and self._batch_context.get("_blocked"):
            error_msg = "Upstream dependency buy_sell_daily is not ready - cannot compute signal_quality_scores"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # ROOT CAUSE #4 FIX: Use cached end_date from batch context (computed once for all symbols)
        # instead of recomputing trading day verification for each symbol.
        if self._batch_context and "end_date" in self._batch_context:
            end = self._batch_context["end_date"]
        else:
            # Fallback if batch context unavailable
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end = now_et.date()

            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                end = end - timedelta(days=1)

            # Fallback: check buy_sell_daily max date if batch context failed
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT MAX(date) FROM buy_sell_daily WHERE signal_type IN ('BUY', 'SELL') AND date <= %s",
                        (end,),
                    )
                    row = cur.fetchone()
                    last_bs_date = row[0] if row is not None and row[0] is not None else None
                    if last_bs_date:
                        last_bs = safe_parse_date(last_bs_date, "buy_sell_daily max date")
                        if last_bs and last_bs < end:
                            end = last_bs
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.debug(f"Could not check buy_sell_daily max date: {e}")

        # On ECS restart the in-memory watermark is empty, so since=None.
        # Use cached watermarks from batch context (loaded once for all symbols).
        # This avoids N+1 per-symbol queries during restart recovery.
        if since is None and self._batch_context and "watermarks" in self._batch_context:
            watermarks = self._batch_context["watermarks"]
            if watermarks.get(symbol):
                parsed = safe_parse_date(watermarks[symbol], f"signal_quality_scores watermark for {symbol}")
                if parsed:
                    since = parsed

        if since is None:
            # On ECS restart, load last 60 days only (not 5 years)
            # This prevents massive data fetch when watermark is empty
            start = end - timedelta(days=60)
        else:
            start = since - timedelta(days=100)

        # Validate buy_sell_daily has run before computing quality scores.
        # buy_sell_daily generates signals only for stocks meeting filter criteria (~500-1500 symbols).
        # Comparing against all active symbols (10,000+) will ALWAYS fail 95% threshold.
        # Instead: require at least 300 buy/sell signals exist for end date.

        # ROOT CAUSE #4 FIX: Use cached signal count from batch context instead of per-symbol query.
        if not self._batch_context:
            raise ValueError("Batch context not available for signal count")
        actual_symbols = self._batch_context.get("bs_signal_count")
        if actual_symbols is None:
            raise ValueError("Signal count not available in batch context")

        # INVESTIGATION: Signal counts dropped 10x on 2026-06-04 (from 1000+ to 134).
        # Root cause: Changes to buy_sell_daily pivot detection logic (commit 5a4c190a4).
        # The pivot detection changed to:
        # 1. Use strict inequality (<) instead of (<=) for high/low pivots
        # 2. Adjust lookback windows from 30-bar to 20-bar (highs) and 10-bar (lows)
        # These changes made the filter more restrictive, reducing signal generation.
        #
        # MONITORING: Instead of silently rejecting all scores when signals are low,
        # we now log signal count metrics for observability. This allows detection of:
        # - Systemic signal generation problems (coverage < 1% of symbols)
        # - Data pipeline issues (missing price or technical data)
        # - Filter tuning side effects (threshold changes)
        #
        # THRESHOLD RATIONALE:
        # - 100 signals = 1% of 10k symbols (baseline for modern signal generation)
        # - Previously was 300 (3% coverage) when seeing 1000+ signals/day
        # - On 2026-06-05, we had 134 signals (1.3%), which was acceptable
        # - If signals drop below 50 (0.5%), something is broken - reject loudly
        # - If signals are 50-100 (0.5-1%), log warning but allow processing
        # - If signals are 100-300 (1-3%), normal operational range
        # - If signals are >300 (3%+), excellent signal generation

        signal_metric = {
            "symbol": symbol,
            "signal_date": end,
            "buy_sell_daily_signal_count": actual_symbols,
            "coverage_pct": round((actual_symbols / 10000) * 100, 2) if actual_symbols >= 0 else None,
        }

        # Hard limit: if signals drop below 50 (<0.5% coverage), reject all scores
        # This indicates a systemic problem (broken pivot logic, missing price data, etc)
        if actual_symbols < 50:
            error_msg = (
                f"CRITICAL signal shortage for {symbol} {end}: "
                f"buy_sell_daily has only {actual_symbols} signals ({signal_metric['coverage_pct']}% coverage). "
                "This indicates a broken data pipeline (missing price_daily, technical_data_daily, or filter misconfiguration). "
                "Cannot safely compute signal_quality_scores."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Warning threshold: if signals drop below 100 (1% coverage), log warning but continue
        # This allows operations to proceed while signaling that signal generation may be suboptimal
        if actual_symbols < 100:
            logger.warning(
                f"[SIGNAL_QUALITY_LOW_COVERAGE] {symbol} {end}: Low signal coverage. "
                f"buy_sell_daily has {actual_symbols} signals ({signal_metric['coverage_pct']}% coverage). "
                "Expected >= 100 signals (1% of symbols). "
                "Possible causes: recent filter tuning, data pipeline lag, or upstream loader incomplete. "
                "Proceeding with signal_quality_scores computation."
            )
        else:
            logger.info(
                f"[SIGNAL_QUALITY_METRICS] {symbol} {end}: "
                f"buy_sell_daily coverage: {actual_symbols} signals ({signal_metric['coverage_pct']}%)"
            )

        try:
            buy_sell_rows = self._fetch_buy_sell_signals(symbol, start, end)
            if not buy_sell_rows:
                raise RuntimeError(
                    f"[SIGNAL_QUALITY] Signal quality scoring failed for {symbol} [{start} to {end}]: "
                    f"No buy/sell signals found. Signal quality assessment is REQUIRED for validating trades. "
                    f"Check that buy_sell_daily table has signals for this symbol or adjust date range."
                )

            # Optional data sources with graceful degradation
            technical_rows = self._fetch_technical_data(symbol, start, end)
            if not technical_rows:
                logger.debug(
                    f"[SIGNAL_QUALITY] Technical data unavailable for {symbol} [{start}-{end}]. "
                    "Proceeding with available data; RSI/MACD will be None."
                )
                technical_rows = []

            trend_rows = self._fetch_trend_data(symbol, start, end)
            if not trend_rows:
                logger.debug(
                    f"[SIGNAL_QUALITY] Trend data unavailable for {symbol} [{start}-{end}]. "
                    "Proceeding with available data; trend_template_score will be 0."
                )
                trend_rows = []

            vcp_rows = self._fetch_vcp_patterns(symbol, start, end)
            if not vcp_rows:
                logger.debug(
                    f"[SIGNAL_QUALITY] VCP pattern data unavailable for {symbol} [{start}-{end}]. "
                    "Proceeding with available data; vcp_pattern_score will be 0."
                )
                vcp_rows = []

            positioning_data = self._fetch_positioning_data(symbol)
            if positioning_data.get("data_unavailable"):
                logger.debug(
                    f"[SIGNAL_QUALITY] Positioning data unavailable for {symbol} "
                    f"({positioning_data.get('reason', 'unknown')}). "
                    "(typical for OTC, preferreds, special securities). Proceeding with available data."
                )

            scores = self._compute_quality_scores(
                symbol,
                buy_sell_rows,
                technical_rows,
                trend_rows,
                vcp_rows,
                positioning_data,
            )
            if not scores:
                raise RuntimeError(
                    f"[SIGNAL_QUALITY] Quality score computation failed for {symbol} [{start} to {end}]: "
                    f"No scores produced despite available buy/sell signals. "
                    f"Signal quality assessment is REQUIRED for validating trades. "
                    f"Check computation logic or validate input data (technical, trend, positioning)."
                )

            # Filter to incremental range using datetime comparison (not string)
            if since is not None:
                since_date = since if isinstance(since, date) else safe_parse_date(since, "score filtering watermark")
                if since_date:
                    # Filter scores by date, handling potential None returns from safe_parse_date
                    filtered_scores = []
                    for s in scores:
                        parsed_date = safe_parse_date(s["date"], "score date filtering")
                        if parsed_date is not None and parsed_date > since_date:
                            filtered_scores.append(s)
                    scores = filtered_scores

            return scores

        except Exception as e:
            # On any exception, log error and create unavailable marker records
            error_reason = str(e)
            logger.error(f"[SIGNAL_QUALITY_ERROR] Failed to compute scores for {symbol}: {error_reason}")

            # Create error marker records for the date range
            # This ensures downstream code sees explicit data_unavailable flags
            error_records = []
            current = start
            while current <= end:
                error_records.append(
                    {
                        "symbol": symbol,
                        "date": current.isoformat(),
                        "base_quality_score": None,
                        "volume_confirmation_score": None,
                        "trend_template_score": None,
                        "distance_from_high_score": None,
                        "institutional_ownership_score": None,
                        "market_stage_score": None,
                        "vcp_pattern_score": None,
                        "distribution_days_score": None,
                        "earnings_proximity_score": None,
                        "composite_sqs": None,
                        "data_completeness": 0.0,
                        "unavailable_components": ["all"],
                        "buy_sell_daily_age_days": None,
                        "technical_data_age_days": None,
                        "trend_template_age_days": None,
                        "data_unavailable": True,
                        "reason": error_reason[:500],  # Truncate to 500 chars
                    }
                )
                current = current + timedelta(days=1)

            return error_records if error_records else None

    def _fetch_buy_sell_signals(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, signal_type FROM buy_sell_daily "
                    "WHERE symbol = %s AND date >= %s AND date <= %s AND signal_type IN ('BUY', 'SELL') ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [{"date": r[0].isoformat(), "signal_type": r[1]} for r in cur.fetchall()]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[SIGNALS] Failed to fetch buy/sell signals for {symbol}: {e}. "
                "Signal quality assessment requires valid signal data."
            ) from e

    def _fetch_technical_data(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        """Fetch technical data."""
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, rsi, macd, macd_signal FROM technical_data_daily "
                    "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [
                    {
                        "date": r[0].isoformat(),
                        "rsi": float(r[1]) if r[1] is not None else None,
                        "macd": float(r[2]) if r[2] is not None else None,
                        "macd_signal": float(r[3]) if r[3] is not None else None,
                    }
                    for r in cur.fetchall()
                ]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[TECHNICAL] Failed to fetch technical data for {symbol}: {e}. "
                "Signal quality requires technical analysis data."
            ) from e

    def _fetch_trend_data(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        """Fetch trend data."""
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, minervini_trend_score, weinstein_stage, percent_from_52w_high FROM trend_template_data "
                    "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [
                    {
                        "date": r[0].isoformat(),
                        "minervini_score": float(r[1]) if r[1] is not None else None,
                        "weinstein_stage": r[2],
                        "percent_from_52w_high": (float(r[3]) if r[3] is not None else None),
                    }
                    for r in cur.fetchall()
                ]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[TREND] Failed to fetch trend data for {symbol}: {e}. "
                "Signal quality assessment requires trend analysis."
            ) from e

    def _ensure_vcp_patterns_populated(self, cur: Any) -> None:
        """Verify VCP patterns table exists (VCP now computed by technical_data_daily loader).

        Consolidation: VCP patterns are now computed by load_technical_data_daily,
        eliminating the separate load_vcp_patterns.py loader.
        """
        try:
            # Check if vcp_patterns table exists
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'vcp_patterns')"
            )
            row = cur.fetchone()
            if row is None or not row[0]:
                logger.warning("[VCP] vcp_patterns table does not exist - will be created when technical_data_daily runs")
                return

            # Check if vcp_patterns has any data
            cur.execute("SELECT COUNT(*) FROM vcp_patterns")
            row = cur.fetchone()
            count = row[0] if row else 0
            if count > 0:
                logger.debug(f"[VCP] vcp_patterns populated with {count} rows (computed by technical_data_daily)")
                return

            logger.info("[VCP] vcp_patterns table empty - will be populated by next technical_data_daily run")
        except psycopg2.DatabaseError as e:
            logger.warning(f"[VCP] Failed to check VCP patterns: {e}")

    def _fetch_vcp_patterns(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        """Fetch VCP patterns."""
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
                # Check if vcp_patterns table exists (ISSUE #10 FIX)
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'vcp_patterns')"
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError("Table existence check query failed")
                table_exists = row[0]
                if not table_exists:
                    raise RuntimeError(
                        "[VCP_TABLE_MISSING] VCP patterns table does not exist. "
                        "Technical data loader (load_technical_data_daily) computes VCP patterns. "
                        "Cannot compute quality scores without VCP pattern data."
                    )

                # Check if vcp_patterns table has been populated for the symbol
                cur.execute(
                    "SELECT COUNT(*) FROM vcp_patterns WHERE symbol = %s AND date >= %s AND date <= %s",
                    (symbol, start, end),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError(f"VCP count query failed for {symbol}")
                count = row[0]
                if count == 0:
                    raise RuntimeError(
                        f"[VCP_NO_DATA] No VCP patterns found for {symbol} in date range {start} to {end}. "
                        f"VCP pattern data is REQUIRED for signal quality scoring. "
                        f"Cannot score signals without VCP trend confirmation data — check vcp_patterns table and data loader."
                    )

                cur.execute(
                    "SELECT date, vcp_strength FROM vcp_patterns "
                    "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [
                    {
                        "date": r[0].isoformat(),
                        "vcp_strength": r[1],
                    }
                    for r in cur.fetchall()
                ]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[VCP] Failed to fetch VCP patterns for {symbol}: {e}. "
                "VCP pattern recognition is authoritative for trend confirmation."
            ) from e

    def _fetch_positioning_data(self, symbol: str) -> dict[str, Any]:
        """Fetch positioning data (optional for many securities).

        Returns:
            dict: With institutional_ownership field if available
            dict: With data_unavailable marker if data missing or database error

        Many OTC, preferred, warrant, and special securities lack institutional ownership data.
        Per CLAUDE.md governance: Return explicit markers instead of None.
        """
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT institutional_ownership FROM positioning_metrics WHERE symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return {"institutional_ownership": float(row[0])}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Failed to fetch positioning data for {symbol}: {e}")
            return {"data_unavailable": True, "reason": f"database_error: {type(e).__name__}"}

        logger.debug(
            f"[SIGNAL_QUALITY] Positioning data unavailable for {symbol} (no record in positioning_metrics). "
            "Common for OTC, preferred stocks, warrants, or special securities lacking institutional ownership tracking."
        )
        return {"data_unavailable": True, "reason": "no_positioning_record"}

    def _compute_quality_scores(
        self,
        symbol: str,
        buy_sell_rows: list[dict[str, Any]],
        technical_rows: list[dict[str, Any]],
        trend_rows: list[dict[str, Any]],
        vcp_rows: list[dict[str, Any]] | None = None,
        positioning_data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Compute quality scores."""
        if not buy_sell_rows:
            raise RuntimeError(
                f"[QUALITY_SCORES] No buy/sell signals available for {symbol}. "
                "Buy/sell signal data is required to compute quality scores. "
                "Upstream loader (load_buy_sell_daily.py) must provide signals first."
            )

        try:
            # Track which optional data sources are available
            # If unavailable, components will be None instead of silently defaulting to 0
            has_vcp_data = bool(vcp_rows)
            has_positioning_data = bool(positioning_data)

            if not has_vcp_data:
                logger.warning(
                    f"[QUALITY_SCORES] VCP patterns unavailable for {symbol} - vcp_pattern_score will be None"
                )
            if not has_positioning_data:
                logger.debug(
                    f"[QUALITY_SCORES] Positioning unavailable for {symbol} - institutional_ownership_score will be None"
                )

            bs_df = pd.DataFrame(buy_sell_rows)
            if bs_df.empty:
                raise RuntimeError(
                    f"[QUALITY_SCORES] Buy/sell dataframe is empty for {symbol}. "
                    "Cannot compute quality scores without buy/sell signal data."
                )
            bs_df["date"] = pd.to_datetime(bs_df["date"])

            tech_df = pd.DataFrame(technical_rows) if technical_rows else pd.DataFrame()
            if not tech_df.empty:
                tech_df["date"] = pd.to_datetime(tech_df["date"])

            trend_df = pd.DataFrame(trend_rows) if trend_rows else pd.DataFrame()
            if not trend_df.empty:
                trend_df["date"] = pd.to_datetime(trend_df["date"])

            vcp_df = pd.DataFrame(vcp_rows) if vcp_rows else pd.DataFrame()
            if not vcp_df.empty:
                vcp_df["date"] = pd.to_datetime(vcp_df["date"])

            # Track max dates from each source for staleness computation
            max_bs_date = bs_df["date"].max() if not bs_df.empty else None
            max_tech_date = tech_df["date"].max() if not tech_df.empty else None
            max_trend_date = trend_df["date"].max() if not trend_df.empty else None

            # Merge with left join to keep all buy/sell rows
            merged = bs_df
            if not tech_df.empty:
                merged = merged.merge(tech_df, on="date", how="left")
            if not trend_df.empty:
                merged = merged.merge(trend_df, on="date", how="left")
            if not vcp_df.empty:
                merged = merged.merge(vcp_df, on="date", how="left")

            institutional_ownership = positioning_data.get("institutional_ownership") if positioning_data else None

            results = []
            for _, row in merged.iterrows():
                # Access Series values using bracket notation (standard pandas idiom, not .get())
                signal_type = row["signal_type"] if "signal_type" in row.index else None
                if not signal_type:
                    continue

                # Use strategy pattern for signal-specific scoring (eliminates OO abuser switch statements)
                from loaders.signal_quality_scorer import get_signal_scorer

                scorer = get_signal_scorer(signal_type)
                base_quality_score = scorer.calculate_base_quality_score()

                # Volume confirmation score (0-20): based on MACD/RSI
                rsi = row["rsi"] if "rsi" in row.index else None
                macd = row["macd"] if "macd" in row.index else None
                macd_signal = row["macd_signal"] if "macd_signal" in row.index else None
                volume_confirmation_score = scorer.calculate_volume_confirmation_score(rsi, macd, macd_signal)

                # Trend template score (0-25): minervini score and stage
                minervini = row["minervini_score"] if "minervini_score" in row.index else None
                weinstein_stage = row["weinstein_stage"] if "weinstein_stage" in row.index else None
                trend_template_score = scorer.calculate_trend_template_score(minervini, weinstein_stage)

                if trend_template_score > 25:
                    logger.warning(
                        f"[SQS_CLAMP] {symbol}: Trend template score clamped from {trend_template_score} to 25. "
                        "This indicates a trend signal stronger than designed threshold."
                    )
                trend_template_score = min(25, trend_template_score)

                # Distance from high score (0-15): closer to 52w high = better
                distance_from_high_score = 0
                pct_from_high = row["percent_from_52w_high"] if "percent_from_52w_high" in row.index else None
                if pct_from_high is not None:
                    try:
                        pct = float(pct_from_high)
                        # Check for NaN and skip if found
                        if not pd.isna(pct):
                            if pct >= -5:  # Within 5% of 52w high
                                distance_from_high_score = 15
                            elif pct >= -10:
                                distance_from_high_score = 12
                            elif pct >= -20:
                                distance_from_high_score = 8
                            elif pct >= -30:
                                distance_from_high_score = 4
                    except (ValueError, TypeError) as e:
                        raise ValueError(
                            f"[SQS] Critical: Cannot parse percent_from_52w_high '{pct_from_high}' for {symbol}. "
                            f"This field is required for accurate signal quality scoring. Raw error: {e}"
                        ) from e

                # Institutional ownership score (0-10) — None if positioning data unavailable
                institutional_ownership_score = None
                if institutional_ownership is not None and not pd.isna(institutional_ownership):
                    if institutional_ownership >= 60:
                        institutional_ownership_score = 10
                    elif institutional_ownership >= 40:
                        institutional_ownership_score = 8
                    elif institutional_ownership >= 20:
                        institutional_ownership_score = 5
                    else:
                        institutional_ownership_score = 2

                # Market stage score (0-10): Weinstein stage 2 and 3 are best
                market_stage_score = 0
                if weinstein_stage is not None and not pd.isna(weinstein_stage):
                    try:
                        stage = int(weinstein_stage)
                        if stage in [2, 3]:
                            market_stage_score = 10
                        elif stage in [1, 4]:
                            market_stage_score = 5
                        else:
                            market_stage_score = 2
                    except (ValueError, TypeError) as e:
                        raise ValueError(
                            f"[SQS] Critical: Cannot parse weinstein_stage '{weinstein_stage}' for {symbol}. "
                            f"This field is required for market stage analysis. Raw error: {e}"
                        ) from e

                # VCP pattern score (0-10) — None if VCP data unavailable
                vcp_pattern_score = None
                vcp_strength = row["vcp_strength"] if "vcp_strength" in row.index else None
                if vcp_strength is not None and not pd.isna(vcp_strength):
                    try:
                        strength = int(vcp_strength)
                        if strength >= 8:
                            vcp_pattern_score = 10
                        elif strength >= 6:
                            vcp_pattern_score = 8
                        elif strength >= 4:
                            vcp_pattern_score = 5
                        else:
                            vcp_pattern_score = 2
                    except (ValueError, TypeError) as e:
                        raise ValueError(
                            f"[SQS] Critical: Cannot parse vcp_strength '{vcp_strength}' for {symbol}. "
                            f"This field is required for VCP pattern analysis. Raw error: {e}"
                        ) from e

                # Distribution days and earnings proximity scores require external data
                # If data unavailable, skip rather than using fake defaults
                distribution_days_score = None
                earnings_proximity_score = None

                # Composite score: only include components with real data (non-None values)
                all_components = {
                    "base_quality": base_quality_score,
                    "volume_confirmation": volume_confirmation_score,
                    "trend_template": trend_template_score,
                    "distance_from_high": distance_from_high_score,
                    "institutional_ownership": institutional_ownership_score,
                    "market_stage": market_stage_score,
                    "vcp_pattern": vcp_pattern_score,
                }
                real_components = [v for v in all_components.values() if v is not None]
                unavailable_components = {k: v for k, v in all_components.items() if v is None}

                composite_sqs = sum(real_components) if real_components else 0
                data_completeness = min(99.99, round((len(real_components) / 7.0) * 100, 2))

                unclamped_composite = int(composite_sqs)
                if unclamped_composite > 100:
                    log_date = row["date"] if "date" in row.index else "unknown"
                    logger.warning(
                        f"[SQS_CLAMP] {symbol} {log_date}: Composite quality score clamped from {unclamped_composite} to 100. "
                        "Score exceeds design range: check individual component contributions."
                    )
                composite_sqs = min(100, unclamped_composite)

                date_val = row["date"] if "date" in row.index else None
                if date_val is not None:
                    date_str = date_val.date().isoformat() if hasattr(date_val, "date") else str(date_val)
                    signal_date = pd.Timestamp(date_str).date()

                    # Compute staleness: how many days old is the underlying data?
                    bs_age = (signal_date - max_bs_date.date()).days if max_bs_date is not None else None
                    tech_age = (signal_date - max_tech_date.date()).days if max_tech_date is not None else None
                    trend_age = (signal_date - max_trend_date.date()).days if max_trend_date is not None else None

                    # CRITICAL: None values indicate missing data. Do NOT convert to 0.
                    # distribution_days_score and earnings_proximity_score are intentionally None
                    # because upstream loaders have not provided these data sources.
                    # Other components (institutional_ownership, vcp_pattern) are None if upstream data unavailable.
                    results.append(
                        {
                            "symbol": symbol,
                            "date": date_str,
                            "base_quality_score": int(base_quality_score),
                            "volume_confirmation_score": int(volume_confirmation_score),
                            "trend_template_score": int(trend_template_score),
                            "distance_from_high_score": int(distance_from_high_score),
                            "institutional_ownership_score": institutional_ownership_score,  # int or None
                            "market_stage_score": int(market_stage_score),
                            "vcp_pattern_score": vcp_pattern_score,  # int or None
                            "distribution_days_score": distribution_days_score,  # None (data unavailable)
                            "earnings_proximity_score": earnings_proximity_score,  # None (data unavailable)
                            "composite_sqs": composite_sqs,
                            "data_completeness": data_completeness,  # % of components available
                            "unavailable_components": list(unavailable_components.keys()),  # Track which are missing
                            "buy_sell_daily_age_days": bs_age,
                            "technical_data_age_days": tech_age,
                            "trend_template_age_days": trend_age,
                            "data_unavailable": False,
                            "reason": None,
                        }
                    )

            return results
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[QUALITY] Failed to compute signal quality scores for {symbol}: {e}. "
                "Quality assessment is authoritative for signal reliability."
            ) from e


def main() -> int:
    """Load signal quality scores.

    Exit codes: 0=success, 1=error, 2=no_data
    """
    parser = argparse.ArgumentParser(description="Load signal quality scores")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=get_default_parallelism("signal_quality_scores"),
        help="Parallel workers",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="daily",
        help="Timeframe (daily/weekly/monthly, ignored for quality scores)",
    )
    parser.add_argument(
        "--asset-class",
        type=str,
        default="stock",
        help="Asset class (stock/etf, ignored for quality scores)",
    )
    args = parser.parse_args()

    try:
        symbols = args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=300)

        logger.info(
            f"Starting signal_quality_scores loader with {len(symbols)} symbols, parallelism={args.parallelism}"
        )

        # VALIDATION: signal_quality_scores is critical path; parallelism should be 2 per steering doc line 44-48
        # If parallelism > 4, log warning as it may cause RDS connection pool exhaustion
        if args.parallelism > 4:
            logger.warning(
                f"[PARALLELISM] signal_quality_scores: parallelism={args.parallelism} exceeds recommended max (2). "
                "This may cause RDS connection pool exhaustion. Check ECS task definition and LOADER_PARALLELISM env var."
            )

        loader = SignalQualityScoresLoader()
        loader.run(symbols, parallelism=args.parallelism)
        logger.info("Signal quality scores load completed")

        # Sync composite_sqs back to buy_sell_daily for consistency
        _sync_scores_to_buy_sell()

        # Log signal generation metrics for observability and trend detection
        _log_signal_metrics()

        logger.info("[LOADER] Signal quality scores load completed successfully. Exit code 0 (SUCCESS).")
        return 0
    except Exception as e:
        logger.error(f"[LOADER] Signal quality scores load failed: {e}. Exit code 1 (ERROR).")
        return 1


def _sync_scores_to_buy_sell() -> None:
    """Sync composite_sqs from signal_quality_scores to buy_sell_daily.signal_quality_score.

    CRITICAL: Only update if BOTH signal_quality_scores has data AND buy_sell_daily is missing it.
    NEVER use COALESCE to fall back to old values — stale data is worse than no data.
    """
    from utils.db.context import DatabaseContext

    try:
        with DatabaseContext("write") as cur:
            # EXPLICIT JOIN: Only update when quality score is computed AND target is NULL
            # No COALESCE fallback — if SQS computed a score, use it; otherwise leave NULL
            cur.execute("""
                UPDATE buy_sell_daily bsd
                SET signal_quality_score = sqs.composite_sqs
                FROM signal_quality_scores sqs
                WHERE bsd.symbol = sqs.symbol
                AND bsd.date = sqs.date
                AND bsd.signal_quality_score IS NULL
                AND sqs.composite_sqs IS NOT NULL
            """)
            rows = cur.rowcount
            if rows > 0:
                logger.info(f"Synced {rows} new signal quality scores to buy_sell_daily (no COALESCE fallback)")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Failed to sync signal quality scores to buy_sell_daily: {e}")
        raise RuntimeError(
            f"[SYNC_FAILURE] Signal quality score sync failed: {e}. "
            "This may cause buy_sell_daily to lack quality scores for newly-computed signals."
        ) from e


def _log_signal_metrics() -> None:
    """Log signal generation metrics for observability and trend detection.

    Captures:
    - Total buy/sell signal count and coverage percentage
    - Quality score distribution (min/max/mean/percentiles)
    - Comparison to baseline (1000+ signals expected historically)

    This enables detection of:
    1. Systemic signal generation problems (10x drops like 2026-06-04)
    2. Data pipeline issues (missing price or technical data)
    3. Filter tuning side effects (threshold changes causing signal reduction)
    4. Seasonal variations (volume changes around earnings, Fed days, etc)
    """

    try:
        with DatabaseContext("read") as cur:
            # Count total signals and get latest date
            cur.execute(
                "SELECT COUNT(*) as total_signals, MAX(date) as latest_date "
                "FROM buy_sell_daily WHERE signal_type IN ('BUY', 'SELL')"
            )
            result = cur.fetchone()
            if result is None:
                logger.info("[SIGNAL_METRICS] No signals found in buy_sell_daily table")
                return

            latest_signal_date = result[1]
            if latest_signal_date is None:
                logger.info("[SIGNAL_METRICS] Signal date is NULL, cannot generate metrics")
                return

            # Count signals on the latest date (today's signal generation)
            cur.execute(
                "SELECT COUNT(*) as daily_signals, COUNT(DISTINCT symbol) as symbols_with_signals "
                "FROM buy_sell_daily WHERE date = %s AND signal_type IN ('BUY', 'SELL')",
                (latest_signal_date,),
            )
            daily_result = cur.fetchone()
            if daily_result is None:
                raise RuntimeError(
                    f"CRITICAL: Signal count query returned None for {latest_signal_date}. "
                    "Query malformed or signal_quality_scores table empty."
                )
            if len(daily_result) < 2:
                raise RuntimeError(
                    f"CRITICAL: Signal count query returned invalid row structure. "
                    f"Expected 2 columns, got {len(daily_result)}."
                )
            if daily_result[0] is None or daily_result[1] is None:
                raise RuntimeError(
                    f"CRITICAL: Signal count query returned NULL values for {latest_signal_date}. "
                    "Cannot calculate signal coverage metrics."
                )
            daily_signals = int(daily_result[0])
            symbols_with_signals = int(daily_result[1])
            if symbols_with_signals == 0:
                logger.critical(
                    f"[LOAD_SIGNAL_QUALITY_SCORES] CRITICAL: Zero symbols have signal quality scores for {latest_signal_date}. "
                    f"Signal quality data may not have loaded. This will block dependent loaders."
                )
                raise RuntimeError(
                    f"Signal coverage check failed: 0 symbols have signal quality scores for {latest_signal_date}. "
                    f"Loader may have failed to compute scores. Cannot calculate signal quality metrics."
                )
            coverage_pct = round((symbols_with_signals / 10000) * 100, 2)

            # Quality score distribution
            cur.execute(
                "SELECT MIN(composite_sqs), MAX(composite_sqs), AVG(composite_sqs), "
                "PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY composite_sqs) as p25, "
                "PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY composite_sqs) as p50, "
                "PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY composite_sqs) as p75 "
                "FROM signal_quality_scores WHERE date = %s AND data_unavailable = false",
                (latest_signal_date,),
            )
            score_result = cur.fetchone()
            if score_result:
                if len(score_result) < 6:
                    raise RuntimeError(
                        f"CRITICAL: Quality score query returned invalid row structure. "
                        f"Expected 6 columns (min/max/avg/p25/p50/p75), got {len(score_result)}."
                    )
                min_score = score_result[0]
                max_score = score_result[1]
                avg_score = round(score_result[2], 2) if score_result[2] is not None else None
                p25 = round(score_result[3], 2) if score_result[3] is not None else None
                p50 = round(score_result[4], 2) if score_result[4] is not None else None
                p75 = round(score_result[5], 2) if score_result[5] is not None else None

                # Determine health status
                if daily_signals < 50:
                    health = "CRITICAL"
                elif daily_signals < 100:
                    health = "WARNING"
                elif daily_signals < 300:
                    health = "NORMAL"
                else:
                    health = "EXCELLENT"

                logger.info(
                    f"[SIGNAL_METRICS] {latest_signal_date} - Health: {health} | "
                    f"Signals: {daily_signals} ({coverage_pct}% coverage) | "
                    f"Quality Scores: min={min_score}, p25={p25}, median={p50}, p75={p75}, max={max_score}, avg={avg_score}"
                )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(
            f"[SIGNAL_METRICS] Failed to log signal generation metrics to database: {e}. "
            f"Performance metrics will not be recorded for this batch. "
            f"Check database connectivity and signal_metrics table."
        )


if __name__ == "__main__":
    sys.exit(main())
