#!/usr/bin/env python3

"""
Capital Routing Engine - what to do with capital the equity exposure dial isn't using.

SCOPE (user-directed, 2026-08-24 /goal): `market_exposure.py`'s exposure_pct answers "how
much capital goes into stock positions." This module answers the follow-on question the
user raised directly - "what else to do with the money," including "cash is also an
option" - for the (100 - exposure_pct)% of capital NOT going into stocks on a given day.

This is deliberately a LEFTOVER-CAPITAL ROUTER, not an independent always-on multi-asset
sleeve (the more common GTAA/Ivy-Portfolio shape, where each asset class holds a fixed
~20% regardless of what any other asset is doing). The equity exposure dial stays primary
and untouched; this module only decides how to deploy the slice it doesn't use, among a
small set of alternatives, each judged on its own trend signal - not a fixed allocation.

ASSET SELECTION (researched against real institutional/academic practice, not invented):
  - GLD (gold): kept SEPARATE from broader commodities, not blended into one index.
    Real-world reasoning (World Gold Council; also why GSCI/BCOM underweight gold to
    ~7-15% despite its narrative importance): gold decouples from and often goes
    negatively-correlated with equities specifically in risk-off regimes, a property
    cyclical/industrial commodities don't reliably share.
  - IEF (7-10yr Treasuries): the literature-correct instrument for GTAA's "US bonds" leg
    (Faber's original paper specifies 10-Year Treasuries, not the long end) - chosen over
    TLT (20yr+, already loaded in this system but the WRONG duration for this leg) and
    over a multi-rung duration ladder (SHY/IEF/TLT), which real CTA/risk-parity practice
    prefers but the user explicitly asked to skip for simplicity: "lets just have one bond
    fund to keep this simple."
  - DBC (broad commodities, GSCI-based): added per explicit user direction as the broad-
    commodity leg, separate from gold for the reason above.
  - Cash: an explicit, real fourth option, not a fallback-only default. Faber/Antonacci
    both treat "go to cash" as a genuine asset-class decision, not "do nothing."
  International equity was explicitly researched and PARKED by the user for a later,
  more-detailed pass - not implemented here, do not add it without that discussion.

SIZING: inverse-volatility (risk-parity / equal-risk-contribution) weighting among
qualifying legs, not equal-dollar. Real CTA/systematic practice (cited ~57% of managed-
futures programs, Bridgewater's convention since 1997) sizes each leg so it contributes
equal RISK, not equal capital - critical here because GLD/IEF/DBC have materially
different volatility and equal-dollar weighting would let the highest-vol leg dominate the
sleeve's actual risk. A leg only qualifies if its OWN 30-week trend is up (same Faber
signal already used for SPY in market_exposure.py, just per-instrument instead of
hardcoded to SPY) - legs with a down trend get zero weight regardless of their inverse-vol
share; unused weight moves to cash_weight, not redistributed to the remaining legs.

DATA FRESHNESS (user-directed: "we cannot rely on fred refresh times... we need the same
currentness of the data" as the Faber equity trend signal, which is instant on price_daily).
This module deliberately follows the EXACT precedent this codebase already uses for VIX:
`loaders/market_health_fetchers.py`'s VIXFetcher reads `^VIX` straight out of `price_daily`,
not FRED. `^MOVE` (bond-market implied vol, the direct institutional analogue of VIX for
Treasuries - real, named threshold bands: <80 calm, 80-120 normal, 120-160 stressed, >160
acute dislocation) is fetchable the identical way and is read here from `price_daily` too -
see MOVE_VETO_THRESHOLD below.

CORRECTION (found during 2026-08-24 pre-live-money review, after this module first landed):
the original version of this comment called `^VIX`/`^MOVE` "Alpaca-sourced" - that's wrong.
`utils/external/alpaca_market_data.py`'s `fetch_daily_bars` explicitly SKIPS every
`^`-prefixed symbol ("Alpaca's /v2/stocks endpoints serve equities only... 400 the WHOLE
multi-symbol request"), so both actually come from the yfinance fallback path in
`loaders/load_prices.py` - confirmed live via `price_daily.data_source = 'yfinance'` on
every recent `^VIX` row. This matters because yfinance is a weaker link than Alpaca
elsewhere in this codebase (see MEMORY.md's Loader Brittleness section) - the MOVE veto's
real-world reliability rides on that fallback path staying healthy, not on Alpaca's.
GLD/IEF/DBC (ordinary equities, not `^`-prefixed) DO go through the primary Alpaca path and
don't have this caveat - but see the staleness guards added in `_leg_signal`/`_move_veto`
below: this module originally trusted "ordinary priced instruments in this system's existing
pipeline" to mean same-day-fresh with no verification, and that assumption was live-found
false for IEF/DBC (26 trading days stale after a prior essential-symbols trim silently
stopped fetching them) on the same day this module first ran against real data. Real-
yield/USD-index context signals researched but NOT wired as hard inputs here - only MOVE has
a real, literature-cited extreme threshold analogous to the equity system's VIX>40 hard veto;
TIPS-price direction and USD index don't have an equivalently well-evidenced extreme-
threshold convention, so adding them as scored/veto inputs now would repeat the exact
"unproven addition" mistake market_exposure.py's own history already learned from (see that
file's Pillar 3 docstring). They can be added later if a real threshold gets found, same as
vol-managed scaling stayed inert pending validation there.

MOVE VETO: MOVE >= 160 (named "acute dislocation" territory - 2008, COVID March 2020, the
Sept 2022 gilt crisis, SVB 2023) vetoes the IEF leg specifically (its weight forced to 0,
reallocated to cash) - a genuinely extreme bond-market stress read is exactly the
circumstance where holding intermediate-duration Treasuries through a liquidity/vol shock
is the wrong call, mirroring how equity's Pillar 2 hard-vetoes the composite at VIX>=40
rather than scoring VIX continuously. GLD/DBC are NOT MOVE-vetoed - MOVE is specifically a
Treasury-market stress read, not a general risk-off signal, and gold in particular often
benefits from exactly the flight-to-safety conditions that spike MOVE.

WHAT THIS DOES NOT DO YET: this module computes and persists the routing DECISION only. It
does not place orders. Wiring real Alpaca execution for GLD/IEF/DBC (sizing dollar amounts
off portfolio value, order submission, exit logic) is real, hard-to-reverse production
trading-system surgery into an execution path (`algo/trading/order_manager.py`,
`algo/orchestrator/phase8_entry_execution.py`) that took this codebase many sessions of
adversarial fuzz-testing to harden for the existing stock path alone (NaN/Infinity/
magnitude-ceiling bugs found via fuzzing as late as 2026-08-11) - deliberately scoped out
of this pass pending the user reviewing what this engine actually recommends day to day
before any real (even paper) order flow gets wired to it.
"""

from __future__ import annotations

import itertools
import json
import logging
import math
from datetime import date as _date
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

from utils.db import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)

_TREND_MA_WEEKS = 30
_VOL_LOOKBACK_DAYS = 20
_TRADING_DAYS_PER_YEAR = 252
# GLD/IEF/DBC are ordinary Alpaca-fed equities and should never lag more than a session
# or two; ^MOVE falls back to yfinance same as ^VIX (see module docstring correction) so
# gets a slightly looser allowance. Both are generous vs. a healthy feed (0-1 trading
# days) but tight enough to catch a leg that has quietly stopped being fetched (live-found
# 2026-08-24: IEF/DBC had gone 26 trading days stale after a prior essential-symbols trim
# stopped fetching them, and this module would have silently sized a real allocation off
# that month-old data with no guard at all before this fix).
_MAX_STALE_TRADING_DAYS_DAILY = 3
_MAX_STALE_TRADING_DAYS_WEEKLY = 10
_MAX_STALE_TRADING_DAYS_MOVE = 5


class CapitalRouting:
    """Routes capital NOT deployed to stocks (100 - exposure_pct)% among GLD/IEF/DBC/cash.

    See module docstring for the full design rationale (asset selection, sizing method,
    data-freshness precedent, MOVE veto, and explicit execution-wiring scope boundary).
    """

    LEGS = ("GLD", "IEF", "DBC")
    MOVE_VETO_THRESHOLD = 160.0  # "acute dislocation" per MOVE index literature

    def compute(self, eval_date: _date | None = None, force_recompute: bool = False) -> dict[str, Any]:
        """Compute today's capital-routing decision. Returns dict (see _persist for shape).

        Requires market_exposure_daily already computed for eval_date (this module is
        wired to run immediately after MarketExposure().compute() in
        loaders/load_market_status_daily.py) - if that row is missing, this returns
        data_unavailable rather than guessing at exposure_pct.
        """
        if eval_date is None:
            eval_date = datetime.now(EASTERN_TZ).date()

        from algo.infrastructure import MarketCalendar

        if not MarketCalendar.is_trading_day(eval_date):
            raise ValueError(
                f"[CAPITAL_ROUTING] Refusing to compute/persist for {eval_date}: not a trading day. "
                f"capital_routing_daily rows must represent real trading days."
            )

        if not force_recompute:
            cached = self.try_load_cached(eval_date)
            if cached is not None:
                return cached

        with DatabaseContext("read") as cur:
            cur.execute("SET statement_timeout = 45000")

            cur.execute(
                "SELECT exposure_pct FROM market_exposure_daily WHERE date = %s LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                result = {
                    "data_unavailable": True,
                    "reason": "market_exposure_daily row missing for eval_date - capital_routing "
                    "requires the equity exposure score to exist first",
                    "eval_date": str(eval_date),
                }
                self._persist(eval_date, result)
                return result

            exposure_pct = float(row[0])
            uninvested_pct = max(0.0, min(100.0, 100.0 - exposure_pct))

            leg_data: dict[str, dict[str, Any]] = {}
            for symbol in self.LEGS:
                leg_data[symbol] = self._leg_signal(symbol, eval_date, cur)

            move_level, move_veto = self._move_veto(eval_date, cur)

            weights = self._size_legs(leg_data, move_veto)

            factors = {
                "exposure_pct": exposure_pct,
                "uninvested_capital_pct": uninvested_pct,
                "legs": leg_data,
                "move_index": move_level,
                "move_veto": move_veto,
                "weights": weights,
            }

            result = {
                "data_unavailable": False,
                "eval_date": str(eval_date),
                "exposure_pct": exposure_pct,
                "uninvested_capital_pct": uninvested_pct,
                "gld_trend_up": leg_data["GLD"].get("trend_up"),
                "ief_trend_up": leg_data["IEF"].get("trend_up"),
                "dbc_trend_up": leg_data["DBC"].get("trend_up"),
                "gld_vol_20d": leg_data["GLD"].get("vol_20d"),
                "ief_vol_20d": leg_data["IEF"].get("vol_20d"),
                "dbc_vol_20d": leg_data["DBC"].get("vol_20d"),
                "gld_weight": weights["GLD"],
                "ief_weight": weights["IEF"],
                "dbc_weight": weights["DBC"],
                "cash_weight": weights["CASH"],
                "move_index": move_level,
                "move_veto": move_veto,
                "factors": factors,
                "reason": None,
            }
            self._persist(eval_date, result)
            return result

    def _leg_signal(self, symbol: str, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Trend (30-week MA, same Faber convention as SPY in market_exposure.py) + 20d
        realized volatility (annualized) for one leg. Missing data makes the leg
        unavailable (excluded from routing, not fatal) - this sleeve is a satellite
        allocation, not foundational the way equity's own SPY trend is, so a data gap
        here should degrade to "skip this leg" rather than halt exposure calculation
        entirely.
        """
        from algo.infrastructure import MarketCalendar

        try:
            cur.execute(
                """
                WITH w AS (
                    SELECT date, close,
                           AVG(close) OVER (ORDER BY date ROWS BETWEEN %s PRECEDING AND CURRENT ROW) as sma,
                           ROW_NUMBER() OVER (ORDER BY date DESC) as rn
                    FROM price_weekly WHERE symbol = %s AND date <= %s
                )
                SELECT date, close, sma FROM w WHERE rn = 1
                """,
                (_TREND_MA_WEEKS - 1, symbol, eval_date),
            )
            row = cur.fetchone()
            if row is None or row[0] is None or row[1] is None or row[2] is None:
                return {"data_unavailable": True, "reason": f"no price_weekly data for {symbol}"}
            week_date, price, sma = row[0], float(row[1]), float(row[2])
            stale_weeks = MarketCalendar.trading_days_elapsed(week_date, eval_date)
            if stale_weeks > _MAX_STALE_TRADING_DAYS_WEEKLY:
                return {
                    "data_unavailable": True,
                    "reason": f"{symbol} price_weekly is {stale_weeks}d stale (latest {week_date}) - "
                    f"feed has likely stopped, not a normal reporting lag",
                }
            if math.isnan(price) or math.isinf(price) or math.isnan(sma) or math.isinf(sma) or sma <= 0:
                return {"data_unavailable": True, "reason": f"non-finite {symbol} trend data"}
            trend_up = price > sma

            cur.execute(
                """
                SELECT date, close FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT %s
                """,
                (symbol, eval_date, _VOL_LOOKBACK_DAYS + 1),
            )
            daily_rows = cur.fetchall()
            if daily_rows and daily_rows[0][0] is not None:
                stale_days = MarketCalendar.trading_days_elapsed(daily_rows[0][0], eval_date)
                if stale_days > _MAX_STALE_TRADING_DAYS_DAILY:
                    return {
                        "data_unavailable": True,
                        "reason": f"{symbol} price_daily is {stale_days}d stale (latest {daily_rows[0][0]}) - "
                        f"feed has likely stopped, not a normal reporting lag",
                    }
            closes = [float(r[1]) for r in daily_rows if r[1] is not None]
            vol_20d = self._annualized_vol(closes)
            if vol_20d is None:
                return {"data_unavailable": True, "reason": f"insufficient price_daily history for {symbol}"}

            return {
                "data_unavailable": False,
                "price": price,
                "sma_30wk": sma,
                "trend_up": trend_up,
                "price_vs_ma_pct": ((price - sma) / sma) * 100.0,
                "vol_20d": vol_20d,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError) as e:
            logger.warning(f"[CAPITAL_ROUTING] {symbol} signal calculation failed, excluding leg: {e}")
            return {"data_unavailable": True, "reason": f"query failed: {type(e).__name__}"}

    @staticmethod
    def _annualized_vol(closes_desc: list[float]) -> float | None:
        """Annualized stddev of daily log-ish returns from a DESC-ordered close list.

        Guards NaN/Infinity/non-positive prices per this codebase's standard convention
        (see market_exposure.py's identical guards on every price-derived factor).
        """
        if len(closes_desc) < 2:
            return None
        closes = list(reversed(closes_desc))  # oldest first
        returns = []
        for prev, cur_ in itertools.pairwise(closes):
            if prev is None or cur_ is None or prev <= 0 or cur_ <= 0:
                continue
            r = (cur_ - prev) / prev
            if math.isnan(r) or math.isinf(r):
                continue
            returns.append(r)
        if len(returns) < 2:
            return None
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        daily_vol = math.sqrt(variance)
        if math.isnan(daily_vol) or math.isinf(daily_vol):
            return None
        return daily_vol * math.sqrt(_TRADING_DAYS_PER_YEAR)

    def _move_veto(self, eval_date: _date, cur: PsycopgCursor[Any]) -> tuple[float | None, bool]:
        """^MOVE read from price_daily - same non-FRED, price-feed pattern as ^VIX's
        VIXFetcher (see module docstring). Missing MOVE data is non-critical (this is a
        veto on top of an already-optional leg, not a foundational signal) - degrades to
        no-veto rather than raising.
        """
        from algo.infrastructure import MarketCalendar

        try:
            cur.execute(
                "SELECT date, close FROM price_daily WHERE symbol = '^MOVE' AND date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            if row is None or row[0] is None or row[1] is None:
                return None, False
            move_date, move = row[0], float(row[1])
            stale_days = MarketCalendar.trading_days_elapsed(move_date, eval_date)
            if stale_days > _MAX_STALE_TRADING_DAYS_MOVE:
                logger.warning(
                    f"[CAPITAL_ROUTING] ^MOVE is {stale_days}d stale (latest {move_date}) - "
                    f"treating as no-veto rather than trusting a stale dislocation read"
                )
                return None, False
            if math.isnan(move) or math.isinf(move) or move < 0:
                return None, False
            return move, move >= self.MOVE_VETO_THRESHOLD
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError) as e:
            logger.warning(f"[CAPITAL_ROUTING] MOVE index read failed, treating as no-veto: {e}")
            return None, False

    def _size_legs(self, leg_data: dict[str, dict[str, Any]], move_veto: bool) -> dict[str, float]:
        """Inverse-volatility (risk-parity) weighting among qualifying legs (trend up,
        data available, not MOVE-vetoed). Weights are fractions of the UNINVESTED slice
        only (sum to exactly 1.0) - NOT fractions of total portfolio. A future consumer
        multiplies by uninvested_capital_pct/100 to get an actual portfolio-fraction
        dollar target; keeping these two scalars separate avoids conflating "how much
        capital is available" with "how it's split among the alternatives."
        """
        inv_vol: dict[str, float] = {}
        for symbol in self.LEGS:
            data = leg_data[symbol]
            if data.get("data_unavailable"):
                continue
            if not data.get("trend_up"):
                continue
            if symbol == "IEF" and move_veto:
                continue
            vol = data.get("vol_20d")
            if not vol or vol <= 0:
                continue
            inv_vol[symbol] = 1.0 / vol

        weights = {"GLD": 0.0, "IEF": 0.0, "DBC": 0.0, "CASH": 1.0}
        total_inv_vol = sum(inv_vol.values())
        if total_inv_vol > 0:
            for symbol, iv in inv_vol.items():
                weights[symbol] = iv / total_inv_vol
            weights["CASH"] = 0.0
        return weights

    def try_load_cached(self, eval_date: _date) -> dict[str, Any] | None:
        """Same-day cache lookup. Returns None (not a data_unavailable dict) on cache miss
        so compute() falls through to a fresh calculation - mirrors
        market_exposure.py's try_load_cached contract for the "no row yet" case.
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT exposure_pct, uninvested_capital_pct, gld_trend_up, ief_trend_up, dbc_trend_up,
                       gld_vol_20d, ief_vol_20d, dbc_vol_20d, gld_weight, ief_weight, dbc_weight,
                       cash_weight, move_index, move_veto, factors, data_unavailable, reason
                FROM capital_routing_daily WHERE date = %s LIMIT 1
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            (
                exposure_pct,
                uninvested_pct,
                gld_trend,
                ief_trend,
                dbc_trend,
                gld_vol,
                ief_vol,
                dbc_vol,
                gld_w,
                ief_w,
                dbc_w,
                cash_w,
                move_index,
                move_veto,
                factors,
                data_unavailable,
                reason,
            ) = row
            if data_unavailable:
                return {"data_unavailable": True, "reason": reason, "eval_date": str(eval_date)}
            return {
                "data_unavailable": False,
                "eval_date": str(eval_date),
                "exposure_pct": float(exposure_pct) if exposure_pct is not None else None,
                "uninvested_capital_pct": float(uninvested_pct) if uninvested_pct is not None else None,
                "gld_trend_up": gld_trend,
                "ief_trend_up": ief_trend,
                "dbc_trend_up": dbc_trend,
                "gld_vol_20d": float(gld_vol) if gld_vol is not None else None,
                "ief_vol_20d": float(ief_vol) if ief_vol is not None else None,
                "dbc_vol_20d": float(dbc_vol) if dbc_vol is not None else None,
                "gld_weight": float(gld_w) if gld_w is not None else 0.0,
                "ief_weight": float(ief_w) if ief_w is not None else 0.0,
                "dbc_weight": float(dbc_w) if dbc_w is not None else 0.0,
                "cash_weight": float(cash_w) if cash_w is not None else 1.0,
                "move_index": float(move_index) if move_index is not None else None,
                "move_veto": move_veto,
                "factors": factors,
                "reason": reason,
            }

    def _persist(self, eval_date: _date, result: dict[str, Any]) -> None:
        data_unavailable = bool(result.get("data_unavailable"))
        factors_json = json.dumps(result.get("factors"), default=str) if result.get("factors") else None
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                INSERT INTO capital_routing_daily
                    (date, exposure_pct, uninvested_capital_pct, gld_trend_up, ief_trend_up, dbc_trend_up,
                     gld_vol_20d, ief_vol_20d, dbc_vol_20d, gld_weight, ief_weight, dbc_weight, cash_weight,
                     move_index, move_veto, factors, data_unavailable, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    exposure_pct = EXCLUDED.exposure_pct,
                    uninvested_capital_pct = EXCLUDED.uninvested_capital_pct,
                    gld_trend_up = EXCLUDED.gld_trend_up,
                    ief_trend_up = EXCLUDED.ief_trend_up,
                    dbc_trend_up = EXCLUDED.dbc_trend_up,
                    gld_vol_20d = EXCLUDED.gld_vol_20d,
                    ief_vol_20d = EXCLUDED.ief_vol_20d,
                    dbc_vol_20d = EXCLUDED.dbc_vol_20d,
                    gld_weight = EXCLUDED.gld_weight,
                    ief_weight = EXCLUDED.ief_weight,
                    dbc_weight = EXCLUDED.dbc_weight,
                    cash_weight = EXCLUDED.cash_weight,
                    move_index = EXCLUDED.move_index,
                    move_veto = EXCLUDED.move_veto,
                    factors = EXCLUDED.factors,
                    data_unavailable = EXCLUDED.data_unavailable,
                    reason = EXCLUDED.reason,
                    updated_at = NOW()
                """,
                (
                    eval_date,
                    result.get("exposure_pct"),
                    result.get("uninvested_capital_pct"),
                    result.get("gld_trend_up"),
                    result.get("ief_trend_up"),
                    result.get("dbc_trend_up"),
                    result.get("gld_vol_20d"),
                    result.get("ief_vol_20d"),
                    result.get("dbc_vol_20d"),
                    result.get("gld_weight"),
                    result.get("ief_weight"),
                    result.get("dbc_weight"),
                    result.get("cash_weight"),
                    result.get("move_index"),
                    result.get("move_veto"),
                    factors_json,
                    data_unavailable,
                    result.get("reason"),
                ),
            )
