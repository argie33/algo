"""Load environment variables from .env.local for local development.

This ensures local development credentials are available without
requiring users to manually source the .env.local file or set
environment variables manually.

CRITICAL: Must be imported BEFORE any boto3/AWS calls.
"""

import os
from pathlib import Path


def load_env_local() -> None:
    """Load .env.local file into environment variables.

    Supports both line-by-line loading (if python-dotenv not available)
    and dotenv library loading (if available).

    Safely handles:
    - Comments (#)
    - Empty lines
    - Values with spaces
    - Missing .env.local (no-op)
    """

    env_local_path = Path(__file__).parent.parent / ".env.local"

    if not env_local_path.exists():
        return

    # FIXED 2026-08-21 (goal session - Alpaca 401 root-cause dig): override=False used to mean
    # a stale credential already sitting in the OS process environment silently permanently
    # wins over .env.local's real, current value, with load_env_local() (and this function's
    # own callers - see credential_manager.py's get_alpaca_credentials() Step 3) having no way
    # to tell "intentional live override" from "leftover cruft" apart. Live-confirmed root
    # cause of today's real Alpaca 401s (NOT AWS Secrets Manager - _is_aws is False locally so
    # that tier is never reached, and NOT the already-fixed algo_config DB placeholder either):
    # a dead APCA_API_KEY_ID/APCA_API_SECRET_KEY pair (confirmed 401 against Alpaca's paper,
    # live, AND market-data endpoints - not a units/scope mismatch, genuinely revoked/invalid)
    # was set as a persistent Windows USER-level environment variable, invisible to this repo
    # or .env.local, silently shadowing the real, working .env.local key on every local
    # process's Step 3 env-var check before it could ever reach the (already-hardened) Step 4
    # DB fallback. override=True is safe here specifically because this whole function no-ops
    # via the exists() check above the moment .env.local isn't present - i.e. in any real
    # deployed environment (AWS Lambda/ECS), .env.local doesn't ship, so this change has zero
    # effect there; it only ever changes behavior on a local dev machine, which is exactly
    # where "the checked-in file should always be authoritative over whatever cruft happens to
    # be sitting in this OS user's environment" is the correct default.
    # Try using dotenv library first (most robust)
    try:
        from dotenv import load_dotenv

        load_dotenv(env_local_path, override=True)
        return
    except ImportError:
        pass

    # Fallback: manual parsing (handles most cases)
    try:
        with open(env_local_path) as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Parse KEY=VALUE
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # override=True to match the dotenv-library path above - see this function's
                # 2026-08-21 fix comment for why .env.local must always win locally.
                if key:
                    os.environ[key] = value

    except PermissionError:
        import warnings

        warnings.warn(
            f"[ENV_LOAD] Permission denied reading .env.local at {env_local_path}. "
            "Local development credentials may not be available. "
            "Check file permissions and ensure .env.local is readable.",
            RuntimeWarning,
            stacklevel=2,
        )
    except FileNotFoundError:
        pass  # Already checked for existence above, this shouldn't happen
    except Exception as e:
        import warnings

        warnings.warn(
            f"[ENV_LOAD] Failed to parse .env.local: {type(e).__name__}: {e}. "
            "Local development credentials may not be available. "
            "Check .env.local syntax and file integrity.",
            RuntimeWarning,
            stacklevel=2,
        )


# Load immediately on import
load_env_local()
