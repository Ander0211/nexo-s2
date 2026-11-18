"""
VALIDACIÓN DE LO QUE LLEGA A LA API
===================================
Cuando la pantalla envía datos al servidor (por ejemplo al guardar una oferta), estos
«esquemas» revisan que vengan completos y correctos ANTES de que la lógica los use.
Si algo está mal, FastAPI responde automáticamente con error 422 y un mensaje.

Usa Pydantic, la librería de validación que trae FastAPI.

Esquemas de este archivo:
    OfertaManualIn  agregar una oferta a mano
    SeleccionIn     elegir a mano el proveedor de un producto
    ProductoIn      crear un producto a mano
    ProductoEdit    cambiar un producto (solo los campos que se envíen)
    EmpresaIn       crear un proveedor a mano
    EmpresaEdit     cambiar el nombre de un proveedor
    FilaIn          una fila de las tablas de la administración ({columna: valor})
    EliminarIn      los números de las filas a eliminar juntas
    ImportarIn      qué tablas importar desde la carpeta de Excel y en qué modo
    LoginIn         usuario y clave para entrar
    ClaveIn         cambiar la propia clave
    UsuarioIn       crear un usuario
    UsuarioEdit     cambiar nombre, perfil, proveedor o estado de un usuario
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OfertaManualIn(BaseModel):
    """Datos para agregar una oferta a mano (POST /api/ofertas)."""

    # Código del producto (obligatorio, hasta 40 caracteres).
    cod_producto: str = Field(min_length=1, max_length=40)
    # Se indica UNO de estos dos: un proveedor que ya existe (cod_empresa)
    # o el nombre de uno nuevo (empresa_nueva). Nunca los dos ni ninguno (ver _un_proveedor).
    cod_empresa: str | None = Field(default=None, max_length=20)
    empresa_nueva: str | None = Field(default=None, max_length=120)
    # Precio por unidad: debe ser mayor que 0, menor a 10 mil millones y un número real
    # (allow_inf_nan=False rechaza "infinito" y "NaN").
    valor: float = Field(gt=0, lt=1e10, allow_inf_nan=False)
    # Presentación opcional, por ejemplo "X100".
    presentacion: str | None = Field(default=None, max_length=40)
    # Cuántas unidades puede entregar el proveedor (opcional: vacío = no lo dijo, se supone que le alcanza). 0 = no tiene unidades.
    disponible: float | None = Field(default=None, ge=0, lt=1e10, allow_inf_nan=False)

    @field_validator("cod_producto", "cod_empresa", "empresa_nueva", "presentacion", mode="before")
    @classmethod
    def _limpiar(cls, v):
        """Limpia los textos: quita espacios de más ("  Mi   proveedor " → "Mi proveedor").
        Un texto vacío se convierte en None (= "no se escribió nada")."""
        if isinstance(v, str):
            v = " ".join(v.split())
            return v or None
        return v

    @model_validator(mode="after")
    def _un_proveedor(self):
        """Regla: exactamente UNO entre cod_empresa y empresa_nueva.
        bool(a) == bool(b) es verdad cuando ambos están llenos o ambos vacíos → error."""
        if bool(self.cod_empresa) == bool(self.empresa_nueva):
            raise ValueError("Indica un proveedor existente o escribe el nombre de uno nuevo (solo uno).")
        return self


class SeleccionIn(BaseModel):
    """Datos para elegir a mano un proveedor de un producto (PUT /api/productos/{cod}/seleccion)."""

    cod_empresa: str = Field(min_length=1, max_length=20)


class CantidadIn(BaseModel):
    """La cantidad a comprar que el usuario fija a mano (PUT /api/productos/{cod}/cantidad): unidades enteras, desde 0."""

    cantidad: int = Field(ge=0, le=10_000_000)


def _limpiar_texto(v):
    """Quita espacios de más de un texto; un texto vacío se convierte en None (= «no se escribió nada»)."""
    if isinstance(v, str):
        v = " ".join(v.split())
        return v or None
    return v


class ProductoIn(BaseModel):
    """Datos para crear un producto a mano (POST /api/productos)."""

    cod: str = Field(min_length=1, max_length=40)
    descripcion: str = Field(min_length=1, max_length=300)
    # Los stocks son opcionales: sin stock máximo el producto queda «sin stock definido» (no se compra).
    stock_max: float | None = Field(default=None, ge=0, lt=1e12, allow_inf_nan=False)
    stock_med: float | None = Field(default=None, ge=0, lt=1e12, allow_inf_nan=False)
    stock_min: float | None = Field(default=None, ge=0, lt=1e12, allow_inf_nan=False)
    existencias: float = Field(default=0, ge=0, lt=1e12, allow_inf_nan=False)

    @field_validator("cod", "descripcion", mode="before")
    @classmethod
    def _limpiar(cls, v):
        """Limpia espacios de los textos."""
        return _limpiar_texto(v)

    @model_validator(mode="after")
    def _minimo_no_mayor_que_maximo(self):
        """Regla: el stock mínimo no puede ser mayor que el máximo."""
        if self.stock_max is not None and self.stock_min is not None and self.stock_min > self.stock_max:
            raise ValueError("El stock mínimo no puede ser mayor que el stock máximo.")
        return self


class ProductoEdit(BaseModel):
    """Datos para cambiar un producto (PUT /api/productos/{cod}).

    Todos los campos son opcionales: solo se cambian los que se envían. Un stock enviado como null se quita.
    (El código no se puede cambiar: es la identidad del producto.)
    """

    descripcion: str | None = Field(default=None, max_length=300)
    stock_max: float | None = Field(default=None, ge=0, lt=1e12, allow_inf_nan=False)
    stock_med: float | None = Field(default=None, ge=0, lt=1e12, allow_inf_nan=False)
    stock_min: float | None = Field(default=None, ge=0, lt=1e12, allow_inf_nan=False)
    existencias: float | None = Field(default=None, ge=0, lt=1e12, allow_inf_nan=False)

    @field_validator("descripcion", mode="before")
    @classmethod
    def _limpiar(cls, v):
        """Limpia espacios de la descripción."""
        return _limpiar_texto(v)


class EmpresaIn(BaseModel):
    """Datos para crear un proveedor a mano (POST /api/empresas). Sin código, se le asigna uno automáticamente."""

    nombre: str = Field(min_length=2, max_length=120)
    cod: str | None = Field(default=None, max_length=20)

    @field_validator("nombre", "cod", mode="before")
    @classmethod
    def _limpiar(cls, v):
        """Limpia espacios de los textos."""
        return _limpiar_texto(v)


class EmpresaEdit(BaseModel):
    """Datos para cambiar el nombre de un proveedor (PUT /api/empresas/{cod})."""

    nombre: str = Field(min_length=2, max_length=120)

    @field_validator("nombre", mode="before")
    @classmethod
    def _limpiar(cls, v):
        """Limpia espacios del nombre."""
        return _limpiar_texto(v)


# --------------------------------------------------------------------------- Administración de las tablas
class FilaIn(BaseModel):
    """Una fila de una de las 5 tablas (POST y PUT /api/admin/tablas/{tabla}/filas). Las claves son los encabezados
    del Excel; el servidor valida columna por columna (services/tablas.py → limpiar)."""

    valores: dict[str, str | int | float | None]


class EliminarIn(BaseModel):
    """Números de las filas que se eliminan juntas (POST /api/admin/tablas/{tabla}/filas/eliminar)."""

    ids: list[int] = Field(min_length=1, max_length=20000)


class ImportarIn(BaseModel):
    """Qué importar desde la carpeta data/excel (POST /api/admin/importar)."""

    tablas: list[str] = Field(min_length=1, max_length=5)
    modo: Literal["reemplazar", "agregar"] = "reemplazar"


# --------------------------------------------------------------------------- Seguridad: sesión y usuarios
class LoginIn(BaseModel):
    """Usuario y clave para entrar (POST /api/sesion)."""

    usuario: str = Field(max_length=60)
    clave: str = Field(max_length=200)


class ClaveIn(BaseModel):
    """Cambiar la propia clave (PUT /api/sesion/clave): la actual y la nueva."""

    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


class EmpresaNuevaIn(BaseModel):
    """Un proveedor que NO está en la lista y se agrega al crear o cambiar un usuario proveedor. Teléfono y correo son obligatorios."""

    nombre: str = Field(max_length=120)
    telefono: str | None = Field(default=None, max_length=30)
    correo: str | None = Field(default=None, max_length=120)


class UsuarioIn(BaseModel):
    """Crear un usuario (POST /api/usuarios). La clave la genera el servidor (temporal)."""

    usuario: str = Field(max_length=60)
    nombre: str = Field(max_length=80)
    rol: Literal["admin", "prime", "consulta", "externo"]
    cod_empresa: str | None = Field(default=None, max_length=20)
    correo: str | None = Field(default=None, max_length=120)  # opcional: aquí se envían usuario y clave temporal
    celular: str | None = Field(default=None, max_length=30)  # opcional: para WhatsApp
    empresa_nueva: EmpresaNuevaIn | None = (
        None  # solo para un proveedor (externo) cuyo proveedor no está en la lista: se agrega y se liga
    )


class UsuarioActivoIn(BaseModel):
    """Activar o desactivar un usuario (POST /api/usuarios/{id}/activo)."""

    activo: bool


class UsuarioEdit(BaseModel):
    """Cambiar un usuario (PUT /api/usuarios/{id})."""

    nombre: str = Field(max_length=80)
    rol: Literal["admin", "prime", "consulta", "externo"]
    cod_empresa: str | None = Field(default=None, max_length=20)
    correo: str | None = Field(default=None, max_length=120)
    celular: str | None = Field(default=None, max_length=30)
    activo: bool = True
    empresa_nueva: EmpresaNuevaIn | None = (
        None  # un proveedor que no está en la lista: se agrega y se liga a este usuario
    )
