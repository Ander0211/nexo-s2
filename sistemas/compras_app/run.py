"""
INICIAR LA APLICACIÓN
=====================
Ejecuta:   python run.py          (o doble clic en iniciar.bat en Windows)

Este archivo se ocupa de que la aplicación arranque SIN errores, aunque sea la primera vez:

    1. LIBRERÍAS: si faltan (uvicorn, fastapi, pandas...), prepara solo el entorno: crea la carpeta .venv e instala
       requirements.txt (la primera vez tarda 1 o 2 minutos y necesita internet), y se vuelve a ejecutar con ese entorno.
       Así ya no sale «No module named uvicorn», ni siquiera si una instalación anterior quedó a medias.
    2. PUERTO: prueba el 8000 y, si Windows lo tiene bloqueado u ocupado (error «WinError 10013»), usa otro libre.
    3. CARPETA: funciona lo ejecutes desde donde lo ejecutes (no hace falta estar dentro de la carpeta del proyecto).
    4. Enciende el servidor web (uvicorn) con la aplicación de app/main.py y abre el navegador en la dirección correcta.

Opciones:
    python run.py --recargar     (para programadores) reinicia el servidor solo cada vez que guardas un archivo.
    COMPRAS_PUERTO=9000          variable de entorno para pedir un puerto concreto (si está libre).
    COMPRAS_HOST=127.0.0.1       por defecto la aplicación queda visible en la red local (0.0.0.0): otros equipos entran con
                                 http://<IP de este equipo>:8000. Con 127.0.0.1 solo se puede usar en este computador.

Para detenerla: Ctrl+C en la terminal.
"""

import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
import venv
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent  # la carpeta donde está este archivo (la raíz del proyecto)
# 0.0.0.0 = «toda la red»: otros equipos de la Clínica pueden entrar con http://<IP de este equipo>:8000 (hay inicio de sesión).
# Para que SOLO se pueda usar en este computador, define la variable COMPRAS_HOST=127.0.0.1
HOST = os.environ.get("COMPRAS_HOST", "0.0.0.0")
PUERTO_PREFERIDO = 8000
# Librerías sin las cuales la aplicación no arranca (se comprueba que se puedan importar). «PIL» es Pillow: sin ella los Excel con logos
# (la ficha de cotización) salen sin imágenes. Estar en esta lista hace que un .venv anterior, que no la tenía, se complete solo al arrancar.
LIBRERIAS = ("uvicorn", "fastapi", "pandas", "openpyxl", "pydantic", "PIL")


def _puerto_disponible(puerto: int) -> bool:
    """¿Se puede abrir este puerto? Se intenta reservarlo un instante.

    Falla (devuelve False) tanto si otro programa lo está usando como si Windows lo tiene bloqueado
    (el error «WinError 10013 … permisos de acceso», típico de Docker, WSL o Hyper-V).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, puerto))
        except OSError:
            return False
    return True


def elegir_puerto(preferido: int = PUERTO_PREFERIDO) -> int:
    """Devuelve el puerto a usar: el preferido si se puede y, si no, uno libre que le pide al sistema operativo."""
    if _puerto_disponible(preferido):
        return preferido
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))  # el puerto 0 significa «dame cualquiera que esté libre y permitido»
        return s.getsockname()[1]


def _faltan_librerias() -> list[str]:
    """Las librerías necesarias que este Python NO tiene instaladas (lista vacía = todo en orden)."""
    return [nombre for nombre in LIBRERIAS if importlib.util.find_spec(nombre) is None]


def _python_del_entorno() -> Path:
    """Dónde está (o estaría) el Python de la carpeta .venv de este proyecto; la ruta cambia según el sistema."""
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return RAIZ / ".venv" / sub


def _entorno_completo(python: Path) -> bool:
    """¿Ese Python (el de .venv) ya tiene todas las librerías? Se comprueba ejecutándolo de verdad."""
    if not python.exists():
        return False
    codigo = "import " + ", ".join(LIBRERIAS)
    return subprocess.run([str(python), "-c", codigo], capture_output=True).returncode == 0


def _preparar_entorno() -> Path:
    """Crea .venv (si no existe o quedó a medias) e instala requirements.txt. Devuelve el Python de ese entorno."""
    python = _python_del_entorno()
    if not python.exists():
        print("Primera vez: creando el entorno (carpeta .venv)...")
        # clear=True borra un .venv que quedó a medias de un intento anterior.
        venv.EnvBuilder(with_pip=True, clear=(RAIZ / ".venv").exists()).create(RAIZ / ".venv")
    print("Instalando las librerías (1 o 2 minutos; necesita internet)...")
    resultado = subprocess.run([str(python), "-m", "pip", "install", "-r", str(RAIZ / "requirements.txt")])
    if resultado.returncode != 0:
        sys.exit(
            "\nNo se pudieron instalar las librerías. Revisa tu conexión a internet y vuelve a ejecutar.\n"
            "Si el problema sigue, copia el mensaje de error de arriba."
        )
    return python


def esperar_servidor(host: str, puerto: int, limite: float = 90.0) -> bool:
    """Espera, hasta `limite` segundos, a que el servidor ACEPTE CONEXIONES (cuando ya terminó de arrancar: crear la base, importar los Excel la
    primera vez...). Devuelve True si ya está listo y False si se acabó el tiempo. Antes el navegador se abría a los 1,5 s fijos, y en un equipo
    lento llegaba a un servidor que todavía no existía: la página salía «no se puede acceder» y luego «se restablecía» sola."""
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        try:
            socket.create_connection((host, puerto), timeout=0.3).close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def _abrir_cuando_este_lista(url: str, puerto: int) -> None:
    """Se ejecuta en otro hilo: cuando el servidor ya responde, avisa «lista» y abre el navegador (nunca antes)."""
    if esperar_servidor("127.0.0.1", puerto):
        print(
            f"\n  SUMIPABON lista en {url}\n  (si el navegador no se abre solo, copia esa dirección)\n  Para detenerla: Ctrl+C\n"
        )
        webbrowser.open(url)
    else:
        print("\n  El servidor no respondió en 90 segundos. Revisa los mensajes de arriba: ahí debe decir qué falló.\n")


def _servir(recargar: bool) -> None:
    """Elige el puerto, abre el navegador y enciende el servidor (esta función no regresa hasta que se detiene)."""
    import uvicorn

    os.chdir(RAIZ)  # para que «app.main» y los archivos de data/ se encuentren desde cualquier carpeta
    sys.path.insert(0, str(RAIZ))
    pedido = int(os.environ.get("COMPRAS_PUERTO", PUERTO_PREFERIDO))
    puerto = elegir_puerto(pedido)
    if puerto != pedido:
        print(f"El puerto {pedido} no está disponible (ocupado o bloqueado por Windows): se usará el {puerto}.")
    url = f"http://127.0.0.1:{puerto}"  # la dirección para ESTE equipo (los demás usan la IP de la red)
    print("\n  Iniciando SUMIPABON... (la primera vez tarda unos segundos: prepara la base de datos)\n")
    if HOST == "0.0.0.0":
        print(
            f"  Otros equipos de la red entran con  http://<la IP de este equipo>:{puerto}  (mírala con «ipconfig»).\n"
        )
    if "onedrive" in str(RAIZ).lower():
        print(
            "  Consejo: esta carpeta está dentro de OneDrive, que a veces vuelve todo lento. Mejor muévela a C:\\proyectos.\n"
        )
    # El navegador se abre SOLO cuando el servidor ya responde (en otro hilo, para no bloquearlo). Si se cierra el programa, ese hilo se va con él.
    threading.Thread(target=_abrir_cuando_este_lista, args=(url, puerto), daemon=True).start()
    uvicorn.run("app.main:app", host=HOST, port=puerto, reload=recargar)


def main(argumentos: list[str]) -> None:
    """Punto de entrada: asegura que estén las librerías (preparando el entorno si hace falta) y enciende el servidor."""
    if not _faltan_librerias():
        _servir(recargar="--recargar" in argumentos)
        return
    # Faltan librerías en ESTE Python. Si ya se intentó arreglar y siguen faltando, se avisa en vez de dar vueltas.
    if os.environ.get("COMPRAS_YA_PREPARADO"):
        sys.exit("Faltan librerías incluso después de preparar el entorno. Borra la carpeta .venv y vuelve a ejecutar.")
    python = _python_del_entorno()
    if not _entorno_completo(python):
        python = _preparar_entorno()
    # Se vuelve a ejecutar este mismo archivo, ahora con el Python del entorno (que sí tiene las librerías).
    os.environ["COMPRAS_YA_PREPARADO"] = "1"
    sys.exit(subprocess.call([str(python), str(Path(__file__).resolve()), *argumentos]))


if __name__ == "__main__":
    main(sys.argv[1:])
