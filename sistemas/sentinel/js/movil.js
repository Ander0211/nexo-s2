/* SENTINEL PABON en el celular (y tabletas):
   - el menú lateral se abre con ☰ y se cierra al elegir una opción, al tocar fuera o con «Atrás»/Esc;
   - «⋮» abre buscar, usuario, Usuarios/Mi clave, Salir, Ayuda, Imprimir y Tema;
   - toda tabla ancha se desplaza dentro de su propio recuadro (la página nunca se corre de lado). */
(function () {
  var html = document.documentElement;
  var side = document.getElementById("side");
  var menuBtn = document.getElementById("menuBtn");
  var masBtn = document.getElementById("masBtn");
  var velo = document.getElementById("velo");
  var acciones = document.getElementById("topActions");
  var esMovil = window.matchMedia("(max-width: 980px)");

  function abrirMenu(si) {
    html.classList.toggle("menu-abierto", si);
    if (si) html.classList.remove("mas-abierto");
    menuBtn.setAttribute("aria-expanded", si ? "true" : "false");
    masBtn.setAttribute("aria-expanded", "false");
    if (si) { var activo = side.querySelector(".nav .active"); if (activo) activo.scrollIntoView({ block: "center" }); }
  }
  function abrirMas(si) {
    html.classList.toggle("mas-abierto", si);
    if (si) html.classList.remove("menu-abierto");
    masBtn.setAttribute("aria-expanded", si ? "true" : "false");
    menuBtn.setAttribute("aria-expanded", "false");
  }
  function cerrarTodo() { html.classList.remove("menu-abierto", "mas-abierto"); menuBtn.setAttribute("aria-expanded", "false"); masBtn.setAttribute("aria-expanded", "false"); }

  menuBtn.addEventListener("click", function () { abrirMenu(!html.classList.contains("menu-abierto")); });
  masBtn.addEventListener("click", function () { abrirMas(!html.classList.contains("mas-abierto")); });
  velo.addEventListener("click", cerrarTodo);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") cerrarTodo(); });
  esMovil.addEventListener("change", function (e) { if (!e.matches) cerrarTodo(); });

  // Elegir una opción del menú o de «⋮» lo cierra y lleva arriba de la página nueva
  document.addEventListener("click", function (e) {
    if (!esMovil.matches) return;
    if (e.target.closest("#side [data-nav], #side [data-go], #side [data-nav-year]")) { cerrarTodo(); window.scrollTo(0, 0); }
    else if (e.target.closest("#topActions button, #topActions a")) { cerrarTodo(); }
  });
  // Al buscar desde «⋮»: Enter cierra el panel para ver los resultados
  var q = document.getElementById("qglob");
  if (q && esMovil.matches) q.placeholder = "Buscar sistema, archivo o fecha";
  if (q) q.addEventListener("keydown", function (e) { if (e.key === "Enter" && esMovil.matches) { cerrarTodo(); q.blur(); } });

  // Tablas anchas: cada una dentro de un recuadro que se desplaza de lado
  function envolverTablas(raiz) {
    (raiz || document).querySelectorAll("#view table, #modal table").forEach(function (t) {
      if (t.parentElement && t.parentElement.classList.contains("tabla-desliza")) return;
      var caja = document.createElement("div");
      caja.className = "tabla-desliza";
      t.parentNode.insertBefore(caja, t);
      caja.appendChild(t);
    });
  }
  var pendiente = false;
  var obs = new MutationObserver(function () {
    if (pendiente) return;
    pendiente = true;
    requestAnimationFrame(function () { pendiente = false; envolverTablas(); });
  });
  ["view", "modal"].forEach(function (id) { var el = document.getElementById(id); if (el) obs.observe(el, { childList: true, subtree: true }); });
  envolverTablas();
})();
