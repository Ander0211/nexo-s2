/*
 * EL PANEL DE OFERTAS (PODIO)
 * ===========================
 * Es el contenido de la ventana emergente «Ofertas del producto» (dlg-ofertas). Tiene tres PESTAÑAS:
 *
 *   🏆 Mejor oferta     la oferta más barata en grande, y por qué es la mejor (cuánto se ahorra frente a la 2.ª)
 *   ☰  Otras ofertas    la 2.ª y la 3.ª; con «Ver siguientes» se siguen mostrando la 4.ª, 5.ª, 6.ª... de 3 en 3
 *   ▦  Comparar todas   la vista de siempre: 🥇🥈🥉 lado a lado y, debajo, las siguientes
 *
 * Se abre desde la fila del producto: el botón «Mejor oferta» abre la ventana en la primera pestaña y «Otras ofertas»
 * en la segunda. Dentro de la ventana se cambia de vista con las pestañas (la tercera, «Comparar todas», solo está ahí).
 *
 * Uso (desde app.js):   const panel = montarPodio(contenedor, '5728', { pestana, alCambiar, abrirAgregar, alPestana })
 *                       panel.recargar()   // vuelve a pedir las ofertas (después de elegir, agregar o eliminar una)
 */
import { api } from './api.js';
import { nombreEmpresa } from './empresa.js';
import { el, icono, fmtNum, fmtMoney, fmtPct, toast } from './util.js';
import { puedeEditar } from './sesion.js';

// Cuántas ofertas se agregan con cada clic en «Ver siguientes».
const POR_PASO = 3;

/** El círculo con el número de puesto: oro (1), plata (2), bronce (3); gris para el resto. */
const medalla = (puesto) => el('span', { class: `medalla ${puesto <= 3 ? 'm' + puesto : 'mn'}` }, puesto);

/** Las etiquetitas de una oferta: de dónde viene, si hay empate de precio y si el usuario la eligió. */
function etiquetas(o, aMano) {
  return [
    // De dónde viene la oferta: escrita a mano, subida desde un Excel en «Cargar datos», o del portafolio base.
    o.origen === 'manual' ? el('span', { class: 'etiqueta manual' }, 'Agregada a mano')
      : o.origen === 'subido' ? el('span', { class: 'etiqueta subido' }, 'Subida de Excel')
        : el('span', { class: 'etiqueta excel' }, 'Portafolio'),
    o.empate && el('span', { class: 'etiqueta empate', title: 'Otro proveedor ofrece el mismo precio' }, 'Empate de precio'),
    o.es_elegida && aMano && el('span', { class: 'etiqueta mano' }, 'Elegida por ti'),
  ];
}

/** Línea de diferencia contra la mejor: «Precio más bajo» (1.ª) o «+$25 por unidad · +1,4% vs la mejor». */
function textoDif(o) {
  if (o.puesto === 1) return el('div', { class: 'dif mejor' }, 'Precio más bajo');
  return el('div', { class: 'dif peor num' }, `+${fmtMoney(o.dif_abs)} por unidad · ${fmtPct(o.dif_pct)} vs la mejor`);
}

/**
 * Dibuja el panel de ofertas de UN producto dentro de `cont`.
 *   cont     elemento donde se dibuja
 *   cod      código del producto
 *   pestana  pestaña con la que se abre: 'mejor' | 'otras' | 'todas'
 *   alCambiar   función a llamar cuando algo cambió (se eligió/agregó/eliminó una oferta) → la pantalla se refresca
 *   abrirAgregar función que abre el panel «Agregar oferta»
 *   alPestana   función a llamar cuando el usuario cambia de pestaña dentro del panel (la ventana cambia su título)
 * Devuelve { listo, recargar }: `listo` es la promesa de la primera carga y `recargar` vuelve a pedir las ofertas.
 */
export function montarPodio(cont, cod, { pestana = 'todas', alCambiar, abrirAgregar, alPestana }) {
  let datos = null; // última respuesta del servidor
  let ofertas = []; // ofertas ya cargadas (crece con cada clic en "ver siguientes")
  let cargando = false;
  let actual = pestana; // pestaña que se está viendo

  // ---- Acciones de los botones ----
  /** Elegir a mano un proveedor distinto (o el mismo) para este producto. */
  const elegir = async (o) => {
    try {
      await api.elegir(cod, o.cod_empresa);
      toast(`Se comprará a ${o.empresa}.`, 'ok');
      alCambiar(cod);
    } catch (e) { toast(e.message, 'error'); }
  };
  /** «Volver a la mejor oferta»: borra la elección manual. */
  const quitarEleccion = async () => {
    try { await api.quitarEleccion(cod); toast('Vuelve a elegirse la mejor oferta.', 'ok'); alCambiar(cod); }
    catch (e) { toast(e.message, 'error'); }
  };
  /** Eliminar una oferta agregada a mano (pide confirmación primero). */
  const eliminar = async (o) => {
    if (!confirm(`¿Eliminar la oferta que agregaste de ${o.empresa} (${fmtMoney(o.valor)})?`)) return;
    try { await api.eliminarOferta(o.id); toast('Oferta eliminada.', 'ok'); alCambiar(cod); }
    catch (e) { toast(e.message, 'error'); }
  };
  /** Cambia de pestaña dentro del panel (no vuelve a pedir datos: usa las ofertas ya cargadas). */
  const cambiarPestana = (id) => { actual = id; alPestana?.(id); pintar(); };

  // ---- Piezas de una oferta ----
  /** Botón «Elegir esta» o, si ya es la elegida, «✓ Elegida». */
  // El perfil «Consulta» solo mira: no ve «Elegir esta», eliminar, ni agregar ofertas (y el servidor tampoco se lo permitiría).
  const botonElegir = (o) => o.es_elegida
    ? el('button', { class: 'btn-elegir activa', type: 'button', 'aria-pressed': 'true' }, '✓ Elegida')
    : puedeEditar() && el('button', { class: 'btn-elegir', type: 'button', onclick: () => elegir(o) }, 'Elegir esta');
  /** Botón de papelera: solo existe en las ofertas agregadas a mano (o.eliminable). */
  const botonQuitar = (o) => puedeEditar() && o.eliminable && el('button', {
    class: 'btn-quitar', type: 'button', title: 'Eliminar esta oferta manual', 'aria-label': 'Eliminar oferta', onclick: () => eliminar(o),
  }, icono('papelera', 16));

  /** «Tiene N und: alcanza» o «Solo tiene N und: faltan M». Vacío si el proveedor no dijo cuántas unidades tiene (se supone que le alcanza). */
  const lineaDisponible = (o) => o.disponible == null ? null : el('div', { class: `disponible${o.alcanza ? '' : ' no-alcanza'}` },
    o.alcanza ? `Tiene ${fmtNum(o.disponible)} und: alcanza` : `Solo tiene ${fmtNum(o.disponible)} und: faltan ${fmtNum(o.faltan)}`);

  /**
   * El cuadro que explica a QUIÉN se le compra cuánto, cuando el mejor proveedor no tiene unidades para todo (o el elegido a mano no alcanza).
   * No sale si todo se le compra a un solo proveedor que alcanza (lo normal).
   */
  const panelReparto = () => {
    if (!(datos.repartido || datos.faltante || datos.excede_disponible)) return null;
    const lineas = datos.reparto || [];
    return el('div', { class: `reparto-panel${datos.faltante || datos.excede_disponible ? ' falta' : ''}` },
      el('h4', {}, datos.repartido ? 'La compra se reparte entre proveedores' : 'Cantidad disponible'),
      datos.repartido && el('p', {}, 'El mejor proveedor no tiene unidades para todo: se le compra lo que tenga y el resto al siguiente más barato.'),
      el('ul', {}, lineas.map((l) => el('li', {}, el('b', {}, l.empresa), ` · ${fmtNum(l.cantidad)} und × ${fmtMoney(l.valor)} = `, el('b', { class: 'num' }, fmtMoney(l.subtotal))))),
      datos.faltante > 0 && el('p', { class: 'mal' }, `Faltan ${fmtNum(datos.faltante)} unidades: ningún proveedor tiene suficientes. Pide más cotizaciones o agrega una oferta.`),
      datos.excede_disponible > 0 && el('p', { class: 'mal' }, `Elegiste a ${lineas[0]?.empresa} para las ${fmtNum(datos.comprar)} unidades, pero dijo tener menos: faltan ${fmtNum(datos.excede_disponible)}.`));
  };

  /** Tarjeta grande de una oferta. La 1.ª lleva la cinta «Mejor oferta». */
  const tarjeta = (o) => el('article', { class: `tarjeta p${o.puesto}${o.es_elegida ? ' elegida' : ''}` },
    o.puesto === 1 && el('span', { class: 'cinta' }, 'Mejor oferta'),
    el('div', { class: 'tarjeta-cab' }, medalla(o.puesto), nombreEmpresa(o.cod_empresa, o.empresa, o.empresa_nueva)),
    el('div', {},
      el('span', { class: 'precio-grande num' }, fmtMoney(o.valor)), el('span', { class: 'unidad' }, 'c/u'),
      o.presentacion && el('em', { class: 'pres', style: 'margin-left:8px' }, o.presentacion)),
    textoDif(o),
    lineaDisponible(o),
    el('div', { class: 'etiquetas' }, etiquetas(o, datos.elegida_a_mano)),
    // Total = cantidad a comprar × precio de esta oferta.
    el('div', { class: 'total' }, el('span', { class: 'num' }, `× ${fmtNum(datos.comprar)} und`), el('b', { class: 'num' }, fmtMoney(o.total))),
    el('div', { class: 'tarjeta-pie' }, botonElegir(o), botonQuitar(o)));

  /** Fila compacta para las ofertas 4.ª en adelante (las que aparecen con «Ver siguientes»). */
  const filaOferta = (o) => el('div', { class: `oferta-fila${o.es_elegida ? ' elegida' : ''}` },
    medalla(o.puesto),
    el('div', { style: 'min-width:0' }, nombreEmpresa(o.cod_empresa, o.empresa, o.empresa_nueva),
      lineaDisponible(o),
      el('div', { class: 'etiquetas', style: 'min-height:0;margin-top:3px' }, etiquetas(o, datos.elegida_a_mano))),
    el('div', { class: 'oculta-movil' }, o.presentacion && el('em', { class: 'pres' }, o.presentacion)),
    el('div', { class: 'precio num' }, fmtMoney(o.valor)),
    el('div', { class: 'dif peor num oculta-movil' }, fmtPct(o.dif_pct) + ' vs la mejor'),
    el('div', { class: 'der num oculta-movil' }, el('b', {}, fmtMoney(o.total))),
    el('div', { class: 'tarjeta-pie', style: 'margin:0;min-width:150px' }, botonElegir(o), botonQuitar(o)));

  /**
   * El botón «seguir adelante» (o «mostrar menos»), que comparten «Otras ofertas» y «Comparar todas».
   *   - si faltan ofertas por mostrar → «Ver siguientes N ofertas · quedan M más ›»
   *   - si ya se ven todas y son más de 3 → «‹ Mostrar solo ...» (textoMenos)
   */
  function controlMas(textoMenos) {
    const total = datos.total_ofertas;
    const restantes = total - ofertas.length;
    if (restantes > 0) {
      const n = Math.min(POR_PASO, restantes);
      return el('div', { class: 'mas' }, el('button', {
        class: 'btn-mas', type: 'button', disabled: cargando, onclick: masOfertas,
      }, `Ver siguientes ${n} oferta${n === 1 ? '' : 's'}`, restantes > n ? ` · quedan ${restantes - n} más` : '', ' ›'));
    }
    if (total > 3) return el('div', { class: 'mas' }, el('button', { class: 'btn btn-fantasma', type: 'button', onclick: soloTop3 }, textoMenos));
    return null;
  }

  // ---- Contenido de cada pestaña ----
  /** PESTAÑA «Mejor oferta»: la tarjeta de la 1.ª y, al lado, un resumen de por qué es la mejor. */
  function cuerpoMejor() {
    const m = ofertas[0], seg = ofertas[1], total = datos.total_ofertas;
    const lineas = [
      el('li', {}, 'Precio por unidad: ', el('b', { class: 'num' }, fmtMoney(m.valor)), m.presentacion ? ` · presentación ${m.presentacion}` : ''),
    ];
    if (seg) {
      // Comparación con la 2.ª: la diferencia por unidad y lo que se ahorra en toda la compra.
      lineas.push(el('li', {}, `La 2.ª (${seg.empresa}) cobra `, el('b', { class: 'num' }, fmtMoney(seg.valor)),
        `: ${fmtMoney(seg.dif_abs)} más por unidad (${fmtPct(seg.dif_pct)}).`));
      if (datos.comprar && !datos.repartido && !datos.faltante) { // con reparto el ahorro no es «diferencia × cantidad»: el cuadro de arriba lo explica
        lineas.push(el('li', {}, 'En esta compra ahorras ', el('b', { class: 'num ahorro' }, fmtMoney(seg.dif_abs * datos.comprar)),
          ` frente a la 2.ª (${fmtNum(datos.comprar)} und).`));
      }
    } else {
      lineas.push(el('li', {}, 'Es la única oferta de este producto.'));
    }
    if (datos.comprar && datos.repartido) {
      const pagar = (datos.reparto || []).reduce((s, l) => s + (l.subtotal || 0), 0);
      lineas.push(el('li', {}, 'Total a pagar con el reparto: ', el('b', { class: 'num' }, fmtMoney(pagar)), ` por ${fmtNum(datos.comprar - datos.faltante)} unidades.`));
    } else if (datos.comprar) lineas.push(el('li', {}, 'Total a pagar: ', el('b', { class: 'num' }, fmtMoney(m.total)), ` por ${fmtNum(datos.comprar)} unidades.`));
    if (m.empate) lineas.push(el('li', {}, 'Ojo: otro proveedor ofrece exactamente el mismo precio.'));
    return [el('div', { class: 'mejor-panel' },
      tarjeta(m),
      el('div', { class: 'mejor-resumen' },
        el('h4', {}, 'Por qué es la mejor'),
        el('ul', {}, lineas),
        total > 1 && el('button', { class: 'btn btn-fantasma', type: 'button', onclick: () => cambiarPestana('otras') }, total === 2 ? 'Ver la otra oferta ›' : `Ver las otras ${total - 1} ofertas ›`)))];
  }

  /** PESTAÑA «Otras ofertas»: la 2.ª y la 3.ª como tarjetas; las siguientes, como filas, con «Ver siguientes». */
  function cuerpoOtras() {
    const otras = ofertas.slice(1); // todo menos la mejor
    const grandes = otras.slice(0, 2); // 2.ª y 3.ª
    const partes = [el('div', { class: `podio ${grandes.length === 1 ? 'uno' : 'dos'}` }, grandes.map(tarjeta))];
    if (otras.length > 2) partes.push(el('div', { class: 'resto' }, otras.slice(2).map(filaOferta)));
    partes.push(controlMas('‹ Mostrar solo la 2.ª y la 3.ª'));
    return partes;
  }

  /** PESTAÑA «Comparar todas»: las 3 primeras lado a lado (el podio de siempre) y las siguientes como filas. */
  function cuerpoTodas() {
    const partes = [el('div', { class: 'podio' }, ofertas.slice(0, 3).map(tarjeta))];
    if (ofertas.length > 3) partes.push(el('div', { class: 'resto' }, ofertas.slice(3).map(filaOferta)));
    partes.push(controlMas('‹ Mostrar solo las 3 mejores'));
    return partes;
  }

  /** La tira de pestañas. «Otras ofertas» se apaga si el producto tiene una sola oferta. */
  function tiraDePestanas(total) {
    // Un botón de pestaña: su id, icono, texto, lo que va al final (el contador) y si está apagada.
    const pestanaBtn = (id, nombreIcono, texto, extra, apagada) => el('button', {
      class: 'pestana', type: 'button', role: 'tab', 'aria-selected': String(actual === id), disabled: apagada,
      onclick: () => cambiarPestana(id),
    }, icono(nombreIcono, 15), texto, extra);
    return el('div', { class: 'pestanas', role: 'tablist', 'aria-label': 'Qué ofertas ver' },
      pestanaBtn('mejor', 'trofeo', 'Mejor oferta', null, false),
      pestanaBtn('otras', 'lista', 'Otras ofertas', el('span', { class: 'n num' }, total - 1), total <= 1),
      pestanaBtn('todas', 'comparar', 'Comparar todas', null, false));
  }

  // ---- Dibujar todo el panel ----
  function pintar() {
    const total = datos.total_ofertas; // cuántas ofertas tiene el producto en total
    // Si se estaba en «Otras» y ya no hay otras (por ejemplo, se eliminó una oferta), se pasa a «Mejor».
    if (actual === 'otras' && total <= 1) { actual = 'mejor'; alPestana?.(actual); }
    const partes = [];
    // Encabezado: las pestañas y, a la derecha, «Mostrando 3 de 8».
    let cuenta = null;
    if (actual === 'todas') cuenta = `Mostrando ${fmtNum(ofertas.length)} de ${fmtNum(total)}`;
    if (actual === 'otras') cuenta = `Mostrando ${fmtNum(ofertas.length - 1)} de ${fmtNum(total - 1)} ${total === 2 ? 'otra oferta' : 'otras ofertas'}`;
    partes.push(el('div', { class: 'detalle-cab' },
      total ? tiraDePestanas(total) : el('h3', {}, 'Sin ofertas'),
      total > 0 && cuenta && el('span', { class: 'cuenta num' }, cuenta)));

    if (!total) {
      // Producto sin ninguna oferta: se invita a agregar la primera.
      partes.push(el('div', { class: 'vacio-ofertas' },
        icono('info', 26), el('strong', {}, 'Nadie ha cotizado este producto todavía'),
        puedeEditar() && el('span', {}, 'Agrega la primera oferta manualmente y aparecerá aquí como la mejor.'),
        puedeEditar() && el('button', { class: 'btn btn-primario', type: 'button', onclick: () => abrirAgregar(cod) }, icono('mas', 16), 'Agregar oferta')));
    } else {
      // El cuerpo cambia según la pestaña; el pie (agregar oferta / volver a la mejor) es igual en todas.
      partes.push(panelReparto(), ...(actual === 'mejor' ? cuerpoMejor() : actual === 'otras' ? cuerpoOtras() : cuerpoTodas()));
      if (puedeEditar()) {
        partes.push(el('div', { class: 'detalle-pie' },
          el('button', { class: 'btn', type: 'button', onclick: () => abrirAgregar(cod) }, icono('mas', 16), 'Agregar oferta manual a este producto'),
          datos.elegida_a_mano && el('button', { class: 'btn btn-fantasma', type: 'button', onclick: quitarEleccion }, 'Volver a la mejor oferta')));
      }
    }
    cont.replaceChildren(el('div', { class: 'detalle' }, partes));
  }

  // ---- Carga de datos ----
  /** Primera carga: pide al servidor las primeras ofertas (desde=0). */
  async function cargar() {
    datos = await api.ofertas(cod, 0, POR_PASO);
    ofertas = datos.ofertas;
    pintar();
  }
  /**
   * Vuelve a pedir las ofertas (algo cambió: se eligió, agregó o eliminó una) y redibuja, conservando
   * cuántas se estaban viendo. Si falla, deja lo que ya estaba dibujado y avisa.
   */
  async function recargar() {
    try {
      datos = await api.ofertas(cod, 0, Math.min(Math.max(ofertas.length, POR_PASO), 50)); // 50 = máximo que acepta la API
      ofertas = datos.ofertas;
      pintar();
    } catch (e) { toast(e.message, 'error'); }
  }
  /** El botón «seguir adelante»: pide las SIGUIENTES 3 (desde = las que ya se ven) y las agrega. */
  async function masOfertas() {
    cargando = true; pintar();
    try {
      const sig = await api.ofertas(cod, ofertas.length, POR_PASO);
      datos = { ...sig, ofertas: [] };
      ofertas = ofertas.concat(sig.ofertas);
    } catch (e) { toast(e.message, 'error'); }
    cargando = false; pintar();
  }
  /** «Mostrar solo las primeras»: recorta la lista a 3 sin volver a pedir nada al servidor. */
  function soloTop3() {
    ofertas = ofertas.slice(0, 3);
    pintar();
  }

  // Mientras llegan los datos se muestra una barra «esqueleto» que brilla.
  cont.replaceChildren(el('div', { class: 'esqueleto', style: 'height:150px;margin:6px 0' }));
  const listo = cargar().catch((e) => { cont.replaceChildren(el('div', { class: 'vacio-ofertas' }, e.message)); });
  return { listo, recargar };
}
