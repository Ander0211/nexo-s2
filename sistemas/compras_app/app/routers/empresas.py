"""
RUTAS DE PROVEEDORES
====================
    GET    /api/empresas/{cod}/ficha  todo lo del proveedor (contacto, ofertas, cuánto se le compra): se abre al pulsar su nombre
    GET    /api/empresas        lista de proveedores (desplegables de las paneles «Agregar oferta» y «Cargar datos»)
    POST   /api/empresas        crear un proveedor a mano
    PUT    /api/empresas/{cod}  cambiar el nombre de un proveedor
    DELETE /api/empresas/{cod}  eliminar un proveedor propio que no tenga ofertas
"""

import sqlite3

from fastapi import APIRouter, Depends

from ..database import get_db
from ..schemas import EmpresaEdit, EmpresaIn
from ..services import catalogo, etiquetas, fichas
from ..services.normalizacion import codigo_empresa

router = APIRouter(prefix="/api", tags=["empresas"])


@router.get("/empresas")
def listar_empresas(db: sqlite3.Connection = Depends(get_db)):
    """Todos los proveedores ordenados por nombre, con cuántas ofertas tiene cada uno."""
    # LEFT JOIN: incluye también los proveedores que aún no tienen ninguna oferta (ofertas = 0).
    filas = db.execute(
        "SELECT e.cod, e.nombre, e.origen, COUNT(o.id) AS ofertas FROM empresas e "
        "LEFT JOIN ofertas o ON o.cod_empresa = e.cod GROUP BY e.cod ORDER BY lower(e.nombre)"
    ).fetchall()
    etiquetas.sincronizar(db)
    nuevas = etiquetas.nuevos(db, "empresa")
    return [{**dict(f), "nuevo": f["cod"] in nuevas} for f in filas]


@router.get("/empresas/{cod}/ficha")
def ficha_de_la_empresa(cod: str, db: sqlite3.Connection = Depends(get_db)):
    """La ficha del proveedor: contacto, cuántas ofertas tiene, cuántas son la mejor, cuánto se le compraría y su lista
    de ofertas. La puede ver todo el que ve el tablero (incluido el perfil Consulta)."""
    return fichas.ficha_empresa(db, cod)


@router.post("/empresas", status_code=201)
def crear_empresa(body: EmpresaIn, db: sqlite3.Connection = Depends(get_db)):
    """Crea un proveedor a mano. Sin código se le asigna uno (desde 1000). 409 si el nombre o el código ya existen."""
    with db:
        return catalogo.crear_empresa(db, body.nombre, body.cod)


@router.put("/empresas/{cod}")
def editar_empresa(cod: str, body: EmpresaEdit, db: sqlite3.Connection = Depends(get_db)):
    """Cambia el nombre de un proveedor (el código no cambia)."""
    with db:
        cambio = catalogo.actualizar_empresa(db, codigo_empresa(cod) or cod, body.nombre)
    return {"ok": True, "cambio": cambio}


@router.delete("/empresas/{cod}")
def eliminar_empresa(cod: str, db: sqlite3.Connection = Depends(get_db)):
    """Elimina un proveedor propio con todos los insumos cotizados; el tablero busca la siguiente oferta más baja. Los del Excel base responden 409."""
    from ..services import importador

    with db:
        n = catalogo.eliminar_empresa(db, codigo_empresa(cod) or cod)
    importador.recalcular(db)
    return {"ok": True, "ofertas_eliminadas": n}
