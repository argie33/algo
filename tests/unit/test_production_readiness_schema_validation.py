#!/usr/bin/env python3
"""
Test that production_readiness_check validates column data types, not just existence.

This verifies the fix for: "Schema validation missing types — Only checks column existence, not data types"

Before fix: check_database_connectivity() only checked if tables existed (information_schema.tables)
After fix: check_database_connectivity() validates column types using validate_table_schema()
"""

import unittest
from unittest.mock import Mock, patch


class TestProductionReadinessSchemaValidation(unittest.TestCase):
    """Test that production readiness check validates column types."""

    def _mock_cursor_with_schema(self, columns_data):
        """Create a mock cursor that returns the given columns data."""
        mock_cur = Mock()
        self._columns_data = columns_data  # Store for fetchall

        def execute_side_effect(query, *args, **kwargs):
            # Store query for fetchall/fetchone to know what to return
            self._last_query = (
                query
                if isinstance(query, str)
                else (query if len(args) == 0 else args[0])
            )

        def fetchall_side_effect():
            # Check last query to know what data to return
            if "information_schema.columns" in self._last_query:
                return self._columns_data
            return []

        def fetchone_side_effect():
            # For table existence checks
            if "information_schema.tables" in self._last_query:
                return (1,)
            return None

        mock_cur.execute.side_effect = execute_side_effect
        mock_cur.fetchall.side_effect = fetchall_side_effect
        mock_cur.fetchone.side_effect = fetchone_side_effect
        return mock_cur

    def test_detects_correct_column_types(self):
        """Valid schema with correct types should pass."""
        columns = [
            ("symbol", "varchar"),
            ("date", "date"),
            ("open", "numeric"),
            ("high", "numeric"),
            ("low", "numeric"),
            ("close", "numeric"),
            ("volume", "int8"),
            ("adj_close", "numeric"),
        ]

        mock_cur = self._mock_cursor_with_schema(columns)

        from utils.ops.production_readiness import ProductionReadinessCheck

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_cur

            check = ProductionReadinessCheck()
            result = check.check_database_connectivity()

            self.assertTrue(result)
            self.assertTrue(any("schema valid" in msg for msg in check.checks_passed))

    def test_detects_wrong_column_type(self):
        """Column with wrong type (e.g., TEXT instead of NUMERIC) should fail."""
        columns = [
            ("symbol", "varchar"),
            ("date", "date"),
            ("open", "numeric"),
            ("high", "numeric"),
            ("low", "numeric"),
            ("close", "text"),  # WRONG: should be numeric
            ("volume", "int8"),
            ("adj_close", "numeric"),
        ]

        mock_cur = self._mock_cursor_with_schema(columns)

        from utils.ops.production_readiness import ProductionReadinessCheck

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_cur

            check = ProductionReadinessCheck()
            result = check.check_database_connectivity()

            self.assertFalse(result)
            self.assertTrue(any("schema INVALID" in msg for msg in check.checks_failed))
            self.assertTrue(
                any(
                    "close" in msg and "wrong type" in msg.lower()
                    for msg in check.checks_failed
                )
            )

    def test_detects_missing_column(self):
        """Missing column should fail."""
        columns = [
            ("symbol", "varchar"),
            ("date", "date"),
            ("open", "numeric"),
            ("high", "numeric"),
            ("low", "numeric"),
            # 'close' is MISSING
            ("volume", "int8"),
        ]

        mock_cur = self._mock_cursor_with_schema(columns)

        from utils.ops.production_readiness import ProductionReadinessCheck

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_cur

            check = ProductionReadinessCheck()
            result = check.check_database_connectivity()

            self.assertFalse(result)
            self.assertTrue(any("schema INVALID" in msg for msg in check.checks_failed))


if __name__ == "__main__":
    unittest.main()
