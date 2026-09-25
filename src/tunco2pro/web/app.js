// TunCO2 Pro front end: guided workflow, linked map, table, chart and 3D model, scenarios.
// Plain ES module; ECharts for charts, Leaflet for the plan, three.js (viewer.js) for 3D.
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = (x, d = 0) => (x == null || !isFinite(x)) ? "–" : Number(x).toLocaleString("en-AU", { maximumFractionDigits: d, minimumFractionDigits: d });
const clone = (o) => JSON.parse(JSON.stringify(o));
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ARTIC = "Road, articulated average (average laden)";
const store = {
  get(k, d = null) { try { const v = localStorage.getItem("tunco2pro." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("tunco2pro." + k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

let project = null, defaults = null, factors = null, help = {}, tbmCat = null;
let lastResult = null, lastRoute = null, lastCompare = null, lastStab = null, lastRouteOpt = null, lastPareto = [];
let selZone = null, step = "project";
const dirty = { model: true, tbm: true, map: true };
const charts = {};
const MODULE_COLOR = () => ({ "A1-A3": css("--series-1"), "A4": css("--series-2"), "A5": css("--series-3") });

// ================================================================ API + status
let pending = 0;
function setStatus(kind, text) { const s = $("#status"); s.className = "status " + kind; s.querySelector(".txt").textContent = text; }
async function api(url, body, { method = "POST", raw = false } = {}) {
  pending++; setStatus("busy", "Calculating…");
  try {
    const r = await fetch(url, method === "GET" ? {} : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
    if (!r.ok) {
      let msg = `${r.status}`; try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : j.detail.map(e => `${e.loc.slice(-2).join(".")}: ${e.msg}`).join("; "); } catch { }
      throw new Error(msg);
    }
    return raw ? r : r.json();
  } catch (e) { toast(`Could not complete the request: ${e.message}`, "err"); setStatus("err", "Error, see message"); throw e; }
  finally { if (--pending === 0 && !$("#status").classList.contains("err")) setStatus("ok", "Up to date"); }
}
const req = () => ({ project, compat_v1: $("#compat").checked });

function toast(msg, kind = "", action) {
  const t = document.createElement("div"); t.className = "toast " + kind;
  t.innerHTML = `<div style="flex:1">${msg}</div>`;
  if (action) { const b = document.createElement("button"); b.textContent = action.label; b.onclick = () => { action.run(); t.remove(); }; t.appendChild(b); }
  const x = document.createElement("button"); x.textContent = "×"; x.setAttribute("aria-label", "Dismiss"); x.onclick = () => t.remove(); t.appendChild(x);
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), kind === "err" ? 12000 : 7000);
}

// ================================================================ steps
const STEPS = [
  ["project", "Project", "Basis and cross-section"], ["route", "Route & ground", "Alignment and zones"],
  ["tbm", "TBM selection", "Machine for the ground"], ["lining", "Lining & materials", "A1–A4 inputs"],
  ["design", "Stability & design", "CCM and optimisation"], ["results", "Carbon results", "A1–A5 breakdown"],
  ["scenarios", "Scenarios", "Compare alternatives"], ["export", "Model & export", "BIM, GIS, reports"]];
function buildSteps() {
  $("#steps").innerHTML = STEPS.map(([k, t, s], i) =>
    `<button data-step="${k}"><span class="n">${i + 1}</span><span class="t">${t}</span><span class="flag" id="flag-${k}"></span><span class="s">${s}</span></button>`).join("");
  $$("#steps button").forEach(b => b.onclick = () => go(b.dataset.step));
}
function go(k) {
  step = k; store.set("step", k);
  $$("#steps button").forEach(b => b.classList.toggle("on", b.dataset.step === k));
  $$(".page").forEach(p => p.classList.toggle("on", p.dataset.step === k));
  const i = STEPS.findIndex(s => s[0] === k);
  $("#btnPrev").style.visibility = i ? "visible" : "hidden";
  $("#btnNext").style.visibility = i < STEPS.length - 1 ? "visible" : "hidden";
  if (i < STEPS.length - 1) $("#btnNext").textContent = `Next: ${STEPS[i + 1][1]} →`;
  window.scrollTo({ top: 0 });
  requestAnimationFrame(() => Object.values(charts).forEach(c => c.resize()));
  if (k === "route") { window.dispatchEvent(new CustomEvent("tunco2:viewer-slot", { detail: { el: $('[data-slot="route"]') } })); drawMap().then(() => { if (map) setTimeout(() => { map.invalidateSize(); const b = mapLayers.length && L.featureGroup(mapLayers).getBounds(); if (b) map.fitBounds(b, { padding: [20, 20] }); }, 60); }); showModel(); }
  if (k === "export") { buildExports(); buildFigures(); window.dispatchEvent(new CustomEvent("tunco2:viewer-slot", { detail: { el: $('[data-slot="export"]') } })); showModel(); }
  if (k === "tbm") tbmPage();
  if (k === "scenarios") scenPage();
}
function flag(k, kind, title) { const f = $("#flag-" + k); if (!f) return; f.className = "flag " + (kind || ""); f.textContent = { ok: "✓", warn: "!", bad: "✗" }[kind] || ""; f.title = title || ""; }
function updateFlags() {
  flag("project", lastResult ? "ok" : "", "");
  if (lastRoute) {
    const fail = lastRoute.zones.filter(z => !z.uls_ok || !z.sls_ok).length;
    const placeholder = project.route?.source ? " Ground parameters are indicative placeholders." : "";
    flag("route", fail ? "bad" : placeholder ? "warn" : "ok", fail ? `${fail} zone(s) fail ULS/SLS.` : placeholder);
  } else flag("route", "", "No route defined");
  const mt = project.tbm.machine_type, w = lastRoute?.tbm_applicability?.worst?.[mt];
  flag("tbm", !mt ? "" : w === "suitable" || !w ? "ok" : w === "marginal" ? "warn" : "bad", mt ? `Worst rating along the route: ${w ?? "n/a"}` : "No machine type chosen");
  flag("lining", lastResult ? "ok" : "");
  flag("design", lastStab ? (lastStab.result.fos >= project.criteria.fos_min ? "ok" : "bad") : "", lastStab ? `FoS ${fmt(lastStab.result.fos, 2)}` : "");
  flag("results", lastResult ? (lastResult.warnings.length ? "warn" : "ok") : "", lastResult ? `${lastResult.warnings.length} warning(s)` : "");
  const n = scenarios().length; const f = $("#flag-scenarios"); if (f) { f.className = "flag"; f.textContent = n ? String(n) : ""; }
}

// ================================================================ forms
const HELP = {
  "stage": "Reporting stage (NSW Embodied Carbon Guide): business case, design or construction.",
  "tunnel_length_m": "Length used for totals when no route is defined. Set automatically from an imported corridor.",
  "lod": "Level of detail of the 3D/IFC model (Parts 1 and 3): 100 envelope … 500 as-built.",
  "functional.kind": "Normalises results per track-km (rail) or lane-km (road) as in Part 1.",
  "face.earth_coefficient": "K0 where surface settlement is to be minimised; Ka (or none) where heave is observed ahead of the machine (JSCE 2016).",
  "face.delta_p_kpa": "Allowance for operational fluctuation added to the control pressure.",
  "tbm.loads.thrust_model": "xie2024 = BIM-to-Thrust relation (soil + water + shield friction; Xie et al. 2024), validated against EPB and Mixshield records; regression_pressure = Part 3 type regression corrected for each zone's support pressure; empirical_type = Part 3 regression; analytical = v1 relations (sandy branch lies above recorded thrust, Xie et al. 2024); empirical = Krause.",
  "criteria.fos_min": "Ultimate limit state: minimum factor of safety of the lining from the convergence–confinement check.",
  "criteria.u_max_mm": "Serviceability limit: maximum radial convergence at equilibrium. Blank = not checked.",
  "settlement.volume_loss_pct": "Volume loss as % of the excavated area, for every zone. Blank = estimated per zone from the ground (fines), the machine and the face-pressure mode: 0.5 % sand, 0.75 % silt, 1 % clay for a closed face at K0 (Mair and Taylor 1997; Mair 2008), ×1.5 below K0, ×2 without face support, 0.1 % in rock. A zone value (route table, V_L %) overrides.",
  "settlement.trough_k": "Trough-width parameter, i = K z₀. Blank = 0.5 clay, 0.4 silt, 0.3 sand, 0.25 rock (O'Reilly and New 1982). A zone value (route table, K) overrides.",
  "settlement.s_max_mm": "Zones whose Gaussian-trough maximum settlement exceeds this are flagged for a settlement assessment (numerical model, Section 7.6.3 of the chapter).",
  "settlement.slope_max": "Maximum slope of the trough, at the point of inflection y = i (0.607 S_max / i). 1/500 is the boundary of Rankin's (1988) negligible category.",
  "geometry.tbm_diameter_m": "Excavated (cutting) diameter of the TBM.",
  "concrete.ecf_mode": "nefd = NABERS national factors by strength band (tier 3); user_points = your EPD values; database = v1 regression; fixed = one value.",
  "concrete.strength_mpa": "Design compressive strength f'c of the segments.",
  "steel.reinforcement_ratio_pct": "Reinforcement as % of lining concrete volume (by volume, v1 convention).",
  "tbm.grid_factor_key": "Electricity emission factor for TBM and plant (NGA Factors 2026, scope 2 + 3, location-based).",
  "tbm.loads.energy_method": "forces = work of thrust and torque (v1); specific_energy = SE × excavated volume (Part 3 method i); components = cutterhead mechanics: torque from cutting, face and rim friction in the support medium (or disc forces in rock), energy = thrust work + 2πT / penetration, with a P10–P90 band (docs/CUTTERHEAD.md).",
  "tbm.loads.cutterhead_rock_quality": "Rock at the face for the disc model (single section; zones take it from the ground model).",
  "tbm.spoil_distance_km": "One-way haul distance to the spoil destination.",
  "tbm.slurry.mode": "estimate = first-principles energy balance (pumping + separation); user = your measured or supplier value; off = excluded.",
  "tbm.amortisation_length_m": "Drive length over which the TBM's manufacture carbon is allocated; also the drive length for the slurry pipeline estimate.",
  "tbm.user_mass_t": "Manufacturer's machine mass. Recommended for hard-rock TBMs (no Part 3 mass regression).",
};
const TYPE_OPTS = ["Open TBM", "EPB TBM", "Slurry TBM", "Single Shield TBM", "Double Shield TBM", "Multi-mode TBM"];
// [path, label, kind, {adv, show}]
const FORMS = {
  project: [
    { title: "Project", fields: [
      ["stage", "Reporting stage", ["business_case", "design", "construction"]], ["factor_set", "Emission factor set", "factorset"],
      ["tunnel_length_m", "Tunnel length (m)"], ["lod", "Model level of detail (LoD)", "lod"],
      ["functional.kind", "Functional unit", ["rail", "road", "other"]], ["functional.count", "Tracks / lanes in this bore"]] },
    { title: "Cross-section", fields: [
      ["geometry.inner_diameter_m", "Lining inner diameter (m)"], ["geometry.lining_thickness_m", "Lining thickness (m)"],
      ["geometry.tbm_diameter_m", "TBM / excavated diameter (m)"], ["geometry.ring_width_m", "Ring width (m)"],
      ["geometry.segments_per_ring", "Segments per ring (incl. key)", null, { adv: 1 }], ["geometry.key_angle_deg", "Key segment angle (°)", null, { adv: 1 }]] },
    { title: "Design criteria", fields: [
      ["criteria.fos_min", "ULS: minimum factor of safety"], ["criteria.u_max_mm", "SLS: max. convergence (mm)", "numnull"],
      ["criteria.ec_from_strength", "Ec from f'c (v1 correlation)", "bool", { adv: 1 }]] },
    { title: "Settlement screening (volume loss)", fields: [
      ["settlement.volume_loss_pct", "Volume loss V_L (%)", "numnull"], ["settlement.trough_k", "Trough width K (i = K z₀)", "numnull"],
      ["settlement.s_max_mm", "SLS: max. settlement (mm)"], ["settlement.slope_max", "SLS: max. trough slope", null, { adv: 1 }]] },
  ],
  tbm: [
    { title: "Excavation energy", fields: [
      ["tbm.grid_factor_key", "Electricity grid", "grid"], ["tbm.loads.energy_method", "Energy method", ["forces", "specific_energy", "components"]],
      ["tbm.loads.cutterhead_rock_quality", "Rock at face (disc model)", ["competent", "fractured", "weak"], { show: p => p.tbm.loads.energy_method === "components" && ["gripper", "single_shield", "double_shield"].includes(p.tbm.machine_type) }],
      ["tbm.loads.specific_energy_kwh_m3", "Specific energy (kWh/m³)", null, { show: p => p.tbm.loads.energy_method === "specific_energy" }],
      ["tbm.loads.rpm", "Cutterhead speed (rev/min)", null, { adv: 1, show: p => p.tbm.loads.energy_method === "forces" }],
      ["tbm.loads.advance_mm_min", "Advance rate (mm/min)", null, { adv: 1 }]] },
    { title: "Face support pressure (JSCE)", show: p => ["epb", "slurry", "multi_mode"].includes(p.tbm.machine_type), fields: [
      ["face.earth_coefficient", "Earth-pressure coefficient K_e", ["K0", "Ka", "none"]],
      ["face.delta_p_kpa", "Fluctuation allowance Δp (kPa)"],
      ["face.epb_friction", "Torque–pressure friction, EPB spoil", null, { adv: 1, show: p => p.tbm.machine_type !== "slurry" && p.tbm.loads.energy_method === "forces" }],
      ["face.slurry_friction", "Torque–pressure friction, slurry", null, { adv: 1, show: p => p.tbm.machine_type !== "epb" && p.tbm.loads.energy_method === "forces" }],
      ["face.use_in_loads", "Drive thrust/torque by each zone's pressure", "bool"]],
      note: "p_control = K_e σ′_v + u_w + Δp (JSCE 2016), K₀ = 1 − sin φ′ (Jaky); upper bound = total vertical stress at the crown. With the regression_pressure models, thrust changes by the face area × (p − p_ref) and torque by the medium friction × (p − p_ref), p_ref = control pressure at z₀ = 2D. Friction values are defaults to be calibrated." },
    { title: "Slurry circuit (pumping and separation)", show: p => ["slurry", "multi_mode"].includes(p.tbm.machine_type), fields: [
      ["tbm.slurry.mode", "Energy basis", ["estimate", "user", "off"]],
      ["tbm.slurry.user_kwh_per_m3", "Measured / supplier value (kWh per m³ excavated)", null, { show: p => p.tbm.slurry.mode === "user" }],
      ["tbm.slurry.multi_mode_slurry_share", "Share of drive in slurry mode", null, { show: p => p.tbm.machine_type === "multi_mode" }],
      ["tbm.slurry.rho_feed_t_m3", "Feed slurry density ρ_f (t/m³)", null, { show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.rho_discharge_t_m3", "Discharge slurry density ρ_d (t/m³)", null, { show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.pipe_diameter_m", "Slurry pipe diameter (m)", null, { show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.shaft_lift_m", "Lift, tunnel to plant (m)", null, { show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.surface_pipe_m", "Surface pipeline (m)", null, { show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.plant_extra_kwh_per_m3_slurry", "Screens, agitators, fines (kWh/m³ slurry)", null, { show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.rho_solids_t_m3", "Particle density (t/m³)", null, { adv: 1, show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.porosity", "In-situ porosity", null, { adv: 1, show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.friction_factor", "Pipe friction factor (Darcy)", null, { adv: 1, show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.pump_efficiency", "Pump efficiency", null, { adv: 1, show: p => p.tbm.slurry.mode === "estimate" }],
      ["tbm.slurry.cyclone_dp_mpa", "Hydrocyclone pressure drop (MPa)", null, { adv: 1, show: p => p.tbm.slurry.mode === "estimate" }]],
      note: "Estimate = energy balance on the slurry circuit: slurry volume from feed/return densities and porosity; Darcy–Weisbach friction over half the drive (allocation length) plus the surface run; shaft lift; hydrocyclone pressure drop. Replace with a supplier or measured value when available." },
    { title: "Machine and spoil", fields: [
      ["tbm.mass_model", "Machine mass", ["EPB", "Slurry", "Multi", "user"]],
      ["tbm.user_mass_t", "Manufacturer mass (t)", null, { show: p => p.tbm.mass_model === "user" }],
      ["tbm.ecf_kg_per_kg", "Machine ECF (kgCO₂e/kg)"], ["tbm.amortisation_length_m", "Allocation length (m)"],
      ["tbm.spoil_distance_km", "Spoil haul (km)"], ["tbm.spoil_mode", "Spoil haul mode", "transport"],
      ["tbm.spoil_density_t_m3", "Spoil density (t/m³)", "numnull", { adv: 1 }]] },
    { title: "Site plant", fields: [
      ["tbm.aux_power_kw", "Auxiliary plant power (kW)"], ["tbm.aux_hours_per_m", "Auxiliary hours per metre"],
      ["tbm.site_diesel_l_per_m", "Site plant diesel (L/m)"], ["tbm.user_defined_a5_kg_per_m", "Other site A5 (kgCO₂e/m)"]] },
    { title: "TBM delivery (A4/A5)", adv: 1, fields: [["transport.tbm", "Delivery legs", "legs"]] },
    { title: "Thrust and torque models", adv: 1, fields: [
      ["tbm.loads.thrust_model", "Thrust model", ["xie2024", "regression_pressure", "empirical_type", "analytical", "empirical", "user"]],
      ["tbm.loads.thrust_bound", "xie2024 bound", ["mean", "upper", "lower"], { show: p => p.tbm.loads.thrust_model === "xie2024" }],
      ["tbm.loads.torque_model", "Torque model", ["regression_pressure", "empirical_type", "analytical", "empirical", "user"]],
      ["tbm.loads.tbm_type_thrust", "Thrust regression type", TYPE_OPTS], ["tbm.loads.tbm_type_torque", "Torque regression type", TYPE_OPTS],
      ["tbm.loads.soil_type", "Ground (analytical thrust)", ["Sandy Soil", "Clay"]]], auto: "tbm.loads" },
  ],
  lining: [
    { title: "Segment concrete (A1–A3)", fields: [
      ["concrete.ecf_mode", "Emission factor source", ["nefd", "user_points", "database", "fixed"]],
      ["concrete.nefd_basis", "NABERS NEFD value", ["default", "average"], { show: p => p.concrete.ecf_mode === "nefd" }],
      ["concrete.strength_mpa", "Design strength f'c (MPa)"],
      ["concrete.fixed_ecf", "Fixed ECF (kgCO₂e/m³)", null, { show: p => p.concrete.ecf_mode === "fixed" }],
      ["concrete.user_points", "EPD points f'c:ECF", "points", { show: p => p.concrete.ecf_mode === "user_points" }],
      ["concrete.db_locations", "Database locations", "multi-loc", { show: p => p.concrete.ecf_mode === "database" }],
      ["concrete.density_kg_m3", "Density (kg/m³)", null, { adv: 1 }]] },
    { title: "Reinforcement (A1–A3)", fields: [
      ["steel.factor_name", "Steel factor", "steel"], ["steel.user_ecf", "Steel ECF (kgCO₂e/kg)", null, { show: p => !p.steel.factor_name }],
      ["steel.reinforcement_ratio_pct", "Reinforcement (% of volume)"], ["steel.density_kg_m3", "Steel density (kg/m³)", null, { adv: 1 }]] },
    { title: "Other elements (A1–A3)", fields: [
      ["invert.include", "Invert backfill", "bool"], ["invert.by", "Backfill defined by", ["theta", "chord"], { show: p => p.invert.include }],
      ["invert.theta_deg", "Backfill angle θ (°)", null, { show: p => p.invert.include && p.invert.by === "theta" }],
      ["invert.chord_m", "Backfill chord (m)", null, { show: p => p.invert.include && p.invert.by === "chord" }],
      ["items.include_grout", "Annulus grout", "bool"], ["items.grout_ecf_kg_m3", "Grout ECF (kgCO₂e/m³)", null, { show: p => p.items.include_grout }],
      ["items.include_fitout", "Fit-out", "bool"], ["items.fitout_quantity_per_m", "Fit-out quantity per m", null, { show: p => p.items.include_fitout }],
      ["items.fitout_ecf", "Fit-out ECF", null, { show: p => p.items.include_fitout }],
      ["items.include_rail_road", "Rail / road / deck", "bool"], ["items.rail_road_quantity_per_m", "Rail/road quantity per m", null, { show: p => p.items.include_rail_road }],
      ["items.rail_road_ecf", "Rail/road ECF", null, { show: p => p.items.include_rail_road }]] },
    { title: "Delivery to site (A4)", fields: ["lining", "grout", "backfill", "fitout", "rail_road"].map(k => [`transport.${k}`, { lining: "Segments", grout: "Grout", backfill: "Backfill", fitout: "Fit-out", rail_road: "Rail / road" }[k], "legs"]) },
  ],
  ground: [
    { title: "Ground for the single-section check", fields: [
      ["ground.p0_mpa", "In-situ stress p₀ (MPa)"], ["ground.cohesion_mpa", "Cohesion c (MPa)"], ["ground.friction_deg", "Friction angle φ (°)"],
      ["ground.modulus_mpa", "Rock-mass modulus Eₘ (MPa)"], ["ground.poisson", "Poisson's ratio ν"]],
      note: "Route zones carry their own ground; this panel is for a single representative section.", button: ["Use the selected route zone", () => groundFromZone()] },
  ],
  levers: [{ title: "Lever settings", auto: "strategies", note: "Each lever is a replacement of the corresponding project input; the bars show the saving of each lever on its own.", fields: [
      ["strategies.scm_percent", "SCM substitution (% of binder)"], ["strategies.ecf_reduction_per_scm_percent", "Concrete factor reduction per % SCM (kgCO₂e/m³)"],
      ["strategies.reduced_strength_mode", "Lower-strength lever defined by", ["strength", "ecf"]],
      ["strategies.reduced_strength_mpa", "Reduced concrete strength (MPa)"], ["strategies.reduced_ecf", "Reduced concrete factor (kgCO₂e/m³)"],
      ["strategies.reduced_thickness_m", "Reduced lining thickness (m)"], ["strategies.reduced_reinforcement_pct", "Reduced reinforcement (% by volume)"],
      ["strategies.reduced_steel_ecf", "Low-carbon steel factor (kgCO₂e/kg)"], ["strategies.reduced_grid_factor", "Renewable electricity factor (kgCO₂e/kWh)"]] }],
};
const get = (o, path) => path.split(".").reduce((a, k) => a?.[k], o);
const set = (o, path, v) => { const ks = path.split("."); const last = ks.pop(); ks.reduce((a, k) => a[k], o)[last] = v; };
const conditions = [];

function field(path, label, kind, opt = {}) {
  const v = get(project, path);
  const wrap = document.createElement("div"); wrap.className = "f" + (opt.adv ? " adv" : ""); wrap.dataset.path = path;
  const h = help[path] || {}, txt = [HELP[path] || h.description, bounds(h)].filter(Boolean).join(" ");
  const lab = document.createElement("label"); lab.textContent = label;
  if (txt) { const q = document.createElement("span"); q.className = "help"; q.textContent = "?"; q.title = txt; lab.appendChild(q); lab.title = txt; }
  wrap.appendChild(lab);
  let el;
  const opts = (arr, cur) => arr.map(o => `<option ${o === cur ? "selected" : ""}>${o}</option>`).join("");
  const changed = () => onInput(path);
  if (Array.isArray(kind)) { el = document.createElement("select"); el.innerHTML = opts(kind, v); el.onchange = () => { set(project, path, el.value); changed(); }; }
  else if (kind === "bool") { el = document.createElement("input"); el.type = "checkbox"; el.checked = v; el.onchange = () => { set(project, path, el.checked); changed(); }; }
  else if (kind === "text") { el = document.createElement("input"); el.type = "text"; el.value = v ?? ""; el.oninput = () => { set(project, path, el.value); changed(); }; }
  else if (kind === "steel") { el = document.createElement("select"); const names = factors.factors.filter(f => f.category === "steel").map(f => f.name);
    el.innerHTML = opts(["(own EPD value)", ...names], v ?? "(own EPD value)"); el.onchange = () => { set(project, path, el.value === "(own EPD value)" ? null : el.value); changed(); }; }
  else if (kind === "transport") { el = document.createElement("select"); el.innerHTML = opts(factors.factors.filter(f => f.category === "transport").map(f => f.name), v);
    el.onchange = () => { set(project, path, el.value); changed(); }; }
  else if (kind === "lod") { el = document.createElement("select"); el.innerHTML = [100, 200, 300, 400, 500].map(o => `<option ${o === v ? "selected" : ""}>${o}</option>`).join("");
    el.onchange = () => { set(project, path, Number(el.value)); $("#lodSel").value = el.value; changed(); }; }
  else if (kind === "numnull") { el = document.createElement("input"); el.type = "number"; el.step = "any"; el.value = v ?? ""; el.placeholder = "none";
    el.oninput = () => { set(project, path, el.value === "" ? null : Number(el.value)); validate(el, h); changed(); }; }
  else if (kind === "factorset") { el = document.createElement("select");
    el.innerHTML = `<option value="current" ${v === "current" ? "selected" : ""}>Current (NGA 2026, NABERS NEFD v2026.2)</option><option value="v1" ${v === "v1" ? "selected" : ""}>TunCO2 v1 values</option>`;
    el.onchange = async () => { set(project, path, el.value); await loadFactors(); buildForms(); changed(); }; }
  else if (kind === "grid") { el = document.createElement("select"); el.innerHTML = factors.factors.filter(f => f.category === "grid")
      .map(f => `<option value="${f.key}" ${f.key === v ? "selected" : ""}>${f.name} (${f.value})</option>`).join(""); el.onchange = () => { set(project, path, el.value); changed(); }; }
  else if (kind === "multi-loc") { el = document.createElement("select"); el.multiple = true; el.size = 4;
    el.innerHTML = factors.concrete_locations.map(l => `<option ${v.includes(l) ? "selected" : ""}>${l}</option>`).join("");
    el.onchange = () => { set(project, path, [...el.selectedOptions].map(o => o.value)); changed(); }; }
  else if (kind === "points") { el = document.createElement("input"); el.type = "text"; el.value = v.map(p => p.join(":")).join(", "); el.placeholder = "32:320, 40:380";
    el.onchange = () => { set(project, path, el.value.split(",").map(s => s.split(":").map(Number)).filter(p => p.length === 2 && p.every(isFinite))); changed(); }; }
  else if (kind === "legs") return legsEditor(path, label, opt);
  else { el = document.createElement("input"); el.type = "number"; el.step = "any"; el.value = v;
    el.oninput = () => { if (el.value === "" || !validate(el, h)) return; set(project, path, Number(el.value)); changed(); }; validate(el, h); }
  el.id = "f-" + path.replaceAll(".", "-"); lab.htmlFor = el.id;
  wrap.appendChild(el);
  if (opt.show) conditions.push([wrap, opt.show]);
  return wrap;
}
function bounds(h) {
  const lo = h.min ?? h.min_excl, hi = h.max ?? h.max_excl;
  if (lo == null && hi == null) return "";
  return `Allowed: ${lo != null ? (h.min_excl != null ? "> " : "≥ ") + lo : ""}${lo != null && hi != null ? ", " : ""}${hi != null ? (h.max_excl != null ? "< " : "≤ ") + hi : ""}.`;
}
function validate(el, h) {
  const x = Number(el.value); let ok = el.value === "" || isFinite(x);
  if (ok && el.value !== "") {
    if (h.min != null && x < h.min) ok = false; if (h.min_excl != null && x <= h.min_excl) ok = false;
    if (h.max != null && x > h.max) ok = false; if (h.max_excl != null && x >= h.max_excl) ok = false;
  }
  el.classList.toggle("invalid", !ok); el.title = ok ? "" : bounds(h) || "Invalid value"; return ok;
}
function legsEditor(path, label, opt) {
  const modes = factors.factors.filter(f => f.category === "transport").map(f => f.name);
  const box = document.createElement("div"); box.className = opt.adv ? "adv" : "";
  const render = () => {
    const legs = get(project, path);
    box.innerHTML = `<div class="grp">${label}</div>`;
    const t = document.createElement("table"); t.className = "legs";
    legs.forEach((leg, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><select aria-label="${label} mode">${modes.map(m => `<option ${m === leg.mode ? "selected" : ""}>${m}</option>`).join("")}</select></td>
        <td><input type="number" step="any" min="0" value="${leg.distance_km}" aria-label="${label} distance"> km</td><td><button type="button" aria-label="Remove leg">×</button></td>`;
      tr.querySelector("select").onchange = (e) => { leg.mode = e.target.value; onInput(path); };
      tr.querySelector("input").oninput = (e) => { leg.distance_km = Number(e.target.value); onInput(path); };
      tr.querySelector("button").onclick = () => { legs.splice(i, 1); render(); onInput(path); };
      t.appendChild(tr);
    });
    box.appendChild(t);
    const add = document.createElement("button"); add.type = "button"; add.textContent = "+ leg";
    add.onclick = () => { legs.push({ mode: ARTIC, distance_km: 0 }); render(); onInput(path); };
    box.appendChild(add);
  };
  render(); return box;
}
function buildForms() {
  conditions.length = 0;
  $$("[data-form]").forEach(host => {
    host.innerHTML = "";
    (FORMS[host.dataset.form] || []).forEach(g => {
      const card = document.createElement("div"); card.className = "card" + (g.adv ? " adv" : "");
      if (g.show) conditions.push([card, g.show]);
      card.innerHTML = `<h3>${g.title}${g.adv ? ' <span class="badge">advanced</span>' : ""}</h3>`;
      g.fields.forEach(([p, l, k, o]) => card.appendChild(field(p, l, k, o)));
      if (g.auto) {
        const obj = get(project, g.auto);
        Object.keys(obj).filter(k => typeof obj[k] === "number").forEach(k => {
          const pth = `${g.auto}.${k}`;
          if (Object.values(FORMS).flat().some(gg => gg.fields.some(f => f[0] === pth))) return;
          card.appendChild(field(pth, k.replaceAll("_", " "), undefined, { adv: g.auto !== "strategies" }));
        });
      }
      if (g.note) card.insertAdjacentHTML("beforeend", `<p class="note">${g.note}</p>`);
      if (g.button) { const bt = document.createElement("button"); bt.type = "button"; bt.textContent = g.button[0]; bt.onclick = g.button[1]; card.appendChild(bt); }
      if (card.querySelector(".f.adv") && !g.adv) card.insertAdjacentHTML("beforeend", `<p class="advnote">More parameters under File ▸ Show advanced parameters.</p>`);
      host.appendChild(card);
    });
  });
  $("#projName").value = project.name;
  refreshVisibility();
}
function refreshVisibility() { conditions.forEach(([w, fn]) => { w.style.display = fn(project) ? "" : "none"; }); }

// ================================================================ recalculation
let timer = null;
function onInput(path) {
  refreshVisibility(); autosave();
  dirty.model = dirty.tbm = true; if (path && path.startsWith("route")) dirty.map = true;
  setStatus("stale", "Inputs changed");
  if ($("#autocalc").checked) { clearTimeout(timer); timer = setTimeout(recalc, 650); }
}
async function recalc() {
  clearTimeout(timer);
  try {
    await run();
    if (project.route) await assessRoute();
    if (step === "tbm") await tbmPage();
    if (step === "route" || step === "export") showModel();
    if (step === "route") drawMap();
  } catch { /* reported by api() */ }
}
function autosave() { store.set("project", project); }

// ================================================================ project-level assessment
async function run() {
  lastResult = await api("/api/assess", req());
  renderResults(routeView(lastResult)); kpis(); updateFlags();
  stability();
}
// with a route, results are length-weighted over the ground zones (the section result supplies the item metadata)
function routeView(d) {
  if (!d || !lastRoute || !lastRoute.items_tCO2e) return d;
  const L = lastRoute.alignment.length_m || 1, it = lastRoute.items_tCO2e, mt = lastRoute.modules_tCO2e;
  return { ...d, total_kgCO2e_per_m: lastRoute.average_kgCO2e_per_m, total_tCO2e: lastRoute.total_tCO2e,
    modules_kgCO2e_per_m: Object.fromEntries(Object.entries(mt).map(([m, v]) => [m, v * 1000 / L])),
    items: d.items.map(i => ({ ...i, kg_per_m: (it[i.element] ?? 0) * 1000 / L, tCO2e: it[i.element] ?? 0,
      basis: `route: length-weighted over ${lastRoute.zones.length} zones (section basis: ${i.basis})` })),
    warnings: [...d.warnings, ...(lastRoute.warnings || [])] };
}
function kpis() {
  const d = routeView(lastResult); if (!d) return;
  const c = MODULE_COLOR(), base = scenarios()[0];
  const tile = (v, l, sw, extra = "") => `<div class="kpi"><div class="v">${v}${extra}</div><div class="l">${sw ? `<span class="sw" style="background:${sw}"></span>` : ""}${l}</div></div>`;
  const total = lastRoute ? lastRoute.total_tCO2e : d.total_tCO2e;
  let delta = "";
  if (base && base.total_tCO2e) { const x = 100 * (total / base.total_tCO2e - 1); if (Math.abs(x) >= 0.05) delta = `<span class="d ${x > 0 ? "up" : "down"}" title="vs baseline scenario '${esc(base.name)}'">${x > 0 ? "+" : ""}${fmt(x, 1)}%</span>`; }
  const mt = project.tbm.machine_type && tbmCat ? tbmCat.types.find(t => t.key === project.tbm.machine_type) : null;
  const w = mt && lastRoute?.tbm_applicability?.worst?.[mt.key];
  const fosMin = lastRoute ? Math.min(...lastRoute.zones.map(z => z.fos ?? 99)) : lastStab?.result.fos;
  $("#kpibar").innerHTML =
    tile(fmt(total), `tCO₂e A1–A5 ${lastRoute ? "(route)" : "(project length)"}`, null, delta) +
    tile(fmt(lastRoute ? lastRoute.average_kgCO2e_per_m : d.total_kgCO2e_per_m), "kgCO₂e/m (= tCO₂e per route-km)") +
    Object.entries(d.modules_kgCO2e_per_m).map(([m, v]) => tile(fmt(v), `${m} kgCO₂e/m · ${fmt(100 * v / d.total_kgCO2e_per_m, 0)}%`, c[m])).join("") +
    tile(fosMin != null ? fmt(fosMin, 2) : "–", lastRoute ? `min. FoS over ${lastRoute.zones.length} zones` : "lining FoS (section)") +
    (lastRoute?.settlement ? tile(fmt(lastRoute.settlement.s_max_mm, 0), `mm max. settlement · ${lastRoute.settlement.zones_failing ? lastRoute.settlement.zones_failing + " zone(s) above limit" : "within limit"}`) : "") +
    tile(mt ? esc(mt.label) : "—", mt ? `TBM · ${w || "no route"}` : "TBM type not chosen").replaceAll('class="v"', 'class="v txt"');
}
const chart = (id) => { if (!charts[id]) charts[id] = echarts.init(document.getElementById(id), null, { renderer: "svg" }); return charts[id]; };
const axisStyle = () => ({ axisLine: { lineStyle: { color: css("--line") } }, axisLabel: { color: css("--text-secondary") }, splitLine: { lineStyle: { color: css("--line") } } });
const tip = () => ({ backgroundColor: css("--surface-1"), borderColor: css("--line"), textStyle: { color: css("--text-primary") } });
const axisName = (n, gap = 28) => ({ name: n, nameLocation: "middle", nameGap: gap, nameTextStyle: { color: css("--text-secondary") } });

function renderResults(d) {
  const w = $("#warnings"); w.hidden = !d.warnings.length;
  w.innerHTML = "<h3>Warnings and assumptions</h3><ul>" + d.warnings.map(x => `<li>${esc(x)}</li>`).join("") + "</ul>";
  const c = MODULE_COLOR();
  const items = d.items.filter(i => i.kg_per_m > 0.005);
  const thr = 0.02 * d.total_kgCO2e_per_m, small = new Set(items.filter(i => i.kg_per_m < thr).map(i => i.element));
  const nodes = [...new Set(items.map(i => i.element))].map(n => ({ name: n, itemStyle: { color: css("--neutral") }, label: { show: !small.has(n) } }))
    .concat(["A1-A3", "A4", "A5"].map(m => ({ name: m, itemStyle: { color: c[m] } })));
  chart("sankey").setOption({
    tooltip: { ...tip(), formatter: p => p.dataType === "edge" ? `${p.data.source} → ${p.data.target}<br><b>${fmt(p.data.value, 1)}</b> kgCO₂e/m` : `${p.name}: <b>${fmt(p.value, 1)}</b> kgCO₂e/m` },
    series: [{ type: "sankey", left: 8, right: 70, nodeGap: 8, nodeWidth: 12, draggable: false, emphasis: { focus: "adjacency" },
      label: { color: css("--text-primary"), fontSize: 11 }, lineStyle: { color: "target", opacity: 0.35 },
      data: nodes, links: items.map(i => ({ source: i.element, target: i.module, value: i.kg_per_m })) }]
  }, true);
  const sorted = [...items].sort((a, b) => a.kg_per_m - b.kg_per_m);
  chart("items").setOption({
    grid: { left: 190, right: 60, top: 10, bottom: 30 }, tooltip: { ...tip(), trigger: "item", formatter: p => `${p.name} (${sorted[p.dataIndex].module})<br><b>${fmt(p.value, 1)}</b> kgCO₂e/m` },
    xAxis: { type: "value", ...axisStyle() }, yAxis: { type: "category", data: sorted.map(i => i.element), ...axisStyle(), splitLine: { show: false } },
    series: [{ type: "bar", barMaxWidth: 16, data: sorted.map(i => ({ value: i.kg_per_m, itemStyle: { color: c[i.module], borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: "right", color: css("--text-secondary"), formatter: p => fmt(p.value, 0) } }]
  }, true);
  $("#itemTable").innerHTML = "<tr><th>Module</th><th>Element</th><th>Resource group</th><th class='n'>kgCO₂e/m</th><th class='n'>tCO₂e</th><th class='n'>Tier</th><th>Basis</th></tr>" +
    d.items.map(i => `<tr><td>${i.module}</td><td>${esc(i.element)}</td><td>${esc(i.material_group)}</td><td class="n">${fmt(i.kg_per_m, 1)}</td><td class="n">${fmt(i.tCO2e, 1)}</td><td class="n">${i.nsw_tier}</td><td>${esc(i.basis)}</td></tr>`).join("");
  const s = Object.entries(d.strategies.savings_kgCO2e_per_m).sort((a, b) => a[1] - b[1]);
  chart("strat").setOption({
    grid: { left: 230, right: 70, top: 10, bottom: 30 }, tooltip: { ...tip(), formatter: p => `${p.name}<br><b>${fmt(p.value, 0)}</b> kgCO₂e/m (${fmt(100 * p.value / d.total_kgCO2e_per_m, 1)}% of total)` },
    xAxis: { type: "value", ...axisStyle() }, yAxis: { type: "category", data: s.map(x => x[0]), ...axisStyle(), splitLine: { show: false } },
    series: [{ type: "bar", barMaxWidth: 16, itemStyle: { color: css("--series-1"), borderRadius: [0, 4, 4, 0] }, data: s.map(x => x[1]),
      label: { show: true, position: "right", color: css("--text-secondary"), formatter: p => `${fmt(100 * p.value / d.total_kgCO2e_per_m, 1)}%` } }]
  }, true);
  $("#stratNote").textContent = d.strategies.note + (lastRoute ? " Levers are evaluated on the representative cross-section." : "") + " " + d.strategies.checks.join(" ");
  $("#stratCombined").innerHTML = `All design levers together, applied in sequence: <b>${fmt(d.strategies.combined_design_levers_kgCO2e_per_m)}</b> kgCO₂e/m (${fmt(d.strategies.combined_pct_of_total, 1)}% of A1–A5)`;
}

// ================================================================ stability + optimisation
async function stability() {
  const g = project.geometry;
  const body = { ground: project.ground, support: { radius_m: g.tbm_diameter_m / 2, thickness_m: g.lining_thickness_m,
    concrete_ucs_mpa: project.concrete.strength_mpa, concrete_modulus_mpa: 30000, concrete_poisson: 0.2, install_distance_m: 0 } };
  const r = lastStab = await api("/api/stability", body);
  chart("grc").setOption({
    grid: { left: 64, right: 20, top: 34, bottom: 50 }, legend: { top: 0, textStyle: { color: css("--text-secondary") } },
    tooltip: { ...tip(), trigger: "axis", valueFormatter: v => fmt(v, 3) },
    xAxis: { type: "value", ...axisName("Radial convergence (m)"), max: v => +(Math.min(v.max, Math.max(r.result.u_support_max * 1.6, r.result.u_mob * 4))).toPrecision(2), ...axisStyle() },
    yAxis: { type: "value", ...axisName("Support pressure (MPa)", 40), ...axisStyle() },
    series: [
      { name: "Ground reaction", type: "line", showSymbol: false, lineStyle: { width: 2 }, color: css("--series-1"), data: r.grc },
      { name: "Support", type: "line", showSymbol: false, lineStyle: { width: 2 }, color: css("--series-2"), data: r.scc },
      { name: "Equilibrium", type: "scatter", symbolSize: 10, color: css("--text-primary"), data: [r.equilibrium] }]
  }, true);
  const ok = r.result.fos >= project.criteria.fos_min;
  $("#fosStat").innerHTML = `Factor of safety <b class="${ok ? "ok" : "fail"}">${fmt(r.result.fos, 2)}</b> (required ≥ ${project.criteria.fos_min}) · p<sub>mob</sub> ${fmt(r.result.p_mob, 3)} MPa · u<sub>mob</sub> ${fmt(r.result.u_mob * 1000, 1)} mm`;
  updateFlags(); kpis();
}
async function runOpt() {
  const b = $("#btnOpt"); b.disabled = true; b.textContent = "Optimising…";
  const body = { project, ground: project.ground, fos_min: +$("#fosMin").value, thickness_m: [+$("#tLo").value, +$("#tHi").value],
    strength_mpa: [+$("#fLo").value, +$("#fHi").value], install_distance_m: [+$("#xLo").value, +$("#xHi").value],
    algorithm: $("#algo").value, discrete_grades: $("#grades").checked, u_max_mm: $("#uMax").value === "" ? null : +$("#uMax").value };
  try {
    const r = await api("/api/optimise", body);
    const pts = lastPareto = r.pareto;
    $("#optResults").hidden = false; $("#optHint").hidden = true;
    chart("pareto").setOption({
      grid: { left: 70, right: 24, top: 24, bottom: 50 },
      tooltip: { ...tip(), formatter: p => { const s = pts[p.dataIndex]; return s ? `t ${fmt(s.thickness_m * 1000)} mm · f'c ${fmt(s.strength_mpa, 1)} MPa · x₀ ${fmt(s.install_distance_m, 1)} m<br>FoS <b>${fmt(s.fos, 2)}</b> · ${fmt(s.carbon_kg_per_m)} kgCO₂e/m<br><i>click to apply</i>` : ""; } },
      xAxis: { type: "value", ...axisName("Factor of safety"), ...axisStyle() },
      yAxis: { type: "value", ...axisName("Lining A1–A3 (kgCO₂e/m)", 50), scale: true, ...axisStyle() },
      series: [{ type: "scatter", symbolSize: 10, color: css("--series-1"), itemStyle: { borderColor: css("--surface-1"), borderWidth: 2 }, data: pts.map(s => [s.fos, s.carbon_kg_per_m]),
        markLine: { silent: true, symbol: "none", lineStyle: { color: css("--text-muted"), type: "dashed" }, label: { color: css("--text-secondary"), formatter: "{b}", position: "insideEndTop" },
          data: [{ name: `Current ${fmt(r.baseline_carbon_kg_per_m)}`, yAxis: r.baseline_carbon_kg_per_m }, { name: `FoS min ${r.fos_min}`, xAxis: r.fos_min }] } }]
    }, true);
    chart("pareto").off("click"); chart("pareto").on("click", p => pts[p.dataIndex] && applyDesign(pts[p.dataIndex]));
    parallel(pts, r.baseline);
    $("#paretoTable").innerHTML = pts.length ? "<tr><th class='n'>Thickness (mm)</th><th class='n'>f'c (MPa)</th><th class='n'>Install x₀ (m)</th><th class='n'>FoS</th><th class='n'>u<sub>mob</sub> (mm)</th><th class='n'>kgCO₂e/m</th><th class='n'>Saving</th></tr>" +
      pts.map((s, i) => `<tr data-i="${i}"><td class="n">${fmt(s.thickness_m * 1000)}</td><td class="n">${fmt(s.strength_mpa, 1)}</td><td class="n">${fmt(s.install_distance_m, 1)}</td><td class="n">${fmt(s.fos, 2)}</td><td class="n">${fmt(s.u_mob_m * 1000, 1)}</td><td class="n">${fmt(s.carbon_kg_per_m)}</td><td class="n">${fmt(100 * (1 - s.carbon_kg_per_m / r.baseline_carbon_kg_per_m), 1)}%</td></tr>`).join("")
      : `<tr><td>${esc(r.message)}</td></tr>`;
    $$("#paretoTable tr[data-i]").forEach(tr => tr.onclick = () => applyDesign(pts[+tr.dataset.i]));
  } finally { b.disabled = false; b.textContent = "Optimise"; }
}
function parallel(pts, base) {
  const dims = [["thickness_m", "t (mm)", 1000], ["strength_mpa", "f'c (MPa)", 1], ["install_distance_m", "x₀ (m)", 1], ["fos", "FoS", 1], ["u_mob_m", "u (mm)", 1000], ["carbon_kg_per_m", "kgCO₂e/m", 1]];
  const row = s => dims.map(([k, , f]) => +(s[k] * f).toFixed(3));
  chart("parallel").setOption({
    parallelAxis: dims.map(([, n], i) => ({ dim: i, name: n, nameTextStyle: { color: css("--text-secondary") }, axisLine: { lineStyle: { color: css("--line") } }, axisLabel: { color: css("--text-secondary") } })),
    parallel: { left: 40, right: 50, top: 40, bottom: 30 }, tooltip: { ...tip() },
    series: [{ name: "Pareto", type: "parallel", lineStyle: { width: 1.5, opacity: 0.5, color: css("--series-1") }, data: pts.map(row) },
      { name: "Current design", type: "parallel", lineStyle: { width: 2.5, color: css("--series-2") }, data: base ? [row(base)] : [] }]
  }, true);
}
function groundFromZone() {
  if (selZone == null || !project.route) { toast("Select a route zone first (Route & ground step).", "err"); return; }
  const z = project.route.zones[selZone];
  Object.assign(project.ground, { p0_mpa: +(z.unit_weight_kn_m3 * z.cover_m / 1000).toFixed(3), cohesion_mpa: z.cohesion_mpa, friction_deg: z.friction_deg, modulus_mpa: z.modulus_mpa, poisson: z.poisson });
  buildForms(); onInput("ground"); toast(`Section ground set from zone ${selZone + 1}: ${esc(z.name)}.`, "ok");
}
function applyDesign(sol) {
  const before = { t: project.geometry.lining_thickness_m, f: project.concrete.strength_mpa };
  project.geometry.lining_thickness_m = +sol.thickness_m.toFixed(3); project.concrete.strength_mpa = +sol.strength_mpa.toFixed(1);
  buildForms(); onInput("design"); recalc();
  toast(`Applied t = ${fmt(sol.thickness_m * 1000)} mm, f'c = ${fmt(sol.strength_mpa, 1)} MPa (install ≤ ${fmt(sol.install_distance_m, 1)} m behind the face).`, "ok",
    { label: "Undo", run: () => { project.geometry.lining_thickness_m = before.t; project.concrete.strength_mpa = before.f; buildForms(); onInput("design"); recalc(); } });
}
async function runParam() {
  const list = id => $(id).value.split(",").map(Number).filter(isFinite);
  const d = await api("/api/parametric", { project, ground: project.ground, inner_diameters_m: list("#pDi"), di_over_t: list("#pRatio"), cover_m: list("#pCover"), strength_mpa: +$("#pFc").value });
  const Dis = [...new Set(d.rows.map(r => r.inner_diameter_m))].slice(0, 3), cols = [css("--series-1"), css("--series-2"), css("--series-3")];
  chart("paramChart").setOption({
    grid: { left: 70, right: 24, top: 36, bottom: 50 }, legend: { top: 0, textStyle: { color: css("--text-secondary") } },
    tooltip: { ...tip(), formatter: p => { const r = p.data.r; return `D<sub>i</sub> ${r.inner_diameter_m} m, D<sub>i</sub>/t ${r.di_over_t}, cover ${r.cover_m} m<br>FoS <b>${fmt(r.fos, 2)}</b> · ${fmt(r.carbon_kg_per_m)} kgCO₂e/m`; } },
    xAxis: { type: "value", ...axisName("Factor of safety"), ...axisStyle() }, yAxis: { type: "value", ...axisName("Lining A1–A3 (kgCO₂e/m)", 55), scale: true, ...axisStyle() },
    series: Dis.map((Di, i) => ({ name: `D_i = ${Di} m`, type: "scatter", symbolSize: 10, color: cols[i], itemStyle: { borderColor: css("--surface-1"), borderWidth: 2 },
      data: d.rows.filter(r => r.inner_diameter_m === Di).map(r => ({ value: [r.fos, r.carbon_kg_per_m], r })) }))
  }, true);
  $("#paramTable").innerHTML = "<tr><th class='n'>D<sub>i</sub> m</th><th class='n'>D<sub>i</sub>/t</th><th class='n'>t mm</th><th class='n'>Cover m</th><th class='n'>p₀ MPa</th><th class='n'>FoS</th><th class='n'>u mm</th><th class='n'>kgCO₂e/m</th></tr>" +
    d.rows.map(r => `<tr><td class="n">${r.inner_diameter_m}</td><td class="n">${r.di_over_t}</td><td class="n">${fmt(r.thickness_m * 1000)}</td><td class="n">${r.cover_m}</td><td class="n">${fmt(r.p0_mpa, 2)}</td><td class="n">${fmt(r.fos, 2)}</td><td class="n">${fmt(r.u_mob_mm, 1)}</td><td class="n">${fmt(r.carbon_kg_per_m)}</td></tr>`).join("");
}

// ================================================================ route, zones and the linked selection
const GROUND_COL = { rock: "#7d858f", soil: "#d49a2c", mixed: "#9b62c4" };
// zone columns: [key, header, kind]; the first four are always shown, the rest belong to the "ground" or "design" group
const ZCOLS_ALL = [["name", "Zone", "text"], ["ground_kind", "Ground", ["", "rock", "soil", "mixed"]], ["ch_from", "Ch from"], ["ch_to", "Ch to"],
  ["cover_m", "z₀ m"], ["unit_weight_kn_m3", "γ kN/m³"], ["cohesion_mpa", "c MPa"], ["friction_deg", "φ °"], ["modulus_mpa", "Eₘ MPa"],
  ["rock_quality", "Rock", ["", "competent", "fractured", "weak"]], ["permeability_m_s", "k m/s"], ["fines_pct", "Fines %"], ["water_head_m", "Water m"],
  ["lining_thickness_m", "t m"], ["concrete_strength_mpa", "f'c MPa"], ["install_distance_m", "x₀ m"], ["volume_loss_pct", "V<sub>L</sub> %"], ["trough_k", "K"]];
const ZGROUP = { ground: ZCOLS_ALL.slice(0, 10), water: [...ZCOLS_ALL.slice(0, 5), ...ZCOLS_ALL.slice(10, 13)],
  design: [...ZCOLS_ALL.slice(0, 5), ...ZCOLS_ALL.slice(13)], all: ZCOLS_ALL };
let zoneCols = "ground";
let ZCOLS = ZGROUP[zoneCols];
const NULLABLE = ["lining_thickness_m", "concrete_strength_mpa", "permeability_m_s", "water_head_m", "fines_pct", "volume_loss_pct", "trough_k"];
function ensureRoute() { if (!project.route) { project.route = clone(defaults.route); dirty.map = true; } }
function zoneTable() {
  if (!project.route) { $("#zoneTable").innerHTML = `<tr><td class="note">No route yet. Start from an example on the Project step, import a corridor, or generate an alignment below.</td></tr>`; return; }
  const z = project.route.zones, rz = lastRoute?.zones || [];
  $("#zoneTable").innerHTML = "<tr><th></th>" + ZCOLS.map(c => `<th>${c[1]}</th>`).join("") + "<th class='n'>C m</th><th class='n' title='JSCE control pressure at the axis'>p kPa</th><th class='n'>kgCO₂e/m</th><th class='n'>FoS</th><th class='n' title='Maximum surface settlement from the volume loss (Gaussian trough); tooltip gives V_L, i and the Rankin category'>S mm</th><th></th></tr>" +
    z.map((r, i) => `<tr data-z="${i}" class="${i === selZone ? "sel" : ""}"><td class="swatch" style="background:${GROUND_COL[r.ground_kind] || "transparent"}"></td>` +
      ZCOLS.map(([k, , t]) => Array.isArray(t)
        ? `<td><select data-i="${i}" data-k="${k}" aria-label="${k}">${t.map(o => `<option ${o === (r[k] ?? "") ? "selected" : ""}>${o}</option>`).join("")}</select></td>`
        : `<td><input data-i="${i}" data-k="${k}" aria-label="${k}" ${t === "text" || k === "permeability_m_s" ? "" : 'type="number" step="any"'} value="${esc(k.startsWith("ch_") ? +(+r[k]).toFixed(1) : k === "permeability_m_s" && r[k] != null ? Number(r[k]).toExponential(0) : (r[k] ?? ""))}" placeholder="${["lining_thickness_m", "concrete_strength_mpa"].includes(k) ? "project" : ["volume_loss_pct", "trough_k"].includes(k) ? "estimated" : ""}" title="${r.unit ? esc(r.unit + " · face " + Object.entries(r.face_fractions || {}).map(([u, f]) => `${u} ${Math.round(f * 100)}%`).join(", ")) : ""}"></td>`).join("") +
      `<td class="n">${rz[i] ? fmt(rz[i].crown_cover_m, 1) : "–"}</td>` +
      `<td class="n ${rz[i]?.face_support && !rz[i].face_support.within_band ? "fail" : ""}" title="${rz[i]?.face_support ? `crown ${fmt(rz[i].face_support.p_control_crown_kpa)} kPa ≤ σv ${fmt(rz[i].face_support.upper_crown_kpa)} kPa` : "open-face machine"}">${rz[i]?.face_support ? fmt(rz[i].face_support.p_control_axis_kpa) : "–"}</td>` +
      `<td class="n">${rz[i] ? fmt(rz[i].kgCO2e_per_m) : "–"}</td><td class="n ${rz[i] && !rz[i].uls_ok ? "fail" : ""}">${rz[i] ? (rz[i].fos ? fmt(rz[i].fos, 2) : "∞") : "–"}</td>` +
      `<td class="n ${rz[i]?.settlement && !(rz[i].settlement.s_ok && rz[i].settlement.slope_ok) ? "fail" : ""}" title="${rz[i]?.settlement ? `V_L ${fmt(rz[i].settlement.volume_loss_pct, 2)} % (${esc(rz[i].settlement.basis)}) · K ${fmt(rz[i].settlement.K, 2)} · i ${fmt(rz[i].settlement.i_m, 1)} m · slope 1/${fmt(1 / rz[i].settlement.slope_max)} · Rankin category ${rz[i].settlement.damage_category}` : ""}">${rz[i]?.settlement ? fmt(rz[i].settlement.s_max_mm, 1) : "–"}</td>` +
      `<td><button data-del="${i}" aria-label="Delete zone">×</button></td></tr>`).join("");
  $$("#zoneTable input").forEach(el => el.oninput = () => {
    const r = z[+el.dataset.i], k = el.dataset.k;
    r[k] = k === "name" ? el.value : (el.value === "" ? (NULLABLE.includes(k) ? null : 0) : +el.value);
    onInput("route.zones");
  });
  $$("#zoneTable select").forEach(el => el.onchange = () => { z[+el.dataset.i][el.dataset.k] = el.value || null; onInput("route.zones"); zoneTable(); });
  $$("#zoneTable button[data-del]").forEach(b => b.onclick = (e) => { e.stopPropagation(); const i = +b.dataset.del, removed = z.splice(i, 1)[0];
    selZone = null; zoneTable(); onInput("route.zones");
    toast(`Deleted zone “${esc(removed.name)}”.`, "", { label: "Undo", run: () => { z.splice(i, 0, removed); zoneTable(); onInput("route.zones"); } }); });
  $$("#zoneTable tr[data-z]").forEach(tr => tr.onclick = (e) => { if (!["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName)) selectZone(+tr.dataset.z); });
  $$("#zoneTable tr[data-z] input, #zoneTable tr[data-z] select").forEach(el => el.addEventListener("focus", () => selectZone(+el.closest("tr").dataset.z, { quiet: true })));
  const al = project.route.alignment;
  $("#alInfo").textContent = `${al.name}: ${al.points.length} points${project.route.crs ? `, georeferenced (EPSG:${project.route.crs.epsg})` : ""}.`;
}
function selectZone(i, { quiet = false } = {}) {
  if (!project.route || i == null || i < 0 || i >= project.route.zones.length) return;
  const same = selZone === i; selZone = i;
  $$("#zoneTable tr[data-z]").forEach(tr => tr.classList.toggle("sel", +tr.dataset.z === i));
  const z = project.route.zones[i];
  styleMap(); routeCharts();
  window.dispatchEvent(new CustomEvent("tunco2:select-zone", { detail: { index: i, ch_from: z.ch_from, ch_to: z.ch_to, frame: !quiet || !same } }));
  if (!quiet) { const tr = $(`#zoneTable tr[data-z="${i}"]`); tr?.scrollIntoView({ block: "nearest" }); }
}
async function assessRoute() {
  if (!project.route) { lastRoute = null; return; }
  lastRoute = await api("/api/route", req());
  zoneTable(); routeCharts(); styleMap(); kpis(); updateFlags();
  if (lastResult) renderResults(routeView(lastResult));
  const w = $("#routeWarn"); w.hidden = !lastRoute.warnings.length; w.innerHTML = "<ul>" + lastRoute.warnings.map(x => `<li>${esc(x)}</li>`).join("") + "</ul>";
}
function routeCharts() {
  const d = lastRoute; if (!d) return;
  const selArea = selZone != null && d.zones[selZone] ? { silent: true, itemStyle: { color: css("--sel"), opacity: 0.18 }, data: [[{ xAxis: d.zones[selZone].ch_from }, { xAxis: d.zones[selZone].ch_to }]] } : undefined;
  chart("routeCarbon").setOption({
    grid: { left: 70, right: 20, top: 20, bottom: 50 }, tooltip: { ...tip(), trigger: "item", formatter: p => `${esc(d.zones[p.data.z].zone)}<br><b>${fmt(p.value[1])}</b> kgCO₂e/m` },
    xAxis: { type: "value", ...axisName("Chainage (m)"), min: d.alignment.start_chainage_m, max: d.alignment.end_chainage_m, ...axisStyle() },
    yAxis: { type: "value", ...axisName("kgCO₂e/m", 55), ...axisStyle() },
    series: [{ type: "line", showSymbol: true, symbolSize: 6, connectNulls: false, lineStyle: { width: 2 }, areaStyle: { opacity: 0.12 }, color: css("--series-1"),
      data: d.zones.flatMap((z, i) => [{ value: [z.ch_from, z.kgCO2e_per_m], z: i }, { value: [z.ch_to, z.kgCO2e_per_m], z: i }, null]), markArea: selArea }]
  }, true);
  chart("routeCarbon").off("click"); chart("routeCarbon").on("click", p => p.data && selectZone(p.data.z));
  chart("routeFos").setOption({
    grid: { left: 60, right: 20, top: 20, bottom: 60 }, tooltip: { ...tip(), trigger: "item", formatter: p => `${esc(d.zones[p.dataIndex].zone)}<br>FoS <b>${fmt(p.value, 2)}</b>` },
    xAxis: { type: "category", data: d.zones.map((z, i) => `${i + 1}`), ...axisStyle(), ...axisName("Zone") },
    yAxis: { type: "value", name: "FoS", ...axisStyle() },
    series: [{ type: "bar", barMaxWidth: 40, data: d.zones.map((z, i) => ({ value: Math.min(z.fos ?? 50, 50), itemStyle: { color: i === selZone ? css("--sel") : z.uls_ok ? css("--series-3") : css("--series-2"), borderRadius: [4, 4, 0, 0] } })),
      label: { show: true, position: "top", color: css("--text-secondary"), formatter: p => d.zones[p.dataIndex].fos ? fmt(d.zones[p.dataIndex].fos, 1) : "∞" },
      markLine: { silent: true, symbol: "none", lineStyle: { color: css("--text-muted"), type: "dashed" }, label: { formatter: `FoS min ${project.criteria.fos_min}`, color: css("--text-secondary"), position: "insideEndTop" }, data: [{ yAxis: project.criteria.fos_min }] } }]
  }, true);
  chart("routeFos").off("click"); chart("routeFos").on("click", p => selectZone(p.dataIndex));
}
async function optimiseRoute() {
  ensureRoute(); const b = $("#btnRouteOpt"); b.disabled = true; b.textContent = "Optimising…";
  try {
    const d = lastRouteOpt = await api("/api/route/optimise", { project, algorithm: "nsga2", discrete_grades: true });
    $("#routeOptCard").hidden = false;
    $("#routeOptTable").innerHTML = "<tr><th>Zone</th><th>Current t / f'c</th><th class='n'>kgCO₂e/m (lining)</th><th>Optimised t / f'c / x₀</th><th class='n'>FoS</th><th class='n'>kgCO₂e/m (lining)</th></tr>" +
      d.zones.map(z => { const b0 = z.baseline, r = z.recommended; return `<tr><td>${esc(z.zone)}</td><td>${fmt(b0.thickness_m * 1000)} mm / ${fmt(b0.strength_mpa)} MPa</td><td class="n">${fmt(b0.carbon_kg_per_m)}</td>` +
        (r ? `<td>${fmt(r.thickness_m * 1000)} mm / ${fmt(r.strength_mpa)} MPa / ${fmt(r.install_distance_m, 1)} m</td><td class="n">${fmt(r.fos, 2)}</td><td class="n">${fmt(r.carbon_kg_per_m)}</td>` : `<td colspan="3">no feasible design</td>`) + "</tr>"; }).join("") +
      `<tr><td><b>Route</b></td><td></td><td class="n">${fmt(d.baseline_lining_tCO2e)} t</td><td></td><td></td><td class="n"><b>${fmt(d.optimised_lining_tCO2e)} t (−${fmt(d.saving_pct, 1)}%)</b></td></tr>`;
    $("#routeOptCard").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } finally { b.disabled = false; b.textContent = "Optimise lining in every zone"; }
}

// ---------------------------------------------------------------- plan map (Leaflet)
let map = null, mapGeo = null, mapLayers = [], plan = null, mapColour = "ground";
// keep the route in view when the window or the layout changes size
let _fitT = null;
function fitMap() { if (map && mapLayers.length) { map.invalidateSize(); map.fitBounds(L.featureGroup(mapLayers).getBounds(), { padding: [20, 20], animate: false }); } }
window.addEventListener("resize", () => { clearTimeout(_fitT); _fitT = setTimeout(fitMap, 150); });
async function drawMap() {
  if (!project.route) { if (map) { mapLayers.forEach(l => l.remove()); mapLayers = []; } $("#mapNote").textContent = "No route defined."; return; }
  if (dirty.map || !plan) { plan = await api("/api/route/plan", req()); dirty.map = false; }
  if (!map || mapGeo !== plan.georeferenced) {
    if (map) map.remove();
    mapGeo = plan.georeferenced;
    map = L.map("map", mapGeo ? { zoomControl: true } : { crs: L.CRS.Simple, minZoom: -6, zoomSnap: 0.25 });
    if (mapGeo) L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
  }
  mapLayers.forEach(l => l.remove()); mapLayers = [];
  plan.zones.forEach((z, i) => {
    const line = L.polyline(z.latlng, { weight: 7, opacity: 0.9, lineCap: "butt" }).addTo(map);
    line.on("click", () => selectZone(i)); line.bindTooltip(() => zoneTip(i), { sticky: true });
    mapLayers.push(line);
  });
  const all = plan.zones.flatMap(z => z.latlng);
  map.invalidateSize();  // the map may have been sized while its step was hidden
  if (all.length) map.fitBounds(L.latLngBounds(all), { padding: [20, 20] });
  $("#mapNote").textContent = mapGeo ? `EPSG:${plan.crs.epsg} → WGS84. Basemap © OpenStreetMap contributors (needs an internet connection).` : "Local coordinates (route not georeferenced): plan view in metres.";
  styleMap();
}
function zoneTip(i) {
  const z = project.route.zones[i], r = lastRoute?.zones?.[i];
  return `<b>${i + 1}. ${esc(z.name)}</b><br>Ch ${fmt(z.ch_from)}–${fmt(z.ch_to)} · ${z.ground_kind ?? "ground n/a"}${z.unit ? " · " + esc(z.unit) : ""}` + (r ? `<br>${fmt(r.kgCO2e_per_m)} kgCO₂e/m · FoS ${r.fos ? fmt(r.fos, 2) : "∞"}` : "");
}
function ramp(t) { t = Math.max(0, Math.min(1, t)); const a = [27, 175, 122], b = [242, 183, 5], c = [200, 73, 42];
  const m = (p, q, u) => p.map((x, k) => Math.round(x + (q[k] - x) * u)); const r = t < .5 ? m(a, b, t * 2) : m(b, c, (t - .5) * 2); return `rgb(${r})`; }
function styleMap() {
  if (!map || !mapLayers.length) return;
  const rz = lastRoute?.zones || [], vals = rz.map(z => z.kgCO2e_per_m), lo = Math.min(...vals), hi = Math.max(...vals);
  mapLayers.forEach((l, i) => {
    const z = project.route?.zones[i]; if (!z) return;
    let col = GROUND_COL[z.ground_kind] || css("--neutral");
    if (mapColour === "carbon" && rz[i]) col = ramp(hi > lo ? (rz[i].kgCO2e_per_m - lo) / (hi - lo) : 0.5);
    if (mapColour === "fos" && rz[i]) col = ramp(1 - Math.min(((rz[i].fos ?? 99) - project.criteria.fos_min) / (3 * project.criteria.fos_min), 1));
    l.setStyle({ color: i === selZone ? css("--sel") : col, weight: i === selZone ? 12 : 7 });
    if (i === selZone) l.bringToFront();
  });
}

// ---------------------------------------------------------------- 3D
function showModel() {
  if (!dirty.model) return; dirty.model = false;
  const lod = +$("#lodSel").value;
  $("#lodNote").textContent = `LoD ${lod}: ${defaults.lod_content[lod] || ""}. ${project.route ? "Built along the route alignment and ground zones." : "No route: a straight stretch of rings."}`;
  $("#v3dNote").textContent = project.route ? "click the model to pick a zone" : "";
  window.dispatchEvent(new CustomEvent("tunco2:model", { detail: { ...req(), rings: +$("#nRings").value, lod,
    tbm_type: $("#tbmAtFace").checked ? project.tbm.machine_type : null,
    zones: project.route ? project.route.zones.map(z => [z.ch_from, z.ch_to]) : [], selected: selZone } }));
}
window.addEventListener("tunco2:zone-picked", (e) => {
  const ch = e.detail.chainage, zs = project.route?.zones || [];
  const i = zs.findIndex(z => ch >= z.ch_from - 1e-6 && ch <= z.ch_to + 1e-6); if (i >= 0) selectZone(i, { quiet: false });
});

// ================================================================ GIS import
function applyCorridor(d) {
  project.route = d.route; dirty.map = dirty.model = dirty.tbm = true; selZone = null;
  if (d.suggested_geometry) Object.assign(project.geometry, d.suggested_geometry);
  project.tunnel_length_m = +d.length_m.toFixed(1);
  const g = d.source.registration;
  $("#gisInfo").innerHTML = `${esc(d.route.alignment.name)}: ${fmt(d.length_m)} m, ${d.route.zones.length} zones. Registered at s₀ = ${fmt(g.s0_m, 2)} m for CH ${fmt(g.ch0_m)} (surface RMS ${fmt(g.rms_m, 2)} m). Tunnel level: ${esc(d.source.tunnel_level)}.`;
  toast(`Corridor loaded: ${fmt(d.length_m)} m in ${d.route.zones.length} ground zones (registration RMS ${fmt(g.rms_m, 2)} m). <b>Zone ground parameters are indicative</b>; replace them with values from the geotechnical interpretative report.`, "ok");
  buildForms(); autosave(); zoneTable(); go("route"); recalc();
}
async function loadExample(key) {
  const d = await api(`/api/gis/example/${key}?min_zone_m=${$("#gisMin").value || 40}` + ($("#gisGw").value ? `&groundwater_depth_m=${$("#gisGw").value}` : ""));
  const g = project.ground; project = d.project; project.ground = g || clone(defaults.ground); syncMass();
  applyCorridor(d);
  if (d.reference) toast(`Example after: ${esc(d.reference)}`);
}
let examples = {};
function buildExamples() {
  $("#examples").innerHTML = Object.entries(examples).map(([k, e]) => `<button class="excard" data-k="${k}"><span class="nm">${esc(e.name.replace(" (example)", ""))}</span>
    <span class="note">${esc(e.summary)}</span><span class="fam">${esc(tbmCat?.types.find(t => t.key === e.machine)?.label || e.machine)} · D ${e.geometry.tbm_diameter_m} m · ${e.functional.kind}${e.functional.count > 1 ? " × " + e.functional.count : ""}${e.reference ? " · after a published study" : ""}</span></button>`).join("");
  $$("#examples .excard").forEach(b => b.onclick = () => loadExample(b.dataset.k));
  $("#exFiles").innerHTML = "Example input files: " + Object.keys(examples).map(k => `${k} <a href="/api/gis/examples/${k}/plan_line.csv">plan</a> · <a href="/api/gis/examples/${k}/long_section.json">section</a> · <a href="/api/gis/examples/${k}/crs.json">CRS</a>`).join("; ") + ".";
}
async function importCorridor() {
  const f = id => $(id).files[0];
  if (!f("#gisPlan") || !f("#gisLs") || !f("#gisCrs")) { toast("Choose the plan line CSV, the long section JSON and the CRS JSON first.", "err"); return; }
  const body = { plan_csv: await f("#gisPlan").text(), long_section: JSON.parse(await f("#gisLs").text()), crs: JSON.parse(await f("#gisCrs").text()),
    tbm_diameter_m: project.geometry.tbm_diameter_m, min_zone_m: +($("#gisMin").value || 40), groundwater_depth_m: $("#gisGw").value ? +$("#gisGw").value : null,
    ch_from: $("#gisC0").value ? +$("#gisC0").value : null, ch_to: $("#gisC1").value ? +$("#gisC1").value : null };
  applyCorridor(await api("/api/gis/import", body));
}

// ================================================================ TBM selection
let selTbm = null;
const RATING = { suitable: "✓ suitable", marginal: "~ marginal", unsuitable: "✗ unsuitable" };
async function tbmPage() {
  if (!tbmCat) return;
  if (dirty.tbm || !lastCompare) { lastCompare = await api("/api/tbm/compare", req()); dirty.tbm = false; }
  const c = lastCompare, cur = project.tbm.machine_type;
  selTbm = selTbm || cur || c.lowest_carbon_suitable || "epb";
  $("#tbmCards").innerHTML = c.types.map(t => `<button class="tbmcard ${t.type === selTbm ? "on" : ""}" data-k="${t.type}">
      <span class="nm">${esc(t.label)}</span><span class="fam">${esc(t.family)}</span>
      <span class="rt ${t.rating || ""}">${t.rating ? RATING[t.rating] : "no route"}${t.suitable_share != null ? ` · ${fmt(t.suitable_share * 100)}% of route` : ""}</span>
      <span class="co">A5 ${fmt(t.a5_kg_per_m)} kgCO₂e/m</span>
      ${t.type === cur ? '<span class="use">IN USE</span>' : t.type === c.lowest_carbon_suitable ? '<span class="use">LOWEST-CARBON SUITABLE</span>' : ""}</button>`).join("");
  $$("#tbmCards .tbmcard").forEach(b => b.onclick = () => { selTbm = b.dataset.k; $$("#tbmCards .tbmcard").forEach(x => x.classList.toggle("on", x === b)); showTbm(); });
  showTbm(); tbmMatrix(c.applicability); tbmChart(c);
}
function showTbm() {
  const t = tbmCat.types.find(x => x.key === selTbm), m = tbmCat.models[selTbm] || {};
  const row = lastCompare?.types.find(x => x.type === selTbm);
  $("#tbmTitle").textContent = t.label;
  const rows = [["Family", t.family], ["Thrust reacted", t.thrust_reaction], ["Face support", t.face_support], ["Muck route", t.muck_route],
    ["Thrust / torque", row ? `${fmt(row.thrust_MN, 1)} MN / ${fmt(row.torque_MNm, 1)} MN·m (Part 3 regression, ${t.regression_type})` : t.regression_type],
    ["Machine mass", row ? `${fmt(row.mass_t)} t, ${t.mass_regression_note || t.mass_model + " regression (Part 3)"}` : t.mass_regression_note],
    ["Notes", t.notes.map(esc).join("<br>")]];
  $("#tbmInfo").innerHTML = rows.map(([a, b]) => `<tr><th>${a}</th><td>${b}</td></tr>`).join("");
  const cur = project.tbm.machine_type;
  $("#btnUseTbm").disabled = cur === selTbm; $("#btnUseTbm").textContent = cur === selTbm ? "In use for the project" : `Use ${t.label}`;
  $("#tbmUsing").textContent = cur ? "" : "No machine chosen yet: the project uses the v1 thrust, torque and mass settings.";
  $("#tbmModelNote").textContent = tbmCat.model_note;
  window.dispatchEvent(new CustomEvent("tunco2:tbm-preview", { detail: { type: selTbm } }));
}
function tbmMatrix(a) {
  if (!a) { $("#tbmMatrix").innerHTML = `<tr><td class="note">Define a route with ground zones to rate the machines.</td></tr>`; return; }
  const T = tbmCat.types, S = { suitable: "✓", marginal: "~", unsuitable: "✗" };
  $("#tbmMatrix").innerHTML = `<tr><th>#</th><th>Zone</th><th>Ch</th><th>Ground</th>${T.map(t => `<th>${esc(t.label)}</th>`).join("")}</tr>` +
    a.zones.map((z, i) => `<tr data-z="${i}"><td>${i + 1}</td><td>${esc(z.zone)}</td><td>${fmt(z.ch_from)}–${fmt(z.ch_to)}</td><td><span class="badge ${z.ground_kind || ""}">${z.ground_kind ?? "–"}</span>${z.unit ? ` ${esc(z.unit)}` : ""}</td>` +
      T.map(t => { const r = z.ratings[t.key]; return `<td class="r r-${r.rating}" title="${esc(r.reason)}">${S[r.rating]}</td>`; }).join("") + "</tr>").join("") +
    `<tr><th colspan="4">Share of route suitable</th>${T.map(t => `<td class="r r-${a.worst[t.key]}">${fmt(a.share[t.key].suitable * 100)}%</td>`).join("")}</tr>`;
  $$("#tbmMatrix tr[data-z]").forEach(tr => tr.onclick = () => { selectZone(+tr.dataset.z); go("route"); });
}
function tbmChart(c) {
  const keys = [...new Set(c.types.flatMap(t => Object.keys(t.a5_items)))];
  const cols = [css("--series-1"), css("--series-2"), css("--series-3"), css("--neutral"), "#8a6bbf", "#c9a227", "#5aa9a0", "#b0607a"];
  chart("tbmCompare").setOption({
    grid: { left: 70, right: 20, top: 40, bottom: 40 }, legend: { top: 0, type: "scroll", textStyle: { color: css("--text-secondary") } },
    tooltip: { ...tip(), trigger: "axis", valueFormatter: v => fmt(v) },
    xAxis: { type: "category", data: c.types.map(t => t.label), ...axisStyle(), axisLabel: { color: css("--text-secondary"), interval: 0 } },
    yAxis: { type: "value", name: "kgCO₂e/m", ...axisStyle() },
    series: keys.map((k, i) => ({ name: k, type: "bar", stack: "a5", color: cols[i % cols.length], barMaxWidth: 46, data: c.types.map(t => t.a5_items[k] || 0),
      ...(i === keys.length - 1 ? { label: { show: true, position: "top", color: css("--text-secondary"), formatter: p => fmt(c.types[p.dataIndex].a5_kg_per_m) } } : {}) }))
  }, true);
  chart("tbmCompare").off("click"); chart("tbmCompare").on("click", p => { selTbm = c.types[p.dataIndex].type; tbmPage(); });
  const best = c.types.find(t => t.type === c.lowest_carbon_suitable);
  $("#tbmCompareNote").innerHTML = `${esc(c.basis)} ` + (best ? `Lowest-carbon machine suitable along the whole route: <b>${esc(best.label)}</b>.` : c.applicability ? "No machine is rated suitable along the whole route; see the matrix." : "") +
    " Hard-rock TBM mass uses the EPB regression unless a manufacturer mass is entered.";
}
function syncMass() {  // show the mass model the machine type implies (a manufacturer mass stays as entered)
  const t = tbmCat?.types.find(x => x.key === project.tbm.machine_type);
  if (t && project.tbm.mass_model !== "user") project.tbm.mass_model = t.mass_model;
}
function useTbm() {
  const prev = project.tbm.machine_type; project.tbm.machine_type = selTbm; syncMass();
  buildForms(); onInput("tbm.machine_type"); recalc().then(() => tbmPage());
  toast(`${tbmCat.types.find(t => t.key === selTbm).label} is now the project machine.`, "ok", { label: "Undo", run: () => { project.tbm.machine_type = prev; buildForms(); onInput("tbm"); recalc().then(() => tbmPage()); } });
}

// ================================================================ scenarios
const scenarios = () => store.get("scenarios", []);
const saveScenarios = (s) => { store.set("scenarios", s); scenSelect(); updateFlags(); kpis(); };
function scenSummary(name) {
  const L = lastRoute ? lastRoute.alignment.length_m : project.tunnel_length_m, d = lastResult;
  const mods = lastRoute ? lastRoute.modules_tCO2e : Object.fromEntries(Object.entries(d.modules_kgCO2e_per_m).map(([k, v]) => [k, v * L / 1000]));
  return { name, when: new Date().toISOString(), project: clone(project), compat_v1: $("#compat").checked,
    total_tCO2e: lastRoute ? lastRoute.total_tCO2e : d.total_tCO2e, per_m: lastRoute ? lastRoute.average_kgCO2e_per_m : d.total_kgCO2e_per_m,
    length_m: L, modules_tCO2e: mods, items_tCO2e: Object.fromEntries(d.items.map(i => [i.element, i.kg_per_m * L / 1000])),
    min_fos: lastRoute ? Math.min(...lastRoute.zones.map(z => z.fos ?? 99)) : lastStab?.result.fos };
}
function askName(title, hint, value) {
  const dlg = $("#nameDlg"); $("#nameTitle").textContent = title; $("#nameHint").textContent = hint || ""; $("#nameIn").value = value || "";
  return new Promise(ok => { dlg.onclose = () => ok(dlg.returnValue === "ok" ? $("#nameIn").value.trim() : null); dlg.showModal(); $("#nameIn").select(); });
}
async function saveScenario() {
  if (pending || $("#status").classList.contains("stale")) await recalc();
  const s = scenarios(), mt = tbmCat?.types.find(t => t.key === project.tbm.machine_type)?.label;
  const name = await askName("Save as scenario", s.length ? "Saved scenarios are compared against the first one (the baseline)." : "The first scenario becomes the baseline.", `${s.length ? "Option " + s.length : "Baseline"}: ${mt || "v1 TBM"}, ${project.concrete.strength_mpa} MPa, t ${project.geometry.lining_thickness_m * 1000} mm`);
  if (!name) return;
  const i = s.findIndex(x => x.name === name), row = scenSummary(name);
  if (i >= 0) s[i] = row; else s.push(row);
  saveScenarios(s); scenSelect(name); toast(`Saved scenario “${esc(name)}”${s.length === 1 ? " as the baseline" : ""}.`, "ok");
  if (step === "scenarios") scenPage();
}
function scenSelect(active) {
  const s = scenarios();
  $("#scenSel").innerHTML = `<option value="">Current inputs</option>` + s.map((x, i) => `<option value="${i}" ${x.name === active ? "selected" : ""}>${i === 0 ? "★ " : ""}${esc(x.name)}</option>`).join("");
}
function loadScenario(i) {
  const s = scenarios()[i]; if (!s) return;
  const prev = clone(project);
  project = clone(s.project); $("#compat").checked = !!s.compat_v1; afterProjectChange();
  toast(`Loaded scenario “${esc(s.name)}”.`, "", { label: "Undo", run: () => { project = prev; afterProjectChange(); } });
}
function scenPage() {
  const s = scenarios(); $("#scenEmpty").hidden = !!s.length;
  const base = s[0];
  $("#scenTable").innerHTML = s.length ? "<tr><th></th><th>Scenario</th><th>Machine</th><th class='n'>f'c</th><th class='n'>t mm</th><th class='n'>Length m</th><th class='n'>tCO₂e</th><th class='n'>kgCO₂e/m</th><th class='n'>vs baseline</th><th class='n'>min FoS</th><th></th></tr>" +
    s.map((x, i) => { const dlt = base ? 100 * (x.total_tCO2e / base.total_tCO2e - 1) : 0, p = x.project;
      return `<tr><td>${i === 0 ? '<span class="badge" title="Baseline">★ base</span>' : ""}</td><td>${esc(x.name)}<div class="note">${new Date(x.when).toLocaleString("en-AU")}</div></td>
      <td>${esc(tbmCat?.types.find(t => t.key === p.tbm.machine_type)?.label || "v1 settings")}</td><td class="n">${fmt(p.concrete.strength_mpa)}</td><td class="n">${fmt(p.geometry.lining_thickness_m * 1000)}</td>
      <td class="n">${fmt(x.length_m)}</td><td class="n"><b>${fmt(x.total_tCO2e)}</b></td><td class="n">${fmt(x.per_m)}</td>
      <td class="n ${i && dlt > 0 ? "fail" : i ? "ok" : ""}">${i ? (dlt > 0 ? "+" : "") + fmt(dlt, 1) + "%" : "—"}</td><td class="n">${fmt(x.min_fos, 2)}</td>
      <td style="white-space:nowrap"><button data-a="load" data-i="${i}">Load</button> ${i ? `<button data-a="base" data-i="${i}" title="Make this the baseline">★</button>` : ""} <button data-a="ren" data-i="${i}" aria-label="Rename">✎</button> <button data-a="del" data-i="${i}" aria-label="Delete">×</button></td></tr>`; }).join("") : "";
  $$("#scenTable button").forEach(b => b.onclick = () => {
    const i = +b.dataset.i, all = scenarios();
    if (b.dataset.a === "load") { loadScenario(i); go("results"); return; }
    if (b.dataset.a === "base") all.unshift(all.splice(i, 1)[0]);
    if (b.dataset.a === "ren") { askName("Rename scenario", "", all[i].name).then(n => { if (!n) return; const a = scenarios(); a[i].name = n; saveScenarios(a); scenPage(); }); return; }
    if (b.dataset.a === "del") { const rm = all.splice(i, 1)[0]; toast(`Deleted “${esc(rm.name)}”.`, "", { label: "Undo", run: () => { const a = scenarios(); a.splice(i, 0, rm); saveScenarios(a); scenPage(); } }); }
    saveScenarios(all); scenPage();
  });
  const c = MODULE_COLOR(), names = s.map(x => x.name);
  chart("scenChart").setOption({
    grid: { left: 70, right: 20, top: 36, bottom: 60 }, legend: { top: 0, textStyle: { color: css("--text-secondary") } }, tooltip: { ...tip(), trigger: "axis", valueFormatter: v => fmt(v) },
    xAxis: { type: "category", data: names, ...axisStyle(), axisLabel: { color: css("--text-secondary"), interval: 0, width: 120, overflow: "truncate" } },
    yAxis: { type: "value", name: "tCO₂e", ...axisStyle() },
    series: ["A1-A3", "A4", "A5"].map(m => ({ name: m, type: "bar", stack: "t", color: c[m], barMaxWidth: 60, data: s.map(x => x.modules_tCO2e[m] || 0) }))
  }, true);
  const els = [...new Set(s.flatMap(x => Object.keys(x.items_tCO2e)))];
  const deltas = s.slice(1).map(x => ({ name: x.name, d: els.map(e => (x.items_tCO2e[e] || 0) - (base?.items_tCO2e[e] || 0)) }));
  const keep = els.map((e, j) => [e, Math.max(0, ...deltas.map(x => Math.abs(x.d[j])))]).filter(x => x[1] > 0.5).map(x => x[0]);
  chart("scenDelta").setOption({
    grid: { left: 190, right: 30, top: 36, bottom: 30 }, legend: { top: 0, type: "scroll", textStyle: { color: css("--text-secondary") } }, tooltip: { ...tip(), trigger: "axis", valueFormatter: v => (v > 0 ? "+" : "") + fmt(v) + " t" },
    xAxis: { type: "value", ...axisStyle() }, yAxis: { type: "category", data: keep, ...axisStyle(), splitLine: { show: false } },
    series: deltas.map((x, k) => ({ name: x.name, type: "bar", barMaxWidth: 14, color: [css("--series-1"), css("--series-2"), css("--series-3"), "#8a6bbf"][k % 4], data: keep.map(e => x.d[els.indexOf(e)]) })),
    graphic: deltas.length ? [] : [{ type: "text", left: "center", top: "middle", style: { text: "Save two or more scenarios to compare", fill: css("--text-muted") } }]
  }, true);
  // input differences
  const flat = (o, p = "", out = {}) => { for (const [k, v] of Object.entries(o || {})) { if (k === "route" && p === "") { out["route (zones)"] = v ? `${v.zones.length} zones, ${fmt(v.alignment.points.length)} pts` : "none"; continue; }
    const q = p ? `${p}.${k}` : k; if (v && typeof v === "object" && !Array.isArray(v)) flat(v, q, out); else out[q] = JSON.stringify(v); } return out; };
  const F = s.map(x => flat(x.project)), keys = [...new Set(F.flatMap(Object.keys))].filter(k => new Set(F.map(f => f[k])).size > 1);
  $("#scenDiff").innerHTML = s.length < 2 ? `<tr><td class="note">Differences appear here once two scenarios are saved.</td></tr>` :
    `<tr><th>Input</th>${names.map(n => `<th>${esc(n)}</th>`).join("")}</tr>` + keys.slice(0, 60).map(k => `<tr><td>${esc(k)}</td>${F.map(f => `<td>${esc((f[k] ?? "–").replace(/^"|"$/g, ""))}</td>`).join("")}</tr>`).join("");
}

// ---------------------------------------------------------------- example comparison
let exCmp = null, exBasis = "m";
async function exCompare() {
  const b = $("#btnExCompare"); b.disabled = true; b.textContent = "Assessing four routes…";
  try { exCmp = await api(`/api/gis/examples/compare?compat_v1=${$("#compat").checked}`, null, { method: "GET" }); } finally { b.disabled = false; b.textContent = "Compare examples"; }
  $("#exCompareOut").hidden = false; $("#btnExScen").disabled = false; exRender();
}
function exRender() {
  if (!exCmp) return;
  const R = exCmp.examples, c = MODULE_COLOR();
  const f = (r, m) => { const v = r.modules_kgCO2e_per_m[m]; return exBasis === "m" ? v : exBasis === "m3" ? v / (Math.PI / 4 * r.tbm_diameter_m ** 2) : exBasis === "fu" ? v / r.functional_count : r.modules_tCO2e[m]; };
  const unit = { m: "kgCO₂e/m", m3: "kgCO₂e per m³ excavated", fu: "tCO₂e per track/lane-km", t: "tCO₂e" }[exBasis];
  const lab = R.map(r => `${r.name.replace(" (example)", "")}\n${r.machine_label.replace(" TBM", "")} ${r.tbm_diameter_m} m`);
  chart("exChart").setOption({
    grid: { left: 70, right: 16, top: 36, bottom: 50 }, legend: { top: 0, textStyle: { color: css("--text-secondary") } }, tooltip: { ...tip(), trigger: "axis", valueFormatter: v => fmt(v, exBasis === "m3" ? 1 : 0) },
    xAxis: { type: "category", data: lab, ...axisStyle(), axisLabel: { color: css("--text-secondary"), interval: 0 } },
    yAxis: { type: "value", name: unit, ...axisStyle() },
    series: ["A1-A3", "A4", "A5"].map((m, k) => ({ name: m, type: "bar", stack: "s", color: c[m], barMaxWidth: 56, data: R.map(r => f(r, m)),
      ...(k === 2 ? { label: { show: true, position: "top", color: css("--text-secondary"), formatter: p => fmt(["A1-A3", "A4", "A5"].reduce((s, mm) => s + f(R[p.dataIndex], mm), 0), exBasis === "m3" ? 1 : 0) } } : {}) }))
  }, true);
  const a5 = [...new Set(R.flatMap(r => Object.keys(r.items_kgCO2e_per_m)))].filter(k => /TBM|Spoil|separation|plant|diesel|site/i.test(k));
  const cols = [css("--series-1"), css("--series-2"), css("--series-3"), css("--neutral"), "#8a6bbf", "#c9a227", "#5aa9a0"];
  chart("exA5").setOption({
    title: { text: "A5 by item (kgCO₂e/m)", left: 0, top: 0, textStyle: { fontSize: 12, color: css("--text-secondary"), fontWeight: 600 } },
    grid: { left: 70, right: 16, top: 56, bottom: 50 }, legend: { top: 18, type: "scroll", textStyle: { color: css("--text-secondary") } }, tooltip: { ...tip(), trigger: "axis", valueFormatter: v => fmt(v) },
    xAxis: { type: "category", data: lab, ...axisStyle(), axisLabel: { color: css("--text-secondary"), interval: 0 } }, yAxis: { type: "value", ...axisStyle() },
    series: a5.map((k, i) => ({ name: k, type: "bar", stack: "a5", barMaxWidth: 56, color: cols[i % cols.length], data: R.map(r => r.items_kgCO2e_per_m[k] || 0) }))
  }, true);
  const rt = { suitable: "✓", marginal: "~", unsuitable: "✗" };
  $("#exTable").innerHTML = `<tr><th>Example</th><th>TBM</th><th class="n">D m</th><th class="n">D<sub>i</sub> / t m</th><th class="n">Length m</th><th class="n">tCO₂e</th><th class="n">kgCO₂e/m</th><th class="n">kgCO₂e/m³ exc.</th><th class="n">tCO₂e per track/lane-km</th><th class="n" title="Excavation specific energy from the cutterhead mechanics, P10 – P50 – P90 over the parameter ranges">SE kWh/m³<br>P10–P50–P90</th><th class="n">A1–A3 %</th><th class="n">A5 %</th><th class="n">min FoS</th><th>Machine fit</th><th></th></tr>` +
    R.map((r, i) => { const tot = r.kgCO2e_per_m; return `<tr><td>${esc(r.name)}</td><td>${esc(r.machine_label)}</td><td class="n">${r.tbm_diameter_m}</td><td class="n">${r.inner_diameter_m} / ${r.lining_thickness_m}</td><td class="n">${fmt(r.length_m)}</td>
      <td class="n"><b>${fmt(r.total_tCO2e)}</b></td><td class="n">${fmt(tot)}</td><td class="n">${fmt(r.kgCO2e_per_m3_excavated, 1)}</td><td class="n">${fmt(r.tCO2e_per_functional_unit)}</td>
      <td class="n">${r.excavation_energy_band ? r.excavation_energy_band.specific_energy_kWh_m3.map(v => fmt(v, 1)).join(" – ") : "–"}</td>
      <td class="n">${fmt(100 * r.modules_kgCO2e_per_m["A1-A3"] / tot)}</td><td class="n">${fmt(100 * r.modules_kgCO2e_per_m["A5"] / tot)}</td>
      <td class="n ${r.zones_failing ? "fail" : ""}">${fmt(r.min_fos, 2)}${r.zones_failing ? ` (${r.zones_failing} zone${r.zones_failing > 1 ? "s" : ""} fail)` : ""}</td>
      <td><span class="rt ${r.machine_worst_rating}">${rt[r.machine_worst_rating]}</span> ${fmt(100 * r.machine_suitable_share)}% of route</td>
      <td><button data-open="${i}">Open</button></td></tr>`; }).join("");
  $$("#exTable button[data-open]").forEach(b => b.onclick = async () => { project = clone(R[+b.dataset.open].project); await afterProjectChange(); go("route"); });
  $("#exNote").innerHTML = esc(exCmp.basis) + (R.find(r => r.reference) ? ` Hydro example after: ${esc(R.find(r => r.reference).reference)}` : "");
}
function exToScenarios() {
  const s = scenarios();
  exCmp.examples.forEach(r => { const row = { name: r.name.replace(" (example)", "") + `, ${r.machine_label.replace(" TBM", "")} ${r.tbm_diameter_m} m`, when: new Date().toISOString(),
    project: r.project, compat_v1: $("#compat").checked, total_tCO2e: r.total_tCO2e, per_m: r.kgCO2e_per_m, length_m: r.length_m,
    modules_tCO2e: r.modules_tCO2e, items_tCO2e: r.items_tCO2e, min_fos: r.min_fos };
    const i = s.findIndex(x => x.name === row.name); if (i >= 0) s[i] = row; else s.push(row); });
  saveScenarios(s); scenPage(); toast("Saved the four examples as scenarios; the first in the list is the baseline.", "ok");
}

// ================================================================ exports
const EXPORTS = [
  ["Excel report", "NSW-structured workbook: summary, line items with tier and basis, levers, route sheet, factors, inputs.", () => download("/api/report.xlsx", `TunCO2Pro_${project.name.replace(/\W+/g, "_")}.xlsx`, req())],
  ["IFC 4.3", "Segmental lining with carbon property sets; georeferenced (IfcMapConversion) when the route has a CRS. For Revit, Bonsai, Navisworks.", () => download(`/api/geometry?fmt=ifc&lod=${$("#lodSel").value}&rings=${$("#nRings").value}`, `TunCO2Pro_LoD${$("#lodSel").value}.ifc`, req())],
  ["Rhino .3dm", "Model for Rhino and Grasshopper.", () => download(`/api/geometry?fmt=3dm&lod=${$("#lodSel").value}&rings=${$("#nRings").value}`, `TunCO2Pro_LoD${$("#lodSel").value}.3dm`, req())],
  ["glTF", "Lightweight 3D for web viewers and presentations.", () => download(`/api/geometry?fmt=glb&lod=${$("#lodSel").value}&rings=${$("#nRings").value}`, `TunCO2Pro_LoD${$("#lodSel").value}.glb`, req())],
  ["GeoJSON", "Centreline and zones with carbon, FoS and TBM ratings for QGIS / ArcGIS.", () => download("/api/gis/geojson", "tunco2pro_route.geojson", req()), "geo"],
  ["Blender package", "Scene, lining and TBM models and the importer script, in project coordinates for Blender scenes that share the origin.", () => download(`/api/gis/blender?lod=${$("#lodSel").value}`, "tunco2pro_blender.zip", req()), "geo"],
  ["Project file", "All inputs as JSON, to reopen here or share with a colleague.", () => saveJson()],
];
function buildExports() {
  const geo = !!project.route?.crs;
  $("#exports").innerHTML = EXPORTS.map(([n, d, , need], i) => `<div class="exp"><span class="nm">${n}</span><p>${d}${need === "geo" && !geo ? " <b>Needs a georeferenced route.</b>" : ""}</p>
    <button data-x="${i}" ${need === "geo" && !geo ? "disabled" : ""}>Download</button></div>`).join("");
  $$("#exports button").forEach(b => b.onclick = async () => { b.disabled = true; const t = b.textContent; b.textContent = "Preparing…"; try { await EXPORTS[+b.dataset.x][2](); } finally { b.disabled = false; b.textContent = t; } });
}
let FIGS = null;
async function buildFigures() {
  FIGS ??= await api("/api/figures", null, { method: "GET" });
  const hasRoute = !!(project.route?.zones?.length);
  const box = $("#figures"); if (!box) return;
  box.innerHTML = Object.entries(FIGS.figures).map(([k, d]) => { const free = FIGS.project_free.includes(k); const ok = free || hasRoute || !/^Route|optimisation|Pareto/.test(d);
    return `<div class="exp"><span class="nm">${esc(k)}</span><p>${esc(d)}${ok ? "" : " <b>Needs a route with ground zones.</b>"}</p><button data-f="${k}" ${ok ? "" : "disabled"}>Download</button></div>`; }).join("");
  $$("#figures button").forEach(b => b.onclick = () => figureDownload(b, b.dataset.f));
  $("#btnFigAll").onclick = async () => { const bb = $("#btnFigAll"); bb.disabled = true; try { for (const b of $$("#figures button:not([disabled])")) await figureDownload(b, b.dataset.f); } finally { bb.disabled = false; } };
}
async function figureDownload(b, name) {
  const fmt = $("#figFmt").value, t = b.textContent; b.disabled = true; b.textContent = "Drawing…";
  try { await download(`/api/figures/${name}?fmt=${fmt}`, `tunco2pro-${name}.${fmt}`, { project: FIGS.project_free.includes(name) ? null : project }); }
  catch { }
  finally { b.disabled = false; b.textContent = t; }
}
async function download(url, name, body) {
  const r = await api(url, body, { raw: true });
  const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = name; a.click();
}
function saveJson() { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(project, null, 2)], { type: "application/json" })); a.download = `${project.name.replace(/\W+/g, "_") || "tunco2pro_project"}.json`; a.click(); }

// ================================================================ wiring
async function loadFactors() { factors = await api(`/api/factors?factor_set=${project.factor_set || "current"}`, null, { method: "GET" }); factorTable(); }
function factorTable() {
  $("#libVer").textContent = `Factor set: ${factors.version}. Tier = NSW emission-factor hierarchy (1 = product EPD … 4 = international literature). Project EPDs can be supplied as factor overrides (tier 1).`;
  $("#factorTable").innerHTML = "<tr><th>Key</th><th>Name</th><th class='n'>Value</th><th>Unit</th><th>Source</th><th class='n'>Tier</th><th>Notes</th></tr>" +
    factors.factors.map(f => `<tr><td>${esc(f.key)}</td><td>${esc(f.name)}</td><td class="n">${f.value}</td><td>${esc(f.unit)}</td><td>${esc(f.source)}</td><td class="n">${f.nsw_tier}</td><td>${esc(f.notes)}</td></tr>`).join("");
}
async function afterProjectChange() {
  project.ground ??= clone(defaults.ground);
  selZone = null; lastRoute = null; lastCompare = null; plan = null;
  dirty.model = dirty.tbm = dirty.map = true;
  await loadFactors(); buildForms(); zoneTable(); buildExports(); buildFigures(); autosave();
  $("#lodSel").value = project.lod;
  await recalc();
  if (step === "route") drawMap();
}
function wire() {
  $("#btnPrev").onclick = () => { const i = STEPS.findIndex(s => s[0] === step); if (i > 0) go(STEPS[i - 1][0]); };
  $("#btnNext").onclick = () => { const i = STEPS.findIndex(s => s[0] === step); if (i < STEPS.length - 1) go(STEPS[i + 1][0]); };
  $("#projName").oninput = () => { project.name = $("#projName").value; autosave(); };
  const pop = $("#menuPop");
  $("#btnMenu").onclick = (e) => { e.stopPropagation(); pop.hidden = !pop.hidden; $("#btnMenu").setAttribute("aria-expanded", String(!pop.hidden)); };
  const help = $("#helpPop");
  $("#btnHelp").onclick = (e) => { e.stopPropagation(); help.hidden = !help.hidden; pop.hidden = true; $("#btnHelp").setAttribute("aria-expanded", String(!help.hidden)); };
  document.addEventListener("click", (e) => { if (!pop.contains(e.target)) pop.hidden = true; if (!help.contains(e.target)) help.hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { pop.hidden = true; help.hidden = true; } });
  fetch("/api/health").then(r => r.json()).then(h => { $("#about").textContent = `TunCO2 Pro ${h.version} · factor library ${h.factor_library}`; }).catch(() => {});
  pop.querySelectorAll("button[data-act]").forEach(b => b.onclick = () => { pop.hidden = true;
    if (b.dataset.act === "load") $("#fileIn").click();
    if (b.dataset.act === "save") saveJson();
    if (b.dataset.act === "reset") resetDefault(); });
  $("#advanced").onchange = () => { document.body.classList.toggle("advanced", $("#advanced").checked); store.set("advanced", $("#advanced").checked); };
  $("#compat").onchange = async () => { project.factor_set = $("#compat").checked ? "v1" : "current"; await loadFactors(); buildForms(); onInput("compat"); };
  $("#autocalc").onchange = () => { store.set("autocalc", $("#autocalc").checked); if ($("#autocalc").checked) recalc(); };
  $("#status").onclick = () => recalc(); $("#status").title = "Click to recalculate now";
  $("#fileIn").onchange = async (e) => { const f = e.target.files[0]; if (!f) return; try { project = JSON.parse(await f.text()); await afterProjectChange(); toast(`Opened ${esc(f.name)}.`, "ok"); } catch (err) { toast(`Could not open ${esc(f.name)}: ${esc(err.message)}`, "err"); } e.target.value = ""; };
  $("#btnStartDefault").onclick = resetDefault;
  $("#btnStartOpen").onclick = () => $("#fileIn").click();
  $("#btnGis").onclick = importCorridor;
  $("#btnAddZone").onclick = () => { ensureRoute(); const z = project.route.zones, last = z[z.length - 1];
    z.push({ ...clone(last || defaults.route.zones[0]), name: `Zone ${z.length + 1}`, ch_from: last ? last.ch_to : 0, ch_to: (last ? last.ch_to : 0) + 200 }); zoneTable(); selectZone(z.length - 1); onInput("route.zones"); };
  $("#btnSplitZone").onclick = () => { if (selZone == null) { toast("Select a zone first (click a row, the map or the model).", "err"); return; }
    const z = project.route.zones, a = z[selZone], mid = +((a.ch_from + a.ch_to) / 2).toFixed(1), b = { ...clone(a), name: a.name + " (b)", ch_from: mid };
    a.ch_to = mid; z.splice(selZone + 1, 0, b); zoneTable(); onInput("route.zones"); };
  $("#btnRouteOpt").onclick = optimiseRoute;
  $("#btnApplyZones").onclick = () => { if (!lastRouteOpt) return; const z = project.route.zones; let n = 0;
    lastRouteOpt.zones.forEach((o, i) => { const r = o.recommended, zz = z[i]; if (zz && r) { zz.lining_thickness_m = +r.thickness_m.toFixed(3); zz.concrete_strength_mpa = r.strength_mpa; zz.install_distance_m = +r.install_distance_m.toFixed(2); n++; } });
    zoneTable(); onInput("route.zones"); recalc(); toast(`Applied optimised designs to ${n} zones.`, "ok"); };
  $("#btnAl").onclick = async () => { ensureRoute();
    const q = new URLSearchParams({ length_m: $("#alLen").value, depth_start: $("#alZ0").value, depth_end: $("#alZ1").value }); if ($("#alR").value) q.set("radius_m", $("#alR").value);
    const d = await api("/api/alignment/simple?" + q); project.route.alignment = d.alignment; project.route.crs = null; project.route.source = null;
    const L = d.length_m, z = project.route.zones;
    if (z.length) { const k = L / (z[z.length - 1].ch_to - z[0].ch_from || L); let c = 0;
      z.forEach((zz, i) => { const len = (zz.ch_to - zz.ch_from) * k; zz.ch_from = +c.toFixed(1); zz.ch_to = i === z.length - 1 ? +L.toFixed(1) : +(c + len).toFixed(1); c += len; }); }
    project.tunnel_length_m = +L.toFixed(1); buildForms(); zoneTable(); onInput("route.alignment"); recalc(); };
  $("#btnXml").onclick = () => $("#xmlIn").click();
  $("#xmlIn").onchange = async (e) => { ensureRoute(); const txt = await e.target.files[0].text();
    const r = await fetch("/api/alignment/landxml", { method: "POST", headers: { "Content-Type": "application/xml" }, body: txt });
    if (!r.ok) { toast((await r.json()).detail, "err"); return; }
    const d = await r.json(); project.route.alignment = d.alignment; project.route.zones = d.zones; project.route.crs = null; zoneTable(); onInput("route.alignment"); recalc(); };
  $$("#mapColour button").forEach(b => b.onclick = () => { mapColour = b.dataset.c; $$("#mapColour button").forEach(x => x.classList.toggle("on", x === b)); styleMap(); });
  $$("#zoneCols button").forEach(b => b.onclick = () => { zoneCols = b.dataset.c; ZCOLS = ZGROUP[zoneCols]; $$("#zoneCols button").forEach(x => x.classList.toggle("on", x === b)); zoneTable(); });
  $("#btnUseTbm").onclick = useTbm;
  $("#btnOpt").onclick = runOpt; $("#btnParam").onclick = runParam;
  $("#btnModel").onclick = () => { dirty.model = true; showModel(); };
  $("#lodSel").onchange = () => { project.lod = +$("#lodSel").value; dirty.model = true; showModel(); autosave(); };
  $("#tbmAtFace").onchange = () => { dirty.model = true; showModel(); };
  $("#btnExCompare").onclick = exCompare; $("#btnExScen").onclick = exToScenarios;
  $$("#exBasis button").forEach(b => b.onclick = () => { exBasis = b.dataset.b; $$("#exBasis button").forEach(x => x.classList.toggle("on", x === b)); exRender(); });
  $("#btnSaveScen").onclick = saveScenario; $("#btnSaveScen2").onclick = saveScenario;
  $("#scenSel").onchange = () => { if ($("#scenSel").value !== "") loadScenario(+$("#scenSel").value); };
  $("#btnExportScen").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(scenarios(), null, 1)], { type: "application/json" })); a.download = "tunco2pro_scenarios.json"; a.click(); };
  $("#btnImportScen").onclick = () => $("#scenIn").click();
  $("#scenIn").onchange = async (e) => { try { const add = JSON.parse(await e.target.files[0].text()); saveScenarios([...scenarios(), ...add]); scenPage(); toast(`Imported ${add.length} scenarios.`, "ok"); } catch (err) { toast("Not a scenarios file: " + esc(err.message), "err"); } e.target.value = ""; };
  window.addEventListener("resize", () => Object.values(charts).forEach(c => c.resize()));
}
async function resetDefault() {
  const prev = clone(project); project = clone(defaults.project); project.ground = clone(defaults.ground);
  await afterProjectChange(); toast("Reset to the default case.", "", { label: "Undo", run: () => { project = prev; afterProjectChange(); } });
}

(async () => {
  buildSteps(); wire();
  document.body.classList.toggle("advanced", !!store.get("advanced", false)); $("#advanced").checked = !!store.get("advanced", false);
  $("#autocalc").checked = store.get("autocalc", true);
  defaults = await api("/api/defaults", null, { method: "GET" }); help = defaults.field_help || {};
  tbmCat = await api("/api/tbm/types", null, { method: "GET" });
  examples = await api("/api/gis/examples", null, { method: "GET" }); buildExamples();
  const saved = store.get("project");
  project = saved || clone(defaults.project); project.ground ??= clone(defaults.ground);
  scenSelect();
  go(store.get("step", "project"));
  await afterProjectChange();
  if (saved) toast("Restored your last session.", "", { label: "Start fresh", run: resetDefault });
})();
