<#
.SYNOPSIS
    A.U.R.O.R.A. Production Backup Script (M14)
.DESCRIPTION
    Creates a secure snapshot of PostgreSQL, Redis, and persistent volumes.
#>

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = "./infra/backups/$timestamp"

Write-Host "[M14] Initiating Production Backup..." -ForegroundColor Cyan

mkdir -Force $backupDir | Out-Null

Write-Host "1. Dumping PostgreSQL Database (pgvector)..."
docker exec aehub-postgres pg_dump -U aehub_user aehub_db > "$backupDir/aehub_db.sql"

Write-Host "2. Snapshotting Redis Event Store..."
docker exec aehub-redis redis-cli SAVE | Out-Null
Copy-Item "./data/redis/dump.rdb" "$backupDir/redis_dump.rdb"

Write-Host "3. Archiving Artifacts and Vectors..."
Compress-Archive -Path "./workspace/chromadb" -DestinationPath "$backupDir/chromadb_snapshot.zip" -ErrorAction SilentlyContinue

Write-Host "Backup completed successfully to: $backupDir" -ForegroundColor Green
