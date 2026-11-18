/*
 * PIEZAS VISUALES
 * ===============
 * Dos componentes que dibujan datos como gráficos sencillos (sin librerías externas):
 *   - medidorStock       la barrita de existencias de cada producto
 *   - barrasProveedores  el gráfico «Dónde comprar» del panel derecho
 */
import { el, etiquetaNuevo, fmtNum, fmtMoney } from './util.js';

/**
 * Barra de stock de un producto: cuánto hay comparado con el máximo.
 *   - el relleno es verde / amarillo / rojo según `nivel_stock` (lo calcula el servidor)
 *   - la rayita vertical marca el stock MÍNIMO
 *   - si el producto no tiene stock definido, solo dice «Sin stock definido»
 */
export function medidorStock(i) {
  if (!i.en_stock || i.stock_max == null) return el('div', { class: 'medidor sin' }, 'Sin stock definido');
  const max = i.stock_max || 1; // «|| 1» evita dividir por cero
  const pct = Math.min(100, (i.existencias / max) * 100); // % de llenado (tope 100)
  const minPct = i.stock_min ? Math.min(100, (i.stock_min / max) * 100) : null; // posición de la marca del mínimo
  return el('div', { class: `medidor ${i.nivel_stock}`, title: `Existencias ${fmtNum(i.existencias)} · mínimo ${fmtNum(i.stock_min)} · máximo ${fmtNum(i.stock_max)}` },
    el('div', { class: 'pista' },
      el('div', { class: 'relleno', style: `width:${pct}%` }),
      minPct != null && el('span', { class: 'minimo', style: `left:${minPct}%` })),
    el('div', { class: 'txt' },
      el('span', {}, el('b', { class: 'num' }, fmtNum(i.existencias)), ' en stock'),
      el('span', { class: 'num' }, 'máx ', fmtNum(i.stock_max))));
}

/**
 * Barras de inversión por proveedor ganador; al hacer clic filtra la lista.
 *   caja        el contenedor donde se dibujan las barras
 *   proveedores lista [{cod, nombre, productos, total}] ya ordenada de mayor a menor
 *   activo      código del proveedor actualmente filtrado (se resalta)
 *   alElegir    función que se ejecuta al hacer clic en una barra
 */
export function barrasProveedores(caja, proveedores, activo, alElegir) {
  caja.replaceChildren();
  const max = Math.max(...proveedores.map((p) => p.total), 1); // la barra más larga = el proveedor con más inversión
  for (const p of proveedores) {
    caja.append(el('button', {
      class: `barra-prov${activo === p.cod ? ' activa' : ''}`, type: 'button',
      title: `Ver los productos que se compran a ${p.nombre}`, onclick: () => alElegir(p),
    },
      el('span', { class: 'nombre' }, p.nombre, p.nuevo && etiquetaNuevo(null, 'Empresa nueva')),
      el('span', { class: 'monto num' }, fmtMoney(p.total)),
      // Ancho proporcional al mayor (mínimo 2% para que siempre se vea algo).
      el('span', { class: 'pista' }, el('i', { style: `width:${Math.max(2, (p.total / max) * 100)}%` })),
      el('span', { class: 'meta' }, `${fmtNum(p.productos)} producto${p.productos === 1 ? '' : 's'}`)));
  }
}
