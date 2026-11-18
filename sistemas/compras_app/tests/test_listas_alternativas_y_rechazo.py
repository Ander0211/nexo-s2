"""LISTAS «SIN OFERTA» Y «NUEVOS», ALTERNATIVAS QUE SIGUEN A LA OFERTA ELEGIDA, Y EL RECHAZO CON MOTIVO POR CORREO.

Datos de conftest.py: A1 (comprar 80): BETA $85 · GAMA $95 · ALFA $100 · DELTA $120. C3 (5, solo ALFA $50) · 0041 (6) · D4 (5, NADIE lo ofrece) · B2 (completo).
Empresas: 1 ALFA SAS · 2 BETA SAS · 3 GAMA LTDA · 4 DELTA SA.
"""

import io

import openpyxl

from app.services import notificaciones
from tests.conftest import excel_bytes
from tests.test_libros_excel import _poner_contacto
from tests.test_ofertas_proveedor import _gama, _subir


def _xlsx(r):
    assert r.status_code == 200, r.text
    return openpyxl.load_workbook(io.BytesIO(r.content), data_only=True)


def _filas(r, hoja=None):
    wb = _xlsx(r)
    ws = wb[hoja] if hoja else wb.active
    return [[c.value for c in f] for f in ws.iter_rows()]


# ================================================================================================ el proveedor: «Sin oferta» y «Nuevos»
def test_el_proveedor_ve_cuantos_hay_sin_oferta_y_nuevos_y_solo_codigo_y_descripcion(cliente, como):
    gama = _gama(como)
    r = gama.get("/api/proveedor/productos", params={"tam": 100}).json()
    assert r["conteos"] == {"sin_oferta": 1, "nuevos": 0}  # D4 es lo único que nadie ha cotizado
    lista = gama.get("/api/proveedor/lista/sin_oferta").json()
    assert lista["total"] == 1 and [i["cod"] for i in lista["items"]] == ["D4"]
    assert all(
        set(i) == {"cod", "descripcion"} for i in lista["items"]
    )  # ni precios, ni cantidades, ni de quién ofrece
    assert set(lista) == {"total", "pagina", "paginas", "tam", "items"}
    assert gama.get("/api/proveedor/lista/nuevos").json()["total"] == 0


def test_los_nuevos_del_proveedor_son_los_productos_nuevos_que_hay_que_comprar(cliente, como):
    gama = _gama(como)
    cliente.post(
        "/api/productos", json={"cod": "M1", "descripcion": "INSUMO NUEVO QUE FALTA", "stock_max": 10, "existencias": 0}
    )  # hay que comprarlo
    cliente.post(
        "/api/productos", json={"cod": "M2", "descripcion": "INSUMO NUEVO COMPLETO", "stock_max": 10, "existencias": 10}
    )  # nuevo, pero no se necesita
    nuevos = gama.get("/api/proveedor/lista/nuevos").json()
    assert [i["cod"] for i in nuevos["items"]] == ["M1"]  # solo lo que la Clínica necesita comprar
    assert gama.get("/api/proveedor/productos").json()["conteos"]["nuevos"] == 1
    assert {i["cod"] for i in gama.get("/api/proveedor/lista/sin_oferta").json()["items"]} == {
        "D4",
        "M1",
    }  # M1 tampoco tiene oferta


def test_las_listas_del_proveedor_se_buscan_y_se_paginan(cliente, como):
    gama = _gama(como)
    for n in range(12):
        cliente.post(
            "/api/productos",
            json={"cod": f"S{n:02d}", "descripcion": f"INSUMO SUELTO {n}", "stock_max": 10, "existencias": 0},
        )
    todo = gama.get("/api/proveedor/lista/sin_oferta", params={"tam": 10}).json()
    assert todo["total"] == 13 and todo["paginas"] == 2 and len(todo["items"]) == 10
    assert len(gama.get("/api/proveedor/lista/sin_oferta", params={"tam": 10, "pagina": 2}).json()["items"]) == 3
    assert [
        i["cod"] for i in gama.get("/api/proveedor/lista/sin_oferta", params={"q": "suelto 7"}).json()["items"]
    ] == ["S07"]
    assert gama.get("/api/proveedor/lista/otra").status_code in (403, 404, 422)  # solo existen «sin_oferta» y «nuevos»


def test_la_ficha_se_puede_bajar_solo_con_los_sin_oferta_o_los_nuevos(cliente, como):
    gama = _gama(como)
    cliente.post(
        "/api/productos", json={"cod": "M1", "descripcion": "INSUMO NUEVO QUE FALTA", "stock_max": 10, "existencias": 0}
    )

    def codigos(r):
        ws = openpyxl.load_workbook(io.BytesIO(r.content)).worksheets[0]
        return [
            ws.cell(f, 1).value
            for f in range(12, 30)
            if ws.cell(f, 1).value
            and ws.cell(f, 1).value != 6
            and ws.cell(f - 1, 1).value != "Control de Cambios del Documento"
        ][:6]

    sin = gama.get("/api/proveedor/excel", params={"grupo": "sin_oferta"})
    assert "_SIN_OFERTA.xlsx" in sin.headers["content-disposition"] and codigos(sin)[:2] == ["D4", "M1"]
    nuevos = gama.get("/api/proveedor/excel", params={"grupo": "nuevos"})
    assert "_NUEVOS.xlsx" in nuevos.headers["content-disposition"] and codigos(nuevos)[:1] == ["M1"]
    solo = gama.get(
        "/api/proveedor/excel", params={"grupo": "sin_oferta", "q": "nuevo"}
    )  # lo que se ve con la búsqueda escrita
    assert codigos(solo)[:1] == ["M1"] and "D4" not in codigos(solo)
    wb = openpyxl.load_workbook(io.BytesIO(solo.content))
    assert wb["SUMIPABON"]["B1"].value == "3"  # y sigue siendo la ficha de SU proveedor, lista para subir
    completa = gama.get("/api/proveedor/excel")
    assert "_SIN_OFERTA" not in completa.headers["content-disposition"] and len(codigos(completa)) > 2


def test_quien_ve_las_listas_del_proveedor(cliente, como, anonimo):
    for ruta in ("/api/proveedor/lista/sin_oferta", "/api/proveedor/lista/nuevos"):
        assert (
            _gama(como).get(ruta).status_code == 200 and cliente.get(ruta).status_code == 200
        )  # el proveedor y el administrador
        for perfil in ("prime", "consulta"):
            assert como(perfil).get(ruta).status_code == 403
        assert anonimo.get(ruta).status_code == 401


# ================================================================================================ el administrador: Excel de sin oferta y de nuevos
# ================================================================================================ las alternativas siguen a la oferta ELEGIDA
def _alternativa(c, puesto, cod="A1"):
    wb = openpyxl.load_workbook(io.BytesIO(c.get("/api/exportar/alternativas").content), data_only=True)
    ws = wb[f"VALORES {puesto}.º"]
    fila = next((f for f in ws.iter_rows(min_row=2, values_only=True) if f[0] == cod), None)
    return (fila[5], fila[3]) if fila else None  # (proveedor, valor)


def test_sin_elegir_otra_las_alternativas_son_el_2_3_y_4_del_ranking(cliente):
    assert [_alternativa(cliente, p) for p in (2, 3, 4)] == [("GAMA LTDA", 95), ("ALFA SAS", 100), ("DELTA SA", 120)]


def test_si_elijo_otra_oferta_en_vez_de_la_mejor_las_alternativas_se_ajustan(cliente):
    """Elijo a GAMA (la 2.ª) para A1: GAMA pasa a ser «la mejor» (va en la OC) y la que era la mejor, BETA, pasa a ser la alternativa 2.ª."""
    assert cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "3"}).status_code == 200
    oc = openpyxl.load_workbook(io.BytesIO(cliente.get("/api/exportar/oc").content), data_only=True)
    assert [f[5] for f in oc["VALORES"].iter_rows(min_row=2, values_only=True) if f[0] == "A1"] == ["GAMA LTDA"]
    assert [_alternativa(cliente, p) for p in (2, 3, 4)] == [
        ("BETA SAS", 85),
        ("ALFA SAS", 100),
        ("DELTA SA", 120),
    ]  # sin repetir a la elegida


def test_elegir_la_tercera_tambien_ajusta_las_alternativas(cliente):
    cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "1"})  # ALFA, la 3.ª
    assert [_alternativa(cliente, p) for p in (2, 3, 4)] == [("BETA SAS", 85), ("GAMA LTDA", 95), ("DELTA SA", 120)]


def test_volver_a_la_mejor_deja_las_alternativas_como_estaban(cliente):
    cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "3"})
    cliente.delete("/api/productos/A1/seleccion")
    assert [_alternativa(cliente, p) for p in (2, 3, 4)] == [("GAMA LTDA", 95), ("ALFA SAS", 100), ("DELTA SA", 120)]


# ================================================================================================ rechazar: el motivo es obligatorio y se envía por correo
def _correos(monkeypatch, falla=False):
    enviados = []  # solo los avisos de RECHAZO (el correo con la clave temporal de un usuario nuevo no cuenta)

    def enviar(destino, asunto, cuerpo, html=None):
        if "rechazada" not in asunto:
            return
        if falla:
            raise notificaciones.NotificacionError("el servidor de correo no respondió")
        enviados.append({"a": destino, "asunto": asunto, "cuerpo": cuerpo, "html": html})

    monkeypatch.setattr(notificaciones, "correo_configurado", lambda: True)
    monkeypatch.setattr(notificaciones, "enviar_correo", enviar)
    return enviados


def _lote(cliente, como):
    return _subir(
        _gama(como), excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 1, "PRESENTACION": "X1"}]), "mi_ficha.xlsx"
    ).json()["lote"]


def test_rechazar_exige_el_motivo(cliente, como):
    lote = _lote(cliente, como)
    for motivo in ("", "  ", "x"):
        r = cliente.post(f"/api/pendientes/{lote}/rechazar", json={"motivo": motivo})
        assert r.status_code == 422 and "motivo" in r.json()["detail"].lower(), repr(motivo)
    assert cliente.get(f"/api/pendientes/{lote}").json()["lote"]["estado"] == "pendiente"  # no se rechazó nada


def test_al_rechazar_se_le_envia_el_motivo_por_correo_al_proveedor(cliente, como, monkeypatch):
    enviados = _correos(monkeypatch)
    _poner_contacto(cliente, "3", "GAMA LTDA")  # el correo de contacto de la empresa: contacto@empresa.com
    lote = _lote(cliente, como)
    r = cliente.post(f"/api/pendientes/{lote}/rechazar", json={"motivo": "El precio de A1 está fuera de lo acordado"})
    assert r.status_code == 200 and r.json()["estado"] == "rechazada"
    assert (
        r.json()["correo"]["estado"] == "enviado"
        and "gama.proveedor@prueba.com" in r.json()["correo"]["detalle"]
        and "contacto@empresa.com" in r.json()["correo"]["detalle"]
    )
    assert sorted(m["a"] for m in enviados) == [
        "contacto@empresa.com",
        "gama.proveedor@prueba.com",
    ]  # al usuario que la subió y al contacto de la empresa
    m = enviados[0]
    assert m["asunto"] == "Tu oferta fue rechazada · SUMIPABON"
    for texto in (m["cuerpo"], m["html"]):
        assert (
            "El precio de A1 está fuera de lo acordado" in texto
            and "GAMA LTDA" in texto
            and "mi_ficha.xlsx" in texto
            and "Enviar mi oferta" in texto
        )
    assert (
        cliente.get(f"/api/pendientes/{lote}").json()["lote"]["motivo"] == "El precio de A1 está fuera de lo acordado"
    )


def test_si_los_dos_correos_son_el_mismo_se_envia_uno_solo(cliente, como, monkeypatch):
    enviados = _correos(monkeypatch)
    _gama(como)
    from tests.test_admin import CONTACTO, _fila

    f = _fila(cliente, "empresas", CODIGO_EMPRESA="3")
    cliente.put(
        f"/api/admin/tablas/empresas/filas/{f['id']}",
        json={
            "valores": {
                "CODIGO_EMPRESA": "3",
                "NOMBRE": "GAMA LTDA",
                **{**CONTACTO, "CORREO": "GAMA.Proveedor@prueba.com"},
            }
        },
    )
    lote = _lote(cliente, como)
    cliente.post(f"/api/pendientes/{lote}/rechazar", json={"motivo": "Motivo de prueba"})
    assert [m["a"] for m in enviados] == ["gama.proveedor@prueba.com"]  # sin repetir (mayúsculas aparte)


def test_rechazar_funciona_aunque_el_correo_no_este_configurado_o_falle(cliente, como, monkeypatch):
    lote = _lote(cliente, como)
    r = cliente.post(f"/api/pendientes/{lote}/rechazar", json={"motivo": "Motivo de prueba"})  # sin SMTP configurado
    assert r.status_code == 200 and r.json()["estado"] == "rechazada"
    assert r.json()["correo"]["estado"] == "no_configurado" and "COMPRAS_SMTP_SERVIDOR" in r.json()["correo"]["detalle"]
    _correos(monkeypatch, falla=True)
    otro = _lote(cliente, como)
    r = cliente.post(f"/api/pendientes/{otro}/rechazar", json={"motivo": "Motivo de prueba"})
    assert (
        r.status_code == 200 and r.json()["estado"] == "rechazada" and r.json()["correo"]["estado"] == "error"
    )  # el rechazo vale aunque el correo no salga
    assert "no respondió" in r.json()["correo"]["detalle"]


# ================================================================================================ el Excel de cada ficha
def test_el_administrador_baja_la_ficha_de_un_proveedor_como_excel(cliente, como):
    lote = _subir(
        _gama(como),
        excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70, "PRESENTACION": "X10"}, {"COD_PRODUCTO": "C3", "VALOR": 60}]),
    ).json()["lote"]
    r = cliente.get(f"/api/pendientes/{lote}/excel")
    assert f"OFERTA_GAMA_LTDA_{lote}.xlsx" in r.headers["content-disposition"]
    filas = _filas(r, "OFERTA")
    assert filas[0] == [
        "COD_PRODUCTO",
        "DESCRIPCION",
        "A_COMPRAR",
        "PRECIO_PROPUESTO",
        "PRESENTACION",
        "MEJOR_OFERTA_HOY",
        "PROVEEDOR_MEJOR_HOY",
        "YA_OFRECIA",
        "MEJORA",
        "AHORRO_ESTIMADO",
    ]
    a1, c3 = filas[1], filas[2]  # primero lo que mejora la mejor oferta
    assert a1[:2] == ["A1", "ALFA PRODUCTO"] and a1[2:] == [80, 70, "X10", 85, "BETA SAS", 95, "SI", 1200]
    assert c3[0] == "C3" and c3[8] == "NO" and c3[9] is None
    datos = dict(_filas(r, "DATOS DE LA FICHA"))
    assert (
        datos["Proveedor"] == "GAMA LTDA"
        and datos["Estado"] == "pendiente"
        and datos["Precios enviados"] == 2
        and datos["Ahorro estimado"] == 1200
    )


def test_el_excel_de_la_ficha_es_solo_del_administrador(cliente, como):
    lote = _subir(_gama(como), excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70}])).json()["lote"]
    assert (
        _gama(como).get(f"/api/pendientes/{lote}/excel").status_code == 403
        and como("prime").get(f"/api/pendientes/{lote}/excel").status_code == 403
    )
    assert cliente.get("/api/pendientes/9999/excel").status_code == 404


def test_las_descargas_de_sin_oferta_y_nuevos_ya_no_existen_en_el_servidor(cliente):
    """«Sin oferta» y «Nuevos» solo van en «Productos que necesitamos» (con su buscador y su descarga de la ficha); la ventana de Alternativas quedó solo con alternativas."""
    for ruta in ("/api/exportar/sin-oferta", "/api/exportar/nuevos"):
        assert cliente.get(ruta).status_code == 404, ruta
    assert cliente.get("/api/exportar/alternativas").status_code == 200  # lo demás sigue igual


# ================================================================================================ aprobar: se le avisa al proveedor por correo
def _correos_aprobacion(monkeypatch, falla=False):
    enviados = []  # solo los avisos de APROBACIÓN

    def enviar(destino, asunto, cuerpo, html=None):
        if "aprobada" not in asunto:
            return
        if falla:
            raise notificaciones.NotificacionError("el servidor de correo no respondió")
        enviados.append({"a": destino, "asunto": asunto, "cuerpo": cuerpo, "html": html})

    monkeypatch.setattr(notificaciones, "correo_configurado", lambda: True)
    monkeypatch.setattr(notificaciones, "enviar_correo", enviar)
    return enviados


def test_al_aprobar_se_le_avisa_al_proveedor_que_la_clinica_pabon_se_pondra_en_contacto(cliente, como, monkeypatch):
    enviados = _correos_aprobacion(monkeypatch)
    _poner_contacto(cliente, "3", "GAMA LTDA")  # el correo de contacto de la empresa: contacto@empresa.com
    lote = _lote(cliente, como)
    r = cliente.post(f"/api/pendientes/{lote}/aprobar")
    assert r.status_code == 200 and r.json()["estado"] == "aprobada"
    assert (
        r.json()["correo"]["estado"] == "enviado"
        and "gama.proveedor@prueba.com" in r.json()["correo"]["detalle"]
        and "contacto@empresa.com" in r.json()["correo"]["detalle"]
    )
    assert sorted(m["a"] for m in enviados) == [
        "contacto@empresa.com",
        "gama.proveedor@prueba.com",
    ]  # a quien la subió y al contacto de la empresa
    m = enviados[0]
    assert m["asunto"] == "Tu oferta fue aprobada · SUMIPABON"
    for texto in (m["cuerpo"], m["html"]):
        assert "GAMA LTDA" in texto and "mi_ficha.xlsx" in texto and "1 producto con precio" in texto
        assert (
            "se pondrá en contacto contigo" in texto and "Clínica Pabón" in texto
        )  # lo que se le promete al proveedor
        assert (
            "Si deseas conocer más productos nuevos o que aún no cuentan con ofertas, puedes consultarlos en el siguiente enlace."
            in texto
        )  # la invitación a ver más productos
        assert "estado de tus fichas" not in texto  # (ya no se dice «puedes ver el estado de tus fichas»)
        assert (
            "/?ingresar=1" in texto
        )  # y el enlace entra por la pantalla de ingreso, que lo lleva a «Productos que necesitamos»
        assert (
            "BETA SAS" not in texto and "ALFA SAS" not in texto and "DELTA SA" not in texto and "$" not in texto
        )  # nada de otros proveedores ni precios
    assert cliente.get(f"/api/pendientes/{lote}").json()["lote"]["estado"] == "aprobada"


def test_el_aviso_de_aprobacion_sale_una_sola_vez_y_el_rechazo_no_lo_manda(cliente, como, monkeypatch):
    enviados = _correos_aprobacion(monkeypatch)
    _poner_contacto(cliente, "3", "GAMA LTDA")
    lote = _lote(cliente, como)
    assert cliente.post(f"/api/pendientes/{lote}/aprobar").status_code == 200
    assert len(enviados) == 2
    assert cliente.post(f"/api/pendientes/{lote}/aprobar").status_code == 409  # no se aprueba dos veces...
    assert len(enviados) == 2  # ...ni se manda otro correo
    otro = _lote(cliente, como)
    assert cliente.post(f"/api/pendientes/{otro}/rechazar", json={"motivo": "Motivo de prueba"}).status_code == 200
    assert len(enviados) == 2  # rechazar manda su propio correo («rechazada»), no el de aprobación


def test_aprobar_funciona_aunque_el_correo_no_este_configurado_o_falle(cliente, como, monkeypatch):
    lote = _lote(cliente, como)
    r = cliente.post(f"/api/pendientes/{lote}/aprobar")  # sin SMTP configurado
    assert r.status_code == 200 and r.json()["estado"] == "aprobada"
    assert r.json()["correo"]["estado"] == "no_configurado" and "COMPRAS_SMTP_SERVIDOR" in r.json()["correo"]["detalle"]
    _correos_aprobacion(monkeypatch, falla=True)
    otro = _lote(cliente, como)
    r = cliente.post(f"/api/pendientes/{otro}/aprobar")
    assert (
        r.status_code == 200 and r.json()["estado"] == "aprobada" and r.json()["correo"]["estado"] == "error"
    )  # la aprobación vale aunque el correo no salga
    assert "no respondió" in r.json()["correo"]["detalle"]


def test_el_correo_de_aprobacion_sin_destinos_o_con_caracteres_raros(monkeypatch):
    assert (
        notificaciones.enviar_aprobacion_oferta([], "X", "2026-10-09 10:00", None, 1, "http://x")["estado"]
        == "sin_dato"
    )
    enviados = _correos_aprobacion(monkeypatch)
    r = notificaciones.enviar_aprobacion_oferta(
        [("Ana <b>", "ana@x.com")], "A&B <SA>", "2026-10-09 10:00", None, 3, "http://x/?a=1&b=2"
    )
    assert r["estado"] == "enviado" and len(enviados) == 1
    m = enviados[0]
    assert (
        "A&B <SA>" in m["cuerpo"] and "3 productos con precio" in m["cuerpo"]
    )  # el texto va tal cual (y «productos» en plural)
    assert (
        "A&amp;B &lt;SA&gt;" in m["html"] and "Ana &lt;b&gt;" in m["html"] and "<b>Ana" not in m["html"]
    )  # en HTML todo va escapado
