from .algo_original import _get_notifications
def handle_notifications(cur, params=None, jwt_claims=None): return _get_notifications(cur, params, jwt_claims)
