# Audit IT

Application Flask de prise en charge des audits informatiques chez les clients.

Pendant l'audit, chaque élément découvert (FW, switch, serveur, NAS, imprimante, etc.)
est saisi via un formulaire à onglets ; **le schéma réseau se construit en temps réel**
à droite de l'écran. Drag & drop pour repositionner. Exports finaux : PDF (rapport
suivant la trame), Excel (inventaire matériel) et SVG/PNG (schéma seul).

## Stack

- Python 3.11+ / Flask 3 / Flask-SQLAlchemy
- SQLite (BD locale dans `instance/audit.db`)
- Gunicorn (production) + Nginx (reverse proxy)
- ReportLab (PDF), openpyxl (Excel), CairoSVG (PNG — optionnel)
- Frontend : HTML/CSS/JS vanilla, SVG natif (aucun framework)

## Trame d'audit couverte (suivant document HTP)

1. Contact (identité, adresse, groupe, tél, horaires)
2. Type d'activité
3. Sites & connexions Internet (FAI, débit, type, backup, IP publique)
4. Plan d'adressage IP (sous-réseaux, plages DHCP)
5. Inventaire équipements (firewall, routeur, switch, AP WiFi, serveur,
   hyperviseur, NAS/SAN, IPBX, imprimante, poste, onduleur, etc.)
6. Liaisons (ethernet, fibre, WiFi, VPN, SD-WAN, SIP trunk)
7. Serveurs & virtualisation (OS, CPU, RAM, RAID, VM, rôle)
8. Sécurité (antivirus, VPN, IDS/IPS, accès distant — par site)
9. Téléphonie VoIP (PABX, softphone, IPBX)
10. Imprimantes / scanners
11. Applications métier (ERP, CRM, GED, éditeur, support, criticité)
12. Sauvegardes (périmètre, solution, type, fréquence, cible, rétention)
13. Messagerie (solution, protocole, domaine, MX, antispam, adresses)
14. Problèmes récurrents / documentation existante

## Déploiement sur Debian 13 (Trixie)

### Méthode automatique (recommandée)

```bash
# Décompresser le ZIP sur le serveur
sudo bash deploy.sh
```

Le script :
- crée l'utilisateur système `audit`,
- copie les sources dans `/opt/audit-it`,
- crée un virtualenv et installe les dépendances,
- installe le service systemd `audit-it.service`,
- déploie la conf Nginx (à adapter pour le `server_name`).

### Méthode manuelle

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx

# Utilisateur dédié
sudo useradd -r -s /usr/sbin/nologin -d /opt/audit-it audit
sudo mkdir -p /opt/audit-it /var/log/audit-it
sudo chown -R audit:audit /var/log/audit-it

# Copier les sources
sudo cp -r ./* /opt/audit-it/
sudo chown -R audit:audit /opt/audit-it

# Virtualenv
sudo -u audit python3 -m venv /opt/audit-it/venv
sudo -u audit /opt/audit-it/venv/bin/pip install -r /opt/audit-it/requirements.txt

# Optionnel pour l'export PNG
sudo apt install -y libcairo2 libpango-1.0-0
sudo -u audit /opt/audit-it/venv/bin/pip install cairosvg

# Service systemd
sudo cp /opt/audit-it/audit-it.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now audit-it.service

# Nginx
sudo cp /opt/audit-it/nginx.conf.sample /etc/nginx/sites-available/audit-it
sudo ln -s /etc/nginx/sites-available/audit-it /etc/nginx/sites-enabled/
# … ajuster server_name dans le fichier …
sudo nginx -t && sudo systemctl reload nginx

# HTTPS (Let's Encrypt)
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d audit.myithead.com
```

## Configuration

Variables d'environnement (à passer dans `/etc/systemd/system/audit-it.service`) :

| Variable           | Défaut             | Rôle                                    |
|--------------------|--------------------|-----------------------------------------|
| `SECRET_KEY`       | `change-me-in-prod`| Clé Flask (sessions, CSRF)              |
| `ADMIN_PASSWORD`   | `AuditIT@2026`     | (réservé, pas encore utilisé en MVP)    |

## Développement local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py        # écoute sur 0.0.0.0:5002
```

Ouvrir http://localhost:5002/.

## Workflow d'audit

1. **Accueil** → "+ Nouvel audit" → choisir un client existant ou en créer un.
2. **Onglet Contact** : remplir identité, adresse, contact, activité.
3. **Onglet Sites & Internet** : un site par défaut a été créé. Éditer son adresse,
   FAI, débit, IP publique, plan IP. Ajouter d'autres sites si besoin.
4. **Onglet Équipements** : cliquer sur un type (Firewall, Switch, Serveur…). Un
   nouvel équipement apparaît dans le schéma et un modal s'ouvre pour la saisie
   détaillée (marque, modèle, IP, VLAN, rôle…).
5. **Schéma temps réel** : à droite, le schéma se met à jour. Glisser les boîtes,
   double-cliquer pour rééditer. Toggle Logique/Physique.
6. **Onglet Liaisons** : connecter les équipements (ethernet, fibre, WiFi, VPN,
   SD-WAN, SIP trunk). VLAN et débit visibles sur le schéma.
7. **Onglet Serveurs/VM** : compléter OS, CPU, RAM, RAID, rôles AD/DNS/DHCP…
8. **Onglet Sécurité** : antivirus, VPN, IDS/IPS, accès distant par site.
9. **Onglets Applications, Sauvegardes, Messagerie** : autant d'entrées que nécessaire.
10. **Onglet Problèmes/Doc** : zone libre pour problèmes récurrents et documentation.
11. **Exports** (en haut à droite) :
    - 📄 PDF — rapport complet suivant la trame d'audit
    - 📊 Excel — inventaire matériel + sites + liaisons + apps + backups + messagerie
    - 🖼 SVG — schéma seul, vectoriel
    - 🖼 PNG — idem rasterisé (si CairoSVG installé)
    - ⛶ Schéma plein écran

## Architecture des fichiers

```
audit-it/
├── app.py                 # Flask app + routes (API JSON, pages HTML, exports)
├── models.py              # SQLAlchemy : Client, Audit, Site, Equipement,
│                          #             Liaison, Application, Sauvegarde, Messagerie
├── exports.py             # PDF (reportlab), Excel (openpyxl), SVG, PNG
├── requirements.txt
├── audit-it.service       # systemd unit
├── nginx.conf.sample
├── deploy.sh              # installation automatisée Debian 13
├── templates/
│   ├── base.html
│   ├── index.html         # liste des audits
│   ├── nouveau.html       # création audit
│   ├── audit.html         # page principale (formulaire + SVG live)
│   └── schema.html        # vue plein écran du schéma
├── static/
│   ├── css/style.css
│   ├── js/app.js          # logique formulaire, autosave, modaux
│   └── js/schema.js       # rendu SVG, drag & drop, auto-layout
└── instance/
    └── audit.db           # BD SQLite (créée au premier démarrage)
```

## Notes pour évolutions futures

- Auth (login admin pour publier l'app en clientèle).
- Import winaudit (XML) pour pré-remplir l'inventaire postes.
- Récupération SNMP/SSH directe pour scanner les équipements sur place.
- Versioning des audits (delta entre 2 audits du même client).
- Import/export JSON d'audits complets.

## Sauvegarde

La base est dans `/opt/audit-it/instance/audit.db`. Pour la sauvegarder :

```bash
sudo -u audit cp /opt/audit-it/instance/audit.db /backup/audit-it-$(date +%F).db
```

## Logs

```bash
journalctl -u audit-it -f
tail -f /var/log/audit-it/access.log /var/log/audit-it/error.log
```
