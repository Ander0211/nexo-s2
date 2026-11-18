"""SENTINEL PABON — usuarios, roles y sesiones.

Roles:
  administrador  hace todo: cargar inventario, configurar la fuente, verificar (ENVIAR) y gestionar usuarios.
  revisor        solo consulta: ve tableros, inventario, análisis y el registro de verificaciones.
                 NO carga inventarios, NO cambia la fuente y NO verifica/aprueba (ENVIAR).

SUPERUSUARIO (igual que en SUMIPABON): un administrador cuya clave se define en el archivo .env
  (SENTINEL_SUPERUSUARIO y SENTINEL_SUPERUSUARIO_CLAVE; si no están, usa COMPRAS_SUPERUSUARIO y COMPRAS_SUPERUSUARIO_CLAVE
  de SUMIPABON). Se crea o se corrige en cada arranque y no se puede editar, desactivar, eliminar ni cambiar su clave desde
  la pantalla: para cambiarle la clave se cambia en el .env y se reinicia.

Las cuentas se guardan en datos/usuarios.json con la clave cifrada (PBKDF2-SHA256, nunca en texto plano).
La carpeta datos/ no se publica en el navegador. Solo usa librerías que vienen con Python.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

import notificaciones as aviso

ROOT = Path(__file__).resolve().parent
DATOS = ROOT / "datos"
ARCHIVO = DATOS / "usuarios.json"
AUDITORIA = DATOS / "auditoria.log"

ROLES = ("administrador", "revisor")
COOKIE = "sentinel_sesion"
DURACION_SESION = 12 * 3600          # 12 horas
ITERACIONES = 200_000
MAX_FALLOS = 5
BLOQUEO = 5 * 60                     # 5 minutos tras 5 claves erradas
CLAVE_MIN = 8

_LOCK = threading.Lock()
_SESIONES: dict[str, dict] = {}      # token -> {"usuario", "expira"}
_FALLOS: dict[str, list] = {}        # usuario -> [intentos, bloqueado_hasta]


class ErrorUsuario(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


# ------------------------------------------------------------------ almacenamiento

def _leer() -> dict:
    if not ARCHIVO.exists():
        return {}
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except Exception:
        return {}


def _guardar(usuarios: dict) -> None:
    DATOS.mkdir(exist_ok=True)
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(usuarios, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ARCHIVO)


def auditar(usuario: str, accion: str, detalle: str = "") -> None:
    """Deja constancia de quién hizo cada acción importante (datos/auditoria.log)."""
    try:
        DATOS.mkdir(exist_ok=True)
        linea = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {usuario or '-'} | {accion}"
        if detalle:
            linea += f" | {detalle}"
        with open(AUDITORIA, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception:
        pass


# ------------------------------------------------------------------ claves

def _hash(clave: str, sal: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, ITERACIONES).hex()


def _nueva_clave(clave: str) -> dict:
    if len(clave or "") < CLAVE_MIN:
        raise ErrorUsuario(f"La clave debe tener al menos {CLAVE_MIN} caracteres.")
    sal = secrets.token_bytes(16)
    return {"sal": sal.hex(), "hash": _hash(clave, sal)}


def _clave_correcta(registro: dict, clave: str) -> bool:
    try:
        esperado = registro["hash"]
        calculado = _hash(clave or "", bytes.fromhex(registro["sal"]))
        return hmac.compare_digest(esperado, calculado)
    except Exception:
        return False


def _coincide(registro: dict, clave: str) -> bool:
    """¿Es su clave? Acepta también la clave con espacios o saltos de línea al inicio/final (pasa al copiarla y
    pegarla desde el correo o WhatsApp). Ninguna clave válida empieza o termina en espacio."""
    clave = clave or ""
    return _clave_correcta(registro, clave) or (clave.strip() != clave and _clave_correcta(registro, clave.strip()))


def _era_temporal_anterior(registro: dict, clave: str) -> bool:
    """¿Es una clave temporal que ya fue reemplazada por «Nueva clave»?"""
    return any(_coincide(vieja, clave) for vieja in registro.get("anteriores", []))


def _limpiar_usuario(u: str) -> str:
    u = (u or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", u):
        raise ErrorUsuario("El usuario debe tener de 3 a 30 letras, números, punto, guion o guion bajo (sin espacios ni tildes).")
    return u


def _publico(u: str, r: dict) -> dict:
    return {"usuario": u, "nombre": r.get("nombre", u), "rol": r.get("rol"), "activo": r.get("activo", True),
            "superusuario": bool(r.get("superusuario")),
            "correo": r.get("correo"), "celular": r.get("celular"), "debe_cambiar": bool(r.get("temporal")),  # clave enviada por correo/WhatsApp: al primer ingreso debe elegir la suya
            "creado": r.get("creado"), "ultimo_ingreso": r.get("ultimo_ingreso")}


def clave_temporal() -> str:
    """10 caracteres al azar, con letras y números, sin los que se confunden (l/I/O/0)."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    while True:
        c = "".join(secrets.choice(alfabeto) for _ in range(10))
        if re.search(r"[A-Za-z]", c) and re.search(r"\d", c):
            return c


def _contacto(usuarios: dict, correo, celular, propio: str | None = None) -> tuple[str, str]:
    """Correo y celular obligatorios, válidos y sin repetir con otra persona."""
    try:
        correo = aviso.normalizar_correo(correo)
        celular = aviso.normalizar_celular(celular)
    except ValueError as e:
        raise ErrorUsuario(str(e))
    if not correo:
        raise ErrorUsuario("El correo es obligatorio (allí se le envía su usuario y clave).")
    if not celular:
        raise ErrorUsuario("El celular / WhatsApp es obligatorio (allí se le envía su usuario y clave).")
    for u, r in usuarios.items():
        if u == propio:
            continue
        if r.get("correo") == correo:
            raise ErrorUsuario(f"Ese correo ya lo tiene el usuario {u}.", 409)
        if r.get("celular") == celular:
            raise ErrorUsuario(f"Ese celular ya lo tiene el usuario {u}.", 409)
    return correo, celular


def _admins_activos(usuarios: dict) -> list[str]:
    return [u for u, r in usuarios.items() if r.get("rol") == "administrador" and r.get("activo", True)]


# ------------------------------------------------------------------ superusuario (definido en el .env)

def validar_clave(clave: str, usuario: str) -> None:
    clave = clave or ""
    if not (CLAVE_MIN <= len(clave) <= 128):
        raise ErrorUsuario(f"La clave debe tener de {CLAVE_MIN} a 128 caracteres.")
    if not (re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", clave) and re.search(r"\d", clave)):
        raise ErrorUsuario("La clave debe tener letras y números.")
    if clave.lower() == (usuario or "").lower():
        raise ErrorUsuario("La clave no puede ser igual al usuario.")


def _exigir_no_superusuario(r: dict, u: str, que: str) -> None:
    if r.get("superusuario"):
        raise ErrorUsuario(f"«{u}» es el superusuario: {que}. Se define en el archivo .env "
                           "(SENTINEL_SUPERUSUARIO y SENTINEL_SUPERUSUARIO_CLAVE).", 409)


def asegurar_superusuario(usuario: str | None, clave: str | None) -> str | None:
    """Deja creado y en regla el SUPERUSUARIO: un administrador activo con la clave del .env. Se llama en cada arranque,
    así que el .env manda: si alguien le cambió la clave, el rol o lo desactivó, vuelve a quedar como en el .env.
    Devuelve «creado», «actualizado» o «igual». Sin clave no hay superusuario: devuelve None y quita la protección
    (la cuenta sigue existiendo como administrador normal). El mensaje de error nunca trae la clave."""
    with _LOCK:
        usuarios = _leer()
        if not clave:
            cambio = False
            for r in usuarios.values():
                if r.pop("superusuario", None):
                    cambio = True
            if cambio:
                _guardar(usuarios)
            return None
        u = (usuario or "superadmin").strip().lower()
        if not re.fullmatch(r"[a-z0-9._-]{3,30}", u):
            raise ErrorUsuario("El nombre del superusuario debe tener de 3 a 30 letras sin tilde, números, punto, guion o guion bajo.")
        validar_clave(clave, u)
        for otro, r in usuarios.items():  # solo hay un superusuario: el del .env
            if otro != u:
                r.pop("superusuario", None)
        r = usuarios.get(u)
        if r is None:
            usuarios[u] = {"nombre": "Superusuario", "rol": "administrador", "activo": True, "superusuario": True,
                           "correo": None, "celular": None,
                           "creado": datetime.now().isoformat(timespec="seconds"), **_nueva_clave(clave)}
            resultado = "creado"
        else:
            clave_igual = _clave_correcta(r, clave)
            en_regla = clave_igual and r.get("rol") == "administrador" and r.get("activo", True) and r.get("superusuario")
            resultado = "igual"
            if not en_regla:
                if not clave_igual:
                    r.update(_nueva_clave(clave))
                if not clave_igual or r.get("rol") != "administrador" or not r.get("activo", True):
                    _cerrar_sesiones_de(u)  # cambió la clave o el perfil: las sesiones viejas dejan de valer
                r.update({"rol": "administrador", "activo": True, "superusuario": True})
                r.pop("temporal", None)
                r.pop("anteriores", None)
                resultado = "actualizado"
        _FALLOS.pop(u, None)
        _guardar(usuarios)
    if resultado != "igual":
        auditar(u, f"superusuario {resultado} desde el .env")
    return resultado


# ------------------------------------------------------------------ estado / primer administrador

def configurado() -> bool:
    return bool(_admins_activos(_leer()))


def crear_primer_admin(usuario: str, nombre: str, clave: str, correo=None, celular=None) -> dict:
    with _LOCK:
        usuarios = _leer()
        if _admins_activos(usuarios):
            raise ErrorUsuario("Ya existe un administrador. Ingrese con su usuario.", 409)
        u = _limpiar_usuario(usuario)
        try:
            correo, celular = aviso.normalizar_correo(correo), aviso.normalizar_celular(celular)
        except ValueError as e:
            raise ErrorUsuario(str(e))
        usuarios[u] = {"nombre": (nombre or u).strip()[:60], "rol": "administrador", "activo": True,
                       "correo": correo, "celular": celular,
                       "creado": datetime.now().isoformat(timespec="seconds"), **_nueva_clave(clave)}
        _guardar(usuarios)
    auditar(u, "primer administrador creado")
    return _publico(u, usuarios[u])


# ------------------------------------------------------------------ sesiones

def iniciar_sesion(usuario: str, clave: str) -> tuple[str, dict]:
    u = (usuario or "").strip().lower()
    ahora = time.time()
    with _LOCK:
        fallos = _FALLOS.get(u, [0, 0.0])
        if fallos[1] > ahora:
            minutos = int((fallos[1] - ahora) // 60) + 1
            raise ErrorUsuario(f"Demasiados intentos. Espere {minutos} min y vuelva a intentar.", 429)
        usuarios = _leer()
        r = usuarios.get(u)
        if not (r and _coincide(r, clave)):
            fallos[0] += 1
            if fallos[0] >= MAX_FALLOS:
                fallos = [0, ahora + BLOQUEO]
            _FALLOS[u] = fallos
            if r and _era_temporal_anterior(r, clave):
                auditar(u, "intento con una clave temporal ya reemplazada")
                raise ErrorUsuario("Esa clave ya no sirve: después se generó una más nueva con «Nueva clave». "
                                   "Use la del ÚLTIMO correo o WhatsApp que recibió.", 401)
            auditar(u, "intento fallido", "usuario no existe" if not r else "clave incorrecta")
            raise ErrorUsuario("Usuario o clave incorrectos.", 401)
        if not r.get("activo", True):
            raise ErrorUsuario("Este usuario está desactivado. Hable con un administrador.", 403)
        _FALLOS.pop(u, None)
        r["ultimo_ingreso"] = datetime.now().isoformat(timespec="seconds")
        _guardar(usuarios)
        token = secrets.token_urlsafe(32)
        _SESIONES[token] = {"usuario": u, "expira": ahora + DURACION_SESION}
        # limpieza de sesiones vencidas
        for t in [t for t, s in _SESIONES.items() if s["expira"] < ahora]:
            _SESIONES.pop(t, None)
    auditar(u, "ingresó")
    return token, _publico(u, r)


def cerrar_sesion(token: str | None) -> None:
    if token:
        with _LOCK:
            s = _SESIONES.pop(token, None)
        if s:
            auditar(s["usuario"], "salió")


def usuario_de(token: str | None) -> dict | None:
    """El usuario de esa sesión (leído de nuevo del archivo: si lo desactivan o le cambian el rol, aplica al instante)."""
    if not token:
        return None
    with _LOCK:
        s = _SESIONES.get(token)
        if not s or s["expira"] < time.time():
            _SESIONES.pop(token, None)
            return None
        r = _leer().get(s["usuario"])
        if not r or not r.get("activo", True):
            _SESIONES.pop(token, None)
            return None
        return _publico(s["usuario"], r)


def _cerrar_sesiones_de(usuario: str) -> None:
    for t in [t for t, s in _SESIONES.items() if s["usuario"] == usuario]:
        _SESIONES.pop(t, None)


# ------------------------------------------------------------------ gestión (solo administrador)

def listar() -> list[dict]:
    usuarios = _leer()
    return sorted((_publico(u, r) for u, r in usuarios.items()),
                  key=lambda x: (not x["superusuario"], x["rol"] != "administrador", x["usuario"]))


def cambiar_mi_clave(usuario: str, actual: str, nueva: str) -> None:
    with _LOCK:
        usuarios = _leer()
        r = usuarios.get(usuario)
        if r:
            _exigir_no_superusuario(r, usuario, "su clave se cambia en el archivo .env y se aplica al reiniciar")
        if not r or not _coincide(r, actual):
            raise ErrorUsuario("La clave actual no es correcta.", 403)
        if (nueva or "") == (actual or "").strip():
            raise ErrorUsuario("La clave nueva debe ser distinta de la actual.")
        if (nueva or "").lower() == usuario.lower():
            raise ErrorUsuario("La clave no puede ser igual al usuario.")
        r.update(_nueva_clave(nueva))
        r.pop("temporal", None)
        r.pop("anteriores", None)
        _guardar(usuarios)
    auditar(usuario, "cambió su clave")


def crear(quien: str, payload: dict) -> tuple[dict, str]:
    """Crea un usuario con una clave temporal automática (al primer ingreso elige la suya). Devuelve (usuario, clave)."""
    with _LOCK:
        usuarios = _leer()
        u = _limpiar_usuario(payload.get("usuario"))
        if u in usuarios:
            raise ErrorUsuario("Ese usuario ya existe.", 409)
        rol = payload.get("rol")
        if rol not in ROLES:
            raise ErrorUsuario("Rol no válido.")
        nombre = " ".join(str(payload.get("nombre") or "").split())[:60]
        if not nombre:
            raise ErrorUsuario("Escriba el nombre de la persona.")
        correo, celular = _contacto(usuarios, payload.get("correo"), payload.get("celular"))
        clave = clave_temporal()
        usuarios[u] = {"nombre": nombre, "rol": rol, "activo": True, "correo": correo, "celular": celular, "temporal": True,
                       "creado": datetime.now().isoformat(timespec="seconds"), **_nueva_clave(clave)}
        _guardar(usuarios)
    auditar(quien, "usuarios: crear", f"{u} ({rol})")
    return _publico(u, usuarios[u]), clave


def restablecer(quien: str, usuario: str) -> tuple[dict, str]:
    """Clave temporal nueva automática (al entrar elige una propia); cierra sus sesiones."""
    with _LOCK:
        usuarios = _leer()
        u = str(usuario or "").strip().lower()
        r = usuarios.get(u)
        if not r:
            raise ErrorUsuario("Ese usuario no existe.", 404)
        _exigir_no_superusuario(r, u, "su clave no se restablece desde la pantalla")
        clave = clave_temporal()
        # la clave anterior queda reemplazada: se recuerda su huella para avisar si alguien la usa
        r["anteriores"] = ([{"sal": r["sal"], "hash": r["hash"]}] + r.get("anteriores", []))[:3]
        r.update(_nueva_clave(clave))
        r["temporal"] = True  # al entrar con ella, debe elegir una clave nueva
        _FALLOS.pop(u, None)
        _cerrar_sesiones_de(u)
        _guardar(usuarios)
    auditar(quien, "usuarios: clave nueva", u)
    return _publico(u, r), clave


def gestionar(quien: str, payload: dict) -> list[dict]:
    """Cambiar rol, activar/desactivar, editar datos (nombre, correo, celular) o eliminar."""
    accion = str(payload.get("accion") or "")
    with _LOCK:
        usuarios = _leer()
        u = str(payload.get("usuario") or "").strip().lower()
        r = usuarios.get(u)
        if not r:
            raise ErrorUsuario("Ese usuario no existe.", 404)
        _exigir_no_superusuario(r, u, "no se puede eliminar" if accion == "eliminar" else "no se modifica desde la pantalla")
        if accion == "rol":
            rol = payload.get("rol")
            if rol not in ROLES:
                raise ErrorUsuario("Rol no válido.")
            if u == quien and rol != "administrador":
                raise ErrorUsuario("No puede quitarse a sí mismo el rol de administrador.")
            r["rol"] = rol
            detalle = f"{u} -> {rol}"
        elif accion == "activo":
            activo = bool(payload.get("activo"))
            if u == quien and not activo:
                raise ErrorUsuario("No puede desactivarse a sí mismo.")
            r["activo"] = activo
            if not activo:
                _cerrar_sesiones_de(u)
            detalle = f"{u} {'activado' if activo else 'desactivado'}"
        elif accion == "datos":
            nombre = " ".join(str(payload.get("nombre") or "").split())[:60]
            if not nombre:
                raise ErrorUsuario("Escriba el nombre de la persona.")
            r["nombre"] = nombre
            r["correo"], r["celular"] = _contacto(usuarios, payload.get("correo"), payload.get("celular"), propio=u)
            detalle = u
        elif accion == "eliminar":
            if u == quien:
                raise ErrorUsuario("No puede eliminarse a sí mismo.")
            usuarios.pop(u)
            _cerrar_sesiones_de(u)
            detalle = u
        else:
            raise ErrorUsuario("Acción no válida.")
        if not _admins_activos(usuarios):
            raise ErrorUsuario("Debe quedar al menos un administrador activo.")
        _guardar(usuarios)
    auditar(quien, f"usuarios: {accion}", detalle)
    return listar()
