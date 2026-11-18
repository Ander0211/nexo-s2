/*
 * PANTALLA «ADICIONALES»
 * ======================
 * El usuario sube (Excel/CSV), pega o escribe el CÓDIGO y la DESCRIPCIÓN de productos, y ve para cada uno el Proveedor 1, 2 y 3
 * (en ese orden) con su MENOR VALOR ofertado al lado. Los cálculos los hace el servidor (app/services/adicionales.py).
 * Los productos no se borran: se INHABILITAN (quedan en rojo y no cuentan en el resumen ni en el Excel) y se pueden volver a habilitar.
 * Es una lista de consulta: no cambia el tablero ni la orden de compra.
 */
import { api } from './api.js';
import { $, $$, el, icono, fmtNum, fmtMoney, toast } from './util.js';
import { puedeEditar } from './sesion.js';

const PUESTOS = 3;
let datos = { items: [], total: 0, con_oferta: 0, sin_oferta: 0, inhabilitados: 0 };
let modo = 'uno';
const POR_PAGINA = 300; // con hasta 100.000 productos, dibujar todos a la vez congelaría el navegador
let visibles = POR_PAGINA;

function pintarKpis() {
  const t = [
    { t: 'Productos activos', v: fmtNum(datos.total), c: 'var(--accent-2)' },
    { t: 'Con oferta', v: fmtNum(datos.con_oferta), c: 'var(--good)' },
    { t: 'Sin oferta', v: fmtNum(datos.sin_oferta), c: 'var(--warn)' },
    { t: 'Inhabilitados', v: fmtNum(datos.inhabilitados || 0), c: 'var(--bad)' },
  ];
  $('#adi-kpis').replaceChildren(...t.map((k) => el('div', { class: 'kpi', style: `--kc:${k.c}` }, el('div', {},
    el('span', { class: 'kpi-titulo' }, k.t), el('strong', { class: 'kpi-valor num' }, k.v)))));
  $('#adi-n-inh').textContent = fmtNum(datos.inhabilitados || 0);
}

/** Dos celdas por puesto: el proveedor y, al lado, su menor valor. */
function celdasProveedor(p, puesto) {
  if (!p) {
    return [el('td', { class: `adi-prov p${puesto} adi-nada` }, puesto === 1 ? el('span', { class: 'adi-sin' }, 'Sin oferta') : '—'),
      el('td', { class: `adi-val p${puesto} adi-nada num` }, '—')];
  }
  return [
    el('td', { class: `adi-prov p${puesto}` }, el('div', { class: 'adi-nombre', title: `Código ${p.cod_empresa}` }, p.nombre),
      p.presentacion ? el('div', { class: 'adi-pres' }, p.presentacion) : null),
    el('td', { class: `adi-val p${puesto} num` }, fmtMoney(p.valor)),
  ];
}

function pintarTabla() {
  const q = ($('#adi-buscar').value || '').trim().toLowerCase();
  const verInh = $('#adi-ver-inh').checked;
  const items = datos.items.filter((it) => (verInh || it.activo) && (!q ||
    [it.cod, it.descripcion, ...it.proveedores.map((p) => p.nombre)].some((x) => (x || '').toLowerCase().includes(q))));
  const editar = puedeEditar();
  const cab = el('thead', {},
    el('tr', { class: 'adi-cab1' },
      el('th', { rowspan: 2 }, 'Código'), el('th', { rowspan: 2 }, 'Descripción'),
      ...Array.from({ length: PUESTOS }, (_, i) => el('th', { colspan: 2, class: `adi-grupo-th p${i + 1}` }, `Proveedor ${i + 1}`)),
      editar ? el('th', { rowspan: 2, class: 'acc' }, 'Estado') : null),
    el('tr', { class: 'adi-cab2' },
      ...Array.from({ length: PUESTOS }, (_, i) => [el('th', { class: `p${i + 1}` }, 'Proveedor'), el('th', { class: `p${i + 1} num` }, 'Menor valor')])));
  const filas = items.slice(0, visibles).map((it) => el('tr', { class: it.activo ? '' : 'adi-inhabilitado' },
    el('td', { class: 'adi-cod num' }, it.cod),
    el('td', { class: 'adi-descr' }, it.descripcion || '—',
      !it.activo ? el('small', { class: 'adi-estado-inh' }, 'Inhabilitado') : null,
      it.activo && it.encontrado_por && it.encontrado_por.startsWith('descripcion:')
        ? el('small', { class: 'adi-nota' }, `Encontrado por la descripción (código ${it.encontrado_por.slice(12)})`) : null),
    ...Array.from({ length: PUESTOS }, (_, i) => celdasProveedor(it.proveedores[i], i + 1)),
    editar ? el('td', { class: 'acc' }, el('button', {
      class: `btn-estado ${it.activo ? 'inhabilitar' : 'habilitar'}`, type: 'button',
      title: it.activo ? 'Inhabilitar: queda en rojo y no cuenta en el resumen ni en el Excel' : 'Volver a habilitar',
      onclick: () => cambiarEstado(it),
    }, it.activo ? 'Inhabilitar' : 'Habilitar')) : null));
  const cols = 2 + PUESTOS * 2 + (editar ? 1 : 0);
  const cuerpo = filas.length ? filas : [el('tr', {}, el('td', { colspan: cols, class: 'adi-vacia' },
    datos.items.length ? 'Ningún producto coincide con la búsqueda.' : 'La lista está vacía. Pulse «Agregar» o suba un Excel con CÓDIGO y DESCRIPCIÓN.'))];
  const faltan = items.length - Math.min(visibles, items.length);
  const pie = faltan > 0 ? el('tfoot', {}, el('tr', {}, el('td', { colspan: cols, class: 'adi-mas' },
    `Mostrando ${fmtNum(visibles)} de ${fmtNum(items.length)} productos. `,
    el('button', { class: 'btn btn-fantasma', type: 'button', onclick: () => { visibles += POR_PAGINA * 3; pintarTabla(); } }, `Ver ${fmtNum(Math.min(faltan, POR_PAGINA * 3))} más`),
    el('span', { class: 'adi-mas-nota' }, ' · Use el buscador para encontrar uno en particular, o «Descargar Excel» para verlos todos.')))) : null;
  $('#adi-tabla').replaceChildren(cab, el('tbody', {}, ...cuerpo), pie);
}

function pintar(d) { datos = d; pintarKpis(); pintarTabla(); }

async function cargar() {
  try { pintar(await api.adicionales()); } catch (e) { toast(e.message, 'error'); }
}

async function cambiarEstado(it) {
  try {
    pintar(await api.adicionalesActivo(it.id, !it.activo));
    toast(it.activo ? `${it.cod} inhabilitado.` : `${it.cod} habilitado de nuevo.`, 'ok');
  } catch (e) { toast(e.message, 'error'); }
}

const resumen = (r) => [r.nuevos && `${fmtNum(r.nuevos)} agregado${r.nuevos === 1 ? '' : 's'}`, r.actualizados && `${fmtNum(r.actualizados)} ya estaba${r.actualizados === 1 ? '' : 'n'} (actualizado${r.actualizados === 1 ? '' : 's'})`].filter(Boolean).join(' · ');

/** Filas pegadas desde Excel: código ⇥ descripción (también acepta «;» o varios espacios como separador). */
function filasPegadas(texto) {
  return texto.split(/\r?\n/).map((l) => (l.includes('\t') ? l.split('\t') : l.includes(';') ? l.split(';') : l.split(/\s{2,}/)))
    .filter((c) => (c[0] || '').trim()).map((c) => ({ cod: c[0].trim(), descripcion: (c.slice(1).join(' ') || '').trim() || null }));
}

// ------------------------------------------------------------------ ventana emergente «Agregar»
function elegirModo(m) {
  modo = m;
  $$('#dlg-adicional .adi-pestanas [data-modo]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.modo === m)));
  $$('#dlg-adicional .adi-modo').forEach((s) => { s.hidden = s.dataset.modo !== m; });
  $('#adi-otro').hidden = m === 'varios';
  (m === 'uno' ? $('#adi-cod') : $('#adi-pegar')).focus();
}

function contarPegadas() {
  const n = filasPegadas($('#adi-pegar').value).length;
  $('#adi-cuenta').textContent = `${fmtNum(n)} producto${n === 1 ? '' : 's'} listo${n === 1 ? '' : 's'} para agregar`;
}

/** Lo agregado en esta ventana, con sus 3 proveedores: así se ve el resultado sin cerrarla. */
function mostrarHechos(cods) {
  const claves = new Set(cods.map((c) => c.toLowerCase()));
  const hechos = datos.items.filter((it) => claves.has(it.cod.toLowerCase())).slice(-5);
  const caja = $('#adi-hechos');
  caja.hidden = !hechos.length;
  caja.replaceChildren(el('div', { class: 'adi-hechos-tit' }, icono('check', 15), 'Agregado'),
    ...hechos.map((it) => el('div', { class: 'adi-hecho' },
      el('b', {}, it.cod), el('span', {}, it.descripcion || ''),
      el('span', { class: 'adi-hecho-p1' }, it.proveedores[0] ? `Proveedor 1: ${it.proveedores[0].nombre} · ${fmtMoney(it.proveedores[0].valor)}` : 'Sin oferta'))));
}

function abrirVentana() {
  $('#adi-form').reset();
  $('#adi-hechos').hidden = true;
  contarPegadas();
  $('#dlg-adicional').showModal();
  elegirModo('uno');
}

async function guardar(e) {
  e.preventDefault();
  const seguir = e.submitter && e.submitter.value === 'otro';
  const filas = modo === 'uno'
    ? [{ cod: $('#adi-cod').value.trim(), descripcion: $('#adi-desc').value.trim() || null }].filter((f) => f.cod)
    : filasPegadas($('#adi-pegar').value);
  if (!filas.length) { toast(modo === 'uno' ? 'Escriba el código del producto.' : 'Pegue al menos una fila con código.', 'aviso'); return; }
  try {
    const r = await api.adicionalesAgregar(filas);
    pintar(r);
    toast(resumen(r), 'ok');
    if (seguir) { mostrarHechos(filas.map((f) => f.cod)); $('#adi-cod').value = ''; $('#adi-desc').value = ''; $('#adi-cod').focus(); }
    else $('#dlg-adicional').close();
  } catch (err) { toast(err.message, 'error'); }
}

export function montarAdicionales() {
  const reiniciar = () => { visibles = POR_PAGINA; pintarTabla(); };
  $('#adi-buscar').addEventListener('input', reiniciar);
  $('#adi-ver-inh').addEventListener('change', reiniciar);
  $('#adi-agregar').addEventListener('click', abrirVentana);
  $$('#dlg-adicional .adi-pestanas [data-modo]').forEach((b) => b.addEventListener('click', () => elegirModo(b.dataset.modo)));
  $('#adi-pegar').addEventListener('input', contarPegadas);
  // Pegar varias filas en «Código» cambia solo al modo «Pegar varios»
  $('#adi-cod').addEventListener('paste', (e) => {
    const texto = e.clipboardData.getData('text');
    if (!/\n|\t/.test(texto.trim())) return;
    e.preventDefault();
    elegirModo('varios');
    $('#adi-pegar').value = texto;
    contarPegadas();
  });
  $('#adi-form').addEventListener('submit', guardar);
  $('#adi-archivo').addEventListener('change', async (e) => {
    const f = e.target.files[0]; e.target.value = '';
    if (!f) return;
    try { const r = await api.adicionalesSubir(f); pintar(r); toast(`${f.name}: ${resumen(r)}`, 'ok'); } catch (err) { toast(err.message, 'error'); }
  });
  return { mostrar: cargar };
}
