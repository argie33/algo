#!/usr/bin/env python3
"""Orchestration module - core execution engine for the trading algorithm.

Exports:
- Orchestrator: Main entry point for executing the full trading pipeline
- RegimeManager: Manages market regime detection and adaptive parameters
"""

from .orchestrator import Orchestrator
from .regime_manager import RegimeManager

__all__ = [
    "Orchestrator",
    "RegimeManager",
]
