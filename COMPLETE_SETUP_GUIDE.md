# 🚀 COMPLETE SETUP GUIDE - Get Everything Running

This is your complete, step-by-step guide to get the Algo Stock Platform fully functional with all data loaded.

---

## ✅ What You Have Now

- ✓ Code repository cloned: `/home/arger/algo`
- ✓ Database schema created: `init-db.sql`
- ✓ Setup scripts created for you
- ✓ Node.js installed (v24.14.0)
- ✓ Python installed (Python 3)

## ❌ What's Missing

- ✗ PostgreSQL (database server) - **Needs to be installed**
- ✗ Backend server running
- ✗ Frontend server running
- ✗ Market data loaded into database

---

## 📋 Step-by-Step Instructions

### PHASE 1: Installation (One Time Only)

#### Step 1.1: Open WSL Terminal

In PowerShell or Windows Terminal:
```powershell
wsl
```

You should see:
```
arger@DESKTOP-4LV044V:~$
```

#### Step 1.2: Navigate to Project

```bash
cd /home/arger/algo
pwd
# Should show: /home/arger/algo
```

#### Step 1.3: Run Installation Script

```bash
bash INSTALL_AND_RUN.sh
```

**What this does:**
- Installs PostgreSQL
- Creates the `stocks` database
- Creates `stocks` user (password: `bed0elAn`)
- Initializes all 50+ database tables
- Installs Node.js and Python dependencies

**Time:** 10-15 minutes
**Note:** You'll be prompted for your WSL password when installing PostgreSQL

**Expected output at the end:**
```
==================================================
✓ INSTALLATION COMPLETE!
==================================================
```

---

### PHASE 2: Start Services (Every Time You Want to Run)

You need **3 separate WSL terminals** running at the same time.

#### Terminal 1: Backend Server

```bash
cd /home/arger/algo/webapp/lambda
node index.js
```

**Wait for output like:**
```
✓ Database connected
🚀 Express server running on port 3001
```

#### Terminal 2: Frontend (Open NEW WSL terminal)

```bash
cd /home/arger/algo/webapp/frontend
npm run dev
```

**Wait for output like:**
```
VITE v7.1.3 ready in 234 ms

➜  Local:   http://localhost:5173/
```

#### Terminal 3: Optional - Admin Site (Open ANOTHER new WSL terminal)

```bash
cd /home/arger/algo/webapp/frontend-admin
npm run dev
```

**Once all 3 terminals are running with green messages, continue to Phase 3**

---

### PHASE 3: Load Market Data (First Time Takes 30-60 Minutes)

In the same Terminal 2 where frontend is running (or a NEW terminal):

```bash
# Open NEW WSL terminal for this
cd /home/arger/algo
source venv/bin/activate

# Load stock symbols (REQUIRED FIRST)
echo "Loading stock symbols..."
python3 loadstocksymbols.py
# Wait for: "✓ Loaded X stock symbols"
# Time: 2-5 minutes

# Load daily prices
echo "Loading daily prices..."
python3 loadpricedaily.py
# Time: 5-10 minutes

# Load fundamental metrics
echo "Loading fundamental metrics..."
python3 loadfundamentalmetrics.py
# Time: 5-10 minutes

# Load technical indicators
echo "Loading technical indicators..."
python3 loadtechnicalindicators.py
# Time: 5-10 minutes

# Load buy/sell signals
echo "Loading buy/sell signals..."
python3 loadbuysellDaily.py
# Time: 5 minutes

# Load stock scores
echo "Loading stock scores..."
python3 loadstockscores.py
# Time: 5 minutes
```

**Or run them all at once:**
```bash
cd /home/arger/algo
source venv/bin/activate
bash run_all_loaders_monitored.sh
```

---

## 🌐 Access Your Application

Once everything is running, open in your browser:

- **Main Site:** http://localhost:5173
- **Admin Panel:** http://localhost:5174
- **API:** http://localhost:3001/api/health

---

## ✅ Verify Everything Works

### Check Database

```bash
# In a new WSL terminal
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"
```

Should show a number like: `3000+`

### Check Backend

```bash
curl http://localhost:3001/api/health
```

Should return:
```json
{"status":"ok"}
```

### Check Frontend

Open http://localhost:5173 in your browser - you should see the dashboard

---

## 🛠️ Quick Troubleshooting

### "PostgreSQL not found" after running INSTALL_AND_RUN.sh

Run in WSL:
```bash
which psql
# If nothing shows, PostgreSQL install failed
# Try again:
sudo apt-get install -y postgresql postgresql-contrib postgresql-client
```

### "Connection refused" when backend starts

PostgreSQL isn't running:
```bash
sudo systemctl status postgresql
# If not running:
sudo systemctl start postgresql
```

### "Port already in use"

Something is using your ports. Kill it:
```bash
# For port 3001 (backend)
sudo lsof -i :3001
# Shows PID, then: kill -9 PID

# For port 5173 (frontend)
sudo lsof -i :5173
```

### "Module not found" errors

Reinstall dependencies:
```bash
cd /home/arger/algo/webapp/lambda
rm -rf node_modules package-lock.json
npm install
```

### Data not showing in frontend

Restart backend (loaders may have run while backend was caching old state):
```bash
# In Terminal 1, press Ctrl+C to stop
# Then restart:
node index.js
```

---

## 📊 What Each Data Loader Does

| Loader | Loads | Required | Time |
|--------|-------|----------|------|
| `loadstocksymbols.py` | Stock/ETF list | **YES** | 2-5 min |
| `loadpricedaily.py` | Price history | **YES** | 5-10 min |
| `loadfundamentalmetrics.py` | Financial ratios | **YES** | 5-10 min |
| `loadtechnicalindicators.py` | RSI, MACD, etc. | **YES** | 5-10 min |
| `loadbuysellDaily.py` | Trading signals | **YES** | 5 min |
| `loadstockscores.py` | Stock rankings | **YES** | 5 min |
| `loadetfpricedaily.py` | ETF prices | Optional | 5 min |
| `loadsentiment.py` | News sentiment | Optional | 10 min |
| `loadearningshistory.py` | Earnings data | Optional | 10 min |

---

## 📁 Files Created For You

These scripts/guides were created to help you:

- `INSTALL_AND_RUN.sh` - Installation script (Run this first!)
- `RUN_EVERYTHING.sh` - All-in-one startup (Advanced)
- `GETTING_STARTED.md` - Quick start guide
- `SETUP_DATABASE.md` - Detailed database info
- `LOAD_DATA.md` - Data loading details
- `init-db.sql` - Database schema (50+ tables)
- `COMPLETE_SETUP_GUIDE.md` - This file

---

## 🎯 Final Checklist

Before considering yourself "done":

- [ ] INSTALL_AND_RUN.sh ran successfully
- [ ] Backend server is running (Terminal 1)
- [ ] Frontend server is running (Terminal 2)
- [ ] You can access http://localhost:5173 in browser
- [ ] loadstocksymbols.py ran successfully
- [ ] loadpricedaily.py ran successfully
- [ ] loadfundamentalmetrics.py ran successfully
- [ ] loadtechnicalindicators.py ran successfully
- [ ] loadbuysellDaily.py ran successfully
- [ ] loadstockscores.py ran successfully
- [ ] You see stocks on the main page
- [ ] You see scores/signals on detail pages

---

## 🚀 You're Ready!

Once you've completed all steps above, your system is **fully functional** with:

✅ PostgreSQL running
✅ Backend API responding
✅ Frontend serving
✅ 3000+ stocks loaded
✅ 100,000+ prices loaded
✅ Stock scores calculated
✅ Trading signals generated
✅ All pages populated

---

## 📞 Need Help?

Check these files for more details:

- Database questions → `SETUP_DATABASE.md`
- Getting started → `GETTING_STARTED.md`
- Data loading → `LOAD_DATA.md`
- Backend code → `/home/arger/algo/webapp/lambda/`
- Frontend code → `/home/arger/algo/webapp/frontend/src/`

---

## 🎉 Start Here!

```bash
# Open WSL
wsl

# Go to project
cd /home/arger/algo

# Run installation
bash INSTALL_AND_RUN.sh

# Then follow Phase 2 & 3 above
```

**That's it! You've got this! 🚀**
