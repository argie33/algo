"""Regression test for the 2026-08-17 fix: insider_transaction_velocity was killed at exactly
the generic SESSION 117 stall-timeout floor (900s, "0% stall for >900s") while genuinely
mid-download, not hung. Its download phase (CachedForm345Aggregator, 12 quarters of SEC Form
3/4/5 bulk data, no on-disk cache, all-or-nothing threading.Event) is structurally incapable of
any DB-visible progress before it completes, and the loader itself budgets up to 1080s for that
download - stricter than the generic floor, so it was killed before its own designed timeout
even had a chance to fire.

See scripts/local_loader_scheduler.py's STALL_TIMEOUT_FLOOR_OVERRIDES / _stall_timeout_for().
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test_stall_floor", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestStallTimeoutFloorOverrides:
    def test_insider_transaction_velocity_floor_exceeds_its_own_download_budget(self):
        """insider_transaction_velocity's LOADER_TIMEOUT is 2700s (45min), so the generic
        formula (min(1800, max(900, timeout/5))) would give exactly 900s - less than the
        loader's own 1080s CachedForm345Aggregator download budget. The override must win."""
        module = _load_scheduler_module()
        generic = min(1800, max(900, int(2700 / 5)))
        assert generic == 900  # sanity: this is the exact value that killed it live
        overridden = module._stall_timeout_for("insider_transaction_velocity", 2700)
        assert overridden == 1500
        assert overridden > 1080  # must exceed the loader's own internal download timeout

    def test_other_loaders_unaffected_by_the_override(self):
        """A loader with no override entry must still get the plain SESSION 117 formula."""
        module = _load_scheduler_module()
        assert module._stall_timeout_for("company_info", 32400) == 1800  # clamped ceiling
        assert module._stall_timeout_for("short_interest", 600) == 900  # clamped floor
        assert module._stall_timeout_for("earnings_calendar", 7200) == 1440  # 7200/5, mid-range
