# GIS → BIM planning bridge

## Frame
Local metres about the project origin in the CRS file: x = E − E₀, y = N − N₀, z = height − h₀.
Large projected coordinates stay out of the model (no single-precision jitter in viewers); any Blender scene
or IFC model that uses the same origin overlays the outputs without transformation.
Geodesy: Krüger n-series Transverse Mercator (sub-millimetre within a zone) for UTM south and MGA zones.

## Inputs
| Input | Format |
| --- | --- |
| Plan line | CSV: `chainage_m` (or `chainage_km`), `easting`, `northing`, `ground_m` |
| Long section | JSON: `sheets[].stations[]` with `chainage_m`, `surface_rl_m`, `units[{unit, top_rl_m, base_rl_m}]`, `structure_top_rl_m`/`structure_base_rl_m` or `control_line_rl_m` |
| CRS | JSON: `epsg`, `crs_name`, `origin{easting, northing, height, height_datum}` |
| Unit parameters | CSV like `data/ground_units.csv` (indicative generic defaults) |

Templates: the four synthetic examples in `src/tunco2pro/data/examples/{metro,railway,road,hydro}/`
(also downloadable from the app, Route & ground ▸ Corridor import).

## Method
1. Registration: plan-line chainage s = s₀ + (CH − CH₀), s₀ by least squares on ground surfaces (median bias removed).
2. Alignment: every 5 m; tunnel axis = mid-height of the drawn structure (or control line + offset).
3. Zones: dominant unit across a face of the TBM diameter; rock ≥ 90 % rock area, soil ≤ 10 %, else mixed;
   runs shorter than the minimum length are merged. Cover = surface − axis; γ = σᵥ/H from the overburden column;
   k = most permeable soil unit in a mixed face.
4. TBM applicability per zone (`tbm_types.applicability`), carbon and CCM per zone (`route.assess_route`).

## Outputs
- `/api/gis/geojson`: centreline and zones (lon/lat), with carbon, FoS and TBM ratings.
- `/api/gis/blender`: zip: `tunco2pro_scene.json`, `tunco2pro_route.glb`, `<type>.glb`, GeoJSON, `tunco2_to_blender.py`.
  In Blender: `blender --python tunco2_to_blender.py -- <folder>`. Tested headless with bpy 5.0.
- `/api/geometry?fmt=ifc`: IFC 4.3 in metres with IfcProjectedCRS + IfcMapConversion when the route has a CRS.

## Limits
- Unit parameters and rock quality are generic placeholders.
- Enter a groundwater depth to rate water head on open-face machines.
- TBM models are generic representations on a common envelope, scaled to the project diameter.
