"""Regression test (2026-09-05, goal: "implausible values" sweep): a module-level
`import loaders.load_sec_valuations as _lsv` in loaders/helpers/sec_valuations_checks.py caused
a real circular ImportError - not just a deferred-attribute-access problem - whenever this
module was imported before load_sec_valuations.py already had a head start in sys.modules.
Reproduced via the EXACT invocation local_loader_scheduler.py uses in production
(`python loaders/load_sec_valuations.py`) and `python -m loaders.load_sec_valuations`: both
raised "cannot import name 'ValuationSanityCheckMixin' from partially initialized module" and
made the entire sec_valuations loader unrunnable standalone since this file's creation at
`5e306dab3`. Fixed by deferring the `import loaders.load_sec_valuations as _lsv` statement
itself (not just the attribute access) to inside the one method that uses it.

This test can't easily reproduce the exact subprocess-level circularity in-process (the failure
mode depends on which module has a head start in sys.modules, which pytest's own collection
order already disturbs) - it instead asserts the two real-world entrypoints load_sec_valuations.py
is actually invoked through both succeed, which is what actually broke.
"""

import subprocess
import sys


class TestSecValuationsChecksCircularImportFixed:
    def test_bare_script_invocation_does_not_crash(self):
        # This is the EXACT invocation scripts/local_loader_scheduler.py uses
        # (cmd = [sys.executable, f"loaders/{loader_filename}"]) - reproduced the bug live.
        result = subprocess.run(
            [sys.executable, "loaders/load_sec_valuations.py", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "ImportError" not in result.stderr
        assert "circular import" not in result.stderr

    def test_module_invocation_does_not_crash(self):
        result = subprocess.run(
            [sys.executable, "-m", "loaders.load_sec_valuations", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "ImportError" not in result.stderr
        assert "circular import" not in result.stderr
