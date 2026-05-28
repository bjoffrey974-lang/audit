# Audit Agent

Agent Windows d'**audit de poste/serveur** : inventaire matériel & système +
**17 contrôles de conformité sécurité** (référentiel maison aligné sur le Guide
d'hygiène informatique de l'ANSSI). Produit un fichier JSON `inventaire_poste`
importable dans la plateforme d'audit.

## Ce qu'il collecte

**Inventaire système** : nom d'hôte, marque, modèle, n° série, CPU, RAM, stockage,
OS + version/build, IP, MAC.

**17 contrôles de conformité** (statuts : Conforme / Attention / Critique / Indéterminé) :
pare-feu, antivirus, BitLocker, MAJ, fin de vie Windows, comptes admin, RDP,
UAC, SMBv1, partages, espace disque, uptime, et 2 contrôles serveurs.

**Collecte détaillée « winaudit-like »** (depuis v1.1) — listes brutes pour l'audit :
- Applications installées (nom, version, éditeur, date d'installation)
- Mises à jour Windows (toutes les KB avec date)
- Comptes utilisateurs locaux (état, mot de passe, dernière connexion)
- Services Windows (état, démarrage, compte d'exécution)
- Pilotes (fabricant, version, date)
- Tâches planifiées non Microsoft
- Règles pare-feu actives
- Sessions ouvertes
- Volumes / partitions
- Configuration réseau (interfaces, DNS, passerelle)
- Échecs d'authentification récents (30j, nécessite admin)
- **Logiciels d'accès distant détectés** (TeamViewer, AnyDesk, VNC, LogMeIn…)
  — croisement automatique avec la liste des applications.

## Élévation administrateur

L'agent tente de s'élever (UAC) au lancement, car plusieurs contrôles
(BitLocker, comptes locaux, registre) nécessitent les droits admin. Sans
élévation, ces contrôles sont marqués **« indéterminé »** — jamais un faux
« conforme ». L'interface indique clairement le mode (admin / standard).

## Utilisation

```
python agent_gui.py
```

1. Accepter l'élévation UAC (recommandé pour un audit complet).
2. Cliquer **▶ Lancer l'audit**.
3. Le tableau se remplit : chaque contrôle avec son statut coloré et son détail.
4. Le **score** et le **verdict** (Conforme / Partiellement / Non conforme)
   s'affichent en haut.
5. **💾 Enregistrer le JSON…** → fichier `inventaire_<machine>_<date>.json`.
6. Dans la plateforme d'audit : ouvrir l'audit → **⬇ Importer** → choisir ce
   fichier. La machine et son bilan de conformité apparaissent dans l'onglet
   **Conformité**, et le score est identique à celui affiché par l'agent.

## Cohérence du score

Le calcul du score est **identique** entre l'agent (affichage immédiat) et la
plateforme (après import) : même pondération par criticité, un point critique
force le verdict « non conforme ». Le poste affiché par l'agent = le poste
affiché par la plateforme.

## Profil poste / serveur

L'agent détecte automatiquement le type de machine (Win32 ProductType) et
active les contrôles spécifiques serveurs (rôles, sauvegarde) uniquement sur
les serveurs. Sur un poste, ces contrôles sont marqués « N/A ».

## Fichiers

```
agent/
├── agent_gui.py    # interface Tkinter (point d'entrée, onglets Conformité + Détails)
├── checks.py       # les 17 contrôles de conformité
├── collect.py      # inventaire matériel/OS (CPU, RAM, IP, MAC…)
├── details.py      # collecte détaillée (applis, MAJ, comptes, services, FW…)
├── elevation.py    # détection admin + auto-élévation UAC + fallback
├── build.txt       # packaging PyInstaller (.exe)
└── README.md
```

## Durée d'un audit

- Conformité seule (17 contrôles) : ~5 secondes
- Conformité + collecte détaillée complète : 20 secondes à 2 minutes selon la
  machine (le poste vs serveur avec beaucoup d'historique de patches).

La GUI affiche une barre de progression détaillée à chaque étape.

## Limites

- Windows uniquement (l'agent lit le système via PowerShell).
- Audit **local** (la machine où il tourne). L'audit distant (WinRM) pourra
  être ajouté ultérieurement sans réécriture (les contrôles acceptent déjà un
  paramètre d'exécution).
- Sans droits admin : contrôles BitLocker / comptes locaux en « indéterminé ».
- Un AV peut flaguer l'exe PyInstaller non signé (usage interne : sans gravité).

## Format de sortie (extrait)

```json
{
  "type": "inventaire_poste",
  "date": "2026-05-28T21:00:00",
  "outil": "audit-agent", "version": "1.0",
  "profil": "poste",
  "machine": { "nom_hote": "PC-01", "ip": "192.168.1.45", "os": "Windows 11 Pro", ... },
  "conformite": [
    { "id": "firewall_actif", "statut": "ok", "detail": "3/3 profils actifs" },
    { "id": "chiffrement_disque", "statut": "attention", "detail": "BitLocker inactif" }
  ]
}
```
