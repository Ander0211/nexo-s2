"""
REVISIÓN DE PERMISOS EN CADA PETICIÓN
=====================================
`autorizar` es una «dependencia» de FastAPI que se aplica a TODA la aplicación (ver main.py): antes de ejecutar cualquier
ruta de /api, mira la cookie de sesión, busca el usuario y comprueba en la tabla POLITICA (services/seguridad.py) si su
perfil puede hacer esa petición. Si no: 401 (no ha iniciado sesión) o 403 (no tiene permiso) y la ruta ni siquiera corre.

Además:
  - deja el usuario en `request.state.usuario` para las rutas que lo necesiten (por ejemplo, anotarlo en el historial);
  - si el usuario debe cambiar su clave (clave temporal), solo le deja usar las rutas de sesión hasta que la cambie;
  - en peticiones que cambian datos (POST, PUT, DELETE) rechaza las que vienen de OTRA página web (cabecera Origin distinta
    de este servidor): junto con la cookie SameSite=Lax, evita que un sitio ajeno use tu sesión (ataque CSRF).
Las páginas y archivos de la interfaz (/ y /static) son públicos: no contienen datos, solo el «esqueleto» de la pantalla.
"""

import os
import sqlite3
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request, Response

from .database import get_db
from .services import seguridad

COOKIE = "sesion"


def poner_cookie(response: Response, token: str) -> None:
    """Guarda el token de sesión en una cookie que el JavaScript de la página NO puede leer (HttpOnly).
    Si la aplicación se publica con https, define COMPRAS_COOKIE_SEGURA=1 para que la cookie solo viaje cifrada."""
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(seguridad.DURACION_SESION.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=os.environ.get("COMPRAS_COOKIE_SEGURA") == "1",
        path="/",
    )


def autorizar(request: Request, db: sqlite3.Connection = Depends(get_db)) -> None:
    """La revisión de cada petición (ver arriba). Lanza 401 o 403 si no corresponde."""
    request.state.usuario = None
    request.state.token = None
    ruta, metodo = request.url.path, request.method
    if not ruta.startswith("/api"):
        return  # la interfaz (HTML, CSS, JS, imágenes): pública
    if metodo in ("POST", "PUT", "DELETE", "PATCH"):
        origen = request.headers.get("origin")
        if origen and urlparse(origen).netloc != request.headers.get("host"):
            raise HTTPException(403, "Petición de origen no permitido.")
    token = request.cookies.get(COOKIE)
    usuario = seguridad.usuario_de_token(db, token)
    request.state.usuario, request.state.token = usuario, token
    permitidos = seguridad.roles_permitidos(metodo, ruta)
    if permitidos == seguridad.PUBLICO:
        return
    if usuario is None:
        raise HTTPException(401, "Inicia sesión para continuar.")
    if usuario["cambiar_clave"] and not seguridad.es_ruta_de_sesion(metodo, ruta):
        raise HTTPException(403, "Debes cambiar tu clave antes de continuar.")
    if usuario["rol"] not in permitidos:
        raise HTTPException(403, "No tienes permiso para hacer esto.")
