"""Synchronisation des données santé quotidiennes Garmin Connect.

- Réponses brutes de l'API -> table `health_raw` (une ligne par jour et par type)
- Indicateurs clés         -> table `daily_health` (une ligne par jour, reconstruite
                              à chaque synchro à partir de `health_raw`)
"""

import json
import sqlite3
import time
from datetime import date, datetime, timedelta

from garminconnect import Garmin, GarminConnectConnectionError, GarminConnectTooManyRequestsError

REQUEST_PAUSE_S = 0.2
RECENT_DAYS = 3        # jours récents toujours re-téléchargés (données encore en mouvement)
HRV_MAX_RANGE = 365    # limite de l'API HRV par requête
MAX_CONSECUTIVE_ERRORS = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS health_raw (
    date        TEXT NOT NULL,  -- 'YYYY-MM-DD'
    kind        TEXT NOT NULL,  -- summary, sleep, hrv, weight, training_readiness, training_status
    raw_json    TEXT,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (date, kind)
);
-- réglages du profil (zones cardiaques...), une ligne par clé
CREATE TABLE IF NOT EXISTS profile (
    key         TEXT PRIMARY KEY,
    raw_json    TEXT,
    fetched_at  TEXT NOT NULL
);
-- période déjà couverte par les endpoints « plage de dates »
CREATE TABLE IF NOT EXISTS health_sync_state (
    kind          TEXT PRIMARY KEY,
    covered_from  TEXT NOT NULL
);
"""

# Endpoints interrogés jour par jour (pas de version « plage de dates »).
PER_DAY = {
    "summary": lambda api, d: api.get_user_summary(d),
    "training_readiness": lambda api, d: api.get_training_readiness(d),
    "training_status": lambda api, d: api.get_training_status(d),
}

DAILY_COLUMNS = {
    # activité de la journée
    "steps": "INTEGER", "active_kcal": "REAL", "total_kcal": "REAL",
    "moderate_min": "INTEGER", "vigorous_min": "INTEGER",
    # cœur, stress, énergie
    "rhr": "INTEGER", "min_hr": "INTEGER", "max_hr": "INTEGER",
    "stress_avg": "INTEGER", "bb_high": "INTEGER", "bb_low": "INTEGER", "bb_wake": "INTEGER",
    # sommeil
    "sleep_s": "INTEGER", "sleep_score": "INTEGER", "deep_s": "INTEGER", "light_s": "INTEGER",
    "rem_s": "INTEGER", "awake_s": "INTEGER", "sleep_hr": "REAL", "spo2": "REAL",
    "respiration": "REAL", "skin_temp_dev_c": "REAL", "sleep_bb_change": "INTEGER",
    # HRV
    "hrv_night": "INTEGER", "hrv_week": "INTEGER", "hrv_status": "TEXT",
    # forme et charge
    "readiness": "INTEGER", "readiness_level": "TEXT", "training_status": "TEXT",
    "acute_load": "REAL", "chronic_load": "REAL", "acwr": "REAL", "vo2max": "REAL",
    # poids
    "weight_kg": "REAL",
}


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def _store(db: sqlite3.Connection, d: str, kind: str, payload) -> None:
    db.execute(
        "INSERT OR REPLACE INTO health_raw (date, kind, raw_json, fetched_at) VALUES (?, ?, ?, ?)",
        (d, kind, json.dumps(payload, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
    )


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _range_start(db: sqlite3.Connection, kind: str, since: date) -> date:
    """Reprend au dernier jour connu (moins une marge), ou à `since` si l'historique
    demandé remonte plus loin que ce qui a déjà été couvert."""
    row = db.execute("SELECT covered_from FROM health_sync_state WHERE kind=?", (kind,)).fetchone()
    if row is None or since < date.fromisoformat(row[0]):
        return since
    last = db.execute("SELECT MAX(date) FROM health_raw WHERE kind=?", (kind,)).fetchone()[0]
    if last is None:
        return since
    return max(since, date.fromisoformat(last) - timedelta(days=RECENT_DAYS))


def _mark_covered(db: sqlite3.Connection, kind: str, since: date) -> None:
    db.execute(
        """INSERT INTO health_sync_state (kind, covered_from) VALUES (?, ?)
           ON CONFLICT(kind) DO UPDATE SET covered_from=MIN(covered_from, excluded.covered_from)""",
        (kind, since.isoformat()),
    )


def sync_profile(api: Garmin, db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT OR REPLACE INTO profile (key, raw_json, fetched_at) VALUES (?, ?, ?)",
        ("hr_zones", json.dumps(api.get_heart_rate_zones()), datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()


def sync_ranges(api: Garmin, db: sqlite3.Connection, since: date, today: date) -> None:
    """Sommeil, HRV et poids : endpoints acceptant une plage de dates."""
    start = _range_start(db, "sleep", since)
    rows = api.get_sleep_daily(start.isoformat(), today.isoformat())
    for r in rows:
        _store(db, r["calendarDate"], "sleep", r.get("values"))
    _mark_covered(db, "sleep", since)
    print(f"  sommeil : {len(rows)} nuits depuis le {start}")

    start = _range_start(db, "hrv", since)
    n = 0
    while start <= today:
        end = min(start + timedelta(days=HRV_MAX_RANGE - 1), today)
        data = api.get_hrv_data_range(start.isoformat(), end.isoformat()) or {}
        for r in data.get("hrvSummaries") or []:
            _store(db, r["calendarDate"], "hrv", r)
            n += 1
        start = end + timedelta(days=1)
        time.sleep(REQUEST_PAUSE_S)
    _mark_covered(db, "hrv", since)
    print(f"  HRV : {n} nuits")

    start = _range_start(db, "weight", since)
    data = api.get_weigh_ins(start.isoformat(), today.isoformat()) or {}
    rows = data.get("dailyWeightSummaries") or []
    for r in rows:
        _store(db, r["summaryDate"], "weight", r)
    _mark_covered(db, "weight", since)
    print(f"  poids : {len(rows)} pesées")
    db.commit()


def sync_per_day(api: Garmin, db: sqlite3.Connection, since: date, today: date) -> None:
    """Résumé quotidien, disposition à l'entraînement, statut d'entraînement."""
    done = set(db.execute("SELECT date, kind FROM health_raw"))
    recent = (today - timedelta(days=RECENT_DAYS)).isoformat()
    todo = [
        (d.isoformat(), kind)
        for d in _days(since, today)
        for kind in PER_DAY
        if (d.isoformat(), kind) not in done or d.isoformat() >= recent
    ]
    if not todo:
        return
    print(f"  données journalières : {len(todo)} requêtes")
    errors = 0
    for i, (d, kind) in enumerate(todo, 1):
        try:
            _store(db, d, kind, PER_DAY[kind](api, d))
            errors = 0
        except GarminConnectTooManyRequestsError:
            print("Limite de requêtes Garmin atteinte : relance la synchro plus tard pour continuer.")
            break
        except GarminConnectConnectionError as e:
            # non enregistré : sera retenté à la prochaine synchro
            errors += 1
            print(f"    {d} {kind} : {e}")
            if errors >= MAX_CONSECUTIVE_ERRORS:
                print("Trop d'erreurs consécutives, arrêt.")
                break
        if i % 100 == 0 or i == len(todo):
            db.commit()
            print(f"    {i}/{len(todo)}")
        time.sleep(REQUEST_PAUSE_S)
    db.commit()


def _primary_device_entry(by_device: dict | None) -> dict:
    """Les statuts d'entraînement sont indexés par montre : garde la principale."""
    entries = list((by_device or {}).values())
    for e in entries:
        if e.get("primaryTrainingDevice"):
            return e
    return entries[0] if entries else {}


def _morning_readiness(entries: list | None) -> dict:
    """Plusieurs scores par jour : on garde celui du réveil, sinon le plus ancien."""
    entries = entries or []
    for e in entries:
        if e.get("inputContext") == "AFTER_WAKEUP_RESET":
            return e
    return min(entries, key=lambda e: e.get("timestampLocal") or "", default={})


def _daily_row(raw: dict) -> dict:
    s = raw.get("summary") or {}
    sl = raw.get("sleep") or {}
    hrv = raw.get("hrv") or {}
    rd = _morning_readiness(raw.get("training_readiness"))
    ts_root = raw.get("training_status") or {}
    ts = _primary_device_entry((ts_root.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData"))
    acute = ts.get("acuteTrainingLoadDTO") or {}
    vo2 = (ts_root.get("mostRecentVO2Max") or {}).get("generic") or {}
    weight = ((raw.get("weight") or {}).get("latestWeight") or {}).get("weight")
    return {
        "steps": s.get("totalSteps"),
        "active_kcal": s.get("activeKilocalories"),
        "total_kcal": s.get("totalKilocalories"),
        "moderate_min": s.get("moderateIntensityMinutes"),
        "vigorous_min": s.get("vigorousIntensityMinutes"),
        "rhr": s.get("restingHeartRate") or sl.get("restingHeartRate"),
        "min_hr": s.get("minHeartRate"),
        "max_hr": s.get("maxHeartRate"),
        "stress_avg": s.get("averageStressLevel") if (s.get("averageStressLevel") or -1) >= 0 else None,
        "bb_high": s.get("bodyBatteryHighestValue"),
        "bb_low": s.get("bodyBatteryLowestValue"),
        "bb_wake": s.get("bodyBatteryAtWakeTime"),
        "sleep_s": sl.get("totalSleepTimeInSeconds"),
        "sleep_score": sl.get("sleepScore"),
        "deep_s": sl.get("deepTime"),
        "light_s": sl.get("lightTime"),
        "rem_s": sl.get("remTime"),
        "awake_s": sl.get("awakeTime"),
        "sleep_hr": sl.get("avgHeartRate"),
        "spo2": sl.get("spO2"),
        "respiration": sl.get("respiration"),
        "skin_temp_dev_c": sl.get("skinTempC"),
        "sleep_bb_change": sl.get("bodyBatteryChange"),
        "hrv_night": hrv.get("lastNightAvg") or sl.get("avgOvernightHrv"),
        "hrv_week": hrv.get("weeklyAvg") or sl.get("hrv7dAverage"),
        "hrv_status": hrv.get("status") or sl.get("hrvStatus"),
        "readiness": rd.get("score"),
        "readiness_level": rd.get("level"),
        "training_status": ts.get("trainingStatusFeedbackPhrase"),
        "acute_load": acute.get("dailyTrainingLoadAcute"),
        "chronic_load": acute.get("dailyTrainingLoadChronic"),
        "acwr": acute.get("dailyAcuteChronicWorkloadRatio"),
        "vo2max": vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue"),
        "weight_kg": weight / 1000 if weight else None,
    }


def rebuild_daily(db: sqlite3.Connection) -> int:
    """Reconstruit la table `daily_health` à partir des réponses brutes."""
    by_date: dict[str, dict] = {}
    for d, kind, raw_json in db.execute("SELECT date, kind, raw_json FROM health_raw"):
        by_date.setdefault(d, {})[kind] = json.loads(raw_json) if raw_json else None

    cols = list(DAILY_COLUMNS)
    db.execute("DROP TABLE IF EXISTS daily_health")
    db.execute(
        "CREATE TABLE daily_health (date TEXT PRIMARY KEY, "
        + ", ".join(f"{c} {t}" for c, t in DAILY_COLUMNS.items())
        + ")"
    )
    rows = []
    for d in sorted(by_date):
        row = _daily_row(by_date[d])
        if any(v is not None for v in row.values()):
            rows.append([d] + [row[c] for c in cols])
    db.executemany(
        f"INSERT INTO daily_health (date, {', '.join(cols)}) VALUES ({', '.join('?' * (len(cols) + 1))})",
        rows,
    )
    db.commit()
    return len(rows)


def _nights(db: sqlite3.Connection) -> set[str]:
    """Jours pour lesquels une nuit de sommeil est enregistrée."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='daily_health'").fetchone():
        return set()
    return {r[0] for r in db.execute("SELECT date FROM daily_health WHERE sleep_s IS NOT NULL")}


def _log_new_nights(db: sqlite3.Connection, before: set[str]) -> None:
    new = sorted(_nights(db) - before)
    print(f"  nouvelles nuits : {len(new)}")
    for d in new[-14:]:
        h = db.execute("SELECT sleep_s, sleep_score, hrv_night, rhr, readiness FROM daily_health WHERE date=?",
                       (d,)).fetchone()
        sleep_s, score, hrv, rhr, readiness = h
        print(f"  + {d} : sommeil {sleep_s // 3600}h{sleep_s % 3600 // 60:02d} (score {score}), "
              f"HRV {hrv}, FC repos {rhr}, disposition {readiness}")


def sync_health(api: Garmin, db: sqlite3.Connection, since: date) -> None:
    today = date.today()
    print(f"Données santé depuis le {since} ...")
    before = _nights(db)
    sync_profile(api, db)
    sync_ranges(api, db, since, today)
    sync_per_day(api, db, since, today)
    n = rebuild_daily(db)
    print(f"  daily_health : {n} jours")
    _log_new_nights(db, before)
