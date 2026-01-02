#!/usr/bin/env python3
# Economic data loader - Fed data, inflation, employment, GDP
# Trigger deploy-app-stocks workflow - loadecondata v4.6 - EXPANDED FRED SERIES + RECESSION INDICATORS - DEPLOY NOW
# Trigger: 20251220-FINAL - Update stale economic_data after infrastructure deployment 
import sys
import os
import json
import logging
import requests
from datetime import datetime, timedelta

import boto3
import pandas as pd
from fredapi import Fred
import psycopg2
from psycopg2.extras import execute_values

# ─── Logging setup ───────────────────────────────────────────────────────────────
# Send all INFO+ logs to stdout so awslogs picks them up
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger()

# ─── Environment variables ──────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")
FRED_API_KEY  = os.environ.get("FRED_API_KEY")

def get_db_creds():
    """Fetch DB creds from Secrets Manager or environment variables."""
    # First, try to use AWS Secrets Manager (for production/Lambda)
    if DB_SECRET_ARN:
        try:
            sm = boto3.client("secretsmanager")
            resp = sm.get_secret_value(SecretId=DB_SECRET_ARN)
            sec = json.loads(resp["SecretString"])
            return {
                "user": sec["username"],
                "password": sec["password"],
                "host": sec["host"],
                "port": int(sec["port"]),
                "dbname": sec["dbname"],
                "sslmode": "require"
            }
        except Exception as e:
            logger.warning(f"Failed to fetch from Secrets Manager: {e}, falling back to environment variables")

    # Fall back to environment variables or Unix socket
    if os.environ.get("DB_HOST"):
        return {
            "user": os.environ.get("DB_USER", "stocks"),
            "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "dbname": os.environ.get("DB_NAME", "stocks"),
            "sslmode": "disable"
        }
    else:
        # Use Unix socket connection (works locally without password)
        logger.info("Using Unix socket connection")
        return {
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

def get_economic_calendar_data():
    """Fetch economic calendar events - tries FRED API first, falls back to scheduled events."""
    try:
        fred_events = []
        scheduled_events = []

        # Try to fetch FRED releases data if API key is available
        if FRED_API_KEY:
            logger.info("Fetching FRED API calendar events...")
            fred_events = get_fred_release_calendar()
            if fred_events:
                logger.info(f"✓ Loaded {len(fred_events)} FRED calendar events from API")
        else:
            logger.warning("⚠️ FRED_API_KEY not set - using scheduled economic events only")
            logger.info("   Get free FRED API key at: https://fredaccount.stlouisfed.org/login")

        # Always include scheduled economic events as baseline
        scheduled_events = get_scheduled_economic_events()
        if scheduled_events:
            logger.info(f"✓ Loaded {len(scheduled_events)} scheduled economic events")

        # Combine events, removing duplicates by event name + date
        all_events = fred_events + scheduled_events
        seen_keys = set()
        unique_events = []

        for event in all_events:
            key = (event['Event'], event['Date'])
            if key not in seen_keys:
                seen_keys.add(key)
                unique_events.append(event)

        if unique_events:
            logger.info(f"✓ Total {len(unique_events)} unique calendar events loaded")
            return unique_events
        else:
            logger.warning("❌ No calendar events loaded from any source")
            return []

    except Exception as e:
        logger.error(f"Failed to fetch economic calendar data: {e}")
        return []

def get_fred_release_calendar():
    """Get upcoming economic releases from FRED API (completely free)."""
    try:
        # Check if FRED API key is available
        if not FRED_API_KEY:
            logger.warning("FRED_API_KEY not set - skipping FRED release calendar")
            return []

        # FRED releases/dates endpoint
        url = "https://api.stlouisfed.org/fred/releases/dates"
        params = {
            'api_key': FRED_API_KEY,
            'file_type': 'json',
            'include_release_dates_with_no_data': 'true',  # Include future dates
            'limit': '50'
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        if 'release_dates' not in data:
            logger.warning("No release_dates in FRED response")
            return []

        events = []
        today = datetime.now().date()

        for release in data['release_dates']:
            release_date = datetime.strptime(release['date'], '%Y-%m-%d').date()

            # Only include future dates within next 90 days
            if release_date >= today and release_date <= today + timedelta(days=90):
                event = {
                    'Event': release.get('release_name', 'Economic Release'),
                    'Date': release['date'],
                    'Time': '08:30',  # Most releases are at 8:30 AM
                    'Country': 'United States',
                    'Category': categorize_fred_release(release.get('release_name', '')),
                    'Importance': get_fred_importance(release.get('release_name', '')),
                    'Currency': 'USD',
                    'Forecast': 'TBD',
                    'Previous': 'See FRED data',
                    'Unit': '',
                    'Frequency': 'Monthly',
                    'Source': 'Federal Reserve Economic Data (FRED)'
                }
                events.append(event)

        logger.info(f"✓ Found {len(events)} upcoming FRED releases")
        return events

    except Exception as e:
        logger.error(f"Failed to fetch FRED release calendar: {e}")
        return []

def get_scraped_calendar_data():
    """Get economic calendar data from free scraper source."""
    try:
        # Use the open source economic calendar API
        url = "https://api.investing.com/api/financialdata/economic/calendar"
        
        # Alternative: try the GitHub open source scraper
        scraper_url = "https://economic-calendar-api.herokuapp.com/api/events"
        
        # For now, let's use a simple approach - just add some key recurring events
        return get_scheduled_economic_events()
        
    except Exception as e:
        logger.error(f"Failed to scrape calendar data: {e}")
        return []

def get_scheduled_economic_events():
    """Generate upcoming economic events based on known schedules."""
    events = []
    today = datetime.now().date()
    
    # FOMC meetings (8 per year, roughly every 6-7 weeks)
    fomc_dates = get_next_fomc_dates(today)
    for date in fomc_dates:
        events.append({
            'Event': 'FOMC Rate Decision',
            'Date': date.strftime('%Y-%m-%d'),
            'Time': '14:00',
            'Country': 'United States',
            'Category': 'monetary_policy',
            'Importance': 'High',
            'Currency': 'USD',
            'Forecast': 'Market expectations vary',
            'Previous': '5.25-5.50%',
            'Unit': '%',
            'Frequency': 'Irregular',
            'Source': 'Federal Reserve'
        })
    
    # Monthly employment report (first Friday of month)
    employment_dates = get_next_employment_dates(today)
    for date in employment_dates:
        events.append({
            'Event': 'Nonfarm Payrolls',
            'Date': date.strftime('%Y-%m-%d'),
            'Time': '08:30',
            'Country': 'United States',
            'Category': 'employment',
            'Importance': 'High',
            'Currency': 'USD',
            'Forecast': 'Estimate varies',
            'Previous': '227K',
            'Unit': 'K',
            'Frequency': 'Monthly',
            'Source': 'Bureau of Labor Statistics'
        })
    
    # CPI releases (around 10th-15th of month)
    cpi_dates = get_next_cpi_dates(today)
    for date in cpi_dates:
        events.append({
            'Event': 'Consumer Price Index',
            'Date': date.strftime('%Y-%m-%d'),
            'Time': '08:30',
            'Country': 'United States',
            'Category': 'inflation',
            'Importance': 'High',
            'Currency': 'USD',
            'Forecast': 'Estimate varies',
            'Previous': '2.6% Y/Y',
            'Unit': '%',
            'Frequency': 'Monthly',
            'Source': 'Bureau of Labor Statistics'
        })
    
    return events
def process_calendar_events(events):
    """Process raw calendar events into standardized format."""
    processed = []
    
    for event in events:
        try:
            processed_event = {
                'Event': event.get('Event', 'Unknown Event'),
                'Date': event.get('Date', datetime.now().strftime('%Y-%m-%d')),
                'Time': event.get('Time', ''),
                'Country': event.get('Country', 'United States'),
                'Category': categorize_event(event.get('Event', '')),
                'Importance': event.get('Importance', 'Medium'),
                'Currency': event.get('Currency', 'USD'),
                'Forecast': event.get('Forecast', ''),
                'Previous': event.get('Previous', ''),
                'Actual': event.get('Actual', ''),
                'Unit': event.get('Unit', ''),
                'Frequency': event.get('Frequency', 'Monthly'),
                'Source': event.get('Source', '')
            }
            processed.append(processed_event)
        except Exception as e:
            logger.warning(f"Error processing event: {e}")
            continue
    
    return processed

def categorize_event(event_name):
    """Categorize economic event based on name."""
    event_lower = event_name.lower()
    
    if any(term in event_lower for term in ['fed', 'interest', 'rate', 'fomc', 'monetary']):
        return 'monetary_policy'
    elif any(term in event_lower for term in ['employment', 'payroll', 'jobs', 'unemployment']):
        return 'employment'
    elif any(term in event_lower for term in ['cpi', 'ppi', 'inflation', 'price']):
        return 'inflation'
    elif any(term in event_lower for term in ['gdp', 'growth', 'economic']):
        return 'gdp'
    elif any(term in event_lower for term in ['housing', 'home', 'construction']):
        return 'housing'
    elif any(term in event_lower for term in ['manufacturing', 'factory', 'industrial']):
        return 'manufacturing'
    elif any(term in event_lower for term in ['consumer', 'retail', 'spending']):
        return 'consumer'
    else:
        return 'other'

def categorize_fred_release(release_name):
    """Categorize FRED release based on name."""
    return categorize_event(release_name)

def get_fred_importance(release_name):
    """Determine importance of FRED release."""
    release_lower = release_name.lower()
    
    high_importance = ['employment', 'payroll', 'cpi', 'inflation', 'gdp', 'fomc', 'interest']
    if any(term in release_lower for term in high_importance):
        return 'High'
    
    medium_importance = ['housing', 'manufacturing', 'retail', 'consumer']
    if any(term in release_lower for term in medium_importance):
        return 'Medium'
    
    return 'Low'

def get_next_fomc_dates(today):
    """Get next FOMC meeting dates (8 meetings per year)."""
    # FOMC meetings are roughly every 6-7 weeks
    # 2025 FOMC dates: Jan 28-29, Mar 18-19, Apr 29-30, Jun 10-11, Jul 29-30, Sep 16-17, Oct 31-Nov 1, Dec 16-17
    fomc_2025_dates = [
        datetime(2025, 1, 29).date(),
        datetime(2025, 3, 19).date(),
        datetime(2025, 4, 30).date(),
        datetime(2025, 6, 11).date(),
        datetime(2025, 7, 30).date(),
        datetime(2025, 9, 17).date(),
        datetime(2025, 11, 1).date(),
        datetime(2025, 12, 17).date()
    ]
    
    # Return dates that are in the future and within 90 days
    return [date for date in fomc_2025_dates
            if date >= today and date <= today + timedelta(days=90)]

def get_next_employment_dates(today):
    """Get next employment report dates (first Friday of each month)."""
    dates = []
    current_date = today
    
    for i in range(3):  # Get next 3 months
        # Find first Friday of the month
        year = current_date.year
        month = current_date.month
        
        # First day of month
        first_day = datetime(year, month, 1).date()
        
        # Find first Friday (weekday 4)
        days_until_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_until_friday)
        
        if first_friday >= today and first_friday <= today + timedelta(days=90):
            dates.append(first_friday)
        
        # Move to next month
        if month == 12:
            current_date = datetime(year + 1, 1, 1).date()
        else:
            current_date = datetime(year, month + 1, 1).date()
    
    return dates

def get_next_cpi_dates(today):
    """Get next CPI release dates (around 10th-15th of each month)."""
    dates = []
    current_date = today
    
    for i in range(3):  # Get next 3 months
        year = current_date.year
        month = current_date.month
        
        # CPI is usually released around the 13th of the month
        cpi_date = datetime(year, month, 13).date()
        
        # Adjust if it falls on weekend
        while cpi_date.weekday() >= 5:  # Saturday or Sunday
            cpi_date += timedelta(days=1)
        
        if cpi_date >= today and cpi_date <= today + timedelta(days=90):
            dates.append(cpi_date)
        
        # Move to next month
        if month == 12:
            current_date = datetime(year + 1, 1, 1).date()
        else:
            current_date = datetime(year, month + 1, 1).date()
    
    return dates

def handler(event, context):
    try:
        # Check FRED API key - if not set, use fallback methods
        if not FRED_API_KEY:
            logger.warning("⚠️ FRED_API_KEY not set - using fallback calendar methods only")
        else:
            logger.info("✓ FRED_API_KEY found - will fetch full economic calendar")

        # 1) Connect
        conn_params = get_db_creds()
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor()

        # 2) Ensure tables exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS economic_data (
                series_id TEXT NOT NULL,
                date       DATE NOT NULL,
                value      DOUBLE PRECISION,
                PRIMARY KEY (series_id, date)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS economic_calendar (
                id SERIAL PRIMARY KEY,
                event_id VARCHAR(50) UNIQUE,
                event_name VARCHAR(255) NOT NULL,
                country VARCHAR(10) DEFAULT 'US',
                category VARCHAR(100),
                importance VARCHAR(20) NOT NULL,
                currency VARCHAR(3) DEFAULT 'USD',
                event_date DATE NOT NULL,
                event_time TIME,
                timezone VARCHAR(50) DEFAULT 'America/New_York',
                actual_value VARCHAR(100),
                forecast_value VARCHAR(100),
                previous_value VARCHAR(100),
                unit VARCHAR(50),
                frequency VARCHAR(20),
                source VARCHAR(100),
                description TEXT,
                impact_analysis TEXT,
                is_revised BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        # 3) Series list
        series_ids = [
            # — U.S. Output & Demand —
            "GDPC1","PCECC96","GPDI","GCEC1","EXPGSC1","IMPGSC1",
            # — U.S. Labor Market —
            "UNRATE","PAYEMS","CIVPART","CES0500000003","AWHAE","JTSJOL","ICSA","OPHNFB","U6RATE",
            # — U.S. Inflation & Prices —
            "CPIAUCSL","CPILFESL","PCEPI","PCEPILFE","PPIACO","MICH","T5YIFR",
            # — Energy & Commodities —
            "DCOILWTICO",
            # — U.S. Financial & Monetary —
            "FEDFUNDS","DGS3MO","DGS6MO","DGS1","DGS2","DGS3","DGS5","DGS7","DGS10","DGS20","DGS30",
            "T10Y2Y","MORTGAGE30US","BAA","AAA","SP500","VIXCLS","M1NS","M2SL","WALCL","IOER","IORB",
            # — S&P 500 Earnings & Valuation —
            "SPASTT01USQ661S","SP500PE",
            # — Credit Spreads (indicators of financial stress) —
            "BAMLH0A0HYM2","BAMLH0A1HYBB","BAMLH0A2HY","BAMLH0A0IG","BAMLH0A1IG","BAMLH0A2IG",
            # — Treasury Spreads (recession indicators) —
            "T10Y3M","T10Y3MM","T10YIE","T5YIFR",
            # — Alternative Financial Conditions —
            "TERMCBCCALLNS","TERMCBCCRMNRNRNXBD",
            # — U.S. Housing & Construction —
            "HOUST","PERMIT","CSUSHPISA","RHORUSQ156N","RRVRUSQ156N","USHVAC",
            # — Manufacturing & Production (ISM/Capacity) —
            "INDPRO","CUMFSL","A371RE1Q156NBEA",
            # — LAGGING ECONOMIC INDICATORS —
            "UEMPMEAN","PRIME","MMNRNJ","ISITC","TOTALSA","IMPGS","LBMVRTQ",
            # — COINCIDENT ECONOMIC INDICATORS —
            "UMCSENT","RSXFS","EMSRATIO"
        ]

        # Initialize FRED client if API key is available
        fred = None
        if FRED_API_KEY:
            try:
                fred = Fred(api_key=FRED_API_KEY)
                logger.info("✓ FRED API initialized")
            except Exception as e:
                logger.error(f"Failed to initialize FRED: {e}")
                fred = None
        else:
            logger.info("FRED_API_KEY not set, skipping FRED data fetching")

        # 4) Fetch & upsert each series
        if fred:
            for sid in series_ids:
                logger.info(f"Fetching {sid} …")
                try:
                    ts = fred.get_series(sid)
                except Exception as e:
                    logger.error(f"Failed to fetch {sid}: {e}")
                    continue

                if ts is None or ts.empty:
                    logger.warning(f"No data for {sid}")
                    continue

                ts = ts.dropna()
                rows = [(sid, pd.to_datetime(dt).date(), float(val)) for dt, val in ts.items()]

                # bulk upsert
                execute_values(
                    cur,
                    """
                    INSERT INTO economic_data (series_id, date, value)
                    VALUES %s
                    ON CONFLICT (series_id, date) DO UPDATE
                      SET value = EXCLUDED.value;
                    """,
                    rows
                )
                conn.commit()
                logger.info(f"✓ {len(rows)} rows upserted for {sid}")
        else:
            logger.warning("⚠️ Skipping FRED data fetching - no API key available")

        # 5) Load economic calendar data
        logger.info("Loading economic calendar data...")
        try:
            calendar_events = get_economic_calendar_data()
            
            # Clear existing future events to avoid duplicates
            cur.execute("DELETE FROM economic_calendar WHERE event_date >= CURRENT_DATE")
            
            # Insert new calendar events
            for event in calendar_events:
                event_id = f"{event['Event']}_{event['Date']}"[:50]  # Limit to 50 chars
                
                # Convert time string (HH:MM) to proper format if it's not None
                event_time = event['Time'] if event['Time'] else None

                cur.execute("""
                    INSERT INTO economic_calendar (
                        event_id, event_name, country, category, importance, currency,
                        event_date, event_time, timezone, forecast_value, previous_value,
                        unit, frequency, source, description, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (event_id) DO UPDATE SET
                        event_name = EXCLUDED.event_name,
                        category = EXCLUDED.category,
                        importance = EXCLUDED.importance,
                        event_date = EXCLUDED.event_date,
                        event_time = EXCLUDED.event_time,
                        forecast_value = EXCLUDED.forecast_value,
                        previous_value = EXCLUDED.previous_value,
                        unit = EXCLUDED.unit,
                        frequency = EXCLUDED.frequency,
                        source = EXCLUDED.source,
                        description = EXCLUDED.description,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    event_id,
                    event['Event'],
                    'US',
                    event['Category'],
                    event['Importance'],
                    event['Currency'],
                    event['Date'],
                    event_time,
                    'America/New_York',
                    event['Forecast'],
                    event['Previous'],
                    event['Unit'],
                    event['Frequency'],
                    event['Source'],
                    f"Expected: {event['Forecast']}, Previous: {event['Previous']}"
                ))
            
            conn.commit()
            logger.info(f"✓ {len(calendar_events)} calendar events loaded")
            
        except Exception as e:
            logger.error(f"Failed to load economic calendar data: {e}")
            # Don't fail the entire process if calendar loading fails
            conn.rollback()

        # 6) Clean up
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({"status": "success"})
        }

    except Exception as e:
        logger.exception("loadecondata failed")
        # if conn was opened, attempt to close
        try:
            cur.close()
            conn.close()
        except Exception as close_error:
            logger.warning(f"Failed to close database connection after error: {str(close_error)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


if __name__ == "__main__":
    # When run as a standalone script (e.g. via "python loadecondata.py"),
    # invoke the handler so all your logging executes.
    result = handler({}, None)
    # Print the result so you can see success/failure in the logs.
    print(json.dumps(result))
    sys.stdout.flush()
