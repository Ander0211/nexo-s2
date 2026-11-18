/*
 * SESIÓN: QUIÉN ESTÁ USANDO LA APLICACIÓN
 * =======================================
 * Guarda el usuario que inició sesión (lo llena app.js después de preguntarle al servidor) y responde «¿puede este perfil…?».
 * OJO: esconder botones según el perfil es solo comodidad. La seguridad de verdad la hace el SERVIDOR en cada petición
 * (app/autorizacion.py): aunque alguien mostrara un botón escondido, el servidor respondería 403.
 *
 * Los perfiles: admin · prime · consulta · externo (ver app/services/seguridad.py).
 */
export const sesion = { usuario: null }; // {id, usuario, nombre, rol, rol_nombre, cod_empresa, cambiar_clave...} o null

/** El perfil actual («admin», «prime», «consulta», «externo») o null si no hay sesión. */
export const rol = () => sesion.usuario?.rol ?? null;

/** ¿El perfil actual es uno de estos?   es('admin', 'prime') */
export const es = (...roles) => roles.includes(rol());

/** ¿Puede cambiar cosas (elegir proveedor, agregar ofertas, cargar datos…)? Administrador y prime. */
export const puedeEditar = () => es('admin', 'prime');
