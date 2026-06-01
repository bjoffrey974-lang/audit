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


# Mapping des rôles Windows Server (nom technique → acronyme court pour l'audit).
# Couvre les rôles les plus courants. Ce qui n'est pas mappé prend son DisplayName.
WINDOWS_ROLES_SHORT = {
    "AD-Domain-Services":         "AD DS",
    "ADRMS":                      "AD RMS",
    "ADCS":                       "AD CS",
    "ADFS-Federation":            "AD FS",
    "ADLDS":                      "AD LDS",
    "DHCP":                       "DHCP",
    "DNS":                        "DNS",
    "Fax":                        "Fax",
    "FileAndStorage-Services":    "File Services",
    "File-Services":              "File Services",
    "Hyper-V":                    "Hyper-V",
    "NPAS":                       "NPS",
    "Print-Services":             "Print Services",
    "Remote-Desktop-Services":    "RDS",
    "RDS":                        "RDS",
    "RemoteAccess":               "RAS",
    "Routing":                    "Routing",
    "ServerEssentialsRole":       "Server Essentials",
    "UpdateServices":             "WSUS",
    "WDS":                        "WDS",
    "WSUS":                       "WSUS",
    "Web-Server":                 "IIS",
    "Application-Server":         "App Server",
    "VolumeActivation":           "KMS",
    "WindowsServerBackup":        "Backup",
}


# Applications "métier" à fort enjeu commercial qu'on souhaite faire remonter
# automatiquement dans l'onglet 7 (Applications métier) de l'audit.
# Chaque entrée déclare comment matcher l'application détectée par l'agent et
# quelles métadonnées injecter dans la fiche.
#
# matchers : liste de motifs CHERCHÉS DANS LE NOM de l'application installée
#   (insensible à la casse, sous-chaîne — donc "office" matche aussi
#    "Microsoft 365 Apps for Business"). On veut être STRICT, donc on ne
#    déclare ici que ce qui a un vrai intérêt en audit commercial.
# type    : valeur métier qu'on pré-remplit (correspond aux types existants
#           dans le dropdown UI)
# editeur : pré-rempli (peut être affiné après par l'auditeur)
APPLICATIONS_METIER_DETECTABLES = [
    # --- Bureautique / collaboration ---
    {"nom": "Microsoft Office / 365",
     "matchers": ["microsoft 365", "office 365", "microsoft office",
                  "office professional", "office home", "office standard"],
     "editeur": "Microsoft", "type": "bureautique"},
    {"nom": "Microsoft Teams",
     "matchers": ["microsoft teams"],
     "editeur": "Microsoft", "type": "communication"},
    {"nom": "Zoom",
     "matchers": ["zoom workplace", "zoom client", "zoom meetings"],
     "editeur": "Zoom", "type": "communication"},
    {"nom": "LibreOffice",
     "matchers": ["libreoffice"],
     "editeur": "The Document Foundation", "type": "bureautique"},
    {"nom": "Adobe Acrobat",
     "matchers": ["adobe acrobat"],
     "editeur": "Adobe", "type": "bureautique"},

    # --- Comptabilité / Gestion / ERP ---
    {"nom": "Sage 100",
     "matchers": ["sage 100"],
     "editeur": "Sage", "type": "comptabilité"},
    {"nom": "Sage X3",
     "matchers": ["sage x3"],
     "editeur": "Sage", "type": "ERP"},
    {"nom": "EBP",
     "matchers": ["ebp comptabilit", "ebp gestion", "ebp paye"],
     "editeur": "EBP", "type": "comptabilité"},
    {"nom": "Cegid",
     "matchers": ["cegid"],
     "editeur": "Cegid", "type": "ERP"},
    {"nom": "Ciel",
     "matchers": ["ciel compta", "ciel gestion", "ciel paye"],
     "editeur": "Ciel / Sage", "type": "comptabilité"},

    # --- Antivirus / Sécurité ---
    {"nom": "Bitdefender",
     "matchers": ["bitdefender"],
     "editeur": "Bitdefender", "type": "sécurité"},
    {"nom": "ESET",
     "matchers": ["eset endpoint", "eset nod32", "eset smart"],
     "editeur": "ESET", "type": "sécurité"},
    {"nom": "Kaspersky",
     "matchers": ["kaspersky"],
     "editeur": "Kaspersky", "type": "sécurité"},
    {"nom": "Norton",
     "matchers": ["norton 360", "norton security"],
     "editeur": "NortonLifeLock", "type": "sécurité"},
    {"nom": "Sophos",
     "matchers": ["sophos"],
     "editeur": "Sophos", "type": "sécurité"},
    {"nom": "McAfee",
     "matchers": ["mcafee"],
     "editeur": "McAfee", "type": "sécurité"},
    {"nom": "Malwarebytes",
     "matchers": ["malwarebytes"],
     "editeur": "Malwarebytes", "type": "sécurité"},

    # --- Sauvegarde ---
    {"nom": "Veeam",
     "matchers": ["veeam"],
     "editeur": "Veeam", "type": "sauvegarde"},
    {"nom": "Acronis",
     "matchers": ["acronis"],
     "editeur": "Acronis", "type": "sauvegarde"},
    {"nom": "Macrium",
     "matchers": ["macrium reflect"],
     "editeur": "Macrium", "type": "sauvegarde"},

    # --- Accès distant ---
    {"nom": "TeamViewer",
     "matchers": ["teamviewer"],
     "editeur": "TeamViewer", "type": "accès distant"},
    {"nom": "AnyDesk",
     "matchers": ["anydesk"],
     "editeur": "AnyDesk SE", "type": "accès distant"},
    {"nom": "Splashtop",
     "matchers": ["splashtop"],
     "editeur": "Splashtop", "type": "accès distant"},

    # --- Métier vertical (WinDev/HFSQL — important pour les clients Boyer) ---
    {"nom": "WinDev",
     "matchers": ["windev", "webdev"],
     "editeur": "PC SOFT", "type": "développement"},
    {"nom": "HFSQL",
     "matchers": ["hfsql"],
     "editeur": "PC SOFT", "type": "base de données"},
]


def _detecter_applications_metier(applications_detectees):
    """
    Filtre les applications collectées par l'agent pour ne garder que celles
    qui correspondent à la liste blanche des applications "métier".

    Retourne un dict {nom_canonique: {nom, editeur, type, version_observee}}.
    Si plusieurs applications de l'agent matchent la même entrée de liste
    blanche (ex: Office 365 + Microsoft 365 Apps), on n'en remonte qu'une.
    """
    if not applications_detectees:
        return {}
    detectes = {}
    for app in applications_detectees:
        nom_app = (app.get("nom") or "").lower()
        if not nom_app:
            continue
        for entry in APPLICATIONS_METIER_DETECTABLES:
            if any(m in nom_app for m in entry["matchers"]):
                if entry["nom"] not in detectes:
                    detectes[entry["nom"]] = {
                        "nom": entry["nom"],
                        "editeur": entry["editeur"],
                        "type": entry["type"],
                        "version_observee": (app.get("version") or "").strip(),
                    }
                break  # ne pas matcher plusieurs entries pour la même app
    return detectes


def _roles_to_short_label(server_roles):
    """
    Convertit une liste de server_roles (collectés par l'agent) en string
    courte type 'AD DS, DNS, DHCP, IIS' pour le champ Rôle/Fonction.

    Pour chaque rôle, on prend l'acronyme du mapping s'il existe, sinon on
    prend le libellé Windows tronqué intelligemment (premier mot avant
    parenthèse ou virgule).
    """
    if not server_roles:
        return ""
    labels = []
    for r in server_roles:
        nom = r.get("nom", "")
        libelle = r.get("libelle", "")
        # 1. Acronyme connu ?
        if nom in WINDOWS_ROLES_SHORT:
            labels.append(WINDOWS_ROLES_SHORT[nom])
            continue
        # 2. Sinon, on utilise le libellé Windows en gardant le texte avant '('
        court = libelle.split("(")[0].strip()
        if court:
            labels.append(court)
        elif nom:
            labels.append(nom)
    # Dédoublonner tout en gardant l'ordre
    seen = []
    for l in labels:
        if l and l not in seen:
            seen.append(l)
    return ", ".join(seen)


def _process_printers(audit, poste, payload, db, Equipement):
    """
    Pour chaque imprimante détectée dans details.printers :
    - Crée ou retrouve l'équipement imprimante (dédoublonnage par IP ou marque+modèle+port)
    - Crée une liaison poste ↔ imprimante (sans doublon)
    Place l'imprimante à droite du poste qui l'a découverte.

    Note : on importe Liaison ici pour ne pas alourdir la signature de
    importer_inventaire_poste qui est déjà longue.
    """
    from models import Liaison

    details = payload.get("details") or {}
    printers = details.get("printers") or []
    if not printers:
        return {"created": 0, "linked": 0}

    # Tous les équipements existants de l'audit pour le dédoublonnage rapide
    tous_eq = Equipement.query.filter_by(audit_id=audit.id).all()
    imprimantes_existantes = [e for e in tous_eq if e.type == "imprimante"]

    created = 0
    linked = 0
    offset_idx = 0  # incrément pour étaler verticalement les nouvelles imprimantes

    for p in printers:
        ip = (p.get("ip") or "").strip()
        marque = (p.get("marque") or "").strip()
        modele = (p.get("modele") or "").strip()
        port = (p.get("port") or "").strip()
        nom_imp = (p.get("nom") or "").strip() or f"{marque} {modele}".strip() or "Imprimante"
        type_reseau = p.get("type_reseau") or "autre"

        # --- Dédoublonnage : IP d'abord, sinon marque+modèle+port ---
        cible_imp = None
        if ip:
            cible_imp = next((e for e in imprimantes_existantes
                              if (e.ip or "").strip() == ip), None)
        if not cible_imp and marque and modele:
            # Pour les USB ou imprimantes sans IP, on dédoublonne sur
            # marque+modèle uniquement (même imprimante chez plusieurs postes USB
            # est rare et bizarre, donc on accepte ce dédoublonnage souple).
            cible_imp = next(
                (e for e in imprimantes_existantes
                 if (e.marque or "").strip().lower() == marque.lower()
                 and (e.modele or "").strip().lower() == modele.lower()
                 and not (e.ip or "").strip()),  # imprimantes sans IP uniquement
                None)

        # --- Création si absente ---
        if not cible_imp:
            # Position : à droite du poste, espacée si plusieurs imprimantes
            pos_x = (poste.pos_x or 0) + 220
            pos_y = (poste.pos_y or 0) + (offset_idx * 90)
            cible_imp = Equipement(
                audit_id=audit.id,
                type="imprimante",
                nom_hote=nom_imp,
                marque=marque,
                modele=modele,
                ip=ip,
                pos_x=pos_x,
                pos_y=pos_y,
                # Le port (USB001, IP_192.168.1.50, etc.) va dans commentaires
                # pour aider à identifier ultérieurement quelle instance physique
                commentaires=f"Port : {port}" if port else None,
                role=("Imprimante USB locale" if type_reseau == "usb"
                      else "Imprimante réseau" if type_reseau == "reseau"
                      else "Imprimante partagée" if type_reseau == "partage"
                      else "Imprimante"),
            )
            db.session.add(cible_imp)
            db.session.flush()
            imprimantes_existantes.append(cible_imp)
            created += 1
            offset_idx += 1
        else:
            # Mise à jour douce : complète les champs vides sans écraser
            if ip and not (cible_imp.ip or "").strip():
                cible_imp.ip = ip
            if marque and not (cible_imp.marque or "").strip():
                cible_imp.marque = marque
            if modele and not (cible_imp.modele or "").strip():
                cible_imp.modele = modele

        # --- Liaison poste ↔ imprimante (sans doublon) ---
        existante = Liaison.query.filter_by(
            audit_id=audit.id, source_id=poste.id, dest_id=cible_imp.id).first()
        if not existante:
            # Vérif inverse aussi (peu importe le sens)
            existante = Liaison.query.filter_by(
                audit_id=audit.id, source_id=cible_imp.id, dest_id=poste.id).first()
        if not existante:
            liaison_type = "wifi" if type_reseau == "reseau" else "usb" if type_reseau == "usb" else "ethernet"
            db.session.add(Liaison(
                audit_id=audit.id,
                source_id=poste.id,
                dest_id=cible_imp.id,
                type=liaison_type,
                commentaire=f"Découverte auto via {nom_imp} ({port or 'pas de port'})",
            ))
            linked += 1

    return {"created": created, "linked": linked}


def _process_applications_metier(audit, poste, payload, db):
    """
    Pour chaque application détectée par l'agent qui correspond à la liste
    blanche APPLICATIONS_METIER_DETECTABLES :
      - Si une entrée du même nom existe déjà dans l'audit (onglet 7) :
        ajoute le nom de la machine au commentaire (sans doublon)
      - Sinon : crée une nouvelle entrée avec nom, éditeur, type, version
        et un commentaire indiquant la(les) machine(s) où elle est installée.

    Ne touche jamais aux champs déjà saisis manuellement (fournisseur_support,
    contact_support, criticité, type si modifié) — on n'écrase pas les
    annotations métier de l'auditeur.

    Retourne {created, updated}.
    """
    from models import Application

    details = payload.get("details") or {}
    apps_detectees = details.get("applications") or []
    if not apps_detectees:
        return {"created": 0, "updated": 0}

    correspondances = _detecter_applications_metier(apps_detectees)
    if not correspondances:
        return {"created": 0, "updated": 0}

    nom_poste = (poste.nom_hote or "").strip() or f"Machine #{poste.id}"
    apps_existantes = Application.query.filter_by(audit_id=audit.id).all()

    created = 0
    updated = 0
    for nom_canon, info in correspondances.items():
        # Chercher si l'application existe déjà (par nom canonique)
        cible = next(
            (a for a in apps_existantes
             if (a.nom or "").strip().lower() == nom_canon.lower()),
            None)

        if not cible:
            # --- Création ---
            commentaire = f"Détecté automatiquement sur : {nom_poste}"
            version = info.get("version_observee")
            if version:
                commentaire += f" (version observée : {version})"
            cible = Application(
                audit_id=audit.id,
                nom=info["nom"],
                editeur=info["editeur"],
                type=info["type"],
                version=version or None,
                commentaires=commentaire,
            )
            db.session.add(cible)
            apps_existantes.append(cible)
            created += 1
        else:
            # --- Enrichissement souple (ne pas écraser la saisie manuelle) ---
            modifie = False

            # Compléter les champs vides uniquement
            if not (cible.editeur or "").strip() and info["editeur"]:
                cible.editeur = info["editeur"]
                modifie = True
            if not (cible.type or "").strip() and info["type"]:
                cible.type = info["type"]
                modifie = True
            if not (cible.version or "").strip() and info.get("version_observee"):
                cible.version = info["version_observee"]
                modifie = True

            # Ajouter le nom de la machine au commentaire si pas déjà mentionné
            commentaire_actuel = cible.commentaires or ""
            if nom_poste not in commentaire_actuel:
                marqueur = "Détecté automatiquement sur :"
                if marqueur in commentaire_actuel:
                    # Ajouter à la liste existante des machines
                    cible.commentaires = commentaire_actuel.rstrip() + f", {nom_poste}"
                else:
                    # Pas encore de section auto, on l'ajoute en gardant le commentaire manuel
                    sep = "\n" if commentaire_actuel.strip() else ""
                    cible.commentaires = (commentaire_actuel
                                          + sep
                                          + f"Détecté automatiquement sur : {nom_poste}")
                modifie = True

            if modifie:
                updated += 1

    return {"created": created, "updated": updated}


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

    # Pré-remplir le champ "rôle / fonction" depuis les rôles Windows Server
    # détectés par l'agent (uniquement si le champ est vide pour préserver
    # une éventuelle annotation manuelle de l'auditeur).
    details_preview = payload.get("details") or {}
    server_roles = details_preview.get("server_roles") or []
    if server_roles and not (cible.role or "").strip():
        short = _roles_to_short_label(server_roles)
        if short:
            cible.role = short

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

    # Traitement des imprimantes découvertes (création + liaisons)
    printers_result = _process_printers(audit, cible, payload, db, Equipement)

    # Traitement des applications métier (liste blanche)
    apps_metier_result = _process_applications_metier(audit, cible, payload, db)

    db.session.commit()
    return {
        "equipement_id": cible.id,
        "conformite_id": conformite_id,
        "score": score,
        "niveau": niveau,
        "action": action,
        "printers_created": printers_result["created"],
        "printers_linked": printers_result["linked"],
        "applications_metier_created": apps_metier_result["created"],
        "applications_metier_updated": apps_metier_result["updated"],
    }
