# Run Database Cleanup - Quick Start

## The Problem
Your local machine can't reach RDS (it's in a private VPC). You need to run the cleanup from within AWS.

## Solution: Use AWS CloudShell (Easiest)

### Step 1: Open AWS CloudShell
1. Go to AWS Console → CloudShell (top right search bar)
2. Wait for terminal to load (30 seconds)
3. You're now inside AWS with VPC access ✓

### Step 2: Clone the repo in CloudShell
```bash
cd /tmp
git clone https://github.com/your-repo/algo.git
cd algo
```

### Step 3: Get the database password
```bash
# Retrieve from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id algo/db/stocks/password \
  --region us-east-1 \
  --query 'SecretString' \
  --output text
```

Copy the output (your password).

### Step 4: Set password and audit databases
```bash
export DB_PASSWORD="paste_your_password_here"
python3 scripts/cleanup_rds_databases.py --list
```

You should see something like:
```
Found X databases:

  [EXPECTED] stocks           (owner: stocks, size: XXXX.XX MB)
  [EXTRA]    algo_trading     (owner: stocks, size: XXXX.XX MB)
  [EXTRA]    temp_db          (owner: stocks, size: XXXX.XX MB)
```

### Step 5: Remove extra databases (if any found)
```bash
export DB_PASSWORD="your_password"
python3 scripts/cleanup_rds_databases.py --clean
```

Then type `yes` when prompted to confirm deletion.

### Step 6: Verify cleanup
```bash
export DB_PASSWORD="your_password"
python3 scripts/cleanup_rds_databases.py --list
```

Should show ONLY:
```
Found 1 database:

  [EXPECTED] stocks
```

## Alternative: RDS Query Editor

If CloudShell doesn't work, use AWS Console's native RDS Query Editor:

1. Go to RDS → Databases → algo-db
2. Click "Query editor" tab
3. Run this to see all databases:
```sql
SELECT datname, pg_get_userbyid(datdba), pg_database_size(datname)
FROM pg_database
WHERE datistemplate = false
ORDER BY datname;
```

To drop a database:
```sql
DROP DATABASE IF EXISTS algo_trading;
```

## Done?
Once only `stocks` database remains, the cleanup is complete. Stock prices loader will now work correctly.
