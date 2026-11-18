"""
PRUEBAS DE SEGURIDAD: inicio de sesión, perfiles y permisos.

Los cuatro perfiles (ver services/seguridad.py):
  admin     todo          prime     todo menos Administración (pero sí «Actualizar Excel»)
  consulta  solo ver el tablero y descargar los productos por comprar
  externo   solo ve QUÉ productos se necesita comprar (sin precios ni cantidades) y descarga ese Excel para cotizar
Usan los datos sintéticos de conftest.py (por comprar: A1 80 · C3 5 · D4 5 · 0041 6).
"""

import io
import re

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.services import seguridad
from tests.conftest import CLAVE_ADMIN, CLAVE_NUEVA, entrar


def _hoja(contenido: bytes) -> list[tuple]:
    """Las filas de la primera hoja de un Excel descargado."""
    return list(load_workbook(io.BytesIO(contenido)).active.values)


# ------------------------------------------------------------------------------------------------ permisos por perfil
# (método, ruta, cuerpo, perfiles que SÍ pueden). Los demás deben recibir 403.
CONTACTO = {"correo": "persona@prueba.com", "celular": "3001234567"}  # el contacto es obligatorio al crear usuarios

ADMIN, PRIME, CONSULTA, EXTERNO = "admin", "prime", "consulta", "externo"
INTERNOS = {ADMIN, PRIME, CONSULTA}
EDITORES = {ADMIN, PRIME}
TODOS = {ADMIN, PRIME, CONSULTA, EXTERNO}
MATRIZ = [
    # ver el tablero
    ("GET", "/api/resumen", None, INTERNOS),
    ("GET", "/api/productos", None, INTERNOS),
    ("GET", "/api/productos/A1/ofertas", None, INTERNOS),
    ("GET", "/api/exportar/productos-a-comprar", None, EDITORES),
    # cambiar cosas: administrador y prime
    ("PUT", "/api/productos/A1/seleccion", {"cod_empresa": "1"}, EDITORES),
    ("DELETE", "/api/productos/A1/seleccion", None, EDITORES),
    ("GET", "/api/productos/A1", None, EDITORES),
    ("POST", "/api/productos", {}, EDITORES),
    ("POST", "/api/ofertas", {}, EDITORES),
    ("DELETE", "/api/ofertas/999", None, EDITORES),
    ("GET", "/api/empresas", None, EDITORES),
    ("POST", "/api/empresas", {}, EDITORES),
    ("GET", "/api/catalogo", None, EDITORES),
    ("GET", "/api/avisos", None, EDITORES),
    ("GET", "/api/plantillas/productos", None, EDITORES),
    ("GET", "/api/exportar/oc", None, EDITORES),
    ("GET", "/api/exportar/alternativas", None, EDITORES),
    ("POST", "/api/cargas/productos", None, EDITORES),
    ("POST", "/api/importar", None, EDITORES),
    # «Actualizar Excel»: administrador y prime
    ("GET", "/api/admin/tablas", None, EDITORES),
    ("POST", "/api/admin/importar", {"tablas": ["empresas"], "modo": "agregar"}, EDITORES),
    ("POST", "/api/admin/tablas/empresas/importar", None, EDITORES),
    # Administración y usuarios: solo el administrador
    ("GET", "/api/admin/tablas/stock/filas", None, {ADMIN}),
    ("POST", "/api/admin/tablas/stock/filas", {"valores": {}}, {ADMIN}),
    ("PUT", "/api/admin/tablas/stock/filas/1", {"valores": {}}, {ADMIN}),
    ("DELETE", "/api/admin/tablas/stock/filas/99999", None, {ADMIN}),
    ("POST", "/api/admin/tablas/stock/filas/eliminar", {"ids": [99999]}, {ADMIN}),
    ("GET", "/api/admin/tablas/stock/filas/1/impacto", None, {ADMIN}),
    ("GET", "/api/admin/tablas/stock/excel", None, {ADMIN}),
    ("GET", "/api/admin/historial", None, {ADMIN}),
    ("POST", "/api/admin/historial/99999/deshacer", None, {ADMIN}),
    ("GET", "/api/usuarios", None, {ADMIN}),
    ("POST", "/api/usuarios", {}, {ADMIN}),
    ("PUT", "/api/usuarios/99999", {}, {ADMIN}),
    ("POST", "/api/usuarios/99999/clave", None, {ADMIN}),
    ("DELETE", "/api/usuarios/99999", None, {ADMIN}),
    ("GET", "/api/docs", None, {ADMIN}),
    ("GET", "/api/openapi.json", None, {ADMIN}),
    # el proveedor externo: SOLO su pantalla (el administrador la ve también, tal como la ve el proveedor)
    ("GET", "/api/proveedor/productos", None, {EXTERNO, ADMIN}),
    ("GET", "/api/proveedor/excel", None, {EXTERNO, ADMIN}),
    ("GET", "/api/proveedor/lista/sin_oferta", None, {EXTERNO, ADMIN}),  # las ventanas «Sin oferta» y «Nuevos»
    ("GET", "/api/proveedor/lista/nuevos", None, {EXTERNO, ADMIN}),
    ("GET", "/api/pendientes/1/excel", None, {ADMIN}),
    ("GET", "/api/proveedor/ofertas", None, {EXTERNO}),  # sus fichas enviadas
    ("POST", "/api/proveedor/ofertas", None, {EXTERNO}),  # subir su ficha (queda pendiente)
    # el administrador revisa lo que suben los proveedores
    ("GET", "/api/pendientes", None, {ADMIN}),
    ("GET", "/api/pendientes/1", None, {ADMIN}),
    ("POST", "/api/pendientes/1/aprobar", None, {ADMIN}),
    ("POST", "/api/pendientes/1/rechazar", {"motivo": "x"}, {ADMIN}),
    ("POST", "/api/pendientes/1/restaurar", None, {ADMIN}),
    # todos los que tienen sesión
    ("GET", "/api/sesion", None, TODOS),
]


@pytest.mark.parametrize("rol", [ADMIN, PRIME, CONSULTA, EXTERNO])
def test_cada_perfil_solo_puede_lo_que_le_corresponde(como, rol):
    """Matriz completa: para cada ruta, quien NO tiene permiso recibe 403 y quien sí lo tiene pasa la revisión (puede
    recibir 404 o 422 por los datos de prueba, pero nunca 401 ni 403)."""
    c = como(rol)
    for metodo, ruta, cuerpo, permitidos in MATRIZ:
        r = c.request(metodo, ruta, json=cuerpo) if cuerpo is not None else c.request(metodo, ruta)
        if rol in permitidos:
            assert r.status_code not in (401, 403), (
                f"{rol} debería poder {metodo} {ruta}: {r.status_code} {r.text[:80]}"
            )
        else:
            assert r.status_code == 403, f"{rol} NO debería poder {metodo} {ruta}: {r.status_code}"


def _rutas_de_la_api(cliente):
    """Todas las (método, ruta) de la API, con los parámetros reemplazados por valores de ejemplo."""
    esquema = cliente.get("/api/openapi.json").json()
    for ruta, metodos in esquema["paths"].items():
        for metodo in metodos:
            yield metodo.upper(), re.sub(r"\{[^}]+\}", "1", ruta)


def test_sin_sesion_todo_es_401_menos_entrar_y_la_prueba_de_vida(cliente, anonimo):
    """Quien no inició sesión no toca NADA de la API. Solo son públicas la prueba de vida y la ruta para entrar."""
    publicas = {("GET", "/api/salud"), ("POST", "/api/sesion")}
    rutas = list(_rutas_de_la_api(cliente))
    assert len(rutas) > 40  # (la prueba recorre de verdad todas las rutas)
    for metodo, ruta in rutas:
        r = anonimo.request(metodo, ruta)
        if (metodo, ruta) in publicas:
            assert r.status_code != 401, (metodo, ruta)
        else:
            assert r.status_code == 401, f"{metodo} {ruta} respondió {r.status_code} sin sesión"


def test_toda_ruta_de_la_api_tiene_su_regla_de_permisos(cliente):
    """Si alguien agrega una ruta nueva y olvida listarla en la tabla de permisos, esta prueba FALLA (no se queda «abierta»).
    Las de /api/admin y /api/usuarios ya las cubre la regla general de solo administrador."""
    sin_regla = []
    for metodo, ruta in _rutas_de_la_api(cliente):
        if re.match(r"/api/(admin|usuarios)(/|$)", ruta):
            continue
        especificas = seguridad.POLITICA[:-1]  # todas menos la regla general (la última)
        if not any(metodo in m and p.fullmatch(ruta) for m, p, _ in especificas):
            sin_regla.append(f"{metodo} {ruta}")
    # Las dos de la documentación no están en el esquema (include_in_schema=False) y caen en «solo administrador».
    assert sin_regla == [], f"Rutas sin regla de permisos: {sin_regla}"


def test_lo_que_no_esta_en_la_tabla_se_niega_a_todos_menos_al_administrador(cliente, como):
    """Una ruta con permisos sin listar (por ejemplo una nueva que alguien olvidó agregar) solo la puede pedir el administrador.
    (Una dirección que NO existe responde 404 a todo el mundo: FastAPI lo decide antes de revisar permisos.)"""
    assert seguridad.roles_permitidos("GET", "/api/loquesea") == {"admin"}
    assert seguridad.roles_permitidos("DELETE", "/api/admin/lo-que-sea/1") == {"admin"}
    assert como("prime").get("/api/loquesea").status_code == 404
    assert como("prime").get("/api/usuarios/1/otra-cosa").status_code == 404


# ------------------------------------------------------------------------------------------------ iniciar sesión
def test_entrar_deja_una_cookie_que_javascript_no_puede_leer(cliente, anonimo):
    """La sesión viaja en una cookie HttpOnly y SameSite=Lax; la respuesta nunca trae la huella de la clave."""
    r = entrar(anonimo, "admin", CLAVE_ADMIN)
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "admin"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "clave_hash" not in r.text and "scrypt" not in r.text
    assert anonimo.get("/api/sesion").json()["usuario"]["usuario"] == "admin"


def test_el_mensaje_de_error_no_dice_si_el_usuario_existe(anonimo):
    """«Usuario inexistente» y «clave incorrecta» dan exactamente la misma respuesta."""
    a = entrar(anonimo, "admin", "incorrecta1")
    b = entrar(anonimo, "nadie", "incorrecta1")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_cinco_claves_incorrectas_bloquean_el_usuario_un_rato(cliente, anonimo):
    """Al quinto fallo seguido se bloquea (429) incluso con la clave correcta; pasado el tiempo, vuelve a entrar."""
    from app.database import conectar

    for _ in range(seguridad.MAX_INTENTOS):
        assert entrar(anonimo, "admin", "incorrecta1").status_code == 401
    r = entrar(anonimo, "admin", CLAVE_ADMIN)
    assert r.status_code == 429 and "intentos" in r.json()["detail"]
    con = conectar()  # «pasan 6 minutos»
    con.execute("UPDATE usuarios SET bloqueado_hasta = '2000-01-01 00:00:00'")
    con.commit()
    con.close()
    assert entrar(anonimo, "admin", CLAVE_ADMIN).status_code == 200


def test_un_acierto_borra_los_fallos_anteriores(anonimo):
    """4 fallos, un acierto y otros 4 fallos NO bloquean: la cuenta de fallos es «seguidos»."""
    for _ in range(4):
        entrar(anonimo, "admin", "incorrecta1")
    assert entrar(anonimo, "admin", CLAVE_ADMIN).status_code == 200
    for _ in range(4):
        assert entrar(anonimo, "admin", "incorrecta1").status_code == 401
    assert entrar(anonimo, "admin", CLAVE_ADMIN).status_code == 200


def test_salir_invalida_la_sesion_aunque_alguien_guarde_la_cookie(cliente, anonimo):
    """«Salir» borra la sesión EN EL SERVIDOR: la cookie vieja ya no sirve."""
    entrar(anonimo, "admin", CLAVE_ADMIN)
    vieja = anonimo.cookies.get("sesion")
    assert anonimo.get("/api/resumen").status_code == 200
    assert anonimo.delete("/api/sesion").status_code == 200
    assert anonimo.get("/api/resumen").status_code == 401
    otro = TestClient(anonimo.app, cookies={"sesion": vieja})
    assert otro.get("/api/resumen").status_code == 401


def test_la_sesion_vence_a_las_12_horas(cliente):
    """Pasada su hora de vencimiento la sesión deja de valer."""
    from app.database import conectar

    assert cliente.get("/api/resumen").status_code == 200
    con = conectar()
    con.execute("UPDATE sesiones SET expira = '2000-01-01 00:00:00'")
    con.commit()
    con.close()
    assert cliente.get("/api/resumen").status_code == 401


def test_un_usuario_desactivado_no_entra_y_pierde_su_sesion_al_instante(cliente, como):
    """Desactivar cierra la sesión YA (no cuando venza) y en adelante no puede entrar."""
    c = como("consulta")
    assert c.get("/api/resumen").status_code == 200
    u = next(x for x in cliente.get("/api/usuarios").json()["usuarios"] if x["usuario"] == "consulta1")
    r = cliente.put(
        f"/api/usuarios/{u['id']}", json={"nombre": u["nombre"], "rol": "consulta", "activo": False, **CONTACTO}
    )
    assert r.status_code == 200
    assert c.get("/api/resumen").status_code == 401
    assert entrar(TestClient(cliente.app), "consulta1", CLAVE_NUEVA).status_code == 403


def test_cambiar_el_perfil_de_alguien_le_cierra_la_sesion(cliente, como):
    """Si a alguien le cambian el perfil, su sesión vieja (con los permisos de antes) se cierra."""
    c = como("prime")
    u = next(x for x in cliente.get("/api/usuarios").json()["usuarios"] if x["usuario"] == "prime1")
    cliente.put(f"/api/usuarios/{u['id']}", json={"nombre": u["nombre"], "rol": "consulta", "activo": True, **CONTACTO})
    assert c.get("/api/resumen").status_code == 401
    c2 = TestClient(cliente.app)
    entrar(c2, "prime1", CLAVE_NUEVA)
    assert c2.get("/api/resumen").status_code == 200 and c2.get("/api/avisos").status_code == 403  # ya es «consulta»


# ------------------------------------------------------------------------------------------------ claves
@pytest.mark.parametrize(
    "clave,error",
    [
        ("corta1", "al menos 8"),
        ("sololetrasaqui", "letras y números"),
        ("12345678", "letras y números"),
        ("x" * 129 + "1", "demasiado larga"),
    ],
)
def test_reglas_de_una_clave_nueva(clave, error):
    """8 a 128 caracteres, con letras y números."""
    with pytest.raises(seguridad.SeguridadError, match=error):
        seguridad.validar_clave(clave)
    seguridad.validar_clave("Buena1234")  # esta sí


def test_la_clave_no_puede_ser_igual_al_usuario():
    with pytest.raises(seguridad.SeguridadError, match="igual al usuario"):
        seguridad.validar_clave("usuario123", "Usuario123")


def test_la_clave_nunca_se_guarda_ni_se_devuelve(cliente):
    """En la base solo hay la huella (scrypt, con sal); dos usuarios con la misma clave tienen huellas distintas; y la lista
    de usuarios nunca trae claves."""
    from app.database import conectar

    cliente.post("/api/usuarios", json={"usuario": "a1", "nombre": "A", "rol": "consulta", **CONTACTO})
    con = conectar()
    huellas = [f[0] for f in con.execute("SELECT clave_hash FROM usuarios")]
    con.close()
    assert all(h.startswith("scrypt$") for h in huellas) and CLAVE_ADMIN not in "".join(huellas)
    assert seguridad.hashear("Igual1234") != seguridad.hashear("Igual1234")
    assert seguridad.verificar("Igual1234", seguridad.hashear("Igual1234"))
    texto = cliente.get("/api/usuarios").text
    assert "clave_hash" not in texto and "scrypt" not in texto


def test_cambiar_mi_clave_pide_la_actual_y_cierra_mis_otras_sesiones(cliente, anonimo):
    """Cambiar la clave exige la actual, rechaza claves débiles o iguales, y cierra las OTRAS sesiones del usuario."""
    entrar(anonimo, "admin", CLAVE_ADMIN)
    url = "/api/sesion/clave"
    assert cliente.put(url, json={"actual": "incorrecta1", "nueva": CLAVE_NUEVA}).status_code == 403
    assert cliente.put(url, json={"actual": CLAVE_ADMIN, "nueva": "corta"}).status_code == 422
    assert cliente.put(url, json={"actual": CLAVE_ADMIN, "nueva": CLAVE_ADMIN}).status_code == 422
    assert cliente.put(url, json={"actual": CLAVE_ADMIN, "nueva": CLAVE_NUEVA}).status_code == 200
    assert cliente.get("/api/resumen").status_code == 200  # la sesión desde la que se cambió sigue
    assert anonimo.get("/api/resumen").status_code == 401  # la otra se cerró
    assert entrar(TestClient(cliente.app), "admin", CLAVE_ADMIN).status_code == 401  # la vieja ya no vale
    assert entrar(TestClient(cliente.app), "admin", CLAVE_NUEVA).status_code == 200


def test_con_clave_temporal_solo_se_puede_cambiarla(cliente):
    """Un usuario nuevo entra con una clave temporal: hasta que la cambie, todo lo demás da 403."""
    r = cliente.post("/api/usuarios", json={"usuario": "nuevo1", "nombre": "Nuevo", "rol": "consulta", **CONTACTO})
    assert r.status_code == 201 and r.json()["usuario"]["cambiar_clave"] is True
    temporal = r.json()["clave_temporal"]
    assert len(temporal) == 10 and re.search(r"\d", temporal) and re.search(r"[A-Za-z]", temporal)
    c = TestClient(cliente.app)
    assert entrar(c, "nuevo1", temporal).json()["usuario"]["cambiar_clave"] is True
    assert c.get("/api/sesion").status_code == 200
    bloqueada = c.get("/api/resumen")
    assert bloqueada.status_code == 403 and "cambiar tu clave" in bloqueada.json()["detail"]
    assert c.put("/api/sesion/clave", json={"actual": temporal, "nueva": CLAVE_NUEVA}).status_code == 200
    assert c.get("/api/resumen").status_code == 200


# ------------------------------------------------------------------------------------------------ gestionar usuarios
def test_crear_un_usuario_valida_los_datos(cliente):
    """Usuario único y bien escrito, perfil válido y proveedor que exista (solo para externos)."""
    mal = {"nombre": "X", "rol": "consulta", **CONTACTO}
    assert cliente.post("/api/usuarios", json={**mal, "usuario": "ab"}).status_code == 422  # muy corto
    assert cliente.post("/api/usuarios", json={**mal, "usuario": "con espacio"}).status_code == 422
    assert cliente.post("/api/usuarios", json={**mal, "usuario": "tilde\u00f1"}).status_code == 422
    assert (
        cliente.post(
            "/api/usuarios", json={"usuario": "ok1", "nombre": "  ", "rol": "consulta", **CONTACTO}
        ).status_code
        == 422
    )
    assert cliente.post("/api/usuarios", json={**mal, "usuario": "ok1", "rol": "dios"}).status_code == 422
    assert (
        cliente.post("/api/usuarios", json={**mal, "usuario": "ok1", "cod_empresa": "1"}).status_code == 422
    )  # no externo
    assert (
        cliente.post(
            "/api/usuarios", json={**mal, "usuario": "ok1", "rol": "externo", "cod_empresa": "777"}
        ).status_code
        == 422
    )
    ok = cliente.post("/api/usuarios", json={**mal, "usuario": "Externo.Uno", "rol": "externo", "cod_empresa": "1"})
    assert ok.status_code == 201 and ok.json()["usuario"]["usuario"] == "externo.uno"  # se guarda en minúsculas
    assert ok.json()["usuario"]["empresa"] == "ALFA SAS"
    assert cliente.post("/api/usuarios", json={**mal, "usuario": "EXTERNO.UNO"}).status_code == 409  # duplicado


def test_no_se_puede_dejar_el_sistema_sin_administrador(cliente):
    """Nadie se quita el perfil ni se desactiva ni se elimina a sí mismo, y el último administrador está protegido."""
    yo = next(x for x in cliente.get("/api/usuarios").json()["usuarios"] if x["usuario"] == "admin")
    cuerpo = {"nombre": "Administrador", "rol": "consulta", "activo": True, **CONTACTO}
    assert cliente.put(f"/api/usuarios/{yo['id']}", json=cuerpo).status_code == 409
    assert cliente.put(f"/api/usuarios/{yo['id']}", json={**cuerpo, "rol": "admin", "activo": False}).status_code == 409
    assert cliente.delete(f"/api/usuarios/{yo['id']}").status_code == 409
    # Otro administrador intenta quitarle el perfil al ÚNICO administrador: también se rechaza (vía el servicio).
    from app.database import conectar

    con = conectar()
    with pytest.raises(seguridad.SeguridadError, match="al menos un administrador"):
        seguridad.editar(con, yo["id"], "Administrador", "prime", None, True, actor_id=9999)
    with pytest.raises(seguridad.SeguridadError, match="al menos un administrador"):
        seguridad.eliminar(con, yo["id"], actor_id=9999)
    con.close()
    # Con un segundo administrador, sí se puede cambiar al primero.
    cliente.post("/api/usuarios", json={"usuario": "admin2", "nombre": "Dos", "rol": "admin", **CONTACTO})
    assert cliente.get("/api/usuarios").json()["usuarios"][0]["rol"] == "admin"


def test_restablecer_la_clave_da_una_temporal_y_cierra_sus_sesiones(cliente, como):
    """El administrador restablece la clave: la vieja no sirve, la sesión abierta se cierra y debe cambiarla al entrar."""
    c = como("consulta")
    u = next(x for x in cliente.get("/api/usuarios").json()["usuarios"] if x["usuario"] == "consulta1")
    r = cliente.post(f"/api/usuarios/{u['id']}/clave")
    assert r.status_code == 200
    temporal = r.json()["clave_temporal"]
    assert c.get("/api/resumen").status_code == 401
    assert entrar(TestClient(cliente.app), "consulta1", CLAVE_NUEVA).status_code == 401
    nuevo = TestClient(cliente.app)
    assert entrar(nuevo, "consulta1", temporal).json()["usuario"]["cambiar_clave"] is True


def test_eliminar_un_usuario(cliente, como):
    """Eliminado, el usuario desaparece de la lista y su sesión ya no vale."""
    c = como("consulta")
    u = next(x for x in cliente.get("/api/usuarios").json()["usuarios"] if x["usuario"] == "consulta1")
    assert cliente.delete(f"/api/usuarios/{u['id']}").status_code == 200
    assert c.get("/api/resumen").status_code == 401
    assert all(x["usuario"] != "consulta1" for x in cliente.get("/api/usuarios").json()["usuarios"])
    assert cliente.delete(f"/api/usuarios/{u['id']}").status_code == 404


# ------------------------------------------------------------------------------------------------ proveedor externo
def test_el_proveedor_solo_ve_que_se_necesita_sin_precios_ni_cantidades(como):
    """La pantalla del proveedor trae los 4 productos por comprar con SOLO código y descripción: ni precios ni cantidades, ni
    otros proveedores, ni existencias, ni stock (aunque los productos tengan ofertas en el sistema)."""
    c = como("externo")
    r = c.get("/api/proveedor/productos").json()
    assert r["total"] == 4
    assert {i["cod"] for i in r["items"]} == {"A1", "C3", "D4", "0041"}
    assert all(set(i) == {"cod", "descripcion"} for i in r["items"])
    # Las CLAVES de la respuesta son lo que garantiza que no salgan precios ni datos de otros proveedores.
    # `conteos` son solo DOS NÚMEROS (cuántos productos hay «sin oferta» y «nuevos»): los de los botones de su pantalla. Nada más se agrega.
    assert set(r) == {"total", "pagina", "paginas", "tam", "items", "conteos"}
    assert set(r["conteos"]) == {"sin_oferta", "nuevos"} and all(isinstance(v, int) for v in r["conteos"].values())
    nombres = [i["descripcion"].lower() for i in r["items"]]
    assert nombres == sorted(nombres)  # de la A a la Z


def test_el_proveedor_busca_y_pagina(como):
    """Buscar ignora tildes y mayúsculas; la paginación respeta el mínimo de 10 por página."""
    c = como("externo")
    assert [i["cod"] for i in c.get("/api/proveedor/productos", params={"q": "nandu"}).json()["items"]] == ["0041"]
    assert c.get("/api/proveedor/productos", params={"q": "no existe"}).json()["total"] == 0
    p = c.get("/api/proveedor/productos", params={"tam": 1}).json()
    assert p["tam"] == 10 and p["paginas"] == 1


# (El Excel que descarga el proveedor ahora es la FICHA OFICIAL FR-GDS-07: sin cantidades ni precios de nadie, con su código y contacto, y
# se sube de vuelta tal cual. Esas pruebas están en tests/test_libros_excel.py.)


# ------------------------------------------------------------------------------------------------ descargas y auditoría
def test_consulta_ya_no_descarga_y_prime_si_los_productos_a_comprar(como):
    """Consulta NO descarga Excel (403). El de productos por comprar lo bajan admin y Prime: los 4 productos por comprar con cantidad, proveedor elegido, precio y total; el que nadie
    ofrece (D4) sale con el proveedor vacío."""
    assert como("consulta").get("/api/exportar/productos-a-comprar").status_code == 403
    r = como("prime").get("/api/exportar/productos-a-comprar")
    assert r.status_code == 200 and 'filename="PRODUCTOS_A_COMPRAR.xlsx"' in r.headers["content-disposition"]
    filas = _hoja(r.content)
    assert list(filas[0]) == [
        "COD_PRODUCTO",
        "DESCRIPCION",
        "STOCK MAXIMO",
        "EXISTENCIAS",
        "CANT_COMPRAR",
        "PROVEEDOR",
        "VALOR",
        "TOTAL",
    ]
    por_cod = {f[0]: f for f in filas[1:]}
    assert set(por_cod) == {"A1", "C3", "D4", "0041"}
    assert por_cod["A1"][4:] == (80, "BETA SAS", 85, 85 * 80)
    assert por_cod["D4"][4:] == (5, None, None, None)


def test_el_historial_anota_quien_hizo_cada_cambio(cliente, como):
    """Cada cambio queda con el usuario de la sesión: lo que hace el administrador y lo que importa un usuario prime."""
    cliente.post(
        "/api/admin/tablas/empresas/filas",
        json={"valores": {"CODIGO_EMPRESA": "9", "NOMBRE": "X", "TELEFONO": "3001234567", "CORREO": "x@empresa.com"}},
    )
    como("prime").post("/api/admin/importar", json={"tablas": ["empresas"], "modo": "agregar"})
    h = cliente.get("/api/admin/historial").json()
    assert h[0]["usuario"] == "prime1" and h[0]["accion"] == "importar"
    assert next(c for c in h if c["accion"] == "agregar")["usuario"] == "admin"


def test_prime_puede_actualizar_excel_pero_no_ver_ni_editar_las_tablas(como):
    """Prime usa «Actualizar Excel» (importar) y agrega ofertas, pero no entra a las tablas de Administración."""
    p = como("prime")
    assert p.post("/api/admin/importar", json={"tablas": ["empresas"], "modo": "agregar"}).status_code == 200
    assert p.put("/api/productos/A1/seleccion", json={"cod_empresa": "1"}).status_code == 200
    assert p.get("/api/admin/tablas/stock/filas").status_code == 403
    assert p.get("/api/admin/historial").status_code == 403
    assert p.get("/api/usuarios").status_code == 403


def test_consulta_no_puede_cambiar_nada(como, cliente):
    """Con el perfil de consulta, ninguna escritura prospera y los datos quedan intactos."""
    c = como("consulta")
    antes = cliente.get("/api/resumen").json()["inversion_total"]
    for metodo, ruta, cuerpo in [
        ("PUT", "/api/productos/A1/seleccion", {"cod_empresa": "1"}),
        ("POST", "/api/ofertas", {"cod_producto": "D4", "empresa_nueva": "X", "valor": 5}),
        ("POST", "/api/empresas", {"nombre": "Nueva"}),
        ("DELETE", "/api/productos/A1", None),
        ("POST", "/api/importar", None),
    ]:
        assert c.request(metodo, ruta, json=cuerpo).status_code == 403
    assert cliente.get("/api/resumen").json()["inversion_total"] == antes


# ------------------------------------------------------------------------------------------------ endurecimiento
def test_una_peticion_que_viene_de_otra_pagina_web_se_rechaza(cliente):
    """Protección CSRF: un POST con sesión válida pero con Origin de OTRO sitio da 403; con el Origin propio, pasa."""
    cuerpo = {"valores": {"CODIGO_EMPRESA": "9", "NOMBRE": "X", "TELEFONO": "3001234567", "CORREO": "x@empresa.com"}}
    ajeno = cliente.post(
        "/api/admin/tablas/empresas/filas", json=cuerpo, headers={"Origin": "http://sitio-malo.example"}
    )
    assert ajeno.status_code == 403 and "origen" in ajeno.json()["detail"].lower()
    propio = cliente.post("/api/admin/tablas/empresas/filas", json=cuerpo, headers={"Origin": "http://testserver"})
    assert propio.status_code == 201


def test_las_respuestas_llevan_cabeceras_de_seguridad(cliente, anonimo):
    """La API no se guarda en caché; ninguna página se puede incrustar en otra; y la política CSP solo permite lo propio."""
    api = cliente.get("/api/resumen")
    assert api.headers["cache-control"] == "no-store" and api.headers["x-frame-options"] == "DENY"
    assert api.headers["x-content-type-options"] == "nosniff"
    pagina = anonimo.get("/")
    assert pagina.status_code == 200 and "script-src 'self'" in pagina.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in pagina.headers["content-security-policy"]


def test_la_documentacion_de_la_api_es_solo_del_administrador(cliente, como, anonimo):
    """/docs ya no existe; /api/docs lo ve el administrador y nadie más."""
    assert anonimo.get("/docs").status_code == 404
    assert anonimo.get("/api/docs").status_code == 401
    assert como("prime").get("/api/docs").status_code == 403
    assert cliente.get("/api/docs").status_code == 200


def test_el_primer_arranque_crea_el_administrador_con_clave_temporal(tmp_path, monkeypatch):
    """Sin COMPRAS_ADMIN_CLAVE se genera una clave al azar que hay que cambiar; con usuarios ya creados no se vuelve a crear."""
    monkeypatch.setenv("COMPRAS_DB", str(tmp_path / "nueva.db"))
    monkeypatch.delenv("COMPRAS_ADMIN_CLAVE", raising=False)
    from app.database import conectar, iniciar_db

    iniciar_db()
    con = conectar()
    clave = seguridad.asegurar_administrador(con)
    assert clave and len(clave) == 10
    u = con.execute("SELECT * FROM usuarios WHERE usuario = 'admin'").fetchone()
    assert u["rol"] == "admin" and u["cambiar_clave"] == 1 and seguridad.verificar(clave, u["clave_hash"])
    assert seguridad.asegurar_administrador(con) is None  # ya hay usuarios: no crea otro
    con.close()


def test_la_terminal_de_emergencia_restablece_la_clave_del_administrador(cliente, capsys):
    """Si se pierde la clave, `python -m app.usuarios_cli restablecer admin` da una temporal y la vieja deja de servir."""
    from app import usuarios_cli

    assert usuarios_cli.main(["restablecer", "admin"]) == 0
    salida = capsys.readouterr().out
    temporal = re.search(r"Clave temporal: (\S+)", salida).group(1)
    assert entrar(TestClient(cliente.app), "admin", CLAVE_ADMIN).status_code == 401
    assert entrar(TestClient(cliente.app), "admin", temporal).json()["usuario"]["cambiar_clave"] is True
    assert usuarios_cli.main(["restablecer", "nadie"]) == 1
    assert usuarios_cli.main(["listar"]) == 0 and "admin" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------ superusuario desde la terminal
def _teclear(monkeypatch, respuestas: list[str], claves: list[str]):
    """Simula lo que escribe la persona: las respuestas normales (input) y las claves (getpass, que no se ve)."""
    import getpass

    texto, secreto = iter(respuestas), iter(claves)
    monkeypatch.setattr("builtins.input", lambda _="": next(texto))
    monkeypatch.setattr(getpass, "getpass", lambda _="": next(secreto))


def test_crear_admin_desde_la_terminal_crea_un_superusuario_que_puede_entrar(cliente, anonimo, monkeypatch, capsys):
    """`python -m app.usuarios_cli crear-admin maria`: perfil Administrador, con la clave que la persona escribió
    (sin obligarla a cambiarla) y con su contacto si lo dio."""
    from app import usuarios_cli

    _teclear(monkeypatch, ["María Pérez", "maria@clinica.com", "300 123 4567"], ["MiClave2026", "MiClave2026"])
    assert usuarios_cli.main(["crear-admin", "Maria"]) == 0
    assert "superusuario «maria» creado" in capsys.readouterr().out
    r = entrar(anonimo, "maria", "MiClave2026")
    assert r.status_code == 200
    u = r.json()["usuario"]
    assert u["rol"] == "admin" and u["nombre"] == "María Pérez" and u["cambiar_clave"] is False
    assert anonimo.get("/api/usuarios").status_code == 200  # puede todo: p. ej. gestionar usuarios
    creado = next(x for x in cliente.get("/api/usuarios").json()["usuarios"] if x["usuario"] == "maria")
    assert creado["correo"] == "maria@clinica.com" and creado["celular"] == "+573001234567"


def test_crear_admin_el_contacto_se_puede_omitir_y_el_alias_funciona(cliente, anonimo, monkeypatch):
    from app import usuarios_cli

    _teclear(monkeypatch, ["", "", ""], ["OtraClave99", "OtraClave99"])
    assert usuarios_cli.main(["crear-superusuario", "jefe"]) == 0
    assert entrar(anonimo, "jefe", "OtraClave99").json()["usuario"]["nombre"] == "jefe"  # sin nombre: usa el usuario


def test_crear_admin_vuelve_a_preguntar_si_el_dato_o_la_clave_no_sirven(cliente, anonimo, monkeypatch, capsys):
    from app import usuarios_cli

    _teclear(
        monkeypatch,
        ["Ana", "sin-arroba", "ana@clinica.com", "123", "3001234567"],  # correo y celular malos, luego buenos
        ["corta1", "corta1", "NoCoincide1", "Otra12345", "ClaveBuena77", "ClaveBuena77"],  # corta · distintas · buena
    )
    assert usuarios_cli.main(["crear-admin", "ana"]) == 0
    salida = capsys.readouterr().out
    assert "correo no es válido" in salida and "celular no es válido" in salida
    assert "al menos 8 caracteres" in salida and "no coinciden" in salida
    assert entrar(anonimo, "ana", "ClaveBuena77").status_code == 200


def test_crear_admin_no_pisa_un_usuario_existente_ni_acepta_claves_malas_siempre(cliente, monkeypatch, capsys):
    from app import usuarios_cli

    assert usuarios_cli.main(["crear-admin", "admin"]) == 1  # ya existe: no se toca
    assert "restablecer admin" in capsys.readouterr().out
    _teclear(monkeypatch, ["", "", ""], ["abc", "abc", "abc", "abc", "abc", "abc"])  # tres intentos malos
    assert usuarios_cli.main(["crear-admin", "nuevo"]) == 1
    assert "Demasiados intentos" in capsys.readouterr().out
    assert "nuevo" not in [x["usuario"] for x in cliente.get("/api/usuarios").json()["usuarios"]]
