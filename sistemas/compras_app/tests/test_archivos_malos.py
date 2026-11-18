"""ARCHIVOS Y PETICIONES MALAS: el servidor responde con un mensaje claro, nunca con un error 500 ni se queda sin memoria.

· Una «bomba de compresión»: un .xlsx que pesa poco pero, abierto, ocupa cientos de MB (una hoja con millones de ceros). Antes agotaba la
  memoria y tumbaba el servidor. Ahora se mide lo que ocuparía SIN abrirlo y se rechaza.
· Un cuerpo con bytes que no son texto, sin tipo JSON: antes lanzaba UnicodeDecodeError (error 500) en cualquier ruta que recibe JSON.
"""

import io
import zipfile

import pytest

from app.services import excel_seguro
from tests.test_cargas import OCTETOS
from tests.test_ofertas_proveedor import _gama, _subir

PARTES_XLSX = {
    "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
    "_rels/.rels": '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
}


def _bomba(megas: int) -> bytes:
    """Un .xlsx de pocos KB que, abierto, ocupa `megas` MB."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, texto in PARTES_XLSX.items():
            z.writestr(nombre, texto)
        z.writestr("xl/worksheets/sheet1.xml", "0" * (megas * 1024 * 1024))
    return b.getvalue()


@pytest.fixture()
def limite_chico(monkeypatch):
    """Baja el límite a 1 MB para probar con archivos diminutos (en la vida real son 150 MB)."""
    monkeypatch.setattr(excel_seguro, "MAX_DESCOMPRIMIDO", 1024 * 1024)


def test_la_bomba_pesa_poco_pero_se_detecta_sin_abrirla(limite_chico):
    bomba = _bomba(3)
    assert len(bomba) < 20_000  # pesa unos KB…
    assert "3 MB al abrirse" in excel_seguro.revisar_xlsx(bomba) and "máximo es 1 MB" in excel_seguro.revisar_xlsx(
        bomba
    )  # …pero abierta ocupa 3 MB


def test_un_excel_normal_y_un_archivo_que_no_es_zip_no_se_marcan(limite_chico):
    assert excel_seguro.revisar_xlsx(_bomba(0)) is None  # un xlsx casi vacío
    assert (
        excel_seguro.revisar_xlsx(b"esto no es un zip") is None and excel_seguro.revisar_xlsx(b"") is None
    )  # el lector da su propio mensaje


def test_cargar_datos_rechaza_la_bomba_con_413_y_no_toca_la_base(cliente, limite_chico):
    antes = cliente.get("/api/resumen").json()["productos"]
    for tipo in ("productos", "cotizaciones", "proveedores"):
        r = cliente.post(
            f"/api/cargas/{tipo}", params={"nombre": "x.xlsx", "aplicar": "true"}, content=_bomba(3), headers=OCTETOS
        )
        assert r.status_code == 413 and "al abrirse" in r.json()["detail"], (tipo, r.status_code, r.text)
    assert cliente.get("/api/resumen").json()["productos"] == antes


def test_actualizar_excel_rechaza_la_bomba(cliente, limite_chico):
    r = cliente.post(
        "/api/admin/tablas/stock/importar",
        params={"modo": "agregar", "nombre": "x.xlsx"},
        content=_bomba(3),
        headers=OCTETOS,
    )
    assert r.status_code == 422 and "al abrirse" in r.json()["detail"], r.text


def test_un_proveedor_externo_no_puede_tumbar_el_servidor_con_una_bomba(cliente, como, limite_chico):
    gama = _gama(como)
    r = _subir(gama, _bomba(3))
    assert r.status_code in (413, 422) and "al abrirse" in r.json()["detail"], r.text


@pytest.mark.parametrize("tipo", ["application/octet-stream", "text/plain"])
@pytest.mark.parametrize(
    "ruta", ["/api/ofertas", "/api/admin/importar", "/api/usuarios", "/api/productos", "/api/empresas", "/api/sesion"]
)
def test_un_cuerpo_con_bytes_que_no_son_texto_responde_400_y_no_500(cliente, ruta, tipo):
    r = cliente.post(ruta, content=b"\x80\x81\xfe\xff binario", headers={"Content-Type": tipo})
    assert r.status_code == 400 and "no es un texto válido" in r.json()["detail"], (ruta, r.status_code, r.text)
