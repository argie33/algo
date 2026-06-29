#!/bin/bash
# Prevent SKIP= bypass for critical pre-commit hooks
# This runs as a commit-msg hook to reject commits that try to skip governance checks

COMMIT_MSG="$1"
COMMIT_EDITMSG="$COMMIT_MSG"

# List of hooks that CANNOT be skipped
CRITICAL_HOOKS=(
    "check-credential-defaults"
    "enforce-type-safety-rules"
    "check-dashboard-get-pattern"
    "enforce-strict-safe-conversion"
)

# Check if commit message or environment tries to skip critical hooks
for hook in "${CRITICAL_HOOKS[@]}"; do
    if [[ "$SKIP" == *"$hook"* ]]; then
        echo "ERROR: Cannot skip critical governance hook: $hook" >&2
        echo "This hook is required to prevent fail-fast violations in financial data handling." >&2
        echo "" >&2
        echo "Reason you cannot skip:" >&2
        case "$hook" in
            "check-credential-defaults")
                echo "  - Prevents empty-string defaults for passwords/API keys"
                echo "  - Silent credential failures could bypass authentication"
                ;;
            "enforce-type-safety-rules")
                echo "  - Ensures type safety across financial calculations"
                echo "  - Type errors in position sizing could cause wrong trade sizes"
                ;;
            "check-dashboard-get-pattern")
                echo "  - Validates data field access in dashboard/portfolio code"
                echo "  - Missing fields could cause incorrect P&L display"
                ;;
            "enforce-strict-safe-conversion")
                echo "  - Requires strict validation for price/cash/position conversions"
                echo "  - Loose conversion could silently degrade financial calculations"
                ;;
        esac
        echo "" >&2
        echo "If you believe this hook is incorrectly blocking legitimate code," >&2
        echo "contact the team to discuss whitelisting." >&2
        exit 1
    fi
done

exit 0
