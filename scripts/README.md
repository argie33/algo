# Startup Scripts

Quick scripts to start the development environment for the Financial Dashboard.

## Available Scripts

### macOS / Linux
```bash
./scripts/start-dev.sh
```

### Windows
```cmd
scripts/start-dev.bat
```

## What These Scripts Do

1. **Validate Prerequisites**
   - ✓ Checks Node.js version (Backend: 18+, Frontend: 20.19+)
   - ✓ Verifies ports 3001 and 5173 are available
   - ✓ Attempts to connect to PostgreSQL database

2. **Start Backend** (Port 3001)
   - Installs npm dependencies if needed
   - Starts Express.js server
   - Waits for server to be ready

3. **Start Frontend** (Port 5173)
   - Installs npm dependencies if needed
   - Starts Vite dev server
   - Ready for development

4. **Log Output**
   - Backend logs: `logs/backend.log`
   - Frontend logs: `logs/frontend.log`

## Usage

### Quick Start (Linux/macOS)
```bash
cd /home/stocks/algo
./scripts/start-dev.sh
```

Then open your browser:
- Frontend: http://localhost:5173
- API: http://localhost:3001

### Stop Services
Press `Ctrl+C` to stop all services.

## Troubleshooting

### "Port already in use"
**Kill the process using the port:**
```bash
# Kill port 3001 (backend)
lsof -ti:3001 | xargs kill -9

# Kill port 5173 (frontend)
lsof -ti:5173 | xargs kill -9
```

### "Cannot connect to PostgreSQL"
**Start PostgreSQL:**
```bash
# macOS (with Homebrew)
brew services start postgresql

# Ubuntu/Debian
sudo service postgresql start

# or via Docker
docker run -d \
  --name postgres \
  -e POSTGRES_USER=stocks \
  -e POSTGRES_PASSWORD=bed0elAn \
  -e POSTGRES_DB=stocks \
  -p 5432:5432 \
  postgres:15
```

Then update `.env` files if using different credentials.

### "Node version mismatch"
**Check your Node version:**
```bash
node --version
```

**Required versions:**
- Backend (Lambda): Node 18+
- Frontend (React): Node 20.19+

**Update Node:**
```bash
# Using nvm (recommended)
nvm install 22
nvm use 22

# or download from nodejs.org
```

### Backend crashes immediately
**Check logs:**
```bash
tail -f logs/backend.log
```

**Common issues:**
- Database not running (see PostgreSQL section above)
- Port 3001 already in use
- Missing environment variables in `webapp/lambda/.env`

### Frontend won't start
**Check logs:**
```bash
tail -f logs/frontend.log
```

**Common issues:**
- Node version too old
- Port 5173 already in use
- Missing dependencies (try: `npm install`)

## Manual Start (if script fails)

### Backend
```bash
cd webapp/lambda
npm install
npm start
# Should see: "Server running on port 3001"
```

### Frontend
```bash
cd webapp/frontend
npm install
npm run dev
# Should see: "VITE v... ready in ... ms"
```

## Environment Configuration

### Backend (.env)
Located: `webapp/lambda/.env`
- `PORT=3001`
- `DB_HOST=localhost`
- `DB_USER=stocks`
- `DB_PASSWORD=bed0elAn`
- `DB_NAME=stocks`
- `DB_PORT=5432`

### Frontend (.env)
Located: `webapp/frontend/.env`
- `VITE_API_URL=http://localhost:3001`
- `VITE_ENVIRONMENT=development`

## Additional Commands

### Backend
```bash
cd webapp/lambda
npm run test           # Run tests
npm run lint          # Lint code
npm run lint:fix      # Fix linting issues
```

### Frontend
```bash
cd webapp/frontend
npm run lint          # Lint code
npm run lint:fix      # Fix linting issues
npm run build         # Build for production
npm test              # Run tests
```

## Support

If services keep crashing:

1. Check logs: `logs/backend.log` and `logs/frontend.log`
2. Verify database is running: `psql -h localhost -U stocks -d stocks -c "SELECT 1"`
3. Check Node versions match requirements
4. Ensure ports 3001 and 5173 are free
5. Try manual start (see "Manual Start" section above)
