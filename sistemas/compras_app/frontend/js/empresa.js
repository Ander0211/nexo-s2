/*
 * FICHA DE LA EMPRESA
 * ===================
 * Al pulsar el NOMBRE de un proveedor (en la fila del producto o en las ofertas de «Mejor oferta» / «Otras ofertas») se abre
 * una ventana con todo lo que el sistema sabe de él (la arma el servidor: GET /api/empresas/{cod}/ficha):
 *   - quién es: código, de dónde viene, teléfono y correo (se escriben en Administración → Empresas)
 *   - cuánto pesa hoy: cuántas ofertas tiene, en cuántas es la mejor, a cuántos productos se le compraría y cuánta inversión
 *   - su lista de ofertas, producto por producto, con el puesto que ocupa frente a los demás (con buscador)
 */
import { api } from './api.js';
import { $, el, etiquetaNuevo, icono, fmtMoney, fmtNum, toast } from './util.js';

/** El nombre del proveedor como botón: al pulsarlo se abre su ficha. `ev.stopPropagation` evita activar la fila que lo contiene. */
export function nombreEmpresa(cod, nombre, nueva = false) {
  const boton = el('button', {
    class: 'prov enlace-empresa', type: 'button', title: `Ver toda la información de ${nombre}`,
    onclick: (ev) => { ev.stopPropagation(); abrirEmpresa(cod); },
  }, nombre);
  return nueva ? el('span', { class: 'prov-fila' }, boton, etiquetaNuevo(null, 'Empresa nueva')) : boton; // empresa nueva: lleva la pastilla «Nuevo»
}

/** Sin tildes y en minúsculas, para buscar «ñandu» y encontrar «ÑANDÚ». */
const plano = (s) => String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

let pedido = 0; // si se abre otra ficha mientras llega la anterior, la vieja se descarta

/** Abre la ventana y la llena con la ficha de la empresa `cod`. */
export async function abrirEmpresa(cod) {
  const dlg = $('#dlg-empresa');
  const mio = ++pedido;
  $('#emp-titulo').replaceChildren('Cargando…');
  $('#emp-sub').textContent = '';
  $('#emp-cuerpo').replaceChildren(el('div', { class: 'esqueleto' }), el('div', { class: 'esqueleto' }));
  if (!dlg.open) dlg.showModal();
  let ficha;
  try {
    ficha = await api.fichaEmpresa(cod);
  } catch (e) {
    if (mio === pedido) { dlg.close(); toast(e.message, 'error'); }
    return;
  }
  if (mio === pedido) pintar(ficha);
}

/** Un dato de contacto: con enlace para llamar o escribir, o «Sin registrar» si falta. */
function dato(titulo, valor, enlace) {
  return el('div', { class: 'ficha-dato' },
    el('small', {}, titulo),
    valor ? (enlace ? el('a', { href: enlace }, valor) : el('strong', {}, valor)) : el('span', { class: 'sin-dato' }, 'Sin registrar'));
}

function cifra(titulo, valor, nota) {
  return el('div', { class: 'ficha-cifra' }, el('small', {}, titulo), el('strong', { class: 'num' }, valor), nota && el('span', {}, nota));
}

function pintar(f) {
  $('#emp-titulo').replaceChildren(...[f.nombre, f.nuevo ? etiquetaNuevo(f.nuevo_desde, 'Empresa nueva') : null].filter(Boolean));
  $('#emp-sub').textContent = `Código ${f.cod} · ${f.origen_texto}`;

  const contacto = el('section', { class: 'ficha-contacto', 'aria-label': 'Datos de contacto' },
    dato('Teléfono', f.telefono, f.telefono && `tel:${f.telefono}`),
    dato('Correo electrónico', f.correo, f.correo && `mailto:${f.correo}`),
    dato('Código', f.cod),
    dato('Origen', f.origen_texto));
  const sinContacto = !f.telefono && !f.correo;

  const cifras = el('section', { class: 'ficha-cifras', 'aria-label': 'Resumen de compras' },
    cifra('Ofertas', fmtNum(f.n_ofertas), 'productos que ofrece'),
    cifra('Mejor oferta en', fmtNum(f.n_mejores), 'productos'),
    cifra('Se le compraría', fmtNum(f.n_elegidas), 'productos'),
    cifra('Inversión', fmtMoney(f.inversion), 'con lo que hoy se le compraría'));

  const lista = el('div', { class: 'ficha-lista', role: 'list' });
  const cuenta = el('small', { class: 'nota', 'aria-live': 'polite' });
  const buscador = el('input', {
    type: 'search', class: 'ficha-buscar', placeholder: 'Buscar entre sus ofertas…', autocomplete: 'off', 'aria-label': 'Buscar entre las ofertas de la empresa',
  });
  const filas = f.ofertas.map((o) => ({ o, texto: plano(`${o.cod_producto} ${o.descripcion}`) }));

  const fila = (o) => el('div', { class: `fo-fila${o.es_elegida ? ' elegida' : ''}`, role: 'listitem' },
    el('div', { class: 'fo-prod' }, el('span', { class: 'cod' }, o.cod_producto), el('span', { class: 'desc', title: o.descripcion }, o.descripcion)),
    el('div', { class: 'fo-pres' }, o.presentacion || '—'),
    el('div', { class: 'fo-valor num' }, fmtMoney(o.valor)),
    el('div', { class: `fo-puesto${o.es_mejor ? ' mejor' : ''}` }, o.es_mejor ? icono('trofeo', 13) : null, `${o.puesto}.ª de ${o.n_ofertas}`),
    el('div', { class: 'fo-compra' },
      o.es_elegida ? el('span', { class: 'etiqueta mano' }, 'Se le compra') : null,
      o.es_elegida ? el('small', { class: 'num' }, `${fmtNum(o.comprar)} und · ${fmtMoney(o.total)}`) : el('small', {}, o.comprar ? 'Se compra a otra empresa' : '—')));

  const dibujar = () => {
    const palabras = plano(buscador.value).split(/\s+/).filter(Boolean);
    const vistas = filas.filter((x) => palabras.every((p) => x.texto.includes(p)));
    lista.replaceChildren(...(vistas.length ? vistas.map((x) => fila(x.o)) : [el('div', { class: 'vacio-ficha' }, f.ofertas.length ? 'Ninguna oferta coincide con lo que buscas.' : 'Esta empresa todavía no tiene ofertas.')]));
    cuenta.textContent = f.ofertas.length ? `Mostrando ${fmtNum(vistas.length)} de ${fmtNum(f.ofertas.length)} ofertas` : '';
  };
  buscador.addEventListener('input', dibujar);
  dibujar();

  $('#emp-cuerpo').replaceChildren(
    contacto,
    sinContacto && el('p', { class: 'nota ficha-aviso' }, 'Esta empresa no tiene teléfono ni correo registrados. Se escriben en Administración → Empresas.'),
    cifras,
    el('section', { class: 'ficha-ofertas', 'aria-label': 'Ofertas de la empresa' },
      el('div', { class: 'ficha-ofertas-cab' }, el('h2', {}, 'Sus ofertas'), buscador, cuenta),
      el('div', { class: 'fo-cab', 'aria-hidden': 'true' }, el('span', {}, 'Producto'), el('span', {}, 'Presentación'), el('span', {}, 'Valor'), el('span', {}, 'Puesto'), el('span', {}, 'Compra')),
      lista));
  $('#emp-cuerpo').scrollTop = 0;
}
