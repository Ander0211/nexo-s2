"""
PLANTILLAS DE EXCEL PARA CARGAR DATOS
=====================================
Genera los Excel de ejemplo que se descargan con el botón «Descargar plantilla» de el panel «Cargar datos».
Cada plantilla tiene dos hojas:

    DATOS          solo los encabezados, VACÍA (así, si se sube sin llenar, no se carga nada de ejemplo por error)
    INSTRUCCIONES  qué significa cada columna, cuáles son obligatorias y un ejemplo

Las columnas de códigos se marcan como TEXTO para que Excel no les quite los ceros de la izquierda («0041»).
Los encabezados coinciden con los que entiende services/cargas.py (COLUMNAS).
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

# Por tipo: encabezados de la hoja DATOS, cuáles columnas son códigos (texto) y las líneas de INSTRUCCIONES.
PLANTILLAS = {
    "productos": {
        "encabezados": ["COD_PRODUCTO", "DESCRIPCION", "STOCKMAX", "STOCKMIN", "EXISTENCIAS"],
        "codigos": ["COD_PRODUCTO"],
        "instrucciones": [
            "PLANTILLA DE PRODUCTOS",
            "",
            "Llena la hoja DATOS (una fila por producto) y súbela en «Cargar datos → Productos».",
            "",
            "COD_PRODUCTO   OBLIGATORIA. Código del producto (por ejemplo 0123 o AB123).",
            "DESCRIPCION    Obligatoria para productos NUEVOS. Para uno que ya existe puedes dejarla vacía.",
            "STOCKMAX       Opcional. Stock máximo: hasta cuánto se quiere tener. Sin él, el producto no se compra.",
            "STOCKMIN       Opcional. Stock mínimo (no puede ser mayor que el máximo).",
            "EXISTENCIAS    Opcional. Cuántas unidades hay hoy.",
            "",
            "Cantidad a comprar = STOCKMAX - EXISTENCIAS.",
            "Si un producto YA existe, solo se cambian las columnas que traigan valor (una celda vacía no borra nada).",
            "Ejemplo:  0123 | PRODUCTO DE EJEMPLO 500 MG | 100 | 20 | 35",
        ],
    },
    "proveedores": {
        "encabezados": ["CODIGO_EMPRESA", "NOMBRE"],
        "codigos": ["CODIGO_EMPRESA"],
        "instrucciones": [
            "PLANTILLA DE PROVEEDORES",
            "",
            "Llena la hoja DATOS (una fila por proveedor) y súbela en «Cargar datos → Proveedores».",
            "",
            "CODIGO_EMPRESA  Opcional. Si la dejas vacía se le asigna un código automáticamente.",
            "NOMBRE          OBLIGATORIA. Nombre del proveedor (mínimo 2 letras).",
            "",
            "Si el código ya existe, se cambia el nombre de ese proveedor. Si el nombre ya existe, no se duplica.",
            "Ejemplo:  (vacío) | DROGUERIA EJEMPLO SAS",
        ],
    },
    "cotizaciones": {
        "encabezados": ["COD_EMPRESA", "COD_PRODUCTO", "VALOR", "PRESENTACION", "CANTIDAD_DISPONIBLE"],
        "codigos": ["COD_EMPRESA", "COD_PRODUCTO"],
        "instrucciones": [
            "PLANTILLA DE COTIZACIONES",
            "",
            "Llena la hoja DATOS (una fila por producto cotizado) y súbela en «Cargar datos → Cotizaciones».",
            "",
            "COD_EMPRESA    Proveedor que cotiza. Es opcional: si el archivo es de UN solo proveedor,",
            "               bórrala y elige el proveedor en la pantalla. En vez del código puedes usar una",
            "               columna EMPRESA con el nombre exacto del proveedor.",
            "COD_PRODUCTO   OBLIGATORIA. Debe ser un producto que ya exista en el catálogo.",
            "VALOR          OBLIGATORIA. Precio POR UNIDAD. Sin precio (o 0) la fila se omite: es lo normal",
            "               cuando el proveedor no cotizó ese producto.",
            "PRESENTACION   Opcional. Por ejemplo X10 o X100.",
            "CANTIDAD_DISPONIBLE  Opcional. Cuántas unidades puede entregar el proveedor. Si no le alcanzan para todo lo que hay",
            "               que comprar, la compra se reparte con el siguiente proveedor más barato. Vacía = no lo dijo (se supone",
            "               que le alcanza). 0 = no tiene unidades.",
            "",
            "El proveedor y el producto deben existir antes (créalos en las pestañas Proveedores y Productos).",
            "Ejemplo:  1 | 0123 | 12500 | X1 | 300",
        ],
    },
}


def plantilla_xlsx(tipo: str) -> bytes:
    """Construye la plantilla del tipo pedido y devuelve los bytes del archivo .xlsx (se arma en memoria)."""
    datos = PLANTILLAS[tipo]
    wb = Workbook()
    hoja = wb.active
    hoja.title = "DATOS"
    hoja.append(datos["encabezados"])
    for celda in hoja[1]:
        celda.font = Font(name="Arial", bold=True, size=10)
        celda.fill = PatternFill("solid", fgColor="D9E1F2")
        celda.alignment = Alignment(horizontal="center")
    for columna, encabezado in enumerate(datos["encabezados"], start=1):
        letra = hoja.cell(1, columna).column_letter
        hoja.column_dimensions[letra].width = 48 if encabezado == "DESCRIPCION" else 18
        if encabezado in datos["codigos"]:
            # Formato «texto» en toda la columna: Excel conserva los ceros de la izquierda (0041).
            for fila in range(2, 1002):
                hoja.cell(fila, columna).number_format = "@"
    hoja.freeze_panes = "A2"

    ayuda = wb.create_sheet("INSTRUCCIONES")
    for linea in datos["instrucciones"]:
        ayuda.append([linea])
    ayuda["A1"].font = Font(name="Arial", bold=True, size=12)
    for fila in ayuda.iter_rows(min_row=2):
        fila[0].font = Font(name="Arial", size=10)
    ayuda.column_dimensions["A"].width = 110

    buffer = io.BytesIO()  # «archivo en memoria»: no se escribe nada en el disco
    wb.save(buffer)
    return buffer.getvalue()
