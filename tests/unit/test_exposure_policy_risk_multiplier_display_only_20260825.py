"""Regression/documentation test for a 2026-08-25 CONFIRMATION (real-money-readiness goal
session, position-sizing audit): each exposure tier's "risk_multiplier" field is
display/logging-only, not applied to real position-sizing math.

This is the SAME situation already found and deliberately resolved for
REGIME_POSITION_SIZE_* (algo/infrastructure/constants.py's own comment documents that those
4 constants were themselves copied from this exact risk_multiplier field, and that their
position-sizing consumer was deleted 2026-08-24 for double-counting exposure_pct against
position_sizer.py's continuous get_market_exposure_multiplier()).

This test exists so "risk_multiplier has no real position-sizing consumer" is asserted
explicitly - if a future change wires risk_multiplier into position sizing, this test's
assumption should be revisited deliberately (checking for the double-count this file's own
new comment warns about), not silently left describing a now-stale reality.
"""

import ast
import inspect
import pkgutil


def test_risk_multiplier_has_no_position_sizing_consumer():
    """Repo-wide AST scan for any attribute access `.risk_multiplier` outside
    exposure_policy.py's own dataclass round-trip and phase5's log line."""
    import algo

    allowed_modules = {"algo.risk.exposure_policy", "algo.orchestrator.phase5_exposure_policy"}
    unexpected_consumers = []

    for _, modname, _ in pkgutil.walk_packages(algo.__path__, prefix="algo."):
        if modname in allowed_modules:
            continue
        try:
            mod = __import__(modname, fromlist=["_"])
            source = inspect.getsource(mod)
        except Exception:
            continue
        if "risk_multiplier" not in source:
            continue
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "risk_multiplier":
                unexpected_consumers.append(modname)

    assert not unexpected_consumers, (
        f"risk_multiplier now has real consumer(s) outside the known display-only sites: "
        f"{unexpected_consumers}. If this is a deliberate new position-sizing application, "
        f"verify it does not double-count against position_sizer.py's continuous "
        f"get_market_exposure_multiplier() (see exposure_policy.py's EXPOSURE_TIERS comment "
        f"for the full history), then update this test."
    )
