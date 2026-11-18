"""
PRUEBAS DE LO «HECHO A MANO»: crear, editar y eliminar productos y proveedores desde formularios.

Usa los datos inventados de conftest.py (productos A1, B2, C3, D4, F6, 0041; proveedores 1 a 6).
Lo más importante que se verifica aquí:
  - las reglas (no duplicar códigos ni nombres, el mínimo no supera al máximo...),
  - que lo del Excel base no se pueda eliminar,
  - que lo hecho a mano SOBREVIVA a «Actualizar Excel».
"""

import sqlite3

from app.database import iniciar_db


def _producto(c, cod):
    """Atajo: pide los datos de un producto."""
    return c.get(f"/api/productos/{cod}")


def _listar(c, **p):
    """Atajo: pide la lista de productos con los filtros dados."""
    return c.get("/api/productos", params=p).json()


# --------------------------------------------------------------------------- Productos
def test_crear_producto_a_mano(cliente):
    """Un producto creado a mano aparece con su cantidad a comprar calculada (StockMax − Existencias)."""
    r = cliente.post(
        "/api/productos",
        json={"cod": " N1 ", "descripcion": "  PRODUCTO   NUEVO ", "stock_max": 50, "stock_min": 10, "existencias": 5},
    )
    assert r.status_code == 201
    assert r.json() == {"cod": "N1", "descripcion": "PRODUCTO NUEVO"}  # se limpian los espacios
    p = _producto(cliente, "N1").json()
    assert p["origen"] == "manual" and p["es_propio"] and p["en_stock"] and p["n_ofertas"] == 0
    fila = next(i for i in _listar(cliente, q="N1")["items"] if i["cod"] == "N1")
    assert fila["comprar"] == 45 and fila["n_ofertas"] == 0  # 50 − 5, y todavía sin ofertas


def test_producto_sin_stock_existe_pero_no_se_compra(cliente):
    """Sin StockMax el producto queda «sin stock definido»: está en el catálogo pero no en «Por comprar»."""
    assert cliente.post("/api/productos", json={"cod": "S1", "descripcion": "SIN STOCK"}).status_code == 201
    assert not _producto(cliente, "S1").json()["en_stock"]
    assert "S1" not in {i["cod"] for i in _listar(cliente, filtro="por_comprar", q="S1")["items"]}
    assert "S1" in {i["cod"] for i in _listar(cliente, filtro="todos", q="S1")["items"]}


def test_crear_producto_repetido_da_409(cliente):
    """No se pueden crear dos productos con el mismo código (ni uno que ya viene del Excel)."""
    assert cliente.post("/api/productos", json={"cod": "N1", "descripcion": "UNO"}).status_code == 201
    assert cliente.post("/api/productos", json={"cod": "N1", "descripcion": "OTRO"}).status_code == 409
    r = cliente.post("/api/productos", json={"cod": "A1", "descripcion": "YA ESTÁ EN EL EXCEL"})
    assert r.status_code == 409 and "A1" in r.json()["detail"]


def test_crear_producto_validaciones(cliente):
    """Se rechazan stocks negativos, mínimo mayor que máximo, y falta de código o de descripción."""

    def post(**b):
        """Atajo: intenta crear un producto con los campos dados."""
        return cliente.post("/api/productos", json=b)

    assert post(cod="V1", descripcion="X", stock_max=-1).status_code == 422
    assert post(cod="V1", descripcion="X", stock_max=10, stock_min=20).status_code == 422
    assert post(cod="V1", descripcion="X", existencias=-5).status_code == 422
    assert post(cod="", descripcion="X").status_code == 422
    assert post(cod="V1", descripcion="   ").status_code == 422
    assert _producto(cliente, "V1").status_code == 404  # ninguno de los intentos creó nada


def test_editar_producto_cambia_solo_lo_enviado(cliente):
    """PUT cambia únicamente los campos que se envían; los demás quedan como estaban."""
    r = cliente.put("/api/productos/A1", json={"existencias": 90})
    assert r.json() == {"ok": True, "cambio": True}
    p = _producto(cliente, "A1").json()
    assert p["existencias"] == 90 and p["stock_max"] == 100 and p["descripcion"] == "ALFA PRODUCTO"
    a1 = next(i for i in _listar(cliente, q="alfa", filtro="todos")["items"] if i["cod"] == "A1")
    assert a1["comprar"] == 10  # 100 − 90
    # enviar lo mismo que ya hay no es un cambio
    assert cliente.put("/api/productos/A1", json={"existencias": 90}).json()["cambio"] is False


def test_editar_producto_del_excel_lo_vuelve_propio(cliente):
    """Al editar un producto del Excel base pasa a ser propio (origen «manual»), para que no se lo pisen."""
    assert _producto(cliente, "A1").json()["origen"] == "excel"
    cliente.put("/api/productos/A1", json={"descripcion": "  ALFA   RENOMBRADO "})
    p = _producto(cliente, "A1").json()
    assert p["origen"] == "manual" and p["descripcion"] == "ALFA RENOMBRADO"


def test_editar_producto_quitar_stock_y_validaciones(cliente):
    """Un stock enviado como null se quita (el producto queda sin stock); y las reglas también valen al editar."""
    cliente.put("/api/productos/A1", json={"stock_max": None})
    assert not _producto(cliente, "A1").json()["en_stock"]
    assert cliente.put("/api/productos/B2", json={"stock_min": 50}).status_code == 422  # mínimo 50 > máximo 10
    assert cliente.put("/api/productos/B2", json={"descripcion": None}).status_code == 422  # no puede quedar vacía
    assert cliente.put("/api/productos/NOEXISTE", json={"existencias": 1}).status_code == 404


def test_eliminar_producto_propio_borra_tambien_sus_ofertas(cliente):
    """Eliminar un producto propio borra sus ofertas propias; los del Excel base no se pueden eliminar."""
    cliente.post("/api/productos", json={"cod": "N1", "descripcion": "NUEVO", "stock_max": 10})
    cliente.post("/api/ofertas", json={"cod_producto": "N1", "cod_empresa": "1", "valor": 5})
    assert cliente.delete("/api/productos/N1").json() == {"ok": True}
    assert _producto(cliente, "N1").status_code == 404
    total = cliente.get("/api/resumen").json()["ofertas_manuales"]
    assert total == 0  # la oferta manual de N1 se fue con el producto
    r = cliente.delete("/api/productos/A1")
    assert r.status_code == 409 and "Excel base" in r.json()["detail"]
    assert cliente.delete("/api/productos/NOEXISTE").status_code == 404


def test_lo_editado_a_mano_sobrevive_a_actualizar_excel(cliente):
    """«Actualizar Excel» recarga los productos base pero NO pisa un producto editado ni uno creado a mano."""
    cliente.put("/api/productos/A1", json={"existencias": 90})
    cliente.post("/api/productos", json={"cod": "N1", "descripcion": "NUEVO", "stock_max": 10})
    cliente.post("/api/importar")
    assert _producto(cliente, "A1").json()["existencias"] == 90  # el Excel decía 20: gana lo tuyo
    assert _producto(cliente, "N1").status_code == 200  # el creado a mano sigue ahí
    assert _producto(cliente, "B2").json()["origen"] == "excel"  # el resto se recargó desde el Excel


# --------------------------------------------------------------------------- Proveedores
def test_crear_proveedor_con_y_sin_codigo(cliente):
    """Sin código se asigna uno desde 1000; con código se respeta."""
    a = cliente.post("/api/empresas", json={"nombre": "  Droguería   Nueva "})
    assert a.status_code == 201 and a.json()["nombre"] == "Droguería Nueva" and int(a.json()["cod"]) >= 1000
    b = cliente.post("/api/empresas", json={"nombre": "Con Código", "cod": "77"})
    assert b.json()["cod"] == "77"
    nombres = {e["nombre"]: e for e in cliente.get("/api/empresas").json()}
    assert nombres["Con Código"]["origen"] == "manual"


def test_crear_proveedor_repetido_da_409(cliente):
    """No se duplican proveedores: ni por nombre (sin importar mayúsculas) ni por código."""
    assert cliente.post("/api/empresas", json={"nombre": "alfa sas"}).status_code == 409  # ya existe «ALFA SAS»
    assert (
        cliente.post("/api/empresas", json={"nombre": "Otro", "cod": "1"}).status_code == 409
    )  # el código 1 es de ALFA
    assert cliente.post("/api/empresas", json={"nombre": "X"}).status_code == 422  # nombre demasiado corto


def test_editar_proveedor(cliente):
    """Se puede cambiar el nombre; no a uno que ya usa otro proveedor; y el proveedor debe existir."""
    assert cliente.put("/api/empresas/1", json={"nombre": "ALFA RENOMBRADA"}).json() == {"ok": True, "cambio": True}
    assert cliente.put("/api/empresas/1", json={"nombre": "ALFA RENOMBRADA"}).json()["cambio"] is False
    assert cliente.put("/api/empresas/1", json={"nombre": "beta sas"}).status_code == 409
    assert cliente.put("/api/empresas/999", json={"nombre": "Nada"}).status_code == 404
    nombres = {e["cod"]: e["nombre"] for e in cliente.get("/api/empresas").json()}
    assert nombres["1"] == "ALFA RENOMBRADA"


def test_proveedor_renombrado_sobrevive_a_actualizar_excel(cliente):
    """Un proveedor del Excel que renombras pasa a ser tuyo: «Actualizar Excel» no le devuelve el nombre viejo."""
    cliente.put("/api/empresas/1", json={"nombre": "ALFA RENOMBRADA"})
    cliente.post("/api/importar")
    nombres = {e["cod"]: e["nombre"] for e in cliente.get("/api/empresas").json()}
    assert nombres["1"] == "ALFA RENOMBRADA"
    assert nombres["2"] == "BETA SAS"  # los demás siguen igual


def test_eliminar_proveedor(cliente):
    """Solo se elimina un proveedor propio SIN ofertas; los del Excel base y los que tienen ofertas dan 409."""
    nuevo = cliente.post("/api/empresas", json={"nombre": "Temporal"}).json()["cod"]
    cliente.post("/api/ofertas", json={"cod_producto": "A1", "cod_empresa": nuevo, "valor": 10})
    r = cliente.delete(f"/api/empresas/{nuevo}")
    assert r.status_code == 409 and "1 oferta" in r.json()["detail"]  # tiene una oferta
    oferta_id = cliente.get("/api/productos/A1/ofertas").json()["ofertas"][0]["id"]
    cliente.delete(f"/api/ofertas/{oferta_id}")  # se elimina su oferta...
    assert cliente.delete(f"/api/empresas/{nuevo}").json() == {"ok": True}  # ...y ahora sí se puede eliminar
    assert cliente.delete("/api/empresas/2").status_code == 409  # BETA viene del Excel base
    assert cliente.delete("/api/empresas/999").status_code == 404


# --------------------------------------------------------------------------- Migración
def test_migracion_agrega_la_columna_origen(tmp_path, monkeypatch):
    """Una base creada con la versión anterior (sin la columna `origen`) se actualiza sola al arrancar."""
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE productos (cod TEXT PRIMARY KEY, descripcion TEXT NOT NULL, stock_max REAL, stock_med REAL, "
        "stock_min REAL, existencias REAL NOT NULL DEFAULT 0, en_stock INTEGER NOT NULL DEFAULT 0)"
    )
    con.execute("INSERT INTO productos (cod, descripcion) VALUES ('P1', 'VIEJO')")
    con.commit()
    con.close()
    monkeypatch.setenv("COMPRAS_DB", str(ruta))
    iniciar_db()
    iniciar_db()  # ejecutarla dos veces no debe fallar
    con = sqlite3.connect(ruta)
    assert "origen" in {f[1] for f in con.execute("PRAGMA table_info(productos)")}
    assert (
        con.execute("SELECT origen FROM productos WHERE cod = 'P1'").fetchone()[0] == "excel"
    )  # lo que ya había era del Excel
    con.close()
