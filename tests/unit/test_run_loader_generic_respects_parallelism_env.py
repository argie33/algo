"""Regression test for a hardcoded parallelism=4 bug in scripts/run_loader.py's
run_loader_generic(), found 2026-08-10 while verifying the LOADER_PARALLELISM=1 default fix
(see [[analyst_loaders_reloaded_and_local_parallelism_ban_20260810]]).

Bug: the value_metrics/quality_metrics/growth_metrics branch called
`loader.run(symbols=symbols, parallelism=4)` with a hardcoded literal, completely bypassing
the LOADER_PARALLELISM env var - unlike every other loader branch, which reads
os.environ.get("LOADER_PARALLELISM", ...). This meant these three loaders would still
self-trigger the yfinance shared-IP rate-limit circuit breaker regardless of the
LOADER_PARALLELISM=1 default fix applied at the top of this same file.

Fixed: read parallelism from LOADER_PARALLELISM (default "1") here too, matching every
other branch's behavior.
"""

from unittest.mock import MagicMock, patch

import scripts.run_loader as run_loader_module


def _make_loader(table_name):
    loader = MagicMock()
    loader.table_name = table_name
    loader.run.return_value = {"symbols_processed": 1}
    del loader.post_run  # hasattr() must be False so run_loader_generic skips the hook
    return loader


class TestValueQualityGrowthRespectsParallelismEnv:
    def test_default_parallelism_is_one_not_hardcoded_four(self):
        loader = _make_loader("quality_metrics")
        with (
            patch("psycopg2.connect", side_effect=RuntimeError("no db in unit test")),
            patch.object(run_loader_module, "get_active_symbols", return_value=["AAPL"]),
            patch.dict("os.environ", {}, clear=False),
        ):
            run_loader_module.run_loader_generic(lambda: loader, "load_quality_metrics.py")

        assert loader.run.call_args.kwargs["parallelism"] == 1

    def test_explicit_env_override_is_respected(self):
        loader = _make_loader("value_metrics")
        with (
            patch("psycopg2.connect", side_effect=RuntimeError("no db in unit test")),
            patch.object(run_loader_module, "get_active_symbols", return_value=["AAPL"]),
            patch.dict("os.environ", {"LOADER_PARALLELISM": "2"}),
        ):
            run_loader_module.run_loader_generic(lambda: loader, "load_value_metrics.py")

        assert loader.run.call_args.kwargs["parallelism"] == 2
