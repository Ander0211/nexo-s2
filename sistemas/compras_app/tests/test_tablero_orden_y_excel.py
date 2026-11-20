"""El tablero se ordena de mayor a menor o de menor a mayor (o A–Z / Z–A) por cualquier columna, y se descarga en Excel
TAL COMO SE VE (mismo filtro, búsqueda, proveedor y orden, con todas las páginas)."""

import io

import openpyxl
import pytest


def _lista(c, **p):
    return c.get("/api/productos", params={"filtro": "todos", "tam": 100, **p}).json()["items"]


@pytest.mark.parametrize("orden", ["inversion", "ahorro", "cantidad", "existencias", "precio", "descripcion", "proveedor", "codigo"])
def test_cada_orden_tiene_dos_sentidos_y_lo_vacio_va_al_final(cliente, orden):
    asc = _lista(cliente, orden=orden, direccion="asc")
    desc = _lista(cliente, orden=orden, direccion="desc")
    assert sorted(i["cod"] for i in asc) == sorted(i["cod"] for i in desc)
    valor = {
        "inversion": lambda i: i["total"], "ahorro": lambda i: i["ahorro"], "cantidad": lambda i: i["comprar"],
        "existencias": lambda i: i["existencias"], "precio": lambda i: i["elegida"] and i["elegida"]["valor"],
        "descripcion": lambda i: i["descripcion"].lower(), "proveedor": lambda i: i["elegida"] and i["elegida"]["empresa"].lower(),
        "codigo": None,
    }[orden]
    if valor:
        for lista, rev in ((asc, False), (desc, True)):
            vals = [valor(i) for i in lista]
            llenos = [v for v in vals if v is not None]
            assert llenos == sorted(llenos, reverse=rev)
            assert all(v is None for v in vals[len(llenos):])  # lo vacío, al final


def test_sin_direccion_numeros_de_mayor_a_menor_y_textos_a_z(cliente):
    tot = [i["total"] for i in _lista(cliente) if i["total"] is not None]
    assert tot == sorted(tot, reverse=True)
    des = [i["descripcion"].lower() for i in _lista(cliente, orden="descripcion")]
    assert des == sorted(des)


def test_excel_del_tablero_tal_como_se_ve(cliente, como):
    r = cliente.get("/api/exportar/tablero", params={"filtro": "todos", "orden": "descripcion", "direccion": "desc"})
    assert r.status_code == 200 and "TABLERO_" in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["TABLERO"]
    assert ws["A1"].value == "CÓDIGO" and ws["F1"].value == "MEJOR PROVEEDOR"
    esperado = [i["cod"] for i in cliente.get("/api/productos", params={"filtro": "todos", "orden": "descripcion", "direccion": "desc", "tam": 100}).json()["items"]]
    codigos = [ws.cell(f, 1).value for f in range(2, 2 + len(esperado))]
    assert codigos == esperado  # mismos productos y mismo orden que la pantalla
    assert wb["FILTRO"]["B3"].value == "Todos"
    # búsqueda: solo lo que coincide
    r = cliente.get("/api/exportar/tablero", params={"filtro": "todos", "q": "A1"})
    ws = openpyxl.load_workbook(io.BytesIO(r.content))["TABLERO"]
    assert ws["A2"].value == "A1"
    # el perfil «Consulta» no descarga (igual que la OC); Prime sí
    assert como("consulta").get("/api/exportar/tablero").status_code == 403
    assert como("prime").get("/api/exportar/tablero").status_code == 200
