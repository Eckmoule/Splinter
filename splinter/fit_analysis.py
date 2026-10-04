"""Analyse seconde par seconde des sorties course à partir des fichiers .fit.

Pour chaque sortie (route, trail...) dont le .fit est disponible, calcule et met en cache :
- `run_km`          : une ligne par kilomètre (allure, FC, D+/D-, cadence, puissance)
- `run_fit_metrics` : indicateurs de la sortie (dérive cardiaque, découplage, FC à allure fixe)

Les résultats sont versionnés : si ANALYSIS_VERSION change, tout est recalculé.
"""

import sqlite3
from dataclasses import dataclass

import fitdecode

from splinter.config import FIT_DIR

ANALYSIS_VERSION = 1
RUN_TYPES = ("running", "trail_running", "treadmill_running", "track_running", "indoor_running")

MAX_DT_S = 10           # écart entre deux points au-delà duquel on considère une pause
MOVING_SPEED = 0.5      # m/s : en dessous, on est à l'arrêt
MIN_LAST_KM_M = 200     # dernier kilomètre partiel gardé s'il fait au moins 200 m
ALT_HYSTERESIS_M = 1.0  # seuil anti-bruit pour le cumul de dénivelé
WARMUP_S = 5 * 60       # début de sortie ignoré pour la dérive (temps de montée de la FC)
MIN_DRIFT_S = 30 * 60   # durée minimale (hors échauffement) pour calculer la dérive
FIXED_PACE_BAND = (6 * 60, 6 * 60 + 30)  # allure de référence en s/km : 6:00-6:30
FLAT_GRADE = 0.02       # |pente| max pour la FC à allure fixe
GRADE_WINDOW = 10       # points pour estimer la pente
MIN_BAND_S = 5 * 60     # temps minimal dans la bande d'allure pour donner une valeur

SCHEMA = """
CREATE TABLE IF NOT EXISTS run_km (
    activity_id  INTEGER NOT NULL,
    km           INTEGER NOT NULL,   -- 1 = premier kilomètre
    distance_m   REAL,               -- 1000 sauf pour le dernier, partiel
    moving_s     REAL,
    hr_avg       REAL,
    hr_max       INTEGER,
    ascent_m     REAL,
    descent_m    REAL,
    cadence_spm  REAL,
    power_w      REAL,
    PRIMARY KEY (activity_id, km)
);
CREATE TABLE IF NOT EXISTS run_fit_metrics (
    activity_id        INTEGER PRIMARY KEY,
    version            INTEGER NOT NULL,
    hr_first_half      REAL,   -- FC moyenne 1re moitié (hors échauffement)
    hr_second_half     REAL,
    speed_first_half   REAL,   -- m/s
    speed_second_half  REAL,
    power_first_half   REAL,
    power_second_half  REAL,
    decoupling_pct     REAL,   -- découplage allure/FC (Pa:HR)
    power_decoupling_pct REAL, -- découplage puissance/FC (Pw:HR)
    hr_fixed_pace      REAL,   -- FC moyenne sur le plat à allure FIXED_PACE_BAND
    fixed_pace_s       REAL    -- temps passé dans cette bande
);
"""


@dataclass
class Point:
    t: float          # secondes depuis le début
    dt: float         # temps « en mouvement » attribué à ce point
    dist: float | None
    speed: float | None
    alt: float | None
    hr: int | None
    cadence: float | None
    power: float | None


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def read_points(path) -> list[Point]:
    points: list[Point] = []
    t0 = prev = None
    with fitdecode.FitReader(str(path), check_crc=fitdecode.CrcCheck.DISABLED) as fr:
        for frame in fr:
            if not (isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record"):
                continue
            v = {f.name: f.value for f in frame.fields}
            ts = v.get("timestamp")
            if ts is None:
                continue
            t0 = t0 or ts
            t = (ts - t0).total_seconds()
            dt = 0.0 if prev is None else t - prev
            prev = t
            speed = v.get("enhanced_speed", v.get("speed"))
            if dt > MAX_DT_S or (speed is not None and speed < MOVING_SPEED):
                dt = 0.0  # pause ou arrêt
            cad = v.get("cadence")
            if cad is not None:
                cad = 2 * (cad + (v.get("fractional_cadence") or 0))  # FIT : foulées/min par jambe
            points.append(Point(
                t=t, dt=dt, dist=v.get("distance"), speed=speed,
                alt=v.get("enhanced_altitude", v.get("altitude")),
                hr=v.get("heart_rate") or None, cadence=cad or None, power=v.get("power") or None,
            ))
    return points


def _wavg(pairs) -> float | None:
    """Moyenne pondérée par le temps : pairs = [(valeur, dt)]."""
    num = sum(v * w for v, w in pairs if v is not None and w > 0)
    den = sum(w for v, w in pairs if v is not None and w > 0)
    return num / den if den else None


def _elevation(alts: list[float]) -> tuple[float, float]:
    """D+ / D- avec hystérésis pour ne pas cumuler le bruit de l'altimètre."""
    up = down = 0.0
    anchor = None
    for a in alts:
        if a is None:
            continue
        if anchor is None:
            anchor = a
        elif a - anchor >= ALT_HYSTERESIS_M:
            up += a - anchor
            anchor = a
        elif anchor - a >= ALT_HYSTERESIS_M:
            down += anchor - a
            anchor = a
    return up, down


def km_splits(points: list[Point]) -> list[dict]:
    buckets: dict[int, list[Point]] = {}
    for p in points:
        if p.dist is not None:
            buckets.setdefault(int(p.dist // 1000), []).append(p)
    splits = []
    last_dist = max((p.dist for p in points if p.dist is not None), default=0)
    for k in sorted(buckets):
        pts = buckets[k]
        dist = min(1000.0, last_dist - k * 1000)
        if dist < 1000 and dist < MIN_LAST_KM_M:
            continue
        up, down = _elevation([p.alt for p in pts])
        hrs = [p.hr for p in pts if p.hr]
        splits.append({
            "km": k + 1,
            "distance_m": round(dist, 1),
            "moving_s": round(sum(p.dt for p in pts), 1),
            "hr_avg": _wavg([(p.hr, p.dt) for p in pts]),
            "hr_max": max(hrs) if hrs else None,
            "ascent_m": round(up, 1),
            "descent_m": round(down, 1),
            "cadence_spm": _wavg([(p.cadence, p.dt) for p in pts]),
            "power_w": _wavg([(p.power, p.dt) for p in pts]),
        })
    return splits


def _decoupling(first: float | None, second: float | None, hr1: float | None, hr2: float | None):
    """(EF1 - EF2) / EF1 en %, avec EF = output / FC. Positif = la FC dérive."""
    if not (first and second and hr1 and hr2):
        return None
    ef1, ef2 = first / hr1, second / hr2
    return 100 * (ef1 - ef2) / ef1


def run_metrics(points: list[Point]) -> dict:
    m: dict = {}
    # --- dérive : on coupe le temps en mouvement (hors échauffement) en deux moitiés
    moving, acc = [], 0.0
    for p in points:
        acc += p.dt
        if acc > WARMUP_S and p.dt > 0:
            moving.append(p)
    total = sum(p.dt for p in moving)
    if total >= MIN_DRIFT_S:
        half, acc, first, second = total / 2, 0.0, [], []
        for p in moving:
            (first if acc < half else second).append(p)
            acc += p.dt
        for name, attr in (("hr", "hr"), ("speed", "speed"), ("power", "power")):
            m[f"{name}_first_half"] = _wavg([(getattr(p, attr), p.dt) for p in first])
            m[f"{name}_second_half"] = _wavg([(getattr(p, attr), p.dt) for p in second])
        m["decoupling_pct"] = _decoupling(m["speed_first_half"], m["speed_second_half"],
                                          m["hr_first_half"], m["hr_second_half"])
        m["power_decoupling_pct"] = _decoupling(m["power_first_half"], m["power_second_half"],
                                                m["hr_first_half"], m["hr_second_half"])

    # --- FC moyenne sur le plat dans la bande d'allure de référence
    lo, hi = FIXED_PACE_BAND
    band = []
    acc = 0.0
    for i, p in enumerate(points):
        acc += p.dt
        if acc <= WARMUP_S or not (p.dt and p.speed and p.hr):
            continue
        pace = 1000 / p.speed
        j = max(0, i - GRADE_WINDOW)
        q = points[j]
        if p.alt is None or q.alt is None or p.dist is None or q.dist is None or p.dist - q.dist < 5:
            continue
        grade = (p.alt - q.alt) / (p.dist - q.dist)
        if lo <= pace <= hi and abs(grade) <= FLAT_GRADE:
            band.append(p)
    band_s = sum(p.dt for p in band)
    m["fixed_pace_s"] = band_s
    m["hr_fixed_pace"] = _wavg([(p.hr, p.dt) for p in band]) if band_s >= MIN_BAND_S else None
    return m


def process(db: sqlite3.Connection) -> int:
    """Analyse les sorties dont le .fit n'a pas encore été traité (ou avec une ancienne version)."""
    init_schema(db)
    placeholders = ",".join("?" * len(RUN_TYPES))
    todo = [r[0] for r in db.execute(
        f"""SELECT a.activity_id FROM activities a
            LEFT JOIN run_fit_metrics m ON m.activity_id = a.activity_id
            WHERE a.type_key IN ({placeholders}) AND a.fit_status = 'ok'
              AND (m.version IS NULL OR m.version < ?)
            ORDER BY a.start_time""",
        (*RUN_TYPES, ANALYSIS_VERSION),
    )]
    if not todo:
        return 0
    print(f"Analyse des fichiers .fit : {len(todo)} sorties ...")
    cols = ["hr_first_half", "hr_second_half", "speed_first_half", "speed_second_half",
            "power_first_half", "power_second_half", "decoupling_pct", "power_decoupling_pct",
            "hr_fixed_pace", "fixed_pace_s"]
    for i, aid in enumerate(todo, 1):
        path = FIT_DIR / f"{aid}.fit"
        try:
            points = read_points(path)
        except (OSError, fitdecode.FitError) as e:
            print(f"  {aid} : lecture impossible ({e})")
            continue
        db.execute("DELETE FROM run_km WHERE activity_id=?", (aid,))
        db.executemany(
            """INSERT INTO run_km (activity_id, km, distance_m, moving_s, hr_avg, hr_max,
                   ascent_m, descent_m, cadence_spm, power_w) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [(aid, s["km"], s["distance_m"], s["moving_s"], s["hr_avg"], s["hr_max"],
              s["ascent_m"], s["descent_m"], s["cadence_spm"], s["power_w"]) for s in km_splits(points)],
        )
        m = run_metrics(points)
        db.execute(
            f"INSERT OR REPLACE INTO run_fit_metrics (activity_id, version, {', '.join(cols)}) "
            f"VALUES (?, ?, {', '.join('?' * len(cols))})",
            (aid, ANALYSIS_VERSION, *[m.get(c) for c in cols]),
        )
        if i % 25 == 0 or i == len(todo):
            db.commit()
            print(f"  {i}/{len(todo)}")
    db.commit()
    return len(todo)
