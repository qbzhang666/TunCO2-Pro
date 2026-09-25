"""Generate the four synthetic example corridors shipped with TunCO2 Pro:
Metro, Railway, Road and Hydro tunnels.

    python tools/make_example_corridors.py        # -> src/tunco2pro/data/examples/<case>/

Each case has the three inputs of the GIS -> BIM bridge:
  plan_line.csv       chainage_m, easting, northing, ground_m (every 10 m)
  long_section.json   stations every 5 m: surface, strata (top/base levels), tunnel structure top/base
  crs.json            projected CRS and project origin

Everything is generated from a fixed random seed. The coordinates are fictitious
(WGS 84 / UTM zone 54S, rural land with no tunnels), the terrain and geology are
invented, and the long-section chainage is offset from the plan-line chainage so
that the registration step has something to find (s0 = 300 m in every case).
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "src" / "tunco2pro" / "data" / "examples"
S0 = 300.0          # plan chainage of the first long-section station
LEAD = 300.0        # plan line extends this far beyond the section at both ends


def smooth_noise(rng, s, scale, amp, n=6):
    """Sum of random sinusoids: a smooth, repeatable profile."""
    out = np.zeros_like(s)
    for _ in range(n):
        lam = scale * rng.uniform(0.35, 1.6)
        out += amp / n * 2 * np.sin(2 * math.pi * s / lam + rng.uniform(0, 2 * math.pi))
    return out


# Machine and cross-section per case (set in gisbim.EXAMPLES) are chosen for comparison:
#   Metro and Road: EPB, 7.25 m vs 15.6 m;  Metro vs Railway: both 7.25 m, EPB vs slurry;
#   Hydro: 10.45 m single shield. The generated geology suits each machine.
CASES = {
    "metro": dict(
        title="Metro tunnel (example)", seed=11, ch0=1000.0, length=2200.0, origin=(512000.0, 6184000.0, 40.0),
        heading=58.0, bends=[(0.35, 450.0, 1), (0.75, 600.0, -1)],
        terrain=dict(base=48.0, scale=900, amp=6.0, trend=-4.0),
        axis=[(0.0, 15.0), (0.3, 17.0), (0.55, 21.0), (0.8, 17.0), (1.0, 14.0)], D_ext=6.9,
        strata=[("FILL", 1.0, 3.0), ("ALLUV", 3.0, 8.0), ("SSAND", 4.0, 12.0), ("XW", 3.0, 8.0), ("MW", 6.0, 12.0), ("FR", None, None)],
        channel=(0.62, 420.0, 10.0),     # buried channel: centre (fraction), width (m), extra soil depth (m)
        faults=[]),
    "railway": dict(
        title="Railway tunnel (example)", seed=23, ch0=20000.0, length=4800.0, origin=(538000.0, 6171000.0, 20.0),
        heading=102.0, bends=[(0.45, 1800.0, -1)],
        terrain=dict(base=24.0, scale=2600, amp=5.0, trend=-6.0),
        axis=[(0.0, 14.0), (0.25, 22.0), (0.5, 28.0), (0.8, 22.0), (1.0, 13.0)], D_ext=6.9,
        strata=[("FILL", 1.0, 3.0), ("ALLUV", 2.0, 6.0), ("SAND", 6.0, 16.0), ("GRAVEL", 4.0, 12.0), ("XW", 3.0, 8.0), ("MW", None, None)],
        channel=(0.35, 900.0, 8.0), faults=[]),
    "road": dict(
        title="Road tunnel (example)", seed=37, ch0=5000.0, length=3000.0, origin=(496000.0, 6160000.0, 30.0),
        heading=15.0, bends=[(0.5, 900.0, 1)],
        terrain=dict(base=45.0, scale=1400, amp=12.0, trend=8.0),
        axis=[(0.0, 19.0), (0.3, 24.0), (0.6, 27.0), (1.0, 19.0)], D_ext=15.2,
        strata=[("FILL", 1.0, 2.5), ("CLAY", 3.0, 8.0), ("SSAND", 5.0, 12.0), ("XW", 9.0, 15.0), ("MW", 8.0, 16.0), ("FR", None, None)],
        channel=(0.45, 700.0, 14.0), faults=[]),
    "hydro": dict(
        title="Hydro tunnel (example)", seed=41, ch0=0.0, length=8000.0, origin=(561000.0, 6205000.0, 700.0),
        heading=140.0, bends=[(0.3, 2500.0, 1), (0.7, 3000.0, -1)],
        terrain=dict(base=1050.0, scale=5200, amp=180.0, trend=-250.0),
        axis=[(0.0, 60.0), (0.2, 260.0), (0.5, 450.0), (0.85, 300.0), (1.0, 90.0)], D_ext=10.1,
        strata=[("COLL", 2.0, 8.0), ("MSED", 40.0, 160.0), ("GRN", None, None)],
        channel=None, faults=[(0.27, 90.0), (0.64, 140.0)]),
}


def build(key: str, c: dict) -> None:
    rng = np.random.default_rng(c["seed"])
    L = c["length"]
    # ---- plan line (plan chainage s from 0 to L + 2 LEAD)
    s_plan = np.arange(0.0, L + 2 * LEAD + 1e-6, 10.0)
    curv = np.zeros_like(s_plan)
    for frac, R, sign in c["bends"]:
        centre, width = LEAD + frac * L, 0.12 * L
        curv += sign / R * np.exp(-0.5 * ((s_plan - centre) / (width / 2.5)) ** 2)
    head = math.radians(90 - c["heading"]) + np.concatenate([[0], np.cumsum(0.5 * (curv[1:] + curv[:-1]) * np.diff(s_plan))])
    E0, N0, h0 = c["origin"]
    E = E0 - 0.5 * L * math.cos(head[0]) + np.concatenate([[0], np.cumsum(10.0 * np.cos(0.5 * (head[1:] + head[:-1])))])
    N = N0 - 0.5 * L * math.sin(head[0]) + np.concatenate([[0], np.cumsum(10.0 * np.sin(0.5 * (head[1:] + head[:-1])))])
    t = c["terrain"]
    terr_rng = np.random.default_rng(c["seed"] + 1000)
    terrain = lambda s: t["base"] + t["trend"] * (s / (L + 2 * LEAD) - 0.5) + smooth_noise(np.random.default_rng(c["seed"] + 1000), s, t["scale"], t["amp"])  # noqa: E731
    ground_plan = terrain(s_plan) + terr_rng.normal(0, 0.08, s_plan.size)

    # ---- long section (section chainage CH = ch0 .. ch0 + L, every 5 m)
    ch = np.arange(c["ch0"], c["ch0"] + L + 1e-6, 5.0)
    s = S0 + (ch - c["ch0"])
    surf = terrain(s) + rng.normal(0, 0.05, ch.size)
    frac = (ch - c["ch0"]) / L
    fx, fd = zip(*c["axis"])
    ctrl_rl = [terrain(np.array([S0 + x * L]))[0] - d for x, d in c["axis"]]
    axis = np.interp(frac, fx, ctrl_rl)
    R = c["D_ext"] / 2
    thick = {}
    for name, lo, hi in c["strata"]:
        if lo is not None:
            thick[name] = lo + (hi - lo) * (0.5 + 0.5 * np.tanh(smooth_noise(rng, ch, L * 0.6, 1.2, 4)))
    if c["channel"]:
        cf, w, extra = c["channel"]
        bump = extra * np.exp(-0.5 * ((ch - (c["ch0"] + cf * L)) / (w / 2.5)) ** 2)
        soil = [n for n, lo, hi in c["strata"] if n in ("ALLUV", "SAND", "SSAND", "CLAY", "GRAVEL")]
        thick[soil[-1]] = thick[soil[-1]] + bump
    stations = []
    rock_names = {"XW", "MW", "FR", "SH", "SST", "MSED", "GRN"}
    datum = min(axis) - 3 * c["D_ext"]
    for i, c_ in enumerate(ch):
        top, units = surf[i], []
        in_fault = any(abs(frac[i] - ff) * L < fw / 2 for ff, fw in c["faults"])
        for name, lo, hi in c["strata"]:
            base = top - thick[name][i] if lo is not None else datum
            if base < top - 0.05:
                units.append({"unit": name, "top_rl_m": round(top, 2), "base_rl_m": round(base, 2)})
            top = base
        if in_fault:  # vertical fault zone replaces the rock below the soils
            rock_top = next((u["top_rl_m"] for u in units if u["unit"] in rock_names), None)
            if rock_top is not None:
                units = [u for u in units if u["unit"] not in rock_names] + [{"unit": "FZ", "top_rl_m": rock_top, "base_rl_m": round(datum, 2)}]
        stations.append({"chainage_m": round(float(c_), 2), "surface_rl_m": round(float(surf[i]), 2), "units": units,
                         "structure_top_rl_m": round(float(axis[i] + R), 2), "structure_base_rl_m": round(float(axis[i] - R), 2)})

    d = OUT / key
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "plan_line.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chainage_m", "easting", "northing", "ground_m"])
        for row in zip(s_plan, E, N, ground_plan):
            w.writerow([f"{row[0]:.1f}", f"{row[1]:.2f}", f"{row[2]:.2f}", f"{row[3]:.2f}"])
    ls = {"description": f"{c['title']}: synthetic long section generated by tools/make_example_corridors.py. "
                         "Terrain, geology and alignment are invented for demonstration.",
          "station_spacing_m": 5.0, "sheets": [{"track": "alignment", "chainage_start_m": float(ch[0]),
                                                 "chainage_end_m": float(ch[-1]), "stations": stations}]}
    (d / "long_section.json").write_text(json.dumps(ls, separators=(",", ":")))
    crs = {"description": "Fictitious project origin for the example (WGS 84 / UTM zone 54S).",
           "epsg": 32754, "crs_name": "WGS 84 / UTM zone 54S",
           "origin": {"easting": E0, "northing": N0, "height": h0, "height_datum": "example datum"}}
    (d / "crs.json").write_text(json.dumps(crs, indent=1))
    print(f"{key:8s} plan {s_plan[-1]:.0f} m, section {ch[0]:.0f}-{ch[-1]:.0f}, cover "
          f"{(surf - axis).min():.0f}-{(surf - axis).max():.0f} m")


if __name__ == "__main__":
    for k, v in CASES.items():
        build(k, v)
