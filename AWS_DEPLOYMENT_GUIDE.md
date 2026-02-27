# 🚀 AWS DEPLOYMENT GUIDE - QUICK START

## Current Status
✅ Local Data: 4,989 symbols with 13,979 signals + scores
✅ Export Ready: Database prepared for sync
✅ Script Ready: Automated deployment available

---

## 3 DEPLOYMENT OPTIONS

### OPTION 1: Interactive Script (EASIEST)
```bash
bash /home/arger/algo/DEPLOY_TO_AWS.sh
```
- Asks for RDS endpoint
- Exports + uploads automatically  
- Verifies data in AWS

### OPTION 2: Manual Steps (FULL CONTROL)
```bash
# Step 1: Export local database
PGPASSWORD=bed0elAn pg_dump -h localhost -U stocks -d stocks -F p > /tmp/stocks.sql

# Step 2: Get RDS endpoint from AWS Console
# AWS → RDS → Databases → stocks → Endpoint

# Step 3: Restore to AWS
PGPASSWORD=<RDS_PASSWORD> psql -h <RDS_ENDPOINT> -U stocks -d stocks < /tmp/stocks.sql

# Step 4: Verify
PGPASSWORD=<RDS_PASSWORD> psql -h <RDS_ENDPOINT> -U stocks -d stocks -c \
  "SELECT COUNT(*) FROM buy_sell_daily"
# Should return: 13979
```

### OPTION 3: AWS CloudShell (BEST)
From AWS CloudShell (has AWS CLI + credentials):
```bash
aws rds describe-db-instances --region us-east-1 \
  --query 'DBInstances[?DBInstanceIdentifier==`stocks`].Endpoint.Address' \
  --output text
# Copy the endpoint, then run OPTION 2 above
```

---

## 🎯 WHAT YOU NEED

1. **RDS Endpoint**
   - Find in AWS Console: RDS → Databases → stocks
   - Format: `stocks-xxxxx.us-east-1.rds.amazonaws.com`

2. **RDS Username & Password**
   - Usually: stocks / [your password]
   - Or from AWS Secrets Manager

3. **Network Access**
   - RDS security group must allow your IP
   - Or run from AWS CloudShell (no IP restrictions)

---

## 📊 DATA BEING DEPLOYED

- Stock Symbols: 4,989
- Buy/Sell Signals: 13,979 records (4,989 symbols)
- Stock Scores: 4,989
- Daily Prices: 22.4M records
- Quality Metrics: 4,989
- All technical indicators

Total size: ~1-2GB

---

## ⏱️ TIMING

- Export: 5-10 minutes
- Upload: 10-15 minutes (depends on internet)
- Verify: 2-3 minutes
- **Total: 20-30 minutes**

---

## ✨ NEXT STEPS

1. **Get RDS Endpoint** from AWS Console
2. **Choose deployment option** (1, 2, or 3 above)
3. **Run deployment**
4. **Verify data** in AWS
5. **Update Lambda** to use AWS RDS
6. **Test API** against AWS data
7. **Deploy to production!**

---

**Ready when you are!** 🚀

