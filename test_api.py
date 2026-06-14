#!/usr/bin/env python
import sys

print("[TEST] Testing backend API functionality...")

try:
    from algo.trading import TradeExecutor
    from algo.reporting import AlertManager, LivePerformance
    from algo.infrastructure.config import get_config
    from utils.db import DatabaseContext

    print("[OK] API core modules import successfully")

    config = get_config()
    print("[OK] Config loaded for API")

    executor = TradeExecutor(config)
    alerts = AlertManager()
    perf = LivePerformance(config)
    print("[OK] API classes instantiated")

    with DatabaseContext('read') as cur:
        cur.execute("SELECT 1")
        print("[OK] Database connection verified")

    print("\n[SUCCESS] Backend API ready to serve requests")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
