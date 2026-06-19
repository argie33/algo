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

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import traceback
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
    import select
    import termios
    import tty

    def _keypress() -> str:
        # Non-Windows implementation using select/termios for Unix-like systems
        # Use select with timeout=0 to check if input is available without blocking
        if select.select([sys.stdin], [], [], 0)[0]:
            try:
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    ch = sys.stdin.read(1).lower()
                    return ch if ch else ""
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                return ""
        return ""


import boto3
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from tools.dashboard.cognito_auth import get_cognito_auth, save_tokens
from tools.dashboard.error_boundary import error_summary_panel
from tools.dashboard.error_recovery import RenderRecovery
from tools.dashboard.fetchers import load_all
from tools.dashboard.formatters import mkt_hours_str
from tools.dashboard.panel_registry import get_panel_registry as _get_panel_registry
from tools.dashboard.panels import (
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
from tools.dashboard.utilities import (
    CONSOLE,
    ET,
    MASCOT_W,
    logger,
    set_api_url,
    set_cognito_auth,
)


class _LoadState:
    """Thread-safe state container for data loading and display."""

    def __init__(self):
        self.result = None
        self.elapsed = 0.0


class _WatchState:
    """Thread-safe state container for watch mode with frame tracking."""

    def __init__(self):
        self.result = None
        self.elapsed = 0.0
        self.loading = True
        self.last_load = 0.0
        self.frame = 0
        self.error = None


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


class _RenderWrapper:
    """Callable wrapper for render_dashboard to avoid recreating closures on every frame."""

    def __init__(self, compact: bool, data_source: str = "AWS"):
        self.compact = compact
        self.data_source = data_source
        self.elapsed = 0.0
        self.frame = 0
        self.view_mode = "normal"
        self.watch_interval = None
        self.last_load_time = None
        self.refreshing = False

    def __call__(self, data: dict) -> Layout:
        return render_dashboard(
            data,
            compact=self.compact,
            elapsed=self.elapsed,
            frame=self.frame,
            watch_interval=self.watch_interval,
            last_load_time=self.last_load_time,
            refreshing=self.refreshing,
            view_mode=self.view_mode,
            data_source=self.data_source,
        )


_REGISTRY_SKIPPED = False
_REGISTRY_FAILED = False
PANEL_REGISTRY = None

if os.environ.get("SKIP_PANEL_REGISTRY"):
    logger.info("Panel registry disabled via SKIP_PANEL_REGISTRY")
    _REGISTRY_SKIPPED = True
else:
    try:
        PANEL_REGISTRY = _get_panel_registry()
    except ImportError as e:
        logger.error(
            f"Panel registry import failed: {e}\n"
            "  This usually means a required dependency is missing.\n"
            "  Try: pip install -r requirements.txt"
        )
        _REGISTRY_FAILED = True
        sys.exit(1)
    except Exception as e:
        logger.error(
            f"Unexpected error initializing panel registry: {type(e).__name__}: {e}",
            exc_info=True,
        )
        logger.error(
            "Please file a bug report with the traceback above. "
            "To run without panel validation:\n"
            "  SKIP_PANEL_REGISTRY=1 python -m tools.dashboard.dashboard"
        )
        _REGISTRY_FAILED = True
        sys.exit(1)


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


def _ensure_aws_profile() -> None:
    """Ensure AWS_PROFILE environment variable is set to algo-developer."""
    if not os.environ.get("AWS_PROFILE"):
        os.environ["AWS_PROFILE"] = "algo-developer"
        logger.debug("Set AWS_PROFILE=algo-developer")


def _fetch_secrets_manager_credentials() -> tuple[str | None, str | None, str | None]:
    """Fetch dashboard credentials from AWS Secrets Manager. Returns (api_url, pool_id, client_id) or (None, None, None)."""

    try:
        # Ensure AWS_PROFILE is set
        _ensure_aws_profile()

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
        _ensure_aws_profile()

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
                    error_output = result.stderr.strip() if result.stderr else "(no error output)"
                    logger.warning(f"Terraform init failed: {error_output[:200]} - may need manual setup")
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
            error_output = result.stderr.strip() if result.stderr else "(no error output)"
            logger.warning(f"Terraform output failed: {error_output[:100]}")
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
        if not _validate_api_url(api_url):
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

    Returns empty dict if registry was skipped or failed to initialize (see startup logs for details).
    """
    if not PANEL_REGISTRY:
        if _REGISTRY_FAILED:
            logger.warning(
                "Panel registry failed to initialize - check startup logs for details"
            )
        elif not _REGISTRY_SKIPPED:
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
            f"[bold red]âš  Render Error[/]\n[dim]{error_line}[/]\n\n{recovery_status}"
        )
    else:
        content = f"[bold red]âš  Render Error[/]\n[dim]{error_line}[/]"

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
    state = _LoadState()
    done = threading.Event()
    bg_thread = None

    def bg():
        try:
            t0 = time.monotonic()
            state.result = load_all()
            state.elapsed = time.monotonic() - t0
        except Exception as e:
            logger.error(f"Background load error: {type(e).__name__}: {e}")
        finally:
            done.set()

    try:
        bg_thread = threading.Thread(target=bg, daemon=False)
        bg_thread.start()

        frame = 0
        view_mode = "normal"
        recovery = RenderRecovery()
        key_map = KEY_MAP
        render_wrapper = _RenderWrapper(compact, data_source)
        with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
            try:
                while True:
                    key = _keypress()
                    if key == "q":
                        break
                    if key in key_map:
                        target = key_map[key]
                        view_mode = "normal" if view_mode == target else target
                    frame += 1
                    if not done.is_set():
                        live.update(loading_layout(frame, data_source=data_source))
                    else:
                        render_wrapper.elapsed = state.elapsed
                        render_wrapper.frame = frame
                        render_wrapper.view_mode = view_mode
                        try:
                            layout, _recovery_status = recovery.render_with_recovery(
                                state.result, render_wrapper
                            )
                            live.update(layout)
                        except Exception as e:
                            error_panel = _handle_render_error(
                                e, recovery.state.get_recovery_status()
                            )
                            try:
                                live.update(error_panel)
                            except Exception as panel_error:
                                logger.error(
                                    f"Failed to render error panel: {type(panel_error).__name__}: {panel_error}"
                                )
                    time.sleep(0.125)
            except KeyboardInterrupt:
                pass
    finally:
        if bg_thread:
            done.set()
            bg_thread.join(timeout=10)
            if bg_thread.is_alive():
                logger.warning("Background thread did not exit within timeout")


def run_watch(interval: int, compact: bool, data_source: str = "AWS") -> None:
    """Watch mode: auto-refresh data every `interval` seconds, mascot dances continuously."""
    state = _WatchState()
    state_lock = threading.Lock()
    active_threads: list = []
    shutdown = threading.Event()

    def reload():
        try:
            with state_lock:
                state.loading = True
                state.error = None
            t0 = time.monotonic()
            new_result = load_all()
            new_elapsed = time.monotonic() - t0
            with state_lock:
                state.result = new_result
                state.elapsed = new_elapsed
                state.last_load = time.monotonic()
                state.loading = False
        except Exception as e:
            logger.error(f"Reload thread error: {type(e).__name__}: {e}")
            with state_lock:
                state.loading = False
                state.error = f"{type(e).__name__}: {e}"

    try:
        reload_thread = threading.Thread(target=reload, daemon=False)
        reload_thread.start()
        active_threads.append(reload_thread)

        view_mode = "normal"
        recovery = RenderRecovery()
        key_map = KEY_MAP
        render_wrapper = _RenderWrapper(compact, data_source)
        render_wrapper.watch_interval = interval
        with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
            try:
                while True:
                    key = _keypress()
                    if key == "q":
                        break
                    if key in key_map:
                        target = key_map[key]
                        view_mode = "normal" if view_mode == target else target
                    with state_lock:
                        state.frame += 1
                        current_frame = state.frame
                        is_loading = state.loading
                        current_last_load = state.last_load
                        current_result = state.result
                        current_elapsed = state.elapsed
                        current_error = state.error

                    if current_result is None:
                        if current_error:
                            error_panel = _handle_render_error(
                                RuntimeError(current_error),
                                recovery.state.get_recovery_status(),
                            )
                            try:
                                live.update(error_panel)
                            except Exception as panel_error:
                                logger.error(
                                    f"Failed to render error panel: {type(panel_error).__name__}: {panel_error}"
                                )
                        else:
                            live.update(loading_layout(current_frame, data_source=data_source))
                    else:
                        render_wrapper.elapsed = current_elapsed
                        render_wrapper.frame = current_frame
                        render_wrapper.last_load_time = current_last_load
                        render_wrapper.refreshing = is_loading
                        render_wrapper.view_mode = view_mode
                        try:
                            layout, _recovery_status = recovery.render_with_recovery(
                                current_result, render_wrapper
                            )
                            live.update(layout)
                        except Exception as e:
                            error_panel = _handle_render_error(
                                e, recovery.state.get_recovery_status()
                            )
                            try:
                                live.update(error_panel)
                            except Exception as panel_error:
                                logger.error(
                                    f"Failed to render error panel: {type(panel_error).__name__}: {panel_error}"
                                )

                        # Trigger data reload on interval or on transient errors
                        should_reload = (
                            not is_loading
                            and (time.monotonic() - current_last_load) >= interval
                        )
                        try:
                            should_retry_load = recovery.should_retry_data_load()
                        except Exception as e:
                            logger.error(
                                f"Failed to check recovery retry status: {type(e).__name__}: {e}"
                            )
                            should_retry_load = False

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
                    logger.warning("Thread still running after 10s timeout in watch mode")


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
        try:
            CONSOLE.print(__doc__)
        except Exception as e:
            logger.error(f"Failed to display legend: {type(e).__name__}: {e}")
        return

    if args.local:
        set_api_url("http://localhost:3001")
        data_source = "LOCAL"
    else:
        # AWS mode: fetch credentials from multiple sources (Secrets Manager -> Terraform -> Error)

        logger.info("AWS mode: Fetching dashboard credentials...")
        aws_url, pool_id, client_id = _fetch_secrets_manager_credentials()

        if not aws_url:
            logger.info("Secrets Manager unavailable, trying Terraform...")
            aws_url, pool_id, client_id = _fetch_terraform_credentials()

        if not aws_url:
            try:
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
            except Exception as e:
                logger.error(
                    f"Dashboard credentials not found. "
                    f"To automate setup, run: scripts/setup-local-dev.ps1"
                    f"Or manually:\n"
                    f"  1. Run: scripts/refresh-aws-credentials.ps1\n"
                    f"  2. Dashboard will auto-fetch from Secrets Manager / Terraform\n"
                    f"  After GitHub Actions deploy completes, run setup-local-dev.ps1 to refresh\n"
                    f"\n(Failed to display full message: {type(e).__name__})\n"
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
        if auth is None:
            logger.error(
                "[AUTH] Authentication required but failed - no credentials available. "
                "Set COGNITO_USERNAME + COGNITO_PASSWORD or run in interactive mode."
            )
            sys.exit(1)

        if auth.is_authenticated():
            set_cognito_auth(auth)
            save_tokens(auth)
        else:
            logger.warning(
                "[AUTH] Running with limited permissions - Cognito not fully authenticated"
            )
            set_cognito_auth(auth)  # Still set it, will fail on protected endpoints

    if args.watch is not None:
        run_watch(args.watch, args.compact, data_source)
    else:
        run_once(args.compact, data_source)


if __name__ == "__main__":
    main()


