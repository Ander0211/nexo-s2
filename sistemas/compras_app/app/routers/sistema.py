"""
RUTAS DEL SISTEMA
=================
Funciones generales que no son de un producto en particular:

    GET  /api/salud             ¿el servidor está vivo?
    GET  /api/resumen           los 4 números grandes de arriba + inversión por proveedor
    GET  /api/avisos            problemas detectados en los Excel (menú «Avisos de datos»), con a dónde llevar al usuario
    POST /api/importar          volver a leer los Excel (botón «Actualizar Excel»)
    GET  /api/exportar/oc       la ORDEN DE COMPRA con el proveedor ganador de cada producto (botón «Descargar OC»)
    GET  /api/exportar/alternativas  el 2.º, 3.º y 4.º proveedor de cada producto, una hoja por puesto (botón «Alternativas 2.º a 4.º»)
"""

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..database import get_db
from ..services import admin, exportador, importador, tablero

router = APIRouter(prefix="/api", tags=["sistema"])


@router.get("/salud")
def salud():
    """Prueba de vida: si responde {"ok": true}, el servidor está funcionando."""
    return {"ok": True}


@router.get("/resumen")
def resumen(db: sqlite3.Connection = Depends(get_db)):
    """KPIs (productos por comprar, inversión, ahorro...), conteos de los filtros y gráfico por proveedor."""
    return tablero.resumen(db, tablero.construir_tablero(db))


@router.get("/avisos")
def avisos(db: sqlite3.Connection = Depends(get_db)):
    """Avisos de calidad de datos; los importantes (warn) primero. Cada uno trae sus botones «Ir a corregir» (`destinos`)."""
    return admin.avisos(db)


@router.post("/importar")
def importar(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Vuelve a leer los Excel de data/excel/. Lo agregado a mano se conserva."""
    usuario = getattr(request.state, "usuario", None)
    try:
        return importador.importar(db, usuario=usuario["usuario"] if usuario else None)
    except importador.ImportacionError as e:
        # Falta un archivo o una columna: se responde 422 con un mensaje claro para el usuario.
        raise HTTPException(422, str(e)) from None


@router.get("/exportar/productos-a-comprar")
def exportar_productos_a_comprar(db: sqlite3.Connection = Depends(get_db)):
    """Excel con los productos que hay que comprar (solo administrador y Prime; el perfil «Consulta» ya no lo descarga)."""
    return Response(
        exportador.productos_a_comprar_xlsx(db),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="PRODUCTOS_A_COMPRAR.xlsx"'},
    )


@router.get("/exportar/oc")
def exportar_oc(db: sqlite3.Connection = Depends(get_db)):
    """La ORDEN DE COMPRA (formato OC.xlsm) con el proveedor ganador de cada producto por comprar."""
    return Response(
        exportador.oc_xlsx(db),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="OC_{date.today().isoformat()}.xlsx"'},
    )


@router.get("/exportar/alternativas")
def exportar_alternativas(db: sqlite3.Connection = Depends(get_db)):
    """Libro con el 2.º, 3.º y 4.º proveedor de cada producto por comprar, una hoja por puesto, con el formato de la orden de compra."""
    return Response(
        exportador.alternativas_xlsx(db),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ALTERNATIVAS_2_a_4_{date.today().isoformat()}.xlsx"'},
    )
