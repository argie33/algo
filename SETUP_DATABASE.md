# Database Setup Guide for Stock Algo Platform

## Quick Start - Database Setup

### Option 1: PostgreSQL on WSL (Recommended)

Since you're using WSL2 with Linux, install PostgreSQL natively:

```bash
# In WSL bash terminal
wsl
cd /home/arger/algo

# Install PostgreSQL (requires password - see below)
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib postgresql-client

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Check if running
sudo systemctl status postgresql
```

### Option 2: Use Docker (if available)

If you have Docker Desktop with WSL integration:

```bash
cd /home/arger/algo
docker compose up -d
```

---

## Database Configuration

**Database Details:**
- Database Name: `stocks`
- Username: `stocks`
- Password: `bed0elAn`
- Port: `5432`
- Host: `localhost`

These values are already configured in `/home/arger/algo/.env.local`

---

## Initialize the Database

Once PostgreSQL is running:

```bash
# Option A: Using psql directly
sudo -u postgres psql -f /home/arger/algo/init-db.sql

# Option B: Using Node.js (after PostgreSQL is running and psql is available)
cd /home/arger/algo/webapp/lambda
node -e "require('./webapp-db-init.js').initializeWebappTables().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); })"
```

---

## Verify Database Setup

```bash
# Connect to the database
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema='public';"

# List all tables
psql -h localhost -U stocks -d stocks -c "\dt"

# Check important tables exist
psql -h localhost -U stocks -d stocks -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"
```

---

## WSL2 vs Windows Path Access

### Current Setup Location
- **WSL Path:** `/home/arger/algo`
- **Windows Path:** `\\wsl$\Ubuntu\home\arger\algo` (or similar, depends on your WSL distro name)

### To Navigate from Windows

```bash
# In PowerShell on Windows
cd \\wsl$\Ubuntu\home\arger\algo

# Or use the WSL bash:
wsl
cd /home/arger/algo
```

### To Access from WSL

```bash
# You should already be in the right place
wsl
cd /home/arger/algo
pwd  # Should show /home/arger/algo
ls -la  # List files
```

---

## Troubleshooting

### Issue: "sudo: a terminal is required to read the password"

This happens in WSL when not running in a real terminal. Use one of these:

**Solution 1: Run with -S flag**
```bash
echo "your_password" | sudo -S apt-get update
```

**Solution 2: Configure sudoers for passwordless sudo**
```bash
# This requires initial password entry
sudo visudo
# Add this line at the end:
# arger ALL=(ALL) NOPASSWD: ALL
```

**Solution 3: Use wsl --user root**
```bash
wsl --user root
apt-get install -y postgresql postgresql-contrib
```

### Issue: PostgreSQL won't start

```bash
# Check service status
sudo systemctl status postgresql

# Try starting manually
sudo service postgresql start

# Check logs
sudo tail -100 /var/log/postgresql/postgresql-*.log
```

### Issue: Connection refused

```bash
# Verify PostgreSQL is listening on port 5432
sudo netstat -tlnp | grep 5432

# Check if service is running
sudo systemctl status postgresql
```

---

## Next Steps After Database Setup

1. ✅ Database initialized
2. Start the backend server: `cd /home/arger/algo/webapp/lambda && node index.js`
3. Start the frontend: `cd /home/arger/algo/webapp/frontend && npm install && npm run dev`
4. Access frontend: `http://localhost:5173` (or the port shown)
5. Load market data: Run the Python data loaders

---

## Data Loaders

After database is running, load market data:

```bash
cd /home/arger/algo

# Load stock symbols (required first)
python3 loadstocksymbols.py

# Load fundamental metrics
python3 loadfundamentalmetrics.py

# Load price data
python3 loadpricedaily.py

# For automated loading, see:
# - run_all_loaders.sh
# - run_all_loaders_monitored.sh
```

---

## Environment Variables

Already configured in `.env.local`:
```
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=bed0elAn
DB_NAME=stocks
NODE_ENV=development
PORT=3001
ALPACA_API_KEY=PKUUMLHSGBRXIHXQSOSMXSOSVK
ALPACA_SECRET_KEY=3HVYtyhmHU8sHe95AsTgJXWYiws2HcizttZU3L58FumF
ALPACA_PAPER_TRADING=true
```

---

## Architecture

```
┌─────────────────────────────────────┐
│   Frontend (React + Vite)           │
│   Port: 5173                        │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│   Backend API (Express.js)          │
│   Port: 3001                        │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│   PostgreSQL Database               │
│   stocks (user: stocks)             │
│   Port: 5432                        │
└─────────────────────────────────────┘
              │
┌─────────────▼───────────────────────┐
│   Python Data Loaders               │
│   (Market data, technical indicators)
└─────────────────────────────────────┘
```
