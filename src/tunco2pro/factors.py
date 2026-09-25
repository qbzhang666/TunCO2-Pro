"""Versioned emission-factor library with provenance.

Every factor carries its unit, source and NSW data-quality tier so that each
line of a report can state where its number came from (NSW Embodied Carbon
Measurement Technical Guide, 2025: EF hierarchy tiers 1-4).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

import numpy as np

LIBRARY_VERSIONS = {
    "current": "2026.09 (NGA 2026; NABERS NEFD v2026.2; DESNZ 2026 freight)",
    "v1": "v1 (TunCO2 Power BI, 2025)",
}
LIBRARY_VERSION = LIBRARY_VERSIONS["current"]

# Closest equivalents between the v1 transport names and the current (DESNZ 2026) names.
V1_TO_CURRENT = {
    "Road, average laden": "Road, HGV average (average laden)",
    "Road, fully laden": "Road, HGV average (fully laden)",
    "Road, articulated truck": "Road, articulated average (average laden)",
    "Road, truck 40 t": "Road, articulated >33 t (average laden)",
    "Road, truck 28 t": "Road, rigid >17 t (average laden)",
    "Road, truck 16 to 28 t": "Road, rigid >17 t (average laden)",
    "Road, truck 3.5 to 16 t": "Road, rigid 7.5-17 t (average laden)",
    "Road, rigid truck": "Road, rigid average (average laden)",
    "Road, van 3.5 t": "Road, van <3.5 t (diesel)",
    "Rail": "Rail, freight train",
    "Sea": "Sea, container ship (average)",
    "Sea, container ship": "Sea, container ship (average)",
    "Sea, bulk carrier": "Sea, bulk carrier (average)",
    "Air": "Air freight, long-haul (with RF)",
    "Air, international": "Air freight, long-haul (with RF)",
    "Air, domestic": "Air freight, short-haul (with RF)",
    "Steel rebar": "Reinforcing steel - NEFD default",
    "Steel rebar, world average": "Reinforcing steel - NEFD average",
    "Hot rolled structural steel": "Structural steel, hot rolled - NEFD default",
}
CURRENT_TO_V1 = {
    "Road, HGV average (average laden)": "Road, average laden",
    "Road, HGV average (fully laden)": "Road, fully laden",
    "Road, articulated average (average laden)": "Road, articulated truck",
    "Road, articulated >33 t (average laden)": "Road, truck 40 t",
    "Road, articulated >33 t (fully laden)": "Road, truck 40 t",
    "Road, rigid average (average laden)": "Road, rigid truck",
    "Road, rigid >17 t (average laden)": "Road, truck 16 to 28 t",
    "Road, rigid 7.5-17 t (average laden)": "Road, truck 3.5 to 16 t",
    "Road, rigid 3.5-7.5 t (average laden)": "Road, truck 3.5 to 16 t",
    "Road, van <3.5 t (diesel)": "Road, van 3.5 t",
    "Rail, freight train": "Rail",
    "Sea, container ship (average)": "Sea, container ship",
    "Sea, bulk carrier (average)": "Sea, bulk carrier",
    "Sea, general cargo (average)": "Sea",
    "Air freight, short-haul (with RF)": "Air, domestic",
    "Air freight, long-haul (with RF)": "Air, international",
    "Reinforcing steel - NEFD default": "Steel rebar",
    "Reinforcing steel - NEFD average": "Steel rebar, world average",
    "Structural steel, hot rolled - NEFD default": "Hot rolled structural steel",
}


@dataclass(frozen=True)
class Factor:
    key: str
    category: str
    name: str
    value: float
    unit: str
    source: str
    nsw_tier: int
    notes: str = ""


class FactorLibrary:
    def __init__(self, factors: dict[str, Factor], concrete_db: list[dict], version: str,
                 factor_set: str = "current", nefd_concrete: list[dict] | None = None):
        self._f = factors
        self.concrete_db = concrete_db
        self.version = version
        self.factor_set = factor_set
        self.nefd_concrete = nefd_concrete or []
        self.substitutions: list[str] = []

    # --- lookup -----------------------------------------------------------
    def __getitem__(self, key: str) -> Factor:
        try:
            return self._f[key]
        except KeyError as e:
            raise KeyError(f"Unknown factor '{key}'. Available: {sorted(self._f)}") from e

    def value(self, key: str) -> float:
        return self[key].value

    def by_category(self, category: str) -> list[Factor]:
        return [f for f in self._f.values() if f.category == category]

    def by_name(self, category: str, name: str) -> Factor:
        for f in self.by_category(category):
            if f.name == name:
                return f
        alt = (CURRENT_TO_V1 if self.factor_set == "v1" else V1_TO_CURRENT).get(name)
        if alt:
            for f in self.by_category(category):
                if f.name == alt:
                    msg = f"'{name}' is not in the {self.factor_set} factor set; used '{alt}'."
                    if msg not in self.substitutions:
                        self.substitutions.append(msg)
                    return f
        raise KeyError(f"No {category} factor named '{name}' in the {self.factor_set} factor set")

    def get(self, key: str, fallback: str | None = None) -> Factor:
        if key in self._f:
            return self._f[key]
        if fallback and fallback in self._f:
            self.substitutions.append(f"Factor '{key}' is not in the {self.factor_set} set; used '{fallback}'.")
            return self._f[fallback]
        return self[key]

    def nefd_concrete_ecf(self, fc_mpa: float, basis: str = "default") -> tuple[float, str]:
        """NABERS NEFD concrete in-situ factor for the strength band containing fc."""
        if not self.nefd_concrete:
            raise ValueError("NEFD concrete bands are only available in the current factor set")
        for b in self.nefd_concrete:
            if fc_mpa <= float(b["upper_mpa"]):
                v = float(b["default_kg_m3" if basis == "default" else "average_kg_m3"])
                lo = [x for x in self.nefd_concrete if float(x["upper_mpa"]) < float(b["upper_mpa"])]
                lo_v = float(lo[-1]["upper_mpa"]) if lo else 0
                band = f">{lo_v:g} to <={float(b['upper_mpa']):g} MPa" if float(b["upper_mpa"]) < 9999 else f">{lo_v:g} MPa"
                return v, f"NABERS NEFD v2026.2, concrete in-situ {band}, {basis}"
        raise ValueError("fc out of range")

    def all(self) -> list[Factor]:
        return list(self._f.values())

    def with_overrides(self, overrides: dict[str, float] | None) -> "FactorLibrary":
        """Project-specific values (e.g. an EPD) replace library values; marked tier 1."""
        if not overrides:
            return self
        f = dict(self._f)
        for k, v in overrides.items():
            base = f.get(k)
            if base is None:
                raise KeyError(f"Cannot override unknown factor '{k}'")
            f[k] = Factor(k, base.category, base.name, float(v), base.unit,
                          "Project override (user supplied)", 1, "Replaces library value")
        return FactorLibrary(f, self.concrete_db, self.version + " + project overrides",
                             self.factor_set, self.nefd_concrete)

    # --- concrete ECF regression (v1 'Database' page) ----------------------
    def concrete_regression(self, locations: list[str] | None = None,
                            types: list[str] | None = None) -> tuple[float, float, int]:
        """Least-squares ECF = slope * fc + intercept over the filtered database.

        Mirrors DAX measures Slope_Database / Intercept_Database.
        Returns (slope [kgCO2e/m3/MPa], intercept [kgCO2e/m3], n).
        """
        rows = self.concrete_db
        if locations:
            rows = [r for r in rows if r["Location"] in locations]
        if types:
            rows = [r for r in rows if r["Type"] in types]
        if len(rows) < 2:
            raise ValueError("Concrete regression needs at least two records after filtering")
        x = np.array([float(r["Compressive Strength"]) for r in rows])
        y = np.array([float(r["Carbon Emission Factor"]) for r in rows])
        slope = float(((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum())
        return slope, float(y.mean() - slope * x.mean()), len(rows)


def fit_user_points(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Linear fit through user (fc, ECF) points; mirrors Slope_Define/Intercept_Define."""
    pts = [(x, y) for x, y in points if x != 0]
    if len(pts) == 1:
        return 0.0, pts[0][1]
    x = np.array([p[0] for p in pts]); y = np.array([p[1] for p in pts])
    slope = float(((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum())
    return slope, float(y.mean() - slope * x.mean())


def _data_path(name: str) -> Path:
    return Path(str(resources.files("tunco2pro") / "data" / name))


@lru_cache(maxsize=8)
def _load(factor_set: str, factors_csv: str | None, concrete_csv: str | None):
    fpath = Path(factors_csv) if factors_csv else _data_path("factors.csv")
    cpath = Path(concrete_csv) if concrete_csv else _data_path("concrete_ecf_database.csv")
    factors: dict[str, Factor] = {}
    with open(fpath, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("set", "current") != factor_set:
                continue
            factors[r["key"]] = Factor(r["key"], r["category"], r["name"], float(r["value"]),
                                       r["unit"], r["source"], int(r["nsw_tier"]), r.get("notes", ""))
    with open(cpath, newline="", encoding="utf-8") as fh:
        concrete = list(csv.DictReader(fh))
    nefd = []
    if factor_set == "current":
        with open(_data_path("nefd_concrete.csv"), newline="", encoding="utf-8") as fh:
            nefd = list(csv.DictReader(fh))
    return factors, concrete, nefd


def load_library(factor_set: str = "current", factors_csv: str | None = None,
                 concrete_csv: str | None = None) -> FactorLibrary:
    """A fresh library object (cheap; files are cached) for the chosen factor set."""
    if factor_set not in LIBRARY_VERSIONS:
        raise ValueError(f"factor_set must be one of {list(LIBRARY_VERSIONS)}")
    factors, concrete, nefd = _load(factor_set, factors_csv, concrete_csv)
    return FactorLibrary(dict(factors), concrete, LIBRARY_VERSIONS[factor_set], factor_set, nefd)
