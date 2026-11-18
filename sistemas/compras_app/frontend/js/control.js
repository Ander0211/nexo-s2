/*
 * PANTALLA «TABLEROS DE CONTROL»
 * ==============================
 * Tres vistas tipo «Power BI» sobre los datos del tablero de compras (los números los calcula el servidor: app/services/control.py):
 *   1. Empresas con menores valores  → quién cobra menos (sobreprecio frente a la mejor oferta de cada producto)
 *   2. Precios más baratos           → dónde la mejor oferta más se aleja, hacia abajo, del precio promedio
 *   3. Productos que más consumen    → qué hay que reponer en mayor cantidad, inversión o stock máximo
 * Filtro cruzado (como en Power BI): al hacer clic en una empresa, las vistas 2 y 3 y los números de arriba se limitan a los productos
 * que ESA empresa cotiza. Otro clic en la misma empresa (o «Quitar filtro») lo deshace.
 */
import { api } from './api.js';
import { $, el, icono, fmtNum, fmtMoney, fmtPct, toast } from './util.js';

const S = { top: 10, min: 1, empresa: null, precios: 'porcentaje', consumo: 'cantidad' };
let datos = null;
let pidiendo = 0; // para ignorar respuestas viejas si se cambian los filtros rápido

const decimales = (n) => (n == null ? '—' : new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 }).format(n));
const plural = (n, uno, varios) => `${fmtNum(n)} ${n === 1 ? uno : varios}`;
const peso = (n) => fmtMoney(Math.round(n)); // montos de resumen: sin centavos

/** Una opción de los interruptores de cada vista (como los «segmentadores» de Power BI). */
function interruptor(opciones, actual, alElegir, etiqueta) {
  return el('div', { class: 'ct-interruptor', role: 'group', 'aria-label': etiqueta },
    ...opciones.map(([id, texto]) => el('button', { class: 'chip', type: 'button', 'aria-pressed': String(actual === id), onclick: () => alElegir(id) }, texto)));
}

/** Cabecera de cada vista: título, ayuda y (si lo hay) el interruptor. */
function cabecera(titulo, ayuda, extra) {
  return el('header', { class: 'ct-cab' }, el('div', {}, el('h2', {}, titulo), el('p', {}, ayuda)), extra || null);
}

const vacio = (texto) => el('p', { class: 'ct-vacio' }, texto);

// ------------------------------------------------------------------ números de arriba
function pintarKpis(k) {
  const barata = k.empresa_mas_barata, consumo = k.producto_mayor_consumo;
  const tarjetas = [
    { t: 'Inversión estimada', v: fmtMoney(k.inversion), s: `${fmtNum(k.con_oferta)} de ${fmtNum(k.productos)} productos con oferta`, i: 'moneda', c: 'var(--accent-2)' },
    { t: 'Ahorro vs 2.ª oferta', v: fmtMoney(k.ahorro), s: 'por comprar siempre al mejor precio', i: 'ahorro', c: 'var(--good)' },
    { t: 'Empresa más barata', v: barata ? barata.nombre : '—', texto: true, i: 'empresa', c: 'var(--accent)',
      s: barata ? (barata.sobreprecio_pct === 0 ? `Gana en ${fmtNum(barata.gana)} de ${fmtNum(barata.cotiza)} productos` : `${fmtPct(barata.sobreprecio_pct)} sobre la mejor oferta`) : 'Aún no hay con qué comparar' },
    { t: 'Mayor consumo', v: consumo ? consumo.descripcion : '—', texto: true, i: 'cesta', c: 'var(--warn)', s: consumo ? `${plural(consumo.comprar, 'unidad', 'unidades')} por reponer` : 'No hay productos por comprar' },
  ];
  $('#ct-kpis').replaceChildren(...tarjetas.map((x) => el('article', { class: 'kpi', style: `--kc:${x.c}` },
    el('div', { class: 'kpi-icono' }, icono(x.i, 20)),
    el('div', {}, el('span', { class: 'kpi-titulo' }, x.t), el('strong', { class: `kpi-valor${x.texto ? ' ct-kpi-texto' : ' num'}`, title: x.texto ? x.v : false }, x.v), el('span', { class: 'kpi-sub' }, x.s)))));
}

// ------------------------------------------------------------------ 1. empresas con menores valores
function pintarEmpresas(j) {
  const filas = j.empresas, max = Math.max(...filas.map((e) => e.sobreprecio_pct || 0), 1);
  const lista = !filas.length ? vacio('Todavía no hay ofertas para comparar empresas.') : el('ol', { class: 'ct-lista' }, ...filas.map((e, n) => {
    const activa = S.empresa === e.cod, sobre = e.sobreprecio_pct;
    return el('li', {}, el('button', { class: `ct-fila${activa ? ' activa' : ''}`, type: 'button', 'aria-pressed': String(activa),
      title: activa ? 'Quitar el filtro de esta empresa' : `Ver solo los productos que cotiza ${e.nombre}`, onclick: () => { S.empresa = activa ? null : e.cod; cargar(); } },
      el('span', { class: 'ct-pos' }, String(n + 1)),
      el('span', { class: 'ct-nombre' }, e.nombre, n === 0 && sobre !== null && el('em', { class: 'ct-etq' }, 'Más barata')),
      el('span', { class: `ct-valor num${sobre === 0 ? ' mejor' : ''}` }, sobre === null ? 'Sin comparar' : sobre === 0 ? '0 %' : fmtPct(sobre)),
      el('span', { class: 'ct-pista' }, el('i', { class: sobre === 0 ? 'bien' : '', style: `width:${sobre === null ? 0 : Math.max(sobre === 0 ? 2 : 4, (sobre / max) * 100)}%` })),
      el('span', { class: 'ct-meta' }, `Gana en ${fmtNum(e.gana)} de ${plural(e.cotiza, 'producto', 'productos')} · sobrecosto ${fmtMoney(e.sobrecosto)} · se le compra ${fmtMoney(e.comprado)}`)));
  }));
  $('#ct-empresas').replaceChildren(
    cabecera('Empresas con menores valores', 'Cuánto más caro es cada proveedor, en promedio, que la mejor oferta de lo que cotiza (0 % = siempre el más barato). Clic para filtrar.'),
    lista,
    el('footer', { class: 'ct-pie' }, `Mostrando ${fmtNum(filas.length)} de ${plural(j.total_empresas, 'empresa', 'empresas')}`));
}

// ------------------------------------------------------------------ 2. precios más baratos
function pintarPrecios(j) {
  const filas = j.precios, medida = (f) => (S.precios === 'valor' ? f.ahorro_valor : f.ahorro_pct), max = Math.max(...filas.map(medida), 1);
  const lista = !filas.length ? vacio(S.empresa ? 'Esa empresa no cotiza productos con 2 o más ofertas.' : 'Todavía no hay productos con 2 o más ofertas para comparar precios.') : el('ol', { class: 'ct-lista' }, ...filas.map((f, n) => el('li', { class: 'ct-fila fija' },
    el('span', { class: 'ct-pos' }, String(n + 1)),
    el('span', { class: 'ct-nombre' }, el('b', {}, f.cod), ' ', f.descripcion),
    el('span', { class: 'ct-valor num mejor' }, S.precios === 'valor' ? peso(f.ahorro_valor) : `−${decimales(f.ahorro_pct)} %`),
    // La barra mide el ahorro (en % o en $, según el interruptor) frente al mayor de la lista.
    el('span', { class: 'ct-pista', title: `Mejor ${fmtMoney(f.mejor_precio)} frente al promedio ${peso(f.precio_promedio)}` }, el('i', { class: 'bien', style: `width:${Math.max(2, (medida(f) / max) * 100)}%` })),
    el('span', { class: 'ct-meta' }, `${fmtMoney(f.mejor_precio)} con ${f.empresa} · promedio ${peso(f.precio_promedio)} (${f.n_ofertas} ofertas) · ahorra ${decimales(f.ahorro_pct)} % = ${peso(f.ahorro_valor)} en la compra`))));
  $('#ct-precios').replaceChildren(
    cabecera('Precios más baratos', 'Dónde la mejor oferta más se aleja, hacia abajo, del precio promedio. Solo productos con 2 o más ofertas.',
      interruptor([['porcentaje', 'Por %'], ['valor', 'Por $']], S.precios, (v) => { S.precios = v; cargar(); }, 'Ordenar los precios')),
    lista,
    el('footer', { class: 'ct-pie' }, `Mostrando ${fmtNum(filas.length)} de ${plural(j.total_precios, 'producto', 'productos')}`));
}

// ------------------------------------------------------------------ 3. productos que más consumen
const METRICAS = { cantidad: (f) => f.comprar, inversion: (f) => f.total || 0, stock_max: (f) => f.stock_max || 0 };
function pintarConsumo(j) {
  const filas = j.consumo, medida = METRICAS[S.consumo], max = Math.max(...filas.map(medida), 1);
  const valor = (f) => (S.consumo === 'inversion' ? (f.total == null ? 'Sin oferta' : fmtMoney(f.total)) : `${fmtNum(medida(f))} und`);
  const lista = !filas.length ? vacio(S.empresa ? 'Esa empresa no cotiza productos por comprar.' : 'No hay productos por comprar.') : el('ol', { class: 'ct-lista' }, ...filas.map((f, n) => el('li', { class: 'ct-fila fija' },
    el('span', { class: 'ct-pos' }, String(n + 1)),
    el('span', { class: 'ct-nombre' }, el('b', {}, f.cod), ' ', f.descripcion),
    el('span', { class: 'ct-valor num' }, valor(f)),
    el('span', { class: 'ct-pista' }, el('i', { style: `width:${Math.max(2, (medida(f) / max) * 100)}%` })),
    el('span', { class: 'ct-meta' }, `Hay ${fmtNum(f.existencias)} y el máximo es ${fmtNum(f.stock_max)} · repone ${f.reposicion_pct == null ? '—' : decimales(f.reposicion_pct) + ' %'} · ${f.empresa ? 'se compra a ' + f.empresa : 'sin oferta'}`))));
  $('#ct-consumo').replaceChildren(
    cabecera('Productos que más consumen', 'El consumo se estima con lo que hay que reponer (stock máximo − existencias): el sistema no recibe las salidas de bodega.',
      interruptor([['cantidad', 'Cantidad'], ['inversion', 'Inversión'], ['stock_max', 'Stock máximo']], S.consumo, (v) => { S.consumo = v; cargar(); }, 'Medir el consumo')),
    lista,
    el('footer', { class: 'ct-pie' }, `Mostrando ${fmtNum(filas.length)} de ${plural(j.total_consumo, 'producto', 'productos')}`));
}

// ------------------------------------------------------------------ filtros y carga
function pintarFiltros(j) {
  const sel = j.filtros.empresa_nombre;
  $('#ct-activo').replaceChildren(...(S.empresa ? [
    el('span', { class: 'ct-filtro-activo' }, icono('empresa', 14), `Empresa: ${sel || S.empresa}`),
    el('button', { class: 'btn btn-fantasma ct-quitar', type: 'button', onclick: () => { S.empresa = null; cargar(); } }, 'Quitar filtro')] : [
    el('span', { class: 'nota' }, 'Haz clic en una empresa para ver solo sus productos.')]));
}

function pintar(j) {
  datos = j;
  pintarKpis(j.kpis); pintarFiltros(j); pintarEmpresas(j); pintarPrecios(j); pintarConsumo(j);
  $('#ct-hora').textContent = `Actualizado ${new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}`;
}

async function cargar() {
  const mia = ++pidiendo;
  try {
    const j = await api.control({ top: S.top, min_productos: S.min, precios: S.precios, consumo: S.consumo, ...(S.empresa ? { empresa: S.empresa } : {}) });
    if (mia === pidiendo) pintar(j);
  } catch (e) {
    if (e.estado === 404 && S.empresa) { S.empresa = null; return cargar(); } // la empresa ya no existe
    toast(e.message, 'error');
  }
}

/** Conecta los controles de la pantalla (una sola vez, al iniciar). Devuelve `mostrar`, que se llama cada vez que se entra a la pantalla. */
export function montarControl() {
  $('#ct-top').addEventListener('change', (ev) => { S.top = Number(ev.target.value); cargar(); });
  $('#ct-min').addEventListener('change', (ev) => { S.min = Number(ev.target.value); cargar(); });
  $('#ct-actualizar').addEventListener('click', cargar);
  return { mostrar: cargar };
}
