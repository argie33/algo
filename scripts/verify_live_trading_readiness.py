#!/usr/bin/env python3
"""Pre-flight checklist for flipping this system from paper to real-money trading.

Built 2026-08-27 (real-money-readiness /goal review) specifically so the actual moment
of going live is a single automated, fail-loud check instead of someone manually eyeballing
env vars and hoping. Run this AFTER setting real Alpaca live-trading credentials and the
three live-intent env vars, BEFORE the first orchestrator run with execution_mode=auto.

Checks, in order:
  1. Live-intent env vars (ALGO_LIVE_TRADING / ALPACA_PAPER_TRADING / APCA_API_BASE_URL) -
     mirrors algo/trading/executor_strategies.py's AutoExecutionMode._check_live_intent()
     exactly, so a PASS here means the real executor will actually resolve to the live
     endpoint, not silently fall back to paper.
  2. Credentials actually authenticate against the LIVE Alpaca endpoint (not paper), and the
     account itself isn't blocked/restricted/flat.
  3. algo_config.execution_mode in the live DB - reported, not failed on (that's an
     intentional switch you flip when ready, not a precondition this script enforces).
  4. Orchestrator halt flag isn't already active (would block Phase 8 entries regardless of
     credentials being correct).
  5. Pointers to the two existing pre-flight scripts this one deliberately does not duplicate:
     verify_safety_thresholds.py (threshold sanity) and the full pytest suite.

Does NOT place any order, does NOT modify any state - read-only end to end.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests  # noqa: E402


def check_live_intent_env_vars() -> list[str]:
    """Mirrors AutoExecutionMode._check_live_intent()/validate_and_log_initialization()
    (algo/trading/executor_strategies.py) exactly - if this check disagrees with what the
    real executor decides at run time, THIS function is wrong, not the other way around.
    """
    import os

    failures = []
    live_ack = os.getenv("ALGO_LIVE_TRADING", "").strip()
    paper_flag = os.getenv("ALPACA_PAPER_TRADING", "true").strip().lower()
    configured_url = os.getenv("APCA_API_BASE_URL")
    url_says_paper = "paper" in (configured_url or "").lower()

    if live_ack != "I_UNDERSTAND_REAL_MONEY":
        failures.append(f"  ALGO_LIVE_TRADING is {live_ack!r}, must be exactly 'I_UNDERSTAND_REAL_MONEY'")
    if paper_flag == "true":
        failures.append("  ALPACA_PAPER_TRADING is 'true' (or unset) - must be 'false' for live trading")
    if not configured_url:
        failures.append("  APCA_API_BASE_URL is not set - must point at https://api.alpaca.markets")
    elif url_says_paper:
        failures.append(f"  APCA_API_BASE_URL contains 'paper': {configured_url!r} - must be the live endpoint")

    return failures


def check_live_alpaca_account() -> tuple[list[str], dict[str, Any] | None]:
    """Resolve real credentials the same way the executor does, then hit the LIVE Alpaca
    endpoint directly (not paper-api) and verify the account can actually trade.

    Returns (failures, account_dict_or_None).
    """
    from algo.config.credential_manager import get_alpaca_credentials
    from utils.dotenv_loader import load_env_local

    failures: list[str] = []
    load_env_local()

    try:
        creds = get_alpaca_credentials()
    except Exception as e:
        return ([f"  Could not resolve Alpaca credentials: {type(e).__name__}: {e!s:.150}"], None)

    key = creds.get("key")
    secret = creds.get("secret")
    if not key or not secret:
        return (["  Resolved credentials are empty - key/secret missing"], None)

    try:
        resp = requests.get(
            "https://api.alpaca.markets/v2/account",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
            timeout=15,
        )
    except requests.RequestException as e:
        return ([f"  Request to live Alpaca endpoint failed: {type(e).__name__}: {e!s:.150}"], None)

    if resp.status_code != 200:
        failures.append(
            f"  Live endpoint returned HTTP {resp.status_code} (not 200) - "
            f"these credentials do not authenticate against api.alpaca.markets. "
            f"Body: {resp.text[:200]}"
        )
        return (failures, None)

    account = resp.json()

    if account.get("status") != "ACTIVE":
        failures.append(f"  Account status is {account.get('status')!r}, expected 'ACTIVE'")
    if account.get("trading_blocked"):
        failures.append("  Account has trading_blocked=True")
    if account.get("account_blocked"):
        failures.append("  Account has account_blocked=True")
    try:
        equity = float(account.get("equity", 0))
    except (TypeError, ValueError):
        equity = 0.0
        failures.append(f"  Account equity is non-numeric: {account.get('equity')!r}")
    if equity <= 0:
        failures.append(f"  Account equity is {equity} - nothing to trade with")
    try:
        buying_power = float(account.get("buying_power", 0))
    except (TypeError, ValueError):
        buying_power = 0.0
        failures.append(f"  Account buying_power is non-numeric: {account.get('buying_power')!r}")

    print(
        f"    account_number={account.get('account_number')} status={account.get('status')} "
        f"equity=${equity:,.2f} buying_power=${buying_power:,.2f} "
        f"pattern_day_trader={account.get('pattern_day_trader')} "
        f"daytrade_count={account.get('daytrade_count')}"
    )

    return (failures, account)


def check_db_execution_mode() -> tuple[str | None, list[str]]:
    """Report (not fail on) algo_config.execution_mode - this script verifies the live
    switch WOULD work correctly if flipped, it does not decide whether to flip it."""
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("SELECT value FROM algo_config WHERE key = 'execution_mode'")
            row = cur.fetchone()
            return (row[0] if row else None, [])
    except Exception as e:
        return (None, [f"  Could not read algo_config.execution_mode: {type(e).__name__}: {e!s:.150}"])


def check_halt_flag_inactive() -> list[str]:
    """A correct live-credential setup is moot if the orchestrator's own circuit-breaker
    halt flag is already active - Phase 8 would block all new entries regardless."""
    try:
        from algo.orchestration.halt_flag_manager import HaltFlagManager

        class _NoOpAlerts:
            def send_position_alert(self, *a: Any, **kw: Any) -> None:
                pass

        def _noop_log(*a: Any, **kw: Any) -> None:
            pass

        mgr = HaltFlagManager(_NoOpAlerts(), _noop_log)
        if mgr.check_halt_flag():
            reason = None
            try:
                reason = mgr.get_halt_reason()
            except Exception:
                pass
            return [f"  Orchestrator halt flag is ACTIVE (reason: {reason or 'unknown'}) - entries are blocked"]
        return []
    except Exception as e:
        return [f"  Could not check halt flag: {type(e).__name__}: {e!s:.150}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight check before flipping to real-money trading")
    args = parser.parse_args()
    del args

    print("\nLive-Trading Readiness Check")
    print("=" * 60)

    all_failures: list[str] = []

    print("\n[1] Live-intent environment variables...")
    failures = check_live_intent_env_vars()
    if failures:
        print("FAIL — live mode would resolve to PAPER, not live, right now:")
        for f in failures:
            print(f)
        all_failures.extend(failures)
    else:
        print("OK  — ALGO_LIVE_TRADING / ALPACA_PAPER_TRADING / APCA_API_BASE_URL all agree on live intent")

    print("\n[2] Credentials against the LIVE Alpaca endpoint (api.alpaca.markets)...")
    failures, account = check_live_alpaca_account()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f)
        all_failures.extend(failures)
    elif account is not None:
        print("OK  — live endpoint authenticates and account can trade")

    print("\n[3] algo_config.execution_mode (informational only)...")
    mode, failures = check_db_execution_mode()
    if failures:
        for f in failures:
            print(f)
        all_failures.extend(failures)
    else:
        print(f"    execution_mode = {mode!r}")
        if mode != "auto":
            print(f"    (still {mode!r} - this is expected until you deliberately flip it; not a failure here)")

    print("\n[4] Orchestrator halt flag...")
    failures = check_halt_flag_inactive()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f)
        all_failures.extend(failures)
    else:
        print("OK  — no halt flag active")

    print("\n" + "=" * 60)
    print("Not covered by this script (run separately before going live):")
    print("  python scripts/verify_safety_thresholds.py --strict   (threshold sanity)")
    print("  python -m pytest tests/unit/ -q                        (full regression suite)")

    print("\n" + "=" * 60)
    if all_failures:
        print(f"NOT READY — {len(all_failures)} issue(s) found. Do not set execution_mode=auto yet.")
        return 1
    print("READY — live credentials and safety gates check out. Flip execution_mode to 'auto' when ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
