"""
Contrôles de conformité sécurité macOS.

Chaque contrôle exécute une commande shell macOS native et interprète le
résultat en statut : ok | attention | critique | indetermine | na

IDs alignés sur conformite_ref.py (référentiel partagé avec la plateforme).
Quelques contrôles Windows-spécifiques (smbv1, rdp NLA) sont remplacés par
leurs équivalents Mac (Screen Sharing, SIP, Gatekeeper, etc.) sous des IDs
mac-spécifiques pour ne pas créer de confusion dans le référentiel.
"""
import re
from datetime import datetime, timedelta

try:
    from shell_mac import sh, sh_json, _result, IS_MAC
except ImportError:
    from .shell_mac import sh, sh_json, _result, IS_MAC


def detect_profil():
    return "mac"


# ---------------------------------------------------------------------------
# Protection
# ---------------------------------------------------------------------------

def chk_firewall_actif(is_admin=False):
    """
    Pare-feu macOS (Application Firewall).
    socketfilterfw --getglobalstate retourne 0=off, 1=on, 2=block-all.
    """
    out, ok = sh(
        "/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null",
        timeout=10)
    if not ok or not out:
        return _result("indetermine", "Pare-feu non interrogeable")
    if "enabled" in out.lower() or "block all" in out.lower():
        return _result("ok", "Pare-feu macOS actif")
    if "disabled" in out.lower() or "off" in out.lower():
        return _result("critique", "Pare-feu macOS désactivé")
    return _result("indetermine", out[:80])


def chk_antivirus_present(is_admin=False):
    """
    Détection d'antivirus tiers connus + XProtect (intégré Apple).
    XProtect est toujours présent depuis 10.6, considéré comme baseline.
    On cherche les AV tiers en bonus dans /Applications.
    """
    avs_connus = [
        ("Bitdefender", "/Applications/Bitdefender Endpoint Security for Mac.app"),
        ("Sophos", "/Applications/Sophos/Sophos Endpoint.app"),
        ("ESET", "/Applications/ESET Endpoint Security.app"),
        ("Norton", "/Applications/Norton 360.app"),
        ("McAfee", "/Library/Application Support/McAfee"),
        ("Avast", "/Applications/Avast.app"),
        ("Malwarebytes", "/Applications/Malwarebytes.app"),
        ("Kaspersky", "/Applications/Kaspersky Endpoint Security 11 for Mac.app"),
        ("Trend Micro", "/Applications/Trend Micro Antivirus.app"),
    ]
    presents = []
    for nom, path in avs_connus:
        out, ok = sh(f"test -e '{path}' && echo OUI", timeout=5)
        if ok and out.strip() == "OUI":
            presents.append(nom)
    # XProtect : toujours présent, vérifions juste qu'il est actif
    xp_out, xp_ok = sh(
        "system_profiler SPInstallHistoryDataType 2>/dev/null | "
        "grep -c 'XProtectPlistConfigData' || echo 0",
        timeout=15)
    xprotect_actif = xp_ok and int((xp_out or "0").strip() or 0) > 0

    if presents:
        return _result("ok", f"AV tiers détecté(s) : {', '.join(presents)}")
    if xprotect_actif:
        return _result("attention",
                       "Seul XProtect (Apple) — pas d'AV tiers détecté")
    return _result("attention", "Aucun antivirus tiers identifié")


def chk_antivirus_ajour(is_admin=False):
    """
    Vérifie la date de la dernière MAJ XProtect (et MRT).
    XProtect se trouve dans /Library/Apple/System/Library/CoreServices/
    """
    paths = [
        "/Library/Apple/System/Library/CoreServices/XProtect.bundle",
        "/System/Library/CoreServices/XProtect.bundle",
    ]
    for p in paths:
        out, ok = sh(
            f"stat -f '%Sm' -t '%Y-%m-%d' '{p}' 2>/dev/null",
            timeout=5)
        if ok and out.strip():
            try:
                d = datetime.strptime(out.strip(), "%Y-%m-%d")
                jours = (datetime.now() - d).days
                if jours <= 14:
                    return _result("ok",
                                   f"XProtect mis à jour il y a {jours} j")
                if jours <= 30:
                    return _result("attention",
                                   f"XProtect mis à jour il y a {jours} j")
                return _result("critique",
                               f"XProtect ancien ({jours} j)")
            except ValueError:
                pass
    return _result("indetermine", "Date XProtect non lisible")


def chk_chiffrement_disque(is_admin=False):
    """FileVault (équivalent BitLocker)."""
    out, ok = sh("fdesetup status 2>/dev/null", timeout=10)
    if not ok:
        return _result("indetermine", "FileVault non interrogeable")
    txt = (out or "").lower()
    if "filevault is on" in txt:
        return _result("ok", "FileVault actif")
    if "filevault is off" in txt:
        return _result("critique", "FileVault inactif")
    return _result("indetermine", out[:80])


# ---------------------------------------------------------------------------
# Mises à jour
# ---------------------------------------------------------------------------

def chk_maj_recentes(is_admin=False):
    """Date de la dernière MAJ système (softwareupdate --history)."""
    # softwareupdate --history sort un texte tabulaire ; on prend la 1ère ligne après l'entête
    out, ok = sh(
        "softwareupdate --history 2>/dev/null | "
        "awk 'NR>2 {print $NF; exit}'",
        timeout=15)
    if not ok or not out.strip():
        return _result("indetermine", "Historique MAJ non lisible")
    # Format attendu : YYYY-MM-DD (ou parfois MM/DD/YY)
    txt = out.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            d = datetime.strptime(txt, fmt)
            jours = (datetime.now() - d).days
            if jours <= 60:
                return _result("ok", f"Dernière MAJ il y a {jours} j")
            if jours <= 120:
                return _result("attention", f"Dernière MAJ il y a {jours} j")
            return _result("critique", f"Dernière MAJ il y a {jours} j")
        except ValueError:
            continue
    return _result("indetermine", f"Date non reconnue : {txt[:30]}")


# Dates de fin de support macOS (approximatives, à actualiser)
MAC_EOL = {
    "10.14": datetime(2021, 10, 25),   # Mojave
    "10.15": datetime(2022, 10, 24),   # Catalina
    "11":    datetime(2023, 11, 6),    # Big Sur
    "12":    datetime(2024, 11, 1),    # Monterey
    "13":    datetime(2025, 11, 1),    # Ventura (estimation)
    "14":    datetime(2026, 11, 1),    # Sonoma (estimation)
    "15":    datetime(2027, 11, 1),    # Sequoia (estimation)
}


def chk_os_supporte(is_admin=False):
    """Version macOS encore supportée par Apple."""
    out, ok = sh("sw_vers -productVersion 2>/dev/null", timeout=5)
    if not ok or not out.strip():
        return _result("indetermine", "Version macOS non lisible")
    ver = out.strip()
    now = datetime.now()
    # Tester d'abord la version complète "X.Y" puis le major
    for key, eol in MAC_EOL.items():
        if ver.startswith(key + ".") or ver == key or ver.startswith(key):
            if now > eol:
                return _result("critique",
                               f"macOS {ver} en fin de support depuis {eol:%m/%Y}")
            if now > eol - timedelta(days=180):
                return _result("attention",
                               f"macOS {ver} : fin de support proche ({eol:%m/%Y})")
            return _result("ok", f"macOS {ver} supporté")
    return _result("ok", f"macOS {ver} (date EOL non référencée)")


# ---------------------------------------------------------------------------
# Comptes & accès
# ---------------------------------------------------------------------------

def chk_admins_limites(is_admin=False):
    """Nombre de comptes administrateurs (membres du groupe 'admin')."""
    out, ok = sh(
        "dscl . -read /Groups/admin GroupMembership 2>/dev/null | "
        "sed 's/GroupMembership://'",
        timeout=10)
    if not ok or not out.strip():
        return _result("indetermine", "Groupe admin non lisible")
    membres = [m for m in out.strip().split() if m and m != "root"]
    n = len(membres)
    if n == 0:
        return _result("attention", "Aucun admin local hors root")
    if n <= 2:
        return _result("ok", f"{n} compte(s) administrateur")
    if n <= 4:
        return _result("attention", f"{n} comptes administrateurs")
    return _result("critique", f"{n} comptes administrateurs (trop)")


def chk_admin_natif_desactive(is_admin=False):
    """
    Sur Mac, l'équivalent du 'compte Administrateur natif' Windows est
    le compte root. Par défaut, root est DÉSACTIVÉ sur macOS — c'est l'état
    sain. Si activé, c'est un signal d'alerte.
    """
    # dscl . -read /Users/root Password : "*" = désactivé
    out, ok = sh(
        "dscl . -read /Users/root Password 2>/dev/null | awk '{print $2}'",
        timeout=10)
    if not ok:
        return _result("indetermine", "Statut root non lisible")
    val = out.strip()
    if val == "*":
        return _result("ok", "Compte root désactivé (par défaut macOS)")
    return _result("attention", "Compte root activé — vérifier nécessité")


def chk_mdp_jamais_expire(is_admin=False):
    """
    macOS ne force pas d'expiration de mot de passe par défaut (différent
    de Windows). On vérifie si une politique d'expiration est en place via
    pwpolicy. Si aucune politique → on considère 'attention' (pas de
    rotation de mot de passe).
    """
    out, ok = sh("pwpolicy -getaccountpolicies 2>/dev/null", timeout=10)
    if not ok:
        return _result("indetermine", "Politique mdp non lisible")
    if "policyAttributeExpiresEveryNDays" in out or "maxMinutesUntilChangePassword" in out:
        return _result("ok", "Politique d'expiration mdp en place")
    return _result("attention",
                   "Aucune politique d'expiration mdp (par défaut macOS)")


def chk_rdp_maitrise(is_admin=False):
    """
    Sur Mac, l'équivalent RDP = Screen Sharing (VNC) + Remote Management (ARD).
    On vérifie que Screen Sharing est désactivé ou maîtrisé.
    """
    # Screen Sharing : launchctl print system/com.apple.screensharing
    out, ok = sh(
        "launchctl print-disabled system 2>/dev/null | "
        "grep -c 'com.apple.screensharing.*=> false' || echo 0",
        timeout=10)
    # Fallback : systemsetup -getremotelogin (SSH, mais souvent corrélé)
    if not ok:
        return _result("indetermine", "État Screen Sharing non lisible")
    # On regarde plus précisément via fdesetup-style : tester si le port 5900 écoute
    listen_out, lok = sh(
        "lsof -iTCP:5900 -sTCP:LISTEN 2>/dev/null | wc -l",
        timeout=10)
    if lok:
        n_listen = int((listen_out or "0").strip())
        if n_listen > 0:
            return _result("attention",
                           "Screen Sharing activé (port 5900 ouvert)")
        return _result("ok", "Screen Sharing désactivé")
    return _result("indetermine")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def chk_uac_actif(is_admin=False):
    """
    Sur Mac, pas d'UAC, mais l'équivalent c'est :
    - SIP (System Integrity Protection) actif
    - Gatekeeper actif
    On vérifie ces deux choses comme indicateur 'protection système'.
    """
    sip_out, sip_ok = sh("csrutil status 2>/dev/null", timeout=5)
    gk_out, gk_ok = sh("spctl --status 2>/dev/null", timeout=5)

    sip_actif = sip_ok and "enabled" in (sip_out or "").lower()
    gk_actif = gk_ok and "enabled" in (gk_out or "").lower()

    if sip_actif and gk_actif:
        return _result("ok", "SIP + Gatekeeper actifs")
    if sip_actif:
        return _result("attention", "SIP actif, Gatekeeper inactif")
    if gk_actif:
        return _result("critique", "SIP désactivé")
    return _result("critique", "SIP et Gatekeeper inactifs")


def chk_smbv1_desactive(is_admin=False):
    """
    macOS moderne (>= 10.12) n'utilise plus SMBv1 par défaut.
    On considère ce contrôle comme N/A sur Mac récent.
    """
    out, ok = sh("sw_vers -productVersion 2>/dev/null", timeout=5)
    if ok and out.strip():
        try:
            major = int(out.strip().split(".")[0])
            if major >= 11:
                return _result("ok", "SMBv1 obsolète depuis macOS 10.12 (non utilisé)")
        except ValueError:
            pass
    return _result("na", "Non applicable (macOS)")


def chk_partages_maitrises(is_admin=False):
    """Partages SMB actifs (sharing -l)."""
    out, ok = sh("sharing -l 2>/dev/null", timeout=10)
    if not ok:
        # sharing peut nécessiter root
        return _result("indetermine", "Partages non lisibles (sharing -l)")
    # Compter les blocs "name:" dans la sortie
    n_shares = len(re.findall(r"^name:", out, re.MULTILINE))
    if n_shares == 0:
        return _result("ok", "Aucun partage SMB local")
    if n_shares <= 3:
        return _result("ok", f"{n_shares} partage(s)")
    return _result("attention", f"{n_shares} partages exposés")


# ---------------------------------------------------------------------------
# Système
# ---------------------------------------------------------------------------

def chk_espace_disque(is_admin=False):
    """% d'espace libre sur le volume racine."""
    out, ok = sh(
        "df -k / 2>/dev/null | awk 'NR==2 {print $4, $2}'",
        timeout=10)
    if not ok or not out.strip():
        return _result("indetermine", "Espace disque non lisible")
    parts = out.strip().split()
    if len(parts) != 2:
        return _result("indetermine")
    try:
        libre = int(parts[0])
        total = int(parts[1])
        if total == 0:
            return _result("indetermine")
        pct = round(libre / total * 100, 1)
        if pct >= 15:
            return _result("ok", f"{pct}% d'espace libre")
        if pct >= 10:
            return _result("attention", f"{pct}% d'espace libre")
        return _result("critique", f"Espace disque critique : {pct}% libre")
    except ValueError:
        return _result("indetermine")


def chk_uptime_raisonnable(is_admin=False):
    """Uptime en jours via sysctl kern.boottime."""
    out, ok = sh("sysctl -n kern.boottime 2>/dev/null", timeout=5)
    if not ok:
        return _result("indetermine", "Uptime non lisible")
    # Format : { sec = 1709123456, usec = 0 } Mon Feb 28 ...
    m = re.search(r"sec\s*=\s*(\d+)", out)
    if not m:
        return _result("indetermine")
    boot_ts = int(m.group(1))
    now_ts = int(datetime.now().timestamp())
    jours = round((now_ts - boot_ts) / 86400, 1)
    if jours <= 30:
        return _result("ok", f"Démarré il y a {jours} jours")
    if jours <= 60:
        return _result("attention", f"Pas de redémarrage depuis {jours} j")
    return _result("attention", f"Uptime élevé : {jours} jours")


# ---------------------------------------------------------------------------
# Spécifique serveurs (macOS n'a plus de version Server depuis Mojave)
# On marque ces contrôles 'na' systématiquement.
# ---------------------------------------------------------------------------

def chk_serveur_roles_documentes(is_admin=False):
    return _result("na", "macOS Server n'existe plus depuis Mojave")


def chk_serveur_sauvegarde(is_admin=False):
    """
    Time Machine : équivalent de la sauvegarde sur Mac.
    tmutil status nous dit si TM est actif.
    """
    out, ok = sh("tmutil destinationinfo 2>/dev/null", timeout=10)
    if not ok:
        return _result("attention",
                       "Time Machine non configuré ou inaccessible")
    if "Name" in out or "Kind" in out:
        return _result("ok", "Destination Time Machine configurée")
    return _result("attention", "Aucune destination Time Machine")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

CHECKS = {
    "firewall_actif": chk_firewall_actif,
    "antivirus_present": chk_antivirus_present,
    "antivirus_ajour": chk_antivirus_ajour,
    "chiffrement_disque": chk_chiffrement_disque,
    "maj_recentes": chk_maj_recentes,
    "os_supporte": chk_os_supporte,
    "admins_limites": chk_admins_limites,
    "admin_natif_desactive": chk_admin_natif_desactive,
    "mdp_jamais_expire": chk_mdp_jamais_expire,
    "rdp_maitrise": chk_rdp_maitrise,
    "uac_actif": chk_uac_actif,
    "smbv1_desactive": chk_smbv1_desactive,
    "partages_maitrises": chk_partages_maitrises,
    "espace_disque": chk_espace_disque,
    "uptime_raisonnable": chk_uptime_raisonnable,
    "serveur_roles_documentes": chk_serveur_roles_documentes,
    "serveur_sauvegarde": chk_serveur_sauvegarde,
}


def run_checks(profil, is_admin=False, progress_cb=None):
    """Lance les contrôles applicables. profil='mac' attendu."""
    # Sur Mac, les "contrôles serveur" sont N/A par construction
    serveur_only = {"serveur_roles_documentes"}  # serveur_sauvegarde devient TimeMachine, donc applicable

    ids = list(CHECKS.keys())
    total = len(ids)
    resultats = []
    for i, cid in enumerate(ids):
        if progress_cb:
            progress_cb(i + 1, total, cid)
        if cid in serveur_only:
            resultats.append({"id": cid, "statut": "na",
                              "detail": "Non applicable (macOS)"})
            continue
        try:
            r = CHECKS[cid](is_admin=is_admin)
        except Exception as e:
            r = _result("indetermine", f"Erreur contrôle : {e}")
        resultats.append({"id": cid, **r})
    return resultats
