"""ETIQUETAS «NUEVO», «STOCK SUFICIENTE» Y AVISO DE COMPRA MENOR A LA RECOMENDADA.

  - Nuevo = el sistema lo ve por primera vez (llegue por Excel, a mano o subido); lo que ya existía al arrancar es «lo de siempre».
    La etiqueta dura DIAS_NUEVO días y un código que ya había estado no vuelve a ser nuevo.
  - Stock suficiente = no hay nada que comprar porque las existencias ya están en el máximo o por encima.
  - Menos de lo recomendado = el usuario fijó una cantidad menor que la calculada (StockMax − Existencias).

Datos de conftest.py: A1 (stock 100, existencias 20, comprar 80) · B2 (10 de 10: completo) · C3, D4, 0041, X9 (sin stock definido).
"""

from datetime import datetime, timedelta

from app import database
from app.services import etiquetas
from tests.conftest import excel_bytes

HOY = datetime(2026, 10, 2, 10, 0, 0)


def _items(c, **params):
    return {
        i["cod"]: i for i in c.get("/api/productos", params={"filtro": "todos", "tam": 100, **params}).json()["items"]
    }


def _empresas(c):
    return {e["cod"]: e for e in c.get("/api/empresas").json()}


def _reloj(monkeypatch, momento):
    monkeypatch.setattr(etiquetas, "ahora", lambda: momento)


# ================================================================================================ NUEVO
def test_lo_que_ya_existia_al_arrancar_no_es_nuevo(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    assert not any(i["nuevo"] for i in _items(cliente).values())
    assert not any(e["nuevo"] for e in _empresas(cliente).values())
    assert not any(i["mejor"] and i["mejor"]["empresa_nueva"] for i in _items(cliente).values())


def test_un_producto_y_una_empresa_creados_a_mano_son_nuevos(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)  # (lo que ya había queda como «de siempre»)
    assert (
        cliente.post(
            "/api/productos", json={"cod": "M1", "descripcion": "PRODUCTO PROPIO", "stock_max": 10, "existencias": 0}
        ).status_code
        == 201
    )
    nueva = cliente.post("/api/empresas", json={"nombre": "EMPRESA PROPIA SAS"}).json()
    items = _items(cliente)
    assert items["M1"]["nuevo"] is True and items["M1"]["nuevo_desde"] == "2026-10-02 10:00:00"
    assert [c for c, i in items.items() if i["nuevo"]] == ["M1"]  # solo ese
    empresas = _empresas(cliente)
    assert empresas[nueva["cod"]]["nuevo"] is True and [c for c, e in empresas.items() if e["nuevo"]] == [nueva["cod"]]
    ficha = cliente.get(f"/api/empresas/{nueva['cod']}/ficha").json()
    assert ficha["nuevo"] is True and ficha["nuevo_desde"] == "2026-10-02 10:00:00"
    assert cliente.get("/api/empresas/1/ficha").json()["nuevo"] is False
    assert (
        cliente.get("/api/productos/M1/ofertas").json()["nuevo"] is True
        and cliente.get("/api/productos/A1/ofertas").json()["nuevo"] is False
    )


def test_lo_que_llega_en_un_excel_tambien_es_nuevo(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)
    productos = excel_bytes(
        [
            {"COD_PRODUCTO": "A1", "DESCRIPCION": "uno", "StockMax": "100"},
            {"COD_PRODUCTO": "ZZ9", "DESCRIPCION": "NUEVO POR EXCEL", "StockMax": "5"},
        ]
    )
    assert (
        cliente.post(
            "/api/admin/tablas/stock/importar", params={"nombre": "s.xlsx", "modo": "agregar"}, content=productos
        ).status_code
        == 200
    )
    empresas = excel_bytes(
        [{"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA SAS"}, {"CODIGO_EMPRESA": "8", "NOMBRE": "OCHO POR EXCEL"}]
    )
    assert (
        cliente.post(
            "/api/admin/tablas/empresas/importar", params={"nombre": "e.xlsx", "modo": "agregar"}, content=empresas
        ).status_code
        == 200
    )
    nuevos = [c for c, i in _items(cliente).items() if i["nuevo"]]
    assert nuevos == ["ZZ9"]  # A1 ya estaba: no es nuevo aunque venga en el archivo
    assert [e["nombre"] for e in _empresas(cliente).values() if e["nuevo"]] == ["OCHO POR EXCEL"]


def test_la_oferta_de_una_empresa_nueva_lleva_la_etiqueta(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)
    r = cliente.post("/api/ofertas", json={"cod_producto": "A1", "empresa_nueva": "RECIEN LLEGADA SAS", "valor": 10})
    assert r.status_code == 201
    a1 = _items(cliente)["A1"]
    assert a1["mejor"]["empresa"] == "RECIEN LLEGADA SAS" and a1["mejor"]["empresa_nueva"] is True  # ahora es la mejor
    assert (
        a1["elegida"]["empresa_nueva"] is True and a1["segunda"]["empresa_nueva"] is False
    )  # la 2.ª (BETA) no es nueva
    podio = cliente.get("/api/productos/A1/ofertas").json()["ofertas"]
    assert [o["empresa_nueva"] for o in podio] == [True, False, False]


def test_la_etiqueta_dura_siete_dias_y_no_vuelve_a_salir(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)
    cliente.post("/api/productos", json={"cod": "M1", "descripcion": "PROPIO", "stock_max": 10, "existencias": 0})
    assert _items(cliente)["M1"]["nuevo"] is True
    _reloj(monkeypatch, HOY + timedelta(days=6, hours=23))
    assert _items(cliente)["M1"]["nuevo"] is True  # todavía no pasan 7 días
    _reloj(monkeypatch, HOY + timedelta(days=7, hours=1))
    assert _items(cliente)["M1"]["nuevo"] is False  # ya no
    # si se borra y se vuelve a crear, NO vuelve a ser nuevo: ya había estado
    assert cliente.delete("/api/productos/M1").status_code in (200, 204)
    cliente.post("/api/productos", json={"cod": "M1", "descripcion": "PROPIO", "stock_max": 10, "existencias": 0})
    assert _items(cliente)["M1"]["nuevo"] is False


def test_una_base_anterior_sin_registro_no_marca_todo_como_nuevo(cliente, monkeypatch):
    """Al actualizar la aplicación, lo que ya existía queda como «de siempre» (si no, TODO saldría «Nuevo»)."""
    _reloj(monkeypatch, HOY)
    con = database.conectar()
    try:
        con.execute("DELETE FROM vistos")
        con.commit()
        etiquetas.sincronizar(con)
        assert con.execute("SELECT COUNT(*) FROM vistos WHERE primera_vez IS NOT NULL").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM vistos").fetchone()[0] > 5
    finally:
        con.close()
    assert not any(i["nuevo"] for i in _items(cliente).values())


def test_el_perfil_consulta_tambien_ve_las_etiquetas(cliente, como, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)
    cliente.post("/api/productos", json={"cod": "M1", "descripcion": "PROPIO", "stock_max": 10, "existencias": 0})
    assert _items(como("consulta"))["M1"]["nuevo"] is True


# ================================================================================================ STOCK SUFICIENTE
def test_stock_suficiente_cuando_no_se_compra_porque_ya_esta_en_el_maximo(cliente):
    items = _items(cliente)
    assert items["B2"]["comprar"] == 0 and items["B2"]["stock_suficiente"] is True  # 10 de 10
    assert items["A1"]["stock_suficiente"] is False  # se compra
    assert items["X9"]["stock_suficiente"] is False  # sin stock definido: no se sabe
    assert items["D4"]["stock_suficiente"] is False


def test_stock_suficiente_tambien_si_las_existencias_superan_el_maximo(cliente):
    ex = next(
        f
        for f in cliente.get("/api/admin/tablas/existencias/filas", params={"q": "B2"}).json()["filas"]
        if f["valores"]["COD_PRODUCTO"] == "B2"
    )
    cliente.put(
        f"/api/admin/tablas/existencias/filas/{ex['id']}", json={"valores": {**ex["valores"], "CANTIDAD": "25"}}
    )
    b2 = _items(cliente)["B2"]
    assert (b2["existencias"], b2["stock_max"], b2["comprar"], b2["stock_suficiente"]) == (25, 10, 0, True)


def test_stock_suficiente_depende_de_las_existencias_no_de_lo_editado(cliente):
    # A1 tiene 20 de 100: poner 0 NO lo vuelve «suficiente» (le faltan 80); solo no se va a comprar
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 0})
    a1 = _items(cliente)["A1"]
    assert (a1["comprar"], a1["stock_suficiente"]) == (0, False)
    # B2 está completo: si alguien decide comprar 5, ya no se muestra «suficiente» (se está comprando)
    cliente.put("/api/productos/B2/cantidad", json={"cantidad": 5})
    assert _items(cliente)["B2"]["stock_suficiente"] is False
    cliente.put("/api/productos/B2/cantidad", json={"cantidad": 0})
    assert _items(cliente)["B2"]["stock_suficiente"] is True


# ================================================================================================ MENOS DE LO RECOMENDADO
def test_aviso_de_compra_menor_a_la_recomendada(cliente):
    assert _items(cliente)["A1"]["menos_de_lo_recomendado"] is False  # sin editar
    for cantidad, avisa in ((50, True), (79, True), (0, True), (80, False), (100, False), (5000, False)):
        cliente.put("/api/productos/A1/cantidad", json={"cantidad": cantidad})
        a1 = _items(cliente)["A1"]
        assert a1["menos_de_lo_recomendado"] is avisa, cantidad
        assert a1["calculada"] == 80  # la recomendada sigue siendo StockMax − Existencias
    r = cliente.put("/api/productos/A1/cantidad", json={"cantidad": 10})
    assert r.json()["item"]["menos_de_lo_recomendado"] is True  # la respuesta ya lo trae para la pantalla
    assert cliente.delete("/api/productos/A1/cantidad").json()["item"]["menos_de_lo_recomendado"] is False


def test_comprar_algo_donde_no_hacia_falta_no_es_comprar_menos(cliente):
    cliente.put("/api/productos/B2/cantidad", json={"cantidad": 3})  # la recomendada es 0
    assert _items(cliente)["B2"]["menos_de_lo_recomendado"] is False


# ================================================================================================ FILTRO «NUEVOS»
def _nuevos(c, **params):
    r = c.get("/api/productos", params={"filtro": "nuevos", "tam": 100, **params})
    assert r.status_code == 200, r.text
    return {i["cod"] for i in r.json()["items"]}


def test_el_filtro_nuevos_esta_vacio_al_arrancar_y_lo_que_ya_habia_no_cuenta(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    assert _nuevos(cliente) == set() and cliente.get("/api/resumen").json()["conteos"]["nuevos"] == 0


def test_el_filtro_nuevos_trae_los_productos_nuevos_y_los_que_tienen_una_empresa_nueva(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)
    cliente.post(
        "/api/productos",
        json={
            "cod": "M1",
            "descripcion": "PRODUCTO RECIEN AGREGADO",
            "stock_max": 10,
            "existencias": 10,
        },  # completo: no hay que comprarlo
    )
    assert _nuevos(cliente) == {
        "M1"
    }  # un producto nuevo (aunque todavía no haya que comprarlo, el filtro «nuevos» no depende de eso)
    cliente.post(
        "/api/ofertas", json={"cod_producto": "C3", "empresa_nueva": "RECIEN LLEGADA SAS", "valor": 10}
    )  # empresa nueva, la mejor de C3
    assert _nuevos(cliente) == {"M1", "C3"}
    assert cliente.get("/api/resumen").json()["conteos"]["nuevos"] == 2
    # el resto del tablero no cambia: «Por comprar» sigue siendo lo mismo
    assert "M1" not in {
        i["cod"] for i in cliente.get("/api/productos", params={"filtro": "por_comprar", "tam": 100}).json()["items"]
    }


def test_una_empresa_nueva_que_no_es_la_mejor_no_hace_nuevo_al_producto(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)
    cliente.post(
        "/api/ofertas", json={"cod_producto": "A1", "empresa_nueva": "CARA SAS", "valor": 500}
    )  # muy cara: no es la mejor ni la elegida
    assert _nuevos(cliente) == set()


def test_el_panel_donde_comprar_marca_a_las_empresas_nuevas(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)
    cliente.post("/api/ofertas", json={"cod_producto": "A1", "empresa_nueva": "RECIEN LLEGADA SAS", "valor": 10})
    prov = {p["nombre"]: p["nuevo"] for p in cliente.get("/api/resumen").json()["por_proveedor"]}
    assert prov["RECIEN LLEGADA SAS"] is True and prov["ALFA SAS"] is False


def test_lo_nuevo_deja_de_serlo_a_los_siete_dias(cliente, monkeypatch):
    _reloj(monkeypatch, HOY)
    _items(cliente)
    cliente.post("/api/productos", json={"cod": "M1", "descripcion": "PROPIO", "stock_max": 10, "existencias": 0})
    assert _nuevos(cliente) == {"M1"}
    _reloj(monkeypatch, HOY + timedelta(days=8))
    assert _nuevos(cliente) == set()
