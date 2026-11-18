"""LA CANTIDAD DISPONIBLE: avisar y repartir la compra cuando el mejor proveedor no tiene unidades para todo.

Cada oferta puede decir cuántas unidades PUEDE entregar el proveedor (`disponible`; vacío = no lo dijo, se supone que le alcanza). Si el mejor no tiene
para todo lo que hay que comprar, se le compra lo que tenga y el resto al siguiente más barato (ranking.repartir). Sin ningún dato de cantidad, todo
sale exactamente como antes (eso lo comprueban las demás pruebas).

Datos de conftest.py: A1 (comprar 80): BETA $85 · GAMA $95 · ALFA $100 · DELTA $120. C3 (5, solo ALFA $50) · 0041 (6) · D4 (5, nadie lo ofrece).
Empresas: 1 ALFA SAS · 2 BETA SAS · 3 GAMA LTDA · 4 DELTA SA.
"""

from app import database
from app.services import exportador
from app.services import ranking as rk
from tests.conftest import excel_bytes
from tests.test_cantidades_y_fichas import _filas_excel, _sql
from tests.test_cargas import OCTETOS
from tests.test_ofertas_proveedor import _ficha_llena, _gama, _subir


# ================================================================================================ la regla pura
def _o(i, empresa, valor, disponible=None):
    return {"id": i, "cod_empresa": str(i), "empresa": empresa, "valor": valor, "disponible": disponible}


A, B, C = _o(1, "A", 10, 600), _o(2, "B", 12), _o(3, "C", 15, 50)


def _quien(r):
    return [(ln["empresa"], ln["cantidad"], ln["subtotal"]) for ln in r["lineas"]]


def test_si_el_mejor_no_alcanza_se_le_compra_lo_que_tenga_y_el_resto_al_siguiente():
    r = rk.repartir(1000, [A, B, C])
    assert _quien(r) == [("A", 600, 6000), ("B", 400, 4800)]  # B no dijo cuánto tiene: cubre el resto
    assert (r["cubierta"], r["faltante"], r["repartida"], r["excede"]) == (1000, 0, True, 0)


def test_si_todos_juntos_no_alcanzan_se_dice_cuanto_falta():
    r = rk.repartir(1000, [A, C])
    assert _quien(r) == [("A", 600, 6000), ("C", 50, 750)]
    assert (r["cubierta"], r["faltante"]) == (650, 350)


def test_si_le_alcanza_al_mejor_no_hay_reparto_y_sin_dato_de_cantidad_todo_sale_como_antes():
    assert _quien(rk.repartir(100, [A, B, C])) == [("A", 100, 1000)]
    sin_dato = [_o(1, "A", 10), _o(2, "B", 12)]
    r = rk.repartir(1000, sin_dato)
    assert _quien(r) == [("A", 1000, 10000)] and not r["repartida"] and r["faltante"] == 0


def test_una_oferta_con_cero_unidades_se_salta_y_la_cantidad_fraccionaria_se_redondea_hacia_abajo():
    r = rk.repartir(10, [_o(1, "A", 10, 0), _o(2, "B", 12, 6.9), _o(3, "C", 15)])
    assert _quien(r) == [("B", 6, 72), ("C", 4, 60)]  # A no tiene; B tiene 6.9 → 6 unidades enteras


def test_si_el_usuario_elige_a_mano_no_se_reparte_solo_se_avisa_cuanto_excede():
    r = rk.repartir(1000, [A, B, C], elegida=C)
    assert _quien(r) == [("C", 1000, 15000)] and r["repartida"] is False and r["excede"] == 950  # C dijo tener 50
    assert rk.repartir(1000, [A, B, C], elegida=B)["excede"] == 0  # B no dijo cuánto tiene


def test_sin_ofertas_o_sin_nada_que_comprar_no_hay_reparto():
    assert rk.repartir(5, [])["lineas"] == [] and rk.repartir(0, [A])["lineas"] == []


def test_a_igual_precio_el_ranking_prefiere_la_oferta_que_dice_cuantas_unidades_tiene():
    sin = {
        "id": 1,
        "cod_empresa": "2",
        "empresa": "B",
        "valor": 85,
        "disponible": None,
    }  # la del Excel base: no trae cantidad
    con = {"id": 9, "cod_empresa": "2", "empresa": "B", "valor": 85, "disponible": 30}  # la subida por el proveedor: sí
    assert rk.construir_ranking([sin, con])[0]["disponible"] == 30  # (antes ganaba la de menor id y el tope se perdía)
    assert (
        rk.construir_ranking([sin, {**con, "valor": 90}])[0]["disponible"] is None
    )  # pero un precio MÁS BARATO siempre gana


# ================================================================================================ el tablero
def _cargar(c, filas, cod_empresa=None, aplicar=True):
    """«Cargar datos → Cotizaciones» con un Excel simple: cada fila trae COD_EMPRESA, COD_PRODUCTO, VALOR y (opcional) DISPONIBLE."""
    params = {"nombre": "cotizacion.xlsx", "aplicar": "true" if aplicar else "false"}
    if cod_empresa:
        params["cod_empresa"] = cod_empresa
    return c.post("/api/cargas/cotizaciones", params=params, content=excel_bytes(filas), headers=OCTETOS)


def _fila(emp, prod, valor, disponible=None):
    return {"COD_EMPRESA": emp, "COD_PRODUCTO": prod, "VALOR": valor, "DISPONIBLE": disponible}


def _item(c, cod):
    return next(
        i for i in c.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"] if i["cod"] == cod
    )


def _lineas(item):
    return [(ln["empresa"], ln["cantidad"], ln["valor"], ln["subtotal"]) for ln in item["reparto"]]


def _a1_con_dos_topes(c):
    """BETA $80 con 30 unidades y GAMA $94 con 20: A1 necesita 80 → BETA 30 + GAMA 20 + ALFA (sin tope) 30."""
    r = _cargar(c, [_fila("2", "A1", "80", "30"), _fila("3", "A1", "94", "20")])
    assert r.status_code == 200 and r.json()["total_errores"] == 0, r.text


def test_sin_ninguna_cantidad_el_tablero_sale_como_siempre_con_una_sola_linea(cliente):
    a1 = _item(cliente, "A1")
    assert (
        _lineas(a1) == [("BETA SAS", 80, 85.0, 6800.0)]
        and a1["total"] == 6800
        and a1["repartido"] is False
        and a1["faltante"] == 0
    )
    assert a1["avisa_cantidad"] is False


def test_el_tablero_reparte_la_compra_entre_los_proveedores_que_alcanzan(cliente):
    _a1_con_dos_topes(cliente)
    a1 = _item(cliente, "A1")
    assert _lineas(a1) == [
        ("BETA SAS", 30, 80.0, 2400.0),
        ("GAMA LTDA", 20, 94.0, 1880.0),
        ("ALFA SAS", 30, 100.0, 3000.0),
    ]
    assert a1["repartido"] is True and a1["faltante"] == 0 and a1["avisa_cantidad"] is True
    assert (
        a1["total"] == 7280 and a1["elegida"]["empresa"] == "BETA SAS" and a1["mejor"]["empresa"] == "BETA SAS"
    )  # la principal es la más barata con unidades
    assert a1["ahorro"] == 240  # 2.ª ($94) × 80 − 7.280: lo que se ahorra frente a comprarlo todo a la 2.ª


def test_los_indicadores_y_donde_comprar_suman_cada_linea_a_su_proveedor(cliente):
    _a1_con_dos_topes(cliente)
    r = cliente.get("/api/resumen").json()
    assert (
        r["inversion_total"] == 7280 + 250 + 42
    )  # A1 repartido + C3 (5 × $50) + 0041 (6 × $7); antes eran 6.800 + 250 + 42
    por = {d["nombre"]: (d["productos"], d["total"]) for d in r["por_proveedor"]}
    assert por["BETA SAS"] == (1, 2400) and por["GAMA LTDA"] == (1, 1880) and por["ALFA SAS"] == (3, 3000 + 250 + 42)
    assert (
        "reparto" not in r["conteos"]
    )  # ya no hay botón de filtro «Reparto»: el aviso sale en la fila de cada producto
    assert cliente.get("/api/productos", params={"filtro": "reparto"}).status_code == 422


def test_si_ningun_proveedor_alcanza_se_compra_lo_que_hay_y_se_dice_cuanto_falta(cliente):
    _cargar(cliente, [_fila("1", "C3", "49", "3")])  # C3 necesita 5 y solo lo ofrece ALFA, que tiene 3
    c3 = _item(cliente, "C3")
    assert (
        _lineas(c3) == [("ALFA SAS", 3, 49.0, 147.0)]
        and c3["faltante"] == 2
        and c3["repartido"] is False
        and c3["avisa_cantidad"] is True
    )
    assert c3["total"] == 147  # solo lo que se puede comprar


def test_si_el_unico_proveedor_no_tiene_unidades_no_hay_total_y_avisa(cliente):
    _cargar(cliente, [_fila("1", "C3", "49", "0")])  # «0» = no tiene nada
    c3 = _item(cliente, "C3")
    assert (
        c3["reparto"] == []
        and c3["sin_unidades"] is True
        and c3["total"] is None
        and c3["faltante"] == 5
        and c3["avisa_cantidad"] is True
    )


def test_si_el_usuario_elige_a_mano_se_le_compra_todo_a_ese_y_solo_se_avisa(cliente):
    _a1_con_dos_topes(cliente)
    # GAMA dijo tener 20 y el usuario la elige para los 80 (si eligiera a BETA, que ya es la mejor, el sistema quita la elección)
    assert cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "3"}).status_code == 200
    a1 = _item(cliente, "A1")
    assert (
        _lineas(a1) == [("GAMA LTDA", 80, 94.0, 7520.0)] and a1["repartido"] is False and a1["elegida_a_mano"] is True
    )
    assert a1["excede_disponible"] == 60 and a1["avisa_cantidad"] is True and a1["total"] == 7520
    assert (
        a1["elegida"]["empresa"] == "GAMA LTDA" and a1["mejor"]["empresa"] == "BETA SAS"
    )  # la elegida es otra que la más barata


def test_el_modal_de_ofertas_trae_el_reparto_y_cuales_alcanzan(cliente):
    _a1_con_dos_topes(cliente)
    j = cliente.get("/api/productos/A1/ofertas", params={"limite": 10}).json()
    assert [(ln["empresa"], ln["cantidad"]) for ln in j["reparto"]] == [
        ("BETA SAS", 30),
        ("GAMA LTDA", 20),
        ("ALFA SAS", 30),
    ]
    assert j["repartido"] is True and j["faltante"] == 0
    por = {o["empresa"]: (o["disponible"], o["alcanza"], o["faltan"]) for o in j["ofertas"]}
    assert (
        por["BETA SAS"] == (30, False, 50)
        and por["GAMA LTDA"] == (20, False, 60)
        and por["ALFA SAS"] == (None, True, 0)
    )
    assert next(o for o in j["ofertas"] if o["empresa"] == "BETA SAS")["es_elegida"] is True


# ================================================================================================ la OC y las alternativas
def test_la_oc_trae_una_fila_por_proveedor_del_reparto(cliente):
    _a1_con_dos_topes(cliente)
    filas = _filas_excel(cliente, "/api/exportar/oc")
    a1 = sorted((f[2], f[3], f[4]) for f in filas[1:] if f[0] == "A1")  # (CANT_COMPRAR, VALOR, COD_EMPRESA)
    assert a1 == [(20, 94.0, "3"), (30, 80.0, "2"), (30, 100.0, "1")]
    assert sum(f[2] for f in filas[1:] if f[0] == "A1") == 80  # entre todos suman lo que hay que comprar


def test_las_alternativas_no_repiten_a_los_proveedores_que_ya_van_en_la_oc(cliente):
    _a1_con_dos_topes(cliente)
    con = database.conectar()
    try:
        filas = exportador.filas_por_puesto(con)
    finally:
        con.close()
    assert [f[5] for f in filas[2] if f[0] == "A1"] == [
        "DELTA SA"
    ]  # BETA, GAMA y ALFA ya están en la OC: la 2.ª alternativa es DELTA


def test_el_excel_de_consulta_muestra_el_reparto_en_una_sola_celda(cliente):
    _a1_con_dos_topes(cliente)
    fila = next(f for f in _filas_excel(cliente, "/api/exportar/productos-a-comprar")[1:] if f[0] == "A1")
    assert fila[5] == "BETA SAS (30) + GAMA LTDA (20) + ALFA SAS (30)" and fila[6] is None and fila[7] == 7280


def test_la_ficha_de_la_empresa_cuenta_solo_lo_que_se_le_compra_a_ella(cliente):
    _a1_con_dos_topes(cliente)
    beta = cliente.get("/api/empresas/2/ficha").json()
    a1 = next(o for o in beta["ofertas"] if o["cod_producto"] == "A1")
    assert (
        a1["es_elegida"] is True and a1["cantidad"] == 30 and a1["total"] == 2400 and beta["inversion"] == 2400
    )  # no los 6.800 de todo el producto


# ================================================================================================ la cantidad llega por todas las vías
def test_cargar_cotizaciones_guarda_la_cantidad_y_la_compara_para_decir_si_cambia(cliente):
    assert _cargar(cliente, [_fila("2", "A1", "80", "30")]).json()["nuevos"] == 1
    igual = _cargar(cliente, [_fila("2", "A1", "80", "30")]).json()
    assert igual["sin_cambios"] == 1 and igual["actualizados"] == 0
    otra_cantidad = _cargar(cliente, [_fila("2", "A1", "80", "45")]).json()  # solo cambia la cantidad
    assert (
        otra_cantidad["actualizados"] == 1
        and _sql("SELECT disponible FROM ofertas WHERE origen = 'subido'")[0][0] == 45
    )


def test_una_cantidad_que_no_es_un_numero_o_es_negativa_rechaza_esa_fila(cliente):
    r = _cargar(
        cliente, [_fila("2", "A1", "80", "mucho"), _fila("3", "A1", "94", "-5"), _fila("1", "C3", "49", "3")]
    ).json()
    assert r["total_errores"] == 2 and r["nuevos"] == 1  # la fila buena sí se carga
    assert all("cantidad disponible" in e["motivo"] for e in r["errores"])


def test_una_oferta_manual_puede_traer_la_cantidad_y_se_reparte(cliente):
    assert (
        cliente.post(
            "/api/ofertas", json={"cod_producto": "D4", "cod_empresa": "1", "valor": 10, "disponible": 3}
        ).status_code
        == 201
    )
    assert (
        cliente.post("/api/ofertas", json={"cod_producto": "D4", "cod_empresa": "2", "valor": 12}).status_code == 201
    )  # sin cantidad: le alcanza
    d4 = _item(cliente, "D4")
    assert (
        _lineas(d4) == [("ALFA SAS", 3, 10.0, 30.0), ("BETA SAS", 2, 12.0, 24.0)]
        and d4["total"] == 54
        and d4["repartido"] is True
    )
    assert (
        cliente.post(
            "/api/ofertas", json={"cod_producto": "D4", "cod_empresa": "1", "valor": 10, "disponible": 4}
        ).json()["actualizada"]
        is True
    )
    assert _lineas(_item(cliente, "D4"))[0][1] == 4  # al actualizar la manual, cambia la cantidad


def test_una_oferta_manual_con_cantidad_negativa_se_rechaza(cliente):
    assert (
        cliente.post(
            "/api/ofertas", json={"cod_producto": "D4", "cod_empresa": "1", "valor": 10, "disponible": -1}
        ).status_code
        == 422
    )


def test_la_ficha_del_proveedor_trae_la_cantidad_y_el_administrador_la_ve_frente_a_lo_que_se_necesita(cliente, como):
    gama = _gama(como)
    r = _subir(
        gama, _ficha_llena(gama, {"A1": (70, 13, "X10", 25), "C3": (40, 0, "X1")})
    )  # A1 necesita 80 y GAMA solo tiene 25; C3 sin cantidad
    assert r.status_code == 201 and r.json()["total_errores"] == 0, r.text
    filas = {f["cod"]: f for f in cliente.get(f"/api/pendientes/{r.json()['lote']}").json()["filas"]}
    assert (filas["A1"]["disponible"], filas["A1"]["alcanza"], filas["A1"]["comprar"]) == (25, False, 80)
    assert (filas["C3"]["disponible"], filas["C3"]["alcanza"]) == (None, True)


def test_aprobar_la_ficha_deja_la_cantidad_en_la_oferta_y_el_tablero_reparte(cliente, como):
    gama = _gama(como)
    lote = _subir(gama, _ficha_llena(gama, {"A1": (70, 13, "X10", 25)})).json()["lote"]
    assert cliente.post(f"/api/pendientes/{lote}/aprobar").status_code == 200
    assert _sql("SELECT disponible FROM ofertas WHERE cod_empresa = '3' AND origen = 'subido'")[0][0] == 25
    assert _lineas(_item(cliente, "A1"))[:2] == [
        ("GAMA LTDA", 25, 70.0, 1750.0),
        ("BETA SAS", 55, 85.0, 4675.0),
    ]  # GAMA ($70) tiene 25; el resto, a BETA
    assert (
        cliente.post(f"/api/pendientes/{lote}/restaurar").status_code == 200
    )  # restaurar: la oferta (con su cantidad) desaparece
    assert _lineas(_item(cliente, "A1")) == [("BETA SAS", 80, 85.0, 6800.0)]


def test_si_el_proveedor_vuelve_a_subir_sin_cantidad_la_anterior_se_borra_y_restaurar_la_devuelve(cliente, como):
    gama = _gama(como)
    primera = _subir(gama, _ficha_llena(gama, {"A1": (70, 13, "X10", 25)})).json()["lote"]
    cliente.post(f"/api/pendientes/{primera}/aprobar")
    segunda = _subir(gama, _ficha_llena(gama, {"A1": (70, 13, "X10")})).json()["lote"]  # el mismo precio, SIN cantidad
    assert cliente.post(f"/api/pendientes/{segunda}/aprobar").status_code == 200
    assert (
        _sql("SELECT disponible FROM ofertas WHERE cod_empresa = '3' AND origen = 'subido'")[0][0] is None
    )  # ya no hay tope viejo
    assert _lineas(_item(cliente, "A1")) == [("GAMA LTDA", 80, 70.0, 5600.0)]
    assert (
        cliente.post(f"/api/pendientes/{segunda}/restaurar").status_code == 200
    )  # restaurar devuelve lo que había: el tope de 25
    assert _sql("SELECT disponible FROM ofertas WHERE cod_empresa = '3' AND origen = 'subido'")[0][0] == 25


def test_una_cantidad_invalida_en_la_ficha_rechaza_solo_esa_fila(cliente, como):
    gama = _gama(como)
    r = _subir(
        gama, _ficha_llena(gama, {"A1": (70, 13, "X10", "mucha"), "C3": (40, 0, "X1", -2), "0041": (6, 0, "X1", 100)})
    ).json()
    assert r["total_errores"] == 2 and r["guardadas"] == 1
    assert all("cantidad disponible" in e["motivo"] for e in r["errores"])


def test_una_base_de_una_version_anterior_recibe_la_columna_de_cantidad_al_arrancar(cliente):
    con = database.conectar()
    try:
        con.execute("ALTER TABLE ofertas DROP COLUMN disponible")
        con.execute("ALTER TABLE ofertas_lote DROP COLUMN disponible")
        con.execute("ALTER TABLE ofertas_lote DROP COLUMN antes_disponible")
        con.commit()
    finally:
        con.close()
    database.iniciar_db()
    con = database.conectar()
    try:
        assert "disponible" in {f["name"] for f in con.execute("PRAGMA table_info(ofertas)")}
        assert {"disponible", "antes_disponible"} <= {f["name"] for f in con.execute("PRAGMA table_info(ofertas_lote)")}
    finally:
        con.close()
