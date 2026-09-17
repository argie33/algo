"""SCE$L (the only active '$'-suffix preferred-share symbol) had no working Alpaca price
path at all: Alpaca 400s "invalid symbol" on the raw '$' form and drops it from the whole
batch, and equity yfinance-fallback was removed 2026-09-15, so a dropped symbol used to get
zero data from any source. Alpaca's real form is '.PR' + series letter (e.g. "SCE.PRL"),
live-confirmed via Alpaca's own /v2/assets?search= endpoint - not the same as yfinance's
'-P' + letter form.
"""

from utils.external.alpaca_market_data import _to_alpaca_symbol


def test_dollar_suffix_translates_to_alpaca_dot_pr_form():
    assert _to_alpaca_symbol("SCE$L") == "SCE.PRL"
    assert _to_alpaca_symbol("MET$E") == "MET.PRE"


def test_non_preferred_symbols_are_unchanged():
    assert _to_alpaca_symbol("AAPL") == "AAPL"
    assert _to_alpaca_symbol("BRK.B") == "BRK.B"  # already matches Alpaca's own convention
