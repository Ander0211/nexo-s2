"""
OFERTAS QUE EL PROVEEDOR ENVÍA (PENDIENTES DE APROBACIÓN)
========================================================
El proveedor externo descarga la ficha FR-GDS-07, escribe sus precios y la SUBE él mismo desde su pantalla. Pero esos precios no entran al
tablero directamente: quedan en un LOTE pendiente, y el administrador los revisa (ve, producto por producto, cuánto cuesta hoy la mejor oferta
frente a lo que propone el proveedor) y los APRUEBA o los RECHAZA. Solo al aprobar pasan a la tabla `ofertas` (como ofertas «subidas») y
empiezan a competir. Así un precio equivocado o abusivo no mueve las compras sin que nadie lo vea.

Reglas de lo que el proveedor sube:
  - la ficha SIEMPRE se guarda a nombre del proveedor del usuario que la sube; si el archivo trae otro proveedor (la hoja oculta de la ficha o
    una columna de proveedor), se rechaza: nadie puede cotizar en nombre de otro
  - solo cuentan los productos que la Clínica necesita comprar HOY (los de su pantalla); lo demás se descarta y se avisa cuántos fueron
  - sin precio o con precio 0 = no cotizó ese producto (se omite en silencio); precio que no es número, o negativo = error
  - el mismo producto repetido en el archivo: se usa el más barato
  - una ficha nueva REEMPLAZA a la que seguía pendiente del mismo proveedor (no se acumulan)
Al proveedor NUNCA se le muestran precios de otros: solo ve el estado de sus propias fichas.
"""

import json
import sqlite3

import pandas as pd

from . import cargas, fichas, notificaciones, tablero
from . import normalizacion as nz

ESTADOS = ("pendiente", "aprobada", "rechazada", "reemplazada")


class PendienteError(Exception):
    """Algo que se le dice al usuario tal cual (con el código de respuesta que corresponde)."""

    def __init__(self, mensaje: str, estado: int = 422):
        super().__init__(mensaje)
        self.mensaje, self.estado = mensaje, estado


def _exigir_que_sea_suya(df: pd.DataFrame, empresa: sqlite3.Row) -> None:
    """La ficha no puede ser de otro proveedor: ni por la hoja oculta que pone la aplicación ni por una columna de proveedor."""
    codigos = {c for c in (nz.codigo_empresa(v) for v in df["COD_EMPRESA"].dropna()) if c}
    nombres = {n for n in (nz.clave_nombre(v) for v in df["EMPRESA"].dropna()) if n}
    if any(c != empresa["cod"] for c in codigos) or any(n != nz.clave_nombre(empresa["nombre"]) for n in nombres):
        raise PendienteError(
            "Esta ficha es de otro proveedor. Descarga la tuya en esta pantalla («Descargar la ficha») y vuelve a subirla.",
            409,
        )


def guardar_subida(
    con: sqlite3.Connection, cod_empresa: str, usuario: str, contenido: bytes, nombre: str | None
) -> dict:
    """Lee la ficha que subió un proveedor, valida sus precios y la deja como lote PENDIENTE. Devuelve el resumen para mostrárselo."""
    empresa = con.execute("SELECT cod, nombre FROM empresas WHERE cod = ?", (cod_empresa,)).fetchone()
    if empresa is None:
        raise PendienteError("Tu usuario no está ligado a un proveedor que exista.", 409)
    df = cargas.leer_archivo(
        contenido, nombre or "", "cotizaciones"
    )  # CargaError si el archivo no sirve (tamaño, formato, columnas...)
    _exigir_que_sea_suya(df, empresa)
    necesarios = {nz.clave_codigo(i["cod"]): i["cod"] for i in tablero.construir_tablero(con) if i["comprar"] > 0}
    res = cargas._resultado("cotizaciones", False, len(df))
    mejores: dict[
        str, tuple[float, str | None, float | None]
    ] = {}  # producto → (valor, presentación, cantidad disponible)
    fuera = 0
    for r in df.itertuples(index=False):
        cod = nz.codigo_producto(r.COD_PRODUCTO)
        if not cod:
            cargas._error(res, r.FILA, "Falta el código del producto.")
            continue
        crudo = nz.texto(r.VALOR)
        if crudo is None:
            res["omitidas"] += 1  # sin precio: no cotizó este producto
            continue
        valor = nz.numero(crudo)
        if valor is None or valor < 0:
            cargas._error(res, r.FILA, f"El valor «{crudo}» no es un precio válido.")
            continue
        if valor == 0:
            res["omitidas"] += 1
            continue
        # La cantidad disponible es opcional (vacía = «no dije cuánto tengo»); si la escribe, debe ser un número (0 = no tengo unidades).
        crudo_disp = nz.texto(getattr(r, "DISPONIBLE", None))
        disponible = None
        if crudo_disp is not None:
            disponible = nz.numero(crudo_disp)
            if disponible is None or disponible < 0:
                cargas._error(res, r.FILA, f"La cantidad disponible «{crudo_disp}» no es un número válido.")
                continue
        oficial = necesarios.get(nz.clave_codigo(cod))
        if oficial is None:
            fuera += 1  # un producto que hoy no se necesita (o que no existe)
            continue
        previa = nz.texto(r.PRESENTACION)
        if oficial in mejores:
            res["repetidas"] += 1
            if valor >= mejores[oficial][0]:
                continue
        mejores[oficial] = (valor, previa, disponible)
    if not mejores:
        detalle = f" ({fuera} producto(s) de la ficha no están en lo que necesitamos hoy.)" if fuera else ""
        raise PendienteError(
            "La ficha no trae ningún precio para los productos que necesitamos: escribe tu precio en la columna PRECIO."
            + detalle,
            422,
        )
    with con:
        con.execute(
            "UPDATE lotes_oferta SET estado = 'reemplazada' WHERE cod_empresa = ? AND estado = 'pendiente'",
            (cod_empresa,),
        )
        lote = con.execute(
            "INSERT INTO lotes_oferta (cod_empresa, usuario, archivo, filas, omitidas) VALUES (?, ?, ?, ?, ?)",
            (cod_empresa, usuario, (nombre or "")[:200] or None, len(mejores), res["omitidas"]),
        ).lastrowid
        con.executemany(
            "INSERT INTO ofertas_lote (lote_id, cod_producto, valor, presentacion, disponible) VALUES (?, ?, ?, ?, ?)",
            [(lote, c, v, p, d) for c, (v, p, d) in mejores.items()],
        )
    res.update({"lote": lote, "estado": "pendiente", "guardadas": len(mejores), "fuera_de_lista": fuera})
    return res


def mis_lotes(con: sqlite3.Connection, cod_empresa: str, limite: int = 10) -> list[dict]:
    """Las fichas que ha enviado ESTE proveedor, de la más nueva a la más vieja, con su estado. Nunca trae precios de nadie."""
    filas = con.execute(
        "SELECT id, fecha, archivo, estado, filas, omitidas, motivo, fecha_revision FROM lotes_oferta WHERE cod_empresa = ? AND estado != 'reemplazada' "
        "ORDER BY id DESC LIMIT ?",
        (cod_empresa, limite),
    ).fetchall()
    return [dict(f) for f in filas]


def conteo_pendientes(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM lotes_oferta WHERE estado = 'pendiente'").fetchone()[0]


def listar_lotes(con: sqlite3.Connection, estado: str | None = None, limite: int = 60) -> list[dict]:
    """Para el administrador: los lotes con el proveedor, primero los pendientes. Sin `estado` no trae los «reemplazada» (no importan)."""
    if estado is not None and estado not in ESTADOS:
        raise PendienteError("Estado no válido.", 422)
    donde, params = ("WHERE l.estado = ?", [estado]) if estado else ("WHERE l.estado != 'reemplazada'", [])
    filas = con.execute(
        f"SELECT l.*, COALESCE(e.nombre, l.cod_empresa) AS empresa FROM lotes_oferta l LEFT JOIN empresas e ON e.cod = l.cod_empresa {donde} "  # noqa: S608
        "ORDER BY (l.estado = 'pendiente') DESC, l.id DESC LIMIT ?",
        [*params, limite],
    ).fetchall()
    return [dict(f) for f in filas]


def _lote(con: sqlite3.Connection, lote_id: int) -> sqlite3.Row:
    fila = con.execute(
        "SELECT l.*, COALESCE(e.nombre, l.cod_empresa) AS empresa FROM lotes_oferta l LEFT JOIN empresas e ON e.cod = l.cod_empresa WHERE l.id = ?",
        (lote_id,),
    ).fetchone()
    if fila is None:
        raise PendienteError("Esa ficha no existe.", 404)
    return fila


def detalle(con: sqlite3.Connection, lote_id: int) -> dict:
    """El lote con cada producto: lo que propone el proveedor frente a la mejor oferta de hoy (y a lo que ya ofrecía este mismo proveedor), para
    que el administrador decida. Primero los que SÍ mejoran la mejor oferta, con el ahorro estimado (cantidad a comprar × diferencia)."""
    lote = _lote(con, lote_id)
    items = {i["cod"]: i for i in tablero.construir_tablero(con)}
    propias = {
        r["cod_producto"]: r["m"]
        for r in con.execute(
            "SELECT cod_producto, MIN(valor) AS m FROM ofertas WHERE cod_empresa = ? GROUP BY cod_producto",
            (lote["cod_empresa"],),
        )
    }
    filas = []
    for r in con.execute("SELECT * FROM ofertas_lote WHERE lote_id = ?", (lote_id,)):
        i = items.get(r["cod_producto"])
        mejor = i["mejor"] if i else None
        mejora = mejor is None or r["valor"] < mejor["valor"]
        comprar = i["comprar"] if i else 0
        filas.append(
            {
                "cod": r["cod_producto"],
                "descripcion": i["descripcion"] if i else r["cod_producto"],
                "valor": r["valor"],
                "presentacion": r["presentacion"],
                "disponible": r["disponible"],  # cuántas unidades dijo tener (None = no lo dijo)
                "alcanza": r["disponible"] is None
                or r["disponible"] >= comprar,  # ¿le alcanza para todo lo que hay que comprar?
                "comprar": comprar,
                "mejor_valor": mejor["valor"] if mejor else None,
                "mejor_empresa": mejor["empresa"] if mejor else None,
                "valor_actual": propias.get(
                    r["cod_producto"]
                ),  # lo que ya ofrecía este proveedor (de cualquier origen)
                "mejora": mejora,
                "ahorro": round((mejor["valor"] - r["valor"]) * comprar, 2) if mejor and mejora else None,
            }
        )
    filas.sort(key=lambda f: (not f["mejora"], -(f["ahorro"] or 0), f["descripcion"].lower()))
    return {
        "lote": dict(lote),
        "filas": filas,
        "mejoran": sum(1 for f in filas if f["mejora"]),
        "ahorro_total": round(sum(f["ahorro"] or 0 for f in filas), 2),
    }


def aprobar(con: sqlite3.Connection, lote_id: int, usuario: str, url: str = "") -> dict:
    """Aprueba el lote: sus precios pasan a ser ofertas «subidas» de ese proveedor y empiezan a competir. Devuelve lo que se cargó y cómo salió el
    correo con el que se le avisa al proveedor que la Clínica Pabón se pondrá en contacto con él (`correo`: enviado, no_configurado, error o sin_dato):
    aprobar nunca falla porque el correo no salga."""
    lote = _lote(con, lote_id)
    if lote["estado"] != "pendiente":
        raise PendienteError(f"Esa ficha ya está {lote['estado']}: no se puede aprobar otra vez.", 409)
    filas = con.execute(
        "SELECT cod_producto, valor, presentacion, disponible FROM ofertas_lote WHERE lote_id = ?", (lote_id,)
    ).fetchall()
    df = pd.DataFrame(
        {
            "COD_PRODUCTO": [f["cod_producto"] for f in filas],
            "VALOR": [repr(f["valor"]) for f in filas],
            "COD_EMPRESA": [lote["cod_empresa"]] * len(filas),
            "EMPRESA": [None] * len(filas),
            "PRESENTACION": [f["presentacion"] for f in filas],
            "DISPONIBLE": [None if f["disponible"] is None else repr(f["disponible"]) for f in filas],
            "FILA": range(2, len(filas) + 2),
        },
        dtype=object,
    )
    # La «foto de antes»: lo que ese proveedor ya tenía «subido» para estos productos, para poder RESTAURAR la ficha y dejarlo como estaba.
    previas = {
        r["cod_producto"]: r
        for r in con.execute(
            "SELECT cod_producto, valor, presentacion, disponible, creado FROM ofertas WHERE cod_empresa = ? AND origen = 'subido'",
            (lote["cod_empresa"],),
        )
    }
    with con:
        for f in filas:
            p = previas.get(f["cod_producto"])
            con.execute(
                "UPDATE ofertas_lote SET antes_existia = ?, antes_valor = ?, antes_presentacion = ?, antes_creado = ?, antes_disponible = ? WHERE lote_id = ? AND cod_producto = ?",
                (
                    1 if p else 0,
                    p["valor"] if p else None,
                    p["presentacion"] if p else None,
                    p["creado"] if p else None,
                    p["disponible"] if p else None,
                    lote_id,
                    f["cod_producto"],
                ),
            )
    res = cargas.procesar_cotizaciones(
        con, df, aplicar=True, cod_empresa=lote["cod_empresa"]
    )  # el mismo camino que «Cargar datos → Cotizaciones»
    resumen = {k: res[k] for k in ("nuevos", "actualizados", "sin_cambios", "no_cambian_ranking", "total_errores")}
    with con:
        con.execute(
            "UPDATE lotes_oferta SET estado = 'aprobada', revisado_por = ?, fecha_revision = datetime('now','localtime'), resultado = ? WHERE id = ?",
            (usuario, json.dumps(resumen), lote_id),
        )
    correo = notificaciones.enviar_aprobacion_oferta(
        _destinos_del_proveedor(con, lote), lote["empresa"], lote["fecha"][:16], lote["archivo"], len(filas), url
    )
    return {**resumen, "lote": lote_id, "estado": "aprobada", "errores": res["errores"], "correo": correo}


def _destinos_del_proveedor(con: sqlite3.Connection, lote: sqlite3.Row) -> list[tuple[str, str]]:
    """A quién se le avisa: el usuario que subió la ficha y el correo de contacto de la empresa (Administración → Empresas), sin repetir."""
    destinos: list[tuple[str, str]] = []
    vistos: set[str] = set()

    def agregar(nombre: str, correo: str | None) -> None:
        if correo and correo.strip().lower() not in vistos:
            vistos.add(correo.strip().lower())
            destinos.append((nombre, correo.strip()))

    u = con.execute("SELECT nombre, correo FROM usuarios WHERE usuario = ?", (lote["usuario"],)).fetchone()
    if u:
        agregar(u["nombre"], u["correo"])
    agregar(lote["empresa"], fichas.contacto_de(con, lote["cod_empresa"]).get("correo"))
    return destinos


def rechazar(con: sqlite3.Connection, lote_id: int, usuario: str, motivo: str = "", url: str = "") -> dict:
    """Rechaza el lote: sus precios no entran al tablero. El MOTIVO es obligatorio porque se le envía al proveedor por correo (y lo ve en su pantalla).
    Devuelve también cómo salió el correo (`correo`: enviado, no_configurado, error o sin_dato): rechazar nunca falla porque el correo no salga."""
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        raise PendienteError(
            "Escribe el motivo del rechazo: se le envía al proveedor por correo para que sepa qué corregir.", 422
        )
    lote = _lote(con, lote_id)
    if lote["estado"] != "pendiente":
        raise PendienteError(f"Esa ficha ya está {lote['estado']}: no se puede rechazar.", 409)
    with con:
        con.execute(
            "UPDATE lotes_oferta SET estado = 'rechazada', revisado_por = ?, fecha_revision = datetime('now','localtime'), motivo = ? WHERE id = ?",
            (usuario, motivo[:300], lote_id),
        )
    correo = notificaciones.enviar_rechazo_oferta(
        _destinos_del_proveedor(con, lote), lote["empresa"], lote["fecha"][:16], lote["archivo"], motivo[:300], url
    )
    return {"lote": lote_id, "estado": "rechazada", "correo": correo}


def restaurar(con: sqlite3.Connection, lote_id: int, usuario: str) -> dict:
    """Deshace la decisión sobre una ficha (aprobada o rechazada) y la deja otra vez PENDIENTE DE REVISIÓN.

      - rechazada → solo cambia su estado (no había tocado nada).
      - aprobada  → además se devuelven las ofertas: las que esa aprobación CREÓ se quitan y las que ACTUALIZÓ vuelven a su precio de antes (la «foto»
                    que se guardó al aprobar). Si alguien cambió después una de esas ofertas, NO se pisa: se deja como está y se cuenta en `no_tocadas`.
    Lo que NO se puede deshacer es el correo que ya se le envió al proveedor al decidir; al restaurar se le manda OTRO («lo sentimos, estamos revisando de nuevo
    sus ofertas, muy pronto tendrá noticias») y, como siempre, el correo nunca impide la restauración (`correo`: enviado, no_configurado, error o sin_dato).
    Protecciones: solo se restaura una ficha ya decidida; no si el proveedor tiene otra pendiente (quedarían dos a la vez); y, si estaba aprobada, solo
    la ÚLTIMA aprobada de ese proveedor (una aprobación posterior pudo cambiar esos mismos precios)."""
    lote = _lote(con, lote_id)
    estado = lote["estado"]
    if estado == "pendiente":
        raise PendienteError("Esa ficha ya está pendiente de revisión: no hay nada que restaurar.", 409)
    if estado not in ("aprobada", "rechazada"):
        raise PendienteError(f"Esa ficha está {estado}: no se puede restaurar.", 409)
    if con.execute(
        "SELECT 1 FROM lotes_oferta WHERE cod_empresa = ? AND estado = 'pendiente' AND id != ?",
        (lote["cod_empresa"], lote_id),
    ).fetchone():
        raise PendienteError(
            "Ese proveedor ya tiene otra ficha pendiente de revisión: decide primero esa (restaurar ésta dejaría dos pendientes a la vez).",
            409,
        )
    revertidas = no_tocadas = 0
    with con:
        if estado == "aprobada":
            if con.execute(
                "SELECT 1 FROM lotes_oferta WHERE cod_empresa = ? AND estado = 'aprobada' AND id > ?",
                (lote["cod_empresa"], lote_id),
            ).fetchone():
                raise PendienteError(
                    "Ese proveedor tiene una ficha aprobada más reciente: restaura primero esa (sus precios pudieron cambiar los de ésta).",
                    409,
                )
            filas = con.execute("SELECT * FROM ofertas_lote WHERE lote_id = ?", (lote_id,)).fetchall()
            if any(f["antes_existia"] is None for f in filas):
                raise PendienteError(
                    "Esta ficha se aprobó antes de que existiera «Restaurar» y no quedó guardado cómo estaba todo: no se puede deshacer automáticamente.",
                    409,
                )
            for f in filas:
                actual = con.execute(
                    "SELECT id, valor, presentacion, disponible FROM ofertas WHERE cod_producto = ? AND cod_empresa = ? AND origen = 'subido'",
                    (f["cod_producto"], lote["cod_empresa"]),
                ).fetchone()
                if actual is None:
                    continue  # ya no existe (se borró a mano): nada que devolver
                if actual["valor"] != f["valor"]:
                    no_tocadas += 1  # alguien cambió ese precio después de aprobar: no se pisa
                    continue
                if f["antes_existia"]:
                    if (
                        actual["valor"] != f["antes_valor"]
                        or (actual["presentacion"] or None) != (f["antes_presentacion"] or None)
                        or actual["disponible"] != f["antes_disponible"]
                    ):
                        con.execute(
                            "UPDATE ofertas SET valor = ?, presentacion = ?, disponible = ?, creado = ? WHERE id = ?",
                            (
                                f["antes_valor"],
                                f["antes_presentacion"],
                                f["antes_disponible"],
                                f["antes_creado"],
                                actual["id"],
                            ),
                        )
                        revertidas += 1
                else:
                    con.execute("DELETE FROM ofertas WHERE id = ?", (actual["id"],))  # la creó esta aprobación
                    revertidas += 1
            con.execute(
                "UPDATE ofertas_lote SET antes_existia = NULL, antes_valor = NULL, antes_presentacion = NULL, antes_creado = NULL, antes_disponible = NULL WHERE lote_id = ?",
                (lote_id,),
            )
        con.execute(
            "UPDATE lotes_oferta SET estado = 'pendiente', revisado_por = NULL, fecha_revision = NULL, motivo = NULL, resultado = NULL WHERE id = ?",
            (lote_id,),
        )
    correo = notificaciones.enviar_restauracion_oferta(
        _destinos_del_proveedor(con, lote), lote["empresa"], lote["fecha"][:16], lote["archivo"]
    )
    return {
        "lote": lote_id,
        "estado": "pendiente",
        "antes": estado,
        "revertidas": revertidas,
        "no_tocadas": no_tocadas,
        "correo": correo,
    }


def excel_lote(con: sqlite3.Connection, lote_id: int) -> tuple[bytes, str]:
    """La ficha de un proveedor como Excel para el administrador: cada precio frente a la mejor oferta de hoy. Devuelve (bytes, nombre de archivo)."""
    import io
    import re

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    d = detalle(con, lote_id)
    lote = d["lote"]
    wb = Workbook()
    ws = wb.active
    ws.title = "OFERTA"
    cols = [
        "COD_PRODUCTO",
        "DESCRIPCION",
        "A_COMPRAR",
        "PRECIO_PROPUESTO",
        "PRESENTACION",
        "MEJOR_OFERTA_HOY",
        "PROVEEDOR_MEJOR_HOY",
        "YA_OFRECIA",
        "MEJORA",
        "AHORRO_ESTIMADO",
    ]
    ws.append(cols)
    for c in ws[1]:
        c.font, c.fill, c.alignment = (
            Font(bold=True, color="FFFFFF"),
            PatternFill("solid", fgColor="1F4E96"),
            Alignment(horizontal="center", vertical="center", wrap_text=True),
        )
    for f in d["filas"]:
        ws.append(
            [
                f["cod"],
                f["descripcion"],
                f["comprar"],
                f["valor"],
                f["presentacion"],
                f["mejor_valor"],
                f["mejor_empresa"],
                f["valor_actual"],
                "SI" if f["mejora"] else "NO",
                f["ahorro"],
            ]
        )
    for n, ancho in enumerate([16, 60, 12, 16, 16, 18, 34, 14, 10, 18], 1):
        ws.column_dimensions[chr(64 + n)].width = ancho
    for fila in ws.iter_rows(min_row=2):
        for c in (fila[3], fila[5], fila[7], fila[9]):
            c.number_format = "#,##0"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    info = wb.create_sheet("DATOS DE LA FICHA")
    for fila in (
        ("Proveedor", lote["empresa"]),
        ("Código", lote["cod_empresa"]),
        ("Enviada", lote["fecha"]),
        ("Archivo", lote["archivo"] or ""),
        ("Estado", lote["estado"]),
        ("Precios enviados", len(d["filas"])),
        ("Mejoran la mejor oferta", d["mejoran"]),
        ("Ahorro estimado", d["ahorro_total"]),
        ("Motivo del rechazo", lote["motivo"] or ""),
    ):
        info.append(fila)
    info.column_dimensions["A"].width, info.column_dimensions["B"].width = 26, 50
    salida = io.BytesIO()
    wb.save(salida)
    nombre = re.sub(r"[^A-Za-z0-9_-]+", "_", lote["empresa"]).strip("_")
    return salida.getvalue(), f"OFERTA_{nombre}_{lote_id}.xlsx"
