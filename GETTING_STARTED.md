# Getting Started - Algo Stock Platform

## 📍 Where Is Your Code?

Your code repository is located at:
- **WSL Linux Path:** `/home/arger/algo`
- **Windows Network Path:** `\\wsl$\Ubuntu\home\arger\algo`
- **In PowerShell:** `\\wsl$\Ubuntu\home\arger\algo`

### ✅ Verify the Folder

```bash
# In WSL bash (which you should be using)
wsl
cd /home/arger/algo
pwd   # Should show: /home/arger/algo
ls    # Should show all your project files
```

---

## 🚀 Quick Setup (5 steps)

### Step 1: Open WSL Bash

```powershell
# In Windows PowerShell
wsl

# You should now see:
# arger@DESKTOP-4LV044V:~$
```

### Step 2: Navigate to the Project

```bash
cd /home/arger/algo
pwd   # Verify you're in /home/arger/algo
```

### Step 3: Run the Setup Script

```bash
# Make sure it's executable
chmod +x setup-env.sh

# Run it (this will install PostgreSQL, initialize DB, and install Node/Python deps)
./setup-env.sh
```

This script will:
- ✅ Check/install PostgreSQL
- ✅ Create the `stocks` database
- ✅ Initialize database schema (50+ tables)
- ✅ Install Node.js dependencies
- ✅ Install Python dependencies

**Note:** You may be prompted for your WSL password during setup.

### Step 4: Start the Backend Server

```bash
# In a new WSL terminal
cd /home/arger/algo/webapp/lambda
node index.js
```

You should see:
```
✅ Database connected
🚀 Server running on port 3001
```

### Step 5: Start the Frontend

```bash
# In another new WSL terminal
cd /home/arger/algo/webapp/frontend
npm run dev
```

You should see:
```
  VITE v7.1.3  ready in 234 ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

---

## 🌐 Access Your Application

### Frontend
- **Main Site:** http://localhost:5173
- **Admin Panel:** Would be at http://localhost:5174 (after starting frontend-admin)

### Backend API
- **Base URL:** http://localhost:3001
- **API Endpoints:** Check `/home/arger/algo/webapp/lambda/routes/`

### Database
- **Host:** localhost
- **Port:** 5432
- **Database:** stocks
- **User:** stocks
- **Password:** bed0elAn

---

## 🛠️ Manual Setup (If Automated Script Fails)

### Install PostgreSQL Manually

```bash
# Update package list
sudo apt-get update

# Install PostgreSQL
sudo apt-get install -y postgresql postgresql-contrib postgresql-client

# Start service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify
sudo systemctl status postgresql
```

### Initialize Database Manually

```bash
cd /home/arger/algo

# Connect as postgres user and create database
sudo -u postgres psql -c "CREATE DATABASE stocks;"
sudo -u postgres psql -c "CREATE USER stocks WITH ENCRYPTED PASSWORD 'bed0elAn';"
sudo -u postgres psql -d stocks -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;"

# Load the schema
sudo -u postgres psql -d stocks -f init-db.sql

# Verify
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema='public';"
```

### Install Dependencies Manually

```bash
# Node dependencies
cd /home/arger/algo/webapp
npm install

cd lambda
npm install

cd ../frontend
npm install

# Python dependencies
cd /home/arger/algo
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 📂 Project Structure

```
/home/arger/algo/
├── webapp/                          # Main application
│   ├── lambda/                      # Backend API (Node.js/Express)
│   │   ├── index.js                # Entry point (port 3001)
│   │   ├── routes/                 # API endpoints
│   │   ├── utils/                  # Database, cache, utilities
│   │   └── handlers/               # Route handlers
│   ├── frontend/                    # Main website (React + Vite)
│   │   ├── src/                    # React components
│   │   └── package.json            # Port: 5173
│   └── frontend-admin/              # Admin dashboard (React + Vite)
│       └── package.json            # Port: 5174
├── lib/                             # Python utilities
├── init-db.sql                      # Database schema (created for you)
├── setup-env.sh                     # Automated setup script (created for you)
├── SETUP_DATABASE.md                # Database setup guide (created for you)
├── GETTING_STARTED.md              # This file
├── .env.local                       # Environment variables
├── loadstocksymbols.py              # Data loader: Stock symbols
├── loadpricedaily.py                # Data loader: Daily prices
├── loadfundamentalmetrics.py        # Data loader: Financial metrics
└── run_all_loaders.sh               # Script to run all data loaders
```

---

## 🔌 Environment Variables

The file `.env.local` already contains all required settings:

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

These are loaded automatically by the backend server.

---

## 📊 Database Schema Overview

The database has **50+ tables** organized in two categories:

### Market Data Tables (Populated by Loaders)
- `stock_symbols` - Stock/ETF listings
- `price_daily`, `price_weekly`, `price_monthly` - Price history
- `company_profile` - Company information
- `fundamental_metrics` - Financial ratios
- `buy_sell_daily/weekly/monthly` - Trading signals
- `stock_scores` - Composite stock scores

### User Data Tables (Webapp)
- `user_profiles` - User accounts
- `portfolio_holdings` - Current positions
- `portfolio_performance` - P&L tracking
- `watchlists` - Stock watchlists
- `trading_strategies` - User strategies
- `price_alerts` - Alert settings

---

## 🎯 Common Tasks

### Load Market Data

```bash
cd /home/arger/algo
source venv/bin/activate

# Load stock symbols first (required)
python3 loadstocksymbols.py

# Load price data
python3 loadpricedaily.py

# Load fundamental metrics
python3 loadfundamentalmetrics.py

# Or run all loaders (slower)
bash run_all_loaders.sh
```

### Access Database Directly

```bash
# Connect to database
psql -h localhost -U stocks -d stocks

# Inside psql:
\dt                           # List all tables
SELECT * FROM stock_symbols LIMIT 5;  # View data
\q                            # Quit
```

### Check Server Logs

```bash
# Backend server logs (if running in terminal)
# Check the terminal where you ran "node index.js"

# PostgreSQL logs
sudo tail -50 /var/log/postgresql/postgresql-*.log

# Frontend dev server logs
# Check the terminal where you ran "npm run dev"
```

### Reset Database (Warning: Deletes All Data)

```bash
cd /home/arger/algo

# Drop and recreate
psql -h localhost -U stocks -d stocks -f init-db.sql
```

---

## ⚠️ Troubleshooting

### "Cannot find module" errors

```bash
# Reinstall dependencies
cd /home/arger/algo/webapp/lambda
rm -rf node_modules package-lock.json
npm install
```

### Database connection errors

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Start if not running
sudo systemctl start postgresql

# Test connection
psql -h localhost -U stocks -d stocks -c "SELECT 1;"
```

### Port already in use

```bash
# Find process using port
sudo lsof -i :3001          # Backend
sudo lsof -i :5173          # Frontend

# Kill process if needed
kill -9 <PID>
```

### WSL Performance Issues

```bash
# Check available memory
free -h

# Reduce backend memory
cd /home/arger/algo/webapp/lambda
node --max-old-space-size=2048 index.js
```

---

## 📞 Support Resources

- **Database Guide:** See `SETUP_DATABASE.md`
- **Code Files:**
  - Backend: `/home/arger/algo/webapp/lambda/index.js`
  - Frontend: `/home/arger/algo/webapp/frontend/src/`
  - Admin: `/home/arger/algo/webapp/frontend-admin/src/`

---

## 🎉 You're All Set!

1. ✅ Code is in `/home/arger/algo`
2. ✅ Database schema is ready in `init-db.sql`
3. ✅ Setup script automates everything in `setup-env.sh`
4. ✅ Follow the "Quick Setup" section above to get running

**Next:** Run `./setup-env.sh` and then start the servers!

