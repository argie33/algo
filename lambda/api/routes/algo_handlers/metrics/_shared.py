"""Shared helper used by more than one algo metrics handler.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
`_compute_data_age_seconds` is used by both `performance._get_algo_performance` and
`performance_analytics._get_performance_analytics`, so it lives here rather than in
either handler's own module. Pure move, no logic changed - body is byte-for-byte
identical to the pre-split version (only the import header differs, trimmed to this
function's actual dependencies).
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
from datetime import datetime
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import safe_dict_convert


def _compute_data_age_seconds(cur: cursor, last_write_at: Any, context: str) -> int:
    """Compute seconds since a DB timestamp using DB-side NOW() (avoids app/DB clock skew).

    Mirrors the age computation _get_algo_portfolio has used since the portfolio panel's
    "always 0/always stale" bug (data_age_seconds vs. DATE-only snapshot_date - see that
    function's docstring for the full incident). FAIL-FAST: raises if the timestamp is
    missing or the DB clock read fails, rather than silently reporting age 0.
    """
    if last_write_at is None:
        raise RuntimeError(f"{context}: missing timestamp - cannot compute data age")
    cur.execute("SELECT NOW()::timestamp")
    now_row = cur.fetchone()
    if not now_row:
        raise RuntimeError(f"{context}: database NOW() returned empty")
    now_row = safe_dict_convert(now_row)
    now_db = now_row.get("now")
    if now_db is None:
        raise RuntimeError(f"{context}: database NOW()::timestamp returned NULL")
    if not isinstance(last_write_at, datetime) or not isinstance(now_db, datetime):
        raise RuntimeError(
            f"{context}: type mismatch computing age - now_db={type(now_db).__name__}, "
            f"last_write_at={type(last_write_at).__name__}"
        )
    if last_write_at.tzinfo is not None:
        last_write_at = last_write_at.replace(tzinfo=None)
    if now_db.tzinfo is not None:
        now_db = now_db.replace(tzinfo=None)
    return int((now_db - last_write_at).total_seconds())
