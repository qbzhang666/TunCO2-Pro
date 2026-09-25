# Machine and face-support relations

Relations and screening limits used by TunCO2 Pro, with their sources.

## TBM type selection (`tbm_types.py`)
| Criterion | Value | Source |
| --- | --- | --- |
| EPB support unaided | k ≤ 10⁻⁶ m/s | DAUB (2025) |
| EPB with foam/polymer conditioning | 10⁻⁶ < k ≤ 10⁻⁴ m/s; limited above | DAUB (2025), EFNARC (2005) |
| Slurry | clean sands and gravels (k ≥ 10⁻⁶ m/s) | DAUB (2025) |
| Overlap: EPB paste | fines (< 0.06 mm) ≥ ~15 % | DAUB (2025) |
| Overlap: slurry separation limit | fines ≤ ~40 % | DAUB (2025) |
Screening limits only; machine selection must be made against the project ground model.

## Face support pressure (`face.py`)
p_control = K_e σ′_v + u_w + Δp (JSCE 2016), with K_e = K₀ to minimise settlement, K_a or 0 where heave is
observed; K₀ = 1 − sin φ′ (Jaky 1944); upper bound = total vertical stress at the crown. Axis depth z₀,
cover to crown C = z₀ − D/2. Face pressure and carbon: Bigdeli et al. (2026).

## Volume-loss settlement (`settlement.py`)
Transverse trough S(y) = S_max exp(−y²/2i²), i = K z₀, S_max = V_L (πD²/4) / (√(2π) i) (Peck 1969; O'Reilly and
New 1982). Horizontal movement towards the axis H(y) = (y/z₀) S(y); horizontal strain ε_h = (S/z₀)(1 − y²/i²);
maximum slope 0.607 S_max / i at y = i (the point of inflection). Longitudinal profile S(x) = S_max Φ(−x/i), x
ahead of the face (Attewell and Woodman 1982). K: 0.5 clay (fines ≥ 35 %), 0.4 silt (15–35 %), 0.3 sand, 0.25
rock, unless entered. V_L, unless entered for the project or the zone: 0.5 % sand, 0.75 % silt, 1 % clay for a
closed-face machine at the K₀ face pressure (upper part of the ranges of Mair and Taylor 1997 and Mair 2008),
×1.5 with the face pressure below K₀, ×2 without face support in soil, 0.1 % in rock. Damage screening after
Rankin (1988): category 1 (negligible) S_max ≤ 10 mm and slope ≤ 1/500; 2 ≤ 50 mm, 1/200; 3 ≤ 75 mm, 1/50; 4
beyond. The trough is a screening tool; a zone above the limits is escalated to a numerical model.

## Machine mass (`tbm.py`, finding F5 resolved)
M_EPB = 7 D^2.21 t and M_slurry = 6.62 D^2.18 t (Part 3 regressions, in tonnes). They reproduce the machines of
Xie et al. (2024): 6.98 m EPB, 510 t (regression 512 t); 12.0 m Mixshield, 1274 t (regression 1491 t). The v1
division by 9.8 is kept only in v1-compatibility mode.

## Thrust: BIM-to-Thrust relation (`xie2024`, default for closed-face machines)
F_T = F_s + F_w + F_f (Xie et al. 2024, Eq. 5), per zone:
- F_s,upper = K₀ σ_v A; F_s,lower = (K_a σ_v − 2c′√K_a) A, K_a = K₀/(1 + sin φ′) (Eqs. 7–10);
- F_w = γ_w h_w A only where k ≥ k_critical = 5 × 10⁻⁵ m/s, the soil then at effective stress; combined otherwise;
- F_f = f_TBM-GEO [W_TBM + L_TBM R σ_v (2 + 4K₀)], machine weight on the invert, vertical stress on the upper half
  and K₀σ_v all round; f_TBM-GEO = 0.1 soft clay, 0.2 typical, 0.3 sand and gravel (Tables 2–3); L_TBM = 1.25 D by default.
With σ_v linear in depth its face average is the value at the axis. Reproduces the published records: 6.98 m EPB in
clay 8–22 MN over 12–27 m depth (record 10–20 MN); 12.0 m Mixshield 36–91 MN over 15–37.5 m (record 40–100 MN).
The Part 3 type regression gives 45 MN at 7.25 m and 281 MN at 15.6 m (EPB), installed capacity rather than
working thrust.

## Thrust and torque (`tbm.py`)
- `empirical_type`: Part 3 type regressions on diameter (Chen et al. 2026).
- `regression_pressure` (default for the closed-face examples): the regression holds at a reference control pressure
  p_ref (z₀ = 2D, water table 3 m below surface, γ = 20 kN/m³, K₀ = 0.5, Δp = 20 kPa);
  F = F_reg + (π/4) D² (p − p_ref); T = T_reg + (π/12)(1 + f_Δp) μ (1 − ξ) D³ (p − p_ref),
  μ = torque rise with chamber pressure as a medium friction: EPB spoil 0.05, bentonite slurry 0.16, the equivalents of the cutterhead-mechanics central values (CUTTERHEAD.md). The earlier 0.30 for EPB overstated the rise 5–13×.
- `analytical`: v1 relations. The clay branch fell inside the recorded thrust of a 6.98 m EPB drive (10–20 MN,
  38 000 records); the sandy-friction branch and Krause's empirical relation lay above it (Xie et al. 2024).
  Per zone the branch follows the fines content (≥ 35 % → clay). A warning is issued when the sandy branch or
  Krause's relation is used.

## Cutterhead mechanics (`cutterhead.py`, `energy_method = "components"`, the default)

E = F·1 m + 2πT/p. Shields: T = (e_c A p/2π + n_f(1−ξ)(2π/3)R³τ_m + πDWRτ_m)/(1−η), with τ_m = τ₀ + tanδ(p_c − u)
for EPB paste and τ_s + ψ tanδ_s(p_c − u) for slurry. Discs: F_n = FPI·p, T = tan(φ/2) N_c F_n r̄ R/(1−η).
Parameter ranges, their physical basis and the P10-P90 propagation: [CUTTERHEAD.md](CUTTERHEAD.md).

## Slurry circuit (`slurry.py`)
Feed and discharge densities ρ_f, ρ_d; solids concentration Cv = (ρ_d − ρ_f)/(ρ_s − ρ_f), slurry volume
(1 − n)/Cv per m³ excavated; Darcy–Weisbach pumping plus hydrocyclone pressure drop; or a user value.

## References
- DAUB (2025) Recommendations for the selection of tunnel boring machines. German Tunnelling Committee (version January 2022, revised August 2025).
- EFNARC (2005) Specification and guidelines for the use of specialist products for mechanised tunnelling (TBM) in soft ground and hard rock.
- ITA-AITES (2000) Recommendations and guidelines for tunnel boring machines (TBMs). Working Group No. 14.
- JSCE (2016) Standard Specifications for Tunneling-2016: Shield Tunnels. Japan Society of Civil Engineers, Tokyo.
- Jaky J. (1944) The coefficient of earth pressure at rest. Journal of the Society of Hungarian Architects and Engineers 78(22), 355–358.
- Krause T. (1987) Schildvortrieb mit flüssigkeits- und erdgestützter Ortsbrust. PhD thesis, TU Braunschweig.
- Xie P., Chen K., Yin Z., Zhu Y., Luo H., Zhang Q.B. (2024) A BIM-based multi-model framework for advancing TBM performance, Part 1: Real-time prediction of thrust force. TUST 151, 105856. doi:10.1016/j.tust.2024.105856
- Bigdeli M., Wang R., Raedle A., Zhang Q.B., Hopkins A., Bragard C. (2026) TBM face pressure optimization and carbon emission assessment in urban and dense environment, California, USA. In Connecting Communities Through Underground Infrastructure, 515–522. CRC Press. doi:10.1201/9781042001064-64
- Peck R.B. (1969) Deep excavations and tunneling in soft ground. 7th ICSMFE, Mexico City, State of the Art Volume, 225–290.
- O'Reilly M.P., New B.M. (1982) Settlements above tunnels in the United Kingdom: their magnitude and prediction. Tunnelling 82, IMM, London, 173–181.
- Attewell P.B., Woodman J.P. (1982) Predicting the dynamics of ground settlement and its derivatives caused by tunnelling in soil. Ground Engineering 15(8), 13–22, 36.
- Rankin W.J. (1988) Ground movements resulting from urban tunnelling: predictions and effects. Geological Society Engineering Geology Special Publication 5, 79–92.
- Mair R.J., Taylor R.N. (1997) Bored tunnelling in the urban environment. 14th ICSMFE, Hamburg, 4, 2353–2385.
- Mair R.J. (2008) Tunnelling and geotechnics: new horizons. Géotechnique 58(9), 695–736.
- Chen X. et al. (2024, 2025, 2026) Sustainability of underground infrastructure, Parts 1–3. TUST 148, 105776; 159, 106479; 167, 107028.
