import math
import pytest
from tunco2pro.ccm import Ground, Support, solve
from reference_v1_ccm import v1_fos

CASES = [
    # sigma3, r0, c, phi, Em, v, Ec, vc, tc, sigma_cc, xi0
    (5.4, 3.64, 0.01, 30, 500, 0.25, 30000, 0.2, 0.252, 20, 0.0),
    (5.4, 3.64, 0.01, 30, 500, 0.25, 30000, 0.2, 0.30, 40, 2.0),
    (3.0, 3.30, 0.30, 35, 2000, 0.25, 32000, 0.2, 0.35, 50, 4.0),
    (8.0, 3.64, 0.50, 28, 1500, 0.30, 34000, 0.2, 0.40, 45, 1.0),
]


@pytest.mark.parametrize("c", CASES)
def test_matches_v1_sympy(c):
    s3, r0, coh, phi, Em, v, Ec, vc, tc, fc, xi0 = c
    ref_fos, ref_p, ref_u = v1_fos(*c)
    r = solve(Ground(p0_mpa=s3, cohesion_mpa=coh, friction_deg=phi, modulus_mpa=Em, poisson=v),
              Support(radius_m=r0, thickness_m=tc, concrete_ucs_mpa=fc, concrete_modulus_mpa=Ec,
                      concrete_poisson=vc, install_distance_m=xi0), v1_plastic_branch=True)
    assert r.p_mob == pytest.approx(ref_p, rel=1e-6)
    assert r.fos == pytest.approx(ref_fos, rel=1e-6)
    assert r.u_mob == pytest.approx(ref_u, rel=1e-6)


def test_elastic_branch_used_above_pcr():
    g = Ground(p0_mpa=2.0, cohesion_mpa=2.0, friction_deg=40, modulus_mpa=20000)  # Pcr < 0: elastic
    r = solve(g, Support())
    assert not r.plastic
    assert math.isfinite(r.fos) and r.fos > 0
