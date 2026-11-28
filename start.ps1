<#
.SYNOPSIS
    Start ÆHub on Windows with a double click (N11).

.DESCRIPTION
    Double-click AEHub.cmd (or the "ÆHub" icon on the desktop), or run
    .\start.ps1. It:
      1. checks Docker and starts Docker Desktop when it is installed but not
         running, waiting until it answers;
      2. checks Python, needed by the launcher (scripts/aehub.py);
      3. on the first run, stores the keys in Windows Credential Manager and
         picks the working folder (the launcher's setup): keys never go to a
         file;
      4. starts the stack with Docker Compose;
      5. waits until ÆHub answers, then opens it in the browser (the first
         start on the setup page);
      6. puts an "ÆHub" icon on the desktop, once.

    .\start.ps1 -Stop stops ÆHub; -NoBrowser starts it without opening the
    browser; -NoShortcut does not create the desktop icon.
    The desktop app (Tauri) is a separate, suspended path: this script does
    not touch it.
#>

param(
    [switch]$Stop,
    [switch]$NoBrowser,
    [switch]$NoShortcut
)

# Not "Stop": in Windows PowerShell 5.1 the error output of a native command
# (docker, python) redirected with *> would then end the script.
Set-Location -Path $PSScriptRoot

$NucleoUrl = "http://localhost:3000/"
$SetupUrl = "http://localhost:3000/control-plane/setup"
$HealthUrl = "http://localhost:3002/health"
$DockerWaitSeconds = 180
$StartWaitSeconds = 600

function Say([string]$Text, [string]$Color = "White") {
    Write-Host $Text -ForegroundColor $Color
}

function Fail([string]$Text) {
    Say "[ERRORE] $Text" "Red"
    exit 1
}

function Test-Url([string]$Url) {
    try {
        $answer = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        return $answer.StatusCode -lt 500
    } catch {
        return $false
    }
}

# ---------------------------------------------------------------------------
# 1. Docker
# ---------------------------------------------------------------------------
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker non è installato. Installa Docker Desktop da https://www.docker.com/products/docker-desktop/ e riapri ÆHub."
}

function Test-Docker {
    & docker info *> $null
    return $LASTEXITCODE -eq 0
}

if (!(Test-Docker)) {
    $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (!(Test-Path $desktop)) {
        Fail "Docker non risponde. Avvia Docker Desktop e riapri ÆHub."
    }
    Say "Avvio Docker Desktop…" "Cyan"
    Start-Process -FilePath $desktop
    $deadline = (Get-Date).AddSeconds($DockerWaitSeconds)
    while (!(Test-Docker)) {
        if ((Get-Date) -gt $deadline) {
            Fail "Docker Desktop non ha risposto entro $DockerWaitSeconds secondi. Aprilo a mano, aspetta che sia pronto e riapri ÆHub."
        }
        Start-Sleep -Seconds 3
    }
    Say "Docker è pronto." "Green"
}

# ---------------------------------------------------------------------------
# 2. Python, for the launcher
# ---------------------------------------------------------------------------
$python = $null
foreach ($candidate in @("py", "python")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
    }
}
if (!$python) {
    Fail "Serve Python 3 (da https://www.python.org/downloads/, con 'Add python.exe to PATH'). Poi riapri ÆHub."
}

if ($Stop) {
    & $python scripts/aehub.py down
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Say "[OK] ÆHub è fermo." "Green"
    exit 0
}

# ---------------------------------------------------------------------------
# 3. First run: keys in the Credential Manager, working folder
# ---------------------------------------------------------------------------
& $python scripts/aehub.py login-key *> $null
$firstRun = $LASTEXITCODE -ne 0
if ($firstRun) {
    Say "Primo avvio: ora ÆHub ti chiede le chiavi (restano nel Gestione credenziali di Windows, mai in un file) e la cartella di lavoro." "Cyan"
    & $python scripts/aehub.py setup
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# ---------------------------------------------------------------------------
# 4. The stack
# ---------------------------------------------------------------------------
Say "Avvio ÆHub (la prima volta qualche minuto: si costruiscono le immagini)…" "Cyan"
& $python scripts/aehub.py up
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ---------------------------------------------------------------------------
# 5. Wait until it answers, then open it
# ---------------------------------------------------------------------------
$deadline = (Get-Date).AddSeconds($StartWaitSeconds)
while (!((Test-Url $HealthUrl) -and (Test-Url $NucleoUrl))) {
    if ((Get-Date) -gt $deadline) {
        Fail "ÆHub non risponde dopo $StartWaitSeconds secondi. Guarda cosa succede con: docker compose logs -f"
    }
    Start-Sleep -Seconds 3
}

Say ""
Say "[OK] ÆHub è pronto." "Green"
Say "Nucleo:          $NucleoUrl"
Say "Chiave d'accesso: $python scripts/aehub.py login-key"
Say "Per fermarlo:     .\start.ps1 -Stop" "DarkGray"

if (!$NoBrowser) {
    Start-Process ($(if ($firstRun) { $SetupUrl } else { $NucleoUrl }))
}

# ---------------------------------------------------------------------------
# 6. The desktop icon, once
# ---------------------------------------------------------------------------
if (!$NoShortcut) {
    $link = Join-Path ([Environment]::GetFolderPath("Desktop")) "ÆHub.lnk"
    if (!(Test-Path $link)) {
        try {
            $shell = New-Object -ComObject WScript.Shell -ErrorAction Stop
            $shortcut = $shell.CreateShortcut($link)
            $shortcut.TargetPath = Join-Path $PSScriptRoot "AEHub.cmd"
            $shortcut.WorkingDirectory = $PSScriptRoot
            $shortcut.Description = "Avvia ÆHub"
            $icon = Join-Path $PSScriptRoot "desktop\src-tauri\icons\icon.ico"
            if (Test-Path $icon) { $shortcut.IconLocation = $icon }
            $shortcut.Save()
            Say "Sul desktop c'è l'icona «ÆHub»: la prossima volta basta un doppio clic." "Green"
        } catch {
            Say "L'icona sul desktop non è stata creata ($($_.Exception.Message)): ÆHub si avvia comunque con AEHub.cmd." "Yellow"
        }
    }
}
