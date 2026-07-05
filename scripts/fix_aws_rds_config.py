#!/usr/bin/env python3
"""
Fix AWS RDS database by populating algo_config with required values.

This script connects to AWS RDS (not local) and populates the algo_config table
with values required by the dashboard API.

Usage:
  python scripts/fix_aws_rds_config.py --fetch-from-secrets
  python scripts/fix_aws_rds_config.py --host <rds-endpoint> --user <user> --password <pass>
"""

import argparse
import json
import sys

import boto3
import psycopg2


def get_credentials_from_secrets(secret_name: str = "algo/rds/password") -> dict:
    """Fetch RDS credentials from AWS Secrets Manager."""
    try:
        client = boto3.client("secretsmanager", region_name="us-east-1")
        response = client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            return json.loads(response["SecretString"])
        raise ValueError(f"Secret {secret_name} not found")
    except Exception as e:
        print(f"[ERROR] Could not fetch credentials from Secrets Manager: {e}")
        return None


def fix_rds_config(db_host: str, db_user: str, db_password: str, db_name: str = "algo") -> bool:
    """Populate algo_config table in AWS RDS."""
    print("AWS RDS Configuration Fix")
    print("=" * 60)
    print("")
    print(f"Connecting to {db_name}@{db_host}...")

    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            sslmode="require"  # AWS RDS requires SSL
        )
        cur = conn.cursor()

        # SQL to populate required config
        sql = """
        INSERT INTO algo_config (key, value, value_type, description, updated_by)
        VALUES
          ('min_completeness_score', '70', 'int', 'Minimum data completeness %', 'fix-script'),
          ('min_stock_price', '5.0', 'float', 'Minimum stock price $', 'fix-script'),
          ('min_signal_quality_score', '60', 'int', 'Minimum SQS 0-100', 'fix-script'),
          ('min_volume_ma_50d', '300000', 'int', 'Minimum 50-day avg volume', 'fix-script'),
          ('min_avg_daily_dollar_volume', '500000', 'float', 'Minimum daily dollar volume', 'fix-script'),
          ('earnings_blackout_days_before', '7', 'int', 'Days before earnings to block entries', 'fix-script'),
          ('earnings_blackout_days_after', '3', 'int', 'Days after earnings to block entries', 'fix-script'),
          ('base_risk_pct', '0.75', 'float', 'Base portfolio risk per trade', 'fix-script'),
          ('max_position_size_pct', '8.0', 'float', 'Maximum single position size', 'fix-script'),
          ('max_positions', '15', 'int', 'Maximum concurrent positions', 'fix-script'),
          ('max_concentration_pct', '50.0', 'float', 'Max concentration in top position', 'fix-script'),
          ('max_distribution_days', '4', 'int', 'Max market distribution days', 'fix-script'),
          ('require_stage_2_market', 'false', 'bool', 'Require market Stage 2 at Tier 2', 'fix-script'),
          ('vix_max_threshold', '35.0', 'float', 'VIX level to halt trading', 'fix-script'),
          ('vix_caution_threshold', '25.0', 'float', 'VIX level to reduce positions', 'fix-script'),
          ('min_swing_score', '55.0', 'float', 'Min swing trader score to enter', 'fix-script'),
          ('min_swing_grade', '', 'string', 'Min swing grade override', 'fix-script'),
          ('execution_mode', 'paper', 'string', 'paper|dry|review|auto', 'fix-script'),
          ('alpaca_paper_trading', 'true', 'bool', 'Use Alpaca paper account', 'fix-script'),
          ('enable_algo', 'true', 'bool', 'Enable algo trading', 'fix-script'),
          ('verbose_logging', 'true', 'bool', 'Detailed logging', 'fix-script')
        ON CONFLICT (key) DO NOTHING
        """

        print("Executing migration...")
        cur.execute(sql)
        conn.commit()

        # Verify
        cur.execute("""
            SELECT COUNT(*) FROM algo_config
            WHERE key IN (
                'min_signal_quality_score',
                'min_swing_score',
                'min_completeness_score',
                'min_volume_ma_50d',
                'min_avg_daily_dollar_volume',
                'earnings_blackout_days_before',
                'earnings_blackout_days_after'
            )
        """)
        count = cur.fetchone()[0]

        print(f"[OK] SUCCESS: {count}/7 required config keys populated in AWS RDS")
        print("")
        print("Config values:")
        cur.execute("""
            SELECT key, value FROM algo_config
            WHERE key IN (
                'min_signal_quality_score',
                'min_swing_score',
                'min_completeness_score',
                'min_volume_ma_50d',
                'min_avg_daily_dollar_volume',
                'earnings_blackout_days_before',
                'earnings_blackout_days_after'
            )
            ORDER BY key
        """)

        for key, value in cur.fetchall():
            print(f"  {key} = {value}")

        cur.close()
        conn.close()

        print("")
        print("[OK] AWS RDS configuration fix applied successfully")
        print("")
        print("Next steps:")
        print("  1. Wait for API Lambda to restart (or restart manually)")
        print("  2. Run dashboard: python -m dashboard")
        print("  3. All panels should now load with data")
        return True

    except psycopg2.Error as e:
        print(f"[ERROR] Database error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Fix AWS RDS algo_config for dashboard")
    parser.add_argument("--fetch-from-secrets", action="store_true", help="Fetch credentials from AWS Secrets Manager")
    parser.add_argument("--host", help="RDS endpoint hostname")
    parser.add_argument("--user", help="Database user (usually 'postgres')")
    parser.add_argument("--password", help="Database password")
    parser.add_argument("--database", default="algo", help="Database name (default: algo)")

    args = parser.parse_args()

    if args.fetch_from_secrets:
        print("Fetching credentials from AWS Secrets Manager...")
        creds = get_credentials_from_secrets()
        if not creds:
            return 1
        db_host = creds.get("host")
        db_user = creds.get("username")
        db_password = creds.get("password")
        db_name = creds.get("dbname", "algo")
    else:
        db_host = args.host
        db_user = args.user
        db_password = args.password
        db_name = args.database

    if not all([db_host, db_user, db_password]):
        print("ERROR: Missing required credentials")
        print("")
        print("Options:")
        print("  1. Use Secrets Manager: python scripts/fix_aws_rds_config.py --fetch-from-secrets")
        print("  2. Provide explicitly: python scripts/fix_aws_rds_config.py --host <host> --user <user> --password <pass>")
        return 1

    success = fix_rds_config(db_host, db_user, db_password, db_name)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
