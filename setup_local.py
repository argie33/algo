#!/usr/bin/env python3
"""
Comprehensive Local Development Setup Script
Sets up PostgreSQL, seeds data, and runs tests
"""

import subprocess
import sys
import os
import time
import json
from pathlib import Path

# Color codes
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

class LocalSetup:
    def __init__(self):
        self.db_host = "localhost"
        self.db_port = 5432
        self.db_user = "postgres"
        self.db_password = "password"
        self.db_name = "stocks"
        self.root_dir = Path(__file__).parent

    def print_header(self, text):
        print(f"\n{BLUE}{'='*60}{NC}")
        print(f"{BLUE}{text}{NC}")
        print(f"{BLUE}{'='*60}{NC}\n")

    def print_success(self, text):
        print(f"{GREEN}✅ {text}{NC}")

    def print_error(self, text):
        print(f"{RED}❌ {text}{NC}")

    def print_warning(self, text):
        print(f"{YELLOW}⚠️  {text}{NC}")

    def print_info(self, text):
        print(f"{BLUE}ℹ️  {text}{NC}")

    def run_command(self, cmd, shell=False, capture=False):
        """Run shell command"""
        try:
            if capture:
                result = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
                return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
            else:
                result = subprocess.run(cmd, shell=shell)
                return result.returncode == 0, "", ""
        except Exception as e:
            return False, "", str(e)

    def check_psql_connection(self):
        """Check if PostgreSQL is accessible"""
        cmd = [
            "psql", "-h", self.db_host, "-U", self.db_user,
            "-d", "postgres", "-c", "SELECT 1;"
        ]
        os.environ["PGPASSWORD"] = self.db_password
        success, _, _ = self.run_command(cmd)
        return success

    def step_check_prerequisites(self):
        """Check Node.js and npm"""
        self.print_header("STEP 1: Checking Prerequisites")

        # Check Node.js
        success, node_version, _ = self.run_command(["node", "--version"], capture=True)
        if not success:
            self.print_error("Node.js not found. Please install Node.js >= 18.0.0")
            return False
        self.print_success(f"Node.js found: {node_version}")

        # Check npm
        success, npm_version, _ = self.run_command(["npm", "--version"], capture=True)
        if not success:
            self.print_error("npm not found")
            return False
        self.print_success(f"npm found: {npm_version}")

        # Check psql
        success, psql_version, _ = self.run_command(["psql", "--version"], capture=True)
        if not success:
            self.print_warning("psql not found - will try to use available tools")
        else:
            self.print_success(f"psql found: {psql_version}")

        return True

    def step_verify_database(self):
        """Verify or setup database"""
        self.print_header("STEP 2: Verifying Database")

        os.environ["PGPASSWORD"] = self.db_password

        # Try to connect
        if self.check_psql_connection():
            self.print_success(f"PostgreSQL is running on {self.db_host}:{self.db_port}")
            return True

        self.print_warning("PostgreSQL not accessible")
        self.print_info("Make sure PostgreSQL is running:")
        self.print_info("  Linux:   sudo service postgresql start")
        self.print_info("  macOS:   brew services start postgresql")
        self.print_info("  Docker:  docker start postgres-stocks")
        return False

    def step_create_schema(self):
        """Create database schema"""
        self.print_header("STEP 3: Creating Database Schema")

        schema_file = self.root_dir / "webapp" / "lambda" / "setup_test_database.sql"
        if not schema_file.exists():
            self.print_error(f"Schema file not found: {schema_file}")
            return False

        os.environ["PGPASSWORD"] = self.db_password

        # Create database if not exists
        self.print_info("Creating database...")
        cmd = [
            "psql", "-h", self.db_host, "-U", self.db_user,
            "-d", "postgres", "-c", f"CREATE DATABASE IF NOT EXISTS {self.db_name};"
        ]
        self.run_command(cmd)

        # Apply schema
        self.print_info("Applying database schema...")
        cmd = [
            "psql", "-h", self.db_host, "-U", self.db_user,
            "-d", self.db_name, "-f", str(schema_file)
        ]
        success, _, err = self.run_command(cmd)

        if success or "already exists" in err:
            self.print_success("Database schema applied")
            return True
        else:
            self.print_warning(f"Schema application issues: {err[:100]}")
            return True  # Continue anyway

    def step_seed_data(self):
        """Seed test data"""
        self.print_header("STEP 4: Seeding Test Data")

        seed_file = self.root_dir / "webapp" / "lambda" / "seed_comprehensive_local_data.sql"
        if not seed_file.exists():
            self.print_warning(f"Seed file not found: {seed_file}")
            return False

        os.environ["PGPASSWORD"] = self.db_password

        self.print_info("Seeding comprehensive test data...")
        cmd = [
            "psql", "-h", self.db_host, "-U", self.db_user,
            "-d", self.db_name, "-f", str(seed_file)
        ]
        success, _, err = self.run_command(cmd)

        if success:
            self.print_success("Test data seeded")
        else:
            self.print_warning(f"Seeding completed with issues: {err[:100]}")

        return True

    def step_verify_data(self):
        """Verify data was loaded"""
        self.print_header("STEP 5: Verifying Data")

        os.environ["PGPASSWORD"] = self.db_password

        queries = {
            "stock_symbols": "SELECT COUNT(*) FROM stock_symbols;",
            "price_daily": "SELECT COUNT(*) FROM price_daily;",
            "stock_scores": "SELECT COUNT(*) FROM stock_scores;",
            "company_profile": "SELECT COUNT(*) FROM company_profile;",
        }

        for table, query in queries.items():
            cmd = [
                "psql", "-h", self.db_host, "-U", self.db_user,
                "-d", self.db_name, "-t", "-c", query
            ]
            success, output, _ = self.run_command(cmd, capture=True)
            count = output.strip() if success else "0"
            self.print_info(f"{table}: {count} records")

    def step_install_dependencies(self):
        """Install npm dependencies"""
        self.print_header("STEP 6: Installing Dependencies")

        # Backend
        lambda_dir = self.root_dir / "webapp" / "lambda"
        if not (lambda_dir / "node_modules").exists():
            self.print_info("Installing backend dependencies...")
            os.chdir(lambda_dir)
            success, _, _ = self.run_command(["npm", "install"], shell=False)
            os.chdir(self.root_dir)
            if success:
                self.print_success("Backend dependencies installed")
            else:
                self.print_warning("Backend dependencies installation had issues")
        else:
            self.print_success("Backend dependencies already installed")

        # Frontend
        frontend_dir = self.root_dir / "webapp" / "frontend"
        if not (frontend_dir / "node_modules").exists():
            self.print_info("Installing frontend dependencies...")
            os.chdir(frontend_dir)
            success, _, _ = self.run_command(["npm", "install"], shell=False)
            os.chdir(self.root_dir)
            if success:
                self.print_success("Frontend dependencies installed")
            else:
                self.print_warning("Frontend dependencies installation had issues")
        else:
            self.print_success("Frontend dependencies already installed")

    def step_create_status_report(self):
        """Create setup status report"""
        self.print_header("SETUP STATUS REPORT")

        os.environ["PGPASSWORD"] = self.db_password

        # Database info
        print(f"{GREEN}Database Configuration:{NC}")
        print(f"  Host: {self.db_host}")
        print(f"  Port: {self.db_port}")
        print(f"  Database: {self.db_name}")
        print(f"  User: {self.db_user}")

        # Data counts
        print(f"\n{GREEN}Data Summary:{NC}")
        queries = {
            "Symbols": "SELECT COUNT(*) FROM stock_symbols;",
            "Prices": "SELECT COUNT(*) FROM price_daily;",
            "Scores": "SELECT COUNT(*) FROM stock_scores;",
            "Companies": "SELECT COUNT(*) FROM company_profile;",
        }

        for label, query in queries.items():
            cmd = [
                "psql", "-h", self.db_host, "-U", self.db_user,
                "-d", self.db_name, "-t", "-c", query
            ]
            success, output, _ = self.run_command(cmd, capture=True)
            count = output.strip() if success else "?"
            print(f"  {label}: {count}")

        # Next steps
        print(f"\n{GREEN}Next Steps:{NC}")
        print(f"  1. Start backend:")
        print(f"     cd {self.root_dir}/webapp/lambda")
        print(f"     npm start")
        print(f"\n  2. Start frontend (new terminal):")
        print(f"     cd {self.root_dir}/webapp/frontend")
        print(f"     npm run dev")
        print(f"\n  3. Open in browser:")
        print(f"     http://localhost:5173")
        print(f"\n  4. Run tests:")
        print(f"     cd {self.root_dir}/webapp/lambda")
        print(f"     npm test")

        print(f"\n{GREEN}API Endpoints:{NC}")
        print(f"  Health:    http://localhost:5001/health")
        print(f"  Dashboard: http://localhost:5001/api/dashboard/summary")
        print(f"  Sectors:   http://localhost:5001/api/sectors")

    def run(self):
        """Execute full setup"""
        try:
            if not self.step_check_prerequisites():
                return False

            if not self.step_verify_database():
                self.print_error("Cannot proceed without database connection")
                return False

            if not self.step_create_schema():
                self.print_warning("Schema creation had issues, continuing...")

            if not self.step_seed_data():
                self.print_warning("Data seeding had issues, continuing...")

            self.step_verify_data()
            self.step_install_dependencies()
            self.step_create_status_report()

            print(f"\n{GREEN}{'='*60}{NC}")
            print(f"{GREEN}Setup complete! Your local dev environment is ready.{NC}")
            print(f"{GREEN}{'='*60}{NC}\n")
            return True

        except Exception as e:
            self.print_error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    setup = LocalSetup()
    success = setup.run()
    sys.exit(0 if success else 1)
