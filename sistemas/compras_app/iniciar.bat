@echo off
rem INICIAR EN WINDOWS (doble clic)
rem run.py hace todo: prepara el entorno la primera vez (crea .venv e instala las librerias),
rem elige un puerto libre y abre el navegador. Este archivo solo lo llama.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 run.py) else (python run.py)
pause
