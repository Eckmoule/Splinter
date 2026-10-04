"""Chemins du projet.

Les données et infos sensibles vivent dans le dossier Data, à côté du dépôt
(../Data), jamais dans git. Surchargeable via la variable d'env SPLINTER_DATA.
"""

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SPLINTER_DATA", REPO_DIR.parent / "Data")).resolve()

DB_PATH = DATA_DIR / "garmin.db"        # base SQLite des activités
FIT_DIR = DATA_DIR / "fit"              # fichiers .fit d'origine
TOKEN_DIR = DATA_DIR / "garmin_tokens"  # jetons OAuth Garmin Connect
