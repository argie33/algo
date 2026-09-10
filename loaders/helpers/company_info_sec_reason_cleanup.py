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


def reclassify_stale_registered_investment_company_reason() -> None:
    """Relabel a stale generic "no_annual_report_filing" reason to the specific
    "registered_investment_company_no_annual_report" one for rows that already carry the
    CEF/RIC signature (entity_type in ('other','investment'), sic_code NULL) on their OWN
    row - a companion self-heal to clear_stale_shares_outstanding_reason() above, for the
    "reason needs relabeling" case rather than the "reason needs clearing" case.

    FOUND 2026-09-09/10 (goal: "SEC/XBRL missing data under 500" sweep): the 2026-09-06 fix
    to fetch_incremental() (this loader's own `shares_outstanding_unavailable_reason =
    "registered_investment_company_no_annual_report" if entity_type in (...) and sic_code is
    None else "no_annual_report_filing"` branch) can only ever fire for a symbol this run's
    `symbols` list actually contains - and this loader's `exclude_etfs_from_symbols = True`
    (inherited from SecLoaderBase) means `runner.py` builds that list via
    `get_active_symbols(exclude_etfs=True)`, which excludes exactly this same
    entity_type/sic_code signature (see utils/loaders/helpers.py's own 2026-08-20 comment on
    that filter). A symbol correctly classified as a CEF by any earlier run becomes
    permanently invisible to every later run of THIS loader - the very row the 2026-09-06
    fix was written to correct can never reach `fetch_incremental()` again to have that fix
    applied. Live-confirmed 88 rows DB-wide (BCAT/GAB/GGN/PIM/VKQ/HQH/GDV/HQH/IIM/BGY/VCV/
    VMO/VVR and dozens of siblings) stuck at the pre-fix generic reason, last touched
    2026-08-26 (10+ days before the relabeling fix even landed). Pure column-to-column
    relabeling using data already on the row (no live SEC call, no risk of overwriting a
    real classification) - same "the row's own current data is the correct source of truth"
    principle as clear_stale_shares_outstanding_reason() above.
    """
    with DatabaseContext("write") as cur:
        cur.execute(
            """
            UPDATE company_info_sec
            SET shares_outstanding_unavailable_reason = 'registered_investment_company_no_annual_report'
            WHERE shares_outstanding_unavailable_reason = 'no_annual_report_filing'
              AND entity_type IN ('other', 'investment')
              AND sic_code IS NULL
            """
        )
        if cur.rowcount:
            logger.info(
                f"[company_info_sec] post_run: reclassified {cur.rowcount} row(s) from the generic "
                f"'no_annual_report_filing' to 'registered_investment_company_no_annual_report' "
                f"based on their own entity_type/sic_code CEF signature"
            )
