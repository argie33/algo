# Project

```bash
python start_dashboard_dev.py        # Local dev
python check_system_health.py        # Diagnose
```

**Data not available?** → Run health check, then `start_dashboard_dev.py`

**Rules:** Type-safe. No `.env`/`pdb`. Data integrity first. Always use `start_dashboard_dev.py` for local dev.

**Orchestrator testing:** `python scripts/run_local_orchestrator.py [--afternoon|--evening]`

**Stale data:** `python scripts/monitor_data_staleness.py` + `verify_eventbridge_scheduler.py --fix`
