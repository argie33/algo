"""Regression test (2026-09-05, background metrics-pipeline run): a module-level
`import loaders.load_financial_statements as _lfs` in
loaders/helpers/financial_statements_q4_sweeps.py caused a real circular ImportError -
load_financial_statements.py imports this module at its own module level (for
Q4DerivationSweepMixin), and this module imported load_financial_statements right back,
so whichever module started loading first crashed with "cannot import name
'Q4DerivationSweepMixin' from partially initialized module ... (most likely due to a
circular import)". This broke the ENTIRE financial_statements loader (all 6 output
tables) in a live local_loader_scheduler.py run, which cascaded into value_quality_growth
and enhanced_quality_growth being skipped too (declared dependency on financial_statements
never completing). Same bug class as
test_sec_valuations_checks_circular_import_fixed_20260905.py, on a different pair of
files - fixed the same way: defer the import itself (not just the attribute access) to
call time, via a `_database_context()` accessor function instead of a module-level
`import ... as _lfs`.
"""

import os
import subprocess
import sys


class TestFinancialStatementsQ4SweepsCircularImportFixed:
    def test_bare_script_invocation_does_not_crash(self):
        # This is the EXACT invocation scripts/local_loader_scheduler.py uses
        # (cmd = [sys.executable, f"loaders/{loader_filename}"]) - reproduced the bug live.
        result = subprocess.run(
            [sys.executable, "loaders/load_financial_statements.py", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "LOADER_STATEMENT_TYPE": "income"},
        )
        assert result.returncode == 0, result.stderr
        assert "ImportError" not in result.stderr
        assert "circular import" not in result.stderr

    def test_module_invocation_does_not_crash(self):
        result = subprocess.run(
            [sys.executable, "-m", "loaders.load_financial_statements", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "LOADER_STATEMENT_TYPE": "income"},
        )
        assert result.returncode == 0, result.stderr
        assert "ImportError" not in result.stderr
        assert "circular import" not in result.stderr

    def test_importing_q4_sweeps_module_first_does_not_crash(self):
        # The failure mode depends on which module gets a head start in sys.modules -
        # this reproduces the other ordering in-process (helpers module first).
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import loaders.helpers.financial_statements_q4_sweeps; import loaders.load_financial_statements",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "ImportError" not in result.stderr
