@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
if errorlevel 1 (
    echo.
    echo RaporPro Python 3.11 gerektirir.
    echo Kullanilan Python: %PYTHON_EXE%
    echo Isterseniz proje klasorunde yalitilmis ortam olusturun:
    echo py -3.11 -m venv .venv
    pause
    exit /b 1
)

:CHECK_PACKAGES
"%PYTHON_EXE%" -c "from ortam_kontrolu import print_cli_dependency_report; raise SystemExit(print_cli_dependency_report())"
if errorlevel 1 (
    echo.
    choice /C EH /N /M "Eksik paketleri requirements.txt ile kurmak ister misiniz? [E/H] "
    if errorlevel 2 goto START_APP
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Paket kurulumu basarisiz oldu.
        pause
        exit /b 1
    )
)

:START_APP
"%PYTHON_EXE%" main.py
if errorlevel 1 (
    echo.
    echo RaporPro baslatilamadi. Detay icin su dosyaya bakin:
    echo %LOCALAPPDATA%\RaporPro\logs\error.log
    echo Kullanilan Python: %PYTHON_EXE%
    pause
)
