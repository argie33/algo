#!/usr/bin/env python3
"""Regression test: the insider transaction velocity loader must wait for the
Form 3/4/5 background download to finish before giving up on a symbol.

Previously wait_for_download was hardcoded False under the assumption a "later
run" would find the data cached - but CachedForm345Aggregator only caches
in-memory for the life of one process (no disk persistence exists despite the
module docstring's caching claim), so every scheduled run started a fresh
2-5 min download and any symbol processed before it finished got
data_unavailable="Form345_download_in_progress" permanently. Confirmed live:
insider_transaction_velocity had never once stored a real row across this
loader's whole life.
"""

from unittest.mock import MagicMock

from loaders.load_insider_transaction_velocity import InsiderTransactionVelocityLoader


def test_fetch_incremental_waits_for_form345_download() -> None:
    loader = InsiderTransactionVelocityLoader.__new__(InsiderTransactionVelocityLoader)
    loader._aggregator = MagicMock()
    metrics = MagicMock()
    metrics.data_unavailable = False
    metrics.buy_transactions_30d = 2
    metrics.sell_transactions_30d = 1
    metrics.buy_transactions_90d = 5
    metrics.sell_transactions_90d = 3
    metrics.total_buy_shares_30d = 100
    metrics.total_sell_shares_30d = 50
    metrics.total_buy_shares_90d = 500
    metrics.total_sell_shares_90d = 300
    loader._aggregator.get_velocity_metrics.return_value = metrics

    loader.fetch_incremental("AAPL", since=None)

    _args, kwargs = loader._aggregator.get_velocity_metrics.call_args
    assert kwargs.get("wait_for_download") is True
