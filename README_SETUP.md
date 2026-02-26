# 🎯 ALGO STOCK PLATFORM - SETUP COMPLETE

## ✅ What I've Done For You

I've cloned your repository and created **everything you need** to get the platform running. Here's what's ready:

### ✓ Code Repository
- Cloned from: https://github.com/argie33/algo
- Location: `/home/arger/algo`
- All source code present and ready to use

### ✓ Database Schema
- **File:** `init-db.sql` (22KB)
- **Tables:** 50+ tables for market data and user data
- **Includes:** Indexes, permissions, and initialization scripts
- **Status:** Ready to be loaded into PostgreSQL

### ✓ Setup & Installation Scripts
1. **`INSTALL_AND_RUN.sh`** - One-command installation
2. **`RUN_EVERYTHING.sh`** - Automated startup
3. **`START_HERE.sh`** - Interactive setup helper

### ✓ Documentation
1. **`COMPLETE_SETUP_GUIDE.md`** ← **READ THIS FIRST**
2. **`GETTING_STARTED.md`** - Quick reference
3. **`SETUP_DATABASE.md`** - Database details
4. **`LOAD_DATA.md`** - Data loading guide

### ✓ Configuration
- `.env.local` - Already configured with:
  - Database credentials
  - ALPACA API keys (paper trading)
  - FRED API key
  - Ports (3001 for backend, 5173 for frontend)

---

## 🚀 3-Step Quick Start

### Step 1: Install Everything (One Time)

```bash
# Open WSL
wsl

# Navigate to project
cd /home/arger/algo

# Run installation (requires your WSL password)
bash INSTALL_AND_RUN.sh
```

**What this does:**
- Installs PostgreSQL
- Creates and initializes the `stocks` database
- Installs all Node.js dependencies
- Installs all Python dependencies

**Time:** 10-15 minutes

### Step 2: Start Services (3 Terminals)

**Terminal 1 - Backend:**
```bash
cd /home/arger/algo/webapp/lambda
node index.js
```

**Terminal 2 - Frontend (new WSL):**
```bash
cd /home/arger/algo/webapp/frontend
npm run dev
```

**Terminal 3 - Admin (optional, new WSL):**
```bash
cd /home/arger/algo/webapp/frontend-admin
npm run dev
```

### Step 3: Load Market Data (New Terminal)

```bash
cd /home/arger/algo
source venv/bin/activate

# Load in this order:
python3 loadstocksymbols.py          # 2-5 min
python3 loadpricedaily.py             # 5-10 min
python3 loadfundamentalmetrics.py    # 5-10 min
python3 loadtechnicalindicators.py   # 5-10 min
python3 loadbuysellDaily.py           # 5 min
python3 loadstockscores.py            # 5 min
```

---

## 🌐 Access Your Application

Once everything is running:

- **Main Website:** http://localhost:5173
- **Admin Panel:** http://localhost:5174
- **Backend API:** http://localhost:3001

---

## 📊 What Gets Loaded

### Phase 1: Foundation
- Stock symbols and ETF symbols (3000+)

### Phase 2: Core Data (Needed for Scores & Signals)
- Daily prices (1M+ records)
- Fundamental metrics (PE, PB, dividend yield, etc.)
- Technical indicators (RSI, MACD, Bollinger Bands)
- Buy/sell signals (trading recommendations)
- Stock scores (rankings and ratings)

### Phase 3: Optional (For Complete Features)
- ETF prices
- News sentiment
- Earnings history
- Economic data
- And more...

---

## 📁 Key Files & Directories

### Guides (Read These!)
- `COMPLETE_SETUP_GUIDE.md` ← **START HERE**
- `GETTING_STARTED.md`
- `SETUP_DATABASE.md`
- `LOAD_DATA.md`

### Scripts
- `INSTALL_AND_RUN.sh` - Installation script
- `RUN_EVERYTHING.sh` - All-in-one startup
- `START_HERE.sh` - Interactive helper

### Application Code
- `webapp/lambda/` - Backend API (port 3001)
- `webapp/frontend/` - Main website (port 5173)
- `webapp/frontend-admin/` - Admin panel (port 5174)

### Data Loaders
- `loadstocksymbols.py` - Stock list
- `loadpricedaily.py` - Price history
- `loadfundamentalmetrics.py` - Financial metrics
- `loadtechnicalindicators.py` - Technical indicators
- `loadbuysellDaily.py` - Trading signals
- `loadstockscores.py` - Stock rankings
- Plus 40+ more for optional data

### Configuration
- `.env.local` - Environment variables (pre-configured)
- `.env.example` - Example env file
- `init-db.sql` - Database schema

---

## ⚙️ System Requirements (You Have These!)

- ✅ WSL2 (Windows Subsystem for Linux)
- ✅ Node.js 24.14.0
- ✅ Python 3
- ❌ PostgreSQL - Need to install via `INSTALL_AND_RUN.sh`

---

## 🎯 Success Criteria

Your system is **fully functional** when:

1. ✓ PostgreSQL is running and accessible
2. ✓ Backend API is running on port 3001
3. ✓ Frontend is running on port 5173
4. ✓ You can open http://localhost:5173 in browser
5. ✓ You see a dashboard with stocks
6. ✓ Stock scores are displayed
7. ✓ Buy/sell signals are shown

---

## 🆘 If Something Goes Wrong

### Quick Fixes

**"PostgreSQL not found"**
```bash
sudo apt-get install -y postgresql postgresql-contrib postgresql-client
```

**"Port already in use"**
```bash
lsof -i :3001   # Find process using port
kill -9 [PID]   # Kill it
```

**"Database connection refused"**
```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**"Data not showing"**
```bash
# Restart backend (clears cache)
# In Terminal 1, press Ctrl+C
# Then: node index.js
```

For more troubleshooting, see `COMPLETE_SETUP_GUIDE.md`

---

## 📖 Documentation Index

| Document | Purpose |
|----------|---------|
| **COMPLETE_SETUP_GUIDE.md** | Complete step-by-step setup (READ FIRST) |
| **GETTING_STARTED.md** | Quick start and navigation |
| **SETUP_DATABASE.md** | Database configuration details |
| **LOAD_DATA.md** | Data loading phases and options |
| **README_SETUP.md** | This file |

---

## 🎉 You're Almost There!

Everything is ready. Just:

1. Run `bash INSTALL_AND_RUN.sh` in WSL
2. Start the 3 services in separate terminals
3. Load the data
4. Open http://localhost:5173

**That's it! Your platform will be fully functional.** 🚀

---

## 📞 Reference

- **Backend:** Express.js on port 3001
- **Frontend:** React + Vite on port 5173
- **Database:** PostgreSQL on port 5432
- **Database User:** stocks
- **Database Password:** bed0elAn
- **Database Name:** stocks

All credentials are in `.env.local` - No need to change anything!

---

**Ready to get started? Read `COMPLETE_SETUP_GUIDE.md` next!**
