@echo off
echo ========================================================
echo Starting ResearchMind...
echo ========================================================

echo [1/2] Launching Backend API on http://127.0.0.1:8000 ...
start "ResearchMind Backend" cmd /k "cd /d %~dp0backend && .\.venv\Scripts\activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

echo [2/2] Launching Frontend on http://localhost:5173 ...
start "ResearchMind Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 3 /nobreak >nul
start http://localhost:5173
echo ========================================================
echo ResearchMind is up and running!
echo ========================================================
