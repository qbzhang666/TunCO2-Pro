# Migration from TunCO2 v1 (Power BI + PyQt + Grasshopper)

This document records how every calculation in TunCO2 v1 was carried into
TunCO2 Pro, what was changed and why, and how to cross-check the two.

Source of truth for v1: `Tunnel Emission.pbix` (GitHub root copy, last updated
Sep 2025) and `Opt3D.py` / `Stability.py`. The 218 DAX measures and 116 Power
Query tables were extracted programmatically and are stored in
`reference/pbix_dax_measures.csv` and `reference/pbix_power_query.csv`.
The concrete ECF database (236 records, AU/UK/CA/DE/US/…) is bundled as
`src/tunco2pro/data/concrete_ecf_database.csv`.

## Measure map

| v1 Power BI measure(s) | TunCO2 Pro |
| --- | --- |
| `Slope_Database`, `Intercept_Database`, `ECFc_Database` | `FactorLibrary.concrete_regression()` |
| `Slope_Define`, `Intercept_Define`, `ECFc_User` | `factors.fit_user_points()` |
| `ECFs_Database`, `ECFs` | `data/factors.csv` category `steel`; `carbon.steel_ecf()` |
| `Concrete`, `Steel`, `Invert backfill`, `Grout`, `Fitout`, `Road/Rail` | `carbon.assess()` A1-A3 line items |
| `*_Selected_TEF_n`, `*_A4_Carbon_n`, `A4: *`, `Transport` | `carbon._legs()`; any number of legs per material |
| `Empirical/Analytical Thrust & Torque`, `*_Type` | `tbm.thrust_mn()`, `tbm.torque_mnm()` |
| `Energy`, `TBM_Result` | `tbm.energy_kwh_per_m()` x grid factor |
| `TBM Production` | `tbm.tbm_mass_kg()` x ECF / allocation length |
| `Spoil Removal`, `TBM_Carbon`, `TBM Emission User Define` | A5 line items in `carbon.assess()` |
| `SCM`, `Reduce Strength`, `Reduce Thickness`, `Reinforcement/Fibre Optimisation`, `Renewable Energy` | `carbon.strategies()` |
| `Summary_*`, `SankeyFlow`, `Pie*`, `Sunburst*` | web front end (ECharts) and Excel report |
| `Stability.py`, `CCM.py` (sympy) | `ccm.solve()` / `ccm.curves()` (closed form + Brent root) |
| `Opt3D.py` (NSGA-III, pymoo) | `optimise.optimise()` |
| Grasshopper `Tunnel_Generation.gh` + Speckle | `geometry.build_rings()` + glTF / IFC 4.3 / .3dm exporters |

## Findings in v1 (fixed by default; `compat_v1=True` reproduces v1)

| # | Where | Issue | TunCO2 Pro default |
| --- | --- | --- | --- |
| F1 | `TBM_A4_Carbon_n` | TBM transport = mass (t) x km x EF x 0.001 is a project total but is added to per-metre A5 | Project total divided by allocation length |
| F2 | `Fitout_A4_*`, `Rail/Road_A4_*` | Quantity (entered as volume) used as mass in kg | Kept; flagged in warnings. Enter kg/m |
| F3 | `TBM_Result` vs `Renewable Energy` | Victoria grid factor 0.92 in one measure, 0.86 in the other; renewable lever also scales TBM manufacture | One grid factor; lever acts on excavation energy only |
| F4 | `Reduce Thickness`, `Reinforcement/Fibre Optimisation` | Steel density hard-coded 7800 | Uses the steel density input |
| F5 | `TBM Production` | Mass = 7 D^2.21 x 1000 / 9.8. If 7 D^2.21 is tonnes (~565 t for 7.28 m), /9.8 under-states mass ~10x | **Resolved: mass in tonnes, no /9.8**, reproduces the 510 t 6.98 m EPB and 1274 t 12.0 m Mixshield of Xie et al. (2024); /9.8 kept in v1-compatibility mode |
| F6 | `A1-A3` | Fit-out is shown in charts but omitted from the A1-A3 total | Included |
| F7 | TEF `SWITCH` | "Rail" listed twice (0.0256 and 0.0240); DAX always returns the first | Single entry 0.0256 in library; confirm source |
| F8 | `Opt3D.py` line 96 | Rock-mass modulus Em overwritten by `9760.9 fc^0.319` (a concrete-stiffness correlation) | Correlation applied to Ec; Em from input |
| F9 | `Opt3D.py` | No constraint: Pareto set includes designs below any required FoS | Hard constraint FoS >= `fos_min` |
| F10 | `Stability.py` | Plastic GRC branch used above Pcr | Elastic branch above Pcr (`v1_plastic_branch=True` reproduces v1) |
| F11 | `Slope_Dark`, `Intercept_Dark` | Covariance and mean use the wrong column (visual only) | Not ported |
| F12 | Power Query | Database read from local file paths on the author's machine (shown as `<local path>` in `reference/`); refresh fails elsewhere | Database bundled with provenance |
| F13 | `Invert backfill`, `Spoil Removal` | 451.2 kgCO2e/m3 and 0.296 x 1.3 hard-coded, units undocumented | Moved to factor library with notes; confirm units |

v1 default case (pbix slicers, v1 factor set): corrected arithmetic 10,294 kgCO2e/m vs 10,662 kgCO2e/m in v1 mode.
F5 matters when the EPB/slurry mass regression is used: if the /9.8 is an error,
TBM manufacture for a 7.28 m EPB rises from 31 to ~306 kgCO2e/m. (The saved .pbix
slicers use a user-defined mass of 1,100 t, giving 599 kgCO2e/m.)

## v2.1: cutterhead mechanics by default

* `tbm.loads.energy_method` defaults to `"components"`: torque and excavation energy from the cutterhead mechanics
  (`cutterhead.py`, `docs/CUTTERHEAD.md`), zone by zone, with a P10–P90 band. `"forces"` is unchanged and is used in
  v1 compatibility. Projects saved with `"forces"` keep it.
* `face.epb_friction` 0.30 → 0.05 and `face.slurry_friction` 0.05 → 0.16, the equivalents of the cutterhead central
  values; the old EPB value overstated the rise of torque with chamber pressure 5–13 times.
* Excavation energy of a soft-ground shield falls substantially against v1 (the v1 torque regression behaves as
  installed capacity, not operating torque); hard-rock energy is set by the disc model.

## Regression evidence

- `tests/test_ccm.py`: FoS, p_mob and u_mob match the v1 sympy algorithm to 1e-6
  on four ground/support cases (`tests/reference_v1_ccm.py` is the verbatim v1 code).
- `tests/test_carbon.py`: every line item of the default case checked against an
  independent hand calculation of the DAX formula.
- Optimiser: 2,400 evaluations in ~0.4 s (v1: minutes with sympy).

## Factor update (Sep 2026)

The `current` factor set replaces v1 values. Effect on the default design case
(D_i 6.6 m, t 0.30 m, f'c 45 MPa, 1.73% rebar, VIC grid):

| Item | v1 factor | Current factor | Source |
| --- | --- | --- | --- |
| Concrete 45 MPa | 450 kgCO2e/m3 (user points) | 621 default / 326 average | NABERS NEFD v2026.2, >40–50 MPa band |
| Reinforcing steel | 1.591 kgCO2e/kg | 3.65 default / 1.48 average | NABERS NEFD v2026.2 |
| Invert backfill | 451.2 kgCO2e/m3 | 556 (default, <=40 MPa) | NABERS NEFD v2026.2 |
| VIC grid | 0.92 kgCO2e/kWh | 0.85 (0.74 scope 2 + 0.11 scope 3) | NGA Factors 2026, Table 1 |
| Articulated truck | 0.106 kgCO2e/t.km | 0.0793 | DESNZ 2026 |
| Spoil haulage | 0.296 x 1.3 per m3.km | 2.8 t/m3 x 0.0793 per t.km (no 1.3) | derived; see F13 |

NEFD "default" values are uncertainty-adjusted upper values used by NABERS when no
EPD is supplied; they are deliberately conservative and reward product EPDs.
Use `nefd_basis: "average"` for a central estimate.

Resulting totals for the same design and inputs (EPB mass regression): v1 factors
10,090 kgCO2e/m; current with NEFD
defaults 12,386 kgCO2e/m (A1-A3 8,952); current with NEFD averages 8,563 kgCO2e/m.
The range is dominated by the concrete and rebar factor choice, which is why
project EPDs matter.

## Cross-check against the .pbix

**Formula level (done, 24 Sep 2026).** The engine reproduces the 218 DAX measures of
the GitHub `Tunnel Emission.pbix` (Sep 2025); every line item is checked in
`tests/test_carbon.py`. Note: the copy in the local `00-GitHub/TunCO2` folder
(saved 11 Apr 2025) is an **older version**: it has 202 measures, no TBM transport
or user-defined A5 items, and its `TBM Production` multiplies by the *steel*
factor `[ECFs]` instead of `[ECF_TBM Value]`. Use the GitHub copy for the check.

**Displayed values (to complete in Power BI Desktop).** Open the GitHub
`Tunnel Emission.pbix`, leave the saved slicers, cancel the "Enable script visuals"
prompt, and fill in the Power BI column:

| Power BI page | Measure | TunCO2 Pro `--v1` (kgCO2e/m) | Power BI value | Match |
| --- | --- | --- | --- | --- |
| A1-A3 Emission | `Concrete` | 2,926.4 |  |  |
| A1-A3 Emission | `Steel` | 1,396.1 |  |  |
| A1-A3 Emission | `Invert backfill` | 1,236.8 |  |  |
| A1-A3 Emission | `Grout` | 182.0 |  |  |
| A1-A3 Emission | `Road/Rail` | 1.2 |  |  |
| A4 Emission | `A4: Lining` | 109.0 |  |  |
| A4 Emission | `A4: Grout` | 14.5 |  |  |
| A4 Emission | `A4: Backfill` | 43.6 |  |  |
| A5 Emission | `TBM_Result − TBM Production (excavation)` | 2,503.9 |  |  |
| A5 Emission | `TBM Production` | 598.5 |  |  |
| A5 Emission | `Spoil Removal` | 1,601.7 |  |  |
| A5 Emission | `TBM Transportation` | 8.2 |  |  |
| A5 Emission | `TBM Emission User Define` | 40.0 |  |  |
| Emission Overview | `A1-A3` / `A4` / `A5` | 5,742.5 / 167.1 / 4,752.3 |  |  |
| TBM Performance | `Thrust` MN / `Torque` MN.m / `Energy` kWh/m | 53.88 / 21.97 / 2,721.6 |  |  |

Command: `tunco2pro assess examples/pbix_default_case.json --v1`. Slicers with no
saved value (rail/road quantity, pq, Ws, Wa) and the 1,100 t TBM mass are listed
in the example file's `_note`; if Power BI shows a different figure for those
items, align the input rather than the formula.

## Open items

1. Confirm the units of finding F13 against Part 1 (F5, TBM mass, is resolved: see `docs/EQUATIONS.md`).
2. Replace the DESNZ freight factors with TfNSW ECCL (tier 2) values once obtained,
   and refresh NGA / NEFD annually (`data/factors.csv`, `data/nefd_concrete.csv`).
3. Map the Excel report to the official NSW Appendix 9 template.
4. Cross-check `--v1` results against the .pbix in Power BI Desktop.
5. Legal review of third-party licences (`THIRD_PARTY_NOTICES.md`).
