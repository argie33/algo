"""PHASE 7 helper: build candidate dicts from buy_sell_daily/stock_scores query rows, and
persist computed signal_quality_scores back to buy_sell_daily.

Pure extract-method split out of algo/orchestrator/phase7_signal_generation.py's
`_get_candidates_from_buysell()` - no computation, validation, or persistence logic changed.
Kept in a separate module because neither function references `compute_signal_quality_components`
(the shared signal-quality-scoring formula) nor the candidate-ranking SQL, so moving them here
does not affect either of those whitebox regression tests:
- tests/unit/test_phase7_candidate_ranking_tiebreak_20260901.py (inspects
  `_get_candidates_from_buysell`'s own source for the ranking query's tiebreak clause - that
  query stays inline in `_get_candidates_from_buysell` itself, not here)
- tests/unit/test_signal_quality_score_single_source_of_truth_20260820.py (counts
  `compute_signal_quality_components` occurrences in phase7_signal_generation.py's module
  source - the inline scorer that calls it, `_score_candidates_inline`, stays in that file)
"""

import logging
import zlib
from typing import Any

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def _build_candidates_from_rows(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """Parse+validate raw SQL rows from `_get_candidates_from_buysell`'s ranking query into
    candidate dicts. Verbatim extraction of that function's former per-row loop body - no
    validation, fallback, or field mapping changed.
    """
    from algo.orchestrator.phase7_signal_generation import _compute_risk_score

    candidates = []
    for r in rows:
        # CRITICAL: Verify query returned all 20 expected columns before unpacking (indices 0-19)
        if len(r) < 20:
            logger.error(
                f"[PHASE 7 CRITICAL] Query returned {len(r)} columns instead of expected 20. "
                f"Schema mismatch detected. Skipping malformed row."
            )
            continue

        symbol = r[0]

        # CRITICAL FIX BLOCKER #6: Verify spinoff filtering worked
        # SQL query filters data_unavailable = false, but double-check at runtime
        # If a symbol with data_unavailable=True somehow makes it here, it's a critical bug
        # because that symbol's metrics are incomplete (spinoff/delisted/etc)
        # Composite score guaranteed by INNER JOIN with stock_scores (non-null check in SQL WHERE)
        if r[1] is None:
            raise ValueError(
                f"[PHASE 7] {symbol}: composite_score is NULL - "
                "INNER JOIN to stock_scores and WHERE ss.composite_score IS NOT NULL guarantees non-null"
            )
        composite = float(r[1])

        # Close guaranteed by LATERAL price_daily join
        if r[6] is None:
            raise ValueError(
                f"[PHASE 7] {symbol}: close price is NULL - price_daily lateral join guarantees latest close"
            )
        close = float(r[6])

        # Signal strength guaranteed by WHERE clause (bsd.strength IS NOT NULL)
        if r[15] is None:
            raise ValueError(f"[PHASE 7] {symbol}: signal_strength is NULL - WHERE clause guarantees non-null strength")
        raw_strength = float(r[15])

        # Validate signal has complete scoring
        quality_score = float(r[2]) if r[2] is not None else None
        growth_score = float(r[3]) if r[3] is not None else None
        momentum_score = float(r[4]) if r[4] is not None else None
        rs_percentile = float(r[5]) if r[5] is not None else None

        # CRITICAL: Most core signal quality metrics should be present
        # If >2 of these are missing (only 1-2 available), signal quality is severely degraded
        # Incomplete signals indicate upstream data quality issues (stock_scores incomplete)
        missing_scores = sum(
            [quality_score is None, growth_score is None, momentum_score is None, rs_percentile is None]
        )
        if missing_scores > 2:
            error_msg = (
                f"[PHASE 7 CRITICAL] {symbol}: Signal generated with severely incomplete scoring data. "
                f"Missing {missing_scores}/4 component scores (only {4 - missing_scores} available): "
                f"quality={quality_score}, growth={growth_score}, momentum={momentum_score}, rs={rs_percentile}. "
                f"Fail-fast: cannot trade on signals with <50% scoring quality assessment. "
                f"Indicates stock_scores loader is incomplete for this symbol. "
                f"Check: (1) stock_scores coverage for {symbol}, "
                f"(2) quality_metrics/growth_metrics/momentum_metrics/positioning_metrics loaders, "
                f"(3) data_completeness threshold in signal query."
            )
            logger.critical(error_msg)
            raise ValueError(error_msg)
        elif missing_scores > 0:
            logger.warning(
                f"[PHASE 7] {symbol}: Signal generated with incomplete scoring data "
                f"(missing {missing_scores}/4 components). "
                f"quality={quality_score}, growth={growth_score}, momentum={momentum_score}, rs={rs_percentile}. "
                f"Position sizing should account for reduced signal quality."
            )

        # _compute_risk_score() intentionally raises ValueError for a single candidate
        # that fails the extreme-volatility gate (ATR > 18% of close) or lacks ATR(14)
        # history (e.g. a recent IPO) - it's a per-symbol tradability filter, not a
        # data-integrity guarantee. Letting that exception escape this loop previously
        # aborted the ENTIRE candidate fetch (caught by the function's outer except and
        # re-raised as a RuntimeError that halts all of Phase 7), so on any day where one
        # candidate happened to be unusually volatile, ZERO signals were generated instead
        # of just excluding that one stock - the exact "some days halt for no clear system
        # reason" pattern this was meant to prevent. Skip just this candidate instead.
        try:
            risk_score = _compute_risk_score(float(r[10]) if r[10] is not None else None, close)
        except ValueError as e:
            logger.info(f"[PHASE 7] {symbol}: excluded from candidates - {e}")
            continue

        # CRITICAL FIX 2026-08-05: Skip stocks with missing rs_percentile
        # Phase 8 requires rs_percentile for entry validation. Passing signals with
        # missing rs_percentile causes Phase 8 to reject them as 'processing_error'.
        # Better to filter here in Phase 7 so only fully-qualified signals reach Phase 8.
        if rs_percentile is None:
            logger.warning(
                f"[PHASE 7] {symbol}: Skipping candidate - missing rs_percentile "
                f"(from positioning_metrics table). Position sizing requires relative strength validation."
            )
            continue

        candidates.append(
            {
                "symbol": symbol,
                "composite_score": composite,
                "quality_score": quality_score,
                "growth_score": growth_score,
                "momentum_score": momentum_score,
                "rs_percentile": rs_percentile,
                "close": close,
                "high": float(r[7]) if r[7] is not None else None,
                "low": float(r[8]) if r[8] is not None else None,
                "sma_50": float(r[9]) if r[9] is not None else None,
                "atr_14": float(r[10]) if r[10] is not None else None,
                "entry_price": close,
                "signal_strength": raw_strength,
                "signal_quality_score": None,  # CRITICAL: Initialize to None to ensure key exists. Will be set by inline scorer.
                "trend_template_score": None,  # CRITICAL: Initialize to None. Will be set by inline scorer if available.
                "base_quality": None,  # CRITICAL: Initialize to None. Will be set by inline scorer after scoring completes.
                "sector": r[11],
                "industry": r[12],
                "buylevel": float(r[13]) if r[13] is not None else None,
                "stoplevel": float(r[14]) if r[14] is not None else None,
                "volume_surge_pct": float(r[16]) if len(r) > 16 and r[16] is not None else None,
                "market_stage": r[17] if len(r) > 17 and r[17] is not None else "unknown",
                "signal_date": str(r[18]) if len(r) > 18 and r[18] is not None else None,
                "base_type": r[19] if len(r) > 19 and r[19] is not None else None,
                "risk_score": risk_score,
            }
        )

    return candidates


def _persist_signal_quality_scores(candidates: list[dict[str, Any]]) -> None:
    """Write computed signal_quality_scores back to buy_sell_daily so that backtest and other
    systems can access them. Only writes non-NULL scores.

    Verbatim extraction of `_get_candidates_from_buysell`'s former write-back block.
    """
    scores_to_write = [
        (c.get("signal_quality_score"), c.get("signal_quality_score"), c.get("symbol"), c.get("signal_date"))
        for c in candidates
        if c.get("symbol") and c.get("signal_date") and c.get("signal_quality_score") is not None
    ]

    if scores_to_write:
        try:
            with DatabaseContext("write") as cur_write:
                # CRITICAL FIX: Use non-blocking advisory lock to prevent concurrent Phase 7 runs from race condition
                # Multiple orchestrator instances may run concurrently in AWS Lambda/ECS.
                # OPTIMIZATION: Use pg_try_advisory_lock (non-blocking) instead of pg_advisory_lock (blocking)
                # - Blocking lock causes 7+ halts when Phase 7 runs 3x daily and lock contention occurs
                # - Non-blocking lock fails fast: if held, skip update and next Phase 7 run handles it
                # - Prevents timeouts that halt the orchestrator unnecessarily
                # Advisory lock ID: deterministic hash of 'phase7_signal_scores'.
                # BUG FIX: previously `hash('phase7_signal_scores') % (2**31)` - Python
                # randomizes str hashing per-process by default (PYTHONHASHSEED, unset
                # anywhere in this repo's deploy config), so concurrent Phase 7 instances
                # (the exact multi-instance scenario this lock exists for) each computed a
                # DIFFERENT lock_id, silently defeating the race-condition protection.
                # zlib.crc32 is not seed-randomized, matching the fixed-constant pattern
                # used elsewhere for the same reason (see PORTFOLIO_SNAPSHOT_LOCK_ID).
                lock_id = zlib.crc32(b"phase7_signal_scores") % (2**31)
                lock_acquired = False

                try:
                    cur_write.execute(f"SELECT pg_try_advisory_lock({lock_id})")
                    result = cur_write.fetchone()
                    lock_acquired = result[0] if result and result[0] is not None else False

                    if lock_acquired:
                        logger.debug("[PHASE 7] Acquired non-blocking advisory lock for signal quality score updates")
                    else:
                        logger.info(
                            "[PHASE 7] Lock held by concurrent Phase 7 instance, skipping score updates (next run will handle)"
                        )
                except Exception as lock_err:
                    logger.warning(f"[PHASE 7] Could not acquire advisory lock: {lock_err}. Continuing without lock.")

                try:
                    # Only proceed with updates if lock was acquired
                    if lock_acquired:
                        failed_writes = []
                        for sqs, entry_sqs, symbol, signal_date in scores_to_write:
                            cur_write.execute(
                                """
                                UPDATE buy_sell_daily
                                SET signal_quality_score = %s, entry_quality_score = %s
                                WHERE symbol = %s AND date = %s
                                """,
                                (sqs, entry_sqs, symbol, signal_date),
                            )
                            if cur_write.rowcount == 0:
                                failed_writes.append(f"{symbol} on {signal_date}")

                        if failed_writes:
                            raise RuntimeError(
                                f"[PHASE 7 CRITICAL] Signal quality score persistence failed for {len(failed_writes)} symbols: {', '.join(failed_writes)}. "
                                f"Expected rows were not found in buy_sell_daily table. This indicates a data integrity issue that must be investigated."
                            )
                        logger.info(f"[PHASE 7] Wrote {len(scores_to_write)} signal_quality_scores to buy_sell_daily")
                    else:
                        logger.info(
                            f"[PHASE 7] Skipping {len(scores_to_write)} score updates (lock held by concurrent run)"
                        )
                finally:
                    # Release advisory lock if acquired
                    if lock_acquired:
                        try:
                            cur_write.execute(f"SELECT pg_advisory_unlock({lock_id})")
                            logger.debug(
                                "[PHASE 7] Released non-blocking advisory lock after signal quality score updates"
                            )
                        except Exception as unlock_err:
                            logger.warning(
                                f"[PHASE 7] Could not release advisory lock: {unlock_err}. Lock will auto-release on connection close."
                            )
        except Exception as write_e:
            raise RuntimeError(
                f"[PHASE 7] Failed to write signal quality scores to buy_sell_daily: {write_e}. "
                f"Cannot proceed with phase completion without persisting signal data."
            ) from write_e
