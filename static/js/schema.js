/* =====================================================================
   schema.js — rendu SVG temps réel de la topologie réseau
   - charge équipements + liaisons via API JSON
   - drag & drop pour repositionner (sauvegarde pos_x/pos_y)
   - double-clic pour ouvrir le modal d'édition
   - mode logique / physique
   - auto-layout (positionnement en arbre)
===================================================================== */

const SVG_NS = "http://www.w3.org/2000/svg";

// ===== Bibliothèque d'icônes SVG par type d'équipement =====
// Chaque icône est conçue pour rentrer dans un viewBox 24x16 (4:3 horizontal)
// et s'affiche dans le bandeau coloré supérieur des boîtes (à gauche du texte).
// Toutes les formes sont en stroke="white" / fill="none" (le bandeau est
// déjà coloré), avec stroke-width 1.4 pour bonne visibilité.
//
// Les icônes sont des chaînes (markup SVG) injectées via innerHTML dans un <g>
// car createElementNS est verbeux pour des formes complexes.
const SCHEMA_ICONS = {
  modem_box:
    '<rect x="3" y="6" width="18" height="8" rx="1" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<line x1="6" y1="6" x2="6" y2="2" stroke="white" stroke-width="1.4"/>' +
    '<line x1="18" y1="6" x2="18" y2="2" stroke="white" stroke-width="1.4"/>' +
    '<circle cx="7" cy="10" r="0.8" fill="white"/>' +
    '<circle cx="10" cy="10" r="0.8" fill="white"/>' +
    '<circle cx="13" cy="10" r="0.8" fill="white"/>',

  firewall:
    '<rect x="3" y="3" width="18" height="10" rx="0.5" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<line x1="3" y1="7" x2="21" y2="7" stroke="white" stroke-width="1"/>' +
    '<line x1="3" y1="10" x2="21" y2="10" stroke="white" stroke-width="1"/>' +
    '<line x1="9" y1="3" x2="9" y2="7" stroke="white" stroke-width="1"/>' +
    '<line x1="15" y1="3" x2="15" y2="7" stroke="white" stroke-width="1"/>' +
    '<line x1="6" y1="7" x2="6" y2="10" stroke="white" stroke-width="1"/>' +
    '<line x1="12" y1="7" x2="12" y2="10" stroke="white" stroke-width="1"/>' +
    '<line x1="18" y1="7" x2="18" y2="10" stroke="white" stroke-width="1"/>' +
    '<line x1="9" y1="10" x2="9" y2="13" stroke="white" stroke-width="1"/>' +
    '<line x1="15" y1="10" x2="15" y2="13" stroke="white" stroke-width="1"/>',

  routeur:
    '<rect x="4" y="7" width="16" height="6" rx="1" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<line x1="7" y1="7" x2="5" y2="3" stroke="white" stroke-width="1.4" stroke-linecap="round"/>' +
    '<line x1="17" y1="7" x2="19" y2="3" stroke="white" stroke-width="1.4" stroke-linecap="round"/>' +
    '<circle cx="8" cy="10" r="0.7" fill="white"/>' +
    '<circle cx="12" cy="10" r="0.7" fill="white"/>' +
    '<circle cx="16" cy="10" r="0.7" fill="white"/>',

  switch:
    '<rect x="2" y="5" width="20" height="6" rx="0.5" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<rect x="4" y="7" width="1.5" height="2" fill="white"/>' +
    '<rect x="6.5" y="7" width="1.5" height="2" fill="white"/>' +
    '<rect x="9" y="7" width="1.5" height="2" fill="white"/>' +
    '<rect x="11.5" y="7" width="1.5" height="2" fill="white"/>' +
    '<rect x="14" y="7" width="1.5" height="2" fill="white"/>' +
    '<rect x="16.5" y="7" width="1.5" height="2" fill="white"/>' +
    '<rect x="19" y="7" width="1.5" height="2" fill="white"/>',

  ap_wifi:
    '<path d="M 4 14 Q 12 6 20 14" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<path d="M 7 12 Q 12 7 17 12" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<circle cx="12" cy="11" r="1" fill="white"/>' +
    '<line x1="12" y1="14" x2="12" y2="15" stroke="white" stroke-width="1.4"/>',

  serveur_physique:
    '<rect x="2" y="4" width="20" height="4" rx="0.5" stroke="white" stroke-width="1.2" fill="none"/>' +
    '<rect x="2" y="9" width="20" height="4" rx="0.5" stroke="white" stroke-width="1.2" fill="none"/>' +
    '<circle cx="4.5" cy="6" r="0.6" fill="white"/>' +
    '<rect x="6" y="5.5" width="8" height="1" fill="white"/>' +
    '<circle cx="4.5" cy="11" r="0.6" fill="white"/>' +
    '<rect x="6" y="10.5" width="8" height="1" fill="white"/>',

  hyperviseur:
    '<rect x="2" y="4" width="20" height="4" rx="0.5" stroke="white" stroke-width="1.2" fill="none"/>' +
    '<rect x="2" y="9" width="20" height="4" rx="0.5" stroke="white" stroke-width="1.2" fill="none"/>' +
    '<circle cx="4.5" cy="6" r="0.6" fill="white"/>' +
    '<circle cx="4.5" cy="11" r="0.6" fill="white"/>' +
    '<rect x="15" y="5" width="2.5" height="2.5" stroke="white" stroke-width="0.8" fill="none"/>' +
    '<rect x="18" y="5" width="2.5" height="2.5" stroke="white" stroke-width="0.8" fill="none"/>' +
    '<rect x="15" y="10" width="2.5" height="2.5" stroke="white" stroke-width="0.8" fill="none"/>' +
    '<rect x="18" y="10" width="2.5" height="2.5" stroke="white" stroke-width="0.8" fill="none"/>',

  serveur_virtuel:
    '<rect x="4" y="3" width="16" height="11" rx="1.5" stroke="white" stroke-width="1.4" fill="none" stroke-dasharray="2,1"/>' +
    '<text x="12" y="11" text-anchor="middle" font-size="6" font-weight="bold" fill="white" font-family="Arial">VM</text>',

  nas:
    '<rect x="6" y="3" width="12" height="12" rx="1" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<line x1="6" y1="9" x2="18" y2="9" stroke="white" stroke-width="1"/>' +
    '<circle cx="9" cy="6" r="0.5" fill="white"/>' +
    '<rect x="11" y="5.5" width="5" height="1" fill="white"/>' +
    '<circle cx="9" cy="12" r="0.5" fill="white"/>' +
    '<rect x="11" y="11.5" width="5" height="1" fill="white"/>',

  ipbx:
    '<path d="M 5 5 L 9 5 L 10 8 L 8 9 Q 10 12 13 14 L 14 12 L 17 13 L 17 17"' +
      ' stroke="white" stroke-width="1.4" fill="none" stroke-linejoin="round"/>',

  imprimante:
    '<rect x="4" y="7" width="16" height="6" rx="1" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<rect x="7" y="3" width="10" height="4" stroke="white" stroke-width="1.2" fill="none"/>' +
    '<rect x="7" y="11" width="10" height="3" stroke="white" stroke-width="1.2" fill="none"/>' +
    '<circle cx="17" cy="10" r="0.6" fill="white"/>',

  // === Postes : 2 variantes (Mac vs PC) ===
  poste_mac:
    '<rect x="3" y="3" width="18" height="9" rx="1.5" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<line x1="10" y1="12" x2="14" y2="12" stroke="white" stroke-width="1.4"/>' +
    '<line x1="9" y1="14" x2="15" y2="14" stroke="white" stroke-width="1.4"/>' +
    '<circle cx="12" cy="7" r="1.8" stroke="white" stroke-width="1" fill="none"/>',

  poste_pc:
    '<rect x="3" y="3" width="18" height="9" rx="1" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<line x1="3" y1="10" x2="21" y2="10" stroke="white" stroke-width="1"/>' +
    '<rect x="10" y="12" width="4" height="2" fill="white"/>' +
    '<line x1="8" y1="14" x2="16" y2="14" stroke="white" stroke-width="1.4"/>',

  onduleur:
    '<rect x="4" y="4" width="14" height="10" rx="0.5" stroke="white" stroke-width="1.4" fill="none"/>' +
    '<rect x="18" y="7" width="2" height="4" fill="white"/>' +
    '<path d="M 11 5 L 9 9 L 11 9 L 9 13 L 14 8 L 12 8 L 14 5 Z"' +
      ' fill="white" stroke="none"/>',
};

// Choisit la bonne clé d'icône pour un équipement.
// Cas spécial : type=poste → on regarde l'OS pour distinguer Mac vs PC.
function pickIconKey(e) {
  if (e.type === "poste") {
    const os = (e.os || "").toLowerCase();
    const marque = (e.marque || "").toLowerCase();
    if (os.includes("macos") || os.includes("mac os") || marque === "apple") {
      return "poste_mac";
    }
    return "poste_pc";
  }
  return e.type in SCHEMA_ICONS ? e.type : null;
}

window.SchemaApp = (function () {
  let equipements = [];
  let liaisons = [];
  let sites = [];
  let vue = "logique";
  const svg = document.getElementById("schema_svg");
  if (!svg) return null;

  // -------------------- Chargement --------------------
  async function load() {
    const [eqs, ls, auditData] = await Promise.all([
      fetch(`/api/audit/${window.AUDIT_ID}/equipements`).then(r => r.json()),
      fetch(`/api/audit/${window.AUDIT_ID}/liaisons`).then(r => r.json()),
      fetch(`/api/audit/${window.AUDIT_ID}`).then(r => r.json()),
    ]);
    equipements = eqs;
    liaisons = ls;
    sites = auditData.sites || [];
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

    // Groupes de sites (rectangles englobants) — dessinés EN PREMIER pour être en arrière-plan
    drawSiteGroups();

    // Liaisons d'abord (en dessous des équipements)
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

    // ===== Rendu spécial CLOUD pour les équipements de type "internet" =====
    if (e.type === "internet") {
      return drawCloudNode(e, vis);
    }

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

    // --- Icône SVG dans le bandeau (à gauche) ---
    // Si un pictogramme existe pour ce type, on l'affiche dans un sous-groupe
    // positionné en haut-gauche du bandeau. Sinon, le texte reste centré
    // comme avant (compatibilité totale).
    const iconKey = pickIconKey(e);
    const iconMarkup = iconKey ? SCHEMA_ICONS[iconKey] : null;
    if (iconMarkup) {
      // Icône dessinée sur 24x16, posée à (4, 3) dans la boîte (bandeau y=0..22)
      const iconG = el("g", { transform: "translate(4, 3)" });
      iconG.innerHTML = iconMarkup;
      g.appendChild(iconG);
      // Texte décalé à droite pour laisser place à l'icône (centré sur x≈74)
      g.appendChild(text(74, 16, (vis.label || "").toUpperCase(), {
        "text-anchor": "middle", "font-size": "10",
        "font-weight": "bold", fill: "white",
      }));
    } else {
      // Pas d'icône (cas "autre" ou type inconnu) : texte centré classique
      g.appendChild(text(60, 16, (vis.label || "").toUpperCase(), {
        "text-anchor": "middle", "font-size": "10",
        "font-weight": "bold", fill: "white",
      }));
    }
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

  // ===== Rendu spécial CLOUD (forme de nuage) pour Internet / FAI =====
  // Largeur 180 × hauteur 100 (un peu plus grand que les autres boîtes).
  // Le nom de l'équipement (ex: "FAI ZEOP") est affiché en GROS au centre,
  // et "INTERNET" apparaît en petit en haut comme étiquette de type.
  function drawCloudNode(e, vis) {
    const W = 180, H = 100;
    const g = el("g", {
      class: "schema-node schema-cloud",
      transform: `translate(${e.pos_x || 0},${e.pos_y || 0})`,
      "data-eq-id": e.id,
    });

    // Forme nuage : composition de cercles + rectangle arrondi en base
    // Couleur bleu clair pâle pour évoquer le ciel/internet
    const FILL_LIGHT = "#e3f2fd";   // bleu très clair (fond)
    const STROKE = "#1976d2";       // bleu moyen (contour)
    const TEXT_DARK = "#0d47a1";    // bleu foncé (texte)

    // Chemin SVG d'un nuage stylisé. Composition de courbes de Bézier
    // formant le contour classique d'un cumulus.
    const cloudPath = `
      M 30 70
      C 10 70, 5 50, 25 45
      C 20 25, 50 15, 65 30
      C 75 15, 110 15, 120 35
      C 145 25, 170 45, 155 65
      C 175 75, 165 95, 140 90
      C 130 100, 50 100, 35 90
      C 15 92, 10 78, 30 70
      Z
    `;
    g.appendChild(el("path", {
      d: cloudPath,
      fill: FILL_LIGHT,
      stroke: STROKE,
      "stroke-width": 2,
    }));

    // Étiquette "INTERNET" en petit en haut
    g.appendChild(text(90, 35, "INTERNET", {
      "text-anchor": "middle", "font-size": "9",
      "font-weight": "bold", fill: STROKE,
      "letter-spacing": "1.5",
    }));

    // Nom du FAI en GROS au centre (ce que voit le client en premier)
    const nomAffiche = e.nom_hote || vis.label || "FAI";
    g.appendChild(text(90, 60, truncate(nomAffiche, 16), {
      "text-anchor": "middle", "font-size": "15",
      "font-weight": "bold", fill: TEXT_DARK,
    }));

    // Sous-titre : IP publique si dispo, sinon vide
    if (e.ip) {
      g.appendChild(text(90, 78, truncate(e.ip, 18), {
        "text-anchor": "middle", "font-size": "9", fill: "#546e7a",
      }));
    }

    // Interactions (drag & double-clic comme les autres)
    makeDraggable(g, e);
    g.addEventListener("dblclick", () => {
      if (window.AppLogic) window.AppLogic.openEqModal(e.id);
    });
    svg.appendChild(g);
  }

  // Calcule le point central d'un équipement (où les liaisons s'attachent).
  // La taille dépend du type : le cloud Internet est 180x100, les autres 120x80.
  function centerOf(e) {
    const isCloud = e.type === "internet";
    const w = isCloud ? 180 : 120;
    const h = isCloud ? 100 : 80;
    return { x: (e.pos_x || 0) + w / 2, y: (e.pos_y || 0) + h / 2 };
  }

  // Dessine un rectangle englobant pour chaque site (regroupement visuel).
  // Pour chaque site_id distinct présent sur les équipements, on calcule la
  // bounding box des positions et on dessine un rectangle pointillé gris
  // clair, posé EN ARRIÈRE-PLAN avant les équipements eux-mêmes.
  function drawSiteGroups() {
    // Indexer les équipements par site_id (ignorer ceux sans site)
    const groups = {};
    equipements.forEach(e => {
      if (!e.site_id) return;
      if (!groups[e.site_id]) groups[e.site_id] = [];
      groups[e.site_id].push(e);
    });

    // Pour chaque groupe, calculer la bounding box + padding et dessiner
    Object.entries(groups).forEach(([siteId, eqs]) => {
      if (eqs.length < 1) return;
      // Bounding box : prendre min/max des positions + tailles des boîtes
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      eqs.forEach(e => {
        const isCloud = e.type === "internet";
        const w = isCloud ? 180 : 120;
        const h = isCloud ? 100 : 80;
        const x = e.pos_x || 0, y = e.pos_y || 0;
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (x + w > maxX) maxX = x + w;
        if (y + h > maxY) maxY = y + h;
      });
      // Padding interne pour l'aspect aéré
      const PAD = 28, PAD_TOP = 36;  // un peu plus haut pour l'étiquette
      const rx = minX - PAD;
      const ry = minY - PAD_TOP;
      const rw = (maxX - minX) + PAD * 2;
      const rh = (maxY - minY) + PAD_TOP + PAD;

      // Récupérer le nom du site (depuis la liste sites chargée par load())
      const site = sites.find(s => s.id == siteId);
      const siteName = site ? (site.nom || `Site #${siteId}`) : `Site #${siteId}`;

      // Rectangle pointillé gris clair avec léger fill semi-transparent
      svg.appendChild(el("rect", {
        x: rx, y: ry, width: rw, height: rh, rx: 8,
        fill: "#f8f9fa", "fill-opacity": "0.4",
        stroke: "#adb5bd", "stroke-width": 1.5,
        "stroke-dasharray": "6,4",
        "data-site-group": siteId,
      }));

      // Étiquette du site en haut à gauche, avec un fond blanc opaque pour
      // bien se détacher du rectangle pointillé.
      const labelW = Math.max(80, siteName.length * 7 + 16);
      svg.appendChild(el("rect", {
        x: rx + 10, y: ry - 10, width: labelW, height: 20, rx: 4,
        fill: "white",
        stroke: "#adb5bd", "stroke-width": 1,
      }));
      svg.appendChild(text(rx + 10 + labelW / 2, ry + 4, siteName, {
        "text-anchor": "middle", "font-size": "12",
        "font-weight": "bold", fill: "#495057",
      }));
    });
  }

  // Vue logique : lien pointillé gris "hébergé par" (VM -> hyperviseur)
  function drawHostLink(vm, host) {
    const a = centerOf(vm), b = centerOf(host);
    const x1 = a.x, y1 = a.y, x2 = b.x, y2 = b.y;
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

  // Cherche le label WAN à afficher sur un lien.
  // Si l'un des 2 équipements est de type "internet", on cherche le
  // site_id de l'AUTRE équipement (la box, la passerelle...) et on lit
  // son type_connexion. Affiche "WAN" par défaut si rien n'est renseigné.
  // Retourne {label, isWan} où isWan vrai = lien sortant vers Internet.
  function getWanLabel(s, d) {
    const sIsNet = s.type === "internet";
    const dIsNet = d.type === "internet";
    if (!sIsNet && !dIsNet) return { label: null, isWan: false };
    // L'équipement local = celui qui n'est pas Internet
    const local = sIsNet ? d : s;
    // Cherche le site associé à l'équipement local
    const site = sites.find(st => st.id === local.site_id);
    // Type de connexion (fibre, ADSL...) — peut être vide
    const typeConnex = site && site.type_connexion ? site.type_connexion.trim() : "";
    // Capitalisation propre : "fibre" -> "Fibre", "4G/5G" -> "4G/5G"
    let label = typeConnex
      ? typeConnex.charAt(0).toUpperCase() + typeConnex.slice(1)
      : "WAN";
    return { label, isWan: true };
  }

  function drawLiaison(l, eqById) {
    const s = eqById[l.source_id];
    const d = eqById[l.dest_id];
    if (!s || !d) return;
    const a = centerOf(s), b = centerOf(d);
    const x1 = a.x, y1 = a.y, x2 = b.x, y2 = b.y;
    let stroke = "#0d6efd", dash = "", strokeWidth = 2;
    if (l.type === "wifi") { stroke = "#20c997"; dash = "6,4"; }
    else if (l.type === "fibre") { stroke = "#ffc107"; }
    else if (l.type === "vpn" || l.type === "sdwan") {
      stroke = "#6610f2"; dash = "4,3";
    } else if (l.type === "sip-trunk") { stroke = "#d63384"; }

    // --- Cas spécial WAN (lien vers Internet) ---
    const wan = getWanLabel(s, d);
    if (wan.isWan) {
      // Lien WAN : un peu plus épais et couleur orange (continuité visuelle
      // avec le rendu existant pour ces liens externes).
      stroke = "#fd9826";
      strokeWidth = 3;
      dash = "";
    }

    svg.appendChild(el("line", {
      x1, y1, x2, y2,
      stroke, "stroke-width": strokeWidth,
      "stroke-dasharray": dash,
      "data-liaison-id": l.id,
    }));

    // --- Label WAN prioritaire (type connexion site) ---
    if (wan.isWan && wan.label) {
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      // Largeur du fond adaptée au label (8 px par char + marge)
      const w = Math.max(56, wan.label.length * 7 + 16);
      svg.appendChild(el("rect", {
        x: mx - w / 2, y: my - 9, width: w, height: 16, rx: 4,
        fill: "white", stroke, "stroke-width": 1, opacity: 0.95,
      }));
      svg.appendChild(text(mx, my + 1, wan.label, {
        "text-anchor": "middle", "font-size": "11",
        "font-weight": "bold", fill: stroke,
      }));
    } else if (l.vlan || l.debit) {
      // Label classique (vlan / débit) pour les autres liens
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

// =====================================================================
// Export PDF avec page schéma
//
// Cette fonction est appelée depuis le bouton "📄 PDF" de audit.html.
// Elle :
//   1. Récupère le SVG du schéma topologique depuis le DOM (#schema_svg)
//   2. Le sérialise en string
//   3. Envoie un POST à /audit/<id>/export/pdf avec le SVG dans le body
//   4. Reçoit le PDF binaire en réponse et déclenche le téléchargement
//
// Si le SVG n'est pas trouvé (utilisateur pas sur l'onglet schéma), on tombe
// en fallback GET (PDF sans page schéma).
// =====================================================================
window.exportPdfWithSchema = async function (auditId) {
  const svgEl = document.getElementById("schema_svg");
  let schemaSvg = null;
  if (svgEl) {
    try {
      // CRITIQUE : Avant de sérialiser, on recalcule la viewBox pour
      // qu'elle englobe TOUS les éléments visibles. Le SVG du DOM a une
      // viewBox fixe (0 0 1200 800) mais des éléments peuvent être en
      // dehors (cloud Internet placé en y négatif, équipements au-delà
      // de la limite droite...). Le navigateur les affiche quand même
      // car overflow:visible, mais cairosvg respecte strictement la
      // viewBox et coupe ce qui dépasse.
      //
      // On appelle getBBox() sur le SVG ORIGINAL (qui est rendu à l'écran).
      // Important : getBBox sur un clone hors écran ou en visibility:hidden
      // renvoie 0,0,0,0 dans la plupart des navigateurs. Il faut un élément
      // réellement rendu pour mesurer.
      let computedViewBox = null;
      try {
        const bbox = svgEl.getBBox();
        if (bbox && bbox.width > 0 && bbox.height > 0) {
          const pad = 30;
          computedViewBox = {
            x: bbox.x - pad,
            y: bbox.y - pad,
            w: bbox.width + pad * 2,
            h: bbox.height + pad * 2,
          };
        } else {
          console.warn("getBBox a renvoyé une zone vide :",
                       bbox && bbox.width, bbox && bbox.height);
        }
      } catch (e) {
        console.warn("getBBox a échoué :", e.message);
      }

      // On clone le SVG pour ne pas perturber l'affichage à l'écran,
      // et on applique la viewBox calculée au clone.
      const clone = svgEl.cloneNode(true);
      // Retirer les attributs de style hors écran s'il y en avait
      clone.removeAttribute("style");
      if (computedViewBox) {
        clone.setAttribute("viewBox",
          `${computedViewBox.x} ${computedViewBox.y} ${computedViewBox.w} ${computedViewBox.h}`);
        clone.setAttribute("width", computedViewBox.w);
        clone.setAttribute("height", computedViewBox.h);
      }
      // Sérialise le clone avec sa viewBox corrigée
      const serializer = new XMLSerializer();
      schemaSvg = serializer.serializeToString(clone);
      // S'assurer que xmlns est présent (sinon cairosvg refuse)
      if (!schemaSvg.includes("xmlns=")) {
        schemaSvg = schemaSvg.replace(
          /<svg\b/,
          '<svg xmlns="http://www.w3.org/2000/svg"'
        );
      }
    } catch (e) {
      console.warn("Sérialisation SVG échouée :", e);
      schemaSvg = null;
    }
  }

  // Si pas de SVG ou SVG vide, fallback GET (ancien comportement)
  if (!schemaSvg || schemaSvg.length < 100) {
    window.location.href = `/audit/${auditId}/export/pdf`;
    return;
  }

  // POST avec le SVG, récupère le PDF binaire, déclenche le téléchargement
  try {
    const r = await fetch(`/audit/${auditId}/export/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schema_svg: schemaSvg }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const blob = await r.blob();
    // Extrait le nom de fichier depuis Content-Disposition si présent
    const cd = r.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="?([^";]+)"?/);
    const filename = m ? m[1] : `audit_${auditId}.pdf`;
    // Crée un lien temporaire pour télécharger
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("Échec export PDF :", err);
    alert("Échec de l'export PDF : " + err.message
      + "\n\nFallback : téléchargement sans schéma.");
    window.location.href = `/audit/${auditId}/export/pdf`;
  }
};