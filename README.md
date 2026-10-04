# Splinter

Analyse locale de l'historique sportif Garmin Connect.

## Organisation

```
Sport/
├── Splinter/          # ce dépôt git (code uniquement)
│   └── splinter/
│       ├── config.py        # chemins du projet
│       └── garmin_sync.py   # connecteur Garmin Connect
└── Data/              # données et infos sensibles, hors git
    ├── garmin.db          # base SQLite des activités
    ├── fit/               # fichiers .fit d'origine
    └── garmin_tokens/     # jetons de connexion Garmin
```

Le dossier de données peut être déplacé via la variable d'environnement `SPLINTER_DATA`.

## Installation

```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Synchronisation Garmin

```
.venv\Scripts\python -m splinter.garmin_sync
```

La première fois, le script demande email, mot de passe et code MFA éventuel
(jamais stockés ; seuls les jetons OAuth sont conservés dans `Data/garmin_tokens`).
Les exécutions suivantes ne récupèrent que les nouvelles activités.
Options : `--full` (reparcourir tout l'historique), `--no-fit` (sans les fichiers .fit).
