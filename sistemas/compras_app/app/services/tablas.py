"""
LAS 5 TABLAS DE LOS EXCEL (la capa que el usuario puede ver y editar)
=====================================================================
Cada Excel de origen se guarda en la base de datos como una tabla PROPIA, con los MISMOS encabezados que tiene el
Excel (COD_PRODUCTO, StockMax, CODIGO_EMPRESA, ...) y con TODAS sus filas tal como vinieron (incluidos los códigos
repetidos, los proveedores sin nombre, las filas sin precio...). Son tablas «espejo»:

    05-STOCK.xlsx          → x_stock          COD_PRODUCTO · DESCRIPCION · StockMax · StockMed · StockMin
    06-EXISTENCIAS.xlsx    → x_existencias    COD_PRODUCTO · DESCRIPCION · CANTIDAD
    EMPRESA.xlsx           → x_empresas       CODIGO_EMPRESA · NOMBRE
    FICHA_COTIZACION.xlsx  → x_ficha          COD_SALUDIPS · DESCRIPCION · TIPO_INSUMO
    PORTAFOLIO.xlsx        → x_portafolio     COD_EMPRESA · COD_PRODUCTO · DESCRIPCION · VALOR · PRESENTACION

La pantalla «Administración» trabaja sobre estas tablas (ver, buscar, editar, adicionar, eliminar). A partir de ellas
`importador.recalcular()` calcula todo lo demás (productos, ofertas, proveedores, avisos) para el tablero de compras.

Reglas de esta capa:
- Los valores se guardan como TEXTO, tal cual venían (solo se les quitan los espacios de los extremos al escribirlos
  desde la pantalla). La limpieza «de verdad» (códigos como 5929.0, números con coma...) la hace el recálculo,
  con normalizacion.py. Así la tabla muestra lo mismo que el Excel.
- Cada fila tiene un número interno `id` (no es una columna del Excel) para poder editarla o borrarla aunque haya
  filas repetidas.
- Este módulo NO recalcula ni guarda historial: solo lee y escribe estas 5 tablas. Quien lo orquesta es admin.py.
"""

import io
import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import contacto, excel_seguro
from . import normalizacion as nz

MAX_BYTES = 25 * 1024 * 1024  # tamaño máximo de un Excel subido: 25 MB (sin tope de filas)
MAX_LARGO_CELDA = 300  # una celda de texto no puede pasar de 300 caracteres


class TablaError(Exception):
    """Problema de negocio con una tabla (no existe, dato inválido...). Lleva el código HTTP que corresponde."""

    def __init__(self, mensaje: str, estado: int = 422):
        super().__init__(mensaje)
        self.mensaje, self.estado = mensaje, estado


class ImportacionError(Exception):
    """Problema con los archivos de origen (falta un archivo o una columna)."""


@dataclass(frozen=True, eq=False)
class Tabla:
    """Todo lo que hay que saber de una de las 5 tablas."""

    clave: str  # nombre corto que usa la API: "stock", "existencias", "empresas", "ficha", "portafolio"
    titulo: str  # el que ve el usuario
    archivo: str  # Excel de origen (carpeta data/excel)
    hoja: str  # nombre de la hoja al descargar la tabla como Excel
    sql: str  # nombre de la tabla en SQLite
    columnas: tuple[str, ...]  # encabezados EXACTOS del Excel, en su orden
    numericas: frozenset[str] = frozenset()  # columnas que deben ser números
    obligatorias: tuple[str, ...] = ()  # sin estas no se puede crear ni guardar una fila
    exigidas: tuple[str, ...] = ()  # columnas que el Excel debe traer (si no, no sirve)
    alias: dict = field(default_factory=dict)  # encabezado exacto → otros nombres aceptados al leer un Excel
    clave_natural: tuple[str, ...] = ()  # columnas que identifican una fila (para «agregar y actualizar»)
    normalizadores: dict = field(default_factory=dict)  # columna clave → función que la deja en formato único
    unicas: tuple[str, ...] = ()  # columnas cuyo valor tampoco puede repetirse (además de la llave), p. ej. el NOMBRE
    conservar: tuple[
        str, ...
    ] = ()  # columnas que NO vienen del Excel base: al «reemplazar» se conservan las de cada fila
    validadores: dict = field(default_factory=dict)  # columna → función que valida y deja el valor en formato único
    extras: tuple[tuple[str, str, str], ...] = ()  # columnas SOLO de lectura: (clave, título, va después de la columna)
    necesaria: bool = (
        False  # ¿el sistema la NECESITA para funcionar? (la pantalla pide por nombre los Excel necesarios que faltan)
    )
    para_que: str = ""  # en una frase, para qué sirve este Excel (se le muestra a quien tiene que subirlo)


TABLAS: dict[str, Tabla] = {
    t.clave: t
    for t in (
        Tabla(
            clave="stock",
            titulo="Stock",
            archivo="05-STOCK.xlsx",
            necesaria=True,
            para_que="Cuánto quiere tener la Clínica de cada producto (stock máximo y mínimo). Junto con las existencias, es lo que calcula cuánto hay que comprar.",
            hoja="_05_STOCK",
            sql="x_stock",
            columnas=("COD_PRODUCTO", "DESCRIPCION", "StockMax", "StockMed", "StockMin"),
            numericas=frozenset({"StockMax", "StockMed", "StockMin"}),
            obligatorias=("COD_PRODUCTO",),
            exigidas=("COD_PRODUCTO", "StockMax"),
            alias={
                "COD_PRODUCTO": ("COD_PRODUCTO", "CODIGO"),
                "StockMax": ("STOCKMAX", "STOCK_MAX"),
                "StockMed": ("STOCKMED", "STOCK_MED"),
                "StockMin": ("STOCKMIN", "STOCK_MIN"),
            },
            clave_natural=("COD_PRODUCTO",),
            normalizadores={"COD_PRODUCTO": nz.codigo_producto},
        ),
        Tabla(
            clave="existencias",
            titulo="Existencias",
            archivo="06-EXISTENCIAS.xlsx",
            necesaria=True,
            para_que="Cuántas unidades hay hoy de cada producto. Sin este archivo el sistema cree que no hay nada y propone comprarlo todo.",
            hoja="06-EXISTENCIAS",
            sql="x_existencias",
            columnas=("COD_PRODUCTO", "DESCRIPCION", "CANTIDAD"),
            numericas=frozenset({"CANTIDAD"}),
            obligatorias=("COD_PRODUCTO", "CANTIDAD"),
            exigidas=("COD_PRODUCTO", "CANTIDAD"),
            alias={"COD_PRODUCTO": ("COD_PRODUCTO", "CODIGO"), "CANTIDAD": ("CANTIDAD", "EXISTENCIAS")},
            clave_natural=("COD_PRODUCTO",),
            normalizadores={"COD_PRODUCTO": nz.codigo_producto},
        ),
        Tabla(
            clave="empresas",
            titulo="Empresas",
            archivo="EMPRESA.xlsx",
            necesaria=True,
            para_que="Los nombres de los proveedores. Sin este archivo salen como «Proveedor N (sin nombre)».",
            hoja="EMPRESA",
            sql="x_empresas",
            columnas=("CODIGO_EMPRESA", "NOMBRE", "TELEFONO", "CORREO"),
            # TELEFONO y CORREO no vienen en EMPRESA.xlsx: se escriben desde la pantalla y son obligatorios al agregar o
            # editar una empresa (la importación del Excel no los exige y, al reemplazar, conserva los que ya había).
            obligatorias=("CODIGO_EMPRESA", "TELEFONO", "CORREO"),
            exigidas=("CODIGO_EMPRESA", "NOMBRE"),
            alias={
                "CODIGO_EMPRESA": ("CODIGO_EMPRESA", "COD_EMPRESA"),
                "NOMBRE": ("NOMBRE", "EMPRESA"),
                "TELEFONO": ("TELEFONO", "CELULAR", "TEL"),
                "CORREO": ("CORREO", "EMAIL", "CORREO_ELECTRONICO", "E_MAIL"),
            },
            clave_natural=("CODIGO_EMPRESA",),
            normalizadores={"CODIGO_EMPRESA": nz.codigo_empresa},
            unicas=("NOMBRE",),
            conservar=("TELEFONO", "CORREO"),
            validadores={"TELEFONO": contacto.normalizar_telefono, "CORREO": contacto.normalizar_correo},
        ),
        Tabla(
            clave="ficha",
            titulo="Ficha de cotización",
            archivo="FICHA_COTIZACION.xlsx",
            necesaria=False,
            para_que="El catálogo de productos a cotizar y su tipo de insumo. Es opcional: suma productos al tablero, pero el sistema funciona sin él.",
            hoja="FICHA_COTIZACION",
            sql="x_ficha",
            columnas=("COD_SALUDIPS", "DESCRIPCION", "TIPO_INSUMO"),
            obligatorias=("COD_SALUDIPS",),
            exigidas=("COD_SALUDIPS",),
            alias={"COD_SALUDIPS": ("COD_SALUDIPS", "COD_PRODUCTO")},
            clave_natural=("COD_SALUDIPS",),
            normalizadores={"COD_SALUDIPS": nz.codigo_producto},
        ),
        Tabla(
            clave="portafolio",
            titulo="Portafolio",
            archivo="PORTAFOLIO.xlsx",
            necesaria=True,
            para_que="Los precios que ofrece cada proveedor por producto. Sin este archivo no hay a quién comprarle (solo llegarían los precios de las fichas que envíen los proveedores).",
            hoja="PORTAFOLIO",
            sql="x_portafolio",
            columnas=("COD_EMPRESA", "COD_PRODUCTO", "DESCRIPCION", "VALOR", "PRESENTACION"),
            numericas=frozenset({"VALOR"}),
            obligatorias=("COD_EMPRESA", "COD_PRODUCTO"),
            exigidas=("COD_EMPRESA", "COD_PRODUCTO", "VALOR"),
            alias={
                "COD_EMPRESA": ("COD_EMPRESA", "CODIGO_EMPRESA"),
                "COD_PRODUCTO": ("COD_PRODUCTO", "CODIGO"),
                "VALOR": ("VALOR", "PRECIO"),
            },
            clave_natural=("COD_EMPRESA", "COD_PRODUCTO"),
            normalizadores={"COD_EMPRESA": nz.codigo_empresa, "COD_PRODUCTO": nz.codigo_producto},
            extras=(("NOMBRE_EMPRESA", "NOMBRE DE LA EMPRESA", "COD_EMPRESA"),),
        ),
    )
}


def obtener(clave: str) -> Tabla:
    """La tabla con esa clave, o TablaError 404 si no existe."""
    if clave not in TABLAS:
        raise TablaError(f"No existe la tabla «{clave}». Las tablas son: {', '.join(TABLAS)}.", 404)
    return TABLAS[clave]


def esquema_sql() -> str:
    """Las instrucciones CREATE TABLE de las 5 tablas (las ejecuta database.iniciar_db).

    Se generan desde TABLAS para que el nombre de cada columna sea SIEMPRE el del encabezado del Excel."""
    partes = []
    for t in TABLAS.values():
        columnas = ", ".join(f'"{c}" TEXT' for c in t.columnas)
        partes.append(f"CREATE TABLE IF NOT EXISTS {t.sql} (id INTEGER PRIMARY KEY AUTOINCREMENT, {columnas});")
        for i, c in enumerate(t.clave_natural):  # índices: buscar por código es lo más frecuente
            partes.append(f'CREATE INDEX IF NOT EXISTS idx_{t.sql}_{i} ON {t.sql}("{c}");')
    return "\n".join(partes)


# --------------------------------------------------------------------------------------------- Validación
def como_texto(v) -> str | None:
    """Un valor cualquiera (texto, número, vacío) como texto recortado, o None si está vacío."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)  # 100.0 → "100"
    s = str(v).strip()
    return s or None


def limpiar(t: Tabla, valores: dict) -> dict[str, str | None]:
    """Valida lo que escribió el usuario para UNA fila y lo deja listo para guardar.

    - Solo se aceptan columnas de la tabla (una desconocida es un error, no se ignora en silencio).
    - Se quitan los espacios de los extremos; lo vacío queda como NULL.
    - Las columnas numéricas deben ser números («100», «12,5», «1.234,50»).
    - Las obligatorias no pueden quedar vacías.
    Lanza TablaError (422) con un mensaje que dice exactamente qué corregir."""
    if not isinstance(valores, dict):
        raise TablaError("Los datos de la fila deben venir como {columna: valor}.")
    desconocidas = [c for c in valores if c not in t.columnas]
    if desconocidas:
        raise TablaError(f"La tabla {t.titulo} no tiene la columna {desconocidas[0]!r}. Columnas: {list(t.columnas)}.")
    salida: dict[str, str | None] = {}
    for c in t.columnas:
        v = como_texto(valores.get(c))
        if v is not None and len(v) > MAX_LARGO_CELDA:
            raise TablaError(f"«{c}» es demasiado largo (máximo {MAX_LARGO_CELDA} caracteres).")
        if v is not None and c in t.numericas and nz.numero(v) is None:
            raise TablaError(f"«{c}» debe ser un número (por ejemplo 100 o 12,5). Escribiste: {v!r}.")
        if v is not None and c in t.validadores:
            try:
                v = t.validadores[c](v)
            except ValueError as e:
                raise TablaError(f"«{c}»: {e}") from None
        salida[c] = v
    for c in t.obligatorias:
        if salida[c] is None:
            raise TablaError(f"«{c}» es obligatorio.")
    return salida


def clave_de(t: Tabla, valores: dict) -> tuple | None:
    """La «llave» normalizada de una fila (por ejemplo ('5', 'A1') para el portafolio), o None si le falta un código.
    Dos filas con la misma llave son «la misma» para «agregar y actualizar»."""
    partes = []
    for c in t.clave_natural:
        v = t.normalizadores[c](valores.get(c))
        if v is None:
            return None
        partes.append(v)
    return tuple(partes)


# --------------------------------------------------------------------------------------------- Repetidos
def _texto_unico(v) -> str | None:
    """Un texto para decidir si dos son «el mismo» (los nombres de `Tabla.unicas`): la regla de todo el sistema, sin tildes, sin mayúsculas y
    sin espacios ni signos («ALFA S.A.S.» = «alfa sas»). None si no tiene letras ni números."""
    return nz.clave_nombre(v) or None


def llave_unica(t: Tabla, valores: dict) -> tuple | None:
    """La llave de una fila para detectar repetidos: sus códigos normalizados (05 = 5, 5929.0 = 5929) y sin distinguir
    mayúsculas. None si le falta algún código."""
    k = clave_de(t, valores)
    return tuple(p.casefold() for p in k) if k is not None else None


def buscar_repetido(
    con: sqlite3.Connection, t: Tabla, valores: dict, *, antes: dict | None = None, excepto_id: int | None = None
) -> tuple[dict, str] | None:
    """Busca otra fila que quedaría «repetida» con `valores`. Devuelve (esa fila, motivo) o None. El motivo es «llave»
    (mismo código, o misma empresa y producto) o el nombre de una columna de `t.unicas`.

    Con `antes` (la fila como estaba) solo se revisa lo que CAMBIÓ: así se puede seguir editando el valor de una fila que
    ya venía repetida del Excel, siempre que no se toque su código. `excepto_id` es la fila que se está editando."""
    llave = llave_unica(t, valores)
    if llave is not None and antes is not None and llave == llave_unica(t, antes):
        llave = None  # el código no cambió
    unicas = {c: _texto_unico(valores.get(c)) for c in t.unicas}
    unicas = {c: v for c, v in unicas.items() if v is not None and (antes is None or v != _texto_unico(antes.get(c)))}
    if llave is None and not unicas:
        return None
    for f in instantanea(con, t):
        if f["id"] == excepto_id:
            continue
        if llave is not None and llave_unica(t, f["valores"]) == llave:
            return f, "llave"
        for c, v in unicas.items():
            if _texto_unico(f["valores"].get(c)) == v:
                return f, c
    return None


def _exigir_sin_choque_con_empresas_propias(con: sqlite3.Connection, valores: dict, antes: dict | None) -> None:
    """Una empresa creada en la aplicación («Agregar oferta», «Proveedores», «Cargar datos») NO está en la tabla EMPRESAS de Administración: allí no
    se vería. Por eso, al agregar o editar una empresa en Administración también se revisa contra TODOS los proveedores que conoce el tablero:
    el nombre (con la regla de todo el sistema) no puede ser el de otro proveedor, y el código no puede ser el de uno creado en la aplicación."""
    cod = nz.codigo_empresa(valores.get("CODIGO_EMPRESA"))
    nombre = nz.texto(valores.get("NOMBRE"))
    clave = nz.clave_nombre(nombre)
    antes_cod = nz.codigo_empresa(antes.get("CODIGO_EMPRESA")) if antes else None
    for e in con.execute("SELECT cod, nombre, origen FROM empresas"):
        if clave and e["cod"] != cod and nz.clave_nombre(e["nombre"]) == clave:
            raise TablaError(
                f"Ya existe el proveedor «{e['nombre']}» (código {e['cod']}): el nombre «{nombre}» sería el mismo.", 409
            )
        if e["cod"] == cod and cod != antes_cod and e["origen"] in ("manual", "subido"):
            raise TablaError(f"El código {cod} ya lo usa el proveedor «{e['nombre']}», creado en la aplicación.", 409)


def exigir_empresas_importables(con: sqlite3.Connection, t: Tabla, filas: list[dict], modo: str) -> None:
    """Antes de cargar un Excel de EMPRESAS (Administración → Importar, o «Actualizar Excel»): el archivo no puede traer la misma empresa dos veces
    ni dejar un nombre que ya tiene otra (ni siquiera una creada en la aplicación). Si algo falla NO se carga nada. (Las demás tablas aceptan
    repetidos a propósito: los Excel de la empresa suelen traerlos en el stock y el portafolio, y salen en los avisos; en las empresas no hay ninguno.)"""
    en_archivo = [(nz.codigo_empresa(f.get("CODIGO_EMPRESA")), nz.texto(f.get("NOMBRE"))) for f in filas]
    en_archivo = [(c, n) for c, n in en_archivo if c and n and nz.clave_nombre(n)]
    problemas: list[str] = []
    por_cod: dict[str, int] = {}
    por_nombre: dict[str, list[tuple[str, str]]] = {}
    for c, n in en_archivo:
        por_cod[c] = por_cod.get(c, 0) + 1
        por_nombre.setdefault(nz.clave_nombre(n), []).append((c, n))
    problemas += [f"El código {c} aparece dos veces en el archivo." for c, veces in por_cod.items() if veces > 1]
    for lista in por_nombre.values():
        if len({c for c, _ in lista}) > 1:
            problemas.append(
                "Es el mismo proveedor y aparece dos veces en el archivo: "
                + " y ".join(f"«{n}» (código {c})" for c, n in lista)
                + "."
            )
    # el archivo contra lo que quedaría en la tabla (en «agregar», lo que ya había con lo del archivo encima)
    final: dict[str, str] = {}
    if modo != "reemplazar":
        for f in instantanea(con, t):
            c, n = nz.codigo_empresa(f["valores"].get("CODIGO_EMPRESA")), nz.texto(f["valores"].get("NOMBRE"))
            if c and n:
                final[c] = n
    final.update({c: n for c, n in en_archivo})
    del_archivo = {c for c, _ in en_archivo}
    grupos: dict[str, list[str]] = {}
    for c, n in final.items():
        grupos.setdefault(nz.clave_nombre(n), []).append(c)
    for clave, codigos in grupos.items():
        if (
            len(codigos) > 1
            and del_archivo & set(codigos)
            and not any(
                clave == nz.clave_nombre(n) and len({x for x, _ in por_nombre.get(clave, [])}) > 1
                for _, n in en_archivo[:0]
            )
        ):
            if (
                len({c for c, _ in por_nombre.get(clave, [])}) <= 1
            ):  # (si ya se dijo arriba que se repite en el archivo, no se repite el aviso)
                problemas.append(
                    "El nombre «"
                    + final[codigos[0]]
                    + "» quedaría repetido en los proveedores "
                    + " y ".join(f"{c} («{final[c]}»)" for c in codigos)
                    + "."
                )
    # y contra los proveedores creados en la aplicación (no están en la tabla EMPRESAS)
    for e in con.execute("SELECT cod, nombre FROM empresas WHERE origen IN ('manual', 'subido')"):
        for c, n in en_archivo:
            if c != e["cod"] and nz.clave_nombre(n) == nz.clave_nombre(e["nombre"]):
                problemas.append(
                    f"El nombre «{n}» (código {c}) ya lo tiene el proveedor «{e['nombre']}» (código {e['cod']}), creado en la aplicación: cámbiale el nombre o elimínalo antes de importar."
                )
            elif c == e["cod"] and nz.clave_nombre(n) != nz.clave_nombre(e["nombre"]):
                problemas.append(
                    f"El código {c} ya lo usa el proveedor «{e['nombre']}», creado en la aplicación, y el archivo lo trae como «{n}»."
                )
    if problemas:
        vistos = list(dict.fromkeys(problemas))
        resto = f" Y {len(vistos) - 8} problema(s) más." if len(vistos) > 8 else ""
        raise ImportacionError(
            "El archivo de empresas trae proveedores repetidos o que ya existen; no se cargó nada. "
            + " ".join(vistos[:8])
            + resto
        )


def exigir_sin_repetidos(
    con: sqlite3.Connection, t: Tabla, valores: dict, *, antes: dict | None = None, excepto_id: int | None = None
) -> None:
    """Lanza TablaError 409 si agregar o guardar estos valores dejaría una fila repetida (ver buscar_repetido)."""
    hallado = buscar_repetido(con, t, valores, antes=antes, excepto_id=excepto_id)
    if hallado is None:
        if t.clave == "empresas":
            _exigir_sin_choque_con_empresas_propias(
                con, valores, antes
            )  # lo creado en la aplicación no está en esta tabla: se revisa aparte
        return
    f, motivo = hallado
    v = f["valores"]
    if motivo == "llave":
        partes = " y ".join(f"{c} {v.get(c)}" for c in t.clave_natural)
        valor = f", valor {v['VALOR']}" if t.clave == "portafolio" and v.get("VALOR") else ""
        raise TablaError(
            f"Ya existe en {t.titulo} una fila con {partes} (fila {f['id']}{valor}). Edítala en vez de agregar otra.",
            409,
        )
    raise TablaError(f"Ya existe en {t.titulo} otra fila con {motivo} «{v.get(motivo)}» (fila {f['id']}).", 409)


# --------------------------------------------------------------------------------------------- Lectura
def total(con: sqlite3.Connection, t: Tabla) -> int:
    """Cuántas filas tiene la tabla."""
    return con.execute(f"SELECT COUNT(*) FROM {t.sql}").fetchone()[0]


def _fila(t: Tabla, r: sqlite3.Row) -> dict:
    """Una fila de SQLite como {'id': 7, 'valores': {'COD_PRODUCTO': '0041', ...}}."""
    return {"id": r["id"], "valores": {c: r[c] for c in t.columnas}}


def _nombres_de_empresas(con: sqlite3.Connection) -> dict[str, str]:
    """{código normalizado: nombre} de los proveedores que conoce el tablero (los del Excel, los inferidos y los propios)."""
    return {r["cod"]: r["nombre"] for r in con.execute("SELECT cod, nombre FROM empresas")}


def leer_fila(con: sqlite3.Connection, t: Tabla, fila_id: int) -> dict | None:
    """Una fila por su número interno, o None si no existe."""
    r = con.execute(f"SELECT * FROM {t.sql} WHERE id = ?", (fila_id,)).fetchone()
    return _fila(t, r) if r else None


def listar(
    con: sqlite3.Connection,
    t: Tabla,
    *,
    q: str = "",
    orden: str | None = None,
    sentido: str = "asc",
    pagina: int = 1,
    tam: int = 50,
    ids: list[int] | None = None,
    solo_ids: bool = False,
) -> dict:
    """Una página de filas, con búsqueda, orden y filtro por números de fila. Todo lo hace SQLite (la tabla del
    portafolio tiene más de 7.000 filas: no se manda entera a la pantalla).

    q       palabras a buscar: cada palabra debe aparecer en alguna columna (sin importar mayúsculas ni tildes)
    orden   encabezado por el que ordenar (debe ser una columna de la tabla; si no, se ordena por número de fila)
    ids     si se pasa, solo esas filas (así se muestran las filas de un aviso)
    solo_ids  devuelve {'total', 'ids'} con el número de TODAS las filas que cumplen (hasta 20.000), sin las filas"""
    con.create_function("sinacentos", 1, lambda s: nz.sin_acentos(s).lower() if s else "", deterministic=True)
    nombres = _nombres_de_empresas(con) if any(e[0] == "NOMBRE_EMPRESA" for e in t.extras) else {}
    if nombres is not None and t.extras:  # el nombre de la empresa del portafolio también se puede buscar y ordenar
        con.create_function("nombreemp", 1, lambda c: nombres.get(nz.codigo_empresa(c) or "", ""), deterministic=True)
    donde, params = [], []
    for palabra in nz.sin_acentos(q or "").lower().split():
        opciones = [f'sinacentos("{c}") LIKE ?' for c in t.columnas]
        if t.extras:
            opciones.append('sinacentos(nombreemp("COD_EMPRESA")) LIKE ?')
        donde.append("(" + " OR ".join(opciones) + ")")
        params += [f"%{palabra}%"] * len(opciones)
    if ids is not None:
        donde.append("id IN (SELECT value FROM json_each(?))")
        params.append(json.dumps(list(ids)))
    clausula = (" WHERE " + " AND ".join(donde)) if donde else ""

    if orden in t.columnas:  # solo encabezados de la tabla: así nada que escriba el usuario llega al SQL
        expr = f'CAST("{orden}" AS REAL)' if orden in t.numericas else f'"{orden}" COLLATE NOCASE'
        # Las celdas vacías van siempre al final; a igual valor, se respeta el orden del Excel (id).
        orden_sql = f"({expr} IS NULL), {expr} {'DESC' if sentido == 'desc' else 'ASC'}, id"
    elif t.extras and orden == "NOMBRE_EMPRESA":
        expr = 'nombreemp("COD_EMPRESA") COLLATE NOCASE'
        orden_sql = f"({expr} = ''), {expr} {'DESC' if sentido == 'desc' else 'ASC'}, id"
    else:
        orden_sql = "id"

    n = con.execute(f"SELECT COUNT(*) FROM {t.sql}{clausula}", params).fetchone()[0]
    if solo_ids:  # para «seleccionar todas las filas del filtro» (por ejemplo, para eliminarlas de una vez)
        todas = con.execute(f"SELECT id FROM {t.sql}{clausula} ORDER BY id LIMIT 20000", params).fetchall()  # noqa: S608
        return {"total": n, "ids": [r["id"] for r in todas]}
    tam = max(1, min(int(tam), 200))
    paginas = max(1, math.ceil(n / tam))
    pagina = max(1, min(int(pagina), paginas))
    filas = con.execute(
        f"SELECT * FROM {t.sql}{clausula} ORDER BY {orden_sql} LIMIT ? OFFSET ?", [*params, tam, (pagina - 1) * tam]
    ).fetchall()
    salida = [_fila(t, r) for r in filas]
    if t.extras:
        for f in salida:
            f["extras"] = {"NOMBRE_EMPRESA": nombres.get(nz.codigo_empresa(f["valores"].get("COD_EMPRESA")) or "")}
    return {"total": n, "pagina": pagina, "paginas": paginas, "tam": tam, "filas": salida}


# --------------------------------------------------------------------------------------------- Escritura
def insertar_crudo(con: sqlite3.Connection, t: Tabla, valores: dict, fila_id: int | None = None) -> int:
    """Inserta una fila SIN validar (lo usan la importación y «deshacer», que deben poder guardar cualquier cosa que
    hubiera antes). Si se da `fila_id`, la fila conserva ese número. Devuelve el número de la fila."""
    columnas = ["id", *t.columnas] if fila_id is not None else list(t.columnas)
    datos = ([fila_id] if fila_id is not None else []) + [valores.get(c) for c in t.columnas]
    nombres = ", ".join(f'"{c}"' for c in columnas)
    marcas = ", ".join("?" * len(columnas))
    cur = con.execute(f"INSERT INTO {t.sql} ({nombres}) VALUES ({marcas})", datos)  # noqa: S608
    return fila_id if fila_id is not None else cur.lastrowid


def actualizar_crudo(con: sqlite3.Connection, t: Tabla, fila_id: int, valores: dict) -> None:
    """Cambia TODAS las columnas de una fila SIN validar (para importar y «deshacer»)."""
    asignar = ", ".join(f'"{c}" = ?' for c in t.columnas)
    con.execute(f"UPDATE {t.sql} SET {asignar} WHERE id = ?", [valores.get(c) for c in t.columnas] + [fila_id])


def insertar(con: sqlite3.Connection, t: Tabla, valores: dict) -> int:
    """Agrega una fila escrita por el usuario (validada y sin repetir códigos). Devuelve su número de fila."""
    limpio = limpiar(t, valores)
    exigir_sin_repetidos(con, t, limpio)
    return insertar_crudo(con, t, limpio)


def actualizar(con: sqlite3.Connection, t: Tabla, fila_id: int, valores: dict) -> None:
    """Guarda los valores nuevos de una fila (validados). TablaError 404 si la fila no existe."""
    antes = leer_fila(con, t, fila_id)
    if antes is None:
        raise TablaError(f"La fila {fila_id} ya no existe en {t.titulo}.", 404)
    limpio = limpiar(t, valores)
    exigir_sin_repetidos(con, t, limpio, antes=antes["valores"], excepto_id=fila_id)
    actualizar_crudo(con, t, fila_id, limpio)


def borrar(con: sqlite3.Connection, t: Tabla, ids: list[int]) -> int:
    """Elimina esas filas y devuelve cuántas se eliminaron."""
    cur = con.execute(f"DELETE FROM {t.sql} WHERE id IN (SELECT value FROM json_each(?))", (json.dumps(list(ids)),))
    return cur.rowcount


def instantanea(con: sqlite3.Connection, t: Tabla) -> list[dict]:
    """Copia de TODA la tabla ([{id, valores}, ...]) para poder restaurarla (historial de importaciones)."""
    return [_fila(t, r) for r in con.execute(f"SELECT * FROM {t.sql} ORDER BY id")]


def restaurar(con: sqlite3.Connection, t: Tabla, filas: list[dict]) -> None:
    """Deja la tabla EXACTAMENTE como estaba en una instantánea (con los mismos números de fila)."""
    con.execute(f"DELETE FROM {t.sql}")
    for f in filas:
        insertar_crudo(con, t, f["valores"], f["id"])


# --------------------------------------------------------------------------------------------- Excel → tabla
def _leer_csv(contenido: bytes) -> pd.DataFrame:
    """Lee un CSV probando UTF-8 y, si falla, Latin-1; detecta solo si separa con coma o punto y coma."""
    try:
        return pd.read_csv(io.BytesIO(contenido), dtype=str, sep=None, engine="python", encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(contenido), dtype=str, sep=None, engine="python", encoding="latin-1")


def leer_excel(t: Tabla, origen: Path | bytes, nombre: str = "") -> tuple[list[dict], set[str]]:
    """Lee un Excel (o CSV) y devuelve (filas, columnas_que_trae).

    - `origen` es la ruta de un archivo de la carpeta data/excel o los bytes de un archivo subido.
    - Los encabezados se reconocen aunque cambien tildes, mayúsculas o espacios («stock max», «STOCK_MAX»...)
      y quedan con el nombre EXACTO de la tabla. Todo se lee como texto (así «0041» sigue siendo «0041»).
    - Las filas totalmente vacías se descartan.
    Lanza ImportacionError si falta el archivo o una columna indispensable."""
    if isinstance(origen, Path):
        if not origen.exists():
            raise ImportacionError(f"Falta el archivo {t.archivo} en {origen.parent}")
        nombre, fuente = origen.name, origen
    else:
        if not origen:
            raise ImportacionError("El archivo está vacío.")
        if len(origen) > MAX_BYTES:
            raise ImportacionError(
                f"El archivo pesa {len(origen) / 1e6:.1f} MB y el máximo es {MAX_BYTES // 1048576} MB."
            )
        if not str(nombre).lower().endswith(".csv") and (problema := excel_seguro.revisar_xlsx(origen)):
            raise ImportacionError(problema)  # una «bomba de compresión»: pesa poco y abierta ocupa cientos de MB
        fuente = io.BytesIO(origen)
    try:
        if str(nombre).lower().endswith(".csv"):
            df = _leer_csv(fuente.read() if isinstance(fuente, io.BytesIO) else Path(fuente).read_bytes())
        else:
            df = nz.leer_excel(fuente)
    except Exception as e:  # archivo dañado, no es un Excel real...
        raise ImportacionError(
            f"No se pudo leer {nombre or t.archivo} ({type(e).__name__}). ¿Es un Excel válido?"
        ) from None

    por_norm = {nz.nombre_columna(c): c for c in df.columns}
    fuente_col: dict[str, str] = {}
    for c in t.columnas:
        nombres = (nz.nombre_columna(c), *t.alias.get(c, ()))
        real = next((por_norm[a] for a in nombres if a in por_norm), None)
        if real is not None:
            fuente_col[c] = real
    faltan = [c for c in t.exigidas if c not in fuente_col]
    if faltan:
        raise ImportacionError(f"{t.archivo}: faltan las columnas {faltan}. Encontradas: {list(df.columns)}")
    filas = []
    for fila in df.to_dict("records"):
        valores = {
            c: (None if c not in fuente_col or pd.isna(fila[fuente_col[c]]) else str(fila[fuente_col[c]]))
            for c in t.columnas
        }
        if any(v is not None and v.strip() for v in valores.values()):
            filas.append(valores)
    return filas, set(fuente_col)


def _mas_barata(nueva: dict, previa: dict) -> dict:
    """De dos filas del portafolio con el MISMO proveedor y producto, la que se queda: la de menor precio válido (mayor que 0).
    Una fila sin precio válido nunca tapa a una que sí lo tiene; si empatan, se queda la primera."""

    def precio(f: dict) -> float | None:
        n = nz.numero(f.get("VALOR"))
        return n if n is not None and n > 0 else None

    pn, pp = precio(nueva), precio(previa)
    if pn is None:
        return previa
    if pp is None:
        return nueva
    return nueva if pn < pp else previa


def aplicar_excel(
    con: sqlite3.Connection, t: Tabla, filas: list[dict], presentes: set[str], modo: str
) -> dict[str, int]:
    """Carga las filas leídas de un Excel en la tabla y devuelve los conteos.

    modo «reemplazar»  borra todo lo que hay en la tabla y deja SOLO lo del Excel.
    modo «agregar»     no borra nada: las filas que ya existen (misma llave: código, o proveedor+producto) se
                       ACTUALIZAN con lo que traiga el Excel (solo las columnas que el archivo trae) y las que no
                       existen se AGREGAN. Si el Excel repite una llave, gana la última fila, SALVO en el portafolio: si un proveedor repite el
                       mismo producto, se queda el de MENOR precio válido (así un precio repetido más caro nunca tapa al barato).
    """
    if t.clave == "empresas":
        exigir_empresas_importables(con, t, filas, modo)  # sin la misma empresa dos veces ni nombres que ya tiene otra
    if modo == "reemplazar":
        previas: dict[tuple, dict] = {}
        if t.conservar:  # lo que no viene en el Excel (teléfono y correo de las empresas) no se pierde al reemplazar
            for f in instantanea(con, t):
                k = clave_de(t, f["valores"])
                if k is not None:
                    previas.setdefault(k, f["valores"])
        con.execute(f"DELETE FROM {t.sql}")
        for v in filas:
            viejo = previas.get(clave_de(t, v)) if previas else None
            if viejo:
                for c in t.conservar:
                    if v.get(c) is None:
                        v[c] = viejo.get(c)
            insertar_crudo(con, t, v)
        return {"filas_archivo": len(filas), "nuevos": len(filas), "actualizados": 0, "sin_cambios": 0, "ignoradas": 0}
    if modo != "agregar":
        raise TablaError("El modo debe ser «reemplazar» o «agregar».")

    existentes: dict[tuple, dict] = {}
    for f in instantanea(con, t):
        k = clave_de(t, f["valores"])
        if k is not None:
            existentes.setdefault(k, f)  # si la tabla ya trae el código repetido, se actualiza la PRIMERA fila
    pendientes: dict[tuple, dict] = {}
    ignoradas = repetidas = 0
    for v in filas:
        k = clave_de(t, v)
        if k is None:
            ignoradas += 1
            continue
        if k in pendientes:
            repetidas += 1
            if t.clave == "portafolio":
                v = _mas_barata(v, pendientes[k])
        pendientes[k] = v  # la última gana (en el portafolio, la más barata de las repetidas)
    nuevos = actualizados = sin_cambios = 0
    for k, v in pendientes.items():
        if k in existentes:
            f = existentes[k]
            cambio = {c: v[c] for c in presentes if v[c] != f["valores"].get(c)}
            if cambio:
                actualizar_crudo(con, t, f["id"], {**f["valores"], **cambio})
                actualizados += 1
            else:
                sin_cambios += 1
        else:
            insertar_crudo(con, t, v)
            nuevos += 1
    return {
        "filas_archivo": len(filas),
        "nuevos": nuevos,
        "actualizados": actualizados,
        "sin_cambios": sin_cambios,
        "ignoradas": ignoradas,
        "repetidas_en_archivo": repetidas,
    }


# --------------------------------------------------------------------------------------------- tabla → Excel
def exportar_xlsx(con: sqlite3.Connection, t: Tabla) -> bytes:
    """La tabla como Excel: mismos encabezados y mismo nombre de hoja que el original. Las columnas numéricas
    salen como números de verdad; los códigos quedan como texto (así «0041» conserva su cero)."""
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = t.hoja
    hoja.append(list(t.columnas))
    for f in instantanea(con, t):
        fila = []
        for c in t.columnas:
            v = f["valores"][c]
            if v is not None and c in t.numericas and (n := nz.numero(v)) is not None:
                v = int(n) if n.is_integer() else n
            fila.append(v)
        hoja.append(fila)
    for i, c in enumerate(t.columnas, start=1):  # ancho de columna cómodo
        hoja.column_dimensions[hoja.cell(row=1, column=i).column_letter].width = (
            44 if c in ("DESCRIPCION", "NOMBRE") else 18
        )
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# --------------------------------------------------------------------------------------------- para el recálculo
def para_calculo(con: sqlite3.Connection, t: Tabla) -> pd.DataFrame:
    """La tabla como DataFrame para importador.recalcular(): columna ID (número de fila) y las columnas con el
    nombre normalizado (StockMax → STOCKMAX)."""
    columnas = ", ".join(f'"{c}"' for c in t.columnas)
    df = pd.read_sql_query(f'SELECT id AS "ID", {columnas} FROM {t.sql} ORDER BY id', con)  # noqa: S608
    return df.rename(columns={c: nz.nombre_columna(c) for c in t.columnas})


# --------------------------------------------------------------------------------------------- impacto de borrar
def impacto_empresa(con: sqlite3.Connection, cod: str | None, nombre: str | None = None) -> str:
    """El aviso al eliminar un proveedor: se borra con todos los insumos cotizados y el tablero busca la siguiente oferta más baja."""
    quien = f"«{nombre}» (código {cod})" if nombre else f"el proveedor {cod}"
    n_of = con.execute("SELECT COUNT(*) FROM ofertas WHERE cod_empresa = ?", (cod,)).fetchone()[0]
    if not n_of:
        return f"Se elimina {quien}. No tiene ofertas en el tablero."
    productos = [r[0] for r in con.execute("SELECT DISTINCT cod_producto FROM ofertas WHERE cod_empresa = ?", (cod,))]
    solo_el = sum(
        1 for p in productos
        if con.execute("SELECT COUNT(DISTINCT cod_empresa) FROM ofertas WHERE cod_producto = ?", (p,)).fetchone()[0] == 1
    )
    texto = (
        f"Se elimina {quien} con todos los insumos cotizados: {'su oferta' if n_of == 1 else f'sus {n_of} ofertas'} (de Portafolio y las cargadas), los productos donde "
        "se había elegido a mano y sus ofertas de «Adicionales». En cada producto donde estaba, el tablero elegirá la "
        "siguiente oferta más baja de otro proveedor."
    )
    if solo_el:
        texto += f" {solo_el} producto(s) solo tenían oferta de este proveedor: quedarán «sin oferta»."
    return texto



def impacto(con: sqlite3.Connection, t: Tabla, fila_id: int) -> dict:
    """Qué pasaría en el tablero si se elimina esa fila (para avisarlo ANTES de confirmar). Eliminar se permite
    siempre; lo que queda «huérfano» se ve luego en los avisos de datos.
    Devuelve {'mensaje': texto o None}."""
    f = leer_fila(con, t, fila_id)
    if f is None:
        raise TablaError(f"La fila {fila_id} ya no existe en {t.titulo}.", 404)
    v = f["valores"]
    mensajes: list[str] = []

    def ofertas_de(campo: str, valor: str | None) -> int:
        return con.execute(f"SELECT COUNT(*) FROM ofertas WHERE {campo} = ?", (valor,)).fetchone()[0]  # noqa: S608

    if t.clave == "empresas":
        mensajes.append(impacto_empresa(con, nz.codigo_empresa(v["CODIGO_EMPRESA"]), v.get("NOMBRE")))
    elif t.clave in ("stock", "existencias"):
        cod = nz.codigo_producto(v["COD_PRODUCTO"])
        otras = sum(
            1
            for r in con.execute(f"SELECT id, COD_PRODUCTO FROM {t.sql}")  # noqa: S608
            if r["id"] != fila_id and nz.codigo_producto(r["COD_PRODUCTO"]) == cod
        )
        if otras:
            mensajes.append(f"Hay {otras} fila(s) más con el código {cod}: el tablero usará esas.")
        elif t.clave == "stock":
            mensajes.append(f"El producto {cod} dejará de tener stock definido y no se calculará cuánto comprar.")
            n = ofertas_de("cod_producto", cod)
            if n:
                mensajes.append(f"Sus {n} oferta(s) seguirán en Portafolio y saldrá un aviso de datos.")
        else:
            mensajes.append(f"Las existencias de {cod} pasarán a 0: se propondrá comprar el StockMax completo.")
    elif t.clave == "portafolio":
        cod = nz.codigo_producto(v["COD_PRODUCTO"])
        if ofertas_de("cod_producto", cod) <= 1:
            mensajes.append(f"Es la única oferta del producto {cod}: quedará «sin oferta» y saldrá un aviso.")
    elif t.clave == "ficha":
        mensajes.append("Solo se pierde la descripción de la ficha; el producto sigue si está en Stock o Portafolio.")
    return {"mensaje": " ".join(mensajes) or None}
