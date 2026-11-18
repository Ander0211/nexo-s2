"""RESTAURAR: deshacer la decisión sobre la ficha de un proveedor (aprobada o rechazada) y dejarla otra vez PENDIENTE DE REVISIÓN.

Si estaba aprobada, además se devuelven las ofertas: las que creó la aprobación se quitan y las que actualizó vuelven a su precio de antes (una «foto» que se
guarda al aprobar). Datos de conftest.py: A1 (comprar 80): BETA $85 es la mejor · GAMA $95 · ALFA $100. C3 (5, solo ALFA $50) · 0041 (6) · inversión 7.092.
"""

import sqlite3

from app import database
from app.services import notificaciones
from tests.conftest import excel_bytes
from tests.test_cantidades_y_fichas import _sql
from tests.test_ofertas_proveedor import _gama, _mejor, _ofertas, _subir


def _lote(cliente, como, valor=70, producto="A1", archivo="ficha.xlsx"):
    return _subir(
        _gama(como), excel_bytes([{"COD_PRODUCTO": producto, "VALOR": valor, "PRESENTACION": "X10"}]), archivo
    ).json()["lote"]


def _aprobar(c, lote):
    r = c.post(f"/api/pendientes/{lote}/aprobar")
    assert r.status_code == 200, r.text
    return r


def _restaurar(c, lote):
    return c.post(f"/api/pendientes/{lote}/restaurar")


def _estado(c, lote):
    return c.get(f"/api/pendientes/{lote}").json()["lote"]


# ================================================================================================ una ficha RECHAZADA
def test_restaurar_una_ficha_rechazada_la_deja_pendiente_y_se_puede_decidir_de_nuevo(cliente, como):
    gama = _gama(como)
    lote = _lote(cliente, como)
    assert (
        cliente.post(f"/api/pendientes/{lote}/rechazar", json={"motivo": "Precio fuera de lo acordado"}).status_code
        == 200
    )
    assert gama.get("/api/proveedor/ofertas").json()[0]["motivo"] == "Precio fuera de lo acordado"
    r = _restaurar(cliente, lote)
    assert r.status_code == 200 and {k: v for k, v in r.json().items() if k != "correo"} == {
        "lote": lote,
        "estado": "pendiente",
        "antes": "rechazada",
        "revertidas": 0,
        "no_tocadas": 0,
    }
    assert (
        r.json()["correo"]["estado"] == "no_configurado"
    )  # y trae cómo salió el correo (aquí no hay correo configurado)
    d = _estado(cliente, lote)
    assert (
        d["estado"] == "pendiente" and d["motivo"] is None and d["revisado_por"] is None and d["fecha_revision"] is None
    )
    assert (
        cliente.get("/api/resumen").json()["ofertas_pendientes"] == 1
    )  # vuelve a contar entre las que esperan revisión
    visto = gama.get("/api/proveedor/ofertas").json()[0]
    assert visto["estado"] == "pendiente" and visto["motivo"] is None  # y el proveedor ya no ve el rechazo
    _aprobar(cliente, lote)  # ahora se puede decidir otra vez
    assert _estado(cliente, lote)["estado"] == "aprobada"


# ================================================================================================ una ficha APROBADA
def test_restaurar_una_ficha_aprobada_quita_las_ofertas_que_creo_y_vuelve_todo_a_como_estaba(cliente, como):
    antes = _ofertas(cliente)
    lote = _lote(cliente, como)
    _aprobar(cliente, lote)
    assert _mejor(cliente, "A1")["empresa"] == "GAMA LTDA" and _ofertas(cliente)[("GAMA LTDA", "subido")] == 70
    r = _restaurar(cliente, lote)
    assert (
        r.status_code == 200
        and r.json()["antes"] == "aprobada"
        and (r.json()["revertidas"], r.json()["no_tocadas"]) == (1, 0)
    )
    assert _ofertas(cliente) == antes  # la oferta que creó la aprobación ya no está
    assert _mejor(cliente, "A1")["empresa"] == "BETA SAS"  # y la mejor vuelve a ser la de antes
    assert (
        cliente.get("/api/resumen").json()["inversion_total"] == 85 * 80 + 50 * 5 + 7 * 6
    )  # el total del tablero también
    assert (
        _estado(cliente, lote)["estado"] == "pendiente"
        and cliente.get("/api/resumen").json()["ofertas_pendientes"] == 1
    )
    _aprobar(cliente, lote)  # y se puede aprobar de nuevo: las ofertas vuelven
    assert _mejor(cliente, "A1")["empresa"] == "GAMA LTDA"


def test_restaurar_devuelve_el_precio_de_antes_a_una_oferta_que_la_aprobacion_actualizo(cliente, como):
    primero = _lote(cliente, como, valor=70, archivo="primera.xlsx")
    _aprobar(cliente, primero)
    segundo = _lote(cliente, como, valor=60, archivo="segunda.xlsx")
    _aprobar(cliente, segundo)  # actualiza la misma oferta «subida»: $70 → $60
    assert _ofertas(cliente)[("GAMA LTDA", "subido")] == 60
    r = _restaurar(cliente, segundo)
    assert r.status_code == 200 and r.json()["revertidas"] == 1
    assert _ofertas(cliente)[("GAMA LTDA", "subido")] == 70  # vuelve a lo de antes, no desaparece
    oferta = next(
        o
        for o in cliente.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["ofertas"]
        if o["origen"] == "subido"
    )
    assert oferta["presentacion"] == "X10" and _estado(cliente, segundo)["estado"] == "pendiente"


def test_si_alguien_cambio_el_precio_despues_de_aprobar_no_se_pisa(cliente, como):
    lote = _lote(cliente, como)
    _aprobar(cliente, lote)
    _sql(
        "UPDATE ofertas SET valor = 65 WHERE cod_producto = 'A1' AND origen = 'subido'"
    )  # alguien lo cambió a mano después
    r = _restaurar(cliente, lote)
    assert r.status_code == 200 and (r.json()["revertidas"], r.json()["no_tocadas"]) == (0, 1)
    assert _ofertas(cliente)[("GAMA LTDA", "subido")] == 65  # se respeta lo que cambió
    assert _estado(cliente, lote)["estado"] == "pendiente"


# ================================================================================================ protecciones
def test_no_se_restaura_una_ficha_vieja_si_hay_una_aprobada_mas_reciente_ni_si_hay_otra_pendiente(cliente, como):
    primero = _lote(cliente, como, valor=70, archivo="primera.xlsx")
    _aprobar(cliente, primero)
    segundo = _lote(cliente, como, valor=60, archivo="segunda.xlsx")
    _aprobar(cliente, segundo)
    r = _restaurar(cliente, primero)
    assert r.status_code == 409 and "más reciente" in r.json()["detail"]  # la 2.ª pudo cambiar los mismos precios
    assert (
        _estado(cliente, primero)["estado"] == "aprobada" and _ofertas(cliente)[("GAMA LTDA", "subido")] == 60
    )  # no se tocó nada
    assert _restaurar(cliente, segundo).status_code == 200  # la última sí
    r = _restaurar(cliente, primero)
    assert (
        r.status_code == 409 and "pendiente" in r.json()["detail"]
    )  # y ahora la 2.ª está pendiente: no pueden ser dos a la vez
    assert _estado(cliente, primero)["estado"] == "aprobada"


def test_una_ficha_aprobada_antes_de_existir_restaurar_no_se_puede_deshacer_sola(cliente, como):
    lote = _lote(cliente, como)
    _aprobar(cliente, lote)
    _sql(
        "UPDATE ofertas_lote SET antes_existia = NULL, antes_valor = NULL, antes_presentacion = NULL, antes_creado = NULL"
    )  # como una aprobación vieja
    r = _restaurar(cliente, lote)
    assert r.status_code == 409 and "antes de que existiera" in r.json()["detail"]
    assert (
        _estado(cliente, lote)["estado"] == "aprobada" and _ofertas(cliente)[("GAMA LTDA", "subido")] == 70
    )  # nada cambió


def test_solo_se_restaura_lo_que_ya_se_decidio(cliente, como):
    lote = _lote(cliente, como)
    r = _restaurar(cliente, lote)
    assert r.status_code == 409 and "ya está pendiente" in r.json()["detail"]
    reemplazada = _lote(cliente, como, archivo="otra.xlsx")  # una ficha nueva reemplaza a la pendiente
    assert _estado(cliente, lote)["estado"] == "reemplazada" and _restaurar(cliente, lote).status_code == 409
    assert _restaurar(cliente, 99999).status_code == 404
    assert _estado(cliente, reemplazada)["estado"] == "pendiente"


def _correos_de(monkeypatch, falla=False):
    """Captura TODOS los correos que salen (asunto, destino, texto y HTML)."""
    enviados = []

    def enviar(destino, asunto, cuerpo, html=None):
        if falla:
            raise notificaciones.NotificacionError("el servidor de correo no respondió")
        enviados.append({"a": destino, "asunto": asunto, "cuerpo": cuerpo, "html": html})

    monkeypatch.setattr(notificaciones, "correo_configurado", lambda: True)
    monkeypatch.setattr(notificaciones, "enviar_correo", enviar)
    return enviados


ASUNTO_RESTAURAR = "Estamos revisando de nuevo sus ofertas · SUMIPABON"


def test_al_restaurar_se_le_avisa_al_proveedor_que_se_revisan_de_nuevo_sus_ofertas(cliente, como, monkeypatch):
    enviados = _correos_de(monkeypatch)
    lote = _lote(cliente, como)
    _aprobar(cliente, lote)
    enviados.clear()  # solo interesa lo que sale al restaurar (el de aprobación ya salió)
    r = _restaurar(cliente, lote)
    assert r.status_code == 200 and r.json()["correo"]["estado"] == "enviado"
    assert [m["a"] for m in enviados] == [
        "gama.proveedor@prueba.com"
    ]  # a quien subió la ficha (y al contacto de su empresa, sin repetir)
    m = enviados[0]
    assert m["asunto"] == ASUNTO_RESTAURAR
    for texto in (m["cuerpo"], m["html"]):
        assert (
            "Lo sentimos" in texto
            and "se encuentra revisando de nuevo las ofertas que" in texto
            and "Muy pronto tendrá noticias" in texto
        )
        assert "GAMA LTDA" in texto  # (en el HTML el nombre va en negrita, por eso se comprueba aparte)
        assert "ficha.xlsx" in texto and "Clínica Pabón" in texto
        assert (
            "BETA SAS" not in texto and "ALFA SAS" not in texto and "$" not in texto and "aprobó" not in texto
        )  # nada de otros proveedores ni precios


def test_tambien_se_avisa_al_restaurar_una_ficha_rechazada_y_solo_una_vez(cliente, como, monkeypatch):
    enviados = _correos_de(monkeypatch)
    lote = _lote(cliente, como)
    assert (
        cliente.post(f"/api/pendientes/{lote}/rechazar", json={"motivo": "Precio fuera de lo acordado"}).status_code
        == 200
    )
    enviados.clear()
    assert _restaurar(cliente, lote).status_code == 200
    assert [m["asunto"] for m in enviados] == [ASUNTO_RESTAURAR]  # un solo correo
    assert _restaurar(cliente, lote).status_code == 409  # ya está pendiente: no se restaura otra vez...
    assert len(enviados) == 1  # ...ni se manda otro correo
    assert _estado(cliente, lote)["estado"] == "pendiente"


def test_restaurar_funciona_aunque_el_correo_no_este_configurado_o_falle(cliente, como, monkeypatch):
    lote = _lote(cliente, como)
    _aprobar(cliente, lote)
    r = _restaurar(cliente, lote)  # sin correo configurado
    assert (
        r.status_code == 200
        and r.json()["correo"]["estado"] == "no_configurado"
        and "COMPRAS_SMTP_SERVIDOR" in r.json()["correo"]["detalle"]
    )
    assert (
        _estado(cliente, lote)["estado"] == "pendiente" and _mejor(cliente, "A1")["empresa"] == "BETA SAS"
    )  # y todo quedó restaurado
    _correos_de(monkeypatch, falla=True)
    _aprobar(cliente, lote)
    r = _restaurar(cliente, lote)
    assert (
        r.status_code == 200
        and r.json()["correo"]["estado"] == "error"
        and "no respondió" in r.json()["correo"]["detalle"]
    )
    assert _estado(cliente, lote)["estado"] == "pendiente"  # la restauración vale aunque el correo no salga


def test_el_correo_de_restauracion_sin_destinos_o_con_caracteres_raros(monkeypatch):
    assert notificaciones.enviar_restauracion_oferta([], "X", "2026-10-12 10:00", None)["estado"] == "sin_dato"
    enviados = _correos_de(monkeypatch)
    r = notificaciones.enviar_restauracion_oferta([("Ana <b>", "ana@x.com")], "A&B <SA>", "2026-10-12 10:00", None)
    assert r["estado"] == "enviado" and len(enviados) == 1
    m = enviados[0]
    assert (
        "A&B <SA>" in m["cuerpo"] and "(" not in m["cuerpo"].split("envió el")[1].split("\n")[0]
    )  # sin archivo no hay paréntesis
    assert (
        "A&amp;B &lt;SA&gt;" in m["html"] and "Ana &lt;b&gt;" in m["html"] and "<b>Ana" not in m["html"]
    )  # en HTML todo va escapado


def test_quien_puede_restaurar(cliente, como, anonimo):
    lote = _lote(cliente, como)
    _aprobar(cliente, lote)
    for quien in (_gama(como), como("prime"), como("consulta")):
        assert _restaurar(quien, lote).status_code == 403
    assert _restaurar(anonimo, lote).status_code == 401
    assert _estado(cliente, lote)["estado"] == "aprobada"  # nada cambió
    assert _restaurar(cliente, lote).status_code == 200


# ================================================================================================ bases de datos de versiones anteriores
def test_una_base_vieja_sin_la_foto_de_antes_se_actualiza_sola(tmp_path, monkeypatch):
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE ofertas_lote (lote_id INTEGER NOT NULL, cod_producto TEXT NOT NULL, valor REAL NOT NULL, presentacion TEXT, PRIMARY KEY (lote_id, cod_producto))"
    )
    con.execute("INSERT INTO ofertas_lote VALUES (1, 'A1', 70, 'X10')")
    con.commit()
    con.close()
    monkeypatch.setenv("COMPRAS_DB", str(ruta))
    database.iniciar_db()
    database.iniciar_db()  # dos veces no debe fallar
    con = sqlite3.connect(ruta)
    assert {"antes_existia", "antes_valor", "antes_presentacion", "antes_creado"} <= {
        f[1] for f in con.execute("PRAGMA table_info(ofertas_lote)")
    }
    assert con.execute("SELECT cod_producto, valor, antes_existia FROM ofertas_lote").fetchone() == (
        "A1",
        70.0,
        None,
    )  # lo que había se conserva
    con.close()
