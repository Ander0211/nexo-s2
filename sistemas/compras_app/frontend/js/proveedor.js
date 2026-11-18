/*
 * PANTALLA «PRODUCTOS QUE NECESITAMOS» (proveedor externo)
 * ========================================================
 * Lo ÚNICO que ve un proveedor externo: qué productos necesita la Clínica (solo código y descripción, sin cantidades), con búsqueda,
 * paginación y un botón para descargar ese mismo listado como Excel (con VALOR y PRESENTACION vacíos, para que cotice).
 * El servidor NUNCA le envía precios, ofertas de otros proveedores, existencias ni stock (app/routers/proveedor.py).
 * También SUBE su ficha con precios (queda pendiente hasta que el administrador la apruebe) y ve el estado de sus envíos.
 * El administrador ve esta misma pantalla, sin la parte de subir.
 */
import { api } from './api.js';
import { $, el, fmtNum, toast, debounce, rangoPaginas, icono, fechaCorta } from './util.js';
import { es, sesion } from './sesion.js';
import { listaBuscable } from './listas.js';

const P = { q: '', pagina: 1, tam: 50, pedido: 0 };
const ESTADOS = { pendiente: 'Pendiente de aprobación', aprobada: 'Aprobada', rechazada: 'Rechazada' };

/** «Mis fichas enviadas»: cada ficha que subió este proveedor y su estado (si se rechazó, el motivo). Nunca trae precios de nadie. */
async function cargarEnvios() {
  let lista;
  try { lista = await api.proveedorMisOfertas(); } catch (e) { toast(e.message, 'error'); return; }
  $('#prov-envios').replaceChildren(lista.length
    ? el('table', { class: 'adm-tabla prov-tabla' },
      el('thead', {}, el('tr', {}, ...['Enviada', 'Archivo', 'Productos con precio', 'Estado'].map((t) => el('th', {}, t)))),
      el('tbody', {}, lista.map((l) => el('tr', {},
        el('td', {}, fechaCorta(l.fecha)), el('td', {}, l.archivo || '—'), el('td', { class: 'num' }, fmtNum(l.filas)),
        el('td', {}, el('span', { class: `estado-lote ${l.estado}` }, ESTADOS[l.estado] || l.estado),
          l.estado === 'rechazada' && l.motivo && el('div', { class: 'nota' }, `Motivo: ${l.motivo}`))))))
    : el('p', { class: 'nota' }, 'Todavía no has enviado ninguna ficha.'));
}

/** Lo que se le muestra al proveedor justo después de subir: que quedó pendiente, cuántos precios entraron y qué se descartó. */
function mostrarResultado(r) {
  const dato = (texto) => el('li', {}, texto);
  const errores = (r.errores || []).slice(0, 10);
  $('#prov-resultado').replaceChildren(el('div', { class: 'resultado-ok' },
    el('p', {}, icono('check', 18), ' ', el('b', {}, 'Tu ficha quedó pendiente de aprobación.'), ' La Clínica la revisará y, si la aprueba, tus precios empezarán a competir.'),
    el('ul', { class: 'cifras-envio' },
      dato(`${fmtNum(r.guardadas)} producto(s) con precio`),
      r.omitidas > 0 && dato(`${fmtNum(r.omitidas)} sin precio (no los cotizaste)`),
      r.fuera_de_lista > 0 && dato(`${fmtNum(r.fuera_de_lista)} que hoy no necesitamos (no se tuvieron en cuenta)`),
      r.repetidas > 0 && dato(`${fmtNum(r.repetidas)} repetido(s): se usó el más barato`)),
    r.total_errores > 0 && el('div', { class: 'resultado-error' },
      el('p', {}, icono('alerta', 16), ` ${fmtNum(r.total_errores)} fila(s) con error (no se enviaron):`),
      el('ul', {}, errores.map((e) => el('li', {}, `Fila ${e.fila}: ${e.mensaje}`))),
      r.total_errores > errores.length && el('p', { class: 'nota' }, `Y ${fmtNum(r.total_errores - errores.length)} más.`))));
}

const LISTAS = {
  sin_oferta: ['Productos sin oferta', 'Insumos que la Clínica necesita y nadie ha cotizado todavía. Descarga la ficha con ellos, escribe tu precio y súbela.', 'Todos los productos que necesitamos ya tienen alguna oferta.'],
  nuevos: ['Productos nuevos', 'Productos nuevos que la Clínica necesita. Descarga la ficha con ellos, escribe tu precio y súbela.', 'Por ahora no hay productos nuevos por cotizar.'],
};

/** Las ventanas de los botones «Sin oferta» y «Nuevos»: la lista (solo código y descripción), su buscador y el botón para descargar la ficha con esos productos. */
function abrirLista(grupo) {
  const [titulo, sub, vacio] = LISTAS[grupo];
  $('#pl-titulo').textContent = titulo;
  $('#pl-sub').textContent = sub;
  listaBuscable({
    caja: $('#pl-cuerpo'),
    pedir: (q, pagina) => api.proveedorLista(grupo, { q, pagina, tam: 50 }),
    columnas: [{ titulo: 'Código', celda: (i) => el('span', { class: 'cod' }, i.cod) }, { titulo: 'Descripción', celda: (i) => i.descripcion }],
    descarga: { url: (q) => `/api/proveedor/excel?${new URLSearchParams({ grupo, q })}`, texto: 'la ficha de esos productos', etiqueta: 'Descargar ficha' },
    vacio,
  }).cargar();
  $('#dlg-prov-lista').showModal();
}

/** Sube la ficha: queda PENDIENTE (no compite hasta que el administrador la apruebe). */
async function subir(archivo) {
  const caja = $('#prov-resultado');
  caja.replaceChildren(el('p', { class: 'nota' }, 'Enviando tu ficha…'));
  try {
    mostrarResultado(await api.proveedorEnviarOferta(archivo));
    toast('Tu ficha quedó pendiente de aprobación.', 'ok');
    cargarEnvios();
  } catch (e) {
    caja.replaceChildren(el('p', { class: 'resultado-error' }, icono('alerta', 16), ` ${e.message}`));
  } finally {
    $('#prov-archivo').value = ''; // para poder volver a elegir el mismo archivo
  }
}

/** Pide la página actual al servidor y la dibuja. */
async function cargar() {
  const n = ++P.pedido;
  let r;
  try { r = await api.proveedorProductos({ q: P.q, pagina: P.pagina, tam: P.tam }); } catch (e) { toast(e.message, 'error'); return; }
  if (n !== P.pedido) return; // llegó una respuesta vieja: ya se pidió otra cosa
  P.pagina = r.pagina;
  $('#prov-total').textContent = `${fmtNum(r.total)} producto(s)`; // (OJO: no es #prov-cuenta, que es el de «Dónde comprar» del tablero)
  $('#prov-n-sin').textContent = fmtNum(r.conteos?.sin_oferta ?? 0); // los números de los botones «Sin oferta» y «Nuevos»
  $('#prov-n-nuevos').textContent = fmtNum(r.conteos?.nuevos ?? 0);
  $('#prov-tabla').replaceChildren(
    el('thead', {}, el('tr', {}, el('th', {}, 'Código'), el('th', {}, 'Descripción'))),
    el('tbody', {}, r.items.length
      ? r.items.map((i) => el('tr', {}, el('td', { class: 'p-cod' }, i.cod), el('td', { class: 'p-desc' }, i.descripcion)))
      : el('tr', {}, el('td', { class: 'vacio-tabla', colspan: 2 }, P.q ? 'Ningún producto coincide con lo que buscas.' : 'Por ahora no necesitamos ningún producto.'))));
  const ini = (r.pagina - 1) * r.tam + 1, fin = Math.min(r.total, r.pagina * r.tam);
  const ir = (p) => () => { P.pagina = p; cargar(); $('#prov-tabla').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  $('#prov-pag').replaceChildren(...(r.total ? [
    el('span', { class: 'num' }, `Mostrando ${fmtNum(ini)}–${fmtNum(fin)} de ${fmtNum(r.total)}`),
    r.paginas > 1 && el('div', { class: 'pags' },
      el('button', { type: 'button', disabled: r.pagina === 1, onclick: ir(r.pagina - 1), 'aria-label': 'Página anterior' }, '‹'),
      rangoPaginas(r.pagina, r.paginas).map((p) => (p === '…' ? el('span', { class: 'pts' }, '…')
        : el('button', { type: 'button', 'aria-current': p === r.pagina ? 'page' : false, onclick: ir(p), class: 'num' }, fmtNum(p)))),
      el('button', { type: 'button', disabled: r.pagina === r.paginas, onclick: ir(r.pagina + 1), 'aria-label': 'Página siguiente' }, '›')),
  ].filter(Boolean) : []));
}

/** Conecta el buscador. Devuelve `mostrar()` (entrar a la pantalla: pide los productos). */
export function montarProveedor() {
  $('#prov-q').addEventListener('input', debounce((ev) => { P.q = ev.target.value.trim(); P.pagina = 1; cargar(); }, 250));
  $('#prov-archivo').addEventListener('change', (ev) => { if (ev.target.files[0]) subir(ev.target.files[0]); });
  $('#prov-btn-sin').addEventListener('click', () => abrirLista('sin_oferta'));
  $('#prov-btn-nuevos').addEventListener('click', () => abrirLista('nuevos'));
  return {
    mostrar() {
      // Subir y ver los envíos es solo del proveedor; el administrador ve la pantalla igual que él, con una nota.
      $('#prov-envio').hidden = !es('externo');
      $('#prov-nota-admin').hidden = !es('admin');
      // Un usuario proveedor sin empresa no puede subir nada: se le dice qué hacer (el sistema ya no deja crearlo así, pero puede haber uno de antes).
      const sinProveedor = es('externo') && !sesion.usuario?.cod_empresa;
      $('#prov-subir').hidden = sinProveedor;
      $('#prov-resultado').replaceChildren(...(sinProveedor ? [el('p', { class: 'resultado-error' }, icono('alerta', 16), ' Tu usuario todavía no está ligado a un proveedor. Pídele al administrador que lo ligue (o que agregue tu empresa) para poder enviar tu oferta.')] : []));
      if (es('externo') && !sinProveedor) cargarEnvios();
      return cargar();
    },
  };
}
