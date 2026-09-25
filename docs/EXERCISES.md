# Student exercises: embodied carbon of TBM tunnels with the four examples

These exercises use the four bundled example tunnels (Metro, Railway, Road and Hydro) to show how the
tunnel's size, the machine type, the ground and design choices drive upfront embodied carbon (EN 15978
modules A1–A5). They suit final-year and postgraduate students in civil, geotechnical or tunnel engineering.

* **Time:** about 3 hours for Exercises 1–7; Exercise 8 is optional.
* **You need:** the TunCO2 Pro app running (Setup below), a spreadsheet for your results, and the worksheet at
  the end of this page.
* **Background reading:** `docs/EQUATIONS.md` (all equations), `docs/CUTTERHEAD.md` (torque and excavation
  energy), `docs/GIS_BIM.md` (route and ground model).

> The examples are synthetic: invented terrain, geology and coordinates, and indicative generic ground
> parameters. Your results illustrate trends and orders of magnitude. They are not design values for any real
> project.

## Setup

**Windows:** double-click `Start-TunCO2Pro.bat`. The first start builds the Python environment (a few
minutes), then the app opens in your browser.

**Any platform:**

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[all]"
tunco2pro serve                                    # then open http://127.0.0.1:8000
```

The app leads you through eight steps: **1 Project → 2 Route & ground → 3 TBM selection → 4 Lining &
materials → 5 Stability & design → 6 Carbon results → 7 Scenarios → 8 Model & export**. The headline results
stay in the bar at the top. Hover over any field to see what it means and its allowed range. Some exercises
need *File ▸ Show advanced parameters*.

**Before each exercise**, reload the example you need (Project step ▸ example card). This undoes your
changes from the previous exercise. Save anything you want to keep with *Save as scenario* first.

---

## Exercise 1: Where does the carbon come from? (Metro tunnel)

1. In the Project step, open the **Metro tunnel** example. Go through steps 2–6 without changing anything.
2. In **Carbon results**, record the total (tCO₂e), the carbon per metre (kgCO₂e/m) and the A1–A3, A4 and A5
   shares.
3. List the five largest items and their share of the total.

**Questions**

* a) Which module dominates, and which two items make up most of it?
* b) What is excavation energy's share of the total? Spoil removal's? What does this tell you about where
  design effort pays off?
* c) Look at a lining item's calculation note. Write out its calculation by hand: ring area × density or
  quantity × emission factor.

## Exercise 2: The effect of size (Metro vs Road, both EPB)

The Road tunnel uses the same machine type as the Metro at 15.6 m instead of 7.25 m.

1. Go to **Scenarios ▸ Compare examples**. Switch the basis between *per m*, *per m³ excavated*,
   *per track/lane-km* and *total*.
2. Record the Metro and Road values on each basis.

**Questions**

* a) The diameter ratio is 15.6 / 7.25 = 2.15. Compare the carbon per metre ratio with D and with D². Explain
  the result using the lining ring area and the excavated area.
* b) Which basis makes the two tunnels look most similar? Which basis is the right one for a planning
  decision between one 3-lane bore and two smaller bores? Justify your choice.
* c) Look at the torque (T) column in the Road zone table. Torque grows roughly with D³, while carbon per
  metre grows roughly with D². Use `docs/CUTTERHEAD.md` §2 to explain why.

## Exercise 3: The effect of machine type (Metro EPB vs Railway slurry, both 7.25 m)

1. Compare Metro and Railway in the example comparison and in the *A5 by item* chart.
2. Open **Railway** and go to **TBM selection**. Note how suitable each of the six machine types is in each
   zone. Do the same for **Metro**.

**Questions**

* a) Which A5 items does the slurry machine have that the EPB does not? Which is larger: the slurry machine's
  saving in cutterhead energy, or the energy of its slurry circuit? Then find the A5 item that explains why the
  Railway total is still lower, and say whether that is a property of the machine or of the drive.
* b) Explain why slurry cutterhead torque is well below EPB torque at the same diameter. Hint: what fills the
  excavation chamber in each machine?
* c) In Route & ground, find the Metro zone rated *marginal* for EPB and read the reason in TBM selection.
  Then choose a *Silty sand* zone (rated suitable) and raise its permeability *k* from 1e-6 to 1e-5, 1e-4 and
  1e-3 m/s, then lower its fines content to 10 %. Using the selection limits in `docs/EQUATIONS.md` (EPB without
  soil conditioning to *k* ≤ 1e-6 m/s; with conditioning to 1e-4 m/s; EPB needs at least 15 % fines), explain
  each change in the EPB and slurry ratings.
* d) Carbon aside, what else would decide between EPB and slurry for this route?

## Exercise 4: Excavation energy from cutterhead mechanics

The app works out excavation energy from how the cutterhead works: E = F · 1 m + 2πT / p, where p is the
penetration per revolution.

1. Open **Metro**. In **Carbon results**, read the note on *TBM excavation energy*: it gives the torque T, the
   penetration and the specific energy, with the P10–P90 range.
2. Check the energy per metre by hand from T, p and the thrust F in the zone table.
3. In **Scenarios ▸ Compare examples**, record the P10–P50–P90 specific energy (kWh/m³) for all four
   tunnels.

**Questions**

* a) For a soil zone, roughly what share of the torque comes from cutting the ground, and what share from
  friction? (See the component breakdown in `docs/CUTTERHEAD.md`.) What does this mean for how specific
  energy responds when penetration drops by half?
* b) Why is the P10–P90 range much wider for the Road tunnel than for the Hydro tunnel?
* c) *(Advanced)* Use *File ▸ Save project*. In the JSON, add
  `"cutterhead_overrides": {"tau0_kpa": 20}` under `tbm.loads`. This stands for poorly conditioned spoil.
  Reopen the project (*File ▸ Open project*). How much do excavation energy and total carbon change? Is soil
  conditioning a significant decarbonisation lever for this tunnel?

## Exercise 5: Face support pressure

1. Open **Metro** and go to **TBM selection ▸ Face support pressure (JSCE)**.
2. In the zone table, record the support pressure *p* (kPa) for the shallowest and the deepest zone.
3. Change the fluctuation allowance Δp from 20 to 50 kPa. Then change the earth-pressure coefficient from
   *K0* to *Ka*.

**Questions**

* a) Write out the control pressure p = K·σ′v + u_w + Δp for one zone. What sets its upper bound, and does
  any zone trigger the blow-out warning?
* b) How much do thrust, torque and total carbon change? Explain why face pressure matters so much for
  ground movement and so little for carbon.

## Exercise 6: Stability and lining optimisation (Hydro tunnel)

The Hydro tunnel runs through granite and metasediments at depth with a 10.45 m single shield. The route crosses two fault
zones, and the 0.35 m lining deliberately fails in one of them.

1. Open **Hydro**. In **Stability & design**, find the zone(s) where the factor of safety (FoS) is below the
   criterion.
2. In **Route & ground**, choose *Optimise lining in every zone*, then *Apply optimised designs to the
   zones*.
3. Save the scenarios before and after, and compare them in **Scenarios**.

**Questions**

* a) Why does one fault zone fail when the other fault zone and the granite zones pass? Compare cover,
  in-situ stress and ground strength, and refer to the ground-reaction curve.
* b) After optimisation, how did the lining change in the fault zone and in the competent-rock zones? What
  is the net carbon change for the whole route?
* c) A designer proposes to use the fault-zone lining along the whole tunnel "for simplicity". Estimate the
  carbon cost of that decision.

## Exercise 7: Decarbonisation levers and scenarios

1. Open **Metro** and save it as the scenario *Baseline*.
2. In **Carbon results ▸ Decarbonisation levers**, read the saving from each lever on its own.
3. Create three scenarios, each changing one thing: (i) 50 % supplementary cementitious materials (SCM);
   (ii) a lower-strength concrete grade that still passes the FoS check; (iii) a renewable electricity supply
   for the TBM. Then create a fourth that combines all three.

**Questions**

* a) Rank the levers by saving. Is the combined saving the sum of the separate savings? Why not?
* b) Which lever addresses the largest module? Which one costs the designer nothing but a specification
  change?
* c) Repeat the ranking for the **Hydro** tunnel. Does the ranking change? Explain in terms of the shares
  you found in Exercise 1.

## Exercise 8 (optional): From GIS to BIM

1. Open **Road**. In **Model & export**, download the GeoJSON and the IFC 4.3 model.
2. Open the GeoJSON in QGIS and colour the zones by carbon per metre. Open the IFC in a viewer such as
   BlenderBIM/Bonsai or an online IFC viewer, and find the carbon property sets on the lining.
3. *(Command line)* Run `tunco2pro examples -o compare.csv`. Plot carbon per m³ excavated against diameter
   for the four tunnels.

**Questions**

* a) Which zones would you flag for further ground investigation, and why?
* b) What information would a contractor need to add before this model could support a tender estimate?

---

## Worksheet

| | Metro | Railway | Road | Hydro |
|---|---|---|---|---|
| TBM type, diameter (m) | | | | |
| Length (m) | | | | |
| Total (tCO₂e) | | | | |
| kgCO₂e/m | | | | |
| kgCO₂e/m³ excavated | | | | |
| tCO₂e per track/lane-km | | | | |
| A1–A3 / A4 / A5 (%) | | | | |
| Excavation energy (kgCO₂e/m) | | | | |
| Specific energy P10–P50–P90 (kWh/m³) | | | | |
| Minimum FoS | | | | |
| Share of the route where the machine is suitable (%) | | | | |

## Report (suggested assessment)

Write a two-page technical note to a client choosing between the Metro and Railway configurations for a
new 7 km twin-bore line. Use your results from Exercises 2, 3, 4 and 7. State the assumptions and
limitations of the model, at least three of them: synthetic ground, generic emission factors, the cutterhead
parameter ranges, and the A1–A5 boundary (no operation or end of life).
