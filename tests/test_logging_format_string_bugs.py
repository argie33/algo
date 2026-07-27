"""Static check: catch logger calls that mix {name} placeholders into a
plain (non f-string) message while also passing %-style positional args.

That combination is silently wrong: logging's %-formatting only touches
%s/%d/etc, so the {name} part never gets substituted and the literal text
"{name}" ships to the logs instead of the real value. This class of bug hid
in loaders/load_prices.py for an unknown number of releases (fixed in commit
d83fd2cba) before anyone noticed the log lines were printing
"{self.table_name}" instead of the actual table name.

This test scans the whole tree so the same mistake can't silently reappear
in load_prices.py or land in any other file.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["loaders", "utils", "algo", "scripts"]

LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log"}


def _iter_python_files():
    for d in SCAN_DIRS:
        base = REPO_ROOT / d
        if base.is_dir():
            yield from base.rglob("*.py")


def _find_bugs_in_tree(tree, label):
    bugs = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_logger_call = (
            isinstance(func, ast.Attribute)
            and func.attr in LOG_METHODS
            and isinstance(func.value, ast.Name)
            and func.value.id in ("logger", "log")
        )
        if not is_logger_call or not node.args:
            continue

        msg_node = node.args[0]
        if not isinstance(msg_node, ast.Constant) or not isinstance(msg_node.value, str):
            continue  # f-strings are ast.JoinedStr, not Constant - not this bug class

        has_brace_placeholder = "{" in msg_node.value and "}" in msg_node.value
        # Extra positional args after the message mean %-style substitution is intended.
        has_percent_args = len(node.args) > 1
        if has_brace_placeholder and has_percent_args:
            bugs.append((label, msg_node.lineno, msg_node.value[:100]))

    return bugs


def _find_bugs_in_file(path):
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    return _find_bugs_in_tree(tree, path.relative_to(REPO_ROOT))


def _find_bugs_in_source(source):
    return _find_bugs_in_tree(ast.parse(source), "synthetic.py")


def test_detector_flags_known_bad_pattern():
    """Proves the detector isn't a false-negative rubber stamp: this is the exact
    shape of bug that shipped in loaders/load_prices.py (fixed in commit d83fd2cba)."""
    bad_source = 'logger.info("[CONSTRAINT] Unique constraint/index found on {self.table_name}(%s)", pk_cols)'
    assert len(_find_bugs_in_source(bad_source)) == 1


def test_detector_does_not_flag_correct_patterns():
    good_sources = [
        'logger.info("[CONSTRAINT] Unique constraint/index found on %s(%s)", self.table_name, pk_cols)',
        'logger.info(f"[CONSTRAINT] Unique constraint/index found on {self.table_name}")',
        'logger.info("no placeholders here")',
        'logger.debug("just one arg with {braces} and nothing to substitute")',
    ]
    for source in good_sources:
        assert _find_bugs_in_source(source) == [], source


def test_no_logger_calls_mix_brace_placeholders_with_percent_args():
    all_bugs = []
    for path in _iter_python_files():
        all_bugs.extend(_find_bugs_in_file(path))

    assert not all_bugs, (
        "Found logger calls using {name}-style placeholders in a plain string while also "
        "passing %-style positional args. The {name} part is never substituted - fix by "
        "either using %s for every value or making the whole string an f-string with no "
        "extra positional args:\n"
        + "\n".join(f"  {p}:{line}: {msg!r}" for p, line, msg in all_bugs)
    )
