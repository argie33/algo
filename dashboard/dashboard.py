#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard

Usage:
  python -m dashboard                                 # live view (AWS endpoints, q or Ctrl+C to exit)
  python -m dashboard -w                              # watch mode, auto-refresh every 30s
  python -m dashboard -w 60                           # watch mode, refresh every 60s
  python -m dashboard --compact                       # narrow positions table
  python -m dashboard --local                         # use local API (localhost:3001) instead of AWS

Modes:
  AWS (default): Set DASHBOARD_API_URL, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID env vars
  Local: Run local dev server on localhost:3001 first, then use --local flag
"""

import os
import sys

# When run as a script (python dashboard/dashboard.py) the dashboard/ dir lands on
# sys.path and `from dashboard.X` resolves to dashboard.py itself, not the package.
# Insert the repo root so absolute intra-package imports always resolve correctly.
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import argparse
import json
import subprocess
import threading
import time
import traceback
from datetime import datetime
from typing import Any, cast
from urllib.parse import urlparse

try:
    import msvcrt

    def _keypress() -> str:
        if msvcrt.kbhit():  # type: ignore[attr-defined]
            ch = msvcrt.getch()  # type: ignore[attr-defined]
            return str(ch.decode("utf-8", errors="ignore").lower())
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
                old_settings = termios.tcgetattr(fd)  # type: ignore[attr-defined,unused-ignore]
                try:
                    tty.setraw(fd)  # type: ignore[attr-defined,unused-ignore]
                    ch = sys.stdin.read(1).lower()
                    return ch if ch else ""
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)  # type: ignore[attr-defined,unused-ignore]
            except (OSError, AttributeError, ValueError):
                return ""
        return ""


import boto3
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.markup import escape as _escape_markup
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from dashboard.api_data_layer import (
    get_cognito_auth,
    set_api_url,
    set_cognito_auth,
)
from dashboard.cognito_auth import (
    get_cognito_auth as get_cognito_auth_instance,
)
from dashboard.cognito_auth import (
    save_tokens,
)
from dashboard.error_boundary import (
    error_summary_panel,
    error_summary_panel_expanded,
    has_error,
)
from dashboard.error_recovery import RenderRecovery
from dashboard.fetchers import load_all
from dashboard.formatters import mkt_hours_str
from dashboard.panel_registry import get_panel_registry as _get_panel_registry
from dashboard.panels import (
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
from dashboard.utilities import (
    CONSOLE,
    ET,
    MASCOT_W,
    logger,
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
    "d": "errors",
}


class _RenderWrapper:
    """Callable wrapper for render_dashboard to avoid recreating closures on every frame."""

    def __init__(self, compact: bool, data_source: str = "AWS"):
        self.compact = compact
        self.data_source = data_source
        self.elapsed = 0.0
        self.frame = 0
        self.view_mode = "normal"
        self.watch_interval: int | None = None
        self.last_load_time: float | None = None
        self.refreshing = False
        self._state_lock = threading.Lock()

    def __call__(self, data: dict) -> Layout:
        with self._state_lock:
            elapsed = self.elapsed
            frame = self.frame
            view_mode = self.view_mode
            watch_interval = self.watch_interval
            last_load_time = self.last_load_time
            refreshing = self.refreshing

        return render_dashboard(
            data,
            compact=self.compact,
            elapsed=elapsed,
            frame=frame,
            watch_interval=watch_interval,
            last_load_time=last_load_time,
            refreshing=refreshing,
            view_mode=view_mode,
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
            "  Try: pip install -r requirements.txt\n"
            "  Dashboard will continue with graceful fallback."
        )
        _REGISTRY_FAILED = True
    except Exception as e:
        logger.error(
            f"Unexpected error initializing panel registry: {type(e).__name__}: {e}",
            exc_info=True,
        )
        logger.error("Panel registry initialization failed. Dashboard will continue with graceful fallback.")
        _REGISTRY_FAILED = True


def _validate_watch_interval(value):
    """Validate watch interval is between 10 and 600 seconds."""
    try:
        int_value = int(value)
        if int_value < 10:
            raise argparse.ArgumentTypeError(f"Watch interval must be at least 10 seconds (got {int_value})")
        if int_value > 600:
            raise argparse.ArgumentTypeError(f"Watch interval must be at most 600 seconds (got {int_value})")
        return int_value
    except ValueError:
        raise argparse.ArgumentTypeError(f"Watch interval must be an integer (got {value})")


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
    except Exception as e:
        logger.error("API URL validation failed for '%s': %s", url, e)
        return False


def _ensure_aws_profile() -> None:
    """Ensure AWS_PROFILE environment variable is set to algo-developer."""
    if not os.environ.get("AWS_PROFILE"):
        os.environ["AWS_PROFILE"] = "algo-developer"
        logger.debug("Set AWS_PROFILE=algo-developer")


def _fetch_secrets_manager_credentials() -> tuple[str | None, str | None, str | None]:
    """Fetch dashboard credentials from AWS Secrets Manager.

    Returns (api_url, pool_id, client_id) or (None, None, None).
    """

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
            logger.debug("Secrets Manager fetch failed: %s", type(e).__name__)

        return (None, None, None)
    except Exception as e:
        logger.debug("Secrets Manager access failed: %s", type(e).__name__)
        return (None, None, None)


def _find_terraform_directory() -> str | None:
    """Find terraform directory from multiple candidate locations."""
    for root in [
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        os.getcwd(),
        os.path.dirname(os.getcwd()),
    ]:
        candidate = os.path.join(root, "terraform")
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "main.tf")):
            logger.debug("Found terraform directory at %s", candidate)
            return candidate
    return None


def _check_terraform_installed() -> bool:
    """Check if terraform CLI is available."""
    try:
        subprocess.run(["terraform", "--version"], capture_output=True, timeout=5, check=True)
        return True
    except FileNotFoundError:
        logger.warning("Terraform not installed - use launcher script or set env vars manually")
    except subprocess.TimeoutExpired:
        logger.warning("Terraform check timed out (running but slow) - use launcher script or set env vars manually")
    except subprocess.CalledProcessError as e:
        logger.warning(
            "Terraform version check failed (code %d) - may be misconfigured",
            e.returncode,
        )
    return False


def _init_terraform(tf_dir: str) -> bool:
    """Initialize terraform if needed."""
    if os.path.exists(os.path.join(tf_dir, ".terraform")):
        return True
    logger.debug("Initializing Terraform...")
    try:
        result = subprocess.run(
            ["terraform", "init", "-backend=true"],
            cwd=tf_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return True
        error_output = result.stderr.strip() if result.stderr else "(no error output)"
        logger.warning("Terraform init failed: %s - may need manual setup", error_output[:200])
    except subprocess.TimeoutExpired:
        logger.warning("Terraform init timed out (60s) - running but slow, may need manual setup")
    return False


def _get_terraform_outputs(tf_dir: str) -> dict | None:
    """Fetch terraform outputs as JSON dict."""
    try:
        result = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=tf_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Terraform output timed out (30s) - running but slow, may need manual setup")
        return None
    if result.returncode != 0:
        error_output = result.stderr.strip() if result.stderr else "(no error output)"
        logger.warning("Terraform output failed: %s", error_output[:100])
        return None
    try:
        return cast(dict[str, Any], json.loads(result.stdout))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse terraform outputs: {e}")
        return None


def _extract_tf_value(outputs: dict, key: str) -> str | None:
    """Extract terraform output value, handling both dict and string formats."""
    val = outputs.get(key)
    result = val.get("value", "").strip() if isinstance(val, dict) else str(val or "").strip()
    return result if result else None


def _fetch_terraform_credentials() -> tuple[str | None, str | None, str | None]:
    """Fetch AWS credentials from Terraform. Returns (api_url, pool_id, client_id) or (None, None, None)."""
    try:
        _ensure_aws_profile()
        tf_dir = _find_terraform_directory()
        if not tf_dir:
            logger.warning("Terraform directory not found - cannot auto-fetch credentials")
            return (None, None, None)
        if not _check_terraform_installed():
            return (None, None, None)
        if not _init_terraform(tf_dir):
            return (None, None, None)

        outputs = _get_terraform_outputs(tf_dir)
        if not outputs:
            return (None, None, None)

        api_url = _extract_tf_value(outputs, "api_url")
        pool_id = _extract_tf_value(outputs, "cognito_user_pool_id")
        client_id = _extract_tf_value(outputs, "cognito_user_pool_client_id")

        if api_url is None or pool_id is None or client_id is None:
            logger.warning(
                "Terraform outputs incomplete: url=%s, pool=%s, client=%s",
                bool(api_url),
                bool(pool_id),
                bool(client_id),
            )
            logger.debug(f"Available outputs: {list(outputs.keys())}")
            return (None, None, None)

        if not _validate_api_url(api_url):
            logger.error(f"Invalid API URL format from terraform: {api_url[:50]}")
            return (None, None, None)

        logger.info("Successfully fetched credentials from Terraform")
        return (api_url, pool_id, client_id)
    except Exception as e:
        logger.error(
            f"Failed to fetch terraform credentials: {type(e).__name__}: {e}\n"
            f"  Operation: Read Terraform outputs (api_url, pool_id, client_id)\n"
            f"  File: terraform/outputs.json"
        )
        return (None, None, None)


def _validate_panel_dependencies(data: dict) -> dict[str, bool]:
    """Validate that panel dependencies are available in data.

    Uses panel registry to check if each panel has its required endpoints.
    Returns dict of {panel_name: can_render}.

    Raises RuntimeError if registry was skipped or failed to initialize (see startup logs for details).
    """
    if not PANEL_REGISTRY:
        if _REGISTRY_FAILED:
            raise RuntimeError("Panel registry failed to initialize - check startup logs for details")
        elif not _REGISTRY_SKIPPED:
            raise RuntimeError("Panel registry unavailable - check startup logs for initialization error")
        raise RuntimeError("Panel registry not initialized")

    panel_status = {}
    for panel_name in PANEL_REGISTRY.get_panel_names():
        can_render, _ = PANEL_REGISTRY.can_render_panel(panel_name, data)
        panel_status[panel_name] = can_render

    return panel_status


def _check_auth_lost() -> Panel | None:
    """Check if authentication was lost and return error panel if needed."""
    auth = get_cognito_auth()
    if auth and auth.has_lost_authentication():
        content = (
            "[bold red]Authentication Lost[/]\n"
            "[dim]Token refresh failed - please re-authenticate[/]\n\n"
            "[yellow]To continue:[/]\n"
            "[dim]� Restart the dashboard\n"
            "� Or set COGNITO_USERNAME + COGNITO_PASSWORD environment variables\n"
            "� Then run the dashboard again[/]"
        )
        return Panel(
            Text.from_markup(content),
            title="[bold red]RE-AUTHENTICATION REQUIRED[/]",
            border_style="red",
        )
    return None


def _handle_render_error(e: Exception, recovery_status: str | None = None) -> Panel:
    """Create an error panel for render failures with recovery info."""
    logger.error(f"Dashboard render error: {type(e).__name__}: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")

    error_line = _escape_markup(f"{type(e).__name__}: {str(e)[:80]}")
    if recovery_status:
        content = f"[bold red]⚠  Render Error[/]\n[dim]{error_line}[/]\n\n{recovery_status}"
    else:
        content = f"[bold red]⚠  Render Error[/]\n[dim]{error_line}[/]"

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
        "errors",
    }
    if view_mode not in valid_modes:
        logger.warning(f"Invalid view_mode '{view_mode}', falling back to 'normal'")
        view_mode = "normal"

    run = data.get("run")
    cfg = data.get("cfg")
    mkt = data.get("mkt")
    port = data.get("port")
    perf = data.get("perf")
    pos = data.get("pos")
    sig = data.get("sig")
    hlth = data.get("health")
    cb = data.get("cb")
    rec = data.get("trades")
    srank = _extract_items(data.get("srank"))
    act = data.get("activity")
    exp_f = data.get("exp_factors")
    eco = data.get("eco")
    notifs = data.get("notifs")
    sentiment = data.get("sentiment")
    econ_cal = _extract_items(data.get("econ_cal"))
    risk = data.get("risk")
    perf_anl = data.get("perf_anl")
    sig_eval = data.get("sig_eval")
    sec_rot = data.get("sec_rot")
    algo_metrics = _extract_items(data.get("algo_metrics"))
    irank = _extract_items(data.get("irank"))
    audit = _extract_items(data.get("audit"))
    exec_hist = _extract_items(data.get("exec_hist"))
    scores = data.get("scores")

    hdr_panel, exp_panel = _render_header_components(
        mkt, cfg, sentiment, elapsed, watch_interval, last_load_time, refreshing, data_source, exp_f
    )
    mascot_panel = mascot_compact(data, frame)

    auth_lost_panel = _check_auth_lost()
    error_panel = error_summary_panel(data)

    outer = Layout()
    if auth_lost_panel:
        outer.split_column(
            Layout(name="auth_error", size=5),
            Layout(name="top", size=10),
            Layout(name="r1", ratio=2),
            Layout(name="r2", ratio=2),
            Layout(name="r3", ratio=2),
            Layout(name="pos", ratio=3),
        )
        outer["auth_error"].update(auth_lost_panel)
    elif error_panel:
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

    _render_dashboard_body(
        outer,
        run, act, hlth, notifs, algo_metrics, audit, exec_hist, risk,
        cb,
        port, cfg, perf, rec, perf_anl, pos,
        eco, econ_cal,
        sig, sig_eval, scores,
        srank, sec_rot, irank,
        compact,
    )

    expanded_layout = _render_expanded_view(
        view_mode,
        hdr_panel, exp_panel, mascot_panel,
        cb, exp_f, mkt, sentiment,
        pos, compact, rec,
        sig, sig_eval, scores,
        run, act, hlth, notifs, algo_metrics, audit, exec_hist, risk,
        srank, port, sec_rot, irank,
        cfg, perf, perf_anl,
        eco, econ_cal,
        data,
    )

    return expanded_layout if expanded_layout is not None else outer


def _render_header_components(
    mkt: Any,
    cfg: Any,
    sentiment: Any,
    elapsed: float,
    watch_interval: int | None,
    last_load_time: float | None,
    refreshing: bool,
    data_source: str,
    exp_f: Any,
) -> tuple[Panel, Panel]:
    """Render header and exposure panels with error handling.

    Returns (header_panel, exposure_panel).
    """
    now_et = datetime.now(ET)
    _mkt_badge, _mkt_cdown = mkt_hours_str()
    mkt_s = f"{_mkt_badge}  [dim]{_mkt_cdown}[/]"
    ts = now_et.strftime("%a %b %d  %I:%M %p ET")

    refresh_s = ""
    if refreshing:
        refresh_s = "  [cyan]↻[/]"
    elif watch_interval is not None and last_load_time is not None:
        secs = max(0, watch_interval - int(time.monotonic() - last_load_time))
        refresh_s = f"  [dim]↻{secs}s[/]"

    if has_error(mkt) or has_error(cfg):
        hdr_panel = Panel(
            Text.from_markup("[red]Market/Config Error - Dashboard data unavailable[/]"),
            title="[bold red]✗ Data Error[/]",
            border_style="red",
        )
    else:
        hdr_panel = panel_header_market(
            mkt,
            sentiment,
            ts,
            mkt_s,
            elapsed,
            refresh_s,
            cfg=cfg,
            data_source=data_source,
        )

    exp_panel = panel_exposure_compact(exp_f) if not has_error(exp_f) else Panel("[red]Exposure factors unavailable[/]")
    return hdr_panel, exp_panel


def _render_dashboard_body(
    outer: Layout,
    run: Any, act: Any, hlth: Any, notifs: Any, algo_metrics: Any, audit: Any, exec_hist: Any, risk: Any,
    cb: Any,
    port: Any, cfg: Any, perf: Any, rec: Any, perf_anl: Any, pos: Any,
    eco: Any, econ_cal: Any,
    sig: Any, sig_eval: Any, scores: Any,
    srank: Any, sec_rot: Any, irank: Any,
    compact: bool,
) -> None:
    """Build main dashboard body layout with all panels.

    Modifies outer Layout in place.
    """
    cb_panel = (
        panel_circuit(cb) if not has_error(cb) else Panel("[red]Circuit breakers unavailable[/]", border_style="red")
    )
    health_panel = (
        panel_algo_health(run, act, hlth, notifs, algo_metrics, audit, exec_hist, risk=risk)
        if not (has_error(run) or has_error(hlth))
        else Panel("[red]Health data unavailable[/]", border_style="red")
    )

    outer["r1"].split_row(
        Layout(cb_panel, ratio=3, name="cb"),
        Layout(health_panel, ratio=5, name="health"),
    )

    port_panel = (
        panel_portfolio(port, cfg, risk=risk, perf=perf)
        if not (has_error(port) or has_error(cfg))
        else Panel("[red]Portfolio unavailable[/]", border_style="red")
    )
    perf_panel = (
        panel_performance_spark(perf, rec, perf_anl, pos=pos)
        if not (has_error(perf) or has_error(rec))
        else Panel("[red]Performance unavailable[/]", border_style="red")
    )
    eco_panel = (
        panel_economic_pulse(eco, econ_cal)
        if not has_error(eco)
        else Panel("[red]Economic data unavailable[/]", border_style="red")
    )

    outer["r2"].split_row(
        Layout(port_panel, name="portfolio"),
        Layout(perf_panel, name="perf"),
        Layout(eco_panel, name="eco"),
    )

    sig_panel = (
        panel_signals_compact(sig, sig_eval, scores=scores)
        if not (has_error(sig) or has_error(scores))
        else Panel("[red]Signals unavailable[/]", border_style="red")
    )
    sector_panel = (
        panel_sector_compact(srank, pos, port, sec_rot, irank)
        if not (has_error(pos) or has_error(port))
        else Panel("[red]Sectors unavailable[/]", border_style="red")
    )

    outer["r3"].split_row(
        Layout(sig_panel, ratio=3, name="signals"),
        Layout(sector_panel, ratio=2, name="sectors"),
    )

    pos_panel = (
        panel_positions(pos, compact, trades=rec)
        if not (has_error(pos) or has_error(rec))
        else Panel("[red]Positions unavailable[/]", border_style="red")
    )
    trades_panel = (
        panel_recent_trades(rec)
        if not has_error(rec)
        else Panel("[red]Recent trades unavailable[/]", border_style="red")
    )

    outer["pos"].split_row(
        Layout(pos_panel, ratio=5, name="positions"),
        Layout(trades_panel, ratio=3, name="recent_trades"),
    )


def _render_expanded_view(
    view_mode: str,
    hdr_panel: Panel, exp_panel: Panel, mascot_panel: Panel,
    cb: Any,
    exp_f: Any,
    mkt: Any, sentiment: Any,
    pos: Any, compact: bool, rec: Any,
    sig: Any, sig_eval: Any, scores: Any,
    run: Any, act: Any, hlth: Any, notifs: Any, algo_metrics: Any, audit: Any, exec_hist: Any, risk: Any,
    srank: Any, port: Any, sec_rot: Any, irank: Any,
    cfg: Any, perf: Any, perf_anl: Any,
    eco: Any, econ_cal: Any,
    data: dict,
) -> Layout | None:
    """Render expanded view for the given view_mode.

    Returns the expanded Layout, or None if view_mode is 'normal'.
    """
    if view_mode == "normal":
        return None

    _exp_top = (hdr_panel, exp_panel, mascot_panel)

    match view_mode:
        case "circuit":
            if has_error(cb):
                panel = Panel("[red]Circuit breaker data unavailable[/]", border_style="red")
                return _expanded_layout(*_exp_top, panel)
            return _expanded_layout(*_exp_top, panel_circuit_expanded(cb))
        case "exposure":
            if has_error(exp_f):
                panel = Panel("[red]Exposure factors unavailable[/]", border_style="red")
                return _expanded_layout(*_exp_top, panel)
            return _expanded_layout(*_exp_top, panel_exposure_expanded(exp_f))
        case "market":
            if has_error(mkt):
                return _expanded_layout(
                    *_exp_top,
                    Panel("[red]Market data unavailable[/]", border_style="red"),
                )
            return _expanded_layout(*_exp_top, panel_market_expanded(mkt, sentiment))
        case "positions":
            if has_error(pos):
                return _expanded_layout(
                    *_exp_top,
                    Panel("[red]Positions data unavailable[/]", border_style="red"),
                )
            _pos_items = pos if isinstance(pos, list) else (pos.get("items", []) if isinstance(pos, dict) else [])
            hint = Text.from_markup("[dim]press [/][bold cyan]p[/][dim] to return to dashboard[/]")
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
        case "signals":
            if has_error(sig) or has_error(scores):
                return _expanded_layout(
                    *_exp_top,
                    Panel("[red]Signals data unavailable[/]", border_style="red"),
                )
            return _expanded_layout(*_exp_top, panel_signals_expanded(sig, sig_eval, scores=scores))
        case "health":
            if has_error(run) or has_error(hlth):
                return _expanded_layout(
                    *_exp_top,
                    Panel("[red]Health data unavailable[/]", border_style="red"),
                )
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
        case "sectors":
            if has_error(pos) or has_error(port):
                return _expanded_layout(
                    *_exp_top,
                    Panel("[red]Sectors data unavailable[/]", border_style="red"),
                )
            return _expanded_layout(*_exp_top, panel_sectors_expanded(srank, pos, port, sec_rot, irank))
        case "trades":
            if has_error(rec):
                return _expanded_layout(
                    *_exp_top,
                    Panel("[red]Trade history unavailable[/]", border_style="red"),
                )
            return _expanded_layout(*_exp_top, panel_trades_expanded(rec))
        case "economic":
            if has_error(eco):
                return _expanded_layout(
                    *_exp_top,
                    Panel("[red]Economic data unavailable[/]", border_style="red"),
                )
            return _expanded_layout(*_exp_top, panel_economic_expanded(eco, econ_cal))
        case "portfolio":
            if has_error(port) or has_error(cfg):
                return _expanded_layout(
                    *_exp_top,
                    Panel("[red]Portfolio data unavailable[/]", border_style="red"),
                )
            return _expanded_layout(
                *_exp_top,
                panel_portfolio_perf_expanded(port, cfg, risk=risk, perf=perf, perf_anl=perf_anl, pos=pos),
            )
        case "errors":
            error_panel_exp = error_summary_panel_expanded(data)
            if error_panel_exp:
                return _expanded_layout(*_exp_top, error_panel_exp)

    return None


def _run_once_update_frame_and_mode(key: str, frame: int, view_mode: str) -> tuple[int, str]:
    """Update frame counter and view mode based on keypress."""
    if key in KEY_MAP:
        target = KEY_MAP[key]
        view_mode = "normal" if view_mode == target else target
    frame += 1
    if frame > 1_000_000:
        frame = 0
    return frame, view_mode


def _run_once_update_display(
    live: Live,
    done: threading.Event,
    state: _LoadState,
    frame: int,
    view_mode: str,
    recovery: RenderRecovery,
    render_wrapper: _RenderWrapper,
    data_source: str,
) -> None:
    """Update display during loading or render dashboard."""
    if not done.is_set():
        live.update(loading_layout(frame, data_source=data_source))
        return

    with render_wrapper._state_lock:
        render_wrapper.elapsed = state.elapsed
        render_wrapper.frame = frame
        render_wrapper.view_mode = view_mode
    try:
        layout, _recovery_status = recovery.render_with_recovery(state.result, render_wrapper)
        live.update(layout)
    except Exception as e:
        error_panel = _handle_render_error(e, recovery.get_recovery_status())
        try:
            live.update(error_panel)
        except Exception as panel_error:
            logger.error(f"Failed to render error panel: {type(panel_error).__name__}: {panel_error}")


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
        render_wrapper = _RenderWrapper(compact, data_source)
        with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
            try:
                while True:
                    key = _keypress()
                    if key == "q":
                        break
                    frame, view_mode = _run_once_update_frame_and_mode(key, frame, view_mode)
                    _run_once_update_display(
                        live,
                        done,
                        state,
                        frame,
                        view_mode,
                        recovery,
                        render_wrapper,
                        data_source,
                    )
                    time.sleep(0.125)
            except KeyboardInterrupt:
                pass
    finally:
        if bg_thread:
            done.set()
            bg_thread.join(timeout=60)
            if bg_thread.is_alive():
                logger.error(
                    "Background thread abandoned after 60s timeout (data load exceeded graceful shutdown window)"
                )


def _run_watch_process_render(
    current_result: Any,
    render_wrapper: _RenderWrapper,
    recovery: RenderRecovery,
    is_loading: bool,
    current_last_load: float,
    interval: int,
    current_elapsed: float,
    current_frame: int,
    view_mode: str,
) -> tuple[Exception | None, Layout | None, str | None, bool, bool]:
    """Process rendering state and determine reload status.

    Returns (render_error, render_layout, error_status, should_reload, should_retry).
    """
    render_error = None
    render_layout = None
    error_status = None
    should_reload = False
    should_retry_load = False

    if current_result is None:
        return (
            render_error,
            render_layout,
            error_status,
            should_reload,
            should_retry_load,
        )

    with render_wrapper._state_lock:
        render_wrapper.elapsed = current_elapsed
        render_wrapper.frame = current_frame
        render_wrapper.last_load_time = current_last_load
        render_wrapper.refreshing = is_loading
        render_wrapper.view_mode = view_mode

    try:
        layout, _recovery_status = recovery.render_with_recovery(current_result, render_wrapper)
        render_layout = layout
    except Exception as e:
        render_error = e
        error_status = recovery.get_recovery_status()

    should_reload = not is_loading and (time.monotonic() - current_last_load) >= interval
    try:
        should_retry_load = recovery.should_retry_data_load()
    except Exception as e:
        logger.error(f"Failed to check recovery retry status: {type(e).__name__}: {e}")

    return render_error, render_layout, error_status, should_reload, should_retry_load


def _run_watch_render_display(
    live: Live,
    current_result: Any,
    current_error: str | None,
    error_status: str | None,
    current_frame: int,
    render_error: Exception | None,
    render_layout: Layout | None,
    data_source: str,
) -> None:
    """Render the UI display for watch mode."""
    if current_result is None:
        if current_error:
            error_panel = _handle_render_error(RuntimeError(current_error), error_status)
            try:
                live.update(error_panel)
            except Exception as panel_error:
                logger.error(f"Failed to render error panel: {type(panel_error).__name__}: {panel_error}")
        else:
            live.update(loading_layout(current_frame, data_source=data_source))
    else:
        if render_error is None and render_layout is not None:
            live.update(render_layout)
        elif render_error is not None:
            error_panel = _handle_render_error(render_error, error_status)
            try:
                live.update(error_panel)
            except Exception as panel_error:
                logger.error(f"Failed to render error panel: {type(panel_error).__name__}: {panel_error}")


def _run_watch_main_loop(
    live: Live,
    state: _WatchState,
    state_lock: threading.Lock,
    render_wrapper: _RenderWrapper,
    recovery: RenderRecovery,
    interval: int,
    data_source: str,
    active_threads: list,
    active_threads_lock: threading.Lock,
    cleanup_dead_threads,
    reload,
    reload_thread,
) -> None:
    """Main event loop for watch mode."""
    view_mode = "normal"
    try:
        while True:
            key = _keypress()
            if key == "q":
                break
            if key in KEY_MAP:
                target = KEY_MAP[key]
                view_mode = "normal" if view_mode == target else target

            with state_lock:
                state.frame += 1
                if state.frame > 1_000_000:
                    state.frame = 0
                current_frame = state.frame
                current_result = state.result
                current_error = state.error
                is_loading = state.loading
                current_last_load = state.last_load
                current_elapsed = state.elapsed

            (
                render_error,
                render_layout,
                error_status,
                should_reload,
                should_retry_load,
            ) = _run_watch_process_render(
                current_result,
                render_wrapper,
                recovery,
                is_loading,
                current_last_load,
                interval,
                current_elapsed,
                current_frame,
                view_mode,
            )

            if current_error and not error_status:
                error_status = recovery.get_recovery_status()

            _run_watch_render_display(
                live,
                current_result,
                current_error,
                error_status,
                current_frame,
                render_error,
                render_layout,
                data_source,
            )

            if should_reload or should_retry_load:
                cleanup_dead_threads()
                reload_thread = threading.Thread(target=reload, daemon=False)
                reload_thread.start()
                with active_threads_lock:
                    active_threads.append(reload_thread)
            time.sleep(0.125)
    except KeyboardInterrupt:
        pass


def _run_watch_shutdown_threads(
    active_threads: list, active_threads_lock: threading.Lock, shutdown: threading.Event
) -> None:
    """Gracefully shutdown all active threads."""
    shutdown.set()
    with active_threads_lock:
        threads_to_join = active_threads[:]
    for thread in threads_to_join:
        if thread:
            thread.join(timeout=60)
            if thread.is_alive():
                logger.error(
                    "Thread abandoned after 60s timeout in watch mode (data load exceeded graceful shutdown window)"
                )


def run_watch(interval: int, compact: bool, data_source: str = "AWS") -> None:
    """Watch mode: auto-refresh data every `interval` seconds, mascot dances continuously."""
    state = _WatchState()
    state_lock = threading.Lock()
    active_threads: list = []
    active_threads_lock = threading.Lock()
    shutdown = threading.Event()

    def cleanup_dead_threads() -> None:
        """Remove finished threads from active_threads list to prevent unbounded growth."""
        with active_threads_lock:
            threads_to_remove = []
            for thread in active_threads:
                if not thread.is_alive():
                    threads_to_remove.append(thread)
            for thread in threads_to_remove:
                active_threads.remove(thread)

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
        with active_threads_lock:
            active_threads.append(reload_thread)

        recovery = RenderRecovery()
        render_wrapper = _RenderWrapper(compact, data_source)
        render_wrapper.watch_interval = interval
        with Live(console=CONSOLE, refresh_per_second=8, screen=True) as live:
            _run_watch_main_loop(
                live,
                state,
                state_lock,
                render_wrapper,
                recovery,
                interval,
                data_source,
                active_threads,
                active_threads_lock,
                cleanup_dead_threads,
                reload,
                reload_thread,
            )
    finally:
        _run_watch_shutdown_threads(active_threads, active_threads_lock, shutdown)


def _setup_local_api() -> str:
    """Setup local API mode and return data source."""
    local_url = "http://localhost:3001"
    if not _validate_api_url(local_url):
        logger.error(f"Invalid local API URL: {local_url}")
        sys.exit(1)
    set_api_url(local_url)
    return "LOCAL"


def _fetch_and_validate_aws_credentials() -> tuple[str, str, str]:
    """Fetch AWS credentials from Secrets Manager or Terraform. Exits on failure."""
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
            CONSOLE.print("[yellow]2. Dashboard will auto-fetch from Secrets Manager / Terraform[/]")
            CONSOLE.print("[dim]After GitHub Actions deploy completes, run setup-local-dev.ps1 to refresh[/]")
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

    return cast(tuple[str, str, str], (aws_url, pool_id, client_id))


def _configure_aws_and_auth(aws_url: str, pool_id: str, client_id: str) -> None:
    """Configure AWS API and Cognito authentication. Exits on failure."""
    set_api_url(aws_url)
    os.environ["DASHBOARD_API_URL"] = aws_url
    os.environ["COGNITO_USER_POOL_ID"] = pool_id
    os.environ["COGNITO_CLIENT_ID"] = client_id
    logger.info("Dashboard credentials loaded from Secrets Manager")

    try:
        auth = get_cognito_auth_instance(require_auth=True)
    except RuntimeError as e:
        try:
            CONSOLE.print("[bold red]ERROR:[/] Authentication required but Cognito credentials not found")
            CONSOLE.print("")
            CONSOLE.print("[bold cyan]Options:[/]")
            CONSOLE.print("[yellow]1. Set environment variables:[/]")
            CONSOLE.print("[cyan]   $env:COGNITO_USERNAME = 'your_username'[/]")
            CONSOLE.print("[cyan]   $env:COGNITO_PASSWORD = 'your_password'[/]")
            CONSOLE.print("")
            CONSOLE.print("[yellow]2. Or run setup (will prompt for credentials):[/]")
            CONSOLE.print("[cyan]   scripts/setup-local-dev.ps1[/]")
            CONSOLE.print("")
            CONSOLE.print("[yellow]3. Or save credentials to ~/.algo/cognito_credentials.json[/]")
        except Exception as print_err:
            logger.error(
                f"[AUTH] Authentication required but failed: {e}. "
                f"(Failed to display full message: {type(print_err).__name__})"
            )
        logger.error(f"[AUTH] Authentication required but failed: {e}")
        sys.exit(1)

    auth = cast(Any, auth)
    if auth.is_authenticated():
        set_cognito_auth(auth)
        save_tokens(auth)
    else:
        logger.warning("[AUTH] Running with limited permissions - Cognito not fully authenticated")
        set_cognito_auth(auth)


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
        data_source = _setup_local_api()
    else:
        aws_url, pool_id, client_id = _fetch_and_validate_aws_credentials()
        _configure_aws_and_auth(aws_url, pool_id, client_id)
        data_source = "AWS"

    if args.watch is not None:
        run_watch(args.watch, args.compact, data_source)
    else:
        run_once(args.compact, data_source)


if __name__ == "__main__":
    main()
