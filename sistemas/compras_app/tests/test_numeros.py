"""CÓMO SE LEEN LOS NÚMEROS de los Excel y CSV (services/normalizacion.numero y leer_excel).

El riesgo grande: en Colombia el punto separa MILES («59.000» = cincuenta y nueve mil) y en un Excel en inglés es decimal («59.000» = 59).
Mal leído, un precio saldría mil veces más barato y falsearía el ranking. La regla:
  · una celda que en Excel es NÚMERO se toma tal cual (su punto es decimal): 1.125 es uno con ciento veinticinco milésimas;
  · un TEXTO con un punto y exactamente tres cifras detrás («59.000», «1.234», «1.234.567») es miles; con otra cantidad («12.5») es decimal.
"""

import io

import pandas as pd
import pytest

from app.services import normalizacion as nz
from tests.conftest import excel_bytes
from tests.test_cargas import OCTETOS


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("59000", 59000), ("59.000", 59000), ("$ 59.000", 59000), ("1.234", 1234), ("12.345", 12345), ("1.234.567", 1234567),  # el punto separa miles
        ("59,000", 59000), ("1,234,567", 1234567), ("1.234,5", 1234.5), ("1,234.5", 1234.5), ("$59.000,50", 59000.5),  # con coma y punto, el último manda
        ("12,5", 12.5), ("0,5", 0.5), ("12.5", 12.5), ("100.25", 100.25), ("3.14159", 3.14159), (".5", 0.5), ("0.125", 0.125), ("1.00", 1),  # decimales
        ("−5", -5), ("-5", -5), ("–5", -5), ("(100)", -100), ("$-1.500", -1500),  # negativos: el menos de Excel y los paréntesis contables
        ("1.5e3", 1500), ("2E-2", 0.02), ("1e3", 1000),  # notación científica
        ("5 000", 5000), ("5\u00a0000", 5000), ("  42  ", 42), ("0041", 41),
    ],
)  # fmt: skip
def test_los_textos_se_leen_a_la_colombiana(texto, esperado):
    assert nz.numero(texto) == pytest.approx(esperado)


@pytest.mark.parametrize(
    "basura", ["abc", "", None, "1.2.3", "10-5", "1e999", "NaN", "inf", True, float("nan"), float("inf")]
)
def test_lo_que_no_es_un_numero_da_none(basura):
    assert nz.numero(basura) is None


def test_una_celda_que_ya_es_numero_no_se_adivina():
    assert (
        nz.numero(1.125) == 1.125 and nz.numero(59000.5) == 59000.5 and nz.numero(7) == 7.0
    )  # el punto de un número es decimal


def test_las_celdas_numericas_con_tres_decimales_no_se_confunden_con_miles():
    assert nz.celda_a_texto(1.125) == "1.1250"  # no «1.125», que se leería como 1125
    assert nz.numero(nz.celda_a_texto(1.125)) == 1.125 and nz.numero(nz.celda_a_texto(12.375)) == 12.375
    assert (
        nz.celda_a_texto(5929.0) == "5929"
        and nz.celda_a_texto(41) == "41"
        and nz.celda_a_texto(12.5) == "12.5"
        and nz.celda_a_texto(0.125) == "0.125"
    )
    assert nz.celda_a_texto(float("nan")) is None and nz.celda_a_texto(None) is None


def test_leer_excel_conserva_los_ceros_de_los_codigos_y_distingue_numeros_de_textos():
    b = io.BytesIO()
    pd.DataFrame({"COD": ["0041", "A1"], "TEXTO": ["59.000", "12.5"], "NUMERO": [1.125, 59000.0]}).to_excel(
        b, index=False
    )
    df = nz.leer_excel(io.BytesIO(b.getvalue()))
    assert list(df["COD"]) == ["0041", "A1"]  # el cero inicial sigue ahí
    assert [nz.numero(v) for v in df["TEXTO"]] == [59000, 12.5]  # texto: a la colombiana
    assert [nz.numero(v) for v in df["NUMERO"]] == [1.125, 59000]  # número de Excel: tal cual


def test_cargar_cotizaciones_lee_bien_el_texto_con_punto_de_miles_y_el_numero_con_tres_decimales(cliente):
    """De punta a punta: D4 no tiene ofertas. Se cargan dos: una con el precio escrito como TEXTO «59.000» y otra con una celda numérica 1,125."""
    filas = [
        {"COD_EMPRESA": "1", "COD_PRODUCTO": "D4", "VALOR": "59.000"},  # texto: 59 mil pesos
        {"COD_EMPRESA": "2", "COD_PRODUCTO": "D4", "VALOR": 1.125},  # número de Excel: un peso con 125 milésimas
    ]
    r = cliente.post(
        "/api/cargas/cotizaciones",
        params={"nombre": "c.xlsx", "aplicar": "true"},
        content=excel_bytes(filas),
        headers=OCTETOS,
    )
    assert r.status_code == 200 and r.json()["total_errores"] == 0, r.text
    ofertas = {o["cod_empresa"]: o["valor"] for o in cliente.get("/api/productos/D4/ofertas").json()["ofertas"]}
    assert ofertas == {"1": 59000, "2": 1.125}


def test_un_precio_con_menos_de_excel_se_rechaza_en_vez_de_volverse_positivo(cliente):
    filas = [{"COD_EMPRESA": "1", "COD_PRODUCTO": "D4", "VALOR": "−5"}]  # el «−» Unicode: antes se leía como +5
    r = cliente.post(
        "/api/cargas/cotizaciones",
        params={"nombre": "c.xlsx", "aplicar": "true"},
        content=excel_bytes(filas),
        headers=OCTETOS,
    )
    assert r.json()["total_errores"] == 1 and r.json()["nuevos"] == 0, r.text
