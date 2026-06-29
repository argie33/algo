#!/usr/bin/env python3
"""Mock broker adapter for dry-run testing and unit tests."""

from algo.infrastructure.dry_run_adapters import DryRunBrokerAdapter

# Alias for backward compatibility
MockBrokerAdapter = DryRunBrokerAdapter
