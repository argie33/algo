#!/usr/bin/env python3
"""FINRA Short Interest Data Fetcher - FINRA Query API (no yfinance).

FINRA publishes Regulation SHO short interest data bi-weekly (settlement dates
are the 15th and last calendar day of each month; published roughly 2-3 weeks
later after the reporting cycle closes).

Data source: FINRA Query API, dataset "Consolidated Short Interest"
  POST https://api.finra.org/data/group/otcMarket/name/ConsolidatedShortInterest
Coverage: ALL FINRA-member-reported equities (NYSE, Nasdaq, and OTC) - verified
  against live data (e.g. AAPL/NNM, A/NYSE both present), not just OTC/pink-sheet
  names despite the "otcMarket" API group name (that's the FINRA API's internal
  namespace, not a coverage filter).
No API key required for read access; response includes raw share counts (not a
percentage), so percent-of-shares-outstanding must be computed by the caller
using an independent shares-outstanding source (company_info_sec).

Usage:
  fetcher = FINRAShortInterestFetcher()
  data, settlement_date = fetcher.fetch_latest()  # {symbol: {"short_shares": int, "days_to_cover": float}, ...}
"""

import logging
from datetime import date, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

FINRA_API_URL = "https://api.finra.org/data/group/otcMarket/name/ConsolidatedShortInterest"
PAGE_SIZE = 5000  # FINRA Query API record-max-limit per request


class FINRAShortInterestFetcher:
    """Fetches short interest data from FINRA's Consolidated Short Interest Query API.

    Key advantages over yfinance:
    - No rate limiting for reasonable use (single-digit requests per run)
    - Authoritative regulatory source (FINRA Reg SHO), covers NYSE/Nasdaq/OTC
    - Raw share counts (caller computes % using shares_outstanding)
    """

    def __init__(self, timeout_sec: int = 30) -> None:
        self.timeout = timeout_sec

    def fetch_latest(self) -> tuple[dict[str, dict[str, Any]], date | None]:
        """Fetch the most recently published FINRA short interest settlement cycle.

        Settlement dates are always the 15th or last day of the month. Walks
        backward from today (skipping cycles FINRA hasn't published yet) until
        it finds a settlement date with data.

        Returns:
            Tuple of (data, settlement_date):
            - data: {symbol: {"short_shares": int, "days_to_cover": float | None,
              "avg_daily_volume": int | None}}
            - settlement_date: the FINRA settlement date the data belongs to, or
              None if no cycle within the lookback window had data.
        """
        for candidate in self._candidate_settlement_dates():
            try:
                data = self.fetch_date(candidate)
            except RuntimeError as e:
                logger.debug(f"[FINRA] {candidate} fetch failed: {e}")
                continue
            if data:
                logger.info(
                    f"[FINRA] Fetched short interest for settlement date {candidate} "
                    f"({len(data)} symbols)"
                )
                return data, candidate

        logger.warning("[FINRA] No published short interest cycle found in lookback window")
        return {}, None

    @staticmethod
    def _candidate_settlement_dates(cycles_back: int = 4) -> list[date]:
        """Generate the last N settlement dates (15th/EOM) at or before today, newest first."""
        candidates: list[date] = []
        year, month = date.today().year, date.today().month
        while len(candidates) < cycles_back:
            # end-of-month settlement date
            if month == 12:
                eom = date(year, 12, 31)
            else:
                eom = date(year, month + 1, 1) - timedelta(days=1)
            mid = date(year, month, 15)

            for d in (eom, mid):
                if d <= date.today():
                    candidates.append(d)

            month -= 1
            if month == 0:
                month = 12
                year -= 1

        candidates.sort(reverse=True)
        return candidates[:cycles_back]

    def fetch_date(self, target_date: date) -> dict[str, dict[str, Any]]:
        """Fetch FINRA consolidated short interest for a specific settlement date.

        Paginates through the full result set (FINRA caps each page at
        `record-max-limit`, typically 5000 rows).

        Args:
            target_date: Settlement date to fetch (15th or last day of a month)

        Returns:
            Dict[symbol, {"short_shares": int, "days_to_cover": float | None,
            "avg_daily_volume": int | None}]

        Raises:
            RuntimeError: If the request fails
        """
        data: dict[str, dict[str, Any]] = {}
        offset = 0

        while True:
            payload = {
                "compareFilters": [
                    {
                        "compareType": "EQUAL",
                        "fieldName": "settlementDate",
                        "fieldValue": target_date.isoformat(),
                    }
                ],
                "limit": PAGE_SIZE,
                "offset": offset,
            }
            try:
                response = requests.post(
                    FINRA_API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise RuntimeError(
                    f"[FINRA] HTTP error fetching short interest for {target_date}: {e}"
                ) from e

            # FINRA returns 204 No Content (empty body) when a query matches zero rows.
            if response.status_code == 204 or not response.content:
                break
            rows = response.json()
            if not rows:
                break

            for row in rows:
                symbol = row.get("symbolCode")
                short_shares = row.get("currentShortPositionQuantity")
                if not symbol or short_shares is None:
                    continue
                data[symbol.strip().upper()] = {
                    "short_shares": int(short_shares),
                    "days_to_cover": row.get("daysToCoverQuantity"),
                    "avg_daily_volume": row.get("averageDailyVolumeQuantity"),
                }

            record_total = int(response.headers.get("record-total", len(rows)))
            offset += len(rows)
            if offset >= record_total or len(rows) < PAGE_SIZE:
                break

        return data
