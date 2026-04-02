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
        echo Impossible de creer l'environnement virtuel.
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
    echo Installation / verification des dependances...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet --upgrade pip
    if errorlevel 1 (
        echo.
        echo Echec de la mise a jour de pip.
        pause
        exit /b 1
    )

    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Echec de l'installation des dependances.
        pause
        exit /b 1
    )

    type nul > "%REQ_STAMP%"
)

if exist "%RUN_ERR_LOG%" del /f /q "%RUN_ERR_LOG%" >nul 2>nul

echo Lancement du programme...
".venv\Scripts\python.exe" main.py 2>"%RUN_ERR_LOG%"

if errorlevel 1 (
    echo.
    echo Le programme s'est arrete avec une erreur.
    if exist "%RUN_ERR_LOG%" (
        echo.
        type "%RUN_ERR_LOG%"
    )
    pause
)

if exist "%RUN_ERR_LOG%" del /f /q "%RUN_ERR_LOG%" >nul 2>nul

endlocal
