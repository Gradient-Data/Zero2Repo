# feature: F01
"""Observation helpers for FP-01 frames, WGS84, and the World Magnetic Model.

C probes are compiled through the sealed harness and linked to the recipe
library. Python observations run in a child interpreter. This module does
not import the product in the pytest process.
"""

from __future__ import annotations

import math
from typing import Sequence

from _harness import HarnessError, RunResult, invoke, product_identity, repo_root, run_python

# ---------------------------------------------------------------------------
# Fixed inputs and tolerances
# ---------------------------------------------------------------------------

STUTTGART_LAT_DEG = 48.783
STUTTGART_LON_DEG = 9.181
STUTTGART_H_M = 300.0
NAMED_ROLL = 0.3
NAMED_PITCH = -0.2
NAMED_YAW = 1.1

WGS84_A_M = 6378137.0
WGS84_F = 1.0 / 298.257223563

SINGLE_ABS = 1.0e-5
LLH_RAD_TOL = 1.0e-10
HEIGHT_M_TOL = 1.0e-4
FLAT_WGS84_M = 1.0
FLAT_SPHERE_M = 10.0
D_MID_DEG = 0.15
D_POLE_DEG = 0.6
I_UNIT_DEG = 15.0
F_UNIT_UT = 20.0
HEADING_SELF_DEG = 0.05
MAG_REL = 1.0e-3
WRAP_D_DEG = 1.0e-3
YEAR_D_DEG = 1.0e-3
H_MIN_UT = 1.0e-6

# Sites used only to *avoid* copying the product's eight-row public table.
_PUBLIC_WMM_ROWS = frozenset(
    (
        (48.137, 11.575),
        (40.712, -74.006),
        (35.689, 139.692),
        (89.9, 0.0),
        (-89.9, 179.9),
        (0.0, 180.0),
        (0.0, -180.0),
        (0.0, 370.0),
    )
)

# NOAA WMM2025 Gauss coefficients (n, m, g, h, gdot, hdot); nT and nT/year.
_WMM2025 = (
    (1, 0, -29351.8, 0.0, 12.0, 0.0),
    (1, 1, -1410.8, 4545.4, 9.7, -21.5),
    (2, 0, -2556.6, 0.0, -11.6, 0.0),
    (2, 1, 2951.1, -3133.6, -5.2, -27.7),
    (2, 2, 1649.3, -815.1, -8.0, -12.1),
    (3, 0, 1361.0, 0.0, -1.3, 0.0),
    (3, 1, -2404.1, -56.6, -4.2, 4.0),
    (3, 2, 1243.8, 237.5, 0.4, -0.3),
    (3, 3, 453.6, -549.5, -15.6, -4.1),
    (4, 0, 895.0, 0.0, -1.6, 0.0),
    (4, 1, 799.5, 278.6, -2.4, -1.1),
    (4, 2, 55.7, -133.9, -6.0, 4.1),
    (4, 3, -281.1, 212.0, 5.6, 1.6),
    (4, 4, 12.1, -375.6, -7.0, -4.4),
    (5, 0, -233.2, 0.0, 0.6, 0.0),
    (5, 1, 368.9, 45.4, 1.4, -0.5),
    (5, 2, 187.2, 220.2, 0.0, 2.2),
    (5, 3, -138.7, -122.9, 0.6, 0.4),
    (5, 4, -142.0, 43.0, 2.2, 1.7),
    (5, 5, 20.9, 106.1, 0.9, 1.9),
    (6, 0, 64.4, 0.0, -0.2, 0.0),
    (6, 1, 63.8, -18.4, -0.4, 0.3),
    (6, 2, 76.9, 16.8, 0.9, -1.6),
    (6, 3, -115.7, 48.8, 1.2, -0.4),
    (6, 4, -40.9, -59.8, -0.9, 0.9),
    (6, 5, 14.9, 10.9, 0.3, 0.7),
    (6, 6, -60.7, 72.7, 0.9, 0.9),
    (7, 0, 79.5, 0.0, -0.0, 0.0),
    (7, 1, -77.0, -48.9, -0.1, 0.6),
    (7, 2, -8.8, -14.4, -0.1, 0.5),
    (7, 3, 59.3, -1.0, 0.5, -0.8),
    (7, 4, 15.8, 23.4, -0.1, 0.0),
    (7, 5, 2.5, -7.4, -0.8, -1.0),
    (7, 6, -11.1, -25.1, -0.8, 0.6),
    (7, 7, 14.2, -2.3, 0.8, -0.2),
    (8, 0, 23.2, 0.0, -0.1, 0.0),
    (8, 1, 10.8, 7.1, 0.2, -0.2),
    (8, 2, -17.5, -12.6, 0.0, 0.5),
    (8, 3, 2.0, 11.4, 0.5, -0.4),
    (8, 4, -21.7, -9.7, -0.1, 0.4),
    (8, 5, 16.9, 12.7, 0.3, -0.5),
    (8, 6, 15.0, 0.7, 0.2, -0.6),
    (8, 7, -16.8, -5.2, -0.0, 0.3),
    (8, 8, 0.9, 3.9, 0.2, 0.2),
    (9, 0, 4.6, 0.0, -0.0, 0.0),
    (9, 1, 7.8, -24.8, -0.1, -0.3),
    (9, 2, 3.0, 12.2, 0.1, 0.3),
    (9, 3, -0.2, 8.3, 0.3, -0.3),
    (9, 4, -2.5, -3.3, -0.3, 0.3),
    (9, 5, -13.1, -5.2, 0.0, 0.2),
    (9, 6, 2.4, 7.2, 0.3, -0.1),
    (9, 7, 8.6, -0.6, -0.1, -0.2),
    (9, 8, -8.7, 0.8, 0.1, 0.4),
    (9, 9, -12.9, 10.0, -0.1, 0.1),
    (10, 0, -1.3, 0.0, 0.1, 0.0),
    (10, 1, -6.4, 3.3, 0.0, 0.0),
    (10, 2, 0.2, 0.0, 0.1, -0.0),
    (10, 3, 2.0, 2.4, 0.1, -0.2),
    (10, 4, -1.0, 5.3, -0.0, 0.1),
    (10, 5, -0.6, -9.1, -0.3, -0.1),
    (10, 6, -0.9, 0.4, 0.0, 0.1),
    (10, 7, 1.5, -4.2, -0.1, 0.0),
    (10, 8, 0.9, -3.8, -0.1, -0.1),
    (10, 9, -2.7, 0.9, -0.0, 0.2),
    (10, 10, -3.9, -9.1, -0.0, -0.0),
    (11, 0, 2.9, 0.0, 0.0, 0.0),
    (11, 1, -1.5, 0.0, -0.0, -0.0),
    (11, 2, -2.5, 2.9, 0.0, 0.1),
    (11, 3, 2.4, -0.6, 0.0, -0.0),
    (11, 4, -0.6, 0.2, 0.0, 0.1),
    (11, 5, -0.1, 0.5, -0.1, -0.0),
    (11, 6, -0.6, -0.3, 0.0, -0.0),
    (11, 7, -0.1, -1.2, -0.0, 0.1),
    (11, 8, 1.1, -1.7, -0.1, -0.0),
    (11, 9, -1.0, -2.9, -0.1, 0.0),
    (11, 10, -0.2, -1.8, -0.1, 0.0),
    (11, 11, 2.6, -2.3, -0.1, 0.0),
    (12, 0, -2.0, 0.0, 0.0, 0.0),
    (12, 1, -0.2, -1.3, 0.0, -0.0),
    (12, 2, 0.3, 0.7, -0.0, 0.0),
    (12, 3, 1.2, 1.0, -0.0, -0.1),
    (12, 4, -1.3, -1.4, -0.0, 0.1),
    (12, 5, 0.6, -0.0, -0.0, -0.0),
    (12, 6, 0.6, 0.6, 0.1, -0.0),
    (12, 7, 0.5, -0.1, -0.0, -0.0),
    (12, 8, -0.1, 0.8, 0.0, 0.0),
    (12, 9, -0.4, 0.1, 0.0, -0.0),
    (12, 10, -0.2, -1.0, -0.1, -0.0),
    (12, 11, -1.3, 0.1, -0.0, 0.0),
    (12, 12, -0.7, 0.2, -0.1, -0.1),
)
_WMM_NMAX = 12
_WMM_EPOCH = 2025.0

_C_PROBE = r"""
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "geodetic_toolbox.h"
#include "magnetic_model.h"

static int fail_usage(void)
{
    fprintf(stderr, "unknown op or argc\n");
    return 2;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        return fail_usage();
    }
    const char *op = argv[1];
    if (strcmp(op, "rpy_to_quat") == 0 && argc == 5) {
        float q[4];
        ins_quat_from_rpy((float)atof(argv[2]), (float)atof(argv[3]),
                          (float)atof(argv[4]), q);
        printf("%.9g %.9g %.9g %.9g\n", q[0], q[1], q[2], q[3]);
        return 0;
    }
    if (strcmp(op, "rpy_roundtrip") == 0 && argc == 5) {
        float q[4], R[9], r, p, y;
        ins_quat_from_rpy((float)atof(argv[2]), (float)atof(argv[3]),
                          (float)atof(argv[4]), q);
        ins_quat_to_rotmat(q, R);
        ins_rotmat_to_rpy(R, &r, &p, &y);
        printf("%.9g %.9g %.9g\n", r, p, y);
        return 0;
    }
    if (strcmp(op, "quat_normalize") == 0 && argc == 6) {
        float q[4] = {(float)atof(argv[2]), (float)atof(argv[3]),
                      (float)atof(argv[4]), (float)atof(argv[5])};
        ins_quat_normalize(q);
        printf("%.9g %.9g %.9g %.9g\n", q[0], q[1], q[2], q[3]);
        return 0;
    }
    if (strcmp(op, "body_to_ned") == 0 && argc == 8) {
        float q[4], R[9], vb[3], vn[3];
        int row, col;
        ins_quat_from_rpy((float)atof(argv[2]), (float)atof(argv[3]),
                          (float)atof(argv[4]), q);
        ins_quat_to_rotmat(q, R);
        vb[0] = (float)atof(argv[5]);
        vb[1] = (float)atof(argv[6]);
        vb[2] = (float)atof(argv[7]);
        vn[0] = vn[1] = vn[2] = 0.0f;
        for (row = 0; row < 3; ++row) {
            for (col = 0; col < 3; ++col) {
                vn[row] += R[row + 3 * col] * vb[col];  /* column-major */
            }
        }
        printf("%.9g %.9g %.9g\n", vn[0], vn[1], vn[2]);
        return 0;
    }
    if (strcmp(op, "llh_to_ecef") == 0 && argc == 5) {
        double xyz[3];
        ins_latlonh_to_ecef(atof(argv[2]) * M_PI / 180.0,
                            atof(argv[3]) * M_PI / 180.0, atof(argv[4]), xyz);
        printf("%.17g %.17g %.17g\n", xyz[0], xyz[1], xyz[2]);
        return 0;
    }
    if (strcmp(op, "ecef_to_llh") == 0 && argc == 5) {
        double xyz[3] = {atof(argv[2]), atof(argv[3]), atof(argv[4])};
        double lat, lon, h;
        ins_ecef_to_latlonh(xyz, &lat, &lon, &h);
        printf("%.17g %.17g %.17g\n", lat, lon, h);
        return 0;
    }
    if (strcmp(op, "llh_roundtrip") == 0 && argc == 5) {
        double xyz[3], lat, lon, h;
        double lat0 = atof(argv[2]) * M_PI / 180.0;
        double lon0 = atof(argv[3]) * M_PI / 180.0;
        double h0 = atof(argv[4]);
        ins_latlonh_to_ecef(lat0, lon0, h0, xyz);
        ins_ecef_to_latlonh(xyz, &lat, &lon, &h);
        printf("%.17g %.17g %.17g\n", lat, lon, h);
        return 0;
    }
    if (strcmp(op, "ecef_roundtrip") == 0 && argc == 5) {
        double xyz0[3] = {atof(argv[2]), atof(argv[3]), atof(argv[4])};
        double lat, lon, h, xyz1[3];
        ins_ecef_to_latlonh(xyz0, &lat, &lon, &h);
        ins_latlonh_to_ecef(lat, lon, h, xyz1);
        printf("%.17g %.17g %.17g\n", xyz1[0], xyz1[1], xyz1[2]);
        return 0;
    }
    if (strcmp(op, "dned_to_dllh") == 0 && argc == 8) {
        float dned[3] = {(float)atof(argv[5]), (float)atof(argv[6]),
                         (float)atof(argv[7])};
        double dllh[3];
        ins_dned_to_dlatlonh(dned, atof(argv[2]) * M_PI / 180.0, atof(argv[4]),
                             dllh);
        printf("%.17g %.17g %.17g\n", dllh[0], dllh[1], dllh[2]);
        return 0;
    }
    if (strcmp(op, "omega_transport") == 0 && argc == 7) {
        float vel[3] = {(float)atof(argv[4]), (float)atof(argv[5]),
                         (float)atof(argv[6])};
        float win[3], wie[3], wen[3];
        ins_calc_omega_n_in(atof(argv[2]) * M_PI / 180.0, atof(argv[3]), vel,
                            win, wie, wen);
        printf("%.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g\n", win[0],
               win[1], win[2], wie[0], wie[1], wie[2], wen[0], wen[1], wen[2]);
        return 0;
    }
    if (strcmp(op, "wmm_all") == 0 && argc == 5) {
        float lat = (float)atof(argv[2]);
        float lon = (float)atof(argv[3]);
        float year = (float)atof(argv[4]);
        float b[3];
        float d = magnetic_declination_deg(lat, lon, year);
        float i = magnetic_inclination_deg(lat, lon);
        float f = magnetic_field_strength_uT(lat, lon);
        magnetic_field_ned_uT(lat, lon, year, b);
        printf("%.9g %.9g %.9g %.9g %.9g %.9g\n", d, i, f, b[0], b[1], b[2]);
        return 0;
    }
    if (strcmp(op, "wmm_mag_span") == 0 && argc == 4) {
        /* |B_ned| over the model epoch, sampled every 1/8 year. */
        float lat = (float)atof(argv[2]);
        float lon = (float)atof(argv[3]);
        float lo = 0.0f, hi = 0.0f;
        for (int k = 0; k <= 40; ++k) {
            float b[3];
            magnetic_field_ned_uT(lat, lon, 2025.0f + 0.125f * (float)k, b);
            float m = sqrtf(b[0] * b[0] + b[1] * b[1] + b[2] * b[2]);
            if (k == 0 || m < lo) lo = m;
            if (k == 0 || m > hi) hi = m;
        }
        printf("%.9g %.9g\n", lo, hi);
        return 0;
    }
    return fail_usage();
}
"""

_PY_PROBE = r"""
import math
import sys

from __PKG__ import ecef_to_llh, llh_to_ecef, rpy_to_quat, wmm_field_ned

if len(sys.argv) < 2:
    raise SystemExit(2)
op = sys.argv[1]
args = [float(a) for a in sys.argv[2:]]
if op == "rpy_to_quat" and len(args) == 3:
    q = rpy_to_quat(*args)
    print("%.17g %.17g %.17g %.17g" % tuple(q))
elif op == "llh_to_ecef" and len(args) == 3:
    xyz = llh_to_ecef(math.radians(args[0]), math.radians(args[1]), args[2])
    print("%.17g %.17g %.17g" % tuple(xyz))
elif op == "ecef_to_llh" and len(args) == 3:
    llh = ecef_to_llh(*args)
    print("%.17g %.17g %.17g" % llh)
elif op == "llh_roundtrip" and len(args) == 3:
    xyz = llh_to_ecef(math.radians(args[0]), math.radians(args[1]), args[2])
    lat, lon, h = ecef_to_llh(*xyz)
    print("%.17g %.17g %.17g" % (lat, lon, h))
elif op == "ecef_roundtrip" and len(args) == 3:
    lat, lon, h = ecef_to_llh(*args)
    xyz = llh_to_ecef(lat, lon, h)
    print("%.17g %.17g %.17g" % xyz)
elif op == "wmm_ned" and len(args) == 3:
    b = wmm_field_ned(*args)
    print("%.17g %.17g %.17g" % tuple(b))
else:
    raise SystemExit(2)
"""


def require_probe_success(result: RunResult) -> str:
    """Return UTF-8 stdout, or raise if the observation cannot be classified."""
    if result.returncode != 0:
        err = ""
        try:
            err = result.stderr_text
        except HarnessError:
            err = "<stderr not utf-8>"
        raise HarnessError(
            f"probe exited {result.returncode} argv={list(result.argv)!r} "
            f"stderr={err!r}"
        )
    if not result.stdout:
        raise HarnessError(f"probe produced empty stdout argv={list(result.argv)!r}")
    return result.stdout_text


def parse_floats(result: RunResult, n: int) -> list[float]:
    """Parse exactly *n* finite floats from stdout; any other shape raises."""
    text = require_probe_success(result).strip()
    parts = text.split()
    if len(parts) != n:
        raise HarnessError(
            f"expected {n} floats, got {len(parts)} from {text!r}"
        )
    values: list[float] = []
    for token in parts:
        try:
            value = float(token)
        except ValueError as exc:
            raise HarnessError(f"not a float: {token!r} in {text!r}") from exc
        if not math.isfinite(value):
            raise AssertionError(f"non-finite observation {value!r} in {text!r}")
        values.append(value)
    return values


def wgs84_ecef_from_geodetic(
    lat_rad: float, lon_rad: float, height_m: float
) -> tuple[float, float, float]:
    """Closed-form WGS84 geodetic → ECEF. Does not call the product."""
    e2 = WGS84_F * (2.0 - WGS84_F)
    slat = math.sin(lat_rad)
    clat = math.cos(lat_rad)
    n = WGS84_A_M / math.sqrt(1.0 - e2 * slat * slat)
    x = (n + height_m) * clat * math.cos(lon_rad)
    y = (n + height_m) * clat * math.sin(lon_rad)
    z = (n * (1.0 - e2) + height_m) * slat
    return x, y, z


def spherical_ecef_from_geodetic(
    lat_rad: float, lon_rad: float, height_m: float
) -> tuple[float, float, float]:
    """Same semi-major axis, no flattening — the PRD's absent ECEF."""
    r = WGS84_A_M + height_m
    clat = math.cos(lat_rad)
    return (
        r * clat * math.cos(lon_rad),
        r * clat * math.sin(lon_rad),
        r * math.sin(lat_rad),
    )


def hamilton_zyx_quaternion(
    roll: float, pitch: float, yaw: float
) -> tuple[float, float, float, float]:
    """Hamilton scalar-first q for R_b_to_n = Rz(yaw) Ry(pitch) Rx(roll)."""
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return (
        cy * cp * cr + sy * sp * sr,
        cy * cp * sr - sy * sp * cr,
        cy * sp * cr + sy * cp * sr,
        sy * cp * cr - cy * sp * sr,
    )


def independent_wmm(
    lat_deg: float, lon_deg: float, year: float, *, alt_km: float = 0.0
) -> tuple[float, float, float]:
    """NOAA WMM2025 spherical-harmonic D (deg), I (deg), F (µT) at MSL.

    Raises if the evaluation is non-finite. Never returns 0.0 to mean
    "could not look up".
    """
    dt = year - _WMM_EPOCH
    g = [[0.0] * (_WMM_NMAX + 1) for _ in range(_WMM_NMAX + 1)]
    h = [[0.0] * (_WMM_NMAX + 1) for _ in range(_WMM_NMAX + 1)]
    for n, m, gv, hv, gd, hd in _WMM2025:
        g[n][m] = gv + dt * gd
        h[n][m] = hv + dt * hd
    scale = [[0.0] * (_WMM_NMAX + 1) for _ in range(_WMM_NMAX + 1)]
    scale[0][0] = 1.0
    for n in range(1, _WMM_NMAX + 1):
        scale[0][n] = scale[0][n - 1] * (2 * n - 1) / n
        delta = 1.0
        for m in range(1, n + 1):
            scale[m][n] = scale[m - 1][n] * math.sqrt(
                (n - m + 1) * (delta + 1.0) / (n + m)
            )
            delta = 0.0
    gg = [[0.0] * (_WMM_NMAX + 1) for _ in range(_WMM_NMAX + 1)]
    hh = [[0.0] * (_WMM_NMAX + 1) for _ in range(_WMM_NMAX + 1)]
    for n in range(1, _WMM_NMAX + 1):
        for m in range(n + 1):
            gg[n][m] = g[n][m] * scale[m][n]
            hh[n][m] = h[n][m] * scale[m][n]
    a_ell = 6378.137
    flatten = 1.0 / 298.257223563
    e2 = flatten * (2.0 - flatten)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    slat = math.sin(lat)
    clat = math.cos(lat)
    n_prime = a_ell / math.sqrt(1.0 - e2 * slat * slat)
    rho = (n_prime + alt_km) * clat
    z_gc = (n_prime * (1.0 - e2) + alt_km) * slat
    radius = math.hypot(rho, z_gc)
    if radius <= 0.0:
        raise HarnessError("WMM geocentric radius is not positive")
    latp = math.atan2(z_gc, rho)
    k = [[0.0] * (_WMM_NMAX + 1) for _ in range(_WMM_NMAX + 1)]
    pnm = [[0.0] * (_WMM_NMAX + 2) for _ in range(_WMM_NMAX + 2)]
    dp = [[0.0] * (_WMM_NMAX + 2) for _ in range(_WMM_NMAX + 2)]
    pnm[0][0] = 1.0
    cos_lat = math.cos(latp)
    sin_lat = math.sin(latp)
    for n in range(1, _WMM_NMAX + 1):
        for m in range(n + 1):
            k[m][n] = (
                0.0
                if n == 1
                else ((n - 1) ** 2 - m * m) / ((2 * n - 1) * (2 * n - 3))
            )
            if n == m:
                pnm[m][n] = cos_lat * pnm[m - 1][n - 1]
                dp[m][n] = cos_lat * dp[m - 1][n - 1] + sin_lat * pnm[m - 1][n - 1]
            else:
                pnm[m][n] = sin_lat * pnm[m][n - 1] - k[m][n] * pnm[m][n - 2]
                dp[m][n] = (
                    sin_lat * dp[m][n - 1]
                    - cos_lat * pnm[m][n - 1]
                    - k[m][n] * dp[m][n - 2]
                )
    cp = [1.0] * (_WMM_NMAX + 1)
    sp = [0.0] * (_WMM_NMAX + 1)
    cp[1] = math.cos(lon)
    sp[1] = math.sin(lon)
    for m in range(2, _WMM_NMAX + 1):
        cp[m] = cp[1] * cp[m - 1] - sp[1] * sp[m - 1]
        sp[m] = sp[1] * cp[m - 1] + cp[1] * sp[m - 1]
    ar = 6371.2 / radius
    xp = yp = zp = bp = 0.0
    for n in range(1, _WMM_NMAX + 1):
        arn2 = ar ** (n + 2)
        x_p = y_p = z_p = 0.0
        for m in range(n + 1):
            gchs = gg[n][m] * cp[m]
            gshc = gg[n][m] * sp[m]
            if m > 0:
                gchs += hh[n][m] * sp[m]
                gshc -= hh[n][m] * cp[m]
            x_p += gchs * dp[m][n]
            y_p += m * gshc * pnm[m][n]
            z_p += gchs * pnm[m][n]
            if abs(cos_lat) < 1e-12 and m == 1:
                bp += arn2 * gshc
                if n > 1:
                    bp *= sin_lat - k[m][n]
        xp += arn2 * x_p
        yp += arn2 * y_p
        zp -= (n + 1) * arn2 * z_p
    yp = bp if abs(cos_lat) < 1e-12 else yp / cos_lat
    dphi = latp - lat
    x = xp * math.cos(dphi) - zp * math.sin(dphi)
    y = yp
    z = xp * math.sin(dphi) + zp * math.cos(dphi)
    horiz = math.hypot(x, y)
    f_nt = math.hypot(horiz, z)
    incl = math.degrees(math.atan2(z, horiz))
    decl = math.degrees(math.atan2(y, x))
    if not (math.isfinite(decl) and math.isfinite(incl) and math.isfinite(f_nt)):
        raise HarnessError(
            f"independent WMM non-finite at lat={lat_deg} lon={lon_deg} year={year}"
        )
    if f_nt <= 0.0:
        raise HarnessError(
            f"independent WMM total field is not positive at {lat_deg},{lon_deg}"
        )
    return decl, incl, f_nt / 1000.0


def ned_heading_deg(bn: float, be: float) -> float:
    """Horizontal heading of a NED field, degrees east of north.

    Raises if the horizontal component cannot be distinguished from zero
    (that would make 0° look like magnetic north).
    """
    horiz = math.hypot(bn, be)
    if not math.isfinite(horiz):
        raise HarnessError(f"NED horizontal field is non-finite: {bn},{be}")
    if horiz < H_MIN_UT:
        raise HarnessError(
            f"NED horizontal field {horiz} uT is too small to recover heading"
        )
    return math.degrees(math.atan2(be, bn))


def ned_magnitude(bn: float, be: float, bd: float) -> float:
    mag = math.sqrt(bn * bn + be * be + bd * bd)
    if not math.isfinite(mag):
        raise HarnessError(f"NED magnitude is non-finite: {bn},{be},{bd}")
    if mag <= 0.0:
        raise HarnessError(f"NED magnitude is not positive: {bn},{be},{bd}")
    return mag


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest signed difference a−b wrapped to (−180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


def hypot3(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def is_public_wmm_row(lat_deg: float, lon_deg: float) -> bool:
    for plat, plon in _PUBLIC_WMM_ROWS:
        if abs(lat_deg - plat) < 1e-3 and abs(lon_deg - plon) < 1e-3:
            return True
    return False


def _c(op: str, *args: float) -> list[float]:
    argv = [op, *[repr(float(a)) for a in args]]
    result = invoke(_C_PROBE, argv)
    return parse_floats(result, _C_ARITY[op])


def _py(op: str, *args: float) -> list[float]:
    argv = [op, *[repr(float(a)) for a in args]]
    ident = product_identity()
    assert ident is not None, "python package directory was not found after make pylib"
    package = ident.package_name
    assert package.isidentifier(), f"discovered package name is not importable: {package!r}"
    result = run_python(_PY_PROBE.replace("__PKG__", package), argv)
    return parse_floats(result, _PY_ARITY[op])


_C_ARITY = {
    "rpy_to_quat": 4,
    "rpy_roundtrip": 3,
    "quat_normalize": 4,
    "body_to_ned": 3,
    "llh_to_ecef": 3,
    "ecef_to_llh": 3,
    "llh_roundtrip": 3,
    "ecef_roundtrip": 3,
    "dned_to_dllh": 3,
    "omega_transport": 9,
    "wmm_all": 6,
    "wmm_mag_span": 2,
}
_PY_ARITY = {
    "rpy_to_quat": 4,
    "llh_to_ecef": 3,
    "ecef_to_llh": 3,
    "llh_roundtrip": 3,
    "ecef_roundtrip": 3,
    "wmm_ned": 3,
}


def c_rpy_to_quat(roll: float, pitch: float, yaw: float) -> tuple[float, ...]:
    return tuple(_c("rpy_to_quat", roll, pitch, yaw))


def py_rpy_to_quat(roll: float, pitch: float, yaw: float) -> tuple[float, ...]:
    return tuple(_py("rpy_to_quat", roll, pitch, yaw))


def c_rpy_roundtrip(roll: float, pitch: float, yaw: float) -> tuple[float, ...]:
    return tuple(_c("rpy_roundtrip", roll, pitch, yaw))


def c_quat_normalize(q: Sequence[float]) -> tuple[float, ...]:
    if len(q) != 4:
        raise ValueError("quaternion must have 4 components")
    return tuple(_c("quat_normalize", *q))


def c_body_to_ned(
    roll: float, pitch: float, yaw: float, body: Sequence[float]
) -> tuple[float, ...]:
    if len(body) != 3:
        raise ValueError("body vector must have 3 components")
    return tuple(_c("body_to_ned", roll, pitch, yaw, *body))


def c_llh_to_ecef(lat_deg: float, lon_deg: float, height_m: float) -> tuple[float, ...]:
    return tuple(_c("llh_to_ecef", lat_deg, lon_deg, height_m))


def py_llh_to_ecef(lat_deg: float, lon_deg: float, height_m: float) -> tuple[float, ...]:
    return tuple(_py("llh_to_ecef", lat_deg, lon_deg, height_m))


def c_llh_roundtrip(lat_deg: float, lon_deg: float, height_m: float) -> tuple[float, ...]:
    return tuple(_c("llh_roundtrip", lat_deg, lon_deg, height_m))


def py_llh_roundtrip(lat_deg: float, lon_deg: float, height_m: float) -> tuple[float, ...]:
    return tuple(_py("llh_roundtrip", lat_deg, lon_deg, height_m))


def c_ecef_roundtrip(xyz: Sequence[float]) -> tuple[float, ...]:
    if len(xyz) != 3:
        raise ValueError("ECEF must have 3 components")
    return tuple(_c("ecef_roundtrip", *xyz))


def py_ecef_roundtrip(xyz: Sequence[float]) -> tuple[float, ...]:
    if len(xyz) != 3:
        raise ValueError("ECEF must have 3 components")
    return tuple(_py("ecef_roundtrip", *xyz))


def c_dned_to_dllh(
    lat_deg: float, lon_deg: float, height_m: float, dned: Sequence[float]
) -> tuple[float, ...]:
    if len(dned) != 3:
        raise ValueError("NED displacement must have 3 components")
    return tuple(_c("dned_to_dllh", lat_deg, lon_deg, height_m, *dned))


def c_omega_transport(
    lat_deg: float, height_m: float, vel_ned: Sequence[float]
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    if len(vel_ned) != 3:
        raise ValueError("velocity must have 3 components")
    vals = _c("omega_transport", lat_deg, height_m, *vel_ned)
    return tuple(vals[0:3]), tuple(vals[3:6]), tuple(vals[6:9])


def c_wmm_all(lat_deg: float, lon_deg: float, year: float) -> tuple[float, ...]:
    """D, I, F, Bn, Be, Bd."""
    return tuple(_c("wmm_all", lat_deg, lon_deg, year))


def c_wmm_mag_span(lat_deg: float, lon_deg: float) -> tuple[float, float]:
    """Min and max C |B_ned| (µT) over the WMM2025 epoch years 2025.0-2030.0."""
    lo, hi = _c("wmm_mag_span", lat_deg, lon_deg)
    return lo, hi


def py_wmm_ned(lat_deg: float, lon_deg: float, year: float) -> tuple[float, ...]:
    return tuple(_py("wmm_ned", lat_deg, lon_deg, year))
