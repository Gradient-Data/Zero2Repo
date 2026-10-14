# feature: F01
"""Frames, WGS84 geodesy, and World Magnetic Model lookup (FP-01).

Assertions stay at the PRD's precision: FRD/NED mapping, Hamilton ZYX
components, WGS84 flattening versus a sphere, finite polar azimuth rate
under non-zero east velocity, WMM D/I/F/NED self-consistency and 0.15°/
0.6° agreement with an independent spherical-harmonic evaluation, longitude
wrap, latitude clamp, and year extrapolation. Message text, LUT knots, and
the polar cosine floor value are not pinned.
"""

from __future__ import annotations

import math

from _harness import runtime_uuid_int
from F01_helpers import (
    D_MID_DEG,
    D_POLE_DEG,
    F_UNIT_UT,
    FLAT_SPHERE_M,
    FLAT_WGS84_M,
    HEADING_SELF_DEG,
    HEIGHT_M_TOL,
    I_UNIT_DEG,
    LLH_RAD_TOL,
    MAG_REL,
    NAMED_PITCH,
    NAMED_ROLL,
    NAMED_YAW,
    SINGLE_ABS,
    STUTTGART_H_M,
    STUTTGART_LAT_DEG,
    STUTTGART_LON_DEG,
    WRAP_D_DEG,
    YEAR_D_DEG,
    angle_diff_deg,
    c_body_to_ned,
    c_dned_to_dllh,
    c_ecef_roundtrip,
    c_llh_roundtrip,
    c_llh_to_ecef,
    c_omega_transport,
    c_quat_normalize,
    c_rpy_roundtrip,
    c_rpy_to_quat,
    c_wmm_all,
    c_wmm_mag_span,
    hamilton_zyx_quaternion,
    hypot3,
    independent_wmm,
    is_public_wmm_row,
    ned_heading_deg,
    ned_magnitude,
    py_ecef_roundtrip,
    py_llh_roundtrip,
    py_llh_to_ecef,
    py_rpy_to_quat,
    py_wmm_ned,
    spherical_ecef_from_geodetic,
    wgs84_ecef_from_geodetic,
)

_YEAR = 2026.5
_WEST_LAT = 42.35
_WEST_LON = -71.06
_POLE_N = (89.9, 25.0)
_POLE_S = (-89.9, -40.0)


def _assert_close(got, exp, tol, what):
    delta = abs(got - exp)
    print(f"{what}: got={got!r} exp={exp!r} |d|={delta} tol={tol}", flush=True)
    assert delta <= tol, f"{what}: |{got} - {exp}| = {delta} > {tol}"


def _assert_quat(got, exp, what):
    assert len(got) == 4 and len(exp) == 4
    for i, name in enumerate("wxyz"):
        _assert_close(got[i], exp[i], SINGLE_ABS, f"{what}.{name}")


def _assert_angle_deg(got, exp, tol, what):
    delta = abs(angle_diff_deg(got, exp))
    print(f"{what}: got={got!r} exp={exp!r} wrap_d={delta} tol={tol}", flush=True)
    assert delta <= tol, f"{what}: wrap |{got}-{exp}| = {delta} > {tol}"


def _runtime_rpy():
    u = runtime_uuid_int()
    roll = ((u % 900) / 1000.0) - 0.45
    pitch = (((u // 900) % 700) / 1000.0) - 0.35
    yaw = (((u // 630000) % 1200) / 1000.0) + 0.15
    if (
        abs(roll - NAMED_ROLL) < 0.05
        and abs(pitch - NAMED_PITCH) < 0.05
        and abs(yaw - NAMED_YAW) < 0.05
    ):
        yaw += 0.4
    print(f"runtime rpy=({roll}, {pitch}, {yaw})", flush=True)
    return roll, pitch, yaw


def _runtime_site():
    u = runtime_uuid_int()
    lat = 32.0 + (u % 1600) / 100.0
    lon = 2.0 + ((u // 1600) % 1200) / 100.0
    h = 50.0 + ((u // 1920000) % 400)
    if abs(lat - STUTTGART_LAT_DEG) < 0.2 and abs(lon - STUTTGART_LON_DEG) < 0.2:
        lat += 1.3
    print(f"runtime site lat={lat} lon={lon} h={h}", flush=True)
    return lat, lon, h


def _runtime_wmm_midlat():
    u = runtime_uuid_int()
    lat = STUTTGART_LAT_DEG + ((u % 400) - 200) / 250.0
    lon = STUTTGART_LON_DEG + (((u // 400) % 400) - 200) / 200.0
    if is_public_wmm_row(lat, lon):
        lon += 0.8
    print(f"runtime WMM midlat lat={lat} lon={lon}", flush=True)
    return lat, lon


def _quat_close_to_identity(q, what):
    _assert_close(q[0], 1.0, SINGLE_ABS, f"{what}.w")
    _assert_close(q[1], 0.0, SINGLE_ABS, f"{what}.x")
    _assert_close(q[2], 0.0, SINGLE_ABS, f"{what}.y")
    _assert_close(q[3], 0.0, SINGLE_ABS, f"{what}.z")


def _assert_total_field_matches_epoch_ned(f, lat, lon, what):
    # The two-argument total field uses a year of the implementer's choice
    # within the model epoch, so it must equal |B_ned| at some epoch year to
    # MAG_REL: it lies inside the span of |B_ned| over 2025.0-2030.0.
    lo, hi = c_wmm_mag_span(lat, lon)
    print(f"{what} F={f} epoch |B| span=[{lo}, {hi}]", flush=True)
    assert lo * (1.0 - MAG_REL) <= f <= hi * (1.0 + MAG_REL), (
        f"{what}: F={f} matches no epoch-year |B| in [{lo}, {hi}] to relative {MAG_REL}"
    )


def _wmm_self_consistent(d, i, f, bn, be, bd, lat, lon, what):
    heading = ned_heading_deg(bn, be)
    _assert_angle_deg(heading, d, HEADING_SELF_DEG, f"{what} heading vs D")
    _assert_total_field_matches_epoch_ned(f, lat, lon, what)
    _ = i  # inclination is a returned quantity; sign is asserted elsewhere


# ---------------------------------------------------------------------------
# A. FRD / NED
# ---------------------------------------------------------------------------


def test_level_identity_maps_body_x_north_z_down():
    north = c_body_to_ned(0.0, 0.0, 0.0, (1.0, 0.0, 0.0))
    down = c_body_to_ned(0.0, 0.0, 0.0, (0.0, 0.0, 1.0))
    east = c_body_to_ned(0.0, 0.0, 0.0, (0.0, 1.0, 0.0))
    print(f"identity body x→{north} z→{down} y→{east}", flush=True)
    _assert_close(north[0], 1.0, SINGLE_ABS, "body+x north")
    _assert_close(north[1], 0.0, SINGLE_ABS, "body+x not east")
    _assert_close(north[2], 0.0, SINGLE_ABS, "body+x not down")
    _assert_close(down[0], 0.0, SINGLE_ABS, "body+z not north")
    _assert_close(down[1], 0.0, SINGLE_ABS, "body+z not east")
    _assert_close(down[2], 1.0, SINGLE_ABS, "body+z down")
    _assert_close(east[0], 0.0, SINGLE_ABS, "body+y not north")
    _assert_close(east[1], 1.0, SINGLE_ABS, "body+y east")
    assert north[0] > east[0], "north and east are distinguishable"


def test_local_1_5_m_is_north_not_east_or_up():
    lat, lon, h = STUTTGART_LAT_DEG, STUTTGART_LON_DEG, STUTTGART_H_M
    north = c_dned_to_dllh(lat, lon, h, (1.5, 0.0, 0.0))
    east = c_dned_to_dllh(lat, lon, h, (0.0, 1.5, 0.0))
    up = c_dned_to_dllh(lat, lon, h, (0.0, 0.0, -1.5))
    print(f"dned 1.5N {north} 1.5E {east} 1.5U {up}", flush=True)
    assert north[0] > 0.0, "north displacement must increase latitude"
    assert abs(north[0]) > abs(east[0]), "1.5 m north is not an east shift"
    assert abs(east[1]) > abs(north[1]), "1.5 m east must change longitude"
    assert east[1] > 0.0, "east displacement must increase longitude (north of equator)"
    _assert_close(up[2], 1.5, 1e-6, "negative-down displacement is up")
    _assert_close(north[2], 0.0, 1e-6, "north-only is not a height change")
    _assert_close(east[2], 0.0, 1e-6, "east-only is not a height change")


def test_yaw_pi_over_2_maps_body_x_to_east():
    yaw = math.pi / 2.0
    mapped = c_body_to_ned(0.0, 0.0, yaw, (1.0, 0.0, 0.0))
    print(f"yaw pi/2 body+x → {mapped}", flush=True)
    _assert_close(mapped[0], 0.0, SINGLE_ABS, "yaw90 not north")
    _assert_close(mapped[1], 1.0, SINGLE_ABS, "yaw90 body+x east")
    _assert_close(mapped[2], 0.0, SINGLE_ABS, "yaw90 not down")


# ---------------------------------------------------------------------------
# B. Hamilton scalar-first, Tait-Bryan ZYX
# ---------------------------------------------------------------------------


def test_zero_rpy_is_identity_scalar_first_c_and_python():
    qc = c_rpy_to_quat(0.0, 0.0, 0.0)
    qp = py_rpy_to_quat(0.0, 0.0, 0.0)
    print(f"zero rpy C={qc} Python={qp}", flush=True)
    _quat_close_to_identity(qc, "C zero")
    _quat_close_to_identity(qp, "Python zero")


def test_yaw_pi_over_2_hamilton_components_c_and_python():
    yaw = math.pi / 2.0
    half = math.cos(math.pi / 4.0)
    exp = (half, 0.0, 0.0, half)
    qc = c_rpy_to_quat(0.0, 0.0, yaw)
    qp = py_rpy_to_quat(0.0, 0.0, yaw)
    print(f"yaw pi/2 C={qc} Python={qp} exp={exp}", flush=True)
    _assert_quat(qc, exp, "C yaw pi/2")
    _assert_quat(qp, exp, "Python yaw pi/2")


def test_named_rpy_forward_zyx_quaternion_c_and_python():
    exp = hamilton_zyx_quaternion(NAMED_ROLL, NAMED_PITCH, NAMED_YAW)
    qc = c_rpy_to_quat(NAMED_ROLL, NAMED_PITCH, NAMED_YAW)
    qp = py_rpy_to_quat(NAMED_ROLL, NAMED_PITCH, NAMED_YAW)
    print(f"named forward C={qc} Python={qp} ZYX={exp}", flush=True)
    _assert_quat(qc, exp, "C named ZYX")
    _assert_quat(qp, exp, "Python named ZYX")


def test_named_rpy_round_trip():
    got = c_rpy_roundtrip(NAMED_ROLL, NAMED_PITCH, NAMED_YAW)
    print(f"named round-trip {got}", flush=True)
    _assert_close(got[0], NAMED_ROLL, SINGLE_ABS, "named roll")
    _assert_close(got[1], NAMED_PITCH, SINGLE_ABS, "named pitch")
    _assert_close(got[2], NAMED_YAW, SINGLE_ABS, "named yaw")


def test_runtime_rpy_forward_and_round_trip():
    roll, pitch, yaw = _runtime_rpy()
    exp = hamilton_zyx_quaternion(roll, pitch, yaw)
    qc = c_rpy_to_quat(roll, pitch, yaw)
    qp = py_rpy_to_quat(roll, pitch, yaw)
    back = c_rpy_roundtrip(roll, pitch, yaw)
    print(f"runtime forward C={qc} Python={qp} back={back}", flush=True)
    _assert_quat(qc, exp, "C runtime ZYX")
    _assert_quat(qp, exp, "Python runtime ZYX")
    _assert_close(back[0], roll, SINGLE_ABS, "runtime roll")
    _assert_close(back[1], pitch, SINGLE_ABS, "runtime pitch")
    _assert_close(back[2], yaw, SINGLE_ABS, "runtime yaw")


# ---------------------------------------------------------------------------
# C. Degenerate normalize and gimbal-lock finite
# ---------------------------------------------------------------------------


def test_zero_quaternion_normalizes_to_identity():
    got = c_quat_normalize((0.0, 0.0, 0.0, 0.0))
    print(f"normalize zero → {got}", flush=True)
    _quat_close_to_identity(got, "zero quat")


def test_degenerate_tiny_quaternion_normalizes_to_identity():
    tiny = (0.0, 1.0e-25, 0.0, 0.0)
    got = c_quat_normalize(tiny)
    print(f"normalize tiny {tiny} → {got}", flush=True)
    _quat_close_to_identity(got, "tiny quat")


def test_gimbal_lock_pitch_yields_finite_rpy():
    baseline = c_rpy_roundtrip(NAMED_ROLL, NAMED_PITCH, NAMED_YAW)
    print(f"gimbal live baseline round-trip {baseline}", flush=True)
    _assert_close(baseline[1], NAMED_PITCH, SINGLE_ABS, "baseline pitch")
    for pitch in (0.999 * math.pi / 2.0, -0.999 * math.pi / 2.0, math.pi / 2.0, -math.pi / 2.0):
        got = c_rpy_roundtrip(0.1, pitch, 0.4)
        print(f"gimbal pitch={pitch} → rpy={got}", flush=True)
        assert all(math.isfinite(v) for v in got), f"gimbal produced non-finite {got}"


# ---------------------------------------------------------------------------
# D. WGS84 ECEF round-trip and flattening
# ---------------------------------------------------------------------------


def test_stuttgart_geodetic_ecef_round_trip_c_and_python():
    lat0 = math.radians(STUTTGART_LAT_DEG)
    lon0 = math.radians(STUTTGART_LON_DEG)
    c_llh = c_llh_roundtrip(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, STUTTGART_H_M)
    p_llh = py_llh_roundtrip(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, STUTTGART_H_M)
    print(f"Stuttgart C llh={c_llh} Python llh={p_llh}", flush=True)
    for label, llh in (("C", c_llh), ("Python", p_llh)):
        _assert_close(llh[0], lat0, LLH_RAD_TOL, f"{label} Stuttgart lat")
        _assert_close(llh[1], lon0, LLH_RAD_TOL, f"{label} Stuttgart lon")
        _assert_close(llh[2], STUTTGART_H_M, HEIGHT_M_TOL, f"{label} Stuttgart h")


def test_ecef_geodetic_ecef_consistent():
    xyz0 = c_llh_to_ecef(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, STUTTGART_H_M)
    c_xyz = c_ecef_roundtrip(xyz0)
    p_xyz = py_ecef_roundtrip(xyz0)
    print(f"ECEF start={xyz0} C={c_xyz} Python={p_xyz}", flush=True)
    for label, xyz in (("C", c_xyz), ("Python", p_xyz)):
        err = hypot3(xyz, xyz0)
        print(f"{label} ECEF round-trip 3d={err} m", flush=True)
        assert err <= HEIGHT_M_TOL, f"{label} ECEF round-trip {err} m > 0.1 mm"


def test_runtime_site_geodetic_round_trip():
    lat, lon, h = _runtime_site()
    lat0 = math.radians(lat)
    lon0 = math.radians(lon)
    c_llh = c_llh_roundtrip(lat, lon, h)
    p_llh = py_llh_roundtrip(lat, lon, h)
    print(f"runtime C llh={c_llh} Python llh={p_llh}", flush=True)
    for label, llh in (("C", c_llh), ("Python", p_llh)):
        _assert_close(llh[0], lat0, LLH_RAD_TOL, f"{label} runtime lat")
        _assert_close(llh[1], lon0, LLH_RAD_TOL, f"{label} runtime lon")
        _assert_close(llh[2], h, HEIGHT_M_TOL, f"{label} runtime h")


def _assert_flattening(lat_deg, lon_deg, height_m, xyz, what):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    wgs = wgs84_ecef_from_geodetic(lat, lon, height_m)
    sph = spherical_ecef_from_geodetic(lat, lon, height_m)
    err_w = hypot3(xyz, wgs)
    err_s = hypot3(xyz, sph)
    print(f"{what} ECEF={xyz} WGS84={wgs} sphere={sph}", flush=True)
    print(f"{what} err_wgs84={err_w} m err_sphere={err_s} m", flush=True)
    assert err_w <= FLAT_WGS84_M, f"{what}: {err_w} m from WGS84 (metre-level miss)"
    assert err_s > FLAT_SPHERE_M, f"{what}: sphere error {err_s} m is not a live flattening contrast"
    assert err_w < err_s / 10.0, f"{what}: not closer to WGS84 than to a sphere"


def test_wgs84_forward_rejects_spherical_earth():
    lat_r, lon_r, h_r = _runtime_site()
    sites = (
        ("C Stuttgart", c_llh_to_ecef(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, STUTTGART_H_M),
         STUTTGART_LAT_DEG, STUTTGART_LON_DEG, STUTTGART_H_M),
        ("Python Stuttgart", py_llh_to_ecef(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, STUTTGART_H_M),
         STUTTGART_LAT_DEG, STUTTGART_LON_DEG, STUTTGART_H_M),
        ("C runtime", c_llh_to_ecef(lat_r, lon_r, h_r), lat_r, lon_r, h_r),
        ("Python runtime", py_llh_to_ecef(lat_r, lon_r, h_r), lat_r, lon_r, h_r),
    )
    for what, xyz, lat, lon, h in sites:
        _assert_flattening(lat, lon, h, xyz, what)


# ---------------------------------------------------------------------------
# E. Polar azimuth transport rate
# ---------------------------------------------------------------------------


def test_midlat_azimuth_rate_moves_with_east_velocity():
    lat, h = STUTTGART_LAT_DEG, 0.0
    _, _, wen_a = c_omega_transport(lat, h, (0.0, 40.0, 0.0))
    _, _, wen_b = c_omega_transport(lat, h, (0.0, 90.0, 0.0))
    print(f"midlat wen east40={wen_a} east90={wen_b}", flush=True)
    assert wen_a[2] != wen_b[2], "azimuth transport rate ignores east velocity"
    assert abs(wen_a[2] - wen_b[2]) > 1e-10, "east-velocity contrast is not visible"


def test_polar_azimuth_transport_rate_finite_with_east_velocity():
    vel = (0.0, 80.0, 0.0)
    _, _, wen_mid = c_omega_transport(STUTTGART_LAT_DEG, 0.0, vel)
    print(f"polar live baseline midlat wen={wen_mid}", flush=True)
    assert math.isfinite(wen_mid[2]), "baseline azimuth rate is not finite"
    for lat in (90.0, -90.0):
        win, wie, wen = c_omega_transport(lat, 0.0, vel)
        print(f"pole lat={lat} win={win} wie={wie} wen={wen}", flush=True)
        for name, vec in (("win", win), ("wie", wie), ("wen", wen)):
            assert all(math.isfinite(v) for v in vec), f"{name} at lat={lat} not finite: {vec}"
        assert math.isfinite(wen[2]), f"azimuth transport at lat={lat} is not finite"


# ---------------------------------------------------------------------------
# F. WMM four quantities, units, Python recovery
# ---------------------------------------------------------------------------


def test_wmm_four_quantities_ned_self_consistent():
    d, i, f, bn, be, bd = c_wmm_all(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR)
    print(f"WMM Stuttgart D={d} I={i} F={f} B=({bn},{be},{bd})", flush=True)
    _wmm_self_consistent(
        d, i, f, bn, be, bd, STUTTGART_LAT_DEG, STUTTGART_LON_DEG, "Stuttgart"
    )


def test_inclination_positive_down_northern_hemisphere():
    north = c_wmm_all(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR)
    print(f"I north={north[1]}", flush=True)
    assert north[1] > 0.0, "northern-hemisphere inclination must be positive (down)"


def test_inclination_and_total_field_match_independent_wmm():
    lat, lon, year = STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR
    d, i, f, bn, be, bd = c_wmm_all(lat, lon, year)
    di, ii, fi = independent_wmm(lat, lon, year)
    mag = ned_magnitude(bn, be, bd)
    print(f"I C={i} SH={ii} F C={f} |B|={mag} SH={fi}", flush=True)
    _assert_close(i, ii, I_UNIT_DEG, "I vs independent (deg, not rad)")
    _assert_close(f, fi, F_UNIT_UT, "F vs independent (uT, not nT)")
    _assert_close(mag, fi, F_UNIT_UT, "|B| vs independent (uT, not nT)")
    _ = d


def test_python_ned_heading_and_magnitude_match_c():
    d, i, f, bn, be, bd = c_wmm_all(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR)
    pb = py_wmm_ned(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR)
    heading = ned_heading_deg(pb[0], pb[1])
    mag = ned_magnitude(*pb)
    print(f"Python B={pb} heading={heading} |B|={mag} C D={d} F={f}", flush=True)
    _assert_angle_deg(heading, d, HEADING_SELF_DEG, "Python heading vs C D")
    c_mag = ned_magnitude(bn, be, bd)
    rel = abs(mag - c_mag) / max(abs(c_mag), 1e-6)
    assert rel <= MAG_REL, f"Python |B| vs C |B| (same year) relative {rel} > {MAG_REL}"
    _assert_total_field_matches_epoch_ned(f, STUTTGART_LAT_DEG, STUTTGART_LON_DEG, "Python")
    _ = i


# ---------------------------------------------------------------------------
# G. Mid-latitude 0.15° / polar 0.6° vs independent spherical harmonics
# ---------------------------------------------------------------------------


def test_midlatitude_declination_within_0_15_deg():
    d, i, f, *_ = c_wmm_all(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR)
    di, ii, fi = independent_wmm(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR)
    print(f"Stuttgart D C={d} SH={di}", flush=True)
    _assert_angle_deg(d, di, D_MID_DEG, "Stuttgart D vs independent")
    _ = (i, f, ii, fi)


def test_second_midlatitude_site_not_constant_heading():
    d_e, *_ = c_wmm_all(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR)
    d_w, *_ = c_wmm_all(_WEST_LAT, _WEST_LON, _YEAR)
    di_e, *_ = independent_wmm(STUTTGART_LAT_DEG, STUTTGART_LON_DEG, _YEAR)
    di_w, *_ = independent_wmm(_WEST_LAT, _WEST_LON, _YEAR)
    print(f"east D C={d_e} SH={di_e} west D C={d_w} SH={di_w}", flush=True)
    _assert_angle_deg(d_e, di_e, D_MID_DEG, "east-site D")
    _assert_angle_deg(d_w, di_w, D_MID_DEG, "west-site D")
    assert d_e * d_w < 0.0 or abs(d_e - d_w) > 5.0, (
        "second mid-latitude site is not distinguishable from a constant heading"
    )


def test_runtime_midlatitude_declination_within_0_15_deg():
    lat, lon = _runtime_wmm_midlat()
    assert not is_public_wmm_row(lat, lon), "runtime site collided with a public table row"
    d, *_ = c_wmm_all(lat, lon, _YEAR)
    di, *_ = independent_wmm(lat, lon, _YEAR)
    print(f"runtime D C={d} SH={di}", flush=True)
    _assert_angle_deg(d, di, D_MID_DEG, "runtime midlat D")


def test_polar_declination_within_0_6_deg():
    for lat, lon in (_POLE_N, _POLE_S):
        assert abs(lat) > 88.0
        assert not is_public_wmm_row(lat, lon)
        d, *_ = c_wmm_all(lat, lon, _YEAR)
        di, *_ = independent_wmm(lat, lon, _YEAR)
        print(f"polar ({lat},{lon}) D C={d} SH={di}", flush=True)
        _assert_angle_deg(d, di, D_POLE_DEG, f"polar D at {lat},{lon}")


# ---------------------------------------------------------------------------
# H. Longitude wrap 190/−170 and ±180 finite
# ---------------------------------------------------------------------------


def test_longitude_190_agrees_with_minus_170():
    lat, year = STUTTGART_LAT_DEG, _YEAR
    a = c_wmm_all(lat, 190.0, year)
    b = c_wmm_all(lat, -170.0, year)
    other = c_wmm_all(lat, STUTTGART_LON_DEG, year)
    print(f"190={a} -170={b} other_lon={STUTTGART_LON_DEG} {other}", flush=True)
    _assert_angle_deg(a[0], b[0], WRAP_D_DEG, "PRD D 190 vs -170")
    for idx, name in ((1, "I"), (2, "F"), (3, "Bn"), (4, "Be"), (5, "Bd")):
        _assert_close(a[idx], b[idx], 1e-3 if idx >= 3 else 1e-3, f"PRD {name} 190 vs -170")
    d_other_190 = abs(angle_diff_deg(a[0], other[0]))
    d_other_170 = abs(angle_diff_deg(b[0], other[0]))
    print(
        f"wrap contrast D other={other[0]} vs 190 d={d_other_190} vs -170 d={d_other_170}",
        flush=True,
    )
    assert d_other_190 > D_MID_DEG, (
        "190° matches a meridian that is not wrap-equivalent; wrap is not shown"
    )
    assert d_other_170 > D_MID_DEG, (
        "-170° matches a meridian that is not wrap-equivalent; wrap is not shown"
    )
    pa = py_wmm_ned(lat, 190.0, year)
    pb = py_wmm_ned(lat, -170.0, year)
    _assert_angle_deg(ned_heading_deg(pa[0], pa[1]), a[0], HEADING_SELF_DEG, "Python 190 vs C D")
    _assert_angle_deg(ned_heading_deg(pb[0], pb[1]), b[0], HEADING_SELF_DEG, "Python -170 vs C D")
    # Same-year comparison: Python |B| vs C |B| (the C F is year-free).
    c_mag_a = ned_magnitude(*a[3:6])
    c_mag_b = ned_magnitude(*b[3:6])
    rel_a = abs(ned_magnitude(*pa) - c_mag_a) / max(abs(c_mag_a), 1e-6)
    rel_b = abs(ned_magnitude(*pb) - c_mag_b) / max(abs(c_mag_b), 1e-6)
    assert rel_a <= MAG_REL and rel_b <= MAG_REL


def test_runtime_longitude_wrap_agrees():
    k = 1 + (runtime_uuid_int() % 3)
    lon_wrapped = 190.0 + 360.0 * k
    lat, year = STUTTGART_LAT_DEG, _YEAR
    a = c_wmm_all(lat, lon_wrapped, year)
    b = c_wmm_all(lat, -170.0, year)
    other = c_wmm_all(lat, STUTTGART_LON_DEG, year)
    print(
        f"runtime wrap k={k} lon={lon_wrapped} {a} vs -170 {b} "
        f"other_lon={STUTTGART_LON_DEG} {other}",
        flush=True,
    )
    _assert_angle_deg(a[0], b[0], WRAP_D_DEG, "D 190+360k vs -170")
    _assert_close(a[1], b[1], 1e-3, "I wrap")
    _assert_close(a[2], b[2], 1e-3, "F wrap")
    d_other_wrap = abs(angle_diff_deg(a[0], other[0]))
    d_other_170 = abs(angle_diff_deg(b[0], other[0]))
    print(
        f"runtime wrap contrast D other={other[0]} vs 190+360k d={d_other_wrap} "
        f"vs -170 d={d_other_170}",
        flush=True,
    )
    assert d_other_wrap > D_MID_DEG, (
        "190°+360k matches a meridian that is not wrap-equivalent; wrap is not shown"
    )
    assert d_other_170 > D_MID_DEG, (
        "-170° matches a meridian that is not wrap-equivalent; wrap is not shown"
    )


def test_longitude_pm_180_finite():
    lat, year = 10.0, 2028.0
    plus = c_wmm_all(lat, 180.0, year)
    minus = c_wmm_all(lat, -180.0, year)
    print(f"+180={plus} -180={minus}", flush=True)
    assert all(math.isfinite(v) for v in plus), f"+180 not finite: {plus}"
    assert all(math.isfinite(v) for v in minus), f"-180 not finite: {minus}"
    _assert_angle_deg(plus[0], minus[0], WRAP_D_DEG, "±180 same meridian D")
    _assert_close(plus[1], minus[1], 1e-3, "±180 I")
    _assert_close(plus[2], minus[2], 1e-3, "±180 F")


# ---------------------------------------------------------------------------
# I. Latitude clamp, year extrapolation, year as input
# ---------------------------------------------------------------------------


def test_latitude_clamped_to_pm_90():
    year = _YEAR
    lon = STUTTGART_LON_DEG
    hi = c_wmm_all(95.0, lon, year)
    hi90 = c_wmm_all(90.0, lon, year)
    lo = c_wmm_all(-95.0, lon, year)
    lo90 = c_wmm_all(-90.0, lon, year)
    extra = 90.0 + 7.0 + (runtime_uuid_int() % 13)
    run = c_wmm_all(extra, lon, year)
    mid = c_wmm_all(STUTTGART_LAT_DEG, lon, year)
    print(
        f"clamp 95={hi} 90={hi90} -95={lo} -90={lo90} runtime {extra}={run} "
        f"midlat {STUTTGART_LAT_DEG}={mid}",
        flush=True,
    )
    for vec in (hi, hi90, lo, lo90, run, mid):
        assert all(math.isfinite(v) for v in vec), f"clamp produced non-finite {vec}"
    _assert_angle_deg(hi[0], hi90[0], WRAP_D_DEG, "95 vs 90 D")
    _assert_close(hi[1], hi90[1], 1e-3, "95 vs 90 I")
    _assert_close(hi[2], hi90[2], 1e-3, "95 vs 90 F")
    _assert_angle_deg(lo[0], lo90[0], WRAP_D_DEG, "-95 vs -90 D")
    _assert_close(lo[1], lo90[1], 1e-3, "-95 vs -90 I")
    _assert_close(lo[2], lo90[2], 1e-3, "-95 vs -90 F")
    _assert_angle_deg(run[0], hi90[0], WRAP_D_DEG, "runtime |lat|>90 vs 90 D")
    d_pole_mid = abs(angle_diff_deg(hi90[0], mid[0]))
    d_95_mid = abs(angle_diff_deg(hi[0], mid[0]))
    print(
        f"clamp contrast midlat D={mid[0]} vs 90 d={d_pole_mid} vs 95 d={d_95_mid}",
        flush=True,
    )
    assert d_pole_mid > D_MID_DEG, (
        "in-range latitude is not distinct from +90°; clamp contrast is dead"
    )
    assert d_95_mid > D_MID_DEG, (
        "95° matches an in-range latitude that is not the clamp target"
    )


def test_out_of_range_year_extrapolated_not_refused():
    lat, lon = STUTTGART_LAT_DEG, STUTTGART_LON_DEG
    baseline = c_wmm_all(lat, lon, _YEAR)
    print(f"year live baseline {_YEAR} → {baseline}", flush=True)
    assert all(math.isfinite(v) for v in baseline)
    early_a = c_wmm_all(lat, lon, 1990.0)
    early_b = c_wmm_all(lat, lon, 2000.0)
    late_a = c_wmm_all(lat, lon, 2045.0)
    late_b = c_wmm_all(lat, lon, 2055.0)
    far = c_wmm_all(lat, lon, 2050.0)
    print(f"1990={early_a[0]} 2000={early_b[0]} 2045={late_a[0]} 2055={late_b[0]} 2050={far}", flush=True)
    for vec, name in (
        (early_a, "1990"),
        (early_b, "2000"),
        (late_a, "2045"),
        (late_b, "2055"),
        (far, "2050"),
    ):
        assert all(math.isfinite(v) for v in vec), f"{name} refused or non-finite: {vec}"
    assert abs(angle_diff_deg(early_a[0], early_b[0])) > YEAR_D_DEG, (
        "two years far before any five-year window produced the same D"
    )
    assert abs(angle_diff_deg(late_a[0], late_b[0])) > YEAR_D_DEG, (
        "two years far after any five-year window produced the same D"
    )


def test_decimal_year_is_an_input():
    lat, lon = STUTTGART_LAT_DEG, STUTTGART_LON_DEG
    a = c_wmm_all(lat, lon, 2026.0)
    b = c_wmm_all(lat, lon, 2029.0)
    print(f"2026 D={a[0]} 2029 D={b[0]}", flush=True)
    assert all(math.isfinite(v) for v in a) and all(math.isfinite(v) for v in b)
    assert abs(angle_diff_deg(a[0], b[0])) > YEAR_D_DEG, (
        "declination is forced identical across distinct legal years"
    )
