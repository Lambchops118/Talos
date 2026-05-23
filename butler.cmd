@echo off
setlocal
set SCRIPT_DIR=%~dp0

if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%\.venv\Scripts\python.exe" "%SCRIPT_DIR%\InfoPanel\chat_client.py" %*
) else (
    py -3 "%SCRIPT_DIR%\InfoPanel\chat_client.py" %*
)
