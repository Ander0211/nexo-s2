"""
ADMINISTRACIÓN DE LAS TABLAS DE LOS EXCEL
=========================================
Une las tres piezas para que cada acción de la pantalla «Administración» sea UNA operación completa:

    1. escribe en la tabla (tablas.py)
    2. anota el cambio en el historial (historial.py), para poder deshacerlo
    3. recalcula el tablero (importador.recalcular)

Todo pasa en una sola transacción: si algo falla en el camino, no queda nada a medias (se hace rollback).
Las rutas de routers/admin.py solo reciben la petición y llaman a estas funciones.
"""

import json
import sqlite3

from . import catalogo, historial, importador, tablas
from . import normalizacion as nz


def _etiqueta(t: tablas.Tabla, valores: dict) -> str:
    """Cómo nombrar una fila en el historial: sus códigos (por ejemplo «5 / A1» en el portafolio)."""
    return " / ".join(str(valores.get(c) or "—") for c in t.clave_natural)


def _con_recalculo(con: sqlite3.Connection, trabajo):
    """Ejecuta `trabajo()` (escrituras + historial) y luego recalcula. Si algo falla, deshace todo."""
    try:
        resultado = trabajo()
        resultado["recalculo"] = importador.recalcular(con)  # confirma la transacción
    except Exception:
        con.rollback()
        raise
    return resultado


def crear_empresa_con_contacto(
    con: sqlite3.Connection, nombre: str, telefono: str | None, correo: str | None, usuario: str | None = None
) -> dict:
    """Agrega una empresa NUEVA a la tabla EMPRESAS de Administración (con la regla de no repetir y el teléfono y correo obligatorios, como
    cualquier empresa que se agrega allí) y devuelve {'cod', 'nombre'}. Así se agrega un proveedor nuevo al crear el usuario que lo va a usar."""
    cod = catalogo.codigo_proveedor_nuevo(con)
    crear(con, "empresas", {"CODIGO_EMPRESA": cod, "NOMBRE": nombre, "TELEFONO": telefono, "CORREO": correo}, usuario)
    return {"cod": cod, "nombre": nz.texto(nombre)}


def crear(con: sqlite3.Connection, clave: str, valores: dict, usuario: str | None = None) -> dict:
    """Agrega una fila a la tabla. Devuelve {'fila': {...}, 'recalculo': {...}}."""
    t = tablas.obtener(clave)

    def trabajo():
        fila_id = tablas.insertar(con, t, valores)
        fila = tablas.leer_fila(con, t, fila_id)
        historial.registrar(
            con,
            clave,
            "agregar",
            fila_id,
            None,
            fila["valores"],
            f"Agregó a {t.titulo}: {_etiqueta(t, fila['valores'])}",
            usuario,
        )
        return {"fila": fila}

    return _con_recalculo(con, trabajo)


def editar(con: sqlite3.Connection, clave: str, fila_id: int, valores: dict, usuario: str | None = None) -> dict:
    """Guarda los cambios de una fila. Las celdas que NO cambiaron se dejan exactamente como estaban (con sus
    espacios originales): solo se toca lo que el usuario modificó. Si no cambió nada, no se guarda ni se anota."""
    t = tablas.obtener(clave)
    antes = tablas.leer_fila(con, t, fila_id)
    if antes is None:
        raise tablas.TablaError(f"La fila {fila_id} ya no existe en {t.titulo}.", 404)

    def trabajo():
        limpio = tablas.limpiar(t, valores)  # valida todo (obligatorias, números...)
        final = {
            c: antes["valores"][c] if limpio[c] == tablas.como_texto(antes["valores"][c]) else limpio[c]
            for c in t.columnas
        }
        cambiadas = [c for c in t.columnas if final[c] != antes["valores"][c]]
        if not cambiadas:
            return {"fila": antes, "cambio": False}
        tablas.exigir_sin_repetidos(con, t, final, antes=antes["valores"], excepto_id=fila_id)  # sin repetir códigos
        tablas.actualizar_crudo(con, t, fila_id, final)
        fila = tablas.leer_fila(con, t, fila_id)
        detalle = ", ".join(f"{c}: {antes['valores'][c] or '—'} → {final[c] or '—'}" for c in cambiadas[:3])
        historial.registrar(
            con,
            clave,
            "editar",
            fila_id,
            antes["valores"],
            fila["valores"],
            f"Editó {t.titulo} {_etiqueta(t, antes['valores'])} ({detalle})",
            usuario,
        )
        return {"fila": fila, "cambio": True}

    return _con_recalculo(con, trabajo)


def todo_de_empresas(con: sqlite3.Connection, codigos: set[str]) -> dict:
    """Todo lo que pertenece a esos proveedores (para borrarlo junto con ellos y poder devolverlo con «Deshacer»):
    sus filas de Portafolio, sus ofertas cargadas a mano o por ficha, los productos donde se les eligió a mano
    y sus ofertas de «Adicionales». Las ofertas «excel» no se guardan: salen de Portafolio al recalcular."""
    t_port = tablas.obtener("portafolio")
    lista = json.dumps(sorted(codigos))
    portafolio = [
        tablas.leer_fila(con, t_port, r["id"])
        for r in con.execute(f"SELECT id, COD_EMPRESA FROM {t_port.sql}")  # noqa: S608
        if nz.codigo_empresa(r["COD_EMPRESA"]) in codigos
    ]
    return {
        "portafolio_filas": portafolio,
        "ofertas": [dict(r) for r in con.execute(
            "SELECT * FROM ofertas WHERE origen <> 'excel' AND cod_empresa IN (SELECT value FROM json_each(?))", (lista,))],
        "seleccion": [dict(r) for r in con.execute(
            "SELECT * FROM seleccion WHERE cod_empresa IN (SELECT value FROM json_each(?))", (lista,))],
        "libres": [dict(r) for r in con.execute(
            "SELECT * FROM ofertas_libres WHERE cod_empresa IN (SELECT value FROM json_each(?))", (lista,))],
        "empresas_db": [dict(r) for r in con.execute(
            "SELECT * FROM empresas WHERE origen IN ('manual', 'subido') AND cod IN (SELECT value FROM json_each(?))", (lista,))],
    }


def borrar_todo_de_empresas(con: sqlite3.Connection, codigos: set[str], todo: dict) -> None:
    """Borra lo reunido por todo_de_empresas. Al recalcular, el tablero elige en cada producto la siguiente oferta más
    baja de OTRO proveedor (o lo deja «sin oferta» si no hay otra)."""
    lista = json.dumps(sorted(codigos))
    tablas.borrar(con, tablas.obtener("portafolio"), [f["id"] for f in todo["portafolio_filas"]])
    con.execute("DELETE FROM ofertas WHERE cod_empresa IN (SELECT value FROM json_each(?))", (lista,))
    con.execute("DELETE FROM seleccion WHERE cod_empresa IN (SELECT value FROM json_each(?))", (lista,))
    con.execute("DELETE FROM ofertas_libres WHERE cod_empresa IN (SELECT value FROM json_each(?))", (lista,))
    con.execute("DELETE FROM empresas WHERE origen IN ('manual', 'subido') AND cod IN (SELECT value FROM json_each(?))", (lista,))


def eliminar(con: sqlite3.Connection, clave: str, ids: list[int], usuario: str | None = None) -> dict:
    """Elimina una o varias filas. Siempre se permite: lo que quede sin par se ve después en los avisos de datos.
    Varias filas juntas quedan como UN solo cambio del historial (se deshacen todas de una vez)."""
    t = tablas.obtener(clave)
    filas = [f for i in dict.fromkeys(ids) if (f := tablas.leer_fila(con, t, i))]
    if not filas:
        raise tablas.TablaError("Esas filas ya no existen.", 404)

    if clave == "empresas":
        # Eliminar un proveedor borra con todos los insumos cotizados y el tablero busca la siguiente oferta más baja de otro proveedor.
        codigos = {c for f in filas if (c := nz.codigo_empresa(f["valores"]["CODIGO_EMPRESA"]))}

        def trabajo_empresas():
            todo = {**todo_de_empresas(con, codigos), "empresa_filas": filas}
            nombres = ", ".join(_etiqueta(t, f["valores"]) for f in filas)
            # Las mismas ofertas que cuenta el aviso de antes de confirmar (tablas.impacto_empresa): las del tablero.
            n_of = con.execute(
                "SELECT COUNT(*) FROM ofertas WHERE cod_empresa IN (SELECT value FROM json_each(?))", (json.dumps(sorted(codigos)),)
            ).fetchone()[0]
            historial.registrar_empresa(
                con, todo, f"Eliminó {'el proveedor' if len(filas) == 1 else f'{len(filas)} proveedores'} {nombres} con todos los insumos cotizados "
                f"({n_of} oferta{'' if n_of == 1 else 's'})", usuario)
            borrar_todo_de_empresas(con, codigos, todo)
            return {"eliminadas": tablas.borrar(con, t, [f["id"] for f in filas]), "ofertas_eliminadas": n_of}

        return _con_recalculo(con, trabajo_empresas)

    def trabajo():
        if len(filas) == 1:
            f = filas[0]
            historial.registrar(
                con,
                clave,
                "eliminar",
                f["id"],
                f["valores"],
                None,
                f"Eliminó de {t.titulo}: {_etiqueta(t, f['valores'])}",
                usuario,
            )
        else:
            historial.registrar_varias(con, t, filas, f"Eliminó {len(filas)} filas de {t.titulo}", usuario)
        return {"eliminadas": tablas.borrar(con, t, [f["id"] for f in filas])}

    return _con_recalculo(con, trabajo)


def importar_carpeta(con: sqlite3.Connection, claves: list[str], modo: str, usuario: str | None = None) -> dict:
    """Importa los Excel de la carpeta data/excel a las tablas pedidas (ver importador.importar_tablas)."""
    return importador.importar_tablas(con, claves, modo, usuario=usuario)


def importar_archivo(
    con: sqlite3.Connection, clave: str, contenido: bytes, nombre: str, modo: str, usuario: str | None = None
) -> dict:
    """Importa UN archivo subido por el usuario a la tabla `clave`."""
    tablas.obtener(clave)
    return importador.importar_tablas(con, [clave], modo, archivos={clave: (contenido, nombre)}, usuario=usuario)


def deshacer(con: sqlite3.Connection, cambio_id: int) -> dict:
    """Deshace un cambio del historial y recalcula el tablero."""
    return _con_recalculo(con, lambda: historial.deshacer(con, cambio_id))


# ------------------------------------------------------------------------------------------------ avisos
def avisos(con: sqlite3.Connection) -> list[dict]:
    """Los avisos de datos para la pantalla, con sus botones «Ir a corregir». Los importantes (warn) primero.

    Cada destino que apunta a filas de una tabla trae solo la CANTIDAD de filas (no la lista, que puede tener miles):
    la pantalla pide esas filas con ?aviso=<clave>&destino=<posición del destino>. La `clave` (por ejemplo
    «empresas_sin_nombre») no cambia cuando se recalcula: así el filtro sigue funcionando mientras se corrige."""
    salida = []
    for f in con.execute(
        "SELECT id, clave, nivel, titulo, detalle, destinos FROM avisos ORDER BY (nivel = 'warn') DESC, id"
    ):
        destinos = []
        for d in json.loads(f["destinos"] or "[]"):
            d = dict(d)
            if "filas" in d:
                d["cantidad"] = len(d.pop("filas"))
            destinos.append(d)
        salida.append(
            {
                "id": f["id"],
                "clave": f["clave"],
                "nivel": f["nivel"],
                "titulo": f["titulo"],
                "detalle": f["detalle"],
                "destinos": destinos,
            }
        )
    return salida


def filas_de_aviso(con: sqlite3.Connection, clave: str, posicion: int) -> tuple[str, list[int]]:
    """(tabla, números de fila) a los que lleva el destino `posicion` del aviso `clave`. TablaError 404 si el aviso
    ya no existe: los avisos se recalculan con cada cambio y, al corregir el problema, desaparecen."""
    f = con.execute("SELECT destinos FROM avisos WHERE clave = ?", (clave,)).fetchone()
    destinos = json.loads(f["destinos"] or "[]") if f else []
    if not 0 <= posicion < len(destinos) or "filas" not in destinos[posicion]:
        raise tablas.TablaError("Ese aviso ya no existe: el problema se corrigió.", 404)
    return destinos[posicion]["tabla"], destinos[posicion]["filas"]
