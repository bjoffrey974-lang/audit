"""
Modèles de données pour l'outil d'audit IT.
Structure inspirée de la trame d'audit HTP.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship

db = SQLAlchemy()


# ============================================================================
# CLIENT & AUDIT
# ============================================================================

class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    groupe = db.Column(db.String(200))
    adresse = db.Column(db.Text)
    contact_nom = db.Column(db.String(200))
    contact_tel = db.Column(db.String(50))
    contact_email = db.Column(db.String(200))
    horaires = db.Column(db.String(200))
    activite = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    audits = relationship("Audit", back_populates="client", cascade="all, delete-orphan")


class Audit(db.Model):
    __tablename__ = "audits"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    date_audit = db.Column(db.Date, default=lambda: datetime.utcnow().date())
    responsable = db.Column(db.String(200))
    interlocuteur_commercial = db.Column(db.String(200))
    statut = db.Column(db.String(50), default="en_cours")  # en_cours / valide / archive
    notes_generales = db.Column(db.Text)
    problemes_recurrents = db.Column(db.Text)
    documentation_existante = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="audits")
    sites = relationship("Site", back_populates="audit", cascade="all, delete-orphan")
    equipements = relationship("Equipement", back_populates="audit", cascade="all, delete-orphan")
    liaisons = relationship("Liaison", back_populates="audit", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="audit", cascade="all, delete-orphan")
    sauvegardes = relationship("Sauvegarde", back_populates="audit", cascade="all, delete-orphan")
    messageries = relationship("Messagerie", back_populates="audit", cascade="all, delete-orphan")
    conformites = relationship("Conformite", back_populates="audit", cascade="all, delete-orphan")


# ============================================================================
# SITE (multi-sites possible)
# ============================================================================

class Site(db.Model):
    __tablename__ = "sites"

    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=False)
    nom = db.Column(db.String(200), nullable=False)
    adresse = db.Column(db.Text)
    # Connectivité Internet
    fai = db.Column(db.String(200))
    type_connexion = db.Column(db.String(100))  # fibre, ADSL, VDSL, 4G/5G, SDSL...
    debit_down = db.Column(db.String(50))
    debit_up = db.Column(db.String(50))
    ip_publique = db.Column(db.String(100))
    backup_connexion = db.Column(db.String(200))
    # Adressage
    plan_ip = db.Column(db.Text)  # sous-réseaux libellés
    plage_dhcp = db.Column(db.String(200))
    # Téléphonie
    voip_solution = db.Column(db.String(200))
    voip_pabx = db.Column(db.String(200))
    voip_softphone = db.Column(db.Boolean, default=False)
    # Sécurité globale du site
    antivirus_solution = db.Column(db.String(200))
    antivirus_gestion = db.Column(db.String(100))  # centralisée / par machine
    vpn_type = db.Column(db.String(200))
    vpn_utilisateurs = db.Column(db.Text)
    idsips_actif = db.Column(db.Boolean, default=False)
    methode_acces_distant = db.Column(db.Text)
    notes = db.Column(db.Text)

    audit = relationship("Audit", back_populates="sites")
    equipements = relationship("Equipement", back_populates="site")


# ============================================================================
# EQUIPEMENT (générique : firewall, switch, routeur, AP, serveur, NAS, IPBX,
#             imprimante, poste, etc.)
# ============================================================================

TYPES_EQUIPEMENT = [
    "firewall", "routeur", "switch", "ap_wifi", "serveur_physique",
    "serveur_virtuel", "hyperviseur", "nas", "san", "ipbx", "telephone",
    "imprimante", "scanner", "poste", "onduleur", "modem_box", "internet",
    "autre",
]

class Equipement(db.Model):
    __tablename__ = "equipements"

    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"))
    parent_id = db.Column(db.Integer, db.ForeignKey("equipements.id"))  # ex: VM dans hyperviseur

    type = db.Column(db.String(50), nullable=False)
    nom_hote = db.Column(db.String(200))
    marque = db.Column(db.String(100))
    modele = db.Column(db.String(200))
    numero_serie = db.Column(db.String(100))

    # Réseau
    ip = db.Column(db.String(50))
    mac = db.Column(db.String(50))
    vlan = db.Column(db.String(50))
    role = db.Column(db.String(500))  # AD, DNS, DHCP, file server, BDD, etc. (libre)

    # OS / Système (serveurs, postes)
    os = db.Column(db.String(200))
    os_version = db.Column(db.String(100))

    # Matériel (serveurs)
    cpu = db.Column(db.String(200))
    ram = db.Column(db.String(100))
    stockage = db.Column(db.String(200))
    raid = db.Column(db.String(100))

    # Stockage (NAS/SAN)
    capacite_totale = db.Column(db.String(100))
    taux_occupation = db.Column(db.String(50))
    date_mise_service = db.Column(db.String(50))

    # Virtualisation
    nb_vm = db.Column(db.Integer)

    # Position dans le schéma (drag & drop)
    pos_x = db.Column(db.Float, default=0)
    pos_y = db.Column(db.Float, default=0)
    # Position physique (rack/baie)
    rack = db.Column(db.String(50))
    rack_u = db.Column(db.String(50))

    commentaires = db.Column(db.Text)

    audit = relationship("Audit", back_populates="equipements")
    site = relationship("Site", back_populates="equipements")
    enfants = relationship("Equipement", backref=db.backref("parent", remote_side=[id]))


# ============================================================================
# LIAISON entre équipements (câblage logique ou physique)
# ============================================================================

class Liaison(db.Model):
    __tablename__ = "liaisons"

    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("equipements.id"), nullable=False)
    dest_id = db.Column(db.Integer, db.ForeignKey("equipements.id"), nullable=False)

    type = db.Column(db.String(50))  # ethernet, fibre, wifi, vpn, sdwan, sip-trunk
    port_source = db.Column(db.String(50))
    port_dest = db.Column(db.String(50))
    vlan = db.Column(db.String(50))
    debit = db.Column(db.String(50))
    commentaire = db.Column(db.String(500))

    audit = relationship("Audit", back_populates="liaisons")
    source = relationship("Equipement", foreign_keys=[source_id])
    dest = relationship("Equipement", foreign_keys=[dest_id])


# ============================================================================
# APPLICATIONS MÉTIER
# ============================================================================

class Application(db.Model):
    __tablename__ = "applications"

    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=False)
    nom = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(100))  # ERP, CRM, GED, métier, etc.
    editeur = db.Column(db.String(200))
    version = db.Column(db.String(100))
    fournisseur_support = db.Column(db.String(200))
    contact_support = db.Column(db.String(200))
    serveur_hote_id = db.Column(db.Integer, db.ForeignKey("equipements.id"))
    criticite = db.Column(db.String(50))  # faible / moyenne / haute / critique
    commentaires = db.Column(db.Text)

    audit = relationship("Audit", back_populates="applications")
    serveur_hote = relationship("Equipement", foreign_keys=[serveur_hote_id])


# ============================================================================
# SAUVEGARDES
# ============================================================================

class Sauvegarde(db.Model):
    __tablename__ = "sauvegardes"

    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=False)
    perimetre = db.Column(db.String(200))  # serveurs, postes, BDD, mail...
    type_sauvegarde = db.Column(db.String(100))  # full, incrémentale, snapshot, cloud
    frequence = db.Column(db.String(100))
    solution = db.Column(db.String(200))  # Veeam, Synology HyperBackup, etc.
    cible = db.Column(db.String(200))  # NAS, cloud Azure, bande, ext.
    retention = db.Column(db.String(100))
    derniere_verification = db.Column(db.String(100))
    chiffrement = db.Column(db.Boolean, default=False)
    externalisation = db.Column(db.Boolean, default=False)
    commentaires = db.Column(db.Text)

    audit = relationship("Audit", back_populates="sauvegardes")


# ============================================================================
# MESSAGERIE
# ============================================================================

class Messagerie(db.Model):
    __tablename__ = "messageries"

    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=False)
    solution = db.Column(db.String(200))  # M365, Google Workspace, OVH, autohébergé
    protocole = db.Column(db.String(100))  # IMAP+SMTP, Exchange, MAPI, Activesync
    nb_boites = db.Column(db.Integer)
    domaine = db.Column(db.String(200))
    mx_records = db.Column(db.Text)
    filtre_antispam = db.Column(db.String(200))
    adresses = db.Column(db.Text)  # liste libre
    commentaires = db.Column(db.Text)

    audit = relationship("Audit", back_populates="messageries")


# ============================================================================
# CONFORMITÉ (bilan sécurité d'une machine auditée)
# ============================================================================

class Conformite(db.Model):
    __tablename__ = "conformites"

    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=False)
    equipement_id = db.Column(db.Integer, db.ForeignKey("equipements.id"))

    machine = db.Column(db.String(200))     # nom de la machine auditée
    profil = db.Column(db.String(20))        # "poste" | "serveur"
    date_collecte = db.Column(db.String(40))
    outil = db.Column(db.String(80))
    version_outil = db.Column(db.String(40))

    score = db.Column(db.Integer)            # 0-100, ou NULL si indéterminé
    niveau = db.Column(db.String(20))        # conforme | partiel | non_conforme | indetermine
    nb_critiques = db.Column(db.Integer, default=0)

    # Détail des contrôles, stocké en JSON texte :
    # [{"id":"firewall_actif","statut":"ok","detail":"..."}, ...]
    resultats_json = db.Column(db.Text)

    # Collecte détaillée "winaudit-like" (depuis agent v1.1+)
    details_json = db.Column(db.Text)

    audit = relationship("Audit", back_populates="conformites")
    equipement = relationship("Equipement", foreign_keys=[equipement_id])
# ============================================================================

# Couleurs et icônes par type (utilisé par le générateur SVG)
EQUIP_VISUAL = {
    "internet":         {"color": "#6c757d", "icon": "🌐", "label": "Internet"},
    "modem_box":        {"color": "#adb5bd", "icon": "📡", "label": "Modem/Box"},
    "firewall":         {"color": "#dc3545", "icon": "🛡️", "label": "Pare-feu"},
    "routeur":          {"color": "#fd7e14", "icon": "🔀", "label": "Routeur"},
    "switch":           {"color": "#0d6efd", "icon": "🔌", "label": "Switch"},
    "ap_wifi":          {"color": "#20c997", "icon": "📶", "label": "AP WiFi"},
    "serveur_physique": {"color": "#198754", "icon": "🖥️", "label": "Serveur"},
    "hyperviseur":      {"color": "#0f5132", "icon": "📦", "label": "Hyperviseur"},
    "serveur_virtuel":  {"color": "#75b798", "icon": "💠", "label": "VM"},
    "nas":              {"color": "#6610f2", "icon": "💾", "label": "NAS"},
    "san":              {"color": "#520dc2", "icon": "🗄️", "label": "SAN"},
    "ipbx":             {"color": "#d63384", "icon": "☎️", "label": "IPBX"},
    "telephone":        {"color": "#e685b5", "icon": "📞", "label": "Téléphone"},
    "imprimante":       {"color": "#6f42c1", "icon": "🖨️", "label": "Imprimante"},
    "scanner":          {"color": "#8a63d2", "icon": "📠", "label": "Scanner"},
    "poste":            {"color": "#ffc107", "icon": "💻", "label": "Poste"},
    "onduleur":         {"color": "#495057", "icon": "🔋", "label": "Onduleur"},
    "autre":            {"color": "#6c757d", "icon": "❓", "label": "Autre"},
}
