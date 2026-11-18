"""
BASE DE DATOS (SQLite)
======================
SQLite es una base de datos que vive en UN solo archivo (data/compras.db): no hay que
instalar ni encender ningún servidor. El archivo se crea solo la primera vez.

Este archivo hace tres cosas:
    1. Define las tablas (ESQUEMA).
    2. Sabe abrir una conexión (conectar).
    3. Entrega una conexión a cada petición web (get_db).

Hay DOS capas de tablas:

  1. Las 5 TABLAS DE LOS EXCEL (x_stock, x_existencias, x_empresas, x_ficha, x_portafolio): copia fiel de cada Excel,
     con sus mismos encabezados. Son las que se ven y se editan en la pantalla «Administración» (services/tablas.py).
     Los Excel se importan a ellas SOLO cuando el usuario lo pide, por tabla (reemplazar o agregar).
  2. Las tablas de TRABAJO (productos, empresas, ofertas, avisos): las calcula importador.recalcular() a partir de las
     5 anteriores cada vez que algo cambia. Son las que lee el tablero de compras.

La columna `origen` de productos, empresas y ofertas dice de dónde salió cada fila:
    - 'excel'  → se calculó desde las 5 tablas de los Excel (se recalcula cada vez que cambian).
    - 'manual' → la escribió el usuario a mano en la pantalla («Agregar oferta» o «Cargar datos»).
    - 'subido' → la cargó el usuario subiendo un Excel desde el panel «Cargar datos».
    Las filas 'manual' y 'subido' son DATOS PROPIOS: el recálculo no las toca
    (y si un producto o proveedor existe en los dos lados, gana el del usuario).
    También son del usuario las tablas seleccion (proveedor elegido a mano) y cambios (historial de la administración).
Seguridad: usuarios (perfiles y claves cifradas) y sesiones (ingresos vigentes); ver services/seguridad.py.
"""

import sqlite3
from collections.abc import Iterator

from .config import ruta_db
from .services import tablas

# Instrucciones SQL que crean las tablas. "IF NOT EXISTS" significa "solo si aún no existe",
# así que ejecutarlas varias veces es seguro.
ESQUEMA = """
-- PROVEEDORES. 'origen' dice de dónde salió:
--   excel    → estaba en EMPRESA.xlsx
--   inferida → tenía ofertas pero no estaba en EMPRESA.xlsx (ej. el proveedor 80)
--   manual   → lo creó el usuario a mano (panel «Agregar oferta» o «Cargar datos»)
--   subido   → lo cargó el usuario desde un Excel en el panel «Cargar datos»
CREATE TABLE IF NOT EXISTS empresas (
    cod    TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    origen TEXT NOT NULL DEFAULT 'excel'          -- excel | inferida | manual | subido
);

-- PRODUCTOS: unión de 05-STOCK, FICHA_COTIZACION y PORTAFOLIO.
-- stock_max/med/min vienen de 05-STOCK; existencias de 06-EXISTENCIAS.
CREATE TABLE IF NOT EXISTS productos (
    cod         TEXT PRIMARY KEY,
    descripcion TEXT NOT NULL,
    stock_max   REAL,
    stock_med   REAL,
    stock_min   REAL,
    existencias REAL NOT NULL DEFAULT 0,
    en_stock    INTEGER NOT NULL DEFAULT 0,       -- 1 si tiene stock definido
    origen      TEXT NOT NULL DEFAULT 'excel'     -- excel | manual | subido
);

-- OFERTAS: cada fila = "el proveedor X vende el producto Y a $Z por unidad".
-- Un producto puede tener varias ofertas (una por proveedor, o más si hubo repetidas).
CREATE TABLE IF NOT EXISTS ofertas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cod_producto TEXT NOT NULL,
    cod_empresa  TEXT NOT NULL,
    valor        REAL NOT NULL,
    presentacion TEXT,
    disponible   REAL,                            -- cuántas unidades PUEDE entregar el proveedor (NULL = no lo dijo: se supone que le alcanza)
    origen       TEXT NOT NULL DEFAULT 'excel',   -- excel | manual | subido
    creado       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
-- Índice: hace muy rápido buscar "todas las ofertas de un producto".
CREATE INDEX IF NOT EXISTS idx_ofertas_producto ON ofertas(cod_producto);

-- SELECCION: cuando el usuario elige un proveedor distinto al mejor, se anota aquí.
-- Si un producto no está en esta tabla, se usa el proveedor más barato.
CREATE TABLE IF NOT EXISTS seleccion (             -- proveedor elegido a mano (si no, gana el mejor)
    cod_producto TEXT PRIMARY KEY,
    cod_empresa  TEXT NOT NULL
);

-- CANTIDADES: cuando el usuario EDITA la cantidad a comprar de un producto, se anota aquí y vale hasta que la restaure.
-- Si un producto no está en esta tabla, la cantidad es la calculada (StockMax - Existencias). No se borra al
-- recalcular ni al «Actualizar Excel»: es una decisión del usuario, igual que la tabla `seleccion`.
CREATE TABLE IF NOT EXISTS cantidades (
    cod_producto TEXT PRIMARY KEY,
    cantidad     INTEGER NOT NULL,                -- unidades a comprar, enteras y >= 0
    usuario      TEXT,                            -- quién la editó
    fecha        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- VISTOS: la primera vez que el sistema vio cada producto y cada empresa (para la etiqueta «Nuevo»; ver services/etiquetas.py).
-- primera_vez vacía = ya existía cuando se empezó a llevar este registro: «lo de siempre», no es nuevo.
CREATE TABLE IF NOT EXISTS vistos (
    tipo         TEXT NOT NULL,                   -- «producto» o «empresa»
    cod          TEXT NOT NULL,
    primera_vez  TEXT,
    PRIMARY KEY (tipo, cod)
);

-- LOTES_OFERTA y OFERTAS_LOTE: cada ficha que un PROVEEDOR sube desde su pantalla. Sus precios NO compiten en el tablero hasta que el
-- administrador la APRUEBA (entonces pasan a la tabla `ofertas` como ofertas «subidas»). Estados: pendiente · aprobada · rechazada · reemplazada
-- (una ficha nueva del mismo proveedor reemplaza a la que seguía pendiente). Ver services/pendientes.py.
CREATE TABLE IF NOT EXISTS lotes_oferta (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    cod_empresa    TEXT NOT NULL,                 -- el proveedor (siempre el del usuario que la subió, nunca el que diga el archivo)
    usuario        TEXT NOT NULL,                 -- quién la subió
    archivo        TEXT,
    fecha          TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    estado         TEXT NOT NULL DEFAULT 'pendiente',
    filas          INTEGER NOT NULL DEFAULT 0,    -- productos con precio que quedaron en la ficha
    omitidas       INTEGER NOT NULL DEFAULT 0,    -- filas sin precio (no cotizó ese producto)
    revisado_por   TEXT,
    fecha_revision TEXT,
    motivo         TEXT,                          -- por qué se rechazó (opcional)
    resultado      TEXT                           -- al aprobar: lo que se cargó (JSON)
);
CREATE INDEX IF NOT EXISTS idx_lotes_estado ON lotes_oferta (estado, cod_empresa);
CREATE TABLE IF NOT EXISTS ofertas_lote (
    lote_id      INTEGER NOT NULL,
    cod_producto TEXT NOT NULL,
    valor        REAL NOT NULL,
    presentacion TEXT,
    disponible   REAL,                            -- la «cantidad disponible» que escribió el proveedor en su ficha (NULL = la dejó vacía)
    -- La «foto de antes»: al APROBAR se guarda lo que había (la oferta «subida» de ese proveedor para ese producto, si ya existía) para poder
    -- RESTAURAR la ficha y dejar todo como estaba (services/pendientes.py → restaurar). NULL = no se aprobó (o se aprobó antes de existir «Restaurar»).
    antes_existia      INTEGER,
    antes_valor        REAL,
    antes_presentacion TEXT,
    antes_creado       TEXT,
    antes_disponible   REAL,
    PRIMARY KEY (lote_id, cod_producto)
);

-- AVISOS: problemas detectados en los Excel (se muestran en el botón ⚠ de la pantalla).
CREATE TABLE IF NOT EXISTS avisos (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    clave    TEXT,                                -- nombre estable del aviso (no cambia entre recálculos)
    nivel    TEXT NOT NULL,                       -- info | warn
    titulo   TEXT NOT NULL,
    detalle  TEXT,
    destinos TEXT                                 -- JSON: a dónde llevan los botones «Ir a corregir» (ver importador.py)
);

-- CAMBIOS: historial de la pantalla «Administración» (qué se agregó, editó, eliminó o importó, y cómo estaba antes).
CREATE TABLE IF NOT EXISTS cambios (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    tabla   TEXT NOT NULL,                        -- stock | existencias | empresas | ficha | portafolio
    accion  TEXT NOT NULL,                        -- agregar | editar | eliminar | eliminar_varias | importar
    fila_id INTEGER,                              -- número de la fila afectada (no aplica a «importar»)
    antes   TEXT,                                 -- JSON con los valores anteriores (o una copia comprimida si es «importar» / «eliminar_varias»)
    despues TEXT,                                 -- JSON con los valores nuevos
    resumen TEXT,                                 -- frase para mostrar en el historial
    deshecho INTEGER NOT NULL DEFAULT 0,          -- 1 si ya se deshizo
    usuario TEXT                                  -- quién hizo el cambio (usuario de la sesión)
);

-- USUARIOS: quién puede entrar y con qué perfil (services/seguridad.py). La clave NUNCA se guarda: solo su «huella» (scrypt).
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario       TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- el nombre con el que entra (minúsculas, sin espacios)
    nombre        TEXT NOT NULL,                          -- nombre para mostrar
    clave_hash    TEXT NOT NULL,                          -- scrypt$N$sal$huella
    rol           TEXT NOT NULL,                          -- admin | prime | consulta | externo
    cod_empresa   TEXT,                                   -- solo «externo»: a qué proveedor corresponde (opcional)
    correo        TEXT,                                   -- opcional: a donde se envían usuario y clave temporal
    celular       TEXT,                                   -- opcional: «+57…» (solo dígitos): para WhatsApp
    activo        INTEGER NOT NULL DEFAULT 1,
    cambiar_clave INTEGER NOT NULL DEFAULT 0,             -- 1 = debe cambiar su clave al entrar (clave temporal)
    intentos      INTEGER NOT NULL DEFAULT 0,             -- claves incorrectas seguidas
    bloqueado_hasta TEXT,                                 -- tras 5 fallos seguidos, espera unos minutos
    creado        TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    ultimo_ingreso TEXT
);

-- SESIONES: una fila por cada ingreso vigente. Se guarda la huella del «token» (el token real vive solo en la cookie).
CREATE TABLE IF NOT EXISTS sesiones (
    token_hash TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creada     TEXT NOT NULL,
    expira     TEXT NOT NULL
);

-- ADICIONALES: lista de productos (código y descripción) que el usuario sube para ver sus 3 proveedores más baratos
-- (pantalla «Adicionales», services/adicionales.py). Es una lista de consulta: no cambia el tablero ni las ofertas.
CREATE TABLE IF NOT EXISTS adicionales (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cod         TEXT NOT NULL,
    descripcion TEXT,
    usuario     TEXT,
    fecha       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    activo      INTEGER NOT NULL DEFAULT 1                -- 0 = inhabilitado (se ve en rojo; no se borra)
);

-- OFERTAS LIBRES: precios que un proveedor ofreció pero que el TABLERO NO TOMA por sus reglas (producto que no está en el catálogo al
-- «Cargar datos», o que hoy no se necesita en la ficha del proveedor externo). No compiten en el tablero ni en la OC: solo los usa
-- «Adicionales» para mostrar quién tiene un producto y a qué valor. Una por (producto, proveedor): la más reciente reemplaza a la anterior.
CREATE TABLE IF NOT EXISTS ofertas_libres (
    clave        TEXT NOT NULL,                       -- código del producto normalizado (para buscar)
    cod_producto TEXT NOT NULL,
    cod_empresa  TEXT NOT NULL,
    valor        REAL NOT NULL,
    presentacion TEXT,
    descripcion  TEXT,
    origen       TEXT NOT NULL,                       -- «Cargar datos» o «Ficha del proveedor»
    archivo      TEXT,
    usuario      TEXT,
    fecha        TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (clave, cod_empresa)
);

-- META: datos sueltos, por ejemplo la fecha de la última importación.
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT
);
"""


def conectar() -> sqlite3.Connection:
    """Abre una conexión a la base de datos (creando la carpeta y el archivo si faltan)."""
    ruta = ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI atiende cada petición en un hilo distinto,
    # y SQLite por defecto no lo permite.
    con = sqlite3.connect(ruta, check_same_thread=False)
    # row_factory=Row: las filas se leen por nombre (fila["valor"]) en vez de por posición.
    con.row_factory = sqlite3.Row
    # WAL: modo que permite leer mientras otro proceso escribe.
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """Actualiza una base de datos CREADA CON UNA VERSIÓN ANTERIOR de la aplicación.

    Las versiones anteriores no tenían la columna `origen` en la tabla productos ni `destinos` en avisos. Si faltan,
    se agregan (los productos existentes quedan como 'excel', que es lo que eran). Es seguro ejecutarla
    siempre: si la columna ya existe, no hace nada.
    """
    columnas = {f["name"] for f in con.execute("PRAGMA table_info(productos)")}
    if "origen" not in columnas:
        con.execute("ALTER TABLE productos ADD COLUMN origen TEXT NOT NULL DEFAULT 'excel'")
    # Los avisos ahora llevan «destinos» (a dónde lleva cada botón «Ir a corregir»). Las bases viejas no la tenían.
    columnas_avisos = {f["name"] for f in con.execute("PRAGMA table_info(avisos)")}
    if "destinos" not in columnas_avisos:
        con.execute("ALTER TABLE avisos ADD COLUMN destinos TEXT")
    if "clave" not in columnas_avisos:
        con.execute("ALTER TABLE avisos ADD COLUMN clave TEXT")
    # Los usuarios ahora guardan correo y celular (para enviarles su usuario y clave temporal).
    # Las 5 tablas de los Excel: si una versión nueva les agrega columnas (p. ej. TELEFONO y CORREO en EMPRESAS), las
    # bases ya creadas las reciben aquí, sin perder datos.
    for t in tablas.TABLAS.values():
        existentes = {f["name"] for f in con.execute(f"PRAGMA table_info({t.sql})")}
        for c in t.columnas:
            if c not in existentes:
                con.execute(f'ALTER TABLE {t.sql} ADD COLUMN "{c}" TEXT')
    columnas_lote = {
        f["name"] for f in con.execute("PRAGMA table_info(ofertas_lote)")
    }  # la «foto de antes» de las fichas aprobadas
    for col, tipo in (
        ("antes_existia", "INTEGER"),
        ("antes_valor", "REAL"),
        ("antes_presentacion", "TEXT"),
        ("antes_creado", "TEXT"),
        ("disponible", "REAL"),  # la cantidad disponible que escribió el proveedor en su ficha
        ("antes_disponible", "REAL"),
    ):
        if col not in columnas_lote:
            con.execute(f"ALTER TABLE ofertas_lote ADD COLUMN {col} {tipo}")
    # Las ofertas ahora pueden traer «cuántas unidades puede entregar el proveedor» (para avisar y repartir la compra).
    if "disponible" not in {f["name"] for f in con.execute("PRAGMA table_info(ofertas)")}:
        con.execute("ALTER TABLE ofertas ADD COLUMN disponible REAL")
    columnas_usuarios = {f["name"] for f in con.execute("PRAGMA table_info(usuarios)")}
    for col in ("correo", "celular"):
        if col not in columnas_usuarios:
            con.execute(f"ALTER TABLE usuarios ADD COLUMN {col} TEXT")
    # «Adicionales»: los productos ya no se borran, se inhabilitan.
    if "activo" not in {f["name"] for f in con.execute("PRAGMA table_info(adicionales)")}:
        con.execute("ALTER TABLE adicionales ADD COLUMN activo INTEGER NOT NULL DEFAULT 1")
    # El historial ahora anota quién hizo cada cambio.
    if "usuario" not in {f["name"] for f in con.execute("PRAGMA table_info(cambios)")}:
        con.execute("ALTER TABLE cambios ADD COLUMN usuario TEXT")


def iniciar_db() -> None:
    """Crea las tablas si no existen y aplica las migraciones. Se llama una vez al arrancar la aplicación (main.py)."""
    con = conectar()
    try:
        con.executescript(ESQUEMA)
        con.executescript(tablas.esquema_sql())  # las 5 tablas de los Excel (encabezados exactos)
        _migrar(con)
        con.commit()
    finally:
        con.close()


def get_db() -> Iterator[sqlite3.Connection]:
    """Dependencia de FastAPI: una conexión por petición.

    Las rutas la piden con `db = Depends(get_db)`. FastAPI la abre antes de ejecutar
    la ruta y, gracias al `finally`, la cierra siempre al terminar (aunque haya un error).
    """
    con = conectar()
    try:
        yield con
    finally:
        con.close()
