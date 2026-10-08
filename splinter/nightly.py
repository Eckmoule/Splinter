"""Lanceur de la synchro planifiée (sans console).

Lancé par la tâche Windows chaque soir à heure fixe ET à chaque sortie de veille : si le
minuteur réveille le PC en retard, Windows considère le créneau comme manqué et ne rattrape la
tâche qu'une dizaine de minutes plus tard, alors que le PC se rendort au bout de 2 min. Le
déclencheur « sortie de veille » démarre tout de suite ; `--if-older-than` évite alors de
resynchroniser à chaque réveil dans la journée.

Redirige toute la sortie vers Data/logs/sync.log et n'attend aucune saisie : si Garmin
redemande les identifiants (jetons expirés), l'erreur est journalisée et il faut relancer
une fois `python -m splinter.sync` à la main.

Dès le démarrage, pendant la synchro puis KEEP_AWAKE_AFTER_S secondes, le PC est maintenu
éveillé pour laisser à Google Drive le temps d'envoyer l'export ; Windows le rendort ensuite
selon ses réglages habituels.

Usage : pythonw -m splinter.nightly [--if-older-than HEURES]
"""

import argparse
import ctypes
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime

from splinter.config import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "sync.log"
LAST_OK_FILE = LOG_DIR / "derniere_synchro_ok.txt"
MAX_LOG_BYTES = 1_000_000
KEEP_AWAKE_AFTER_S = 3 * 60
NETWORK_HOST = ("connect.garmin.com", 443)
NETWORK_WAIT_S = 120  # après un réveil, le réseau met parfois quelques secondes à revenir

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _keep_awake(on: bool) -> None:
    """Empêche (ou ré-autorise) la mise en veille automatique de Windows."""
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if on else ES_CONTINUOUS
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


def _last_wake() -> str:
    """Source du dernier réveil selon Windows (ex. minuteur = réveil par la tâche)."""
    try:
        out = subprocess.run(["powercfg", "/lastwake"], capture_output=True, timeout=15,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.decode("cp850", "replace")
    except (OSError, subprocess.SubprocessError) as e:
        return f"inconnu ({e})"
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    # on garde le détail de la première source de réveil
    try:
        i = next(i for i, l in enumerate(lines) if l.startswith("Source de sortie de veille [0]"))
        return " | ".join(lines[i + 1:i + 6]) or "aucun détail"
    except StopIteration:
        return " | ".join(lines[-3:]) or "aucun détail"


def _hours_since_last_ok() -> float | None:
    try:
        last = datetime.fromisoformat(LAST_OK_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return (datetime.now() - last).total_seconds() / 3600


def _wait_for_network() -> bool:
    deadline = time.monotonic() + NETWORK_WAIT_S
    while True:
        try:
            socket.create_connection(NETWORK_HOST, timeout=5).close()
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-older-than", type=float, metavar="HEURES",
                        help="ne rien faire si la dernière synchro réussie date de moins de HEURES")
    args = parser.parse_args()

    _keep_awake(True)  # tout de suite : Windows rendort vite un PC réveillé par un minuteur
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        LOG_FILE.replace(LOG_FILE.with_suffix(".old.log"))

    started = time.monotonic()
    with LOG_FILE.open("a", encoding="utf-8") as log:
        sys.stdout = sys.stderr = log
        sys.stdin = None  # aucune saisie possible en mode planifié

        age = _hours_since_last_ok()
        if args.if_older_than is not None and age is not None and age < args.if_older_than:
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S} — déclenchement ignoré : "
                  f"dernière synchro réussie il y a {age:.1f} h")
            _keep_awake(False)
            return 0

        print(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} — synchro planifiée =====")
        print(f"Dernier réveil du PC : {_last_wake()}")
        log.flush()
        code = 1
        try:
            if not _wait_for_network():
                print(f"Réseau indisponible après {NETWORK_WAIT_S} s : synchro abandonnée.")
            else:
                sys.argv = ["splinter.sync"]
                from splinter import sync
                sync.main()
                LAST_OK_FILE.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
                code = 0
        except SystemExit as e:
            print(f"Arrêt : {e}")
        except Exception:
            traceback.print_exc()
            print("ÉCHEC. Si les jetons Garmin ont expiré, relancer `python -m splinter.sync` à la main.")
        finally:
            print(f"Synchro {'terminée' if code == 0 else 'en échec'} en {time.monotonic() - started:.0f} s ; "
                  f"PC maintenu éveillé encore {KEEP_AWAKE_AFTER_S // 60} min pour Google Drive.")
            log.flush()
            try:
                time.sleep(KEEP_AWAKE_AFTER_S)
            finally:
                _keep_awake(False)
                print(f"{datetime.now():%H:%M:%S} — fin, mise en veille de nouveau autorisée.")
        return code


if __name__ == "__main__":
    sys.exit(main())
