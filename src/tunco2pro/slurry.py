"""Slurry circuit energy (slurry shields and multi-mode machines in slurry mode).

Not modelled in Part 3 (listed there as a limitation). The estimate is a first-
principles energy balance on the slurry circuit, with every assumption an input:

1. Slurry volume per m3 excavated. The discharge line carries the excavated solids
   at a volumetric concentration set by the feed and discharge densities (the
   excavated mass is recovered from their difference),
       Cv = (rho_d - rho_f) / (rho_solids - rho_f),
   so V_slurry = (1 - n) / Cv per m3 of ground, n = in-situ porosity.
   The feed line carries about the same volume.

2. Pumping. Flow Q = V_slurry x A_exc x advance rate. Darcy-Weisbach friction
   h_f = f (L/Dp) v^2 / 2g over the mean pipeline length L = half the drive plus
   the surface run, in each of the feed and discharge lines; the discharge also lifts
   the denser slurry through the shaft while the feed descends it:
       E_pump = [rho_f g h_f + rho_d g (h_f + z) - rho_f g z] V_slurry / eta_pump.

3. Separation plant. Hydrocyclones: pressure drop x volume treated / eta;
   plus screens, agitators and fines treatment as a user energy per m3 slurry.

The result is kWh per m3 excavated, converted with the project grid factor.
A measured or supplier value can replace it (mode "user").
"""
from __future__ import annotations

import math

from pydantic import AliasChoices, BaseModel, Field

G = 9.81


class SlurryCircuit(BaseModel):
    mode: str = Field("estimate", pattern="^(estimate|user|off)$",
                      description="estimate = energy balance below; user = kWh/m3 entered; off = not included")
    user_kwh_per_m3: float = Field(0.0, ge=0, description="User value, kWh per m3 excavated (mode 'user')")
    rho_feed_t_m3: float = Field(1.10, gt=1.0, lt=2.0, description="Feed slurry density, rho_f")
    rho_discharge_t_m3: float = Field(1.30, gt=1.0, lt=2.2, description="Discharge (loaded) slurry density, rho_d",
                                    validation_alias=AliasChoices("rho_discharge_t_m3", "rho_return_t_m3"))
    rho_solids_t_m3: float = Field(2.65, gt=1.5, lt=3.5, description="Particle density of the excavated ground")
    porosity: float = Field(0.35, ge=0.0, lt=0.9, description="In-situ porosity of the excavated ground")
    pipe_diameter_m: float = Field(0.30, gt=0.05, description="Feed / discharge pipe internal diameter")
    friction_factor: float = Field(0.02, gt=0.0, lt=0.2, description="Darcy friction factor of the slurry lines")
    surface_pipe_m: float = Field(200.0, ge=0, description="Pipeline length on the surface to the plant")
    shaft_lift_m: float = Field(30.0, ge=0, description="Vertical lift from tunnel to plant")
    pump_efficiency: float = Field(0.65, gt=0.1, le=1.0, description="Wire-to-water efficiency of the slurry pumps")
    cyclone_dp_mpa: float = Field(0.20, ge=0, description="Hydrocyclone pressure drop")
    plant_extra_kwh_per_m3_slurry: float = Field(0.0, ge=0, description="Screens, agitators, fines treatment (kWh per m3 slurry)")
    multi_mode_slurry_share: float = Field(0.5, ge=0, le=1, description="Multi-mode machines: share of the drive in slurry mode")


def estimate(s: SlurryCircuit, tbm_diameter_m: float, drive_length_m: float, advance_mm_min: float) -> dict:
    """Energy per m3 excavated and its components."""
    a_exc = math.pi / 4 * tbm_diameter_m ** 2
    cv = (s.rho_discharge_t_m3 - s.rho_feed_t_m3) / (s.rho_solids_t_m3 - s.rho_feed_t_m3)
    if cv <= 0:
        raise ValueError("discharge slurry density must exceed feed density")
    v_slurry = (1 - s.porosity) / cv                        # m3 slurry per m3 excavated (each line)
    q = v_slurry * a_exc * advance_mm_min * 60 / 1000 / 3600  # m3/s
    v = q / (math.pi / 4 * s.pipe_diameter_m ** 2)
    L = drive_length_m / 2 + s.surface_pipe_m
    hf = s.friction_factor * L / s.pipe_diameter_m * v ** 2 / (2 * G)
    rf, rr = s.rho_feed_t_m3 * 1000, s.rho_discharge_t_m3 * 1000
    e_pump_j = (rf * G * hf + rr * G * (hf + s.shaft_lift_m) - rf * G * s.shaft_lift_m) / s.pump_efficiency  # J per m3 slurry
    e_cyc_j = s.cyclone_dp_mpa * 1e6 / s.pump_efficiency
    kwh_slurry = (e_pump_j + e_cyc_j) / 3.6e6 + s.plant_extra_kwh_per_m3_slurry
    return {"kwh_per_m3": kwh_slurry * v_slurry, "slurry_m3_per_m3": v_slurry, "cv": cv, "flow_m3_h": q * 3600,
            "velocity_m_s": v, "friction_head_m": hf, "pumping_kwh_per_m3": e_pump_j / 3.6e6 * v_slurry,
            "separation_kwh_per_m3": (e_cyc_j / 3.6e6 + s.plant_extra_kwh_per_m3_slurry) * v_slurry,
            "mean_pipeline_m": L}
