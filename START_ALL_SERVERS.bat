@echo off
title CopyGuard - Starting All Servers
color 0A
echo.
echo  =====================================================
echo   CopyGuard Platform - Starting All Services
echo  =====================================================
echo.

echo [1/4] Starting Registry Backend (port 8000)...
start "Registry Backend :8000" cmd /k "cd /d C:\Users\cheth\OneDrive\Desktop\copyright-protection\registry-backend && venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
timeout /t 2 /nobreak >nul

echo [2/4] Starting Social Backend (port 8001)...
start "Social Backend :8001" cmd /k "cd /d C:\Users\cheth\OneDrive\Desktop\copyright-protection\social-backend && venv\Scripts\python -m uvicorn app.main:app --reload --port 8001"
timeout /t 2 /nobreak >nul

echo [3/4] Starting Registry Frontend (port 3000)...
start "Registry Frontend :3000" cmd /k "cd /d C:\Users\cheth\OneDrive\Desktop\copyright-protection\registry-frontend && npm run dev"
timeout /t 2 /nobreak >nul

echo [4/4] Starting Social Frontend (port 4000)...
start "Social Frontend :4000" cmd /k "cd /d C:\Users\cheth\OneDrive\Desktop\copyright-protection\social-frontend && npm run dev"
timeout /t 2 /nobreak >nul

echo.
echo  =====================================================
echo   All servers started! Opening in browser...
echo  =====================================================
echo.
timeout /t 4 /nobreak >nul

start http://localhost:3000
timeout /t 2 /nobreak >nul
start http://localhost:4000

echo.
echo  Servers running:
echo    Registry Portal  -^>  http://localhost:3000
echo    Social Portal    -^>  http://localhost:4000
echo    Registry API     -^>  http://localhost:8000
echo    Social API       -^>  http://localhost:8001
echo.
echo  Close the 4 server windows to stop all services.
pause
