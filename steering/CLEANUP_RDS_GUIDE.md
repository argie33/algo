# RDS Database Cleanup Guide

## Problem
Extra databases may exist in RDS that weren't created by Terraform. The correct setup should have ONLY the `stocks` database.

## Step 1: Get Your RDS Master Password

The password is stored in AWS Secrets Manager. You can retrieve it using:

```bash
# Get the secret ARN
SECRET_ARN=$(aws secretsmanager list-secrets \
  --region us-east-1 \
  --query 'SecretList[?name==`algo/db/stocks/password`].ARN' \
  --output text)

# Get the password value
aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ARN" \
  --region us-east-1 \
  --query 'SecretString' \
  --output text
```

Or if that doesn't work, use the Secrets Manager console:
1. Go to AWS Secrets Manager
2. Search for "algo/db" or "stocks"
3. Click the secret and reveal the password value

## Step 2: Run the Cleanup Script

Export the password and run the script:

```bash
export DB_PASSWORD="your_password_here"

# List all databases
python3 scripts/cleanup_rds_databases.py --list

# Drop all extra databases (will prompt for confirmation)
python3 scripts/cleanup_rds_databases.py --clean

# Or drop a specific database
python3 scripts/cleanup_rds_databases.py --drop=extra_database_name
```

## Step 3: Verify Cleanup

After cleanup, verify only the `stocks` database exists:

```bash
export DB_PASSWORD="your_password_here"
python3 scripts/cleanup_rds_databases.py --list
```

You should see:
- `[EXPECTED] stocks` (the one and only database)

## Expected Outcome

- ✅ Only `stocks` database should exist
- ✅ No `algo_trading` or other stray databases
- ✅ All loaders and orchestrator will use the correct database

## Troubleshooting

### Can't connect to RDS
- The local machine might not have RDS network access
- You may need to run this from within AWS (CloudShell, EC2, Lambda)
- Or use AWS RDS Query Editor from the console

### Permission Denied
- Make sure you're using the master username (`stocks`)
- Verify the password is correct
- Check that your IAM user has RDS access

### What if I don't know the password?
- Use AWS Secrets Manager to retrieve it (see Step 1)
- Or create a new master password via RDS console (caution: may require reboot)
