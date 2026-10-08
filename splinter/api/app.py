"""API locale du dashboard : lit Data/garmin.db (lecture seule) et sert l'interface web compilée.

Les indicateurs sont calculés dans splinter.api.metrics.
"""

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
