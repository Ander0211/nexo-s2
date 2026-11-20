"""
PRUEBAS DE LA ADMINISTRACIÓN DE TABLAS (las 5 tablas de los Excel) Y DE LOS AVISOS QUE LLEVAN AL LUGAR DEL PROBLEMA.

Usan los datos sintéticos de conftest.py. Recordatorio de esos datos:
  Stock         A1, B2, C3, D4, F6, 0041           Existencias   A1, B2, D4, ZZ, 0041
  Empresas      1 ALFA, 2 BETA, 3 GAMA, 4 DELTA, 6 (sin nombre)
  Ficha         A1, X9                              Portafolio    11 filas (filas 1 a 11, en el orden de conftest)
Lo que se protege aquí:
  - las tablas muestran los MISMOS encabezados que el Excel
  - cada cambio (agregar, editar, eliminar) recalcula el tablero
  - eliminar SIEMPRE se permite, y lo que queda huérfano sale en los avisos
  - cada aviso sabe a qué tabla y filas llevar
  - importar por tabla (reemplazar / agregar) y deshacer
"""

import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from tests.conftest import CLAVE_ADMIN, entrar, excel_bytes

ENCABEZADOS = {
    "stock": ["COD_PRODUCTO", "DESCRIPCION", "StockMax", "StockMed", "StockMin"],
    "existencias": ["COD_PRODUCTO", "DESCRIPCION", "CANTIDAD"],
    "empresas": ["CODIGO_EMPRESA", "NOMBRE", "TELEFONO", "CORREO"],
    "ficha": ["COD_SALUDIPS", "DESCRIPCION", "TIPO_INSUMO"],
    "portafolio": ["COD_EMPRESA", "COD_PRODUCTO", "DESCRIPCION", "VALOR", "PRESENTACION"],
}
FILAS = {"stock": 6, "existencias": 5, "empresas": 5, "ficha": 2, "portafolio": 11}


def _filas(c, tabla, **p):
    """Atajo: una página de filas de la tabla (hasta 200), como diccionario."""
    p.setdefault("tam", 200)
    return c.get(f"/api/admin/tablas/{tabla}/filas", params=p).json()


def _fila(c, tabla, **buscar):
    """La primera fila cuyos valores coinciden con `buscar` (por ejemplo COD_PRODUCTO='A1'), o None."""
    for f in _filas(c, tabla)["filas"]:
        if all(f["valores"].get(k) == v for k, v in buscar.items()):
            return f
    return None


def _item(c, cod):
    """El producto `cod` tal como lo ve el tablero (filtro «todos»)."""
    return next(
        i for i in c.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"] if i["cod"] == cod
    )


def _avisos(c):
    return {a["titulo"]: a for a in c.get("/api/avisos").json()}


def _aviso(c, empieza):
    return next(a for t, a in _avisos(c).items() if t.startswith(empieza))


CONTACTO = {"TELEFONO": "300 123 4567", "CORREO": "contacto@empresa.com"}  # obligatorio al agregar o editar una empresa


# ------------------------------------------------------------------------------------------------ ver las tablas
def test_las_cinco_tablas_muestran_los_encabezados_exactos_del_excel(cliente):
    """Cada tabla trae las columnas con el MISMO nombre y orden que su Excel (StockMax, CODIGO_EMPRESA...) y sus filas."""
    r = cliente.get("/api/admin/tablas").json()
    assert [t["clave"] for t in r] == list(ENCABEZADOS)
    for t in r:
        assert [c["nombre"] for c in t["columnas"]] == ENCABEZADOS[t["clave"]]
        assert t["filas"] == FILAS[t["clave"]]
    assert next(t for t in r if t["clave"] == "stock")["archivo"] == "05-STOCK.xlsx"


def test_las_filas_se_guardan_tal_cual_venian_en_el_excel(cliente):
    """Nada se «arregla» al guardar la tabla: el código «05» sigue siendo «05» y el proveedor sin nombre sigue vacío."""
    assert _fila(cliente, "portafolio", COD_EMPRESA="05")["valores"]["COD_PRODUCTO"] == "A1"
    assert _fila(cliente, "empresas", CODIGO_EMPRESA="6")["valores"]["NOMBRE"] is None
    assert _fila(cliente, "stock", COD_PRODUCTO="0041")["valores"]["StockMax"] == "10"


def test_buscar_ordenar_y_paginar_en_el_servidor(cliente):
    """La búsqueda ignora tildes y mayúsculas; las columnas numéricas ordenan como números; se pagina."""
    assert [f["valores"]["COD_PRODUCTO"] for f in _filas(cliente, "stock", q="nandu")["filas"]] == ["0041"]
    assert _filas(cliente, "stock", q="no existe")["total"] == 0
    # Como número: 100, 10, 10, 7, 5, 0 (como texto «7» iría antes que «100»).
    por_max = _filas(cliente, "stock", orden="StockMax", sentido="desc")["filas"]
    assert [f["valores"]["StockMax"] for f in por_max] == ["100", "10", "10", "7", "5", "0"]
    pagina = _filas(cliente, "portafolio", tam=4, pagina=3)
    assert pagina["total"] == 11 and pagina["paginas"] == 3 and len(pagina["filas"]) == 3
    # Las celdas vacías van siempre al final, sea cual sea el sentido.
    vacios = _filas(cliente, "portafolio", orden="VALOR", sentido="asc")["filas"]
    assert vacios[-1]["valores"]["VALOR"] is None and vacios[0]["valores"]["VALOR"] == "7"
    # Un encabezado inventado no llega al SQL: se ordena por número de fila.
    assert _filas(cliente, "stock", orden="x; DROP TABLE x_stock")["total"] == 6


# ------------------------------------------------------------------------------------------------ agregar y editar
def test_agregar_una_fila_recalcula_el_tablero(cliente):
    """Agregar X9 al Stock (antes solo estaba en ficha y portafolio) le da cantidad a comprar y oferta en el tablero."""
    assert _item(cliente, "X9")["comprar"] == 0
    r = cliente.post("/api/admin/tablas/stock/filas", json={"valores": {"COD_PRODUCTO": "X9", "StockMax": 20}})
    assert r.status_code == 201 and r.json()["fila"]["valores"]["StockMax"] == "20"
    x9 = _item(cliente, "X9")
    assert x9["en_stock"] and x9["comprar"] == 20 and x9["n_ofertas"] == 1
    assert _filas(cliente, "stock")["total"] == 7


def test_editar_una_fila_recalcula_y_respeta_lo_que_no_cambio(cliente):
    """Subir el StockMax de A1 a 200 cambia la cantidad a comprar (200 − 20 = 180). Solo se toca lo que cambió."""
    a1 = _fila(cliente, "stock", COD_PRODUCTO="A1")
    nuevos = {**a1["valores"], "StockMax": "200"}
    r = cliente.put(f"/api/admin/tablas/stock/filas/{a1['id']}", json={"valores": nuevos}).json()
    assert r["cambio"] and r["fila"]["valores"]["StockMax"] == "200"
    assert _item(cliente, "A1")["comprar"] == 180
    # Sin cambios reales: no se guarda nada ni se anota en el historial.
    antes = len(cliente.get("/api/admin/historial").json())
    assert cliente.put(f"/api/admin/tablas/stock/filas/{a1['id']}", json={"valores": nuevos}).json()["cambio"] is False
    assert len(cliente.get("/api/admin/historial").json()) == antes


def test_editar_no_recorta_las_celdas_que_no_se_tocaron(cliente):
    """Si una celda tenía espacios de más (como en el Excel real), editar OTRA columna no la modifica."""
    from app.database import conectar

    con = conectar()
    con.execute("INSERT INTO x_stock (COD_PRODUCTO, DESCRIPCION, StockMax) VALUES ('Z1', 'CON ESPACIO ', '5')")
    con.commit()
    fila_id = con.execute("SELECT id FROM x_stock WHERE COD_PRODUCTO = 'Z1'").fetchone()[0]
    con.close()
    valores = {"COD_PRODUCTO": "Z1", "DESCRIPCION": "CON ESPACIO", "StockMax": "9", "StockMed": None, "StockMin": None}
    cliente.put(f"/api/admin/tablas/stock/filas/{fila_id}", json={"valores": valores})
    fila = _fila(cliente, "stock", COD_PRODUCTO="Z1")["valores"]
    assert fila["StockMax"] == "9" and fila["DESCRIPCION"] == "CON ESPACIO "  # el espacio original se conservó


def test_validaciones_de_lo_que_escribe_el_usuario(cliente):
    """Números que no lo son, obligatorios vacíos, columnas inventadas, tablas y filas que no existen: errores claros."""
    url = "/api/admin/tablas/stock/filas"
    r = cliente.post(url, json={"valores": {"COD_PRODUCTO": "Q1", "StockMax": "muchos"}})
    assert r.status_code == 422 and "StockMax" in r.json()["detail"] and "número" in r.json()["detail"]
    r = cliente.post(url, json={"valores": {"COD_PRODUCTO": "  ", "StockMax": 5}})
    assert r.status_code == 422 and "COD_PRODUCTO" in r.json()["detail"] and "obligatorio" in r.json()["detail"]
    r = cliente.post(url, json={"valores": {"COD_PRODUCTO": "Q1", "COLOR": "rojo"}})
    assert r.status_code == 422 and "COLOR" in r.json()["detail"]
    assert cliente.post(url, json={"valores": {"COD_PRODUCTO": "Q1", "DESCRIPCION": "x" * 400}}).status_code == 422
    assert cliente.get("/api/admin/tablas/inventada/filas").status_code == 404
    assert cliente.put(f"{url}/9999", json={"valores": {"COD_PRODUCTO": "Q1"}}).status_code == 404
    assert cliente.delete(f"{url}/9999").status_code == 404
    assert _filas(cliente, "stock")["total"] == 6  # nada quedó guardado a medias


def test_un_numero_con_coma_o_puntos_se_acepta(cliente):
    """El usuario puede escribir «12,5» o «1.234,50» (como en Colombia); se guarda tal cual y el recálculo lo entiende."""
    r = cliente.post("/api/admin/tablas/stock/filas", json={"valores": {"COD_PRODUCTO": "Q1", "StockMax": "1.234,50"}})
    assert r.status_code == 201 and r.json()["fila"]["valores"]["StockMax"] == "1.234,50"
    assert _item(cliente, "Q1")["stock_max"] == 1234.5


# ------------------------------------------------------------------------------------------------ eliminar y huérfanos
def test_eliminar_un_proveedor_borra_todo_lo_suyo_y_el_tablero_busca_la_siguiente_menor(cliente):
    """Eliminar BETA borra sus ofertas, lo elegido a mano y sus «Adicionales»; A1 pasa a la siguiente más baja; se deshace."""
    antes = _item(cliente, "A1")["mejor"]
    assert antes["cod_empresa"] == "2"
    beta = _fila(cliente, "empresas", CODIGO_EMPRESA="2")
    aviso = cliente.get(f"/api/admin/tablas/empresas/filas/{beta['id']}/impacto").json()["mensaje"]
    assert "con todos los insumos cotizados" in aviso and "siguiente oferta más baja" in aviso  # se le dice ANTES de confirmar
    r = cliente.delete(f"/api/admin/tablas/empresas/filas/{beta['id']}").json()
    assert r["eliminadas"] == 1 and r["ofertas_eliminadas"] >= 1
    a1 = _item(cliente, "A1")
    assert a1["mejor"]["cod_empresa"] != "2"  # otro proveedor, el más barato que queda
    assert _fila(cliente, "portafolio", COD_EMPRESA="2") is None  # nada de BETA en Portafolio
    assert "Proveedores con ofertas que no existen" not in _avisos(cliente)
    h = cliente.get("/api/admin/historial").json()
    assert "con todos los insumos cotizados" in h[0]["resumen"]
    assert cliente.post(f"/api/admin/historial/{h[0]['id']}/deshacer").status_code == 200
    a1 = _item(cliente, "A1")
    assert a1["mejor"]["cod_empresa"] == "2"  # volvió todo
    assert _fila(cliente, "portafolio", COD_EMPRESA="2") is not None and _fila(cliente, "empresas", CODIGO_EMPRESA="2")


def test_eliminar_proveedor_elegido_a_mano_y_deshacer_devuelve_la_eleccion(cliente):
    """GAMA elegida a mano para A1: al eliminar GAMA, A1 vuelve a la más barata; al deshacer, vuelve a GAMA a mano."""
    cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "3"})
    assert _item(cliente, "A1")["elegida_a_mano"]
    gama = _fila(cliente, "empresas", CODIGO_EMPRESA="3")
    cliente.delete(f"/api/admin/tablas/empresas/filas/{gama['id']}")
    a1 = _item(cliente, "A1")
    assert a1["elegida"]["cod_empresa"] != "3" and not a1["elegida_a_mano"]
    assert "ya no los ofrece" not in _avisos(cliente)  # su elección se borró con él: no queda «huérfana»
    h = cliente.get("/api/admin/historial").json()
    cliente.post(f"/api/admin/historial/{h[0]['id']}/deshacer")
    a1 = _item(cliente, "A1")
    assert a1["elegida"]["cod_empresa"] == "3" and a1["elegida_a_mano"]


def test_eliminar_la_unica_oferta_deja_el_producto_sin_oferta(cliente):
    """Quitar de Portafolio la única oferta de C3 lo deja «sin oferta»: sube el conteo y el impacto lo advirtió."""
    assert cliente.get("/api/resumen").json()["sin_oferta"] == 1
    fila = _fila(cliente, "portafolio", COD_PRODUCTO="C3", VALOR="50")
    assert "única oferta" in cliente.get(f"/api/admin/tablas/portafolio/filas/{fila['id']}/impacto").json()["mensaje"]
    cliente.delete(f"/api/admin/tablas/portafolio/filas/{fila['id']}")
    assert cliente.get("/api/resumen").json()["sin_oferta"] == 2
    assert "2 productos por comprar no tienen ninguna oferta" in _avisos(cliente)


def test_eliminar_del_stock_avisa_que_el_producto_ya_no_tiene_stock(cliente):
    """Quitar A1 del Stock: el producto sigue (por sus ofertas) pero sin cantidad a comprar, y sale el aviso."""
    a1 = _fila(cliente, "stock", COD_PRODUCTO="A1")
    assert "stock definido" in cliente.get(f"/api/admin/tablas/stock/filas/{a1['id']}/impacto").json()["mensaje"]
    cliente.delete(f"/api/admin/tablas/stock/filas/{a1['id']}")
    assert not _item(cliente, "A1")["en_stock"] and _item(cliente, "A1")["comprar"] == 0
    assert "A1" in _aviso(cliente, "2 productos con ofertas no tienen stock definido")["detalle"]


def test_una_eleccion_de_proveedor_vieja_se_avisa_y_usa_la_mejor_oferta(cliente):
    """Si eliges GAMA para A1 y luego se elimina su fila del Portafolio, el tablero vuelve a la mejor y avisa."""
    cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "3"})
    assert _item(cliente, "A1")["elegida"]["cod_empresa"] == "3"
    fila = _fila(cliente, "portafolio", COD_EMPRESA="3", COD_PRODUCTO="A1")
    cliente.delete(f"/api/admin/tablas/portafolio/filas/{fila['id']}")
    a1 = _item(cliente, "A1")
    assert a1["elegida"]["cod_empresa"] == "2" and not a1["elegida_a_mano"]  # volvió a BETA, la más barata
    aviso = _aviso(cliente, "1 productos tienen elegido un proveedor que ya no los ofrece")
    assert "A1" in aviso["detalle"] and aviso["destinos"][0]["vista"] == "tablero"
    assert aviso["destinos"][0]["filtro"] == "elegidos"


def test_eliminar_varias_filas_juntas_es_un_solo_cambio_que_se_deshace_de_una_vez(cliente):
    """Eliminar 3 filas a la vez deja UN registro en el historial; deshacerlo las devuelve con sus mismos números."""
    ids = [f["id"] for f in _filas(cliente, "portafolio")["filas"][:3]]
    assert cliente.post("/api/admin/tablas/portafolio/filas/eliminar", json={"ids": ids}).json()["eliminadas"] == 3
    assert _filas(cliente, "portafolio")["total"] == 8
    historial = cliente.get("/api/admin/historial").json()
    assert historial[0]["accion"] == "eliminar_varias" and "3 filas" in historial[0]["resumen"]
    assert cliente.post(f"/api/admin/historial/{historial[0]['id']}/deshacer").status_code == 200
    despues = _filas(cliente, "portafolio")
    assert despues["total"] == 11 and [f["id"] for f in despues["filas"]][:3] == ids


# ------------------------------------------------------------------------------------------------ historial
def test_deshacer_agregar_editar_y_eliminar(cliente):
    """Cada tipo de cambio se puede deshacer, y solo una vez."""
    nueva = cliente.post(
        "/api/admin/tablas/empresas/filas", json={"valores": {"CODIGO_EMPRESA": "9", "NOMBRE": "NUEVA", **CONTACTO}}
    )
    nueva_id = nueva.json()["fila"]["id"]
    cliente.put(
        f"/api/admin/tablas/empresas/filas/{nueva_id}",
        json={"valores": {"CODIGO_EMPRESA": "9", "NOMBRE": "OTRA", **CONTACTO}},
    )
    cliente.delete(f"/api/admin/tablas/empresas/filas/{nueva_id}")
    h = cliente.get("/api/admin/historial", params={"tabla": "empresas"}).json()
    assert [x["accion"] for x in h[:3]] == ["eliminar_empresa", "editar", "agregar"] and all(x["se_puede"] for x in h[:3])

    def nombre():
        f = _fila(cliente, "empresas", CODIGO_EMPRESA="9")
        return f["valores"]["NOMBRE"] if f else None

    assert nombre() is None
    cliente.post(f"/api/admin/historial/{h[0]['id']}/deshacer")  # eliminar → vuelve, con su número y su nombre OTRA
    assert nombre() == "OTRA" and _fila(cliente, "empresas", CODIGO_EMPRESA="9")["id"] == nueva_id
    cliente.post(f"/api/admin/historial/{h[1]['id']}/deshacer")  # editar → vuelve NUEVA
    assert nombre() == "NUEVA"
    cliente.post(f"/api/admin/historial/{h[2]['id']}/deshacer")  # agregar → desaparece
    assert nombre() is None
    assert cliente.post(f"/api/admin/historial/{h[2]['id']}/deshacer").status_code == 409  # ya estaba deshecho
    # En el historial, lo deshecho queda marcado (y ya no se ofrece «Deshacer»).
    marcados = {c["id"]: c for c in cliente.get("/api/admin/historial", params={"tabla": "empresas"}).json()}
    assert all(marcados[h[i]["id"]]["deshecho"] and not marcados[h[i]["id"]]["se_puede"] for i in range(3))


def test_no_se_puede_deshacer_si_ya_hay_otra_fila_con_ese_numero(cliente):
    """Deshacer un «eliminar» no pisa nada: si el número de fila ya lo ocupa otra fila, avisa con un error claro."""
    from app.database import conectar

    a1 = _fila(cliente, "stock", COD_PRODUCTO="A1")
    cliente.delete(f"/api/admin/tablas/stock/filas/{a1['id']}")
    con = conectar()
    con.execute("INSERT INTO x_stock (id, COD_PRODUCTO, StockMax) VALUES (?, 'OCUPA', '1')", (a1["id"],))
    con.commit()
    con.close()
    cambio = cliente.get("/api/admin/historial").json()[0]
    r = cliente.post(f"/api/admin/historial/{cambio['id']}/deshacer")
    assert r.status_code == 409 and "otra fila" in r.json()["detail"]


# ------------------------------------------------------------------------------------------------ avisos → lugar
def test_cada_aviso_sabe_a_donde_llevar_al_usuario(cliente):
    """Los avisos traen botones «Ir a corregir»: la tabla, cuántas filas y, si aplica, qué valores poner al agregar."""
    sin_nombre = _aviso(cliente, "Proveedores sin nombre")["destinos"][0]
    assert sin_nombre["tabla"] == "empresas" and sin_nombre["cantidad"] == 1 and "filas" not in sin_nombre

    inferida = _aviso(cliente, "Proveedores con ofertas que no existen")["destinos"]
    assert inferida[0]["tabla"] == "empresas" and inferida[0]["agregar"] == {"CODIGO_EMPRESA": "5"}
    assert inferida[1]["tabla"] == "portafolio" and inferida[1]["cantidad"] == 1  # la fila «05»

    assert _aviso(cliente, "1 productos por comprar")["destinos"][0] == {
        "texto": "Ver estos productos en el tablero",
        "vista": "tablero",
        "filtro": "sin_oferta",
    }
    fuera = _aviso(cliente, "1 productos con ofertas no tienen stock definido")["destinos"]
    assert fuera[0]["tabla"] == "stock" and fuera[0]["agregar"]["COD_PRODUCTO"] == "X9"
    assert fuera[0]["agregar"]["DESCRIPCION"] == "x"


def test_las_filas_de_un_aviso_se_piden_por_su_clave(cliente):
    """La pantalla pide ?aviso=<clave>&destino=<n> y recibe SOLO las filas del problema (no viaja una lista enorme)."""
    aviso = _aviso(cliente, "Proveedores sin nombre")
    r = _filas(cliente, "empresas", aviso=aviso["clave"], destino=0)
    assert r["total"] == 1 and r["filas"][0]["valores"]["CODIGO_EMPRESA"] == "6"
    ignoradas = _aviso(cliente, "2 filas del portafolio se ignoraron")
    r = _filas(cliente, "portafolio", aviso=ignoradas["clave"], destino=0)
    assert {f["valores"]["COD_EMPRESA"] for f in r["filas"]} == {"6", "2"}  # las dos filas sin precio
    # También se puede buscar dentro de las filas del aviso.
    assert _filas(cliente, "portafolio", aviso=ignoradas["clave"], destino=0, q="C3")["total"] == 1


def test_un_aviso_de_otra_tabla_o_que_ya_no_existe_da_error_claro(cliente):
    """Pedir las filas de un aviso en la tabla equivocada (409) o de uno que ya se corrigió (404) da un mensaje claro."""
    aviso = _aviso(cliente, "Proveedores sin nombre")
    assert (
        cliente.get("/api/admin/tablas/stock/filas", params={"aviso": aviso["clave"], "destino": 0}).status_code == 409
    )
    r = cliente.get("/api/admin/tablas/empresas/filas", params={"aviso": "no_existe", "destino": 0})
    assert r.status_code == 404 and "ya no existe" in r.json()["detail"]
    # El aviso del tablero no lleva a una tabla: no tiene filas que mostrar.
    sin_oferta = _aviso(cliente, "1 productos por comprar")
    assert (
        cliente.get("/api/admin/tablas/stock/filas", params={"aviso": sin_oferta["clave"], "destino": 0}).status_code
        == 404
    )


def test_corregir_el_problema_hace_desaparecer_el_aviso(cliente):
    """Flujo completo: el aviso lleva a la fila, se le pone nombre al proveedor 6 y el aviso desaparece."""
    aviso = _aviso(cliente, "Proveedores sin nombre")
    fila = _filas(cliente, "empresas", aviso=aviso["clave"], destino=0)["filas"][0]
    cliente.put(
        f"/api/admin/tablas/empresas/filas/{fila['id']}",
        json={"valores": {"CODIGO_EMPRESA": "6", "NOMBRE": "EPSILON SAS", **CONTACTO}},
    )
    assert not any(t.startswith("Proveedores sin nombre") for t in _avisos(cliente))
    assert cliente.get("/api/empresas").json()  # y el proveedor ya se ve con su nombre
    assert any(e["nombre"] == "EPSILON SAS" for e in cliente.get("/api/empresas").json())


def test_la_clave_del_aviso_no_cambia_mientras_se_corrige(cliente):
    """El aviso se recalcula con cada edición, pero su clave es estable: el filtro sigue valiendo hasta que el problema
    desaparece de verdad (entonces da 404 y la pantalla avisa «¡Listo!»)."""
    a = _aviso(cliente, "1 productos por comprar")
    assert a["clave"] == "sin_oferta" and _aviso(cliente, "Proveedores sin nombre")["clave"] == "empresas_sin_nombre"
    cliente.post(
        "/api/admin/tablas/empresas/filas", json={"valores": {"CODIGO_EMPRESA": "9", "NOMBRE": "X", **CONTACTO}}
    )  # recalcula
    r = cliente.get("/api/admin/tablas/empresas/filas", params={"aviso": "empresas_sin_nombre", "destino": 0})
    assert r.status_code == 200 and r.json()["total"] == 1  # sigue funcionando
    fila = r.json()["filas"][0]
    cliente.put(
        f"/api/admin/tablas/empresas/filas/{fila['id']}",
        json={"valores": {"CODIGO_EMPRESA": "6", "NOMBRE": "Y", **CONTACTO}},
    )
    r = cliente.get("/api/admin/tablas/empresas/filas", params={"aviso": "empresas_sin_nombre", "destino": 0})
    assert r.status_code == 404 and "se corrigió" in r.json()["detail"]


def test_seleccionar_todas_las_filas_de_un_filtro_y_eliminarlas_juntas(cliente):
    """Para limpiar de una vez (por ejemplo las filas del portafolio sin precio) se piden los números de TODAS las filas
    del filtro, no solo de la página, y se eliminan juntas."""
    aviso = _aviso(cliente, "2 filas del portafolio se ignoraron")
    r = _filas(cliente, "portafolio", aviso=aviso["clave"], destino=0, tam=1, solo_ids=True)
    assert r["total"] == 2 and len(r["ids"]) == 2 and "filas" not in r
    assert _filas(cliente, "portafolio", q="C3", solo_ids=True)["total"] == 2
    cliente.post("/api/admin/tablas/portafolio/filas/eliminar", json={"ids": r["ids"]})
    assert _filas(cliente, "portafolio")["total"] == 9
    assert not any(titulo.endswith("filas del portafolio se ignoraron") for titulo in _avisos(cliente))


# ------------------------------------------------------------------------------------------------ importar por tabla
def test_importar_portafolio_agregando_con_un_precio_repetido_se_queda_con_el_mas_barato(cliente):
    """Si en el MISMO archivo un proveedor repite un producto, se queda el precio MÁS BARATO (no el último): da igual si el barato viene antes o después, y una fila
    sin precio (o con precio 0) nunca tapa a la que sí tiene. Antes ganaba la última y un precio repetido más caro tapaba al barato."""

    def fila(emp, cod, valor):
        return {"COD_EMPRESA": emp, "COD_PRODUCTO": cod, "DESCRIPCION": cod, "VALOR": valor, "PRESENTACION": "X1"}

    def valor(cod):
        return _fila(cliente, "portafolio", COD_PRODUCTO=cod)["valores"]["VALOR"]

    archivo = excel_bytes(
        [
            fila("9", "Z1", "30200"),
            fila("9", "Z1", "32900"),  # el barato va ANTES
            fila("9", "Z2", "5000"),
            fila("9", "Z2", "4000"),  # el barato va DESPUÉS
            fila("9", "Z3", "7000"),
            fila("9", "Z3", None),  # la fila sin precio no tapa
            fila("9", "Z4", "0"),
            fila("9", "Z4", "1800"),  # el 0 tampoco
            fila("9", "Z5", "800"),
            fila("9", "Z5", "800"),  # empate: se queda la primera (da igual: valen lo mismo)
            fila("9", "5929", "8000"),
            fila("09", "5929.0", "6000"),  # mismo proveedor y producto escritos distinto: son la MISMA oferta
        ]
    )
    r = cliente.post(
        "/api/admin/tablas/portafolio/importar", params={"nombre": "p.xlsx", "modo": "agregar"}, content=archivo
    )
    assert r.status_code == 200 and r.json()["tablas"][0]["repetidas_en_archivo"] == 6
    assert [valor(z) for z in ("Z1", "Z2", "Z3", "Z4", "Z5")] == ["30200", "4000", "7000", "1800", "800"]
    assert (
        valor("5929.0") == "6000"
    )  # ganó la segunda fila (la más barata), aunque el código venía con «.0» y el proveedor con un cero
    assert (
        _filas(cliente, "portafolio", q="5929")["total"] == 1
    )  # y no quedó la otra: una sola oferta por proveedor y producto


def test_importar_un_excel_agregando_actualiza_y_suma_sin_borrar(cliente):
    """Modo «agregar»: actualiza por código (A1 → 50), suma los nuevos, ignora filas sin código y NO borra nada."""
    archivo = excel_bytes(
        [
            {"COD_PRODUCTO": "A1", "DESCRIPCION": "x", "CANTIDAD": "50"},
            {"COD_PRODUCTO": "N1", "DESCRIPCION": "nuevo", "CANTIDAD": "7"},
            {"COD_PRODUCTO": "N1", "DESCRIPCION": "nuevo", "CANTIDAD": "8"},  # repetido en el archivo: gana la última
            {"COD_PRODUCTO": None, "DESCRIPCION": "sin código", "CANTIDAD": "3"},
        ]
    )
    r = cliente.post(
        "/api/admin/tablas/existencias/importar", params={"nombre": "e.xlsx", "modo": "agregar"}, content=archivo
    )
    assert r.status_code == 200
    t = r.json()["tablas"][0]
    assert (t["nuevos"], t["actualizados"], t["ignoradas"], t["repetidas_en_archivo"]) == (1, 1, 1, 1)
    assert _filas(cliente, "existencias")["total"] == 6  # 5 que había + N1: no se borró nada
    assert _fila(cliente, "existencias", COD_PRODUCTO="A1")["valores"]["CANTIDAD"] == "50"
    assert _fila(cliente, "existencias", COD_PRODUCTO="N1")["valores"]["CANTIDAD"] == "8"
    assert _item(cliente, "A1")["existencias"] == 50 and _item(cliente, "A1")["comprar"] == 50  # 100 − 50


def test_importar_un_excel_reemplazando_deja_la_tabla_igual_al_archivo(cliente):
    """Modo «reemplazar»: la tabla queda con SOLO las filas del archivo; las demás tablas no se tocan."""
    archivo = excel_bytes(
        [{"CODIGO_EMPRESA": "7", "NOMBRE": "SIETE SAS"}, {"CODIGO_EMPRESA": "8", "NOMBRE": "OCHO SAS"}]
    )
    r = cliente.post(
        "/api/admin/tablas/empresas/importar", params={"nombre": "e.xlsx", "modo": "reemplazar"}, content=archivo
    )
    assert r.status_code == 200 and r.json()["tablas"][0]["nuevos"] == 2
    assert [f["valores"]["NOMBRE"] for f in _filas(cliente, "empresas")["filas"]] == ["SIETE SAS", "OCHO SAS"]
    assert _filas(cliente, "portafolio")["total"] == 11 and _filas(cliente, "stock")["total"] == 6


def test_los_encabezados_del_archivo_se_reconocen_aunque_cambien(cliente):
    """«stock max», «Código» o «precio» se entienden y quedan guardados con el encabezado EXACTO de la tabla."""
    archivo = excel_bytes([{"codigo": "P1", "Descripción": "algo", "stock max": "12", "STOCK_MIN": "3"}])
    r = cliente.post(
        "/api/admin/tablas/stock/importar", params={"nombre": "s.xlsx", "modo": "agregar"}, content=archivo
    )
    assert r.status_code == 200
    assert _fila(cliente, "stock", COD_PRODUCTO="P1")["valores"] == {
        "COD_PRODUCTO": "P1",
        "DESCRIPCION": "algo",
        "StockMax": "12",
        "StockMed": None,
        "StockMin": "3",
    }


def test_un_archivo_al_que_le_falta_una_columna_da_error_claro_y_no_cambia_nada(cliente):
    """Sin la columna VALOR el portafolio no sirve: error 422 que dice cuál falta, y la tabla queda intacta."""
    archivo = excel_bytes([{"COD_EMPRESA": "1", "COD_PRODUCTO": "A1"}])
    r = cliente.post(
        "/api/admin/tablas/portafolio/importar", params={"nombre": "p.xlsx", "modo": "reemplazar"}, content=archivo
    )
    assert r.status_code == 422 and "VALOR" in r.json()["detail"] and "faltan las columnas" in r.json()["detail"]
    assert _filas(cliente, "portafolio")["total"] == 11
    assert (
        cliente.post("/api/admin/tablas/stock/importar", params={"nombre": "x.txt"}, content=b"hola").status_code == 422
    )
    assert cliente.post("/api/admin/tablas/stock/importar", params={"nombre": "x.xlsx"}, content=b"").status_code == 422


def test_importar_desde_la_carpeta_solo_toca_las_tablas_elegidas(cliente):
    """«Reemplazar» EMPRESA desde la carpeta pierde las ediciones de Empresas, pero las de Stock se quedan."""
    beta = _fila(cliente, "empresas", CODIGO_EMPRESA="2")
    cliente.put(
        f"/api/admin/tablas/empresas/filas/{beta['id']}", json={"valores": {"CODIGO_EMPRESA": "2", "NOMBRE": "EDITADA"}}
    )
    a1 = _fila(cliente, "stock", COD_PRODUCTO="A1")
    cliente.put(f"/api/admin/tablas/stock/filas/{a1['id']}", json={"valores": {**a1["valores"], "StockMax": "300"}})

    r = cliente.post("/api/admin/importar", json={"tablas": ["empresas"], "modo": "reemplazar"})
    assert r.status_code == 200 and [t["tabla"] for t in r.json()["tablas"]] == ["empresas"]
    assert _fila(cliente, "empresas", CODIGO_EMPRESA="2")["valores"]["NOMBRE"] == "BETA SAS"  # volvió al Excel
    assert _fila(cliente, "stock", COD_PRODUCTO="A1")["valores"]["StockMax"] == "300"  # esta edición sigue ahí


def test_importar_desde_la_carpeta_agregando_respeta_lo_editado_en_otras_filas(cliente):
    """«Agregar» desde la carpeta actualiza las filas que existen (por código), así que pisa la edición de ESA fila,
    pero no toca las filas que el Excel no trae ni borra las que agregaste a mano."""
    cliente.post(
        "/api/admin/tablas/empresas/filas", json={"valores": {"CODIGO_EMPRESA": "9", "NOMBRE": "MIA", **CONTACTO}}
    )
    r = cliente.post("/api/admin/importar", json={"tablas": ["empresas"], "modo": "agregar"}).json()["tablas"][0]
    assert r["nuevos"] == 0 and r["sin_cambios"] == 5  # lo del Excel ya estaba
    assert _fila(cliente, "empresas", CODIGO_EMPRESA="9")["valores"]["NOMBRE"] == "MIA"  # no se borró


def test_deshacer_una_importacion_devuelve_la_tabla_como_estaba(cliente):
    """Importar guarda una copia: deshacer la importación restaura la tabla completa, con sus números de fila."""
    antes = _filas(cliente, "empresas")["filas"]
    archivo = excel_bytes([{"CODIGO_EMPRESA": "7", "NOMBRE": "SIETE SAS"}])
    cliente.post(
        "/api/admin/tablas/empresas/importar", params={"nombre": "e.xlsx", "modo": "reemplazar"}, content=archivo
    )
    assert _filas(cliente, "empresas")["total"] == 1
    cambio = next(c for c in cliente.get("/api/admin/historial").json() if c["accion"] == "importar")
    assert cambio["tabla"] == "empresas" and "Reemplazó" in cambio["resumen"] and cambio["se_puede"]
    assert cliente.post(f"/api/admin/historial/{cambio['id']}/deshacer").status_code == 200
    assert _filas(cliente, "empresas")["filas"] == antes


def test_el_historial_recuerda_solo_las_ultimas_copias(cliente):
    """Para no crecer sin fin, solo las 5 importaciones más recientes conservan copia; las viejas ya no se deshacen."""
    from app.services import historial

    archivo = excel_bytes([{"CODIGO_EMPRESA": "7", "NOMBRE": "SIETE SAS"}])
    for _ in range(historial.MAX_COPIAS + 2):
        cliente.post(
            "/api/admin/tablas/empresas/importar", params={"nombre": "e.xlsx", "modo": "reemplazar"}, content=archivo
        )
    importaciones = [
        c for c in cliente.get("/api/admin/historial", params={"tabla": "empresas"}).json() if c["accion"] == "importar"
    ]
    assert sum(c["se_puede"] for c in importaciones) == historial.MAX_COPIAS
    vieja = next(c for c in importaciones if not c["se_puede"])
    assert "sin copia" in vieja["resumen"]
    assert cliente.post(f"/api/admin/historial/{vieja['id']}/deshacer").status_code == 409


# ------------------------------------------------------------------------------------------------ Excel y arranque
def test_descargar_una_tabla_como_excel_conserva_encabezados_y_codigos(cliente):
    """El Excel descargado tiene los mismos encabezados, el nombre de hoja original, números como números y los
    códigos como texto (el «0041» conserva su cero)."""
    r = cliente.get("/api/admin/tablas/stock/excel")
    assert r.status_code == 200 and 'filename="05-STOCK.xlsx"' in r.headers["content-disposition"]
    hoja = load_workbook(io.BytesIO(r.content)).active
    assert hoja.title == "_05_STOCK"
    filas = list(hoja.values)
    assert list(filas[0]) == ENCABEZADOS["stock"] and len(filas) == 7
    cuarentayuno = next(f for f in filas[1:] if f[1] == "AGUJA ÑANDÚ")
    assert cuarentayuno[0] == "0041" and cuarentayuno[2] == 10  # código como texto, StockMax como número


def test_las_ediciones_no_se_pierden_al_reiniciar_la_aplicacion(cliente):
    """Después de la primera carga, los Excel NUNCA se vuelven a leer solos: aunque se vacíe una tabla a propósito,
    al reiniciar sigue vacía (así lo editado en Administración no se pierde)."""
    from app.main import app

    ids = [f["id"] for f in _filas(cliente, "empresas")["filas"]]
    cliente.post("/api/admin/tablas/empresas/filas/eliminar", json={"ids": ids})
    assert _filas(cliente, "empresas")["total"] == 0
    with TestClient(app) as reiniciada:  # arranca de nuevo con la MISMA base de datos
        entrar(reiniciada, "admin", CLAVE_ADMIN)  # un cliente nuevo no trae la sesión del anterior
        assert reiniciada.get("/api/admin/tablas/empresas/filas").json()["total"] == 0
        assert reiniciada.get("/api/admin/tablas/stock/filas").json()["total"] == 6


def test_una_base_de_una_version_anterior_recibe_las_tablas_al_arrancar(cliente):
    """Una base creada antes de existir la administración (tablas de trabajo llenas, tablas de los Excel vacías y sin
    marca de «ya importado») se pone al día sola al arrancar, conservando lo que el usuario hizo a mano."""
    from app.database import conectar
    from app.main import app

    cliente.post("/api/ofertas", json={"cod_producto": "D4", "empresa_nueva": "MANUAL SAS", "valor": 9})
    con = conectar()
    for tabla in ("x_stock", "x_existencias", "x_empresas", "x_ficha", "x_portafolio"):
        con.execute(f"DELETE FROM {tabla}")
    con.execute("DELETE FROM meta WHERE clave = 'crudas_iniciadas'")
    con.commit()
    con.close()
    with TestClient(app) as c:
        entrar(c, "admin", CLAVE_ADMIN)
        assert c.get("/api/admin/tablas/stock/filas").json()["total"] == 6
        assert _item(c, "D4")["mejor"]["empresa"] == "MANUAL SAS"  # lo hecho a mano se conservó


def test_lo_hecho_a_mano_sobrevive_a_los_cambios_de_la_administracion(cliente):
    """Las ofertas y proveedores creados en «Agregar oferta» no se borran cuando se edita o se elimina en las tablas."""
    cliente.post("/api/ofertas", json={"cod_producto": "D4", "empresa_nueva": "MANUAL SAS", "valor": 9})
    a1 = _fila(cliente, "stock", COD_PRODUCTO="A1")
    cliente.delete(f"/api/admin/tablas/stock/filas/{a1['id']}")
    assert _item(cliente, "D4")["mejor"]["empresa"] == "MANUAL SAS"
    assert any(e["nombre"] == "MANUAL SAS" for e in cliente.get("/api/empresas").json())


def test_cada_excel_dice_para_que_sirve_y_si_el_sistema_lo_necesita(cliente, como):
    """La pantalla le pide por nombre al usuario los Excel que el sistema NECESITA: por eso cada tabla trae su nombre de archivo, para qué sirve y si es
    obligatoria. Son 4 obligatorias (stock, existencias, empresas y portafolio) y 1 opcional (la ficha de cotización)."""
    r = como("prime").get("/api/admin/tablas")  # Prime también ve la lista (es quien sube los Excel)
    assert r.status_code == 200
    tablas = {x["clave"]: x for x in r.json()}
    assert {k for k, x in tablas.items() if x["necesaria"]} == {"stock", "existencias", "empresas", "portafolio"}
    assert tablas["ficha"]["necesaria"] is False
    assert all(
        len(x["para_que"]) > 40 and x["archivo"].endswith(".xlsx") for x in tablas.values()
    )  # cada una explica para qué sirve
    assert como("consulta").get("/api/admin/tablas").status_code == 403  # y Consulta no (no sube nada)
