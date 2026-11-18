/*
 * PANTALLA «ADMINISTRACIÓN»
 * =========================
 * Muestra las 5 tablas de los Excel (Stock, Existencias, Empresas, Ficha de cotización y Portafolio) con los MISMOS
 * encabezados que el Excel, para verlas, buscarlas, ordenarlas, editarlas, agregar filas y eliminarlas.
 *
 * Qué hay aquí, en orden:
 *   1. Estado de la pantalla (E) y utilidades
 *   2. Cargar y dibujar: pestañas, franja del aviso, barra de selección, tabla y paginación
 *   3. Editar una fila (en la misma tabla) · Agregar (ventana) · Eliminar (con aviso del impacto)
 *   4. Importar Excel (ventana) · Historial y «Deshacer» (ventana)
 *   5. montarAdmin(): conecta los botones y devuelve lo que necesita app.js
 *
 * Cada cambio lo valida y lo recalcula el servidor (app/services/admin.py); esta pantalla solo muestra el resultado y,
 * si algo no es válido, el mensaje que el servidor devuelve. Después de cada cambio llama a `alCambiar()` para que el
 * tablero de compras y el contador de avisos se pongan al día.
 */
import { api } from './api.js';
import { $, $$, el, icono, fmtNum, toast, debounce, rangoPaginas, confirmar } from './util.js';

// ------------------------------------------------------------------ 1. Estado y utilidades
const E = {
  tablas: [], // las 5 tablas: {clave, titulo, archivo, filas, columnas: [{nombre, numerica, obligatoria}]}
  clave: 'stock', // pestaña abierta
  q: '', // texto del buscador
  orden: null, // encabezado por el que se ordena (null = como está en el Excel)
  sentido: 'asc',
  pagina: 1,
  tam: 50, // filas por página
  aviso: null, // {clave, destino, titulo} mientras solo se muestran las filas de un aviso
  datos: null, // última respuesta de /api/admin/tablas/{t}/filas
  seleccion: new Set(), // números de fila marcados (valen entre páginas)
  editando: null, // número de la fila que se está editando
  resaltar: null, // número de la fila recién agregada (se resalta un momento)
  pedido: 0, // cuenta las consultas: si llega una respuesta vieja, se descarta
};
let alCambiar = () => {}; // avisa a app.js que hubo cambios (la pone montarAdmin)
let pendiente = null; // lo que pidió un aviso para cuando se abra la pantalla: {aviso} o {agregar}
let dlgFila, dlgImportar, dlgHistorial; // las ventanas (las conecta montarAdmin)

const tablaActual = () => E.tablas.find((t) => t.clave === E.clave) || E.tablas[0];
const pantallaVisible = () => !$('#vista-admin').hidden;

/** «2026-09-29 21:15:03» → «29/09 21:15» */
const fechaCorta = (f) => `${f.slice(8, 10)}/${f.slice(5, 7)} ${f.slice(11, 16)}`;

// ------------------------------------------------------------------ 2. Cargar y dibujar
/** Pide las 5 tablas (encabezados y cuántas filas tiene cada una) y dibuja las pestañas. */
async function cargarTablas() {
  try { E.tablas = await api.adminTablas(); } catch (e) { toast(e.message, 'error'); return; }
  pintarPestanas();
}

/** Las pestañas: una por tabla, con el número de filas. Cambiar de pestaña cambia la dirección (#admin/stock). */
function pintarPestanas() {
  $('#adm-pestanas').replaceChildren(...E.tablas.map((t) => el('button', {
    class: 'pestana', type: 'button', role: 'tab', 'aria-selected': String(t.clave === E.clave),
    onclick: () => { location.hash = `#admin/${t.clave}`; },
  }, t.titulo, el('span', { class: 'n' }, fmtNum(t.filas)))));
}

/** Vuelve la pantalla a cero para una tabla: sin búsqueda, orden, filtro de aviso, selección ni edición. */
function reiniciar(clave) {
  Object.assign(E, { clave, q: '', orden: null, sentido: 'asc', pagina: 1, aviso: null, editando: null, resaltar: null, datos: null });
  E.seleccion.clear();
  $('#adm-q').value = '';
}

/** Pide la página actual de filas al servidor y la dibuja. Si el aviso ya se corrigió (404), muestra todas las filas. */
async function cargarFilas() {
  const t = tablaActual(), n = ++E.pedido;
  const params = { q: E.q, orden: E.orden, sentido: E.sentido, pagina: E.pagina, tam: E.tam };
  if (E.aviso) Object.assign(params, { aviso: E.aviso.clave, destino: E.aviso.destino });
  let r;
  try { r = await api.adminFilas(t.clave, params); } catch (e) {
    if (E.aviso && e.estado === 404) { // el problema del aviso ya no existe: se corrigió
      E.aviso = null; E.pagina = 1;
      toast('¡Listo! Ese aviso ya no existe: el problema se corrigió.', 'ok', 6000);
      return cargarFilas();
    }
    toast(e.message, 'error'); return;
  }
  if (n !== E.pedido) return; // llegó tarde: ya se pidió otra cosa
  E.datos = r; E.pagina = r.pagina;
  pintar();
}

/** Redibuja todo lo que depende de los datos cargados. */
function pintar() {
  const t = tablaActual();
  $$('.pestana', $('#adm-pestanas')).forEach((b, i) => b.setAttribute('aria-selected', String(E.tablas[i].clave === E.clave)));
  $('#adm-excel').href = api.adminExcelUrl(t.clave);
  $('#adm-excel').title = `Descarga la tabla como ${t.archivo}, con los mismos encabezados`;
  pintarFiltro(); pintarSeleccion(); pintarTabla(); pintarPaginacion();
}

/** Franja azul «Mostrando 3 filas del aviso …  ·  Quitar filtro» (solo cuando se llegó desde un aviso). */
function pintarFiltro() {
  const caja = $('#adm-filtro');
  caja.hidden = !E.aviso;
  if (!E.aviso) { caja.replaceChildren(); return; }
  caja.replaceChildren(icono('alerta', 16),
    el('span', {}, 'Mostrando las ', el('b', {}, fmtNum(E.datos.total)), ` fila(s) del aviso «${E.aviso.titulo}»`),
    el('button', { type: 'button', onclick: () => { E.aviso = null; E.pagina = 1; E.seleccion.clear(); cargarFilas(); } }, 'Quitar filtro'));
}

/** Barra de selección: cuántas filas hay marcadas y atajos para marcar todas las del filtro o quitar la marca. */
function pintarSeleccion() {
  const n = E.seleccion.size, caja = $('#adm-seleccion'), total = E.datos?.total || 0;
  const boton = $('#adm-eliminar');
  boton.disabled = n === 0;
  boton.replaceChildren(icono('papelera', 16), n ? `Eliminar seleccionadas (${fmtNum(n)})` : 'Eliminar seleccionadas');
  caja.hidden = n === 0;
  if (!n) { caja.replaceChildren(); return; }
  const paginaCompleta = E.datos.filas.length && E.datos.filas.every((f) => E.seleccion.has(f.id));
  // OJO: replaceChildren convierte un `false` en el TEXTO «false» (a diferencia de el()), por eso se filtran los vacíos.
  caja.replaceChildren(...[
    el('span', {}, el('b', {}, fmtNum(n)), n === 1 ? ' fila seleccionada' : ' filas seleccionadas'),
    paginaCompleta && n < total && el('button', { type: 'button', onclick: seleccionarTodasDelFiltro }, `Seleccionar las ${fmtNum(total)} filas ${E.aviso || E.q ? 'del filtro' : 'de la tabla'}`),
    el('button', { type: 'button', onclick: () => { E.seleccion.clear(); pintarSeleccion(); pintarTabla(); } }, 'Quitar la selección'),
  ].filter(Boolean));
}

/** Marca TODAS las filas que cumplen el filtro actual (no solo las de esta página): el servidor da sus números. */
async function seleccionarTodasDelFiltro() {
  const params = { q: E.q, solo_ids: 'true' };
  if (E.aviso) Object.assign(params, { aviso: E.aviso.clave, destino: E.aviso.destino });
  try {
    const r = await api.adminFilas(tablaActual().clave, params);
    E.seleccion = new Set(r.ids);
    pintarSeleccion(); pintarTabla();
  } catch (e) { toast(e.message, 'error'); }
}

/** Ordena por un encabezado: primer clic ↑, segundo ↓, tercero vuelve al orden del Excel. */
function ordenarPor(columna) {
  if (E.orden !== columna) { E.orden = columna; E.sentido = 'asc'; }
  else if (E.sentido === 'asc') E.sentido = 'desc';
  else { E.orden = null; E.sentido = 'asc'; }
  E.pagina = 1;
  cargarFilas();
}

/**
 * Las columnas que se DIBUJAN: las de la tabla y, justo después de la que indican, las «extras» de solo lectura (por ejemplo el
 * NOMBRE DE LA EMPRESA junto a su código en el Portafolio). Una extra no se edita, no va en el Excel y se puede buscar y ordenar.
 * Devuelve [{ c }] para una columna normal y [{ x }] para una extra.
 */
function columnasVisibles(t) {
  return t.columnas.flatMap((c) => [{ c }, ...(t.extras || []).filter((x) => x.despues === c.nombre).map((x) => ({ x }))]);
}

/** La tabla: encabezados exactos del Excel (ordenables), una fila por registro, y los botones de cada fila. */
function pintarTabla() {
  const t = tablaActual(), d = E.datos, tabla = $('#adm-tabla');
  const paginaCompleta = d.filas.length > 0 && d.filas.every((f) => E.seleccion.has(f.id));
  const marcarPagina = (ev) => {
    d.filas.forEach((f) => (ev.target.checked ? E.seleccion.add(f.id) : E.seleccion.delete(f.id)));
    pintarSeleccion(); pintarTabla();
  };
  const cabecera = el('tr', {},
    el('th', { class: 'c-sel' }, el('input', { type: 'checkbox', checked: paginaCompleta, 'aria-label': 'Seleccionar las filas de esta página', onchange: marcarPagina })),
    el('th', { class: 'c-num', title: 'Número de fila (no es una columna del Excel)' }, '#'),
    columnasVisibles(t).map(({ c, x }) => {
      const nombre = c ? c.nombre : x.nombre;
      return el('th', {
        class: [c?.numerica && 'der', x && 'extra'].filter(Boolean).join(' '),
        title: x ? 'Solo lectura: se toma de la tabla Empresas (no es una columna del Excel)' : false,
        'aria-sort': E.orden === nombre ? (E.sentido === 'desc' ? 'descending' : 'ascending') : 'none',
      }, el('button', { class: 'orden-col', type: 'button', title: 'Ordenar por esta columna', onclick: () => ordenarPor(nombre) },
        c ? c.nombre : x.titulo, el('span', { class: 'flecha', 'aria-hidden': 'true' }, E.orden === nombre ? (E.sentido === 'desc' ? '▼' : '▲') : '')));
    }),
    el('th', { class: 'c-acc' }));

  let cuerpo;
  if (!d.filas.length) {
    const msg = E.aviso || E.q ? 'Ninguna fila coincide con lo que buscas.' : `${t.titulo} no tiene filas todavía. Usa «Agregar fila» o «Importar Excel…».`;
    cuerpo = el('tr', {}, el('td', { class: 'vacio-tabla', colspan: columnasVisibles(t).length + 3 }, msg));
  } else {
    cuerpo = d.filas.map((f) => (f.id === E.editando ? filaEdicion(f, t) : filaLectura(f, t)));
  }
  tabla.replaceChildren(el('thead', {}, cabecera), el('tbody', {}, cuerpo));
  if (E.resaltar) { // la fila recién agregada: se muestra y se resalta un momento
    $(`tr[data-id="${E.resaltar}"]`, tabla)?.scrollIntoView({ block: 'center' });
    E.resaltar = null;
  }
}

/** Una fila en modo lectura. Doble clic en una celda = editar esa fila. */
function filaLectura(f, t) {
  const marcada = E.seleccion.has(f.id);
  const alternar = (ev) => { if (ev.target.checked) E.seleccion.add(f.id); else E.seleccion.delete(f.id); pintarSeleccion(); pintarTabla(); };
  return el('tr', { 'data-id': f.id, class: [marcada && 'sel', f.id === E.resaltar && 'nueva'].filter(Boolean).join(' ') },
    el('td', { class: 'c-sel' }, el('input', { type: 'checkbox', checked: marcada, 'aria-label': `Seleccionar la fila ${f.id}`, onchange: alternar })),
    el('td', { class: 'c-num' }, f.id),
    columnasVisibles(t).map(({ c, x }) => {
      if (x) { // columna extra de solo lectura (nombre de la empresa)
        const n = f.extras?.[x.nombre];
        return el('td', { class: n ? 'extra' : 'extra vacia', title: n || 'No se encontró el nombre de esa empresa', ondblclick: () => empezarEdicion(f.id) }, n || '—');
      }
      const v = f.valores[c.nombre];
      const vacia = v == null;
      return el('td', {
        class: [c.numerica && 'der', vacia && 'vacia', vacia && (c.obligatoria || E.aviso) && 'falta'].filter(Boolean).join(' '),
        title: vacia ? 'Vacío' : v, ondblclick: () => empezarEdicion(f.id),
      }, vacia ? '—' : v);
    }),
    el('td', { class: 'c-acc' },
      el('button', { class: 'btn-icono', type: 'button', title: 'Editar esta fila', 'aria-label': `Editar la fila ${f.id}`, onclick: () => empezarEdicion(f.id) }, icono('editar', 15)),
      el('button', { class: 'btn-icono peligro', type: 'button', title: 'Eliminar esta fila', 'aria-label': `Eliminar la fila ${f.id}`, onclick: () => pedirEliminar([f.id]) }, icono('papelera', 15))));
}

/** Dibuja «Mostrando 1–50 de N filas» y los botones ‹ 1 2 3 … ›. */
function pintarPaginacion() {
  const r = E.datos, nav = $('#adm-pag');
  if (!r.total) { nav.replaceChildren(); return; }
  const ini = (r.pagina - 1) * r.tam + 1, fin = Math.min(r.total, r.pagina * r.tam);
  const ir = (p) => () => { E.pagina = p; cargarFilas(); $('#adm-tabla').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  nav.replaceChildren(...[
    el('span', { class: 'num' }, `Mostrando ${fmtNum(ini)}–${fmtNum(fin)} de ${fmtNum(r.total)} filas`),
    r.paginas > 1 && el('div', { class: 'pags' },
      el('button', { type: 'button', disabled: r.pagina === 1, onclick: ir(r.pagina - 1), 'aria-label': 'Página anterior' }, '‹'),
      rangoPaginas(r.pagina, r.paginas).map((p) => (p === '…' ? el('span', { class: 'pts' }, '…')
        : el('button', { type: 'button', 'aria-current': p === r.pagina ? 'page' : false, onclick: ir(p), class: 'num' }, fmtNum(p)))),
      el('button', { type: 'button', disabled: r.pagina === r.paginas, onclick: ir(r.pagina + 1), 'aria-label': 'Página siguiente' }, '›')),
  ].filter(Boolean));
}

/** Después de un cambio: cuentas de las pestañas, la tabla y el resto de la aplicación se ponen al día. */
async function alCambiarDatos() {
  await cargarTablas();
  await cargarFilas();
  alCambiar();
}

// ------------------------------------------------------------------ 3. Editar · Agregar · Eliminar
/** Convierte la fila en cajas de texto (una por columna). Enter guarda, Esc cancela. */
function empezarEdicion(id) {
  E.editando = id;
  pintarTabla();
  $(`tr[data-id="${id}"] input[data-col]`)?.focus();
}

/** La fila en modo edición: una caja de texto por columna, con ✓ guardar y ✕ cancelar. */
function filaEdicion(f, t) {
  const cajas = () => $$('input[data-col]', $(`tr[data-id="${f.id}"]`));
  const guardar = async () => {
    const valores = Object.fromEntries(cajas().map((i) => [i.dataset.col, i.value]));
    try {
      const r = await api.adminGuardar(t.clave, f.id, valores);
      E.editando = null;
      toast(r.cambio ? 'Fila guardada. Los datos se recalcularon.' : 'No había cambios que guardar.', r.cambio ? 'ok' : 'info');
      if (r.cambio) await alCambiarDatos(); else pintarTabla();
    } catch (e) { toast(e.message, 'error', 6000); } // no se cierra la edición: se puede corregir y volver a intentar
  };
  const cancelar = () => { E.editando = null; pintarTabla(); };
  const teclas = (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); guardar(); }
    else if (ev.key === 'Escape') { ev.preventDefault(); cancelar(); }
  };
  return el('tr', { 'data-id': f.id, class: 'editando' },
    el('td', { class: 'c-sel' }),
    el('td', { class: 'c-num' }, f.id),
    columnasVisibles(t).map(({ c, x }) => x ? el('td', { class: 'extra', title: 'Solo lectura' }, f.extras?.[x.nombre] || '—') : el('td', {}, el('input', {
      type: 'text', value: f.valores[c.nombre] ?? '', 'data-col': c.nombre, 'aria-label': c.nombre, autocomplete: 'off',
      inputmode: c.numerica ? 'decimal' : false, class: c.numerica ? 'der' : '', onkeydown: teclas,
    }))),
    el('td', { class: 'c-acc' },
      el('button', { class: 'btn-icono ok', type: 'button', title: 'Guardar (Enter)', 'aria-label': 'Guardar los cambios', onclick: guardar }, icono('check', 15)),
      el('button', { class: 'btn-icono', type: 'button', title: 'Cancelar (Esc)', 'aria-label': 'Cancelar la edición', onclick: cancelar }, icono('x', 15))));
}

/** Abre la ventana «Agregar fila» con un campo por columna. `iniciales` = valores ya puestos (los que sugiere un aviso). */
function abrirAgregar(iniciales = {}) {
  const t = tablaActual();
  $('#af-titulo').textContent = `Agregar a ${t.titulo}`;
  $('#af-sub').textContent = `Las columnas son las de ${t.archivo}${t.clave === 'empresas' ? ' (el teléfono y el correo se escriben aquí: no vienen en el Excel)' : ''}. Los campos con * son obligatorios.`;
  $('#af-campos').replaceChildren(...t.columnas.map((c) => el('div', { class: 'grupo' },
    el('label', { class: 'etiqueta-campo', for: `af-${c.nombre}` }, c.nombre, c.obligatoria && el('span', { class: 'req' }, ' *')),
    el('div', { class: 'campo' }, el('input', {
      id: `af-${c.nombre}`, type: 'text', 'data-col': c.nombre, value: iniciales[c.nombre] ?? '', autocomplete: 'off',
      inputmode: c.numerica ? 'decimal' : false, onkeydown: (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); guardarNueva(false); } },
    })))));
  $('#af-error').hidden = true;
  dlgFila.showModal();
  // El cursor va al primer campo que aún está vacío (si un aviso ya puso el código, se escribe lo que falta) o, si todos tienen algo, al primero.
  const cajas = $$('#af-campos input');
  (cajas.find((i) => !i.value) || cajas[0]).focus();
}

/** Guarda la fila nueva. `otra` = dejar la ventana abierta y vacía para agregar otra más. */
async function guardarNueva(otra) {
  const t = tablaActual();
  const valores = Object.fromEntries($$('#af-campos input').map((i) => [i.dataset.col, i.value]));
  const error = $('#af-error');
  try {
    const r = await api.adminCrear(t.clave, valores);
    error.hidden = true;
    toast(`Fila agregada a ${t.titulo} (n.º ${r.fila.id}). Los datos se recalcularon.`, 'ok');
    if (!E.aviso) { E.q = ''; $('#adm-q').value = ''; E.orden = null; E.pagina = 1e6; } // ir al final, donde quedó la fila nueva
    E.resaltar = r.fila.id;
    if (otra) $$('#af-campos input').forEach((i) => { i.value = ''; }); else dlgFila.close();
    await alCambiarDatos();
    if (otra) $('#af-campos input')?.focus();
  } catch (e) { error.textContent = e.message; error.hidden = false; }
}

/** Eliminar una o varias filas. Se PERMITE siempre, pero antes se explica qué pasará en el tablero. */
async function pedirEliminar(ids) {
  const t = tablaActual();
  let impacto = null;
  if (ids.length === 1) {
    try { impacto = (await api.adminImpacto(t.clave, ids[0])).mensaje; } catch (e) { toast(e.message, 'error'); return; }
  }
  const ok = await confirmar({
    titulo: ids.length === 1 ? '¿Eliminar esta fila?' : `¿Eliminar ${fmtNum(ids.length)} filas de ${t.titulo}?`,
    parrafos: [
      impacto || (ids.length > 1 ? 'Lo que quede sin par (por ejemplo ofertas de un proveedor eliminado) saldrá en los avisos de datos.' : null),
      'Podrás deshacerlo desde el Historial.',
    ],
    boton: 'Eliminar', peligro: true,
  });
  if (!ok) return;
  try {
    const r = await api.adminEliminar(t.clave, ids);
    ids.forEach((id) => E.seleccion.delete(id));
    toast(`${fmtNum(r.eliminadas)} fila(s) eliminada(s). Los datos se recalcularon. Puedes deshacerlo en el Historial.`, 'ok', 6000);
    await alCambiarDatos();
  } catch (e) { toast(e.message, 'error'); }
}

// ------------------------------------------------------------------ 4. Importar Excel
/** Una línea legible con lo que pasó con cada tabla importada. */
function lineaImportacion(r) {
  if (r.modo === 'reemplazar') return `${r.titulo}: reemplazada con las ${fmtNum(r.nuevos)} filas de ${r.archivo}.`;
  const partes = [`${fmtNum(r.nuevos)} nuevas`, `${fmtNum(r.actualizados)} actualizadas`, `${fmtNum(r.sin_cambios)} sin cambios`];
  if (r.ignoradas) partes.push(`${fmtNum(r.ignoradas)} sin código (ignoradas)`);
  return `${r.titulo}: ${partes.join(' · ')}.`;
}

/**
 * «LO QUE NECESITA EL SISTEMA»: una fila por Excel con su nombre, PARA QUÉ SIRVE, si es obligatorio u opcional y si ya está cargado (cuántas filas tiene).
 * Es lo que se le muestra a quien tiene que subir los archivos: así sabe cuáles son, por qué y cuáles faltan. Se vuelve a dibujar sola al importar.
 */
function dibujarChecklist(caja) {
  const faltan = E.tablas.filter((t) => t.necesaria && !t.filas);
  caja.classList.add('checklist');
  caja.replaceChildren(
    el('p', { class: `checklist-resumen ${faltan.length ? 'falta' : 'listo'}` }, faltan.length
      ? `Faltan ${faltan.length} Excel obligatorio(s): ${faltan.map((t) => t.titulo).join(', ')}.` : 'Ya está todo lo obligatorio.'),
    ...E.tablas.map((t) => el('div', { class: `checklist-fila ${t.filas ? 'ok' : t.necesaria ? 'falta' : 'opcional'}`, 'data-tabla': t.clave },
      icono(t.filas ? 'check' : t.necesaria ? 'alerta' : 'info', 18),
      el('div', { class: 'checklist-texto' }, el('strong', {}, t.archivo), el('span', { class: `checklist-etiqueta ${t.necesaria ? 'obligatorio' : 'opcional'}` }, t.necesaria ? 'Obligatorio' : 'Opcional'), el('small', {}, t.para_que)),
      el('span', { class: 'checklist-estado' }, t.filas ? `${fmtNum(t.filas)} filas` : 'Falta'))));
}
/** Dibuja la lista en `caja` (pide al servidor cuántas filas tiene cada Excel). */
async function pintarChecklist(caja) {
  try { await cargarTablas(); } catch (e) { caja.replaceChildren(el('p', { class: 'nota' }, `No se pudo revisar qué datos hay: ${e.message}`)); return; }
  dibujarChecklist(caja);
}

/** Abre «Importar Excel». `sugerida` = la tabla que se marca de entrada (sin ella, se marcan las 5). */
async function abrirImportar(sugerida) {
  if (!E.tablas.length) await cargarTablas();
  const modo = () => $('input[name="imp-modo"]:checked', dlgImportar).value;
  const marcadas = () => $$('input[data-tabla]:checked', dlgImportar).map((i) => i.dataset.tabla);

  const mostrarResultado = (resultados) => $('#imp-resultado').replaceChildren(
    el('h3', {}, 'Listo'), el('ul', {}, resultados.map((r) => el('li', {}, lineaImportacion(r)))),
    el('p', { class: 'nota' }, 'Cada importación quedó en el Historial: desde allí se puede deshacer.'));
  // Vuelve a escribir cuántas filas tiene cada tabla, sin cerrar la ventana.
  const actualizarConteos = () => $$('.imp-filas', dlgImportar).forEach((c) => {
    c.textContent = `${fmtNum(E.tablas.find((t) => t.clave === c.dataset.tabla).filas)} filas ahora`;
  });
  const terminar = async (resultados) => {
    mostrarResultado(resultados);
    toast('Importación lista. Los datos se recalcularon.', 'ok');
    await cargarTablas();
    actualizarConteos();
    $$('.checklist').forEach(dibujarChecklist); // la lista de lo que falta se pone al día en todas partes donde esté
    if (pantallaVisible()) { reiniciar(E.clave); await cargarFilas(); } // la pantalla de fondo muestra lo nuevo
    alCambiar();
  };

  const importarCarpeta = async () => {
    const claves = marcadas();
    if (!claves.length) { toast('Marca al menos una tabla.', 'aviso'); return; }
    if (modo() === 'reemplazar') {
      const ok = await confirmar({
        titulo: `¿Reemplazar ${claves.length === 1 ? 'esta tabla' : `estas ${claves.length} tablas`} con los Excel?`,
        parrafos: [`Se borra lo que hay hoy en ${claves.map((c) => E.tablas.find((t) => t.clave === c).titulo).join(', ')} (incluidas tus ediciones) y quedan solo las filas del Excel.`, 'Podrás deshacerlo desde el Historial.'],
        boton: 'Reemplazar', peligro: true,
      });
      if (!ok) return;
    }
    const b = $('#imp-carpeta');
    b.disabled = true;
    try { await terminar((await api.adminImportar(claves, modo())).tablas); } catch (e) { toast(e.message, 'error', 8000); } finally { b.disabled = false; }
  };

  const subirArchivo = async () => {
    const archivo = $('#imp-archivo').files[0], clave = $('#imp-destino').value;
    if (!archivo) { toast('Elige primero el archivo Excel.', 'aviso'); return; }
    if (modo() === 'reemplazar') {
      const ok = await confirmar({
        titulo: `¿Reemplazar ${E.tablas.find((t) => t.clave === clave).titulo} con «${archivo.name}»?`,
        parrafos: ['Se borra lo que hay hoy en esa tabla (incluidas tus ediciones).', 'Podrás deshacerlo desde el Historial.'], boton: 'Reemplazar', peligro: true,
      });
      if (!ok) return;
    }
    const b = $('#imp-subir');
    b.disabled = true;
    try { await terminar((await api.adminSubir(clave, archivo, modo())).tablas); $('#imp-archivo').value = ''; } catch (e) { toast(e.message, 'error', 8000); } finally { b.disabled = false; }
  };

  const opcion = (valor, titulo, texto, marcado) => el('label', { class: 'opcion' },
    el('input', { type: 'radio', name: 'imp-modo', value: valor, checked: marcado }), el('span', {}, el('b', {}, titulo), el('small', {}, texto)));

  // ---- Subir los Excel desde el computador, varios a la vez. A qué tabla va cada uno se reconoce por su NOMBRE (y se puede corregir).
  const claveDelNombre = (nombre) => {
    const n = nombre.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    if (n.includes('existencia')) return 'existencias';
    if (n.includes('stock')) return 'stock';
    if (n.includes('empresa')) return 'empresas';
    if (n.includes('ficha') || n.includes('cotiza')) return 'ficha';
    if (n.includes('portafolio')) return 'portafolio';
    return '';
  };
  let lote = []; // los archivos elegidos: [{ archivo, clave }]
  const pintarLote = () => {
    const sinTabla = lote.filter((x) => !x.clave).length;
    $('#imp-lote').replaceChildren(...lote.map((it) => el('div', { class: `imp-lote-fila${it.clave ? '' : ' sin-tabla'}` },
      el('span', { class: 'imp-lote-nombre', title: it.archivo.name }, it.archivo.name, el('small', {}, `${fmtNum(Math.round(it.archivo.size / 1024))} KB`)),
      el('select', { 'aria-label': `Tabla de ${it.archivo.name}`, onchange: (ev) => { it.clave = ev.target.value; pintarLote(); } },
        el('option', { value: '' }, '— elige la tabla —'), E.tablas.map((t) => el('option', { value: t.clave, selected: t.clave === it.clave }, t.titulo))),
      el('button', { class: 'btn-icono', type: 'button', title: 'Quitar este archivo', 'aria-label': `Quitar ${it.archivo.name}`, onclick: () => { lote = lote.filter((x) => x !== it); pintarLote(); } }, icono('x', 14)))));
    const usadas = new Set(lote.map((x) => x.clave).filter(Boolean));
    const faltan = E.tablas.filter((t) => !usadas.has(t.clave)).map((t) => t.titulo);
    $('#imp-lote-resumen').textContent = !lote.length ? '' : sinTabla ? `${sinTabla} archivo(s) sin tabla: elígela para poder subirlos.`
      : (faltan.length ? `Con estos archivos se llenan ${usadas.size} de las ${E.tablas.length} tablas. No incluiste: ${faltan.join(', ')}.` : 'Con estos archivos se llenan las 5 tablas.');
    $('#imp-subir-lote').disabled = !lote.length || sinTabla > 0;
  };
  const subirLote = async () => {
    if (modo() === 'reemplazar') {
      const titulos = [...new Set(lote.map((x) => E.tablas.find((t) => t.clave === x.clave).titulo))];
      const ok = await confirmar({
        titulo: `¿Reemplazar ${titulos.length === 1 ? 'esta tabla' : `estas ${titulos.length} tablas`} con los archivos que elegiste?`,
        parrafos: [`Se borra lo que hay hoy en ${titulos.join(', ')} (incluidas tus ediciones) y quedan solo las filas de los archivos.`, 'Podrás deshacerlo desde el Historial.'], boton: 'Reemplazar', peligro: true,
      });
      if (!ok) return;
    }
    const orden = (clave) => E.tablas.findIndex((t) => t.clave === clave);
    const pendientes = [...lote].sort((a, b) => orden(a.clave) - orden(b.clave)), resultados = [], fallidos = [], fallos = [];
    const boton = $('#imp-subir-lote'), texto = $('#imp-subir-lote-txt');
    boton.disabled = true;
    for (const [i, it] of pendientes.entries()) {
      texto.textContent = `Subiendo ${i + 1} de ${pendientes.length}…`;
      try { resultados.push(...(await api.adminSubir(it.clave, it.archivo, modo())).tablas); } catch (e) { fallidos.push(it); fallos.push(`${it.archivo.name}: ${e.message}`); }
    }
    texto.textContent = 'Subir e importar los archivos';
    lote = fallidos; // lo que se subió bien sale de la lista; lo que falló se queda para corregirlo y reintentar
    pintarLote();
    if (resultados.length) await terminar(resultados);
    if (fallos.length) {
      $('#imp-resultado').append(el('div', { class: 'imp-errores' }, el('h3', {}, 'No se pudieron subir'), el('ul', {}, fallos.map((f) => el('li', {}, f)))));
      toast(`${fallos.length} archivo(s) no se pudieron subir.`, 'error', 8000);
    }
  };

  const lista = el('div', { id: 'imp-checklist' });
  dibujarChecklist(lista);
  $('#imp-cuerpo').replaceChildren(
    el('p', { class: 'intro' }, 'Los Excel solo se importan cuando tú lo pides aquí. Lo que edites en Administración se queda hasta que tú decidas reemplazarlo.'),
    el('div', { class: 'opciones' },
      opcion('agregar', 'Agregar y actualizar', 'Suma las filas nuevas y actualiza las que ya existen (por código). No borra nada.', true),
      opcion('reemplazar', 'Reemplazar', 'La tabla queda igual que el Excel: se borra lo que había, con tus ediciones.', false)),
    el('section', { class: 'imp-bloque' }, el('h3', {}, 'Lo que necesita el sistema'), lista),
    el('section', { class: 'imp-bloque' },
      el('h3', {}, 'Sube tus Excel desde el computador'),
      el('p', { class: 'nota' }, 'Elige los 5 archivos juntos (stock, existencias, empresas, ficha de cotización y portafolio). El sistema reconoce a qué tabla va cada uno por su nombre y puedes corregirlo.'),
      Object.assign(el('input', { id: 'imp-archivos', type: 'file', accept: '.xlsx,.xlsm,.csv', 'aria-label': 'Archivos Excel', onchange: (ev) => {
        lote = [...lote, ...[...ev.target.files].map((a) => ({ archivo: a, clave: claveDelNombre(a.name) }))];
        ev.target.value = ''; // así se puede volver a elegir el mismo archivo
        pintarLote();
      } }), { multiple: true }),
      el('div', { id: 'imp-lote', class: 'imp-lote' }), el('p', { id: 'imp-lote-resumen', class: 'imp-resumen', 'aria-live': 'polite' }),
      el('button', { class: 'btn btn-primario', id: 'imp-subir-lote', type: 'button', disabled: true, onclick: subirLote }, icono('subir', 16), el('span', { id: 'imp-subir-lote-txt' }, 'Subir e importar los archivos'))),
    el('section', { class: 'imp-bloque' },
      el('h3', {}, 'O desde la carpeta data/excel (si copiaste allí los archivos)'),
      el('div', { class: 'imp-tablas' }, E.tablas.map((t) => el('label', { class: 'imp-fila' },
        el('input', { type: 'checkbox', 'data-tabla': t.clave, checked: !sugerida || sugerida === t.clave }),
        el('span', { class: 'imp-nombre' }, el('b', {}, t.titulo), el('small', {}, t.archivo)),
        el('span', { class: 'imp-filas', 'data-tabla': t.clave }, `${fmtNum(t.filas)} filas ahora`)))),
      el('button', { class: 'btn btn-primario', id: 'imp-carpeta', type: 'button', onclick: importarCarpeta }, icono('refrescar', 16), 'Importar las tablas marcadas')),
    el('section', { class: 'imp-bloque' },
      el('h3', {}, 'O sube un archivo a una sola tabla'),
      el('div', { class: 'imp-subir' },
        el('select', { id: 'imp-destino', 'aria-label': 'Tabla de destino' }, E.tablas.map((t) => el('option', { value: t.clave, selected: t.clave === (sugerida || E.clave) }, `${t.titulo} (${t.archivo})`))),
        el('input', { id: 'imp-archivo', type: 'file', accept: '.xlsx,.xlsm,.csv', 'aria-label': 'Archivo Excel' }),
        el('button', { class: 'btn btn-primario', id: 'imp-subir', type: 'button', onclick: subirArchivo }, icono('subir', 16), 'Subir e importar')),
      el('p', { class: 'nota' }, 'Los encabezados se reconocen aunque cambien tildes o mayúsculas (por ejemplo «stock max»). Máximo 25 MB.')),
    el('div', { id: 'imp-resultado', class: 'imp-resultado', 'aria-live': 'polite' }));
  dlgImportar.showModal();
}

// ------------------------------------------------------------------ Historial y Deshacer
/** Abre el historial de cambios. Cada uno tiene su botón «Deshacer». */
async function abrirHistorial(tabla = '') {
  if (!E.tablas.length) await cargarTablas();
  const cuerpo = $('#hist-cuerpo');
  let lista;
  try { lista = await api.adminHistorial(tabla || null); } catch (e) { toast(e.message, 'error'); return; }
  const deshacer = async (c, boton) => {
    // Deshacer una importación o una eliminación de varias filas cambia MUCHAS filas de golpe: primero se confirma.
    if (['importar', 'eliminar_varias'].includes(c.accion)) {
      const ok = await confirmar({
        titulo: '¿Deshacer este cambio?',
        parrafos: [c.resumen, 'La tabla vuelve a como estaba antes; lo que se haya cambiado en ella después de ese momento se pierde.'],
        boton: 'Deshacer', peligro: true,
      });
      if (!ok) return;
    }
    boton.disabled = true;
    try {
      await api.adminDeshacer(c.id);
      toast('Cambio deshecho. Los datos se recalcularon.', 'ok');
      if (pantallaVisible()) { await cargarTablas(); await cargarFilas(); }
      alCambiar();
      await abrirHistorial(tabla);
    } catch (e) { toast(e.message, 'error', 7000); boton.disabled = false; }
  };
  cuerpo.replaceChildren(
    el('div', { class: 'hist-filtro' }, el('label', {}, 'Tabla: ',
      el('select', { 'aria-label': 'Filtrar por tabla', onchange: (ev) => abrirHistorial(ev.target.value) },
        el('option', { value: '' }, 'Todas'), E.tablas.map((t) => el('option', { value: t.clave, selected: t.clave === tabla }, t.titulo))))),
    lista.length ? el('table', { class: 'hist-tabla' },
      el('thead', {}, el('tr', {}, ['Cuándo', 'Tabla', 'Qué pasó', ''].map((h) => el('th', {}, h)))),
      el('tbody', {}, lista.map((c) => {
        const boton = el('button', { class: 'btn btn-fantasma', type: 'button', onclick: (ev) => deshacer(c, ev.currentTarget) }, icono('deshacer', 15), 'Deshacer');
        return el('tr', { class: c.deshecho ? 'deshecho' : '' },
          el('td', { class: 'h-fecha' }, fechaCorta(c.fecha)),
          el('td', {}, el('span', { class: 'etq-tabla' }, E.tablas.find((t) => t.clave === c.tabla)?.titulo || c.tabla)),
          el('td', { class: 'h-texto', title: c.resumen }, c.resumen), // el resumen ya empieza con el verbo («Editó Stock A1 …»)
          el('td', { class: 'h-acc' }, c.se_puede ? boton : el('span', { class: 'nota' }, c.deshecho ? 'Deshecho' : 'Sin copia')));
      }))) : el('p', { class: 'vacio-hist' }, 'Todavía no hay cambios. Aquí aparecerá lo que agregues, edites, elimines o importes.'));
  if (!dlgHistorial.open) dlgHistorial.showModal();
}

// ------------------------------------------------------------------ 5. Conexión con la página
/**
 * Conecta la pantalla y sus ventanas. Devuelve lo que usa app.js:
 *   mostrar(clave)        entrar a la pantalla (o cambiar de pestaña): carga las tablas y las filas
 *   irA(destino, aviso)   ir al lugar de un aviso (tabla con las filas del problema, o «Agregar» con valores puestos)
 *   abrirImportar()       la ventana «Importar Excel» (la del menú «Actualizar Excel»)
 *   abrirHistorial()      la ventana de cambios
 */
export function montarAdmin(opciones) {
  alCambiar = opciones.alCambiar;
  dlgFila = $('#dlg-admin-fila'); dlgImportar = $('#dlg-importar'); dlgHistorial = $('#dlg-historial');

  $('#adm-q').addEventListener('input', debounce((ev) => { E.q = ev.target.value.trim(); E.pagina = 1; cargarFilas(); }, 250));
  $('#adm-agregar').addEventListener('click', () => abrirAgregar());
  $('#adm-eliminar').addEventListener('click', () => { if (E.seleccion.size) pedirEliminar([...E.seleccion]); });
  $('#adm-importar').addEventListener('click', () => abrirImportar(E.clave));
  $('#adm-historial').addEventListener('click', () => abrirHistorial());
  $('#af-guardar').addEventListener('click', () => guardarNueva(false));
  $('#af-otra').addEventListener('click', () => guardarNueva(true));

  /** Entra a la pantalla. Si un aviso dejó una petición pendiente, la aplica (filtro del aviso o formulario de agregar). */
  async function mostrar(clave) {
    const p = pendiente; pendiente = null;
    if (!E.tablas.length) await cargarTablas(); // la primera vez hay que conocer las tablas para saber cuál abrir
    const destino = E.tablas.some((t) => t.clave === clave) ? clave : E.clave;
    if (destino !== E.clave || p) reiniciar(destino); // otra pestaña, o llegada desde un aviso: se empieza limpio
    if (p?.aviso) E.aviso = p.aviso;
    pintarPestanas(); // la pestaña cambia YA, sin esperar al servidor
    await Promise.all([cargarTablas(), cargarFilas()]); // conteos y filas, en paralelo
    if (p?.agregar) abrirAgregar(p.agregar);
  }

  /** «Ir a corregir» de un aviso. `destino` viene de /api/avisos; `aviso` = {clave, titulo, posicion}. */
  function irA(destino, aviso) {
    pendiente = destino.cantidad != null
      ? { aviso: { clave: aviso.clave, destino: aviso.posicion, titulo: aviso.titulo } }
      : { agregar: destino.agregar || {} };
    const hash = `#admin/${destino.tabla}`;
    if (location.hash === hash) mostrar(destino.tabla); else location.hash = hash; // si ya se está ahí, no hay «cambio de dirección»
  }

  return { mostrar, irA, abrirImportar, abrirHistorial, pintarChecklist };
}
