"""
PREPARAR LA ANIMACIÓN DE LA VENTANA DE ESPERA «EL VIAJE A LA CLÍNICA» (se ejecuta a mano cuando cambia la animación)
===================================================================================================================
La animación llega como una página HTML completa e independiente (con su propia ventana, título, subtítulos de ejemplo, botón «reproducir» y una
imagen del doctor de ~800 KB embebida en el texto). La aplicación necesita solo la ESCENA, liviana y ajustable al ancho:

    python herramientas/preparar_animacion.py  <página de animación .html>

Genera en frontend/viaje/:
  escena.txt   un fragmento (estilos + SVG) que js/viaje.js mete en un «Shadow DOM» (así sus estilos no se mezclan con los de la aplicación)
  doctor.webp  la imagen del doctor, aparte y comprimida

Qué se quita de la página original:
  - lo que no es de la escena: el fondo de la página, el título, la etiqueta, los subtítulos de ejemplo («Personaje tal cual la imagen...»),
    la barra de progreso y el botón de reproducir (la ventana de la aplicación pone su propio título, texto y barra, y los mueve la petición real)
  - todo el CSS y las animaciones que ningún elemento de la escena usa (la página original trae cientos de reglas de otras versiones)
  - los scripts: la página trae el guion de la caminata (que ya está en js/viaje.js, conectado a la petición real) y un script de Cloudflare que
    NO es parte de la animación y que la aplicación nunca debe cargar (su política de seguridad lo bloquea y llamaría a un servidor externo)
Qué se agrega: ajustes para la aplicación (la escena se adapta al ancho que le den, sin ventana ni sombras).
"""

import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image

DESTINO = Path(__file__).resolve().parent.parent / "frontend" / "viaje"
ANCHO_DOCTOR = 324  # px del archivo (la escena lo muestra a ~200 px de ancho de dibujo: 1,6 veces para que se vea nítido en pantallas densas)
# Reglas de la página original que pertenecen a la página y no a la escena
NO_ES_ESCENA = re.compile(
    r"^(body|html|button|\.wrap|\.title-strip|\.badge|\.progress-pill|\.progress|\.caption|\.controls)\b"
)

AJUSTES = """
/* ---- Ajustes para la aplicación ---- */
:host { display: block; }
.animation-window { border-width: 3px; border-radius: 16px; box-shadow: none; }
.stage { height: auto; aspect-ratio: 1040 / 580; }
.stage::before { animation-duration: 1.6s; opacity: .1; }
@media (prefers-reduced-motion: reduce) { * , *::before, *::after { animation: none !important; transition: none !important; } }
"""


def bloques_de_primer_nivel(css: str) -> list[tuple[str, str]]:
    """Parte un CSS en [(selector, bloque completo)], respetando las llaves anidadas (@keyframes, @media)."""
    salida, prof, ini, sel = [], 0, 0, ""
    for k, ch in enumerate(css):
        if ch == "{":
            if prof == 0:
                sel = css[ini:k].strip()
            prof += 1
        elif ch == "}":
            prof -= 1
            if prof == 0:
                salida.append((sel, css[ini : k + 1].strip()))
                ini = k + 1
    return salida


def usa_solo_lo_que_existe(selector: str, existentes: set[str]) -> bool:
    """¿Alguna parte del selector (separadas por comas) solo nombra clases o ids que existen en la escena?"""
    for parte in selector.split(","):
        nombres = re.findall(r"[.#]([A-Za-z0-9_-]+)", parte)
        if all(n in existentes for n in nombres):
            return True
    return False


def preparar(origen: Path) -> None:
    html = origen.read_text(encoding="utf-8")
    # 1) la imagen del doctor: aparte y liviana
    b64 = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html).group(1)
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
    img = img.resize((ANCHO_DOCTOR, round(img.height * ANCHO_DOCTOR / img.width)), Image.LANCZOS)
    DESTINO.mkdir(parents=True, exist_ok=True)
    img.save(DESTINO / "doctor.webp", "WEBP", quality=82, method=6)
    html = html.replace(f"data:image/png;base64,{b64}", "/static/viaje/doctor.webp")
    # 2) el SVG de la escena y sus tres capas de fondo
    svg = re.search(r"<svg viewBox.*?</svg>", html, re.S).group(0)
    capas = '<div class="sunburst" aria-hidden="true"></div>\n        <div class="ground" aria-hidden="true"></div>\n'
    fragmento = f'<div class="animation-window">\n<div class="stage">\n        {capas}\n        {svg}\n</div>\n</div>\n'
    existentes = set(re.findall(r'class="([^"]+)"', fragmento + capas))
    existentes = {c for grupo in existentes for c in grupo.split()} | set(re.findall(r'id="([^"]+)"', fragmento))
    existentes |= {"animation-window", "stage", "sunburst", "ground", "route", "route-back", "route-ink"}
    existentes |= {
        "near",
        "excited",
        "arrived",
        "pop",
        "hide",
        "show",
    }  # las que agrega js/viaje.js mientras corre la animación (no están en el SVG)
    # 3) el CSS: solo lo de la escena, y solo lo que algún elemento usa
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    reglas, keyframes = [], {}
    for sel, bloque in bloques_de_primer_nivel(css):
        if sel.startswith("@keyframes"):
            keyframes[sel.split()[1]] = bloque
        elif sel.startswith("@media"):
            continue  # los @media de la página original son de su propio diseño (se agrega el de «reducir movimiento» más abajo)
        elif sel == ":root":
            reglas.append(bloque.replace(":root", ":host", 1))
        elif sel == "*" or (not NO_ES_ESCENA.match(sel) and usa_solo_lo_que_existe(sel, existentes)):
            reglas.append(bloque)
    texto_css = "\n".join(reglas)
    usadas = [
        b for nombre, b in keyframes.items() if re.search(rf"animation[^;{{}}]*\b{re.escape(nombre)}\b", texto_css)
    ]
    estilos = "<style>\n" + texto_css + "\n" + "\n".join(usadas) + AJUSTES + "</style>\n"
    (DESTINO / "escena.txt").write_text(estilos + fragmento, encoding="utf-8")
    print(
        f"escena.txt: {len(estilos + fragmento) // 1024} KB · {len(reglas)} reglas y {len(usadas)} animaciones (la página traía {len(bloques_de_primer_nivel(css))} bloques)"
    )
    print(f"doctor.webp: {img.size[0]}x{img.size[1]} · {(DESTINO / 'doctor.webp').stat().st_size // 1024} KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    preparar(Path(sys.argv[1]))
