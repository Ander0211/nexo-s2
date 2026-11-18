"""
RUTA DE LOS TABLEROS DE CONTROL
===============================
    GET /api/control      las tres vistas (empresas con menores valores, precios más baratos, productos que más consumen)

Parámetros (todos opcionales): top (cuántos renglones por vista), empresa (código de proveedor: filtro cruzado), min_productos (mínimo de
productos que debe cotizar un proveedor para entrar en el ranking), precios (porcentaje | valor), consumo (cantidad | inversion | stock_max).
Los cálculos están en services/control.py.
"""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..services import control

router = APIRouter(prefix="/api", tags=["control"])


@router.get("/control")
def tableros_de_control(
    top: int = Query(10, ge=3, le=30),  # renglones por vista
    empresa: str | None = None,  # código de proveedor (clic en una barra de «Empresas con menores valores»)
    min_productos: int = Query(1, ge=1, le=50),
    precios: Literal["porcentaje", "valor"] = "porcentaje",
    consumo: Literal["cantidad", "inversion", "stock_max"] = "cantidad",
    db: sqlite3.Connection = Depends(get_db),
):
    """Las tres vistas de los tableros de control, calculadas con los datos de hoy."""
    if (
        empresa
        and not db.execute(
            "SELECT 1 FROM empresas WHERE cod = ? UNION SELECT 1 FROM ofertas WHERE cod_empresa = ?", (empresa, empresa)
        ).fetchone()
    ):
        raise HTTPException(404, "Ese proveedor no existe.")
    return control.construir_control(db, top, empresa or None, min_productos, precios, consumo)
