"""Lance le dashboard : python -m splinter.dashboard  (http://localhost:8050).

Compile l'interface web (web/) si elle n'existe pas ou si ses sources ont changé, puis démarre
l'API locale qui sert à la fois les données et l'interface. Accessible uniquement depuis ce PC.

Options : --port 8050, --no-browser (ne pas ouvrir le navigateur), --no-build (ne pas compiler).
"""

import argparse
import shutil
import subprocess
import sys
import threading
import webbrowser

import uvicorn

from splinter.config import REPO_DIR

WEB = REPO_DIR / "web"
DIST_INDEX = WEB / "dist" / "index.html"
SOURCES = ["src", "index.html", "package.json", "vite.config.js"]


def _needs_build() -> bool:
    if not DIST_INDEX.exists():
        return True
    built = DIST_INDEX.stat().st_mtime
    for name in SOURCES:
        p = WEB / name
        files = p.rglob("*") if p.is_dir() else [p]
        if any(f.is_file() and f.stat().st_mtime > built for f in files):
            return True
    return False


def build() -> None:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm introuvable : installer Node.js (https://nodejs.org) pour compiler l'interface.")
    if not (WEB / "node_modules").is_dir():
        print("Installation des dépendances de l'interface (npm install)...")
        subprocess.run([npm, "install"], cwd=WEB, check=True)
    print("Compilation de l'interface (npm run build)...")
    subprocess.run([npm, "run", "build"], cwd=WEB, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    parser.add_argument("--no-build", action="store_true", help="ne pas compiler l'interface")
    args = parser.parse_args()

    if not args.no_build and _needs_build():
        build()

    url = f"http://localhost:{args.port}/"
    print(f"Dashboard Splinter : {url}  (Ctrl+C pour arrêter)")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    uvicorn.run("splinter.api.app:app", host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
