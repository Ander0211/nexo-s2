"""
HISTORIAL DE CAMBIOS (y «Deshacer»)
===================================
Cada cambio que se hace en las 5 tablas de la pantalla «Administración» queda anotado en la tabla `cambios`, con la
fecha, lo que había ANTES y lo que hay DESPUÉS. Desde el historial se puede deshacer:

    agregar    → se elimina la fila que se agregó
    editar     → la fila vuelve a los valores que tenía
    eliminar   → la fila vuelve a existir, con su mismo número
    eliminar_varias → las filas vuelven a existir todas, con sus mismos números (se eliminaron juntas)
    importar   → la tabla vuelve a estar como antes de importar el Excel (se guarda una copia completa)

Límites (para que la base no crezca sin fin): se recuerdan los últimos 300 cambios y las copias completas de las
últimas 5 importaciones. Una importación más vieja se sigue viendo en el historial pero ya no se puede deshacer.
Este módulo solo escribe en `cambios` y en las 5 tablas; el recálculo del tablero lo hace admin.py después.
"""

import base64
import json
import sqlite3
import zlib

from . import tablas

MAX_CAMBIOS = 300
MAX_COPIAS = 5


def _comprimir(filas: list[dict]) -> str:
    """Una copia completa de una tabla como texto compacto (JSON comprimido con zlib y pasado a base64)."""
    return base64.b64encode(zlib.compress(json.dumps(filas, ensure_ascii=False).encode("utf-8"), 6)).decode("ascii")


def _descomprimir(texto: str) -> list[dict]:
    return json.loads(zlib.decompress(base64.b64decode(texto)).decode("utf-8"))


def registrar(
    con: sqlite3.Connection,
    tabla: str,
    accion: str,
    fila_id: int | None,
    antes: dict | None,
    despues: dict | None,
    resumen: str,
    usuario: str | None = None,
) -> int:
    """Anota un cambio de UNA fila (agregar, editar o eliminar). `antes` y `despues` son los valores de la fila.
    `usuario` = quién lo hizo (el usuario de la sesión)."""
    cur = con.execute(
        "INSERT INTO cambios (tabla, accion, fila_id, antes, despues, resumen, usuario) VALUES (?,?,?,?,?,?,?)",
        (
            tabla,
            accion,
            fila_id,
            json.dumps(antes, ensure_ascii=False) if antes is not None else None,
            json.dumps(despues, ensure_ascii=False) if despues is not None else None,
            resumen,
            usuario,
        ),
    )
    _podar(con)
    return cur.lastrowid


def registrar_varias(
    con: sqlite3.Connection, t: tablas.Tabla, filas: list[dict], resumen: str, usuario: str | None = None
) -> int:
    """Anota la eliminación de VARIAS filas a la vez como UN solo cambio (guarda las filas, comprimidas)."""
    cur = con.execute(
        "INSERT INTO cambios (tabla, accion, antes, resumen, usuario) VALUES (?, 'eliminar_varias', ?, ?, ?)",
        (t.clave, _comprimir(filas), resumen, usuario),
    )
    _podar(con)
    return cur.lastrowid


def registrar_copia(con: sqlite3.Connection, t: tablas.Tabla, resumen: str, usuario: str | None = None) -> int:
    """Anota una importación guardando una copia COMPLETA de la tabla tal como está AHORA (antes de importar)."""
    cur = con.execute(
        "INSERT INTO cambios (tabla, accion, antes, resumen, usuario) VALUES (?, 'importar', ?, ?, ?)",
        (t.clave, _comprimir(tablas.instantanea(con, t)), resumen, usuario),
    )
    _podar(con)
    return cur.lastrowid


def _podar(con: sqlite3.Connection) -> None:
    """Mantiene el historial dentro de sus límites (ver arriba)."""
    con.execute("DELETE FROM cambios WHERE id NOT IN (SELECT id FROM cambios ORDER BY id DESC LIMIT ?)", (MAX_CAMBIOS,))
    con.execute(
        "UPDATE cambios SET antes = NULL, resumen = resumen || ' (sin copia para deshacer)' "
        "WHERE accion IN ('importar', 'eliminar_varias') AND antes IS NOT NULL AND id NOT IN "
        "(SELECT id FROM cambios WHERE accion IN ('importar', 'eliminar_varias') AND antes IS NOT NULL "
        "ORDER BY id DESC LIMIT ?)",
        (MAX_COPIAS,),
    )


def listar(con: sqlite3.Connection, tabla: str | None = None, limite: int = 100) -> list[dict]:
    """Los cambios más recientes primero. Con `tabla`, solo los de esa tabla."""
    filtro, params = ("WHERE tabla = ?", [tabla]) if tabla else ("", [])
    filas = con.execute(
        "SELECT id, fecha, tabla, accion, fila_id, resumen, deshecho, usuario, "
        "(accion NOT IN ('importar', 'eliminar_varias') OR antes IS NOT NULL) AS se_puede "
        f"FROM cambios {filtro} ORDER BY id DESC LIMIT ?",  # noqa: S608
        [*params, max(1, min(int(limite), 500))],
    ).fetchall()
    return [
        {**dict(f), "deshecho": bool(f["deshecho"]), "se_puede": bool(f["se_puede"]) and not f["deshecho"]}
        for f in filas
    ]


def _deshacer_uno(con: sqlite3.Connection, c: sqlite3.Row) -> None:
    """Revierte UN cambio. Lanza TablaError (409) si ya no se puede sin pisar otra cosa."""
    t = tablas.obtener(c["tabla"])
    accion, fila_id = c["accion"], c["fila_id"]
    if accion == "agregar":
        tablas.borrar(con, t, [fila_id])  # si ya la habían borrado, no hay nada que hacer
    elif accion == "editar":
        if tablas.leer_fila(con, t, fila_id) is None:
            raise tablas.TablaError(f"No se puede deshacer: la fila {fila_id} ya no existe en {t.titulo}.", 409)
        tablas.actualizar_crudo(con, t, fila_id, json.loads(c["antes"]))
    elif accion == "eliminar":
        if tablas.leer_fila(con, t, fila_id) is not None:
            raise tablas.TablaError(f"No se puede deshacer: ya hay otra fila con el número {fila_id}.", 409)
        tablas.insertar_crudo(con, t, json.loads(c["antes"]), fila_id)
    elif accion == "eliminar_varias":
        if c["antes"] is None:
            raise tablas.TablaError("Ese cambio es muy antiguo: ya no hay copia para deshacerlo.", 409)
        filas = _descomprimir(c["antes"])
        ocupadas = [f["id"] for f in filas if tablas.leer_fila(con, t, f["id"]) is not None]
        if ocupadas:
            raise tablas.TablaError(f"No se puede deshacer: ya hay otra fila con el número {ocupadas[0]}.", 409)
        for f in filas:
            tablas.insertar_crudo(con, t, f["valores"], f["id"])
    elif accion == "importar":
        if c["antes"] is None:
            raise tablas.TablaError("Esa importación es muy antigua: ya no hay copia para deshacerla.", 409)
        tablas.restaurar(con, t, _descomprimir(c["antes"]))
    else:  # pragma: no cover - solo si alguien escribe a mano en la tabla cambios
        raise tablas.TablaError(f"Acción desconocida: {accion}.", 409)


def deshacer(con: sqlite3.Connection, cambio_id: int) -> dict:
    """Deshace un cambio. Devuelve {'tabla': ...}.

    No recalcula el tablero ni confirma la transacción: eso lo hace quien llama (admin.deshacer)."""
    c = con.execute("SELECT * FROM cambios WHERE id = ?", (cambio_id,)).fetchone()
    if c is None:
        raise tablas.TablaError("Ese cambio ya no está en el historial.", 404)
    if c["deshecho"]:
        raise tablas.TablaError("Ese cambio ya se había deshecho.", 409)
    _deshacer_uno(con, c)
    con.execute("UPDATE cambios SET deshecho = 1 WHERE id = ?", (cambio_id,))
    return {"tabla": c["tabla"]}
