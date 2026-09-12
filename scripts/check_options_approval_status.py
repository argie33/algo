#!/usr/bin/env python3
"""Read-only diagnostic: check whether this Alpaca account is approved for options
trading, and at what level.

Why this exists (options-strategy phase 2 kickoff, 2026-09-12): the 7-phase options
strategy plan (see MEMORY.md options_strategy_full_plan_and_phase1_20260912) is
blocked on a single external fact for phase 5+ (real order submission) - whether
Alpaca has actually approved this account for options trading. Nothing in the repo
checked this before now. Options approval is tiered (Alpaca uses levels 1-3: level 1
covered calls/cash-secured puts, level 2 adds long calls/puts, level 3 adds spreads) -
the planned wheel strategy (CSP + covered call) only needs level 1, so this script
reports the level explicitly rather than just approved/not-approved.

This makes exactly one authenticated GET request to /v2/account and prints the
options-relevant fields. It does not place orders, modify config, or write to the
database. Must be run somewhere AlpacaSyncManager can resolve real credentials (see
check_pdt_field_status.py for the same constraint) - a bare local-only session without
AWS Secrets Manager access cannot run this meaningfully.
"""

import json
import sys

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager
from algo.infrastructure.config.main import get_config

OPTIONS_RELATED_KEYS = (
    "options_approved_level",
    "options_trading_level",
    "options_buying_power",
    "trading_blocked",
    "account_blocked",
    "status",
)


def main() -> int:
    import requests

    config = get_config()
    try:
        sync = AlpacaSyncManager(config)
    except ValueError as exc:
        print(f"ERROR: could not resolve Alpaca credentials: {exc}", file=sys.stderr)
        print(
            "This must be run somewhere AlpacaSyncManager can resolve real credentials "
            "(e.g. via AWS Secrets Manager access, or APCA_API_KEY_ID/APCA_API_SECRET_KEY "
            "env vars), not a bare local-only session.",
            file=sys.stderr,
        )
        return 1

    if not sync.alpaca_key or not sync.alpaca_secret:
        print("ERROR: Alpaca credentials not available in this environment.", file=sys.stderr)
        print(
            "This must be run somewhere AlpacaSyncManager can resolve real credentials "
            "(e.g. via AWS Secrets Manager access), not a bare local-only session.",
            file=sys.stderr,
        )
        return 1

    resp = requests.get(
        f"{sync.alpaca_base_url}/v2/account",
        headers={
            "APCA-API-KEY-ID": sync.alpaca_key,
            "APCA-API-SECRET-KEY": sync.alpaca_secret,
        },
        timeout=30,
    )
    print(f"HTTP {resp.status_code} from {sync.alpaca_base_url}/v2/account\n")

    if resp.status_code != 200:
        print(resp.text)
        return 1

    data = resp.json()

    print("=== Options-approval related fields ===")
    for key in OPTIONS_RELATED_KEYS:
        present = key in data
        print(f"  {key:28s} present={present!s:5s} value={data.get(key)!r}")

    print("\n=== Full raw response ===")
    print(json.dumps(data, indent=2, default=str))

    print("\n=== Interpretation ===")
    level = data.get("options_approved_level") or data.get("options_trading_level")
    if level is None:
        print(
            "No options_approved_level/options_trading_level field found. This account is "
            "almost certainly NOT approved for options trading - phase 5+ (real order "
            "submission) of the options strategy plan stays blocked. Apply for options "
            "trading approval in the Alpaca dashboard/API before continuing past phase 3 "
            "(backtest)."
        )
    elif level == 0:
        print("options level = 0 -> explicitly NOT approved. Phase 5+ stays blocked until approval is granted.")
    elif level >= 1:
        print(
            f"options level = {level} -> approved. Level 1 (covers cash-secured puts and "
            "covered calls, i.e. the planned wheel strategy) is sufficient for this plan. "
            "Phase 5+ is NOT blocked by approval status; other phase-5 gates (backtest "
            "pass, spec sign-off, risk infra) still apply."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
