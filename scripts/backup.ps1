# Omnixa backup script (Windows dev). Backs up MySQL + uploads to ./backup/.
# Usage: .\scripts\backup.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$backupDir = Join-Path $root 'backup'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

# 1. Parse DATABASE_URL from backend/.env (mysql+pymysql://user:pass@host:port/db)
$envFile = Join-Path $root 'backend\.env'
if (-not (Test-Path $envFile)) { throw "backend/.env not found" }
$dbUrl = (Select-String -Path $envFile -Pattern '^\s*DATABASE_URL\s*=' | Select-Object -First 1).Line
if (-not $dbUrl) { throw "DATABASE_URL not found in backend/.env" }
$dbUrl = ($dbUrl -split '=', 2)[1].Trim().Trim('"').Trim("'")

if ($dbUrl -notmatch '^mysql(?:[+a-z0-9]*)://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)$') {
    throw "Unsupported DATABASE_URL format: $dbUrl"
}
$user = $Matches[1]; $pass = $Matches[2]; $dbHost = $Matches[3]; $dbPort = $Matches[4]; $db = $Matches[5]
$db = ($db -split '\?')[0]

# Locate mysqldump
$mysqldump = (Get-Command mysqldump -ErrorAction SilentlyContinue).Source
if (-not $mysqldump) {
    $candidates = @(
        'D:\BtSoft\mysql\MySQL8.0\bin\mysqldump.exe',
        'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe',
        'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe',
        'C:\Program Files\MySQL\MySQL Server 9.0\bin\mysqldump.exe'
    )
    $mysqldump = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $mysqldump) { throw "mysqldump not found; add MySQL bin to PATH" }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$sqlFile = Join-Path $backupDir "my_web_$stamp.sql"
$zipFile = Join-Path $backupDir "uploads_$stamp.zip"

Write-Output "Backing up MySQL ($db) -> $sqlFile"
$env:MYSQL_PWD = $pass
& $mysqldump -h $dbHost -P $dbPort -u $user --single-transaction --routines --triggers $db `
    | Out-File -FilePath $sqlFile -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "mysqldump failed with exit code $LASTEXITCODE" }
Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue

Write-Output "Backing up uploads -> $zipFile"
$uploads = Join-Path $root 'backend\data\uploads'
if (Test-Path $uploads) {
    Compress-Archive -Path $uploads -DestinationPath $zipFile -Force
} else {
    Write-Warning "uploads dir not found: $uploads"
}

Write-Output "Done."
Write-Output "  DB:     $sqlFile ($((Get-Item $sqlFile).Length) bytes)"
if (Test-Path $zipFile) { Write-Output "  Uploads: $zipFile ($((Get-Item $zipFile).Length) bytes)" }
