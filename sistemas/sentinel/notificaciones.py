"""SENTINEL PABON — envío de usuario y clave temporal por CORREO y por WHATSAPP (igual que en SUMIPABON).

Cuando el administrador crea un usuario o le da una clave nueva, SENTINEL intenta enviarle su usuario y su clave
temporal por correo y por WhatsApp. Si WhatsApp automático no está configurado, la pantalla ofrece el botón
«Abrir WhatsApp con el mensaje» (enlace wa.me) para enviarlo a mano.

DÓNDE SE CONFIGURA (gana el primero que tenga el dato):
  1. Variables de entorno  SENTINEL_...
  2. El archivo  sentinel/.env  con líneas  SENTINEL_...=valor
  3. Lo que YA tiene SUMIPABON: variables de entorno COMPRAS_... o su archivo  compras_app/.env
     → Si el correo/WhatsApp ya funciona en SUMIPABON, SENTINEL lo usa sin configurar nada más.

Nombres (con prefijo SENTINEL_ o COMPRAS_):
  SMTP_SERVIDOR, SMTP_PUERTO (587; 465 = SSL), SMTP_USUARIO, SMTP_CLAVE, SMTP_REMITENTE, SMTP_TLS ("0" = sin STARTTLS)
  WHATSAPP_TOKEN, WHATSAPP_ID_NUMERO, WHATSAPP_PLANTILLA (4 variables: nombre, usuario, clave, dirección), WHATSAPP_IDIOMA
  SENTINEL_URL_PUBLICA  la dirección que va en el mensaje (si no, la que usó el administrador)

La clave temporal nunca se escribe en registros ni en mensajes de error. Solo usa librerías que vienen con Python.
"""

from __future__ import annotations

import html
import json
import os
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

import nexo_correo

ROOT = Path(__file__).resolve().parent
LOGO_CORREO = ROOT / "assets" / "nexo-correo.png"  # logo de Nexo S² incrustado en los correos
TIEMPO_ESPERA = 10
API_WHATSAPP = "https://graph.facebook.com/v20.0"
ENVIADO, NO_CONFIGURADO, SIN_DATO, ERROR = "enviado", "no_configurado", "sin_dato", "error"


class NotificacionError(Exception):
    pass


def _archivos_env() -> list[tuple[Path, str]]:
    propio = Path(os.environ["SENTINEL_ENV"]) if os.environ.get("SENTINEL_ENV") else ROOT / ".env"
    compras = Path(os.environ["SENTINEL_ENV_COMPRAS"]) if os.environ.get("SENTINEL_ENV_COMPRAS") else ROOT.parent / "compras_app" / ".env"
    return [(propio, "SENTINEL_"), (compras, "COMPRAS_")]


_cache: dict = {}


def _leer_env(ruta: Path) -> dict:
    try:
        clave = ruta.stat().st_mtime_ns
    except OSError:
        return {}
    if _cache.get(str(ruta), (None,))[0] != clave:
        valores = {}
        for linea in ruta.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            nombre, _, valor = linea.partition("=")
            nombre = nombre.strip().removeprefix("export ").strip()
            valor = valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            valores[nombre] = valor
        _cache[str(ruta)] = (clave, valores)
    return _cache[str(ruta)][1]


# Lo que es PROPIO de cada sistema y nunca se toma de SUMIPABON: sus plantillas de WhatsApp dicen «SUMIPABON» y su
# dirección lleva a SUMIPABON; usarlas aquí enviaría un mensaje que no corresponde (con credenciales que allá no sirven).
SOLO_SENTINEL = {"WHATSAPP_PLANTILLA", "WHATSAPP_PLANTILLA_RESTABLECER", "URL_PUBLICA"}


def _env(nombre: str) -> str:
    """nombre sin prefijo, p. ej. «SMTP_SERVIDOR». El correo y la cuenta de WhatsApp se pueden compartir con SUMIPABON."""
    (propio, p1), (compras, p2) = _archivos_env()
    valores = [os.environ.get(p1 + nombre, ""), _leer_env(propio).get(p1 + nombre, "")]
    if nombre not in SOLO_SENTINEL:
        valores += [os.environ.get(p2 + nombre, ""), _leer_env(compras).get(p2 + nombre, "")]
    for valor in valores:
        valor = (valor or "").strip()
        if valor:
            if nombre == "SMTP_CLAVE" and re.fullmatch(r"[A-Za-z]{4}( [A-Za-z]{4}){3}", valor):
                valor = valor.replace(" ", "")  # clave de aplicación de Google escrita en 4 grupos
            return valor
    return ""


def superusuario_configurado() -> tuple[str, str]:
    """(usuario, clave) del superusuario. Se toman JUNTOS de un solo sistema: primero SENTINEL_SUPERUSUARIO /
    SENTINEL_SUPERUSUARIO_CLAVE (variables o sentinel/.env); si SENTINEL no define ninguno, los de SUMIPABON
    (COMPRAS_SUPERUSUARIO / COMPRAS_SUPERUSUARIO_CLAVE), así el mismo superusuario entra a los dos sistemas de Nexo S²."""
    (propio, p1), (compras, p2) = _archivos_env()
    for ruta, pref in ((propio, p1), (compras, p2)):
        env = _leer_env(ruta)
        usuario = (os.environ.get(pref + "SUPERUSUARIO") or env.get(pref + "SUPERUSUARIO") or "").strip()
        clave = os.environ.get(pref + "SUPERUSUARIO_CLAVE") or env.get(pref + "SUPERUSUARIO_CLAVE") or ""
        if usuario or clave:
            return usuario or "superadmin", clave
    return "superadmin", ""


def correo_configurado() -> bool:
    return bool(_env("SMTP_SERVIDOR"))


def cuenta_whatsapp() -> bool:
    return bool(_env("WHATSAPP_TOKEN") and _env("WHATSAPP_ID_NUMERO"))


def _plantillas_sumipabon() -> set[str]:
    """Los nombres de las plantillas de WhatsApp de SUMIPABON (para no confundirlas nunca con las de SENTINEL)."""
    _, (compras, p2) = _archivos_env()
    nombres = set()
    for n in ("WHATSAPP_PLANTILLA", "WHATSAPP_PLANTILLA_RESTABLECER"):
        for v in (os.environ.get(p2 + n, ""), _leer_env(compras).get(p2 + n, "")):
            if v.strip():
                nombres.add(v.strip().lower())
    return nombres


def problema_plantilla() -> str:
    """Por qué no se puede enviar WhatsApp automático con la plantilla de SENTINEL (vacío = todo bien).
    Cada sistema debe tener su PROPIA plantilla: la de SUMIPABON dice «SUMIPABON» y lleva a SUMIPABON."""
    if not cuenta_whatsapp():
        return "El envío automático por WhatsApp no está configurado: use el botón «Abrir WhatsApp con el mensaje»."
    propia = _env("WHATSAPP_PLANTILLA")
    if not propia:
        return ("WhatsApp automático de SENTINEL necesita su propia plantilla aprobada en Meta (SENTINEL_WHATSAPP_PLANTILLA), "
                "diferente a la de SUMIPABON. Mientras tanto use «Abrir WhatsApp con el mensaje».")
    ajenas = _plantillas_sumipabon()
    repetidas = [x for x in (propia, _env("WHATSAPP_PLANTILLA_RESTABLECER")) if x and x.strip().lower() in ajenas]
    if repetidas:
        return (f"La plantilla «{repetidas[0]}» es la de SUMIPABON. SENTINEL debe tener una plantilla DIFERENTE "
                "(la de SUMIPABON dice SUMIPABON y sus credenciales allá no sirven). Cámbiela en sistemas/sentinel/.env; "
                "mientras tanto use «Abrir WhatsApp con el mensaje».")
    return ""


def whatsapp_configurado() -> bool:
    """Envío automático: cuenta de WhatsApp (propia o la de SUMIPABON) + una plantilla PROPIA de SENTINEL, distinta a la
    de SUMIPABON y aprobada por Meta. Sin ella no se intenta (WhatsApp no entrega texto libre a quien no ha escrito antes)."""
    return not problema_plantilla()


def canales() -> dict:
    return {"correo": correo_configurado(), "whatsapp": whatsapp_configurado(), "aviso_whatsapp": problema_plantilla()}


def url_publica() -> str:
    return _env("URL_PUBLICA")


# ------------------------------------------------------------------ validación de contacto

def normalizar_correo(correo: str | None) -> str | None:
    correo = (correo or "").strip().lower()
    if not correo:
        return None
    if len(correo) > 120 or not re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]{2,}", correo):
        raise ValueError("El correo no es válido. Escríbalo así: nombre@dominio.com")
    return correo


def normalizar_celular(celular: str | None) -> str | None:
    """«300 123 4567» → «+573001234567». Para otro país, escriba el indicativo con «+»."""
    bruto = (celular or "").strip()
    if not bruto:
        return None
    digitos = re.sub(r"[\s().-]", "", bruto)
    con_mas = digitos.startswith("+")
    digitos = digitos.lstrip("+")
    if not digitos.isdigit():
        raise ValueError("El celular solo puede llevar números (y un + al inicio para el indicativo).")
    if len(digitos) == 10 and digitos.startswith("3"):
        digitos = "57" + digitos
    elif not ((len(digitos) == 12 and digitos.startswith("57")) or (con_mas and 8 <= len(digitos) <= 15)):
        raise ValueError("El celular no es válido. Escriba los 10 dígitos (ej. 300 123 4567) o con indicativo (+57…).")
    return "+" + digitos


# ------------------------------------------------------------------ mensajes

def _frases(restablecida: bool) -> tuple[str, str]:
    if restablecida:
        return ("se restableció tu clave de acceso a",
                "Al entrar, el sistema te pedirá elegir una clave nueva. Si no esperabas este cambio, avisa al administrador. No compartas este mensaje.")
    return ("ya tienes acceso a", "Al entrar por primera vez el sistema te pedirá elegir tu propia clave. No compartas este mensaje.")


def _rol(rol: str) -> str:
    return "Administrador" if rol == "administrador" else "Revisor (solo consulta)"


def mensaje(nombre, usuario, clave, url, rol, restablecida=False) -> str:
    apertura, cierre = _frases(restablecida)
    return nexo_correo.encabezado_texto("sentinel") + "\n\n" + (f"Hola {nombre}, {apertura} SENTINEL PABON, copias de seguridad (Clínica Cardioneurovascular Pabón).\n\n"
            f"Dirección: {url}\nUsuario: {usuario}\nClave temporal: {clave}\nPerfil: {_rol(rol)}" + (f"\n\n{cierre}" if cierre else ""))


def mensaje_html(nombre, usuario, clave, url, rol, restablecida=False) -> str:
    e = html.escape
    apertura, cierre = _frases(restablecida)
    boton = ""
    if url.lower().startswith(("http://", "https://")):
        boton = (f'<p style="margin:22px 0"><a href="{e(url, quote=True)}" style="display:inline-block;background:#015AAA;'
                 'color:#ffffff;text-decoration:none;font-weight:bold;padding:12px 24px;border-radius:6px">Entrar a SENTINEL</a></p>')
    return ('<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;color:#1d2733;line-height:1.5">'
            f"<p>Hola <b>{e(nombre)}</b>, {apertura} <b>SENTINEL PABON</b>, copias de seguridad (Clínica Cardioneurovascular Pabón).</p>"
            '<table style="border-collapse:collapse;margin:8px 0">'
            f'<tr><td style="padding:4px 18px 4px 0;color:#5f6b7a">Usuario</td><td><b>{e(usuario)}</b></td></tr>'
            f'<tr><td style="padding:4px 18px 4px 0;color:#5f6b7a">Clave temporal</td><td><b style="font-family:Consolas,monospace;font-size:16px">{e(clave)}</b></td></tr>'
            f'<tr><td style="padding:4px 18px 4px 0;color:#5f6b7a">Perfil</td><td>{e(_rol(rol))}</td></tr></table>'
            f'{boton}' + (f'<p style="font-size:13px;color:#5f6b7a">{e(cierre)}</p>' if cierre else "") + '</div>')


def enlace_whatsapp(celular: str, texto: str) -> str:
    return f"https://wa.me/{celular.lstrip('+')}?text={quote(texto)}"


# ------------------------------------------------------------------ envíos

def enviar_correo(destino, asunto, cuerpo, cuerpo_html=None) -> None:
    servidor = _env("SMTP_SERVIDOR")
    puerto = int(_env("SMTP_PUERTO") or 587)
    usuario, clave = _env("SMTP_USUARIO"), _env("SMTP_CLAVE")
    msg = EmailMessage()
    msg["To"] = destino
    # Marca Nexo S²: nombre del remitente, asunto, encabezado con logo, franja SENTINEL PABON y pie.
    msg["From"] = nexo_correo.remitente(_env("SMTP_REMITENTE") or usuario, "sentinel@localhost")
    msg["Subject"] = nexo_correo.asunto(asunto)
    nexo_correo.armar(msg, "sentinel", cuerpo, cuerpo_html, LOGO_CORREO)
    try:
        if puerto == 465:
            s = smtplib.SMTP_SSL(servidor, puerto, timeout=TIEMPO_ESPERA, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(servidor, puerto, timeout=TIEMPO_ESPERA)
        with s:
            if puerto != 465 and _env("SMTP_TLS") != "0":
                s.starttls(context=ssl.create_default_context())
            if usuario:
                s.login(usuario, clave)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise NotificacionError("El servidor de correo rechazó el usuario o la clave SMTP configurados.") from None
    except (smtplib.SMTPException, OSError) as e:
        raise NotificacionError(f"No se pudo conectar o enviar por correo ({type(e).__name__}).") from None


def enviar_whatsapp(celular, nombre, usuario, clave, url, rol, restablecida=False) -> None:
    """Con la plantilla de SENTINEL (4 variables: nombre, usuario, clave temporal, dirección). Para restablecer usa
    SENTINEL_WHATSAPP_PLANTILLA_RESTABLECER si existe; si no, la normal."""
    plantilla = (_env("WHATSAPP_PLANTILLA_RESTABLECER") if restablecida else "") or _env("WHATSAPP_PLANTILLA")
    if not plantilla or problema_plantilla():
        raise NotificacionError(problema_plantilla() or "Falta la plantilla de WhatsApp de SENTINEL.")
    base = {"messaging_product": "whatsapp", "to": celular.lstrip("+"), "type": "template", "template": {
        "name": plantilla, "language": {"code": _env("WHATSAPP_IDIOMA") or "es"},
        "components": [{"type": "body", "parameters": [{"type": "text", "text": v} for v in (nombre, usuario, clave, url)]}],
    }}
    pedido = urllib.request.Request(
        f"{API_WHATSAPP}/{_env('WHATSAPP_ID_NUMERO')}/messages", data=json.dumps(base).encode("utf-8"),
        headers={"Authorization": f"Bearer {_env('WHATSAPP_TOKEN')}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=TIEMPO_ESPERA):
            pass
    except urllib.error.HTTPError as e:
        try:
            motivo = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            motivo = ""
        raise NotificacionError(f"WhatsApp respondió con error {e.code}. {motivo[:160]}".strip()) from None
    except (urllib.error.URLError, OSError) as e:
        raise NotificacionError(f"No se pudo conectar con WhatsApp ({type(e).__name__}).") from None


def enviar_credenciales(u: dict, clave: str, url: str, restablecida: bool = False) -> dict:
    """Nunca lanza errores: cada canal dice qué pasó. Incluye enlace_whatsapp para el envío manual."""
    texto = mensaje(u["nombre"], u["usuario"], clave, url, u["rol"], restablecida)
    r = {}
    if not u.get("correo"):
        r["correo"] = {"estado": SIN_DATO, "detalle": "No tiene correo registrado."}
    elif not correo_configurado():
        r["correo"] = {"estado": NO_CONFIGURADO, "detalle": "El envío de correo no está configurado (ni en sentinel/.env ni en el .env de SUMIPABON)."}
    else:
        try:
            enviar_correo(u["correo"], "Se restableció tu clave de SENTINEL PABON" if restablecida else "Tu acceso a SENTINEL PABON", texto,
                          mensaje_html(u["nombre"], u["usuario"], clave, url, u["rol"], restablecida))
            r["correo"] = {"estado": ENVIADO, "detalle": f"Enviado a {u['correo']}."}
        except NotificacionError as e:
            r["correo"] = {"estado": ERROR, "detalle": str(e)}
    if not u.get("celular"):
        r["whatsapp"] = {"estado": SIN_DATO, "detalle": "No tiene celular registrado."}
    elif not whatsapp_configurado():
        r["whatsapp"] = {"estado": NO_CONFIGURADO, "detalle": problema_plantilla()}
    else:
        try:
            enviar_whatsapp(u["celular"], u["nombre"], u["usuario"], clave, url, u["rol"], restablecida)
            r["whatsapp"] = {"estado": ENVIADO, "detalle": f"Enviado al {u['celular']}."}
        except NotificacionError as e:
            r["whatsapp"] = {"estado": ERROR, "detalle": str(e)}
    if u.get("celular") and r["whatsapp"]["estado"] != ENVIADO:
        r["enlace_whatsapp"] = enlace_whatsapp(u["celular"], texto + "\n\n" + nexo_correo.PIE)
    return r
