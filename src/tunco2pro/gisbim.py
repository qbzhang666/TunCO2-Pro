"""GIS > BIM planning bridge.

Brings a georeferenced corridor (plan line, ground surface and geological long
section) into TunCO2 Pro as a Route - alignment in local metres plus ground
zones derived from the strata the TBM actually cuts - and sends the results
back out as GeoJSON (GIS), a scene file for Blender, and georeferenced IFC 4.3
(IfcMapConversion) for BIM tools.

Frame: local x = grid east - origin E, y = grid north - origin N,
z = height - origin height, with the origin given in the project CRS file.
Keeping large projected coordinates out of the model avoids single-precision
jitter in viewers; any Blender scene or IFC model that uses the same origin
overlays the outputs without transformation.

Formats read:
  * plan line: CSV with chainage (chainage_km or chainage_m), easting, northing,
    and optionally ground level (ground_m / ground_mAHD / ground_rl_m);
  * long section: JSON with sheets[].stations[] holding chainage_m, surface_rl_m,
    units[{unit, top_rl_m, base_rl_m}], and structure_top_rl_m /
    structure_base_rl_m (tunnel extrados) and/or control_line_rl_m;
  * CRS: {"epsg", "crs_name", "origin": {"easting", "northing", "height"}}.

Four synthetic examples (Metro, Railway, Road, Hydro tunnels) are bundled in
data/examples/; see tools/make_example_corridors.py. Blender itself is never
imported here; it reads what this module writes.
"""
from __future__ import annotations

import csv
import io
import json
import math
from importlib import resources
from statistics import median

import numpy as np

from .alignment import Alignment, AlignmentPoint, GroundZone
from .models import CRS, Route

# ---------------------------------------------------------------------------- geodesy
# Transverse Mercator by Krueger's n-series (Karney 2011), GRS80 - sub-millimetre in a UTM/MGA zone.
_A, _F = 6378137.0, 1 / 298.257222101
_N = _F / (2 - _F)
_E = math.sqrt(_F * (2 - _F))
_AR = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALPHA = [_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16 + 41 * _N ** 4 / 180,
          13 * _N ** 2 / 48 - 3 * _N ** 3 / 5 + 557 * _N ** 4 / 1440,
          61 * _N ** 3 / 240 - 103 * _N ** 4 / 140,
          49561 * _N ** 4 / 161280]
_BETA = [_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96 - _N ** 4 / 360,
         _N ** 2 / 48 + _N ** 3 / 15 - 437 * _N ** 4 / 1440,
         17 * _N ** 3 / 480 - 37 * _N ** 4 / 840,
         4397 * _N ** 4 / 161280]
K0, FE, FN = 0.9996, 500000.0, 10000000.0


def _zone(epsg: int) -> int:
    if 7849 <= epsg <= 7859:      # GDA2020 / MGA zones 49-59
        return epsg - 7800
    if 28348 <= epsg <= 28358:    # GDA94 / MGA zones 48-58
        return epsg - 28300
    if 32701 <= epsg <= 32760:    # WGS 84 / UTM south
        return epsg - 32700
    raise ValueError(f"EPSG:{epsg} is not an MGA/UTM south zone")


def lonlat_to_grid(lon: float, lat: float, epsg: int) -> tuple[float, float]:
    lam0 = math.radians(6 * _zone(epsg) - 183)
    phi, dl = math.radians(lat), math.radians(lon) - lam0
    s = math.sin(phi)
    t = math.sinh(math.atanh(s) - _E * math.atanh(_E * s))
    xi_, eta_ = math.atan2(t, math.cos(dl)), math.atanh(math.sin(dl) / math.sqrt(1 + t * t))
    xi = xi_ + sum(a * math.sin(2 * j * xi_) * math.cosh(2 * j * eta_) for j, a in enumerate(_ALPHA, 1))
    eta = eta_ + sum(a * math.cos(2 * j * xi_) * math.sinh(2 * j * eta_) for j, a in enumerate(_ALPHA, 1))
    return FE + K0 * _AR * eta, FN + K0 * _AR * xi


def grid_to_lonlat(e: float, n: float, epsg: int) -> tuple[float, float]:
    lam0 = math.radians(6 * _zone(epsg) - 183)
    xi, eta = (n - FN) / (K0 * _AR), (e - FE) / (K0 * _AR)
    xi_ = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    eta_ = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    tau_ = math.sin(xi_) / math.sqrt(math.sinh(eta_) ** 2 + math.cos(xi_) ** 2)
    tau = tau_
    for _ in range(6):
        sig = math.sinh(_E * math.atanh(_E * tau / math.sqrt(1 + tau * tau)))
        ti = tau * math.sqrt(1 + sig * sig) - sig * math.sqrt(1 + tau * tau)
        tau += (tau_ - ti) / math.sqrt(1 + ti * ti) * (1 + (1 - _E ** 2) * tau * tau) / ((1 - _E ** 2) * math.sqrt(1 + tau * tau))
    return math.degrees(lam0 + math.atan2(math.sinh(eta_), math.cos(xi_))), math.degrees(math.atan(tau))


def local_to_lonlat(x: float, y: float, crs: CRS) -> tuple[float, float]:
    return grid_to_lonlat(x + crs.origin_easting, y + crs.origin_northing, crs.epsg)


def crs_from_json(cfg: dict) -> CRS:
    o = cfg["origin"]
    return CRS(epsg=int(cfg["epsg"]), name=cfg.get("crs_name", ""), origin_easting=o["easting"],
               origin_northing=o["northing"], origin_height=o.get("height", 0.0),
               height_datum=str(o.get("height_datum", "AHD")).split(" ")[0])


# ---------------------------------------------------------------------------- readers
def read_plan_csv(text: str) -> dict:
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("plan line CSV is empty")
    k = {c.lower().strip(): c for c in rows[0]}
    if "chainage_m" in k:
        ch = np.array([float(r[k["chainage_m"]]) for r in rows])
    elif "chainage_km" in k:
        ch = np.array([float(r[k["chainage_km"]]) * 1000 for r in rows])
    else:
        raise ValueError("plan line CSV needs chainage_m or chainage_km")
    E = np.array([float(r[k["easting"]]) for r in rows])
    N = np.array([float(r[k["northing"]]) for r in rows])
    gk = next((k[c] for c in ("ground_m", "ground_mahd", "ground_rl_m", "surface_rl_m") if c in k), None)
    G = np.array([float(r[gk]) for r in rows]) if gk else None
    return {"chainage_m": ch, "E": E, "N": N, "ground": G}


def read_long_section(data: dict | str, track: str = "alignment") -> list[dict]:
    d = json.loads(data) if isinstance(data, str) else data
    rows = {}
    for sh in d.get("sheets", [{"track": track, "stations": d.get("stations", [])}]):
        if sh.get("track", track) != track:
            continue
        for st in sh["stations"]:
            rows.setdefault(float(st["chainage_m"]), st)
    if not rows:
        raise ValueError(f"no stations on track '{track}'")
    return [rows[c] for c in sorted(rows)]


def load_units(csv_text: str | None = None) -> dict[str, dict]:
    if csv_text is None:
        csv_text = (resources.files("tunco2pro") / "data" / "ground_units.csv").read_text(encoding="utf-8")
    out = {}
    for r in csv.DictReader(io.StringIO(csv_text)):
        out[r["unit"]] = {"name": r["name"], "ground_kind": r["ground_kind"], "rock_quality": r["rock_quality"] or None,
                          "unit_weight_kn_m3": float(r["unit_weight_kn_m3"]), "cohesion_mpa": float(r["cohesion_mpa"]),
                          "friction_deg": float(r["friction_deg"]), "modulus_mpa": float(r["modulus_mpa"]),
                          "poisson": float(r["poisson"]), "permeability_m_s": float(r["permeability_m_s"]),
                          "fines_pct": float(r["fines_pct"]) if r.get("fines_pct") not in (None, "") else None,
                          "colour": r.get("colour", ""), "basis": r.get("basis", "")}
    return out


# ---------------------------------------------------------------------------- registration
def register(plan: dict, stations: list[dict], step: float = 1.0) -> dict:
    """Plan-line chainage of each long-section chainage: s = s0 + (CH - CH0), found by
    matching the section's ground surface to the plan line's ground profile
    (least squares after removing the median bias)."""
    if plan["ground"] is None:
        raise ValueError("registration needs ground levels on the plan line")
    ch = np.array([s["chainage_m"] for s in stations], float)
    surf = np.array([s["surface_rl_m"] for s in stations], float)
    rel = ch - ch[0]
    pc, pg = plan["chainage_m"], plan["ground"]

    def rms(s0):
        r = np.interp(s0 + rel, pc, pg) - surf
        return float(np.sqrt(np.mean((r - np.median(r)) ** 2))), float(np.median(r))

    cand = np.arange(pc[0], pc[-1] - rel[-1], 10.0)
    coarse = min(cand, key=lambda s: rms(s)[0])
    fine = np.arange(coarse - 20, coarse + 20 + 1e-9, step / 4)
    s0 = min(fine, key=lambda s: rms(s)[0])
    r, bias = rms(s0)
    return {"s0_m": float(s0), "ch0_m": float(ch[0]), "rms_m": r, "bias_m": bias,
            "method": "ground-surface match of the long section to the plan-line profile"}


# ---------------------------------------------------------------------------- corridor -> route
def face_fractions(units: list[dict], axis: float, radius: float) -> dict[str, float]:
    y = np.linspace(axis - radius, axis + radius, 201)
    w = 2 * np.sqrt(np.maximum(radius ** 2 - (y - axis) ** 2, 0))
    w /= w.sum()
    out: dict[str, float] = {}
    for u in units:
        m = (y <= u["top_rl_m"]) & (y > u["base_rl_m"])
        if m.any():
            out[u["unit"]] = out.get(u["unit"], 0.0) + float(w[m].sum())
    return out


def overburden_stress_kpa(units: list[dict], surface: float, axis: float, props: dict) -> float:
    s = 0.0
    for u in units:
        top, base = min(u["top_rl_m"], surface), max(u["base_rl_m"], axis)
        if top > base:
            s += (top - base) * props.get(u["unit"], {}).get("unit_weight_kn_m3", 20.0)
    return s


def corridor_route(plan: dict, stations: list[dict], crs: CRS, tbm_diameter_m: float, *,
                   ch_from: float | None = None, ch_to: float | None = None, step_m: float = 5.0,
                   min_zone_m: float = 40.0, units: dict | None = None, groundwater_depth_m: float | None = None,
                   axis_from: str = "structure", rail_to_axis_m: float = 1.97, name: str = "Corridor") -> Route:
    units = units or load_units()
    reg = register(plan, stations)
    ch = np.array([s["chainage_m"] for s in stations], float)
    lo, hi = ch_from if ch_from is not None else ch[0], ch_to if ch_to is not None else ch[-1]
    top = np.array([s.get("structure_top_rl_m", np.nan) for s in stations], float)
    base = np.array([s.get("structure_base_rl_m", np.nan) for s in stations], float)
    ctl = np.array([s.get("control_line_rl_m", np.nan) for s in stations], float)
    axis = (top + base) / 2 if axis_from == "structure" else ctl + rail_to_axis_m
    ok = np.isfinite(axis)
    if ok.sum() < 2:
        raise ValueError("long section has no tunnel levels (structure_top/base_rl_m or control_line_rl_m)")
    axis_i = np.interp(ch, ch[ok], axis[ok])
    R = tbm_diameter_m / 2

    # alignment in local metres
    grid = np.arange(lo, hi + 1e-6, step_m)
    if grid[-1] < hi - 1e-6:
        grid = np.r_[grid, hi]
    s = reg["s0_m"] + (grid - reg["ch0_m"])
    E = np.interp(s, plan["chainage_m"], plan["E"]); N = np.interp(s, plan["chainage_m"], plan["N"])
    Z = np.interp(grid, ch, axis_i)
    pts = [AlignmentPoint(x=float(e - crs.origin_easting), y=float(n - crs.origin_northing), z=float(z - crs.origin_height))
           for e, n, z in zip(E, N, Z)]
    al = Alignment(name=name, start_chainage_m=float(grid[0]), points=pts)
    # the alignment's own chainage (3D length) can differ slightly from the drawing's; zones use the drawing's,
    # rescaled onto the alignment so they tile it exactly
    a0, a1 = al.start_chainage_m, al.end_chainage_m
    to_al = lambda c: a0 + (c - grid[0]) / (grid[-1] - grid[0]) * (a1 - a0)  # noqa: E731

    # per station classification
    sel = [i for i, c in enumerate(ch) if lo - 1e-6 <= c <= hi + 1e-6]
    recs = []
    for i in sel:
        st = stations[i]
        fr = face_fractions(st["units"], axis_i[i], R)
        if not fr:
            continue
        dom = max(fr, key=fr.get)
        rock = sum(v for k, v in fr.items() if units.get(k, {}).get("ground_kind") == "rock")
        kind = "rock" if rock >= 0.9 else "soil" if rock <= 0.1 else "mixed"
        recs.append({"ch": ch[i], "dom": dom, "kind": kind, "fr": fr, "surface": st["surface_rl_m"], "axis": axis_i[i],
                     "sv": overburden_stress_kpa(st["units"], st["surface_rl_m"], axis_i[i], units)})
    if not recs:
        raise ValueError("no stations with strata inside the chosen chainage range")

    # runs of the same (dominant unit, kind); absorb short runs into the longer neighbour
    runs = []
    for r in recs:
        key = (r["dom"], r["kind"])
        if runs and runs[-1]["key"] == key:
            runs[-1]["recs"].append(r)
        else:
            runs.append({"key": key, "recs": [r]})
    length = lambda run: run["recs"][-1]["ch"] - run["recs"][0]["ch"] + 1.0  # noqa: E731
    changed = True
    while changed and len(runs) > 1:
        changed = False
        i = min(range(len(runs)), key=lambda j: length(runs[j]))
        if length(runs[i]) < min_zone_m:
            nb = [j for j in (i - 1, i + 1) if 0 <= j < len(runs)]
            j = max(nb, key=lambda j: length(runs[j]))
            a, b = sorted((i, j))
            keep = runs[j]["key"]
            runs[a:b + 1] = [{"key": keep, "recs": runs[a]["recs"] + runs[b]["recs"]}]
            k = 0
            while k < len(runs) - 1:  # re-join neighbours that now match
                if runs[k]["key"] == runs[k + 1]["key"]:
                    runs[k:k + 2] = [{"key": runs[k]["key"], "recs": runs[k]["recs"] + runs[k + 1]["recs"]}]
                else:
                    k += 1
            changed = True

    zones = []
    for n, run in enumerate(runs):
        rs = run["recs"]
        c0 = lo if n == 0 else 0.5 * (runs[n - 1]["recs"][-1]["ch"] + rs[0]["ch"])
        c1 = hi if n == len(runs) - 1 else 0.5 * (rs[-1]["ch"] + runs[n + 1]["recs"][0]["ch"])
        dom, kind = run["key"]
        u = units.get(dom, {})
        cover = median(r["surface"] - r["axis"] for r in rs)
        sv = median(r["sv"] for r in rs)
        fr: dict[str, float] = {}
        for r in rs:
            for k2, v in r["fr"].items():
                fr[k2] = fr.get(k2, 0) + v / len(rs)
        soil_k = [units[k2]["permeability_m_s"] for k2, v in fr.items() if v > 0.05 and units.get(k2, {}).get("ground_kind") == "soil"]
        kperm = max(soil_k) if (kind != "rock" and soil_k) else u.get("permeability_m_s")
        # fines content of the soil in the face, weighted by face area (None for rock-only faces)
        sf = [(v, units[k2]["fines_pct"]) for k2, v in fr.items() if units.get(k2, {}).get("fines_pct") is not None]
        fines = round(sum(v * f for v, f in sf) / sum(v for v, _ in sf), 1) if (kind != "rock" and sf) else None
        wh = None
        if groundwater_depth_m is not None:
            wh = max(0.0, median(r["surface"] - groundwater_depth_m - r["axis"] for r in rs))
        zones.append(GroundZone(
            name=f"{u.get('name', dom)}" + (" - mixed face" if kind == "mixed" else ""),
            ch_from=round(to_al(c0), 3), ch_to=round(to_al(c1), 3), cover_m=round(max(cover, 0.5), 2),
            unit_weight_kn_m3=round(sv / cover, 2) if cover > 0 else u.get("unit_weight_kn_m3", 20),
            cohesion_mpa=u.get("cohesion_mpa", 0.1), friction_deg=u.get("friction_deg", 30),
            modulus_mpa=u.get("modulus_mpa", 500), poisson=u.get("poisson", 0.3),
            ground_kind=kind, rock_quality=u.get("rock_quality") if kind != "soil" else None,
            permeability_m_s=kperm, fines_pct=fines, water_head_m=wh, unit=dom,
            face_fractions={k2: round(v, 3) for k2, v in sorted(fr.items(), key=lambda kv: -kv[1])},
            rock_fraction=round(sum(v for k2, v in fr.items() if units.get(k2, {}).get("ground_kind") == "rock"), 3)))
    src = {"registration": reg, "stations_used": len(recs), "chainage_from_m": float(lo), "chainage_to_m": float(hi),
           "tunnel_level": "mid-height of structure top/base" if axis_from == "structure" else f"control line + {rail_to_axis_m} m",
           "zone_rule": f"dominant unit across a {tbm_diameter_m:g} m face; rock >= 90 % rock, soil <= 10 %, else mixed; "
                        f"runs shorter than {min_zone_m:g} m merged",
           "unit_parameters": sorted({u.get("basis", "") for u in units.values()}),
           "groundwater": "not given - no water head" if groundwater_depth_m is None else f"{groundwater_depth_m} m below surface"}
    return Route(alignment=al, zones=zones, crs=crs, source=src)


# ---------------------------------------------------------------------------- bundled synthetic examples
# The four examples are set up for comparison: Metro vs Road = EPB at two sizes (7.25 m, 15.6 m);
# Metro vs Railway = same 7.25 m, EPB vs slurry; Hydro = 10.45 m single shield in hard rock.
EXAMPLES = {
    "metro": {"groundwater_depth_m": 4.0, "name": "Metro tunnel (example)", "functional": {"kind": "rail", "count": 1}, "machine": "epb",
              "geometry": {"inner_diameter_m": 6.3, "lining_thickness_m": 0.3, "tbm_diameter_m": 7.25, "ring_width_m": 1.5},
              "summary": "2.2 km metro running tunnel, EPB 7.25 m; 11-25 m cover in alluvium, sand and weathered rock."},
    "railway": {"groundwater_depth_m": 3.0, "name": "Railway tunnel (example)", "functional": {"kind": "rail", "count": 1}, "machine": "slurry",
                "geometry": {"inner_diameter_m": 6.3, "lining_thickness_m": 0.3, "tbm_diameter_m": 7.25, "ring_width_m": 1.5},
                "summary": "4.8 km railway tunnel, slurry 7.25 m; 13-30 m cover in water-bearing sand and gravel."},
    "road": {"groundwater_depth_m": 6.0, "name": "Road tunnel (example)", "functional": {"kind": "road", "count": 3}, "machine": "epb",
             "geometry": {"inner_diameter_m": 13.9, "lining_thickness_m": 0.65, "tbm_diameter_m": 15.6, "ring_width_m": 2.0},
             "summary": "3.0 km three-lane road tunnel, EPB 15.6 m; 18-35 m cover in clay, sand and weathered rock."},
    "hydro": {"groundwater_depth_m": 30.0, "name": "Hydro tunnel (example)", "functional": {"kind": "other", "count": 1}, "machine": "single_shield",
              "geometry": {"inner_diameter_m": 9.4, "lining_thickness_m": 0.35, "tbm_diameter_m": 10.45, "ring_width_m": 1.8},
              "summary": "8.0 km hydropower pressure tunnel, single shield 10.45 m; up to 470 m cover in granite and "
                         "metasediments with two fault zones, one of which fails the FoS check.",
              "reference": "Xiao F., Chen X., Zhu Y., Xie P., Salimzadeh S., Zhang Q.B. (2025). Multi-LoD BIM integrated design "
                           "framework for pressurised tunnel: hydro-mechanical coupling simulation and sustainability assessment. "
                           "Tunnelling and Underground Space Technology 158, 106404. doi:10.1016/j.tust.2025.106404"},
}


def example_files(key: str) -> tuple[str, str, dict]:
    base = resources.files("tunco2pro") / "data" / "examples" / key
    return ((base / "plan_line.csv").read_text(encoding="utf-8"), (base / "long_section.json").read_text(encoding="utf-8"),
            json.loads((base / "crs.json").read_text(encoding="utf-8")))


def example_route(key: str, tbm_diameter_m: float | None = None, **kw) -> Route:
    """One of the bundled synthetic corridors (metro, railway, road, hydro)."""
    if key not in EXAMPLES:
        raise ValueError(f"unknown example '{key}'; choose from {', '.join(EXAMPLES)}")
    plan_csv, ls, crs = example_files(key)
    D = tbm_diameter_m or EXAMPLES[key]["geometry"]["tbm_diameter_m"]
    kw.setdefault("groundwater_depth_m", EXAMPLES[key].get("groundwater_depth_m"))
    return corridor_route(read_plan_csv(plan_csv), read_long_section(ls), crs_from_json(crs), D, name=EXAMPLES[key]["name"], **kw)


def example_project(key: str, **kw):
    """A complete ProjectInput for an example: geometry, functional unit, machine, groundwater and route.
    Closed-face machines use the pressure-corrected Part 3 regressions (zone by zone); the single shield the
    Part 3 regressions."""
    from .models import ProjectInput
    ex = EXAMPLES[key]
    route = example_route(key, **kw)
    p = ProjectInput(name=ex["name"])
    geom = p.geometry.model_copy(update={**ex["geometry"], **({"tbm_diameter_m": kw["tbm_diameter_m"]} if kw.get("tbm_diameter_m") else {})})
    # closed-face machines: analytical thrust and torque driven zone by zone by depth, water and the JSCE
    # support pressure (face.py); hard-rock machines: the Part 3 type regressions
    model = "regression_pressure" if ex["machine"] in ("epb", "slurry", "multi_mode") else "empirical_type"
    # thrust of closed-face machines: the BIM-to-Thrust relation of Xie et al. (2024), validated on an EPB and a Mixshield drive
    # excavation energy (and torque) from the cutterhead mechanics (cutterhead.py), zone by zone, with a P10-P90 band
    upd = {"thrust_model": "xie2024" if model == "regression_pressure" else model, "torque_model": model,
           "energy_method": "components"}
    if model != "empirical_type":  # cutterhead speed at the peripheral speed of the 7.25 m default (rpm x D constant)
        upd["rpm"] = round(p.tbm.loads.rpm * 7.25 / ex["geometry"]["tbm_diameter_m"], 2)
    loads = p.tbm.loads.model_copy(update=upd)
    tbm = p.tbm.model_copy(update={"machine_type": ex["machine"], "loads": loads,
                                   "amortisation_length_m": round(route.alignment.length_m, 1)})  # one machine per drive
    # the thinner-lining lever scaled to the example's lining (the default 0.25 m belongs to the 0.30 m default case)
    strat = p.strategies.model_copy(update={"reduced_thickness_m": round(round(geom.lining_thickness_m * 0.25 / 0.30 / 0.05) * 0.05, 2)})
    return p.model_copy(update={"geometry": geom, "tbm": tbm, "route": route, "tunnel_length_m": round(route.alignment.length_m, 1),
                                "functional": p.functional.model_copy(update=ex["functional"]), "strategies": strat})


def _energy_band(zones: list[dict], L: float) -> dict | None:
    """Length-weighted P10 / P50 / P90 of excavation energy (kWh/m) and specific energy (kWh/m3) along the drive.
    Weighting the zone percentiles treats the parameter uncertainty as common to the whole drive (one machine,
    one crew, one conditioning regime), which is the conservative, fully correlated case."""
    zs = [z for z in zones if z.get("cutterhead") and "energy_kWh_per_m_p10_p50_p90" in z["cutterhead"]]
    if not zs:
        return None
    w = lambda key: [sum(z["cutterhead"][key][i] * z["length_m"] for z in zs) / L for i in range(3)]  # noqa: E731
    return {"energy_kWh_per_m": w("energy_kWh_per_m_p10_p50_p90"), "specific_energy_kWh_m3": w("specific_energy_kWh_m3_p10_p50_p90"),
            "torque_MNm": w("torque_MNm_p10_p50_p90")}


def compare_examples(compat_v1: bool = False) -> dict:
    """Assess the four examples on the same factor set and methods, normalised for comparison."""
    import math
    from .carbon import apply_machine_type, assess
    from .route import assess_route
    from .tbm_types import TYPES
    rows = []
    for key, ex in EXAMPLES.items():
        p = example_project(key)
        rt = assess_route(p, compat_v1=compat_v1)
        res = assess(apply_machine_type(p).model_copy(update={"route": None}), compat_v1=compat_v1)
        L = rt["alignment"]["length_m"]
        D = p.geometry.tbm_diameter_m
        a_exc = math.pi / 4 * D ** 2
        per_m = rt["average_kgCO2e_per_m"]
        fu = {"rail": "track-km", "road": "lane-km"}.get(p.functional.kind, "route-km")
        app = rt["tbm_applicability"]
        rows.append({
            "key": key, "name": ex["name"], "machine": ex["machine"], "machine_label": TYPES[ex["machine"]].label,
            "tbm_diameter_m": D, "inner_diameter_m": p.geometry.inner_diameter_m, "lining_thickness_m": p.geometry.lining_thickness_m,
            "length_m": L, "zones": len(rt["zones"]), "total_tCO2e": rt["total_tCO2e"], "kgCO2e_per_m": per_m,
            "kgCO2e_per_m3_excavated": per_m / a_exc, "tCO2e_per_functional_unit": per_m / p.functional.count,
            "functional_unit": fu, "functional_count": p.functional.count,
            "modules_tCO2e": rt["modules_tCO2e"], "modules_kgCO2e_per_m": {k: v * 1000 / L for k, v in rt["modules_tCO2e"].items()},
            "items_kgCO2e_per_m": {k: v * 1000 / L for k, v in rt["items_tCO2e"].items()},
            "items_tCO2e": rt["items_tCO2e"],
            "tbm_by_zone": [{"zone": z["zone"], "thrust_MN": z["thrust_MN"], "torque_MNm": z["torque_MNm"],
                             "energy_kWh_per_m": z["energy_kWh_per_m"], "length_m": z["length_m"],
                             "support_kpa": (z["face_support"] or {}).get("p_control_axis_kpa"),
                             "cutterhead": z.get("cutterhead")} for z in rt["zones"]],
            "excavation_energy_band": _energy_band(rt["zones"], L),
            "min_fos": min((z["fos"] for z in rt["zones"] if z["fos"]), default=None),
            "zones_failing": sum(1 for z in rt["zones"] if not (z["uls_ok"] and z["sls_ok"])),
            "machine_worst_rating": app["worst"][ex["machine"]], "machine_suitable_share": app["share"][ex["machine"]]["suitable"],
            "warnings": rt["warnings"] + res.warnings, "project": p.model_dump(), "reference": ex.get("reference"),
        })
    return {"examples": rows,
            "pairs": [{"compare": ["metro", "road"], "isolates": "size: EPB at 7.25 m vs 15.6 m"},
                      {"compare": ["metro", "railway"], "isolates": "machine: EPB vs slurry at the same 7.25 m"},
                      {"compare": ["hydro"], "isolates": "hard-rock single shield, 10.45 m, deep cover"}],
            "basis": "Same factor set and methods for all. EPB and slurry: thrust by the BIM-to-Thrust relation of Xie et al. "
                     "(2024) zone by zone. Torque and excavation energy for all machines from the cutterhead mechanics (cutterhead.py): "
                     "cutting, face and rim friction in the support medium and losses for shields in soil, disc forces from the field "
                     "penetration index for rock; P10-P90 band from the parameter ranges. Machine mass from the Part 3 "
                     "regressions in tonnes (finding F5 resolved). "
                     "route totals from the zone-by-zone assessment; one machine per drive; slurry circuit energy estimated from first principles (tbm.slurry)."}


# ---------------------------------------------------------------------------- exports
def _ramp(v: float, lo: float, hi: float) -> list[float]:
    t = 0.0 if hi <= lo else min(max((v - lo) / (hi - lo), 0), 1)
    stops = [(0, (0.18, 0.55, 0.34)), (0.5, (0.95, 0.77, 0.25)), (1, (0.80, 0.22, 0.17))]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            return [round(a + (b - a) * u, 3) for a, b in zip(c0, c1)]
    return list(stops[-1][1])


def _zone_polyline(al: Alignment, c0: float, c1: float) -> list[list[float]]:
    c = al.cumulative()
    P = al._arr()
    inner = [P[i].tolist() for i in range(len(c)) if c0 < c[i] < c1]
    return [al.frame(c0)[0].tolist()] + inner + [al.frame(c1)[0].tolist()]


def route_geojson(route: Route, route_result: dict | None = None, applicability: dict | None = None) -> dict:
    """Centreline and zones as GeoJSON (RFC 7946, lon/lat WGS84 ~ GDA2020), with carbon and TBM ratings."""
    if route.crs is None:
        raise ValueError("route is not georeferenced (no CRS)")
    crs = route.crs
    ll = lambda p: [round(v, 8) for v in local_to_lonlat(p[0], p[1], crs)] + [round(p[2] + crs.origin_height, 2)]  # noqa: E731
    al = route.alignment
    feats = [{"type": "Feature", "properties": {"kind": "centreline", "name": al.name, "length_m": al.length_m,
                                                 "crs": f"EPSG:{crs.epsg}", "height_datum": crs.height_datum},
              "geometry": {"type": "LineString", "coordinates": [ll(p) for p in al._arr().tolist()]}}]
    zr = {z["zone_index"]: z for z in (route_result or {}).get("zones", []) if "zone_index" in z}
    zr = zr or {i: z for i, z in enumerate((route_result or {}).get("zones", []))}
    ap = {i: r for i, r in enumerate((applicability or {}).get("zones", []))}
    for i, z in enumerate(route.zones):
        props = {"kind": "zone", "index": i, "zone": z.name, "unit": z.unit, "ground_kind": z.ground_kind,
                 "ch_from": z.ch_from, "ch_to": z.ch_to, "cover_m": z.cover_m}
        if i in zr:
            props.update({k: zr[i].get(k) for k in ("kgCO2e_per_m", "tCO2e", "fos", "u_mob_mm") if k in zr[i]})
        if i in ap:
            props["tbm"] = {t: v["rating"] for t, v in ap[i]["ratings"].items()}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "LineString", "coordinates": [ll(p) for p in _zone_polyline(al, z.ch_from, z.ch_to)]}})
    return {"type": "FeatureCollection", "name": al.name, "features": feats}


TAIL_BEHIND_FACE_D = 14.8 / 10.453  # shield tail behind the face, in diameters (the six Rhino models)


def blender_scene(route: Route, route_result: dict | None, applicability: dict | None, *, tbm_type: str | None,
                  tbm_diameter_m: float, face_chainage_m: float | None = None, project_name: str = "") -> dict:
    """Everything the Blender importer (integrations/blender/tunco2_to_blender.py) needs."""
    al = route.alignment
    zres = (route_result or {}).get("zones", [])
    vals = [z.get("kgCO2e_per_m", 0) for z in zres] or [0]
    lo, hi = min(vals), max(vals)
    zones = []
    for i, z in enumerate(route.zones):
        r = zres[i] if i < len(zres) else {}
        zones.append({"index": i, "name": z.name, "unit": z.unit, "ground_kind": z.ground_kind, "ch_from": z.ch_from,
                      "ch_to": z.ch_to, "cover_m": z.cover_m, "kgCO2e_per_m": r.get("kgCO2e_per_m"), "tCO2e": r.get("tCO2e"),
                      "fos": r.get("fos"), "colour_carbon": _ramp(r.get("kgCO2e_per_m", lo), lo, hi),
                      "tbm": {t: v["rating"] for t, v in (applicability or {"zones": []})["zones"][i]["ratings"].items()}
                      if applicability and i < len(applicability["zones"]) else None,
                      "polyline": [[round(v, 3) for v in p] for p in _zone_polyline(al, z.ch_from, z.ch_to)]})
    # the lining ends at the shield tail: put the face one tail length ahead of the last ring
    tail = TAIL_BEHIND_FACE_D * tbm_diameter_m
    fc = face_chainage_m if face_chainage_m is not None else al.end_chainage_m + tail
    P, T, Nn, U = al.frame(min(fc, al.end_chainage_m))
    P = P + T * max(0.0, fc - al.end_chainage_m)
    return {"format": "tunco2pro-scene", "version": 1, "project": project_name,
            "frame": {"convention": "local metres: x = grid east - origin E, y = grid north - origin N, z = height - origin height; z up",
                      "crs": route.crs.model_dump() if route.crs else None},
            "alignment": {"name": al.name, "start_chainage_m": al.start_chainage_m, "end_chainage_m": al.end_chainage_m,
                          "points": [[round(v, 3) for v in p] for p in al._arr().tolist()]},
            "zones": zones, "carbon_range_kgCO2e_per_m": [lo, hi],
            "tbm": {"type": tbm_type, "model": f"{tbm_type}.glb" if tbm_type else None, "diameter_m": tbm_diameter_m,
                    "model_envelope_m": 10.453, "face_chainage_m": fc, "position": P.tolist(), "direction": T.tolist(),
                    "model_axes": "face at local x = 0, +x = drive, z up"},
            "lining_model": "tunco2pro_route.glb (glTF is y-up: the importer rotates it back to z-up)",
            "source": route.source}
