"""
ADICIONALES: CÓDIGO Y DESCRIPCIÓN → PROVEEDOR 1, 2 Y 3 CON SU MENOR VALOR
=========================================================================
El usuario sube (Excel o CSV) o escribe una lista de productos con su CÓDIGO y DESCRIPCIÓN. Para cada uno se muestran los tres
proveedores que ofrecen el MENOR valor, en orden: Proveedor 1 (el más barato), Proveedor 2 y Proveedor 3.

Cómo se busca cada producto en las ofertas:
  1. por su CÓDIGO (sin distinguir mayúsculas; «5929», 5929.0 y « 5929 » son el mismo);
  2. si ese código no tiene ofertas, por su DESCRIPCIÓN exacta (sin tildes, mayúsculas ni espacios de más).
Cada proveedor cuenta una sola vez, con su oferta más baja (la misma regla del tablero: ranking.construir_ranking).

ADICIONALES ES LIBRE: además de las ofertas del tablero, busca en las OFERTAS LIBRES (tabla ofertas_libres): precios que un proveedor
ofreció pero que el tablero no toma por sus reglas (producto que no está en el catálogo al «Cargar datos», o que hoy no se necesita en
la ficha del proveedor externo). Esas ofertas se muestran aquí, marcadas «fuera del tablero», y nunca entran al tablero ni a la OC.

Es una lista de CONSULTA: no cambia el tablero, las ofertas ni la orden de compra.
"""

import io
import sqlite3
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import excel_seguro, ranking
from . import normalizacion as nz

MAX_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_FILAS = 100_000  # productos por archivo
PUESTOS = 3


class AdicionalesError(Exception):
    def __init__(self, mensaje: str, estado: int = 422):
        super().__init__(mensaje)
        self.mensaje, self.estado = mensaje, estado


# ------------------------------------------------------------------------------------------------ lectura del archivo
def _columna(nombres: list[str], *pistas: str) -> int | None:
    for i, n in enumerate(nombres):
        if any(p in n for p in pistas):
            return i
    return None


def leer_archivo(contenido: bytes, nombre: str) -> list[dict]:
    """Del Excel/CSV saca las filas {cod, descripcion}. Busca las columnas «código» y «descripción» por su encabezado
    (en las primeras 20 filas); si no hay encabezado reconocible, usa la 1.ª columna como código y la 2.ª como descripción."""
    if not contenido:
        raise AdicionalesError("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise AdicionalesError(f"El archivo pesa {len(contenido) / 1e6:.1f} MB y el máximo es {MAX_BYTES // 1048576} MB.", 413)
    ext = Path(nombre or "").suffix.lower()
    try:
        if ext in (".xlsx", ".xlsm"):
            if problema := excel_seguro.revisar_xlsx(contenido):
                raise AdicionalesError(problema, 413)
            wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
            filas = [list(f) for f in wb.worksheets[0].iter_rows(values_only=True)]
            wb.close()
        elif ext in (".csv", ".txt"):
            try:
                df = pd.read_csv(io.BytesIO(contenido), dtype=str, sep=None, engine="python", encoding="utf-8-sig", header=None)
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(contenido), dtype=str, sep=None, engine="python", encoding="latin-1", header=None)
            filas = df.where(df.notna(), None).values.tolist()
        else:
            raise AdicionalesError("Suba un archivo de Excel (.xlsx) o CSV con las columnas CÓDIGO y DESCRIPCIÓN.")
    except AdicionalesError:
        raise
    except Exception:
        raise AdicionalesError("No se pudo leer el archivo. Revise que sea un Excel (.xlsx) o CSV válido.") from None

    i_cod, i_desc, inicio = 0, 1, 0
    for n, fila in enumerate(filas[:20]):
        nombres = [nz.nombre_columna(c) if c is not None else "" for c in fila]
        c = _columna(nombres, "COD", "REFERENCIA")
        if c is not None:
            d = _columna(nombres, "DESCRIP", "PRODUCTO", "NOMBRE", "DETALLE")
            i_cod, i_desc, inicio = c, (d if d is not None and d != c else c + 1), n + 1
            break
    salida = []
    for fila in filas[inicio:]:
        cod = nz.codigo_producto(nz.celda_a_texto(fila[i_cod]) if i_cod < len(fila) else None)
        desc = nz.texto(fila[i_desc]) if i_desc < len(fila) else None
        if cod:
            salida.append({"cod": cod, "descripcion": desc})
    if not salida:
        raise AdicionalesError("El archivo no trae productos: se necesitan las columnas CÓDIGO y DESCRIPCIÓN.")
    if len(salida) > MAX_FILAS:
        raise AdicionalesError(f"El archivo tiene {len(salida):,} productos y el máximo es {MAX_FILAS:,}.".replace(",", "."))
    return salida


# ------------------------------------------------------------------------------------------------ la lista
def agregar(con: sqlite3.Connection, filas: list[dict], usuario: str | None) -> dict:
    """Agrega las filas a la lista. Si un código ya estaba, solo actualiza su descripción (no se repite)."""
    existentes = {nz.clave_codigo(r["cod"]): r["id"] for r in con.execute("SELECT id, cod FROM adicionales")}
    nuevos = actualizados = 0
    for f in filas:
        cod = nz.codigo_producto(f.get("cod"))
        if not cod:
            continue
        desc = nz.texto(f.get("descripcion"))
        clave = nz.clave_codigo(cod)
        if clave in existentes:
            # si vuelve a subirse un producto inhabilitado, se habilita otra vez
            con.execute("UPDATE adicionales SET descripcion = COALESCE(?, descripcion), activo = 1 WHERE id = ?", (desc, existentes[clave]))
            actualizados += 1
        else:
            cur = con.execute("INSERT INTO adicionales (cod, descripcion, usuario) VALUES (?, ?, ?)", (cod, desc, usuario))
            existentes[clave] = cur.lastrowid
            nuevos += 1
    con.commit()
    if not (nuevos or actualizados):
        raise AdicionalesError("Escriba al menos un código de producto.")
    return {"nuevos": nuevos, "actualizados": actualizados}


def guardar_libres(con: sqlite3.Connection, filas: list[dict], origen: str, archivo: str | None, usuario: str | None) -> int:
    """Guarda ofertas que el tablero no tomó: [{cod, cod_empresa, valor, presentacion?, descripcion?}]. La más reciente de cada
    (producto, proveedor) reemplaza a la anterior. No hace commit (lo hace quien llama). Devuelve cuántas guardó."""
    n = 0
    for f in filas:
        cod = nz.codigo_producto(f.get("cod"))
        emp = nz.codigo_empresa(f.get("cod_empresa"))
        valor = f.get("valor")
        if not cod or not emp or valor is None or valor <= 0:
            continue
        con.execute(
            "INSERT INTO ofertas_libres (clave, cod_producto, cod_empresa, valor, presentacion, descripcion, origen, archivo, usuario, fecha)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))"
            " ON CONFLICT(clave, cod_empresa) DO UPDATE SET cod_producto = excluded.cod_producto, valor = excluded.valor,"
            " presentacion = excluded.presentacion, descripcion = COALESCE(excluded.descripcion, ofertas_libres.descripcion),"
            " origen = excluded.origen, archivo = excluded.archivo, usuario = excluded.usuario, fecha = excluded.fecha",
            (nz.clave_codigo(cod), cod, emp, float(valor), nz.texto(f.get("presentacion")), nz.texto(f.get("descripcion")),
             origen, (archivo or "")[:200] or None, usuario),
        )
        n += 1
    return n


def cambiar_activo(con: sqlite3.Connection, id_: int, activo: bool) -> None:
    """Inhabilitar (queda en la lista, en rojo, y no cuenta en el resumen ni en el Excel) o volver a habilitar."""
    if con.execute("UPDATE adicionales SET activo = ? WHERE id = ?", (int(activo), id_)).rowcount == 0:
        raise AdicionalesError("Ese producto ya no está en la lista.", 404)
    con.commit()


def eliminar(con: sqlite3.Connection, id_: int) -> None:
    if con.execute("DELETE FROM adicionales WHERE id = ?", (id_,)).rowcount == 0:
        raise AdicionalesError("Ese producto ya no está en la lista.", 404)
    con.commit()


def vaciar(con: sqlite3.Connection) -> int:
    n = con.execute("DELETE FROM adicionales").rowcount
    con.commit()
    return n


def listar(con: sqlite3.Connection) -> dict:
    """Cada producto de la lista con sus 3 proveedores de menor valor (Proveedor 1, 2 y 3)."""
    empresas = {r["cod"]: r["nombre"] for r in con.execute("SELECT cod, nombre FROM empresas")}
    ofertas: dict[str, list] = {}
    for o in con.execute("SELECT id, cod_producto, cod_empresa, valor, presentacion, disponible FROM ofertas"):
        ofertas.setdefault(nz.clave_codigo(o["cod_producto"]), []).append({**dict(o), "libre": False})
    # Ofertas que el tablero no tomó (Adicionales es libre): compiten aquí con las demás, cada proveedor con su menor valor.
    for i, o in enumerate(con.execute("SELECT clave, cod_producto, cod_empresa, valor, presentacion, origen, fecha FROM ofertas_libres")):
        ofertas.setdefault(o["clave"], []).append({"id": -(i + 1), "cod_producto": o["cod_producto"], "cod_empresa": o["cod_empresa"],
                                                   "valor": o["valor"], "presentacion": o["presentacion"], "disponible": None,
                                                   "libre": True, "origen": o["origen"], "fecha": o["fecha"]})
    por_descripcion: dict[str, str] = {}
    for p in con.execute("SELECT cod, descripcion FROM productos"):
        por_descripcion.setdefault(nz.clave_busqueda(p["descripcion"]), p["cod"])
    for p in con.execute("SELECT cod_producto, descripcion FROM ofertas_libres WHERE descripcion IS NOT NULL"):
        por_descripcion.setdefault(nz.clave_busqueda(p["descripcion"]), p["cod_producto"])

    items, con_oferta, activos = [], 0, 0
    for r in con.execute("SELECT id, cod, descripcion, usuario, fecha, activo FROM adicionales ORDER BY activo DESC, id"):
        lista = ofertas.get(nz.clave_codigo(r["cod"]), [])
        por = "codigo"
        if not lista and r["descripcion"]:
            cod_igual = por_descripcion.get(nz.clave_busqueda(r["descripcion"]))
            if cod_igual:
                lista, por = ofertas.get(nz.clave_codigo(cod_igual), []), f"descripcion:{cod_igual}"
        top = ranking.construir_ranking(lista)[:PUESTOS]
        proveedores = [
            {"puesto": o["puesto"], "cod_empresa": o["cod_empresa"], "nombre": empresas.get(o["cod_empresa"]) or f"Proveedor {o['cod_empresa']}",
             "valor": o["valor"], "presentacion": o.get("presentacion"),
             "fuera_del_tablero": o.get("libre", False), "origen": o.get("origen"), "fecha": o.get("fecha")}
            for o in top
        ]
        activo = bool(r["activo"])
        if activo:
            activos += 1
            con_oferta += bool(proveedores)
        items.append({"id": r["id"], "cod": r["cod"], "descripcion": r["descripcion"], "usuario": r["usuario"], "fecha": r["fecha"],
                      "activo": activo, "encontrado_por": por if proveedores else None, "proveedores": proveedores})
    return {"items": items, "total": activos, "con_oferta": con_oferta, "sin_oferta": activos - con_oferta,
            "inhabilitados": len(items) - activos}


def excel(con: sqlite3.Connection) -> bytes:
    """La lista con Proveedor 1, 2 y 3 y su menor valor, en un Excel."""
    datos = [it for it in listar(con)["items"] if it["activo"]]  # los inhabilitados no van al Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Adicionales"
    cab = ["CÓDIGO", "DESCRIPCIÓN"]
    for i in range(1, PUESTOS + 1):
        cab += [f"PROVEEDOR {i}", f"MENOR VALOR {i}"]
    ws.append(cab)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="015AAA")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for it in datos:
        fila = [it["cod"], it["descripcion"] or ""]
        for i in range(PUESTOS):
            p = it["proveedores"][i] if i < len(it["proveedores"]) else None
            fila += [p["nombre"], p["valor"]] if p else (["Sin oferta", None] if i == 0 else ["", None])
        ws.append(fila)
    for n in range(2, ws.max_row + 1):
        for k in range(PUESTOS):
            ws.cell(n, 4 + 2 * k).number_format = '"$"#,##0.00'
    anchos = [14, 45] + [32, 16] * PUESTOS
    for i, a in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = a
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def plantilla() -> bytes:
    """Excel vacío con las dos columnas, para llenar y subir."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Adicionales"
    ws.append(["CÓDIGO", "DESCRIPCIÓN"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="015AAA")
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 50
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
