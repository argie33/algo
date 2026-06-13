from .algo_original import _get_algo_status, _get_algo_trades, _get_algo_positions
def handle_status(cur): return _get_algo_status(cur)
def handle_trades(cur, limit=200, user_id=None): return _get_algo_trades(cur, limit, user_id)
def handle_positions(cur, user_id=None): return _get_algo_positions(cur, user_id)
