# TunCO2 Pro launcher for Windows.
#   Start-TunCO2Pro.bat   -> start the app
#   Run-Tests.bat         -> run the test suite (Start-TunCO2Pro.ps1 -Test)
# The Python environment lives in this folder, in .venv, so the whole product is managed and packaged
# from one place. .venv is marked "ignored" for Dropbox (it is neither synced nor locked while syncing);
# delete .venv at any time to rebuild it. First run installs it (a few minutes); later runs start at once.
param([switch]$Test)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$venv = Join-Path $PSScriptRoot ".venv"
$py   = Join-Path $venv "Scripts\python.exe"

function Invoke-Checked($exe, [string[]]$argv) {
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $exe $($argv -join ' ')" }
}

function Find-Python {
    foreach ($cmd in @("py -3.12", "py -3.11", "py -3.10", "py -3", "python")) {
        $parts = @($cmd -split " ")
        $exe = $parts[0]; $pre = @($parts | Select-Object -Skip 1)
        try {
            $v = & $exe @pre -c "import sys; print(sys.version_info >= (3,10))" 2>$null
            if ("$v".Trim() -eq "True") { return $cmd }
        } catch {}
    }
    throw "Python 3.10 or later was not found. Install it from python.org (tick 'Add to PATH') and run again."
}

function Set-DropboxIgnored($path) {
    # Dropbox honours this NTFS stream on files and folders: the item stays on disk but is not synced.
    try { Set-Content -Path $path -Stream com.dropbox.ignored -Value 1 -ErrorAction Stop } catch {
        Write-Host "Note: could not mark $path as ignored by Dropbox ($($_.Exception.Message))." -ForegroundColor Yellow
    }
}

$check = if ($Test) { "import tunco2pro, matplotlib, pytest, sympy, httpx" } else { "import tunco2pro, matplotlib" }   # matplotlib: the Figures export
$installed = $false
if (Test-Path $py) { & $py -c $check 2>$null; $installed = ($LASTEXITCODE -eq 0) }
if (-not $installed) {
    Write-Host "Setting up TunCO2 Pro in $venv (a few minutes)..." -ForegroundColor Cyan
    if (-not (Test-Path $venv)) { New-Item -ItemType Directory -Path $venv | Out-Null }
    Set-DropboxIgnored $venv      # before anything is written inside it
    if (-not (Test-Path $py)) {
        $parts = @((Find-Python) -split " ")
        Invoke-Checked $parts[0] (@($parts | Select-Object -Skip 1) + @("-m", "venv", $venv))
    }
    Invoke-Checked $py @("-m", "pip", "install", "--disable-pip-version-check", "-e", ".[all]")
    foreach ($d in @("src\tunco2pro.egg-info", "build")) { if (Test-Path $d) { Set-DropboxIgnored $d } }
}

if ($Test) {
    Invoke-Checked $py @("-m", "pytest", "-q")
    Write-Host "All tests passed." -ForegroundColor Green
    exit 0
}

function Get-FreePort([int]$from = 8000, [int]$to = 8020) {
    foreach ($p in $from..$to) {
        $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $p)
        try { $l.Start(); $l.Stop(); return $p } catch { continue }
    }
    throw "No free port between $from and $to."
}

$port = Get-FreePort
if ($port -ne 8000) {
    Write-Host "Port 8000 is in use (probably an earlier TunCO2 Pro window still open - close it to stop the old version)." -ForegroundColor Yellow
}
Write-Host "TunCO2 Pro running at http://127.0.0.1:$port  (close this window to stop)" -ForegroundColor Green
Start-Job { Start-Sleep 3; Start-Process "http://127.0.0.1:$using:port" } | Out-Null
Invoke-Checked $py @("-m", "tunco2pro.cli", "serve", "--port", "$port")
