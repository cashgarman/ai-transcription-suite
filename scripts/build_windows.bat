@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Create the project virtual environment first:
    echo   py -3.11 -m venv .venv
    echo   .\.venv\Scripts\Activate.ps1
    echo   pip install -e ".[dev]"
    exit /b 1
)

echo Building Speaker Transcriber standalone executable...
".venv\Scripts\python.exe" -m pip install -e ".[dev]" >nul
".venv\Scripts\pyinstaller.exe" --clean -y speaker_transcriber.spec
if errorlevel 1 (
    echo.
    echo Build failed. See the PyInstaller output above.
    exit /b 1
)

echo.
echo Build complete.
echo Launch: dist\SpeakerTranscriber\SpeakerTranscriber.exe
echo.
echo Notes:
echo - FFmpeg must still be installed and available on PATH.
echo - Model weights are downloaded on first use to the normal local caches.
echo - Copy the entire dist\SpeakerTranscriber folder when distributing.
