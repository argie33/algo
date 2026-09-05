"""Post-run self-heal for company_info_sec's shares_outstanding_unavailable_reason.

Split out of loaders/load_company_info_sec.py (2026-09-05, file-size ratchet: that file is
an already-oversized legacy bloater, growth blocked) - body verbatim, only moved.

FOUND 2026-09-05 (goal: "Missing SEC/XBRL data" reduction to zero): putting
`shares_outstanding_unavailable_reason` in preserve_on_missing_fields (2026-09-04 fix in
load_company_info_sec.py) only protects a CORRECT reason from being overwritten when a run's
fetch comes back None - it can't ever CLEAR a reason, because
`COALESCE(EXCLUDED.col, existing.col)` has no way to write NULL over a non-NULL existing
value; a NULL EXCLUDED side always falls back to the (stale) existing value instead. So a
symbol whose reason was set to "shares_outstanding_not_in_xbrl_or_filing_text" by an old
run, before a later code fix (dual-class xmlns/Series-label resolution, WeightedAverage
fallback, etc.) taught the loader to actually find its real shares_outstanding, keeps that
stale reason forever even once the real value is on file - it can never self-heal via the
normal per-symbol write path. Live-confirmed 67 active-universe rows this way (AMH, DDS,
ARTNA, F, SF, BBBY among them) - each with a real, current shares_outstanding value sitting
right next to a "not found" label, each still counting as a live "Missing SEC/XBRL data" gap
on the coverage dashboard. Same "the row's actual column values are the correct source of
truth, not a possibly-stale flag" principle as load_financial_statements.py's own post_run()
rescue - a direct UPDATE is the only way to actually clear it, since the normal per-symbol
upsert path structurally cannot.
"""

import logging

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def clear_stale_shares_outstanding_reason() -> None:
    """Clear shares_outstanding_unavailable_reason wherever shares_outstanding is already
    non-NULL - the only way to actually clear a stale reason, since the normal per-symbol
    upsert path (COALESCE-preserve) structurally cannot."""
    with DatabaseContext("write") as cur:
        cur.execute(
            """
            UPDATE company_info_sec
            SET shares_outstanding_unavailable_reason = NULL
            WHERE shares_outstanding IS NOT NULL
              AND shares_outstanding_unavailable_reason IS NOT NULL
            """
        )
        if cur.rowcount:
            logger.info(
                f"[company_info_sec] post_run: cleared stale shares_outstanding_unavailable_reason "
                f"on {cur.rowcount} row(s) with a real shares_outstanding value already on file"
            )
