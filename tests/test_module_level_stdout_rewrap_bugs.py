"""Static check: catch `sys.stdout`/`sys.stderr` reassigned to a new
io.TextIOWrapper at module import time (unguarded), outside any function.

That pattern (a "Windows console can't print emoji/UTF-8" fix, present in a
dozen+ standalone scripts in this repo) permanently replaces pytest's own
capture streams the first time anything imports the module - not just when
the script is actually run directly. The new TextIOWrapper wraps the SAME
underlying buffer pytest's capture fixture is tracking; when either wrapper
is later closed, it cascades to the shared buffer, and pytest's capture
teardown crashes with "ValueError: I/O operation on closed file" for the
rest of the test session. Confirmed live 3 separate times in this repo
(monitor_data_staleness.py, verify_eventbridge_scheduler.py,
check_system_health.py) - each time only surfacing once someone added a test
that imports the module, at which point it looked like a flaky/unrelated
pytest internals crash rather than the real cause.

The two correct fixes already used in this repo, either of which this test
accepts:
  1. Guard the module-level `if` with `"pytest" not in sys.modules` (see
     dashboard/dashboard.py) - never reassigns anything while pytest is
     running, in this process or a subprocess importing under pytest.
  2. Move the reassignment inside main()/a function, so merely importing the
     module (as any test file naturally does) never executes it at all (see
     monitor_data_staleness.py, check_system_health.py,
     verify_eventbridge_scheduler.py after their fixes).

This test scans the whole tree so the same mistake can't silently reappear.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["loaders", "utils", "algo", "scripts", "dashboard", ".pre-commit-scripts"]
ROOT_FILES = ["check_system_health.py", "dashboard.py"]


def _iter_python_files():
    for f in ROOT_FILES:
        p = REPO_ROOT / f
        if p.is_file():
            yield p
    for d in SCAN_DIRS:
        base = REPO_ROOT / d
        if base.is_dir():
            yield from base.rglob("*.py")


def _is_stdio_textiowrapper_assign(node):
    """True if `node` is `sys.stdout = io.TextIOWrapper(...)` or the stderr
    equivalent (an ast.Assign whose single target is sys.stdout/sys.stderr and
    whose value is a call to `io.TextIOWrapper` / `TextIOWrapper`)."""
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return False
    target = node.targets[0]
    if not (
        isinstance(target, ast.Attribute)
        and target.attr in ("stdout", "stderr")
        and isinstance(target.value, ast.Name)
        and target.value.id == "sys"
    ):
        return False
    value = node.value
    return isinstance(value, ast.Call) and (
        (isinstance(value.func, ast.Name) and value.func.id == "TextIOWrapper")
        or (isinstance(value.func, ast.Attribute) and value.func.attr == "TextIOWrapper")
    )


def _is_name_main_guard(node):
    """True if `node` is `if __name__ == "__main__":` (either operand order).
    Code inside this block only runs when the script is executed directly -
    never when merely imported (by pytest or anything else) - so it's just as
    safe as being inside a function."""
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    operands = [test.left, *test.comparators]
    names = {n.id for n in operands if isinstance(n, ast.Name)}
    strings = {n.value for n in operands if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    return "__name__" in names and "__main__" in strings


def _find_bugs_in_tree(tree, source, label):
    bugs = []
    guarded = '"pytest" not in sys.modules' in source or "'pytest' not in sys.modules" in source

    # Track enclosing function/`if __name__ == "__main__"` scope via a
    # parent-stack walk (ast.walk has no parent pointers by default).
    def walk(node, in_safe_scope):
        for child in ast.iter_child_nodes(node):
            child_in_safe_scope = (
                in_safe_scope
                or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                or _is_name_main_guard(child)
            )
            if _is_stdio_textiowrapper_assign(child) and not in_safe_scope and not guarded:
                bugs.append((label, child.lineno))
            walk(child, child_in_safe_scope)

    walk(tree, False)
    return bugs


def _find_bugs_in_file(path):
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    return _find_bugs_in_tree(tree, source, path.relative_to(REPO_ROOT))


def _find_bugs_in_source(source):
    return _find_bugs_in_tree(ast.parse(source), source, "synthetic.py")


def test_detector_flags_known_bad_pattern():
    """Proves the detector isn't a false-negative rubber stamp: this is the
    exact shape that shipped (and crashed pytest) in verify_eventbridge_scheduler.py
    and check_system_health.py before their fixes."""
    bad_source = (
        "import sys\nimport io\n"
        "if sys.platform.startswith('win'):\n"
        "    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')\n"
    )
    assert len(_find_bugs_in_source(bad_source)) == 1


def test_detector_does_not_flag_correct_patterns():
    good_sources = [
        # Fix pattern 1: pytest-guarded (dashboard/dashboard.py)
        "import sys\nimport io\n"
        "if sys.platform.startswith('win') and \"pytest\" not in sys.modules:\n"
        "    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')\n",
        # Fix pattern 2: inside a function (check_system_health.py after fix)
        "import sys\nimport io\n"
        "def main():\n"
        "    if sys.platform.startswith('win'):\n"
        "        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')\n",
        # Fix pattern 3: inside `if __name__ == "__main__":` (monitor_data_staleness.py after fix)
        "import sys\nimport io\n"
        "if __name__ == '__main__':\n"
        "    if sys.platform.startswith('win'):\n"
        "        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')\n",
        # No rewrap at all
        "import sys\nprint('hello')\n",
    ]
    for source in good_sources:
        assert _find_bugs_in_source(source) == [], source


def test_no_unguarded_module_level_stdio_textiowrapper_reassignment():
    all_bugs = []
    for path in _iter_python_files():
        all_bugs.extend(_find_bugs_in_file(path))

    assert not all_bugs, (
        "Found sys.stdout/sys.stderr reassigned to a new io.TextIOWrapper at module "
        "import time, unguarded. This corrupts pytest's own capture streams the "
        "first time anything imports the module (crashes capture teardown with "
        "'ValueError: I/O operation on closed file'). Fix by either adding "
        "'and \"pytest\" not in sys.modules' to the guarding if-statement, or moving "
        "the reassignment inside main()/a function:\n" + "\n".join(f"  {p}:{line}" for p, line in all_bugs)
    )
