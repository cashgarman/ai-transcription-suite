@echo off
:: Activate the virtual environment
call .\venv\Scripts\activate.bat

:: Run the GUI application
python transcriber_launcher.py

:: Deactivate the virtual environment
call deactivate 