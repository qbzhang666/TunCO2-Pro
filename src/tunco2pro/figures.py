"""Publication figures from the engine: the same charts the browser app shows, drawn for print.

Each maker takes a project (or nothing, for the reference-tunnel comparisons) and returns a matplotlib
Figure together with the numbers it plots. `render()` returns the figure as PDF, SVG or PNG (1000 dpi)
bytes; the app's Step 8 (Model and export) and `tunco2pro figures` on the command line call it. The style
matches the textbook: Latin Modern Sans (Computer Modern), a fixed colour-blind-checked palette, thin marks,
captions left to the document.

Requires matplotlib (`pip install tunco2pro[figures]`).
"""
from __future__ import annotations

import io
import math
from pathlib import Path

from .models import ProjectInput

FONT_DIR = Path(__file__).parent / "data" / "fonts"
C = {"s1": "#4F86C6", "s2": "#E58B2A", "s3": "#7551A8", "s4": "#4E9A68", "ink": "#30343B", "ink2": "#5A5F68",
     "grid": "#E2E4E7", "neutral": "#9AA0A8", "tan": "#D8C6A8"}
W = 6.3  # figure width in inches: the text width of the book
FORMATS = {"pdf": "application/pdf", "svg": "image/svg+xml", "png": "image/png"}

FIGURES = {
    "route": "Route: axis depth and ground at the face, face support pressure (thrust for open-face machines), excavation energy (P10 to P90)",
    "suitability": "Route: suitability of the six machine types, zone by zone",
    "items": "Upfront carbon per metre by line item, length-weighted over the route, by lifecycle module",
    "levers": "Decarbonisation levers: saving of each lever alone and of the design levers combined",
    "se-penetration": "Specific energy against penetration (shield) and against the field penetration index (hard rock)",
    "route-optimisation": "Zone-by-zone lining optimisation: lining carbon and factor of safety along the route",
    "pareto": "Pareto set of linings (carbon against factor of safety) for the zone with the lowest factor of safety",
    "pathway": "Reduction pathway: the design levers applied in sequence from the baseline to the residual carbon per metre",
    "machines": "Machine types compared on the project: A5 carbon per metre by item, total per metre and suitability",
    "design-space": "Lining design space of the zone with the lowest factor of safety: lining carbon and FoS over thickness and grade",
    "examples": "Reference tunnels: upfront carbon per metre and per cubic metre excavated",
    "examples-composition": "Reference tunnels: upfront carbon per metre by element, and the composition in per cent",
    "examples-levers": "Reference tunnels: saving of each lever and of the design levers combined, per tunnel",
    "benchmark": "Reference tunnels against the published rail exemplar: carbon per metre and per cubic metre against diameter",
    "cutterhead": "Reference tunnels: specific-energy bands and composition of the cutterhead torque",
    "examples-pathway": "Reference tunnels: verified reduction from the baseline (zone-by-zone lining optimisation, then material and energy levers) to the residual",
    "settlement": "Route: volume-loss settlement screening; maximum settlement and trough slope along the route, and the transverse and longitudinal troughs of the worst zone",
}
PROJECT_FREE = {"examples", "examples-composition", "examples-levers", "benchmark", "cutterhead", "examples-pathway"}

_ready = False


def _setup():
    """Fonts and rcParams, once."""
    global _ready
    if _ready:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in FONT_DIR.glob("*.ttf"):
        font_manager.fontManager.addfont(str(f))
    fam = "LMSans10TT" if any(FONT_DIR.glob("*.ttf")) else "DejaVu Sans"
    plt.rcParams.update({"font.family": fam, "font.size": 8.5, "axes.labelsize": 8.5, "xtick.labelsize": 8,
                         "ytick.labelsize": 8, "legend.fontsize": 8, "axes.edgecolor": C["ink2"], "axes.linewidth": 0.6,
                         "axes.labelcolor": C["ink"], "xtick.color": C["ink2"], "ytick.color": C["ink2"],
                         "text.color": C["ink"], "axes.spines.top": False, "axes.spines.right": False,
                         "legend.frameon": False, "mathtext.fontset": "custom", "mathtext.rm": fam,
                         "mathtext.it": f"{fam}:italic", "mathtext.bf": f"{fam}:bold", "axes.formatter.use_mathtext": True,
                         "axes.unicode_minus": False, "pdf.fonttype": 42, "svg.fonttype": "path",
                         "savefig.bbox": "tight", "savefig.pad_inches": 0.03})
    _ready = True


def _plt():
    _setup()
    import matplotlib.pyplot as plt
    return plt


def _panel(ax, letter):
    ax.text(-0.02, 1.04, f"({letter})", transform=ax.transAxes, fontweight="bold", ha="right", fontsize=9, va="bottom")


def _ygrid(ax):
    ax.yaxis.grid(True, color=C["grid"], lw=0.5); ax.set_axisbelow(True)


def _xgrid(ax):
    ax.xaxis.grid(True, color=C["grid"], lw=0.5); ax.set_axisbelow(True)


def _section(p: ProjectInput) -> ProjectInput:
    from .carbon import apply_machine_type
    return apply_machine_type(p).model_copy(update={"route": None})


def _route_result(p: ProjectInput) -> dict:
    from .route import assess_route
    if not p.route or not p.route.zones:
        raise ValueError("this figure needs a route with ground zones (Step 2)")
    return assess_route(p)


# ------------------------------------------------------------------------------------------ route figures
def make_route(p: ProjectInput, rt: dict | None = None):
    """Axis depth with the ground at the face, face support pressure and excavation energy along the route."""
    plt = _plt(); from matplotlib.patches import Patch
    rt = rt or _route_result(p); zs = rt["zones"]
    kcol = {"soil": C["tan"], "mixed": C["s2"], "rock": C["neutral"]}
    fig, axs = plt.subplots(3, 1, figsize=(W, 4.6), sharex=True, gridspec_kw={"height_ratios": [1.1, 1, 1]})

    def steps(f):
        xs, ys = [], []
        for z in zs:
            xs += [z["ch_from"] / 1000, z["ch_to"] / 1000]; ys += [f(z)] * 2
        return xs, ys
    ax = axs[0]
    for z in zs:
        ax.axvspan(z["ch_from"] / 1000, z["ch_to"] / 1000, ymin=0.92, ymax=1.0, color=kcol[z["ground_kind"]], lw=0)
    xs, ys = steps(lambda z: z["cover_m"]); ax.plot(xs, ys, color=C["s1"], lw=2)
    ax.set_ylim(max(ys) * 1.1, -0.1 * max(ys)); ax.set_ylabel("Axis depth $z_0$, m"); _ygrid(ax); _panel(ax, "a")
    ax.legend(handles=[Patch(color=kcol[k], label=k.capitalize()) for k in ("soil", "mixed", "rock")],
              loc="lower right", bbox_to_anchor=(1, 1.0), ncol=3)
    ax = axs[1]
    closed = all(z.get("face_support") for z in zs)   # open-face (hard-rock) machines carry no face support pressure
    xs, ys = steps(lambda z: z["face_support"]["p_control_axis_kpa"] if closed else z["thrust_MN"]); ax.plot(xs, ys, color=C["s1"], lw=2)
    ax.set_ylabel("Face pressure, kPa" if closed else "Thrust, MN"); ax.set_ylim(0, None); _ygrid(ax); _panel(ax, "b")
    ax = axs[2]
    xs, lo, mid, hi = [], [], [], []
    for z in zs:
        b = (z.get("cutterhead") or {}).get("energy_kWh_per_m_p10_p50_p90") or [z["energy_kWh_per_m"]] * 3
        xs += [z["ch_from"] / 1000, z["ch_to"] / 1000]; lo += [b[0]] * 2; mid += [b[1]] * 2; hi += [b[2]] * 2
    ax.fill_between(xs, lo, hi, color=C["s1"], alpha=0.18, lw=0); ax.plot(xs, mid, color=C["s1"], lw=2)
    ax.set_ylabel("Excavation, kWh/m"); ax.set_xlabel("Chainage, km"); ax.set_ylim(0, None); _ygrid(ax); _panel(ax, "c")
    fig.tight_layout(h_pad=1.0)
    return fig, {"zones": [{k: z[k] for k in ("zone", "ch_from", "ch_to", "cover_m", "ground_kind", "energy_kWh_per_m")}
                           | {"p_control_axis_kpa": (z.get("face_support") or {}).get("p_control_axis_kpa"), "thrust_MN": z["thrust_MN"]} for z in zs]}


def make_suitability(p: ProjectInput, rt: dict | None = None):
    """Suitability of the six machine types along the route."""
    plt = _plt(); from matplotlib.patches import Patch
    from .tbm_types import ORDER, TYPES
    rt = rt or _route_result(p); ra = rt["tbm_applicability"]
    rcol = {"suitable": C["s4"], "marginal": C["tan"], "unsuitable": "#6E737B"}
    fig, ax = plt.subplots(figsize=(W, 2.0))
    for j, t in enumerate(ORDER):
        for zr in ra["zones"]:
            ax.barh(j, (zr["ch_to"] - zr["ch_from"]) / 1000, left=zr["ch_from"] / 1000, height=0.62,
                    color=rcol[zr["ratings"][t]["rating"]], edgecolor="white", linewidth=0.6)
    ax.set_yticks(range(len(ORDER)), [TYPES[t].label.replace(" TBM", "").replace(" shield", "") for t in ORDER])
    ax.invert_yaxis(); ax.set_xlabel("Chainage, km"); ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
    ax.legend(handles=[Patch(color=rcol[k], label=k.capitalize()) for k in ("suitable", "marginal", "unsuitable")],
              loc="lower right", bbox_to_anchor=(1, 1.0), ncol=3)
    return fig, {"share": ra["share"]}


def make_items(p: ProjectInput, rt: dict | None = None, min_kg_per_m: float = 1.0):
    """Upfront carbon per metre by line item, length-weighted over the route, coloured by module."""
    plt = _plt(); from matplotlib.patches import Patch
    from .carbon import assess
    rt = rt or _route_result(p); L = rt["alignment"]["length_m"]
    items = {k: v * 1000 / L for k, v in rt["items_tCO2e"].items()}
    mod_of = {i.element: i.module for i in assess(_section(p)).items}
    rows = sorted(((k, v) for k, v in items.items() if v >= min_kg_per_m), key=lambda kv: kv[1])
    mcol = {"A1-A3": C["s1"], "A4": C["s2"], "A5": C["s3"]}
    fig, ax = plt.subplots(figsize=(W * 0.8, 3.0))
    ax.barh([k for k, _ in rows], [v for _, v in rows], 0.6, color=[mcol[mod_of.get(k, "A5")] for k, _ in rows])
    xmax = max(v for _, v in rows)
    for y, (k, v) in enumerate(rows):
        ax.text(v + 0.01 * xmax, y, f"{v:,.0f}", va="center", fontsize=7.5, color=C["ink2"])
    ax.set_xlabel("kgCO$_2$e per metre"); _xgrid(ax); ax.tick_params(axis="y", length=0); ax.spines["left"].set_visible(False)
    ax.legend(handles=[Patch(color=mcol[m], label=m) for m in mcol], loc="lower right")
    return fig, {"items_kg_per_m": items, "modules_kg_per_m": {k: v * 1000 / L for k, v in rt["modules_tCO2e"].items()}}


def make_settlement(p: ProjectInput, rt: dict | None = None, zone: str | int | None = None):
    """Volume-loss settlement screening along the route (Gaussian trough) with the troughs of one zone."""
    plt = _plt()
    from .settlement import profiles
    rt = rt or _route_result(p); zs = rt["zones"]; crit = p.settlement
    if zone is None:
        zi = max(range(len(zs)), key=lambda j: zs[j]["settlement"]["s_max_mm"])
    else:
        zi = zone if isinstance(zone, int) else next(j for j, z in enumerate(zs) if z["zone"] == zone)
    zsel = zs[zi]; st = zsel["settlement"]; pr = profiles(zsel["cover_m"], st["i_m"], st["s_max_mm"] / 1000, 121)
    fig = plt.figure(figsize=(W, 4.9))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1], hspace=0.5, wspace=0.32)
    # (a) maximum settlement and slope along the route
    ax = fig.add_subplot(gs[0, :]); ax2 = ax.twinx()
    for z in zs:
        s = z["settlement"]; x0, x1 = z["ch_from"] / 1000, z["ch_to"] / 1000
        ax.bar((x0 + x1) / 2, s["s_max_mm"], x1 - x0, color=C["s1"] if s["s_ok"] else C["s2"], edgecolor="white", linewidth=0.5)
        ax2.plot([x0, x1], [1000 * s["slope_max"]] * 2, color=C["s3"], lw=1.6)
    ax.axhline(crit.s_max_mm, color=C["ink2"], lw=0.8, ls=(0, (4, 2)))
    ax.text(zs[0]["ch_from"] / 1000, crit.s_max_mm, f" limit {crit.s_max_mm:.0f} mm", va="bottom", ha="left", fontsize=7.5, color=C["ink2"])
    ax2.axhline(1000 * crit.slope_max, color=C["s3"], lw=0.8, ls=(0, (4, 2)))
    ax2.text(zs[-1]["ch_to"] / 1000, 1000 * crit.slope_max, f"1/{1 / crit.slope_max:.0f} ", va="bottom", ha="right", fontsize=7.5, color=C["s3"])
    ax2.set_ylabel("Max. slope, mm/m", color=C["s3"]); ax2.tick_params(axis="y", colors=C["s3"]); ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(C["s3"]); ax2.set_ylim(0, None)
    ax.set_ylabel("$S_{max}$, mm"); ax.set_xlabel("Chainage, km"); ax.set_ylim(0, None); _ygrid(ax); _panel(ax, "a")
    ax.set_xlim(zs[0]["ch_from"] / 1000, zs[-1]["ch_to"] / 1000)
    ax.axvspan(zsel["ch_from"] / 1000, zsel["ch_to"] / 1000, color=C["tan"], alpha=0.35, lw=0, zorder=0)
    # (b) transverse trough of the selected zone: settlement and horizontal movement
    ax = fig.add_subplot(gs[1, 0])
    ax.plot(pr["y_m"], [-v for v in pr["s_mm"]], color=C["s1"], lw=1.8, label="settlement $S$")
    ax.plot(pr["y_m"], pr["h_mm"], color=C["s4"], lw=1.4, ls=(0, (4, 2)), label="horizontal $H$ (towards the axis)")
    for sgn in (-1, 1):
        ax.axvline(sgn * st["i_m"], color=C["ink2"], lw=0.6, ls=(0, (2, 2)))
    ax.text(st["i_m"], 0.02 * st["s_max_mm"], " $i$", fontsize=7.5, color=C["ink2"], va="bottom")
    ax.set_xlabel("Offset from the axis $y$, m"); ax.set_ylabel("Movement, mm"); _ygrid(ax); ax.legend(loc="lower right"); _panel(ax, "b")
    # (c) longitudinal profile about the face
    ax = fig.add_subplot(gs[1, 1])
    ax.plot(pr["x_ahead_m"], [-v for v in pr["s_long_mm"]], color=C["s1"], lw=1.8)
    ax.axvline(0, color=C["s2"], lw=1.0); ax.text(0.5, -0.05 * st["s_max_mm"], "face", color=C["s2"], fontsize=7.5, va="top")
    ax.set_xlabel("Distance ahead of the face $x$, m"); ax.set_ylabel("Axis settlement, mm"); _ygrid(ax); _panel(ax, "c")
    ax.set_xlim(pr["x_ahead_m"][0], pr["x_ahead_m"][-1])
    return fig, {"zone": zsel["zone"], "ch_from": zsel["ch_from"], "cover_m": zsel["cover_m"], "settlement": st,
                 "route": rt["settlement"], "criteria": crit.model_dump(),
                 "zones": [{"zone": z["zone"], "ch_from": z["ch_from"], "ch_to": z["ch_to"], "s_max_mm": z["settlement"]["s_max_mm"],
                            "i_m": z["settlement"]["i_m"], "volume_loss_pct": z["settlement"]["volume_loss_pct"],
                            "slope_max": z["settlement"]["slope_max"], "damage_category": z["settlement"]["damage_category"]} for z in zs]}


def make_levers(p: ProjectInput):
    """Saving of each decarbonisation lever alone and of the design levers combined, on the project section."""
    plt = _plt()
    from .carbon import assess, strategies
    q = _section(p); rm = assess(q); st = strategies(q, rm)
    lev = st["savings_kgCO2e_per_m"]
    names = {"SCM substitution": "SCM substitution", "Reduce concrete strength": "Lower strength",
             "Reduce lining thickness": "Thinner lining", "Reinforcement / fibre optimisation": "Reinforcement / fibre",
             "Renewable energy for TBM": "Renewable TBM power", "Logistics optimisation (A4 potential)": "Logistics (A4)"}
    rows = sorted(lev.items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(W * 0.72, 2.3))
    ax.barh([names.get(k, k) for k, _ in rows], [100 * v / rm.total_kg_per_m for _, v in rows], 0.56, color=C["s1"])
    ax.barh(["Combined design levers"], [st["combined_pct_of_total"]], 0.56, color=C["s2"])
    ax.set_xlabel("Saving, % of baseline carbon per metre"); _xgrid(ax)
    return fig, {"total_kg_per_m": rm.total_kg_per_m, "savings_kg_per_m": lev,
                 "combined_kg_per_m": st["combined_design_levers_kgCO2e_per_m"], "combined_pct": st["combined_pct_of_total"]}


def make_se_penetration(p: ProjectInput | None = None, d_shield_m: float | None = None, d_rock_m: float | None = None,
                        shield: str | None = None, thrust_mn: float = 15.0):
    """(a) specific energy by component against penetration for a soft-ground shield; (b) against the field
    penetration index for a hard-rock head. Diameters default to the project's."""
    plt = _plt(); import numpy as np
    from . import cutterhead as chd
    D = p.geometry.tbm_diameter_m if p else 7.25
    ds, dr = d_shield_m or D, d_rock_m or D
    fam = shield or (chd.family(p.tbm.machine_type) if p and p.tbm.machine_type else "epb")
    fam = "slurry" if fam == "slurry" else "epb"
    face = chd.Face(p_c_kpa=250, u_kpa=150, sigma_v_eff_kpa=200, cohesion_kpa=10, phi_deg=32, rock_fraction=0.0)
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.5))
    ax = axs[0]; pens = np.linspace(5, 45, 80); A = math.pi / 4 * ds ** 2
    parts = {"thrust": [], "cutting": [], "friction": [], "losses": []}
    q0 = chd.central(fam)
    for pmm in pens:
        r = chd.torque_energy(fam, ds, face, dict(q0, pen_soil_mm=float(pmm)), thrust_mn=thrust_mn)
        k = 2 * math.pi * 1000 / (pmm / 1000) / 3600 / A
        cm = r["components_MNm"]
        parts["thrust"].append(r["thrust_kWh_per_m"] / A); parts["cutting"].append(cm["cutting"] * k)
        parts["friction"].append((cm["face_friction"] + cm["rim"]) * k); parts["losses"].append(cm["mechanical"] * k)
    ax.stackplot(pens, parts["thrust"], parts["cutting"], parts["friction"], parts["losses"],
                 colors=[C["neutral"], C["s1"], C["s2"], C["s3"]], labels=["Thrust", "Cutting", "Friction", "Losses"],
                 edgecolor="white", linewidth=0.4)
    ax.set_xlabel("Penetration per revolution, mm"); ax.set_ylabel("Specific energy, kWh/m$^3$")
    ax.set_xlim(pens[0], pens[-1]); ax.set_ylim(0, None); _ygrid(ax); ax.legend(loc="upper right"); _panel(ax, "a")
    ax = axs[1]; fpis = np.linspace(5, 60, 60); se = []
    for fpi in fpis:
        q = dict(chd.central("hardrock"), fpi_fractured=float(fpi))
        se.append(chd.torque_energy("hardrock", dr, chd.Face(rock_fraction=1, rock_quality="fractured"), q)["specific_energy_kWh_m3"])
    ax.plot(fpis, se, color=C["s3"], lw=1.8)
    ax.set_xlabel("Field penetration index, kN per disc per mm/rev"); ax.set_ylabel("Specific energy, kWh/m$^3$")
    ax.set_ylim(0, None); _ygrid(ax); _panel(ax, "b")
    fig.tight_layout(w_pad=2.5)
    return fig, {"shield": {"family": fam, "D_m": ds, "pen_mm": pens.tolist()} | parts,
                 "hard_rock": {"D_m": dr, "fpi": fpis.tolist(), "se": se}}


# ------------------------------------------------------------------------------------------ optimisation figures
def optimise_zones(p: ProjectInput, thickness_m=(0.30, 0.50), strength_mpa=(40.0, 65.0), install_distance_m=(0.0, 0.0),
                   pop_size: int = 40, n_gen: int = 40, seed: int = 1) -> dict:
    """Optimise each zone for lining carbon subject to the project FoS, keeping the Pareto set of every zone."""
    from .factors import load_library
    from .optimise import OptimiseInput, optimise
    from .route import zone_ground, zone_project
    if not p.route or not p.route.zones:
        raise ValueError("this figure needs a route with ground zones (Step 2)")
    lib = load_library(p.factor_set).with_overrides(p.factor_overrides)
    keys = ("thickness_m", "strength_mpa", "fos", "carbon_kg_per_m")
    zones = []
    for z in sorted(p.route.zones, key=lambda z: z.ch_from):
        oi = OptimiseInput(project=zone_project(p, z), ground=zone_ground(z), algorithm="nsga2", pop_size=pop_size, n_gen=n_gen,
                           thickness_m=tuple(thickness_m), strength_mpa=tuple(strength_mpa),
                           install_distance_m=tuple(install_distance_m), fos_min=p.criteria.fos_min,
                           discrete_grades=True, seed=seed)
        r = optimise(oi, lib); b, rec = r["baseline"], r["recommended"]
        binding = ("FoS" if rec and rec["fos"] < p.criteria.fos_min * 1.05 else
                   "constructability (t_min) and minimum grade" if rec and rec["thickness_m"] < thickness_m[0] + 1e-3 else "other")
        zones.append({"zone": z.name, "ch_from": z.ch_from, "ch_to": z.ch_to, "length_m": z.length_m, "cover_m": z.cover_m,
                      "p0_mpa": z.p0_mpa, "rock_quality": z.rock_quality, "ground_kind": z.ground_kind, "base": {k: b[k] for k in keys},
                      "opt": {k: rec[k] for k in keys} if rec else None, "binding": binding,
                      "pareto": [{k: s[k] for k in keys} for s in r["pareto"]]})
    L = sum(z["length_m"] for z in zones)
    base_t = sum(z["base"]["carbon_kg_per_m"] * z["length_m"] for z in zones) / 1000
    opt_t = sum((z["opt"] or z["base"])["carbon_kg_per_m"] * z["length_m"] for z in zones) / 1000
    worst = max((z for z in zones if z["opt"]), key=lambda z: z["opt"]["carbon_kg_per_m"], default=None)
    return {"design_space": {"thickness_m": list(thickness_m), "grades_mpa": list(strength_mpa), "fos_min": p.criteria.fos_min,
                             "install_distance_m": list(install_distance_m)},
            "zones": zones, "length_m": L, "baseline_lining_t": base_t, "optimised_lining_t": opt_t,
            "saving_t": base_t - opt_t, "saving_pct": 100 * (1 - opt_t / base_t) if base_t else 0.0,
            "uniform_worst_zone_lining_t": worst["opt"]["carbon_kg_per_m"] * L / 1000 if worst else None}


def make_route_optimisation(p: ProjectInput, opt: dict | None = None, **bounds):
    """Lining carbon and factor of safety along the route: uniform baseline and the optimised design of each zone."""
    plt = _plt()
    opt = opt or optimise_zones(p, **bounds); zones = opt["zones"]
    g = p.geometry; base_lab = f"Baseline {g.lining_thickness_m:.2f} m, C{p.concrete.strength_mpa:.0f}"
    fig, axs = plt.subplots(2, 1, figsize=(W, 3.6), sharex=True)
    for key, col, lab in (("base", C["neutral"], base_lab), ("opt", C["s1"], "Optimised by zone")):
        xs, ys, fs = [], [], []
        for z in zones:
            d = z[key] or z["base"]
            xs += [z["ch_from"] / 1000, z["ch_to"] / 1000]; ys += [d["carbon_kg_per_m"] / 1000] * 2; fs += [d["fos"]] * 2
        axs[0].plot(xs, ys, color=col, lw=2 if key == "opt" else 1.5, label=lab, ls="-" if key == "opt" else "--")
        axs[1].plot(xs, fs, color=col, lw=2 if key == "opt" else 1.5, label=lab, ls="-" if key == "opt" else "--")
    for z in zones:
        if z["rock_quality"] == "weak" and z.get("ground_kind", "rock") == "rock":   # fault or weak-rock zones
            for ax in axs:
                ax.axvspan(z["ch_from"] / 1000, z["ch_to"] / 1000, color=C["tan"], alpha=0.45, lw=0)
    axs[0].set_ylabel("Lining, tCO$_2$e/m"); axs[0].set_ylim(0, None); _ygrid(axs[0]); _panel(axs[0], "a")
    axs[0].legend(loc="lower right", ncol=2)
    axs[1].axhline(p.criteria.fos_min, color=C["ink"], lw=0.8, ls="--")
    axs[1].set_yscale("log"); axs[1].set_ylabel("FoS (CCM)"); axs[1].set_xlabel("Chainage, km")
    fmax = max(max(z["base"]["fos"], (z["opt"] or z["base"])["fos"]) for z in zones)
    ticks = [t for t in (1, 1.5, 2, 5, 10, 20, 50, 100) if t <= fmax * 1.5][:6] or [1, 1.5, 2]
    axs[1].set_yticks(ticks, [f"{t:g}" for t in ticks]); axs[1].minorticks_off()
    _ygrid(axs[1]); _panel(axs[1], "b")
    fig.tight_layout(h_pad=1.2)
    return fig, opt


def make_pareto(p: ProjectInput, opt: dict | None = None, zone: str | None = None, **bounds):
    """Pareto set of one zone (by default the zone with the lowest baseline FoS): lining carbon against FoS."""
    plt = _plt()
    opt = opt or optimise_zones(p, **bounds)
    zs = opt["zones"]
    z = next((z for z in zs if z["zone"] == zone), None) if zone else min(zs, key=lambda z: z["base"]["fos"])
    if z is None:
        raise ValueError(f"zone {zone!r} not found")
    pts = z["pareto"]; fos_min = p.criteria.fos_min
    fig, ax = plt.subplots(figsize=(3.6, 2.6))
    ax.axvspan(0, fos_min, color=C["grid"], alpha=0.6, lw=0)
    ax.plot([s["fos"] for s in pts], [s["carbon_kg_per_m"] / 1000 for s in pts], "o", ms=4.5, color=C["s1"], mec="white",
            mew=0.8, label="Pareto set")
    ax.plot(z["base"]["fos"], z["base"]["carbon_kg_per_m"] / 1000, "s", ms=6, color=C["neutral"], mec="white", mew=0.8, label="Baseline")
    if z["opt"]:
        ax.plot(z["opt"]["fos"], z["opt"]["carbon_kg_per_m"] / 1000, "D", ms=6, color=C["s2"], mec="white", mew=0.8, label="Selected")
    ax.axvline(fos_min, color=C["ink"], lw=0.8, ls="--")
    xmax = max([s["fos"] for s in pts] + [z["base"]["fos"]])
    ax.set_xlim(min(0.8, z["base"]["fos"] * 0.9), xmax * 1.05); ax.set_xlabel("FoS (CCM)"); ax.set_ylabel("Lining, tCO$_2$e/m")
    _ygrid(ax); ax.legend(loc="upper left")
    near = sorted((s for s in pts if s["fos"] <= fos_min + 0.25), key=lambda s: s["fos"])
    shadow = ((near[-1]["carbon_kg_per_m"] - near[0]["carbon_kg_per_m"]) / 1000 / (near[-1]["fos"] - near[0]["fos"])
              if len(near) >= 2 and near[-1]["fos"] > near[0]["fos"] else None)
    return fig, {"zone": z["zone"], "points": pts, "baseline": z["base"], "opt": z["opt"], "dcarbon_dfos_t_per_m": shadow}


# ------------------------------------------------------------------------------------------ reference tunnels
def _short(name: str) -> str:
    return name.split(" tunnel")[0].split(" (")[0]


def make_examples(cmp: dict | None = None):
    """Upfront carbon of the four reference tunnels by module, per metre and per cubic metre excavated."""
    plt = _plt()
    from .gisbim import EXAMPLES, compare_examples
    cmp = cmp or compare_examples(); ex = {e["key"]: e for e in cmp["examples"]}; keys = list(EXAMPLES)
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.5))
    mods, cols = ["A1-A3", "A4", "A5"], [C["s1"], C["s2"], C["s3"]]
    for ax, basis, letter in ((axs[0], "m", "a"), (axs[1], "m3", "b")):
        bottom = [0.0] * len(keys)
        for m, col in zip(mods, cols):
            vals = [ex[k]["modules_kgCO2e_per_m"][m] / (1000 if basis == "m" else math.pi / 4 * ex[k]["tbm_diameter_m"] ** 2)
                    for k in keys]
            ax.bar([_short(EXAMPLES[k]["name"]) for k in keys], vals, 0.56, bottom=bottom, color=col, label=m,
                   edgecolor="white", linewidth=0.8)
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_ylabel("tCO$_2$e per m" if basis == "m" else "kgCO$_2$e per m$^3$ excavated"); _ygrid(ax); _panel(ax, letter)
    axs[0].legend(loc="upper left"); fig.tight_layout(w_pad=2.5)
    return fig, {k: {"modules_kg_per_m": ex[k]["modules_kgCO2e_per_m"], "D_m": ex[k]["tbm_diameter_m"]} for k in keys}


def make_cutterhead(cmp: dict | None = None):
    """Specific-energy bands (P10 to P90) and the composition of the cutterhead torque of the four reference tunnels."""
    plt = _plt()
    from .gisbim import EXAMPLES, compare_examples
    cmp = cmp or compare_examples(); ex = {e["key"]: e for e in cmp["examples"]}; keys = list(EXAMPLES)
    lab = {k: _short(EXAMPLES[k]["name"]) for k in keys}
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.4), gridspec_kw={"width_ratios": [1, 1.25]})
    ax = axs[0]
    for i, k in enumerate(keys):
        lo, mid, hi = ex[k]["excavation_energy_band"]["specific_energy_kWh_m3"]
        ax.plot([i, i], [lo, hi], color=C["s1"], lw=2, solid_capstyle="round"); ax.plot(i, mid, "o", ms=6, color=C["s1"], mec="white", mew=1.2)
    ax.set_xticks(range(len(keys)), [lab[k] for k in keys]); ax.set_xlim(-0.5, len(keys) - 0.5)
    ax.set_ylabel("Specific energy, kWh/m$^3$"); ax.set_ylim(0, None); _ygrid(ax); _panel(ax, "a")
    comp = [("cutting", "Cutting"), ("face_friction", "Face"), ("rim", "Rim"), ("mechanical", "Losses")]
    shares = {}
    for k in keys:
        tot = {c: 0.0 for c, _ in comp}
        for z in ex[k]["tbm_by_zone"]:
            cm = (z.get("cutterhead") or {}).get("components_MNm") or {}
            for c, _ in comp:
                tot[c] += cm.get(c, 0.0) * z["length_m"]
        s = sum(tot.values()) or 1.0
        shares[k] = {c: 100 * v / s for c, v in tot.items()}
    ax = axs[1]; left = [0.0] * len(keys)
    for (c, l), col in zip(comp, [C["s1"], C["s2"], C["s3"], C["s4"]]):
        vals = [shares[k][c] for k in keys]
        ax.barh([lab[k] for k in keys], vals, 0.56, left=left, color=col, label=l, edgecolor="white", linewidth=0.8)
        left = [a + b for a, b in zip(left, vals)]
    ax.invert_yaxis(); ax.set_xlim(0, 100); ax.set_xlabel("Share of cutterhead torque, %"); _xgrid(ax)
    ax.legend(ncol=4, loc="lower left", bbox_to_anchor=(0, 1.02), handlelength=1.2, columnspacing=1.0); _panel(ax, "b")
    fig.tight_layout(w_pad=2.5)
    return fig, {"torque_shares_pct": shares, "energy_band": {k: ex[k]["excavation_energy_band"] for k in keys}}



# ------------------------------------------------------------------------------------------ reduction, machines, design space
LEVER_SHORT = {"SCM substitution": "SCM substitution", "Reduce concrete strength": "Lower strength",
               "Reduce lining thickness": "Thinner lining", "Reinforcement / fibre optimisation": "Reinforcement / fibre",
               "Renewable energy for TBM": "Renewable TBM power", "Logistics optimisation (A4 potential)": "Logistics (A4)"}


def make_pathway(p: ProjectInput):
    """Waterfall from the baseline carbon per metre through the design levers in sequence to the residual."""
    plt = _plt()
    from .carbon import assess, strategies
    q = _section(p); rm = assess(q); st = strategies(q, rm)
    total = rm.total_kg_per_m; seq = st["sequence_kgCO2e_per_m"]
    labels = ["Baseline"] + [x["lever"] for x in seq] + ["Residual"]
    fig, ax = plt.subplots(figsize=(W, 2.8))
    level = total
    ax.bar(0, total / 1000, 0.6, color=C["neutral"])
    ax.text(0, total / 1000 * 1.01, f"{total / 1000:,.1f}", ha="center", va="bottom", fontsize=7.5)
    for i, x in enumerate(seq, 1):
        sv = x["saving"]
        ax.bar(i, sv / 1000, 0.6, bottom=(level - sv) / 1000, color=C["s2"])
        ax.plot([i - 1 - 0.3, i + 0.3], [level / 1000] * 2, color=C["ink2"], lw=0.5, ls=(0, (2, 2)))
        ax.text(i, level / 1000 * 1.01, f"$-${100 * sv / total:.0f}%", ha="center", va="bottom", fontsize=7.5, color=C["ink2"])
        level -= sv
    n = len(seq) + 1
    ax.bar(n, level / 1000, 0.6, color=C["s1"])
    ax.text(n, level / 1000 * 1.01, f"{level / 1000:,.1f}  ($-${100 * (1 - level / total):.0f}%)", ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(range(n + 1), labels, rotation=25, ha="right")
    ax.set_ylabel("Upfront carbon, tCO$_2$e per m"); ax.set_ylim(0, total / 1000 * 1.12); _ygrid(ax)
    fig.tight_layout()
    return fig, {"total_kg_per_m": total, "sequence": seq, "residual_kg_per_m": level, "combined_pct": 100 * (1 - level / total),
                 "levers_alone_kg_per_m": st["savings_kgCO2e_per_m"]}


def make_machines(p: ProjectInput):
    """A5 carbon per metre by item for each of the six machine types on the project, with the total per metre and the
    route suitability of each type."""
    plt = _plt(); from matplotlib.patches import Patch
    from .tbm_types import ORDER, TYPES, compare
    cmp = compare(p); rows = {r["type"]: r for r in cmp["types"]}
    keys = [k for k in ORDER if k in rows]
    items = ["TBM excavation energy", "TBM manufacture (allocated)", "Spoil removal", "Slurry circuit (pumping and separation)"]
    cols = [C["s1"], C["s3"], C["s2"], C["s4"]]
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.6), gridspec_kw={"width_ratios": [1.35, 1]})
    ax = axs[0]; bottom = [0.0] * len(keys)
    lab = [TYPES[k].label.replace(" TBM", "").replace(" shield", "") for k in keys]
    present = set()
    for it, col in zip(items, cols):
        vals = [rows[k]["a5_items"].get(it, 0.0) / 1000 for k in keys]
        if any(v > 0 for v in vals):
            present.add(it)
            ax.bar(lab, vals, 0.6, bottom=bottom, color=col, label=it.split(" (")[0], edgecolor="white", linewidth=0.8)
            bottom = [b + v for b, v in zip(bottom, vals)]
    other = [rows[k]["a5_kg_per_m"] / 1000 - b for k, b in zip(keys, bottom)]
    if any(v > 1e-6 for v in other):
        ax.bar(lab, other, 0.6, bottom=bottom, color=C["neutral"], label="Other A5", edgecolor="white", linewidth=0.8)
    ax.set_ylabel("A5, tCO$_2$e per m"); ax.set_ylim(0, max(rows[k]["a5_kg_per_m"] for k in keys) / 1000 * 1.45); _ygrid(ax); _panel(ax, "a")
    ax.legend(fontsize=7, loc="upper left", ncol=2, handlelength=1.0, columnspacing=0.8); ax.tick_params(axis="x", rotation=25)
    for t_ in ax.get_xticklabels():
        t_.set_ha("right")
    rcol = {"suitable": C["s4"], "marginal": C["tan"], "unsuitable": "#6E737B", None: C["neutral"]}
    ax = axs[1]
    ax.barh(lab, [rows[k]["total_kg_per_m"] / 1000 for k in keys], 0.6, color=[rcol[rows[k]["rating"]] for k in keys])
    ax.invert_yaxis(); ax.set_xlabel("Total, tCO$_2$e per m"); _xgrid(ax); ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False); _panel(ax, "b")
    ax.legend(handles=[Patch(color=rcol[k], label=k.capitalize()) for k in ("suitable", "marginal", "unsuitable")],
              loc="lower right", fontsize=7)
    x0 = min(rows[k]["total_kg_per_m"] for k in keys) / 1000
    ax.set_xlim(x0 * 0.9, None)
    fig.tight_layout(w_pad=2.0)
    return fig, {"types": {k: {kk: rows[k][kk] for kk in ("a5_items", "a5_kg_per_m", "total_kg_per_m", "rating", "suitable_share",
                                                          "energy_kWh_per_m", "torque_MNm", "thrust_MN")} for k in keys},
                 "lowest_carbon_suitable": cmp["lowest_carbon_suitable"]}


def make_design_space(p: ProjectInput, zone: str | int | None = None, thickness_m=(0.25, 0.50), strength_mpa=(30.0, 70.0),
                      install_distance_m: float = 0.0, n: int = 41, selected: tuple[float, float] | None = None):
    """Lining carbon per metre (colour) and factor of safety (contours) over thickness and concrete grade for one zone
    (by default the zone with the lowest FoS); the feasible region is where FoS meets the project requirement."""
    plt = _plt(); import numpy as np
    from .ccm import Support, concrete_modulus_v1, solve
    from .factors import load_library
    from .optimise import lining_carbon_kg_per_m
    from .route import assess_route, zone_ground
    if not p.route or not p.route.zones:
        raise ValueError("this figure needs a route with ground zones (Step 2)")
    rt = assess_route(p)
    zsel = (next((z for z in rt["zones"] if z["zone"] == zone), None) if isinstance(zone, str) else
            rt["zones"][zone] if isinstance(zone, int) else min(rt["zones"], key=lambda z: z["fos"]))
    if zsel is None:
        raise ValueError(f"zone {zone!r} not found")
    zname = zsel["zone"]
    z = min(p.route.zones, key=lambda zz: abs(zz.ch_from - zsel["ch_from"]))   # names may repeat; match by chainage
    lib = load_library(p.factor_set).with_overrides(p.factor_overrides)
    g = zone_ground(z); r0 = p.geometry.tbm_diameter_m / 2
    ts = np.linspace(thickness_m[0], thickness_m[1], n); fcs = np.linspace(strength_mpa[0], strength_mpa[1], n)
    FOS = np.zeros((n, n)); CARB = np.zeros((n, n))
    for i, fc in enumerate(fcs):
        for j, t in enumerate(ts):
            r = solve(g, Support(radius_m=r0, thickness_m=float(t), concrete_ucs_mpa=float(fc),
                                 concrete_modulus_mpa=concrete_modulus_v1(float(fc)), install_distance_m=install_distance_m))
            FOS[i, j] = min(r.fos, 50.0) if math.isfinite(r.fos) else 50.0
            CARB[i, j] = lining_carbon_kg_per_m(p, float(t), float(fc), lib) / 1000
    fig, ax = plt.subplots(figsize=(W * 0.72, 2.9))
    im = ax.pcolormesh(ts, fcs, CARB, cmap="Blues", shading="auto", rasterized=True)
    cb = fig.colorbar(im, ax=ax, pad=0.02); cb.set_label("Lining, tCO$_2$e/m"); cb.outline.set_visible(False)
    req = p.criteria.fos_min
    ax.contourf(ts, fcs, FOS, levels=[-1, req], colors=["#6E737B"], alpha=0.35)
    levels = sorted({lv for lv in (0.5, 1, req, 2, 3, 5, 10, 20) if FOS.min() < lv < FOS.max()})
    cs = ax.contour(ts, fcs, FOS, levels=levels, colors=C["ink"], linewidths=[1.4 if lv == req else 0.6 for lv in levels])
    ax.clabel(cs, fmt=lambda v: f"FoS {v:g}", fontsize=7, inline=True)
    ax.plot(p.geometry.lining_thickness_m, p.concrete.strength_mpa, "s", ms=6, color=C["neutral"], mec="white", mew=0.8, label="Baseline")
    if selected:
        ax.plot(selected[0], selected[1], "D", ms=6, color=C["s2"], mec="white", mew=0.8, label="Selected")
    ax.set_xlabel("Lining thickness, m"); ax.set_ylabel("Concrete grade, MPa")
    ax.legend(loc="lower right", fontsize=7.5)
    fig.tight_layout()
    return fig, {"zone": zname, "ch_from": zsel["ch_from"], "fos_min": req, "thickness_m": ts.tolist(), "strength_mpa": fcs.tolist(),
                 "fos": FOS.tolist(), "lining_t_per_m": CARB.tolist()}


# ------------------------------------------------------------------------------------------ more reference-tunnel figures
ELEMENT_GROUPS = [("Lining concrete", ["Lining concrete"]), ("Lining reinforcement", ["Lining reinforcement"]),
                  ("Grout, backfill, fit-out", ["Annulus grout", "Invert backfill", "Fit-out", "Rail, road, pavement or deck"]),
                  ("Transport (A4)", None), ("Spoil removal", ["Spoil removal"]),
                  ("TBM manufacture and transport", ["TBM manufacture (allocated)", "TBM transport"]),
                  ("Excavation energy", ["TBM excavation energy"]), ("Other site (A5)", "rest")]
GCOL = [C["s1"], "#2F5F9E", "#9DBCE0", C["s2"], C["s3"], "#B39DD1", C["s4"], C["neutral"]]


def _grouped(items: dict, a4_keys: set) -> dict:
    used = set(); out = {}
    for name, keys in ELEMENT_GROUPS:
        if keys is None:
            out[name] = sum(v for k, v in items.items() if k in a4_keys); used |= a4_keys
        elif keys == "rest":
            out[name] = sum(v for k, v in items.items() if k not in used)
        else:
            out[name] = sum(items.get(k, 0.0) for k in keys); used |= set(keys)
    return out


def make_examples_composition(cmp: dict | None = None):
    """Upfront carbon per metre of the reference tunnels by element group, and its composition in per cent."""
    plt = _plt()
    from .carbon import assess
    from .gisbim import EXAMPLES, compare_examples, example_project
    cmp = cmp or compare_examples(); ex = {e["key"]: e for e in cmp["examples"]}; keys = list(EXAMPLES)
    lab = [_short(EXAMPLES[k]["name"]) for k in keys]
    groups = {}
    for k in keys:
        a4 = {i.element for i in assess(_section(example_project(k))).items if i.module == "A4"}
        groups[k] = _grouped(ex[k]["items_kgCO2e_per_m"], a4)
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.7), gridspec_kw={"width_ratios": [1, 1]})
    for ax, pct, letter in ((axs[0], False, "a"), (axs[1], True, "b")):
        bottom = [0.0] * len(keys)
        for (name, _), col in zip(ELEMENT_GROUPS, GCOL):
            vals = [groups[k][name] / (ex[k]["kgCO2e_per_m"] / 100 if pct else 1000) for k in keys]
            ax.bar(lab, vals, 0.6, bottom=bottom, color=col, label=name, edgecolor="white", linewidth=0.6)
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_ylabel("Share, %" if pct else "tCO$_2$e per m"); ax.set_ylim(0, 100 if pct else None); _ygrid(ax); _panel(ax, letter)
    axs[1].legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7, handlelength=1.0)
    fig.tight_layout(w_pad=1.5)
    return fig, {k: groups[k] for k in keys}


def make_examples_levers(cmp: dict | None = None):
    """Saving of each lever alone and of the design levers combined, for each reference tunnel."""
    plt = _plt(); import numpy as np
    from .carbon import assess, strategies
    from .gisbim import EXAMPLES, example_project
    keys = list(EXAMPLES); lab = [_short(EXAMPLES[k]["name"]) for k in keys]
    order = ["Reinforcement / fibre optimisation", "SCM substitution", "Reduce concrete strength", "Reduce lining thickness",
             "Renewable energy for TBM", "Logistics optimisation (A4 potential)"]
    data = {}
    for k in keys:
        q = _section(example_project(k)); r = assess(q); st = strategies(q, r)
        data[k] = {"total": r.total_kg_per_m, "pct": {n: 100 * st["savings_kgCO2e_per_m"][n] / r.total_kg_per_m for n in order},
                   "combined_pct": st["combined_pct_of_total"]}
    fig, ax = plt.subplots(figsize=(W, 2.6))
    x = np.arange(len(order) + 1); w = 0.19
    cols = [C["s1"], C["s2"], C["s3"], C["s4"]]
    for i, k in enumerate(keys):
        vals = [data[k]["pct"][n] for n in order] + [data[k]["combined_pct"]]
        ax.bar(x + (i - 1.5) * w, vals, w, color=cols[i], label=lab[i])
    ax.set_xticks(x, [LEVER_SHORT[n] for n in order] + ["Combined design levers"], rotation=20, ha="right")
    ax.set_ylabel("Saving, % of baseline per m"); _ygrid(ax); ax.legend(ncol=4, loc="upper left", fontsize=7.5)
    ax.axvline(len(order) - 0.5, color=C["grid"], lw=0.8)
    fig.tight_layout()
    return fig, data


def make_benchmark(cmp: dict | None = None):
    """Reference tunnels and the published rail exemplar of the toolbox's validation case (Part 3, v1 factors) against
    excavated diameter: (a) upfront carbon per metre, with the area scaling of the Metro tunnel; (b) per cubic metre."""
    plt = _plt(); import json as _json, numpy as np
    from .carbon import apply_machine_type, assess
    from .gisbim import EXAMPLES, compare_examples
    cmp = cmp or compare_examples(); ex = {e["key"]: e for e in cmp["examples"]}; keys = list(EXAMPLES)
    p3 = Path(__file__).parent / "data" / "benchmark_part3_rail.json"   # the toolbox's validation case (docs/PAPERS_TRACEABILITY.md)
    bench = None
    if p3.exists():
        q = ProjectInput.model_validate(_json.loads(p3.read_text()))
        r = assess(apply_machine_type(q), compat_v1=True)
        D = q.geometry.tbm_diameter_m
        bench = {"D_m": D, "kg_per_m": r.total_kg_per_m, "kg_per_m3": r.total_kg_per_m / (math.pi / 4 * D * D),
                 "label": "Published rail exemplar (Part 3, v1 factors)"}
    mk = {"epb": "o", "slurry": "s", "single_shield": "^", "gripper": "v", "double_shield": "D", "multi_mode": "P"}
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.6))
    ax = axs[0]
    Ds = np.linspace(5, 17, 50); m = ex["metro"]
    ax.plot(Ds, m["kgCO2e_per_m"] / 1000 * (Ds / m["tbm_diameter_m"]) ** 2, color=C["neutral"], lw=1, ls=(0, (4, 3)),
            label="Metro scaled with $D^2$")
    off = [(5, 3), (5, -9), (5, -3), (5, -3)]
    for i, k in enumerate(keys):
        e = ex[k]; ax.plot(e["tbm_diameter_m"], e["kgCO2e_per_m"] / 1000, mk.get(e["machine"], "o"), ms=6, color=C["s1"],
                           mec="white", mew=0.8)
        ax.annotate(_short(EXAMPLES[k]["name"]), (e["tbm_diameter_m"], e["kgCO2e_per_m"] / 1000), xytext=off[i % 4],
                    textcoords="offset points", fontsize=7.3)
    if bench:
        ax.plot(bench["D_m"], bench["kg_per_m"] / 1000, "*", ms=9, color=C["s2"], mec="white", mew=0.6, label="Published rail exemplar")
    ax.set_xlabel("Excavated diameter $D$, m"); ax.set_ylabel("tCO$_2$e per m"); ax.set_ylim(0, None); _ygrid(ax); _panel(ax, "a")
    ax.legend(loc="upper left", fontsize=7.3)
    ax = axs[1]
    vals = [ex[k]["kgCO2e_per_m3_excavated"] for k in keys]
    ax.axhspan(min(vals), max(vals), color=C["s1"], alpha=0.12, lw=0, label="Reference-tunnel range")
    for i, k in enumerate(keys):
        e = ex[k]; ax.plot(e["tbm_diameter_m"], e["kgCO2e_per_m3_excavated"], mk.get(e["machine"], "o"), ms=6, color=C["s1"], mec="white", mew=0.8)
        ax.annotate(_short(EXAMPLES[k]["name"]), (e["tbm_diameter_m"], e["kgCO2e_per_m3_excavated"]), xytext=off[i % 4],
                    textcoords="offset points", fontsize=7.3)
    if bench:
        ax.plot(bench["D_m"], bench["kg_per_m3"], "*", ms=9, color=C["s2"], mec="white", mew=0.6)
    ax.set_xlabel("Excavated diameter $D$, m"); ax.set_ylabel("kgCO$_2$e per m$^3$ excavated"); ax.set_ylim(0, max(vals) * 1.25); _ygrid(ax); _panel(ax, "b")
    ax.legend(loc="lower right", fontsize=7.3)
    fig.tight_layout(w_pad=2.5)
    return fig, {"reference": {k: {"D_m": ex[k]["tbm_diameter_m"], "kg_per_m": ex[k]["kgCO2e_per_m"],
                                   "kg_per_m3": ex[k]["kgCO2e_per_m3_excavated"], "machine": ex[k]["machine"]} for k in keys},
                 "published": bench}


def verified_pathway(p: ProjectInput, opt: dict | None = None, pop_size: int = 40, n_gen: int = 40) -> dict:
    """Reduction of the route's upfront carbon per metre in three verified steps: zone-by-zone lining optimisation
    under the project FoS (thickness from the project's thinner-lining lever value to the baseline plus 0.15 m, grades
    C40 to C65, lining at the face), then the material levers that leave the structure unchanged (clinker substitution
    and fibre reinforcement, at the project's lever settings) on the optimised lining, then renewable power for the
    machine. Returns the per-metre totals after each step."""
    from .carbon import assess, concrete_ecf, ring_area, steel_ecf
    from .factors import load_library
    from .route import assess_route
    rt = assess_route(p); L = rt["alignment"]["length_m"]
    items = {k: v * 1000 / L for k, v in rt["items_tCO2e"].items()}
    total = rt["average_kgCO2e_per_m"]
    g, st = p.geometry, p.strategies
    t_lo = min(st.reduced_thickness_m, g.lining_thickness_m)
    opt = opt or optimise_zones(p, thickness_m=(t_lo, g.lining_thickness_m + 0.15), strength_mpa=(40.0, 65.0),
                                install_distance_m=(0.0, 0.0), pop_size=pop_size, n_gen=n_gen)
    lib = load_library(p.factor_set).with_overrides(p.factor_overrides)
    q0 = _section(p); r0 = assess(q0)
    ecf_c0 = r0.intermediate["concrete_ecf_kg_m3"]; ecf_s0 = r0.intermediate["steel_ecf_kg_kg"]
    rho = p.steel.density_kg_m3; ratio = p.steel.reinforcement_ratio_pct / 100
    conc_opt = steel_opt = 0.0
    for z in opt["zones"]:
        d = z["opt"] or z["base"]
        q = q0.model_copy(update={"concrete": q0.concrete.model_copy(update={"strength_mpa": d["strength_mpa"]})})
        ecf_c, _, _ = concrete_ecf(q, lib)
        A = ring_area(g.inner_diameter_m, d["thickness_m"])
        conc_opt += A * ecf_c * z["length_m"] / L
        steel_opt += A * ratio * rho * ecf_s0 * z["length_m"] / L
        A_opt = A
    lining0 = items.get("Lining concrete", 0.0) + items.get("Lining reinforcement", 0.0)
    after_opt = total - lining0 + conc_opt + steel_opt
    f_scm = st.scm_percent * st.ecf_reduction_per_scm_percent / ecf_c0 if ecf_c0 else 0.0
    conc_scm = conc_opt * (1 - f_scm)
    steel_new = sum(ring_area(g.inner_diameter_m, (z["opt"] or z["base"])["thickness_m"]) * st.reduced_reinforcement_pct / 100
                    * rho * st.reduced_steel_ecf * z["length_m"] / L for z in opt["zones"])
    after_mat = after_opt - (conc_opt - conc_scm) - (steel_opt - steel_new)
    exc = items.get("TBM excavation energy", 0.0)
    grid = lib.get(p.tbm.grid_factor_key, "grid.vic").value
    after_energy = after_mat - exc * (1 - st.reduced_grid_factor / grid) if grid else after_mat
    return {"baseline_kg_per_m": total, "after_lining_optimisation": after_opt, "after_material_levers": after_mat,
            "after_renewable_power": after_energy, "lining_saving_pct": 100 * (total - after_opt) / total,
            "total_saving_pct": 100 * (total - after_energy) / total, "design_space": opt["design_space"],
            "min_fos_after": min((z["opt"] or z["base"])["fos"] for z in opt["zones"])}


def make_examples_pathway(paths: dict | None = None):
    """For each reference tunnel, the upfront carbon per metre from the baseline through the verified lining
    optimisation, the material levers and renewable machine power to the residual."""
    plt = _plt(); import numpy as np
    from .gisbim import EXAMPLES, example_project
    keys = list(EXAMPLES); lab = [_short(EXAMPLES[k]["name"]) for k in keys]
    paths = paths or {k: verified_pathway(example_project(k)) for k in keys}
    steps = [("after_lining_optimisation", "Lining optimised zone by zone (FoS verified)", C["s1"]),
             ("after_material_levers", "Clinker substitution and fibre reinforcement", C["s2"]),
             ("after_renewable_power", "Renewable power for the machine", C["s4"])]
    fig, ax = plt.subplots(figsize=(W, 2.9))
    x = np.arange(len(keys))
    res = [paths[k]["after_renewable_power"] / 1000 for k in keys]
    ax.bar(x, res, 0.58, color=C["ink2"], label="Residual")
    prev = res
    for j, (key, name, col) in enumerate(reversed(steps)):
        upper_key = ["baseline_kg_per_m", "after_lining_optimisation", "after_material_levers"][2 - j]
        top = [paths[k][upper_key] / 1000 for k in keys]
        ax.bar(x, [t - b for t, b in zip(top, prev)], 0.58, bottom=prev, color=col, alpha=0.85, label=name, edgecolor="white", linewidth=0.6)
        prev = top
    for i, k in enumerate(keys):
        b, r = paths[k]["baseline_kg_per_m"] / 1000, paths[k]["after_renewable_power"] / 1000
        ax.text(i, b * 1.01, f"$-${100 * (1 - r / b):.0f}%", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x, lab); ax.set_ylabel("Upfront carbon, tCO$_2$e per m"); ax.set_ylim(0, max(paths[k]["baseline_kg_per_m"] for k in keys) / 1000 * 1.12)
    _ygrid(ax); h, l = ax.get_legend_handles_labels(); ax.legend(h[::-1], l[::-1], loc="upper right", fontsize=7.5)
    fig.tight_layout()
    return fig, paths

MAKERS = {"route": make_route, "suitability": make_suitability, "items": make_items, "levers": make_levers,
          "se-penetration": make_se_penetration, "route-optimisation": make_route_optimisation, "pareto": make_pareto,
          "pathway": make_pathway, "machines": make_machines, "design-space": make_design_space,
          "examples": make_examples, "examples-composition": make_examples_composition, "examples-levers": make_examples_levers,
          "benchmark": make_benchmark, "cutterhead": make_cutterhead, "examples-pathway": make_examples_pathway,
          "settlement": make_settlement}


def to_bytes(fig, fmt: str = "pdf", dpi: int = 1000) -> bytes:
    plt = _plt()
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, dpi=dpi if fmt == "png" else None)
    plt.close(fig)
    return buf.getvalue()


def render(name: str, project: ProjectInput | None = None, fmt: str = "pdf", dpi: int = 1000, **opts) -> tuple[bytes, dict]:
    """Figure `name` for `project` as bytes in `fmt`, with the plotted numbers."""
    if name not in MAKERS:
        raise ValueError(f"unknown figure {name!r}; one of {', '.join(MAKERS)}")
    if name in PROJECT_FREE:
        fig, data = MAKERS[name](**opts)
    else:
        if project is None:
            raise ValueError("this figure needs a project")
        fig, data = MAKERS[name](project, **opts)
    return to_bytes(fig, fmt, dpi), data
