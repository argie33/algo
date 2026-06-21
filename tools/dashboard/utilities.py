"""Shared utilities for dashboard modules."""

import hashlib
import json
import logging
import os
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from rich.console import Console

# ── globals ───────────────────────────────────────────────────────────────────
ET = ZoneInfo("America/New_York")
CONSOLE = Console(force_terminal=True, legacy_windows=False, highlight=False)

# Thread-safe caches
_data_status_lock = threading.Lock()
_data_status_cache: dict[str, Any] = {}

_sector_cache_lock = threading.Lock()
_sector_agg_cache: dict[str, Any] = {}

# Colors for dashboard rendering
G = "bright_green"
R = "bright_red"
Y = "yellow"
CY = "cyan"
DIM = "dim"
MG = "magenta"
WH = "white"

TIER_COLOR = {
    "confirmed_uptrend": "bright_green",
    "healthy_uptrend": "green",
    "pressure": "yellow",
    "caution": "orange1",
    "correction": "bright_red",
}

TIER_SHORT = {
    "confirmed_uptrend": "CONFIRMED UP",
    "healthy_uptrend": "HEALTHY UP",
    "pressure": "PRESSURE",
    "caution": "CAUTION",
    "correction": "CORRECTION",
}

SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"

# Mascot animation sequence
LOAD_SEQ = [0, 1, 4, 3]

MASCOT_COLORS = [
    "bright_green",
    "cyan",
    "magenta",
    "yellow",
    "bright_yellow",
    "white",
    "yellow",
    "bright_red",
]

MASCOT_FRAMES = [
    "zzZ",
    "zzz",
    "...",
    "Zzz",
]

MASCOT_W = 3

PHASE_NAMES = {
    "phase_0": "Pre-flight",
    "phase_1": "Data",
    "phase_2": "Circuits",
    "phase_3": "Positions",
    "phase_3a": "Reconcile",
    "phase_3b": "Exposure",
    "phase_4": "Exits",
    "phase_5": "Signals",
    "phase_6": "Entries",
    "phase_7": "Wrap-up",
}

# Configure logging for stability monitoring
_log_dir = os.path.expanduser("~/.algo/logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "dashboard.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def get_data_status_cache():
    """Get thread-safe access to data status cache."""
    return _data_status_cache, _data_status_lock


def get_sector_cache():
    """Get thread-safe access to sector aggregation cache."""
    return _sector_agg_cache, _sector_cache_lock
