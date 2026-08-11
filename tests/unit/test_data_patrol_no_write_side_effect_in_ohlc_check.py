"""Regression test for the 2026-08-11 fix: QualityChecker's identical-OHLC check silently
UPDATEd price_daily.data_quality_flags as a side effect of what is supposed to be a
read-only monitoring/diagnostic pass. data_patrol checks log findings; they must not also
mutate the tables they're inspecting - a monitoring check with an undocumented write
contract is exactly the kind of silent side effect that makes system behavior hard to
reason about, especially with no test ever having covered the write path.
"""

import inspect

from algo.monitoring.data_patrol.checks.quality import QualityChecker


class TestNoWriteSideEffectInOhlcCheck:
    def test_quality_checker_source_has_no_price_daily_update(self):
        source = inspect.getsource(QualityChecker)
        assert "UPDATE price_daily" not in source, (
            "data_patrol checks must be read-only diagnostics - QualityChecker must not "
            "write back to price_daily as a side effect of the identical-OHLC check"
        )
