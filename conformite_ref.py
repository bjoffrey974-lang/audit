"""
Référentiel de conformité sécurité — postes et serveurs Windows/macOS.

Approche "maison" (pragmatique PME) avec mapping vers le Guide d'hygiène
informatique de l'ANSSI (42 règles, version 2017). Partagé entre la
plateforme d'audit et l'agent de collecte.

Chaque contrôle a :
  - id            : identifiant stable (clé)
  - libelle       : intitulé lisible
  - categorie     : regroupement d'affichage
  - anssi         : référence ANSSI structurée (voir ANSSI_REF ci-dessous)
  - profil        : "poste" | "serveur" | "both" (à qui s'applique le contrôle)
  - criticite     : poids du contrôle s'il échoue : "critique" | "majeur" | "mineur"

Le champ `anssi` est un dict {ref, libelle, url} où :
  - ref     : numéro de règle ANSSI ("R8", "R17", "R29"...) ou section ("VIII")
  - libelle : libellé court de la règle ANSSI (utilisé pour l'affichage)
  - url     : lien vers le PDF officiel ANSSI (page d'ancre si possible)

Le résultat d'un contrôle (rempli par l'agent) est l'un de :
  - "ok"           : conforme
  - "attention"    : non conforme, risque modéré
  - "critique"     : non conforme, risque élevé
  - "indetermine"  : non vérifiable (ex. droits insuffisants)
  - "na"           : non applicable à ce profil de machine
"""

# Statuts possibles d'un contrôle évalué
STATUTS = ("ok", "attention", "critique", "indetermine", "na")

# Poids pour le score (les "indetermine"/"na" sont exclus du calcul)
POIDS_CRITICITE = {"critique": 3, "majeur": 2, "mineur": 1}

# URL officielle du Guide d'hygiène informatique ANSSI (version 2017, 42 règles)
ANSSI_GUIDE_URL = "https://messervices.cyber.gouv.fr/documents-guides/guide_hygiene_informatique_anssi.pdf"


def anssi_ref(ref, libelle):
    """Helper : construit une référence ANSSI structurée."""
    return {"ref": ref, "libelle": libelle, "url": ANSSI_GUIDE_URL}


REFERENTIEL = [
    # ---------------- Protection ----------------
    {
        "id": "firewall_actif",
        "libelle": "Pare-feu local activé (tous profils)",
        "categorie": "Protection",
        "anssi": anssi_ref("R17",
                           "Activer et configurer le pare-feu local des postes de travail"),
        "profil": "both", "criticite": "critique",
    },
    {
        "id": "antivirus_present",
        "libelle": "Antivirus présent et activé",
        "categorie": "Protection",
        "anssi": anssi_ref("R14",
                           "Mettre en place un niveau de sécurité minimal sur le parc"),
        "profil": "both", "criticite": "critique",
    },
    {
        "id": "antivirus_ajour",
        "libelle": "Signatures antivirus à jour",
        "categorie": "Protection",
        "anssi": anssi_ref("R14",
                           "Mettre en place un niveau de sécurité minimal sur le parc"),
        "profil": "both", "criticite": "majeur",
    },
    {
        "id": "chiffrement_disque",
        "libelle": "Chiffrement du disque (BitLocker / FileVault) actif",
        "categorie": "Protection",
        "anssi": anssi_ref("R14",
                           "Chiffrer les partitions où sont stockées les données utilisateurs"),
        "profil": "both", "criticite": "majeur",
    },

    # ---------------- Mises à jour ----------------
    {
        "id": "maj_recentes",
        "libelle": "Mises à jour récentes (< 60 jours)",
        "categorie": "Mises à jour",
        "anssi": anssi_ref("VIII",
                           "Maintenir le système d'information à jour"),
        "profil": "both", "criticite": "critique",
    },
    {
        "id": "os_supporte",
        "libelle": "Système d'exploitation encore supporté (pas en fin de vie)",
        "categorie": "Mises à jour",
        "anssi": anssi_ref("VIII",
                           "Anticiper la fin de maintenance des composants"),
        "profil": "both", "criticite": "critique",
    },

    # ---------------- Comptes & accès ----------------
    {
        "id": "admins_limites",
        "libelle": "Nombre de comptes administrateurs locaux maîtrisé",
        "categorie": "Comptes & accès",
        "anssi": anssi_ref("R29",
                           "Limiter au strict besoin opérationnel les droits d'administration"),
        "profil": "both", "criticite": "majeur",
    },
    {
        "id": "admin_natif_desactive",
        "libelle": "Compte 'Administrateur' / 'root' natif désactivé",
        "categorie": "Comptes & accès",
        "anssi": anssi_ref("R8",
                           "Identifier nommément chaque personne accédant au système"),
        "profil": "both", "criticite": "majeur",
    },
    {
        "id": "mdp_jamais_expire",
        "libelle": "Pas de compte avec mot de passe sans expiration",
        "categorie": "Comptes & accès",
        "anssi": anssi_ref("R10",
                           "Définir et vérifier des règles de choix et de dimensionnement des mots de passe"),
        "profil": "both", "criticite": "mineur",
    },
    {
        "id": "rdp_maitrise",
        "libelle": "Bureau à distance (RDP / Screen Sharing) maîtrisé",
        "categorie": "Comptes & accès",
        "anssi": anssi_ref("R28",
                           "Utiliser un réseau dédié et cloisonné pour l'administration"),
        "profil": "both", "criticite": "majeur",
    },

    # ---------------- Configuration ----------------
    {
        "id": "uac_actif",
        "libelle": "Contrôle de compte utilisateur (UAC / SIP) activé",
        "categorie": "Configuration",
        "anssi": anssi_ref("R29",
                           "Cloisonnement des privilèges utilisateur / administrateur"),
        "profil": "both", "criticite": "majeur",
    },
    {
        "id": "smbv1_desactive",
        "libelle": "SMBv1 désactivé (protocole obsolète)",
        "categorie": "Configuration",
        "anssi": anssi_ref("VIII",
                           "Limiter l'usage de composants logiciels obsolètes"),
        "profil": "both", "criticite": "critique",
    },
    {
        "id": "partages_maitrises",
        "libelle": "Partages réseau exposés maîtrisés",
        "categorie": "Configuration",
        "anssi": anssi_ref("R9",
                           "Attribuer les bons droits sur les ressources sensibles"),
        "profil": "both", "criticite": "mineur",
    },

    # ---------------- Système ----------------
    {
        "id": "espace_disque",
        "libelle": "Espace disque système suffisant (> 10%)",
        "categorie": "Système",
        # Pas de règle ANSSI directe : bonne pratique d'exploitation.
        "anssi": {"ref": "", "libelle": "Bonne pratique d'exploitation",
                  "url": ANSSI_GUIDE_URL},
        "profil": "both", "criticite": "mineur",
    },
    {
        "id": "uptime_raisonnable",
        "libelle": "Redémarrage récent (uptime < 30 jours)",
        "categorie": "Système",
        "anssi": anssi_ref("VIII",
                           "Application effective des mises à jour"),
        "profil": "both", "criticite": "mineur",
    },

    # ---------------- Spécifique serveurs ----------------
    {
        "id": "serveur_roles_documentes",
        "libelle": "Rôles serveur identifiés (AD/DNS/DHCP/fichiers…)",
        "categorie": "Serveur",
        "anssi": anssi_ref("R4",
                           "Identifier les informations et serveurs les plus sensibles, maintenir un schéma du réseau"),
        "profil": "serveur", "criticite": "mineur",
    },
    {
        "id": "serveur_sauvegarde",
        "libelle": "Sauvegarde du serveur en place",
        "categorie": "Serveur",
        "anssi": anssi_ref("R14",
                           "Sauvegardes régulières stockées sur équipements déconnectés (niveau renforcé)"),
        "profil": "serveur", "criticite": "critique",
    },
]


def controle_by_id(cid):
    for c in REFERENTIEL:
        if c["id"] == cid:
            return c
    return None


def controles_pour_profil(profil):
    """
    Renvoie les contrôles applicables à un profil donné.
    Profils reconnus :
      - 'poste'   : poste Windows
      - 'serveur' : serveur Windows
      - 'mac'     : poste macOS (utilise les contrôles 'poste' adaptés)
    """
    if profil == "mac":
        # Sur Mac, tous les contrôles 'both' + 'poste' s'appliquent.
        # Les contrôles serveur-spécifiques sont exclus (sauf si Time Machine
        # remonte une info — l'agent Mac le décide).
        return [c for c in REFERENTIEL
                if c["profil"] in ("both", "poste")]
    return [c for c in REFERENTIEL
            if c["profil"] == "both" or c["profil"] == profil]


# Libellés alternatifs par profil pour adapter l'affichage (le contrôle reste
# le même côté logique, seul l'affichage change). Permet de dire "FileVault"
# sur Mac et "BitLocker" sur Windows pour le même id 'chiffrement_disque'.
LIBELLES_PAR_PROFIL = {
    "mac": {
        "firewall_actif": "Pare-feu macOS (Application Firewall) activé",
        "chiffrement_disque": "Chiffrement du disque (FileVault) actif",
        "uac_actif": "SIP + Gatekeeper actifs",
        "rdp_maitrise": "Screen Sharing désactivé ou maîtrisé",
        "smbv1_desactive": "SMBv1 (N/A sur macOS moderne)",
        "admin_natif_desactive": "Compte root désactivé",
        "serveur_sauvegarde": "Time Machine configurée",
    },
}


def libelle_pour(cid, profil=None):
    """Renvoie le libellé adapté au profil (ou le libellé par défaut)."""
    if profil and profil in LIBELLES_PAR_PROFIL:
        lbl = LIBELLES_PAR_PROFIL[profil].get(cid)
        if lbl:
            return lbl
    ctrl = controle_by_id(cid)
    return ctrl["libelle"] if ctrl else cid


def calcul_score(resultats):
    """
    Calcule un score de conformité (0-100) à partir d'une liste de résultats.
    resultats : liste de dicts {id, statut}.
    Les statuts 'indetermine' et 'na' sont exclus du calcul.
    Score = points obtenus / points possibles, pondéré par criticité.
    Un 'attention' compte pour la moitié des points, 'critique'/'ok' tout ou rien.
    """
    points_obtenus = 0.0
    points_possibles = 0.0
    details = {"ok": 0, "attention": 0, "critique": 0, "indetermine": 0, "na": 0}

    for r in resultats:
        statut = r.get("statut", "indetermine")
        details[statut] = details.get(statut, 0) + 1
        if statut in ("indetermine", "na"):
            continue
        ctrl = controle_by_id(r.get("id"))
        if not ctrl:
            continue
        poids = POIDS_CRITICITE.get(ctrl["criticite"], 1)
        points_possibles += poids
        if statut == "ok":
            points_obtenus += poids
        elif statut == "attention":
            points_obtenus += poids * 0.5
        # "critique" => 0 point

    score = round((points_obtenus / points_possibles) * 100) if points_possibles else None
    return {
        "score": score,                  # None si rien d'évaluable
        "details": details,
        "nb_critiques": details["critique"],
        "nb_attention": details["attention"],
    }


def niveau_global(score, nb_critiques):
    """Verdict global lisible à partir du score et du nb de points critiques."""
    if score is None:
        return "indetermine"
    if nb_critiques > 0:
        return "non_conforme"
    if score >= 85:
        return "conforme"
    if score >= 60:
        return "partiel"
    return "non_conforme"
