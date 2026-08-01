#!/usr/bin/env python3
"""Final verification that XBRL extraction fixes resolve 466-company zero-coverage issue."""

import sys
import io

from utils.external.sec_statements import get_income_statement
from utils.external.sec_edgar_client import SecEdgarClient

# Handle Unicode on Windows
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# All problem companies from /goal
PROBLEM_COMPANIES = {
    "GLD": "SPDR Gold Trust (ETF)",
    "EE": "iShares MSCI EAFE (ETF, quarterly-only reporter)",
    "RANI": "Aytu BioPharma (us-gaap)",
    "ONON": "On Holding (IFRS-only, uses ProfitLossAttributableToOwnersOfParent)",
    "SNGX": "Small-cap (mixed quarterly/annual)",
    "AIFC": "AIF Holdings (mixed quarterly/annual)",
    "ATHE": "Athena Health (IFRS-only, uses ComprehensiveIncome)",
}

def test_coverage():
    """Test that problem companies now have net income coverage."""
    client = SecEdgarClient()
    fixed = 0
    still_broken = 0

    print("XBRL Net Income Coverage Verification")
    print("=" * 70)

    for symbol, description in PROBLEM_COMPANIES.items():
        try:
            statements = get_income_statement(client, symbol, period="annual")
            has_coverage = any(s.get("net_income_loss") is not None for s in statements)

            status = "[FIXED]" if has_coverage else "[BROKEN]"
            print(f"{status} {symbol:6} ({len(statements):2} stmts): {description}")

            if has_coverage:
                fixed += 1
                # Show an example
                for s in statements:
                    if s.get("net_income_loss") is not None:
                        print(f"         -> {s.get('fiscal_year')}: ${s.get('net_income_loss'):,}")
                        break
            else:
                still_broken += 1

        except Exception as e:
            print(f"[ERROR] {symbol:6}: {e}")
            still_broken += 1

    print("\n" + "=" * 70)
    print(f"SUMMARY: {fixed}/{len(PROBLEM_COMPANIES)} companies fixed")
    print(f"         {still_broken} companies still broken")

    if fixed == len(PROBLEM_COMPANIES):
        print("\n✓ ROOT CAUSE FIXED: All problem companies now have net income data!")
        return True
    else:
        print(f"\n✗ Still have {still_broken} companies with zero coverage")
        return False


if __name__ == "__main__":
    success = test_coverage()
    exit(0 if success else 1)
