"""EL PROVEEDOR SUBE SU OFERTA; EL ADMINISTRADOR LA APRUEBA ANTES DE QUE COMPITA.

Flujo: el proveedor (usuario «externo», ligado a UNA empresa) descarga la ficha FR-GDS-07, escribe sus precios y la sube él mismo. Queda como lote PENDIENTE:
no entra al tablero. El administrador la revisa (cada precio frente a la mejor oferta de hoy) y la aprueba (los precios empiezan a competir) o la rechaza.

Datos de conftest.py: A1 (comprar 80): BETA $85 · GAMA $95 · ALFA $100 · DELTA $120. C3 (5, solo ALFA $50) · 0041 (6) · D4 (5, nadie lo ofrece) · B2 (no se necesita).
Empresas: 1 ALFA SAS · 2 BETA SAS · 3 GAMA LTDA · 4 DELTA SA.
"""

import io

import openpyxl

from tests.conftest import excel_bytes
from tests.test_cargas import OCTETOS
from tests.test_libros_excel import _diligenciar


def _subir(c, contenido, nombre="ficha.xlsx"):
    return c.post("/api/proveedor/ofertas", params={"nombre": nombre}, content=contenido, headers=OCTETOS)


def _gama(como):
    return como("externo", cod_empresa="3", usuario="gama.proveedor")


def _alfa(como):
    return como("externo", cod_empresa="1", usuario="alfa.proveedor")


def _ficha_llena(proveedor, precios):
    """La ficha que descargaría ese proveedor, con los precios escritos (precio, IVA, empaque)."""
    return _diligenciar(proveedor.get("/api/proveedor/excel").content, precios)


def _ofertas(c, cod="A1"):
    return {
        (o["empresa"], o["origen"]): o["valor"]
        for o in c.get(f"/api/productos/{cod}/ofertas", params={"limite": 50}).json()["ofertas"]
    }


def _mejor(c, cod):
    return next(
        i for i in c.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"] if i["cod"] == cod
    )["mejor"]


# ================================================================================================ subir: queda pendiente
def test_el_proveedor_sube_su_ficha_y_queda_pendiente_sin_competir(cliente, como):
    gama = _gama(como)
    antes = _ofertas(cliente)
    r = _subir(gama, _ficha_llena(gama, {"A1": (70, 13, "X10"), "C3": (40, 0, "X1")}))
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["estado"] == "pendiente" and j["guardadas"] == 2 and j["total_errores"] == 0 and isinstance(j["lote"], int)
    assert _ofertas(cliente) == antes  # NO entró al tablero: GAMA sigue en $95 (Excel base)
    assert _mejor(cliente, "A1")["empresa"] == "BETA SAS"
    assert cliente.get("/api/resumen").json()["ofertas_pendientes"] == 1
    assert not (
        {"mejor", "ofertas", "segunda"} & set(j)
    )  # lo que se le responde al proveedor no trae precios de nadie más


def test_solo_cuentan_los_productos_que_la_clinica_necesita_hoy(cliente, como):
    gama = _gama(como)
    archivo = excel_bytes(
        [
            {"COD_PRODUCTO": "A1", "VALOR": 70},
            {"COD_PRODUCTO": "B2", "VALOR": 5},
            {"COD_PRODUCTO": "NOEXISTE", "VALOR": 5},
        ]
    )  # B2 está completo
    j = _subir(gama, archivo).json()
    assert (
        j["guardadas"] == 1 and j["fuera_de_lista"] == 2
    )  # B2 no se necesita y el otro ni existe: se descartan y se avisa cuántos
    assert [f["cod"] for f in cliente.get(f"/api/pendientes/{j['lote']}").json()["filas"]] == ["A1"]


def test_sin_precios_no_se_guarda_nada(cliente, como):
    gama = _gama(como)
    r = _subir(gama, gama.get("/api/proveedor/excel").content)  # la ficha tal como se descargó: sin un solo precio
    assert r.status_code == 422 and "ningún precio" in r.json()["detail"]
    assert (
        gama.get("/api/proveedor/ofertas").json() == []
        and cliente.get("/api/resumen").json()["ofertas_pendientes"] == 0
    )


def test_un_precio_invalido_se_reporta_con_su_fila_y_lo_valido_se_guarda(cliente, como):
    gama = _gama(como)
    archivo = excel_bytes(
        [
            {"COD_PRODUCTO": "A1", "VALOR": "abc"},
            {"COD_PRODUCTO": "C3", "VALOR": 40},
            {"COD_PRODUCTO": "0041", "VALOR": -5},
        ]
    )
    j = _subir(gama, archivo).json()
    assert j["guardadas"] == 1 and j["total_errores"] == 2
    assert sorted(e["fila"] for e in j["errores"]) == [2, 4]  # las filas del archivo


def test_el_mismo_producto_repetido_en_el_archivo_usa_el_mas_barato(cliente, como):
    gama = _gama(como)
    j = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 90}, {"COD_PRODUCTO": "a1", "VALOR": 70}])).json()
    assert j["guardadas"] == 1 and j["repetidas"] == 1
    assert cliente.get(f"/api/pendientes/{j['lote']}").json()["filas"][0]["valor"] == 70


# ================================================================================================ nadie cotiza por otro
def test_nadie_puede_subir_una_ficha_a_nombre_de_otro_proveedor(cliente, como):
    gama, alfa = _gama(como), _alfa(como)
    ficha_de_alfa = _diligenciar(
        alfa.get("/api/proveedor/excel").content, {"A1": (1, 0, "X1")}
    )  # trae el código de ALFA en su hoja oculta
    r = _subir(gama, ficha_de_alfa)
    assert r.status_code == 409 and "otro proveedor" in r.json()["detail"]
    for columna, valor in (("COD_EMPRESA", "1"), ("EMPRESA", "alfa s.a.s.")):  # tampoco con una columna de proveedor
        r = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 1, columna: valor}]))
        assert r.status_code == 409, columna
    assert (
        gama.get("/api/proveedor/ofertas").json() == []
        and cliente.get("/api/resumen").json()["ofertas_pendientes"] == 0
    )


def test_la_ficha_se_guarda_a_nombre_del_usuario_aunque_el_archivo_no_diga_nada(cliente, como):
    gama = _gama(como)
    j = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70}])).json()
    assert cliente.get(f"/api/pendientes/{j['lote']}").json()["lote"]["cod_empresa"] == "3"


def test_cada_proveedor_ve_solo_sus_propios_envios(cliente, como):
    gama, alfa = _gama(como), _alfa(como)
    _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70}]))
    _subir(alfa, excel_bytes([{"COD_PRODUCTO": "C3", "VALOR": 45}]))
    g, a = gama.get("/api/proveedor/ofertas").json(), alfa.get("/api/proveedor/ofertas").json()
    assert len(g) == 1 and len(a) == 1 and g[0]["id"] != a[0]["id"]
    assert set(g[0]) == {
        "id",
        "fecha",
        "archivo",
        "estado",
        "filas",
        "omitidas",
        "motivo",
        "fecha_revision",
    }  # sin precios ni datos de otros
    assert [x["empresa"] for x in cliente.get("/api/pendientes").json()] == ["GAMA LTDA", "ALFA SAS"] or len(
        cliente.get("/api/pendientes").json()
    ) == 2


def test_una_ficha_nueva_reemplaza_a_la_que_seguia_pendiente(cliente, como):
    gama = _gama(como)
    primera = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70}])).json()["lote"]
    segunda = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 65}])).json()["lote"]
    mias = gama.get("/api/proveedor/ofertas").json()
    assert [m["id"] for m in mias] == [segunda] and mias[0]["estado"] == "pendiente"  # la primera ya no aparece
    assert cliente.get("/api/resumen").json()["ofertas_pendientes"] == 1
    assert cliente.get(f"/api/pendientes/{primera}").json()["lote"]["estado"] == "reemplazada"
    assert cliente.post(f"/api/pendientes/{primera}/aprobar").status_code == 409  # lo reemplazado no se puede aprobar


# ================================================================================================ el administrador revisa
def test_el_administrador_ve_cada_precio_frente_a_la_mejor_oferta(cliente, como):
    gama = _gama(como)
    lote = _subir(
        gama,
        excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70, "PRESENTACION": "X10"}, {"COD_PRODUCTO": "C3", "VALOR": 60}]),
    ).json()["lote"]
    lista = cliente.get("/api/pendientes").json()
    assert [(f["id"], f["empresa"], f["estado"], f["n_filas"] if "n_filas" in f else f["filas"]) for f in lista] == [
        (lote, "GAMA LTDA", "pendiente", 2)
    ]
    d = cliente.get(f"/api/pendientes/{lote}").json()
    a1, c3 = d["filas"]  # primero lo que mejora la mejor oferta
    assert (
        a1["cod"],
        a1["valor"],
        a1["mejor_valor"],
        a1["mejor_empresa"],
        a1["valor_actual"],
        a1["comprar"],
        a1["mejora"],
        a1["ahorro"],
    ) == ("A1", 70, 85, "BETA SAS", 95, 80, True, 1200)
    assert (c3["cod"], c3["valor"], c3["mejor_valor"], c3["mejor_empresa"], c3["mejora"], c3["ahorro"]) == (
        "C3",
        60,
        50,
        "ALFA SAS",
        False,
        None,
    )
    assert d["mejoran"] == 1 and d["ahorro_total"] == 1200 and a1["presentacion"] == "X10"
    assert cliente.get("/api/pendientes/9999").status_code == 404


def test_aprobar_hace_que_los_precios_compitan(cliente, como):
    gama = _gama(como)
    lote = _subir(
        gama,
        excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70, "PRESENTACION": "X10"}, {"COD_PRODUCTO": "C3", "VALOR": 40}]),
    ).json()["lote"]
    r = cliente.post(f"/api/pendientes/{lote}/aprobar")
    assert r.status_code == 200, r.text
    assert (r.json()["estado"], r.json()["nuevos"], r.json()["total_errores"]) == ("aprobada", 2, 0)
    assert _ofertas(cliente)[("GAMA LTDA", "subido")] == 70  # ahora compiten
    assert (
        _mejor(cliente, "A1")["empresa"] == "GAMA LTDA" and _mejor(cliente, "C3")["empresa"] == "GAMA LTDA"
    )  # $70 < $85 y $40 < $50
    assert (
        cliente.get("/api/resumen").json()["inversion_total"] == 70 * 80 + 40 * 5 + 7 * 6
    )  # el total del tablero ya lo refleja
    assert cliente.get("/api/resumen").json()["ofertas_pendientes"] == 0
    mia = gama.get("/api/proveedor/ofertas").json()[0]
    assert mia["estado"] == "aprobada" and mia["fecha_revision"]
    assert cliente.post(f"/api/pendientes/{lote}/aprobar").status_code == 409  # no se aprueba dos veces


def test_aprobar_una_segunda_ficha_actualiza_el_precio_y_no_duplica_la_oferta(cliente, como):
    gama = _gama(como)
    for precio in (70, 60):
        lote = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": precio}])).json()["lote"]
        assert cliente.post(f"/api/pendientes/{lote}/aprobar").status_code == 200
    ofertas = cliente.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["ofertas"]
    gama_subidas = [o["valor"] for o in ofertas if o["empresa"] == "GAMA LTDA" and o["origen"] == "subido"]
    assert gama_subidas == [60]  # UNA sola, con el último precio (la regla de no repetir sigue valiendo)


def test_rechazar_no_cambia_nada_y_el_proveedor_ve_el_motivo(cliente, como):
    gama = _gama(como)
    antes = _ofertas(cliente)
    lote = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 1}])).json()["lote"]  # un precio absurdo
    r = cliente.post(f"/api/pendientes/{lote}/rechazar", json={"motivo": "Precio fuera de lo acordado"})
    assert r.status_code == 200 and r.json()["estado"] == "rechazada"
    assert _ofertas(cliente) == antes and _mejor(cliente, "A1")["empresa"] == "BETA SAS"  # no entró
    mia = gama.get("/api/proveedor/ofertas").json()[0]
    assert (mia["estado"], mia["motivo"]) == ("rechazada", "Precio fuera de lo acordado")
    assert cliente.post(f"/api/pendientes/{lote}/aprobar").status_code == 409  # y ya no se puede aprobar
    assert cliente.get("/api/resumen").json()["ofertas_pendientes"] == 0


def test_las_fichas_ya_revisadas_se_pueden_listar_por_estado(cliente, como):
    gama = _gama(como)
    a = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70}])).json()["lote"]
    cliente.post(f"/api/pendientes/{a}/aprobar")
    b = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 65}])).json()["lote"]
    assert [x["id"] for x in cliente.get("/api/pendientes", params={"estado": "pendiente"}).json()] == [b]
    assert [x["id"] for x in cliente.get("/api/pendientes", params={"estado": "aprobada"}).json()] == [a]
    assert [x["id"] for x in cliente.get("/api/pendientes").json()] == [b, a]  # los pendientes primero
    assert cliente.get("/api/pendientes", params={"estado": "cualquiera"}).status_code == 422


# ================================================================================================ la pantalla del proveedor y los permisos
def test_el_administrador_tambien_ve_la_pantalla_del_proveedor(cliente):
    productos = cliente.get("/api/proveedor/productos", params={"tam": 100})
    assert productos.status_code == 200 and all(
        set(i) == {"cod", "descripcion"} for i in productos.json()["items"]
    )  # solo código y descripción
    r = cliente.get("/api/proveedor/excel")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert (
        wb["SUMIPABON"]["B1"].value in (None, "") and "FR-GDS-07" in wb.worksheets[0]["K1"].value
    )  # la ficha, sin proveedor


def test_quien_puede_subir_revisar_y_ver_la_pantalla_del_proveedor(cliente, como, anonimo):
    gama = _gama(como)
    lote = _subir(gama, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70}])).json()["lote"]
    # el proveedor NO revisa ni aprueba
    for metodo, ruta in (
        ("get", "/api/pendientes"),
        ("get", f"/api/pendientes/{lote}"),
        ("post", f"/api/pendientes/{lote}/aprobar"),
        ("post", f"/api/pendientes/{lote}/rechazar"),
    ):
        kw = {"json": {"motivo": "x"}} if ruta.endswith("rechazar") else {}
        assert getattr(gama, metodo)(ruta, **kw).status_code == 403, ruta
    assert cliente.get(f"/api/pendientes/{lote}").json()["lote"]["estado"] == "pendiente"  # nada cambió
    # el administrador NO sube ofertas por un proveedor (para eso está «Cargar datos») ni ve sus envíos
    assert _subir(cliente, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 1}])).status_code == 403
    assert cliente.get("/api/proveedor/ofertas").status_code == 403
    # Prime y Consulta no ven nada de esto
    for perfil in ("prime", "consulta"):
        c = como(perfil)
        for metodo, ruta in (
            ("get", "/api/pendientes"),
            ("get", "/api/proveedor/productos"),
            ("get", "/api/proveedor/excel"),
            ("get", "/api/proveedor/ofertas"),
        ):
            assert getattr(c, metodo)(ruta).status_code == 403, (perfil, ruta)
        assert _subir(c, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 1}])).status_code == 403
    # sin sesión, nada
    assert (
        anonimo.get("/api/pendientes").status_code == 401 and anonimo.get("/api/proveedor/ofertas").status_code == 401
    )
    assert _subir(anonimo, excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 1}])).status_code == 401


def test_un_archivo_que_no_es_excel_se_rechaza_con_un_mensaje(cliente, como):
    gama = _gama(como)
    r = _subir(gama, b"esto no es un excel", "mentira.xlsx")
    assert r.status_code in (400, 422) and r.json()["detail"]
    assert gama.get("/api/proveedor/ofertas").json() == []
