#!/usr/bin/env python3
"""Backfill historical SEC Form 13F bulk datasets into institutional_holdings_13f_history.

ADDED 2026-09-14 (scores-input data-depth investigation): `load_institutional_holdings_13f.py`'s
`_discover_latest_13f_bulk_dataset()` only ever fetches the single most recent published bulk
dataset - by design, since `institutional_holdings_13f`'s primary key is `symbol` alone (a
current-snapshot table, see migration 1291's own comment for why it structurally can't hold
history). SEC's real dataset listing page (`SEC_13F_DATASETS_PAGE`) publishes a live-verified
10 historical bulk .zip files (rolling ~3-month windows back to 2024-01-01 - that's the real
ceiling SEC exposes via this page, not a scraping bug on our side).

This script fetches ALL of them (reusing InstitutionalHoldings13FLoader's own parsing/crosswalk
methods directly - not a reimplementation) and writes into the separate
institutional_holdings_13f_history table (migration 1291), one row per (symbol, filing_date).
Does not touch institutional_holdings_13f or the regular loader's run()/fetch_global() path -
purely additive.

Run:
    python scripts/backfill_institutional_holdings_13f_history.py
    python scripts/backfill_institutional_holdings_13f_history.py --dry-run
"""

import argparse
import logging
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from loaders.load_institutional_holdings_13f import (  # noqa: E402
    SEC_13F_DATASETS_PAGE,
    InstitutionalHoldings13FLoader,
)
from utils.db.context import DatabaseContext  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ZIP_LINK_RE = re.compile(
    r'href="(/files/[a-z]+/data/form-13f-data-sets/(\d{2}[a-z]{3}\d{4})-(\d{2}[a-z]{3}\d{4})_form13f\.zip)"',
    re.IGNORECASE,
)


def _discover_all_13f_bulk_datasets(loader: InstitutionalHoldings13FLoader) -> list[tuple[str, "datetime"]]:
    """Every historical bulk dataset SEC's listing page currently publishes, oldest first.

    Same scraping approach as the production loader's `_discover_latest_13f_bulk_dataset` -
    just keeps every match instead of only the one with the latest end date.
    """
    req = urllib.request.Request(SEC_13F_DATASETS_PAGE, headers={"User-Agent": "algo-trading argeropolos@gmail.com"})
    with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310 - hardcoded https:// constant
        html = response.read().decode("utf-8", errors="replace")

    datasets = []
    for path, _start_str, end_str in _ZIP_LINK_RE.findall(html):
        try:
            end_date = loader._parse_ddmmmyyyy(end_str)
        except (KeyError, ValueError):
            continue
        datasets.append((f"https://www.sec.gov{path}", end_date))
    datasets.sort(key=lambda x: x[1])
    return datasets


def backfill(dry_run: bool) -> None:
    loader = InstitutionalHoldings13FLoader()
    datasets = _discover_all_13f_bulk_datasets(loader)
    logger.info(f"[13F BACKFILL] {len(datasets)} historical bulk datasets discovered on SEC's listing page")

    with DatabaseContext("read") as cur:
        cur.execute("SELECT DISTINCT filing_date FROM institutional_holdings_13f_history")
        already_have = {row[0] for row in cur.fetchall()}

    tracked_cusips = loader._get_known_tracked_cusips()

    for url, period_end in datasets:
        if period_end in already_have:
            logger.info(f"[13F BACKFILL] {period_end}: already present, skipping")
            continue
        logger.info(f"[13F BACKFILL] Fetching {url} (period end {period_end})...")
        try:
            holdings_by_cusip, manager_holdings_by_cusip = loader._fetch_and_parse_13f_bulk(url, tracked_cusips)
        except Exception as e:
            logger.warning(f"[13F BACKFILL] {period_end}: fetch/parse failed ({type(e).__name__}: {e}), skipping")
            continue

        holdings_by_ticker, manager_holdings_by_ticker = loader._crosswalk_to_tickers(
            holdings_by_cusip, manager_holdings_by_cusip
        )
        records = loader._calculate_and_cache_ownership(holdings_by_ticker, period_end, manager_holdings_by_ticker)
        # Only real resolved/zero-holdings rows belong in a historical panel - skip the
        # data_unavailable markers _calculate_and_cache_ownership also emits for every
        # active symbol (that's the right behavior for the current-snapshot production
        # table, which must explicitly mark absence; a history table should only carry
        # rows we actually observed for that period, same convention as the FINRA backfill).
        real_records = [r for r in records if not r["data_unavailable"]]

        if not dry_run:
            now_et = datetime.now(EASTERN_TZ)
            with DatabaseContext("write") as cur:
                for r in real_records:
                    cur.execute(
                        """
                        INSERT INTO institutional_holdings_13f_history
                        (symbol, filing_date, institutional_ownership_pct, number_of_institutional_holders,
                         top_10_institutions_pct, data_unavailable, reason, data_source, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, filing_date) DO NOTHING
                        """,
                        (
                            r["symbol"],
                            period_end,
                            r["institutional_ownership_pct"],
                            r["number_of_institutional_holders"],
                            r["top_10_institutions_pct"],
                            r["data_unavailable"],
                            r["reason"],
                            "sec_form13f_bulk_backfill",
                            now_et,
                        ),
                    )
        logger.info(
            f"[13F BACKFILL] {period_end}: {len(real_records)} real ownership rows "
            f"{'(dry-run)' if dry_run else 'written'}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report, don't write to DB")
    args = parser.parse_args()
    backfill(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
