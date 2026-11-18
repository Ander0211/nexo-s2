"""
ENVÍO DE USUARIO Y CLAVE TEMPORAL (correo y WhatsApp)
=====================================================
Cuando el administrador crea un usuario (o le restablece la clave), la aplicación intenta enviarle su usuario y su clave
temporal por **correo** y por **WhatsApp**, si la persona tiene esos datos. Sin lógica web: solo arma y envía mensajes.

Nada se envía si no está configurado. La configuración se lee de DOS sitios (gana el primero que la tenga):
  1. variables de entorno del sistema;
  2. el archivo `.env` que está en la carpeta del proyecto (junto a run.py). ES LO MÁS FÁCIL: no depende de qué terminal
     o programa abras. Copia `.env.ejemplo` como `.env` y escribe tus datos. `.env` no se sube a GitHub (.gitignore).
Las variables son (ver README → «Enviar usuario y clave»):

  CORREO (SMTP)
    COMPRAS_SMTP_SERVIDOR     ej. smtp.gmail.com          (sin esto, el correo queda «no configurado»)
    COMPRAS_SMTP_PUERTO       587 (por defecto; con 465 usa SSL)
    COMPRAS_SMTP_USUARIO      la cuenta que envía
    COMPRAS_SMTP_CLAVE        su clave (en Gmail: «clave de aplicación»)
    COMPRAS_SMTP_REMITENTE    «SUMIPABON <compras@clinica.com>» (por defecto, el usuario SMTP)
    COMPRAS_SMTP_TLS          «0» para no usar STARTTLS (por defecto sí)

  WHATSAPP (API oficial «WhatsApp Cloud API» de Meta)
    COMPRAS_WHATSAPP_TOKEN        token de acceso permanente
    COMPRAS_WHATSAPP_ID_NUMERO    «Phone number ID» del número de la Clínica
    COMPRAS_WHATSAPP_PLANTILLA    nombre de una plantilla aprobada con 4 variables: {{1}} nombre, {{2}} usuario,
                                  {{3}} clave temporal, {{4}} dirección. Meta EXIGE plantilla para escribirle a
                                  alguien que no te ha escrito en las últimas 24 h; sin plantilla se envía texto simple,
                                  que solo llega dentro de esa ventana.
    COMPRAS_WHATSAPP_IDIOMA       código de idioma de la plantilla (por defecto «es»)

  COMPRAS_URL_PUBLICA             dirección que se escribe en el mensaje (por defecto, la que usó el administrador)

Si WhatsApp no está configurado, la pantalla ofrece un botón «Abrir WhatsApp» que deja el mensaje escrito (enlace
wa.me) para que el administrador lo envíe a mano.

Cada canal devuelve {"estado", "detalle"}; estado = «enviado» · «no_configurado» · «sin_dato» · «error».
La clave temporal NUNCA se escribe en registros ni en los mensajes de error.
"""

import html
import json
import os
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from html import escape
from pathlib import Path
from urllib.parse import quote

from . import nexo_correo

TIEMPO_ESPERA = 10  # segundos por intento: si el servicio no responde, se informa y se sigue
API_WHATSAPP = "https://graph.facebook.com/v20.0"

ENVIADO, NO_CONFIGURADO, SIN_DATO, ERROR = "enviado", "no_configurado", "sin_dato", "error"


class NotificacionError(Exception):
    """No se pudo enviar (el texto es apto para mostrarlo a la persona; nunca trae claves)."""


RAIZ = Path(__file__).resolve().parents[2]  # la carpeta del proyecto (donde está run.py)
LOGO_CORREO = RAIZ / "frontend" / "img" / "nexo-correo.png"  # logo de Nexo S² que va incrustado en los correos
_cache_env: dict = {"clave": None, "valores": {}}


def _archivo_env() -> Path:
    """El archivo de configuración: el de COMPRAS_ENV si existe esa variable; si no, `.env` en la raíz del proyecto."""
    return Path(os.environ["COMPRAS_ENV"]) if os.environ.get("COMPRAS_ENV") else RAIZ / ".env"


def diagnostico_env() -> str:
    """Dónde busca el programa su configuración y por qué no la encontró: va en el mensaje «el correo no está configurado», para no tener que
    adivinar. Cubre lo más común: el archivo no está en esa carpeta (p. ej. se reemplazó la carpeta del proyecto y se perdió) o Windows le agregó
    «.txt» al nombre (el Bloc de notas guarda «.env» como «.env.txt»)."""
    ruta = _archivo_env()
    if ruta.exists():
        return f"Busqué en {ruta}: el archivo existe, pero no trae una línea COMPRAS_SMTP_SERVIDOR=... con valor."
    carpeta = ruta.parent
    parecidos = [p.name for p in (carpeta / ".env.txt", carpeta / "env.txt", carpeta / "env") if p.exists()]
    if parecidos:
        pista = f" Encontré «{parecidos[0]}»: en Windows el Bloc de notas suele agregarle .txt al nombre; debe llamarse exactamente .env (sin .txt)."
    elif (carpeta / ".env.ejemplo").exists():
        pista = " Copia «.env.ejemplo» como «.env» en esa carpeta y escribe tus datos de correo."
    else:
        pista = ""
    return f"No existe el archivo {ruta}.{pista}"


def leer_archivo_env(ruta: Path) -> dict:
    """Lee un archivo de líneas `NOMBRE=valor`. Ignora líneas vacías y comentarios (#), un `export ` al inicio y las
    comillas que rodean el valor. Tolera lo que hace el Bloc de notas de Windows (BOM al inicio, saltos \\r\\n)."""
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
        if nombre:
            valores[nombre] = valor
    return valores


def _valores_archivo() -> dict:
    """Los valores del archivo .env (se vuelve a leer solo si el archivo cambió: se puede editar sin reiniciar)."""
    ruta = _archivo_env()
    try:
        clave = (str(ruta), ruta.stat().st_mtime_ns)
    except OSError:
        return {}
    if _cache_env["clave"] != clave:
        _cache_env.update(clave=clave, valores=leer_archivo_env(ruta))
    return _cache_env["valores"]


def _env(nombre: str) -> str:
    """Valor de configuración: primero la variable de entorno del sistema; si no está, el archivo .env."""
    valor = os.environ.get(nombre, "").strip() or _valores_archivo().get(nombre, "").strip()
    if nombre == "COMPRAS_SMTP_CLAVE" and re.fullmatch(r"[A-Za-z]{4}( [A-Za-z]{4}){3}", valor):
        valor = valor.replace(" ", "")  # Google muestra la clave de aplicación en 4 grupos con espacios: se aceptan así
    return valor


def valor_de_configuracion(nombre: str) -> str:
    """Un valor de configuración (variable de entorno o archivo .env) para quien lo necesite fuera de este módulo."""
    return _env(nombre)


def url_publica() -> str:
    """La dirección que se escribe en el mensaje (COMPRAS_URL_PUBLICA, de las variables o del .env); vacío si no hay."""
    return _env("COMPRAS_URL_PUBLICA")


def ip_de_red() -> str:
    """La IP de este PC en la red local (la que usan los celulares y otros equipos para entrar)."""
    import socket

    for destino in ("10.255.255.255", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect((destino, 1))  # no envía nada: solo pregunta por qué tarjeta de red saldría
                ip = s.getsockname()[0]
            finally:
                s.close()
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return "localhost"


def direccion_alcanzable(base: str) -> str:
    """Si el administrador entró como «localhost» (o 127.0.0.1), en el celular de otra persona esa dirección no lleva a
    SUMIPABON: se cambia por la IP de este PC en la red, con el mismo puerto."""
    from urllib.parse import urlsplit, urlunsplit

    partes = urlsplit(base)
    if (partes.hostname or "") in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        puerto = f":{partes.port}" if partes.port else ""
        partes = partes._replace(netloc=f"{ip_de_red()}{puerto}")
    return urlunsplit(partes)


def enlace_de_ingreso(base: str, usuario: str | None = None) -> str:
    """La dirección que va en el mensaje. Termina en «/?ingresar=1»: al abrirla, la página cierra cualquier sesión que
    hubiera en ese navegador y pide usuario y clave (así no entra directo como otra persona, p. ej. el administrador).
    Con `usuario`, la pantalla de ingreso lo trae ya escrito (como SENTINEL)."""
    enlace = direccion_alcanzable(base).rstrip("/") + "/?ingresar=1"
    return enlace + "&usuario=" + quote(usuario) if usuario else enlace


def correo_configurado() -> bool:
    return bool(_env("COMPRAS_SMTP_SERVIDOR"))


def _plantillas_sentinel() -> set[str]:
    """Nombres de las plantillas de WhatsApp de SENTINEL PABON (Nexo S²): variables SENTINEL_... o sentinel/.env."""
    ruta = Path(os.environ["COMPRAS_ENV_SENTINEL"]) if os.environ.get("COMPRAS_ENV_SENTINEL") else RAIZ.parent / "sentinel" / ".env"
    valores = {}
    try:
        for linea in ruta.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            nombre, igual, valor = linea.strip().partition("=")
            if igual and not nombre.startswith("#"):
                valores[nombre.strip()] = valor.strip().strip("\"'")
    except OSError:
        pass
    nombres = set()
    for n in ("SENTINEL_WHATSAPP_PLANTILLA", "SENTINEL_WHATSAPP_PLANTILLA_RESTABLECER"):
        for v in (os.environ.get(n, ""), valores.get(n, "")):
            if v.strip():
                nombres.add(v.strip().lower())
    return nombres


def plantilla_de_otro_sistema(restablecida: bool = False) -> str:
    """Si la plantilla que usaría SUMIPABON es la MISMA de SENTINEL, la devuelve (y no se envía): cada sistema debe
    tener su propia plantilla, o la persona recibiría el mensaje del otro sistema. Vacío = todo bien."""
    plantilla = ((_env("COMPRAS_WHATSAPP_PLANTILLA_RESTABLECER") if restablecida else "") or _env("COMPRAS_WHATSAPP_PLANTILLA")).strip()
    return plantilla if plantilla and plantilla.lower() in _plantillas_sentinel() else ""


def whatsapp_configurado() -> bool:
    return bool(_env("COMPRAS_WHATSAPP_TOKEN") and _env("COMPRAS_WHATSAPP_ID_NUMERO"))


def canales() -> dict:
    """Qué canales están listos (para que la pantalla de Usuarios lo avise antes de crear a alguien)."""
    return {"correo": correo_configurado(), "whatsapp": whatsapp_configurado()}


def _frases(restablecida: bool) -> tuple[str, str]:
    """(cómo abre el mensaje, cómo cierra): una cuenta nueva y una clave restablecida no se dicen igual."""
    if restablecida:
        return (
            "se restableció tu clave de acceso a",
            "Al entrar, el sistema te pedirá elegir una clave nueva. Si no esperabas este cambio, avisa al "
            "administrador. No compartas este mensaje.",
        )
    return (
        "ya tienes acceso a",
        "Al entrar por primera vez el sistema te pedirá elegir tu propia clave. No compartas este mensaje.",
    )


def asunto(restablecida: bool = False) -> str:
    """El asunto del correo."""
    return "Se restableció tu clave de SUMIPABON" if restablecida else "Tu acceso a SUMIPABON"


def mensaje(nombre: str, usuario: str, clave: str, url: str, restablecida: bool = False) -> str:
    """El texto que recibe la persona (sirve igual para el correo y para WhatsApp). `restablecida=True` cuando no es una
    cuenta nueva sino una clave que el administrador restableció."""
    apertura, cierre = _frases(restablecida)
    return nexo_correo.encabezado_texto("sumipabon") + "\n\n" + (
        f"Hola {nombre}, {apertura} SUMIPABON (Clínica Cardioneurovascular Pabón).\n\n"
        f"Usuario: {usuario}\n"
        f"Clave temporal: {clave}\n\n"
        f"Ingresa aquí: {url}\n\n"
        f"{cierre}"
    )


def mensaje_html(nombre: str, usuario: str, clave: str, url: str, restablecida: bool = False) -> str:
    """El mismo mensaje del correo, con un botón «Entrar a SUMIPABON»: la dirección (IP) queda DENTRO del botón y no se escribe
    como texto visible. Todo lo que se inserta se escapa; si `url` no es http(s), no se pone botón."""
    e = html.escape
    apertura, cierre = _frases(restablecida)
    boton = ""
    if url.lower().startswith(("http://", "https://")):
        boton = (
            f'<p style="margin:22px 0"><a href="{e(url, quote=True)}" style="display:inline-block;background:#0a7cff;'
            'color:#ffffff;text-decoration:none;font-weight:bold;padding:12px 24px;border-radius:6px">'
            "Entrar a SUMIPABON</a></p>"
        )
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;color:#1d2733;line-height:1.5">'
        f"<p>Hola <b>{e(nombre)}</b>, {apertura} <b>SUMIPABON</b> (Clínica Cardioneurovascular Pabón).</p>"
        '<table style="border-collapse:collapse;margin:8px 0">'
        f'<tr><td style="padding:4px 18px 4px 0;color:#5f6b7a">Usuario</td><td><b>{e(usuario)}</b></td></tr>'
        '<tr><td style="padding:4px 18px 4px 0;color:#5f6b7a">Clave temporal</td>'
        f'<td><b style="font-family:Consolas,monospace;font-size:16px">{e(clave)}</b></td></tr></table>'
        f"{boton}"
        f'<p style="font-size:13px;color:#5f6b7a">{e(cierre)}</p></div>'
    )


def enlace_whatsapp(celular: str, texto: str) -> str:
    """Enlace wa.me que abre WhatsApp con el mensaje ya escrito (envío manual)."""
    return f"https://wa.me/{celular.lstrip('+')}?text={quote(texto)}"


def enviar_correo(destino: str, asunto: str, cuerpo: str, cuerpo_html: str | None = None) -> None:
    """Envía un correo por SMTP: texto simple y, si se da `cuerpo_html`, también esa versión (la que casi todos ven).
    Lanza NotificacionError si no se pudo."""
    servidor = _env("COMPRAS_SMTP_SERVIDOR")
    puerto = int(_env("COMPRAS_SMTP_PUERTO") or 587)
    usuario, clave = _env("COMPRAS_SMTP_USUARIO"), _env("COMPRAS_SMTP_CLAVE")
    msg = EmailMessage()
    msg["To"] = destino
    # Todos los correos salen con la marca Nexo S²: nombre del remitente, asunto, encabezado con logo y pie.
    msg["From"] = nexo_correo.remitente(_env("COMPRAS_SMTP_REMITENTE") or usuario, "sumipabon@localhost")
    msg["Subject"] = nexo_correo.asunto(asunto)
    nexo_correo.armar(msg, "sumipabon", cuerpo, cuerpo_html, LOGO_CORREO)
    try:
        if puerto == 465:
            s = smtplib.SMTP_SSL(servidor, puerto, timeout=TIEMPO_ESPERA, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(servidor, puerto, timeout=TIEMPO_ESPERA)
        with s:
            if puerto != 465 and _env("COMPRAS_SMTP_TLS") != "0":
                s.starttls(context=ssl.create_default_context())
            if usuario:
                s.login(usuario, clave)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise NotificacionError("El servidor de correo rechazó el usuario o la clave SMTP configurados.") from None
    except (smtplib.SMTPException, OSError) as e:
        raise NotificacionError(f"No se pudo conectar o enviar por correo ({type(e).__name__}).") from None


def enviar_whatsapp(celular: str, nombre: str, usuario: str, clave: str, url: str, restablecida: bool = False) -> None:
    """Envía el mensaje por la API de WhatsApp Cloud (plantilla si está configurada; si no, texto simple). Para un
    restablecimiento usa COMPRAS_WHATSAPP_PLANTILLA_RESTABLECER si existe (con las mismas 4 variables); si no, la normal."""
    plantilla = (_env("COMPRAS_WHATSAPP_PLANTILLA_RESTABLECER") if restablecida else "") or _env(
        "COMPRAS_WHATSAPP_PLANTILLA"
    )
    base = {"messaging_product": "whatsapp", "to": celular.lstrip("+")}
    if plantilla:
        valores = [nombre, usuario, clave, url]
        base.update(
            type="template",
            template={
                "name": plantilla,
                "language": {"code": _env("COMPRAS_WHATSAPP_IDIOMA") or "es"},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": v} for v in valores]}],
            },
        )
    else:
        base.update(type="text", text={"body": mensaje(nombre, usuario, clave, url, restablecida)})
    pedido = urllib.request.Request(
        f"{API_WHATSAPP}/{_env('COMPRAS_WHATSAPP_ID_NUMERO')}/messages",
        data=json.dumps(base).encode("utf-8"),
        headers={"Authorization": f"Bearer {_env('COMPRAS_WHATSAPP_TOKEN')}", "Content-Type": "application/json"},
        method="POST",
    )
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


def enviar_rechazo_oferta(
    destinos: list[tuple[str, str]], empresa: str, fecha: str, archivo: str | None, motivo: str, url: str
) -> dict:
    """Le avisa por correo al proveedor que la Clínica NO aprobó la ficha de precios que envió y POR QUÉ. `destinos` = [(nombre, correo), ...].
    Nunca lanza errores: devuelve {estado, detalle} igual que el envío de claves (enviado · no_configurado · error · sin_dato)."""
    if not destinos:
        return {"estado": SIN_DATO, "detalle": "El proveedor no tiene ningún correo registrado: no se le pudo avisar."}
    if not correo_configurado():
        return {
            "estado": NO_CONFIGURADO,
            "detalle": f"El envío de correo no está configurado en el servidor (falta COMPRAS_SMTP_SERVIDOR). {diagnostico_env()}",
        }
    enviados, fallos = [], []
    for nombre, correo in destinos:
        saludo = f"Hola {nombre}," if nombre else "Hola,"
        archivo_txt = f" ({archivo})" if archivo else ""
        texto = (
            f"{saludo}\n\nLa Clínica revisó la ficha de precios que {empresa} envió el {fecha}{archivo_txt} y no la aprobó.\n\n"
            f"Motivo: {motivo}\n\nPuedes corregirla y volver a subirla desde «Productos que necesitamos» → «Enviar mi oferta»:\n{url}\n\n"
            "SUMIPABON · Clínica Cardioneurovascular Pabón"
        )
        cuerpo = (
            f"<p>{escape(saludo)}</p><p>La Clínica revisó la ficha de precios que <b>{escape(empresa)}</b> envió el {escape(fecha)}{escape(archivo_txt)} y <b>no la aprobó</b>.</p>"
            f'<p style="padding:10px 14px;background:#fff2f2;border-left:4px solid #c0392b"><b>Motivo:</b> {escape(motivo)}</p>'
            f'<p>Puedes corregirla y volver a subirla desde «Productos que necesitamos» → «Enviar mi oferta»:<br><a href="{escape(url)}">{escape(url)}</a></p>'
            "<p>SUMIPABON · Clínica Cardioneurovascular Pabón</p>"
        )
        try:
            enviar_correo(correo, "Tu oferta fue rechazada · SUMIPABON", texto, cuerpo)
            enviados.append(correo)
        except NotificacionError as e:
            fallos.append(f"{correo}: {e}")
    if enviados:
        extra = f" No se pudo enviar a: {'; '.join(fallos)}" if fallos else ""
        return {"estado": ENVIADO, "detalle": f"Enviado a {', '.join(enviados)}.{extra}"}
    return {"estado": ERROR, "detalle": "; ".join(fallos)}


def enviar_aprobacion_oferta(
    destinos: list[tuple[str, str]], empresa: str, fecha: str, archivo: str | None, productos: int, url: str
) -> dict:
    """Le avisa por correo al proveedor que la Clínica APROBÓ la ficha de precios que envió y que la Clínica Pabón se pondrá en contacto con él.
    `destinos` = [(nombre, correo), ...]. Nunca lanza errores: devuelve {estado, detalle} igual que el envío de claves y el aviso de rechazo
    (enviado · no_configurado · error · sin_dato). Cierra invitando a consultar más productos nuevos o sin ofertas en el enlace. No dice precios ni nombres de otros proveedores: solo lo que es del propio proveedor."""
    if not destinos:
        return {"estado": SIN_DATO, "detalle": "El proveedor no tiene ningún correo registrado: no se le pudo avisar."}
    if not correo_configurado():
        return {
            "estado": NO_CONFIGURADO,
            "detalle": f"El envío de correo no está configurado en el servidor (falta COMPRAS_SMTP_SERVIDOR). {diagnostico_env()}",
        }
    enviados, fallos = [], []
    cuantos = f"{productos} producto{'s' if productos != 1 else ''} con precio"
    for nombre, correo in destinos:
        saludo = f"Hola {nombre}," if nombre else "Hola,"
        archivo_txt = f" ({archivo})" if archivo else ""
        texto = (
            f"{saludo}\n\nLa Clínica Pabón revisó la ficha de precios que {empresa} envió el {fecha}{archivo_txt} y la APROBÓ: "
            f"{cuantos} ya participan en la comparación de ofertas de la Clínica.\n\n"
            "La Clínica Pabón se pondrá en contacto contigo para coordinar los siguientes pasos. "
            "Por ahora no necesitas hacer nada más.\n\n"
            f"Si deseas conocer más productos nuevos o que aún no cuentan con ofertas, puedes consultarlos en el siguiente enlace.\n{url}\n\n"
            "SUMIPABON · Clínica Cardioneurovascular Pabón · Cra 36 #12, Pasto, Nariño"
        )
        cuerpo = (
            f"<p>{escape(saludo)}</p>"
            f"<p>La Clínica Pabón revisó la ficha de precios que <b>{escape(empresa)}</b> envió el {escape(fecha)}{escape(archivo_txt)} y "
            f"<b>la aprobó</b>: {escape(cuantos)} ya participan en la comparación de ofertas de la Clínica.</p>"
            '<p style="padding:10px 14px;background:#ecf8f0;border-left:4px solid #1e8e5a"><b>La Clínica Pabón se pondrá en contacto contigo</b> '
            "para coordinar los siguientes pasos. Por ahora no necesitas hacer nada más.</p>"
            f'<p>Si deseas conocer más productos nuevos o que aún no cuentan con ofertas, puedes consultarlos en el siguiente enlace.<br><a href="{escape(url)}">{escape(url)}</a></p>'
            "<p>SUMIPABON · Clínica Cardioneurovascular Pabón · Cra 36 #12, Pasto, Nariño</p>"
        )
        try:
            enviar_correo(correo, "Tu oferta fue aprobada · SUMIPABON", texto, cuerpo)
            enviados.append(correo)
        except NotificacionError as e:
            fallos.append(f"{correo}: {e}")
    if enviados:
        extra = f" No se pudo enviar a: {'; '.join(fallos)}" if fallos else ""
        return {"estado": ENVIADO, "detalle": f"Enviado a {', '.join(enviados)}.{extra}"}
    return {"estado": ERROR, "detalle": "; ".join(fallos)}


def enviar_restauracion_oferta(destinos: list[tuple[str, str]], empresa: str, fecha: str, archivo: str | None) -> dict:
    """Le avisa por correo al proveedor que la Clínica RESTAURÓ la decisión sobre su ficha (la aprobó o la rechazó y ahora la vuelve a revisar):
    se pide disculpas, se le dice que el equipo está revisando de nuevo sus ofertas y que muy pronto tendrá noticias. `destinos` = [(nombre, correo), ...].
    Nunca lanza errores: devuelve {estado, detalle} igual que los demás avisos (enviado · no_configurado · error · sin_dato). No dice precios ni
    nombres de otros proveedores."""
    if not destinos:
        return {"estado": SIN_DATO, "detalle": "El proveedor no tiene ningún correo registrado: no se le pudo avisar."}
    if not correo_configurado():
        return {
            "estado": NO_CONFIGURADO,
            "detalle": f"El envío de correo no está configurado en el servidor (falta COMPRAS_SMTP_SERVIDOR). {diagnostico_env()}",
        }
    enviados, fallos = [], []
    for nombre, correo in destinos:
        saludo = f"Hola {nombre}," if nombre else "Hola,"
        archivo_txt = f" ({archivo})" if archivo else ""
        texto = (
            f"{saludo}\n\nLo sentimos. Nuestro equipo de la Clínica Pabón se encuentra revisando de nuevo las ofertas que {empresa} envió el {fecha}{archivo_txt}.\n\n"
            "Muy pronto tendrá noticias.\n\n"
            "SUMIPABON · Clínica Cardioneurovascular Pabón · Cra 36 #12, Pasto, Nariño"
        )
        cuerpo = (
            f"<p>{escape(saludo)}</p>"
            '<p style="padding:10px 14px;background:#fff6e5;border-left:4px solid #d29b00"><b>Lo sentimos.</b> Nuestro equipo de la Clínica Pabón se encuentra '
            f"revisando de nuevo las ofertas que <b>{escape(empresa)}</b> envió el {escape(fecha)}{escape(archivo_txt)}.</p>"
            "<p><b>Muy pronto tendrá noticias.</b></p>"
            "<p>SUMIPABON · Clínica Cardioneurovascular Pabón · Cra 36 #12, Pasto, Nariño</p>"
        )
        try:
            enviar_correo(correo, "Estamos revisando de nuevo sus ofertas · SUMIPABON", texto, cuerpo)
            enviados.append(correo)
        except NotificacionError as e:
            fallos.append(f"{correo}: {e}")
    if enviados:
        extra = f" No se pudo enviar a: {'; '.join(fallos)}" if fallos else ""
        return {"estado": ENVIADO, "detalle": f"Enviado a {', '.join(enviados)}.{extra}"}
    return {"estado": ERROR, "detalle": "; ".join(fallos)}


def enviar_credenciales(u: dict, clave: str, url: str, restablecida: bool = False) -> dict:
    """Envía usuario y clave temporal de `u` (un usuario «público») por correo y WhatsApp, según sus datos y lo configurado.
    Nunca lanza errores: cada canal informa su resultado. Incluye `enlace_whatsapp` para el envío manual."""
    texto = mensaje(u["nombre"], u["usuario"], clave, url, restablecida)
    resultado = {}

    if not u.get("correo"):
        resultado["correo"] = {"estado": SIN_DATO, "detalle": "No tiene correo registrado."}
    elif not correo_configurado():
        resultado["correo"] = {
            "estado": NO_CONFIGURADO,
            "detalle": f"El envío de correo no está configurado en el servidor (falta COMPRAS_SMTP_SERVIDOR). {diagnostico_env()}",
        }
    else:
        try:
            enviar_correo(
                u["correo"],
                asunto(restablecida),
                texto,
                mensaje_html(u["nombre"], u["usuario"], clave, url, restablecida),
            )
            resultado["correo"] = {"estado": ENVIADO, "detalle": f"Enviado a {u['correo']}."}
        except NotificacionError as e:
            resultado["correo"] = {"estado": ERROR, "detalle": str(e)}

    if not u.get("celular"):
        resultado["whatsapp"] = {"estado": SIN_DATO, "detalle": "No tiene celular registrado."}
    elif not whatsapp_configurado():
        resultado["whatsapp"] = {
            "estado": NO_CONFIGURADO,
            "detalle": "El envío automático por WhatsApp no está configurado (faltan COMPRAS_WHATSAPP_TOKEN y COMPRAS_WHATSAPP_ID_NUMERO en el archivo .env).",
        }
    elif plantilla_de_otro_sistema(restablecida):
        resultado["whatsapp"] = {
            "estado": NO_CONFIGURADO,
            "detalle": f"La plantilla «{plantilla_de_otro_sistema(restablecida)}» es la misma de SENTINEL PABON: SUMIPABON debe "
            "tener una plantilla DIFERENTE (revise COMPRAS_WHATSAPP_PLANTILLA en el .env). No se envió para no mandar el mensaje de "
            "otro sistema; use «Abrir WhatsApp con el mensaje».",
        }
    else:
        try:
            enviar_whatsapp(u["celular"], u["nombre"], u["usuario"], clave, url, restablecida)
            resultado["whatsapp"] = {"estado": ENVIADO, "detalle": f"Enviado al {u['celular']}."}
        except NotificacionError as e:
            resultado["whatsapp"] = {"estado": ERROR, "detalle": str(e)}

    if u.get("celular") and resultado["whatsapp"]["estado"] != ENVIADO:
        resultado["enlace_whatsapp"] = enlace_whatsapp(u["celular"], texto + "\n\n" + nexo_correo.PIE)
    return resultado
