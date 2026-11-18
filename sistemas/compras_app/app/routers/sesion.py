"""
RUTAS DE SESIÓN
===============
    POST   /api/sesion         entrar (usuario y clave) → deja la cookie de sesión
    GET    /api/sesion         ¿quién soy? (la pantalla lo pregunta al abrir para saber qué mostrar)
    DELETE /api/sesion         salir
    PUT    /api/sesion/clave   cambiar mi propia clave
El trabajo real está en services/seguridad.py; los permisos los revisa autorizacion.py.
"""

import sqlite3

from fastapi import APIRouter, Depends, Request, Response

from ..autorizacion import COOKIE, poner_cookie
from ..database import get_db
from ..schemas import ClaveIn, LoginIn
from ..services import seguridad

router = APIRouter(prefix="/api", tags=["sesión"])


@router.post("/sesion")
def entrar(body: LoginIn, response: Response, db: sqlite3.Connection = Depends(get_db)):
    """Valida usuario y clave; si son correctos deja la cookie de sesión. El mensaje de error no dice cuál falló."""
    token, usuario = seguridad.ingresar(db, body.usuario, body.clave)
    poner_cookie(response, token)
    return {"usuario": usuario}


@router.get("/sesion")
def quien_soy(request: Request):
    """El usuario de la sesión actual (401 si no hay sesión)."""
    return {"usuario": seguridad.publico(request.state.usuario)}


@router.delete("/sesion")
def salir(request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    """Cierra la sesión (en el servidor y en la cookie)."""
    seguridad.cerrar_sesion(db, request.state.token)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.put("/sesion/clave")
def cambiar_mi_clave(body: ClaveIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Cambia la clave del usuario de la sesión (pide la actual). Cierra sus otras sesiones."""
    u = request.state.usuario
    return {"usuario": seguridad.cambiar_clave(db, u["id"], body.actual, body.nueva, request.state.token)}
