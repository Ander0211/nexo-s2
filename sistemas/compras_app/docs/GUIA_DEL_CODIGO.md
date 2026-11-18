# Guía del código

Esta guía sirve para **entender qué hace cada parte** del proyecto sin ser programador.
Además, cada archivo de código empieza con un comentario que explica su papel, y cada
función lleva una explicación de lo que hace.

## 1. La idea general: cuatro capas

```
  PANTALLA (navegador)          frontend/          lo que ves y tocas
        │  ▲
        ▼  │   peticiones y respuestas (JSON)
  API (rutas)                   app/routers/       recibe la petición y responde
        │
        ▼
  LÓGICA DE NEGOCIO             app/services/      calcula, importa, exporta
        │
        ▼
  BASE DE DATOS                 data/compras.db    guarda dos capas de tablas (ver abajo)
        ▲
        ├── los 5 Excel NO vienen con el proyecto: se suben a mano desde «Actualizar Excel» (varios a la vez; frontend/js/admin.js → abrirImportar) y luego SOLO cuando tú lo pides.
        │   (Si copias los archivos a data/excel/, la 1.ª vez se cargan solos.)
        ├── lo que editas en «Administración» (ver, editar, agregar, eliminar filas)
        └── y con lo que cargues tú: subiendo un Excel o a mano (botón «Cargar datos»)
```

**Las dos capas de tablas** (esto es lo más importante de entender del módulo de administración):

```
  CAPA 1 · LAS 5 TABLAS DE LOS EXCEL          CAPA 2 · TABLAS DE TRABAJO
  x_stock  x_existencias  x_empresas          productos · empresas · ofertas · avisos
  x_ficha  x_portafolio                       (las lee el tablero de compras)
  = copia fiel de cada Excel, con sus           ▲
    mismos encabezados. Es lo que ves           │  importador.recalcular() las calcula
    y editas en «Administración».  ─────────────┘  desde la capa 1 tras CADA cambio
```

Lo que creas en «Cargar datos» / «Agregar oferta» (`origen` `manual` o `subido`) vive solo en la capa 2 y el recálculo no lo toca.

**Regla de oro:** cada capa solo habla con la de al lado. La pantalla nunca toca la base de
datos; las rutas casi no calculan (le piden los cálculos a `services/`).

## 2. Mapa de archivos

### Backend (`app/`)

| Archivo | Qué hace |
|---|---|
| `main.py` | **Arma la aplicación**: conecta las rutas, instala el guardián (`autorizacion`) y las cabeceras de seguridad, crea el usuario `admin` la primera vez, publica la única página (`/`) y sus CSS/JS **sin copias viejas en el navegador** (`EstaticosSinCache`), convierte los errores de negocio en mensajes claros y, la primera vez (y solo esa), carga los Excel en las 5 tablas. |
| `config.py` | Rutas y valores ajustables (nombres de los Excel, cuántas ofertas por paso...). |
| `database.py` | Define las tablas de SQLite (las de trabajo y, desde `tablas.esquema_sql()`, las 5 de los Excel; más `cambios`), abre las conexiones y **actualiza solo las bases viejas** (`_migrar`). Cada producto, proveedor y oferta guarda su `origen` (`excel`, `manual` o `subido`). |
| `schemas.py` | Revisa que lo que envía la pantalla esté completo y correcto (precio > 0, stock mínimo ≤ máximo, nombre de proveedor...). |
| `routers/productos.py` | Rutas de productos: lista, **podio de ofertas**, elegir proveedor, buscador y **crear / cambiar / eliminar un producto a mano**. |
| `routers/ofertas.py` | Rutas para **agregar y eliminar ofertas propias** (a mano o subidas). |
| `routers/empresas.py` | Lista de proveedores y **crear / renombrar / eliminar un proveedor a mano**. |
| `routers/cargas.py` | ⭐ **Subir un Excel** (`POST /api/cargas/{tipo}`) y **descargar la plantilla** (`GET /api/plantillas/{tipo}`). |
| `routers/admin.py` | ⭐ **Administración**: ver/agregar/editar/eliminar filas de las 5 tablas, descargar cada una como Excel, importar (de la carpeta o subiendo un archivo), historial y deshacer. |
| `routers/sistema.py` | Resumen (KPIs), avisos (con sus botones «Ir a corregir»), importar todo, **exportar VALORES** y **exportar productos a comprar**. |
| `routers/sesion.py` | ⭐ **Ingresar, salir, quién soy y cambiar mi clave** (`/api/sesion`). Es la única ruta que se puede usar sin haber ingresado (solo el ingreso). |
| `routers/usuarios.py` | (solo administrador) Crear, cambiar perfil, desactivar, eliminar usuarios y **restablecer su clave**. |
| `routers/proveedor.py` | Lo que ve el **proveedor externo**: los productos por comprar **sin precios** y su Excel de cotización. |
| `autorizacion.py` | ⭐ **El guardián**: se ejecuta antes de cada ruta. Exige sesión (401), revisa el perfil contra la tabla de permisos (403), comprueba el origen de las peticiones que cambian datos (anti-CSRF) y, si la persona debe cambiar su clave, le cierra todo lo demás. |
| `main.py → asegurar_superusuario` | En cada arranque lee `COMPRAS_SUPERUSUARIO` y `COMPRAS_SUPERUSUARIO_CLAVE` (del `.env`) y llama a `seguridad.asegurar_superusuario`; si están mal, avisa en la terminal y sigue (nunca imprime la clave). |
| `usuarios_cli.py` | Herramienta de terminal: **olvidos de clave** (`listar`, `restablecer <usuario>`) **`probar-correo <destino>`**, que envía un correo de prueba y explica qué falla, y **`crear-admin <usuario>`** (alias `crear-superusuario`), que crea un administrador con la clave que la persona escriba (no se ve al teclearla). |
| `services/libros_excel.py` | ⭐ **Arma los Excel con el formato oficial**: la **ficha FR-GDS-07** del proveedor (`ficha_cotizacion_xlsx`), la **orden de compra** (`oc_xlsx`: VALORES, DINAMICA y ORDENES) y el **libro de alternativas** 2.º a 4.º con las tres hojas de la OC por puesto (`alternativas_xlsx`). |
| `plantillas/` | Los formatos oficiales livianos: `ficha_base.xlsx` y `oc_base.xlsx`, en blanco y sin datos de ningún Excel (la marca de cada producto la escribe el proveedor). |
| `../herramientas/preparar_animacion.py` | Convierte la página de animación entregada (con título, botón, subtítulos de ejemplo y un script de Cloudflare) en la escena liviana `viaje/escena.txt` + `viaje/doctor.webp`: quita lo que no es de la escena, poda el CSS que nada usa y saca la imagen del texto. Se corre a mano cuando cambia la animación. |
| `../herramientas/preparar_plantillas.py` | Genera esas plantillas a partir de los archivos originales (la ficha y el `OC.xlsm`). Se corre una sola vez, a mano; no es parte de la aplicación. |
| `frontend/img/` | Los logos: `logo-pabon.png` y `logo-centro.png` (en las esquinas del inicio) y `certificaciones.png` (en el pie del inicio). |
| `services/pendientes.py` | ⭐ **Las fichas que suben los proveedores**: valida y guarda cada ficha como lote PENDIENTE (`guardar_subida`), la muestra frente a la mejor oferta (`detalle`) y la **aprueba** (`aprobar`: pasa por el mismo camino de «Cargar datos → Cotizaciones») o la **rechaza**. Tablas `lotes_oferta` y `ofertas_lote`. |
| `routers/pendientes.py` | Las rutas del administrador para revisar esas fichas. Las del proveedor (subir y ver sus envíos) están en `routers/proveedor.py`. |
| `frontend/js/listas.js` | El componente de **lista con buscador y descarga** (búsqueda en el servidor, «Ver más», botón de Excel que baja lo buscado). Lo usan las ventanas «Sin oferta» y «Nuevos». |
| `frontend/js/alternativas.js` | La ventana «Alternativas 2.º a 4.º» del administrador y Prime: explica y baja el libro de 9 hojas (sin pestañas: «Sin oferta» y «Nuevos» van solo en `proveedor.js`). |
| `frontend/js/pendientes.js` | La ventana «Ofertas de proveedores»: lista, detalle, aprobar y rechazar. |
| `services/etiquetas.py` | Decide qué productos y empresas son **«Nuevos»**: la tabla `vistos` guarda cuándo vio el sistema cada código por primera vez (`sincronizar`) y `nuevos` dice cuáles llevan la etiqueta (7 días, `config.DIAS_NUEVO`). |
| `services/contacto.py` | Valida y da formato único al **teléfono** y al **correo** de las empresas (`normalizar_telefono`, `normalizar_correo`). |
| `services/fichas.py` | ⭐ **La ficha de una empresa**: contacto, cuántas ofertas tiene, en cuántas es la mejor, a cuántos productos se le compraría y cuánta inversión suma, y la lista de sus ofertas con el puesto de cada una. |
| `services/notificaciones.py` | ⭐ **Envía el usuario y la clave temporal** (el correo lleva un botón «Entrar a SUMIPABON» —`mensaje_html`— para no mostrar la IP) por **correo** (SMTP) y **WhatsApp** (API oficial de Meta) cuando se crea un usuario o se restablece su clave. Cada canal informa su resultado (`enviado`, `no_configurado`, `sin_dato`, `error`) y, si WhatsApp no se puede, arma un enlace `wa.me` para enviarlo a mano. La clave nunca se escribe en mensajes de error. Se configura con el archivo **`.env`** de la raíz (plantilla: `.env.ejemplo`; se relee solo cuando cambia) o con variables `COMPRAS_SMTP_*` y `COMPRAS_WHATSAPP_*`. |
| `services/seguridad.py` | ⭐ **Toda la seguridad sin web**: perfiles (`ROLES`), claves con scrypt y sus reglas, usuarios, sesiones de 12 h, bloqueo tras 5 fallos y la **tabla de permisos `POLITICA`** (qué perfil puede qué ruta; lo que no está declarado queda solo para el administrador). |
| `services/ranking.py` | ⭐ **El cerebro**: cantidad a comprar y orden de las ofertas (mejor, 2.ª, 3.ª...). |
| `services/tablero.py` | Junta todo por producto: cantidad, mejor oferta, elegida, total, ahorro; filtra y ordena. |
| `services/tablas.py` | ⭐ **Las 5 tablas de los Excel**: sus encabezados exactos (`TABLAS`), validar lo que escribe el usuario, buscar/ordenar/paginar, importar un Excel (reemplazar o agregar), exportar a Excel y explicar el impacto de eliminar. No recalcula ni guarda historial. |
| `services/historial.py` | El historial de cambios (`cambios`) y **deshacer** (agregar, editar, eliminar, eliminar varias, importar). |
| `services/admin.py` | Une las tres piezas: cada acción = escribir en la tabla + anotar en el historial + **recalcular**, todo en una transacción. También arma la lista de avisos con sus destinos. |
| `services/importador.py` | Dos trabajos: **importar** un Excel a una de las 5 tablas (`cargar_tablas`) y **recalcular** productos, proveedores, ofertas y avisos desde ellas (`recalcular`). **No borra lo tuyo** (a mano o subido). Cada aviso lleva su `clave` estable y sus `destinos`. |
| `services/cargas.py` | ⭐ **La carga de Excel desde la pantalla**: lee el archivo, valida fila por fila, cuenta qué pasaría (**revisar**) y lo guarda (**cargar**). |
| `services/catalogo.py` | Las **reglas** de crear, cambiar y eliminar productos y proveedores. Las usan los formularios manuales **y** la carga de Excel. |
| `services/plantillas.py` | Genera los Excel en blanco («Descargar plantilla») con sus instrucciones. |
| `services/exportador.py` | Arma los datos de la OC (`filas_valores`), el `PRODUCTOS_A_COMPRAR.xlsx` (administrador y Prime, por la API) y el Excel de cotización del proveedor (precios vacíos en amarillo). |
| `services/normalizacion.py` | Limpieza: códigos, textos, números en distintos formatos, tildes y encabezados de columna. |

### Frontend (`frontend/`)

| Archivo | Qué hace |
|---|---|
| `index.html` | ⭐ **La única página HTML**: el esqueleto de la barra azul, el **menú lateral**, las tres pantallas (**bienvenida**, **tablero de compras** y **administración**) **y** de los paneles emergentes («Agregar oferta», «Cargar datos», «Ofertas del producto», y los de la administración: agregar fila, importar, historial y confirmar; todos son `<dialog>`). No hay más páginas ni ventanas aparte. |
| `js/app.js` | ⭐ **Director de la aplicación**: primero pregunta quién eres (`arrancar`) y muestra el ingreso o la pantalla que te toca según tu perfil (`aplicarPerfil`, `PANTALLAS_POR_PERFIL`); también el **menú lateral y las pantallas** (`armarMenu`, `mostrarPantalla`), números, filtros, lista, paginación, avisos, los **botones «Mejor oferta» / «Otras ofertas»** de cada fila y la ventana que abren (`abrirOfertas`). |
| `js/admin.js` | ⭐ **La pantalla «Administración»**: pestañas, tabla con edición en la misma fila, agregar, eliminar (con aviso del impacto), selección de filas, y las ventanas de **importar** e **historial**. También `irA`: llegar desde un aviso con el filtro puesto. |
| `js/podio.js` | ⭐ **El contenido de la ventana de ofertas** con sus 3 pestañas (**Mejor oferta · Otras ofertas · Comparar todas**) y el botón «Ver siguientes ofertas». |
| `js/agregar.js` | La lógica del panel «Agregar oferta»: buscar, elegir, **vista previa** y guardar. |
| `js/cargar.js` | ⭐ La lógica del panel «Cargar datos»: **subir Excel** (arrastrar, revisar, cargar) y los **formularios** de producto y proveedor. |
| `js/sesion.js` | Guarda **quién ingresó y con qué perfil** (`rol`, `es`, `puedeEditar`). Lo consultan las demás pantallas para mostrar u ocultar cosas. |
| `js/usuarios.js` | La pantalla **«Usuarios»** (solo administrador): tabla, crear, cambiar perfil, desactivar, eliminar y restablecer clave (muestra la temporal una sola vez). |
| `js/proveedor.js` | La pantalla **«Productos que necesitamos»** del proveedor externo: lista sin precios y botón de descarga. |
| `js/api.js` | Toda la comunicación con el servidor (una función por ruta). Si el servidor responde 401, avisa con el evento `sesion-vencida` y se vuelve al ingreso. |
| `js/graficos.js` | El medidor de stock y el gráfico «Dónde comprar». |
| `js/util.js` | Herramientas: formato de pesos y números, leer un número escrito por una persona, iconos, avisos flotantes. |
| `css/base.css` | ⭐ **Identidad visual y estructura**: colores y tipografías (variables del sitio de la Clínica Pabón), barra azul, **menú lateral**, bienvenida, botones, tarjetas de números y pie. |
| `fonts/` | Montserrat, Mulish y Poppins en formato `woff2` (con su `LEEME.txt` y licencia): se ven igual sin internet. |
| `img/` | Logos de la Clínica: `logo-blanco.png` (barra de arriba y pie), `corazon.png` (bienvenida) e `icono-192.png` (icono de la pestaña). |
| `css/componentes.css` | Lista de productos, podio, gráfico lateral, paginación. |
| `css/agregar.css` | Estilos de los **paneles emergentes** (tarjeta centrada, cabecera/cuerpo/pie), del formulario y de la vista previa de «Agregar oferta». |
| `css/cargar.css` | Estilos del panel «Cargar datos»: zona de arrastrar, resultado de la revisión, formularios. |
| `js/empresa.js` | ⭐ **El nombre del proveedor como botón** (`nombreEmpresa`) y la **ventana con su ficha** (`abrirEmpresa`): contacto, cifras y sus ofertas con buscador. |
| `js/viaje.js` | ⭐ **La ventana de espera «El viaje a la clínica»** (`conViaje`): mientras corre una petición, un doctor camina hasta la clínica; avanza al ritmo de la petición real y, al llegar, se cierra y deja ver el resultado. |
| `viaje/escena.txt` · `viaje/doctor.webp` | La **escena** de esa animación (SVG y estilos, generados con `herramientas/preparar_animacion.py` a partir de la página de animación original) y el dibujo del doctor. No es una página: se pide con `fetch` y se mete en un *Shadow DOM* para que sus estilos no se mezclen con los de la aplicación. |
| `css/extras.css` | Estilos de lo último: botón «Actualizar todo», **cantidad editable** (escritorio y celular), nombre de empresa como botón, **ficha de la empresa**, columna de solo lectura en Administración, ventana de espera y la barra superior en celular. |
| `css/seguridad.css` | Pantalla de ingreso, caja de usuario en la barra, pantalla de Usuarios, pantalla del proveedor y sus diálogos. |
| `css/admin.css` | Estilos de la pantalla Administración (tabla, edición en línea, selección) y de sus ventanas; también los botones «Ir a corregir» del panel de avisos. |

### Otros

| Archivo | Qué hace |
|---|---|
| `run.py` | ⭐ **Arranca todo sin errores**: si faltan librerías crea `.venv` e instala; si el puerto 8000 está bloqueado elige otro; abre el navegador. |
| `iniciar.bat` / `iniciar.sh` | Para el doble clic: solo llaman a `run.py`. |
| `tests/` | Pruebas automáticas (incluye `test_repetidos_y_contacto.py` y `test_cantidades_y_fichas.py`, que cubren los datos repetidos, el contacto de las empresas, la cantidad editable y la ficha; `test_seguridad.py`, que prueba cada perfil contra cada ruta, y `test_notificaciones.py`, que prueba el correo, el celular y los envíos —siempre simulados—): comprueban que todo sigue funcionando después de cada cambio. |
| `.vscode/` | Configuración de VS Code (depurar con F5, formato al guardar, pruebas). |
| `.github/workflows/pruebas.yml` | Corre las pruebas automáticamente en GitHub. |

## 3. Qué pasa cuando… (recorridos paso a paso)

### …abres la aplicación
0. `run.py → main` comprueba que estén las librerías: si faltan, `_preparar_entorno` crea `.venv`, instala `requirements.txt` y se vuelve a ejecutar con ese entorno.
   Luego `elegir_puerto` prueba el 8000 y, si Windows lo bloquea u otro programa lo usa, toma uno libre.
1. `run.py → _servir` enciende el servidor (uvicorn) con `app/main.py` y abre el navegador en la dirección correcta.
2. `main.py → ciclo_de_vida` crea las tablas (`database.iniciar_db`) y, si la base está vacía,
   llama a `importador.importar` para leer los Excel.
3. El navegador pide `/` → recibe `index.html` → carga `js/app.js`.
4. `app.js → iniciar` pide dos cosas al mismo tiempo: `/api/resumen` (números grandes y gráfico) y
   `/api/productos` (la primera página de la lista).
5. `app.js` dibuja los números (`pintarKPIs`), los filtros (`pintarChips`), el gráfico
   (`pintarProveedores`) y las filas (`renderFila`).

### …pulsas «Mejor oferta» u «Otras ofertas» en una fila
1. Cada fila tiene una columna **«Ofertas»** con dos botones (los dibuja `app.js → celdaAcciones`).
   Si el producto no tiene ofertas, en su lugar hay un solo botón «Agregar oferta»; si tiene una sola, «Otras ofertas» queda apagado.
2. El botón llama a `app.js → abrirOfertas(producto, 'mejor' | 'otras')`: pone el título y el producto en la cabecera del
   `<dialog id="dlg-ofertas">` de `index.html`, lo abre (`showModal`) y monta dentro el panel de `podio.js`. **La fila no cambia** (no hay flecha ni zona que se despliegue).
3. `podio.js → montarPodio → cargar` pide `/api/productos/{cod}/ofertas?desde=0&limite=3`.
   En el servidor, `routers/productos.py → ofertas_de_producto` lee las ofertas y `ranking.construir_ranking` las ordena de la más barata a la más cara.
4. `podio.js → pintar` dibuja las **pestañas** y el cuerpo de la elegida:
   - **Mejor oferta** (`cuerpoMejor`): la tarjeta de la 1.ª y «Por qué es la mejor» (diferencia con la 2.ª y ahorro en la compra).
   - **Otras ofertas** (`cuerpoOtras`): la 2.ª y la 3.ª; con «Ver siguientes» aparecen la 4.ª, 5.ª... (`cuerpoTodas` es la vista con las tres lado a lado).
5. La ventana se cierra con la ✕, con «Cerrar» o con Esc (al cerrar se vacía, para que no quede nada viejo). Cambiar de pestaña dentro de
   ella (`cambiarPestana`) no vuelve a pedir datos y cambia el título de la ventana (`alPestana → titular`).
6. Si dentro de la ventana eliges un proveedor o eliminas una oferta, `alCambiar` refresca la lista de atrás **y** llama a
   `panel.recargar()`, que vuelve a pedir las ofertas de esa ventana conservando cuántas se veían.

### …quieres ver todas las ofertas lado a lado («Comparar todas»)
Abre cualquiera de las dos ventanas y pulsa la pestaña **«Comparar todas»**: las tres mejores ofertas lado a lado (🥇🥈🥉) y, debajo, las siguientes.

### …pulsas «Ver siguientes ofertas»
1. `podio.js → masOfertas` pide `/api/productos/{cod}/ofertas?desde=N&limite=3` (las que siguen).
2. Las agrega a las que ya se veían y vuelve a dibujar: las nuevas salen como filas compactas (4.ª, 5.ª, 6.ª…).
3. Cuando ya se ven todas, el botón se convierte en «Mostrar solo las 3 mejores» (o «solo la 2.ª y la 3.ª» en la pestaña «Otras ofertas»).

### …agregas una oferta a mano (el panel «Agregar oferta»)
1. El botón «Agregar oferta» de la barra (o el de una fila) llama a `app.js → abrirAgregar(cod)`, que llama a `agregar.js → abrir`: se abre el `<dialog id="dlg-agregar">` **encima de la misma página**
   (con un `cod`, ese producto ya viene elegido). No es una ventana aparte, así que el navegador no lo puede bloquear.
2. `agregar.js` carga el producto y los proveedores. Con cada cambio, `calcularPrevia` simula el
   ranking y `pintarPrevia` muestra «¡Sería la mejor oferta!» o «Quedaría en el puesto N».
3. Al guardar, `agregar.js → guardar` envía `POST /api/ofertas`.
4. `routers/ofertas.py → agregar_oferta` valida, crea el proveedor si es nuevo, guarda la oferta y
   responde en qué puesto quedó.
5. `agregar.js` llama a `alGuardar`, la función que le entregó `app.js` (no hace falta mandar mensajes entre ventanas). `app.js → alGuardarOferta`
   muestra el aviso verde y llama a `refrescarTodo`: todo se recalcula solo.
   «Guardar y cerrar» cierra el panel; «Guardar y agregar otra» lo deja abierto con un banner verde. Esc también lo cierra.
   Si «Agregar oferta» se abrió desde la ventana de ofertas de un producto, queda **encima** de ella; al guardar, esa ventana de abajo se actualiza sola
   (`ofertasAbiertas.panel.recargar()`) y el aviso verde se muestra dentro de ella (`util.js → toast / avisosAlFondo`).

### …eliges otro proveedor para un producto
1. Botón «Elegir esta» → `podio.js → elegir` → `PUT /api/productos/{cod}/seleccion`.
2. `routers/productos.py → elegir_proveedor` lo guarda en la tabla `seleccion` (si eliges la mejor, borra la elección).
3. `tablero.construir_tablero` usa `ranking.elegir`: la oferta elegida manda para el **total** y para el **VALORES** exportado;
   la «mejor» sigue siendo la más barata.

### …pulsas «Actualizar Excel»
1. `app.js` abre la ventana de importar: `admin.abrirImportar()` → `<dialog id="dlg-importar">`. **No importa nada todavía.**
2. Eliges las tablas y el modo. **«Agregar y actualizar»** suma lo nuevo y actualiza lo que ya existe por código; **«Reemplazar»** deja la tabla igual al Excel (pide confirmación).
3. `api.adminImportar` → `POST /api/admin/importar` → `services/admin.py → importar_carpeta` → `importador.importar_tablas`.
4. Primero **lee todos los archivos** (si falta uno o una columna, avisa y no toca nada). Luego, por cada tabla, guarda una **copia completa en el historial** y aplica el modo (`tablas.aplicar_excel`).
5. Al final `importador.recalcular` calcula de nuevo productos, proveedores, ofertas y avisos, y confirma **todo en una sola transacción**. Lo tuyo (`manual`/`subido`) no se toca.

### …abres «Administración» y editas una fila
1. `app.js → mostrarLaPedida` ve la dirección `#admin/stock` y llama a `admin.mostrar('stock')`.
2. `admin.js` pide `GET /api/admin/tablas` (encabezados y conteos) y `GET /api/admin/tablas/stock/filas` (una página; búsqueda y orden los hace SQLite en `tablas.listar`).
3. Doble clic en una fila → se vuelve cajas de texto. **Enter** → `PUT /api/admin/tablas/stock/filas/{id}` → `services/admin.py → editar`.
4. `editar` valida (`tablas.limpiar`: números, obligatorias, largo), guarda **solo lo que cambió**, anota en el historial y llama a `importador.recalcular`.
5. La pantalla recarga la página de filas, los conteos de las pestañas y, con `alCambiar()`, el tablero y el contador de avisos.
   Si algo no es válido, el servidor responde 422 con el mensaje y la fila sigue en edición.

### …pulsas «Ir a corregir» en un aviso
1. `recalcular` guardó cada aviso con una **`clave`** estable y sus **`destinos`** (JSON): a qué tabla ir y a qué filas (sus números de fila), o valores para «Agregar», o un filtro del tablero.
2. `GET /api/avisos` (`services/admin.py → avisos`) manda cada destino con la **cantidad** de filas, no la lista (puede tener miles).
3. El botón llama `app.js → irAlAviso`: si el destino es del tablero, pone el filtro (`cambiarFiltro`); si es una tabla, `admin.irA` deja un «pedido pendiente» y cambia la dirección a `#admin/empresas`.
4. `admin.mostrar` aplica el pedido: pide `…/filas?aviso=empresas_sin_nombre&destino=0` (el servidor busca esos números de fila en `avisos`) o abre el formulario de agregar con los valores puestos.
5. Al corregir, los avisos se recalculan. Como la `clave` no cambia, el filtro sigue valiendo hasta que el problema desaparece: entonces el servidor responde 404 y la pantalla dice «¡Listo!» y muestra todas las filas.

### …eliminas filas en «Administración»
1. Con una fila, `GET …/filas/{id}/impacto` (`tablas.impacto`) explica el efecto («este proveedor tiene 2 ofertas…»); la ventana de confirmar lo muestra.
2. Eliminar **siempre se permite**. `POST …/filas/eliminar` guarda en el historial (una fila = un cambio; varias = un solo cambio con copia de todas) y recalcula.
3. Lo que queda huérfano sale en los avisos: proveedor sin registro (`empresas_inferidas`), producto sin stock (`ofertas_sin_stock`), producto sin oferta (`sin_oferta`) o **elección de proveedor que ya no ofrece el producto** (`eleccion_vieja`; el tablero usa entonces la mejor oferta).

### …pulsas «Deshacer» en el historial
`POST /api/admin/historial/{id}/deshacer` → `historial.deshacer`: **agregar** borra la fila; **editar** devuelve los valores anteriores; **eliminar** devuelve la fila con su mismo número (409 si ese número ya lo ocupa otra); **importar** / **eliminar varias** restauran la copia guardada (pide confirmación). Luego se recalcula.

### …subes un Excel en «Cargar datos»
1. El botón **«Cargar datos»** llama a `cargar.js → abrir`, que abre el `<dialog id="dlg-cargar">` de `index.html` encima de la pantalla (sin ventanas emergentes).
2. `cargar.js → abrir` pide los proveedores al día y `construir` arma **tres pestañas** (Productos · Proveedores · Cotizaciones). Cada una tiene el bloque **A** (subir Excel: `subidor`) y el bloque **B** (a mano).
3. Eliges o **arrastras** un archivo (`.xlsx`, `.xlsm` o `.csv`). `subidor → elegirArchivo → revisar` lo envía con `api.subirArchivo(tipo, archivo, {aplicar: false})`
   → `POST /api/cargas/{tipo}?aplicar=false`. El archivo viaja tal cual como cuerpo de la petición.
4. `routers/cargas.py → subir_archivo` lee los bytes y llama a `services/cargas.py → procesar`.
5. `cargas.leer_archivo` abre el archivo con pandas, reconoce los **encabezados** aunque cambien las tildes, mayúsculas o espacios (`COLUMNAS`) y anota el número de fila de Excel.
6. `procesar_productos`, `procesar_proveedores` o `procesar_cotizaciones` validan **fila por fila** y cuentan cuántas son nuevas, se actualizan, quedan sin cambios o tienen error.
   **En este paso NO se escribe nada** en la base de datos.
7. La pantalla muestra los números, las notas y la tabla de errores (fila + qué pasó). Las filas con error no se cargan; las demás sí.
8. Pulsas **«Cargar N filas»** → el mismo camino con `aplicar=true`: ahora sí se guarda, en **una sola transacción**, con origen `subido`.
   (Productos y proveedores pasan por `services/catalogo.py`, así que valen las mismas reglas que a mano.)
9. `cargar.js → cargar` llama a `avisarPrincipal`, que ejecuta `alCambiar` (la función que le entregó `app.js`). `app.js → alCargarDatos` llama a `refrescarTodo`:
   la pantalla de fondo se recalcula sola mientras el panel sigue abierto mostrando su resultado.

**Reglas de las cotizaciones subidas** (`cargas.procesar_cotizaciones`):
- El proveedor sale de la columna `COD_EMPRESA` o `EMPRESA` del archivo o, si no la trae, del proveedor elegido en pantalla (uno existente o uno nuevo que se crea al cargar).
- Una fila **sin precio (o con 0)** se omite en silencio: es lo normal cuando el proveedor devuelve la ficha con huecos.
- El producto y el proveedor deben existir antes; si no, la fila da error y dice dónde crearlos.
- Una oferta subida **no reemplaza** la del portafolio: el ranking siempre usa el **menor precio de cada proveedor**. Si tu archivo trae un precio más alto que el que ya tenía ese proveedor, la revisión te avisa («no cambiarán el ranking»).

### …agregas un producto o proveedor a mano
1. En «Cargar datos», pestaña **Productos**, bloque B. Al escribir un código, `cargar.js → formProducto → buscar` pide `GET /api/productos/{cod}`:
   si **ya existe** rellena el formulario y pasa al modo «editar» (botón «Guardar cambios»); si no (404), el modo es «crear».
2. **«Crear producto»** → `POST /api/productos`; **«Guardar cambios»** → `PUT /api/productos/{cod}` (solo cambia los campos enviados).
   Los dos pasan por `routers/productos.py` → `services/catalogo.py → crear_producto / actualizar_producto`, donde están las reglas.
3. Si una regla se rompe (código repetido, stock mínimo mayor que el máximo...), `catalogo.py` lanza un `CatalogoError` y `main.py → error_de_catalogo`
   lo convierte en un mensaje claro (código 409 = ya existe, 404 = no existe, 422 = dato inválido) que aparece en rojo en el formulario.
4. **Eliminar** solo aparece en productos tuyos (`manual` o `subido`). Los del Excel base se pueden **cambiar** (y el cambio se conserva al actualizar el Excel) pero **no eliminar**.
5. Los **proveedores** funcionan igual con `formProveedor` y `/api/empresas`. Solo se elimina un proveedor tuyo **sin ofertas**.
6. Una **cotización** a mano se agrega en el panel «Agregar oferta» (el botón de la pestaña Cotizaciones cierra «Cargar datos» y lo abre).

### …un dato es del Excel, «manual» o «subido»
Cada producto, proveedor y oferta recuerda de dónde salió (columna `origen`). Eso decide qué pasa con él:

| Origen | Cómo entró | Etiqueta en la oferta | ¿Se puede eliminar? | ¿Sobrevive a «Actualizar Excel»? |
|---|---|---|---|---|
| `excel` | Calculado desde las 5 tablas de los Excel (Administración) | «Portafolio» | Se edita/elimina en la tabla de origen (Administración) | Se recalcula desde las tablas; solo cambia si tú reemplazas la tabla |
| `manual` | Formulario o panel «Agregar oferta» | «Agregada a mano» | Sí | **Sí** |
| `subido` | Excel subido en «Cargar datos» | «Subida de Excel» | Sí | **Sí** |

Si **cambias** con «Cargar datos» un producto o proveedor que venía de las tablas, pasa a ser tuyo (el recálculo no te pisa el cambio).
Si **eliminas** uno tuyo que también existe en las tablas de los Excel, volverá a verse el de la tabla.

### …editas la cantidad a comprar de un producto
1. En la fila, `app.js → celdaCantidad` dibuja una **caja de texto** (no «number»: así siempre se ven los dígitos). Solo acepta números; Enter o el ✓ llaman a `guardarCantidad`, que **pregunta antes de guardar** (`confirmarCantidad`: «¿Está seguro de la cantidad a comprar?», con lo recomendado y el aviso si se compra menos). «Revisar» no guarda nada.
2. `PUT /api/productos/{cod}/cantidad` (administrador y Prime) guarda el número en la tabla `cantidades`. **No** toca `productos` ni las 5 tablas, ni el stock máximo ni las existencias (la barra «3 en stock · máx 15» no cambia): por eso lo editado sobrevive a recalcular y a «Actualizar Excel». La respuesta trae la fila `item` ya recalculada.
3. `tablero.construir_tablero` usa esa cantidad en vez de la calculada para el total, el ahorro, los indicadores y los Excel exportados. La fila queda marcada «editada · calculada N»; si la cantidad es menor que la calculada (`menos_de_lo_recomendado`) también dice «Menos de lo recomendado», y si no hay nada que comprar porque las existencias están en el máximo o por encima (`stock_suficiente`) dice «Stock suficiente».
4. `app.js → actualizarFila` cambia **solo esa fila** (y los números de arriba): la lista **no se reordena ni se vuelve a filtrar**, así lo editado no salta de lugar ni desaparece. Si la fila ya no cumple el filtro activo (`perteneceAlFiltro`, la misma regla que `tablero._cumple`), se atenúa con un aviso hasta que se pulse «Actualizar todo».
5. El botón «editada · calculada N» llama a `DELETE …/cantidad` y vuelve a la calculada. Si el producto es propio y se elimina, su cantidad se va con él.

### …el proveedor descarga la ficha y la devuelve
1. `GET /api/proveedor/excel` → `exportador.cotizacion_xlsx` junta los productos por comprar (código y descripción) y llama a `libros_excel.ficha_cotizacion_xlsx`, que abre `ficha_base.xlsx`, escribe una fila por producto copiando el formato y el bloqueo de celdas de la fila modelo, vuelve a poner la tabla de control de cambios debajo y llena la fecha y los datos del proveedor.
2. El código del proveedor se guarda en la hoja `SUMIPABON`, que Excel no deja mostrar. La cantidad solicitada va vacía.
3. El proveedor escribe precio, IVA y empaque (las únicas celdas desbloqueadas) y devuelve el archivo.
4. En «Cargar datos → Cotizaciones», `cargas._leer_ficha` reconoce la ficha (encabezado en la fila 11), lee `PRECIO` (sin IVA) y la unidad de empaque, toma el proveedor de la hoja oculta y entrega las columnas de siempre; desde ahí sigue el camino normal de las cotizaciones. Para cualquier otro Excel, no cambia nada.

### …descargas la orden de compra o las alternativas
1. `GET /api/exportar/oc` usa `exportador.filas_valores` (el proveedor elegido de cada producto por comprar, con la cantidad vigente) y `libros_excel.oc_xlsx`: escribe `VALORES`, calcula `DINAMICA` (una fila por proveedor y producto) y llena `ORDENES` con las fórmulas del original (`=DINAMICA!A4`, ítem consecutivo, `=S*Q`).
2. `GET /api/exportar/alternativas` usa `exportador.filas_por_puesto`: para cada producto por comprar toma su 2.ª, 3.ª y 4.ª oferta del ranking (en las mismas 8 columnas de VALORES) y `libros_excel.alternativas_xlsx` arma, por cada puesto, las **tres hojas de la OC** (`VALORES 2.º`, `DINAMICA 2.º`, `ORDENES 2.º`...: 9 en total). Las fórmulas de `ORDENES 2.º` leen de `'DINAMICA 2.º'`.
3. **Cómo se escriben (por velocidad):** `openpyxl` solo arma el libro; las filas de datos y las celdas combinadas se escriben como XML ya armado (`_hoja_ordenes`, `_hoja_dinamica`, `_hoja_valores`) y se insertan en el archivo (`_inyectar`), con los formatos de la plantilla (`_estilo`). Cada fórmula lleva su valor calculado (`_c_formula`). Con `merge_cells` de openpyxl la OC tardaba casi un minuto, porque revisa todos los rangos ya combinados en cada fila.
4. Si se cambia algo de estas hojas hay que mantener las reglas que Excel exige y LibreOffice perdona (sin filas repetidas, celdas en orden, estilos que existen): `tests/test_libros_excel.py → _revisar_estructura` las vigila.

### …el proveedor sube su ficha y el administrador la aprueba
1. En su pantalla el proveedor elige su ficha llena: `proveedor.js → subir` hace `POST /api/proveedor/ofertas` (el archivo va como cuerpo, igual que en «Cargar datos»).
2. `pendientes.guardar_subida` lee el archivo con `cargas.leer_archivo`, **exige que sea de su proveedor** (`_exigir_que_sea_suya`: la hoja oculta de la ficha o una columna de proveedor que diga otro → 409), se queda solo con los productos que la Clínica necesita hoy, descarta lo demás, y guarda un lote **pendiente** (`lotes_oferta` + `ofertas_lote`). Si había otro pendiente del mismo proveedor, pasa a «reemplazada». **No toca la tabla `ofertas`**: nada compite todavía.
3. El administrador ve la insignia del menú (`resumen.ofertas_pendientes`) y abre «Ofertas de proveedores» (`pendientes.js`). `GET /api/pendientes/{id}` → `pendientes.detalle` compara cada precio con la mejor oferta del tablero (`tablero.construir_tablero`) y calcula el ahorro (cantidad a comprar × diferencia).
4. **Aprobar:** `pendientes.aprobar` arma un DataFrame con los precios del lote y llama a `cargas.procesar_cotizaciones(aplicar=True)`: las ofertas se crean o se actualizan como «subidas» (sin duplicar), y el lote queda «aprobada». **Rechazar:** el lote queda «rechazada» con el motivo; la tabla `ofertas` no se toca.
5. **Restaurar:** `POST /api/pendientes/{id}/restaurar` → `pendientes.restaurar`. Al **aprobar**, `pendientes.aprobar` guarda en `ofertas_lote` una «foto» de lo que había (`antes_existia`, `antes_valor`, `antes_presentacion`, `antes_creado`: la oferta «subida» de ese proveedor para ese producto). Al restaurar una aprobada, por cada producto: si la aprobación **creó** la oferta se borra; si la **actualizó** vuelve a su valor y presentación de antes; si alguien cambió ese precio después, no se toca (`no_tocadas`). Luego la ficha queda `pendiente` (sin revisor, fecha ni motivo). Una rechazada solo cambia de estado. Rechaza (409) si el proveedor ya tiene otra ficha pendiente, si hay una aprobada más reciente, o si la ficha se aprobó antes de existir la «foto». Al terminar le avisa al proveedor con `notificaciones.enviar_restauracion_oferta` («Lo sentimos… se encuentra revisando de nuevo las ofertas… Muy pronto tendrá noticias»): mismos destinatarios que aprobar y rechazar (`_destinos_del_proveedor`), el resultado va en `correo` y nunca impide la restauración.
   En la pantalla (`pendientes.js`) los botones del pie dependen del estado de la ficha que se ve: pendiente → «Aprobar» y «Rechazar»; ya decidida → «Restaurar». Al confirmar una decisión, los dos botones se esconden de inmediato y la ventana se queda en la ficha (no vuelve a la lista).
5. El proveedor ve el estado en «Mis fichas enviadas» (`GET /api/proveedor/ofertas` → `pendientes.mis_lotes`: solo campos de su propio lote, nunca precios de otros).

### …las alternativas siguen a la oferta que elegiste
`exportador.filas_por_puesto` toma, de cada producto por comprar, el ranking completo (`rk.construir_ranking`) y **quita la oferta elegida** (`i["elegida"]`, la que va en la OC): las que quedan, en orden, son la alternativa 2.ª, 3.ª y 4.ª. Si la elegida es la mejor, son la 2.ª, 3.ª y 4.ª del ranking; si elegiste otra, la que era la mejor pasa a ser la 2.ª. La prueba está en `tests/test_listas_alternativas_y_rechazo.py`.

### …rechazas una ficha de un proveedor
`pendientes.rechazar` exige un motivo (mínimo 3 letras), deja el lote «rechazada» y llama a `notificaciones.enviar_rechazo_oferta` con los correos del usuario que subió la ficha y del contacto de su empresa (`_destinos_del_proveedor`, sin repetir). El correo nunca hace fallar el rechazo: el resultado (`correo`: enviado, no_configurado, error o sin_dato) vuelve a la pantalla, que lo muestra.

### …el sistema decide qué es «Nuevo»
1. Al arrancar y cada vez que se arma el tablero (`tablero.construir_tablero`), `etiquetas.sincronizar` compara los productos y empresas que hay con los de la tabla `vistos` y anota los que faltan con la fecha de hoy. Lo que ya había al empezar (o al actualizar la aplicación) se anota **sin fecha**: es «de siempre».
2. `etiquetas.nuevos` devuelve los que se anotaron en los últimos `DIAS_NUEVO` días. El tablero los manda como `nuevo` (producto) y `empresa_nueva` (en cada oferta); la lista de empresas y la ficha, como `nuevo`.
3. `util.js → etiquetaNuevo` dibuja la pastilla; `app.js`, `empresa.js` y `podio.js` la ponen junto al producto y al nombre de la empresa.

### …pulsas el nombre de un proveedor
1. `empresa.js → nombreEmpresa` es un botón que llama a `abrirEmpresa(cod)`, que pide `GET /api/empresas/{cod}/ficha`.
2. `fichas.ficha_empresa` junta: el contacto (de la tabla EMPRESAS de Administración), sus ofertas (una por producto: la más barata si repitió) con su puesto en el ranking, y cuánto se le compraría hoy (usa `construir_tablero`, así cuenta lo elegido a mano y las cantidades editadas).
3. La ventana se dibuja con cifras y una lista con buscador. Se abre encima de «Mejor oferta» si se pulsó desde allí.

### …se crea un usuario o se restablece una clave (la animación)
1. `usuarios.js` llama a `conViaje(() => api.crearUsuario(…))` (o `restablecerClave`). `viaje.js` abre `#dlg-viaje`, mete la escena en su Shadow DOM y lanza la petición.
2. Mientras el servidor trabaja (crear el usuario y, si están configurados, enviar el correo y el WhatsApp) el doctor avanza hacia el 88 % del camino cada vez más despacio: **nunca llega antes de que haya respuesta**. Los textos cambian por tramos.
3. Al llegar la respuesta corre el último tramo, la clínica saluda, la ventana se cierra y aparecen el usuario y la clave temporal. Dura al menos ~2 s; si el servidor tarda 4 s, dura ~6.
4. Si la petición falla, la ventana se cierra y el formulario **sigue abierto** con el mensaje de error y lo que se había escrito.
5. Con «reducir movimiento» activado en el sistema no se dibuja la escena: solo el texto y la barra de progreso.

### …agregas o editas una fila y el sistema evita los repetidos
1. `tablas.insertar` y `admin.editar` llaman a `tablas.exigir_sin_repetidos`: compara la **llave** de la fila (`clave_natural`: el código, o empresa + producto) con las demás, ya normalizada (`05` = `5`, sin distinguir mayúsculas), y las columnas de `Tabla.unicas` (el NOMBRE de una empresa).
2. Al **editar** solo se revisa lo que cambió: una fila que ya venía repetida del Excel se puede seguir editando, siempre que no se toque su código.
3. Importar un archivo y «Deshacer» usan las funciones «crudas» y **no** revisan repetidos a propósito (son cargas de datos tal cual).
4. «Agregar oferta» (`routers/ofertas.py`) y los usuarios (`seguridad._exigir_contacto_unico`) tienen sus propias revisiones.

### …ingresas a la aplicación
0. Si abriste el **enlace del correo** (termina en `/?ingresar=1`), `app.js → arrancar` lo detecta primero: limpia la dirección, cierra con `DELETE /api/sesion` la sesión que hubiera en ese navegador y muestra el ingreso con un aviso. Así el enlace nunca entra directo como otra persona. La dirección con ese final la arma `notificaciones.enlace_de_ingreso`.
1. `app.js → arrancar` pide `GET /api/sesion`. Sin cookie responde 401 y se muestra solo el formulario de ingreso (el resto de la página queda oculto).
2. Al enviar, `POST /api/sesion` llama a `seguridad.ingresar`: compara la clave (scrypt), cuenta los fallos (5 = bloqueo de 5 min) y, si todo va bien, crea una sesión de 12 h. El servidor pone una cookie `HttpOnly`; en la base solo queda su huella (sha256).
3. Si la cuenta tiene `cambiar_clave` (usuario nuevo o restablecido), `pedirClaveNueva` abre un diálogo **que no se puede cerrar** hasta cambiarla; mientras tanto el guardián rechaza cualquier otra ruta.
4. `aplicarPerfil` deja visible en el menú solo lo que lleva tu perfil en `data-roles` y te lleva a tu pantalla.

### …pides una ruta del servidor (cómo se decide el permiso)
1. Antes de cada ruta corre `autorizacion.autorizar`: busca la sesión por la cookie (401 si no hay o venció).
2. Busca la ruta en `seguridad.POLITICA` (método + patrón → perfiles permitidos). Si tu perfil no está: 403. Si la ruta no está declarada: solo el administrador.
3. En `POST/PUT/DELETE` comprueba además que el `Origin` sea el propio sitio.
4. La pantalla **oculta** lo que no puedes usar, pero eso es comodidad: **quien manda es el servidor**, y `tests/test_seguridad.py` prueba cada perfil contra cada ruta.

### …el administrador gestiona usuarios
1. «Usuarios» (`usuarios.js`) llama a `/api/usuarios`; `seguridad.py` aplica las reglas: clave válida, siempre queda un administrador activo, nadie se cambia el perfil ni se elimina a sí mismo.
2. «Restablecer clave» genera una temporal (`clave_temporal`) que se muestra **una sola vez**; la persona deberá cambiarla al ingresar.
3. Al cambiar el perfil, desactivar o restablecer a alguien se **cierran sus sesiones**.
4. El historial de Administración anota **quién** hizo cada cambio.

### …el administrador crea un usuario con correo y celular
1. El formulario de «Usuarios» (`usuarios.js → abrirFormulario`) pide usuario, nombre, **correo** y **celular** (los cuatro **obligatorios**, marcados con asterisco rojo), perfil y, si es externo, proveedor. Bajo el formulario avisa qué envíos automáticos hay configurados.
2. `POST /api/usuarios` valida todo (`seguridad.exigir_contacto` rechaza si falta correo o celular; `normalizar_correo` y `normalizar_celular` revisan el formato: el celular queda como `+57…`), crea el usuario con clave temporal y llama a `notificaciones.enviar_credenciales`.
3. Esa función intenta el correo y el WhatsApp por separado; si uno falla, el otro sigue y **el usuario queda creado igual**. La respuesta trae `envio` con el resultado de cada uno.
4. La ventana de la clave temporal (`mostrarClaveTemporal`) muestra esos resultados y, si WhatsApp no se envió, el botón «Abrir WhatsApp con el mensaje». Al cerrarla se borran la clave y ese enlace de la pantalla.
5. «Restablecer la clave» hace lo mismo con una clave nueva.

### …entra un proveedor externo o una persona de Consulta
- **Externo:** solo ve «Productos que necesitamos» (`/api/proveedor/productos`: solo código y descripción; nunca precios ni cantidades). Su botón baja `COTIZACION_<proveedor>.xlsx` con `exportador.cotizacion_xlsx`: columnas de precio y presentación vacías, en amarillo.
- **Consulta:** ve el tablero sin poder editar ni elegir proveedor, y **no descarga ningún Excel**. (`PRODUCTOS_A_COMPRAR.xlsx`, de `exportador.productos_a_comprar_xlsx`, lo bajan solo administrador y Prime por la API.)

## 4. «Quiero cambiar…» → dónde tocar

| Quiero cambiar… | Archivo y lugar |
|---|---|
| Qué muestran los **tableros de control** (empresas con menores valores, precios más baratos, productos que más consumen) | `services/control.py` (los cálculos) y `js/control.js` (la pantalla) |
| El **ojo** para ver la clave que se escribe | `js/util.js → activarVerClave` (se llama en `app.js → iniciar`) y los estilos `.ver-clave` en `css/seguridad.css` |
| Cómo se **leen los números** de los Excel (miles, decimales, negativos) | `services/normalizacion.py → numero` (textos) y `celda_a_texto` / `leer_excel` (celdas numéricas) |
| Cómo se **reparte la compra** cuando el mejor proveedor no tiene unidades para todo | `services/ranking.py → repartir` (la regla) y `services/tablero.py → construir_tablero` (el total, el ahorro y las líneas del reparto) |
| Qué puede hacer cada **perfil** en el servidor | `services/seguridad.py → POLITICA` (método, patrón de ruta, perfiles) |
| Qué **opciones del menú** ve cada perfil | `index.html → data-roles` de cada opción |
| A qué **pantalla** va cada perfil al ingresar | `js/app.js → PANTALLAS_POR_PERFIL` |
| Un **perfil nuevo** | `services/seguridad.py → ROLES` y `POLITICA`, `index.html → data-roles`, `js/app.js → PANTALLAS_POR_PERFIL` y las listas de `js/usuarios.js` |
| Las **reglas de la clave** (largo, letras y números) | `services/seguridad.py → validar_clave` |
| Cuántos **fallos** bloquean y por cuánto tiempo | `services/seguridad.py → MAX_INTENTOS` y `BLOQUEO` |
| Cuánto **dura la sesión** (12 h) | `services/seguridad.py → DURACION_SESION` |
| Las **cabeceras de seguridad** (CSP, etc.) | `app/main.py` (middleware de cabeceras) |
| El **nombre** de la aplicación (SUMIPABON) | `frontend/index.html` (título, barra lateral, ingreso y pie), `app/main.py`, `app/services/notificaciones.py` (texto del mensaje), `README.md` |
| Que el enlace del correo **no cierre la sesión** y entre directo (no recomendado) | `services/notificaciones.py → enlace_de_ingreso` y `js/app.js → arrancar` (el bloque de «ingresar») |
| El **superusuario con clave fija** (nombre, clave, cómo se protege) | `.env` (`COMPRAS_SUPERUSUARIO`, `COMPRAS_SUPERUSUARIO_CLAVE`) · `services/seguridad.py → asegurar_superusuario / superusuario_protegido / _exigir_no_protegido` · `main.py → asegurar_superusuario` |
| Crear un **superusuario** desde la terminal | `app/usuarios_cli.py → _crear_superusuario` (`python -m app.usuarios_cli crear-admin <usuario>`) |
| Si los demás equipos pueden **entrar desde la red** | `run.py → HOST` o la variable `COMPRAS_HOST` (`0.0.0.0` = toda la red; `127.0.0.1` = solo este computador) |
| Hacer el correo y el celular **opcionales u obligatorios** | `services/seguridad.py → exigir_contacto` y `routers/usuarios.py` (`contacto_obligatorio=True`) |
| Qué **columnas** trae el Excel de cotización del proveedor | `services/exportador.py → cotizacion_xlsx` |
| A dónde y cómo se **envían** el usuario y la clave | El archivo `.env` (datos) y `services/notificaciones.py` (`enviar_correo`, `enviar_whatsapp`) |
| El **texto del mensaje** que reciben (cuenta nueva y clave restablecida tienen cada una el suyo) | `services/notificaciones.py → _frases` (cómo abre y cierra cada mensaje), `asunto`, `mensaje` (texto y WhatsApp) y `mensaje_html` (el correo con botón); si usas plantilla de WhatsApp, la plantilla en Meta |
| Cómo se **valida el celular o el correo** | `services/seguridad.py → normalizar_celular / normalizar_correo` |
| Las **columnas** de `PRODUCTOS_A_COMPRAR.xlsx` o de la cotización | `services/exportador.py → productos_a_comprar_xlsx / cotizacion_xlsx` |
| Qué datos recibe el **proveedor externo** | `routers/proveedor.py` (y `tests/test_seguridad.py`, que comprueba que no salgan precios) |
| Cuántos **dígitos** caben en la cantidad editable y su **tope** (10.000.000) | `js/app.js → CANTIDAD_MAX` y `schemas.py → CantidadIn`; el ancho de la caja: `css/extras.css → .cantidad-input` |
| Cómo se ve la fila en **celular** o en escritorio | `css/componentes.css` (columnas de la fila) y `css/extras.css` (`@container lista`) |
| Qué sale en la **ficha de la empresa** | `services/fichas.py` (los datos) y `js/empresa.js` (cómo se dibuja) |
| **Qué no se puede repetir** en cada tabla | `services/tablas.py → Tabla.clave_natural` y `Tabla.unicas` (en la definición de cada tabla) |
| Hacer **opcional** el teléfono o el correo de una empresa | `services/tablas.py` → quitar `TELEFONO` / `CORREO` de `obligatorias` en la tabla `empresas` |
| Los avisos «Preparando…» de las descargas | `js/util.js → descargarConAviso`; basta agregar `data-descarga="lo que se descarga"` al enlace `<a href download>` |
| Qué dice el mensaje cuando el correo no está configurado | `services/notificaciones.py → diagnostico_env` |
| Qué columnas o formato tiene la **ficha** o la **orden de compra** | Se cambia el Excel original y se vuelve a correr `herramientas/preparar_plantillas.py`; el código que las llena es `services/libros_excel.py` |
| Cuáles puestos trae el libro de **alternativas** (hoy 2.º a 4.º) | `services/libros_excel.py → PUESTOS_ALTERNATIVOS` |
| Qué **precio** se lee de la ficha del proveedor (hoy el que no lleva IVA) | `services/cargas.py → _leer_ficha` (columna «PRECIO»; el «PRECIO + IVA» es otra) |
| Los **logos** del inicio y las certificaciones del pie | `frontend/img/` (se reemplazan los archivos) y `css/extras.css`, sección «Inicio: logos de la Clínica y certificaciones» |
| Que la ficha del proveedor entre **directo** al tablero, sin aprobación | `services/pendientes.py → guardar_subida` (en vez de guardar el lote, llamar a `cargas.procesar_cotizaciones(aplicar=True)`) |
| Qué pasa con una ficha **pendiente** que el proveedor reemplaza | `services/pendientes.py → guardar_subida` (el `UPDATE ... 'reemplazada'`) |
| Quién ve la pantalla del proveedor | `services/seguridad.py → POLITICA` (las rutas `/api/proveedor/...`) y `frontend/js/app.js → PANTALLAS_POR_PERFIL` |
| Quién recibe el correo cuando se **rechaza** una ficha | `services/pendientes.py → _destinos_del_proveedor` |
| Qué se hace al **restaurar** una ficha (y qué protecciones tiene) | `services/pendientes.py → restaurar` |
| El texto del correo de **restauración** («estamos revisando de nuevo sus ofertas») | `services/notificaciones.py → enviar_restauracion_oferta` (lo llama `pendientes.restaurar`) |
| El texto del correo de **aprobación** (avisa que la Clínica Pabón se pondrá en contacto) | `services/notificaciones.py → enviar_aprobacion_oferta` (lo llama `pendientes.aprobar`; los destinatarios son los mismos, `_destinos_del_proveedor`) |
| El texto del correo de **rechazo** | `services/notificaciones.py → enviar_rechazo_oferta` |
| Qué es «**sin oferta**» o «**nuevos**» para el proveedor | `services/tablero.py → para_proveedor` |
| Cuántos días dura la etiqueta **«Nuevo»** | `config.py → DIAS_NUEVO` |
| El texto de la ventana **«¿Está seguro de la cantidad?»** | `js/app.js → confirmarCantidad` |
| El tamaño de la **animación de espera** | `css/extras.css → dialog.modal.viaje` (ancho) |
| Que las ventanas **no se puedan mover** | `js/app.js` → quitar la llamada a `hacerMovibles()` (la función está en `js/util.js`) |
| El tamaño mínimo de los botones en **celular** (44 px) | `css/extras.css`, sección «Ventanas emergentes: movibles y adaptadas al celular» |
| La **animación de espera**: duración mínima, velocidad, textos | `js/viaje.js` (`ESPERA_MIN`, `SPRINT`, `FLORITURA`, `TAU`, `etapas`) |
| El **dibujo** de la animación (doctor, clínica, colores) | No se edita a mano: se cambia la página de animación original y se corre `python herramientas/preparar_animacion.py <página .html>`, que regenera `viaje/escena.txt` y `viaje/doctor.webp` |
| La regla de **cuánto comprar** | `services/ranking.py → cantidad_a_comprar` |
| Cómo se decide el **mejor proveedor** (p. ej. tener en cuenta la presentación) | `services/ranking.py → construir_ranking` |
| Cuántas ofertas salen por paso en el podio | `config.py → OFERTAS_POR_PAGINA` **y** `js/podio.js → POR_PASO` (deben coincidir) |
| Los **botones** «Mejor oferta» / «Otras ofertas» de cada fila | `js/app.js → celdaAcciones` (y `css/componentes.css → .btn-fila`) |
| La **ventana** que abren esos botones (título, tamaño, pie) | `index.html → #dlg-ofertas`, `js/app.js → abrirOfertas` y `css/agregar.css → dialog.modal.extra` |
| Las **pestañas** del panel de ofertas y qué muestra cada una | `js/podio.js → tiraDePestanas`, `cuerpoMejor`, `cuerpoOtras`, `cuerpoTodas` |
| El ancho a partir del cual la fila se acomoda en 3 renglones | `css/componentes.css → @media (max-width: 1500px)` |
| El **nombre de un Excel** | `config.py → ARCHIVOS_EXCEL` |
| El **nombre de una columna** de un Excel (o un nombre alternativo que se acepte al importar) | `services/tablas.py → TABLAS` (`columnas` y `alias`) |
| Una **tabla nueva** en Administración | `services/tablas.py → TABLAS` (se crea sola en la base) y, para que afecte al tablero, `importador.recalcular` |
| Qué columnas son **numéricas u obligatorias** al escribir una fila | `services/tablas.py → TABLAS` (`numericas`, `obligatorias`) |
| Qué identifica una fila en «Agregar y actualizar» | `services/tablas.py → TABLAS` (`clave_natural`, `normalizadores`) |
| Filas por página de la administración | `js/admin.js → E.tam` |
| Cuántos cambios y copias recuerda el historial | `services/historial.py → MAX_CAMBIOS`, `MAX_COPIAS` |
| El **mensaje de impacto** al eliminar | `services/tablas.py → impacto` |
| Un **aviso nuevo** sobre los datos (con su botón «Ir a corregir») | `services/importador.py → recalcular` (agregar a `avisos` con una `clave` nueva y un `_destino(...)`) |
| A dónde lleva el botón de un aviso | `services/importador.py → _destino`; en pantalla, `js/app.js → irAlAviso` y `js/admin.js → irA` |
| Qué **encabezados** acepta un Excel **subido** (p. ej. otro nombre para «VALOR») | `services/cargas.py → COLUMNAS` (y `REQUERIDAS` para las obligatorias) |
| El **tamaño máximo** de un Excel subido o su número de filas | `services/cargas.py → MAX_BYTES`, `MAX_FILAS` |
| Las **reglas de una fila** subida (qué es un error, qué se omite) | `services/cargas.py → procesar_productos / procesar_proveedores / procesar_cotizaciones` |
| Las **plantillas** descargables (columnas e instrucciones) | `services/plantillas.py → PLANTILLAS` |
| Las **reglas de productos y proveedores** (duplicados, qué se puede eliminar...) | `services/catalogo.py` |
| El **texto de ayuda** de cada pestaña de «Cargar datos» | `js/cargar.js → TIPOS` |
| Un **panel emergente** nuevo (otro formulario encima de la pantalla) | Un `<dialog class="modal">` más en `index.html`, su lógica en un `js/…​.js` con `montar…` como `agregar.js`, y conectarlo en `js/app.js → iniciar` |
| Los **campos** del formulario de producto | `schemas.py → ProductoIn / ProductoEdit`, `js/cargar.js → formProducto` |
| Desde qué número se **numeran** los proveedores creados por ti | `config.py → PRIMER_CODIGO_EMPRESA_MANUAL` |
| Las **columnas de la hoja VALORES de la OC** | `services/exportador.py → COLUMNAS` y `filas_valores` |
| Un **filtro nuevo** (botón) | `services/tablero.py → FILTROS` y `_cumple`; `routers/productos.py → listar`; `js/app.js → FILTROS` |
| Un **criterio de orden nuevo** | `services/tablero.py → filtrar_y_ordenar`; `index.html → #orden` |
| **Productos por página** | `js/app.js → S.tam` |
| Los **colores** de la aplicación | `css/base.css → :root` (hay un solo diseño) |
| Las **tipografías** | `css/base.css → --font` (texto), `--font-encabezado` (h1–h6), `--font-display` (títulos grandes), `--font-titulo` (cifras) y `--font-boton` (botones); los archivos están en `frontend/fonts/` |
| Las **opciones del menú lateral** (nombre, orden, icono) | `index.html → #menu`; qué hace cada una: `js/app.js → iniciar` y `armarMenu` (las que son pantallas llevan `data-pantalla`) |
| La **pantalla de bienvenida** (textos, botón, datos rápidos) | `index.html → #vista-inicio`; los datos: `js/app.js → cargarResumen` |
| El **ancho del menú** o el alto de la barra azul | `css/base.css → --menu-w` y `--barra-h` |
| El **puerto** preferido (8000) | `run.py → PUERTO_PREFERIDO` (o, sin tocar código, la variable `COMPRAS_PUERTO`) |
| Qué **librerías** exige `run.py` antes de arrancar | `run.py → LIBRERIAS` (y `requirements.txt` para instalarlas) |
| Los **colores del medidor** de stock | `services/ranking.py → nivel_stock` (reglas) y `css/componentes.css → .medidor` (colores) |

## 5. Glosario

| Palabra | Significado |
|---|---|
| **Oferta** | «El proveedor X vende el producto Y a $Z por unidad». |
| **Ranking / podio** | Las ofertas de un producto ordenadas de la más barata a la más cara. |
| **Cantidad disponible / reparto** | Cuántas unidades puede entregar un proveedor. Si el mejor no tiene para todo, la compra se reparte con el siguiente más barato (`ranking.repartir`). |
| **Mejor / 2.ª / 3.ª** | Puestos 1, 2 y 3 del ranking. |
| **Elegida** | La oferta con la que realmente se va a comprar: la mejor, salvo que hayas elegido otra. |
| **Manual** | Producto, proveedor u oferta que escribiste a mano en la pantalla (no viene del Excel). |
| **Subido** | Lo que cargaste subiendo un Excel en «Cargar datos». |
| **Propio** | Todo lo que es tuyo (manual o subido): se conserva al actualizar los Excel base y se puede eliminar. |
| **Origen** | De dónde salió un dato: `excel`, `manual` o `subido`. |
| **Cotización** | Lo mismo que una oferta, en el lenguaje de compras: el precio que un proveedor da por un producto. |
| **Plantilla** | Un Excel en blanco, con los encabezados correctos y una hoja de instrucciones, para llenarlo y subirlo. |
| **Revisar / Cargar** | Los dos pasos al subir un Excel: *revisar* cuenta qué pasaría sin guardar nada; *cargar* lo guarda. |
| **Pestaña** | Cada una de las vistas del panel de una fila (Mejor oferta, Otras ofertas, Comparar todas) o del panel «Cargar datos». |
| **Panel emergente** | Una caja que se abre encima de la pantalla (`<dialog>`): «Agregar oferta», «Cargar datos» y «Ofertas del producto». Oscurece el fondo, se cierra con Esc y **no** es una ventana aparte, así el navegador no la bloquea. |
| **Migración** | Ajustar automáticamente una base de datos vieja para que funcione con la versión nueva. |
| **Aviso** | Un problema detectado en los Excel (proveedor sin nombre, código repetido…). Tiene una `clave` estable y botones «Ir a corregir». |
| **Destino** | A dónde lleva un botón «Ir a corregir»: una tabla con ciertas filas, el formulario de agregar con valores puestos, o el tablero con un filtro. |
| **Tablas de los Excel** | Las 5 tablas (`x_stock`, `x_existencias`, `x_empresas`, `x_ficha`, `x_portafolio`) que copian cada Excel con sus mismos encabezados. Son las que editas en Administración. |
| **Recalcular** | Volver a calcular productos, proveedores, ofertas y avisos a partir de las 5 tablas. Ocurre después de cada cambio. |
| **Huérfano** | Un dato que perdió a su pareja (una oferta de un proveedor eliminado, un producto sin stock…). Se permite, pero sale en los avisos. |
| **Historial** | La lista de cambios de la administración; cada uno se puede **deshacer**. |
| **Perfil / rol** | El tipo de usuario: `admin`, `prime`, `consulta` o `externo`. Decide qué ve y qué puede hacer. |
| **Sesión** | El «ya ingresaste» de tu navegador: dura 12 horas y vive en una cookie que la página no puede leer. |
| **SUMIPABON** | El nombre de la aplicación (antes «Mesa de ofertas»). |
| **`.env`** | Archivo de texto en la raíz con tus datos de envío (correo y WhatsApp). Tiene claves: no se sube a Git. |
| **HOST** | A quién deja entrar el servidor: `0.0.0.0` = cualquier equipo de la red; `127.0.0.1` = solo este computador. |
| **Cantidad editada** | La cantidad a comprar que una persona fijó a mano para un producto. Manda sobre la calculada hasta que se restaura. |
| **Ficha de la empresa** | La ventana que se abre al pulsar el nombre de un proveedor: contacto, cifras y sus ofertas. |
| **Shadow DOM** | Una «burbuja» del navegador donde los estilos de adentro no afectan a la página ni al revés. Se usa para la animación de espera. |
| **Llave (de una fila)** | Lo que identifica una fila para detectar repetidos: el código, o la pareja empresa + producto. |
| **FR-GDS-07** | El código de la «Ficha de solicitud de cotización» de la Clínica: el Excel que llena el proveedor. |
| **OC (orden de compra)** | El libro con las hojas VALORES (datos), DINAMICA (resumen por proveedor) y ORDENES (la orden). |
| **DINAMICA** | Antes una tabla dinámica de Excel; ahora una tabla que calcula la aplicación con el mismo resultado. |
| **Lote (de ofertas)** | Una ficha que subió un proveedor, con sus precios: pendiente, aprobada, rechazada o reemplazada. |
| **Pendiente de aprobación** | Los precios del proveedor ya están guardados pero **todavía no compiten**: espera que el administrador los apruebe. |
| **Nuevo (etiqueta)** | La pastilla de un producto o una empresa que el sistema ve por primera vez; dura 7 días. |
| **Stock suficiente** | Lo que dice la columna «Comprar» cuando no hay nada que comprar porque las existencias están en el máximo o por encima. |
| **Ventana movible** | Una ventana emergente que se arrastra por su cabecera; doble clic la vuelve al centro. |
| **SMTP** | El protocolo con el que un programa envía correos a través de un servidor (Gmail, Outlook, el de la Clínica). |
| **Plantilla de WhatsApp** | Un mensaje con huecos ({{1}}, {{2}}…) que Meta debe aprobar antes; es lo único con lo que se le puede escribir primero a alguien. |
| **Clave temporal** | La que recibe un usuario nuevo o restablecido; se muestra una sola vez y obliga a elegir una propia. |
| **scrypt** | La forma de guardar las claves: nunca en texto, solo su «huella» difícil de revertir. |
| **Política (`POLITICA`)** | La tabla que dice qué perfil puede usar cada ruta. Lo no declarado es solo del administrador. |
| **CSRF** | Un ataque en que otra página intenta hacer cambios con tu sesión; se frena comprobando de dónde viene la petición. |
| **Ruta / endpoint** | Una dirección que la pantalla le pide al servidor, p. ej. `/api/resumen`. |
| **API** | El conjunto de rutas del servidor. |
| **JSON** | El formato de texto en que viajan los datos entre servidor y pantalla. |
| **Transacción** | Grupo de cambios en la base que se guardan todos o ninguno. |
| **KPI** | Cada uno de los 4 números grandes de arriba. |
| **Toast** | El aviso flotante que desaparece solo. |
| **Debounce** | Esperar a que dejes de escribir antes de buscar. |

## 6. Convenciones del código

- Los nombres están **en español** (`construir_ranking`, `cargarLista`, `pintarChips`).
- `pintar…` **dibuja** en pantalla; `cargar…` **pide datos** al servidor y luego pinta.
- Un nombre que empieza con `_` (`_leer`, `_cumple`, `_busqueda`) es **interno**: solo se usa dentro de su archivo.
- Una función **pura** (las de `ranking.py`) no toca la base ni la web: mismos datos → mismo resultado.
- Los **comentarios explican el «porqué»**; el nombre de cada función explica el «qué».
- **Cada regla nueva lleva su prueba** en `tests/` (`test_manual.py`, `test_cargas.py`, `e2e/test_interfaz.py`): si algo se rompe, `python -m pytest` lo dice.
