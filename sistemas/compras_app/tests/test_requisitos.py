"""LAS LIBRERÍAS QUE LA APLICACIÓN NECESITA ESTÁN DECLARADAS.

Pillow no se usa directamente en el código: openpyxl la necesita para conservar las imágenes (los dos logos) de la ficha de cotización. Si falta,
la ficha sale sin logos y SIN ningún error: por eso se vigila aquí, además de comprobar que la ficha realmente los trae (tests/test_libros_excel.py).
"""

import re
from pathlib import Path

import run

RAIZ = Path(__file__).resolve().parent.parent


def _requisitos() -> set[str]:
    lineas = (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {
        re.split(r"[<>=!~ #]", ln.strip(), maxsplit=1)[0].lower()
        for ln in lineas
        if ln.strip() and not ln.lstrip().startswith("#")
    }


def test_pillow_esta_en_los_requisitos_porque_los_logos_de_la_ficha_dependen_de_ella():
    assert {"pillow", "openpyxl", "pandas", "fastapi", "uvicorn"} <= _requisitos()


def test_run_py_completa_un_entorno_anterior_al_que_le_falta_pillow():
    assert "PIL" in run.LIBRERIAS  # si falta, run.py prepara el entorno e instala requirements.txt


def test_cada_libreria_que_run_py_vigila_esta_instalada_aqui():
    import importlib.util

    assert [n for n in run.LIBRERIAS if importlib.util.find_spec(n) is None] == []
