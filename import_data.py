"""
Import de données collectées par les outils Windows (scanner réseau, agent poste).

Format JSON attendu (contrat commun scanner / agent / plateforme) :

{
  "type": "scan_reseau" | "inventaire_poste",
  "date": "2026-05-28T10:30:00",
  "outil": "audit-scanner",
  "version": "1.0",
  "sous_reseau": "192.168.1.0/24",        # scan_reseau uniquement
  "equipements": [
    {
      "ip": "192.168.1.1",
      "mac": "00:11:22:33:44:55",
      "constructeur": "Fortinet",          # déduit de l'OUI MAC
      "hostname": "FW-HTP",
      "type_suppose": "firewall",          # déduit des ports / constructeur
      "ports_ouverts": [443, 22],
      # champs facultatifs (agent poste) :
      "os": "Windows 11 Pro",
      "os_version": "23H2",
      "cpu": "Intel i5-12500",
      "ram": "16 Go",
      "stockage": "512 Go SSD",
      "marque": "Dell",
      "modele": "OptiPlex 7010",
      "numero_serie": "ABC123"
    }
  ]
}

Règle de dédoublonnage : un équipement déjà présent dans l'audit (même IP non vide,
ou à défaut même MAC) est MIS À JOUR (champs vides complétés) plutôt que dupliqué.
"""

# Mapping ports ouverts -> type d'équipement supposé (du plus spécifique au plus générique)
PORT_SIGNATURES = [
    ({9100, 515, 631}, "imprimante"),       # RAW/LPD/IPP
    ({5060, 5061}, "ipbx"),                  # SIP
    ({3389}, "poste"),                       # RDP -> souvent poste/serveur Windows
    ({445, 139}, "serveur_physique"),        # SMB -> serveur de fichiers / Windows
    ({80, 443}, "autre"),                    # web (trop générique seul)
    ({22}, "autre"),                         # SSH (Linux/réseau)
]

# Mapping constructeur (OUI) -> type probable
CONSTRUCTEUR_TYPE = {
    "fortinet": "firewall",
    "mikrotik": "routeur",
    "cisco": "switch",
    "hpe": "serveur_physique",
    "hewlett": "serveur_physique",
    "dell": "poste",
    "synology": "nas",
    "qnap": "nas",
    "ubiquiti": "ap_wifi",
    "aruba": "ap_wifi",
    "xorcom": "ipbx",
    "yealink": "telephone",
    "brother": "imprimante",
    "canon": "imprimante",
    "epson": "imprimante",
    "kyocera": "imprimante",
    "ricoh": "imprimante",
    "apc": "onduleur",
    "eaton": "onduleur",
}

# Champs autorisés à l'import (sécurité : on ne mappe que ces clés)
CHAMPS_IMPORT = (
    "nom_hote", "marque", "modele", "numero_serie", "ip", "mac", "vlan",
    "role", "os", "os_version", "cpu", "ram", "stockage", "raid",
    "commentaires",
)


def deduire_type(item):
    """Devine le type d'équipement à partir du constructeur puis des ports."""
    # 1) Si l'outil a déjà proposé un type valide, on le respecte
    from models import TYPES_EQUIPEMENT
    t = (item.get("type_suppose") or "").strip().lower()
    if t in TYPES_EQUIPEMENT:
        return t
    # 2) Constructeur
    constructeur = (item.get("constructeur") or "").lower()
    for cle, type_eq in CONSTRUCTEUR_TYPE.items():
        if cle in constructeur:
            return type_eq
    # 3) Ports ouverts
    ports = set(item.get("ports_ouverts") or [])
    for signature, type_eq in PORT_SIGNATURES:
        if signature & ports:
            return type_eq
    return "autre"


def importer_payload(audit, payload, db, Equipement):
    """
    Applique un payload d'import à un audit.
    Retourne un dict de stats : {crees, maj, ignores, total}.
    """
    items = payload.get("equipements") or []
    existants = Equipement.query.filter_by(audit_id=audit.id).all()
    # Index par IP et par MAC pour le dédoublonnage
    par_ip = {e.ip: e for e in existants if e.ip}
    par_mac = {e.mac.lower(): e for e in existants if e.mac}

    # Position de départ pour les nouveaux (en grille, sous l'existant)
    base_idx = len(existants)
    cols = 6

    stats = {"crees": 0, "maj": 0, "ignores": 0, "total": len(items)}

    for item in items:
        ip = (item.get("ip") or "").strip()
        mac = (item.get("mac") or "").strip()
        # Cherche un équipement existant
        cible = None
        if ip and ip in par_ip:
            cible = par_ip[ip]
        elif mac and mac.lower() in par_mac:
            cible = par_mac[mac.lower()]

        if cible:
            # MAJ : ne remplit que les champs vides (ne pas écraser la saisie manuelle)
            modifie = False
            for champ in CHAMPS_IMPORT:
                val = item.get(champ)
                if val and not getattr(cible, champ, None):
                    setattr(cible, champ, val)
                    modifie = True
            if modifie:
                stats["maj"] += 1
            else:
                stats["ignores"] += 1
        else:
            # Création
            idx = base_idx + stats["crees"]
            eq = Equipement(
                audit_id=audit.id,
                type=deduire_type(item),
                pos_x=40 + (idx % cols) * 140,
                pos_y=40 + (idx // cols) * 110,
            )
            for champ in CHAMPS_IMPORT:
                val = item.get(champ)
                if val:
                    setattr(eq, champ, val)
            # nom par défaut si rien
            if not eq.nom_hote:
                eq.nom_hote = item.get("hostname") or ip or "Équipement importé"
            # mémorise les ports en commentaire si pas déjà rempli
            ports = item.get("ports_ouverts")
            if ports and not eq.commentaires:
                eq.commentaires = "Ports ouverts: " + ", ".join(str(p) for p in ports)
            db.session.add(eq)
            # indexe pour éviter les doublons dans le même import
            if ip:
                par_ip[ip] = eq
            if mac:
                par_mac[mac.lower()] = eq
            stats["crees"] += 1

    db.session.commit()
    return stats


def importer_inventaire_poste(audit, payload, db, Equipement, Conformite):
    """
    Importe un inventaire de poste/serveur (avec bloc conformité éventuel).
    Crée/met à jour l'équipement, et enregistre un bilan de conformité.
    Retourne {equipement_id, conformite_id, score, niveau, action}.
    """
    import json as _json
    from conformite_ref import calcul_score, niveau_global

    machine = payload.get("machine") or {}
    ip = (machine.get("ip") or "").strip()
    mac = (machine.get("mac") or "").strip()
    nom = machine.get("nom_hote") or machine.get("hostname") or ip or "Poste importé"
    profil = payload.get("profil") or "poste"
    eq_type = "serveur_physique" if profil == "serveur" else "poste"

    # Cherche un équipement existant (par IP puis MAC)
    existants = Equipement.query.filter_by(audit_id=audit.id).all()
    cible = None
    if ip:
        cible = next((e for e in existants if e.ip == ip), None)
    if not cible and mac:
        cible = next((e for e in existants if e.mac and e.mac.lower() == mac.lower()), None)

    action = "maj"
    if not cible:
        idx = len(existants)
        cible = Equipement(
            audit_id=audit.id, type=eq_type,
            pos_x=40 + (idx % 6) * 140, pos_y=40 + (idx // 6) * 110,
        )
        db.session.add(cible)
        action = "cree"

    # Remplit les champs machine (complète les vides + champs techniques)
    for champ in ("nom_hote", "marque", "modele", "numero_serie", "ip", "mac",
                  "os", "os_version", "cpu", "ram", "stockage"):
        val = machine.get(champ)
        if val and not getattr(cible, champ, None):
            setattr(cible, champ, val)
    if not cible.nom_hote:
        cible.nom_hote = nom
    db.session.flush()

    # --- Bloc conformité ---
    conformite_id = None
    score = None
    niveau = "indetermine"
    resultats = payload.get("conformite") or []
    if resultats:
        calc = calcul_score(resultats)
        score = calc["score"]
        niveau = niveau_global(score, calc["nb_critiques"])
        conf = Conformite(
            audit_id=audit.id,
            equipement_id=cible.id,
            machine=nom,
            profil=profil,
            date_collecte=payload.get("date"),
            outil=payload.get("outil"),
            version_outil=payload.get("version"),
            score=score,
            niveau=niveau,
            nb_critiques=calc["nb_critiques"],
            resultats_json=_json.dumps(resultats, ensure_ascii=False),
        )
        # Bloc details (agent v1.1+) — optionnel
        details = payload.get("details")
        if details:
            conf.details_json = _json.dumps(details, ensure_ascii=False)
        db.session.add(conf)
        db.session.flush()
        conformite_id = conf.id

    db.session.commit()
    return {
        "equipement_id": cible.id,
        "conformite_id": conformite_id,
        "score": score,
        "niveau": niveau,
        "action": action,
    }
