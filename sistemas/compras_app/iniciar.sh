#!/usr/bin/env bash
# INICIAR EN LINUX / macOS
# run.py hace todo: prepara el entorno la primera vez (crea .venv e instala las librerías),
# elige un puerto libre y abre el navegador. Este archivo solo lo llama.
cd "$(dirname "$0")"   # ir a la carpeta donde está este archivo
exec python3 run.py
