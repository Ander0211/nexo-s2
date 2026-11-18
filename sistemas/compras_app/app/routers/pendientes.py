"""
RUTAS DE LAS OFERTAS PENDIENTES (solo el administrador)
=======================================================
Revisar las fichas que los proveedores han subido (services/pendientes.py): ver cada una frente a la mejor oferta de hoy, aprobarla o rechazarla.

    GET  /api/pendientes                  los lotes (primero los pendientes); ?estado= pendiente | aprobada | rechazada
    GET  /api/pendientes/{id}             un lote con cada producto frente a la mejor oferta actual
    POST /api/pendientes/{id}/aprobar     sus precios pasan a competir en el tablero
    GET  /api/pendientes/{id}/excel       la ficha como Excel (cada precio frente a la mejor oferta de hoy)
    POST /api/pendientes/{id}/rechazar    sus precios no entran; el MOTIVO es obligatorio: se le envía al proveedor por correo y lo ve en su pantalla
"""

import sqlite3

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from ..database import get_db
from ..services import notificaciones, pendientes

router = APIRouter(prefix="/api/pendientes", tags=["ofertas pendientes"])


class MotivoIn(BaseModel):
    motivo: str = Field(default="", max_length=300)


@router.get("")
def listar(estado: str | None = None, db: sqlite3.Connection = Depends(get_db)):
    return pendientes.listar_lotes(db, estado)


@router.get("/{lote_id}")
def ver(lote_id: int, db: sqlite3.Connection = Depends(get_db)):
    return pendientes.detalle(db, lote_id)


@router.get("/{lote_id}/excel")
def excel(lote_id: int, db: sqlite3.Connection = Depends(get_db)):
    """La ficha de un proveedor como Excel (cada precio frente a la mejor oferta de hoy)."""
    contenido, nombre = pendientes.excel_lote(db, lote_id)
    return Response(
        contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post("/{lote_id}/aprobar")
def aprobar(lote_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    url = notificaciones.enlace_de_ingreso(
        notificaciones.url_publica() or str(request.base_url)
    )  # a dónde entra el proveedor a ver el estado de sus fichas
    return pendientes.aprobar(db, lote_id, request.state.usuario["usuario"], url)


@router.post("/{lote_id}/rechazar")
def rechazar(lote_id: int, cuerpo: MotivoIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    url = notificaciones.enlace_de_ingreso(
        notificaciones.url_publica() or str(request.base_url)
    )  # a dónde vuelve el proveedor a corregir
    return pendientes.rechazar(db, lote_id, request.state.usuario["usuario"], cuerpo.motivo, url)


@router.post("/{lote_id}/restaurar")
def restaurar(lote_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Deshace la aprobación o el rechazo y deja la ficha otra vez PENDIENTE DE REVISIÓN (si estaba aprobada, devuelve también las ofertas)."""
    return pendientes.restaurar(db, lote_id, request.state.usuario["usuario"])
