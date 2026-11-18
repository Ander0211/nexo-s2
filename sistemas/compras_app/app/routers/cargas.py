"""
RUTAS DE CARGA DE EXCEL
=======================
    POST /api/cargas/{tipo}      sube un Excel/CSV de productos, proveedores o cotizaciones
    GET  /api/plantillas/{tipo}  descarga la plantilla en blanco de ese tipo

`tipo` es «productos», «proveedores» o «cotizaciones».

Cómo se sube el archivo: el navegador envía el archivo tal cual como cuerpo de la petición (bytes), y su nombre
va en la dirección (?nombre=cotizacion.xlsx). Se hizo así, en vez de con formulario multipart, para no depender de
una librería adicional.

Parámetros de POST /api/cargas/{tipo}:
    nombre         nombre del archivo (para saber si es .xlsx o .csv)
    aplicar        false = solo REVISAR y contar (no escribe nada) · true = CARGAR de verdad
    cod_empresa    (solo cotizaciones) proveedor existente al que pertenece el archivo
    empresa_nueva  (solo cotizaciones) nombre de un proveedor nuevo que se crea al cargar
El trabajo real está en services/cargas.py; esta ruta solo recibe los bytes y traduce los errores.
"""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from ..database import get_db
from ..services import cargas, exportador, plantillas

router = APIRouter(prefix="/api", tags=["cargas"])

Tipo = Literal["productos", "proveedores", "cotizaciones"]


@router.post("/cargas/{tipo}")
async def subir_archivo(
    tipo: Tipo,
    request: Request,
    nombre: str = "",
    aplicar: bool = False,
    cod_empresa: str | None = None,
    empresa_nueva: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    """Revisa (aplicar=false) o carga (aplicar=true) el archivo subido y devuelve el resultado con los conteos."""
    # Si el navegador avisa el tamaño antes de enviar, se rechaza sin leer todo el archivo.
    tamano = request.headers.get("content-length", "")
    if tamano.isdigit() and int(tamano) > cargas.MAX_BYTES + 4096:
        raise HTTPException(
            413, f"El archivo es demasiado grande: el máximo es {cargas.MAX_BYTES // (1024 * 1024)} MB."
        )
    contenido = await request.body()
    try:
        # Leer el Excel y escribir en la base es trabajo «pesado»: se hace en un hilo aparte para no
        # dejar bloqueado al servidor mientras tanto.
        return await run_in_threadpool(
            cargas.procesar, db, tipo, contenido, nombre, aplicar, cod_empresa, empresa_nueva
        )
    except cargas.CargaError as e:
        raise HTTPException(e.estado, e.mensaje) from None


@router.get("/plantillas/{tipo}")
def descargar_plantilla(tipo: Tipo, db: sqlite3.Connection = Depends(get_db)):
    """La plantilla del tipo pedido. La de COTIZACIONES es la ficha oficial FR-GDS-07 (con los productos por comprar y sin datos de proveedor);
    las demás son la hoja DATOS vacía + una hoja de instrucciones."""
    if tipo == "cotizaciones":
        return Response(
            exportador.cotizacion_xlsx(db, None),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="FR-GDS-07_Ficha_Cotizacion.xlsx"'},
        )
    return Response(
        plantillas.plantilla_xlsx(tipo),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="PLANTILLA_{tipo.upper()}.xlsx"'},
    )
