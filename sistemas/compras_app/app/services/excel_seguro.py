"""
REVISIÓN DE SEGURIDAD DE LOS .xlsx SUBIDOS
==========================================
Un .xlsx es un zip. Un archivo malicioso (o dañado) puede PESAR POCO y, al abrirse, ocupar cientos de megas: una «bomba de compresión»
(una hoja con millones de ceros comprime a casi nada). Sin esta revisión, subirlo agota la memoria y tumba el servidor.

Aquí se mide, SIN descomprimir nada, cuánto ocuparía cada parte del archivo (el zip declara su tamaño real, y la librería de Python no lee
más de lo declarado), y se rechaza si pasa del límite. Un Excel normal de 25 MB ocupa unos 170 MB abierto: el límite deja holgura.
Si el archivo ni siquiera es un zip, aquí no se dice nada: el lector de Excel ya da su mensaje de «archivo dañado».
"""

import io
import zipfile

MAX_DESCOMPRIMIDO = 250 * 1024 * 1024  # lo que puede ocupar el archivo ya abierto
MAX_PARTES = 5000  # cantidad de archivos dentro del zip (un Excel normal tiene unas decenas)


def revisar_xlsx(contenido: bytes) -> str | None:
    """Devuelve un mensaje (para mostrar al usuario) si el .xlsx es sospechoso; None si está bien o si no es un zip."""
    try:
        partes = zipfile.ZipFile(io.BytesIO(contenido)).infolist()
    except (zipfile.BadZipFile, OSError):
        return None
    total = sum(p.file_size for p in partes)
    if total > MAX_DESCOMPRIMIDO or len(partes) > MAX_PARTES:
        return (
            f"El archivo ocupa {total / 1e6:,.0f} MB al abrirse (el máximo es {MAX_DESCOMPRIMIDO // 1048576} MB): "
            "no parece un Excel normal. Revisa que sea el archivo correcto."
        ).replace(",", ".")
    return None
