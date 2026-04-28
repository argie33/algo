@echo off
set DB_HOST=localhost
set DB_PORT=5432
set DB_USER=stocks
set DB_PASSWORD=bed0elAn
set DB_NAME=stocks
set PORT=3001
node webapp/lambda/index.js
