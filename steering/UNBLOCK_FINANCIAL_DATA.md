# CRITICAL: Unblock Financial Data - Migration 0044

## Status Report
- ❌ Financial data NOT visible (quality_score, growth_score, positioning_score all NULL)
- ❌ Stock scores NOT computing (metric loaders blocked)
- ❌ Critical data gap NOT resolved (RDS missing schema columns)
- ⏳ Migration 0044 never applied (shows "✅ success" but was never executed)

## Root Cause
Migration 0044 was marked complete in AWS deployment but never actually applied to RDS. The `quality_metrics` table is missing the `quality_score` column required by metric loaders.

## The Fix (Choose One Method)

### Method 1: AWS CloudShell (Recommended - 1 minute)
1. AWS Console → Search "CloudShell" → Open
2. Paste this command:
```bash
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(
    host="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
    port=5432, database="algo_prod", user="algo_admin",
    password="4$6QcbvV)vU(2G]hKEiY2mnj3L}>9Mxe", sslmode='require'
)
conn.autocommit = True
cur = conn.cursor()
cur.execute("ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets DECIMAL(8, 4);")
cur.execute("ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quality_score DECIMAL(5, 2);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_quality_metrics_quality_score ON quality_metrics(quality_score DESC);")
print("✓ Migration applied!")
cur.close()
conn.close()
EOF
```
3. Press Enter, wait for "✓ Migration applied!" message

### Method 2: RDS Query Editor
1. AWS Console → RDS → algo-db → Query Editor
2. Connect as `algo_admin` to `algo_prod`
3. Execute:
```sql
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets DECIMAL(8, 4);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quality_score DECIMAL(5, 2);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_quality_score ON quality_metrics(quality_score DESC);
```

### Method 3: Terraform
```bash
cd terraform
terraform apply \
  -var="rds_password=4\$6QcbvV)vU(2G]hKEiY2mnj3L}>9Mxe" \
  -target=postgresql_query.add_debt_to_assets \
  -target=postgresql_query.add_quality_score \
  -target=postgresql_query.create_quality_score_index
```

## After Migration
Financial data flows automatically via EventBridge (4 AM, 9:30 AM, 5:30 PM ET). To verify immediately:
```bash
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores?limit=3"
```
Should return non-NULL quality_score, growth_score, positioning_score values.

## Impact
This single action unblocks:
- Metric loaders writing financial data
- API returning populated scores
- Dashboard showing complete information
- User goal: seeing financial data
