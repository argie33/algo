"""TieOutChecker mixin, extracted from tie_out.py (file-size ratchet split, pure
extraction - no behavior change). Methods moved verbatim; mixed into TieOutChecker
via multiple inheritance in tie_out.py - every `self.` call here (self.results,
self.config, and any shared private helper from TieOutSharedMixin) resolves
normally through the instance regardless of which mixin file defines it.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..base import CheckResult
from ..config import ERROR, WARN
from .tie_out_shared import (
    _ACCOUNTS_RECEIVABLE_TOLERANCE_PCT,
    _CURRENT_VS_TOTAL_TOLERANCE_PCT,
    _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT,
    _INVENTORY_TOLERANCE_PCT,
    _LONG_TERM_DEBT_TOLERANCE_PCT,
    _MAX_REPORTED_PER_CHECK,
    _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT,
    _PPE_NET_TOLERANCE_PCT,
    _SHORT_TERM_DEBT_TOLERANCE_PCT,
)

logger = logging.getLogger(__name__)


class TieOutBoundsAnnual2Quarterly1Mixin:
    if TYPE_CHECKING:
        results: list[CheckResult]

        def log(
            self,
            check_name: str,
            severity: str,
            target: str,
            message: str,
            details: dict[str, Any] | None = None,
        ) -> CheckResult: ...

    def check_short_term_debt_le_current_liabilities(self, cur: Any) -> None:
        """short_term_debt <= current_liabilities (both from annual_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Same subset/category structural inequality as
        long_term_debt_le_total_liabilities above, applied to the current-liability side -
        short_term_debt is one liability line item, never the whole current-liability side.
        See _SHORT_TERM_DEBT_TOLERANCE_PCT's own comment for the live-feasibility numbers
        (64/2,012 annual).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.current_liabilities, b.short_term_debt
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_liabilities IS NOT NULL
                  AND b.short_term_debt IS NOT NULL
                  AND b.current_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_liabilities, short_term_debt = (
                    float(row["current_liabilities"]),
                    float(row["short_term_debt"]),
                )
                residual = short_term_debt - current_liabilities
                tolerance = abs(current_liabilities) * _SHORT_TERM_DEBT_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "current_liabilities": current_liabilities,
                            "short_term_debt": short_term_debt,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "short_term_debt_le_current_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail short_term_debt <= current_liabilities "
                    f"beyond {_SHORT_TERM_DEBT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] short_term_debt_le_current_liabilities failed: {e}", exc_info=True)
            self.log(
                "short_term_debt_le_current_liabilities",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_operating_lease_liability_le_total_liabilities(self, cur: Any) -> None:
        """operating_lease_liability <= total_liabilities (both from annual_balance_sheet,
        same row).

        ADDED 2026-09-07 (Round 3). Same subset/category structural inequality as
        long_term_debt_le_total_liabilities above - operating_lease_liability is one
        liability line item, never the whole liability side. See
        _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT's own comment for the live-feasibility
        numbers (7/4,471).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_liabilities, b.operating_lease_liability
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.operating_lease_liability IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, operating_lease_liability = (
                    float(row["total_liabilities"]),
                    float(row["operating_lease_liability"]),
                )
                residual = operating_lease_liability - total_liabilities
                tolerance = abs(total_liabilities) * _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_liabilities": total_liabilities,
                            "operating_lease_liability": operating_lease_liability,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "operating_lease_liability_le_total_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail operating_lease_liability <= "
                    f"total_liabilities beyond {_OPERATING_LEASE_LIABILITY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] operating_lease_liability_le_total_liabilities failed: {e}", exc_info=True)
            self.log(
                "operating_lease_liability_le_total_liabilities",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_finance_lease_liability_le_total_liabilities(self, cur: Any) -> None:
        """finance_lease_liability <= total_liabilities (both from annual_balance_sheet,
        same row).

        ADDED 2026-09-07 (Round 3). Same subset/category structural inequality as
        operating_lease_liability_le_total_liabilities above. See
        _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT's own comment for the live-feasibility
        numbers (1/1,663).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.total_liabilities, b.finance_lease_liability
                FROM annual_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.finance_lease_liability IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, finance_lease_liability = (
                    float(row["total_liabilities"]),
                    float(row["finance_lease_liability"]),
                )
                residual = finance_lease_liability - total_liabilities
                tolerance = abs(total_liabilities) * _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "total_liabilities": total_liabilities,
                            "finance_lease_liability": finance_lease_liability,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "finance_lease_liability_le_total_liabilities",
                    WARN,
                    "annual_balance_sheet",
                    f"{len(flagged)} symbol(s) fail finance_lease_liability <= "
                    f"total_liabilities beyond {_FINANCE_LEASE_LIABILITY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] finance_lease_liability_le_total_liabilities failed: {e}", exc_info=True)
            self.log(
                "finance_lease_liability_le_total_liabilities",
                ERROR,
                "annual_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_inventory_le_current_assets(self, cur: Any) -> None:
        """inventory <= current_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_inventory_le_current_assets -
        reuses the annual _INVENTORY_TOLERANCE_PCT unchanged (live-verified 2/2,800).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.current_assets, b.inventory
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_assets IS NOT NULL
                  AND b.inventory IS NOT NULL
                  AND b.current_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_assets, inventory = (
                    float(row["current_assets"]),
                    float(row["inventory"]),
                )
                residual = inventory - current_assets
                tolerance = abs(current_assets) * _INVENTORY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "current_assets": current_assets,
                            "inventory": inventory,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_inventory_le_current_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail inventory <= current_assets "
                    f"beyond {_INVENTORY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_inventory_le_current_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_inventory_le_current_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_accounts_receivable_le_current_assets(self, cur: Any) -> None:
        """accounts_receivable <= current_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_accounts_receivable_le_current_assets - reuses the annual
        _ACCOUNTS_RECEIVABLE_TOLERANCE_PCT unchanged (live-verified 5/3,786).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.current_assets, b.accounts_receivable
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_assets IS NOT NULL
                  AND b.accounts_receivable IS NOT NULL
                  AND b.current_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_assets, accounts_receivable = (
                    float(row["current_assets"]),
                    float(row["accounts_receivable"]),
                )
                residual = accounts_receivable - current_assets
                tolerance = abs(current_assets) * _ACCOUNTS_RECEIVABLE_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "current_assets": current_assets,
                            "accounts_receivable": accounts_receivable,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_accounts_receivable_le_current_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail accounts_receivable <= "
                    f"current_assets beyond {_ACCOUNTS_RECEIVABLE_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_accounts_receivable_le_current_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_accounts_receivable_le_current_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_ppe_net_le_total_assets(self, cur: Any) -> None:
        """ppe_net <= total_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_ppe_net_le_total_assets - reuses
        the annual _PPE_NET_TOLERANCE_PCT unchanged (live-verified 4/4,757).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_assets, b.ppe_net
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.ppe_net IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_assets, ppe_net = (
                    float(row["total_assets"]),
                    float(row["ppe_net"]),
                )
                residual = ppe_net - total_assets
                tolerance = abs(total_assets) * _PPE_NET_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_assets": total_assets,
                            "ppe_net": ppe_net,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_ppe_net_le_total_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail ppe_net <= total_assets beyond "
                    f"{_PPE_NET_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_ppe_net_le_total_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_ppe_net_le_total_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_short_term_debt_le_current_liabilities(self, cur: Any) -> None:
        """short_term_debt <= current_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_short_term_debt_le_current_liabilities - reuses the annual
        _SHORT_TERM_DEBT_TOLERANCE_PCT unchanged (live-verified 44/1,945, the noisiest of
        the Batch C ports at 2.3% but still a small minority, comparable to
        long_term_debt_le_total_liabilities's own noise floor).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.current_liabilities, b.short_term_debt
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.current_liabilities IS NOT NULL
                  AND b.short_term_debt IS NOT NULL
                  AND b.current_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                current_liabilities, short_term_debt = (
                    float(row["current_liabilities"]),
                    float(row["short_term_debt"]),
                )
                residual = short_term_debt - current_liabilities
                tolerance = abs(current_liabilities) * _SHORT_TERM_DEBT_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "current_liabilities": current_liabilities,
                            "short_term_debt": short_term_debt,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_short_term_debt_le_current_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail short_term_debt <= "
                    f"current_liabilities beyond {_SHORT_TERM_DEBT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_short_term_debt_le_current_liabilities failed: {e}", exc_info=True)
            self.log(
                "quarterly_short_term_debt_le_current_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_operating_lease_liability_le_total_liabilities(self, cur: Any) -> None:
        """operating_lease_liability <= total_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_operating_lease_liability_le_total_liabilities - reuses the annual
        _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT unchanged (live-verified 3/4,326).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.total_liabilities, b.operating_lease_liability
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.operating_lease_liability IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, operating_lease_liability = (
                    float(row["total_liabilities"]),
                    float(row["operating_lease_liability"]),
                )
                residual = operating_lease_liability - total_liabilities
                tolerance = abs(total_liabilities) * _OPERATING_LEASE_LIABILITY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_liabilities": total_liabilities,
                            "operating_lease_liability": operating_lease_liability,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_operating_lease_liability_le_total_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail operating_lease_liability <= "
                    f"total_liabilities beyond {_OPERATING_LEASE_LIABILITY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[TieOutChecker] quarterly_operating_lease_liability_le_total_liabilities failed: {e}", exc_info=True
            )
            self.log(
                "quarterly_operating_lease_liability_le_total_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_finance_lease_liability_le_total_liabilities(self, cur: Any) -> None:
        """finance_lease_liability <= total_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_finance_lease_liability_le_total_liabilities - reuses the annual
        _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT unchanged (live-verified 3/1,652).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.total_liabilities, b.finance_lease_liability
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.finance_lease_liability IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, finance_lease_liability = (
                    float(row["total_liabilities"]),
                    float(row["finance_lease_liability"]),
                )
                residual = finance_lease_liability - total_liabilities
                tolerance = abs(total_liabilities) * _FINANCE_LEASE_LIABILITY_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_liabilities": total_liabilities,
                            "finance_lease_liability": finance_lease_liability,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_finance_lease_liability_le_total_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail finance_lease_liability <= "
                    f"total_liabilities beyond {_FINANCE_LEASE_LIABILITY_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[TieOutChecker] quarterly_finance_lease_liability_le_total_liabilities failed: {e}", exc_info=True
            )
            self.log(
                "quarterly_finance_lease_liability_le_total_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_current_assets_le_total_assets(self, cur: Any) -> None:
        """current_assets <= total_assets (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of check_current_assets_le_total_assets -
        reuses the annual _CURRENT_VS_TOTAL_TOLERANCE_PCT unchanged (live-verified 1/4,634,
        the same SSL magnitude-swap bug the annual check also catches).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_assets, b.current_assets
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_assets IS NOT NULL
                  AND b.current_assets IS NOT NULL
                  AND b.total_assets != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_assets, current_assets = (
                    float(row["total_assets"]),
                    float(row["current_assets"]),
                )
                residual = current_assets - total_assets
                tolerance = abs(total_assets) * _CURRENT_VS_TOTAL_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_assets": total_assets,
                            "current_assets": current_assets,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_current_assets_le_total_assets",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail current_assets <= total_assets "
                    f"beyond {_CURRENT_VS_TOTAL_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_current_assets_le_total_assets failed: {e}", exc_info=True)
            self.log(
                "quarterly_current_assets_le_total_assets",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_current_liabilities_le_total_liabilities(self, cur: Any) -> None:
        """current_liabilities <= total_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_current_liabilities_le_total_liabilities - reuses the annual
        _CURRENT_VS_TOTAL_TOLERANCE_PCT unchanged (live-verified 4/4,596).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter,
                    b.total_liabilities, b.current_liabilities
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.current_liabilities IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, current_liabilities = (
                    float(row["total_liabilities"]),
                    float(row["current_liabilities"]),
                )
                residual = current_liabilities - total_liabilities
                tolerance = abs(total_liabilities) * _CURRENT_VS_TOTAL_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_liabilities": total_liabilities,
                            "current_liabilities": current_liabilities,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_current_liabilities_le_total_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail current_liabilities <= "
                    f"total_liabilities beyond {_CURRENT_VS_TOTAL_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(
                f"[TieOutChecker] quarterly_current_liabilities_le_total_liabilities failed: {e}", exc_info=True
            )
            self.log(
                "quarterly_current_liabilities_le_total_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )

    def check_quarterly_long_term_debt_le_total_liabilities(self, cur: Any) -> None:
        """long_term_debt <= total_liabilities (quarterly_balance_sheet, same row).

        ADDED 2026-09-07 (Round 3). Quarterly port of
        check_long_term_debt_le_total_liabilities - reuses the annual
        _LONG_TERM_DEBT_TOLERANCE_PCT unchanged (live-verified 38/4,331, comparable to
        annual's own 64/4,244).
        """
        try:
            cur.execute(
                """
                SELECT DISTINCT ON (b.symbol)
                    b.symbol, b.fiscal_year, b.fiscal_quarter, b.total_liabilities, b.long_term_debt
                FROM quarterly_balance_sheet b
                JOIN stock_symbols s ON s.symbol = b.symbol AND s.active = true
                WHERE b.data_unavailable = FALSE
                  AND b.total_liabilities IS NOT NULL
                  AND b.long_term_debt IS NOT NULL
                  AND b.total_liabilities != 0
                ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC
                """
            )
            flagged = []
            for row in cur.fetchall():
                total_liabilities, long_term_debt = (
                    float(row["total_liabilities"]),
                    float(row["long_term_debt"]),
                )
                residual = long_term_debt - total_liabilities
                tolerance = abs(total_liabilities) * _LONG_TERM_DEBT_TOLERANCE_PCT
                if residual > tolerance:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "fiscal_year": row["fiscal_year"],
                            "fiscal_quarter": row["fiscal_quarter"],
                            "total_liabilities": total_liabilities,
                            "long_term_debt": long_term_debt,
                            "residual": residual,
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["residual"], reverse=True)
                self.log(
                    "quarterly_long_term_debt_le_total_liabilities",
                    WARN,
                    "quarterly_balance_sheet",
                    f"{len(flagged)} symbol/quarter(s) fail long_term_debt <= "
                    f"total_liabilities beyond {_LONG_TERM_DEBT_TOLERANCE_PCT:.1%} slack",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
        except Exception as e:
            logger.error(f"[TieOutChecker] quarterly_long_term_debt_le_total_liabilities failed: {e}", exc_info=True)
            self.log(
                "quarterly_long_term_debt_le_total_liabilities",
                ERROR,
                "quarterly_balance_sheet",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
