"""
Configuration Validator

Validates all required configuration at startup.
Catches config errors early (fail-fast pattern).
Provides clear error messages for missing/invalid values.
"""

import os
import sys
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validate application configuration (environment variables only)."""

    # Required environment variables and their validation rules
    REQUIRED_CONFIG = {
        # Database
        'DB_HOST': {'type': str, 'default': DEFAULT_DB_HOST},
        'DB_PORT': {'type': int, 'default': 5432, 'min': 1, 'max': 65535},
        'DB_USER': {'type': str},  # Required
        'DB_PASSWORD': {'type': str},  # Required (from env or AWS Secrets Manager)
        'DB_NAME': {'type': str, 'default': DEFAULT_DB_NAME},

        # Alpaca Trading
        'ALPACA_API_KEY': {'type': str},  # Required for trading
        'ALPACA_SECRET_KEY': {'type': str},  # Required for trading
        'ALPACA_BASE_URL': {'type': str, 'default': 'https://paper-api.alpaca.markets'},

        # API/Web
        'API_PORT': {'type': int, 'default': 5000, 'min': 1, 'max': 65535},
        'API_HOST': {'type': str, 'default': '0.0.0.0'},

        # Logging
        'LOG_LEVEL': {'type': str, 'default': 'INFO', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']},

        # Trading Parameters
        'INITIAL_CAPITAL': {'type': float, 'default': 100000.0, 'min': 1000},
        'MAX_POSITIONS': {'type': int, 'default': 12, 'min': 1, 'max': 100},
        'MAX_POSITION_SIZE': {'type': float, 'default': 25000.0, 'min': 100},

        # Feature Flags
        'DEV_MODE': {'type': str, 'default': 'false', 'allowed': ['true', 'false']},
        'DRY_RUN': {'type': str, 'default': 'false', 'allowed': ['true', 'false']},
    }

    def __init__(self, env_file: Optional[str] = None):
        """Initialize validator.

        Args:
            env_file: Deprecated, ignored. All credentials come from environment variables.
        """
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.config: Dict[str, Any] = {}

        if env_file:
            logger.warning("env_file parameter is deprecated and ignored. Use environment variables only.")

    def validate(self) -> bool:
        """Validate all configuration.

        Returns:
            True if valid, False if errors found
        """
        self.errors = []
        self.warnings = []

        for key, rules in self.REQUIRED_CONFIG.items():
            value = os.getenv(key)

            # Check if required
            if 'default' not in rules and value is None:
                self.errors.append(f"Missing required: {key}")
                continue

            # Use default if not set
            if value is None:
                value = rules['default']

            # Validate type
            expected_type = rules['type']
            try:
                if expected_type == int:
                    value = int(value)
                elif expected_type == float:
                    value = float(value)
                elif expected_type == bool:
                    value = value.lower() in ('true', '1', 'yes')
                # str doesn't need conversion
            except ValueError:
                self.errors.append(f"Invalid type for {key}: expected {expected_type.__name__}, got {value}")
                continue

            # Validate constraints
            if 'min' in rules and value < rules['min']:
                self.errors.append(f"{key} must be >= {rules['min']}, got {value}")

            if 'max' in rules and value > rules['max']:
                self.errors.append(f"{key} must be <= {rules['max']}, got {value}")

            if 'allowed' in rules:
                # For LOG_LEVEL and similar uppercase enums, compare case-insensitively
                # For true/false booleans, compare as-is (lowercase)
                check_value = str(value).upper() if key in ['LOG_LEVEL'] else str(value).lower()
                allowed_values = [v.upper() if key in ['LOG_LEVEL'] else v.lower() for v in rules['allowed']]
                if check_value not in allowed_values:
                    self.errors.append(f"{key} must be one of {rules['allowed']}, got {value}")

            self.config[key] = value

        # Log results
        if self.errors:
            logger.error(f"Configuration validation FAILED with {len(self.errors)} error(s):")
            for error in self.errors:
                logger.error(f"  [ERROR] {error}")
            return False

        if self.warnings:
            logger.warning(f"Configuration warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                logger.warning(f"  [WARNING] {warning}")

        logger.info(f"[OK] Configuration valid ({len(self.config)} settings loaded)")
        return True

    def get(self, key: str, default=None):
        """Get configuration value.

        Args:
            key: Configuration key
            default: Default if not found

        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)

    def summary(self) -> str:
        """Get configuration summary (sanitized).

        Returns:
            Human-readable config summary
        """
        lines = ["Configuration Summary:"]
        for key in sorted(self.REQUIRED_CONFIG.keys()):
            value = self.config.get(key, 'NOT SET')
            # Sanitize sensitive values
            if any(s in key for s in ['PASSWORD', 'SECRET', 'KEY']):
                value = '***REDACTED***'
            lines.append(f"  {key:25} = {value}")
        return '\n'.join(lines)


def validate_at_startup(env_file: Optional[str] = None) -> Dict[str, Any]:
    """Validate configuration at application startup.

    Prints errors and exits if validation fails.

    Args:
        env_file: Path to .env file (optional)

    Returns:
        Validated configuration dict

    Raises:
        SystemExit: If validation fails
    """
    validator = ConfigValidator(env_file)

    if not validator.validate():
        logger.critical("\n" + "="*70)
        logger.critical("CONFIGURATION VALIDATION FAILED")
        logger.critical("="*70)
        logger.critical("\nFix the above errors and restart.\n")
        sys.exit(1)

    logger.info("\n" + validator.summary())
    return validator.config


