"""Correo y celular de los usuarios, y el envío de usuario + clave temporal por correo y WhatsApp.

Nunca se envía nada de verdad: SMTP y la API de WhatsApp se sustituyen por dobles que guardan lo que se les pide."""

import json
import os
import sqlite3
import time
import urllib.error

import pytest

from app import database
from app.services import notificaciones, seguridad
from app.services.seguridad import SeguridadError, normalizar_celular, normalizar_correo

VARIABLES = [
    "COMPRAS_SMTP_SERVIDOR",
    "COMPRAS_SMTP_PUERTO",
    "COMPRAS_SMTP_USUARIO",
    "COMPRAS_SMTP_CLAVE",
    "COMPRAS_SMTP_REMITENTE",
    "COMPRAS_SMTP_TLS",
    "COMPRAS_WHATSAPP_TOKEN",
    "COMPRAS_WHATSAPP_ID_NUMERO",
    "COMPRAS_WHATSAPP_PLANTILLA",
    "COMPRAS_WHATSAPP_IDIOMA",
    "COMPRAS_URL_PUBLICA",
]
NUEVO = {
    "usuario": "ana.lopez",
    "nombre": "Ana López",
    "rol": "consulta",
    "correo": "Ana@Clinica.com",
    "celular": "300 123 4567",
}


def _texto(msg) -> str:
    """La parte de texto simple de un correo enviado (el correo lleva también una versión HTML)."""
    return msg.get_body(preferencelist=("plain",)).get_content()


def _html(msg) -> str:
    return msg.get_body(preferencelist=("html",)).get_content()


@pytest.fixture(autouse=True)
def sin_configuracion(monkeypatch):
    """Cada prueba parte de «nada configurado»; la que lo necesite lo activa."""
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)


@pytest.fixture
def smtp(monkeypatch):
    """SMTP falso: guarda conexiones y mensajes. `falla` = excepción que debe lanzar al enviar."""
    registro = {"mensajes": [], "conexiones": [], "falla": None, "login": None, "tls": False}

    class FalsoSMTP:
        def __init__(self, servidor, puerto, **kw):
            registro["conexiones"].append((servidor, puerto, type(self).__name__))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, **kw):
            registro["tls"] = True

        def login(self, usuario, clave):
            registro["login"] = (usuario, clave)

        def send_message(self, msg):
            if registro["falla"]:
                raise registro["falla"]
            registro["mensajes"].append(msg)

    monkeypatch.setattr(notificaciones.smtplib, "SMTP", FalsoSMTP)
    monkeypatch.setattr(notificaciones.smtplib, "SMTP_SSL", FalsoSMTP)
    monkeypatch.setenv("COMPRAS_SMTP_SERVIDOR", "smtp.prueba.com")
    monkeypatch.setenv("COMPRAS_SMTP_USUARIO", "envia@clinica.com")
    monkeypatch.setenv("COMPRAS_SMTP_CLAVE", "clave-smtp-secreta")
    return registro


@pytest.fixture
def whatsapp(monkeypatch):
    """API de WhatsApp falsa: guarda el pedido. `falla` = excepción que debe lanzar."""
    registro = {"pedidos": [], "falla": None}

    class Respuesta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def falso_urlopen(pedido, timeout=None):
        if registro["falla"]:
            raise registro["falla"]
        registro["pedidos"].append(pedido)
        return Respuesta()

    monkeypatch.setattr(notificaciones.urllib.request, "urlopen", falso_urlopen)
    monkeypatch.setenv("COMPRAS_WHATSAPP_TOKEN", "token-whatsapp-secreto")
    monkeypatch.setenv("COMPRAS_WHATSAPP_ID_NUMERO", "1234567890")
    return registro


# ------------------------------------------------------------------------------------------------ validar los datos
@pytest.mark.parametrize(
    "escrito, guardado",
    [
        ("3001234567", "+573001234567"),
        ("300 123 4567", "+573001234567"),
        ("(300) 123-4567", "+573001234567"),
        ("57 300 123 4567", "+573001234567"),
        ("+57 300 123 4567", "+573001234567"),
        ("+1 415 555 0100", "+14155550100"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_celular_se_normaliza(escrito, guardado):
    assert normalizar_celular(escrito) == guardado


@pytest.mark.parametrize(
    "malo", ["abc", "12345", "2001234567", "300123456", "+57300", "300-123-45-67-89", "4155550100"]
)
def test_celular_invalido(malo):
    with pytest.raises(SeguridadError):
        normalizar_celular(malo)


def test_correo_se_normaliza_y_se_valida():
    assert normalizar_correo("  Ana@Clinica.COM ") == "ana@clinica.com"
    assert normalizar_correo("") is None and normalizar_correo(None) is None
    for malo in ["ana", "ana@", "@clinica.com", "ana@clinica", "a na@clinica.com", "a@b.com,c@d.com"]:
        with pytest.raises(SeguridadError):
            normalizar_correo(malo)


# ------------------------------------------------------------------------------------------------ guardar el contacto
def test_se_guardan_correo_y_celular_y_se_pueden_cambiar(cliente):
    r = cliente.post("/api/usuarios", json=NUEVO)
    assert r.status_code == 201
    u = r.json()["usuario"]
    assert u["correo"] == "ana@clinica.com" and u["celular"] == "+573001234567"
    cambio = {**NUEVO, "correo": "nuevo@clinica.com", "celular": "315 789 4561", "activo": True}
    e = cliente.put(f"/api/usuarios/{u['id']}", json=cambio)
    assert e.json()["usuario"]["correo"] == "nuevo@clinica.com" and e.json()["usuario"]["celular"] == "+573157894561"
    lista = cliente.get("/api/usuarios").json()["usuarios"]
    assert [x["celular"] for x in lista if x["usuario"] == "ana.lopez"] == ["+573157894561"]


def test_contacto_invalido_no_crea_el_usuario(cliente):
    assert cliente.post("/api/usuarios", json={**NUEVO, "correo": "sin-arroba"}).status_code == 422
    assert cliente.post("/api/usuarios", json={**NUEVO, "celular": "123"}).status_code == 422
    assert "ana.lopez" not in [x["usuario"] for x in cliente.get("/api/usuarios").json()["usuarios"]]


def test_el_correo_y_el_celular_son_obligatorios(cliente):
    """Al crear o editar desde la pantalla, sin correo o sin celular no se guarda (así siempre hay a dónde enviar la clave)."""
    base = {"usuario": "sin.contacto", "nombre": "Sin Contacto", "rol": "prime"}
    for faltan, mensaje in (({}, "correo"), ({"correo": "a@b.com"}, "celular"), ({"celular": "3001234567"}, "correo")):
        r = cliente.post("/api/usuarios", json={**base, **faltan})
        assert r.status_code == 422 and mensaje in r.json()["detail"], r.text
        r = cliente.post(
            "/api/usuarios",
            json={**base, **faltan, "correo": faltan.get("correo", "  "), "celular": faltan.get("celular", "")},
        )
        assert r.status_code == 422
    assert "sin.contacto" not in [x["usuario"] for x in cliente.get("/api/usuarios").json()["usuarios"]]
    u = cliente.post("/api/usuarios", json={**base, "correo": "ok@clinica.com", "celular": "3001234567"}).json()[
        "usuario"
    ]
    for vacio in ({"correo": ""}, {"celular": ""}):  # tampoco se puede dejar vacío al editar
        e = cliente.put(
            f"/api/usuarios/{u['id']}",
            json={**base, "correo": "ok@clinica.com", "celular": "3001234567", "activo": True, **vacio},
        )
        assert e.status_code == 422, e.text


def test_base_vieja_sin_columnas_se_actualiza(tmp_path, monkeypatch):
    """Una base creada antes de existir correo/celular recibe las columnas sola, sin perder usuarios."""
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL UNIQUE COLLATE NOCASE, "
        "nombre TEXT NOT NULL, clave_hash TEXT NOT NULL, rol TEXT NOT NULL, cod_empresa TEXT, activo INTEGER NOT NULL "
        "DEFAULT 1, cambiar_clave INTEGER NOT NULL DEFAULT 0, intentos INTEGER NOT NULL DEFAULT 0, bloqueado_hasta TEXT, "
        "creado TEXT NOT NULL DEFAULT (datetime('now','localtime')), ultimo_ingreso TEXT)"
    )
    con.execute("INSERT INTO usuarios (usuario, nombre, clave_hash, rol) VALUES ('viejo', 'Viejo', 'x', 'admin')")
    con.commit()
    con.close()
    monkeypatch.setenv("COMPRAS_DB", str(ruta))
    database.iniciar_db()
    database.iniciar_db()  # dos veces no debe fallar
    con = sqlite3.connect(ruta)
    assert {"correo", "celular"} <= {f[1] for f in con.execute("PRAGMA table_info(usuarios)")}
    assert con.execute("SELECT usuario, correo FROM usuarios").fetchone() == ("viejo", None)
    con.close()


# ------------------------------------------------------------------------------------------------ envío: nada configurado
def test_sin_configurar_no_envia_nada_pero_ofrece_el_enlace_de_whatsapp(cliente):
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    assert r["envio"]["correo"]["estado"] == "no_configurado"
    assert r["envio"]["whatsapp"]["estado"] == "no_configurado"
    enlace = r["envio"]["enlace_whatsapp"]
    assert enlace.startswith("https://wa.me/573001234567?text=")
    assert "ana.lopez" in enlace and r["clave_temporal"] in enlace  # el mensaje ya viene escrito
    assert cliente.get("/api/usuarios").json()["canales"] == {"correo": False, "whatsapp": False}


def test_sin_datos_no_hay_que_enviar():
    """Un usuario sin correo ni celular (p. ej. el «admin» inicial) no rompe nada: cada canal dice «sin_dato»."""
    r = notificaciones.enviar_credenciales({"nombre": "Solo", "usuario": "solo.usuario"}, "Abc12345xy", "http://x")
    assert r["correo"]["estado"] == "sin_dato" and r["whatsapp"]["estado"] == "sin_dato"
    assert "enlace_whatsapp" not in r


# ------------------------------------------------------------------------------------------------ envío por correo
def test_se_envia_el_correo_con_usuario_y_clave(cliente, smtp, monkeypatch):
    monkeypatch.setenv("COMPRAS_URL_PUBLICA", "http://compras.clinica.local:8000/")
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    assert r["envio"]["correo"]["estado"] == "enviado"
    assert len(smtp["mensajes"]) == 1
    msg = smtp["mensajes"][0]
    cuerpo = _texto(msg)
    assert msg["To"] == "ana@clinica.com" and "SUMIPABON" in msg["Subject"]
    assert "ana.lopez" in cuerpo and r["clave_temporal"] in cuerpo and "Ana López" in cuerpo
    assert "http://compras.clinica.local:8000/?ingresar=1" in cuerpo  # la pública, sin «/» sobrante y con «?ingresar=1»
    assert smtp["login"] == ("envia@clinica.com", "clave-smtp-secreta") and smtp["tls"] is True
    assert smtp["conexiones"][0][:2] == ("smtp.prueba.com", 587)


def test_puerto_465_usa_ssl_sin_starttls(cliente, smtp, monkeypatch):
    monkeypatch.setenv("COMPRAS_SMTP_PUERTO", "465")
    cliente.post("/api/usuarios", json=NUEVO)
    assert smtp["conexiones"][0] == ("smtp.prueba.com", 465, "FalsoSMTP") and smtp["tls"] is False


def test_si_el_correo_falla_el_usuario_se_crea_igual_y_el_error_no_filtra_claves(cliente, smtp):
    smtp["falla"] = OSError("no hay red")
    r = cliente.post("/api/usuarios", json=NUEVO)
    assert r.status_code == 201
    envio = r.json()["envio"]["correo"]
    assert envio["estado"] == "error"
    for secreto in (r.json()["clave_temporal"], "clave-smtp-secreta"):
        assert secreto not in envio["detalle"]
    assert "ana.lopez" in [x["usuario"] for x in cliente.get("/api/usuarios").json()["usuarios"]]


def test_clave_smtp_rechazada_se_explica(cliente, smtp):
    smtp["falla"] = notificaciones.smtplib.SMTPAuthenticationError(535, b"mal")
    detalle = cliente.post("/api/usuarios", json=NUEVO).json()["envio"]["correo"]["detalle"]
    assert "rechazó" in detalle and "clave-smtp-secreta" not in detalle


# ------------------------------------------------------------------------------------------------ envío por WhatsApp
def test_whatsapp_con_plantilla_envia_las_cuatro_variables(cliente, whatsapp, monkeypatch):
    monkeypatch.setenv("COMPRAS_WHATSAPP_PLANTILLA", "acceso_sumipabon")
    monkeypatch.setenv("COMPRAS_URL_PUBLICA", "http://compras.clinica.local")
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    assert r["envio"]["whatsapp"]["estado"] == "enviado" and "enlace_whatsapp" not in r["envio"]
    pedido = whatsapp["pedidos"][0]
    assert pedido.full_url == "https://graph.facebook.com/v20.0/1234567890/messages"
    assert pedido.get_header("Authorization") == "Bearer token-whatsapp-secreto"
    cuerpo = json.loads(pedido.data)
    assert cuerpo["to"] == "573001234567" and cuerpo["type"] == "template"
    assert cuerpo["template"]["name"] == "acceso_sumipabon" and cuerpo["template"]["language"]["code"] == "es"
    valores = [p["text"] for p in cuerpo["template"]["components"][0]["parameters"]]
    assert valores == ["Ana López", "ana.lopez", r["clave_temporal"], "http://compras.clinica.local/?ingresar=1&usuario=ana.lopez"]


def test_whatsapp_sin_plantilla_envia_texto_simple(cliente, whatsapp):
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    cuerpo = json.loads(whatsapp["pedidos"][0].data)
    assert cuerpo["type"] == "text" and r["clave_temporal"] in cuerpo["text"]["body"]


def test_error_de_whatsapp_se_informa_y_ofrece_el_envio_manual(cliente, whatsapp):
    import io

    cuerpo_error = json.dumps({"error": {"message": "Recipient phone number not in allowed list"}}).encode()
    whatsapp["falla"] = urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(cuerpo_error))
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    w = r["envio"]["whatsapp"]
    assert w["estado"] == "error" and "400" in w["detalle"] and "allowed list" in w["detalle"]
    assert "token-whatsapp-secreto" not in w["detalle"] and r["clave_temporal"] not in w["detalle"]
    assert r["envio"]["enlace_whatsapp"].startswith("https://wa.me/573001234567")  # queda el envío a mano


def test_whatsapp_sin_conexion(cliente, whatsapp):
    whatsapp["falla"] = urllib.error.URLError("sin red")
    w = cliente.post("/api/usuarios", json=NUEVO).json()["envio"]["whatsapp"]
    assert w["estado"] == "error" and "conectar" in w["detalle"]


# ------------------------------------------------------------------------------------------------ restablecer la clave
def test_restablecer_la_clave_la_reenvia_con_la_clave_nueva(cliente, smtp):
    u = cliente.post("/api/usuarios", json=NUEVO).json()
    r = cliente.post(f"/api/usuarios/{u['usuario']['id']}/clave").json()
    assert r["clave_temporal"] != u["clave_temporal"] and r["envio"]["correo"]["estado"] == "enviado"
    assert len(smtp["mensajes"]) == 2
    assert r["clave_temporal"] in _texto(smtp["mensajes"][1])
    assert u["clave_temporal"] not in _texto(smtp["mensajes"][1])


def test_editar_el_contacto_no_envia_nada(cliente, smtp):
    u = cliente.post("/api/usuarios", json=NUEVO).json()["usuario"]
    cliente.put(f"/api/usuarios/{u['id']}", json={**NUEVO, "correo": "otro@clinica.com", "activo": True})
    assert len(smtp["mensajes"]) == 1  # solo el de la creación


def test_la_clave_no_queda_guardada_en_la_base(cliente, smtp):
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    con = database.conectar()
    try:
        filas = [tuple(f) for f in con.execute("SELECT * FROM usuarios")]
    finally:
        con.close()
    assert all(r["clave_temporal"] not in str(f) for f in filas)


def test_solo_el_administrador_crea_usuarios_y_dispara_envios(como, smtp):
    prime, consulta = como("prime"), como("consulta")  # (al crearlos, el administrador les envía su clave)
    enviados = len(smtp["mensajes"])
    assert prime.post("/api/usuarios", json=NUEVO).status_code == 403
    assert consulta.post("/api/usuarios", json=NUEVO).status_code == 403
    assert len(smtp["mensajes"]) == enviados  # ellos no pueden crear usuarios ni disparar envíos


def test_mensaje_no_promete_lo_que_no_hay():
    texto = notificaciones.mensaje("Ana", "ana", "Abc12345xy", "http://x")
    assert "SUMIPABON" in texto and "Mesa de ofertas" not in texto
    assert "ana" in texto and "Abc12345xy" in texto and "elegir tu propia clave" in texto
    assert seguridad.ROLES  # (el módulo de seguridad sigue disponible junto al de notificaciones)


# ------------------------------------------------------------------------------------------------ archivo .env
def test_se_lee_el_archivo_env_con_las_manias_de_windows(tmp_path):
    ruta = tmp_path / "x.env"
    ruta.write_bytes(
        "\ufeff# comentario\r\n\r\nCOMPRAS_SMTP_SERVIDOR=smtp.gmail.com\r\n"
        "export COMPRAS_SMTP_USUARIO = ana@clinica.com \r\n"
        'COMPRAS_SMTP_REMITENTE="SUMIPABON <ana@clinica.com>"\r\n'
        "COMPRAS_SMTP_CLAVE=abc=def\r\nlinea sin igual\r\n".encode("utf-8")
    )
    assert notificaciones.leer_archivo_env(ruta) == {
        "COMPRAS_SMTP_SERVIDOR": "smtp.gmail.com",
        "COMPRAS_SMTP_USUARIO": "ana@clinica.com",
        "COMPRAS_SMTP_REMITENTE": "SUMIPABON <ana@clinica.com>",
        "COMPRAS_SMTP_CLAVE": "abc=def",
    }


def test_con_el_archivo_env_el_correo_se_envia_solo(cliente, smtp, monkeypatch, tmp_path):
    """Sin variables del sistema: basta el archivo .env en la carpeta del proyecto."""
    for v in ("COMPRAS_SMTP_SERVIDOR", "COMPRAS_SMTP_USUARIO", "COMPRAS_SMTP_CLAVE"):
        monkeypatch.delenv(v)
    env = tmp_path / ".env"
    env.write_text(
        "COMPRAS_SMTP_SERVIDOR=smtp.desdearchivo.com\nCOMPRAS_SMTP_USUARIO=envia@clinica.com\n"
        "COMPRAS_SMTP_CLAVE=abcd efgh ijkl mnop\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPRAS_ENV", str(env))
    assert cliente.get("/api/usuarios").json()["canales"]["correo"] is True
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    assert r["envio"]["correo"]["estado"] == "enviado"
    assert smtp["conexiones"][0][:2] == ("smtp.desdearchivo.com", 587)
    assert smtp["login"] == ("envia@clinica.com", "abcdefghijklmnop")  # la clave de Google con espacios se acepta


def test_la_variable_del_sistema_gana_al_archivo_y_los_cambios_del_archivo_se_notan(
    cliente, smtp, monkeypatch, tmp_path
):
    env = tmp_path / ".env"
    env.write_text("COMPRAS_SMTP_SERVIDOR=del-archivo.com\n", encoding="utf-8")
    monkeypatch.setenv("COMPRAS_ENV", str(env))
    cliente.post("/api/usuarios", json=NUEVO)
    assert smtp["conexiones"][-1][0] == "smtp.prueba.com"  # la variable del sistema (fixture smtp) gana

    monkeypatch.delenv("COMPRAS_SMTP_SERVIDOR")
    cliente.post(
        "/api/usuarios", json={**NUEVO, "usuario": "otra.persona", "correo": "o2@x.com", "celular": "3100000002"}
    )
    assert smtp["conexiones"][-1][0] == "del-archivo.com"

    env.write_text("COMPRAS_SMTP_SERVIDOR=nuevo-servidor.com\n", encoding="utf-8")
    os.utime(env, ns=(time.time_ns() + 5_000_000_000, time.time_ns() + 5_000_000_000))  # que el cambio se note siempre
    cliente.post(
        "/api/usuarios", json={**NUEVO, "usuario": "tercera.persona", "correo": "o3@x.com", "celular": "3100000003"}
    )
    assert smtp["conexiones"][-1][0] == "nuevo-servidor.com"  # se editó el archivo sin reiniciar


def test_sin_archivo_ni_variables_el_mensaje_dice_donde_configurar(cliente):
    d = cliente.post("/api/usuarios", json=NUEVO).json()["envio"]
    assert "COMPRAS_SMTP_SERVIDOR" in d["correo"]["detalle"] and ".env" in d["correo"]["detalle"]
    assert "COMPRAS_WHATSAPP_TOKEN" in d["whatsapp"]["detalle"]


def test_probar_correo_desde_la_terminal(smtp, capsys):
    from app import usuarios_cli

    assert usuarios_cli.main(["probar-correo", "yo@clinica.com"]) == 0
    assert "Enviado a yo@clinica.com" in capsys.readouterr().out
    assert smtp["mensajes"][0]["To"] == "yo@clinica.com"
    smtp["falla"] = OSError("sin red")
    assert usuarios_cli.main(["probar-correo", "yo@clinica.com"]) == 1
    assert "NO se pudo enviar" in capsys.readouterr().out


def test_probar_correo_sin_configurar_explica_que_falta(capsys):
    from app import usuarios_cli

    assert usuarios_cli.main(["probar-correo", "yo@clinica.com"]) == 1
    salida = capsys.readouterr().out
    assert "NO está configurado" in salida and "COMPRAS_SMTP_SERVIDOR" in salida


def test_la_direccion_del_mensaje_sale_del_archivo_env(cliente, smtp, monkeypatch, tmp_path):
    """COMPRAS_URL_PUBLICA escrita en el .env (no solo en las variables del sistema) es la dirección que va en el correo."""
    env = tmp_path / "config.env"
    env.write_text("COMPRAS_URL_PUBLICA=http://172.16.21.121:8000\n", encoding="utf-8")
    monkeypatch.setenv("COMPRAS_ENV", str(env))
    cliente.post("/api/usuarios", json=NUEVO)
    assert "http://172.16.21.121:8000" in _texto(smtp["mensajes"][0])
    assert "127.0.0.1" not in _texto(smtp["mensajes"][0])


def test_el_correo_oculta_la_ip_detras_de_un_boton(cliente, smtp, monkeypatch):
    """En la versión HTML la dirección va DENTRO del botón «Entrar a SUMIPABON», no escrita como texto visible."""
    import re

    monkeypatch.setenv("COMPRAS_URL_PUBLICA", "http://172.16.21.121:8000")
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    cuerpo = _html(smtp["mensajes"][0])
    assert 'href="http://172.16.21.121:8000/?ingresar=1&amp;usuario=ana.lopez"' in cuerpo and "Entrar a SUMIPABON" in cuerpo
    visible = re.sub(r"<[^>]+>", " ", cuerpo)  # lo que se ve: sin las etiquetas (y por tanto sin el href)
    assert "172.16.21.121" not in visible
    assert "ana.lopez" in visible and r["clave_temporal"] in visible
    assert "http://172.16.21.121:8000" in _texto(smtp["mensajes"][0])  # el texto simple sí la lleva (no tiene botones)


def test_el_html_del_mensaje_escapa_todo_y_no_acepta_enlaces_raros():
    peligroso = notificaciones.mensaje_html("<script>alert(1)</script>", 'u"><b>', "c<>&", 'http://x/?a=1&b="2')
    assert "<script>" not in peligroso and "&lt;script&gt;" in peligroso
    assert 'u"><b>' not in peligroso and "c&lt;&gt;&amp;" in peligroso
    assert 'href="http://x/?a=1&amp;b=&quot;2"' in peligroso  # la dirección también se escapa
    sin_boton = notificaciones.mensaje_html("Ana", "ana", "Abc12345xy", "javascript:alert(1)")
    assert "<a " not in sin_boton and "javascript" not in sin_boton  # solo http(s) se vuelve botón


def test_el_enlace_del_mensaje_siempre_abre_la_pantalla_de_ingreso(cliente, smtp, monkeypatch):
    """El enlace termina en «/?ingresar=1»: la página cierra la sesión que hubiera y pide usuario y clave."""
    from urllib.parse import unquote

    assert notificaciones.enlace_de_ingreso("http://x:8000") == "http://x:8000/?ingresar=1"
    assert notificaciones.enlace_de_ingreso("http://x:8000/") == "http://x:8000/?ingresar=1"  # sin «/» doble
    cliente.post(
        "/api/usuarios", json=NUEVO
    )  # sin COMPRAS_URL_PUBLICA: usa la dirección con que entró el administrador
    assert "http://testserver/?ingresar=1&usuario=ana.lopez" in _texto(smtp["mensajes"][0])  # con el usuario ya escrito
    assert 'href="http://testserver/?ingresar=1&amp;usuario=ana.lopez"' in _html(smtp["mensajes"][0])
    monkeypatch.setenv("COMPRAS_URL_PUBLICA", "http://sumipabon:8000/")
    otro = {**NUEVO, "usuario": "otra.persona", "correo": "otra@clinica.com", "celular": "3100000004"}
    r = cliente.post("/api/usuarios", json=otro).json()
    assert "http://sumipabon:8000/?ingresar=1" in unquote(
        r["envio"]["enlace_whatsapp"]
    )  # también en el WhatsApp manual


# ------------------------------------------------------------------------------------------------ texto propio al restablecer
def test_el_texto_de_restablecer_no_dice_que_es_una_cuenta_nueva():
    nueva = notificaciones.mensaje("Ana", "ana", "Abc12345xy", "http://x")
    reset = notificaciones.mensaje("Ana", "ana", "Abc12345xy", "http://x", restablecida=True)
    assert "ya tienes acceso" in nueva and "se restableció" not in nueva
    assert "se restableció tu clave de acceso" in reset and "ya tienes acceso" not in reset
    assert "avisa al administrador" in reset and "primera vez" not in reset
    assert "Abc12345xy" in reset and "Hola Ana" in reset  # sigue llevando el usuario, la clave y el nombre
    assert notificaciones.asunto() != notificaciones.asunto(True) and "restableció" in notificaciones.asunto(True)


def test_el_html_de_restablecer_tambien_cambia_y_sigue_escapando():
    reset = notificaciones.mensaje_html("<b>X</b>", "u", "c", "http://x", restablecida=True)
    assert "se restableció tu clave de acceso" in reset and "ya tienes acceso" not in reset
    assert "&lt;b&gt;X&lt;/b&gt;" in reset and "Entrar a SUMIPABON" in reset  # el botón se conserva
    assert "ya tienes acceso" in notificaciones.mensaje_html("Ana", "u", "c", "http://x")


def test_crear_y_restablecer_envian_correos_distintos_y_con_el_nombre_actual(cliente, smtp):
    """El saludo usa el Nombre que tenga guardado el usuario en ese momento: si se corrige, el correo siguiente lo trae."""
    u = cliente.post("/api/usuarios", json={**NUEVO, "nombre": "prueba"}).json()
    primero = smtp["mensajes"][-1]
    assert primero["Subject"] == "Nexo S² · Tu acceso a SUMIPABON"
    assert "Hola prueba, ya tienes acceso" in _texto(primero) and "ya tienes acceso" in _html(primero)

    cambio = {**NUEVO, "nombre": "Josea Sánchez", "activo": True}
    assert cliente.put(f"/api/usuarios/{u['usuario']['id']}", json=cambio).status_code == 200
    assert len(smtp["mensajes"]) == 1  # editar el nombre no envía nada
    r = cliente.post(f"/api/usuarios/{u['usuario']['id']}/clave").json()
    segundo = smtp["mensajes"][-1]
    assert segundo["Subject"] == "Nexo S² · Se restableció tu clave de SUMIPABON"
    assert "Hola Josea Sánchez, se restableció tu clave de acceso" in _texto(segundo)
    assert "se restableció tu clave de acceso" in _html(segundo) and "ya tienes acceso" not in _html(segundo)
    assert r["clave_temporal"] in _texto(segundo) and r["clave_temporal"] != u["clave_temporal"]


def test_el_enlace_manual_de_whatsapp_tambien_usa_el_texto_de_restablecer(cliente):
    from urllib.parse import unquote

    u = cliente.post("/api/usuarios", json=NUEVO).json()
    assert "ya tienes acceso" in unquote(u["envio"]["enlace_whatsapp"])
    r = cliente.post(f"/api/usuarios/{u['usuario']['id']}/clave").json()
    texto = unquote(r["envio"]["enlace_whatsapp"])
    assert "se restableció tu clave de acceso" in texto and "ya tienes acceso" not in texto


def test_whatsapp_en_texto_simple_usa_el_texto_de_restablecer(cliente, whatsapp):
    u = cliente.post("/api/usuarios", json=NUEVO).json()
    assert "ya tienes acceso" in json.loads(whatsapp["pedidos"][-1].data)["text"]["body"]
    cliente.post(f"/api/usuarios/{u['usuario']['id']}/clave")
    assert "se restableció tu clave de acceso" in json.loads(whatsapp["pedidos"][-1].data)["text"]["body"]


def test_whatsapp_con_plantilla_propia_para_restablecer(cliente, whatsapp, monkeypatch):
    monkeypatch.setenv("COMPRAS_WHATSAPP_PLANTILLA", "acceso_sumipabon")
    monkeypatch.setenv("COMPRAS_WHATSAPP_PLANTILLA_RESTABLECER", "clave_restablecida")
    u = cliente.post("/api/usuarios", json=NUEVO).json()
    cliente.post(f"/api/usuarios/{u['usuario']['id']}/clave")
    nombres = [json.loads(p.data)["template"]["name"] for p in whatsapp["pedidos"]]
    assert nombres == ["acceso_sumipabon", "clave_restablecida"]  # cada caso con su plantilla


def test_whatsapp_sin_plantilla_de_restablecer_usa_la_normal(cliente, whatsapp, monkeypatch):
    monkeypatch.setenv("COMPRAS_WHATSAPP_PLANTILLA", "acceso_sumipabon")
    u = cliente.post("/api/usuarios", json=NUEVO).json()
    cliente.post(f"/api/usuarios/{u['usuario']['id']}/clave")
    nombres = [json.loads(p.data)["template"]["name"] for p in whatsapp["pedidos"]]
    assert nombres == ["acceso_sumipabon", "acceso_sumipabon"]  # no se rompe: reutiliza la que ya hay


# ------------------------------------------------------------------------------------------------ diagnóstico del archivo .env
def test_el_mensaje_de_correo_no_configurado_dice_que_archivo_busco(monkeypatch, tmp_path):
    """Si el correo no está configurado, la ventana de la clave temporal dice DÓNDE se buscó el .env y qué pasó con él (no hay que adivinar)."""
    destino = tmp_path / ".env"
    monkeypatch.setenv("COMPRAS_ENV", str(destino))
    assert f"No existe el archivo {destino}" in notificaciones.diagnostico_env()
    # el error más común en Windows: el Bloc de notas guardó «.env» como «.env.txt»
    (tmp_path / ".env.txt").write_text("COMPRAS_SMTP_SERVIDOR=smtp.gmail.com\n", encoding="utf-8")
    d = notificaciones.diagnostico_env()
    assert "Encontré «.env.txt»" in d and "debe llamarse exactamente .env" in d
    (tmp_path / ".env.txt").unlink()
    (tmp_path / ".env.ejemplo").write_text("x", encoding="utf-8")
    assert "Copia «.env.ejemplo» como «.env»" in notificaciones.diagnostico_env()
    # el archivo existe pero sin la línea del servidor
    destino.write_text("COMPRAS_SMTP_USUARIO=a@b.com\n", encoding="utf-8")
    assert "el archivo existe, pero no trae una línea COMPRAS_SMTP_SERVIDOR" in notificaciones.diagnostico_env()


def test_al_crear_un_usuario_sin_correo_configurado_el_detalle_incluye_el_diagnostico(cliente):
    r = cliente.post("/api/usuarios", json=NUEVO).json()
    detalle = r["envio"]["correo"]["detalle"]
    assert r["envio"]["correo"]["estado"] == "no_configurado"
    assert (
        "falta COMPRAS_SMTP_SERVIDOR" in detalle and "No existe el archivo" in detalle
    )  # la configuración de las pruebas apunta a un .env que no existe


# ------------------------------------------------------------------------------------------------ marca Nexo S²
def test_los_correos_salen_con_la_marca_nexo_s2(cliente, smtp, monkeypatch):
    """Remitente «Nexo S²» (con la dirección configurada), asunto con «Nexo S² · », logo incrustado y franja SUMIPABON."""
    monkeypatch.setenv("COMPRAS_SMTP_REMITENTE", "SUMIPABON <compras@clinica.com>")
    cliente.post("/api/usuarios", json=NUEVO)
    msg = smtp["mensajes"][-1]
    from email.utils import parseaddr

    assert parseaddr(str(msg["From"])) == ("Nexo S²", "compras@clinica.com")
    assert msg["Subject"].startswith("Nexo S² · ")
    html = _html(msg)
    assert 'src="cid:nexo-logo"' in html and "SUMIPABON &middot; COMPRAS Y SUMINISTROS" in html
    assert any(p.get_content_type() == "image/png" for p in msg.walk())  # el logo va dentro del correo
    texto = _texto(msg)
    assert texto.startswith("Nexo S² · SUMIPABON") and texto.count("Nexo S² · SUMIPABON (Compras") == 1
