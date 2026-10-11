"""Concrete ECF regression with groups held only as sufficient statistics (v0.2.1).

The reference values are the regressions of v0.2.0, computed from the full
236 record-level rows; the split into records and summary groups must
reproduce them exactly.
"""
import csv

import pytest

from tunco2pro.factors import load_library

REF = [  # (locations, types) -> (slope, intercept, n) from v0.2.0
    ((None, None), (5.669450067556279, 126.5775867115787, 236)),
    ((["AUSTRALIA", "UK"], None), (6.0874737947478845, 120.83260229332907, 135)),
    ((["UK"], None), (4.250631099544567, 146.90798959011065, 100)),
    ((["UK"], ["fly ash"]), (4.208197787898504, 162.1780091086532, 30)),
    ((["UK", "CANADA"], ["fly ash", "SCM", "In Situ"]), (4.071036154403771, 151.92741708952505, 84)),
]


@pytest.mark.parametrize("factor_set", ["current", "v1"])
@pytest.mark.parametrize("filt,ref", REF)
def test_regression_matches_v020(factor_set, filt, ref):
    s, b, n = load_library(factor_set).concrete_regression(*filt)
    assert n == ref[2]
    assert s == pytest.approx(ref[0], rel=1e-10) and b == pytest.approx(ref[1], rel=1e-10)


def test_no_ice_records_bundled():
    lib = load_library()
    assert not [r for r in lib.concrete_db if r["Database"] == "ICE"]
    assert {g["Database"] for g in lib.concrete_summary} == {"ICE"}
    assert "UK" in {g["Location"] for g in lib.concrete_groups()}


def test_extra_records_replace_summary_groups(tmp_path):
    # a user-held record file for one summary group replaces that group's statistics
    f = tmp_path / "extra.csv"
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["No.", "Location", "Database", "Type", "Substitute Content", "Compressive Strength", "Carbon Emission Factor"])
        w.writerow([1, "UK", "ICE", "fly ash", 0, 20, 200.0])
        w.writerow([2, "UK", "ICE", "fly ash", 0, 40, 300.0])
    s, b, n = load_library(ecf_extra=str(f)).concrete_regression(["UK"], ["fly ash"])
    assert (n, s, b) == (2, pytest.approx(5.0), pytest.approx(100.0))
    assert load_library(ecf_extra=str(f)).concrete_regression(["UK"])[2] == 72  # 2 + 70 from the other groups
