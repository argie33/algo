@echo off
REM Quick restart script for both servers with auto-restart
REM Run this if servers crash: RESTART_SERVERS.bat

echo Stopping PM2...
call pm2 kill

echo Waiting 3 seconds...
timeout /t 3 /nobreak

echo Starting all servers with PM2 (auto-restart enabled)...
call pm2 start node --name "api" -- webapp/lambda/index.js
timeout /t 3 /nobreak
call pm2 start "npm run dev" --cwd webapp/frontend --name "frontend"

echo.
echo Waiting for startup...
timeout /t 8 /nobreak

echo.
echo === SERVER STATUS ===
call pm2 status

echo.
echo === TESTING SERVERS ===
echo API (port 3001):
curl -s http://localhost:3001/api/status | find /I "ok" >nul && echo   Status: OK || echo   Not responding yet...

echo Frontend (port 5173):
curl -s -o nul -w "   HTTP %%{http_code}\n" http://localhost:5173

echo.
echo SERVERS RUNNING WITH AUTO-RESTART ENABLED
echo View logs with: pm2 logs
echo Restart anytime: RESTART_SERVERS.bat
pause
