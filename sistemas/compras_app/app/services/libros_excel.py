"""
LIBROS DE EXCEL CON EL FORMATO OFICIAL DE LA CLÍNICA
====================================================
Arma los tres Excel que la aplicación entrega con el formato de los documentos de la Clínica (sin tocar la base de datos: reciben
las filas ya listas; quien las llama es exportador.py):

  ficha_cotizacion_xlsx   la FICHA DE SOLICITUD DE COTIZACIÓN (FR-GDS-07) que descarga el proveedor, con el código y la descripción de
                          cada producto por comprar. Mantiene la hoja PROTEGIDA del original: el proveedor solo puede escribir en detalle de
                          valor agregado, precio, IVA, unidad de empaque y cantidad disponible.
  oc_xlsx                 la ORDEN DE COMPRA con las hojas VALORES (los datos), DINAMICA (el resumen por proveedor, antes una tabla dinámica)
                          y ORDENES (la orden: una fila por producto y proveedor ganador).
  alternativas_xlsx       un libro con las MISMAS TRES HOJAS de la OC para cada puesto (2.º, 3.º y 4.º proveedor): 9 hojas en total
                          («VALORES 2.º», «DINAMICA 2.º», «ORDENES 2.º», «VALORES 3.º»...).

CÓMO SE ESCRIBEN LAS HOJAS DE DATOS (por qué es rápido): openpyxl tarda casi un minuto en crear y combinar las ~60.000 celdas de una OC grande
(su comprobación de celdas combinadas es cuadrática). Por eso openpyxl solo arma el libro (hojas, anchos, encabezados, formatos) y las FILAS DE DATOS
y las CELDAS COMBINADAS se escriben como texto XML ya armado y se insertan en el archivo (_inyectar), usando los mismos formatos de la plantilla.
Cada fórmula lleva además su valor ya calculado, así el archivo se ve bien hasta en visores que no calculan (el correo del celular, vistas previas).

Los formatos salen de plantillas livianas en app/plantillas/ (las prepara herramientas/preparar_plantillas.py a partir de los archivos
originales, que son demasiado pesados para abrirlos en cada descarga).
"""

import io
import re
import zipfile
from copy import copy
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.styles.cell_style import StyleArray
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.merge import MergedCellRange

PLANTILLAS = Path(__file__).resolve().parent.parent / "plantillas"

# --- Ficha FR-GDS-07: dónde está cada cosa en ficha_base.xlsx (ver herramientas/preparar_plantillas.py)
FILA_MODELO = 12  # la primera fila de productos
BLOQUE_CONTROL = (14, 16)  # «Control de Cambios del Documento»: se vuelve a poner debajo de los productos
COLUMNAS_FICHA = range(1, 13)  # A..L
HOJA_META = "SUMIPABON"  # hoja MUY oculta de la ficha: lleva el código del proveedor para reconocerlo al subir la ficha de vuelta

PUESTOS_ALTERNATIVOS = (2, 3, 4)  # el libro de alternativas trae el 2.º, 3.º y 4.º proveedor de cada producto


def _unir(ws, fila0: int, col0: int, fila1: int, col1: int) -> None:
    """Combina celdas igual que ws.merge_cells, pero sin su comprobación contra TODOS los rangos ya combinados (que se vuelve cuadrática:
    con miles de filas la orden de compra tardaba casi un minuto). Aquí las celdas combinadas ya traen su formato copiado de la plantilla."""
    ws.merged_cells.ranges.add(
        MergedCellRange(ws, f"{get_column_letter(col0)}{fila0}:{get_column_letter(col1)}{fila1}")
    )


def _a_bytes(wb: openpyxl.Workbook) -> bytes:
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


# ============================================================================================ FICHA DE COTIZACIÓN (FR-GDS-07)
def ficha_cotizacion_xlsx(productos: list[dict], proveedor: dict | None = None, hoy: date | None = None) -> bytes:
    """La ficha FR-GDS-07 con un producto por fila (código y descripción; la marca solo si la plantilla original ya la traía).

    productos  [{"cod": ..., "descripcion": ...}, ...] en el orden en que deben salir
    proveedor  {"cod", "nombre", "telefono", "correo"} del proveedor que la va a diligenciar; con él se llenan la razón social, el
               teléfono y el correo, y su código queda en la hoja MUY oculta (así, al subir la ficha, se sabe de quién es).
    La cantidad solicitada se deja VACÍA a propósito: el proveedor no ve cantidades.
    """
    wb = openpyxl.load_workbook(PLANTILLAS / "ficha_base.xlsx")
    ws = wb.worksheets[0]
    a, b = BLOQUE_CONTROL
    # 1) se guarda la tabla de control de cambios (valores, formatos, alturas y celdas combinadas) y se quita; se repone al final
    bloque = [[(c, ws.cell(r, c).value, copy(ws.cell(r, c)._style)) for c in COLUMNAS_FICHA] for r in range(a, b + 1)]
    altos = [ws.row_dimensions[r].height for r in range(a, b + 1)]
    unir = [(m.min_row - a, m.min_col, m.max_row - a, m.max_col) for m in ws.merged_cells.ranges if m.min_row >= a]
    for m in [m for m in list(ws.merged_cells.ranges) if m.min_row >= a]:
        ws.unmerge_cells(str(m))
    ws.delete_rows(a, b - a + 1)
    # 2) los productos: cada fila copia el formato (y el bloqueo de celdas) de la fila modelo
    modelo = [copy(ws.cell(FILA_MODELO, c)._style) for c in COLUMNAS_FICHA]
    alto = ws.row_dimensions[FILA_MODELO].height
    for i, p in enumerate(productos):
        r = FILA_MODELO + i
        for c in COLUMNAS_FICHA:
            ws.cell(r, c)._style = copy(modelo[c - 1])
        ws.cell(r, 1).value = str(p["cod"])  # texto: «0041» no se vuelve 41
        ws.cell(r, 2).value = p["descripcion"]
        ws.cell(r, 9).value = f"=G{r}+H{r}"  # PRECIO + IVA
        ws.row_dimensions[r].height = alto
        if r > FILA_MODELO:
            _unir(ws, r, 2, r, 3)
    ultima = FILA_MODELO + max(len(productos), 1) - 1
    # 3) la tabla de control de cambios vuelve debajo de los productos (con una fila de aire)
    inicio = ultima + 2
    for i, fila in enumerate(bloque):
        for c, valor, estilo in fila:
            celda = ws.cell(inicio + i, c)
            celda.value, celda._style = valor, estilo
        ws.row_dimensions[inicio + i].height = altos[i]
    for r0, c0, r1, c1 in unir:
        _unir(ws, inicio + r0, c0, inicio + r1, c1)
    # 4) encabezado: fecha de la solicitud y datos del proveedor
    ws["D5"] = (hoy or date.today()).strftime("%d/%m/%Y")
    if proveedor:
        ws["B8"] = proveedor.get("nombre")  # razón social
        ws["K8"] = proveedor.get("correo")  # e-mail
        ws["K9"] = proveedor.get("telefono")  # teléfono
    # 5) hoja muy oculta con el código del proveedor (no se ve ni se puede mostrar desde el menú de Excel)
    meta = wb.create_sheet(HOJA_META)
    meta.sheet_state = "veryHidden"
    meta["A1"], meta["B1"] = "COD_EMPRESA", (proveedor or {}).get("cod") or ""
    meta["A2"], meta["B2"] = "FORMATO", "FR-GDS-07"
    meta["A3"], meta["B3"] = "GENERADO", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    wb.active = 0
    wb.properties.title = "FR-GDS-07 Ficha de solicitud de cotización"
    wb.properties.creator = "SUMIPABON"
    return _a_bytes(wb)


# ============================================================================================ ORDEN DE COMPRA (OC) Y ALTERNATIVAS
# Las 6 combinaciones de columnas de la hoja ORDENES (igual que en OC.xlsm): código, descripción, cantidad, valor unitario, valor total, IVA.
_UNIONES_ORDENES = ((3, 6), (7, 16), (17, 18), (19, 21), (22, 24), (25, 26))
_ESTILO_ENCABEZADO = dict(
    font=Font(name="Arial", bold=True, size=10),
    fill=PatternFill("solid", fgColor="D9E1F2"),
    alignment=Alignment(horizontal="center", vertical="center", wrap_text=True),
)
_BORDE = Border(*(Side(style="thin") for _ in range(4)))
_CARACTERES_PROHIBIDOS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # no caben en un XML
_FORMATO_MILES = 3  # «#,##0» (formato predefinido de Excel)


def _col(n: int) -> str:
    return get_column_letter(n)


def _texto(v) -> str:
    return escape(_CARACTERES_PROHIBIDOS.sub("", str(v)))


def _num(v) -> str:
    """Un número como lo escribe Excel en el XML (85.0 → «85»)."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v) if isinstance(v, float) else str(v)


def _c_vacia(ref: str, s: int) -> str:
    return f'<c r="{ref}" s="{s}"/>'


def _c_texto(ref: str, s: int, v) -> str:
    t = _texto(v)
    espacio = ' xml:space="preserve"' if t != t.strip() or "  " in t else ""
    return f'<c r="{ref}" s="{s}" t="inlineStr"><is><t{espacio}>{t}</t></is></c>'


def _c_numero(ref: str, s: int, v) -> str:
    return f'<c r="{ref}" s="{s}"><v>{_num(v)}</v></c>'


def _c_valor(ref: str, s: int, v) -> str:
    """Texto, número o vacío, según lo que sea `v`."""
    if v is None or v == "":
        return _c_vacia(ref, s)
    return _c_numero(ref, s, v) if isinstance(v, (int, float)) and not isinstance(v, bool) else _c_texto(ref, s, v)


def _c_formula(ref: str, s: int, formula: str, resultado) -> str:
    """Una fórmula con su resultado ya calculado (texto o número)."""
    f = _texto(formula)
    if isinstance(resultado, (int, float)):
        return f'<c r="{ref}" s="{s}"><f>{f}</f><v>{_num(resultado)}</v></c>'
    return f'<c r="{ref}" s="{s}" t="str"><f>{f}</f><v>{_texto(resultado)}</v></c>'


def _fila_xml(r: int, celdas: list[str], alto: float | None = None) -> str:
    ht = f' ht="{alto}" customHeight="1"' if alto else ""
    return f'<row r="{r}"{ht}>{"".join(celdas)}</row>'


def _agrupar(filas: list[list], ind: dict[str, int]) -> list[list]:
    """Une las filas del mismo proveedor y producto (suma la cantidad y deja el valor más bajo, como hacía la tabla dinámica) y las ordena por
    proveedor y luego por descripción. Devuelve [proveedor, código, descripción, cantidad, valor] (lo que lleva DINAMICA)."""
    grupos: dict[tuple, list] = {}
    for f in filas:
        k = (f[ind["COD_EMPRESA"]], f[ind["COD_PRODUCTO"]])
        if k not in grupos:
            grupos[k] = [
                f[ind["NOM_EMPRESA"]],
                f[ind["COD_PRODUCTO"]],
                f[ind["DESCRIPCION"]],
                f[ind["CANT_COMPRAR"]],
                f[ind["VALOR"]],
            ]
        else:
            grupos[k][3] += f[ind["CANT_COMPRAR"]]
            grupos[k][4] = min(grupos[k][4], f[ind["VALOR"]])
    return sorted(grupos.values(), key=lambda g: (g[0].lower(), g[2].lower(), str(g[1])))


class _Hoja:
    """Lo que se inserta en una hoja que openpyxl ya guardó: las filas de datos, las celdas combinadas y hasta dónde llega la hoja."""

    def __init__(self, filas: list[str], uniones: list[str], ultima_fila: int, ultima_col: int):
        self.filas, self.uniones, self.ultima_fila, self.ultima_col = filas, uniones, ultima_fila, ultima_col


def _partes_de_hojas(zin: zipfile.ZipFile) -> dict[str, str]:
    """{nombre de la hoja: archivo xml que la guarda} (lo dice workbook.xml y sus relaciones)."""
    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    libro = ElementTree.fromstring(zin.read("xl/workbook.xml"))
    destinos = {r.get("Id"): r.get("Target") for r in ElementTree.fromstring(zin.read("xl/_rels/workbook.xml.rels"))}
    salida = {}
    for hoja in libro.find("m:sheets", ns):
        destino = destinos[hoja.get("{" + ns["r"] + "}id")].lstrip("/")
        salida[hoja.get("name")] = destino if destino.startswith("xl/") else "xl/" + destino
    return salida


def _inyectar(paquete: bytes, hojas: dict[str, _Hoja]) -> bytes:
    """Reescribe el .xlsx que guardó openpyxl poniendo en cada hoja indicada sus filas de datos y sus celdas combinadas ya armadas."""
    entrada = zipfile.ZipFile(io.BytesIO(paquete))
    partes = {parte: nombre for nombre, parte in _partes_de_hojas(entrada).items() if nombre in hojas}
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zout:
        for item in entrada.infolist():
            datos = entrada.read(item.filename)
            if item.filename in partes:
                datos = _poner_en_hoja(datos.decode("utf-8"), hojas[partes[item.filename]]).encode("utf-8")
            zout.writestr(item, datos)
    return salida.getvalue()


def _poner_en_hoja(xml: str, h: _Hoja) -> str:
    filas = "".join(h.filas)
    if "<sheetData/>" in xml:
        xml = xml.replace("<sheetData/>", f"<sheetData>{filas}</sheetData>", 1)
    else:
        xml = xml.replace("</sheetData>", f"{filas}</sheetData>", 1)
    previas = re.findall(r'<mergeCell ref="([^"]+)"', xml)  # las del encabezado, que dejó openpyxl
    todas = previas + h.uniones
    bloque = (
        f'<mergeCells count="{len(todas)}">' + "".join(f'<mergeCell ref="{r}"/>' for r in todas) + "</mergeCells>"
        if todas
        else ""
    )
    if "<mergeCells" in xml:
        xml = re.sub(r"<mergeCells[^>]*>.*?</mergeCells>", lambda _: bloque, xml, count=1, flags=re.S)
    elif bloque:
        xml = xml.replace("</sheetData>", f"</sheetData>{bloque}", 1)
    return re.sub(
        r'<dimension ref="[^"]*"\s*/>', f'<dimension ref="A1:{_col(h.ultima_col)}{h.ultima_fila}"/>', xml, count=1
    )


def _estilo(wb: openpyxl.Workbook, base: StyleArray | None, formato: int | None = None) -> int:
    """El número de estilo (el que llevan las celdas en el XML) de una copia de `base`, con un formato numérico si se pide."""
    e = copy(base) if base is not None else StyleArray()
    if formato is not None:
        e.numFmtId = formato
    return wb._cell_styles.add(e)


def _hoja_ordenes(filas: list[list], estilos: dict[int, int], resumen: str, desde: int = 4) -> _Hoja:
    """ORDENES: proveedor, ítem, código, descripción, cantidad, valor unitario, valor total (fórmula) e IVA (vacío, como en OC.xlsm).
    Cada celda lee de la hoja DINAMICA (cuyas filas empiezan en la 4), igual que el original."""
    xml, uniones = [], []
    for i, g in enumerate(filas):
        r, d = 2 + i, desde + i
        celdas = []
        for c in range(1, 27):
            s, ref = estilos[c], f"{_col(c)}{r}"
            if c == 1:
                celdas.append(_c_formula(ref, s, f"{resumen}!A{d}", g[0]))
            elif c == 2:
                celdas.append(
                    _c_formula(
                        ref, s, "ROWS($A$2:A2)" if i == 0 else f"IF(A{r}<>0,B{r - 1}+1,((B{r - 1}-B{r - 1})))", i + 1
                    )
                )
            elif c == 3:
                celdas.append(_c_formula(ref, s, f"{resumen}!B{d}", str(g[1])))
            elif c == 7:
                celdas.append(_c_formula(ref, s, f"{resumen}!C{d}", g[2]))
            elif c == 17:
                celdas.append(_c_formula(ref, s, f"{resumen}!D{d}", g[3]))
            elif c == 19:
                celdas.append(_c_formula(ref, s, f"{resumen}!E{d}", g[4]))
            elif c == 22:
                celdas.append(_c_formula(ref, s, f"S{r}*Q{r}", g[3] * g[4]))
            else:
                celdas.append(_c_vacia(ref, s))
        xml.append(_fila_xml(r, celdas, 15))
        uniones.extend(f"{_col(a)}{r}:{_col(b)}{r}" for a, b in _UNIONES_ORDENES)
    return _Hoja(xml, uniones, max(1 + len(filas), 1), 26)


def _hoja_dinamica(filas: list[list], s_texto: int, s_miles: int) -> _Hoja:
    xml = []
    for i, (empresa, cod, desc, cant, valor) in enumerate(filas):
        r = 4 + i
        xml.append(
            _fila_xml(
                r,
                [
                    _c_texto(f"A{r}", s_texto, empresa),
                    _c_texto(f"B{r}", s_texto, str(cod)),
                    _c_texto(f"C{r}", s_texto, desc),
                    _c_numero(f"D{r}", s_miles, cant),
                    _c_numero(f"E{r}", s_miles, valor),
                ],
            )
        )
    return _Hoja(xml, [], max(3 + len(filas), 3), 5)


def _hoja_valores(filas: list[list], s_texto: int, s_miles: int) -> _Hoja:
    xml = []
    for i, f in enumerate(filas):
        r = 2 + i
        xml.append(
            _fila_xml(
                r,
                [
                    _c_texto(f"A{r}", s_texto, str(f[0])),
                    _c_valor(f"B{r}", s_texto, f[1]),
                    _c_valor(f"C{r}", s_miles, f[2]),
                    _c_valor(f"D{r}", s_miles, f[3]),
                    _c_valor(f"E{r}", s_texto, f[4]),
                    _c_valor(f"F{r}", s_texto, f[5]),
                    _c_valor(f"G{r}", s_texto, f[6]),
                    _c_valor(f"H{r}", s_texto, f[7]),
                ],
            )
        )
    return _Hoja(xml, [], max(1 + len(filas), 1), 8)


def _libro_oc(grupos: list[tuple[str, str, list[list]]], columnas: list[str]) -> bytes:
    """Arma un libro con las tres hojas de la OC por cada grupo (sufijo del nombre, texto del encabezado de empresa, filas con las `columnas`).
    Un solo grupo con sufijo «» es la OC de siempre (hojas VALORES, DINAMICA y ORDENES); con varios, cada uno trae sus propias tres hojas."""
    wb = openpyxl.load_workbook(PLANTILLAS / "oc_base.xlsx")
    valores, dinamica, ordenes = wb["VALORES"], wb["DINAMICA"], wb["ORDENES"]
    # los formatos de la fila modelo de ORDENES (columna por columna), y la fila modelo se quita: sus celdas las escribe _hoja_ordenes
    miles = {17, 19, 22}
    estilos = {c: _estilo(wb, ordenes.cell(2, c)._style, _FORMATO_MILES if c in miles else None) for c in range(1, 27)}
    for c in range(1, 27):
        ordenes._cells.pop((2, c), None)
    for m in [m for m in list(ordenes.merged_cells.ranges) if m.min_row >= 2]:
        ordenes.merged_cells.ranges.discard(m)
    # Las filas de datos las escribe _hoja_*: no puede quedar NINGUNA fila (ni vacía, por una altura heredada de la plantilla) en esos números,
    # porque openpyxl la escribiría y la fila quedaría duplicada (Excel ofrece «reparar» un archivo así).
    for hoja, primera in ((valores, 2), (dinamica, 4), (ordenes, 2)):
        for fila in [r for r in hoja.row_dimensions if r >= primera]:
            del hoja.row_dimensions[fila]
    for c, nombre in enumerate(columnas, 1):
        valores.cell(1, c).value = nombre
    for c in range(1, 6):  # encabezado de DINAMICA (antes lo dibujaba la tabla dinámica)
        celda = dinamica.cell(3, c)
        celda.font, celda.fill, celda.alignment, celda.border = (
            _ESTILO_ENCABEZADO["font"],
            _ESTILO_ENCABEZADO["fill"],
            _ESTILO_ENCABEZADO["alignment"],
            _BORDE,
        )
    dinamica.column_dimensions["C"].width = 70
    s_texto, s_miles = _estilo(wb, None), _estilo(wb, None, _FORMATO_MILES)
    ind = {n: i for i, n in enumerate(columnas)}
    varios = len(grupos) > 1 or grupos[0][0] != ""
    inyecciones: dict[str, _Hoja] = {}
    for sufijo, encabezado_empresa, filas in grupos:
        v, d, o = (
            (wb.copy_worksheet(h) for h in (valores, dinamica, ordenes)) if varios else (valores, dinamica, ordenes)
        )
        v.title, d.title, o.title = f"VALORES{sufijo}", f"DINAMICA{sufijo}", f"ORDENES{sufijo}"
        o["A1"].value = encabezado_empresa
        resumen = _agrupar(filas, ind)
        inyecciones[v.title] = _hoja_valores(filas, s_texto, s_miles)
        inyecciones[d.title] = _hoja_dinamica(resumen, s_texto, s_miles)
        inyecciones[o.title] = _hoja_ordenes(resumen, estilos, f"'{d.title}'" if sufijo else d.title)
    if varios:
        for h in (valores, dinamica, ordenes):
            wb.remove(h)
    wb.active = 0
    return _inyectar(_a_bytes(wb), inyecciones)


def oc_xlsx(filas_valores: list[list], columnas: list[str]) -> bytes:
    """La ORDEN DE COMPRA: VALORES (los datos de cada producto a comprar y su proveedor ganador), DINAMICA (resumen por proveedor y producto) y ORDENES.
    filas_valores: una fila por producto a comprar, en el orden de `columnas` (exportador.COLUMNAS)."""
    return _libro_oc([("", "EMPRESA GANADORA", filas_valores)], columnas)


def alternativas_xlsx(por_puesto: dict[int, list[list]], columnas: list[str]) -> bytes:
    """El libro de ALTERNATIVAS: para el 2.º, 3.º y 4.º proveedor, las MISMAS TRES HOJAS de la OC (9 en total): «VALORES 2.º», «DINAMICA 2.º»,
    «ORDENES 2.º», «VALORES 3.º»... por_puesto: {2: [fila, ...], 3: [...], 4: [...]} con las filas en el orden de `columnas`: para cada producto
    por comprar, su oferta de ese puesto en el ranking (la 2.ª más barata, la 3.ª, la 4.ª)."""
    grupos = [(f" {p}.º", f"EMPRESA ({p}.º PROVEEDOR)", por_puesto.get(p, [])) for p in PUESTOS_ALTERNATIVOS]
    return _libro_oc(grupos, columnas)
