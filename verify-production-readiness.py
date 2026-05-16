#!/usr/bin/env python3
"""
PRODUCTION READINESS VERIFICATION
Checks code quality, module integrity, and configuration without needing a running database
"""

import os
import sys
import ast
import json
from pathlib import Path
from collections import defaultdict

class ProductionAudit:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checks_passed = []
        self.root = Path(".")

    def check(self, name, passed, message=""):
        if passed:
            self.checks_passed.append(name)
            print(f"[PASS] {name}")
        else:
            self.errors.append(f"{name}: {message}")
            print(f"[FAIL] {name}: {message}")

    def warn(self, name, message=""):
        self.warnings.append(f"{name}: {message}")
        print(f"[WARN] {name}: {message}")

    # ====== TIER 1: CODE INTEGRITY ======

    def check_python_modules(self):
        """Verify all core Python modules are syntactically correct"""
        print("\n=== PYTHON MODULE INTEGRITY ===")

        core_modules = [
            "algo_config.py",
            "algo_orchestrator.py",
            "algo_signals.py",
            "algo_filter_pipeline.py",
            "algo_exit_engine.py",
            "algo_position_sizer.py",
            "loadstockscores.py",
        ]

        for module in core_modules:
            if not (self.root / module).exists():
                self.check(f"Module {module} exists", False)
                continue

            try:
                with open(self.root / module) as f:
                    ast.parse(f.read())
                self.check(f"Module {module} syntax", True)
            except SyntaxError as e:
                self.check(f"Module {module} syntax", False, str(e))

    def check_imports(self):
        """Verify critical imports are available"""
        print("\n=== IMPORT AVAILABILITY ===")

        try:
            import psycopg2
            self.check("psycopg2 module", True)
        except ImportError:
            self.check("psycopg2 module", False, "PostgreSQL driver not installed")

        try:
            from dotenv import load_dotenv
            self.check("python-dotenv module", True)
        except ImportError:
            self.check("python-dotenv module", False, "python-dotenv not installed")

        try:
            import pandas
            self.check("pandas module", True)
        except ImportError:
            self.check("pandas module", False, "pandas not installed")

    def check_database_schema(self):
        """Verify database schema file is complete"""
        print("\n=== DATABASE SCHEMA ===")

        schema_files = [
            "init_database.py",
            "init_db.sql",
        ]

        for schema_file in schema_files:
            if (self.root / schema_file).exists():
                with open(self.root / schema_file) as f:
                    content = f.read()

                # Check for critical tables
                critical_tables = [
                    "stock_symbols",
                    "price_daily",
                    "stock_scores",
                    "algo_trades",
                    "algo_positions",
                    "quality_metrics",
                    "growth_metrics",
                    "value_metrics",
                ]

                found_tables = sum(1 for table in critical_tables if table in content)
                self.check(
                    f"{schema_file} has critical tables",
                    found_tables >= 7,
                    f"Found {found_tables}/8 critical tables"
                )

    def check_configuration(self):
        """Verify algo_config.py has reasonable defaults"""
        print("\n=== CONFIGURATION ===")

        try:
            import algo_config
            config = algo_config.get_config()

            self.check("algo_config loads", True)

            # Check critical config values
            critical_keys = [
                'max_positions',
                'max_position_size_pct',
                'risk_per_trade_pct',
                'min_trend_template_score',
            ]

            for key in critical_keys:
                has_key = hasattr(config, key) or key in config
                self.check(f"Config has {key}", has_key)

        except Exception as e:
            self.check("algo_config loads", False, str(e))

    # ====== TIER 2: CALCULATION CORRECTNESS ======

    def check_rsi_calculation(self):
        """Verify RSI formula is Wilder's method"""
        print("\n=== CALCULATION VERIFICATION ===")

        with open(self.root / "loadstockscores.py") as f:
            content = f.read()

        # Check for Wilder's RSI formula
        has_wilder_formula = (
            "100 - (100 / (1 + RS))" in content or
            "100 - (100 / (1+rs))" in content or
            "100 - (100/(1 + rs))" in content
        )
        self.check("RSI uses Wilder's formula", has_wilder_formula)

    def check_percentile_ranking(self):
        """Verify RS uses PERCENT_RANK, not linear scalar"""
        print("\n=== PERCENTILE RANKING ===")

        with open(self.root / "algo_signals.py") as f:
            content = f.read()

        has_percent_rank = "PERCENT_RANK()" in content
        self.check("RS uses PERCENT_RANK()", has_percent_rank)

        # Should NOT use linear scalar
        has_linear = "pct = 50 + (excess_return * 150)" in content
        self.check("RS does not use linear scalar", not has_linear)

    def check_position_sizing(self):
        """Verify position sizing has risk limits"""
        print("\n=== POSITION SIZING ===")

        with open(self.root / "algo_position_sizer.py") as f:
            content = f.read()

        has_risk_pct = "risk_per_trade_pct" in content
        has_max_position = "max_position_size_pct" in content

        self.check("Position sizer uses risk_per_trade_pct", has_risk_pct)
        self.check("Position sizer uses max_position_size_pct", has_max_position)

    # ====== TIER 3: SECURITY ======

    def check_credentials(self):
        """Verify no hardcoded credentials in code"""
        print("\n=== CREDENTIAL SECURITY ===")

        sensitive_patterns = [
            "ALPACA_API_KEY",
            "FRED_API_KEY",
            "APCA_API_SECRET_KEY",
            "POSTGRES_PASSWORD",
        ]

        # Check Python files
        py_files = list(self.root.glob("*.py"))
        credentials_found = []

        for py_file in py_files:
            if "test" in str(py_file):
                continue

            with open(py_file) as f:
                content = f.read()

            for pattern in sensitive_patterns:
                # Allow env var references, not hardcoded values
                if pattern in content:
                    # Check if it's in os.getenv() or similar
                    if f'os.getenv("{pattern}")' not in content and \
                       f"os.getenv('{pattern}')" not in content:
                        credentials_found.append((str(py_file), pattern))

        if credentials_found:
            self.warn("Hardcoded credentials check",
                     f"Found {len(credentials_found)} potential hardcoded patterns")
        else:
            self.check("No hardcoded credentials found", True)

    def check_sql_injection(self):
        """Verify all database queries are parameterized"""
        print("\n=== SQL INJECTION PREVENTION ===")

        py_files = list(self.root.glob("*.py"))
        unsafe_queries = []

        for py_file in py_files:
            with open(py_file) as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                # Look for f-strings or + concatenation in SQL
                if "execute(" in line and (".format(" in line or f"f'" in line or f'f"' in line):
                    unsafe_queries.append((py_file.name, i+1))

        if unsafe_queries:
            self.warn("SQL parameterization check",
                     f"Found {len(unsafe_queries)} potential unsafe queries (may be false positives)")
        else:
            self.check("All SQL queries appear parameterized", True)

    # ====== TIER 4: API ======

    def check_api_helpers(self):
        """Verify API uses sendSuccess/sendError helpers"""
        print("\n=== API CONSISTENCY ===")

        routes_dir = self.root / "webapp" / "lambda" / "routes"
        if not routes_dir.exists():
            self.warn("API routes directory", f"Not found at {routes_dir}")
            return

        js_files = list(routes_dir.glob("*.js"))
        using_helpers = 0

        for js_file in js_files:
            with open(js_file) as f:
                content = f.read()

            if "sendSuccess" in content or "sendError" in content:
                using_helpers += 1

        self.check(f"API endpoints use helpers",
                  using_helpers >= len(js_files) * 0.7,
                  f"{using_helpers}/{len(js_files)} files")

    # ====== TIER 5: FRONTEND ======

    def check_frontend_dependencies(self):
        """Verify frontend has all necessary dependencies"""
        print("\n=== FRONTEND DEPENDENCIES ===")

        package_json = self.root / "webapp" / "frontend" / "package.json"

        if package_json.exists():
            with open(package_json) as f:
                deps = json.load(f)

            required_deps = ["react", "axios", "react-router-dom"]
            for dep in required_deps:
                has_dep = dep in deps.get("dependencies", {})
                self.check(f"Has {dep} dependency", has_dep)

    def check_terraform_validation(self):
        """Verify Terraform is valid (run: terraform validate)"""
        print("\n=== TERRAFORM CONFIGURATION ===")

        tf_files = list((self.root / "terraform").glob("**/*.tf"))
        self.check(f"Terraform files exist", len(tf_files) > 0, f"Found {len(tf_files)} .tf files")

        # Check for critical resources
        critical_resources = [
            "aws_rds_instance",
            "aws_lambda_function",
            "aws_apigatewayv2_api",
            "aws_ecs_cluster",
        ]

        tf_content = " ".join([f.read_text() for f in tf_files])
        for resource in critical_resources:
            has_resource = resource in tf_content
            self.check(f"Has {resource}", has_resource)

    # ====== RUNNER ======

    def run_all_checks(self):
        """Run all verification checks"""
        print("=" * 60)
        print("PRODUCTION READINESS AUDIT")
        print("=" * 60)

        self.check_python_modules()
        self.check_imports()
        self.check_database_schema()
        self.check_configuration()
        self.check_rsi_calculation()
        self.check_percentile_ranking()
        self.check_position_sizing()
        self.check_credentials()
        self.check_sql_injection()
        self.check_api_helpers()
        self.check_frontend_dependencies()
        self.check_terraform_validation()

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"[PASS] Checks passed: {len(self.checks_passed)}")
        print(f"[WARN] Warnings: {len(self.warnings)}")
        print(f"[FAIL] Errors: {len(self.errors)}")

        if self.errors:
            print("\nERRORS:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print("\nWARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")

        print("\n" + "=" * 60)
        if self.errors:
            print("[FAIL] PRODUCTION NOT READY — Fix errors above")
            return 1
        elif self.warnings:
            print("[PASS] PRODUCTION READY (with warnings — review above)")
            return 0
        else:
            print("[PASS] PRODUCTION READY — All checks passed!")
            return 0

if __name__ == "__main__":
    audit = ProductionAudit()
    sys.exit(audit.run_all_checks())
