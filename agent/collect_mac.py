"""
Collecte de l'inventaire matériel et système d'un Mac.
Utilise system_profiler -json (disponible depuis Catalina 10.15).
Retourne un dict 'machine' au format attendu par la plateforme d'audit
(identique au format Windows pour que l'import fonctionne sans changement).
"""
import socket
import platform

try:
    from shell_mac import sh, sh_json
except ImportError:
    from .shell_mac import sh, sh_json


def _first(lst):
    return lst[0] if isinstance(lst, list) and lst else {}


def collect_machine():
    """Retourne le dict d'inventaire de la machine locale."""
    info = {
        "nom_hote": "", "marque": "Apple", "modele": "", "numero_serie": "",
        "ip": "", "mac": "", "os": "", "os_version": "",
        "cpu": "", "ram": "", "stockage": "",
    }

    # Nom d'hôte
    info["nom_hote"] = socket.gethostname()

    # --- Hardware (modèle, série, CPU, RAM, architecture) ---
    data, ok = sh_json("system_profiler SPHardwareDataType -json", timeout=30)
    if ok:
        hw = _first(data.get("SPHardwareDataType", []))
        if hw:
            info["modele"] = hw.get("machine_model", "") or hw.get("machine_name", "")
            info["numero_serie"] = hw.get("serial_number", "")
            # CPU : sur Apple Silicon, c'est "chip_type" ; sur Intel, "cpu_type"
            info["cpu"] = (hw.get("chip_type")
                           or hw.get("cpu_type")
                           or hw.get("processor_name", ""))
            # RAM : "physical_memory" est une string genre "16 GB"
            ram = hw.get("physical_memory", "")
            if ram:
                info["ram"] = ram.replace("GB", "Go").strip()

    # --- OS (nom complet + version) ---
    data, ok = sh_json("system_profiler SPSoftwareDataType -json", timeout=30)
    if ok:
        sw = _first(data.get("SPSoftwareDataType", []))
        if sw:
            # os_version contient quelque chose comme "macOS 14.5 (23F79)"
            full_os = sw.get("os_version", "")
            info["os"] = full_os.split(" (")[0] if full_os else "macOS"
            # Extraire juste la version numérique pour os_version
            import re
            m = re.search(r"(\d+(?:\.\d+)+)", full_os)
            if m:
                info["os_version"] = m.group(1)
            # Si build présent entre parenthèses, l'ajouter
            mb = re.search(r"\(([^)]+)\)", full_os)
            if mb:
                info["os_version"] = f"{info['os_version']} ({mb.group(1)})"

    # --- Stockage : volume principal ---
    data, ok = sh_json("system_profiler SPStorageDataType -json", timeout=30)
    if ok:
        storages = data.get("SPStorageDataType", [])
        # Trouver le volume "Macintosh HD" ou racine
        main = None
        for s in storages:
            if s.get("mount_point") == "/":
                main = s
                break
        if not main and storages:
            main = storages[0]
        if main:
            size = main.get("size_in_bytes", 0)
            if isinstance(size, (int, float)) and size > 0:
                gb = round(size / 1024**3)
                info["stockage"] = f"{gb} Go"

    # --- Réseau : IP + MAC de l'interface active ---
    # On utilise "route get default" pour trouver l'interface par défaut,
    # puis ifconfig pour lire IP et MAC.
    iface_out, ok = sh(
        "route -n get default 2>/dev/null | awk '/interface:/ {print $2}'",
        timeout=10)
    iface = iface_out.strip() if ok else ""
    if iface:
        # IP
        ip_out, ok = sh(f"ipconfig getifaddr {iface} 2>/dev/null", timeout=10)
        if ok and ip_out.strip():
            info["ip"] = ip_out.strip()
        # MAC : ifconfig <iface> | awk '/ether/ {print $2}'
        mac_out, ok = sh(
            f"ifconfig {iface} 2>/dev/null | awk '/ether/ {{print $2}}'",
            timeout=10)
        if ok and mac_out.strip():
            info["mac"] = mac_out.strip().lower()

    # Fallback IP si rien trouvé via route default
    if not info["ip"]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            info["ip"] = s.getsockname()[0]
            s.close()
        except Exception:
            pass

    return info


def detect_profil():
    """
    Sur Mac, on retourne toujours 'mac' (pas de distinction poste/serveur
    significative — macOS Server n'existe plus depuis Mojave).
    La plateforme reconnaîtra ce profil et adaptera les contrôles applicables.
    """
    return "mac"
