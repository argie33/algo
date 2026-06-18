#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard

Usage:
  python -m tools.dashboard.dashboard                 # live view (AWS endpoints, q or Ctrl+C to exit)
  python -m tools.dashboard.dashboard -w              # watch mode, auto-refresh every 30s
  python -m tools.dashboard.dashboard -w 60           # watch mode, refresh every 60s
  python -m tools.dashboard.dashboard --compact       # narrow positions table
  python -m tools.dashboard.dashboard --local         # use local API (localhost:3001) instead of AWS

Modes:
  AWS (default): Set DASHBOARD_API_URL, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID env vars
  Local: Run local dev server on localhost:3001 first, then use --local flag
"""

import json
import os
import subprocess
import sys
import traceback


# Support both direct execution and module import
# If run directly (python dashboard.py), add repo root to sys.path before any imports
if __name__ == "__main__" and __package__ is None:
    _dashboard_dir = os.path.dirname(os.path.abspath(__file__))
    _repo_root = os.path.dirname(
        os.path.dirname(_dashboard_dir)
    )  # Go up two levels: dashboard -> tools -> repo_root
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    __package__ = "tools.dashboard"

import argparse
import threading
import time
from datetime import datetime
from urllib.parse import urlparse


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


import boto3
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from .cognito_auth import get_cognito_auth, save_tokens
from .error_boundary import error_summary_panel
from .error_recovery import RenderRecovery
from .fetchers import load_all
from .formatters import mkt_hours_str
from .panel_registry import get_panel_registry as _get_panel_registry
from .panels import (
    _expanded_layout,
    _extract_items,
    loading_layout,
    mascot_compact,
    panel_algo_health,
    panel_algo_health_expanded,
    panel_circuit,
    panel_circuit_expanded,
    panel_economic_expanded,
    panel_economic_pulse,
    panel_exposure_compact,
    panel_exposure_expanded,
    panel_header_market,
    panel_market_expanded,
    panel_performance_spark,
    panel_portfolio,
    panel_portfolio_perf_expanded,
    panel_positions,
    panel_recent_trades,
    panel_sector_compact,
    panel_sectors_expanded,
    panel_signals_compact,
    panel_signals_expanded,
    panel_trades_expanded,
)
from .utilities import CONSOLE, ET, MASCOT_W, logger, set_api_url, set_cognito_auth


KEY_MAP = {
    "p": "positions",
    "s": "signals",
    "h": "health",
    "r": "sectors",
    "t": "trades",
    "e": "economic",
    "f": "portfolio",
    "b": "circuit",
    "x": "exposure",
    "m": "market",
}


try:
    PANEL_REGISTRY = _get_panel_registry()
    _REGISTRY_AVAILABLE = True
except Exception as e:
    logger.error(
        f"Failed to initialize panel registry: {type(e).__name__}: {e}", exc_info=True
    )
    _REGISTRY_AVAILABLE = False
    PANEL_REGISTRY = None


def _validate_watch_interval(value):
    """Validate watch interval is between 10 and 600 seconds."""
    try:
        int_value = int(value)
        if int_value < 10:
            raise argparse.ArgumentTypeError(
                f"Watch interval must be at least 10 seconds (got {int_value})"
            )
        if int_value > 600:
            raise argparse.ArgumentTypeError(
                f"Watch interval must be at most 600 seconds (got {int_value})"
            )
        return int_value
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Watch interval must be an integer (got {value})"
        )


def _validate_api_url(url: str) -> bool:
    """Validate API URL format using urllib.parse.

    Returns True if URL is valid, False otherwise.
    Allows both http:// and https://, including localhost for local development.
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)

        # Must have http or https scheme
        if parsed.scheme not in ("http", "https"):
            return False

        # Must have a hostname (netloc contains host:port)
        if not parsed.netloc:
            return False

        # Validate hostname is not empty after parsing
        hostname = parsed.hostname
        if not hostname:
            return False

        return True
    except Exception:
        return False


def _fetch_secrets_manager_credentials() -> tuple[str | None, str | None, str | None]:
    """Fetch dashboard credentials from AWS Secrets Manager. Returns (api_url, pool_id, client_id) or (None, None, None)."""

    try:
        # Ensure AWS_PROFILE is set
        if not os.environ.get("AWS_PROFILE"):
            os.environ["AWS_PROFILE"] = "algo-developer"

        # Try to fetch from Secrets Manager
        client = boto3.client("secretsmanager", region_name="us-east-1")

        try:
            # Try dashboard-config secret first
            response = client.get_secret_value(SecretId="algo/dashboard-config")
            secret = json.loads(response["SecretString"])

            api_url = secret.get("api_url", "").strip()
            pool_id = secret.get("cognito_user_pool_id", "").strip()
            client_id = secret.get("cognito_user_pool_client_id", "").strip()

            if all([api_url, pool_id, client_id]):
                logger.info("Credentials fetched from AWS Secrets Manager")
                return (api_url, pool_id, client_id)
        except client.exceptions.ResourceNotFoundException:
            logger.debug("Secrets Manager secret not found")
        except Exception as e:
            logger.debug(f"Secrets Manager fetch failed: {type(e).__name__}")

        return (None, None, None)
    except Exception as e:
        logger.debug(f"Secrets Manager access failed: {type(e).__name__}")
        return (None, None, None)


def _fetch_terraform_credentials() -> tuple[str | None, str | None, str | None]:
    """Fetch AWS credentials from Terraform. Returns (api_url, pool_id, client_id) or (None, None, None)."""

    try:
        # Ensure AWS_PROFILE is set for Terraform
        if not os.environ.get("AWS_PROFILE"):
            os.environ["AWS_PROFILE"] = "algo-developer"
            logger.debug("Set AWS_PROFILE=algo-developer")

        # Find terraform directory - try multiple paths
        possible_roots = [
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),  # From tools/dashboard/
            os.getcwd(),  # Current working directory
            os.path.dirname(os.getcwd()),  # Parent of cwd
        ]

        tf_dir = None
        for root in possible_roots:
            candidate = os.path.join(root, "terraform")
            if os.path.isdir(candidate) and os.path.exists(
                os.path.join(candidate, "main.tf")
            ):
                tf_dir = candidate
                logger.debug(f"Found terraform directory at {tf_dir}")
                break

        if not tf_dir:
            logger.warning(
                "Terraform directory not found - cannot auto-fetch credentials"
            )
            return (None, None, None)

        # Check if terraform is available
        try:
            subprocess.run(
                ["terraform", "--version"], capture_output=True, timeout=5, check=True
            )
        except FileNotFoundError:
            logger.warning(
                "Terraform not installed - use launcher script or set env vars manually"
            )
            return (None, None, None)
        except subprocess.TimeoutExpired:
            logger.warning(
                "Terraform check timed out (running but slow) - "
                "use launcher script or set env vars manually"
            )
            return (None, None, None)
        except subprocess.CalledProcessError as e:
            logger.warning(
                "Terraform version check failed (code %d) - may be misconfigured",
                e.returncode,
            )
            return (None, None, None)

        # Initialize if needed
        if not os.path.exists(os.path.join(tf_dir, ".terraform")):
            logger.debug("Initializing Terraform...")
            try:
                result = subprocess.run(
                    ["terraform", "init", "-backend=true"],
                    cwd=tf_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    logger.warning("Terraform init failed - may need manual setup")
                    return (None, None, None)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Terraform init timed out (60s) - "
                    "running but slow, may need manual setup"
                )
                return (None, None, None)

        # Fetch outputs
        try:
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=tf_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Terraform output timed out (30s) - "
                "running but slow, may need manual setup"
            )
            return (None, None, None)

        if result.returncode != 0:
            logger.warning(f"Terraform output failed: {result.stderr[:100]}")
            return (None, None, None)

        try:
            outputs = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse terraform outputs: {e}")
            return (None, None, None)

        # Validate outputs are present and non-empty
        # Handle both JSON object format and raw value format
        api_url = None
        pool_id = None
        client_id = None

        if isinstance(outputs.get("api_url"), dict):
            api_url = outputs.get("api_url", {}).get("value", "").strip()
        else:
            api_url = str(outputs.get("api_url", "")).strip()

        if isinstance(outputs.get("cognito_user_pool_id"), dict):
            pool_id = outputs.get("cognito_user_pool_id", {}).get("value", "").strip()
        else:
            pool_id = str(outputs.get("cognito_user_pool_id", "")).strip()

        if isinstance(outputs.get("cognito_user_pool_client_id"), dict):
            client_id = (
                outputs.get("cognito_user_pool_client_id", {}).get("value", "").strip()
            )
        else:
            client_id = str(outputs.get("cognito_user_pool_client_id", "")).strip()

        if not all([api_url, pool_id, client_id]):
            logger.warning(
                "Terraform outputs incomplete: url=%s, pool=%s, client=%s",
                bool(api_url),
                bool(pool_id),
                bool(client_id),
            )
            logger.debug(f"Available outputs: {list(outputs.keys())}")
            return (None, None, None)

        # Validate API URL format
        if not api_url.startswith(("http://", "https://")):
            logger.error(f"Invalid API URL format from terraform: {api_url[:50]}")
            return (None, None, None)

        logger.info("Successfully fetched credentials from Terraform")
        return (api_url, pool_id, client_id)
    except Exception as e:
        logger.error(
            f"Failed to fetch terraform credentials: {type(e).__name__}: {e}\n  Operation: Read Terraform outputs (api_url, pool_id, client_id)\n  File: terraform/outputs.json"
        )
        return (None, None, None)


def _validate_panel_dependencies(data: dict) -> dict[str, bool]:
    """Validate that panel dependencies are available in data.

    Uses panel registry to check if each panel has its required endpoints.
    Returns dict of {panel_name: can_render}.

    Returns empty dict if registry failed to initialize (see startup logs for details).
    """
    if not _REGISTRY_AVAILABLE or not PANEL_REGISTRY:
        if not _REGISTRY_AVAILABLE:
            logger.warning(
                "Panel registry unavailable - check startup logs for initialization error"
            )
        return {}

    panel_status = {}
    for panel_name in PANEL_REGISTRY.get_panel_names():
        can_render, _ = PANEL_REGISTRY.can_render_panel(panel_name, data)
        panel_status[panel_name] = can_render

    return panel_status


def _handle_render_error(e: Exception, recovery_status: str = "") -> Panel:
    """Create an error panel for render failures with recovery info."""
    logger.error(f"Dashboard render error: {type(e).__name__}: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")

    error_line = f"{type(e).__name__}: {str(e)[:80]}"
    if recovery_status:
        content = (
            f"[bold red]âš  Render Error[/]\n[dim]{error_line}[/]\n\n{recovery_status}"
        )
    else:
        content = f"[bold red]âš  Render Error[/]\n[dim]{error_line}[/]"

    return Panel(
        Text.from_markup(content),
        title="[bold red]ERROR[/]",
        border_style="red",
    )


def render_dashboard(
    data: dict,
    compact: bool = False,
    elapsed: float = 0.0,
    frame: int = 0,
    watch_interval: int | None = None,
    last_load_time: float | None = None,
    refreshing: bool = False,
    view_mode: str = "normal",
    data_source: str = "AWS",
) -> Layout:
    valid_modes = {
        "normal",
        "circuit",
        "exposure",
        "market",
        "positions",
        "signals",
        "health",
        "sectors",
        "trades",
        "economic",
        "portfolio",
    }
    if view_mode not in valid_modes:
        logger.warning(f"Invalid view_mode '{view_mode}', falling back to 'normal'")
        view_mode = "normal"

    run = data.get("run") or {}
    cfg = data.get("cfg") or {}
    mkt = data.get("mkt") or {}
    port = data.get("port") or {}
    perf = data.get("perf") or {}
    pos = data.get("pos") or {}
    sig = data.get("sig") or {}
    hlth = (
        data.get("health") or {}
    )  # keep raw dict; ready_to_trade/critical_stale available to panels
    cb = data.get("cb") or {}
    rec = data.get("trades") or {}
    srank = _extract_items(data.get("srank") or {})
    act = data.get("activity") or {}
    exp_f = data.get("exp_factors") or {}
    eco = data.get("eco") or {}
    notifs = data.get("notifs") or []
    sentiment = data.get("sentiment") or {}
    econ_cal = _extract_items(data.get("econ_cal") or {})
    risk = data.get("risk") or {}
    perf_anl = data.get("perf_anl") or {}
    sig_eval = data.get("sig_eval") or {}
    sec_rot = data.get("sec_rot") or {}
    algo_metrics = _extract_items(data.get("algo_metrics") or {})
    irank = _extract_items(data.get("irank") or {})
    audit = _extract_items(data.get("audit") or {})
    exec_hist = _extract_items(data.get("exec_hist") or {})
    scores = data.get("scores") or {}

    now_et = datetime.now(ET)
    _mkt_badge, _mkt_cdown = mkt_hours_str()
    mkt_s = f"{_mkt_badge}  [dim]{_mkt_cdown}[/]"
    ts = now_et.strftime("%a %b %d  %I:%M %p ET")

    refresh_s = ""
    if refreshing:
        refresh_s = "  [cyan]â†»[/]"
    elif watch_interval is not None and last_load_time is not None:
        secs = max(0, watch_interval - int(time.monotonic() - last_load_time))
        refresh_s = f"  [dim]â†»{secs}s[/]"

    hdr_panel = panel_header_market(
        mkt, sentiment, ts, mkt_s, elapsed, refresh_s, cfg=cfg, data_source=data_source
    )
    exp_panel = panel_exposure_compact(exp_f)
    mascot_panel = mascot_compact(data, frame)

    # Check for data fetch errors and show summary if present
    error_panel = error_summary_panel(data)

    outer = Layout()
    # If there are errors, add error panel at the top
    if error_panel:
        outer.split_column(
            Layout(name="errors", size=3),
            Layout(name="top", size=10),
            Layout(name="r1", ratio=2),
            Layout(name="r2", ratio=2),
            Layout(name="r3", ratio=2),
            Layout(name="pos", ratio=3),
        )
        outer["errors"].update(error_panel)
    else:
        outer.split_column(
            Layout(name="top", size=10),
            Layout(name="r1", ratio=2),
            Layout(name="r2", ratio=2),
            Layout(name="r3", ratio=2),
            Layout(name="pos", ratio=3),
        )

    outer["top"].split_row(
        Layout(name="hdr", ratio=1),
        Layout(name="exposure", ratio=1),
        Layout(name="mascot", size=MASCOT_W),
    )
    outer["top"]["hdr"].update(hdr_panel)
    outer["top"]["exposure"].update(exp_panel)
    outer["top"]["mascot"].update(mascot_panel)

    outer["r1"].split_row(
        Layout(panel_circuit(cb), ratio=3, name="cb"),
        Layout(
            panel_algo_health(
                run,
                act,
                hlth,
                notifs,
                algo_metrics,
                audit,
                exec_hist,
                risk=risk,
            ),
            ratio=5,
            name="health",
        ),
    )

    outer["r2"].split_row(
        Layout(panel_portfolio(port, cfg, risk=risk, perf=perf), name="portfolio"),
        Layout(panel_performance_spark(perf, rec, perf_anl, pos=pos), name="perf"),
        Layout(panel_economic_pulse(eco, econ_cal), name="eco"),
    )

    outer["r3"].split_row(
        Layout(
            panel_signals_compact(sig, sig_eval, scores=scores), ratio=3, name="signals"
        ),
        Layout(
            panel_sector_compact(srank, pos, port, sec_rot, irank),
            ratio=2,
            name="sectors",
        ),
    )

    outer["pos"].split_row(
        Layout(panel_positions(pos, compact, trades=rec), ratio=5, name="positions"),
        Layout(panel_recent_trades(rec), ratio=3, name="recent_trades"),
    )

    _exp_top = (hdr_panel, exp_panel, mascot_panel)

    if view_mode == "circuit":
        return _expanded_layout(*_exp_top, panel_circuit_expanded(cb))

    if view_mode == "exposure":
        return _expanded_layout(*_exp_top, panel_exposure_expanded(exp_f))

    if view_mode == "market":
        return _expanded_layout(*_exp_top, panel_market_expanded(mkt, sentiment))

    if view_mode == "positions":
        hint = Text.from_markup(
            "[dim]press [/][bold cyan]p[/][dim] to return to dashboard[/]"
        )
        _pos_items = pos.get("items", []) if isinstance(pos, dict) else (pos or [])
        return _expanded_layout(
            *_exp_top,
            Panel(
                Group(
                    hint,
                    Rule(style="dim"),
                    panel_positions(pos, compact=False, trades=rec, extended=True),
                ),
                title=f"[bold cyan]ALL POSITIONS ({len(_pos_items)})[/]  [dim][p] return[/]",
                border_style="cyan",
                padding=(0, 1),
            ),
        )

    if view_mode == "signals":
        return _expanded_layout(
            *_exp_top, panel_signals_expanded(sig, sig_eval, scores=scores)
        )

    if view_mode == "health":
        return _expanded_layout(
            *_exp_top,
            panel_algo_health_expanded(
                run,
                act,
                hlth,
                notifs,
                algo_metrics,
                audit,
                exec_hist,
                risk=risk,
            ),
        )

    if view_mode == "sectors":
        return _expanded_layout(
            *_exp_top, panel_sectors_expanded(srank, pos, port, sec_rot, irank)
        )

    if view_mode == "trades":
        return _expanded_layout(*_exp_top, panel_trades_expanded(rec))

    if view_mode == "economic":
        return _expanded_layout(*_exp_top, panel_economic_expanded(eco, econ_cal))

    if view_mode == "portfolio":
        return _expanded_layout(
            *_exp_top,
            panel_portfolio_perf_expanded(
                port, cfg, risk=risk, perf=perf, perf_anl=perf_anl, pos=pos
            ),
        )

    return outer


def run_once(compact: bool, data_source: str = "AWS") -> None:
    """Single Live session: mascot stays in upper right through loading and live view."""
    result: list = [None]
    elapsed: list = [0.0]
    done = threading.Event()
    bg_thread = None

    def bg():
        nonlocal result, elapsed
        try:
            t0 = time.monotonic()
            result[0] = load_all()
            elapsed[0] = time.monotonic() - t0
        except Exception as e:
            logger.error(f"Background load error: {type(e).__name__}: {e}")
        finally:
            done.set()

    try:
        bg_thread = threading.Thread(target=bg, daemon=False)
        bg_thread.start()

        frame = 0
        view_mode = ["normal"]
        recovery = RenderRecovery()
        key_map = KEY_MAP
        with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
            try:
                while True:
                    key = _keypress()
                    if key == "q":
                        break
                    if key in key_map:
                        target = key_map[key]
                        view_mode[0] = "normal" if view_mode[0] == target else target
                    frame += 1
                    if not done.is_set():
                        live.update(loading_layout(frame, data_source=data_source))
                    else:

                        def render_fn(data):
                            return render_dashboard(
                                data,
                                compact=compact,
                                elapsed=elapsed[0],
                                frame=frame,
                                view_mode=view_mode[0],
                                data_source=data_source,
                            )

                        try:
                            layout, recovery_status = recovery.render_with_recovery(
                                result[0], render_fn
                            )
                            live.update(layout)
                        except Exception as e:
                            live.update(
                                _handle_render_error(
                                    e, recovery.state.get_recovery_status()
                                )
                            )
                    time.sleep(0.125)
            except KeyboardInterrupt:
                pass
    finally:
        if bg_thread:
            done.set()
            bg_thread.join(timeout=10)
            if bg_thread.is_alive():
                print(
                    "âš ï¸  Background thread did not exit within timeout", file=sys.stderr
                )


def run_watch(interval: int, compact: bool, data_source: str = "AWS") -> None:
    """Watch mode: auto-refresh data every `interval` seconds, mascot dances continuously."""
    result: list = [None]
    elapsed: list = [0.0]
    loading: list = [True]
    last_load: list = [0.0]
    frame: list = [0]
    error: list = [None]
    state_lock = threading.Lock()
    active_threads: list = []
    shutdown = threading.Event()

    def reload():
        try:
            with state_lock:
                loading[0] = True
                error[0] = None
            t0 = time.monotonic()
            result[0] = load_all()
            elapsed[0] = time.monotonic() - t0
            with state_lock:
                last_load[0] = time.monotonic()
                loading[0] = False
        except Exception as e:
            logger.error(f"Reload thread error: {type(e).__name__}: {e}")
            with state_lock:
                loading[0] = False
                error[0] = f"{type(e).__name__}: {e}"

    try:
        reload_thread = threading.Thread(target=reload, daemon=False)
        reload_thread.start()
        active_threads.append(reload_thread)

        view_mode = ["normal"]
        recovery = RenderRecovery()
        key_map = KEY_MAP
        with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
            try:
                while True:
                    key = _keypress()
                    if key == "q":
                        break
                    if key in key_map:
                        target = key_map[key]
                        view_mode[0] = "normal" if view_mode[0] == target else target
                    frame[0] += 1
                    with state_lock:
                        is_loading = loading[0]
                        current_last_load = last_load[0]
                        current_result = result[0]
                        current_elapsed = elapsed[0]
                        current_error = error[0]

                    if current_result is None:
                        if current_error:
                            live.update(
                                _handle_render_error(
                                    RuntimeError(current_error),
                                    recovery.state.get_recovery_status(),
                                )
                            )
                        else:
                            live.update(loading_layout(frame[0], data_source=data_source))
                    else:

                        def render_fn(data):
                            return render_dashboard(
                                data,
                                compact=compact,
                                elapsed=current_elapsed,
                                frame=frame[0],
                                watch_interval=interval,
                                last_load_time=current_last_load,
                                refreshing=is_loading,
                                view_mode=view_mode[0],
                                data_source=data_source,
                            )

                        try:
                            layout, recovery_status = recovery.render_with_recovery(
                                current_result, render_fn
                            )
                            live.update(layout)
                        except Exception as e:
                            live.update(
                                _handle_render_error(
                                    e, recovery.state.get_recovery_status()
                                )
                            )

                        # Trigger data reload on interval or on transient errors
                        should_reload = (
                            not is_loading
                            and (time.monotonic() - current_last_load) >= interval
                        )
                        should_retry_load = recovery.should_retry_data_load()

                        if should_reload or should_retry_load:
                            reload_thread = threading.Thread(
                                target=reload, daemon=False
                            )
                            reload_thread.start()
                            active_threads.append(reload_thread)
                    time.sleep(0.125)
            except KeyboardInterrupt:
                pass
    finally:
        shutdown.set()
        for thread in active_threads:
            if thread:
                thread.join(timeout=10)
                if thread.is_alive():
                    print(
                        "âš ï¸  Thread still running after 10s timeout in watch mode",
                        file=sys.stderr,
                    )


def main():
    pa = argparse.ArgumentParser(
        description="Algo ops terminal dashboard",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pa.add_argument(
        "-w",
        "--watch",
        nargs="?",
        const=30,
        type=_validate_watch_interval,
        metavar="SECS",
        help="Watch mode, auto-refresh interval in seconds (5-600, default 30s)",
    )
    pa.add_argument(
        "--compact",
        "-c",
        action="store_true",
        help="Omit T1 and Sector columns from positions table",
    )
    pa.add_argument(
        "--local",
        action="store_true",
        help="Use local API (localhost:3001) instead of AWS endpoints",
    )
    pa.add_argument(
        "--legend",
        "-l",
        action="store_true",
        help="Print a guide explaining every term and panel, then exit",
    )
    args = pa.parse_args()

    if args.legend:
        CONSOLE.print(__doc__)
        return

    if args.local:
        set_api_url("http://localhost:3001")
        data_source = "LOCAL"
    else:
        # AWS mode: fetch credentials from multiple sources (Secrets Manager â†’ Terraform â†’ Error)

        logger.info("AWS mode: Fetching dashboard credentials...")
        aws_url, pool_id, client_id = _fetch_secrets_manager_credentials()

        if not aws_url:
            logger.info("Secrets Manager unavailable, trying Terraform...")
            aws_url, pool_id, client_id = _fetch_terraform_credentials()

        if not aws_url:
            CONSOLE.print("[bold red]ERROR:[/] Dashboard credentials not found")
            CONSOLE.print("")
            CONSOLE.print("[bold cyan]To automate setup:[/]")
            CONSOLE.print("[yellow]Run this to set up local dev environment:[/]")
            CONSOLE.print("[cyan]   scripts/setup-local-dev.ps1[/]")
            CONSOLE.print("")
            CONSOLE.print("[bold cyan]Or manually:[/]")
            CONSOLE.print("[yellow]1. Fetch AWS credentials:[/]")
            CONSOLE.print("[cyan]   scripts/refresh-aws-credentials.ps1[/]")
            CONSOLE.print("")
            CONSOLE.print(
                "[yellow]2. Dashboard will auto-fetch from Secrets Manager / Terraform[/]"
            )
            CONSOLE.print(
                "[dim]After GitHub Actions deploy completes, run setup-local-dev.ps1 to refresh[/]"
            )
            sys.exit(1)

        set_api_url(aws_url)
        os.environ["DASHBOARD_API_URL"] = aws_url
        os.environ["COGNITO_USER_POOL_ID"] = pool_id
        os.environ["COGNITO_CLIENT_ID"] = client_id
        logger.info("Dashboard credentials loaded from Secrets Manager")
        data_source = "AWS"

        # Cognito authentication - dynamic with fallback

        auth = get_cognito_auth(require_auth=True)
        if auth and auth.is_authenticated():
            set_cognito_auth(auth)
            save_tokens(auth)
        elif auth:
            logger.warning(
                "[AUTH] Running with limited permissions - Cognito not available"
            )
            set_cognito_auth(auth)  # Still set it, will fail on protected endpoints

    if args.watch is not None:
        run_watch(args.watch, args.compact, data_source)
    else:
        run_once(args.compact, data_source)


if __name__ == "__main__":
    main()
