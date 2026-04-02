@echo off
setlocal
cd /d "%~dp0"

set "NEEDS_INSTALL=0"
set "REQ_STAMP=.venv\.requirements_installed"
set "RUN_ERR_LOG=.run_stderr.log"

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3.12 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 (
        echo.
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
    set "NEEDS_INSTALL=1"
)

if not exist "%REQ_STAMP%" set "NEEDS_INSTALL=1"

powershell -NoProfile -Command ^
    "if ((Test-Path '%REQ_STAMP%') -and ((Get-Item 'requirements.txt').LastWriteTime -gt (Get-Item '%REQ_STAMP%').LastWriteTime)) { exit 0 } else { exit 1 }"
if %errorlevel%==0 set "NEEDS_INSTALL=1"

if "%NEEDS_INSTALL%"=="1" (
    echo Installing / verifying dependencies...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet --upgrade pip
    if errorlevel 1 (
        echo.
        echo Failed to upgrade pip.
        pause
        exit /b 1
    )

    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Failed to install dependencies.
        pause
        exit /b 1
    )

    type nul > "%REQ_STAMP%"
)

if exist "%RUN_ERR_LOG%" del /f /q "%RUN_ERR_LOG%" >nul 2>nul

echo Launching the app...
".venv\Scripts\python.exe" main.py 2>"%RUN_ERR_LOG%"

if errorlevel 1 (
    echo.
    echo The app stopped with an error.
    if exist "%RUN_ERR_LOG%" (
        echo.
        type "%RUN_ERR_LOG%"
    )
    pause
)

if exist "%RUN_ERR_LOG%" del /f /q "%RUN_ERR_LOG%" >nul 2>nul

endlocal
