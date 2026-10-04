"""Synchronisation des activités Garmin Connect.

- Métadonnées des activités -> table `activities` de Data/garmin.db
- Fichiers d'origine (.fit)  -> Data/fit/<activity_id>.fit
"""

import io
import json
import sqlite3
import time
import zipfile
from pathlib import Path

from garminconnect import Garmin, GarminConnectNotFoundError, GarminConnectTooManyRequestsError

from splinter.config import FIT_DIR

PAGE_SIZE = 100
DOWNLOAD_PAUSE_S = 0.5  # pause entre téléchargements pour ménager l'API

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id     INTEGER PRIMARY KEY,
    start_time      TEXT,      -- heure locale, 'YYYY-MM-DD HH:MM:SS'
    start_time_gmt  TEXT,
    name            TEXT,
    type_key        TEXT,      -- running, cycling, lap_swimming, ...
    distance_m      REAL,
    duration_s      REAL,
    moving_s        REAL,
    elevation_gain  REAL,
    avg_hr          REAL,
    max_hr          REAL,
    calories        REAL,
    raw_json        TEXT NOT NULL,
    fit_status      TEXT       -- NULL = à télécharger, 'ok', 'none' (pas de fichier)
);
CREATE INDEX IF NOT EXISTS idx_activities_start ON activities(start_time);
"""


def init_schema(db: sqlite3.Connection) -> None:
    FIT_DIR.mkdir(parents=True, exist_ok=True)
    db.executescript(SCHEMA)


def upsert_activity(db: sqlite3.Connection, a: dict) -> None:
    db.execute(
        """
        INSERT INTO activities (activity_id, start_time, start_time_gmt, name, type_key,
            distance_m, duration_s, moving_s, elevation_gain, avg_hr, max_hr, calories, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(activity_id) DO UPDATE SET
            start_time=excluded.start_time, start_time_gmt=excluded.start_time_gmt,
            name=excluded.name, type_key=excluded.type_key, distance_m=excluded.distance_m,
            duration_s=excluded.duration_s, moving_s=excluded.moving_s,
            elevation_gain=excluded.elevation_gain, avg_hr=excluded.avg_hr,
            max_hr=excluded.max_hr, calories=excluded.calories, raw_json=excluded.raw_json
        """,
        (
            a["activityId"],
            a.get("startTimeLocal"),
            a.get("startTimeGMT"),
            a.get("activityName"),
            (a.get("activityType") or {}).get("typeKey"),
            a.get("distance"),
            a.get("duration"),
            a.get("movingDuration"),
            a.get("elevationGain"),
            a.get("averageHR"),
            a.get("maxHR"),
            a.get("calories"),
            json.dumps(a, ensure_ascii=False),
        ),
    )


def sync_activities(api: Garmin, db: sqlite3.Connection, full: bool) -> int:
    """Parcourt les activités de la plus récente à la plus ancienne.

    En mode incrémental, s'arrête dès qu'une page ne contient que des activités connues.
    """
    known = {row[0] for row in db.execute("SELECT activity_id FROM activities")}
    if not known:
        full = True
    if full:
        print(f"Synchro complète : {api.count_activities()} activités sur le compte.")

    start, new = 0, 0
    while True:
        page = api.get_activities(start, PAGE_SIZE)
        if not page:
            break
        page_new = 0
        for a in page:
            if a["activityId"] not in known:
                page_new += 1
                print(f"  + {(a.get('startTimeLocal') or '')[:16]} {(a.get('activityType') or {}).get('typeKey')} "
                      f"« {a.get('activityName')} » {(a.get('distance') or 0) / 1000:.1f} km")
            upsert_activity(db, a)
        db.commit()
        new += page_new
        print(f"  activités {start + 1}-{start + len(page)} : {page_new} nouvelles")
        if not full and page_new == 0:
            break
        start += len(page)
    return new


def download_fits(api: Garmin, db: sqlite3.Connection) -> None:
    todo = [
        r[0]
        for r in db.execute(
            "SELECT activity_id FROM activities WHERE fit_status IS NULL ORDER BY start_time DESC"
        )
    ]
    if not todo:
        return
    print(f"Téléchargement de {len(todo)} fichiers .fit ...")
    for i, activity_id in enumerate(todo, 1):
        try:
            blob = api.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            status = save_original(activity_id, blob)
        except GarminConnectNotFoundError:
            status = "none"  # activité manuelle, sans fichier
        except GarminConnectTooManyRequestsError:
            print("Limite de requêtes Garmin atteinte : relance le script plus tard pour continuer.")
            break
        db.execute("UPDATE activities SET fit_status=? WHERE activity_id=?", (status, activity_id))
        db.commit()
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}")
        time.sleep(DOWNLOAD_PAUSE_S)


def save_original(activity_id: int, blob: bytes) -> str:
    """Le format ORIGINAL est un zip contenant en général un seul .fit."""
    if not blob:
        return "none"
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            members = [m for m in z.namelist() if not m.endswith("/")]
            if not members:
                return "none"
            for n, member in enumerate(members):
                suffix = Path(member).suffix.lower() or ".fit"
                name = f"{activity_id}{'' if n == 0 else f'_{n}'}{suffix}"
                (FIT_DIR / name).write_bytes(z.read(member))
    except zipfile.BadZipFile:
        (FIT_DIR / f"{activity_id}.fit").write_bytes(blob)
    return "ok"
