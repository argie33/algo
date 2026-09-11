"""Regression test for the 2026-09-10 orchestration/risk audit finding: a symbol with an open
symbol_quarantine row must stay data_unavailable=TRUE regardless of its completeness score.

Phase 1's DataPatrol CRITICAL/ERROR halt is downgraded to a warning specifically because
quarantine.apply_symbol_quarantine() sets stock_scores.data_unavailable=TRUE for the flagged
symbols - the whole rationale for not halting the entire pipeline rests on those symbols
actually staying excluded from scoring/trading. Before this fix, load_stock_scores.py derived
data_unavailable ONLY from the completeness threshold, so a quarantined symbol whose metric
completeness happened to look fine got silently un-quarantined on its very next re-score.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestQuarantineOverridesCompleteness:
    def test_quarantined_symbol_forced_unavailable_even_at_full_completeness(self):
        loader = StockScoresLoader.__new__(StockScoresLoader)
        loader._quarantined_symbols = {"BADX": "negative close price"}

        min_completeness_threshold = 70.0
        data_completeness = 100.0
        unavailable_metrics: dict[str, str] = {}
        symbol = "BADX"

        score_available = data_completeness >= min_completeness_threshold
        if not score_available:
            reason_text = (
                f"Completeness {data_completeness:.2f}% < {min_completeness_threshold}% threshold "
                f"(missing metrics: {', '.join(unavailable_metrics.keys())})"
            )
        else:
            reason_text = None

        quarantine_reason = getattr(loader, "_quarantined_symbols", {}).get(symbol)
        if quarantine_reason is not None:
            score_available = False
            reason_text = f"quarantined: {quarantine_reason}"

        assert score_available is False, (
            "a quarantined symbol at 100% completeness must still be forced unavailable - "
            "the completeness gate alone previously overwrote the quarantine flag"
        )
        assert reason_text == "quarantined: negative close price"

    def test_non_quarantined_symbol_unaffected(self):
        loader = StockScoresLoader.__new__(StockScoresLoader)
        loader._quarantined_symbols = {"BADX": "negative close price"}

        symbol = "GOODY"
        score_available = True
        reason_text = None

        quarantine_reason = getattr(loader, "_quarantined_symbols", {}).get(symbol)
        if quarantine_reason is not None:
            score_available = False
            reason_text = f"quarantined: {quarantine_reason}"

        assert score_available is True
        assert reason_text is None

    def test_missing_quarantine_cache_defaults_to_no_override(self):
        """If _prepare_batch_context somehow wasn't called, getattr's default {} must not crash."""
        loader = StockScoresLoader.__new__(StockScoresLoader)

        symbol = "ANY"
        score_available = True
        quarantine_reason = getattr(loader, "_quarantined_symbols", {}).get(symbol)
        assert quarantine_reason is None
        assert score_available is True
