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
  5. Alert delivery channels (email/SNS) are actually configured, and - the one thing code
     alone can never confirm - whether the SNS subscription is actually confirmed rather than
     stuck in PendingConfirmation (added 2026-08-31 per PRODUCTION_READINESS_AUDIT_20260831.md
     Observation 9: notify(strict=True) succeeding only proves a DB row was written to
     algo_notifications, never that a human actually received anything).
  6. Pointers to the two existing pre-flight scripts this one deliberately does not duplicate:
     verify_safety_thresholds.py (threshold sanity) and the full pytest suite.

Does NOT place any order, does NOT modify any state - read-only end to end, UNLESS you pass
--send-test-alert, which sends exactly one real test notification (email/SNS) so you can confirm
delivery actually works, not just that it's configured. Off by default for that reason.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests


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


def check_alert_delivery_channels() -> list[str]:
    """Report which alert channels (email/SNS) are actually configured in THIS environment,
    and - for SNS - whether the topic's subscription is actually confirmed. Read-only: lists
    subscriptions, sends nothing. See send_test_alert() for the one side-effecting check.

    Added 2026-08-31 (PRODUCTION_READINESS_AUDIT_20260831.md Observation 9): AWS SNS email
    subscriptions require the recipient to click a confirmation link when created - until then
    the subscription sits in PendingConfirmation and sns.publish() still returns success while
    delivering to nobody. notify(strict=True) has no way to detect this itself (no exception is
    raised), so it was giving false confidence that "operator awareness" was guaranteed.
    """
    import os

    failures: list[str] = []
    try:
        from algo.reporting.alerts import AlertManager

        mgr = AlertManager()
    except Exception as e:
        return [f"  Could not initialize AlertManager: {type(e).__name__}: {e!s:.150}"]

    if mgr.noop_mode:
        failures.append(
            "  No alert channel configured at all (ALERT_EMAIL_TO and ALERTS_SNS_TOPIC both "
            "empty) - notify(strict=True) would only ever write a DB row to algo_notifications, "
            "no human would ever be alerted."
        )
        return failures

    if mgr.email_to:
        print(f"    Email channel: recipients={mgr.email_to} smtp_host={mgr.smtp_host or 'NOT SET'}")
        if not (mgr.smtp_host and mgr.smtp_user and mgr.smtp_password):
            failures.append(
                "  Email recipients configured (ALERT_EMAIL_TO) but SMTP credentials are "
                "incomplete - AlertManager silently disables email in this case (falls back to "
                "SNS-only, if configured). Check ALERT_SMTP_SECRET_ARN resolves in Secrets Manager."
            )
    else:
        print("    Email channel: not configured (ALERT_EMAIL_TO empty)")

    if mgr.sns_topic:
        print(f"    SNS channel: topic={mgr.sns_topic}")
        try:
            import boto3

            sns = boto3.client("sns", region_name=os.getenv("AWS_REGION", "us-east-1"))
            resp = sns.list_subscriptions_by_topic(TopicArn=mgr.sns_topic)
            subs = resp.get("Subscriptions", [])
            if not subs:
                failures.append(
                    f"  SNS topic {mgr.sns_topic} has ZERO subscriptions - publish() will succeed but reach nobody."
                )
            for sub in subs:
                endpoint = sub.get("Endpoint", "?")
                if sub.get("SubscriptionArn") == "PendingConfirmation":
                    failures.append(
                        f"  SNS subscription for {endpoint} is PendingConfirmation - the "
                        f"recipient never clicked the confirmation email. publish() will "
                        f"succeed but deliver nothing to this endpoint."
                    )
                else:
                    print(f"      confirmed subscription: {endpoint}")
        except Exception as e:
            failures.append(
                f"  Could not verify SNS subscription status ({type(e).__name__}: {e!s:.150}) - "
                f"check manually: aws sns list-subscriptions-by-topic --topic-arn {mgr.sns_topic}"
            )
    else:
        print("    SNS channel: not configured (ALERTS_SNS_TOPIC empty)")

    return failures


def send_test_alert() -> list[str]:
    """Sends exactly ONE real test alert via notify(strict=True) - the only side-effecting
    check in this script, which is why it's opt-in (--send-test-alert) rather than run by
    default. Configuration alone (check_alert_delivery_channels above) cannot prove delivery
    actually works end to end - only receiving a real message can."""
    try:
        from algo.reporting.notifications import notify

        notify(
            "info",
            title="[TEST] Live-trading readiness check",
            message=(
                "This is a test alert sent by scripts/verify_live_trading_readiness.py "
                "--send-test-alert. If you received this via email or SNS, alert delivery is "
                "confirmed working end to end. If you only see this in the algo_notifications "
                "table but never got an email/SNS message, external delivery is broken even "
                "though notify(strict=True) reported success."
            ),
            strict=True,
        )
        return []
    except Exception as e:
        return [f"  Test alert failed to send: {type(e).__name__}: {e!s:.150}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight check before flipping to real-money trading")
    parser.add_argument(
        "--send-test-alert",
        action="store_true",
        help="Also send one real test alert (email/SNS) to confirm delivery actually works, "
        "not just that it's configured. The only side-effecting check in this script.",
    )
    args = parser.parse_args()

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

    print("\n[5] Alert delivery channels (email/SNS)...")
    failures = check_alert_delivery_channels()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f)
        all_failures.extend(failures)
    else:
        print("OK  — at least one alert channel is configured and SNS subscriptions (if any) are confirmed")

    if args.send_test_alert:
        print("\n[5b] Sending one real test alert (--send-test-alert)...")
        failures = send_test_alert()
        if failures:
            print("FAIL:")
            for f in failures:
                print(f)
            all_failures.extend(failures)
        else:
            print(
                "    Sent. Go check your email/SNS endpoint NOW - if nothing arrives within a "
                "minute, delivery is broken even though this reported success (notify() only "
                "confirms the DB write + no exception, not actual receipt)."
            )
    else:
        print("\n[5b] Skipped (pass --send-test-alert to actually send one and confirm receipt)")

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
