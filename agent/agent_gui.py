"""
Audit Agent — interface graphique (Tkinter).

Audit local d'un poste / serveur Windows :
  - inventaire matériel & OS
  - 17 contrôles de conformité (référentiel maison aligné ANSSI)
  - export JSON 'inventaire_poste' importable dans la plateforme d'audit

Tente l'élévation administrateur (UAC) au lancement pour un audit complet.
Sans élévation, les contrôles concernés sont marqués 'indéterminé'.

Lancement :  python agent_gui.py
Packaging  :  voir build.txt (PyInstaller -> .exe, avec manifeste admin)
"""
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

try:
    from elevation import is_admin, ensure_admin
    # Détection de l'OS pour basculer sur les bons modules de collecte/contrôles
    import platform as _plat
    _SYSTEM = _plat.system()
    if _SYSTEM == "Darwin":
        # macOS : on utilise les modules dédiés Mac
        from checks_mac import detect_profil, run_checks, CHECKS
        from collect_mac import collect_machine
        from details_mac import collect_all as collect_details, count_summary, COLLECTORS
    else:
        # Windows (et Linux pour les tests) : modules d'origine
        from checks import detect_profil, run_checks, CHECKS
        from collect import collect_machine
        from details import collect_all as collect_details, count_summary, COLLECTORS
except ImportError:
    from .elevation import is_admin, ensure_admin
    import platform as _plat
    _SYSTEM = _plat.system()
    if _SYSTEM == "Darwin":
        from .checks_mac import detect_profil, run_checks, CHECKS
        from .collect_mac import collect_machine
        from .details_mac import collect_all as collect_details, count_summary, COLLECTORS
    else:
        from .checks import detect_profil, run_checks, CHECKS
        from .collect import collect_machine
        from .details import collect_all as collect_details, count_summary, COLLECTORS


# Libellés lisibles des contrôles (repris du référentiel, dupliqués ici pour
# que l'agent soit autonome — pas de dépendance à la plateforme).
LIBELLES = {
    "firewall_actif": "Pare-feu Windows activé",
    "antivirus_present": "Antivirus présent et activé",
    "antivirus_ajour": "Signatures antivirus à jour",
    "chiffrement_disque": "Chiffrement disque (BitLocker)",
    "maj_recentes": "Mises à jour Windows récentes",
    "os_supporte": "Version Windows supportée",
    "admins_limites": "Comptes administrateurs locaux maîtrisés",
    "admin_natif_desactive": "Compte 'Administrateur' natif désactivé",
    "mdp_jamais_expire": "Pas de mot de passe sans expiration",
    "rdp_maitrise": "Bureau à distance (RDP) maîtrisé",
    "uac_actif": "Contrôle de compte (UAC) activé",
    "smbv1_desactive": "SMBv1 désactivé",
    "partages_maitrises": "Partages réseau maîtrisés",
    "espace_disque": "Espace disque suffisant",
    "uptime_raisonnable": "Redémarrage récent",
    "serveur_roles_documentes": "Rôles serveur identifiés",
    "serveur_sauvegarde": "Sauvegarde serveur en place",
}

STATUT_COULEUR = {
    "ok": "#198754", "attention": "#fd7e14", "critique": "#dc3545",
    "indetermine": "#adb5bd", "na": "#ced4da",
}
STATUT_LABEL = {
    "ok": "Conforme", "attention": "Attention", "critique": "Critique",
    "indetermine": "Indéterminé", "na": "N/A",
}


class AgentApp:
    def __init__(self, root, admin):
        self.root = root
        self.admin = admin
        self.payload = None
        root.title("Audit Agent — myithead")
        root.geometry("820x600")
        root.minsize(720, 520)
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Audit de conformité du poste / serveur local",
                  font=("", 11, "bold")).pack(side="left")

        # Bandeau droits admin
        admin_frame = ttk.Frame(self.root, padding=(10, 0))
        admin_frame.pack(fill="x")
        if self.admin:
            txt, col = "✓ Lancé en administrateur — audit complet", "#198754"
        else:
            txt, col = ("⚠ Mode standard (non-admin) — certains contrôles "
                        "seront 'indéterminés'"), "#fd7e14"
        lbl = tk.Label(admin_frame, text=txt, fg=col, anchor="w")
        lbl.pack(fill="x")

        # Bouton lancer + progression
        ctl = ttk.Frame(self.root, padding=10)
        ctl.pack(fill="x")
        self.btn_run = ttk.Button(ctl, text="▶ Lancer l'audit",
                                  command=self.on_run)
        self.btn_run.pack(side="left")
        self.progress = ttk.Progressbar(ctl, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(10, 10))
        self.status_var = tk.StringVar(value="Prêt.")
        ttk.Label(ctl, textvariable=self.status_var, width=24,
                  anchor="e").pack(side="left")

        # Résumé (score)
        self.summary_var = tk.StringVar(value="")
        self.summary_lbl = tk.Label(self.root, textvariable=self.summary_var,
                                    font=("", 14, "bold"), pady=6)
        self.summary_lbl.pack(fill="x")

        # Zone centrale : notebook avec onglets Conformité / Détails
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 0))

        # --- Onglet Conformité ---
        tab_conf = ttk.Frame(nb)
        nb.add(tab_conf, text="Conformité (17 contrôles)")
        cols = ("controle", "statut", "detail")
        self.tree = ttk.Treeview(tab_conf, columns=cols, show="headings")
        self.tree.heading("controle", text="Contrôle")
        self.tree.heading("statut", text="Statut")
        self.tree.heading("detail", text="Détail")
        self.tree.column("controle", width=260, anchor="w")
        self.tree.column("statut", width=110, anchor="w")
        self.tree.column("detail", width=360, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        for st, col in STATUT_COULEUR.items():
            self.tree.tag_configure(st, foreground=col)
        sb = ttk.Scrollbar(tab_conf, orient="vertical",
                           command=self.tree.yview)
        sb.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        # --- Onglet Détails (winaudit-like) ---
        tab_det = ttk.Frame(nb)
        nb.add(tab_det, text="Détails (applis, MAJ, comptes…)")

        # Sous-notebook avec une section par catégorie
        self.details_nb = ttk.Notebook(tab_det)
        self.details_nb.pack(fill="both", expand=True)
        self.details_trees = {}  # key -> Treeview

        # Définitions des colonnes affichées par catégorie
        self.DETAIL_COLUMNS = {
            "applications":    [("nom", "Nom", 280), ("version", "Version", 110),
                                ("editeur", "Éditeur", 180),
                                ("date_install", "Installé", 100)],
            "updates":         [("kb", "KB", 110), ("type", "Type", 140),
                                ("date_install", "Date", 100),
                                ("installe_par", "Par", 200)],
            "users":           [("nom", "Nom", 160), ("active", "Activé", 70),
                                ("description", "Description", 220),
                                ("derniere_connexion", "Dernière connexion", 140),
                                ("mdp_jamais_expire", "Mdp éternel", 90)],
            "services":        [("nom_affiche", "Service", 260), ("etat", "État", 90),
                                ("demarrage", "Démarrage", 100),
                                ("compte", "Compte", 180)],
            "drivers":         [("peripherique", "Périphérique", 280),
                                ("fabricant", "Fabricant", 160),
                                ("version", "Version", 110),
                                ("date", "Date", 100)],
            "scheduled_tasks": [("nom", "Tâche", 260), ("chemin", "Chemin", 220),
                                ("etat", "État", 80),
                                ("derniere_exec", "Dernière exéc.", 130)],
            "firewall_rules":  [("nom", "Règle", 380),
                                ("direction", "Direction", 90),
                                ("profil", "Profil", 100)],
            "sessions":        [("utilisateur", "Utilisateur", 200),
                                ("etat", "État", 100), ("session", "Session", 100)],
            "volumes":         [("lettre", "Lettre", 70), ("label", "Label", 140),
                                ("fs", "FS", 80),
                                ("taille_go", "Taille (Go)", 100),
                                ("libre_go", "Libre (Go)", 100),
                                ("etat", "État", 90)],
            "network":         [("interface", "Interface", 160),
                                ("ip", "IP", 140), ("mac", "MAC", 160),
                                ("passerelle", "Passerelle", 130),
                                ("dns", "DNS", 220)],
            "auth_failures":   [("date", "Date", 140), ("message", "Message", 500)],
            "remote_access":   [("nom", "Logiciel", 240), ("version", "Version", 110),
                                ("editeur", "Éditeur", 180)],
        }
        self.DETAIL_LABELS = {key: label for key, label, _ in COLLECTORS}
        self.DETAIL_LABELS["remote_access"] = "⚠ Accès distants détectés"

        # On crée les onglets vides ; ils seront remplis quand un audit est lancé
        self.detail_tabs_created = False

        # Bas : enregistrer
        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")
        self.machine_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.machine_var).pack(side="left")
        self.btn_save = ttk.Button(bottom, text="💾 Enregistrer le JSON…",
                                   command=self.on_save, state="disabled")
        self.btn_save.pack(side="right")

    def on_run(self):
        self.payload = None
        self.btn_save.config(state="disabled")
        self.btn_run.config(state="disabled")
        self.summary_var.set("")
        self.status_var.set("Audit en cours…")
        self.progress.config(value=0, maximum=100)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            profil = detect_profil()
            self.root.after(0, lambda: self.status_var.set(
                f"Profil : {profil} — collecte inventaire…"))
            machine = collect_machine()

            # --- Phase 1 : contrôles de conformité (17, rapide) ---
            n_checks = len(CHECKS)
            n_details = len(COLLECTORS)
            total_steps = n_checks + n_details

            def progress_checks(done, total, cid):
                pct = (done / total_steps) * 100
                self.root.after(0, self._progress, pct,
                                f"Contrôle : {LIBELLES.get(cid, cid)[:30]}")

            resultats = run_checks(profil, is_admin=self.admin,
                                   progress_cb=progress_checks)

            # --- Phase 2 : collecte détaillée (winaudit-like) ---
            def progress_details(i, t, label):
                pct = ((n_checks + i) / total_steps) * 100
                self.root.after(0, self._progress, pct,
                                f"Détails : {label[:30]}")

            details = collect_details(progress_cb=progress_details)

            # Calcul du score local
            score, niveau, nb_crit = self._score(resultats)

            payload = {
                "type": "inventaire_poste",
                "date": datetime.now().isoformat(timespec="seconds"),
                "outil": "audit-agent", "version": "1.1",
                "profil": profil,
                "machine": machine,
                "conformite": resultats,
                "score_local": score, "niveau_local": niveau,
                "details": details,
            }
            self.root.after(0, self._done, payload, score, niveau, nb_crit)
        except Exception as e:
            self.root.after(0, self._error, str(e))

    def _score(self, resultats):
        """Score pondéré (repris de conformite_ref, dupliqué pour autonomie)."""
        POIDS = {"critique": 3, "majeur": 2, "mineur": 1}
        # Criticité par id (doit rester alignée avec conformite_ref.py)
        CRIT = {
            "firewall_actif": "critique", "antivirus_present": "critique",
            "antivirus_ajour": "majeur", "chiffrement_disque": "majeur",
            "maj_recentes": "critique", "os_supporte": "critique",
            "admins_limites": "majeur", "admin_natif_desactive": "majeur",
            "mdp_jamais_expire": "mineur", "rdp_maitrise": "majeur",
            "uac_actif": "majeur", "smbv1_desactive": "critique",
            "partages_maitrises": "mineur", "espace_disque": "mineur",
            "uptime_raisonnable": "mineur",
            "serveur_roles_documentes": "mineur", "serveur_sauvegarde": "critique",
        }
        obt = pos = 0.0
        nb_crit = 0
        for r in resultats:
            st = r["statut"]
            if st == "critique":
                nb_crit += 1
            if st in ("indetermine", "na"):
                continue
            poids = POIDS.get(CRIT.get(r["id"], "mineur"), 1)
            pos += poids
            if st == "ok":
                obt += poids
            elif st == "attention":
                obt += poids * 0.5
        score = round((obt / pos) * 100) if pos else None
        if score is None:
            niveau = "indetermine"
        elif nb_crit > 0:
            niveau = "non_conforme"
        elif score >= 85:
            niveau = "conforme"
        elif score >= 60:
            niveau = "partiel"
        else:
            niveau = "non_conforme"
        return score, niveau, nb_crit

    def _progress(self, pct, label):
        self.progress.config(value=pct)
        self.status_var.set(label)

    def _done(self, payload, score, niveau, nb_crit):
        self.payload = payload
        # --- Onglet Conformité ---
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in payload["conformite"]:
            self.tree.insert("", "end", tags=(r["statut"],), values=(
                LIBELLES.get(r["id"], r["id"]),
                STATUT_LABEL.get(r["statut"], r["statut"]),
                r.get("detail", ""),
            ))
        # --- Onglet Détails (winaudit-like) ---
        self._populate_details(payload.get("details", {}))

        col = STATUT_COULEUR.get(
            "ok" if niveau == "conforme" else
            "attention" if niveau == "partiel" else
            "critique" if niveau == "non_conforme" else "indetermine")
        niveau_txt = {"conforme": "CONFORME", "partiel": "PARTIELLEMENT CONFORME",
                      "non_conforme": "NON CONFORME",
                      "indetermine": "INDÉTERMINÉ"}.get(niveau, niveau)
        score_txt = "—" if score is None else f"{score}/100"
        self.summary_lbl.config(fg=col)
        # Petit récap des compteurs détails
        cs = count_summary(payload.get("details", {})) if payload.get("details") else {}
        recap_det = ""
        if cs:
            recap_det = (f"  •  {cs.get('applications',0)} applis, "
                         f"{cs.get('updates',0)} MAJ, "
                         f"{cs.get('users',0)} comptes")
            if cs.get("remote_access"):
                recap_det += f"  ⚠ {cs['remote_access']} outil(s) d'accès distant"
        self.summary_var.set(f"Score : {score_txt}  —  {niveau_txt}"
                             + (f"  ({nb_crit} critique(s))" if nb_crit else "")
                             + recap_det)
        self.machine_var.set(
            f"{payload['machine'].get('nom_hote','?')} "
            f"({payload['profil']}) — {payload['machine'].get('os','?')}")
        self.status_var.set("Terminé.")
        self.progress.config(value=100)
        self.btn_run.config(state="normal")
        self.btn_save.config(state="normal")

    def _populate_details(self, details):
        """Crée ou rafraîchit les onglets de détails avec les données collectées."""
        # Reset : supprimer les onglets existants pour repartir propre
        for tab_id in self.details_nb.tabs():
            self.details_nb.forget(tab_id)
        self.details_trees.clear()

        # Ordre d'affichage : on met "remote_access" en premier s'il y a des
        # détections (alerte visible immédiatement)
        order = list(self.DETAIL_COLUMNS.keys())
        if details.get("remote_access"):
            order.remove("remote_access")
            order.insert(0, "remote_access")

        for key in order:
            rows = details.get(key, [])
            cols_def = self.DETAIL_COLUMNS.get(key, [])
            if not cols_def:
                continue
            label = self.DETAIL_LABELS.get(key, key)
            # Titre d'onglet avec compteur
            tab_title = f"{label} ({len(rows)})"
            frame = ttk.Frame(self.details_nb)
            self.details_nb.add(frame, text=tab_title)
            col_ids = [c[0] for c in cols_def]
            tv = ttk.Treeview(frame, columns=col_ids, show="headings")
            for cid, cname, cw in cols_def:
                tv.heading(cid, text=cname)
                tv.column(cid, width=cw, anchor="w")
            tv.pack(side="left", fill="both", expand=True)
            sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
            sb.pack(side="left", fill="y")
            tv.configure(yscrollcommand=sb.set)
            # Remplissage
            for row in rows:
                values = []
                for cid in col_ids:
                    v = row.get(cid, "")
                    # Booléens en oui/non lisibles
                    if isinstance(v, bool):
                        v = "Oui" if v else "Non"
                    elif v is None:
                        v = ""
                    values.append(str(v))
                tv.insert("", "end", values=values)
            self.details_trees[key] = tv

    def _error(self, msg):
        self.status_var.set("Erreur.")
        self.btn_run.config(state="normal")
        messagebox.showerror("Erreur d'audit", msg)

    def on_save(self):
        if not self.payload:
            return
        host = self.payload["machine"].get("nom_hote", "machine")
        default = f"inventaire_{host}_{datetime.now():%Y%m%d_%H%M}.json"
        path = filedialog.asksaveasfilename(
            title="Enregistrer l'inventaire",
            defaultextension=".json", initialfile=default,
            filetypes=[("Fichier JSON", "*.json"), ("Tous", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.payload, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Enregistré",
                f"Inventaire enregistré :\n{path}\n\n"
                "Importez ce fichier dans la plateforme d'audit\n"
                "via le bouton « ⬇ Importer ».")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'enregistrer :\n{e}")


def main():
    # Tentative d'élévation AVANT de créer la fenêtre
    admin, relance = ensure_admin()
    if relance:
        # Une instance élevée a été lancée : on ferme celle-ci.
        sys.exit(0)

    root = tk.Tk()
    try:
        ws = root.tk.call("tk", "windowingsystem")
        ttk.Style().theme_use("vista" if ws == "win32" else "clam")
    except Exception:
        pass
    AgentApp(root, admin)
    root.mainloop()


if __name__ == "__main__":
    main()
