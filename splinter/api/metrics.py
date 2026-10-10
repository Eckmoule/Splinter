"""Indicateurs des pages du dashboard, calculés à partir de garmin.db.

- progression() : est-ce que je progresse sur le long terme ?
- training()    : est-ce que je m'entraîne correctement, en général et en ce moment ?

Charge d'entraînement : TRIMP de Banister par sortie (calculé seconde par seconde depuis les .fit,
voir fit_analysis), estimé à partir de la FC moyenne pour les autres activités, puis lissé en
Forme (CTL, moyenne exponentielle 42 j), Fatigue (ATL, 7 j) et Fraîcheur (TSB = Forme - Fatigue).
"""

import json
import math
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, timedelta

from splinter.export import RUN_TYPES, terrain
from splinter.fit_analysis import heart_rate_refs, trimp_rate

TREND_DAYS = 42          # fenêtre glissante des tendances (6 semaines)
LONG_RUN_S = 60 * 60     # sortie longue pour le découplage
LONG_RUN_WEEK_S = 75 * 60  # sortie longue pour la variété des séances
CTL_DAYS, ATL_DAYS = 42, 7
MIN_TRIMP_PER_MIN = 0.2  # en dessous : capteur FC défaillant, charge estimée
RAMP_LIMIT_PCT = 10      # repère de montée en charge hebdomadaire

# règles du résumé « en ce moment »
RATIO_LOW, RATIO_HIGH, RATIO_PEAK = 0.8, 1.3, 1.5
RHR_RISE_BPM = 3
SHORT_SLEEP_H = 6.5
EASY_SHARE_MIN = 50      # % minimal de temps en zones 1-2 sur 4 semaines
HRV_BASELINE_DAYS = 60

EFFORT_LABELS = {"RECOVERY": "récupération", "AEROBIC_BASE": "endurance", "TEMPO": "tempo",
                 "LACTATE_THRESHOLD": "seuil", "VO2MAX": "VO2max", "ANAEROBIC_CAPACITY": "anaérobie",
                 "SPEED": "vitesse"}


def _db(path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _rolling(points: list[tuple[str, float]], days: int = TREND_DAYS, stat=statistics.fmean) -> list:
    """Tendance : statistique des points des `days` jours précédents, évaluée à chaque point."""
    out = []
    for i, (d, _) in enumerate(points):
        lo = (_d(d) - timedelta(days=days)).isoformat()
        window = [v for dd, v in points[: i + 1] if dd > lo]
        out.append([d, round(stat(window), 3)])
    return out


def _runs(db) -> list[dict]:
    placeholders = ",".join("?" * len(RUN_TYPES))
    rows = db.execute(
        f"""SELECT a.activity_id, a.start_time, a.type_key, a.name, a.distance_m, a.moving_s, a.elevation_gain,
                   a.avg_hr, a.raw_json, f.hr_fixed_pace, f.ef_flat, f.decoupling_pct, f.trimp,
                   EXISTS (SELECT 1 FROM run_laps l WHERE l.activity_id = a.activity_id
                           AND l.intensity IN ('rest', 'recovery')) AS structured
            FROM activities a LEFT JOIN run_fit_metrics f USING (activity_id)
            WHERE a.type_key IN ({placeholders}) ORDER BY a.start_time""",
        list(RUN_TYPES),
    ).fetchall()
    runs = []
    for r in rows:
        raw = json.loads(r["raw_json"])
        runs.append({
            "id": r["activity_id"], "date": r["start_time"][:10], "name": r["name"],
            "km": (r["distance_m"] or 0) / 1000, "moving_s": r["moving_s"] or 0, "d_plus": r["elevation_gain"] or 0,
            "avg_hr": r["avg_hr"], "vo2max": raw.get("vO2MaxValue"), "effect": raw.get("trainingEffectLabel"),
            "zones_s": [raw.get(f"hrTimeInZone_{z}") or 0 for z in range(1, 6)],
            "hr_fixed_pace": r["hr_fixed_pace"], "ef": r["ef_flat"], "decoupling": r["decoupling_pct"],
            "trimp": r["trimp"], "structured": bool(r["structured"]),
        })
    return runs


def _health(db) -> dict[str, dict]:
    rows = {r["date"]: dict(r) for r in db.execute(
        "SELECT date, rhr, hrv_night, sleep_s, readiness, vo2max FROM daily_health ORDER BY date")}
    rhr = sorted(h["rhr"] for h in rows.values() if h["rhr"])
    if rhr:  # jours sans montre : « FC repos » aberrante calculée sur une seule activité
        limit = 1.5 * rhr[len(rhr) // 2]
        for h in rows.values():
            if h["rhr"] and h["rhr"] > limit:
                h["rhr"] = None
    return rows


def _monthly(health: dict, key: str) -> list:
    acc = defaultdict(list)
    for d, h in health.items():
        if h[key] is not None:
            acc[d[:7]].append(h[key])
    return [[f"{m}-15", round(statistics.fmean(v), 1)] for m, v in sorted(acc.items()) if len(v) >= 10]


# --- Progression -------------------------------------------------------------------------------

def progression(db_path) -> dict:
    with _db(db_path) as db:
        runs = _runs(db)
        health = _health(db)
    today = date.today()
    # FC à allure fixe et efficacité : toutes les sorties, la sélection des portions comparables (plat,
    # 5e-60e minute, pas juste après une montée) est faite dans fit_analysis. Le type Garmin (course /
    # trail) n'est pas utilisé : il ne reflète que l'appli lancée sur la montre.
    fixed = [(r["date"], round(r["hr_fixed_pace"], 1)) for r in runs if r["hr_fixed_pace"]]
    ef = [(r["date"], round(r["ef"], 3)) for r in runs
          if r["ef"] and not r["structured"] and r["moving_s"] >= 30 * 60]
    # VO2max quotidienne (montres récentes) dès qu'elle existe ; avant, valeur par sortie. Pas de
    # mélange ensuite : une ancienne montre ressortie ponctuellement estime une VO2max différente.
    # Les jours sans données de sommeil, la montre principale n'est pas portée : Garmin recalcule alors
    # la VO2max depuis une autre montre, avec des valeurs incohérentes : elles sont écartées.
    vo2_daily = {d: h["vo2max"] for d, h in health.items() if h["vo2max"] and h["sleep_s"]}
    daily_from = min(vo2_daily) if vo2_daily else "9999"
    vo2_runs = {r["date"]: r["vo2max"] for r in runs if r["vo2max"] and r["date"] < daily_from}
    vo2 = sorted({**vo2_runs, **vo2_daily}.items())
    # découplage : compare les deux moitiés de toute la sortie, donc seulement sur terrain plat (D+/km)
    flat = [r for r in runs if terrain(r["d_plus"], r["km"]) == "plat"]
    long_runs = [(r["date"], round(r["decoupling"], 1)) for r in flat
                 if r["decoupling"] is not None and r["moving_s"] >= LONG_RUN_S]

    months = defaultdict(lambda: {"km": 0.0, "d_plus": 0.0, "longest": 0.0})
    for r in runs:
        m = months[r["date"][:7]]
        m["km"] += r["km"]
        m["d_plus"] += r["d_plus"]
        m["longest"] = max(m["longest"], r["km"])
    month_keys = sorted(months)

    # tuiles : même calcul que la fin des courbes (fenêtre glissante jusqu'à aujourd'hui), comparé à
    # la même fenêtre un an plus tôt (même saison, donc même effet de la chaleur)
    def tile(points, days, stat):
        def window(end: date):
            lo, hi = (end - timedelta(days=days)).isoformat(), end.isoformat()
            values = [v for d, v in points if lo < d <= hi]
            return stat(values) if values else None
        return {"now": window(today), "year_ago": window(today - timedelta(days=365)), "days": days}

    rhr_points = [(d, h["rhr"]) for d, h in health.items() if h["rhr"]]
    return {
        "tiles": {
            "hr_fixed_pace": tile(fixed, TREND_DAYS, statistics.median),
            "ef": tile(ef, TREND_DAYS, statistics.fmean),
            "rhr": tile(rhr_points, 30, statistics.fmean),
            "vo2max": {"now": vo2[-1][1] if vo2 else None,
                       "year_ago": next((v for d, v in reversed(vo2) if d <= (today - timedelta(days=365)).isoformat()), None)},
        },
        "hr_fixed_pace": {"points": fixed, "trend": _rolling(fixed, stat=statistics.median)},
        "ef": {"points": ef, "trend": _rolling(ef)},
        "vo2max": {"points": vo2},
        "decoupling": {"points": long_runs, "trend": _rolling(long_runs, days=90, stat=statistics.median)},
        "rhr": _monthly(health, "rhr"),
        "hrv": _monthly(health, "hrv_night"),
        "months": [{"month": m, "km": round(months[m]["km"], 1), "d_plus": round(months[m]["d_plus"]),
                    "longest": round(months[m]["longest"], 1)} for m in month_keys],
        "fixed_pace_band": "6:00-6:30",
    }


# --- Entraînement ------------------------------------------------------------------------------

def _daily_loads(db, runs: list[dict]) -> dict[str, float]:
    """Charge TRIMP par jour : sorties course (seconde par seconde) + autres activités (FC moyenne)."""
    hr_max, rest_by_day, rest_default = heart_rate_refs(db)
    rates = sorted(r["trimp"] / (r["moving_s"] / 60) for r in runs
                   if r["trimp"] and r["moving_s"] and r["trimp"] / (r["moving_s"] / 60) >= MIN_TRIMP_PER_MIN)
    typical = rates[len(rates) // 2] if rates else 1.0

    loads: dict[str, float] = defaultdict(float)
    for r in runs:
        minutes = r["moving_s"] / 60
        ok = r["trimp"] and minutes and r["trimp"] / minutes >= MIN_TRIMP_PER_MIN
        loads[r["date"]] += r["trimp"] if ok else minutes * typical  # pas de FC fiable : charge typique
    placeholders = ",".join("?" * len(RUN_TYPES))
    for a in db.execute(f"SELECT start_time, duration_s, avg_hr FROM activities WHERE type_key NOT IN ({placeholders})",
                        list(RUN_TYPES)):
        if a["avg_hr"] and a["duration_s"]:
            d = a["start_time"][:10]
            loads[d] += a["duration_s"] / 60 * trimp_rate(a["avg_hr"], rest_by_day.get(d, rest_default), hr_max)
    return loads


def _fitness(loads: dict[str, float], start: date, end: date) -> list[dict]:
    """Forme (CTL), Fatigue (ATL), Fraîcheur (TSB = CTL - ATL de la veille), jour par jour."""
    k_ctl, k_atl = 1 - math.exp(-1 / CTL_DAYS), 1 - math.exp(-1 / ATL_DAYS)
    ctl = atl = 0.0
    out = []
    for d in _days(start, end):
        tsb = ctl - atl
        load = loads.get(d.isoformat(), 0.0)
        ctl += (load - ctl) * k_ctl
        atl += (load - atl) * k_atl
        out.append({"date": d.isoformat(), "load": round(load, 1), "ctl": round(ctl, 1), "atl": round(atl, 1),
                    "tsb": round(tsb, 1), "ratio": round(atl / ctl, 2) if ctl >= 1 else None})
    return out


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _fr(x: float) -> str:
    return str(x).replace(".", ",")


def _summary(fit_today: dict, health: dict, runs: list[dict], today: date) -> dict:
    """Résumé « en ce moment » par règles simples et explicites."""
    signals = []

    ratio = fit_today["ratio"]
    if ratio is None:
        signals.append({"label": "Charge", "value": "–", "status": "neutre", "text": None,
                        "rule": "Pas assez d'historique pour calculer le ratio."})
    else:
        if ratio > RATIO_PEAK:
            status, text = "alerte", "pic de charge"
        elif ratio > RATIO_HIGH:
            status, text = "attention", "charge en hausse rapide"
        elif ratio < RATIO_LOW:
            status, text = "neutre", "charge en baisse (récupération ou coupure)"
        else:
            status, text = "ok", "charge maîtrisée"
        signals.append({"label": "Charge", "value": f"ratio {ratio:.2f}".replace(".", ","), "status": status,
                        "text": text, "rule": f"Fatigue ÷ Forme : sain entre {_fr(RATIO_LOW)} et {_fr(RATIO_HIGH)}, "
                                              f"hausse rapide au-delà, pic au-delà de {_fr(RATIO_PEAK)}."})

    def window(key, days, end_offset=0):
        end = today - timedelta(days=end_offset)
        start = end - timedelta(days=days - 1)
        return [h[key] for d, h in health.items() if start.isoformat() <= d <= end.isoformat() and h[key] is not None]

    hrv7, base = window("hrv_night", 7), window("hrv_night", HRV_BASELINE_DAYS, end_offset=7)
    if len(hrv7) >= 3 and len(base) >= 20:
        m7, mb, sd = statistics.fmean(hrv7), statistics.fmean(base), statistics.pstdev(base)
        low = m7 < mb - sd
        signals.append({"label": "HRV", "value": f"{m7:.0f} ms (normale {mb:.0f})",
                        "status": "attention" if low else "ok", "text": "HRV sous ta normale" if low else None,
                        "rule": f"Moyenne des 7 dernières nuits comparée aux {HRV_BASELINE_DAYS} jours précédents : "
                                "alerte si plus d'un écart-type en dessous."})

    rhr7, rhr30 = window("rhr", 7), window("rhr", 30, end_offset=7)
    if len(rhr7) >= 3 and len(rhr30) >= 10:
        diff = statistics.fmean(rhr7) - statistics.fmean(rhr30)
        high = diff >= RHR_RISE_BPM
        signals.append({"label": "FC repos", "value": f"{diff:+.1f} bpm".replace(".", ","),
                        "status": "attention" if high else "ok", "text": "FC repos en hausse" if high else None,
                        "rule": f"Moyenne sur 7 jours comparée aux 30 jours précédents : alerte à +{RHR_RISE_BPM} bpm."})

    sleep7 = window("sleep_s", 7)
    if len(sleep7) >= 3:
        hours = statistics.fmean(sleep7) / 3600
        short = hours < SHORT_SLEEP_H
        signals.append({"label": "Sommeil", "value": f"{int(hours)} h {round(hours % 1 * 60):02d}",
                        "status": "attention" if short else "ok", "text": "sommeil court" if short else None,
                        "rule": f"Moyenne des 7 dernières nuits : alerte sous {_fr(SHORT_SLEEP_H)} h."})

    since = (today - timedelta(days=27)).isoformat()
    zones = [sum(r["zones_s"][z] for r in runs if r["date"] >= since) for z in range(5)]
    if sum(zones):
        easy = 100 * (zones[0] + zones[1]) / sum(zones)
        few = easy < EASY_SHARE_MIN
        signals.append({"label": "Intensité", "value": f"{easy:.0f} % en zones 1-2",
                        "status": "attention" if few else "ok", "text": "peu de course facile" if few else None,
                        "rule": f"Temps de course en zones cardiaques 1-2 sur 4 semaines : alerte sous {EASY_SHARE_MIN} %."})

    # rouge : pic de charge, ou HRV basse ET FC repos en hausse (signe classique de surmenage)
    alerts = [s for s in signals if s["status"] == "alerte"]
    warnings = [s for s in signals if s["status"] == "attention"]
    flagged = {s["label"] for s in warnings}
    level = "alerte" if alerts or {"HRV", "FC repos"} <= flagged else "attention" if warnings else "ok"
    texts = [s["text"] for s in alerts + warnings]
    if not texts:
        load_text = next((s["text"] for s in signals if s["label"] == "Charge" and s["text"]), None)
        texts = [load_text or "rien à signaler", "récupération correcte"]
    sentence = ", ".join(texts)
    return {"level": level, "sentence": sentence[0].upper() + sentence[1:] + ".", "signals": signals}


def training(db_path, months: int = 3) -> dict:
    today = date.today()
    with _db(db_path) as db:
        runs = _runs(db)
        health = _health(db)
        loads = _daily_loads(db, runs)
        readiness = {d: h["readiness"] for d, h in health.items() if h["readiness"] is not None}
    first = _d(min(loads)) if loads else today
    fitness = _fitness(loads, first, today)
    now_start = (today - timedelta(days=89)).isoformat()

    # récupération sur 90 jours, avec la normale de HRV (moyenne ± écart-type des 60 jours précédents)
    hrv_band = []
    for d in _days(today - timedelta(days=89), today):
        lo = (d - timedelta(days=HRV_BASELINE_DAYS + 7)).isoformat()
        hi = (d - timedelta(days=7)).isoformat()
        base = [h["hrv_night"] for dd, h in health.items() if lo <= dd <= hi and h["hrv_night"]]
        if len(base) >= 20:
            m, sd = statistics.fmean(base), statistics.pstdev(base)
            hrv_band.append([d.isoformat(), round(m - sd, 1), round(m + sd, 1)])
    recent = {d: h for d, h in health.items() if d >= now_start}

    # tendance générale sur la période choisie
    period_start = _monday(today - timedelta(days=30 * months))
    sel = [r for r in runs if r["date"] >= period_start.isoformat()]
    weeks = []
    w = period_start
    while w <= today:
        rs = [r for r in sel if w.isoformat() <= r["date"] < (w + timedelta(days=7)).isoformat()]
        weeks.append({"week": w.isoformat(), "partial": w + timedelta(days=6) > today,
                      "runs": len(rs), "km": round(sum(r["km"] for r in rs), 1),
                      "long_run": any(r["moving_s"] >= LONG_RUN_WEEK_S for r in rs),
                      "load": round(sum(loads.get((w + timedelta(days=i)).isoformat(), 0) for i in range(7)))})
        w += timedelta(days=7)
    all_weeks_km = defaultdict(float)
    for r in runs:
        all_weeks_km[_monday(_d(r["date"])).isoformat()] += r["km"]
    for wk in weeks:  # variation vs moyenne des 4 semaines précédentes
        prev = [all_weeks_km.get((_d(wk["week"]) - timedelta(days=7 * i)).isoformat(), 0.0) for i in range(1, 5)]
        base = statistics.fmean(prev)
        wk["ramp_pct"] = round(100 * (wk["km"] / base - 1)) if base >= 5 and not wk["partial"] else None

    zone_months = defaultdict(lambda: [0.0] * 5)
    for r in sel:
        for z in range(5):
            zone_months[r["date"][:7]][z] += r["zones_s"][z]
    zones_total = [sum(r["zones_s"][z] for r in sel) for z in range(5)]
    effects = defaultdict(int)
    for r in sel:
        effects[EFFORT_LABELS.get(r["effect"], "non classée")] += 1
    full_weeks = [wk for wk in weeks if not wk["partial"]]

    return {
        "summary": _summary(fitness[-1], health, runs, today),
        "now": {
            "fitness": [f for f in fitness if f["date"] >= now_start],
            "hrv": [[d, h["hrv_night"]] for d, h in sorted(recent.items()) if h["hrv_night"]],
            "hrv_band": hrv_band,
            "rhr": [[d, h["rhr"]] for d, h in sorted(recent.items()) if h["rhr"]],
            "sleep_h": [[d, round(h["sleep_s"] / 3600, 2)] for d, h in sorted(recent.items()) if h["sleep_s"]],
            "readiness": [[d, v] for d, v in sorted(readiness.items()) if d >= now_start],
        },
        "fitness_all": [{"date": f["date"], "ctl": f["ctl"], "atl": f["atl"], "tsb": f["tsb"]} for f in fitness],
        "general": {
            "months": months,
            "start": period_start.isoformat(),
            "weeks": weeks,
            "zones_total_s": zones_total,
            "zones_by_month": [{"month": m, "zones_s": z} for m, z in sorted(zone_months.items())],
            "effects": sorted(effects.items(), key=lambda x: -x[1]),
            "runs_per_week": round(len(sel) / max(1, len(weeks)), 1),
            "empty_weeks": sum(1 for wk in full_weeks if wk["runs"] == 0),
            "long_run_weeks": sum(1 for wk in full_weeks if wk["long_run"]),
            "full_weeks": len(full_weeks),
            "ramp_limit_pct": RAMP_LIMIT_PCT,
        },
        "rules": {"ratio": [RATIO_LOW, RATIO_HIGH, RATIO_PEAK], "ctl_days": CTL_DAYS, "atl_days": ATL_DAYS},
    }
