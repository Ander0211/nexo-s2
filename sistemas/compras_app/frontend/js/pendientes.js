/*
 * VENTANA «OFERTAS DE PROVEEDORES» (solo el administrador)
 * =======================================================
 * Las fichas con precios que los proveedores subieron desde su pantalla. No compiten hasta que el administrador las revisa:
 *   - LISTA: una tarjeta por ficha (proveedor, fecha, cuántos precios, estado); las pendientes primero. Con BUSCADOR.
 *   - DETALLE: cada precio frente a la mejor oferta de hoy y a lo que ese proveedor ya ofrecía, con el ahorro estimado (cantidad a comprar ×
 *     diferencia). Con BUSCADOR y botón para DESCARGAR la ficha como Excel. Desde ahí se APRUEBA (los precios pasan a competir en el tablero) o se
 *     RECHAZA: el MOTIVO es obligatorio, se le envía al proveedor por correo y lo ve en su pantalla. Reglas y datos: app/services/pendientes.py.
 */
import { api } from './api.js';
import { $, el, fmtMoney, fmtNum, toast, confirmar, fechaCorta } from './util.js';

const ESTADO = { pendiente: 'Pendiente', aprobada: 'Aprobada', rechazada: 'Rechazada' };
/** Un texto para comparar al buscar: sin tildes ni mayúsculas. */
const norm = (s) => String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const coincide = (q, ...campos) => !q || campos.some((c) => norm(c).includes(q));

/**
 * Conecta la ventana. `alCambiar` se llama cuando se aprueba o rechaza algo (para refrescar el tablero y la insignia del menú).
 * Devuelve `abrir()` (abre la ventana en la lista).
 */
export function montarPendientes({ alCambiar }) {
  const dlg = $('#dlg-pendientes');
  const pie = { volver: $('#pend-volver'), rechazar: $('#pend-rechazar'), aprobar: $('#pend-aprobar'), restaurar: $('#pend-restaurar'), excel: $('#pend-excel') };
  const buscador = $('#pend-q');
  let viendo = null; // { id, empresa, n, mejoran } de la ficha que se está revisando (null = se ve la lista)
  let datos = []; // la lista de fichas (para filtrarla sin volver a pedirla)
  let det = null; // el detalle de la ficha que se está viendo (idem)

  const cuerpo = () => $('#pend-cuerpo');
  const encabezado = (titulo, sub) => { $('#pend-titulo').textContent = titulo; $('#pend-sub').textContent = sub; };
  /**
   * Qué botones salen en el pie. `estado` es el de la ficha que se está viendo: PENDIENTE → «Aprobar» y «Rechazar»; ya decidida (aprobada o rechazada) →
   * solo «Restaurar» (que la deja otra vez pendiente). En la lista, o mientras carga (estado falso), no sale ninguno de los tres.
   */
  const botones = (detalle, estado, id) => {
    pie.volver.hidden = !detalle;
    pie.rechazar.hidden = pie.aprobar.hidden = !(detalle && estado === 'pendiente');
    pie.restaurar.hidden = !(detalle && (estado === 'aprobada' || estado === 'rechazada'));
    pie.excel.hidden = !detalle;
    if (detalle) pie.excel.href = `/api/pendientes/${id}/excel`;
    $('#pend-pista').hidden = detalle;
  };
  const busqueda = () => norm(buscador.value.trim());

  function tarjeta(l) {
    return el('article', { class: `pend-tarjeta ${l.estado}` },
      el('div', { class: 'pend-info' },
        el('strong', {}, l.empresa),
        el('span', { class: 'nota' }, `${fechaCorta(l.fecha)} · ${l.archivo || 'sin nombre'} · ${fmtNum(l.filas)} producto(s) con precio`),
        l.estado === 'rechazada' && l.motivo && el('span', { class: 'nota' }, `Motivo: ${l.motivo}`)),
      el('span', { class: `estado-lote ${l.estado}` }, ESTADO[l.estado]),
      el('button', { class: `btn ${l.estado === 'pendiente' ? 'btn-primario' : 'btn-fantasma'}`, type: 'button', onclick: () => detalle(l.id) },
        l.estado === 'pendiente' ? 'Revisar' : 'Ver'));
  }

  /** Dibuja la lista (con lo que haya escrito en el buscador). */
  function pintarLista() {
    const q = busqueda();
    const vista = datos.filter((l) => coincide(q, l.empresa, l.archivo, ESTADO[l.estado], l.motivo, l.usuario));
    cuerpo().replaceChildren(...(vista.length ? vista.map(tarjeta)
      : [el('p', { class: 'vacio-tabla' }, datos.length ? 'Nada coincide con lo que buscas.' : 'Ningún proveedor ha enviado una ficha todavía.')]));
  }

  /** La lista de fichas (las pendientes primero). */
  async function lista() {
    viendo = det = null;
    buscador.value = '';
    buscador.placeholder = 'Buscar por proveedor, archivo o estado…';
    botones(false, false);
    encabezado('Ofertas de proveedores', 'Fichas con precios que enviaron los proveedores. No compiten hasta que las apruebes.');
    cuerpo().replaceChildren(el('p', { class: 'nota' }, 'Cargando…'));
    try { datos = await api.pendientes(); } catch (e) { cuerpo().replaceChildren(el('p', { class: 'resultado-error' }, e.message)); return; }
    pintarLista();
  }

  /** Una fila del detalle: el producto, lo que propone el proveedor y cómo queda frente a la mejor oferta de hoy. */
  function fila(f) {
    const resultado = f.mejora
      ? el('span', { class: 'estado-lote aprobada' }, f.ahorro ? `Mejora · ahorra ${fmtMoney(f.ahorro)}` : 'Primera oferta')
      : el('span', { class: 'estado-lote pendiente' }, 'No mejora');
    return el('tr', {},
      el('td', { 'data-et': 'Producto' }, el('span', { class: 'cod' }, f.cod), ' ', f.descripcion),
      el('td', { 'data-et': 'A comprar', class: 'num' }, fmtNum(f.comprar)),
      el('td', { 'data-et': 'Disponible', class: 'num' }, f.disponible == null ? '—' : fmtNum(f.disponible),
        f.disponible != null && !f.alcanza && el('small', { class: 'nota' }, ` · faltan ${fmtNum(f.comprar - f.disponible)}`)),
      el('td', { 'data-et': 'Propone', class: 'num' }, el('b', {}, fmtMoney(f.valor)), f.presentacion && el('small', {}, ` · ${f.presentacion}`)),
      el('td', { 'data-et': 'Mejor hoy' }, f.mejor_valor != null ? `${fmtMoney(f.mejor_valor)} · ${f.mejor_empresa}` : 'Sin oferta',
        f.valor_actual != null && el('small', { class: 'nota' }, ` (ya ofrecía ${fmtMoney(f.valor_actual)})`)),
      el('td', { 'data-et': 'Resultado' }, resultado));
  }

  /** Dibuja el detalle de la ficha (con lo que haya escrito en el buscador). */
  function pintarDetalle() {
    const d = det;
    const l = d.lote;
    const q = busqueda();
    const filas = d.filas.filter((f) => coincide(q, f.cod, f.descripcion, f.mejor_empresa, f.presentacion));
    cuerpo().replaceChildren(
      el('div', { class: 'pend-resumen' },
        el('p', {}, el('b', {}, fmtNum(d.filas.length)), ' precio(s) enviado(s) · ', el('b', {}, fmtNum(d.mejoran)), ' mejoran la mejor oferta de hoy',
          d.ahorro_total > 0 && ` · ahorro estimado ${fmtMoney(d.ahorro_total)}`, q && ` · mostrando ${fmtNum(filas.length)}`),
        l.estado === 'rechazada' && l.motivo && el('p', { class: 'nota' }, `Rechazada: ${l.motivo}`)),
      el('div', { class: 'adm-tabla-caja' }, el('table', { class: 'adm-tabla pend-tabla' },
        el('thead', {}, el('tr', {}, ...['Producto', 'A comprar', 'Disponible', 'Propone', 'Mejor hoy', 'Resultado'].map((t) => el('th', {}, t)))),
        el('tbody', {}, filas.length ? filas.map(fila) : el('tr', {}, el('td', { class: 'vacio-tabla', colspan: 6 }, 'Nada coincide con lo que buscas.'))))));
  }

  /** Una ficha por dentro. */
  async function detalle(id) {
    botones(true, false, id);
    buscador.value = '';
    buscador.placeholder = 'Buscar por código, descripción o proveedor…';
    cuerpo().replaceChildren(el('p', { class: 'nota' }, 'Cargando…'));
    try { det = await api.pendiente(id); } catch (e) { toast(e.message, 'error'); return lista(); }
    const l = det.lote;
    viendo = { id, empresa: l.empresa, n: det.filas.length, mejoran: det.mejoran, estado: l.estado };
    encabezado(l.empresa, `${ESTADO[l.estado]} · enviada el ${fechaCorta(l.fecha)}${l.archivo ? ` · ${l.archivo}` : ''}`);
    botones(true, l.estado, id);
    pintarDetalle();
  }

  buscador.addEventListener('input', () => { if (det) pintarDetalle(); else pintarLista(); });
  pie.volver.addEventListener('click', lista);

  pie.aprobar.addEventListener('click', async () => {
    if (!viendo) return;
    const { id, empresa, n, mejoran } = viendo;
    const ok = await confirmar({
      titulo: '¿Aprobar esta ficha?',
      parrafos: [
        `Los ${fmtNum(n)} precio(s) de ${empresa} pasarán a competir en el tablero.`,
        `${fmtNum(mejoran)} mejoran la mejor oferta de hoy; los demás quedan como ofertas del proveedor pero no cambian lo que se compra.`,
        'Se le envía un correo al proveedor avisándole que la ficha fue aprobada y que la Clínica Pabón se pondrá en contacto con él.',
      ],
      boton: 'Sí, aprobar', cancelar: 'Revisar',
    });
    if (!ok) return;
    pie.aprobar.hidden = pie.rechazar.hidden = true; // al confirmar, «Aprobar» y «Rechazar» desaparecen YA (y no se pueden pulsar dos veces)
    try {
      const r = await api.aprobarPendiente(id);
      const resumen = `Ficha aprobada: ${fmtNum(r.nuevos)} oferta(s) nueva(s) y ${fmtNum(r.actualizados)} actualizada(s).`;
      const enviado = r.correo?.estado === 'enviado';
      toast(enviado ? `${resumen} Se le avisó al proveedor por correo: ${r.correo.detalle}` : `${resumen} Pero el correo al proveedor no salió: ${r.correo?.detalle || 'sin detalle'}`,
        enviado ? 'ok' : 'error', enviado ? 4500 : 9000);
      await alCambiar();
      await detalle(id); // se queda en la ficha: ahora dice «Aprobada» y ofrece «Restaurar»
    } catch (e) { toast(e.message, 'error'); await detalle(id); }
  });

  /** Rechazar: el MOTIVO es obligatorio (se le envía al proveedor por correo para que sepa qué corregir). */
  pie.rechazar.addEventListener('click', async () => {
    if (!viendo) return;
    const { id, empresa } = viendo;
    let escrito = '';
    for (;;) { // si cierran la pregunta sin escribir el motivo, se vuelve a pedir
      const motivo = el('input', { class: 'campo', type: 'text', maxlength: 300, value: escrito, placeholder: 'Motivo (obligatorio): le llega al proveedor por correo', 'aria-label': 'Motivo del rechazo' });
      const ok = await confirmar({
        titulo: '¿Rechazar esta ficha?',
        parrafos: [`Los precios de ${empresa} no entrarán al tablero. Escribe el motivo: se le envía por correo para que sepa qué corregir.`, motivo],
        boton: 'Sí, rechazar', peligro: true,
      });
      if (!ok) return;
      escrito = motivo.value.trim();
      if (escrito.length >= 3) break;
      toast('Escribe el motivo del rechazo: es lo que se le envía al proveedor.', 'error');
    }
    pie.aprobar.hidden = pie.rechazar.hidden = true; // al confirmar, los dos botones desaparecen YA
    try {
      const r = await api.rechazarPendiente(id, escrito);
      toast(r.correo?.estado === 'enviado' ? `Ficha rechazada. Se avisó por correo: ${r.correo.detalle}` : `Ficha rechazada, pero el correo no salió: ${r.correo?.detalle || 'sin detalle'}`,
        r.correo?.estado === 'enviado' ? 'ok' : 'error', r.correo?.estado === 'enviado' ? 4500 : 9000);
      await alCambiar();
      await detalle(id); // se queda en la ficha: ahora dice «Rechazada» (con su motivo) y ofrece «Restaurar»
    } catch (e) { toast(e.message, 'error'); await detalle(id); }
  });

  /** Restaurar: deshace la decisión y deja la ficha otra vez «Pendiente de revisión». Si estaba aprobada, también devuelve las ofertas a como estaban. */
  pie.restaurar.addEventListener('click', async () => {
    if (!viendo) return;
    const { id, empresa, estado } = viendo;
    const ok = await confirmar({
      titulo: '¿Restaurar esta ficha?',
      parrafos: [
        estado === 'aprobada'
          ? `Los precios de ${empresa} dejarán de competir: las ofertas que creó esta aprobación se quitan y las que actualizó vuelven a su precio de antes.`
          : `Se quita el rechazo de la ficha de ${empresa}.`,
        'La ficha vuelve a «Pendiente de revisión» para que decidas de nuevo.',
        'Se le enviará un correo al proveedor: «Lo sentimos. Nuestro equipo se encuentra revisando de nuevo sus ofertas. Muy pronto tendrá noticias.»',
        'El correo que ya se le envió al decidir no se puede retirar.',
      ],
      boton: 'Sí, restaurar', cancelar: 'Cancelar',
    });
    if (!ok) return;
    pie.restaurar.hidden = true;
    try {
      const r = await api.restaurarPendiente(id);
      const vueltas = r.revertidas ? ` ${fmtNum(r.revertidas)} oferta(s) volvieron a como estaban.` : '';
      const quietas = r.no_tocadas ? ` ${fmtNum(r.no_tocadas)} no se tocaron porque alguien las cambió después.` : '';
      const enviado = r.correo?.estado === 'enviado';
      const aviso = enviado ? ' Se le avisó al proveedor por correo.' : ` Pero el correo al proveedor no salió: ${r.correo?.detalle || 'sin detalle'}`;
      toast(`Ficha restaurada: vuelve a «Pendiente de revisión».${vueltas}${quietas}${aviso}`, enviado ? 'ok' : 'error', enviado ? 6000 : 9000);
      await alCambiar();
      await detalle(id); // ahora vuelve a ofrecer «Aprobar» y «Rechazar»
    } catch (e) { toast(e.message, 'error', 8000); await detalle(id); }
  });

  return { abrir() { dlg.showModal(); lista(); } };
}
