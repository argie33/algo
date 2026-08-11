"""Regression test: RouteAuthGuard.check_admin_access() (lambda/api/routes/auth_guard.py,
used by audit.py) must behave identically to auth_utils.check_admin_access() (lambda/api/
auth_utils.py, used by algo.py and 5 other route files) - not drift into a second,
independent copy.

BUG FOUND 2026-08-11: both modules' docstrings independently claimed to be "the single
source of truth" for admin auth, but RouteAuthGuard carried its own parallel
implementation that never recognized the "dev-admin" sub claim the canonical
auth_utils.check_admin_access() does (that recognition is itself safely gated far
upstream, in dev_auth.py's is_local_dev_mode() - see
test_dev_auth_fails_closed_in_real_lambda.py - so adding it here doesn't weaken
anything). In practice this meant /api/audit/* was the one route family that 403'd a
valid local dev-admin session while every other admin-gated route accepted it - a
functional inconsistency, not a live vulnerability (the drift was in the
fail-CLOSED direction), but exactly the duplicated-logic-drift class this codebase has
hit before elsewhere (execution_mode blocklist/allowlist fixes). Fixed by making
RouteAuthGuard delegate to the canonical function instead of maintaining its own copy.

'lambda' is a Python keyword, so modules under test are loaded via importlib.

Verified via: python -m pytest tests/unit/test_route_auth_guard_matches_canonical_check_admin_access.py -v
"""

import importlib
import sys
from pathlib import Path

_api_dir = str(Path(__file__).resolve().parents[2] / "lambda" / "api")
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

auth_utils = importlib.import_module("lambda.api.auth_utils")
auth_guard = importlib.import_module("lambda.api.routes.auth_guard")

CASES = [
    ("dev-admin sub", {"sub": "dev-admin"}, True),
    ("real cognito admin group", {"sub": "abc-123", "cognito:groups": ["admin"]}, True),
    ("real cognito non-admin group", {"sub": "abc-123", "cognito:groups": ["trader"]}, False),
    ("no groups claim", {"sub": "abc-123"}, False),
    ("empty claims", {}, False),
    ("none claims", None, False),
    ("groups not a list", {"sub": "abc-123", "cognito:groups": "admin"}, False),
    ("not a dict", "not-a-dict", False),
]


def test_route_auth_guard_matches_canonical_for_every_case():
    for label, claims, expected in CASES:
        canonical = auth_utils.check_admin_access(claims)
        guard = auth_guard.RouteAuthGuard.check_admin_access(claims)
        assert canonical == expected, f"[{label}] canonical check_admin_access diverged from expectation"
        assert guard == expected, f"[{label}] RouteAuthGuard.check_admin_access diverged from expectation"
        assert guard == canonical, f"[{label}] RouteAuthGuard and canonical check_admin_access disagree"


def test_route_auth_guard_delegates_to_canonical_function_not_a_copy():
    """Guard against this drifting apart again silently - assert the delegation is real,
    not just coincidentally-matching duplicate logic."""
    import inspect

    source = inspect.getsource(auth_guard.RouteAuthGuard.check_admin_access)
    assert "_check_admin_access" in source or "auth_utils" in source, (
        "RouteAuthGuard.check_admin_access must delegate to auth_utils.check_admin_access, "
        "not reimplement the check independently"
    )
