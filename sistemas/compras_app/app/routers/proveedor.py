"""
RUTAS DEL PROVEEDOR EXTERNO
===========================
Lo ÚNICO que puede usar un usuario «externo» (ver la tabla POLITICA en services/seguridad.py). El administrador ve las dos primeras
(para ver la pantalla tal como la ve el proveedor); subir y ver los envíos es solo del proveedor:

    GET  /api/proveedor/productos   los productos que la Clínica necesita comprar: código y descripción
    GET  /api/proveedor/lista/{grupo}  solo los «sin_oferta» o «nuevos» (las ventanas de sus dos botones), con búsqueda
    GET  /api/proveedor/excel       esos mismos productos como la ficha FR-GDS-07 para que el proveedor escriba su precio (?grupo= y ?q= la reducen)
    POST /api/proveedor/ofertas     SUBE su ficha con precios: queda PENDIENTE hasta que el administrador la apruebe (services/pendientes.py)
    GET  /api/proveedor/ofertas     las fichas que él ha enviado y su estado (nunca precios de otros)

NUNCA salen precios, ofertas de otros proveedores, existencias ni stock: el proveedor solo debe saber QUÉ y CUÁNTO se
necesita. Por eso cada producto se arma campo por campo aquí (no se reenvía el diccionario completo del tablero).
"""

import math
import re
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from ..database import get_db
from ..services import cargas, exportador, pendientes, tablero

router = APIRouter(prefix="/api/proveedor", tags=["proveedor externo"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


Grupo = Literal["sin_oferta", "nuevos"]


def _pagina(items: list[dict], pagina: int, tam: int) -> dict:
    """Una página de la lista con SOLO código y descripción. Nada de precios ni de otros proveedores."""
    tam = max(10, min(int(tam), 200))
    paginas = max(1, math.ceil(len(items) / tam))
    pagina = max(1, min(int(pagina), paginas))
    pedazo = items[(pagina - 1) * tam : pagina * tam]
    return {
        "total": len(items),
        "pagina": pagina,
        "paginas": paginas,
        "tam": tam,
        "items": [{"cod": i["cod"], "descripcion": i["descripcion"]} for i in pedazo],
    }


@router.get("/productos")
def productos(q: str = "", pagina: int = 1, tam: int = 50, db: sqlite3.Connection = Depends(get_db)):
    """Los productos por comprar (todos, tengan o no oferta), de la A a la Z, con búsqueda y paginación. Trae también cuántos hay «sin oferta» y
    «nuevos» (los números de los dos botones de su pantalla)."""
    todos = tablero.construir_tablero(db)
    r = _pagina(tablero.para_proveedor(todos, None, q), pagina, tam)
    r["conteos"] = {g: len(tablero.para_proveedor(todos, g)) for g in ("sin_oferta", "nuevos")}
    return r


@router.get("/lista/{grupo}")
def lista(grupo: Grupo, q: str = "", pagina: int = 1, tam: int = 50, db: sqlite3.Connection = Depends(get_db)):
    """Solo los productos «sin_oferta» (nadie los ha cotizado) o «nuevos», con búsqueda y paginación: lo que muestran sus ventanas."""
    return _pagina(tablero.para_proveedor(tablero.construir_tablero(db), grupo, q), pagina, tam)


@router.get("/excel")
def excel(request: Request, grupo: Grupo | None = None, q: str = "", db: sqlite3.Connection = Depends(get_db)):
    """El Excel para cotizar: la FICHA DE SOLICITUD DE COTIZACIÓN (FR-GDS-07) con el código y la descripción de cada producto por comprar,
    para que el proveedor llene su precio, IVA y unidad de empaque. Sin cantidades."""
    u = request.state.usuario
    empresa = {"cod": u["cod_empresa"], "nombre": u["empresa"]} if u["cod_empresa"] else None
    nombre = re.sub(r"[^A-Za-z0-9_-]+", "_", (empresa or {}).get("nombre") or u["usuario"]).strip("_")
    return Response(
        exportador.cotizacion_xlsx(db, empresa, grupo, q),
        media_type=XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="FR-GDS-07_Ficha_Cotizacion_{nombre}{"_" + grupo.upper() if grupo else ""}.xlsx"'
        },
    )


def _cod_empresa(request: Request) -> str:
    cod = request.state.usuario["cod_empresa"]
    if not cod:
        raise HTTPException(409, "Tu usuario no está ligado a un proveedor.")
    return cod


@router.post("/ofertas", status_code=201)
async def enviar_oferta(request: Request, nombre: str = "", db: sqlite3.Connection = Depends(get_db)):
    """El proveedor sube su ficha con precios (el archivo va como cuerpo de la petición, igual que en «Cargar datos»). Siempre queda a nombre de SU
    proveedor y PENDIENTE: no compite hasta que el administrador la apruebe. Responde con el resumen para mostrárselo (sin precios de nadie más)."""
    cod = _cod_empresa(request)
    tamano = request.headers.get("content-length", "")
    if (
        tamano.isdigit() and int(tamano) > cargas.MAX_BYTES + 4096
    ):  # si el navegador avisa el tamaño, se rechaza sin leer todo el archivo
        raise HTTPException(
            413, f"El archivo es demasiado grande: el máximo es {cargas.MAX_BYTES // (1024 * 1024)} MB."
        )
    contenido = await request.body()
    try:  # leer el Excel es trabajo pesado: se hace en un hilo aparte para no dejar bloqueado al servidor
        return await run_in_threadpool(
            pendientes.guardar_subida, db, cod, request.state.usuario["usuario"], contenido, nombre
        )
    except (
        cargas.CargaError
    ) as e:  # un archivo que no sirve (no es Excel, muy grande, sin columnas...) se explica, no se cae
        raise HTTPException(e.estado, e.mensaje) from None


@router.get("/ofertas")
def mis_ofertas(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Las fichas que ha enviado este proveedor, con su estado (pendiente, aprobada o rechazada y, si la hay, la razón)."""
    return pendientes.mis_lotes(db, _cod_empresa(request))
