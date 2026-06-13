from .algo_original import _get_algo_portfolio, _get_algo_metrics
def handle_metrics(cur): return _get_algo_metrics(cur)
def handle_portfolio(cur): return _get_algo_portfolio(cur)
