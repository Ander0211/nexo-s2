#!/usr/bin/env python3
"""Parsea el inventario .xlsx (AÑO / FECHA / ARCHIVO / PESO) → js/data.js y js/analytics.js.

No inventa Resultado ni RTO. Ver DOCUMENTACION.md.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MES_NOMBRES = set(MESES) | {m.upper() for m in MESES}


def fmt_peso(gb: float) -> str:
    if gb >= 1024:
        return f"{gb / 1024:.2f} TB"
    if gb >= 1:
        return f"{gb:.2f} GB"
    return f"{gb * 1024:.2f} MB"


def parse_peso(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".").replace("\xa0", " ")
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(TB|GB|MB|KB)?", s, re.I)
    if not m:
        return 0.0
    n = float(m.group(1))
    u = (m.group(2) or "GB").upper()
    return n * 1024 if u == "TB" else n / 1024 if u == "MB" else n / (1024 * 1024) if u == "KB" else n


def parse_fecha(v):
    if v is None:
        return None, None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d"), v.strftime("%H:%M")
    s = str(v).strip().lower().replace("\xa0", " ")
    if s in MES_NOMBRES or s.startswith("año") or s in ("fecha", "archivo", "peso"):
        return None, None
    m = re.search(
        r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4}).*?(\d{1,2}):(\d{2})\s*(a\.?\s*m\.?|p\.?\s*m\.?)?",
        s,
        re.I,
    )
    if m:
        d, mes, y, hh, mm, ap = m.groups()
        mo = MESES.get(mes.lower().replace("é", "e").replace("á", "a"))
        if not mo:
            return None, None
        h = int(hh)
        if ap:
            apn = ap.lower().replace(" ", "").replace(".", "")
            if apn.startswith("p") and h < 12:
                h += 12
            if apn.startswith("a") and h == 12:
                h = 0
        return f"{int(y):04d}-{mo:02d}-{int(d):02d}", f"{h:02d}:{int(mm):02d}"
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?", str(v))
    if m:
        y, mo, d, hh, mm = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}", f"{int(hh or 0):02d}:{int(mm or 0):02d}"
    return None, None


def sistema_de(nombre: str) -> str:
    n = str(nombre or "")
    return n.split("_")[0].replace(".bak", "").strip() or "DESCONOCIDO"


def name_clock(nombre: str):
    n = str(nombre or "")
    m = re.search(r"_(\d{4})_(\d{2})_(\d{2})_(\d{2})(\d{2})", n)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
    m = re.search(r"_(\d{4})-(\d{1,2})-(\d{1,2})_(\d{1,4})(?:\.bak)?$", n, re.I)
    if m:
        raw = m.group(4)
        if len(raw) <= 2:
            h, mi = int(raw), 0
        elif len(raw) == 3:
            h, mi = int(raw[0]), int(raw[1:])
        else:
            h, mi = int(raw[:2]), int(raw[2:])
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), h % 24, mi % 60)
        except ValueError:
            return None
    return None


def pick_sheet(wb):
    names = list(wb.sheetnames)
    for prefer in ("192.168.200.50", "01-30"):
        if prefer in names:
            return prefer
    best, nbest = None, -1
    for name in names:
        if name.lower() in ("resumen", "verificaciones"):
            continue
        ws = wb[name]
        n = 0
        for row in ws.iter_rows(min_row=1, max_col=min(ws.max_column or 1, 40), values_only=True):
            for v in row:
                if isinstance(v, str) and ".bak" in v.lower():
                    n += 1
        if n > nbest:
            best, nbest = name, n
    return best or names[0]


def es_mes_fila(v) -> bool:
    if not isinstance(v, str):
        return False
    return v.strip().lower() in MESES


def parse_sheet_records(ws, hoja: str) -> list[dict]:
    blocks = year_blocks(ws)
    recs = []
    seen = set()
    for c0 in blocks:
        for r in range(5, (ws.max_row or 0) + 1):
            fecha_v = ws.cell(r, c0).value
            arch = ws.cell(r, c0 + 1).value
            peso_v = ws.cell(r, c0 + 2).value
            if es_mes_fila(fecha_v):
                continue
            if not arch or not isinstance(arch, str) or ".bak" not in arch.lower():
                continue
            f, h = parse_fecha(fecha_v)
            if not f:
                clock = name_clock(arch)
                if clock:
                    f, h = clock.strftime("%Y-%m-%d"), clock.strftime("%H:%M")
                else:
                    continue
            p = parse_peso(peso_v)
            key = (f, h, arch.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            recs.append({
                "f": f, "h": h, "a": arch, "s": sistema_de(arch),
                "p": round(p, 6), "pr": fmt_peso(p), "hoja": hoja,
            })
    recs.sort(key=lambda r: (r["f"], r["h"], r["s"], r["a"]))
    return recs


def resumen_hoja(name: str, recs: list[dict]) -> dict:
    if not recs:
        return {"hoja": name, "reg": 0, "dias": 0, "desde": "", "hasta": "", "sistemas": []}
    dias = sorted({r["f"] for r in recs})
    return {
        "hoja": name,
        "reg": len(recs),
        "dias": len(dias),
        "desde": dias[0],
        "hasta": dias[-1],
        "sistemas": sorted({r["s"] for r in recs}),
    }


def year_blocks(ws):
    blocks = []
    for c in range(1, (ws.max_column or 1) + 1):
        v = ws.cell(4, c).value
        if isinstance(v, str) and v.strip().upper() == "FECHA":
            blocks.append(c)
    if not blocks:
        for c in range(1, (ws.max_column or 1) + 1):
            v = ws.cell(1, c).value
            if isinstance(v, str) and v.strip().upper() == "FECHA":
                blocks.append(c)
    return blocks


def extract_records(path: Path):
    wb = openpyxl.load_workbook(path, data_only=True)
    por_hoja = {}
    orden = []
    for name in wb.sheetnames:
        low = name.lower()
        if low in ("resumen", "verificaciones"):
            continue
        recs_h = parse_sheet_records(wb[name], name)
        if not recs_h and name not in ("192.168.200.50", "01-30"):
            continue
        por_hoja[name] = recs_h
        orden.append(name)
    hoja = "192.168.200.50" if "192.168.200.50" in por_hoja else pick_sheet(wb)
    recs_host = list(por_hoja.get("192.168.200.50") or por_hoja.get(hoja) or [])
    recs_0130 = list(por_hoja.get("01-30") or [])
    seen = {(r["f"], r["a"].strip().lower()) for r in recs_host}
    extra_0130 = [r for r in recs_0130 if (r["f"], r["a"].strip().lower()) not in seen]
    recs = recs_host + extra_0130
    recs.sort(key=lambda r: (r["f"], r["h"], r["s"], r["a"]))
    ayer = datetime.now().date() - timedelta(days=1)
    recs = [r for r in recs if r.get("f") and datetime.strptime(r["f"], "%Y-%m-%d").date() <= ayer]
    recs_0130 = [r for r in recs_0130 if r.get("f") and datetime.strptime(r["f"], "%Y-%m-%d").date() <= ayer]
    sistemas = sorted({r["s"] for r in recs})
    anios = []
    by_y = defaultdict(list)
    for r in recs:
        by_y[int(r["f"][:4])].append(r)
    for y in sorted(by_y):
        rows = by_y[y]
        dias = sorted({x["f"] for x in rows})
        gb = sum(x["p"] for x in rows)
        anios.append({
            "anio": y, "reg": len(rows), "dias": len(dias),
            "peso": fmt_peso(gb), "prom": fmt_peso(gb / len(rows) if rows else 0),
            "desde": dias[0], "hasta": dias[-1],
        })
    total_gb = round(sum(r["p"] for r in recs), 2)
    host_ip = "192.168.200.50" if "192.168.200.50" in por_hoja else (hoja if re.match(r"^\d+\.\d+\.\d+\.\d+$", hoja) else "")
    hojas = [resumen_hoja(n, por_hoja.get(n) or []) for n in orden]
    data = {
        "fuente": path.name,
        "hoja": hoja,
        "ubicacion": host_ip,
        "hojas": hojas,
        "hoja0130": resumen_hoja("01-30", recs_0130),
        "total": len(recs),
        "pesoTotalGB": total_gb,
        "desde": recs[0]["f"] if recs else "",
        "hasta": recs[-1]["f"] if recs else "",
        "sistemas": sistemas,
        "anios": anios,
        "faltantes": "",
        "destacados": {
            "mesesSinCaptura": 0,
            "anioPesado": anios[-1]["anio"] if anios else "",
            "anioRegistros": f'{anios[-1]["anio"]} — {anios[-1]["reg"]:,} archivos'.replace(",", ".") if anios else "",
        },
        "records": recs,
    }
    return data, wb.sheetnames


def build_analytics(data: dict) -> dict:
    recs = data["records"]
    if not recs:
        return {}
    year = int(data["hasta"][:4]) if data.get("hasta") else datetime.now().year
    y0, y1 = f"{year}-01-01", data["hasta"]
    present = sorted({r["f"] for r in recs if r["f"][:4] == str(year)})
    start = datetime(year, 1, 1)
    end = datetime.strptime(data["hasta"], "%Y-%m-%d")
    cal_days, missing = [], []
    d = start
    while d <= end:
        iso = d.strftime("%Y-%m-%d")
        cal_days.append(iso)
        if iso not in present:
            missing.append(iso)
        d += timedelta(days=1)
    huecos = []
    run = []
    for iso in missing:
        if not run or (datetime.strptime(iso, "%Y-%m-%d") - datetime.strptime(run[-1], "%Y-%m-%d")).days == 1:
            run.append(iso)
        else:
            huecos.append({"desde": run[0], "hasta": run[-1], "dias": len(run)})
            run = [iso]
    if run:
        huecos.append({"desde": run[0], "hasta": run[-1], "dias": len(run)})
    huecos.sort(key=lambda x: -x["dias"])

    by_day = defaultdict(int)
    for r in recs:
        if r["f"][:4] == str(year):
            by_day[r["f"]] += 1
    counts = list(by_day.values()) or [0]
    counts_sorted = sorted(counts)
    med = counts_sorted[len(counts_sorted) // 2]
    raros = [{"f": f, "n": n} for f, n in sorted(by_day.items()) if n != 10]

    last_f = data["hasta"]
    last_map = {}
    series = defaultdict(dict)
    for r in recs:
        last_map[r["s"]] = {"p": r["p"], "pr": r["pr"], "f": r["f"], "h": r["h"], "a": r["a"]}
        series[r["s"]][r["f"][:4]] = round(r["p"], 3)
    activos = [s for s, o in last_map.items() if o["f"] == last_f]

    # gemelas SIFacturacion
    ampm = defaultdict(lambda: {"AM": None, "PM": None})
    for r in recs:
        if r["s"] == "SIFacturacion" and r["f"][:4] == str(year):
            ampm[r["f"]]["AM" if r["h"] < "12:00" else "PM"] = r["p"]
    ambos, una, deltas, muestra = 0, [], [], []
    for f, v in sorted(ampm.items()):
        if v["AM"] is not None and v["PM"] is not None:
            ambos += 1
            dlt = v["PM"] - v["AM"]
            deltas.append(dlt)
            if len(muestra) < 8:
                muestra.append({"f": f, "am": round(v["AM"], 3), "pm": round(v["PM"], 3), "d": round(dlt, 4)})
        else:
            rec = next((r for r in recs if r["s"] == "SIFacturacion" and r["f"] == f), None)
            una.append({
                "f": f,
                "h": rec["h"] if rec else "—",
                "pr": rec["pr"] if rec else "—",
            })
    gemelas = {
        "diasAmbos": ambos, "diasUna": len(una),
        "deltaMedioGB": round(sum(deltas) / len(deltas), 4) if deltas else 0,
        "deltaMaxGB": round(max(deltas), 4) if deltas else 0,
        "una": una[:20],
        "muestra": [
            {**x, "amr": f"{x['am']} GB", "pmr": f"{x['pm']} GB"} for x in muestra
        ],
    }

    caidas = []
    prev = {}
    for r in recs:
        p0 = prev.get(r["s"])
        if p0 and p0["p"] > 0.05 and r["p"] < p0["p"] * 0.7:
            pct = round(100 * (1 - r["p"] / p0["p"]), 1)
            caidas.append({
                "s": r["s"], "f": r["f"], "h": r["h"],
                "antes": p0["pr"], "despues": r["pr"], "pct": pct, "prevf": p0["f"],
            })
        prev[r["s"]] = r
    caidas = caidas[:25]

    horas_raras = []
    for r in recs:
        if r["f"][:4] == str(year) and not (r["h"].startswith("01:") or r["h"].startswith("13:")):
            horas_raras.append({"f": r["f"], "h": r["h"], "s": r["s"], "a": r["a"], "pr": r["pr"]})

    fact_year = {}
    for r in recs:
        if r["s"] == "SIFacturacion":
            fact_year[r["f"][:4]] = r["p"]
    ys = sorted(fact_year)
    crecimiento = []
    for i in range(1, len(ys)):
        crecimiento.append({
            "de": ys[i - 1], "a": ys[i],
            "p0": round(fact_year[ys[i - 1]], 2), "p1": round(fact_year[ys[i]], 2),
            "delta": round(fact_year[ys[i]] - fact_year[ys[i - 1]], 2),
        })

    wd = [0] * 7
    for iso in present:
        wd[datetime.strptime(iso, "%Y-%m-%d").weekday()] += 1

    mismatches = []
    for r in recs:
        clock = name_clock(r["a"])
        if not clock:
            continue
        try:
            col = datetime.strptime(r["f"] + " " + r["h"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        diff = abs(int((col - clock).total_seconds() // 60))
        if diff >= 5:
            mismatches.append({
                "s": r["s"], "f": r["f"], "h": r["h"], "a": r["a"],
                "nombre": clock.strftime("%Y-%m-%d %H:%M"), "diffMin": diff,
            })

    # corridas incompletas latest year: 5 activos
    bloques = defaultdict(lambda: defaultdict(list))
    for r in recs:
        if r["f"][:4] != str(year) or r["s"] not in activos:
            continue
        b = "AM" if r["h"] < "12:00" else "PM"
        bloques[r["f"]][b].append(r["s"])
    esperados = set(activos)
    incompletas = []
    for f in sorted(bloques):
        for b, ss in bloques[f].items():
            uniq = sorted(set(ss))
            if esperados and len(uniq) < len(esperados):
                incompletas.append({"f": f, "b": b, "n": len(uniq), "sistemas": uniq})

    ret = {}
    end_d = datetime.strptime(data["hasta"], "%Y-%m-%d")
    for days in (7, 30, 90):
        cut = (end_d - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        c, gb = defaultdict(int), defaultdict(float)
        for r in recs:
            if r["f"] >= cut and r["s"] in activos:
                c[r["s"]] += 1
                gb[r["s"]] += r["p"]
        ret[str(days)] = {"n": dict(c), "gb": {k: round(v, 2) for k, v in gb.items()}}

    daily = round(sum(last_map[s]["p"] * 2 for s in activos), 2) if activos else 0
    return {
        "cal2026": {
            "desde": y0, "hasta": y1,
            "diasCalendario": len(cal_days),
            "diasConBak": len(present),
            "diasSinBak": len(missing),
        },
        "huecos2026": huecos[:12],
        "missing2026": missing,
        "present2026": present,
        "diasRaros": raros[:40],
        "gemelasFact": gemelas,
        "caidas": caidas,
        "horasRaras2026": horas_raras[:20],
        "crecimientoFact": crecimiento,
        "ultimoFact": {k: round(v, 2) for k, v in fact_year.items()},
        "weekday2026": wd,
        "archivosPorDia2026": {
            "mediana": med, "min": min(counts), "max": max(counts),
            "dias10": sum(1 for n in counts if n == 10),
        },
        "mismatchNombreHora": mismatches[:20],
        "corridasIncompletas": incompletas[:40],
        "disco": {
            "last": last_map,
            "series": {s: series[s] for s in last_map},
            "daily2fullGB": daily,
            "retencion": ret,
        },
        "activos": activos,
    }


def write_js(root: Path, data: dict, analytics: dict):
    (root / "js" / "data.js").write_text(
        "window.BACKUP_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    (root / "js" / "analytics.js").write_text(
        "window.BACKUP_ANALYTICS = " + json.dumps(analytics, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
