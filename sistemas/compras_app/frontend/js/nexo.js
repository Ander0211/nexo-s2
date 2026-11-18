/* Nexo S²: botón «Volver a Nexo S²».
   El portal llega con ?nexo=<puerto>; se recuerda en este navegador para que el botón siempre sepa a dónde volver.
   Sin ese dato usa el puerto 7000 (el de Nexo S² por defecto). Cualquier enlace con data-nexo-volver toma la dirección. */
(function () {
  var CLAVE = "nexo_portal_puerto";
  var puerto = "7000";
  try {
    var params = new URLSearchParams(location.search);
    var pedido = params.get("nexo");
    if (pedido && /^\d{2,5}$/.test(pedido)) {
      localStorage.setItem(CLAVE, pedido);
      params.delete("nexo");
      var resto = params.toString();
      history.replaceState(null, "", location.pathname + (resto ? "?" + resto : "") + location.hash);
    }
    puerto = localStorage.getItem(CLAVE) || puerto;
  } catch (e) {}
  var url = location.protocol + "//" + location.hostname + ":" + puerto + "/";
  function aplicar() {
    var enlaces = document.querySelectorAll("[data-nexo-volver]");
    for (var i = 0; i < enlaces.length; i++) enlaces[i].href = url;
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", aplicar);
  else aplicar();
})();
