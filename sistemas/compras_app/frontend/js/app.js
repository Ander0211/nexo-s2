/*
 * PANTALLA PRINCIPAL
 * ==================
 * Es el «director de orquesta» de la aplicación (index.html). Junta todas las piezas:
 *
 *   0. El MENÚ LATERAL y las dos pantallas: la bienvenida (la que se ve al ingresar) y el tablero de compras
 *   1. Los 4 números grandes de arriba (KPIs)
 *   2. Los botones de filtro (chips) y el orden
 *   3. La lista de productos, con su barra de stock, mejor proveedor y total
 *   4. La ventana de ofertas que abren los botones «Mejor oferta» y «Otras ofertas» de cada producto (podio.js)
 *   5. El gráfico «Dónde comprar» del panel derecho
 *   6. La paginación
 *   7. Las ventanas emergentes: ofertas de un producto, agregar ofertas a mano y cargar datos
 *   8. El panel de avisos de calidad de datos
 *
 * Flujo general: el usuario hace algo (escribe, filtra, hace clic) → se actualiza el
 * estado `S` → se le piden los datos al servidor (api.js) → se dibujan en la pantalla.
 *
 * Las secciones de abajo siguen ese orden. Casi todas las funciones «pintar...» solo
 * dibujan; las funciones «cargar...» piden datos al servidor y luego llaman a las de pintar.
 */
import { api } from './api.js';
import { $, $$, el, icono, fmtNum, fmtMoney, fmtPct, contar, toast, debounce, avisosAlFondo, rangoPaginas, confirmar, etiquetaNuevo, hacerMovibles, descargarConAviso, activarVerClave, ordenarTablas } from './util.js';
import { medidorStock, barrasProveedores } from './graficos.js';
import { montarPodio } from './podio.js';
import { nombreEmpresa } from './empresa.js';
import { montarAgregar } from './agregar.js';
import { montarCargar } from './cargar.js';
import { montarAdmin } from './admin.js';
import { montarUsuarios } from './usuarios.js';
import { montarControl } from './control.js';
import { montarAdicionales } from './adicionales.js';
import { montarProveedor } from './proveedor.js';
import { montarPendientes } from './pendientes.js';
import { montarAlternativas } from './alternativas.js';
import { sesion, es, puedeEditar } from './sesion.js';

// ESTADO de la pantalla: lo que el usuario tiene elegido en este momento.
const S = {
  q: '', // texto del buscador
  filtro: 'por_comprar', // botón de filtro activo
  empresa: null, // código del proveedor filtrado desde el gráfico (null = ninguno)
  empresaNombre: '',
  orden: 'inversion', // criterio de orden
  dir: null, // sentido: 'desc' (mayor a menor, Z–A) o 'asc' (menor a mayor, A–Z); null = el natural de ese criterio
  pagina: 1,
  tam: 25, // productos por página
  verTodosProv: false, // ¿el gráfico muestra los 12 principales o todos los proveedores?
  resumen: null, // última respuesta de /api/resumen
};
// Los botones de filtro: [id que entiende el servidor, texto, ¿es de alerta (color amarillo)?, ayuda al pasar el ratón]
const FILTROS = [
  ['por_comprar', 'Por comprar'], ['con_oferta', 'Con oferta'], ['sin_oferta', 'Sin oferta', true],
  ['nuevos', 'Nuevos', false, 'Productos nuevos y productos con una empresa nueva entre su mejor oferta o la elegida (la etiqueta dura 7 días)'],
  ['todos', 'Todos'],
];

// ------------------------------------------------------------------ KPIs
// Los 4 números grandes de arriba. `boton: true` = se puede hacer clic (filtra los productos sin oferta).
const KPIS = [
  { id: 'comprar', titulo: 'Productos por comprar', icono: 'cesta', color: 'var(--accent)' },
  { id: 'inversion', titulo: 'Inversión estimada', icono: 'moneda', color: 'var(--accent-2)' },
  { id: 'ahorro', titulo: 'Ahorro vs 2.ª oferta', icono: 'ahorro', color: 'var(--good)' },
  { id: 'sin', titulo: 'Sin ninguna oferta', icono: 'info', color: 'var(--warn)', boton: true },
];
/** Crea las 4 tarjetas vacías (una sola vez, al iniciar). Los números se llenan en pintarKPIs. */
function armarKPIs() {
  $('#kpis').replaceChildren(...KPIS.map((k) => el(k.boton ? 'button' : 'article',
    { class: 'kpi', id: `kpi-${k.id}`, style: `--kc:${k.color}`, type: k.boton ? 'button' : false,
      title: k.boton ? 'Ver solo los productos sin oferta' : false,
      onclick: k.boton ? () => cambiarFiltro('sin_oferta') : false },
    el('div', { class: 'kpi-icono' }, icono(k.icono, 20)),
    el('div', {},
      el('span', { class: 'kpi-titulo' }, k.titulo),
      el('strong', { class: 'kpi-valor num', id: `kv-${k.id}` }, '—'),
      el('span', { class: 'kpi-sub', id: `ks-${k.id}` }, '\u00a0')))));
}
/** Escribe los valores en las tarjetas; `contar` anima el número hasta llegar al valor nuevo. */
function pintarKPIs(r) {
  contar($('#kv-comprar'), r.por_comprar);
  $('#ks-comprar').textContent = `${fmtNum(r.con_oferta)} con oferta · ${fmtNum(r.proveedores_ganadores)} proveedores`;
  contar($('#kv-inversion'), r.inversion_total, fmtMoney);
  $('#ks-inversion').textContent = 'comprando siempre a quien elegiste';
  contar($('#kv-ahorro'), r.ahorro_total, fmtMoney);
  $('#ks-ahorro').textContent = 'por elegir la mejor y no la segunda';
  contar($('#kv-sin'), r.sin_oferta);
  $('#ks-sin').textContent = r.sin_oferta ? 'necesitan cotización u oferta manual' : '¡todo tiene al menos una oferta!';
}

// ------------------------------------------------------------------ Resumen, chips y panel de proveedores
/** Pide /api/resumen y actualiza todo lo que depende de él: KPIs, fecha, datos de la bienvenida, insignia de avisos, chips y gráfico. */
async function cargarResumen() {
  const r = S.resumen = await api.resumen();
  pintarKPIs(r);
  // Si la lista llegó ANTES que el resumen, el mensaje de «lista vacía» se escribió sin saber si es que no hay datos o que la búsqueda no coincide:
  // ahora que se sabe, se vuelve a escribir bien (sin esto, con la base vacía salía «Nada coincide» en vez de «Todavía no hay datos»).
  $('#filas .vacio[data-vacio]')?.replaceWith(estadoVacio());
  // La fecha llega como "2026-09-28 19:35"; se muestra como "28/09 19:35".
  $('#actualizado').textContent = r.ultima_importacion ? `Datos del ${r.ultima_importacion.slice(8, 10)}/${r.ultima_importacion.slice(5, 7)} ${r.ultima_importacion.slice(11)}` : 'Sin datos importados';
  // Tres datos rápidos en la pantalla de bienvenida.
  const dato = (valor, texto) => el('li', {}, el('strong', { class: 'num' }, fmtNum(valor)), texto);
  // Si no hay datos, la bienvenida lo dice y lleva a subirlos (lo primero que se ve al entrar con la base vacía).
  const pide = $('#inicio-pide');
  pide.hidden = r.productos !== 0;
  if (r.productos === 0) {
    const puede = es('admin', 'prime');
    pide.replaceChildren(icono('info', 18), el('span', {}, puede ? 'El sistema todavía no tiene datos. Para empezar necesita sus Excel.' : 'El sistema todavía no tiene datos. Pídele al administrador que suba los Excel.'),
      puede ? el('button', { class: 'btn btn-primario', id: 'inicio-subir', type: 'button', onclick: () => admin.abrirImportar() }, icono('subir', 16), 'Subir los Excel') : null);
  }
  $('#inicio-datos').replaceChildren(dato(r.por_comprar, 'productos por comprar'), dato(r.sin_oferta, 'sin ninguna oferta'), dato(r.proveedores_ganadores, 'proveedores ganadores'));
  // La insignia del menú «Avisos de datos» muestra cuántos avisos importantes hay (se oculta si son 0).
  const b = $('#badge-avisos');
  b.hidden = !r.avisos_pendientes; b.textContent = r.avisos_pendientes;
  // Y la de «Ofertas de proveedores»: cuántas fichas de proveedores esperan que las revisen.
  const bp = $('#badge-pendientes');
  bp.hidden = !r.ofertas_pendientes; bp.textContent = r.ofertas_pendientes;
  pintarChips();
  pintarProveedores();
}

/** Dibuja los botones de filtro con su contador; el activo queda resaltado (aria-pressed). */
function pintarChips() {
  const c = S.resumen?.conteos || {};
  $('#chips').replaceChildren(...FILTROS.map(([id, texto, alerta, ayuda]) => el('button', {
    class: `chip${alerta && c[id] ? ' alerta' : ''}${id === 'nuevos' && c[id] ? ' hay-nuevos' : ''}`, type: 'button', 'aria-pressed': String(S.filtro === id),
    title: ayuda || false, onclick: () => cambiarFiltro(id),
  }, texto, el('span', { class: 'n num' }, fmtNum(c[id] ?? 0)))));
}

/** Dibuja el gráfico «Dónde comprar»: 12 proveedores, o todos si se pulsó «Ver los N proveedores». */
function pintarProveedores() {
  const todos = S.resumen?.por_proveedor || [];
  $('#prov-cuenta').textContent = todos.length ? `${todos.length} proveedores` : '';
  const lista = S.verTodosProv ? todos : todos.slice(0, 12);
  const caja = $('#barras');
  if (!todos.length) { caja.replaceChildren(el('p', { style: 'color:var(--muted)' }, 'Aún no hay productos con oferta.')); }
  else barrasProveedores(caja, lista, S.empresa, (p) => elegirProveedor(p));
  const vt = $('#ver-todos');
  vt.hidden = todos.length <= 12;
  vt.textContent = S.verTodosProv ? 'Ver solo los 12 principales' : `Ver los ${todos.length} proveedores`;
}

/** Clic en una barra del gráfico: filtra la lista por ese proveedor (otro clic en la misma barra lo quita). */
function elegirProveedor(p) {
  const quitar = S.empresa === p.cod;
  S.empresa = quitar ? null : p.cod;
  S.empresaNombre = quitar ? '' : p.nombre;
  // Estos dos filtros no tienen sentido combinados con un proveedor, así que se vuelve a «Por comprar».
  if (!quitar && S.filtro === 'sin_oferta') S.filtro = 'por_comprar';
  S.pagina = 1;
  pintarChips(); pintarProveedores(); cargarLista();
}

/** Clic en un botón de filtro (o en el KPI «Sin ninguna oferta»). */
function cambiarFiltro(id) {
  S.filtro = id; S.pagina = 1;
  if (id === 'sin_oferta') { S.empresa = null; S.empresaNombre = ''; pintarProveedores(); }
  pintarChips(); cargarLista();
}

// ------------------------------------------------------------------ Orden de la lista (y Excel del tablero)
// Los números se ordenan de MAYOR a MENOR por defecto y los textos de la A a la Z; el botón del sentido (o un 2.º clic en el título) lo invierte.
const TEXTOS_ORDEN = new Set(['descripcion', 'proveedor', 'codigo']);
const direccion = () => S.dir || (TEXTOS_ORDEN.has(S.orden) ? 'asc' : 'desc');

/** Pinta el sentido del orden (botón y flecha del título activo) y arma la dirección del «Excel del tablero» con lo que se ve. */
function pintarOrden() {
  const texto = TEXTOS_ORDEN.has(S.orden), asc = direccion() === 'asc';
  const b = $('#orden-dir');
  b.textContent = texto ? (asc ? 'A → Z' : 'Z → A') : (asc ? '↑ Menor a mayor' : '↓ Mayor a menor');
  b.title = 'Cambiar el sentido del orden';
  $('#orden').value = S.orden;
  $$('.cabecera-lista [data-orden]').forEach((h) => {
    const activo = h.dataset.orden === S.orden;
    h.title = 'Ordenar por esta columna (otro clic invierte el sentido)';
    if (activo) { h.setAttribute('aria-sort', asc ? 'ascending' : 'descending'); h.dataset.flecha = asc ? '▲' : '▼'; } else h.removeAttribute('aria-sort');
  });
  const p = { q: S.q, filtro: S.filtro, orden: S.orden, direccion: direccion() };
  if (S.empresa) p.empresa = S.empresa;
  $('#btn-excel-tablero')?.setAttribute('href', `/api/exportar/tablero?${new URLSearchParams(p)}`);
}

/** Ordenar por un criterio: si ya era ese, se invierte el sentido; si no, empieza con su sentido natural. */
function ordenarPor(criterio) {
  if (S.orden === criterio) S.dir = direccion() === 'asc' ? 'desc' : 'asc';
  else { S.orden = criterio; S.dir = null; }
  S.pagina = 1; cargarLista();
}

// ------------------------------------------------------------------ Lista de productos
/** Columna «Mejor proveedor» de una fila: proveedor + precio + presentación + nota de la 2.ª oferta. */
function celdaOferta(i) {
  if (!i.elegida) {
    // Producto sin ninguna oferta: etiqueta amarilla de alerta.
    return el('div', { class: 'c-oferta' }, el('span', { class: 'etiqueta sin' }, icono('info', 14), 'Sin oferta'));
  }
  const e = i.elegida;
  // La nota de abajo depende del caso:
  //   elegida a mano → recuerda cuál era la mejor   ·   hay 2.ª oferta → cuánto más cara es   ·   si no → «Única oferta»
  let nota = null;
  if (i.elegida_a_mano) nota = el('div', { class: 'nota' }, 'Mejor: ', el('b', {}, `${i.mejor.empresa} · ${fmtMoney(i.mejor.valor)}`));
  else if (i.segunda) nota = el('div', { class: 'nota' }, '2.ª oferta: ', el('b', { class: 'num' }, fmtPct(i.dif_segunda_pct)));
  else nota = el('div', { class: 'nota' }, 'Única oferta');
  return el('div', { class: 'c-oferta' },
    nombreEmpresa(e.cod_empresa, e.empresa, e.empresa_nueva),
    el('div', { class: 'precio-linea' },
      el('span', { class: 'precio num' }, fmtMoney(e.valor)),
      e.presentacion && el('em', { class: 'pres' }, e.presentacion),
      i.elegida_a_mano && el('span', { class: 'etiqueta mano' }, 'Elegida por ti')),
    nota,
    ...avisosDeCantidad(i));
}

/**
 * Los avisos de CANTIDAD de una fila (solo si el proveedor dijo cuántas unidades tiene):
 *   «Repartido» → el mejor no tiene para todo: se le compra lo que tenga y el resto al siguiente (el detalle está en «Mejor oferta»)
 *   «Faltan N» → ningún proveedor tiene suficientes   ·   «solo tiene N» → elegiste a mano un proveedor que dijo tener menos
 */
function avisosDeCantidad(i) {
  const e = i.elegida, avisos = [];
  if (i.repartido) {
    const partes = i.reparto.map((l) => `${fmtNum(l.cantidad)} con ${l.empresa}`).join(' · ');
    avisos.push(el('div', { class: 'aviso-cant', title: partes }, icono('comparar', 14), `Repartido en ${i.reparto.length} proveedores`));
  }
  if (i.sin_unidades) avisos.push(el('div', { class: 'aviso-cant mal' }, icono('alerta', 14), 'Ningún proveedor tiene unidades'));
  else if (i.faltante > 0) avisos.push(el('div', { class: 'aviso-cant mal' }, icono('alerta', 14), `Faltan ${fmtNum(i.faltante)} und: nadie las tiene`));
  if (i.excede_disponible > 0 && e) avisos.push(el('div', { class: 'aviso-cant mal' }, icono('alerta', 14), `${e.empresa} solo tiene ${fmtNum(e.disponible)}: faltan ${fmtNum(i.excede_disponible)}`));
  return avisos;
}

/** Columna «Total» de una fila: precio × cantidad, y el ahorro frente a la 2.ª oferta. */
function celdaTotal(i) {
  if (!i.elegida || !i.comprar || i.total == null) return el('div', { class: 'c-total' }, el('strong', { style: 'color:var(--faint)' }, '—'));
  return el('div', { class: 'c-total' },
    el('strong', { class: 'num' }, fmtMoney(i.total)),
    !i.elegida_a_mano && i.ahorro > 0 && el('span', { class: 'ahorro num' }, `ahorras ${fmtMoney(i.ahorro)}`));
}

/**
 * Columna «Ofertas» de una fila: dos botones, cada uno abre su ventana emergente (ver abrirOfertas).
 *   «Mejor oferta»  → ventana con la oferta más barata y por qué lo es
 *   «Otras ofertas» → ventana con la 2.ª, 3.ª... (y «Ver siguientes» si hay más)
 * Si el producto no tiene ofertas se muestra un solo botón para agregar la primera;
 * si tiene una sola, «Otras ofertas» queda apagado.
 */
function celdaAcciones(i) {
  if (i.n_ofertas === 0) {
    // El perfil «Consulta» solo mira: en vez del botón para agregar la primera oferta ve un texto.
    if (!puedeEditar()) return el('div', { class: 'c-acciones' }, el('span', { class: 'nota' }, 'Nadie ha cotizado todavía'));
    return el('div', { class: 'c-acciones' }, el('button', {
      class: 'btn-fila agregar', type: 'button', title: 'Nadie ha cotizado este producto: agrega la primera oferta',
      onclick: () => abrirAgregar(i.cod),
    }, icono('mas', 14), 'Agregar oferta'));
  }
  const otras = i.n_ofertas - 1; // cuántas ofertas hay además de la mejor
  // Arma uno de los dos botones: su pestaña, icono, texto, ayuda emergente, lo que va al final (el contador) y si está apagado.
  const boton = (pestana, nombreIcono, texto, titulo, extra, apagado) => el('button', {
    class: 'btn-fila', type: 'button', 'data-pestana': pestana, title: titulo, disabled: apagado,
    onclick: () => abrirOfertas(i, pestana),
  }, icono(nombreIcono, 14), texto, extra);
  return el('div', { class: 'c-acciones' },
    boton('mejor', 'trofeo', 'Mejor oferta', 'Ver la mejor oferta de proveedores', null, false),
    boton('otras', 'lista', 'Otras ofertas', otras ? 'Ver las otras ofertas' : 'Este producto solo tiene una oferta',
      el('span', { class: 'n num' }, otras), otras === 0));
}

/**
 * Dibuja UNA fila de producto: código y descripción, stock, cantidad a comprar, mejor proveedor, los botones
 * «Mejor oferta» / «Otras ofertas» (cada uno abre su ventana emergente) y el total.
 */
const CANTIDAD_MAX = 10_000_000; // el mismo tope que valida el servidor (schemas.CantidadIn)

/** Guarda la cantidad escrita. Se valida aquí (entero de 0 a 10.000.000) para avisar sin ir al servidor. */
async function guardarCantidad(i, input, boton) {
  const texto = input.value.trim();
  const cantidad = Number(texto);
  if (texto === '' || !Number.isInteger(cantidad) || cantidad < 0 || cantidad > CANTIDAD_MAX) {
    toast(`Escribe una cantidad entera entre 0 y ${fmtNum(CANTIDAD_MAX)}.`, 'error'); input.focus(); input.select(); return;
  }
  if (!(await confirmarCantidad(i, cantidad))) { input.focus(); input.select(); return; } // «Revisar»: no se guarda nada
  boton.disabled = true;
  try {
    const r = await api.editarCantidad(i.cod, cantidad);
    toast(`Cantidad de ${i.cod} fijada en ${fmtNum(cantidad)}. El stock y el máximo no cambian.`, 'ok');
    await actualizarFila(r.item);
  } catch (e) { toast(e.message, 'error'); boton.disabled = false; }
}

/**
 * La ventanita «¿Está seguro de la cantidad a comprar?» que sale antes de guardar: repite el producto y la cantidad, compara con lo recomendado
 * (StockMax − Existencias), dice cuántas unidades quedarían en stock y, si se compra MENOS de lo recomendado, lo avisa. Aclara que el stock
 * máximo no cambia. «Sí, guardar» guarda; «Revisar» vuelve a la caja sin guardar nada.
 */
function confirmarCantidad(i, cantidad) {
  const hayMax = i.stock_max != null;
  const quedarian = (i.existencias ?? 0) + cantidad;
  return confirmar({
    titulo: '¿Está seguro de la cantidad a comprar?',
    parrafos: [
      el('p', {}, el('b', {}, i.cod), ' · ', i.descripcion),
      el('p', { class: 'cf-cifra' }, 'Vas a comprar ', el('b', {}, `${fmtNum(cantidad)} ${cantidad === 1 ? 'unidad' : 'unidades'}`), '.'),
      el('p', { class: 'cf-detalle' }, hayMax
        ? `Hoy hay ${fmtNum(i.existencias ?? 0)} en stock (máx ${fmtNum(i.stock_max)}). Lo recomendado es comprar ${fmtNum(i.calculada)}. Con esta compra tendrías ${fmtNum(quedarian)}.`
        : 'Este producto no tiene stock máximo definido, así que no hay una cantidad recomendada.'),
      hayMax && cantidad < i.calculada
        ? el('p', { class: 'cf-aviso' }, icono('alerta', 16), el('span', {}, `Estás comprando menos de lo recomendado: faltarían ${fmtNum(i.calculada - cantidad)} unidades para llegar a las ${fmtNum(i.calculada)} recomendadas.`))
        : null,
      el('p', { class: 'cf-nota' }, 'El stock máximo no cambia: esto solo define cuántas unidades vas a comprar.'),
    ],
    boton: 'Sí, guardar',
    cancelar: 'Revisar',
  });
}

/** «Stock suficiente»: no hay nada que comprar porque las existencias ya están en el máximo o por encima. */
const stockSuficiente = (i) => el('small', { class: 'stock-suficiente', title: `Las existencias (${fmtNum(i.existencias)}) ya están en el máximo (${fmtNum(i.stock_max)}) o por encima: no hay nada que comprar.` }, icono('check', 12), 'Stock suficiente');

/** El aviso «Menos de lo recomendado»: la cantidad fijada a mano es menor que la calculada. */
const menosDeLoRecomendado = (i) => el('small', { class: 'cantidad-aviso', title: `Se compra menos de lo recomendado: lo recomendado (máx − stock) es ${fmtNum(i.calculada)}.` }, icono('alerta', 12), `Menos de lo recomendado (${fmtNum(i.calculada)})`);

/** ¿Esta fila sigue perteneciendo al filtro que se está viendo? (la misma regla que aplica el servidor: services/tablero.py → _cumple). */
function perteneceAlFiltro(i) {
  if (S.empresa && !(i.elegida && i.elegida.cod_empresa === S.empresa)) return false;
  if (S.filtro === 'por_comprar') return i.comprar > 0;
  if (S.filtro === 'con_oferta') return i.comprar > 0 && i.n_ofertas > 0;
  if (S.filtro === 'sin_oferta') return i.comprar > 0 && i.n_ofertas === 0;
  if (S.filtro === 'nuevos') return i.novedad;
  return true; // «todos»
}

/**
 * Después de editar o restaurar una cantidad se cambia SOLO esa fila (y los números de arriba): la lista NO se vuelve a ordenar ni a filtrar.
 * Así lo que acabas de editar se queda donde estaba aunque su total o su cantidad hayan cambiado (por ejemplo, un producto al que le pones 0).
 * Si ya no cumple el filtro activo, la fila se atenúa con un aviso y saldrá de la lista cuando pulses «Actualizar todo» o cambies de filtro.
 */
async function actualizarFila(item) {
  const vieja = item && $(`.fila[data-cod="${CSS.escape(item.cod)}"]`);
  if (vieja) vieja.replaceWith(renderFila(item, !perteneceAlFiltro(item)));
  else await cargarLista({ silencioso: true }); // la fila no está a la vista: se lee de nuevo la lista
  await cargarResumen().catch((e) => toast(e.message, 'error')); // los 4 números, los filtros y «Dónde comprar»
}

/** Vuelve a la cantidad calculada (StockMax − Existencias): quita la que se había fijado a mano. */
async function restaurarCantidad(i) {
  try {
    const r = await api.restaurarCantidad(i.cod);
    toast(`${i.cod} vuelve a la cantidad calculada (${fmtNum(i.calculada)}).`, 'ok');
    await actualizarFila(r.item);
  } catch (e) { toast(e.message, 'error'); }
}

/**
 * Columna «Comprar» de una fila. Quien puede editar ve una caja donde se ESCRIBE la cantidad (no hace falta usar flechas):
 *   - solo acepta dígitos y trae el número seleccionado al entrar, así basta con teclear el nuevo
 *   - Enter o el botón ✓ guardan · Esc cancela · las teclas ↑ ↓ suben o bajan de 1 en 1 (con Shift, de 10 en 10)
 *   - el botón ✓ solo se enciende cuando hay un cambio por guardar
 *   - si la cantidad se fijó a mano, queda marcada y un botón permite volver a la calculada
 * La caja es de texto (no «number») para que SIEMPRE se vean todos los dígitos, sin flechitas encima del número.
 * La cantidad que se fija vale hasta que se restaure: no la cambian las existencias ni «Actualizar Excel».
 * Quien no puede editar (perfil Consulta) solo ve el número.
 */
function celdaCantidad(i) {
  if (!puedeEditar()) {
    return el('div', { class: `c-comprar${i.comprar ? '' : ' cero'}` },
      i.comprar || !i.stock_suficiente ? el('strong', { class: 'num' }, i.comprar ? fmtNum(i.comprar) : '—') : stockSuficiente(i),
      i.comprar ? el('small', {}, i.editada ? 'unidades · editada' : 'unidades') : null,
      i.menos_de_lo_recomendado && menosDeLoRecomendado(i));
  }
  const original = String(Math.round(i.comprar));
  const input = el('input', {
    class: 'cantidad-input', type: 'text', inputmode: 'numeric', pattern: '[0-9]*', autocomplete: 'off', enterkeyhint: 'done', maxlength: '8',
    value: original, 'aria-label': `Cantidad a comprar de ${i.cod}`, title: 'Cuántas unidades vas a comprar. No cambia el stock ni el máximo. Enter guarda · Esc cancela · ↑ ↓ suben o bajan',
  });
  const boton = el('button', {
    class: 'cantidad-guardar', type: 'button', title: 'Guardar la cantidad', 'aria-label': `Guardar la cantidad de ${i.cod}`,
    disabled: true, onclick: () => guardarCantidad(i, input, boton),
  }, icono('check', 15));
  const pie = el('div', { class: 'cantidad-pie' },
    i.editada
      ? el('button', { class: 'cantidad-restaurar', type: 'button', title: `Volver a la cantidad calculada (${fmtNum(i.calculada)})`, onclick: () => restaurarCantidad(i) },
        icono('deshacer', 12), `editada · calculada ${fmtNum(i.calculada)}`)
      : el('small', {}, 'calculada'),
    i.menos_de_lo_recomendado && menosDeLoRecomendado(i),
    i.stock_suficiente && stockSuficiente(i));
  const celda = el('div', { class: `c-comprar${i.comprar ? '' : ' cero'} cantidad-editable${i.editada ? ' es-manual' : ''}` },
    el('span', { class: 'cantidad-titulo' }, 'Cantidad a comprar'),
    el('div', { class: 'cantidad-campo' }, input, boton),
    pie);
  const cambio = () => { const hay = input.value !== original; boton.disabled = !hay; celda.classList.toggle('sin-guardar', hay); };
  input.addEventListener('focus', () => input.select());
  input.addEventListener('input', () => { input.value = input.value.replace(/\D/g, '').slice(0, 8); cambio(); });
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); if (!boton.disabled) boton.click(); }
    else if (ev.key === 'Escape') { input.value = original; cambio(); input.blur(); }
    else if (ev.key === 'ArrowUp' || ev.key === 'ArrowDown') {
      ev.preventDefault();
      const paso = (ev.shiftKey ? 10 : 1) * (ev.key === 'ArrowUp' ? 1 : -1);
      input.value = String(Math.min(CANTIDAD_MAX, Math.max(0, (Number(input.value) || 0) + paso)));
      cambio();
    }
  });
  return celda;
}

function renderFila(i, fuera = false) {
  return el('article', { class: `fila${fuera ? ' fuera-filtro' : ''}`, 'data-cod': i.cod },
    el('div', { class: 'fila-principal' },
      el('div', { class: 'c-prod' }, el('div', { class: 'cod-fila' }, el('span', { class: 'cod' }, i.cod), i.nuevo && etiquetaNuevo(i.nuevo_desde, 'Producto nuevo')), el('span', { class: 'desc', title: i.descripcion }, i.descripcion)),
      el('div', { class: 'c-stock' }, medidorStock(i)),
      celdaCantidad(i),
      celdaOferta(i), celdaAcciones(i), celdaTotal(i)),
    fuera && el('div', { class: 'fuera-aviso' }, 'Ya no cumple este filtro: saldrá de la lista cuando pulses «Actualizar todo» o cambies de filtro.'));
}

// ------------------------------------------------------------------ Ventana «Ofertas del producto»
// Es el <dialog id="dlg-ofertas"> de index.html. La abren los botones «Mejor oferta» y «Otras ofertas» de cada fila.
/** Título e icono de la ventana según la pestaña que se está viendo. */
const VISTAS = { mejor: ['Mejor oferta', 'trofeo'], otras: ['Otras ofertas', 'lista'], todas: ['Comparar todas las ofertas', 'comparar'] };
/** El panel de ofertas que hay dentro de la ventana ahora mismo: { cod, panel }. Vale null si la ventana está cerrada. */
let ofertasAbiertas = null;

/**
 * Abre la ventana con las ofertas de un producto.
 *   i        el producto (fila de la lista)
 *   pestana  qué ver al abrir: 'mejor' | 'otras' | 'todas'
 */
function abrirOfertas(i, pestana) {
  const dlg = $('#dlg-ofertas');
  // El título y el icono siguen a la pestaña: cambian al abrir y cada vez que se cambia de pestaña dentro de la ventana.
  const titular = (p) => {
    const [texto, nombreIcono] = VISTAS[p] || VISTAS.todas;
    $('#of-titulo').textContent = texto;
    $('#of-icono').replaceChildren(icono(nombreIcono, 22));
  };
  titular(pestana);
  $('#of-sub').replaceChildren(...[`${i.cod} · ${i.descripcion} `, i.nuevo ? etiquetaNuevo(i.nuevo_desde, 'Producto nuevo') : null].filter(Boolean));
  // Cada apertura usa un contenedor NUEVO: si una respuesta lenta de otro producto llega tarde, escribe en uno ya descartado.
  const cuerpo = el('div');
  $('#of-cuerpo').replaceChildren(cuerpo);
  const panel = montarPodio(cuerpo, i.cod, {
    pestana,
    abrirAgregar, // botón «Agregar oferta manual a este producto» (abre «Agregar oferta» encima de esta ventana)
    // Si se eligió/eliminó algo: se recalcula la lista de atrás y se vuelven a pedir las ofertas de esta ventana.
    alCambiar: () => { refrescarTodo(); panel.recargar(); },
    alPestana: titular,
  });
  ofertasAbiertas = { cod: i.cod, panel };
  if (!dlg.open) dlg.showModal();
  $('#of-cuerpo').scrollTop = 0;
}

// «Ticket»: cada vez que se pide la lista se toma un número. Si mientras llega la respuesta el
// usuario ya pidió otra cosa (siguió escribiendo, cambió de filtro), la respuesta vieja se descarta.
let ticket = 0;   // descarta respuestas viejas si el usuario sigue escribiendo o cambiando filtros
/**
 * Pide la lista de productos al servidor con el estado actual (S) y la dibuja.
 *   silencioso: true → no muestra las barras «esqueleto» (se usa al refrescar, para que no parpadee)
 */
async function cargarLista({ silencioso = false } = {}) {
  const mio = ++ticket;
  const caja = $('#filas');
  if (!silencioso) caja.replaceChildren(...Array.from({ length: 7 }, () => el('div', { class: 'esqueleto' })));
  let r;
  try {
    pintarOrden();
    r = await api.productos({ q: S.q, filtro: S.filtro, empresa: S.empresa, orden: S.orden, direccion: direccion(), pagina: S.pagina, tam: S.tam });
  } catch (e) {
    if (mio === ticket) caja.replaceChildren(el('div', { class: 'vacio' }, el('strong', {}, 'No se pudo cargar la lista'), e.message));
    return;
  }
  if (mio !== ticket) return; // llegó tarde: ya hay una petición más nueva
  S.pagina = r.pagina;
  pintarFiltroActivo();
  if (!r.items.length) caja.replaceChildren(estadoVacio());
  else caja.replaceChildren(...r.items.map((i) => renderFila(i)));
  pintarPaginacion(r);
}

/** Mensaje cuando la lista queda vacía: «Todavía no hay datos» (sin Excel) o «Nada coincide» (búsqueda sin resultados). */
function estadoVacio() {
  if (S.resumen && S.resumen.productos === 0) {
    const puede = es('admin', 'prime');
    const caja = el('div', { id: 'vacio-checklist' });
    if (puede) admin.pintarChecklist(caja); // la lista de Excel que necesita, con cuáles ya están y cuáles faltan
    return el('div', { class: 'vacio vacio-pide', 'data-vacio': 'sin-datos' }, icono('info', 30), el('strong', {}, 'Todavía no hay datos'),
      el('p', {}, puede ? 'Para que el sistema funcione necesito estos Excel. Súbelos todos juntos: reconozco cuál es cuál por su nombre.' : 'Pídele al administrador que suba los Excel.'),
      puede ? caja : null,
      puede ? el('button', { class: 'btn btn-primario', id: 'vacio-subir', type: 'button', onclick: () => admin.abrirImportar() }, icono('subir', 16), 'Subir los Excel') : null,
      puede ? el('p', { class: 'nota' }, 'También sirven las plantillas de «Cargar datos» (productos, proveedores y cotizaciones).') : null);
  }
  return el('div', { class: 'vacio', 'data-vacio': 'sin-resultados' }, icono('buscar', 30), el('strong', {}, 'Nada coincide con lo que buscas'),
    'Prueba con otra palabra, cambia de filtro o quita el proveedor seleccionado.');
}

/** La franja azul «Productos que se compran a X · Quitar filtro» (solo aparece si hay un proveedor filtrado). */
function pintarFiltroActivo() {
  const caja = $('#filtro-activo');
  caja.hidden = !S.empresa;
  if (S.empresa) {
    caja.replaceChildren(icono('trofeo', 16), el('span', {}, 'Productos que se compran a ', el('b', {}, S.empresaNombre)),
      el('button', { type: 'button', onclick: () => elegirProveedor({ cod: S.empresa }) }, 'Quitar filtro'));
  }
}

// ------------------------------------------------------------------ Paginación
/** Dibuja «Mostrando 26–50 de N productos» y los botones ‹ 1 2 3 … ›. */
function pintarPaginacion(r) {
  const nav = $('#paginacion');
  if (!r.total) { nav.replaceChildren(); return; }
  const ini = (r.pagina - 1) * r.tam + 1, fin = Math.min(r.total, r.pagina * r.tam);
  // Ir a una página: carga la lista y sube suavemente al inicio de la tabla.
  const ir = (p) => () => { S.pagina = p; cargarLista(); $('.lista').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  nav.replaceChildren(
    el('span', { class: 'num' }, `Mostrando ${fmtNum(ini)}–${fmtNum(fin)} de ${fmtNum(r.total)} productos`),
    el('div', { class: 'pags' },
      el('button', { type: 'button', disabled: r.pagina === 1, onclick: ir(r.pagina - 1), 'aria-label': 'Página anterior' }, '‹'),
      rangoPaginas(r.pagina, r.paginas).map((p) => p === '…' ? el('span', { class: 'pts' }, '…')
        : el('button', { type: 'button', 'aria-current': p === r.pagina ? 'page' : false, onclick: ir(p), class: 'num' }, fmtNum(p))),
      el('button', { type: 'button', disabled: r.pagina === r.paginas, onclick: ir(r.pagina + 1), 'aria-label': 'Página siguiente' }, '›')));
}

/** Recalcula TODO (KPIs, chips, gráfico y lista) sin parpadeo. Se usa después de cualquier cambio de datos. */
const refrescarTodo = () => Promise.all([cargarResumen(), cargarLista({ silencioso: true })]).catch((e) => toast(e.message, 'error'));

/**
 * Botón «Actualizar todo»: vuelve a leer del servidor TODO el contenido del tablero (los 4 números, los filtros, la lista, «Dónde
 * comprar» y la insignia de avisos) y anota la hora. Sirve cuando otra persona hizo cambios mientras esta pantalla estaba abierta.
 * No importa los Excel: para eso está «Actualizar Excel».
 */
async function actualizarTodo() {
  const b = $('#btn-actualizar-todo');
  b.disabled = true; b.classList.add('girando');
  try {
    await Promise.all([cargarResumen(), cargarLista({ silencioso: true })]);
    $('#tablero-hora').textContent = `Actualizado a las ${new Date().toTimeString().slice(0, 5)}`;
    toast('Todo el tablero está al día.', 'ok');
  } catch (e) { toast(e.message, 'error'); }
  finally { b.disabled = false; b.classList.remove('girando'); }
}

// ------------------------------------------------------------------ Paneles emergentes: agregar oferta y cargar datos
// Son <dialog> de esta misma página (index.html), no ventanas aparte: el navegador no los puede bloquear.
let agregar = null, cargar = null, admin = null, usuarios = null, proveedor = null, control = null, adicionales = null; // paneles y pantallas (los crea iniciar)

/** Abre el panel «Agregar oferta manual». Si se le pasa el código de un producto, se abre con ese producto ya elegido. */
const abrirAgregar = (cod) => agregar.abrir(cod);

/**
 * El panel «Agregar oferta» guardó una oferta: muestra el aviso y refresca la pantalla.
 *   panelAbierto = true cuando fue «Guardar y agregar otra» (el panel sigue abierto y ya muestra su propio banner).
 */
function alGuardarOferta(d, panelAbierto = false) {
  if (!panelAbierto) toast(d.es_la_mejor ? `¡${d.empresa} pasó a ser la mejor oferta de ${d.cod}!` : `Oferta de ${d.empresa} agregada a ${d.cod} (puesto ${d.puesto}).`, 'ok');
  refrescarTodo();
  // Si la ventana de ofertas de ese producto está abierta debajo, se actualiza con la oferta nueva.
  if (ofertasAbiertas?.cod === d.cod) ofertasAbiertas.panel.recargar();
}
/** El panel «Cargar datos» cargó o guardó algo: refresca toda la pantalla (el panel ya muestra su propio resultado). */
function alCargarDatos() {
  refrescarTodo();
}

// ------------------------------------------------------------------ Avisos de calidad de datos
/** Los botones «Ir a corregir» de un aviso que ESTE perfil puede usar: los que llevan a una tabla de Administración solo los ve
 *  el administrador; los que llevan al tablero, todos los que ven avisos. Devuelve null si no queda ninguno. */
function botonesDeAviso(a, cerrar) {
  const botones = (a.destinos || []).map((d, k) => (d.vista || es('admin')) && el('button', {
    class: `btn btn-ir${k ? '' : ' principal'}`, type: 'button', onclick: () => { cerrar(); irAlAviso(a, k); },
  }, icono('flecha', 14), d.texto, d.cantidad != null && el('span', { class: 'n' }, fmtNum(d.cantidad)))).filter(Boolean);
  return botones.length > 0 && el('div', { class: 'ir' }, botones);
}

/** Abre el panel lateral del botón ⚠ con los avisos de los Excel. Se cierra con Esc, la X o clic afuera. */
async function abrirAvisos() {
  const previo = document.activeElement; // para devolver el foco al cerrar (accesibilidad)
  let lista;
  try { lista = await api.avisos(); } catch (e) { toast(e.message, 'error'); return; }
  // Cerrar el panel: quita el fondo y el cajón, deja de escuchar la tecla Esc y devuelve el foco a donde estaba.
  const cerrar = () => { telon.remove(); cajon.remove(); document.removeEventListener('keydown', esc); previo?.focus?.(); };
  // Esc cierra el panel de avisos.
  const esc = (ev) => { if (ev.key === 'Escape') cerrar(); };
  const telon = el('div', { class: 'telon', onclick: cerrar }); // el fondo oscuro; al hacer clic se cierra
  // Cada aviso trae sus botones «Ir a corregir»: llevan a la tabla y a las filas del problema (o al tablero con el filtro puesto).
  const cuerpo = el('div', { class: 'cuerpo' }, lista.length ? lista.map((a) => el('div', { class: `aviso ${a.nivel}` },
    el('div', { class: 't' }, el('span', { class: 'punto' }), a.titulo), a.detalle && el('div', { class: 'd' }, a.detalle),
    botonesDeAviso(a, cerrar)))
    : el('p', { style: 'color:var(--muted)' }, 'No hay avisos: los datos se ven limpios.'));
  const cajon = el('aside', { class: 'cajon', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Avisos sobre los datos' },
    el('header', {}, el('h2', {}, 'Avisos sobre los datos'),
      el('button', { class: 'btn-icono', type: 'button', 'aria-label': 'Cerrar', onclick: cerrar }, icono('x', 18))),
    cuerpo);
  document.body.append(telon, cajon);
  document.addEventListener('keydown', esc);
  $('button', cajon).focus();
}

/**
 * Lleva al lugar de un aviso (el botón «Ir a corregir» número `k`):
 *   - destino del tablero → se pone ese filtro (por ejemplo «Sin oferta») y se muestra el tablero
 *   - destino de tabla    → la pantalla Administración: las filas del problema, o «Agregar» con los valores puestos
 */
function irAlAviso(aviso, k) {
  const d = aviso.destinos[k];
  if (d.vista === 'tablero') {
    S.empresa = null; S.empresaNombre = ''; S.q = ''; $('#q').value = ''; // sin otros filtros encima: se ve justo el problema
    pintarProveedores(); pintarFiltroActivo(); cambiarFiltro(d.filtro);
    location.hash = '#tablero';
    mostrarPantalla('tablero'); // por si ya se estaba en el tablero y la dirección no cambia
  } else {
    admin.irA(d, { clave: aviso.clave, titulo: aviso.titulo, posicion: k });
  }
}

// ------------------------------------------------------------------ Pantallas y menú lateral
/** Las «pantallas» de la aplicación y cómo se llaman en la ruta de arriba. Se elige con el final de la dirección:
 *  #inicio · #tablero · #admin (y #admin/stock, #admin/portafolio... para abrir una tabla concreta). */
const PANTALLAS = { inicio: 'Bienvenida', tablero: 'Tablero de compras', control: 'Tableros de control', adicionales: 'Adicionales', admin: 'Administración', usuarios: 'Usuarios', proveedor: 'Productos que necesitamos' };

/** Qué pantallas puede ver cada perfil (la primera es la de por defecto). Es solo comodidad: el servidor revisa cada petición. */
const PANTALLAS_POR_PERFIL = {
  admin: ['inicio', 'tablero', 'control', 'adicionales', 'admin', 'usuarios', 'proveedor'], // el administrador también ve la pantalla del proveedor
  prime: ['inicio', 'tablero', 'control'],
  consulta: ['inicio', 'tablero', 'control'], // «Adicionales» es solo del administrador
  externo: ['proveedor'],
};

/** ¿Qué pantalla pide la dirección actual? Cualquier cosa desconocida → la bienvenida (la de por defecto). */
const pantallaPedida = () => {
  const h = location.hash;
  if (h === '#tablero') return 'tablero';
  if (h === '#control') return 'control';
  if (h === '#adicionales') return 'adicionales';
  if (/^#admin(\/|$)/.test(h)) return 'admin';
  if (h === '#usuarios') return 'usuarios';
  if (h === '#proveedor') return 'proveedor';
  return 'inicio';
};

/**
 * Muestra una pantalla y oculta las demás; marca su opción en el menú y actualiza la ruta de la barra de arriba
 * («Inicio › Tablero de compras») y el título de la pestaña del navegador.
 */
function mostrarPantalla(nombre) {
  for (const n of Object.keys(PANTALLAS)) $(`#vista-${n}`).hidden = n !== nombre;
  // La opción del menú de la pantalla actual queda marcada (franja azul a la izquierda).
  $$('.menu-item[data-pantalla]').forEach((o) => (o.dataset.pantalla === nombre ? o.setAttribute('aria-current', 'page') : o.removeAttribute('aria-current')));
  $('#ruta-actual').textContent = nombre === 'inicio' ? '' : PANTALLAS[nombre];
  document.title = nombre === 'inicio' ? 'SUMIPABON · Compras' : `${PANTALLAS[nombre]} · SUMIPABON`;
  window.scrollTo(0, 0);
}

/** Conecta el menú lateral: el botón ☰, el botón grande de la bienvenida y el cambio de pantalla al cambiar la dirección. */
function armarMenu() {
  const cuerpo = document.body, boton = $('#btn-menu');
  const angosta = () => window.innerWidth < 1000; // en pantallas angostas el menú se abre encima del contenido y empieza cerrado
  const marcar = () => boton.setAttribute('aria-expanded', String(!cuerpo.classList.contains('menu-cerrado')));
  if (angosta()) cuerpo.classList.add('menu-cerrado');
  marcar();
  boton.addEventListener('click', () => { cuerpo.classList.toggle('menu-cerrado'); marcar(); });
  // En pantallas angostas, al elegir una opción el menú se esconde para dejar ver el resultado.
  $$('.menu-item').forEach((o) => o.addEventListener('click', () => { if (angosta()) { cuerpo.classList.add('menu-cerrado'); marcar(); } }));
  $('#btn-entrar').addEventListener('click', () => { location.hash = '#tablero'; });
  // Al cambiar la dirección se muestra la pantalla pedida (la primera vez, al terminar de entrar: ver comenzar).
  window.addEventListener('hashchange', () => { if (sesion.usuario) mostrarLaPedida(); });
}

/**
 * Muestra la pantalla que pide la dirección, PERO solo si el perfil puede verla: si no, lo lleva a la suya (un proveedor
 * externo siempre va a «Productos que necesitamos»). Después carga lo que esa pantalla necesita.
 */
function mostrarLaPedida() {
  const permitidas = PANTALLAS_POR_PERFIL[sesion.usuario.rol];
  let n = pantallaPedida();
  if (!permitidas.includes(n)) { n = permitidas[0]; history.replaceState(null, '', `#${n}`); }
  mostrarPantalla(n);
  if (n === 'admin') admin.mostrar(location.hash.split('/')[1]); // la pestaña sale de «#admin/stock»
  if (n === 'usuarios') usuarios.mostrar();
  if (n === 'control') control.mostrar();
  if (n === 'adicionales') adicionales.mostrar();
  if (n === 'proveedor') proveedor.mostrar();
}

// ------------------------------------------------------------------ Sesión: ingreso, perfil, cambio de clave y salida
/** Sin sesión: se ve solo la pantalla de ingreso (y, si la sesión acababa de vencer, un aviso). */
function mostrarLogin() {
  document.body.classList.remove('verificando');
  document.body.classList.add('sin-sesion');
  const aviso = sessionStorage.getItem('aviso-login');
  sessionStorage.removeItem('aviso-login');
  $('#login-aviso').hidden = !aviso;
  $('#login-aviso').textContent = aviso || '';
  $('#login-usuario').focus();
}

/** Ajusta la aplicación al perfil: muestra solo las opciones del menú que le corresponden y escribe quién es en la barra. */
function aplicarPerfil() {
  const u = sesion.usuario;
  document.body.dataset.rol = u.rol;
  document.body.classList.remove('verificando', 'sin-sesion');
  $$('[data-roles]').forEach((n) => { n.hidden = !n.dataset.roles.split(' ').includes(u.rol); });
  $('#usuario-nombre').textContent = u.nombre;
  $('#usuario-rol').textContent = u.empresa ? `${u.rol_nombre} · ${u.empresa}` : u.rol_nombre;
}

/**
 * Ya hay una sesión válida: si tiene clave temporal la obliga a cambiarla, ajusta la pantalla al perfil, muestra la
 * pantalla pedida y pide los primeros datos (solo los perfiles que ven el tablero).
 */
async function comenzar(usuario) {
  sesion.usuario = usuario;
  if (usuario.cambiar_clave) await pedirClaveNueva(true);
  aplicarPerfil();
  mostrarLaPedida();
  if (es('admin', 'prime', 'consulta')) {
    cargarResumen().catch((e) => toast(e.message, 'error'));
    cargarLista();
  }
}

/**
 * Ventana «Cambiar mi clave». `obligatoria` = se entró con una clave temporal: no se puede cancelar ni cerrar con Esc hasta
 * cambiarla. Devuelve una promesa que se cumple cuando la clave quedó cambiada (o, si era voluntaria, se cerró la ventana).
 */
function pedirClaveNueva(obligatoria = false) {
  return new Promise((resolve) => {
    const dlg = $('#dlg-clave'), form = $('#cl-form'), error = $('#cl-error');
    form.reset(); error.hidden = true;
    $('#cl-cancelar').hidden = obligatoria;
    $('#cl-sub').textContent = obligatoria ? 'Entraste con una clave temporal: elige la tuya para continuar.' : 'Escribe tu clave actual y la nueva.';
    const bloquearEsc = (ev) => ev.preventDefault(); // con clave temporal, Esc no cierra la ventana
    if (obligatoria) dlg.addEventListener('cancel', bloquearEsc);
    const enviar = async (ev) => {
      ev.preventDefault();
      if ($('#cl-nueva').value !== $('#cl-repite').value) { error.textContent = 'Las dos claves nuevas no coinciden.'; error.hidden = false; return; }
      try {
        const r = await api.cambiarClave($('#cl-actual').value, $('#cl-nueva').value);
        sesion.usuario = r.usuario;
        limpiar(); dlg.close();
        toast('Tu clave se cambió.', 'ok');
        resolve();
      } catch (e) { error.textContent = e.message; error.hidden = false; }
    };
    const alCerrar = () => { limpiar(); resolve(); };
    const limpiar = () => {
      form.removeEventListener('submit', enviar); dlg.removeEventListener('cancel', bloquearEsc); dlg.removeEventListener('close', alCerrar);
      form.reset();
    };
    form.addEventListener('submit', enviar);
    dlg.addEventListener('close', alCerrar);
    dlg.showModal();
    $('#cl-actual').focus();
  });
}

/** El formulario de ingreso: valida en el servidor; si la clave es temporal, obliga a cambiarla antes de entrar. */
async function ingresar(ev) {
  ev.preventDefault();
  const error = $('#login-error'), boton = $('#login-entrar');
  error.hidden = true; boton.disabled = true;
  try {
    const r = await api.entrar($('#login-usuario').value, $('#login-clave').value);
    $('#login-clave').value = '';
    await comenzar(r.usuario);
  } catch (e) {
    error.textContent = e.message; error.hidden = false;
    $('#login-clave').value = ''; $('#login-clave').focus();
  } finally { boton.disabled = false; }
}

/** «Salir»: cierra la sesión en el servidor y recarga la página (así no queda ningún dato en pantalla). */
async function salir() {
  try { await api.salir(); } catch { /* si ya no había sesión, da igual */ }
  location.replace(location.pathname);
}

// ------------------------------------------------------------------ Arranque
/** Se ejecuta UNA vez al cargar la página: conecta cada botón con su acción y pide los primeros datos. */
function iniciar() {
  // Los iconos del HTML estático (data-icono="mas") se dibujan aquí.
  $$('[data-icono]').forEach((n) => n.prepend(icono(n.dataset.icono, Number(n.dataset.tam) || 18)));
  admin = montarAdmin({ alCambiar: alCargarDatos });
  usuarios = montarUsuarios();
  proveedor = montarProveedor();
  control = montarControl();
  adicionales = montarAdicionales(); // los tableros de control (empresas con menores valores, precios más baratos, productos que más consumen)
  const pendientes = montarPendientes({ alCambiar: refrescarTodo }); // las fichas que envían los proveedores (solo el administrador)
  $('#btn-pendientes').addEventListener('click', () => pendientes.abrir());
  const alternativas = montarAlternativas(); // alternativas 2.º a 4.º, insumos sin oferta y productos nuevos (administrador y Prime)
  $('#btn-alternativas').addEventListener('click', () => alternativas.abrir());
  activarVerClave(); // el ojo para ver la clave que se escribe (ingreso y «Cambiar mi clave»)
  armarKPIs(); pintarChips(); armarMenu();
  // Sesión: formulario de ingreso, «Clave», «Salir», y volver al ingreso si la sesión vence mientras se usa la aplicación.
  $('#login-form').addEventListener('submit', ingresar);
  $('#btn-clave').addEventListener('click', () => pedirClaveNueva(false));
  $('#btn-salir').addEventListener('click', salir);
  let vencida = false;
  document.addEventListener('sesion-vencida', () => {
    if (vencida) return;
    vencida = true;
    sessionStorage.setItem('aviso-login', 'Tu sesión terminó. Entra de nuevo para continuar.');
    location.replace(location.pathname);
  });

  // Buscador: espera 250 ms de pausa al escribir y vuelve a la página 1.
  $('#q').addEventListener('input', debounce((ev) => { S.q = ev.target.value.trim(); S.pagina = 1; cargarLista(); }, 250));
  $('#orden').addEventListener('change', (ev) => { S.orden = ev.target.value; S.dir = null; S.pagina = 1; cargarLista(); });
  $('#orden-dir').addEventListener('click', () => { S.dir = direccion() === 'asc' ? 'desc' : 'asc'; S.pagina = 1; cargarLista(); });
  $$('.cabecera-lista [data-orden]').forEach((h) => h.addEventListener('click', () => ordenarPor(h.dataset.orden)));
  ordenarTablas(); // las demás tablas (usuarios, pendientes, historial...) se ordenan con un clic en el título
  // Las ventanas emergentes: se conectan una vez; las opciones del menú solo las abren.
  agregar = montarAgregar({ alGuardar: alGuardarOferta });
  cargar = montarCargar({ alCambiar: alCargarDatos, abrirAgregar: () => abrirAgregar() });
  $('#btn-agregar').addEventListener('click', () => abrirAgregar());
  $('#btn-cargar').addEventListener('click', () => cargar.abrir());
  // Cualquier botón con data-cerrar cierra el panel donde está; al cerrarse, los avisos vuelven a la página.
  $$('dialog.modal [data-cerrar]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
  $$('dialog.modal').forEach((d) => d.addEventListener('close', avisosAlFondo));
  // Al cerrar la ventana de ofertas se vacía: así no queda nada viejo si se abre con otro producto.
  $('#dlg-ofertas').addEventListener('close', () => { ofertasAbiertas = null; $('#of-cuerpo').replaceChildren(); });
  $('#btn-avisos').addEventListener('click', abrirAvisos);
  $('#btn-actualizar-todo').addEventListener('click', actualizarTodo);
  hacerMovibles(); // las ventanas emergentes se pueden mover arrastrando su cabecera
  // Las descargas que tardan en prepararse avisan «Preparando…» en vez de dejar al navegador esperando en silencio.
  $$('a[data-descarga]').forEach((a) => a.addEventListener('click', (ev) => { ev.preventDefault(); descargarConAviso(a, a.dataset.descarga); }));
  $('#ver-todos').addEventListener('click', () => { S.verTodosProv = !S.verTodosProv; pintarProveedores(); });
  // «Actualizar Excel»: abre la ventana para elegir qué tablas importar y cómo (reemplazar o agregar). Nada se importa solo.
  $('#btn-importar').addEventListener('click', () => admin.abrirImportar());
  // Atajo de teclado: «/» lleva el cursor al buscador (salvo que ya se esté escribiendo en un campo).
  // Si se está en la bienvenida, primero pasa al tablero, que es donde vive el buscador.
  document.addEventListener('keydown', (ev) => {
    const escribiendo = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName);
    if (ev.key === '/' && !escribiendo && !document.querySelector('dialog[open]') && es('admin', 'prime', 'consulta')) {
      ev.preventDefault();
      if (pantallaPedida() !== 'tablero') location.hash = '#tablero';
      mostrarPantalla('tablero');
      $('#q').focus();
    }
  });
}

/** Punto de entrada: conecta la página y le pregunta al servidor si ya hay una sesión iniciada (si no, muestra el ingreso). */
async function arrancar() {
  iniciar();
  // Enlace del correo («/?ingresar=1»): SIEMPRE pide usuario y clave, aunque en este navegador ya hubiera una sesión
  // abierta (p. ej. la del administrador). Se cierra esa sesión y se limpia la dirección: así, al recargar después de
  // entrar, no se vuelve a cerrar.
  const enlace = new URLSearchParams(location.search);
  if (enlace.has('ingresar')) {
    const usuarioEnlace = (enlace.get('usuario') || '').trim();
    history.replaceState(null, '', location.pathname + location.hash);
    try { await api.salir(); } catch { /* no había sesión */ }
    sessionStorage.setItem('aviso-login', usuarioEnlace ? 'Escribe la clave temporal que te enviamos.' : 'Ingresa con el usuario y la clave que te enviamos.');
    mostrarLogin();
    if (usuarioEnlace) { $('#login-usuario').value = usuarioEnlace; $('#login-clave').focus(); } // usuario ya escrito, como en SENTINEL
    return;
  }
  let usuario = null;
  try { usuario = (await api.sesion()).usuario; } catch { /* sin sesión */ }
  if (!usuario) { mostrarLogin(); return; }
  await comenzar(usuario);
}
arrancar();
