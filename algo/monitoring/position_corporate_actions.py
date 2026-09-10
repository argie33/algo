"""Corporate-actions detection/adjustment methods for PositionMonitor, extracted from
algo/monitoring/position_monitor.py (2026-09-05, file-size ratchet: that file is a Tier-2
bloater flagged for decomposition). Bodies are verbatim, no logic changed - mixed into
PositionMonitor, which still defines the `config` instance attribute these methods read via
`self`.

`DatabaseContext`/`requests`/`time` are accessed via the position_monitor module object at
call time (not imported by name here) because several existing tests patch
`algo.monitoring.position_monitor.DatabaseContext`/`.requests`/`.time` expecting that to
affect these methods - a plain import here would silently stop seeing those patches.
`algo.monitoring.position_monitor` itself imports this module at load time, so the reference
is resolved lazily (inside the method bodies, not at import time) to avoid a circular-import
failure.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

import algo.monitoring.position_monitor as _pm
from algo.config.api_endpoints import get_alpaca_base_url
from algo.config.credential_manager import get_credential_manager
from algo.monitoring.position_monitor import PositionValidationError

logger = logging.getLogger(__name__)


class CorporateActionsMixin:
    """Corporate-action (stock split) detection and position-quantity reconciliation methods
    for PositionMonitor. Not usable standalone - relies on the `config` instance attribute
    defined on PositionMonitor itself.
    """

    config: Any

    def check_corporate_actions(self) -> list[dict[str, Any]]:
        """Phase 6.1: Detect stock splits and corporate actions.

        Compares Alpaca qty to DB qty. If different and greater than 20%,
        likely a stock split. Adjusts position qty and recalculates stop loss.

        Returns:
            list of adjustments made
        """
        adjustments: list[dict[str, Any]] = []
        ctx = _pm.DatabaseContext("write")  # type: ignore[attr-defined]
        with ctx as cur:
            # trade_ids_arr added 2026-09-05 (real-money-readiness audit): this SELECT used to
            # omit it entirely, so both call sites below always passed a hardcoded None down
            # to _apply_split_adjustment - meaning a real stock split NEVER rescaled
            # algo_trades.entry_price/stop_loss_price/target_N_price (only algo_positions), the
            # exact gap _apply_split_adjustment's own docstring/warning already describes but
            # that nothing upstream ever supplied real data to close.
            cur.execute("""
                SELECT ap.id, ap.symbol, ap.quantity, ap.stop_loss_price,
                       ap.avg_entry_price AS entry_price, ap.trade_ids_arr
                FROM algo_positions ap
                WHERE ap.status = 'open'
            """)
            positions = cur.fetchall()

            alpaca_base_url, alpaca_key, alpaca_secret = self._get_alpaca_creds()

            for pos_id, symbol, db_qty, db_stop, _entry_price, trade_ids_arr in positions:
                try:
                    alpaca_pos = self._fetch_alpaca_position(alpaca_base_url, alpaca_key, alpaca_secret, symbol)
                    alpaca_qty = None if alpaca_pos is None else int(alpaca_pos["qty"])
                    self._handle_qty_variance(
                        cur,
                        pos_id,
                        symbol,
                        db_qty,
                        db_stop,
                        alpaca_qty,
                        trade_ids_arr,
                        adjustments,
                        alpaca_pos,
                    )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    error_msg = (
                        f"Corporate action detection failed for {symbol}: Database error during qty variance handling. "
                        f"Cannot proceed without complete position verification. {e}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e
                except RuntimeError as e:
                    # FIX (2026-09-07 real-money-readiness audit): a genuine per-symbol failure
                    # (malformed Alpaca response, an unexpected non-200/404 status, missing qty
                    # field) used to propagate out of this loop entirely - a DB error is a
                    # systemic problem worth halting the whole cycle for (caught above), but one
                    # symbol's own API oddity is not, and must not block split-detection/
                    # reconciliation for every OTHER open position in the same run.
                    logger.error(
                        f"[CORP_ACTION] {symbol}: skipping this symbol's corporate-action check "
                        f"after an unexpected error, continuing with remaining positions: {e}"
                    )

            return adjustments

    def _get_alpaca_creds(self) -> tuple[str, str, str]:
        """Retrieve Alpaca credentials, raise if unavailable."""
        alpaca_base_url = get_alpaca_base_url(self.config.get("execution_mode"))
        try:
            cm = get_credential_manager()
            creds = cm.get_alpaca_credentials()
            alpaca_key = creds.get("key")
            alpaca_secret = creds.get("secret")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Could not retrieve Alpaca credentials: {e}")
            alpaca_key = None
            alpaca_secret = None

        if not alpaca_key or not alpaca_secret:
            raise RuntimeError("Alpaca credentials unavailable - cannot detect corporate actions. Halted.")
        return alpaca_base_url, alpaca_key, alpaca_secret

    def _fetch_alpaca_position(
        self, alpaca_base_url: str, alpaca_key: str, alpaca_secret: str, symbol: str
    ) -> dict[str, Any] | None:
        """Fetch the raw position payload from Alpaca API.

        Returns None when Alpaca has no position for this symbol (404) - matching the
        established 200/204/404 pattern already used elsewhere in this codebase for the
        identical endpoint (position_order_management.py:332, order_manager.py:1153) - a
        symbol that closed, was delisted, or was renamed by a merger/ticker change legitimately
        has no position at the broker, not a data-integrity failure. FIX (2026-09-07 real-money-
        readiness audit): this used to raise RuntimeError on ANY non-200, including 404, making
        _handle_qty_variance's own `alpaca_qty == 0` "position closed at broker" branch
        unreachable in practice and, worse, propagating an uncaught RuntimeError out of
        check_corporate_actions's per-symbol loop (only psycopg2 errors were caught there) -
        one delisted/renamed symbol could silently abort corporate-action detection, including
        split-adjustment, for every OTHER open position in the same cycle.

        Raises:
            RuntimeError: On any other non-200 status, or if qty is missing from a 200 response
                (fail-fast for data integrity).
        """
        url = f"{alpaca_base_url}/v2/positions/{symbol}"
        headers = {
            "APCA-API-KEY-ID": alpaca_key,
            "APCA-API-SECRET-KEY": alpaca_secret,
        }
        try:
            timeout = int(self.config["api_request_timeout_seconds"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}") from e

        # RETRY (found 2026-07-28, same bug class as order_manager.py's send/cancel fixes and
        # this file's own _cancel_on_alpaca): a transient 429/503 used to raise immediately,
        # halting corporate-action detection for the whole cycle over a retryable blip.
        max_attempts = 3
        resp = None
        for attempt in range(max_attempts):
            try:
                resp = _pm.requests.get(url, headers=headers, timeout=timeout)
            except (_pm.requests.Timeout, _pm.requests.ConnectionError) as e:
                if attempt < max_attempts - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[CORP_ACTION] {symbol}: Alpaca {type(e).__name__} - transient, retrying in "
                        f"{wait_time}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    _pm.time.sleep(wait_time)
                    continue
                raise RuntimeError(f"Alpaca API unreachable for {symbol} after {max_attempts} attempts: {e}") from e
            if resp.status_code in (429, 503) and attempt < max_attempts - 1:
                wait_time = 2**attempt
                logger.warning(
                    f"[CORP_ACTION] {symbol}: Alpaca {resp.status_code} - transient, retrying in "
                    f"{wait_time}s (attempt {attempt + 1}/{max_attempts})"
                )
                _pm.time.sleep(wait_time)
                continue
            break

        assert resp is not None, "Response should be set after loop"
        if resp.status_code == 404:
            logger.info(f"[CORP_ACTION] {symbol}: no position at Alpaca (404) - treating as closed at broker.")
            return None
        if resp.status_code != 200:
            raise RuntimeError(f"Alpaca API returned {resp.status_code} for {symbol}")

        try:
            alpaca_pos = resp.json()
        except (ValueError, Exception) as e:
            raise RuntimeError(f"Invalid JSON response from Alpaca: {e}") from e

        if "qty" not in alpaca_pos or alpaca_pos["qty"] is None:
            raise RuntimeError(
                f"Alpaca response for {symbol} missing qty field (malformed response). "
                f"Response: {alpaca_pos}. Cannot verify position quantity - halting corporate action check."
            )
        return dict(alpaca_pos)

    def _handle_qty_variance(
        self,
        cur: PsycopgCursor[Any],
        pos_id: int,
        symbol: str,
        db_qty: int,
        db_stop: float,
        alpaca_qty: int | None,
        trade_ids_arr: list[int] | None,
        adjustments: list[dict[str, Any]],
        alpaca_pos: dict[str, Any] | None = None,
    ) -> None:
        """Handle quantity changes between DB and Alpaca.

        alpaca_qty is None specifically means Alpaca has NO position for this symbol at all
        (404). A real qty of 0 never reaches this branch by a different route: this whole
        method only runs against rows this query already filtered to `status = 'open'`, and
        our own exit path (executor_exit_handler.py) always flips status to 'closed' as part
        of the same transaction that reduces quantity to 0 - so a position landing here as
        'open' in our DB while Alpaca shows qty 0/404 was NOT closed by an exit WE recorded.
        It's an unexplained broker-side discrepancy: possibly a genuine liquidation, but
        _fetch_alpaca_qty's own docstring notes 404 is indistinguishable from a ticker
        rename/merger, where the real position still exists at the broker under a new symbol
        - fabricating a P&L and marking this 'closed' as if it were a routine, self-initiated
        exit would silently orphan that still-open (and possibly still-protected-under-the-
        old-symbol-only) position from all further stop/exit monitoring. FIX (2026-09-09
        real-money-readiness audit): treat this as requiring human confirmation, the same way
        exit_engine.py's delisted/unavailable branch refuses to compute P&L off a price it
        can't trust, rather than a routine close.
        """
        if alpaca_qty is None or alpaca_qty == 0:
            cur.execute(
                """UPDATE algo_positions SET status = 'closed', closed_at = CURRENT_TIMESTAMP,
                   exit_reason = %s,
                   profit_loss_dollars = NULL,
                   unrealized_pnl = NULL
                   WHERE id = %s""",
                ("broker_position_not_found|requires_manual_review", pos_id),
            )
            adjustments.append(
                {
                    "symbol": symbol,
                    "action": "POSITION_CLOSED_AT_ALPACA",
                    "db_qty": db_qty,
                    "alpaca_qty": alpaca_qty,
                }
            )
            try:
                from algo.reporting.notifications import notify

                notify(
                    "critical",
                    title="Position closed at broker without a matching exit - verify not a rename/merger",
                    message=(
                        f"{symbol} (position id {pos_id}, {db_qty} shares) showed no position at "
                        f"Alpaca (404/qty=0) despite being 'open' in our DB with no exit we recorded. "
                        f"Marked closed with NO computed P&L (unknown - do not trust current_price for "
                        f"this). This can be a genuine liquidation, OR a ticker rename/merger where the "
                        f"real position still exists at the broker under a NEW symbol and is no longer "
                        f"being monitored/protected by this system under either symbol. Verify at Alpaca "
                        f"directly before treating this as resolved."
                    ),
                )
            except Exception as notify_err:
                logger.critical(
                    f"[CORP_ACTION] Failed to alert on unexplained broker-side close for {symbol} "
                    f"(position id {pos_id}): {notify_err}",
                    exc_info=True,
                )
            return

        if alpaca_qty == db_qty:
            # FIX (2026-09-09 real-money-readiness audit, spinoff-handling gap): a corporate
            # action that doesn't change share count (a spinoff distributes NEW shares of a
            # different symbol, it doesn't change how many shares of THIS symbol you hold) used
            # to fall straight through this equal-qty branch with zero investigation - the qty
            # check above is qty-only by construction, so it can never see a spinoff coming.
            # The position would keep being monitored at its stale pre-spinoff entry_price/
            # stop/targets indefinitely, with no alert, until (if ever) the resulting price gap
            # happened to breach the stop - and even then, only exit_engine.py's `_gap_risk_note`
            # would flag it, and only in an exit's own reason string after the fact. Detect the
            # same signature exit_engine.py already treats as gap risk (see its
            # `_GAP_RISK_PCT_THRESHOLD` docstring: "a real fix needs a proper corporate-actions
            # data feed... until then, annotate, don't alter") one layer earlier, right here in
            # the daily corp-actions pass, using price fields Alpaca already returned in the
            # same position lookup above - no new API call or data feed required.
            self._check_price_gap_anomaly(cur, pos_id, symbol, alpaca_pos, adjustments)
            return

        if db_qty <= 0:
            raise RuntimeError(
                f"[POSITION_MONITOR] Cannot calculate quantity variance for {symbol} (db_qty={db_qty}). "
                f"Position has invalid or missing quantity in database. "
                f"Data integrity check failed - reconciliation cannot proceed without valid position data."
            )
        qty_change_pct = abs(alpaca_qty - db_qty) / db_qty * 100
        if qty_change_pct <= 20:
            return

        # FIX (2026-09-09 real-money-readiness audit): a >20% qty mismatch used to be treated
        # as "likely a stock split" with zero corroboration against an actual split ratio -
        # ANY other cause of a large qty divergence (a mistaken manual broker-side share
        # adjustment, a reconciliation bug elsewhere, a partial-fill accounting error) would
        # be misclassified as a split and would actively CORRUPT good entry/stop/target prices
        # by dividing them by a bogus ratio (e.g. a mistaken 30%-share manual reduction at the
        # broker would get "corrected" by dividing the real stop-loss price by 0.7, moving a
        # working stop to the wrong level on a real position). Reuse the same canonical-ratio
        # matcher the offline loader/tick_validator use to detect splits from price data, so a
        # qty change is only ever treated as a split here if it actually snaps to a real split
        # ratio (2, 3, 4, 5, 10, 1/2, 1/3, ...) within tolerance - anything else is an
        # unexplained mismatch that gets a critical alert for manual review instead of a
        # silent price rewrite.
        from loaders.technical_indicators import _match_split_ratio

        observed_ratio = alpaca_qty / db_qty
        canonical_ratio = _match_split_ratio(observed_ratio)
        if canonical_ratio is None:
            adjustments.append(
                {
                    "symbol": symbol,
                    "action": "QTY_MISMATCH_NOT_A_SPLIT|requires_manual_review",
                    "db_qty": db_qty,
                    "alpaca_qty": alpaca_qty,
                }
            )
            try:
                from algo.reporting.notifications import notify

                notify(
                    "critical",
                    title="Unexplained quantity mismatch does not match any known split ratio - verify manually",
                    message=(
                        f"{symbol} (position id {pos_id}) shows {db_qty} shares in our DB vs "
                        f"{alpaca_qty} at Alpaca ({qty_change_pct:.1f}% change), but the ratio "
                        f"{observed_ratio:.4f} doesn't match any canonical stock-split ratio. NOT "
                        f"treating this as a split and NOT rescaling entry/stop/target prices, since "
                        f"doing so on a non-split cause would corrupt real risk-protection prices. "
                        f"Verify at Alpaca directly (manual adjustment, reconciliation error, partial "
                        f"fill discrepancy, or a genuine but unusual split) before resolving."
                    ),
                )
            except Exception as notify_err:
                logger.critical(
                    f"[CORP_ACTION] Failed to alert on unexplained qty mismatch for {symbol} "
                    f"(position id {pos_id}): {notify_err}",
                    exc_info=True,
                )
            return

        self._apply_split_adjustment(cur, pos_id, symbol, db_qty, db_stop, alpaca_qty, trade_ids_arr, adjustments)

    def _check_price_gap_anomaly(
        self,
        cur: PsycopgCursor[Any],
        pos_id: int,
        symbol: str,
        alpaca_pos: dict[str, Any] | None,
        adjustments: list[dict[str, Any]],
    ) -> None:
        """Flag (never auto-adjust) an unexplained overnight price gap on a position whose
        share count didn't change - the one signature a spinoff, special cash-in-lieu
        distribution, or similar corporate action leaves behind that qty-based detection above
        can never see (see the FIX comment at this method's call site). Deliberately
        annotation-only, same philosophy as exit_engine.py's `_gap_risk_note`: we have no
        corporate-actions data feed to confirm the cause or compute a real cost-basis/price
        adjustment, and guessing would risk corrupting a correct entry/stop/target on what
        could just as easily be an ordinary large move (earnings, litigation, M&A news) instead
        of a corporate action. This only buys earlier visibility - a human can check Alpaca's
        account activity for a spinoff/distribution and manually correct cost basis/stop before
        it matters, rather than finding out weeks later (or not at all, if the gap never
        happens to breach the stop).

        Silently returns if `alpaca_pos` lacks usable current_price/lastday_price - those
        fields aren't part of `_fetch_alpaca_position`'s own required-fields contract (only
        `qty` is), so a payload shape change elsewhere must not turn this best-effort check
        into a new failure mode for corporate-action detection as a whole.
        """
        if not alpaca_pos:
            return
        try:
            current_price = float(alpaca_pos["current_price"])
            lastday_price = float(alpaca_pos["lastday_price"])
        except (KeyError, TypeError, ValueError):
            return
        if lastday_price <= 0:
            return

        from algo.trading.exit_engine import _GAP_RISK_PCT_THRESHOLD

        pct_change = (lastday_price - current_price) / lastday_price
        if abs(pct_change) < _GAP_RISK_PCT_THRESHOLD:
            return

        direction = "drop" if pct_change > 0 else "rise"
        adjustments.append(
            {
                "symbol": symbol,
                "action": "UNEXPLAINED_PRICE_GAP|requires_manual_review",
                "lastday_price": lastday_price,
                "current_price": current_price,
                "pct_change": round(pct_change * 100, 2),
            }
        )
        details = (
            f"{symbol} (position id {pos_id}): {abs(pct_change) * 100:.1f}% overnight {direction} "
            f"(${lastday_price:.2f} -> ${current_price:.2f}) with NO quantity change at the broker. "
            f"Not treated as a split (qty unchanged) and NOT adjusting entry/stop/target prices - "
            f"verify at Alpaca account activity for a spinoff, special cash-in-lieu distribution, or "
            f"other corporate action before assuming this reflects genuine trading performance. If "
            f"a spinoff distributed new shares, they should also surface separately as an untracked "
            f"broker position (see algo_untracked_positions)."
        )
        cur.execute(
            "INSERT INTO algo_audit_log (action_type, action_date, details, severity) VALUES (%s, %s, %s, %s)",
            ("CORPORATE_ACTION_PRICE_GAP", datetime.now(timezone.utc), details, "CRITICAL"),
        )
        logger.critical(f"[CORP_ACTION] {details}")
        try:
            from algo.reporting.notifications import notify

            notify(
                "critical",
                title="Unexplained overnight price gap with no quantity change - verify for corporate action",
                message=details,
            )
        except Exception as notify_err:
            logger.critical(
                f"[CORP_ACTION] Failed to alert on unexplained price gap for {symbol} "
                f"(position id {pos_id}): {notify_err}",
                exc_info=True,
            )

    def _apply_split_adjustment(
        self,
        cur: PsycopgCursor[Any],
        pos_id: int,
        symbol: str,
        db_qty: int,
        db_stop: float,
        alpaca_qty: int,
        trade_ids_arr: list[int] | None,
        adjustments: list[dict[str, Any]],
    ) -> None:
        """Apply stock split adjustment to quantity, stop loss, and every other
        price-scale field that a split invalidates.

        CRITICAL (2026-07-27): this used to update ONLY algo_positions.quantity and
        current_stop_price. But the exit engine's R-multiple math (risk_per_share =
        entry_price - init_stop, r_multiple = (cur_price - entry_price) / risk_per_share)
        and every T1/T2/T3 profit-target comparison read entry_price/stop_loss_price/
        target_N_price from algo_trades (see position_monitor._evaluate_position's join),
        not algo_positions - and those were never adjusted. After a real split, cur_price
        reflects the new post-split scale while entry_price/targets stayed at the old
        pre-split scale, so r_multiple and every T1/T2/T3 check silently computed against
        mismatched price scales for the rest of the position's life: profit targets could
        become effectively unreachable (stale targets far above the rescaled price) or
        R-multiple-gated exits (first-red-day 2.5R+, climax-exhaustion 5R+) could fire on
        garbage ratios. Also corrupts unrealized_pnl_pct reporting (uses entry_price the
        same way). Fixed by scaling every price-scale column - on both algo_trades (the
        actual source the exit engine reads) and algo_positions (cache/display columns) -
        by the same split_ratio used for the stop, not just current_stop_price.

        Raises:
            RuntimeError: If stop_loss is missing when stock split detected. Missing
            stop loss means position has no protection - cannot silently proceed.
        """
        if db_qty <= 0:
            raise PositionValidationError(
                f"CRITICAL: Database position quantity invalid ({db_qty}) - cannot calculate split ratio. "
                f"Position data corruption detected for {symbol}."
            )
        # CRITICAL (2026-07-21 financial-integrity audit): this stop-loss adjustment feeds
        # current_stop_price - a real value controlling actual stop-loss risk protection -
        # but was computed via chained plain-float division (alpaca_qty/db_qty then db_stop/
        # split_ratio) with no Decimal quantization before the DB write. Split ratios aren't
        # guaranteed to be clean floats (any share-count discrepancy from prior partial-fill
        # corrections makes the ratio non-round), so this could silently write an
        # unquantized, imprecise stop price. Same bug class already fixed in order_manager.py
        # and exposure_policy.py this session - a price about to control real trading
        # behavior, computed without Decimal.
        split_ratio_dec = Decimal(str(alpaca_qty)) / Decimal(str(db_qty))

        if not db_stop:
            raise RuntimeError(
                f"STOCK SPLIT DETECTED for {symbol} but current_stop_price is NULL in database. "
                f"Cannot adjust stop loss - position protection broken. "
                f"Manual intervention required to restore stop loss protection before trading continues."
            )

        new_stop_dec = (Decimal(str(db_stop)) / split_ratio_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        new_stop = float(new_stop_dec)
        ratio_f = float(split_ratio_dec)
        # BUG FOUND 2026-08-25 (real-money-readiness goal session, position-monitor audit):
        # this UPDATE assigned `stop_loss_price` TWICE in the same SET clause (once to the
        # Python-computed `new_stop`, once via `ROUND(stop_loss_price / %s, 2)`) - PostgreSQL
        # categorically rejects this ("multiple assignments to same column"), live-confirmed
        # via a direct test query. Every real stock-split adjustment for any open position has
        # been crashing with a SyntaxError instead of applying, since whenever this duplicate
        # assignment was introduced - not a hypothetical edge case, stock splits are a real,
        # recurring market event. Fixed by dropping the redundant Python-value assignment and
        # keeping only the SQL-native ROUND(col / ratio) form, matching every sibling column.
        #
        # SECOND BUG FOUND in the same statement: only `stop_loss_price` (the FROZEN
        # entry-time value - see the CRITICAL FIX comment on _evaluate_position's SELECT
        # above, live-confirmed 2026-08-03) was ever rescaled here. `current_stop_price` - the
        # LIVE, actively-trailed stop that `_evaluate_position` actually compares against
        # market price for every real STOP_LOSS_HIT decision - was never touched, so after a
        # real split it would be left at its stale pre-split level (e.g. ~2x too high after a
        # 2-for-1 split) until the next unrelated stop-raise happened to recompute it -
        # exactly the "comparing against the wrong/stale stop" failure mode the 2026-08-03 fix
        # already fixed for a different code path, reintroduced here for the split-adjustment
        # path. Now rescaled alongside stop_loss_price; NULL-safe (a position with no trailing
        # raise yet has current_stop_price=NULL, and NULL/ratio stays NULL in SQL, preserving
        # the documented "fall back to stop_loss_price when current_stop_price is NULL"
        # semantics rather than fabricating a non-NULL value).
        cur.execute(
            """
            UPDATE algo_positions
            SET quantity = %s,
                entry_price = ROUND(entry_price / %s, 2),
                avg_entry_price = ROUND(avg_entry_price / %s, 2),
                stop_loss_price = ROUND(stop_loss_price / %s, 2),
                current_stop_price = ROUND(current_stop_price / %s, 2),
                target_1_price = ROUND(target_1_price / %s, 2),
                target_2_price = ROUND(target_2_price / %s, 2),
                target_3_price = ROUND(target_3_price / %s, 2),
                initial_risk_per_share = ROUND(initial_risk_per_share / %s, 4)
            WHERE id = %s
            """,
            (alpaca_qty, ratio_f, ratio_f, ratio_f, ratio_f, ratio_f, ratio_f, ratio_f, ratio_f, pos_id),
        )

        if trade_ids_arr:
            cur.execute(
                """
                UPDATE algo_trades
                SET entry_price = ROUND(entry_price / %s, 2),
                    stop_loss_price = ROUND(stop_loss_price / %s, 2),
                    target_1_price = ROUND(target_1_price / %s, 2),
                    target_2_price = ROUND(target_2_price / %s, 2),
                    target_3_price = ROUND(target_3_price / %s, 2)
                WHERE trade_id = ANY(%s)
                """,
                (ratio_f, ratio_f, ratio_f, ratio_f, ratio_f, list(trade_ids_arr)),
            )
        else:
            # ESCALATION FIX (2026-09-06 adversarial review): this was a plain logger.warning
            # only - every other consumer of an empty/NULL trade_ids_arr in this codebase
            # (circuit_breaker.py, phase6/phase9_reconciliation.py, executor_exit_handler.py)
            # treats it as a real, actionable "orphaned position" condition that fails closed
            # or halts, not a log-and-continue warning. A position left in this state here has
            # its algo_positions row correctly rescaled but its algo_trades row(s) silently
            # left at stale pre-split prices - R-multiple and profit-target checks will be
            # wrong until manual correction, and nothing was loud enough to prompt that
            # correction. Escalated to a real alert + CRITICAL audit severity, matching how
            # this exact condition is already treated everywhere else in the codebase.
            msg = (
                f"Split detected for {symbol} (position_id={pos_id}) but trade_ids_arr is "
                f"empty/NULL - algo_trades entry_price/stop_loss_price/target_N_price were "
                f"NOT rescaled. R-multiple and profit-target checks for this position's "
                f"underlying trade(s) will use stale pre-split prices until manually corrected."
            )
            logger.critical(f"[POSITION_MONITOR] {msg}")
            try:
                from algo.reporting import notify

                notify("CRITICAL", "Corporate action split - orphaned trade_ids_arr", msg, symbol=symbol)
            except Exception as notify_err:
                logger.error(f"[POSITION_MONITOR] Failed to send split-orphan alert: {notify_err}")

        audit_severity = "CRITICAL" if not trade_ids_arr else "WARN"
        audit_details = (
            f"Split: {symbol} {db_qty} -> {alpaca_qty} ratio {float(split_ratio_dec):.2f}. "
            f"Stop adjusted {db_stop:.2f} to {new_stop:.2f}."
        )
        if not trade_ids_arr:
            audit_details += " algo_trades NOT rescaled (empty/NULL trade_ids_arr) - manual correction needed."
        cur.execute(
            "INSERT INTO algo_audit_log (action_type, action_date, details, severity) VALUES (%s, %s, %s, %s)",
            (
                "CORPORATE_ACTION_SPLIT",
                datetime.now(timezone.utc),
                audit_details,
                audit_severity,
            ),
        )

        adjustments.append(
            {
                "symbol": symbol,
                "action": "STOCK_SPLIT",
                "old_qty": db_qty,
                "new_qty": alpaca_qty,
                "split_ratio": round(float(split_ratio_dec), 2),
                "old_stop": db_stop,
                "new_stop": new_stop,
            }
        )

        self._reconcile_broker_orders_after_split(cur, pos_id, symbol, new_stop)

    def _reconcile_broker_orders_after_split(
        self, cur: PsycopgCursor[Any], pos_id: int, symbol: str, new_stop: float
    ) -> None:
        """CRITICAL FIX (2026-09-06 real-money-readiness audit): _apply_split_adjustment above
        only ever rescaled DB price columns. The live protective stop-loss (and take-profit)
        order(s) resting at the broker were never cancelled/replaced, so they stayed at their
        stale PRE-split price indefinitely - phase9_stop_loss_repair.py's
        check_stop_loss_leg_live only verifies a stop LEG'S PRESENCE and QTY, never its price,
        so it would report "protected" forever while the real broker-side stop sat at up to
        Nx the correct level (a forward split leaves it far too high - fires immediately or
        nonsensically; a reverse split leaves it far too low - never fires, unbounded downside
        exposure). Whether Alpaca itself auto-adjusts a resting order's price on a split is not
        something this codebase can assume or verify from here, so treat every resting order
        for this symbol as stale and force a real re-verification rather than trust it.

        Fix: cancel every open order resting at the broker for this symbol (the stale-priced
        bracket/standalone legs) and clear standalone_stop_order_id, so phase9's normal
        check_stop_loss_leg_live/is_order_still_live checks correctly see "no live stop" on
        the next cycle and submit a fresh standalone protective stop at the just-rescaled
        new_stop price - reusing the existing, already-tested repair path instead of
        duplicating order-submission logic here. With enable_stop_loss_guardian now on (see
        prod.tfvars), that next cycle is at most ~15 minutes away, not the once-daily
        orchestrator run.
        """
        from algo.trading.order_manager import OrderManager

        try:
            alpaca_base_url, alpaca_key, alpaca_secret = self._get_alpaca_creds()
            order_mgr = OrderManager(alpaca_key, alpaca_secret, alpaca_base_url)
            cancel_result = order_mgr.cancel_all_open_orders_for_symbol(symbol)
        except Exception as e:
            cancel_result = {"success": False, "cancelled_order_ids": [], "message": str(e)}

        cur.execute(
            "UPDATE algo_positions SET standalone_stop_order_id = NULL WHERE id = %s",
            (pos_id,),
        )

        severity = "WARN" if cancel_result.get("success") else "CRITICAL"
        details = (
            f"Split follow-up for {symbol} (position {pos_id}): cancelled stale-priced broker "
            f"order(s) {cancel_result.get('cancelled_order_ids')} so the next stop-loss-repair "
            f"cycle resubmits at the corrected post-split stop {new_stop:.2f}. "
            f"{cancel_result.get('message')}"
        )
        cur.execute(
            "INSERT INTO algo_audit_log (action_type, action_date, details, severity) VALUES (%s, %s, %s, %s)",
            ("CORPORATE_ACTION_SPLIT_BROKER_RECONCILE", datetime.now(timezone.utc), details, severity),
        )
        if not cancel_result.get("success"):
            logger.critical(f"[POSITION_MONITOR] {details}")
            try:
                from algo.reporting import notify

                notify(
                    "CRITICAL",
                    "Split detected but stale broker order cancel failed",
                    details,
                    symbol=symbol,
                )
            except Exception as notify_err:
                logger.error(f"[POSITION_MONITOR] Failed to send split-broker-reconcile alert: {notify_err}")
        else:
            logger.warning(f"[POSITION_MONITOR] {details}")
