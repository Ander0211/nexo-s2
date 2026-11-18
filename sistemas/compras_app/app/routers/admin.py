"""
RUTAS DE LA ADMINISTRACIÓN DE TABLAS
====================================
Las 5 tablas de los Excel (stock, existencias, empresas, ficha, portafolio) para verlas y editarlas.

    GET    /api/admin/tablas                                   las 5 tablas: encabezados y cuántas filas tiene cada una
    GET    /api/admin/tablas/{tabla}/filas                     una página de filas (búsqueda, orden, filas de un aviso)
    POST   /api/admin/tablas/{tabla}/filas                     agregar una fila
    PUT    /api/admin/tablas/{tabla}/filas/{id}                guardar los cambios de una fila
    DELETE /api/admin/tablas/{tabla}/filas/{id}                eliminar una fila
    POST   /api/admin/tablas/{tabla}/filas/eliminar            eliminar varias filas juntas
    GET    /api/admin/tablas/{tabla}/filas/{id}/impacto        qué pasaría en el tablero si se elimina (para avisar antes)
    GET    /api/admin/tablas/{tabla}/excel                     descargar la tabla como Excel (mismos encabezados)
    POST   /api/admin/importar                                 importar Excel de la carpeta data/excel (reemplazar o agregar)
    POST   /api/admin/tablas/{tabla}/importar                  importar un Excel SUBIDO a esa tabla
    GET    /api/admin/historial                                cambios recientes
    POST   /api/admin/historial/{id}/deshacer                  deshacer un cambio

El trabajo real está en services/admin.py y services/tablas.py; los errores de negocio (TablaError,
ImportacionError) los convierte main.py en respuestas {"detail": mensaje}.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from ..database import get_db
from ..schemas import EliminarIn, FilaIn, ImportarIn
from ..services import admin, historial, tablas

router = APIRouter(prefix="/api/admin", tags=["administración"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def quien(request: Request) -> str | None:
    """El usuario de la sesión (lo deja listo la revisión de permisos de autorizacion.py): se anota en el historial."""
    u = getattr(request.state, "usuario", None)
    return u["usuario"] if u else None


def _resumen(t: tablas.Tabla, total: int) -> dict:
    return {
        "clave": t.clave,
        "titulo": t.titulo,
        "archivo": t.archivo,
        "filas": total,
        "necesaria": t.necesaria,  # ¿el sistema la necesita para funcionar?
        "para_que": t.para_que,  # para qué sirve, en una frase
        "columnas": [
            {"nombre": c, "numerica": c in t.numericas, "obligatoria": c in t.obligatorias} for c in t.columnas
        ],
        # Columnas que solo se ven (no se editan ni van en el Excel): p. ej. el nombre de la empresa en el portafolio.
        "extras": [{"nombre": n, "titulo": titulo, "despues": despues} for n, titulo, despues in t.extras],
    }


@router.get("/tablas")
def listar_tablas(db: sqlite3.Connection = Depends(get_db)):
    """Las 5 tablas con sus encabezados EXACTOS y el número de filas de cada una."""
    return [_resumen(t, tablas.total(db, t)) for t in tablas.TABLAS.values()]


@router.get("/tablas/{clave}/filas")
def listar_filas(
    clave: str,
    q: str = "",
    orden: str | None = None,
    sentido: str = "asc",
    pagina: int = 1,
    tam: int = 50,
    aviso: str | None = None,
    destino: int = 0,
    solo_ids: bool = False,
    db: sqlite3.Connection = Depends(get_db),
):
    """Una página de filas. Con `aviso` (su clave) y `destino`, solo las filas a las que lleva ese botón de un aviso.
    Con `solo_ids=true` no devuelve las filas sino los números de TODAS las que cumplen el filtro (para seleccionarlas)."""
    t = tablas.obtener(clave)
    ids = None
    if aviso is not None:
        tabla_aviso, ids = admin.filas_de_aviso(db, aviso, destino)
        if tabla_aviso != clave:
            raise tablas.TablaError("Ese aviso corresponde a otra tabla.", 409)
    return tablas.listar(db, t, q=q, orden=orden, sentido=sentido, pagina=pagina, tam=tam, ids=ids, solo_ids=solo_ids)


@router.post("/tablas/{clave}/filas", status_code=201)
def agregar_fila(clave: str, body: FilaIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Agrega una fila (se valida y se recalcula el tablero)."""
    return admin.crear(db, clave, body.valores, quien(request))


@router.put("/tablas/{clave}/filas/{fila_id}")
def guardar_fila(clave: str, fila_id: int, body: FilaIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Guarda los cambios de una fila (se valida y se recalcula el tablero)."""
    return admin.editar(db, clave, fila_id, body.valores, quien(request))


@router.post("/tablas/{clave}/filas/eliminar")
def eliminar_varias(clave: str, body: EliminarIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Elimina varias filas juntas (un solo cambio en el historial)."""
    return admin.eliminar(db, clave, body.ids, quien(request))


@router.get("/tablas/{clave}/filas/{fila_id}/impacto")
def impacto(clave: str, fila_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Qué pasaría si se elimina esa fila. Sirve para avisarle al usuario ANTES de confirmar (siempre se permite)."""
    return tablas.impacto(db, tablas.obtener(clave), fila_id)


@router.delete("/tablas/{clave}/filas/{fila_id}")
def eliminar_fila(clave: str, fila_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Elimina una fila."""
    return admin.eliminar(db, clave, [fila_id], quien(request))


@router.get("/tablas/{clave}/excel")
def descargar_excel(clave: str, db: sqlite3.Connection = Depends(get_db)):
    """La tabla como Excel, con los mismos encabezados y el mismo nombre de archivo que el original."""
    t = tablas.obtener(clave)
    return Response(
        tablas.exportar_xlsx(db, t),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{t.archivo}"'},
    )


@router.post("/importar")
def importar_carpeta(body: ImportarIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Importa los Excel de la carpeta data/excel a las tablas elegidas, reemplazando o agregando."""
    return admin.importar_carpeta(db, body.tablas, body.modo, quien(request))


@router.post("/tablas/{clave}/importar")
async def importar_archivo(
    clave: str,
    request: Request,
    nombre: str = "",
    modo: str = "agregar",
    db: sqlite3.Connection = Depends(get_db),
):
    """Importa un Excel/CSV SUBIDO (el archivo viaja tal cual como cuerpo de la petición, igual que en «Cargar datos»)."""
    if modo not in ("reemplazar", "agregar"):
        raise HTTPException(422, "El modo debe ser «reemplazar» o «agregar».")
    tamano = request.headers.get("content-length", "")
    if tamano.isdigit() and int(tamano) > tablas.MAX_BYTES + 4096:
        raise HTTPException(413, f"El archivo es demasiado grande: el máximo es {tablas.MAX_BYTES // 1048576} MB.")
    contenido = await request.body()
    return await run_in_threadpool(admin.importar_archivo, db, clave, contenido, nombre, modo, quien(request))


@router.get("/historial")
def ver_historial(tabla: str | None = None, limite: int = 100, db: sqlite3.Connection = Depends(get_db)):
    """Los cambios más recientes primero (con `tabla`, solo los de esa tabla)."""
    if tabla:
        tablas.obtener(tabla)
    return historial.listar(db, tabla, limite)


@router.post("/historial/{cambio_id}/deshacer")
def deshacer(cambio_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Deshace un cambio del historial y recalcula el tablero."""
    return admin.deshacer(db, cambio_id)
