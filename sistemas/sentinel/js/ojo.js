/* SENTINEL PABON: botón del ojo para ver u ocultar la clave en todos los campos de clave de la página. */
(function () {
  var ABIERTO = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>';
  var CERRADO = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4 20 20 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  function poner(input) {
    if (input.dataset.ojo) return;
    input.dataset.ojo = "1";
    var caja = document.createElement("span");
    caja.className = "clave-caja";
    input.parentNode.insertBefore(caja, input);
    caja.appendChild(input);
    var b = document.createElement("button");
    b.type = "button";
    b.className = "ojo";
    b.title = "Mostrar la clave";
    b.setAttribute("aria-label", "Mostrar la clave");
    b.setAttribute("aria-pressed", "false");
    b.innerHTML = ABIERTO;
    b.addEventListener("click", function () {
      var ver = input.type === "password";
      input.type = ver ? "text" : "password";
      b.innerHTML = ver ? CERRADO : ABIERTO;
      b.title = ver ? "Ocultar la clave" : "Mostrar la clave";
      b.setAttribute("aria-label", b.title);
      b.setAttribute("aria-pressed", ver ? "true" : "false");
      input.focus();
    });
    // Al enviar el formulario la clave vuelve a ocultarse
    if (input.form) input.form.addEventListener("submit", function () {
      input.type = "password"; b.innerHTML = ABIERTO; b.setAttribute("aria-pressed", "false");
    });
    caja.appendChild(b);
  }
  function todos() { document.querySelectorAll('input[type="password"]').forEach(poner); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", todos); else todos();
})();
