# Launch Summit from PowerShell without cmd.exe's "Terminate batch job (Y/N)?" prompt.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$python = $null
$pyArgs = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $env:PATH = (Join-Path $PWD ".venv\Lib\site-packages\nvidia\cudnn\bin") + ";" + $env:PATH
    $env:PATH = (Join-Path $PWD ".venv\Lib\site-packages\nvidia\cublas\bin") + ";" + $env:PATH
    $python = Join-Path $PWD ".venv\Scripts\python.exe"
} elseif (Test-Path "venv_summarizer\Scripts\python.exe") {
    $python = Join-Path $PWD "venv_summarizer\Scripts\python.exe"
} else {
    $python = "py"
    $pyArgs = @("-3.12")
}

if ($null -eq $python) {
    Write-Error "No Python environment found."
    exit 1
}

function Invoke-Python {
    param([string[]]$Arguments)
    if ($pyArgs) {
        & $python @pyArgs @Arguments
    } else {
        & $python @Arguments
    }
}

$pipCheck = Invoke-Python @("-m", "pip", "show", "cryptography")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing missing dependency: cryptography..."
    Invoke-Python @("-m", "pip", "install", "cryptography>=43")
}

Invoke-Python @("-m", "speaker_transcriber.app")
exit $LASTEXITCODE
