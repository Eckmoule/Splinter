# Splinter

Analyse locale de l'historique sportif Garmin Connect.

## Organisation

```
Sport/
├── Splinter/          # ce dépôt git (code uniquement)
│   └── splinter/
│       ├── config.py         # chemins du projet
│       ├── garmin_client.py  # connexion Garmin Connect + base locale
│       ├── activities.py     # synchro des activités et fichiers .fit
│       ├── health.py         # synchro des données santé quotidiennes
│       └── sync.py           # point d'entrée de la synchro
└── Data/              # données et infos sensibles, hors git
    ├── garmin.db          # base SQLite (activités + santé)
    ├── fit/               # fichiers .fit d'origine
    └── garmin_tokens/     # jetons de connexion Garmin
```

Le dossier de données peut être déplacé via la variable d'environnement `SPLINTER_DATA`.

## Installation

```
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## Synchronisation Garmin

```
.\.venv\Scripts\python -m splinter.sync
```

La première fois, le script demande email, mot de passe et code MFA éventuel
(jamais stockés ; seuls les jetons OAuth sont conservés dans `Data/garmin_tokens`).
Les exécutions suivantes ne récupèrent que les nouveautés.

Options :
- `--full` : reparcourir toute la liste des activités
- `--no-fit` : sans télécharger les fichiers .fit
- `--no-health` : activités seulement
- `--since AAAA-MM-JJ` : début de l'historique santé (par défaut : première activité)

## Contenu de la base

| Table | Contenu |
|---|---|
| `activities` | une ligne par activité : type, distance, durée, FC, D+… + JSON Garmin complet |
| `daily_health` | une ligne par jour : pas, FC repos, stress, Body Battery, sommeil, HRV, disposition à l'entraînement, charge aiguë/chronique, VO2max, poids |
| `health_raw` | réponses brutes de l'API santé (par jour et par type), source de `daily_health` |
