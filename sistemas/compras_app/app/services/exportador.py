"""
EXPORTADOR DE LA HOJA «VALORES»
===============================
Arma los Excel que se descargan: la orden de compra (OC), el libro de alternativas 2.º a 4.º, la ficha del proveedor y PRODUCTOS_A_COMPRAR.
Tiene las mismas 8 columnas que la hoja VALORES de OC.xlsm, para poder copiarla
y pegarla ahí y seguir usando la tabla dinámica y la hoja ORDENES de siempre.

Solo salen los productos que hay que comprar Y que tienen alguna oferta, usando el
proveedor ELEGIDO de cada uno (la mejor oferta, o la que el usuario eligió a mano).
"""

import io
import sqlite3

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from . import fichas, libros_excel
from . import ranking as rk
from .tablero import construir_tablero, ofertas_por_producto
from .tablero import para_proveedor as tablero_para_proveedor

# Encabezados exactamente como en la hoja VALORES de OC.xlsm. La última columna es la PRESENTACION de la oferta ganadora
# (antes era «STOCK MAXIMO»).
COLUMNAS = [
    "COD_PRODUCTO",
    "DESCRIPCION",
    "CANT_COMPRAR",
    "VALOR",
    "COD_EMPRESA",
    "NOM_EMPRESA",
    "EXISTENCIAS",
    "PRESENTACION",
]


def filas_valores(con: sqlite3.Connection) -> list[list]:
    """Una fila por producto a comprar Y PROVEEDOR, en el orden de COLUMNAS, ordenadas por proveedor y luego por código. Casi siempre es una fila por
    producto; si el mejor proveedor no tiene unidades para todo, el producto sale en varias filas (una por proveedor, con las unidades de cada uno)."""
    filas = []
    for i in construir_tablero(con):
        if i["comprar"] <= 0:
            continue  # no hay que comprarlo
        for e in i["reparto"]:  # vacío si nadie lo ofrece (o a nadie le quedan unidades): no va en VALORES
            filas.append(
                [
                    i["cod"],
                    i["descripcion"],
                    e["cantidad"],
                    e["valor"],
                    e["cod_empresa"],
                    e["empresa"],
                    i["existencias"],
                    e["presentacion"],  # la presentación que ofreció ESE proveedor
                ]
            )
    filas.sort(key=lambda f: (f[5].lower(), f[0]))  # f[5] = nombre del proveedor, f[0] = código
    return filas


def _xlsx(
    hoja: str,
    columnas: list[str],
    filas: list[list],
    anchos: list[int],
    miles: tuple[int, ...] = (),
    llenar: tuple[int, ...] = (),
) -> bytes:
    """Arma un Excel sencillo en memoria: encabezado azul claro, filas, separador de miles en las columnas `miles` (posiciones
    desde 0) y fondo amarillo en las columnas `llenar` (las que debe completar quien lo recibe)."""
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(columnas)
    for c in ws[1]:
        c.font = Font(name="Arial", bold=True, size=10)
        c.fill = PatternFill("solid", fgColor="D9E1F2")
        c.alignment = Alignment(horizontal="center")
    for f in filas:
        ws.append(f)
    for fila in ws.iter_rows(min_row=2):
        for c in fila:
            c.font = Font(name="Arial", size=10)
        for k in miles:
            fila[k].number_format = "#,##0"
        for k in llenar:
            fila[k].fill = PatternFill("solid", fgColor="FFF2CC")
    for i, ancho in enumerate(anchos):
        ws.column_dimensions[ws.cell(row=1, column=i + 1).column_letter].width = ancho
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def productos_a_comprar_xlsx(con: sqlite3.Connection) -> bytes:
    """EXCEL PARA EL PERFIL «CONSULTA»: todos los productos que hay que comprar (tengan o no oferta), con la cantidad,
    el proveedor elegido, su precio y el total. Los que nadie ofrece salen con el proveedor vacío."""
    filas = []
    for i in construir_tablero(con):
        if i["comprar"] <= 0:
            continue
        e = i["elegida"]
        proveedor, valor = (e["empresa"], e["valor"]) if e else (None, None)
        if i["repartido"]:  # la compra se divide: «A (600) + B (400)», y sin un precio único
            proveedor, valor = " + ".join(f"{ln['empresa']} ({ln['cantidad']})" for ln in i["reparto"]), None
        filas.append(
            [
                i["cod"],
                i["descripcion"],
                i["stock_max"],
                i["existencias"],
                i["comprar"],
                proveedor,
                valor,
                i["total"],
            ]
        )
    filas.sort(key=lambda f: f[1].lower())
    return _xlsx(
        "PRODUCTOS_A_COMPRAR",
        ["COD_PRODUCTO", "DESCRIPCION", "STOCK MAXIMO", "EXISTENCIAS", "CANT_COMPRAR", "PROVEEDOR", "VALOR", "TOTAL"],
        filas,
        [14, 60, 13, 12, 14, 45, 12, 16],
        miles=(2, 3, 4, 6, 7),
    )


def cotizacion_xlsx(con: sqlite3.Connection, empresa: dict | None, grupo: str | None = None, q: str = "") -> bytes:
    """EXCEL PARA EL PROVEEDOR EXTERNO: la FICHA DE SOLICITUD DE COTIZACIÓN (FR-GDS-07) con los productos por comprar (código y descripción).
    `grupo` la reduce a los productos «sin_oferta» (los que nadie ha cotizado) o «nuevos»; `q` a los que coinciden con la búsqueda.
    NO lleva cantidades, precios ni ofertas de nadie, ni existencias: la columna «cantidad solicitada» queda vacía. Si el usuario está ligado a
    un proveedor, se llenan su razón social, teléfono y correo y su código queda en una hoja muy oculta, para reconocerlo al subir la ficha.
    Al subirla de vuelta (el proveedor desde su pantalla, o «Cargar datos → Cotizaciones») se lee el PRECIO (sin IVA) y la unidad de empaque."""
    productos = [
        {"cod": i["cod"], "descripcion": i["descripcion"]}
        for i in tablero_para_proveedor(construir_tablero(con), grupo, q)
    ]
    proveedor = None
    if empresa and empresa.get("cod"):
        proveedor = {"cod": empresa["cod"], "nombre": empresa.get("nombre"), **fichas.contacto_de(con, empresa["cod"])}
    return libros_excel.ficha_cotizacion_xlsx(productos, proveedor)


def _lista_xlsx(hoja: str, columnas: list[str], filas: list[list], anchos: list[int]) -> bytes:
    """Un Excel sencillo para el administrador: una hoja con su encabezado, filtros y la primera fila fija."""
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(columnas)
    for c in ws[1]:
        c.font, c.fill, c.alignment = (
            Font(bold=True, color="FFFFFF"),
            PatternFill("solid", fgColor="1F4E96"),
            Alignment(horizontal="center", vertical="center", wrap_text=True),
        )
    for f in filas:
        ws.append(f)
    for n, ancho in enumerate(anchos, 1):
        ws.column_dimensions[chr(64 + n)].width = ancho
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def oc_xlsx(con: sqlite3.Connection) -> bytes:
    """LA ORDEN DE COMPRA (formato OC): para cada producto por comprar, el proveedor GANADOR (el elegido: la mejor oferta, o la que el usuario
    eligió a mano). Trae las hojas VALORES, DINAMICA y ORDENES."""
    return libros_excel.oc_xlsx(filas_valores(con), COLUMNAS)


def filas_por_puesto(con: sqlite3.Connection) -> dict[int, list[list]]:
    """Para cada producto por comprar, su 2.ª, 3.ª y 4.ª oferta (las siguientes a la ELEGIDA, que es la de la OC) si tiene tantas: {puesto: [fila, ...]}.
    Cada fila trae las mismas 8 columnas de VALORES (COLUMNAS) y va ordenada como ella: por proveedor y luego por código."""
    agrupadas = ofertas_por_producto(con)
    salida: dict[int, list[list]] = {p: [] for p in libros_excel.PUESTOS_ALTERNATIVOS}
    for i in construir_tablero(con):
        if i["comprar"] <= 0:
            continue
        # Los que ya van en la OC (la elegida; con reparto, todos los del reparto) no cuentan como alternativa.
        usados = {ln["cod_empresa"] for ln in i["reparto"]} or (
            {i["elegida"]["cod_empresa"]} if i["elegida"] else set()
        )
        # Las alternativas son las SIGUIENTES mejores ofertas SIN contar la elegida (que es la que va en la OC): si eliges otra en vez de la mejor,
        # la elegida pasa a ser «la mejor» y las alternativas se ajustan (la que era la mejor se vuelve la 2.ª). Sin elección distinta, es el 2.º, 3.º y 4.º del ranking.
        otras = [o for o in rk.construir_ranking(agrupadas.get(i["cod"], [])) if o["cod_empresa"] not in usados]
        for puesto in libros_excel.PUESTOS_ALTERNATIVOS:
            if len(otras) >= puesto - 1:
                o = otras[puesto - 2]
                salida[puesto].append(
                    [
                        i["cod"],
                        i["descripcion"],
                        i["comprar"],
                        o["valor"],
                        o["cod_empresa"],
                        o["empresa"],
                        i["existencias"],
                        o["presentacion"],  # la presentación que ofreció ese proveedor alternativo
                    ]
                )
    for filas in salida.values():
        filas.sort(key=lambda f: (f[5].lower(), f[0]))
    return salida


def alternativas_xlsx(con: sqlite3.Connection) -> bytes:
    """EL LIBRO DE ALTERNATIVAS: para el 2.º, 3.º y 4.º proveedor, las mismas tres hojas de la OC (VALORES, DINAMICA y ORDENES): 9 hojas."""
    return libros_excel.alternativas_xlsx(filas_por_puesto(con), COLUMNAS)
