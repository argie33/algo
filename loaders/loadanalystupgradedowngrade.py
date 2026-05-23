#!/usr/bin/env python3
"""Analyst Upgrade/Downgrade Loader — fetches rating change history from yfinance.

Table: analyst_upgrade_downgrade
Primary key: (symbol, action_date, firm)

Run: python3 loaders/loadanalystupgradedowngrade.py [--symbols AAPL,MSFT] [--parallelism 4]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date, timedelta
from typing import List, Optional

from utils.yfinance_wrapper import get_ticker

from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

log = logging.getLogger(__name__)

def _detect_action(old_grade: str, new_grade: str) -> str:
    """Infer upgrade/downgrade/initiation from rating change."""
    RANK = {"strong buy": 5, "buy": 4, "outperform": 4, "overweight": 4,
            "hold": 3, "neutral": 3, "market perform": 3,
            "underperform": 2, "underweight": 2, "reduce": 2,
            "sell": 1, "strong sell": 1}
    old = RANK.get(str(old_grade).lower().strip(), 0)
    new = RANK.get(str(new_grade).lower().strip(), 0)
    if not old_grade or old_grade in ("", "None", "-"):
        return "initiated"
    if new > old:
        return "upgrade"
    if new < old:
        return "downgrade"
    return "reiterate"

class AnalystUpgradeDowngradeLoader(OptimalLoader):
    table_name = "analyst_upgrade_downgrade"
    primary_key = ("symbol", "action_date", "firm")
    watermark_field = "action_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        try:
            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = get_ticker(yf_symbol)

            upgrades = ticker.upgrades_downgrades
            if upgrades is None or (hasattr(upgrades, "empty") and upgrades.empty):
                return None

            rows = []
            cutoff_str = since.isoformat() if since else (date.today() - timedelta(days=2 * 365)).isoformat()

            for idx, row in upgrades.iterrows():
                try:
                    if hasattr(idx, "date"):
                        action_date = idx.date().isoformat()
                    else:
                        action_date = str(idx)[:10]

                    if action_date <= cutoff_str:
                        continue

                    firm = str(row.get("Firm") or row.get("firm") or "")[:100]
                    old_grade = str(row.get("FromGrade") or row.get("from_grade") or "")[:50]
                    new_grade = str(row.get("ToGrade") or row.get("to_grade") or "")[:50]
                    action = _detect_action(old_grade, new_grade)

                    # Company name from the row if available
                    company_name = ""

                    rows.append({
                        "symbol": symbol,
                        "action_date": action_date,
                        "firm": firm,
                        "old_rating": old_grade,
                        "new_rating": new_grade,
                        "action": action,
                        "company_name": company_name,
                    })
                except Exception as e:
                    log.debug("Skipping upgrade/downgrade row for %s: %s", symbol, e)

            return rows if rows else None

        except Exception as e:
            log.debug("Upgrade/downgrade error for %s: %s", symbol, e)
            return None

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        return bool(row.get("firm")) and bool(row.get("action_date"))

def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = AnalystUpgradeDowngradeLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
        if fail_rate > 0.05:
            logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
            return 1
        return 0

if __name__ == "__main__":
    sys.exit(main())
