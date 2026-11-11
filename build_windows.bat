@echo off
rem Double-click to build FolderLock.exe on Windows (needs Python 3.12 from python.org installed).
cd /d "%~dp0"
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :error
python build.py || goto :error
echo.
echo Done. Your portable program is: %~dp0dist\FolderLock.exe
pause
exit /b 0
:error
echo.
echo Build failed - see the messages above.
pause
exit /b 1
