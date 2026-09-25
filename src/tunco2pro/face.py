"""Face support pressure for closed-face shields (EPB and slurry), per ground zone.

Control pressure after the Japanese shield-tunnelling specification (JSCE 2016):

    p_control = K_e * sigma'_v + u_w + dp

with K_e = K0 where surface settlement is to be minimised, K_a (or the earth
pressure omitted) where heave is observed ahead of the machine, u_w the
pore-water pressure and dp an allowance for operational fluctuation. K0 from
Jaky's relation, K0 = 1 - sin(phi'); K_a from Rankine. The specification sets
no upper bound; the one adopted here is the total vertical stress at the crown
(blow-out / heave). Face pressure can be optimised within that band, with its
carbon consequence (Bigdeli et al. 2026).

The pressure feeds the analytical thrust and torque models (tbm.py): it is the
chamber pressure on the face and bulkhead, and the cutterhead turns against it
with a friction coefficient that depends on the support medium - high in
conditioned spoil (EPB), low in bentonite slurry. Those coefficients are
defaults to be calibrated against machine records.
"""
from __future__ import annotations

import math

from pydantic import BaseModel, Field

GAMMA_W = 9.81  # kN/m3


class FaceSupport(BaseModel):
    earth_coefficient: str = Field("K0", pattern="^(K0|Ka|none)$",
                                   description="K0 (minimise settlement), Ka (heave observed), none (earth pressure omitted)")
    delta_p_kpa: float = Field(20.0, ge=0, description="Allowance for operational fluctuation, dp")
    epb_friction: float = Field(0.05, gt=0, lt=1, description="Torque rise with chamber pressure, as a medium friction, conditioned "
                                "spoil (EPB); = cutterhead.equivalent_friction('epb') (0.30 before v2.1 overstated the rise 5-13x)")
    slurry_friction: float = Field(0.16, gt=0, lt=1, description="As above, bentonite slurry; = cutterhead.equivalent_friction('slurry')")
    use_in_loads: bool = Field(True, description="Use each zone's support pressure, depth and water head in the analytical thrust/torque models")


def earth_coefficient(phi_deg: float, mode: str) -> float:
    s = math.sin(math.radians(phi_deg))
    if mode == "K0":
        return 1 - s                    # Jaky
    if mode == "Ka":
        return (1 - s) / (1 + s)        # Rankine, cohesion neglected
    return 0.0


def zone_support(z, tbm_diameter_m: float, fs: FaceSupport) -> dict:
    """Support-pressure band at the axis and crown of one zone (kPa)."""
    z0 = z.cover_m
    R = tbm_diameter_m / 2
    zc = max(z0 - R, 0.0)
    gam = z.unit_weight_kn_m3
    u_axis = GAMMA_W * (z.water_head_m or 0.0)
    u_crown = max(0.0, u_axis - GAMMA_W * R)
    Ke = earth_coefficient(z.friction_deg, fs.earth_coefficient)
    sv_axis, sv_crown = gam * z0, gam * zc
    p_axis = Ke * max(sv_axis - u_axis, 0.0) + u_axis + fs.delta_p_kpa
    p_crown = Ke * max(sv_crown - u_crown, 0.0) + u_crown + fs.delta_p_kpa
    return {"K_e": Ke, "earth_coefficient": fs.earth_coefficient, "u_axis_kpa": u_axis, "sigma_v_axis_kpa": sv_axis,
            "p_control_axis_kpa": p_axis, "p_control_crown_kpa": p_crown, "upper_crown_kpa": sv_crown,
            "within_band": p_crown <= sv_crown, "crown_cover_m": zc, "water_assumed": z.water_head_m is not None}
