# SENTINEL PABON — documentación del código

Tablero de copias de seguridad (.bak) de Clinica Cardioneurovascular PABON.
No inventa Resultado ni RTO: el inventario solo lista archivos; el acta sale de ENVIAR.

La interfaz no explica el sistema. Este archivo sí.

## Qué hace

- Lee el Excel de inventario (bloques AÑO / FECHA / ARCHIVO / PESO).
- Muestra tableros, cadencia, semáforos, ficha por sistema.
- Formato de verificación y verificación del día → hoja Verificaciones.
- Vigila `C:\Users\Db Developer\Documents\SENTINEL` (Excel).
- Recorre `\\172.168.100.10\copias` y `\\192.168.200.50\backup_saludips\2026` y agrega .bak nuevos (sin duplicar).
- BACKUP_SERVER: unidad Z: = `\\172.168.10.100\backup_server` (carpetas 2019–2026). Semáforo verde/amarillo/rojo.

## Verificación del día (no por sistema)

Se cuenta cuántos .bak hay en el último día del inventario.

| Cantidad | Resultado |
|---|---|
| 10 | Exitoso |
| 1–9 | Parcial |
| 0 | Fallido |

Observaciones: una línea por archivo  
`nombre.bak | dd/mm/aaaa hh:mm a. m. | n KB`

ENVIAR escribe una fila, sistema `DIA`.

## Archivos

| Ruta | Rol |
|---|---|
| `server.py` | HTTP 8080, APIs, vigilante Excel + carpeta de red, hoja Verificaciones |
| `ingest.py` | Parseo del .xlsx → `js/data.js` y `js/analytics.js` |
| `js/app.js` | Interfaz |
| `js/data.js` | Inventario generado (no editar a mano) |
| `js/analytics.js` | Agregados generados |
| `css/app.css` | Paleta clínica (#015AAA, #013E74, #6ACEF5, #EA0B0B) |
| `index.html` | Shell + splash |
| `config.json` | Rutas e intervalo |
| `assets/inventario-backups.xlsx` | Copia de trabajo |
| `iniciar-SENTINEL.bat` | Arranque en Windows |
| `PASOS.txt` | Instalación en el PC Db Developer |

## server.py

- `WIN_FUENTE`: carpeta del Excel.
- `COPIAS_UNC`: `\\172.168.100.10\copias`. 172.168.10.100 se abre con VNC Viewer; no es fuente de .bak.
- `parse_path` / `ruta_permitida`: Documentos, UNC, home.
- `pick_xlsx`: elige inventario/backup/sentinel o el .xlsx más reciente.
- `listar_bak` + `merge_copias_into`: recorre la red, escribe FECHA/ARCHIVO/PESO. `escribir_celda` descombina MergedCell.
- `ciclo_auto`: cada N s mira mtime del Excel y stamp de copias. Cortes de red (WinError 10053) se reintentan, no tumban el servicio.
- `apply_source`: copia a `assets/inventario-backups.xlsx`, conserva Verificaciones, regenera JS.
- `append_one`: ENVIAR → fila en Verificaciones.

API:

- `GET /api/verificaciones`
- `GET|POST /api/fuente`  body: ruta, copias, intervalo, activo, sync
- `POST /api/fuente/sync`
- `POST /api/verificar`  una fila o lista
- `POST /api/excel-upload`
- `GET /api/excel`

## ingest.py

- `extract_records`: hojas con más .bak (omite Resumen y Verificaciones).
- `name_clock` / `sistema_de`: fecha y prefijo del nombre.
- `build_analytics`: calendario 2026, huecos, gemelas SIFacturacion, corridas AM/PM, disco.

## js/app.js

- `D` / `A`: datos y analítica.
- `ACTIVE`: sistemas cuyo último .bak = último día del libro.
- `resultadoDelDia(n)`: regla de 10 archivos.
- `viewLote`: un formulario para el día.
- `viewForm`: formato institucional; Resultado lo elige el operador.
- `pushExcel`: POST al servidor; si falla, localStorage.

## Arranque (PC Db Developer)

Python en PATH, `py -m pip install openpyxl`, Excel cerrado,  
`dir \\172.168.100.10\copias` visible, luego `iniciar-SENTINEL.bat`  
y http://localhost:8080

## Usuarios y roles (usuarios.py)

Para entrar hay que iniciar sesión (`login.html`). La primera vez, desde el PC donde corre SENTINEL
(http://localhost:8080), se crea la cuenta del **administrador**; desde otros equipos no se puede.

| Rol | Puede | No puede |
|---|---|---|
| Administrador | Todo: cargar inventario, fuente/copias de red, verificar (ENVIAR), gestionar usuarios | — |
| Revisor | Consultar tableros, inventario, análisis, registro de verificaciones, descargar el Excel | Cargar inventario, cambiar la fuente, verificar/ENVIAR, gestionar usuarios |

- El permiso lo exige el **servidor** (403), no solo la interfaz: `/api/excel-upload`, `POST /api/fuente`, `/api/verificar`, `/api/usuarios` → solo administrador.
- Cuentas en `datos/usuarios.json` (clave con PBKDF2-SHA256 + sal). `datos/` no se publica.
- `datos/auditoria.log`: quién ingresó, cargó, cambió la fuente, verificó o gestionó usuarios.
- Sesión: cookie `sentinel_sesion` (HttpOnly), 12 h. 5 claves erradas → 5 min de bloqueo.
- `usuarios.html`: el administrador gestiona usuarios (crear, rol, nueva clave, desactivar, eliminar); todos cambian su clave.
- Sin sesión solo se ven `login.html`, estilos e imágenes; `js/data.js`, APIs y el Excel piden sesión.
- `GET /api/salud` (público) lo usa Nexo S² para saber si SENTINEL está encendido.

Si olvida la clave del único administrador: detenga SENTINEL, borre `datos/usuarios.json` y vuelva a crear el administrador desde este PC.

## Envío de usuario y clave (notificaciones.py), igual que SUMIPABON

- Al **crear** un usuario (nombre, usuario, rol, correo y celular obligatorios) SENTINEL genera una **clave temporal**,
  la muestra una sola vez (con «Copiar clave») y la envía por **correo** y por **WhatsApp**.
- **Nueva clave** hace lo mismo con una clave temporal nueva y cierra las sesiones de esa persona.
- Con clave temporal, al ingresar se pide elegir una clave propia antes de ver cualquier cosa (también lo exige el servidor).
- Si WhatsApp automático no está configurado: botón «Abrir WhatsApp con el mensaje» (wa.me, envío manual).
- Configuración: `sentinel/.env` (ver `.env.ejemplo`, prefijo `SENTINEL_`) y, si no está, la de SUMIPABON
  (`compras_app/.env`, prefijo `COMPRAS_`). El `.env` no se publica en el navegador.
- «Datos» permite corregir nombre, correo y celular. Correo y celular no se repiten entre usuarios.

## Celulares y tabletas (js/movil.js)

- Hasta 980 px de ancho: barra superior con ☰ (menú lateral deslizable), título, botón Nexo S² y ⋮
  (buscar, usuario, Usuarios/Mi clave, Ayuda, Imprimir, Tema, Salir). Se cierra al elegir, tocar fuera o con Esc.
- Toda tabla queda dentro de un recuadro que se desliza de lado; la página nunca se corre. Probado sin desbordes
  en 320, 360, 375, 390, 412 y 768 px en todas las vistas. En Usuarios, la lista se ve como tarjetas.
- Campos con letra de 16 px (el iPhone no hace zoom) y botones de al menos 40–44 px de alto.

## Enlace del correo / WhatsApp

`http://<IP-del-PC>:8080/login.html?ingresar=1&usuario=<usuario>`
- Si el administrador entró como `localhost`, el enlace usa la **IP de este PC en la red** (en el celular de otra
  persona «localhost» no lleva a SENTINEL). Para fijar otra dirección: `SENTINEL_URL_PUBLICA` en `sentinel/.env`.
- `ingresar=1` cierra la sesión que hubiera en ese navegador y muestra el ingreso con el usuario ya escrito.
- Con la clave temporal pide elegir una propia y entra directo a SENTINEL.

## Superusuario (igual que SUMIPABON)

- `SENTINEL_SUPERUSUARIO` / `SENTINEL_SUPERUSUARIO_CLAVE` en `sentinel/.env` (o variables). Si SENTINEL no define
  ninguno, toma el par de SUMIPABON (`COMPRAS_SUPERUSUARIO` / `COMPRAS_SUPERUSUARIO_CLAVE`). Se toman juntos, nunca mezclados.
- En cada arranque (`server.py → preparar_superusuario`) se crea o se repara: administrador, activo y con la clave del .env.
- Protegido: no se edita, desactiva, elimina, ni se le cambia o restablece la clave desde la pantalla (409).
- Con superusuario configurado ya no aparece la pantalla «crear el primer administrador».
- Sin clave en el .env, la cuenta queda como administrador normal (pierde la protección).

