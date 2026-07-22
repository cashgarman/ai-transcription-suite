@echo off
:: Activate the virtual environment
call .\venv_summarizer\Scripts\activate.bat

:: Run the GUI application
python summarize_gui.py

:: Deactivate the virtual environment
call deactivate 