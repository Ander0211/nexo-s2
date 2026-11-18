"""Reglas de negocio puras: cantidad, ranking, normalización."""

from app.services import normalizacion as nz
from app.services import ranking as rk


def test_cantidad_a_comprar():
    """La cantidad es StockMax − Existencias: nunca negativa, sin datos = 0 y siempre en unidades enteras."""
    assert rk.cantidad_a_comprar(100, 20) == 80
    assert rk.cantidad_a_comprar(10, 10) == 0  # justo en el máximo
    assert rk.cantidad_a_comprar(10, 25) == 0  # nunca negativa
    assert rk.cantidad_a_comprar(5, None) == 5  # sin existencias = 0
    assert rk.cantidad_a_comprar(None, 3) == 0  # sin stock definido
    assert rk.cantidad_a_comprar(1000, 331.1) == 669  # siempre unidades enteras (hacia arriba)


def test_nivel_stock():
    """El color del medidor: crítico (en/bajo el mínimo), bajo (bajo la mitad del rango), ok, o sin definir."""
    assert rk.nivel_stock(0, 36, 108) == "critico"
    assert rk.nivel_stock(36, 36, 108) == "critico"
    assert rk.nivel_stock(50, 36, 108) == "bajo"
    assert rk.nivel_stock(100, 36, 108) == "ok"
    assert rk.nivel_stock(5, None, None) == "sin_definir"


def _o(id, emp, valor, origen="excel"):
    """Crea una oferta de prueba con los campos mínimos que necesita construir_ranking."""
    return {"id": id, "cod_empresa": emp, "empresa": f"E{emp}", "valor": valor, "presentacion": None, "origen": origen}


def test_ranking_ordena_y_calcula_diferencias():
    """Ordena de la más barata a la más cara y calcula cuánto más cara es cada una que la mejor (pesos y %)."""
    r = rk.construir_ranking([_o(1, "1", 100), _o(2, "2", 80), _o(3, "3", 120)])
    assert [o["cod_empresa"] for o in r] == ["2", "1", "3"]
    assert [o["puesto"] for o in r] == [1, 2, 3]
    assert r[0]["dif_pct"] == 0 and r[1]["dif_abs"] == 20 and r[1]["dif_pct"] == 25.0


def test_ranking_un_proveedor_cuenta_una_vez_con_su_menor_precio():
    """Si un proveedor tiene dos ofertas (una del Excel y otra manual), solo cuenta la más barata."""
    r = rk.construir_ranking([_o(1, "1", 100), _o(2, "1", 70, "manual"), _o(3, "2", 90)])
    assert [(o["cod_empresa"], o["valor"]) for o in r] == [("1", 70), ("2", 90)]
    assert r[0]["origen"] == "manual"


def test_ranking_empate_gana_menor_codigo_y_se_marca():
    """En empate de precio gana el proveedor de menor código (2 antes que 10) y ambos quedan marcados como empate."""
    r = rk.construir_ranking([_o(1, "10", 50), _o(2, "2", 50), _o(3, "3", 60)])
    assert [o["cod_empresa"] for o in r] == ["2", "10", "3"]
    assert r[0]["empate"] and r[1]["empate"] and not r[2]["empate"]


def test_ranking_vacio_y_elegir():
    """Sin ofertas no hay ranking; y la oferta elegida a mano gana, salvo que ya no exista (entonces la mejor)."""
    assert rk.construir_ranking([]) == []
    assert rk.elegir([], None) == (None, False)
    r = rk.construir_ranking([_o(1, "1", 100), _o(2, "2", 80)])
    assert rk.elegir(r, None)[0]["cod_empresa"] == "2"
    assert rk.elegir(r, "1") == (r[1], True)
    assert rk.elegir(r, "99")[1] is False  # elegida que ya no existe -> gana la mejor


def test_normalizacion():
    """Limpieza de datos: «05» = «5» en proveedores, los ceros de los productos se conservan, y los números se leen en varios formatos."""
    assert nz.codigo_empresa("05") == "5" and nz.codigo_empresa(" 80 ") == "80"
    assert nz.codigo_producto("0041") == "0041"  # ceros a la izquierda de PRODUCTOS se conservan
    assert nz.codigo_producto("5929.0") == "5929"
    assert nz.codigo_producto(float("nan")) is None
    assert nz.numero("1.234,5") == 1234.5 and nz.numero("$ 1,234.50") == 1234.5
    assert nz.numero("30940") == 30940 and nz.numero("abc") is None and nz.numero(None) is None
    assert nz.clave_busqueda("0041", "AGUJA ÑANDÚ") == "0041 aguja nandu"
