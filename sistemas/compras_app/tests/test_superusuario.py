"""El SUPERUSUARIO: un administrador cuya clave se define de antemano en el archivo .env (COMPRAS_SUPERUSUARIO y
COMPRAS_SUPERUSUARIO_CLAVE). Se crea o se deja en regla en cada arranque y no se puede tocar desde la pantalla.

Las claves de estas pruebas son inventadas: la clave real de la Clínica vive solo en su .env, nunca en el código."""

import pytest

from app import database, main
from tests.conftest import entrar

CLAVE = "Super-Prueba77*"  # lleva «*» a propósito: así se comprueba que el .env admite símbolos


def _preparar(monkeypatch, usuario: str | None = "superadmin", clave: str | None = CLAVE) -> None:
    if usuario is not None:
        monkeypatch.setenv("COMPRAS_SUPERUSUARIO", usuario)
    if clave is not None:
        monkeypatch.setenv("COMPRAS_SUPERUSUARIO_CLAVE", clave)


def _arrancar() -> None:
    """Lo que hace la aplicación al encender, en cuanto al superusuario."""
    con = database.conectar()
    try:
        main.asegurar_superusuario(con)
    finally:
        con.close()


def _sql(consulta: str, *params):
    con = database.conectar()
    try:
        r = con.execute(consulta, params).fetchall()
        con.commit()
        return r
    finally:
        con.close()


def _fila(cliente, usuario: str) -> dict:
    return next(u for u in cliente.get("/api/usuarios").json()["usuarios"] if u["usuario"] == usuario)


def test_el_arranque_crea_al_superusuario_que_entra_a_todo(cliente, anonimo, monkeypatch, capsys):
    _preparar(monkeypatch)
    _arrancar()
    salida = capsys.readouterr().out
    assert "Superusuario «superadmin» creado" in salida
    assert CLAVE not in salida  # la clave nunca se imprime
    r = entrar(anonimo, "superadmin", CLAVE)
    assert r.status_code == 200
    u = r.json()["usuario"]
    assert u["rol"] == "admin" and u["cambiar_clave"] is False  # entra directo, sin pedir cambiar la clave
    for ruta in ("/api/usuarios", "/api/admin/tablas", "/api/resumen", "/api/avisos"):
        assert anonimo.get(ruta).status_code == 200, ruta  # puede todo lo del administrador


def test_sin_nombre_en_el_env_se_llama_superadmin(cliente, anonimo, monkeypatch):
    _preparar(monkeypatch, usuario=None)
    _arrancar()
    assert entrar(anonimo, "superadmin", CLAVE).status_code == 200


def test_se_puede_poner_otro_nombre(cliente, anonimo, monkeypatch):
    _preparar(monkeypatch, usuario="Jefe.Compras")
    _arrancar()
    assert entrar(anonimo, "jefe.compras", CLAVE).status_code == 200  # el nombre se guarda en minúsculas


def test_leerlo_del_archivo_env_con_simbolos_en_la_clave(cliente, anonimo, monkeypatch, tmp_path):
    env = tmp_path / "config.env"
    env.write_text(f"COMPRAS_SUPERUSUARIO=desde.archivo\nCOMPRAS_SUPERUSUARIO_CLAVE={CLAVE}\n", encoding="utf-8")
    monkeypatch.setenv("COMPRAS_ENV", str(env))
    _arrancar()
    assert entrar(anonimo, "desde.archivo", CLAVE).status_code == 200


def test_reiniciar_con_todo_en_regla_no_cambia_nada(cliente, anonimo, monkeypatch, capsys):
    _preparar(monkeypatch)
    _arrancar()
    entrar(anonimo, "superadmin", CLAVE)
    capsys.readouterr()
    _arrancar()
    assert capsys.readouterr().out == ""  # nada que avisar
    assert anonimo.get("/api/sesion").status_code == 200  # y su sesión sigue valiendo
    assert len([u for u in cliente.get("/api/usuarios").json()["usuarios"] if u["usuario"] == "superadmin"]) == 1


def test_si_cambia_la_clave_en_el_env_la_vieja_deja_de_valer_y_se_cierran_las_sesiones(
    cliente, anonimo, monkeypatch, capsys
):
    _preparar(monkeypatch)
    _arrancar()
    entrar(anonimo, "superadmin", CLAVE)
    nueva = "Otra-Clave88*"
    monkeypatch.setenv("COMPRAS_SUPERUSUARIO_CLAVE", nueva)
    capsys.readouterr()
    _arrancar()
    salida = capsys.readouterr().out
    assert "actualizado" in salida and nueva not in salida and CLAVE not in salida
    assert anonimo.get("/api/sesion").status_code == 401  # la sesión de la clave anterior se cerró
    assert entrar(anonimo, "superadmin", CLAVE).status_code == 401
    assert entrar(anonimo, "superadmin", nueva).status_code == 200


def test_el_env_manda_sobre_lo_que_alguien_haya_cambiado_en_la_base(cliente, anonimo, monkeypatch):
    _preparar(monkeypatch)
    _arrancar()
    _sql(
        "UPDATE usuarios SET activo = 0, rol = 'consulta', cambiar_clave = 1, intentos = 3,"
        " bloqueado_hasta = '2999-01-01 00:00:00' WHERE usuario = 'superadmin'"
    )
    assert entrar(anonimo, "superadmin", CLAVE).status_code != 200  # estropeado
    _arrancar()
    r = entrar(anonimo, "superadmin", CLAVE)
    assert r.status_code == 200
    assert r.json()["usuario"]["rol"] == "admin" and r.json()["usuario"]["cambiar_clave"] is False


def test_si_ya_existia_un_usuario_con_ese_nombre_pasa_a_ser_el_superusuario(cliente, anonimo, monkeypatch):
    datos = {
        "usuario": "camila",
        "nombre": "Camila",
        "rol": "externo",
        "cod_empresa": "1",
        "correo": "c@x.com",
        "celular": "3001234567",
    }
    assert cliente.post("/api/usuarios", json=datos).status_code == 201
    _preparar(monkeypatch, usuario="camila")
    _arrancar()
    r = entrar(anonimo, "camila", CLAVE)
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "admin"


def test_desde_la_pantalla_el_superusuario_no_se_toca(cliente, anonimo, monkeypatch):
    _preparar(monkeypatch)
    _arrancar()
    s = _fila(cliente, "superadmin")
    assert s["protegido"] is True and _fila(cliente, "admin")["protegido"] is False
    cuerpo = {"nombre": "X", "rol": "consulta", "activo": False, "correo": "x@x.com", "celular": "3001234567"}
    for r in (
        cliente.delete(f"/api/usuarios/{s['id']}"),
        cliente.put(f"/api/usuarios/{s['id']}", json=cuerpo),
        cliente.post(f"/api/usuarios/{s['id']}/clave"),
    ):
        assert r.status_code == 409 and ".env" in r.json()["detail"], r.text
    # tampoco él mismo puede cambiarse la clave desde la pantalla: se define en el .env
    entrar(anonimo, "superadmin", CLAVE)
    r = anonimo.put("/api/sesion/clave", json={"actual": CLAVE, "nueva": "Nueva-Clave99"})
    assert r.status_code == 409 and ".env" in r.json()["detail"]
    assert entrar(anonimo, "superadmin", CLAVE).status_code == 200  # nada cambió


def test_quitar_la_clave_del_env_libera_al_usuario(cliente, monkeypatch):
    _preparar(monkeypatch)
    _arrancar()
    monkeypatch.delenv("COMPRAS_SUPERUSUARIO_CLAVE")
    _arrancar()
    s = _fila(cliente, "superadmin")
    assert s["protegido"] is False and s["rol"] == "admin"  # sigue siendo administrador, pero ya normal
    assert cliente.delete(f"/api/usuarios/{s['id']}").status_code in (200, 204)


def test_sin_configuracion_no_se_crea_ningun_superusuario(cliente, capsys):
    _arrancar()
    assert capsys.readouterr().out == ""
    assert "superadmin" not in [u["usuario"] for u in cliente.get("/api/usuarios").json()["usuarios"]]


@pytest.mark.parametrize(
    "usuario, clave",
    [
        ("superadmin", "corta1"),
        ("superadmin", "sololetrasaquí"),
        ("superadmin", "12345678"),
        ("AB", CLAVE),
        ("con espacio", CLAVE),
    ],
)
def test_una_configuracion_invalida_avisa_pero_no_tumba_el_arranque(cliente, monkeypatch, capsys, usuario, clave):
    _preparar(monkeypatch, usuario=usuario, clave=clave)
    _arrancar()  # no debe lanzar errores
    salida = capsys.readouterr().out
    assert "ATENCIÓN" in salida and clave not in salida
    assert [u["usuario"] for u in cliente.get("/api/usuarios").json()["usuarios"]] == ["admin"]  # no se creó nada


def test_la_clave_no_queda_guardada_en_texto(cliente, monkeypatch):
    _preparar(monkeypatch)
    _arrancar()
    filas = _sql("SELECT * FROM usuarios") + _sql("SELECT * FROM meta")
    assert all(CLAVE not in str(tuple(f)) for f in filas)
