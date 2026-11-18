"""Prueba de la interfaz con un navegador real (Chromium).

Se omite sola si no tienes playwright:   pip install playwright && playwright install chromium
"""

import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from tests.conftest import CLAVE_ADMIN, crear_excel_sintetico, excel_bytes  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture()
def servidor(tmp_path, monkeypatch):
    """Enciende la aplicación de verdad (con datos de prueba) en un puerto libre y entrega su dirección; la apaga al terminar."""
    excel = tmp_path / "excel"
    excel.mkdir()
    crear_excel_sintetico(excel)
    monkeypatch.setenv("COMPRAS_EXCEL_DIR", str(excel))
    monkeypatch.setenv("COMPRAS_DB", str(tmp_path / "e2e.db"))
    monkeypatch.setenv("COMPRAS_ADMIN_CLAVE", CLAVE_ADMIN)  # el arranque crea el usuario «admin» con esta clave
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    from app.main import app

    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="error"))
    hilo = threading.Thread(target=srv.run, daemon=True)
    hilo.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{puerto}"
    srv.should_exit = True
    hilo.join(timeout=5)


@pytest.fixture()
def servidor_vacio(tmp_path, monkeypatch):
    """Igual que `servidor`, pero SIN ningún Excel en la carpeta: la aplicación arranca con la base vacía («Todavía no hay datos»)."""
    vacia = tmp_path / "excel_vacia"
    vacia.mkdir()
    monkeypatch.setenv("COMPRAS_EXCEL_DIR", str(vacia))
    monkeypatch.setenv("COMPRAS_DB", str(tmp_path / "vacio.db"))
    monkeypatch.setenv("COMPRAS_ADMIN_CLAVE", CLAVE_ADMIN)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    from app.main import app

    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="error"))
    hilo = threading.Thread(target=srv.run, daemon=True)
    hilo.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{puerto}"
    srv.should_exit = True
    hilo.join(timeout=5)


@pytest.fixture()
def navegador():
    """Abre un navegador Chromium real. Si no está instalado, la prueba se omite en vez de fallar."""
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # sin navegador instalado
            pytest.skip(f"Chromium no disponible: {e}")
        yield b
        b.close()


def _contexto(navegador, servidor, ancho, alto, usuario="admin", clave=CLAVE_ADMIN):
    """Un navegador nuevo con la sesión ya iniciada (por defecto como administrador): la cookie queda en el contexto, así
    cada página que se abra después ya entra logueada, igual que si la persona hubiera escrito su clave."""
    ctx = navegador.new_context(viewport={"width": ancho, "height": alto}, bypass_csp=True)
    r = ctx.request.post(servidor + "/api/sesion", data={"usuario": usuario, "clave": clave})
    assert r.ok, r.text()
    return ctx


def test_podio_boton_seguir_y_panel_de_agregar(servidor, navegador):
    """Recorre la aplicación como una persona, con un navegador real:
    1. Los números de arriba aparecen y coinciden.  2. Abre la ventana de ofertas del producto A1 (pestaña «Comparar todas»):
       ve 3 ofertas y el botón «Ver siguientes».  3. Pulsa el botón: aparecen las 2 restantes.  4. Elige la 2.ª oferta.
    5. Desde esa ventana abre el PANEL «Agregar oferta» (queda encima), agrega una oferta nueva más barata con «Guardar y
       cerrar» y comprueba que solo se cierra el panel de encima, que el aviso verde se ve y que la ventana de ofertas de
       abajo se actualiza sola (la nueva oferta pasa a ser la 1.ª).  6. No hubo errores de JavaScript y no se abrió ninguna ventana nueva."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")  # entra directo al tablero (sin pasar por la bienvenida)
    pg.wait_for_selector(".fila")

    # KPIs con los datos de prueba: 4 productos por comprar, 1 sin oferta
    # (los números se animan al aparecer: se espera a que lleguen a su valor)
    pg.wait_for_function("document.querySelector('#kv-comprar').textContent === '4'")
    pg.wait_for_function("document.querySelector('#kv-sin').textContent === '1'")

    # el producto A1 tiene 5 ofertas: se ven 3 y un botón para seguir
    pg.fill("#q", "alfa")
    # el buscador espera 250 ms antes de filtrar: hay que esperar a que quede UNA sola fila,
    # si no, el refresco de la lista puede llegar justo después del clic
    pg.wait_for_function("document.querySelectorAll('.fila').length === 1")
    # el botón «Mejor oferta» abre la ventana; desde su pestaña «Comparar todas» se ve el podio completo
    pg.click(".fila[data-cod='A1'] .btn-fila[data-pestana='mejor']")
    pg.wait_for_selector("#dlg-ofertas[open] .mejor-panel")
    pg.click("#dlg-ofertas .pestana:has-text('Comparar todas')")
    pg.wait_for_function("document.querySelectorAll('#dlg-ofertas .tarjeta').length === 3")
    assert pg.inner_text(".cuenta") == "Mostrando 3 de 5"
    pg.click(".btn-mas")
    pg.wait_for_selector(".oferta-fila")
    assert pg.locator(".oferta-fila").count() == 2
    assert pg.locator(".btn-mas").count() == 0

    # elegir la 2.ª oferta la marca como elegida
    pg.locator(".tarjeta.p2 .btn-elegir").click()
    pg.wait_for_selector(".tarjeta.p2.elegida")

    # panel «Agregar oferta»: se abre encima de la misma página, agrega una oferta y se cierra
    pg.click(".detalle-pie .btn")
    pg.wait_for_selector("#dlg-agregar[open] .ficha-datos")
    pg.select_option("#ag-proveedor", "__nuevo__")
    pg.fill("#ag-proveedor-nuevo", "Proveedor E2E")
    pg.fill("#ag-valor", "50")
    pg.wait_for_selector("#ag-previa.mejor")
    pg.click("#ag-guardar")
    pg.wait_for_selector("#dlg-agregar", state="hidden")  # el panel se cerró solo
    # el aviso verde se ve DENTRO de la ventana de ofertas (la que sigue abierta debajo), no escondido detrás de ella
    pg.wait_for_selector("#dlg-ofertas .toast.ok")
    assert pg.is_visible("#dlg-ofertas[open]")  # cerrar el panel de encima no cierra la ventana de ofertas
    # y esa ventana se actualizó sola: la oferta nueva ($50) es ahora la 1.ª
    pg.wait_for_selector("#dlg-ofertas .tarjeta.p1 .prov:has-text('Proveedor E2E')")
    assert len(ctx.pages) == 1  # no se abrió ninguna ventana nueva
    assert errores == []


def test_agregar_oferta_guardar_y_agregar_otra_y_cerrar_con_esc(servidor, navegador):
    """El panel «Agregar oferta» sin usar el mouse para cerrar:
    1. Se abre desde la barra superior, busca un producto y lo elige.  2. «Guardar y agregar otra» deja el panel abierto
    con un banner verde y la pantalla de fondo ya actualizada.  3. La tecla Esc lo cierra."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")  # entra directo al tablero (sin pasar por la bienvenida)
    pg.wait_for_selector(".fila")

    pg.click("#btn-agregar")
    pg.wait_for_selector("#dlg-agregar[open]")
    pg.fill("#ag-buscar", "alfa")
    pg.click("#ag-resultados li:first-child")  # elige el primer resultado de la lista desplegable
    pg.wait_for_selector("#ag-ficha .ficha-datos")
    assert "A1" in pg.inner_text("#ag-ficha")
    pg.select_option("#ag-proveedor", "__nuevo__")
    pg.fill("#ag-proveedor-nuevo", "Proveedor Otra")
    pg.fill("#ag-valor", "40")
    pg.click("#ag-guardar-otra")
    pg.wait_for_selector("#ag-banner.banner-ok")
    assert "guardada" in pg.inner_text("#ag-banner").lower()
    assert pg.is_visible("#dlg-agregar")  # sigue abierto
    assert pg.input_value("#ag-valor") == ""  # y con el formulario limpio, listo para otra oferta

    pg.keyboard.press("Escape")
    pg.wait_for_selector("#dlg-agregar", state="hidden")
    # la pantalla de fondo ya se actualizó: A1 tiene ahora a «Proveedor Otra» como mejor proveedor
    pg.fill("#q", "alfa")
    pg.wait_for_function(
        "document.querySelector(\"[data-cod='A1'] .c-oferta\")?.textContent.includes('Proveedor Otra')"
    )
    assert len(ctx.pages) == 1 and errores == []


def test_botones_mejor_oferta_y_otras_ofertas(servidor, navegador):
    """Los dos botones de cada fila abren su propia ventana emergente (sin flecha ni desplegable en la fila):
    1. «Mejor oferta» abre una ventana con solo la mejor y por qué lo es.  2. «Otras ofertas» abre la ventana con la 2.ª y 3.ª,
    con «Ver siguientes».  3. Las pestañas de la ventana cambian de vista y su título las sigue.
    4. La ventana se cierra con la X, con «Cerrar» y con Esc; el resto de la fila no abre nada.
    5. Con una sola oferta, «Otras ofertas» está apagado.  6. Sin ofertas, el botón es «Agregar oferta» y abre el panel con ese producto elegido."""
    ctx = _contexto(navegador, servidor, 1600, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")  # entra directo al tablero (sin pasar por la bienvenida)
    pg.wait_for_selector(".fila")

    def buscar(texto):
        """Escribe en el buscador y espera a que quede UNA sola fila (el buscador espera 250 ms antes de filtrar)."""
        pg.fill("#q", texto)
        pg.wait_for_function("document.querySelectorAll('.fila').length === 1")

    # ---- A1: 5 ofertas (BETA $85 es la mejor)
    buscar("alfa")
    fila = pg.locator(".fila[data-cod='A1']")
    # la fila ya no tiene flecha ni zona que se despliega
    assert pg.locator(".chev").count() == 0 and pg.locator(".fila-detalle").count() == 0
    # clic en el resto de la fila (el nombre del producto): no abre nada
    fila.locator(".c-prod").click()
    assert not pg.is_visible("#dlg-ofertas")

    # «Mejor oferta»: abre SU ventana, con la mejor y por qué lo es
    fila.locator(".btn-fila[data-pestana='mejor']").click()
    pg.wait_for_selector("#dlg-ofertas[open] .mejor-panel")
    assert pg.inner_text("#of-titulo") == "Mejor oferta"
    assert "A1" in pg.inner_text("#of-sub")
    assert "BETA SAS" in pg.inner_text(".mejor-panel .tarjeta.p1")
    assert (
        "por qué es la mejor" in pg.inner_text(".mejor-resumen").lower()
    )  # el título se ve en mayúsculas por el estilo
    assert pg.locator("#dlg-ofertas .pestana[aria-selected='true']").inner_text().strip().startswith("Mejor oferta")

    # se cierra con la X (y la lista de atrás sigue ahí)
    pg.click("#dlg-ofertas .cerrar-modal")
    pg.wait_for_selector("#dlg-ofertas", state="hidden")
    assert pg.locator(".fila").count() == 1

    # «Otras ofertas»: abre OTRA ventana, con la 2.ª y la 3.ª (NO la mejor) y el botón para seguir
    fila.locator(".btn-fila[data-pestana='otras']").click()
    pg.wait_for_function("document.querySelectorAll('#dlg-ofertas .tarjeta').length === 2")
    assert pg.inner_text("#of-titulo") == "Otras ofertas"
    assert "BETA SAS" not in pg.inner_text("#dlg-ofertas .detalle")
    assert "GAMA LTDA" in pg.inner_text(".tarjeta.p2")
    assert pg.inner_text(".cuenta") == "Mostrando 2 de 4 otras ofertas"
    pg.click(".btn-mas")
    pg.wait_for_function("document.querySelectorAll('.oferta-fila').length === 2")
    assert pg.locator(".btn-mas").count() == 0

    # las pestañas de la ventana cambian de vista y el título las sigue
    pg.click("#dlg-ofertas .pestana:has-text('Comparar todas')")
    pg.wait_for_function("document.querySelectorAll('#dlg-ofertas .tarjeta').length === 3")
    assert pg.inner_text("#of-titulo") == "Comparar todas las ofertas"
    pg.click("#dlg-ofertas .pestana:has-text('Mejor oferta')")
    pg.wait_for_selector("#dlg-ofertas .mejor-panel")
    assert pg.inner_text("#of-titulo") == "Mejor oferta"

    # Esc y «Cerrar» también cierran la ventana
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#dlg-ofertas", state="hidden")
    fila.locator(".btn-fila[data-pestana='mejor']").click()
    pg.wait_for_selector("#dlg-ofertas[open] .mejor-panel")
    pg.click("#dlg-ofertas .v-pie [data-cerrar]")
    pg.wait_for_selector("#dlg-ofertas", state="hidden")
    # al cerrar se vacía (lo hace el evento «close», que llega un instante después de ocultarse): no queda nada viejo
    pg.wait_for_function("document.querySelector('#of-cuerpo').innerHTML === ''")

    # ---- C3: una sola oferta → «Otras ofertas» apagado y la ventana Mejor dice que es la única
    buscar("C3")
    otras = pg.locator(".fila[data-cod='C3'] .btn-fila[data-pestana='otras']")
    assert otras.is_disabled()
    pg.locator(".fila[data-cod='C3'] .btn-fila[data-pestana='mejor']").click()
    pg.wait_for_selector("#dlg-ofertas[open] .mejor-panel")
    assert "única oferta" in pg.inner_text(".mejor-resumen")
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#dlg-ofertas", state="hidden")

    # ---- D4: sin ofertas → el botón es «Agregar oferta» y abre el panel con ese producto ya elegido
    buscar("D4")
    boton = pg.locator(".fila[data-cod='D4'] .btn-fila.agregar")
    assert "Agregar oferta" in boton.inner_text()
    boton.click()
    pg.wait_for_selector("#dlg-agregar[open] #ag-ficha .ficha-datos")
    assert "D4" in pg.inner_text("#ag-ficha")
    assert len(ctx.pages) == 1 and errores == []


def test_cargar_datos_subir_excel_y_agregar_a_mano(servidor, navegador):
    """El panel «Cargar datos», como una persona:
    1. Se abre con el botón de la barra superior (sin ventanas emergentes que el navegador pueda bloquear).
    2. Sube un Excel de cotizaciones de un proveedor NUEVO: se REVISA solo (1 nueva, 1 con error) y se carga.
    3. Sin cerrar el panel, agrega un producto a mano en el formulario.
    4. Al cerrarlo, la pantalla principal ya está actualizada: A1 tiene esa oferta y el producto nuevo aparece."""
    ctx = _contexto(navegador, servidor, 1600, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")  # entra directo al tablero (sin pasar por la bienvenida)
    pg.wait_for_selector(".fila")

    pg.click("#btn-cargar")
    pg.wait_for_selector("#dlg-cargar[open]")
    assert len(ctx.pages) == 1  # se abrió DENTRO de la página, no en una ventana nueva
    assert [t.strip() for t in pg.locator("#cg-pestanas .pestana").all_inner_texts()] == [
        "Productos",
        "Proveedores",
        "Cotizaciones",
    ]

    # ---- subir cotizaciones de un proveedor nuevo (el archivo no trae la columna del proveedor)
    pg.click("#cg-pestanas .pestana[data-tipo='cotizaciones']")
    pg.select_option("#panel-cotizaciones select", "__nuevo__")
    pg.fill("#panel-cotizaciones input[aria-label='Nombre del proveedor nuevo']", "Proveedor Subido")
    pg.press("#panel-cotizaciones input[aria-label='Nombre del proveedor nuevo']", "Tab")
    archivo = excel_bytes(
        [{"COD_PRODUCTO": "A1", "VALOR": 50, "PRESENTACION": "X5"}, {"COD_PRODUCTO": "NOEXISTE", "VALOR": 5}]
    )
    pg.set_input_files(
        "#panel-cotizaciones input[type='file']",
        {
            "name": "cotizacion.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "buffer": archivo,
        },
    )
    pg.wait_for_selector("#panel-cotizaciones .estadisticas")
    assert "creará el proveedor nuevo" in pg.inner_text("#panel-cotizaciones .notas")
    assert "NOEXISTE" in pg.inner_text("#panel-cotizaciones .tabla-errores")
    # revisar NO guarda nada: todavía no existe ese proveedor
    assert (
        pg.evaluate(
            "fetch('/api/empresas').then(r => r.json()).then(l => l.some(e => e.nombre === 'Proveedor Subido'))"
        )
        is False
    )
    pg.click("#panel-cotizaciones .subidor .acciones-carga .btn-primario")  # «Cargar 1 fila»
    pg.wait_for_selector("#panel-cotizaciones .subidor .banner-ok")

    # ---- agregar un producto a mano en el formulario (sin cerrar el panel)
    pg.click("#cg-pestanas .pestana[data-tipo='productos']")
    formulario = "#panel-productos .formulario"
    pg.fill(f"{formulario} input[aria-label^='Código']", "E2E1")
    pg.fill(f"{formulario} input[aria-label^='Descripción']", "PRODUCTO E2E")
    pg.fill(f"{formulario} input[aria-label='Stock máximo']", "30")
    pg.fill(f"{formulario} input[aria-label='Existencias']", "5")
    pg.click(f"{formulario} .btn-primario")
    pg.wait_for_selector(f"{formulario} .banner-ok:not([hidden])")

    # ---- cerrar con «Listo, cerrar»: la pantalla principal ya está al día
    pg.click("#dlg-cargar .v-pie [data-cerrar]")
    pg.wait_for_selector("#dlg-cargar", state="hidden")
    pg.fill("#q", "alfa")
    pg.wait_for_function(
        "document.querySelector(\"[data-cod='A1'] .c-oferta\")?.textContent.includes('Proveedor Subido')"
    )
    pg.fill("#q", "E2E1")
    pg.wait_for_selector(".fila[data-cod='E2E1']")
    assert (
        pg.input_value(".fila[data-cod='E2E1'] .cantidad-input") == "25"
    )  # 30 − 5 (la cantidad es una caja donde se escribe)
    assert len(ctx.pages) == 1 and errores == []


def test_desde_cargar_datos_se_puede_pasar_a_agregar_oferta(servidor, navegador):
    """En la pestaña Cotizaciones, el botón «Abrir Agregar oferta» cierra «Cargar datos» y abre «Agregar oferta»
    (un solo panel a la vez)."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    pg.goto(servidor + "/#tablero")  # entra directo al tablero (sin pasar por la bienvenida)
    pg.wait_for_selector(".fila")
    pg.click("#btn-cargar")
    pg.wait_for_selector("#dlg-cargar[open]")
    pg.click("#cg-pestanas .pestana[data-tipo='cotizaciones']")
    pg.click("#panel-cotizaciones .tarjeta-info .btn-primario")
    pg.wait_for_selector("#dlg-agregar[open]")
    assert not pg.is_visible("#dlg-cargar")


def test_bienvenida_menu_lateral_y_pantallas(servidor, navegador):
    """Lo primero que se ve al ingresar, y el menú de la izquierda:
    1. Se ve la bienvenida a pantalla completa con el menú a la izquierda y sus 8 opciones (las del administrador), en orden. El tablero NO se ve todavía.
    2. La bienvenida muestra tres datos rápidos y el botón grande «Tablero de compras».
    3. Desde el menú, ya en la bienvenida, se abren las ventanas «Agregar oferta», «Cargar datos» y «Actualizar Excel»
       (que ahora pregunta qué tablas importar y cómo) y el panel de avisos.
    4. El botón grande abre el tablero: la ruta de arriba dice «Tablero de compras» y su opción del menú queda marcada.
    5. La marca de arriba vuelve a la bienvenida.  6. El botón ☰ esconde y vuelve a mostrar el menú.  7. Sin errores de JavaScript."""
    ctx = _contexto(navegador, servidor, 1500, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor)

    # 1. bienvenida + menú lateral con sus 8 opciones (las del administrador)
    pg.wait_for_selector("#vista-inicio", state="visible")
    assert not pg.is_visible("#vista-tablero")
    assert "SUMIPABON" in pg.title() and "Mesa de ofertas" not in pg.inner_text(
        "body"
    )  # el nombre nuevo, en todos lados
    opciones = [t.strip() for t in pg.locator("#menu .menu-item:visible .txt").all_inner_texts()]
    assert opciones == [
        "Tablero de compras",
        "Tableros de control",
        "Administración",
        "Usuarios",
        "Productos que necesitamos",  # el administrador también ve la pantalla del proveedor
        "Agregar oferta",
        "Cargar datos",
        "Actualizar Excel",
        "Descargar OC (ganadores)",
        "Alternativas 2.º a 4.º",
        "Ofertas de proveedores",
        "Avisos de datos",
    ]
    caja = pg.locator("#menu").bounding_box()
    assert caja["x"] == 0 and caja["width"] > 150  # el menú está pegado al lado IZQUIERDO
    assert pg.locator("#vista-inicio").bounding_box()["x"] >= caja["width"] - 1  # y el contenido queda a su derecha

    # 2. datos rápidos y botón grande
    pg.wait_for_function("document.querySelectorAll('#inicio-datos li').length === 3")
    assert pg.is_visible("#btn-entrar")

    # 3. desde la bienvenida, las opciones del menú abren sus ventanas
    pg.click("#btn-agregar")
    pg.wait_for_selector("#dlg-agregar[open]")
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#dlg-agregar", state="hidden")
    pg.click("#btn-cargar")
    pg.wait_for_selector("#dlg-cargar[open]")
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#dlg-cargar", state="hidden")
    pg.click(
        "#btn-importar"
    )  # «Actualizar Excel» ya no recarga todo de golpe: abre la ventana para elegir tablas y modo
    pg.wait_for_selector("#dlg-importar[open] .imp-fila")
    assert pg.locator("#dlg-importar .imp-fila").count() == 5
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#dlg-importar", state="hidden")
    pg.click("#btn-avisos")
    pg.wait_for_selector(".cajon")
    pg.keyboard.press("Escape")
    pg.wait_for_selector(".cajon", state="detached")

    # 4. el botón grande abre el tablero
    pg.click("#btn-entrar")
    pg.wait_for_selector("#vista-tablero", state="visible")
    pg.wait_for_selector(".fila")
    assert not pg.is_visible("#vista-inicio")
    assert pg.inner_text("#ruta-actual").strip() == "Tablero de compras"
    assert pg.get_attribute("#menu-tablero", "aria-current") == "page"
    assert pg.get_attribute("#menu-admin", "aria-current") is None

    # 5. la marca vuelve a la bienvenida
    pg.click(".marca")
    pg.wait_for_selector("#vista-inicio", state="visible")
    assert not pg.is_visible("#vista-tablero")
    assert pg.get_attribute("#menu-tablero", "aria-current") is None

    # 6. el botón ☰ esconde el menú (sale de la pantalla por la izquierda) y lo vuelve a mostrar
    pg.click("#btn-menu")
    pg.wait_for_function("document.querySelector('#menu').getBoundingClientRect().right <= 0")
    pg.click("#btn-menu")
    pg.wait_for_function("document.querySelector('#menu').getBoundingClientRect().left >= 0")

    assert len(ctx.pages) == 1 and errores == []


# ------------------------------------------------------------------------------------------------ Administración
def _filas_tabla(pg) -> int:
    """Cuántas filas de datos muestra ahora la tabla de Administración."""
    return pg.locator("#adm-tabla tbody tr[data-id]").count()


def test_un_aviso_lleva_a_la_fila_del_problema_y_se_corrige_ahi(servidor, navegador):
    """El aviso ya no solo se lee, LLEVA al problema:
    1. En el panel de avisos, «Proveedores sin nombre» trae un botón «Ir a Empresas…» con el número de filas.
    2. Al pulsarlo se cierra el panel y se abre Administración en la pestaña Empresas, con SOLO la fila del problema
       (proveedor 6) y la franja «Mostrando las 1 fila(s) del aviso…».
    3. Se le pone nombre en la misma fila (doble clic → escribir → Enter): el aviso desaparece, la pantalla avisa «¡Listo!»,
       quita el filtro y muestra las 5 empresas; el contador de avisos del menú baja de 3 a 2.
    4. El aviso «sin oferta» lleva al TABLERO con el filtro «Sin oferta» puesto (solo D4).   5. Sin errores de JavaScript."""
    ctx = _contexto(navegador, servidor, 1500, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    pg.wait_for_function("document.querySelector('#badge-avisos').textContent.trim() === '3'")

    # 1-2. del aviso a la tabla, con el filtro puesto
    pg.click("#btn-avisos")
    pg.wait_for_selector(".cajon .aviso")
    boton = pg.locator(".cajon .aviso", has_text="Proveedores sin nombre").locator(".btn-ir").first
    assert "Empresas" in boton.inner_text() and boton.locator(".n").inner_text() == "1"
    boton.click()
    pg.wait_for_selector(".cajon", state="detached")
    pg.wait_for_selector("#vista-admin", state="visible")
    assert pg.url.endswith("#admin/empresas")
    pg.wait_for_selector("#adm-pestanas .pestana[aria-selected='true']:has-text('Empresas')")
    pg.wait_for_selector("#adm-filtro:not([hidden])")
    assert "Proveedores sin nombre" in pg.inner_text("#adm-filtro")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 1")
    assert pg.locator("#adm-tabla tbody tr[data-id] td").nth(2).inner_text() == "6"
    assert pg.get_attribute("#menu-admin", "aria-current") == "page"

    # 3. corregirlo en la misma fila
    pg.locator("#adm-tabla tbody tr[data-id] td").nth(3).dblclick()
    caja = pg.locator("#adm-tabla tr.editando input[data-col='NOMBRE']")
    caja.fill("EPSILON SAS")
    pg.fill("#adm-tabla tr.editando input[data-col='TELEFONO']", "300 123 4567")  # teléfono y correo son obligatorios
    pg.fill("#adm-tabla tr.editando input[data-col='CORREO']", "epsilon@empresa.com")
    caja.press("Enter")
    pg.wait_for_function("document.querySelector('#adm-filtro').hidden")  # el aviso desapareció: se quitó el filtro
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 5")
    pg.wait_for_selector(".toast:has-text('Listo')")
    pg.wait_for_function("document.querySelector('#badge-avisos').textContent.trim() === '2'")

    # 4. el aviso del tablero
    pg.click("#btn-avisos")
    pg.wait_for_selector(".cajon .aviso")
    pg.locator(".cajon .aviso", has_text="no tienen ninguna oferta").locator(".btn-ir").first.click()
    pg.wait_for_selector("#vista-tablero", state="visible")
    assert pg.url.endswith("#tablero")
    pg.wait_for_function("document.querySelectorAll('.fila').length === 1")
    assert pg.get_attribute("#chips .chip:has-text('Sin oferta')", "aria-pressed") == "true"
    assert errores == []


def test_agregar_validar_eliminar_y_deshacer_en_administracion(servidor, navegador):
    """El ciclo completo sobre la tabla Stock (6 filas):
    1. Agregar con un número inválido: la ventana muestra el error y NO se cierra. Se corrige y se guarda: hay 7 filas,
       la pestaña dice 7 y la fila nueva se ve.   2. Editar en la fila: Esc cancela; con un valor inválido avisa y sigue editando.
    3. Eliminar: la ventana de confirmación explica qué pasará; «Cancelar» no borra; «Eliminar» sí (vuelven a ser 6).
    4. En el Historial, «Deshacer» devuelve la fila eliminada (7).   5. Sin errores de JavaScript."""
    ctx = _contexto(navegador, servidor, 1500, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#admin/stock")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 6")
    assert [t.strip() for t in pg.locator("#adm-tabla thead th").all_inner_texts()][2:7] == [
        "COD_PRODUCTO",
        "DESCRIPCION",
        "StockMax",
        "StockMed",
        "StockMin",
    ]  # los encabezados del Excel, tal cual

    # 1. agregar: primero mal, luego bien
    pg.click("#adm-agregar")
    pg.wait_for_selector("#dlg-admin-fila[open]")
    pg.fill("#af-COD_PRODUCTO", "ZZ9")
    pg.fill("#af-StockMax", "muchos")
    pg.click("#af-guardar")
    pg.wait_for_selector("#af-error:not([hidden])")
    assert "StockMax" in pg.inner_text("#af-error") and pg.is_visible("#dlg-admin-fila")
    pg.fill("#af-StockMax", "12")
    pg.click("#af-guardar")
    pg.wait_for_selector("#dlg-admin-fila", state="hidden")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 7")
    assert pg.locator("#adm-pestanas .pestana[aria-selected='true'] .n").inner_text() == "7"
    fila = pg.locator("#adm-tabla tbody tr", has_text="ZZ9")
    assert fila.count() == 1

    # 2. editar: Esc cancela; un valor inválido no cierra la edición
    fila.locator("button[title^='Editar']").click()
    pg.locator("#adm-tabla tr.editando input[data-col='StockMax']").fill("99")
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#adm-tabla tr.editando", state="detached")
    assert pg.locator("#adm-tabla tbody tr", has_text="ZZ9").locator("td").nth(4).inner_text() == "12"
    pg.locator("#adm-tabla tbody tr", has_text="ZZ9").locator("button[title^='Editar']").click()
    pg.locator("#adm-tabla tr.editando input[data-col='StockMax']").fill("abc")
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".toast.error")
    assert pg.locator("#adm-tabla tr.editando").count() == 1  # sigue en edición para poder corregir
    pg.keyboard.press("Escape")

    # 3. eliminar: cancelar no borra; confirmar sí
    pg.locator("#adm-tabla tbody tr", has_text="ZZ9").locator("button[title^='Eliminar']").click()
    pg.wait_for_selector("#dlg-confirmar[open]")
    assert "Eliminar" in pg.inner_text("#cf-titulo") and "Historial" in pg.inner_text("#cf-cuerpo")
    pg.click("#dlg-confirmar [data-cerrar]")
    pg.wait_for_selector("#dlg-confirmar", state="hidden")
    assert _filas_tabla(pg) == 7
    pg.locator("#adm-tabla tbody tr", has_text="ZZ9").locator("button[title^='Eliminar']").click()
    pg.wait_for_selector("#dlg-confirmar[open]")
    pg.click("#cf-ok")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 6")

    # 4. deshacer desde el historial
    pg.click("#adm-historial")
    pg.wait_for_selector("#dlg-historial[open] .hist-tabla")
    primera = pg.locator(".hist-tabla tbody tr").first
    assert "Eliminó" in primera.inner_text() and "ZZ9" in primera.inner_text()
    primera.locator("button:has-text('Deshacer')").click()
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 7")
    pg.wait_for_selector(".hist-tabla tbody tr.deshecho")
    assert errores == []


def test_seleccion_masiva_orden_y_busqueda(servidor, navegador):
    """Con una tabla de más de una página (Stock con 66 filas): se ordena por un encabezado (como número), se busca,
    se marca la página y luego «Seleccionar las 66 filas de la tabla»; eliminarlas todas deja la tabla vacía y avisa cómo seguir."""
    ctx = _contexto(navegador, servidor, 1500, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#admin/stock")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 6")
    # 60 filas más, subidas por la API (como haría el botón «Subir e importar»)
    archivo = excel_bytes(
        [{"COD_PRODUCTO": f"M{i:03d}", "DESCRIPCION": f"MASIVO {i}", "StockMax": str(i)} for i in range(60)]
    )
    r = pg.request.post(servidor + "/api/admin/tablas/stock/importar?nombre=s.xlsx&modo=agregar", data=archivo)
    assert r.ok
    pg.reload()
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 50")
    assert "de 66 filas" in pg.inner_text("#adm-pag")

    # orden numérico: el primer clic ordena de menor a mayor (los ceros primero), el segundo de mayor a menor
    pg.click("#adm-tabla thead th:has-text('StockMax') .orden-col")
    pg.wait_for_function("document.querySelector(\"th[aria-sort='ascending']\") !== null")
    primeros = [t for t in pg.locator("#adm-tabla tbody tr[data-id] td:nth-child(5)").all_inner_texts()[:2]]
    assert primeros == ["0", "0"]
    pg.click("#adm-tabla thead th:has-text('StockMax') .orden-col")
    pg.wait_for_function("document.querySelector(\"th[aria-sort='descending']\") !== null")
    assert pg.locator("#adm-tabla tbody tr[data-id] td:nth-child(5)").first.inner_text() == "100"

    # búsqueda (con pausa de 250 ms al escribir)
    pg.fill("#adm-q", "masivo 59")  # cada palabra puede estar en cualquier columna: «59» solo está en una fila
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 1")
    pg.fill("#adm-q", "")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 50")

    # marcar la página y luego TODA la tabla
    pg.check("#adm-tabla thead .c-sel input")
    pg.wait_for_selector("#adm-seleccion:not([hidden])")
    assert "50" in pg.inner_text("#adm-seleccion")
    pg.click("#adm-seleccion button:has-text('Seleccionar las 66')")
    pg.wait_for_function("document.querySelector('#adm-eliminar').innerText.includes('(66)')")
    pg.click("#adm-eliminar")
    pg.wait_for_selector("#dlg-confirmar[open]")
    assert "66" in pg.inner_text("#cf-titulo")
    pg.click("#cf-ok")
    pg.wait_for_selector("#adm-tabla .vacio-tabla")
    assert "no tiene filas" in pg.inner_text("#adm-tabla .vacio-tabla")
    assert errores == []


def test_importar_desde_la_ventana_de_actualizar_excel(servidor, navegador):
    """La ventana de «Actualizar Excel»: 1. «Agregar» de las 5 tablas (nada cambia porque ya están al día).
    2. «Reemplazar» pide confirmación; al aceptar, la tabla queda como el Excel de la carpeta (Empresas vuelve a 5 filas
       tras agregarle una a mano).  3. Subir un archivo a una tabla: se ve el resultado y la tabla crece.  4. Sin errores."""
    ctx = _contexto(navegador, servidor, 1500, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#admin/empresas")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 5")
    # una fila a mano, para ver que «Agregar» no la borra y «Reemplazar» sí
    pg.click("#adm-agregar")
    pg.fill("#af-CODIGO_EMPRESA", "9")
    pg.fill("#af-NOMBRE", "MIA SAS")
    pg.fill("#af-TELEFONO", "3001234567")
    pg.fill("#af-CORREO", "mia@empresa.com")
    pg.click("#af-guardar")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 6")

    # 1. agregar (modo por defecto): las 5 tablas marcadas
    pg.click("#btn-importar")
    pg.wait_for_selector("#dlg-importar[open] .imp-fila")
    assert pg.locator("#dlg-importar input[name='imp-modo']:checked").get_attribute("value") == "agregar"
    assert pg.locator("#dlg-importar input[data-tabla]:checked").count() == 5
    pg.click("#imp-carpeta")
    pg.wait_for_selector("#imp-resultado li")
    assert pg.locator("#imp-resultado li").count() == 5 and "0 nuevas" in pg.inner_text("#imp-resultado")
    assert _filas_tabla(pg) == 6  # la fila «a mano» sigue ahí

    # 2. reemplazar SOLO Empresas: pide confirmación y la fila a mano desaparece
    pg.check("#dlg-importar input[value='reemplazar']")
    for clave in ("stock", "existencias", "ficha", "portafolio"):
        pg.uncheck(f"#dlg-importar input[data-tabla='{clave}']")
    pg.click("#imp-carpeta")
    pg.wait_for_selector("#dlg-confirmar[open]")
    assert "Empresas" in pg.inner_text("#cf-cuerpo")
    pg.click("#cf-ok")
    pg.wait_for_function("document.querySelector('#imp-resultado').innerText.includes('reemplazada')")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 5")

    # 3. subir un archivo a Existencias (modo agregar): A1 pasa de 20 a 55
    pg.check("#dlg-importar input[value='agregar']")
    pg.select_option("#imp-destino", "existencias")
    pg.set_input_files(
        "#imp-archivo",
        files=[
            {
                "name": "e.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "buffer": excel_bytes([{"COD_PRODUCTO": "A1", "DESCRIPCION": "x", "CANTIDAD": "55"}]),
            }
        ],
    )
    pg.click("#imp-subir")
    pg.wait_for_function("document.querySelector('#imp-resultado').innerText.includes('1 actualizadas')")
    assert errores == []


# ------------------------------------------------------------------------------------------------ Seguridad
def test_sin_sesion_solo_se_ve_el_ingreso_y_un_error_no_deja_entrar(servidor, navegador):
    """Sin sesión no se ve el menú, ni la barra, ni nada de la aplicación aunque se pida una dirección interna; una clave
    incorrecta muestra un error y no entra; la correcta lleva directo a la pantalla que se había pedido."""
    ctx = navegador.new_context(viewport={"width": 1500, "height": 900}, bypass_csp=True)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#admin/stock")
    pg.wait_for_selector(".login-tarjeta", state="visible")
    assert not pg.is_visible("#menu") and not pg.is_visible(".barra-sup") and not pg.is_visible("#vista-admin")
    pg.fill("#login-usuario", "admin")
    pg.fill("#login-clave", "mala")
    pg.click("#login-entrar")
    pg.wait_for_selector("#login-error:not([hidden])")
    assert "incorrectos" in pg.inner_text("#login-error") and pg.is_visible(".login-tarjeta")
    pg.fill("#login-usuario", "admin")
    pg.fill("#login-clave", CLAVE_ADMIN)
    pg.click("#login-entrar")
    pg.wait_for_selector("#vista-admin", state="visible")  # entró y cayó en la dirección que había pedido
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 6")
    assert not pg.is_visible(".login-tarjeta") and "Administrador" in pg.inner_text("#usuario-caja")
    # Salir: vuelve al ingreso y la sesión ya no sirve ni recargando.
    pg.click("#btn-salir")
    pg.wait_for_selector(".login-tarjeta", state="visible")
    pg.reload()
    pg.wait_for_selector(".login-tarjeta", state="visible")
    assert errores == []


def test_cada_perfil_ve_solo_lo_suyo_en_la_interfaz(servidor, navegador):
    """Recorre los tres perfiles con un navegador real, creándolos como lo haría el administrador:
    - PRIME: menú sin Administración ni Usuarios; si pide #admin/stock o #usuarios lo devuelve al inicio; en los avisos solo ve
      el botón que lleva al tablero (no los de las tablas).
    - CONSULTA: solo «Tablero de compras»; sin «Agregar oferta» ni «Elegir esta»; no descarga ningún Excel.
    - EXTERNO: solo «Productos que necesitamos» (sin precios); cualquier otra dirección lo devuelve ahí; descarga su Excel.
    Cada uno entra con una clave temporal y la pantalla le OBLIGA a cambiarla (no se puede cancelar)."""
    admin = _contexto(navegador, servidor, 1500, 900)
    claves = {}
    for usuario, rol in (("prime1", "prime"), ("consulta1", "consulta"), ("externo1", "externo")):
        r = admin.request.post(
            servidor + "/api/usuarios",
            data={
                "usuario": usuario,
                "nombre": f"Persona {rol}",
                "rol": rol,
                "cod_empresa": "1" if rol == "externo" else None,  # un proveedor siempre va ligado a una empresa
                "correo": f"{usuario}@prueba.com",
                "celular": f"310{len(claves) + 1:07d}",  # único por persona
            },
        )
        assert r.status == 201, r.text()
        claves[usuario] = r.json()["clave_temporal"]

    def entrar_como(usuario):
        ctx = navegador.new_context(viewport={"width": 1500, "height": 900}, bypass_csp=True)
        pg = ctx.new_page()
        pg.errores = []
        pg.on("pageerror", lambda e: pg.errores.append(str(e)))
        pg.goto(servidor + "/")
        pg.fill("#login-usuario", usuario)
        pg.fill("#login-clave", claves[usuario])
        pg.click("#login-entrar")
        pg.wait_for_selector("#dlg-clave[open]")
        pg.keyboard.press("Escape")  # con clave temporal, Esc NO cierra el cambio obligatorio
        pg.wait_for_timeout(250)
        assert pg.is_visible("#dlg-clave") and not pg.is_visible("#cl-cancelar")
        pg.fill("#cl-actual", claves[usuario])
        pg.fill("#cl-nueva", "OtraClave2026")
        pg.fill("#cl-repite", "OtraClave2026")
        pg.click("#cl-guardar")
        pg.wait_for_selector("#dlg-clave", state="hidden")
        return pg

    def menu(pg):
        return [t.strip() for t in pg.locator("#menu .menu-item:visible .txt").all_inner_texts()]

    # ---- PRIME
    pg = entrar_como("prime1")
    assert menu(pg) == [
        "Tablero de compras",
        "Tableros de control",
        "Agregar oferta",
        "Cargar datos",
        "Actualizar Excel",
        "Descargar OC (ganadores)",
        "Alternativas 2.º a 4.º",
        "Avisos de datos",
    ]
    for prohibida in ("#admin/stock", "#usuarios", "#proveedor"):
        pg.goto(servidor + "/" + prohibida)
        pg.wait_for_selector("#vista-inicio", state="visible")
        assert pg.url.endswith("#inicio")
    pg.click("#btn-avisos")
    pg.wait_for_selector(".cajon .aviso")
    botones = pg.locator(".cajon .btn-ir").all_inner_texts()
    assert (
        len(botones) == 1 and "tablero" in botones[0].lower()
    )  # el aviso «sin oferta»; los de tablas son del administrador
    assert pg.errores == []

    # ---- CONSULTA
    pg = entrar_como("consulta1")
    assert menu(pg) == ["Tablero de compras", "Tableros de control"]  # Consulta no descarga ningún Excel
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    pg.click("#chips .chip:has-text('Sin oferta')")
    pg.wait_for_function("document.querySelectorAll('.fila').length === 1")
    assert pg.locator(".btn-fila.agregar").count() == 0 and "cotizado" in pg.inner_text(".c-acciones")
    pg.click("#chips .chip:has-text('Con oferta')")
    pg.wait_for_function("document.querySelectorAll('.fila').length === 3")
    pg.locator(".fila").first.locator(".btn-fila").first.click()
    pg.wait_for_selector("#dlg-ofertas[open] .tarjeta, #dlg-ofertas[open] .detalle")
    assert pg.locator(".btn-elegir:not(.activa)").count() == 0 and pg.locator(".btn-quitar").count() == 0
    assert pg.locator("#dlg-ofertas button:has-text('Agregar oferta')").count() == 0
    pg.keyboard.press("Escape")
    assert pg.locator("#btn-descargar-comprar").count() == 0
    assert pg.locator(".cantidad-input").count() == 0  # solo ve la cantidad, no la edita
    pg.locator(".fila").first.locator(".enlace-empresa").click()
    pg.wait_for_selector("#dlg-empresa[open] .ficha-cifra")  # pero sí puede ver la información del proveedor
    pg.keyboard.press("Escape")
    assert pg.errores == []

    # ---- EXTERNO
    pg = entrar_como("externo1")
    assert menu(pg) == ["Productos que necesitamos"] and pg.url.endswith("#proveedor")
    pg.wait_for_function("document.querySelectorAll('#prov-tabla tbody tr').length === 4")
    assert [t.strip() for t in pg.locator("#prov-tabla thead th").all_inner_texts()] == [
        "Código",
        "Descripción",
    ]
    texto = pg.inner_text("#vista-proveedor").lower()
    assert "$" not in texto and "precio:" not in texto  # no hay precios en pantalla
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector("#vista-proveedor", state="visible")
    assert pg.url.endswith("#proveedor")
    with pg.expect_download() as d:
        pg.click("#prov-excel")
    assert d.value.suggested_filename.startswith(
        "FR-GDS-07_Ficha_Cotizacion_"
    )  # el Excel es la ficha oficial FR-GDS-07
    import tempfile
    from pathlib import Path

    import openpyxl

    destino = (
        Path(tempfile.mkdtemp()) / d.value.suggested_filename
    )  # (Playwright guarda la descarga sin extensión: se copia con su nombre)
    d.value.save_as(destino)
    ficha = openpyxl.load_workbook(destino).worksheets[0]
    pantalla = {c.strip() for c in pg.locator("#vista-proveedor td.p-cod").all_inner_texts()}
    assert ficha.title == "FICHA DE COTIZACIÓN" and pantalla  # trae justo los productos que se ven en la pantalla
    assert {ficha.cell(r, 1).value for r in range(12, 12 + len(pantalla))} == pantalla
    assert pg.errores == []


def test_gestion_de_usuarios_desde_la_pantalla(servidor, navegador):
    """El administrador crea un usuario en la pantalla «Usuarios»: ve la clave temporal UNA vez (y se borra al cerrar), el
    usuario aparece «Debe cambiar su clave»; puede restablecer su clave (con confirmación) y desactivarlo; y no puede
    eliminarse a sí mismo (su fila no tiene botón de eliminar)."""
    ctx = _contexto(navegador, servidor, 1500, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#usuarios")
    pg.wait_for_selector("#us-tabla tbody tr")
    assert pg.locator("#us-tabla tbody tr").count() == 1 and pg.locator("#us-perfiles .perfil-tarjeta").count() == 4
    assert pg.locator("#us-tabla tbody tr button[title='Eliminar']").count() == 0  # la propia fila no se puede eliminar

    # crear (con un error primero: usuario demasiado corto)
    pg.click("#us-nuevo")
    pg.wait_for_selector("#dlg-usuario[open]")  # se abre cuando llega la lista de proveedores: hay que esperarlo
    assert "Correo electrónico" in pg.inner_text("#dlg-usuario")  # (y que el formulario ya está pintado)
    assert "null" not in pg.inner_text("#dlg-usuario")  # replaceChildren escribe «null» si recibe null
    assert "no tiene configurado el envío automático" in pg.inner_text("#dlg-usuario")  # aviso: sin SMTP ni WhatsApp
    pg.fill("#us-usuario", "ab")
    pg.fill("#us-nombre", "Persona Prueba")
    pg.fill("#us-correo", "sin-arroba")
    pg.fill("#us-celular", "300 123 4567")
    pg.select_option("#us-rol", "externo")
    assert pg.is_visible("#us-empresa")  # el proveedor solo se ofrece a los externos
    pg.select_option(
        "#us-empresa", index=1
    )  # (un proveedor siempre va ligado a una empresa: sin elegirla el primer error sería ese)
    pg.click("#us-guardar")
    pg.wait_for_selector("#us-error:not([hidden])")
    assert "3 a 40" in pg.inner_text("#us-error")
    pg.fill("#us-usuario", "proveedor.uno")
    pg.click("#us-guardar")  # ahora el usuario es válido pero el correo no
    pg.wait_for_function("document.querySelector('#us-error').textContent.includes('correo')")
    pg.fill("#us-correo", "Proveedor@Farma.com")
    pg.select_option("#us-empresa", index=1)
    pg.click("#us-guardar")
    pg.wait_for_selector("#dlg-clave-temporal[open]")
    clave = pg.inner_text("#ct-clave")
    assert len(clave) == 10 and pg.inner_text("#ct-usuario") == "proveedor.uno"
    # sin SMTP ni WhatsApp configurados: se dice claro y queda el envío a mano por WhatsApp (mensaje ya escrito)
    envio = pg.inner_text("#ct-envio")
    assert "Correo: El envío de correo no está configurado" in envio and "WhatsApp: El envío automático" in envio
    enlace = pg.get_attribute("#ct-envio a", "href")
    assert enlace.startswith("https://wa.me/573001234567?text=") and clave in enlace
    pg.click("#dlg-clave-temporal [data-cerrar]")
    pg.wait_for_selector("#dlg-clave-temporal", state="hidden")
    assert pg.inner_text("#ct-clave") == "" and pg.locator("#ct-envio a").count() == 0  # nada queda en la pantalla
    fila = pg.locator("#us-tabla tbody tr", has_text="proveedor.uno")
    assert "Proveedor externo" in fila.inner_text() and "Debe cambiar su clave" in fila.inner_text()
    assert (
        "proveedor@farma.com" in fila.inner_text() and "+573001234567" in fila.inner_text()
    )  # el contacto se ve en la tabla

    # restablecer la clave: pide confirmación y da otra clave temporal distinta
    fila.locator("button[title='Restablecer la clave']").click()
    pg.wait_for_selector("#dlg-confirmar[open]")
    pg.click("#cf-ok")
    pg.wait_for_selector("#dlg-clave-temporal[open]")
    assert pg.inner_text("#ct-clave") != clave
    pg.click("#dlg-clave-temporal [data-cerrar]")

    # desactivar
    fila.locator("button[title='Editar']").click()
    pg.uncheck("#us-activo")
    pg.click("#us-guardar")
    pg.wait_for_selector("#dlg-usuario", state="hidden")
    pg.wait_for_selector("#us-tabla tbody tr:has-text('proveedor.uno'):has-text('Desactivado')")
    assert errores == []


def test_el_enlace_del_correo_siempre_pide_usuario_y_clave(servidor, navegador):
    """Con la sesión del administrador abierta en el navegador, abrir el enlace del correo («/?ingresar=1») NO entra
    directo: cierra esa sesión, muestra el ingreso con un aviso y limpia la dirección. Al entrar (aquí con el mismo
    usuario) y recargar, la sesión se mantiene: el enlace no se vuelve a aplicar."""
    ctx = _contexto(navegador, servidor, 1400, 900)  # el administrador ya tiene la sesión abierta en este navegador
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    assert ctx.request.get(servidor + "/api/sesion").ok  # (antes del enlace, la sesión es válida)
    pg.goto(servidor + "/?ingresar=1")
    pg.wait_for_selector(".login-tarjeta", state="visible")
    assert not pg.is_visible("#menu") and not pg.is_visible(".barra-sup")  # no entró a la aplicación
    assert "usuario y la clave que te enviamos" in pg.inner_text("#login-aviso")
    assert pg.evaluate("location.search") == ""  # la dirección quedó limpia
    assert ctx.request.get(servidor + "/api/sesion").status == 401  # la sesión anterior se cerró de verdad
    pg.fill("#login-usuario", "admin")
    pg.fill("#login-clave", CLAVE_ADMIN)
    pg.click("#login-entrar")
    pg.wait_for_selector("#usuario-caja", state="visible")
    assert pg.is_visible("#menu") and "Administrador" in pg.inner_text("#usuario-caja")
    pg.reload()  # ya sin «?ingresar=1»: sigue dentro
    pg.wait_for_selector("#usuario-caja", state="visible")
    assert pg.is_visible("#menu") and not pg.is_visible(".login-tarjeta")
    # Sin ninguna sesión previa, el enlace también lleva al ingreso.
    nuevo = navegador.new_context(viewport={"width": 1400, "height": 900}, bypass_csp=True).new_page()
    nuevo.goto(servidor + "/?ingresar=1")
    nuevo.wait_for_selector(".login-tarjeta", state="visible")
    assert errores == []


@pytest.fixture()
def con_superusuario(monkeypatch):
    """Define el superusuario en la configuración ANTES de que arranque el servidor de la prueba."""
    monkeypatch.setenv("COMPRAS_SUPERUSUARIO", "superadmin")
    monkeypatch.setenv("COMPRAS_SUPERUSUARIO_CLAVE", "Super-Prueba77*")


def test_el_superusuario_entra_por_la_pantalla_con_su_clave_y_ve_todo(con_superusuario, servidor, navegador):
    """El arranque crea al superusuario con la clave del .env: entra por el formulario (sin pedirle cambiar la clave),
    ve TODO el menú del administrador y, en Usuarios, aparece marcado y sin botones para editarlo, restablecerlo o borrarlo."""
    ctx = navegador.new_context(viewport={"width": 1500, "height": 900}, bypass_csp=True)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/")
    pg.wait_for_selector(".login-tarjeta", state="visible")
    pg.fill("#login-usuario", "superadmin")
    pg.fill("#login-clave", "Super-Prueba77*")
    pg.click("#login-entrar")
    pg.wait_for_selector("#menu", state="visible")
    assert not pg.is_visible("#dlg-clave[open]")  # no le pide cambiar la clave
    opciones = pg.locator("#menu .menu-item:visible .txt").all_inner_texts()
    assert opciones == [
        "Tablero de compras",
        "Tableros de control",
        "Administración",
        "Usuarios",
        "Productos que necesitamos",  # el administrador también ve la pantalla del proveedor
        "Agregar oferta",
        "Cargar datos",
        "Actualizar Excel",
        "Descargar OC (ganadores)",
        "Alternativas 2.º a 4.º",
        "Ofertas de proveedores",
        "Avisos de datos",
    ]
    pg.goto(servidor + "/#usuarios")
    fila = pg.locator("#us-tabla tbody tr", has_text="superadmin")
    fila.wait_for()
    assert "superusuario" in fila.inner_text() and "Se define en .env" in fila.inner_text()
    assert fila.locator("button").count() == 0  # nada que editar, restablecer ni eliminar
    assert (
        pg.locator("#us-tabla tbody tr", has_text="Administrador").first.locator("button").count() >= 2
    )  # el resto sí
    assert errores == []


def test_actualizar_todo_y_cantidad_editable_se_escribe_y_se_ve_completa(servidor, navegador):
    """Botón «Actualizar todo» (anota la hora) y la cantidad a comprar: es una caja donde se ESCRIBE (con 8 dígitos a la vista, sin
    flechitas), Enter guarda y cambia el total, Esc cancela, y un botón permite volver a la cantidad calculada."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    assert pg.inner_text("#tablero-hora") == ""
    pg.click("#btn-actualizar-todo")
    pg.wait_for_function("document.querySelector('#tablero-hora').textContent.startsWith('Actualizado a las')")

    fila = pg.locator(".fila[data-cod='A1']")
    caja = fila.locator(".cantidad-input")
    assert (
        caja.get_attribute("type") == "text" and caja.input_value() == "80"
    )  # una caja de texto: sin flechitas encima de las cifras
    caja.click()
    caja.press("Control+a")
    caja.type("10000000")
    assert caja.input_value() == "10000000" and caja.evaluate(
        "e => e.scrollWidth <= e.clientWidth"
    )  # caben los 8 dígitos
    caja.press("Control+a")
    caja.type("2a5b0")  # las letras no entran
    assert caja.input_value() == "250"
    caja.press("ArrowUp")
    caja.press("Shift+ArrowUp")
    assert caja.input_value() == "261"  # ↑ suma 1 y Shift+↑ suma 10
    caja.press("Escape")
    assert caja.input_value() == "80" and fila.locator(".cantidad-guardar").is_disabled()  # Esc cancela
    caja.click()
    caja.press("Control+a")
    caja.type("250")
    caja.press("Enter")
    pg.wait_for_selector("#dlg-confirmar[open]")  # antes de guardar pregunta «¿Está seguro de la cantidad a comprar?»
    pg.click("#cf-ok")
    pg.wait_for_selector(".fila[data-cod='A1'] .cantidad-editable.es-manual")
    assert fila.locator(".cantidad-input").input_value() == "250"
    assert "21.250" in fila.locator(".c-total").inner_text()  # $85 × 250
    assert "calculada 80" in fila.locator(".cantidad-restaurar").inner_text()
    fila.locator(".cantidad-restaurar").click()
    pg.wait_for_function("document.querySelector(\".fila[data-cod='A1'] .cantidad-input\").value === '80'")
    assert "6.800" in fila.locator(".c-total").inner_text() and fila.locator(".cantidad-restaurar").count() == 0
    assert errores == []


def test_la_cantidad_y_la_pantalla_se_ven_bien_en_celular(servidor, navegador):
    """En 390 px de ancho la cantidad pasa a su propia fila con caja y botón grandes (44 px), caben los 8 dígitos y la página no se desborda."""
    ctx = _contexto(navegador, servidor, 390, 844)
    pg = ctx.new_page()
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    caja = pg.locator(".fila[data-cod='A1'] .cantidad-input")
    caja.click()
    caja.press("Control+a")
    caja.type("10000000")
    assert caja.evaluate("e => e.scrollWidth <= e.clientWidth") and caja.bounding_box()["height"] >= 44
    assert pg.locator(".fila[data-cod='A1'] .cantidad-guardar").bounding_box()["height"] >= 44
    assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert (
        pg.locator(".ruta-actual").bounding_box()["height"] < 26
    )  # la ruta de la barra de arriba cabe en UN renglón (no se parte)


def test_ficha_de_la_empresa_desde_la_fila_y_desde_mejor_oferta(servidor, navegador):
    """Al pulsar el NOMBRE del proveedor se abre su ficha: contacto, cifras y sus ofertas (con buscador). Funciona desde la fila y desde «Mejor oferta»."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    pg.locator(".fila[data-cod='A1'] .enlace-empresa").click()  # la mejor oferta de A1 es BETA SAS
    pg.wait_for_selector("#dlg-empresa[open] .ficha-cifra")
    assert pg.inner_text("#emp-titulo") == "BETA SAS" and pg.inner_text("#emp-sub").startswith("Código 2")
    assert pg.locator(".ficha-cifra strong").all_inner_texts() == [
        "1",
        "1",
        "1",
        "$6.800",
    ]  # ofertas, mejores, se le compra, inversión
    assert "no tiene teléfono ni correo" in pg.inner_text("#emp-cuerpo")  # las del Excel base aún no lo traen
    assert (
        pg.locator(".fo-fila").count() == 1
        and "ALFA PRODUCTO" in pg.inner_text(".fo-fila")
        and "Se le compra" in pg.inner_text(".fo-fila")
    )
    pg.fill(".ficha-buscar", "zzz")
    assert pg.locator(".fo-fila").count() == 0 and "Ninguna oferta coincide" in pg.inner_text(".vacio-ficha")
    pg.click("#dlg-empresa footer [data-cerrar]")  # (Esc dentro de un buscador primero borra el texto)
    pg.wait_for_selector("#dlg-empresa", state="hidden")
    # desde «Mejor oferta»
    pg.locator(".fila[data-cod='A1'] .btn-fila", has_text="Mejor oferta").click()
    pg.wait_for_selector("#dlg-ofertas[open] .enlace-empresa")
    pg.locator("#dlg-ofertas .enlace-empresa").first.click()
    pg.wait_for_selector("#dlg-empresa[open] .ficha-cifra")
    assert pg.inner_text("#emp-titulo") == "BETA SAS"
    assert pg.locator("#dlg-empresa").evaluate(
        "e => e.matches(':modal')"
    )  # la ficha queda ENCIMA de la ventana de ofertas
    assert errores == []


def test_portafolio_muestra_el_nombre_de_la_empresa_y_administracion_no_deja_repetir(servidor, navegador):
    """Portafolio: junto a COD_EMPRESA sale el NOMBRE DE LA EMPRESA (se busca por él). Al agregar: no se repite empresa + producto, y una empresa
    nueva exige teléfono y correo."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#admin/portafolio")
    pg.wait_for_selector("#adm-tabla tbody tr[data-id]")
    titulos = [t.strip() for t in pg.locator("#adm-tabla thead th").all_inner_texts() if t.strip()]
    assert titulos[:4] == ["#", "COD_EMPRESA", "NOMBRE DE LA EMPRESA", "COD_PRODUCTO"]
    assert pg.locator("#adm-tabla tbody tr").first.locator("td.extra").inner_text() == "ALFA SAS"
    pg.fill("#adm-q", "beta")
    pg.wait_for_function(
        "[...document.querySelectorAll('#adm-tabla tbody tr[data-id] td.extra')].every(td => td.textContent === 'BETA SAS')"
    )
    assert pg.locator("#adm-tabla tbody tr[data-id]").count() >= 1
    pg.fill("#adm-q", "")
    # agregar una oferta que esa empresa ya tiene: se rechaza con un mensaje claro y la ventana queda abierta
    pg.click("#adm-agregar")
    pg.fill("#af-COD_EMPRESA", "1")
    pg.fill("#af-COD_PRODUCTO", "A1")
    pg.fill("#af-VALOR", "99")
    pg.click("#af-guardar")
    pg.wait_for_selector("#af-error:not([hidden])")
    assert "Ya existe" in pg.inner_text("#af-error") and pg.locator("#dlg-admin-fila[open]").count() == 1
    pg.keyboard.press("Escape")
    # una empresa nueva SIN teléfono ni correo: se rechaza
    pg.goto(servidor + "/#admin/empresas")
    pg.wait_for_selector("#adm-tabla tbody tr[data-id]")
    pg.click("#adm-agregar")
    pg.fill("#af-CODIGO_EMPRESA", "9")
    pg.fill("#af-NOMBRE", "NUEVE SAS")
    pg.click("#af-guardar")
    pg.wait_for_selector("#af-error:not([hidden])")
    assert "obligatorio" in pg.inner_text("#af-error")
    pg.fill("#af-TELEFONO", "300 123 4567")
    pg.fill("#af-CORREO", "nueve@empresa.com")
    pg.click("#af-guardar")
    pg.wait_for_function("document.querySelectorAll('#adm-tabla tbody tr[data-id]').length === 6")
    assert errores == []


def test_la_animacion_del_viaje_al_crear_un_usuario_y_al_restablecer_la_clave(servidor, navegador):
    """Mientras el servidor genera el usuario y la clave temporal sale la ventana con la animación (con la escena y un texto real); al llegar se
    cierra y aparecen los datos. Si algo falla, la animación se cierra y el formulario sigue abierto con el error. Lo mismo al restablecer."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#usuarios")
    pg.wait_for_selector("#vista-usuarios tbody tr")

    def formulario(usuario, correo, celular):
        pg.click("#us-nuevo")
        pg.wait_for_selector("#dlg-usuario[open]")
        pg.fill("#us-usuario", usuario)
        pg.fill("#us-nombre", f"Persona {usuario}")
        pg.fill("#us-correo", correo)
        pg.fill("#us-celular", celular)

    formulario("ana.viaje", "ana@x.com", "3205550001")
    pg.click("#us-guardar")
    pg.wait_for_selector("#dlg-viaje[open]")
    assert pg.evaluate(
        "!!document.querySelector('#vj-escena').shadowRoot.querySelector('#heartMascot')"
    )  # la escena está dibujada
    assert "Creando el usuario" in pg.inner_text("#vj-titulo") and pg.inner_text("#vj-texto") != ""
    caja = pg.locator("#dlg-viaje").bounding_box()
    escena = pg.locator("#vj-escena").bounding_box()
    assert (
        caja["width"] <= 365 and caja["height"] <= 330
    )  # la ventana de la animación es PEQUEÑA (360 px de ancho; antes 560)
    assert 300 <= escena["width"] <= 345 and escena["height"] <= 200  # y la escena se ajusta a ese ancho
    pg.wait_for_selector("#dlg-clave-temporal[open]")  # al llegar se muestran el usuario y la clave
    assert pg.locator("#dlg-viaje[open]").count() == 0
    assert pg.inner_text("#ct-usuario") == "ana.viaje" and len(pg.inner_text("#ct-clave")) == 10
    pg.click("#dlg-clave-temporal [data-cerrar] >> nth=-1")

    # un error (el usuario ya existe): la animación se cierra y el formulario sigue abierto, con el mensaje y lo escrito
    formulario("admin", "otro@x.com", "3205550002")
    pg.click("#us-guardar")
    pg.wait_for_selector("#dlg-viaje[open]")
    pg.wait_for_selector("#us-error:not([hidden])")
    assert pg.locator("#dlg-viaje[open]").count() == 0 and pg.locator("#dlg-usuario[open]").count() == 1
    assert "Ya existe" in pg.inner_text("#us-error") and pg.input_value("#us-correo") == "otro@x.com"
    pg.keyboard.press("Escape")

    # restablecer la clave: también sale la animación y luego los datos nuevos
    pg.locator("#us-tabla tbody tr", has_text="ana.viaje").locator("button[title='Restablecer la clave']").click()
    pg.click("dialog.confirmar[open] .btn-peligro")
    pg.wait_for_selector("#dlg-viaje[open]")
    assert "Restableciendo" in pg.inner_text("#vj-titulo")
    pg.wait_for_selector("#dlg-clave-temporal[open]")
    assert pg.inner_text("#ct-usuario") == "ana.viaje" and len(pg.inner_text("#ct-clave")) == 10
    assert "restableció" in pg.get_attribute("#ct-envio a", "href").replace(
        "%C3%B3", "ó"
    )  # el botón manual de WhatsApp lleva el texto de restablecer
    assert errores == []


def test_con_reducir_movimiento_la_espera_muestra_solo_texto_y_barra(servidor, navegador):
    """Si el sistema pide reducir movimiento, no se dibuja la escena animada: solo el texto y la barra de progreso."""
    ctx = navegador.new_context(viewport={"width": 1400, "height": 900}, bypass_csp=True, reduced_motion="reduce")
    assert ctx.request.post(servidor + "/api/sesion", data={"usuario": "admin", "clave": CLAVE_ADMIN}).ok
    pg = ctx.new_page()
    pg.goto(servidor + "/#usuarios")
    pg.wait_for_selector("#vista-usuarios tbody tr")
    pg.click("#us-nuevo")
    pg.fill("#us-usuario", "carla.quieta")
    pg.fill("#us-nombre", "Carla")
    pg.fill("#us-correo", "carla@x.com")
    pg.fill("#us-celular", "3205550004")
    pg.click("#us-guardar")
    pg.wait_for_selector("#dlg-viaje[open]")
    assert not pg.is_visible("#vj-escena") and pg.is_visible("#vj-progreso")
    pg.wait_for_selector("#dlg-clave-temporal[open]")
    assert pg.inner_text("#ct-usuario") == "carla.quieta"


def test_editar_la_cantidad_no_mueve_la_fila_ni_toca_el_stock(servidor, navegador):
    """Al guardar una cantidad, la fila se queda DONDE ESTABA (aunque su total cambie o le pongas 0): no se reordena ni desaparece de la lista.
    Si ya no cumple el filtro se atenúa con un aviso, y solo «Actualizar todo» la saca. Y el stock («20 en stock · máx 100») nunca cambia."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")

    def orden():
        return pg.locator(".fila").evaluate_all("els => els.map(e => e.dataset.cod)")

    def cuenta():
        return pg.locator("#chips .chip", has_text="Por comprar").inner_text().split()[-1]

    def stock():
        return pg.locator(".fila[data-cod='A1'] .medidor .txt").inner_text().replace("\n", " ")

    antes = orden()
    assert antes[0] == "A1" and cuenta() == "4"  # A1 es el de mayor inversión: ($85 × 80)
    assert stock() == "20 en stock máx 100"

    # una cantidad enorme en OTRO producto cambiaría su puesto si la lista se reordenara: no debe moverse
    caja = pg.locator(".fila[data-cod='0041'] .cantidad-input")
    caja.click()
    caja.press("Control+a")
    caja.type("9999999")
    caja.press("Enter")
    pg.wait_for_selector("#dlg-confirmar[open]")  # antes de guardar pregunta «¿Está seguro de la cantidad a comprar?»
    pg.click("#cf-ok")
    pg.wait_for_selector(".fila[data-cod='0041'] .cantidad-editable.es-manual")
    assert orden() == antes  # nadie saltó de lugar
    assert any(
        "no cambian" in x for x in pg.locator(".toast").all_inner_texts()
    )  # el aviso dice que el stock y el máximo no cambian

    # poner 0 mientras se ve «Por comprar»: la fila se queda, atenuada y con aviso; el contador de arriba sí baja
    caja = pg.locator(".fila[data-cod='A1'] .cantidad-input")
    caja.click()
    caja.press("Control+a")
    caja.type("0")
    caja.press("Enter")
    pg.wait_for_selector("#dlg-confirmar[open]")  # antes de guardar pregunta «¿Está seguro de la cantidad a comprar?»
    pg.click("#cf-ok")
    pg.wait_for_selector(".fila[data-cod='A1'].fuera-filtro")
    assert "Ya no cumple este filtro" in pg.inner_text(".fila[data-cod='A1'] .fuera-aviso")
    assert orden() == antes and pg.locator(".fila[data-cod='A1'] .cantidad-input").input_value() == "0"
    pg.wait_for_function(
        "[...document.querySelectorAll('#chips .chip')].find(c => c.textContent.includes('Por comprar')).textContent.trim().endsWith('3')"
    )
    assert stock() == "20 en stock máx 100"  # el stock y el máximo siguen igual con cantidad 0

    # se puede restaurar ahí mismo, sin que la fila se vaya
    pg.locator(".fila[data-cod='A1'] .cantidad-restaurar").click()
    pg.wait_for_function("document.querySelector(\".fila[data-cod='A1'] .cantidad-input\").value === '80'")
    assert (
        orden() == antes
        and pg.locator(".fila[data-cod='A1'].fuera-filtro").count() == 0
        and stock() == "20 en stock máx 100"
    )

    # solo al actualizar la lista se reordena (0041 pasa al primer puesto por su gran cantidad)
    pg.click("#btn-actualizar-todo")
    pg.wait_for_function("document.querySelector('.fila').dataset.cod === '0041'")
    assert errores == []


def test_etiquetas_nuevo_en_productos_y_empresas(servidor, navegador):
    """Lo que el sistema ve por primera vez lleva la pastilla «Nuevo» (producto en la fila; empresa junto a su nombre y en su ficha). Lo de siempre no."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    assert pg.locator(".etq-nuevo").count() == 0  # al arrancar, todo lo que había es «de siempre»
    assert ctx.request.post(
        servidor + "/api/productos",
        data={"cod": "M1", "descripcion": "PRODUCTO RECIEN AGREGADO", "stock_max": 10, "existencias": 0},
    ).ok
    assert ctx.request.post(
        servidor + "/api/ofertas", data={"cod_producto": "A1", "empresa_nueva": "RECIEN LLEGADA SAS", "valor": 10}
    ).ok
    pg.click("#btn-actualizar-todo")
    pg.wait_for_function("document.querySelector('#tablero-hora').textContent.startsWith('Actualizado')")
    pg.click("#chips .chip:has-text('Todos')")
    pg.wait_for_selector(".fila[data-cod='M1']")
    assert pg.locator(".fila[data-cod='M1'] .cod-fila .etq-nuevo").count() == 1  # producto nuevo
    assert (
        pg.locator(".fila[data-cod='A1'] .cod-fila .etq-nuevo").count() == 0
        and pg.locator(".fila[data-cod='C3'] .etq-nuevo").count() == 0
    )
    assert (
        pg.locator(".fila[data-cod='A1'] .prov-fila .etq-nuevo").count() == 1
    )  # la empresa nueva es ahora la mejor oferta de A1
    pg.locator(".fila[data-cod='A1'] .enlace-empresa").click()
    pg.wait_for_selector("#dlg-empresa[open] .ficha-cifra")
    assert pg.locator("#emp-titulo .etq-nuevo").count() == 1 and "RECIEN LLEGADA SAS" in pg.inner_text("#emp-titulo")
    pg.click("#dlg-empresa footer [data-cerrar]")
    pg.locator(
        ".fila[data-cod='A1'] .btn-fila", has_text="Mejor oferta"
    ).click()  # en «Mejor oferta» (la empresa nueva) también lleva la etiqueta
    pg.wait_for_selector("#dlg-ofertas[open] .enlace-empresa")
    assert pg.locator("#dlg-ofertas .prov-fila .etq-nuevo").count() == 1
    assert "RECIEN LLEGADA SAS" in pg.locator("#dlg-ofertas .prov-fila").inner_text()
    assert errores == []


def test_stock_suficiente_aviso_de_compra_menor_y_confirmacion_de_la_cantidad(servidor, navegador):
    """B2 está completo (10 de 10): sale «Stock suficiente». Al guardar una cantidad sale «¿Está seguro de la cantidad a comprar?»: «Revisar» no guarda;
    si es menor que la recomendada, avisa; «Sí, guardar» guarda y la fila queda con el aviso «Menos de lo recomendado»."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    pg.click("#chips .chip:has-text('Todos')")
    pg.wait_for_selector(".fila[data-cod='B2']")
    b2 = pg.locator(".fila[data-cod='B2']")
    assert (
        "Stock suficiente" in b2.locator(".c-comprar").inner_text()
        and b2.locator(".cantidad-input").input_value() == "0"
    )
    assert "Stock suficiente" not in pg.locator(".fila[data-cod='A1']").inner_text()  # a A1 sí le falta (20 de 100)

    caja = pg.locator(".fila[data-cod='A1'] .cantidad-input")
    caja.click()
    caja.press("Control+a")
    caja.type("50")
    caja.press("Enter")
    pg.wait_for_selector("#dlg-confirmar[open]")
    texto = pg.inner_text("#dlg-confirmar")
    assert "¿Está seguro de la cantidad a comprar?" in texto and "Vas a comprar 50 unidades" in texto
    assert "20 en stock (máx 100)" in texto and "recomendado es comprar 80" in texto and "tendrías 70" in texto
    assert "menos de lo recomendado" in texto and "faltarían 30" in texto  # el aviso de compra menor
    assert "El stock máximo no cambia" in texto
    pg.click("#cf-cancelar")  # «Revisar»: no se guarda nada
    pg.wait_for_selector("#dlg-confirmar", state="hidden")
    assert caja.input_value() == "50" and pg.locator(".fila[data-cod='A1'] .cantidad-editable.es-manual").count() == 0
    assert (
        ctx.request.get(servidor + "/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"][0][
            "editada"
        ]
        is False
    )
    caja.press("Enter")
    pg.wait_for_selector("#dlg-confirmar[open]")
    pg.click("#cf-ok")  # «Sí, guardar»
    pg.wait_for_selector(".fila[data-cod='A1'] .cantidad-editable.es-manual")
    assert "Menos de lo recomendado (80)" in pg.locator(".fila[data-cod='A1'] .cantidad-aviso").inner_text()
    assert "20 en stock máx 100" in pg.locator(".fila[data-cod='A1'] .medidor .txt").inner_text().replace("\n", " ")

    # con la cantidad recomendada (o más) ya no hay aviso de compra menor
    caja = pg.locator(".fila[data-cod='A1'] .cantidad-input")
    caja.click()
    caja.press("Control+a")
    caja.type("80")
    caja.press("Enter")
    pg.wait_for_selector("#dlg-confirmar[open]")
    assert "menos de lo recomendado" not in pg.inner_text("#dlg-confirmar")
    pg.click("#cf-ok")
    pg.wait_for_function("!document.querySelector(\".fila[data-cod='A1'] .cantidad-aviso\")")
    assert errores == []


def test_las_ventanas_emergentes_se_pueden_mover_arrastrando_la_cabecera(servidor, navegador):
    """Se arrastra la cabecera y la ventana se mueve; nunca sale de la pantalla; doble clic y cerrar/abrir la devuelven al centro."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    pg.locator(".fila").first.locator(".enlace-empresa").click()
    pg.wait_for_selector("#dlg-empresa[open] .ficha-cifra")
    dlg = pg.locator("#dlg-empresa")
    quieta = "e => Promise.all(e.getAnimations().map(a => a.finished))"  # la ventana se desliza al abrirse: se mide cuando ya se detuvo
    dlg.evaluate(quieta)
    inicio = dlg.bounding_box()
    cab = pg.locator("#dlg-empresa .v-cab").bounding_box()
    centro = (cab["x"] + 200, cab["y"] + cab["height"] / 2)
    pg.mouse.move(*centro)
    pg.mouse.down()
    pg.mouse.move(centro[0] - 150, centro[1] + 80, steps=8)
    pg.mouse.up()
    movida = dlg.bounding_box()
    assert (
        abs(movida["x"] - (inicio["x"] - 150)) <= 2 and abs(movida["y"] - (inicio["y"] + 80)) <= 2
    )  # se movió lo arrastrado
    pg.mouse.move(centro[0] - 150, centro[1] + 80)
    pg.mouse.down()
    pg.mouse.move(-2000, -2000, steps=6)  # intenta sacarla de la pantalla
    pg.mouse.up()
    fuera = dlg.bounding_box()
    assert (
        fuera["y"] >= -1 and fuera["x"] + fuera["width"] >= 119
    )  # queda a la vista una franja de la cabecera para volver a agarrarla
    ancho_cab = pg.locator("#dlg-empresa .v-cab").bounding_box()["width"]
    pg.locator("#dlg-empresa .v-cab").dblclick(
        position={"x": ancho_cab - 90, "y": 20}
    )  # (en la franja visible, junto al botón de cerrar)
    assert (
        abs(dlg.bounding_box()["x"] - inicio["x"]) <= 2 and abs(dlg.bounding_box()["y"] - inicio["y"]) <= 2
    )  # doble clic: al centro
    pg.mouse.move(centro[0], centro[1])
    pg.mouse.down()
    pg.mouse.move(centro[0] + 100, centro[1] + 60, steps=5)
    pg.mouse.up()
    assert dlg.bounding_box()["x"] > inicio["x"] + 90
    pg.click("#dlg-empresa footer [data-cerrar]")
    pg.locator(".fila").first.locator(".enlace-empresa").click()
    pg.wait_for_selector("#dlg-empresa[open] .ficha-cifra")
    dlg.evaluate(quieta)
    assert (
        abs(dlg.bounding_box()["x"] - inicio["x"]) <= 2 and abs(dlg.bounding_box()["y"] - inicio["y"]) <= 2
    )  # al abrirla de nuevo vuelve al centro


def test_las_ventanas_emergentes_se_adaptan_al_celular(servidor, navegador):
    """En pantallas de 390 y 360 px de ancho ninguna de las 12 ventanas se sale de la pantalla, desborda hacia los lados ni tiene botones
    más chicos que 44 px (el nombre de la empresa, que es un enlace dentro de un texto, tiene el área táctil ampliada)."""
    abrir = {
        "dlg-agregar": "#btn-agregar",
        "dlg-cargar": "#btn-cargar",
        "dlg-usuario": "#us-nuevo",
        "dlg-admin-fila": "#adm-agregar",
        "dlg-importar": "#btn-importar",
        "dlg-historial": "#adm-historial",
    }
    rutas = {
        "dlg-usuario": "#usuarios",
        "dlg-admin-fila": "#admin/stock",
        "dlg-importar": "#admin/stock",
        "dlg-historial": "#admin/stock",
    }
    medir = """(id) => { const d = document.getElementById(id); const b = d.getBoundingClientRect(); const cu = d.querySelector('.v-cuerpo');
        const chicos = [...d.querySelectorAll('button:not(.enlace-empresa)')].filter(x => x.offsetParent !== null && x.getBoundingClientRect().height < 43.5).map(x => (x.textContent || x.getAttribute('aria-label') || '').trim().slice(0, 20));
        return {dentro: b.left >= 0 && b.right <= innerWidth + 1 && b.top >= 0 && b.bottom <= innerHeight + 1, desborda: (cu ? cu.scrollWidth > cu.clientWidth + 1 : false) || d.scrollWidth > d.clientWidth + 1, chicos}; }"""
    for ancho, alto in ((390, 844), (360, 640)):
        ctx = navegador.new_context(
            viewport={"width": ancho, "height": alto}, bypass_csp=True, has_touch=True, is_mobile=True
        )
        assert ctx.request.post(servidor + "/api/sesion", data={"usuario": "admin", "clave": CLAVE_ADMIN}).ok
        pg = ctx.new_page()
        problemas = []
        for did in (
            "dlg-agregar",
            "dlg-cargar",
            "dlg-ofertas",
            "dlg-empresa",
            "dlg-usuario",
            "dlg-admin-fila",
            "dlg-importar",
            "dlg-historial",
            "dlg-clave",
            "dlg-clave-temporal",
            "dlg-prov-lista",
            "dlg-alternativas",
            "dlg-pendientes",
            "dlg-confirmar",
            "dlg-viaje",
        ):
            pg.goto(servidor + "/" + rutas.get(did, "#tablero"))
            pg.wait_for_selector("#menu", state="attached")
            pg.wait_for_timeout(300)
            if did == "dlg-ofertas":
                pg.wait_for_selector(".fila")
                pg.locator(".fila").first.locator("button:has-text('Mejor oferta')").click()
                pg.wait_for_selector("#dlg-ofertas[open] .v-cuerpo > *")
            elif did == "dlg-empresa":
                pg.wait_for_selector(".fila")
                pg.locator(".fila").first.locator(".enlace-empresa").click()
                pg.wait_for_selector("#dlg-empresa[open] .fo-fila")
            elif did in abrir:
                try:
                    pg.wait_for_selector(abrir[did], state="visible", timeout=2000)
                    pg.click(abrir[did], timeout=2000)
                    pg.wait_for_selector(f"#{did}[open]", timeout=2000)
                except Exception:  # (en el celular el menú está cerrado: se abre la ventana directamente)
                    pg.evaluate(f"document.getElementById('{did}').showModal()")
            else:
                pg.evaluate(f"document.getElementById('{did}').showModal()")
            pg.wait_for_timeout(350)
            r = pg.evaluate(medir, did)
            if not r["dentro"] or r["desborda"] or r["chicos"]:
                problemas.append((did, r))
            pg.evaluate(f"document.getElementById('{did}').close()")
        assert not problemas, f"{ancho}x{alto}: {problemas}"
        ctx.close()


def test_el_inicio_lleva_los_logos_en_las_esquinas_y_las_certificaciones_en_el_pie(servidor, navegador):
    """Inicio: el logo de Pabón arriba a la izquierda, el del Centro de Cuidados arriba a la derecha y, en el centro del pie, las certificaciones
    (solo en el inicio). Todo cabe sin barra de desplazamiento. En celular los logos pasan a una fila arriba y las certificaciones a todo el ancho."""
    ctx = _contexto(navegador, servidor, 1456, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/")
    pg.wait_for_selector(".bienvenida-datos li")
    pg.wait_for_function(
        "[...document.querySelectorAll('.bienvenida-logos img, .pie-certs img')].every(i => i.complete && i.naturalWidth > 0)"
    )
    pabon, centro, titulo = (pg.locator(s).bounding_box() for s in (".logo-pabon", ".logo-centro", "#inicio-titulo"))
    tarjeta = pg.locator(".bienvenida").bounding_box()
    assert pg.locator(".bienvenida-logo, .bienvenida-sede").count() == 0  # el corazón y el texto del centro ya no están
    assert (
        pabon["y"] + pabon["height"] <= titulo["y"] and centro["y"] + centro["height"] <= titulo["y"]
    )  # los dos logos quedan ARRIBA del título: no se pisan con él
    assert (
        pabon["x"] < tarjeta["x"] + 40 and centro["x"] + centro["width"] > tarjeta["x"] + tarjeta["width"] - 40
    )  # en las esquinas de la tarjeta
    assert abs(pabon["y"] - centro["y"]) < 20  # a la misma altura, arriba
    marca, certs, derecha = (pg.locator(s).bounding_box() for s in (".pie-marca", ".pie-certs", ".pie > :last-child"))
    assert (
        marca["x"] + marca["width"] <= certs["x"] + 1 and certs["x"] + certs["width"] <= derecha["x"] + 1
    )  # en el centro del pie, entre la sede y la marca
    assert not pg.evaluate(
        "document.documentElement.scrollHeight > innerHeight"
    )  # el pie más alto no hace crecer la página
    assert pg.evaluate("document.querySelector('.pie-certs img').alt").startswith("Certificaciones de la Clínica")
    pg.click("#btn-entrar")  # en el tablero las certificaciones no salen
    pg.wait_for_selector("#vista-tablero:not([hidden])")
    assert not pg.locator(".pie-certs").is_visible()
    pg.click("a.logo-inicio, #menu a[href='#inicio'], .ruta a")  # y al volver al inicio, vuelven
    pg.wait_for_selector("#vista-inicio:not([hidden])")
    assert pg.locator(".pie-certs").is_visible()
    assert errores == []

    movil = _contexto(navegador, servidor, 390, 844).new_page()
    movil.goto(servidor + "/")
    movil.wait_for_selector(".bienvenida-datos li")
    movil.wait_for_function(
        "[...document.querySelectorAll('.bienvenida-logos img, .pie-certs img')].every(i => i.complete && i.naturalWidth > 0)"
    )
    pabon, centro, titulo = (movil.locator(s).bounding_box() for s in (".logo-pabon", ".logo-centro", "#inicio-titulo"))
    assert (
        pabon["y"] + pabon["height"] <= titulo["y"] + 1 and centro["y"] + centro["height"] <= titulo["y"] + 1
    )  # arriba del título, en una fila
    assert abs(pabon["y"] - centro["y"]) < 40 and pabon["x"] < centro["x"]
    certs = movil.locator(".pie-certs").bounding_box()
    assert certs["width"] > 300 and certs["x"] >= 0 and certs["x"] + certs["width"] <= 391  # a todo el ancho del pie
    assert not movil.evaluate("document.documentElement.scrollWidth > innerWidth")


def test_descargar_la_oc_y_las_alternativas_desde_el_menu(servidor, navegador):
    """Los dos botones nuevos del menú bajan la orden de compra (con el ganador de cada producto) y el libro de alternativas (2.º, 3.º y 4.º)."""
    import tempfile
    from pathlib import Path

    import openpyxl

    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    carpeta = Path(tempfile.mkdtemp())

    def bajar(boton):
        with pg.expect_download() as d:
            pg.click(boton)
        destino = carpeta / d.value.suggested_filename
        d.value.save_as(destino)
        return destino

    oc = bajar("#btn-oc")
    assert oc.name.startswith("OC_") and oc.suffix == ".xlsx"
    libro = openpyxl.load_workbook(oc)
    assert (
        libro.sheetnames == ["VALORES", "DINAMICA", "ORDENES"] and libro["ORDENES"].max_row == 4
    )  # 3 productos ganadores + el encabezado
    pg.click("#btn-alternativas")  # abre la ventana «Alternativas 2.º a 4.º», que baja el libro
    pg.wait_for_selector("#dlg-alternativas[open] #alt-descargar")
    alt = bajar("#alt-descargar")
    assert alt.name.startswith("ALTERNATIVAS_2_a_4_") and alt.suffix == ".xlsx"
    nombres = openpyxl.load_workbook(alt).sheetnames
    assert nombres == [
        f"{h} {p}.º" for p in (2, 3, 4) for h in ("VALORES", "DINAMICA", "ORDENES")
    ]  # las 3 hojas de la OC por cada puesto
    assert pg.locator("#btn-exportar").count() == 0  # «Exportar VALORES» ya no existe (esa hoja va dentro de la OC)
    assert errores == []


def test_las_descargas_que_tardan_avisan_preparando_y_no_se_piden_dos_veces(servidor, navegador):
    """Mientras el servidor arma la orden de compra el botón se apaga y sale «Preparando…» (antes el navegador esperaba en silencio); pulsarlo otra vez
    no hace un segundo pedido; al llegar se baja el archivo y sale «Listo». Se simula un servidor lento demorando la petición 1,5 s en el navegador."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    ctx.add_init_script(
        """
        const _fetch = window.fetch; window.__pedidosOc = 0;
        window.fetch = async (u, o) => { if (String(u).includes('/api/exportar/oc')) { window.__pedidosOc++; await new Promise(r => setTimeout(r, 1500)); } return _fetch(u, o); };
        """
    )
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    with pg.expect_download() as d:
        pg.click("#btn-oc")
        pg.wait_for_selector("#btn-oc.preparando")
        assert pg.get_attribute("#btn-oc", "aria-busy") == "true"
        pg.wait_for_selector(".toast.info:has-text('Preparando la orden de compra')")
        pg.evaluate("document.getElementById('btn-oc').click()")  # un segundo clic mientras prepara
    assert d.value.suggested_filename.startswith("OC_")
    assert pg.evaluate("window.__pedidosOc") == 1  # solo se pidió una vez
    pg.wait_for_selector(".toast.ok:has-text('Listo: OC_')")
    assert (
        pg.locator("#btn-oc.preparando").count() == 0 and pg.get_attribute("#btn-oc", "aria-busy") is None
    )  # el botón vuelve a estar disponible
    pg.wait_for_selector(
        ".toast.info:has-text('Preparando')", state="detached"
    )  # y el aviso «Preparando…» se desvanece y se quita
    assert errores == []


def test_si_la_descarga_falla_se_dice_por_que_y_el_boton_se_recupera(servidor, navegador):
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    pg.route(
        "**/api/exportar/alternativas",
        lambda r: r.fulfill(
            status=500, content_type="application/json", body='{"detail": "Prueba de error del servidor"}'
        ),
    )
    pg.click("#btn-alternativas")
    pg.wait_for_selector("#dlg-alternativas[open] #alt-descargar")
    pg.click("#alt-descargar")
    pg.wait_for_selector(".toast.error:has-text('Prueba de error del servidor')")
    assert pg.locator("#alt-descargar.preparando").count() == 0  # el botón se recupera para poder reintentar
    pg.wait_for_selector(".toast.info:has-text('Preparando')", state="detached")


def test_el_filtro_nuevos_muestra_lo_nuevo_y_el_panel_marca_las_empresas_nuevas(servidor, navegador):
    """En la fila de filtros hay un «Nuevos» con su contador: trae los productos nuevos y los que tienen una empresa nueva como mejor oferta. En
    «Dónde comprar» las empresas nuevas llevan su etiqueta."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    chip = pg.locator("#chips .chip", has_text="Nuevos")
    assert (
        chip.count() == 1
        and chip.locator(".n").inner_text() == "0"
        and not chip.evaluate("e => e.classList.contains('hay-nuevos')")
    )
    assert ctx.request.post(
        servidor + "/api/productos",
        data={"cod": "M1", "descripcion": "PRODUCTO RECIEN AGREGADO", "stock_max": 10, "existencias": 10},
    ).ok
    assert ctx.request.post(
        servidor + "/api/ofertas", data={"cod_producto": "C3", "empresa_nueva": "RECIEN LLEGADA SAS", "valor": 10}
    ).ok
    pg.click("#btn-actualizar-todo")
    pg.wait_for_function("document.querySelector('#tablero-hora').textContent.startsWith('Actualizado')")
    assert chip.locator(".n").inner_text() == "2" and chip.evaluate(
        "e => e.classList.contains('hay-nuevos')"
    )  # M1 (producto nuevo) y C3 (empresa nueva)
    chip.click()
    pg.wait_for_selector(".fila[data-cod='M1']")
    assert sorted(pg.locator(".fila").evaluate_all("els => els.map(e => e.dataset.cod)")) == ["C3", "M1"]
    assert (
        pg.locator(".fila[data-cod='M1'] .cod-fila .etq-nuevo").count() == 1
        and pg.locator(".fila[data-cod='C3'] .prov-fila .etq-nuevo").count() == 1
    )
    assert pg.locator("#barras .etq-nuevo").count() == 1  # «Dónde comprar»: solo la empresa que llegó hoy
    assert "RECIEN LLEGADA SAS" in pg.locator("#barras .barra-prov:has(.etq-nuevo)").inner_text()
    pg.click("#chips .chip:has-text('Todos')")
    pg.wait_for_function("document.querySelectorAll('.fila').length > 2")
    assert errores == []


def test_el_proveedor_sube_su_ficha_y_el_administrador_la_revisa_y_la_aprueba(servidor, navegador, tmp_path):
    """El recorrido completo, con un navegador real: el PROVEEDOR descarga su ficha, escribe sus precios y la sube desde su pantalla (queda
    pendiente: no compite). El ADMINISTRADOR ve la insignia en el menú, abre «Ofertas de proveedores», revisa cada precio frente a la mejor oferta de
    hoy y aprueba: los precios pasan al tablero. El proveedor ve su ficha como «Aprobada». El administrador también ve la pantalla del proveedor."""
    import openpyxl

    admin = _contexto(navegador, servidor, 1400, 900)
    r = admin.request.post(
        servidor + "/api/usuarios",
        data={
            "usuario": "gama.prov",
            "nombre": "Gama Proveedor",
            "rol": "externo",
            "cod_empresa": "3",
            "correo": "gama.prov@prueba.com",
            "celular": "3100000099",
        },
    )
    assert r.status == 201, r.text()
    temporal = r.json()["clave_temporal"]
    gama = navegador.new_context(viewport={"width": 1400, "height": 900}, bypass_csp=True)
    assert gama.request.post(servidor + "/api/sesion", data={"usuario": "gama.prov", "clave": temporal}).ok
    assert gama.request.put(servidor + "/api/sesion/clave", data={"actual": temporal, "nueva": "OtraClave2026"}).ok
    pv = gama.new_page()
    errores = []
    pv.on("pageerror", lambda e: errores.append(str(e)))
    pv.goto(servidor + "/#proveedor")
    pv.wait_for_selector("#prov-tabla tbody tr")
    assert pv.is_visible("#prov-envio") and not pv.is_visible("#prov-nota-admin")  # el proveedor ve «Enviar mi oferta»

    # 1) descarga la ficha, escribe SUS precios (A1 a $70: mejor que el mejor de hoy, $85) y la sube
    with pv.expect_download() as d:
        pv.click("#prov-excel")
    ficha = tmp_path / "ficha.xlsx"
    d.value.save_as(ficha)
    libro = openpyxl.load_workbook(ficha)
    hoja = libro.worksheets[0]
    for fila in range(12, 40):
        if hoja.cell(fila, 1).value == "A1":
            hoja.cell(fila, 7).value, hoja.cell(fila, 11).value = 70, "X10"
    libro.save(ficha)
    pv.set_input_files("#prov-archivo", str(ficha))
    pv.wait_for_selector("#prov-resultado .resultado-ok")
    assert "pendiente de aprobación" in pv.inner_text(
        "#prov-resultado"
    ) and "1 producto(s) con precio" in pv.inner_text("#prov-resultado")
    assert "Pendiente de aprobación" in pv.inner_text("#prov-envios")
    # todavía NO compite: el mejor de A1 sigue siendo BETA
    assert (
        admin.request.get(servidor + "/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"][0][
            "mejor"
        ]["empresa"]
        == "BETA SAS"
    )

    # 2) el administrador ve la insignia, revisa y aprueba
    pa = admin.new_page()
    pa.on("pageerror", lambda e: errores.append(str(e)))
    pa.goto(servidor + "/#tablero")
    pa.wait_for_selector(".fila")
    pa.wait_for_function(
        "document.querySelector('#badge-pendientes') && !document.querySelector('#badge-pendientes').hidden"
    )
    assert pa.inner_text("#badge-pendientes") == "1"
    pa.click("#btn-pendientes")
    pa.wait_for_selector("#dlg-pendientes[open] .pend-tarjeta.pendiente")
    assert "GAMA LTDA" in pa.inner_text(".pend-tarjeta") and "1 producto(s) con precio" in pa.inner_text(
        ".pend-tarjeta"
    )
    pa.click(".pend-tarjeta .btn")  # «Revisar»
    pa.wait_for_selector("#dlg-pendientes .pend-tabla tbody tr")
    fila = pa.locator("#dlg-pendientes .pend-tabla tbody tr").first.inner_text()
    assert (
        "A1" in fila and "$70" in fila.replace(" ", "") and "BETA SAS" in fila and "Mejora" in fila
    )  # su precio frente a la mejor oferta de hoy
    assert pa.is_visible("#pend-aprobar") and pa.is_visible("#pend-rechazar")
    pa.click("#pend-aprobar")
    pa.wait_for_selector("#dlg-confirmar[open]")
    assert "¿Aprobar esta ficha?" in pa.inner_text("#dlg-confirmar")
    assert "se pondrá en contacto con él" in pa.inner_text(
        "#dlg-confirmar"
    )  # avisa que se le manda un correo al proveedor
    pa.click("#cf-ok")
    pa.wait_for_selector(
        ".toast:has-text('correo')"
    )  # y la pantalla dice cómo salió (en esta prueba no hay correo configurado)
    # al confirmar, «Aprobar» y «Rechazar» desaparecen y la ventana se queda en la ficha, que ahora dice «Aprobada» y ofrece «Restaurar»
    pa.wait_for_selector("#pend-restaurar", state="visible")
    assert pa.is_hidden("#pend-aprobar") and pa.is_hidden("#pend-rechazar")
    assert "Aprobada" in pa.inner_text("#pend-sub") and pa.is_visible("#pend-volver")
    pa.wait_for_function("document.querySelector('#badge-pendientes').hidden")
    assert (
        admin.request.get(servidor + "/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"][0][
            "mejor"
        ]["empresa"]
        == "GAMA LTDA"
    )

    # RESTAURAR: deshace la aprobación y la deja otra vez pendiente de revisión, con las ofertas como estaban
    pa.click("#pend-restaurar")
    pa.wait_for_selector("#dlg-confirmar[open]")
    assert "¿Restaurar esta ficha?" in pa.inner_text("#dlg-confirmar") and "no se puede retirar" in pa.inner_text(
        "#dlg-confirmar"
    )
    assert "revisando de nuevo sus ofertas" in pa.inner_text(
        "#dlg-confirmar"
    )  # avisa del correo que se le manda al proveedor
    pa.click("#cf-ok")
    pa.wait_for_selector(".toast:has-text('Ficha restaurada')")
    pa.wait_for_selector(
        ".toast:has-text('correo')"
    )  # y la pantalla dice cómo salió (en esta prueba no hay correo configurado)
    pa.wait_for_selector("#pend-aprobar", state="visible")  # vuelven «Aprobar» y «Rechazar»; «Restaurar» se va
    assert (
        pa.is_visible("#pend-rechazar")
        and pa.is_hidden("#pend-restaurar")
        and "Pendiente" in pa.inner_text("#pend-sub")
    )
    pa.wait_for_function(
        "document.querySelector('#badge-pendientes') && !document.querySelector('#badge-pendientes').hidden"
    )
    assert pa.inner_text("#badge-pendientes") == "1"
    assert (
        admin.request.get(servidor + "/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"][0][
            "mejor"
        ]["empresa"]
        == "BETA SAS"
    )  # la mejor oferta de A1 vuelve a ser la de antes
    pa.click("#pend-aprobar")  # y se puede aprobar otra vez
    pa.wait_for_selector("#dlg-confirmar[open]")
    pa.click("#cf-ok")
    pa.wait_for_selector("#pend-restaurar", state="visible")
    pa.click("#pend-volver")
    pa.wait_for_selector("#dlg-pendientes .pend-tarjeta.aprobada")  # en la lista, la ficha está aprobada
    pa.click("#dlg-pendientes footer [data-cerrar]")

    # 3) ahora SÍ compite: la mejor oferta de A1 es la de GAMA
    assert (
        admin.request.get(servidor + "/api/productos", params={"filtro": "todos", "tam": 100}).json()["items"][0][
            "mejor"
        ]["empresa"]
        == "GAMA LTDA"
    )
    pv.reload()
    pv.wait_for_selector("#prov-envios .estado-lote.aprobada")  # el proveedor ve su ficha aprobada

    # 4) el administrador también ve la pantalla del proveedor, sin la parte de subir
    pa.goto(servidor + "/#proveedor")
    pa.wait_for_selector("#prov-tabla tbody tr")
    assert pa.is_visible("#prov-nota-admin") and not pa.is_visible("#prov-envio")
    assert "Productos que necesitamos" in pa.inner_text("#menu")
    assert errores == []


def _proveedor_conectado(servidor, navegador, admin, usuario, celular, cod_empresa="3"):
    """Crea un usuario proveedor (como lo haría el administrador), le cambia la clave temporal y devuelve su navegador ya con la sesión iniciada."""
    r = admin.request.post(
        servidor + "/api/usuarios",
        data={
            "usuario": usuario,
            "nombre": f"Persona {usuario}",
            "rol": "externo",
            "cod_empresa": cod_empresa,
            "correo": f"{usuario}@prueba.com",
            "celular": celular,
        },
    )
    assert r.status == 201, r.text()
    temporal = r.json()["clave_temporal"]
    ctx = navegador.new_context(viewport={"width": 1400, "height": 900}, bypass_csp=True)
    assert ctx.request.post(servidor + "/api/sesion", data={"usuario": usuario, "clave": temporal}).ok
    assert ctx.request.put(servidor + "/api/sesion/clave", data={"actual": temporal, "nueva": "OtraClave2026"}).ok
    return ctx


def _bajar(pagina, selector, carpeta):
    """Pulsa un botón de descarga y guarda el archivo con su nombre real; devuelve la ruta."""
    with pagina.expect_download() as d:
        pagina.click(selector)
    destino = carpeta / d.value.suggested_filename
    d.value.save_as(destino)
    return destino


def test_el_proveedor_ve_sin_oferta_y_nuevos_con_buscador_y_descarga(servidor, navegador, tmp_path):
    """En «Productos que necesitamos» el proveedor tiene los botones «Sin oferta» y «Nuevos» (con su número). Cada uno abre una ventana con la lista (solo
    código y descripción), un buscador y el botón para descargar la ficha con esos productos, lista para llenar y subir."""
    import openpyxl

    admin = _contexto(navegador, servidor, 1400, 900)
    assert admin.request.post(
        servidor + "/api/productos",
        data={"cod": "M1", "descripcion": "INSUMO NUEVO QUE FALTA", "stock_max": 10, "existencias": 0},
    ).ok
    pv = _proveedor_conectado(servidor, navegador, admin, "lista.prov", "3100000071").new_page()
    errores = []
    pv.on("pageerror", lambda e: errores.append(str(e)))
    pv.goto(servidor + "/#proveedor")
    pv.wait_for_selector("#prov-tabla tbody tr")
    assert (
        pv.inner_text("#prov-n-sin") == "2" and pv.inner_text("#prov-n-nuevos") == "1"
    )  # D4 y M1 sin oferta · M1 nuevo

    pv.click("#prov-btn-sin")
    pv.wait_for_selector("#dlg-prov-lista[open] .lb-tabla tbody tr")
    assert "Productos sin oferta" in pv.inner_text("#pl-titulo")
    assert [h.strip() for h in pv.locator("#pl-cuerpo .lb-tabla th").all_inner_texts()] == [
        "Código",
        "Descripción",
    ]  # solo eso: nada de precios ni de otros proveedores
    assert sorted(pv.locator("#pl-cuerpo .lb-tabla td .cod").all_inner_texts()) == ["D4", "M1"]
    pv.fill("#pl-cuerpo .lb-q", "nuevo")  # el buscador
    pv.wait_for_function("document.querySelectorAll('#pl-cuerpo .lb-tabla tbody tr').length === 1")
    assert pv.inner_text("#pl-cuerpo .lb-tabla td .cod") == "M1" and "1 producto(s)" in pv.inner_text(
        "#pl-cuerpo .lb-cuenta"
    )
    pv.fill("#pl-cuerpo .lb-q", "zzzz-no-existe")
    pv.wait_for_selector("#pl-cuerpo .vacio-tabla")
    assert "Nada coincide" in pv.inner_text("#pl-cuerpo .vacio-tabla")
    pv.fill("#pl-cuerpo .lb-q", "nuevo")  # y el Excel que se baja es el de lo que se está buscando
    pv.wait_for_function("document.querySelectorAll('#pl-cuerpo .lb-tabla tbody tr').length === 1")
    ficha = _bajar(pv, "#pl-cuerpo .lb-barra a.btn", tmp_path)
    assert ficha.name.endswith("_SIN_OFERTA.xlsx")
    libro = openpyxl.load_workbook(ficha)
    assert (
        libro.worksheets[0]["A12"].value == "M1"
        and libro.worksheets[0]["A13"].value != "D4"
        and libro["SUMIPABON"]["B1"].value == "3"
    )  # solo M1, y es SU ficha
    pv.click("#dlg-prov-lista footer [data-cerrar]")

    pv.click("#prov-btn-nuevos")
    pv.wait_for_selector("#dlg-prov-lista[open] .lb-tabla tbody tr")
    assert "Productos nuevos" in pv.inner_text("#pl-titulo") and pv.locator(
        "#pl-cuerpo .lb-tabla td .cod"
    ).all_inner_texts() == ["M1"]
    assert _bajar(pv, "#pl-cuerpo .lb-barra a.btn", tmp_path).name.endswith("_NUEVOS.xlsx")
    assert errores == []


def test_alternativas_para_el_administrador_sin_las_listas_de_sin_oferta_y_nuevos(servidor, navegador, tmp_path):
    """El botón del menú abre una ventana SOLO de alternativas 2.º a 4.º: explica y baja el libro de 9 hojas. «Sin oferta» y «Nuevos» ya no van aquí
    (están en «Productos que necesitamos»)."""
    import openpyxl

    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    pg.click("#btn-alternativas")
    pg.wait_for_selector("#dlg-alternativas[open] #alt-descargar")
    assert pg.locator("#alt-tabs, #dlg-alternativas .pestana").count() == 0  # sin pestañas
    texto = pg.inner_text("#dlg-alternativas")
    assert "9 hojas" in texto and "Se ajusta a lo que elijas" in texto
    assert "Sin oferta" not in texto and "Nuevos" not in texto and "buscador" not in texto.lower()
    libro = _bajar(pg, "#alt-descargar", tmp_path)
    assert libro.name.startswith("ALTERNATIVAS_2_a_4_")
    assert openpyxl.load_workbook(libro).sheetnames == [
        f"{h} {p}.º" for p in (2, 3, 4) for h in ("VALORES", "DINAMICA", "ORDENES")
    ]
    assert errores == []


def test_ofertas_de_proveedores_buscar_descargar_y_rechazar_con_motivo(servidor, navegador, tmp_path):
    """El administrador busca en las fichas, abre una, busca sus productos, baja el Excel y la rechaza: el motivo es obligatorio (si no lo escribe, se
    lo vuelve a pedir), se intenta avisar por correo y el proveedor ve «Rechazada» con el motivo."""
    import io

    import openpyxl

    admin = _contexto(navegador, servidor, 1400, 900)
    prov = _proveedor_conectado(servidor, navegador, admin, "ofer.prov", "3100000072")
    libro = openpyxl.Workbook()
    libro.active.append(["COD_PRODUCTO", "VALOR", "PRESENTACION"])
    libro.active.append(["A1", 70, "X10"])
    libro.active.append(["C3", 60, "X1"])
    memoria = io.BytesIO()
    libro.save(memoria)
    r = prov.request.post(
        servidor + "/api/proveedor/ofertas?nombre=mi_ficha.xlsx",
        data=memoria.getvalue(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status == 201, r.text()

    pa = admin.new_page()
    errores = []
    pa.on("pageerror", lambda e: errores.append(str(e)))
    pa.goto(servidor + "/#tablero")
    pa.wait_for_selector(".fila")
    pa.click("#btn-pendientes")
    pa.wait_for_selector("#dlg-pendientes[open] .pend-tarjeta")
    pa.fill("#pend-q", "gama")  # el buscador de la lista
    assert pa.locator("#dlg-pendientes .pend-tarjeta").count() == 1
    pa.fill("#pend-q", "zzz-no-existe")
    pa.wait_for_selector("#dlg-pendientes .vacio-tabla")
    assert "Nada coincide" in pa.inner_text("#pend-cuerpo")
    pa.fill("#pend-q", "mi_ficha")  # también por el nombre del archivo
    assert pa.locator("#dlg-pendientes .pend-tarjeta").count() == 1
    pa.click(".pend-tarjeta .btn")
    pa.wait_for_selector("#dlg-pendientes .pend-tabla tbody tr")
    assert pa.locator("#dlg-pendientes .pend-tabla tbody tr").count() == 2 and pa.is_visible("#pend-excel")
    pa.fill("#pend-q", "c3")  # el buscador del detalle
    pa.wait_for_function("document.querySelectorAll('#dlg-pendientes .pend-tabla tbody tr').length === 1")
    assert "C3" in pa.inner_text(".pend-tabla tbody")
    pa.fill("#pend-q", "")
    pa.wait_for_function("document.querySelectorAll('#dlg-pendientes .pend-tabla tbody tr').length === 2")
    excel = _bajar(pa, "#pend-excel", tmp_path)
    assert excel.name.startswith("OFERTA_GAMA_LTDA_") and excel.suffix == ".xlsx"
    assert openpyxl.load_workbook(excel).sheetnames == ["OFERTA", "DATOS DE LA FICHA"]

    pa.click("#pend-rechazar")
    pa.wait_for_selector("#dlg-confirmar[open]")
    pa.click("#cf-ok")  # sin escribir el motivo
    pa.wait_for_selector(".toast.error:has-text('Escribe el motivo')")
    pa.wait_for_selector("#dlg-confirmar[open] #cf-cuerpo input")  # se lo vuelve a pedir
    pa.fill("#cf-cuerpo input", "El precio de A1 está fuera de lo acordado")
    pa.click("#cf-ok")
    pa.wait_for_selector(
        ".toast.error:has-text('el correo no salió')"
    )  # (el servidor de pruebas no tiene correo configurado: se dice, pero el rechazo vale)
    pa.wait_for_selector("#pend-restaurar", state="visible")  # se queda en la ficha: «Aprobar» y «Rechazar» ya no están
    assert (
        pa.is_hidden("#pend-aprobar") and pa.is_hidden("#pend-rechazar") and "Rechazada" in pa.inner_text("#pend-sub")
    )
    assert "Rechazada: El precio de A1 está fuera de lo acordado" in pa.inner_text("#pend-cuerpo")
    pa.click("#pend-volver")
    pa.wait_for_selector("#dlg-pendientes .pend-tarjeta.rechazada")
    assert "Motivo: El precio de A1 está fuera de lo acordado" in pa.inner_text(".pend-tarjeta.rechazada")

    pv = prov.new_page()
    pv.goto(servidor + "/#proveedor")
    pv.wait_for_selector("#prov-envios .estado-lote.rechazada")
    assert "Motivo: El precio de A1 está fuera de lo acordado" in pv.inner_text("#prov-envios")
    assert errores == []


def test_crear_un_usuario_proveedor_agregando_un_proveedor_nuevo_desde_la_pantalla(servidor, navegador):
    """En «Usuarios», un proveedor debe elegir su empresa; si no está en la lista, la opción «Agregar un proveedor nuevo…» pide su nombre, teléfono y
    correo (propone los de la persona), la agrega y la liga. Un nombre que ya existe se rechaza."""
    ctx = _contexto(navegador, servidor, 1500, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#usuarios")
    pg.wait_for_selector("#us-tabla tbody tr")
    pg.click("#us-nuevo")
    pg.wait_for_selector("#dlg-usuario[open]")
    pg.fill("#us-usuario", "labo.nuevo")
    pg.fill("#us-nombre", "Persona del Laboratorio")
    pg.fill("#us-correo", "laboratorio@nuevo.com")
    pg.fill("#us-celular", "3100000073")
    pg.select_option("#us-rol", "externo")
    assert "Proveedor *" in pg.inner_text("#dlg-usuario") and not pg.is_visible("#us-prov-nuevo")
    opciones = pg.locator("#us-empresa option").all_inner_texts()
    assert opciones[0] == "Elige un proveedor…" and opciones[-1] == "➕ Agregar un proveedor nuevo…"
    pg.click("#us-guardar")  # sin elegir proveedor
    pg.wait_for_selector("#us-error:not([hidden])")
    assert "Elige el proveedor" in pg.inner_text("#us-error")
    pg.select_option("#us-empresa", "__nuevo__")
    assert pg.is_visible("#us-prov-nuevo")
    assert (
        pg.input_value("#us-pn-tel") == "3100000073" and pg.input_value("#us-pn-correo") == "laboratorio@nuevo.com"
    )  # propone el contacto de la persona
    pg.fill("#us-pn-nombre", "ALFA S.A.S.")  # uno que YA existe (con otra escritura)
    pg.click("#us-guardar")
    pg.wait_for_function("document.querySelector('#us-error').textContent.includes('Ya existe')")
    assert "ALFA SAS" in pg.inner_text("#us-error") and pg.is_visible(
        "#dlg-usuario"
    )  # no se creó nada y lo escrito no se pierde
    pg.fill("#us-pn-nombre", "LABORATORIO NUEVO E2E SAS")
    pg.click("#us-guardar")
    pg.wait_for_selector("#dlg-clave-temporal[open]")
    nombres = [e["nombre"] for e in ctx.request.get(servidor + "/api/empresas").json()]
    assert "LABORATORIO NUEVO E2E SAS" in nombres  # ya es un proveedor más del sistema
    pg.click("#dlg-clave-temporal [data-cerrar]")
    pg.wait_for_selector("#us-tabla tbody tr:has-text('labo.nuevo')")
    assert (
        "LABORATORIO NUEVO E2E SAS" in pg.locator("#us-tabla tbody tr", has_text="labo.nuevo").inner_text()
    )  # el usuario quedó ligado a ella
    assert errores == []


def test_ajustes_de_pantalla_sin_elegidos_sin_comprar_en_proveedor_sumipabon_grande_y_logos_nuevos(servidor, navegador):
    """El tablero ya no tiene «Elegidos por ti»; «Productos que necesitamos» no usa la palabra «comprar» y su contador funciona (antes escribía en el
    de «Dónde comprar», que tenía el mismo id); SUMIPABON se ve grande; y el logo de la Clínica es el vector nuevo (con «Clínica Pabón»)."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#inicio")
    pg.wait_for_selector(".bienvenida-datos li")
    assert (
        float(pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#inicio-titulo')).fontSize)")) >= 60
    )  # SUMIPABON en grande
    assert (
        float(pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.marca strong')).fontSize)")) >= 18
    )  # y en el menú
    pg.wait_for_function(
        "[...document.querySelectorAll('img.logo-pabon, img.marca-logo')].every(i => i.complete && i.naturalWidth > 0)"
    )
    ratio = pg.evaluate(
        "(() => { const i = document.querySelector('img.logo-pabon'); return i.naturalWidth / i.naturalHeight; })()"
    )
    assert (
        2.0 < ratio < 2.3 and pg.get_attribute("img.logo-pabon", "alt") == "Clínica Pabón"
    )  # el vector nuevo: corazón + «Clínica Pabón»
    assert (
        pg.evaluate("document.querySelector('img.marca-logo').naturalWidth") >= 500
    )  # el del menú es de alta resolución

    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    assert [c.split("\n")[0].strip() for c in pg.locator("#chips .chip").all_inner_texts()] == [
        "Por comprar",
        "Con oferta",
        "Sin oferta",
        "Nuevos",
        "Todos",
    ]
    assert "Elegidos" not in pg.inner_text("#chips")
    cuenta_tablero = pg.inner_text("#prov-cuenta")

    pg.goto(servidor + "/#proveedor")
    pg.wait_for_selector("#prov-tabla tbody tr")
    assert "comprar" not in pg.inner_text("#vista-proveedor").lower()  # la palabra «comprar» no va en esta pantalla
    assert pg.inner_text("#prov-total").endswith("producto(s)") and pg.inner_text("#prov-total")[0].isdigit()
    assert pg.get_attribute("#prov-btn-nuevos", "title") == "Productos nuevos que la Clínica necesita"
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    assert pg.inner_text("#prov-cuenta") == cuenta_tablero and "producto(s)" not in pg.inner_text(
        "#prov-cuenta"
    )  # el de «Dónde comprar» no se pisa
    assert errores == []


def _excel_con_otros_nombres(tmp_path):
    """Los 5 Excel de prueba copiados con nombres DISTINTOS a los originales (como los tendría una persona): {tabla: ruta}."""
    import shutil

    from app.config import ARCHIVOS_EXCEL

    origen = tmp_path / "origen"
    origen.mkdir()
    crear_excel_sintetico(origen)
    nombres = {
        "stock": "Stock septiembre.xlsx",
        "existencias": "existencias hoy.xlsx",
        "empresas": "Empresas actualizado.xlsx",
        "ficha": "Ficha cotizacion 2026.xlsx",
        "portafolio": "PORTAFOLIO_final.xlsx",
    }
    rutas = {}
    for clave, nuevo in nombres.items():
        shutil.copy(origen / ARCHIVOS_EXCEL[clave], origen / nuevo)
        rutas[clave] = str(origen / nuevo)
    return rutas


def test_sin_excel_la_pantalla_explica_y_se_suben_los_cinco_de_una_vez(servidor_vacio, navegador, tmp_path):
    """El proyecto ya NO trae los Excel: sin ellos, el tablero dice «Todavía no hay datos» y ofrece «Subir los Excel». Se eligen los 5 juntos (con
    nombres distintos a los originales), el sistema reconoce a qué tabla va cada uno, los sube y el tablero se llena."""
    rutas = _excel_con_otros_nombres(tmp_path)
    ctx = _contexto(navegador, servidor_vacio, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor_vacio + "/#tablero")
    pg.wait_for_function("document.querySelector('.vacio')?.innerText.includes('Todavía no hay datos')", timeout=15000)
    assert "Todavía no hay datos" in pg.inner_text(".vacio") and "necesito estos Excel" in pg.inner_text(".vacio")
    assert "data/excel" not in pg.inner_text(".vacio")  # ya no manda a copiar archivos a una carpeta
    pg.wait_for_selector(".vacio .checklist-fila")  # el sistema PIDE por nombre cada Excel, con su estado
    assert pg.locator(".vacio .checklist-fila").count() == 5 and pg.locator(".vacio .checklist-fila.falta").count() == 4
    assert (
        pg.locator(".vacio .checklist-etiqueta.obligatorio").count() == 4
        and pg.locator(".vacio .checklist-etiqueta.opcional").count() == 1
    )
    assert "Faltan 4 Excel obligatorio(s)" in pg.inner_text(".vacio .checklist-resumen")
    for archivo in ("05-STOCK.xlsx", "06-EXISTENCIAS.xlsx", "EMPRESA.xlsx", "PORTAFOLIO.xlsx", "FICHA_COTIZACION.xlsx"):
        assert archivo in pg.inner_text(".vacio .checklist")
    pg.click("#vacio-subir")
    pg.wait_for_selector("#dlg-importar[open] #imp-archivos")
    assert pg.is_disabled("#imp-subir-lote")  # sin archivos no se puede subir
    assert pg.locator("#imp-checklist .checklist-fila").count() == 5  # la misma lista dentro de la ventana de carga
    pg.set_input_files("#imp-archivos", list(rutas.values()))
    pg.wait_for_selector(".imp-lote-fila")
    assert pg.eval_on_selector_all(".imp-lote-fila select", "els => els.map(e => e.value)") == [
        "stock",
        "existencias",
        "empresas",
        "ficha",
        "portafolio",
    ]
    assert pg.locator(".imp-lote-fila.sin-tabla").count() == 0
    assert "Con estos archivos se llenan las 5 tablas" in pg.inner_text("#imp-lote-resumen") and pg.is_enabled(
        "#imp-subir-lote"
    )
    pg.click("#imp-subir-lote")
    pg.wait_for_function("document.querySelectorAll('#imp-resultado li').length === 5", timeout=60000)
    assert pg.locator(".imp-lote-fila").count() == 0  # lo subido sale de la lista
    # la lista se pone al día un instante DESPUÉS de mostrar el resultado (pide de nuevo las tablas): se espera, no se verifica al vuelo
    pg.wait_for_function("document.querySelectorAll('#imp-checklist .checklist-fila.ok').length === 5", timeout=30000)
    assert "Ya está todo lo obligatorio" in pg.inner_text("#imp-checklist")
    pg.click("#dlg-importar .cerrar-modal")
    pg.wait_for_selector(".fila")  # el tablero ya muestra productos
    assert pg.locator(".vacio").count() == 0
    assert errores == []


def test_subir_varios_excel_reconoce_por_el_nombre_deja_corregir_y_sigue_si_uno_falla(servidor, navegador, tmp_path):
    rutas = _excel_con_otros_nombres(tmp_path)
    import shutil

    misterio = tmp_path / "origen" / "misterio.xlsx"
    shutil.copy(rutas["existencias"], misterio)  # un nombre que no dice nada: hay que elegir la tabla
    roto = tmp_path / "origen" / "stock roto.xlsx"
    roto.write_bytes(b"esto no es un Excel")  # el nombre dice «stock», pero el archivo está dañado
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila")
    pg.click("#btn-importar")
    pg.wait_for_selector("#dlg-importar[open] #imp-archivos")
    pg.set_input_files("#imp-archivos", [rutas["empresas"], str(misterio), str(roto)])
    pg.wait_for_selector(".imp-lote-fila")
    assert pg.eval_on_selector_all(".imp-lote-fila select", "els => els.map(e => e.value)") == ["empresas", "", "stock"]
    assert pg.locator(".imp-lote-fila.sin-tabla").count() == 1 and pg.is_disabled(
        "#imp-subir-lote"
    )  # falta elegir la tabla del «misterio»
    assert "sin tabla" in pg.inner_text("#imp-lote-resumen")
    pg.select_option(".imp-lote-fila.sin-tabla select", "existencias")
    assert (
        pg.is_enabled("#imp-subir-lote")
        and "3 de las 5 tablas" in pg.inner_text("#imp-lote-resumen")
        and "Portafolio" in pg.inner_text("#imp-lote-resumen")
    )
    pg.click(".imp-lote-fila:first-child button")  # quitar el primero (Empresas)...
    assert pg.locator(".imp-lote-fila").count() == 2
    pg.set_input_files("#imp-archivos", [rutas["empresas"]])  # ...y volver a elegirlo: se suma a la lista
    assert pg.locator(".imp-lote-fila").count() == 3
    pg.click("#imp-subir-lote")
    pg.wait_for_selector("#imp-resultado .imp-errores")
    assert pg.locator("#imp-resultado li").count() == 3  # 2 importaciones bien (Existencias y Empresas) + 1 error
    assert "stock roto.xlsx" in pg.inner_text("#imp-resultado .imp-errores")  # y dice cuál falló
    assert pg.locator(".imp-lote-fila").count() == 1 and "stock roto.xlsx" in pg.inner_text(
        ".imp-lote-fila"
    )  # solo queda lo que falló, para corregirlo
    assert errores == []


def test_el_mensaje_de_pantalla_vacia_sale_aunque_la_lista_llegue_antes_que_el_resumen(servidor_vacio, navegador):
    """Antes, si la lista de productos llegaba antes que el resumen, el tablero escribía «Nada coincide con lo que buscas» y nunca lo corregía: sin Excel,
    lo primero que se veía era un mensaje equivocado. Aquí el resumen llega MUY tarde a propósito: igual debe terminar diciendo «Todavía no hay datos»."""
    ctx = _contexto(navegador, servidor_vacio, 1400, 900)
    pg = ctx.new_page()

    def resumen_lento(route):
        time.sleep(1.5)
        route.continue_()

    pg.route("**/api/resumen", resumen_lento)
    pg.goto(servidor_vacio + "/#tablero")
    pg.wait_for_selector(".vacio")  # primero llega la lista (vacía)
    pg.wait_for_function("document.querySelector('.vacio')?.innerText.includes('Todavía no hay datos')", timeout=15000)
    assert "Nada coincide" not in pg.inner_text("#filas") and pg.locator("#vacio-subir").count() == 1


def test_la_lista_de_excel_se_pone_al_dia_al_subir_solo_algunos(servidor_vacio, navegador, tmp_path):
    """Si solo se suben algunos Excel, la lista dice cuáles ya están (con sus filas) y cuáles obligatorios siguen faltando."""
    rutas = _excel_con_otros_nombres(tmp_path)
    ctx = _contexto(navegador, servidor_vacio, 1400, 900)
    pg = ctx.new_page()
    pg.goto(servidor_vacio + "/#tablero")
    pg.wait_for_function("document.querySelector('.vacio')?.innerText.includes('Todavía no hay datos')", timeout=15000)
    pg.click("#vacio-subir")
    pg.wait_for_selector("#dlg-importar[open] #imp-checklist .checklist-fila")
    pg.set_input_files("#imp-archivos", [rutas["stock"], rutas["existencias"]])
    pg.wait_for_selector(".imp-lote-fila")
    pg.click("#imp-subir-lote")
    pg.wait_for_function("document.querySelectorAll('#imp-checklist .checklist-fila.ok').length === 2", timeout=60000)
    assert "Faltan 2 Excel obligatorio(s): Empresas, Portafolio" in pg.inner_text("#imp-checklist .checklist-resumen")
    estado = pg.eval_on_selector_all(
        "#imp-checklist .checklist-fila",
        "els => els.map(e => [e.dataset.tabla, e.className.includes('ok'), e.querySelector('.checklist-estado').innerText])",
    )
    assert [(c, ok) for c, ok, _ in estado] == [
        ("stock", True),
        ("existencias", True),
        ("empresas", False),
        ("ficha", False),
        ("portafolio", False),
    ]
    assert (
        estado[0][2].endswith("filas") and estado[2][2] == "Falta"
    )  # las cargadas dicen cuántas filas; las que faltan, «Falta»


def test_la_bienvenida_con_la_base_vacia_pide_los_excel_y_lleva_a_subirlos(servidor_vacio, navegador):
    ctx = _contexto(navegador, servidor_vacio, 1400, 900)
    pg = ctx.new_page()
    pg.goto(servidor_vacio + "/#inicio")
    pg.wait_for_selector("#inicio-pide:not([hidden])")
    assert "todavía no tiene datos" in pg.inner_text("#inicio-pide") and "necesita sus Excel" in pg.inner_text(
        "#inicio-pide"
    )
    pg.click("#inicio-subir")
    pg.wait_for_selector("#dlg-importar[open] #imp-checklist .checklist-fila")
    assert "Faltan 4 Excel obligatorio(s)" in pg.inner_text("#imp-checklist")


def _cotizar(ctx, servidor, filas):
    """«Cargar datos → Cotizaciones» por la API, para dejar ofertas con cantidad disponible antes de abrir la pantalla."""
    r = ctx.request.post(
        servidor + "/api/cargas/cotizaciones",
        params={"nombre": "c.xlsx", "aplicar": "true"},
        data=excel_bytes(filas),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.ok, r.text()


def test_cantidad_disponible_avisa_en_la_fila_y_explica_el_reparto(servidor, navegador):
    """A1 necesita 80: BETA ($80) tiene 30 y GAMA ($94) tiene 20, así que se le compra 30 a BETA, 20 a GAMA y 30 a ALFA (sin tope). La fila lo avisa
    y la ventana de ofertas explica a quién se le compra cuánto y cuáles proveedores no alcanzan (no hay botón de filtro «Reparto»)."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    _cotizar(
        ctx,
        servidor,
        [
            {"COD_EMPRESA": "2", "COD_PRODUCTO": "A1", "VALOR": 80, "DISPONIBLE": 30},
            {"COD_EMPRESA": "3", "COD_PRODUCTO": "A1", "VALOR": 94, "DISPONIBLE": 20},
        ],
    )
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila[data-cod='A1']")
    assert "Repartido en 3 proveedores" in pg.locator(".fila[data-cod='A1'] .aviso-cant").inner_text()
    assert "7.280" in pg.locator(".fila[data-cod='A1'] .c-total").inner_text().replace(
        ",", "."
    )  # el total es el del reparto, no 80 × $80
    assert pg.locator("#chips .chip", has_text="Reparto").count() == 0  # no hay botón de filtro «Reparto»
    pg.locator(".fila[data-cod='A1'] button", has_text="Mejor oferta").click()
    pg.wait_for_selector("#dlg-ofertas[open] .reparto-panel")
    panel = pg.locator(".reparto-panel")
    assert "La compra se reparte entre proveedores" in panel.inner_text() and panel.locator("li").count() == 3
    assert "30 und" in panel.locator("li").nth(0).inner_text() and "BETA SAS" in panel.locator("li").nth(0).inner_text()
    assert "Solo tiene 30 und: faltan 50" in pg.locator("#dlg-ofertas .tarjeta.p1 .disponible").inner_text()
    assert "Total a pagar con el reparto" in pg.locator(".mejor-resumen").inner_text()
    assert errores == []


def test_agregar_oferta_a_mano_con_cantidad_disponible_y_avisa_lo_que_falta(servidor, navegador):
    """D4 necesita 5 y nadie lo ofrece. Se agrega una oferta manual de ALFA con 3 unidades: la fila avisa que faltan 2. Una cantidad que no es número se rechaza."""
    ctx = _contexto(navegador, servidor, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#tablero")
    pg.wait_for_selector(".fila[data-cod='D4']")
    pg.locator(".fila[data-cod='D4'] .btn-fila.agregar").click()
    pg.wait_for_selector("#dlg-agregar[open] .ficha-datos")
    pg.select_option("#ag-proveedor", "1")
    pg.fill("#ag-valor", "10")
    pg.fill("#ag-disponible", "mucha")
    pg.click("#ag-guardar")
    pg.wait_for_selector("#ag-error:not([hidden])")
    assert "cantidad disponible" in pg.inner_text("#ag-error")  # no se guardó nada
    pg.fill("#ag-disponible", "3")
    pg.click("#ag-guardar")
    pg.wait_for_selector("#dlg-agregar", state="hidden")
    pg.wait_for_function("document.querySelector(\".fila[data-cod='D4']\")?.innerText.includes('Faltan 2 und')")
    oferta = ctx.request.get(servidor + "/api/productos/D4/ofertas").json()["ofertas"][0]
    assert oferta["disponible"] == 3 and oferta["faltan"] == 2
    assert errores == []


def test_tableros_de_control_empresas_precios_y_consumo(servidor, navegador):
    """La pantalla nueva: con los datos de prueba, las tres vistas muestran lo calculado a mano (BETA la más barata; A1 el producto de
    mayor ahorro y consumo), el clic en una empresa filtra las demás vistas, y los interruptores cambian el orden."""
    ctx = _contexto(navegador, servidor, 1500, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/#control")
    pg.wait_for_selector("#ct-empresas .ct-fila")
    assert pg.locator("#menu-control").get_attribute(
        "aria-current"
    ) == "page" and "Tableros de control" in pg.inner_text("#ruta-actual")
    # los 4 números de arriba
    kpis = pg.inner_text("#ct-kpis")
    assert (
        "$7.092" in kpis and "$800" in kpis and "BETA SAS" in kpis and "ALFA PRODUCTO" in kpis and "80 unidades" in kpis
    )
    # 1. empresas: de la que cobra menos a la que cobra más
    filas = pg.locator("#ct-empresas .ct-fila")
    assert filas.count() == 5 and "BETA SAS" in filas.nth(0).inner_text() and "Más barata" in filas.nth(0).inner_text()
    assert (
        "0 %" in filas.nth(0).inner_text()
        and "+11,8%" in filas.nth(1).inner_text()
        and "GAMA LTDA" in filas.nth(1).inner_text()
    )
    assert "Gana en 2 de 3 productos" in pg.locator("#ct-empresas .ct-fila:has-text('ALFA SAS')").inner_text()
    # 2. precios: solo A1 tiene 2 o más ofertas
    assert pg.locator("#ct-precios .ct-fila").count() == 1
    assert (
        "A1" in pg.inner_text("#ct-precios")
        and "−19,8 %" in pg.inner_text("#ct-precios")
        and "BETA SAS" in pg.inner_text("#ct-precios")
    )
    # 3. consumo: por cantidad a comprar
    cons = pg.locator("#ct-consumo .ct-fila")
    assert (
        cons.count() == 4
        and "A1" in cons.nth(0).inner_text()
        and "80 und" in cons.nth(0).inner_text()
        and "Hay 20 y el máximo es 100" in cons.nth(0).inner_text()
    )
    # filtro cruzado: clic en ALFA → las vistas 2 y 3 y los números se limitan a sus productos
    pg.click("#ct-empresas .ct-fila:has-text('ALFA SAS')")
    pg.wait_for_function("document.querySelectorAll('#ct-consumo .ct-fila').length === 3")
    assert (
        "Empresa: ALFA SAS" in pg.inner_text("#ct-activo")
        and "D4" not in pg.inner_text("#ct-consumo")
        and "DELTA SIN OFERTA" not in pg.inner_text("#ct-consumo")
    )
    assert pg.locator("#ct-empresas .ct-fila").count() == 5  # el ranking de empresas no se achica
    pg.click("#ct-activo .ct-quitar")
    pg.wait_for_function("document.querySelectorAll('#ct-consumo .ct-fila').length === 4")
    # interruptor de consumo: por inversión, el producto sin oferta queda al final
    pg.click("#ct-consumo .ct-interruptor .chip:has-text('Inversión')")
    pg.wait_for_function(
        "document.querySelector('#ct-consumo .ct-fila:last-child') && document.querySelector('#ct-consumo li:last-child').innerText.includes('Sin oferta')"
    )
    assert "$6.800" in pg.locator("#ct-consumo .ct-fila").nth(0).inner_text()
    # cuántos renglones: con 5 se ven las 5 empresas y con un mínimo de 2 productos cotizados solo queda ALFA
    pg.select_option("#ct-min", "3")
    pg.wait_for_function("document.querySelectorAll('#ct-empresas .ct-fila').length === 1")
    assert "ALFA SAS" in pg.inner_text("#ct-empresas") and "Mostrando 1 de 1 empresa" in pg.inner_text("#ct-empresas")
    assert errores == []


def test_tableros_de_control_sin_datos_no_fallan(servidor_vacio, navegador):
    """Con la base vacía los tres tableros avisan que no hay nada que comparar, sin errores."""
    ctx = _contexto(navegador, servidor_vacio, 1400, 900)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor_vacio + "/#control")
    pg.wait_for_selector("#ct-empresas .ct-vacio")
    assert pg.locator("#ct-precios .ct-vacio").count() == 1 and pg.locator("#ct-consumo .ct-vacio").count() == 1
    assert "Todavía no hay ofertas" in pg.inner_text(
        "#ct-empresas"
    ) and "No hay productos por comprar" in pg.inner_text("#ct-consumo")
    assert errores == []


def test_el_ojo_deja_ver_y_ocultar_la_clave_en_el_ingreso_y_al_cambiarla(servidor, navegador):
    """En el ingreso (y en «Cambiar mi clave») cada campo de clave tiene un ojo: al pulsarlo se VE lo que se escribe, al pulsarlo otra vez se oculta,
    el cursor no se mueve, y al ingresar el formulario se limpia y la clave vuelve a quedar oculta."""
    ctx = navegador.new_context(viewport={"width": 1200, "height": 800}, bypass_csp=True)
    pg = ctx.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(servidor + "/")
    pg.wait_for_selector("#login-clave")
    ojo = pg.locator("#login-clave ~ .ver-clave")
    assert (
        ojo.count() == 1
        and pg.get_attribute("#login-clave", "type") == "password"
        and ojo.get_attribute("aria-pressed") == "false"
    )
    pg.fill("#login-clave", "MiClave123")
    ojo.click()  # se ve
    assert pg.get_attribute("#login-clave", "type") == "text" and pg.input_value("#login-clave") == "MiClave123"
    assert ojo.get_attribute("aria-pressed") == "true" and ojo.get_attribute("aria-label") == "Ocultar la clave"
    ojo.click()  # se oculta otra vez
    assert (
        pg.get_attribute("#login-clave", "type") == "password" and ojo.get_attribute("aria-label") == "Mostrar la clave"
    )
    assert pg.locator("#login-usuario ~ .ver-clave").count() == 0  # el usuario no lleva ojo: solo las claves
    # el ojo no manda el formulario ni pierde el foco del campo
    ojo.click()
    assert pg.url.rstrip("/") == servidor.rstrip("/") and pg.evaluate("document.activeElement.id") == "login-clave"
    # entrar: «Cambiar mi clave» trae un ojo en cada uno de sus tres campos
    pg.fill("#login-usuario", "admin")
    pg.fill("#login-clave", CLAVE_ADMIN)
    pg.click("#login-entrar")
    pg.wait_for_selector("#btn-clave", state="visible")
    pg.click("#btn-clave")
    pg.wait_for_selector("#dlg-clave[open]")
    assert pg.locator("#dlg-clave .ver-clave").count() == 3
    pg.fill("#cl-nueva", "OtraClave2026")
    pg.click("#cl-nueva ~ .ver-clave")
    assert pg.get_attribute("#cl-nueva", "type") == "text" and pg.input_value("#cl-nueva") == "OtraClave2026"
    pg.click("#cl-cancelar")  # cerrar: al volver a abrir, el formulario está limpio y las claves ocultas
    pg.click("#btn-clave")
    pg.wait_for_selector("#dlg-clave[open]")
    assert pg.get_attribute("#cl-nueva", "type") == "password" and pg.input_value("#cl-nueva") == ""
    assert errores == []
