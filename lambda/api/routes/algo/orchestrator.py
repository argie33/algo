from .algo_original import _get_orchestrator_execution_recent
def handle_execution_recent(cur, days=7, limit=50): return _get_orchestrator_execution_recent(cur, days, limit)
