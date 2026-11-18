"""
TELÉFONO Y CORREO DE CONTACTO DE UNA EMPRESA
============================================
Validan y dejan en un formato único lo que se escribe en las columnas TELEFONO y CORREO de la tabla EMPRESAS
(pantalla «Administración»). Lanzan ValueError con un mensaje que dice qué corregir; quien las llama lo convierte en
el error que corresponde (ver tablas.limpiar).

(Para las personas que usan el sistema, el celular se valida aparte en seguridad.normalizar_celular: allí tiene que
ser un celular; una empresa puede tener también un teléfono fijo.)
"""

import re


def normalizar_correo(valor: str | None) -> str | None:
    """Correo en minúsculas, o None si se dejó vacío. ValueError si no parece un correo."""
    correo = (valor or "").strip().lower()
    if not correo:
        return None
    if len(correo) > 120 or not re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]{2,}", correo):
        raise ValueError("El correo no es válido. Escríbelo así: nombre@dominio.com")
    return correo


def normalizar_telefono(valor: str | None) -> str | None:
    """Teléfono fijo o celular, o None si se dejó vacío.

    Acepta espacios, guiones y paréntesis («300 123 4567», «(602) 123-4567») y un «+» al inicio para el indicativo.
    Debe tener de 7 a 15 dígitos. Un celular colombiano de 10 dígitos que empieza por 3 se guarda como «+57…»; lo demás
    se guarda solo con dígitos (y con «+» si se escribió).
    """
    bruto = (valor or "").strip()
    if not bruto:
        return None
    limpio = re.sub(r"[\s().-]", "", bruto)
    if not re.fullmatch(r"\+?\d+", limpio):  # solo dígitos, con un único «+» y únicamente al inicio
        raise ValueError("El teléfono solo puede llevar números (y un + al inicio para el indicativo).")
    con_mas = limpio.startswith("+")
    digitos = limpio.lstrip("+")
    if len(digitos) == 10 and digitos.startswith("3"):  # celular colombiano sin indicativo
        digitos, con_mas = "57" + digitos, True
    if not 7 <= len(digitos) <= 15:
        raise ValueError(
            "El teléfono no es válido: debe tener de 7 a 15 dígitos (por ejemplo 300 123 4567 o 602 123 4567)."
        )
    return ("+" if con_mas else "") + digitos
