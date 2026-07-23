$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Output "Python was not found on PATH. Install it from https://www.python.org/downloads/ (check 'Add python.exe to PATH' during setup), then re-run this installer."
    exit 1
}

$repo = "Nantaphat-Yoktaworn/macfind"
$branch = "main"
$dest = "$env:LOCALAPPDATA\macfind"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

foreach ($f in "macfind.py", "macfind.cmd", "mac.cmd") {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/$repo/$branch/$f" -OutFile "$dest\$f"
}

if (-not (Test-Path "$dest\devices.json")) {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/$repo/$branch/devices.example.json" -OutFile "$dest\devices.json"
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -split ';' -notcontains $dest) {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dest", "User")
}

Write-Output "macfind installed to $dest"
Write-Output "Close and reopen PowerShell (PATH only applies to new windows), then run: macfind help"
