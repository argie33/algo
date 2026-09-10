#!/usr/bin/env python3
"""Phase 8 PDT (Pattern Day Trader) proactive limit check, extracted from
phase8_entry_execution.py (file-size ratchet: that file was already past the 2000-line
hard ceiling, see .file-size-baseline.json). Body is verbatim, no logic changed.
"""

from typing import Any


def _check_pdt_limit_breach(account_data: dict[str, Any]) -> tuple[bool, str | None]:
    """Check whether this account is one same-day round-trip away from exceeding the
    rolling 5-business-day PDT day-trade limit.

    PROACTIVE PDT CHECK (2026-08-24 fix): crossing this limit triggers a real, severe
    consequence (Alpaca/FINRA Reg T: a 90-day day-trading lockout on accounts under $25k
    equity). This system intentionally generates same-day stop-loss exits (exit_engine.py's
    own docstring), so this isn't hypothetical. Phase 2 already fetches this exact same
    account data but only logs a warning - nothing previously stopped Phase 8 from
    submitting an entry that could become the trade that crosses the threshold (see
    pdt_day_trade_limit_reactive_only_not_proactively_enforced_20260824 in memory).

    FIXED 2026-08-27 (goal: pre-live-money audit): the 2026-08-24 version gated this
    entire check on `pattern_day_trader == True`, reasoning that the flag already
    encoded Alpaca's equity-aware PDT determination. That reasoning had it backwards -
    `pattern_day_trader` is a *trailing* flag Alpaca sets only once a 4th day trade in
    the rolling window has already happened (and on an account under $25k equity, Alpaca
    sets `trading_blocked=True` in that same moment - already caught by this file's
    separate frozen-account check). `daytrade_count` is tracked independently and
    continuously by Alpaca regardless of the flag's state, so the exact "one round-trip
    from the 4th" scenario this check exists to catch - daytrade_count==3, flag still
    False - is precisely the state the old gate excluded. It could never fire in the
    scenario its own docstring and tests described. Now checks daytrade_count directly;
    pattern_day_trader is still a required field (fail-fast if missing) but no longer
    gates the comparison, only informs the message.

    Args:
        account_data: Alpaca account dict, must contain 'pattern_day_trader' (raises
            KeyError if missing - fail-fast, matching this file's other pre-checks).

    Returns:
        (breach: bool, reason: str | None) - breach=True means block new entries this run.
    """
    if "pattern_day_trader" not in account_data:
        raise KeyError(
            "[PHASE 8] Account data missing required 'pattern_day_trader' field. "
            "Cannot verify PDT status before submitting live entries."
        )
    # EQUITY-AWARE FIX (2026-09-06 real-money-readiness audit): FINRA Rule 4210's PDT
    # restriction (90-day day-trading lockout after a 4th day-trade in 5 business days)
    # applies ONLY to accounts with equity under $25,000 - an account at or above that
    # threshold cannot be PDT-restricted at all, regardless of daytrade_count. This check
    # previously blocked new entries purely on daytrade_count>=3 with no equity awareness,
    # needlessly halting a well-capitalized account's real trading on a restriction that
    # genuinely cannot apply to it. Not a regulatory-exposure bug (it was over-conservative,
    # never under), but a real correctness gap worth closing before real-money trading.
    equity = account_data.get("equity")
    if equity is not None and float(equity) >= 25_000:
        return False, None
    daytrade_count = account_data.get("daytrade_count")
    # FAIL-CLOSED FIX (real-money-readiness audit): a missing daytrade_count on a
    # sub-$25k account used to fall through the `is None` branch straight to "safe to
    # trade" - inconsistent with this file's own fail-fast stance on every other missing
    # PDT-relevant field (pattern_day_trader raises KeyError above). Alpaca reliably
    # populates this field in practice, but "reliably" isn't "always" - a genuinely
    # unknown day-trade count is exactly the kind of unknown this file's docstring says
    # must block, not silently permit, given the real 90-day lockout consequence of
    # guessing wrong.
    if daytrade_count is None:
        return True, (
            "[PHASE 8 PDT LIMIT] Account daytrade_count is missing/unknown and equity is "
            "under $25k (or unavailable) - cannot verify this account is not one round-trip "
            "away from Alpaca's PDT restriction. Blocking new entries this run as a fail-"
            "closed precaution; existing positions and their protective stops (Phase 6, "
            "already executed) are unaffected."
        )
    if int(daytrade_count) < 3:
        return False, None
    return True, (
        f"[PHASE 8 PDT LIMIT] Account daytrade_count={daytrade_count} (>=3 of the "
        f"rolling 5-business-day limit; pattern_day_trader currently "
        f"{bool(account_data['pattern_day_trader'])}) - one more same-day round-trip "
        "would trigger Alpaca's PDT restriction (90-day day-trading lockout on accounts "
        "under $25k equity). Blocking new entries this run; existing positions and "
        "their protective stops (Phase 6, already executed) are unaffected."
    )
