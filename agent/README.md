# Audit Agent

Agent Windows d'**audit de poste/serveur** : inventaire matériel & système +
**17 contrôles de conformité sécurité** (référentiel maison aligné sur le Guide
d'hygiène informatique de l'ANSSI). Produit un fichier JSON `inventaire_poste`
importable dans la plateforme d'audit.

## Ce qu'il collecte

**Inventaire** : nom d'hôte, marque, modèle, n° série, CPU, RAM, stockage,
OS + version/build, IP, MAC.

**Conformité** (statuts : Conforme / Attention / Critique / Indéterminé) :
- Pare-feu Windows (3 profils)
- Antivirus présent + signatures à jour
- BitLocker (chiffrement disque)
- Mises à jour Windows récentes
- Version Windows supportée (fin de vie)
- Comptes administrateurs locaux maîtrisés
- Compte 'Administrateur' natif désactivé
- Mots de passe sans expiration
- Bureau à distance (RDP) maîtrisé
- UAC activé
- SMBv1 désactivé
- Partages réseau
- Espace disque, uptime
- (serveurs) rôles installés, sauvegarde

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
├── agent_gui.py    # interface Tkinter (point d'entrée)
├── checks.py       # les 17 contrôles (PowerShell + interprétation)
├── collect.py      # inventaire matériel/OS (PowerShell/CIM)
├── elevation.py    # détection admin + auto-élévation UAC + fallback
├── build.txt       # packaging PyInstaller (.exe)
└── README.md
```

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
