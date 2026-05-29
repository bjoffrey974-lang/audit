"""
Collecte détaillée macOS — équivalent winaudit-like.

Chaque fonction retourne une liste de dicts en gérant les échecs proprement.
Sources principales : system_profiler -json, dscl, launchctl, softwareupdate.

Format de sortie identique à details.py côté Windows : les clés des dicts
sont alignées pour que la plateforme puisse afficher indifféremment Windows
ou Mac dans les mêmes tableaux.
"""
import re

try:
    from shell_mac import sh, sh_json
except ImportError:
    from .shell_mac import sh, sh_json


# ---------------------------------------------------------------------------
# Applications installées
# ---------------------------------------------------------------------------

def collect_applications():
    """
    Liste des applications via system_profiler SPApplicationsDataType.
    Renvoie [{nom, version, editeur, date_install}].
    """
    data, ok = sh_json(
        "system_profiler SPApplicationsDataType -json", timeout=120)
    if not ok:
        return []
    apps = data.get("SPApplicationsDataType", [])
    out = []
    for a in apps:
        out.append({
            "nom": a.get("_name", ""),
            "version": a.get("version", ""),
            "editeur": a.get("info") or a.get("obtained_from", ""),
            "date_install": (a.get("lastModified") or "")[:10],  # ISO date
            "chemin": a.get("path", ""),
        })
    return out


# ---------------------------------------------------------------------------
# Mises à jour
# ---------------------------------------------------------------------------

def collect_updates():
    """
    Historique des MAJ macOS via softwareupdate --history.
    Format texte tabulaire, on parse manuellement.
    """
    out, ok = sh("softwareupdate --history 2>/dev/null", timeout=30)
    if not ok or not out.strip():
        return []
    updates = []
    lines = out.splitlines()
    # Sauter les 2 lignes d'entête. Format approximatif :
    # Display Name                            Version    Date
    # ---                                     ---        ---
    # Command Line Tools for Xcode            15.3       10/03/2024
    for line in lines[2:]:
        line = line.rstrip()
        if not line or set(line.strip()) <= {"-", " "}:
            continue
        # On split sur les espaces multiples pour récupérer name / version / date
        parts = re.split(r"\s{2,}", line)
        if len(parts) >= 3:
            updates.append({
                "kb": "",
                "type": parts[0].strip(),
                "installe_par": "",
                "date_install": parts[-1].strip(),
            })
    return updates


# ---------------------------------------------------------------------------
# Comptes utilisateurs
# ---------------------------------------------------------------------------

def collect_users():
    """
    Comptes utilisateurs locaux (UniqueID >= 500 = vrais users, < 500 = système).
    """
    # Liste des noms d'utilisateurs avec UID >= 500
    out, ok = sh(
        "dscl . -list /Users UniqueID 2>/dev/null | "
        "awk '$2 >= 500 {print $1}'",
        timeout=15)
    if not ok or not out.strip():
        return []
    users = []
    # Membres du groupe admin pour savoir qui est admin
    adm_out, _ = sh(
        "dscl . -read /Groups/admin GroupMembership 2>/dev/null | "
        "sed 's/GroupMembership://'",
        timeout=10)
    admins = set((adm_out or "").split())

    for nom in out.strip().splitlines():
        nom = nom.strip()
        if not nom:
            continue
        # Récupérer description (RealName) et état (AuthenticationAuthority)
        rn_out, _ = sh(
            f"dscl . -read /Users/{nom} RealName 2>/dev/null | "
            f"tail -n +2 | xargs",
            timeout=5)
        # Dernière connexion : last -1 <user>
        last_out, _ = sh(
            f"last -1 {nom} 2>/dev/null | head -1 | "
            f"awk '{{print $4, $5, $6, $7}}'",
            timeout=5)
        users.append({
            "nom": nom,
            "active": True,  # dscl ne désactive pas explicitement les comptes
            "description": (rn_out or "").strip(),
            "derniere_connexion": (last_out or "").strip(),
            "mdp_jamais_expire": True,  # pas d'expiration par défaut macOS
            "mdp_requis": True,
            "source": "Local",
            "admin": nom in admins,
        })
    return users


# ---------------------------------------------------------------------------
# Services (launchd daemons et agents)
# ---------------------------------------------------------------------------

def collect_services():
    """
    Liste les services launchd actifs (équivalent des services Windows).
    launchctl list = format tabulaire "PID Status Label".
    """
    out, ok = sh("launchctl list 2>/dev/null", timeout=30)
    if not ok:
        return []
    services = []
    for line in out.splitlines()[1:]:  # skip header
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, status, label = parts
        services.append({
            "nom": label,
            "nom_affiche": label,  # macOS n'a pas de display name distinct
            "etat": "Running" if pid != "-" else "Stopped",
            "demarrage": "",  # launchd ne sépare pas auto/manuel comme Windows
            "compte": "",
        })
    return services


# ---------------------------------------------------------------------------
# Pilotes / extensions kernel
# ---------------------------------------------------------------------------

def collect_drivers():
    """
    Extensions kernel chargées (kextstat). Sur Apple Silicon avec macOS 11+,
    les kexts sont en voie d'extinction (remplacés par les System Extensions).
    On collecte les deux.
    """
    drivers = []
    # Kexts (legacy + signed)
    out, ok = sh(
        "kextstat -l 2>/dev/null | awk 'NR>1 {print $6, $7}'",
        timeout=20)
    if ok and out.strip():
        for line in out.strip().splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                drivers.append({
                    "peripherique": parts[0],
                    "fabricant": "",
                    "version": parts[1].strip("()"),
                    "date": "",
                    "classe": "kext",
                })
    # System Extensions (modernes)
    out2, ok2 = sh(
        "systemextensionsctl list 2>/dev/null | "
        "awk '/^[*]/ {print $5, $6, $7}'",
        timeout=15)
    if ok2 and out2.strip():
        for line in out2.strip().splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) >= 1:
                drivers.append({
                    "peripherique": parts[0] if parts else "",
                    "fabricant": parts[1] if len(parts) > 1 else "",
                    "version": parts[2] if len(parts) > 2 else "",
                    "date": "",
                    "classe": "system_extension",
                })
    return drivers


# ---------------------------------------------------------------------------
# Tâches planifiées (cron + launchd timers)
# ---------------------------------------------------------------------------

def collect_scheduled_tasks():
    """
    Tâches planifiées : on combine crontab utilisateur (legacy) et
    LaunchAgents/LaunchDaemons utilisateur (modernes).
    On ignore /System/Library/LaunchDaemons (trop bruyant, c'est Apple).
    """
    tasks = []
    # Crontab utilisateur
    out, ok = sh("crontab -l 2>/dev/null", timeout=5)
    if ok and out.strip():
        for line in out.strip().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                tasks.append({
                    "nom": line[:80],
                    "chemin": "crontab",
                    "etat": "Enabled",
                    "derniere_exec": "",
                    "compte": "user",
                })
    # LaunchAgents / LaunchDaemons utilisateur et /Library (pas /System)
    for path in ["/Library/LaunchAgents", "/Library/LaunchDaemons",
                 "~/Library/LaunchAgents"]:
        out, ok = sh(f"ls {path}/*.plist 2>/dev/null", timeout=5)
        if ok and out.strip():
            for fp in out.strip().splitlines():
                tasks.append({
                    "nom": fp.split("/")[-1].replace(".plist", ""),
                    "chemin": "/".join(fp.split("/")[:-1]),
                    "etat": "Loaded",
                    "derniere_exec": "",
                    "compte": "system" if "Daemons" in fp else "user",
                })
    return tasks


# ---------------------------------------------------------------------------
# Règles pare-feu
# ---------------------------------------------------------------------------

def collect_firewall_rules():
    """
    Règles de l'Application Firewall macOS (par appli, pas par port).
    socketfilterfw --listapps liste les applis autorisées/bloquées.
    """
    out, ok = sh(
        "/usr/libexec/ApplicationFirewall/socketfilterfw --listapps 2>/dev/null",
        timeout=15)
    if not ok or not out.strip():
        return []
    rules = []
    # Format : Path / Action multi-lignes par appli
    current = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("ALF: ") or line.startswith("Total number"):
            continue
        if " : " in line and line.endswith(".app"):
            # Nouvelle entrée appli
            current = {"nom": line.split(" : ", 1)[-1],
                       "direction": "Inbound",
                       "profil": "All", "action": ""}
        elif current and ("allow" in line.lower() or "block" in line.lower()):
            current["action"] = "Allow" if "allow" in line.lower() else "Block"
            rules.append(current)
            current = None
    return rules


# ---------------------------------------------------------------------------
# Sessions ouvertes
# ---------------------------------------------------------------------------

def collect_sessions():
    """
    Utilisateurs connectés via 'who' (équivalent quser).
    """
    out, ok = sh("who 2>/dev/null", timeout=5)
    if not ok or not out.strip():
        return []
    sessions = []
    for line in out.strip().splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 2:
            sessions.append({
                "utilisateur": parts[0],
                "etat": "Active",
                "session": parts[1],
                "source": "who",
            })
    return sessions


# ---------------------------------------------------------------------------
# Logiciels d'accès distant
# ---------------------------------------------------------------------------

REMOTE_KEYWORDS = [
    "teamviewer", "anydesk", "tightvnc", "realvnc",
    "logmein", "splashtop", "remotepc", "screenconnect", "connectwise",
    "rustdesk", "supremo", "zoho assist", "bomgar", "beyondtrust",
    "chrome remote desktop", "dameware", "kaseya", "jump desktop",
]


def detect_remote_access(applications):
    """Détecte les apps d'accès distant connues dans la liste."""
    detectes = []
    for app in applications:
        nom = (app.get("nom") or "").lower()
        for kw in REMOTE_KEYWORDS:
            if kw in nom:
                detectes.append({
                    "nom": app.get("nom"),
                    "version": app.get("version"),
                    "editeur": app.get("editeur"),
                })
                break
    return detectes


# ---------------------------------------------------------------------------
# Échecs d'authentification
# ---------------------------------------------------------------------------

def collect_auth_failures(days=30, limit=50):
    """
    Échecs d'authentification via log (unified log macOS, depuis 10.12).
    """
    cmd = (
        f"log show --predicate "
        f"'eventMessage CONTAINS \"authentication failed\" "
        f"OR eventMessage CONTAINS \"Failed to authenticate\"' "
        f"--last {days}d --style compact 2>/dev/null | head -{limit}"
    )
    out, ok = sh(cmd, timeout=60)
    if not ok or not out.strip():
        return []
    fails = []
    for line in out.strip().splitlines()[:limit]:
        parts = line.split(None, 2)
        if len(parts) >= 3:
            fails.append({"date": " ".join(parts[:2]),
                          "message": parts[2][:120]})
    return fails


# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------

def collect_volumes():
    """Volumes montés via diskutil ou df."""
    out, ok = sh(
        "df -k 2>/dev/null | awk 'NR>1 && $1 ~ /^\\/dev/ "
        "{printf \"%s|%s|%s|%s\\n\", $9, $2, $4, $1}'",
        timeout=10)
    if not ok or not out.strip():
        return []
    volumes = []
    for line in out.strip().splitlines():
        parts = line.split("|")
        if len(parts) >= 4:
            try:
                taille = round(int(parts[1]) / 1024 / 1024, 1)
                libre = round(int(parts[2]) / 1024 / 1024, 1)
            except ValueError:
                taille = libre = 0
            volumes.append({
                "lettre": parts[0],
                "label": parts[0].split("/")[-1] if parts[0] else "",
                "fs": "APFS",  # par défaut sur Mac moderne
                "taille_go": taille,
                "libre_go": libre,
                "etat": "Healthy",
            })
    return volumes


# ---------------------------------------------------------------------------
# Configuration réseau
# ---------------------------------------------------------------------------

def collect_network():
    """Configuration des interfaces réseau actives."""
    # Trouver l'interface par défaut
    iface_out, ok = sh(
        "route -n get default 2>/dev/null | awk '/interface:/ {print $2}'",
        timeout=10)
    if not ok or not iface_out.strip():
        return []
    iface = iface_out.strip()
    ip_out, _ = sh(f"ipconfig getifaddr {iface} 2>/dev/null", timeout=5)
    mac_out, _ = sh(
        f"ifconfig {iface} 2>/dev/null | awk '/ether/ {{print $2}}'",
        timeout=5)
    gw_out, _ = sh(
        "route -n get default 2>/dev/null | awk '/gateway:/ {print $2}'",
        timeout=5)
    dns_out, _ = sh(
        "scutil --dns 2>/dev/null | awk '/nameserver/ {print $3}' | "
        "sort -u | head -3 | tr '\\n' ',' | sed 's/,$//'",
        timeout=10)
    return [{
        "interface": iface,
        "ip": (ip_out or "").strip(),
        "mac": (mac_out or "").strip().lower(),
        "masque": "",
        "passerelle": (gw_out or "").strip(),
        "dns": (dns_out or "").strip(),
    }]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

COLLECTORS = [
    ("applications",     "Applications installées",       collect_applications),
    ("updates",          "Mises à jour macOS",            collect_updates),
    ("users",            "Comptes utilisateurs locaux",   collect_users),
    ("services",         "Services / daemons",            collect_services),
    ("drivers",          "Extensions kernel/système",     collect_drivers),
    ("scheduled_tasks",  "Tâches planifiées",             collect_scheduled_tasks),
    ("firewall_rules",   "Règles pare-feu (apps)",        collect_firewall_rules),
    ("sessions",         "Sessions ouvertes",             collect_sessions),
    ("volumes",          "Volumes / partitions",          collect_volumes),
    ("network",          "Configuration réseau",          collect_network),
    ("auth_failures",    "Échecs d'authentification (30j)", collect_auth_failures),
]


def collect_all(progress_cb=None):
    """Lance toutes les collectes. Retourne le dict 'details'."""
    total = len(COLLECTORS)
    details = {}
    for i, (key, label, fn) in enumerate(COLLECTORS, 1):
        if progress_cb:
            progress_cb(i, total, label)
        try:
            details[key] = fn()
        except Exception as e:
            details[key] = []
            details.setdefault("_errors", {})[key] = str(e)

    if details.get("applications"):
        details["remote_access"] = detect_remote_access(details["applications"])
    else:
        details["remote_access"] = []
    return details


def count_summary(details):
    return {
        "applications": len(details.get("applications", [])),
        "updates": len(details.get("updates", [])),
        "users": len(details.get("users", [])),
        "services": len(details.get("services", [])),
        "drivers": len(details.get("drivers", [])),
        "scheduled_tasks": len(details.get("scheduled_tasks", [])),
        "firewall_rules": len(details.get("firewall_rules", [])),
        "sessions": len(details.get("sessions", [])),
        "volumes": len(details.get("volumes", [])),
        "network": len(details.get("network", [])),
        "auth_failures": len(details.get("auth_failures", [])),
        "remote_access": len(details.get("remote_access", [])),
    }
