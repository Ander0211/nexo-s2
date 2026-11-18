# SUMIPABON · Compras

Aplicación web (FastAPI + SQLite + HTML/JS) que reemplaza la pantalla **«Visualizar mejor precio por producto»**
de Access. Para cada producto calcula **cuánto comprar** y **a quién**, y muestra la **1.ª, 2.ª y 3.ª mejor oferta**
con un botón para seguir viendo las siguientes.

> 📖 **¿Quieres entender cómo funciona el código?** Lee la [**Guía del código**](docs/GUIA_DEL_CODIGO.md):
> mapa de cada archivo, recorridos paso a paso («qué pasa cuando pulsas X»), tabla «quiero cambiar… → dónde tocar» y glosario.
> Además, **cada archivo empieza con un comentario que explica su papel** y cada función explica lo que hace.

## Qué hace

- **Cantidad a comprar** = `StockMax − Existencias` (nunca menor que 0, en unidades enteras).
- **Mejor proveedor** = el de menor `VALOR`. En cada fila, dos botones abren una **ventana emergente**:
  **«Mejor oferta»** (la más barata y por qué lo es) y **«Otras ofertas»** (la 2.ª, 3.ª… con **«Ver siguientes ofertas»**
  de 3 en 3). Dentro de la ventana, la pestaña **«Comparar todas»** muestra el podio 🥇🥈🥉 lado a lado. Se cierra con la ✕, «Cerrar» o Esc.
- **Elegir a mano** otro proveedor distinto al mejor (queda marcado «Elegida por ti»).
- **Cantidad disponible y reparto de la compra.** Cada oferta puede decir **cuántas unidades puede entregar** el proveedor (en la ficha FR-GDS-07 es la columna
  «CANTIDAD DISPONIBLE PROVEEDOR»; en «Cargar datos → Cotizaciones», la columna opcional `CANTIDAD_DISPONIBLE`; en «Agregar oferta», el campo «Cantidad disponible»).
  Vacía = no lo dijo (se supone que le alcanza); 0 = no tiene unidades. **Si el mejor proveedor no tiene unidades para todo lo que hay que comprar, se le compra lo que tenga
  y el resto al siguiente más barato, y así hasta cubrirlo**: el total, el ahorro, «Dónde comprar» y la **OC** (una fila por proveedor) usan ese reparto. La fila avisa
  **«Repartido en N proveedores»** o **«Faltan N und: nadie las tiene»**, y la ventana de ofertas explica a quién se le compra cuánto.
  Si **eliges un proveedor a mano** no se reparte: se le compra todo a ese y solo se avisa si dijo tener menos. Sin ninguna cantidad declarada, todo sale como siempre.
  Al revisar una ficha, el administrador ve la cantidad que dijo el proveedor frente a lo que se necesita; si el proveedor vuelve a subir su ficha **sin cantidad**, la anterior se borra
  (para no repartir con un tope viejo) y **«Restaurar»** la devuelve.
- **Editar la cantidad a comprar** (administrador y Prime): en cada fila la cantidad es una **caja donde se escribe** (caben 8 dígitos, sin
  flechitas encima del número; Enter guarda, Esc cancela, ↑ ↓ suben o bajan). **Solo cambia cuántas unidades vas a comprar según tu necesidad: no toca el stock ni el máximo** (la barra «3 en stock · máx 15» queda igual, ponga lo que se ponga), ni las tablas, ni el historial. Al guardar, **la fila se queda donde estaba** (no se reordena ni desaparece, aunque le pongas 0: se atenúa con un aviso hasta que pulses «Actualizar todo»). Lo que fijas **dura hasta que lo restaures** con el botón «editada ·
  calculada N»: no lo cambian las existencias ni «Actualizar Excel». Cambia el total, los indicadores y los Excel exportados. Se puede comprar
  también un producto que no tenía nada por comprar, o poner 0 para sacarlo de la lista. En el celular la cantidad pasa a su propia fila.
- **Antes de guardar una cantidad, el sistema pregunta** «¿Está seguro de la cantidad a comprar?»: repite el producto y la cantidad, compara con lo
  recomendado (máx − stock), dice cuántas unidades quedarían y, si compras **menos de lo recomendado**, lo avisa («faltarían 30 unidades»). «Sí, guardar»
  guarda y «Revisar» vuelve a la caja sin guardar nada. Una fila con la cantidad menor a la recomendada queda marcada «Menos de lo recomendado (80)».
  Restaurar no pregunta.
- **«Stock suficiente»:** cuando no hay nada que comprar porque las existencias ya están en el máximo o por encima, la columna «Comprar» lo dice en vez de
  mostrar un «—». (Poner 0 a un producto al que le falta stock **no** lo marca como suficiente: solo no se compra.)
- **El proveedor sube su propia oferta.** En su pantalla «Productos que necesitamos» descarga la ficha FR-GDS-07, escribe sus precios y **la sube él mismo** («Enviar mi oferta»). Esa ficha
  **queda pendiente: no compite** hasta que el administrador la revisa y la aprueba, así un precio equivocado o abusivo no mueve las compras sin que nadie lo vea. Reglas: siempre queda a
  nombre de **su** proveedor (si el archivo trae a otro, se rechaza: nadie cotiza por otro), solo cuentan los productos que la Clínica necesita hoy (lo demás se descarta y se le avisa
  cuántos fueron), sin precio = no cotizó, el repetido usa el más barato, y una ficha nueva **reemplaza** a la que seguía pendiente. El proveedor ve el estado de sus fichas
  (pendiente, aprobada o rechazada con el motivo) y **nunca** precios de otros.
- **«Sin oferta» y «Nuevos» en la pantalla del proveedor:** dos botones (con su número) que abren una ventana con esa lista, un **buscador** y el botón de **descargar la ficha** con esos productos (lista para llenar y
  subir; baja lo que estás buscando). El proveedor solo recibe **código y descripción**. Ojo: «sin oferta» le dice qué productos nadie ha cotizado todavía.
- **Ofertas de proveedores** (menú del administrador, con una insignia con las que esperan): la lista de fichas y, al abrir una, **cada precio frente a la mejor oferta de hoy** (y a lo que ese
  proveedor ya ofrecía), con el ahorro estimado (cantidad a comprar × diferencia). Desde ahí se **aprueba** (sus precios pasan a competir como ofertas «subidas» y **se le envía un correo al proveedor** diciéndole que la ficha fue aprobada y que **la Clínica Pabón se pondrá en contacto con él**; al usuario que subió la ficha y al correo de contacto de su empresa, sin repetir, y sin mostrar precios ni nombres de otros proveedores; si el correo no sale, se dice por qué, pero la aprobación vale) o se **rechaza** con un motivo
  que verá el proveedor. Al aprobar rige la misma regla de no repetir: el precio de ese proveedor para ese producto se actualiza, no se duplica. La ventana tiene **buscador** (en la lista busca por proveedor, archivo
  o estado; en el detalle, por código, descripción o proveedor) y el botón **Descargar Excel** de la ficha (`OFERTA_<proveedor>_<n>.xlsx`: cada precio frente a la mejor oferta de hoy). **Al rechazar, el motivo es
  obligatorio y se le envía al proveedor por correo** (al usuario que subió la ficha y al correo de contacto de su empresa, sin repetir); si el correo no sale, se dice por qué, pero el rechazo vale.
  **Al decidir, «Aprobar» y «Rechazar» desaparecen de inmediato** y la ventana se queda en la ficha, que pasa a decir «Aprobada» o «Rechazada» y ofrece **«Restaurar»**: deshace la decisión y deja la ficha otra
  vez **pendiente de revisión**. Si estaba rechazada, solo cambia su estado. Si estaba aprobada, además **se devuelven las ofertas**: las que creó la aprobación se quitan y las que actualizó vuelven a su precio de
  antes (al aprobar se guarda una «foto» de lo que había). Protecciones: no se pisa un precio que alguien cambió después (se deja como está y se avisa cuántos), solo se restaura la **última** ficha aprobada de un
  proveedor, no se restaura si ese proveedor ya tiene otra ficha pendiente, y una ficha aprobada antes de existir «Restaurar» no se puede deshacer sola. **El correo que ya se le envió al proveedor al decidir no se puede retirar**, y por eso al restaurar se le manda **otro**: «Lo sentimos. Nuestro equipo de la Clínica Pabón se encuentra revisando de nuevo las ofertas que su empresa envió… Muy pronto tendrá noticias.» (a quien subió la ficha y al contacto de su empresa, sin repetir; sin precios; si no sale, la restauración vale igual y se dice por qué).
- **Un proveedor siempre va ligado a una empresa; si es nuevo, se agrega al crear el usuario.** En «Usuarios», al elegir el perfil proveedor hay que elegir su empresa; si no está en la lista, la opción
  **«➕ Agregar un proveedor nuevo…»** pide su nombre, teléfono y correo (propone los de la persona), la agrega a Administración → Empresas (con la regla de no repetir) y la liga. Antes se podía crear un proveedor sin
  empresa y, al subir su oferta, salía «Tu usuario no está ligado a un proveedor». Un usuario proveedor de antes que quedó sin empresa ve ese mismo aviso con lo que debe hacer.
- **El administrador también ve la pantalla del proveedor** («Productos que necesitamos»), tal como la ve el proveedor, sin la parte de subir.
- **Filtro «Nuevos»** (en la fila de filtros, junto a «Todos»): los productos nuevos y los que tienen una **empresa nueva** como mejor oferta o como la elegida; en «Dónde comprar» las empresas nuevas llevan su etiqueta.
- **Etiqueta «Nuevo»** en los productos y las empresas que **no habían estado antes** en el sistema, lleguen por Excel, a mano o subidos. Sale en la fila del
  producto, junto al nombre de la empresa (en la fila, en «Mejor oferta» y «Otras ofertas») y en su ficha, y dura **7 días** (`DIAS_NUEVO` en `app/config.py`).
  Lo que ya existía al arrancar es «de siempre»; un código que se borra y se vuelve a crear no vuelve a ser nuevo.
- **Ventanas emergentes movibles y para el celular:** se arrastran por su cabecera (ratón o dedo; doble clic las devuelve al centro y nunca salen de la
  pantalla). En el celular ocupan casi todo el ancho y alto, los botones miden al menos 44 px y el historial de cambios se ve como tarjetas.
- **Información de cada empresa:** al pulsar el **nombre de un proveedor** (en la fila o en «Mejor oferta» / «Otras ofertas») se abre su **ficha**:
  teléfono y correo, cuántas ofertas tiene, en cuántos productos es la mejor, a cuántos se le compraría y cuánta inversión suma, y la lista de
  sus ofertas con el puesto que ocupa en cada una (con buscador). Hasta el perfil Consulta la puede ver.
- **«Actualizar todo»** en el tablero: vuelve a leer del servidor los números de arriba, la lista, «Dónde comprar» y los avisos, y anota la hora.
  (Importar los Excel sigue siendo «Actualizar Excel».)
- **Sin datos repetidos:** al agregar o editar en Administración no se repite un código ni la pareja empresa + producto; una empresa tampoco repite
  su nombre; en «Agregar oferta» no se repite una oferta de la misma empresa para el mismo producto; y dos personas no comparten usuario, correo ni
  celular. Lo que ya venía repetido en los Excel se respeta (se puede seguir editando su precio). Ver [Datos repetidos](#datos-repetidos).
- **Agregar oferta manual** en un **panel** que se abre encima de la pantalla: busca el producto, elige o crea el proveedor,
  escribe el precio y ve al instante *en qué puesto quedaría*. La pantalla de fondo se actualiza sola.
- **Cargar datos** en otro **panel**: **sube un Excel** de productos, proveedores o cotizaciones (se *revisa* antes de
  cargar: qué es nuevo, qué se actualiza y qué filas tienen error) **o agrégalos a mano** con formularios.
  Incluye plantillas de Excel para descargar. Ver [Cargar datos](#cargar-datos-subir-excel-o-agregar-a-mano).
- **Descargar OC (ganadores):** la **orden de compra** con el formato de `OC.xlsm` (hojas `VALORES`, `DINAMICA` y `ORDENES`) y, de cada producto por comprar,
  el proveedor ganador (la mejor oferta o la que elegiste a mano) con la cantidad vigente. Sale como `.xlsx`: las macros del `OC.xlsm` estaban vacías.
  `DINAMICA` ya no es una tabla dinámica sino una tabla calculada por la aplicación (con el mismo resultado) y `ORDENES` conserva sus fórmulas. El total
  de `ORDENES` coincide con la «Inversión estimada» del tablero. Archivo: `OC_<fecha>.xlsx`.
- **Alternativas 2.º a 4.º** (menú; administrador y Prime): una ventana que explica y baja un solo libro con **9 hojas**: las **mismas tres hojas de la OC** (`VALORES`, `DINAMICA` y `ORDENES`) para cada puesto,
  con el puesto en el nombre (`VALORES 2.º`, `DINAMICA 2.º`, `ORDENES 2.º`, `VALORES 3.º`...). **Se ajusta a lo que elijas:** las alternativas son las **siguientes mejores ofertas sin contar la elegida** (que es la de
  la OC). Si en el tablero eliges una oferta distinta de la mejor, esa pasa a ser la de la OC y la que era la mejor se vuelve la alternativa 2.ª, y así con las demás; si no eliges otra, son la 2.ª, 3.ª y 4.ª del
  ranking. Un proveedor cuenta una sola vez aunque repita oferta. Archivo: `ALTERNATIVAS_2_a_4_<fecha>.xlsx`. **«Sin oferta» y «Nuevos» ya no van aquí:** viven solo en «Productos que necesitamos».
- **«Sin oferta» y «Nuevos» en «Productos que necesitamos»** (la pantalla del proveedor, que el administrador también ve): dos botones con su contador; al pulsarlos se abre una ventana con la lista (solo
  código y descripción), un **buscador** y el botón para **descargar la ficha** con esos productos (`..._SIN_OFERTA.xlsx` / `..._NUEVOS.xlsx`; baja lo que estás buscando). «Sin oferta» son los productos que la
  Clínica necesita y nadie ha cotizado todavía. En esa pantalla no se usa la palabra «comprar».
- **Las descargas avisan mientras se preparan:** al pulsar «Descargar OC», «Alternativas 2.º a 4.º» o la ficha del proveedor sale
  «Preparando…», el botón se apaga (no se pide dos veces) y al terminar sale «Listo: <archivo>»; si falla, dice por qué y el botón se recupera.
- **Ficha de cotización FR-GDS-07 (la «plantilla original»):** es el Excel que descarga el proveedor y también la plantilla de «Cargar datos → Cotizaciones».
  Trae el código y la descripción de cada producto por comprar, con la hoja **protegida** como en el original (el proveedor solo escribe detalle, precio, IVA,
  empaque y cantidad disponible), los dos logos y la tabla de control de cambios. Se le llenan la fecha y, si el usuario está ligado a una empresa, su razón
  social, teléfono y correo. **No lleva cantidades** (la columna «cantidad solicitada» va vacía). Al subirla de vuelta se lee el **PRECIO sin IVA** y la unidad
  de empaque, y el proveedor se reconoce solo (su código va en una hoja que Excel no deja mostrar). Ver [Los Excel con el formato oficial](#los-excel-con-el-formato-oficial).
- **Avisos de datos que te llevan al problema**: códigos repetidos, proveedores sin nombre, productos sin ninguna oferta, etc.
  Cada aviso trae botones **«Ir a corregir»**: te abren la tabla exacta con solo las filas afectadas (o el formulario de
  agregar con el código ya escrito, o el tablero con el filtro puesto). Al corregirlo, el aviso desaparece.
- **Administración** de las 5 tablas de los Excel (Stock, Existencias, Empresas, Ficha de cotización y Portafolio) con **los mismos
  encabezados del Excel**: ver, buscar, ordenar, **editar en la misma fila**, **agregar**, **eliminar** (avisando antes qué
  pasará), seleccionar todas las filas de un filtro, **descargar cada tabla como Excel** y **deshacer** desde el historial.
  Ver [Administración](#administración-las-5-tablas-de-los-excel).
- **Tableros de control** (menú «Tableros de control», para administrador, Prime y Consulta): tres vistas tipo «Power BI» sobre los mismos datos del tablero.
  **Empresas con menores valores** (cuánto más caro es cada proveedor, en promedio, que la mejor oferta de lo que cotiza: 0 % = siempre el más barato),
  **Precios más baratos** (dónde la mejor oferta más se aleja, hacia abajo, del precio promedio; por % o por $; solo productos con 2 o más ofertas) y
  **Productos que más consumen** (por cantidad a comprar, inversión o stock máximo). Un clic en una empresa **filtra las otras vistas y los números de arriba**
  (filtro cruzado, como en Power BI); también se elige cuántos renglones ver y el mínimo de productos que debe cotizar una empresa. El sistema no recibe las
  salidas de bodega: el **consumo se estima con lo que hay que reponer** (stock máximo − existencias).
- **Pantalla de bienvenida y menú lateral** (Tablero de compras · Tableros de control · Administración · Agregar oferta · Cargar datos · Actualizar Excel · Descargar OC · Alternativas 2.º a 4.º · Avisos de datos), con la
  **identidad visual de la Clínica Pabón**; búsqueda con `/`, filtros y gráfico «Dónde comprar» por proveedor. Ver [Identidad visual](#identidad-visual).

## Identidad visual

Al ingresar aparece una **pantalla de bienvenida** a pantalla completa, con el **menú a la izquierda** (como en un panel de administración: barra azul arriba,
columna azul oscura con las opciones, contenido al centro y pie azul con el logo de la clínica). El botón grande «Tablero de compras» (o la primera opción del menú) abre el tablero; las
otras opciones del menú abren sus ventanas o ejecutan su acción desde cualquier pantalla. El botón ☰ esconde o muestra el menú.

El diseño es **uno solo** y usa los colores y tipografías de la página web de la Clínica Pabón (clinicardiopabon.com): fondo claro, azules de marca, esquinas de 3 px, sin degradados ni brillos. Todo sale de las variables de `frontend/css/base.css → :root`.

| Variable | Color | De dónde sale (hoja de estilo del sitio) |
|---|---|---|
| `--accent` | `#015aaa` azul de marca | «primary» del kit de Elementor: barra de arriba, títulos, pie de página |
| `--accent-2` | `#007eff` azul vivo | «accent» del kit y color de los botones «CONOCE TODOS LOS SERVICIOS» del inicio |
| `--hover` | `#d0e6fa` azul claro | fondo al pasar el mouse por los menús desplegables |
| `--navy` | `#013e74` azul oscuro | contadores del inicio (aquí: menú lateral y cifras grandes) |
| `--hover-menu` | `#014785` | color del menú del encabezado al pasar el mouse (aquí: opción del menú lateral) |
| `--rojo-menu` / `--rojo` | `#e62429` / `#ea0b0b` | subrayado del menú y frase «CON ESTÁNDARES DE CALIDAD…» del sitio |
| `--bg` | `#f5f5f5` | «content boxes» del kit (fondo de las cajas de contenido) |
| `--muted` | `#666666` | color base del texto del sitio |
| `--faint` | `#767676` | «light-gray» del sitio |
| `--line` | negro al 12 % | «divider» del sitio |
| `--panel` | `#ffffff` | fondo del sitio |

**Medidas del sitio que se copiaron:** botones de 34 px de alto con letra Mulish 600 de 14 px y esquinas de 3 px (el «CONOCE TODOS…» del inicio usa 9 px y mayúsculas); campos con la letra en azul de marca y la ayuda al 40 %; títulos con la rayita corta de 3 px debajo.

**Tipografías** (guardadas en `frontend/fonts/`, funcionan sin internet): *Mulish* (texto y encabezados h1–h6, como el tema), *Poppins* (títulos grandes y el nombre de la aplicación) y *Montserrat* (cifras y frases en mayúsculas).

**Logos** (en `frontend/img/`): `logo-blanco.png` (barra de arriba y pie), `corazon.png` (bienvenida) e `icono-192.png` (icono de la pestaña).

> **Qué es exacto y qué es una aproximación.** Los colores salen de los valores que aparecen escritos en el código de la página; las hojas de estilo
> completas del sitio no se pudieron leer, así que **el reparto de las tres tipografías** (cuál va en títulos, texto y botones) y los tonos de fondo
> claros (`--bg`, `--panel-2`) son una interpretación. Si tienes los valores oficiales del manual de marca, cámbialos en `css/base.css` (una sola vez) y toda la aplicación se actualiza.

## Inicio rápido

Necesitas **Python 3.11 o superior** (probado con 3.12, 3.13 y 3.14) e internet la primera vez.

1. **Extrae el ZIP** con clic derecho → *Extraer todo…*. Te queda **una sola carpeta** `compras_app` con `run.py` adentro.
   Mejor fuera de OneDrive, por ejemplo `C:\proyectos\compras_app`.
2. **Ejecuta la aplicación** con cualquiera de estas dos formas:

```bash
# Windows: doble clic en iniciar.bat     ·     Linux/macOS: ./iniciar.sh
# o en una terminal, dentro de la carpeta:
python run.py
```

`run.py` se ocupa de todo lo demás: **la primera vez crea el entorno (`.venv`) e instala las librerías** (1 o 2 minutos),
**elige un puerto libre** si el 8000 no está disponible, y abre el navegador (normalmente en `http://127.0.0.1:8000` para quien la ejecuta; los demás equipos usan la IP de este; si
usó otro puerto, lo muestra en la terminal). No hace falta activar nada ni instalar librerías a mano.

**Los Excel ya no vienen con el proyecto** (son datos de la empresa): se suben a mano desde la aplicación, ver «Cargar los 5 Excel por primera vez» más abajo. Documentación interactiva de la API: la dirección de la
aplicación seguida de `/api/docs` (solo la ve el administrador).

**Ingresar por primera vez:** la aplicación ahora pide usuario y clave. Al crear la base se crea el usuario **`admin`** con una
clave temporal aleatoria que se **imprime en la terminal** (busca la línea `[compras] Usuario inicial «admin»…`). Con esa clave
entras y la aplicación te obliga a cambiarla. Ver la sección «Seguridad y perfiles».

### Problemas frecuentes

| Qué ves | Qué significa | Qué hacer |
|---|---|---|
| `No module named uvicorn` | Se usó un Python sin las librerías (p. ej. con F5 o `uvicorn` a mano en versiones viejas) | Ejecuta `python run.py` o `iniciar.bat`: detecta que faltan y las instala solo. |
| `WinError 10013 … permisos de acceso` | Windows bloquea o tiene ocupado el puerto 8000 (Docker, WSL, Hyper-V u otra app) | Ya no debería pasar: `run.py` elige otro puerto solo. Para pedir uno concreto: `set COMPRAS_PUERTO=9000` antes de ejecutar. |
| Hay **dos `index.html`** o dos carpetas `compras_app` | Se extrajo el ZIP dentro de otra copia del proyecto | Deja **una sola** carpeta con `run.py`, `app` y `frontend` adentro; borra las demás. |
| La pantalla sale vacía («Todavía no hay datos») | Todavía no se han subido los Excel (no vienen con el proyecto) | Pulsa **«Subir los Excel»** (o «Actualizar Excel» en el menú) y elige los 5 archivos juntos. |
| Un botón nuevo (p. ej. **«Cargar datos»**) **no hace nada** después de actualizar la aplicación | El navegador guardó una copia vieja de la página | Pulsa **Ctrl + F5**. Desde esta versión ya no debería pasar: los archivos se entregan con «no-cache» y «Agregar oferta» y «Cargar datos» son **paneles dentro de la misma página**, no ventanas emergentes que el navegador pueda bloquear. |
| Todo va lento o da errores raros dentro de una carpeta de **OneDrive** | OneDrive sincroniza miles de archivos del entorno | Mueve la carpeta fuera de OneDrive (p. ej. `C:\proyectos`). |
| `.venv\Scripts\python.exe: command not found` en **Git Bash** | Git Bash usa `/`, no `\` | Escribe `.venv/Scripts/python.exe run.py`, o simplemente `python run.py`. |

La tecla **F5** de VS Code (y `python run.py`) enciende la aplicación **normal**: el navegador se abre solo cuando el servidor ya responde (en el primer arranque tarda unos
segundos) y el servidor **no se reinicia solo**. Para programar con recarga automática hay una configuración aparte en VS Code («con recarga automática, solo para programar»)
o `python run.py --recargar`: reinicia el servidor cada vez que se guarda un `.py`. **No la uses para trabajar**: en una carpeta de OneDrive la sincronización también «guarda»
archivos y el servidor se reinicia solo, dejando la página caída unos segundos.

**«La página se cae y luego vuelve» al arrancar:** antes el navegador se abría a los 1,5 s fijos y, en un equipo lento, llegaba a un servidor que todavía no existía
(«no se puede acceder»); cuando el servidor terminaba de arrancar, la página volvía. Ahora `run.py` espera a que el servidor acepte conexiones y solo entonces dice
«SUMIPABON lista» y abre el navegador.

### Cargar los 5 Excel por primera vez

El proyecto **no trae los Excel** (tienen productos, existencias y precios de proveedores). Se suben a mano, una sola vez:

1. Entra como administrador (o Prime). Con la base vacía, el sistema **te pide por nombre los Excel que necesita**: la bienvenida y el tablero dicen **«Todavía no hay datos»**,
   muestran la lista **«Lo que necesita el sistema»** y traen el botón **«Subir los Excel»** (es lo mismo que **«Actualizar Excel»** del menú). La lista dice, para cada archivo,
   **para qué sirve**, si es **obligatorio** (`05-STOCK`, `06-EXISTENCIAS`, `EMPRESA` y `PORTAFOLIO`) u **opcional** (`FICHA_COTIZACION`) y si ya está cargado (cuántas filas tiene);
   se pone al día sola a medida que subes archivos, y la misma lista está dentro de «Actualizar Excel». En la terminal, al arrancar, también se imprime cuáles faltan.
2. En **«Sube tus Excel desde el computador»** elige los 5 archivos **juntos**: `05-STOCK`, `06-EXISTENCIAS`, `EMPRESA`, `FICHA_COTIZACION` y `PORTAFOLIO`.
   El sistema **reconoce a qué tabla va cada uno por su nombre** (aunque se llamen distinto, por ejemplo «Stock septiembre.xlsx»); si no reconoce uno, eliges
   su tabla; puedes quitar archivos o agregar más. También sirve subir de a uno.
3. Pulsa **«Subir e importar los archivos»**. Se suben en orden y la ventana muestra cuántas filas entraron en cada tabla. Si un archivo falla (por ejemplo, está dañado),
   los demás igual se cargan y ese queda en la lista para corregirlo y reintentar. Cada importación queda en el Historial y se puede deshacer.

*(Opcional)* Si prefieres copiar los archivos a la carpeta `data/excel/` con esos nombres exactos, la primera vez que arranque la aplicación los carga sola, y «Actualizar Excel» también ofrece importarlos de ahí.

### Actualizar los datos

**La base de datos manda.** Después de la primera carga, **los Excel nunca se vuelven a leer por su cuenta** (así no se pierde lo que editas en «Administración»): solo cuando
tú lo pides con **«Actualizar Excel»** (menú lateral) o **«Importar Excel…»** (dentro de Administración). La ventana te deja elegir:

- **Qué tablas** importar (las 5, o solo algunas): **subiendo los archivos desde tu computador** (varios a la vez o uno solo) o, si los copiaste allí, desde la carpeta `data/excel/`.
- **Cómo:** **«Agregar y actualizar»** (por defecto) suma las filas nuevas y actualiza las que ya existen por código, sin borrar nada;
  **«Reemplazar»** deja la tabla igual al Excel (borra lo que había, con tus ediciones; pide confirmación).
- Cada importación queda en el **Historial** con una copia completa de la tabla, así que se puede **deshacer**.

Lo que agregaste con «Cargar datos» o «Agregar oferta» (`manual` / `subido`) **no se toca** al importar.

| Archivo | Contenido |
|---|---|
| `05-STOCK.xlsx` | `StockMax`, `StockMed`, `StockMin` por producto |
| `06-EXISTENCIAS.xlsx` | cantidad actual por producto |
| `EMPRESA.xlsx` | proveedores |
| `FICHA_COTIZACION.xlsx` | catálogo de productos a cotizar |
| `PORTAFOLIO.xlsx` | ofertas: proveedor + producto + valor + presentación |

## Cargar datos: subir Excel o agregar a mano

El botón **«Cargar datos»** abre un panel (encima de la misma pantalla, sin ventanas emergentes) con tres pestañas: **Productos**, **Proveedores** y **Cotizaciones**
(las ofertas de precio). En cada una hay dos maneras de meter datos:

**A) Subir un Excel** — arrastra el archivo (o haz clic para elegirlo). Se **revisa solo** y ves cuántas filas son
nuevas, cuántas se actualizan, cuántas quedan sin cambios y cuáles tienen error (con el número de fila y qué pasó).
Nada se guarda hasta que pulses **«Cargar N filas»**. Las filas con error no se cargan; las demás sí.
El botón **«Descargar plantilla»** te da un Excel en blanco con los encabezados correctos y una hoja de instrucciones. En **Cotizaciones** el botón es **«Descargar ficha FR-GDS-07»**: la ficha oficial con los productos por comprar.

**B) Agregar a mano** — un formulario. En *Productos*, si escribes un código que ya existe, el formulario se rellena y
pasa a modo «editar». En *Proveedores* eliges «Proveedor nuevo» o uno existente para cambiarle el nombre.
Las *cotizaciones* a mano se agregan en el panel «Agregar oferta».

### Formatos de archivo

Se aceptan `.xlsx`, `.xlsm` y `.csv` (hasta 15 MB y 50.000 filas; se lee la primera hoja). Los encabezados se reconocen
sin importar tildes, mayúsculas o espacios (`Stock Max` = `STOCKMAX`).

| Pestaña | Columnas obligatorias | Columnas opcionales | Qué hace |
|---|---|---|---|
| **Productos** | `COD_PRODUCTO` | `DESCRIPCION`*, `STOCKMAX`, `STOCKMIN`, `EXISTENCIAS` | Crea los productos nuevos y actualiza los existentes (solo las columnas con valor; una celda vacía no borra nada). *La descripción es obligatoria solo en productos nuevos. |
| **Proveedores** | `NOMBRE` | `CODIGO_EMPRESA` | Crea los nuevos (sin código se asigna uno desde 1000) y cambia el nombre de los que ya existen. |
| **Cotizaciones** | `COD_PRODUCTO`, `VALOR` | `PRESENTACION`, `CANTIDAD_DISPONIBLE` (cuántas unidades puede entregar), `COD_EMPRESA` o `EMPRESA` (nombre) | Crea o actualiza ofertas. Si el archivo no trae el proveedor, se elige en la pantalla (uno existente o uno nuevo). |

Reglas útiles al subir **cotizaciones**:
- Una fila **sin precio (o con 0)** se omite sin error: es lo normal cuando el proveedor devuelve la ficha con huecos.
- El producto y el proveedor deben **existir antes** (créalos en las otras pestañas); si no, la fila da error y te lo dice.
- Una oferta subida **no reemplaza** la del portafolio: el ranking usa siempre el **menor precio de cada proveedor**.
  La revisión te avisa cuántas cotizaciones no cambiarán el ranking por eso.
- Si subes el mismo archivo otra vez, no se duplica nada: mismo precio = «sin cambios», precio distinto = «se actualiza».
- Si el mismo producto y proveedor aparecen dos veces en el archivo, se usa el más barato.
- `CANTIDAD_DISPONIBLE` debe ser un número (0 o más): si no, esa fila da error. Vacía = el proveedor no dijo cuánto tiene.

### Qué se conserva y qué no

| Origen | Cómo entró | ¿Se puede eliminar? | ¿Sobrevive a «Actualizar Excel»? |
|---|---|---|---|
| Excel base | Las 5 tablas de «Administración» (subidas desde «Actualizar Excel») | **Sí**, en Administración | Solo si no las **reemplazas** (con «Agregar y actualizar» se conservan) |
| A mano | Formularios | Sí | **Sí** |
| Subido | «Cargar datos» | Sí | **Sí** |

Si **cambias** un producto o proveedor del Excel base con los formularios de «Cargar datos», pasa a ser tuyo y el cambio se conserva. Lo que editas
directamente en las tablas de Administración queda en esas tablas hasta que las reemplaces desde un Excel. **No hace falta instalar nada nuevo**: la
carga de archivos no usa librerías adicionales, y una base de datos creada con la versión anterior se actualiza sola.

## Administración: las 5 tablas de los Excel

El menú **«Administración»** abre una pantalla con una pestaña por Excel. Las columnas se llaman **exactamente** como en el Excel y
las filas están **tal cual venían** (incluidos los códigos repetidos, los proveedores sin nombre o las filas sin precio):

| Pestaña | Excel | Columnas |
|---|---|---|
| Stock | `05-STOCK.xlsx` | `COD_PRODUCTO` · `DESCRIPCION` · `StockMax` · `StockMed` · `StockMin` |
| Existencias | `06-EXISTENCIAS.xlsx` | `COD_PRODUCTO` · `DESCRIPCION` · `CANTIDAD` |
| Empresas | `EMPRESA.xlsx` | `CODIGO_EMPRESA` · `NOMBRE` · `TELEFONO` · `CORREO` (estos dos **no vienen en el Excel**: se escriben aquí) |
| Ficha de cotización | `FICHA_COTIZACION.xlsx` | `COD_SALUDIPS` · `DESCRIPCION` · `TIPO_INSUMO` |
| Portafolio | `PORTAFOLIO.xlsx` | `COD_EMPRESA` · `COD_PRODUCTO` · `DESCRIPCION` · `VALOR` · `PRESENTACION` |

- **Ver y buscar:** la búsqueda ignora tildes y mayúsculas; clic en un encabezado ordena (las columnas numéricas ordenan como números, las celdas vacías van al final). Se pagina de 50 en 50 (el portafolio tiene más de 7.000 filas).
- **Editar:** doble clic en una fila (o el lápiz) → escribes → **Enter** guarda, **Esc** cancela. Si un valor no es válido (por ejemplo texto en `StockMax`) te dice cuál y no cierra la edición. Las celdas que no tocas se guardan exactamente como estaban.
- **Agregar:** «Agregar fila» abre un formulario con un campo por columna (los `*` son obligatorios). Los números se aceptan como `1.234,50`.
- **Empresas: teléfono y correo obligatorios.** Al agregar o editar una empresa hay que escribir su teléfono (7 a 15 dígitos; un celular de 10 dígitos que
  empieza por 3 se guarda como `+57…`) y un correo válido. Las empresas que vienen del Excel `EMPRESA` no los traen: al editar una, se piden. **Importar el
  Excel no los borra**: «reemplazar» conserva el teléfono y el correo de cada empresa que ya los tenía, y un archivo con esas columnas vacías tampoco los pisa.
- **Portafolio: el nombre de la empresa.** Junto a `COD_EMPRESA` aparece la columna **NOMBRE DE LA EMPRESA** (solo lectura, no va en el Excel): se puede
  **buscar** y **ordenar** por ella.
- **Eliminar:** una fila o varias (casillas; «Seleccionar las N filas del filtro» marca también las de otras páginas). **Siempre se permite**, pero antes se te explica qué pasará; lo que quede huérfano aparece en «Avisos de datos».
- **Recalculo:** después de cada cambio, el tablero se recalcula solo (≈0,1 s con miles de productos).
- **Descargar Excel:** baja la tabla con los mismos encabezados y el nombre de archivo original.
- **Historial:** cada cambio queda anotado (se recuerdan los últimos 300 y las copias de las últimas 5 importaciones) y tiene su botón **«Deshacer»**.
- **Avisos:** los botones «Ir a corregir» del panel de avisos abren la pestaña con solo las filas del problema. Mientras corriges, el filtro se mantiene; cuando el aviso desaparece, la pantalla te lo dice y muestra todas las filas.

### Si el correo dice «no está configurado»

La ventana de la clave temporal dice en la línea «Correo:» qué pasó **y dónde buscó** el archivo de configuración. Lo más común:
1. **No existe el `.env`** junto a `run.py`: pasa al reemplazar la carpeta del proyecto por una versión nueva (el zip no trae tu `.env`, a propósito: lleva tus claves). Cópialo de la carpeta anterior, o copia `.env.ejemplo` como `.env` y escribe tus datos.
2. **Se llama `.env.txt`:** el Bloc de notas de Windows agrega `.txt` al nombre y el programa no lo encuentra. Debe llamarse exactamente `.env` (activa «Extensiones de nombre de archivo» en el Explorador para verlo). El mensaje lo detecta y lo dice.
3. Existe, pero **falta la línea `COMPRAS_SMTP_SERVIDOR=...`**.

No hace falta reiniciar: el archivo se vuelve a leer solo cuando cambia. Para probar sin crear usuarios: `python -m app.usuarios_cli probar-correo tu@correo.com`, que dice exactamente qué falla (clave de aplicación de Gmail, puerto bloqueado por la red, etc.).

### Los Excel con el formato oficial

La ficha FR-GDS-07 y la orden de compra salen de **plantillas livianas** en `app/plantillas/`. Abrir los originales en cada descarga era imposible
(`OC.xlsm` tarda ~40 s), así que `herramientas/preparar_plantillas.py` los abre **una sola vez** y deja versiones de unos 25 KB. Con ellas, con más de mil productos
a comprar, la ficha se arma en ~1 s, la **OC en ~0,2 s** y las **alternativas (9 hojas) en ~0,3 s**.

**Por qué es rápido:** `openpyxl` tarda casi un minuto en crear y combinar las ~60.000 celdas de una OC grande (su revisión de celdas combinadas crece al
cuadrado). Por eso solo arma el libro (hojas, anchos, encabezados, formatos) y las **filas de datos y las celdas combinadas se escriben ya armadas** y se
insertan en el archivo. Cada fórmula guarda además su **valor ya calculado**, así el archivo se ve bien aunque el visor no calcule (el celular, una vista
previa del correo). Las pruebas vigilan las reglas que Excel exige (filas sin repetir y en orden, estilos que existen, celdas combinadas sin pisarse) y que
LibreOffice recalcule exactamente lo mismo que se guardó.

| Cambio respecto de los originales | Por qué |
|---|---|
| Se quitaron las 7 hojas ocultas de la ficha | Eran datos internos de la Clínica que no deben llegar al proveedor, y ninguna fórmula las usaba |
| La ficha solo trae los productos por comprar (no los 2.304 de la plantilla) | Es lo mismo que ve el proveedor en la pantalla |
| La columna «cantidad solicitada» va vacía | El proveedor no ve cantidades |
| La OC es `.xlsx` y `DINAMICA` es una tabla calculada | Las macros estaban vacías y no se puede comprobar aquí cómo refresca Excel una tabla dinámica |
| El IVA de `ORDENES` queda vacío | Igual que en el `OC.xlsm` original |

**Necesita la librería Pillow** (está en `requirements.txt`): sin ella `openpyxl` descarta las imágenes y la ficha saldría sin sus dos logos, sin ningún error.
Si tu carpeta ya tenía un `.venv` de antes, `run.py` lo detecta al arrancar y lo completa; si prefieres hacerlo a mano: `.venv\Scripts\python -m pip install pillow`.

Si algún día cambia el formato (una versión nueva de la ficha, otra columna en la orden de compra), basta con volver a correr
`python herramientas/preparar_plantillas.py <ficha .xlsx> <OC .xlsm>` con los archivos nuevos.

### Datos repetidos

| Dónde | Qué no se puede repetir | Si ya venía repetido |
|---|---|---|
| Stock · Existencias · Ficha | el código del producto (sin importar mayúsculas: `a1` = `A1`; `0041` ≠ `41`) | se respeta; se puede editar todo menos cambiar el código a uno que ya exista |
| Empresas | el código (`05` = `5`) y el **nombre** (sin tildes ni mayúsculas) | ídem |
| Portafolio | la pareja **empresa + producto** | ídem: si ya venían repetidas siguen ahí (con su aviso) y se les puede cambiar el precio. Si es el **mismo archivo** el que repite la pareja, al «Agregar y actualizar» se queda la de **menor precio válido** (no la última) |
| Agregar oferta | una oferta de la misma empresa para el mismo producto: si la tiene **manual**, se actualiza su precio; si la tiene del **Excel base** o **subida**, se rechaza con un mensaje que dice qué hacer | — |
| Usuarios | usuario, **correo** y **celular** | un contacto repetido «de antes» no impide editar a la persona |

**Cómo se decide que dos nombres de empresa son el mismo (la regla de TODO el sistema):** se comparan **sin tildes, sin mayúsculas y sin espacios ni signos**. «Ñandú S.A.S.»,
«NANDU SAS» y «ñandu, s a s» son la misma empresa; «A.L.F.A. SAS» es «ALFA SAS». La misma regla vale para **todos los caminos por los que entra una empresa**:
el servicio de proveedores (crear y cambiar el nombre), «Agregar oferta» (si escribes un nombre que ya existe se usa ese proveedor, no se crea otro), Administración → Empresas
(que además se revisa contra las empresas creadas en la aplicación, porque esas no están en esa tabla), importar el Excel de empresas, «Cargar datos → Proveedores» y
«Cargar datos → Cotizaciones» (en una carpeta de OneDrive o a mano, igual). Los códigos de producto tampoco distinguen mayúsculas: `a1` es `A1`.

**Importar el Excel de empresas** es la excepción a «los archivos aceptan repetidos»: ahí **no se carga nada** si el archivo trae la misma empresa dos veces (por código o por nombre), si deja un
nombre que ya tiene otra empresa o si choca con una creada en la aplicación; el mensaje dice cuáles son. Las demás tablas (stock, portafolio...) siguen aceptando repetidos en la importación,
porque los Excel de la empresa suelen traerlos y salen en los avisos.

Importar un archivo (Administración → «Importar Excel…» o «Actualizar Excel») de las demás tablas **sí acepta** repetidos: es cargar datos tal cual, y lo raro sale en los avisos.
Una consecuencia a tener en cuenta: el perfil Prime ya no puede *cambiar el precio de una oferta del Excel base* agregando otra manual; para eso el administrador
la edita en Administración → Portafolio. «Deshacer» devuelve el estado anterior sin revisar repetidos.

Cómo se relacionan las dos capas de tablas: las **5 tablas de los Excel** son la fuente; de ellas se **calcula** todo lo que ve el tablero
(productos, proveedores, ofertas y avisos). Lo que creas en «Cargar datos» y «Agregar oferta» vive en una capa aparte y no se mezcla con esas 5 tablas.

## Seguridad y perfiles

Nadie entra sin usuario y clave. En el ingreso y en «Cambiar mi clave», cada campo de clave tiene un **ojo** que deja ver lo que se está escribiendo (y volver a ocultarlo; al limpiar el formulario queda oculta otra vez). Cada persona tiene **un perfil** que decide qué ve y qué puede hacer:

| Perfil | Qué ve | Qué puede hacer |
|---|---|---|
| **Administrador** (`admin`) | Todo el menú, incluidas **Administración** y **Usuarios** · también «Ofertas de proveedores» (revisa y aprueba lo que suben) y «Productos que necesitamos» (la pantalla del proveedor) | Todo: editar las 5 tablas, importar, gestionar usuarios, `/api/docs` |
| **Prime** | Todo el menú **excepto** Administración y Usuarios | Elegir proveedores, agregar/cargar datos, **Actualizar Excel**, exportar VALORES, ver avisos |
| **Consulta** | Solo el tablero de compras (sin avisos de datos) | Solo lectura: no edita ni descarga ningún Excel |
| **Externo** (proveedor) | Solo «Productos que necesitamos»: solo código y descripción, **sin precios ni cantidades** | Descarga la **ficha FR-GDS-07** (código y descripción, sin cantidades ni precios de nadie), escribe sus precios y **la sube él mismo**: queda **pendiente** hasta que el administrador la apruebe; ve el estado de sus fichas, nunca precios de otros |

- **Usuarios:** el administrador los crea, cambia su perfil, los desactiva, los elimina o **restablece su clave** (se genera una temporal que se muestra una sola vez). Un usuario nuevo o restablecido **debe cambiar la clave** en su primer ingreso. Siempre queda al menos un administrador activo y nadie puede cambiarse el perfil ni eliminarse a sí mismo. Un externo puede ligarse, si se quiere, a un proveedor (solo para nombrar su Excel). Al crear o editar un usuario, su **correo** y su **celular** son **obligatorios** (campos con asterisco rojo): a ellos se le envían el usuario y la clave temporal (ver «Enviar usuario y clave»). El `admin` inicial nace sin contacto; al editarlo se piden.
- **Claves:** de 8 a 128 caracteres, con letras y números, distintas del usuario. Se guardan con *scrypt* (nunca en texto).
- **Sesión:** dura 12 horas, vive en una cookie `HttpOnly` (la página no puede leerla). Tras **5 intentos fallidos** la cuenta se bloquea 5 minutos. Al cambiar el perfil, desactivar o restablecer la clave de alguien, sus sesiones se cierran.
- **Auditoría:** el historial de Administración anota **quién** hizo cada cambio.
- **Regla por defecto:** una ruta nueva sin permiso declarado queda **solo para el administrador** (`app/services/seguridad.py`, tabla `POLITICA`).
- **Protecciones:** comprobación de origen contra CSRF, cabeceras de seguridad (CSP `script-src 'self'`, `nosniff`, `X-Frame-Options: DENY`) y `Cache-Control: no-store` en la API.

Variables de entorno (opcionales):

| Variable | Para qué |
|---|---|
| `COMPRAS_ADMIN_CLAVE` | Clave inicial del `admin` en lugar de la temporal aleatoria (no obliga a cambiarla) |
| `COMPRAS_COOKIE_SEGURA=1` | Marca la cookie como `Secure`: úsalo si sirves la aplicación por **https** |
| `COMPRAS_HOST` | Por defecto `0.0.0.0`: **otros equipos de la red** pueden entrar con `http://<IP de este equipo>:8000` (hay inicio de sesión). Ponla en `127.0.0.1` para que solo funcione en este computador |

### Enviar usuario y clave por correo y WhatsApp

Al **crear un usuario** o **restablecer su clave**, la aplicación intenta enviarle su usuario y su clave temporal al **correo** y al **WhatsApp** que tenga registrados. El celular se escribe como `300 123 4567` (se le pone el +57) o con indicativo, `+1 415…`.
**Cada caso tiene su propio texto:** al **crear** una cuenta el mensaje dice «ya tienes acceso a SUMIPABON»; al **restablecer** una clave dice «se restableció tu clave de acceso» (con otro asunto en el correo) y pide avisar al administrador si la persona no esperaba el cambio. El saludo usa el **Nombre** que tenga guardado el usuario en ese momento: si lo corriges con el lápiz de «Usuarios», el siguiente correo ya sale con el nombre nuevo (editar el nombre no envía nada).

**El correo no muestra la IP:** lleva un botón **«Entrar a SUMIPABON»** (la dirección va dentro del botón) y, para los programas de correo que no muestran botones, una versión de texto simple que sí escribe la dirección. En **WhatsApp** el enlace tiene que verse completo para poder tocarlo; para que no se vea un número, ponle nombre al computador y usa `COMPRAS_URL_PUBLICA=http://sumipabon:8000` (si cambia la IP del equipo, el enlace sigue sirviendo).
**El enlace del mensaje siempre pide usuario y clave:** termina en `/?ingresar=1`. Al abrirlo, la página **cierra la sesión que hubiera en ese navegador** (por ejemplo, la del administrador) y muestra la pantalla de ingreso con el aviso «Ingresa con el usuario y la clave que te enviamos». Así nadie entra directo como otra persona, ni siquiera si el correo o el usuario son los mismos. Después de entrar, recargar la página no vuelve a cerrar la sesión.
La ventana de la clave temporal dice qué pasó con cada canal (enviado, falló o no configurado). Si falla el correo o WhatsApp, **el usuario se crea igual** y la clave se puede copiar de esa ventana. **Nada se envía hasta que configures los canales.

**Forma recomendada: el archivo `.env`** (no depende de Windows, de VS Code ni de reiniciar nada):

1. En la carpeta del proyecto, junto a `run.py`, copia la plantilla: `cp .env.ejemplo .env` (Git Bash) o `copy .env.ejemplo .env` (cmd).
2. Abre `.env` y escribe tus datos después de cada `=` (sin comillas ni espacios alrededor del `=`): servidor, usuario, clave de aplicación, remitente y `COMPRAS_URL_PUBLICA`.
3. **Prueba el correo** antes de crear usuarios, desde la carpeta del proyecto: `python -m app.usuarios_cli probar-correo tu@correo.com`. Dice qué archivo leyó y, si algo falla, por qué.
4. Guarda el cambio: el programa vuelve a leer `.env` solo cuando cambia; no hace falta reiniciarlo.

`.env` contiene tus claves: ya está en `.gitignore`, **no se sube a GitHub**; no lo compartas. Si una variable existe en el `.env` **y** en las variables de Windows, gana la de Windows. Las pruebas automáticas nunca leen tu `.env` ni envían mensajes reales.

Las mismas opciones se pueden dar como variables de entorno del sistema:

| Variable | Para qué |
|---|---|
| `COMPRAS_SMTP_SERVIDOR` | Servidor de correo, p. ej. `smtp.gmail.com` (sin esto no se envía correo) |
| `COMPRAS_SMTP_PUERTO` | `587` (por defecto, con STARTTLS) o `465` (SSL) |
| `COMPRAS_SMTP_USUARIO` · `COMPRAS_SMTP_CLAVE` | La cuenta que envía y su clave (en Gmail, una «clave de aplicación») |
| `COMPRAS_SMTP_REMITENTE` | Cómo aparece el remitente: `SUMIPABON <compras@clinica.com>` |
| `COMPRAS_WHATSAPP_TOKEN` · `COMPRAS_WHATSAPP_ID_NUMERO` | Token y «Phone number ID» de la **API oficial de WhatsApp Business (Cloud API de Meta)** |
| `COMPRAS_WHATSAPP_PLANTILLA` | Nombre de una **plantilla aprobada** por Meta con 4 variables: `{{1}}` nombre, `{{2}}` usuario, `{{3}}` clave temporal, `{{4}}` dirección |
| `COMPRAS_WHATSAPP_PLANTILLA_RESTABLECER` | (Opcional) Otra plantilla, con las mismas 4 variables, para cuando se **restablece** una clave. Si no la pones, se usa la de arriba (cuyo texto, al estar en Meta, no cambia por sí solo) |
| `COMPRAS_ENV` | Ruta de otro archivo de configuración en lugar de `.env` (las pruebas automáticas la usan para no leer el tuyo ni enviar mensajes reales) |
| `COMPRAS_URL_PUBLICA` | La dirección que se escribe en el mensaje (por defecto, la que usó el administrador, p. ej. `http://127.0.0.1:8000`: **ponla con la dirección real** que usarán los demás, como `http://192.168.1.20:8000`) |

```bash
# Windows (cmd), antes de python run.py:
set COMPRAS_SMTP_SERVIDOR=smtp.gmail.com
set COMPRAS_SMTP_USUARIO=compras@clinica.com
set COMPRAS_SMTP_CLAVE=la-clave-de-aplicacion
set COMPRAS_URL_PUBLICA=http://192.168.1.20:8000
```

> **WhatsApp exige pasos de tu lado:** no existe un envío gratuito y directo desde un programa. Hay que tener una cuenta de **WhatsApp Business Platform** (Meta) con un número verificado, y Meta solo deja escribirle a quien no te ha escrito antes usando una **plantilla aprobada** (sin plantilla, el mensaje de texto solo llega si la persona te escribió en las últimas 24 h). Mientras no lo configures, al crear el usuario aparece el botón **«Abrir WhatsApp con el mensaje»**: abre WhatsApp con el texto ya escrito y solo pulsas enviar.
>
> **Sobre la seguridad:** la clave que se envía es **temporal**: la persona debe cambiarla al entrar, y se guarda solo su huella (nunca en texto). Aun así, correo y WhatsApp no son canales cifrados de extremo a extremo para el correo: envía solo a correos de confianza. La clave nunca se escribe en registros ni en mensajes de error.

**Superusuario con clave fija** (un administrador que entra a **todo el sistema** con una clave que defines de antemano, sin pedirle cambiarla): escríbelo en tu archivo `.env`, junto a `run.py`:

```
COMPRAS_SUPERUSUARIO=superadmin
COMPRAS_SUPERUSUARIO_CLAVE=la-clave-que-elijas
```

Al arrancar (`python run.py`) el sistema lo **crea** si no existe y, si ya existe, lo **deja en regla**: perfil Administrador, activo, sin bloqueo y con esa clave. Así el `.env` manda: si alguien lo elimina, lo desactiva o le cambia la clave, al reiniciar vuelve a quedar como está escrito. La terminal solo avisa «Superusuario … creado/actualizado»; **nunca imprime la clave**.
En la pantalla «Usuarios» aparece marcado como *superusuario* y **sin botones**: no se puede editar, restablecer ni eliminar desde allí, y tampoco él puede cambiarse la clave desde la llave (se cambia en el `.env` y se reinicia). Si más adelante borras esas dos líneas del `.env`, queda como un administrador normal.
La clave sigue las reglas de siempre: 8 a 128 caracteres, con letras y números. Tu `.env` tiene esa clave en texto: ya está en `.gitignore`, **no lo subas a GitHub ni lo compartas**. Si el nombre ya lo usaba otro usuario, esa cuenta se convierte en el superusuario. El perfil Administrador no ve la pantalla del proveedor externo (es solo de ese perfil); todo lo demás sí.

**Crear otro administrador desde la terminal** (con la clave que tú elijas; sirve también si perdiste la del primer arranque). En SUMIPABON el «superusuario» es el perfil **Administrador**: puede todo. En una terminal, dentro de la carpeta del proyecto y con el entorno activado:

```bash
python -m app.usuarios_cli crear-admin maria      # también: crear-superusuario maria
```

Pide nombre, correo y celular (Enter para omitirlos) y la clave dos veces (**no se ve al escribirla**). La clave sigue las reglas de siempre (8 a 128 caracteres, con letras y números) y **no se le obliga a cambiarla**: ya la eligió quien la escribió. Si el usuario ya existe, no lo toca.

**Olvidé la clave del administrador:** en una terminal, dentro de la carpeta del proyecto:

```bash
python -m app.usuarios_cli listar
python -m app.usuarios_cli restablecer admin     # imprime una clave temporal nueva
```

> Con `COMPRAS_HOST` por defecto, la aplicación queda visible en la **red local** de la Clínica (Windows pedirá permiso en el firewall: acepta «Redes privadas»). Está pensada para esa red local. Si la vas a publicar en internet, hazlo detrás de **https**
> (con `COMPRAS_COOKIE_SEGURA=1`) y con un proxy que limite el acceso.

## Trabajar en Visual Studio Code

1. **Archivo → Abrir carpeta…** y elige esta carpeta. VS Code te propondrá instalar las extensiones recomendadas
   (Python, Pylance, Ruff, GitLens…): acepta.
2. Crea el entorno: `python -m venv .venv` y `pip install -r requirements-dev.txt`.
   Luego `Ctrl+Shift+P → Python: Select Interpreter` → `.venv`.
3. **F5** inicia la API con recarga automática y depuración (configuración *«Compras: iniciar API»*).
   Puedes poner puntos de parada en cualquier archivo de `app/`.
4. **Tests**: icono del matraz en la barra lateral, o `Ctrl+Shift+P → Tasks: Run Test Task`.
5. El código se formatea solo al guardar (Ruff). Revisión manual: `python -m ruff check .`

> El frontend son archivos estáticos (`frontend/`): editas, guardas y recargas el navegador; no hay que compilar nada.

## Trabajar con GitHub

```bash
git init -b main
git add .
git status            # comprueba que NO aparezcan data/excel/*.xlsx (están en .gitignore)
git commit -m "Primera versión: mesa de ofertas"

# crea un repositorio vacío en github.com (mejor PRIVADO) y luego:
git remote add origin https://github.com/TU_USUARIO/compras-mesa-de-ofertas.git
git push -u origin main
```

Con la CLI de GitHub, todo en un paso: `gh repo create compras-mesa-de-ofertas --private --source . --push`.

**Flujo de trabajo sugerido:** una rama por cambio (`git switch -c mejora-x`) → *Pull Request* → revisar →
*merge* a `main`. En VS Code puedes hacerlo con la extensión *GitHub Pull Requests*.

**Integración continua:** `.github/workflows/pruebas.yml` corre las pruebas y Ruff en cada `push` y *Pull Request*.

> ⚠️ **Los Excel no se suben a GitHub ni vienen en el ZIP** (`.gitignore`): tienen productos, existencias y precios de proveedores.
> Todas las pruebas usan **datos inventados**: no hace falta ningún Excel real para correrlas.

## Estructura

```
compras_app/
├── run.py                     # prepara el entorno, elige puerto libre, inicia el servidor y abre el navegador
├── iniciar.bat / iniciar.sh   # doble clic: solo llaman a run.py
├── .env.ejemplo               # plantilla de configuración: cópiala como `.env` y pon tus datos de correo/WhatsApp
├── .env                       # (lo creas tú) tus claves de envío: NO se sube a Git, no lo compartas
├── requirements.txt           # dependencias para ejecutar
├── requirements-dev.txt       # + pruebas y revisión de código
├── pyproject.toml             # configuración de Ruff y pytest
├── app/                       # BACKEND (FastAPI)
│   ├── main.py                #   arranque, rutas de las páginas, primera carga de los Excel (una sola vez)
│   ├── config.py              #   rutas y constantes
│   ├── database.py            #   SQLite: tablas y conexión
│   ├── schemas.py             #   validación de lo que llega a la API
│   ├── routers/               #   ENDPOINTS
│   │   ├── productos.py       #     listado, podio paginado, elegir proveedor, buscador, crear/editar/eliminar
│   │   ├── ofertas.py         #     agregar / eliminar ofertas propias (a mano o subidas)
│   │   ├── empresas.py        #     proveedores: lista, crear, renombrar, eliminar
│   │   ├── cargas.py          #     subir un Excel (revisar / cargar) y descargar plantillas
│   │   ├── admin.py           #     Administración: ver/editar/agregar/eliminar las 5 tablas, importar, historial
│   │   ├── sesion.py          #     ingresar, salir, quién soy, cambiar mi clave
│   │   ├── usuarios.py        #     (admin) crear, editar, desactivar, eliminar y restablecer clave
│   │   ├── proveedor.py       #     pantalla y Excel de cotización del proveedor externo (sin precios)
│   │   ├── pendientes.py      #     /api/pendientes: el administrador revisa, aprueba o rechaza lo que suben los proveedores
│   │   ├── control.py         #     /api/control: los tableros de control (empresas con menores valores, precios más baratos, productos que más consumen)
│   │   └── sistema.py         #     resumen, avisos (con «Ir a corregir»), importar todo, exportar VALORES y productos a comprar
│   ├── autorizacion.py        #   guardián global: sesión, perfil, CSRF y cambio de clave obligatorio
│   ├── usuarios_cli.py        #   `python -m app.usuarios_cli` (listar / restablecer clave / probar-correo / crear-admin)
│   └── services/              #   LÓGICA DE NEGOCIO (sin web)
│       ├── ranking.py         #     cantidad a comprar + orden de ofertas (funciones puras)
│       ├── tablero.py         #     junta productos + ofertas + elecciones + totales
│       ├── control.py         #     los tableros de control: ranking de empresas, precios más baratos y consumo (sobre los datos del tablero)
│       ├── excel_seguro.py    #     rechaza los .xlsx que pesan poco pero abiertos ocupan cientos de MB (bomba de compresión)
│       ├── tablas.py          #     las 5 tablas de los Excel: encabezados exactos, validar, buscar, importar/exportar Excel
│       ├── historial.py       #     historial de cambios y «Deshacer»
│       ├── admin.py           #     une escribir + historial + recalcular en una sola operación
│       ├── importador.py      #     importa Excel a las 5 tablas y RECALCULA productos/ofertas/avisos (conserva lo tuyo)
│       ├── cargas.py          #     carga de Excel desde la pantalla: validar, revisar, cargar
│       ├── catalogo.py        #     reglas de crear/editar/eliminar productos y proveedores
│       ├── seguridad.py       #     perfiles, claves (scrypt), usuarios, sesiones, bloqueo y tabla de permisos
│       ├── notificaciones.py  #     envía usuario y clave temporal por correo (SMTP) y WhatsApp (API de Meta)
│       ├── contacto.py        #     valida y da formato al teléfono y al correo de las empresas
│       ├── etiquetas.py       #     qué productos y empresas son «Nuevos» (la primera vez que el sistema los ve)
│       ├── pendientes.py     #     las fichas que suben los proveedores: quedan pendientes hasta que el administrador las aprueba o rechaza
│       ├── fichas.py          #     la ficha de una empresa: contacto, ofertas, cuánto se le compra
│       ├── plantillas.py      #     Excel en blanco para descargar (productos y proveedores)
│       ├── libros_excel.py    #     la ficha FR-GDS-07, la orden de compra y el libro de alternativas, con el formato oficial
│       ├── exportador.py      #     genera la OC, las alternativas, PRODUCTOS_A_COMPRAR.xlsx y la ficha del proveedor
│       └── normalizacion.py   #     limpieza de códigos, textos, números y encabezados
│   └── plantillas/            #   ficha_base.xlsx · oc_base.xlsx: los formatos oficiales, livianos y sin datos
├── herramientas/              # preparar_plantillas.py (la ficha y el OC livianos) · preparar_animacion.py (la escena de la ventana de espera): se usan a mano, una vez
├── frontend/                  # INTERFAZ (HTML + CSS + JS sin compilar)
│   ├── index.html             #   LA ÚNICA PÁGINA: barra + menú lateral + bienvenida + tablero + ventanas emergentes
│   ├── css/                   #   base.css · componentes.css · agregar.css · cargar.css · admin.css · seguridad.css · extras.css
│   ├── viaje/                 #   la animación de espera: escena.txt (SVG + estilos, no es una página) y doctor.webp (se generan con herramientas/preparar_animacion.py)
│   ├── fonts/                 #   Montserrat · Mulish · Poppins (las del sitio de la Clínica; funcionan sin internet)
│   ├── img/                   #   logo blanco, corazón e icono de la pestaña (los de la Clínica)
│   └── js/                    #   app.js · podio.js · graficos.js · control.js (tableros de control) · agregar.js · cargar.js · admin.js · sesion.js · usuarios.js · proveedor.js · empresa.js · viaje.js · api.js · util.js
│   │   ├── pendientes.js      #     ventana «Ofertas de proveedores» (administrador): lista, detalle, aprobar y rechazar
│   │   ├── listas.js          #     lista de productos con buscador y descarga («Sin oferta», «Nuevos»)
│   │   ├── alternativas.js    #     ventana «Alternativas 2.º a 4.º» (administrador y Prime)
├── data/
│   ├── excel/                 #   aquí van los 5 Excel (no se suben a Git)
│   └── compras.db             #   base local, se crea sola (no se sube a Git)
├── tests/                     # pytest: reglas, API, interfaz con navegador
│   ├── test_seguridad.py      #   perfiles × rutas, claves, sesiones, usuarios, Excel de Consulta y del proveedor
│   ├── test_notificaciones.py #   correo/celular, envío por correo y WhatsApp (siempre simulado), archivo .env
│   ├── test_repetidos_y_contacto.py   # sin repetidos en las 5 tablas, teléfono/correo de empresas, nombre en el portafolio
│   ├── test_cantidades_y_fichas.py    # cantidad editable, ficha de empresa, ofertas y usuarios sin repetir
│   ├── test_etiquetas_y_avisos.py     # etiquetas «Nuevo», «Stock suficiente» y aviso de compra menor a la recomendada
│   ├── test_libros_excel.py           # la ficha FR-GDS-07 (y subirla de vuelta), la orden de compra y las alternativas 2.º a 4.º
│   ├── test_ofertas_proveedor.py      # el proveedor sube su ficha (pendiente), el administrador la revisa y la aprueba o rechaza
│   ├── test_restaurar_ficha.py        # «Restaurar»: deshacer una aprobación o un rechazo (con sus protecciones)
│   ├── test_proveedor_nuevo.py        # un proveedor siempre va ligado a una empresa; si es nuevo se agrega al crear el usuario
│   ├── test_listas_alternativas_y_rechazo.py  # sin oferta y nuevos, alternativas que siguen a la elegida, rechazo con motivo y correo
│   └── e2e/                   #   la interfaz de verdad, con navegador (Playwright)
├── docs/GUIA_DEL_CODIGO.md    # guía para entender el código sin ser programador
├── .vscode/                   # depuración, tareas y ajustes compartidos
└── .github/workflows/         # pruebas automáticas en GitHub
```

## API

Todas las rutas (salvo `POST /api/sesion`) exigen sesión y se filtran por perfil; los permisos de cada una están en `POLITICA`.

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/api/resumen` | KPIs, conteos por filtro, inversión por proveedor |
| GET | `/api/control` | Tableros de control: empresas con menores valores, precios más baratos y productos que más consumen (`top`, `empresa`, `min_productos`, `precios`, `consumo`) |
| GET | `/api/productos` | Lista (`q`, `filtro`, `empresa`, `orden`, `pagina`, `tam`) |
| GET | `/api/productos/{cod}/ofertas?desde=0&limite=3` | Podio: 1.ª, 2.ª, 3.ª… `desde=3` da las siguientes |
| PUT/DELETE | `/api/productos/{cod}/seleccion` | Elegir (o quitar) un proveedor a mano |
| PUT/DELETE | `/api/productos/{cod}/cantidad` | Fijar a mano la cantidad a comprar `{cantidad}` (entero de 0 a 10.000.000) / volver a la calculada (administrador y Prime) |
| GET | `/api/empresas/{cod}/ficha` | La ficha de un proveedor: contacto, cifras y sus ofertas (administrador, Prime y Consulta) |
| GET | `/api/catalogo?q=` | Buscador de productos |
| GET | `/api/productos/{cod}` | Datos de un producto (y si es tuyo) |
| POST | `/api/productos` | Crear un producto a mano (409 si el código ya existe) |
| PUT | `/api/productos/{cod}` | Cambiar un producto (solo los campos enviados) |
| DELETE | `/api/productos/{cod}` | Eliminar un producto tuyo (los del Excel base dan 409) |
| POST | `/api/ofertas` | Agregar oferta manual (proveedor existente o nuevo) |
| DELETE | `/api/ofertas/{id}` | Eliminar una oferta tuya, a mano o subida (las del Excel base no se pueden borrar) |
| GET | `/api/empresas` | Proveedores |
| POST | `/api/empresas` | Crear un proveedor a mano (sin código se asigna uno) |
| PUT | `/api/empresas/{cod}` | Cambiar el nombre de un proveedor |
| DELETE | `/api/empresas/{cod}` | Eliminar un proveedor tuyo sin ofertas |
| POST | `/api/cargas/{tipo}?nombre=&aplicar=` | Subir un Excel/CSV de `productos`, `proveedores` o `cotizaciones`. `aplicar=false` solo revisa; `true` carga. El archivo va como cuerpo de la petición. Para cotizaciones sin proveedor en el archivo: `cod_empresa=` o `empresa_nueva=` |
| GET | `/api/plantillas/{tipo}` | Descarga la plantilla en blanco de ese tipo |
| GET | `/api/avisos` | Avisos de calidad de datos, cada uno con su `clave` estable y sus `destinos` («Ir a corregir») |
| POST | `/api/importar` | Reemplaza las 5 tablas con los Excel de `data/excel/` (conserva lo hecho a mano). La pantalla usa `/api/admin/importar` (carpeta) y `/api/admin/tablas/{tabla}/importar` (archivo subido: así sube los varios archivos, uno por tabla) |
| GET | `/api/admin/tablas` | Las 5 tablas: encabezados exactos y número de filas |
| GET | `/api/admin/tablas/{tabla}/filas` | Una página de filas (`q`, `orden`, `sentido`, `pagina`, `tam`). `aviso=<clave>&destino=<n>` = solo las filas de un aviso; `solo_ids=true` = los números de todas las que cumplen |
| POST | `/api/admin/tablas/{tabla}/filas` | Agregar una fila `{valores: {columna: valor}}` (valida y recalcula) |
| PUT | `/api/admin/tablas/{tabla}/filas/{id}` | Guardar los cambios de una fila |
| DELETE | `/api/admin/tablas/{tabla}/filas/{id}` | Eliminar una fila (siempre se permite) |
| POST | `/api/admin/tablas/{tabla}/filas/eliminar` | Eliminar varias filas juntas `{ids: [...]}` (un solo cambio en el historial) |
| GET | `/api/admin/tablas/{tabla}/filas/{id}/impacto` | Qué pasaría si se elimina (para avisar antes) |
| GET | `/api/admin/tablas/{tabla}/excel` | Descarga la tabla como Excel con los mismos encabezados |
| POST | `/api/admin/importar` | Importar Excel de la carpeta: `{tablas: [...], modo: "reemplazar" \| "agregar"}` |
| POST | `/api/admin/tablas/{tabla}/importar?nombre=&modo=` | Importar un Excel/CSV subido a una tabla (el archivo va como cuerpo) |
| GET | `/api/admin/historial` | Cambios recientes (`tabla=` para filtrar) |
| POST | `/api/admin/historial/{id}/deshacer` | Deshacer un cambio |
| GET | `/api/exportar/oc` | La orden de compra (`OC_<fecha>.xlsx`: VALORES, DINAMICA y ORDENES) con el proveedor ganador de cada producto (admin y Prime) |
| GET | `/api/exportar/alternativas` | El 2.º, 3.º y 4.º proveedor de cada producto, con las tres hojas de la OC por puesto: 9 hojas (`ALTERNATIVAS_2_a_4_<fecha>.xlsx`; admin y Prime) |
| POST | `/api/sesion` | Ingresar `{usuario, clave}` (pone la cookie; 5 fallos = bloqueo de 5 min, 429) |
| GET | `/api/sesion` | Quién soy (usuario, perfil, si debo cambiar la clave) |
| DELETE | `/api/sesion` | Salir |
| PUT | `/api/sesion/clave` | Cambiar mi clave `{actual, nueva}` |
| GET/POST | `/api/usuarios` | (admin) Listar (con los canales de envío configurados) / crear (`correo` y `celular` obligatorios; envía usuario y clave y devuelve el resultado en `envio`) |
| PUT/DELETE | `/api/usuarios/{id}` | (admin) Cambiar perfil, nombre o estado / eliminar |
| POST | `/api/usuarios/{id}/clave` | (admin) Restablecer la clave (devuelve una temporal y la reenvía por correo/WhatsApp) |
| GET | `/api/proveedor/productos` | (externo) Productos por comprar: solo código y descripción |
| POST | `/api/proveedor/ofertas` | (externo) sube su ficha con precios: queda **pendiente** de aprobación |
| GET | `/api/proveedor/lista/{grupo}` | (externo y admin) solo los `sin_oferta` o `nuevos` (código y descripción; `?q=`) |
| GET | `/api/proveedor/excel?grupo=&q=` | (externo y admin) la ficha reducida a los `sin_oferta` / `nuevos` y a la búsqueda |
| GET | `/api/proveedor/ofertas` | (externo) sus fichas enviadas y su estado (sin precios de nadie) |
| GET | `/api/pendientes` | (admin) las fichas de los proveedores; `?estado=pendiente\|aprobada\|rechazada` |
| GET | `/api/pendientes/{id}/excel` | (admin) la ficha de un proveedor como Excel |
| GET | `/api/pendientes/{id}` | (admin) una ficha con cada precio frente a la mejor oferta de hoy |
| POST | `/api/pendientes/{id}/restaurar` | (admin) deshace aprobar o rechazar: la ficha vuelve a «pendiente de revisión» (si estaba aprobada, devuelve también las ofertas) |
| POST | `/api/pendientes/{id}/aprobar` · `/rechazar` | (admin) sus precios pasan a competir y se le **avisa por correo al proveedor** · o no entran (`{"motivo": ...}` **obligatorio**: se envía al proveedor por correo) |
| GET | `/api/proveedor/excel` | (externo) la ficha FR-GDS-07 con los productos por comprar y los precios en blanco |
| GET | `/api/exportar/productos-a-comprar` | Descarga `PRODUCTOS_A_COMPRAR.xlsx` (admin y prime; Consulta ya no) |
| GET | `/api/docs` · `/api/openapi.json` | (admin) Documentación interactiva de la API |

## Pruebas

```bash
python -m pytest                 # 606 pruebas (559 sin navegador + 47 de interfaz)
python -m pytest tests/e2e       # solo interfaz (necesita: pip install playwright && playwright install chromium)
```

Con los Excel reales se verificó que las cantidades a comprar coinciden con las que calculaba Access
y que el «mejor precio» es siempre el mínimo del portafolio.

## Decisiones y supuestos

- **Cómo se leen los números:** una celda que en Excel es un **número** se toma tal cual (su punto es decimal). Un **texto** se interpreta a la colombiana: un punto con
  exactamente tres cifras detrás (`59.000`, `1.234`, `1.234.567`) separa **miles**; con otra cantidad (`12.5`, `100.25`) es decimal. También se entienden el «−» de Excel,
  los paréntesis contables `(100)` como negativo y la notación científica `1.5e3`. Excepción conocida: un texto «1.125» se lee como 1125, no como 1,125.
- **Un Excel que, abierto, ocupa más de 150 MB se rechaza** aunque pese poco (una «bomba de compresión» agotaría la memoria): ver `services/excel_seguro.py`.
- **Consumo estimado:** los tableros de control no tienen las salidas de bodega; «los productos que más consumen» se ordenan por lo que hay que reponer (stock máximo − existencias).
- **`VALOR` es precio por unidad** (igual que en `OC.xlsm`: `VR. TOTAL = VALOR × CANT. COMPRAR`). La presentación (X10, X100…) se muestra pero no divide el precio.
- **Cantidades enteras:** si `StockMax − Existencias` da decimales, se redondea hacia arriba.
- **Una cantidad editada manda sobre la calculada** y vive en su propia tabla (`cantidades`), como la elección de proveedor: dura hasta que se restaura. Al eliminar un producto propio se va con él.
- **«Nuevo» se decide con una tabla (`vistos`)** que anota cuándo se vio por primera vez cada producto y cada empresa; lo que existía al empezar a llevarla queda sin fecha (no es nuevo). La animación de espera es **pequeña** (360 px de ancho, también en el celular) y no ocupa la pantalla.
- **La animación de espera sigue a la petición real:** el doctor avanza mientras el servidor trabaja, nunca «llega» antes de que haya respuesta, y al llegar se cierra y muestra los datos (mínimo ~2 s; si el servidor tarda 4 s, dura ~6). Si hay un error, se cierra y el formulario sigue abierto. Con «reducir movimiento» activado en el sistema solo se ve el texto y la barra.
  La escena es la animación del **doctor que corre hasta la Clínica Pabón** (el edificio despierta, lo saluda y al llegar salen estrellitas). Llegó como una página completa que traía un script de Cloudflare y una imagen de ~800 KB metida en el texto; `herramientas/preparar_animacion.py` la convierte en una escena de ~30 KB (sin scripts ni llamadas externas: una prueba lo vigila) con el doctor aparte en `doctor.webp` (~34 KB). Si algún día cambia la animación: `python herramientas/preparar_animacion.py <página de animación .html>`.
- **Empate de precio:** gana el proveedor de menor código y ambos quedan marcados «Empate de precio».
- **Un proveedor cuenta una vez** por producto, con su precio más bajo (aunque tenga una oferta del Excel y otra manual).
- **Proveedor `05` = `5`**: se unifican los códigos con ceros a la izquierda. Los códigos de *producto* conservan sus ceros (`0041`).
- **Filas de portafolio sin precio o con precio 0** se ignoran (se informa cuántas en «Avisos»).
- **Códigos de producto repetidos** en `05-STOCK.xlsx` (p. ej. `A0001`): se usa la primera fila y se avisa.
- Los proveedores creados a mano o subidos sin código reciben códigos desde el **1000** para no chocar con los del Excel.
- **Lo tuyo gana:** un producto o proveedor que cambias (o subes) con «Cargar datos» y que también está en las tablas de los Excel se conserva al importar.
- **Los Excel se importan solo cuando lo pides** (por tabla, «reemplazar» o «agregar»); la primera carga es automática y única (marca `crudas_iniciadas` en la tabla `meta`).
- **Eliminar siempre se permite** en Administración: se avisa antes del efecto y lo huérfano queda en «Avisos» (proveedor sin registro, producto sin stock, elección de proveedor que ya no ofrece el producto).
- **Cada aviso tiene una `clave` estable** (`empresas_sin_nombre`, `stock_repetidos`…) para que el filtro «filas del aviso» siga valiendo mientras se corrige, aunque los avisos se recalculen.
- **Las tablas guardan los valores como texto, tal cual venían**; la limpieza (códigos `5929.0`, números con coma, `05` = `5`) ocurre al recalcular, así la tabla se ve igual que el Excel.
- **Subir es en dos pasos** (revisar y cargar) para que nada se guarde por sorpresa; las filas con error se omiten y se informan con su número de fila.
- **Subir no da permiso para borrar:** los productos y proveedores del Excel base solo se pueden cambiar, no eliminar, desde la pantalla.
- Los archivos se suben como cuerpo de la petición (sin formulario multipart), así no se necesita ninguna librería adicional.

## Ideas para seguir

- Generar la hoja `ORDENES` (un bloque por proveedor, con IVA) directamente desde la aplicación.
- Editar el precio de una oferta subida directamente desde su tarjeta (hoy se corrige subiendo el archivo otra vez).
- Inicio de sesión y usuarios, si va a usarse en red.
