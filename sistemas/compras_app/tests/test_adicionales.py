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
    consulta = como("consulta")
    assert consulta.get("/api/adicionales").status_code == 200  # consulta ve
    assert consulta.post("/api/adicionales", json={"filas": [{"cod": "X9"}]}).status_code == 403  # pero no cambia
    assert como("prime").post("/api/adicionales", json={"filas": [{"cod": "X9"}]}).status_code == 200
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
