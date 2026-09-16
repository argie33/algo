"""Regression test: eps_growth_trend_5y (loaders/helpers/vqg_growth.py) must use DILUTED EPS
(annual_income_statement.diluted_eps), not basic EPS (annual_income_statement.earnings_per_share
- what the pre-existing eps_growth_1y/3y/5y CAGR fields use).

Found 2026-09-16 (factor-purity /goal session, user: "we are using the wrong eps stuff though
arent we"): loaders/helpers/financial_statements_income_config.py maps
"earnings_per_share_basic" -> earnings_per_share and "earnings_per_share_diluted" -> diluted_eps
- two genuinely separate, both-maintained columns, not naming variants of the same figure.
MSCI's/Barra's real EPS-growth-trend formula (loaders/helpers/growth_trend.py) specifies diluted
EPS, the institutional-standard convention. This test constructs a fixture where basic and
diluted EPS diverge enough to produce different growth trends if the wrong column were used,
and asserts the diluted-EPS answer wins.
"""

from loaders.helpers.growth_trend import ols_growth_trend
from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_eps_growth_trend_5y_matches_diluted_eps_series_not_basic():
    # Basic EPS (5th column) grows slowly (no real dilution story); diluted EPS (9th column)
    # grows meaningfully faster - a deliberately exaggerated split so a wrong-column bug would
    # produce a visibly different, wrong number rather than a coincidentally-close one.
    income_rows = [
        (2026, 1_000_000_000.0, None, None, 5.10, 1_000_000_000, None, None, 6.00),
        (2025, 1_000_000_000.0, None, None, 5.05, 1_000_000_000, None, None, 5.00),
        (2024, 1_000_000_000.0, None, None, 5.00, 1_000_000_000, None, None, 4.00),
        (2023, 1_000_000_000.0, None, None, 4.95, 1_000_000_000, None, None, 3.00),
        (2022, 1_000_000_000.0, None, None, 4.90, 1_000_000_000, None, None, 2.00),
    ]
    loader = _make_loader()
    result = loader._compute_growth_metrics("TEST", income_rows)

    basic_eps_series = [(int(r[0]), float(r[4])) for r in income_rows]
    diluted_eps_series = [(int(r[0]), float(r[8])) for r in income_rows]
    expected_from_diluted = ols_growth_trend(diluted_eps_series)
    expected_from_basic = ols_growth_trend(basic_eps_series)

    assert expected_from_diluted != expected_from_basic, "fixture must make the two columns diverge"
    assert result["eps_growth_trend_5y"] == expected_from_diluted, (
        f"eps_growth_trend_5y used the wrong EPS column - got {result['eps_growth_trend_5y']}, "
        f"expected the diluted-EPS trend {expected_from_diluted} (basic-EPS trend would have "
        f"been {expected_from_basic})"
    )
