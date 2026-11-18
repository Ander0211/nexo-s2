/*
 * PANTALLA «USUARIOS» (solo administrador)
 * ========================================
 * Crear usuarios, darles un perfil, desactivarlos, restablecer su clave o eliminarlos. Las reglas (no quedarse sin
 * administradores, no editarse a sí mismo, claves temporales...) las aplica el servidor (app/services/seguridad.py);
 * aquí solo se muestra el resultado y, si algo no es válido, el mensaje que devuelve.
 *
 * Al crear un usuario o restablecer su clave, el servidor da una CLAVE TEMPORAL que se muestra UNA sola vez en una ventana
 * (con botón «Copiar»). El usuario deberá cambiarla al entrar.
 */
import { api } from './api.js';
import { $, $$, el, icono, toast, confirmar } from './util.js';
import { sesion } from './sesion.js';
import { conViaje } from './viaje.js';

/** Qué puede hacer cada perfil (texto de ayuda; lo que de verdad se permite lo decide el servidor). */
const PERFILES = [
  ['admin', 'Administrador', 'Todo: incluye la pantalla Administración (tablas, historial) y los usuarios.'],
  ['prime', 'Prime', 'Todo lo del menú menos Administración. Puede agregar ofertas, cargar datos y usar «Actualizar Excel».'],
  ['consulta', 'Consulta', 'Solo ve el tablero de compras. No edita ni descarga nada.'],
  ['externo', 'Proveedor externo', 'Ve qué productos necesita la Clínica, descarga la ficha y sube su oferta (queda pendiente hasta que el administrador la apruebe). Siempre va ligado a una empresa. No ve precios de otros.'],
];
const NOMBRE_PERFIL = Object.fromEntries(PERFILES.map(([id, nombre]) => [id, nombre]));

let lista = []; // los usuarios
let empresas = []; // proveedores, para ligar a un usuario externo
const NUEVO = '__nuevo__'; // el valor de la opción «Agregar un proveedor nuevo…» de la lista de proveedores
let canales = { correo: false, whatsapp: false }; // qué envíos automáticos tiene configurados el servidor
let editando = null; // el usuario que se edita en la ventana (null = crear uno nuevo)
let dlg, dlgTemporal;

/** Fecha de la base («2026-09-29 21:15:03») en formato corto («29/09 21:15»); «Nunca» si aún no entra. */
const fechaCorta = (f) => (f ? `${f.slice(8, 10)}/${f.slice(5, 7)} ${f.slice(11, 16)}` : 'Nunca');

/** Los usuarios desde el servidor, dibujados. */
async function cargar() {
  try { const r = await api.usuarios(); lista = r.usuarios; canales = r.canales || canales; } catch (e) { toast(e.message, 'error'); return; }
  pintar();
}

/** La tabla de usuarios, con sus botones. */
function pintar() {
  const yo = sesion.usuario?.id;
  const fila = (u) => el('tr', { class: u.activo ? '' : 'deshecho' },
    el('td', {}, el('b', {}, u.usuario), u.id === yo && el('span', { class: 'etq-yo' }, 'tú'), u.protegido && el('span', { class: 'etq-yo', title: 'Se define en el archivo .env' }, 'superusuario')),
    el('td', {}, u.nombre),
    el('td', { class: 'contacto' }, u.correo || u.celular ? [u.correo && el('span', {}, u.correo), u.celular && el('span', {}, u.celular)] : '—'),
    el('td', {}, el('span', { class: `etq-perfil ${u.rol}` }, u.rol_nombre)),
    el('td', {}, u.empresa || (u.rol === 'externo' ? el('span', { class: 'nota' }, 'Sin proveedor ligado') : '—')),
    el('td', {}, u.activo ? el('span', { class: 'estado ok' }, 'Activo') : el('span', { class: 'estado off' }, 'Desactivado'),
      u.cambiar_clave && el('small', { class: 'nota', style: 'display:block' }, 'Debe cambiar su clave')),
    el('td', { class: 'h-fecha' }, fechaCorta(u.ultimo_ingreso)),
    el('td', { class: 'c-acc acc-usuario' }, ...(u.protegido ? [el('small', { class: 'nota' }, 'Se define en .env')] : [
      el('button', { class: 'btn-icono', type: 'button', title: 'Editar', 'aria-label': `Editar a ${u.usuario}`, onclick: () => abrirFormulario(u) }, icono('editar', 15)),
      el('button', { class: 'btn-icono', type: 'button', title: 'Restablecer la clave', 'aria-label': `Restablecer la clave de ${u.usuario}`, onclick: () => restablecer(u) }, icono('llave', 15)),
      u.id !== yo && el('button', { class: `btn-activo ${u.activo ? 'desactivar' : 'activar'}`, type: 'button',
        title: u.activo ? 'Desactivar: no podrá entrar hasta que lo active de nuevo' : 'Activar: podrá volver a entrar',
        'aria-label': `${u.activo ? 'Desactivar' : 'Activar'} a ${u.usuario}`, onclick: () => cambiarActivo(u) }, u.activo ? 'Desactivar' : 'Activar'),
      u.id !== yo && el('button', { class: 'btn-icono peligro', type: 'button', title: 'Eliminar', 'aria-label': `Eliminar a ${u.usuario}`, onclick: () => eliminar(u) }, icono('papelera', 15))])));
  $('#us-tabla').replaceChildren(
    el('thead', {}, el('tr', {}, ['Usuario', 'Nombre', 'Contacto', 'Perfil', 'Proveedor', 'Estado', 'Último ingreso', ''].map((h) => el('th', {}, h)))),
    el('tbody', {}, lista.map(fila)));
}

/** Tarjetas con lo que puede hacer cada perfil (ayuda para elegir al crear usuarios). */
function pintarPerfiles() {
  $('#us-perfiles').replaceChildren(...PERFILES.map(([id, nombre, texto]) =>
    el('div', { class: `perfil-tarjeta ${id}` }, el('b', {}, nombre), el('span', {}, texto))));
}

/** Aviso bajo el formulario: qué envíos automáticos hay y cuáles no (así nadie espera un correo que no va a llegar). */
function pistaEnvio() {
  if (canales.correo && canales.whatsapp) return 'El usuario y la clave temporal se enviarán por correo y por WhatsApp a los datos que escribas.';
  const faltan = [!canales.correo && 'correo', !canales.whatsapp && 'WhatsApp'].filter(Boolean).join(' ni ');
  const hay = canales.correo ? 'Se enviarán por correo. ' : canales.whatsapp ? 'Se enviarán por WhatsApp. ' : '';
  return `${hay}El servidor aún no tiene configurado el envío automático por ${faltan}: al guardar podrás copiar la clave${canales.whatsapp ? '' : ' o abrir WhatsApp con el mensaje ya escrito'}.`;
}

/** Abre la ventana para crear (sin argumento) o editar un usuario. */
async function abrirFormulario(u = null) {
  editando = u;
  if (!empresas.length) { try { empresas = await api.empresas(); } catch { /* sin lista: solo no se podrá ligar un proveedor */ } }
  $('#us-titulo').textContent = u ? `Editar a ${u.usuario}` : 'Nuevo usuario';
  $('#us-sub').textContent = u ? 'Cambia el nombre, el perfil o si puede entrar.' : 'Se le dará una clave temporal que deberá cambiar al entrar; se la enviamos a su correo y a su celular.';
  const campo = (id, etiqueta, control) => el('div', { class: 'grupo' }, el('label', { class: 'etiqueta-campo', for: id }, ...(etiqueta.endsWith(' *') ? [etiqueta.slice(0, -2) + ' ', el('span', { class: 'req', 'aria-hidden': 'true' }, '*')] : [etiqueta])), control);
  const perfil = el('select', { id: 'us-rol', 'aria-label': 'Perfil' }, PERFILES.map(([id, nombre]) => el('option', { value: id, selected: (u?.rol || 'consulta') === id }, nombre)));
  // Un proveedor SIEMPRE va ligado a una empresa. Si la suya no está en la lista, se agrega ahí mismo («Agregar un proveedor nuevo…»).
  const proveedor = el('select', { id: 'us-empresa', 'aria-label': 'Proveedor' },
    el('option', { value: '' }, 'Elige un proveedor…'),
    empresas.map((e) => el('option', { value: e.cod, selected: u?.cod_empresa === e.cod }, `${e.nombre} (${e.cod})`)),
    el('option', { value: NUEVO }, '➕ Agregar un proveedor nuevo…'));
  const cajaProveedor = campo('us-empresa', 'Proveedor *', el('div', { class: 'campo' }, proveedor));
  const cajaNuevo = el('div', { class: 'prov-nuevo', id: 'us-prov-nuevo', hidden: true },
    el('p', { class: 'nota' }, 'Ese proveedor no está en la lista: se agrega ahora (a Administración → Empresas, sin repetir uno que ya exista) y queda ligado a este usuario.'),
    campo('us-pn-nombre', 'Nombre del proveedor *', el('div', { class: 'campo' }, el('input', { id: 'us-pn-nombre', type: 'text', autocomplete: 'off', placeholder: 'Razón social' }))),
    campo('us-pn-tel', 'Teléfono del proveedor *', el('div', { class: 'campo' }, el('input', { id: 'us-pn-tel', type: 'tel', autocomplete: 'off', placeholder: '3001234567' }))),
    campo('us-pn-correo', 'Correo del proveedor *', el('div', { class: 'campo' }, el('input', { id: 'us-pn-correo', type: 'email', autocomplete: 'off', placeholder: 'contacto@proveedor.com' }))));
  const alternar = () => {
    const externo = perfil.value === 'externo';
    cajaProveedor.hidden = !externo;
    cajaNuevo.hidden = !(externo && proveedor.value === NUEVO);
    if (!cajaNuevo.hidden) { // para no escribir dos veces: se propone el contacto de la persona (se puede cambiar)
      if (!$('#us-pn-tel').value) $('#us-pn-tel').value = $('#us-celular')?.value || '';
      if (!$('#us-pn-correo').value) $('#us-pn-correo').value = $('#us-correo')?.value || '';
    }
  };
  perfil.addEventListener('change', alternar);
  proveedor.addEventListener('change', alternar);
  $('#us-campos').replaceChildren(
    campo('us-usuario', 'Usuario *', el('div', { class: 'campo' }, el('input', { id: 'us-usuario', type: 'text', value: u?.usuario || '', readonly: !!u, autocomplete: 'off', autocapitalize: 'none', spellcheck: 'false', placeholder: 'ej. maria.perez' }))),
    campo('us-nombre', 'Nombre *', el('div', { class: 'campo' }, el('input', { id: 'us-nombre', type: 'text', value: u?.nombre || '', autocomplete: 'off', placeholder: 'Nombre para mostrar' }))),
    campo('us-correo', 'Correo electrónico *', el('div', { class: 'campo' }, el('input', { id: 'us-correo', type: 'email', required: true, value: u?.correo || '', autocomplete: 'off', autocapitalize: 'none', spellcheck: 'false', placeholder: 'nombre@dominio.com' }))),
    campo('us-celular', 'Celular / WhatsApp *', el('div', { class: 'campo' }, el('input', { id: 'us-celular', type: 'tel', required: true, value: u?.celular || '', autocomplete: 'off', placeholder: '300 123 4567' }))),
    campo('us-rol', 'Perfil', el('div', { class: 'campo' }, perfil)),
    cajaProveedor,
    cajaNuevo,
    ...(u ? [] : [el('p', { class: 'nota ayuda-envio' }, pistaEnvio())]),
    // replaceChildren escribe «null» como texto si recibe null: por eso la casilla solo se agrega al editar.
    ...(u ? [el('label', { class: 'casilla-activo' }, el('input', { id: 'us-activo', type: 'checkbox', checked: u.activo }), ' Puede entrar (activo)')] : []));
  alternar();
  $('#us-error').hidden = true;
  dlg.showModal();
  (u ? $('#us-nombre') : $('#us-usuario')).focus();
}

/** Una línea por canal con lo que pasó: enviado (verde), falló (rojo) o no se pudo intentar (gris). */
function pintarEnvio(envio) {
  const caja = $('#ct-envio');
  const linea = (nombre, r) => r && el('li', { class: `envio ${r.estado}` }, el('b', {}, `${nombre}: `), r.detalle);
  const enlace = envio?.enlace_whatsapp && el('a', { class: 'btn', href: envio.enlace_whatsapp, target: '_blank', rel: 'noopener noreferrer' }, 'Abrir WhatsApp con el mensaje');
  caja.replaceChildren(...(envio ? [el('ul', { class: 'envios' }, linea('Correo', envio.correo), linea('WhatsApp', envio.whatsapp)), ...(enlace ? [enlace] : [])] : []));
}

/** Muestra la clave temporal una sola vez, con el resultado de los envíos por correo y WhatsApp. */
function mostrarClaveTemporal(usuario, clave, envio) {
  $('#ct-usuario').textContent = usuario;
  $('#ct-clave').textContent = clave;
  pintarEnvio(envio);
  dlgTemporal.showModal();
}

/** Guarda el formulario: crea o edita, según `editando`. */
async function guardar() {
  const error = $('#us-error');
  const externo = $('#us-rol').value === 'externo';
  const elegido = externo ? $('#us-empresa').value : '';
  const cuerpo = {
    nombre: $('#us-nombre').value,
    rol: $('#us-rol').value,
    cod_empresa: externo && elegido && elegido !== NUEVO ? elegido : null,
    correo: $('#us-correo').value.trim() || null,
    celular: $('#us-celular').value.trim() || null,
  };
  if (externo && !elegido) { error.textContent = 'Elige el proveedor de este usuario, o agrégalo como nuevo en la lista.'; error.hidden = false; return; }
  if (externo && elegido === NUEVO) {
    const nuevo = { nombre: $('#us-pn-nombre').value.trim(), telefono: $('#us-pn-tel').value.trim(), correo: $('#us-pn-correo').value.trim() };
    if (!nuevo.nombre || !nuevo.telefono || !nuevo.correo) { error.textContent = 'Para agregar el proveedor nuevo escribe su nombre, su teléfono y su correo.'; error.hidden = false; return; }
    cuerpo.empresa_nueva = nuevo;
  }
  try {
    if (editando) {
      const r = await api.editarUsuario(editando.id, { ...cuerpo, activo: $('#us-activo').checked });
      dlg.close();
      toast(r?.proveedor_nuevo ? `Usuario guardado. Proveedor «${r.proveedor_nuevo.nombre}» agregado (código ${r.proveedor_nuevo.cod}).` : 'Usuario guardado.', 'ok');
      if (r?.proveedor_nuevo) empresas = []; // la lista de proveedores cambió: se vuelve a pedir la próxima vez
    } else {
      // La animación sale encima del formulario y dura lo que tarde el servidor. Si algo falla, se cierra y el formulario sigue
      // abierto con el mensaje de error (no se pierde lo escrito); si sale bien, el formulario se cierra y aparecen los datos.
      const r = await conViaje(() => api.crearUsuario({ ...cuerpo, usuario: $('#us-usuario').value }), {
        titulo: 'Creando el usuario…', conEnvio: canales.correo || canales.whatsapp,
      });
      dlg.close();
      if (r.proveedor_nuevo) { toast(`Proveedor «${r.proveedor_nuevo.nombre}» agregado (código ${r.proveedor_nuevo.cod}) y ligado al usuario.`, 'ok'); empresas = []; }
      mostrarClaveTemporal(r.usuario.usuario, r.clave_temporal, r.envio);
    }
    await cargar();
  } catch (e) { error.textContent = e.message; error.hidden = false; }
}

/** Restablecer la clave: pide confirmación y muestra la temporal nueva una sola vez. */
async function restablecer(u) {
  const ok = await confirmar({
    titulo: `¿Restablecer la clave de ${u.usuario}?`,
    parrafos: ['Se le pondrá una clave temporal nueva, se cerrarán sus sesiones abiertas y deberá cambiarla al entrar.'],
    boton: 'Restablecer', peligro: true,
  });
  if (!ok) return;
  try {
    const r = await conViaje(() => api.restablecerClave(u.id), {
      titulo: 'Restableciendo la clave…', conEnvio: canales.correo || canales.whatsapp,
    });
    mostrarClaveTemporal(r.usuario.usuario, r.clave_temporal, r.envio);
    await cargar();
  } catch (e) { toast(e.message, 'error'); }
}

/** Desactivar (no puede entrar; se cierran sus sesiones, conserva todo lo demás) o volver a activar. */
async function cambiarActivo(u) {
  if (u.activo) {
    const ok = await confirmar({
      titulo: `¿Desactivar a ${u.usuario}?`,
      parrafos: ['No podrá entrar a SUMIPABON y se cerrarán sus sesiones abiertas. Conserva sus datos: puedes activarlo de nuevo cuando quieras.'],
      boton: 'Desactivar', peligro: true,
    });
    if (!ok) return;
  }
  try {
    await api.activarUsuario(u.id, !u.activo);
    toast(u.activo ? `${u.usuario} desactivado: ya no puede entrar.` : `${u.usuario} activado: ya puede entrar.`, 'ok');
    await cargar();
  } catch (e) { toast(e.message, 'error'); }
}

/** Eliminar un usuario (con confirmación). */
async function eliminar(u) {
  const ok = await confirmar({
    titulo: `¿Eliminar a ${u.usuario}?`,
    parrafos: ['Dejará de poder entrar y se cerrarán sus sesiones. Si solo quieres que no entre por ahora, mejor usa «Desactivar».'],
    boton: 'Eliminar', peligro: true,
  });
  if (!ok) return;
  try { await api.eliminarUsuario(u.id); toast('Usuario eliminado.', 'ok'); await cargar(); } catch (e) { toast(e.message, 'error'); }
}

/** Conecta la pantalla y sus ventanas. Devuelve `mostrar()` (entrar a la pantalla: pide la lista). */
export function montarUsuarios() {
  dlg = $('#dlg-usuario'); dlgTemporal = $('#dlg-clave-temporal');
  pintarPerfiles();
  $('#us-nuevo').addEventListener('click', () => abrirFormulario());
  $('#us-guardar').addEventListener('click', guardar);
  $('#dlg-usuario').addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && ev.target.tagName === 'INPUT' && ['text', 'email', 'tel'].includes(ev.target.type)) { ev.preventDefault(); guardar(); } });
  $('#ct-copiar').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('#ct-clave').textContent); toast('Clave copiada.', 'ok'); } catch { toast('No se pudo copiar: selecciónala y cópiala a mano.', 'aviso'); }
  });
  dlgTemporal.addEventListener('close', () => { $('#ct-clave').textContent = ''; $('#ct-envio').replaceChildren(); }); // no dejar la clave en la pantalla (ni en el enlace de WhatsApp)
  return { mostrar: cargar };
}
