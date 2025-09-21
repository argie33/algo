# AWS Lambda Deployment Checklist

## Environment Variables Required for AWS Lambda

### Database Configuration
Set ONE of the following options:

**Option 1: AWS Secrets Manager (Recommended for Production)**
```bash
DB_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:your-secret-name
```

**Option 2: Direct Environment Variables (Development/Testing)**
```bash
DB_HOST=your-rds-endpoint.amazonaws.com
DB_PORT=5432
DB_NAME=stocks
DB_USER=your-username
DB_PASSWORD=your-password
```

### Authentication Configuration

**For Development/Testing (Public Endpoints)**
```bash
AWS_LAMBDA_DEV_MODE=true
NODE_ENV=development
```

**For Production**
```bash
COGNITO_USER_POOL_ID=your-pool-id
COGNITO_CLIENT_ID=your-client-id
COGNITO_REGION=us-east-1
```

### Other Required Variables
```bash
AWS_REGION=us-east-1
WEBAPP_AWS_REGION=us-east-1
```

## Pre-Deployment Tests

All critical endpoints verified:
- ✅ 16/16 routes passing
- ✅ Real data from loader script tables (no null values)
- ✅ SQL syntax compatible with PostgreSQL
- ✅ Authentication bypass working for public endpoints
- ✅ Error handling and 404 responses working

## Database Tables Required

Ensure these tables exist and are populated:
- `stock_prices` (primary price data)
- `technical_data_daily` (RSI, MACD, SMA data)
- `company_profile` (company information)
- `market_data` (market cap, volume data)
- `buy_sell_daily` (trading signals)

## Known Working Configuration

Local development confirmed working with:
- Database: localhost:5432/stocks
- Authentication: Development mode bypass enabled
- All 16 critical API endpoints responding correctly

## Critical Fixes Applied

1. **SQL Syntax Errors Fixed**: Resolved "syntax error at or near WHERE" in metrics and scores endpoints
2. **Database Table Alignment**: Fixed empty `price_daily` references to use populated `stock_prices`
3. **Real Data Integration**: All endpoints now return actual financial data instead of null values
4. **PostgreSQL Compatibility**: Fixed ROUND function and column name mismatches

## AWS Lambda Specific Notes

- Set `AWS_LAMBDA_DEV_MODE=true` for public endpoint access without authentication
- Ensure database connection pool limits are appropriate for Lambda (max: 3, min: 1)
- Verify Secrets Manager permissions if using DB_SECRET_ARN
- All SQL queries optimized for AWS RDS PostgreSQL compatibility