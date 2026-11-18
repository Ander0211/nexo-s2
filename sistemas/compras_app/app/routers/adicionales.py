"""
RUTAS DE «ADICIONALES»: código y descripción de productos → Proveedor 1, 2 y 3 con su menor valor
==================================================================================================
    GET    /api/adicionales             la lista con los 3 proveedores más baratos de cada producto
    POST   /api/adicionales             agregar productos escritos a mano: {"filas": [{"cod": ..., "descripcion": ...}]}
    POST   /api/adicionales/archivo     subir un Excel/CSV con CÓDIGO y DESCRIPCIÓN (el archivo va como cuerpo)
    POST   /api/adicionales/{id}/activo inhabilitar (se ve en rojo, no se borra) o habilitar: {"activo": false|true}
    DELETE /api/adicionales/{id}        quitar un producto de la lista
    DELETE /api/adicionales             vaciar la lista
    GET    /api/adicionales/excel       descargar la lista con los proveedores
    GET    /api/adicionales/plantilla   Excel vacío con las columnas CÓDIGO y DESCRIPCIÓN
La lógica está en services/adicionales.py. Ver: administrador, prime y consulta. Cambiar la lista: administrador y prime.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..database import get_db
from ..services import adicionales

router = APIRouter(prefix="/api/adicionales", tags=["adicionales"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Fila(BaseModel):
    cod: str
    descripcion: str | None = None


class FilasIn(BaseModel):
    filas: list[Fila]


class ActivoIn(BaseModel):
    activo: bool


def _usuario(request: Request) -> str | None:
    u = getattr(request.state, "usuario", None)
    return u["usuario"] if u else None


@router.get("")
def lista(db: sqlite3.Connection = Depends(get_db)):
    return adicionales.listar(db)


@router.post("")
def agregar(body: FilasIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    try:
        r = adicionales.agregar(db, [f.model_dump() for f in body.filas][: adicionales.MAX_FILAS], _usuario(request))
    except adicionales.AdicionalesError as e:
        raise HTTPException(e.estado, e.mensaje) from None
    return {**r, **adicionales.listar(db)}


@router.post("/archivo")
async def subir(request: Request, nombre: str = "", db: sqlite3.Connection = Depends(get_db)):
    tamano = request.headers.get("content-length", "")
    if tamano.isdigit() and int(tamano) > adicionales.MAX_BYTES + 4096:
        raise HTTPException(413, f"El archivo es demasiado grande: el máximo es {adicionales.MAX_BYTES // 1048576} MB.")
    contenido = await request.body()
    try:
        filas = await run_in_threadpool(adicionales.leer_archivo, contenido, nombre)
        r = adicionales.agregar(db, filas, _usuario(request))
    except adicionales.AdicionalesError as e:
        raise HTTPException(e.estado, e.mensaje) from None
    return {**r, **adicionales.listar(db)}


@router.get("/excel")
def descargar(db: sqlite3.Connection = Depends(get_db)):
    return Response(adicionales.excel(db), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="Adicionales_proveedores.xlsx"'})


@router.get("/plantilla")
def plantilla():
    return Response(adicionales.plantilla(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="Plantilla_Adicionales.xlsx"'})


@router.post("/{id_}/activo")
def activo(id_: int, body: ActivoIn, db: sqlite3.Connection = Depends(get_db)):
    try:
        adicionales.cambiar_activo(db, id_, body.activo)
    except adicionales.AdicionalesError as e:
        raise HTTPException(e.estado, e.mensaje) from None
    return adicionales.listar(db)


@router.delete("/{id_}")
def quitar(id_: int, db: sqlite3.Connection = Depends(get_db)):
    try:
        adicionales.eliminar(db, id_)
    except adicionales.AdicionalesError as e:
        raise HTTPException(e.estado, e.mensaje) from None
    return adicionales.listar(db)


@router.delete("")
def vaciar(db: sqlite3.Connection = Depends(get_db)):
    return {"eliminados": adicionales.vaciar(db), **adicionales.listar(db)}
