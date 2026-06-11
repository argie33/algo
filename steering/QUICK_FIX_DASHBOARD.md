# Quick Fix: Missing Dashboard Data

## The Problem (30 seconds)
Your dashboard shows "no data" because it's using **LOCAL database** (localhost) instead of **AWS RDS** where the real data lives.

## The Fix (2 minutes)

### Step 1: Switch to AWS Database
```powershell
# Run this ONE command:
.\scripts\setup-database-config.ps1 -UseAWS
```

This will:
- Get AWS credentials
- Connect to AWS RDS (algo-db.cvjv6oql86ak.us-east-1.rds.amazonaws.com)
- Update your configuration

### Step 2: Verify Configuration
```powershell
# Check it worked:
.\scripts\setup-database-config.ps1 -Show
```

You should see:
```
Target:  AWS-RDS
DB_HOST: algo-db.cvjv6oql86ak.us-east-1.rds.amazonaws.com
```

### Step 3: Refresh Dashboard
- Close and reopen your browser tab
- Wait a few seconds for data to load
- Should now see portfolio data, performance metrics, etc.

## Done!
If data appears → **Problem solved!**

If data still missing → See troubleshooting below

---

## Troubleshooting

### "AWS credentials not available"
→ Run: `.\scripts\refresh-aws-credentials.ps1`
→ Then retry: `.\scripts\setup-database-config.ps1 -UseAWS`

### "Could not connect to AWS RDS"  
→ Your security group may block your IP
→ Check AWS Console → RDS → Security Groups
→ Add your IP or contact team lead

### Data still shows as empty
→ Loaders may not have run yet
→ Run: `python scripts/diagnose-dashboard-data.py`
→ See FIX_DASHBOARD_DATA.md for details

---

## What Just Changed?
- **Before:** Using local database (stocks@localhost)
- **After:** Using AWS RDS (algo_trades@aws-rds)
- **Result:** Dashboard now connects to live data that loaders update every day

## Want to Go Back to Local?
```powershell
.\scripts\setup-database-config.ps1 -UseLocal
```

---

## Files Created to Fix This
1. `scripts/setup-database-config.ps1` - Switch between local and AWS
2. `scripts/apply-database-schema.py` - Initialize local database
3. `scripts/diagnose-dashboard-data.py` - Check data availability
4. `FIX_DASHBOARD_DATA.md` - Detailed explanation
5. `DASHBOARD_DATA_WIRING.md` - Architecture docs

All ready to use. Enjoy your dashboard! 🎉
