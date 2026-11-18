"""
PREPARAR LAS PLANTILLAS DE EXCEL (se ejecuta UNA vez, a mano; no forma parte de la aplicación)
=============================================================================================
La aplicación entrega dos Excel con el formato oficial de la Clínica:

  - la FICHA DE SOLICITUD DE COTIZACIÓN (FR-GDS-07), que descarga el proveedor
  - la ORDEN DE COMPRA (OC), con sus hojas VALORES, DINAMICA y ORDENES

Los archivos originales son pesados: abrir OC.xlsm tarda ~40 s y la ficha ~6 s, imposible en cada descarga. Este script los
abre una sola vez y deja en app/plantillas/ versiones LIVIANAS (solo el encabezado, una fila modelo y, en la ficha, la tabla
de control de cambios), que es lo que la aplicación abre en cada descarga (~0,1 s):

    python herramientas/preparar_plantillas.py  <ficha FR-GDS-07 .xlsx>  <OC .xlsm>

Qué se hace con cada una:
  FICHA  · se quitan las 7 hojas ocultas (datos internos que NO deben llegar al proveedor; ninguna fórmula las usa)
         · se quitan los productos de la plantilla (la aplicación escribe los suyos) y con ellos su columna «MARCA / LABORATORIO»:
           NO se guarda ningún dato del Excel original (la marca la escribe cada proveedor)
         · se deja una fila modelo (con los formatos y el bloqueo de celdas) y la tabla «Control de Cambios del Documento»
         · se agranda el cuadro de cada comentario de ayuda de los encabezados (al reescribirlos quedaban diminutos)
  OC     · las macros están vacías: se entrega .xlsx (sin avisos de seguridad)
         · la tabla dinámica de DINAMICA se reemplaza por una tabla calculada por la aplicación (mismo resultado)
         · se deja ORDENES con el encabezado y una fila modelo con sus fórmulas y celdas combinadas
"""

import sys
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment

DESTINO = Path(__file__).resolve().parent.parent / "app" / "plantillas"
FILA_MODELO = 12  # primera fila de productos de la ficha
BLOQUE_CONTROL = (2316, 2318)  # filas de «Control de Cambios del Documento» en el original
DONDE_QUEDA_EL_BLOQUE = 14  # en la plantilla liviana, el bloque queda aquí


def preparar_ficha(origen: Path) -> None:
    wb = openpyxl.load_workbook(origen)
    ws = wb.worksheets[0]
    # 1) fuera las hojas ocultas
    for extra in wb.worksheets[1:]:
        wb.remove(extra)
    # 2) el bloque de control de cambios se guarda y se vuelve a poner justo debajo de la fila modelo
    a, b = BLOQUE_CONTROL
    bloque = [[(c, ws.cell(r, c).value, copy(ws.cell(r, c)._style)) for c in range(1, 13)] for r in range(a, b + 1)]
    altos = [ws.row_dimensions[r].height for r in range(a, b + 1)]
    unir = [(m.min_row - a, m.min_col, m.max_row - a, m.max_col) for m in ws.merged_cells.ranges if a <= m.min_row <= b]
    for m in [m for m in ws.merged_cells.ranges if m.min_row >= FILA_MODELO]:
        ws.unmerge_cells(str(m))
    ws.delete_rows(FILA_MODELO + 1, ws.max_row)  # fuera todo lo que sigue a la fila modelo
    for r in list(ws.row_dimensions):
        if r > FILA_MODELO:
            del ws.row_dimensions[r]
    for c in (1, 2, 5, 10):  # la fila modelo queda sin los datos de la plantilla
        ws.cell(FILA_MODELO, c).value = None
    ws.merge_cells(start_row=FILA_MODELO, start_column=2, end_row=FILA_MODELO, end_column=3)
    for i, fila in enumerate(bloque):
        for c, valor, estilo in fila:
            celda = ws.cell(DONDE_QUEDA_EL_BLOQUE + i, c)
            celda.value, celda._style = valor, estilo
        ws.row_dimensions[DONDE_QUEDA_EL_BLOQUE + i].height = altos[i]
    for r0, c0, r1, c1 in unir:
        ws.merge_cells(
            start_row=DONDE_QUEDA_EL_BLOQUE + r0, start_column=c0, end_row=DONDE_QUEDA_EL_BLOQUE + r1, end_column=c1
        )
    # 4) los comentarios de ayuda de los encabezados: cuadro legible
    for fila in ws.iter_rows(min_row=1, max_row=12):
        for c in fila:
            if c.comment:
                nuevo = Comment(c.comment.text, c.comment.author or "FR-GDS-07")
                nuevo.width, nuevo.height = 320, 150
                c.comment = nuevo
    wb.properties.creator = wb.properties.lastModifiedBy = "SUMIPABON"  # sin nombres de personas en los metadatos
    wb.save(DESTINO / "ficha_base.xlsx")


def preparar_oc(origen: Path) -> None:
    wb = openpyxl.load_workbook(origen)  # sin keep_vba: las macros están vacías
    valores, dinamica, ordenes = wb["VALORES"], wb["DINAMICA"], wb["ORDENES"]
    dinamica._pivots = []  # la tabla dinámica la reemplaza una tabla calculada
    for ws, desde in ((valores, 2), (dinamica, 4)):
        if ws.max_row >= desde:
            ws.delete_rows(desde, ws.max_row)
    for m in [m for m in ordenes.merged_cells.ranges if m.min_row >= 3]:
        ordenes.unmerge_cells(str(m))
    ordenes.delete_rows(3, ordenes.max_row)
    for r in list(ordenes.row_dimensions):
        if r > 2:
            del ordenes.row_dimensions[r]
    wb.properties.creator = wb.properties.lastModifiedBy = "SUMIPABON"  # sin nombres de personas en los metadatos
    wb.save(DESTINO / "oc_base.xlsx")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    DESTINO.mkdir(parents=True, exist_ok=True)
    preparar_ficha(Path(sys.argv[1]))
    print("ficha_base.xlsx listo")
    preparar_oc(Path(sys.argv[2]))
    print("oc_base.xlsx listo")
