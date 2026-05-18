#!/usr/bin/env python3
"""Config validator - startup checks for required configuration."""

import logging
logger = logging.getLogger(__name__)


def validate_at_startup():
    """Validate required configuration at startup."""
    from config.credential_validator import assert_credentials
    try:
        assert_credentials(mode='warn')
        logger.debug("Startup validation: OK")
    except Exception as e:
        logger.warning(f"Startup validation warning: {e}")
