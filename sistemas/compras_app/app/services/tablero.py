"""
EL TABLERO DE PRODUCTOS
=======================
Junta TODO lo que muestra la pantalla principal, producto por producto:

    - cuánto hay que comprar         (ranking.cantidad_a_comprar)
    - la mejor y la 2.ª oferta       (ranking.construir_ranking)
    - la oferta elegida y su total   (ranking.elegir)
    - el ahorro frente a la 2.ª

También filtra, ordena y calcula los números grandes de arriba (resumen).

Con ~2.300 productos y ~7.000 ofertas se recalcula completo en milisegundos,
así que no hace falta caché: los datos siempre están al día.
"""

import sqlite3
from collections import defaultdict

from . import etiquetas
from . import ranking as rk
from .normalizacion import clave_busqueda, sin_acentos

# Valores permitidos para ordenar y filtrar (los mismos que ofrece la pantalla).
FILTROS = ("por_comprar", "con_oferta", "sin_oferta", "elegidos", "nuevos", "todos")


def _oferta_publica(o: dict | None, empresas_nuevas: dict | None = None) -> dict | None:
    """De una oferta completa, deja solo los datos que la pantalla necesita mostrar en la lista."""
    if not o:
        return None
    return {
        "cod_empresa": o["cod_empresa"],
        "empresa": o["empresa"],
        "empresa_nueva": o["cod_empresa"] in (empresas_nuevas or {}),  # la empresa es nueva: lleva la etiqueta «Nuevo»
        "valor": o["valor"],
        "presentacion": o["presentacion"],
        "origen": o["origen"],
        "disponible": o.get("disponible"),  # cuántas unidades dijo tener el proveedor (None = no lo dijo)
    }


def _linea_publica(linea: dict, empresas_nuevas: dict | None = None) -> dict:
    """Una línea del reparto: la oferta (como se muestra en la lista) más cuántas unidades se le compran y cuánto cuesta eso."""
    return {**_oferta_publica(linea, empresas_nuevas), "cantidad": linea["cantidad"], "subtotal": linea["subtotal"]}


def ofertas_por_producto(con: sqlite3.Connection, cod: str | None = None) -> dict[str, list[dict]]:
    """Lee las ofertas de la base y las agrupa por producto: {"5728": [oferta, oferta...], ...}.
    Si se pasa `cod`, solo trae las de ese producto (más rápido)."""
    # COALESCE(e.nombre, ...): si la oferta apunta a un proveedor que no existe, usa «Proveedor N».
    sql = (
        "SELECT o.id, o.cod_producto, o.cod_empresa, COALESCE(e.nombre, 'Proveedor ' || o.cod_empresa) AS empresa, "
        "o.valor, o.presentacion, o.disponible, o.origen FROM ofertas o LEFT JOIN empresas e ON e.cod = o.cod_empresa"
    )
    filas = con.execute(sql + (" WHERE o.cod_producto = ?" if cod else ""), (cod,) if cod else ()).fetchall()
    agrupadas: dict[str, list[dict]] = defaultdict(list)
    for f in filas:
        agrupadas[f["cod_producto"]].append(dict(f))
    return agrupadas


def cantidades_editadas(con: sqlite3.Connection, cod: str | None = None) -> dict[str, int]:
    """Las cantidades a comprar que el usuario fijó a mano: {código de producto: unidades}. Valen hasta que las restaure."""
    sql = "SELECT cod_producto, cantidad FROM cantidades" + (" WHERE cod_producto = ?" if cod else "")
    return {r["cod_producto"]: r["cantidad"] for r in con.execute(sql, (cod,) if cod else ())}


def construir_tablero(con: sqlite3.Connection) -> list[dict]:
    """Calcula la fila completa de cada producto. Devuelve una lista con un diccionario por producto."""
    agrupadas = ofertas_por_producto(con)
    # Proveedores que el usuario eligió a mano: {código de producto: código de proveedor}.
    elegidas = {r["cod_producto"]: r["cod_empresa"] for r in con.execute("SELECT * FROM seleccion")}
    editadas = cantidades_editadas(con)
    etiquetas.sincronizar(con)  # anota lo que el sistema ve por primera vez (para las etiquetas «Nuevo»)
    productos_nuevos = etiquetas.nuevos(con, "producto")
    empresas_nuevas = etiquetas.nuevos(con, "empresa")
    items = []
    for p in con.execute("SELECT * FROM productos"):
        ranking = rk.construir_ranking(agrupadas.get(p["cod"], []))
        elegida, a_mano = rk.elegir(ranking, elegidas.get(p["cod"]))
        # La cantidad calculada es StockMax - Existencias; si el usuario fijó otra a mano, esa manda (en totales, ahorro,
        # indicadores y exportaciones, que salen de aquí).
        calculada = rk.cantidad_a_comprar(p["stock_max"], p["existencias"])
        comprar = editadas.get(p["cod"], calculada)
        mejor = ranking[0] if ranking else None
        segunda = ranking[1] if len(ranking) > 1 else None
        # ¿A quién se le compra cuánto? Si el mejor no tiene unidades para todo, se le compra lo que tenga y el resto al siguiente (ranking.repartir).
        # Si ningún proveedor dijo cuánto tiene, sale lo de siempre: todo al elegido.
        plan = rk.repartir(comprar, ranking, elegida if a_mano else None)
        lineas = plan["lineas"]
        if lineas and not a_mano:
            elegida = lineas[0]  # el proveedor con la mayor parte de la compra (el más barato que tiene unidades)
        if not elegida:
            total = None
        elif comprar <= 0:
            total = 0.0
        elif lineas:
            total = round(sum(ln["subtotal"] for ln in lineas), 2)
        else:
            total = None  # hay ofertas, pero a ningún proveedor le quedan unidades
        # Ahorro = lo que se ahorra por no comprar todo a la 2.ª oferta. Si hay reparto o el mejor no tiene unidades: (2.ª × lo cubierto) − lo que cuesta.
        ajustado = bool(
            plan["faltante"]
            or plan["repartida"]
            or (lineas and not a_mano and lineas[0]["cod_empresa"] != mejor["cod_empresa"])
        )
        if not (segunda and comprar):
            ahorro = 0
        elif ajustado:
            ahorro = max(0.0, round(segunda["valor"] * plan["cubierta"] - total, 2)) if total is not None else 0
        else:
            ahorro = round((segunda["valor"] - mejor["valor"]) * comprar, 2)
        sin_unidades = bool(ranking and comprar > 0 and not lineas)  # hay ofertas, pero ninguna tiene unidades
        items.append(
            {
                "cod": p["cod"],
                "descripcion": p["descripcion"],
                "en_stock": bool(p["en_stock"]),
                "stock_max": p["stock_max"],
                "stock_min": p["stock_min"],
                "existencias": p["existencias"],
                "nivel_stock": rk.nivel_stock(p["existencias"], p["stock_min"], p["stock_max"]),
                "comprar": comprar,
                "calculada": calculada,  # lo que saldría sin la edición
                "editada": p["cod"] in editadas,  # True si la cantidad la fijó el usuario
                # Se compra MENOS de lo recomendado (calculada = StockMax − Existencias): para avisarlo en la pantalla.
                "menos_de_lo_recomendado": p["cod"] in editadas and comprar < calculada,
                # No hay nada que comprar porque las existencias ya están en el máximo o por encima.
                "stock_suficiente": comprar == 0
                and p["stock_max"] is not None
                and p["existencias"] is not None
                and p["existencias"] >= p["stock_max"],
                "nuevo": p["cod"] in productos_nuevos,  # producto nuevo (primera vez que el sistema lo ve)
                # «Nuevos» (el filtro de la pantalla): un producto nuevo, o uno cuya mejor oferta o la elegida es de una EMPRESA nueva.
                "novedad": p["cod"] in productos_nuevos
                or any(o and o["cod_empresa"] in empresas_nuevas for o in (mejor, elegida)),
                "nuevo_desde": productos_nuevos.get(p["cod"]),
                "n_ofertas": len(ranking),
                "mejor": _oferta_publica(
                    mejor, empresas_nuevas
                ),  # la más barata (no cambia aunque el usuario elija otra)
                "segunda": _oferta_publica(segunda, empresas_nuevas),
                "elegida": _oferta_publica(elegida, empresas_nuevas),  # la que realmente se va a comprar
                "elegida_a_mano": a_mano,
                # A quién se le compra cuánto: normalmente UNA línea (la oferta elegida × la cantidad). Si el mejor proveedor no tiene unidades
                # para todo, son varias: lo que tenga + el resto al siguiente (ver ranking.repartir).
                "reparto": [_linea_publica(ln, empresas_nuevas) for ln in lineas],
                "repartido": plan["repartida"],  # la compra se divide entre más de un proveedor
                "faltante": plan["faltante"],  # unidades que ningún proveedor puede entregar
                "excede_disponible": plan["excede"],  # (elegido a mano) pide más de lo que ese proveedor dijo tener
                "sin_unidades": sin_unidades,
                "avisa_cantidad": bool(
                    comprar > 0 and (plan["repartida"] or plan["faltante"] or plan["excede"] or sin_unidades)
                ),
                # Total = lo que cuesta todo el reparto (normalmente: precio de la oferta elegida × cantidad a comprar); None si no hay ofertas.
                "total": total,
                "ahorro": ahorro,
                "dif_segunda_pct": segunda["dif_pct"] if segunda else None,
                # Texto en minúscula y sin tildes para buscar rápido. El «_» inicial = dato interno.
                "_busqueda": clave_busqueda(p["cod"], p["descripcion"]),
            }
        )
    return items


def para_proveedor(items: list[dict], grupo: str | None = None, q: str = "") -> list[dict]:
    """Los productos que ve un PROVEEDOR: los que la Clínica necesita comprar, de la A a la Z y con búsqueda. `grupo` los reduce a los que no tienen
    NINGUNA oferta («sin_oferta») o a los productos nuevos («nuevos»). El proveedor solo recibirá código y descripción (routers/proveedor.py)."""
    base = [i for i in items if i["comprar"] > 0]
    if grupo == "sin_oferta":
        base = [i for i in base if i["n_ofertas"] == 0]
    elif grupo == "nuevos":
        base = [i for i in base if i["nuevo"]]
    return filtrar_y_ordenar(base, "por_comprar", q, None, "descripcion")


def publico(item: dict) -> dict:
    """Quita los datos internos (los que empiezan con «_») antes de enviar el producto a la pantalla."""
    return {k: v for k, v in item.items() if not k.startswith("_")}


def _cumple(item: dict, filtro: str) -> bool:
    """¿Este producto pertenece al filtro elegido? (los botones «Por comprar», «Con oferta»...)"""
    if filtro == "por_comprar":
        return item["comprar"] > 0
    if filtro == "con_oferta":
        return item["comprar"] > 0 and item["n_ofertas"] > 0
    if filtro == "sin_oferta":
        return item["comprar"] > 0 and item["n_ofertas"] == 0
    if filtro == "elegidos":
        return item["elegida_a_mano"]
    if filtro == "nuevos":
        return item["novedad"]
    return True  # "todos"


def conteos(items: list[dict]) -> dict:
    """Cuántos productos hay en cada filtro (los números dentro de los botones de la pantalla)."""
    return {f: sum(1 for i in items if _cumple(i, f)) for f in FILTROS}


# Criterios de orden del tablero → (valor de cada producto, sentido por defecto). Los números van de MAYOR a MENOR por defecto
# y los textos de la A a la Z; `direccion` («asc» / «desc») lo invierte. Lo vacío (sin oferta, sin stock) siempre queda AL FINAL.
ORDENES = {
    "inversion": (lambda i: i["total"], "desc"),
    "ahorro": (lambda i: i["ahorro"], "desc"),
    "cantidad": (lambda i: i["comprar"], "desc"),
    "existencias": (lambda i: i["existencias"], "desc"),
    "precio": (lambda i: i["elegida"]["valor"] if i["elegida"] else None, "desc"),
    "descripcion": (lambda i: sin_acentos(i["descripcion"] or "").lower() or None, "asc"),
    "proveedor": (lambda i: sin_acentos(i["elegida"]["empresa"] or "").lower() if i["elegida"] else None, "asc"),
    # Códigos numéricos en orden numérico (5 antes que 10) y luego los que tienen letras.
    "codigo": (lambda i: (0, int(i["cod"]), "") if i["cod"].isdigit() else (1, 0, i["cod"].lower()), "asc"),
}


def filtrar_y_ordenar(items, filtro="por_comprar", q="", empresa=None, orden="inversion", direccion=None) -> list[dict]:
    """Aplica filtro, búsqueda y proveedor; luego ordena por `orden` en la `direccion` pedida (o la de por defecto)."""
    # Cada palabra escrita en el buscador debe aparecer en el producto (sin importar tildes ni mayúsculas).
    tokens = sin_acentos(q or "").lower().split()
    out = [
        i
        for i in items
        if _cumple(i, filtro)
        and all(t in i["_busqueda"] for t in tokens)
        # Filtro por proveedor: solo productos cuya oferta elegida es de ese proveedor.
        and (not empresa or (i["elegida"] and i["elegida"]["cod_empresa"] == empresa))
    ]
    valor, por_defecto = ORDENES.get(orden, ORDENES["inversion"])
    descendente = (direccion or por_defecto) == "desc"
    # Desempate estable por descripción; luego el criterio (invertido si es «desc»); lo vacío se separa y va al final.
    out.sort(key=lambda i: (i["descripcion"] or "").lower())
    con_valor = [i for i in out if valor(i) is not None]
    vacios = [i for i in out if valor(i) is None]
    con_valor.sort(key=valor, reverse=descendente)
    return con_valor + vacios


def resumen(con: sqlite3.Connection, items: list[dict]) -> dict:
    """Los números grandes de arriba de la pantalla y los datos del gráfico «Dónde comprar»."""
    a_comprar = [i for i in items if i["comprar"] > 0]
    con_oferta = [i for i in a_comprar if i["elegida"]]
    # Suma cuánto se le compra a cada proveedor (según el reparto de cada producto: normalmente, su oferta elegida).
    por_prov: dict[str, dict] = {}
    for i in con_oferta:
        for e in i["reparto"]:  # cada línea del reparto (normalmente una sola) suma a SU proveedor
            d = por_prov.setdefault(
                e["cod_empresa"],
                {
                    "cod": e["cod_empresa"],
                    "nombre": e["empresa"],
                    "productos": 0,
                    "total": 0.0,
                    "nuevo": e["empresa_nueva"],
                },
            )
            d["productos"] += 1
            d["total"] += e["subtotal"] or 0
    proveedores = sorted(por_prov.values(), key=lambda d: -d["total"])  # el que más se le compra, primero
    for d in proveedores:
        d["total"] = round(d["total"], 2)
    meta = {r["clave"]: r["valor"] for r in con.execute("SELECT * FROM meta")}
    return {
        "productos": len(items),
        "por_comprar": len(a_comprar),
        "con_oferta": len(con_oferta),
        "sin_oferta": len(a_comprar) - len(con_oferta),
        "inversion_total": round(sum(i["total"] or 0 for i in con_oferta), 2),
        "ahorro_total": round(sum(i["ahorro"] or 0 for i in con_oferta), 2),
        "proveedores_ganadores": len(proveedores),
        "ofertas_pendientes": con.execute("SELECT COUNT(*) FROM lotes_oferta WHERE estado = 'pendiente'").fetchone()[
            0
        ],  # fichas de proveedores por revisar
        "ofertas_manuales": con.execute("SELECT COUNT(*) FROM ofertas WHERE origen='manual'").fetchone()[0],
        "por_proveedor": proveedores,
        "conteos": conteos(items),
        "ultima_importacion": meta.get("ultima_importacion"),
        "avisos_pendientes": con.execute("SELECT COUNT(*) FROM avisos WHERE nivel='warn'").fetchone()[0],
    }
