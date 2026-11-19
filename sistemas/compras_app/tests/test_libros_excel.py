"""LA FICHA FR-GDS-07 (la que descarga el proveedor), LA ORDEN DE COMPRA (OC) Y EL LIBRO DE ALTERNATIVAS (2.º a 4.º PROVEEDOR).

Datos de conftest.py. Para A1 el ranking es: BETA $85 · GAMA $95 · ALFA $100 · DELTA $120 · proveedor 5 $130 (BETA aparece dos veces en el Excel:
cuenta una sola). Hay que comprar A1 (80), C3 (5, solo ALFA a $50), 0041 (6, solo ALFA a $7) y D4 (5, nadie lo ofrece).
Ganadores = BETA (A1), ALFA (C3 y 0041). Inversión = 85×80 + 50×5 + 7×6 = 7.092.
"""

import io
from datetime import date

import openpyxl

from app.services import libros_excel
from tests.test_admin import CONTACTO, _fila
from tests.test_cargas import subir

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _libro(respuesta) -> openpyxl.Workbook:
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"].startswith(XLSX)
    return openpyxl.load_workbook(io.BytesIO(respuesta.content))


def _ficha(c):
    return _libro(c.get("/api/proveedor/excel"))


def _poner_contacto(cliente, cod="1", nombre="ALFA SAS"):
    f = _fila(cliente, "empresas", CODIGO_EMPRESA=cod)
    r = cliente.put(
        f"/api/admin/tablas/empresas/filas/{f['id']}",
        json={"valores": {"CODIGO_EMPRESA": cod, "NOMBRE": nombre, **CONTACTO}},
    )
    assert r.status_code == 200, r.text


# ================================================================================================ FICHA FR-GDS-07
def test_la_ficha_del_proveedor_es_la_FR_GDS_07_con_los_productos_por_comprar(cliente, como):
    externo = como("externo", cod_empresa="1")
    r = externo.get("/api/proveedor/excel")
    assert "FR-GDS-07_Ficha_Cotizacion_ALFA_SAS.xlsx" in r.headers["content-disposition"]
    wb = _libro(r)
    ws = wb.worksheets[0]
    assert ws.title == "FICHA DE COTIZACIÓN" and "FR-GDS-07" in ws["K1"].value  # el encabezado oficial del formato
    # los mismos productos que ve en la pantalla «Productos que necesitamos», en el mismo orden (A–Z por descripción)
    pantalla = [
        (i["cod"], i["descripcion"])
        for i in externo.get("/api/proveedor/productos", params={"tam": 100}).json()["items"]
    ]
    assert pantalla and sorted(pantalla, key=lambda x: x[1].lower()) == pantalla
    filas = [(ws.cell(r, 1).value, ws.cell(r, 2).value) for r in range(12, 12 + len(pantalla))]
    assert filas == pantalla
    assert ws.cell(12 + len(pantalla), 1).value is None  # y ni una fila más
    assert ws["D5"].value == date.today().strftime("%d/%m/%Y")  # fecha de la solicitud
    assert ws["B8"].value == "ALFA SAS"  # razón social del proveedor que la descarga


def test_la_ficha_no_lleva_cantidades_precios_ni_datos_internos(cliente, como):
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 4321})
    wb = _ficha(como("externo", cod_empresa="1"))
    ws = wb.worksheets[0]
    ultima = 11 + len(
        como("externo", cod_empresa="1").get("/api/proveedor/productos", params={"tam": 100}).json()["items"]
    )
    assert all(
        ws.cell(r, 10).value is None for r in range(12, ultima + 1)
    )  # «cantidad solicitada»: vacía, el proveedor no ve cantidades
    for c in (6, 7, 8, 11, 12):  # precio techo, precio, IVA, empaque, cantidad disponible: sin nada escrito
        assert all(ws.cell(r, c).value is None for r in range(12, ultima + 1)), c
    texto = " ".join(str(c.value) for fila in ws.iter_rows() for c in fila if c.value is not None)
    assert "4321" not in texto and "ALFA PRODUCTO" in texto
    assert wb.sheetnames == [
        "FICHA DE COTIZACIÓN",
        "SUMIPABON",
    ]  # sin las hojas ocultas con datos internos del original
    assert [s.sheet_state for s in wb.worksheets] == ["visible", "veryHidden"]


def test_la_ficha_conserva_formato_proteccion_logos_y_ayudas(cliente, como):
    ws = _ficha(como("externo", cod_empresa="1")).worksheets[0]
    assert ws.protection.sheet is True  # la hoja sigue protegida como en el original
    for c in (1, 2, 5, 9, 10):  # código, producto, marca, precio+IVA y cantidad solicitada: bloqueadas
        assert ws.cell(12, c).protection.locked, c
        assert ws.cell(13, c).protection.locked, c
    for c in (
        4,
        7,
        8,
        11,
        12,
    ):  # detalle, precio, IVA, empaque y cantidad disponible: las únicas que el proveedor puede escribir
        assert not ws.cell(12, c).protection.locked and not ws.cell(13, c).protection.locked, c
    assert ws["I12"].value == "=G12+H12" and ws["I13"].value == "=G13+H13"  # PRECIO + IVA
    assert len(ws._images) == 2  # los dos logos del encabezado
    assert (
        sum(1 for fila in ws.iter_rows(min_row=1, max_row=12) for c in fila if c.comment) >= 8
    )  # las ayudas de cada encabezado
    assert "G11" in {c.coordinate for fila in ws.iter_rows(min_row=11, max_row=11) for c in fila if c.comment}
    assert {str(m) for m in ws.merged_cells.ranges if m.min_row in (12, 13)} == {
        "B12:C12",
        "B13:C13",
    }  # descripción en B:C


def test_la_ficha_trae_el_control_de_cambios_debajo_de_los_productos(cliente, como):
    ws = _ficha(como("externo", cod_empresa="1")).worksheets[0]
    n = len(como("externo", cod_empresa="1").get("/api/proveedor/productos", params={"tam": 100}).json()["items"])
    assert ws.cell(12 + n, 1).value is None  # una fila de aire entre el último producto y la tabla
    inicio = 13 + n
    assert ws.cell(inicio, 1).value == "Control de Cambios del Documento"
    assert [ws.cell(inicio + 1, c).value for c in (1, 3, 5)] == ["Versión", "Fecha", "Descripción de Actividades"]
    assert ws.cell(inicio + 2, 1).value == 6 and "proveedores" in ws.cell(inicio + 2, 5).value


def test_la_ficha_lleva_telefono_y_correo_del_proveedor_y_su_codigo_oculto(cliente, como):
    _poner_contacto(cliente)
    wb = _ficha(como("externo", cod_empresa="1"))
    ws = wb.worksheets[0]
    assert ws["K8"].value == "contacto@empresa.com" and ws["K9"].value == "+573001234567"
    assert (
        wb["SUMIPABON"]["B1"].value == "1" and wb["SUMIPABON"]["B2"].value == "FR-GDS-07"
    )  # para reconocer al proveedor al subirla


def test_el_codigo_se_guarda_como_texto_y_la_marca_queda_vacia_para_que_la_escriba_el_proveedor(cliente, como):
    ws = _ficha(como("externo", cod_empresa="1")).worksheets[0]
    n = len(como("externo", cod_empresa="1").get("/api/proveedor/productos", params={"tam": 100}).json()["items"])
    codigos = {ws.cell(r, 1).value: r for r in range(12, 12 + n)}
    assert all(isinstance(c, str) for c in codigos) and "0041" in codigos  # «0041» no se vuelve 41
    assert ws.cell(codigos["0041"], 1).data_type == "s"
    assert all(
        ws.cell(r, 5).value is None for r in codigos.values()
    )  # MARCA / LABORATORIO sale vacía: la escribe cada proveedor
    assert not (
        libros_excel.PLANTILLAS / "ficha_marcas.json"
    ).exists()  # y el proyecto no guarda marcas de ningún Excel


def test_la_ficha_sin_productos_por_comprar_sale_con_el_formato_completo(cliente, como):
    for cod in ("A1", "C3", "D4", "0041"):
        cliente.put(f"/api/productos/{cod}/cantidad", json={"cantidad": 0})  # nada por comprar
    ws = _ficha(como("externo", cod_empresa="1")).worksheets[0]
    assert (
        ws.cell(12, 1).value is None and ws.cell(14, 1).value == "Control de Cambios del Documento"
    )  # sin productos: solo la fila modelo vacía


def test_la_plantilla_de_cotizaciones_de_cargar_datos_es_la_ficha_original(cliente):
    wb = _libro(cliente.get("/api/plantillas/cotizaciones"))
    assert wb.sheetnames == ["FICHA DE COTIZACIÓN", "SUMIPABON"] and "FR-GDS-07" in wb.worksheets[0]["K1"].value
    assert wb["SUMIPABON"]["B1"].value in (None, "")  # sin proveedor: se elige al subirla
    productos = _libro(cliente.get("/api/plantillas/productos"))  # las demás plantillas siguen igual
    assert productos.sheetnames == ["DATOS", "INSTRUCCIONES"]


# ================================================================================================ SUBIR LA FICHA DE VUELTA
def _diligenciar(contenido: bytes, precios: dict[str, tuple], quitar_meta: bool = False) -> bytes:
    """Hace lo que haría el proveedor: escribe precio (G), IVA (H), empaque (K) y, si se da, la cantidad disponible (L) de los productos indicados."""
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    ws = wb.worksheets[0]
    for r in range(12, ws.max_row + 1):
        cod = ws.cell(r, 1).value
        if cod in precios:
            precio, iva, empaque, *resto = precios[cod]
            ws.cell(r, 7).value, ws.cell(r, 8).value, ws.cell(r, 11).value = precio, iva, empaque
            if resto:  # el 4.º dato, opcional: la «cantidad disponible proveedor» (columna L)
                ws.cell(r, 12).value = resto[0]
    if quitar_meta:
        wb.remove(wb["SUMIPABON"])
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def test_la_ficha_diligenciada_se_sube_tal_cual_y_el_precio_es_el_que_no_lleva_iva(cliente, como):
    ficha = como("externo", cod_empresa="3").get("/api/proveedor/excel").content  # GAMA LTDA (3) la descarga
    llena = _diligenciar(ficha, {"A1": (70, 13.3, "X10"), "C3": (40, 0, "X1")})
    r = subir(
        cliente, "cotizaciones", llena, "ficha.xlsx", aplicar=True
    )  # sin elegir proveedor: sale de la hoja oculta
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["aplicado"] is True and res["nuevos"] == 2 and res["total_errores"] == 0, res
    assert res["omitidas"] >= 1  # el resto de productos de la ficha no traían precio: se omiten sin error
    ofertas = {
        o["empresa"]: o for o in cliente.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["ofertas"]
    }
    assert (
        ofertas["GAMA LTDA"]["valor"] == 70 and ofertas["GAMA LTDA"]["presentacion"] == "X10"
    )  # PRECIO (G), no PRECIO + IVA (G + H = 83,3)
    assert ofertas["GAMA LTDA"]["origen"] == "subido"
    c3 = {o["empresa"]: o for o in cliente.get("/api/productos/C3/ofertas", params={"limite": 50}).json()["ofertas"]}
    assert c3["GAMA LTDA"]["valor"] == 40


def test_subir_la_ficha_primero_solo_revisa_y_no_cambia_nada(cliente, como):
    ficha = como("externo", cod_empresa="3").get("/api/proveedor/excel").content
    antes = cliente.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["total_ofertas"]
    r = subir(cliente, "cotizaciones", _diligenciar(ficha, {"A1": (70, 0, "X1")}), "ficha.xlsx", aplicar=False)
    assert r.status_code == 200 and r.json()["aplicado"] is False
    assert cliente.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["total_ofertas"] == antes


def test_la_ficha_sin_la_hoja_oculta_se_sube_eligiendo_el_proveedor_en_pantalla(cliente, como):
    ficha = como("externo").get("/api/proveedor/excel").content
    llena = _diligenciar(ficha, {"A1": (70, 0, "X1")}, quitar_meta=True)
    sin = subir(cliente, "cotizaciones", llena, "ficha.xlsx", aplicar=True)
    assert sin.status_code in (422, 400) and (
        "proveedor" in sin.text.lower() or "empresa" in sin.text.lower()
    )  # no se sabe de quién es
    ok = subir(cliente, "cotizaciones", llena, "ficha.xlsx", aplicar=True, cod_empresa="3")
    assert ok.status_code == 200, ok.text
    ofertas = {
        o["empresa"]: o["valor"]
        for o in cliente.get("/api/productos/A1/ofertas", params={"limite": 50}).json()["ofertas"]
    }
    assert ofertas["GAMA LTDA"] == 70


def test_un_precio_que_no_es_numero_en_la_ficha_se_reporta_con_su_fila_real(cliente, como):
    ficha = como("externo", cod_empresa="3").get("/api/proveedor/excel").content
    wb = openpyxl.load_workbook(io.BytesIO(ficha))
    ws = wb.worksheets[0]
    fila = next(r for r in range(12, 40) if ws.cell(r, 1).value == "A1")
    ws.cell(fila, 7).value = "abc"
    salida = io.BytesIO()
    wb.save(salida)
    r = subir(cliente, "cotizaciones", salida.getvalue(), "ficha.xlsx")
    assert r.status_code == 200 and [e["fila"] for e in r.json()["errores"]] == [
        fila
    ]  # dice la fila de la ficha, no un número cualquiera


def test_la_tabla_de_control_de_cambios_no_se_confunde_con_un_producto(cliente, como):
    ficha = como("externo", cod_empresa="3").get("/api/proveedor/excel").content
    r = subir(cliente, "cotizaciones", _diligenciar(ficha, {"A1": (70, 0, "X1")}), "ficha.xlsx")
    assert (
        r.status_code == 200 and r.json()["errores"] == []
    )  # «Control de Cambios del Documento», «Versión»... no dan errores


def test_un_excel_cualquiera_se_sigue_leyendo_como_antes(cliente):
    simple = openpyxl.Workbook()
    simple.active.append(["COD_PRODUCTO", "VALOR", "PRESENTACION"])
    simple.active.append(["A1", 70, "X1"])
    salida = io.BytesIO()
    simple.save(salida)
    r = subir(cliente, "cotizaciones", salida.getvalue(), "otro.xlsx", cod_empresa="3")
    assert r.status_code == 200 and r.json()["errores"] == []


# ================================================================================================ ORDEN DE COMPRA (OC)
def _oc(c):
    return _libro(c.get("/api/exportar/oc"))


def _tabla(ws, desde, hasta_col):
    return [
        [c.value for c in fila[:hasta_col]]
        for fila in ws.iter_rows(min_row=desde)
        if any(c.value is not None for c in fila[:hasta_col])
    ]


def test_la_oc_trae_las_tres_hojas_y_los_ganadores(cliente):
    r = cliente.get("/api/exportar/oc")
    assert f"OC_{date.today().isoformat()}.xlsx" in r.headers["content-disposition"]
    wb = _libro(r)
    assert wb.sheetnames == ["VALORES", "DINAMICA", "ORDENES"]
    # VALORES: los datos de cada producto a comprar y su proveedor ganador
    valores = _tabla(wb["VALORES"], 1, 8)
    assert valores[0][0] == "COD_PRODUCTO" and len(valores) == 4  # encabezado + A1, C3 y 0041
    # DINAMICA: una fila por proveedor ganador y producto (encabezado en la fila 3, como en OC.xlsm)
    din = _tabla(wb["DINAMICA"], 3, 5)
    assert din[0] == ["NOM_EMPRESA", "COD_PRODUCTO", "DESCRIPCION", "Suma de CANT_COMPRAR", "Mín. de VALOR"]
    assert {(f[0], f[1], f[3], f[4]) for f in din[1:]} == {
        ("BETA SAS", "A1", 80, 85),
        ("ALFA SAS", "C3", 5, 50),
        ("ALFA SAS", "0041", 6, 7),
    }
    assert [f[0] for f in din[1:]] == ["ALFA SAS", "ALFA SAS", "BETA SAS"]  # por proveedor
    assert (
        sum(f[3] * f[4] for f in din[1:]) == cliente.get("/api/resumen").json()["inversion_total"] == 7092
    )  # lo mismo que dice el tablero


def test_la_hoja_ordenes_conserva_el_formato_y_las_formulas_del_original(cliente):
    o = _oc(cliente)["ORDENES"]
    assert [o[c].value for c in ("A1", "B1", "C1", "G1", "Q1", "S1", "V1", "Y1")] == [
        "EMPRESA GANADORA",
        "ITEM",
        "CODIGO PRODUCTO",
        "DESCRIPCION PRODUCTO",
        "CANT.  COMPRAR",
        "VR. UNITARIO",
        "VR. TOTAL",
        "IVA",
    ]
    assert [o[c].value for c in ("A2", "B2", "C2", "G2", "Q2", "S2", "V2")] == [
        "=DINAMICA!A4",
        "=ROWS($A$2:A2)",
        "=DINAMICA!B4",
        "=DINAMICA!C4",
        "=DINAMICA!D4",
        "=DINAMICA!E4",
        "=S2*Q2",
    ]
    assert (
        o["B3"].value == "=IF(A3<>0,B2+1,((B2-B2)))" and o["V4"].value == "=S4*Q4" and o["A4"].value == "=DINAMICA!A6"
    )
    assert o["Y2"].value is None  # el IVA queda vacío, como en OC.xlsm
    # 3 productos de 2 proveedores + UNA FILA EN BLANCO después de cada proveedor (como OC.xlsm) + el encabezado
    assert o.max_row == 6
    for fila in (1, 2, 3, 4, 5, 6):  # las mismas celdas combinadas del original en cada fila (también en las de separación)
        assert {str(m) for m in o.merged_cells.ranges if m.min_row == fila} == {
            f"{a}{fila}:{b}{fila}" for a, b in (("C", "F"), ("G", "P"), ("Q", "R"), ("S", "U"), ("V", "X"), ("Y", "Z"))
        }
    assert o["Q2"].number_format == "General" and o["A1"].font.b and o.row_dimensions[1].height > 30  # «General» como OC.xlsm


def test_dinamica_deja_una_fila_en_blanco_por_proveedor_y_el_item_se_reinicia(cliente):
    """Como en OC.xlsm: en DINAMICA, después de cada proveedor queda una fila vacía; en ORDENES esa fila da 0 (se oculta) y el ITEM
    del proveedor siguiente vuelve a empezar en 1."""
    wb = openpyxl.load_workbook(io.BytesIO(cliente.get("/api/exportar/oc").content), data_only=True)
    d, o = wb["DINAMICA"], wb["ORDENES"]
    assert [[d.cell(r, c).value for c in (1, 2)] for r in range(4, 9)] == [
        ["ALFA SAS", "0041"], ["ALFA SAS", "C3"], [None, None], ["BETA SAS", "A1"], [None, None]]
    assert [o.cell(r, 2).value for r in range(2, 7)] == [1, 2, 0, 1, 0]  # ITEM: 1, 2 · (separador) · 1 · (separador)
    assert [o.cell(r, 1).value for r in range(2, 7)] == ["ALFA SAS", "ALFA SAS", 0, "BETA SAS", 0]
    assert d.column_dimensions["C"].width > 100  # descripción ancha, como OC.xlsm
    # encabezado como lo muestra la tabla dinámica de OC.xlsm: azul (énfasis 1 del tema) con letra blanca en negrita
    for c in ("A3", "B3", "C3", "D3", "E3"):
        assert d[c].font.b and d[c].font.color.theme == 0 and d[c].fill.fgColor.theme == 4


def test_la_oc_respeta_el_proveedor_elegido_a_mano_y_la_cantidad_editada(cliente):
    cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "1"})  # se le comprará A1 a ALFA ($100)
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 100})
    din = _tabla(_oc(cliente)["DINAMICA"], 4, 5)
    assert ("ALFA SAS", "A1", "ALFA PRODUCTO", 100, 100) in {
        tuple(f) for f in din
    }  # el elegido y la cantidad editada, no la mejor oferta ni la calculada
    assert not any(f[0] == "BETA SAS" for f in din)


def test_la_oc_deja_afuera_lo_que_no_hay_que_comprar_o_nadie_ofrece(cliente):
    cliente.put("/api/productos/C3/cantidad", json={"cantidad": 0})
    codigos = [f[1] for f in _tabla(_oc(cliente)["DINAMICA"], 4, 5)]
    assert sorted(codigos) == ["0041", "A1"]  # C3 se puso en 0; D4 no tiene ofertas
    assert "D4" not in codigos


def test_la_oc_sin_nada_por_comprar_sale_vacia_pero_valida(cliente):
    for cod in ("A1", "C3", "D4", "0041"):
        cliente.put(f"/api/productos/{cod}/cantidad", json={"cantidad": 0})
    wb = _oc(cliente)
    assert wb.sheetnames == [
        "VALORES",
        "DINAMICA",
        "ORDENES",
    ]  # sin nada por comprar: las tres hojas, solo con su encabezado
    assert (
        wb["ORDENES"].max_row == 1
        and wb["ORDENES"]["A1"].value == "EMPRESA GANADORA"
        and wb["ORDENES"]["A2"].value is None
    )
    assert wb["DINAMICA"].max_row == 3 and wb["VALORES"].max_row == 1


# ================================================================================================ ALTERNATIVAS (2.º a 4.º)
COLUMNAS = [
    "COD_PRODUCTO",
    "DESCRIPCION",
    "CANT_COMPRAR",
    "VALOR",
    "COD_EMPRESA",
    "NOM_EMPRESA",
    "EXISTENCIAS",
    "PRESENTACION",
]
# puestos 2, 3 y 4 de A1 (BETA es el 1.º): GAMA $95 (empresa 3) · ALFA $100 (empresa 1) · DELTA $120 (empresa 4)
PUESTOS = {2: ("GAMA LTDA", "3", 95), 3: ("ALFA SAS", "1", 100), 4: ("DELTA SA", "4", 120)}
# la PRESENTACION que ofreció cada uno para A1 (última columna de VALORES): solo ALFA la escribió
PRESENTACION_A1 = {"3": None, "1": "X10", "4": None}


def _alternativas(c, calculado=False):
    r = c.get("/api/exportar/alternativas")
    assert r.status_code == 200, r.text
    return openpyxl.load_workbook(io.BytesIO(r.content), data_only=calculado)


def test_el_libro_de_alternativas_tiene_las_tres_hojas_de_la_oc_por_cada_puesto(cliente):
    r = cliente.get("/api/exportar/alternativas")
    assert f"ALTERNATIVAS_2_a_4_{date.today().isoformat()}.xlsx" in r.headers["content-disposition"]
    wb = _libro(r)
    assert wb.sheetnames == [
        f"{hoja} {p}.º" for p in (2, 3, 4) for hoja in ("VALORES", "DINAMICA", "ORDENES")
    ]  # 9 hojas, agrupadas por puesto
    assert wb.active.title == "VALORES 2.º"


def test_cada_puesto_trae_sus_VALORES_DINAMICA_y_ORDENES_como_la_primera_oc(cliente):
    wb = _alternativas(cliente, calculado=True)
    for puesto, (empresa, cod_empresa, valor) in PUESTOS.items():
        suf = f" {puesto}.º"
        # VALORES: las 8 columnas de OC.xlsm; solo A1 tiene tantas ofertas (C3 y 0041 tienen una sola)
        assert _tabla(wb["VALORES" + suf], 1, 8) == [
            COLUMNAS,
            ["A1", "ALFA PRODUCTO", 80, valor, cod_empresa, empresa, 20, PRESENTACION_A1[cod_empresa]],  # última: PRESENTACION
        ], puesto
        # DINAMICA: encabezado en la fila 3, una fila por proveedor y producto
        din = _tabla(wb["DINAMICA" + suf], 3, 5)
        assert din == [
            ["NOM_EMPRESA", "COD_PRODUCTO", "DESCRIPCION", "Suma de CANT_COMPRAR", "Mín. de VALOR"],
            [empresa, "A1", "ALFA PRODUCTO", 80, valor],
        ], puesto
        # ORDENES: el encabezado del puesto y la orden con sus valores calculados
        o = wb["ORDENES" + suf]
        assert o["A1"].value == f"EMPRESA ({puesto}.º PROVEEDOR)" and o["V1"].value == "VR. TOTAL"
        assert [c.value for c in o[2] if c.value is not None] == [
            empresa,
            1,
            "A1",
            "ALFA PRODUCTO",
            80,
            valor,
            80 * valor,
        ], puesto
        assert o.max_row == 3 and o["B3"].value == 0  # la fila en blanco después del proveedor (como OC.xlsm)


def test_las_hojas_de_alternativas_tienen_las_formulas_y_el_formato_del_original(cliente):
    wb = _alternativas(cliente)
    for puesto in PUESTOS:
        o, suf = wb[f"ORDENES {puesto}.º"], f" {puesto}.º"
        assert [o[c].value for c in ("A2", "B2", "C2", "G2", "Q2", "S2", "V2")] == [
            f"='DINAMICA{suf}'!A4",
            "=ROWS($A$2:A2)",
            f"='DINAMICA{suf}'!B4",
            f"='DINAMICA{suf}'!C4",
            f"='DINAMICA{suf}'!D4",
            f"='DINAMICA{suf}'!E4",
            "=S2*Q2",
        ]
        assert {str(m) for m in o.merged_cells.ranges if m.min_row == 2} == {
            "C2:F2",
            "G2:P2",
            "Q2:R2",
            "S2:U2",
            "V2:X2",
            "Y2:Z2",
        }
        assert o["Q2"].number_format == "General" and o["V2"].number_format == "General" and o["A1"].font.b
        assert wb[f"DINAMICA{suf}"]["D4"].number_format == "General"  # como OC.xlsm


def test_las_alternativas_usan_la_cantidad_editada_y_no_repiten_a_un_proveedor(cliente):
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 100})
    wb = _alternativas(cliente, calculado=True)
    assert [wb[f"ORDENES {p}.º"]["Q2"].value for p in (2, 3, 4)] == [100, 100, 100]  # la cantidad vigente
    assert [wb[f"VALORES {p}.º"]["C2"].value for p in (2, 3, 4)] == [100, 100, 100]
    # BETA aparece dos veces en el Excel para A1 ($90 y $85) pero cuenta como UN proveedor: el 2.º es GAMA, no la repetida de BETA
    assert [wb[f"ORDENES {p}.º"]["A2"].value for p in (2, 3, 4)] == ["GAMA LTDA", "ALFA SAS", "DELTA SA"]


def test_las_alternativas_con_ofertas_en_otros_productos(cliente):
    cliente.post("/api/ofertas", json={"cod_producto": "C3", "empresa_nueva": "SEGUNDA CIA", "valor": 60})
    cliente.post("/api/ofertas", json={"cod_producto": "C3", "empresa_nueva": "TERCERA CIA", "valor": 70})
    wb = _alternativas(cliente, calculado=True)
    filas2 = {f[1]: f[0] for f in _tabla(wb["DINAMICA 2.º"], 4, 5)}
    filas3 = {f[1]: f[0] for f in _tabla(wb["DINAMICA 3.º"], 4, 5)}
    assert (
        filas2["C3"] == "SEGUNDA CIA" and filas3["C3"] == "TERCERA CIA"
    )  # ahora C3 tiene 3 ofertas (ALFA $50 es la mejor)
    assert "C3" not in {f[1] for f in _tabla(wb["DINAMICA 4.º"], 4, 5)}
    # las tres hojas de un puesto cuentan lo mismo (ORDENES suma una fila en blanco por proveedor, como OC.xlsm)
    ordenes = _tabla(wb["ORDENES 2.º"], 2, 8)
    assert len(_tabla(wb["VALORES 2.º"], 2, 8)) == len(_tabla(wb["DINAMICA 2.º"], 4, 5)) == 2
    assert len([f for f in ordenes if f[0] != 0]) == 2 and len(ordenes) == 4


def test_las_alternativas_sin_ofertas_suficientes_dejan_cada_hoja_con_solo_el_encabezado(cliente):
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 0})
    wb = _alternativas(cliente)  # sin A1, nadie tiene 2 o más ofertas
    assert len(wb.sheetnames) == 9
    for p in (2, 3, 4):
        assert wb[f"VALORES {p}.º"]["A1"].value == "COD_PRODUCTO" and wb[f"VALORES {p}.º"]["A2"].value is None
        assert wb[f"DINAMICA {p}.º"]["A3"].value is None or wb[f"DINAMICA {p}.º"]["A4"].value is None
        assert wb[f"ORDENES {p}.º"]["A1"].value and wb[f"ORDENES {p}.º"]["A2"].value is None


# ================================================================================================ PERMISOS
def test_quien_puede_descargar_la_oc_y_las_alternativas(cliente, como, anonimo):
    for ruta in ("/api/exportar/oc", "/api/exportar/alternativas"):
        assert cliente.get(ruta).status_code == 200 and como("prime").get(ruta).status_code == 200, ruta
        assert (
            como("consulta").get(ruta).status_code == 403
            and como("externo", cod_empresa="1").get(ruta).status_code == 403
        ), ruta
        assert anonimo.get(ruta).status_code == 401, ruta


# ================================================================================================ ESTRUCTURA DEL XML (lo que Excel exige)
def _revisar_estructura(contenido: bytes) -> list[str]:
    """Las hojas de datos se escriben como XML armado a mano (por velocidad): se comprueban las reglas que Excel exige y que LibreOffice perdona.
    Devuelve la lista de problemas (vacía si está bien)."""
    import re
    import zipfile

    z = zipfile.ZipFile(io.BytesIO(contenido))
    problemas = []
    estilos = int(re.search(r'<cellXfs count="(\d+)"', z.read("xl/styles.xml").decode()).group(1))
    for parte in sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)):
        xml = z.read(parte).decode("utf-8")
        filas = [int(x) for x in re.findall(r'<row r="(\d+)"', xml)]
        if len(filas) != len(set(filas)):
            problemas.append(f"{parte}: hay filas duplicadas")
        if filas != sorted(filas):
            problemas.append(f"{parte}: las filas no van en orden")
        for fila in re.findall(r"<row [^>]*>(.*?)</row>", xml, re.S):
            cols = [
                sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(c)))
                for c in re.findall(r'<c r="([A-Z]+)\d+"', fila)
            ]
            if cols != sorted(set(cols)):
                problemas.append(f"{parte}: celdas repetidas o fuera de orden en una fila")
                break
        if [s for s in map(int, re.findall(r' s="(\d+)"', xml)) if s >= estilos]:
            problemas.append(f"{parte}: usa un estilo que no existe")
        uniones = re.findall(r'<mergeCell ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"', xml)
        cuenta = re.search(r'<mergeCells count="(\d+)"', xml)
        if (len(uniones) != int(cuenta.group(1))) if cuenta else bool(uniones):
            problemas.append(f"{parte}: el conteo de celdas combinadas no coincide")
        vistas = set()
        for c0, r0, c1, r1 in uniones:
            for r in range(int(r0), int(r1) + 1):
                for c in range(_n(c0), _n(c1) + 1):
                    if (r, c) in vistas:
                        problemas.append(f"{parte}: celdas combinadas que se pisan")
                        break
                    vistas.add((r, c))
        ultima = re.search(r'<dimension ref="[A-Z]+\d+:[A-Z]+(\d+)"', xml)
        if ultima and filas and int(ultima.group(1)) < max(filas):
            problemas.append(f"{parte}: la dimensión no llega a la última fila")
    return problemas


def _n(columna: str) -> int:
    return sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(columna)))


def test_las_hojas_escritas_a_mano_cumplen_lo_que_excel_exige(cliente):
    for ruta in ("/api/exportar/oc", "/api/exportar/alternativas"):
        assert _revisar_estructura(cliente.get(ruta).content) == [], ruta
    for cod in ("A1", "C3", "D4", "0041"):  # y también con las hojas vacías
        cliente.put(f"/api/productos/{cod}/cantidad", json={"cantidad": 0})
    for ruta in ("/api/exportar/oc", "/api/exportar/alternativas"):
        assert _revisar_estructura(cliente.get(ruta).content) == [], ruta + " (vacío)"


def test_un_libro_grande_se_arma_en_pocos_segundos():
    """Con miles de filas la OC tardaba casi un minuto (openpyxl combina celdas en tiempo cuadrático); ahora debe tardar una fracción de segundo."""
    import time

    columnas = [
        "COD_PRODUCTO",
        "DESCRIPCION",
        "CANT_COMPRAR",
        "VALOR",
        "COD_EMPRESA",
        "NOM_EMPRESA",
        "EXISTENCIAS",
        "PRESENTACION",
    ]
    filas = [
        [
            f"P{i:05d}",
            f"PRODUCTO NUMERO {i} CON DESCRIPCION LARGA & <ESPECIAL>",
            10 + i % 7,
            1000.5 + i,
            str(i % 90),
            f"PROVEEDOR {i % 90}",
            3,
            20,
        ]
        for i in range(5000)
    ]
    t0 = time.perf_counter()
    contenido = libros_excel.oc_xlsx(filas, columnas)
    assert time.perf_counter() - t0 < 6, "la OC de 5.000 filas tardó demasiado"
    assert _revisar_estructura(contenido) == []
    o = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True)["ORDENES"]
    assert o.max_row == 5001 + 90 and o["G2"].value.endswith("& <ESPECIAL>")  # 5.000 filas + 1 en blanco por cada uno de los 90 proveedores
    assert abs(sum(o.cell(r, 22).value for r in range(2, o.max_row + 1)) - sum(f[2] * f[3] for f in filas)) < 1e-3
