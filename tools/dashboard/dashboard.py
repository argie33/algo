#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard

Usage:
  python tools/dashboard/dashboard.py                 # live view (AWS endpoints, q or Ctrl+C to exit)
  python tools/dashboard/dashboard.py -w              # watch mode, auto-refresh every 30s
  python tools/dashboard/dashboard.py -w 60           # watch mode, refresh every 60s
  python tools/dashboard/dashboard.py --compact       # narrow positions table
  python tools/dashboard/dashboard.py --local         # use local API (localhost:3001) instead of AWS

Modes:
  AWS (default): Set DASHBOARD_API_URL, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID env vars
  Local: Run local dev server on localhost:3001 first, then use --local flag
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

from utilities import CONSOLE, ET, MASCOT_W, logger, set_api_url, set_cognito_auth
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


def _validate_watch_interval(value):
    """Validate watch interval is between 5 and 600 seconds."""
    try:
        int_value = int(value)
        if int_value < 5:
            raise argparse.ArgumentTypeError(f"Watch interval must be at least 5 seconds (got {int_value})")
        if int_value > 600:
            raise argparse.ArgumentTypeError(f"Watch interval must be at most 600 seconds (got {int_value})")
        return int_value
    except ValueError:
        raise argparse.ArgumentTypeError(f"Watch interval must be an integer (got {value})")


def render_dashboard(data: dict, compact: bool = False, elapsed: float = 0.0,
                     frame: int = 0, watch_interval: Optional[int] = None,
                     last_load_time: Optional[float] = None,
                     refreshing: bool = False,
                     view_mode: str = "normal",
                     data_source: str = "AWS") -> Layout:
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

    hdr_panel = panel_header_market(mkt, sentiment, ts, mkt_s, elapsed, refresh_s, cfg=cfg, data_source=data_source)
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


def run_once(compact: bool, data_source: str = "AWS") -> None:
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
                    live.update(loading_layout(frame, data_source=data_source))
                else:
                    live.update(render_dashboard(
                        result[0], compact=compact, elapsed=elapsed[0], frame=frame,
                        view_mode=view_mode[0], data_source=data_source))
                time.sleep(0.125)
        except KeyboardInterrupt:
            pass


def run_watch(interval: int, compact: bool, data_source: str = "AWS") -> None:
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
                    live.update(loading_layout(frame[0], data_source=data_source))
                else:
                    live.update(render_dashboard(
                        result[0], compact=compact, elapsed=elapsed[0],
                        frame=frame[0], watch_interval=interval,
                        last_load_time=last_load[0], refreshing=loading[0],
                        view_mode=view_mode[0], data_source=data_source))
                    if not loading[0] and (time.monotonic() - last_load[0]) >= interval:
                        threading.Thread(target=reload, daemon=True).start()
                time.sleep(0.125)
        except KeyboardInterrupt:
            pass


def main():
    pa = argparse.ArgumentParser(
        description="Algo ops terminal dashboard",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pa.add_argument("-w", "--watch", nargs="?", const=30, type=_validate_watch_interval, metavar="SECS",
                    help="Watch mode, auto-refresh interval in seconds (5-600, default 30s)")
    pa.add_argument("--compact", "-c", action="store_true",
                    help="Omit T1 and Sector columns from positions table")
    pa.add_argument("--local", action="store_true",
                    help="Use local API (localhost:3001) instead of AWS endpoints")
    pa.add_argument("--legend", "-l", action="store_true",
                    help="Print a guide explaining every term and panel, then exit")
    args = pa.parse_args()

    if args.legend:
        CONSOLE.print(__doc__)
        return

    if args.local:
        set_api_url("http://localhost:3001")
        data_source = "LOCAL"
    else:
        # AWS mode: require DASHBOARD_API_URL
        import os
        aws_url = os.environ.get("DASHBOARD_API_URL")
        if not aws_url:
            CONSOLE.print("[bold red]ERROR:[/] AWS mode requires DASHBOARD_API_URL environment variable")
            CONSOLE.print("")
            CONSOLE.print("[bold cyan]Setup Instructions:[/]")
            CONSOLE.print("1. Get credentials from Terraform:")
            CONSOLE.print("[cyan]   cd terraform[/]")
            CONSOLE.print("[cyan]   terraform init -backend-config=bucket=stocks-terraform-state \\[/]")
            CONSOLE.print("[cyan]     -backend-config=key=stocks/terraform.tfstate \\[/]")
            CONSOLE.print("[cyan]     -backend-config=region=us-east-1 -backend-config=encrypt=true[/]")
            CONSOLE.print("[cyan]   $apiUrl = terraform output -raw api_url[/]")
            CONSOLE.print("[cyan]   $poolId = terraform output -raw cognito_user_pool_id[/]")
            CONSOLE.print("[cyan]   $clientId = terraform output -raw cognito_user_pool_client_id[/]")
            CONSOLE.print("")
            CONSOLE.print("2. Set environment variables in PowerShell:")
            CONSOLE.print("[cyan]   $env:DASHBOARD_API_URL = $apiUrl[/]")
            CONSOLE.print("[cyan]   $env:COGNITO_USER_POOL_ID = $poolId[/]")
            CONSOLE.print("[cyan]   $env:COGNITO_CLIENT_ID = $clientId[/]")
            CONSOLE.print("")
            CONSOLE.print("3. Run dashboard:")
            CONSOLE.print("[cyan]   python tools/dashboard/dashboard.py[/]")
            CONSOLE.print("")
            CONSOLE.print("[dim]Or use:[/] [cyan]--local[/] [dim]for localhost:3001[/]")
            CONSOLE.print("")
            CONSOLE.print("[dim]See: tools/dashboard/COGNITO_SETUP.md for full setup guide[/]")
            sys.exit(1)
        set_api_url(aws_url)
        data_source = "AWS"

        # Setup Cognito authentication for AWS mode
        from cognito_auth import get_cognito_auth, save_tokens
        auth = get_cognito_auth(require_auth=True)
        if auth and auth.is_authenticated():
            set_cognito_auth(auth)
            save_tokens(auth)

    if args.watch is not None:
        run_watch(max(10, args.watch), args.compact, data_source)
    else:
        run_once(args.compact, data_source)


if __name__ == "__main__":
    main()
