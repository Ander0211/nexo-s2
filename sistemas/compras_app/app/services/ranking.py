"""
REGLAS DE NEGOCIO PURAS
=======================
Este es el archivo más importante para entender el «cerebro» de la aplicación.
Son funciones «puras»: reciben datos y devuelven un resultado, sin tocar la base de
datos ni la web. Por eso son fáciles de probar (ver tests/test_reglas.py).

Las dos reglas del negocio (las mismas que tenía Access):

    cantidad a comprar = StockMax - Existencias   (nunca menor que 0, en unidades enteras)
    mejor proveedor    = el de menor VALOR; luego 2.ª, 3.ª... en orden ascendente

Y una tercera, que las ofertas con «cantidad disponible» hacen necesaria:

    reparto            = si el mejor proveedor no tiene unidades para todo lo que hay que comprar, se le compra lo que tenga
                         y el resto al siguiente más barato, y así hasta cubrirlo (ver `repartir`)
"""

import math
from collections.abc import Iterable, Mapping


def _clave_empresa(cod: str):
    """Clave para desempatar proveedores por su código.

    Los códigos numéricos se comparan como NÚMEROS (2 antes que 10; como texto "10" < "2"),
    y los códigos con letras van después de los numéricos.
    """
    return (0, int(cod), "") if cod.isdigit() else (1, 0, cod)


def cantidad_a_comprar(stock_max: float | None, existencias: float | None) -> int:
    """Cuántas unidades hay que comprar para llegar al stock máximo.

    Ejemplos:
        cantidad_a_comprar(100, 20)  → 80     (faltan 80 para llegar a 100)
        cantidad_a_comprar(10, 25)   → 0      (ya hay de sobra; nunca es negativa)
        cantidad_a_comprar(None, 3)  → 0      (sin stock definido no se compra)
        cantidad_a_comprar(1000, 331.1) → 669 (siempre unidades enteras, redondeando hacia arriba)
    """
    if stock_max is None:
        return 0
    faltante = stock_max - (existencias or 0)  # «existencias or 0»: si no hay dato, se asume 0
    # El «- 1e-9» evita que un error mínimo de decimales (ej. 668.9999999) suba una unidad de más.
    return 0 if faltante <= 0 else math.ceil(faltante - 1e-9)


def nivel_stock(existencias: float | None, stock_min: float | None, stock_max: float | None) -> str:
    """critico: en o bajo el mínimo · bajo: bajo la mitad del rango · ok · sin_definir.

    Sirve para el color de la barra de stock en la pantalla (rojo / amarillo / verde).
    """
    if stock_max is None:
        return "sin_definir"
    ex, mn = existencias or 0, stock_min or 0
    if ex <= mn:
        return "critico"
    # (mn + stock_max) / 2 = punto medio entre el mínimo y el máximo.
    return "bajo" if ex <= (mn + stock_max) / 2 else "ok"


def construir_ranking(ofertas: Iterable[Mapping]) -> list[dict]:
    """Ordena las ofertas de UN producto de la más barata a la más cara.

    Si un proveedor tiene varias ofertas (p. ej. una del Excel y otra manual) cuenta
    solo la de menor precio (a igual precio, la que dice cuántas unidades tiene). Empates de precio: gana el proveedor de menor código.

    A cada oferta le agrega:
        puesto   1, 2, 3...
        dif_abs  cuánto más cara es que la mejor, en pesos por unidad
        dif_pct  cuánto más cara es que la mejor, en porcentaje
        empate   True si otro proveedor ofrece exactamente el mismo precio
    """

    # Paso 1: quedarse con UNA oferta por proveedor (la más barata; si empatan, la de menor id).
    # A igual precio se prefiere la que informa su cantidad disponible (la del Excel base no la trae): así un tope declarado no se pierde.
    def _orden(o: Mapping) -> tuple:
        return (o["valor"], o.get("disponible") is None, o["id"])

    por_empresa: dict[str, Mapping] = {}
    for o in ofertas:
        actual = por_empresa.get(o["cod_empresa"])
        if actual is None or _orden(o) < _orden(actual):
            por_empresa[o["cod_empresa"]] = o
    # Paso 2: ordenar por precio; en empate, por código de proveedor; luego por id.
    ordenadas = sorted(
        por_empresa.values(),
        key=lambda o: (o["valor"], _clave_empresa(o["cod_empresa"]), o["id"]),
    )
    if not ordenadas:
        return []
    # Paso 3: numerar y calcular la diferencia contra la mejor (la primera).
    mejor = ordenadas[0]["valor"]
    valores = [o["valor"] for o in ordenadas]
    resultado = []
    for i, o in enumerate(ordenadas, start=1):
        d = dict(o)  # copia, para no modificar el dato original
        d["puesto"] = i
        d["dif_abs"] = round(o["valor"] - mejor, 2)
        d["dif_pct"] = round((o["valor"] / mejor - 1) * 100, 1)
        d["empate"] = valores.count(o["valor"]) > 1
        resultado.append(d)
    return resultado


def elegir(ranking: list[dict], cod_empresa_elegida: str | None) -> tuple[dict | None, bool]:
    """Devuelve (oferta_elegida, fue_elegida_a_mano). Si la elegida ya no tiene oferta, gana la mejor.

    Es la oferta con la que realmente se va a comprar:
        - si el usuario eligió un proveedor y todavía tiene oferta → esa (a_mano = True)
        - si no → la primera del ranking, la más barata (a_mano = False)
        - si el producto no tiene ofertas → (None, False)
    """
    if cod_empresa_elegida:
        for o in ranking:
            if o["cod_empresa"] == cod_empresa_elegida:
                return o, True
    return (ranking[0], False) if ranking else (None, False)


def repartir(cantidad: int, ranking: list[dict], elegida: dict | None = None) -> dict:
    """Decide a QUIÉN se le compra cuánto, teniendo en cuenta cuántas unidades puede entregar cada proveedor (`disponible`).

    `ranking` es lo que devuelve `construir_ranking` (de la oferta más barata a la más cara, una por proveedor). Una oferta sin `disponible`
    (None) significa que el proveedor NO dijo cuánto tiene: se supone que le alcanza para todo. `elegida` es la oferta que el usuario escogió
    A MANO (None si no escogió ninguna).

    Devuelve un diccionario con:
        lineas      lista de ofertas con dos datos más: `cantidad` (unidades que se le compran) y `subtotal` (valor × cantidad)
        cubierta    cuántas unidades quedan cubiertas
        faltante    cuántas unidades NINGÚN proveedor puede entregar (0 si todo queda cubierto)
        repartida   True si la compra se divide entre más de un proveedor
        excede      solo con elección a mano: cuántas unidades pide por encima de lo que dijo tener ese proveedor

    Ejemplos (precio · disponible):  A $10 · 600    B $12 · sin dato    C $15 · 50
        repartir(1000, [A, B, C])     → 600 con A, 400 con B           (B no tiene tope: cubre el resto)
        repartir(1000, [A, C])        → 600 con A, 50 con C, faltan 350
        repartir(1000, [A, B, C], B)  → 1000 con B: lo escogió el usuario, no se reparte (y avisa si B no alcanza)
        repartir(100,  [A, B, C])     → 100 con A                       (alcanza: igual que si no hubiera tope)
    """
    if cantidad <= 0 or not ranking:
        return {"lineas": [], "cubierta": 0, "faltante": 0, "repartida": False, "excede": 0}

    def linea(o: dict, n: int) -> dict:
        return {**o, "cantidad": n, "subtotal": round(o["valor"] * n, 2)}

    if elegida:  # lo escogió el usuario: se le compra TODO a ese proveedor; solo se avisa si dijo tener menos
        disp = elegida.get("disponible")
        excede = max(0, cantidad - int(disp)) if disp is not None else 0
        return {
            "lineas": [linea(elegida, cantidad)],
            "cubierta": cantidad,
            "faltante": 0,
            "repartida": False,
            "excede": excede,
        }
    falta = cantidad
    lineas: list[dict] = []
    for o in ranking:
        disp = o.get("disponible")
        tomar = (
            falta if disp is None else min(falta, max(int(disp), 0))
        )  # sin dato: le alcanza; si no, solo lo que tiene (enteros)
        if tomar > 0:
            lineas.append(linea(o, tomar))
            falta -= tomar
        if falta == 0:
            break
    return {
        "lineas": lineas,
        "cubierta": cantidad - falta,
        "faltante": falta,
        "repartida": len(lineas) > 1,
        "excede": 0,
    }
