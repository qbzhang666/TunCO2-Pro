"""Verbatim algorithm of TunCO2 v1 Stability.py (sympy), used as a regression oracle."""
import numpy as np
import sympy as sp


def v1_fos(sigma3, r0, c, phi, Em, v, Ec, vc, tc, sigma_cc, xi0):
    sigma_cm = 2 * c * np.cos(np.deg2rad(phi)) / (1 - np.sin(np.deg2rad(phi)))
    k = (1 + np.sin(np.deg2rad(phi))) / (1 - np.sin(np.deg2rad(phi)))
    po = sigma3
    Pcr = (2 * po - sigma_cm) / (1 + k)
    p_i = sp.symbols('p_i')
    rp = r0 * (2 * (po * (k - 1) + sigma_cm) / ((1 + k) * ((k - 1) * p_i + sigma_cm)))**(1/(k-1))
    uip = r0 * (1 + v) * (2 * (1 - v) * (po - Pcr) * (rp/r0)**2 - (1 - 2*v) * (po - p_i)) / Em
    rpf = float(rp.subs(p_i, 0))
    u_lamda1 = min(float(uip.subs(p_i, 0)), r0)
    uf = (1 / 3) * np.exp(-0.15 * rpf / r0) * u_lamda1
    u = sp.symbols('u')
    xa = -2 * rpf / 3 * sp.log((1 - u / u_lamda1) / (1 - uf / u_lamda1))
    ui0 = float(sp.solve(sp.Eq(xa, xi0), u)[0])
    kc = Ec * (r0**2 - (r0 - tc)**2) / ((1 + vc) * ((1 - 2 * vc) * r0**2 + (r0 - tc)**2))
    psc_max = sigma_cc / 2 * (1 - (r0 - tc)**2 / r0**2)
    p_mob = float(sp.nsolve(sp.Eq(uip, p_i * r0 / kc + ui0), p_i, 0))
    u_mob = float(uip.subs(p_i, p_mob).evalf())
    return psc_max / p_mob, p_mob, u_mob
