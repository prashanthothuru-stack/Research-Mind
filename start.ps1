# Launch ResearchMind Backend and Frontend
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting ResearchMind..." -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

Write-Host "[1/2] Launching Backend API on http://127.0.0.1:8000 ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

Write-Host "[2/2] Launching Frontend on http://localhost:5173 ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev"

Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"

Write-Host "========================================================" -ForegroundColor Green
Write-Host "ResearchMind is running at http://localhost:5173" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
