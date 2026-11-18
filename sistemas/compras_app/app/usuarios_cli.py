"""
USUARIOS DESDE LA TERMINAL
==========================
Por si se pierde la clave del administrador (la pantalla no puede ayudar si nadie puede entrar). Se ejecuta en la carpeta
del proyecto, con el entorno activado (o con .venv/…/python):

    python -m app.usuarios_cli listar                  muestra los usuarios (sin claves)
    python -m app.usuarios_cli restablecer admin       le pone una clave temporal nueva y la muestra (deberá cambiarla al entrar)
    python -m app.usuarios_cli probar-correo yo@dominio.com   envía un correo de prueba y dice qué falla si no sale
    python -m app.usuarios_cli crear-admin maria       crea un SUPERUSUARIO (perfil Administrador) con la clave que tú escribas
                                                       (también se llama  crear-superusuario ; la clave no se ve al escribirla)
"""

import getpass
import sys

from .database import conectar, iniciar_db
from .services import notificaciones, seguridad
from .services.seguridad import SeguridadError


def _probar_correo(destino: str) -> int:
    """Envía un correo de prueba con la configuración actual y explica qué está mal si no se puede."""
    ruta = notificaciones._archivo_env()
    print(f"Archivo de configuración: {ruta} ({'existe' if ruta.exists() else 'NO existe'})")
    if not notificaciones.correo_configurado():
        print(
            "El correo NO está configurado: falta COMPRAS_SMTP_SERVIDOR (ponla en el archivo .env o en las variables del sistema)."
        )
        print(notificaciones.diagnostico_env())
        return 1
    servidor = notificaciones._env("COMPRAS_SMTP_SERVIDOR")
    puerto = notificaciones._env("COMPRAS_SMTP_PUERTO") or 587
    print(f"Servidor: {servidor}:{puerto}   Usuario: {notificaciones._env('COMPRAS_SMTP_USUARIO') or '(ninguno)'}")
    try:
        notificaciones.enviar_correo(
            destino, "Prueba de correo de SUMIPABON", "Si lees esto, el envío de correo de Nexo S² (SUMIPABON) funciona."
        )
    except notificaciones.NotificacionError as e:
        print(f"NO se pudo enviar: {e}")
        return 1
    print(f"Enviado a {destino}. Revisa la bandeja (y el spam).")
    return 0


def _pedir_opcional(texto: str, validar) -> str | None:
    """Pregunta un dato que se puede omitir (Enter) y repite la pregunta mientras lo escrito no sea válido."""
    while True:
        valor = input(texto).strip()
        if not valor:
            return None
        try:
            return validar(valor)
        except SeguridadError as e:
            print(f"  {e.mensaje}")


def _crear_superusuario(usuario: str) -> int:
    """Crea un administrador (el «superusuario» de SUMIPABON: puede todo) pidiendo sus datos por la terminal.
    La clave la escribe la persona (no se ve en pantalla) y no se le obliga a cambiarla: ya es suya."""
    usuario = usuario.strip().lower()
    iniciar_db()
    con = conectar()
    try:
        if con.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (usuario,)).fetchone():
            print(
                f"Ya existe el usuario «{usuario}». Para ponerle una clave nueva usa:  "
                f"python -m app.usuarios_cli restablecer {usuario}"
            )
            return 1
        nombre = input(f"Nombre para mostrar [{usuario}]: ").strip() or usuario
        correo = _pedir_opcional("Correo (Enter para omitir): ", seguridad.normalizar_correo)
        celular = _pedir_opcional("Celular (Enter para omitir): ", seguridad.normalizar_celular)
        for _ in range(3):
            clave = getpass.getpass("Clave (no se ve al escribir): ")
            if clave != getpass.getpass("Repite la clave: "):
                print("  Las dos claves no coinciden. Intenta de nuevo.")
                continue
            try:
                seguridad.validar_clave(clave, usuario)
            except SeguridadError as e:
                print(f"  {e.mensaje}")
                continue
            try:
                seguridad.crear(con, usuario, nombre, "admin", clave=clave, correo=correo, celular=celular)
            except SeguridadError as e:
                print(f"No se pudo crear el usuario: {e.mensaje}")
                return 1
            print(f"Listo: superusuario «{usuario}» creado (perfil Administrador). Ya puede ingresar con esa clave.")
            return 0
        print("Demasiados intentos con la clave: no se creó el usuario.")
        return 1
    finally:
        con.close()


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "probar-correo":  # no necesita la base de datos
        return _probar_correo(argv[1].strip())
    if len(argv) == 2 and argv[0] in ("crear-admin", "crear-superusuario"):
        return _crear_superusuario(argv[1])
    iniciar_db()
    con = conectar()
    try:
        if argv[:1] == ["listar"]:
            for u in seguridad.listar(con):
                print(f"{u['usuario']:<20} {u['rol_nombre']:<18} {'activo' if u['activo'] else 'DESACTIVADO'}")
            return 0
        if len(argv) == 2 and argv[0] == "restablecer":
            fila = con.execute("SELECT id FROM usuarios WHERE usuario = ?", (argv[1].strip().lower(),)).fetchone()
            if fila is None:
                print(f"No existe el usuario «{argv[1]}». Usa «listar» para ver los que hay.")
                return 1
            _, clave = seguridad.restablecer_clave(con, fila["id"])
            print(f"Usuario: {argv[1]}   Clave temporal: {clave}   (deberá cambiarla al entrar)")
            return 0
        print(__doc__)
        return 2
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
