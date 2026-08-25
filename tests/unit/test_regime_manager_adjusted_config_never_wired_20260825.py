"""Regression/documentation test for a 2026-08-25 STRUCTURAL FINDING (real-money-readiness
goal session, targets/position-sizing audit): RegimeManager.get_adjusted_config() - the one
place max_hold_days/t1-3_target_r_multiple get regime-scaled - has ZERO real callers anywhere
in this codebase.

exit_engine.py's check_time_exit/check_target_t1/t2/t3 read max_hold_days/
t1-3_target_r_multiple straight off the config object phase6_exit_execution.py passes to
`ExitEngine(config)` - the RAW AlgoConfig, never routed through get_adjusted_config(). So
unlike position_size_mult (deliberately made display-only after its consumer was removed
2026-08-24 for double-counting exposure_pct - see
test_regime_manager_dead_position_size_multiplier_removed_20260824.py), REGIME_TARGET_*/
REGIME_HOLD_DAYS_* have no such "intentionally disconnected" note - this looks like an
unfinished wire-up, not a deliberate design choice, but there is also no backtest evidence
(unlike vol_managed_multiplier in market_exposure.py) that regime-scaling targets/hold-days
actually helps. See get_adjusted_config()'s own docstring for the two concrete remediation
options left for explicit user direction.

This test exists so the "currently unwired" state is asserted explicitly, not just narrated -
if a future change wires get_adjusted_config() into ExitEngine's config (or anywhere else),
this test's assumption should be revisited deliberately, not silently left describing a
now-stale reality.
"""

import ast
import inspect
import pkgutil


class TestGetAdjustedConfigHasNoRealCallers:
    def test_no_module_in_algo_calls_get_adjusted_config(self):
        """Repo-wide (within the `algo` package) AST scan for any call to
        `.get_adjusted_config(` other than the method's own definition."""
        import algo

        call_sites = []
        for _, modname, _ in pkgutil.walk_packages(algo.__path__, prefix="algo."):
            try:
                mod = __import__(modname, fromlist=["_"])
                source = inspect.getsource(mod)
            except Exception:
                continue
            if "get_adjusted_config" not in source:
                continue
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "get_adjusted_config" and modname != "algo.orchestration.regime_manager":
                        call_sites.append(modname)
                if isinstance(node, ast.FunctionDef) and node.name == "get_adjusted_config":
                    continue  # the definition itself, not a call

        assert not call_sites, (
            f"get_adjusted_config() now has real caller(s): {call_sites}. This test's premise "
            f"(the regime-based target/hold-days adjustment is unwired) is stale - update or "
            f"remove this test and the STRUCTURAL FINDING note in regime_manager.py's "
            f"get_adjusted_config() docstring to match the new reality."
        )

    def test_exit_engine_reads_max_hold_days_directly_from_config_not_a_regime_adjusted_copy(self):
        """exit_engine.py's check_time_exit must read max_hold_days via a plain
        self.config.get()/__getitem__ call, confirming it's the raw config ExitEngine(config)
        was constructed with, not output from get_adjusted_config()."""
        from algo.trading.exit_engine import PositionContext

        source = inspect.getsource(PositionContext.check_time_exit)
        assert 'self.config.get("max_hold_days")' in source or 'self.config["max_hold_days"]' in source
        assert "get_adjusted_config" not in source
