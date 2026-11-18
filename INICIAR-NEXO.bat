@echo off
title NEXO S2
cd /d "%~dp0"
echo Iniciando Nexo S2...
echo No cierre esta ventana mientras use los sistemas.
echo.
where py >nul 2>nul
if %errorlevel%==0 (py -3 nexo.py) else (python nexo.py)
pause
