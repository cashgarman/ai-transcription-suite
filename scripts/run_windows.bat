@echo off
setlocal
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PATH=%~dp0..\.venv\Lib\site-packages\nvidia\cudnn\bin;%PATH%"
    set "PATH=%~dp0..\.venv\Lib\site-packages\nvidia\cublas\bin;%PATH%"
    ".venv\Scripts\python.exe" -m speaker_transcriber.app
) else if exist "venv_summarizer\Scripts\python.exe" (
    "venv_summarizer\Scripts\python.exe" -m speaker_transcriber.app
) else (
    py -3.11 -m speaker_transcriber.app
)

if errorlevel 1 (
    echo.
    echo Speaker Transcriber exited with an error. See the application log for details.
    pause
)
