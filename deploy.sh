#!/bin/bash
# ============================================================================
# deploy.sh — Installation de l'outil d'audit IT sur Debian 13
# Usage : sudo bash deploy.sh
# ============================================================================
set -euo pipefail

APP_DIR=/opt/audit-it
APP_USER=audit
LOG_DIR=/var/log/audit-it

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+] $*${NC}"; }
warn() { echo -e "${YELLOW}[!] $*${NC}"; }
err()  { echo -e "${RED}[x] $*${NC}" >&2; exit 1; }

[ "$EUID" -eq 0 ] || err "Doit être lancé en root (sudo)."

log "Mise à jour des paquets…"
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip nginx git curl >/dev/null

log "Création de l'utilisateur système 'audit'…"
if ! id -u $APP_USER &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d $APP_DIR $APP_USER
fi

log "Préparation des répertoires…"
mkdir -p $APP_DIR $LOG_DIR
chown -R $APP_USER:$APP_USER $LOG_DIR

# Si on lance depuis le dossier source, copier
SRC="$(dirname "$(readlink -f "$0")")"
if [ "$SRC" != "$APP_DIR" ]; then
    log "Copie des sources depuis $SRC vers $APP_DIR…"
    rsync -a --exclude='venv' --exclude='__pycache__' --exclude='instance' \
        --exclude='.git' "$SRC"/ "$APP_DIR"/
fi

log "Création du virtualenv Python…"
sudo -u $APP_USER python3 -m venv $APP_DIR/venv
sudo -u $APP_USER $APP_DIR/venv/bin/pip install -q --upgrade pip
sudo -u $APP_USER $APP_DIR/venv/bin/pip install -q -r $APP_DIR/requirements.txt

# CairoSVG en option pour le PNG (si Cairo dispo)
log "Installation optionnelle CairoSVG pour export PNG…"
apt-get install -y libcairo2 libpango-1.0-0 libpangocairo-1.0-0 >/dev/null 2>&1 || true
sudo -u $APP_USER $APP_DIR/venv/bin/pip install -q cairosvg 2>&1 || warn "CairoSVG indisponible — l'export PNG fera un fallback SVG."

log "Préparation du répertoire instance (BD SQLite)…"
mkdir -p $APP_DIR/instance
chown -R $APP_USER:$APP_USER $APP_DIR

log "Installation du service systemd…"
cp $APP_DIR/audit-it.service /etc/systemd/system/audit-it.service
systemctl daemon-reload
systemctl enable audit-it.service
systemctl restart audit-it.service

sleep 2
if systemctl is-active --quiet audit-it.service; then
    log "Service audit-it démarré ✔"
else
    err "Le service ne démarre pas — vérifier 'journalctl -u audit-it -n 50'"
fi

# Nginx
if [ ! -f /etc/nginx/sites-available/audit-it ]; then
    log "Installation de la conf Nginx (à adapter pour ton DNS)…"
    cp $APP_DIR/nginx.conf.sample /etc/nginx/sites-available/audit-it
    ln -sf /etc/nginx/sites-available/audit-it /etc/nginx/sites-enabled/audit-it
    nginx -t && systemctl reload nginx
else
    warn "Conf Nginx déjà présente, non écrasée."
fi

log "==============================================================="
log "Installation terminée !"
log ""
log "Application :   http://127.0.0.1:5002/  (via Gunicorn)"
log "Via Nginx :     http://<ton-domaine>/   (après modif server_name)"
log ""
log "Pour le HTTPS :"
log "  apt install certbot python3-certbot-nginx"
log "  certbot --nginx -d audit.myithead.com"
log ""
log "Logs : journalctl -u audit-it -f"
log "==============================================================="
