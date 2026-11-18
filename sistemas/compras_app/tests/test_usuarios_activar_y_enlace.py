"""Botón «Desactivar / Activar» de la lista de usuarios, enlace del mensaje que sirve desde el celular y clave pegada con espacios."""

from fastapi.testclient import TestClient

from app.services import notificaciones

from tests.conftest import CLAVE_NUEVA, entrar


def _id(cliente, usuario):
    return next(x for x in cliente.get("/api/usuarios").json()["usuarios"] if x["usuario"] == usuario)["id"]


def test_desactivar_cierra_su_sesion_y_no_puede_entrar_hasta_activarlo(cliente, como):
    c = como("consulta")
    assert c.get("/api/resumen").status_code == 200
    uid = _id(cliente, "consulta1")
    r = cliente.post(f"/api/usuarios/{uid}/activo", json={"activo": False})
    assert r.status_code == 200 and r.json()["usuario"]["activo"] is False
    assert c.get("/api/resumen").status_code == 401  # su sesión se cerró al instante
    assert entrar(TestClient(cliente.app), "consulta1", CLAVE_NUEVA).status_code == 403
    # sus datos siguen iguales (no hubo que reescribirlos para desactivarlo)
    u = next(x for x in cliente.get("/api/usuarios").json()["usuarios"] if x["usuario"] == "consulta1")
    assert u["correo"] == "consulta1@prueba.com" and u["rol"] == "consulta"
    assert cliente.post(f"/api/usuarios/{uid}/activo", json={"activo": True}).status_code == 200
    assert entrar(TestClient(cliente.app), "consulta1", CLAVE_NUEVA).status_code == 200


def test_nadie_se_desactiva_a_si_mismo_ni_deja_el_sistema_sin_administrador(cliente):
    yo = _id(cliente, "admin")
    r = cliente.post(f"/api/usuarios/{yo}/activo", json={"activo": False})
    assert r.status_code == 409


def test_solo_el_administrador_puede_desactivar(cliente, como):
    uid = _id(cliente, "admin")
    assert como("prime").post(f"/api/usuarios/{uid}/activo", json={"activo": False}).status_code == 403


def test_el_enlace_no_lleva_localhost_porque_en_el_celular_no_sirve(monkeypatch):
    monkeypatch.setattr(notificaciones, "ip_de_red", lambda: "192.168.1.50")
    assert notificaciones.enlace_de_ingreso("http://localhost:8000/") == "http://192.168.1.50:8000/?ingresar=1"
    assert notificaciones.enlace_de_ingreso("http://127.0.0.1:8000") == "http://192.168.1.50:8000/?ingresar=1"
    # una dirección de verdad se respeta tal cual
    assert notificaciones.enlace_de_ingreso("http://10.0.0.7:8000/") == "http://10.0.0.7:8000/?ingresar=1"
    assert notificaciones.enlace_de_ingreso("https://compras.clinica.co") == "https://compras.clinica.co/?ingresar=1"


def test_la_clave_temporal_pegada_con_espacio_o_salto_de_linea_sirve(cliente, anonimo):
    r = cliente.post("/api/usuarios", json={"usuario": "pegado", "nombre": "Pega Do", "rol": "consulta",
                                             "correo": "pegado@prueba.com", "celular": "3207778899"})
    temporal = r.json()["clave_temporal"]
    assert entrar(anonimo, "pegado", temporal + " \n").status_code == 200
    assert entrar(TestClient(anonimo.app), "Pegado ", temporal).status_code == 200


def test_sumipabon_no_envia_whatsapp_si_su_plantilla_es_la_misma_de_sentinel(cliente, monkeypatch, tmp_path):
    """Cada sistema de Nexo S² debe tener su PROPIA plantilla de WhatsApp."""
    enviados = []
    monkeypatch.setattr(notificaciones, "enviar_whatsapp", lambda *a, **k: enviados.append(a))
    monkeypatch.setenv("COMPRAS_WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("COMPRAS_WHATSAPP_ID_NUMERO", "1")
    monkeypatch.setenv("COMPRAS_WHATSAPP_PLANTILLA", "Acceso_Nexo")
    sentinel_env = tmp_path / "sentinel.env"
    sentinel_env.write_text("SENTINEL_WHATSAPP_PLANTILLA=acceso_nexo\n", encoding="utf-8")
    monkeypatch.setenv("COMPRAS_ENV_SENTINEL", str(sentinel_env))
    r = cliente.post("/api/usuarios", json={"usuario": "doble", "nombre": "Do Ble", "rol": "consulta",
                                             "correo": "doble@prueba.com", "celular": "3201112244"}).json()
    assert enviados == [] and r["envio"]["whatsapp"]["estado"] == "no_configurado"
    assert "SENTINEL" in r["envio"]["whatsapp"]["detalle"] and r["envio"]["enlace_whatsapp"].startswith("https://wa.me/")
    # con plantillas diferentes sí se envía
    sentinel_env.write_text("SENTINEL_WHATSAPP_PLANTILLA=acceso_sentinel\n", encoding="utf-8")
    r = cliente.post("/api/usuarios", json={"usuario": "doble2", "nombre": "Do Ble", "rol": "consulta",
                                             "correo": "doble2@prueba.com", "celular": "3201112255"}).json()
    assert len(enviados) == 1 and r["envio"]["whatsapp"]["estado"] == "enviado"


def test_la_clave_temporal_pegada_con_espacio_tambien_sirve_al_cambiarla(cliente, anonimo):
    """Entrar con la temporal pegada con espacio y, en «elige tu clave», volver a pegarla igual: debe funcionar."""
    r = cliente.post("/api/usuarios", json={"usuario": "pegado2", "nombre": "Pega Dos", "rol": "consulta",
                                             "correo": "pegado2@prueba.com", "celular": "3207778800"})
    temporal = r.json()["clave_temporal"]
    assert entrar(anonimo, "pegado2", temporal + " ").status_code == 200
    r = anonimo.put("/api/sesion/clave", json={"actual": temporal + " \n", "nueva": CLAVE_NUEVA})
    assert r.status_code == 200, r.text
    assert entrar(TestClient(anonimo.app), "pegado2", CLAVE_NUEVA).status_code == 200
