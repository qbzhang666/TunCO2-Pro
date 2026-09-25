"""EN 15978 A1-A5 embodied carbon for a TBM tunnel (per metre and total).

Ported from the TunCO2 v1 Power BI measures. Where v1 has a unit or logic
problem, the corrected behaviour is the default and ``compat_v1=True``
reproduces v1 exactly so results can be cross-checked against the .pbix.
Each deviation is listed in docs/MIGRATION.md (findings F1-F8).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import tbm as tbm_mod
from .factors import FactorLibrary, fit_user_points, load_library
from .models import ProjectInput, TransportLeg


@dataclass
class LineItem:
    module: str          # "A1-A3" | "A4" | "A5"
    element: str         # e.g. "Lining concrete"
    material_group: str  # NSW-style resource grouping
    kg_per_m: float
    factor_key: str = ""
    nsw_tier: int = 3
    basis: str = ""


@dataclass
class Result:
    project: str
    stage: str
    length_m: float
    items: list[LineItem]
    intermediate: dict
    warnings: list[str] = field(default_factory=list)
    factor_library_version: str = ""
    compat_v1: bool = False

    # ---- aggregates ----
    def module_totals_kg_per_m(self) -> dict[str, float]:
        out = {"A1-A3": 0.0, "A4": 0.0, "A5": 0.0}
        for i in self.items:
            out[i.module] += i.kg_per_m
        return out

    def functional_units(self) -> dict[str, float]:
        """Part 1 normalisations of the A1-A5 total."""
        t = self.total_kg_per_m
        im = self.intermediate
        n = im.get("functional_count", 1) or 1
        unit = {"rail": "track", "road": "lane"}.get(im.get("functional_kind", "other"), "bore")
        return {"tCO2e per route-km": t, f"tCO2e per {unit}-km": t / n,
                "kgCO2e per m2 of internal cross-section per m": t / im["internal_area_m2"],
                "kgCO2e per m3 excavated": t / im["excavated_area_m2"]}

    @property
    def total_kg_per_m(self) -> float:
        return sum(i.kg_per_m for i in self.items)

    @property
    def total_t(self) -> float:
        return self.total_kg_per_m * self.length_m / 1000

    def to_dict(self) -> dict:
        mods = self.module_totals_kg_per_m()
        return {
            "project": self.project,
            "stage": self.stage,
            "length_m": self.length_m,
            "compat_v1": self.compat_v1,
            "factor_library_version": self.factor_library_version,
            "total_kgCO2e_per_m": self.total_kg_per_m,
            "total_tCO2e": self.total_t,
            "total_tCO2e_per_route_km": self.total_kg_per_m,  # kg/m == t/km
            "modules_kgCO2e_per_m": mods,
            "modules_tCO2e": {k: v * self.length_m / 1000 for k, v in mods.items()},
            "functional_units": self.functional_units(),
            "items": [i.__dict__ | {"tCO2e": i.kg_per_m * self.length_m / 1000} for i in self.items],
            "intermediate": self.intermediate,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
def ring_area(D_i: float, t: float) -> float:
    return math.pi / 4 * ((D_i + 2 * t) ** 2 - D_i ** 2)


def annulus_area(D_tbm: float, D_i: float, t: float) -> float:
    return math.pi / 4 * (D_tbm ** 2 - (D_i + 2 * t) ** 2)


def segment_area(D_i: float, theta_deg: float) -> float:
    r = D_i / 2
    th = math.radians(theta_deg)
    return math.pi * r ** 2 * theta_deg / 360 - r ** 2 * math.sin(th / 2) * math.cos(th / 2)


def concrete_ecf(p: ProjectInput, lib: FactorLibrary) -> tuple[float, int, str]:
    c = p.concrete
    if c.ecf_mode == "fixed":
        return c.fixed_ecf, 1, "User-specified ECF (EPD)"
    if c.ecf_mode == "nefd":
        v, basis = lib.nefd_concrete_ecf(c.strength_mpa, c.nefd_basis)
        return v, 2, basis
    if c.ecf_mode == "database":
        s, b, n = lib.concrete_regression(c.db_locations, c.db_types)
        return s * c.strength_mpa + b, 3, f"Regression over {n} database records ({', '.join(c.db_locations)})"
    s, b = fit_user_points(c.user_points)
    return s * c.strength_mpa + b, 2, f"Regression over {len(c.user_points)} user points"


def steel_ecf(p: ProjectInput, lib: FactorLibrary) -> tuple[float, str, int]:
    if p.steel.factor_name:
        f = lib.by_name("steel", p.steel.factor_name)
        return f.value, f.key, f.nsw_tier
    return p.steel.user_ecf, "", 1


def apply_machine_type(p: ProjectInput, force_regressions: bool = False) -> ProjectInput:
    """Settings implied by p.tbm.machine_type (regression keys, mass model)."""
    if not p.tbm.machine_type:
        return p
    from .tbm_types import TYPES
    mt = TYPES[p.tbm.machine_type]
    lu = {"tbm_type_thrust": mt.regression_type, "tbm_type_torque": mt.regression_type}
    if force_regressions:
        lu.update(thrust_model="empirical_type", torque_model="empirical_type")
    tu = {"loads": p.tbm.loads.model_copy(update=lu)}
    if p.tbm.mass_model != "user":
        tu["mass_model"] = mt.mass_model
    return p.model_copy(update={"tbm": p.tbm.model_copy(update=tu)})


def _legs(legs: list[TransportLeg], mass_t: float, lib: FactorLibrary) -> tuple[float, str]:
    kg = 0.0
    parts = []
    for leg in legs:
        if leg.distance_km <= 0:
            continue
        ef = lib.by_name("transport", leg.mode).value
        kg += mass_t * leg.distance_km * ef
        parts.append(f"{leg.mode} {leg.distance_km:g} km")
    return kg, "; ".join(parts)


# ---------------------------------------------------------------------------
def assess(p: ProjectInput, lib: FactorLibrary | None = None, compat_v1: bool = False) -> Result:
    lib = (lib or load_library(p.factor_set)).with_overrides(p.factor_overrides)
    g = p.geometry
    warnings: list[str] = []
    items: list[LineItem] = []

    A_ring = ring_area(g.inner_diameter_m, g.lining_thickness_m)
    A_grout = annulus_area(g.tbm_diameter_m, g.inner_diameter_m, g.lining_thickness_m)
    if A_grout < 0:
        warnings.append("TBM diameter is smaller than lining outer diameter; grout volume set to zero.")
        A_grout = 0.0

    # ---------------- A1-A3 ----------------
    ecf_c, tier_c, basis_c = concrete_ecf(p, lib)
    items.append(LineItem("A1-A3", "Lining concrete", "Concrete", A_ring * ecf_c,
                          "concrete", tier_c, f"{A_ring:.3f} m3/m x {ecf_c:.1f} kgCO2e/m3; {basis_c}"))

    ecf_s, key_s, tier_s = steel_ecf(p, lib)
    steel_kg_per_m = A_ring * p.steel.reinforcement_ratio_pct / 100 * p.steel.density_kg_m3
    items.append(LineItem("A1-A3", "Lining reinforcement", "Steel and other metals", steel_kg_per_m * ecf_s,
                          key_s, tier_s, f"{steel_kg_per_m:.1f} kg/m x {ecf_s} kgCO2e/kg"))

    backfill_vol = 0.0
    if p.invert.include:
        if p.invert.by == "theta":
            theta = p.invert.theta_deg
        else:
            theta = 2 * math.degrees(math.asin(min(1.0, p.invert.chord_m / g.inner_diameter_m)))
        backfill_vol = segment_area(g.inner_diameter_m, theta)
        ef_b = p.invert.ecf_kg_m3 if p.invert.ecf_kg_m3 is not None else lib.get("material.invert_backfill").value
        items.append(LineItem("A1-A3", "Invert backfill", "Concrete", backfill_vol * ef_b,
                              "material.invert_backfill", 3, f"{backfill_vol:.3f} m3/m, theta {theta:.1f} deg"))

    it = p.items
    if it.include_grout:
        items.append(LineItem("A1-A3", "Annulus grout", "Concrete", A_grout * it.grout_ecf_kg_m3, "", 2,
                              f"{A_grout:.3f} m3/m x {it.grout_ecf_kg_m3} kgCO2e/m3"))
    if it.include_rail_road:
        items.append(LineItem("A1-A3", "Rail, road, pavement or deck", "Other resource types",
                              it.rail_road_quantity_per_m * it.rail_road_ecf, "", 2, "quantity x ECF"))
    if it.include_fitout:
        # v1 shows Fitout in the pie but excludes it from the A1-A3 total (finding F6).
        items.append(LineItem("A1-A3", "Fit-out", "Plastics, membranes and roofing",
                              0.0 if compat_v1 else it.fitout_quantity_per_m * it.fitout_ecf, "", 2,
                              "excluded (v1 compat)" if compat_v1 else "quantity x ECF"))

    # ---------------- A4 ----------------
    rho_c = p.concrete.density_kg_m3
    lining_mass_t = (A_ring * rho_c + A_ring * p.steel.reinforcement_ratio_pct / 100 * p.steel.density_kg_m3) / 1000
    for label, legs, mass_t in [
        ("Lining delivery", p.transport.lining, lining_mass_t),
        ("Grout delivery", p.transport.grout, A_grout * rho_c / 1000 if it.include_grout else 0),
        ("Backfill delivery", p.transport.backfill, backfill_vol * rho_c / 1000),
        # v1 treats fit-out and rail/road *quantities* as kg (finding F2)
        ("Fit-out delivery", p.transport.fitout, it.fitout_quantity_per_m / 1000 if it.include_fitout else 0),
        ("Rail/road delivery", p.transport.rail_road, it.rail_road_quantity_per_m / 1000 if it.include_rail_road else 0),
    ]:
        kg, basis = _legs(legs, mass_t, lib)
        items.append(LineItem("A4", label, "Other resource types", kg, "transport.*", 3,
                              f"{mass_t:.3f} t/m; {basis}"))
    if (it.include_fitout or it.include_rail_road) and any(
            l.distance_km > 0 for l in p.transport.fitout + p.transport.rail_road):
        warnings.append("Fit-out and rail/road A4 treat the entered quantity as mass in kg/m (v1 convention).")

    # ---------------- A5 ----------------
    D = g.tbm_diameter_m
    mt = None
    if p.tbm.machine_type:
        from .tbm_types import TYPES
        mt = TYPES[p.tbm.machine_type]
        p = apply_machine_type(p)
        if mt.family == "hard-rock TBM" and "analytical" in (p.tbm.loads.thrust_model, p.tbm.loads.torque_model):
            warnings.append(f"{mt.label}: the analytical thrust/torque models are for closed-face shields in soil; "
                            "use the type regression (empirical_type).")
        if mt.mass_regression_note and p.tbm.mass_model != "user":
            warnings.append(f"{mt.label} mass: {mt.mass_regression_note}; enter the manufacturer mass if known.")
    L = p.tbm.loads
    if not compat_v1 and L.thrust_model == "analytical" and L.soil_type == "Sandy Soil":
        warnings.append("Thrust: the sandy-friction branch of the analytical relation lies above recorded thrust on a "
                        "6.98 m EPB drive, where the clay branch fell inside the record (Xie et al. 2024); treat it as an upper bound.")
    if not compat_v1 and L.thrust_model == "empirical":
        warnings.append("Thrust: Krause's empirical relation lies above recorded EPB thrust (Xie et al. 2024); treat it as an upper bound.")
    if L.thrust_model == "xie2024":
        L = L.model_copy(update={"mass_t": tbm_mod.tbm_mass_kg(p.tbm, D, v1=compat_v1) / 1000})
    thrust = tbm_mod.thrust_mn(L, D)
    torque = tbm_mod.torque_mnm(L, D)
    cut = None
    if L.energy_method == "components" and not compat_v1:
        from . import cutterhead as ch
        fam = ch.family(p.tbm.machine_type)
        cut = ch.evaluate(p.tbm.machine_type, D, ch.face_from_loads(L, fam), thrust, L.cutterhead_overrides)
        torque, energy = cut["torque_MNm"], cut["energy_kWh_per_m"]
        if fam == "hardrock":
            thrust = cut["thrust_kWh_per_m"] * 3.6
    elif L.energy_method == "specific_energy":
        energy = L.specific_energy_kwh_m3 * math.pi / 4 * D ** 2
    else:
        energy = tbm_mod.energy_kwh_per_m(L, D)
    grid = lib.get(p.tbm.grid_factor_key, "grid.vic")
    items.append(LineItem("A5", "TBM excavation energy", "Machinery power", energy * grid.value, grid.key,
                          grid.nsw_tier, f"{energy:.1f} kWh/m x {grid.value} kgCO2e/kWh" + (
                              f" (cutterhead mechanics: T {cut['torque_MNm']:.1f} MN.m at {cut['penetration_mm_rev']:.0f} mm/rev, "
                              f"SE {cut['specific_energy_kWh_m3']:.1f} kWh/m3; P10-P90 {cut['energy_kWh_per_m_p10_p50_p90'][0]:.0f}-"
                              f"{cut['energy_kWh_per_m_p10_p50_p90'][2]:.0f} kWh/m)" if cut else "")))

    mass_kg = tbm_mod.tbm_mass_kg(p.tbm, D, v1=compat_v1)
    items.append(LineItem("A5", "TBM manufacture (allocated)", "Steel and other metals",
                          mass_kg * p.tbm.ecf_kg_per_kg / p.tbm.amortisation_length_m, "", 3,
                          f"{mass_kg/1000:.1f} t x {p.tbm.ecf_kg_per_kg} kgCO2e/kg / {p.tbm.amortisation_length_m:g} m"))

    A_exc = math.pi / 4 * D ** 2
    keys = {f.key for f in lib.all()}
    if compat_v1:
        spoil_ef = lib.value("material.spoil_removal") if "material.spoil_removal" in keys else 0.296
        items.append(LineItem("A5", "Spoil removal", "Other resource types",
                              A_exc * spoil_ef * p.tbm.spoil_distance_km * 1.3, "material.spoil_removal", 3,
                              f"v1 formula: {A_exc:.2f} m3/m x {spoil_ef} x {p.tbm.spoil_distance_km:g} km x 1.3"))
    else:
        if p.tbm.spoil_density_t_m3 is not None:
            rho = p.tbm.spoil_density_t_m3
        elif "material.spoil_density" in keys:
            rho = lib.value("material.spoil_density")
        else:
            rho = 2.8
            warnings.append("Spoil density not in this factor set; 2.8 t/m3 assumed.")
        ef_sp = lib.by_name("transport", p.tbm.spoil_mode)
        items.append(LineItem("A5", "Spoil removal", "Other resource types",
                              A_exc * rho * p.tbm.spoil_distance_km * ef_sp.value, ef_sp.key, ef_sp.nsw_tier,
                              f"{A_exc:.2f} m3/m x {rho:g} t/m3 x {p.tbm.spoil_distance_km:g} km x {ef_sp.value} kgCO2e/t.km"))

    # TBM transport: v1 uses user TBM mass (t) x km x EF x 0.001 and adds it to per-metre A5 (finding F1)
    tbm_mass_t = p.tbm.user_mass_t if p.tbm.mass_model == "user" or compat_v1 else mass_kg / 1000
    kg_total, basis = _legs(p.transport.tbm, tbm_mass_t, lib)
    tbm_tr = kg_total * 0.001 if compat_v1 else kg_total / p.tbm.amortisation_length_m
    items.append(LineItem("A5", "TBM transport", "Other resource types", tbm_tr, "transport.*", 3,
                          ("v1 formula: " if compat_v1 else "allocated per metre: ") + basis))

    sc = p.tbm.slurry
    has_circuit = (mt is not None and mt.slurry_circuit) or (mt is None and p.tbm.mass_model == "Slurry")
    if p.tbm.separation_kwh_per_m3:
        kwh = p.tbm.separation_kwh_per_m3 * A_exc
        items.append(LineItem("A5", "Slurry circuit (user)", "Machinery power", kwh * grid.value, grid.key, 2,
                              f"{p.tbm.separation_kwh_per_m3:g} kWh/m3 x {A_exc:.2f} m3/m x {grid.value} kgCO2e/kWh"))
    elif has_circuit and sc.mode != "off" and not compat_v1:
        share = sc.multi_mode_slurry_share if p.tbm.machine_type == "multi_mode" else 1.0
        tag = f" x {share:g} of drive in slurry mode" if share < 1 else ""
        if sc.mode == "user":
            kwh = sc.user_kwh_per_m3 * A_exc * share
            items.append(LineItem("A5", "Slurry circuit (user)", "Machinery power", kwh * grid.value, grid.key, 2,
                                  f"{sc.user_kwh_per_m3:g} kWh/m3 x {A_exc:.2f} m3/m{tag} x {grid.value} kgCO2e/kWh"))
        else:
            from .slurry import estimate
            e = estimate(sc, D, p.tbm.amortisation_length_m, p.tbm.loads.advance_mm_min)
            items.append(LineItem("A5", "Slurry pumping", "Machinery power", e["pumping_kwh_per_m3"] * A_exc * share * grid.value,
                                  grid.key, 3, f"estimate: {e['slurry_m3_per_m3']:.1f} m3 slurry/m3 (Cv {e['cv']:.2f}), "
                                  f"{e['flow_m3_h']:.0f} m3/h at {e['velocity_m_s']:.1f} m/s, mean line {e['mean_pipeline_m']:.0f} m, "
                                  f"{e['pumping_kwh_per_m3']:.2f} kWh/m3 x {A_exc:.2f} m3/m{tag}"))
            items.append(LineItem("A5", "Slurry separation plant", "Machinery power", e["separation_kwh_per_m3"] * A_exc * share * grid.value,
                                  grid.key, 3, f"estimate: hydrocyclones {sc.cyclone_dp_mpa:g} MPa + {sc.plant_extra_kwh_per_m3_slurry:g} kWh/m3 slurry other plant, "
                                  f"{e['separation_kwh_per_m3']:.2f} kWh/m3 x {A_exc:.2f} m3/m{tag}"))
            warnings.append("Slurry circuit energy is a first-principles estimate (tbm.slurry); replace with a supplier or measured value when available.")

    if p.tbm.aux_power_kw and p.tbm.aux_hours_per_m:
        kwh = p.tbm.aux_power_kw * p.tbm.aux_hours_per_m
        items.append(LineItem("A5", "Auxiliary plant (electric)", "Machinery power", kwh * grid.value, grid.key,
                              grid.nsw_tier, f"{p.tbm.aux_power_kw:g} kW x {p.tbm.aux_hours_per_m:g} h/m x {grid.value} kgCO2e/kWh"))
    if p.tbm.site_diesel_l_per_m:
        dsl = lib.get("fuel.diesel")
        items.append(LineItem("A5", "Site plant diesel", "Machinery power", p.tbm.site_diesel_l_per_m * dsl.value,
                              dsl.key, dsl.nsw_tier, f"{p.tbm.site_diesel_l_per_m:g} L/m x {dsl.value} kgCO2e/L"))

    if p.tbm.user_defined_a5_kg_per_m:
        items.append(LineItem("A5", "Other site emissions (user)", "Other resource types",
                              p.tbm.user_defined_a5_kg_per_m, "", 2, "user-defined"))

    res = Result(p.name, p.stage, p.tunnel_length_m, items,
                 intermediate={
                     "ring_area_m2": A_ring, "excavated_area_m2": math.pi / 4 * D ** 2,
                     "internal_area_m2": math.pi / 4 * g.inner_diameter_m ** 2,
                     "functional_kind": p.functional.kind, "functional_count": p.functional.count, "lod": p.lod, "grout_area_m2": A_grout, "invert_area_m2": backfill_vol,
                     "concrete_ecf_kg_m3": ecf_c, "steel_ecf_kg_kg": ecf_s,
                     "machine_type": p.tbm.machine_type, "tbm_mass_model": p.tbm.mass_model,
                     "thrust_MN": thrust, "torque_MNm": torque, "energy_kWh_per_m": energy, "cutterhead": cut,
                     "tbm_mass_t": mass_kg / 1000, "lining_mass_t_per_m": lining_mass_t,
                 },
                 warnings=warnings + lib.substitutions, factor_library_version=lib.version, compat_v1=compat_v1)
    return res


# ---------------------------------------------------------------------------
def strategies(p: ProjectInput, res: Result, lib: FactorLibrary | None = None, compat_v1: bool = False) -> dict:
    """Carbon savings (kgCO2e/m) of the v1 decarbonisation levers."""
    lib = (lib or load_library(p.factor_set)).with_overrides(p.factor_overrides)
    s = p.strategies
    g = p.geometry
    ecf_c = res.intermediate["concrete_ecf_kg_m3"]
    ecf_s = res.intermediate["steel_ecf_kg_kg"]
    by = {i.element: i.kg_per_m for i in res.items}
    conc = by.get("Lining concrete", 0.0)
    rho_s = 7800.0 if compat_v1 else p.steel.density_kg_m3  # finding F4
    out: dict[str, float] = {}

    out["SCM substitution"] = conc - conc / ecf_c * (ecf_c - s.scm_percent * s.ecf_reduction_per_scm_percent)
    if s.reduced_strength_mode == "ecf":
        new_ecf = s.reduced_ecf
    else:
        c2 = p.concrete.model_copy(update={"strength_mpa": s.reduced_strength_mpa})
        new_ecf, _, _ = concrete_ecf(p.model_copy(update={"concrete": c2}), lib)
    out["Reduce concrete strength"] = conc - conc / ecf_c * new_ecf

    def unit(t, ratio, ecfs):
        return ring_area(g.inner_diameter_m, t) * (ecf_c + ratio / 100 * ecfs * rho_s)
    base = unit(g.lining_thickness_m, p.steel.reinforcement_ratio_pct, ecf_s)
    out["Reduce lining thickness"] = base - unit(s.reduced_thickness_m, p.steel.reinforcement_ratio_pct, ecf_s)
    out["Reinforcement / fibre optimisation"] = base - unit(g.lining_thickness_m, s.reduced_reinforcement_pct, s.reduced_steel_ecf)

    exc = by.get("TBM excavation energy", 0.0)
    grid = lib.get(p.tbm.grid_factor_key, "grid.vic").value
    grid_ren = 0.86 if (compat_v1 and p.tbm.grid_factor_key == "grid.vic") else grid  # finding F3
    tbm_res = exc + by.get("TBM manufacture (allocated)", 0.0)
    # reduced_grid_factor = emission factor of the (partly) renewable supply, kgCO2e/kWh
    if compat_v1:
        out["Renewable energy for TBM"] = tbm_res - tbm_res / grid_ren * s.reduced_grid_factor
    else:
        out["Renewable energy for TBM"] = exc * (1 - s.reduced_grid_factor / grid)
    out["Logistics optimisation (A4 potential)"] = sum(i.kg_per_m for i in res.items if i.module == "A4")

    # Combined (sequential) application of the design levers on the lining and TBM energy.
    # Each lever acts on what remains after the previous one, so the sum is not double-counted.
    A0 = ring_area(g.inner_diameter_m, g.lining_thickness_m)
    A1 = ring_area(g.inner_diameter_m, min(s.reduced_thickness_m, g.lining_thickness_m))
    ecf_scm = new_ecf * (1 - s.scm_percent * s.ecf_reduction_per_scm_percent / ecf_c) if ecf_c else new_ecf
    conc_new = A1 * max(ecf_scm, 0.0)
    steel_new = A1 * s.reduced_reinforcement_pct / 100 * rho_s * s.reduced_steel_ecf
    steel_old = by.get("Lining reinforcement", 0.0)
    exc_new = exc * (s.reduced_grid_factor / grid) if grid else exc
    combined = (conc - conc_new) + (steel_old - steel_new) + (exc - exc_new)
    # the same sequence lever by lever, each acting on what the previous one left (for the reduction pathway)
    c1 = conc / ecf_c * new_ecf if ecf_c else conc
    c2 = conc / ecf_c * ecf_scm if ecf_c else conc
    c3, s3 = c2 * A1 / A0, steel_old * A1 / A0
    sequence = [("Lower strength", conc - c1), ("SCM substitution", c1 - c2), ("Thinner lining", (c2 - c3) + (steel_old - s3)),
                ("Reinforcement / fibre", s3 - steel_new), ("Renewable TBM power", exc - exc_new)]
    out_combined = {"combined_design_levers_kgCO2e_per_m": combined,
                    "sequence_kgCO2e_per_m": [{"lever": k, "saving": v} for k, v in sequence],
                    "combined_pct_of_total": 100 * combined / res.total_kg_per_m if res.total_kg_per_m else 0.0,
                    "combined_basis": "Lower strength + SCM + thinner lining + reinforcement/fibre + renewable supply, applied in sequence"}

    checks = []
    if out["SCM substitution"] + out["Reduce concrete strength"] + out["Reduce lining thickness"] >= conc:
        checks.append("Concrete savings exceed lining concrete carbon: levers overlap; check inputs.")
    if out["Reinforcement / fibre optimisation"] >= by.get("Lining reinforcement", 0) + conc:
        checks.append("Reinforcement saving exceeds lining carbon; check inputs.")
    return {"savings_kgCO2e_per_m": out, "checks": checks, **out_combined,
            "note": "Bars show each lever on its own (not additive); the combined figure applies the design levers in sequence."}
