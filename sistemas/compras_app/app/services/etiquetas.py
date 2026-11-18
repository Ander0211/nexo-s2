"""
ETIQUETAS «NUEVO» (productos y empresas)
========================================
Un producto o una empresa es NUEVO cuando es la primera vez que el sistema lo ve: no había estado antes. Da igual cómo llegó
(en un Excel que se importó, a mano, o subido desde «Cargar datos»). La etiqueta «Nuevo» se muestra durante DIAS_NUEVO días
(app/config.py) desde esa primera vez.

CÓMO SE SABE:  la tabla `vistos` guarda, por cada código, cuándo se vio por primera vez. Cada vez que se arma el tablero (y al
arrancar) `sincronizar` compara los códigos que hay con los que ya se habían visto, y anota los que faltan con la fecha de hoy.
  - Lo que ya existía cuando se empezó a llevar este registro (o cuando se hizo la primera carga de los Excel) queda anotado SIN
    fecha: es «lo de siempre», no se marca como nuevo.
  - Un código nuevo que se borra y luego se vuelve a crear NO vuelve a ser nuevo: ya había estado.
"""

import sqlite3
from datetime import datetime, timedelta

from .. import config

_TABLAS = (("producto", "productos"), ("empresa", "empresas"))
_FORMATO = "%Y-%m-%d %H:%M:%S"  # igual al de SQLite (datetime('now','localtime'))


def ahora() -> datetime:
    """La hora de ahora (aparte para poder cambiarla en las pruebas)."""
    return datetime.now()


def sincronizar(con: sqlite3.Connection) -> None:
    """Anota los productos y empresas que el sistema ve por primera vez. Si de un tipo no había NINGUNO anotado, lo que hay es
    «lo de siempre» (primera_vez vacía = no es nuevo); a partir de ahí, cada código que aparezca queda con la fecha de hoy."""
    cambio = False
    for tipo, tabla in _TABLAS:
        codigos = {r[0] for r in con.execute(f"SELECT cod FROM {tabla}")}  # noqa: S608
        vistos = {r[0] for r in con.execute("SELECT cod FROM vistos WHERE tipo = ?", (tipo,))}
        faltan = codigos - vistos
        if not faltan:
            continue
        primera = ahora().strftime(_FORMATO) if vistos else None
        con.executemany(
            "INSERT OR IGNORE INTO vistos (tipo, cod, primera_vez) VALUES (?, ?, ?)",
            [(tipo, c, primera) for c in faltan],
        )
        cambio = True
    if cambio:
        con.commit()


def nuevos(con: sqlite3.Connection, tipo: str) -> dict[str, str]:
    """Los códigos de ese tipo («producto» o «empresa») que hoy llevan la etiqueta «Nuevo»: {código: primera vez que se vio}."""
    desde = (ahora() - timedelta(days=config.DIAS_NUEVO)).strftime(_FORMATO)
    filas = con.execute(
        "SELECT cod, primera_vez FROM vistos WHERE tipo = ? AND primera_vez IS NOT NULL AND primera_vez >= ?",
        (tipo, desde),
    )
    return {f["cod"]: f["primera_vez"] for f in filas}
