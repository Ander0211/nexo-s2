"""
PRUEBAS DE LA CARGA DE EXCEL DESDE LA PANTALLA (productos, proveedores y cotizaciones)

Cada tipo se prueba en sus dos pasos: REVISAR (aplicar=false: cuenta lo que pasaría sin escribir) y CARGAR (aplicar=true).
Usa los datos inventados de conftest.py: productos A1, B2, C3, D4, F6, 0041 y proveedores 1 (ALFA), 2 (BETA), 3 (GAMA), 4 (DELTA).
Ranking de A1 antes de subir nada: BETA $85, GAMA $95, ALFA $100, DELTA $120, proveedor 5 $130.
"""

import io

import pandas as pd
from openpyxl import load_workbook

from tests.conftest import excel_bytes

OCTETOS = {"Content-Type": "application/octet-stream"}


def subir(c, tipo, contenido, nombre="archivo.xlsx", aplicar=False, **params):
    """Atajo: sube un archivo a /api/cargas/{tipo} igual que lo hace la pantalla (el archivo va como cuerpo)."""
    return c.post(
        f"/api/cargas/{tipo}",
        params={"nombre": nombre, "aplicar": "true" if aplicar else "false", **params},
        content=contenido,
        headers=OCTETOS,
    )


def _ofertas_a1(c):
    """Atajo: las ofertas de A1 como lista [(proveedor, valor, origen)] de la mejor a la peor."""
    ofertas = c.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["ofertas"]
    return [(o["empresa"], o["valor"], o["origen"]) for o in ofertas]


# --------------------------------------------------------------------------- Productos
FILAS_PRODUCTOS = [
    {
        "COD_PRODUCTO": "N1",
        "DESCRIPCION": "PRODUCTO NUEVO",
        "STOCKMAX": 50,
        "STOCKMIN": 10,
        "EXISTENCIAS": 5,
    },  # fila 2: se crea
    {
        "COD_PRODUCTO": "A1",
        "DESCRIPCION": None,
        "STOCKMAX": None,
        "STOCKMIN": None,
        "EXISTENCIAS": 90,
    },  # fila 3: actualiza
    {
        "COD_PRODUCTO": "B2",
        "DESCRIPCION": "BETA PRODUCTO",
        "STOCKMAX": 10,
        "STOCKMIN": 3,
        "EXISTENCIAS": 10,
    },  # fila 4: igual
    {
        "COD_PRODUCTO": None,
        "DESCRIPCION": "SIN CÓDIGO",
        "STOCKMAX": 1,
        "STOCKMIN": 0,
        "EXISTENCIAS": 0,
    },  # fila 5: error
    {
        "COD_PRODUCTO": "N2",
        "DESCRIPCION": "MAL NÚMERO",
        "STOCKMAX": "abc",
        "STOCKMIN": 0,
        "EXISTENCIAS": 0,
    },  # fila 6: error
    {"COD_PRODUCTO": "N1", "DESCRIPCION": "REPETIDO", "STOCKMAX": 1, "STOCKMIN": 0, "EXISTENCIAS": 0},  # fila 7: error
]


def test_productos_revisar_cuenta_pero_no_escribe(cliente):
    """Revisar (aplicar=false) informa qué pasaría y NO toca la base de datos."""
    r = subir(cliente, "productos", excel_bytes(FILAS_PRODUCTOS))
    assert r.status_code == 200
    j = r.json()
    assert j["aplicado"] is False and j["filas"] == 6
    assert (j["nuevos"], j["actualizados"], j["sin_cambios"], j["total_errores"]) == (1, 1, 1, 3)
    assert {e["fila"] for e in j["errores"]} == {5, 6, 7}  # los números de fila son los que se ven en Excel
    assert cliente.get("/api/productos/N1").status_code == 404  # no se creó
    assert cliente.get("/api/productos/A1").json()["existencias"] == 20  # no se cambió


def test_productos_cargar_crea_y_actualiza(cliente):
    """Cargar (aplicar=true) crea los nuevos, actualiza los existentes y omite las filas con error."""
    j = subir(cliente, "productos", excel_bytes(FILAS_PRODUCTOS), aplicar=True).json()
    assert j["aplicado"] is True and (j["nuevos"], j["actualizados"]) == (1, 1)
    n1 = cliente.get("/api/productos/N1").json()
    assert n1["origen"] == "subido" and n1["es_propio"] and n1["stock_max"] == 50
    a1 = cliente.get("/api/productos/A1").json()
    assert a1["existencias"] == 90 and a1["stock_max"] == 100  # solo cambió lo que el archivo traía
    assert a1["descripcion"] == "ALFA PRODUCTO" and a1["origen"] == "subido"  # celda vacía = no se toca
    assert cliente.get("/api/productos/N2").status_code == 404  # la fila con error no se cargó
    fila = next(i for i in cliente.get("/api/productos", params={"q": "N1"}).json()["items"] if i["cod"] == "N1")
    assert fila["comprar"] == 45


def test_productos_reconoce_encabezados_con_tildes_y_espacios(cliente):
    """«Código», «Descripción», «Stock Max»... se reconocen aunque no estén escritos como en la plantilla."""
    archivo = excel_bytes([{"Código": "T1", "Descripción": "CON TILDES", "Stock Max": 20, "Existencia": 4}])
    j = subir(cliente, "productos", archivo, aplicar=True).json()
    assert j["nuevos"] == 1
    assert cliente.get("/api/productos/T1").json()["stock_max"] == 20


def test_productos_desde_csv(cliente):
    """También se aceptan archivos .csv (aquí con punto y coma, como los guarda Excel en español)."""
    archivo = excel_bytes([{"COD_PRODUCTO": "C1", "DESCRIPCION": "DESDE CSV", "STOCKMAX": 8}], extension="csv")
    j = subir(cliente, "productos", archivo, nombre="datos.csv", aplicar=True).json()
    assert j["nuevos"] == 1 and cliente.get("/api/productos/C1").status_code == 200


def test_productos_nuevo_sin_descripcion_es_error(cliente):
    """Un producto NUEVO necesita descripción; uno existente no."""
    j = subir(cliente, "productos", excel_bytes([{"COD_PRODUCTO": "Z9", "STOCKMAX": 5}])).json()
    assert j["nuevos"] == 0 and j["total_errores"] == 1 and "descripción" in j["errores"][0]["motivo"]


def test_productos_minimo_mayor_que_maximo_es_error(cliente):
    """La regla «mínimo ≤ máximo» también se aplica a las filas del archivo."""
    archivo = excel_bytes([{"COD_PRODUCTO": "M1", "DESCRIPCION": "X", "STOCKMAX": 5, "STOCKMIN": 9}])
    j = subir(cliente, "productos", archivo).json()
    assert j["total_errores"] == 1 and "mínimo" in j["errores"][0]["motivo"]


# --------------------------------------------------------------------------- Errores del archivo
def test_archivos_invalidos_dan_mensajes_claros(cliente):
    """Formato no admitido, archivo vacío, dañado, solo encabezados, sin columnas obligatorias o demasiado grande."""
    valido = excel_bytes([{"COD_PRODUCTO": "Z1", "DESCRIPCION": "X"}])
    assert "Formato no admitido" in subir(cliente, "productos", valido, nombre="datos.txt").json()["detail"]
    assert subir(cliente, "productos", b"", nombre="a.xlsx").status_code == 422  # archivo vacío
    assert "No se pudo leer" in subir(cliente, "productos", b"esto no es un excel").json()["detail"]  # dañado
    # un Excel con encabezados pero sin ninguna fila de datos
    buffer = io.BytesIO()
    pd.DataFrame(columns=["COD_PRODUCTO", "DESCRIPCION"]).to_excel(buffer, index=False)
    assert "no tiene filas" in subir(cliente, "productos", buffer.getvalue()).json()["detail"]
    # le falta la columna del código, que es obligatoria
    falta = subir(cliente, "productos", excel_bytes([{"OTRA": 1}])).json()["detail"]
    assert falta.startswith("Faltan las columnas obligatorias") and "COD_PRODUCTO" in falta
    assert subir(cliente, "productos", b"x" * (16 * 1024 * 1024)).status_code == 413  # pesa más de 15 MB
    assert cliente.post("/api/cargas/otracosa", content=valido, headers=OCTETOS).status_code == 422  # tipo inexistente


# --------------------------------------------------------------------------- Proveedores
def test_proveedores_revisar_y_cargar(cliente):
    """Crea nuevos (con y sin código), renombra por código, reconoce por nombre y rechaza los conflictos."""
    filas = [
        {"CODIGO_EMPRESA": "90", "NOMBRE": "PROV NOVENTA"},  # nuevo, con código
        {"CODIGO_EMPRESA": None, "NOMBRE": "PROV SIN CODIGO"},  # nuevo, código automático
        {"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA RENOMBRADA"},  # el 1 existe: se renombra
        {"CODIGO_EMPRESA": None, "NOMBRE": "beta sas"},  # ya existe por nombre: sin cambios
        {"CODIGO_EMPRESA": "2", "NOMBRE": "GAMA LTDA"},  # error: ese nombre es del proveedor 3
        {"CODIGO_EMPRESA": "91", "NOMBRE": None},  # error: falta el nombre
    ]
    revisar = subir(cliente, "proveedores", excel_bytes(filas)).json()
    assert (revisar["nuevos"], revisar["actualizados"], revisar["sin_cambios"], revisar["total_errores"]) == (
        2,
        1,
        1,
        2,
    )
    assert "PROV NOVENTA" not in {e["nombre"] for e in cliente.get("/api/empresas").json()}  # revisar no escribe
    subir(cliente, "proveedores", excel_bytes(filas), aplicar=True)
    por_cod = {e["cod"]: e for e in cliente.get("/api/empresas").json()}
    assert por_cod["90"]["nombre"] == "PROV NOVENTA" and por_cod["90"]["origen"] == "subido"
    assert por_cod["1"]["nombre"] == "ALFA RENOMBRADA" and por_cod["1"]["origen"] == "subido"
    automatico = next(e for e in por_cod.values() if e["nombre"] == "PROV SIN CODIGO")
    assert int(automatico["cod"]) >= 1000


def test_proveedores_codigo_repetido_con_otro_nombre_es_error(cliente):
    """El mismo código dos veces en el archivo con nombres distintos no debe renombrar en silencio."""
    filas = [{"CODIGO_EMPRESA": "95", "NOMBRE": "PRIMERO"}, {"CODIGO_EMPRESA": "95", "NOMBRE": "SEGUNDO"}]
    j = subir(cliente, "proveedores", excel_bytes(filas), aplicar=True).json()
    assert j["nuevos"] == 1 and j["total_errores"] == 1
    assert {e["cod"]: e["nombre"] for e in cliente.get("/api/empresas").json()}["95"] == "PRIMERO"


# --------------------------------------------------------------------------- Cotizaciones
FILAS_COTIZACIONES = [
    {"COD_EMPRESA": "4", "COD_PRODUCTO": "A1", "VALOR": 50, "PRESENTACION": "X10"},  # fila 2: pasa a ser la mejor de A1
    {"COD_EMPRESA": "3", "COD_PRODUCTO": "C3", "VALOR": 40, "PRESENTACION": None},  # fila 3: nueva
    {"COD_EMPRESA": "1", "COD_PRODUCTO": "D4", "VALOR": None, "PRESENTACION": None},  # fila 4: sin precio → se omite
    {"COD_EMPRESA": "1", "COD_PRODUCTO": "B2", "VALOR": 0, "PRESENTACION": None},  # fila 5: precio 0 → se omite
    {"COD_EMPRESA": "1", "COD_PRODUCTO": "NOEXISTE", "VALOR": 9, "PRESENTACION": None},  # fila 6: error, producto
    {"COD_EMPRESA": "999", "COD_PRODUCTO": "A1", "VALOR": 9, "PRESENTACION": None},  # fila 7: error, proveedor
    {"COD_EMPRESA": "1", "COD_PRODUCTO": "0041", "VALOR": "caro", "PRESENTACION": None},  # fila 8: error, precio
]


def test_cotizaciones_con_columna_de_proveedor(cliente):
    """El archivo trae COD_EMPRESA: se crean ofertas 'subido', se omiten las sin precio y se informan los errores."""
    j = subir(cliente, "cotizaciones", excel_bytes(FILAS_COTIZACIONES)).json()
    assert (j["nuevos"], j["omitidas"], j["total_errores"]) == (2, 2, 3)
    assert {e["fila"] for e in j["errores"]} == {6, 7, 8}
    assert _ofertas_a1(cliente)[0][0] == "BETA SAS"  # revisar no cambió nada

    subir(cliente, "cotizaciones", excel_bytes(FILAS_COTIZACIONES), aplicar=True)
    assert _ofertas_a1(cliente)[0] == ("DELTA SA", 50, "subido")  # la nueva oferta es la mejor
    primera = cliente.get("/api/productos/A1/ofertas").json()["ofertas"][0]
    assert primera["presentacion"] == "X10" and primera["eliminable"] is True
    assert cliente.get("/api/productos/C3/ofertas").json()["ofertas"][0]["valor"] == 40


def test_cotizaciones_con_proveedor_elegido_en_pantalla(cliente):
    """Un archivo sin columna de proveedor usa el elegido en pantalla; sin ninguno da un error claro."""
    archivo = excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 60}, {"COD_PRODUCTO": "C3", "VALOR": 45}])
    sin_proveedor = subir(cliente, "cotizaciones", archivo)
    assert sin_proveedor.status_code == 422 and "columna del proveedor" in sin_proveedor.json()["detail"]
    j = subir(cliente, "cotizaciones", archivo, aplicar=True, cod_empresa="2").json()
    assert j["nuevos"] == 2 and j["proveedor"]["nombre"] == "BETA SAS"
    # BETA ya ofrecía A1 a $85 en el Excel base: su nueva oferta de $60 pasa a ser la que cuenta
    assert _ofertas_a1(cliente)[0] == ("BETA SAS", 60, "subido")
    assert subir(cliente, "cotizaciones", archivo, cod_empresa="999").status_code == 404


def test_cotizaciones_con_proveedor_nuevo_se_crea_solo_al_cargar(cliente):
    """Con un proveedor nuevo, revisar solo avisa que «se creará» y cargar lo crea de verdad (una sola vez)."""
    archivo = excel_bytes([{"COD_PRODUCTO": "A1", "VALOR": 70}, {"COD_PRODUCTO": "C3", "VALOR": 30}])
    revisar = subir(cliente, "cotizaciones", archivo, empresa_nueva="Proveedor Recién Llegado").json()
    assert "creará" in revisar["avisos"][0] and revisar["proveedor"]["nuevo"] is True
    assert "Proveedor Recién Llegado" not in {e["nombre"] for e in cliente.get("/api/empresas").json()}
    subir(cliente, "cotizaciones", archivo, aplicar=True, empresa_nueva="Proveedor Recién Llegado")
    nuevos = [e for e in cliente.get("/api/empresas").json() if e["nombre"] == "Proveedor Recién Llegado"]
    assert len(nuevos) == 1 and nuevos[0]["origen"] == "subido" and nuevos[0]["ofertas"] == 2
    # con el mismo nombre otra vez NO se duplica el proveedor: se reutiliza
    subir(cliente, "cotizaciones", archivo, aplicar=True, empresa_nueva="proveedor recién llegado")
    assert len([e for e in cliente.get("/api/empresas").json() if "Recién" in e["nombre"]]) == 1


def test_cotizaciones_por_nombre_de_proveedor(cliente):
    """En vez del código, el archivo puede traer una columna EMPRESA con el nombre exacto del proveedor."""
    archivo = excel_bytes(
        [
            {"EMPRESA": "gama ltda", "COD_PRODUCTO": "A1", "VALOR": 55},
            {"EMPRESA": "NO EXISTE", "COD_PRODUCTO": "A1", "VALOR": 5},
        ]
    )
    j = subir(cliente, "cotizaciones", archivo, aplicar=True).json()
    assert j["nuevos"] == 1 and j["total_errores"] == 1 and "NO EXISTE" in j["errores"][0]["motivo"]
    assert _ofertas_a1(cliente)[0] == ("GAMA LTDA", 55, "subido")


def test_cotizaciones_repetidas_en_el_archivo_usa_la_mas_barata(cliente):
    """El mismo producto y proveedor dos veces en el archivo: se queda con el precio más bajo."""
    archivo = excel_bytes(
        [
            {"COD_EMPRESA": "4", "COD_PRODUCTO": "A1", "VALOR": 60},
            {"COD_EMPRESA": "4", "COD_PRODUCTO": "A1", "VALOR": 55},
        ]
    )
    j = subir(cliente, "cotizaciones", archivo, aplicar=True).json()
    assert j["nuevos"] == 1 and j["repetidas"] == 1
    assert _ofertas_a1(cliente)[0] == ("DELTA SA", 55, "subido")


def test_cotizaciones_volver_a_subir_actualiza_o_no_cambia(cliente):
    """Subir otra vez: mismo precio = «sin cambios»; precio distinto = «actualizada» (no se duplica la oferta)."""
    fila = {"COD_EMPRESA": "4", "COD_PRODUCTO": "A1", "VALOR": 60, "PRESENTACION": "X1"}
    subir(cliente, "cotizaciones", excel_bytes([fila]), aplicar=True)
    igual = subir(cliente, "cotizaciones", excel_bytes([fila]), aplicar=True).json()
    assert (igual["nuevos"], igual["actualizados"], igual["sin_cambios"]) == (0, 0, 1)
    nuevo = subir(cliente, "cotizaciones", excel_bytes([{**fila, "VALOR": 58}]), aplicar=True).json()
    assert (nuevo["nuevos"], nuevo["actualizados"]) == (0, 1)
    assert [o for o in _ofertas_a1(cliente) if o[0] == "DELTA SA"] == [("DELTA SA", 58, "subido")]


def test_cotizaciones_que_no_mejoran_lo_que_ya_habia_se_avisan(cliente):
    """Si ese proveedor ya ofrecía el producto igual o más barato en el Excel base, se cuenta en «no_cambian_ranking»."""
    archivo = excel_bytes([{"COD_EMPRESA": "2", "COD_PRODUCTO": "A1", "VALOR": 90}])  # BETA ya ofrecía A1 a $85
    j = subir(cliente, "cotizaciones", archivo, aplicar=True).json()
    assert j["nuevos"] == 1 and j["no_cambian_ranking"] == 1
    assert _ofertas_a1(cliente)[0] == ("BETA SAS", 85, "excel")  # el ranking sigue igual


def test_oferta_subida_se_puede_eliminar(cliente):
    """Las ofertas subidas son propias: se pueden eliminar igual que las agregadas a mano."""
    subir(cliente, "cotizaciones", excel_bytes([{"COD_EMPRESA": "4", "COD_PRODUCTO": "A1", "VALOR": 50}]), aplicar=True)
    oferta = cliente.get("/api/productos/A1/ofertas").json()["ofertas"][0]
    assert oferta["origen"] == "subido"
    assert cliente.delete(f"/api/ofertas/{oferta['id']}").status_code == 200
    assert _ofertas_a1(cliente)[0][0] == "BETA SAS"


# --------------------------------------------------------------------------- Persistencia y plantillas
def test_lo_subido_sobrevive_a_actualizar_excel(cliente):
    """Lo cargado desde un Excel es dato propio: «Actualizar Excel» recarga la base pero no lo borra."""
    subir(
        cliente, "productos", excel_bytes([{"COD_PRODUCTO": "N1", "DESCRIPCION": "NUEVO", "STOCKMAX": 9}]), aplicar=True
    )
    subir(cliente, "proveedores", excel_bytes([{"CODIGO_EMPRESA": "90", "NOMBRE": "PROV NOVENTA"}]), aplicar=True)
    subir(cliente, "cotizaciones", excel_bytes([{"COD_EMPRESA": "90", "COD_PRODUCTO": "N1", "VALOR": 7}]), aplicar=True)
    subir(cliente, "cotizaciones", excel_bytes([{"COD_EMPRESA": "4", "COD_PRODUCTO": "A1", "VALOR": 50}]), aplicar=True)
    assert cliente.post("/api/importar").status_code == 200
    assert cliente.get("/api/productos/N1").json()["origen"] == "subido"
    assert "PROV NOVENTA" in {e["nombre"] for e in cliente.get("/api/empresas").json()}
    assert cliente.get("/api/productos/N1/ofertas").json()["ofertas"][0]["valor"] == 7
    assert _ofertas_a1(cliente)[0] == ("DELTA SA", 50, "subido")


def test_plantillas_descargables_y_listas_para_llenar(cliente):
    """Cada plantilla trae solo los encabezados (vacía) + hoja de instrucciones, y se puede llenar y subir."""
    esperados = {
        "productos": ["COD_PRODUCTO", "DESCRIPCION", "STOCKMAX", "STOCKMIN", "EXISTENCIAS"],
        "proveedores": ["CODIGO_EMPRESA", "NOMBRE"],
    }
    for tipo, encabezados in esperados.items():
        r = cliente.get(f"/api/plantillas/{tipo}")
        assert r.status_code == 200 and f"PLANTILLA_{tipo.upper()}.xlsx" in r.headers["content-disposition"]
        libro = load_workbook(io.BytesIO(r.content))
        assert libro.sheetnames == ["DATOS", "INSTRUCCIONES"]
        assert [c.value for c in libro["DATOS"][1]] == encabezados
        # sin filas de ejemplo: todas las celdas bajo el encabezado están vacías (aunque tengan formato de texto),
        # así que subir la plantilla sin llenar no carga nada por error
        assert all(c.value is None for fila in libro["DATOS"].iter_rows(min_row=2) for c in fila)
        assert subir(cliente, tipo, r.content).json()["detail"].startswith("El archivo no tiene filas")
    # la plantilla de COTIZACIONES es la ficha oficial FR-GDS-07 (con los productos por comprar): sin precios, subirla no carga nada
    r = cliente.get("/api/plantillas/cotizaciones")
    assert r.status_code == 200 and "FR-GDS-07_Ficha_Cotizacion.xlsx" in r.headers["content-disposition"]
    assert load_workbook(io.BytesIO(r.content)).worksheets[0].title == "FICHA DE COTIZACIÓN"
    antes = cliente.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["total_ofertas"]
    vacia = subir(cliente, "cotizaciones", r.content, "ficha.xlsx", aplicar=True, cod_empresa="3").json()
    assert (
        vacia["nuevos"] == 0 and vacia["total_errores"] == 0 and vacia["omitidas"] >= 4
    )  # todos «sin precio»: se omiten, sin errores
    assert cliente.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["total_ofertas"] == antes
    assert cliente.get("/api/plantillas/otracosa").status_code == 422

    # ida y vuelta: se llena la plantilla de productos y se sube
    libro = load_workbook(io.BytesIO(cliente.get("/api/plantillas/productos").content))
    libro["DATOS"].append(["0777", "PRODUCTO DE LA PLANTILLA", 30, 5, 2])
    buffer = io.BytesIO()
    libro.save(buffer)
    j = subir(cliente, "productos", buffer.getvalue(), aplicar=True).json()
    assert j["nuevos"] == 1
    assert cliente.get("/api/productos/0777").json()["stock_max"] == 30  # el código conserva sus ceros
