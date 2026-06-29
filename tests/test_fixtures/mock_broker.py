#!/usr/bin/env python3
"""Mock broker adapter for dry-run testing and unit tests."""

from tests.test_utilities import DryRunBrokerAdapter

# Alias for backward compatibility
MockBrokerAdapter = DryRunBrokerAdapter
