/* SENTINEL PABON — interfaz.
 * Datos: window.BACKUP_DATA / BACKUP_ANALYTICS (generados por ingest.py).
 * Reglas y arquitectura: DOCUMENTACION.md
 * No explicar el sistema en pantalla; títulos sí, párrafos de ayuda no.
 */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));

const D = window.BACKUP_DATA || { records: [], sistemas: [], anios: [], total: 0, pesoTotalGB: 0, desde: "", hasta: "", hoja: "", ubicacion: "", fuente: "", destacados: {} };
const A = window.BACKUP_ANALYTICS || {};
const KEY = "sentinel-osi-real-v1";
function isoHoyLocal() {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}
function isoAyerLocal() {
  const n = new Date();
  n.setDate(n.getDate() - 1);
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}
(function recortarHastaAyer() {
  const ayer = isoAyerLocal();
  D.records = (D.records || []).filter((r) => r.f && r.f <= ayer);
  if (D.records.length) {
    D.desde = D.records[0].f;
    D.hasta = D.records[D.records.length - 1].f;
    D.total = D.records.length;
    const gb = D.records.reduce((a, r) => a + (Number(r.p) || 0), 0);
    D.pesoTotalGB = Math.round(gb * 100) / 100;
  } else if (!D.hasta || D.hasta > ayer) {
    D.hasta = ayer;
  }
  if (Array.isArray(D.anios)) {
    D.anios = D.anios.map((a) => {
      const rows = D.records.filter((r) => Number(r.f.slice(0, 4)) === Number(a.anio));
      if (!rows.length) return { ...a, reg: 0, dias: 0, hasta: a.hasta };
      const dias = [...new Set(rows.map((r) => r.f))].sort();
      return { ...a, reg: rows.length, dias: dias.length, desde: dias[0], hasta: dias[dias.length - 1] };
    }).filter((a) => a.reg > 0);
  }
})();
const HOY_FORM = D.hasta || isoAyerLocal();
const _lastF = {};
D.records.forEach((r) => { _lastF[r.s] = r.f; });
const ACTIVE = D.sistemas.filter((s) => _lastF[s] === D.hasta);
const STOPPED = D.sistemas.filter((s) => _lastF[s] !== D.hasta);
const RESULTADOS = ["Exitoso", "Parcial", "Exitoso con observaciones", "Fallido", "No ejecutado"];

const ICONS = {
  mando: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 13h4v7H4zM10 4h4v16h-4zM16 9h4v11h-4z"/></svg>',
  verificar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
  verificadas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l8 4v5c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V7z"/></svg>',
  bitacora: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>',
  inventario: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="6" rx="1"/><rect x="3" y="14" width="18" height="6" rx="1"/></svg>',
  comportamiento: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V5M4 19h16"/><path d="M8 15l3-4 3 2 5-7"/></svg>',
  cadencia: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 11h18"/></svg>',
  gemelas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="8" cy="12" r="5"/><circle cx="16" cy="12" r="5"/></svg>',
  deriva: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 18l5-6 4 3 7-9"/><path d="M4 20h16"/></svg>',
  interrogantes: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.8.4-1 1.2-1 1.7V14"/><circle cx="12" cy="17" r=".6" fill="currentColor"/></svg>',
  huecos: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 8h16M4 12h10M4 16h7"/></svg>',
  rips: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>',
  sla: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V5M4 19h16"/><path d="M7 15l3-4 3 2 4-6"/></svg>',
  compare: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 7h12M8 12h8M8 17h10"/><path d="M4 7h.01M4 12h.01M4 17h.01"/></svg>',
  informe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/></svg>',
  mejoras: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l2 4 5 .5-3.5 3.2L16.5 16 12 14l-4.5 2 1-5.3L5 7.5 10 7z"/></svg>',
  alertas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9L2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
  lote: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 11l3 3L22 4"/><rect x="3" y="5" width="14" height="14" rx="2"/></svg>',
  disco: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>',
  ficha: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
  host: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="8" rx="1"/><path d="M7 16h10M9 20h6M12 12v4"/></svg>',
  reloj: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  corridas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 6h16M4 12h10M4 18h7"/></svg>',
  tableros: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="5" rx="1"/><rect x="13" y="10" width="8" height="11" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/></svg>',
  excelup: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 16V4M8 8l4-4 4 4"/><path d="M4 20h16"/></svg>'
};

/* Usuarios: el servidor entrega la sesión en window.SENTINEL_SESION.
   Administrador: todo. Revisor: solo consulta (sin cargar inventario ni verificar/ENVIAR).
   El servidor también lo exige: aunque se fuerce la pantalla, un revisor no puede escribir. */
const SESION = window.SENTINEL_SESION || { rol: "revisor", nombre: "" };
const ES_ADMIN = SESION.rol === "administrador";
const SOLO_ADMIN = new Set(["verificar", "lote", "excelup"]);
function puedeVer(id) { return ES_ADMIN || !SOLO_ADMIN.has(id); }

const VIEWS = [
  { id: "mando", label: "Resumen ejecutivo", sec: "Hoy" },
  { id: "tableros", label: "Tableros de control", sec: "Hoy" },
  { id: "verificar", label: "Formato de verificación", sec: "Formulario" },
  { id: "verificadas", label: "Registro de verificaciones", sec: "Formulario" },
  { id: "lote", label: "Verificación del día", sec: "Formulario" },
  { id: "bitacora", label: "Inventario de copias", sec: "Excel" },
  { id: "excelup", label: "Cargar inventario", sec: "Excel" },
  { id: "inventario", label: "Catálogo de sistemas", sec: "Excel" },
  { id: "comportamiento", label: "Comportamiento histórico", sec: "Análisis" },
  { id: "cadencia", label: "Cadencia por año", sec: "Análisis" },
  { id: "gemelas", label: "Corridas 01:00 y 13:00", sec: "Análisis" },
  { id: "deriva", label: "Deriva de tamaño", sec: "Análisis" },
  { id: "alertas", label: "Alertas del inventario", sec: "Análisis" },
  { id: "corridas", label: "Corridas incompletas", sec: "Análisis" },
  { id: "reloj", label: "Consistencia de fecha", sec: "Análisis" },
  { id: "disco", label: "Capacidad y retención", sec: "Análisis" },
  { id: "ficha", label: "Ficha de sistema", sec: "Análisis" },
  { id: "host", label: "Continuidad operativa", sec: "Análisis" },
  { id: "sla", label: "Cumplimiento mensual", sec: "Análisis" },
  { id: "compare", label: "Comparativo anual", sec: "Análisis" },
  { id: "informe", label: "Informe de turno", sec: "Análisis" },
  { id: "mejoras", label: "Plan de mejora", sec: "Diseño" },
  { id: "interrogantes", label: "Requisitos del registro", sec: "Diseño" },
  { id: "huecos", label: "Meses sin captura", sec: "Diseño" },
  { id: "rips", label: "Trazabilidad RIPS", sec: "Diseño" }
];

function fmtDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}
function fmtGB(n) {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1024) return (n / 1024).toFixed(2) + " TB";
  if (n >= 1) return n.toFixed(2) + " GB";
  return (n * 1024).toFixed(2) + " MB";
}
function arr(x) { return Array.isArray(x) ? x : []; }
function pesoAnio(y) {
  const v = (A.ultimoFact || {})[y];
  if (v == null) return 0;
  return typeof v === "number" ? v : Number(v.p) || 0;
}
function uid() { return "v" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }

let state = { theme: "light", view: "mando", extra: [], checks: {}, simple: true, guia: false, easy: true, anio: null };
const SIMPLE_IDS = new Set([
  "mando", "tableros", "verificar", "verificadas", "lote",
  "bitacora", "inventario", "informe", "excelup", "ficha", "alertas",
  "cadencia", "compare", "sla", "comportamiento"
]);
function load() {
  try {
    const p = JSON.parse(localStorage.getItem(KEY) || "{}");
    state.theme = p.theme || "light";
    state.extra = Array.isArray(p.extra) ? p.extra : [];
    state.checks = p.checks && typeof p.checks === "object" ? p.checks : {};
    if (typeof p.simple === "boolean") state.simple = p.simple;
    if (typeof p.guia === "boolean") state.guia = p.guia;
    if (typeof p.easy === "boolean") state.easy = p.easy;
    if (p.anio != null && p.anio !== "") state.anio = Number(p.anio);
  } catch { /* localStorage bloqueado: se trabaja en memoria */ }
}
function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      theme: state.theme, extra: state.extra, checks: state.checks,
      simple: state.simple, guia: state.guia, easy: state.easy, anio: state.anio
    }));
  } catch { /* sigue en memoria */ }
}

function registrarVerificacion(row) {
  const rec = {
    id: uid(),
    fecha: row.fecha,
    sistema: row.sistema,
    ubicacion: row.ubicacion,
    tipo: row.tipo,
    resultado: row.resultado,
    observaciones: row.observaciones || ""
  };
  state.extra.unshift(rec);
  save();
  return rec;
}

async function pullExcel() {
  try {
    const j = await fetch("/api/verificaciones").then((r) => r.json());
    if (j && j.ok && Array.isArray(j.verificaciones)) {
      state.extra = j.verificaciones;
      save();
    }
  } catch { /* sin API: queda localStorage */ }
}

async function pushExcel(payload) {
  const res = await fetch("/api/verificar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const txt = await res.text();
  let j;
  try {
    j = JSON.parse(txt);
  } catch {
    throw new Error(
      res.status === 405 || /method not allowed/i.test(txt)
        ? "Abra SENTINEL con iniciar-SENTINEL.bat (http://localhost:8080). Este servidor no acepta ENVIAR."
        : "El servidor no respondió JSON (" + res.status + ")"
    );
  }
  if (!j.ok) throw new Error(j.error || "No se pudo guardar el Excel");
  if (Array.isArray(j.verificaciones)) state.extra = j.verificaciones;
  save();
  return j;
}

function cruzarSistema(sistema, fecha) {
  const s = bySystem().find((x) => x.s === sistema);
  const day = recsOn(fecha).filter((r) => r.s === sistema);
  return {
    coincide: day.length ? `Sí · ${day.length} .bak el ${fecha}` : (s && s.last ? `No hay .bak el ${fecha}. Último inventario: ${s.last}` : "Sin cruce"),
    ultimoBak: s ? s.lastA : "",
    fechaBak: s ? s.last : "",
    horaBak: s ? s.lastH : "",
    pesoBak: s ? s.lastP : ""
  };
}

async function enviarFormulario() {
  const form = $("#fver");
  if (!form) return false;
  const fecha = (form.fecha.value || "").trim();
  const sistema = (form.sistema.value || "").trim();
  const ubicacion = (form.ubicacion.value || "").trim();
  const tipo = (form.tipo.value || "").trim();
  const resultado = (form.resultado.value || "").trim();
  const observaciones = (form.observaciones.value || "").trim();
  const miss = [];
  if (!fecha) miss.push("Fecha de verificación");
  if (!sistema) miss.push("Sistema / Carpeta");
  if (!ubicacion) miss.push("Ubicación");
  if (!tipo) miss.push("Tipo de Backup");
  if (!resultado) miss.push("Resultado");
  const box = $("#formErr");
  if (miss.length) {
    if (box) box.innerHTML = `<div class="q-card gap"><h4>Faltan campos obligatorios</h4><p>${miss.map(esc).join(" · ")}</p></div>`;
    toast("Completa los campos con * para enviar.");
    form.reportValidity?.();
    return false;
  }
  if (box) box.innerHTML = "";
  const x = cruzarSistema(sistema, fecha);
  const rec = {
    fecha, sistema, ubicacion, tipo, resultado, observaciones,
    operador: (form.operador?.value || "").trim(),
    tamano: (form.tamano?.value || "").trim(),
    duracion: (form.duracion?.value || "").trim(),
    hash: (form.hash?.value || "").trim(),
    segunda: (form.segunda?.value || "").trim(),
    restore: (form.restore?.value || "").trim(),
    ...x
  };
  const btn = $("#btnSend");
  if (btn) { btn.disabled = true; btn.textContent = "GUARDANDO…"; }
  try {
    await pushExcel(rec);
    toast("Guardado en Excel · hoja Verificaciones · " + rec.sistema);
    showEnviado(rec);
  } catch (err) {
    registrarVerificacion(rec);
    if (box) box.innerHTML = `<div class="q-card warn"><h4>No se alcanzó el archivo .xlsx</h4><p>${esc(err.message)}. Quedó en este navegador. Revisá que el servidor de SENTINEL PABON esté arriba.</p></div>`;
    toast("No se pudo escribir el Excel: " + err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "ENVIAR"; }
  }
  return true;
}

function showEnviado(rec) {
  $("#modalBg").classList.add("show");
  $("#modal").innerHTML = `
    <h3 style="font-family:var(--display);margin:0 0 8px">Verificación enviada</h3>
    <p class="tiny muted">El botón ENVIAR registró esta fila. Queda en Verificaciones enviadas.</p>
    <div class="kv" style="margin-top:12px">
      <b>Fecha</b><span>${fmtDate(rec.fecha)}</span>
      <b>Sistema / Carpeta</b><span>${esc(rec.sistema)}</span>
      <b>Ubicación</b><span class="mono">${esc(rec.ubicacion)}</span>
      <b>Tipo</b><span>${esc(rec.tipo)}</span>
      <b>Resultado</b><span>${badgeRes(rec.resultado)}</span>
      <b>Observaciones</b><span>${esc(rec.observaciones || "—")}</span>
      <b>Operador</b><span>${esc(rec.operador || "—")}</span>
      <b>Tamaño</b><span>${esc(rec.tamano || "—")}</span>
      <b>Cruce inventario</b><span>${esc(rec.coincide || "—")}</span>
    </div>
    <p class="tiny muted" style="margin:12px 0 0">Fila escrita en <span class="mono">inventario-backups.xlsx</span> · hoja Verificaciones.</p>
    <div style="margin-top:16px;display:flex;gap:8px;justify-content:flex-end">
      <button class="btn" type="button" id="otraV">Otra verificación</button>
      <button class="btn primary" type="button" id="verEnv">Ver enviadas</button>
    </div>`;
  $("#otraV").onclick = () => { $("#modalBg").classList.remove("show"); go("verificar"); };
  $("#verEnv").onclick = () => { $("#modalBg").classList.remove("show"); go("verificadas"); };
}

let _bySysAll = null;
function bySystem(year) {
  if (!year && _bySysAll) return _bySysAll;
  const map = {};
  D.sistemas.forEach((s) => { map[s] = { s, n: 0, gb: 0, first: null, last: null, lastP: null, lastH: null, lastA: null }; });
  const y = year ? String(year) : null;
  D.records.forEach((r) => {
    if (y && r.f.slice(0, 4) !== y) return;
    const o = map[r.s];
    if (!o) return;
    o.n++; o.gb += r.p;
    if (!o.first) o.first = r.f;
    o.last = r.f; o.lastP = r.pr; o.lastH = r.h; o.lastA = r.a;
  });
  const out = D.sistemas.map((s) => map[s]);
  if (!year) _bySysAll = out;
  return out;
}
function yearMatrix() {
  const years = D.anios.map((a) => String(a.anio));
  const m = {};
  D.sistemas.forEach((s) => {
    m[s] = {};
    years.forEach((y) => { m[s][y] = { n: 0, last: null, lastP: null, lastH: null }; });
  });
  D.records.forEach((r) => {
    const y = r.f.slice(0, 4);
    if (!m[r.s] || !m[r.s][y]) return;
    const o = m[r.s][y];
    o.n++; o.last = r.f; o.lastP = r.pr; o.lastH = r.h;
  });
  return { years, m };
}
function htmlSysList(stats, year) {
  return stats.map((s) => {
    const viva = year
      ? s.n > 0
      : ACTIVE.includes(s.s);
    if (year && !s.n) {
      return `<div class="insight go" data-ficha="${esc(s.s)}" title="Abrir ficha de ${esc(s.s)}">
        <div class="mark" style="background:var(--line)"></div>
        <div>
          <h4>${esc(s.s)}</h4>
          <p>Sin copia en ${year}. Abrir ficha del sistema →</p>
        </div>
      </div>`;
    }
    return `<div class="insight go" data-ficha="${esc(s.s)}" title="Abrir ficha de ${esc(s.s)}">
      <div class="mark" style="background:${viva ? "var(--ok)" : "var(--bad)"}"></div>
      <div>
        <h4>${esc(s.s)}</h4>
        <p>${fmtDate(s.first)} → ${fmtDate(s.last)} ${esc(s.lastH || "")} · ${s.n} archivo${s.n === 1 ? "" : "s"} · último ${esc(s.lastP)}</p>

      </div>
    </div>`;
  }).join("");
}
function htmlYearMatrix() {
  const { years, m } = yearMatrix();
  const head = `<tr><th class="sys">Sistema</th>${years.map((y) => `<th>${y}</th>`).join("")}<th>Todos</th></tr>`;
  const body = D.sistemas.map((s) => {
    const tot = years.reduce((a, y) => a + m[s][y].n, 0);
    const cells = years.map((y) => {
      const o = m[s][y];
      if (!o.n) return `<td class="noc">—</td>`;
      return `<td class="okc" title="${o.n} archivos · último ${fmtDate(o.last)} ${o.lastH || ""} · ${o.lastP}">${o.n}<div class="tiny muted">${esc(o.lastP)}</div></td>`;
    }).join("");
    return `<tr><td class="sys go" data-ficha="${esc(s)}" title="Abrir ficha">${esc(s)}</td>${cells}<td><b>${tot}</b></td></tr>`;
  }).join("");
  const foot = `<tr><td class="sys"><b>Total año</b></td>${years.map((y) => {
    const n = D.sistemas.reduce((a, s) => a + m[s][y].n, 0);
    return `<td><b>${n.toLocaleString("es-CO")}</b></td>`;
  }).join("")}<td><b>${D.total.toLocaleString("es-CO")}</b></td></tr>`;
  return `<div class="table-wrap"><table class="mtx"><thead>${head}</thead><tbody>${body}${foot}</tbody></table></div>
`;
}
function recsOn(iso) { return D.records.filter((r) => r.f === iso); }
function ultimoAnio() {
  const ys = arr(D.anios);
  return ys.length ? Number(ys[ys.length - 1].anio) : Number(String(D.hasta || "").slice(0, 4)) || null;
}
function rangoAniosTxt() {
  const ys = arr(D.anios).map((a) => a.anio);
  if (!ys.length) return "";
  return ys[0] === ys[ys.length - 1] ? String(ys[0]) : `${ys[0]} – ${ys[ys.length - 1]}`;
}
function presentSet(year) {
  const y = String(year || ultimoAnio() || "");
  return new Set(D.records.filter((r) => r.f.slice(0, 4) === y).map((r) => r.f));
}

let cadAnio = null;
function anioCadencia() {
  const ys = arr(D.anios).map((a) => Number(a.anio));
  if (!ys.length) return ultimoAnio();
  if (state.anio && ys.includes(Number(state.anio))) return Number(state.anio);
  if (cadAnio && ys.includes(Number(cadAnio))) return Number(cadAnio);
  return ys[ys.length - 1];
}
const YEAR_VIEWS = new Set([
  "mando", "tableros", "bitacora", "inventario", "cadencia", "compare", "sla",
  "comportamiento", "gemelas", "corridas", "deriva", "huecos", "alertas", "ficha",
  "reloj", "disco", "host", "informe", "verificadas"
]);
function elegirAnio(y) {
  const ys = arr(D.anios).map((a) => Number(a.anio));
  const n = Number(y);
  state.anio = ys.includes(n) ? n : ultimoAnio();
  cadAnio = state.anio;
  if (!YEAR_VIEWS.has(state.view)) state.view = "cadencia";
  save();
  render();
}

function htmlAniosBar() {
  const y = anioCadencia();
  const meta = arr(D.anios).find((a) => Number(a.anio) === y);
  return `<div class="year-tabs view-years">
    ${arr(D.anios).map((a) => `<button type="button" data-nav-year="${a.anio}" class="${Number(a.anio) === y ? "on" : ""}">${a.anio}</button>`).join("")}
  </div>
  <p class="tiny muted" style="margin:-4px 0 12px">${y}${meta ? " · " + Number(meta.reg).toLocaleString("es-CO") + " archivos · " + fmtDate(meta.desde) + " → " + fmtDate(meta.hasta) : ""}</p>`;
}
function weekdayDe(year) {
  const c = [0, 0, 0, 0, 0, 0, 0];
  const y = String(year);
  D.records.forEach((r) => {
    if (r.f.slice(0, 4) !== y) return;
    const [Y, M, d] = r.f.split("-").map(Number);
    c[(new Date(Y, M - 1, d).getDay() + 6) % 7]++;
  });
  return c;
}
function gemelasDe(year) {
  const y = String(year);
  const ampm = {};
  D.records.forEach((r) => {
    if (r.s !== "SIFacturacion" || r.f.slice(0, 4) !== y) return;
    if (!ampm[r.f]) ampm[r.f] = { AM: null, PM: null };
    if (String(r.h) < "12:00") ampm[r.f].AM = r;
    else ampm[r.f].PM = r;
  });
  let ambos = 0;
  const una = [], muestra = [], deltas = [];
  Object.keys(ampm).sort().forEach((f) => {
    const v = ampm[f];
    if (v.AM && v.PM) {
      ambos++;
      const dlt = v.PM.p - v.AM.p;
      deltas.push(dlt);
      if (muestra.length < 8) muestra.push({ f, am: v.AM.pr, pm: v.PM.pr, d: Math.round(dlt * 10000) / 10000 });
    } else {
      const rec = v.AM || v.PM;
      una.push({ f, h: rec.h, pr: rec.pr });
    }
  });
  return {
    ambos, una: una.slice(0, 20), muestra,
    deltaMedio: deltas.length ? Math.round((deltas.reduce((a, b) => a + b, 0) / deltas.length) * 10000) / 10000 : 0
  };
}
function corridasDe(year) {
  const y = String(year);
  const activos = ACTIVE.length ? ACTIVE : D.sistemas.slice(0, 5);
  const map = {};
  D.records.forEach((r) => {
    if (r.f.slice(0, 4) !== y || !activos.includes(r.s)) return;
    const b = String(r.h) < "12:00" ? "AM" : "PM";
    const k = r.f + "|" + b;
    if (!map[k]) map[k] = { f: r.f, b, sistemas: [] };
    if (!map[k].sistemas.includes(r.s)) map[k].sistemas.push(r.s);
  });
  return Object.values(map)
    .filter((o) => o.sistemas.length && o.sistemas.length < activos.length)
    .sort((a, b) => a.f.localeCompare(b.f) || a.b.localeCompare(b.b))
    .map((o) => ({ f: o.f, b: o.b, n: o.sistemas.length, sistemas: o.sistemas, falta: activos.filter((s) => !o.sistemas.includes(s)) }));
}
function isoYmd(y, m, d) {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
function diasEntreIso(a, b) {
  const [y1, m1, d1] = String(a).split("-").map(Number);
  const [y2, m2, d2] = String(b).split("-").map(Number);
  return Math.round((new Date(y2, m2 - 1, d2) - new Date(y1, m1 - 1, d1)) / 864e5);
}
function cadenciaAnio(year) {
  const y = Number(year);
  const recs = D.records.filter((r) => Number(r.f.slice(0, 4)) === y);
  const byDay = {};
  recs.forEach((r) => { byDay[r.f] = (byDay[r.f] || 0) + 1; });
  const dias = Object.keys(byDay).sort();
  const present = new Set(dias);
  const meta = arr(D.anios).find((a) => Number(a.anio) === y);
  const ayer = isoAyerLocal();
  const esUltimo = y === ultimoAnio();
  let first = (meta && meta.desde) || dias[0] || "";
  let last = (meta && meta.hasta) || dias[dias.length - 1] || first;
  if (esUltimo) first = `${y}-01-01`;
  if (last && last > ayer) last = ayer;
  if (D.hasta && esUltimo && D.hasta < last) last = D.hasta;
  const firstM = esUltimo ? 1 : (first ? Number(first.slice(5, 7)) : 1);
  const lastM = last ? Number(last.slice(5, 7)) : firstM;
  const firstD = esUltimo ? 1 : (first ? Number(first.slice(8, 10)) : 1);
  const lastD = last ? Number(last.slice(8, 10)) : 1;
  let diario = esUltimo;
  if (!diario && dias.length >= 30) {
    const gaps = [];
    for (let i = 1; i < dias.length; i++) gaps.push(diasEntreIso(dias[i - 1], dias[i]));
    gaps.sort((a, b) => a - b);
    diario = gaps[Math.floor(gaps.length / 2)] <= 1;
  }
  const missing = [];
  let cal = 0;
  if (first && last) {
    for (let mo = firstM; mo <= lastM; mo++) {
      const dim = new Date(y, mo, 0).getDate();
      const from = mo === firstM ? firstD : 1;
      const to = mo === lastM ? lastD : dim;
      for (let day = from; day <= to; day++) {
        cal++;
        const iso = isoYmd(y, mo, day);
        if (!present.has(iso)) missing.push(iso);
      }
    }
  } else {
    cal = present.size;
  }
  const huecos = [];
  if (diario) {
    let run = [];
    missing.forEach((iso) => {
      if (!run.length) { run = [iso]; return; }
      const prev = run[run.length - 1];
      const [py, pm, pd] = prev.split("-").map(Number);
      const nxt = new Date(py, pm - 1, pd + 1);
      const niso = isoYmd(nxt.getFullYear(), nxt.getMonth() + 1, nxt.getDate());
      if (iso === niso) run.push(iso);
      else {
        huecos.push({ desde: run[0], hasta: run[run.length - 1], dias: run.length });
        run = [iso];
      }
    });
    if (run.length) huecos.push({ desde: run[0], hasta: run[run.length - 1], dias: run.length });
    huecos.sort((a, b) => b.dias - a.dias);
  }
  const esperados = diario ? 10 : null;
  const raros = esperados
    ? Object.keys(byDay).sort().filter((f) => byDay[f] !== esperados).map((f) => ({ f, n: byDay[f] }))
    : [];
  return {
    y, first, last, firstM, lastM, firstD, lastD, cal, present, byDay, recs,
    con: present.size, sin: missing.length, huecos, raros, diario, esperados
  };
}

function sparkline(values, w = 120, h = 36, color = "#6ACEF5") {
  if (!values.length) return "";
  const min = Math.min(...values), max = Math.max(...values);
  const n = values.length;
  const pts = values.map((v, i) => {
    const x = n === 1 ? w / 2 : (i / (n - 1)) * w;
    const y = h - 4 - ((v - min) / (max - min || 1)) * (h - 8);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="${color}" stroke-width="2" points="${pts.join(" ")}"/></svg>`;
}
function bars(items, w = 640, h = 180) {
  if (!items || !items.length) return "";
  const max = Math.max(1, ...items.map((i) => i.v));
  const bw = w / items.length;
  return `<svg width="100%" viewBox="0 0 ${w} ${h}">${items.map((it, i) => {
    const bh = (it.v / max) * (h - 28);
    const x = i * bw + 4;
    return `<rect x="${x}" y="${h - 18 - bh}" width="${Math.max(8, bw - 10)}" height="${bh}" rx="3" fill="${it.color || "#015AAA"}"/>
      <text x="${x + (bw - 10) / 2}" y="${h - 4}" text-anchor="middle" font-size="10" fill="currentColor">${esc(it.l)}</text>`;
  }).join("")}</svg>`;
}
function donut(pct, color) {
  const r = 28, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct)), off = c * (1 - p / 100);
  return `<svg class="score-ring" viewBox="0 0 72 72">
    <circle cx="36" cy="36" r="${r}" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="7"/>
    <circle cx="36" cy="36" r="${r}" fill="none" stroke="${color}" stroke-width="7"
      stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"
      stroke-linecap="round" transform="rotate(-90 36 36)"/>
    <text x="36" y="40" text-anchor="middle" font-size="13" fill="#fff" font-weight="700">${Math.round(p)}</text>
  </svg>`;
}

function go(id) {
  if (state.simple && !SIMPLE_IDS.has(id)) state.simple = false;
  state.view = id;
  render();
}

function listaNav() {
  const list = (state.simple ? VIEWS.filter((v) => SIMPLE_IDS.has(v.id)) : VIEWS).filter((v) => puedeVer(v.id));
  return list.map((v, i) => {
    const prev = list[i - 1];
    const head = !prev || prev.sec !== v.sec ? `<div class="sec">${v.sec}</div>` : "";
    const btn = `<button data-nav="${v.id}" class="${state.view === v.id ? "active" : ""}" title="${esc(v.label)}">${ICONS[v.id] || ""}<span>${v.label}</span></button>`;
    return `${head}${btn}`;
  }).join("");
}

function renderShell() {
  document.documentElement.classList.toggle("easy", state.easy);
  const ySel = anioCadencia();
  const cad = cadenciaAnio(ySel);
  const den = cad.cal || 1;
  const cob = Math.round((cad.con || 0) / den * 100);
  $("#side").innerHTML = `
    <div class="brand" data-go="mando" title="Ir al inicio">
      <img src="assets/logo.png" alt="SENTINEL PABON">
      <div><h1>SENTINEL <em>PABON</em></h1><small>Copias de seguridad</small></div>
    </div>
    <div class="score-pill go" data-go="cadencia" title="Cadencia del año ${ySel}">
      ${donut(cob, cob >= 80 ? "#6ACEF5" : "#EA0B0B")}
      <div><b>${cob}% · ${ySel}</b><span>${cad.con} de ${cad.cal} días con copia</span></div>
    </div>
    <div class="modo">
      <button type="button" class="${state.simple ? "on" : ""}" id="btnSimple">Menú corto</button>
      <button type="button" class="${!state.simple ? "on" : ""}" id="btnFull">Menú completo</button>
    </div>
    <div class="nav">${listaNav()}</div>
    <div class="side-foot">
      <img src="assets/clinica-pabon.png" alt="Clinica Cardioneurovascular PABON" class="foot-marca">
      Clinica Cardioneurovascular PABON<br>
      Oficina de Sistemas de Información<br>
      <button type="button" class="linkish" id="btnEasy">${state.easy ? "Letra normal" : "Letra grande"}</button>
    </div>`;
  const bs = $("#btnSimple"), bf = $("#btnFull"), be = $("#btnEasy");
  if (bs) bs.onclick = (e) => { e.stopPropagation(); state.simple = true; if (!SIMPLE_IDS.has(state.view)) state.view = "mando"; save(); render(); };
  if (bf) bf.onclick = (e) => { e.stopPropagation(); state.simple = false; save(); render(); };
  if (be) be.onclick = (e) => { e.stopPropagation(); state.easy = !state.easy; save(); render(); };
}

function render() {
  document.documentElement.dataset.theme = state.theme;
  renderShell();
  const v = VIEWS.find((x) => x.id === state.view) || VIEWS[0];
  $("#crumb").innerHTML = `<em>${v.sec}</em><strong>${v.label}</strong>`;
  if (!puedeVer(state.view)) { viewSoloLectura(v); return; }
  ({
    mando: viewMando, tableros: viewTableros, verificar: viewForm, verificadas: viewExtra,
    bitacora: viewBitacora, excelup: viewExcelUp, inventario: viewInventario, comportamiento: viewComp,
    cadencia: viewCadencia, gemelas: viewGemelas, deriva: viewDeriva,
    alertas: viewAlertas, corridas: viewCorridas, reloj: viewReloj,
    disco: viewDisco, ficha: viewFicha, host: viewHost, lote: viewLote,
    sla: viewSLA, compare: viewCompare, informe: viewInforme, mejoras: viewMejoras,
    interrogantes: viewQ, huecos: viewHuecos, rips: viewRips
  }[state.view] || viewMando)();
}

function viewSoloLectura(v) {
  $("#view").innerHTML = `
    <div class="card solo-lectura">
      <h2>${esc(v.label)}: solo para administradores</h2>
      <p>Su usuario es <b>Revisor</b>. Puede consultar tableros, inventario, análisis y el registro de verificaciones,
      pero el cargue del inventario y la verificación (ENVIAR) de las copias los hace un administrador.</p>
      <div class="form-actions" style="justify-content:flex-start">
        <button class="btn primary" type="button" id="slReg">Ver registro de verificaciones</button>
        <button class="btn" type="button" id="slIni">Ir al resumen</button>
      </div>
    </div>`;
  $("#slReg").onclick = () => go("verificadas");
  $("#slIni").onclick = () => go("mando");
}

let tableroId = "gerencial";

function semaforo(s) {
  if (ACTIVE.includes(s.s) && s.last === D.hasta) return "g";
  if (ACTIVE.includes(s.s)) return "y";
  return "r";
}
function diasHasta(iso) {
  if (!iso) return "—";
  const a = new Date(iso + "T00:00:00");
  const b = new Date(HOY_FORM + "T00:00:00");
  return Math.round((b - a) / 864e5);
}

function viewTableros() {
  const boards = [
    { id: "gerencial", t: "Gerencial", s: "Pulso 2019–2026" },
    { id: "operacion", t: "Operación", s: "Corrida " + fmtDate(D.hasta) },
    { id: "riesgo", t: "Riesgo y control", s: "Huecos, host único, bajas" },
    { id: "capacidad", t: "Capacidad", s: "Peso y retención" },
    { id: "semaforos", t: "Semáforos", s: "10 sistemas" }
  ];
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="board-tabs">${boards.map((b) => `
      <button type="button" data-board="${b.id}" class="${tableroId === b.id ? "on" : ""}">${esc(b.t)}<small>${esc(b.s)}</small></button>
    `).join("")}</div>
    <div id="board"></div>`;
  const draw = () => {
    $$("[data-board]").forEach((b) => b.classList.toggle("on", b.dataset.board === tableroId));
    const map = { gerencial: boardGerencial, operacion: boardOperacion, riesgo: boardRiesgo, capacidad: boardCapacidad, semaforos: boardSema };
    (map[tableroId] || boardGerencial)();
  };
  $$("[data-board]").forEach((b) => { b.onclick = () => { tableroId = b.dataset.board; draw(); }; });
  draw();
}

function boardGerencial() {
  const y = anioCadencia();
  const stats = bySystem(y);
  const sla = slaMeses();
  const totC = sla.reduce((a, r) => a + r.last, 0);
  const totW = sla.reduce((a, r) => a + r.withD, 0);
  const pct = totC ? (100 * totW / totC) : 0;
  const verdes = stats.filter((s) => semaforo(s) === "g").length;
  const amarillos = stats.filter((s) => semaforo(s) === "y").length;
  const rojos = stats.filter((s) => semaforo(s) === "r").length;
  $("#board").innerHTML = `
    <div class="ctrl-grid" style="margin-bottom:14px">
      <div class="ctrl-tile info go" data-go="bitacora"><div class="k">Inventario</div><div class="n">${D.total.toLocaleString("es-CO")}</div><div class="s">${fmtGB(D.pesoTotalGB)} · ${esc(D.ubicacion)}</div><span class="hint-go">Inventario de copias →</span></div>
      <div class="ctrl-tile go ${pct >= 80 ? "ok" : pct >= 50 ? "warn" : "bad"}" data-go="sla"><div class="k">Cumplimiento ${y}</div><div class="n">${pct.toFixed(0)}%</div><div class="s">${totW}/${totC} días en ${y}</div><span class="hint-go">Informe mensual →</span></div>
      <div class="ctrl-tile go ${verdes === 5 ? "ok" : "warn"}" data-go="tableros" data-board="semaforos"><div class="k">Al día (${fmtDate(D.hasta)})</div><div class="n">${verdes}<span style="font-size:14px;color:var(--muted)"> / 10</span></div><div class="s">${amarillos} con hueco · ${rojos} sin copia desde 2022</div><span class="hint-go">Semáforos →</span></div>
      <div class="ctrl-tile go ${state.extra.length ? "ok" : "warn"}" data-go="verificadas"><div class="k">Verificaciones registradas</div><div class="n">${state.extra.length}</div><div class="s">Hoja Verificaciones del Excel</div><span class="hint-go">Registro →</span></div>
    </div>
    <div class="grid g-2">
      <div class="card">
        <h3>Volumen por año</h3>
        ${bars(D.anios.map((a) => ({ l: String(a.anio).slice(2), v: a.reg, color: Number(a.anio) === y ? "#6ACEF5" : "#015AAA" })))}
      </div>
      <div class="card">
        <h3>SLA mensual ${y}</h3>
        ${sla.map((r) => `
          <div class="sla-row">
            <b>${r.nom}</b>
            <div class="bar"><i style="width:${r.pct.toFixed(0)}%;background:${r.pct >= 90 ? "var(--ok)" : r.pct >= 50 ? "var(--warn)" : "var(--bad)"}"></i></div>
            <span>${r.pct.toFixed(0)}%</span>
            <span class="tiny muted">${r.withD}/${r.last}</span>
          </div>`).join("")}
      </div>
    </div>`;
}

function boardOperacion() {
  const ayer = recsOn(D.hasta);
  const am = ayer.filter((r) => r.h < "12:00");
  const pm = ayer.filter((r) => r.h >= "12:00");
  const esperados = ACTIVE.length * 2;
  const ok = ayer.length === esperados;
  $("#board").innerHTML = `
    <div class="ctrl-grid" style="margin-bottom:14px">
      <div class="ctrl-tile go ${ok ? "ok" : "warn"}" data-go="informe"><div class="k">Archivos ${fmtDate(D.hasta)}</div><div class="n">${ayer.length}<span style="font-size:14px"> / ${esperados}</span></div><div class="s">Cinco bases × dos corridas</div><span class="hint-go">Informe de turno →</span></div>
      <div class="ctrl-tile info go" data-go="gemelas"><div class="k">Madrugada</div><div class="n">${am.length}</div><div class="s">${am.map((r) => r.s).join(" · ") || "—"}</div><span class="hint-go">Corridas 01:00 y 13:00 →</span></div>
      <div class="ctrl-tile info go" data-go="gemelas"><div class="k">Tarde</div><div class="n">${pm.length}</div><div class="s">${pm.map((r) => r.s).join(" · ") || "—"}</div><span class="hint-go">Corridas 01:00 y 13:00 →</span></div>
      <div class="ctrl-tile go ${arr(A.corridasIncompletas).length ? "warn" : "ok"}" data-go="corridas"><div class="k">Corridas incompletas 2026</div><div class="n">${arr(A.corridasIncompletas).length}</div><div class="s">Se esperan cinco bases por bloque</div><span class="hint-go">Detalle →</span></div>
    </div>
    <div class="grid g-13">
      <div class="card">
        <h3>Detalle de la última corrida</h3>
        <table><thead><tr><th>Hora</th><th>Sistema</th><th>Peso</th><th>Archivo</th></tr></thead>
        <tbody>${ayer.map((r) => `<tr><td class="mono">${esc(r.h)}</td><td>${esc(r.s)}</td><td>${esc(r.pr)}</td><td class="mono tiny">${esc(r.a)}</td></tr>`).join("")}</tbody></table>
      </div>
      <div class="card">
        <h3>Control del turno ${fmtDate(HOY_FORM)}</h3>
        <p class="meta">Último día del Excel: ${fmtDate(D.hasta)}.</p>
        <button class="btn primary" data-go="lote" style="margin-top:8px">Verificar el día (10 copias)</button>
        <button class="btn" data-go="corridas" style="margin-top:8px">Ver corridas incompletas</button>
      </div>
    </div>`;
  $$("#board [data-go]").forEach((b) => { b.onclick = () => go(b.dataset.go); });
}

function boardRiesgo() {
  const stats = bySystem();
  const hueco = (A.huecos2026 && A.huecos2026[0]) || { dias: 0, desde: D.hasta, hasta: D.hasta };
  $("#board").innerHTML = `
    <div class="ctrl-grid" style="margin-bottom:14px">
      <div class="ctrl-tile bad go" data-go="host"><div class="k">Host único</div><div class="n" style="font-size:18px">${esc(D.ubicacion)}</div><div class="s">El inventario no lista réplica ni medio externo.</div><span class="hint-go">Continuidad operativa →</span></div>
      <div class="ctrl-tile bad go" data-go="inventario"><div class="k">Bases sin copia desde 2022</div><div class="n">${STOPPED.length}</div><div class="s">${STOPPED.join(" · ")}</div><span class="hint-go">Catálogo de sistemas →</span></div>
      <div class="ctrl-tile warn go" data-go="cadencia"><div class="k">Hueco 2026 más largo</div><div class="n">${hueco.dias}<span style="font-size:14px"> d</span></div><div class="s">${fmtDate(hueco.desde)} – ${fmtDate(hueco.hasta)}</div><span class="hint-go">Cadencia →</span></div>
      <div class="ctrl-tile warn go" data-go="reloj"><div class="k">Nombre ≠ columna FECHA</div><div class="n">${arr(A.mismatchNombreHora).length}</div><div class="s">Desfaces de 358 a 544 minutos</div><span class="hint-go">Consistencia de fecha →</span></div>
    </div>
    <div class="card">
      <h3>Controles (lo que el inventario permite afirmar)</h3>
      <table><thead><tr><th></th><th>Control</th><th>Estado</th><th>Evidencia</th></tr></thead>
      <tbody>
        <tr><td><span class="sema y"></span></td><td>Cadencia diaria 2026</td><td>Parcial</td><td>${(A.cal2026 && A.cal2026.diasConBak) || 0}/${(A.cal2026 && A.cal2026.diasCalendario) || 0} días con .bak</td></tr>
        <tr><td><span class="sema r"></span></td><td>Segunda copia</td><td>No observable</td><td>Una sola hoja-host</td></tr>
        <tr><td><span class="sema r"></span></td><td>Historia clínica respaldada</td><td>Roto</td><td>SIHCLINICA último ${fmtDate((stats.find((s) => s.s === "SIHCLINICA") || {}).last)}</td></tr>
        <tr><td><span class="sema y"></span></td><td>Job AM = job PM (full)</td><td>Sospecha</td><td>Δ medio SIFacturacion ${(A.gemelasFact && A.gemelasFact.deltaMedioGB) || 0} GB</td></tr>
        <tr><td><span class="sema r"></span></td><td>Resultado del job</td><td>Ausente en .bak</td><td>Solo la hoja Verificaciones (ENVIAR)</td></tr>
        <tr><td><span class="sema g"></span></td><td>Última corrida 5×2</td><td>OK</td><td>${recsOn(D.hasta).length} archivos el ${fmtDate(D.hasta)}</td></tr>
      </tbody></table>
    </div>`;
}

function boardCapacidad() {
  const d = A.disco || { last: {}, daily2fullGB: 0, retencion: {} };
  const last = d.last || {};
  const gbOf = (k) => Object.values(((d.retencion || {})[k] || {}).gb || {}).reduce((a, b) => a + b, 0);
  const ret7 = gbOf("7");
  const ret30 = gbOf("30");
  const ret90 = gbOf("90");
  $("#board").innerHTML = `
    <div class="ctrl-grid" style="margin-bottom:14px">
      <div class="ctrl-tile info go" data-go="disco"><div class="k">Dos copias/día (último peso)</div><div class="n">${Number(d.daily2fullGB || 0).toFixed(1)}<span style="font-size:14px"> GB</span></div><div class="s">≈ ${fmtGB((d.daily2fullGB || 0) * 30)} / 30 días</div><span class="hint-go">Capacidad y retención →</span></div>
      <div class="ctrl-tile go" data-go="disco"><div class="k">Últimos 7 días (inventario)</div><div class="n" style="font-size:22px">${fmtGB(ret7)}</div><div class="s">Suma de archivos listados</div><span class="hint-go">Detalle →</span></div>
      <div class="ctrl-tile go" data-go="disco"><div class="k">Últimos 30 días</div><div class="n" style="font-size:22px">${fmtGB(ret30)}</div><div class="s">Cifra del Excel, no estimación</div><span class="hint-go">Detalle →</span></div>
      <div class="ctrl-tile warn go" data-go="disco"><div class="k">Últimos 90 días</div><div class="n" style="font-size:22px">${fmtGB(ret90)}</div><div class="s">SIFacturacion concentra la mayor parte</div><span class="hint-go">Detalle →</span></div>
    </div>
    <div class="card">
      <h3>Último peso por sistema activo</h3>
      ${bars(ACTIVE.map((s) => ({ l: s.replace("SI", "").slice(0, 8), v: (last[s] || {}).p || 0, color: s === "SIFacturacion" ? "#EA0B0B" : "#015AAA" })))}
      <table style="margin-top:10px"><thead><tr><th>Sistema</th><th>Último</th><th>Peso</th><th>×2 / día</th></tr></thead>
      <tbody>${ACTIVE.map((s) => {
        const o = last[s] || { f: "", h: "", pr: "—", p: 0 };
        return `<tr>
        <td>${esc(s)}</td><td>${fmtDate(o.f)} ${esc(o.h)}</td>
        <td>${esc(o.pr)}</td><td>${fmtGB(o.p * 2)}</td>
      </tr>`;
      }).join("")}</tbody></table>
    </div>`;
}

function boardSema() {
  const stats = bySystem();
  const lab = { g: "Al día (" + fmtDate(D.hasta) + ")", y: "Activo, no es el " + fmtDate(D.hasta), r: "Sin .bak el último día del Excel" };
  $("#board").innerHTML = `
    <div class="card">
      <h3>Semáforo al ${fmtDate(HOY_FORM)}</h3>
      <p class="legend-s"><span><i class="sema g"></i>${lab.g}</span><span><i class="sema y"></i>${lab.y}</span><span><i class="sema r"></i>${lab.r}</span></p>
      <table style="margin-top:10px"><thead><tr><th></th><th>Sistema</th><th>Último .bak</th><th>Antigüedad</th><th>Archivos</th><th>Peso último</th></tr></thead>
      <tbody>${stats.map((s) => {
        const c = semaforo(s);
        return `<tr>
          <td><span class="sema ${c}"></span></td>
          <td><b>${esc(s.s)}</b></td>
          <td>${fmtDate(s.last)} ${esc(s.lastH || "")}</td>
          <td>${diasHasta(s.last)} d</td>
          <td>${s.n}</td>
          <td>${esc(s.lastP)}</td>
        </tr>`;
      }).join("")}</tbody></table>
    </div>
`;
}

function viewMando() {
  const stats = bySystem();
  const y = D.anios.map((a) => a.reg);
  const lastDay = D.hasta;
  const lastN = recsOn(lastDay).length;
  const cad = cadenciaAnio(anioCadencia());
  const hueco = (cad.huecos && cad.huecos[0]) || { dias: 0, desde: D.hasta, hasta: D.hasta };
  const verdes = stats.filter((s) => semaforo(s) === "g").length;
  $("#view").innerHTML = `
    ${htmlAniosBar()}
<div class="grid g-4" style="margin-bottom:14px">
      <div class="card kpi go" data-go="bitacora" title="Abrir inventario de copias">
        <div class="lbl">Copias en el inventario</div>
        <div class="val">${D.total.toLocaleString("es-CO")}</div>
        <div class="delta">${fmtDate(D.desde)} → ${fmtDate(D.hasta)}</div>
        ${sparkline(y)}

      </div>
      <div class="card kpi go" data-go="sla" title="Abrir cumplimiento mensual">
        <div class="lbl">Cobertura ${ultimoAnio()} (Excel)</div>
        <div class="val">${cad.con}<span style="font-size:14px;color:var(--muted)"> / ${cad.cal}</span></div>
        <div class="delta">${fmtDate(cad.first)} → ${fmtDate(cad.last)}${cad.diario ? " · " + cad.sin + " días sin .bak" : ""}</div>

      </div>
      <div class="card kpi go" data-go="informe" title="Abrir informe de turno">
        <div class="lbl">Último día en inventario</div>
        <div class="val" style="font-size:22px">${fmtDate(lastDay)}</div>
        <div class="delta">${lastN} archivos · fecha del formato ${fmtDate(HOY_FORM)}</div>

      </div>
      <div class="card kpi go" data-go="cadencia" title="Abrir calendario de cadencia">
        <div class="lbl">Hueco 2026 más largo</div>
        <div class="val">${hueco.dias}<span style="font-size:14px"> d</span></div>
        <div class="delta down">${fmtDate(hueco.desde)} – ${fmtDate(hueco.hasta)}</div>

      </div>
    </div>
    <div class="grid g-23">
      <div class="brief">
        <h3>${fmtDate(HOY_FORM)}</h3>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn primary" data-go="tableros">Tableros de control</button>
          <button class="btn" data-go="informe">Informe de turno</button>
          <button class="btn" data-go="lote">Verificación del día</button>
          <button class="btn" data-go="verificar">Formato de verificación</button>
        </div>
      </div>
      <div class="card">
        <h3>Hallazgos con evidencia en el inventario</h3>
        <div class="q-card gap go" data-go="cadencia" style="margin-bottom:8px"><h4>${cad.diario ? cad.sin + " días de " + cad.y + " sin .bak en el Excel" : cad.con + " fechas de " + cad.y + " en el Excel"}</h4><p>${hueco.dias ? "Hueco más largo: " + hueco.dias + " días (" + fmtDate(hueco.desde) + " – " + fmtDate(hueco.hasta) + ")." : "Rango " + fmtDate(cad.first) + " → " + fmtDate(cad.last) + "."} Abrir cadencia →</p></div>
        <div class="q-card warn go" data-go="gemelas" style="margin-bottom:8px"><h4>Corridas 01:00 y 13:00 de peso similar</h4><p>SIFacturacion: ${(A.gemelasFact && A.gemelasFact.diasAmbos) || 0} días con ambas copias. Diferencia media ${(A.gemelasFact && A.gemelasFact.deltaMedioGB) || 0} GB. Abrir corridas gemelas →</p></div>
        <div class="q-card go" data-go="host"><h4>Cinco sistemas sin copia desde 2022</h4><p>${STOPPED.join(", ")}. El libro no indica apagado ni migración. Abrir continuidad operativa →</p></div>
      </div>
    </div>
    <div class="card" style="margin-top:14px">
      <h3>Último .bak por sistema</h3>
      <div class="year-tabs" id="ytabs">
        <button type="button" data-year="" class="on">Todos los años</button>
        ${D.anios.map((a) => `<button type="button" data-year="${a.anio}">${a.anio}</button>`).join("")}
      </div>
      <p class="tiny muted" id="ylab">${rangoAniosTxt()} · ${D.total.toLocaleString("es-CO")} archivos · ${fmtDate(D.desde)} → ${fmtDate(D.hasta)}</p>
      <div id="ylist">${htmlSysList(stats, null)}</div>
    </div>
    <div class="card" style="margin-top:14px">
      <h3>Matriz sistema × año</h3>
      ${htmlYearMatrix()}
    </div>
    <div class="card" style="margin-top:14px">
      <h3>Directorio de informes</h3>
      <div class="dir">${VIEWS.filter((v) => v.id !== "mando").map((v) => `
        <button type="button" class="dir-item" data-go="${v.id}">
          <b>${esc(v.label)}</b>
          <span>${esc(v.dest || "")}</span>
        </button>`).join("")}</div>
    </div>`;
  $$("[data-go]").forEach((b) => { b.onclick = () => go(b.dataset.go); });
  $$("#ytabs [data-year]").forEach((b) => {
    b.onclick = () => {
      $$("#ytabs button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      const y = b.dataset.year;
      const st = bySystem(y || null);
      const tot = st.reduce((a, s) => a + s.n, 0);
      $("#ylab").textContent = y
        ? `${y} · ${tot.toLocaleString("es-CO")} archivos · ${st.filter((s) => s.n).length} de ${D.sistemas.length} sistemas`
        : `${rangoAniosTxt()} · ${D.total.toLocaleString("es-CO")} archivos`;
      $("#ylist").innerHTML = htmlSysList(st, y || null);
    };
  });
}

function viewForm() {
  const sysOpts = D.sistemas.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  $("#view").innerHTML = `
    <div class="form-shell">
      <div class="form-head"><h2>FORMATO DE SEGUIMIENTO A COPIAS DE SEGURIDAD</h2></div>
      <form id="fver" class="form-body">
        <div class="field">
          <label>Fecha de verificación <span class="req">*</span></label>
          <input type="date" name="fecha" required value="${HOY_FORM}"><span class="hint">Fecha</span>
        </div>
        <div class="field">
          <label>Sistema / Carpeta <span class="req">*</span></label>
          <select name="sistema" required><option value="">Seleccione</option>${sysOpts}</select>
        </div>
        <div class="field">
          <label>Ubicación <span class="req">*</span></label>
          <input name="ubicacion" required value="${esc(D.ubicacion)}">
        </div>
        <div class="field">
          <label>Tipo de Backup <span class="req">*</span></label>
          <input name="tipo" required value=".bak">
        </div>
        <div class="field">
          <label>Resultado <span class="req">*</span></label>
          <select name="resultado" required>
            <option value="">Seleccione</option>
            ${RESULTADOS.map((r) => `<option>${r}</option>`).join("")}
          </select>
        </div>
        <div class="field full">
          <label>Observaciones</label>
          <textarea name="observaciones" rows="4"></textarea>
        </div>

        <div class="field">
          <label>Operador</label>
          <input name="operador" placeholder="Nombre de quien verifica">
        </div>
        <div class="field">
          <label>Tamaño observado</label>
          <input name="tamano" placeholder="ej. 11.36 GB">
        </div>
        <div class="field">
          <label>Duración (min)</label>
          <input name="duracion" type="number" min="0" step="1" placeholder="0">
        </div>
        <div class="field">
          <label>Hash / VERIFYONLY</label>
          <input name="hash" placeholder="SHA-256 o OK de RESTORE VERIFYONLY">
        </div>
        <div class="field">
          <label>Segunda copia</label>
          <input name="segunda" placeholder="No hay en el inventario · IP, cinta, NAS…">
        </div>
        <div class="field">
          <label>Restore de prueba</label>
          <select name="restore">
            <option value="">No realizado</option>
            <option>OK técnico</option>
            <option>OK clínico</option>
            <option>Falló</option>
          </select>
        </div>
      </form>
      <div class="form-foot">
        <img src="assets/logo.png" alt="">
        <div><b>Este formulario fue creado por la Oficina de Sistemas de Información</b><br>Clinica Cardioneurovascular PABON</div>
      </div>
      <div id="formErr" style="margin:0 22px 12px"></div>
      <div class="form-actions">
        <button class="btn ghost" type="button" id="btnReset">Limpiar</button>
        <button class="btn ok" type="button" id="btnSend">ENVIAR</button>
      </div>
    </div>
    <div class="card" style="max-width:820px;margin:14px auto 0" id="ctx"></div>`;
  const form = $("#fver");
  const ctx = () => {
    const s = bySystem().find((x) => x.s === form.sistema.value);
    const day = recsOn(form.fecha.value).filter((r) => r.s === form.sistema.value);
    if (!s) { $("#ctx").innerHTML = ""; return; }
    $("#ctx").innerHTML = `<h3>Cruce con el inventario</h3>
      <p class="meta">Último .bak: <span class="mono">${esc(s.lastA)}</span> · ${fmtDate(s.last)} ${esc(s.lastH)} · ${esc(s.lastP)}</p>
      <p class="meta">En la fecha de verificación (${fmtDate(form.fecha.value)}): ${day.length ? day.map((r) => `${r.h} · ${r.pr}`).join(" · ") : "<b>ningún .bak listado</b> (último día del Excel: " + fmtDate(D.hasta) + ")."}</p>`;
  };
  form.sistema.addEventListener("change", ctx);
  form.fecha.addEventListener("change", ctx);
  form.addEventListener("submit", (e) => { e.preventDefault(); enviarFormulario(); });
  $("#btnSend").onclick = (e) => { e.preventDefault(); enviarFormulario(); };
  ctx();
  $("#btnReset").onclick = () => { form.reset(); form.fecha.value = HOY_FORM; form.ubicacion.value = D.ubicacion; form.tipo.value = ".bak"; ctx(); const box = $("#formErr"); if (box) box.innerHTML = ""; };
}

function badgeRes(r) {
  if (r === "Fallido") return `<span class="badge b-bad">${r}</span>`;
  if (r === "No ejecutado") return `<span class="badge b-mute">${r}</span>`;
  if (r && r.includes("observ")) return `<span class="badge b-warn">${r}</span>`;
  return `<span class="badge b-ok">${r}</span>`;
}

function viewExtra() {
  const y = anioCadencia();
  const lista = state.extra.filter((r) => String(r.fecha || "").slice(0, 4) === String(y));
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="card">
    <h3>Hoja Verificaciones · ${y}</h3>

    <div style="margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap">
      <a class="btn primary" href="/api/excel">Descargar Excel actualizado</a>
      <button class="btn" type="button" id="reloadX">Recargar desde el archivo</button>
    </div>
    ${lista.length ? `<div class="table-wrap"><table><thead><tr>
      <th>Marca</th><th>Fecha</th><th>Sistema</th><th>Resultado</th><th>Operador</th><th>Cruce</th><th>Observaciones</th>
    </tr></thead>
      <tbody>${lista.map((r) => `<tr>
        <td class="mono tiny">${esc(r.id)}</td>
        <td class="mono">${fmtDate(r.fecha)}</td><td>${esc(r.sistema)}</td>
        <td>${badgeRes(r.resultado)}</td>
        <td>${esc(r.operador || "—")}</td>
        <td class="tiny">${esc(r.coincide || "—")}</td>
        <td>${esc(r.observaciones || "")}</td>
      </tr>`).join("")}</tbody></table></div>` : `<div class="empty">${state.extra.length ? "Ninguna verificación de " + y + "." : "Todavía no hay filas en Verificaciones."}</div>`}
  </div>`;
  const b = $("#reloadX");
  if (b) b.onclick = async () => { await pullExcel(); toast("Excel recargado"); viewExtra(); };
}

async function subirExcelArchivo(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file, file.name);
  toast("Leyendo " + file.name + "…");
  const res = await fetch("/api/excel-upload", { method: "POST", body: fd });
  const j = await res.json();
  if (!j.ok) throw new Error(j.error || "No se pudo cargar");
  toast("Inventario actualizado · " + j.total.toLocaleString("es-CO") + " .bak · " + j.hoja);
  setTimeout(() => location.reload(), 600);
  return j;
}

function bindDrop(zone) {
  if (!zone) return;
  const input = zone.querySelector('input[type="file"]');
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("on"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("on"));
  zone.addEventListener("drop", async (e) => {
    e.preventDefault(); zone.classList.remove("on");
    const f = e.dataTransfer.files[0];
    try { await subirExcelArchivo(f); } catch (err) { toast(err.message); }
  });
  if (input) input.onchange = async () => {
    try { await subirExcelArchivo(input.files[0]); } catch (err) { toast(err.message); }
  };
}

function pintarFuente(j) {
  const el = $("#fstatus");
  if (!el || !j) return;
  el.innerHTML = `
    <p class="meta">${j.activo ? "<b>Automático encendido</b>" : "<b>Automático apagado</b>"}
      · cada ${j.intervalo}s
      · ${j.existe ? (j.carpeta ? "carpeta encontrada" : "archivo encontrado") : "<span class='delta down'>no encontrada en este equipo</span>"}</p>
    <p class="tiny muted">Ruta: <span class="mono">${esc(j.ruta)}</span></p>
    ${j.archivo_usado ? `<p class="tiny muted">Excel en uso: <span class="mono">${esc(j.archivo_usado)}</span></p>` : ""}
    <p class="tiny muted">Modificado: ${esc(j.mtime_archivo || "—")}
      · última lectura: ${esc(j.ultimo_sync || "aún no")}
      ${j.ultimo_total != null ? " · " + Number(j.ultimo_total).toLocaleString("es-CO") + " archivos" : ""}
      ${j.ultimo_hasta ? " · hasta " + fmtDate(j.ultimo_hasta) : ""}</p>

    <p class="tiny muted">Copias nuevas: <span class="mono">${esc((arr(j.copias_lista).join(" · ") || j.copias || ""))}</span>
      · ${j.copias_existe ? "al menos una carpeta alcanzada" : "<span class='delta down'>ninguna alcanzada en este equipo</span>"}
      ${arr(j.copias_roots).length ? " · abiertas: " + arr(j.copias_roots).map(esc).join(" · ") : ""}
      ${j.copias_vistos != null ? " · " + j.copias_vistos + " .bak vistos" : ""}
      ${j.copias_nuevos != null ? " · " + j.copias_nuevos + " agregados al Excel" : ""}</p>
    ${j.copias_error ? `<p class="delta down">Copias: ${esc(j.copias_error)}</p>` : ""}
    ${j.ultimo_error ? `<p class="delta down">Último error: ${esc(j.ultimo_error)}</p>` : ""}`;
}

function viewExcelUp() {
  $("#view").innerHTML = `
    <h3>Fuente del inventario</h3>
    <div class="card" style="margin-bottom:14px">
      <h3>Ruta automática</h3>
      <div class="filters" style="margin:10px 0">
        <input id="fruta" style="flex:1;min-width:240px" placeholder="C:\\Users\\Db Developer\\Documents\\SENTINEL">
        <input id="fcopias" style="flex:1;min-width:240px" placeholder="\\\\172.168.100.10\\copias;\\\\172.168.10.100">
        <select id="fint">
          <option value="15">cada 15 s</option>
          <option value="30" selected>cada 30 s</option>
          <option value="60">cada 1 min</option>
          <option value="300">cada 5 min</option>
        </select>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn primary" type="button" id="fguardar">Guardar y conectar</button>
        <button class="btn" type="button" id="fsync">Leer ahora</button>
        <button class="btn ghost" type="button" id="fstop">Pausar automático</button>
      </div>
      <div id="fstatus" style="margin-top:12px"></div>
    </div>
    <div class="drop" id="dropx">
      <input type="file" id="xlsxfile" accept=".xlsx,.xlsm">
      Suelte un .xlsx
      <span>Inventario en uso: ${D.total.toLocaleString("es-CO")} archivos · ${fmtDate(D.desde)} → ${fmtDate(D.hasta)}</span>
    </div>
    <div class="grid g-2" style="margin-top:14px">
      ${arr(D.hojas).map((h) => `
        <div class="card">
          <h3>Hoja ${esc(h.hoja)}</h3>
          <p class="meta">${(h.reg || 0).toLocaleString("es-CO")} .bak · ${h.dias || 0} días</p>
          <p class="tiny muted">${fmtDate(h.desde)} → ${fmtDate(h.hasta)}</p>
          <p class="tiny">${arr(h.sistemas).map((s) => esc(s)).join(" · ")}</p>
        </div>`).join("") || `<div class="card"><p class="muted">No se leyeron las hojas 01-30 / 192.168.200.50. Cargue el Excel de Drive.</p></div>`}
    </div>`;
  bindDrop($("#dropx"));
  $("#dropx").onclick = (e) => { if (e.target.id !== "xlsxfile") $("#xlsxfile").click(); };
  const aplicar = async (extra) => {
    const body = Object.assign({
      ruta: $("#fruta").value.trim(),
      copias: ($("#fcopias") && $("#fcopias").value.trim()) || "\\\\172.168.100.10\\copias;\\\\172.168.10.100",
      intervalo: +$("#fint").value
    }, extra || {});
    const r = await fetch("/api/fuente", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    pintarFuente(j);
    if (!j.ok && j.error) toast(j.error);
    else if (j.ingesta) { toast("Inventario actualizado · " + j.ingesta.total + " archivos"); setTimeout(() => location.reload(), 700); }
    else toast(j.activo ? "Ruta conectada. Se actualizará solo." : "Automático en pausa");
    return j;
  };
  fetch("/api/fuente").then((r) => r.json()).then((j) => {
    if (j.ruta) $("#fruta").value = j.ruta;
    if (j.copias && $("#fcopias")) $("#fcopias").value = j.copias;
    if (j.intervalo) $("#fint").value = String(j.intervalo);
    pintarFuente(j);
  }).catch(() => pintarFuente({ activo: false, intervalo: 30, ruta: "", existe: false }));
  $("#fguardar").onclick = () => aplicar({ activo: true, sync: true });
  $("#fsync").onclick = () => aplicar({ activo: true, sync: true });
  $("#fstop").onclick = () => aplicar({ activo: false });
}

function viewBitacora() {
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="filters">
      <input id="q" placeholder="Buscar archivo…">
      <select id="fSys"><option value="">Sistema / Carpeta</option>${D.sistemas.map((s) => `<option>${esc(s)}</option>`).join("")}</select>
      <select id="fYear"><option value="">Año</option>${D.anios.map((a) => `<option ${Number(a.anio) === Number(anioCadencia()) ? "selected" : ""}>${a.anio}</option>`).join("")}</select>
      <input id="fDay" type="date" title="Filtrar fecha">
      <button class="btn" id="exp">CSV</button>
    </div>
    <div class="card table-wrap" id="tbl"></div>`;
  let page = 0;
  const draw = () => {
    const q = ($("#q").value || "").toLowerCase();
    const sy = $("#fSys").value, yr = $("#fYear").value, day = $("#fDay").value;
    const rows = D.records.filter((r) => {
      if (sy && r.s !== sy) return false;
      if (yr && r.f.slice(0, 4) !== yr) return false;
      if (day && r.f !== day) return false;
      if (q && !r.a.toLowerCase().includes(q)) return false;
      return true;
    });
    const size = 80, maxP = Math.max(0, Math.ceil(rows.length / size) - 1);
    if (page > maxP) page = 0;
    const slice = rows.slice(page * size, page * size + size);
    $("#tbl").innerHTML = `<table>
      <thead><tr><th>Fecha</th><th>Hora</th><th>Sistema</th><th>Archivo</th><th>Peso</th><th>Ubicación</th></tr></thead>
      <tbody>${slice.map((r) => `<tr>
        <td class="mono">${fmtDate(r.f)}</td><td class="mono">${esc(r.h)}</td>
        <td>${esc(r.s)}</td><td class="mono tiny">${esc(r.a)}</td>
        <td>${esc(r.pr)}</td><td class="mono">${esc(D.ubicacion)}</td>
      </tr>`).join("")}</tbody></table>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px">
        <span class="tiny muted">${rows.length.toLocaleString("es-CO")} · pág. ${page + 1}/${maxP + 1}</span>
        <div style="display:flex;gap:6px">
          <button class="btn" id="prev" ${page === 0 ? "disabled" : ""}>Anterior</button>
          <button class="btn" id="next" ${page >= maxP ? "disabled" : ""}>Siguiente</button>
        </div>
      </div>`;
    $("#prev").onclick = () => { page--; draw(); };
    $("#next").onclick = () => { page++; draw(); };
  };
  ["q", "fSys", "fYear", "fDay"].forEach((id) => $("#" + id).addEventListener("input", () => { page = 0; draw(); }));
  $("#exp").onclick = () => {
    const lines = ["fecha;hora;sistema;archivo;peso;ubicacion"];
    D.records.forEach((r) => lines.push([r.f, r.h, r.s, r.a, r.pr, D.ubicacion].map((x) => `"${String(x).replace(/"/g, '""')}"`).join(";")));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["\uFEFF" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
    a.download = "inventario-bak-192.168.200.50.csv";
    a.click();
  };
  draw();
}

function viewInventario() {
  const yInv = anioCadencia();
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="grid g-2">${bySystem(yInv).map((s) => {
      const viva = yInv ? s.n > 0 : ACTIVE.includes(s.s);
      return `<div class="card sys-card go" data-ficha="${esc(s.s)}" title="Abrir ficha técnica">
        <header>
          <div><div class="${viva ? "tag-med" : "tag-crit"}">${yInv ? (s.n ? s.n + " en " + yInv : "sin copia en " + yInv) : (viva ? "con copia el " + fmtDate(D.hasta) : "último " + fmtDate(s.last))}</div>
          <h4>${esc(s.s)}</h4></div>
          <span class="badge ${viva ? "b-ok" : "b-bad"}">${s.n} archivos</span>
        </header>
        <div class="meta">Ubicación <span class="mono">${esc(D.ubicacion)}</span><br>
          ${fmtDate(s.first)} → ${fmtDate(s.last)} ${esc(s.lastH || "")}<br>
          <span class="mono">${esc(s.lastA)}</span><br>Último peso ${esc(s.lastP)} · suma ${fmtGB(s.gb)}</div>
        <div class="bar"><i style="width:${Math.min(100, (s.n / 701) * 100)}%"></i></div>

      </div>`;
    }).join("")}</div>`;
}

function viewComp() {
  const y = anioCadencia();
  const byYearN = D.anios.map((a) => ({ l: String(a.anio).slice(2), v: a.reg, color: Number(a.anio) === y ? "#6ACEF5" : "#015AAA" }));
  const stats = bySystem(y);
  const wdL = ["L", "M", "X", "J", "V", "S", "D"];
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="grid g-2" style="margin-bottom:14px">
      <div class="card"><h3>Archivos por año</h3>${bars(byYearN)}</div>
      <div class="card"><h3>Día de la semana · ${y}</h3>
        ${bars(weekdayDe(y).map((v, i) => ({ l: wdL[i], v, color: "#12a36a" })))}</div>
    </div>
    <div class="card" style="margin-top:14px">
      <h3>Conteo por sistema · ${y}</h3>
      ${bars(stats.map((s) => ({ l: s.s.replace("SI", "").slice(0, 8), v: s.n, color: s.n ? "#12a36a" : "#9aa8b8" })), 720, 170)}
    </div>`;
}

function viewCadencia() {
  const years = arr(D.anios).map((a) => Number(a.anio));
  const y = anioCadencia();
  cadAnio = y;
  const C = cadenciaAnio(y);
  const names = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"];
  const dow = ["L", "M", "X", "J", "V", "S", "D"];
  const cals = [];
  const mesIni = C.diario || y === ultimoAnio() ? 1 : C.firstM;
  const mesFin = C.lastM;
  for (let mo = mesIni; mo <= mesFin; mo++) {
    const first = new Date(y, mo - 1, 1);
    const dim = new Date(y, mo, 0).getDate();
    const startPad = (first.getDay() + 6) % 7;
    let cells = dow.map((d) => `<span>${d}</span>`).join("");
    for (let i = 0; i < startPad; i++) cells += `<div class="d out"></div>`;
    let conMes = 0, revMes = 0;
    for (let day = 1; day <= dim; day++) {
      const iso = isoYmd(y, mo, day);
      const n = C.byDay[iso] || 0;
      let cls = "out";
      if (C.first && C.last && iso >= C.first && iso <= C.last) {
        cls = n > 0 ? "on" : "off";
        revMes++;
        if (n > 0) conMes++;
      }
      cells += `<div class="d ${cls}" data-day="${iso}" title="${iso} · ${n} archivo${n === 1 ? "" : "s"}">${day}</div>`;
    }
    cals.push(`<div class="cal"><h4>${names[mo - 1]} ${y} · ${conMes}/${revMes || dim}</h4><div class="cal-grid">${cells}</div></div>`);
  }
  const rango = (C.first && C.last) ? `${fmtDate(C.first)} → ${fmtDate(C.last)}` : String(y);
  const rarosShow = C.raros.slice(0, 60);
  const iY = years.indexOf(y);
  $("#view").innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <h3>Año</h3>
      <div class="year-tabs" id="cadYears">
        <button type="button" id="cadPrev" ${iY <= 0 ? "disabled" : ""} title="Año anterior">◀</button>
        ${years.map((a) => `<button type="button" data-cad-year="${a}" class="${a === y ? "on" : ""}">${a}</button>`).join("")}
        <button type="button" id="cadNext" ${iY < 0 || iY >= years.length - 1 ? "disabled" : ""} title="Año siguiente">▶</button>
      </div>
      <p class="tiny muted">${C.recs.length.toLocaleString("es-CO")} archivos en el Excel · ${rango}${C.diario ? " · ritmo diario" : " · solo fechas que están en el libro"}</p>
    </div>
    <div class="grid g-3" style="margin-bottom:14px">
      <div class="card kpi"><div class="lbl">Días con .bak</div><div class="val">${C.con}</div><div class="delta">${rango}</div></div>
      <div class="card kpi"><div class="lbl">Días sin .bak</div><div class="val">${C.diario ? C.sin : "—"}</div><div class="delta">${C.diario ? "entre primera y última fecha del Excel" : "no se inventan huecos"}</div></div>
      <div class="card kpi"><div class="lbl">${C.esperados ? "Días con ≠ " + C.esperados + " archivos" : "Archivos en el año"}</div><div class="val">${C.esperados ? C.raros.length : C.recs.length}</div><div class="delta">${C.esperados ? "el esperado es " + C.esperados : "según el Excel"}</div></div>
    </div>
    <div class="card" style="margin-bottom:14px">
      <h3>Huecos ${y}</h3>
      ${!C.diario
        ? `<p class="muted">En ${y} el Excel no es diario (${C.con} fechas). No se marcan huecos que no estén en el libro.</p>`
        : C.huecos.length
        ? `<table><thead><tr><th>Desde</th><th>Hasta</th><th>Días</th></tr></thead>
      <tbody>${C.huecos.map((h) => `<tr><td>${fmtDate(h.desde)}</td><td>${fmtDate(h.hasta)}</td><td><b>${h.dias}</b></td></tr>`).join("")}</tbody></table>`
        : `<p class="muted">No hay huecos entre ${fmtDate(C.first)} y ${fmtDate(C.last)}.</p>`}
    </div>
    <div class="card" style="margin-bottom:14px">
      <h3>Calendario ${y}</h3>
      <p class="tiny muted" style="margin:0 0 10px"><span class="cal-leg on"></span> hay .bak en el Excel &nbsp; <span class="cal-leg off"></span> no hay .bak ese día (se revisó) &nbsp; · ${C.con} verdes · ${C.sin} rojos · ${rango}</p>
      <div class="cal-wrap">${cals.join("")}</div>
    </div>
    <div class="card">
      <h3>${C.esperados ? `Días ${y} con cantidad distinta de ${C.esperados} .bak` : `Fechas ${y} en el Excel`}</h3>
      ${C.esperados
        ? (C.raros.length ? `<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Archivos</th><th>Detalle</th></tr></thead>
      <tbody>${rarosShow.map((d) => {
        const rs = recsOn(d.f);
        return `<tr><td class="mono">${fmtDate(d.f)}</td><td>${d.n}</td><td class="tiny">${rs.map((r) => `${esc(r.s)} ${esc(r.h)}`).join(" · ")}</td></tr>`;
      }).join("")}</tbody></table></div>
      ${C.raros.length > rarosShow.length ? `<p class="tiny muted">Se muestran 60 de ${C.raros.length}.</p>` : ""}`
        : `<p class="muted">Todos los días con copia en ${y} tienen ${C.esperados} archivos.</p>`)
        : `<p class="muted">${C.con} fechas listadas. No se espera 10 archivos/día en este año del Excel.</p>`}
    </div>`;
  const ir = (n) => {
    if (!years.length) return;
    const i = Math.max(0, Math.min(years.length - 1, years.indexOf(anioCadencia()) + n));
    elegirAnio(years[i]);
  };
  const prev = $("#cadPrev");
  const next = $("#cadNext");
  if (prev) prev.onclick = () => ir(-1);
  if (next) next.onclick = () => ir(1);
  $$("#cadYears [data-cad-year]").forEach((b) => {
    b.onclick = () => elegirAnio(b.dataset.cadYear);
  });
}

function showDay(iso) {
  const rs = recsOn(iso);
  const md = $("#modal");
  if (md) md.onclick = null;
  $("#modalBg").classList.add("show");
  $("#modal").innerHTML = `<h3 style="font-family:var(--display);margin:0 0 8px">${fmtDate(iso)}</h3>
    <p class="tiny muted">${rs.length} .bak · ${esc(D.ubicacion)}</p>
    ${rs.length ? `<table><thead><tr><th>Hora</th><th>Sistema</th><th>Archivo</th><th>Peso</th></tr></thead>
      <tbody>${rs.map((r) => `<tr><td class="mono">${esc(r.h)}</td><td>${esc(r.s)}</td><td class="mono tiny">${esc(r.a)}</td><td>${esc(r.pr)}</td></tr>`).join("")}</tbody></table>`
      : `<p>Ningún archivo ese día en el Excel.</p>`}
    <div style="margin-top:16px;text-align:right"><button class="btn" id="closeM">Cerrar</button></div>`;
  $("#closeM").onclick = () => $("#modalBg").classList.remove("show");
}

function viewGemelas() {
  const y = anioCadencia();
  const g = gemelasDe(y);
  const una = g.una;
  const muestra = g.muestra;
  $("#view").innerHTML = `
    ${htmlAniosBar()}
<h3>Corridas 01:00 y 13:00 · ${y}</h3>
    <div class="grid g-2" style="margin-bottom:14px">
      <div class="card">
        <h3>Días con una sola corrida (SIFacturacion ${y})</h3>
        ${una.length ? `<table><thead><tr><th>Fecha</th><th>Hora</th><th>Peso</th></tr></thead>
          <tbody>${una.map((x) => `<tr><td>${fmtDate(x.f)}</td><td class="mono">${esc(x.h)}</td><td>${esc(x.pr)}</td></tr>`).join("")}</tbody></table>`
          : `<p class="muted">Ninguno</p>`}
      </div>
      <div class="card">
        <h3>Últimos 8 días con ambas</h3>
        <table><thead><tr><th>Fecha</th><th>AM</th><th>PM</th><th>Δ GB</th></tr></thead>
        <tbody>${muestra.map((x) => `<tr><td>${fmtDate(x.f)}</td><td>${esc(x.am)}</td><td>${esc(x.pm)}</td><td>${x.d}</td></tr>`).join("")}</tbody></table>
      </div>
    </div>
    <div class="card">
      <h3>Hora que no encaja</h3>
      ${arr(A.horasRaras2026).filter((r) => String(r.f).slice(0, 4) === String(y)).length ? arr(A.horasRaras2026).filter((r) => String(r.f).slice(0, 4) === String(y)).map((r) => `
        <div class="q-card warn"><h4>${esc(r.s)} · ${fmtDate(r.f)} · ${esc(r.h)}</h4>
        <p>Peso ${esc(r.pr)}. El nombre del archivo es <span class="mono">${esc(r.a)}</span>.</p></div>`).join("") : `<p class="muted">Sin horas raras en ${y}.</p>`}
    </div>`;
}

function viewDeriva() {
  const y = anioCadencia();
  const g = arr(A.crecimientoFact);
  const ys = Object.keys(A.ultimoFact || {}).sort();
  const lastY = ys[ys.length - 1];
  const lastP = pesoAnio(lastY);
  const avg = g.length ? g.reduce((s, x) => s + x.delta, 0) / g.length : 0;
  const forecast = lastP + avg;
  const caidasY = arr(A.caidas).filter((c) => String(c.f).slice(0, 4) === String(y));
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="grid g-2" style="margin-bottom:14px">
      <div class="card">
        <h3>SIFacturacion · último peso de cada año</h3>
        ${bars(ys.map((y) => ({ l: y.slice(2), v: pesoAnio(y), color: "#EA0B0B" })))}

      </div>
      <div class="card">
        <h3>Incremento año a año</h3>
        <table><thead><tr><th>De</th><th>A</th><th>Peso final</th><th>Δ</th></tr></thead>
        <tbody>${g.map((x) => `<tr><td>${x.de}</td><td>${x.a}</td><td>${x.p1.toFixed(2)} GB</td><td>+${x.delta} GB</td></tr>`).join("")}</tbody></table>
      </div>
    </div>
    <div class="card">
      <h3>Caídas &gt; 30% vs. el .bak anterior del mismo sistema</h3>

      <table><thead><tr><th>Sistema</th><th>Fecha</th><th>Antes</th><th>Después</th><th>%</th></tr></thead>
      <tbody>${caidasY.map((c) => `<tr>
        <td class="go" data-ficha="${esc(c.s)}">${esc(c.s)}</td><td>${fmtDate(c.f)} ${esc(c.h)}</td>
        <td>${esc(c.antes)}</td><td>${esc(c.despues)}</td>
        <td class="delta down">−${c.pct}%</td>
      </tr>`).join("")}</tbody></table>

    </div>`;
}

function viewAlertas() {
  const y = anioCadencia();
  const cad = cadenciaAnio(y);
  const hueco = (cad.huecos && cad.huecos[0]) || { dias: 0, desde: D.hasta, hasta: D.hasta };
  const items = [
    { sev: "alta", go: "informe", t: "Formato del 28/10 sin copia ese día", d: `El inventario cierra el ${fmtDate(D.hasta)}. La verificación se cruza con esa corrida (10 archivos).` },
    { sev: "alta", go: "host", t: `${STOPPED.length} sistemas sin copia desde el 01/02/2022`, d: STOPPED.join(", ") + "." },
    { sev: "alta", go: "cadencia", t: `Hueco ${y} de ${hueco.dias} días`, d: `${fmtDate(hueco.desde)} – ${fmtDate(hueco.hasta)}.` },
    { sev: "media", go: "sla", t: `${cad.sin} días de ${y} sin copia`, d: `${cad.con}/${cad.cal} días con archivo.` },
    { sev: "media", go: "corridas", t: `${corridasDe(y).length} corridas AM/PM incompletas en ${y}`, d: "Se esperan las bases activas por bloque." },
    { sev: "media", go: "reloj", t: `${arr(A.mismatchNombreHora).filter((m) => String(m.f).slice(0, 4) === String(y)).length} archivos con hora distinta al nombre en ${y}`, d: "Hora del nombre distinta a la columna FECHA." },
    { sev: "media", go: "host", t: "Un solo host", d: `${D.ubicacion} concentra ${fmtGB(D.pesoTotalGB)} listados.` },
    { sev: "baja", ficha: "WinSisLab", t: "WinSisLab 02/07/2026 06:59 = 3,55 GB", d: "El resto de julio ≈ 696 MB. Nombre del archivo: 010002." }
  ];
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="grid g-2">${items.map((a) => `
      <div class="q-card go ${a.sev === "alta" ? "gap" : a.sev === "media" ? "warn" : ""}" ${a.go ? `data-go="${a.go}"` : ""} ${a.ficha ? `data-ficha="${a.ficha}"` : ""}>
        <h4>${esc(a.t)}</h4><p>${esc(a.d)}</p>

      </div>`).join("")}</div>`;
  $$("[data-go]").forEach((b) => { b.onclick = () => go(b.dataset.go); });
}

function viewCorridas() {
  const y = anioCadencia();
  const rows = corridasDe(y);
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <h3>Corridas incompletas · ${y}</h3>
    <div class="card">
      ${rows.length ? `<table><thead><tr><th>Fecha</th><th>Bloque</th><th>Archivos</th><th>Sistemas presentes</th><th>Faltan</th></tr></thead>
      <tbody>${rows.map((c) => `<tr>
          <td>${fmtDate(c.f)}</td><td>${c.b}</td><td>${c.n}/${ACTIVE.length || 5}</td>
          <td>${c.sistemas.map(esc).join(", ")}</td>
          <td class="delta down">${(c.falta || []).map(esc).join(", ")}</td>
        </tr>`).join("")}</tbody></table>` : `<p class="muted">En ${y} no hay bloques incompletos de las bases activas, o el Excel no es diario.</p>`}
    </div>
`;
}

function viewReloj() {
  const y = anioCadencia();
  const rows = arr(A.mismatchNombreHora).filter((m) => String(m.f).slice(0, 4) === String(y));
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <h3>Consistencia de fecha · ${y}</h3>
    <div class="card">
      ${rows.length ? `<table><thead><tr><th>Sistema</th><th>Columna FECHA</th><th>Hora en el nombre</th><th>Δ min</th><th>Archivo</th></tr></thead>
      <tbody>${rows.map((m) => `<tr>
        <td>${esc(m.s)}</td>
        <td>${fmtDate(m.f)} ${esc(m.h)}</td>
        <td class="mono">${esc(m.nombre)}</td>
        <td class="delta down">${m.diffMin}</td>
        <td class="mono tiny">${esc(m.a)}</td>
      </tr>`).join("")}</tbody></table>` : `<p class="muted">Ningún desfase nombre vs hora en ${y}.</p>`}
    </div>`;
}

function viewDisco() {
  const y = anioCadencia();
  const d = A.disco || { last: {}, daily2fullGB: 0, retencion: { "7": { gb: {}, n: {} }, "30": { gb: {}, n: {} }, "90": { gb: {}, n: {} } } };
  const last = {};
  D.records.forEach((r) => {
    if (Number(r.f.slice(0, 4)) !== y) return;
    last[r.s] = { f: r.f, h: r.h, pr: r.pr, p: r.p };
  });
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <h3>Capacidad y retención · ${y}</h3>
    <div class="card" style="margin-bottom:14px">
      <h3>Retención hipotética</h3>
      <p class="meta">Copias/día <select id="cpd"><option value="2" selected>2 (01:00 y 13:00)</option><option value="1">1</option></select>
      · días a guardar <input id="dias" type="range" min="7" max="365" value="30" style="width:180px;vertical-align:middle">
      <b id="diasv">30</b></p>
      <div id="discocal"></div>
    </div>
    <div class="grid g-3">
      ${["7", "30", "90"].map((k) => {
        const r = (d.retencion && d.retencion[k]) || { gb: {}, n: {} };
        const tot = Object.values(r.gb || {}).reduce((a, b) => a + b, 0);
        const n = Object.values(r.n || {}).reduce((a, b) => a + b, 0);
        return `<div class="card kpi"><div class="lbl">En inventario, últimos ${k} días</div>
          <div class="val" style="font-size:22px">${fmtGB(tot)}</div>
          <div class="delta">${n} archivos (conteo real del Excel)</div></div>`;
      }).join("")}
    </div>
    <div class="card" style="margin-top:14px">
      <h3>Último peso × 2 / día</h3>
      <table><thead><tr><th>Sistema</th><th>Último .bak</th><th>Peso</th><th>×2 / día</th></tr></thead>
      <tbody>${ACTIVE.map((s) => {
        const o = last[s] || { f: "", h: "", pr: "—", p: 0 };
        return `<tr>
        <td>${esc(s)}</td><td>${fmtDate(o.f)} ${esc(o.h)}</td>
        <td>${esc(o.pr)}</td><td>${fmtGB(o.p * 2)}</td>
      </tr>`;
      }).join("")}</tbody></table>
    </div>`;
  const draw = () => {
    const cpd = +$("#cpd").value, dias = +$("#dias").value;
    $("#diasv").textContent = dias;
    const rows = ACTIVE.map((s) => {
      const p = (last[s] && last[s].p) || 0;
      const gb = p * cpd * dias;
      return `<tr><td>${esc(s)}</td><td>${fmtGB(p)}</td><td>${fmtGB(gb)}</td></tr>`;
    }).join("");
    const tot = ACTIVE.reduce((a, s) => a + ((last[s] && last[s].p) || 0) * cpd * dias, 0);
    $("#discocal").innerHTML = `<table><thead><tr><th>Sistema</th><th>Peso unitario</th><th>Ocupación estimada</th></tr></thead>
      <tbody>${rows}<tr><td><b>Total</b></td><td></td><td><b>${fmtGB(tot)}</b></td></tr></tbody></table>
      <p class="tiny muted">No incluye índices, ni las 5 bases detenidas, ni el overhead del volumen.</p>`;
  };
  $("#cpd").onchange = draw;
  $("#dias").oninput = draw;
  draw();
}

function viewFicha() {
  const pre = state.sistema && D.sistemas.includes(state.sistema) ? state.sistema : D.sistemas[0];
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="brief" style="margin-bottom:12px">
      <h3>Ficha técnica del sistema</h3>
      <p>Expediente construido únicamente con las filas del inventario. No incluye dueño, RTO ni resultado del job.</p>
    </div>
    <div class="filters">
      <select id="fs">${D.sistemas.map((s) => `<option ${s === pre ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
      <button class="btn" type="button" data-go="inventario">Volver al catálogo</button>
      <button class="btn" type="button" data-go="verificar">Registrar verificación</button>
    </div>
    <div id="fichaout"></div>`;
  const draw = () => {
    const s = $("#fs").value;
    const y = anioCadencia();
    const rsAll = D.records.filter((r) => r.s === s);
    const rs = rsAll.filter((r) => Number(r.f.slice(0, 4)) === y);
    if (!rsAll.length) {
      $("#fichaout").innerHTML = `<p class="muted">No hay filas de ${esc(s)} en el Excel.</p>`;
      return;
    }
    if (!rs.length) {
      $("#fichaout").innerHTML = `<p class="muted">No hay filas de ${esc(s)} en ${y}.</p>`;
      return;
    }
    const years = {};
    rsAll.forEach((r) => { years[r.f.slice(0, 4)] = (years[r.f.slice(0, 4)] || 0) + 1; });
    const lastN = rs.slice(-12).reverse();
    const first = rs[0], last = rs[rs.length - 1];
    const sizes = [];
    const byMonth = {};
    rs.forEach((r) => {
      const k = r.f.slice(0, 7);
      byMonth[k] = r.p;
    });
    const mk = Object.keys(byMonth).slice(-24);
    $("#fichaout").innerHTML = `
      <div class="grid g-4" style="margin-bottom:14px">
        <div class="card kpi"><div class="lbl">Archivos ${y}</div><div class="val">${rs.length}</div><div class="delta">${rsAll.length} en todo el Excel</div></div>
        <div class="card kpi"><div class="lbl">Primero</div><div class="val" style="font-size:18px">${fmtDate(first.f)}</div><div class="delta">${esc(first.h)} · ${esc(first.pr)}</div></div>
        <div class="card kpi"><div class="lbl">Último</div><div class="val" style="font-size:18px">${fmtDate(last.f)}</div><div class="delta">${esc(last.h)} · ${esc(last.pr)}</div></div>
        <div class="card kpi"><div class="lbl">Suma listada</div><div class="val" style="font-size:18px">${fmtGB(rs.reduce((a, r) => a + r.p, 0))}</div></div>
      </div>
      <div class="card" style="margin-bottom:14px">
        <h3>Archivos por año</h3>
        ${bars(Object.keys(years).sort().map((yy) => ({ l: yy.slice(2), v: years[yy], color: Number(yy) === y ? "#6ACEF5" : (ACTIVE.includes(s) ? "#12a36a" : "#9aa8b8") })))}
      </div>
      <div class="card" style="margin-bottom:14px">
        <h3>Último peso por mes (24 meses)</h3>
        ${mk.length ? bars(mk.map((k) => ({ l: k.slice(2), v: byMonth[k], color: "#015AAA" })), 720, 160) : ""}
      </div>
      <div class="card">
        <h3>Últimos 12 .bak</h3>
        <table><thead><tr><th>Fecha</th><th>Hora</th><th>Peso</th><th>Archivo</th></tr></thead>
        <tbody>${lastN.map((r) => `<tr><td>${fmtDate(r.f)}</td><td class="mono">${esc(r.h)}</td><td>${esc(r.pr)}</td><td class="mono tiny">${esc(r.a)}</td></tr>`).join("")}</tbody></table>
      </div>`;
  };
  $("#fs").onchange = draw;
  draw();
}

function viewHost() {
  const y = anioCadencia();
  const stats = bySystem(y);
  const meta = arr(D.anios).find((a) => Number(a.anio) === y);
  const corte = (meta && meta.hasta) || D.hasta || HOY_FORM;
  const horas = (iso) => {
    const a = new Date(iso + "T00:00:00");
    const b = new Date(corte + "T00:00:00");
    return Math.round((b - a) / 36e5);
  };
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="brief" style="margin-bottom:14px">
      <h3>Un disco en ${esc(D.ubicacion)} · ${y}</h3>
      <p>El Excel no lista réplica. Si ese host no arranca el 28/10/2026, el punto restaurable es el último .bak de cada base — siempre que el archivo exista en otro lado, cosa que este libro no demuestra.</p>
    </div>
    <div class="card">
      <table><thead><tr><th>Sistema</th><th>Último .bak</th><th>Antigüedad al 28/10</th><th>Peso</th><th>Archivo</th></tr></thead>
      <tbody>${stats.map((s) => {
        const h = horas(s.last);
        const bad = !ACTIVE.includes(s.s) || h > 36;
        return `<tr>
          <td>${esc(s.s)}</td>
          <td>${fmtDate(s.last)} ${esc(s.lastH || "")}</td>
          <td class="${bad ? "delta down" : ""}">${h >= 24 ? Math.round(h / 24) + " d" : h + " h"}</td>
          <td>${esc(s.lastP)}</td>
          <td class="mono tiny">${esc(s.lastA)}</td>
        </tr>`;
      }).join("")}</tbody></table>
    </div>
    <p class="tiny muted" style="margin-top:10px">SIHCLINICA, SICITAS, laboratorio, kardex y PYP: último punto 01/02/2022 (~1.730 días). Facturación, almacén, SisConFi, SIIFNet y WinSisLab: 13–15 h (corrida de las 13:00 del 27/10).</p>`;
}

function hora12(h) {
  const p = String(h || "00:00").split(":");
  let hh = +p[0] || 0, mm = +p[1] || 0;
  const ap = hh < 12 ? "a. m." : "p. m.";
  const h12 = hh % 12 || 12;
  return `${pad2(h12)}:${pad2(mm)} ${ap}`;
}
function fmtDateObs(iso) {
  const [y, m, d] = String(iso || "").split("-");
  if (!d) return iso || "";
  return `${d}/${m}/${y}`;
}
function kbEnteros(p) {
  return Math.round(Number(p || 0) * 1024 * 1024);
}
function lineaObsBak(r) {
  const kb = kbEnteros(r.p).toLocaleString("en-US");
  return `${r.a} | ${fmtDateObs(r.f)} ${hora12(r.h)} | ${kb} KB`;
}
function parMananaTarde(rs) {
  const am = rs.filter((r) => String(r.h || "00:00") < "12:00").sort((a, b) => a.h.localeCompare(b.h));
  const pm = rs.filter((r) => String(r.h || "00:00") >= "12:00").sort((a, b) => a.h.localeCompare(b.h));
  return { am: am[0] || null, pm: pm[0] || null, extra: rs.length };
}
function resultadoDiaCompleto(par) {
  if (!par.am && !par.pm) return "Fallido";
  if (par.am && par.pm) return "Exitoso";
  return "Parcial";
}
function obsDiaCompleto(rs) {
  const par = parMananaTarde(rs);
  const lineas = [];
  if (par.am) lineas.push(lineaObsBak(par.am));
  if (par.pm) lineas.push(lineaObsBak(par.pm));
  if (par.am && par.pm) {
    const dKb = kbEnteros(par.pm.p) - kbEnteros(par.am.p);
    const signo = dKb > 0 ? "+" : "";
    lineas.push(`Diferencia tarde − mañana: ${signo}${dKb.toLocaleString("en-US")} KB`);
  } else if (par.am) {
    lineas.push("Falta copia de la tarde");
  } else if (par.pm) {
    lineas.push("Falta copia de la mañana");
  }
  return lineas.join("\n");
}

function resultadoDelDia(n) {
  if (!n) return "Fallido";
  if (n === 10) return "Exitoso";
  return "Parcial";
}

function verifDiaDe(iso) {
  const f = String(iso || "").trim();
  if (!f) return null;
  return arr(state.extra).find((e) => {
    const s = String(e.sistema || "").trim().toUpperCase();
    if (s !== "DIA") return false;
    return String(e.fecha || "").trim() === f || String(e.fechaBak || "").trim() === f;
  }) || null;
}

function viewLote() {
  const dia = recsOn(D.hasta);
  const n = dia.length;
  const auto = resultadoDelDia(n);
  const obs = dia.map(lineaObsBak).join("\n");
  const ya = verifDiaDe(D.hasta) || verifDiaDe(HOY_FORM);
  if (ya) {
    $("#view").innerHTML = `
      <h3>Verificación del día ${fmtDate(D.hasta)}</h3>
      <div class="card">
        <p class="meta">${n} / 10 · ${fmtDate(D.hasta)}</p>
        <p style="margin:10px 0 6px"><b>Ya enviado.</b> Este día no se puede enviar otra vez.</p>
        <p class="tiny muted">Resultado: ${esc(ya.resultado || "—")} · ${fmtDate(ya.fecha || D.hasta)}</p>
        ${ya.observaciones ? `<pre style="white-space:pre-wrap;font-family:var(--mono);font-size:12px;margin:12px 0 0">${esc(ya.observaciones)}</pre>` : ""}
        <div class="form-actions" style="padding:16px 0 0">
          <button class="btn" type="button" disabled>ENVIAR</button>
          <button class="btn primary" type="button" data-go="verificadas">Ver registro</button>
        </div>
      </div>`;
    $$("[data-go]").forEach((b) => { b.onclick = () => go(b.dataset.go); });
    return;
  }
  $("#view").innerHTML = `
    <h3>Verificación del día ${fmtDate(D.hasta)}</h3>
    <form id="flote" class="card">
      <p class="meta">${n} / 10 · ${fmtDate(D.hasta)}</p>
      <div class="field" style="max-width:280px;margin:12px 0">
        <label>Resultado <span class="req">*</span></label>
        <select name="resultado" required>
          <option value="">Resultado *</option>
          ${RESULTADOS.map((r) => `<option${r === auto ? " selected" : ""}>${r}</option>`).join("")}
        </select>
      </div>
      <label>Observaciones</label>
      <textarea name="observaciones" rows="${Math.min(12, Math.max(4, n))}" style="width:100%;border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:var(--card);font-family:var(--mono);font-size:12px;margin:6px 0 14px">${esc(obs)}</textarea>
      <div class="form-actions" style="padding:0"><button class="btn ok" type="button" id="btnDia">ENVIAR</button></div>
    </form>`;
  const enviarDia = async () => {
    if (verifDiaDe(D.hasta) || verifDiaDe(HOY_FORM)) {
      toast("Este día ya se envió");
      viewLote();
      return;
    }
    const f = $("#flote");
    if (!f) return;
    const resultado = f.resultado.value;
    if (!resultado) { toast("Falta Resultado"); return; }
    const btn = $("#btnDia");
    if (btn) { btn.disabled = true; btn.textContent = "Enviando…"; }
    const ultimo = dia[dia.length - 1];
    const payload = [{
      fecha: HOY_FORM,
      sistema: "DIA",
      ubicacion: D.ubicacion,
      tipo: ".bak",
      resultado,
      observaciones: f.observaciones.value.trim() || `${n} .bak el ${D.hasta}`,
      coincide: n === 10 ? `Sí · 10 .bak el ${D.hasta}` : `No · ${n} .bak el ${D.hasta} (se esperan 10)`,
      ultimoBak: ultimo ? ultimo.a : "",
      fechaBak: ultimo ? ultimo.f : D.hasta,
      horaBak: ultimo ? ultimo.h : "",
      pesoBak: ultimo ? ultimo.pr : ""
    }];
    try {
      await pushExcel(payload);
      toast("Día guardado en Excel · hoja Verificaciones");
      go("verificadas");
    } catch (err) {
      if (/ya (fue )?envi/i.test(err.message)) {
        toast("Este día ya se envió");
        await pullExcel();
        viewLote();
        return;
      }
      payload.forEach(registrarVerificacion);
      toast("No se pudo escribir el Excel: " + err.message);
      if (btn) { btn.disabled = false; btn.textContent = "ENVIAR"; }
    }
  };
  const btn = $("#btnDia");
  if (btn) btn.onclick = enviarDia;
  const form = $("#flote");
  if (form) form.onsubmit = (e) => { e.preventDefault(); enviarDia(); };
}

function pad2(n) { return String(n).padStart(2, "0"); }
function slaMeses() {
  const y = anioCadencia();
  const present = presentSet(y);
  const meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
  const meta = arr(D.anios).find((a) => Number(a.anio) === y);
  const first = (meta && meta.desde) || `${y}-01-01`;
  const last = (meta && meta.hasta) || D.hasta || first;
  const firstM = Number(first.slice(5, 7));
  const lastM = Number(last.slice(5, 7));
  const out = [];
  for (let m = firstM; m <= lastM; m++) {
    const dim = new Date(y, m, 0).getDate();
    const from = m === firstM ? Number(first.slice(8, 10)) : 1;
    const to = m === lastM ? Number(last.slice(8, 10)) : dim;
    let withD = 0, files = 0, gb = 0, days = 0;
    for (let d = from; d <= to; d++) {
      days++;
      if (present.has(`${y}-${pad2(m)}-${pad2(d)}`)) withD++;
    }
    D.records.forEach((r) => {
      if (r.f.startsWith(`${y}-${pad2(m)}`)) { files++; gb += r.p; }
    });
    out.push({ m, nom: meses[m - 1], last: days, withD, files, gb, pct: days ? (withD / days) * 100 : 0, y });
  }
  return out;
}

function viewSLA() {
  const y = anioCadencia();
  const rows = slaMeses();
  const totC = rows.reduce((a, r) => a + r.last, 0);
  const totW = rows.reduce((a, r) => a + r.withD, 0);
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="brief" style="margin-bottom:14px">
      <h3>Días con .bak en ${y} (Excel)</h3>
      <p>Se cuenta lo que está en el libro: días con al menos un .bak en ${y}. <b>${totW}/${totC} = ${totC ? (100 * totW / totC).toFixed(1) : "0"}%</b>.</p>
    </div>
    <div class="card">
      ${rows.map((r) => `
        <div class="sla-row">
          <b>${r.nom}</b>
          <div class="bar"><i style="width:${r.pct.toFixed(0)}%;background:${r.pct >= 90 ? "var(--ok)" : r.pct >= 50 ? "var(--warn)" : "var(--bad)"}"></i></div>
          <span>${r.pct.toFixed(0)}%</span>
          <span class="tiny muted">${r.withD}/${r.last} d · ${r.files} .bak · ${fmtGB(r.gb)}</span>
        </div>`).join("")}
    </div>
    <p class="tiny muted" style="margin-top:10px">Fuente: Excel ${esc(D.fuente || "")} · ${fmtDate(D.desde)} → ${fmtDate(D.hasta)}</p>`;
}

function viewCompare() {
  const years = D.anios.map((a) => a.anio);
  const ySel = anioCadencia();
  const yPrev = years[Math.max(0, years.indexOf(ySel) - 1)] || years[0];
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="filters">
      <select id="y1">${years.map((y) => `<option ${Number(y) === Number(yPrev) ? "selected" : ""}>${y}</option>`).join("")}</select>
      <span class="muted">vs</span>
      <select id="y2">${years.map((y) => `<option ${Number(y) === Number(ySel) ? "selected" : ""}>${y}</option>`).join("")}</select>
    </div>
    <div class="card" id="cmp"></div>`;
  const draw = () => {
    const a = $("#y1").value, b = $("#y2").value;
    const sa = bySystem(a), sb = bySystem(b);
    $("#cmp").innerHTML = `<table>
      <thead><tr><th>Sistema</th><th>${a} archivos</th><th>Último ${a}</th><th>${b} archivos</th><th>Último ${b}</th><th>Δ archivos</th></tr></thead>
      <tbody>${D.sistemas.map((s, i) => {
        const x = sa[i], y = sb[i], dlt = y.n - x.n;
        return `<tr>
          <td>${esc(s)}</td>
          <td>${x.n || "—"}</td><td class="tiny">${x.n ? fmtDate(x.last) + " · " + esc(x.lastP) : "—"}</td>
          <td>${y.n || "—"}</td><td class="tiny">${y.n ? fmtDate(y.last) + " · " + esc(y.lastP) : "—"}</td>
          <td class="${dlt > 0 ? "delta up" : dlt < 0 ? "delta down" : ""}">${dlt > 0 ? "+" : ""}${dlt}</td>
        </tr>`;
      }).join("")}</tbody></table>
      <p class="tiny muted" style="margin-top:8px">2025 vs 2026: las 5 activas pasan de ~66–70 archivos/año a ~443–446 (doble diario).</p>`;
  };
  $("#y1").onchange = draw; $("#y2").onchange = draw; draw();
}

function viewInforme() {
  const y = anioCadencia();
  const stats = bySystem(y);
  const sla = slaMeses();
  const meta = arr(D.anios).find((a) => Number(a.anio) === y);
  const corte = (meta && meta.hasta) || D.hasta;
  const ayer = recsOn(corte);
  const totC = sla.reduce((a, r) => a + r.last, 0);
  const totW = sla.reduce((a, r) => a + r.withD, 0);
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="brief" style="margin-bottom:14px">
      <h3>Informe de turno · ${y} · ${fmtDate(corte)}</h3>
      <p>Oficina de Sistemas · Clinica Cardioneurovascular PABON · fuente hoja ${esc(D.hoja)}</p>
      <button class="btn primary" id="printInf">Imprimir / PDF</button>
    </div>
    <div class="grid g-4" style="margin-bottom:14px">
      <div class="card kpi"><div class="lbl">.bak ${y}</div><div class="val">${(meta ? meta.reg : 0).toLocaleString("es-CO")}</div></div>
      <div class="card kpi"><div class="lbl">Último inventario ${y}</div><div class="val" style="font-size:20px">${fmtDate(corte)}</div><div class="delta">${ayer.length} archivos</div></div>
      <div class="card kpi"><div class="lbl">SLA ${y}</div><div class="val">${totC ? (100 * totW / totC).toFixed(0) : "0"}%</div></div>
      <div class="card kpi"><div class="lbl">Verificaciones hoy</div><div class="val">${state.extra.filter((e) => e.fecha === HOY_FORM).length}</div></div>
    </div>
    <div class="card" style="margin-bottom:14px">
      <h3>Corrida del ${fmtDate(corte)}</h3>
      <table><thead><tr><th>Hora</th><th>Sistema</th><th>Peso</th><th>Archivo</th></tr></thead>
      <tbody>${ayer.map((r) => `<tr><td class="mono">${esc(r.h)}</td><td>${esc(r.s)}</td><td>${esc(r.pr)}</td><td class="mono tiny">${esc(r.a)}</td></tr>`).join("")}</tbody></table>
    </div>
    <div class="card" style="margin-bottom:14px">
      <h3>Estado por sistema</h3>
      ${htmlSysList(stats, null)}
    </div>
    <div class="card">
      <h3>Alertas abiertas</h3>
      <ul class="meta">
        <li>5 bases sin .bak desde 01/02/2022.</li>
        <li>70 días 2026 sin archivo. Hueco máximo 17 d (2–18 feb).</li>
        <li>Un host: ${esc(D.ubicacion)}.</li>
        <li>3 desfaces nombre vs hora. Outlier WinSisLab 02/07/2026 06:59 = 3.55 GB.</li>
      </ul>
    </div>`;
  $("#printInf").onclick = () => window.print();
}

const MEJORAS = [
  { id: "job", t: "Pegar estado del job (ok/fail/código) al .bak", d: "Sin esto el rojo del calendario no es un incidente, es un vacío." },
  { id: "hash", t: "RESTORE VERIFYONLY o hash al cerrar la corrida", d: "Un .bak de 11 GB no prueba que SQL pueda leerlo." },
  { id: "copy2", t: "Segunda copia fuera de 192.168.200.50", d: "10 TB en un solo host. Ransomware o disco muerto = todo." },
  { id: "alert10", t: "Alerta si el día cierra ≠ 10 archivos", d: "El contrato 2026 es 5 bases × 2. Jun 21–22 lo rompe." },
  { id: "hc", t: "Decidir SIHCLINICA y las otras 4 de 2022", d: "¿Viven en otro motor? ¿Se deprecaron? El inventario no lo dice." },
  { id: "pm", t: "Revisar si las 13:00 deben seguir siendo full", d: "SIFacturacion ~11 GB × 2/día. Delta AM/PM ≈ 0." },
  { id: "enviar", t: "Que ENVIAR escriba en la misma hoja del Excel", d: "Hoy la verificación vive en el navegador, aparte del inventario." },
  { id: "restore", t: "Simulacro de restore trimestral con usuario clínico", d: "El DBA no es el criterio de éxito de una HC." },
  { id: "space", t: "Monitorear espacio libre del volumen", d: "Los huecos de feb/jun/ago podrían ser disco, parche o feriado." },
  { id: "rips", t: "Trazar JSON RIPS ↔ SIFacturacion", d: "La base que más crece y el archivo FEPB198527 no están ligados en estos datos." }
];

function viewMejoras() {
  const done = MEJORAS.filter((m) => state.checks[m.id]).length;
  $("#view").innerHTML = `
    <div class="brief" style="margin-bottom:14px">
      <h3>Mejoras que sí mueven el análisis</h3>
      <p>Priorizadas con lo que el Excel ya mostró. Marcadas: ${done}/${MEJORAS.length}. Se guardan en este navegador.</p>
    </div>
    <div class="card">
      ${MEJORAS.map((m) => `
        <label class="chk-row">
          <input type="checkbox" data-chk="${m.id}" ${state.checks[m.id] ? "checked" : ""}>
          <div><b>${esc(m.t)}</b><div class="tiny muted">${esc(m.d)}</div></div>
        </label>`).join("")}
    </div>`;
  $$("[data-chk]").forEach((el) => {
    el.onchange = () => { state.checks[el.dataset.chk] = el.checked; save(); };
  });
}

function buscarGlobal(q) {
  q = (q || "").trim().toLowerCase();
  if (q.length < 2) return;
  const hits = [];
  D.sistemas.forEach((s) => {
    if (s.toLowerCase().includes(q)) hits.push({ k: "sistema", t: s, go: "ficha", sistema: s });
  });
  D.records.filter((r) => r.a.toLowerCase().includes(q) || r.f.includes(q)).slice(-15).reverse()
    .forEach((r) => hits.push({ k: "archivo", t: `${r.f} ${r.h} · ${r.s} · ${r.a}`, day: r.f }));
  const md = $("#modal");
  if (md) md.onclick = null;
  $("#modalBg").classList.add("show");
  $("#modal").innerHTML = `<h3 style="font-family:var(--display);margin:0 0 8px">Buscar «${esc(q)}»</h3>
    ${hits.length ? hits.slice(0, 20).map((h) => `<div class="search-hit" data-hit="${esc(h.go || "")}" data-day="${h.day || ""}" data-sistema="${esc(h.sistema || "")}"><b>${esc(h.k)}</b> · ${esc(h.t)}</div>`).join("") : `<p class="muted">Sin coincidencias en el Excel.</p>`}
    <div style="margin-top:12px;text-align:right"><button class="btn" id="closeM">Cerrar</button></div>`;
  $("#closeM").onclick = () => $("#modalBg").classList.remove("show");
  $$("#modal [data-hit]").forEach((el) => {
    el.onclick = () => {
      $("#modalBg").classList.remove("show");
      if (el.dataset.sistema) { state.sistema = el.dataset.sistema; go("ficha"); }
      else if (el.dataset.day) showDay(el.dataset.day);
      else if (el.dataset.hit) go(el.dataset.hit);
    };
  });
}

function viewQ() {
  const tiene = [
    { ok: true, t: "Fecha y hora del archivo", d: "Columna FECHA del Excel, con hora al minuto." },
    { ok: true, t: "Sistema / carpeta", d: "Prefijo del .bak (10 bases)." },
    { ok: true, t: "Ubicación", d: "Una: 192.168.200.50 (nombre de la hoja)." },
    { ok: true, t: "Peso", d: "Por archivo, suficiente para ver deriva y copias gemelas." },
    { ok: true, t: "Tipo observable", d: "Extensión .bak. No hay full/diff/log." },
    { ok: false, t: "Resultado del job", d: "El formulario lo pide; el Excel no lo tiene. Un .bak listado no prueba que el restore funcione." },
    { ok: false, t: "Código / log del agente", d: "Veeam, SQL Agent, Maintenance Plan: no hay job-id ni error." },
    { ok: false, t: "Hash o CHECKSUM", d: "Sin huella no se detecta .bak truncado que pese “casi igual”." },
    { ok: false, t: "Duración", d: "Solo se infiere la ventana 01:00–01:04. No hay start/end por base." },
    { ok: false, t: "Segunda copia / offsite", d: "Un host. No hay cinta, NAS réplica ni object-lock." },
    { ok: false, t: "Retención", d: "No se sabe cuántas generaciones se borran ni si 192.168.200.50 se está llenando (SIFacturacion × 2/día × 11 GB)." },
    { ok: false, t: "Prueba de restauración", d: "Nadie en el libro confirma que un médico abra SIHCLINICA o que facturación lea el .bak." },
    { ok: false, t: "Operador", d: "El formato original cabecea un humano. Aquí todo parece job automático." },
    { ok: false, t: "Motivo de baja 2022", d: "Cinco bases desaparecen el 01/02/2022. ¿Migración, deprecación, job mal filtrado?" },
    { ok: false, t: "Espacio libre del volumen", d: "Los huecos de feb/jun/ago podrían ser disco lleno, parche o feriado. El Excel no lo dice." },
    { ok: false, t: "Alerta de cadencia", d: "En 2026 el contrato implícito es diario. Debería avisar al día siguiente de un rojo." }
  ];
  const qs = [
    { t: "¿Las copias de las 13:00 justifican el disco que comen?", d: "SIFacturacion ~11 GB × 2 = ~22 GB/día en un solo host. Si son dos full, la segunda no aporta RPO de 12 h si la primera ya está bien: aporta consumo." },
    { t: "¿Dónde está la historia clínica desde 2022?", d: "SIHCLINICA último .bak 01/02/2022 13:31, 2.51 GB. Si el HIS sigue vivo, el inventario no lo cubre." },
    { t: "¿El 02/07/2026 06:59 de WinSisLab fue un restore?", d: "Peso 3.55 GB vs ~696 MB. El nombre del archivo dice 010002 y la fecha 06:59. Hay que cruzar con el log de SQL Agent." },
    { t: "¿Quién verifica el 28/10 si el inventario cierra el 27/10?", d: "El formulario de la imagen está fechado un día después del último .bak. Eso es correcto como verificación al día siguiente, o un atraso de captura." },
    { t: "¿SIFacturacion es la fuente del JSON RIPS?", d: "El JSON FEPB198527 es nota crédito. El .bak de facturación crece 1.3–1.8 GB/año. Relación plausible, no demostrada en estos archivos." }
  ];
  $("#view").innerHTML = `
    <div class="brief" style="margin-bottom:14px">
      <h3>Para un buen análisis, este sistema tiene que dejar de ser un listado de .bak</h3>
      <p>Hoy responde: qué archivo, cuándo, cuánto pesa, en qué IP. Un análisis de copias de IPS tiene que responder también: ¿se puede restaurar?, ¿hay una copia que un ransomware no pueda cifrar?, ¿el job falló anoche?, ¿cuánto disco queda?, ¿quién firmó la verificación del formulario?</p>
    </div>
    <div class="grid g-13">
      <div class="card">
        <h3>Campos: lo que hay vs. lo que falta</h3>
        ${tiene.map((c) => `<div class="check">
          <div class="box ${c.ok ? "yes" : ""}">${c.ok ? "✓" : "!"}</div>
          <div><b>${esc(c.t)}</b><span>${esc(c.d)}</span></div>
        </div>`).join("")}
      </div>
      <div>
        <div class="card" style="margin-bottom:14px">
          <h3>Interrogantes abiertos (no se responden con el Excel)</h3>
          ${qs.map((q) => `<div class="q-card gap" style="margin-bottom:8px"><h4>${esc(q.t)}</h4><p>${esc(q.d)}</p></div>`).join("")}
        </div>
        <div class="card">
          <h3>Mínimo viable a agregar</h3>
          <ol class="meta" style="padding-left:18px;line-height:1.7">
            <li>Estado del job (ok / fail / código) al mismo minuto del .bak.</li>
            <li>Hash SHA-256 o <span class="mono">RESTORE VERIFYONLY</span>.</li>
            <li>Copia 2: NAS distinto o cinta. IP única = un disco muerto borra 10.09 TB de historia.</li>
            <li>Alerta si un día 2026-like cierra con ≠ 10 archivos.</li>
            <li>Bitácora de restore trimestral (clínica, no solo DBA).</li>
            <li>Inventario vivo de las 5 bases que callaron en 2022.</li>
            <li>El ENVIAR del formulario debería escribir en la misma hoja, no en otro cajón.</li>
          </ol>
        </div>
      </div>
    </div>`;
}

function viewHuecos() {
  const y = anioCadencia();
  const C = cadenciaAnio(y);
  $("#view").innerHTML = `
    ${htmlAniosBar()}
    <div class="brief" style="margin-bottom:14px">
      <h3>Meses sin captura · ${y}</h3>
      <p>${esc(D.faltantes)}</p>
      <p>${(D.destacados && D.destacados.mesesSinCaptura) || "—"} meses marcados en el libro.</p>
    </div>
    <div class="card" style="margin-bottom:14px">
      <h3>Huecos ${y}</h3>
      ${!C.diario
        ? `<p class="muted">En ${y} el Excel no es diario (${C.con} fechas). No se marcan huecos que no estén en el libro.</p>`
        : C.huecos.length
        ? `<table><thead><tr><th>Desde</th><th>Hasta</th><th>Días</th></tr></thead>
      <tbody>${C.huecos.map((h) => `<tr><td>${fmtDate(h.desde)}</td><td>${fmtDate(h.hasta)}</td><td><b>${h.dias}</b></td></tr>`).join("")}</tbody></table>`
        : `<p class="muted">No hay huecos entre ${fmtDate(C.first)} y ${fmtDate(C.last)}.</p>`}
    </div>
    <div class="card table-wrap">
      <h3>Totales por año (hoja Resumen)</h3>
      <table>
        <thead><tr><th>Año</th><th>Registros</th><th>Días</th><th>Peso</th><th>Promedio</th><th>Desde</th><th>Hasta</th></tr></thead>
        <tbody>
          ${D.anios.map((a) => `<tr class="${Number(a.anio) === y ? "on-year" : ""}">
            <td>${a.anio}</td><td>${a.reg.toLocaleString("es-CO")}</td><td>${a.dias}</td>
            <td>${esc(a.peso)}</td><td>${esc(a.prom)}</td>
            <td class="mono">${fmtDate(a.desde)}</td><td class="mono">${fmtDate(a.hasta)}</td>
          </tr>`).join("")}
          <tr><td><b>Total</b></td><td><b>${D.total.toLocaleString("es-CO")}</b></td><td>${D.anios.reduce((a, x) => a + x.dias, 0)}</td><td><b>${fmtGB(D.pesoTotalGB)}</b></td><td>${D.total ? fmtGB(D.pesoTotalGB / D.total) : "—"}</td><td>${fmtDate(D.desde)}</td><td>${fmtDate(D.hasta)}</td></tr>
        </tbody>
      </table>
    </div>`;
}

const RIPS_MAP = {
  tipoUsuario: { "01": "Contributivo", "02": "Subsidiado", "03": "Especial / excepción", "04": "No afiliado / particular", "05": "Extranjero" },
  tipoDoc: { CC: "Cédula de ciudadanía" },
  sexo: { M: "Masculino", F: "Femenino" },
  zona: { "01": "Urbana", "02": "Rural" },
  nota: { NC: "Nota crédito", ND: "Nota débito" }
};
function mapCode(dict, v) {
  if (v == null || v === "") return "—";
  return RIPS_MAP[dict]?.[String(v)] ? `${v} · ${RIPS_MAP[dict][String(v)]}` : String(v);
}
function viewRips() {
  $("#view").innerHTML = `
    <div class="rips-hero">
      <div>
        <h2>JSON RIPS adjunto</h2>
        <p><span class="mono">RIPS_900900155_FEPB198527.json</span> — no salió del Excel de .bak.</p>
        <button class="btn" id="loadSample" style="margin-top:12px;background:#fff;color:#013E74">Mostrar FEPB198527</button>
      </div>
      <div><p>Pregunta abierta: ¿este JSON se genera desde SIFacturacion, cuya base es la que más crece?</p></div>
    </div>
    <div id="ripsOut" style="margin-top:14px"></div>`;
  $("#loadSample").onclick = async () => {
    let j;
    try {
      const r = await fetch("assets/rips-sample.json");
      if (!r.ok) throw new Error("archivo no encontrado");
      j = await r.json();
    } catch (err) {
      toast("No se pudo leer el RIPS: " + err.message);
      return;
    }
    const u = (j.usuarios && j.usuarios[0]) || {};
    const proc = (((u.servicios || {}).procedimientos) || [])[0] || {};
    $("#ripsOut").innerHTML = `<div class="card"><div class="kv">
      <b>NIT</b><span class="mono">${esc(j.numDocumentoIdObligado)}</span>
      <b>Factura</b><span>${esc(j.numFactura)}</span>
      <b>Nota</b><span>${esc(mapCode("nota", j.tipoNota))} ${esc(j.numNota)}</span>
      <b>Documento</b><span>${esc(mapCode("tipoDoc", u.tipoDocumentoIdentificacion))} ${esc(u.numDocumentoIdentificacion)}</span>
      <b>Sexo</b><span>${esc(mapCode("sexo", u.codSexo))}</span>
      <b>Nacimiento</b><span>${esc(u.fechaNacimiento)}</span>
      <b>Usuario</b><span>${esc(mapCode("tipoUsuario", u.tipoUsuario))}</span>
      <b>Municipio</b><span>${esc(u.codMunicipioResidencia)}</span>
      <b>Zona</b><span>${esc(mapCode("zona", u.codZonaTerritorialResidencia))}</span>
      <b>Incapacidad</b><span>${esc(u.incapacidad)}</span>
      <b>Prestador</b><span class="mono">${esc(proc.codPrestador)}</span>
      <b>Atención</b><span>${esc(proc.fechaInicioAtencion)}</span>
      <b>CUPS</b><span>${esc(proc.codProcedimiento)}</span>
      <b>Dx</b><span>${esc(proc.codDiagnosticoPrincipal)}</span>
      <b>Valor</b><span>${proc.vrServicio}</span>
      <b>Autorización</b><span class="mono">${esc(proc.numAutorizacion)}</span>
    </div><pre class="codeblock" style="margin-top:14px">${esc(JSON.stringify(j, null, 2))}</pre></div>`;
  };
}

function showGuia() { showAyuda(); }

function showAyuda() {
  const dia = recsOn(D.hasta);
  const nDia = dia.length;
  const stats = bySystem();
  const ejLines = dia.slice(0, 4).map(lineaObsBak);
  const glos = [
    { id: "sentinel", t: "SENTINEL PABON", d: "Sistema de la clínica para ver si las copias de seguridad existen y para dejar constancia del turno. No es el programa que hace el backup: solo lo registra y lo verifica.", e: "Clinica Cardioneurovascular PABON · Oficina de Sistemas" },
    { id: "bak", t: ".bak", d: "Archivo de copia de una base SQL Server. El nombre suele llevar el sistema, la fecha y la hora.", e: dia[0] ? dia[0].a : "SCAlmacen_backup_2026_10_27_010002_1907384.bak" },
    { id: "host", t: "Host", d: "Equipo donde se generan las copias. En este inventario hay uno solo.", e: D.ubicacion || "192.168.200.50" },
    { id: "inventario", t: "Inventario", d: "El Excel con columnas FECHA, ARCHIVO y PESO por año. De ahí salen todos los tableros. Hoy hay " + D.total.toLocaleString("es-CO") + " archivos, del " + fmtDate(D.desde) + " al " + fmtDate(D.hasta) + ".", e: D.fuente || "inventario-backups.xlsx" },
    { id: "dia", t: "Día", d: "La verificación del turno mira el día entero, no cada sistema. Un día en regla tiene 10 .bak: mañana y tarde de las 5 bases que siguen activas.", e: fmtDate(D.hasta) + " · " + nDia + " archivos" },
    { id: "exitoso", t: "Exitoso", d: "Ese día hay exactamente 10 copias.", e: "10 / 10 → Exitoso" },
    { id: "parcial", t: "Parcial", d: "Hay copias, pero no llegan a 10. Falta alguna mañana o tarde.", e: "7 / 10 → Parcial" },
    { id: "fallido", t: "Fallido", d: "Ese día no hay ningún .bak en el inventario.", e: "0 / 10 → Fallido" },
    { id: "obs", t: "Observaciones", d: "Texto que se guarda con el acta. En la verificación del día se arma así: archivo | fecha hora | KB.", e: ejLines[0] || "" },
    { id: "enviar", t: "ENVIAR", d: "Graba una fila en la hoja Verificaciones del Excel. No borra .bak ni inventa Resultado: usa lo que usted confirma.", e: "Debe estar en http://localhost:8080 con el servidor Python" },
    { id: "sema", t: "Semáforo", d: "Verde: hay copia el último día del Excel. Amarillo: el sistema aún tiene copias recientes, pero no ese día. Rojo: no hay copia desde 2022.", e: ACTIVE.length + " activos · " + STOPPED.length + " detenidos" },
    { id: "corrida", t: "Corrida", d: "Los .bak de la misma fecha en la mañana (antes de las 12:00) o en la tarde.", e: "01:00 a. m. y 01:00 p. m." },
    { id: "activa", t: "Base activa", d: "Sistema cuyo último .bak es el último día del inventario.", e: ACTIVE.join(", ") || "—" },
    { id: "detenida", t: "Base detenida", d: "Sistema que dejó de aparecer. Aquí, el 01/02/2022.", e: STOPPED.join(", ") || "—" },
    { id: "sla", t: "Cumplimiento", d: "Porcentaje de días del año (hasta el último del Excel) que tienen al menos una copia.", e: ((A.cal2026 && A.cal2026.diasConBak) || 0) + " de " + ((A.cal2026 && A.cal2026.diasCalendario) || 0) + " días" },
    { id: "ficha", t: "Ficha", d: "Historial de un sistema: primer y último archivo, pesos, años. Se abre pulsando el nombre.", e: "Ejemplo: " + (ACTIVE[0] || D.sistemas[0] || "SIFacturacion") },
    { id: "verif", t: "Verificaciones", d: "Hoja del Excel donde quedan las actas del turno. Es distinta de la lista de .bak.", e: state.extra.length + " filas en este equipo" },
    { id: "red", t: "Carpeta de red", d: "Donde aparecen las copias nuevas. SENTINEL las suma al Excel si no estaban.", e: "\\\\172.168.100.10\\copias · \\\\172.168.10.100" },
    { id: "rto", t: "RTO / Resultado", d: "El inventario no dice si el job salió bien. Eso solo existe cuando alguien pulsa ENVIAR.", e: "No se rellena solo desde el .bak" }
  ];
  const pasos = [
    { t: "Bienvenida", p: "SENTINEL PABON es el tablero de copias de la clínica. Usted mira si el .bak está y deja constancia del turno. No es el motor que hace el backup." },
    { t: "Dos verdades", p: "1) El Excel lista archivos (existen o no). 2) ENVIAR escribe el acta (Exitoso, Parcial o Fallido). Nunca se inventa un resultado." },
    { t: "Pantalla", p: "Izquierda: menú. Arriba: buscar sistema o fecha, Ayuda, imprimir, tema. Centro: la vista. El logo SENTINEL PABON vuelve al inicio." },
    { t: "Menú corto y completo", p: "Corto: lo del turno (resumen, tableros, verificar, el día, inventario). Completo: cadencia, disco, RIPS y el resto del análisis." },
    { t: "Semáforos", p: "Verde = hay .bak el " + fmtDate(D.hasta) + ". Amarillo = el sistema sigue, pero no ese día. Rojo = sin copia desde 2022 (" + STOPPED.join(", ") + ")." },
    { t: "El día", p: "En Verificación del día se cuentan los .bak de esa fecha. 10 = Exitoso, 1 a 9 = Parcial, 0 = Fallido. No se parte por sistema." },
    { t: "Formato", p: "El formato institucional es por sistema (SIFacturacion, SCAlmacen…). El resultado lo elige usted. ENVIAR lo guarda en Verificaciones." },
    { t: "Excel y red", p: "Inventario en Documentos\\SENTINEL. Copias nuevas en \\\\172.168.100.10\\copias y \\\\172.168.10.100. Hay que abrir SENTINEL con iniciar-SENTINEL.bat (http://localhost:8080)." },
    { t: "Listo", p: "Pruebe las otras pestañas: Palabras, Colores, El día, Mapa y Práctica. Pulse un nombre de menú para ir ahí." }
  ];
  const quiz = [
    { q: "Si el día tiene 10 archivos .bak, el resultado es…", ok: 0, op: ["Exitoso", "Parcial", "Fallido"] },
    { q: "¿SENTINEL inventa si el job de SQL salió bien?", ok: 1, op: ["Sí, lo lee del .bak", "No: solo ENVIAR deja el Resultado"] },
    { q: "¿La verificación del día se hace por cada sistema?", ok: 1, op: ["Sí, una tarjeta por base", "No: se cuenta el día completo (10 copias)"] },
    { q: "Rojo en el semáforo significa…", ok: 2, op: ["El job falló", "Falta la corrida de la tarde", "No hay .bak de ese sistema desde 2022"] }
  ];
  $("#modalBg").classList.add("show");
  $("#modal").innerHTML = `
    <h3>Ayuda · SENTINEL PABON</h3>
    <div class="help-tabs">
      <button type="button" class="on" data-htab="tour">Recorrido</button>
      <button type="button" data-htab="pal">Palabras</button>
      <button type="button" data-htab="col">Colores</button>
      <button type="button" data-htab="dia">El día</button>
      <button type="button" data-htab="map">Mapa</button>
      <button type="button" data-htab="quiz">Práctica</button>
      <button type="button" data-htab="ej">Ejemplo real</button>
    </div>
    <div class="help-pane on" data-hpane="tour">
      <div class="help-step" id="tourBox"></div>
      <div class="help-nav">
        <button type="button" class="btn" id="tourPrev">Anterior</button>
        <button type="button" class="btn primary" id="tourNext">Siguiente</button>
      </div>
    </div>
    <div class="help-pane" data-hpane="pal">
      <h4>Pulse una palabra</h4>
      <div class="glos">${glos.map((g, i) => `<button type="button" data-glos="${g.id}" class="${i === 0 ? "on" : ""}">${g.t}</button>`).join("")}</div>
      <div class="glos-def" id="glosDef"></div>
    </div>
    <div class="help-pane" data-hpane="col">
      <h4>Pulse un color</h4>
      <div class="sema-demo">
        <button type="button" data-sema="g"><i class="sema g"></i> Verde</button>
        <button type="button" data-sema="y"><i class="sema y"></i> Amarillo</button>
        <button type="button" data-sema="r"><i class="sema r"></i> Rojo</button>
      </div>
      <div class="glos-def" id="semaDef"></div>
    </div>
    <div class="help-pane" data-hpane="dia">
      <h4>Califique un día</h4>
      <p>Mueva el control. SENTINEL aplica la regla del turno.</p>
      <p class="meta">Archivos del día: <b id="simN">${nDia}</b> / 10</p>
      <input id="simRange" type="range" min="0" max="12" value="${Math.min(12, nDia)}" style="width:100%">
      <div class="sim-out" id="simOut"></div>
    </div>
    <div class="help-pane" data-hpane="map">
      <h4>Pulse para abrir esa pantalla</h4>
      <div class="help-map">${VIEWS.map((v) => `<button type="button" data-gohelp="${v.id}">${esc(v.label)}<small>${esc(v.sec)}</small></button>`).join("")}</div>
    </div>
    <div class="help-pane" data-hpane="quiz">
      <h4 id="quizQ"></h4>
      <div id="quizOps"></div>
      <p class="meta" id="quizScore"></p>
      <button type="button" class="btn" id="quizNext" hidden>Siguiente pregunta</button>
    </div>
    <div class="help-pane" data-hpane="ej">
      <h4>Último día del inventario · ${fmtDate(D.hasta)}</h4>
      <p>${nDia} / 10 · ${resultadoDelDia(nDia)} · ${D.total.toLocaleString("es-CO")} archivos en total</p>
      <div class="ej-dia">${esc((ejLines.join("\n") || "Sin .bak") + (dia.length > 4 ? "\n…" : ""))}</div>
      <p class="meta">Activas: ${esc(ACTIVE.join(", ") || "—")}</p>
      <p class="meta">Sin copia desde 2022: ${esc(STOPPED.join(", ") || "—")}</p>
    </div>
    <div style="margin-top:14px;display:flex;justify-content:flex-end">
      <button class="btn primary" type="button" id="closeM">Cerrar</button>
    </div>`;

  let ti = 0;
  const tourBox = () => {
    const s = pasos[ti];
    $("#tourBox").innerHTML = `<div class="nstep">Paso ${ti + 1} de ${pasos.length}</div><h4>${esc(s.t)}</h4><p>${esc(s.p)}</p>`;
    $("#tourPrev").disabled = ti === 0;
    $("#tourNext").textContent = ti === pasos.length - 1 ? "Terminar recorrido" : "Siguiente";
  };
  tourBox();

  const pintarGlos = (id) => {
    const g = glos.find((x) => x.id === id) || glos[0];
    $$(".glos button").forEach((b) => b.classList.toggle("on", b.dataset.glos === g.id));
    $("#glosDef").innerHTML = `<h4>${esc(g.t)}</h4><p>${esc(g.d)}</p><div class="ej">${esc(g.e)}</div>`;
  };
  pintarGlos("sentinel");

  const semaTxt = {
    g: { t: "Verde", d: "Hay .bak el " + fmtDate(D.hasta) + ". No significa que el job se haya verificado: solo que el archivo está en el Excel.", e: stats.filter((s) => semaforo(s) === "g").map((s) => s.s).join(", ") || "ninguno" },
    y: { t: "Amarillo", d: "El sistema sigue teniendo copias en 2026, pero no el último día del inventario.", e: stats.filter((s) => semaforo(s) === "y").map((s) => s.s).join(", ") || "ninguno" },
    r: { t: "Rojo", d: "No hay copia desde 2022. El libro no dice si se apagó o se migró.", e: STOPPED.join(", ") || "ninguno" }
  };
  const pintarSema = (k) => {
    const o = semaTxt[k];
    $$("[data-sema]").forEach((b) => b.classList.toggle("on", b.dataset.sema === k));
    $("#semaDef").innerHTML = `<h4>${esc(o.t)}</h4><p>${esc(o.d)}</p><div class="ej">${esc(o.e)}</div>`;
  };
  pintarSema("g");

  const pintarSim = (n) => {
    const r = resultadoDelDia(n);
    $("#simN").textContent = n;
    const el = $("#simOut");
    el.className = "sim-out " + (r === "Exitoso" ? "ok" : r === "Parcial" ? "mid" : "bad");
    el.textContent = n + " / 10  →  " + r;
  };
  const rg = $("#simRange");
  if (rg) rg.oninput = () => pintarSim(+rg.value);
  pintarSim(Math.min(12, nDia));


  let qi = 0, aciertos = 0, locked = false, fin = false;
  const pintarQuiz = () => {
    fin = false;
    locked = false;
    const item = quiz[qi];
    if (!item) return;
    const qel = $("#quizQ"), ops = $("#quizOps"), sc = $("#quizScore"), nx = $("#quizNext");
    if (!qel || !ops || !nx) return;
    qel.textContent = "Pregunta " + (qi + 1) + " de " + quiz.length + " · " + item.q;
    ops.innerHTML = item.op.map((o, i) => `<button type="button" class="quiz-opt" data-qi="${i}">${esc(o)}</button>`).join("");
    sc.textContent = qi ? (aciertos + " bien de " + qi) : "Elija una respuesta";
    nx.hidden = true;
    nx.textContent = "Siguiente pregunta";
  };
  const responder = (i) => {
    if (locked || fin) return;
    const item = quiz[qi];
    if (!item) return;
    locked = true;
    $$("#quizOps .quiz-opt").forEach((x, j) => {
      x.classList.add(j === item.ok ? "good" : (j === i ? "bad" : ""));
      x.disabled = true;
    });
    if (i === item.ok) aciertos++;
    $("#quizScore").textContent = (i === item.ok ? "Correcto. " : "Era: " + item.op[item.ok] + ". ") + aciertos + " bien.";
    const nx = $("#quizNext");
    nx.hidden = false;
    nx.textContent = qi >= quiz.length - 1 ? "Ver resultado" : "Siguiente pregunta";
  };
  const avanzarQuiz = () => {
    if (fin) {
      qi = 0; aciertos = 0; pintarQuiz();
      return;
    }
    if (qi < quiz.length - 1) {
      qi++;
      pintarQuiz();
      return;
    }
    fin = true;
    $("#quizQ").textContent = "Resultado";
    $("#quizOps").innerHTML = aciertos === quiz.length
      ? "<p>Puede cubrir un turno.</p>"
      : "<p>Repita Palabras y El día, y vuelva a intentar.</p>";
    $("#quizScore").textContent = aciertos + " de " + quiz.length + " correctas";
    const nx = $("#quizNext");
    nx.hidden = false;
    nx.textContent = "Otra vez";
  };
  pintarQuiz();

  const modal = $("#modal");
  modal.onclick = (e) => {
    e.stopPropagation();
    const tab = e.target.closest("[data-htab]");
    if (tab) {
      $$("#modal [data-htab]").forEach((x) => x.classList.toggle("on", x === tab));
      $$("#modal [data-hpane]").forEach((p) => p.classList.toggle("on", p.dataset.hpane === tab.dataset.htab));
      if (tab.dataset.htab === "quiz" && !fin && !$("#quizOps").children.length) pintarQuiz();
      return;
    }
    const opt = e.target.closest("#quizOps .quiz-opt");
    if (opt && opt.dataset.qi != null) { responder(+opt.dataset.qi); return; }
    if (e.target.closest("#quizNext")) { avanzarQuiz(); return; }
    if (e.target.closest("#tourPrev")) { if (ti > 0) { ti--; tourBox(); } return; }
    if (e.target.closest("#tourNext")) {
      if (ti < pasos.length - 1) { ti++; tourBox(); }
      else $("#modalBg").classList.remove("show");
      return;
    }
    const gl = e.target.closest("[data-glos]");
    if (gl) { pintarGlos(gl.dataset.glos); return; }
    const sm = e.target.closest("[data-sema]");
    if (sm) { pintarSema(sm.dataset.sema); return; }
    const gh = e.target.closest("[data-gohelp]");
    if (gh) { $("#modalBg").classList.remove("show"); go(gh.dataset.gohelp); return; }
    if (e.target.closest("#closeM")) { $("#modalBg").classList.remove("show"); return; }
  };
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2800);
}

function init() {
  load();
  pullExcel();
  document.addEventListener("click", (e) => {
    if (e.target.closest("#modal")) return;
    const yb = e.target.closest("[data-nav-year]");
    if (yb && yb.dataset.navYear) {
      e.preventDefault();
      if (yb.dataset.navKeep) state.view = yb.dataset.navKeep;
      elegirAnio(yb.dataset.navYear);
      return;
    }
    const nav = e.target.closest("[data-nav]");
    if (nav) { e.preventDefault(); go(nav.dataset.nav); return; }
    const dayEl = e.target.closest("[data-day]");
    if (dayEl && dayEl.dataset.day) { e.preventDefault(); showDay(dayEl.dataset.day); return; }
    const fi = e.target.closest("[data-ficha]");
    if (fi && fi.dataset.ficha) {
      e.preventDefault();
      state.sistema = fi.dataset.ficha;
      go("ficha");
      return;
    }
    const g = e.target.closest("[data-go]");
    if (g && g.dataset.go) {
      e.preventDefault();
      if (g.dataset.board) tableroId = g.dataset.board;
      go(g.dataset.go);
      return;
    }
    if (e.target.closest("#themeBtn")) {
      state.theme = state.theme === "dark" ? "light" : "dark"; save(); render(); return;
    }
    if (e.target.closest("#printBtn")) { window.print(); return; }
    if (e.target.closest("#helpBtn")) { showAyuda(); return; }
  });
  $("#modalBg").addEventListener("click", (e) => { if (e.target.id === "modalBg") e.target.classList.remove("show"); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#modalBg").classList.remove("show"); });
  const qg = $("#qglob");
  if (qg) qg.addEventListener("keydown", (e) => { if (e.key === "Enter") buscarGlobal(qg.value); });
  render();
  const splash = $("#splash");
  const afterSplash = () => {
    if (splash) {
      splash.classList.add("out");
      setTimeout(() => splash.remove(), 700);
    }
  };
  if (splash) setTimeout(afterSplash, 1200);
  else afterSplash();
  arranqueInventario();
}

function arranqueInventario() {
  const recargarSiCambio = (j) => {
    const tot = j && (j.ingesta && j.ingesta.total != null ? j.ingesta.total : j.ultimo_total);
    if (tot == null || Number(tot) === Number(D.total)) return;
    const k = "sentinel-reload-" + tot;
    if (sessionStorage.getItem(k)) return;
    sessionStorage.setItem(k, "1");
    location.reload();
  };
  fetch("/api/fuente/sync").then((r) => r.json()).then(recargarSiCambio).catch(() => {});
  setInterval(() => {
    fetch("/api/fuente").then((r) => r.json()).then(recargarSiCambio).catch(() => {});
  }, 8000);
}
document.addEventListener("DOMContentLoaded", init);
