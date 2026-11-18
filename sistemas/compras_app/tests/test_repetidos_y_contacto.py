"""NO SE REPITEN DATOS, Y LAS EMPRESAS LLEVAN TELÉFONO Y CORREO.

Lo que se protege aquí (sobre los datos sintéticos de conftest.py):
  - al AGREGAR o EDITAR una fila en Administración no se puede repetir un código (stock, existencias, ficha, empresas) ni la
    pareja empresa + producto (portafolio); los códigos se comparan sin importar ceros a la izquierda de las empresas
    (05 = 5) ni mayúsculas, y el NOMBRE de una empresa tampoco se repite
  - lo que ya venía repetido del Excel se respeta (se puede seguir editando su precio) y los archivos importados se aceptan tal cual
  - al agregar o editar una EMPRESA, el teléfono y el correo son obligatorios y se dejan en formato único
  - importar el Excel (que no trae esos datos) no los borra
  - el portafolio muestra el nombre de la empresa junto a su código (solo lectura; se puede buscar y ordenar por él)
"""

import sqlite3

import pytest

from app import database
from app.services import contacto
from tests.conftest import excel_bytes
from tests.test_admin import CONTACTO, _fila, _filas


def _crear(c, tabla, valores):
    return c.post(f"/api/admin/tablas/{tabla}/filas", json={"valores": valores})


def _editar(c, tabla, fila_id, valores):
    return c.put(f"/api/admin/tablas/{tabla}/filas/{fila_id}", json={"valores": valores})


# ------------------------------------------------------------------------------------------------ códigos repetidos
@pytest.mark.parametrize(
    "tabla, repetido, distinto",
    [
        ("stock", {"COD_PRODUCTO": "A1", "StockMax": "5"}, {"COD_PRODUCTO": "NUEVO1", "StockMax": "5"}),
        ("stock", {"COD_PRODUCTO": "a1", "StockMax": "5"}, {"COD_PRODUCTO": "41", "StockMax": "5"}),  # «41» ≠ «0041»
        ("stock", {"COD_PRODUCTO": "  A1  ", "StockMax": "5"}, {"COD_PRODUCTO": "A10", "StockMax": "5"}),
        ("existencias", {"COD_PRODUCTO": "A1", "CANTIDAD": "3"}, {"COD_PRODUCTO": "N2", "CANTIDAD": "3"}),
        ("ficha", {"COD_SALUDIPS": "X9"}, {"COD_SALUDIPS": "X10"}),
    ],
)
def test_no_se_agrega_un_codigo_repetido(cliente, tabla, repetido, distinto):
    antes = _filas(cliente, tabla)["total"]
    r = _crear(cliente, tabla, repetido)
    assert r.status_code == 409 and "Ya existe" in r.json()["detail"], r.text
    assert _filas(cliente, tabla)["total"] == antes  # no quedó nada a medias
    assert _crear(cliente, tabla, distinto).status_code == 201  # un código distinto sí entra


def test_la_empresa_no_se_repite_por_codigo_ni_por_nombre(cliente):
    for repetida in (
        {"CODIGO_EMPRESA": "1", "NOMBRE": "OTRA SAS"},
        {"CODIGO_EMPRESA": "01", "NOMBRE": "OTRA SAS"},  # 01 = 1
        {"CODIGO_EMPRESA": "7", "NOMBRE": "alfa sas"},  # mismo nombre en minúsculas
        {"CODIGO_EMPRESA": "7", "NOMBRE": "ÁLFA   SAS"},  # sin tildes y con espacios de más
    ):
        r = _crear(cliente, "empresas", {**repetida, **CONTACTO})
        assert r.status_code == 409 and "Ya existe" in r.json()["detail"], (repetida, r.text)
    assert _filas(cliente, "empresas")["total"] == 5
    assert _crear(cliente, "empresas", {"CODIGO_EMPRESA": "7", "NOMBRE": "SIETE SAS", **CONTACTO}).status_code == 201


def test_editar_una_empresa_tampoco_puede_dejarla_repetida(cliente):
    beta = _fila(cliente, "empresas", CODIGO_EMPRESA="2")
    r = _editar(cliente, "empresas", beta["id"], {"CODIGO_EMPRESA": "2", "NOMBRE": "ALFA SAS", **CONTACTO})
    assert r.status_code == 409 and "NOMBRE" in r.json()["detail"]
    r = _editar(cliente, "empresas", beta["id"], {"CODIGO_EMPRESA": "1", "NOMBRE": "BETA SAS", **CONTACTO})
    assert r.status_code == 409  # su código chocaría con la empresa 1
    # sin tocar su código ni su nombre, sí se puede guardar (aquí cambia el teléfono)
    r = _editar(cliente, "empresas", beta["id"], {"CODIGO_EMPRESA": "2", "NOMBRE": "BETA SAS", **CONTACTO})
    assert r.status_code == 200 and r.json()["cambio"] is True


def test_portafolio_no_repite_empresa_y_producto(cliente):
    antes = _filas(cliente, "portafolio")["total"]
    for repetida in ("1", "01"):  # la empresa 1 ya ofrece A1 ($100)
        r = _crear(cliente, "portafolio", {"COD_EMPRESA": repetida, "COD_PRODUCTO": "A1", "VALOR": "99"})
        assert r.status_code == 409 and "valor 100" in r.json()["detail"], r.text
    assert _crear(cliente, "portafolio", {"COD_EMPRESA": "1", "COD_PRODUCTO": "a1", "VALOR": "99"}).status_code == 409
    assert _filas(cliente, "portafolio")["total"] == antes
    # la misma empresa con OTRO producto, o el mismo producto con OTRA empresa, sí
    assert _crear(cliente, "portafolio", {"COD_EMPRESA": "3", "COD_PRODUCTO": "C3", "VALOR": "55"}).status_code == 201
    assert _crear(cliente, "portafolio", {"COD_EMPRESA": "4", "COD_PRODUCTO": "C3", "VALOR": "56"}).status_code == 201


def test_portafolio_editar_no_puede_chocar_con_otra_fila(cliente):
    nueva = _crear(cliente, "portafolio", {"COD_EMPRESA": "3", "COD_PRODUCTO": "C3", "VALOR": "55"}).json()["fila"]
    r = _editar(cliente, "portafolio", nueva["id"], {**nueva["valores"], "COD_PRODUCTO": "A1"})  # (3, A1) ya existe
    assert r.status_code == 409
    r = _editar(cliente, "portafolio", nueva["id"], {**nueva["valores"], "VALOR": "54"})  # solo el precio: sí
    assert r.status_code == 200


def test_lo_que_ya_venia_repetido_se_respeta_y_se_puede_seguir_editando(cliente):
    """En los datos de prueba la empresa 2 ofrece A1 DOS veces ($90 y $85, como pasa en el Excel real): no se tocan."""
    dos = [
        f
        for f in _filas(cliente, "portafolio")["filas"]
        if f["valores"]["COD_EMPRESA"] == "2" and f["valores"]["COD_PRODUCTO"] == "A1"
    ]
    assert len(dos) == 2
    primera = dos[0]
    # editar solo el precio de una de las repetidas funciona (su código no cambia)
    assert _editar(cliente, "portafolio", primera["id"], {**primera["valores"], "VALOR": "91"}).status_code == 200
    # pero NO se puede crear una tercera
    assert _crear(cliente, "portafolio", {"COD_EMPRESA": "2", "COD_PRODUCTO": "A1", "VALOR": "80"}).status_code == 409
    assert (
        len(
            [
                f
                for f in _filas(cliente, "portafolio")["filas"]
                if f["valores"]["COD_EMPRESA"] == "2" and f["valores"]["COD_PRODUCTO"] == "A1"
            ]
        )
        == 2
    )


def test_un_archivo_importado_se_acepta_aunque_traiga_repetidos(cliente):
    """Importar es cargar datos tal cual (los repetidos salen luego en los avisos): no se rechaza el archivo."""
    archivo = excel_bytes(
        [
            {"COD_PRODUCTO": "R1", "DESCRIPCION": "uno", "StockMax": "5"},
            {"COD_PRODUCTO": "R1", "DESCRIPCION": "otro", "StockMax": "6"},
        ]
    )
    r = cliente.post(
        "/api/admin/tablas/stock/importar", params={"nombre": "s.xlsx", "modo": "reemplazar"}, content=archivo
    )
    assert r.status_code == 200 and _filas(cliente, "stock")["total"] == 2


# ------------------------------------------------------------------------------------------------ teléfono y correo de las empresas
def test_la_empresa_exige_telefono_y_correo(cliente):
    base = {"CODIGO_EMPRESA": "7", "NOMBRE": "SIETE SAS"}
    r = _crear(cliente, "empresas", {**base, "CORREO": "a@b.com"})
    assert r.status_code == 422 and "TELEFONO" in r.json()["detail"] and "obligatorio" in r.json()["detail"]
    r = _crear(cliente, "empresas", {**base, "TELEFONO": "3001234567"})
    assert r.status_code == 422 and "CORREO" in r.json()["detail"] and "obligatorio" in r.json()["detail"]
    assert _filas(cliente, "empresas")["total"] == 5


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("CORREO", "sin-arroba"),
        ("CORREO", "a@b"),
        ("TELEFONO", "abc"),
        ("TELEFONO", "12345"),
        ("TELEFONO", "1234567890123456"),
    ],
)
def test_telefono_y_correo_invalidos_se_rechazan(cliente, campo, valor):
    valores = {"CODIGO_EMPRESA": "7", "NOMBRE": "SIETE SAS", **CONTACTO, campo: valor}
    r = _crear(cliente, "empresas", valores)
    assert r.status_code == 422 and campo in r.json()["detail"], r.text


def test_telefono_y_correo_se_guardan_en_formato_unico(cliente):
    f = _crear(
        cliente,
        "empresas",
        {"CODIGO_EMPRESA": "7", "NOMBRE": "SIETE SAS", "TELEFONO": "(300) 123-4567", "CORREO": " Info@SIETE.com "},
    ).json()["fila"]
    assert f["valores"]["TELEFONO"] == "+573001234567" and f["valores"]["CORREO"] == "info@siete.com"
    g = _crear(
        cliente,
        "empresas",
        {"CODIGO_EMPRESA": "8", "NOMBRE": "OCHO SAS", "TELEFONO": "602 123 4567", "CORREO": "o@ocho.com"},
    ).json()["fila"]
    assert g["valores"]["TELEFONO"] == "6021234567"  # un fijo no se convierte en celular


def test_editar_una_empresa_que_no_tiene_contacto_obliga_a_ponerlo(cliente):
    beta = _fila(cliente, "empresas", CODIGO_EMPRESA="2")
    assert beta["valores"]["TELEFONO"] is None  # las del Excel base no traen teléfono ni correo
    r = _editar(cliente, "empresas", beta["id"], {"CODIGO_EMPRESA": "2", "NOMBRE": "BETA SAS Y CIA"})
    assert r.status_code == 422 and "obligatorio" in r.json()["detail"]
    r = _editar(cliente, "empresas", beta["id"], {"CODIGO_EMPRESA": "2", "NOMBRE": "BETA SAS Y CIA", **CONTACTO})
    assert r.status_code == 200


def test_las_otras_tablas_no_piden_contacto(cliente):
    assert _crear(cliente, "stock", {"COD_PRODUCTO": "SIN1", "StockMax": "5"}).status_code == 201
    assert _crear(cliente, "portafolio", {"COD_EMPRESA": "3", "COD_PRODUCTO": "C3", "VALOR": "55"}).status_code == 201


def test_importar_el_excel_no_borra_el_contacto_que_ya_estaba(cliente):
    beta = _fila(cliente, "empresas", CODIGO_EMPRESA="2")
    _editar(cliente, "empresas", beta["id"], {"CODIGO_EMPRESA": "2", "NOMBRE": "BETA SAS", **CONTACTO})
    for modo in ("reemplazar", "agregar"):
        r = cliente.post(
            "/api/admin/importar", json={"tablas": ["empresas"], "modo": modo}
        )  # EMPRESA.xlsx: sin contacto
        assert r.status_code == 200, r.text
        beta = _fila(cliente, "empresas", CODIGO_EMPRESA="2")
        assert beta["valores"]["TELEFONO"] == "+573001234567" and beta["valores"]["CORREO"] == "contacto@empresa.com", (
            modo
        )
        assert _fila(cliente, "empresas", CODIGO_EMPRESA="1")["valores"]["TELEFONO"] is None  # las demás siguen sin


def test_un_excel_que_trae_telefono_y_correo_los_carga_y_uno_vacio_no_los_pisa(cliente):
    con = excel_bytes(
        [
            {"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA SAS", "TELEFONO": "3105550000", "CORREO": "alfa@x.com"},
            {"CODIGO_EMPRESA": "2", "NOMBRE": "BETA SAS", "TELEFONO": None, "CORREO": None},
        ]
    )
    r = cliente.post(
        "/api/admin/tablas/empresas/importar", params={"nombre": "e.xlsx", "modo": "reemplazar"}, content=con
    )
    assert r.status_code == 200
    alfa = _fila(cliente, "empresas", CODIGO_EMPRESA="1")["valores"]
    assert (
        alfa["TELEFONO"] == "3105550000" and alfa["CORREO"] == "alfa@x.com"
    )  # lo que trae el archivo se carga tal cual
    vacio = excel_bytes([{"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA SAS", "TELEFONO": None, "CORREO": None}])
    cliente.post(
        "/api/admin/tablas/empresas/importar", params={"nombre": "e.xlsx", "modo": "reemplazar"}, content=vacio
    )
    assert (
        _fila(cliente, "empresas", CODIGO_EMPRESA="1")["valores"]["CORREO"] == "alfa@x.com"
    )  # un archivo vacío no lo borra


def test_deshacer_una_importacion_devuelve_tambien_el_contacto(cliente):
    beta = _fila(cliente, "empresas", CODIGO_EMPRESA="2")
    _editar(cliente, "empresas", beta["id"], {"CODIGO_EMPRESA": "2", "NOMBRE": "BETA SAS", **CONTACTO})
    archivo = excel_bytes(
        [{"CODIGO_EMPRESA": "9", "NOMBRE": "NUEVE SAS", "TELEFONO": "3100000009", "CORREO": "n@x.com"}]
    )
    cliente.post(
        "/api/admin/tablas/empresas/importar", params={"nombre": "e.xlsx", "modo": "reemplazar"}, content=archivo
    )
    assert _fila(cliente, "empresas", CODIGO_EMPRESA="2") is None
    h = next(x for x in cliente.get("/api/admin/historial").json() if x["accion"] == "importar")
    assert cliente.post(f"/api/admin/historial/{h['id']}/deshacer").status_code == 200
    assert _fila(cliente, "empresas", CODIGO_EMPRESA="2")["valores"]["CORREO"] == "contacto@empresa.com"


def test_el_excel_descargado_de_empresas_trae_telefono_y_correo(cliente):
    from io import BytesIO

    from openpyxl import load_workbook

    r = cliente.get("/api/admin/tablas/empresas/excel")
    assert r.status_code == 200
    assert [c.value for c in next(load_workbook(BytesIO(r.content)).active.iter_rows(max_row=1))] == [
        "CODIGO_EMPRESA",
        "NOMBRE",
        "TELEFONO",
        "CORREO",
    ]


def test_una_base_anterior_recibe_las_columnas_nuevas_sin_perder_filas(tmp_path, monkeypatch):
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE x_empresas (id INTEGER PRIMARY KEY AUTOINCREMENT, CODIGO_EMPRESA TEXT, NOMBRE TEXT)")
    con.execute("INSERT INTO x_empresas (CODIGO_EMPRESA, NOMBRE) VALUES ('1', 'ALFA SAS')")
    con.commit()
    con.close()
    monkeypatch.setenv("COMPRAS_DB", str(ruta))
    database.iniciar_db()
    database.iniciar_db()  # dos veces no debe fallar
    con = sqlite3.connect(ruta)
    assert {"TELEFONO", "CORREO"} <= {f[1] for f in con.execute("PRAGMA table_info(x_empresas)")}
    assert con.execute("SELECT NOMBRE, TELEFONO FROM x_empresas").fetchone() == ("ALFA SAS", None)
    con.close()


# ------------------------------------------------------------------------------------------------ nombre de la empresa en el portafolio
def test_el_portafolio_muestra_el_nombre_de_la_empresa_junto_a_su_codigo(cliente):
    meta = {t["clave"]: t for t in cliente.get("/api/admin/tablas").json()}
    assert meta["portafolio"]["extras"] == [
        {"nombre": "NOMBRE_EMPRESA", "titulo": "NOMBRE DE LA EMPRESA", "despues": "COD_EMPRESA"}
    ]
    assert all(meta[k]["extras"] == [] for k in ("stock", "existencias", "empresas", "ficha"))
    nombres = {
        f["valores"]["COD_EMPRESA"]: f["extras"]["NOMBRE_EMPRESA"] for f in _filas(cliente, "portafolio")["filas"]
    }
    assert nombres["1"] == "ALFA SAS" and nombres["2"] == "BETA SAS" and nombres["3"] == "GAMA LTDA"
    assert nombres["05"].startswith("Proveedor 5")  # «05» es la empresa 5, que no está en EMPRESA.xlsx
    assert nombres["6"].startswith("Proveedor 6")  # la que no tiene nombre
    assert "extras" not in _filas(cliente, "stock")["filas"][0]  # solo el portafolio las lleva


def test_en_el_portafolio_se_busca_por_el_nombre_de_la_empresa(cliente):
    alfa = _filas(cliente, "portafolio", q="alfa")
    assert alfa["total"] == 3 and {f["valores"]["COD_EMPRESA"] for f in alfa["filas"]} == {"1"}
    assert _filas(cliente, "portafolio", q="gama ltda")["total"] == 2
    assert _filas(cliente, "portafolio", q="álfa a1")["total"] == 1  # sin tildes y combinando con el producto
    assert _filas(cliente, "portafolio", q="inexistente")["total"] == 0


def test_el_portafolio_se_ordena_por_el_nombre_de_la_empresa(cliente):
    for sentido in ("asc", "desc"):
        filas = _filas(cliente, "portafolio", orden="NOMBRE_EMPRESA", sentido=sentido)["filas"]
        nombres = [f["extras"]["NOMBRE_EMPRESA"].lower() for f in filas]
        assert nombres == sorted(nombres, reverse=(sentido == "desc")), sentido


def test_al_cambiar_el_nombre_de_una_empresa_el_portafolio_lo_muestra(cliente):
    alfa = _fila(cliente, "empresas", CODIGO_EMPRESA="1")
    _editar(cliente, "empresas", alfa["id"], {"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA Y CIA", **CONTACTO})
    assert _filas(cliente, "portafolio", q="alfa y cia")["total"] == 3


# ------------------------------------------------------------------------------------------------ las funciones de contacto
@pytest.mark.parametrize(
    "escrito, guardado",
    [
        ("3001234567", "+573001234567"),
        ("300 123 4567", "+573001234567"),
        ("(300) 123-4567", "+573001234567"),
        ("+57 300 123 4567", "+573001234567"),
        ("602 123 4567", "6021234567"),
        ("123 4567", "1234567"),
        ("+1 415 555 0100", "+14155550100"),
        ("", None),
        (None, None),
    ],
)
def test_normalizar_telefono(escrito, guardado):
    assert contacto.normalizar_telefono(escrito) == guardado


@pytest.mark.parametrize("malo", ["abc", "12345", "123456", "1234567890123456", "300-abc-4567", "++573001234567"])
def test_telefono_invalido(malo):
    with pytest.raises(ValueError):
        contacto.normalizar_telefono(malo)


def test_normalizar_correo():
    assert contacto.normalizar_correo("  Info@Empresa.COM ") == "info@empresa.com"
    assert contacto.normalizar_correo("") is None and contacto.normalizar_correo(None) is None
    for malo in ("sin-arroba", "a@b", "@x.com", "a b@x.com", "a@x.com,b@y.com"):
        with pytest.raises(ValueError):
            contacto.normalizar_correo(malo)
