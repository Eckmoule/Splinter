"""Synchronise Garmin Connect vers la base locale Data/garmin.db.

Usage (depuis le dossier Splinter) :
    python -m splinter.sync               # incrémental : activités + santé
    python -m splinter.sync --full        # reparcourt toute la liste des activités
    python -m splinter.sync --no-fit      # sans télécharger les fichiers .fit
    python -m splinter.sync --no-health   # activités seulement
    python -m splinter.sync --no-export   # sans régénérer l'export pour Claude
    python -m splinter.sync --since 2024-01-01   # début de l'historique santé
"""

import argparse
import sys
from datetime import date

from garminconnect import GarminConnectAuthenticationError

from splinter import activities, export, fit_analysis, health
from splinter.sync_state import AlreadyRunning, sync_run
from splinter.config import DB_PATH
from splinter.garmin_client import connect, open_db


def _default_since(db) -> date:
    """Par défaut, l'historique santé démarre à la première activité."""
    first = db.execute("SELECT MIN(start_time) FROM activities").fetchone()[0]
    return date.fromisoformat(first[:10]) if first else date.today()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="reparcourir toute la liste des activités")
    parser.add_argument("--no-fit", action="store_true", help="ne pas télécharger les fichiers .fit")
    parser.add_argument("--no-health", action="store_true", help="ne pas synchroniser les données santé")
    parser.add_argument("--no-export", action="store_true", help="ne pas régénérer l'export pour Claude")
    parser.add_argument("--since", type=date.fromisoformat, help="début de l'historique santé (AAAA-MM-JJ)")
    args = parser.parse_args()

    # une seule synchro à la fois (commande, tâche de nuit ou dashboard) ; résultat mémorisé
    try:
        with sync_run():
            _sync(args)
    except AlreadyRunning as e:
        sys.exit(str(e))


def _sync(args) -> None:
    try:
        api = connect()
    except GarminConnectAuthenticationError as e:
        sys.exit(f"Échec de connexion : {e}")

    db = open_db()
    try:
        activities.init_schema(db)
        health.init_schema(db)

        new = activities.sync_activities(api, db, args.full)
        print(f"{new} nouvelle(s) activité(s).")
        if not args.no_fit:
            activities.download_fits(api, db)
        fit_analysis.process(db)

        if not args.no_health:
            health.sync_health(api, db, args.since or _default_since(db))

        total = db.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        print(f"Base : {DB_PATH} ({total} activités)")
    finally:
        db.close()

    if not args.no_export:
        export.export()


if __name__ == "__main__":
    main()
