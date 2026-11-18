"""LA ESCENA DE LA VENTANA DE ESPERA «EL VIAJE A LA CLÍNICA» (frontend/viaje/).

La animación llegó como una página completa que traía un script de Cloudflare («/cdn-cgi/challenge-platform/...») y una imagen de ~800 KB metida en el
texto. herramientas/preparar_animacion.py la convierte en una escena liviana; estas pruebas vigilan que NUNCA vuelva a traer lo que no debe.
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ESCENA = RAIZ / "frontend" / "viaje" / "escena.txt"
DOCTOR = RAIZ / "frontend" / "viaje" / "doctor.webp"


def _escena() -> str:
    return ESCENA.read_text(encoding="utf-8")


def test_la_escena_no_trae_scripts_ni_llamadas_a_servidores_externos():
    t = _escena()
    assert "<script" not in t.lower() and "cloudflare" not in t.lower() and "cdn-cgi" not in t.lower()
    sin_espacio_de_nombres = re.sub(r"http://www\.w3\.org/\d+/svg", "", t)
    assert (
        "http://" not in sin_espacio_de_nombres and "https://" not in sin_espacio_de_nombres
    )  # nada se pide fuera de la aplicación
    assert "javascript:" not in t.lower() and not re.search(
        r"\son[a-z]+\s*=", t
    )  # ni atributos que ejecuten código (onclick=...)


def test_la_imagen_del_doctor_va_aparte_y_liviana():
    t = _escena()
    assert "data:image" not in t  # antes iba embebida (~800 KB) y la escena era enorme
    assert re.findall(r'<image[^>]*href="([^"]+)"', t) == ["/static/viaje/doctor.webp"]
    assert DOCTOR.exists() and DOCTOR.stat().st_size < 80 * 1024
    assert ESCENA.stat().st_size < 60 * 1024


def test_la_escena_trae_las_piezas_que_mueve_viaje_js():
    t = _escena()
    for pieza in ("routePath", "heartMascot", "clinicPabon", "poof"):  # js/viaje.js las busca por su id
        assert f'id="{pieza}"' in t, pieza
    for estado in (
        ".near",
        ".excited",
        ".arrived",
        ".pop",
        ".hide",
        ".show",
    ):  # los estados que viaje.js enciende y apaga
        assert estado in t, estado


def test_la_escena_respeta_reducir_movimiento_y_no_trae_adornos_de_la_pagina_original():
    t = _escena()
    assert "prefers-reduced-motion: reduce" in t
    for adorno in ("title-strip", "Reproducir", "captionText", "progress-pill", "Personaje tal cual"):
        assert adorno not in t, (
            adorno
        )  # el título, los subtítulos de ejemplo y el botón de la página original no van en la aplicación
