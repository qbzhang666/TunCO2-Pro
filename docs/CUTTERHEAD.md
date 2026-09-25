# Cutterhead mechanics: torque, excavation energy and their ranges

`energy_method = "components"` (module `cutterhead.py`) builds the cutterhead torque from what resists the head
turning, and the excavation energy from the work done per metre of advance. The parameters are given as
(low, central, high) because they change from project to project with the ground, the conditioning, the head
design and the way the machine is driven. A triangular Monte Carlo over the ranges gives P10 / P50 / P90 torque
and energy for every zone; the carbon uses the central set (or your overrides in `tbm.loads.cutterhead_overrides`).

## 1. Energy per metre

    E = F · 1 m + 2π T / p          p = penetration per revolution (m/rev)
    SE = E / A                      A = π D² / 4

Every torque term that does not grow with penetration (friction in the support medium, bearings and seals) is
paid once per revolution. Its share of the energy therefore rises as penetration falls, which is why the
specific energy of a shield rises steeply in slow, stiff or sticky ground even though the cutting work itself
is small. The thrust work F·1 m is typically 5-15 % of the total.

## 2. Soft-ground shields (EPB, slurry, multi-mode)

    T_cut  = e_c A p / (2π)                        tools cutting the face, e_c = κ τ_f,  τ_f = c + σ'v tan φ
    T_face = n_f (1 − ξ) (2π/3) R³ τ_m             closed part of the face (ξ = opening ratio) and, in a full
                                                    chamber, the bulkhead side (n_f up to 2)
    T_rim  = π D W R τ_m                           gauge / rim of width W turning in the overcut
    T      = (T_cut + T_face + T_rim) / (1 − η)    η = bearing, seal and gearbox losses

The medium in contact with the steel sets τ_m:

* **EPB**: the chamber holds conditioned spoil, a plastic paste: τ_m = τ₀ + tan δ (p_c − u). τ₀ is the
  undrained strength of the paste (target consistency 5-25 kPa). Because the paste is near-saturated and
  foam-lubricated, only a small fraction of the effective chamber stress p_c − u mobilises friction (tan δ 0.01-0.10);
  torque therefore rises only weakly with support pressure. Poor conditioning or clogging clay moves both to the
  top of the range, or beyond it.
* **Slurry**: the chamber holds bentonite suspension whose yield stress is tens of pascals. The resistance is
  the drag of the slurry-spoil mixture on spokes and in the chamber invert where coarse spoil settles (τ_s), plus
  the part of the closed face ψ that bears on the ground through the filter cake:
  τ_m = τ_s + ψ tan δ_s max(p_c − u, Δσ_min). Slurry torque is thus well below EPB torque at the same diameter.
* **Mixed faces**: penetration and cutting energy are weighted by the rock share of the face (from the
  long-section face fractions): p = (1 − r) p_soil + r p_rock; e_c = (1 − r) e_c,soil + r e_c,rock.

Because the friction terms scale with R³, torque grows with about D³ (about 10× from 7.25 m to 15.6 m), and the
specific energy of friction with about D.

## 3. Hard-rock heads (discs)

    F_n = FPI · p      per disc, with p = min(F_n,op / FPI, p_cap)
    CC  = tan(φ/2),    cos φ = (R_d − p) / R_d    rolling / normal force ratio of a disc
    N_c = R / s + 8    face tracks at spacing s plus gauge discs
    T   = CC N_c F_n r̄ R / (1 − η),   F = N_c F_n

The field penetration index FPI (kN per disc per mm/rev) carries the rock: competent massive rock needs high
force per millimetre, so penetration is low and specific energy high; fractured rock the reverse. In weak and
faulted rock penetration is capped by torque and muck handling (p_cap), not by the discs.

## 4. Parameter ranges and their basis

### EPB (and multi-mode in EPB mode)

| Parameter | Low | Central | High | Physical basis |
|---|---:|---:|---:|---|
| `opening` | 0.25 | 0.35 | 0.45 | open area of soft-ground heads; mixed-ground heads nearer the low end |
| `n_faces` | 1.5 | 1.8 | 2 | face plus bulkhead side in paste; <2 where the chamber is not full |
| `tau0_kpa` | 4 | 8 | 20 | undrained shear strength of conditioned spoil (plastic paste); central value calibrated on operating records of a large-diameter EPB drive |
| `tan_delta` | 0.01 | 0.02 | 0.06 | friction on effective chamber stress; foam keeps it small, clogging raises it; central value from the recorded torque-pressure slope of the same drive |
| `rim_w_over_d` | 0.05 | 0.07 | 0.09 | gauge / rim width relative to diameter |
| `kappa` | 2 | 3 | 5 | cutting energy per m3 as a multiple of the ground's shear strength (drag tools) |
| `pen_soil_mm` | 10 | 20 | 35 | penetration per revolution in soil |
| `pen_rock_mm` | 5 | 10 | 20 | penetration per revolution where the face is weak rock |
| `eta_mech` | 0.05 | 0.08 | 0.12 | bearing, seal and gearbox losses |
| `ec_rock_factor` | 0.6 | 1 | 1.5 | scatter of rock cutting energy (discs on a mixed-ground head) about EC_ROCK_KJ_M3 |

### Slurry

| Parameter | Low | Central | High | Physical basis |
|---|---:|---:|---:|---|
| `opening` | 0.25 | 0.35 | 0.45 | open area |
| `n_faces` | 1 | 1.2 | 1.5 | face side; bulkhead side partly in slurry |
| `psi` | 0.1 | 0.2 | 0.3 | share of the closed face bearing on the ground through the filter cake |
| `tau_s_kpa` | 2 | 5 | 10 | drag of the slurry-spoil mixture on spokes and settled spoil in the chamber invert |
| `tan_delta` | 0.3 | 0.4 | 0.5 | steel-soil friction at the face |
| `min_sigma_kpa` | 10 | 20 | 40 | effective face support at least the overpressure margin |
| `rim_w_over_d` | 0.05 | 0.07 | 0.09 | gauge / rim width relative to diameter |
| `kappa` | 2 | 3 | 5 | cutting energy as a multiple of shear strength |
| `pen_soil_mm` | 15 | 25 | 40 | penetration per revolution in sand and gravel |
| `pen_rock_mm` | 5 | 10 | 20 | penetration per revolution in weak rock |
| `eta_mech` | 0.05 | 0.08 | 0.12 | bearing, seal and gearbox losses |
| `ec_rock_factor` | 0.6 | 1 | 1.5 | scatter of rock cutting energy about EC_ROCK_KJ_M3 |

### Hard rock (gripper, single and double shield)

| Parameter | Low | Central | High | Physical basis |
|---|---:|---:|---:|---|
| `disc_radius_m` | 0.216 | 0.241 | 0.254 | 17-20 inch discs |
| `spacing_mm` | 75 | 85 | 95 | track spacing |
| `fn_kn` | 200 | 250 | 300 | operating normal force per disc (80-90 % of rating) |
| `fpi_competent` | 25 | 40 | 60 | field penetration index, kN/cutter per mm/rev, competent massive rock |
| `fpi_fractured` | 12 | 22 | 35 | FPI in jointed / blocky rock |
| `fpi_weak` | 4 | 8 | 15 | FPI in weak or faulted rock (penetration then limited by torque and muck) |
| `pen_cap_mm` | 10 | 15 | 20 | operational cap on penetration per revolution |
| `r_bar` | 0.5 | 0.55 | 0.6 | torque-weighted mean cutter radius / R |
| `eta_mech` | 0.05 | 0.08 | 0.12 | bearing, seal and gearbox losses |

Rock cutting energy for discs on a soft- or mixed-ground head (`EC_ROCK_KJ_M3`): 40, 20 and 8 MJ/m³ (about 11,
5.5 and 2.2 kWh/m³) for competent, fractured and weak rock, scattered by `ec_rock_factor`.

**Calibration.** The EPB paste parameters (τ₀ central 8 kPa, tan δ central 0.02) are calibrated on operating
records of a large-diameter (> 15 m) EPB drive in weathered rock and soil: the recorded median torque and median
specific energy are reproduced within 5 %, and the recorded torque–pressure slope fixes tan δ. The earlier
torque–pressure friction of 0.30 for EPB spoil overstated the rise of torque with chamber pressure 5–13 times;
`face.epb_friction` (0.05) and `face.slurry_friction` (0.16), used by the `regression_pressure` torque, are now the
equivalents of the central values here (`cutterhead.equivalent_friction`), so both torque routes rise at the same rate.

## 5. What moves a project within, or outside, these ranges

* **Conditioning** (EPB): foam and polymer dose sets τ₀ and tan δ; clogging clays can double the torque.
* **Head design**: opening ratio, number of spokes, active mixing arms, rim width, disc size and spacing.
* **Chamber fill**: a partly filled chamber (n_f → 1.5) or an air bubble lowers the bulkhead term.
* **Driving**: rpm and penetration are operator choices; specific energy is lowest at the highest penetration the
  ground and the muck system allow.
* **Restarts**: after a stoppage the paste consolidates and breakout torque can reach 60-80 % of the rated
  torque for a few rings (Acta Geotechnica 2022). That is outside the steady-state bands here.
* **Rated vs operating**: the Part 3 torque regression describes installed capacity; steady operating torque in soil is
  usually 30-50 % of it.

## 6. Checks

* Large-diameter EPB drive (calibration, above): median torque and specific energy within 5 %; the P10–P90 torque band
  sits inside the recorded range.
* 9.19 m EPB in limestone (Heliyon 2024): recorded mean torque 7.6 MN·m; the model gives P10–P90 5.7–9.4 MN·m, P50 7.4,
  with cutting 36 % of the torque (paper: about 50 %, its cutting term including tool friction in the chamber).
* The four examples, P10 – P50 – P90 specific energy (kWh/m³): Metro EPB 7.25 m 6.8 – 9.3 – 12.9; Railway slurry
  7.25 m 4.4 – 5.7 – 7.5 (the slurry circuit is counted separately); Road EPB 15.6 m 14 – 21 – 31; Hydro single
  shield 10.45 m 17 – 20 – 23 (`tunco2pro examples`, or step 8 of the web app).

`energy_method = "components"` is the default from v2.1. `"forces"` (thrust and torque work with the chosen torque
model) remains available and is used in v1 compatibility.

## References

* Heliyon (2024). Torque components of a 9.19 m EPB shield in limestone. https://pmc.ncbi.nlm.nih.gov/articles/PMC11140792/
* Acta Geotechnica (2022). Soil conditioning and restart torque of EPB shields. https://doi.org/10.1007/s11440-022-01666-7
* Wang et al. (2012) and Zhang et al. (2014), Automation in Construction: component models of EPB cutterhead torque
  (cutting, face, rim and chamber friction), on which Section 2 is built.
* Rostami, J. (CSM model of disc cutter forces) and Bruland, A. (1998, NTNU hard-rock prediction model, field
  penetration index), on which Section 3 is built.
* DAUB (2025). Recommendations for the selection of tunnel boring machines.
