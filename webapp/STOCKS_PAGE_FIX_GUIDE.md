# 🔧 Stocks Page Database Fix Guide

## 🚨 **Issue Summary**
The stocks page is returning **503 Service Unavailable** errors because:

1. **Missing Database Tables**: The application expects `stock_symbols` table but it doesn't exist
2. **AWS Permissions Issue**: Lambda can't access AWS Secrets Manager to get database credentials
3. **No Sample Data**: Even if tables existed, there's no stock data to display

## 📊 **Error Details**
```
GET /api/stocks/screen → 503 Service Unavailable
Error: "screen stocks: Database connection failed"
Error: "User: arn:aws:iam::626216981288:user/reader is not authorized to perform: secretsmanager:GetSecretValue"
```

## ✅ **Complete Solution**

### **Step 1: Fix AWS Permissions**
The Lambda function needs access to AWS Secrets Manager:

```bash
# AWS CLI command to add permissions (run by AWS admin)
aws iam attach-user-policy \
  --user-name lambda-execution-role \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite

# Or create custom policy:
aws iam put-user-policy \
  --user-name lambda-execution-role \
  --policy-name SecretsManagerAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "secretsmanager:GetSecretValue"
        ],
        "Resource": "arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-credentials-dev"
      }
    ]
  }'
```

### **Step 2: Create Required Database Tables**
Run the database setup script:

```bash
# From the lambda directory:
cd /home/stocks/algo/webapp/lambda

# Option A: Run automated setup script
scripts/run-stocks-setup.sh

# Option B: Run Node.js script directly  
node scripts/setup-stocks-database.js

# Option C: Run SQL manually
psql -h stocks-db-dev.cluster-cjmjnpvmvfqg.us-east-1.rds.amazonaws.com \
     -U your-username \
     -d financial_dashboard \
     -f scripts/setup-stock-symbols-table.sql
```

### **Step 3: Verify Database Setup**
After running the setup, verify tables exist:

```sql
-- Check if tables exist
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('stock_symbols', 'portfolio_holdings', 'trading_history', 'user_accounts');

-- Check sample data
SELECT COUNT(*) as stock_count FROM stock_symbols;
SELECT sector, COUNT(*) as companies FROM stock_symbols GROUP BY sector;
```

### **Step 4: Test API Endpoints**
Verify the fixes work:

```bash
# Test stocks sectors endpoint
curl "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/stocks/sectors"

# Test stocks screening endpoint  
curl "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/stocks/screen?page=1&limit=10"

# Test health endpoint
curl "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/health/database"
```

## 📋 **Required Tables & Sample Data**

### **Tables Created:**
1. **`stock_symbols`** - Main stocks table with 25 sample companies
2. **`portfolio_holdings`** - User portfolio positions  
3. **`trading_history`** - Trading transaction records
4. **`user_accounts`** - User account information

### **Sample Stock Data Loaded:**
- **Technology**: AAPL, MSFT, GOOGL, META, NVDA, ADBE, CRM, INTC
- **Financial Services**: JPM, V, PYPL, BAC  
- **Healthcare**: JNJ, UNH, PFE
- **Consumer**: AMZN, TSLA, HD, DIS, WMT
- **Energy**: XOM, CVX
- **Consumer Staples**: PG, KO

## 🛠️ **Files Created**

### **Database Setup Files:**
- `scripts/setup-stock-symbols-table.sql` - SQL schema and sample data
- `scripts/setup-stocks-database.js` - Node.js setup script
- `scripts/run-stocks-setup.sh` - Bash runner script

### **What Each Script Does:**
1. **SQL Script**: Creates tables with proper indexes and sample data
2. **Node.js Script**: Connects to database and executes SQL setup
3. **Bash Script**: Environment check and automated execution

## 🔍 **Troubleshooting**

### **If Setup Script Fails:**
```bash
# Check environment variables
echo "DB_ENDPOINT: $DB_ENDPOINT"
echo "DB_SECRET_ARN: $DB_SECRET_ARN"  
echo "USE_AWS_SECRETS: $USE_AWS_SECRETS"

# Test database connectivity
node -e "
const { initializeDatabase } = require('./utils/database');
initializeDatabase().then(() => console.log('✅ Connected'))
.catch(err => console.error('❌ Failed:', err.message));
"
```

### **If Permissions Issue Persists:**
1. **Contact AWS Administrator** to add Secrets Manager permissions
2. **Alternative**: Set local database credentials in `.env`:
   ```bash
   DB_HOST=localhost
   DB_PORT=5432
   DB_USER=postgres
   DB_PASSWORD=your_password
   DB_NAME=stocks
   DB_SSL=false
   USE_AWS_SECRETS=false
   ```

### **If API Still Returns 503:**
1. Check Lambda function deployment
2. Verify database connection in AWS Lambda environment
3. Check CloudWatch logs for detailed error messages
4. Ensure Lambda has VPC access to RDS database

## 🎯 **Expected Results**

After successful setup:
- ✅ Stocks page loads without 503 errors
- ✅ Stock screening works with sample data
- ✅ Sectors filtering shows Technology, Financial Services, etc.
- ✅ Database health checks pass
- ✅ Portfolio functionality works

## 📞 **Support**

If issues persist after following this guide:
1. Check AWS CloudWatch logs for Lambda function errors
2. Verify RDS database is accessible from Lambda VPC
3. Ensure database user has CREATE TABLE permissions
4. Contact AWS administrator for IAM policy updates