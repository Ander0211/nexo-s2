"""
RUTAS DE PRODUCTOS
==================
Una «ruta» es una dirección que la pantalla puede pedirle al servidor. Este archivo
atiende todo lo relacionado con productos:

    GET    /api/productos                  la lista de la pantalla principal (con filtros y páginas)
    GET    /api/productos/{cod}/ofertas    el podio: 1.ª, 2.ª, 3.ª oferta... (y las siguientes)
    PUT    /api/productos/{cod}/seleccion  elegir a mano otro proveedor
    DELETE /api/productos/{cod}/seleccion  volver a la mejor oferta
    GET    /api/catalogo                   buscador de productos (panel «Agregar oferta»)
    GET    /api/productos/{cod}            los datos de un producto (formulario «Cargar datos»)
    POST   /api/productos                  crear un producto a mano
    PUT    /api/productos/{cod}            cambiar un producto
    DELETE /api/productos/{cod}            eliminar un producto propio

Estas rutas casi no calculan nada: piden los cálculos a services/tablero.py y
services/ranking.py y solo se ocupan de recibir parámetros y armar la respuesta.
"""

import math
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..config import OFERTAS_POR_PAGINA
from ..database import get_db
from ..schemas import CantidadIn, ProductoEdit, ProductoIn, SeleccionIn
from ..services import catalogo, etiquetas, tablero
from ..services import ranking as rk
from ..services.normalizacion import clave_busqueda, codigo_empresa, sin_acentos

# prefix="/api": todas las rutas de este archivo empiezan con /api
router = APIRouter(prefix="/api", tags=["productos"])


def _producto(db: sqlite3.Connection, cod: str) -> sqlite3.Row:
    """Busca un producto por código. Si no existe, responde error 404 («no encontrado»).
    Las rutas de abajo la usan para validar el código antes de hacer cualquier cosa."""
    p = db.execute("SELECT * FROM productos WHERE cod = ?", (cod,)).fetchone()
    if not p:
        raise HTTPException(404, "Ese producto no existe en el catálogo.")
    return p


@router.get("/productos")
def listar(
    q: str = "",  # texto de búsqueda (código o descripción)
    # Los 5 filtros de los botones de la pantalla:
    filtro: Literal["por_comprar", "con_oferta", "sin_oferta", "elegidos", "nuevos", "todos"] = "por_comprar",
    empresa: str | None = None,  # código de proveedor (clic en el gráfico «Dónde comprar»)
    orden: Literal["inversion", "ahorro", "cantidad", "existencias", "precio", "descripcion", "proveedor", "codigo"] = "inversion",
    direccion: Literal["asc", "desc"] | None = None,  # de menor a mayor / de mayor a menor (None = la natural de ese orden)
    pagina: int = Query(1, ge=1),  # ge=1: mínimo página 1
    tam: int = Query(25, ge=1, le=100),  # productos por página (entre 1 y 100)
    db: sqlite3.Connection = Depends(get_db),
):
    """Lista de productos de la pantalla principal, ya filtrada, ordenada y paginada."""
    # 1) Calcula el tablero completo (cantidad, mejor oferta, total... de cada producto).
    items = tablero.construir_tablero(db)
    # 2) Aplica búsqueda, filtro de chips, proveedor y orden.
    filtrados = tablero.filtrar_y_ordenar(items, filtro, q, empresa, orden, direccion)
    # 3) Recorta la página pedida. Si piden una página que no existe, se usa la última.
    total = len(filtrados)
    paginas = max(1, math.ceil(total / tam))
    pagina = min(pagina, paginas)
    ini = (pagina - 1) * tam
    return {
        "total": total,
        "pagina": pagina,
        "paginas": paginas,
        "tam": tam,
        "items": [tablero.publico(i) for i in filtrados[ini : ini + tam]],
    }


@router.get("/productos/{cod}/ofertas")
def ofertas_de_producto(
    cod: str,
    desde: int = Query(0, ge=0),  # desde qué puesto empezar (0 = desde la mejor)
    limite: int = Query(OFERTAS_POR_PAGINA, ge=1, le=50),  # cuántas ofertas devolver
    db: sqlite3.Connection = Depends(get_db),
):
    """Ofertas ordenadas de la mejor a la peor. `desde`/`limite` permiten 'seguir adelante'
    con el botón: primera llamada desde=0 (1.ª, 2.ª y 3.ª), luego desde=3, desde=6, ..."""
    p = _producto(db, cod)
    # Ordena todas las ofertas del producto de la más barata a la más cara.
    ranking = rk.construir_ranking(tablero.ofertas_por_producto(db, cod).get(cod, []))
    # ¿El usuario eligió a mano un proveedor para este producto?
    sel = db.execute("SELECT cod_empresa FROM seleccion WHERE cod_producto = ?", (cod,)).fetchone()
    elegida, a_mano = rk.elegir(ranking, sel["cod_empresa"] if sel else None)
    calculada = rk.cantidad_a_comprar(p["stock_max"], p["existencias"])
    editadas = tablero.cantidades_editadas(db, cod)
    comprar = editadas.get(cod, calculada)  # la que fijó el usuario, si la hay
    # A quién se le compra cuánto (si el mejor no tiene unidades para todo, se reparte). La «principal» es a quien se le compra la mayor parte.
    plan = rk.repartir(comprar, ranking, elegida if a_mano else None)
    principal = plan["lineas"][0] if plan["lineas"] and not a_mano else elegida
    # «Tajada» = la porción de ofertas que se pidió (ej. puestos 4, 5 y 6).
    tajada = ranking[desde : desde + limite]
    etiquetas.sincronizar(db)
    empresas_nuevas = etiquetas.nuevos(db, "empresa")
    productos_nuevos = etiquetas.nuevos(db, "producto")
    for o in tajada:
        o["empresa_nueva"] = o["cod_empresa"] in empresas_nuevas  # la empresa es nueva: lleva la etiqueta «Nuevo»
        o["total"] = round(o["valor"] * comprar, 2)  # cuánto costaría comprar todo a este proveedor
        o["es_elegida"] = bool(principal) and o["cod_empresa"] == principal["cod_empresa"]
        disp = o.get("disponible")  # cuántas unidades dijo tener (None = no lo dijo)
        o["alcanza"] = disp is None or disp >= comprar  # ¿le alcanza para TODO lo que hay que comprar?
        o["faltan"] = 0 if disp is None else max(0, comprar - int(disp))
        o["eliminable"] = (
            o["origen"] in catalogo.ORIGENES_PROPIOS
        )  # solo las propias (a mano o subidas) se pueden borrar
    return {
        "cod": p["cod"],
        "descripcion": p["descripcion"],
        "comprar": comprar,
        "calculada": calculada,
        "editada": cod in editadas,
        "nuevo": cod in productos_nuevos,
        "existencias": p["existencias"],
        "stock_max": p["stock_max"],
        "stock_min": p["stock_min"],
        "total_ofertas": len(ranking),
        "desde": desde,
        "limite": limite,
        "restantes": max(len(ranking) - (desde + len(tajada)), 0),  # cuántas faltan por mostrar
        "hay_mas": desde + len(tajada) < len(ranking),  # ¿hay que mostrar el botón «Ver siguientes»?
        "elegida_a_mano": a_mano,
        # El reparto: normalmente una sola línea (el elegido, con todo); varias si el mejor no tiene unidades para todo.
        "reparto": [
            {
                k: ln.get(k)
                for k in (
                    "cod_empresa",
                    "empresa",
                    "valor",
                    "presentacion",
                    "origen",
                    "disponible",
                    "cantidad",
                    "subtotal",
                )
            }
            for ln in plan["lineas"]
        ],
        "repartido": plan["repartida"],
        "faltante": plan["faltante"],  # unidades que ningún proveedor puede entregar
        "excede_disponible": plan["excede"],  # (elegido a mano) pide más de lo que ese proveedor dijo tener
        "ofertas": tajada,
    }


@router.put("/productos/{cod}/seleccion")
def elegir_proveedor(cod: str, body: SeleccionIn, db: sqlite3.Connection = Depends(get_db)):
    """Elige a mano qué proveedor usar para este producto (si eliges el mejor, se quita la elección)."""
    _producto(db, cod)
    empresa = codigo_empresa(body.cod_empresa)
    ranking = rk.construir_ranking(tablero.ofertas_por_producto(db, cod).get(cod, []))
    # Solo se puede elegir un proveedor que realmente tenga una oferta para este producto.
    if not any(o["cod_empresa"] == empresa for o in ranking):
        raise HTTPException(422, "Ese proveedor no tiene una oferta para este producto.")
    with db:  # `with db` = transacción: o se guarda todo o no se guarda nada
        if ranking[0]["cod_empresa"] == empresa:
            # Eligió la mejor: no hace falta guardar nada, es el comportamiento por defecto.
            db.execute("DELETE FROM seleccion WHERE cod_producto = ?", (cod,))
        else:
            db.execute("INSERT OR REPLACE INTO seleccion (cod_producto, cod_empresa) VALUES (?, ?)", (cod, empresa))
    return {"ok": True, "a_mano": ranking[0]["cod_empresa"] != empresa}


@router.delete("/productos/{cod}/seleccion")
def quitar_eleccion(cod: str, db: sqlite3.Connection = Depends(get_db)):
    """Borra la elección manual: el producto vuelve a usar la oferta más barata."""
    _producto(db, cod)
    with db:
        db.execute("DELETE FROM seleccion WHERE cod_producto = ?", (cod,))
    return {"ok": True}


def _fila_del_tablero(db: sqlite3.Connection, cod: str) -> dict | None:
    """La fila del producto tal como la ve el tablero (la misma de GET /api/productos), ya con la cantidad vigente."""
    return next((tablero.publico(i) for i in tablero.construir_tablero(db) if i["cod"] == cod), None)


@router.put("/productos/{cod}/cantidad")
def editar_cantidad(cod: str, body: CantidadIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Fija a mano la cantidad a comprar de este producto: SOLO cuántas unidades se van a comprar. NO toca el stock máximo ni
    las existencias (la barra «3 en stock · máx 15» no cambia) ni ninguna de las 5 tablas. Vale hasta que se restaure (no la
    cambian las existencias, ni el recálculo, ni «Actualizar Excel»); cambia el total, los indicadores y las exportaciones.
    Responde también con la fila `item` ya recalculada, para que la pantalla la actualice en su sitio sin reordenar la lista."""
    p = _producto(db, cod)
    calculada = rk.cantidad_a_comprar(p["stock_max"], p["existencias"])
    usuario = getattr(request.state, "usuario", None)
    with db:
        db.execute(
            "INSERT INTO cantidades (cod_producto, cantidad, usuario) VALUES (?, ?, ?) ON CONFLICT(cod_producto) DO UPDATE "
            "SET cantidad = excluded.cantidad, usuario = excluded.usuario, fecha = datetime('now','localtime')",
            (cod, body.cantidad, usuario["usuario"] if usuario else None),
        )
    return {
        "cod": cod,
        "comprar": body.cantidad,
        "calculada": calculada,
        "editada": True,
        "item": _fila_del_tablero(db, cod),
    }


@router.delete("/productos/{cod}/cantidad")
def restaurar_cantidad(cod: str, db: sqlite3.Connection = Depends(get_db)):
    """Vuelve a la cantidad calculada (StockMax − Existencias): quita la que se había fijado a mano (tampoco toca el stock)."""
    p = _producto(db, cod)
    with db:
        db.execute("DELETE FROM cantidades WHERE cod_producto = ?", (cod,))
    calculada = rk.cantidad_a_comprar(p["stock_max"], p["existencias"])
    return {
        "cod": cod,
        "comprar": calculada,
        "calculada": calculada,
        "editada": False,
        "item": _fila_del_tablero(db, cod),
    }


@router.get("/catalogo")
def buscar_catalogo(q: str = "", limite: int = Query(12, ge=1, le=50), db: sqlite3.Connection = Depends(get_db)):
    """Buscador de productos (código o descripción) para la panel de agregar oferta."""
    # La búsqueda ignora tildes y mayúsculas, y cada palabra escrita debe aparecer en el producto.
    tokens = sin_acentos(q).lower().split()
    if not tokens:
        return []
    out = []
    for i in tablero.construir_tablero(db):
        if all(t in i["_busqueda"] for t in tokens):
            out.append(
                {
                    "cod": i["cod"],
                    "descripcion": i["descripcion"],
                    "comprar": i["comprar"],
                    "n_ofertas": i["n_ofertas"],
                    "mejor_valor": i["mejor"]["valor"] if i["mejor"] else None,
                }
            )
    # los códigos que empiezan igual que la búsqueda van primero
    out.sort(key=lambda r: (not clave_busqueda(r["cod"]).startswith(tokens[0]), r["descripcion"]))
    return out[:limite]


@router.get("/productos/{cod}")
def detalle_producto(cod: str, db: sqlite3.Connection = Depends(get_db)):
    """Los datos de UN producto, para rellenar el formulario de «Cargar datos» cuando el código ya existe."""
    p = _producto(db, cod)
    n_ofertas = db.execute("SELECT COUNT(*) FROM ofertas WHERE cod_producto = ?", (cod,)).fetchone()[0]
    return {
        "cod": p["cod"],
        "descripcion": p["descripcion"],
        "stock_max": p["stock_max"],
        "stock_med": p["stock_med"],
        "stock_min": p["stock_min"],
        "existencias": p["existencias"],
        "en_stock": bool(p["en_stock"]),
        "origen": p["origen"],
        "es_propio": p["origen"] in catalogo.ORIGENES_PROPIOS,  # ¿se puede eliminar?
        "n_ofertas": n_ofertas,
    }


@router.post("/productos", status_code=201)
def crear_producto(body: ProductoIn, db: sqlite3.Connection = Depends(get_db)):
    """Crea un producto a mano. `body` ya llega validado por schemas.ProductoIn.
    Si el código ya existe responde 409 (lo decide services/catalogo.py)."""
    with db:  # transacción: si algo falla no queda nada a medias
        return catalogo.crear_producto(
            db,
            body.cod,
            body.descripcion,
            stock_max=body.stock_max,
            stock_med=body.stock_med,
            stock_min=body.stock_min,
            existencias=body.existencias,
        )


@router.put("/productos/{cod}")
def editar_producto(cod: str, body: ProductoEdit, db: sqlite3.Connection = Depends(get_db)):
    """Cambia SOLO los campos que se enviaron (model_fields_set = los que venían en la petición)."""
    cambios = {c: getattr(body, c) for c in body.model_fields_set if c in catalogo.CAMPOS_PRODUCTO}
    with db:
        cambio = catalogo.actualizar_producto(db, cod, cambios)
    return {"ok": True, "cambio": cambio}


@router.delete("/productos/{cod}")
def eliminar_producto(cod: str, db: sqlite3.Connection = Depends(get_db)):
    """Elimina un producto propio (a mano o subido). Los del Excel base responden 409."""
    with db:
        catalogo.eliminar_producto(db, cod)
    return {"ok": True}
