#!/usr/bin/env python3
"""
Local Database Setup Helper
Sets up PostgreSQL for local development or verifies existing setup.
"""

import subprocess
import os
import sys
import json
from pathlib import Path

def run_command(cmd, shell=False):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Command timeout"
    except Exception as e:
        return 1, "", str(e)

def check_postgresql():
    """Check if PostgreSQL is installed and running"""
    # Check if psql is available
    code, out, err = run_command("psql --version")
    if code != 0:
        print("❌ PostgreSQL client not found. Please install PostgreSQL 16+")
        return False

    print("✅ PostgreSQL client found:", out.strip())

    # Check if service is running
    code, out, err = run_command("systemctl status postgresql", shell=True)
    if "active (running)" in out or code == 0:
        print("✅ PostgreSQL service is running")
        return True
    else:
        print("⚠️  PostgreSQL service might not be running")
        print("   Try: sudo systemctl start postgresql")
        return False

def check_docker():
    """Check if Docker is available"""
    code, out, err = run_command("docker --version")
    if code != 0:
        return False

    code, out, err = run_command("docker compose version")
    if code != 0:
        return False

    return True

def check_local_connection():
    """Test connection to local PostgreSQL"""
    env = os.environ.copy()
    env['PGPASSWORD'] = 'stocks'

    code, out, err = run_command(
        "psql -U stocks -h localhost -d stocks -c 'SELECT 1;'",
        shell=True
    )

    if code == 0:
        print("✅ Successfully connected to local PostgreSQL")
        return True
    else:
        if "password authentication failed" in err:
            print("❌ PostgreSQL authentication failed for user 'stocks'")
            print("   Database exists but credentials are wrong")
        elif "does not exist" in err:
            print("⚠️  Database 'stocks' does not exist yet")
        else:
            print(f"❌ Connection failed: {err[:100]}")
        return False

def create_env_file():
    """Create .env.local file with database configuration"""
    env_file = Path("/home/stocks/.env.local")

    env_content = """# Local Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=stocks
DB_NAME=stocks

# AWS Configuration (leave empty for local dev)
AWS_REGION=
DB_SECRET_ARN=
"""

    if env_file.exists():
        print(f"ℹ️  .env.local already exists at {env_file}")
        with open(env_file, 'r') as f:
            content = f.read()
            if 'DB_HOST' in content:
                print("✅ .env.local is properly configured")
                return True
    else:
        try:
            env_file.write_text(env_content)
            print(f"✅ Created .env.local at {env_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to create .env.local: {e}")
            return False

def test_data_loader():
    """Test if data loaders can load configuration"""
    try:
        from lib.db import get_db_config
        cfg = get_db_config()
        print("✅ Data loader can load database configuration")
        print(f"   Host: {cfg['host']}")
        print(f"   User: {cfg['user']}")
        print(f"   Database: {cfg['dbname']}")
        return True
    except Exception as e:
        print(f"❌ Data loader configuration failed: {e}")
        return False

def print_status_report(results):
    """Print a status report"""
    print("\n" + "="*60)
    print("LOCAL DEVELOPMENT SETUP STATUS")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"\n✅ Checks Passed: {passed}/{total}\n")

    if passed == total:
        print("🎉 Local development environment is ready!")
        print("\nNext steps:")
        print("1. Start backend:  cd /home/stocks/algo/webapp/lambda && node index.js")
        print("2. Start frontend: cd /home/stocks/algo/webapp/frontend && npm run dev")
        print("3. Load data:      bash /tmp/refresh_all_data.sh")
        return True
    else:
        print("⚠️  Some checks failed. See above for details.\n")
        if not results.get('postgres_running'):
            print("PostgreSQL Setup Options:")
            print("1. Local PostgreSQL: sudo systemctl start postgresql")
            print("2. Docker:          docker compose -f /home/stocks/algo/docker-compose.yml up -d")
        return False

def main():
    print("🔧 Local Database Setup Helper\n")

    results = {}

    # Check PostgreSQL
    print("1. Checking PostgreSQL...")
    results['postgres_installed'] = check_postgresql()

    # Check connection
    print("\n2. Checking PostgreSQL connection...")
    results['postgres_connection'] = check_local_connection()

    # Check Docker availability
    print("\n3. Checking Docker (optional)...")
    docker_available = check_docker()
    if docker_available:
        print("✅ Docker is available as an alternative")
    else:
        print("ℹ️  Docker not available (not required)")

    # Create/verify .env.local
    print("\n4. Setting up environment variables...")
    results['env_file'] = create_env_file()

    # Test data loaders
    print("\n5. Testing data loader configuration...")
    results['data_loader'] = test_data_loader()

    # Print status
    success = print_status_report(results)

    # If PostgreSQL not connecting, offer alternatives
    if not results.get('postgres_connection'):
        print("\n" + "="*60)
        print("DATABASE NOT CONNECTED - OPTIONS:")
        print("="*60)
        print("\nOption A: Use Docker Compose (Recommended)")
        print("  cd /home/stocks/algo")
        print("  docker compose up -d")
        print("  (Wait a few seconds for PostgreSQL to start)")

        print("\nOption B: Manual PostgreSQL Setup")
        print("  sudo systemctl start postgresql")
        print("  sudo -u postgres psql -f /home/stocks/algo/init-db.sql")

        print("\nOption C: Use Cached Data (No Database)")
        print("  Frontend will display cached data from previous loads")
        print("  Run: cd /home/stocks/algo/webapp/lambda && node index.js")

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
