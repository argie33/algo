"""Regression test: AlpacaBrokerAdapter.fetch_closed_orders() must read alpaca_paper_trading
from a real AlgoConfig instance, not just a plain dict.

fetch_closed_orders()'s credentials-missing fallback branch previously gated on
`isinstance(self.config, dict)` then `"alpaca_paper_trading" not in self.config` - the exact
same bug class already fixed in alpaca_sync_manager.py's __init__ (see its comment): isinstance
is always False for the real AlgoConfig instance used in production, so this raised
"[CONFIG_ERROR] alpaca_paper_trading configuration missing" unconditionally regardless of
whether alpaca_paper_trading was actually configured. Confirmed live 2026-07-27: a fresh
AlgoConfig() has alpaca_paper_trading=True (loaded from the DB), yet
isinstance(AlgoConfig(), dict) is False, so the old code raised the false error the moment
this branch was reached (missing/empty Alpaca credentials). Fixed to use .get(), which works
for both a plain dict and AlgoConfig.
"""

from unittest.mock import MagicMock

from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter


class _FakeAlgoConfig:
    """Mimics AlgoConfig: NOT a dict, only supports .get()."""

    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


def _adapter_with_missing_credentials(config) -> AlpacaBrokerAdapter:
    adapter = AlpacaBrokerAdapter.__new__(AlpacaBrokerAdapter)
    adapter.config = config
    adapter.alpaca_sync = MagicMock(alpaca_key="", alpaca_secret="")
    return adapter


def test_real_algoconfig_with_paper_trading_true_does_not_raise_config_missing():
    adapter = _adapter_with_missing_credentials(_FakeAlgoConfig({"alpaca_paper_trading": True}))

    try:
        adapter.fetch_closed_orders()
        raised_msg = None
    except ValueError as e:
        raised_msg = str(e)

    assert raised_msg is not None
    assert "configuration missing" not in raised_msg
    assert "PAPER_TRADING" in raised_msg


def test_real_algoconfig_with_paper_trading_false_raises_credentials_required():
    adapter = _adapter_with_missing_credentials(_FakeAlgoConfig({"alpaca_paper_trading": False}))

    try:
        adapter.fetch_closed_orders()
        raised_msg = None
    except ValueError as e:
        raised_msg = str(e)

    assert raised_msg is not None
    assert "credentials" in raised_msg.lower()
    assert "configuration missing" not in raised_msg


def test_missing_alpaca_paper_trading_key_still_raises_config_missing():
    adapter = _adapter_with_missing_credentials(_FakeAlgoConfig({}))

    try:
        adapter.fetch_closed_orders()
        raised_msg = None
    except ValueError as e:
        raised_msg = str(e)

    assert raised_msg is not None
    assert "alpaca_paper_trading key missing" in raised_msg
