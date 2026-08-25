#!/usr/bin/env python3
"""Read-only diagnostic: dump the raw Alpaca GET /v2/account response.

Why this exists (goal session 2026-08-24, real-money-readiness audit): Alpaca
is retiring the legacy PDT fields (pattern_day_trader, daytrade_count,
daytrading_buying_power, last_daytrade_count, last_daytrading_buying_power)
as part of FINRA's 2026 intraday-margin-framework replacement for Rule 4210's
old pattern-day-trader provisions. Alpaca's own migration blog post says the
Broker API returned fallback values during the transition window
(pattern_day_trader=false, daytrade_count=0 - i.e. always "no risk", not an
error) before full field removal on 2026-07-06, which has already passed.

algo/orchestrator/phase2_circuit_breakers.py and
algo/orchestrator/phase8_entry_execution.py's _check_pdt_limit_breach() both
depend entirely on pattern_day_trader/daytrade_count from
AlpacaBrokerAdapter.fetch_account() (algo/infrastructure/alpaca_broker_adapter.py)
to proactively block new entries before a real 90-day day-trading lockout.
If Alpaca now always returns pattern_day_trader=false (fallback) or omits the
field entirely, that protection is either a permanent silent no-op or (worse,
since _check_pdt_limit_breach fails closed) an unconditional halt on every
live entry run - and nothing in the current test suite would catch either,
since the unit tests only exercise the function against a hand-built dict,
never real API output.

This script cannot be run from a machine without real Alpaca credentials
(this repo's local dev sessions get them from AWS Secrets Manager, out of
scope for local-only work) - run it from wherever those credentials ARE
reachable, once, to get ground truth on what the account endpoint actually
returns today. It makes exactly one authenticated GET request and prints the
result; it does not place orders, modify config, or write to the database.
"""

import json
import sys

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager
from algo.infrastructure.config.main import get_config

PDT_RELATED_KEYS = (
    "pattern_day_trader",
    "daytrade_count",
    "daytrading_buying_power",
    "last_daytrade_count",
    "last_daytrading_buying_power",
    "buying_power",
    "regt_buying_power",
    "non_marginable_buying_power",
    "effective_buying_power",
    "options_buying_power",
    "trading_blocked",
    "account_blocked",
    "multiplier",
)


def main() -> int:
    import requests

    config = get_config()
    sync = AlpacaSyncManager(config)

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

    print("=== PDT / buying-power related fields (what the code actually needs) ===")
    for key in PDT_RELATED_KEYS:
        present = key in data
        print(f"  {key:32s} present={present!s:5s} value={data.get(key)!r}")

    print("\n=== Full raw response ===")
    print(json.dumps(data, indent=2, default=str))

    print("\n=== Interpretation ===")
    if "pattern_day_trader" not in data:
        print(
            "pattern_day_trader is ABSENT from the response. "
            "_check_pdt_limit_breach() and phase2_circuit_breakers.py's equivalent check "
            "will raise/fail-closed on every live run right now - this needs fixing before "
            "going live, not after."
        )
    elif data.get("pattern_day_trader") is False and data.get("daytrade_count") in (0, None):
        print(
            "pattern_day_trader=False and daytrade_count=0/None. This MATCHES Alpaca's "
            "documented fallback-value behavior during the PDT-field deprecation - it may be "
            "a placeholder, not a real 'zero day trades' reading. Compare against actual "
            "recent trading activity on this account before trusting it; if it doesn't match "
            "reality, the PDT check is currently a silent no-op and needs to be rebuilt on "
            "the new intraday-buying-power fields shown above instead."
        )
    else:
        print(
            "Fields are present and non-fallback-looking. Still worth a manual sanity check "
            "against known recent day-trade activity on this account before trusting the "
            "PDT gate in Phase 8 for live trading."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
