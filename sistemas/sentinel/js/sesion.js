/* SENTINEL PABON: quién está conectado, su rol, el botón Salir y qué pasa si la sesión vence. */
(function () {
  var S = window.SENTINEL_SESION || { rol: "revisor", nombre: "" };
  var admin = S.rol === "administrador";
  document.documentElement.classList.add(admin ? "rol-admin" : "rol-revisor");

  // Si el servidor responde 401 (sesión vencida o cerrada), se vuelve a la pantalla de ingreso.
  var fetchOriginal = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    return fetchOriginal(url, opts).then(function (r) {
      if (r.status === 401 && String(url).indexOf("/api/") !== -1) location.href = "/login.html";
      return r;
    });
  };

  function llenar() {
    var n = document.getElementById("quienNombre"), r = document.getElementById("quienRol");
    if (n) n.textContent = S.nombre || S.usuario || "";
    if (r) r.textContent = S.superusuario ? "Superusuario" : admin ? "Administrador" : "Revisor";
    var c = document.getElementById("btnCuentas");
    if (c) { c.textContent = admin ? "Usuarios" : "Mi clave"; c.title = admin ? "Crear y gestionar usuarios" : "Cambiar mi clave"; }
    var s = document.getElementById("btnSalir");
    if (s) s.onclick = function () {
      fetchOriginal("/api/logout", { method: "POST" }).finally(function () { location.href = "/login.html"; });
    };
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", llenar); else llenar();
})();
