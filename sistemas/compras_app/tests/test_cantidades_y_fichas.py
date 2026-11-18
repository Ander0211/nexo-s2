"""CANTIDAD A COMPRAR EDITABLE, FICHA DE LA EMPRESA, Y OFERTAS / USUARIOS SIN REPETIR.

Sobre los datos sintéticos de conftest.py (ver su mapa de datos). Cuentas que se usan aquí:
  A1   stock 100, existencias 20 → se calcula comprar 80.  Ranking: BETA $85 · GAMA $95 · ALFA $100 · DELTA $120 · prov. 5 $130
  C3   comprar 5, solo ALFA ($50)        0041   comprar 6, solo ALFA ($7)        D4   comprar 5, nadie lo ofrece
  B2   no hay que comprarlo (0)
  Sin editar nada: inversión = 85×80 + 50×5 + 7×6 = 7.092 y ahorro = (95−85)×80 = 800.
"""

from io import BytesIO

from openpyxl import load_workbook

from app import database
from tests.conftest import CLAVE_ADMIN, entrar
from tests.test_admin import CONTACTO, _fila


def _item(c, cod):
    return next(
        i for i in c.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"] if i["cod"] == cod
    )


def _filas_excel(c, ruta):
    r = c.get(ruta)
    assert r.status_code == 200, r.text
    return list(load_workbook(BytesIO(r.content)).active.values)


def _sql(consulta, *params):
    con = database.conectar()
    try:
        filas = con.execute(consulta, params).fetchall()
        con.commit()
        return filas
    finally:
        con.close()


# ================================================================================================ cantidad editable
def test_por_defecto_la_cantidad_es_la_calculada(cliente):
    a1 = _item(cliente, "A1")
    assert (a1["comprar"], a1["calculada"], a1["editada"]) == (80, 80, False)
    r = cliente.get("/api/resumen").json()
    assert r["inversion_total"] == 7092 and r["ahorro_total"] == 800 and r["por_comprar"] == 4


def test_editar_la_cantidad_cambia_el_total_los_indicadores_y_el_podio(cliente):
    r = cliente.put("/api/productos/A1/cantidad", json={"cantidad": 100})
    assert r.status_code == 200
    assert {k: r.json()[k] for k in ("cod", "comprar", "calculada", "editada")} == {
        "cod": "A1",
        "comprar": 100,
        "calculada": 80,
        "editada": True,
    }
    # la respuesta trae la fila ya recalculada: la pantalla la cambia en su sitio sin volver a ordenar la lista
    assert r.json()["item"] == next(
        i
        for i in cliente.get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"]
        if i["cod"] == "A1"
    )
    a1 = _item(cliente, "A1")
    assert (a1["comprar"], a1["calculada"], a1["editada"]) == (100, 80, True)
    assert a1["total"] == 8500 and a1["ahorro"] == 1000  # $85 × 100 y (95 − 85) × 100
    resumen = cliente.get("/api/resumen").json()
    assert resumen["inversion_total"] == 7092 - 6800 + 8500 and resumen["ahorro_total"] == 1000
    podio = cliente.get("/api/productos/A1/ofertas").json()
    assert (podio["comprar"], podio["calculada"], podio["editada"]) == (100, 80, True)
    assert podio["ofertas"][0]["total"] == 8500  # el total de cada oferta usa la cantidad editada


def test_la_cantidad_editada_llega_a_las_exportaciones(cliente):
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 100})
    valores = {f[0]: f for f in _filas_excel(cliente, "/api/exportar/oc")[1:]}
    assert valores["A1"][2] == 100  # CANT_COMPRAR
    por_comprar = {f[0]: f for f in _filas_excel(cliente, "/api/exportar/productos-a-comprar")[1:]}
    assert por_comprar["A1"][4] == 100 and por_comprar["A1"][7] == 8500  # CANT_COMPRAR y TOTAL


def test_restaurar_vuelve_a_la_cantidad_calculada(cliente):
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 100})
    r = cliente.delete("/api/productos/A1/cantidad")
    assert r.status_code == 200
    assert {k: r.json()[k] for k in ("cod", "comprar", "calculada", "editada")} == {
        "cod": "A1",
        "comprar": 80,
        "calculada": 80,
        "editada": False,
    }
    assert r.json()["item"]["comprar"] == 80 and r.json()["item"]["editada"] is False
    a1 = _item(cliente, "A1")
    assert (a1["comprar"], a1["editada"], a1["total"]) == (80, False, 6800)
    assert cliente.delete("/api/productos/A1/cantidad").status_code == 200  # restaurar sin edición no falla


def test_la_cantidad_editada_dura_hasta_que_se_restaure(cliente):
    """Ni cambiar las existencias, ni recalcular, ni «Actualizar Excel» la borran: es una decisión del usuario."""
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 100})
    existencias = _fila(cliente, "existencias", COD_PRODUCTO="A1")
    cliente.put(
        f"/api/admin/tablas/existencias/filas/{existencias['id']}",
        json={"valores": {**existencias["valores"], "CANTIDAD": "50"}},
    )
    a1 = _item(cliente, "A1")
    assert (a1["calculada"], a1["comprar"], a1["editada"]) == (50, 100, True)  # lo calculado cambió; lo editado no
    assert (
        cliente.post("/api/admin/importar", json={"tablas": ["existencias", "stock"], "modo": "reemplazar"}).status_code
        == 200
    )
    a1 = _item(cliente, "A1")
    assert (a1["calculada"], a1["comprar"], a1["editada"]) == (80, 100, True)  # el Excel volvió a 20, y sigue en 100


def test_editar_la_cantidad_NO_toca_el_stock_ni_el_maximo_ni_las_tablas(cliente):
    """La cantidad a comprar es SOLO cuántas unidades se van a comprar según la necesidad: ni el stock máximo, ni las existencias, ni el nivel de
    la barra de stock, ni las 5 tablas de los Excel, ni el historial de Administración cambian, ponga lo que se ponga (incluso más de lo que falta
    para llegar al máximo, o 0)."""

    def foto():
        filas = {
            t: [tuple(f) for f in _sql(f"SELECT * FROM {t} ORDER BY id")]
            for t in ("x_stock", "x_existencias", "x_empresas", "x_ficha", "x_portafolio")
        }
        productos = [
            tuple(f)
            for f in _sql(
                "SELECT cod, descripcion, stock_max, stock_med, stock_min, existencias, en_stock, origen FROM productos ORDER BY cod"
            )
        ]
        a1 = _item(cliente, "A1")
        barra = {k: a1[k] for k in ("stock_max", "stock_min", "existencias", "nivel_stock", "en_stock")}
        return filas, productos, barra, _sql("SELECT COUNT(*) FROM cambios")[0][0]

    antes = foto()
    assert antes[2]["stock_max"] == 100 and antes[2]["existencias"] == 20
    for cantidad in (250, 0, 999_999, 7):  # más de lo que falta (80), nada, muchísimo y poco
        assert cliente.put("/api/productos/A1/cantidad", json={"cantidad": cantidad}).status_code == 200
        assert foto() == antes, cantidad
    assert cliente.delete("/api/productos/A1/cantidad").status_code == 200
    assert foto() == antes
    # tampoco al ver el producto: sigue «20 en stock · máx 100» con cualquier cantidad
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 5000})
    a1 = _item(cliente, "A1")
    assert (a1["existencias"], a1["stock_max"], a1["comprar"], a1["calculada"]) == (20, 100, 5000, 80)


def test_editar_a_cero_saca_el_producto_de_por_comprar(cliente):
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 0})
    por_comprar = cliente.get("/api/productos", params={"filtro": "por_comprar", "tam": 100}).json()
    assert "A1" not in {i["cod"] for i in por_comprar["items"]} and por_comprar["total"] == 3
    assert cliente.get("/api/resumen").json()["inversion_total"] == 7092 - 6800
    assert "A1" not in {f[0] for f in _filas_excel(cliente, "/api/exportar/oc")[1:]}


def test_un_producto_que_no_habia_que_comprar_se_puede_comprar(cliente):
    """B2 está completo (0 por comprar). Si alguien decide comprar 12, aparece en «por comprar» y, al no tener oferta, en el aviso."""
    assert _item(cliente, "B2")["comprar"] == 0
    cliente.put("/api/productos/B2/cantidad", json={"cantidad": 12})
    b2 = _item(cliente, "B2")
    assert (b2["comprar"], b2["calculada"], b2["editada"]) == (12, 0, True)
    por_comprar = cliente.get("/api/productos", params={"filtro": "por_comprar", "tam": 100}).json()
    assert "B2" in {i["cod"] for i in por_comprar["items"]}
    sin_oferta = cliente.get("/api/productos", params={"filtro": "sin_oferta", "tam": 100}).json()
    assert {i["cod"] for i in sin_oferta["items"]} == {"B2", "D4"}
    # el aviso «productos por comprar sin oferta» también lo cuenta (se recalcula con cualquier cambio de datos)
    existencias = _fila(cliente, "existencias", COD_PRODUCTO="B2")
    cliente.put(
        f"/api/admin/tablas/existencias/filas/{existencias['id']}",
        json={"valores": {**existencias["valores"], "CANTIDAD": "10"}},
    )
    aviso = next(a for a in cliente.get("/api/avisos").json() if a["clave"] == "sin_oferta")
    assert "B2" in aviso["detalle"] and "D4" in aviso["detalle"]


def test_la_cantidad_debe_ser_un_entero_desde_cero(cliente):
    for malo in (-1, 1.5, "abc", 10_000_001, None):
        r = cliente.put("/api/productos/A1/cantidad", json={"cantidad": malo})
        assert r.status_code == 422, (malo, r.text)
    assert cliente.put("/api/productos/A1/cantidad", json={}).status_code == 422
    assert _item(cliente, "A1")["editada"] is False  # nada quedó guardado
    assert cliente.put("/api/productos/A1/cantidad", json={"cantidad": 10_000_000}).status_code == 200  # el máximo


def test_un_producto_inexistente_da_404(cliente):
    assert cliente.put("/api/productos/NOEXISTE/cantidad", json={"cantidad": 3}).status_code == 404
    assert cliente.delete("/api/productos/NOEXISTE/cantidad").status_code == 404


def test_quien_puede_editar_la_cantidad(cliente, como, anonimo):
    cuerpo = {"cantidad": 7}
    assert como("prime").put("/api/productos/A1/cantidad", json=cuerpo).status_code == 200
    assert como("prime").delete("/api/productos/A1/cantidad").status_code == 200
    for perfil in ("consulta", "externo"):
        c = como(perfil)
        assert c.put("/api/productos/A1/cantidad", json=cuerpo).status_code == 403, perfil
        assert c.delete("/api/productos/A1/cantidad").status_code == 403, perfil
    assert anonimo.put("/api/productos/A1/cantidad", json=cuerpo).status_code == 401
    # el perfil Consulta ve la cantidad editada, aunque no pueda cambiarla
    cliente.put("/api/productos/A1/cantidad", json=cuerpo)
    a1 = next(
        i
        for i in como("consulta").get("/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"]
        if i["cod"] == "A1"
    )
    assert (a1["comprar"], a1["editada"]) == (7, True)


def test_se_anota_quien_edito_la_cantidad(cliente, como):
    como("prime").put("/api/productos/A1/cantidad", json={"cantidad": 9})
    assert [tuple(f) for f in _sql("SELECT cantidad, usuario FROM cantidades WHERE cod_producto = 'A1'")] == [
        (9, "prime1")
    ]
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 11})  # editar de nuevo no duplica la fila
    assert [tuple(f) for f in _sql("SELECT cantidad, usuario FROM cantidades")] == [(11, "admin")]


def test_al_eliminar_un_producto_propio_se_va_su_cantidad_editada(cliente):
    cliente.post("/api/productos", json={"cod": "M1", "descripcion": "PROPIO", "stock_max": 10, "existencias": 0})
    cliente.put("/api/productos/M1/cantidad", json={"cantidad": 3})
    assert _sql("SELECT COUNT(*) FROM cantidades")[0][0] == 1
    assert cliente.delete("/api/productos/M1").status_code in (200, 204)
    assert _sql("SELECT COUNT(*) FROM cantidades")[0][0] == 0


def test_el_proveedor_externo_ve_los_productos_segun_la_cantidad_vigente(cliente, como):
    externo = como("externo")
    antes = {i["cod"] for i in externo.get("/api/proveedor/productos", params={"tam": 100}).json()["items"]}
    assert antes == {"A1", "C3", "D4", "0041"}
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 0})
    cliente.put("/api/productos/B2/cantidad", json={"cantidad": 4})
    ahora = {i["cod"] for i in externo.get("/api/proveedor/productos", params={"tam": 100}).json()["items"]}
    assert ahora == {"B2", "C3", "D4", "0041"}  # A1 ya no se compra; B2 sí (y sigue sin mostrar cantidades)
    assert all(set(i) == {"cod", "descripcion"} for i in externo.get("/api/proveedor/productos").json()["items"])


# ================================================================================================ ficha de la empresa
def _ficha(c, cod):
    r = c.get(f"/api/empresas/{cod}/ficha")
    assert r.status_code == 200, r.text
    return r.json()


def test_ficha_de_una_empresa_del_excel(cliente):
    f = _ficha(cliente, "1")
    assert (f["cod"], f["nombre"], f["origen"], f["origen_texto"]) == ("1", "ALFA SAS", "excel", "Excel base")
    assert f["telefono"] is None and f["correo"] is None  # las del Excel base no traen contacto
    # ALFA ofrece A1 ($100, 3.ª de 5), C3 ($50) y 0041 ($7): es la mejor en C3 y 0041, y se le compraría C3 y 0041
    assert (f["n_ofertas"], f["n_mejores"], f["n_elegidas"], f["inversion"]) == (3, 2, 2, 5 * 50 + 6 * 7)
    primeras = [o["cod_producto"] for o in f["ofertas"]]
    assert primeras == ["0041", "C3", "A1"]  # primero los que se le compran (A–Z), luego el resto
    a1 = next(o for o in f["ofertas"] if o["cod_producto"] == "A1")
    assert (a1["valor"], a1["puesto"], a1["n_ofertas"], a1["es_mejor"], a1["es_elegida"]) == (100, 3, 5, False, False)
    assert a1["comprar"] == 80 and a1["total"] == 8000
    c3 = next(o for o in f["ofertas"] if o["cod_producto"] == "C3")
    assert (c3["puesto"], c3["es_mejor"], c3["es_elegida"], c3["total"], c3["presentacion"]) == (
        1,
        True,
        True,
        250,
        "X1",
    )


def test_la_ficha_muestra_el_telefono_y_el_correo_de_administracion(cliente):
    alfa = _fila(cliente, "empresas", CODIGO_EMPRESA="1")
    cliente.put(
        f"/api/admin/tablas/empresas/filas/{alfa['id']}",
        json={"valores": {"CODIGO_EMPRESA": "1", "NOMBRE": "ALFA SAS", **CONTACTO}},
    )
    f = _ficha(cliente, "1")
    assert f["telefono"] == "+573001234567" and f["correo"] == "contacto@empresa.com"
    assert _ficha(cliente, "01")["nombre"] == "ALFA SAS"  # «01» es la empresa 1


def test_la_ficha_cuenta_el_proveedor_elegido_a_mano_y_la_cantidad_editada(cliente):
    cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "1"})  # se le comprará A1 a ALFA ($100 × 80)
    f = _ficha(cliente, "1")
    assert (f["n_elegidas"], f["inversion"]) == (3, 8000 + 250 + 42)
    assert next(o for o in f["ofertas"] if o["cod_producto"] == "A1")["es_elegida"] is True
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 10})
    assert _ficha(cliente, "1")["inversion"] == 1000 + 250 + 42  # la cantidad editada cuenta
    cliente.put("/api/productos/A1/cantidad", json={"cantidad": 0})  # si ya no se compra, no cuenta como elegida
    f = _ficha(cliente, "1")
    assert f["n_elegidas"] == 2 and f["inversion"] == 292
    assert _ficha(cliente, "2")["n_elegidas"] == 0  # y BETA ya no se lleva A1


def test_la_ficha_no_repite_un_producto_si_la_empresa_lo_ofrecia_dos_veces(cliente):
    """BETA ofrecía A1 a $90 y a $85 (repetida en el Excel): en la ficha cuenta una sola vez, con la más barata."""
    f = _ficha(cliente, "2")
    assert [o["cod_producto"] for o in f["ofertas"]] == ["A1"] and f["ofertas"][0]["valor"] == 85
    assert (f["n_ofertas"], f["n_mejores"], f["n_elegidas"], f["inversion"]) == (1, 1, 1, 6800)


def test_la_ficha_de_empresas_propias_e_inferidas(cliente):
    cinco = _ficha(cliente, "5")
    assert cinco["nombre"].startswith("Proveedor 5") and cinco["origen"] == "inferida" and cinco["telefono"] is None
    assert "EMPRESA.xlsx" in cinco["origen_texto"] and cinco["n_ofertas"] == 1
    nueva = cliente.post("/api/empresas", json={"nombre": "MANUAL SAS"}).json()
    f = _ficha(cliente, nueva["cod"])
    assert (f["origen"], f["telefono"], f["correo"], f["n_ofertas"], f["ofertas"]) == ("manual", None, None, 0, [])


def test_ficha_de_una_empresa_inexistente_da_404(cliente):
    assert cliente.get("/api/empresas/999/ficha").status_code == 404


def test_quien_puede_ver_la_ficha(como, anonimo):
    for perfil in ("prime", "consulta"):  # todo el que ve el tablero, incluida Consulta
        assert como(perfil).get("/api/empresas/1/ficha").status_code == 200, perfil
    assert como("externo").get("/api/empresas/1/ficha").status_code == 403  # el proveedor no ve a los demás
    assert anonimo.get("/api/empresas/1/ficha").status_code == 401


# ================================================================================================ ofertas sin repetir
def _oferta(c, **datos):
    return c.post("/api/ofertas", json={"cod_producto": "A1", "valor": 80, **datos})


def test_no_se_agrega_una_oferta_manual_si_la_empresa_ya_tiene_una_del_excel(cliente):
    antes = cliente.get("/api/productos/A1/ofertas").json()["total_ofertas"]
    r = _oferta(cliente, cod_empresa="1")  # ALFA ya ofrece A1 a $100 en el Excel base
    assert r.status_code == 409
    d = r.json()["detail"]
    assert "ya tiene una oferta" in d and "$100" in d and "Excel base" in d and "Administración → Portafolio" in d
    # escribir el nombre de una empresa que existe es lo mismo que elegirla: tampoco se repite
    assert _oferta(cliente, empresa_nueva="alfa sas").status_code == 409
    assert cliente.get("/api/productos/A1/ofertas").json()["total_ofertas"] == antes  # no se agregó nada


def test_no_se_agrega_una_oferta_manual_si_la_empresa_ya_tiene_una_subida_desde_un_excel(cliente):
    _sql("INSERT INTO ofertas (cod_producto, cod_empresa, valor, origen) VALUES ('C3', '3', 77, 'subido')")
    r = cliente.post("/api/ofertas", json={"cod_producto": "C3", "cod_empresa": "3", "valor": 60})
    assert r.status_code == 409 and "subida desde un Excel" in r.json()["detail"] and "papelera" in r.json()["detail"]


def test_la_oferta_manual_de_la_misma_empresa_se_actualiza_no_se_repite(cliente):
    primera = _oferta(cliente, empresa_nueva="ZETA SAS", valor=80)
    assert primera.status_code == 201 and primera.json()["proveedor_nuevo"] is True
    total = cliente.get("/api/productos/A1/ofertas").json()["total_ofertas"]
    segunda = _oferta(cliente, empresa_nueva="zeta sas", valor=70)  # mismo proveedor y producto: cambia el precio
    assert segunda.status_code == 201 and segunda.json()["actualizada"] is True
    assert segunda.json()["id"] == primera.json()["id"] and segunda.json()["proveedor_nuevo"] is False
    assert cliente.get("/api/productos/A1/ofertas").json()["total_ofertas"] == total  # sigue habiendo una sola de ZETA


def test_un_fallo_por_repetida_no_deja_empresas_nuevas_a_medias(cliente):
    n = len(cliente.get("/api/empresas").json())
    assert _oferta(cliente, cod_empresa="1").status_code == 409
    assert len(cliente.get("/api/empresas").json()) == n


# ================================================================================================ usuarios sin repetir
def _usuario(usuario, **extra):
    return {
        "usuario": usuario,
        "nombre": usuario.title(),
        "rol": "consulta",
        "correo": f"{usuario}@x.com",
        "celular": "3201111111",
        **extra,
    }


def test_dos_usuarios_no_pueden_tener_el_mismo_correo_ni_el_mismo_celular(cliente):
    assert cliente.post("/api/usuarios", json=_usuario("ana")).status_code == 201
    r = cliente.post(
        "/api/usuarios", json=_usuario("beto", correo="ANA@x.com", celular="3202222222")
    )  # mismo correo, en mayúsculas
    assert r.status_code == 409 and "correo" in r.json()["detail"] and "«ana»" in r.json()["detail"]
    for celular in ("3201111111", "320 111 1111", "+57 320 111 1111"):  # el mismo celular escrito de distintas formas
        r = cliente.post("/api/usuarios", json=_usuario("beto", celular=celular))
        assert r.status_code == 409 and "celular" in r.json()["detail"], celular
    assert "beto" not in [u["usuario"] for u in cliente.get("/api/usuarios").json()["usuarios"]]
    assert cliente.post("/api/usuarios", json=_usuario("beto", celular="3202222222")).status_code == 201


def test_editar_un_usuario_tampoco_puede_quitarle_el_contacto_a_otro(cliente):
    ana = cliente.post("/api/usuarios", json=_usuario("ana")).json()["usuario"]
    beto = cliente.post("/api/usuarios", json=_usuario("beto", celular="3202222222")).json()["usuario"]
    cuerpo = {"nombre": "Beto", "rol": "consulta", "activo": True, "correo": "beto@x.com", "celular": "3202222222"}
    assert cliente.put(f"/api/usuarios/{beto['id']}", json={**cuerpo, "correo": "ana@x.com"}).status_code == 409
    assert cliente.put(f"/api/usuarios/{beto['id']}", json={**cuerpo, "celular": "3201111111"}).status_code == 409
    assert (
        cliente.put(f"/api/usuarios/{beto['id']}", json={**cuerpo, "nombre": "Beto Pérez"}).status_code == 200
    )  # su propio contacto
    assert ana["correo"] == "ana@x.com"


def test_un_contacto_que_ya_estaba_repetido_no_impide_seguir_editando(cliente):
    """Si de antes hay dos personas con el mismo celular, se puede cambiar el nombre o el perfil de cualquiera de ellas."""
    ana = cliente.post("/api/usuarios", json=_usuario("ana")).json()["usuario"]
    beto = cliente.post("/api/usuarios", json=_usuario("beto", celular="3202222222")).json()["usuario"]
    _sql("UPDATE usuarios SET celular = '+573201111111' WHERE usuario = 'beto'")  # repetido «de antes»
    cuerpo = {
        "nombre": "Beto Pérez",
        "rol": "prime",
        "activo": True,
        "correo": "beto@x.com",
        "celular": "+573201111111",
    }
    assert cliente.put(f"/api/usuarios/{beto['id']}", json=cuerpo).status_code == 200
    assert ana["id"] != beto["id"]


def test_el_administrador_actual_no_choca_consigo_mismo(cliente):
    me = cliente.get("/api/sesion").json()["usuario"]
    cuerpo = {
        "nombre": "Administrador",
        "rol": "admin",
        "activo": True,
        "correo": "admin@clinica.com",
        "celular": "3109999999",
    }
    assert cliente.put(f"/api/usuarios/{me['id']}", json=cuerpo).status_code == 200
    assert (
        cliente.put(f"/api/usuarios/{me['id']}", json={**cuerpo, "nombre": "Jefe"}).status_code == 200
    )  # mismo contacto otra vez
    assert entrar(cliente, "admin", CLAVE_ADMIN).status_code == 200
