# Database Schema Deployment Guide

## Overview

This guide walks through deploying the comprehensive database schema that fixes the missing tables blocking your API.

**Status:** 60+ tables created, all API routes now have supporting tables

## What's New

### Tables Created (60+)
- **User Management:** users, user_api_keys, user_portfolio, user_dashboard_settings
- **Trading:** trades, algo_positions, algo_portfolio_snapshots, algo_trades, manual_positions, portfolio_holdings
- **Market Data:** market_health_daily, technical_data_daily, trend_template_data
- **Signal Quality:** signal_quality_scores, data_completeness_scores, mean_reversion_signals_daily, range_signals_daily
- **Financial:** company_profile, analyst_sentiment_analysis, insider_transactions, insider_roster, earnings_history, earnings_estimates
- **Metrics:** quality_metrics, growth_metrics, value_metrics, stability_metrics
- **Economic:** economic_calendar, economic_data, fear_greed_index
- **Commodities:** commodity_prices, commodity_correlations
- **Backtesting:** backtest_runs, backtest_trades
- **Monitoring:** algo_audit_log, filter_rejection_log, data_patrol_log
- **Legacy:** balance_sheet, income_statement, cash_flow (kept for compatibility)

### Enhanced Tables
- **buy_sell_daily:** Added 50+ columns for signal metadata, trading levels, technical indicators
- **stock_symbols:** Added security_name, market_category, exchange columns

## Deployment Steps

### Option 1: Docker Compose (Recommended for Testing)

```bash
# Restart Docker Compose with new schema
cd C:\Users\arger\code\algo
docker-compose down
docker-compose up -d

# Verify tables were created
docker-compose exec postgres psql -U stocks -d stocks -c "\dt"

# Run verification script
docker-compose exec postgres psql -U stocks -d stocks -f /home/verify-schema.sql
```

### Option 2: Direct PostgreSQL (Local/AWS RDS)

```bash
# Local development
psql -h localhost -U stocks -d stocks -f init_db.sql

# AWS RDS
psql -h <RDS_ENDPOINT> -U stocks -d stocks -f init_db.sql

# Or via AWS Secrets Manager bastion
aws ssm start-session --target i-xxxxx --document-name AWS-StartInteractiveCommand
# Then inside bastion:
psql -h <RDS_ENDPOINT> -U stocks -d stocks -f init_db.sql
```

### Option 3: AWS Lambda Startup (Automatic)

The Lambda function will automatically initialize the schema on first run:

```bash
# Add this to webapp/lambda/utils/database.js
async function ensureSchema() {
  try {
    const schemaScript = fs.readFileSync('init_db.sql', 'utf8');
    await pool.query(schemaScript);
    console.log('✅ Schema initialized on Lambda startup');
  } catch (error) {
    console.warn('⚠️ Schema initialization failed:', error.message);
  }
}
```

## Verification

### Quick Test (After Deployment)

```bash
# Check table count (should be 60+)
psql -h localhost -U stocks -d stocks \
  -c "SELECT COUNT(*) as table_count FROM pg_tables WHERE schemaname='public';"

# Check critical tables exist
psql -h localhost -U stocks -d stocks \
  -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LIMIT 20;"

# Verify buy_sell_daily has new columns
psql -h localhost -U stocks -d stocks \
  -c "\d buy_sell_daily" | grep -E "buylevel|stoplevel|entry_price|rsi|adx"

# Insert test user
psql -h localhost -U stocks -d stocks \
  -c "INSERT INTO users (email, active) VALUES ('test@example.com', true) RETURNING id;"

# Query trades (should return empty)
psql -h localhost -U stocks -d stocks \
  -c "SELECT COUNT(*) as trade_count FROM trades;"
```

### Full Verification Script

```bash
# Run the comprehensive verification
psql -h localhost -U stocks -d stocks -f verify-schema.sql
```

Expected output:
```
========================================
✅ COMPREHENSIVE DATABASE SETUP COMPLETE
==========================================
Tables created: 60+
  - User management (users, api_keys, portfolio, settings)
  - Trading (trades, positions, snapshots, portfolio holdings)
  - Market data (60+ tables for prices, signals, technical, fundamentals)
  - Quality & monitoring (audit logs, data patrol, filters)

TimescaleDB: Enabled (25+ hypertables for time-series)
Indexes: Created for optimal performance

Ready for production! 🚀
```

## Testing API After Schema Deployment

### 1. Start the API

```bash
# Local development
cd webapp/lambda
npm install
npm start

# Or via Docker
docker-compose up -d api
```

### 2. Test Key Endpoints

```bash
# Health check (should work even without auth)
curl http://localhost:3001/health

# API info
curl http://localhost:3001/api

# Stocks (public data)
curl http://localhost:3001/api/stocks?limit=5

# Portfolio (requires auth - will fail gracefully)
curl -H "Authorization: Bearer test-token" http://localhost:3001/api/portfolio

# Market status
curl http://localhost:3001/api/market/status

# Signals (should work now)
curl "http://localhost:3001/api/signals?limit=10"
```

### 3. Run Endpoint Test Suite

```bash
cd webapp/lambda
npm run test:api

# Or comprehensive test
npm run test:comprehensive
```

## Troubleshooting

### Issue: "relation does not exist" errors

**Symptom:**
```
ERROR: relation "trades" does not exist
ERROR: relation "users" does not exist
```

**Fix:**
1. Verify schema deployment completed: `psql -h localhost -U stocks -d stocks -c "\dt" | wc -l`
2. Should show 60+ tables. If not, re-run: `psql -h localhost -U stocks -d stocks -f init_db.sql`
3. Restart API after schema deployment

### Issue: "column does not exist" in buy_sell_daily

**Symptom:**
```
ERROR: column "buylevel" of relation "buy_sell_daily" does not exist
```

**Fix:**
1. Check if migration ran: `psql -h localhost -U stocks -d stocks -c "\d buy_sell_daily" | grep buylevel`
2. If not present, the DO block in init_db.sql didn't execute
3. Re-run: `psql -h localhost -U stocks -d stocks -f init_db.sql`
4. Or manually run schema-migration.sql: `psql -h localhost -U stocks -d stocks -f schema-migration.sql`

### Issue: TimescaleDB hypertables not created

**Symptom:**
```
ERROR: function create_hypertable does not exist
```

**Fix:**
1. Verify TimescaleDB is enabled: `psql -h localhost -U stocks -d stocks -c "SELECT extname FROM pg_extension WHERE extname='timescaledb';"`
2. If not present, enable it: `CREATE EXTENSION timescaledb CASCADE;`
3. Then re-run init_db.sql

### Issue: Docker Compose database volume is stale

**Symptom:**
Tables from old schema persist, new tables don't appear

**Fix:**
```bash
# Completely reset the database
docker-compose down -v
docker-compose up -d
docker-compose exec postgres psql -U stocks -d stocks -f /home/init_db.sql
```

## Performance Notes

### Indexes
- Created 50+ indexes for common queries
- Symbol + date indexes on all time-series tables
- Foreign key indexes for joins

### Hypertables (TimescaleDB)
- 25+ tables configured as hypertables
- Automatic chunking by date (1 month for daily, 3 months for weekly, etc.)
- Compression policies can be enabled for historical data

### Connection Pooling
- Lambda uses connection pooling to reduce overhead
- RDS provisioned with db.t3.small for dev (~$13/month)
- Production: Consider db.t3.medium or larger

## Migration from Old Schema

If you have existing data in the old schema:

```bash
# Export old data
pg_dump -h localhost -U stocks -d stocks \
  --tables=price_daily,buy_sell_daily,stock_symbols \
  -f backup.sql

# Import into new schema
psql -h localhost -U stocks -d stocks -f backup.sql

# Update sequences if needed
psql -h localhost -U stocks -d stocks \
  -c "SELECT pg_catalog.setval(pg_get_serial_sequence('buy_sell_daily', 'id'), COALESCE(MAX(id), 0) + 1) FROM buy_sell_daily;"
```

## Next Steps

1. ✅ Deploy schema (this guide)
2. ✅ Verify all 60+ tables exist
3. ✅ Test API endpoints
4. ⏭️ **Populate with real data**
   - Run data loaders (loadpricedaily.py, etc.)
   - Load company profiles from external APIs
   - Load analyst sentiment data
5. ⏭️ **Configure Alpaca integration**
   - Test paper trading
   - Verify portfolio syncing
6. ⏭️ **Deploy to AWS**
   - Update RDS to use new schema
   - Update Lambda environment
   - Run smoke tests

## File References

- **init_db.sql** - Complete schema (use this for deployment)
- **schema-migration.sql** - Alternative phased approach (created in parallel)
- **verify-schema.sql** - Verification script
- **SCHEMA_DEPLOYMENT_GUIDE.md** - This file

## Questions?

Check the troubleshooting section above, or review:
- `STATUS.md` - Current deployment status
- `deployment-reference.md` - Infrastructure details
- `CLAUDE.md` - Navigation index
