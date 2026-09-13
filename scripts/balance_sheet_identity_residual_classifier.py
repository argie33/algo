#!/usr/bin/env python3
"""Classifies balance_sheet_identity's confirmed-fresh violations by KNOWN residual signature,
instead of leaving a flat "N confirmed-fresh, go investigate" count for a human to re-derive by
hand every time (which is how the 2026-09-13 NCI-double-count bug - 84 symbols, ~39% of that
day's backlog - and the DIS-shaped liabilities-derivation sibling were actually found: manual
one-off SQL against the flagged population, symbol by symbol).

This is the "find these in bulk" tool that session's ad hoc investigation should have been from
the start - a signature is a closed-form relationship between the residual and other already-
extracted fields (e.g. residual == -noncontrolling_interest) that, when it matches, identifies
the SAME root cause as a previously-fixed bug without needing a fresh live SEC lookup per
symbol. Run this FIRST when triaging a new balance_sheet_identity/quarterly_balance_sheet_identity
warning, before spending time on one-off companyfacts fetches - it tells you how much of the
count is already explained by a known pattern (and whether any of your registered signatures'
"fixed" claim has quietly regressed) versus how much is genuinely unclassified and worth a
fresh investigation.

Signatures are intentionally a flat, auditable list here (not a plugin/registry abstraction) -
add a new one by appending a `_Signature` instance with a `matches(row) -> bool` and a `note`.

Usage:
    python scripts/balance_sheet_identity_residual_classifier.py               # annual
    python scripts/balance_sheet_identity_residual_classifier.py --period quarterly
    python scripts/balance_sheet_identity_residual_classifier.py --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

IDENTITY_TOLERANCE_PCT = 0.01


@dataclass(frozen=True)
class _Signature:
    name: str
    note: str
    matches: Callable[[dict[str, float]], bool]


def _residual_matches(row: dict[str, float], field: str, tol_frac: float = 0.001) -> bool:
    val = row.get(field, 0.0)
    if val == 0:
        return False
    tol = max(1.0, abs(val) * tol_frac)
    return abs(row["residual"] + val) < tol


SIGNATURES: list[_Signature] = [
    _Signature(
        name="nci_double_count",
        note=(
            "residual == -noncontrolling_interest: liabilities+equity alone already balance to "
            "assets - fixed for the IFRS Equity-total case (10b444644) and the "
            "liabilities-from-assets-minus-equity derivation case (7e2454582) on 2026-09-13. A "
            "match here after a reload means either a NEW variant of the same bug (e.g. the "
            "GAAP StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest path, "
            "not yet checked) or a genuinely-unfixable filer-side tagging quirk - not noise."
        ),
        matches=lambda row: _residual_matches(row, "nci"),
    ),
    _Signature(
        name="temp_equity_double_count",
        note="residual == -temporary_equity: same double-count shape as nci_double_count, mezzanine-equity side - not yet fixed anywhere, treat any match as a fresh lead.",
        matches=lambda row: _residual_matches(row, "te"),
    ),
    _Signature(
        name="temp_equity_missing_entirely",
        note=(
            "temporary_equity/noncontrolling_interest both zero AND |residual| roughly equals "
            "assets minus (liabilities+equity) with liabilities+equity small relative to "
            "assets (SPAC/Up-C trust-account shape, HDRN/MRLN/IMSR-style) - confirmed 2026-09-13 "
            "this is a companyfacts API dimensional-fact-drop limitation, NOT a quick "
            "concept-mapping fix. Do not attempt to map an asset-side concept "
            "(AssetsHeldInTrustNoncurrent) into temporary_equity to close this - verified that "
            "double-counts the trust assets."
        ),
        matches=lambda row: (
            row.get("nci", 0.0) == 0.0
            and row.get("te", 0.0) == 0.0
            and row["liab"] + row["eq"] < 0.05 * row["assets"]
            and abs(row["residual"]) > 0.5 * row["assets"]
        ),
    ),
]


def _classify(cur: Any, period: str) -> dict[str, Any]:
    table = "annual_balance_sheet" if period == "annual" else "quarterly_balance_sheet"
    distinct_extra = ", i.fiscal_quarter" if period == "quarterly" else ""
    order_extra = ", i.fiscal_quarter" if period == "quarterly" else ""

    cur.execute(
        "SELECT last_success_at FROM data_loader_status WHERE table_name = %s",
        (table,),
    )
    watermark_row = cur.fetchone()
    watermark = watermark_row[0] if watermark_row else None

    cur.execute(
        f"""
        SELECT DISTINCT ON (i.symbol{distinct_extra})
            i.symbol, i.total_assets AS assets, i.total_liabilities AS liab,
            i.stockholders_equity AS eq, COALESCE(i.noncontrolling_interest, 0) AS nci,
            COALESCE(i.temporary_equity, 0) AS te, i.updated_at AS updated_at
        FROM {table} i
        JOIN stock_symbols s ON s.symbol = i.symbol AND s.active = true
        WHERE i.data_unavailable = FALSE
          AND i.total_assets IS NOT NULL AND i.total_liabilities IS NOT NULL
          AND i.stockholders_equity IS NOT NULL AND i.total_assets != 0
        ORDER BY i.symbol{order_extra}, i.fiscal_year DESC
        """,
    )

    unclassified: list[dict[str, Any]] = []
    by_signature: dict[str, int] = {sig.name: 0 for sig in SIGNATURES}
    total_flagged = 0
    total_confirmed_fresh = 0

    for db_row in cur.fetchall():
        symbol = db_row["symbol"]
        assets, liab, eq, nci, te = (
            float(db_row["assets"]),
            float(db_row["liab"]),
            float(db_row["eq"]),
            float(db_row["nci"]),
            float(db_row["te"]),
        )
        updated_at = db_row["updated_at"]
        implied = liab + eq + nci + te
        residual = assets - implied
        tol = max(1.0, abs(assets) * IDENTITY_TOLERANCE_PCT)
        if abs(residual) <= tol:
            continue
        total_flagged += 1
        if watermark is not None and (updated_at is None or updated_at < watermark):
            continue  # unverified/stale, same discipline as _staleness_split
        total_confirmed_fresh += 1

        row = {"assets": assets, "liab": liab, "eq": eq, "nci": nci, "te": te, "residual": residual}
        matched = next((sig for sig in SIGNATURES if sig.matches(row)), None)
        if matched:
            by_signature[matched.name] += 1
        else:
            unclassified.append({"symbol": symbol, "residual": residual, **row})

    unclassified.sort(key=lambda r: abs(r["residual"]), reverse=True)
    return {
        "period": period,
        "total_flagged": total_flagged,
        "confirmed_fresh": total_confirmed_fresh,
        "by_signature": by_signature,
        "unclassified_count": len(unclassified),
        "unclassified_top20": unclassified[:20],
        "signature_notes": {sig.name: sig.note for sig in SIGNATURES},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--period", choices=["annual", "quarterly"], default="annual")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from utils.db.context import DatabaseContext

    with DatabaseContext("read") as cur:
        result = _classify(cur, args.period)

    if args.json:
        print(json.dumps(result, default=str, indent=2))
    else:
        logger.info(
            f"{args.period}: {result['confirmed_fresh']} confirmed-fresh / {result['total_flagged']} total flagged"
        )
        for name, count in result["by_signature"].items():
            logger.info(f"  {name}: {count}")
        logger.info(f"  unclassified: {result['unclassified_count']}")
        for row in result["unclassified_top20"][:10]:
            logger.info(f"    {row}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
