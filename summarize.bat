@echo off
:: Activate the virtual environment
call .\venv_summarizer\Scripts\activate.bat

:: Run the CLI script with all arguments
python summarize.py %*

:: Deactivate the virtual environment
call deactivate 