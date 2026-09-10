"""Regression test for the 2026-09-07 fix in check_file_size_ratchet.py: a commit that edits
ONLY .file-size-baseline.json (no .py files) never appeared in check_diff()'s .py-only
`entries` list, so the "raise the cap in a separate prior commit" escape hatch had zero upper
bound - baselines for already-huge files kept getting bumped commit after commit instead of
ever forcing a split (see MEMORY.md's bloater_decomposition_strategy note: a 2026-09-05
decision to split one bloater per session went unenforced while several of the named worst
offenders grew by hundreds of lines afterward). check_baseline_raise() now validates the
baseline file's own diff and refuses any raise that crosses HARD_CEILING, with no override.
"""

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_file_size_ratchet",
    Path(__file__).resolve().parents[2] / ".pre-commit-scripts" / "check_file_size_ratchet.py",
)
assert _SPEC and _SPEC.loader
check_file_size_ratchet = importlib.util.module_from_spec(_SPEC)
sys.modules["check_file_size_ratchet"] = check_file_size_ratchet
_SPEC.loader.exec_module(check_file_size_ratchet)


def test_baseline_raise_past_hard_ceiling_is_rejected():
    old = {"loaders/helpers/vqg_quality.py": 3674}
    new = {"loaders/helpers/vqg_quality.py": 5000}
    failures = check_file_size_ratchet.check_baseline_raise(old, new)
    assert len(failures) == 1
    assert "vqg_quality.py" in failures[0]
    assert "2000" in failures[0]


def test_baseline_raise_under_hard_ceiling_is_allowed():
    old = {"utils/small_module.py": 1000}
    new = {"utils/small_module.py": 1500}
    assert check_file_size_ratchet.check_baseline_raise(old, new) == []


def test_baseline_shrink_never_fails():
    old = {"loaders/helpers/vqg_quality.py": 3674}
    new = {"loaders/helpers/vqg_quality.py": 2000}
    assert check_file_size_ratchet.check_baseline_raise(old, new) == []


def test_baseline_unchanged_entries_are_ignored():
    old = {"a.py": 500, "b.py": 6000}
    new = {"a.py": 500, "b.py": 6000}
    assert check_file_size_ratchet.check_baseline_raise(old, new) == []


def test_check_diff_growth_on_already_huge_file_names_the_ceiling():
    """A file already past HARD_CEILING can never get a fresh baseline bump to cover
    further growth - the GROWN failure message must say so, not point at the (now-refused)
    raise-the-baseline escape hatch."""
    entries = [("loaders/helpers/vqg_quality.py", None)]
    baseline = {"loaders/helpers/vqg_quality.py": 3674}
    current_lines = {"loaders/helpers/vqg_quality.py": 3700}
    failures, _ = check_file_size_ratchet.check_diff(entries, baseline, current_lines)
    assert len(failures) == 1
    assert "No baseline raise will be accepted" in failures[0]


def test_check_diff_growth_under_ceiling_still_offers_the_raise_escape_hatch():
    entries = [("utils/small_module.py", None)]
    baseline = {"utils/small_module.py": 1000}
    current_lines = {"utils/small_module.py": 1100}
    failures, _ = check_file_size_ratchet.check_diff(entries, baseline, current_lines)
    assert len(failures) == 1
    assert "SEPARATE prior commit" in failures[0]
