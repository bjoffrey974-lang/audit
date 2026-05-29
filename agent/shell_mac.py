"""
Helper d'exécution shell pour macOS.
Équivalent de la fonction ps() côté Windows : exécute une commande shell,
retourne (stdout, ok). Gère timeout et erreurs proprement.

Sur macOS, pas besoin de masquer une fenêtre console (Tkinter --windowed
ne fait pas clignoter de Terminal au subprocess.run, contrairement à
Windows).
"""
import subprocess
import platform
import json
import shlex

IS_MAC = platform.system() == "Darwin"


def sh(command, timeout=30, shell=True):
    """
    Exécute une commande shell sur macOS.
    Retourne (stdout, ok). ok=False si erreur / timeout / hors macOS.

    Par défaut shell=True pour permettre les pipes et la composition simple
    (ex: "ls /Applications/*.app | wc -l"). Si tu passes une liste d'args,
    utilise shell=False.
    """
    if not IS_MAC:
        return ("", False)
    try:
        r = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode != 0:
            # On retourne quand même la sortie pour debug, mais ok=False
            return ((r.stdout or "").strip() or (r.stderr or "").strip(), False)
        return ((r.stdout or "").strip(), True)
    except Exception:
        return ("", False)


def sh_json(command, timeout=30):
    """
    Exécute une commande shell qui produit du JSON, retourne (data, ok).
    Beaucoup d'outils macOS supportent -json nativement (system_profiler,
    pmset, etc.). Pour les autres, on parse leur sortie textuelle.
    """
    out, ok = sh(command, timeout=timeout)
    if not ok or not out.strip():
        return (None, False)
    try:
        return (json.loads(out), True)
    except json.JSONDecodeError:
        return (None, False)


# Statuts standardisés (alignés avec checks.py côté Windows)
def _result(statut, detail=""):
    return {"statut": statut, "detail": detail}
