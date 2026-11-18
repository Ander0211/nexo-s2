"""
RUTAS DE USUARIOS (solo administrador)
======================================
    GET    /api/usuarios              lista (y qué canales de envío están configurados)
    POST   /api/usuarios              crear; devuelve la clave temporal UNA sola vez y la envía por correo/WhatsApp
    PUT    /api/usuarios/{id}         cambiar nombre, perfil, proveedor, correo, celular o estado
    POST   /api/usuarios/{id}/clave   restablecer la clave (temporal nueva UNA sola vez; también se envía)
    POST   /api/usuarios/{id}/activo  activar o desactivar (desactivado no puede entrar; sus sesiones se cierran)
    DELETE /api/usuarios/{id}         eliminar
Las reglas (no quedarse sin administradores, etc.) están en services/seguridad.py.
"""

import sqlite3

from fastapi import APIRouter, Depends, Request

from ..database import get_db
from ..schemas import UsuarioActivoIn, UsuarioEdit, UsuarioIn
from ..services import admin, notificaciones, seguridad

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


def _direccion(request: Request) -> str:
    """La dirección que va en el mensaje: COMPRAS_URL_PUBLICA si existe; si no, la que usó el administrador.
    Siempre abre la pantalla de ingreso (pide usuario y clave)."""
    return notificaciones.enlace_de_ingreso(notificaciones.url_publica() or str(request.base_url))


def _proveedor_del_usuario(db, rol: str, cod_empresa: str | None, nuevo, actor: str) -> tuple[str | None, dict | None]:
    """Si el usuario es un proveedor (externo) y su proveedor NO está en la lista, lo agrega (a Administración → Empresas, con teléfono y correo
    obligatorios y sin repetir uno que ya existe) y devuelve su código para ligarlo. Devuelve (código, proveedor creado o None)."""
    if nuevo is None or rol != "externo" or (cod_empresa or "").strip():
        return cod_empresa, None
    creado = admin.crear_empresa_con_contacto(db, nuevo.nombre, nuevo.telefono, nuevo.correo, actor)
    return creado["cod"], creado


@router.get("")
def listar(db: sqlite3.Connection = Depends(get_db)):
    """Todos los usuarios (nunca incluye claves)."""
    return {"usuarios": seguridad.listar(db), "perfiles": seguridad.ROLES, "canales": notificaciones.canales()}


@router.post("", status_code=201)
def crear(body: UsuarioIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Crea un usuario con clave temporal (la debe cambiar al entrar). El correo y el celular son obligatorios.
    La clave se muestra solo esta vez y además se envía por correo y WhatsApp (el resultado de cada envío viene en `envio`)."""
    cod_empresa, proveedor_nuevo = body.cod_empresa, None
    if body.empresa_nueva is not None and body.rol == "externo" and not (body.cod_empresa or "").strip():
        # Primero se revisa que el usuario se pueda crear, para no dejar un proveedor nuevo «a medias» si luego fallara el usuario.
        seguridad.comprobar_nuevo(db, body.usuario, body.correo, body.celular)
        cod_empresa, proveedor_nuevo = _proveedor_del_usuario(
            db, body.rol, body.cod_empresa, body.empresa_nueva, request.state.usuario["usuario"]
        )
    usuario, clave = seguridad.crear(
        db,
        body.usuario,
        body.nombre,
        body.rol,
        cod_empresa,
        correo=body.correo,
        celular=body.celular,
        contacto_obligatorio=True,
    )
    envio = notificaciones.enviar_credenciales(usuario, clave, _direccion(request))
    return {"usuario": usuario, "clave_temporal": clave, "envio": envio, "proveedor_nuevo": proveedor_nuevo}


@router.put("/{usuario_id}")
def editar(usuario_id: int, body: UsuarioEdit, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Cambia nombre, perfil, proveedor, correo, celular y si está activo (correo y celular son obligatorios)."""
    actor = request.state.usuario["id"]
    cod_empresa, proveedor_nuevo = _proveedor_del_usuario(
        db, body.rol, body.cod_empresa, body.empresa_nueva, request.state.usuario["usuario"]
    )
    return {
        "proveedor_nuevo": proveedor_nuevo,
        "usuario": seguridad.editar(
            db,
            usuario_id,
            body.nombre,
            body.rol,
            cod_empresa,
            body.activo,
            actor,
            body.correo,
            body.celular,
            contacto_obligatorio=True,
        ),
    }


@router.post("/{usuario_id}/clave")
def restablecer(usuario_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Le pone una clave temporal nueva, cierra sus sesiones y se la envía por correo/WhatsApp si tiene esos datos."""
    usuario, clave = seguridad.restablecer_clave(db, usuario_id)
    envio = notificaciones.enviar_credenciales(usuario, clave, _direccion(request), restablecida=True)
    return {"usuario": usuario, "clave_temporal": clave, "envio": envio}


@router.post("/{usuario_id}/activo")
def activar(usuario_id: int, body: UsuarioActivoIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Activa o desactiva el usuario sin cambiar sus demás datos."""
    return {"usuario": seguridad.cambiar_activo(db, usuario_id, body.activo, request.state.usuario["id"])}


@router.delete("/{usuario_id}")
def eliminar(usuario_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Elimina un usuario (no a uno mismo ni al último administrador)."""
    seguridad.eliminar(db, usuario_id, request.state.usuario["id"])
    return {"ok": True}
