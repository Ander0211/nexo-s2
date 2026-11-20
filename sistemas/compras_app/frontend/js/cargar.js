/*
 * PANEL «CARGAR DATOS»
 * ====================
 * Un panel emergente (el <dialog id="dlg-cargar"> de index.html) para meter datos de DOS maneras y para TRES cosas:
 *
 *   Dos maneras:   A) SUBIR UN EXCEL   ·   B) AGREGAR A MANO (formularios)
 *   Tres cosas:    Productos · Proveedores · Cotizaciones (las ofertas de precio de cada proveedor)
 *
 * Cada cosa tiene su pestaña. Subir un Excel funciona en DOS pasos, para que nada se cargue por sorpresa:
 *   1. Al elegir el archivo se REVISA solo: el servidor lo lee y cuenta qué pasaría (cuántos nuevos, cuántos se
 *      actualizan, cuáles tienen error) SIN guardar nada.
 *   2. Si todo está bien, el botón «Cargar N filas» lo guarda de verdad.
 *
 * Al cargar o guardar algo, avisa a la pantalla principal (con la función `alCambiar` que ella le entrega) para que se
 * actualice sola. Ya no es una ventana aparte: por eso no hay ventanas emergentes que el navegador pueda bloquear.
 *
 * Uso (desde app.js):   const cargar = montarCargar({ alCambiar, abrirAgregar });   cargar.abrir();
 * Orden del archivo: datos comunes → piezas de formulario → subir Excel → formularios manuales → pestañas → abrir y montar.
 */
import { api } from './api.js';
import { $, $$, el, icono, fmtNum, toast, parseValor } from './util.js';

// Valor especial del desplegable de proveedores que significa «Proveedor nuevo…».
const NUEVO = '__nuevo__';

// Datos de cada pestaña: su nombre, su icono y el texto que explica qué columnas espera el Excel.
// (Las columnas reales que reconoce el servidor están en app/services/cargas.py → COLUMNAS.)
const TIPOS = {
  productos: {
    titulo: 'Productos',
    icono: 'cesta',
    ayuda: () => el('p', { class: 'ayuda-columnas' },
      'Columnas: ', el('b', {}, 'COD_PRODUCTO'), ' (obligatoria) y ', el('b', {}, 'DESCRIPCION'),
      ' (obligatoria solo en productos nuevos) · opcionales: ', el('b', {}, 'STOCKMAX, STOCKMIN, EXISTENCIAS'),
      '. Si el producto ya existe, solo se cambian las columnas que traigan valor.'),
  },
  proveedores: {
    titulo: 'Proveedores',
    icono: 'trofeo',
    ayuda: () => el('p', { class: 'ayuda-columnas' },
      'Columnas: ', el('b', {}, 'NOMBRE'), ' (obligatoria) · opcional: ', el('b', {}, 'CODIGO_EMPRESA'),
      ' (si la dejas vacía se asigna un código automáticamente). Si el código ya existe, se cambia el nombre de ese proveedor.'),
  },
  cotizaciones: {
    titulo: 'Cotizaciones',
    icono: 'moneda',
    ayuda: () => el('p', { class: 'ayuda-columnas' },
      'Sube la ', el('b', {}, 'ficha de cotización FR-GDS-07'), ' que devolvió el proveedor: de cada producto se lee el ', el('b', {}, 'PRECIO'),
      ' (sin IVA) y la ', el('b', {}, 'unidad de empaque'), ', y el proveedor se reconoce solo (si no, elígelo abajo). ',
      'También sirve un Excel sencillo con las columnas ', el('b', {}, 'COD_PRODUCTO'), ' y ', el('b', {}, 'VALOR'), ' (obligatorias; el valor es por unidad) y ',
      el('b', {}, 'PRESENTACION'), ' (opcional); ahí el proveedor puede venir en el archivo (', el('b', {}, 'COD_EMPRESA'), ' o ', el('b', {}, 'EMPRESA'),
      ') o elegirse abajo. Las filas sin precio se omiten.'),
  },
};

let empresas = []; // lista de proveedores (para los desplegables)
const alCambiarEmpresas = []; // funciones que redibujan los desplegables cuando cambia la lista de proveedores
let dlg = null; // el <dialog> del panel
let alCambiar = () => {}; // función de la pantalla principal: «se cargó algo, actualízate» (la entrega app.js)
let irAAgregar = () => {}; // función de la pantalla principal: abrir el panel «Agregar oferta» (la entrega app.js)

/** Vuelve a pedir los proveedores y redibuja todos los desplegables (después de crear, renombrar o eliminar uno). */
async function recargarEmpresas() {
  empresas = await api.empresas();
  alCambiarEmpresas.forEach((redibujar) => redibujar());
}

/** Le avisa a la pantalla principal que se cargaron datos, para que se refresque sola. */
function avisarPrincipal(mensaje) {
  alCambiar(mensaje);
}

// ------------------------------------------------------------------ Piezas de formulario
/** Un campo de texto con su etiqueta encima. Devuelve {entrada, caja}: el <input> y el conjunto para insertar. */
function campo(etiqueta, atributos = {}) {
  const entrada = el('input', { autocomplete: 'off', 'aria-label': etiqueta, ...atributos });
  const caja = el('label', { class: 'grupo' }, el('span', { class: 'etiqueta-campo' }, etiqueta), el('div', { class: 'campo' }, entrada));
  return { entrada, caja };
}

/** Lee un número opcional de un campo: vacío → null; número válido (0 o más) → el número; otra cosa → lanza un Error. */
function leerNumero(entrada, nombre) {
  const texto = entrada.value.trim();
  if (texto === '') return null;
  const n = parseValor(texto);
  if (!Number.isFinite(n) || n < 0) throw new Error(`${nombre}: escribe un número válido (0 o más).`);
  return n;
}

/** Muestra u oculta un recuadro de mensaje (el rojo de error o la franja verde de «listo»). */
function mostrar(recuadro, texto) {
  recuadro.hidden = !texto;
  recuadro.replaceChildren(...(texto ? [texto] : []));
}

/** «1 fila» / «3 filas»: la palabra «fila» en singular o plural según la cantidad. */
const filas = (n) => `${fmtNum(n)} fila${n === 1 ? '' : 's'}`;

/** «120 KB» / «2,3 MB»: el tamaño de un archivo en palabras. */
function tamanoLegible(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`;
}

/** Un bloque con título «A · ...» o «B · ...» que agrupa una parte de la pestaña. */
function bloque(letra, titulo, contenido) {
  return el('section', { class: 'paso' }, el('h3', { class: 'titulo-bloque' }, el('i', {}, letra), titulo), contenido);
}

/**
 * El desplegable de proveedor de las cotizaciones («¿de quién es este archivo?»).
 *   ''      → usar el proveedor que trae el archivo (la hoja oculta de la ficha FR-GDS-07, o la columna COD_EMPRESA o EMPRESA)
 *   NUEVO   → proveedor nuevo: aparece una caja para escribir su nombre (se crea al cargar)
 *   código  → uno de los proveedores existentes
 * Devuelve {caja, valores()}; valores() da lo que se le envía al servidor: {cod_empresa} o {empresa_nueva} o {}.
 */
function selectorProveedor(alCambiar) {
  const lista = el('select', {
    'aria-label': 'Proveedor de la cotización',
    onchange: () => {
      cajaNuevo.hidden = lista.value !== NUEVO;
      if (lista.value === NUEVO) nuevo.focus();
      alCambiar();
    },
  });
  const nuevo = el('input', { placeholder: 'Nombre del proveedor nuevo', maxlength: '120', autocomplete: 'off', 'aria-label': 'Nombre del proveedor nuevo', onchange: alCambiar });
  const cajaNuevo = el('div', { class: 'campo', hidden: true }, nuevo);

  /** Llena el desplegable con los proveedores actuales, conservando lo que estaba elegido. */
  function pintar() {
    const previo = lista.value;
    lista.replaceChildren(
      el('option', { value: '' }, 'El archivo ya trae el proveedor en cada fila'),
      el('option', { value: NUEVO }, '＋ Proveedor nuevo…'),
      ...empresas.map((e) => el('option', { value: e.cod }, `${e.nombre} · ${e.cod}`)));
    if ([...lista.options].some((o) => o.value === previo)) lista.value = previo;
  }
  pintar();
  alCambiarEmpresas.push(pintar);

  const caja = el('div', { class: 'grupo' },
    el('span', { class: 'etiqueta-campo' }, '¿De qué proveedor es esta cotización?'),
    el('div', { class: 'campo' }, lista), cajaNuevo,
    el('p', { class: 'pista-campo' }, 'Elígelo solo si el archivo NO trae el proveedor en cada fila.'));

  return {
    caja,
    valores() {
      if (lista.value === NUEVO) return nuevo.value.trim() ? { empresa_nueva: nuevo.value.trim() } : {};
      return lista.value ? { cod_empresa: lista.value } : {};
    },
  };
}

// ------------------------------------------------------------------ A) Subir un Excel
/**
 * El bloque «Subir un Excel» de una pestaña. Estados por los que pasa:
 *   sin archivo → (eliges uno) → REVISANDO → resultado de la revisión → (pulsas «Cargar») → CARGANDO → «Listo»
 * `archivo` es el archivo elegido; `revision` es lo que respondió el servidor al revisarlo; `hecho`, el resultado
 * de la carga; `error`, un mensaje si algo falló; `ocupado`, «revisando» o «cargando» mientras se espera.
 */
function subidor(tipo) {
  const cfg = TIPOS[tipo];
  let archivo = null;
  let revision = null;
  let hecho = null;
  let error = '';
  let ocupado = '';
  let ticket = 0; // si eliges otro archivo mientras se revisa el anterior, la respuesta vieja se descarta
  const raiz = el('div', { class: 'subidor' });

  // Solo las cotizaciones necesitan elegir proveedor; si cambia, se vuelve a revisar el archivo.
  const selector = tipo === 'cotizaciones' ? selectorProveedor(() => { if (archivo) revisar(); }) : null;
  // Lo que se le envía al servidor: si es solo revisar o cargar, y el proveedor elegido (solo cotizaciones).
  const parametros = (aplicar) => ({ aplicar, ...(selector ? selector.valores() : {}) });

  // La zona de arrastrar: un <label> que envuelve el <input type=file> (oculto), así que un clic abre el explorador.
  const entrada = el('input', { type: 'file', accept: '.xlsx,.xlsm,.csv', class: 'oculto', 'aria-label': `Archivo de ${cfg.titulo.toLowerCase()}`, onchange: (ev) => elegirArchivo(ev.target.files[0]) });
  const zona = el('label', { class: 'zona' },
    icono('subir', 28), el('strong', {}, 'Arrastra aquí tu archivo'), el('span', {}, 'o haz clic para elegirlo · .xlsx, .xlsm o .csv'), entrada);
  ['dragenter', 'dragover'].forEach((n) => zona.addEventListener(n, (ev) => { ev.preventDefault(); zona.classList.add('sobre'); }));
  ['dragleave', 'drop'].forEach((n) => zona.addEventListener(n, (ev) => { ev.preventDefault(); zona.classList.remove('sobre'); }));
  zona.addEventListener('drop', (ev) => elegirArchivo(ev.dataTransfer.files[0]));

  /** Se eligió (o se soltó) un archivo: se guarda y se REVISA de inmediato. */
  function elegirArchivo(f) {
    if (!f) return;
    archivo = f; revision = null; hecho = null; error = '';
    revisar();
  }
  /** Quita el archivo y deja todo como al principio. */
  function quitar() {
    archivo = null; revision = null; error = ''; entrada.value = ''; // value='' permite volver a elegir el MISMO archivo
    pintar();
  }
  /** Paso 1: el servidor lee el archivo y cuenta qué pasaría (no guarda nada). */
  async function revisar() {
    const mio = ++ticket;
    ocupado = 'revisando'; error = ''; revision = null; pintar();
    let respuesta = null, mensaje = '';
    try { respuesta = await api.subirArchivo(tipo, archivo, parametros(false)); } catch (e) { mensaje = e.message; }
    if (mio !== ticket) return; // llegó tarde: ya se eligió otro archivo
    revision = respuesta; error = mensaje; ocupado = ''; pintar();
  }
  /** Paso 2: carga de verdad. Después avisa a la pantalla principal y refresca los desplegables de proveedores. */
  async function cargar() {
    ocupado = 'cargando'; error = ''; pintar();
    try {
      const r = await api.subirArchivo(tipo, archivo, parametros(true));
      hecho = r; archivo = null; revision = null; entrada.value = '';
      await recargarEmpresas(); // por si la carga creó proveedores nuevos
      avisarPrincipal(`Se cargó ${cfg.titulo.toLowerCase()} desde Excel: ${fmtNum(r.nuevos)} nuevos y ${fmtNum(r.actualizados)} actualizados.`);
    } catch (e) { error = e.message; }
    ocupado = ''; pintar();
  }

  /** Las casillas con los números de la revisión (nuevos, se actualizan, con error...). */
  function estadisticas(r) {
    // Una casilla con un número grande y su descripción debajo; `clase` la pinta de verde (ok) o rojo (mal).
    const casilla = (n, texto, clase = '') => el('div', { class: `stat ${clase}` }, el('strong', { class: 'num' }, fmtNum(n)), el('span', {}, texto));
    return el('div', { class: 'estadisticas' },
      casilla(r.filas, 'filas leídas'), casilla(r.nuevos, 'nuevos', 'ok'), casilla(r.actualizados, 'se actualizan', 'ok'),
      casilla(r.sin_cambios, 'sin cambios'),
      tipo === 'cotizaciones' && casilla(r.omitidas, 'sin precio (se omiten)'),
      casilla(r.total_errores, 'con error', r.total_errores ? 'mal' : ''));
  }
  /** Las notas explicativas bajo los números (proveedor nuevo, repetidas, cotizaciones que no cambian el ranking...). */
  function notas(r) {
    const lineas = [...r.avisos];
    if (r.repetidas) lineas.push(`${filas(r.repetidas)} repetida${r.repetidas === 1 ? '' : 's'} en el archivo: se usó la más barata de cada una.`);
    if (r.no_cambian_ranking) lineas.push(`${fmtNum(r.no_cambian_ranking)} cotizaciones no cambiarán el ranking: ese proveedor ya ofrecía ese producto igual o más barato en el portafolio.`);
    if (r.total_errores) lineas.push(r.total_errores === 1 ? 'La fila con error NO se cargará; las demás sí.' : `Las ${fmtNum(r.total_errores)} filas con error NO se cargarán; las demás sí.`);
    return lineas.length ? el('ul', { class: 'notas' }, lineas.map((l) => el('li', {}, l))) : null;
  }
  /** La tabla con las filas que tienen error: número de fila (el de Excel) y qué pasó. */
  function tablaErrores(r) {
    if (!r.errores.length) return null;
    const faltan = r.total_errores - r.errores.length;
    return el('div', { class: 'tabla-errores' }, el('table', {},
      el('thead', {}, el('tr', {}, el('th', {}, 'Fila'), el('th', {}, 'Qué pasó'))),
      el('tbody', {}, r.errores.map((e) => el('tr', {}, el('td', {}, e.fila), el('td', {}, e.motivo))),
        faltan > 0 && el('tr', {}, el('td', {}, '…'), el('td', {}, `y ${fmtNum(faltan)} filas más con error`)))));
  }

  /** Dibuja el bloque según el estado en que esté. */
  function pintar() {
    const partes = [cfg.ayuda(), el('div', { class: 'enlaces' },
      el('a', { class: 'btn btn-fantasma', href: `/api/plantillas/${tipo}`, download: '',
        title: tipo === 'cotizaciones' ? 'La ficha oficial FR-GDS-07 con los productos por comprar, sin datos de ningún proveedor' : 'Excel en blanco con los encabezados y las instrucciones' },
        icono('descargar', 15), tipo === 'cotizaciones' ? 'Descargar ficha FR-GDS-07' : 'Descargar plantilla'))];
    if (selector) partes.push(selector.caja);

    if (hecho) {
      // Resultado de la última carga (queda visible; la zona de abajo permite cargar otro archivo).
      partes.push(el('div', { class: 'banner-ok' }, icono('check', 20),
        el('span', {}, `Listo: ${fmtNum(hecho.nuevos)} nuevos y ${fmtNum(hecho.actualizados)} actualizados` +
          (hecho.total_errores ? `; ${filas(hecho.total_errores)} con error se ${hecho.total_errores === 1 ? 'omitió' : 'omitieron'}.` : '.'))));
    }
    if (!archivo) {
      partes.push(zona);
    } else {
      partes.push(el('div', { class: 'archivo-elegido' }, icono('archivo', 20),
        el('span', { class: 'nombre', title: archivo.name }, archivo.name), el('span', { class: 'peso' }, tamanoLegible(archivo.size)),
        el('button', { class: 'btn btn-fantasma', type: 'button', disabled: !!ocupado, onclick: quitar }, 'Quitar')));
      if (ocupado) {
        partes.push(el('div', { class: 'revisando' }, icono('refrescar', 18, 'spin'), ocupado === 'revisando' ? 'Revisando el archivo…' : 'Cargando…'));
      } else if (error) {
        partes.push(el('p', { class: 'error', role: 'alert' }, error));
      } else if (revision) {
        const aCargar = revision.nuevos + revision.actualizados; // «sin cambios» no hace falta cargarlos
        partes.push(estadisticas(revision), notas(revision), tablaErrores(revision),
          el('div', { class: 'acciones-carga' },
            el('button', { class: 'btn btn-primario', type: 'button', disabled: aCargar === 0, onclick: cargar },
              icono('subir', 16), aCargar ? `Cargar ${filas(aCargar)}` : 'No hay nada nuevo que cargar')));
      }
    }
    raiz.replaceChildren(...partes);
  }
  pintar();
  return raiz;
}

// ------------------------------------------------------------------ B) Agregar a mano: productos
/**
 * Formulario de producto. Escribir un código que YA EXISTE rellena el formulario con sus datos y cambia el modo a
 * «editar» (botón «Guardar cambios», y «Eliminar» si el producto es tuyo). Con un código nuevo, el modo es «crear».
 */
function formProducto() {
  let existente = null; // datos del producto si el código ya existe; null si es nuevo
  const cod = campo('Código del producto *', { placeholder: 'Ej. 0085', maxlength: '40' });
  const desc = campo('Descripción *', { placeholder: 'Nombre del producto', maxlength: '300' });
  const max = campo('Stock máximo', { inputmode: 'decimal', placeholder: 'Ej. 100' });
  const min = campo('Stock mínimo', { inputmode: 'decimal', placeholder: 'Ej. 20' });
  const exi = campo('Existencias', { inputmode: 'decimal', placeholder: 'Ej. 35' });
  const pista = el('p', { class: 'pista-campo' });
  const errorCaja = el('p', { class: 'error', role: 'alert', hidden: true });
  const okCaja = el('div', { class: 'banner-ok', hidden: true });
  const btnGuardar = el('button', { class: 'btn btn-primario', type: 'button', onclick: guardar }, 'Crear producto');
  const btnEliminar = el('button', { class: 'btn btn-peligro', type: 'button', hidden: true, onclick: eliminar }, icono('papelera', 15), 'Eliminar');

  /** Ajusta textos y botones según sea crear o editar (y si el producto se puede eliminar). */
  function pintarModo() {
    btnGuardar.textContent = existente ? 'Guardar cambios' : 'Crear producto';
    btnEliminar.hidden = !(existente && existente.es_propio);
    if (!existente) pista.textContent = 'Producto nuevo: se crea con estos datos. Sin stock máximo queda «sin stock definido» (no se compra).';
    else if (existente.es_propio) pista.textContent = 'Este producto ya existe y es tuyo: puedes cambiarlo o eliminarlo.';
    else pista.textContent = 'Este producto ya existe (viene del Excel base). Si lo cambias aquí, tu cambio se conserva al actualizar los Excel; no se puede eliminar.';
  }
  /** Al terminar de escribir el código: si ya existe, rellena el formulario con sus datos. */
  async function buscar() {
    mostrar(errorCaja, ''); mostrar(okCaja, '');
    const c = cod.entrada.value.trim();
    existente = null;
    if (c) {
      try {
        existente = await api.producto(c);
        desc.entrada.value = existente.descripcion;
        max.entrada.value = existente.stock_max ?? '';
        min.entrada.value = existente.stock_min ?? '';
        exi.entrada.value = existente.existencias ?? 0;
      } catch (e) { if (e.estado !== 404) mostrar(errorCaja, e.message); } // 404 = código nuevo: es lo normal
    }
    pintarModo();
  }
  /** Deja el formulario vacío, listo para el siguiente producto. */
  function limpiar() {
    [cod, desc, max, min, exi].forEach((c) => { c.entrada.value = ''; });
    existente = null; pintarModo(); cod.entrada.focus();
  }
  /** Crea el producto (código nuevo) o guarda los cambios (código existente). */
  async function guardar() {
    mostrar(errorCaja, ''); mostrar(okCaja, '');
    try {
      const c = cod.entrada.value.trim(), d = desc.entrada.value.trim();
      if (!c) throw new Error('Escribe el código del producto.');
      if (!d) throw new Error('Escribe la descripción del producto.');
      const cuerpo = {
        descripcion: d, stock_max: leerNumero(max.entrada, 'Stock máximo'), stock_min: leerNumero(min.entrada, 'Stock mínimo'),
        existencias: leerNumero(exi.entrada, 'Existencias') ?? 0,
      };
      btnGuardar.disabled = true;
      if (existente) {
        await api.editarProducto(c, cuerpo);
        mostrar(okCaja, `Producto ${c} actualizado.`);
        avisarPrincipal(`Producto ${c} actualizado.`);
        await buscar(); mostrar(okCaja, `Producto ${c} actualizado.`); // se vuelve a leer: pudo pasar a ser «tuyo»
      } else {
        await api.crearProducto({ cod: c, ...cuerpo });
        limpiar(); mostrar(okCaja, `Producto ${c} creado.`);
        avisarPrincipal(`Producto ${c} creado.`);
      }
    } catch (e) { mostrar(errorCaja, e.message); }
    btnGuardar.disabled = false;
  }
  /** Elimina el producto (pide confirmación; solo si es propio). */
  async function eliminar() {
    const c = cod.entrada.value.trim();
    if (!confirm(`¿Eliminar el producto ${c} y sus ofertas propias?`)) return;
    try {
      await api.eliminarProducto(c);
      limpiar(); mostrar(okCaja, `Producto ${c} eliminado.`);
      avisarPrincipal(`Producto ${c} eliminado.`);
    } catch (e) { mostrar(errorCaja, e.message); }
  }

  cod.entrada.addEventListener('change', buscar);
  pintarModo();
  return el('div', { class: 'formulario' }, cod.caja, desc.caja, el('div', { class: 'fila-campos' }, max.caja, min.caja, exi.caja),
    pista, errorCaja, okCaja, el('div', { class: 'acciones-carga' }, btnGuardar, btnEliminar));
}

// ------------------------------------------------------------------ B) Agregar a mano: proveedores
/**
 * Formulario de proveedor. El desplegable de arriba elige «＋ Proveedor nuevo» (crear) o uno existente (cambiarle el
 * nombre o eliminarlo). Solo se elimina un proveedor tuyo que no tenga ofertas.
 */
function formProveedor() {
  let actual = null; // el proveedor elegido en el desplegable; null = nuevo
  const lista = el('select', { 'aria-label': 'Proveedor', onchange: alElegir });
  const nombre = campo('Nombre del proveedor *', { placeholder: 'Ej. DROGUERÍA EJEMPLO SAS', maxlength: '120' });
  const codigo = campo('Código (opcional)', { placeholder: 'Si lo dejas vacío se asigna uno solo', maxlength: '20' });
  const pista = el('p', { class: 'pista-campo' });
  const errorCaja = el('p', { class: 'error', role: 'alert', hidden: true });
  const okCaja = el('div', { class: 'banner-ok', hidden: true });
  const btnGuardar = el('button', { class: 'btn btn-primario', type: 'button', onclick: guardar }, 'Crear proveedor');
  const btnEliminar = el('button', { class: 'btn btn-peligro', type: 'button', hidden: true, onclick: eliminar }, icono('papelera', 15), 'Eliminar');

  /** Llena el desplegable con los proveedores actuales, conservando lo que estaba elegido. */
  function pintarLista() {
    const previo = lista.value;
    lista.replaceChildren(el('option', { value: '' }, '＋ Proveedor nuevo'), ...empresas.map((e) => el('option', { value: e.cod }, `${e.nombre} · ${e.cod}`)));
    if ([...lista.options].some((o) => o.value === previo)) lista.value = previo;
    actual = empresas.find((e) => e.cod === lista.value) || null;
    pintarModo();
  }
  /** Ajusta textos y botones según sea crear o editar, y si el proveedor se puede eliminar. */
  function pintarModo() {
    codigo.caja.hidden = !!actual;
    btnGuardar.textContent = actual ? 'Guardar nombre' : 'Crear proveedor';
    const propio = actual && ['manual', 'subido'].includes(actual.origen);
    btnEliminar.hidden = !propio;
    btnEliminar.disabled = !!(propio && actual.ofertas > 0);
    if (!actual) pista.textContent = 'Proveedor nuevo: se crea con este nombre.';
    else if (!propio) pista.textContent = 'Viene de los Excel base: puedes cambiarle el nombre (el cambio se conserva), pero no eliminarlo.';
    else if (actual.ofertas > 0) pista.textContent = `Tiene ${actual.ofertas} oferta${actual.ofertas === 1 ? '' : 's'}: elimínalas primero para poder eliminar el proveedor.`;
    else pista.textContent = 'Este proveedor es tuyo y no tiene ofertas: puedes cambiarle el nombre o eliminarlo.';
  }
  /** El usuario eligió otro proveedor en el desplegable: se rellena (o se vacía) el nombre. */
  function alElegir() {
    mostrar(errorCaja, ''); mostrar(okCaja, '');
    actual = empresas.find((e) => e.cod === lista.value) || null;
    nombre.entrada.value = actual ? actual.nombre : '';
    codigo.entrada.value = '';
    pintarModo();
  }
  /** Deja el formulario en «proveedor nuevo», vacío. */
  function limpiar() {
    lista.value = ''; alElegir();
  }
  /** Crea el proveedor o guarda el nuevo nombre. */
  async function guardar() {
    mostrar(errorCaja, ''); mostrar(okCaja, '');
    const n = nombre.entrada.value.trim();
    if (n.length < 2) { mostrar(errorCaja, 'Escribe el nombre del proveedor (mínimo 2 letras).'); return; }
    btnGuardar.disabled = true;
    try {
      if (actual) {
        await api.editarEmpresa(actual.cod, { nombre: n });
        await recargarEmpresas();
        mostrar(okCaja, `Nombre actualizado: ${n}.`);
        avisarPrincipal(`Proveedor «${n}» actualizado.`);
      } else {
        const creado = await api.crearEmpresa({ nombre: n, cod: codigo.entrada.value.trim() || null });
        await recargarEmpresas();
        limpiar(); mostrar(okCaja, `Proveedor «${creado.nombre}» creado con el código ${creado.cod}.`);
        avisarPrincipal(`Proveedor «${creado.nombre}» creado.`);
      }
    } catch (e) { mostrar(errorCaja, e.message); }
    btnGuardar.disabled = false;
  }
  /** Elimina el proveedor (pide confirmación; el servidor exige que sea tuyo y no tenga ofertas). */
  async function eliminar() {
    if (!confirm(`¿Eliminar el proveedor «${actual.nombre}»?\n\nSe borra TODO lo suyo: sus ofertas, los productos donde se había elegido a mano y sus ofertas de «Adicionales». En cada producto, el tablero elegirá la siguiente oferta más baja de otro proveedor.`)) return;
    try {
      const n = actual.nombre;
      await api.eliminarEmpresa(actual.cod);
      await recargarEmpresas();
      limpiar(); mostrar(okCaja, `Proveedor «${n}» eliminado.`);
      avisarPrincipal(`Proveedor «${n}» eliminado.`);
    } catch (e) { mostrar(errorCaja, e.message); }
  }

  pintarLista();
  alCambiarEmpresas.push(pintarLista);
  return el('div', { class: 'formulario' },
    el('label', { class: 'grupo' }, el('span', { class: 'etiqueta-campo' }, 'Proveedor'), el('div', { class: 'campo' }, lista)),
    nombre.caja, codigo.caja, pista, errorCaja, okCaja, el('div', { class: 'acciones-carga' }, btnGuardar, btnEliminar));
}

// ------------------------------------------------------------------ B) Agregar a mano: cotizaciones
/** Las cotizaciones a mano ya tienen su propio panel (con buscador de producto y vista previa del ranking). */
function cotizacionManual() {
  return el('div', { class: 'tarjeta-info' },
    el('span', {}, 'Para agregar UNA cotización a mano tienes un panel pensado para eso: buscas el producto, eliges el proveedor, escribes el precio y ves en qué puesto quedaría antes de guardar.'),
    // Se cierra este panel y se abre el de «Agregar oferta» (dos paneles a la vez no se mezclan bien).
    el('button', { class: 'btn btn-primario', type: 'button', onclick: () => { dlg.close(); irAAgregar(); } },
      icono('mas', 16), 'Abrir «Agregar oferta»'));
}

// ------------------------------------------------------------------ Pestañas y arranque
/** Dibuja las tres pestañas y muestra el panel de la elegida (los demás quedan ocultos). */
function armarPestanas() {
  const ids = Object.keys(TIPOS);
  const caja = $('#cg-pestanas');
  /** Muestra el panel de una pestaña y marca su botón como seleccionado. */
  function irA(id) {
    ids.forEach((i) => { $(`#panel-${i}`).hidden = i !== id; });
    $$('.pestana', caja).forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tipo === id)));
  }
  caja.replaceChildren(...ids.map((id) => el('button', {
    class: 'pestana', type: 'button', role: 'tab', 'data-tipo': id, 'aria-selected': 'false', onclick: () => irA(id),
  }, icono(TIPOS[id].icono, 15), TIPOS[id].titulo)));
  irA('productos');
}

/** Dibuja el contenido del panel desde cero: cada pestaña con su bloque A (subir Excel) y B (a mano). */
function construir() {
  alCambiarEmpresas.length = 0; // los desplegables viejos ya no existen: se olvidan
  $('#panel-productos').replaceChildren(
    bloque('A', 'Subir un Excel de productos', subidor('productos')),
    bloque('B', 'Agregar o cambiar un producto a mano', formProducto()));
  $('#panel-proveedores').replaceChildren(
    bloque('A', 'Subir un Excel de proveedores', subidor('proveedores')),
    bloque('B', 'Agregar o cambiar un proveedor a mano', formProveedor()));
  $('#panel-cotizaciones').replaceChildren(
    bloque('A', 'Subir un Excel de cotizaciones', subidor('cotizaciones')),
    bloque('B', 'Agregar una cotización a mano', cotizacionManual()));
  armarPestanas();
}

// ------------------------------------------------------------------ Abrir y montar
/**
 * Conecta el panel: busca el <dialog> en index.html. Se llama UNA vez al cargar la página.
 *   opciones.alCambiar(mensaje)  función de la pantalla principal; se llama cada vez que se carga o guarda algo
 *   opciones.abrirAgregar()      función de la pantalla principal que abre el panel «Agregar oferta»
 * Devuelve {abrir}, la función que abre el panel.
 */
export function montarCargar(opciones) {
  alCambiar = opciones.alCambiar;
  irAAgregar = opciones.abrirAgregar;
  dlg = $('#dlg-cargar');
  /** Abre el panel como nuevo: pide los proveedores al día y dibuja las pestañas desde cero (sin restos de la vez anterior). */
  async function abrir() {
    try { empresas = await api.empresas(); } catch (e) { toast(e.message, 'error'); }
    construir();
    if (!dlg.open) dlg.showModal();
  }
  return { abrir };
}
