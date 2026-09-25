"""Publication figures: every maker draws for the reference tunnels, in the three formats, through the API too."""
import pytest

pytest.importorskip("matplotlib")
from tunco2pro import figures as F  # noqa: E402
from tunco2pro.gisbim import example_project  # noqa: E402


def test_project_figures_metro():
    p = example_project("metro")
    for name in ("route", "suitability", "items", "levers", "se-penetration", "pathway", "machines"):
        for fmt in ("pdf", "svg"):
            data, numbers = F.render(name, p, fmt)
            assert len(data) > 1000 and isinstance(numbers, dict)
    png, _ = F.render("levers", p, "png", dpi=150)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_optimisation_figures_hydro():
    p = example_project("hydro")
    opt = F.optimise_zones(p, pop_size=12, n_gen=6)
    assert 0 < opt["saving_pct"] < 60 and len(opt["zones"]) == len(p.route.zones)
    data, d = F.render("route-optimisation", p, "pdf", opt=opt)
    assert len(data) > 1000
    _, d = F.render("pareto", p, "pdf", opt=opt)
    assert d["zone"] and d["points"]


def test_project_free_and_errors():
    data, d = F.render("examples", fmt="pdf")
    assert len(data) > 1000 and "metro" in d
    for name in ("examples-composition", "examples-levers", "benchmark"):  # examples-pathway runs four route optimisations; covered by the chapter script
        data, d = F.render(name, fmt="svg")
        assert len(data) > 1000
    _, d = F.render("design-space", example_project("hydro"), "pdf", n=9)
    assert d["zone"] == "Fault zone" and d["fos_min"] == 1.5
    with pytest.raises(ValueError):
        F.render("route", example_project("metro").model_copy(update={"route": None}))
    with pytest.raises(ValueError):
        F.render("no-such-figure")


def test_api_figure():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from tunco2pro.api import app
    c = TestClient(app)
    assert set(c.get("/api/figures").json()["figures"]) == set(F.FIGURES)
    r = c.post("/api/figures/levers?fmt=svg", json={"project": example_project("metro").model_dump(mode="json")})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
    assert c.post("/api/figures/route?fmt=pdf", json={"project": {}}).status_code == 422
