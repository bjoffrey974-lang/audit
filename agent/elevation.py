"""
Gestion de l'élévation administrateur (Windows).

- is_admin()        : True si le process tourne avec les droits admin.
- ensure_admin()    : tente de relancer le programme en admin via UAC.
                      Si l'élévation échoue ou est refusée, retourne False
                      (l'agent continue en mode dégradé, contrôles admin -> indéterminé).

Comportement volontaire : on ne FORCE jamais. On tente, et on dégrade proprement.
"""
import sys
import os
import platform

IS_WINDOWS = platform.system().lower().startswith("win")


def is_admin():
    """Retourne True si le process courant a les droits administrateur."""
    if not IS_WINDOWS:
        # Sous Linux/dev : on considère "non admin" pour exercer le mode dégradé.
        try:
            return os.geteuid() == 0
        except AttributeError:
            return False
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin():
    """
    Si pas admin, tente de relancer le programme avec élévation UAC.

    Retourne :
      - True  si déjà admin (rien à faire).
      - False si non-admin ET (relance lancée OU relance impossible/refusée).
              Dans le cas "relance lancée", le process courant doit se terminer
              (l'appelant gère sys.exit). Dans le cas "impossible", on continue
              en mode dégradé.

    Renvoie un tuple (admin, relance_lancee) pour que l'appelant décide.
    """
    if is_admin():
        return (True, False)

    if not IS_WINDOWS:
        # Pas d'élévation hors Windows : mode dégradé.
        return (False, False)

    try:
        import ctypes
        # Relgance le même programme avec le verbe "runas" -> déclenche l'UAC.
        # Cas .exe (PyInstaller) : sys.executable est l'exe lui-même.
        # Cas script .py : on relance python avec le script en argument.
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv[1:])
        else:
            exe = sys.executable  # python.exe
            params = " ".join(f'"{a}"' for a in sys.argv)

        # ShellExecuteW renvoie > 32 si succès.
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, None, 1
        )
        if ret > 32:
            # Relance lancée avec succès -> l'instance courante doit se fermer.
            return (False, True)
        else:
            # Échec/refus UAC -> mode dégradé.
            return (False, False)
    except Exception:
        return (False, False)
