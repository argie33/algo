#!/usr/bin/env python3
"""Economic Calendar Loader - forward-looking macro event dates.

FOUND (2026-08-24, real-money-readiness goal session): `economic_calendar` had 13 rows,
all dated 2026-06-01/03, zero future events, and no loader anywhere in git history despite
`terraform/modules/monitoring/loader-monitoring.tf` listing it as a monitored table. Infra
expected a loader that was never built. This is that loader.

Two sources, matching the existing (stale) seed data's event_id convention:

1. FRED release/dates API (https://fred.stlouisfed.org/docs/api/fred/release_dates.html) -
   real, live, already-configured (same FRED_API_KEY used by load_economic_data.py) schedule
   of upcoming release dates for major market-moving releases: CPI, Employment Situation
   (NFP), GDP, Personal Income and Outlays (PCE). FRED does not publish forecast/actual
   values on the release-date entity itself (those are per-series observations, not a
   forecast concept), so forecast_value/actual_value/previous_value stay NULL here - same
   shape as the original seed rows.

2. FOMC meeting dates - the Federal Reserve does not expose these via a clean FRED release,
   so this uses the Fed's own officially published calendar
   (https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), statically listed
   below. This is real, dated, authoritative public data (the Fed publishes it 12+ months
   ahead and meeting dates essentially never change once announced) - not a placeholder or
   guess - but it needs a manual refresh once a year when the Fed publishes next year's
   calendar. FOMC_MEETING_DATES below is intentionally the single place to update.

FAIL-FAST GOVERNANCE: raises RuntimeError on real failures instead of silently returning
empty results, matching every other loader in this codebase.
"""

import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import requests  # noqa: E402

from algo.config.api_endpoints import get_fred_url  # noqa: E402
from loaders.load_economic_data import get_fred_api_key  # noqa: E402
from loaders.timeout_config import configure_socket_timeout, get_http_timeout  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.loaders.status_manager import LoaderStatusManager  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

configure_socket_timeout(30)

# FRED release_id -> (short code for event_id, display name, importance).
# release_id values verified live 2026-08-24 via GET /fred/release?release_id=<id>.
FRED_RELEASES: dict[int, tuple[str, str, str]] = {
    10: ("CPI", "Consumer Price Index", "HIGH"),
    50: ("NFP", "Employment Situation", "HIGH"),
    53: ("GDP", "Gross Domestic Product", "HIGH"),
    54: ("PCE", "Personal Income and Outlays", "MEDIUM"),
}

# Federal Reserve's officially published FOMC meeting-decision dates (second day of each
# two-day meeting, when the rate decision is announced). Source:
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm - update this list once a
# year when the Fed publishes the next calendar year's schedule; not derivable from FRED.
FOMC_MEETING_DATES: list[str] = [
    "2026-01-28",
    "2026-03-18",
    "2026-04-29",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-16",
]


def fetch_fred_release_dates(api_key: str, release_id: int, start_date: date) -> list[str]:
    """Fetch real upcoming/recent release dates for a FRED release_id.

    Returns: list of ISO date strings from `start_date` onward.

    Raises:
        RuntimeError: on any HTTP/API failure (fail-fast, no silent empty-list swallow).
    """
    url = f"{get_fred_url()}/release/dates"
    try:
        response = requests.get(
            url,
            params={
                "release_id": release_id,
                "api_key": api_key,
                "file_type": "json",
                "include_release_dates_with_no_data": "true",
                "sort_order": "asc",
                "realtime_start": start_date.isoformat(),
            },
            timeout=get_http_timeout(),
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        raise RuntimeError(
            f"[ECONOMIC_CALENDAR] FRED release/dates request failed for release_id={release_id}: {e}"
        ) from e
    except ValueError as e:
        raise RuntimeError(
            f"[ECONOMIC_CALENDAR] FRED release/dates returned invalid JSON for release_id={release_id}: {e}"
        ) from e

    release_dates = data.get("release_dates")
    if release_dates is None:
        raise RuntimeError(
            f"[ECONOMIC_CALENDAR] FRED release/dates response missing 'release_dates' key for "
            f"release_id={release_id}: {data}"
        )
    return [d["date"] for d in release_dates if "date" in d]


def build_events(api_key: str) -> list[dict[str, Any]]:
    """Assemble the full set of calendar events to upsert: FRED releases + FOMC meetings."""
    today = date.today()
    events: list[dict[str, Any]] = []

    for i, (release_id, (short_code, display_name, importance)) in enumerate(FRED_RELEASES.items()):
        if i > 0:
            time.sleep(2.0)  # matches load_economic_data.py's FRED rate-limit courtesy
        dates = fetch_fred_release_dates(api_key, release_id, today - timedelta(days=30))
        for d in dates:
            events.append(
                {
                    "event_id": f"FRED_{short_code}_{d}",
                    "event_date": d,
                    "event_name": display_name,
                    "category": "Economic",
                    "country": "US",
                    "importance": importance,
                }
            )

    for d in FOMC_MEETING_DATES:
        events.append(
            {
                "event_id": f"FOMC_{d}",
                "event_date": d,
                "event_name": "FOMC Meeting Decision",
                "category": "FOMC",
                "country": "US",
                "importance": "HIGH",
            }
        )

    return events


def store_events(events: list[dict[str, Any]]) -> int:
    """Upsert calendar events. Idempotent on (event_id, event_date).

    Raises:
        RuntimeError: if the database write fails (fail-fast, no silent swallow).
    """
    if not events:
        return 0
    try:
        with DatabaseContext("write") as cur:
            for event in events:
                cur.execute(
                    """
                    INSERT INTO economic_calendar
                        (event_id, event_date, event_name, category, country, importance, updated_at)
                    VALUES (%(event_id)s, %(event_date)s, %(event_name)s, %(category)s, %(country)s,
                             %(importance)s, CURRENT_TIMESTAMP)
                    ON CONFLICT (event_id, event_date) DO UPDATE SET
                        event_name = EXCLUDED.event_name,
                        category = EXCLUDED.category,
                        country = EXCLUDED.country,
                        importance = EXCLUDED.importance,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    event,
                )
        return len(events)
    except Exception as e:
        raise RuntimeError(f"[ECONOMIC_CALENDAR] Failed to store events: {e}") from e


def _load_impl() -> dict[str, Any]:
    api_key = get_fred_api_key()
    events = build_events(api_key)
    stored = store_events(events)
    future_count = sum(1 for e in events if e["event_date"] >= date.today().isoformat())
    logger.info(f"[ECONOMIC_CALENDAR] Stored {stored} events ({future_count} future-dated)")
    return {"status": "complete", "events_stored": stored, "future_events": future_count}


def load() -> dict[str, Any]:
    """Fetch and store the forward-looking economic calendar (FRED releases + FOMC). See
    load_economic_data.py's load() docstring for why every loader wires LoaderStatusManager -
    same rationale applies here: an unwired loader's status row can look "fine" in the
    dashboard forever regardless of whether it actually ran.
    """
    status_mgr = LoaderStatusManager("economic_calendar")
    status_mgr.mark_running()
    start_time = time.time()
    try:
        result = _load_impl()
    except Exception as e:
        status_mgr.mark_failed(error_message=str(e)[:500])
        raise

    # Non-symbol-based loader (fixed list of FRED releases + FOMC dates, not a symbol
    # universe) - mark_completed()'s built-in <98%-completion safety check needs the
    # current_run_* override here, same pattern load_economic_data.py's load() uses and
    # documents in full.
    total_expected = len(FRED_RELEASES) + len(FOMC_MEETING_DATES)
    status_mgr.mark_completed(
        execution_duration_sec=time.time() - start_time,
        current_run_symbols_loaded=total_expected,
        current_run_symbol_count=total_expected,
    )
    return result


if __name__ == "__main__":
    load_result = load()
    sys.exit(0 if load_result.get("status") == "complete" else 1)
