"""Regression guard for Rich-markup-eaten keyboard-shortcut hints.

Every dashboard panel title embeds a hint like "[l] expand" / "[p] return" so the
user knows which key toggles/exits that panel's expanded view. Rich markup treats
unescaped square brackets as style tags, so a literal "[l]" in a markup string is
silently parsed as an (unrecognized) style tag and never rendered - the bracket and
its letter vanish with no error, leaving the user with no visible hint at all. The
fix is escaping the opening bracket ("\\[l]"); this test fails if that escaping is
ever dropped again in an edit, since Rich swallows it without warning.
"""

import re
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[2] / "dashboard"

# Matches an un-escaped shortcut hint: [dim][<letter>] expand[/] or [dim][<letter>] return[/]
UNESCAPED_HINT = re.compile(r"\[dim\]\[[a-z]\] (?:expand|return)\[/\]")


def _panel_source_files():
    files = list((DASHBOARD_ROOT / "panels").glob("*.py"))
    files += list((DASHBOARD_ROOT / "renderers").glob("*.py"))
    return files


def test_no_unescaped_keyboard_shortcut_hints():
    offenders = []
    for path in _panel_source_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if UNESCAPED_HINT.search(line):
                offenders.append(f"{path.relative_to(DASHBOARD_ROOT.parent)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Un-escaped keyboard-shortcut hint(s) found - Rich markup will silently swallow "
        "the bracketed letter and the hint will never render. Escape the opening bracket, "
        r'e.g. [dim]\[l] expand[/]" instead of "[dim][l] expand[/]":' + "\n" + "\n".join(offenders)
    )


def test_escaped_hint_renders_literally():
    from rich.console import Console
    from rich.text import Text

    console = Console(width=80, record=True)
    console.print(Text.from_markup(r"[dim]\[l] expand[/]"))
    output = console.export_text()
    assert "[l] expand" in output
