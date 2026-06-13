#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard

Usage:
  python tools/dashboard/dashboard.py            # live view (AWS endpoints, q or Ctrl+C to exit)
  python tools/dashboard/dashboard.py -w         # watch mode, auto-refresh every 30s
  python tools/dashboard/dashboard.py -w 60      # watch mode, refresh every 60s
  python tools/dashboard/dashboard.py --compact  # narrow positions table
  python tools/dashboard/dashboard.py --local    # use local API (localhost:3001) instead of AWS

Modes:
  AWS (default): Requires AWS credentials (AWS_PROFILE env var), reads data from AWS Secrets Manager
  Local: Requires local API service running on http://localhost:3001
"""

import argparse
import sys
import threading
import time
from datetime import datetime
from typing import Optional

try:
    import msvcrt
    def _keypress() -> str:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            return ch.decode("utf-8", errors="ignore").lower()
        return ""
except ImportError:
    def _keypress() -> str:
        return ""

from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from utilities import CONSOLE, ET, MASCOT_W, logger, set_api_url
from fetchers import load_all
from panels import (
    _extract_items, mascot_compact, loading_layout, _expanded_layout,
    panel_header_market, panel_exposure_compact, panel_circuit,
    panel_algo_health, panel_portfolio, panel_performance_spark,
    panel_economic_pulse, panel_signals_compact, panel_sector_compact,
    panel_positions, panel_recent_trades, panel_signals_expanded,
    panel_algo_health_expanded, panel_sectors_expanded
)
from formatters import mkt_hours_str, next_run_str


def render_dashboard(data: dict, compact: bool = False, elapsed: float = 0.0,
                     frame: int = 0, watch_interval: Optional[int] = None,
                     last_load_time: Optional[float] = None,
                     refreshing: bool = False,
                     view_mode: str = "normal") -> Layout:
    run      = data.get("run")         or {}
    cfg      = data.get("cfg")         or {}
    mkt      = data.get("mkt")         or {}
    port     = data.get("port")        or {}
    perf     = data.get("perf")        or {}
    pos      = data.get("pos")
    sig      = data.get("sig")         or {}
    hlth     = _extract_items(data.get("health") or {})
    cb       = data.get("cb")          or {}
    rec      = data.get("trades")      or {}
    srank    = _extract_items(data.get("srank") or {})
    act      = data.get("activity")    or {}
    exp_f    = data.get("exp_factors") or {}
    eco      = data.get("eco")         or {}
    notifs   = data.get("notifs")      or []
    sentiment = data.get("sentiment")  or {}
    econ_cal = _extract_items(data.get("econ_cal") or {})
    risk      = data.get("risk")       or {}
    perf_anl  = data.get("perf_anl")   or {}
    sig_eval  = data.get("sig_eval")   or {}
    sec_rot      = data.get("sec_rot")       or {}
    algo_metrics = _extract_items(data.get("algo_metrics") or {})
    irank        = _extract_items(data.get("irank") or {})
    loader       = hlth
    audit        = _extract_items(data.get("audit") or {})
    exec_hist    = _extract_items(data.get("exec_hist") or {})

    now_et = datetime.now(ET)
    _mkt_badge, _mkt_cdown = mkt_hours_str()
    mkt_s  = f"{_mkt_badge}  [dim]{_mkt_cdown}[/]"
    ts     = now_et.strftime("%a %b %d  %I:%M %p ET")

    refresh_s = ""
    if refreshing:
        refresh_s = "  [cyan]↻[/]"
    elif watch_interval is not None and last_load_time is not None:
        secs = max(0, watch_interval - int(time.monotonic() - last_load_time))
        refresh_s = f"  [dim]↻{secs}s[/]"

    hdr_panel = panel_header_market(mkt, sentiment, ts, mkt_s, elapsed, refresh_s, cfg=cfg)
    exp_panel = panel_exposure_compact(exp_f)
    mascot_panel = mascot_compact(data, frame)

    outer = Layout()
    outer.split_column(
        Layout(name="top",  size=10),
        Layout(name="r1",   ratio=2),
        Layout(name="r2",   ratio=2),
        Layout(name="r3",   ratio=2),
        Layout(name="pos",  ratio=3),
    )

    outer["top"].split_row(
        Layout(name="hdr",      ratio=1),
        Layout(name="exposure", ratio=2),
        Layout(name="mascot",   size=MASCOT_W),
    )
    outer["top"]["hdr"].update(hdr_panel)
    outer["top"]["exposure"].update(exp_panel)
    outer["top"]["mascot"].update(mascot_panel)

    outer["r1"].split_row(
        Layout(panel_circuit(cb),                                                                         ratio=1, name="cb"),
        Layout(panel_algo_health(run, act, hlth, notifs, algo_metrics, loader, audit, exec_hist, risk=risk), ratio=2, name="health"),
    )

    outer["r2"].split_row(
        Layout(panel_portfolio(port, cfg, risk=risk, perf=perf),    name="portfolio"),
        Layout(panel_performance_spark(perf, rec, perf_anl),        name="perf"),
        Layout(panel_economic_pulse(eco, econ_cal),                  name="eco"),
    )

    outer["r3"].split_row(
        Layout(panel_signals_compact(sig, sig_eval), ratio=3, name="signals"),
        Layout(panel_sector_compact(srank, pos, port, sec_rot, irank), ratio=2, name="sectors"),
    )

    outer["pos"].split_row(
        Layout(panel_positions(pos, compact, trades=rec),  ratio=3, name="positions"),
        Layout(panel_recent_trades(rec),                   ratio=2, name="recent_trades"),
    )

    _exp_top = (hdr_panel, exp_panel, mascot_panel)

    if view_mode == "positions":
        hint = Text.from_markup("[dim]press [/][bold cyan]p[/][dim] to return to dashboard[/]")
        return _expanded_layout(*_exp_top, Panel(
            Group(hint, Rule(style="dim"), panel_positions(pos, compact=False, trades=rec)),
            title=f"[bold cyan]ALL POSITIONS ({len(pos or [])})[/]",
            border_style="cyan", padding=(0, 1),
        ))

    if view_mode == "signals":
        return _expanded_layout(*_exp_top, panel_signals_expanded(sig, sig_eval))

    if view_mode == "health":
        return _expanded_layout(*_exp_top, panel_algo_health_expanded(
            run, act, hlth, notifs, algo_metrics, loader, audit, exec_hist, risk=risk))

    if view_mode == "sectors":
        return _expanded_layout(*_exp_top, panel_sectors_expanded(srank, pos, port, sec_rot, irank))

    return outer


def run_once(compact: bool) -> None:
    """Single Live session: mascot stays in upper right through loading and live view."""
    result:  list = [None]
    elapsed: list = [0.0]
    done = threading.Event()

    def bg():
        t0 = time.monotonic()
        result[0] = load_all()
        elapsed[0] = time.monotonic() - t0
        done.set()

    threading.Thread(target=bg, daemon=True).start()

    frame = 0
    view_mode = ["normal"]
    _KEY_MAP = {"p": "positions", "s": "signals", "h": "health", "r": "sectors"}
    with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
        try:
            while True:
                key = _keypress()
                if key == "q":
                    break
                if key in _KEY_MAP:
                    target = _KEY_MAP[key]
                    view_mode[0] = "normal" if view_mode[0] == target else target
                frame += 1
                if not done.is_set():
                    live.update(loading_layout(frame))
                else:
                    live.update(render_dashboard(
                        result[0], compact=compact, elapsed=elapsed[0], frame=frame,
                        view_mode=view_mode[0]))
                time.sleep(0.125)
        except KeyboardInterrupt:
            pass


def run_watch(interval: int, compact: bool) -> None:
    """Watch mode: auto-refresh data every `interval` seconds, mascot dances continuously."""
    result:    list = [None]
    elapsed:   list = [0.0]
    loading:   list = [True]
    last_load: list = [0.0]
    frame:     list = [0]

    def reload():
        loading[0] = True
        t0 = time.monotonic()
        result[0] = load_all()
        elapsed[0] = time.monotonic() - t0
        last_load[0] = time.monotonic()
        loading[0] = False

    threading.Thread(target=reload, daemon=True).start()

    view_mode = ["normal"]
    _KEY_MAP  = {"p": "positions", "s": "signals", "h": "health", "r": "sectors"}
    with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
        try:
            while True:
                key = _keypress()
                if key == "q":
                    break
                if key in _KEY_MAP:
                    target = _KEY_MAP[key]
                    view_mode[0] = "normal" if view_mode[0] == target else target
                frame[0] += 1
                if result[0] is None:
                    live.update(loading_layout(frame[0]))
                else:
                    live.update(render_dashboard(
                        result[0], compact=compact, elapsed=elapsed[0],
                        frame=frame[0], watch_interval=interval,
                        last_load_time=last_load[0], refreshing=loading[0],
                        view_mode=view_mode[0]))
                    if not loading[0] and (time.monotonic() - last_load[0]) >= interval:
                        threading.Thread(target=reload, daemon=True).start()
                time.sleep(0.125)
        except KeyboardInterrupt:
            pass


LEGEND = """
╔════════════════════════════════════════════════════════════════════════════╗
║                     ALGO DASHBOARD - TERM GUIDE                            ║
╚════════════════════════════════════════════════════════════════════════════╝

PANELS:

  ORCHESTRATOR - algo run status & configuration
    Mode            LIVE or PAPER trading, SWING/MOMENTUM style
    Enabled         Whether the algo is currently active
    min score ≥     Minimum swing score a stock must have to be considered
    max N positions Max simultaneous open positions allowed
    sector ≤ N      Max positions in any single sector
    base risk %     % of portfolio risked per trade (stop-loss sizing)
    T1 target NR    Target profit = N × the initial risk amount (R-multiple)
    pyramid on      Algo can add to winning positions (scale in)
    Phase 1/2/3✓    Algo run phases: prep, screening, execution - ✓=passed
    VaR 95%         Value at Risk: max expected daily loss 95% of the time
    CVaR 95%        Conditional VaR: avg loss on the worst 5% of days
    Portfolio Beta  How much the portfolio moves vs SPY (1.0 = same as market)
    Top-5 Conc      % of portfolio in top 5 positions (concentration risk)

  MARKET - market regime inputs to the algo
    CONF UP etc     Market tier: Confirmed Uptrend → Correction (5 levels)
    exposure %      How much of the portfolio the algo is deploying (0-100%)
    VIX             Volatility Index (>20 = caution, >30 = algo reduces)
    Dist Days       Distribution days in 4 weeks (heavy selling by institutions)
    Stage           Market stage 1-4 (Weinstein: 1=base, 2=up, 3=top, 4=down)
    SPY             S&P 500 ETF price + daily % change
    Up Volume %     % of NYSE volume in advancing stocks (>60% = bullish)
    Adv/Dec         Advance/Decline ratio (stocks up vs down)
    New Highs/Lows  52-week highs vs lows (breadth indicator)
    NH-NL           Net new highs minus new lows
    Put/Call Ratio  Options market sentiment (<0.8 = bullish, >1.0 = fearful)
    Breadth Momentum 10-day breadth trend (+= improving market internals)
    Yield Curve Slope 10Y minus 2Y yield (negative = inverted = recession risk)
    Trading Halt    Reasons the algo has paused new entries
    Fear & Greed    CNN composite sentiment index (0=extreme fear, 100=greed)

  CIRCUIT BREAKERS - hard stops that halt the algo
    Drawdown        Current drawdown from equity peak / halt threshold
    Daily Loss      Today's loss / max allowed daily loss
    Weekly Loss     This week's loss / max allowed weekly loss
    Consec Losses   Consecutive losing trades / max before halt
    Total Risk      Open position risk (vs stops) as % of portfolio
    VIX             Current VIX / threshold that triggers halt
    Mkt Stage       Current market stage (halts if stage ≥ 4)

  PORTFOLIO - live account snapshot
    Total value     Current account value including unrealized P&L
    Cash            Available cash (not invested)
    Positions       Number of open positions / open slots remaining
    Today's Return  Today's portfolio return %
    Unrealized P&L  Gain/loss on currently open positions
    Buying Power    Approximate capital available to open new positions
    Total Return    Cumulative portfolio return since algo started
    Max Drawdown    Largest peak-to-trough portfolio drop

  PERFORMANCE - historical trade analytics
    N Trades        Total closed trades
    W/L             Wins / Losses
    Win Rate        % of trades that were profitable
    streak          Current win (+) or loss (-) streak
    P&L             Total dollar profit/loss from all closed trades
    Profit Factor   Gross wins ÷ gross losses (>1.5 = good, >2.0 = excellent)
    Sharpe          Risk-adjusted return (>1.0 = good, >2.0 = excellent)
    Expectancy      Average dollar gain/loss per trade (positive = edge)
    Avg R           Average R-multiple per trade (1R = risked amount won)
    Avg Win/Loss    Average dollar size of winning vs losing trades
    Equity curve    Visual chart of portfolio value over time (sparkline)
    Sharpe (1Y)     Rolling 252-day Sharpe ratio
    Sortino         Like Sharpe but only penalizes downside volatility
    Calmar          Annualized return ÷ max drawdown
    Win Rate (50T)  Win rate over the most recent 50 trades
    Avg Win R       Average R-multiple on winning trades
    Avg Loss R      Average R-multiple on losing trades (should be < 1.0)

  POSITIONS - currently open trades
    Val             Current dollar value of the position ($45K, $1.2M)
    Entry           Average cost basis per share
    Price           Current market price
    P&L%            Unrealized gain/loss %
    R-Mult          How many R (risk units) this position has moved
    Stop            Current stop-loss price
    Dist%           Distance from current price to stop (buffer remaining)
    T1→             % gain needed to hit first profit target
    Days            Days since position was entered
    Stage           Weinstein stage of the stock (2 = uptrend)
    Swing Score     Algo's composite score for this stock (0-100)

  SIGNALS - today's buy signal analysis
    A/B/C/D grades  Score grade distribution of all stocks screened today
    buy signals / N scored  How many stocks got a BUY signal today
    Screened → Selected   Signal filter funnel (how many pass each gate)
      →Mkt:          Market condition gate (is market healthy enough?)
      →Score:        Minimum swing score gate
      →Risk:         Position sizing / risk gate
      →Sector:       Sector concentration gate
      →Selected:     Final candidates the algo can trade
    avg score       Average quality score of signals passing all filters
    Top rejection reasons   Why most signals were filtered out

  SECTORS & INDUSTRY - rotation context for position decisions
    Rotation signal   Whether defensive or cyclical sectors are leading
    Sector holdings   Which sectors our current positions are in
    #1 Tech ↓2        Sector rank (1=best), with 1-week rank change
    #2 Industry ↓1    Top industry sub-groups within sectors

  EXPOSURE SCORE BREAKDOWN - what drives the algo's allocation %
    Score N/100       Raw points scored → converted to exposure % (0-100%)
    30wk Trend        Is SPY above its 30-week moving average?
    Breadth 50MA      % of S&P 500 stocks above their 50-day MA
    IBD State         IBD market status (Confirmed Uptrend/Under Pressure/etc)
    Breadth 200MA     % of S&P 500 stocks above their 200-day MA
    McClellan Osc     Short-term breadth oscillator (momentum of A/D)
    VIX Level         Volatility regime contribution to score
    New Hi vs Lo      Daily new highs minus new lows
    Credit Spread     High-yield bond spread (risk appetite indicator)
    Adv/Dec Line      Cumulative advance/decline trend
    AAII Sentiment    Weekly survey: retail investor bullish vs bearish %
    NAAIM Exposure    Active manager equity exposure level

  ECONOMIC INPUTS → Exposure Score - macro factors the algo monitors
    3M/6M/2Y/10Y Tsy  Treasury yield curve (used in yield curve slope factor)
    10Y-2Y spread     Yield curve inversion (algo reduces exposure when inverted)
    Fed Rate          Federal Funds Rate (algo's fed_rate_environment filter)
    HY/IG OAS         Credit spreads - widening = risk-off → algo reduces exposure
    CPI YoY           Inflation rate (algo's economic overlay factor)
    Unemployment      Labor market health (economic overlay)
    WTI Crude Oil     Oil price (energy cost / inflation proxy)
    Chicago Fed NFCI  Financial conditions index (tight = algo more conservative)
    USD Index (DXY)   Dollar strength (affects international/commodity stocks)
    10Y/5Y Breakeven  Market's inflation expectations
    30Y Mortgage      Housing market health proxy
    UMich Sentiment   Consumer confidence (economic overlay factor)

  ACTIVITY & HEALTH - algo system status
    Run phases        Which phases of today's run completed (✓/~/✗)
    Data health       Whether all required data tables are fresh
    Notifications     System alerts (circuit breaker fired, trade executed, etc)
    Daily actions     How many entries/exits the algo took each day
    Loader status     Data pipeline status (are feeds updating correctly?)
    Audit log         Recent significant algo actions with pass/fail status

SIDEBAR:
    Market tier       Current regime label (Confirmed Uptrend = max aggression)
    exposure %        Current allocation level set by exposure score
    VIX               Volatility (algo dials back when high)
    SPY ±%            S&P 500 daily change
    Portfolio value   Total account value
    +/-% today        Today's portfolio return
    +/-% unrlzd       Unrealized P&L on open positions
    N positions       Currently open position count
    Win rate %        All-time trade win rate
    P&L $             Total realized profit/loss
    Last run status   ✓=completed ✗=error ~=halted, and time since
    - N alerts        Unread notifications needing attention
"""


def print_legend():
    CONSOLE.print(LEGEND)


def main():
    pa = argparse.ArgumentParser(
        description="Algo ops terminal dashboard",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pa.add_argument("-w", "--watch", nargs="?", const=30, type=int, metavar="SECS",
                    help="Watch mode, auto-refresh interval (default 30s)")
    pa.add_argument("--compact", "-c", action="store_true",
                    help="Omit T1 and Sector columns from positions table")
    pa.add_argument("--legend", "-l", action="store_true",
                    help="Print a guide explaining every term and panel, then exit")
    args = pa.parse_args()

    if args.legend:
        print_legend()
        return

    if args.watch is not None:
        run_watch(max(10, args.watch), args.compact)
    else:
        run_once(args.compact)


if __name__ == "__main__":
    main()
