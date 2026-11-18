"""Nexo S² — marca común de los correos y mensajes de SUMIPABON y SENTINEL PABON.

Todo correo que sale de cualquiera de los dos sistemas:
  · llega de «Nexo S²» (se conserva la dirección configurada, solo cambia el nombre que se ve);
  · el asunto empieza por «Nexo S² · »;
  · trae el encabezado con el logo de Nexo S², una franja con el sistema que lo envía
    (SUMIPABON o SENTINEL PABON) y un pie común.
El mismo archivo vive en los dos sistemas; solo usa librerías que vienen con Python.
"""

from __future__ import annotations

import html
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from pathlib import Path

NOMBRE = "Nexo S²"
CLINICA = "Clínica Cardioneurovascular Pabón"
SISTEMAS = {
    "sumipabon": {"nombre": "SUMIPABON", "area": "Compras y suministros", "color": "#1d6ee6", "fondo": "#e8f1fd"},
    "sentinel": {"nombre": "SENTINEL PABON", "area": "Copias de seguridad", "color": "#0e8f6a", "fondo": "#e6f6f0"},
}


def asunto(texto: str) -> str:
    texto = (texto or "").strip()
    return texto if texto.startswith(NOMBRE) else f"{NOMBRE} · {texto}"


def remitente(configurado: str, defecto: str) -> str:
    """El correo sale con el nombre «Nexo S²» y la dirección configurada."""
    _, direccion = parseaddr(configurado or "")
    return formataddr((NOMBRE, direccion or defecto))


def encabezado_texto(sistema: str) -> str:
    s = SISTEMAS[sistema]
    return f"{NOMBRE} · {s['nombre']} ({s['area']})\n{CLINICA}"


def texto(sistema: str, cuerpo: str) -> str:
    """Versión de texto simple (y la de WhatsApp): encabezado de Nexo S² + el mensaje."""
    if cuerpo.startswith(NOMBRE):
        return cuerpo
    return f"{encabezado_texto(sistema)}\n\n{cuerpo}"


def pie_texto(sistema: str) -> str:
    return f"\n\n--\nEnviado por {NOMBRE} · {SISTEMAS[sistema]['nombre']} · {CLINICA}"


def _html(sistema: str, contenido: str, con_logo: bool) -> str:
    s = SISTEMAS[sistema]
    e = html.escape
    logo = (f'<td style="padding-right:12px;vertical-align:middle"><img src="cid:nexo-logo" width="52" height="52" alt="{e(NOMBRE)}" '
            'style="display:block;border:0"></td>') if con_logo else ""
    return (
        '<div style="margin:0;padding:24px 10px;background:#eef3f9">'
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:580px;margin:0 auto;background:#ffffff;'
        'border:1px solid #d6e0ee;border-radius:12px;border-collapse:separate;font-family:Arial,Helvetica,sans-serif">'
        f'<tr><td style="padding:18px 24px 16px;border-bottom:3px solid {s["color"]}">'
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'{logo}<td style="vertical-align:middle">'
        f'<div style="font-size:22px;font-weight:bold;color:#0b2a6f;line-height:1.1">Nexo S<sup style="color:#10a77c;font-size:14px">2</sup></div>'
        f'<div style="font-size:12px;color:#6b7a96;margin-top:3px">{e(CLINICA)}</div></td></tr></table></td></tr>'
        f'<tr><td style="padding:9px 24px;background:{s["fondo"]};color:{s["color"]};font-size:12px;font-weight:bold;letter-spacing:.06em">'
        f'{e(s["nombre"])} &middot; {e(s["area"].upper())}</td></tr>'
        f'<tr><td style="padding:20px 24px 8px;color:#1d2733;font-size:15px;line-height:1.5">{contenido}</td></tr>'
        '<tr><td style="padding:14px 24px 18px;border-top:1px solid #e3e8ef;color:#8a96a8;font-size:11.5px;line-height:1.5">'
        f'Mensaje enviado por <b style="color:#6b7a96">{e(NOMBRE)}</b>, la plataforma que reúne SUMIPABON y SENTINEL PABON '
        f'de la {e(CLINICA)}.</td></tr></table></div>'
    )


def armar(msg: EmailMessage, sistema: str, cuerpo: str, cuerpo_html: str | None, logo: Path | None) -> None:
    """Pone el texto y el HTML con la marca de Nexo S² en `msg` (el logo va incrustado: no depende de internet)."""
    msg.set_content(texto(sistema, cuerpo) + pie_texto(sistema))
    contenido = cuerpo_html if cuerpo_html else html.escape(cuerpo).replace("\n", "<br>")
    con_logo = bool(logo and Path(logo).is_file())
    msg.add_alternative(_html(sistema, contenido, con_logo), subtype="html")
    if con_logo:
        parte_html = msg.get_payload()[1]
        parte_html.add_related(Path(logo).read_bytes(), "image", "png", cid="<nexo-logo>", filename="nexo-s2.png",
                               disposition="inline")
