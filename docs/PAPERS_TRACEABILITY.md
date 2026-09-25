# Traceability to the TunCO2 papers (Parts 1–3)

Chen X., Huang M., Bai Y., Zhang Q.B. et al., *Sustainability of underground infrastructure*,
Tunnelling and Underground Space Technology:
Part 1 (vol. 148, 105776, 2024): digitalisation-based carbon assessment and baseline;
Part 2 (vol. 159, 106479, 2025): digitalisation-based integration and optimisation;
Part 3 (vol. 167, 107028, 2026): TunCO2 open-source toolbox.

Related: Xiao F., Chen X., Zhu Y., Xie P., Salimzadeh S., Zhang Q.B., *Multi-LoD BIM integrated design framework for
pressurised tunnel: hydro-mechanical coupling simulation and sustainability assessment*, TUST 158, 106404 (2025),
doi:10.1016/j.tust.2025.106404, basis of the Hydro tunnel example (10.45 m single shield, pressure tunnel, LoD 100–400).

## Validation against the published baseline (Part 3, rail exemplar)

`examples/part3_metro_case.json`, run with `--v1` (v1 factors and arithmetic), test
`tests/test_parts_1_3.py::test_part3_rail_exemplar_matches_paper`:

| Item (kgCO2e/m) | Part 3 | TunCO2 Pro |
| --- | --- | --- |
| Lining concrete | 2,799 | 2,799 |
| Lining steel | 1,335 | 1,335 |
| Invert backfill | 1,126 | 1,127 |
| Annulus grout | 846 | 846 |
| Transport (A4) | 211 | 211 |
| TBM production | 598 | 599 |
| Excavation | 2,504 | 2,504 |
| Spoil removal | 961 | 961 |

TBM transport (27) and rail/fit-out (~75) depend on inputs not saved in the .pbix.

## Digitalisation

| Paper feature | Where | TunCO2 Pro |
| --- | --- | --- |
| Parametric segmental lining, unique object IDs (P1, P3) | `geometry.build_rings`, `route_elements` | Rings with key segment, stagger, per-element IDs and carbon |
| Rings duplicated along the alignment (P3) | `alignment.Alignment`, `route_elements` | 3D polyline alignment; rings placed and oriented along it |
| Alignment from design files (P3 "DWG, XML") | `alignment.from_landxml` | LandXML Line/Curve + vertical PVIs; simple straight/curve generator |
| Chainage, overburden, strata as fixed variables (P2) | `alignment.GroundZone`, `route.assess_route` | Ground zones by chainage; p0 = γH; carbon + CCM per zone |
| LoD 100–500 models (P1, P3) | `geometry.LOD_CONTENT` | 100 envelope · 200 lining/grout/invert solids · 300 segmented rings · 400 + deck · 500 as-built flag |
| Semantic enrichment / attribute tagging (P3) | `elements_to_ifc` | IFC 4.3 Psets: zone, chainage, volume, A1–A3 carbon, LoD, ring/segment |
| Downstream numerical / BIM tools (P3: FLAC3D, Revit) | IFC 4.3, glTF, .3dm export | Revit/Bonsai via IFC; Rhino via .3dm. FLAC3D export not yet implemented |
| Functional units per rail/lane/m²/m³ (P1) | `Result.functional_units` | Per route-km, track/lane-km, m² internal area, m³ excavated |
| TBM lifecycle: production, transport, excavation, spoil, auxiliary (P3) | `carbon.assess` | All five, plus site diesel (NGA 2026) |
| Excavation energy: specific energy, empirical, analytical (P3) | `tbm.py`, `TBMLoads.energy_method` | All three methods |

| TBM types (P3: type regressions of thrust and torque) | `tbm_types.py`, `tbm.py` | Six types incl. multi-mode (max of EPB/slurry), applicability per zone, A5 comparison |
| GIS/BIM integration (P1 digital workflow) | `gisbim.py` | Georeferenced corridor import, GeoJSON, Blender scene, IFC 4.3 IfcMapConversion |

## Optimisation

| Paper feature | Where | TunCO2 Pro |
| --- | --- | --- |
| NSGA-II, carbon vs FoS (P2) | `optimise(algorithm="nsga2")` | Yes |
| NSGA-III, carbon/FoS/convergence (P3) | `optimise(algorithm="nsga3")` | Yes |
| Variables t, f'c, x0 (P2, P3) | `OptimiseInput` | Yes, bounds user-set |
| Constraints: ULS FoS, SLS convergence, discrete grades (P2) | `fos_min`, `u_max_mm`, `discrete_grades` | Yes (hard constraints) |
| Parametric FoS–carbon–diameter study, D_i/t 18–25, 50–125 m cover (P2 Fig. 5) | `optimise.parametric` | Yes; Parametric tab |
| Parallel coordinates, 2D/3D Pareto (P3) | web app | Parallel coordinates + Pareto scatter; click to apply a design |
| Optimisation along the route by ground zone (P2 BIM data hub) | `route.optimise_route` | Yes; results can be written back to zones |
| Reduction strategies and cumulative potential (P3) | `carbon.strategies` | Individual levers + sequential combined figure |

## Not yet covered

- 3D numerical TBM simulation (P2): link through IFC to FLAC3D/open-source FE; not embedded.
- Slurry treatment carbon (P3 limitation): first-principles estimate of pumping and separation energy (`slurry.py`), or a user value.
- Mass regression for hard-rock TBMs, none published in Part 3; EPB regression used with a warning.
- Station and cavern elements (P3 future work).
- Industry benchmark database across projects (P3 future work).
