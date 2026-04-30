#!/usr/bin/env python3
"""
Load State Manager - Tracks last load dates for incremental loading

Maintains state file tracking when each loader last successfully ran.
Enables incremental loads: only load data since last_load_date.

Usage:
    from load_state import LoadState

    state = LoadState()
    last_load = state.get_last_load('price_daily')  # Returns datetime or None
    state.update_load('price_daily', start_date, end_date)
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path


class LoadState:
    """Manages load state for incremental data loading"""

    STATE_FILE = Path(__file__).parent / ".load_state.json"

    def __init__(self):
        self.state = self._load_state()

    def _load_state(self):
        """Load state from file, create if missing"""
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load state file: {e}")
                return {}
        return {}

    def _save_state(self):
        """Save state to file"""
        try:
            with open(self.STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Could not save state file: {e}")

    def get_last_load(self, loader_name: str):
        """Get last successful load date for a loader

        Args:
            loader_name: e.g. 'price_daily', 'analyst_sentiment', 'stock_scores'

        Returns:
            datetime object or None if never loaded
        """
        if loader_name not in self.state:
            return None

        last_load = self.state[loader_name].get('last_load_date')
        if not last_load:
            return None

        try:
            return datetime.fromisoformat(last_load)
        except Exception:
            return None

    def get_all_loads(self):
        """Get all loader states"""
        return self.state.copy()

    def update_load(self, loader_name: str, start_date=None, end_date=None,
                    row_count=0, status='success', error=None):
        """Update load state for a loader

        Args:
            loader_name: e.g. 'price_daily'
            start_date: When data was loaded from (datetime or string)
            end_date: When data was loaded to (datetime or string)
            row_count: Rows loaded
            status: 'success' or 'error'
            error: Error message if failed
        """
        if loader_name not in self.state:
            self.state[loader_name] = {}

        # Convert to ISO string if datetime
        if isinstance(start_date, datetime):
            start_date = start_date.isoformat()
        if isinstance(end_date, datetime):
            end_date = end_date.isoformat()

        self.state[loader_name] = {
            'last_load_date': end_date or datetime.now().isoformat(),
            'last_load_start': start_date,
            'rows_loaded': row_count,
            'status': status,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }

        self._save_state()

    def is_incremental_load(self):
        """Check if this should be an incremental load

        Returns: True if all loaders have been loaded before (incremental mode)
                 False if any loader never loaded (full reload mode)
        """
        # List of critical loaders for incremental check
        critical_loaders = [
            'price_daily',
            'analyst_sentiment',
            'stock_scores'
        ]

        for loader in critical_loaders:
            if loader not in self.state or not self.state[loader].get('last_load_date'):
                return False

        return True

    def get_incremental_date_range(self):
        """Get date range for incremental load

        Returns: (start_date, end_date) for incremental load
        """
        # Get oldest last_load_date from all loaders (most conservative approach)
        dates = []

        for loader, info in self.state.items():
            if isinstance(info, dict) and info.get('last_load_date'):
                try:
                    dt = datetime.fromisoformat(info['last_load_date'])
                    dates.append(dt)
                except Exception:
                    pass

        if not dates:
            # First incremental load: start from 7 days ago
            start = datetime.now() - timedelta(days=7)
        else:
            # Start from oldest last_load_date
            start = min(dates)

        end = datetime.now()

        return start, end

    def reset_loader(self, loader_name: str):
        """Reset state for a specific loader (forces full reload next time)"""
        if loader_name in self.state:
            del self.state[loader_name]
            self._save_state()

    def reset_all(self):
        """Reset all state (forces full reload)"""
        self.state = {}
        self._save_state()

    def print_summary(self):
        """Print current state summary"""
        print("\n" + "="*80)
        print("LOAD STATE SUMMARY")
        print("="*80)

        if not self.state:
            print("No load history found (first run)")
            return

        for loader, info in sorted(self.state.items()):
            if isinstance(info, dict):
                last_load = info.get('last_load_date', 'Never')
                status = info.get('status', 'unknown')
                rows = info.get('rows_loaded', 0)

                print(f"\n{loader}:")
                print(f"  Last load: {last_load}")
                print(f"  Rows: {rows}")
                print(f"  Status: {status}")

                if info.get('error'):
                    print(f"  Error: {info['error']}")

        print("\n" + "="*80)
        print(f"Incremental load ready: {self.is_incremental_load()}")
        print("="*80 + "\n")


# Convenience functions
_state_instance = None

def get_state():
    """Get global LoadState instance"""
    global _state_instance
    if _state_instance is None:
        _state_instance = LoadState()
    return _state_instance

def update_state(loader_name: str, start_date=None, end_date=None,
                 row_count=0, status='success', error=None):
    """Update load state"""
    get_state().update_load(loader_name, start_date, end_date, row_count, status, error)

def get_last_load(loader_name: str):
    """Get last load date for loader"""
    return get_state().get_last_load(loader_name)


if __name__ == "__main__":
    state = LoadState()
    state.print_summary()
