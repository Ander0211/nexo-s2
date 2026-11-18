@echo off
title SENTINEL PABON
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
echo SENTINEL PABON
echo Carpeta: %cd%
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  py -c "import openpyxl" >nul 2>&1
  if errorlevel 1 (
    echo Instalando openpyxl...
    py -m pip install --user openpyxl
  )
  echo Abra: http://localhost:8080
  echo No cierre esta ventana.
  echo.
  py -u server.py
  goto :fin
)

where python >nul 2>&1
if %errorlevel%==0 (
  python -c "import openpyxl" >nul 2>&1
  if errorlevel 1 (
    echo Instalando openpyxl...
    python -m pip install --user openpyxl
  )
  echo Abra: http://localhost:8080
  echo No cierre esta ventana.
  echo.
  python -u server.py
  goto :fin
)

echo.
echo Python no esta instalado o no esta en el PATH.
echo 1. Descargue: https://www.python.org/downloads/
echo 2. Ejecute el instalador.
echo 3. MARQUE la casilla "Add python.exe to PATH"
echo 4. Instale y vuelva a abrir este archivo.
echo.
pause
exit /b 1

:fin
echo.
echo SENTINEL PABON se detuvo.
pause
