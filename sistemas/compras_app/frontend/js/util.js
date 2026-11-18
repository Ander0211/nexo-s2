/*
 * UTILIDADES COMPARTIDAS
 * ======================
 * Herramientas pequeñas que usan TODAS las pantallas (la principal y los paneles de
 * «Agregar oferta»). Aquí no hay lógica de negocio, solo ayudas:
 *
 *   $ y $$          buscar elementos en la página
 *   el()            crear elementos HTML de forma segura
 *   fmtNum/fmtMoney/fmtPct   dar formato colombiano a números, pesos y porcentajes
 *   icono()         dibujar los iconos
 *   debounce()      esperar a que el usuario deje de escribir
 *   contar()        animar un número (de 0 hasta su valor)
 *   toast()         los avisos flotantes de abajo a la derecha
 *   avisosAlFondo() lleva los avisos a la ventana que quede abierta (o a la página) al cerrar un panel emergente
 *   parseValor()    leer un número escrito por una persona («12.500», «12,5», «1.234,50»)
 */

// Atajos para buscar en la página:  $('#q') = un elemento;  $$('.fila') = una lista de elementos.
export const $ = (s, r = document) => r.querySelector(s);
// (Arriba: $ devuelve UN elemento; $$ devuelve TODOS los que coinciden, como una lista.)
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/**
 * Crea elementos SIN innerHTML: todo el texto se inserta como texto (a prueba de inyección).
 *
 * Uso:  el('div', { class: 'tarjeta', onclick: hacerAlgo }, 'Hola ', el('b', {}, 'mundo'))
 *   1.er parámetro → la etiqueta HTML ('div', 'button', ...)
 *   2.º parámetro  → sus atributos: class, id, onclick... (los valores false/null se omiten)
 *   el resto       → sus hijos: textos u otros elementos
 *
 * ¿Por qué no escribir HTML como texto? Porque si un nombre de proveedor o producto
 * contuviera código malicioso, se ejecutaría. Con textContent siempre se muestra como texto plano.
 */
export function el(tag, attrs = {}, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue; // atributo apagado: no se agrega
    if (k === 'class') e.className = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v); // onclick → evento "click"
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const h of hijos.flat(Infinity)) {
    if (h == null || h === false) continue; // permite escribir  condicion && el(...)  como hijo
    e.append(h instanceof Node ? h : document.createTextNode(String(h)));
  }
  return e;
}

// ---- Formatos numéricos colombianos: punto para miles, coma para decimales ----
// useGrouping:'always' fuerza el punto de miles incluso en números de 4 cifras (1.500).
const G = { useGrouping: 'always' };
const nf0 = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0, ...G }); // enteros
const nf2 = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2, ...G }); // hasta 2 decimales
const nfp = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 });       // porcentajes: 1 decimal
/** 16725 → "16.725"    ·    null → "—" */
export const fmtNum = (n) => (n == null ? '—' : Number.isInteger(n) ? nf0.format(n) : nf2.format(n));
/** 59000 → "$59.000" */
export const fmtMoney = (n) => (n == null ? '—' : '$' + fmtNum(Math.round(n * 100) / 100));
/** 11.8 → "+11,8%"    ·    -3 → "-3%" */
export const fmtPct = (p) => (p > 0 ? '+' : '') + nfp.format(p) + '%';

// ---- Iconos ----
// Cada icono es el «dibujo» (path) de un SVG de 24x24. Para agregar uno nuevo, se añade una línea aquí.
const ICONOS = {
  logo: '<path d="M4 20v-8h5v8M9.5 20V5h5v15M15 20v-10h5v10"/>',
  buscar: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  mas: '<path d="M12 5v14M5 12h14"/>',
  refrescar: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  descargar: '<path d="M12 4v11"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/>',
  alerta: '<path d="M12 4 3 20h18L12 4Z"/><path d="M12 10v4.5M12 17.5h.01"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  cesta: '<path d="M5 8h14l-1.5 10.5a2 2 0 0 1-2 1.5h-7a2 2 0 0 1-2-1.5L5 8Z"/><path d="m9 8 3-4 3 4"/>',
  moneda: '<circle cx="12" cy="12" r="9"/><path d="M14.5 9.2c-.6-.8-1.5-1.2-2.5-1.2-1.4 0-2.5.8-2.5 2s1 1.6 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1 0-2-.4-2.5-1.2M12 6.5V8M12 16v1.5"/>',
  ahorro: '<path d="m3 7 6 6 4-4 8 8"/><path d="M15 17h6v-6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  papelera: '<path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13"/>',
  trofeo: '<path d="M8 4h8v5a4 4 0 0 1-8 0V4Z"/><path d="M8 6H4v1a3 3 0 0 0 4 3M16 6h4v1a3 3 0 0 1-4 3M12 13v4M8 20h8"/>',
  subir: '<path d="M12 16V5"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>',
  archivo: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5"/>',
  lista: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  empresa: '<path d="M4 21V5l8-2 8 2v16M8 8h2M14 8h2M8 12h2M14 12h2M8 16h2M14 16h2M10 21v-3h4v3"/>',
  grafico: '<path d="M4 20V10M10 20V4M16 20v-7M2 20h20"/>',
  ojo: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  ojo_tachado: '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/>',
  tabla: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/>',
  editar: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/>',
  deshacer: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
  flecha: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  reloj: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  usuario: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  usuarios: '<circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3-5.5 7-5.5s7 2 7 5.5"/><path d="M17 4.5a3.5 3.5 0 0 1 0 7M19 15c2 .8 3 2.5 3 5"/>',
  llave: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M16 7l3 3"/>',
  salir: '<path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4"/><path d="m16 8 4 4-4 4M20 12H9"/>',
  copiar: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
  comparar: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
};
/** Iconos SVG: el marcado es constante (nunca incluye datos del usuario).
 *  icono('check', 20) → un check de 20 píxeles. Usa el color del texto que lo rodea (currentColor). */
export function icono(nombre, tam = 18, clase = '') {
  const t = document.createElement('template');
  t.innerHTML = `<svg width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="${clase}" aria-hidden="true">${ICONOS[nombre] || ''}</svg>`;
  return t.content.firstElementChild;
}

/**
 * Los números de página que se muestran en la paginación: la primera, la última y las cercanas a la actual, con «…»
 * donde se salta. rangoPaginas(7, 20) → [1, '…', 5, 6, 7, 8, 9, '…', 20]. La usan la lista del tablero y la administración.
 */
export function rangoPaginas(actual, total) {
  const set = new Set([1, total, actual, actual - 1, actual + 1, actual - 2, actual + 2].filter((n) => n >= 1 && n <= total));
  const lista = [...set].sort((a, b) => a - b), out = [];
  lista.forEach((n, k) => { if (k && n - lista[k - 1] > 1) out.push('…'); out.push(n); });
  return out;
}

/**
 * Ventana de confirmación («¿Eliminar esta fila?», «¿Restablecer la clave?», «¿Está seguro de la cantidad a comprar?»...). Usa el
 * <dialog id="dlg-confirmar"> de index.html. Con `peligro: true` la cabecera es roja; si no, azul («suave»). `cancelar` cambia el texto del botón
 * de salir (por defecto «Cancelar»). Los `parrafos` pueden ser textos o elementos ya armados.
 * Devuelve una promesa: true si la persona aceptó, false si canceló o cerró. El foco empieza en «Cancelar» (el lado seguro).
 *   confirmar({ titulo, parrafos: ['texto', ...], boton: 'Eliminar', peligro: true })
 */
export function confirmar({ titulo, parrafos = [], boton = 'Aceptar', cancelar = 'Cancelar', peligro = false }) {
  return new Promise((resolve) => {
    const dlg = $('#dlg-confirmar');
    $('#cf-titulo').textContent = titulo;
    $('#cf-cuerpo').replaceChildren(...parrafos.filter(Boolean).map((p) => (p instanceof Node ? p : el('p', {}, p))));
    $('#cf-cancelar').textContent = cancelar;
    dlg.classList.toggle('suave', !peligro);
    const ok = $('#cf-ok');
    ok.textContent = boton;
    ok.classList.toggle('btn-peligro', peligro);
    ok.classList.toggle('btn-primario', !peligro);
    let aceptado = false;
    const alAceptar = () => { aceptado = true; dlg.close(); };
    ok.addEventListener('click', alAceptar, { once: true });
    dlg.addEventListener('close', () => { ok.removeEventListener('click', alAceptar); resolve(aceptado); }, { once: true });
    dlg.showModal();
  });
}

/** «02/10 14:30» a partir de «2026-10-02 14:30:00» (la fecha como la guarda el servidor). */
export const fechaCorta = (f) => (f ? `${f.slice(8, 10)}/${f.slice(5, 7)} ${f.slice(11, 16)}` : '');

/** La pastilla «NUEVO» de un producto o una empresa que el sistema ve por primera vez (dura 7 días). `desde` = cuándo se vio. */
export function etiquetaNuevo(desde, que = 'Nuevo') {
  const cuando = desde ? ` el ${fechaCorta(desde)}` : '';
  return el('span', { class: 'etq-nuevo', title: `${que}: el sistema lo vio por primera vez${cuando}. La etiqueta dura 7 días.` }, 'Nuevo');
}

/**
 * Hace que las ventanas emergentes se puedan MOVER: se arrastra su cabecera (con el ratón o con el dedo) y se suelta donde estorbe menos;
 * doble clic (o doble toque) en la cabecera la devuelve al centro, y al cerrarla y abrirla de nuevo también vuelve al centro. Nunca se puede
 * sacar de la pantalla: siempre queda a la vista una franja de 120 px de la cabecera (más que el botón de cerrar) para volver a agarrarla.
 */
export function hacerMovibles(raiz = document) {
  raiz.querySelectorAll('dialog.modal').forEach((dlg) => {
    const cab = dlg.querySelector('.v-cab');
    if (!cab || dlg.dataset.movible) return;
    dlg.dataset.movible = '1';
    cab.classList.add('movible');
    cab.title = 'Arrastra para mover la ventana · doble clic para volver al centro';
    let x = 0, y = 0, agarre = null;
    const poner = () => { dlg.style.translate = x || y ? `${x}px ${y}px` : ''; };
    const reiniciar = () => { x = 0; y = 0; agarre = null; poner(); };
    cab.addEventListener('pointerdown', (ev) => {
      if (ev.button > 0 || ev.target.closest('button, a, input, select, textarea')) return;
      agarre = { px: ev.clientX, py: ev.clientY, x, y };
      cab.setPointerCapture(ev.pointerId);
    });
    cab.addEventListener('pointermove', (ev) => {
      if (!agarre) return;
      const r = dlg.getBoundingClientRect();
      const baseX = r.left - x, baseY = r.top - y; // dónde estaría sin moverla
      x = Math.min(innerWidth - 120 - baseX, Math.max(120 - r.width - baseX, agarre.x + ev.clientX - agarre.px)); // siempre quedan 120 px a la vista
      y = Math.min(innerHeight - 48 - baseY, Math.max(-baseY, agarre.y + ev.clientY - agarre.py)); // la cabecera nunca sale por arriba
      poner();
    });
    const soltar = () => { agarre = null; };
    cab.addEventListener('pointerup', soltar);
    cab.addEventListener('pointercancel', soltar);
    cab.addEventListener('dblclick', (ev) => { if (!ev.target.closest('button, a')) reiniciar(); });
    dlg.addEventListener('close', reiniciar);
  });
}

/**
 * Retrasa una función hasta que pasen `ms` milisegundos SIN que se vuelva a llamar.
 * Se usa en el buscador: en vez de consultar al servidor con cada tecla, espera a que
 * la persona termine de escribir (250 ms de pausa).
 */
export const debounce = (fn, ms = 250) => {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
};

/**
 * Anima un número hasta su valor nuevo (respeta "reducir movimiento").
 * Los números grandes de arriba «cuentan» desde el valor anterior hasta el nuevo en 650 ms.
 *   nodo    el elemento donde se escribe el número
 *   hasta   el valor final
 *   formato función que convierte el número en texto (fmtNum o fmtMoney)
 */
export function contar(nodo, hasta, formato = fmtNum, ms = 650) {
  const desde = Number(nodo.dataset.v ?? 0); // el valor anterior se guarda en data-v
  nodo.dataset.v = hasta;
  // Sin animación si la persona pidió "reducir movimiento" o si el número no cambió.
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || desde === hasta) { nodo.textContent = formato(hasta); return; }
  const t0 = performance.now();
  // Un «fotograma» de la animación: calcula el número intermedio y pide el siguiente fotograma hasta llegar al final.
  const paso = (t) => {
    const p = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - p, 3); // e: avance con «frenado» al final
    nodo.textContent = formato(Math.round(desde + (hasta - desde) * e));
    if (p < 1) requestAnimationFrame(paso); else nodo.textContent = formato(hasta);
  };
  requestAnimationFrame(paso);
}

/**
 * Muestra un aviso flotante abajo a la derecha que desaparece solo.
 *   tipo: 'ok' (verde) · 'error' (rojo) · 'aviso' (amarillo) · 'info' (azul, por defecto)
 */
export function toast(mensaje, tipo = 'info', ms = 4500) {  // con ms = 0 el aviso NO se quita solo: quien lo pidió lo cierra con el `cerrar()` que devuelve
  const caja = $('#toasts') || document.body.appendChild(el('div', { id: 'toasts' }));
  // Un panel emergente (<dialog>) abierto tapa todo lo demás, avisos incluidos: si hay uno abierto, el aviso se muestra dentro de él.
  (document.querySelector('dialog[open]') || document.body).append(caja);
  const t = el('div', { class: `toast ${tipo}`, role: 'status' },
    icono(tipo === 'ok' ? 'check' : tipo === 'error' ? 'alerta' : 'info', 18), el('span', {}, mensaje));
  caja.append(t);
  // Pasado el tiempo, primero se le pone la clase «sale» (animación de salida) y 320 ms después se elimina.
  const cerrar = () => { t.classList.add('sale'); setTimeout(() => t.remove(), 320); };
  if (ms > 0) setTimeout(cerrar, ms);
  return { cerrar };
}

/**
 * Descarga un archivo que el servidor tarda en preparar (la orden de compra, las alternativas, la ficha de cotización...). Un enlace normal
 * deja al navegador esperando EN SILENCIO y parece que no pasa nada; aquí se pide el archivo con fetch y mientras tanto: sale el aviso
 * «Preparando…», el botón se apaga (para no pedirlo dos veces) y su icono gira. Al llegar se guarda con el nombre que manda el servidor; si
 * falla, se dice por qué. Sin JavaScript el enlace (<a href download>) sigue funcionando.
 *   enlace      el <a> que se pulsó (su href es la dirección del archivo)
 *   queDescarga lo que se está preparando, para el aviso («la orden de compra»)
 */
export async function descargarConAviso(enlace, queDescarga) {
  if (enlace.dataset.ocupado) return;
  enlace.dataset.ocupado = '1';
  enlace.classList.add('preparando');
  enlace.setAttribute('aria-busy', 'true');
  const aviso = toast(`Preparando ${queDescarga}… puede tardar unos segundos.`, 'info', 0);
  try {
    const r = await fetch(enlace.getAttribute('href'), { credentials: 'same-origin' });
    if (!r.ok) {
      let mensaje = `No se pudo preparar ${queDescarga} (error ${r.status}).`;
      try { mensaje = (await r.json()).detail || mensaje; } catch { /* la respuesta no era JSON: se queda el mensaje general */ }
      throw new Error(mensaje);
    }
    const nombre = /filename="?([^";]+)"?/.exec(r.headers.get('Content-Disposition') || '')?.[1] || 'archivo.xlsx';
    const direccion = URL.createObjectURL(await r.blob());
    const a = el('a', { href: direccion, download: nombre });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(direccion), 10_000);
    aviso.cerrar();
    toast(`Listo: ${nombre}`, 'ok');
  } catch (e) {
    aviso.cerrar();
    toast(e.message || `No se pudo preparar ${queDescarga}.`, 'error', 8000);
  } finally {
    delete enlace.dataset.ocupado;
    enlace.classList.remove('preparando');
    enlace.removeAttribute('aria-busy');
  }
}

/**
 * Cambia de sitio el espacio de avisos al cerrar un panel emergente, donde pudo quedar escondido:
 * si debajo queda otra ventana abierta (por ejemplo «Ofertas del producto» tras cerrar «Agregar oferta») pasa a ella;
 * si no, vuelve a la página.
 */
export function avisosAlFondo() {
  const caja = $('#toasts');
  if (caja) (document.querySelector('dialog[open]') || document.body).append(caja);
}


/**
 * Convierte un número escrito por una persona en un número de verdad. Devuelve NaN si no es un número.
 *   "12.500" → 12500   ·   "12,5" → 12.5   ·   "1.234,50" → 1234.5   ·   "$ 8.700.000" → 8700000
 * En Colombia el punto separa los miles y la coma los decimales, pero la gente escribe de todas formas.
 * Regla: un punto (o coma) seguido de EXACTAMENTE 3 dígitos se toma como separador de miles.
 * La usan los dos paneles con formularios (agregar.js y cargar.js).
 */
export function parseValor(txt) {
  let s = String(txt || '').replace(/[^\d.,]/g, ''); // deja solo dígitos, puntos y comas
  if (!s) return NaN;
  const punto = s.includes('.'), coma = s.includes(',');
  // Si están los dos, el ÚLTIMO es el decimal y el otro es separador de miles.
  if (punto && coma) s = s.lastIndexOf(',') > s.lastIndexOf('.') ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
  else if (punto) { const p = s.split('.'); if (p.length > 2 || p.at(-1).length === 3) s = s.replace(/\./g, ''); }
  else if (coma) { const p = s.split(','); s = (p.length > 2 || p.at(-1).length === 3) ? s.replace(/,/g, '') : s.replace(',', '.'); }
  return Number(s);
}

/**
 * EL OJO DE LAS CLAVES: a cada campo de clave le agrega un botón con un ojo que deja VER lo que se está escribiendo (y volver a ocultarlo).
 * Se usa en el ingreso y en «Cambiar mi clave». Al limpiar el formulario (form.reset) la clave vuelve a quedar oculta.
 */
export function activarVerClave(raiz = document) {
  raiz.querySelectorAll('input[type="password"]').forEach((input) => {
    const caja = input.closest('.campo');
    if (!caja || caja.querySelector('.ver-clave')) return;
    const boton = el('button', { class: 'ver-clave', type: 'button', title: 'Mostrar la clave', 'aria-label': 'Mostrar la clave', 'aria-pressed': 'false' }, icono('ojo', 18));
    const poner = (visible) => {
      const pos = input.selectionStart; // para no perder el lugar del cursor al cambiar
      input.type = visible ? 'text' : 'password';
      boton.setAttribute('aria-pressed', String(visible));
      boton.title = boton.ariaLabel = visible ? 'Ocultar la clave' : 'Mostrar la clave';
      boton.replaceChildren(icono(visible ? 'ojo_tachado' : 'ojo', 18));
      input.focus();
      if (pos != null) input.setSelectionRange(pos, pos);
    };
    boton.addEventListener('click', () => poner(input.type === 'password'));
    input.form?.addEventListener('reset', () => { if (input.type !== 'password') poner(false); });
    caja.append(boton);
  });
}
