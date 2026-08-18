<#
.SYNOPSIS
    A.U.R.O.R.A. System Genesis Script (M10)
    
.DESCRIPTION
    Bootstraps the entire 100/100 AI Operating Platform.
    Builds the Docker containers, initializes the Vector DB, 
    and launches the UI and backend.
#>

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host " A.U.R.O.R.A. 100/100 GENESIS (M10) " -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

# Check dependencies
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Docker is not installed or not running." -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Bootstrapping Docker Infrastructure..." -ForegroundColor Yellow
docker compose up -d postgres redis

Write-Host "[INFO] Waiting for PostgreSQL (pgvector) to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host "[INFO] Building AI Backend and Next.js Frontend..." -ForegroundColor Yellow
docker compose build

Write-Host "[INFO] Igniting the Core (Backend, Frontend, Celery Workers)..." -ForegroundColor Yellow
docker compose up -d

Write-Host ""
Write-Host "[OK] A.U.R.O.R.A. System is now Online." -ForegroundColor Green
Write-Host "Dashboard: http://localhost:3000" -ForegroundColor White
Write-Host "API Gateway: http://localhost:3002/docs" -ForegroundColor White
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "To view logs in real-time, run: docker compose logs -f" -ForegroundColor DarkGray
