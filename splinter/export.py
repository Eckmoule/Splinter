"""Export des données course à pied dans un format lisible par Claude.

Génère dans Data/SplinterDrive (synchronisé par Google Drive) :
- LISEZMOI.md            profil, records, résumé récent, dictionnaire des colonnes
- courses.csv            une ligne par sortie (route + trail)
- courses_km.csv         une ligne par kilomètre de chaque sortie (issu des .fit)
- semaines.csv           volume, intensité et forme par semaine
- sante_quotidienne.csv  sommeil, HRV, FC repos, charge... par jour

Usage : python -m splinter.export
"""

import csv
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from splinter.config import EXPORT_DIR
from splinter.fit_analysis import FIXED_PACE_BAND
from splinter.garmin_client import open_db

MAX_FLAT_GAIN_PER_KM = 10  # m de D+ par km au-delà desquels le découplage n'est pas exporté

RUN_TYPES = {"running": "route", "trail_running": "trail", "treadmill_running": "tapis",
             "track_running": "piste", "indoor_running": "intérieur"}


# --- formatage ---------------------------------------------------------------

def _hms(seconds) -> str:
    if seconds is None:
        return ""
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _pace(speed_ms) -> str:
    """m/s -> 'm:ss' par km."""
    if not speed_ms:
        return ""
    s = round(1000 / speed_ms)
    return f"{s // 60}:{s % 60:02d}"


def _r(x, nd=1):
    if x is None:
        return ""
    return round(x) if nd == 0 else round(x, nd)


def _min(seconds):
    return "" if seconds is None else round(seconds / 60)


def _hours(seconds):
    return "" if seconds is None else round(seconds / 3600, 2)


def _status(phrase):
    """'PRODUCTIVE_3' -> 'PRODUCTIVE' (le suffixe est une variante de message)."""
    return phrase.rsplit("_", 1)[0] if phrase and phrase[-1].isdigit() else (phrase or "")


def _monday(d: str) -> str:
    day = date.fromisoformat(d[:10])
    return (day - timedelta(days=day.weekday())).isoformat()


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# --- chargement --------------------------------------------------------------

def _clean_rhr(health: dict) -> None:
    """Les jours où la montre n'est pas portée, Garmin peut calculer une « FC repos »
    à partir d'une seule activité (ex. 130 bpm) : on l'écarte au-delà de 1,5 x la médiane."""
    values = sorted(h["rhr"] for h in health.values() if h["rhr"])
    if not values:
        return
    limit = 1.5 * values[len(values) // 2]
    for h in health.values():
        if h["rhr"] and h["rhr"] > limit:
            h["rhr"] = None


def _wear_gaps(health: dict, min_days: int = 3) -> list[str]:
    """Périodes d'au moins `min_days` jours sans données de sommeil (montre non portée)."""
    days = sorted(health)
    if not days:
        return []
    have = {d for d, h in health.items() if h["sleep_s"]}
    gaps, start = [], None
    d, end = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    while d <= end:
        if d.isoformat() not in have:
            start = start or d
        elif start:
            if (d - start).days >= min_days:
                gaps.append(f"du {start} au {d - timedelta(days=1)}")
            start = None
        d += timedelta(days=1)
    if start and (end - start).days + 1 >= min_days:
        gaps.append(f"du {start} au {end}")
    return gaps


def _load(db: sqlite3.Connection):
    db.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(RUN_TYPES))
    runs = [
        (r["start_time"], json.loads(r["raw_json"]))
        for r in db.execute(
            f"SELECT start_time, raw_json FROM activities WHERE type_key IN ({placeholders}) ORDER BY start_time",
            list(RUN_TYPES),
        )
    ]
    health = {r["date"]: dict(r) for r in db.execute("SELECT * FROM daily_health ORDER BY date")}
    _clean_rhr(health)
    zones_row = db.execute("SELECT raw_json FROM profile WHERE key='hr_zones'").fetchone()
    zones = json.loads(zones_row[0]) if zones_row else []
    fit_metrics = {r["activity_id"]: dict(r) for r in db.execute("SELECT * FROM run_fit_metrics")}
    km_rows = [dict(r) for r in db.execute("SELECT * FROM run_km ORDER BY activity_id, km")]
    return runs, health, zones, fit_metrics, km_rows


# --- fichiers ----------------------------------------------------------------

_BAND = "{}_{:02d}_{}_{:02d}".format(FIXED_PACE_BAND[0] // 60, FIXED_PACE_BAND[0] % 60,
                                     FIXED_PACE_BAND[1] // 60, FIXED_PACE_BAND[1] % 60)
_BAND_TXT = "{}:{:02d}-{}:{:02d}".format(FIXED_PACE_BAND[0] // 60, FIXED_PACE_BAND[0] % 60,
                                       FIXED_PACE_BAND[1] // 60, FIXED_PACE_BAND[1] % 60)

COURSES_COLUMNS = [
    ("id", "identifiant Garmin de la sortie (clé de jointure avec courses_km.csv)"),
    ("date", "date locale de départ (AAAA-MM-JJ)"),
    ("heure", "heure locale de départ"),
    ("type", "route, trail, tapis, piste"),
    ("nom", "nom de l'activité dans Garmin Connect"),
    ("distance_km", "distance"),
    ("duree", "durée totale h:mm:ss (pauses incluses)"),
    ("duree_mouvement", "temps en mouvement h:mm:ss"),
    ("allure", "allure moyenne en mouvement, min:s par km"),
    ("allure_ajustee_pente", "allure équivalente sur plat (GAP), min:s par km"),
    ("d_plus_m", "dénivelé positif"),
    ("d_moins_m", "dénivelé négatif"),
    ("fc_moy", "fréquence cardiaque moyenne (bpm)"),
    ("fc_max", "fréquence cardiaque max (bpm)"),
    ("cadence", "cadence moyenne (pas/min)"),
    ("foulee_m", "longueur de foulée moyenne (m)"),
    ("puissance_moy", "puissance moyenne (W)"),
    ("puissance_norm", "puissance normalisée (W)"),
    ("oscillation_cm", "oscillation verticale moyenne (cm)"),
    ("contact_sol_ms", "temps de contact au sol moyen (ms)"),
    ("te_aerobie", "Training Effect aérobie Garmin (0-5)"),
    ("te_anaerobie", "Training Effect anaérobie Garmin (0-5)"),
    ("type_effort", "bénéfice principal selon Garmin (AEROBIC_BASE, TEMPO, THRESHOLD, VO2MAX, ...)"),
    ("charge", "charge d'entraînement Garmin de la séance (EPOC)"),
    ("z1_min", "minutes en zone cardiaque 1"),
    ("z2_min", "minutes en zone cardiaque 2"),
    ("z3_min", "minutes en zone cardiaque 3"),
    ("z4_min", "minutes en zone cardiaque 4"),
    ("z5_min", "minutes en zone cardiaque 5"),
    ("meilleur_1km", "meilleur kilomètre de la sortie h:mm:ss"),
    ("meilleur_5km", "meilleurs 5 km de la sortie"),
    ("meilleur_10km", "meilleurs 10 km de la sortie"),
    ("temp_min_c", "température min mesurée par la montre (°C, influencée par le corps)"),
    ("temp_max_c", "température max mesurée par la montre"),
    ("vo2max", "VO2max estimée après la séance"),
    ("body_battery_delta", "variation de Body Battery pendant la séance"),
    ("lieu", "lieu de départ"),
    ("hrv_nuit_precedente", "HRV moyenne de la nuit précédente (ms)"),
    ("score_sommeil_veille", "score de sommeil de la nuit précédente (0-100)"),
    ("disposition_matin", "disposition à l'entraînement du matin (0-100, montres récentes : voir Limites)"),
    ("fc_1re_moitie", "FC moyenne de la 1re moitié du temps en mouvement (5 premières min exclues)"),
    ("fc_2e_moitie", "FC moyenne de la 2e moitié"),
    ("allure_1re_moitie", "allure moyenne de la 1re moitié, min:s par km"),
    ("allure_2e_moitie", "allure moyenne de la 2e moitié"),
    ("decouplage_pct", "découplage allure/FC (Pa:HR) en % : perte d'efficacité (vitesse/FC) entre les "
                       "deux moitiés. < 5 % = bonne endurance aérobie sur cette durée. Seulement pour les "
                       f"sorties route d'au moins 35 min avec au plus {MAX_FLAT_GAIN_PER_KM} m D+/km"),
    (f"fc_allure_{_BAND}", f"FC moyenne sur le plat (pente < 2 %) quand l'allure est entre {_BAND_TXT}/km, "
                           "hors 5 premières min ; indicateur de progression : baisse = meilleure forme"),
    (f"min_allure_{_BAND}", f"minutes passées sur le plat à {_BAND_TXT}/km (la FC est fournie si >= 5 min)"),
]


def _course_row(start_time: str, a: dict, health: dict, fm: dict) -> list:
    h = health.get(start_time[:10], {})
    km = (a.get("distance") or 0) / 1000
    flat_road = ((a.get("activityType") or {}).get("typeKey") == "running" and km > 0
                 and (a.get("elevationGain") or 0) / km <= MAX_FLAT_GAIN_PER_KM)
    return [
        a["activityId"],
        start_time[:10],
        start_time[11:16],
        RUN_TYPES.get((a.get("activityType") or {}).get("typeKey"), ""),
        a.get("activityName") or "",
        _r((a.get("distance") or 0) / 1000, 2),
        _hms(a.get("duration")),
        _hms(a.get("movingDuration")),
        _pace((a.get("distance") or 0) / a["movingDuration"] if a.get("movingDuration") else None),
        _pace(a.get("avgGradeAdjustedSpeed")),
        _r(a.get("elevationGain"), 0),
        _r(a.get("elevationLoss"), 0),
        _r(a.get("averageHR"), 0),
        _r(a.get("maxHR"), 0),
        _r(a.get("averageRunningCadenceInStepsPerMinute"), 0),
        _r((a.get("avgStrideLength") or 0) / 100, 2) if a.get("avgStrideLength") else "",
        _r(a.get("avgPower"), 0),
        _r(a.get("normPower"), 0),
        _r(a.get("avgVerticalOscillation"), 1),
        _r(a.get("avgGroundContactTime"), 0),
        _r(a.get("aerobicTrainingEffect"), 1),
        _r(a.get("anaerobicTrainingEffect"), 1),
        a.get("trainingEffectLabel") or "",
        _r(a.get("activityTrainingLoad"), 0),
        *[_min(a.get(f"hrTimeInZone_{z}")) for z in range(1, 6)],
        _hms(a.get("fastestSplit_1000")),
        _hms(a.get("fastestSplit_5000")),
        _hms(a.get("fastestSplit_10000")),
        _r(a.get("minTemperature"), 0),
        _r(a.get("maxTemperature"), 0),
        _r(a.get("vO2MaxValue"), 0),
        a.get("differenceBodyBattery") if a.get("differenceBodyBattery") is not None else "",
        a.get("locationName") or "",
        h.get("hrv_night") or "",
        h.get("sleep_score") or "",
        h.get("readiness") or "",
        _r(fm.get("hr_first_half"), 0),
        _r(fm.get("hr_second_half"), 0),
        _pace(fm.get("speed_first_half")),
        _pace(fm.get("speed_second_half")),
        _r(fm.get("decoupling_pct"), 1) if flat_road else "",
        _r(fm.get("hr_fixed_pace"), 0),
        _min(fm.get("fixed_pace_s")) if fm else "",
    ]


KM_COLUMNS = [
    ("id", "identifiant de la sortie (voir courses.csv)"),
    ("date", "date de la sortie"),
    ("type", "route, trail..."),
    ("km", "numéro du kilomètre (1 = premier)"),
    ("distance_m", "1000, sauf le dernier kilomètre partiel"),
    ("temps", "temps en mouvement sur ce kilomètre m:ss"),
    ("allure", "allure en mouvement, min:s par km"),
    ("fc_moy", "FC moyenne"),
    ("fc_max", "FC max"),
    ("d_plus_m", "dénivelé positif sur ce kilomètre"),
    ("d_moins_m", "dénivelé négatif"),
    ("cadence", "cadence moyenne (pas/min)"),
    ("puissance", "puissance moyenne (W)"),
]


def _km_rows(km_rows, runs) -> list[list]:
    info = {a["activityId"]: (t[:10], RUN_TYPES.get((a.get("activityType") or {}).get("typeKey"), ""))
            for t, a in runs}
    rows = []
    for k in km_rows:
        if k["activity_id"] not in info:
            continue
        d, typ = info[k["activity_id"]]
        moving, dist = k["moving_s"], k["distance_m"]
        rows.append([
            k["activity_id"], d, typ, k["km"], _r(dist, 0),
            f"{int(moving // 60)}:{int(moving % 60):02d}" if moving else "",
            _pace(dist / moving) if moving else "",
            _r(k["hr_avg"], 0), k["hr_max"] or "",
            _r(k["ascent_m"], 0), _r(k["descent_m"], 0),
            _r(k["cadence_spm"], 0), _r(k["power_w"], 0),
        ])
    return rows


SEMAINES_COLUMNS = [
    ("semaine", "lundi de la semaine (AAAA-MM-JJ)"),
    ("sorties", "nombre de sorties course"),
    ("km", "distance totale"),
    ("d_plus_m", "dénivelé positif total"),
    ("duree", "temps en mouvement total h:mm:ss"),
    ("allure_moy", "allure moyenne en mouvement, min:s par km"),
    ("plus_longue_km", "plus longue sortie de la semaine"),
    ("charge", "somme des charges Garmin des séances"),
    ("pct_z1_z2", "% du temps en zones cardiaques 1-2 (facile)"),
    ("pct_z4_z5", "% du temps en zones cardiaques 4-5 (intense)"),
    ("fc_repos_moy", "FC au repos moyenne de la semaine"),
    ("hrv_moy", "HRV nocturne moyenne (ms)"),
    ("sommeil_moy_h", "durée de sommeil moyenne (heures)"),
    ("score_sommeil_moy", "score de sommeil moyen"),
    ("disposition_moy", "disposition à l'entraînement moyenne (montres récentes : voir Limites)"),
    ("ratio_charge_fin", "ratio charge aiguë/chronique Garmin en fin de semaine (optimal ~0.8-1.3)"),
    ("statut_fin", "statut d'entraînement Garmin en fin de semaine"),
]


def _avg(values, nd=1):
    values = [v for v in values if v is not None]
    if not values:
        return ""
    return round(sum(values) / len(values)) if nd == 0 else round(sum(values) / len(values), nd)


def _sum_known(values):
    """Somme des valeurs connues ; vide si aucune n'est connue."""
    values = [v for v in values if v is not None]
    return round(sum(values)) if values else ""


def _semaines(runs, health) -> list[list]:
    weeks = defaultdict(lambda: {"runs": [], "days": []})
    for start_time, a in runs:
        weeks[_monday(start_time)]["runs"].append(a)
    for d, h in health.items():
        weeks[_monday(d)]["days"].append(h)

    rows = []
    for monday in sorted(weeks):
        w = weeks[monday]
        rs, ds = w["runs"], sorted(w["days"], key=lambda h: h["date"])
        dist = sum(a.get("distance") or 0 for a in rs)
        moving = sum(a.get("movingDuration") or 0 for a in rs)
        zones = [sum(a.get(f"hrTimeInZone_{z}") or 0 for a in rs) for z in range(1, 6)]
        zt = sum(zones)
        last = next((h for h in reversed(ds) if h.get("acwr") is not None), {})
        rows.append([
            monday,
            len(rs),
            round(dist / 1000, 1),
            round(sum(a.get("elevationGain") or 0 for a in rs)),
            _hms(moving) if rs else "",
            _pace(dist / moving) if moving else "",
            round(max((a.get("distance") or 0 for a in rs), default=0) / 1000, 1),
            _sum_known([a.get("activityTrainingLoad") for a in rs]),
            round(100 * (zones[0] + zones[1]) / zt) if zt else "",
            round(100 * (zones[3] + zones[4]) / zt) if zt else "",
            _avg([h["rhr"] for h in ds]),
            _avg([h["hrv_night"] for h in ds], 0),
            _avg([h["sleep_s"] / 3600 if h["sleep_s"] else None for h in ds], 2),
            _avg([h["sleep_score"] for h in ds], 0),
            _avg([h["readiness"] for h in ds], 0),
            last.get("acwr", ""),
            _status(last.get("training_status")),
        ])
    return rows


SANTE_COLUMNS = [
    ("date", "jour (le sommeil et la HRV sont ceux de la nuit qui précède ce jour)"),
    ("pas", "nombre de pas"),
    ("kcal_actives", "calories actives"),
    ("min_intenses", "minutes d'intensité modérée + 2 x vigoureuse (comptage OMS/Garmin)"),
    ("fc_repos", "FC au repos (bpm)"),
    ("stress_moy", "stress moyen Garmin (0-100)"),
    ("body_battery_max", "Body Battery max de la journée"),
    ("body_battery_min", "Body Battery min de la journée"),
    ("body_battery_reveil", "Body Battery au réveil"),
    ("sommeil_h", "durée de sommeil (heures)"),
    ("score_sommeil", "score de sommeil (0-100)"),
    ("profond_h", "sommeil profond (heures)"),
    ("paradoxal_h", "sommeil paradoxal / REM (heures)"),
    ("eveil_min", "temps éveillé pendant la nuit (minutes)"),
    ("respiration", "fréquence respiratoire nocturne moyenne"),
    ("hrv_nuit", "HRV moyenne de la nuit (ms)"),
    ("hrv_7j", "moyenne HRV sur 7 jours (ms)"),
    ("statut_hrv", "statut HRV Garmin (BALANCED, UNBALANCED, LOW...)"),
    ("disposition", "disposition à l'entraînement au réveil (0-100, montres récentes : voir Limites)"),
    ("charge_aigue", "charge aiguë Garmin (7 jours pondérés, montres récentes : voir Limites)"),
    ("charge_chronique", "charge chronique Garmin (~28 jours, montres récentes : voir Limites)"),
    ("ratio_charge", "ratio aiguë/chronique (montres récentes : voir Limites)"),
    ("statut_entrainement", "statut d'entraînement Garmin (montres récentes : voir Limites)"),
    ("vo2max", "VO2max précise (montres récentes : voir Limites ; sinon voir courses.csv)"),
    ("poids_kg", "poids saisi"),
]


def _sante(health) -> list[list]:
    rows = []
    for d, h in health.items():
        mod, vig = h.get("moderate_min"), h.get("vigorous_min")
        rows.append([
            d,
            h["steps"] or "",
            _r(h["active_kcal"], 0),
            (mod or 0) + 2 * (vig or 0) if mod is not None or vig is not None else "",
            h["rhr"] or "",
            h["stress_avg"] if h["stress_avg"] is not None else "",
            h["bb_high"] or "",
            h["bb_low"] if h["bb_low"] is not None else "",
            h["bb_wake"] or "",
            _hours(h["sleep_s"]),
            h["sleep_score"] or "",
            _hours(h["deep_s"]),
            _hours(h["rem_s"]),
            _min(h["awake_s"]),
            _r(h["respiration"], 1),
            h["hrv_night"] or "",
            h["hrv_week"] or "",
            h["hrv_status"] or "",
            h["readiness"] if h["readiness"] is not None else "",
            _r(h["acute_load"], 0),
            _r(h["chronic_load"], 0),
            _r(h["acwr"], 1),
            _status(h["training_status"]),
            _r(h["vo2max"], 1),
            _r(h["weight_kg"], 1),
        ])
    return rows


# --- LISEZMOI ----------------------------------------------------------------

def _records(runs) -> list[str]:
    lines = []
    for key, label, meters in [("fastestSplit_1000", "1 km", 1000), ("fastestSplit_5000", "5 km", 5000),
                               ("fastestSplit_10000", "10 km", 10000),
                               ("fastestSplit_21098", "semi-marathon", 21097.5),
                               ("fastestSplit_42195", "marathon", 42195)]:
        best = min(((a[key], t, a) for t, a in runs if a.get(key)), default=None, key=lambda x: x[0])
        if best:
            s, t, a = best
            lines.append(f"- {label} : {_hms(s)} ({_pace(meters / s)}/km) le {t[:10]} — « {a.get('activityName')} »")
    return lines


def _last_value(health, col, days=30):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    vals = [h[col] for d, h in health.items() if d >= cutoff and h[col] is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _lisezmoi(runs, health, zones, semaines) -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    first, last = runs[0][0][:10], runs[-1][0][:10]
    vo2 = next((h["vo2max"] for d, h in reversed(health.items()) if h["vo2max"]), None)
    vo2_hist = [(t[:7], a["vO2MaxValue"]) for t, a in runs if a.get("vO2MaxValue")]
    vo2_peak = max(vo2_hist, key=lambda x: x[1]) if vo2_hist else None
    weight = next((h["weight_kg"] for d, h in reversed(health.items()) if h["weight_kg"]), None)
    max_hr_seen = round(max((a.get("maxHR") or 0 for _, a in runs), default=0))
    gaps = _wear_gaps(health)
    advanced = next((d for d, h in health.items() if h["readiness"] is not None or h["acute_load"] is not None), None)
    advanced_txt = f"disponibles à partir du {advanced}." if advanced else "non disponibles."

    by_year = defaultdict(lambda: [0, 0.0, 0.0])
    for t, a in runs:
        y = by_year[t[:4]]
        y[0] += 1
        y[1] += (a.get("distance") or 0) / 1000
        y[2] += a.get("elevationGain") or 0

    z = next((z for z in zones if z.get("sport") == "DEFAULT"), zones[0] if zones else None)
    zone_lines = []
    if z:
        floors = [z[f"zone{i}Floor"] for i in range(1, 6)] + [z["maxHeartRateUsed"]]
        names = ["récupération", "endurance fondamentale", "tempo / aérobie", "seuil", "VO2max / anaérobie"]
        zone_lines = [f"- Z{i + 1} ({names[i]}) : {floors[i]}-{floors[i + 1] - (1 if i < 4 else 0)} bpm" for i in range(5)]
        zone_lines.insert(0, f"Méthode Garmin : {z['trainingMethod']}, FC max utilisée {z['maxHeartRateUsed']}, "
                             f"FC seuil lactique {z.get('lactateThresholdHeartRateUsed')}.")

    recent_weeks = semaines[-6:]
    recent_lines = ["| semaine | sorties | km | D+ | allure | charge | % Z1-2 | HRV | sommeil h | statut |",
                    "|---|---|---|---|---|---|---|---|---|---|"]
    for w in recent_weeks:
        recent_lines.append(f"| {w[0]} | {w[1]} | {w[2]} | {w[3]} | {w[5]} | {w[7]} | {w[8]} | {w[11]} | {w[12]} | {w[16]} |")

    def coldoc(cols):
        return "\n".join(f"- `{c}` : {d}" for c, d in cols)

    return f"""# Splinter — données course à pied

Mise à jour : {today}. Export automatique depuis Garmin Connect (projet Splinter).
Données de santé personnelles : ne pas partager.

## À l'attention de Claude

Ces fichiers décrivent l'entraînement de course à pied (route et trail) d'un coureur et ses
données de récupération. Utilise-les pour analyser sa progression, sa charge, sa récupération
et l'aider à planifier. Les CSV sont en UTF-8, séparateur virgule, décimales avec un point.
Les allures sont en min:s par km, les durées en h:mm:ss. Une cellule vide = donnée absente.
Les données couvrent du {first} au {last}.

Fichiers :
- `courses.csv` : une ligne par sortie ({len(runs)} sorties)
- `courses_km.csv` : une ligne par kilomètre de chaque sortie, calculée à partir des
  enregistrements seconde par seconde (évolution de l'allure et de la FC pendant la sortie)
- `semaines.csv` : agrégats hebdomadaires (semaines du lundi au dimanche)
- `sante_quotidienne.csv` : une ligne par jour (sommeil, HRV, FC repos, charge...)

## Profil

- VO2max actuelle (Garmin) : {vo2 or '?'}{f" — pic à {vo2_peak[1]:.0f} en {vo2_peak[0]}" if vo2_peak else ''}
- FC repos moyenne 30 derniers jours : {_last_value(health, 'rhr') or '?'} bpm
- HRV nocturne moyenne 30 derniers jours : {_last_value(health, 'hrv_night') or '?'} ms
- Sommeil moyen 30 derniers jours : {round((_last_value(health, 'sleep_s') or 0) / 3600, 1)} h
- FC max observée en course : {max_hr_seen} bpm
- Dernier poids saisi : {f'{weight:.1f} kg' if weight else '?'}

### Zones cardiaques

{chr(10).join(zone_lines) or 'Non disponibles.'}

### Meilleurs temps (segments les plus rapides détectés par Garmin dans une sortie)

{chr(10).join(_records(runs)) or 'Aucun.'}

### Volume par année

{chr(10).join(f"- {y} : {v[0]} sorties, {v[1]:.0f} km, {v[2]:.0f} m D+" for y, v in sorted(by_year.items()))}

## 6 dernières semaines

{chr(10).join(recent_lines)}

## Limites à connaître

- Disposition à l'entraînement, charge aiguë/chronique, statut d'entraînement et VO2max précise
  quotidienne ne sont calculés que par les montres Garmin récentes : {advanced_txt}
  Sinon, la VO2max est disponible par séance dans `courses.csv`.
- Périodes sans données de sommeil (montre principale non portée la nuit ou pas du tout) :
  {", ".join(gaps) or "aucune"}. Pendant ces périodes les données santé sont absentes ou
  partielles et des sorties ont pu être enregistrées avec une ancienne montre, sans charge
  d'entraînement ni zones fiables. Les FC repos aberrantes (> 1,5 x la médiane) ont été retirées.
- Les meilleurs temps sont des segments à l'intérieur de sorties, pas forcément des courses officielles.
- La température vient du capteur de la montre, au poignet : elle surestime la température de l'air.
- `hrv_nuit_precedente`, `score_sommeil_veille` et `disposition_matin` dans `courses.csv`
  correspondent à la nuit / au matin du jour de la sortie.
- Le découplage et la dérive cardiaque ne sont interprétables que sur des sorties à allure
  régulière : un fractionné ou un parcours vallonné fausse la comparaison des deux moitiés.
  La FC à allure fixe est le meilleur indicateur pour suivre la progression aérobie dans le temps.
- La chaleur fait monter la FC et le découplage : comparer de préférence des périodes de météo
  proche (températures dans `temp_min_c` / `temp_max_c`, imprécises car mesurées au poignet).
- La FC vient du capteur optique au poignet (sauf ceinture) : quelques valeurs aberrantes sont
  possibles, surtout dans les premières minutes.

## Colonnes de courses.csv

{coldoc(COURSES_COLUMNS)}

## Colonnes de courses_km.csv

{coldoc(KM_COLUMNS)}

## Colonnes de semaines.csv

{coldoc(SEMAINES_COLUMNS)}

## Colonnes de sante_quotidienne.csv

{coldoc(SANTE_COLUMNS)}
"""


def export(out_dir: Path = EXPORT_DIR) -> None:
    db = open_db()
    try:
        runs, health, zones, fit_metrics, km_rows = _load(db)
    finally:
        db.close()
    if not runs:
        print("Aucune sortie course à exporter.")
        return
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(out_dir / "courses.csv", [c for c, _ in COURSES_COLUMNS],
               [_course_row(t, a, health, fit_metrics.get(a["activityId"], {})) for t, a in runs])
    _write_csv(out_dir / "courses_km.csv", [c for c, _ in KM_COLUMNS], _km_rows(km_rows, runs))
    semaines = _semaines(runs, health)
    _write_csv(out_dir / "semaines.csv", [c for c, _ in SEMAINES_COLUMNS], semaines)
    _write_csv(out_dir / "sante_quotidienne.csv", [c for c, _ in SANTE_COLUMNS], _sante(health))
    (out_dir / "LISEZMOI.md").write_text(_lisezmoi(runs, health, zones, semaines), encoding="utf-8")
    print(f"Export Claude : {out_dir} ({len(runs)} sorties, {len(semaines)} semaines, {len(health)} jours)")
    print(f"  dernière sortie : {runs[-1][0][:16]} ; dernier jour santé : {max(health) if health else '-'}")


if __name__ == "__main__":
    export()
