/*
 * PANEL «AGREGAR OFERTA MANUAL»
 * =============================
 * Un panel emergente (el <dialog id="dlg-agregar"> de index.html) que se abre encima de la pantalla principal y permite:
 *   1. Elegir un producto (buscándolo, o ya viene elegido si se abrió desde el botón de una fila)
 *   2. Elegir un proveedor existente, o escribir uno nuevo
 *   3. Escribir el precio por unidad (y opcionalmente la presentación)
 *   → Mientras tanto muestra una VISTA PREVIA: en qué puesto quedaría la oferta.
 *   4. Guardar (y cerrar, o guardar y agregar otra)
 *
 * Al guardar, avisa a la pantalla principal (con la función `alGuardar` que ella le entrega) para que se actualice sola.
 * Ya no es una ventana aparte: por eso no hay ventanas emergentes que el navegador pueda bloquear.
 *
 * Uso (desde app.js):   const agregar = montarAgregar({ alGuardar });   agregar.abrir();   agregar.abrir('5728');
 * Orden del archivo: utilidades → producto → proveedor → vista previa → guardar → abrir y montar.
 */
import { api } from './api.js';
import { $, el, icono, fmtNum, fmtMoney, debounce, parseValor } from './util.js';

// Valor especial del desplegable de proveedores que significa «Proveedor nuevo…».
const NUEVO = '__nuevo__';
const E = {};   // elementos del panel (se llenan en montarAgregar); se usa E.valor, E.proveedor, etc.
let dlg = null;           // el <dialog> del panel
let producto = null;      // respuesta de /api/productos/{cod}/ofertas (con todas las ofertas)
let empresas = [];        // lista de proveedores para el desplegable
let alGuardar = () => {}; // función de la pantalla principal que se llama al guardar (la entrega app.js)

// (El número escrito por una persona se convierte con parseValor, que vive en util.js porque también la usa cargar.js.)

// Atajos para leer el estado del formulario:
const codEmpresa = () => (E.proveedor.value && E.proveedor.value !== NUEVO ? E.proveedor.value : null); // proveedor existente elegido
const esNuevo = () => E.proveedor.value === NUEVO; // ¿eligió «Proveedor nuevo…»?
// Nombre del proveedor elegido: el que se escribió (si es nuevo) o el del desplegable.
const nombreElegido = () => (esNuevo() ? E.nuevo.value.trim() : empresas.find((x) => x.cod === E.proveedor.value)?.nombre || '');
const valorActual = () => parseValor(E.valor.value); // precio escrito, ya convertido a número

/** Muestra (o esconde, si va vacío) el recuadro rojo de error. */
function mostrarError(msg) { E.error.hidden = !msg; E.error.textContent = msg || ''; }

// ------------------------------------------------------------------ Producto
/** Carga el producto elegido (con TODAS sus ofertas, hasta 50) y actualiza el formulario. */
async function elegirProducto(cod) {
  mostrarError('');
  try {
    producto = await api.ofertas(cod, 0, 50);
  } catch (e) { mostrarError(e.message); producto = null; }
  E.resultados.hidden = true;
  pintarFicha();
  pintarOpcionesProveedor();
  actualizar();
}

/** La ficha del producto elegido: código, descripción, cuánto comprar, stock y mejor oferta de hoy. */
function pintarFicha() {
  if (!producto) { E.ficha.hidden = true; E.buscarCaja.hidden = false; return; } // sin producto: se ve el buscador
  const mejor = producto.ofertas[0];
  E.buscarCaja.hidden = true; E.ficha.hidden = false;
  E.ficha.replaceChildren(
    el('div', { class: 'ficha-cab' },
      el('div', { style: 'min-width:0' }, el('span', { class: 'cod' }, producto.cod), el('div', { class: 'desc', style: 'font-weight:650' }, producto.descripcion)),
      el('button', { class: 'btn btn-fantasma', type: 'button', style: 'height:32px', onclick: cambiarProducto }, 'Cambiar')),
    el('div', { class: 'ficha-datos' },
      el('div', {}, el('small', {}, 'A comprar'), el('strong', { class: 'num' }, producto.comprar ? `${fmtNum(producto.comprar)} und` : '—')),
      el('div', {}, el('small', {}, 'En stock'), el('strong', { class: 'num' }, fmtNum(producto.existencias), ' ', el('em', {}, producto.stock_max != null ? `de ${fmtNum(producto.stock_max)}` : ''))),
      el('div', {}, el('small', {}, 'Mejor oferta hoy'),
        el('strong', { class: 'num', style: mejor ? 'color:var(--good)' : '' }, mejor ? fmtMoney(mejor.valor) : 'Sin ofertas'),
        mejor && el('em', {}, mejor.empresa))));
}

/** Botón «Cambiar»: olvida el producto y vuelve al buscador. */
function cambiarProducto() {
  producto = null; E.buscar.value = '';
  pintarFicha(); pintarOpcionesProveedor(); actualizar();
  E.buscar.focus();
}

// buscador con teclado (↑ ↓ Enter Esc)
let resultadosActuales = [], indice = -1; // resultados de la última búsqueda y cuál está resaltado
/** Busca productos mientras se escribe (espera 220 ms de pausa) y muestra la lista desplegable. */
const buscar = debounce(async () => {
  const q = E.buscar.value.trim();
  if (q.length < 1) { E.resultados.hidden = true; E.buscar.setAttribute('aria-expanded', 'false'); return; }
  try { resultadosActuales = await api.catalogo(q); } catch (e) { mostrarError(e.message); return; }
  indice = resultadosActuales.length ? 0 : -1;
  pintarResultados();
}, 220);
/** Dibuja la lista de resultados; cada uno muestra código, descripción, cantidad a comprar y mejor oferta. */
function pintarResultados() {
  E.resultados.hidden = false; E.buscar.setAttribute('aria-expanded', 'true');
  if (!resultadosActuales.length) { E.resultados.replaceChildren(el('li', { class: 'vacio-res' }, 'Ningún producto coincide.')); return; }
  E.resultados.replaceChildren(...resultadosActuales.map((r, k) => el('li', {
    // mousedown (y no click) porque el campo pierde el foco antes del click y cerraría la lista.
    role: 'option', 'aria-selected': String(k === indice), onmousedown: (ev) => { ev.preventDefault(); elegirProducto(r.cod); },
  },
    el('span', { class: 'd' }, el('span', { class: 'cod', style: 'margin-right:8px' }, r.cod), r.descripcion),
    el('span', { class: 'm' }, r.comprar ? `Comprar ${fmtNum(r.comprar)} und` : 'Sin cantidad a comprar', ' · ',
      r.n_ofertas ? `${r.n_ofertas} oferta${r.n_ofertas === 1 ? '' : 's'}, mejor ${fmtMoney(r.mejor_valor)}` : 'sin ofertas'))));
}
/** Teclado en el buscador: ↑ ↓ mueven la selección, Enter elige, Esc cierra la lista (sin cerrar todo el panel). */
function teclasBuscador(ev) {
  if (E.resultados.hidden || !resultadosActuales.length) return;
  if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
    ev.preventDefault();
    // El «+ length … % length» hace que al pasar del último se vuelva al primero (y al revés).
    indice = (indice + (ev.key === 'ArrowDown' ? 1 : -1) + resultadosActuales.length) % resultadosActuales.length;
    pintarResultados();
  } else if (ev.key === 'Enter' && indice >= 0) { ev.preventDefault(); elegirProducto(resultadosActuales[indice].cod); }
  else if (ev.key === 'Escape') { ev.preventDefault(); E.resultados.hidden = true; } // preventDefault: que Esc no cierre el panel entero
}

// ------------------------------------------------------------------ Proveedor
/** Llena el desplegable de proveedores; marca con «· ya ofrece $X» los que ya cotizaron este producto. */
function pintarOpcionesProveedor() {
  const previo = E.proveedor.value; // para conservar la selección al redibujar
  const ya = new Map((producto?.ofertas || []).map((o) => [o.cod_empresa, o]));
  E.proveedor.replaceChildren(
    el('option', { value: '' }, 'Elige un proveedor…'),
    el('option', { value: NUEVO }, '＋ Proveedor nuevo…'),
    ...empresas.map((e) => el('option', { value: e.cod }, e.nombre + (ya.has(e.cod) ? `  ·  ya ofrece ${fmtMoney(ya.get(e.cod).valor)}` : ''))));
  if ([...E.proveedor.options].some((o) => o.value === previo)) E.proveedor.value = previo;
  cambioProveedor();
}
/** Al cambiar de proveedor: muestra/oculta el campo de nombre nuevo y avisa si ya tenía una oferta. */
function cambioProveedor() {
  E.cajaNuevo.hidden = !esNuevo();
  if (esNuevo()) E.nuevo.focus();
  const ya = producto?.ofertas.find((o) => o.cod_empresa === codEmpresa());
  E.pistaProv.className = 'pista-campo';
  E.pistaProv.replaceChildren();
  if (ya) {
    // Aviso amarillo: explica qué pasará con la oferta que ya existe.
    E.pistaProv.classList.add('aviso');
    E.pistaProv.append(`${ya.empresa} ya ofrece este producto a `, el('b', {}, fmtMoney(ya.valor)),
      ya.origen === 'manual' ? '. Tu oferta reemplazará la que agregaste antes.' : ' (portafolio). Si tu precio es menor, pasará a ser el que cuenta.');
  }
  actualizar();
}

// ------------------------------------------------------------------ Vista previa del ranking
/**
 * Simula cómo quedaría el ranking del producto SI se guardara la oferta escrita.
 * Replica las mismas reglas del servidor (app/services/ranking.py): un proveedor cuenta
 * una vez con su precio más bajo, y en empate gana el de menor código.
 * Devuelve null mientras falten datos (producto, proveedor o precio).
 */
function calcularPrevia() {
  const valor = valorActual();
  if (!producto || !(valor > 0) || !(codEmpresa() || (esNuevo() && nombreElegido().length >= 2))) return null;
  const cod = codEmpresa() || NUEVO, nombre = nombreElegido();
  // Las ofertas actuales, una por proveedor.
  const mapa = new Map(producto.ofertas.map((o) => [o.cod_empresa, { cod: o.cod_empresa, nombre: o.empresa, valor: o.valor, nueva: false }]));
  const previa = mapa.get(cod);
  const oculta = previa && previa.valor <= valor;            // su oferta actual ya es igual o más barata
  if (!oculta) mapa.set(cod, { cod, nombre, valor, nueva: true });
  const orden = [...mapa.values()].sort((a, b) => a.valor - b.valor
    || (Number(a.cod) || 1e9) - (Number(b.cod) || 1e9));    // igual que el servidor: en empate gana el menor código
  const puesto = orden.findIndex((o) => o.nueva) + 1;
  return { orden, puesto, oculta, previa, valor, mejorAntes: producto.ofertas[0] };
}
/** Dibuja el recuadro de vista previa: título («¡Sería la mejor oferta!»), ahorro y lista de puestos. */
function pintarPrevia() {
  const p = calcularPrevia();
  E.previa.hidden = !p;
  if (!p) return;
  const n = p.orden.length;
  const esMejor = p.puesto === 1 && !p.oculta;
  E.previa.className = `previa${esMejor ? ' mejor' : ''}`; // «mejor» = borde dorado
  // Tres mensajes posibles: no cambia nada / sería la mejor / quedaría en el puesto N.
  let titulo, sub;
  if (p.oculta) {
    titulo = 'Esta oferta no cambiaría el ranking';
    sub = `${p.previa.nombre} ya ofrece ${fmtMoney(p.previa.valor)}, que es igual o más barato.`;
  } else if (esMejor) {
    titulo = '¡Sería la mejor oferta!';
    sub = p.mejorAntes
      ? `Ahorras ${fmtMoney(p.mejorAntes.valor - p.valor)} por unidad frente a la mejor de hoy` +
        (producto.comprar ? ` (${fmtMoney((p.mejorAntes.valor - p.valor) * producto.comprar)} en la compra de ${fmtNum(producto.comprar)} und).` : '.')
      : 'Hoy nadie más ha cotizado este producto.';
  } else {
    titulo = `Quedaría en el puesto ${p.puesto} de ${n}`;
    sub = `${fmtMoney(p.valor - p.orden[0].valor)} por unidad más cara que la mejor.`;
  }
  // Una fila por proveedor; la oferta nueva se resalta con «← tu oferta».
  const fila = (o, i) => el('li', { class: o.nueva ? 'nueva' : '' },
    el('span', { class: `medalla ${i < 3 ? 'm' + (i + 1) : 'mn'}` }, i + 1),
    el('span', { class: 'nom' }, o.nombre, o.nueva ? '  ← tu oferta' : ''), el('span', { class: 'num' }, fmtMoney(o.valor)));
  // Solo se listan las 4 primeras; si la nueva queda más abajo, se agrega también su fila tras un «⋯».
  let filas = p.orden.slice(0, 4).map(fila);
  if (!p.oculta && p.puesto > 4) filas = [...filas, el('li', { class: 'hueco' }, '⋯'), fila(p.orden[p.puesto - 1], p.puesto - 1)];
  else if (p.orden.length > 4) filas.push(el('li', { class: 'hueco' }, `y ${p.orden.length - 4} más`));
  E.previa.replaceChildren(el('h2', {}, esMejor ? '🏆 ' : '', titulo), el('p', { class: 'sub' }, sub), el('ol', {}, filas));
}

/** Se llama con cada cambio del formulario: actualiza el texto del precio, los botones y la vista previa. */
function actualizar() {
  const v = valorActual();
  E.pistaValor.replaceChildren(E.valor.value.trim() && v > 0 ? el('span', {}, 'Se guardará: ', el('b', {}, fmtMoney(v), ' por unidad')) : 'Valor por unidad, igual que en el portafolio.');
  // Los botones de guardar solo se habilitan con producto + proveedor + precio válido.
  const listo = !!producto && v > 0 && (codEmpresa() || (esNuevo() && nombreElegido().length >= 2));
  E.guardar.disabled = E.otra.disabled = !listo;
  pintarPrevia();
}

// ------------------------------------------------------------------ Guardar
/**
 * Envía la oferta al servidor.
 *   cerrar = true  → «Guardar y cerrar»: cierra el panel y la pantalla principal muestra el aviso verde
 *   cerrar = false → «Guardar y agregar otra»: deja el panel abierto con el mismo producto
 * En los dos casos le avisa a la pantalla principal con `alGuardar` (el segundo dato dice si el panel sigue abierto).
 */
async function guardar(cerrar) {
  mostrarError('');
  const cuerpo = { cod_producto: producto.cod, valor: valorActual(), presentacion: E.presentacion.value.trim() || null };
  const crudoDisp = E.disponible.value.trim(); // opcional: vacío = el proveedor no dijo cuántas unidades tiene
  if (crudoDisp) {
    const disp = Number(crudoDisp.replace(/\./g, '').replace(',', '.'));
    if (!Number.isFinite(disp) || disp < 0) { mostrarError('La cantidad disponible debe ser un número (0 o más), o déjala vacía.'); return; }
    cuerpo.disponible = disp;
  }
  if (esNuevo()) cuerpo.empresa_nueva = nombreElegido(); else cuerpo.cod_empresa = codEmpresa();
  E.guardar.disabled = E.otra.disabled = true; // evita guardar dos veces por un doble clic
  let r;
  try { r = await api.agregarOferta(cuerpo); }
  catch (e) { mostrarError(e.message); actualizar(); return; }

  const aviso = { cod: r.producto.cod, empresa: r.empresa, puesto: r.puesto, es_la_mejor: r.es_la_mejor };
  const texto = `${r.actualizada ? 'Oferta actualizada' : 'Oferta guardada'}: ${r.empresa} ${r.es_la_mejor ? 'es ahora la mejor oferta' : `quedó en el puesto ${r.puesto} de ${r.total_ofertas}`}.`;
  if (cerrar) {
    dlg.close();
    alGuardar(aviso, false);
  } else {
    // «Guardar y agregar otra»: banner verde, formulario limpio y el mismo producto recargado.
    empresas = await api.empresas(); // por si se creó un proveedor nuevo
    E.banner.className = 'banner-ok'; E.banner.hidden = false;
    E.banner.replaceChildren(icono('check', 20), el('span', {}, texto));
    E.proveedor.value = ''; E.nuevo.value = ''; E.valor.value = ''; E.presentacion.value = ''; E.disponible.value = '';
    await elegirProducto(r.producto.cod);         // refresca el ranking con la oferta recién guardada
    E.proveedor.focus();
    alGuardar(aviso, true);
  }
}

// ------------------------------------------------------------------ Abrir y montar
/** Deja el formulario como nuevo: sin producto, sin proveedor, sin precio y sin mensajes. */
function reiniciar() {
  producto = null; resultadosActuales = []; indice = -1;
  E.buscar.value = ''; E.proveedor.value = ''; E.nuevo.value = ''; E.valor.value = ''; E.presentacion.value = ''; E.disponible.value = '';
  E.banner.hidden = true; E.resultados.hidden = true;
  mostrarError('');
  pintarFicha();
}

/**
 * Abre el panel. Con el código de un producto (por ejemplo desde el botón «Agregar oferta» de su fila) el producto
 * ya viene elegido; sin código, el cursor queda en el buscador.
 */
async function abrir(cod) {
  reiniciar();
  if (!dlg.open) dlg.showModal();
  try { empresas = await api.empresas(); } catch (e) { mostrarError(e.message); } // lista fresca (pudo cambiar en «Cargar datos»)
  pintarOpcionesProveedor();
  if (cod) { await elegirProducto(cod); E.proveedor.focus(); } else E.buscar.focus();
  actualizar();
}

/**
 * Conecta el panel: busca sus elementos en index.html y les pone sus acciones. Se llama UNA vez al cargar la página.
 *   opciones.alGuardar(aviso, panelAbierto)  función de la pantalla principal; se llama después de guardar una oferta
 * Devuelve {abrir}, la función que abre el panel.
 */
export function montarAgregar(opciones) {
  alGuardar = opciones.alGuardar;
  dlg = $('#dlg-agregar');
  // Referencias a los elementos del formulario (sus ids están en index.html).
  Object.assign(E, {
    buscar: $('#ag-buscar'), buscarCaja: $('#ag-producto-buscar'), resultados: $('#ag-resultados'), ficha: $('#ag-ficha'),
    proveedor: $('#ag-proveedor'), cajaNuevo: $('#ag-caja-nuevo'), nuevo: $('#ag-proveedor-nuevo'), pistaProv: $('#ag-pista-proveedor'),
    valor: $('#ag-valor'), presentacion: $('#ag-presentacion'), disponible: $('#ag-disponible'), pistaValor: $('#ag-pista-valor'), previa: $('#ag-previa'),
    error: $('#ag-error'), banner: $('#ag-banner'), guardar: $('#ag-guardar'), otra: $('#ag-guardar-otra'),
  });
  E.buscar.addEventListener('input', buscar);
  E.buscar.addEventListener('keydown', teclasBuscador);
  E.buscar.addEventListener('blur', () => setTimeout(() => { E.resultados.hidden = true; }, 120));
  E.proveedor.addEventListener('change', cambioProveedor);
  [E.nuevo, E.valor, E.presentacion].forEach((i) => i.addEventListener('input', actualizar));
  // Enter en cualquiera de estos campos = «Guardar y cerrar» (si el formulario está completo).
  [E.valor, E.presentacion, E.nuevo].forEach((i) => i.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && !E.guardar.disabled) guardar(true); }));
  E.guardar.addEventListener('click', () => guardar(true));
  E.otra.addEventListener('click', () => guardar(false));
  return { abrir };
}
