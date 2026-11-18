"""
SEGURIDAD: USUARIOS, CLAVES, SESIONES Y PERMISOS
================================================
Quién puede entrar y qué puede hacer cada uno. Hay CUATRO perfiles:

    admin      Administrador   todo, incluida la pantalla «Administración» y la gestión de usuarios
    prime      Prime           todo lo del menú EXCEPTO «Administración» (tablero, agregar oferta, cargar datos,
                               actualizar Excel, exportar VALORES, avisos)
    consulta   Consulta        solo VER el tablero y descargar el Excel de los productos por comprar. No edita nada.
    externo    Proveedor       solo ve los productos que la Clínica necesita comprar (sin precios ni ofertas) y
               externo         descarga ese Excel para cotizar

Cómo se protege (lo importante, en orden):
  1. CLAVES: nunca se guardan; solo su «huella» (scrypt con sal propia). Mínimo 8 caracteres con letras y números.
  2. SESIÓN: al entrar se crea un «token» al azar que viaja en una cookie HttpOnly (el JavaScript de la página no puede
     leerla). En la base solo se guarda la huella del token. Dura 12 horas y se puede cerrar desde «Salir».
  3. PERMISOS EN EL SERVIDOR: cada ruta de la API está en la tabla POLITICA de abajo. Esconder un botón no basta, por eso
     el servidor revisa el perfil en CADA petición. Lo que no está en la tabla se niega a todos menos al administrador.
  4. INTENTOS: 5 claves incorrectas seguidas bloquean el usuario 5 minutos. El mensaje no dice si el usuario existe.
  5. CLAVE TEMPORAL: la del primer administrador y las que crea o restablece el administrador obligan a cambiarla al entrar.
  6. No se puede dejar el sistema sin administrador (no se elimina, desactiva ni degrada al último).
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta

ROLES = {"admin": "Administrador", "prime": "Prime", "consulta": "Consulta", "externo": "Proveedor externo"}
DURACION_SESION = timedelta(hours=12)
MAX_INTENTOS = 5
BLOQUEO = timedelta(minutes=5)
_FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"
_N_SCRYPT = 2**14  # costo de la huella: ≈50 ms por clave (lo bastante lento para frenar adivinadores, sin molestar)


class SeguridadError(Exception):
    """Un problema de seguridad o de usuarios (clave incorrecta, sin permiso...). Lleva el código HTTP que corresponde."""

    def __init__(self, mensaje: str, estado: int = 422):
        super().__init__(mensaje)
        self.mensaje, self.estado = mensaje, estado


def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _texto(f: datetime) -> str:
    return f.strftime(_FORMATO_FECHA)


# ============================================================================================ claves
def hashear(clave: str) -> str:
    """La «huella» de una clave, con una sal al azar: dos usuarios con la misma clave tienen huellas distintas."""
    sal = os.urandom(16)
    h = hashlib.scrypt(clave.encode(), salt=sal, n=_N_SCRYPT, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)
    return f"scrypt${_N_SCRYPT}${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}"


def verificar(clave: str, guardada: str) -> bool:
    """¿Esta clave corresponde a la huella guardada? (comparación de tiempo constante)."""
    try:
        _, n, sal, esperada = guardada.split("$")
        h = hashlib.scrypt(
            clave.encode(), salt=base64.b64decode(sal), n=int(n), r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024
        )
        return hmac.compare_digest(h, base64.b64decode(esperada))
    except (ValueError, TypeError):
        return False


_HUELLA_FALSA = hashear(
    "clave-falsa-0"
)  # para gastar el mismo tiempo cuando el usuario no existe (no delatar cuáles existen)


def validar_clave(clave: str, usuario: str | None = None) -> None:
    """Reglas de una clave nueva: 8 a 128 caracteres, con letras y números, y distinta del usuario."""
    if len(clave) < 8:
        raise SeguridadError("La clave debe tener al menos 8 caracteres.")
    if len(clave) > 128:
        raise SeguridadError("La clave es demasiado larga (máximo 128 caracteres).")
    if not re.search(r"[A-Za-z]", clave) or not re.search(r"\d", clave):
        raise SeguridadError("La clave debe tener letras y números.")
    if usuario and clave.lower() == usuario.lower():
        raise SeguridadError("La clave no puede ser igual al usuario.")


def clave_temporal() -> str:
    """Una clave al azar de 10 caracteres (sin letras que se confunden, como l/I/O/0) con letras y números."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    while True:
        c = "".join(secrets.choice(alfabeto) for _ in range(10))
        if re.search(r"[A-Za-z]", c) and re.search(r"\d", c):
            return c


# ============================================================================================ usuarios
def publico(u: sqlite3.Row | dict) -> dict:
    """El usuario como lo ve la pantalla. NUNCA incluye la huella de la clave."""
    return {
        "id": u["id"],
        "usuario": u["usuario"],
        "nombre": u["nombre"],
        "rol": u["rol"],
        "rol_nombre": ROLES[u["rol"]],
        "cod_empresa": u["cod_empresa"],
        "correo": u["correo"],
        "celular": u["celular"],
        "empresa": u["empresa"] if "empresa" in u.keys() else None,
        "activo": bool(u["activo"]),
        "cambiar_clave": bool(u["cambiar_clave"]),
        "ultimo_ingreso": u["ultimo_ingreso"],
        "creado": u["creado"],
        "protegido": False,  # True solo para el superusuario definido en .env (lo marca `listar`)
    }


_SELECT = "SELECT u.*, e.nombre AS empresa FROM usuarios u LEFT JOIN empresas e ON e.cod = u.cod_empresa"


def listar(con: sqlite3.Connection) -> list[dict]:
    """Todos los usuarios, los administradores primero."""
    filas = con.execute(
        _SELECT
        + " ORDER BY CASE u.rol WHEN 'admin' THEN 0 WHEN 'prime' THEN 1 WHEN 'consulta' THEN 2 ELSE 3 END, u.usuario"
    ).fetchall()
    protegido = superusuario_protegido(con)
    usuarios = [publico(f) for f in filas]
    for u in usuarios:
        u["protegido"] = u["usuario"] == protegido
    return usuarios


def _obtener(con: sqlite3.Connection, usuario_id: int) -> sqlite3.Row:
    u = con.execute(_SELECT + " WHERE u.id = ?", (usuario_id,)).fetchone()
    if u is None:
        raise SeguridadError("Ese usuario ya no existe.", 404)
    return u


def normalizar_correo(correo: str | None) -> str | None:
    """Correo limpio en minúsculas, o None si se dejó vacío. Lanza SeguridadError si no parece un correo."""
    correo = (correo or "").strip().lower()
    if not correo:
        return None
    if len(correo) > 120 or not re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]{2,}", correo):
        raise SeguridadError("El correo no es válido. Escríbelo así: nombre@dominio.com")
    return correo


def normalizar_celular(celular: str | None) -> str | None:
    """Celular como «+57300…» (solo dígitos tras el +), o None si se dejó vacío.
    Acepta «300 123 4567», «3001234567», «57 300 123 4567» o «+57 300 123 4567»; un número de 10 dígitos que empieza
    por 3 se toma como colombiano. Para otro país hay que escribir el indicativo con «+»."""
    bruto = (celular or "").strip()
    if not bruto:
        return None
    digitos = re.sub(r"[\s().-]", "", bruto)
    con_mas = digitos.startswith("+")
    digitos = digitos.lstrip("+")
    if not digitos.isdigit():
        raise SeguridadError("El celular solo puede llevar números (y un + al inicio para el indicativo).")
    if len(digitos) == 10 and digitos.startswith("3"):
        digitos = "57" + digitos
    elif not ((len(digitos) == 12 and digitos.startswith("57")) or (con_mas and 8 <= len(digitos) <= 15)):
        raise SeguridadError(
            "El celular no es válido. Escribe los 10 dígitos (ej. 300 123 4567) o con indicativo (+57…)."
        )
    return "+" + digitos


def exigir_contacto(correo: str | None, celular: str | None) -> None:
    """Desde la pantalla de Usuarios el correo y el celular son OBLIGATORIOS (así siempre hay a dónde enviar la clave)."""
    if not (correo or "").strip():
        raise SeguridadError("El correo es obligatorio.")
    if not (celular or "").strip():
        raise SeguridadError("El celular es obligatorio.")


def _exigir_contacto_unico(
    con: sqlite3.Connection, correo: str | None, celular: str | None, actual: sqlite3.Row | None = None
) -> None:
    """Dos personas no pueden tener el mismo correo ni el mismo celular. Al EDITAR solo se revisa lo que cambió (así un
    contacto que ya estaba repetido de antes no impide seguir editando a esa persona)."""
    id_actual = actual["id"] if actual is not None else None
    for campo, valor, nombre in (("correo", correo, "el correo"), ("celular", celular, "el celular")):
        if not valor or (actual is not None and actual[campo] == valor):
            continue
        otro = con.execute(
            f"SELECT usuario FROM usuarios WHERE {campo} = ? AND id IS NOT ?",
            (valor, id_actual),  # noqa: S608
        ).fetchone()
        if otro:
            raise SeguridadError(f"Ya hay un usuario con {nombre} {valor} («{otro['usuario']}»).", 409)


def _validar_datos(
    con, usuario: str | None, nombre: str, rol: str, cod_empresa: str | None, exigir_empresa: bool = True
) -> str | None:
    """Revisa nombre, perfil y proveedor. Devuelve el código de proveedor limpio (o None).

    Un usuario «externo» (proveedor) DEBE estar ligado a una empresa: sin ella no puede subir su oferta ni se sabe a nombre de quién cotiza. Si su
    proveedor no está en la lista, se agrega al crear el usuario (routers/usuarios.py → `empresa_nueva`) y entonces llega aquí ya con su código."""
    if not nombre.strip():
        raise SeguridadError("El nombre es obligatorio.")
    if rol not in ROLES:
        raise SeguridadError(f"El perfil debe ser uno de: {', '.join(ROLES)}.")
    cod_empresa = (cod_empresa or "").strip() or None
    if cod_empresa and rol != "externo":
        raise SeguridadError("Solo un usuario externo se liga a un proveedor.")
    if cod_empresa and not con.execute("SELECT 1 FROM empresas WHERE cod = ?", (cod_empresa,)).fetchone():
        raise SeguridadError(f"El proveedor {cod_empresa} no existe.")
    if rol == "externo" and exigir_empresa and not cod_empresa:
        raise SeguridadError(
            "Un usuario proveedor debe estar ligado a un proveedor: elige uno de la lista o agrega uno nuevo.",
            422,
        )
    return cod_empresa


def _admins_activos(con: sqlite3.Connection, excepto: int | None = None) -> int:
    return con.execute(
        "SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND activo = 1 AND id IS NOT ?", (excepto,)
    ).fetchone()[0]


def comprobar_nuevo(con: sqlite3.Connection, usuario: str, correo: str | None, celular: str | None) -> None:
    """Revisa que un usuario NUEVO se pueda crear (formato del usuario, contacto completo, que no exista y que su correo y celular sean únicos)
    SIN crearlo. Sirve para no dejar un proveedor creado «a medias» si luego falla el usuario que se iba a ligar a él."""
    exigir_contacto(correo, celular)
    usuario = usuario.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", usuario):
        raise SeguridadError(
            "El usuario debe tener de 3 a 40 caracteres: letras sin tilde, números, punto, guion o guion bajo."
        )
    if con.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (usuario,)).fetchone():
        raise SeguridadError(f"Ya existe el usuario «{usuario}».", 409)
    _exigir_contacto_unico(con, normalizar_correo(correo), normalizar_celular(celular))


def crear(
    con: sqlite3.Connection,
    usuario: str,
    nombre: str,
    rol: str,
    cod_empresa: str | None = None,
    clave: str | None = None,
    correo: str | None = None,
    celular: str | None = None,
    contacto_obligatorio: bool = False,
) -> tuple[dict, str]:
    """Crea un usuario. Sin `clave`, se genera una temporal y el usuario deberá cambiarla al entrar.
    Devuelve (usuario, clave con la que puede entrar): es la única vez que se ve en claro."""
    if contacto_obligatorio:
        exigir_contacto(correo, celular)
    usuario = usuario.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", usuario):
        raise SeguridadError(
            "El usuario debe tener de 3 a 40 caracteres: letras sin tilde, números, punto, guion o guion bajo."
        )
    cod_empresa = _validar_datos(con, usuario, nombre, rol, cod_empresa)
    correo, celular = normalizar_correo(correo), normalizar_celular(celular)
    if con.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (usuario,)).fetchone():
        raise SeguridadError(f"Ya existe el usuario «{usuario}».", 409)
    _exigir_contacto_unico(con, correo, celular)
    temporal = clave is None
    clave = clave or clave_temporal()
    validar_clave(clave, usuario)
    cur = con.execute(
        "INSERT INTO usuarios (usuario, nombre, clave_hash, rol, cod_empresa, correo, celular, cambiar_clave)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (usuario, " ".join(nombre.split()), hashear(clave), rol, cod_empresa, correo, celular, int(temporal)),
    )
    con.commit()
    return publico(_obtener(con, cur.lastrowid)), clave


def editar(
    con: sqlite3.Connection,
    usuario_id: int,
    nombre: str,
    rol: str,
    cod_empresa: str | None,
    activo: bool,
    actor_id: int,
    correo: str | None = None,
    celular: str | None = None,
    contacto_obligatorio: bool = False,
) -> dict:
    """Cambia nombre, perfil, proveedor y si está activo. Reglas: nadie se quita a sí mismo el perfil de administrador
    ni se desactiva (quedaría fuera), y siempre debe quedar al menos un administrador activo."""
    if contacto_obligatorio:
        exigir_contacto(correo, celular)
    u = _obtener(con, usuario_id)
    _exigir_no_protegido(con, u, "no se modifica desde la pantalla")
    cod_empresa = _validar_datos(
        con, u["usuario"], nombre, rol, cod_empresa, exigir_empresa=activo
    )  # un proveedor que se desactiva puede quedar sin empresa
    correo, celular = normalizar_correo(correo), normalizar_celular(celular)
    _exigir_contacto_unico(con, correo, celular, actual=u)
    if usuario_id == actor_id and (rol != u["rol"] or not activo):
        raise SeguridadError("No puedes cambiar tu propio perfil ni desactivarte: pídeselo a otro administrador.", 409)
    if u["rol"] == "admin" and (rol != "admin" or not activo) and _admins_activos(con, excepto=usuario_id) == 0:
        raise SeguridadError("Debe quedar al menos un administrador activo.", 409)
    con.execute(
        "UPDATE usuarios SET nombre = ?, rol = ?, cod_empresa = ?, correo = ?, celular = ?, activo = ? WHERE id = ?",
        (" ".join(nombre.split()), rol, cod_empresa, correo, celular, int(activo), usuario_id),
    )
    if rol != u["rol"] or not activo:
        cerrar_sesiones(con, usuario_id)  # el cambio de perfil o la desactivación valen YA, no cuando venza la sesión
    con.commit()
    return publico(_obtener(con, usuario_id))


def cambiar_activo(con: sqlite3.Connection, usuario_id: int, activo: bool, actor_id: int) -> dict:
    """Activar o desactivar (sin tocar sus demás datos). Desactivado no puede entrar y sus sesiones se cierran ya.
    Mismas reglas que al editar: nadie se desactiva a sí mismo y siempre queda al menos un administrador activo."""
    u = _obtener(con, usuario_id)
    _exigir_no_protegido(con, u, "no se modifica desde la pantalla")
    if usuario_id == actor_id and not activo:
        raise SeguridadError("No puedes desactivarte a ti mismo: pídeselo a otro administrador.", 409)
    if u["rol"] == "admin" and not activo and u["activo"] and _admins_activos(con, excepto=usuario_id) == 0:
        raise SeguridadError("Debe quedar al menos un administrador activo.", 409)
    con.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (int(activo), usuario_id))
    if not activo:
        cerrar_sesiones(con, usuario_id)
    con.commit()
    return publico(_obtener(con, usuario_id))


def restablecer_clave(con: sqlite3.Connection, usuario_id: int) -> tuple[dict, str]:
    """Le pone una clave temporal nueva (la que debe cambiar al entrar), cierra sus sesiones y lo desbloquea."""
    u = _obtener(con, usuario_id)
    _exigir_no_protegido(con, u, "su clave no se restablece desde la pantalla")
    temporal = clave_temporal()
    con.execute(
        "UPDATE usuarios SET clave_hash = ?, cambiar_clave = 1, intentos = 0, bloqueado_hasta = NULL WHERE id = ?",
        (hashear(temporal), usuario_id),
    )
    cerrar_sesiones(con, usuario_id)
    con.commit()
    return publico(_obtener(con, u["id"])), temporal


def eliminar(con: sqlite3.Connection, usuario_id: int, actor_id: int) -> None:
    """Elimina un usuario (y sus sesiones). No a uno mismo ni al último administrador."""
    u = _obtener(con, usuario_id)
    _exigir_no_protegido(con, u, "no se puede eliminar")
    if usuario_id == actor_id:
        raise SeguridadError("No puedes eliminar tu propio usuario.", 409)
    if u["rol"] == "admin" and u["activo"] and _admins_activos(con, excepto=usuario_id) == 0:
        raise SeguridadError("Debe quedar al menos un administrador activo.", 409)
    con.execute("DELETE FROM sesiones WHERE usuario_id = ?", (usuario_id,))
    con.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    con.commit()


def cambiar_clave(con: sqlite3.Connection, usuario_id: int, actual: str, nueva: str, token: str | None) -> dict:
    """El propio usuario cambia su clave (debe saber la actual). Se cierran sus OTRAS sesiones."""
    u = _obtener(con, usuario_id)
    _exigir_no_protegido(con, u, "su clave se cambia en el archivo .env y se aplica al reiniciar")
    actual = actual or ""
    # la clave temporal se suele pegar desde el correo/WhatsApp con un espacio o salto de línea al final
    if not verificar(actual, u["clave_hash"]):
        if actual.strip() != actual and verificar(actual.strip(), u["clave_hash"]):
            actual = actual.strip()
        else:
            raise SeguridadError("La clave actual no es correcta.", 403)
    if actual == nueva:
        raise SeguridadError("La clave nueva debe ser distinta de la actual.")
    validar_clave(nueva, u["usuario"])
    con.execute("UPDATE usuarios SET clave_hash = ?, cambiar_clave = 0 WHERE id = ?", (hashear(nueva), usuario_id))
    cerrar_sesiones(con, usuario_id, conservar=token)
    con.commit()
    return publico(_obtener(con, usuario_id))


def asegurar_administrador(con: sqlite3.Connection) -> str | None:
    """Si todavía no hay NINGÚN usuario, crea el administrador inicial («admin»). Devuelve la clave temporal para
    mostrarla en la terminal (o None si ya había usuarios).

    Con la variable de entorno COMPRAS_ADMIN_CLAVE se usa esa clave y no se obliga a cambiarla (para pruebas y despliegues
    automáticos). Sin ella, se genera una temporal al azar que hay que cambiar en el primer ingreso."""
    if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
        return None
    fija = os.environ.get("COMPRAS_ADMIN_CLAVE")
    _, clave = crear(con, "admin", "Administrador", "admin", clave=fija or None)
    if fija:
        con.execute("UPDATE usuarios SET cambiar_clave = 0 WHERE usuario = 'admin'")
        con.commit()
    return clave


def superusuario_protegido(con: sqlite3.Connection) -> str | None:
    """El nombre del superusuario definido en .env (o None si no hay): ese usuario no se edita desde la pantalla."""
    f = con.execute("SELECT valor FROM meta WHERE clave = 'superusuario'").fetchone()
    return f["valor"] if f else None


def _exigir_no_protegido(con: sqlite3.Connection, u: sqlite3.Row, que: str) -> None:
    if u["usuario"] == superusuario_protegido(con):
        raise SeguridadError(
            f"«{u['usuario']}» es el superusuario: {que}. Se define en el archivo .env "
            "(COMPRAS_SUPERUSUARIO y COMPRAS_SUPERUSUARIO_CLAVE).",
            409,
        )


def asegurar_superusuario(con: sqlite3.Connection, usuario: str | None, clave: str | None) -> str | None:
    """Deja creado y en regla el SUPERUSUARIO: un administrador con la clave que se definió en el archivo .env.
    Se llama en cada arranque, así que el .env manda: si alguien lo borró, desactivó, le quitó el perfil o le cambió la
    clave, vuelve a quedar como está en el .env. Nunca pide cambiar la clave.

    Devuelve «creado», «actualizado» o «igual». Sin `clave` no hay superusuario: devuelve None y libera la protección
    (el usuario sigue existiendo, ya como un administrador normal). Lanza SeguridadError si el nombre o la clave no
    cumplen las reglas (el mensaje nunca trae la clave)."""
    if not clave:
        con.execute("DELETE FROM meta WHERE clave = 'superusuario'")
        con.commit()
        return None
    usuario = (usuario or "superadmin").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", usuario):
        raise SeguridadError(
            "El nombre del superusuario debe tener de 3 a 40 caracteres: letras sin tilde, números, punto, guion o guion bajo."
        )
    validar_clave(clave, usuario)
    u = con.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
    if u is None:
        crear(con, usuario, "Superusuario", "admin", clave=clave)
        resultado = "creado"
    else:
        clave_igual = verificar(clave, u["clave_hash"])
        en_regla = (
            clave_igual
            and u["rol"] == "admin"
            and u["activo"]
            and not u["cambiar_clave"]
            and not u["bloqueado_hasta"]
            and u["intentos"] == 0
        )
        resultado = "igual"
        if not en_regla:
            con.execute(
                "UPDATE usuarios SET clave_hash = ?, rol = 'admin', cod_empresa = NULL, activo = 1, cambiar_clave = 0,"
                " intentos = 0, bloqueado_hasta = NULL WHERE id = ?",
                (u["clave_hash"] if clave_igual else hashear(clave), u["id"]),
            )
            if not clave_igual or u["rol"] != "admin" or not u["activo"]:
                cerrar_sesiones(con, u["id"])  # la clave o el perfil cambiaron: las sesiones viejas dejan de valer
            resultado = "actualizado"
    con.execute(
        "INSERT INTO meta (clave, valor) VALUES ('superusuario', ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
        (usuario,),
    )
    con.commit()
    return resultado


# ============================================================================================ sesiones
def _huella(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ingresar(con: sqlite3.Connection, usuario: str, clave: str) -> tuple[str, dict]:
    """Valida usuario y clave y abre una sesión. Devuelve (token para la cookie, usuario).
    El mismo mensaje para «usuario inexistente» y «clave incorrecta»; 5 fallos seguidos bloquean 5 minutos."""
    ahora = _ahora()
    u = con.execute(_SELECT + " WHERE u.usuario = ?", ((usuario or "").strip().lower(),)).fetchone()
    if u is None:
        verificar(clave or "", _HUELLA_FALSA)  # mismo tiempo de respuesta que con un usuario real
        raise SeguridadError("Usuario o clave incorrectos.", 401)
    if u["bloqueado_hasta"] and ahora < datetime.strptime(u["bloqueado_hasta"], _FORMATO_FECHA):
        raise SeguridadError("Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.", 429)
    clave = clave or ""
    # Al copiar la clave del correo o de WhatsApp a veces se pega con un espacio o salto de línea al final
    if not verificar(clave, u["clave_hash"]) and not (clave.strip() != clave and verificar(clave.strip(), u["clave_hash"])):
        intentos = u["intentos"] + 1
        bloqueo = _texto(ahora + BLOQUEO) if intentos >= MAX_INTENTOS else None
        con.execute(
            "UPDATE usuarios SET intentos = ?, bloqueado_hasta = ? WHERE id = ?",
            (0 if bloqueo else intentos, bloqueo, u["id"]),
        )
        con.commit()
        raise SeguridadError("Usuario o clave incorrectos.", 401)
    if not u["activo"]:
        raise SeguridadError("Tu usuario está desactivado. Habla con el administrador.", 403)
    token = secrets.token_urlsafe(32)
    con.execute("DELETE FROM sesiones WHERE expira < ?", (_texto(ahora),))  # limpieza de sesiones vencidas
    con.execute(
        "INSERT INTO sesiones (token_hash, usuario_id, creada, expira) VALUES (?,?,?,?)",
        (_huella(token), u["id"], _texto(ahora), _texto(ahora + DURACION_SESION)),
    )
    con.execute(
        "UPDATE usuarios SET intentos = 0, bloqueado_hasta = NULL, ultimo_ingreso = ? WHERE id = ?",
        (_texto(ahora), u["id"]),
    )
    con.commit()
    return token, publico(_obtener(con, u["id"]))


def usuario_de_token(con: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    """El usuario dueño de esa sesión, o None si no hay sesión, venció o el usuario fue desactivado o eliminado."""
    if not token:
        return None
    return con.execute(
        "SELECT u.*, e.nombre AS empresa FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id "
        "LEFT JOIN empresas e ON e.cod = u.cod_empresa WHERE s.token_hash = ? AND s.expira > ? AND u.activo = 1",
        (_huella(token), _texto(_ahora())),
    ).fetchone()


def cerrar_sesion(con: sqlite3.Connection, token: str | None) -> None:
    """Cierra UNA sesión (el botón «Salir»)."""
    if token:
        con.execute("DELETE FROM sesiones WHERE token_hash = ?", (_huella(token),))
        con.commit()


def cerrar_sesiones(con: sqlite3.Connection, usuario_id: int, conservar: str | None = None) -> None:
    """Cierra TODAS las sesiones de un usuario (salvo, si se pide, la del `conservar`). No confirma la transacción."""
    con.execute(
        "DELETE FROM sesiones WHERE usuario_id = ? AND token_hash IS NOT ?",
        (usuario_id, _huella(conservar) if conservar else None),
    )


# ============================================================================================ permisos
TODOS = frozenset(ROLES)
INTERNOS = frozenset({"admin", "prime", "consulta"})  # los de la Clínica que ven el tablero
EDITORES = frozenset({"admin", "prime"})  # los que pueden cambiar cosas (todo menos Administración)
SOLO_ADMIN = frozenset({"admin"})
EXTERNOS = frozenset({"externo"})
PUBLICO = "publico"  # sin sesión

# (métodos, ruta, perfiles permitidos). Se evalúa en orden y gana la PRIMERA que coincida.
# LO QUE NO ESTÁ AQUÍ se niega a todos menos al administrador (por si alguien agrega una ruta y olvida listarla).
# Hay una prueba (tests/test_seguridad.py) que recorre TODAS las rutas y falla si alguna no está en esta tabla.
_POLITICA_TEXTO = [
    # --- sesión ---
    ("POST", r"/api/sesion", PUBLICO),
    ("GET", r"/api/salud", PUBLICO),
    ("GET|DELETE", r"/api/sesion", TODOS),
    ("PUT", r"/api/sesion/clave", TODOS),
    # --- el proveedor externo: SOLO esto ---
    (
        "GET",
        r"/api/proveedor/productos",
        EXTERNOS | SOLO_ADMIN,
    ),  # el administrador ve esta pantalla tal como la ve el proveedor
    ("GET", r"/api/proveedor/lista/[^/]+", EXTERNOS | SOLO_ADMIN),  # las ventanas «Sin oferta» y «Nuevos»
    ("GET", r"/api/proveedor/excel", EXTERNOS | SOLO_ADMIN),
    ("POST", r"/api/proveedor/ofertas", EXTERNOS),  # subir su ficha con precios (queda pendiente)
    ("GET", r"/api/proveedor/ofertas", EXTERNOS),  # sus envíos y su estado
    # --- el administrador revisa lo que suben los proveedores ---
    ("GET", r"/api/pendientes", SOLO_ADMIN),
    ("GET", r"/api/pendientes/\d+", SOLO_ADMIN),
    ("GET", r"/api/pendientes/\d+/excel", SOLO_ADMIN),  # la ficha del proveedor como Excel
    ("POST", r"/api/pendientes/\d+/(aprobar|rechazar|restaurar)", SOLO_ADMIN),
    # --- ver el tablero (administrador, prime y consulta) ---
    ("GET", r"/api/resumen", INTERNOS),
    ("GET", r"/api/control", INTERNOS),  # los tableros de control (empresas, precios y consumo)
    ("GET", r"/api/productos", INTERNOS),
    ("GET", r"/api/productos/[^/]+/ofertas", INTERNOS),
    ("GET", r"/api/empresas/[^/]+/ficha", INTERNOS),
    ("GET", r"/api/exportar/productos-a-comprar", EDITORES),
    # --- cambiar cosas (administrador y prime) ---
    ("GET", r"/api/productos/[^/]+", EDITORES),
    ("PUT|DELETE", r"/api/productos/[^/]+/seleccion", EDITORES),
    ("PUT|DELETE", r"/api/productos/[^/]+/cantidad", EDITORES),
    ("POST", r"/api/productos", EDITORES),
    ("PUT|DELETE", r"/api/productos/[^/]+", EDITORES),
    ("GET", r"/api/catalogo", EDITORES),
    ("POST", r"/api/ofertas", EDITORES),
    ("DELETE", r"/api/ofertas/\d+", EDITORES),
    ("GET|POST", r"/api/empresas", EDITORES),
    ("PUT|DELETE", r"/api/empresas/[^/]+", EDITORES),
    ("POST", r"/api/cargas/[^/]+", EDITORES),
    ("GET", r"/api/plantillas/[^/]+", EDITORES),
    ("GET", r"/api/avisos", EDITORES),
    ("POST", r"/api/importar", EDITORES),
    ("GET", r"/api/exportar/oc", EDITORES),
    ("GET", r"/api/exportar/alternativas", EDITORES),
    # --- «Adicionales»: código y descripción → Proveedor 1, 2 y 3 con su menor valor ---
    ("GET", r"/api/adicionales(/excel|/plantilla)?", INTERNOS),
    ("POST", r"/api/adicionales(/archivo|/\d+/activo)?", EDITORES),
    ("DELETE", r"/api/adicionales(/\d+)?", EDITORES),
    # --- «Actualizar Excel»: importar y ver cuántas filas tiene cada tabla (administrador y prime) ---
    ("GET", r"/api/admin/tablas", EDITORES),
    ("POST", r"/api/admin/importar", EDITORES),
    ("POST", r"/api/admin/tablas/[^/]+/importar", EDITORES),
    # --- todo lo demás de /api/admin (ver/editar filas, historial) y /api/usuarios: solo administrador ---
    ("GET|POST|PUT|DELETE", r"/api/(admin|usuarios)(/.*)?", SOLO_ADMIN),
]
POLITICA = [(frozenset(m.split("|")), re.compile(r), roles) for m, r, roles in _POLITICA_TEXTO]
_RUTAS_DE_SESION = {("GET", "/api/sesion"), ("DELETE", "/api/sesion"), ("PUT", "/api/sesion/clave")}


def roles_permitidos(metodo: str, ruta: str):
    """Quiénes pueden hacer esta petición: PUBLICO (sin sesión) o un conjunto de perfiles. Sin regla → solo administrador."""
    ruta = ruta.rstrip("/") or "/"
    for metodos, patron, roles in POLITICA:
        if metodo in metodos and patron.fullmatch(ruta):
            return roles
    return SOLO_ADMIN


def es_ruta_de_sesion(metodo: str, ruta: str) -> bool:
    """¿Es una de las tres rutas que se pueden usar aun teniendo que cambiar la clave (ver la sesión, salir, cambiarla)?"""
    return (metodo, ruta.rstrip("/")) in _RUTAS_DE_SESION
