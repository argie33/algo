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

# CRITICAL FIX: Windows console encoding (cp1252) cannot display UTF-8.
# Redirect stdout/stderr to use UTF-8 before any Rich console creation.
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
import threading
import time
from typing import Any
from urllib.parse import urlparse

# AUTO-DETECT LOCAL MODE: Check if localhost:3001 is available; if so, use it by default
# This eliminates the need for users to remember --local flag
# Also support explicit --local flag for backward compatibility
import socket
import os as _os_auto

def _is_dev_server_available() -> bool:
    """Check if dev server is running on localhost:3001."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('localhost', 3001))
        sock.close()
        return result == 0
    except Exception:
        return False

# Parse --local flag early before any dashboard/API modules are imported
_args_temp = argparse.ArgumentParser(add_help=False)
_args_temp.add_argument('--local', action='store_true', help='Use local API (localhost:3001)')
_temp_args, _ = _args_temp.parse_known_args()

# CRITICAL FIX: Only auto-detect localhost if AWS config is NOT explicitly set
# This ensures AWS configuration is never overridden by localhost auto-detection.
# Respects explicit AWS setup while still providing convenience for dev-only scenarios.
_has_aws_config = _os_auto.environ.get('DASHBOARD_API_URL') is not None

# Enable local mode if:
# 1. User explicitly passes --local flag, OR
# 2. Dev server is running on localhost:3001 AND no AWS config is explicitly set
if _temp_args.local or (_is_dev_server_available() and not _has_aws_config):
    _os_auto.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
    _os_auto.environ['LOCAL_MODE'] = 'true'
    print("[DASHBOARD_STARTUP] LOCAL MODE DETECTED/ENABLED - Using localhost:3001", flush=True)

try:
    import msvcrt

    def _keypress() -> str:
        """Non-blocking keypress detection on Windows.

        CRITICAL FIX: msvcrt operations can hang on some Windows configs.
        Check kbhit() only, skip getch() to avoid blocking.
        """
        try:
            result = msvcrt.kbhit()
            if result:
                try:
                    ch = msvcrt.getch()
                    return str(ch.decode("utf-8", errors="ignore").lower())
                except Exception:
                    return ""  # Ignore encoding/read errors
            return ""
        except Exception:
            return ""  # Ignore any msvcrt errors

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

# Support both: direct execution (python dashboard/dashboard.py) and module execution (python -m dashboard)
try:
    # Try relative imports first (module execution)
    from .api_data_layer import set_api_url, set_cognito_auth, validate_api_config
    from .cognito_auth import get_cognito_auth as get_cognito_auth_instance
    from .cognito_auth import save_tokens
    from .core import DashboardContext, ViewMode
    from .error_boundary import error_summary_panel
    from .error_recovery import RenderRecovery
    from .fetchers import load_all
    from .panel_registry import get_panel_registry as _get_panel_registry
    from .panels import loading_layout, mascot_compact
    from .renderers import (
        check_auth_lost,
        render_dashboard_body,
        render_error_panel,
        render_expanded_view,
        render_header_components,
    )
    from .utilities import CONSOLE, MASCOT_W, logger
    from .watch import LoadState, WatchModeController, WatchState
except ImportError:
    # Fall back to absolute imports (direct execution)
    from dashboard.api_data_layer import set_api_url, set_cognito_auth, validate_api_config
    from dashboard.cognito_auth import get_cognito_auth as get_cognito_auth_instance
    from dashboard.cognito_auth import save_tokens
    from dashboard.core import DashboardContext, ViewMode
    from dashboard.error_boundary import error_summary_panel
    from dashboard.error_recovery import RenderRecovery
    from dashboard.fetchers import load_all
    from dashboard.panel_registry import get_panel_registry as _get_panel_registry
    from dashboard.panels import loading_layout, mascot_compact
    from dashboard.renderers import (
        check_auth_lost,
        render_dashboard_body,
        render_error_panel,
        render_expanded_view,
        render_header_components,
    )
    from dashboard.utilities import CONSOLE, MASCOT_W, logger
    from dashboard.watch import LoadState, WatchModeController, WatchState


def get_cli_args() -> argparse.Namespace:
    """Parse command line arguments."""
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


def get_cognito_auth() -> tuple[str, str]:
    """Get Cognito JWT token for AWS API access.

    Returns tuple of (api_url, jwt_token).
    Tries multiple methods:
    1. Check if token already in environment
    2. Try Secrets Manager (if AWS credentials available)
    3. Prompt user for username/password
    """
    api_url = os.environ.get('DASHBOARD_API_URL', '')
    jwt_token = os.environ.get('DASHBOARD_JWT_TOKEN', '')

    if jwt_token:
        return api_url, jwt_token

    # Try Secrets Manager
    try:
        import boto3
        sm_client = boto3.client('secretsmanager')
        secret = sm_client.get_secret_value(SecretId='algo/cognito-creds')
        import json
        creds = json.loads(secret['SecretString'])
        cognito_instance = get_cognito_auth_instance()
        jwt_token = cognito_instance.get_token(creds.get('username'), creds.get('password'))
        save_tokens(jwt_token, None)
        return api_url, jwt_token
    except Exception:
        pass

    # Interactive prompt
    cognito_instance = get_cognito_auth_instance()
    return api_url, cognito_instance.interactive_login()


def setup_logging(debug: bool = False) -> None:
    """Configure logging for dashboard."""
    import logging
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )


def validate_config(args: argparse.Namespace) -> None:
    """Validate dashboard configuration before starting."""
    if args.local:
        # Local mode: no validation needed, will auto-detect dev_server
        pass
    else:
        # AWS mode: validate Cognito config
        try:
            validate_api_config()
        except Exception as e:
            print(f"ERROR: API configuration invalid: {e}")
            print("\nFor local development, use: python dashboard/dashboard.py --local")
            sys.exit(1)


def reset_circuit_breaker() -> None:
    """Reset circuit breaker on dashboard startup to prevent stale failures from blocking new sessions."""
    try:
        from utils.db.context import DatabaseContext
        with DatabaseContext('write') as cur:
            cur.execute('TRUNCATE TABLE circuit_breaker_status')
        logger.info('[STARTUP] Circuit breaker reset on dashboard startup')
    except Exception as e:
        logger.warning(f'[STARTUP] Failed to reset circuit breaker: {e}')


def main() -> None:
    """Main dashboard entry point."""
    try:
        # Reset circuit breaker to prevent stale failures
        reset_circuit_breaker()

        # Parse arguments
        args = get_cli_args()
        setup_logging(args.debug)

        # Validate configuration
        validate_config(args)

        # Get API credentials
        api_url, jwt_token = get_cognito_auth()

        # Set API configuration
        set_api_url(api_url)
        set_cognito_auth(jwt_token)

        # Create dashboard context
        ctx = DashboardContext(
            mode=ViewMode.LOCAL if args.local or args.watch > 0 else ViewMode.AWS,
            watch_interval=args.watch if args.watch > 0 else None,
        )

        # Create panel registry
        panel_registry = _get_panel_registry()

        # Create watch mode controller for auto-refresh
        watch_controller = WatchModeController(
            watch_interval=ctx.watch_interval,
            is_watch_mode=bool(ctx.watch_interval),
        )

        # Create recovery system
        recovery = RenderRecovery()

        # Main event loop
        with Live(layout := Layout(), refresh_per_second=4, screen=True) as live:
            load_state = LoadState()
            watch_state = WatchState()

            while True:
                try:
                    # Check for user input
                    key = _keypress()
                    if key in ('q', 'exit'):
                        break

                    # Load data from API
                    if watch_state.should_update(watch_controller):
                        try:
                            watch_state.mark_updating()
                            all_data = load_all(ctx)
                            load_state.success(all_data)
                            watch_state.mark_complete()
                        except Exception as load_error:
                            load_state.error(load_error)
                            recovery.handle_render_error(layout, load_error)
                            watch_state.mark_error()
                            time.sleep(1)
                            continue

                    # Check for auth loss
                    if check_auth_lost(load_state.last_data):
                        CONSOLE.print("[red]ERROR: Authentication lost. Please restart dashboard.[/red]")
                        break

                    # Render dashboard
                    try:
                        # Build layout
                        if load_state.is_loading():
                            layout.update(loading_layout(load_state.load_time))
                        elif load_state.has_error():
                            layout.update(render_error_panel(load_state.error))
                        else:
                            # Render header
                            header_components = render_header_components(load_state.last_data, ctx, load_state.load_time)

                            # Render body panels
                            body = render_dashboard_body(load_state.last_data, panel_registry, ctx)

                            # Add mascot and error summary
                            layout.split_column(
                                (header_components, {'size': 3}),
                                body,
                                (error_summary_panel(load_state.last_data), {'size': 4}),
                            )

                        recovery.mark_success(layout)

                    except Exception as render_error:
                        recovery.handle_render_error(layout, render_error)

                    # Sleep before next iteration
                    if ctx.watch_interval:
                        time.sleep(0.1)
                    else:
                        time.sleep(1)

                except KeyboardInterrupt:
                    CONSOLE.print("\n[yellow]Dashboard closed by user[/yellow]")
                    break
                except Exception as e:
                    recovery.handle_render_error(layout, e)
                    time.sleep(1)

    except Exception as e:
        print(f"FATAL: Dashboard failed to start: {e}", file=sys.stderr)
        if "--debug" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
