# Run TimescaleDB Setup Now (Windows)

## What to Do Right Now

You're on **Windows** with **Docker Desktop**. Run this one command in PowerShell:

```powershell
cd C:\Users\arger\code\algo
& ".\setup_timescaledb_local.bat"
```

That's it. It will:
1. Stop any running database
2. Start PostgreSQL 15 with TimescaleDB (from docker-compose)
3. Wait for it to come online
4. Initialize schema (create tables)
5. Apply TimescaleDB migration (convert to hypertables)
6. Run benchmarks (show speedups)

**Expected time:** 2-3 minutes

---

## What Happens Step-by-Step

### Step 1: Docker Compose Down
```
Stopping existing containers...
```

### Step 2: Docker Compose Up
```
Starting PostgreSQL 15 with TimescaleDB...
Creating stocks_postgres_local ... done
```

### Step 3: Wait for Database
```
Waiting for database to start (30 seconds)...
```

### Step 4: Verify Connection
```
✓ Database is online
```

You'll see:
```
PostgreSQL 15.x on ...
```

### Step 5: Initialize Schema
```
Schema already initialized (45 tables)
```

Or if first time:
```
Running init_database.py...
```

### Step 6: Apply Migration
```
✓ Connected to stocks@localhost
✓ TimescaleDB extension created/enabled

Converting tables to hypertables...
✓ price_daily: converted to hypertable (chunk: 7 days)
✓ price_weekly: converted to hypertable (chunk: 12 weeks)
...
✓ Migration completed successfully!
```

### Step 7: Run Benchmarks
```
✓ Query 1: Recent price data (7 days): 45.2ms
✓ Query 2: 90-day aggregation: 82.5ms
✓ Query 3: Multi-symbol comparison: 156.3ms
...
Average query time: 87.4ms
```

---

## If Something Goes Wrong

### Error: `docker-compose: command not found`
→ Docker Desktop isn't installed or not in PATH  
→ Install from https://www.docker.com/products/docker-desktop

### Error: `psql: command not found`
→ This is OK - the script doesn't need psql installed  
→ Continue, the script will still work

### Error: `Failed to connect to database`
→ Wait 60 seconds (database startup is slow first time)  
→ Run script again: `.\setup_timescaledb_local.bat`

### Error: `ModuleNotFoundError: No module named 'psycopg2'`
→ Install it: `pip install psycopg2-binary python-dotenv`  
→ Run script again

### Container won't stop
```powershell
docker-compose -f docker-compose.local.yml rm -f
```

### See what's running
```powershell
docker ps
# Should show: stocks_postgres_local
```

### Check logs
```powershell
docker-compose -f docker-compose.local.yml logs postgres
```

---

## After Setup Works Locally

Once you see the benchmarks output, you're done with local setup. 

**Next:** Deploy to AWS RDS:

```bash
cd terraform
terraform plan -target=aws_db_parameter_group.main
terraform apply -target=aws_db_parameter_group.main
```

This updates RDS parameters and reboots the instance (30-60 sec downtime).

Then run the same migration on RDS:

```bash
# Update .env.local with your RDS endpoint
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PASSWORD=<your-rds-password>

python migrate_timescaledb.py
python test_timescaledb_performance.py
```

---

## Verify Everything Worked

Once running, check:

```sql
-- Connect to database
psql -h localhost -U stocks -d stocks

-- List hypertables
SELECT hypertable_name, num_chunks
FROM timescaledb_information.hypertables;

-- Check compression
SELECT * FROM timescaledb_information.compression_policies;

-- Check query performance
EXPLAIN ANALYZE
SELECT symbol, AVG(close)
FROM price_daily
WHERE date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY symbol;
```

You should see:
- 12 hypertables created
- 12 compression policies active
- Query plan using "Gather" for parallel workers

---

## Commands Reference

| What | Command |
|------|---------|
| Start database | `docker-compose -f docker-compose.local.yml up -d postgres` |
| Stop database | `docker-compose -f docker-compose.local.yml down` |
| View logs | `docker-compose -f docker-compose.local.yml logs postgres` |
| Connect with psql | `psql -h localhost -U stocks -d stocks` |
| Run migration | `python migrate_timescaledb.py` |
| Run benchmarks | `python test_timescaledb_performance.py` |
| Check container | `docker ps` |
| Remove container | `docker-compose -f docker-compose.local.yml rm -f` |

---

**Ready? Run this in PowerShell:**
```powershell
cd C:\Users\arger\code\algo
& ".\setup_timescaledb_local.bat"
```
