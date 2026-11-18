"""LOS TABLEROS DE CONTROL: empresas con menores valores · precios más baratos · productos que más consumen.

Datos de conftest.py (todo se puede calcular a mano):
  A1 (comprar 80): BETA $85 · GAMA $95 · ALFA $100 · DELTA $120 · «Proveedor 5» $130      → mejor $85, promedio $106
  C3 (comprar 5):  solo ALFA $50      0041 (comprar 6): solo ALFA $7      D4 (comprar 5): nadie lo ofrece
Solo cuentan los productos que hay que comprar. El sobreprecio de una empresa = cuánto más cara es, en promedio, que la mejor oferta de
los productos en los que compite con otras (0 % = siempre la más barata).
"""

import sqlite3

from app import database
from app.services import control, tablas


def _api(c, **params):
    r = c.get("/api/control", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _por_cod(filas):
    return {f["cod"]: f for f in filas}


# ================================================================================================ empresas con menores valores
def test_las_empresas_salen_de_la_que_cobra_menos_a_la_que_cobra_mas(cliente):
    j = _api(cliente)
    nombres = [e["nombre"] for e in j["empresas"]]
    assert nombres[:4] == ["BETA SAS", "GAMA LTDA", "ALFA SAS", "DELTA SA"] and nombres[4].startswith(
        "Proveedor 5"
    )  # el 5 no está en EMPRESA.xlsx
    assert [e["sobreprecio_pct"] for e in j["empresas"]] == [
        0.0,
        11.8,
        17.6,
        41.2,
        52.9,
    ]  # (95/85−1), (100/85−1), (120/85−1), (130/85−1)
    assert j["total_empresas"] == 5


def test_cada_empresa_dice_en_cuantos_productos_cotiza_y_en_cuantos_es_la_mas_barata(cliente):
    e = _por_cod(_api(cliente)["empresas"])
    assert (e["2"]["cotiza"], e["2"]["gana"], e["2"]["pct_gana"]) == (1, 1, 100.0)  # BETA: solo A1, y ahí es la mejor
    assert (e["1"]["cotiza"], e["1"]["gana"]) == (3, 2)  # ALFA: A1 (no gana), C3 y 0041 (únicas, ganan)
    assert e["1"]["sobreprecio_pct"] == 17.6  # solo A1 cuenta: C3 y 0041 no tienen con quién compararse
    assert (e["3"]["gana"], e["3"]["pct_gana"]) == (0, 0.0)


def test_el_valor_cotizado_es_lo_que_costaria_comprar_todo_lo_que_cotiza_a_sus_precios(cliente):
    e = _por_cod(_api(cliente)["empresas"])
    assert (e["3"]["valor_cotizado"], e["3"]["valor_minimo"], e["3"]["sobrecosto"]) == (
        80 * 95,
        80 * 85,
        800,
    )  # GAMA: A1
    assert (e["1"]["valor_cotizado"], e["1"]["valor_minimo"], e["1"]["sobrecosto"]) == (
        8000 + 250 + 42,
        6800 + 250 + 42,
        1200,
    )  # ALFA: A1 + C3 + 0041
    assert e["2"]["sobrecosto"] == 0


def test_lo_comprado_es_lo_que_de_verdad_se_le_compra_a_cada_empresa(cliente):
    e = _por_cod(_api(cliente)["empresas"])
    assert e["2"]["comprado"] == 6800  # BETA gana A1
    assert e["1"]["comprado"] == 250 + 42  # ALFA gana C3 y 0041
    assert e["3"]["comprado"] == 0 and e["4"]["comprado"] == 0


def test_el_minimo_de_productos_deja_fuera_a_las_empresas_que_cotizan_poco(cliente):
    j = _api(cliente, min_productos=2)
    assert [e["nombre"] for e in j["empresas"]] == ["ALFA SAS"] and j["total_empresas"] == 1  # solo ALFA cotiza 2 o más


def test_el_top_limita_los_renglones_pero_no_el_total(cliente):
    j = _api(cliente, top=3)
    assert len(j["empresas"]) == 3 and j["total_empresas"] == 5


# ================================================================================================ precios más baratos
def test_los_precios_mas_baratos_comparan_la_mejor_oferta_con_el_promedio(cliente):
    j = _api(cliente)
    assert j["total_precios"] == 1  # solo A1 tiene 2 o más ofertas con las que comparar
    a1 = j["precios"][0]
    assert (a1["cod"], a1["empresa"], a1["mejor_precio"], a1["precio_promedio"], a1["n_ofertas"]) == (
        "A1",
        "BETA SAS",
        85,
        106,
        5,
    )
    assert (a1["ahorro_pct"], a1["ahorro_valor"]) == (19.8, 21 * 80)  # (106−85)/106 · 100 y (106−85) × 80 unidades


def test_los_precios_se_pueden_ordenar_por_porcentaje_o_por_valor(cliente):
    c = cliente
    # Un segundo producto con 2 ofertas: $10 y $12 (promedio $11 → 9,1 % de ahorro, pero solo $5 × 5 = $25 en total)
    assert c.post("/api/ofertas", json={"cod_producto": "D4", "cod_empresa": "1", "valor": 10}).status_code == 201
    assert c.post("/api/ofertas", json={"cod_producto": "D4", "cod_empresa": "2", "valor": 12}).status_code == 201
    pct = [f["cod"] for f in _api(c, precios="porcentaje")["precios"]]
    val = [f["cod"] for f in _api(c, precios="valor")["precios"]]
    assert pct == ["A1", "D4"] and val == ["A1", "D4"]  # A1 gana en las dos medidas
    d4 = _por_cod(_api(c)["precios"])["D4"]
    assert (d4["ahorro_pct"], d4["ahorro_valor"]) == (9.1, 5.0)


# ================================================================================================ productos que más consumen
def test_los_productos_que_mas_consumen_salen_por_cantidad_a_comprar(cliente):
    j = _api(cliente)
    assert [f["cod"] for f in j["consumo"]] == ["A1", "0041", "D4", "C3"]  # 80, 6, 5 y 5 (empate: por descripción)
    a1 = j["consumo"][0]
    assert (a1["comprar"], a1["existencias"], a1["stock_max"], a1["reposicion_pct"], a1["total"], a1["empresa"]) == (
        80,
        20,
        100,
        80.0,
        6800,
        "BETA SAS",
    )


def test_el_consumo_se_puede_ordenar_por_inversion_o_por_stock_maximo(cliente):
    assert [f["cod"] for f in _api(cliente, consumo="inversion")["consumo"]] == [
        "A1",
        "C3",
        "0041",
        "D4",
    ]  # $6.800, $250, $42 y sin oferta
    assert [f["cod"] for f in _api(cliente, consumo="stock_max")["consumo"]] == [
        "A1",
        "0041",
        "D4",
        "C3",
    ]  # 100, 10, 7 y 5
    assert _por_cod(_api(cliente)["consumo"])["D4"]["empresa"] is None  # sin oferta: no hay proveedor


# ================================================================================================ números de arriba y filtro cruzado
def test_los_numeros_de_arriba_coinciden_con_el_tablero(cliente):
    k = _api(cliente)["kpis"]
    assert (k["productos"], k["con_oferta"], k["inversion"], k["ahorro"]) == (4, 3, 6800 + 250 + 42, 800)
    assert k["empresa_mas_barata"] == {"nombre": "BETA SAS", "sobreprecio_pct": 0.0, "gana": 1, "cotiza": 1}
    assert k["producto_mayor_consumo"]["cod"] == "A1" and k["mejor_ahorro"]["cod"] == "A1"
    r = cliente.get("/api/resumen").json()
    assert (
        k["inversion"] == r["inversion_total"] and k["ahorro"] == r["ahorro_total"]
    )  # el mismo cálculo que el tablero


def test_elegir_una_empresa_limita_las_vistas_a_los_productos_que_ella_cotiza(cliente):
    j = _api(cliente, empresa="1")  # ALFA: cotiza A1, C3 y 0041 (D4 nadie)
    assert j["filtros"]["empresa_nombre"] == "ALFA SAS"
    assert sorted(f["cod"] for f in j["consumo"]) == ["0041", "A1", "C3"] and j["kpis"]["productos"] == 3
    assert [e["nombre"] for e in j["empresas"]][
        0
    ] == "BETA SAS"  # el ranking de empresas no se achica: es el que se usa para elegir
    assert len(_api(cliente, empresa="3")["consumo"]) == 1  # GAMA solo cotiza A1


def test_una_empresa_que_no_existe_responde_404(cliente):
    assert cliente.get("/api/control", params={"empresa": "999"}).status_code == 404


def test_los_parametros_invalidos_se_rechazan(cliente):
    for p in ({"top": 2}, {"top": 31}, {"min_productos": 0}, {"precios": "otro"}, {"consumo": "otro"}):
        assert cliente.get("/api/control", params=p).status_code == 422, p


def test_sin_datos_los_tableros_salen_vacios_sin_fallar():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(database.ESQUEMA)
    con.executescript(tablas.esquema_sql())
    j = control.construir_control(con)
    assert j["empresas"] == [] and j["precios"] == [] and j["consumo"] == []
    assert (
        j["kpis"]["productos"] == 0
        and j["kpis"]["empresa_mas_barata"] is None
        and j["kpis"]["producto_mayor_consumo"] is None
    )


# ================================================================================================ permisos
def test_los_perfiles_internos_ven_los_tableros_y_el_proveedor_externo_no(como):
    for rol in ("admin", "prime", "consulta"):
        assert como(rol).get("/api/control").status_code == 200, rol
    assert como("externo").get("/api/control").status_code == 403
