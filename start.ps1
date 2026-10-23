<#
.SYNOPSIS
    Start ÆHub on Windows.

.DESCRIPTION
    Thin wrapper over the launcher (scripts/aehub.py): on the first run it
    stores the keys in Windows Credential Manager and picks the working
    folder, then it starts the stack with Docker Compose. Keys never go to a
    file.
#>

if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Docker is not installed or not running." -ForegroundColor Red
    exit 1
}

$python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }

# No login key in the keyring yet: this is the first run.
& $python scripts/aehub.py login-key *> $null
if ($LASTEXITCODE -ne 0) {
    & $python scripts/aehub.py setup
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $python scripts/aehub.py up
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[OK] ÆHub is starting." -ForegroundColor Green
Write-Host "Control Plane: http://localhost:3000/control-plane" -ForegroundColor White
Write-Host "Login key:     python scripts/aehub.py login-key" -ForegroundColor White
Write-Host "Logs:          docker compose logs -f" -ForegroundColor DarkGray
