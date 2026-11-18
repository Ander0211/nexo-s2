"""
CARGA DE EXCEL DESDE LA PANTALLA
================================
Permite SUBIR un Excel (o CSV) de productos, proveedores o cotizaciones desde el panel «Cargar datos».

Funciona en DOS pasos, para que nada se cargue por sorpresa:
    1. REVISAR  (aplicar=False)  lee el archivo y cuenta qué pasaría: cuántos son nuevos, cuántos se
                                 actualizan, cuáles tienen error. NO escribe nada en la base de datos.
    2. CARGAR   (aplicar=True)   hace exactamente lo mismo y además lo guarda.
Las dos etapas comparten el mismo código: lo único que cambia es si se escribe o no.

Reglas generales:
    - Las filas con error se OMITEN (se informa cuáles y por qué); las demás se cargan.
    - Lo cargado queda como origen 'subido': es dato PROPIO y se conserva al pulsar «Actualizar Excel».
    - Los encabezados se reconocen sin importar tildes, mayúsculas ni espacios («Stock Max» = STOCKMAX).
    - Se aceptan archivos .xlsx, .xlsm y .csv (hasta 25 MB y 100.000 filas). Se lee la primera hoja.

Qué hace cada tipo de carga:
    productos     crea los nuevos y actualiza los existentes (solo los campos que el archivo traiga con valor).
    proveedores   crea los nuevos y cambia el nombre de los existentes.
    cotizaciones  crea o actualiza ofertas. El proveedor sale de la columna COD_EMPRESA / EMPRESA del archivo
                  o, si no la trae, del proveedor elegido en pantalla.

Este archivo NO conoce la web: recibe bytes y una conexión, y devuelve un diccionario con el resultado.
La ruta que lo usa es routers/cargas.py.
"""

import io
import sqlite3
from pathlib import Path

import openpyxl
import pandas as pd

from . import catalogo, excel_seguro
from . import normalizacion as nz
from .libros_excel import HOJA_META

TIPOS = ("productos", "proveedores", "cotizaciones")
MAX_BYTES = 25 * 1024 * 1024  # tamaño máximo del archivo: 25 MB
MAX_FILAS = 100_000  # filas máximas por archivo
MAX_ERRORES_MOSTRADOS = 100  # de los errores solo se detallan los primeros 100 (el total sí se cuenta)

# Marca interna para «el proveedor todavía no existe: se creará al cargar» (cotizaciones con proveedor nuevo).
_PROVEEDOR_NUEVO = "__nuevo__"

# Columnas de cada tipo: nombre estándar → encabezados aceptados (ya normalizados: mayúsculas, sin tildes).
# Si mañana alguien usa otro encabezado, se agrega aquí.
COLUMNAS = {
    "productos": {
        "COD": ("COD_PRODUCTO", "CODIGO", "COD_SALUDIPS", "COD"),
        "DESCRIPCION": ("DESCRIPCION", "PRODUCTO", "NOMBRE_PRODUCTO"),
        "STOCKMAX": ("STOCKMAX", "STOCK_MAX", "STOCK_MAXIMO", "MAXIMO"),
        "STOCKMED": ("STOCKMED", "STOCK_MED", "STOCK_MEDIO"),
        "STOCKMIN": ("STOCKMIN", "STOCK_MIN", "STOCK_MINIMO", "MINIMO"),
        "EXISTENCIAS": ("EXISTENCIAS", "EXISTENCIA", "CANTIDAD", "STOCK_ACTUAL"),
    },
    "proveedores": {
        "COD": ("CODIGO_EMPRESA", "COD_EMPRESA", "COD_PROVEEDOR", "CODIGO"),
        "NOMBRE": ("NOMBRE", "EMPRESA", "PROVEEDOR", "NOMBRE_PROVEEDOR"),
    },
    "cotizaciones": {
        "COD_PRODUCTO": ("COD_PRODUCTO", "CODIGO_PRODUCTO", "COD_SALUDIPS", "CODIGO"),
        "VALOR": ("VALOR", "PRECIO", "VALOR_UNITARIO", "PRECIO_UNITARIO"),
        "COD_EMPRESA": ("COD_EMPRESA", "CODIGO_EMPRESA", "COD_PROVEEDOR"),
        "EMPRESA": ("NOMBRE_EMPRESA", "EMPRESA", "PROVEEDOR", "NOMBRE_PROVEEDOR"),
        "PRESENTACION": ("PRESENTACION",),
        # Opcional: cuántas unidades PUEDE entregar el proveedor de este producto (la ficha FR-GDS-07 la trae como «CANTIDAD DISPONIBLE PROVEEDOR»).
        "DISPONIBLE": (
            "CANTIDAD_DISPONIBLE",
            "DISPONIBLE",
            "CANTIDAD_DISPONIBLE_PROVEEDOR",
            "UNIDADES_DISPONIBLES",
            "STOCK_PROVEEDOR",
        ),
    },
}
# Columnas sin las cuales el archivo no sirve (el resto son opcionales).
REQUERIDAS = {"productos": ["COD"], "proveedores": ["NOMBRE"], "cotizaciones": ["COD_PRODUCTO", "VALOR"]}


class CargaError(Exception):
    """Problema con el ARCHIVO completo (formato, tamaño, columnas que faltan...). Trae su código HTTP."""

    def __init__(self, mensaje: str, estado: int = 422):
        """Guarda el mensaje (para mostrárselo al usuario) y el código HTTP (422 por defecto)."""
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado


# --------------------------------------------------------------------------- Lectura del archivo
def _leer_csv(contenido: bytes) -> pd.DataFrame:
    """Lee un CSV probando primero UTF-8 (con tildes) y, si falla, Latin-1 (el de Excel antiguo en Windows).
    `sep=None` detecta solo si el separador es coma o punto y coma."""
    try:
        return pd.read_csv(io.BytesIO(contenido), dtype=str, sep=None, engine="python", encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(contenido), dtype=str, sep=None, engine="python", encoding="latin-1")


def _leer_ficha(contenido: bytes) -> pd.DataFrame | None:
    """Si el archivo es la FICHA DE SOLICITUD DE COTIZACIÓN (FR-GDS-07) que descargó el proveedor, la lee y devuelve las columnas estándar de
    «cotizaciones»; si no lo es, devuelve None (y se lee como cualquier otro Excel).

    La ficha tiene el encabezado en la fila 11 (no en la 1), celdas combinadas y, al final, la tabla «Control de Cambios del Documento»:
      COD_PRODUCTO ← «CODIGO PRODUCTO»      VALOR ← «PRECIO» (el precio SIN IVA)      PRESENTACION ← «UNIDAD DE EMPAQUE / PRESENTACION»
      DISPONIBLE ← «CANTIDAD DISPONIBLE PROVEEDOR» (cuántas unidades puede entregar; opcional)
    El proveedor sale de la hoja muy oculta de la ficha (la pone la aplicación al descargarla); si no está, se elige en pantalla.
    FILA es el número de fila real de la ficha, para poder decir «error en la fila 57»."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception:
        return None
    try:
        filas = wb.worksheets[0].iter_rows(values_only=True)
        columnas = None
        datos: list[list] = []
        for n, fila in enumerate(filas, start=1):
            if columnas is None:
                if n > 30:
                    return None  # no hay encabezado de ficha en las primeras filas: no es una ficha
                nombres = [nz.nombre_columna(c) if c is not None else "" for c in fila]
                if "CODIGO_PRODUCTO" in nombres and "PRECIO" in nombres:
                    columnas = {
                        "cod": nombres.index("CODIGO_PRODUCTO"),
                        "precio": nombres.index("PRECIO"),
                        "empaque": next((i for i, x in enumerate(nombres) if x.startswith("UNIDAD_DE_EMPAQUE")), None),
                        "disponible": next(
                            (i for i, x in enumerate(nombres) if x.startswith("CANTIDAD_DISPONIBLE")), None
                        ),
                    }
                continue
            primera = fila[0] if fila else None
            if isinstance(primera, str) and primera.strip().lower().startswith("control de cambios"):
                break  # aquí termina la lista de productos
            cod = fila[columnas["cod"]] if len(fila) > columnas["cod"] else None
            if cod is None or not str(cod).strip():
                continue
            precio = fila[columnas["precio"]] if len(fila) > columnas["precio"] else None
            empaque = (
                fila[columnas["empaque"]]
                if columnas["empaque"] is not None and len(fila) > columnas["empaque"]
                else None
            )
            disponible = (
                fila[columnas["disponible"]]
                if columnas["disponible"] is not None and len(fila) > columnas["disponible"]
                else None
            )
            datos.append(
                [
                    n,
                    str(cod).strip(),
                    None if precio is None else str(precio).strip(),
                    None if empaque is None else str(empaque).strip(),
                    None if disponible is None else str(disponible).strip(),
                ]
            )
        if columnas is None:
            return None
        cod_empresa = None
        if HOJA_META in wb.sheetnames:  # la hoja muy oculta que puso la aplicación al descargar la ficha
            valor = wb[HOJA_META]["B1"].value
            cod_empresa = str(valor).strip() if valor not in (None, "") else None
    finally:
        wb.close()
    df = pd.DataFrame(datos, columns=["FILA", "COD_PRODUCTO", "VALOR", "PRESENTACION", "DISPONIBLE"], dtype=object)
    df["COD_EMPRESA"] = cod_empresa
    df["EMPRESA"] = None
    return df[["COD_PRODUCTO", "VALOR", "COD_EMPRESA", "EMPRESA", "PRESENTACION", "DISPONIBLE", "FILA"]]


def leer_archivo(contenido: bytes, nombre: str, tipo: str) -> pd.DataFrame:
    """Convierte el archivo subido en una tabla con los nombres de columna estándar de COLUMNAS.

    Además agrega la columna FILA con el número de fila que el usuario ve en Excel (la 1 es el encabezado,
    así que los datos empiezan en la 2), para poder decirle «error en la fila 7».
    Lanza CargaError si el archivo no se puede usar.
    """
    if not contenido:
        raise CargaError("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise CargaError(
            f"El archivo pesa {len(contenido) / 1e6:.1f} MB y el máximo es {MAX_BYTES // (1024 * 1024)} MB.", 413
        )
    extension = Path(nombre or "").suffix.lower()
    if extension in (".xlsx", ".xlsm") and (problema := excel_seguro.revisar_xlsx(contenido)):
        raise CargaError(problema, 413)  # una «bomba de compresión»: pesa poco y abierta ocupa cientos de MB
    if tipo == "cotizaciones" and extension in (".xlsx", ".xlsm"):
        ficha = _leer_ficha(contenido)  # ¿es la ficha FR-GDS-07 que devuelve el proveedor?
        if ficha is not None:
            if ficha.empty:
                raise CargaError("La ficha no trae ningún producto.")
            if len(ficha) > MAX_FILAS:
                raise CargaError(f"La ficha tiene {len(ficha):,} filas y el máximo es {MAX_FILAS:,}.".replace(",", "."))
            return ficha
    try:
        if extension in (".xlsx", ".xlsm"):
            # dtype=str: todo como TEXTO, así «0041» no se convierte en el número 41.
            df = nz.leer_excel(io.BytesIO(contenido))
        elif extension == ".csv":
            df = _leer_csv(contenido)
        else:
            raise CargaError("Formato no admitido: sube un archivo .xlsx, .xlsm o .csv.")
    except CargaError:
        raise
    except Exception as e:  # cualquier otro problema al abrirlo (archivo dañado, no es un Excel real...)
        raise CargaError(f"No se pudo leer el archivo ({type(e).__name__}). ¿Es un Excel válido?") from None
    if df.empty:
        raise CargaError("El archivo no tiene filas de datos (¿solo trae los encabezados?).")
    if len(df) > MAX_FILAS:
        raise CargaError(f"El archivo tiene {len(df):,} filas y el máximo es {MAX_FILAS:,}.".replace(",", "."))

    # Cada encabezado del archivo se traduce a su nombre estándar. Una columna del archivo se usa una sola vez.
    por_norm = {nz.nombre_columna(c): c for c in df.columns}
    salida, usadas = {}, set()
    for estandar, alias in COLUMNAS[tipo].items():
        origen = next((por_norm[a] for a in alias if a in por_norm and a not in usadas), None)
        if origen is None:
            salida[estandar] = pd.Series([None] * len(df), dtype=object)  # columna ausente: queda vacía
        else:
            usadas.add(nz.nombre_columna(origen))
            salida[estandar] = df[origen]
    # Obligatorias: el archivo debe TRAER la columna (aunque alguna celda esté vacía; eso es un error por fila).
    faltan = [COLUMNAS[tipo][c][0] for c in REQUERIDAS[tipo] if not any(a in por_norm for a in COLUMNAS[tipo][c])]
    if faltan:
        raise CargaError(f"Faltan las columnas obligatorias {faltan}. Encabezados encontrados: {list(df.columns)}.")
    resultado = pd.DataFrame(salida)
    resultado["FILA"] = range(2, len(resultado) + 2)
    return resultado


# --------------------------------------------------------------------------- Ayudas del resultado
def _resultado(tipo: str, aplicar: bool, filas: int) -> dict:
    """El diccionario de resultado, con todos los contadores en cero."""
    return {
        "tipo": tipo,
        "aplicado": aplicar,
        "filas": filas,  # filas leídas del archivo
        "nuevos": 0,  # se crean
        "actualizados": 0,  # ya existían y cambian
        "sin_cambios": 0,  # ya existían y son iguales
        "omitidas": 0,  # cotizaciones sin precio (el proveedor no cotizó ese producto)
        "repetidas": 0,  # cotizaciones repetidas dentro del archivo (se usa la más barata)
        "no_cambian_ranking": 0,  # cotizaciones que no cambian el ranking (el proveedor ya ofrecía igual o más barato)
        "total_errores": 0,  # cuántas filas tienen error (no se cargan)
        "errores": [],  # detalle de las primeras filas con error: {"fila": 7, "motivo": "..."}
        "avisos": [],  # notas informativas para el usuario
        "proveedor": None,  # solo cotizaciones: el proveedor usado por defecto
    }


def _error(res: dict, fila: int, motivo: str) -> None:
    """Anota una fila con error (se cuenta siempre; solo se detallan las primeras MAX_ERRORES_MOSTRADOS)."""
    res["total_errores"] += 1
    if len(res["errores"]) < MAX_ERRORES_MOSTRADOS:
        res["errores"].append({"fila": fila, "motivo": motivo})


def _leer_numero(crudo, campo: str, fila: int, res: dict) -> tuple[float | None, bool]:
    """Lee un número opcional de una celda. Devuelve (valor, es_válido).

    Celda vacía → (None, True): «no viene dato», no es error.
    Texto que no es número, o negativo → se anota el error y devuelve (None, False).
    """
    if nz.texto(crudo) is None:
        return None, True
    n = nz.numero(crudo)
    if n is None:
        _error(res, fila, f"{campo}: «{nz.texto(crudo)}» no es un número.")
        return None, False
    if n < 0:
        _error(res, fila, f"{campo}: no puede ser negativo ({n:g}).")
        return None, False
    return n, True


# --------------------------------------------------------------------------- Productos
def procesar_productos(con: sqlite3.Connection, df: pd.DataFrame, aplicar: bool) -> dict:
    """Crea los productos nuevos y actualiza los existentes con lo que el archivo traiga.

    - Un producto EXISTENTE se actualiza solo en los campos que la fila trae con valor (celda vacía = no tocar).
    - Un producto NUEVO necesita al menos la descripción; el stock es opcional (sin StockMax queda «sin stock definido»).
    """
    res = _resultado("productos", aplicar, len(df))
    existentes = {
        nz.clave_codigo(r["cod"]): dict(r) for r in con.execute("SELECT * FROM productos")
    }  # sin distinguir mayúsculas: «a1» es «A1»
    vistos: set[str] = set()
    operaciones: list[
        tuple
    ] = []  # lo que se hará al aplicar: ("crear", cod, desc, campos) | ("actualizar", cod, cambios)

    for r in df.itertuples(index=False):
        fila = r.FILA
        cod = nz.codigo_producto(r.COD)
        if not cod:
            _error(res, fila, "Falta el código del producto.")
            continue
        if nz.clave_codigo(cod) in vistos:
            _error(res, fila, f"El código {cod} está repetido en el archivo; se usa solo la primera fila.")
            continue
        vistos.add(nz.clave_codigo(cod))
        descripcion = nz.texto(r.DESCRIPCION)

        # Los cuatro campos numéricos: solo entran los que traen un valor válido.
        campos, todo_bien = {}, True
        for campo, crudo, titulo in (
            ("stock_max", r.STOCKMAX, "StockMax"),
            ("stock_med", r.STOCKMED, "StockMed"),
            ("stock_min", r.STOCKMIN, "StockMin"),
            ("existencias", r.EXISTENCIAS, "Existencias"),
        ):
            valor, valido = _leer_numero(crudo, titulo, fila, res)
            if not valido:
                todo_bien = False
            elif valor is not None:
                campos[campo] = valor
        if not todo_bien:
            continue

        actual = existentes.get(nz.clave_codigo(cod))
        if actual:
            cod = actual[
                "cod"
            ]  # el producto ya existe (aunque el archivo lo escriba con otras mayúsculas): se actualiza ese, no se crea otro
            cambios = dict(campos)
            if descripcion:
                cambios["descripcion"] = descripcion
            maximo = cambios.get("stock_max", actual["stock_max"])
            minimo = cambios.get("stock_min", actual["stock_min"])
            if maximo is not None and minimo is not None and minimo > maximo:
                _error(res, fila, f"El stock mínimo ({minimo:g}) es mayor que el máximo ({maximo:g}).")
                continue
            distintos = {c: v for c, v in cambios.items() if actual[c] != v}
            if distintos:
                res["actualizados"] += 1
                operaciones.append(("actualizar", cod, distintos))
            else:
                res["sin_cambios"] += 1
        else:
            if not descripcion:
                _error(res, fila, f"El producto nuevo {cod} necesita una descripción.")
                continue
            if campos.get("stock_max") is not None and campos.get("stock_min") is not None:
                if campos["stock_min"] > campos["stock_max"]:
                    _error(res, fila, f"El stock mínimo ({campos['stock_min']:g}) es mayor que el máximo.")
                    continue
            res["nuevos"] += 1
            operaciones.append(("crear", cod, descripcion, campos))

    if aplicar and operaciones:
        with con:  # una sola transacción: o se carga todo lo válido o nada
            for op in operaciones:
                if op[0] == "crear":
                    catalogo.crear_producto(con, op[1], op[2], origen="subido", **op[3])
                else:
                    catalogo.actualizar_producto(con, op[1], op[2], origen="subido")
    return res


# --------------------------------------------------------------------------- Proveedores
def procesar_proveedores(con: sqlite3.Connection, df: pd.DataFrame, aplicar: bool) -> dict:
    """Crea los proveedores nuevos y cambia el nombre de los que ya existen.

    Cómo se reconoce cada fila:
      - con código que ya existe   → es ese proveedor; si el nombre cambió, se renombra.
      - con código que NO existe   → se crea con ese código (error si su nombre ya lo tiene otro proveedor).
      - sin código                 → se busca por nombre; si no existe se crea con un código automático (desde 1000).
    """
    res = _resultado("proveedores", aplicar, len(df))
    filas_db = con.execute("SELECT cod, nombre FROM empresas").fetchall()
    por_cod = {r["cod"]: r["nombre"] for r in filas_db}
    por_nombre = {
        nz.clave_nombre(r["nombre"]): r["cod"] for r in filas_db
    }  # regla de todo el sistema: sin tildes, mayúsculas, espacios ni signos
    tocados: set[str] = set()  # códigos creados o renombrados en ESTE archivo (para detectar repeticiones)
    operaciones: list[tuple] = []  # ("crear", nombre, cod|None) | ("renombrar", cod, nombre)

    for r in df.itertuples(index=False):
        fila = r.FILA
        nombre = nz.texto(r.NOMBRE)
        cod = nz.codigo_empresa(r.COD)
        if not nombre or len(nz.clave_nombre(nombre)) < 2:
            _error(res, fila, "Falta el nombre del proveedor.")
            continue
        clave = nz.clave_nombre(nombre)
        if cod and cod in por_cod:
            if cod in tocados and por_cod[cod] != nombre:
                _error(res, fila, f"El código {cod} aparece dos veces en el archivo con nombres distintos.")
            elif por_cod[cod] == nombre:
                res["sin_cambios"] += 1
            elif por_nombre.get(clave, cod) != cod:
                _error(res, fila, f"El nombre «{nombre}» ya lo tiene el proveedor {por_nombre[clave]}.")
            else:
                por_nombre.pop(nz.clave_nombre(por_cod[cod]), None)
                por_nombre[clave] = cod
                por_cod[cod] = nombre
                tocados.add(cod)
                res["actualizados"] += 1
                operaciones.append(("renombrar", cod, nombre))
        elif cod:
            if clave in por_nombre:
                _error(res, fila, f"«{nombre}» ya existe con el código {por_nombre[clave]}.")
            else:
                por_cod[cod] = nombre
                por_nombre[clave] = cod
                tocados.add(cod)
                res["nuevos"] += 1
                operaciones.append(("crear", nombre, cod))
        elif clave in por_nombre:
            res["sin_cambios"] += 1  # sin código y el nombre ya existe: es ese mismo proveedor
        else:
            por_nombre[clave] = "(nuevo)"
            res["nuevos"] += 1
            operaciones.append(("crear", nombre, None))

    if aplicar and operaciones:
        with con:
            for op in operaciones:
                if op[0] == "crear":
                    catalogo.crear_empresa(con, op[1], cod=op[2], origen="subido")
                else:
                    catalogo.actualizar_empresa(con, op[1], op[2], origen="subido")
    return res


# --------------------------------------------------------------------------- Cotizaciones
def _proveedor_por_defecto(con: sqlite3.Connection, cod_empresa: str | None, empresa_nueva: str | None) -> dict | None:
    """El proveedor elegido en pantalla para las filas que no indican el suyo.

    Devuelve {"cod", "nombre", "nuevo"} o None si no se eligió ninguno. Si se escribió un nombre que ya existe,
    se usa ese proveedor (no se duplica); si no existe, queda «nuevo» y se creará al cargar.
    """
    if cod_empresa:
        cod = nz.codigo_empresa(cod_empresa)
        fila = con.execute("SELECT nombre FROM empresas WHERE cod = ?", (cod,)).fetchone()
        if not fila:
            raise CargaError("Ese proveedor no existe.", 404)
        return {"cod": cod, "nombre": fila["nombre"], "nuevo": False}
    if empresa_nueva:
        nombre = nz.texto(empresa_nueva)
        if not nombre or len(nombre) < 2:
            raise CargaError("Escribe el nombre del proveedor nuevo (mínimo 2 letras).")
        existente = catalogo.buscar_empresa_por_nombre(con, nombre)
        if existente:
            return {"cod": existente["cod"], "nombre": existente["nombre"], "nuevo": False}
        return {"cod": None, "nombre": nombre, "nuevo": True}
    return None


def procesar_cotizaciones(
    con: sqlite3.Connection,
    df: pd.DataFrame,
    aplicar: bool,
    cod_empresa: str | None = None,
    empresa_nueva: str | None = None,
) -> dict:
    """Crea o actualiza ofertas (origen 'subido').

    De dónde sale el proveedor de cada fila, en este orden:
      1. la columna COD_EMPRESA del archivo   (debe ser un proveedor que ya exista)
      2. la columna EMPRESA (nombre)          (debe coincidir con un proveedor que ya exista)
      3. el proveedor elegido en pantalla     (uno existente, o uno nuevo que se crea al cargar)

    Reglas de las filas:
      - sin precio o con precio 0 → se OMITE en silencio (el proveedor no cotizó ese producto; es lo normal
        cuando devuelve la ficha de cotización con huecos)
      - precio que no es número, o negativo → error
      - producto que no existe en el catálogo → error (hay que crearlo antes en la pestaña Productos)
      - el mismo producto y proveedor repetido en el archivo → se usa el más barato

    Una oferta subida NO reemplaza la del Excel base: si ese proveedor ya ofrecía el producto más barato en el
    portafolio, esa sigue contando (el ranking siempre usa el menor precio de cada proveedor). Para avisarlo,
    se cuenta en «no_cambian_ranking».
    """
    res = _resultado("cotizaciones", aplicar, len(df))
    defecto = _proveedor_por_defecto(con, cod_empresa, empresa_nueva)
    res["proveedor"] = defecto
    if not df["COD_EMPRESA"].notna().any() and not df["EMPRESA"].notna().any() and defecto is None:
        raise CargaError(
            "Este archivo no trae la columna del proveedor (COD_EMPRESA o EMPRESA): elige el proveedor de la cotización."
        )

    productos = {r["cod"] for r in con.execute("SELECT cod FROM productos")}
    empresas = con.execute("SELECT cod, nombre FROM empresas").fetchall()
    cods_empresa = {r["cod"] for r in empresas}
    cod_por_nombre = {nz.clave_nombre(r["nombre"]): r["cod"] for r in empresas}

    # Paso 1: validar cada fila y quedarse con la oferta más barata de cada (producto, proveedor).
    mejores: dict[
        tuple[str, str], tuple[float, str | None, float | None]
    ] = {}  # (producto, proveedor) → (valor, presentación, disponible)
    for r in df.itertuples(index=False):
        fila = r.FILA
        cod_producto = nz.codigo_producto(r.COD_PRODUCTO)
        if not cod_producto:
            _error(res, fila, "Falta el código del producto.")
            continue
        crudo = nz.texto(r.VALOR)
        if crudo is None:
            res["omitidas"] += 1  # sin precio: no cotizó este producto
            continue
        valor = nz.numero(crudo)
        if valor is None or valor < 0:
            _error(res, fila, f"El valor «{crudo}» no es un precio válido.")
            continue
        if valor == 0:
            res["omitidas"] += 1  # precio 0 = sin precio
            continue
        # La cantidad disponible es opcional: vacía = «no dijo cuánto tiene». Si la escribe, tiene que ser un número (0 = no tiene unidades).
        crudo_disp = nz.texto(getattr(r, "DISPONIBLE", None))
        disponible = None
        if crudo_disp is not None:
            disponible = nz.numero(crudo_disp)
            if disponible is None or disponible < 0:
                _error(res, fila, f"La cantidad disponible «{crudo_disp}» no es un número válido.")
                continue
        if cod_producto not in productos:
            _error(
                res,
                fila,
                f"El producto {cod_producto} no existe en el catálogo (créalo antes en la pestaña Productos).",
            )
            continue

        cod_e, nombre_e = nz.codigo_empresa(r.COD_EMPRESA), nz.texto(r.EMPRESA)
        if cod_e:
            if cod_e not in cods_empresa:
                _error(res, fila, f"El proveedor {cod_e} no existe (créalo antes en la pestaña Proveedores).")
                continue
            proveedor = cod_e
        elif nombre_e:
            proveedor = cod_por_nombre.get(nz.clave_nombre(nombre_e))
            if proveedor is None:
                _error(res, fila, f"El proveedor «{nombre_e}» no existe (créalo antes en la pestaña Proveedores).")
                continue
        elif defecto:
            proveedor = defecto["cod"] or _PROVEEDOR_NUEVO
        else:
            _error(res, fila, "La fila no indica el proveedor.")
            continue

        clave = (cod_producto, proveedor)
        previa = nz.texto(r.PRESENTACION)
        if clave in mejores:
            res["repetidas"] += 1
            if valor >= mejores[clave][0]:
                continue
        mejores[clave] = (valor, previa, disponible)

    # Paso 2: comparar con lo que ya hay en la base para saber qué se crea, qué se actualiza y qué no cambia.
    subidas: dict[tuple[str, str], sqlite3.Row] = {}  # ofertas 'subido' ya existentes
    minimo_otras: dict[tuple[str, str], float] = {}  # precio más bajo de las ofertas NO subidas de ese proveedor
    for o in con.execute("SELECT id, cod_producto, cod_empresa, valor, presentacion, disponible, origen FROM ofertas"):
        clave = (o["cod_producto"], o["cod_empresa"])
        if o["origen"] == "subido":
            subidas[clave] = o
        else:
            minimo_otras[clave] = min(minimo_otras.get(clave, o["valor"]), o["valor"])

    operaciones: list[
        tuple
    ] = []  # ("crear", cod_producto, proveedor, valor, presentacion, disponible) | ("actualizar", id, valor, presentacion, disponible)
    for (cod_producto, proveedor), (valor, presentacion, disponible) in mejores.items():
        if (
            proveedor != _PROVEEDOR_NUEVO
            and minimo_otras.get((cod_producto, proveedor)) is not None
            and minimo_otras[(cod_producto, proveedor)] <= valor
        ):
            res["no_cambian_ranking"] += 1
        ya = subidas.get((cod_producto, proveedor)) if proveedor != _PROVEEDOR_NUEVO else None
        if ya is None:
            res["nuevos"] += 1
            operaciones.append(("crear", cod_producto, proveedor, valor, presentacion, disponible))
        elif (
            ya["valor"] == valor
            and (ya["presentacion"] or None) == (presentacion or None)
            and ya["disponible"] == disponible
        ):
            res["sin_cambios"] += 1
        else:
            res["actualizados"] += 1
            operaciones.append(("actualizar", ya["id"], valor, presentacion, disponible))

    if defecto and defecto["nuevo"]:
        res["avisos"].append(f"Se {'creó' if aplicar else 'creará'} el proveedor nuevo «{defecto['nombre']}».")

    if aplicar and operaciones:
        with con:
            nuevo = None  # código del proveedor nuevo, creado una sola vez y solo si alguna fila lo necesita
            for op in operaciones:
                if op[0] == "crear":
                    proveedor = op[2]
                    if proveedor == _PROVEEDOR_NUEVO:
                        if nuevo is None:
                            nuevo = catalogo.crear_empresa(con, defecto["nombre"], origen="subido")["cod"]
                        proveedor = nuevo
                    con.execute(
                        "INSERT INTO ofertas (cod_producto, cod_empresa, valor, presentacion, disponible, origen) "
                        "VALUES (?,?,?,?,?, 'subido')",
                        (op[1], proveedor, op[3], op[4], op[5]),
                    )
                else:
                    con.execute(
                        "UPDATE ofertas SET valor = ?, presentacion = ?, disponible = ?, creado = datetime('now','localtime') WHERE id = ?",
                        (op[2], op[3], op[4], op[1]),
                    )
    return res


# --------------------------------------------------------------------------- Punto de entrada
def procesar(
    con: sqlite3.Connection,
    tipo: str,
    contenido: bytes,
    nombre: str,
    aplicar: bool = False,
    cod_empresa: str | None = None,
    empresa_nueva: str | None = None,
) -> dict:
    """Lee el archivo y lo procesa según su tipo. Es lo único que llama la ruta (routers/cargas.py).

    aplicar=False → solo revisa y cuenta (no escribe).   aplicar=True → carga de verdad.
    cod_empresa / empresa_nueva solo se usan en las cotizaciones (el proveedor elegido en pantalla).
    """
    if tipo not in TIPOS:
        raise CargaError("Tipo de carga desconocido.", 404)
    df = leer_archivo(contenido, nombre, tipo)
    if tipo == "productos":
        return procesar_productos(con, df, aplicar)
    if tipo == "proveedores":
        return procesar_proveedores(con, df, aplicar)
    return procesar_cotizaciones(con, df, aplicar, cod_empresa, empresa_nueva)
