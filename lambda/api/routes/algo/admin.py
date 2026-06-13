from .algo_original import _check_admin_access, _trigger_data_patrol
def handle_trigger_patrol(): return _trigger_data_patrol()
def check_admin_access(jwt_claims): return _check_admin_access(jwt_claims)
