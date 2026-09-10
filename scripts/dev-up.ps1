<#
.SYNOPSIS
  Omnixa dev environment one-click management: start / stop / status / logs
  for MySQL, Redis, Worker, Backend and Frontend.

.DESCRIPTION
  Idempotently starts all components in the background and writes stdout/stderr
  to <root>\logs\. MySQL is a BT-panel Windows service ("mysql"); the script
  only ensures it is running and never stops it (shared dependency).

  Usage (run from the project root):
    powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1             # start all (default)
    powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 start
    powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 stop        # stop script-managed processes
    powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 status      # show component status
    powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 logs        # tail recent logs
    powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 logs backend # one component only
#>

param(
    [ValidateSet('start', 'stop', 'status', 'logs')]
    [string]$Command = 'start',
    [string]$Service = ''
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$LogDir = Join-Path $Root 'logs'
$StateFile = Join-Path $LogDir 'runstate.json'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'
$RedisDir = "$env:LOCALAPPDATA\omnixa-dev-tools\redis"
$Node = (Get-Command node -ErrorAction SilentlyContinue).Source
$ViteJs = Join-Path $Root 'node_modules\vite\bin\vite.js'
$MySqlService = 'mysql'

function Write-Step([string]$Msg, [string]$Color = 'Cyan') {
    Write-Host "[dev-up] $Msg" -ForegroundColor $Color
}

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Get-TrackedState {
    if (Test-Path $StateFile) {
        try {
            $json = Get-Content $StateFile -Raw | ConvertFrom-Json
            $state = @{}
            foreach ($prop in $json.PSObject.Properties) { $state[$prop.Name] = $prop.Value }
            return $state
        } catch { return @{} }
    }
    return @{}
}

function Save-TrackedState([hashtable]$State) {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
    $State | ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8
}

function Start-Logged([string]$Name, [string]$FilePath, [string[]]$ProcArgs, [string]$WorkDir) {
    $out = Join-Path $LogDir "$Name.out.log"
    $err = Join-Path $LogDir "$Name.err.log"
    $proc = Start-Process -FilePath $FilePath -ArgumentList $ProcArgs -WorkingDirectory $WorkDir `
        -RedirectStandardOutput $out -RedirectStandardError $err `
        -WindowStyle Hidden -PassThru
    return $proc.Id
}

function Test-WorkerRunning {
    return [bool](Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
        Where-Object { $_.CommandLine -match 'app\.worker' })
}

function Get-MySqlService {
    return Get-Service -Name $MySqlService -ErrorAction SilentlyContinue
}

switch ($Command) {
    'start' {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
        $state = Get-TrackedState

        # 1. MySQL (external dependency; only ensure it is running)
        if (Test-Port 3306) {
            Write-Step 'MySQL already listening on 3306 (skip)' 'Green'
        } else {
            $svc = Get-MySqlService
            if ($null -eq $svc) {
                throw "MySQL is not listening on 3306 and no Windows service named '$MySqlService' was found. Start MySQL manually first."
            }
            Write-Step "starting MySQL service '$MySqlService'..."
            try {
                Start-Service -Name $MySqlService
            } catch {
                throw "Failed to start MySQL service (admin rights may be required): $($_.Exception.Message)"
            }
            Start-Sleep -Seconds 3
            if (-not (Test-Port 3306)) {
                throw 'MySQL service started but port 3306 is still not ready. Check the MySQL configuration.'
            }
            Write-Step 'MySQL is up (3306).' 'Green'
        }

        # 2. Redis
        if (Test-Port 6379) {
            Write-Step 'Redis already listening on 6379 (skip)' 'Green'
        } else {
            if (-not (Test-Path (Join-Path $RedisDir 'redis-server.exe'))) {
                throw "redis-server.exe not found at $RedisDir"
            }
            Write-Step 'starting Redis (AOF preserved)...'
            $state['redis'] = Start-Logged 'redis' (Join-Path $RedisDir 'redis-server.exe') `
                @('--port', '6379', '--bind', '127.0.0.1', '--appendonly', 'yes', '--appendfsync', 'everysec', '--dir', './data') `
                $RedisDir
            Start-Sleep -Seconds 2
        }

        # 3. Backend (8010)
        if (Test-Port 8010) {
            Write-Step 'Backend already listening on 8010 (skip)' 'Green'
        } else {
            if (-not (Test-Path $Python)) { throw "backend venv python not found: $Python" }
            Write-Step 'starting Backend (uvicorn 8010)...'
            $state['backend'] = Start-Logged 'backend' $Python `
                @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8010') `
                $Backend
            Start-Sleep -Seconds 3
        }

        # 4. Worker
        if (Test-WorkerRunning) {
            Write-Step 'worker already running (skip)' 'Green'
        } else {
            if (-not (Test-Path $Python)) { throw "backend venv python not found: $Python" }
            Write-Step 'starting document worker...'
            $state['worker'] = Start-Logged 'worker' $Python @('-m', 'app.worker') $Backend
        }

        # 5. Frontend (5173)
        if (Test-Port 5173) {
            Write-Step 'Frontend already listening on 5173 (skip)' 'Green'
        } else {
            if (-not $Node) { throw 'node.exe is not on PATH.' }
            if (-not (Test-Path $ViteJs)) { throw "vite is not installed, missing $ViteJs" }
            Write-Step 'starting Frontend (vite 5173)...'
            $state['frontend'] = Start-Logged 'frontend' $Node @($ViteJs) $Root
            Start-Sleep -Seconds 3
        }

        Save-TrackedState $state
        Write-Step ''
        Write-Step 'All components are up:' 'Green'
        Write-Step '  MySQL    : 127.0.0.1:3306' 'White'
        Write-Step '  Redis    : 127.0.0.1:6379' 'White'
        Write-Step '  Backend  : http://127.0.0.1:8010  (/health /ready)' 'White'
        Write-Step '  Worker   : background (document-processing)' 'White'
        Write-Step '  Frontend : http://127.0.0.1:5173' 'White'
        Write-Step "  Logs dir : $LogDir" 'White'
        Write-Step '  Status   : powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 status' 'White'
    }

    'stop' {
        $state = Get-TrackedState
        $stopped = New-Object System.Collections.Generic.List[string]

        foreach ($name in @('frontend', 'backend', 'worker', 'redis')) {
            $trackedPid = $state[$name]
            if ($trackedPid -and (Get-Process -Id $trackedPid -ErrorAction SilentlyContinue)) {
                Stop-Process -Id $trackedPid -Force -ErrorAction SilentlyContinue
                $stopped.Add($name)
            }
        }

        # Fallback: clean up processes the script started but lost track of,
        # matched by command-line signature.
        $patterns = [ordered]@{
            'frontend' = 'node_modules\\vite'
            'backend'  = 'uvicorn.*app\.main'
            'worker'   = 'app\.worker'
            'redis'    = 'omnixa-dev-tools.*redis-server'
        }
        $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine }
        foreach ($entry in $patterns.GetEnumerator()) {
            if ($stopped.Contains($entry.Key)) { continue }
            foreach ($proc in $procs) {
                if ($proc.CommandLine -match $entry.Value) {
                    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
                    if (-not $stopped.Contains($entry.Key)) { $stopped.Add($entry.Key) }
                }
            }
        }

        if (Test-Path $StateFile) { Remove-Item $StateFile -ErrorAction SilentlyContinue }

        if ($stopped.Count -eq 0) {
            Write-Step 'Nothing to stop (script-managed app processes are already down).' 'Yellow'
        } else {
            Write-Step "Stopped: $($stopped -join ', ')" 'Green'
        }
        Write-Step 'MySQL was NOT stopped (shared BT-panel service). To stop it manually (admin): Stop-Service mysql' 'Yellow'
    }

    'status' {
        $state = Get-TrackedState
        $mysqlSvc = Get-MySqlService
        $rows = @(
            [pscustomobject]@{
                Service = 'mysql'; Port = 3306; Running = (Test-Port 3306)
                Detail = if ($mysqlSvc) { "service=$($mysqlSvc.Status)" } else { 'no service' }
            },
            [pscustomobject]@{ Service = 'redis'; Port = 6379; Running = (Test-Port 6379); Detail = '' },
            [pscustomobject]@{ Service = 'backend'; Port = 8010; Running = (Test-Port 8010); Detail = '' },
            [pscustomobject]@{ Service = 'worker'; Port = '-'; Running = (Test-WorkerRunning); Detail = '' },
            [pscustomobject]@{ Service = 'frontend'; Port = 5173; Running = (Test-Port 5173); Detail = '' }
        )
        foreach ($row in $rows) {
            if ($state[$row.Service]) { $row.Detail = "$($row.Detail) pid=$($state[$row.Service])".TrimStart(' ') }
        }
        $rows | Format-Table @{Label='Service';Expression={$_.Service}},
            @{Label='Port';Expression={$_.Port}},
            @{Label='Running';Expression={if($_.Running){'UP'}else{'DOWN'}}},
            @{Label='Detail';Expression={$_.Detail}} -AutoSize
    }

    'logs' {
        $names = if ($Service) { @($Service) } else { @('redis', 'worker', 'backend', 'frontend') }
        foreach ($name in $names) {
            $found = $false
            foreach ($ext in @('.err.log', '.out.log')) {
                $file = Join-Path $LogDir "$name$ext"
                if (Test-Path $file) {
                    $found = $true
                    Write-Host "`n===== $name$ext (last 30 lines) =====" -ForegroundColor Cyan
                    Get-Content $file -Tail 30
                }
            }
            if (-not $found) {
                Write-Step "no logs for '$name' under $LogDir" 'Yellow'
            }
        }
        Write-Step 'MySQL logs are managed by the BT-panel service and are not captured by this script.' 'White'
    }
}
