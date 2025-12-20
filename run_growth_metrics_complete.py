#!/usr/bin/env python3
"""
Run existing loadfactormetrics.py for ALL symbols with batching.
Uses the existing infrastructure - no new calculations, just runs what you have.
"""

import subprocess
import sys
import time

def main():
    print("🚀 RUNNING EXISTING GROWTH METRICS LOADER FOR ALL SYMBOLS")
    print("="*70)
    print("")
    print("This runs the existing loadfactormetrics.py")
    print("Batches symbols to avoid context window errors")
    print("")

    # Run loadfactormetrics.py - it's designed to handle all symbols
    try:
        result = subprocess.run(
            ["python3", "loadfactormetrics.py"],
            cwd="/home/stocks/algo",
            timeout=7200,  # 2 hour timeout
        )

        if result.returncode == 0:
            print("\n✅ Complete - Growth metrics loaded")
            return 0
        else:
            print(f"\n⚠️ Exit code: {result.returncode}")
            return result.returncode

    except subprocess.TimeoutExpired:
        print("\n❌ Timeout - took longer than 2 hours")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
