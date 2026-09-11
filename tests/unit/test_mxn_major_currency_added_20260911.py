"""Regression test for the 2026-09-11 fix (goal session: SEC/XBRL missing-data count under
300): MXN (Mexican Peso) added to MAJOR_CURRENCIES, reversing an earlier exclusion that
predated the 2026-09-04 BRL policy reversal (28-29% year-over-year volatility accepted) and
the COP/CLP additions (19-20%/19.8% accepted) - MXN's own 22.4% high-water mark was never
revisited against that looser bar, the same stale-rejection bug class already fixed once for
SEK on 2026-09-06.

Live-confirmed via ASR (Grupo Aeroportuario del Sureste, CIK 0001123452) and PAC/TBBB/TV: real
ifrs-full:Revenue/ProfitLoss/Assets tagged exclusively under unit="MXN", no USD-tagged
alternative - the blanket non-USD currency guard was zeroing their entire
quality_metrics/growth_metrics/value_metrics/sec_valuations rows.
"""

from utils.external.fx_rates import MAJOR_CURRENCIES


def test_mxn_is_a_major_currency() -> None:
    assert "MXN" in MAJOR_CURRENCIES
