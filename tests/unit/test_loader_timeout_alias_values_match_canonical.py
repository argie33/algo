"""Regression test: every "Alias for X" loader timeout entry in loader_timeout_config.py
must have the SAME value as the canonical entry X it claims to be an alias for.

Bug (found 2026-08-18, live): "institutional" (900s/15min) and "institutional_holdings_13f"
(2700s/45min) are the exact same script - loaders/loader_registry.py maps
"institutional" -> load_institutional_holdings_13f.py, and the real ECS task-def timeout
(terraform/modules/loaders/main.tf) is 2700s, matching institutional_holdings_13f. But the
"institutional" shorthand entry - the one actually used by
scripts/local_loader_scheduler.py's "reference" pipeline loader list - was never synced to
it, so every run through the shorthand enforced only a 900s Python-level timeout, 3x below
the real budget. Every other alias/canonical pair in this file (positioning/
positioning_metrics, insider_holdings/insider_holdings_sec, insider_velocity/
insider_transaction_velocity, etc.) already had matching values - this one didn't, and
nothing caught it because the two entries are ~80 lines apart and neither test suite
(get_loader_timeouts() itself, or the terraform-vs-python drift tests) compares declared
aliases against what they claim to alias.
"""

import re
from pathlib import Path

from loaders.loader_timeout_config import get_loader_timeouts

REPO_ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_CONFIG = REPO_ROOT / "loaders" / "loader_timeout_config.py"


def _parse_declared_aliases() -> list[tuple[str, int, str]]:
    """Extract (alias_name, alias_seconds, canonical_name) from every
    '"alias": N * 60,  # ... Alias for canonical ...' comment in the source."""
    content = TIMEOUT_CONFIG.read_text(encoding="utf-8")
    pattern = re.compile(r'"(\w+)":\s*(\d+)\s*\*\s*60,.*?[Aa]lias for (\w+)')
    return [(name, int(mult) * 60, canonical) for name, mult, canonical in pattern.findall(content)]


def test_parser_finds_a_reasonable_number_of_declared_aliases() -> None:
    aliases = _parse_declared_aliases()
    assert len(aliases) >= 20, (
        f"Only found {len(aliases)} declared alias entries - expected 20+. "
        "The '# Alias for X' comment parsing regex likely needs updating."
    )


def test_every_declared_alias_value_matches_its_canonical_entry() -> None:
    aliases = _parse_declared_aliases()
    timeouts = get_loader_timeouts()

    violations = []
    for alias_name, alias_seconds, canonical in aliases:
        canonical_seconds = timeouts.get(canonical)
        if canonical_seconds is None:
            violations.append(f"  {alias_name!r}: claims to alias {canonical!r}, which has no timeout entry at all")
        elif canonical_seconds != alias_seconds:
            violations.append(
                f"  {alias_name!r}={alias_seconds}s but its canonical entry {canonical!r}={canonical_seconds}s - "
                f"these must match since they're the same underlying loader"
            )

    assert not violations, "Alias/canonical loader timeout mismatches found:\n" + "\n".join(violations)
