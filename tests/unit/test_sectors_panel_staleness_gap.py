"""Regression: the SECTORS panel's stale-data warning was dead code.

BUG FOUND 2026-08-17: panel_sector_compact checked data_source.get("age_hours") on all four
data sources it receives (srank, pos, port, sec_rot), but no fetcher
(fetch_sector_ranking/fetch_positions/fetch_portfolio/fetch_sector_rotation) has ever set that
key - the check could never fire regardless of actual staleness, same bug class as the now-fixed
TRADES/MARKET/EXPOSURE panels. fetch_positions already propagates a real, server-computed
data_freshness field (dashboard/fetchers_portfolio.py) - wired that in as the staleness signal.
"""

from dashboard.panels.sectors import panel_sector_compact


def _pos(data_freshness: dict | None = None) -> dict:
    row: dict = {"items": []}
    if data_freshness is not None:
        row["data_freshness"] = data_freshness
    return row


def _extract_texts(panel) -> list[str]:
    renderable = panel.renderable
    if hasattr(renderable, "renderables"):
        return [r.plain for r in renderable.renderables if hasattr(r, "plain")]
    if hasattr(renderable, "plain"):
        return [renderable.plain]
    return []


def test_stale_positions_produces_warning_row():
    srank = {"items": []}
    pos = _pos({"is_stale": True, "data_age_days": 4, "warning": "4 days old"})
    port = {"total_portfolio_value": 10000.0}
    panel = panel_sector_compact(srank, pos, port)
    texts = _extract_texts(panel)
    assert any("stale" in t.lower() for t in texts), f"expected a stale warning row, got: {texts}"


def test_fresh_positions_no_warning_row():
    srank = {"items": []}
    pos = _pos({"is_stale": False})
    port = {"total_portfolio_value": 10000.0}
    panel = panel_sector_compact(srank, pos, port)
    texts = _extract_texts(panel)
    assert not any("stale" in t.lower() for t in texts)


def test_missing_data_freshness_no_crash_no_warning():
    srank = {"items": []}
    pos = _pos()  # no data_freshness key at all
    port = {"total_portfolio_value": 10000.0}
    panel = panel_sector_compact(srank, pos, port)
    texts = _extract_texts(panel)
    assert not any("stale" in t.lower() for t in texts)
