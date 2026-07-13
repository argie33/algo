"""Environment variable validation - ensures all required variables are set before execution.

PHASE 3 FIX: Validate ALL required environment variables at startup.
Prevents silent failures from missing credentials or configuration.
"""

import os
from typing import Any

from algo.config.error_codes import ErrorCode, OrchestrationError


class EnvironmentValidator:

    # Required environment variables for orchestrator execution
    REQUIRED_VARS = {
        # Database connection (host, port, name, user required; password loaded from Secrets Manager or env)
        "DB_HOST": "PostgreSQL host",
        "DB_PORT": "PostgreSQL port",
        "DB_NAME": "PostgreSQL database name",
        "DB_USER": "PostgreSQL username",
        # DB_PASSWORD is NOT required here - loaded from:
        #   1. AWS Lambda: DB_SECRET_ARN (Secrets Manager JSON blob with password field)
        #   2. Local dev: environment variable DB_PASSWORD
        # Credential validation happens at first database connection, not at startup
        # AWS (always required)
        "AWS_REGION": "AWS region for Lambda/RDS/Secrets Manager",
        # Execution Mode (optional if EXECUTION_MODE set, defaults to paper if neither set)
        # NOTE: Alpaca credentials (APCA_API_KEY_ID, APCA_API_SECRET_KEY) only required for live trading
        # For paper trading, credentials can be loaded from AWS Secrets Manager at runtime
    }

    # Optional variables with sensible defaults
    OPTIONAL_WITH_DEFAULTS = {
        "ORCHESTRATOR_EXECUTION_MODE": ("paper", "Execution mode: paper or live (default: paper)"),
        "ORCHESTRATOR_DRY_RUN": ("false", "Dry run mode: true or false (default: false)"),
    }

    # Alternative variable names (accepted if primary not set)
    # Allows flexibility across different deployment contexts
    ALTERNATIVE_VARS = {
        "AWS_ACCOUNT_ID": (
            "ORCHESTRATOR_EXECUTION_MODE",
            "AWS account ID (optional, can be fetched from STS if not set)",
        ),
        "EXECUTION_MODE": ("ORCHESTRATOR_EXECUTION_MODE", "Legacy name for execution mode"),
    }

    # Optional but recommended variables
    RECOMMENDED_VARS = {
        "LOG_LEVEL": "DEBUG, INFO, WARNING, ERROR (default: INFO)",
        "BACKFILL_DAYS": "Number of days to backfill data on loader runs",
        "SKIP_ORCHESTRATOR_LOCK": "true to skip distributed lock (for testing only)",
        "MAX_RUNTIME_SECONDS": "Maximum orchestrator runtime in seconds",
        "DATA_FRESHNESS_THRESHOLD_MINUTES": "Max age for data to be considered fresh",
    }

    @classmethod
    def validate_required(cls) -> tuple[bool, list[str]]:
        """Validate all required environment variables are set.

        Returns:
            (is_valid, missing_vars): True if all set, False + list of missing vars
        """
        missing = []

        for var_name, description in cls.REQUIRED_VARS.items():
            value = os.getenv(var_name)
            if not value or value.strip() == "":
                # Check for alternative names if primary not set
                if var_name in cls.ALTERNATIVE_VARS:
                    alt_name, _alt_desc = cls.ALTERNATIVE_VARS[var_name]
                    alt_value = os.getenv(alt_name)
                    if alt_value and alt_value.strip() != "":
                        # Alternative found, continue without error
                        continue
                missing.append(f"{var_name}: {description}")

        # Check optional variables with defaults - no missing errors if defaults exist
        for var_name, (default_val, _description) in cls.OPTIONAL_WITH_DEFAULTS.items():
            value = os.getenv(var_name)
            if not value or value.strip() == "":
                # Check for alternative names if primary not set
                if var_name in cls.ALTERNATIVE_VARS:
                    alt_name, _alt_desc = cls.ALTERNATIVE_VARS[var_name]
                    alt_value = os.getenv(alt_name)
                    if alt_value and alt_value.strip() != "":
                        # Alternative found, use it instead of default
                        os.environ[var_name] = alt_value
                        continue
                # Use default
                os.environ[var_name] = default_val

        return len(missing) == 0, missing

    @classmethod
    def validate_optional(cls) -> dict[str, str]:
        """Check optional variables and log which ones are missing.

        Returns:
            dict of missing optional vars
        """
        missing = {}

        for var_name, description in cls.RECOMMENDED_VARS.items():
            value = os.getenv(var_name)
            if not value or value.strip() == "":
                missing[var_name] = description

        return missing

    @classmethod
    def get_status(cls) -> dict[str, Any]:
        """Get environment validation status.

        Returns:
            dict with required_ok, missing_required, missing_optional
        """
        required_ok, missing_required = cls.validate_required()
        missing_optional = cls.validate_optional()

        return {
            "required_ok": required_ok,
            "missing_required": missing_required,
            "missing_recommended": list(missing_optional.keys()),
        }

    @classmethod
    def require_valid_or_halt(cls, context: str = "orchestrator") -> None:
        """Require valid environment or raise OrchestrationError with helpful message.

        Args:
            context: Where this validation is happening (for error messages)

        Raises:
            OrchestrationError if any required variable is missing
        """
        is_valid, missing = cls.validate_required()

        if not is_valid:
            error_msg = f"\n[{context.upper()}] ENVIRONMENT CONFIGURATION ERROR:\n"
            error_msg += "The following required environment variables are not set:\n\n"

            for var_desc in missing:
                error_msg += f"  - {var_desc}\n"

            error_msg += "\nHow to fix:\n"
            error_msg += "1. Local testing: export these variables in your shell\n"
            error_msg += "2. AWS Lambda: set in environment variables or AWS Secrets Manager\n"
            error_msg += "3. Docker: pass via -e flag or .env file\n"
            error_msg += "4. GitHub Actions: add to secrets or workflow env\n"
            error_msg += "\nNOTE: Alpaca credentials can be loaded from AWS Secrets Manager at runtime;\n"
            error_msg += "they only need to be in the environment for paper trading if not using Secrets Manager.\n"

            raise OrchestrationError(
                ErrorCode.ENV_VAR_MISSING, error_msg, {"context": context, "missing_vars": missing}
            )

        # Log optional missing variables
        missing_optional = cls.validate_optional()
        if missing_optional:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"[{context.upper()}] Optional environment variables not set: "
                f"{list(missing_optional.keys())}. Using defaults."
            )
