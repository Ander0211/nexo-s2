"""
LOS TABLEROS DE CONTROL
=======================
Tres vistas tipo «Power BI» sobre los mismos datos del tablero de compras (nada se guarda: todo se calcula al pedirlo):

    1. EMPRESAS CON MENORES VALORES   quién cobra menos. Para cada proveedor se compara su precio con el MEJOR de cada producto que
                                      cotiza: el «sobreprecio» es cuánto más caro es, en promedio (0 % = siempre es el más barato).
    2. PRECIOS MÁS BARATOS            en qué productos la mejor oferta más se aleja, hacia abajo, del precio promedio de las ofertas.
    3. PRODUCTOS QUE MÁS CONSUMEN     qué productos hay que reponer en mayor cantidad (o inversión, o stock máximo). El sistema no
                                      recibe las salidas de bodega: el consumo se estima con lo que hay que reponer
                                      (StockMax − Existencias), que es lo que la Clínica ya consumió respecto de su máximo.

Un filtro cruzado: si se elige una empresa, las vistas 2 y 3 y los números de arriba se limitan a los productos que ESA empresa cotiza
(como al hacer clic en una barra de Power BI).

Solo cuentan los productos que hay que comprar (cantidad > 0). Las ofertas se comparan con las reglas de siempre (services/ranking.py):
una oferta por proveedor, la más barata.
"""

import sqlite3
from typing import Literal

from . import ranking as rk
from . import tablero

PRECIOS_ORDEN = ("porcentaje", "valor")
CONSUMOS = ("cantidad", "inversion", "stock_max")


def _r(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


def _productos_a_comprar(con: sqlite3.Connection) -> list[tuple[dict, list[dict]]]:
    """[(producto del tablero, su ranking de ofertas)] de los productos que hay que comprar (el ranking puede estar vacío)."""
    items = tablero.construir_tablero(con)
    ofertas = tablero.ofertas_por_producto(con)
    return [(i, rk.construir_ranking(ofertas.get(i["cod"], []))) for i in items if i["comprar"] > 0]


def empresas(todos: list[tuple[dict, list[dict]]], min_productos: int = 1) -> list[dict]:
    """Un renglón por proveedor, del que cobra menos al que cobra más (por su sobreprecio promedio frente a la mejor oferta)."""
    acum: dict[str, dict] = {}
    comprado: dict[str, float] = {}
    for item, ranking in todos:
        if not ranking:
            continue
        mejor, n = ranking[0]["valor"], len(ranking)
        for puesto, o in enumerate(ranking):
            e = acum.setdefault(
                o["cod_empresa"],
                {
                    "cod": o["cod_empresa"],
                    "nombre": o["empresa"],
                    "cotiza": 0,
                    "gana": 0,
                    "suma": 0.0,
                    "n_comp": 0,
                    "cotizado": 0.0,
                    "minimo": 0.0,
                },
            )
            e["cotiza"] += 1
            e["gana"] += 1 if puesto == 0 else 0
            e["cotizado"] += o["valor"] * item["comprar"]  # lo que costaría comprar TODO lo que cotiza a sus precios
            e["minimo"] += mejor * item["comprar"]  # y lo que costaría a los mejores precios
            if n >= 2 and mejor > 0:  # el sobreprecio solo tiene sentido si hay con quién compararse
                e["suma"] += (o["valor"] / mejor - 1) * 100
                e["n_comp"] += 1
        for ln in item["reparto"]:  # lo que de verdad se le compra a cada uno (según el reparto de cada producto)
            comprado[ln["cod_empresa"]] = comprado.get(ln["cod_empresa"], 0.0) + (ln["subtotal"] or 0)
    filas = []
    for e in acum.values():
        if e["cotiza"] < min_productos:
            continue
        sobre = e["suma"] / e["n_comp"] if e["n_comp"] else None
        filas.append(
            {
                "cod": e["cod"],
                "nombre": e["nombre"],
                "cotiza": e["cotiza"],  # en cuántos productos a comprar tiene oferta
                "gana": e["gana"],  # en cuántos es el más barato
                "pct_gana": _r(e["gana"] / e["cotiza"] * 100, 1),
                "sobreprecio_pct": _r(sobre, 1),  # None = nunca compite con otro (no hay con qué compararlo)
                "valor_cotizado": _r(e["cotizado"]),
                "valor_minimo": _r(e["minimo"]),
                "sobrecosto": _r(e["cotizado"] - e["minimo"]),
                "comprado": _r(comprado.get(e["cod"], 0.0)),
            }
        )
    filas.sort(key=lambda e: (e["sobreprecio_pct"] is None, e["sobreprecio_pct"] or 0, -e["gana"], e["nombre"]))
    return filas


def precios(todos: list[tuple[dict, list[dict]]], orden: str = "porcentaje") -> list[dict]:
    """Productos donde la mejor oferta más baja está frente al promedio de las ofertas (solo con 2 o más ofertas)."""
    filas = []
    for item, ranking in todos:
        if len(ranking) < 2:
            continue
        mejor = ranking[0]
        promedio = sum(o["valor"] for o in ranking) / len(ranking)
        filas.append(
            {
                "cod": item["cod"],
                "descripcion": item["descripcion"],
                "comprar": item["comprar"],
                "n_ofertas": len(ranking),
                "mejor_precio": mejor["valor"],
                "cod_empresa": mejor["cod_empresa"],
                "empresa": mejor["empresa"],
                "precio_promedio": _r(promedio),
                "ahorro_pct": _r((promedio - mejor["valor"]) / promedio * 100, 1),
                "ahorro_valor": _r((promedio - mejor["valor"]) * item["comprar"]),
            }
        )
    if orden == "valor":
        filas.sort(key=lambda f: (-f["ahorro_valor"], -f["ahorro_pct"], f["descripcion"]))
    else:
        filas.sort(key=lambda f: (-f["ahorro_pct"], -f["ahorro_valor"], f["descripcion"]))
    return filas


def consumo(todos: list[tuple[dict, list[dict]]], orden: str = "cantidad") -> list[dict]:
    """Productos que más hay que reponer: por cantidad a comprar, por inversión o por stock máximo."""
    filas = [
        {
            "cod": i["cod"],
            "descripcion": i["descripcion"],
            "comprar": i["comprar"],
            "existencias": i["existencias"],
            "stock_max": i["stock_max"],
            "reposicion_pct": _r(i["comprar"] / i["stock_max"] * 100, 1) if i["stock_max"] else None,
            "total": i["total"],
            "empresa": i["elegida"]["empresa"] if i["elegida"] else None,
        }
        for i, _ in todos
    ]
    if orden == "inversion":
        filas.sort(key=lambda f: (-(f["total"] or 0), f["descripcion"]))
    elif orden == "stock_max":
        filas.sort(key=lambda f: (-(f["stock_max"] or 0), f["descripcion"]))
    else:
        filas.sort(key=lambda f: (-f["comprar"], f["descripcion"]))
    return filas


def construir_control(
    con: sqlite3.Connection,
    top: int = 10,
    empresa: str | None = None,
    min_productos: int = 1,
    precios_orden: Literal["porcentaje", "valor"] = "porcentaje",
    consumo_orden: Literal["cantidad", "inversion", "stock_max"] = "cantidad",
) -> dict:
    """Todo lo que muestra la pantalla «Tableros de control», en un solo paso."""
    todos = _productos_a_comprar(con)
    ranking_empresas = empresas(todos, min_productos)  # siempre sobre todos los productos: es el «filtro» que se elige
    alcance = [(i, r) for i, r in todos if not empresa or any(o["cod_empresa"] == empresa for o in r)]  # filtro cruzado
    con_oferta = [i for i, _ in alcance if i["elegida"]]
    lista_precios = precios(alcance, precios_orden)
    lista_consumo = consumo(alcance, consumo_orden)
    barata = ranking_empresas[0] if ranking_empresas and ranking_empresas[0]["sobreprecio_pct"] is not None else None
    nombre_sel = next((e["nombre"] for e in empresas(todos) if e["cod"] == empresa), None) if empresa else None
    return {
        "filtros": {
            "top": top,
            "empresa": empresa,
            "empresa_nombre": nombre_sel,
            "min_productos": min_productos,
            "precios": precios_orden,
            "consumo": consumo_orden,
        },
        "kpis": {
            "productos": len(alcance),
            "con_oferta": len(con_oferta),
            "inversion": round(sum(i["total"] or 0 for i in con_oferta), 2),
            "ahorro": round(sum(i["ahorro"] or 0 for i in con_oferta), 2),
            "empresa_mas_barata": {
                "nombre": barata["nombre"],
                "sobreprecio_pct": barata["sobreprecio_pct"],
                "gana": barata["gana"],
                "cotiza": barata["cotiza"],
            }
            if barata
            else None,
            "producto_mayor_consumo": {
                "cod": lista_consumo[0]["cod"],
                "descripcion": lista_consumo[0]["descripcion"],
                "comprar": lista_consumo[0]["comprar"],
            }
            if lista_consumo
            else None,
            "mejor_ahorro": {
                "cod": lista_precios[0]["cod"],
                "descripcion": lista_precios[0]["descripcion"],
                "ahorro_pct": lista_precios[0]["ahorro_pct"],
            }
            if lista_precios
            else None,
        },
        "empresas": ranking_empresas[:top],
        "total_empresas": len(ranking_empresas),
        "precios": lista_precios[:top],
        "total_precios": len(lista_precios),
        "consumo": lista_consumo[:top],
        "total_consumo": len(lista_consumo),
    }
