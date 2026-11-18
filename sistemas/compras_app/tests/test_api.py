"""API completa con datos sintéticos (ver conftest.py)."""

import io

from openpyxl import load_workbook


def _listar(c, **p):
    """Atajo: pide la lista de productos con los filtros dados y devuelve la respuesta como diccionario."""
    return c.get("/api/productos", params=p).json()


def test_importacion_y_resumen(cliente):
    """Al arrancar se importan los Excel y el resumen cuenta bien: 4 por comprar, 3 con oferta, 1 sin oferta, 7 productos."""
    r = cliente.get("/api/resumen").json()
    assert r["por_comprar"] == 4  # A1, C3, D4 y 0041
    assert r["con_oferta"] == 3 and r["sin_oferta"] == 1  # D4 no tiene ofertas
    assert r["productos"] == 7  # 6 en stock + X9 (solo ficha/portafolio)
    assert r["conteos"]["todos"] == 7


def test_listado_por_comprar_ordenado_por_inversion(cliente):
    """La lista por defecto trae solo lo que hay que comprar, del mayor total al menor, y los productos sin oferta al final."""
    d = _listar(cliente)
    assert [i["cod"] for i in d["items"]] == ["A1", "C3", "0041", "D4"]
    a1 = d["items"][0]
    assert a1["comprar"] == 80 and a1["mejor"]["empresa"] == "BETA SAS" and a1["mejor"]["valor"] == 85
    assert a1["total"] == 85 * 80 and a1["n_ofertas"] == 5
    assert a1["ahorro"] == (95 - 85) * 80  # diferencia con la 2.ª oferta x cantidad
    assert d["items"][-1]["mejor"] is None  # sin oferta al final


def test_busqueda_ignora_tildes_y_mayusculas(cliente):
    """Buscar «nandu» encuentra «ÑANDÚ»; se puede buscar por código; y una búsqueda sin coincidencias da 0."""
    assert [i["cod"] for i in _listar(cliente, q="nandu", filtro="todos")["items"]] == ["0041"]
    assert [i["cod"] for i in _listar(cliente, q="0041")["items"]] == ["0041"]
    assert _listar(cliente, q="no existe")["total"] == 0


def test_filtros(cliente):
    """Cada botón de filtro (sin oferta, con oferta, todos) devuelve exactamente los productos que corresponden."""
    assert {i["cod"] for i in _listar(cliente, filtro="sin_oferta")["items"]} == {"D4"}
    assert {i["cod"] for i in _listar(cliente, filtro="con_oferta")["items"]} == {"A1", "C3", "0041"}
    assert _listar(cliente, filtro="todos")["total"] == 7


def test_podio_paginado_1_2_3_y_seguir_adelante(cliente):
    """El podio trae la 1.ª, 2.ª y 3.ª; y pedir desde=3 (el botón «Ver siguientes») trae la 4.ª y 5.ª."""
    p1 = cliente.get("/api/productos/A1/ofertas").json()
    assert [o["puesto"] for o in p1["ofertas"]] == [1, 2, 3]
    assert [o["empresa"] for o in p1["ofertas"]] == ["BETA SAS", "GAMA LTDA", "ALFA SAS"]
    assert p1["total_ofertas"] == 5 and p1["hay_mas"] and p1["restantes"] == 2
    assert p1["ofertas"][0]["es_elegida"] and p1["ofertas"][1]["dif_abs"] == 10

    p2 = cliente.get("/api/productos/A1/ofertas", params={"desde": 3}).json()  # el botón "ver siguientes"
    assert [o["puesto"] for o in p2["ofertas"]] == [4, 5]
    assert not p2["hay_mas"] and p2["restantes"] == 0
    assert p2["ofertas"][1]["empresa"].startswith("Proveedor 5")  # '05' se unificó con '5'


def test_producto_con_una_sola_oferta_y_sin_ofertas(cliente):
    """Con una sola oferta no hay botón «Ver siguientes»; sin ofertas la lista viene vacía; un producto inexistente da 404."""
    assert cliente.get("/api/productos/C3/ofertas").json()["hay_mas"] is False
    assert cliente.get("/api/productos/D4/ofertas").json()["ofertas"] == []
    assert cliente.get("/api/productos/NOEXISTE/ofertas").status_code == 404


def test_agregar_oferta_manual_proveedor_nuevo_llega_al_puesto_1(cliente):
    """Agregar una oferta más barata con un proveedor nuevo la deja de 1.ª; repetirla actualiza el precio sin duplicar nada."""
    r = cliente.post(
        "/api/ofertas",
        json={"cod_producto": "A1", "empresa_nueva": "Droguería Nueva", "valor": 80, "presentacion": "X100"},
    )
    assert r.status_code == 201
    j = r.json()
    assert j["puesto"] == 1 and j["es_la_mejor"] and j["proveedor_nuevo"] and int(j["cod_empresa"]) >= 1000
    top = cliente.get("/api/productos/A1/ofertas").json()["ofertas"]
    assert top[0]["empresa"] == "Droguería Nueva" and top[0]["origen"] == "manual" and top[0]["eliminable"]
    # el mismo nombre no duplica el proveedor, y repetir la oferta la actualiza
    r2 = cliente.post(
        "/api/ofertas", json={"cod_producto": "A1", "empresa_nueva": "droguería nueva", "valor": 75}
    ).json()
    assert r2["actualizada"] and not r2["proveedor_nuevo"] and r2["cod_empresa"] == j["cod_empresa"]
    assert cliente.get("/api/productos/A1/ofertas").json()["ofertas"][0]["valor"] == 75


def test_agregar_oferta_a_producto_sin_ofertas(cliente):
    """Un producto sin ofertas pasa a tenerla y deja de aparecer en «Sin oferta»."""
    r = cliente.post("/api/ofertas", json={"cod_producto": "D4", "cod_empresa": "3", "valor": 500}).json()
    assert r["puesto"] == 1 and r["total_ofertas"] == 1
    assert _listar(cliente, filtro="sin_oferta")["total"] == 0


def test_validaciones_de_oferta_manual(cliente):
    """Se rechazan precios 0 o negativos, no indicar proveedor, indicar dos, y productos o proveedores que no existen."""

    def post(**b):
        """Atajo: envía una oferta manual con los campos indicados y devuelve la respuesta."""
        return cliente.post("/api/ofertas", json=b)

    assert post(cod_producto="A1", cod_empresa="1", valor=0).status_code == 422
    assert post(cod_producto="A1", cod_empresa="1", valor=-5).status_code == 422
    assert post(cod_producto="A1", valor=10).status_code == 422  # sin proveedor
    assert post(cod_producto="A1", cod_empresa="1", empresa_nueva="X", valor=10).status_code == 422  # dos proveedores
    assert post(cod_producto="NOEXISTE", cod_empresa="1", valor=10).status_code == 404
    assert post(cod_producto="A1", cod_empresa="999", valor=10).status_code == 404


def test_eliminar_solo_ofertas_manuales(cliente):
    """Una oferta del Excel NO se puede borrar (409); una manual sí; una inexistente da 404."""
    excel_id = cliente.get("/api/productos/A1/ofertas").json()["ofertas"][0]["id"]
    assert cliente.delete(f"/api/ofertas/{excel_id}").status_code == 409
    nueva = cliente.post("/api/ofertas", json={"cod_producto": "A1", "cod_empresa": "6", "valor": 10}).json()
    assert cliente.delete(f"/api/ofertas/{nueva['id']}").status_code == 200
    assert cliente.get("/api/productos/A1/ofertas").json()["ofertas"][0]["empresa"] == "BETA SAS"
    assert cliente.delete("/api/ofertas/99999").status_code == 404


def test_elegir_proveedor_distinto_al_mejor(cliente):
    """Elegir otro proveedor cambia la oferta elegida y el total pero no la «mejor»; elegir la mejor quita la elección."""
    assert cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "1"}).json()["a_mano"] is True
    a1 = _listar(cliente)["items"][0]
    assert a1["elegida"]["empresa"] == "ALFA SAS" and a1["elegida_a_mano"] and a1["total"] == 100 * 80
    assert a1["mejor"]["empresa"] == "BETA SAS"  # "mejor" no cambia, solo la elegida
    assert _listar(cliente, filtro="elegidos")["total"] == 1
    assert cliente.get("/api/productos/A1/ofertas").json()["ofertas"][2]["es_elegida"]
    # elegir de nuevo la mejor = quitar la elección
    assert cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "2"}).json()["a_mano"] is False
    assert _listar(cliente, filtro="elegidos")["total"] == 0
    assert cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "6"}).status_code == 422  # sin oferta


def test_filtrar_por_proveedor_ganador(cliente):
    """Filtrar por proveedor (clic en el gráfico) devuelve solo los productos que se le compran a ese proveedor."""
    assert {i["cod"] for i in _listar(cliente, empresa="2")["items"]} == {"A1"}
    assert {i["cod"] for i in _listar(cliente, empresa="1")["items"]} == {"C3", "0041"}


def test_reimportar_conserva_lo_agregado_a_mano(cliente):
    """Volver a importar los Excel no duplica ofertas y CONSERVA lo agregado a mano (ofertas, proveedores y elecciones)."""
    cliente.post("/api/ofertas", json={"cod_producto": "A1", "empresa_nueva": "Prov Manual", "valor": 60})
    cliente.put("/api/productos/C3/seleccion", json={"cod_empresa": "1"})
    cliente.post("/api/ofertas", json={"cod_producto": "C3", "cod_empresa": "3", "valor": 30})
    cliente.put("/api/productos/C3/seleccion", json={"cod_empresa": "1"})
    r = cliente.post("/api/importar").json()
    assert r["ofertas"] == 8  # las del Excel, sin duplicarse
    assert cliente.get("/api/productos/A1/ofertas").json()["ofertas"][0]["empresa"] == "Prov Manual"
    assert _listar(cliente, filtro="elegidos")["total"] == 1
    assert "Prov Manual" in [e["nombre"] for e in cliente.get("/api/empresas").json()]


def test_la_hoja_valores_de_la_oc_tiene_el_formato_de_oc_xlsm(cliente):
    """La hoja VALORES de la orden de compra tiene las 8 columnas de OC.xlsm, usa el proveedor elegido, omite productos sin oferta y guarda los códigos como texto."""
    cliente.put("/api/productos/A1/seleccion", json={"cod_empresa": "1"})  # se exporta la elegida, no la mejor
    r = cliente.get("/api/exportar/oc")
    assert r.status_code == 200 and "OC_" in r.headers["content-disposition"]
    assert (
        cliente.get("/api/exportar/valores").status_code == 404
    )  # el botón «Exportar VALORES» ya no existe: esa hoja va dentro de la OC
    ws = load_workbook(io.BytesIO(r.content))["VALORES"]
    filas = list(ws.iter_rows(values_only=True))
    assert list(filas[0]) == [
        "COD_PRODUCTO",
        "DESCRIPCION",
        "CANT_COMPRAR",
        "VALOR",
        "COD_EMPRESA",
        "NOM_EMPRESA",
        "EXISTENCIAS",
        "STOCK MAXIMO",
    ]
    cuerpo = {f[0]: f for f in filas[1:]}
    assert set(cuerpo) == {"A1", "C3", "0041"}  # D4 no tiene oferta -> no se exporta
    assert cuerpo["A1"][2:6] == (80, 100, "1", "ALFA SAS") and cuerpo["A1"][6:] == (20, 100)
    assert isinstance(cuerpo["0041"][0], str)  # el código conserva el cero


def test_catalogo_para_la_ventana_de_agregar(cliente):
    """El buscador de el panel «Agregar oferta» encuentra productos por descripción, incluso los que solo están en la ficha."""
    r = cliente.get("/api/catalogo", params={"q": "alfa"}).json()
    assert r[0]["cod"] == "A1" and r[0]["comprar"] == 80 and r[0]["mejor_valor"] == 85
    assert cliente.get("/api/catalogo", params={"q": ""}).json() == []
    assert cliente.get("/api/catalogo", params={"q": "producto solo en ficha"}).json()[0]["cod"] == "X9"


def test_avisos_de_calidad_de_datos(cliente):
    """Se generan los avisos esperados: proveedor sin nombre, proveedor que no está en EMPRESA.xlsx y productos sin ninguna oferta."""
    t = [a["titulo"] for a in cliente.get("/api/avisos").json()]
    assert any("sin nombre" in x for x in t)  # proveedor 6
    assert any("no existen en EMPRESA.xlsx" in x for x in t)  # proveedor 5
    assert any("no tienen ninguna oferta" in x for x in t)  # D4
    assert cliente.get("/api/resumen").json()["avisos_pendientes"] >= 3


def test_importar_sin_archivos_da_error_claro(cliente, monkeypatch, tmp_path):
    """Si faltan los Excel, importar responde 422 con un mensaje claro («Falta el archivo…») en vez de romperse."""
    monkeypatch.setenv("COMPRAS_EXCEL_DIR", str(tmp_path / "vacia"))
    r = cliente.post("/api/importar")
    assert r.status_code == 422 and "Falta el archivo" in r.json()["detail"]


def test_la_aplicacion_tiene_un_solo_html(cliente):
    """Toda la aplicación vive en UNA página (index.html): la pantalla principal y los dos paneles emergentes
    «Agregar oferta» y «Cargar datos». No debe volver a haber otros .html ni rutas de «ventanas» aparte."""
    from app.config import FRONTEND_DIR

    assert [f.name for f in FRONTEND_DIR.glob("**/*.html")] == ["index.html"]
    pagina = cliente.get("/")
    assert pagina.status_code == 200
    # los dos paneles están dentro de esa misma página
    assert 'id="dlg-agregar"' in pagina.text and 'id="dlg-cargar"' in pagina.text
    assert 'id="btn-agregar"' in pagina.text and 'id="btn-cargar"' in pagina.text
    # las rutas de las antiguas ventanas ya no existen
    assert cliente.get("/ventana/agregar-oferta").status_code == 404
    assert cliente.get("/ventana/cargar-datos").status_code == 404


def test_el_navegador_no_guarda_copias_viejas(cliente):
    """La página y sus archivos JS/CSS se entregan con «no-cache»: al actualizar la aplicación, el navegador nunca
    sigue usando el JavaScript de la versión anterior (una causa típica de que un botón nuevo «no funcione»)."""
    for ruta in ("/", "/static/js/app.js", "/static/js/cargar.js", "/static/css/agregar.css"):
        r = cliente.get(ruta)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", ruta


def test_las_tipografias_del_diseno_existen_y_se_sirven(cliente):
    """La identidad visual usa tres tipografías guardadas en frontend/fonts. Si alguien mueve o borra un archivo,
    la pantalla se vería con letras del sistema sin avisar: esta prueba lo detecta.
    Comprueba que el CSS nombre las tres familias y que CADA archivo .woff2 que nombra lo sirva la aplicación."""
    import re

    css = cliente.get("/static/css/base.css")
    assert css.status_code == 200
    rutas = re.findall(r'url\("(/static/fonts/[^"]+\.woff2)"\)', css.text)
    assert len(rutas) >= 9  # Montserrat (3 pesos) + Mulish (4) + Poppins (2)
    for familia in ("Montserrat", "Mulish", "Poppins"):
        assert f'font-family: "{familia}"' in css.text
    for ruta in rutas:
        r = cliente.get(ruta)
        assert r.status_code == 200, f"falta la tipografía {ruta}"
        assert len(r.content) > 5000  # es un archivo de fuente de verdad, no una página de error


def test_los_logos_de_la_pagina_existen_y_se_sirven(cliente):
    """La página muestra los logos de la clínica (barra de arriba, bienvenida, pie e icono de la pestaña), guardados en
    frontend/img. Si alguien mueve o borra uno, aparecería una imagen rota: esta prueba lo detecta.
    Lee los <img> y el <link rel="icon"> de index.html y comprueba que CADA archivo se sirva como imagen PNG."""
    import re

    html = cliente.get("/").text
    rutas = set(re.findall(r'(?:src|href)="(/static/img/[^"]+)"', html))
    assert {"/static/img/logo-blanco.png", "/static/img/corazon.png", "/static/img/icono-192.png"} <= rutas
    for ruta in rutas:
        r = cliente.get(ruta)
        assert r.status_code == 200, f"falta el logo {ruta}"
        assert r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"
