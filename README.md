# TunCO2 Pro

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23290499.svg)](https://doi.org/10.5281/zenodo.23290499)

TunCO2 Pro carries published research on tunnel decarbonisation into a design
tool for practice. It quantifies the upfront embodied carbon (modules A1–A5) of
TBM tunnels along a georeferenced route; compares the TBM types used on real
projects (gripper, single and double shield, EPB, slurry and multi-mode) by
ground applicability and excavation energy; checks lining stability and surface
settlement with closed-form analytical solutions; and optimises lining thickness,
concrete grade and installation distance for carbon and safety together. It
serves designers, contractors and clients at the option and tender stages, and
researchers and students who need a transparent, reproducible model.

Successor to the published TunCO2
toolbox (TUST Parts 1–3; the original research code is at
github.com/X-Chen1997/TunCO2). Open source under the MIT licence (`LICENSE`).
Copyright (c) 2026 Qianbing Zhang, Monash University; contact
qianbing.zhang@monash.edu. To cite the toolbox, see `CITATION.cff` (DOI [10.5281/zenodo.23290499](https://doi.org/10.5281/zenodo.23290499)) and the
references at the end of this file.

TunCO2 Pro is a research and teaching tool. Results are indicative and depend
on the input data and emission factors; they do not replace project-specific
assessment, verified EPDs or professional engineering judgement. The bundled
ground parameters and reference tunnels are generic or synthetic and do not
represent any real project.

TunCO2 Pro is the worked toolbox of Chapter 7, *Digitisation for
Sustainability*, of the textbook *Digital Underground Engineering*; the
chapter's figures, tables and supplementary videos are generated from it.

## Download and install

Everything the toolbox needs (code, data, four reference tunnels, launcher and
tests) is in this repository: https://github.com/qbzhang666/TunCO2-Pro.
Download the release archive (*Releases*, or *Code ▸ Download ZIP*) and unpack
it, or clone it with `git clone https://github.com/qbzhang666/TunCO2-Pro`.
The only prerequisite is Python 3.10 or later (https://www.python.org); no
commercial software is required.

**Windows.** Double-click `Start-TunCO2Pro.bat`. The first start creates a
private Python environment in the folder (`.venv`, a few minutes), installs the
package and opens the app in the default browser; later starts take seconds,
and the launcher picks a free port if 8000 is in use. `Run-Tests.bat` runs the
test suite. If the folder is synced by Dropbox, `.venv` is excluded from syncing; delete it to
rebuild.

**Any platform**, from a terminal in the unpacked folder:

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[all]"                            # core + IFC and Rhino export + tests
tunco2pro serve                                    # opens http://127.0.0.1:8000
python -m pytest                                   # optional: test suite
```

The optional extras are `ifc` (IFC 4.3 export), `rhino` (.3dm export),
`figures` (publication figures, matplotlib) and `dev` (tests); the core
calculation needs none of them.

**Docker** (hosted or on-premises): `docker build -t tunco2pro . && docker run -p 8000:8000 tunco2pro`.

**Without the browser:** `tunco2pro assess project.json -o report.xlsx`
assesses a saved project; `tunco2pro examples -o compare.csv` assesses the
four reference tunnels; the web API is documented at `/docs` on the running
server. In the app, *Help ▾* opens this documentation and the API reference.

## What it does

| Capability | Module |
| --- | --- |
| A1–A3 lining concrete, reinforcement, invert backfill, grout, fit-out, rail/road | `carbon.py` |
| A4 transport, any number of legs per material | `carbon.py` |
| A5 TBM excavation (forces or specific energy), TBM production, spoil, TBM transport, auxiliary plant, site diesel | `tbm.py`, `carbon.py` |
| Functional units: per route-km, track/lane-km, m² internal area, m³ excavated | `carbon.Result` |
| Alignment (LandXML or generated) and ground zones by chainage; route-level carbon and stability | `alignment.py`, `route.py` |
| LoD 100–500 models along the alignment → glTF, IFC 4.3 (Psets with carbon), Rhino .3dm | `geometry.py` |
| Convergence-confinement stability (GRC, LDP, SCC, FoS) | `ccm.py` |
| Volume-loss settlement screening per zone: Gaussian trough (S_max, i, slope, horizontal strain, longitudinal profile), V_L estimated or entered, Rankin damage category, SLS limits | `settlement.py` |
| NSGA-II, SPEA2, MOEA/D (Part 3) and NSGA-III optimisation of thickness, grade and installation distance with ULS FoS, SLS convergence and standard concrete grades; per-zone optimisation | `optimise.py`, `route.py` |
| Parametric FoS–carbon–diameter study (after Part 2) | `optimise.parametric` |
| Decarbonisation levers, individually and combined | `carbon.strategies` |
| Six TBM types (gripper, single / double shield, EPB, slurry, multi-mode): ground applicability per zone, A5 comparison, 3D models at the face | `tbm_types.py`, `web/assets/tbm/` |
| GIS → BIM planning bridge: plan line + geological long section + CRS → georeferenced route and zones; GeoJSON, Blender package, IFC 4.3 with IfcMapConversion | `gisbim.py`, `integrations/tunco2_to_blender.py` |
| Versioned emission-factor library with source and NSW data-quality tier | `factors.py`, `data/` |
| Excel report (NSW structure, route sheet) · REST API · browser app | `report.py`, `api.py`, `web/` |
| Publication figures (PDF, SVG, PNG at 1000 dpi) from the project: route, machine comparison and suitability, line items, levers and reduction pathway, specific energy, lining design space, zone-by-zone optimisation, Pareto set, settlement screening; reference-tunnel comparisons, levers and benchmark | `figures.py` (Step 8 *Figures*, `tunco2pro figures`) |

Validated against the published Part 3 baseline; see `docs/PAPERS_TRACEABILITY.md`.

No commercial software is needed to run it. Power BI, Rhino and Grasshopper
are not dependencies; their file formats are optional outputs.

## Using the app

The browser app follows the workflow an engineer works through: **1 Project → 2 Route & ground →
3 TBM selection → 4 Lining & materials → 5 Stability & design → 6 Carbon results → 7 Scenarios →
8 Model & export**. Each step shows a status mark (✓ done, ! check, ✗ criterion failed).

- Results recalculate automatically as inputs change; the headline figures stay in the bar at the top.
- Advanced model parameters are hidden until *File ▸ Show advanced parameters*; every field has a tooltip
  with its meaning and allowed range, and out-of-range values are flagged.
- Route zones are linked across the map, zone table, charts and 3D model: pick a zone anywhere to follow it.
- Save alternatives as **scenarios** and compare them (totals, change by element, and the inputs that differ).
- Work is saved in the browser automatically and restored on the next start; use *File ▸ Save project* to keep a file.
- Step 8 ▸ **Figures** draws publication figures from the current project (print style, vector PDF or SVG, or PNG at
  1000 dpi); `tunco2pro figures project.json -o figures` does the same from the command line, and
  `tunco2pro figures hydro` for a reference tunnel. The textbook chapter's figures are made this way.

Teaching: `docs/EXERCISES.md` has eight student exercises built on the four examples (size, machine type,
cutterhead energy, face pressure, lining optimisation, decarbonisation levers, GIS → BIM).

## Planning workflow (GIS → BIM)

1. Project step → pick one of the four bundled examples, **Metro, Railway, Road or Hydro tunnel**, or, under
   Route & ground, import your own plan line CSV, long-section JSON and CRS JSON. The section is registered to the
   plan line by ground-surface matching.
2. Zones follow the dominant unit across the TBM face (rock / soil / mixed). **Unit parameters in
   `data/ground_units.csv` are indicative generic values**; replace them with values from the geotechnical interpretative report.
3. TBM selection → applicability of the six machine types per zone and their A5 carbon; *Use this machine*.
4. Export: GeoJSON (QGIS/ArcGIS), Blender package (zip: scene JSON, route and TBM glTF, importer script),
   georeferenced IFC 4.3. All in local metres about the project origin, so they overlay other models that use
   the same origin without transformation.

The four examples are set up for comparison (Scenarios step ▸ *Compare examples*, or `tunco2pro examples -o compare.csv`):

| Example | TBM | Diameter | Compared with | Isolates |
| --- | --- | --- | --- | --- |
| Metro tunnel | EPB shield | 7.25 m | Road; Railway | – |
| Road tunnel (3 lanes) | EPB shield | 15.6 m | Metro | size |
| Railway tunnel | Slurry shield | 7.25 m | Metro | machine type |
| Hydro tunnel | Single shield | 10.45 m | – | hard rock at depth (after Xiao et al., 2025, TUST 158, 106404) |

Results are normalised per metre, per m³ excavated and per track/lane-km. For slurry and multi-mode machines the
slurry circuit (pumping and separation) is estimated from first principles (`slurry.py`: slurry volume from
feed/return densities and porosity, Darcy–Weisbach friction over the pipeline, shaft lift, hydrocyclone pressure
drop) or taken from a user value (`tbm.slurry.mode = "user"`). Cutterhead torque and excavation energy come from
the mechanics of the head (`cutterhead.py`, `energy_method = "components"`): cutting, face and rim friction in the
support medium and losses for shields, disc forces from the field penetration index in rock, with a P10–P90 band
from parameter ranges that vary by project (`docs/CUTTERHEAD.md`). The Hydro example deliberately has one fault zone that
fails the FoS check with its 0.35 m lining, as a starting point for zone-by-zone optimisation.

The examples are synthetic: invented terrain and geology on fictitious coordinates (WGS 84 / UTM 54S), generated
by `tools/make_example_corridors.py`. Their input files double as templates for the import formats
(`src/tunco2pro/data/examples/<case>/`). See `docs/GIS_BIM.md`.

The TBM previews are generic representations of each machine type; regenerate them from your own Rhino models with
`python tools/convert_tbm_models.py <folder of .3dm files>`.

## Emission factor sets

| Set | Grid electricity | Concrete / steel | Freight transport |
| --- | --- | --- | --- |
| `current` (default) | NGA Factors 2026, location-based scope 2 + scope 3 (VIC 0.85 kgCO2e/kWh) | NABERS National material emission factors database v2026.2 (Jul 2026): concrete by strength band, reinforcing steel 3.65 kgCO2e/kg (default) or 1.48 (average) | UK DESNZ conversion factors 2026 (tonne.km); no Australian t.km set is published |
| `v1` | TunCO2 v1 values (VIC 0.92) | v1 database regression / user points; rebar 1.591 | v1 values |

Transport and steel names from v1 projects are mapped to their closest current
equivalents automatically, with a warning. Every factor carries source and NSW
data-quality tier; project EPDs override library values as tier 1.

## Calculation modes

- **Default (corrected):** fixes the unit and logic issues found in v1.
- **v1 compatibility** (`--v1`, `compat_v1: true`, or the toggle in the app):
  reproduces the v1 Power BI arithmetic for cross-checking.

Machine selection, face-support pressure (JSCE), thrust/torque and slurry relations with their sources:
`docs/EQUATIONS.md`.

See `docs/MIGRATION.md` for the measure-by-measure map, findings F1–F13 and
the cross-check procedure.

## Documentation

| File | Content |
| --- | --- |
| `docs/EQUATIONS.md` | Machine selection, face-support pressure (JSCE), thrust, torque, slurry circuit, with sources |
| `docs/CUTTERHEAD.md` | Cutterhead mechanics: torque components, specific energy, parameter ranges and the P10–P90 band |
| `docs/GIS_BIM.md` | Import formats (plan line, long section, CRS) and the GIS → BIM exports |
| `docs/EXERCISES.md` | Eight student exercises on the four reference tunnels |
| `docs/MIGRATION.md` | Measure-by-measure map from TunCO2 v1, findings F1–F13, cross-check procedure, open items |
| `docs/PAPERS_TRACEABILITY.md` | Validation against the published Part 3 baseline |
| `CHANGELOG.md` | Versions; the version used for the textbook chapter |

## Layout

```
src/tunco2pro/   engine, API, web app, data (factor library, ground units, reference tunnels)
tests/           regression and hand-calculation tests
docs/            documentation (above)
tools/           corridor generator, TBM model converter
reference/       DAX and Power Query extracted from the v1 .pbix
examples/        project files (v1 default case, Part 3 metro case)
```

## References

The method, the baseline and the original toolbox are published in
*Tunnelling and Underground Space Technology* as a three-part series:

1. Chen, X., Huang, M., Bai, Y., Zhang, Q.B. (2024). Sustainability of underground
   infrastructure – Part 1: Digitalisation-based carbon assessment and baseline for
   TBM tunnelling. *Tunnelling and Underground Space Technology*, 148, 105776.
   https://doi.org/10.1016/j.tust.2024.105776
2. Chen, X., Huang, M., Xiao, F., Bai, Y., Zhang, Q.B. (2025). Sustainability of
   underground infrastructure – Part 2: Digitalisation-based integration and
   optimisation for low carbon design. *Tunnelling and Underground Space Technology*,
   159, 106479. https://doi.org/10.1016/j.tust.2025.106479
3. Chen, X., Lei, Q., Xiao, F., Huang, M., Zhang, Q.B. (2026). Sustainability of
   underground infrastructure – Part 3: TunCO2, an open-source digital toolbox for
   accounting and optimising decarbonisation in tunnelling. *Tunnelling and
   Underground Space Technology*, 167, 107028.
   https://doi.org/10.1016/j.tust.2025.107028

The Hydro tunnel and resilience and sustainability trade-offs follow: 
1. Xiao, F., Chen, X., Zhu, Y., Xie, P., Salimzadeh, S., Zhang, Q.B. (2025). Multi-LoD BIM integrated design framework for pressurised tunnel: Hydro-mechanical coupling simulation and sustainability assessment. *Tunnelling and Underground Space Technology*, 158, 106404. https://doi.org/10.1016/j.tust.2025.106404
2. Zhu, Y., Zhang, Q. B. (2026). Lifecycle resilience and sustainability trade-offs for underground infrastructure under multi-hazard scenarios. *Reliability Engineering & System Safety*, 267, Part A, 111797. https://doi.org/10.1016/j.ress.2025.111797

Life-cycle modules and closed-form ground response follow:

1. CEN (2011). EN 15978:2011 Sustainability of construction works: Assessment of environmental performance of buildings: Calculation method. European Committee for Standardization, Brussels.
2. Carranza-Torres, C., Fairhurst, C. (2000). Application of the convergence-confinement method of tunnel design to rock masses that satisfy the Hoek-Brown failure criterion. *Tunnelling and Underground Space Technology*, 15(2), 187–213. https://doi.org/10.1016/S0886-7798(00)00046-8
3. Vlachopoulos, N., Diederichs, M.S. (2009). Improved longitudinal displacement profiles for convergence confinement analysis of deep tunnels. *Rock Mechanics and Rock Engineering*, 42(2), 131–146. https://doi.org/10.1007/s00603-009-0176-4
4. Panet, M., Sulem, J. (2022). *Convergence-Confinement Method for Tunnel Design*. Springer Tracts in Civil Engineering. Springer, Cham. https://doi.org/10.1007/978-3-030-93193-3

TBM performance, face support and machine selection follow:

1. Xie, P., Chen, K., Yin, Z., Zhu, Y., Luo, H., Zhang, Q.B. (2024). A BIM-based multi-model framework for advancing TBM performance, Part 1: Real-time prediction of thrust force. *Tunnelling and Underground Space Technology*, 151, 105856. https://doi.org/10.1016/j.tust.2024.105856
2. Bigdeli, M., Wang, R., Raedle, A., Zhang, Q.B., Hopkins, A., Bragard, C. (2026). TBM face pressure optimization and carbon emission assessment in urban and dense environment, California, USA. In *Connecting Communities Through Underground Infrastructure*, 515–522. CRC Press. https://doi.org/10.1201/9781042001064-64
3. JSCE (2016). *Standard Specifications for Tunneling-2016: Shield Tunnels*. Japan Society of Civil Engineers, Tokyo.
4. DAUB (2025). *Recommendations for the selection of tunnel boring machines*. German Tunnelling Committee (version January 2022, revised August 2025).

Settlement screening follows:

1. Peck, R.B. (1969). Deep excavations and tunneling in soft ground. *Proceedings of the 7th International Conference on Soil Mechanics and Foundation Engineering*, Mexico City, State of the Art Volume, 225–290.
2. O'Reilly, M.P., New, B.M. (1982). Settlements above tunnels in the United Kingdom: their magnitude and prediction. *Tunnelling 82*, Institution of Mining and Metallurgy, London, 173–181.
3. Rankin, W.J. (1988). Ground movements resulting from urban tunnelling: predictions and effects. *Geological Society Engineering Geology Special Publication*, 5, 79–92.
4. Mair, R.J., Taylor, R.N. (1997). Bored tunnelling in the urban environment. *Proceedings of the 14th International Conference on Soil Mechanics and Foundation Engineering*, Hamburg, 4, 2353–2385.

Emission factors and data-quality tiers follow:

1. DCCEEW (2026). *Australian National Greenhouse Accounts Factors 2026*. Australian Government Department of Climate Change, Energy, the Environment and Water, Canberra.
2. NABERS (2026). *National Material Emission Factors Database*, v2026.2 (July 2026). NSW Government, Sydney. https://www.nabers.gov.au/publications/national-emission-factors-database
3. DESNZ (2026). *Greenhouse gas reporting: conversion factors 2026*. UK Department for Energy Security and Net Zero, London.
4. Infrastructure NSW (2025). *Embodied Carbon Measurement Technical Guide* (April 2025). NSW Government, Sydney.

### Concrete emission-factor database

The concrete regression (`ecf_mode = "database"`) draws on 236 records of
embodied carbon against compressive strength from 11 sources in 9 countries,
compiled and harmonised to kgCO2e/m3 by strength class and binder type in
Chen et al. (2024):

| Source | Country | Records |
| --- | --- | ---: |
| Inventory of Carbon and Energy (ICE) v3.0, Circular Ecology and University of Bath | UK | 100 |
| CSA Group product EPDs | Canada | 55 |
| ASTM International product EPDs | USA | 29 |
| EPiC database (Crawford, Stephan and Prideaux, 2019), University of Melbourne | Australia | 15 |
| AusLCI, Australian Life Cycle Assessment Society | Australia | 15 |
| ÖKOBAUDAT, German Federal Ministry for Housing, Urban Development and Building | Germany | 8 |
| Ready-mix concrete EPDs | Greece | 5 |
| Gunlake Concrete EPD | Australia | 5 |
| Ready Mix Industries EPD | Israel | 2 |
| INIES environmental and health reference data (FDES) | France | 1 |
| EPD Italy | Italy | 1 |

Our contribution is the compiled dataset itself: the records were screened,
converted to a common functional unit (1 m3 of concrete) and classified by
strength and supplementary cementitious material content, which turns
heterogeneous inventories and EPDs into a single strength-carbon relation that
can be filtered by region and binder type. TunCO2 Pro keeps the source of every
record, distributes the ICE groups only as least-squares summary statistics
(n and sums, `data/concrete_ecf_summary.csv`) so that the published regression
is reproduced exactly without redistributing ICE values, and lets licensed
users add record-level data (`TUNCO2PRO_ECF_EXTRA`). Licences and attributions
are listed in `src/tunco2pro/data/DATA_LICENCES.md`.

1. Crawford, R.H., Stephan, A., Prideaux, F. (2019). *Environmental Performance in Construction (EPiC) Database*. The University of Melbourne, Melbourne.
2. Hammond, G., Jones, C. (2019). *Inventory of Carbon and Energy (ICE) Database*, v3.0. Circular Ecology and University of Bath. https://circularecology.com/embodied-carbon-footprint-database.html
3. Australian Life Cycle Assessment Society. *Australian National Life Cycle Inventory Database (AusLCI)*. https://www.auslci.com.au
4. Federal Ministry for Housing, Urban Development and Building. *ÖKOBAUDAT*. https://www.oekobaudat.de
