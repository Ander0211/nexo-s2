/*
 * CLIENTE DE LA API
 * =================
 * Aquí está TODA la comunicación entre la pantalla y el servidor. Las pantallas nunca
 * llaman a fetch() directamente: usan `api.algo()`. Así, si una dirección del servidor
 * cambia, se corrige en un solo lugar.
 *
 * Cada función devuelve una promesa con la respuesta ya convertida a objeto JavaScript,
 * o lanza un Error con un mensaje legible en español si algo falla.
 */

/** Convierte el detalle de un error del servidor en un texto para el usuario. */
function mensaje(detail) {
  if (typeof detail === 'string') return detail; // errores propios (404, 409, 422 del importador...)
  if (Array.isArray(detail)) {
    // Errores de validación de FastAPI/Pydantic (vienen en inglés): se traducen los más comunes.
    return detail.map((d) => {
      const m = String(d.msg || '').replace(/^Value error, /, '');
      return /greater than 0/.test(m) ? 'El valor debe ser mayor que 0.' : m;
    }).join(' · ');
  }
  return 'Ocurrió un error inesperado.';
}

/** Hace la petición HTTP y devuelve el JSON; si falla, lanza un Error con un mensaje claro.
 *  Un 401 (la sesión terminó o venció) avisa a la página con el evento «sesion-vencida» para volver a la pantalla de ingreso;
 *  las llamadas de ingreso y de «¿quién soy?» lo desactivan con `{ alVencer: false }` porque para ellas un 401 es lo esperado. */
async function pedir(url, opciones = {}, { alVencer = true } = {}) {
  let r;
  try {
    r = await fetch(url, opciones);
  } catch {
    // fetch solo falla así cuando NO hay conexión con el servidor (por ejemplo, run.py se cerró).
    throw new Error('No se pudo conectar con el servidor. ¿Sigue corriendo run.py?');
  }
  if (!r.ok) {
    let texto = `Error ${r.status}`;
    try { texto = mensaje((await r.json()).detail); } catch { /* sin cuerpo JSON */ }
    // El error lleva también el código HTTP (404 = no existe, 409 = ya existe...) por si quien llama necesita distinguirlos.
    const error = new Error(texto);
    error.estado = r.status;
    if (r.status === 401 && alVencer) document.dispatchEvent(new CustomEvent('sesion-vencida'));
    throw error;
  }
  return r.json();
}
/** Arma las opciones de un envío con cuerpo JSON (POST / PUT). */
const json = (metodo, cuerpo) => ({ method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
/** Convierte un objeto en parámetros de dirección (?a=1&b=2), omitiendo los vacíos. */
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== '')).toString();

/** Una función por cada ruta del servidor (ver app/routers/ en el backend). */
export const api = {
  control: (p = {}) => pedir(`/api/control?${new URLSearchParams(p)}`),  // los tableros de control (empresas, precios y consumo)
  resumen: () => pedir('/api/resumen'),                                   // KPIs y datos del gráfico
  productos: (p) => pedir('/api/productos?' + qs(p)),                     // lista filtrada y paginada
  // Podio: desde=0 → 1.ª, 2.ª y 3.ª; desde=3 → las siguientes (botón «Ver siguientes»).
  ofertas: (cod, desde = 0, limite = 3) => pedir(`/api/productos/${encodeURIComponent(cod)}/ofertas?` + qs({ desde, limite })),
  elegir: (cod, cod_empresa) => pedir(`/api/productos/${encodeURIComponent(cod)}/seleccion`, json('PUT', { cod_empresa })),
  editarCantidad: (cod, cantidad) => pedir(`/api/productos/${encodeURIComponent(cod)}/cantidad`, json('PUT', { cantidad })), // fija a mano la cantidad a comprar
  restaurarCantidad: (cod) => pedir(`/api/productos/${encodeURIComponent(cod)}/cantidad`, { method: 'DELETE' }), // vuelve a la calculada
  fichaEmpresa: (cod) => pedir(`/api/empresas/${encodeURIComponent(cod)}/ficha`), // todo lo del proveedor (contacto, ofertas, cuánto se le compra)
  quitarEleccion: (cod) => pedir(`/api/productos/${encodeURIComponent(cod)}/seleccion`, { method: 'DELETE' }),
  agregarOferta: (cuerpo) => pedir('/api/ofertas', json('POST', cuerpo)), // panel «Agregar oferta»
  eliminarOferta: (id) => pedir(`/api/ofertas/${id}`, { method: 'DELETE' }),
  empresas: () => pedir('/api/empresas'),                                 // proveedores para el desplegable
  catalogo: (q) => pedir('/api/catalogo?' + qs({ q, limite: 10 })),       // buscador de productos
  avisos: () => pedir('/api/avisos'),                                     // avisos de calidad de datos

  // ---- Seguridad: sesión y usuarios (ver app/routers/sesion.py y usuarios.py) ----
  sesion: () => pedir('/api/sesion', {}, { alVencer: false }),             // ¿quién soy? (401 si no hay sesión)
  entrar: (usuario, clave) => pedir('/api/sesion', json('POST', { usuario, clave }), { alVencer: false }),
  salir: () => pedir('/api/sesion', { method: 'DELETE' }, { alVencer: false }),
  cambiarClave: (actual, nueva) => pedir('/api/sesion/clave', json('PUT', { actual, nueva }), { alVencer: false }),
  usuarios: () => pedir('/api/usuarios'),                                 // solo administrador
  crearUsuario: (cuerpo) => pedir('/api/usuarios', json('POST', cuerpo)), // devuelve la clave temporal (una sola vez)
  editarUsuario: (id, cuerpo) => pedir(`/api/usuarios/${id}`, json('PUT', cuerpo)),
  // «Adicionales»: código y descripción → Proveedor 1, 2 y 3 con su menor valor (app/routers/adicionales.py).
  adicionales: () => pedir('/api/adicionales'),
  adicionalesAgregar: (filas) => pedir('/api/adicionales', json('POST', { filas })),
  adicionalesSubir: (archivo) => pedir('/api/adicionales/archivo?' + qs({ nombre: archivo.name }), {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: archivo,
  }),
  adicionalesActivo: (id, activo) => pedir(`/api/adicionales/${id}/activo`, json('POST', { activo })),
  adicionalesQuitar: (id) => pedir(`/api/adicionales/${id}`, { method: 'DELETE' }),
  adicionalesVaciar: () => pedir('/api/adicionales', { method: 'DELETE' }),
  restablecerClave: (id) => pedir(`/api/usuarios/${id}/clave`, { method: 'POST' }),
  activarUsuario: (id, activo) => pedir(`/api/usuarios/${id}/activo`, json('POST', { activo })),
  eliminarUsuario: (id) => pedir(`/api/usuarios/${id}`, { method: 'DELETE' }),
  // Proveedor externo: SOLO qué y cuánto se necesita (sin precios).
  proveedorProductos: (p) => pedir('/api/proveedor/productos?' + qs(p)),
  proveedorExcelUrl: '/api/proveedor/excel',                              // enlace de descarga
  // El proveedor sube su ficha con precios (queda PENDIENTE hasta que el administrador la apruebe) y ve el estado de sus envíos.
  proveedorEnviarOferta: (archivo) => pedir('/api/proveedor/ofertas?' + qs({ nombre: archivo.name }), {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: archivo,
  }),
  proveedorMisOfertas: () => pedir('/api/proveedor/ofertas'),
  proveedorLista: (grupo, p) => pedir(`/api/proveedor/lista/${grupo}?` + qs(p)), // solo «sin_oferta» o «nuevos» (código y descripción)
  // El administrador revisa lo que enviaron los proveedores (app/routers/pendientes.py).
  pendientes: (estado) => pedir('/api/pendientes' + (estado ? '?' + qs({ estado }) : '')),
  pendiente: (id) => pedir(`/api/pendientes/${id}`),
  aprobarPendiente: (id) => pedir(`/api/pendientes/${id}/aprobar`, { method: 'POST' }),
  restaurarPendiente: (id) => pedir(`/api/pendientes/${id}/restaurar`, { method: 'POST' }), // deshace aprobar o rechazar: vuelve a «pendiente»
  rechazarPendiente: (id, motivo) => pedir(`/api/pendientes/${id}/rechazar`, json('POST', { motivo })),

  // ---- Pantalla «Administración»: las 5 tablas de los Excel (ver app/routers/admin.py) ----
  adminTablas: () => pedir('/api/admin/tablas'),                          // encabezados y número de filas de cada tabla
  // Una página de filas. p = {q, orden, sentido, pagina, tam, aviso, destino, solo_ids}
  adminFilas: (tabla, p) => pedir(`/api/admin/tablas/${tabla}/filas?` + qs(p)),
  adminCrear: (tabla, valores) => pedir(`/api/admin/tablas/${tabla}/filas`, json('POST', { valores })),
  adminGuardar: (tabla, id, valores) => pedir(`/api/admin/tablas/${tabla}/filas/${id}`, json('PUT', { valores })),
  adminEliminar: (tabla, ids) => pedir(`/api/admin/tablas/${tabla}/filas/eliminar`, json('POST', { ids })), // una o varias
  adminImpacto: (tabla, id) => pedir(`/api/admin/tablas/${tabla}/filas/${id}/impacto`), // qué pasaría si se elimina
  adminExcelUrl: (tabla) => `/api/admin/tablas/${tabla}/excel`,           // dirección de descarga (enlace, no petición)
  // Importar desde la carpeta data/excel: tablas = ['stock', ...], modo = 'reemplazar' | 'agregar'
  adminImportar: (tablas, modo) => pedir('/api/admin/importar', json('POST', { tablas, modo })),
  // Importar un archivo subido a UNA tabla (el archivo viaja tal cual como cuerpo, igual que en «Cargar datos»).
  adminSubir: (tabla, archivo, modo) =>
    pedir(`/api/admin/tablas/${tabla}/importar?` + qs({ nombre: archivo.name, modo }), {
      method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: archivo,
    }),
  adminHistorial: (tabla) => pedir('/api/admin/historial?' + qs({ tabla })),
  adminDeshacer: (id) => pedir(`/api/admin/historial/${id}/deshacer`, { method: 'POST' }),

  // ---- Ventana «Cargar datos»: productos y proveedores a mano ----
  producto: (cod) => pedir(`/api/productos/${encodeURIComponent(cod)}`),  // 404 si el código no existe todavía
  crearProducto: (cuerpo) => pedir('/api/productos', json('POST', cuerpo)),
  editarProducto: (cod, cuerpo) => pedir(`/api/productos/${encodeURIComponent(cod)}`, json('PUT', cuerpo)),
  eliminarProducto: (cod) => pedir(`/api/productos/${encodeURIComponent(cod)}`, { method: 'DELETE' }),
  crearEmpresa: (cuerpo) => pedir('/api/empresas', json('POST', cuerpo)),
  editarEmpresa: (cod, cuerpo) => pedir(`/api/empresas/${encodeURIComponent(cod)}`, json('PUT', cuerpo)),
  eliminarEmpresa: (cod) => pedir(`/api/empresas/${encodeURIComponent(cod)}`, { method: 'DELETE' }),

  // ---- Ventana «Cargar datos»: subir un Excel ----
  // El archivo viaja tal cual como cuerpo de la petición (sin formulario multipart); su nombre va en la dirección.
  //   aplicar=false → solo REVISAR (cuenta qué pasaría, no escribe)   ·   aplicar=true → CARGAR de verdad
  //   cod_empresa / empresa_nueva → solo cotizaciones: el proveedor elegido en pantalla
  subirArchivo: (tipo, archivo, { aplicar = false, cod_empresa, empresa_nueva } = {}) =>
    pedir(`/api/cargas/${tipo}?` + qs({ nombre: archivo.name, aplicar: aplicar ? 'true' : 'false', cod_empresa, empresa_nueva }), {
      method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: archivo,
    }),
};
