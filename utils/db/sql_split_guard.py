"""SQL fragment for excluding split-corrupted price ratios from aggregate calculations.

price_daily stores raw/unadjusted prices (see utils/external/alpaca_market_data.py -
ALPACA_DATA_ADJUSTMENT defaults to "raw"). Any query that computes a percent return
directly from two price_daily.close values (e.g. "(close_today - close_N_days_ago) /
close_N_days_ago") will read a stock split within that window as a fake ~50%+ return -
one split stock can materially skew a sector/industry average built from many stocks'
individual returns.

loaders/technical_indicators.py::detect_and_adjust_splits() fixes this for the technical
indicator pipeline by back-adjusting each symbol's full price series in memory before
computing RSI/MACD/etc. That approach doesn't fit here: these are ad-hoc two-point SQL
return calculations across many symbols in a single query, not a per-symbol pandas
DataFrame pass. Instead, exclude a stock's return from the aggregate for that specific
window if the two closes' ratio matches a clean split ratio - the same criterion
tick_validator.py and detect_and_adjust_splits() both use to recognize a split, so a
price move is excluded here if and only if it would also be recognized (not rejected as
bad data) at ingestion. This doesn't recover the correct return for that stock - it just
stops the wrong one from silently distorting the average.
"""

# Kept in sync with utils/data/tick_validator.py's TickValidator._SPLIT_RATIOS /
# _SPLIT_RATIO_TOLERANCE and loaders/technical_indicators.py's _match_split_ratio.
_SPLIT_RATIOS_SQL_ARRAY = "ARRAY[1.25,1.5,2,3,4,5,6,7,8,10,15,20,25,50,100]::numeric[]"
_SPLIT_RATIO_TOLERANCE = 0.02

# tick_validator.py's _check_sequence only ever calls _is_likely_split (i.e. only ever
# considers a ratio as a candidate split) once the day-over-day gap already exceeds 30% -
# below that, a move is accepted as ordinary price action without any split judgment at
# all. The smallest entry in _SPLIT_RATIOS (1.25, a 5-for-4 split = a 25% gap) is BELOW
# that 30% floor, so a real ~25% single-day move for a volatile penny/micro-cap stock
# (routine, not a split) would fall inside the 1.25 candidate's tolerance band. Applying
# ratio-matching unconditionally - without this floor - would misclassify ordinary
# penny-stock volatility as a split and wrongly exclude real returns from the aggregate,
# the opposite failure mode from what this guard exists to prevent. Requiring the ratio to
# clear 30% first (matching tick_validator's own gate) keeps this guard exactly as
# conservative as the ingestion-time check it's meant to mirror.
_MIN_GAP_RATIO = 1.30


def split_guard_sql(close_a: str, close_b: str) -> str:
    """Return a SQL boolean expression: TRUE unless close_a/close_b looks like a stock split.

    Args:
        close_a: SQL expression for one close price (e.g. "p1.close")
        close_b: SQL expression for the other close price (e.g. "pnow.close")

    Usage: append as an extra AND condition alongside existing NULL/zero guards in a CASE
    or WHERE clause, e.g.:
        CASE WHEN p1.close IS NOT NULL AND p1.close != 0 AND {split_guard_sql("p1.close", "pnow.close")}
             THEN (pnow.close - p1.close) / p1.close * 100 END
    """
    magnitude = f"GREATEST({close_a}/{close_b}, {close_b}/{close_a})"
    return (
        f"NOT ("
        f"{magnitude} > {_MIN_GAP_RATIO} AND EXISTS ("
        f"SELECT 1 FROM unnest({_SPLIT_RATIOS_SQL_ARRAY}) AS split_ratio "
        f"WHERE ABS({magnitude} - split_ratio) / split_ratio <= {_SPLIT_RATIO_TOLERANCE}"
        f")"
        f")"
    )
