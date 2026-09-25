"""Command line: ``tunco2pro serve`` | ``tunco2pro assess in.json [-o report.xlsx] [--v1]``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tunco2pro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="Run the web app and API")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8000)
    a = sub.add_parser("assess", help="Assess a project JSON file")
    a.add_argument("input", nargs="?", help="Project JSON (omit for the default case)")
    a.add_argument("-o", "--xlsx", help="Write Excel report")
    a.add_argument("--v1", action="store_true", help="Reproduce TunCO2 v1 Power BI arithmetic")
    sub.add_parser("defaults", help="Print the default project JSON")
    e = sub.add_parser("examples", help="Compare the four example tunnels (Metro, Railway, Road, Hydro)")
    e.add_argument("-o", "--csv", help="Write the comparison table as CSV")
    e.add_argument("--save", metavar="DIR", help="Also save each example as a project JSON in DIR")
    f = sub.add_parser("figures", help="Publication figures (PDF, SVG, PNG at 1000 dpi) from a project or the reference tunnels")
    f.add_argument("input", nargs="?", help="Project JSON, or an example key (metro, railway, road, hydro); omit for the reference-tunnel figures only")
    f.add_argument("-o", "--dir", default="figures", help="Output folder (default: figures)")
    f.add_argument("-n", "--names", nargs="*", help="Figure names (default: all that apply); see --list")
    f.add_argument("-f", "--formats", nargs="*", default=["pdf", "svg", "png"])
    f.add_argument("--list", action="store_true", help="List the figures and exit")
    args = ap.parse_args(argv)

    if args.cmd == "figures":
        return _figures(args)

    if args.cmd == "serve":
        from .api import run
        run(args.host, args.port); return 0
    if args.cmd == "examples":
        return _examples(args)
    from .models import ProjectInput
    if args.cmd == "defaults":
        print(ProjectInput().model_dump_json(indent=2)); return 0
    from .carbon import assess, strategies
    from .factors import load_library
    p = ProjectInput.model_validate_json(Path(args.input).read_text()) if args.input else ProjectInput()
    if args.v1:
        p = p.model_copy(update={"factor_set": "v1"})
    res = assess(p, compat_v1=args.v1)
    d = res.to_dict()
    print(f"{p.name}: {d['total_kgCO2e_per_m']:.0f} kgCO2e/m  |  {d['total_tCO2e']:.0f} tCO2e over {p.tunnel_length_m:g} m")
    for m, v in d["modules_kgCO2e_per_m"].items():
        print(f"  {m:6s} {v:10.1f} kgCO2e/m")
    for w in res.warnings:
        print("  ! " + w)
    if args.xlsx:
        from .report import build_workbook
        lib = load_library(p.factor_set).with_overrides(p.factor_overrides)
        Path(args.xlsx).write_bytes(build_workbook(p, res, lib, strategies(p, res, compat_v1=args.v1)))
        print("Report written:", args.xlsx)
    return 0


def _examples(args):
    import csv
    from .gisbim import compare_examples
    rows = compare_examples()["examples"]
    cols = [("name", "Example"), ("machine_label", "TBM"), ("tbm_diameter_m", "D (m)"), ("length_m", "Length (m)"),
            ("total_tCO2e", "tCO2e"), ("kgCO2e_per_m", "kgCO2e/m"), ("kgCO2e_per_m3_excavated", "kgCO2e/m3 exc."),
            ("tCO2e_per_functional_unit", "tCO2e per track/lane-km"), ("min_fos", "min FoS"), ("machine_worst_rating", "TBM fit")]
    print("  ".join(f"{h:>14s}" for _, h in cols))
    for r in rows:
        print("  ".join((f"{r[k]:>14,.2f}" if k == "tbm_diameter_m" else f"{r[k]:>14,.1f}") if isinstance(r[k], float) else f"{str(r[k]):>14s}" for k, _ in cols))
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            mods = ["A1-A3", "A4", "A5"]
            w.writerow([h for _, h in cols] + [f"{m} (kgCO2e/m)" for m in mods])
            for r in rows:
                w.writerow([r[k] for k, _ in cols] + [round(r["modules_kgCO2e_per_m"][m], 1) for m in mods])
        print("Written:", args.csv)
    if args.save:
        Path(args.save).mkdir(parents=True, exist_ok=True)
        for r in rows:
            Path(args.save, f"example_{r['key']}.json").write_text(json.dumps(r["project"], indent=1))
        print("Projects saved in", args.save)
    return 0


def _figures(args):
    from . import figures as F
    if args.list:
        for k, v in F.FIGURES.items():
            print(f"{k:20s} {v}")
        return 0
    project = None
    if args.input:
        from .gisbim import EXAMPLES, example_project
        from .models import ProjectInput
        project = example_project(args.input) if args.input in EXAMPLES else ProjectInput.model_validate(json.loads(Path(args.input).read_text()))
    names = args.names or ([n for n in F.FIGURES if n not in F.PROJECT_FREE] if project else []) + sorted(F.PROJECT_FREE)
    out = Path(args.dir); out.mkdir(parents=True, exist_ok=True)
    opt = None
    for n in names:
        opts = {}
        if n in ("route-optimisation", "pareto"):
            opt = opt or F.optimise_zones(project)
            opts["opt"] = opt
        for fmt in args.formats:
            data, _ = F.render(n, project, fmt, **opts)
            (out / f"{n}.{fmt}").write_bytes(data)
        print("wrote", out / n, ",".join(args.formats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
