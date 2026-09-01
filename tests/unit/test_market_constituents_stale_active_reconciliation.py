"""Regression: already-`active=true` stock_symbols rows must be re-evaluated against
CURRENT should_exclude() patterns, not just newly-fetched rows.

Bug (confirmed live 2026-08-04): excluded symbols are simply omitted from the list
fetch_global() returns to the bulk-insert write path, so a symbol that was `active=true`
under an OLDER, looser pattern set stays `active=true` forever even after a later pattern
change tightens to newly cover it. Live-confirmed 59 already-active SPAC-rights symbols
(AACPR, AESPR, ...) still `active=true` a full day after the 2026-08-03 `\\brights?\\b`
pattern addition - inflating price_daily's "active universe" denominator and pinning its
completion % below the 98% mark_completed() safety threshold every single day, so the
dashboard's Data Freshness table showed price_daily as chronically FAILED for a reason
that had nothing to do with the price loader itself.

Also covers the companion pattern-gap fix: CORP_SPONSOR_PATTERN (formerly
INVESTMENT_CORP_PATTERN) widened from `\\binvestment corp\\b` to
`\\b(investment|acquisition) corp(oration)?\\b`, since "... Acquisition Corp[oration]"
turned out to be the more common SPAC-sponsor naming convention and its base
"Class A Ordinary Share(s)" equity line was never excluded by any pattern.
"""

from unittest.mock import MagicMock, patch

from loaders.load_market_constituents import MarketConstituentsLoader, _is_excluded, should_exclude


def _make_loader():
    return MarketConstituentsLoader.__new__(MarketConstituentsLoader)


class TestAcquisitionCorpSponsorPattern:
    def test_acquisition_corp_ordinary_shares_excluded(self):
        assert should_exclude("Abony Acquisition Corp. I - Class A Ordinary Share")

    def test_acquisition_corporation_ordinary_shares_excluded(self):
        assert should_exclude("Alpex Acquisition Corporation - Class A Ordinary Shares")

    def test_acquisition_corp_units_still_excluded_by_existing_pattern(self):
        assert should_exclude("Iron Dome Acquisition I Corp. - Units")

    def test_real_operating_company_with_acquisition_in_name_not_excluded(self):
        """A real operating company's Common Stock line must stay included even if its
        legal name happens to contain 'Acquisition Corp' - the SPAC_SHARE_CLASS_PATTERN
        gate (Ordinary Shares/Rights) is what keeps this safe, same guard as the existing
        investment-corp case (AGNC/Saratoga)."""
        assert not should_exclude("Example Acquisition Corp. - Common Stock")


class TestDeactivateStaleExcludedSymbols:
    def test_active_row_matching_current_pattern_gets_deactivated(self):
        loader = _make_loader()
        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("algo.reporting.notify") as mock_notify,
        ):
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [
                ("AACPR", "Apogee Acquisition Corp - Rights"),
                ("AAPL", "Apple Inc. - Common Stock"),
            ]
            mock_write_cur = MagicMock()
            mock_purge_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.side_effect = [mock_read_cur, mock_write_cur, mock_purge_cur]

            loader._deactivate_stale_excluded_symbols()

            mock_write_cur.execute.assert_called_once()
            sql, params = mock_write_cur.execute.call_args[0]
            assert "UPDATE stock_symbols" in sql
            assert "active = false" in sql
            assert params == (["AACPR"],)

        # BUG FOUND 2026-09-01 (/goal session): a tightened/broadened exclusion pattern
        # can reach into the already-active universe and flip a real symbol inactive -
        # must alert so an operator can catch a false positive, same as the sibling
        # feed-absence deactivation path.
        mock_notify.assert_called_once()
        _, kwargs = mock_notify.call_args
        assert kwargs["severity"] == "warning"
        assert "AACPR" in kwargs["message"]
        assert kwargs["details"]["symbols"] == ["AACPR"]

        # Deactivation must also purge the newly-inactive symbol's stale rows from
        # every downstream score table - see _purge_stale_downstream_score_rows.
        assert mock_purge_cur.execute.call_count == 6
        for call in mock_purge_cur.execute.call_args_list:
            sql, params = call[0]
            assert "DELETE FROM" in sql
            assert params == (["AACPR"],)

    def test_no_stale_matches_skips_write(self):
        loader = _make_loader()
        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("algo.reporting.notify") as mock_notify,
        ):
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [("AAPL", "Apple Inc. - Common Stock")]
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._deactivate_stale_excluded_symbols()

            # Only the read call happened - DatabaseContext("write") never entered.
            assert mock_db_ctx.call_args_list == [(("read",), {})]

        mock_notify.assert_not_called()

    def test_notify_failure_does_not_crash_the_loader(self):
        """A notification-delivery failure must be swallowed (logged), not propagate and
        abort the market-constituents run - alerting is best-effort here, not a
        governance gate."""
        loader = _make_loader()
        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("algo.reporting.notify", side_effect=RuntimeError("smtp down")),
        ):
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [
                ("AACPR", "Apogee Acquisition Corp - Rights"),
                ("AAPL", "Apple Inc. - Common Stock"),
            ]
            mock_write_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.side_effect = [mock_read_cur, mock_write_cur]

            # Must not raise despite notify() failing internally.
            loader._deactivate_stale_excluded_symbols()


class TestReactivateNoLongerExcludedSymbols:
    """Regression test added 2026-08-18 (goal: "no SEC data"/loader-failure audit):
    the reverse direction of TestDeactivateStaleExcludedSymbols above. Once a pattern is
    corrected to no longer match a symbol (e.g. the American-Depositary-Shares
    false-positive fix), that symbol's `active=false` row was never revisited - excluded
    symbols are omitted from fetch_global()'s `rows` list entirely, so the bulk-insert
    write path's ON CONFLICT SET clause (dynamically built from row-dict keys, which
    never include `active`) can never flip it back to true on a normal re-run.
    """

    def test_no_longer_excluded_row_gets_reactivated(self):
        loader = _make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [
                (
                    "BABA",
                    "Alibaba Group Holding Limited American Depositary Shares each representing eight Ordinary share",
                ),
                ("EQH$A", "Equitable Holdings, Inc. Depositary Shares"),
            ]
            mock_write_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.side_effect = [mock_read_cur, mock_write_cur]

            loader._reactivate_no_longer_excluded_symbols()

            mock_write_cur.execute.assert_called_once()
            sql, params = mock_write_cur.execute.call_args[0]
            assert "UPDATE stock_symbols" in sql
            assert "active = true" in sql
            assert params == (["BABA"],)

    def test_no_recovered_matches_skips_write(self):
        loader = _make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [("EQH$A", "Equitable Holdings, Inc. Depositary Shares")]
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._reactivate_no_longer_excluded_symbols()

            # Only the read call happened - DatabaseContext("write") never entered.
            assert mock_db_ctx.call_args_list == [(("read",), {})]

    def test_read_query_scoped_to_naming_pattern_reason(self):
        """Must never touch active=false rows excluded for an unrelated, still-valid
        reason (e.g. genuinely delisted) - only rows this loader itself deactivated."""
        loader = _make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = []
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._reactivate_no_longer_excluded_symbols()

            sql = mock_read_cur.execute.call_args[0][0]
            assert "data_unavailable_reason = 'excluded_by_naming_pattern'" in sql


class TestDeactivateSymbolsDelistedFromExchangeFeed:
    """Regression test added 2026-08-21 (goal session - "why does price_daily keep
    retry-failing on the same handful of symbols every day"): a symbol that vanishes
    entirely from nasdaqlisted.txt/otherlisted.txt (real delisting/acquisition) was never
    deactivated - `active` is never a key in fetch_global()'s row dicts, so the bulk-insert
    write path only ever adds/updates symbols present in the CURRENT fetch and never
    notices one that dropped out. Live-confirmed: NSA/ELSE/LPRO/PSTV/SKYT/VSTD absent from
    both live feeds, Alpaca has zero bars for each past its own last real trading day, yet
    all six sat `active=true` and price_daily logged them FAILED every single run.

    BUG FOUND 2026-08-21 (same session): "absent from feed" alone is not trustworthy -
    the first live run deactivated 110 symbols and 94 (AVB, EQR, WBS, BBBY, ...) had
    price_daily data within the last 2 weeks, obviously still trading. Fixed to require
    BOTH signals (missing from feed AND no recent price_daily row) before deactivating -
    these tests now cover that second, orthogonal check.
    """

    def test_symbol_missing_from_feed_and_no_recent_price_gets_deactivated(self):
        loader = _make_loader()
        feed_symbols = {f"SYM{i}" for i in range(5000)} | {"AAPL"}
        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("algo.reporting.notify") as mock_notify,
        ):
            mock_active_cur = MagicMock()
            mock_active_cur.fetchall.return_value = [(s,) for s in feed_symbols] + [("NSA",)]
            mock_priced_cur = MagicMock()
            mock_priced_cur.fetchall.return_value = []  # NSA has no recent price_daily row
            mock_write_cur = MagicMock()
            mock_purge_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.side_effect = [
                mock_active_cur,
                mock_priced_cur,
                mock_write_cur,
                mock_purge_cur,
            ]

            loader._deactivate_symbols_delisted_from_exchange_feed(feed_symbols)

            mock_write_cur.execute.assert_called_once()
            sql, params = mock_write_cur.execute.call_args[0]
            assert "UPDATE stock_symbols" in sql
            assert "active = false" in sql
            assert "delisted_or_removed_from_exchange_feed" in sql
            assert params == (["NSA"],)

        # BUG FOUND 2026-09-01 (/goal session): this deactivation used to be a bare log
        # line - live-caught firing a genuine false positive for EQR (still-listed,
        # yfinance-confirmed active NYSE equity) despite this exact "second orthogonal
        # signal" guard, because a shared upstream yfinance gap can trip both conditions
        # at once. Must alert so an operator can catch and reverse a false positive.
        mock_notify.assert_called_once()
        _, kwargs = mock_notify.call_args
        assert kwargs["severity"] == "warning"
        assert "NSA" in kwargs["message"]
        assert kwargs["details"]["symbols"] == ["NSA"]

        # Deactivation must also purge the newly-inactive symbol's stale rows from
        # every downstream score table - see _purge_stale_downstream_score_rows.
        assert mock_purge_cur.execute.call_count == 6

    def test_no_symbols_deactivated_means_no_alert(self):
        """Sanity check: the alert must not fire when nothing was actually deactivated -
        covered implicitly by test_no_missing_symbols_skips_price_check_and_write and
        test_symbol_missing_from_feed_but_still_recently_priced_stays_active below (neither
        reaches the notify() call at all since `gone` is empty), but pinned explicitly here
        too since this is the exact behavior those tests protect without asserting on it."""
        loader = _make_loader()
        feed_symbols = {f"SYM{i}" for i in range(5000)} | {"AAPL"}
        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("algo.reporting.notify") as mock_notify,
        ):
            mock_active_cur = MagicMock()
            mock_active_cur.fetchall.return_value = [(s,) for s in feed_symbols] + [("AVB",)]
            mock_priced_cur = MagicMock()
            mock_priced_cur.fetchall.return_value = [("AVB",)]  # recent price_daily row exists
            mock_db_ctx.return_value.__enter__.side_effect = [mock_active_cur, mock_priced_cur]

            loader._deactivate_symbols_delisted_from_exchange_feed(feed_symbols)

        mock_notify.assert_not_called()

    def test_notify_failure_does_not_crash_the_loader(self):
        """A notification-delivery failure must be swallowed (logged), not propagate and
        abort the market-constituents run - alerting is best-effort here, not a
        governance gate."""
        loader = _make_loader()
        feed_symbols = {f"SYM{i}" for i in range(5000)} | {"AAPL"}
        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("algo.reporting.notify", side_effect=RuntimeError("smtp down")),
        ):
            mock_active_cur = MagicMock()
            mock_active_cur.fetchall.return_value = [(s,) for s in feed_symbols] + [("NSA",)]
            mock_priced_cur = MagicMock()
            mock_priced_cur.fetchall.return_value = []
            mock_write_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.side_effect = [mock_active_cur, mock_priced_cur, mock_write_cur]

            # Must not raise despite notify() failing internally.
            loader._deactivate_symbols_delisted_from_exchange_feed(feed_symbols)

    def test_symbol_missing_from_feed_but_still_recently_priced_stays_active(self):
        """The exact false-positive this bug produced live: absent from the feed fetch,
        but price_daily proves it's still trading - must not be touched."""
        loader = _make_loader()
        feed_symbols = {f"SYM{i}" for i in range(5000)} | {"AAPL"}
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_active_cur = MagicMock()
            mock_active_cur.fetchall.return_value = [(s,) for s in feed_symbols] + [("AVB",)]
            mock_priced_cur = MagicMock()
            mock_priced_cur.fetchall.return_value = [("AVB",)]  # recent price_daily row exists
            mock_db_ctx.return_value.__enter__.side_effect = [mock_active_cur, mock_priced_cur]

            loader._deactivate_symbols_delisted_from_exchange_feed(feed_symbols)

            # Only the two read calls happened - DatabaseContext("write") never entered.
            assert mock_db_ctx.call_args_list == [(("read",), {}), (("read",), {})]

    def test_no_missing_symbols_skips_price_check_and_write(self):
        loader = _make_loader()
        feed_symbols = {f"SYM{i}" for i in range(5000)}
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [(s,) for s in feed_symbols]
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._deactivate_symbols_delisted_from_exchange_feed(feed_symbols)

            assert mock_db_ctx.call_args_list == [(("read",), {})]

    def test_truncated_feed_skips_check_entirely(self):
        """A feed with far fewer symbols than a real universe is more likely a broken
        fetch than a mass-delisting event - must not touch the DB at all."""
        loader = _make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            loader._deactivate_symbols_delisted_from_exchange_feed({"AAPL", "MSFT"})

            mock_db_ctx.assert_not_called()

    def test_mass_missing_symbols_exceeds_safety_cap_skips_write(self):
        """More than MAX_AUTO_DEACTIVATE symbols that are both missing from the feed AND
        have no recent price data implies a bad fetch, not real delistings - must not
        mass-deactivate the universe on a single bad run."""
        loader = _make_loader()
        feed_symbols = {f"SYM{i}" for i in range(5000)}
        missing = [f"GONE{i}" for i in range(51)]
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_active_cur = MagicMock()
            mock_active_cur.fetchall.return_value = [(s,) for s in feed_symbols] + [(s,) for s in missing]
            mock_priced_cur = MagicMock()
            mock_priced_cur.fetchall.return_value = []  # none of the missing symbols have recent prices
            mock_db_ctx.return_value.__enter__.side_effect = [mock_active_cur, mock_priced_cur]

            loader._deactivate_symbols_delisted_from_exchange_feed(feed_symbols)

            # Only the two read calls happened - DatabaseContext("write") never entered.
            assert mock_db_ctx.call_args_list == [(("read",), {}), (("read",), {})]


class TestKnownWhenIssuedMisclassificationOverride:
    """Regression test added 2026-08-18 (goal: "no SEC data"/loader-failure audit): SNDK
    (Sandisk Corp, spun off from Western Digital Feb 2025) and CEG (Constellation Energy
    Corp, spun off from Exelon Feb 2022) are both real, large, long-established common
    stocks - live-confirmed against TODAY's actual NASDAQ feed (not a cached copy) that
    it still says "...Common Stock When-Issued" for both, well past any realistic
    when-issued settlement window (SEC's own live submissions data registers both under
    their plain names with no when-issued qualifier). `\\bwhen-issued\\b` is a correct
    pattern for genuinely-still-when-issued shares - this is an upstream feed data-quality
    issue, same class as the existing KNOWN_ETF_MISCLASSIFICATIONS override, not a regex
    bug to fix generally.
    """

    def test_sndk_when_issued_text_would_normally_be_excluded(self):
        """Sanity check that the underlying pattern still fires - the override is what
        exempts these specific symbols, not a change to the pattern itself."""
        assert should_exclude("Sandisk Corporation - Common Stock When-Issued")

    def test_sndk_exempted_via_known_override(self):
        assert not _is_excluded("SNDK", "Sandisk Corporation - Common Stock When-Issued")

    def test_ceg_exempted_via_known_override(self):
        assert not _is_excluded("CEG", "Constellation Energy Corporation - Common Stock When-Issued")

    def test_other_when_issued_symbols_still_excluded(self):
        """The override is scoped to the specific known-misclassified symbols, not a
        blanket exemption for the when-issued pattern."""
        assert _is_excluded("XYZ", "Resideo Technologies, Inc. Common Stock When-Issued")


class TestDeactivateBlankCheckShellsBySicAndRevenue:
    """GOVERNANCE 2026-09-01: user pushback that name-pattern SPAC exclusion "lets too
    many in" after two rounds of CORP_SPONSOR_PATTERN/KNOWN_SPAC_MISCLASSIFICATIONS
    whack-a-mole in the same session. Replaces (for the SPAC-shell category specifically)
    ongoing name-pattern guessing with a structural, self-maintaining SEC-classification
    signal: sic_code=6770 ("Blank Checks") is SEC's own entity classification, not text
    matched from free-form security_name. Live-verified against a full active-universe
    scan: 28 active sic_code=6770 symbols, 27 with zero nonzero-revenue years ever
    (genuine dormant shells) and exactly one (INV/Innventure, real revenue in 2 fiscal
    years) that completed its de-SPAC merger - confirming the revenue check is needed as
    a second signal, not just the SIC code alone, to avoid the AGNC/SAR-class false
    positive of excluding a real operating company.
    """

    def _make_loader(self):
        return MarketConstituentsLoader.__new__(MarketConstituentsLoader)

    def test_shell_with_no_revenue_ever_gets_deactivated(self):
        loader = self._make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [("CEPV",), ("GIX",)]
            mock_write_cur = MagicMock()
            mock_purge_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.side_effect = [mock_read_cur, mock_write_cur, mock_purge_cur]

            loader._deactivate_blank_check_shells_by_sic_and_revenue()

            mock_write_cur.execute.assert_called_once()
            sql, params = mock_write_cur.execute.call_args[0]
            assert "UPDATE stock_symbols" in sql
            assert "active = false" in sql
            assert params == (["CEPV", "GIX"],)

            assert mock_purge_cur.execute.call_count == 6

    def test_read_query_scoped_to_sic_6770_and_no_revenue(self):
        """The read query must filter on sic_code=6770 AND a NOT EXISTS revenue check -
        not just sic_code alone, which would wrongly exclude a real de-SPAC'd company
        like INV whose SIC code is simply stale."""
        loader = self._make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = []
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._deactivate_blank_check_shells_by_sic_and_revenue()

            sql = mock_read_cur.execute.call_args[0][0]
            assert "sic_code = 6770" in sql
            assert "annual_income_statement" in sql
            assert "revenue > 0" in sql

    def test_no_shells_found_skips_write(self):
        loader = self._make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = []
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._deactivate_blank_check_shells_by_sic_and_revenue()

            # Only the read call happened - DatabaseContext("write") never entered.
            assert mock_db_ctx.call_args_list == [(("read",), {})]


class TestPurgeStaleDownstreamScoreRows:
    """GOVERNANCE 2026-09-01: deactivating a symbol in stock_symbols does nothing to its
    already-computed rows in stock_scores/value_metrics/stability_metrics/growth_metrics/
    momentum_metrics/quality_metrics - downstream loaders only ever fetch active symbols to
    write NEW rows, they never delete stale rows for symbols that later become inactive.
    Live-caught: DDT ("Dillard's Capital Trust I", excluded since 2026-08-31) was still
    ranking #3 in stock_scores' Value top-10 today with its original misattributed-financials
    numbers, because nobody had ever deleted its stale value_metrics/stock_scores rows even
    though stock_symbols.active was correctly false. A live scan found 6 total symbols in
    this state across the 6 tables (DDT, TALK, AXIA, KVAC, MBAV, BNZI). This purge closes the
    gap at its source so it can't recur for any future deactivation.
    """

    def _make_loader(self):
        return MarketConstituentsLoader.__new__(MarketConstituentsLoader)

    def test_purges_all_six_downstream_tables(self):
        loader = self._make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            mock_purge_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.return_value = mock_purge_cur

            loader._purge_stale_downstream_score_rows(["DDT", "TALK"])

            mock_db_ctx.assert_called_once_with("write")
            assert mock_purge_cur.execute.call_count == 6
            tables_deleted = set()
            for call in mock_purge_cur.execute.call_args_list:
                sql, params = call[0]
                assert sql.startswith("DELETE FROM ")
                assert params == (["DDT", "TALK"],)
                tables_deleted.add(sql.split()[2])
            assert tables_deleted == {
                "stock_scores",
                "value_metrics",
                "stability_metrics",
                "growth_metrics",
                "momentum_metrics",
                "quality_metrics",
            }

    def test_empty_symbol_list_skips_db_entirely(self):
        loader = self._make_loader()
        with patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx:
            loader._purge_stale_downstream_score_rows([])
            mock_db_ctx.assert_not_called()
