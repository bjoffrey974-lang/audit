"""
Contrôles de conformité sécurité Windows (postes et serveurs).

Chaque contrôle exécute une commande PowerShell ciblée et interprète le
résultat en statut : ok | attention | critique | indetermine | na

Conçu pour fonctionner en local. Les fonctions acceptent un paramètre
`runner` (par défaut PowerShell local) pour permettre une extension distante
ultérieure (WinRM) sans réécrire la logique.

Les contrôles nécessitant des droits admin renvoient "indetermine" si l'agent
n'est pas élevé (jamais un faux "ok").

IDs alignés sur conformite_ref.py (référentiel partagé avec la plateforme).
"""
import subprocess
import platform
import json
import re
from datetime import datetime, timedelta

IS_WINDOWS = platform.system().lower().startswith("win")


# ---------------------------------------------------------------------------
# Exécution PowerShell
# ---------------------------------------------------------------------------

def ps(command, timeout=20):
    """
    Exécute une commande PowerShell et retourne (stdout, ok).
    ok=False si erreur d'exécution / timeout / hors Windows.
    """
    if not IS_WINDOWS:
        return ("", False)
    try:
        full = ["powershell", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", command]
        r = subprocess.run(full, capture_output=True, text=True,
                           timeout=timeout)
        if r.returncode != 0:
            return (r.stdout.strip() or r.stderr.strip(), False)
        return (r.stdout.strip(), True)
    except Exception:
        return ("", False)


def _result(statut, detail=""):
    return {"statut": statut, "detail": detail}


# ---------------------------------------------------------------------------
# Détection du profil de la machine (poste / serveur)
# ---------------------------------------------------------------------------

def detect_profil():
    """
    Retourne 'poste' ou 'serveur' via ProductType WMI.
    ProductType : 1 = Workstation, 2 = Domain Controller, 3 = Server.
    """
    out, ok = ps("(Get-CimInstance Win32_OperatingSystem).ProductType")
    if ok and out.strip().isdigit():
        return "poste" if out.strip() == "1" else "serveur"
    return "poste"  # défaut prudent


# ---------------------------------------------------------------------------
# CONTRÔLES (un par mesure du référentiel)
# Chaque fonction : (is_admin) -> {"statut":..., "detail":...}
# ---------------------------------------------------------------------------

def chk_firewall_actif(is_admin=False):
    out, ok = ps("(Get-NetFirewallProfile | Select-Object -ExpandProperty Enabled) -join ','")
    if not ok:
        return _result("indetermine", "Profils pare-feu non lisibles")
    vals = [v.strip().lower() for v in out.split(",") if v.strip()]
    if not vals:
        return _result("indetermine")
    actifs = sum(1 for v in vals if v in ("true", "1"))
    if actifs == len(vals):
        return _result("ok", f"{actifs}/{len(vals)} profils actifs")
    if actifs == 0:
        return _result("critique", "Pare-feu désactivé sur tous les profils")
    return _result("attention", f"Pare-feu actif sur {actifs}/{len(vals)} profils seulement")


def chk_antivirus_present(is_admin=False):
    # Security Center (postes). Sur serveurs, SecurityCenter2 n'existe pas -> Defender.
    out, ok = ps(
        "Get-CimInstance -Namespace root/SecurityCenter2 -Class AntiVirusProduct "
        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty displayName")
    if ok and out.strip():
        return _result("ok", "AV détecté : " + out.strip().replace("\n", ", "))
    # Fallback Defender
    out2, ok2 = ps("(Get-MpComputerStatus).AntivirusEnabled")
    if ok2 and out2.strip().lower() == "true":
        return _result("ok", "Microsoft Defender actif")
    if ok2 and out2.strip().lower() == "false":
        return _result("critique", "Aucun antivirus actif détecté")
    return _result("indetermine", "État antivirus non déterminable")


def chk_antivirus_ajour(is_admin=False):
    out, ok = ps("(Get-MpComputerStatus).AntivirusSignatureAge")
    if ok and out.strip().isdigit():
        age = int(out.strip())
        if age <= 3:
            return _result("ok", f"Signatures de {age} jour(s)")
        if age <= 7:
            return _result("attention", f"Signatures de {age} jours")
        return _result("critique", f"Signatures anciennes ({age} jours)")
    return _result("indetermine", "Âge des signatures non lisible (AV tiers ?)")


def chk_chiffrement_disque(is_admin=False):
    if not is_admin:
        return _result("indetermine", "Nécessite les droits administrateur")
    out, ok = ps(
        "(Get-BitLockerVolume -MountPoint $env:SystemDrive "
        "-ErrorAction SilentlyContinue).ProtectionStatus")
    if not ok:
        return _result("indetermine", "BitLocker non interrogeable")
    val = out.strip().lower()
    if val in ("on", "1"):
        return _result("ok", "BitLocker actif sur le disque système")
    if val in ("off", "0"):
        return _result("attention", "BitLocker inactif sur le disque système")
    return _result("indetermine", f"État BitLocker : {out.strip() or 'inconnu'}")


def chk_maj_recentes(is_admin=False):
    out, ok = ps(
        "(Get-HotFix | Sort-Object InstalledOn -Descending | "
        "Select-Object -First 1).InstalledOn.ToString('yyyy-MM-dd')")
    if not ok or not out.strip():
        return _result("indetermine", "Date de dernière MAJ non lisible")
    try:
        d = datetime.strptime(out.strip(), "%Y-%m-%d")
        jours = (datetime.now() - d).days
        if jours <= 60:
            return _result("ok", f"Dernière MAJ il y a {jours} jours")
        if jours <= 120:
            return _result("attention", f"Dernière MAJ il y a {jours} jours")
        return _result("critique", f"Dernière MAJ il y a {jours} jours")
    except ValueError:
        return _result("indetermine", "Format de date inattendu")


# Dates de fin de support des Windows courants (simplifié, à actualiser)
WINDOWS_EOL = {
    "10": datetime(2025, 10, 14),   # Windows 10 (toutes éditions grand public)
    "8.1": datetime(2023, 1, 10),
    "7": datetime(2020, 1, 14),
    "2012": datetime(2023, 10, 10),
    "2016": datetime(2027, 1, 12),
    "2019": datetime(2029, 1, 9),
    "2022": datetime(2031, 10, 14),
}

def chk_os_supporte(is_admin=False):
    out, ok = ps("(Get-CimInstance Win32_OperatingSystem).Caption")
    if not ok or not out.strip():
        return _result("indetermine", "Version OS non lisible")
    caption = out.strip()
    now = datetime.now()
    for key, eol in WINDOWS_EOL.items():
        if key in caption:
            if now > eol:
                return _result("critique",
                               f"{caption} en fin de support depuis {eol:%m/%Y}")
            if now > eol - timedelta(days=180):
                return _result("attention",
                               f"{caption} : fin de support proche ({eol:%m/%Y})")
            return _result("ok", f"{caption} supporté")
    # Windows 11 ou inconnu -> considéré OK mais on note la version
    if "11" in caption:
        return _result("ok", caption)
    return _result("ok", caption + " (date EOL non référencée)")


def chk_admins_limites(is_admin=False):
    out, ok = ps(
        "(Get-LocalGroupMember -Group 'Administrateurs' -ErrorAction SilentlyContinue) "
        ".Count; if(-not $?){ (Get-LocalGroupMember -Group 'Administrators').Count }")
    # Récupère le premier nombre trouvé
    m = re.search(r"\d+", out or "")
    if ok and m:
        n = int(m.group())
        if n <= 2:
            return _result("ok", f"{n} compte(s) administrateur local")
        if n <= 4:
            return _result("attention", f"{n} comptes administrateurs locaux")
        return _result("critique", f"{n} comptes administrateurs locaux (trop)")
    return _result("indetermine", "Membres du groupe Administrateurs non lisibles")


def chk_admin_natif_desactive(is_admin=False):
    # Compte natif = SID se terminant par -500
    out, ok = ps(
        "(Get-LocalUser | Where-Object { $_.SID -like 'S-1-5-*-500' }).Enabled")
    if not ok or not out.strip():
        return _result("indetermine", "Compte Administrateur natif non lisible")
    val = out.strip().lower()
    if val == "false":
        return _result("ok", "Compte Administrateur natif désactivé")
    if val == "true":
        return _result("attention", "Compte Administrateur natif activé")
    return _result("indetermine")


def chk_mdp_jamais_expire(is_admin=False):
    out, ok = ps(
        "(Get-LocalUser | Where-Object { $_.Enabled -and $_.PasswordExpires -eq $null "
        "-and $_.PasswordRequired }).Count")
    m = re.search(r"\d+", out or "")
    if ok and m:
        n = int(m.group())
        if n == 0:
            return _result("ok", "Aucun compte actif sans expiration de mot de passe")
        return _result("attention", f"{n} compte(s) avec mot de passe sans expiration")
    return _result("indetermine", "Comptes locaux non lisibles")


def chk_rdp_maitrise(is_admin=False):
    out, ok = ps(
        "(Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' "
        "-Name fDenyTSConnections -ErrorAction SilentlyContinue).fDenyTSConnections")
    if not ok or out.strip() == "":
        return _result("indetermine", "État RDP non lisible")
    val = out.strip()
    if val == "1":
        return _result("ok", "Bureau à distance (RDP) désactivé")
    if val == "0":
        # RDP activé : vérifier si NLA est requis (atténuation)
        nla, nok = ps(
            "(Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server"
            "\\WinStations\\RDP-Tcp' -Name UserAuthentication "
            "-ErrorAction SilentlyContinue).UserAuthentication")
        if nok and nla.strip() == "1":
            return _result("attention", "RDP activé (NLA requis)")
        return _result("critique", "RDP activé sans NLA")
    return _result("indetermine")


def chk_uac_actif(is_admin=False):
    out, ok = ps(
        "(Get-ItemProperty 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion"
        "\\Policies\\System' -Name EnableLUA -ErrorAction SilentlyContinue).EnableLUA")
    if not ok or out.strip() == "":
        return _result("indetermine", "État UAC non lisible")
    if out.strip() == "1":
        return _result("ok", "UAC activé")
    return _result("critique", "UAC désactivé")


def chk_smbv1_desactive(is_admin=False):
    out, ok = ps(
        "(Get-SmbServerConfiguration -ErrorAction SilentlyContinue).EnableSMB1Protocol")
    if not ok or out.strip() == "":
        # Fallback : feature optionnelle
        out2, ok2 = ps(
            "(Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol "
            "-ErrorAction SilentlyContinue).State")
        if ok2 and out2.strip().lower() == "disabled":
            return _result("ok", "SMBv1 désactivé")
        if ok2 and out2.strip().lower() == "enabled":
            return _result("critique", "SMBv1 activé (obsolète, risque)")
        return _result("indetermine", "État SMBv1 non lisible")
    val = out.strip().lower()
    if val == "false":
        return _result("ok", "SMBv1 désactivé")
    if val == "true":
        return _result("critique", "SMBv1 activé (obsolète, risque)")
    return _result("indetermine")


def chk_partages_maitrises(is_admin=False):
    # Partages hors partages administratifs par défaut (C$, ADMIN$, IPC$)
    out, ok = ps(
        "(Get-SmbShare -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Name -notmatch '\\$$' }).Name -join ','")
    if not ok:
        return _result("indetermine", "Partages non lisibles")
    partages = [p for p in out.split(",") if p.strip()]
    if not partages:
        return _result("ok", "Aucun partage réseau personnalisé")
    if len(partages) <= 5:
        return _result("ok", f"{len(partages)} partage(s) : " + ", ".join(partages[:5]))
    return _result("attention", f"{len(partages)} partages exposés")


def chk_espace_disque(is_admin=False):
    out, ok = ps(
        "$d = Get-PSDrive -Name ($env:SystemDrive.TrimEnd(':')); "
        "[math]::Round($d.Free / ($d.Used + $d.Free) * 100, 1)")
    if not ok or not out.strip():
        return _result("indetermine", "Espace disque non lisible")
    try:
        pct = float(out.strip().replace(",", "."))
        if pct >= 15:
            return _result("ok", f"{pct}% d'espace libre")
        if pct >= 10:
            return _result("attention", f"{pct}% d'espace libre")
        return _result("critique", f"Espace disque critique : {pct}% libre")
    except ValueError:
        return _result("indetermine")


def chk_uptime_raisonnable(is_admin=False):
    out, ok = ps(
        "[math]::Round(((Get-Date) - (Get-CimInstance Win32_OperatingSystem)"
        ".LastBootUpTime).TotalDays, 1)")
    if not ok or not out.strip():
        return _result("indetermine", "Uptime non lisible")
    try:
        jours = float(out.strip().replace(",", "."))
        if jours <= 30:
            return _result("ok", f"Démarré il y a {jours} jours")
        if jours <= 60:
            return _result("attention", f"Pas de redémarrage depuis {jours} jours")
        return _result("attention", f"Uptime élevé : {jours} jours")
    except ValueError:
        return _result("indetermine")


# --- Contrôles spécifiques serveurs ---

def chk_serveur_roles_documentes(is_admin=False):
    out, ok = ps(
        "(Get-WindowsFeature -ErrorAction SilentlyContinue | "
        "Where-Object Installed | Select-Object -ExpandProperty Name) -join ','")
    if not ok:
        return _result("indetermine", "Rôles serveur non lisibles")
    roles = [r for r in out.split(",") if r.strip()]
    if roles:
        return _result("ok", f"{len(roles)} rôle(s)/fonctionnalité(s) installés")
    return _result("indetermine", "Aucun rôle détecté")


def chk_serveur_sauvegarde(is_admin=False):
    # Heuristique : présence de Windows Server Backup ou tâche de sauvegarde
    out, ok = ps(
        "(Get-WindowsFeature Windows-Server-Backup -ErrorAction SilentlyContinue)"
        ".Installed")
    if ok and out.strip().lower() == "true":
        return _result("ok", "Windows Server Backup installé")
    return _result("indetermine",
                   "Solution de sauvegarde à vérifier manuellement")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

# Mapping id du référentiel -> fonction de contrôle
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
    """
    Lance les contrôles applicables au profil donné.
    profil : 'poste' ou 'serveur'.
    Retourne une liste [{"id":..., "statut":..., "detail":...}, ...].
    """
    # Contrôles spécifiques serveurs : ignorés (statut 'na') sur un poste
    serveur_only = {"serveur_roles_documentes", "serveur_sauvegarde"}

    ids = list(CHECKS.keys())
    total = len(ids)
    resultats = []
    for i, cid in enumerate(ids):
        if progress_cb:
            progress_cb(i + 1, total, cid)
        if cid in serveur_only and profil != "serveur":
            resultats.append({"id": cid, "statut": "na", "detail": "Non applicable (poste)"})
            continue
        try:
            r = CHECKS[cid](is_admin=is_admin)
        except Exception as e:
            r = _result("indetermine", f"Erreur contrôle : {e}")
        resultats.append({"id": cid, **r})
    return resultats
