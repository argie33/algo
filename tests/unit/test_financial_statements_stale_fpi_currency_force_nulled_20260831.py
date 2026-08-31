"""Regression test for the 2026-08-31 fix: BMA (Macro Bank Inc, an Argentine FPI) and other
ARS/BRL-reporting foreign private issuers had annual_balance_sheet.stockholders_equity (and
other monetary fields) stuck at a raw home-market-currency magnitude (BMA FY2021:
$466,723,603,000 - live-confirmed via BMA's own real SEC companyfacts JSON, CIK 1347426, to be
tagged unit="ARS", not "USD") divided against a USD ADS price downstream in sec_valuations.py,
producing an absurd pb_ratio=0.01 that won percentile 100 on Value and drove BMA (and VCIG,
CISS, and others via the same mechanism) to the top of composite_score.

utils/external/sec_statements.py's _aggregate_concepts already correctly rejects any non-USD/
non-MAJOR_CURRENCIES unit (ARS isn't whitelisted, by design) - live-verified via a direct call:
get_balance_sheet(client, 'BMA', 'annual') returns ZERO rows under current code, for every
fiscal year. But that correct rejection never reached the DB: preserve_on_missing_fields'
COALESCE(EXCLUDED.col, table.col) can't distinguish "this run's full-history extraction found
nothing at all for this FPI" from "this run's incremental fetch simply has nothing NEWER than
the watermark" (the overwhelmingly common, must-not-touch case).

sec_base.py's own fetch_incremental (the base class method this loader's fetch_incremental
overrides) is NOT symmetric here, and a first attempt at this fix got the signal backwards: a
truly-empty `rows` there ALWAYS means "real history exists, nothing newer than the watermark" -
when the full-history SEC extraction finds nothing at all, sec_base.py returns
`[self._unavailable_marker(symbol, reason)]` instead, a single data_unavailable=True row, never
a bare `[]` - live-confirmed via a real remediation run against BMA/LOMA/CEPU/CIG/GGB (all 5
hit "[YFINANCE_FALLBACK] ... has no USD conversion available - rejecting" and each got a
fiscal_year=0 marker row written, while their real stale rows stayed completely untouched
because the fix's first version checked `not rows`, which was always False). The correct signal
is "every row this run got back is a data_unavailable marker", not "rows is falsy".

Fix: fetch_incremental() now queues every existing row's preserve_on_missing_fields columns for
force-null (via the pre-existing _record_explicit_null_rejection/post_run() path
_reject_implausible_eps/_reject_implausible_shares_outstanding already use) when, and ONLY
when, ALL of: (a) this run's full-history extraction returned at least one row and every one of
them is a data_unavailable marker (real "nothing survives extraction", never a routine
"nothing newer than watermark" empty list), (b) self._backfill_days >= 3650 (an explicit large
backfill - an extra intentionality guard before a brand-new force-null path runs against
production data), (c) company_info_sec.is_foreign_private_issuer is True for this symbol (a
domestic filer returning nothing means something else entirely - delisted, no XBRL at all - and
must not have its history wiped by this guard).
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader

UNAVAILABLE_MARKER = {"symbol": "BMA", "fiscal_year": 0, "data_unavailable": True, "reason": "some_reason"}


def _make_loader(
    statement_type: str = "balance", period: str = "annual", backfill_days: int = 11000
) -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)
    # NOTE: __init__'s own backfill_days param only sets the separate, otherwise-unused
    # self.backfill_days attribute - the real self._backfill_days (OptimalLoader's, what
    # fetch_incremental's guard actually reads) is only ever set by run(backfill_days=...),
    # matching how the CLI's --backfill-days flag actually reaches it in production.
    loader._backfill_days = backfill_days
    return loader


def _mock_read_context(fetchone=None, fetchall=None):
    mock_cur = MagicMock()
    if fetchone is not None:
        mock_cur.fetchone.return_value = fetchone
    if fetchall is not None:
        mock_cur.fetchall.return_value = fetchall
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestFpiMarkerOnlyFetchQueuesForceNull:
    def test_fpi_marker_only_fetch_queues_existing_rows(self) -> None:
        loader = _make_loader()
        # is_foreign_private_issuer lookup -> True; existing-rows lookup -> 2 fiscal years
        fpi_ctx, _ = _mock_read_context(fetchone=(True,))
        rows_ctx, _ = _mock_read_context(fetchall=[("BMA", 2021), ("BMA", 2020)])
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[UNAVAILABLE_MARKER],
            ),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                side_effect=[fpi_ctx, rows_ctx],
            ),
        ):
            result = loader.fetch_incremental("BMA", None)
        assert result == [UNAVAILABLE_MARKER]
        for field in loader._bulk_insert_mgr.preserve_on_missing_fields:
            assert ({"symbol": "BMA", "fiscal_year": 2021}, field) in loader._explicit_null_rejections
            assert ({"symbol": "BMA", "fiscal_year": 2020}, field) in loader._explicit_null_rejections

    def test_domestic_symbol_marker_only_fetch_does_not_queue(self) -> None:
        """A domestic filer's full-history extraction legitimately returning nothing (e.g.
        delisted, never filed XBRL) must NOT have existing rows force-nulled."""
        loader = _make_loader()
        fpi_ctx, mock_cur = _mock_read_context(fetchone=(False,))
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[UNAVAILABLE_MARKER],
            ),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=fpi_ctx),
        ):
            result = loader.fetch_incremental("ZZZZ", None)
        assert result == [UNAVAILABLE_MARKER]
        assert loader._explicit_null_rejections == []
        # Only the is_foreign_private_issuer lookup ran - never queried existing rows.
        mock_cur.fetchall.assert_not_called()

    def test_small_backfill_does_not_queue_even_for_fpi(self) -> None:
        """A routine incremental/small-backfill run must never trigger this, even if this
        run's fetch happens to be marker-only."""
        loader = _make_loader(backfill_days=30)
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[UNAVAILABLE_MARKER],
            ),
            patch("loaders.load_financial_statements.DatabaseContext") as mock_dc,
        ):
            result = loader.fetch_incremental("BMA", None)
        assert result == [UNAVAILABLE_MARKER]
        assert loader._explicit_null_rejections == []
        mock_dc.assert_not_called()

    def test_truly_empty_rows_does_not_queue(self) -> None:
        """A bare empty list from sec_base.py's fetch_incremental means real history
        exists but nothing is newer than the watermark - the overwhelmingly common,
        must-not-touch incremental case. Must never trigger the sweep, even for an FPI on
        a large backfill."""
        loader = _make_loader()
        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "fetch_incremental", return_value=[]),
            patch("loaders.load_financial_statements.DatabaseContext") as mock_dc,
        ):
            result = loader.fetch_incremental("BMA", None)
        assert result == []
        assert loader._explicit_null_rejections == []
        mock_dc.assert_not_called()

    def test_real_data_present_does_not_queue(self) -> None:
        """A real fetch that returned actual data this run must never trigger the
        stale-currency sweep, even for an FPI on a large backfill."""
        loader = _make_loader()
        real_rows = [{"symbol": "TSM", "fiscal_year": 2024, "stockholders_equity": 123, "data_unavailable": False}]
        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "fetch_incremental", return_value=real_rows),
            patch("loaders.load_financial_statements.DatabaseContext") as mock_dc,
        ):
            result = loader.fetch_incremental("TSM", None)
        assert result == real_rows
        assert loader._explicit_null_rejections == []
        mock_dc.assert_not_called()

    def test_mixed_real_and_marker_rows_does_not_queue(self) -> None:
        """Even one real (non-data_unavailable) row alongside markers for other fiscal
        years must not trigger the sweep - only a fetch with ZERO real data qualifies."""
        loader = _make_loader()
        mixed_rows = [
            UNAVAILABLE_MARKER,
            {"symbol": "BMA", "fiscal_year": 2024, "stockholders_equity": 123, "data_unavailable": False},
        ]
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1], "fetch_incremental", return_value=mixed_rows
            ),
            patch("loaders.load_financial_statements.DatabaseContext") as mock_dc,
        ):
            result = loader.fetch_incremental("BMA", None)
        assert result == mixed_rows
        assert loader._explicit_null_rejections == []
        mock_dc.assert_not_called()

    def test_fpi_status_is_cached_per_symbol(self) -> None:
        loader = _make_loader()
        fpi_ctx, mock_cur = _mock_read_context(fetchone=(True,))
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=fpi_ctx):
            assert loader._is_foreign_private_issuer("BMA") is True
            assert loader._is_foreign_private_issuer("BMA") is True
        assert mock_cur.execute.call_count == 1

    def test_no_existing_rows_queues_nothing(self) -> None:
        loader = _make_loader()
        fpi_ctx, _ = _mock_read_context(fetchone=(True,))
        rows_ctx, _ = _mock_read_context(fetchall=[])
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[UNAVAILABLE_MARKER],
            ),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                side_effect=[fpi_ctx, rows_ctx],
            ),
        ):
            result = loader.fetch_incremental("NEWFPI", None)
        assert result == [UNAVAILABLE_MARKER]
        assert loader._explicit_null_rejections == []
