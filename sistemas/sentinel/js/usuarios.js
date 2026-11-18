/* SENTINEL PABON — página de usuarios.
   Todos: cambiar su clave. Administrador: crear usuarios (clave temporal enviada por correo y WhatsApp, como en SUMIPABON),
   dar clave nueva, editar datos, cambiar rol, activar/desactivar y eliminar. */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var YO = null, LISTA = [], CANALES = { correo: false, whatsapp: false };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  function msg(el, texto, bien) { el.textContent = texto; el.className = "msg " + (bien ? "ok" : "mal"); el.hidden = !texto; }
  async function api(url, datos) {
    var r = await fetch(url, datos === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) });
    if (r.status === 401) { location.href = "/login.html"; throw new Error("Sesión terminada"); }
    var j = {}; try { j = await r.json(); } catch (e) {}
    if (!r.ok || !j.ok) throw new Error(j.error || "No se pudo completar (" + r.status + ")");
    return j;
  }
  function fecha(iso) { return iso ? iso.replace("T", " ").slice(0, 16) : "—"; }
  function celularBonito(c) { var m = /^\+57(\d{3})(\d{3})(\d{4})$/.exec(c || ""); return m ? m[1] + " " + m[2] + " " + m[3] : (c || ""); }

  function pistaEnvio() {
    if (CANALES.aviso_whatsapp && /SUMIPABON/.test(CANALES.aviso_whatsapp)) return (CANALES.correo ? "Se enviarán por correo. " : "") + CANALES.aviso_whatsapp;
    if (CANALES.correo && CANALES.whatsapp) return "El usuario y la clave (creada automáticamente) se enviarán por correo y por WhatsApp.";
    var hay = CANALES.correo ? "Se enviarán por correo. " : CANALES.whatsapp ? "Se enviarán por WhatsApp. " : "";
    var faltan = [!CANALES.correo && "correo", !CANALES.whatsapp && "WhatsApp"].filter(Boolean).join(" ni ");
    return hay + "El envío automático por " + faltan + " no está configurado: al crear podrá copiar la clave" +
      (CANALES.whatsapp ? "." : " o abrir WhatsApp con el mensaje ya escrito.");
  }

  function pintar(lista) {
    LISTA = lista;
    $("tUsuarios").innerHTML = lista.map(function (u) {
      var yo = u.usuario === YO.usuario;
      var su = u.superusuario; // definido en el .env: no se modifica desde aquí
      var contacto = (u.correo || u.celular)
        ? "<span class=\"contacto\">" + (u.correo ? "<span>" + esc(u.correo) + "</span>" : "") + (u.celular ? "<span>" + esc(celularBonito(u.celular)) + "</span>" : "") + "</span>"
        : "—";
      var estado = !u.activo ? "<span class=\"chip off\">Desactivado</span>"
        : u.debe_cambiar ? "<span class=\"chip admin\" title=\"Aún no ha cambiado la clave temporal\">Clave temporal</span>"
        : "<span class=\"chip rev\">Activo</span>";
      return "<tr data-u=\"" + esc(u.usuario) + "\">" +
        "<td data-l=\"Nombre\"><span>" + esc(u.nombre) + (yo ? " <small>(usted)</small>" : "") + "</span></td>" +
        "<td data-l=\"Usuario\">" + esc(u.usuario) + (su ? " <span class=\"chip su\" title=\"Se define en el archivo .env\">Superusuario</span>" : "") + "</td>" +
        "<td data-l=\"Contacto\">" + contacto + "</td>" +
        "<td data-l=\"Rol\"><select data-a=\"rol\"" + (yo || su ? " disabled" : "") + ">" +
          "<option value=\"revisor\"" + (u.rol === "revisor" ? " selected" : "") + ">Revisor</option>" +
          "<option value=\"administrador\"" + (u.rol === "administrador" ? " selected" : "") + ">Administrador</option></select></td>" +
        "<td data-l=\"Estado\">" + estado + "</td>" +
        "<td data-l=\"Último ingreso\">" + fecha(u.ultimo_ingreso) + "</td>" +
        "<td class=\"acciones\">" + (su ? "<small class=\"su-nota\">Se administra en el archivo .env</small>" :
          "<button class=\"btn\" type=\"button\" data-a=\"datos\">Datos</button>" +
          (yo ? "" : "<button class=\"btn\" type=\"button\" data-a=\"clave\" title=\"Clave nueva automática, enviada por correo y WhatsApp\">Nueva clave</button>" +
                     "<button class=\"btn\" type=\"button\" data-a=\"activo\">" + (u.activo ? "Desactivar" : "Activar") + "</button>" +
                     "<button class=\"btn peligro\" type=\"button\" data-a=\"eliminar\">Eliminar</button>")) +
        "</td></tr>";
    }).join("");
  }

  /* Clave temporal (una sola vez) + resultado del correo y de WhatsApp */
  function mostrarTemporal(titulo, r) {
    $("dtTitulo").textContent = titulo;
    $("dtUsuario").textContent = r.usuario.usuario;
    $("dtClave").textContent = r.clave_temporal;
    var e = r.envio || {};
    var linea = function (nombre, x) { return x ? "<li class=\"envio " + esc(x.estado) + "\"><b>" + nombre + ":</b> " + esc(x.detalle) + "</li>" : ""; };
    $("dtEnvio").innerHTML = "<ul class=\"envios\">" + linea("Correo", e.correo) + linea("WhatsApp", e.whatsapp) + "</ul>" +
      (e.enlace_whatsapp ? "<a class=\"btn whatsapp\" target=\"_blank\" rel=\"noopener noreferrer\" href=\"" + esc(e.enlace_whatsapp) + "\">Abrir WhatsApp con el mensaje</a>" : "");
    $("dTemporal").showModal();
  }
  $("dtCopiar").addEventListener("click", async function () {
    try { await navigator.clipboard.writeText($("dtClave").textContent); $("dtCopiar").textContent = "Copiada ✓"; }
    catch (e) { $("dtCopiar").textContent = "Selecciónela y cópiela"; }
    setTimeout(function () { $("dtCopiar").textContent = "Copiar clave"; }, 2000);
  });
  $("dtCerrar").addEventListener("click", function () { $("dTemporal").close(); });
  // al cerrar, la clave y el enlace (que la lleva escrita) no se quedan en la pantalla
  $("dTemporal").addEventListener("close", function () { $("dtClave").textContent = ""; $("dtEnvio").innerHTML = ""; });

  async function accion(payload, okTexto) {
    try { var j = await api("/api/usuarios", payload); pintar(j.usuarios); msg($("mLista"), okTexto, true); return j; }
    catch (e) { msg($("mLista"), e.message, false); cargar(); }
  }

  $("tUsuarios").addEventListener("change", function (e) {
    var t = e.target; if (t.dataset.a !== "rol") return;
    var u = t.closest("tr").dataset.u;
    accion({ accion: "rol", usuario: u, rol: t.value }, "Rol de " + u + " cambiado a " + (t.value === "administrador" ? "Administrador" : "Revisor") + ".");
  });
  $("tUsuarios").addEventListener("click", async function (e) {
    var b = e.target.closest("button[data-a]"); if (!b) return;
    var u = b.closest("tr").dataset.u;
    var dato = LISTA.find(function (x) { return x.usuario === u; }) || {};
    if (b.dataset.a === "datos") {
      $("ddUsuario").textContent = u; $("dNombre").value = dato.nombre || ""; $("dCorreo").value = dato.correo || "";
      $("dCelular").value = celularBonito(dato.celular); msg($("mDatos"), "", true); $("fDatos").dataset.u = u; $("dDatos").showModal();
    } else if (b.dataset.a === "clave") {
      if (!confirm("¿Crearle a " + u + " una clave nueva? Su clave actual dejará de servir y se le enviará la nueva por correo y WhatsApp.")) return;
      b.disabled = true; b.textContent = "Enviando…";
      var j = await accion({ accion: "clave", usuario: u }, "Clave nueva para " + u + ".");
      if (j) mostrarTemporal("Clave nueva para " + u, j);
    } else if (b.dataset.a === "activo") {
      var activar = b.textContent === "Activar";
      accion({ accion: "activo", usuario: u, activo: activar }, u + (activar ? " activado." : " desactivado: ya no puede ingresar."));
    } else if (b.dataset.a === "eliminar") {
      if (confirm("¿Eliminar el usuario " + u + "? Esta acción no se puede deshacer.")) accion({ accion: "eliminar", usuario: u }, u + " eliminado.");
    }
  });

  $("fDatos").addEventListener("submit", async function (e) {
    e.preventDefault();
    var u = $("fDatos").dataset.u;
    try {
      var j = await api("/api/usuarios", { accion: "datos", usuario: u, nombre: $("dNombre").value, correo: $("dCorreo").value, celular: $("dCelular").value });
      pintar(j.usuarios); $("dDatos").close(); msg($("mLista"), "Datos de " + u + " guardados.", true);
    } catch (err) { msg($("mDatos"), err.message, false); }
  });
  $("ddCancelar").addEventListener("click", function () { $("dDatos").close(); });

  $("fCrear").addEventListener("submit", async function (e) {
    e.preventDefault();
    var b = $("bCrear"); b.disabled = true; b.textContent = "Creando y enviando…"; msg($("mCrear"), "", true);
    try {
      var j = await api("/api/usuarios", { accion: "crear", nombre: $("cNombre").value, usuario: $("cUsuario").value, rol: $("cRol").value,
                                           correo: $("cCorreo").value, celular: $("cCelular").value });
      pintar(j.usuarios); $("fCrear").reset();
      mostrarTemporal("Usuario " + j.usuario.usuario + " creado", j);
    } catch (err) { msg($("mCrear"), err.message, false); }
    b.disabled = false; b.textContent = "Crear y enviar";
  });

  $("fClave").addEventListener("submit", async function (e) {
    e.preventDefault();
    if ($("kNueva").value !== $("kNueva2").value) { msg($("mClave"), "Las dos claves nuevas no coinciden.", false); return; }
    try { await api("/api/mi-clave", { actual: $("kActual").value, nueva: $("kNueva").value }); msg($("mClave"), "Su clave fue cambiada.", true); $("fClave").reset(); }
    catch (err) { msg($("mClave"), err.message, false); }
  });

  async function cargar() {
    try { var j = await api("/api/usuarios"); CANALES = j.canales || CANALES; $("pistaEnvio").textContent = pistaEnvio(); pintar(j.usuarios); }
    catch (e) { msg($("mLista"), e.message, false); }
  }

  fetch("/api/sesion").then(function (r) { return r.json(); }).then(function (s) {
    if (!s.autenticado) { location.href = "/login.html"; return; }
    YO = s;
    var admin = s.rol === "administrador";
    $("yo").textContent = "Conectado como " + (s.nombre || s.usuario) + " (" + s.usuario + "), " + (s.superusuario ? "Superusuario" : admin ? "Administrador" : "Revisor") + ".";
    if (s.superusuario) { // su clave se cambia en el .env, no aquí
      $("fClave").hidden = true;
      msg($("mClave"), "Usted es el superusuario: su clave se define en el archivo .env (SENTINEL_SUPERUSUARIO_CLAVE, o la de SUMIPABON si SENTINEL no tiene una propia) y se aplica al reiniciar.", true);
    }
    $("titulo").textContent = admin ? "Usuarios" : "Mi clave";
    document.title = (admin ? "Usuarios" : "Mi clave") + " · SENTINEL PABON";
    ["pAdmin", "pCrear", "pLista"].forEach(function (id) { $(id).hidden = !admin; });
    if (admin) cargar();
  });
})();
