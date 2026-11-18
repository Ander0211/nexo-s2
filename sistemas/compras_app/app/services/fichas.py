"""
FICHA DE UNA EMPRESA (PROVEEDOR)
================================
Todo lo que el sistema sabe de un proveedor, para mostrarlo cuando se pulsa su nombre en «Mejor oferta» u «Otras ofertas»:

    - quién es: código, nombre, de dónde viene (Excel base, propio...), teléfono y correo
    - cuánto pesa en las compras de hoy: en cuántos productos tiene la mejor oferta, a cuántos se le compraría (la oferta
      elegida, que puede ser otra si el usuario eligió a mano) y cuánto sería la inversión
    - sus ofertas: producto por producto, con el puesto que ocupa frente a los demás proveedores

El teléfono y el correo se escriben en la tabla EMPRESAS de «Administración»; solo los proveedores del Excel base los tienen
(los creados a mano en «Agregar oferta» o «Cargar datos» no tienen esos datos).
"""

import sqlite3

from . import etiquetas, tablero
from . import normalizacion as nz
from . import ranking as rk
from .catalogo import CatalogoError

ORIGENES = {
    "excel": "Excel base",
    "inferida": "Aparece en el portafolio pero no está en EMPRESA.xlsx",
    "manual": "Creada a mano",
    "subido": "Subida desde un Excel",
}


def contacto_de(con: sqlite3.Connection, cod: str) -> dict:
    """Teléfono y correo de la empresa, tomados de la tabla EMPRESAS de Administración (o vacíos si no los tiene)."""
    cod = nz.codigo_empresa(cod) or cod
    for r in con.execute("SELECT CODIGO_EMPRESA, TELEFONO, CORREO FROM x_empresas ORDER BY id"):
        if nz.codigo_empresa(r["CODIGO_EMPRESA"]) == cod:
            return {"telefono": r["TELEFONO"], "correo": r["CORREO"]}
    return {"telefono": None, "correo": None}


def ficha_empresa(con: sqlite3.Connection, cod: str) -> dict:
    """La ficha de la empresa `cod`. CatalogoError 404 si no existe."""
    cod = nz.codigo_empresa(cod) or cod
    e = con.execute("SELECT cod, nombre, origen FROM empresas WHERE cod = ?", (cod,)).fetchone()
    if e is None:
        raise CatalogoError("Ese proveedor no existe.", 404)

    etiquetas.sincronizar(con)
    nuevas = etiquetas.nuevos(con, "empresa")
    agrupadas = tablero.ofertas_por_producto(con)
    por_producto = {i["cod"]: i for i in tablero.construir_tablero(con)}
    propias: dict[
        str, dict
    ] = {}  # su oferta más barata en cada producto (si repitió, cuenta la menor, como en el ranking)
    for cod_prod, ofertas in agrupadas.items():
        mias = [o for o in ofertas if o["cod_empresa"] == cod]
        if mias:
            propias[cod_prod] = min(mias, key=lambda o: (o["valor"], o["id"]))

    ofertas, n_mejores, n_elegidas, inversion = [], 0, 0, 0.0
    for cod_prod, mia in propias.items():
        item = por_producto.get(cod_prod)
        ranking = rk.construir_ranking(agrupadas[cod_prod])
        puesto = next((o["puesto"] for o in ranking if o["cod_empresa"] == cod), None)
        comprar = item["comprar"] if item else 0
        linea = (
            next((ln for ln in item["reparto"] if ln["cod_empresa"] == cod), None) if item else None
        )  # lo que se le compra (si algo)
        es_elegida = bool(linea and comprar > 0)
        n_mejores += puesto == 1
        if es_elegida:
            n_elegidas += 1
            inversion += (
                linea["subtotal"] or 0
            )  # solo la parte que se le compra a ÉL (si la compra se reparte, no todo el producto)
        ofertas.append(
            {
                "cod_producto": cod_prod,
                "descripcion": item["descripcion"] if item else cod_prod,
                "valor": mia["valor"],
                "presentacion": mia["presentacion"],
                "origen": mia["origen"],
                "puesto": puesto,
                "n_ofertas": len(ranking),
                "es_mejor": puesto == 1,
                "es_elegida": es_elegida,
                "comprar": comprar,
                "total": linea["subtotal"] if es_elegida else (round(mia["valor"] * comprar, 2) if comprar else None),
                "cantidad": linea["cantidad"]
                if es_elegida
                else comprar,  # las unidades que se le compran (con reparto pueden ser menos que «comprar»)
            }
        )
    # Primero los productos que se le comprarían, luego sus mejores ofertas, y el resto de la A a la Z.
    ofertas.sort(key=lambda o: (not o["es_elegida"], not o["es_mejor"], o["descripcion"].lower()))
    return {
        "cod": e["cod"],
        "nombre": e["nombre"],
        "origen": e["origen"],
        "origen_texto": ORIGENES.get(e["origen"], e["origen"]),
        "nuevo": cod in nuevas,  # empresa nueva (primera vez que el sistema la ve)
        "nuevo_desde": nuevas.get(cod),
        **contacto_de(con, cod),
        "n_ofertas": len(ofertas),
        "n_mejores": n_mejores,
        "n_elegidas": n_elegidas,
        "inversion": round(inversion, 2),
        "ofertas": ofertas,
    }
