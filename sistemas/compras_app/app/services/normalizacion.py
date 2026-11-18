"""
LIMPIEZA DE DATOS
=================
Los Excel llegan «sucios»: espacios de más, códigos como 5929.0, números con puntos
y comas, celdas vacías... Estas funciones los dejan en un formato único y confiable
ANTES de guardarlos. Las usa importador.py (al leer los Excel) y las rutas de la API
(al recibir lo que escribe el usuario).
"""

import math
import re
import unicodedata


def texto(v) -> str | None:
    """Limpia un texto: quita espacios de más y devuelve None si está vacío.

    "  ALCOHOL   ANTISEPTICO " → "ALCOHOL ANTISEPTICO"
    ""  /  None  /  NaN (celda vacía de Excel) → None
    """
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = " ".join(str(v).split())  # split() sin argumentos junta cualquier cantidad de espacios en uno
    return s or None


def codigo_producto(v) -> str | None:
    """'5929', 5929.0 y ' 5929 ' -> '5929'. Los ceros a la izquierda ('0041') se conservan."""
    s = texto(v)
    if s is None:
        return None
    # Excel a veces guarda 5929 como "5929.0"; aquí se le quita el ".0" final.
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


def codigo_empresa(v) -> str | None:
    """'05' y '5' son el mismo proveedor -> '5'."""
    s = codigo_producto(v)
    if s is not None and s.isdigit():
        return str(int(s))  # int("05") = 5 → quita los ceros a la izquierda
    return s


_MENOS = str.maketrans(
    {"−": "-", "–": "-", "—": "-", "\u00a0": " "}
)  # el «menos» de Excel/Word (Unicode) y el espacio duro


def numero(v) -> float | None:
    """Interpreta un número escrito de cualquier forma. Devuelve None si no es un número.

    Una celda de Excel que ya es NÚMERO (int o float) se toma tal cual: su punto, si lo tiene, es decimal.
    Un TEXTO se interpreta a la colombiana:
        '1234'  '1234.5'  '12,5'  '1.234,5'  '$ 1,234.50'  → como se escriben
        '59.000'  '1.234'  '1.234.567'                      → el punto separa MILES (59000, 1234, 1234567)
        '−5'  '-5'  '(100)'                                 → negativos (el menos de Excel y los paréntesis contables)
        '1.5e3'  '2E-2'                                     → notación científica (1500, 0.02)
    Un punto con tres cifras exactas detrás ('59.000') es miles; con otra cantidad ('12.5', '100.25', '3.14159') es decimal.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):  # ya viene como número: no hay nada que adivinar
        return float(v) if math.isfinite(v) else None
    s = texto(v)
    if s is None:
        return None
    s = s.translate(_MENOS)
    negativo = bool(re.fullmatch(r"\(.*\)", s))  # (100) = -100: el negativo contable
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?[eE][+-]?\d+", s.strip("() ")):  # 1.5e3
        try:
            x = float(s.strip("() ").replace(",", "."))
        except ValueError:
            return None
        return (-abs(x) if negativo else x) if math.isfinite(x) else None
    s = re.sub(r"[^\d,.\-]", "", s)  # deja solo dígitos, coma, punto y signo menos ("$ 1.500" → "1.500")
    if not s:
        return None
    if "," in s and "." in s:
        # Si están los dos, el ÚLTIMO es el decimal y el otro separa miles:
        #   "1.234,50" → 1234.50      "1,234.50" → 1234.50
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        # Solo coma: si tiene 3 dígitos después es separador de miles ("1,234"), si no es decimal ("12,5").
        s = s.replace(",", ".") if len(s.split(",")[-1]) != 3 else s.replace(",", "")
    elif "." in s and re.fullmatch(r"-?[1-9]\d{0,2}(?:\.\d{3})+", s):
        s = s.replace(".", "")  # solo puntos: «59.000», «1.234.567» → los puntos separan miles
    try:
        x = float(s)
    except ValueError:
        return None
    if not math.isfinite(x):
        return None  # descarta "infinito" y "NaN"
    return -abs(x) if negativo else x


def sin_acentos(s: str) -> str:
    """Quita las tildes y la ñ: "ÑANDÚ" → "NANDU". Sirve para que buscar «nandu» encuentre «ÑANDÚ»."""
    # NFKD separa cada letra de su tilde; encode('ascii', 'ignore') descarta lo que no es ASCII (las tildes).
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def clave_busqueda(*partes: str | None) -> str:
    """Texto de búsqueda de un producto: sus partes unidas, sin tildes y en minúscula.
    Ejemplo: ("0041", "AGUJA ÑANDÚ") → "0041 aguja nandu"."""
    return sin_acentos(" ".join(p for p in partes if p)).lower()


def nombre_columna(c) -> str:
    """Normaliza el encabezado de una columna de Excel: sin tildes, en mayúsculas y con «_» en vez de espacios.

    "StockMax" → "STOCKMAX"      "Código Producto" → "CODIGO_PRODUCTO"      " valor " → "VALOR"
    Así se reconocen los encabezados aunque cada persona los escriba un poco distinto.
    """
    return "_".join(sin_acentos(str(c)).strip().upper().split())


def clave_nombre(nombre) -> str:
    """El nombre de una empresa reducido a lo esencial, para decidir si dos son «la misma»: sin tildes, sin mayúsculas y sin espacios ni signos.
    «Ñandú S.A.S.», «NANDU SAS» y «ñandu, s a s» dan la misma clave. Es la regla de TODO el sistema para no repetir empresas
    (servicio de proveedores, «Agregar oferta», Administración, importar Excel y «Cargar datos»). Una clave vacía = nombre sin letras ni números."""
    return re.sub(r"[^a-z0-9]", "", sin_acentos(texto(nombre) or "").casefold())


def clave_codigo(codigo) -> str:
    """Un código de producto sin distinguir mayúsculas («a1» = «A1»), para no repetir productos."""
    return (texto(codigo) or "").casefold()


def celda_a_texto(v):
    """Una celda de Excel leída con sus tipos reales → texto, para el resto de la limpieza (que trabaja con texto).

    Los NÚMEROS pierden su «.0» ('5929.0' → '5929') y, si su punto sería ambiguo (1.125: ¿tres decimales o mil ciento veinticinco?),
    se les agrega un cero ('1.1250') para que nunca se confundan con un «1.125» escrito a la colombiana. Las celdas vacías siguen vacías."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        r = repr(v)
        return r + "0" if re.fullmatch(r"-?[1-9]\d{0,2}\.\d{3}", r) else r
    return str(v)


def leer_excel(fuente):
    """Lee un .xlsx/.xlsm como TEXTO (así «0041» no pasa a 41) pero respetando cuáles celdas eran números (ver celda_a_texto)."""
    import pandas as pd

    df = pd.read_excel(fuente, dtype=object, engine="openpyxl")
    return df.apply(lambda col: col.map(celda_a_texto))
