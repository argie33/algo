#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard

Usage (LOCAL DEVELOPMENT - RECOMMENDED):
  python dashboard/dashboard.py --local               # use local API (localhost:3001)
  python dashboard/dashboard.py --local -w 30         # watch mode, auto-refresh every 30s

Usage (AWS/Production - requires Cognito):
  python dashboard/dashboard.py                       # requires COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID env vars
  python dashboard/dashboard.py -w 60                 # watch mode, refresh every 60s

IMPORTANT: For local development, ALWAYS use --local flag!
Without it, dashboard tries to connect to AWS Lambda which requires Cognito authentication.

Modes:
  Local: Run local dev server first (python api-pkg/dev_server.py), then use --local flag
  AWS (default): Set DASHBOARD_API_URL, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID env vars
"""

import os
import sys

# Windows console encoding (cp1252) cannot display UTF-8. Redirect before any Rich console creation.
if sys.platform.startswith('win'):
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass  # If redirection fails, continue anyway - better than crashing

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_dashboard_dir = os.path.dirname(os.path.abspath(__file__))
if _dashboard_dir in sys.path:
    sys.path.remove(_dashboard_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import argparse
import socket
import time
from typing import Any

_args_temp = argparse.ArgumentParser(add_help=False)
_args_temp.add_argument('--local', action='store_true')
_temp_args, _ = _args_temp.parse_known_args()


def _is_dev_server_available() -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('localhost', 3001))
        sock.close()
        return result == 0
    except Exception:
        return False


# CRITICAL: Only auto-detect localhost if AWS config is NOT explicitly set.
# AWS configuration is never overridden by localhost auto-detection.
_has_aws_config = os.environ.get('DASHBOARD_API_URL') is not None
if _temp_args.local or (_is_dev_server_available() and not _has_aws_config):
    os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
    os.environ['LOCAL_MODE'] = 'true'
    print("[DASHBOARD] LOCAL MODE - using localhost:3001", flush=True)

try:
    import msvcrt

    def _keypress() -> str:
        """Non-blocking keypress detection on Windows."""
        try:
            if msvcrt.kbhit():
                try:
                    ch = msvcrt.getch()
                    return str(ch.decode("utf-8", errors="ignore").lower())
                except Exception:
                    return ""
            return ""
        except Exception:
            return ""

except ImportError:
    import select
    import termios
    import tty

    def _keypress() -> str:
        if select.select([sys.stdin], [], [], 0)[0]:
            try:
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)  # type: ignore[attr-defined]
                try:
                    tty.setraw(fd)  # type: ignore[attr-defined]
                    ch = sys.stdin.read(1).lower()
                    return ch if ch else ""
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)  # type: ignore[attr-defined]
            except (OSError, AttributeError, ValueError) as e:
                raise RuntimeError(
                    f"Dashboard terminal input failed: {type(e).__name__}: {e}. "
                    "Terminal mode is broken — cannot read user input."
                ) from e
        return ""


from rich.layout import Layout
from rich.live import Live

from dashboard.api_data_layer import set_api_url, set_cognito_auth, validate_api_config
from dashboard.core import DashboardContext
from dashboard.dashboard_orchestrator import DashboardOrchestrator
from dashboard.error_boundary import error_summary_panel
from dashboard.error_recovery import RenderRecovery
from dashboard.fetchers import load_all
from dashboard.panels import loading_layout, mascot_compact
from dashboard.renderers import (
    check_auth_lost,
    render_dashboard_body,
    render_error_panel,
    render_expanded_view,
    render_header_components,
)
from dashboard.utilities import MASCOT_W, logger
from dashboard.watch import ReloadManager, WatchModeController, WatchState


def get_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Algo Ops Terminal Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python dashboard/dashboard.py --local              # Connect to local dev_server
  python dashboard/dashboard.py --local -w 30        # Auto-refresh every 30s
  python dashboard/dashboard.py                      # Connect to AWS Lambda (requires AWS creds)
        """,
    )
    parser.add_argument('--local', action='store_true', help='Use local API (localhost:3001)')
    parser.add_argument('-w', '--watch', type=int, default=0, metavar='SECONDS', help='Auto-refresh interval (seconds, 0=manual only)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    return parser.parse_args()


def setup_logging(debug: bool = False) -> None:
    """Configure logging for dashboard."""
    import logging
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )


def validate_config(args: argparse.Namespace) -> None:
    is_local = bool(args.local or os.environ.get('LOCAL_MODE'))
    try:
        validate_api_config(allow_localhost=is_local)
    except Exception as e:
        print(f"ERROR: API configuration invalid: {e}")
        print("\nFor local development, use: python dashboard/dashboard.py --local")
        sys.exit(1)


def configure_cognito(args: argparse.Namespace) -> None:
    """Authenticate against Cognito for AWS mode. No-op for local mode."""
    if args.local or os.environ.get('LOCAL_MODE'):
        return
    from dashboard.cognito_auth import get_cognito_auth as _get_cognito_auth_instance

    auth = _get_cognito_auth_instance()
    if isinstance(auth, dict):
        raise RuntimeError(f"Cognito authentication unavailable: {auth.get('reason', 'unknown')}")
    set_cognito_auth(auth)


def render_dashboard(
    data: dict[str, Any],
    *,
    compact: bool,
    elapsed: float,
    frame: int,
    watch_interval: int | None,
    last_load_time: float | None,
    refreshing: bool,
    view_mode: str,
    data_source: str,
) -> Layout:
    """Assemble the full dashboard layout from fetched data.

    Imported by dashboard.renderers.base/modes (NormalRenderer/ModeRenderer), which
    call back into this module — keep this function's name and signature stable.
    """
    ctx = DashboardContext(data)

    auth_lost_panel = check_auth_lost()
    if auth_lost_panel is not None:
        layout = Layout()
        layout.update(auth_lost_panel)
        return layout

    hdr_panel, exp_panel = render_header_components(
        ctx, elapsed, watch_interval, last_load_time, refreshing, data_source
    )
    mascot_panel = mascot_compact(data, frame)

    if view_mode != "normal":
        expanded = render_expanded_view(view_mode, ctx, hdr_panel, exp_panel, mascot_panel, compact)
        if expanded is not None:
            return expanded

    outer = Layout()
    outer.split_column(
        Layout(name="top", size=3),
        Layout(name="r1", size=9),
        Layout(name="r2", size=11),
        Layout(name="r3", size=11),
        Layout(name="pos", ratio=1),
        Layout(name="footer", size=4),
    )
    outer["top"].split_row(
        Layout(hdr_panel, name="hdr", ratio=3),
        Layout(exp_panel, name="exp", ratio=2),
        Layout(mascot_panel, name="mascot", size=MASCOT_W),
    )
    render_dashboard_body(outer, ctx, compact)

    err_panel = error_summary_panel(data)
    if err_panel is not None:
        outer["footer"].update(err_panel)
    else:
        outer["footer"].visible = False

    return outer


def main() -> None:  # noqa: C901
    """Main dashboard entry point."""
    try:
        args = get_cli_args()
        setup_logging(args.debug)
        validate_config(args)
        configure_cognito(args)

        if args.local:
            os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
            os.environ['LOCAL_MODE'] = 'true'
        set_api_url(os.environ.get('DASHBOARD_API_URL', 'http://localhost:3001'))

        data_source = "LOCAL" if os.environ.get('LOCAL_MODE') else "AWS"
        orchestrator = DashboardOrchestrator(compact=False, data_source=data_source)
        orchestrator.set_state(watch_interval=args.watch if args.watch > 0 else None)

        watch_ctl = WatchModeController()
        watch_state = WatchState()
        recovery = RenderRecovery()
        reload_mgr = ReloadManager(load_all)

        def on_reload_complete(payload: dict[str, Any]) -> None:
            if payload["error"]:
                watch_state.error = payload["error"]
            else:
                watch_state.result = payload["result"]
                watch_state.error = None
            watch_state.elapsed = payload["elapsed"]
            watch_state.loading = False
            watch_state.last_load = time.monotonic()
            orchestrator.set_state(last_load_time=watch_state.last_load, refreshing=False)

        reload_mgr.spawn_reload(on_reload_complete)

        try:
            with Live(Layout(), refresh_per_second=4, screen=True) as live:
                while True:
                    key = _keypress()
                    if key in ('q', 'exit'):
                        break
                    if key:
                        watch_ctl.handle_keypress(key)
                        orchestrator.set_state(view_mode=watch_ctl.get_view_mode())

                    snap = orchestrator.get_snapshot()

                    if (
                        snap["watch_interval"]
                        and not watch_state.loading
                        and watch_ctl.should_reload(watch_state.last_load, snap["watch_interval"], watch_state.loading)
                    ):
                        watch_state.loading = True
                        orchestrator.set_state(refreshing=True)
                        reload_mgr.spawn_reload(on_reload_complete)

                    orchestrator.update_frame()
                    snap = orchestrator.get_snapshot()

                    result = watch_state.result
                    if result is None and watch_state.error is None:
                        live.update(loading_layout(snap["frame"], snap["data_source"]))
                    elif result is None and watch_state.error is not None:
                        live.update(render_error_panel(RuntimeError(watch_state.error)))
                    else:
                        layout, _status = recovery.render_with_recovery(
                            result,
                            lambda d: render_dashboard(
                                d,
                                compact=snap["compact"],
                                elapsed=watch_state.elapsed,
                                frame=snap["frame"],
                                watch_interval=snap["watch_interval"],
                                last_load_time=snap["last_load_time"],
                                refreshing=snap["refreshing"],
                                view_mode=snap["view_mode"],
                                data_source=snap["data_source"],
                            ),
                        )
                        live.update(layout)

                    time.sleep(0.1 if snap["watch_interval"] else 0.25)
        finally:
            reload_mgr.shutdown_all(timeout=5)

    except KeyboardInterrupt:
        print("\n[DASHBOARD] Closed by user", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"[DASHBOARD] FATAL: {e}", file=sys.stderr, flush=True)
        if "--debug" in sys.argv:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
