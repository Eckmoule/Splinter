"""État partagé des synchros : verrou (une seule à la fois) et résultat de la dernière.

Utilisé par `splinter.sync` (quel que soit le lanceur : commande, tâche de nuit, dashboard), par
le lanceur de nuit (synchro ignorée si récente) et par l'API du dashboard (indicateur, bouton).

- Data/logs/sync.lock            : PID de la synchro en cours
- Data/logs/derniere_synchro.json : { started, finished, ok, message, last_ok }
"""

import ctypes
import json
import os
from contextlib import contextmanager
from datetime import datetime

from splinter.config import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "sync.log"
LOCK_FILE = LOG_DIR / "sync.lock"
STATE_FILE = LOG_DIR / "derniere_synchro.json"
LEGACY_OK_FILE = LOG_DIR / "derniere_synchro_ok.txt"  # ancien format, lu en secours

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


class AlreadyRunning(RuntimeError):
    pass


def _alive(pid: int) -> bool:
    """Le processus existe-t-il encore ? (Windows ; os.kill(pid, 0) y tuerait le processus.)"""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def running_pid() -> int | None:
    try:
        pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if _alive(pid) else None


def read_state() -> dict:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if not state.get("last_ok"):
        try:
            state["last_ok"] = LEGACY_OK_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return state


def _write_state(state: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def hours_since_last_ok() -> float | None:
    last = read_state().get("last_ok")
    if not last:
        return None
    return (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600


@contextmanager
def sync_run():
    """Verrouille la synchro et enregistre son résultat. Lève AlreadyRunning si une autre tourne."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    other = running_pid()
    if other and other != os.getpid():
        raise AlreadyRunning(f"Une synchro est déjà en cours (processus {other}).")
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    now = lambda: datetime.now().isoformat(timespec="seconds")  # noqa: E731
    state = read_state()
    state.update(started=now(), finished=None, ok=None, message=None)
    _write_state(state)
    try:
        yield
        state.update(finished=now(), ok=True, message=None, last_ok=now())
    except BaseException as e:
        state.update(finished=now(), ok=False, message=describe_error(e))
        raise
    finally:
        _write_state(state)
        LOCK_FILE.unlink(missing_ok=True)


def describe_error(e: BaseException) -> str:
    # sans console (tâche de nuit, dashboard), la demande d'identifiants échoue faute de saisie
    if isinstance(e, EOFError) or (isinstance(e, RuntimeError) and "stdin" in str(e).lower()):
        return ("Connexion Garmin impossible sans identifiants (jetons expirés) : relancer "
                "`python -m splinter.sync` à la main.")
    if isinstance(e, SystemExit):
        return str(e.code) if e.code not in (None, 0) else "Arrêt."
    if isinstance(e, KeyboardInterrupt):
        return "Interrompue."
    return f"{type(e).__name__} : {e}"
