"""
Collecte détaillée d'un poste / serveur Windows ("winaudit-like").

Chaque fonction retourne une liste de dicts ou un dict, en gérant proprement
les échecs (retourne [] ou {} avec une clé d'erreur si la commande PowerShell
plante, jamais d'exception non gérée).

Les listes peuvent être volumineuses (200 applis, 500 KB, etc.) — c'est
attendu et géré côté agent (progression + export JSON unique).

Utilise la fonction ps() du module checks pour exécuter PowerShell.
"""
import json
import re

try:
    import checks
except ImportError:
    from . import checks


# ---------------------------------------------------------------------------
# Helper : exécute du PowerShell qui renvoie du JSON
# ---------------------------------------------------------------------------

def _ps_json(command, timeout=60):
    """
    Exécute une commande PowerShell censée renvoyer du JSON
    (typiquement via ConvertTo-Json).
    Retourne (data, ok) où data est l'objet parsé ou None.

    La commande est enveloppée dans un script block & { ... } pour que le pipe
    final '| ConvertTo-Json' s'applique au RÉSULTAT du bloc entier, même si
    la commande utilise plusieurs lignes. Sans ça, PowerShell traite le
    '| ConvertTo-Json' sur la nouvelle ligne comme une commande séparée et
    plante silencieusement (bug observé sur Windows 11 25H2).
    """
    full = f"& {{\n{command}\n}} | ConvertTo-Json -Depth 4 -Compress"
    out, ok = checks.ps(full, timeout=timeout)
    if not ok or not out.strip():
        return (None, False)
    try:
        data = json.loads(out)
        # ConvertTo-Json renvoie un objet si 1 élément, une liste si plusieurs.
        # On normalise toujours en liste.
        if isinstance(data, dict):
            return ([data], True)
        if isinstance(data, list):
            return (data, True)
        return (None, False)
    except json.JSONDecodeError:
        return (None, False)


# ---------------------------------------------------------------------------
# Applications installées
# ---------------------------------------------------------------------------

def collect_applications():
    """
    Liste des logiciels installés (toutes architectures : 32 et 64 bits, par
    machine et par utilisateur).
    Lecture directe du registre Uninstall (méthode robuste, indépendante du
    fournisseur de gestion de packages).
    """
    cmd = r"""
$paths = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$apps = foreach ($p in $paths) {
    Get-ItemProperty $p -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -and -not $_.SystemComponent } |
    Select-Object @{N='nom';E={$_.DisplayName}},
                  @{N='version';E={$_.DisplayVersion}},
                  @{N='editeur';E={$_.Publisher}},
                  @{N='date_install';E={$_.InstallDate}},
                  @{N='taille_ko';E={$_.EstimatedSize}}
}
# Déduplique sur (nom, version)
$apps | Sort-Object nom, version -Unique
"""
    data, ok = _ps_json(cmd)
    if not ok:
        return []
    # Normalise la date InstallDate (yyyyMMdd) en yyyy-MM-dd
    for a in data:
        d = a.get("date_install")
        if isinstance(d, str) and re.fullmatch(r"\d{8}", d):
            a["date_install"] = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    return data


# ---------------------------------------------------------------------------
# Mises à jour Windows (KB)
# ---------------------------------------------------------------------------

def collect_updates():
    """
    Liste des mises à jour Windows installées.

    Combine 2 sources :
    - Update Session COM (Microsoft.Update.Session) : couvre les MAJ modernes
      (cumulatives, drivers, Defender). Lent mais complet.
    - Get-HotFix : fallback / complément pour les hotfixes traditionnels.
    """
    # Source 1 : Update Session COM (la plus complète)
    cmd = """
$session = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
$count = $searcher.GetTotalHistoryCount()
if ($count -gt 0) {
    $history = $searcher.QueryHistory(0, $count)
    $history | Where-Object { $_.ResultCode -eq 2 -and $_.Title } |
    ForEach-Object {
        [PSCustomObject]@{
            kb = if ($_.Title -match 'KB\\d+') { $matches[0] } else { '' }
            type = $_.Title
            installe_par = ''
            date_install = if ($_.Date) { $_.Date.ToString('yyyy-MM-dd') } else { '' }
        }
    } | Sort-Object date_install -Descending
}
"""
    data, ok = _ps_json(cmd, timeout=60)
    if ok and data and len(data) > 5:
        return data
    # Fallback : Get-HotFix (limité aux hotfixes traditionnels)
    cmd2 = """
Get-HotFix -ErrorAction SilentlyContinue |
Select-Object @{N='kb';E={$_.HotFixID}},
              @{N='type';E={$_.Description}},
              @{N='installe_par';E={$_.InstalledBy}},
              @{N='date_install';E={if($_.InstalledOn){$_.InstalledOn.ToString('yyyy-MM-dd')}else{''}}} |
Sort-Object date_install -Descending
"""
    data, ok = _ps_json(cmd2)
    return data or []


# ---------------------------------------------------------------------------
# Comptes utilisateurs locaux
# ---------------------------------------------------------------------------

def collect_users():
    """
    Liste détaillée des comptes locaux. Utilise Get-LocalUser avec fallback
    WMI Win32_UserAccount (insensible au bug Azure AD).
    """
    # Tentative 1 : Get-LocalUser
    cmd = """
Get-LocalUser -ErrorAction SilentlyContinue |
Select-Object @{N='nom';E={$_.Name}},
              @{N='active';E={$_.Enabled}},
              @{N='description';E={$_.Description}},
              @{N='derniere_connexion';E={if($_.LastLogon){$_.LastLogon.ToString('yyyy-MM-dd HH:mm')}else{''}}},
              @{N='mdp_jamais_expire';E={$_.PasswordExpires -eq $null}},
              @{N='mdp_requis';E={$_.PasswordRequired}},
              @{N='source';E={$_.PrincipalSource}},
              @{N='sid';E={$_.SID.Value}}
"""
    data, ok = _ps_json(cmd)
    if ok and data:
        return data
    # Fallback WMI
    cmd2 = """
Get-CimInstance Win32_UserAccount -Filter "LocalAccount=True" |
Select-Object @{N='nom';E={$_.Name}},
              @{N='active';E={-not $_.Disabled}},
              @{N='description';E={$_.Description}},
              @{N='mdp_jamais_expire';E={$_.PasswordExpires -eq $false}},
              @{N='mdp_requis';E={$_.PasswordRequired}},
              @{N='sid';E={$_.SID}}
"""
    data, ok = _ps_json(cmd2)
    return data or []


# ---------------------------------------------------------------------------
# Services Windows
# ---------------------------------------------------------------------------

def collect_services():
    """
    Services Windows. Utilise Get-Service (rapide) + enrichissement par CIM
    pour le type de démarrage et le compte. Si CIM trop lent, on garde
    juste Get-Service.
    """
    # Étape 1 : Get-Service seul (très rapide, donne nom + état)
    cmd_fast = """
Get-Service -ErrorAction SilentlyContinue |
Select-Object @{N='nom';E={$_.Name}},
              @{N='nom_affiche';E={$_.DisplayName}},
              @{N='etat';E={$_.Status.ToString()}},
              @{N='demarrage';E={$_.StartType.ToString()}}
"""
    data, ok = _ps_json(cmd_fast, timeout=60)
    if not ok:
        return []
    services = data or []

    # Étape 2 : enrichir avec le compte d'exécution (via CIM, plus lent)
    cmd_accounts = """
Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
Select-Object @{N='nom';E={$_.Name}}, @{N='compte';E={$_.StartName}}
"""
    accounts_data, ok2 = _ps_json(cmd_accounts, timeout=120)
    if ok2 and accounts_data:
        # Indexer par nom puis enrichir
        accounts = {a.get("nom"): a.get("compte") for a in accounts_data}
        for s in services:
            s["compte"] = accounts.get(s.get("nom"), "")
    else:
        for s in services:
            s["compte"] = ""
    return services


# ---------------------------------------------------------------------------
# Pilotes (drivers)
# ---------------------------------------------------------------------------

def collect_drivers():
    """Pilotes signés (Win32_PnPSignedDriver)."""
    cmd = """
Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue |
Where-Object { $_.DeviceName } |
Select-Object @{N='peripherique';E={$_.DeviceName}},
              @{N='fabricant';E={$_.Manufacturer}},
              @{N='version';E={$_.DriverVersion}},
              @{N='date';E={if($_.DriverDate){$_.DriverDate.ToString('yyyy-MM-dd')}else{''}}},
              @{N='classe';E={$_.DeviceClass}} |
Sort-Object peripherique
"""
    data, ok = _ps_json(cmd, timeout=90)
    return data or []


# ---------------------------------------------------------------------------
# Tâches planifiées
# ---------------------------------------------------------------------------

def collect_scheduled_tasks():
    """
    Tâches planifiées non Microsoft (les Microsoft Windows sont trop bruyantes,
    ~300 par défaut, on les filtre).
    """
    cmd = r"""
Get-ScheduledTask -ErrorAction SilentlyContinue |
Where-Object { $_.TaskPath -notlike '\Microsoft\Windows\*' } |
ForEach-Object {
    $info = $_ | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue
    [PSCustomObject]@{
        nom = $_.TaskName
        chemin = $_.TaskPath
        etat = $_.State.ToString()
        derniere_exec = if($info.LastRunTime){$info.LastRunTime.ToString('yyyy-MM-dd HH:mm')}else{''}
        compte = $_.Principal.UserId
    }
}
"""
    data, ok = _ps_json(cmd, timeout=60)
    return data or []


# ---------------------------------------------------------------------------
# Règles pare-feu activées
# ---------------------------------------------------------------------------

def collect_firewall_rules():
    """
    Règles pare-feu actives qui autorisent du trafic ENTRANT.
    On limite aux Inbound/Allow (les plus pertinentes en audit) — l'outbound
    est massif et beaucoup moins informatif.
    """
    cmd = """
Get-NetFirewallRule -ErrorAction SilentlyContinue |
Where-Object { $_.Enabled -eq 'True' -and $_.Action -eq 'Allow' -and $_.Direction -eq 'Inbound' } |
Select-Object @{N='nom';E={$_.DisplayName}},
              @{N='direction';E={$_.Direction.ToString()}},
              @{N='profil';E={$_.Profile.ToString()}},
              @{N='action';E={$_.Action.ToString()}}
"""
    data, ok = _ps_json(cmd, timeout=120)
    return data or []


# ---------------------------------------------------------------------------
# Sessions ouvertes / utilisateurs connectés
# ---------------------------------------------------------------------------

def collect_sessions():
    """
    Sessions / utilisateurs connectés.
    quser n'est pas disponible sur Win11 Famille → fallback CIM.
    """
    # Méthode 1 : quser (Win10/11 Pro+, Server)
    cmd1 = r"""
$result = $null
try { $out = quser 2>$null } catch { $out = $null }
if ($out) {
    $lines = $out -split "`n" | Select-Object -Skip 1
    $result = foreach ($l in $lines) {
        $cols = $l -split '\s+' | Where-Object { $_ }
        if ($cols.Count -ge 3) {
            [PSCustomObject]@{
                utilisateur = $cols[0]
                etat = $cols[2]
                session = $cols[1]
                source = 'quser'
            }
        }
    }
}
$result
"""
    data, ok = _ps_json(cmd1, timeout=15)
    if ok and data:
        return data
    # Méthode 2 : fallback CIM (Win11 Famille, sans quser)
    cmd2 = """
Get-CimInstance Win32_LogonSession -ErrorAction SilentlyContinue |
Where-Object { $_.LogonType -in 2,10,11 } |
ForEach-Object {
    $sid = $_.LogonId
    $user = Get-CimInstance Win32_LoggedOnUser -ErrorAction SilentlyContinue |
        Where-Object { $_.Dependent.LogonId -eq $sid } |
        Select-Object -First 1
    if ($user) {
        $name = $user.Antecedent.Name
        $domain = $user.Antecedent.Domain
        $logonTypes = @{2='Interactive'; 10='RemoteInteractive'; 11='CachedInteractive'}
        [PSCustomObject]@{
            utilisateur = "$domain\\$name"
            etat = 'Active'
            session = $logonTypes[[int]$_.LogonType]
            source = 'CIM'
        }
    }
}
"""
    data, ok = _ps_json(cmd2, timeout=30)
    return data or []


# ---------------------------------------------------------------------------
# Logiciels d'accès distant (TeamViewer, AnyDesk, VNC, etc.)
# ---------------------------------------------------------------------------

REMOTE_KEYWORDS = [
    "teamviewer", "anydesk", "ammyy", "tightvnc", "ultravnc", "realvnc",
    "logmein", "splashtop", "remotepc", "screenconnect", "connectwise",
    "rustdesk", "supremo", "zoho assist", "bomgar", "beyondtrust",
    "chrome remote desktop", "dameware", "kaseya",
]

def detect_remote_access(applications):
    """
    Détecte les logiciels d'accès à distance présents en croisant la liste
    des applications avec une base de mots-clés connus.
    """
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
# Événements de sécurité récents (échecs d'authentification)
# ---------------------------------------------------------------------------

def collect_auth_failures(days=30, limit=50):
    """
    Échecs d'authentification des N derniers jours (Event ID 4625).
    Nécessite des droits admin.
    """
    cmd = f"""
$since = (Get-Date).AddDays(-{days})
Get-WinEvent -FilterHashtable @{{LogName='Security'; Id=4625; StartTime=$since}} `
    -MaxEvents {limit} -ErrorAction SilentlyContinue |
Select-Object @{{N='date';E={{$_.TimeCreated.ToString('yyyy-MM-dd HH:mm')}}}},
              @{{N='message';E={{($_.Message -split "`n")[0]}}}}
"""
    data, ok = _ps_json(cmd, timeout=30)
    return data or []


# ---------------------------------------------------------------------------
# Volumes / partitions
# ---------------------------------------------------------------------------

def collect_volumes():
    """État des volumes : lettre, capacité, libre, système de fichiers, BitLocker."""
    cmd = """
Get-Volume -ErrorAction SilentlyContinue |
Where-Object { $_.DriveLetter } |
Select-Object @{N='lettre';E={$_.DriveLetter}},
              @{N='label';E={$_.FileSystemLabel}},
              @{N='fs';E={$_.FileSystem}},
              @{N='taille_go';E={[math]::Round($_.Size/1GB,1)}},
              @{N='libre_go';E={[math]::Round($_.SizeRemaining/1GB,1)}},
              @{N='etat';E={$_.HealthStatus}}
"""
    data, ok = _ps_json(cmd)
    return data or []


# ---------------------------------------------------------------------------
# Cartes réseau
# ---------------------------------------------------------------------------

def collect_network():
    """Configuration réseau détaillée."""
    cmd = """
Get-NetIPConfiguration -ErrorAction SilentlyContinue |
Where-Object { $_.NetAdapter.Status -eq 'Up' } |
ForEach-Object {
    [PSCustomObject]@{
        interface = $_.InterfaceAlias
        mac = $_.NetAdapter.MacAddress
        ip = $_.IPv4Address.IPAddress -join ','
        masque = $_.IPv4Address.PrefixLength -join ','
        passerelle = $_.IPv4DefaultGateway.NextHop
        dns = ($_.DNSServer.ServerAddresses -join ',')
    }
}
"""
    data, ok = _ps_json(cmd)
    return data or []


# ---------------------------------------------------------------------------
# Orchestration : collecte tout
# ---------------------------------------------------------------------------

# Liste des collecteurs avec libellé pour la GUI
COLLECTORS = [
    ("applications",     "Applications installées",       collect_applications),
    ("updates",          "Mises à jour Windows",          collect_updates),
    ("users",            "Comptes utilisateurs locaux",   collect_users),
    ("services",         "Services Windows",              collect_services),
    ("drivers",          "Pilotes",                       collect_drivers),
    ("scheduled_tasks",  "Tâches planifiées (non MS)",    collect_scheduled_tasks),
    ("firewall_rules",   "Règles pare-feu actives",       collect_firewall_rules),
    ("sessions",         "Sessions ouvertes",             collect_sessions),
    ("volumes",          "Volumes / partitions",          collect_volumes),
    ("network",          "Configuration réseau",          collect_network),
    ("auth_failures",    "Échecs d'authentification (30j)", collect_auth_failures),
]


def collect_all(progress_cb=None):
    """
    Lance toutes les collectes. progress_cb(i, total, label) optionnel.
    Retourne un dict { 'applications': [...], 'updates': [...], ... }
    + une section dérivée 'remote_access' croisée sur les applications.
    """
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

    # Section dérivée : logiciels d'accès distant détectés
    if details.get("applications"):
        details["remote_access"] = detect_remote_access(details["applications"])
    else:
        details["remote_access"] = []

    return details


# ---------------------------------------------------------------------------
# Compteurs (pour affichage GUI)
# ---------------------------------------------------------------------------

def count_summary(details):
    """Renvoie un dict de compteurs lisibles depuis details."""
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
