"""NO SE PUEDE CREAR ALGO NUEVO QUE YA EXISTE — EN TODO EL SISTEMA.

Una empresa (proveedor) nueva no puede repetir el nombre ni el código de una que ya hay, entre por donde entre:
  - «Agregar oferta» escribiendo el nombre   - el servicio de proveedores (/api/empresas: crear y cambiar el nombre)
  - Administración → Empresas (agregar, editar e importar el Excel)   - Cargar datos → Proveedores y → Cotizaciones
Se comparan SIN tildes, sin mayúsculas y sin espacios ni signos: «Ñandú S.A.S.» = «NANDU SAS» = «ñandu  s a s».
Igual para los productos (el código no distingue mayúsculas) y para las personas (usuario, correo y celular).

Empresas de conftest.py: 1 ALFA SAS · 2 BETA SAS · 3 GAMA LTDA · 4 DELTA SA · 5 (sin registro) · 6 (sin nombre).
"""

import pytest

from app.services import normalizacion as nz
from tests.conftest import excel_bytes
from tests.test_admin import CONTACTO, _fila, _filas
from tests.test_cargas import subir

# distintas formas de escribir «ALFA SAS»
ALFA = [
    "alfa sas",
    "ÁLFA SAS",
    "ALFA S.A.S.",
    "alfa-sas",
    "ALFA   SAS",
    "  Alfa Sas  ",
    "A.L.F.A. S.A.S",
    "Alfa, S.A.S",
]


def _empresas(c):
    return {e["cod"]: e["nombre"] for e in c.get("/api/empresas").json()}


def _admin_crear(c, valores):
    return c.post("/api/admin/tablas/empresas/filas", json={"valores": {**valores, **CONTACTO}})


# ================================================================================================ servicio de proveedores
@pytest.mark.parametrize("nombre", ALFA)
def test_no_se_crea_un_proveedor_con_el_nombre_de_otro_escrito_distinto(cliente, nombre):
    antes = _empresas(cliente)
    r = cliente.post("/api/empresas", json={"nombre": nombre})
    assert r.status_code == 409 and "ALFA SAS" in r.json()["detail"], (nombre, r.text)
    assert _empresas(cliente) == antes  # no quedó nada creado


def test_los_nombres_con_enie_o_tildes_tampoco_se_repiten(cliente):
    """SQLite solo pasa a minúsculas las letras sin tilde: «MUÑOZ» y «muñoz» eran dos nombres distintos para el sistema."""
    assert cliente.post("/api/empresas", json={"nombre": "MUÑOZ & CÍA"}).status_code == 201
    for repetido in ("muñoz & cía", "MUNOZ & CIA", "Muñoz &  Cia.", "múñoz&cía"):
        assert cliente.post("/api/empresas", json={"nombre": repetido}).status_code == 409, repetido


def test_el_codigo_de_un_proveedor_tampoco_se_repite(cliente):
    for cod in ("1", "01", " 1 ", "001"):
        r = cliente.post("/api/empresas", json={"nombre": "NOMBRE NUEVO", "cod": cod})
        assert r.status_code == 409, cod
    assert cliente.post("/api/empresas", json={"nombre": "NOMBRE NUEVO", "cod": "77"}).status_code == 201


def test_cambiar_el_nombre_no_puede_dejarlo_igual_al_de_otro(cliente):
    assert cliente.put("/api/empresas/2", json={"nombre": "ALFA S.A.S."}).status_code == 409
    assert cliente.put("/api/empresas/2", json={"nombre": "ÁLFA sas"}).status_code == 409
    assert _empresas(cliente)["2"] == "BETA SAS"
    # pero un proveedor sí puede escribirse distinto a sí mismo (no se estorba a sí mismo)
    assert cliente.put("/api/empresas/1", json={"nombre": "ALFA S.A.S."}).status_code == 200


# ================================================================================================ «Agregar oferta» escribiendo el nombre
@pytest.mark.parametrize("nombre", ALFA)
def test_agregar_oferta_con_el_nombre_de_un_proveedor_que_existe_usa_ese_proveedor(cliente, nombre):
    antes = _empresas(cliente)
    r = cliente.post("/api/ofertas", json={"cod_producto": "D4", "empresa_nueva": nombre, "valor": 10})
    assert r.status_code == 201, (nombre, r.text)
    assert r.json()["proveedor_nuevo"] is False  # no creó otro proveedor «ALFA»
    assert _empresas(cliente) == antes
    cliente.delete(f"/api/ofertas/{r.json()['id']}")


def test_agregar_oferta_con_un_nombre_nuevo_lo_crea_una_sola_vez(cliente):
    primera = cliente.post(
        "/api/ofertas", json={"cod_producto": "D4", "empresa_nueva": "Cía. Ñandú S.A.S.", "valor": 10}
    )
    assert primera.status_code == 201 and primera.json()["proveedor_nuevo"] is True
    segunda = cliente.post("/api/ofertas", json={"cod_producto": "A1", "empresa_nueva": "CIA NANDU SAS", "valor": 70})
    assert segunda.status_code == 201 and segunda.json()["proveedor_nuevo"] is False  # es el mismo
    assert (
        sum(1 for n in _empresas(cliente).values() if "nandu" in nz.sin_acentos(n).lower()) == 1
    )  # un solo proveedor «Ñandú»


# ================================================================================================ Administración → Empresas
@pytest.mark.parametrize("nombre", ["ALFA S.A.S.", "álfa sas", "alfa  sas", "A.L.F.A. SAS"])
def test_administracion_no_agrega_una_empresa_con_el_nombre_de_otra(cliente, nombre):
    antes = _filas(cliente, "empresas")["total"]
    r = _admin_crear(cliente, {"CODIGO_EMPRESA": "7", "NOMBRE": nombre})
    assert r.status_code == 409 and "Ya existe" in r.json()["detail"], (nombre, r.text)
    assert _filas(cliente, "empresas")["total"] == antes


def test_administracion_y_las_empresas_creadas_en_la_aplicacion_no_se_pisan(cliente):
    """Una empresa creada a mano en «Agregar oferta» o «Proveedores» no está en la tabla EMPRESAS de Administración: también se revisa contra ella."""
    manual = cliente.post("/api/empresas", json={"nombre": "ZETA SAS"}).json()  # código desde 1000
    r = _admin_crear(cliente, {"CODIGO_EMPRESA": "7", "NOMBRE": "zeta s.a.s"})
    assert r.status_code == 409 and "ZETA SAS" in r.json()["detail"], r.text  # el nombre ya lo tiene otra
    r = _admin_crear(cliente, {"CODIGO_EMPRESA": manual["cod"], "NOMBRE": "OTRO NOMBRE DISTINTO"})
    assert r.status_code == 409 and manual["cod"] in r.json()["detail"], r.text  # el código ya lo usa otra
    beta = _fila(cliente, "empresas", CODIGO_EMPRESA="2")
    r = cliente.put(
        f"/api/admin/tablas/empresas/filas/{beta['id']}",
        json={"valores": {"CODIGO_EMPRESA": "2", "NOMBRE": "Zeta S.A.S.", **CONTACTO}},
    )
    assert r.status_code == 409, r.text  # tampoco se le puede poner a una existente el nombre de la creada a mano
    assert _admin_crear(cliente, {"CODIGO_EMPRESA": "7", "NOMBRE": "SIETE SAS"}).status_code == 201  # lo demás sí


def test_el_servicio_de_proveedores_revisa_tambien_las_empresas_de_administracion(cliente):
    """Al revés: lo que está en la tabla EMPRESAS de Administración tampoco se puede volver a crear a mano."""
    assert _admin_crear(cliente, {"CODIGO_EMPRESA": "8", "NOMBRE": "OCHO SAS"}).status_code == 201
    assert cliente.post("/api/empresas", json={"nombre": "ocho s.a.s."}).status_code == 409
    assert cliente.post("/api/empresas", json={"nombre": "OTRO", "cod": "8"}).status_code == 409


# ================================================================================================ importar el Excel de empresas
def _importar_empresas(c, filas, modo):
    return c.post(
        "/api/admin/tablas/empresas/importar", params={"nombre": "e.xlsx", "modo": modo}, content=excel_bytes(filas)
    )


def test_un_excel_de_empresas_con_la_misma_empresa_dos_veces_se_rechaza_completo(cliente):
    antes = _filas(cliente, "empresas")["total"]
    repetido_por_codigo = [{"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA SAS"}, {"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA SAS"}]
    repetido_por_nombre = [
        {"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA SAS"},
        {"CODIGO_EMPRESA": "9", "NOMBRE": "Alfa S.A.S."},
    ]
    for filas in (repetido_por_codigo, repetido_por_nombre):
        for modo in ("reemplazar", "agregar"):
            r = _importar_empresas(cliente, filas, modo)
            assert r.status_code in (400, 409, 422) and "dos veces" in r.json()["detail"], (modo, r.text)
    assert _filas(cliente, "empresas")["total"] == antes  # no se cambió nada


def test_importar_empresas_agregando_no_deja_un_nombre_que_ya_tiene_otra(cliente):
    r = _importar_empresas(
        cliente, [{"CODIGO_EMPRESA": "30", "NOMBRE": "Gama, Ltda."}], "agregar"
    )  # GAMA LTDA ya es la empresa 3
    assert r.status_code in (400, 409, 422) and "GAMA LTDA" in r.json()["detail"], r.text
    r = _importar_empresas(
        cliente, [{"CODIGO_EMPRESA": "2", "NOMBRE": "ÁLFA SAS"}], "agregar"
    )  # renombrar BETA como ALFA
    assert r.status_code in (400, 409, 422), r.text
    assert _empresas(cliente)["3"] == "GAMA LTDA" and _empresas(cliente)["2"] == "BETA SAS"


def test_importar_empresas_no_pisa_a_una_empresa_creada_en_la_aplicacion(cliente):
    cliente.post("/api/empresas", json={"nombre": "ZETA SAS"})
    r = _importar_empresas(cliente, [{"CODIGO_EMPRESA": "50", "NOMBRE": "Zeta S.A.S."}], "agregar")
    assert r.status_code in (400, 409, 422) and "ZETA SAS" in r.json()["detail"], r.text


def test_lo_que_si_es_nuevo_se_sigue_importando_y_el_excel_base_tambien(cliente):
    ok = _importar_empresas(
        cliente,
        [{"CODIGO_EMPRESA": "30", "NOMBRE": "TREINTA SAS", "TELEFONO": "3001234567", "CORREO": "t@x.com"}],
        "agregar",
    )
    assert ok.status_code == 200, ok.text
    assert (
        cliente.post("/api/admin/importar", json={"tablas": ["empresas"], "modo": "reemplazar"}).status_code == 200
    )  # EMPRESA.xlsx de siempre


# ================================================================================================ Cargar datos → Proveedores y Cotizaciones
def test_cargar_proveedores_no_crea_uno_con_el_nombre_de_otro_escrito_distinto(cliente):
    antes = _empresas(cliente)
    r = subir(cliente, "proveedores", excel_bytes([{"CODIGO_EMPRESA": "20", "NOMBRE": "ÁLFA S.A.S."}]), aplicar=True)
    assert r.status_code == 200 and r.json()["nuevos"] == 0 and r.json()["total_errores"] == 1, r.text
    assert _empresas(cliente) == antes


def test_cargar_proveedores_con_dos_formas_del_mismo_nombre_nuevo_crea_uno_solo(cliente):
    filas = [{"CODIGO_EMPRESA": "21", "NOMBRE": "NUEVA CIA"}, {"CODIGO_EMPRESA": "22", "NOMBRE": "Nueva Cía."}]
    r = subir(cliente, "proveedores", excel_bytes(filas), aplicar=True)
    assert r.json()["nuevos"] == 1 and r.json()["total_errores"] == 1, r.text
    assert sum(1 for n in _empresas(cliente).values() if n.upper().startswith("NUEVA C")) == 1


def test_cargar_proveedores_sin_codigo_reconoce_al_que_ya_existe(cliente):
    antes = _empresas(cliente)
    r = subir(cliente, "proveedores", excel_bytes([{"NOMBRE": "gama ltda."}, {"NOMBRE": "DELTA S.A."}]), aplicar=True)
    assert r.status_code == 200 and r.json()["nuevos"] == 0, r.text
    assert _empresas(cliente) == antes


def test_cargar_cotizaciones_reconoce_al_proveedor_aunque_el_nombre_venga_distinto(cliente):
    antes = _empresas(cliente)
    archivo = excel_bytes([{"COD_PRODUCTO": "D4", "VALOR": 10, "EMPRESA": "alfa s.a.s."}])
    r = subir(cliente, "cotizaciones", archivo, aplicar=True)
    assert r.status_code == 200 and r.json()["total_errores"] == 0 and r.json()["nuevos"] == 1, r.text
    assert _empresas(cliente) == antes  # la oferta quedó a nombre de ALFA; no se creó otro proveedor
    d4 = cliente.get("/api/productos/D4/ofertas", params={"limite": 50}).json()["ofertas"]
    assert [o["empresa"] for o in d4] == ["ALFA SAS"]


def test_cargar_cotizaciones_con_un_proveedor_nuevo_escrito_en_pantalla_no_duplica(cliente):
    archivo = excel_bytes([{"COD_PRODUCTO": "D4", "VALOR": 10}])
    assert subir(cliente, "cotizaciones", archivo, aplicar=True, empresa_nueva="Cía. Ñandú S.A.S.").status_code == 200
    antes = _empresas(cliente)
    assert subir(cliente, "cotizaciones", archivo, aplicar=True, empresa_nueva="CIA NANDU SAS").status_code == 200
    assert _empresas(cliente) == antes  # la segunda vez reconoce al proveedor que se creó la primera
    assert subir(cliente, "cotizaciones", archivo, aplicar=True, empresa_nueva="alfa s.a.s").status_code == 200
    assert _empresas(cliente) == antes  # y uno que ya existía tampoco se duplica


# ================================================================================================ productos
@pytest.mark.parametrize("codigo", ["a1", " A1 ", "a1  "])
def test_no_se_crea_un_producto_con_el_codigo_de_otro_escrito_distinto(cliente, codigo):
    antes = cliente.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["total"]
    r = cliente.post("/api/productos", json={"cod": codigo, "descripcion": "OTRO", "stock_max": 10, "existencias": 0})
    assert r.status_code == 409, (codigo, r.text)
    assert cliente.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["total"] == antes


def test_cargar_productos_con_un_codigo_que_ya_existe_lo_actualiza_en_vez_de_duplicarlo(cliente):
    antes = cliente.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["total"]
    r = subir(
        cliente,
        "productos",
        excel_bytes([{"COD_PRODUCTO": "a1", "DESCRIPCION": "ALFA PRODUCTO", "StockMax": 100}]),
        aplicar=True,
    )
    assert r.status_code == 200 and r.json()["nuevos"] == 0 and r.json()["total_errores"] == 0, r.text
    assert cliente.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["total"] == antes


# ================================================================================================ personas
def test_los_usuarios_no_se_repiten_aunque_se_escriban_distinto(cliente):
    base = {"usuario": "ana.lopez", "nombre": "Ana", "rol": "consulta", "correo": "ana@x.com", "celular": "3201234567"}
    assert cliente.post("/api/usuarios", json=base).status_code == 201
    for cambio in (
        {"usuario": "ANA.LOPEZ"},
        {"usuario": " ana.lopez "},
        {"correo": "ANA@X.COM"},
        {"celular": "+57 320 123 4567"},
    ):
        otro = {**base, "usuario": "otra.persona", "correo": "otra@x.com", "celular": "3109999999", **cambio}
        assert cliente.post("/api/usuarios", json=otro).status_code == 409, cambio
