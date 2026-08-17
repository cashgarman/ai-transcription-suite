@echo off

setlocal EnableDelayedExpansion

cd /d "%~dp0.."

set "EXITCODE=0"



rem Prefer PowerShell so Ctrl+C does not leave cmd's "Terminate batch job (Y/N)?" prompt.

where powershell >nul 2>&1

if not errorlevel 1 (

    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_windows.ps1"

    set "EXITCODE=!ERRORLEVEL!"

    goto handle_exit

)



set "PYTHON="

set "PYARGS="

if exist ".venv\Scripts\python.exe" (

    set "PYTHON=.venv\Scripts\python.exe"

    set "PATH=%~dp0..\.venv\Lib\site-packages\nvidia\cudnn\bin;%PATH%"

    set "PATH=%~dp0..\.venv\Lib\site-packages\nvidia\cublas\bin;%PATH%"

) else if exist "venv_summarizer\Scripts\python.exe" (

    set "PYTHON=venv_summarizer\Scripts\python.exe"

) else (

    set "PYTHON=py"

    set "PYARGS=-3.12"

)



if not defined PYTHON (

    echo No Python environment found.

    exit /b 1

)



"%PYTHON%" %PYARGS% -m pip show cryptography >nul 2>&1

if errorlevel 1 (

    echo Installing missing dependency: cryptography...

    "%PYTHON%" %PYARGS% -m pip install "cryptography>=43"

)



rem start /wait keeps Ctrl+C in the child process and avoids the batch prompt.

start "" /wait "%PYTHON%" %PYARGS% -m speaker_transcriber.app

set "EXITCODE=!ERRORLEVEL!"



:handle_exit

if !EXITCODE! EQU 130 exit /b 130

if !EXITCODE! GEQ 1 (

    echo.

    echo Speaker Transcriber exited with an error. See the application log for details.

    pause

)

exit /b !EXITCODE!

