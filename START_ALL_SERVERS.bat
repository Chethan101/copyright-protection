@echo off
title CopyGuard - Starting All Servers
color 0A

REM Change to the folder where this batch file is located
cd /d "%~dp0"

echo.
echo =====================================================
echo  CopyGuard Platform - Starting All Services
echo =====================================================
echo.
echo  Everything runs at http://localhost:4000
echo  (the copyright registry is built into it - see the
echo   "Registry" item in the sidebar)
echo.

echo [1/3] Starting Registry API (port 8000)...
start "Registry API :8000" cmd /k "cd /d ""%~dp0registry-backend"" && ..\venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
timeout /t 2 /nobreak >nul

echo [2/3] Starting Social API (port 8001)...
start "Social API :8001" cmd /k "cd /d ""%~dp0social-backend"" && ..\venv\Scripts\python -m uvicorn app.main:app --reload --port 8001"
timeout /t 2 /nobreak >nul

echo [3/3] Starting VibeSocial (port 4000)...
start "VibeSocial :4000" cmd /k "cd /d ""%~dp0social-frontend"" && npm run dev"
timeout /t 2 /nobreak >nul

echo.
echo =====================================================
echo  All servers started! Opening in browser...
echo =====================================================
echo.

timeout /t 5 /nobreak >nul

start http://localhost:4000

echo.
echo Servers running:
echo   VibeSocial (app) -^> http://localhost:4000   ^<-- open this
echo   Registry API     -^> http://localhost:8000
echo   Social API       -^> http://localhost:8001
echo.
echo NOTE: Ganache must be running on port 7545 for blockchain
echo       registration. Start it before this script.
echo.
echo The old standalone registry UI on port 3000 is no longer
echo needed. To run it anyway:  cd registry-frontend ^&^& npm run dev
echo.
echo Close the 3 server windows to stop all services.
pause
