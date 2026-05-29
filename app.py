"""
Outil d'audit IT — Application Flask.
Trame d'audit basée sur le modèle HTP.
"""
import os
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, send_file, abort, flash
)
from models import (
    db, Client, Audit, Site, Equipement, Liaison, Application,
    Sauvegarde, Messagerie, Conformite, TYPES_EQUIPEMENT, EQUIP_VISUAL
)


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-prod")
    db_path = os.path.join(app.instance_path, "audit.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "AuditIT@2026")

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)

    with app.app_context():
        db.create_all()

    # ------------------------------------------------------------------------
    # PAGES HTML
    # ------------------------------------------------------------------------
    @app.route("/")
    def index():
        clients = Client.query.order_by(Client.nom).all()
        recent = Audit.query.order_by(Audit.updated_at.desc()).limit(10).all()
        return render_template("index.html", clients=clients, recent=recent)

    @app.route("/audit/nouveau", methods=["GET", "POST"])
    def nouveau_audit():
        if request.method == "POST":
            # Crée client si nouveau, puis audit
            client_id = request.form.get("client_id")
            if client_id == "__new__":
                client = Client(nom=request.form.get("nouveau_client_nom", "").strip())
                db.session.add(client)
                db.session.flush()
                client_id = client.id
            audit = Audit(
                client_id=client_id,
                responsable=request.form.get("responsable"),
                interlocuteur_commercial=request.form.get("interlocuteur_commercial"),
                date_audit=datetime.utcnow().date(),
            )
            db.session.add(audit)
            db.session.commit()
            # Crée un site par défaut
            site = Site(audit_id=audit.id, nom="Site principal")
            db.session.add(site)
            db.session.commit()
            return redirect(url_for("audit_edit", audit_id=audit.id))

        clients = Client.query.order_by(Client.nom).all()
        return render_template("nouveau.html", clients=clients)

    @app.route("/audit/<int:audit_id>")
    def audit_edit(audit_id):
        from conformite_ref import REFERENTIEL
        audit = Audit.query.get_or_404(audit_id)
        conf_labels = {c["id"]: c["libelle"] for c in REFERENTIEL}
        return render_template(
            "audit.html",
            audit=audit,
            types_equipement=TYPES_EQUIPEMENT,
            equip_visual=EQUIP_VISUAL,
            conf_labels=conf_labels,
        )

    @app.route("/audit/<int:audit_id>/schema")
    def schema_view(audit_id):
        audit = Audit.query.get_or_404(audit_id)
        return render_template(
            "schema.html", audit=audit, equip_visual=EQUIP_VISUAL
        )

    # ------------------------------------------------------------------------
    # API JSON — audit (édition client / sites / champs globaux)
    # ------------------------------------------------------------------------
    @app.route("/api/audit/<int:audit_id>", methods=["GET"])
    def api_audit_get(audit_id):
        a = Audit.query.get_or_404(audit_id)
        return jsonify(serialize_audit(a))

    @app.route("/api/audit/<int:audit_id>", methods=["PUT"])
    def api_audit_update(audit_id):
        a = Audit.query.get_or_404(audit_id)
        data = request.get_json() or {}
        # Champs audit
        for field in ("responsable", "interlocuteur_commercial", "statut",
                      "notes_generales", "problemes_recurrents",
                      "documentation_existante"):
            if field in data:
                setattr(a, field, data[field])
        # Champs client
        client = a.client
        if "client" in data:
            for field in ("nom", "groupe", "adresse", "contact_nom",
                          "contact_tel", "contact_email", "horaires", "activite"):
                if field in data["client"]:
                    setattr(client, field, data["client"][field])
        db.session.commit()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------------
    # API JSON — sites
    # ------------------------------------------------------------------------
    @app.route("/api/audit/<int:audit_id>/sites", methods=["POST"])
    def api_site_create(audit_id):
        Audit.query.get_or_404(audit_id)
        data = request.get_json() or {}
        site = Site(audit_id=audit_id, nom=data.get("nom", "Nouveau site"))
        db.session.add(site)
        db.session.commit()
        return jsonify(serialize_site(site)), 201

    @app.route("/api/site/<int:site_id>", methods=["PUT"])
    def api_site_update(site_id):
        s = Site.query.get_or_404(site_id)
        data = request.get_json() or {}
        for field in (
            "nom", "adresse", "fai", "type_connexion", "debit_down", "debit_up",
            "ip_publique", "backup_connexion", "plan_ip", "plage_dhcp",
            "voip_solution", "voip_pabx", "voip_softphone",
            "antivirus_solution", "antivirus_gestion", "vpn_type",
            "vpn_utilisateurs", "idsips_actif", "methode_acces_distant", "notes",
        ):
            if field in data:
                setattr(s, field, data[field])
        db.session.commit()
        return jsonify(serialize_site(s))

    @app.route("/api/site/<int:site_id>", methods=["DELETE"])
    def api_site_delete(site_id):
        s = Site.query.get_or_404(site_id)
        db.session.delete(s)
        db.session.commit()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------------
    # API JSON — équipements
    # ------------------------------------------------------------------------
    @app.route("/api/audit/<int:audit_id>/equipements", methods=["GET"])
    def api_equipements_list(audit_id):
        Audit.query.get_or_404(audit_id)
        eqs = Equipement.query.filter_by(audit_id=audit_id).all()
        return jsonify([serialize_equipement(e) for e in eqs])

    @app.route("/api/audit/<int:audit_id>/equipements", methods=["POST"])
    def api_equipement_create(audit_id):
        Audit.query.get_or_404(audit_id)
        data = request.get_json() or {}
        eq = Equipement(
            audit_id=audit_id,
            site_id=data.get("site_id"),
            parent_id=data.get("parent_id"),
            type=data.get("type", "autre"),
            nom_hote=data.get("nom_hote", ""),
            pos_x=data.get("pos_x", 100),
            pos_y=data.get("pos_y", 100),
        )
        # Tous les autres champs si fournis
        _apply_equipement_fields(eq, data)
        db.session.add(eq)
        db.session.commit()
        return jsonify(serialize_equipement(eq)), 201

    @app.route("/api/equipement/<int:eq_id>", methods=["PUT"])
    def api_equipement_update(eq_id):
        eq = Equipement.query.get_or_404(eq_id)
        data = request.get_json() or {}
        _apply_equipement_fields(eq, data)
        db.session.commit()
        return jsonify(serialize_equipement(eq))

    @app.route("/api/equipement/<int:eq_id>", methods=["DELETE"])
    def api_equipement_delete(eq_id):
        eq = Equipement.query.get_or_404(eq_id)
        # Supprimer aussi les liaisons impliquant cet équipement
        Liaison.query.filter(
            (Liaison.source_id == eq_id) | (Liaison.dest_id == eq_id)
        ).delete()
        db.session.delete(eq)
        db.session.commit()
        return jsonify({"ok": True})

    def _apply_equipement_fields(eq, data):
        for field in (
            "site_id", "parent_id", "type", "nom_hote", "marque", "modele",
            "numero_serie", "ip", "mac", "vlan", "role", "os", "os_version",
            "cpu", "ram", "stockage", "raid", "capacite_totale", "taux_occupation",
            "date_mise_service", "nb_vm", "pos_x", "pos_y", "rack", "rack_u",
            "commentaires",
        ):
            if field in data:
                setattr(eq, field, data[field])

    # ------------------------------------------------------------------------
    # API JSON — liaisons
    # ------------------------------------------------------------------------
    @app.route("/api/audit/<int:audit_id>/liaisons", methods=["GET"])
    def api_liaisons_list(audit_id):
        Audit.query.get_or_404(audit_id)
        ls = Liaison.query.filter_by(audit_id=audit_id).all()
        return jsonify([serialize_liaison(l) for l in ls])

    @app.route("/api/audit/<int:audit_id>/liaisons", methods=["POST"])
    def api_liaison_create(audit_id):
        Audit.query.get_or_404(audit_id)
        data = request.get_json() or {}
        if not data.get("source_id") or not data.get("dest_id"):
            return jsonify({"error": "source_id et dest_id requis"}), 400
        l = Liaison(
            audit_id=audit_id,
            source_id=data["source_id"],
            dest_id=data["dest_id"],
            type=data.get("type", "ethernet"),
            port_source=data.get("port_source"),
            port_dest=data.get("port_dest"),
            vlan=data.get("vlan"),
            debit=data.get("debit"),
            commentaire=data.get("commentaire"),
        )
        db.session.add(l)
        db.session.commit()
        return jsonify(serialize_liaison(l)), 201

    @app.route("/api/liaison/<int:l_id>", methods=["DELETE"])
    def api_liaison_delete(l_id):
        l = Liaison.query.get_or_404(l_id)
        db.session.delete(l)
        db.session.commit()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------------
    # API JSON — applications, sauvegardes, messagerie
    # ------------------------------------------------------------------------
    @app.route("/api/audit/<int:audit_id>/applications", methods=["GET"])
    def api_apps_list(audit_id):
        Audit.query.get_or_404(audit_id)
        items = Application.query.filter_by(audit_id=audit_id).all()
        return jsonify([serialize_app(a) for a in items])

    @app.route("/api/audit/<int:audit_id>/applications", methods=["POST"])
    def api_app_create(audit_id):
        Audit.query.get_or_404(audit_id)
        data = request.get_json() or {}
        app_ = Application(audit_id=audit_id, **{
            k: v for k, v in data.items()
            if k in ("nom", "type", "editeur", "version", "fournisseur_support",
                     "contact_support", "serveur_hote_id", "criticite", "commentaires")
        })
        db.session.add(app_)
        db.session.commit()
        return jsonify(serialize_app(app_)), 201

    @app.route("/api/application/<int:app_id>", methods=["PUT"])
    def api_app_update(app_id):
        a = Application.query.get_or_404(app_id)
        data = request.get_json() or {}
        for field in ("nom", "type", "editeur", "version", "fournisseur_support",
                      "contact_support", "serveur_hote_id", "criticite", "commentaires"):
            if field in data:
                setattr(a, field, data[field])
        db.session.commit()
        return jsonify(serialize_app(a))

    @app.route("/api/application/<int:app_id>", methods=["DELETE"])
    def api_app_delete(app_id):
        a = Application.query.get_or_404(app_id)
        db.session.delete(a)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/audit/<int:audit_id>/sauvegardes", methods=["GET"])
    def api_bks_list(audit_id):
        Audit.query.get_or_404(audit_id)
        items = Sauvegarde.query.filter_by(audit_id=audit_id).all()
        return jsonify([serialize_backup(s) for s in items])

    @app.route("/api/audit/<int:audit_id>/sauvegardes", methods=["POST"])
    def api_bk_create(audit_id):
        Audit.query.get_or_404(audit_id)
        data = request.get_json() or {}
        s = Sauvegarde(audit_id=audit_id, **{
            k: v for k, v in data.items()
            if k in ("perimetre", "type_sauvegarde", "frequence", "solution",
                     "cible", "retention", "derniere_verification",
                     "chiffrement", "externalisation", "commentaires")
        })
        db.session.add(s)
        db.session.commit()
        return jsonify(serialize_backup(s)), 201

    @app.route("/api/sauvegarde/<int:s_id>", methods=["PUT"])
    def api_bk_update(s_id):
        s = Sauvegarde.query.get_or_404(s_id)
        data = request.get_json() or {}
        for field in ("perimetre", "type_sauvegarde", "frequence", "solution",
                      "cible", "retention", "derniere_verification",
                      "chiffrement", "externalisation", "commentaires"):
            if field in data:
                setattr(s, field, data[field])
        db.session.commit()
        return jsonify(serialize_backup(s))

    @app.route("/api/sauvegarde/<int:s_id>", methods=["DELETE"])
    def api_bk_delete(s_id):
        s = Sauvegarde.query.get_or_404(s_id)
        db.session.delete(s)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/audit/<int:audit_id>/messageries", methods=["GET"])
    def api_msgs_list(audit_id):
        Audit.query.get_or_404(audit_id)
        items = Messagerie.query.filter_by(audit_id=audit_id).all()
        return jsonify([serialize_msg(m) for m in items])

    @app.route("/api/audit/<int:audit_id>/messageries", methods=["POST"])
    def api_msg_create(audit_id):
        Audit.query.get_or_404(audit_id)
        data = request.get_json() or {}
        m = Messagerie(audit_id=audit_id, **{
            k: v for k, v in data.items()
            if k in ("solution", "protocole", "nb_boites", "domaine",
                     "mx_records", "filtre_antispam", "adresses", "commentaires")
        })
        db.session.add(m)
        db.session.commit()
        return jsonify(serialize_msg(m)), 201

    @app.route("/api/messagerie/<int:m_id>", methods=["PUT"])
    def api_msg_update(m_id):
        m = Messagerie.query.get_or_404(m_id)
        data = request.get_json() or {}
        for field in ("solution", "protocole", "nb_boites", "domaine",
                      "mx_records", "filtre_antispam", "adresses", "commentaires"):
            if field in data:
                setattr(m, field, data[field])
        db.session.commit()
        return jsonify(serialize_msg(m))

    @app.route("/api/messagerie/<int:m_id>", methods=["DELETE"])
    def api_msg_delete(m_id):
        m = Messagerie.query.get_or_404(m_id)
        db.session.delete(m)
        db.session.commit()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------------
    # SUPPRESSION AUDIT
    # ------------------------------------------------------------------------
    @app.route("/audit/<int:audit_id>/supprimer", methods=["POST"])
    def supprimer_audit(audit_id):
        a = Audit.query.get_or_404(audit_id)
        db.session.delete(a)
        db.session.commit()
        return redirect(url_for("index"))

    # ------------------------------------------------------------------------
    # IMPORT (scanner réseau / agent poste -> équipements)
    # ------------------------------------------------------------------------
    @app.route("/api/audit/<int:audit_id>/import", methods=["POST"])
    def api_import(audit_id):
        from import_data import importer_payload, importer_inventaire_poste
        audit = Audit.query.get_or_404(audit_id)
        # Accepte soit un fichier uploadé (champ "fichier"), soit du JSON brut
        payload = None
        if "fichier" in request.files:
            f = request.files["fichier"]
            try:
                import json
                payload = json.load(f.stream)
            except Exception as e:
                return jsonify({"error": f"JSON invalide : {e}"}), 400
        else:
            payload = request.get_json(silent=True)
        if not payload:
            return jsonify({"error": "Aucune donnée reçue"}), 400

        ptype = payload.get("type", "")
        try:
            if ptype == "inventaire_poste":
                res = importer_inventaire_poste(
                    audit, payload, db, Equipement, Conformite)
                return jsonify({"ok": True, "mode": "inventaire", "resultat": res})
            else:
                # scan_reseau (défaut)
                if "equipements" not in payload:
                    return jsonify({"error": "Format invalide : 'equipements' attendu"}), 400
                stats = importer_payload(audit, payload, db, Equipement)
                return jsonify({"ok": True, "mode": "scan", "stats": stats})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Échec import : {e}"}), 500

    @app.route("/api/audit/<int:audit_id>/conformites", methods=["GET"])
    def api_conformites_list(audit_id):
        import json as _json
        Audit.query.get_or_404(audit_id)
        items = Conformite.query.filter_by(audit_id=audit_id).all()
        out = []
        for c in items:
            try:
                resultats = _json.loads(c.resultats_json) if c.resultats_json else []
            except Exception:
                resultats = []
            # Résumé compact des détails (compteurs uniquement)
            details_counts = None
            has_details = False
            if getattr(c, "details_json", None):
                has_details = True
                try:
                    det = _json.loads(c.details_json)
                    details_counts = {k: len(v) for k, v in det.items()
                                      if isinstance(v, list)}
                except Exception:
                    details_counts = None
            out.append({
                "id": c.id, "machine": c.machine, "profil": c.profil,
                "date_collecte": c.date_collecte, "outil": c.outil,
                "score": c.score, "niveau": c.niveau,
                "nb_critiques": c.nb_critiques,
                "equipement_id": c.equipement_id,
                "resultats": resultats,
                "details_counts": details_counts,
                "has_details": has_details,
            })
        return jsonify(out)

    @app.route("/api/conformite/<int:conf_id>/details", methods=["GET"])
    def api_conformite_details(conf_id):
        """Renvoie le bloc 'details' complet d'un bilan de conformité."""
        import json as _json
        c = Conformite.query.get_or_404(conf_id)
        if not getattr(c, "details_json", None):
            return jsonify({})
        try:
            return jsonify(_json.loads(c.details_json))
        except Exception:
            return jsonify({"error": "details_json corrompu"}), 500

    @app.route("/api/conformite/<int:conf_id>/details/<section>/csv", methods=["GET"])
    def api_conformite_details_csv(conf_id, section):
        """Export CSV d'une section (applications, updates, users, services, ...)."""
        import json as _json
        import csv
        from io import StringIO
        from flask import Response
        c = Conformite.query.get_or_404(conf_id)
        if not getattr(c, "details_json", None):
            return jsonify({"error": "Aucun détail enregistré"}), 404
        try:
            det = _json.loads(c.details_json)
        except Exception:
            return jsonify({"error": "details_json corrompu"}), 500
        rows = det.get(section)
        if not isinstance(rows, list):
            return jsonify({"error": f"Section '{section}' introuvable"}), 404
        # Colonnes : union des clés rencontrées (ordre stable)
        seen = []
        for r in rows:
            if isinstance(r, dict):
                for k in r.keys():
                    if k not in seen:
                        seen.append(k)
        sio = StringIO()
        sio.write("\ufeff")  # BOM UTF-8 (Excel ouvre directement en UTF-8)
        w = csv.DictWriter(sio, fieldnames=seen, extrasaction="ignore",
                           delimiter=";")  # ; pour Excel FR
        w.writeheader()
        for r in rows:
            if isinstance(r, dict):
                w.writerow({k: ("" if v is None else v) for k, v in r.items()})
        filename = f"{_safe(c.machine or 'machine')}_{section}.csv"
        return Response(
            sio.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.route("/api/conformite/<int:conf_id>", methods=["DELETE"])
    def api_conformite_delete(conf_id):
        c = Conformite.query.get_or_404(conf_id)
        db.session.delete(c)
        db.session.commit()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------------
    # EXPORTS
    # ------------------------------------------------------------------------
    @app.route("/audit/<int:audit_id>/export/pdf")
    def export_pdf(audit_id):
        from exports import generate_pdf
        audit = Audit.query.get_or_404(audit_id)
        buf = generate_pdf(audit)
        filename = f"audit_{_safe(audit.client.nom)}_{audit.date_audit}.pdf"
        return send_file(buf, mimetype="application/pdf",
                         as_attachment=True, download_name=filename)

    @app.route("/audit/<int:audit_id>/export/excel")
    def export_excel(audit_id):
        from exports import generate_excel
        audit = Audit.query.get_or_404(audit_id)
        buf = generate_excel(audit)
        filename = f"inventaire_{_safe(audit.client.nom)}_{audit.date_audit}.xlsx"
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/audit/<int:audit_id>/export/svg")
    def export_svg(audit_id):
        from exports import generate_svg
        audit = Audit.query.get_or_404(audit_id)
        vue = request.args.get("vue", "logique")
        svg_bytes = generate_svg(audit, vue=vue)
        filename = f"schema_{_safe(audit.client.nom)}_{vue}.svg"
        return send_file(svg_bytes, mimetype="image/svg+xml",
                         as_attachment=True, download_name=filename)

    @app.route("/audit/<int:audit_id>/export/png")
    def export_png(audit_id):
        from exports import generate_png
        audit = Audit.query.get_or_404(audit_id)
        vue = request.args.get("vue", "logique")
        png_bytes = generate_png(audit, vue=vue)
        if png_bytes is None:
            flash("Export PNG indisponible (CairoSVG non installé). SVG disponible.")
            return redirect(url_for("export_svg", audit_id=audit_id, vue=vue))
        filename = f"schema_{_safe(audit.client.nom)}_{vue}.png"
        return send_file(png_bytes, mimetype="image/png",
                         as_attachment=True, download_name=filename)

    return app


# ============================================================================
# Sérialisation JSON
# ============================================================================

def serialize_audit(a):
    return {
        "id": a.id,
        "date_audit": a.date_audit.isoformat() if a.date_audit else None,
        "responsable": a.responsable,
        "interlocuteur_commercial": a.interlocuteur_commercial,
        "statut": a.statut,
        "notes_generales": a.notes_generales,
        "problemes_recurrents": a.problemes_recurrents,
        "documentation_existante": a.documentation_existante,
        "client": {
            "id": a.client.id,
            "nom": a.client.nom,
            "groupe": a.client.groupe,
            "adresse": a.client.adresse,
            "contact_nom": a.client.contact_nom,
            "contact_tel": a.client.contact_tel,
            "contact_email": a.client.contact_email,
            "horaires": a.client.horaires,
            "activite": a.client.activite,
        },
        "sites": [serialize_site(s) for s in a.sites],
    }


def serialize_site(s):
    return {
        "id": s.id, "nom": s.nom, "adresse": s.adresse,
        "fai": s.fai, "type_connexion": s.type_connexion,
        "debit_down": s.debit_down, "debit_up": s.debit_up,
        "ip_publique": s.ip_publique, "backup_connexion": s.backup_connexion,
        "plan_ip": s.plan_ip, "plage_dhcp": s.plage_dhcp,
        "voip_solution": s.voip_solution, "voip_pabx": s.voip_pabx,
        "voip_softphone": s.voip_softphone,
        "antivirus_solution": s.antivirus_solution,
        "antivirus_gestion": s.antivirus_gestion,
        "vpn_type": s.vpn_type, "vpn_utilisateurs": s.vpn_utilisateurs,
        "idsips_actif": s.idsips_actif,
        "methode_acces_distant": s.methode_acces_distant,
        "notes": s.notes,
    }


def serialize_equipement(e):
    return {
        "id": e.id, "audit_id": e.audit_id, "site_id": e.site_id,
        "parent_id": e.parent_id, "type": e.type,
        "nom_hote": e.nom_hote, "marque": e.marque, "modele": e.modele,
        "numero_serie": e.numero_serie,
        "ip": e.ip, "mac": e.mac, "vlan": e.vlan, "role": e.role,
        "os": e.os, "os_version": e.os_version,
        "cpu": e.cpu, "ram": e.ram, "stockage": e.stockage, "raid": e.raid,
        "capacite_totale": e.capacite_totale,
        "taux_occupation": e.taux_occupation,
        "date_mise_service": e.date_mise_service,
        "nb_vm": e.nb_vm,
        "pos_x": e.pos_x, "pos_y": e.pos_y,
        "rack": e.rack, "rack_u": e.rack_u,
        "commentaires": e.commentaires,
    }


def serialize_liaison(l):
    return {
        "id": l.id, "audit_id": l.audit_id,
        "source_id": l.source_id, "dest_id": l.dest_id,
        "type": l.type, "port_source": l.port_source,
        "port_dest": l.port_dest, "vlan": l.vlan,
        "debit": l.debit, "commentaire": l.commentaire,
    }


def serialize_app(a):
    return {
        "id": a.id, "nom": a.nom, "type": a.type, "editeur": a.editeur,
        "version": a.version, "fournisseur_support": a.fournisseur_support,
        "contact_support": a.contact_support, "serveur_hote_id": a.serveur_hote_id,
        "criticite": a.criticite, "commentaires": a.commentaires,
    }


def serialize_backup(s):
    return {
        "id": s.id, "perimetre": s.perimetre,
        "type_sauvegarde": s.type_sauvegarde, "frequence": s.frequence,
        "solution": s.solution, "cible": s.cible, "retention": s.retention,
        "derniere_verification": s.derniere_verification,
        "chiffrement": s.chiffrement, "externalisation": s.externalisation,
        "commentaires": s.commentaires,
    }


def serialize_msg(m):
    return {
        "id": m.id, "solution": m.solution, "protocole": m.protocole,
        "nb_boites": m.nb_boites, "domaine": m.domaine,
        "mx_records": m.mx_records, "filtre_antispam": m.filtre_antispam,
        "adresses": m.adresses, "commentaires": m.commentaires,
    }


def _safe(s):
    if not s:
        return "client"
    keep = "-_."
    return "".join(c if c.isalnum() or c in keep else "_" for c in s)[:50]


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
