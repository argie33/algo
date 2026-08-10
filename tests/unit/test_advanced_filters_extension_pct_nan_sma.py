#!/usr/bin/env python3
"""Regression test for AdvancedFilters._extension_pct, found via a systematic sweep for
the NaN-comparison-guard bug class on 2026-08-10 (after fuzzing found 8 other instances
this session).

`float(row[0]) <= 0` doesn't catch NaN (NaN comparisons are always False in Python) - a
NaN sma_50 silently produced ext_pct=nan, which then cascaded through
_extension_risk_score's own chain of `<`/`<=` comparisons (also all silently False for
NaN) to fall through to its worst-case 0.0 return. This fails toward rejecting the stock
rather than favoring it (lower severity than the other instances this session, several of
which silently favored the corrupted-data case), but a NaN input should raise here, not
silently cascade through several unrelated comparisons in a different function.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from algo.signals.advanced_filters import AdvancedFilters

BASE_CONFIG = {
    "strong_sector_top_n": 5,
    "block_days_before_earnings": 5,
    "max_extension_above_50ma_pct": 15.0,
    "min_avg_daily_dollar_volume": 500_000,
    "require_strong_sector": False,
}


def _filters():
    return AdvancedFilters(dict(BASE_CONFIG))


class TestExtensionPctRejectsNanSma:
    def test_nan_sma_raises_not_silently_returns_nan(self):
        filters = _filters()
        fake_cur = MagicMock()
        fake_cur.fetchone.return_value = (float("nan"),)

        with pytest.raises(ValueError, match="50-day SMA invalid"):
            filters._extension_pct("CHAOSFUZZ", date(2026, 8, 10), 100.0, fake_cur)

    def test_infinite_sma_raises(self):
        filters = _filters()
        fake_cur = MagicMock()
        fake_cur.fetchone.return_value = (float("inf"),)

        with pytest.raises(ValueError, match="50-day SMA invalid"):
            filters._extension_pct("CHAOSFUZZ", date(2026, 8, 10), 100.0, fake_cur)

    def test_normal_sma_still_works(self):
        filters = _filters()
        fake_cur = MagicMock()
        fake_cur.fetchone.return_value = (150.0,)

        result = filters._extension_pct("AAPL", date(2026, 8, 10), 165.0, fake_cur)
        assert result == 10.0
