/*
 * VENTANA «ALTERNATIVAS 2.º A 4.º» (administrador y Prime)
 * ========================================================
 * Baja el libro con las mismas tres hojas de la OC (VALORES, DINAMICA y ORDENES) para la 2.ª, 3.ª y 4.ª oferta de cada producto. Se ajusta a lo que se
 * elija en el tablero: si se elige otra oferta en vez de la mejor, esa pasa a ser la de la OC y la que era la mejor se vuelve la alternativa 2.ª.
 * (Los productos «Sin oferta» y «Nuevos» NO van aquí: están en «Productos que necesitamos», con su buscador y su descarga.)
 */
import { $, el, icono, descargarConAviso } from './util.js';

export function montarAlternativas() {
  const dlg = $('#dlg-alternativas');
  function dibujar() {
    $('#alt-cuerpo').replaceChildren(el('div', { class: 'alt-intro' },
      el('p', {}, 'Un libro de Excel con las ', el('b', {}, 'mismas tres hojas de la OC'), ' (VALORES, DINAMICA y ORDENES) para la ', el('b', {}, '2.ª, 3.ª y 4.ª oferta'), ' de cada producto: 9 hojas en total.'),
      el('p', { class: 'nota' }, 'Se ajusta a lo que elijas: si en el tablero eliges una oferta distinta de la mejor, esa pasa a ser la de la OC y la que era la mejor se vuelve la alternativa 2.ª.'),
      el('a', { id: 'alt-descargar', class: 'btn btn-primario', href: '/api/exportar/alternativas', download: '',
        onclick: (ev) => { ev.preventDefault(); descargarConAviso(ev.currentTarget, 'las alternativas 2.º a 4.º'); } },
      icono('descargar', 16), 'Descargar alternativas')));
  }
  return { abrir() { dlg.showModal(); dibujar(); } };
}
