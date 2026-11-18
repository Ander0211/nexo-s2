"""
RUTAS DE OFERTAS AGREGADAS A MANO
=================================
    POST   /api/ofertas        agrega una oferta (panel «Agregar oferta»)
    DELETE /api/ofertas/{id}   elimina una oferta agregada a mano

Regla importante: solo se pueden borrar las ofertas PROPIAS (agregadas a mano o subidas desde un Excel
en «Cargar datos»). Las del Excel base no se tocan aquí (se actualizan cambiando el Excel y pulsando
«Actualizar Excel»).
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..database import get_db
from ..schemas import OfertaManualIn
from ..services import catalogo, tablero
from ..services import ranking as rk
from ..services.normalizacion import codigo_empresa

router = APIRouter(prefix="/api", tags=["ofertas"])


@router.post("/ofertas", status_code=201)
def agregar_oferta(body: OfertaManualIn, db: sqlite3.Connection = Depends(get_db)):
    """Guarda una oferta manual y responde en qué puesto quedó.

    `body` ya llega validado por schemas.OfertaManualIn (precio > 0, un solo proveedor, etc.).
    """
    # 1) El producto debe existir en el catálogo.
    prod = db.execute("SELECT cod, descripcion FROM productos WHERE cod = ?", (body.cod_producto,)).fetchone()
    if not prod:
        raise HTTPException(404, "Ese producto no existe en el catálogo.")

    # `with db` agrupa todo en una transacción: si algo falla, no queda nada a medias.
    with db:
        # 2) Resolver el proveedor: uno existente, o crear uno nuevo.
        if body.cod_empresa:
            cod_emp = codigo_empresa(body.cod_empresa)
            emp = db.execute("SELECT nombre FROM empresas WHERE cod = ?", (cod_emp,)).fetchone()
            if not emp:
                raise HTTPException(404, "Ese proveedor no existe.")
            nombre_emp, proveedor_nuevo = emp["nombre"], False
        else:
            existente = catalogo.buscar_empresa_por_nombre(db, body.empresa_nueva)
            if existente:  # no duplicar proveedores por escribir el mismo nombre (aunque cambien tildes, mayúsculas, espacios o puntos)
                cod_emp, nombre_emp, proveedor_nuevo = existente["cod"], existente["nombre"], False
            else:
                creada = catalogo.crear_empresa(db, body.empresa_nueva)
                cod_emp, nombre_emp, proveedor_nuevo = creada["cod"], creada["nombre"], True

        # 3) Sin repetidos: si ese proveedor ya tiene una oferta de OTRO origen (Excel base o subida) para este producto,
        #    no se agrega otra. (Una oferta MANUAL del mismo proveedor sí se actualiza, abajo.)
        otra = db.execute(
            "SELECT valor, origen FROM ofertas WHERE cod_producto = ? AND cod_empresa = ? AND origen != 'manual' "
            "ORDER BY valor LIMIT 1",
            (body.cod_producto, cod_emp),
        ).fetchone()
        if otra:
            precio = f"${otra['valor']:,.0f}".replace(",", ".")
            if otra["origen"] == "excel":
                que_hacer = (
                    "Para cambiar su precio, pídele al administrador que la edite en Administración → Portafolio."
                )
            else:
                que_hacer = "Para cambiarla, elimínala primero (la papelera en «Otras ofertas») y agrégala de nuevo."
            raise HTTPException(
                409,
                f"«{nombre_emp}» ya tiene una oferta para este producto: {precio} "
                f"({'del Excel base' if otra['origen'] == 'excel' else 'subida desde un Excel'}). "
                f"No se agregan ofertas repetidas. {que_hacer}",
            )

        # 4) Guardar la oferta. Si ese proveedor ya tenía una oferta MANUAL para este
        #    producto, se actualiza su precio en vez de crear otra repetida.
        previa = db.execute(
            "SELECT id FROM ofertas WHERE cod_producto = ? AND cod_empresa = ? AND origen = 'manual'",
            (body.cod_producto, cod_emp),
        ).fetchone()
        if previa:  # misma oferta manual otra vez: se actualiza el precio
            oferta_id, actualizada = previa["id"], True
            db.execute(
                "UPDATE ofertas SET valor = ?, presentacion = ?, disponible = ?, creado = datetime('now','localtime') WHERE id = ?",
                (body.valor, body.presentacion, body.disponible, oferta_id),
            )
        else:
            actualizada = False
            oferta_id = db.execute(
                "INSERT INTO ofertas (cod_producto, cod_empresa, valor, presentacion, disponible, origen) VALUES (?,?,?,?,?, 'manual')",
                (body.cod_producto, cod_emp, body.valor, body.presentacion, body.disponible),
            ).lastrowid

    # 5) Recalcular el ranking del producto para informar en qué puesto quedó la oferta nueva.
    ranking = rk.construir_ranking(tablero.ofertas_por_producto(db, body.cod_producto).get(body.cod_producto, []))
    puesto = next((o["puesto"] for o in ranking if o["cod_empresa"] == cod_emp), None)
    return {
        "id": oferta_id,
        "actualizada": actualizada,
        "proveedor_nuevo": proveedor_nuevo,
        "cod_empresa": cod_emp,
        "empresa": nombre_emp,
        "producto": dict(prod),
        "puesto": puesto,
        "total_ofertas": len(ranking),
        "es_la_mejor": puesto == 1,
    }


@router.delete("/ofertas/{oferta_id}")
def eliminar_oferta(oferta_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Elimina una oferta propia: agregada a mano o subida desde un Excel (las del Excel base están protegidas)."""
    o = db.execute("SELECT * FROM ofertas WHERE id = ?", (oferta_id,)).fetchone()
    if not o:
        raise HTTPException(404, "Esa oferta no existe.")
    if o["origen"] not in catalogo.ORIGENES_PROPIOS:
        # 409 = conflicto: la petición es válida pero no está permitida sobre este dato.
        raise HTTPException(
            409,
            "Solo se pueden eliminar las ofertas propias (agregadas a mano o subidas desde un Excel); "
            "las del Excel base se actualizan importando.",
        )
    with db:
        db.execute("DELETE FROM ofertas WHERE id = ?", (oferta_id,))
        quedan = db.execute(
            "SELECT 1 FROM ofertas WHERE cod_producto = ? AND cod_empresa = ?", (o["cod_producto"], o["cod_empresa"])
        ).fetchone()
        if not quedan:  # si ese proveedor estaba elegido y ya no tiene oferta, se libera la elección
            db.execute(
                "DELETE FROM seleccion WHERE cod_producto = ? AND cod_empresa = ?",
                (o["cod_producto"], o["cod_empresa"]),
            )
    return {"ok": True, "cod_producto": o["cod_producto"]}
