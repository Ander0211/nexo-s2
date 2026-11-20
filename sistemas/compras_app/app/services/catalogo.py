"""
CATÁLOGO: CREAR, EDITAR Y ELIMINAR PRODUCTOS Y PROVEEDORES
==========================================================
Este archivo concentra las REGLAS para tocar productos y proveedores. Lo usan dos «puertas»:

    - los formularios manuales      (routers/productos.py y routers/empresas.py)
    - la carga de Excel desde la pantalla   (services/cargas.py)

Así, las reglas están escritas UNA sola vez y valen igual venga el dato de un formulario o de un Excel.

Las funciones NO hacen `commit`: quien las llama decide cuándo se confirma la transacción
(con `with con:`). Cuando algo no se puede hacer, lanzan CatalogoError con el código HTTP que corresponde;
main.py lo convierte en una respuesta de error con un mensaje claro para el usuario.

Sobre el «origen» de cada fila (ver database.py):
    'excel'  viene de los Excel base            → no se puede eliminar desde la pantalla
    'manual' lo escribió el usuario a mano      → se puede editar y eliminar
    'subido' lo cargó el usuario desde un Excel → se puede editar y eliminar
Editar un producto o proveedor que venía del Excel base lo convierte en PROPIO (queda como 'manual' o 'subido'),
para que «Actualizar Excel» no le pise el cambio.
"""

import sqlite3

from ..config import PRIMER_CODIGO_EMPRESA_MANUAL
from . import normalizacion as nz

# Orígenes que pertenecen al usuario: se conservan al actualizar los Excel base.
ORIGENES_PROPIOS = ("manual", "subido")

# Únicos campos de un producto que se pueden cambiar (lista fija: se usa para armar el UPDATE de forma segura).
CAMPOS_PRODUCTO = ("descripcion", "stock_max", "stock_med", "stock_min", "existencias")


class CatalogoError(Exception):
    """Error de negocio con el código HTTP que le corresponde.

    estado 404 = no existe · 409 = conflicto (ya existe, o no se permite) · 422 = dato inválido.
    """

    def __init__(self, mensaje: str, estado: int = 422):
        """Guarda el mensaje (para mostrárselo al usuario) y el código HTTP (422 por defecto)."""
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado


# --------------------------------------------------------------------------- Proveedores
def codigo_proveedor_nuevo(con: sqlite3.Connection) -> str:
    """Código para un proveedor creado por el usuario: el mayor código numérico existente + 1,
    pero nunca menor que 1000 (así no choca con los del Excel, que van del 1 al ~80)."""
    fila = con.execute("SELECT MAX(CAST(cod AS INTEGER)) AS m FROM empresas WHERE cod GLOB '[0-9]*'").fetchone()
    return str(max((fila["m"] or 0) + 1, PRIMER_CODIGO_EMPRESA_MANUAL))


def buscar_empresa_por_nombre(con: sqlite3.Connection, nombre: str) -> sqlite3.Row | None:
    """Busca un proveedor por nombre con la regla de todo el sistema (normalizacion.clave_nombre): sin tildes, sin mayúsculas y sin espacios
    ni signos. «alfa s.a.s.», «ÁLFA SAS» y «ALFA  SAS» encuentran a «ALFA SAS». Devuelve None si no hay uno igual."""
    clave = nz.clave_nombre(nombre)
    if not clave:
        return None
    return next(
        (f for f in con.execute("SELECT * FROM empresas ORDER BY cod") if nz.clave_nombre(f["nombre"]) == clave), None
    )


def buscar_producto_por_codigo(con: sqlite3.Connection, cod) -> sqlite3.Row | None:
    """Busca un producto por código sin distinguir mayúsculas («a1» encuentra «A1»). Devuelve None si no hay uno igual."""
    clave = nz.clave_codigo(nz.codigo_producto(cod))
    if not clave:
        return None
    return next((f for f in con.execute("SELECT * FROM productos") if nz.clave_codigo(f["cod"]) == clave), None)


def _nombre_valido(nombre) -> str:
    """Limpia el nombre de un proveedor y exige al menos 2 caracteres."""
    limpio = nz.texto(nombre)
    if not limpio or len(nz.clave_nombre(limpio)) < 2:
        raise CatalogoError("El nombre del proveedor debe tener al menos 2 letras.")
    return limpio


def crear_empresa(con: sqlite3.Connection, nombre, cod=None, origen: str = "manual") -> dict:
    """Crea un proveedor. Si no se indica código se le asigna uno (desde 1000).

    409 si ya hay un proveedor con ese nombre (sin importar mayúsculas) o con ese código.
    """
    nombre = _nombre_valido(nombre)
    existente = buscar_empresa_por_nombre(con, nombre)
    if existente:
        raise CatalogoError(f"Ya existe un proveedor llamado «{existente['nombre']}» (código {existente['cod']}).", 409)
    if cod:
        cod = nz.codigo_empresa(cod)
        ocupado = con.execute("SELECT nombre FROM empresas WHERE cod = ?", (cod,)).fetchone()
        if ocupado:
            raise CatalogoError(f"El código {cod} ya lo usa el proveedor «{ocupado['nombre']}».", 409)
    else:
        cod = codigo_proveedor_nuevo(con)
    con.execute("INSERT INTO empresas (cod, nombre, origen) VALUES (?, ?, ?)", (cod, nombre, origen))
    return {"cod": cod, "nombre": nombre}


def actualizar_empresa(con: sqlite3.Connection, cod: str, nombre, origen: str = "manual") -> bool:
    """Cambia el nombre de un proveedor. Devuelve True si hubo cambio y False si el nombre ya era ese.

    Si el proveedor venía del Excel base, pasa a ser PROPIO (para que «Actualizar Excel» no le devuelva el nombre viejo).
    """
    fila = con.execute("SELECT * FROM empresas WHERE cod = ?", (cod,)).fetchone()
    if not fila:
        raise CatalogoError("Ese proveedor no existe.", 404)
    nombre = _nombre_valido(nombre)
    otro = buscar_empresa_por_nombre(con, nombre)
    if otro and otro["cod"] != cod:
        raise CatalogoError(f"Ya existe otro proveedor llamado «{otro['nombre']}» (código {otro['cod']}).", 409)
    if fila["nombre"] == nombre:
        return False
    origen_final = fila["origen"] if fila["origen"] in ORIGENES_PROPIOS else origen
    con.execute("UPDATE empresas SET nombre = ?, origen = ? WHERE cod = ?", (nombre, origen_final, cod))
    return True


def eliminar_empresa(con: sqlite3.Connection, cod: str) -> int:
    """Elimina un proveedor PROPIO con TODO lo suyo (ofertas, elegidos a mano, ofertas de «Adicionales»); el tablero
    busca la siguiente oferta más baja de otro proveedor. Los del Excel base se eliminan en Administración → Empresas
    (409 aquí). Devuelve cuántas ofertas se borraron."""
    fila = con.execute("SELECT * FROM empresas WHERE cod = ?", (cod,)).fetchone()
    if not fila:
        raise CatalogoError("Ese proveedor no existe.", 404)
    if fila["origen"] not in ORIGENES_PROPIOS:
        raise CatalogoError(
            "Este proveedor viene de los Excel base y no se puede eliminar desde aquí. "
            "Quítalo del Excel y pulsa «Actualizar Excel».",
            409,
        )
    n = con.execute("SELECT COUNT(*) FROM ofertas WHERE cod_empresa = ?", (cod,)).fetchone()[0]
    for tabla in ("ofertas", "seleccion", "ofertas_libres"):
        con.execute(f"DELETE FROM {tabla} WHERE cod_empresa = ?", (cod,))  # noqa: S608
    con.execute("DELETE FROM empresas WHERE cod = ?", (cod,))
    return n


# --------------------------------------------------------------------------- Productos
def _validar_stock(stock_max, stock_min) -> None:
    """Regla: el stock mínimo no puede ser mayor que el máximo."""
    if stock_max is not None and stock_min is not None and stock_min > stock_max:
        raise CatalogoError(f"El stock mínimo ({stock_min:g}) no puede ser mayor que el máximo ({stock_max:g}).")


def crear_producto(
    con: sqlite3.Connection,
    cod,
    descripcion,
    *,
    stock_max=None,
    stock_med=None,
    stock_min=None,
    existencias=0.0,
    origen: str = "manual",
) -> dict:
    """Crea un producto. Sin StockMax queda «sin stock definido» (existe en el catálogo pero no se compra).

    409 si ya existe un producto con ese código.
    """
    cod = nz.codigo_producto(cod)
    descripcion = nz.texto(descripcion)
    if not cod:
        raise CatalogoError("Falta el código del producto.")
    if not descripcion:
        raise CatalogoError("Falta la descripción del producto.")
    _validar_stock(stock_max, stock_min)
    if buscar_producto_por_codigo(con, cod):
        raise CatalogoError(f"Ya existe un producto con el código {cod}.", 409)
    con.execute(
        "INSERT INTO productos (cod, descripcion, stock_max, stock_med, stock_min, existencias, en_stock, origen) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (cod, descripcion, stock_max, stock_med, stock_min, existencias or 0.0, 0 if stock_max is None else 1, origen),
    )
    return {"cod": cod, "descripcion": descripcion}


def actualizar_producto(con: sqlite3.Connection, cod: str, cambios: dict, origen: str = "manual") -> bool:
    """Cambia SOLO los campos que vengan en `cambios` (los demás quedan como estaban).

    `cambios` usa las claves de CAMPOS_PRODUCTO. Un stock puesto en None significa «quitarlo».
    Devuelve True si algo cambió de verdad. Si el producto venía del Excel base, pasa a ser PROPIO.
    """
    fila = con.execute("SELECT * FROM productos WHERE cod = ?", (cod,)).fetchone()
    if not fila:
        raise CatalogoError("Ese producto no existe.", 404)
    desconocidos = set(cambios) - set(CAMPOS_PRODUCTO)
    if desconocidos:
        raise CatalogoError(f"Campos no permitidos: {sorted(desconocidos)}")
    cambios = dict(cambios)
    if "descripcion" in cambios:
        cambios["descripcion"] = nz.texto(cambios["descripcion"])
        if not cambios["descripcion"]:
            raise CatalogoError("La descripción no puede quedar vacía.")
    if "existencias" in cambios and cambios["existencias"] is None:
        cambios["existencias"] = 0.0
    _validar_stock(
        cambios.get("stock_max", fila["stock_max"]),
        cambios.get("stock_min", fila["stock_min"]),
    )
    distintos = {c: v for c, v in cambios.items() if fila[c] != v}
    if not distintos:
        return False
    stock_max_final = distintos.get("stock_max", fila["stock_max"])
    origen_final = fila["origen"] if fila["origen"] != "excel" else origen
    # Los nombres de columna salen de CAMPOS_PRODUCTO (lista fija), nunca del usuario: el f-string es seguro.
    asignaciones = ", ".join(f"{c} = ?" for c in distintos)
    con.execute(
        f"UPDATE productos SET {asignaciones}, en_stock = ?, origen = ? WHERE cod = ?",
        (*distintos.values(), 0 if stock_max_final is None else 1, origen_final, cod),
    )
    return True


def eliminar_producto(con: sqlite3.Connection, cod: str) -> None:
    """Elimina un producto PROPIO junto con sus ofertas propias y su proveedor elegido.

    Los del Excel base no se pueden eliminar desde aquí (409). Si un producto también está en el Excel base
    y lo eliminas aquí, volverá a aparecer al pulsar «Actualizar Excel».
    """
    fila = con.execute("SELECT * FROM productos WHERE cod = ?", (cod,)).fetchone()
    if not fila:
        raise CatalogoError("Ese producto no existe.", 404)
    if fila["origen"] == "excel":
        raise CatalogoError(
            "Este producto viene de los Excel base y no se puede eliminar desde aquí. "
            "Quítalo del Excel y pulsa «Actualizar Excel».",
            409,
        )
    con.execute("DELETE FROM ofertas WHERE cod_producto = ? AND origen IN ('manual', 'subido')", (cod,))
    con.execute("DELETE FROM seleccion WHERE cod_producto = ?", (cod,))
    con.execute("DELETE FROM cantidades WHERE cod_producto = ?", (cod,))
    con.execute("DELETE FROM productos WHERE cod = ?", (cod,))
