"""Input schema for a TBM tunnel carbon assessment.

Defaults reproduce the slicer settings saved in the TunCO2 v1 Power BI file
(see examples/pbix_default_case.json and docs/MIGRATION.md). All quantities are
per metre of tunnel unless stated; totals are scaled by ``tunnel_length_m``.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .alignment import Alignment, GroundZone, default_zones
from .slurry import SlurryCircuit
from .face import FaceSupport
from .settlement import SettlementCriteria


ARTIC = "Road, articulated average (average laden)"


class TransportLeg(BaseModel):
    mode: str = Field(ARTIC, description="Name of a transport factor")
    distance_km: float = Field(60.0, ge=0)


def _default_legs() -> list[TransportLeg]:
    return [TransportLeg()]


class Geometry(BaseModel):
    inner_diameter_m: float = Field(6.6, gt=0, description="Lining internal diameter D_i")
    lining_thickness_m: float = Field(0.30, gt=0, description="Segment thickness t")
    tbm_diameter_m: float = Field(7.28, gt=0, description="Excavated / TBM diameter")
    ring_width_m: float = Field(1.5, gt=0)
    segments_per_ring: int = Field(6, ge=3, le=12, description="Including key segment")
    key_angle_deg: float = Field(22.5, gt=0, lt=90)


class Concrete(BaseModel):
    ecf_mode: Literal["nefd", "database", "user_points", "fixed"] = "nefd"
    nefd_basis: Literal["default", "average"] = Field("default", description="NABERS NEFD default (uncertainty-adjusted) or category average")
    strength_mpa: float = Field(45.0, gt=0, description="Design concrete strength (x0)")
    db_locations: list[str] = ["AUSTRALIA", "UK"]
    db_types: list[str] | None = None
    user_points: list[tuple[float, float]] = [(30, 300), (40, 400), (50, 500)]
    fixed_ecf: float = Field(400.0, ge=0, description="kgCO2e/m3, used when ecf_mode='fixed'")
    density_kg_m3: float = 2500.0


class Steel(BaseModel):
    factor_name: str | None = Field("Reinforcing steel - NEFD default", description="Steel factor from library; None -> user_ecf")
    user_ecf: float = Field(1.99, ge=0, description="kgCO2e/kg")
    reinforcement_ratio_pct: float = Field(1.73, ge=0, le=10, description="% of lining volume")
    density_kg_m3: float = 7800.0


class InvertBackfill(BaseModel):
    include: bool = True
    by: Literal["theta", "chord"] = "theta"
    theta_deg: float = Field(86.0, ge=0, le=360)
    chord_m: float = Field(3.6, ge=0)
    ecf_kg_m3: float | None = Field(None, description="None -> library material.invert_backfill")


class Items(BaseModel):
    include_grout: bool = True
    grout_ecf_kg_m3: float = 200.0
    include_fitout: bool = True
    fitout_quantity_per_m: float = 2.869
    fitout_ecf: float = 1.3
    include_rail_road: bool = True
    rail_road_quantity_per_m: float = 1.0
    rail_road_ecf: float = 1.2


class Transport(BaseModel):
    lining: list[TransportLeg] = Field(default_factory=_default_legs)
    grout: list[TransportLeg] = Field(default_factory=_default_legs)
    backfill: list[TransportLeg] = Field(default_factory=_default_legs)
    fitout: list[TransportLeg] = Field(default_factory=_default_legs)
    rail_road: list[TransportLeg] = Field(default_factory=_default_legs)
    tbm: list[TransportLeg] = Field(default_factory=lambda: [
        TransportLeg(mode=ARTIC, distance_km=40),
        TransportLeg(mode="Road, HGV average (average laden)", distance_km=30)])


class TBMLoads(BaseModel):
    """Parameters for thrust/torque models (v1 'TBM Performance' page)."""
    thrust_model: Literal["empirical", "empirical_type", "regression_pressure", "xie2024", "analytical", "user"] = "analytical"
    torque_model: Literal["empirical", "empirical_type", "regression_pressure", "analytical", "user"] = "analytical"
    tbm_type_torque: str = "Open TBM"
    tbm_type_thrust: str = "EPB TBM"
    soil_type: Literal["Sandy Soil", "Clay"] = "Sandy Soil"
    alpha_t: float = 35.0
    alpha_f: float = 500.0
    user_thrust_mn: float = 20.0
    user_torque_mnm: float = 20.0
    K0: float = 0.6
    gamma: float = 25.0
    H: float = 32.0
    f: float = 0.3
    f_deltap: float = 1.0
    opening: float = 0.7
    kq: float = 0.3
    tau: float = 21.0
    W: float = 0.8
    Db: float = 0.2
    Lb: float = 0.32
    fc_cut: float = 0.3
    Nb: float = 4.0
    Rb: float = 0.1
    K: float = 0.37
    pq: float = 0.0
    hatch: float = 0.3
    H_w: float = 20.0
    pc: float = 300.0
    L: float = 9.0
    G: float = 35000.0
    ns: float = 4.0
    Ws: float = 0.0
    mus: float = 0.25
    mua: float = 0.15
    Wa: float = 0.0
    c: float = 30.0
    rpm: float = Field(3.53, gt=0, description="Cutterhead speed nc [rev/min]")
    lc: float = Field(20.0, gt=0, description="lc in rc = v/(nc*lc)")
    advance_mm_min: float = Field(50.0, gt=0, description="Advance rate v [mm/min]")
    thrust_bound: Literal["mean", "upper", "lower"] = Field("mean", description="xie2024: K0 (upper), Ka (lower) or their mean")
    shield_friction: float = Field(0.2, gt=0, lt=1, description="Shield-ground friction f_TBM-GEO (xie2024): 0.1 soft clay, 0.2 typical, 0.3 sand/gravel")
    shield_length_m: float | None = Field(None, gt=0, description="Shield length L_TBM (xie2024); None -> 1.25 D")
    permeability_m_s: float | None = Field(None, gt=0, description="Ground permeability at the face (xie2024: water separate if >= 5e-5 m/s)")
    mass_t: float | None = Field(None, gt=0, description="Machine mass for shield friction (set from the mass model)")
    support_pressure_kpa: float | None = Field(None, ge=0, description="Chamber support pressure on the face (set per zone from face.py); None -> K0 gamma H")
    energy_method: Literal["forces", "specific_energy", "components"] = Field(
        "components", description="'forces' = thrust + torque work with the torque model below (v1; forced in v1 compatibility); 'specific_energy' = SE x excavated volume (Part 3 method i); "
                              "'components' = cutterhead mechanics (cutterhead.py): torque built from cutting, face and rim friction "
                              "and losses, energy per metre = thrust work + 2 pi T / penetration")
    cutterhead_overrides: dict[str, float] = Field(default_factory=dict, description="'components': central values to replace (see cutterhead.RANGES)")
    cutterhead_rock_quality: Literal["competent", "fractured", "weak"] = Field("fractured", description="'components', single section: rock at the face")
    cutterhead_face: dict | None = Field(None, description="'components': face state set per zone (cutterhead.Face fields)")
    specific_energy_kwh_m3: float = Field(15.0, gt=0, description="Specific energy of excavation, kWh per m3")


class TBM(BaseModel):
    loads: TBMLoads = TBMLoads()
    grid_factor_key: str = "grid.vic"
    machine_type: Literal["gripper", "single_shield", "double_shield", "epb", "slurry", "multi_mode"] | None = Field(
        None, description="One of the six TBM types; None keeps the v1 settings below. See tbm_types.py")
    mass_model: Literal["EPB", "Slurry", "Multi", "user"] = "EPB"
    user_mass_t: float = 1100.0
    ecf_kg_per_kg: float = 1.85
    amortisation_length_m: float = Field(3400.0, gt=0, description="Drive length over which TBM manufacture is allocated")
    spoil_distance_km: float = 100.0
    spoil_mode: str = Field(ARTIC, description="Transport factor for spoil haulage")
    spoil_density_t_m3: float | None = Field(None, description="None -> library material.spoil_density")
    user_defined_a5_kg_per_m: float = 40.0
    aux_power_kw: float = Field(0.0, ge=0, description="Auxiliary plant (ventilation, pumps, conveyors) rated power")
    aux_hours_per_m: float = Field(0.0, ge=0, description="Operating hours of auxiliary plant per metre of tunnel")
    site_diesel_l_per_m: float = Field(0.0, ge=0, description="Site plant diesel per metre (loaders, locos, generators)")
    separation_kwh_per_m3: float = Field(0.0, ge=0, description="Legacy: slurry circuit energy per m3 excavated; > 0 overrides tbm.slurry")
    slurry: SlurryCircuit = Field(default_factory=SlurryCircuit, description="Slurry circuit (slurry and multi-mode machines)")


class Strategies(BaseModel):
    """Decarbonisation levers (v1 'Decarbon Strategy' page)."""
    scm_percent: float = 50.0
    ecf_reduction_per_scm_percent: float = 4.7
    reduced_strength_mode: Literal["strength", "ecf"] = "ecf"
    reduced_strength_mpa: float = 40.0
    reduced_ecf: float = 400.0
    reduced_thickness_m: float = 0.25
    reduced_reinforcement_pct: float = 0.45
    reduced_steel_ecf: float = 2.42
    reduced_grid_factor: float = Field(0.47, ge=0, description="kgCO2e/kWh of the renewable/green supply")


class FunctionalUnit(BaseModel):
    """Part 1 normalisation: per route-km, per track/lane-km, per m2 and m3."""
    kind: Literal["rail", "road", "other"] = "rail"
    count: int = Field(1, ge=1, description="Tracks (rail) or lanes (road) in this bore")


class DesignCriteria(BaseModel):
    fos_min: float = Field(1.5, gt=0, description="ULS: minimum factor of safety of the lining (CCM)")
    u_max_mm: float | None = Field(None, gt=0, description="SLS: maximum radial convergence at equilibrium")
    ec_from_strength: bool = Field(True, description="Ec = 9760.9 fc^0.319 (v1 correlation); else 30 GPa")
    concrete_grades_mpa: list[float] = [25, 32, 40, 50, 65]


class CRS(BaseModel):
    """Project coordinate reference: local metres = projected coordinates minus the origin."""
    epsg: int = Field(32754, description="Projected CRS (UTM south / MGA zones supported)")
    name: str = "WGS 84 / UTM zone 54S"
    origin_easting: float = 500000.0
    origin_northing: float = 6200000.0
    origin_height: float = 0.0
    height_datum: str = ""


class Route(BaseModel):
    alignment: Alignment = Field(default_factory=Alignment)
    zones: list[GroundZone] = Field(default_factory=lambda: default_zones(1000.0))
    crs: CRS | None = Field(None, description="Set when the alignment is georeferenced (local metres about the origin)")
    source: dict | None = Field(None, description="Provenance of an imported corridor (files, registration, assumptions)")


class ProjectInput(BaseModel):
    name: str = "Default case (current factors)"
    factor_set: Literal["current", "v1"] = Field("current", description="'current' = NGA 2026 / NABERS NEFD v2026.2 / DESNZ 2026; 'v1' = TunCO2 v1 values")
    stage: Literal["business_case", "design", "construction"] = "design"
    tunnel_length_m: float = Field(1000.0, gt=0)
    geometry: Geometry = Geometry()
    concrete: Concrete = Concrete()
    steel: Steel = Steel()
    invert: InvertBackfill = InvertBackfill()
    items: Items = Items()
    transport: Transport = Transport()
    tbm: TBM = TBM()
    strategies: Strategies = Strategies()
    factor_overrides: dict[str, float] | None = None
    functional: FunctionalUnit = FunctionalUnit()
    lod: Literal[100, 200, 300, 400, 500] = Field(300, description="Level of detail of the model (Part 1/3)")
    criteria: DesignCriteria = DesignCriteria()
    face: FaceSupport = Field(default_factory=FaceSupport, description="Face support pressure (JSCE) and support-medium friction")
    settlement: SettlementCriteria = Field(default_factory=SettlementCriteria, description="Volume-loss settlement screening (Gaussian trough) and its limits")
    route: Route | None = Field(None, description="Alignment + ground zones; enables route assessment")
