"""Connexion à Garmin Connect et accès à la base locale."""

import getpass
import sqlite3

from garminconnect import Garmin

from splinter.config import DATA_DIR, DB_PATH, TOKEN_DIR


def connect() -> Garmin:
    """Connexion via jetons sauvegardés, sinon via email/mot de passe (+ MFA).

    Les identifiants ne sont jamais stockés : seuls les jetons OAuth sont conservés
    dans Data/garmin_tokens.
    """
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        api = Garmin()
        api.login(str(TOKEN_DIR))
        return api
    except Exception:  # pas de jetons, ou jetons invalides/expirés
        pass

    print("Première connexion (ou jetons expirés) : identifiants Garmin Connect requis.")
    email = input("Email : ").strip()
    password = getpass.getpass("Mot de passe : ")
    api = Garmin(email, password, prompt_mfa=lambda: input("Code MFA : ").strip())
    api.login(str(TOKEN_DIR))
    print(f"Connecté. Jetons enregistrés dans {TOKEN_DIR}")
    return api


def open_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)
