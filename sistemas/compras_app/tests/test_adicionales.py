"""Pantalla «Adicionales»: subir código y descripción y ver Proveedor 1, 2 y 3 con su menor valor."""

import io

import openpyxl

from tests.conftest import excel_bytes


def _un_producto_con_ofertas(cliente):
    """El producto con más ofertas de los datos de prueba, con su mejor y su segunda oferta."""
    items = cliente.get("/api/productos").json()["items"]
    p = max(items, key=lambda x: x["n_ofertas"])
    assert p["n_ofertas"] >= 3 and p["segunda"]
    return p, [p["mejor"], p["segunda"]]


def test_subir_excel_y_ver_proveedores_en_orden_de_menor_valor(cliente):
    p, ranking = _un_producto_con_ofertas(cliente)
    archivo = excel_bytes([{"Código": p["cod"], "Descripción": p["descripcion"]}, {"Código": "NO-EXISTE-1", "Descripción": "Algo raro"}])
    r = cliente.post("/api/adicionales/archivo", params={"nombre": "lista.xlsx"}, content=archivo)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["nuevos"] == 2 and d["total"] == 2 and d["con_oferta"] == 1 and d["sin_oferta"] == 1
    it = next(x for x in d["items"] if x["cod"] == p["cod"])
    valores = [x["valor"] for x in it["proveedores"]]
    assert 1 <= len(valores) <= 3 and valores == sorted(valores)
    assert [x["puesto"] for x in it["proveedores"]] == list(range(1, len(valores) + 1))
    assert len(valores) == 3  # tiene 5 ofertas: se muestran solo los 3 más baratos
    assert valores[0] == ranking[0]["valor"] and it["proveedores"][0]["nombre"] == ranking[0]["empresa"]
    assert valores[1] == ranking[1]["valor"] and it["proveedores"][1]["nombre"] == ranking[1]["empresa"]
    assert len({x["cod_empresa"] for x in it["proveedores"]}) == len(valores)  # cada proveedor una sola vez
    sin = next(x for x in d["items"] if x["cod"] == "NO-EXISTE-1")
    assert sin["proveedores"] == []


def test_agregar_a_mano_no_repite_codigos_y_busca_por_descripcion(cliente):
    p, _ = _un_producto_con_ofertas(cliente)
    r = cliente.post("/api/adicionales", json={"filas": [{"cod": "OTRO-COD", "descripcion": "  " + p["descripcion"].lower() + " "}]}).json()
    it = r["items"][0]
    assert it["proveedores"] and it["encontrado_por"] == f"descripcion:{p['cod']}"
    r = cliente.post("/api/adicionales", json={"filas": [{"cod": "otro-cod", "descripcion": "Nueva descripción"}]}).json()
    assert r["total"] == 1 and r["actualizados"] == 1 and r["items"][0]["descripcion"] == "Nueva descripción"


def test_csv_sin_encabezado_usa_primera_y_segunda_columna(cliente):
    r = cliente.post("/api/adicionales/archivo", params={"nombre": "l.csv"}, content="A1;Uno\nA2;Dos\n".encode())
    assert r.status_code == 200 and r.json()["total"] == 2


def test_descargar_excel_con_proveedor_1_2_3(cliente):
    p, _ = _un_producto_con_ofertas(cliente)
    cliente.post("/api/adicionales", json={"filas": [{"cod": p["cod"], "descripcion": p["descripcion"]}]})
    r = cliente.get("/api/adicionales/excel")
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    assert [c.value for c in ws[1]][:6] == ["CÓDIGO", "DESCRIPCIÓN", "PROVEEDOR 1", "MENOR VALOR 1", "PROVEEDOR 2", "MENOR VALOR 2"]
    assert ws.cell(2, 1).value == p["cod"] and ws.cell(2, 4).value is not None


def test_quitar_vaciar_y_permisos(cliente, como):
    d = cliente.post("/api/adicionales", json={"filas": [{"cod": "X1"}, {"cod": "X2"}]}).json()
    assert cliente.delete(f"/api/adicionales/{d['items'][0]['id']}").json()["total"] == 1
    # solo el administrador: Prime, Consulta y el proveedor no ven ni usan «Adicionales»
    for rol in ("prime", "consulta", "externo"):
        otro = como(rol)
        assert otro.get("/api/adicionales").status_code == 403, rol
        assert otro.get("/api/adicionales/excel").status_code == 403, rol
        assert otro.post("/api/adicionales", json={"filas": [{"cod": "X9"}]}).status_code == 403, rol
        assert otro.post(f"/api/adicionales/{d['items'][1]['id']}/activo", json={"activo": False}).status_code == 403, rol
    assert cliente.delete("/api/adicionales").json()["total"] == 0


def test_archivo_que_no_sirve_se_explica(cliente):
    r = cliente.post("/api/adicionales/archivo", params={"nombre": "a.pdf"}, content=b"%PDF")
    assert r.status_code == 422 and "Excel" in r.json()["detail"]


def test_inhabilitar_no_borra_y_no_cuenta_ni_sale_en_el_excel(cliente):
    d = cliente.post("/api/adicionales", json={"filas": [{"cod": "Y1", "descripcion": "Uno"}, {"cod": "Y2", "descripcion": "Dos"}]}).json()
    uid = next(x["id"] for x in d["items"] if x["cod"] == "Y1")
    r = cliente.post(f"/api/adicionales/{uid}/activo", json={"activo": False}).json()
    y1 = next(x for x in r["items"] if x["cod"] == "Y1")
    assert y1["activo"] is False and r["total"] == 1 and r["inhabilitados"] == 1 and len(r["items"]) == 2
    ws = openpyxl.load_workbook(io.BytesIO(cliente.get("/api/adicionales/excel").content)).active
    assert [ws.cell(n, 1).value for n in range(2, ws.max_row + 1)] == ["Y2"]
    # volver a subirlo lo habilita de nuevo
    r = cliente.post("/api/adicionales", json={"filas": [{"cod": "y1"}]}).json()
    assert next(x for x in r["items"] if x["cod"] == "Y1")["activo"] is True and r["inhabilitados"] == 0


def test_limites_25_mb_y_100_000_productos(cliente):
    from app.services import adicionales, cargas, tablas

    assert adicionales.MAX_BYTES == cargas.MAX_BYTES == tablas.MAX_BYTES == 25 * 1024 * 1024
    assert adicionales.MAX_FILAS == cargas.MAX_FILAS == 100_000
    r = cliente.post("/api/adicionales/archivo", params={"nombre": "g.xlsx"}, content=b"x" * (26 * 1024 * 1024))
    assert r.status_code == 413 and "25 MB" in r.json()["detail"]


# ------------------------------------------------------------------ Adicionales es libre: ofertas que el tablero no toma
def _item(cliente, cod):
    return next(x for x in cliente.get("/api/adicionales").json()["items"] if x["cod"] == cod)


def test_cargar_datos_con_producto_fuera_del_catalogo_queda_en_adicionales_y_no_en_el_tablero(cliente):
    from tests.test_cargas import subir

    archivo = excel_bytes([
        {"COD_EMPRESA": "1", "COD_PRODUCTO": "NUEVO-77", "DESCRIPCION": "TAPABOCAS N95", "VALOR": 1500, "PRESENTACION": "CAJA X20"},
        {"COD_EMPRESA": "3", "COD_PRODUCTO": "NUEVO-77", "VALOR": 1200},
    ])
    revisado = subir(cliente, "cotizaciones", archivo).json()
    assert revisado["a_adicionales"] == 2 and revisado["total_errores"] == 0
    assert any("Adicionales" in a for a in revisado["avisos"])
    assert cliente.get("/api/adicionales").json()["items"] == []  # revisar no guarda nada
    subir(cliente, "cotizaciones", archivo, aplicar=True)
    assert all(p["cod"] != "NUEVO-77" for p in cliente.get("/api/productos").json()["items"])  # el tablero no lo toma
    cliente.post("/api/adicionales", json={"filas": [{"cod": "nuevo-77"}]})
    provs = _item(cliente, "nuevo-77")["proveedores"]
    assert [(p["nombre"], p["valor"]) for p in provs] == [("GAMA LTDA", 1200), ("ALFA SAS", 1500)]
    assert all(p["fuera_del_tablero"] and p["origen"] == "Cargar datos" for p in provs)
    # también se encuentra por la descripción que traía el archivo
    cliente.post("/api/adicionales", json={"filas": [{"cod": "OTRO-CODIGO", "descripcion": "tapabocas  n95"}]})
    assert _item(cliente, "OTRO-CODIGO")["proveedores"][0]["valor"] == 1200


def test_ficha_del_proveedor_con_producto_que_hoy_no_se_necesita_queda_en_adicionales(cliente, como):
    from tests.test_ofertas_proveedor import _gama, _subir

    j = _subir(_gama(como), excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70}, {"COD_PRODUCTO": "B2", "VALOR": 5},
                                         {"COD_PRODUCTO": "LIBRE-1", "VALOR": 9}])).json()
    assert j["guardadas"] == 1 and j["fuera_de_lista"] == 2  # el tablero sigue igual: solo toma A1
    cliente.post("/api/adicionales", json={"filas": [{"cod": "LIBRE-1"}, {"cod": "B2"}]})
    libre = _item(cliente, "LIBRE-1")["proveedores"]
    assert libre == [{**libre[0], "nombre": "GAMA LTDA", "valor": 9, "fuera_del_tablero": True, "origen": "Ficha del proveedor"}]
    b2 = _item(cliente, "B2")["proveedores"]  # B2 ya tenía ofertas del tablero: compiten todas, cada proveedor con su menor valor
    assert b2[0]["valor"] == 5 and b2[0]["nombre"] == "GAMA LTDA" and b2[0]["fuera_del_tablero"] is True


def test_oferta_libre_mas_reciente_reemplaza_la_anterior(cliente):
    from tests.test_cargas import subir

    for valor in (900, 800):
        subir(cliente, "cotizaciones", excel_bytes([{"COD_EMPRESA": "2", "COD_PRODUCTO": "X-LIB", "VALOR": valor}]), aplicar=True)
    cliente.post("/api/adicionales", json={"filas": [{"cod": "X-LIB"}]})
    assert [p["valor"] for p in _item(cliente, "X-LIB")["proveedores"]] == [800]


def test_mismo_producto_y_proveedor_repetido_en_el_archivo_usa_el_mas_barato(cliente):
    from tests.test_cargas import subir

    filas = [{"COD_EMPRESA": "1", "COD_PRODUCTO": "R-1", "VALOR": v} for v in (9800, 11000)]
    subir(cliente, "cotizaciones", excel_bytes(filas), aplicar=True)
    cliente.post("/api/adicionales", json={"filas": [{"cod": "R-1"}]})
    assert [p["valor"] for p in _item(cliente, "R-1")["proveedores"]] == [9800]
