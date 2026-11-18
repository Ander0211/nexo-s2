"""
NEXO S²  —  un solo inicio para los sistemas de la Clínica
===========================================================
Ejecuta:   python nexo.py        (o doble clic en INICIAR-NEXO.bat en Windows)

Qué hace:
    1. Enciende el PORTAL de Nexo S² (por defecto en http://localhost:7000) y abre el navegador.
    2. En el portal aparecen los dos sistemas: SUMIPABON (compras) y SENTINEL PABON (copias de seguridad).
    3. Al elegir uno, Nexo S² lo arranca EXACTAMENTE como si lo hubieras abierto solo
       (SUMIPABON con su run.py, SENTINEL con su server.py, cada uno en su propia carpeta)
       y cuando ya responde te lleva a él.
    4. Si el sistema ya estaba abierto (por ejemplo lo iniciaste con su propio .bat), solo te lleva.

Los dos sistemas NO se modifican: siguen en  sistemas/compras_app  y  sistemas/sentinel.
Si los tienes en otra carpeta, cambia las rutas en  nexo_config.json  (se crea solo la primera vez).

Para detener todo: Ctrl+C en esta ventana (también apaga los sistemas que Nexo S² encendió).
Solo usa librerías que ya vienen con Python.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent
PORTAL = RAIZ / "portal"
LOGS = RAIZ / "logs"
CONFIG = RAIZ / "nexo_config.json"
HOST = os.environ.get("NEXO_HOST", "0.0.0.0")  # 0.0.0.0 = otros equipos de la red también pueden entrar al portal

CONFIG_INICIAL = {
    "puerto_portal": 7000,
    "sistemas": {
        "sumipabon": {"carpeta": "sistemas/compras_app", "puerto": 8000},
        "sentinel": {"carpeta": "sistemas/sentinel", "puerto": 8080},
    },
}


def cargar_config() -> dict:
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(CONFIG_INICIAL, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.loads(json.dumps(CONFIG_INICIAL))
    datos = json.loads(CONFIG.read_text(encoding="utf-8"))
    for clave, valor in CONFIG_INICIAL["sistemas"].items():  # completa lo que falte
        datos.setdefault("sistemas", {}).setdefault(clave, dict(valor))
    datos.setdefault("puerto_portal", 7000)
    return datos


CFG = cargar_config()


def carpeta(clave: str) -> Path:
    p = Path(CFG["sistemas"][clave]["carpeta"])
    return p if p.is_absolute() else (RAIZ / p).resolve()


# ---------------------------------------------------------------- utilidades de red

def responde(puerto: int, ruta: str) -> bool:
    """¿Hay un sistema vivo en ese puerto? Se pregunta a una dirección que solo ese sistema tiene."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}{ruta}", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def puerto_ocupado(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", puerto))
            return False
        except OSError:
            return True


def puerto_libre_desde(inicio: int) -> int:
    for p in range(inicio, inicio + 50):
        if not puerto_ocupado(p):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


def entorno_sin_navegador() -> dict:
    """Cada sistema abre el navegador por su cuenta al arrancar; aquí se evita esa pestaña extra
    porque es el portal el que te lleva. (BROWSER apunta a un comando que no hace nada.)"""
    env = dict(os.environ)
    env["BROWSER"] = f'"{sys.executable}" -c "pass" %s'
    env["PYTHONUNBUFFERED"] = "1"
    return env


# ---------------------------------------------------------------- los sistemas

class Sistema:
    def __init__(self, clave: str, nombre: str, ruta_salud: str):
        self.clave = clave
        self.nombre = nombre
        self.ruta_salud = ruta_salud
        self.proceso: subprocess.Popen | None = None
        self.puerto = int(CFG["sistemas"][clave]["puerto"])
        self.estado = "apagado"  # apagado | iniciando | activo | error
        self.mensaje = ""
        self.lock = threading.Lock()

    # Cada sistema dice cómo se arranca (igual que su propio .bat)
    def comando(self) -> list[str]:
        raise NotImplementedError

    def preparar(self) -> None:
        pass

    def env_extra(self) -> dict:
        return {}

    def vivo(self) -> bool:
        return responde(self.puerto, self.ruta_salud)

    def info(self) -> dict:
        if self.estado in ("apagado", "error") and self.vivo():
            self.estado, self.mensaje = "activo", ""
        elif self.estado == "activo" and not self.vivo():
            self.estado = "apagado"
        return {"estado": self.estado, "puerto": self.puerto, "mensaje": self.mensaje}

    def iniciar(self) -> None:
        with self.lock:
            if self.estado == "iniciando":
                return
            if self.vivo():
                self.estado = "activo"
                return
            self.estado, self.mensaje = "iniciando", ""
        threading.Thread(target=self._arrancar, daemon=True).start()

    def _arrancar(self) -> None:
        try:
            if not (carpeta(self.clave)).exists():
                raise RuntimeError(f"No se encuentra la carpeta {carpeta(self.clave)}. Revisa nexo_config.json.")
            self.preparar()
            LOGS.mkdir(exist_ok=True)
            log = open(LOGS / f"{self.clave}.log", "a", encoding="utf-8", errors="replace")
            log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} Nexo S² inicia {self.nombre} =====\n")
            log.flush()
            env = entorno_sin_navegador()
            env.update(self.env_extra())
            extra = {}
            if os.name == "nt":
                extra["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                extra["start_new_session"] = True
            self.proceso = subprocess.Popen(
                self.comando(), cwd=carpeta(self.clave), env=env, stdout=log, stderr=subprocess.STDOUT, **extra
            )
            print(f"  [{self.nombre}] arrancando en el puerto {self.puerto}... (detalles en logs/{self.clave}.log)")
            limite = time.monotonic() + 300  # la primera vez SUMIPABON instala librerías: puede tardar
            while time.monotonic() < limite:
                if self.vivo():
                    self.estado, self.mensaje = "activo", ""
                    print(f"  [{self.nombre}] listo en http://localhost:{self.puerto}")
                    return
                if self.proceso.poll() is not None:
                    raise RuntimeError(f"{self.nombre} se cerró al arrancar. Mira logs/{self.clave}.log para ver el error.")
                time.sleep(0.5)
            raise RuntimeError(f"{self.nombre} no respondió en 5 minutos. Mira logs/{self.clave}.log.")
        except Exception as e:
            self.estado, self.mensaje = "error", str(e)
            print(f"  [{self.nombre}] ERROR: {e}")

    def detener(self) -> None:
        p = self.proceso
        if not p or p.poll() is not None:
            return
        try:
            if os.name == "nt":  # /T apaga también los procesos hijos (el servidor real que lanza run.py)
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            else:
                os.killpg(p.pid, signal.SIGTERM)
        except Exception:
            pass


class Sumipabon(Sistema):
    def __init__(self):
        super().__init__("sumipabon", "SUMIPABON", "/api/salud")

    def preparar(self) -> None:
        # run.py usa el puerto que se le pida si está libre; si el preferido está ocupado por OTRO programa,
        # se busca el siguiente libre para no chocar.
        preferido = int(CFG["sistemas"]["sumipabon"]["puerto"])
        self.puerto = preferido if not puerto_ocupado(preferido) else puerto_libre_desde(preferido + 1)

    def env_extra(self) -> dict:
        return {"COMPRAS_PUERTO": str(self.puerto)}

    def comando(self) -> list[str]:
        return [sys.executable, "run.py"]  # run.py prepara solo su .venv la primera vez, como siempre


class Sentinel(Sistema):
    def __init__(self):
        super().__init__("sentinel", "SENTINEL PABON", "/api/salud")

    def preparar(self) -> None:
        if puerto_ocupado(self.puerto):
            raise RuntimeError(
                f"El puerto {self.puerto} lo está usando otro programa y SENTINEL siempre usa ese puerto. Ciérralo e intenta de nuevo."
            )
        # Igual que iniciar-SENTINEL.bat: si falta openpyxl, se instala
        if subprocess.run([sys.executable, "-c", "import openpyxl"], capture_output=True).returncode != 0:
            self.mensaje = "Instalando openpyxl (solo la primera vez)..."
            subprocess.run([sys.executable, "-m", "pip", "install", "--user", "openpyxl"], capture_output=True)
            self.mensaje = ""

    def comando(self) -> list[str]:
        return [sys.executable, "-u", "server.py"]


SISTEMAS: dict[str, Sistema] = {"sumipabon": Sumipabon(), "sentinel": Sentinel()}


# ---------------------------------------------------------------- el portal

class Portal(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(PORTAL), **k)

    def _json(self, codigo: int, datos: dict) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta == "/api/estado":
            self._json(200, {clave: s.info() for clave, s in SISTEMAS.items()})
            return
        if ruta in ("/", ""):
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        ruta = urlparse(self.path).path
        if ruta.startswith("/api/iniciar/"):
            clave = ruta.rsplit("/", 1)[-1]
            if clave not in SISTEMAS:
                self._json(404, {"ok": False, "error": "Ese sistema no existe"})
                return
            SISTEMAS[clave].iniciar()
            self._json(200, {"ok": True, **SISTEMAS[clave].info()})
            return
        self._json(404, {"ok": False, "error": "ruta desconocida"})

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # el portal no llena la ventana de mensajes


def apagar_todo(*_):
    print("\n  Apagando Nexo S² y los sistemas que encendió...")
    for s in SISTEMAS.values():
        s.detener()
    os._exit(0)


def main() -> None:
    os.chdir(RAIZ)
    puerto = int(os.environ.get("NEXO_PUERTO", CFG["puerto_portal"]))
    if puerto_ocupado(puerto):
        if responde(puerto, "/api/estado"):
            print(f"  Nexo S² ya estaba abierto: http://localhost:{puerto}")
            webbrowser.open(f"http://localhost:{puerto}")
            return
        puerto = puerto_libre_desde(puerto + 1)
    servidor = ThreadingHTTPServer((HOST, puerto), Portal)
    url = f"http://localhost:{puerto}"
    print("\n  ==============================================")
    print("   NEXO S²  listo en", url)
    print("   Otros equipos:  http://<IP de este equipo>:%d" % puerto)
    print("   No cierres esta ventana. Para salir: Ctrl+C")
    print("  ==============================================\n")
    signal.signal(signal.SIGINT, apagar_todo)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, apagar_todo)
    if "--sin-navegador" not in sys.argv:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    finally:
        apagar_todo()


if __name__ == "__main__":
    main()
