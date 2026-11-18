# Nexo S²

Plataforma integrada de la **Clínica Cardioneurovascular Pabón** para el análisis de compras y el seguimiento de copias de seguridad. Reúne dos sistemas en un solo punto de acceso:

| Sistema | Para qué sirve | Puerto |
|---|---|---|
| **SUMIPABON** (`sistemas/compras_app`) | Análisis de compras y suministros: ofertas de proveedores, mejor precio por producto, cotizaciones, órdenes de compra y «Adicionales» (Proveedor 1, 2 y 3 con su menor valor). | 8000 |
| **SENTINEL PABON** (`sistemas/sentinel`) | Seguimiento de backups: inventario de copias del servidor, días sin respaldo y verificación diaria. Roles Administrador / Revisor y superusuario. | 8080 |
| **Portal Nexo S²** (`nexo.py`, `portal/`) | Pantalla de inicio para elegir el sistema; lo enciende y lleva a él. | 7000 |

## Iniciar

- **Windows:** doble clic en `INICIAR-NEXO.bat`.
- **Linux / macOS:** `./iniciar-nexo.sh`.

Requiere Python 3.12 o superior. La primera vez, SUMIPABON instala sus librerías (necesita internet).

## Configuración (no se sube a GitHub)

- `sistemas/compras_app/.env`: correo, WhatsApp y superusuario de SUMIPABON (ver `.env.ejemplo`).
- `sistemas/sentinel/.env`: lo propio de SENTINEL (ver `.env.ejemplo`). Si no existe, usa el correo, la cuenta de WhatsApp y el superusuario de SUMIPABON. La plantilla de WhatsApp debe ser **diferente** para cada sistema.

Los datos (bases de datos, usuarios de SENTINEL, inventario de backups y Excel de la empresa) están excluidos en `.gitignore`.

Más detalles en `LEEME.txt`, `sistemas/compras_app/README.md` y `sistemas/sentinel/DOCUMENTACION.md`.
