#!/usr/bin/env python3
"""Fix dashboard by populating algo_config table with required entries."""

import os
import sys

import psycopg2


def main():
    # Get DB credentials
    db_host = os.environ.get("DB_HOST")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME")

    if not all([db_host, db_user, db_password, db_name]):
        print("ERROR: Database credentials not set")
        print("Required: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME")
        return 1

    print("Dashboard Configuration Fix")
    print("=" * 50)
    print("")
    print(f"Connecting to {db_name}@{db_host}...")

    try:
        # Use SSL for AWS RDS, disable for local dev databases
        sslmode = "require" if "rds.amazonaws.com" in db_host else "prefer"

        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            sslmode=sslmode
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

        print(f"[OK] SUCCESS: {count}/7 required config keys populated")
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
        print("[OK] Configuration fix applied successfully")
        print("")
        print("Next steps:")
        print("  1. Run dashboard: python -m dashboard")
        print("  2. All panels should now load with data")
        return 0

    except psycopg2.Error as e:
        print("[ERROR] Database error: " + str(e))
        return 1
    except Exception as e:
        print("[ERROR] Error: " + str(e))
        return 1

if __name__ == "__main__":
    sys.exit(main())
