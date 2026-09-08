@echo off
REM ===================================================================
REM  Starts backend and frontend on MATCHING ports, in two windows.
REM
REM  The most common failure is the backend on 8080 (because Windows
REM  reserves 8000) while the frontend still proxies to 8000, giving
REM  ECONNREFUSED and blank cards. This script keeps them in sync.
REM ===================================================================

set PORT=8000

echo Checking whether port %PORT% is usable...
netstat -ano | findstr ":%PORT% " >nul 2>&1
if %errorlevel%==0 (
  echo   Port %PORT% is busy. Using 8080 instead.
  set PORT=8080
)

echo.
echo   Backend  : http://127.0.0.1:%PORT%
echo   Frontend : http://127.0.0.1:5173
echo.

REM Pin the frontend proxy to the same port.
echo VITE_API_PORT=%PORT%> frontend\.env.local

start "Agri Backend" cmd /k "cd backend && uvicorn app.main:app --reload --port %PORT%"

echo Waiting for the backend to come up...
timeout /t 6 /nobreak >nul

start "Agri Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both started. Open http://127.0.0.1:5173
echo Login: farmer@demo.com / demo123
pause
