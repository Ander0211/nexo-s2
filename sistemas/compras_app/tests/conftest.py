"""Datos de prueba pequeños y controlados (no dependen de tus Excel reales)."""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient


def crear_excel_sintetico(carpeta):
    """Crea los 5 Excel de prueba: pequeños y con datos INVENTADOS, para que cada resultado sea fácil de calcular a mano.

    MAPA DE DATOS (los tests se basan en esto):
      Producto  StockMax  Existencias  → A comprar   Ofertas
      A1        100       20           → 80          5 (ver abajo)
      B2        10        10           → 0           (no hay que comprarlo)
      C3        5         (ninguna)    → 5           1 (proveedor 1 a $50; la del proveedor 2 no trae precio y se ignora)
      D4        7         2            → 5           0 (¡nadie lo ofrece!)
      F6        0         —            → 0           (StockMax 0: nunca se compra)
      0041      10        4            → 6           1 ($7 del proveedor 1). Su código empieza en cero a propósito.
      X9        (solo aparece en la ficha y el portafolio: no tiene stock definido)

    Ofertas de A1 (para probar el podio): proveedor 1 $100 · proveedor 2 $90 y otra fila de $85 (repetida:
    debe quedar la de $85) · proveedor 3 $95 · proveedor 4 $120 · código «05» $130 (= proveedor 5, que NO está
    en EMPRESA.xlsx) · proveedor 6 sin precio (se ignora).
    Ranking esperado de A1: BETA $85, GAMA $95, ALFA $100, DELTA $120, proveedor 5 $130.
    El proveedor 6 aparece sin nombre en EMPRESA.xlsx (para probar los avisos)."""
    pd.DataFrame(
        {
            "COD_PRODUCTO": ["A1", "B2", "C3", "D4", "F6", "0041"],
            "DESCRIPCION": [
                "ALFA PRODUCTO",
                "BETA PRODUCTO",
                "GAMA PRODUCTO",
                "DELTA SIN OFERTA",
                "CERO",
                "AGUJA ÑANDÚ",
            ],
            "StockMax": ["100", "10", "5", "7", "0", "10"],
            "StockMed": [None] * 6,
            "StockMin": ["30", "3", "1", "2", "0", "3"],
        }
    ).to_excel(carpeta / "05-STOCK.xlsx", index=False)
    pd.DataFrame(
        {
            "COD_PRODUCTO": ["A1", "B2", "D4", "ZZ", "0041"],
            "DESCRIPCION": ["x"] * 5,
            "CANTIDAD": ["20", "10", "2", "9", "4"],
        }
    ).to_excel(carpeta / "06-EXISTENCIAS.xlsx", index=False)
    pd.DataFrame(
        {
            "CODIGO_EMPRESA": ["1", "2", "3", "4", "6"],
            "NOMBRE": ["ALFA SAS", "BETA SAS", "GAMA LTDA", "DELTA SA", None],
        }
    ).to_excel(carpeta / "EMPRESA.xlsx", index=False)
    pd.DataFrame(
        {
            "COD_SALUDIPS": ["A1", "X9"],
            "DESCRIPCION": ["ALFA", "PRODUCTO SOLO EN FICHA"],
            "TIPO_INSUMO": [None, None],
        }
    ).to_excel(carpeta / "FICHA_COTIZACION.xlsx", index=False)
    pd.DataFrame(
        {
            "COD_EMPRESA": ["1", "2", "3", "4", "2", "05", "6", "1", "2", "3", "1"],
            "COD_PRODUCTO": ["A1", "A1", "A1", "A1", "A1", "A1", "A1", "C3", "C3", "X9", "0041"],
            "DESCRIPCION": ["x"] * 11,
            "VALOR": ["100", "90", "95", "120", "85", "130", None, "50", None, "10", "7"],
            "PRESENTACION": ["X10", "X5", None, None, "X5", None, None, "X1", None, None, "X1"],
        }
    ).to_excel(carpeta / "PORTAFOLIO.xlsx", index=False)


CLAVE_ADMIN = "Prueba12345"


def entrar(c, usuario: str, clave: str):
    """Inicia sesión en un cliente de prueba (la cookie queda guardada en él). Devuelve la respuesta."""
    return c.post("/api/sesion", json={"usuario": usuario, "clave": clave})


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """Una aplicación de prueba lista para usar: base de datos temporal + Excel de prueba ya importados.
    Cada test recibe una copia limpia (tmp_path), así que ninguno afecta a los demás ni a tus datos reales."""
    excel = tmp_path / "excel"
    excel.mkdir()
    crear_excel_sintetico(excel)
    monkeypatch.setenv("COMPRAS_EXCEL_DIR", str(excel))
    monkeypatch.setenv("COMPRAS_DB", str(tmp_path / "prueba.db"))
    monkeypatch.setenv(
        "COMPRAS_ADMIN_CLAVE", CLAVE_ADMIN
    )  # el arranque crea «admin» con esta clave (sin pedir cambiarla)
    from app.main import app

    with TestClient(app) as c:  # el arranque importa los Excel sintéticos
        entrar(c, "admin", CLAVE_ADMIN)  # las pruebas de siempre corren como administrador: con sesión iniciada
        yield c


def excel_bytes(filas: list[dict], extension: str = "xlsx") -> bytes:
    """Arma en memoria un archivo Excel (o CSV) con las filas dadas, para subirlo en las pruebas de carga.

    Cada fila es un diccionario {encabezado: valor}. Los encabezados del archivo salen de las claves.
    """
    df = pd.DataFrame(filas)
    buffer = io.BytesIO()
    if extension == "csv":
        df.to_csv(buffer, index=False, sep=";")
    else:
        df.to_excel(buffer, index=False)
    return buffer.getvalue()


CLAVE_NUEVA = "NuevaClave77"


@pytest.fixture()
def como(cliente):
    """Fábrica de clientes con sesión de un perfil: `como("prime")`. El administrador crea el usuario, el usuario entra con
    la clave temporal y la cambia (como en la vida real). Se guardan para no crear dos veces el mismo."""
    from app.main import app

    creados = {}

    def _como(rol, cod_empresa=None, usuario=None):
        if rol == "admin":
            return cliente
        usuario = usuario or f"{rol}1"
        if rol == "externo" and cod_empresa is None:
            cod_empresa = "1"  # un proveedor SIEMPRE va ligado a una empresa (por defecto, ALFA SAS)
        if usuario not in creados:
            r = cliente.post(
                "/api/usuarios",
                json={
                    "usuario": usuario,
                    "nombre": f"Usuario {rol}",
                    "rol": rol,
                    "cod_empresa": cod_empresa,
                    "correo": f"{usuario}@prueba.com",  # el contacto es obligatorio
                    "celular": f"31{len(creados) + 1:08d}",  # único por persona (no se repiten celulares)
                },
            )
            assert r.status_code == 201, r.text
            temporal = r.json()["clave_temporal"]
            c = TestClient(app)
            assert entrar(c, usuario, temporal).status_code == 200
            assert c.put("/api/sesion/clave", json={"actual": temporal, "nueva": CLAVE_NUEVA}).status_code == 200
            creados[usuario] = c
        return creados[usuario]

    return _como


VARIABLES_DE_ENVIO = [
    "COMPRAS_SMTP_SERVIDOR",
    "COMPRAS_SMTP_PUERTO",
    "COMPRAS_SMTP_USUARIO",
    "COMPRAS_SMTP_CLAVE",
    "COMPRAS_SMTP_REMITENTE",
    "COMPRAS_SMTP_TLS",
    "COMPRAS_WHATSAPP_TOKEN",
    "COMPRAS_WHATSAPP_ID_NUMERO",
    "COMPRAS_WHATSAPP_PLANTILLA",
    "COMPRAS_WHATSAPP_PLANTILLA_RESTABLECER",
    "COMPRAS_WHATSAPP_IDIOMA",
    "COMPRAS_URL_PUBLICA",
    "COMPRAS_SUPERUSUARIO",
    "COMPRAS_SUPERUSUARIO_CLAVE",
    "SENTINEL_WHATSAPP_PLANTILLA",  # de SENTINEL (Nexo S²): SUMIPABON los mira para no usar la misma plantilla
    "SENTINEL_WHATSAPP_PLANTILLA_RESTABLECER",
]


@pytest.fixture(autouse=True)
def sin_envios_reales(monkeypatch, tmp_path):
    """SEGURIDAD de las pruebas: aunque en tu equipo tengas correo y WhatsApp configurados (variables del sistema o archivo
    .env), ninguna prueba debe enviar mensajes de verdad. Se borran esas variables y se apunta a un .env que no existe;
    las pruebas de envío ponen aquí sus propios dobles."""
    for v in VARIABLES_DE_ENVIO:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("COMPRAS_ENV", str(tmp_path / "no-existe.env"))
    monkeypatch.setenv("COMPRAS_ENV_SENTINEL", str(tmp_path / "no-existe-sentinel.env"))


@pytest.fixture()
def anonimo(cliente):
    """Un navegador SIN sesión iniciada (comparte la aplicación y la base de datos con `cliente`)."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
