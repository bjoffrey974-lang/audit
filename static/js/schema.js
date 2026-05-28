/* =====================================================================
   schema.js — rendu SVG temps réel de la topologie réseau
   - charge équipements + liaisons via API JSON
   - drag & drop pour repositionner (sauvegarde pos_x/pos_y)
   - double-clic pour ouvrir le modal d'édition
   - mode logique / physique
   - auto-layout (positionnement en arbre)
===================================================================== */

const SVG_NS = "http://www.w3.org/2000/svg";

window.SchemaApp = (function () {
  let equipements = [];
  let liaisons = [];
  let vue = "logique";
  const svg = document.getElementById("schema_svg");
  if (!svg) return null;

  // -------------------- Chargement --------------------
  async function load() {
    const [eqs, ls] = await Promise.all([
      fetch(`/api/audit/${window.AUDIT_ID}/equipements`).then(r => r.json()),
      fetch(`/api/audit/${window.AUDIT_ID}/liaisons`).then(r => r.json()),
    ]);
    equipements = eqs;
    liaisons = ls;
    render();
    // Notifier l'app pour qu'elle reconstruise les listes
    document.dispatchEvent(new CustomEvent("schema:loaded", {
      detail: { equipements, liaisons }
    }));
  }

  // -------------------- Rendu --------------------
  function render() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    // Calcule la taille
    let maxX = 1200, maxY = 800;
    equipements.forEach(e => {
      maxX = Math.max(maxX, (e.pos_x || 0) + 200);
      maxY = Math.max(maxY, (e.pos_y || 0) + 150);
    });
    svg.setAttribute("viewBox", `0 0 ${maxX} ${maxY}`);

    // Defs : marqueurs de flèche par couleur
    const defs = el("defs");
    svg.appendChild(defs);

    // Liaisons d'abord (en dessous)
    const eqById = Object.fromEntries(equipements.map(e => [e.id, e]));
    liaisons.forEach(l => drawLiaison(l, eqById));

    // Relations d'hébergement (VM -> hyperviseur via parent_id)
    if (vue === "physique") {
      equipements.forEach(h => {
        if (h.type !== "hyperviseur") return;
        const vms = equipements.filter(e => e.parent_id === h.id);
        if (vms.length) drawHostContainer(h, vms);
      });
    } else {
      equipements.forEach(e => {
        if (e.parent_id && eqById[e.parent_id]) {
          drawHostLink(e, eqById[e.parent_id]);
        }
      });
    }

    // Équipements
    equipements.forEach(e => drawNode(e));

    // Si vide, message d'aide
    if (!equipements.length) {
      const g = el("g");
      const text = el("text", {
        x: maxX / 2, y: maxY / 2,
        "text-anchor": "middle",
        "font-size": "18", fill: "#adb5bd",
        "font-family": "Arial"
      });
      text.textContent = "Ajoutez des équipements depuis l'onglet 3";
      g.appendChild(text);
      svg.appendChild(g);
    }
  }

  function drawNode(e) {
    const vis = (window.EQUIP_VISUAL || {})[e.type] || { color: "#6c757d", label: "?" };
    const g = el("g", {
      class: "schema-node",
      transform: `translate(${e.pos_x || 0},${e.pos_y || 0})`,
      "data-eq-id": e.id,
    });
    // Box
    g.appendChild(el("rect", {
      class: "node-box",
      width: 120, height: 80, rx: 8,
      fill: "white", stroke: vis.color, "stroke-width": 2,
    }));
    g.appendChild(el("rect", {
      width: 120, height: 22, rx: 8, fill: vis.color,
    }));
    g.appendChild(el("rect", {
      y: 14, width: 120, height: 8, fill: vis.color,
    }));
    g.appendChild(text(60, 16, (vis.label || "").toUpperCase(), {
      "text-anchor": "middle", "font-size": "10",
      "font-weight": "bold", fill: "white",
    }));
    g.appendChild(text(60, 42, truncate(e.nom_hote || vis.label, 18), {
      "text-anchor": "middle", "font-size": "11", "font-weight": "bold",
    }));
    g.appendChild(text(60, 58, truncate(e.ip || "", 18), {
      "text-anchor": "middle", "font-size": "9", fill: "#6c757d",
    }));
    if (vue === "physique" && (e.rack || e.rack_u)) {
      const tag = [e.rack, e.rack_u].filter(Boolean).join(" ");
      g.appendChild(text(60, 72, "📍 " + tag, {
        "text-anchor": "middle", "font-size": "9", fill: "#6c757d",
      }));
    } else if (e.vlan) {
      g.appendChild(text(60, 72, "VLAN " + e.vlan, {
        "text-anchor": "middle", "font-size": "9", fill: "#6c757d",
      }));
    }
    // Interactions
    makeDraggable(g, e);
    g.addEventListener("dblclick", () => {
      if (window.AppLogic) window.AppLogic.openEqModal(e.id);
    });
    svg.appendChild(g);
  }

  // Vue logique : lien pointillé gris "hébergé par" (VM -> hyperviseur)
  function drawHostLink(vm, host) {
    const x1 = (vm.pos_x || 0) + 60;
    const y1 = (vm.pos_y || 0) + 40;
    const x2 = (host.pos_x || 0) + 60;
    const y2 = (host.pos_y || 0) + 40;
    svg.appendChild(el("line", {
      x1, y1, x2, y2,
      stroke: "#adb5bd", "stroke-width": 1.5,
      "stroke-dasharray": "2,3",
      "data-host-link": vm.id,
    }));
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    svg.appendChild(el("rect", {
      x: mx - 38, y: my - 9, width: 76, height: 13, rx: 3,
      fill: "white", stroke: "#adb5bd", "stroke-width": 0.5, opacity: 0.9,
    }));
    svg.appendChild(text(mx, my + 1, "hébergé par", {
      "text-anchor": "middle", "font-size": "8", fill: "#6c757d",
    }));
  }

  // Vue physique : cadre conteneur englobant l'hyperviseur et ses VM
  function drawHostContainer(host, vms) {
    const all = [host, ...vms];
    const xs = all.map(e => e.pos_x || 0);
    const ys = all.map(e => e.pos_y || 0);
    const minX = Math.min(...xs) - 16;
    const minY = Math.min(...ys) - 28;
    const maxX = Math.max(...xs) + 120 + 16;
    const maxY = Math.max(...ys) + 80 + 16;
    const vis = (window.EQUIP_VISUAL || {}).hyperviseur || { color: "#0f5132" };
    svg.appendChild(el("rect", {
      x: minX, y: minY, width: maxX - minX, height: maxY - minY, rx: 12,
      fill: vis.color, "fill-opacity": 0.05,
      stroke: vis.color, "stroke-width": 1.5, "stroke-dasharray": "6,4",
    }));
    const label = `📦 ${host.nom_hote || "Hyperviseur"}${
      host.modele ? " — " + host.modele : ""} (${vms.length} VM)`;
    svg.appendChild(el("rect", {
      x: minX, y: minY, width: Math.min(label.length * 6.2 + 16, maxX - minX),
      height: 18, rx: 6, fill: vis.color,
    }));
    svg.appendChild(text(minX + 8, minY + 13, label, {
      "font-size": "10", "font-weight": "bold", fill: "white",
    }));
  }

  function drawLiaison(l, eqById) {
    const s = eqById[l.source_id];
    const d = eqById[l.dest_id];
    if (!s || !d) return;
    const x1 = (s.pos_x || 0) + 60;
    const y1 = (s.pos_y || 0) + 40;
    const x2 = (d.pos_x || 0) + 60;
    const y2 = (d.pos_y || 0) + 40;
    let stroke = "#0d6efd", dash = "";
    if (l.type === "wifi") { stroke = "#20c997"; dash = "6,4"; }
    else if (l.type === "fibre") { stroke = "#ffc107"; }
    else if (l.type === "vpn" || l.type === "sdwan") {
      stroke = "#6610f2"; dash = "4,3";
    } else if (l.type === "sip-trunk") { stroke = "#d63384"; }
    svg.appendChild(el("line", {
      x1, y1, x2, y2,
      stroke, "stroke-width": 2,
      "stroke-dasharray": dash,
      "data-liaison-id": l.id,
    }));
    if (l.vlan || l.debit) {
      const label = [l.vlan, l.debit].filter(Boolean).join(" ");
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      svg.appendChild(el("rect", {
        x: mx - 30, y: my - 10, width: 60, height: 14, rx: 3,
        fill: "white", stroke, "stroke-width": 0.5, opacity: 0.9,
      }));
      svg.appendChild(text(mx, my, label, {
        "text-anchor": "middle", "font-size": "10", fill: stroke,
      }));
    }
  }

  // -------------------- Drag & drop --------------------
  function makeDraggable(g, eq) {
    let dragging = false, startX, startY, origX, origY;
    g.addEventListener("mousedown", (ev) => {
      if (ev.detail >= 2) return; // double-click handled separately
      dragging = true;
      g.classList.add("dragging");
      const pt = clientToSvg(ev);
      startX = pt.x; startY = pt.y;
      origX = eq.pos_x || 0; origY = eq.pos_y || 0;
      ev.preventDefault();
    });
    document.addEventListener("mousemove", (ev) => {
      if (!dragging) return;
      const pt = clientToSvg(ev);
      eq.pos_x = origX + (pt.x - startX);
      eq.pos_y = origY + (pt.y - startY);
      g.setAttribute("transform", `translate(${eq.pos_x},${eq.pos_y})`);
      // Re-dessiner uniquement les liaisons touchées
      updateLiaisons(eq.id);
    });
    document.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      g.classList.remove("dragging");
      // Sauvegarder la position
      fetch(`/api/equipement/${eq.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pos_x: eq.pos_x, pos_y: eq.pos_y }),
      });
    });
  }

  function updateLiaisons(eqId) {
    // Reconstruction simple : on re-rend tout (peu coûteux pour <100 nœuds)
    render();
  }

  function clientToSvg(ev) {
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }

  // -------------------- Auto-layout (arbre hiérarchique simple) --------------------
  function autoLayout() {
    // Ordre par "criticité" (Internet/box/FW/router/switch/AP/serveur/poste)
    const order = [
      "internet", "modem_box", "firewall", "routeur", "switch", "ap_wifi",
      "hyperviseur", "serveur_physique", "nas", "san",
      "serveur_virtuel", "ipbx", "imprimante", "poste", "telephone",
      "scanner", "onduleur", "autre",
    ];
    const groups = {};
    equipements.forEach(e => {
      (groups[e.type] = groups[e.type] || []).push(e);
    });
    const colW = 160, rowH = 110;
    let y = 40;
    order.forEach(type => {
      const arr = groups[type];
      if (!arr || !arr.length) return;
      arr.forEach((e, i) => {
        e.pos_x = 40 + i * colW;
        e.pos_y = y;
      });
      y += rowH;
    });
    // Sauvegarde en lot
    Promise.all(equipements.map(e =>
      fetch(`/api/equipement/${e.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pos_x: e.pos_x, pos_y: e.pos_y }),
      })
    )).then(() => render());
  }

  // -------------------- Helpers SVG --------------------
  function el(tag, attrs = {}) {
    const e = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v != null && v !== "") e.setAttribute(k, v);
    }
    return e;
  }
  function text(x, y, content, attrs = {}) {
    const t = el("text", { x, y, ...attrs });
    t.textContent = content;
    return t;
  }
  function truncate(s, n) {
    s = String(s || "");
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  // -------------------- API publique --------------------
  function setVue(v) { vue = v; render(); }
  function addEquipement(eq) {
    equipements.push(eq);
    render();
  }
  function removeEquipement(id) {
    equipements = equipements.filter(e => e.id !== id);
    liaisons = liaisons.filter(l => l.source_id !== id && l.dest_id !== id);
    render();
  }
  function updateEquipement(eq) {
    const i = equipements.findIndex(e => e.id === eq.id);
    if (i >= 0) equipements[i] = eq;
    render();
  }
  function addLiaison(l) { liaisons.push(l); render(); }
  function removeLiaison(id) {
    liaisons = liaisons.filter(l => l.id !== id);
    render();
  }
  function getEquipements() { return equipements; }
  function getLiaisons() { return liaisons; }

  // -------------------- Évènements UI --------------------
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('input[name="vue"]').forEach(r => {
      r.addEventListener("change", e => setVue(e.target.value));
    });
    const btn = document.getElementById("btn_auto_layout");
    if (btn) btn.addEventListener("click", autoLayout);
    load();
  });

  return {
    load, render, setVue, autoLayout,
    addEquipement, updateEquipement, removeEquipement,
    addLiaison, removeLiaison,
    getEquipements, getLiaisons,
  };
})();
