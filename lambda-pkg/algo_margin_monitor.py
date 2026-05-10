#!/usr/bin/env python3
"""Real-time margin monitoring for Alpaca account.

Tracks margin usage and enforces entry gates to prevent over-leverage.
Default thresholds: Alert at 70%, Block entries at 80%.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class MarginMonitor:
    """Monitor and enforce margin limits via Alpaca API."""

    def __init__(self, config=None):
        self.config = config or {}
        self.alert_threshold = float(self.config.get('margin_alert_pct', 70.0))
        self.halt_threshold = float(self.config.get('margin_halt_pct', 80.0))
        self.alpaca_api_key = os.getenv("ALPACA_API_KEY", "")
        self.alpaca_secret = os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = "https://paper-api.alpaca.markets" if os.getenv("ALPACA_PAPER") == "true" else "https://api.alpaca.markets"

    def get_margin_usage(self) -> Dict[str, float]:
        """Fetch live account margin info from Alpaca."""
        try:
            import requests

            headers = {
                "APCA-API-KEY-ID": self.alpaca_api_key,
                "APCA-API-SECRET-KEY": self.alpaca_secret,
            }
            resp = requests.get(f"{self.base_url}/v2/account", headers=headers, timeout=5)

            if resp.status_code != 200:
                logger.warning(f"Alpaca API error: {resp.status_code}")
                return None

            data = resp.json()
            equity = float(data.get("equity", 0))
            cash = float(data.get("cash", 0))
            multiplied_positions = float(data.get("multiplied_positions", equity))

            margin_used = multiplied_positions - equity if multiplied_positions > equity else 0
            margin_pct = (margin_used / equity * 100) if equity > 0 else 0

            return {
                'equity': equity,
                'cash': cash,
                'margin_used': margin_used,
                'margin_usage_pct': margin_pct,
                'buying_power': float(data.get("buying_power", cash)),
                'account_health': 'healthy' if margin_pct < self.alert_threshold else 'warning',
            }
        except Exception as e:
            logger.warning(f"Failed to fetch margin info: {e}")
            return None

    def can_enter_new_position(self) -> Tuple[bool, str]:
        """Check if margin is low enough to enter new position."""
        try:
            margin_info = self.get_margin_usage()

            if not margin_info:
                return True, "Margin check skipped (API unavailable)"

            margin_pct = margin_info['margin_usage_pct']

            if margin_pct > self.halt_threshold:
                return False, f"Margin {margin_pct:.1f}% > halt threshold {self.halt_threshold}%"

            return True, f"Margin OK: {margin_pct:.1f}%"
        except Exception as e:
            logger.warning(f"Margin entry gate error: {e}")
            return True, "Entry gate check skipped"

    def check_margin_health(self) -> Tuple[bool, str]:
        """Check if margin is healthy. Returns (is_healthy, reason)."""
        try:
            margin_info = self.get_margin_usage()

            if not margin_info:
                return True, "Margin check skipped (API unavailable)"

            margin_pct = margin_info['margin_usage_pct']

            if margin_pct > self.halt_threshold:
                return False, f"CRITICAL: Margin {margin_pct:.1f}% > halt {self.halt_threshold}%"
            elif margin_pct > self.alert_threshold:
                return True, f"WARNING: Margin {margin_pct:.1f}% approaching limit ({self.alert_threshold}%)"

            return True, f"Healthy: {margin_pct:.1f}% margin"
        except Exception as e:
            logger.warning(f"Margin health check error: {e}")
            return True, "Check skipped"


if __name__ == "__main__":
    mm = MarginMonitor()
    info = mm.get_margin_usage()
    if info:
        print(f"Margin: {info['margin_usage_pct']:.1f}%")
        can_enter, msg = mm.can_enter_new_position()
        print(f"Can enter: {can_enter} ({msg})")
    else:
        print("Alpaca API unavailable")
