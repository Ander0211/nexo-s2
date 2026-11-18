"""
PRUEBAS DEL ARRANQUE (run.py): elegir el puerto y detectar las librerías.

Estas pruebas protegen los dos errores que más se repitieron al instalar en Windows:
  - «WinError 10013» (el puerto 8000 está ocupado o bloqueado)  → run.py debe elegir otro solo.
  - «No module named uvicorn» (faltan las librerías)             → run.py debe detectarlo y prepararlas.
"""

import socket

import run


def _puerto_libre() -> int:
    """Atajo: pide al sistema un puerto que esté libre en este momento."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_usa_el_puerto_preferido_si_esta_libre():
    """Con el puerto libre, se usa exactamente el que se pidió."""
    libre = _puerto_libre()
    assert run.elegir_puerto(libre) == libre


def test_si_el_puerto_esta_ocupado_elige_otro():
    """Con el puerto ocupado por otro programa, elige uno distinto que sí se pueda abrir."""
    with socket.socket() as ocupante:
        ocupante.bind(("127.0.0.1", 0))
        ocupante.listen()
        ocupado = ocupante.getsockname()[1]
        elegido = run.elegir_puerto(ocupado)
        assert elegido != ocupado
        assert run._puerto_disponible(elegido)


def test_si_windows_bloquea_el_puerto_elige_otro(monkeypatch):
    """Simula el «WinError 10013» (puerto bloqueado por el sistema): tampoco debe fallar, sino usar otro puerto."""
    monkeypatch.setattr(run, "_puerto_disponible", lambda puerto: puerto != 8000)
    elegido = run.elegir_puerto(8000)
    assert elegido != 8000 and elegido > 0


def test_puerto_disponible_devuelve_falso_ante_un_error_del_sistema(monkeypatch):
    """Cualquier error al reservar el puerto (ocupado, permisos…) se traduce en «no disponible», sin romper el programa."""

    class SocketQueFalla:
        """Un socket falso que imita el error 10013 de Windows al intentar abrir el puerto."""

        def __init__(self, *args, **kwargs):
            """Acepta los mismos argumentos que un socket de verdad (no los usa)."""

        def __enter__(self):
            """Permite usarlo con «with», igual que un socket real."""
            return self

        def __exit__(self, *args):
            """Cierre del «with»: no hay nada que cerrar."""

        def bind(self, direccion):
            """Falla como falla Windows cuando el puerto está bloqueado."""
            raise PermissionError(10013, "Intento de acceso a un socket no permitido por sus permisos de acceso")

    monkeypatch.setattr(run.socket, "socket", SocketQueFalla)
    assert run._puerto_disponible(8000) is False


def test_detecta_que_las_librerias_estan_instaladas():
    """En el entorno de pruebas están todas las librerías: no debe reportar ninguna como faltante."""
    assert run._faltan_librerias() == []


def test_detecta_una_libreria_faltante(monkeypatch):
    """Si una librería no está instalada, run.py la reconoce (así sabe que debe preparar el entorno)."""
    monkeypatch.setattr(run, "LIBRERIAS", ("uvicorn", "libreria_que_no_existe_xyz"))
    assert run._faltan_librerias() == ["libreria_que_no_existe_xyz"]


def test_la_ruta_del_python_del_entorno_esta_dentro_de_la_carpeta_del_proyecto():
    """El Python del entorno (.venv) se busca siempre dentro del proyecto, en la subcarpeta que corresponde al sistema."""
    ruta = run._python_del_entorno()
    assert run.RAIZ in ruta.parents and ".venv" in ruta.parts


# ------------------------------------------------------------------------------------------------ el navegador se abre cuando el servidor ya responde
def test_esperar_servidor_dice_que_si_cuando_ya_acepta_conexiones():
    with socket.socket() as oyente:
        oyente.bind(("127.0.0.1", 0))
        oyente.listen()
        assert run.esperar_servidor("127.0.0.1", oyente.getsockname()[1], limite=2) is True


def test_esperar_servidor_dice_que_no_si_nadie_responde_y_no_espera_de_mas():
    import time

    with socket.socket() as libre:  # un puerto que acaba de quedar libre: nadie escucha
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]
    t0 = time.monotonic()
    assert run.esperar_servidor("127.0.0.1", puerto, limite=0.6) is False
    assert 0.5 <= time.monotonic() - t0 < 3


def test_esperar_servidor_espera_a_un_servidor_que_tarda_en_arrancar():
    """Lo que pasa en un equipo lento: el servidor se enciende DESPUÉS de empezar a esperar, y se le espera en vez de rendirse a los 1,5 s."""
    import threading
    import time

    with socket.socket() as reservado:
        reservado.bind(("127.0.0.1", 0))
        puerto = reservado.getsockname()[1]
    oyente = socket.socket()

    def encender_tarde():
        time.sleep(1.2)  # más de lo que antes se esperaba antes de abrir el navegador
        oyente.bind(("127.0.0.1", puerto))
        oyente.listen()

    threading.Thread(target=encender_tarde, daemon=True).start()
    try:
        assert run.esperar_servidor("127.0.0.1", puerto, limite=10) is True
    finally:
        oyente.close()


def test_el_navegador_se_abre_solo_cuando_el_servidor_esta_listo(monkeypatch, capsys):
    abiertos = []
    monkeypatch.setattr(run.webbrowser, "open", lambda url: abiertos.append(url))
    monkeypatch.setattr(run, "esperar_servidor", lambda *a, **k: False)  # el servidor NO respondió
    run._abrir_cuando_este_lista("http://127.0.0.1:8000", 8000)
    assert (
        abiertos == [] and "no respondió" in capsys.readouterr().out
    )  # nunca se abre el navegador a un servidor que no existe
    monkeypatch.setattr(run, "esperar_servidor", lambda *a, **k: True)  # ahora sí
    run._abrir_cuando_este_lista("http://127.0.0.1:8000", 8000)
    assert (
        abiertos == ["http://127.0.0.1:8000"] and "SUMIPABON lista en http://127.0.0.1:8000" in capsys.readouterr().out
    )


def test_f5_en_vs_code_arranca_sin_recarga_automatica():
    """La primera configuración (la que corre con F5) no lleva --recargar: el servidor no se reinicia solo cada vez que cambia un archivo."""
    import json
    import re
    from pathlib import Path

    texto = (Path(run.__file__).parent / ".vscode" / "launch.json").read_text(encoding="utf-8")
    config = json.loads(re.sub(r"^\s*//.*$", "", texto, flags=re.M))["configurations"]
    assert config[0]["program"].endswith("run.py") and "--recargar" not in config[0].get("args", [])
    assert any("--recargar" in c.get("args", []) for c in config)  # la recarga sigue disponible, pero aparte
