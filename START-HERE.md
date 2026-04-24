# Load Data Locally - Quick Start

You have 59 AWS-integrated loaders ready to go. Use them locally first, then push to AWS.

## ⚡ 30-Second Start

```bash
# 1. Make sure database is running
pg_isready -h localhost -p 5432

# 2. Initialize schema (one time only)
python3 init_database.py

# 3. Run all loaders
python3 run-loaders.py
```

That's it. The orchestrator will:
- Run loaders in correct dependency order
- Track progress automatically
- Skip loaders that already completed
- Continue on non-critical failures
- Show summary when done

## 📊 Timeline

- **Critical loaders only** (symbols + prices): ~45 minutes
- **Full load** (all 9 loaders): ~2-4 hours
- **Can pause/resume**: Stop anytime, run again to continue

## 🎯 Common Commands

```bash
# Skip critical loaders, load all extras
python3 run-loaders.py

# Just symbols and prices (for quick testing)
python3 run-loaders.py --critical-only

# Run specific loader only
python3 run-loaders.py --loader loadstocksymbols.py

# Force restart from beginning
python3 run-loaders.py --reset-progress

# View what completed
cat .loader-progress.json
```

## ✅ Verify It Works

```bash
# Connect to database
psql -U stocks -d stocks

# Check record counts
SELECT COUNT(*) FROM stock_symbols;
SELECT COUNT(*) FROM price_daily;
SELECT COUNT(*) FROM company_profile;

# Exit
\q
```

## 🚀 Ready for AWS?

Once local tests pass, same loaders work on AWS:

1. Use AWS RDS credentials instead of local
2. Run `python3 init_database.py` on AWS (optional, usually exists)
3. Run `python3 run-loaders.py` with AWS database
4. Deploy loaders to AWS ECS/Lambda

## 📚 Full Documentation

See `LOADER-SETUP.md` for:
- Detailed loader descriptions
- Troubleshooting guide
- Performance tuning
- Dependency diagram
- AWS deployment steps

## ⚠️ Important Notes

- **Database must be running** - loaders can't start otherwise
- **Loaders use yfinance (free)** - no API keys needed, but has rate limits
- **Progress is saved** - can pause/resume safely
- **Non-critical failures don't block** - only critical loaders abort on error
- **Tests locally first** - always run locally before pushing to AWS

## 🔧 Troubleshooting

**"Connection refused"**
```bash
pg_isready -h localhost -p 5432
# If not ready, start PostgreSQL
postgres -D /var/lib/postgresql/data
```

**"Loader times out"**
- Check network: `ping yahoo.com`
- Increase timeout in run-loaders.py if needed
- Can re-run, will resume from where it stopped

**"Table doesn't exist"**
```bash
# Re-run initialization
python3 init_database.py
```

---

**Ready? Run this:**
```bash
python3 run-loaders.py
```
