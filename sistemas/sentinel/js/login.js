/* Pantalla de ingreso de SENTINEL PABON: ingreso, primer administrador y cambio de la clave temporal. */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var claveRecienUsada = "";
  function error(el, msg) { el.textContent = msg; el.hidden = !msg; }
  async function enviar(url, datos) {
    var r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) });
    var j = {};
    try { j = await r.json(); } catch (e) {}
    if (!r.ok || !j.ok) throw new Error(j.error || "No se pudo completar (" + r.status + ")");
    return j;
  }
  function soloMostrar(id) {
    ["fIngreso", "fPrimera", "fCambiar", "aRemoto"].forEach(function (x) { $(x).hidden = x !== id; });
  }
  function pedirCambio(conActual) {
    soloMostrar("fCambiar");
    if (conActual) { $("kActual").value = conActual; $("lActual").hidden = true; $("kNueva").focus(); }
    else { $("lActual").hidden = false; $("kActual").focus(); }
  }

  // Enlace del correo / WhatsApp: /login.html?ingresar=1&usuario=...
  // Cierra la sesión que hubiera en este navegador (p. ej. la del administrador) y deja el usuario escrito.
  var params = new URLSearchParams(location.search);
  var desdeEnlace = params.get("ingresar") === "1";
  var usuarioEnlace = (params.get("usuario") || "").trim();
  if (desdeEnlace) history.replaceState(null, "", "/login.html");

  (desdeEnlace ? fetch("/api/logout", { method: "POST" }).catch(function () {}) : Promise.resolve())
  .then(function () { return fetch("/api/sesion"); }).then(function (r) { return r.json(); }).then(function (s) {
    if (desdeEnlace && s.configurado) {
      soloMostrar("fIngreso");
      // que el navegador no rellene con el usuario y la clave guardados de otra persona (p. ej. el administrador)
      $("iUsuario").setAttribute("autocomplete", "off");
      $("iClave").setAttribute("autocomplete", "one-time-code");
      $("iClave").value = "";
      if (usuarioEnlace) {
        $("iUsuario").value = usuarioEnlace;
        $("subIngreso").textContent = "Escriba la clave que le llegó por correo o WhatsApp.";
        $("iClave").focus();
      } else { $("iUsuario").focus(); }
      return;
    }
    if (s.autenticado && s.debe_cambiar) { pedirCambio(""); return; }
    if (s.autenticado) { location.href = "/"; return; }
    if (s.configurado) { soloMostrar("fIngreso"); $("iUsuario").focus(); }
    else if (s.local) { soloMostrar("fPrimera"); $("pNombre").focus(); }
    else { soloMostrar("aRemoto"); }
  }).catch(function () { soloMostrar("fIngreso"); });

  $("fIngreso").addEventListener("submit", async function (e) {
    e.preventDefault();
    var b = $("bIngresar"); b.disabled = true; error($("eIngreso"), "");
    try {
      claveRecienUsada = $("iClave").value.trim(); // pegada del correo/WhatsApp puede traer espacios
      var j = await enviar("/api/login", { usuario: $("iUsuario").value, clave: claveRecienUsada });
      if (j.debe_cambiar) pedirCambio(claveRecienUsada); else location.href = "/";
    } catch (err) { error($("eIngreso"), err.message); $("iClave").select(); }
    b.disabled = false;
  });

  $("fCambiar").addEventListener("submit", async function (e) {
    e.preventDefault();
    error($("eCambiar"), "");
    if ($("kNueva").value !== $("kNueva2").value) { error($("eCambiar"), "Las dos claves nuevas no coinciden."); return; }
    try {
      await enviar("/api/mi-clave", { actual: $("kActual").value, nueva: $("kNueva").value });
      location.href = "/";
    } catch (err) {
      error($("eCambiar"), err.message);
      if (/actual/i.test(err.message)) { $("lActual").hidden = false; $("kActual").value = ""; $("kActual").focus(); }
    }
  });

  $("fPrimera").addEventListener("submit", async function (e) {
    e.preventDefault();
    error($("ePrimera"), "");
    if ($("pClave").value !== $("pClave2").value) { error($("ePrimera"), "Las dos claves no coinciden."); return; }
    try {
      await enviar("/api/primer-admin", { nombre: $("pNombre").value, usuario: $("pUsuario").value, clave: $("pClave").value,
                                          correo: $("pCorreo").value, celular: $("pCelular").value });
      await enviar("/api/login", { usuario: $("pUsuario").value, clave: $("pClave").value });
      location.href = "/";
    } catch (err) { error($("ePrimera"), err.message); }
  });
})();
