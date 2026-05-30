/* =====================================================================
   app.js — logique du formulaire d'audit
   - autosave des champs (debounce)
   - gestion des onglets
   - quick-add équipement → push dans le schéma
   - modal d'édition équipement & site
   - CRUD apps / backups / messageries / liaisons / sites
===================================================================== */

window.AppLogic = (function () {
  const auditEl = document.querySelector(".audit-layout");
  if (!auditEl) return null;

  const AUDIT_ID = parseInt(auditEl.dataset.auditId, 10);
  const indicator = document.getElementById("save_indicator");

  // -------------------- Onglets --------------------
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const id = btn.dataset.tab;
      document.querySelector(`[data-panel="${id}"]`).classList.add("active");
    });
  });

  // -------------------- Autosave champs --------------------
  const saveTimers = {};
  function flagSaving() {
    if (indicator) indicator.classList.add("saving");
  }
  function flagSaved(ok) {
    if (!indicator) return;
    indicator.classList.remove("saving");
    if (!ok) indicator.classList.add("error");
    else indicator.classList.remove("error");
  }

  function scheduleSaveAudit() {
    flagSaving();
    clearTimeout(saveTimers.audit);
    saveTimers.audit = setTimeout(saveAuditFields, 500);
  }

  function saveAuditFields() {
    const payload = { client: {} };
    document.querySelectorAll("[data-field]").forEach(el => {
      const k = el.dataset.field;
      const val = el.type === "checkbox" ? el.checked : el.value;
      if (k.startsWith("client.")) payload.client[k.split(".")[1]] = val;
      else payload[k] = val;
    });
    fetch(`/api/audit/${AUDIT_ID}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(r => {
      flagSaved(r.ok);
      // MAJ titre client
      if (payload.client.nom) {
        const hdr = document.getElementById("hdr_client");
        if (hdr) hdr.textContent = payload.client.nom;
      }
    }).catch(() => flagSaved(false));
  }

  // Branche tous les champs `data-field` à l'autosave
  document.querySelectorAll("[data-field]").forEach(el => {
    el.addEventListener("input", scheduleSaveAudit);
    el.addEventListener("change", scheduleSaveAudit);
  });

  // -------------------- Quick-add équipement --------------------
  document.querySelectorAll(".quick-add-btn").forEach(btn => {
    btn.addEventListener("click", () => addEquipement(btn.dataset.type));
  });

  function addEquipement(type) {
    // Position auto : grille libre
    const eqs = window.SchemaApp ? window.SchemaApp.getEquipements() : [];
    const cols = 6;
    const idx = eqs.length;
    const pos_x = 40 + (idx % cols) * 140;
    const pos_y = 40 + Math.floor(idx / cols) * 110;
    fetch(`/api/audit/${AUDIT_ID}/equipements`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, pos_x, pos_y }),
    }).then(r => r.json()).then(eq => {
      if (window.SchemaApp) window.SchemaApp.addEquipement(eq);
      renderEqList();
      // Ouvrir le modal pour saisie immédiate
      openEqModal(eq.id);
    });
  }

  // -------------------- Liste équipements --------------------
  function renderEqList() {
    const container = document.getElementById("equipements_container");
    if (!container) return;
    const eqs = window.SchemaApp ? window.SchemaApp.getEquipements() : [];
    if (!eqs.length) {
      container.innerHTML = '<p class="empty">Cliquez sur un bouton ci-dessus pour ajouter un équipement.</p>';
      return;
    }
    container.innerHTML = "";
    // Regrouper par type
    const groups = {};
    eqs.forEach(e => (groups[e.type] = groups[e.type] || []).push(e));
    const VIS = window.EQUIP_VISUAL || {};
    Object.keys(groups).sort().forEach(type => {
      const vis = VIS[type] || { color: "#6c757d", icon: "❓", label: type };
      const arr = groups[type];
      const titre = document.createElement("h3");
      titre.style.cssText = "font-size:13px;margin:14px 0 6px;color:" + vis.color;
      titre.textContent = `${vis.icon} ${vis.label}s (${arr.length})`;
      container.appendChild(titre);
      arr.forEach(e => container.appendChild(buildEqCard(e)));
    });
    refreshLiaisonSelectors();
    renderServeursList();
    renderSecuriteList();
  }

  function buildEqCard(eq) {
    const vis = (window.EQUIP_VISUAL || {})[eq.type] || { color: "#6c757d", icon: "❓" };
    const card = document.createElement("div");
    card.className = "eq-card";
    card.style.borderLeft = `4px solid ${vis.color}`;
    card.innerHTML = `
      <div class="eq-icon">${vis.icon}</div>
      <div class="eq-info">
        <strong>${escape(eq.nom_hote) || "<em>Sans nom</em>"}</strong>
        ${eq.marque || eq.modele ? `<small> · ${escape(eq.marque || "")} ${escape(eq.modele || "")}</small>` : ""}<br>
        <small>${eq.ip ? "IP " + escape(eq.ip) + " · " : ""}${eq.vlan ? "VLAN " + escape(eq.vlan) + " · " : ""}${escape(eq.role || "")}</small>
      </div>
      <div class="eq-actions">
        <button class="btn btn-sm" data-edit="${eq.id}">Éditer</button>
        <button class="btn btn-sm btn-danger" data-del="${eq.id}">×</button>
      </div>`;
    card.querySelector("[data-edit]").addEventListener("click", () => openEqModal(eq.id));
    card.querySelector("[data-del]").addEventListener("click", () => deleteEq(eq.id));
    return card;
  }

  function deleteEq(id) {
    if (!confirm("Supprimer cet équipement ?")) return;
    fetch(`/api/equipement/${id}`, { method: "DELETE" }).then(() => {
      if (window.SchemaApp) window.SchemaApp.removeEquipement(id);
      renderEqList();
    });
  }

  // -------------------- Modal équipement --------------------
  let currentEqId = null;

  function openEqModal(id) {
    const eq = (window.SchemaApp ? window.SchemaApp.getEquipements() : []).find(e => e.id === id);
    if (!eq) return;
    currentEqId = id;
    document.getElementById("modal_eq_title").textContent =
      `Équipement #${id}`;
    document.getElementById("m_eq_id").value = eq.id;
    ["type", "site_id", "nom_hote", "marque", "modele", "numero_serie",
     "ip", "mac", "vlan", "role", "os", "os_version", "cpu", "ram",
     "stockage", "raid", "capacite_totale", "taux_occupation",
     "date_mise_service", "nb_vm", "rack", "rack_u", "commentaires"].forEach(f => {
      const el = document.getElementById("m_eq_" + f);
      if (el) el.value = eq[f] == null ? "" : eq[f];
    });
    refreshSiteSelect("m_eq_site_id", eq.site_id);
    refreshParentSelect(eq);
    toggleParentField(eq.type);
    const typeSel = document.getElementById("m_eq_type");
    typeSel.onchange = () => toggleParentField(typeSel.value);
    document.getElementById("modal_eq").hidden = false;
  }

  // Affiche le sélecteur "Hébergé sur" pour tout ce qui peut être virtualisé :
  // un poste (Windows en VM), un serveur physique (peut tourner en VM aussi),
  // ou explicitement un serveur virtuel.
  const TYPES_VIRTUALISABLES = ["poste", "serveur_physique", "serveur_virtuel"];
  function toggleParentField(type) {
    const wrap = document.getElementById("m_eq_parent_wrap");
    if (wrap) wrap.style.display = TYPES_VIRTUALISABLES.includes(type) ? "" : "none";
  }

  function refreshParentSelect(eq) {
    const sel = document.getElementById("m_eq_parent_id");
    if (!sel) return;
    const eqs = window.SchemaApp ? window.SchemaApp.getEquipements() : [];
    sel.innerHTML = '<option value="">— Aucun —</option>';
    eqs.filter(e => e.type === "hyperviseur").forEach(h => {
      const o = document.createElement("option");
      o.value = h.id;
      o.textContent = h.nom_hote || `Hyperviseur #${h.id}`;
      if (eq.parent_id === h.id) o.selected = true;
      sel.appendChild(o);
    });
  }
  window.closeEqModal = function () {
    document.getElementById("modal_eq").hidden = true;
    currentEqId = null;
  };
  window.saveEqModal = function () {
    if (!currentEqId) return;
    const payload = {};
    ["type", "site_id", "nom_hote", "marque", "modele", "numero_serie",
     "ip", "mac", "vlan", "role", "os", "os_version", "cpu", "ram",
     "stockage", "raid", "capacite_totale", "taux_occupation",
     "date_mise_service", "nb_vm", "rack", "rack_u", "commentaires"].forEach(f => {
      const el = document.getElementById("m_eq_" + f);
      if (!el) return;
      let v = el.value;
      if (f === "site_id" || f === "nb_vm") v = v === "" ? null : parseInt(v, 10);
      payload[f] = v;
    });
    // parent_id : pour tout équipement virtualisable (poste, serveur physique, VM)
    const parentEl = document.getElementById("m_eq_parent_id");
    payload.parent_id = (TYPES_VIRTUALISABLES.includes(payload.type)
                         && parentEl && parentEl.value)
      ? parseInt(parentEl.value, 10) : null;
    fetch(`/api/equipement/${currentEqId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(r => r.json()).then(eq => {
      if (window.SchemaApp) window.SchemaApp.updateEquipement(eq);
      recomputeHostVmCounts();
      renderEqList();
      closeEqModal();
    });
  };

  function recomputeHostVmCounts() {
    const eqs = window.SchemaApp ? window.SchemaApp.getEquipements() : [];
    eqs.filter(e => e.type === "hyperviseur").forEach(h => {
      const count = eqs.filter(e => e.parent_id === h.id).length;
      if (h.nb_vm !== count) {
        fetch(`/api/equipement/${h.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nb_vm: count }),
        }).then(r => r.json()).then(updated => {
          if (window.SchemaApp) window.SchemaApp.updateEquipement(updated);
        });
      }
    });
  }
  window.deleteEquipement = function () {
    if (!currentEqId) return;
    deleteEq(currentEqId);
    closeEqModal();
  };

  // -------------------- Sites --------------------
  let sites = [];

  async function loadSites() {
    const r = await fetch(`/api/audit/${AUDIT_ID}`);
    const data = await r.json();
    sites = data.sites || [];
    renderSitesList();
    renderSecuriteList();
    refreshSiteSelect("m_eq_site_id");
  }

  function renderSitesList() {
    const c = document.getElementById("sites_container");
    if (!c) return;
    c.innerHTML = "";
    if (!sites.length) {
      c.innerHTML = '<p class="empty">Cliquez sur "Ajouter un site"</p>';
      return;
    }
    sites.forEach(s => {
      const card = document.createElement("div");
      card.className = "site-card";
      card.innerHTML = `
        <div class="site-card-header">
          <strong>📍 ${escape(s.nom)}</strong>
          <div>
            <button class="btn btn-sm" data-edit-site="${s.id}">Éditer</button>
            <button class="btn btn-sm btn-danger" data-del-site="${s.id}">×</button>
          </div>
        </div>
        <small class="muted">
          ${escape(s.adresse || "(adresse non renseignée)")} ·
          ${escape(s.fai || "?")} ${escape(s.type_connexion || "")} ·
          ${s.ip_publique ? "IP pub " + escape(s.ip_publique) : ""}
        </small>`;
      card.querySelector("[data-edit-site]").addEventListener("click",
        () => openSiteModal(s.id));
      card.querySelector("[data-del-site]").addEventListener("click", () => {
        if (!confirm("Supprimer ce site ?")) return;
        fetch(`/api/site/${s.id}`, { method: "DELETE" }).then(loadSites);
      });
      c.appendChild(card);
    });
  }

  let currentSiteId = null;
  function openSiteModal(id) {
    const s = sites.find(x => x.id === id);
    if (!s) return;
    currentSiteId = id;
    document.getElementById("m_site_id").value = s.id;
    ["nom", "adresse", "fai", "type_connexion", "debit_down", "debit_up",
     "ip_publique", "backup_connexion", "plan_ip", "plage_dhcp",
     "voip_solution", "voip_pabx", "notes"].forEach(f => {
      const el = document.getElementById("m_site_" + f);
      if (el) el.value = s[f] == null ? "" : s[f];
    });
    document.getElementById("m_site_voip_softphone").value = s.voip_softphone ? "1" : "0";
    document.getElementById("modal_site").hidden = false;
  }
  window.closeSiteModal = function () {
    document.getElementById("modal_site").hidden = true;
    currentSiteId = null;
  };
  window.saveSiteModal = function () {
    if (!currentSiteId) return;
    const payload = {};
    ["nom", "adresse", "fai", "type_connexion", "debit_down", "debit_up",
     "ip_publique", "backup_connexion", "plan_ip", "plage_dhcp",
     "voip_solution", "voip_pabx", "notes"].forEach(f => {
      const el = document.getElementById("m_site_" + f);
      if (el) payload[f] = el.value;
    });
    payload.voip_softphone = document.getElementById("m_site_voip_softphone").value === "1";
    fetch(`/api/site/${currentSiteId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(() => {
      loadSites();
      closeSiteModal();
    });
  };
  window.deleteSite = function () {
    if (!currentSiteId) return;
    if (!confirm("Supprimer ce site ?")) return;
    fetch(`/api/site/${currentSiteId}`, { method: "DELETE" }).then(() => {
      loadSites();
      closeSiteModal();
    });
  };

  const btnAddSite = document.getElementById("btn_add_site");
  if (btnAddSite) {
    btnAddSite.addEventListener("click", () => {
      const nom = prompt("Nom du site :", "Nouveau site");
      if (!nom) return;
      fetch(`/api/audit/${AUDIT_ID}/sites`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nom }),
      }).then(loadSites);
    });
  }

  function refreshSiteSelect(selectId, currentVal = null) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    sel.innerHTML = '<option value="">—</option>';
    sites.forEach(s => {
      const o = document.createElement("option");
      o.value = s.id; o.textContent = s.nom;
      if (currentVal && s.id === currentVal) o.selected = true;
      sel.appendChild(o);
    });
  }

  // -------------------- Sécurité (édition par site) --------------------
  function renderSecuriteList() {
    const c = document.getElementById("securite_container");
    if (!c) return;
    c.innerHTML = "";
    if (!sites.length) {
      c.innerHTML = '<p class="empty">Ajoutez un site dans l\'onglet 2.</p>';
      return;
    }
    sites.forEach(s => {
      const div = document.createElement("div");
      div.className = "site-card";
      div.innerHTML = `
        <h3 style="margin:0 0 10px">📍 ${escape(s.nom)}</h3>
        <div class="grid-2">
          <label>Antivirus (solution)
            <input data-sec="${s.id}.antivirus_solution" value="${escape(s.antivirus_solution || '')}"></label>
          <label>Gestion antivirus
            <select data-sec="${s.id}.antivirus_gestion">
              <option value="">—</option>
              <option ${s.antivirus_gestion === 'centralisee' ? 'selected' : ''} value="centralisee">Centralisée</option>
              <option ${s.antivirus_gestion === 'par_machine' ? 'selected' : ''} value="par_machine">Par machine</option>
            </select></label>
          <label>VPN — type
            <input data-sec="${s.id}.vpn_type" value="${escape(s.vpn_type || '')}"
                   placeholder="IPsec, SSL VPN, WireGuard..."></label>
          <label>VPN — utilisateurs clés
            <input data-sec="${s.id}.vpn_utilisateurs" value="${escape(s.vpn_utilisateurs || '')}"></label>
          <label>IDS/IPS activés ?
            <select data-sec="${s.id}.idsips_actif">
              <option value="0" ${!s.idsips_actif ? 'selected' : ''}>Non</option>
              <option value="1" ${s.idsips_actif ? 'selected' : ''}>Oui</option>
            </select></label>
          <label class="full">Méthodes d'accès à distance autorisées
            <textarea data-sec="${s.id}.methode_acces_distant" rows="2">${escape(s.methode_acces_distant || '')}</textarea></label>
        </div>`;
      c.appendChild(div);
    });
    // Branche autosave par site
    c.querySelectorAll("[data-sec]").forEach(el => {
      el.addEventListener("input", () => debouncedSaveSite(el));
      el.addEventListener("change", () => debouncedSaveSite(el));
    });
  }

  const siteSaveTimers = {};
  function debouncedSaveSite(el) {
    const [sid, field] = el.dataset.sec.split(".");
    const key = sid + "." + field;
    flagSaving();
    clearTimeout(siteSaveTimers[key]);
    siteSaveTimers[key] = setTimeout(() => {
      let v = el.value;
      if (field === "idsips_actif") v = v === "1";
      fetch(`/api/site/${sid}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: v }),
      }).then(r => flagSaved(r.ok));
    }, 500);
  }

  // -------------------- Liaisons --------------------
  function refreshLiaisonSelectors() {
    const src = document.getElementById("liaison_src");
    const dst = document.getElementById("liaison_dst");
    if (!src || !dst) return;
    const eqs = window.SchemaApp ? window.SchemaApp.getEquipements() : [];
    [src, dst].forEach(sel => {
      sel.innerHTML = '<option value="">—</option>';
      eqs.forEach(e => {
        const vis = (window.EQUIP_VISUAL || {})[e.type] || {};
        const o = document.createElement("option");
        o.value = e.id;
        o.textContent = `${vis.icon || ""} ${e.nom_hote || vis.label || e.type} ${e.ip ? "(" + e.ip + ")" : ""}`;
        sel.appendChild(o);
      });
    });
    renderLiaisonsTable();
  }

  function renderLiaisonsTable() {
    const tbody = document.querySelector("#liaisons_table tbody");
    if (!tbody) return;
    const ls = window.SchemaApp ? window.SchemaApp.getLiaisons() : [];
    const eqs = window.SchemaApp ? window.SchemaApp.getEquipements() : [];
    const eqById = Object.fromEntries(eqs.map(e => [e.id, e]));
    tbody.innerHTML = "";
    ls.forEach(l => {
      const s = eqById[l.source_id], d = eqById[l.dest_id];
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escape(s ? s.nom_hote || "?" : "?")}</td>
        <td>${escape(l.port_source || "")}</td>
        <td>${escape(d ? d.nom_hote || "?" : "?")}</td>
        <td>${escape(l.port_dest || "")}</td>
        <td>${escape(l.type || "")}</td>
        <td>${escape(l.vlan || "")}</td>
        <td>${escape(l.debit || "")}</td>
        <td><button class="btn btn-sm btn-danger" data-del-l="${l.id}">×</button></td>`;
      tr.querySelector("[data-del-l]").addEventListener("click", () => {
        fetch(`/api/liaison/${l.id}`, { method: "DELETE" }).then(() => {
          if (window.SchemaApp) window.SchemaApp.removeLiaison(l.id);
          renderLiaisonsTable();
        });
      });
      tbody.appendChild(tr);
    });
  }

  const btnAddLiaison = document.getElementById("btn_add_liaison");
  if (btnAddLiaison) {
    btnAddLiaison.addEventListener("click", () => {
      const src = parseInt(document.getElementById("liaison_src").value, 10);
      const dst = parseInt(document.getElementById("liaison_dst").value, 10);
      if (!src || !dst) { alert("Sélectionner source et destination"); return; }
      const payload = {
        source_id: src, dest_id: dst,
        type: document.getElementById("liaison_type").value,
        port_source: document.getElementById("liaison_port_src").value,
        port_dest: document.getElementById("liaison_port_dst").value,
        vlan: document.getElementById("liaison_vlan").value,
        debit: document.getElementById("liaison_debit").value,
      };
      fetch(`/api/audit/${AUDIT_ID}/liaisons`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(r => r.json()).then(l => {
        if (window.SchemaApp) window.SchemaApp.addLiaison(l);
        renderLiaisonsTable();
      });
    });
  }

  // -------------------- Serveurs (édition rapide) --------------------
  function renderServeursList() {
    const c = document.getElementById("serveurs_container");
    if (!c) return;
    const eqs = (window.SchemaApp ? window.SchemaApp.getEquipements() : [])
      .filter(e => ["serveur_physique", "serveur_virtuel", "hyperviseur"].includes(e.type));
    if (!eqs.length) {
      c.innerHTML = '<p class="empty">Ajoutez d\'abord un serveur dans l\'onglet 3.</p>';
      return;
    }
    c.innerHTML = "";
    eqs.forEach(e => {
      const vis = (window.EQUIP_VISUAL || {})[e.type] || {};
      const div = document.createElement("div");
      div.className = "site-card";
      div.innerHTML = `
        <div class="site-card-header">
          <strong>${vis.icon} ${escape(e.nom_hote || vis.label)}</strong>
          <button class="btn btn-sm" data-edit-serv="${e.id}">Éditer en détail</button>
        </div>
        <div class="grid-2">
          <label>OS<input data-serv="${e.id}.os" value="${escape(e.os || '')}"></label>
          <label>Version OS<input data-serv="${e.id}.os_version" value="${escape(e.os_version || '')}"></label>
          <label>IP<input data-serv="${e.id}.ip" value="${escape(e.ip || '')}"></label>
          <label>CPU<input data-serv="${e.id}.cpu" value="${escape(e.cpu || '')}"></label>
          <label>RAM<input data-serv="${e.id}.ram" value="${escape(e.ram || '')}"></label>
          <label>Stockage<input data-serv="${e.id}.stockage" value="${escape(e.stockage || '')}"></label>
          <label>RAID<input data-serv="${e.id}.raid" value="${escape(e.raid || '')}"></label>
          <label>Nb VM<input data-serv="${e.id}.nb_vm" type="number" value="${e.nb_vm || ''}"></label>
          <label class="full">Rôle / fonction
            <input data-serv="${e.id}.role" value="${escape(e.role || '')}"
              placeholder="AD, DNS, DHCP, fichiers, BDD, web, hyperviseur..."></label>
        </div>`;
      div.querySelector("[data-edit-serv]").addEventListener("click", () => openEqModal(e.id));
      c.appendChild(div);
    });
    c.querySelectorAll("[data-serv]").forEach(el => {
      el.addEventListener("input", () => debouncedSaveServ(el));
      el.addEventListener("change", () => debouncedSaveServ(el));
    });
  }
  const servSaveTimers = {};
  function debouncedSaveServ(el) {
    const [id, field] = el.dataset.serv.split(".");
    const key = id + "." + field;
    flagSaving();
    clearTimeout(servSaveTimers[key]);
    servSaveTimers[key] = setTimeout(() => {
      let v = el.value;
      if (field === "nb_vm") v = v ? parseInt(v, 10) : null;
      fetch(`/api/equipement/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: v }),
      }).then(r => r.json()).then(eq => {
        if (window.SchemaApp) window.SchemaApp.updateEquipement(eq);
        flagSaved(true);
      }).catch(() => flagSaved(false));
    }, 500);
  }

  // -------------------- Applications --------------------
  let apps = [];
  async function loadApps() {
    const r = await fetch(`/api/audit/${AUDIT_ID}`);
    // (les apps ne sont pas dans l'API audit GET pour l'instant — on les charge à part)
    // On utilise une API dédiée : non créée. À la place on stocke localement.
    renderAppsList();
  }
  function renderAppsList() {
    const c = document.getElementById("apps_container");
    if (!c) return;
    if (!apps.length) {
      c.innerHTML = '<p class="empty">Aucune application. Cliquez sur "+ Ajouter".</p>';
      return;
    }
    c.innerHTML = "";
    apps.forEach(a => c.appendChild(buildAppCard(a)));
  }
  function buildAppCard(a) {
    const div = document.createElement("div");
    div.className = "app-card";
    div.innerHTML = `
      <div class="grid-2">
        <label>Nom<input data-app="${a.id}.nom" value="${escape(a.nom || '')}"></label>
        <label>Type
          <select data-app="${a.id}.type">
            ${["", "ERP", "CRM", "GED", "Métier", "Comptabilité", "Paie", "Production", "Autre"]
              .map(t => `<option ${a.type === t ? 'selected' : ''} value="${t}">${t || '—'}</option>`).join("")}
          </select></label>
        <label>Éditeur<input data-app="${a.id}.editeur" value="${escape(a.editeur || '')}"></label>
        <label>Version<input data-app="${a.id}.version" value="${escape(a.version || '')}"></label>
        <label>Fournisseur support<input data-app="${a.id}.fournisseur_support" value="${escape(a.fournisseur_support || '')}"></label>
        <label>Contact support<input data-app="${a.id}.contact_support" value="${escape(a.contact_support || '')}"></label>
        <label>Criticité
          <select data-app="${a.id}.criticite">
            ${["", "faible", "moyenne", "haute", "critique"]
              .map(c => `<option ${a.criticite === c ? 'selected' : ''} value="${c}">${c || '—'}</option>`).join("")}
          </select></label>
        <label class="full">Commentaires
          <textarea data-app="${a.id}.commentaires" rows="2">${escape(a.commentaires || '')}</textarea></label>
      </div>
      <div style="text-align:right;margin-top:8px">
        <button class="btn btn-sm btn-danger" data-del-app="${a.id}">Supprimer</button>
      </div>`;
    div.querySelector("[data-del-app]").addEventListener("click", () => {
      if (!confirm("Supprimer cette application ?")) return;
      fetch(`/api/application/${a.id}`, { method: "DELETE" }).then(() => {
        apps = apps.filter(x => x.id !== a.id); renderAppsList();
      });
    });
    div.querySelectorAll("[data-app]").forEach(el => {
      el.addEventListener("input", () => debouncedSaveGeneric(el, "app", "application", apps));
      el.addEventListener("change", () => debouncedSaveGeneric(el, "app", "application", apps));
    });
    return div;
  }
  const btnAddApp = document.getElementById("btn_add_app");
  if (btnAddApp) {
    btnAddApp.addEventListener("click", () => {
      fetch(`/api/audit/${AUDIT_ID}/applications`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nom: "Nouvelle application" }),
      }).then(r => r.json()).then(a => { apps.push(a); renderAppsList(); });
    });
  }

  // -------------------- Sauvegardes --------------------
  let backups = [];
  function renderBackupsList() {
    const c = document.getElementById("backups_container");
    if (!c) return;
    if (!backups.length) {
      c.innerHTML = '<p class="empty">Aucune sauvegarde. Cliquez sur "+ Ajouter".</p>';
      return;
    }
    c.innerHTML = "";
    backups.forEach(b => c.appendChild(buildBackupCard(b)));
  }
  function buildBackupCard(b) {
    const div = document.createElement("div");
    div.className = "backup-card";
    div.innerHTML = `
      <div class="grid-2">
        <label>Périmètre<input data-bk="${b.id}.perimetre" value="${escape(b.perimetre || '')}"
                                placeholder="serveurs, postes, BDD..."></label>
        <label>Solution<input data-bk="${b.id}.solution" value="${escape(b.solution || '')}"
                               placeholder="Veeam, Synology, Acronis..."></label>
        <label>Type
          <select data-bk="${b.id}.type_sauvegarde">
            ${["", "full", "incrémentale", "différentielle", "snapshot", "cloud"]
              .map(t => `<option ${b.type_sauvegarde === t ? 'selected' : ''} value="${t}">${t || '—'}</option>`).join("")}
          </select></label>
        <label>Fréquence<input data-bk="${b.id}.frequence" value="${escape(b.frequence || '')}"
                                placeholder="quotidienne, hebdomadaire..."></label>
        <label>Cible<input data-bk="${b.id}.cible" value="${escape(b.cible || '')}"
                            placeholder="NAS, cloud Azure, bande..."></label>
        <label>Rétention<input data-bk="${b.id}.retention" value="${escape(b.retention || '')}"
                                placeholder="30j, 1an, GFS..."></label>
        <label>Dernière vérification<input data-bk="${b.id}.derniere_verification" value="${escape(b.derniere_verification || '')}"></label>
        <label>Chiffré
          <select data-bk="${b.id}.chiffrement">
            <option value="0" ${!b.chiffrement ? 'selected' : ''}>Non</option>
            <option value="1" ${b.chiffrement ? 'selected' : ''}>Oui</option>
          </select></label>
        <label>Externalisé
          <select data-bk="${b.id}.externalisation">
            <option value="0" ${!b.externalisation ? 'selected' : ''}>Non</option>
            <option value="1" ${b.externalisation ? 'selected' : ''}>Oui</option>
          </select></label>
        <label class="full">Commentaires<textarea data-bk="${b.id}.commentaires" rows="2">${escape(b.commentaires || '')}</textarea></label>
      </div>
      <div style="text-align:right;margin-top:8px">
        <button class="btn btn-sm btn-danger" data-del-bk="${b.id}">Supprimer</button>
      </div>`;
    div.querySelector("[data-del-bk]").addEventListener("click", () => {
      if (!confirm("Supprimer cette sauvegarde ?")) return;
      fetch(`/api/sauvegarde/${b.id}`, { method: "DELETE" }).then(() => {
        backups = backups.filter(x => x.id !== b.id); renderBackupsList();
      });
    });
    div.querySelectorAll("[data-bk]").forEach(el => {
      el.addEventListener("input", () => debouncedSaveGeneric(el, "bk", "sauvegarde", backups));
      el.addEventListener("change", () => debouncedSaveGeneric(el, "bk", "sauvegarde", backups));
    });
    return div;
  }
  const btnAddBk = document.getElementById("btn_add_backup");
  if (btnAddBk) {
    btnAddBk.addEventListener("click", () => {
      fetch(`/api/audit/${AUDIT_ID}/sauvegardes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ perimetre: "Serveurs" }),
      }).then(r => r.json()).then(b => { backups.push(b); renderBackupsList(); });
    });
  }

  // -------------------- Messagerie --------------------
  let msgs = [];
  function renderMsgsList() {
    const c = document.getElementById("msgs_container");
    if (!c) return;
    if (!msgs.length) {
      c.innerHTML = '<p class="empty">Aucune messagerie. Cliquez sur "+ Ajouter".</p>';
      return;
    }
    c.innerHTML = "";
    msgs.forEach(m => c.appendChild(buildMsgCard(m)));
  }
  function buildMsgCard(m) {
    const div = document.createElement("div");
    div.className = "msg-card";
    div.innerHTML = `
      <div class="grid-2">
        <label>Solution<input data-msg="${m.id}.solution" value="${escape(m.solution || '')}"
                               placeholder="M365, Google Workspace, Exchange, OVH..."></label>
        <label>Protocole<input data-msg="${m.id}.protocole" value="${escape(m.protocole || '')}"
                                placeholder="IMAP+SMTP, MAPI, ActiveSync..."></label>
        <label>Domaine<input data-msg="${m.id}.domaine" value="${escape(m.domaine || '')}"></label>
        <label>Nombre de boîtes<input data-msg="${m.id}.nb_boites" type="number" value="${m.nb_boites || ''}"></label>
        <label>Filtre antispam<input data-msg="${m.id}.filtre_antispam" value="${escape(m.filtre_antispam || '')}"></label>
        <label>MX records<input data-msg="${m.id}.mx_records" value="${escape(m.mx_records || '')}"></label>
        <label class="full">Liste des adresses email
          <textarea data-msg="${m.id}.adresses" rows="3">${escape(m.adresses || '')}</textarea></label>
        <label class="full">Commentaires<textarea data-msg="${m.id}.commentaires" rows="2">${escape(m.commentaires || '')}</textarea></label>
      </div>
      <div style="text-align:right;margin-top:8px">
        <button class="btn btn-sm btn-danger" data-del-msg="${m.id}">Supprimer</button>
      </div>`;
    div.querySelector("[data-del-msg]").addEventListener("click", () => {
      if (!confirm("Supprimer cette messagerie ?")) return;
      fetch(`/api/messagerie/${m.id}`, { method: "DELETE" }).then(() => {
        msgs = msgs.filter(x => x.id !== m.id); renderMsgsList();
      });
    });
    div.querySelectorAll("[data-msg]").forEach(el => {
      el.addEventListener("input", () => debouncedSaveGeneric(el, "msg", "messagerie", msgs));
      el.addEventListener("change", () => debouncedSaveGeneric(el, "msg", "messagerie", msgs));
    });
    return div;
  }
  const btnAddMsg = document.getElementById("btn_add_msg");
  if (btnAddMsg) {
    btnAddMsg.addEventListener("click", () => {
      fetch(`/api/audit/${AUDIT_ID}/messageries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ solution: "" }),
      }).then(r => r.json()).then(m => { msgs.push(m); renderMsgsList(); });
    });
  }

  // -------------------- Save générique --------------------
  const genericTimers = {};
  function debouncedSaveGeneric(el, prefix, endpoint, store) {
    const [id, field] = el.dataset[prefix].split(".");
    const key = `${prefix}.${id}.${field}`;
    flagSaving();
    clearTimeout(genericTimers[key]);
    genericTimers[key] = setTimeout(() => {
      let v = el.value;
      if (["chiffrement", "externalisation"].includes(field)) v = v === "1";
      if (["nb_boites", "nb_vm", "serveur_hote_id"].includes(field)) v = v ? parseInt(v, 10) : null;
      fetch(`/api/${endpoint}/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: v }),
      }).then(r => r.json()).then(updated => {
        const i = store.findIndex(x => x.id == id);
        if (i >= 0) store[i] = updated;
        flagSaved(true);
      }).catch(() => flagSaved(false));
    }, 500);
  }

  // -------------------- Helpers --------------------
  function escape(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  // -------------------- Init --------------------
  document.addEventListener("schema:loaded", () => {
    renderEqList();
    refreshLiaisonSelectors();
  });

  // -------------------- Conformité (affichage des bilans) --------------------
  let conformites = [];
  const STATUT_VISUAL = {
    ok: { color: "#198754", label: "Conforme", icon: "✓" },
    attention: { color: "#fd7e14", label: "Attention", icon: "!" },
    critique: { color: "#dc3545", label: "Critique", icon: "✕" },
    indetermine: { color: "#adb5bd", label: "Indéterminé", icon: "?" },
    na: { color: "#ced4da", label: "N/A", icon: "–" },
  };
  const NIVEAU_VISUAL = {
    conforme: { color: "#198754", label: "Conforme" },
    partiel: { color: "#fd7e14", label: "Partiellement conforme" },
    non_conforme: { color: "#dc3545", label: "Non conforme" },
    indetermine: { color: "#adb5bd", label: "Indéterminé" },
  };

  function loadConformites() {
    fetch(`/api/audit/${AUDIT_ID}/conformites`).then(r => r.json()).then(d => {
      conformites = d || [];
      renderConformites();
    }).catch(() => {});
  }

  function renderConformites() {
    const c = document.getElementById("conformite_container");
    if (!c) return;
    if (!conformites.length) {
      c.innerHTML = '<p class="empty">Aucun bilan de conformité. Lancez l\'agent sur une machine puis importez le JSON.</p>';
      return;
    }
    c.innerHTML = "";
    conformites.forEach(conf => c.appendChild(buildConfCard(conf)));
  }

  function buildConfCard(conf) {
    const nv = NIVEAU_VISUAL[conf.niveau] || NIVEAU_VISUAL.indetermine;
    const div = document.createElement("div");
    div.className = "site-card";
    const scoreTxt = conf.score == null ? "—" : conf.score + "/100";
    let rows = "";
    (conf.resultats || []).forEach(r => {
      const sv = STATUT_VISUAL[r.statut] || STATUT_VISUAL.indetermine;
      const lbl = (window.CONF_LABELS && window.CONF_LABELS[r.id]) || r.id;
      rows += `<tr>
        <td><span class="conf-dot" style="background:${sv.color}">${sv.icon}</span>
            ${escape(lbl)}</td>
        <td style="color:${sv.color};font-weight:600">${sv.label}</td>
        <td><small class="muted">${escape(r.detail || "")}</small></td>
      </tr>`;
    });
    // Bloc "Détails" (winaudit-like) — affiché seulement si has_details
    let detailsBlock = "";
    if (conf.has_details && conf.details_counts) {
      const dc = conf.details_counts;
      const remoteAlert = dc.remote_access > 0
        ? `<span style="color:#dc3545;font-weight:600">⚠ ${dc.remote_access} accès distant(s) détecté(s)</span> · `
        : "";
      detailsBlock = `
        <div class="conf-details-summary">
          <strong>📋 Détails collectés :</strong>
          ${remoteAlert}
          ${dc.applications || 0} applis ·
          ${dc.updates || 0} MAJ ·
          ${dc.users || 0} comptes ·
          ${dc.services || 0} services ·
          ${dc.drivers || 0} pilotes
          <button class="btn btn-sm" data-toggle-details="${conf.id}"
                  style="margin-left:10px">Voir les détails ▾</button>
        </div>
        <div class="conf-details-pane" id="conf_details_${conf.id}" hidden></div>`;
    }
    div.innerHTML = `
      <div class="site-card-header">
        <strong>🖥 ${escape(conf.machine || "Machine")}
          <span class="muted">(${escape(conf.profil || "?")})</span></strong>
        <div style="display:flex;align-items:center;gap:10px">
          <span class="conf-badge" style="background:${nv.color}">${nv.label}</span>
          <span style="font-weight:700;font-size:18px;color:${nv.color}">${scoreTxt}</span>
          <button class="btn btn-sm btn-danger" data-del-conf="${conf.id}">×</button>
        </div>
      </div>
      <small class="muted">Collecté le ${escape(conf.date_collecte || "?")}
        · ${conf.nb_critiques} point(s) critique(s)</small>
      <table class="table" style="margin-top:8px">
        <thead><tr><th>Contrôle</th><th>Statut</th><th>Détail</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${detailsBlock}`;
    div.querySelector("[data-del-conf]").addEventListener("click", () => {
      if (!confirm("Supprimer ce bilan de conformité ?")) return;
      fetch(`/api/conformite/${conf.id}`, { method: "DELETE" }).then(() => {
        conformites = conformites.filter(x => x.id !== conf.id);
        renderConformites();
      });
    });
    const togBtn = div.querySelector("[data-toggle-details]");
    if (togBtn) {
      togBtn.addEventListener("click", () => toggleConfDetails(conf.id, togBtn));
    }
    return div;
  }

  // -------------------- Détails étendus (winaudit-like) --------------------
  const DETAIL_SECTIONS = [
    { key: "remote_access", label: "⚠ Accès distants détectés",
      cols: [["nom","Logiciel"],["version","Version"],["editeur","Éditeur"]] },
    { key: "applications", label: "Applications installées",
      cols: [["nom","Nom"],["version","Version"],["editeur","Éditeur"],
             ["date_install","Installé"]] },
    { key: "updates", label: "Mises à jour Windows",
      cols: [["kb","KB"],["type","Type"],["date_install","Date"],
             ["installe_par","Installé par"]] },
    { key: "users", label: "Comptes utilisateurs",
      cols: [["nom","Nom"],["active","Actif"],["description","Description"],
             ["derniere_connexion","Dernière connexion"],
             ["mdp_jamais_expire","Mdp éternel"]] },
    { key: "services", label: "Services Windows",
      cols: [["nom_affiche","Service"],["etat","État"],
             ["demarrage","Démarrage"],["compte","Compte"]] },
    { key: "drivers", label: "Pilotes",
      cols: [["peripherique","Périphérique"],["fabricant","Fabricant"],
             ["version","Version"],["date","Date"]] },
    { key: "scheduled_tasks", label: "Tâches planifiées",
      cols: [["nom","Tâche"],["chemin","Chemin"],["etat","État"],
             ["derniere_exec","Dernière exéc."]] },
    { key: "firewall_rules", label: "Règles pare-feu",
      cols: [["nom","Règle"],["direction","Direction"],["profil","Profil"]] },
    { key: "sessions", label: "Sessions ouvertes",
      cols: [["utilisateur","Utilisateur"],["etat","État"],["session","Session"]] },
    { key: "server_roles", label: "Rôles serveur installés",
      cols: [["libelle","Rôle"],["nom","Nom technique"]] },
    { key: "server_features", label: "Fonctionnalités serveur",
      cols: [["libelle","Fonctionnalité"],["nom","Nom technique"]] },
    { key: "volumes", label: "Volumes",
      cols: [["lettre","Lettre"],["label","Label"],["fs","FS"],
             ["taille_go","Taille (Go)"],["libre_go","Libre (Go)"]] },
    { key: "printers", label: "Imprimantes",
      cols: [["nom","Nom"],["marque","Marque"],["modele","Modèle"],
             ["ip","IP"],["port","Port"],["type_reseau","Type"]] },
    { key: "network", label: "Configuration réseau",
      cols: [["interface","Interface"],["ip","IP"],["mac","MAC"],
             ["passerelle","Passerelle"],["dns","DNS"]] },
    { key: "auth_failures", label: "Échecs d'authentification (30j)",
      cols: [["date","Date"],["message","Message"]] },
  ];

  async function toggleConfDetails(confId, button) {
    const pane = document.getElementById(`conf_details_${confId}`);
    if (!pane) return;
    if (!pane.hidden) {
      pane.hidden = true;
      button.textContent = "Voir les détails ▾";
      return;
    }
    if (!pane.dataset.loaded) {
      pane.innerHTML = '<p class="muted">Chargement…</p>';
      try {
        const r = await fetch(`/api/conformite/${confId}/details`);
        const det = await r.json();
        pane.innerHTML = renderConfDetails(confId, det);
        pane.dataset.loaded = "1";
      } catch (e) {
        pane.innerHTML = '<p class="muted">Erreur de chargement.</p>';
      }
    }
    pane.hidden = false;
    button.textContent = "Masquer les détails ▴";
  }

  function renderConfDetails(confId, det) {
    let html = '<div class="conf-details-sections">';
    let nbVisibles = 0;
    DETAIL_SECTIONS.forEach(sec => {
      const rows = det[sec.key];
      if (!Array.isArray(rows) || rows.length === 0) return;
      nbVisibles++;
      const csvUrl = `/api/conformite/${confId}/details/${sec.key}/csv`;
      let table = `<table class="table" style="margin:6px 0"><thead><tr>`;
      sec.cols.forEach(c => { table += `<th>${escape(c[1])}</th>`; });
      table += `</tr></thead><tbody>`;
      rows.forEach(row => {
        table += "<tr>";
        sec.cols.forEach(c => {
          let v = row[c[0]];
          if (v === true) v = "Oui";
          else if (v === false) v = "Non";
          else if (v == null) v = "";
          table += `<td>${escape(v)}</td>`;
        });
        table += "</tr>";
      });
      table += `</tbody></table>`;
      html += `
        <details class="conf-section" style="margin:8px 0">
          <summary style="cursor:pointer;padding:6px 0;font-weight:600">
            ${escape(sec.label)} <span class="muted">(${rows.length})</span>
            <a href="${csvUrl}" class="btn btn-sm btn-export"
               style="float:right;margin-left:8px"
               download>📥 CSV</a>
          </summary>
          ${table}
        </details>`;
    });
    if (nbVisibles === 0) {
      html += '<p class="muted">Aucune section ne contient de données.</p>';
    }
    html += "</div>";
    return html;
  }

  // -------------------- Import (scanner réseau / agent poste) --------------------
  const btnImport = document.getElementById("btn_import");
  const importFile = document.getElementById("import_file");
  if (btnImport && importFile) {
    btnImport.addEventListener("click", () => importFile.click());
    importFile.addEventListener("change", () => {
      const file = importFile.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("fichier", file);
      flagSaving();
      fetch(`/api/audit/${AUDIT_ID}/import`, { method: "POST", body: fd })
        .then(r => r.json())
        .then(res => {
          importFile.value = "";  // reset pour réimport du même fichier
          if (res.error) {
            flagSaved(false);
            alert("Import échoué : " + res.error);
            return;
          }
          flagSaved(true);
          if (res.mode === "inventaire") {
            const r = res.resultat;
            const niveau = { conforme: "Conforme", partiel: "Partiellement conforme",
                             non_conforme: "NON CONFORME", indetermine: "Indéterminé" }[r.niveau] || r.niveau;
            let msg = `Inventaire poste importé :\n` +
                  `• Machine ${r.action === "cree" ? "créée" : "mise à jour"}\n` +
                  `• Conformité : ${r.score == null ? "—" : r.score + "/100"} (${niveau})`;
            if (r.printers_created > 0 || r.printers_linked > 0) {
              msg += `\n• Imprimantes : ${r.printers_created} créée(s), ${r.printers_linked} liaison(s) ajoutée(s)`;
            }
            alert(msg);
            loadConformites();
          } else {
            const s = res.stats;
            alert(`Import terminé :\n` +
                  `• ${s.crees} équipement(s) créé(s)\n` +
                  `• ${s.maj} mis à jour\n` +
                  `• ${s.ignores} déjà à jour (ignorés)\n` +
                  `• ${s.total} au total dans le fichier`);
          }
          // Recharge tout le schéma + les listes
          if (window.SchemaApp) window.SchemaApp.load();
        })
        .catch(err => { flagSaved(false); alert("Erreur réseau : " + err); });
    });
  }

  // Charge les bilans de conformité existants
  loadConformites();

  // Chargement initial des sites + apps + backups + msgs
  fetch(`/api/audit/${AUDIT_ID}`).then(r => r.json()).then(data => {
    sites = data.sites || [];
    renderSitesList();
    renderSecuriteList();
    refreshSiteSelect("m_eq_site_id");
  });
  // Charger apps / sauvegardes / messageries existantes
  fetch(`/api/audit/${AUDIT_ID}/applications`).then(r => r.json()).then(d => {
    apps = d || []; renderAppsList();
  });
  fetch(`/api/audit/${AUDIT_ID}/sauvegardes`).then(r => r.json()).then(d => {
    backups = d || []; renderBackupsList();
  });
  fetch(`/api/audit/${AUDIT_ID}/messageries`).then(r => r.json()).then(d => {
    msgs = d || []; renderMsgsList();
  });

  return { openEqModal };
})();
