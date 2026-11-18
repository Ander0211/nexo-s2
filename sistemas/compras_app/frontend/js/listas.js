/*
 * LISTA DE PRODUCTOS CON BUSCADOR Y DESCARGA
 * ==========================================
 * La usan las ventanas «Sin oferta» y «Nuevos» del proveedor (js/proveedor.js) y las pestañas «Sin oferta» y «Nuevos» del administrador
 * (js/alternativas.js). Dibuja: una barra con el BUSCADOR, cuántos hay y el botón de DESCARGAR el Excel; la tabla; y «Ver más» (pide
 * la siguiente página al servidor). La búsqueda se hace en el servidor y el Excel que se baja es el de lo que se está buscando.
 */
import { $, el, icono, fmtNum, toast, debounce, descargarConAviso } from './util.js';

/**
 * @param caja      el elemento donde se dibuja todo
 * @param pedir     (q, pagina) → Promise<{ total, items }>: pide al servidor esa página con esa búsqueda
 * @param columnas  [{ titulo, clase?, celda: (item) => texto o elemento }]
 * @param descarga  { url: (q) => dirección del Excel, texto: «lo que se prepara» (para el aviso), etiqueta?: texto del botón }
 * @param vacio     texto cuando no hay ningún producto
 * @returns         { cargar() } (vuelve a pedir desde la primera página) y { enfocar() }
 */
export function listaBuscable({ caja, pedir, columnas, descarga, vacio, placeholder = 'Buscar por código o descripción…' }) {
  const S = { q: '', pagina: 1, items: [], total: 0, pedido: 0 };
  const entrada = el('input', { type: 'search', class: 'lb-q', placeholder, autocomplete: 'off', 'aria-label': 'Buscar' });
  const cuenta = el('span', { class: 'nota lb-cuenta', 'aria-live': 'polite' });
  const bajar = el('a', { class: 'btn btn-primario', href: descarga.url(''), download: '' }, icono('descargar', 16), descarga.etiqueta || 'Descargar Excel');
  const tabla = el('table', { class: 'adm-tabla lb-tabla' });
  const mas = el('button', { class: 'btn btn-fantasma', type: 'button', hidden: true }, 'Ver más');
  caja.replaceChildren(
    el('div', { class: 'lb-barra' }, el('label', { class: 'buscador' }, icono('buscar', 18), entrada), cuenta, bajar),
    el('div', { class: 'adm-tabla-caja' }, tabla),
    el('div', { class: 'lb-mas' }, mas));

  function pintar() {
    tabla.replaceChildren(
      el('thead', {}, el('tr', {}, ...columnas.map((c) => el('th', { class: c.clase || false }, c.titulo)))),
      el('tbody', {}, S.items.length
        ? S.items.map((i) => el('tr', {}, ...columnas.map((c) => el('td', { 'data-et': c.titulo, class: c.clase || false }, c.celda(i)))))
        : el('tr', {}, el('td', { class: 'vacio-tabla', colspan: columnas.length }, S.q ? 'Nada coincide con lo que buscas.' : vacio))));
    cuenta.textContent = `${fmtNum(S.total)} producto(s)${S.items.length < S.total ? ` · mostrando ${fmtNum(S.items.length)}` : ''}`;
    mas.hidden = S.items.length >= S.total;
    bajar.href = descarga.url(S.q); // el Excel es el de lo que se está buscando
    bajar.classList.toggle('desactivado', !S.total);
  }

  async function cargar() {
    const n = ++S.pedido;
    S.pagina = 1;
    let r;
    try { r = await pedir(S.q, 1); } catch (e) { toast(e.message, 'error'); return; }
    if (n !== S.pedido) return; // llegó una respuesta vieja: ya se pidió otra búsqueda
    S.items = r.items;
    S.total = r.total;
    pintar();
  }

  mas.addEventListener('click', async () => {
    const n = S.pedido;
    let r;
    try { r = await pedir(S.q, S.pagina + 1); } catch (e) { toast(e.message, 'error'); return; }
    if (n !== S.pedido) return;
    S.pagina += 1;
    S.items = S.items.concat(r.items);
    pintar();
  });
  entrada.addEventListener('input', debounce(() => { S.q = entrada.value.trim(); cargar(); }, 250));
  bajar.addEventListener('click', (ev) => { ev.preventDefault(); if (S.total) descargarConAviso(bajar, descarga.texto); });
  return { cargar, enfocar: () => entrada.focus() };
}
