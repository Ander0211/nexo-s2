#!/usr/bin/env python3
"""SENTINEL PABON — HTTP 8080, APIs y vigilante.

Excel: C:\\Users\\Db Developer\\Documents\\SENTINEL
Copias nuevas: \\\\172.168.100.10\\copias
Documentación: DOCUMENTACION.md
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from openpyxl.cell.cell import MergedCell
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote
from http.cookies import SimpleCookie

import openpyxl
import usuarios as cuentas
import notificaciones as aviso

from ingest import build_analytics, extract_records, write_js, fmt_peso, name_clock, pick_sheet, year_blocks
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

ROOT = Path(__file__).resolve().parent
XLSX = ROOT / "assets" / "inventario-backups.xlsx"
XLSX_DRIVE = Path("/home/user/google_drive/INVENTARIO DE BACKUPS DE DATOS SERVIDOR PRINCIPAL.xlsx")
CFG_PATH = ROOT / "config.json"
HOME = Path.home().resolve()
WIN_FUENTE = r"C:\Users\Db Developer\Documents\SENTINEL"
COPIAS_UNC = r"\\172.168.100.10\copias"
COPIAS_UNC_2 = r"\\172.168.10.100"
COPIAS_UNCS = [COPIAS_UNC, COPIAS_UNC_2]
COPIAS_TXT = r"\\172.168.100.10\copias;\\172.168.10.100"
SHEET = "Verificaciones"
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}
LOCK = threading.Lock()
WATCH_STOP = threading.Event()
CICLO_LOCK = threading.Lock()
_COPIAS_STAMP_CACHE = {"t": 0.0, "v": None}

def default_ruta():
    return WIN_FUENTE

def parse_path(raw: str) -> Path:
    s = (raw or "").strip().strip('"').strip("'")
    if not s:
        s = WIN_FUENTE
    s = os.path.expandvars(os.path.expanduser(s))
    if s.startswith("\\\\") or s.startswith("//"):
        if os.name != "nt":
            s = s.replace("\\", "/")
            if not s.startswith("//"):
                s = "//" + s.lstrip("/")
        return Path(s)
    s = s.replace("\\", os.sep).replace("/", os.sep)
    return Path(s)

def _norm(p: Path) -> str:
    try:
        return str(p.resolve()).replace("\\", "/").lower()
    except OSError:
        return str(p).replace("\\", "/").lower()

def ruta_permitida(path: Path) -> bool:
    n = _norm(path)
    home_n = _norm(HOME)
    root_n = _norm(ROOT)
    if n == home_n or n.startswith(home_n + "/") or n == root_n or n.startswith(root_n + "/"):
        return True
    if re.search(r"(^|/)users/[^/]+/documents(/|$)", n):
        return True
    if "documents/sentinel" in n:
        return True
    win_n = WIN_FUENTE.replace("\\", "/").lower()
    if n == win_n or n.startswith(win_n + "/"):
        return True
    if n.startswith("//") or "172.168.100.10" in n or "172.168.10.100" in n or n.rstrip("/").endswith("/copias"):
        return True
    return False

def listar_xlsx(folder: Path) -> list[Path]:
    out = []
    if folder.is_file():
        return [folder] if folder.suffix.lower() in (".xlsx", ".xlsm") else []
    try:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "node_modules"} and not d.startswith(".")]
            rel = os.path.relpath(dirpath, folder)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > 3:
                dirnames.clear()
                continue
            for fn in filenames:
                low = fn.lower()
                if fn.startswith("~$") or low.endswith(".prev.xlsx"):
                    continue
                if low.endswith((".xlsx", ".xlsm")):
                    out.append(Path(dirpath) / fn)
    except OSError:
        pass
    return out

def pick_xlsx(folder: Path) -> Path:
    files = listar_xlsx(folder)
    if not files:
        raise ValueError(f"No hay un .xlsx en {folder}")
    def score(p: Path):
        n = p.name.lower()
        pri = 0
        if "inventario de backups" in n or "servidor principal" in n:
            pri += 50
        if "inventario" in n or "backup" in n or "sentinel" in n or "192.168" in n:
            pri += 20
        if p.parent.name.lower() == "assets" and n == "inventario-backups.xlsx":
            pri -= 40
        try:
            mt = p.stat().st_mtime
            sz = p.stat().st_size
        except OSError:
            mt, sz = 0, 0
        return (pri, mt, sz)
    files.sort(key=score, reverse=True)
    return files[0]

def es_corte_red(e: BaseException) -> bool:
    if isinstance(e, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError)):
        return True
    win = getattr(e, "winerror", None) or getattr(e, "errno", None)
    if win in (10053, 10054, 10060, 64, 59, 1236, 53, 51):
        return True
    s = str(e).lower()
    return "10053" in s or "10054" in s or "anulado una conex" in s


def leer_celda(ws, row, col):
    cell = ws.cell(row, col)
    if isinstance(cell, MergedCell):
        for mr in ws.merged_cells.ranges:
            if cell.coordinate in mr:
                return ws.cell(mr.min_row, mr.min_col).value
        return None
    return cell.value


def escribir_celda(ws, row, col, value):
    coord = ws.cell(row, col).coordinate
    for mr in list(ws.merged_cells.ranges):
        if coord in mr:
            ws.unmerge_cells(str(mr))
            break
    ws.cell(row, col).value = value


def fecha_es(dt: datetime) -> str:
    h = dt.hour
    ap = "a. m." if h < 12 else "p. m."
    h12 = h % 12 or 12
    return (
        f"{DIAS_ES[dt.weekday()]}, {dt.day} de {MESES_ES[dt.month]} de {dt.year}, "
        f"{h12:02d}:{dt.minute:02d} {ap}"
    )

def lista_copias(raw=None) -> list[str]:
    if raw is None:
        raw = CFG.get("copias") if "CFG" in globals() else COPIAS_TXT
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        txt = str(raw or "").strip()
        items = [x.strip() for x in re.split(r"[;\n|]+", txt) if x.strip()] if txt else list(COPIAS_UNCS)
    out = []
    for it in items:
        it = it.replace("/", "\\").strip().strip('"').strip("'")
        if not it.startswith("\\\\"):
            it = "\\\\" + it.lstrip("\\")
        out.append(it.rstrip("\\") if len(it) > 3 else it)
    return list(dict.fromkeys(out)) or list(COPIAS_UNCS)


def copias_txt(raw=None) -> str:
    return ";".join(lista_copias(raw))


def shares_de_host(host: str) -> list[str]:
    if os.name != "nt" or not host:
        return []
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(
            ["net", "view", "\\\\" + host],
            timeout=15, capture_output=True, text=True, errors="replace",
            creationflags=flags,
        )
        skip = {"IPC$", "ADMIN$", "C$", "D$", "E$", "F$", "PRINT$"}
        names = []
        for line in (r.stdout or "").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].lower() == "disk":
                n = parts[0]
                if n.upper() not in skip:
                    names.append(n)
        return names
    except Exception:
        return []


def formas_copias(raw: str) -> list[str]:
    s = (raw or COPIAS_UNC).strip().strip('"').strip("'")
    s = s.replace("/", "\\")
    parts = [p for p in s.split("\\") if p]
    out = []
    if not parts:
        parts = ["172.168.100.10", "copias"]
    host = parts[0]
    if len(parts) == 1:
        shares = ["copias"] + shares_de_host(host)
        for sh in list(dict.fromkeys(shares)):
            unc = "\\\\" + host + "\\" + sh
            out.extend([unc, unc + "\\", unc.replace("\\", "/")])
        return list(dict.fromkeys(out))
    host, share = parts[0], parts[1]
    rest = "\\".join(parts[2:])
    for sh in (share, share.lower(), share.upper(), share.capitalize()):
        unc = "\\\\" + host + "\\" + sh
        if rest:
            unc += "\\" + rest
        out.extend([unc, unc + "\\", unc.replace("\\", "/")])
    return list(dict.fromkeys(out))


def asegurar_sesion_unc(raw: str):
    if os.name != "nt":
        return
    try:
        import subprocess
        tgt = formas_copias(raw)[0]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(["net", "use", tgt], timeout=12, capture_output=True, creationflags=flags)
    except Exception:
        pass


def abrir_copias(raw: str, segundos=25) -> str:
    asegurar_sesion_unc(raw)
    box = {"root": None, "err": None}

    def run():
        last = None
        vistos = []
        prev_map = CFG.get("copias_roots_map") or {}
        prev = prev_map.get(raw)
        for cand in ([prev] if prev else []) + formas_copias(raw):
            if not cand or cand in vistos:
                continue
            vistos.append(cand)
            try:
                os.listdir(cand)
                box["root"] = cand
                return
            except OSError as e:
                last = e
        box["err"] = last

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(segundos)
    if t.is_alive():
        raise TimeoutError(f"La red tarda en abrir {raw}. Se reintenta solo.")
    if box["root"]:
        CFG["copias_ok"] = True
        CFG["copias_root"] = box["root"]
        mp = dict(CFG.get("copias_roots_map") or {})
        mp[raw] = box["root"]
        CFG["copias_roots_map"] = mp
        print("[sentinel] copias en", box["root"])
        return box["root"]
    e = box["err"]
    extra = f" ({e})" if e else ""
    raise ValueError(
        f"No se alcanza {raw}{extra}. "
        "Abra esa ruta en el Explorador de Windows (si pide usuario, inicie sesión) y deje SENTINEL abierto."
    )


def listar_bak(root: Path, desde=None) -> list[dict]:
    out = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if not fn.lower().endswith(".bak") or fn.startswith("~$"):
                    continue
                clock = name_clock(fn)
                if desde and clock and clock.date() < desde:
                    continue
                if desde and not clock:
                    continue
                pth = Path(dirpath) / fn
                if clock and desde:
                    try:
                        st = pth.stat()
                        nbytes = st.st_size
                    except OSError:
                        continue
                    out.append({"path": pth, "name": fn, "dt": clock, "bytes": nbytes})
                elif clock:
                    out.append({"path": pth, "name": fn, "dt": clock, "bytes": 0})
                else:
                    try:
                        st = pth.stat()
                    except OSError:
                        continue
                    out.append({"path": pth, "name": fn, "dt": datetime.fromtimestamp(st.st_mtime), "bytes": st.st_size})
    except OSError:
        return out
    return out

def stamp_copias(raw=None):
    now = time.time()
    if _COPIAS_STAMP_CACHE["v"] is not None and now - _COPIAS_STAMP_CACHE["t"] < 20:
        return _COPIAS_STAMP_CACHE["v"]
    parts = []
    any_ok = False
    errs = []
    for item in lista_copias(raw):
        try:
            root = abrir_copias(item)
            any_ok = True
            n, mx = 0, 0.0
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for fn in filenames:
                    if not fn.lower().endswith(".bak") or fn.startswith("~$"):
                        continue
                    n += 1
                    clock = name_clock(fn)
                    if clock:
                        ts = clock.timestamp()
                        if ts > mx:
                            mx = ts
            parts.append((item, n, mx))
        except Exception as e:
            errs.append(f"{item}: {e}")
            parts.append((item, "err", 0))
    if errs and any_ok:
        CFG["copias_error"] = " · ".join(errs)
    elif errs and not any_ok:
        CFG["copias_error"] = " · ".join(errs)
    else:
        CFG["copias_error"] = None
    val = parts if any_ok else None
    _COPIAS_STAMP_CACHE["t"] = now
    _COPIAS_STAMP_CACHE["v"] = val
    return val

def col_de_anio(ws, year: int) -> int:
    for c in range(1, (ws.max_column or 1) + 1):
        v = leer_celda(ws, 3, c)
        if isinstance(v, str) and re.search(rf"\b{year}\b", v):
            return c
    last = ws.max_column or 0
    c = last + 2 if last else 1
    escribir_celda(ws, 3, c, f"AÑO {year}")
    escribir_celda(ws, 4, c, "FECHA")
    escribir_celda(ws, 4, c + 1, "ARCHIVO")
    escribir_celda(ws, 4, c + 2, "PESO")
    return c

def next_row_block(ws, c0: int) -> int:
    r = 5
    while leer_celda(ws, r, c0 + 1):
        r += 1
    return r

def baks_listos_para_ingestar(baks: list[dict]) -> tuple[list[dict], dict]:
    """Hoy no entra. Mañana: si ya hay 10, entran 10; si siguen 5 (o los que haya), entran esos."""
    hoy = datetime.now().date()
    por_dia: dict = defaultdict(list)
    vistos: dict = defaultdict(set)
    for b in baks:
        d = b["dt"].date()
        k = b["name"].strip().lower()
        if k in vistos[d]:
            continue
        vistos[d].add(k)
        por_dia[d].append(b)
    listos: list[dict] = []
    meta = {"hoy": str(hoy), "omitidos_hoy": 0, "esperando": [], "cerrados": []}
    for d in sorted(por_dia):
        files = sorted(por_dia[d], key=lambda x: x["dt"])
        n = len(files)
        if d >= hoy:
            meta["omitidos_hoy"] += n
            meta["esperando"].append(f"{d} n={n} (hoy: espera mañana)")
            continue
        listos.extend(files)
        if n >= 10:
            meta["cerrados"].append(f"{d} n={n}")
        else:
            meta["cerrados"].append(f"{d} n={n} lo que haya")
    return listos, meta


def merge_copias_into(xlsx: Path, copias_raw=None) -> dict:
    baks = []
    roots = []
    errs = []
    desde = datetime.now().date() - timedelta(days=4)
    for item in lista_copias(copias_raw):
        try:
            root = Path(abrir_copias(item))
            roots.append(str(root))
            baks.extend(listar_bak(root, desde=desde))
        except Exception as e:
            errs.append(f"{item}: {e}")
    if not roots:
        raise ValueError(" · ".join(errs) or "No se alcanza ninguna carpeta de copias")
    listos, regla = baks_listos_para_ingestar(baks)
    CFG["copias_regla"] = regla
    nuevos = []
    with LOCK:
        wb = openpyxl.load_workbook(xlsx)
        hoja = pick_sheet(wb)
        ws = wb[hoja]
        have = set()
        for c0 in year_blocks(ws):
            for r in range(5, (ws.max_row or 0) + 1):
                a = leer_celda(ws, r, c0 + 1)
                if isinstance(a, str) and a.strip():
                    have.add(a.strip().lower())
        for b in listos:
            key = b["name"].strip().lower()
            if key in have:
                continue
            c0 = col_de_anio(ws, b["dt"].year)
            r = next_row_block(ws, c0)
            gb = b["bytes"] / (1024 ** 3)
            escribir_celda(ws, r, c0, fecha_es(b["dt"]))
            escribir_celda(ws, r, c0 + 1, b["name"])
            escribir_celda(ws, r, c0 + 2, fmt_peso(gb))
            have.add(key)
            nuevos.append(b["name"])
        if nuevos:
            wb.save(xlsx)
    CFG["copias_ok"] = True
    CFG["copias_nuevos"] = len(nuevos)
    CFG["copias_vistos"] = len(baks)
    if errs:
        CFG["copias_error"] = " · ".join(errs)
    else:
        CFG["copias_error"] = None
    print("[sentinel] regla días", regla, "rutas", roots)
    return {"nuevos": len(nuevos), "nombres": nuevos[:30], "vistos": len(baks), "regla": regla, "roots": roots, "errores": errs}

def excel_trabajo(raw: str) -> Path:
    vistos = []
    for cand in (raw, WIN_FUENTE, str(ROOT), str(ROOT.parent)):
        if not cand or cand in vistos:
            continue
        vistos.append(cand)
        p = parse_path(cand)
        try:
            if not p.exists():
                continue
            if p.is_file() and p.suffix.lower() in (".xlsx", ".xlsm"):
                return p
            if p.is_dir() and listar_xlsx(p):
                return pick_xlsx(p)
        except OSError:
            continue
    if XLSX.exists():
        return XLSX
    raise ValueError(f"No hay Excel de inventario en {raw}")

def resolve_excel(raw: str) -> Path:
    path = parse_path(raw)
    if not ruta_permitida(path):
        raise ValueError("La ruta debe ser la carpeta SENTINEL de Documentos o un Excel de este usuario.")
    if not path.exists():
        raise ValueError(
            f"No se ve la carpeta en este equipo: {path}. "
            "SENTINEL PABON debe correr en el PC Db Developer, con el Excel en "
            r"C:\Users\Db Developer\Documents\SENTINEL"
        )
    if path.is_dir():
        path = pick_xlsx(path)
    elif path.is_file():
        if path.suffix.lower() not in (".xlsx", ".xlsm"):
            raise ValueError("Solo se acepta Excel .xlsx")
    else:
        raise ValueError(f"No existe: {path}")
    return path

def source_stamp(raw: str):
    path = parse_path(raw)
    if not path.exists():
        return None
    if path.is_dir():
        files = listar_xlsx(path)
        if not files:
            return None
        parts = []
        for f in files:
            try:
                st = f.stat()
                parts.append((f.name, st.st_mtime, st.st_size))
            except OSError:
                continue
        return tuple(sorted(parts))
    try:
        st = path.stat()
        return (path.name, st.st_mtime, st.st_size)
    except OSError:
        return None

def load_cfg():
    base = {
        "ruta": default_ruta(),
        "intervalo": 30,
        "activo": True,
        "mtime": None,
        "ultimo_sync": None,
        "ultimo_error": None,
        "ultimo_total": None,
        "ultimo_hasta": None,
        "archivo_usado": None,
        "copias": COPIAS_TXT,
        "copias_activo": True,
        "copias_stamp": None,
        "copias_error": None,
        "copias_nuevos": None,
        "copias_vistos": None,
    }
    if CFG_PATH.exists():
        try:
            base.update(json.loads(CFG_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return base

CFG = load_cfg()

def save_cfg():
    CFG_PATH.write_text(json.dumps(CFG, ensure_ascii=False, indent=2), encoding="utf-8")

def safe_excel_path(raw: str) -> Path:
    return resolve_excel(raw)

HEADERS = [
    "Marca temporal",
    "Fecha de verificación",
    "Sistema / Carpeta",
    "Ubicación",
    "Tipo de Backup",
    "Resultado",
    "Observaciones",
    "Operador",
    "Tamaño observado",
    "Duración (min)",
    "Hash / VERIFYONLY",
    "Segunda copia",
    "Restore de prueba",
    "Coincide con inventario",
    "Último .bak (inventario)",
    "Fecha último .bak",
    "Hora último .bak",
    "Peso último .bak",
]


def _style_header(ws):
    fill = PatternFill("solid", fgColor="0B2748")
    font = Font(color="FFFFFF", bold=True, name="Calibri", size=10)
    thin = Border(
        left=Side(style="thin", color="D5E0EE"),
        right=Side(style="thin", color="D5E0EE"),
        bottom=Side(style="thin", color="D5E0EE"),
        top=Side(style="thin", color="D5E0EE"),
    )
    for col, h in enumerate(HEADERS, 1):
        cell = ws.cell(1, col, h)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = thin
    ws.freeze_panes = "A2"
    widths = [20, 18, 22, 20, 14, 26, 36, 18, 16, 14, 22, 18, 16, 22, 42, 16, 14, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w


def ensure_sheet(wb):
    if SHEET not in wb.sheetnames:
        ws = wb.create_sheet(SHEET)
        _style_header(ws)
    else:
        ws = wb[SHEET]
        if ws.cell(1, 1).value != HEADERS[0]:
            ws.insert_rows(1)
            _style_header(ws)
    return ws


def row_to_dict(values):
    d = {}
    for i, h in enumerate(HEADERS):
        d[h] = values[i] if i < len(values) else ""
    return {
        "id": str(d.get("Marca temporal") or ""),
        "fecha": str(d.get("Fecha de verificación") or ""),
        "sistema": str(d.get("Sistema / Carpeta") or ""),
        "ubicacion": str(d.get("Ubicación") or ""),
        "tipo": str(d.get("Tipo de Backup") or ""),
        "resultado": str(d.get("Resultado") or ""),
        "observaciones": str(d.get("Observaciones") or ""),
        "operador": str(d.get("Operador") or ""),
        "tamano": str(d.get("Tamaño observado") or ""),
        "duracion": str(d.get("Duración (min)") or ""),
        "hash": str(d.get("Hash / VERIFYONLY") or ""),
        "segunda": str(d.get("Segunda copia") or ""),
        "restore": str(d.get("Restore de prueba") or ""),
        "coincide": str(d.get("Coincide con inventario") or ""),
        "ultimoBak": str(d.get("Último .bak (inventario)") or ""),
        "fechaBak": str(d.get("Fecha último .bak") or ""),
        "horaBak": str(d.get("Hora último .bak") or ""),
        "pesoBak": str(d.get("Peso último .bak") or ""),
    }


def read_all():
    if not XLSX.exists():
        return []
    with LOCK:
        wb = openpyxl.load_workbook(XLSX, data_only=True)
        if SHEET not in wb.sheetnames:
            return []
        ws = wb[SHEET]
        out = []
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            if not any(row):
                continue
            rec = row_to_dict(list(row))
            rec["id"] = rec["id"] or f"row-{i}"
            out.append(rec)
        out.reverse()
        return out


def ya_hay_dia(fecha: str) -> bool:
    f = (fecha or "").strip()
    if not f:
        return False
    for rec in read_all():
        if str(rec.get("sistema") or "").strip().upper() != "DIA":
            continue
        if str(rec.get("fecha") or "").strip() == f:
            return True
        if str(rec.get("fechaBak") or "").strip() == f:
            return True
    return False


def append_one(payload: dict) -> dict:
    XLSX.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    values = [
        stamp,
        payload.get("fecha") or "",
        payload.get("sistema") or "",
        payload.get("ubicacion") or "",
        payload.get("tipo") or "",
        payload.get("resultado") or "",
        payload.get("observaciones") or "",
        payload.get("operador") or "",
        payload.get("tamano") or "",
        payload.get("duracion") or "",
        payload.get("hash") or "",
        payload.get("segunda") or "",
        payload.get("restore") or "",
        payload.get("coincide") or "",
        payload.get("ultimoBak") or "",
        payload.get("fechaBak") or "",
        payload.get("horaBak") or "",
        payload.get("pesoBak") or "",
    ]
    with LOCK:
        wb = openpyxl.load_workbook(XLSX)
        ws = ensure_sheet(wb)
        ws.append(values)
        wb.save(XLSX)
    try:
        if XLSX_DRIVE.parent.exists():
            shutil.copy2(XLSX, XLSX_DRIVE)
    except OSError:
        pass
    rec = row_to_dict(values)
    rec["id"] = stamp
    rec["archivo"] = str(XLSX)
    return rec


def parse_multipart_file(headers, body: bytes):
    ctype = headers.get("Content-Type") or ""
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', ctype)
    if not m:
        raise ValueError("La subida no es multipart (falta boundary).")
    boundary = (m.group(1) or m.group(2)).strip().encode()
    for part in body.split(b"--" + boundary):
        if b"filename=" not in part:
            continue
        head, sep, content = part.partition(b"\r\n\r\n")
        if not sep:
            head, sep, content = part.partition(b"\n\n")
        content = content.rstrip(b"\r\n")
        if content.endswith(b"--"):
            content = content[:-2]
        hm = re.search(br'filename="([^"]*)"', head)
        name = hm.group(1).decode("utf-8", "replace") if hm else "inventario.xlsx"
        return name, content
    raise ValueError("No vino ningún archivo.")


def copy_sheet(src_ws, dst_wb, title):
    if title in dst_wb.sheetnames:
        del dst_wb[title]
    dst = dst_wb.create_sheet(title)
    for row in src_ws.iter_rows():
        for cell in row:
            dst.cell(cell.row, cell.column, cell.value)


def apply_source(src: Path) -> dict:
    data, sheets = extract_records(src)
    if data["total"] < 1:
        raise ValueError("No se encontraron .bak (FECHA / ARCHIVO / PESO).")
    prev = ROOT / "assets" / "inventario-backups.prev.xlsx"
    with LOCK:
        src_res = src.resolve()
        xlsx_res = XLSX.resolve() if XLSX.exists() else XLSX
        if XLSX.exists() and src_res != xlsx_res:
            shutil.copy2(XLSX, prev)
            shutil.copy2(src, XLSX)
        elif XLSX.exists():
            shutil.copy2(XLSX, prev)
        elif src_res != xlsx_res:
            shutil.copy2(src, XLSX)
        wb = openpyxl.load_workbook(XLSX)
        if SHEET not in wb.sheetnames and prev.exists():
            old = openpyxl.load_workbook(prev)
            if SHEET in old.sheetnames:
                copy_sheet(old[SHEET], wb, SHEET)
        ensure_sheet(wb)
        wb.save(XLSX)
        analytics = build_analytics(data)
        write_js(ROOT, data, analytics)
    CFG["ultimo_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CFG["ultimo_error"] = None
    CFG["ultimo_total"] = data["total"]
    CFG["ultimo_hasta"] = data["hasta"]
    CFG["archivo_usado"] = src.name
    CFG["mtime"] = source_stamp(CFG.get("ruta") or str(src))
    save_cfg()
    return {
        "ok": True,
        "nombre": src.name,
        "ruta": str(src),
        "total": data["total"],
        "hoja": data["hoja"],
        "desde": data["desde"],
        "hasta": data["hasta"],
        "sistemas": data["sistemas"],
        "pesoTotalGB": data["pesoTotalGB"],
        "hojas": sheets,
        "archivo": XLSX.name,
        "sync": CFG["ultimo_sync"],
    }


def ingest_upload(headers, body: bytes) -> dict:
    name, content = parse_multipart_file(headers, body)
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise ValueError("Solo se acepta .xlsx (Excel).")
    if len(content) < 100:
        raise ValueError("El archivo está vacío.")
    tmp = ROOT / "assets" / "_upload.xlsx"
    tmp.write_bytes(content)
    try:
        info = apply_source(tmp)
        info["nombre"] = name
        return info
    finally:
        tmp.unlink(missing_ok=True)


def fuente_estado():
    ruta = CFG.get("ruta") or default_ruta()
    p = parse_path(ruta)
    existe = p.exists()
    mtime = None
    tam = None
    es_carpeta = bool(existe and p.is_dir())
    archivo = CFG.get("archivo_usado")
    xlsx_nombres = []
    nota = None
    if existe and p.is_dir():
        files = listar_xlsx(p)
        xlsx_nombres = [f.name for f in files]
        try:
            chosen = pick_xlsx(p)
            archivo = chosen.name
            st = chosen.stat()
            mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            tam = st.st_size
        except (ValueError, OSError):
            pass
    elif existe and p.is_file():
        st = p.stat()
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        tam = st.st_size
        archivo = p.name
    elif not existe:
        nota = (
            "Esta carpeta está en el PC Windows (Db Developer). "
            "Al abrir SENTINEL PABON ahí, leerá C:\\Users\\Db Developer\\Documents\\SENTINEL "
            "y las copias en \\\\172.168.100.10\\copias y \\\\172.168.10.100"
        )
    copias = copias_txt()
    roots = list((CFG.get("copias_roots_map") or {}).values())
    copias_ok = bool(roots) or bool(CFG.get("copias_ok"))
    return {
        "ok": True,
        "ruta": ruta,
        "activo": bool(CFG.get("activo")),
        "intervalo": int(CFG.get("intervalo") or 30),
        "existe": existe,
        "carpeta": es_carpeta,
        "archivo_usado": archivo,
        "xlsx": xlsx_nombres,
        "mtime_archivo": mtime,
        "bytes": tam,
        "ultimo_sync": CFG.get("ultimo_sync"),
        "ultimo_error": CFG.get("ultimo_error"),
        "ultimo_total": CFG.get("ultimo_total"),
        "ultimo_hasta": CFG.get("ultimo_hasta"),
        "nota": nota,
        "copias": copias,
        "copias_lista": lista_copias(),
        "copias_activo": bool(CFG.get("copias_activo", True)),
        "copias_existe": copias_ok,
        "copias_roots": roots,
        "copias_error": CFG.get("copias_error"),
        "copias_nuevos": CFG.get("copias_nuevos"),
        "copias_vistos": CFG.get("copias_vistos"),
    }


def ciclo_auto(forzar=False):
    raw = CFG.get("ruta") or default_ruta()
    cop = copias_txt()
    merged = 0
    if CFG.get("copias_activo", True):
        try:
            stc = stamp_copias(cop)
            if stc is None:
                CFG["copias_error"] = f"Aún no responde {cop}"
            elif forzar or CFG.get("copias_stamp") != stc:
                xlsx = excel_trabajo(raw)
                info = merge_copias_into(xlsx, cop)
                CFG["copias_stamp"] = stc
                _COPIAS_STAMP_CACHE["v"] = stc
                _COPIAS_STAMP_CACHE["t"] = time.time()
                merged = info["nuevos"]
                print("[sentinel] copias", info["vistos"], "vistos · nuevos", merged)
        except TimeoutError as e:
            CFG["copias_error"] = str(e)
            print("[sentinel] copias espera", e)
            save_cfg()
        except Exception as e:
            if es_corte_red(e):
                CFG["copias_error"] = "La red cortó la carpeta de copias. Se reintenta solo."
            else:
                CFG["copias_error"] = str(e)
            print("[sentinel] copias error", e)
            save_cfg()
    stamp = source_stamp(raw)
    src = None
    try:
        src = excel_trabajo(raw)
    except OSError as e:
        if es_corte_red(e):
            print("[sentinel] corte de red al leer Excel", e)
            return None
        raise
    except ValueError:
        src = XLSX if XLSX.exists() else None
    if src is None:
        CFG["ultimo_error"] = f"No hay .xlsx en {raw}"
        save_cfg()
        return None
    if merged or CFG.get("mtime") != stamp:
        try:
            info = apply_source(src)
        except OSError as e:
            if es_corte_red(e):
                print("[sentinel] corte de red al guardar", e)
                return None
            raise
        print("[sentinel] auto-sync", src, CFG.get("ultimo_total"))
        return info
    save_cfg()
    return None

def kick_ciclo(forzar=False) -> bool:
    if not CICLO_LOCK.acquire(blocking=False):
        return False
    def run():
        try:
            ciclo_auto(forzar)
        except Exception as e:
            print("[sentinel] ciclo", e)
        finally:
            CICLO_LOCK.release()
    threading.Thread(target=run, name="ciclo-auto", daemon=True).start()
    return True

def watch_loop():
    while True:
        if CFG.get("activo"):
            if CICLO_LOCK.acquire(blocking=False):
                try:
                    ciclo_auto(False)
                except Exception as e:
                    if es_corte_red(e):
                        print("[sentinel] watch red", e)
                    else:
                        CFG["ultimo_error"] = str(e)
                        save_cfg()
                        print("[sentinel] watch error", e)
                finally:
                    CICLO_LOCK.release()
        if WATCH_STOP.wait(timeout=max(5, int(CFG.get("intervalo") or 30))):
            break


PORT = 8080


def ip_de_red():
    """La IP de este PC en la red local (la que usan los celulares y otros equipos para entrar)."""
    import socket
    for destino in ("10.255.255.255", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect((destino, 1))  # no envía nada: solo pregunta por qué tarjeta de red saldría
                ip = s.getsockname()[0]
            finally:
                s.close()
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return "localhost"


class Handler(SimpleHTTPRequestHandler):
    # ---------------- usuarios y permisos (administrador / revisor) ----------------
    PUBLICOS = {"/login.html", "/js/login.js", "/js/nexo.js", "/js/ojo.js"}
    EXT_OK = {".html", ".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".woff2", ".woff", ".ttf"}

    def _token(self):
        try:
            c = SimpleCookie(self.headers.get("Cookie") or "")
            return c[cuentas.COOKIE].value if cuentas.COOKIE in c else None
        except Exception:
            return None

    def _usuario(self):
        return cuentas.usuario_de(self._token())

    def _es_local(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _origen_ok(self):
        origen = self.headers.get("Origin")
        if not origen or origen == "null":
            return True
        return urlparse(origen).netloc == (self.headers.get("Host") or "")

    def _enlace_ingreso(self, usuario):
        """Dirección que va en el correo/WhatsApp. Abre la pantalla de ingreso de SENTINEL con el usuario ya escrito
        (?ingresar=1 cierra cualquier sesión que hubiera en ese navegador). Si el administrador entró como «localhost»,
        se cambia por la IP de este PC en la red, porque «localhost» en el celular de otra persona no lleva a SENTINEL."""
        base = aviso.url_publica()
        if not base:
            host = self.headers.get("Host") or f"localhost:{PORT}"
            nombre, _, puerto = host.rpartition(":") if host.count(":") == 1 else (host, "", "")
            if not nombre:
                nombre, puerto = host, ""
            if nombre.strip("[]") in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                nombre = ip_de_red()
            base = f"http://{nombre}:{puerto or PORT}"
        return base.rstrip("/") + "/login.html?ingresar=1&usuario=" + quote(usuario)

    def _redirigir(self, destino):
        self.send_response(302)
        self.send_header("Location", destino)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _servir_index(self, u):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        ses = json.dumps({"usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"], "superusuario": u.get("superusuario", False)}, ensure_ascii=True).replace("<", "\\u003c")
        html = html.replace("</head>", f"  <script>window.SENTINEL_SESION = {ses};</script>\n</head>", 1)
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _gate_get(self, path):
        """True si la petición ya quedó respondida (redirigida, negada o atendida aquí)."""
        if path == "/api/salud":
            self._json(200, {"ok": True, "app": "sentinel"})
            return True
        if path == "/api/sesion":
            u = self._usuario()
            self._json(200, {"ok": True, "configurado": cuentas.configurado(), "autenticado": bool(u),
                             "local": self._es_local(), **(u or {})})
            return True
        u = self._usuario()
        if u and u.get("debe_cambiar") and (path in ("/", "/index.html", "/usuarios.html") or path.startswith("/api/")):
            # Clave temporal: antes de ver cualquier cosa debe elegir su propia clave
            if path.startswith("/api/"):
                self._json(403, {"ok": False, "error": "Primero debe cambiar su clave temporal.", "debe_cambiar": True})
            else:
                self._redirigir("/login.html?cambiar=1")
            return True
        if path in ("/", "/index.html"):
            if not u:
                q = urlparse(self.path).query
                self._redirigir("/login.html" + ("?" + q if q else ""))
            else:
                self._servir_index(u)
            return True
        if path in self.PUBLICOS:
            if path == "/login.html" and u and not u.get("debe_cambiar") and "ingresar=1" not in urlparse(self.path).query:
                self._redirigir("/")
                return True
            return False
        ext = os.path.splitext(path)[1].lower()
        if path.startswith("/css/") or (path.startswith("/assets/") and ext in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico"}):
            return False  # estilos e imágenes: necesarios también en la pantalla de ingreso
        if path.startswith("/api/"):
            if not u:
                self._json(401, {"ok": False, "error": "Debe iniciar sesión.", "sesion": False})
                return True
            if path == "/api/usuarios":
                if u["rol"] != "administrador":
                    self._json(403, {"ok": False, "error": "Solo un administrador gestiona usuarios."})
                else:
                    self._json(200, {"ok": True, "usuarios": cuentas.listar(), "canales": aviso.canales()})
                return True
            return False
        # Archivos: solo con sesión, y nunca datos/, .py, .json de configuración, Excel ni documentos internos
        permitido = ext in self.EXT_OK or path == "/assets/rips-sample.json"
        if path.startswith("/datos/") or not permitido:
            self.send_error(404)
            return True
        if not u:
            if ext == ".html":
                self._redirigir("/login.html")
            else:
                self.send_error(401)
            return True
        return False

    def _gate_post(self, path, raw):
        """Ingreso, salida, cuentas y permisos. True si ya respondió."""
        if not self._origen_ok():
            self._json(403, {"ok": False, "error": "Origen no permitido."})
            return True
        def cuerpo():
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                return {}
        try:
            if path == "/api/login":
                b = cuerpo()
                token, u = cuentas.iniciar_sesion(b.get("usuario"), b.get("clave"))
                data = json.dumps({"ok": True, **u}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie", f"{cuentas.COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={cuentas.DURACION_SESION}")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return True
            if path == "/api/logout":
                cuentas.cerrar_sesion(self._token())
                data = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", f"{cuentas.COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return True
            if path == "/api/primer-admin":
                if not self._es_local():
                    raise cuentas.ErrorUsuario("La primera cuenta de administrador solo se crea desde el PC donde corre SENTINEL.", 403)
                b = cuerpo()
                u = cuentas.crear_primer_admin(b.get("usuario"), b.get("nombre"), b.get("clave"), b.get("correo"), b.get("celular"))
                self._json(200, {"ok": True, **u})
                return True
            u = self._usuario()
            if not u:
                self._json(401, {"ok": False, "error": "Su sesión terminó. Vuelva a ingresar.", "sesion": False})
                return True
            if u.get("debe_cambiar") and path != "/api/mi-clave":
                raise cuentas.ErrorUsuario("Primero debe cambiar su clave temporal.", 403)
            if path == "/api/mi-clave":
                b = cuerpo()
                cuentas.cambiar_mi_clave(u["usuario"], b.get("actual"), b.get("nueva"))
                self._json(200, {"ok": True})
                return True
            if path == "/api/usuarios":
                if u["rol"] != "administrador":
                    raise cuentas.ErrorUsuario("Solo un administrador gestiona usuarios.", 403)
                b = cuerpo()
                if b.get("accion") in ("crear", "clave"):
                    if b.get("accion") == "crear":
                        nuevo, clave = cuentas.crear(u["usuario"], b)
                    else:
                        nuevo, clave = cuentas.restablecer(u["usuario"], b.get("usuario"))
                    url = self._enlace_ingreso(nuevo["usuario"])
                    envio = aviso.enviar_credenciales(nuevo, clave, url, restablecida=b.get("accion") == "clave")
                    self._json(200, {"ok": True, "usuarios": cuentas.listar(), "usuario": nuevo,
                                     "clave_temporal": clave, "envio": envio})
                    return True
                self._json(200, {"ok": True, "usuarios": cuentas.gestionar(u["usuario"], b)})
                return True
            # Cargar inventario, cambiar la fuente y verificar (ENVIAR): solo administrador
            if path.rstrip("/") in ("/api/excel-upload", "/api/fuente", "/api/verificar"):
                if u["rol"] != "administrador":
                    raise cuentas.ErrorUsuario("Su usuario es Revisor: puede consultar, pero el cargue y la verificación de copias los hace un administrador.", 403)
                accion = {"/api/excel-upload": "cargó inventario", "/api/fuente": "cambió la fuente",
                          "/api/verificar": "verificó (ENVIAR)"}[path.rstrip("/")]
                detalle = ""
                if path.rstrip("/") == "/api/verificar":
                    b = cuerpo()
                    items = b if isinstance(b, list) else [b]
                    detalle = ", ".join(f"{(i or {}).get('sistema','')} {(i or {}).get('fecha','')} {(i or {}).get('resultado','')}".strip() for i in items)[:300]
                cuentas.auditar(u["usuario"], accion, detalle)
            return False
        except cuentas.ErrorUsuario as e:
            self._json(e.codigo, {"ok": False, "error": e.mensaje})
            return True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except OSError as e:
            if es_corte_red(e):
                return
            raise

    def do_GET(self):
        path = urlparse(self.path).path
        if self._gate_get(path):
            return
        if path == "/api/verificaciones":
            self._json(200, {"ok": True, "verificaciones": read_all(), "archivo": str(XLSX.name)})
            return
        if path == "/api/fuente":
            self._json(200, fuente_estado())
            return
        if path.rstrip("/") == "/api/fuente/sync":
            en_curso = not kick_ciclo(False)
            st = fuente_estado()
            st["en_curso"] = True if en_curso or CICLO_LOCK.locked() else False
            self._json(200, st)
            return
        if path == "/api/excel":
            raw = XLSX.read_bytes() if XLSX.exists() else b""
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="inventario-backups.xlsx"')
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        return super().do_GET()

    def do_HEAD(self):
        self.send_error(405)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if self._gate_post(path, raw):
            return
        if path == "/api/excel-upload":
            try:
                info = ingest_upload(self.headers, raw)
                self._json(200, info)
            except Exception as e:
                self._json(400, {"ok": False, "error": str(e)})
            return
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "JSON inválido"})
            return
        if path == "/api/fuente":
            try:
                if "ruta" in payload:
                    raw = str(payload.get("ruta") or "").strip() or WIN_FUENTE
                    p = parse_path(raw)
                    if not ruta_permitida(p):
                        raise ValueError("La ruta debe ser Documentos\\SENTINEL o un Excel de este usuario.")
                    CFG["ruta"] = raw
                    CFG["mtime"] = None
                if "intervalo" in payload:
                    CFG["intervalo"] = max(10, min(3600, int(payload["intervalo"])))
                if "activo" in payload:
                    CFG["activo"] = bool(payload["activo"])
                if "copias" in payload:
                    rawc = str(payload.get("copias") or "").strip() or COPIAS_TXT
                    CFG["copias"] = copias_txt(rawc)
                    CFG["copias_stamp"] = None
                if "copias_activo" in payload:
                    CFG["copias_activo"] = bool(payload["copias_activo"])
                save_cfg()
                if payload.get("sync"):
                    info = ciclo_auto(True)
                    st = fuente_estado()
                    if info:
                        st["ingesta"] = info
                    self._json(200, st)
                    return
                self._json(200, fuente_estado())
            except Exception as e:
                CFG["ultimo_error"] = str(e)
                save_cfg()
                self._json(400, {"ok": False, "error": str(e), **fuente_estado()})
            return
        if path == "/api/fuente/sync":
            en_curso = not kick_ciclo(False)
            st = fuente_estado()
            st["en_curso"] = True if en_curso or CICLO_LOCK.locked() else False
            self._json(200, st)
            return
        if path.rstrip("/") == "/api/verificar":
            try:
                items = payload if isinstance(payload, list) else [payload]
                for p in items:
                    sis = str((p or {}).get("sistema") or "").strip().upper()
                    if sis == "DIA":
                        f = str((p or {}).get("fecha") or "").strip()
                        fb = str((p or {}).get("fechaBak") or "").strip()
                        if ya_hay_dia(f) or ya_hay_dia(fb):
                            raise ValueError("Este día ya fue enviado. No se permite ENVIAR otra vez.")
                recs = [append_one(p) for p in items]
                self._json(200, {
                    "ok": True,
                    "guardado": recs,
                    "verificaciones": read_all(),
                    "archivo": XLSX.name,
                    "hoja": SHEET,
                })
            except Exception as e:
                self._json(400, {"ok": False, "error": str(e)})
            return
        self._json(404, {"ok": False, "error": "ruta desconocida"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        print("[sentinel]", self.address_string(), fmt % args)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except OSError as e:
            if es_corte_red(e):
                return
            raise


def preparar_superusuario():
    """Lee SENTINEL_SUPERUSUARIO y SENTINEL_SUPERUSUARIO_CLAVE (variables o sentinel/.env; si no están, los de SUMIPABON:
    COMPRAS_SUPERUSUARIO y COMPRAS_SUPERUSUARIO_CLAVE) y deja listo al superusuario. Nunca muestra la clave."""
    usuario, clave = aviso.superusuario_configurado()
    try:
        r = cuentas.asegurar_superusuario(usuario, clave)
    except cuentas.ErrorUsuario as e:
        print(f"[sentinel] ATENCIÓN: no se pudo preparar el superusuario: {e.mensaje}")
        return
    if r:
        print(f"[sentinel] Superusuario «{usuario.strip().lower()}» {r} (con la clave definida en .env).")


def main():
    preparar_superusuario()
    t = threading.Thread(target=watch_loop, name="excel-watch", daemon=True)
    t.start()
    httpd = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    print("[sentinel] LISTO  http://localhost:8080")
    print("[sentinel] el Excel y las copias se leen en segundo plano")
    try:
        import webbrowser
        threading.Timer(0.3, lambda: webbrowser.open("http://localhost:8080")).start()
    except Exception:
        pass
    httpd.serve_forever()


if __name__ == "__main__":
    main()
