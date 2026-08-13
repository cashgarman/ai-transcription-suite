<#
.SYNOPSIS
    Manages the Summit marketing website in website/ on a local machine.

.DESCRIPTION
    Wraps the npm scripts with process tracking so the dev or production server
    can be started in the background, inspected, and stopped again without
    hunting for a stray node.exe.

.PARAMETER Command
    install   Install npm dependencies.
    dev       Run the dev server in the foreground with hot reload.
    serve     Run the dev server in the background and return.
    build     Produce a production build.
    start     Build if needed, then run the production server in the background.
    stop      Stop whichever server this script started.
    restart   Stop, then start the production server again.
    status    Report whether a server is running and on which port.
    logs      Print the background server log.
    open      Open the running site in the default browser.
    lint      Run eslint.
    check     Run the TypeScript compiler with no emit.
    clean     Remove .next, the log, and the pid file.
    reset     clean, plus remove node_modules.

.PARAMETER Port
    TCP port for dev/serve/start. Defaults to 3100.

.PARAMETER Bind
    Interface to listen on. Defaults to 0.0.0.0 so phones and tablets on
    the LAN can reach the site.

.EXAMPLE
    .\scripts\website.ps1 start

.EXAMPLE
    .\scripts\website.ps1 start -Port 4000 -Bind 127.0.0.1
#>

[CmdletBinding()]
param
(
    [Parameter(Position = 0)]
    [ValidateSet(
        'install', 'dev', 'serve', 'build', 'start', 'stop', 'restart',
        'status', 'logs', 'open', 'lint', 'check', 'clean', 'reset'
    )]
    [string] $Command = 'status',

    [int] $Port = 3100,

    [string] $Bind = '0.0.0.0',

    [switch] $Follow
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SiteDir = Join-Path $ProjectRoot 'website'
$PidFile = Join-Path $SiteDir '.website-server.pid'
$LogFile = Join-Path $SiteDir '.website-server.log'
$BuildDir = Join-Path $SiteDir '.next'

function Write-Step([string] $Message)
{
    Write-Host "  $Message" -ForegroundColor Cyan
}

function Write-Note([string] $Message)
{
    Write-Host "  $Message" -ForegroundColor DarkGray
}

function Write-Problem([string] $Message)
{
    Write-Host "  $Message" -ForegroundColor Yellow
}

function Assert-SiteDirectory
{
    if (-not (Test-Path $SiteDir))
    {
        throw "No website directory at $SiteDir."
    }
}

function Assert-Npm
{
    if (-not (Get-Command npm -ErrorAction SilentlyContinue))
    {
        throw 'npm was not found on PATH. Install Node.js 20 or newer.'
    }
}

function Invoke-Npm([string[]] $Arguments)
{
    Push-Location $SiteDir
    try
    {
        & npm @Arguments
        if ($LASTEXITCODE -ne 0)
        {
            throw "npm $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
        }
    }
    finally
    {
        Pop-Location
    }
}

function Install-IfNeeded
{
    if (-not (Test-Path (Join-Path $SiteDir 'node_modules')))
    {
        Write-Step 'Installing dependencies (first run).'
        Invoke-Npm @('install')
    }
}

function Get-TrackedProcess
{
    if (-not (Test-Path $PidFile))
    {
        return $null
    }

    $recorded = (Get-Content $PidFile -Raw).Trim()
    $parsed = 0
    if (-not [int]::TryParse($recorded, [ref] $parsed))
    {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $process = Get-Process -Id $parsed -ErrorAction SilentlyContinue
    if ($null -eq $process)
    {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    return $process
}

function Get-LanIpv4
{
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and
            $_.PrefixOrigin -ne 'WellKnown'
        } |
        Select-Object -ExpandProperty IPAddress -Unique
}

function Write-ListenUrls([int] $TargetPort, [string] $ListenAddress)
{
    Write-Host "  Ready at http://127.0.0.1:$TargetPort" -ForegroundColor Green
    if ($ListenAddress -eq '0.0.0.0' -or $ListenAddress -eq '::')
    {
        foreach ($ip in (Get-LanIpv4))
        {
            Write-Host "  LAN    http://${ip}:$TargetPort" -ForegroundColor Green
        }
    }
    elseif ($ListenAddress -ne '127.0.0.1' -and $ListenAddress -ne 'localhost')
    {
        Write-Host "  Bound  http://${ListenAddress}:$TargetPort" -ForegroundColor Green
    }
}

function Ensure-WebsiteFirewall([int] $TargetPort)
{
    try
    {
        $name = "Summit website $TargetPort"
        $existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
        if ($null -eq $existing)
        {
            New-NetFirewallRule `
                -DisplayName $name `
                -Direction Inbound `
                -Protocol TCP `
                -LocalPort $TargetPort `
                -Action Allow `
                -Profile Any `
                -ErrorAction Stop |
                Out-Null
            Write-Note "Opened Windows Firewall for inbound TCP $TargetPort."
        }
    }
    catch
    {
        Write-Note "Could not add a firewall rule (often needs Administrator). If other devices cannot connect, allow TCP $TargetPort inbound."
    }
}

function Get-PortOwner([int] $TargetPort)
{
    $connection = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $connection)
    {
        return $null
    }

    return Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
}

function Start-Background([string] $NpmScript, [int] $TargetPort, [string] $ListenAddress)
{
    $existing = Get-TrackedProcess
    if ($null -ne $existing)
    {
        Write-Problem "A server is already running (pid $($existing.Id)). Stop it first."
        return
    }

    $portOwner = Get-PortOwner $TargetPort
    if ($null -ne $portOwner)
    {
        Write-Problem "Port $TargetPort is already in use by $($portOwner.ProcessName) (pid $($portOwner.Id))."
        return
    }

    if ($ListenAddress -eq '0.0.0.0' -or $ListenAddress -eq '::')
    {
        Ensure-WebsiteFirewall $TargetPort
    }

    Remove-Item $LogFile -Force -ErrorAction SilentlyContinue

    # cmd.exe owns the redirection here. PowerShell's own -RedirectStandardOutput
    # keeps handles open and can stop this script from exiting.
    $commandLine = "/c npm run $NpmScript -- --hostname $ListenAddress --port $TargetPort > `"$LogFile`" 2>&1"
    $process = Start-Process `
        -FilePath $env:ComSpec `
        -ArgumentList $commandLine `
        -WorkingDirectory $SiteDir `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -Path $PidFile -Value $process.Id -Encoding ascii

    Write-Step "Started '$NpmScript' in the background (pid $($process.Id))."
    Wait-ForPort $TargetPort $ListenAddress
}

function Wait-ForPort([int] $TargetPort, [string] $ListenAddress)
{
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline)
    {
        if ($null -ne (Get-PortOwner $TargetPort))
        {
            Write-ListenUrls $TargetPort $ListenAddress
            return
        }

        $tracked = Get-TrackedProcess
        if ($null -eq $tracked)
        {
            Write-Problem 'The server exited during startup. Recent output:'
            Show-Logs
            return
        }

        Start-Sleep -Milliseconds 400
    }

    Write-Problem "Port $TargetPort did not open within 60 seconds. Check the log with: website.ps1 logs"
}

function Stop-Server
{
    $process = Get-TrackedProcess
    if ($null -eq $process)
    {
        Write-Note 'No tracked server is running.'
        return
    }

    Write-Step "Stopping pid $($process.Id) and its children."
    & taskkill /PID $process.Id /T /F | Out-Null
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host '  Stopped.' -ForegroundColor Green
}

function Show-Status([int] $TargetPort)
{
    $process = Get-TrackedProcess
    if ($null -eq $process)
    {
        Write-Note 'Tracked server: not running.'
    }
    else
    {
        $uptime = (Get-Date) - $process.StartTime
        Write-Host "  Tracked server: running (pid $($process.Id), up $([int]$uptime.TotalMinutes)m)." -ForegroundColor Green
    }

    $owner = Get-PortOwner $TargetPort
    if ($null -eq $owner)
    {
        Write-Note "Port $TargetPort : free."
    }
    else
    {
        Write-Host "  Port $TargetPort : listening ($($owner.ProcessName), pid $($owner.Id))" -ForegroundColor Green
        Write-ListenUrls $TargetPort $Bind
    }

    if (Test-Path (Join-Path $SiteDir 'node_modules'))
    {
        Write-Note 'Dependencies: installed.'
    }
    else
    {
        Write-Problem "Dependencies: missing. Run: website.ps1 install"
    }

    if (Test-Path $BuildDir)
    {
        $built = (Get-Item $BuildDir).LastWriteTime
        Write-Note "Production build: last written $built."
    }
    else
    {
        Write-Note 'Production build: none.'
    }
}

function Show-Logs
{
    foreach ($path in @($LogFile))
    {
        if (Test-Path $path)
        {
            $content = Get-Content $path -Tail 40
            if ($content)
            {
                Write-Host "  --- $(Split-Path -Leaf $path) ---" -ForegroundColor DarkGray
                $content | ForEach-Object { Write-Host "  $_" }
            }
        }
    }
}

Assert-SiteDirectory
Assert-Npm

switch ($Command)
{
    'install'
    {
        Write-Step 'Installing dependencies.'
        Invoke-Npm @('install')
    }

    'dev'
    {
        Install-IfNeeded
        if ($Bind -eq '0.0.0.0' -or $Bind -eq '::')
        {
            Ensure-WebsiteFirewall $Port
        }
        Write-Step "Dev server on $Bind`:$Port (Ctrl+C to stop)."
        Write-ListenUrls $Port $Bind
        Invoke-Npm @('run', 'dev', '--', '--hostname', $Bind, '--port', "$Port")
    }

    'serve'
    {
        Install-IfNeeded
        Start-Background 'dev' $Port $Bind
    }

    'build'
    {
        Install-IfNeeded
        Write-Step 'Building for production.'
        Invoke-Npm @('run', 'build')
    }

    'start'
    {
        Install-IfNeeded
        if (-not (Test-Path $BuildDir))
        {
            Write-Step 'No build found; building first.'
            Invoke-Npm @('run', 'build')
        }
        Start-Background 'start' $Port $Bind
    }

    'stop'
    {
        Stop-Server
    }

    'restart'
    {
        Stop-Server
        Start-Sleep -Seconds 2
        Install-IfNeeded
        Invoke-Npm @('run', 'build')
        Start-Background 'start' $Port $Bind
    }

    'status'
    {
        Show-Status $Port
    }

    'logs'
    {
        if ($Follow)
        {
            if (-not (Test-Path $LogFile))
            {
                Write-Note 'No log yet.'
            }
            else
            {
                Get-Content $LogFile -Wait -Tail 40
            }
        }
        else
        {
            Show-Logs
        }
    }

    'open'
    {
        if ($null -eq (Get-PortOwner $Port))
        {
            Write-Problem "Nothing is listening on port $Port. Start it with: website.ps1 serve"
        }
        else
        {
            Start-Process "http://localhost:$Port"
        }
    }

    'lint'
    {
        Install-IfNeeded
        Invoke-Npm @('run', 'lint')
    }

    'check'
    {
        Install-IfNeeded
        Push-Location $SiteDir
        try
        {
            & npx tsc --noEmit
            if ($LASTEXITCODE -ne 0)
            {
                throw "TypeScript reported errors."
            }
            Write-Host '  No type errors.' -ForegroundColor Green
        }
        finally
        {
            Pop-Location
        }
    }

    'clean'
    {
        Stop-Server
        foreach ($path in @($BuildDir, $LogFile, "$LogFile.err", $PidFile))
        {
            if (Test-Path $path)
            {
                Remove-Item $path -Recurse -Force
                Write-Note "Removed $(Split-Path -Leaf $path)."
            }
        }
    }

    'reset'
    {
        Stop-Server
        foreach ($path in @($BuildDir, $LogFile, "$LogFile.err", $PidFile, (Join-Path $SiteDir 'node_modules')))
        {
            if (Test-Path $path)
            {
                Remove-Item $path -Recurse -Force
                Write-Note "Removed $(Split-Path -Leaf $path)."
            }
        }
    }
}
