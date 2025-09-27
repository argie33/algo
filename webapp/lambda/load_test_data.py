#!/usr/bin/env python3
"""
Load test data into analyst tables for local testing
This script populates the analyst-related tables with sample data
to ensure tests have realistic data to work with.
"""

import psycopg2
from datetime import datetime, date, timedelta
import os

def get_local_db_config():
    """Get local database configuration"""
    return {
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "password",
        "dbname": "stocks"
    }

def load_analyst_recommendations(cur):
    """Load sample analyst recommendations data"""
    print("Loading analyst_recommendations data...")

    # Clear existing data
    cur.execute("DELETE FROM analyst_recommendations")

    # Sample data - matching actual schema
    recommendations = [
        ("AAPL", "Goldman Sachs", "Strong Buy", 185.50, 175.50, "2025-09-27"),
        ("AAPL", "Morgan Stanley", "Buy", 180.00, 175.50, "2025-09-26"),
        ("AAPL", "JPMorgan", "Overweight", 190.00, 175.50, "2025-09-25"),
        ("MSFT", "Goldman Sachs", "Buy", 425.00, 420.75, "2025-09-27"),
        ("MSFT", "Barclays", "Overweight", 430.00, 420.75, "2025-09-26"),
        ("TSLA", "Deutsche Bank", "Hold", 240.00, 235.00, "2025-09-25"),
    ]

    for symbol, analyst_firm, rating, target_price, current_price, date_published in recommendations:
        cur.execute("""
            INSERT INTO analyst_recommendations
            (symbol, analyst_firm, rating, target_price, current_price, date_published)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (symbol, analyst_firm, rating, target_price, current_price, date_published))

    print(f"Inserted {len(recommendations)} analyst recommendations")

def load_analyst_coverage(cur):
    """Load sample analyst coverage data"""
    print("Loading analyst_coverage data...")

    # Clear existing data
    cur.execute("DELETE FROM analyst_coverage")

    # Sample data - matching actual schema
    coverage = [
        ("AAPL", "Goldman Sachs", "John Doe", "2025-09-01", "active"),
        ("AAPL", "Morgan Stanley", "Jane Smith", "2025-09-01", "active"),
        ("AAPL", "JPMorgan", "Bob Johnson", "2025-08-15", "active"),
        ("AAPL", "Barclays", "Alice Brown", "2025-08-01", "active"),
        ("MSFT", "Goldman Sachs", "Mike Wilson", "2025-09-01", "active"),
        ("MSFT", "Barclays", "Sarah Davis", "2025-08-20", "active"),
        ("MSFT", "Credit Suisse", "Tom Lee", "2025-08-10", "active"),
    ]

    for symbol, analyst_firm, analyst_name, coverage_started, coverage_status in coverage:
        cur.execute("""
            INSERT INTO analyst_coverage
            (symbol, analyst_firm, analyst_name, coverage_started, coverage_status)
            VALUES (%s, %s, %s, %s, %s)
        """, (symbol, analyst_firm, analyst_name, coverage_started, coverage_status))

    print(f"Inserted {len(coverage)} analyst coverage records")

def load_analyst_price_targets(cur):
    """Load sample price targets data"""
    print("Loading analyst_price_targets data...")

    # Clear existing data
    cur.execute("DELETE FROM analyst_price_targets")

    # Sample data - matching actual schema
    targets = [
        ("AAPL", "Goldman Sachs", 185.50, 180.00, "2025-09-27"),
        ("AAPL", "Morgan Stanley", 180.00, 175.00, "2025-09-26"),
        ("AAPL", "JPMorgan", 190.00, 185.00, "2025-09-25"),
        ("AAPL", "Barclays", 175.00, 170.00, "2025-09-24"),
        ("AAPL", "Credit Suisse", 182.00, 178.00, "2025-09-23"),
        ("MSFT", "Goldman Sachs", 425.00, 420.00, "2025-09-27"),
        ("MSFT", "Barclays", 430.00, 425.00, "2025-09-26"),
        ("MSFT", "Credit Suisse", 410.00, 405.00, "2025-09-25"),
        ("TSLA", "Deutsche Bank", 240.00, 250.00, "2025-09-25"),
        ("TSLA", "Wedbush", 300.00, 290.00, "2025-09-24"),
    ]

    for symbol, analyst_firm, target_price, previous_target_price, target_date in targets:
        cur.execute("""
            INSERT INTO analyst_price_targets
            (symbol, analyst_firm, target_price, previous_target_price, target_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (symbol, analyst_firm, target_price, previous_target_price, target_date))

    print(f"Inserted {len(targets)} price targets")

def load_research_reports(cur):
    """Load sample research reports data"""
    print("Loading research_reports data...")

    # Clear existing data
    cur.execute("DELETE FROM research_reports")

    # Sample data - matching actual schema
    reports = [
        ("AAPL", "Goldman Sachs", "Apple: Strong iPhone 15 Cycle Ahead", "Strong fundamentals support continued growth", "https://example.com/report1", "2025-09-27"),
        ("AAPL", "Morgan Stanley", "Apple Services Growth Accelerating", "Services revenue showing accelerating momentum", "https://example.com/report2", "2025-09-26"),
        ("MSFT", "Goldman Sachs", "Microsoft: AI Leadership Driving Growth", "Leading position in AI market expected to drive revenue", "https://example.com/report3", "2025-09-27"),
        ("MSFT", "Barclays", "Microsoft Cloud Momentum Continues", "Azure growth continues to exceed expectations", "https://example.com/report4", "2025-09-26"),
        ("TSLA", "Deutsche Bank", "Tesla: Delivery Challenges Ahead", "Production constraints may impact Q4 deliveries", "https://example.com/report5", "2025-09-25"),
    ]

    for symbol, analyst_firm, report_title, report_summary, report_url, report_date in reports:
        cur.execute("""
            INSERT INTO research_reports
            (symbol, analyst_firm, report_title, report_summary, report_url, report_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (symbol, analyst_firm, report_title, report_summary, report_url, report_date))

    print(f"Inserted {len(reports)} research reports")

def load_analyst_estimates(cur):
    """Load sample analyst estimates data"""
    print("Loading analyst_estimates data...")

    # Clear existing data
    cur.execute("DELETE FROM analyst_estimates")

    # Sample data - matching actual schema
    estimates = [
        ("AAPL", 195.00, 170.00, 185.50, 182.00, "Buy", 2.2, 15, 2.1),
        ("MSFT", 450.00, 400.00, 425.00, 422.00, "Buy", 2.0, 12, 2.0),
        ("TSLA", 280.00, 200.00, 240.00, 235.00, "Hold", 2.8, 8, 2.7),
    ]

    for ticker, target_high, target_low, target_mean, target_median, recommendation_key, recommendation_mean, analyst_count, avg_rating in estimates:
        cur.execute("""
            INSERT INTO analyst_estimates
            (ticker, target_high_price, target_low_price, target_mean_price, target_median_price,
             recommendation_key, recommendation_mean, analyst_opinion_count, average_analyst_rating)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (ticker, target_high, target_low, target_mean, target_median, recommendation_key, recommendation_mean, analyst_count, avg_rating))

    print(f"Inserted {len(estimates)} analyst estimates")

def load_analyst_sentiment_analysis(cur):
    """Load sample analyst sentiment data"""
    print("Loading analyst_sentiment_analysis data...")

    # Clear existing data
    cur.execute("DELETE FROM analyst_sentiment_analysis")

    # Sample data - matching actual schema
    sentiment_data = [
        ("AAPL", date.today(), 2.2, 4.8, 15),
        ("AAPL", date.today() - timedelta(days=1), 2.1, 4.5, 14),
        ("AAPL", date.today() - timedelta(days=2), 2.3, 5.0, 16),
        ("MSFT", date.today(), 2.0, 5.2, 12),
        ("MSFT", date.today() - timedelta(days=1), 2.1, 5.0, 11),
        ("TSLA", date.today(), 2.8, 2.1, 8),
        ("TSLA", date.today() - timedelta(days=1), 2.7, 2.3, 9),
    ]

    for symbol, date_val, recommendation_mean, price_target_vs_current, analyst_count in sentiment_data:
        cur.execute("""
            INSERT INTO analyst_sentiment_analysis
            (symbol, date, recommendation_mean, price_target_vs_current, analyst_count)
            VALUES (%s, %s, %s, %s, %s)
        """, (symbol, date_val, recommendation_mean, price_target_vs_current, analyst_count))

    print(f"Inserted {len(sentiment_data)} sentiment analysis records")

def main():
    """Main function to load all test data"""
    print("Loading test data into analyst tables...")

    # Connect to database
    config = get_local_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()

    try:
        # Load data into all analyst tables
        load_analyst_recommendations(cur)
        load_analyst_coverage(cur)
        load_analyst_price_targets(cur)
        load_research_reports(cur)
        load_analyst_estimates(cur)
        load_analyst_sentiment_analysis(cur)

        # Commit all changes
        conn.commit()
        print("\n✅ Successfully loaded all test data!")

        # Verify data was loaded
        tables = [
            "analyst_recommendations",
            "analyst_coverage",
            "analyst_price_targets",
            "research_reports",
            "analyst_estimates",
            "analyst_sentiment_analysis"
        ]

        print("\nData verification:")
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} records")

    except Exception as e:
        print(f"❌ Error loading data: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()