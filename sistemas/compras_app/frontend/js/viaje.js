/*
 * VENTANA DE ESPERA «EL VIAJE A LA CLÍNICA»
 * =========================================
 * Mientras el servidor crea un usuario o restablece una clave (y, si están configurados, envía el correo y el WhatsApp),
 * se muestra una ventana PEQUEÑA con una animación: un doctor corre por un sendero hasta la Clínica Pabón (el edificio despierta y lo saluda). Al llegar, la
 * ventana se cierra sola y aparecen el usuario y la clave temporal.
 *
 * La animación NO tiene una duración fija: va al ritmo de la petición real.
 *   - mientras el servidor trabaja, el doctor avanza cada vez más despacio hacia el 88 % del camino (nunca «llega» antes
 *     de que haya respuesta);
 *   - cuando llega la respuesta, corre el último tramo (0,9 s), la clínica lo saluda y se muestran los datos;
 *   - aunque el servidor responda al instante, dura al menos ~2 s para que se alcance a ver; si tarda más, dura más.
 *   - si la petición FALLA, la ventana se cierra y el error lo muestra quien llamó (el formulario sigue abierto).
 *
 * Uso:   const r = await conViaje(() => api.crearUsuario(datos), { titulo: 'Creando el usuario…', conEnvio: true });
 *
 * La escena (SVG + estilos) está en frontend/viaje/escena.txt (no es una página: es un fragmento; se genera con herramientas/preparar_animacion.py a partir de la animación original) y se mete en un «Shadow DOM»: así sus estilos no se mezclan
 * con los de la aplicación. Con «reducir movimiento» activado en el sistema, no se dibuja la escena: solo el texto y la
 * barra de progreso.
 */
import { $ } from './util.js';

const ESPERA_MIN = 600; // ms: no «llega» antes de este tiempo, aunque la respuesta sea inmediata
const SPRINT = 900; // ms: lo que tarda el último tramo cuando llega la respuesta
const FLORITURA = 650; // ms: la clínica saluda antes de mostrar los datos
const TAU = 1700; // ms: qué tan rápido avanza mientras espera (se acerca al tope sin llegar)
const TOPE = 0.88; // fracción del camino a la que se acerca esperando

let plantilla = null; // el texto de escena.html (se pide una sola vez)
let enCurso = false;

const limitar = (n, a, b) => Math.min(b, Math.max(a, n));
const sale = (x) => 1 - Math.pow(1 - x, 3); // frena al llegar
const esperando = (t) => TOPE * (1 - Math.exp(-t / TAU)); // avance mientras no hay respuesta

/** Pide la escena y la mete en el Shadow DOM. Devuelve las piezas que se mueven, o null si no se pudo (se sigue sin escena). */
async function montarEscena() {
  const host = $('#vj-escena');
  try {
    plantilla ||= await fetch('/static/viaje/escena.txt').then((r) => (r.ok ? r.text() : Promise.reject(new Error(r.status))));
    const raiz = host.shadowRoot || host.attachShadow({ mode: 'open' });
    raiz.innerHTML = plantilla;
    const pieza = (id) => raiz.getElementById(id);
    const e = { ruta: pieza('routePath'), corazon: pieza('heartMascot'), clinica: pieza('clinicPabon'), poof: pieza('poof') };
    return Object.values(e).every(Boolean) ? e : null;
  } catch {
    return null;
  }
}

/** Pone al doctor en el punto `p` (0 a 1) del sendero, con su balanceo de caminata. */
function colocar(e, p) {
  const total = e.ruta.getTotalLength();
  const suave = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
  const largo = total * suave;
  const punto = e.ruta.getPointAtLength(largo);
  const adelante = e.ruta.getPointAtLength(Math.min(total, largo + 7));
  const angulo = (Math.atan2(adelante.y - punto.y, adelante.x - punto.x) * 180) / Math.PI;
  const paso = Math.abs(Math.sin(p * Math.PI * 28));
  const salto = -8 * Math.pow(paso, 1.35);
  const bamboleo = Math.sin(p * Math.PI * 14) * 5.5;
  const lado = Math.sin(p * Math.PI * 14) * 5;
  const pasado = p > 0.965 ? (p - 0.965) * 70 : 0;
  e.corazon.setAttribute(
    'transform',
    `translate(${(punto.x + lado).toFixed(2)} ${(punto.y + salto).toFixed(2)}) rotate(${(angulo * 0.07 + bamboleo + pasado).toFixed(2)}) scale(${(1 + paso * 0.08).toFixed(3)} ${(1 - paso * 0.055).toFixed(3)})`,
  );
  e.poof.setAttribute('transform', `translate(${punto.x.toFixed(2)} ${punto.y.toFixed(2)})`);
}

/** Deja la escena como al principio (para la próxima vez). */
function reiniciar(e) {
  if (!e) return;
  e.corazon.classList.remove('hide', 'pop');
  e.clinica.classList.remove('arrived', 'near', 'excited');
  e.poof.classList.remove('show');
  e.corazon.style.opacity = '1';
  colocar(e, 0);
}

/** El texto que acompaña cada tramo del camino. */
const etapas = (titulo, conEnvio) => [
  { desde: 0, texto: titulo },
  { desde: 0.33, texto: 'Generando la clave temporal…' },
  { desde: 0.66, texto: conEnvio ? 'Enviando el usuario y la clave…' : 'Casi listo…' },
  { desde: 0.86, texto: 'Llegando a la clínica…' },
];

/**
 * Muestra la ventana mientras corre `trabajo()` (una función que devuelve una promesa) y devuelve su resultado cuando el
 * doctor ya llegó. Si `trabajo` falla, cierra la ventana y lanza el mismo error.
 *   titulo   lo que se está haciendo («Creando el usuario…», «Restableciendo la clave…»)
 *   conEnvio ¿el servidor enviará correo o WhatsApp? (cambia el texto del tramo final)
 */
export async function conViaje(trabajo, { titulo = 'Creando el usuario…', conEnvio = false } = {}) {
  if (enCurso) return trabajo(); // por si acaso: nunca dos ventanas a la vez
  enCurso = true;
  const dlg = $('#dlg-viaje');
  const quieto = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const escena = quieto ? null : await montarEscena();
  $('#vj-escena').hidden = !escena;
  $('#vj-titulo').textContent = titulo;
  $('#vj-progreso').style.width = '0%';
  const texto = $('#vj-texto');
  const tramos = etapas(titulo, conEnvio);
  texto.textContent = tramos[0].texto;
  reiniciar(escena);
  const bloquear = (ev) => ev.preventDefault(); // Esc no cierra la ventana mientras el servidor trabaja
  dlg.addEventListener('cancel', bloquear);
  dlg.showModal();

  const inicio = performance.now();
  const espera = quieto ? 0 : ESPERA_MIN;
  const sprint = quieto ? 150 : SPRINT;
  let respuesta = null; // { ok, valor } cuando el servidor contestó
  let tRespuesta = 0;
  Promise.resolve()
    .then(trabajo)
    .then(
      (valor) => { respuesta = { ok: true, valor }; tRespuesta = performance.now() - inicio; },
      (error) => { respuesta = { ok: false, valor: error }; tRespuesta = performance.now() - inicio; },
    );

  const cerrar = () => {
    dlg.removeEventListener('cancel', bloquear);
    if (dlg.open) dlg.close();
    reiniciar(escena);
    enCurso = false;
  };

  return new Promise((resolve, reject) => {
    let llego = false;
    const cuadro = (ahora) => {
      const t = ahora - inicio;
      let p;
      if (!respuesta) {
        p = esperando(t);
      } else if (!respuesta.ok) {
        // Falló: se cierra enseguida (con un respiro mínimo para que la ventana no «parpadee»).
        if (t >= 450) { cerrar(); reject(respuesta.valor); return; }
        p = esperando(t);
      } else {
        const t0 = Math.max(tRespuesta, espera);
        const p0 = esperando(t0);
        p = t < t0 ? esperando(t) : p0 + (1 - p0) * sale(limitar((t - t0) / sprint, 0, 1));
        if (t >= t0 + sprint && !llego) {
          llego = true;
          if (escena) {
            escena.clinica.classList.remove('near', 'excited');
            escena.clinica.classList.add('arrived');
            escena.corazon.classList.add('pop');
            escena.poof.classList.add('show');
            setTimeout(() => escena.corazon.classList.add('hide'), 430);
          }
          texto.textContent = '¡Listo! Aquí están los datos.';
          $('#vj-progreso').style.width = '100%';
          setTimeout(() => { cerrar(); resolve(respuesta.valor); }, quieto ? 250 : FLORITURA);
        }
      }
      if (!llego) {
        if (escena) {
          colocar(escena, p);
          escena.clinica.classList.toggle('near', p > 0.6);
          escena.clinica.classList.toggle('excited', p > 0.82);
        }
        $('#vj-progreso').style.width = `${Math.round(p * 100)}%`;
        const tramo = [...tramos].reverse().find((x) => p >= x.desde);
        if (tramo && texto.textContent !== tramo.texto) texto.textContent = tramo.texto;
        requestAnimationFrame(cuadro);
      }
    };
    requestAnimationFrame(cuadro);
  });
}
