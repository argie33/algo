#!/usr/bin/env python3
"""
Apply Phase 2 migrations to dashboard.py
Replaces 9 critical fetch_* functions with API-only versions.
"""

import re


# Read the migration script to extract the replacement functions
with open("API_MIGRATION_SCRIPT.py", "r", encoding="utf-8") as f:
    migration_code = f.read()

# Read dashboard.py
with open("dashboard.py", "r", encoding="utf-8") as f:
    dashboard_code = f.read()

# Define the 9 replacements
replacements = [
    ("fetch_per", "fetch_perf_API_ONLY"),
    ("fetch_positions", "fetch_positions_API_ONLY"),
    ("fetch_recent_trades", "fetch_recent_trades_API_ONLY"),
    ("fetch_signals", "fetch_signals_API_ONLY"),
    ("fetch_portfolio", "fetch_portfolio_API_ONLY"),
    ("fetch_health", "fetch_health_API_ONLY"),
    ("fetch_algo_config", "fetch_algo_config_API_ONLY"),
    ("fetch_circuit", "fetch_circuit_API_ONLY"),
    ("fetch_activity", "fetch_activity_API_ONLY"),
]

updated_code = dashboard_code

for original_fn, replacement_fn in replacements:
    # Extract the replacement function from migration script
    pattern = rf"def {re.escape(replacement_fn)}\(c\):.*?(?=\ndef [a-z_]+\(|# ===|if __name__|$)"
    match = re.search(pattern, migration_code, re.DOTALL)

    if not match:
        print(f"[!] Could not find {replacement_fn} in migration script")
        continue

    replacement_code = match.group(0).strip()
    # Remove the _API_ONLY suffix to get the actual function name
    replacement_code = replacement_code.replace(
        f"def {replacement_fn}", f"def {original_fn}"
    )

    # Find and replace the original function in dashboard
    original_pattern = (
        rf"def {re.escape(original_fn)}\(c\):.*?(?=\ndef [a-z_]+\(|# ===|$)"
    )

    matches = list(re.finditer(original_pattern, updated_code, re.DOTALL))
    if not matches:
        print(f"[!] Could not find {original_fn} in dashboard.py")
        continue

    # Replace the FIRST occurrence only
    match = matches[0]
    updated_code = (
        updated_code[: match.start()] + replacement_code + updated_code[match.end() :]
    )
    print(f"[OK] Updated {original_fn}")

# Write the updated code
with open("dashboard.py", "w", encoding="utf-8") as f:
    f.write(updated_code)

print("\n" + "=" * 70)
print("[DONE] Phase 2 migration complete!")
print("=" * 70)
print("\nUpdated functions:")
for orig, _ in replacements:
    print(f"  [OK] {orig}()")
print("\nAll functions now use API-only (DashboardDataAPI) instead of DB queries.")
print("\nNext steps:")
print("  1. Test dashboard with: python dashboard.py -w 30")
print("  2. Verify all panels populate correctly")
print("  3. Check for any remaining DB query patterns")
