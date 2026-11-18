"""UN USUARIO PROVEEDOR SIEMPRE VA LIGADO A UNA EMPRESA; SI EL PROVEEDOR ES NUEVO, SE AGREGA AL CREAR EL USUARIO.

Antes se podía crear un usuario proveedor sin empresa y, al querer subir su oferta, salía «Tu usuario no está ligado a un proveedor». Ahora:
  - un proveedor (perfil «externo») no se crea ni se edita sin una empresa;
  - si su empresa NO está en la lista, se agrega ahí mismo (a Administración → Empresas, con teléfono y correo obligatorios) y se liga;
  - la empresa nueva sigue la regla de no repetir (nombre sin tildes, mayúsculas, espacios ni signos) y, si algo falla, no queda nada creado «a medias».
"""

import pytest

from tests.test_admin import _filas

DATOS = {
    "usuario": "nuevo.prov",
    "nombre": "Persona Nueva",
    "rol": "externo",
    "correo": "nuevo@prov.com",
    "celular": "3150000001",
}
EMPRESA = {"nombre": "LABORATORIOS NUEVOS SAS", "telefono": "3001112233", "correo": "contacto@nuevos.com"}


def _empresas(c):
    return {e["cod"]: e["nombre"] for e in c.get("/api/empresas").json()}


def _lista(c):
    return c.get("/api/usuarios").json()["usuarios"]


def _usuarios(c):
    return sorted(u["usuario"] for u in _lista(c))


def test_un_proveedor_no_se_crea_sin_estar_ligado_a_una_empresa(cliente):
    r = cliente.post("/api/usuarios", json=DATOS)
    assert r.status_code == 422 and "debe estar ligado a un proveedor" in r.json()["detail"]
    assert "nuevo.prov" not in _usuarios(cliente)


def test_un_proveedor_tampoco_se_deja_sin_empresa_al_editarlo(cliente, como):
    como("externo", cod_empresa="3", usuario="gama.prov")
    uid = next(u["id"] for u in _lista(cliente) if u["usuario"] == "gama.prov")
    cambio = {
        "nombre": "Gama",
        "rol": "externo",
        "cod_empresa": None,
        "correo": "gama.prov@prueba.com",
        "celular": "3109999999",
        "activo": True,
    }
    assert cliente.put(f"/api/usuarios/{uid}", json=cambio).status_code == 422
    assert (
        cliente.put(f"/api/usuarios/{uid}", json={**cambio, "cod_empresa": "2"}).status_code == 200
    )  # cambiarlo a otra empresa sí


def test_si_el_proveedor_es_nuevo_se_agrega_y_el_usuario_queda_ligado(cliente):
    antes = _empresas(cliente)
    r = cliente.post("/api/usuarios", json={**DATOS, "empresa_nueva": EMPRESA})
    assert r.status_code == 201, r.text
    nuevo = r.json()["proveedor_nuevo"]
    assert nuevo["nombre"] == "LABORATORIOS NUEVOS SAS" and int(nuevo["cod"]) >= 1000
    assert r.json()["usuario"]["cod_empresa"] == nuevo["cod"]
    assert _empresas(cliente) == {
        **antes,
        nuevo["cod"]: "LABORATORIOS NUEVOS SAS",
    }  # ya es un proveedor más del sistema
    fila = next(f for f in _filas(cliente, "empresas")["filas"] if f["valores"]["CODIGO_EMPRESA"] == nuevo["cod"])
    assert (
        fila["valores"]["TELEFONO"] == "3001112233" or "3001112233" in fila["valores"]["TELEFONO"]
    )  # quedó en Administración → Empresas, con su contacto
    assert fila["valores"]["CORREO"] == "contacto@nuevos.com"


def test_el_proveedor_nuevo_entra_y_puede_usar_su_pantalla(cliente, como):
    r = cliente.post("/api/usuarios", json={**DATOS, "empresa_nueva": EMPRESA})
    assert r.status_code == 201, r.text
    # entra con la clave temporal y la cambia, como cualquier usuario
    from fastapi.testclient import TestClient

    from app import main
    from tests.conftest import entrar

    c = TestClient(main.app)
    assert entrar(c, "nuevo.prov", r.json()["clave_temporal"]).status_code == 200
    assert (
        c.put("/api/sesion/clave", json={"actual": r.json()["clave_temporal"], "nueva": "OtraClave2026"}).status_code
        == 200
    )
    assert (
        c.get("/api/proveedor/productos").status_code == 200 and c.get("/api/proveedor/ofertas").json() == []
    )  # ya NO dice «no está ligado»
    assert c.get("/api/proveedor/excel").status_code == 200


@pytest.mark.parametrize("nombre", ["alfa sas", "ÁLFA S.A.S.", "A.L.F.A. SAS", "  Alfa  Sas "])
def test_el_proveedor_nuevo_no_puede_repetir_uno_que_ya_existe(cliente, nombre):
    antes, usuarios = _empresas(cliente), _usuarios(cliente)
    r = cliente.post("/api/usuarios", json={**DATOS, "empresa_nueva": {**EMPRESA, "nombre": nombre}})
    assert r.status_code == 409 and "ALFA SAS" in r.json()["detail"], r.text
    assert _empresas(cliente) == antes and _usuarios(cliente) == usuarios  # no quedó ni la empresa ni el usuario


@pytest.mark.parametrize("falta", ["telefono", "correo"])
def test_el_proveedor_nuevo_exige_su_telefono_y_su_correo(cliente, falta):
    antes, usuarios = _empresas(cliente), _usuarios(cliente)
    r = cliente.post("/api/usuarios", json={**DATOS, "empresa_nueva": {**EMPRESA, falta: ""}})
    assert r.status_code in (409, 422), r.text
    assert _empresas(cliente) == antes and _usuarios(cliente) == usuarios


def test_si_el_usuario_no_se_puede_crear_no_queda_el_proveedor_a_medias(cliente):
    cliente.post("/api/usuarios", json={**DATOS, "empresa_nueva": EMPRESA})  # ya existe «nuevo.prov»
    antes = _empresas(cliente)
    for cambio in (
        {"empresa_nueva": {**EMPRESA, "nombre": "OTRO PROVEEDOR SAS"}},
        {"empresa_nueva": {**EMPRESA, "nombre": "TERCERO SAS"}, "correo": "otro@x.com"},
    ):
        r = cliente.post("/api/usuarios", json={**DATOS, **cambio})  # mismo usuario / mismo celular: no se puede
        assert r.status_code == 409, r.text
    assert _empresas(cliente) == antes  # ninguno de los dos proveedores nuevos quedó creado


def test_editar_a_un_proveedor_con_un_proveedor_nuevo_lo_agrega_y_lo_liga(cliente, como):
    como("externo", cod_empresa="3", usuario="gama.prov")
    uid = next(u["id"] for u in _lista(cliente) if u["usuario"] == "gama.prov")
    cambio = {
        "nombre": "Gama",
        "rol": "externo",
        "cod_empresa": None,
        "correo": "gama.prov@prueba.com",
        "celular": "3109999999",
        "activo": True,
        "empresa_nueva": EMPRESA,
    }
    r = cliente.put(f"/api/usuarios/{uid}", json=cambio)
    assert r.status_code == 200, r.text
    assert (
        r.json()["proveedor_nuevo"]["nombre"] == "LABORATORIOS NUEVOS SAS"
        and r.json()["usuario"]["cod_empresa"] == r.json()["proveedor_nuevo"]["cod"]
    )


def test_la_empresa_nueva_se_ignora_si_ya_se_eligio_una_o_si_no_es_proveedor(cliente):
    antes = _empresas(cliente)
    r = cliente.post("/api/usuarios", json={**DATOS, "cod_empresa": "2", "empresa_nueva": EMPRESA})  # ya eligió BETA
    assert r.status_code == 201 and r.json()["proveedor_nuevo"] is None and r.json()["usuario"]["cod_empresa"] == "2"
    r = cliente.post(
        "/api/usuarios",
        json={
            **DATOS,
            "usuario": "consulta.x",
            "correo": "cx@x.com",
            "celular": "3150000002",
            "rol": "consulta",
            "empresa_nueva": EMPRESA,
        },
    )
    assert r.status_code == 201 and r.json()["proveedor_nuevo"] is None
    assert _empresas(cliente) == antes  # ninguna empresa nueva
