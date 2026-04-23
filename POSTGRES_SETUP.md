# PostgreSQL Setup Guide for Algo Trading System

## Quick Summary
- **PostgreSQL Version**: 16 (recommended) or 15+
- **Database Name**: `stocks`
- **Database User**: `stocks`
- **Database Password**: `bed0elAn`
- **Port**: 5432
- **Host**: localhost

---

## Step 1: Install PostgreSQL on Windows

### Download PostgreSQL
1. Visit: https://www.postgresql.org/download/windows/
2. Download **PostgreSQL 16** (latest stable recommended)
3. Download size: ~200 MB

### Run the Installer
1. Execute the downloaded `.exe` file
2. Follow the installation wizard:
   - **Installation Directory**: `C:\Program Files\PostgreSQL\16` (default)
   - **Select Components**: Keep all checked (Server, pgAdmin, Command Line Tools)
   - **Data Directory**: `C:\Program Files\PostgreSQL\16\data` (default)
   - **Port Number**: `5432` (default - **DO NOT CHANGE**)
   - **Superuser Password**: Set something secure (you'll use this temporarily)
   - **Start service**: Check "Install as a service"

### Verify Installation
Once installed, open Command Prompt and run:
```cmd
"C:\Program Files\PostgreSQL\16\bin\psql.exe" --version
```

You should see: `psql (PostgreSQL) 16.x`

---

## Step 2: Create Database & User

### Using Command Prompt (Easiest)

Open **Command Prompt** (not PowerShell) and run:

```cmd
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost
```

You'll be prompted for the superuser password you set during installation.

Then paste and execute these commands in the psql prompt:

```sql
CREATE USER stocks WITH PASSWORD 'bed0elAn';
CREATE DATABASE stocks OWNER stocks;
GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
ALTER ROLE stocks WITH CREATEDB;
\q
```

### Or Using the Setup Script (If you have Admin access)

Right-click **Command Prompt** → "Run as Administrator" → Navigate to the algo folder:

```cmd
cd C:\Users\arger\code\algo
powershell -ExecutionPolicy Bypass -File setup-postgres.ps1
```

---

## Step 3: Verify Connection

Test that everything works:

```cmd
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U stocks -d stocks -h localhost -c "SELECT 1;"
```

If successful, you'll see:
```
 ?column?
----------
        1
(1 row)
```

---

## Step 4: Install Node Dependencies

Navigate to the project directory:

```cmd
cd C:\Users\arger\code\algo
npm install
```

This installs:
- **express**: Web framework
- **pg**: PostgreSQL driver
- **cors**: Cross-Origin Resource Sharing

---

## Step 5: Set Environment Variables

The `.env.local` file is already configured with correct values:
```
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=bed0elAn
DB_NAME=stocks
```

✅ **No changes needed** - it's ready to go!

---

## Testing the Setup

### Test 1: PostgreSQL Connection
```cmd
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U stocks -d stocks -h localhost -c "SELECT NOW();"
```

### Test 2: Node.js Dependencies
```cmd
npm list pg
```

Should show: `pg@8.19.0` or similar

### Test 3: Start the Application
```cmd
npm start
```

The web server should start on `http://localhost:3001`

---

## Troubleshooting

### PostgreSQL Service Not Running
```cmd
sc query postgresql-x64-16
```

To start the service:
```cmd
sc start postgresql-x64-16
```

### Port Already in Use (5432)
```cmd
netstat -ano | findstr :5432
```

If something else is using port 5432, you have two options:
1. Stop the other service
2. Change PostgreSQL port during installation and update `.env.local`

### Connection Refused
1. Verify PostgreSQL service is running
2. Verify port is 5432: `SELECT setting FROM pg_settings WHERE name = 'port';`
3. Check firewall isn't blocking localhost:5432

### "User stocks does not exist"
Re-run the database creation commands from Step 2

---

## Connection String Reference

For use in applications:
```
postgresql://stocks:bed0elAn@localhost:5432/stocks
```

---

## Next Steps

Once setup is complete:

1. **Start the web server**:
   ```cmd
   npm start
   ```

2. **Load initial data** (in a new terminal):
   ```cmd
   python loadstocksymbols.py
   ```

3. **Access the application**:
   - Open browser to: http://localhost:3001

---

## Quick Reference Commands

```cmd
# Check PostgreSQL status
sc query postgresql-x64-16

# Start PostgreSQL
sc start postgresql-x64-16

# Stop PostgreSQL
sc stop postgresql-x64-16

# Connect to database
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U stocks -d stocks -h localhost

# Run SQL file
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U stocks -d stocks -h localhost -f script.sql

# Backup database
"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -U stocks -d stocks > backup.sql

# Restore database
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U stocks -d stocks < backup.sql
```

---

## Windows Service Management

**View all database-related services**:
```cmd
sc query | findstr postgres
```

**Restart PostgreSQL**:
```cmd
sc stop postgresql-x64-16 & sc start postgresql-x64-16
```

**View logs** (with pgAdmin or):
```cmd
type "C:\Program Files\PostgreSQL\16\data\log\*.log"
```
