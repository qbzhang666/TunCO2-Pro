"""Route-level assessment: carbon and stability zone by zone along the alignment."""
from __future__ import annotations

import math

from .tbm_types import route_applicability
from .face import earth_coefficient, zone_support
from .carbon import assess
from .ccm import Ground, Support, concrete_modulus_v1, solve
from .factors import load_library
from .models import ProjectInput, Route
from .optimise import OptimiseInput, optimise
from .settlement import zone_settlement


def zone_project(p: ProjectInput, z) -> ProjectInput:
    q = p.model_copy(deep=True)
    q.tunnel_length_m = max(z.length_m, 1e-6)
    if z.lining_thickness_m:
        q.geometry.lining_thickness_m = z.lining_thickness_m
    if z.concrete_strength_mpa:
        q.concrete.strength_mpa = z.concrete_strength_mpa
    if z.reinforcement_ratio_pct is not None:
        q.steel.reinforcement_ratio_pct = z.reinforcement_ratio_pct
    q.route = None
    if q.tbm.loads.energy_method == "components":
        from .cutterhead import face_from_zone, family
        pc = 0.0 if family(p.tbm.machine_type) == "hardrock" else zone_support(z, q.geometry.tbm_diameter_m, p.face)["p_control_axis_kpa"]
        q.tbm.loads.cutterhead_face = vars(face_from_zone(z, pc))
    # closed-face machines: the zone's depth, water and JSCE support pressure drive the analytical loads
    if p.face.use_in_loads and p.tbm.machine_type in CLOSED_FACE:
        fs = zone_support(z, q.geometry.tbm_diameter_m, p.face)
        L = q.tbm.loads
        L.H, L.gamma, L.H_w = z.cover_m, z.unit_weight_kn_m3, z.water_head_m or 0.0
        L.K, L.K0 = fs["K_e"], earth_coefficient(z.friction_deg, "K0")
        L.pc = L.support_pressure_kpa = fs["p_control_axis_kpa"]
        L.f = p.face.slurry_friction if p.tbm.machine_type == "slurry" else p.face.epb_friction
        # thrust branch by soil: the clay branch where the face is cohesive (fines >= 35 %), else sandy friction
        if z.fines_pct is not None:
            L.soil_type = "Clay" if z.fines_pct >= 35 else "Sandy Soil"
        if z.cohesion_mpa:
            L.c = z.cohesion_mpa * 1000
        L.permeability_m_s = z.permeability_m_s
        # shield-ground friction after Xie et al. (2024, Tables 2-3): 0.1 soft clay, 0.2 typical, 0.3 sand and gravel
        if z.fines_pct is not None:
            L.shield_friction = 0.3 if z.fines_pct < 15 else (0.1 if z.fines_pct >= 60 else 0.2)
    return q


CLOSED_FACE = ("epb", "slurry", "multi_mode")


def _cut_summary(c):
    if not c:
        return None
    keys = ("penetration_mm_rev", "specific_energy_kWh_m3", "components_MNm", "torque_MNm_p10_p50_p90",
            "energy_kWh_per_m_p10_p50_p90", "specific_energy_kWh_m3_p10_p50_p90", "family")
    return {k: c[k] for k in keys if k in c}


def zone_ground(z) -> Ground:
    return Ground(p0_mpa=z.p0_mpa, cohesion_mpa=z.cohesion_mpa, friction_deg=z.friction_deg,
                  modulus_mpa=z.modulus_mpa, poisson=z.poisson)


def zone_stability(p: ProjectInput, z):
    q = zone_project(p, z)
    fc = q.concrete.strength_mpa
    Ec = concrete_modulus_v1(fc) if p.criteria.ec_from_strength else 30000.0
    return solve(zone_ground(z), Support(radius_m=q.geometry.tbm_diameter_m / 2, thickness_m=q.geometry.lining_thickness_m,
                                         concrete_ucs_mpa=fc, concrete_modulus_mpa=Ec,
                                         install_distance_m=z.install_distance_m))


def assess_route(p: ProjectInput, compat_v1: bool = False) -> dict:
    route = p.route or Route()
    al = route.alignment
    zones = sorted(route.zones, key=lambda z: z.ch_from)
    warnings = []
    c0, c1 = al.start_chainage_m, al.end_chainage_m
    covered = sum(max(0.0, min(z.ch_to, c1) - max(z.ch_from, c0)) for z in zones)
    if abs(covered - al.length_m) > 0.5:
        warnings.append(f"Ground zones cover {covered:,.0f} m of a {al.length_m:,.0f} m alignment; check chainages.")
    rows, total_t, mods, items_t = [], 0.0, {"A1-A3": 0.0, "A4": 0.0, "A5": 0.0}, {}
    crit = p.criteria
    for z in zones:
        q = zone_project(p, z)
        r = assess(q, compat_v1=compat_v1)
        fsup = zone_support(z, q.geometry.tbm_diameter_m, p.face) if p.tbm.machine_type in CLOSED_FACE else None
        if fsup and not fsup["within_band"]:
            warnings.append(f"{z.name}: control pressure {fsup['p_control_crown_kpa']:.0f} kPa at the crown exceeds the total "
                            f"vertical stress {fsup['upper_crown_kpa']:.0f} kPa (blow-out/heave bound); shallow cover.")
        s = zone_stability(p, z)
        st = zone_settlement(p, z)
        uls = s.fos >= crit.fos_min
        sls = True if crit.u_max_mm is None else s.u_mob * 1000 <= crit.u_max_mm
        m = r.module_totals_kg_per_m()
        for k in mods:
            mods[k] += m[k] * z.length_m / 1000
        total_t += r.total_t
        for it in r.items:
            items_t[it.element] = items_t.get(it.element, 0.0) + it.kg_per_m * z.length_m / 1000
        rows.append({"zone": z.name, "ch_from": z.ch_from, "ch_to": z.ch_to, "length_m": z.length_m,
                     "cover_m": z.cover_m, "p0_mpa": z.p0_mpa, "thickness_m": q.geometry.lining_thickness_m,
                     "strength_mpa": q.concrete.strength_mpa, "reinforcement_pct": q.steel.reinforcement_ratio_pct,
                     "kgCO2e_per_m": r.total_kg_per_m, "tCO2e": r.total_t,
                     "modules_kgCO2e_per_m": m, "fos": s.fos if math.isfinite(s.fos) else None,
                     "u_mob_mm": s.u_mob * 1000, "plastic_radius_m": s.rp_final,
                     "uls_ok": uls, "sls_ok": sls, "unit": z.unit, "ground_kind": z.ground_kind,
                     "crown_cover_m": z.cover_m - q.geometry.tbm_diameter_m / 2, "face_support": fsup,
                     "thrust_MN": r.intermediate["thrust_MN"], "torque_MNm": r.intermediate["torque_MNm"],
                     "energy_kWh_per_m": r.intermediate["energy_kWh_per_m"],
                     "cutterhead": _cut_summary(r.intermediate.get("cutterhead")),
                     "face_fractions": z.face_fractions, "settlement": st})
        if not uls:
            warnings.append(f"{z.name}: FoS {s.fos:.2f} below {crit.fos_min} (ULS).")
        if not sls:
            warnings.append(f"{z.name}: convergence {s.u_mob*1000:.0f} mm above {crit.u_max_mm} mm (SLS).")
        if not st["s_ok"]:
            warnings.append(f"{z.name}: settlement {st['s_max_mm']:.0f} mm over the axis (volume loss {st['volume_loss_pct']:.2g} %, {st['basis']}) "
                            f"exceeds the {p.settlement.s_max_mm:.0f} mm limit (SLS); a settlement assessment is needed.")
        elif not st["slope_ok"]:
            warnings.append(f"{z.name}: trough slope 1/{1 / st['slope_max']:.0f} is steeper than the 1/{1 / p.settlement.slope_max:.0f} limit (SLS).")
    L = sum(z.length_m for z in zones) or 1.0
    return {"alignment": {"name": al.name, "length_m": al.length_m, "start_chainage_m": c0, "end_chainage_m": c1,
                          "polyline": al.as_polyline(max(al.length_m / 200, 2.0))},
            "zones": rows, "total_tCO2e": total_t, "average_kgCO2e_per_m": total_t * 1000 / L,
            "modules_tCO2e": mods, "items_tCO2e": items_t, "rings": int(L / p.geometry.ring_width_m), "warnings": warnings,
            "tbm_applicability": route_applicability(zones), "georeferenced": route.crs is not None,
            "settlement": {"s_max_mm": max(r["settlement"]["s_max_mm"] for r in rows) if rows else 0.0,
                           "worst_zone": max(rows, key=lambda r: r["settlement"]["s_max_mm"])["zone"] if rows else None,
                           "zones_failing": sum(1 for r in rows if not r["settlement"]["s_ok"]),
                           "damage_category": max((r["settlement"]["damage_category"] for r in rows), default=1)},
            "source": route.source}


def optimise_route(p: ProjectInput, algorithm: str = "nsga2", pop_size: int = 40, n_gen: int = 30,
                   discrete_grades: bool = True) -> dict:
    """Optimise each ground zone separately and report the route-level saving."""
    route = p.route or Route()
    lib = load_library(p.factor_set).with_overrides(p.factor_overrides)
    out, base_t, opt_t = [], 0.0, 0.0
    for z in sorted(route.zones, key=lambda z: z.ch_from):
        q = zone_project(p, z)
        oi = OptimiseInput(project=q, ground=zone_ground(z), algorithm=algorithm, pop_size=pop_size, n_gen=n_gen,
                           fos_min=p.criteria.fos_min, u_max_mm=p.criteria.u_max_mm, discrete_grades=discrete_grades,
                           modulus_from_strength=p.criteria.ec_from_strength)
        res = optimise(oi, lib)
        b = res["baseline"]["carbon_kg_per_m"]
        rec = res["recommended"]
        base_t += b * z.length_m / 1000
        opt_t += (rec["carbon_kg_per_m"] if rec else b) * z.length_m / 1000
        out.append({"zone": z.name, "length_m": z.length_m, "baseline": res["baseline"], "recommended": rec,
                    "feasible": res["feasible"], "pareto_size": len(res["pareto"])})
    return {"zones": out, "baseline_lining_tCO2e": base_t, "optimised_lining_tCO2e": opt_t,
            "saving_tCO2e": base_t - opt_t, "saving_pct": 100 * (1 - opt_t / base_t) if base_t else 0.0}
