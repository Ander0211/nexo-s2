"""
PUNTO DE ENTRADA DE LA APLICACIÓN
=================================
Aquí se «arma» la aplicación FastAPI: se conectan las rutas de la API (routers/),
se publican las páginas web (frontend/) y se cargan los Excel la primera vez.

Arranque:   python run.py        (o)   uvicorn app.main:app --reload
Interfaz:   http://127.0.0.1:8000   (si ese puerto no está libre, run.py elige otro y lo muestra al arrancar)
Docs API:   http://127.0.0.1:8000/docs   (FastAPI la genera sola; sirve para probar cada ruta)

Mapa del proyecto (quién hace qué):
    main.py            arma todo (este archivo)
    routers/           las «puertas» de la API: reciben la petición y responden
                       (cargas.py = subir Excel · productos/empresas/ofertas = formularios manuales ·
                        admin.py = administración de las 5 tablas de los Excel · sesion.py / usuarios.py = entrar,
                        salir y gestionar usuarios · proveedor.py = lo único que ve un proveedor externo)
    autorizacion.py    revisa los permisos de CADA petición a /api (ver services/seguridad.py)
    services/          la lógica de negocio: calculan, importan, exportan
    database.py        tablas y conexión a SQLite
    schemas.py         validación de lo que envía la pantalla
    frontend/          lo que ve el usuario en el navegador
"""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .autorizacion import autorizar
from .config import FRONTEND_DIR
from .database import conectar, iniciar_db
from .routers import (
    adicionales,
    admin,
    cargas,
    control,
    empresas,
    ofertas,
    pendientes,
    productos,
    proveedor,
    sesion,
    sistema,
    usuarios,
)
from .services import catalogo, etiquetas, importador, notificaciones, seguridad, tablas
from .services import pendientes as ofertas_pendientes


def asegurar_superusuario(con) -> None:
    """Lee COMPRAS_SUPERUSUARIO y COMPRAS_SUPERUSUARIO_CLAVE (de las variables o del .env) y deja listo al superusuario.
    Si están mal, avisa en la terminal y sigue arrancando (nunca imprime la clave)."""
    usuario = notificaciones.valor_de_configuracion("COMPRAS_SUPERUSUARIO") or "superadmin"
    clave = notificaciones.valor_de_configuracion("COMPRAS_SUPERUSUARIO_CLAVE")
    try:
        r = seguridad.asegurar_superusuario(con, usuario, clave)
    except seguridad.SeguridadError as e:
        print(f"[compras] ATENCIÓN: no se pudo preparar el superusuario: {e}")
        return
    if r in ("creado", "actualizado"):
        print(f"[compras] Superusuario «{usuario.strip().lower()}» {r} (con la clave definida en .env).")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """Código que corre UNA vez al encender la aplicación (antes del `yield`).

    1. Crea las tablas si no existen.
    2. Si es la PRIMERA vez (las 5 tablas de los Excel están vacías y nunca se importó nada), importa los Excel de
       data/excel/ automáticamente. También sirve para las bases de versiones anteriores, que no tenían esas tablas.
       Después de esa primera carga, los Excel NUNCA se vuelven a leer por su cuenta: solo cuando el usuario lo pide
       (así lo que se edita en «Administración» no se pierde, ni siquiera vaciando una tabla a propósito).
       Si faltan archivos NO se cae: solo avisa en la terminal y la pantalla mostrará
       «Todavía no hay datos» con instrucciones.
    """
    iniciar_db()
    con = conectar()
    try:  # primera vez: crear el administrador inicial
        clave_inicial = seguridad.asegurar_administrador(con)
        if clave_inicial:
            if os.environ.get("COMPRAS_ADMIN_CLAVE"):
                print("[compras] Usuario inicial «admin» creado con la clave de COMPRAS_ADMIN_CLAVE.")
            else:
                print("[compras] " + "=" * 62)
                print("[compras]  USUARIO INICIAL CREADO")
                print(f"[compras]  Usuario: admin        Clave temporal: {clave_inicial}")
                print("[compras]  Al entrar te pedirá cambiarla. Anótala ahora: no se vuelve a mostrar.")
                print("[compras]  Si la pierdes:  python -m app.usuarios_cli restablecer admin")
                print("[compras] " + "=" * 62)
    finally:
        con.close()
    con = conectar()
    try:  # superusuario definido en .env (si lo hay): se crea o se deja en regla en cada arranque
        asegurar_superusuario(con)
    finally:
        con.close()
    con = conectar()
    try:  # primera vez: cargar los Excel automáticamente
        ya_importado = con.execute("SELECT 1 FROM meta WHERE clave = 'crudas_iniciadas'").fetchone()
        if not ya_importado and sum(tablas.total(con, t) for t in tablas.TABLAS.values()) == 0:
            try:
                r = importador.importar(con)
                print(f"[compras] Importación inicial: {r['productos']} productos, {r['ofertas']} ofertas.")
            except importador.ImportacionError as e:
                from .config import ARCHIVOS_EXCEL, carpeta_excel

                if not any((carpeta_excel() / f).exists() for f in ARCHIVOS_EXCEL.values()):
                    from .services.tablas import TABLAS

                    obligatorios = ", ".join(t.archivo for t in TABLAS.values() if t.necesaria)
                    opcionales = ", ".join(t.archivo for t in TABLAS.values() if not t.necesaria)
                    print(
                        f"[compras] Todavía no hay datos. Entra a la aplicación: te pedirá estos Excel. Obligatorios: {obligatorios}. Opcional: {opcionales}."
                    )
                else:
                    print(f"[compras] No se pudo importar: {e}")
    finally:
        con.close()
    try:  # Pillow: sin ella la ficha de cotización sale sin sus logos y sin ningún error; mejor avisarlo desde el arranque
        import PIL  # noqa: F401
    except ImportError:
        print(
            "[compras] ATENCIÓN: falta la librería Pillow: la ficha de cotización saldría SIN LOGOS. Instálala con: pip install pillow"
        )
    con = conectar()
    try:  # lo que ya hay al arrancar es «lo de siempre»: solo lo que llegue después se marcará como «Nuevo»
        etiquetas.sincronizar(con)
    finally:
        con.close()
    yield


# `dependencies=[Depends(autorizar)]`: la revisión de permisos se aplica a TODAS las rutas de /api (autorizacion.py).
# La documentación automática se sirve desde /api/docs (mismo control: solo el administrador), no desde /docs.
app = FastAPI(
    title="Compras · SUMIPABON",
    version="1.1.0",
    lifespan=ciclo_de_vida,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    dependencies=[Depends(autorizar)],
)

# Conecta cada grupo de rutas de la API (todas empiezan con /api).
for r in (
    sesion.router,
    usuarios.router,
    proveedor.router,
    pendientes.router,
    productos.router,
    control.router,
    adicionales.router,
    ofertas.router,
    empresas.router,
    cargas.router,
    admin.router,
    sistema.router,
):
    app.include_router(r)


@app.get("/api/openapi.json", include_in_schema=False)
def esquema_de_la_api():
    """El esquema OpenAPI (solo administrador, como toda ruta de /api que no está en la tabla de permisos)."""
    return JSONResponse(app.openapi())


@app.get("/api/docs", include_in_schema=False)
def documentacion_de_la_api():
    """La documentación interactiva de la API (solo administrador)."""
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="API · SUMIPABON")


@app.exception_handler(UnicodeDecodeError)
async def cuerpo_ilegible(request: Request, exc: UnicodeDecodeError):
    """Una petición con bytes que no son texto (y sin tipo JSON) hacía fallar al servidor con un error 500: ahora se responde un 400 claro."""
    return JSONResponse({"detail": "El contenido enviado no se puede leer: no es un texto válido."}, status_code=400)


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    """Agrega a cada respuesta cabeceras que endurecen el navegador: sin adivinar tipos de archivo, sin incrustar la página
    en otra (clickjacking), sin enviar la dirección a otros sitios y, en la API, sin guardar copias (son datos privados).
    La política CSP solo permite scripts y estilos propios (la documentación /api/docs carga los suyos de internet: sin CSP)."""
    respuesta = await call_next(request)
    h = respuesta.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api"):
        h["Cache-Control"] = "no-store"
    if request.url.path != "/api/docs":
        h["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
    return respuesta


@app.exception_handler(catalogo.CatalogoError)
async def error_de_catalogo(request, exc: catalogo.CatalogoError):
    """Convierte los errores de negocio de services/catalogo.py (producto que ya existe, proveedor con ofertas...)
    en una respuesta de error normal: {"detail": "mensaje claro"} con el código HTTP que corresponde (404, 409, 422)."""
    return JSONResponse({"detail": exc.mensaje}, status_code=exc.estado)


@app.exception_handler(ofertas_pendientes.PendienteError)
async def error_de_pendientes(request, exc: ofertas_pendientes.PendienteError):
    """Los errores de las fichas que suben los proveedores (ficha de otro proveedor, sin precios...) con su código HTTP."""
    return JSONResponse({"detail": exc.mensaje}, status_code=exc.estado)


@app.exception_handler(seguridad.SeguridadError)
async def error_de_seguridad(request, exc: seguridad.SeguridadError):
    """Errores de sesión y usuarios (clave incorrecta, usuario duplicado...): {"detail": mensaje}."""
    return JSONResponse({"detail": exc.mensaje}, status_code=exc.estado)


@app.exception_handler(tablas.TablaError)
async def error_de_tabla(request, exc: tablas.TablaError):
    """Errores de la administración de tablas (dato inválido, fila que ya no existe...): {"detail": mensaje}."""
    return JSONResponse({"detail": exc.mensaje}, status_code=exc.estado)


@app.exception_handler(tablas.ImportacionError)
async def error_de_importacion(request, exc: tablas.ImportacionError):
    """Falta un archivo o una columna al importar un Excel: 422 con un mensaje claro para el usuario."""
    return JSONResponse({"detail": str(exc)}, status_code=422)


class EstaticosSinCache(StaticFiles):
    """Los archivos de frontend/ (CSS y JS), pero con la orden «no guardes copias viejas».

    Con `Cache-Control: no-cache` el navegador pregunta cada vez si el archivo cambió (y si no cambió, usa su copia
    sin volver a descargarlo). Así, al reemplazar la aplicación por una versión nueva, el navegador NUNCA sigue
    mostrando el JavaScript de la versión anterior (que era una causa de que un botón nuevo «no funcionara»).
    """

    async def get_response(self, path, scope):
        """Entrega el archivo pedido agregándole el encabezado que evita las copias viejas."""
        respuesta = await super().get_response(path, scope)
        respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta


# Publica la carpeta frontend/ en la dirección /static (ahí están los CSS y JS de la página).
app.mount("/static", EstaticosSinCache(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def inicio():
    """LA página de la aplicación (frontend/index.html). Contiene la pantalla principal y los paneles emergentes
    «Agregar oferta» y «Cargar datos»: no hay más páginas HTML."""
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})
