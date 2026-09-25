# Changelog

## 0.2.0 (September 2026)

- First push to github.com/qbzhang666/TunCO2-Pro: copyright, `CITATION.cff`,
  references to the TUST Part 1-3 papers; the v1 Power Query reference no
  longer carries local file paths.

- Volume-loss settlement screening (`settlement.py`): Gaussian trough per
  ground zone (S_max, i = K z₀, maximum slope, horizontal movement and strain,
  longitudinal profile about the face), with V_L and K entered for the project
  or the zone or estimated from the ground, the machine and the face-pressure
  mode; Rankin (1988) damage category; SLS limits on settlement and slope in
  `ProjectInput.settlement`, checked in the route assessment (warnings, `S mm`
  column of the route table, headline tile). `POST /api/settlement` and
  `/api/settlement/trough`; figure `settlement` (Step 8, `tunco2pro figures`);
  `docs/EQUATIONS.md`.
- Route zones accept `volume_loss_pct` and `trough_k`.
- Route table: input columns grouped (Ground; Water and soil; Design
  overrides t, f'c, x₀, V_L, K; All) so the results columns stay in view;
  torque moved out of the table (route figure and TBM step). Lever settings
  labelled with units. First step states the usual path through the app.
  Em dashes removed from the interface and the documents.
- Lining optimisation: SPEA2 and MOEA/D added beside NSGA-II and NSGA-III,
  with the SBX and polynomial-mutation settings of TunCO2 v1 (Part 3), so the
  two-objective problem of the paper (lining carbon against FoS, with and
  without the installation distance) runs with any of its three algorithms;
  selectable in Step 5 and `OptimiseInput.algorithm`.

## 0.1.0 (September 2026)

First public release, MIT licence. This is the version used for Chapter 7,
*Digitisation for Sustainability*, of *Digital Underground Engineering*: the
chapter's figures, tables, exercises and supplementary videos are generated
from it (`tools/` of the chapter package and `docs/EXERCISES.md`).

- Upfront carbon (EN 15978 A1–A5) per section and along a georeferenced route,
  zone by zone, with functional units per metre, per m³ excavated and per
  track/lane-km.
- GIS → BIM planning bridge: plan line, geological long section and CRS
  registered into a route; GeoJSON, Blender package and georeferenced IFC 4.3.
- Six machine types with ground applicability, JSCE face-support pressure,
  thrust and cutterhead mechanics (`energy_method = "components"` by default)
  with a P10–P90 excavation-energy band; slurry circuit from first principles.
- Convergence-confinement stability and NSGA-II/III lining optimisation per
  zone; decarbonisation levers alone and combined.
- Versioned emission-factor library (factor set 2026.09) with source and
  data-quality tier; Excel report, REST API and browser application with
  scenarios, linked map, table, charts and 3D model, and a Help menu.
- Four synthetic reference tunnels (Metro, Railway, Road, Hydro).
- Publication figures from the engine (`figures.py`): sixteen figures in PDF,
  SVG or PNG at 1000 dpi from Step 8 of the app, `POST /api/figures/{name}`
  or `tunco2pro figures`; the chapter's data figures are produced this way.
- Change from the pre-release: the EPB equivalent-friction value 0.3 is
  retired in favour of the components model (`docs/MIGRATION.md`, v2.1).
