"""
IMPORTADOR Y RECÁLCULO
======================
Este módulo hace DOS trabajos distintos, y conviene no confundirlos:

  A. IMPORTAR un Excel a una de las 5 tablas de los Excel (services/tablas.py)
        cargar_tablas() / importar_tablas()
     Solo copia las filas del archivo a la tabla, en uno de dos modos:
        «reemplazar»  la tabla queda igual que el Excel (se borra lo que había)
        «agregar»     se agregan las filas nuevas y se actualizan las que ya existían (por código); no se borra nada
     Se ejecuta cuando el usuario lo pide (menú «Actualizar Excel» o botón «Importar» de la administración) y la
     primera vez que arranca la aplicación (main.py). NUNCA por su cuenta: lo que se edita en «Administración» se queda.

  B. RECALCULAR lo que ve el tablero a partir de las 5 tablas
        recalcular()
     Toma las 5 tablas (con sus ediciones) y calcula los productos, los proveedores, las ofertas y los avisos.
     Se ejecuta después de CADA cambio (importar, agregar, editar, eliminar, deshacer). Son las reglas de siempre:

        - Los datos PROPIOS del usuario se conservan: ofertas, productos y proveedores hechos a mano ('manual') o
          subidos desde el panel «Cargar datos» ('subido'), y las elecciones de proveedor. Si un producto o proveedor
          está en las tablas Y ADEMÁS es del usuario, gana el del usuario.
        - Todo lo raro que se encuentra (códigos repetidos, proveedores sin nombre, etc.) queda en la tabla `avisos`,
          y cada aviso sabe a qué tabla y a qué filas llevar al usuario para corregirlo (`destinos`).

Recorrido de `recalcular()`, en orden:
    1. Lee las 5 tablas                    6. Portafolio → ofertas válidas
    2. Proveedores                         7. Une productos de stock + ficha + portafolio
    3. Stock                               8. Detecta productos por comprar sin oferta
    4. Existencias                         9. Guarda todo en la base (una sola transacción)
    5. Ficha de cotización                10. Avisos de datos «huérfanos» (elecciones de proveedor viejas)
"""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from ..config import carpeta_excel
from . import historial, tablas
from . import normalizacion as nz
from .ranking import cantidad_a_comprar

ImportacionError = tablas.ImportacionError  # se sigue pudiendo usar importador.ImportacionError


def _muestra(items, n=8) -> str:
    """Para los avisos: muestra hasta 8 elementos y resume el resto ("A, B, C … y 40 más")."""
    items = list(items)
    extra = f" … y {len(items) - n} más" if len(items) > n else ""
    return ", ".join(map(str, items[:n])) + extra


def _destino(texto: str, *, tabla=None, filas=None, agregar=None, vista=None, filtro=None) -> dict:
    """Un botón «Ir a corregir» de un aviso. Lleva al usuario a:
    tabla + filas    la tabla de Administración, mostrando solo esas filas (sus números de fila)
    tabla + agregar  la tabla de Administración con el formulario «Agregar» ya abierto y estos valores puestos
    vista + filtro   el tablero de compras con ese filtro puesto («sin_oferta»...)"""
    d: dict = {"texto": texto}
    if tabla:
        d["tabla"] = tabla
    if filas is not None:
        d["filas"] = sorted(set(filas))
    if agregar is not None:
        d["agregar"] = agregar
    if vista:
        d["vista"] = vista
        d["filtro"] = filtro
    return d


# ============================================================================================ A. IMPORTAR
def cargar_tablas(
    con: sqlite3.Connection,
    claves: list[str],
    modo: str = "reemplazar",
    carpeta: Path | None = None,
    archivos: dict[str, tuple[bytes, str]] | None = None,
    usuario: str | None = None,
) -> list[dict]:
    """Copia el Excel de cada tabla pedida a su tabla (ver A arriba). NO recalcula el tablero ni confirma la transacción.

    claves    las tablas a importar: "stock", "existencias", "empresas", "ficha", "portafolio"
    carpeta   de dónde leer los Excel (por defecto data/excel)
    archivos  {tabla: (bytes, nombre)} para usar un archivo SUBIDO en vez del de la carpeta
    Primero se LEEN todos los archivos: si falta uno o le falta una columna, se lanza ImportacionError sin haber
    tocado nada. Antes de cambiar cada tabla se guarda una copia completa en el historial (para «Deshacer»)."""
    carpeta = carpeta or carpeta_excel()
    leidos = {}
    for clave in claves:
        t = tablas.obtener(clave)
        if archivos and clave in archivos:
            leidos[clave] = tablas.leer_excel(t, archivos[clave][0], archivos[clave][1])
        else:
            leidos[clave] = tablas.leer_excel(t, carpeta / t.archivo)
    resultados = []
    for clave in claves:
        t = tablas.TABLAS[clave]
        filas, presentes = leidos[clave]
        cambio_id = historial.registrar_copia(con, t, f"Importó {t.archivo}", usuario)
        r = tablas.aplicar_excel(con, t, filas, presentes, modo)
        resumen = (
            f"Reemplazó {t.titulo} con {t.archivo}: {r['nuevos']} filas"
            if modo == "reemplazar"
            else f"Agregó a {t.titulo} desde {t.archivo}: {r['nuevos']} nuevas, {r['actualizados']} actualizadas"
        )
        con.execute("UPDATE cambios SET resumen = ? WHERE id = ?", (resumen, cambio_id))
        resultados.append({"tabla": clave, "titulo": t.titulo, "archivo": t.archivo, "modo": modo, **r})
    return resultados


def importar_tablas(
    con: sqlite3.Connection,
    claves: list[str],
    modo: str = "reemplazar",
    carpeta: Path | None = None,
    archivos: dict[str, tuple[bytes, str]] | None = None,
    usuario: str | None = None,
) -> dict:
    """Importa las tablas pedidas Y recalcula el tablero. Todo en una transacción: o entra todo o no entra nada.
    Devuelve el resumen del recálculo más `tablas` (qué pasó con cada Excel)."""
    try:
        resultados = cargar_tablas(con, claves, modo, carpeta, archivos, usuario)
        resumen = recalcular(con)
        con.execute("INSERT OR REPLACE INTO meta VALUES ('crudas_iniciadas', '1')")
        con.commit()
    except Exception:
        con.rollback()
        raise
    resumen["tablas"] = resultados
    return resumen


def importar(con: sqlite3.Connection, carpeta: Path | None = None, usuario: str | None = None) -> dict:
    """Importa los 5 Excel de la carpeta REEMPLAZANDO las 5 tablas (es lo que hace el arranque inicial y
    POST /api/importar). Lo hecho a mano en «Cargar datos» y «Agregar oferta» se conserva."""
    return importar_tablas(con, list(tablas.TABLAS), "reemplazar", carpeta, usuario=usuario)


# ============================================================================================ B. RECALCULAR
def recalcular(con: sqlite3.Connection) -> dict:
    """Calcula productos, proveedores, ofertas y avisos a partir de las 5 tablas y los guarda (ver B arriba).
    Devuelve un resumen con los conteos. Confirma la transacción (también lo que se escribió antes en las 5 tablas)."""
    t0 = time.time()
    df_stock = tablas.para_calculo(con, tablas.TABLAS["stock"])
    df_exist = tablas.para_calculo(con, tablas.TABLAS["existencias"])
    df_emp = tablas.para_calculo(con, tablas.TABLAS["empresas"])
    df_ficha = tablas.para_calculo(con, tablas.TABLAS["ficha"])
    df_port = tablas.para_calculo(con, tablas.TABLAS["portafolio"])
    # Lista de avisos que se irá llenando: (clave estable, nivel, título, detalle, destinos).
    avisos: list[tuple[str, str, str, str | None, list[dict]]] = []

    # ---- 2. Proveedores (EMPRESA.xlsx) -----------------------------------------------------
    empresas: dict[str, tuple[str, str]] = {}  # cod -> (nombre, origen)
    sin_nombre, filas_sin_nombre = [], []
    for r in df_emp.itertuples(index=False):
        cod = nz.codigo_empresa(r.CODIGO_EMPRESA)  # "05" y "5" quedan como "5"
        if not cod:
            continue
        nombre = nz.texto(r.NOMBRE)
        if not nombre:
            # Hay proveedores sin nombre en el Excel (14, 34, 61): se les pone uno provisional y se avisa.
            sin_nombre.append(cod)
            filas_sin_nombre.append(r.ID)
            nombre = f"Proveedor {cod} (sin nombre)"
        empresas[cod] = (nombre, "excel")
    if sin_nombre:
        avisos.append(
            (
                "empresas_sin_nombre",
                "warn",
                "Proveedores sin nombre en EMPRESA.xlsx",
                _muestra(sin_nombre),
                [_destino("Ir a Empresas y ponerles nombre", tabla="empresas", filas=filas_sin_nombre)],
            )
        )

    # ---- 3. Stock (05-STOCK.xlsx): se usa la PRIMERA aparición de cada código ---------------
    stock: dict[str, dict] = {}
    repetidos: dict[str, int] = {}
    filas_stock: dict[str, list[int]] = {}  # cod -> números de fila que lo tienen (para llevar al usuario a ellas)
    for r in df_stock.itertuples(index=False):
        cod = nz.codigo_producto(r.COD_PRODUCTO)
        if not cod:
            continue
        filas_stock.setdefault(cod, []).append(r.ID)
        if cod in stock:
            # Código repetido (ej. A0001 está en 3 productos distintos): se ignora la fila y se cuenta.
            repetidos[cod] = repetidos.get(cod, 1) + 1
            continue
        stock[cod] = {
            "descripcion": nz.texto(r.DESCRIPCION) or cod,
            "max": nz.numero(r.STOCKMAX),
            "med": nz.numero(r.STOCKMED),
            "min": nz.numero(r.STOCKMIN),
        }
    if repetidos:
        avisos.append(
            (
                "stock_repetidos",
                "warn",
                f"{len(repetidos)} códigos repetidos en STOCK (productos distintos con el mismo código)",
                "Se usó la primera fila de cada uno: " + _muestra(repetidos),
                [
                    _destino(
                        "Ir a Stock y dejar una sola fila por código",
                        tabla="stock",
                        filas=[i for c in repetidos for i in filas_stock[c]],
                    )
                ],
            )
        )

    # ---- 4. Existencias (06-EXISTENCIAS.xlsx): suma si un código aparece varias veces --------
    existencias: dict[str, float] = {}
    filas_exist: dict[str, list[int]] = {}
    for r in df_exist.itertuples(index=False):
        cod = nz.codigo_producto(r.COD_PRODUCTO)
        n = nz.numero(r.CANTIDAD)
        if cod and n is not None:
            existencias[cod] = existencias.get(cod, 0) + n
            filas_exist.setdefault(cod, []).append(r.ID)
    # Existencias de productos que no están en el stock: no tienen StockMax, así que no se compran.
    huerfanas = [c for c in existencias if c not in stock]
    if huerfanas:
        avisos.append(
            (
                "existencias_sin_stock",
                "info",
                f"{len(huerfanas)} productos con existencias no tienen stock definido",
                "Se ignoran para la compra: " + _muestra(huerfanas),
                [
                    _destino(
                        "Ir a Existencias y ver estas filas",
                        tabla="existencias",
                        filas=[i for c in huerfanas for i in filas_exist[c]],
                    )
                ],
            )
        )

    # ---- 5. Ficha de cotización (catálogo de productos y sus descripciones) -----------------
    ficha: dict[str, str] = {}
    mal_codificados, filas_mal = [], []
    for r in df_ficha.itertuples(index=False):
        cod = nz.codigo_producto(r.COD_SALUDIPS)
        if not cod:
            continue
        ficha.setdefault(cod, nz.texto(r.DESCRIPCION) or cod)  # setdefault: solo guarda la primera
        # Algunos productos vienen marcados «MAL CODIFICADO» en la columna TIPO_INSUMO.
        if nz.texto(r.TIPO_INSUMO) and "MAL" in nz.texto(r.TIPO_INSUMO).upper():
            mal_codificados.append(cod)
            filas_mal.append(r.ID)
    if mal_codificados:
        avisos.append(
            (
                "ficha_mal_codificados",
                "warn",
                "Productos marcados MAL CODIFICADO en la ficha de cotización",
                _muestra(sorted(set(mal_codificados))),
                [_destino("Ir a la Ficha de cotización y corregir el código", tabla="ficha", filas=filas_mal)],
            )
        )

    # ---- 6. Portafolio (PORTAFOLIO.xlsx): ofertas válidas, UNA por (producto, proveedor) ----
    ofertas: dict[tuple[str, str], tuple[float, str | None]] = {}  # (producto, proveedor) -> (valor, presentación)
    desc_port: dict[str, str] = {}
    sin_precio = sin_codigo = repetidas = 0
    codigos_empresa_cambiados = set()
    filas_ignoradas: list[int] = []  # filas sin precio o sin código
    filas_cambiadas: list[int] = []  # filas cuyo código de proveedor traía ceros a la izquierda
    filas_por_oferta: dict[tuple[str, str], list[int]] = {}  # (producto, proveedor) -> filas válidas que lo ofrecen
    filas_por_emp: dict[str, list[int]] = {}
    for r in df_port.itertuples(index=False):
        cod = nz.codigo_producto(r.COD_PRODUCTO)
        crudo = nz.codigo_producto(r.COD_EMPRESA)  # código del proveedor tal como venía ("05")
        emp = nz.codigo_empresa(r.COD_EMPRESA)  # ya normalizado ("5")
        if not cod or not emp:
            sin_codigo += 1
            filas_ignoradas.append(r.ID)
            continue
        filas_por_emp.setdefault(emp, []).append(r.ID)
        if crudo != emp:
            codigos_empresa_cambiados.add(f"{crudo}→{emp}")
            filas_cambiadas.append(r.ID)
        valor = nz.numero(r.VALOR)
        if valor is None or valor <= 0:
            # Fila sin precio o con precio 0: no es una oferta real, se ignora (suelen ser muchas).
            sin_precio += 1
            filas_ignoradas.append(r.ID)
            continue
        desc_port.setdefault(cod, nz.texto(r.DESCRIPCION) or cod)
        clave = (cod, emp)
        pres = nz.texto(r.PRESENTACION)
        filas_por_oferta.setdefault(clave, []).append(r.ID)
        if clave in ofertas:
            # El mismo proveedor ofrece el mismo producto en dos filas: se queda con la más barata.
            repetidas += 1
            if valor >= ofertas[clave][0]:
                continue
        ofertas[clave] = (valor, pres)
    if codigos_empresa_cambiados:
        avisos.append(
            (
                "portafolio_codigos_unificados",
                "info",
                "Códigos de proveedor unificados (ceros a la izquierda)",
                _muestra(sorted(codigos_empresa_cambiados)),
                [_destino("Ir al Portafolio y ver esas filas", tabla="portafolio", filas=filas_cambiadas)],
            )
        )
    if sin_precio or sin_codigo:
        avisos.append(
            (
                "portafolio_ignoradas",
                "info",
                f"{sin_precio + sin_codigo} filas del portafolio se ignoraron",
                f"{sin_precio} sin precio o con precio 0 · {sin_codigo} sin código de producto o proveedor",
                [_destino("Ir al Portafolio y ver esas filas", tabla="portafolio", filas=filas_ignoradas)],
            )
        )
    if repetidas:
        avisos.append(
            (
                "portafolio_repetidas",
                "info",
                f"{repetidas} ofertas repetidas (mismo producto y proveedor)",
                "Se dejó la de menor precio.",
                [
                    _destino(
                        "Ir al Portafolio y ver las filas repetidas",
                        tabla="portafolio",
                        filas=[i for ids in filas_por_oferta.values() if len(ids) > 1 for i in ids],
                    )
                ],
            )
        )

    # Proveedores que tienen ofertas pero NO están en EMPRESA.xlsx (ej. el 80): se crean como «inferida».
    inferidas = sorted({e for (_, e) in ofertas if e not in empresas}, key=lambda x: (len(x), x))
    for e in inferidas:
        empresas[e] = (f"Proveedor {e} (no está en EMPRESA.xlsx)", "inferida")
    if inferidas:
        avisos.append(
            (
                "empresas_inferidas",
                "warn",
                "Proveedores con ofertas que no existen en EMPRESA.xlsx",
                _muestra(inferidas),
                [
                    _destino(
                        f"Ir a Empresas y agregar el proveedor {inferidas[0]}",
                        tabla="empresas",
                        agregar={"CODIGO_EMPRESA": inferidas[0]},
                    ),
                    _destino(
                        "Ver sus ofertas en el Portafolio",
                        tabla="portafolio",
                        filas=[i for e in inferidas for i in filas_por_emp[e]],
                    ),
                ],
            )
        )

    # ---- 7. Productos: unión de stock, ficha y portafolio ----------------------------------
    # Un producto puede estar en uno, dos o los tres archivos. La descripción se toma en este
    # orden de preferencia: stock → ficha → portafolio.
    codigos = list(stock) + [c for c in ficha if c not in stock]
    codigos += [c for c in desc_port if c not in stock and c not in ficha]
    productos = []
    for cod in codigos:
        s = stock.get(cod)
        productos.append(
            (
                cod,
                (s["descripcion"] if s else ficha.get(cod) or desc_port.get(cod) or cod),
                s["max"] if s else None,
                s["med"] if s else None,
                s["min"] if s else None,
                existencias.get(cod, 0.0) if s else 0.0,
                1 if s else 0,  # en_stock
            )
        )

    # ---- 8. ¿Qué productos hay que comprar pero nadie ofrece? ------------------------------
    con_oferta = {c for (c, _) in ofertas}
    # Una cantidad que el usuario fijó a mano (tabla `cantidades`) manda sobre la calculada: si puso 0, ya no se compra;
    # si puso más de 0 en un producto que no tenía nada por comprar, ahora sí.
    editadas = {r["cod_producto"]: r["cantidad"] for r in con.execute("SELECT cod_producto, cantidad FROM cantidades")}

    def a_comprar(c: str) -> int:
        s = stock.get(c)
        return editadas.get(c, cantidad_a_comprar(s["max"] if s else None, existencias.get(c, 0)))

    por_comprar = [c for c in codigos if a_comprar(c) > 0]
    sin_oferta = [c for c in por_comprar if c not in con_oferta]
    if sin_oferta:
        avisos.append(
            (
                "sin_oferta",
                "warn",
                f"{len(sin_oferta)} productos por comprar no tienen ninguna oferta",
                "Necesitan cotización o una oferta manual: " + _muestra(sin_oferta),
                [_destino("Ver estos productos en el tablero", vista="tablero", filtro="sin_oferta")],
            )
        )
    fuera = sorted(c for c in con_oferta if c not in stock)
    if fuera:
        avisos.append(
            (
                "ofertas_sin_stock",
                "info",
                f"{len(fuera)} productos con ofertas no tienen stock definido",
                "No tienen cantidad a comprar: " + _muestra(fuera),
                [
                    _destino(
                        f"Ir a Stock y agregar el producto {fuera[0]}",
                        tabla="stock",
                        agregar={"COD_PRODUCTO": fuera[0], "DESCRIPCION": desc_port.get(fuera[0])},
                    ),
                    _destino(
                        "Ver sus ofertas en el Portafolio",
                        tabla="portafolio",
                        filas=[i for (c, _), ids in filas_por_oferta.items() if c in set(fuera) for i in ids],
                    ),
                ],
            )
        )

    # ---- 9. Escritura en la base (una sola transacción: o entra todo o no entra nada) -------
    with con:
        # Datos PROPIOS del usuario (a mano o subidos): se conservan y ganan sobre lo calculado.
        # Se anotan sus códigos ANTES de borrar, para no volver a insertar los calculados encima de ellos.
        productos_propios = {r["cod"] for r in con.execute("SELECT cod FROM productos WHERE origen != 'excel'")}
        empresas_propias = {
            r["cod"] for r in con.execute("SELECT cod FROM empresas WHERE origen IN ('manual', 'subido')")
        }
        # Se borra SOLO lo calculado desde las tablas. Las ofertas 'manual' y 'subido', los productos y proveedores
        # propios y la tabla `seleccion` no se tocan: por eso lo tuyo sobrevive a cada recálculo.
        con.execute("DELETE FROM ofertas WHERE origen = 'excel'")
        con.execute("DELETE FROM productos WHERE origen = 'excel'")
        con.execute("DELETE FROM empresas WHERE origen NOT IN ('manual', 'subido')")
        con.execute("DELETE FROM avisos")
        con.executemany(
            "INSERT INTO productos (cod, descripcion, stock_max, stock_med, stock_min, existencias, en_stock, origen) "
            "VALUES (?,?,?,?,?,?,?, 'excel')",
            [p for p in productos if p[0] not in productos_propios],
        )
        con.executemany(
            "INSERT OR REPLACE INTO empresas (cod, nombre, origen) VALUES (?,?,?)",
            [(c, n, o) for c, (n, o) in empresas.items() if c not in empresas_propias],
        )
        con.executemany(
            "INSERT INTO ofertas (cod_producto, cod_empresa, valor, presentacion, origen) VALUES (?,?,?,?, 'excel')",
            [(c, e, v, p) for (c, e), (v, p) in ofertas.items()],
        )

        # ---- 10. Datos «huérfanos»: un proveedor elegido a mano que YA NO ofrece ese producto -------------
        # (por ejemplo, porque se eliminó su fila del Portafolio). El tablero lo tolera y usa la mejor oferta, pero
        # se avisa. Se calcula aquí, con las ofertas ya guardadas (incluidas las que el usuario agregó a mano).
        viejas = con.execute(
            "SELECT s.cod_producto FROM seleccion s WHERE NOT EXISTS "
            "(SELECT 1 FROM ofertas o WHERE o.cod_producto = s.cod_producto AND o.cod_empresa = s.cod_empresa)"
        ).fetchall()
        if viejas:
            cods = sorted(r["cod_producto"] for r in viejas)
            avisos.append(
                (
                    "eleccion_vieja",
                    "warn",
                    f"{len(cods)} productos tienen elegido un proveedor que ya no los ofrece",
                    "Se está usando la mejor oferta disponible: " + _muestra(cods),
                    [_destino("Ver los productos elegidos en el tablero", vista="tablero", filtro="elegidos")],
                )
            )

        con.executemany(
            "INSERT INTO avisos (clave, nivel, titulo, detalle, destinos) VALUES (?,?,?,?,?)",
            [(c, n, t, d, json.dumps(dest, ensure_ascii=False)) for c, n, t, d, dest in avisos],
        )
        con.execute(
            "INSERT OR REPLACE INTO meta VALUES ('ultima_importacion', ?)", (datetime.now().strftime("%Y-%m-%d %H:%M"),)
        )

    # Resumen que ve el usuario en el aviso «Excel actualizado: N productos y M ofertas».
    return {
        "productos": len(productos),
        "empresas": len(empresas),
        "ofertas": len(ofertas),
        "por_comprar": len(por_comprar),
        "sin_oferta": len(sin_oferta),
        "avisos": len(avisos),
        "segundos": round(time.time() - t0, 2),
    }
