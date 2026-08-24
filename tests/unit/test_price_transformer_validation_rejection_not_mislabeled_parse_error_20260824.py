#!/usr/bin/env python3
"""Regression test: a price-validation rejection (bad OHLC, price gap > 30%) must not be
counted or logged as a "parse error".

PriceTransformer._process_row used to return the SAME counter slot for a true date-parse
failure and for a price-validation rejection - so validate_and_transform()'s aggregate "High
rejection rate" WARNING said "N parse errors" even when every rejected row had a perfectly
parseable date and was instead rejected by _validate_row_prices() (e.g. a real price-gap
anomaly). Live-confirmed 2026-08-24: LGCL's real run logged "4 parse errors out of 5 rows"
when the actual per-row reason was "price gap > 30%: 0.083 -> 0.057" - a correctly-caught
data-quality rejection, not a parsing bug. This test locks in that the two failure modes are
now counted (and logged) separately.
"""

from unittest.mock import patch

from loaders.price_transformer import PriceTransformer


class TestValidationRejectionNotMislabeledParseError:
    def test_price_gap_rejection_not_counted_as_parse_error(self):
        transformer = PriceTransformer(asset_class="stock")

        rows = [
            {
                "symbol": "LGCL",
                "date": "2026-08-17",
                "open": 0.085,
                "high": 0.090,
                "low": 0.080,
                "close": 0.083,
                "volume": 500000,
            },
            # Real price-gap anomaly (>30% move, no matching split) - correctly rejected by
            # _validate_row_prices(), not a parse failure.
            {
                "symbol": "LGCL",
                "date": "2026-08-18",
                "open": 0.060,
                "high": 0.062,
                "low": 0.055,
                "close": 0.057,
                "volume": 900000,
            },
        ]

        with patch("loaders.price_transformer.logger") as mock_logger:
            transformer.validate_and_transform(rows)

            warning_calls = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
            summary_calls = [c for c in warning_calls if "High rejection rate" in c or "rejection rate" in c.lower()]

        assert summary_calls, "expected a rejection-rate summary log for a 50% single-row rejection"
        summary = summary_calls[-1]
        assert "0 parse errors" in summary, (
            f"a price-gap rejection is not a parse error and must not inflate the parse-error count: {summary!r}"
        )
        assert "1 validation rejections" in summary, (
            f"the price-gap rejection must be counted as a validation rejection: {summary!r}"
        )

    def test_process_row_still_returns_4_values(self):
        """_process_row's return signature grew a 4th element (validation_rejected_count) -
        pin the shape so a future edit can't silently collapse it back to 3 and re-conflate
        the two failure modes."""
        transformer = PriceTransformer(asset_class="stock")
        result = transformer._process_row(
            {"symbol": "TEST", "date": "not-a-date", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            trading_day_set=set(),
            prior_close_by_symbol={},
            tracker=None,
        )
        assert len(result) == 4
        is_valid, non_trading, parse_error, validation_rejected = result
        assert is_valid is False
        assert parse_error == 1
        assert validation_rejected == 0
