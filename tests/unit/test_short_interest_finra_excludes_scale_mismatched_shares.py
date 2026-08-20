"""Regression test for a 2026-08-20 fix (goal: finance-accuracy audit) to
load_short_interest_finra.py's _load_shares_outstanding(): sec_valuations' own
shares_outstanding cross-check (added earlier this session) already flags symbols where
company_info_sec's value disagrees sharply with an independent source and is likely mis-scaled
(reason='shares_outstanding_scale_mismatch'). This loader had no equivalent guard, so it used
the same suspect value anyway.

Live-confirmed via GPUS (Hyperscale Data, Inc.): company_info_sec.shares_outstanding=1,529,995
is a real filed value, but stale relative to this company's own extreme dilution pace (real
share count grew ~30,000 -> ~380,730,000 across FY2022-FY2026). short_pct = short_shares /
outstanding * 100 then computed 3939.62% for a stock with genuinely single-digit-to-low-triple-
digit real short interest - this propagates into positioning_metrics.short_interest_pct and its
trend/change fields, which feed scoring.

Rather than clamp short_pct itself (this file's own comment already correctly rejects that - it
would mask genuine >100% squeeze readings like GME), this excludes the specific symbols
sec_valuations has already determined are untrustworthy, so this loader falls through to its own
honest "shares_outstanding_unavailable" path instead of reusing already-rejected data.
"""

from unittest.mock import MagicMock, patch

from loaders.load_short_interest_finra import ShortInterestFinraLoader


class _FakeCursor:
    """Sequential fetchall stand-in that also records executed query text."""

    def __init__(self, fetchall_results: list[list[tuple]]) -> None:
        self._results = list(fetchall_results)
        self._idx = 0
        self.executed_sql: list[str] = []

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        self.executed_sql.append(query)

    def fetchall(self) -> list[tuple]:
        result = self._results[self._idx]
        self._idx += 1
        return result


class TestShortInterestExcludesScaleMismatchedShares:
    def test_query_text_excludes_scale_mismatch_reason(self) -> None:
        """Regression guard: both queries must carry the exclusion clause, and neither
        must regress to a bare `reason != ...` (NULL-unsafe in SQL's three-valued logic -
        would silently drop every clean row, since most have reason IS NULL)."""
        fake_cursor = _FakeCursor([[], []])
        fake_ctx = MagicMock()
        fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
        fake_ctx.__exit__ = MagicMock(return_value=False)

        with patch("loaders.load_short_interest_finra.DatabaseContext", return_value=fake_ctx):
            ShortInterestFinraLoader._load_shares_outstanding()

        assert len(fake_cursor.executed_sql) == 2
        cis_query, sv_query = fake_cursor.executed_sql

        assert "shares_outstanding_scale_mismatch" in cis_query
        assert "sv.reason IS NULL OR sv.reason !=" in cis_query

        assert "shares_outstanding_scale_mismatch" in sv_query
        assert "reason IS NULL OR reason !=" in sv_query

    def test_scale_mismatched_symbol_falls_through_to_unavailable(self) -> None:
        """End-to-end: a symbol whose only shares_outstanding source is flagged
        scale-mismatched must end up with no usable value at all, not the suspect one."""
        # First query (company_info_sec JOIN sec_valuations) correctly excludes GPUS at
        # the SQL level (simulated here since the fake cursor doesn't execute real SQL) -
        # second query (sec_valuations fallback) also excludes it.
        fake_cursor = _FakeCursor(
            [
                [("AAPL", 15_000_000_000)],  # company_info_sec: a clean, unaffected symbol
                [],  # sec_valuations fallback: nothing for GPUS (correctly excluded)
            ]
        )
        fake_ctx = MagicMock()
        fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
        fake_ctx.__exit__ = MagicMock(return_value=False)

        with patch("loaders.load_short_interest_finra.DatabaseContext", return_value=fake_ctx):
            result = ShortInterestFinraLoader._load_shares_outstanding()

        assert result.get("GPUS") is None
        assert result["AAPL"] == 15_000_000_000
