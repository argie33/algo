# Project

```bash
python start_dashboard_dev.py                          # Local dev
python scripts/run_local_orchestrator.py               # Test orchestrator
```

**Data not available?** → Check staleness, then run orchestrator tests

**Rules:** Type-safe. No `.env`/`pdb`. Data integrity first. Always use `start_dashboard_dev.py` for local dev.

**Data staleness:** `python scripts/monitor_data_staleness.py` + `python scripts/verify_eventbridge_scheduler.py --fix`

**Orchestrator testing:** `python scripts/run_local_orchestrator.py [--afternoon|--evening]`
