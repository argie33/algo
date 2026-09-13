"""Real-world-magnitude ceiling checks for core flow/balance-sheet fields, added 2026-09-13
(goal session: quarterly-revenue-identity backlog, wired into the permanent DataPatrol suite
rather than left as a one-off hand-run scan).

Live-confirmed this exact session: MKZR (REIT-exclusive-concept scale mismatch, revenue
tagged 1,000,000x too large), INVE (NetIncomeLoss tagged 1,000,000x too large vs. its own
ProfitLoss sibling), and SKM/KT/TSM/IX (stale pre-FX-conversion legacy rows) all produced
figures no real company has ever reported - a value beyond these ceilings is definitionally a
data-integrity problem, not a real business figure, regardless of currency or filer size.
Ceilings are deliberately generous (well above the largest real filer on record - e.g.
Walmart's ~$680B revenue, Berkshire's ~$1.1T total assets) so this only ever catches a
genuine order-of-magnitude corruption, never a real mega-cap's real figures.
"""

from typing import TYPE_CHECKING, Any

_REVENUE_CEILING = 1_000_000_000_000.0  # no real filer has ever reported >$1T revenue
_NET_INCOME_CEILING = 500_000_000_000.0  # no real filer has ever reported >$500B net income
_GROSS_PROFIT_CEILING = 1_000_000_000_000.0
_OPERATING_INCOME_CEILING = 500_000_000_000.0
_TOTAL_ASSETS_CEILING = 20_000_000_000_000.0  # low tens of trillions - largest real balance sheets (banks)
_TOTAL_LIABILITIES_CEILING = 20_000_000_000_000.0
_STOCKHOLDERS_EQUITY_CEILING = 5_000_000_000_000.0
_OPERATING_CASH_FLOW_CEILING = 500_000_000_000.0


class TieOutImplausibleMagnitudeMixin:
    if TYPE_CHECKING:
        # Provided by TieOutSharedMixin; declared here only for the type checker (this mixin
        # is never instantiated on its own, always combined with TieOutSharedMixin on
        # TieOutChecker).
        def _check_implausible_magnitude_field(
            self, cur: Any, *, table: str, field: str, check_name: str, quarterly: bool, ceiling: float
        ) -> None: ...

    def check_revenue_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="annual_income_statement",
            field="revenue",
            check_name="revenue_implausible_magnitude",
            quarterly=False,
            ceiling=_REVENUE_CEILING,
        )

    def check_quarterly_revenue_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="quarterly_income_statement",
            field="revenue",
            check_name="quarterly_revenue_implausible_magnitude",
            quarterly=True,
            ceiling=_REVENUE_CEILING,
        )

    def check_net_income_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="annual_income_statement",
            field="net_income",
            check_name="net_income_implausible_magnitude",
            quarterly=False,
            ceiling=_NET_INCOME_CEILING,
        )

    def check_quarterly_net_income_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="quarterly_income_statement",
            field="net_income",
            check_name="quarterly_net_income_implausible_magnitude",
            quarterly=True,
            ceiling=_NET_INCOME_CEILING,
        )

    def check_gross_profit_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="annual_income_statement",
            field="gross_profit",
            check_name="gross_profit_implausible_magnitude",
            quarterly=False,
            ceiling=_GROSS_PROFIT_CEILING,
        )

    def check_operating_income_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="annual_income_statement",
            field="operating_income",
            check_name="operating_income_implausible_magnitude",
            quarterly=False,
            ceiling=_OPERATING_INCOME_CEILING,
        )

    def check_total_assets_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="annual_balance_sheet",
            field="total_assets",
            check_name="total_assets_implausible_magnitude",
            quarterly=False,
            ceiling=_TOTAL_ASSETS_CEILING,
        )

    def check_quarterly_total_assets_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="quarterly_balance_sheet",
            field="total_assets",
            check_name="quarterly_total_assets_implausible_magnitude",
            quarterly=True,
            ceiling=_TOTAL_ASSETS_CEILING,
        )

    def check_total_liabilities_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="annual_balance_sheet",
            field="total_liabilities",
            check_name="total_liabilities_implausible_magnitude",
            quarterly=False,
            ceiling=_TOTAL_LIABILITIES_CEILING,
        )

    def check_stockholders_equity_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="annual_balance_sheet",
            field="stockholders_equity",
            check_name="stockholders_equity_implausible_magnitude",
            quarterly=False,
            ceiling=_STOCKHOLDERS_EQUITY_CEILING,
        )

    def check_operating_cash_flow_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="annual_cash_flow",
            field="operating_cash_flow",
            check_name="operating_cash_flow_implausible_magnitude",
            quarterly=False,
            ceiling=_OPERATING_CASH_FLOW_CEILING,
        )

    def check_quarterly_operating_cash_flow_implausible_magnitude(self, cur: Any) -> None:
        self._check_implausible_magnitude_field(
            cur,
            table="quarterly_cash_flow",
            field="operating_cash_flow",
            check_name="quarterly_operating_cash_flow_implausible_magnitude",
            quarterly=True,
            ceiling=_OPERATING_CASH_FLOW_CEILING,
        )
