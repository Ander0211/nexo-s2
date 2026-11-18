"""
CONFIGURACIÓN CENTRAL
=====================
Aquí viven las rutas y los valores que se pueden cambiar sin tocar la lógica.

Quién lo usa:
    - database.py  → ruta_db()        para saber dónde está la base de datos.
    - importador.py → carpeta_excel()  para saber dónde están los Excel.
    - main.py      → FRONTEND_DIR      para servir las páginas web.

Las rutas se pueden cambiar con variables de entorno (útil para pruebas):
    COMPRAS_EXCEL_DIR  carpeta con los Excel de origen
    COMPRAS_DB         archivo de la base de datos SQLite
"""

import os
from pathlib import Path

# BASE_DIR = la carpeta principal del proyecto (la que contiene app/, frontend/, data/...).
# __file__ es este archivo (app/config.py); .parent.parent sube dos niveles hasta la raíz.
BASE_DIR = Path(__file__).resolve().parent.parent

# Carpeta con las páginas web (HTML, CSS y JavaScript).
FRONTEND_DIR = BASE_DIR / "frontend"

# Nombre que debe tener cada Excel dentro de data/excel/.
# Si algún día cambia el nombre de un archivo, se cambia solo aquí.
ARCHIVOS_EXCEL = {
    "stock": "05-STOCK.xlsx",  # StockMax / StockMed / StockMin por producto
    "existencias": "06-EXISTENCIAS.xlsx",  # cantidad actual por producto
    "empresas": "EMPRESA.xlsx",  # proveedores
    "ficha": "FICHA_COTIZACION.xlsx",  # catálogo de productos a cotizar
    "portafolio": "PORTAFOLIO.xlsx",  # ofertas: proveedor + producto + valor
}

# En el podio se ven 3 ofertas (1.ª, 2.ª y 3.ª); cada clic en «Ver siguientes» muestra 3 más.
OFERTAS_POR_PAGINA = 3
DIAS_NUEVO = 7  # cuántos días lleva la etiqueta «Nuevo» un producto o una empresa que el sistema ve por primera vez

# Los proveedores creados a mano reciben un código desde 1000, para que nunca
# choquen con los códigos del Excel (que van del 1 al ~80).
PRIMER_CODIGO_EMPRESA_MANUAL = 1000


def carpeta_excel() -> Path:
    """Carpeta donde están los 5 Excel. Por defecto: data/excel/ (o la de COMPRAS_EXCEL_DIR)."""
    return Path(os.environ.get("COMPRAS_EXCEL_DIR", BASE_DIR / "data" / "excel"))


def ruta_db() -> Path:
    """Archivo de la base de datos SQLite. Por defecto: data/compras.db (o el de COMPRAS_DB)."""
    return Path(os.environ.get("COMPRAS_DB", BASE_DIR / "data" / "compras.db"))
