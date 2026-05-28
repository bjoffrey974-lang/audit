"""
Collecte de l'inventaire matériel et système d'une machine Windows.
Utilise PowerShell / CIM. Renvoie un dict 'machine' au format attendu
par la plateforme d'audit (clé "machine" du payload inventaire_poste).
"""
import platform
import socket

try:
    from checks import ps
except ImportError:
    from .checks import ps


def _first_line(s):
    return (s or "").strip().splitlines()[0].strip() if (s or "").strip() else ""


def collect_machine():
    """Retourne le dict d'inventaire de la machine locale."""
    info = {
        "nom_hote": "", "marque": "", "modele": "", "numero_serie": "",
        "ip": "", "mac": "", "os": "", "os_version": "",
        "cpu": "", "ram": "", "stockage": "",
    }

    # Nom d'hôte
    info["nom_hote"] = socket.gethostname()

    # Marque / modèle (Win32_ComputerSystem)
    out, ok = ps("$c = Get-CimInstance Win32_ComputerSystem; "
                 "Write-Output $c.Manufacturer; Write-Output $c.Model")
    if ok:
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        if len(lines) >= 1:
            info["marque"] = lines[0]
        if len(lines) >= 2:
            info["modele"] = lines[1]

    # Numéro de série (BIOS)
    out, ok = ps("(Get-CimInstance Win32_BIOS).SerialNumber")
    if ok:
        info["numero_serie"] = _first_line(out)

    # OS + version/build
    out, ok = ps("$o = Get-CimInstance Win32_OperatingSystem; "
                 "Write-Output $o.Caption; Write-Output $o.Version")
    if ok:
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        if len(lines) >= 1:
            info["os"] = lines[0]
        if len(lines) >= 2:
            info["os_version"] = lines[1]
    # Affinage version "23H2" via DisplayVersion registre (postes Win10/11)
    out, ok = ps("(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT"
                 "\\CurrentVersion' -Name DisplayVersion "
                 "-ErrorAction SilentlyContinue).DisplayVersion")
    if ok and out.strip():
        dv = _first_line(out)
        if dv:
            info["os_version"] = (info["os_version"] + f" ({dv})").strip()

    # CPU
    out, ok = ps("(Get-CimInstance Win32_Processor | "
                 "Select-Object -First 1).Name")
    if ok:
        info["cpu"] = _first_line(out)

    # RAM (Go)
    out, ok = ps("[math]::Round((Get-CimInstance Win32_ComputerSystem)"
                 ".TotalPhysicalMemory / 1GB, 0)")
    if ok and out.strip():
        info["ram"] = f"{_first_line(out)} Go"

    # Stockage (disques physiques, résumé)
    out, ok = ps("(Get-CimInstance Win32_DiskDrive | ForEach-Object "
                 "{ [math]::Round($_.Size/1GB,0).ToString() + ' Go' }) -join ' + '")
    if ok and out.strip():
        info["stockage"] = _first_line(out)

    # IP + MAC de l'interface active (celle avec passerelle)
    out, ok = ps(
        "$a = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | "
        "Select-Object -First 1; "
        "Write-Output $a.IPv4Address.IPAddress; "
        "Write-Output $a.NetAdapter.MacAddress")
    if ok:
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        if len(lines) >= 1:
            info["ip"] = lines[0]
        if len(lines) >= 2:
            info["mac"] = lines[1].replace("-", ":").lower()

    # Fallback IP si pas trouvé via gateway
    if not info["ip"]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            info["ip"] = s.getsockname()[0]
            s.close()
        except Exception:
            pass

    return info
