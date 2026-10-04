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
│       ├── fit_analysis.py   # analyse seconde par seconde des .fit (km, dérive)
│       ├── export.py         # export course à pied lisible par Claude
│       └── sync.py           # point d'entrée de la synchro
└── Data/              # données et infos sensibles, hors git
    ├── garmin.db          # base SQLite (activités + santé)
    ├── fit/               # fichiers .fit d'origine
    ├── SplinterDrive/     # export pour Claude, synchronisé par Google Drive
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
- `--no-export` : sans régénérer l'export pour Claude
- `--since AAAA-MM-JJ` : début de l'historique santé (par défaut : première activité)

## Contenu de la base

| Table | Contenu |
|---|---|
| `activities` | une ligne par activité : type, distance, durée, FC, D+… + JSON Garmin complet |
| `daily_health` | une ligne par jour : pas, FC repos, stress, Body Battery, sommeil, HRV, disposition à l'entraînement, charge aiguë/chronique, VO2max, poids |
| `run_km` | une ligne par kilomètre de chaque sortie course, calculée depuis les .fit |
| `run_fit_metrics` | par sortie : FC et allure par moitié, découplage, FC à allure fixe |
| `health_raw` | réponses brutes de l'API santé (par jour et par type), source de `daily_health` |

## Export pour Claude

À la fin de chaque synchro, `splinter.export` régénère dans `Data/SplinterDrive` des fichiers
compacts sur la course à pied (`LISEZMOI.md`, `courses.csv`, `courses_km.csv`,
`semaines.csv`, `sante_quotidienne.csv`). Ce dossier est synchronisé par Google Drive pour ordinateur, ce qui
permet d'en discuter avec Claude depuis le téléphone. Lancement seul :

```
.\.venv\Scripts\python -m splinter.export
```

## Synchro automatique chaque soir

```
powershell -ExecutionPolicy Bypass -File scripts\planifier_synchro.ps1 -Heure 22:00
```

Crée une tâche Windows « Splinter - synchro Garmin » qui lance `splinter.nightly` chaque soir,
sans fenêtre. Elle réveille le PC s'il est en veille et rattrape la synchro au prochain
démarrage s'il était éteint. Le PC reste éveillé 3 min après la synchro pour laisser
Google Drive envoyer l'export, puis Windows le rendort. Journal : `Data/logs/sync.log`
(source du réveil, nouvelles sorties et nuits récupérées, dates les plus récentes exportées). Si les jetons Garmin expirent, la
tâche échoue (voir le journal) : relancer une fois `python -m splinter.sync` à la main.
