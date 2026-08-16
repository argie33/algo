"""Regression test: log_db_error() must not truncate params to the point of hiding the
actual failing value.

Gap found 2026-08-16: format_parameters()'s default max_items=10 (sized for log_retry(), which
can genuinely see bulk-operation params) silently hid the real bad value on every DB error -
live-confirmed a NumericValueOutOfRange on a 91-param single-row INSERT (quality_metrics for
GLPI, ~30 numeric columns) logged only the first 10 params ("+81 more"), none of which were the
overflowing field - undiagnosable from the log alone without live-reproducing the whole loader
run. Fixed by raising log_db_error()'s own max_items to 200 - error logging only fires on actual
failures, so the higher cap carries none of the bulk-operation log-spam risk max_items=10 exists
to prevent for log_retry().
"""

import logging

from utils.db.structured_logging import StructuredDBLogger


def test_log_db_error_does_not_truncate_a_91_param_query(caplog):
    params = [f"value_{i}" for i in range(91)]

    with caplog.at_level(logging.ERROR):
        StructuredDBLogger.log_db_error(
            operation_name="insert_quality_metrics",
            query="INSERT INTO quality_metrics (...) VALUES (...)",
            params=params,
            error=ValueError("numeric field overflow"),
            context={"symbol": "GLPI"},
        )

    logged_text = "\n".join(record.message for record in caplog.records)
    assert "value_90" in logged_text, "the 91st (last) param must survive into the error log"
    assert "+81 more" not in logged_text, "error logging must not silently drop the failing value"
