"""API locale du dashboard : lit Data/garmin.db (lecture seule) et sert l'interface web compilée.

Les indicateurs sont calculés dans splinter.api.metrics.
"""

import os
import sqlite3
import subprocess
import sys
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from splinter import sync_state
from splinter.api import metrics
from splinter.config import DB_PATH, REPO_DIR

WEB_DIST = REPO_DIR / "web" / "dist"

app = FastAPI(title="Splinter", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.get("/api/progression")
def progression() -> dict:
    """Page Progression : FC à allure fixe, efficacité, VO2max, découplage, FC repos, HRV, volume."""
    return metrics.progression(DB_PATH)


@app.get("/api/training")
def training(months: int = Query(3, ge=1, le=24)) -> dict:
    """Page Entraînement : résumé, charge (Forme / Fatigue / Fraîcheur), récupération, tendances."""
    return metrics.training(DB_PATH, months)


# --- synchro Garmin depuis le dashboard ----------------------------------------------------------

@app.get("/api/sync")
def sync_status() -> dict:
    """Dernière synchro (réussie ou non), synchro en cours, données les plus récentes en base."""
    state = sync_state.read_state()
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as db:
        last_run = db.execute("SELECT MAX(start_time) FROM activities").fetchone()[0]
        last_day = db.execute("SELECT MAX(date) FROM daily_health").fetchone()[0]
    return {**state, "running": sync_state.running_pid() is not None, "last_run": last_run, "last_health_day": last_day}


@app.post("/api/sync", status_code=202)
def start_sync() -> dict:
    """Lance `python -m splinter.sync` en arrière-plan (récupération Garmin + export Drive)."""
    if sync_state.running_pid():
        raise HTTPException(409, "Une synchro est déjà en cours.")
    sync_state.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = sync_state.LOG_FILE.open("a", encoding="utf-8")
    log.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} — synchro lancée depuis le dashboard =====\n")
    log.flush()
    subprocess.Popen(
        [sys.executable, "-m", "splinter.sync"],
        cwd=REPO_DIR, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log.close()  # le processus enfant garde sa propre copie du descripteur
    return {"started": True}


# --- interface compilée (web/dist), routage par ancre (#/page) côté client ---------------------

if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    target = (WEB_DIST / path).resolve()
    if path and target.is_file() and WEB_DIST.resolve() in target.parents:
        return FileResponse(target)
    index = WEB_DIST / "index.html"
    if index.is_file():
        # toujours revalidé : après une recompilation, le navigateur charge les nouveaux fichiers
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return {"erreur": "Interface non compilée : lancer `python -m splinter.dashboard` (compile web/ au besoin)."}
