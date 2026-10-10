# Splinter

Analyse locale de l'historique sportif Garmin Connect.

## Organisation

```
Sport/
├── Splinter/          # ce dépôt git (code uniquement)
│   ├── web/                  # interface du dashboard (Vue 3 + Vite + ECharts, kit UI Fafnir)
│   └── splinter/
│       ├── config.py         # chemins du projet
│       ├── garmin_client.py  # connexion Garmin Connect + base locale
│       ├── activities.py     # synchro des activités et fichiers .fit
│       ├── health.py         # synchro des données santé quotidiennes
│       ├── fit_analysis.py   # analyse seconde par seconde des .fit (km, dérive)
│       ├── export.py         # export course à pied lisible par Claude
│       ├── api/              # API locale FastAPI du dashboard (lit garmin.db)
│       ├── dashboard.py      # lance le dashboard (compile web/ au besoin)
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
| `run_laps` | une ligne par tour enregistré par la montre (auto au km, étape de séance, manuel), depuis les .fit |
| `run_fit_metrics` | par sortie : FC et allure par moitié, découplage, FC à allure fixe, efficacité, charge TRIMP |
| `health_raw` | réponses brutes de l'API santé (par jour et par type), source de `daily_health` |

## Export pour Claude

À la fin de chaque synchro, `splinter.export` régénère dans `Data/SplinterDrive` des fichiers
compacts sur la course à pied : `LISEZMOI.md`, `courses.csv`, `tours.csv` (tous les tours de
l'historique), `semaines.csv`, `sante_quotidienne.csv`, et `sorties_recentes/` (un point toutes
les 10 s pour les 10 dernières sorties, les plus anciennes sont supprimées à chaque export).
Ce dossier est synchronisé par Google Drive pour ordinateur, ce qui permet d'en discuter avec
Claude depuis le téléphone. Lancement seul :

```
.\.venv\Scripts\python -m splinter.export
```

## Dashboard

```
.\.venv\Scripts\python -m splinter.dashboard
```

Ouvre http://localhost:8050 (accessible uniquement depuis ce PC). En haut à droite : date de la dernière
synchro réussie (détail au survol) et bouton **Mettre à jour**, qui lance `splinter.sync` en
arrière-plan (récupération Garmin + export Drive) ; les pages se rechargent à la fin. Ouvrir le
dashboard ne lance pas de synchro. Au premier lancement, ou quand
les sources de `web/` ont changé, l'interface est compilée automatiquement (Node.js requis).

- `splinter/api/` : API FastAPI en lecture seule sur `garmin.db`, sert aussi l'interface compilée.
- `web/` : interface Vue 3 + Vite + ECharts, sur la base du kit UI « Fafnir » (`web/src/kit/` :
  thème, composants, formats français, graphiques).
- Développement de l'interface avec rechargement à chaud : lancer le dashboard avec
  `--no-browser`, puis `npm run dev` dans `web/` (http://localhost:5173).

Pages (indicateurs calculés dans `splinter/api/metrics.py`) :
- **Progression** — est-ce que je progresse sur le long terme ? FC sur le plat à allure fixe,
  efficacité (vitesse ÷ FC), VO2max ; en contexte : découplage des sorties longues, FC repos et HRV
  mensuelles, volume et plus longue sortie par mois. Tuiles : 3 derniers mois vs même période un an avant.
- **Entraînement** — est-ce que je m'entraîne correctement ? Résumé par règles explicites (charge,
  HRV, FC repos, sommeil, intensité) ; Forme / Fatigue / Fraîcheur calculées depuis une charge TRIMP
  (FC seconde par seconde) sur tout l'historique ; récupération sur 90 jours ; sur 3, 6 ou 12 mois :
  répartition de l'intensité, régularité, montée en charge, types de séances.

## Synchro automatique chaque soir

```
powershell -ExecutionPolicy Bypass -File scripts\planifier_synchro.ps1 -Heure 22:00
```

Crée une tâche Windows « Splinter - synchro Garmin » qui lance `splinter.nightly`, sans fenêtre :
- chaque soir à l'heure choisie, en réveillant le PC s'il est en veille ;
- à chaque sortie de veille (si le minuteur réveille le PC en retard, Windows ne rattraperait la
  tâche qu'après ~10 min, alors que le PC se rendort au bout de 2 min) ;
- au prochain démarrage si le PC était éteint.

Une seule synchro tourne à la fois (verrou `Data/logs/sync.lock`, quel que soit le lanceur) ; le
résultat de la dernière est gardé dans `Data/logs/derniere_synchro.json`. La synchro est ignorée si la dernière réussie date de moins de 6 h (`-IntervalleMin`). Le PC
reste éveillé pendant la synchro puis 3 min pour laisser Google Drive envoyer l'export.
Journal : `Data/logs/sync.log` (source du réveil, nouvelles sorties et nuits récupérées, dates
les plus récentes exportées). Si les jetons Garmin expirent, la tâche échoue (voir le journal) :
relancer une fois `python -m splinter.sync` à la main.
