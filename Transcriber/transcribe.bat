@echo off
:: Activate the virtual environment
call .\venv\Scripts\activate.bat

:: Run the transcribe.py script with all arguments
python transcribe.py %*

:: Deactivate the virtual environment
call deactivate 