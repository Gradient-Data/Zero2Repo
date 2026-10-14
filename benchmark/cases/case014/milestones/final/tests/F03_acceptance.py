# feature: F03
"""Aiding beyond GNSS (FP-03).

Assertions stay at the PRD's precision: a 10 Hz centimetre local NED tracker
bootstraps a ready 3D solution without GNSS and the published local position
matches that tracker; a later healthy sample is followed rather than the first
fix being pasted forever; ECEF is the Earth anchor plus that NED, not the
tracker treated as ECEF; a high-rate glitch is omitted from fusion (position
stays on the clean tracker) rather than fused at reduced weight, and the
downweight diagnostic does not rise; degenerate local covariance is not
fused. Magnetometer fusion corrects heading only and does not tilt
roll/pitch; the default 1 s rate limit is a long-term yaw anchor, not a
per-sample compass; all-zero axis variance is a weak default, not a
zero-noise lock; arming WMM moves yaw from magnetic north toward true north
by the local declination; an unusable horizontal reference does not pull
heading the way a usable field does. Absolute yaw accepts both single-turn
conventions, refuses a heading beyond one turn while incrementing the
invalid-input counter, and skips near gimbal lock. Scalar ground speed pulls
an along-track speed error and does not correct a purely sideways velocity
error; a sample is skipped when the filter's own speed is below the default
1 m/s. With barometer and GNSS both wired and the disable switch off, the
barometer is the height source (GNSS position fusion stays horizontal) and a
GNSS outage keeps that vertical; the disable switch forces GNSS height; a
local-position bootstrap keeps tracker height even with a barometer.
Explicit ZUPT holds velocity near zero with the auto-detector off, and extra
flags inside one filter-update interval do not pull harder than one flag;
explicit ZARU pulls gyro bias toward a still-body reading with the same
one-fusion-per-interval limit; the auto-detector reports
stationary on a still IMU after the dwell and not on a turntable, fuses
zero velocity without an explicit flag, ignores the filter's own velocity on
a biased IMU, gates on a recent accurate GNSS speed value, does not fire on
a handful of samples, leaves the latch on an epoch with no IMU, and a
disable does not block explicit flags. Message text, exception types, and
unpublished numeric floors are not pinned.
"""

from __future__ import annotations

import math
from dataclasses import replace

from F01_helpers import angle_diff_deg, hypot3, independent_wmm
from F02_helpers import (
    ECEF_MATCH_M,
    GNSS_STD_M,
    HAPPY_DURATION_S,
    LEVEL_RAD,
    SPECIFIC_FORCE_LEVEL,
    ecef_from_llh_deg,
    ecef_plus_ned,
    ned_offset_from_two_ecef,
)
from F03_helpers import (
    CM_STD_M,
    LOCAL_HZ,
    SPEED_MIN_MPS,
    TRACKER_NAMED_NED,
    WMM_YEAR,
    YAW_STD_RAD,
    AidingEpoch,
    aiding_site,
    angle_diff_rad,
    body_mag_for_yaw,
    c_aiding_run,
    extend_epochs,
    extend_gnss_constant_vel,
    extend_local_ramp,
    extend_wobble,
    gnss_stream,
    horiz_speed,
    isa_pressure_pa,
    local_stream,
    magnetic_north_ned,
    ned_field_from_independent_wmm,
    py_aiding_run,
    require_ready_solution,
    runtime_heading_rad,
    runtime_tracker_ned,
    runtime_wmm_site,
    still_level_acc,
)

MAG_VAR_WEAK = (0.0, 0.0, 0.0)
MAG_VAR_STRONG = (1.0e-4, 1.0e-4, 1.0e-4)  # µT², explicit near-exact magnetometer
GNSS_VEL_STD = (0.15, 0.15, 0.15)
TURN_RPS = math.radians(18.0)
DRIFT_RPS = 0.15
RATE_DRIFT_RPS = 0.22


def _langs(scen):
    return (("c", c_aiding_run(scen)), ("py", py_aiding_run(scen)))


def _deg(rad: float) -> float:
    return math.degrees(rad)


def _modest_yaw() -> float:
    """Heading error large enough to see, small enough that mag still fuses."""
    raw = runtime_heading_rad()
    yaw = 0.38 + math.fmod(abs(raw) * 7.0, 0.22)
    print(f"modest yaw rad={yaw}", flush=True)
    return yaw


def _assert_ned_matches(got, tracker, what):
    err = hypot3(got, tracker)
    print(
        f"{what}: ned={got} tracker={tracker} |err|={err} m (limit {ECEF_MATCH_M})",
        flush=True,
    )
    assert err < ECEF_MATCH_M, f"{what}: local NED error {err} m is not well under a metre"
    assert got[0] * tracker[0] > 0 or abs(tracker[0]) < 0.2, (
        f"{what}: north sign does not follow the tracker"
    )


def _assert_near_level(rpy, what):
    roll, pitch, _yaw = rpy
    print(
        f"{what}: roll={_deg(roll)} deg pitch={_deg(pitch)} deg "
        f"limit={_deg(LEVEL_RAD)} deg",
        flush=True,
    )
    assert abs(roll) < LEVEL_RAD, f"{what}: |roll| {_deg(roll)} deg not well under 0.5 deg"
    assert abs(pitch) < LEVEL_RAD, (
        f"{what}: |pitch| {_deg(pitch)} deg not well under 0.5 deg"
    )


def _snap_after(run, t_us, what):
    snap = run.at_or_after(t_us)
    require_ready_solution(snap, what)
    return snap


# ---------------------------------------------------------------------------
# A. Local NED position
# ---------------------------------------------------------------------------


def test_local_ned_10hz_bootstraps_without_gnss_c_and_python():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    epochs = local_stream(TRACKER_NAMED_NED)
    scen = aiding_site(lat, lon, h, epochs, origin_ecef=origin)
    for kind, run in _langs(scen):
        last = run.last()
        require_ready_solution(last, f"{kind} named tracker")
        _assert_ned_matches(last.ned, TRACKER_NAMED_NED, f"{kind} named tracker")
        _assert_near_level(last.rpy, f"{kind} named tracker")


def test_runtime_local_ned_is_reported():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    tracker = runtime_tracker_ned()
    epochs = local_stream(tracker)
    scen = aiding_site(lat, lon, h, epochs, origin_ecef=origin)
    for kind, run in _langs(scen):
        last = run.last()
        require_ready_solution(last, f"{kind} runtime tracker")
        _assert_ned_matches(last.ned, tracker, f"{kind} runtime tracker")


def test_local_ned_follows_second_healthy_sample_after_ready():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    first = TRACKER_NAMED_NED
    second = (first[0] + 0.70, first[1] + 0.40, first[2] + 0.15)
    epochs = local_stream(first, duration_s=HAPPY_DURATION_S)
    epochs = extend_local_ramp(epochs, first, second, duration_s=3.0)
    # The IMU stays perfectly still while the tracker moves, so the automatic
    # standstill detector (on by default, tuning unspecified) would fight the
    # tracker. It is not under test here and is turned off publicly.
    scen = aiding_site(lat, lon, h, epochs, origin_ecef=origin, auto_zupt_disable=True)
    t_switch = epochs[int(round(HAPPY_DURATION_S * 100)) - 1].t_us
    for kind, run in _langs(scen):
        before = _snap_after(run, t_switch - 200_000, f"{kind} before second tracker")
        _assert_ned_matches(before.ned, first, f"{kind} still on first tracker")
        after = run.last()
        require_ready_solution(after, f"{kind} after second tracker")
        _assert_ned_matches(after.ned, second, f"{kind} followed second tracker")
        assert hypot3(after.ned, first) > ECEF_MATCH_M, (
            f"{kind}: published NED stayed on the bootstrap tracker"
        )


def test_local_ned_is_not_treated_as_ecef():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    tracker = TRACKER_NAMED_NED
    epochs = local_stream(tracker)
    scen = aiding_site(lat, lon, h, epochs, origin_ecef=origin)
    expected_ecef = ecef_plus_ned(origin, tracker[0], tracker[1], tracker[2])
    for kind, run in _langs(scen):
        last = run.last()
        require_ready_solution(last, f"{kind} ECEF from NED")
        as_ecef_err = hypot3(last.ecef, tracker)
        print(f"{kind}: |ecef-tracker-as-ecef|={as_ecef_err}", flush=True)
        assert as_ecef_err > 1.0e6, f"{kind}: local NED was treated as ECEF"
        got_ned = ned_offset_from_two_ecef(origin, last.ecef)
        _assert_ned_matches(got_ned, tracker, f"{kind} ECEF-implied NED")
        assert hypot3(last.ecef, expected_ecef) < ECEF_MATCH_M, (
            f"{kind}: ECEF is not the Earth anchor plus the tracker NED"
        )


def test_local_pos_glitch_skipped_not_downweighted():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    tracker = TRACKER_NAMED_NED
    glitch = (tracker[0] + 18.0, tracker[1] + 12.0, tracker[2] + 4.0)
    glitch_k = int(round((HAPPY_DURATION_S + 0.1) * 100))
    clean = local_stream(tracker, duration_s=HAPPY_DURATION_S + 1.5)
    glitch_epochs = local_stream(
        tracker,
        duration_s=HAPPY_DURATION_S + 1.5,
        tracker_at=lambda _t, k: glitch if k == glitch_k else tracker,
    )
    clean_scen = aiding_site(lat, lon, h, clean, origin_ecef=origin)
    glitch_scen = aiding_site(lat, lon, h, glitch_epochs, origin_ecef=origin)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        clean_run = runner(clean_scen)
        glitch_run = runner(glitch_scen)
        cl = clean_run.last()
        gl = glitch_run.last()
        require_ready_solution(cl, f"{kind} clean")
        require_ready_solution(gl, f"{kind} glitch")
        _assert_ned_matches(cl.ned, tracker, f"{kind} clean")
        _assert_ned_matches(gl.ned, tracker, f"{kind} glitch stayed on tracker")
        assert hypot3(gl.ned, glitch) > 5.0, f"{kind}: published NED jumped to the glitch"
        before = glitch_run.at_or_after(int(HAPPY_DURATION_S * 1e6) - 50_000)
        print(
            f"{kind}: downweight before={before.n_downweighted} after={gl.n_downweighted} "
            f"invalid {before.n_invalid}->{gl.n_invalid} "
            f"fuse_fail {before.n_fuse_fail}->{gl.n_fuse_fail} "
            f"clean_downweight={cl.n_downweighted}",
            flush=True,
        )
        assert gl.n_downweighted <= before.n_downweighted, (
            f"{kind}: glitch increased the downweight counter"
        )


def test_degenerate_local_covariance_not_fused():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    a = TRACKER_NAMED_NED
    b = (a[0] + 0.70, a[1] + 0.40, a[2] + 0.15)
    epochs = local_stream(a, duration_s=HAPPY_DURATION_S)
    t_before = epochs[-1].t_us
    epochs = extend_epochs(
        epochs,
        duration_s=0.6,
        local_ned=b,
        local_std=(0.0, 0.0, 0.0),
    )
    t_deg = epochs[-1].t_us
    epochs = extend_local_ramp(epochs, a, b, duration_s=3.0)
    # Still IMU under a moving tracker: automatic standstill is not under
    # test here (see test_local_ned_follows_second_healthy_sample_after_ready).
    scen = aiding_site(lat, lon, h, epochs, origin_ecef=origin, auto_zupt_disable=True)
    for kind, run in _langs(scen):
        before = run.at_or_after(t_before - 20_000)
        require_ready_solution(before, f"{kind} before degenerate")
        mid = run.at_or_after(t_deg - 20_000)
        require_ready_solution(mid, f"{kind} after degenerate")
        print(
            f"{kind}: after degenerate ned={mid.ned} A={a} B={b}",
            flush=True,
        )
        assert hypot3(mid.ned, b) > ECEF_MATCH_M, (
            f"{kind}: degenerate covariance was fused toward B"
        )
        last = run.last()
        require_ready_solution(last, f"{kind} recovered")
        _assert_ned_matches(last.ned, b, f"{kind} recovered on healthy B")


# ---------------------------------------------------------------------------
# B. Magnetometer
# ---------------------------------------------------------------------------


def test_magnetometer_corrects_heading_not_roll_pitch():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    mag_n = magnetic_north_ned(lat, lon, WMM_YEAR)
    yaw_cmd = _modest_yaw()
    body = body_mag_for_yaw(0.0, 0.0, yaw_cmd, mag_n)
    disturbed = (body[0], body[1] + 6.0, body[2] + 4.0)
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    none = extend_epochs(list(base), duration_s=3.0)
    mag_ep = extend_epochs(
        list(base),
        duration_s=3.0,
        mag=disturbed,
        mag_var=MAG_VAR_WEAK,
    )
    none_scen = aiding_site(
        lat, lon, h, none, origin_ecef=origin, magnetic_n=mag_n, mag_min_delay_ms=-1
    )
    mag_scen = aiding_site(
        lat, lon, h, mag_ep, origin_ecef=origin, magnetic_n=mag_n, mag_min_delay_ms=-1
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        nrun = runner(none_scen)
        mrun = runner(mag_scen)
        ns, ms = nrun.last(), mrun.last()
        require_ready_solution(ns, f"{kind} no mag")
        require_ready_solution(ms, f"{kind} mag")
        _assert_near_level(ns.rpy, f"{kind} no mag")
        _assert_near_level(ms.rpy, f"{kind} mag must not tilt")
        dyaw = abs(angle_diff_rad(ms.rpy[2], ns.rpy[2]))
        print(f"{kind}: yaw none={ns.rpy[2]} mag={ms.rpy[2]} |d|={dyaw} cmd={yaw_cmd}", flush=True)
        assert dyaw > math.radians(4.0), f"{kind}: magnetometer did not change heading"


def test_default_mag_rate_limit_not_every_100hz_sample():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    mag_n = magnetic_north_ned(lat, lon, WMM_YEAR)
    yaw_cmd = _modest_yaw()
    body = body_mag_for_yaw(0.0, 0.0, yaw_cmd, mag_n)
    gyr = (0.0, 0.0, RATE_DRIFT_RPS)
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    none = extend_epochs(list(base), duration_s=3.0, gyr=gyr)
    default = extend_epochs(
        list(base), duration_s=3.0, gyr=gyr, mag=body, mag_var=MAG_VAR_WEAK
    )
    unlimited = extend_epochs(
        list(base), duration_s=3.0, gyr=gyr, mag=body, mag_var=MAG_VAR_WEAK
    )
    t0 = base[-1].t_us
    none_scen = aiding_site(lat, lon, h, none, origin_ecef=origin, magnetic_n=mag_n)
    # Zero delay field → built-in 1 s default.
    def_scen = aiding_site(lat, lon, h, default, origin_ecef=origin, magnetic_n=mag_n)
    unl_scen = aiding_site(
        lat, lon, h, unlimited, origin_ecef=origin, magnetic_n=mag_n, mag_min_delay_ms=-1
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        nrun = runner(none_scen)
        drun = runner(def_scen)
        urun = runner(unl_scen)
        t_fused = t0 + 500_000
        t_short = t0 + 920_000
        n1 = _snap_after(nrun, t_fused, f"{kind} none@0.5")
        d1 = _snap_after(drun, t_fused, f"{kind} default@0.5")
        err_n1 = abs(angle_diff_rad(n1.rpy[2], yaw_cmd))
        err_d1 = abs(angle_diff_rad(d1.rpy[2], yaw_cmd))
        print(
            f"{kind}: after first window |yaw-cmd| none={err_n1} default={err_d1}",
            flush=True,
        )
        assert err_d1 + math.radians(2.0) < err_n1, (
            f"{kind}: default magnetometer never fused (looks like mag disabled)"
        )
        d2 = _snap_after(drun, t_short, f"{kind} default@0.92")
        u2 = _snap_after(urun, t_short, f"{kind} unlimited@0.92")
        err_d2 = abs(angle_diff_rad(d2.rpy[2], yaw_cmd))
        err_u2 = abs(angle_diff_rad(u2.rpy[2], yaw_cmd))
        print(
            f"{kind}: short window |yaw-cmd| default={err_d2} unlimited={err_u2}",
            flush=True,
        )
        assert err_u2 + math.radians(1.0) < err_d2, (
            f"{kind}: default arm looks like a per-sample compass"
        )
        # Just after 1 s (still far shorter than a multi-second gate). A 2.2 s
        # window sits a full extra 1 s of gyro drift after the second fusion, so
        # a correct 1 s limiter looks like it fused only once.
        t_late = t0 + 1_250_000
        d_late = _snap_after(drun, t_late, f"{kind} default@1.25")
        err_late = abs(angle_diff_rad(d_late.rpy[2], yaw_cmd))
        dt_s = (t_late - t_short) / 1e6
        once_only = err_d2 + RATE_DRIFT_RPS * dt_s
        print(
            f"{kind}: just after 1 s default |yaw-cmd| {err_d2} -> {err_late} "
            f"(once-only drift would be ~{once_only})",
            flush=True,
        )
        assert err_late + math.radians(2.0) < once_only, (
            f"{kind}: default arm fused only once; heading kept drifting like no further mag"
        )


def test_zero_mag_variance_is_weak_default_not_perfect():
    """all-zero mag variance fuses as some positive finite variance: not exact, not a skip.

    Three otherwise identical arms bracket it: no magnetometer at all (a
    skip), the same samples with an explicit very small variance (close to
    infinite trust), and the same samples with all-zero variance. A finite
    positive default pulls heading part of the way: the zero arm's final
    yaw lies strictly between the other two. The size of the library's
    default is not assumed.
    """
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    mag_n = magnetic_north_ned(lat, lon, WMM_YEAR)
    yaw_cmd = _modest_yaw()
    body = body_mag_for_yaw(0.0, 0.0, yaw_cmd, mag_n)
    gyr = (0.0, 0.0, RATE_DRIFT_RPS)
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    none = extend_epochs(list(base), duration_s=3.5, gyr=gyr)
    zero = extend_epochs(
        list(base), duration_s=3.5, gyr=gyr, mag=body, mag_var=MAG_VAR_WEAK
    )
    strong = extend_epochs(
        list(base), duration_s=3.5, gyr=gyr, mag=body, mag_var=MAG_VAR_STRONG
    )

    def _scen(epochs):
        return aiding_site(
            lat, lon, h, epochs, origin_ecef=origin, magnetic_n=mag_n, mag_min_delay_ms=1000
        )

    margin = math.radians(1.0)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        ns = runner(_scen(none)).last()
        zs = runner(_scen(zero)).last()
        ss = runner(_scen(strong)).last()
        require_ready_solution(ns, f"{kind} none")
        require_ready_solution(zs, f"{kind} zero-var")
        require_ready_solution(ss, f"{kind} strong-var")
        pull_zero = angle_diff_rad(zs.rpy[2], ns.rpy[2])
        pull_strong = angle_diff_rad(ss.rpy[2], ns.rpy[2])
        print(
            f"{kind}: yaw vs no-mag arm: zero-var pull={pull_zero} "
            f"strong-var pull={pull_strong}",
            flush=True,
        )
        assert abs(pull_strong) > 2.0 * margin, (
            f"{kind}: scenario error, a near-exact magnetometer did not move heading"
        )
        assert abs(pull_zero) > margin and pull_zero * pull_strong > 0.0, (
            f"{kind}: all-zero mag variance did not act as a heading anchor (treated as a skip)"
        )
        assert abs(pull_zero) + margin < abs(pull_strong), (
            f"{kind}: all-zero mag variance pulled heading as far as an explicit near-exact variance"
        )


def test_arming_wmm_references_true_north_by_declination():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    mag_n = magnetic_north_ned(lat, lon, WMM_YEAR)
    decl, _incl, _f = independent_wmm(lat, lon, WMM_YEAR)
    body = body_mag_for_yaw(0.0, 0.0, 0.0, mag_n)
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    unarmed = extend_epochs(list(base), duration_s=3.0, mag=body, mag_var=MAG_VAR_WEAK)
    armed = extend_epochs(
        list(base),
        duration_s=3.0,
        mag=body,
        mag_var=MAG_VAR_WEAK,
        arm_wmm=(lat, lon, WMM_YEAR),
    )
    un_scen = aiding_site(
        lat, lon, h, unarmed, origin_ecef=origin, magnetic_n=mag_n, mag_min_delay_ms=-1
    )
    ar_scen = aiding_site(
        lat, lon, h, armed, origin_ecef=origin, magnetic_n=mag_n, mag_min_delay_ms=-1
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        urun = runner(un_scen)
        arun = runner(ar_scen)
        u, a = urun.last(), arun.last()
        require_ready_solution(u, f"{kind} unarmed")
        require_ready_solution(a, f"{kind} armed")
        dyaw_deg = angle_diff_deg(_deg(a.rpy[2]), _deg(u.rpy[2]))
        print(
            f"{kind}: unarmed yaw={_deg(u.rpy[2])} armed={_deg(a.rpy[2])} "
            f"d={dyaw_deg} decl={decl}",
            flush=True,
        )
        assert abs(dyaw_deg) > 1.5, f"{kind}: arming WMM did not change heading"
        assert abs(abs(dyaw_deg) - abs(decl)) < 2.5, (
            f"{kind}: armed vs unarmed yaw difference {dyaw_deg} deg "
            f"is not the local declination {decl}"
        )


def test_unusable_horizontal_reference_skips_mag_fusion():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    mag_n = magnetic_north_ned(lat, lon, WMM_YEAR)
    yaw_cmd = runtime_heading_rad()
    body = body_mag_for_yaw(0.0, 0.0, yaw_cmd, mag_n)
    # Near-vertical reference: horizontal component ~0, total field still typical.
    vert_n = (0.0, 0.0, ned_field_from_independent_wmm(lat, lon, WMM_YEAR)[2] or 50.0)
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    usable = extend_epochs(
        list(base), duration_s=3.0, mag=body, mag_var=MAG_VAR_WEAK
    )
    vertical = extend_epochs(
        list(base), duration_s=3.0, mag=body, mag_var=MAG_VAR_WEAK
    )
    zero = extend_epochs(
        list(base),
        duration_s=3.0,
        mag=(1.0e-8, -1.0e-8, 1.0e-8),
        mag_var=MAG_VAR_WEAK,
    )
    none = extend_epochs(list(base), duration_s=3.0)
    kw = dict(origin_ecef=origin, mag_min_delay_ms=-1)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        u = runner(aiding_site(lat, lon, h, usable, magnetic_n=mag_n, **kw)).last()
        v = runner(aiding_site(lat, lon, h, vertical, magnetic_n=vert_n, **kw)).last()
        z = runner(aiding_site(lat, lon, h, zero, magnetic_n=mag_n, **kw)).last()
        n = runner(aiding_site(lat, lon, h, none, magnetic_n=mag_n, **kw)).last()
        require_ready_solution(u, f"{kind} usable")
        require_ready_solution(v, f"{kind} near-vertical")
        require_ready_solution(z, f"{kind} near-zero")
        err_u = abs(angle_diff_rad(u.rpy[2], yaw_cmd))
        err_v = abs(angle_diff_rad(v.rpy[2], yaw_cmd))
        err_z = abs(angle_diff_rad(z.rpy[2], yaw_cmd))
        err_n = abs(angle_diff_rad(n.rpy[2], yaw_cmd))
        print(
            f"{kind}: |yaw-cmd| usable={err_u} vert={err_v} zero={err_z} none={err_n}",
            flush=True,
        )
        assert err_u + math.radians(4.0) < err_n, f"{kind}: usable mag did not pull heading"
        assert err_v > err_u + math.radians(3.0), (
            f"{kind}: near-vertical reference pulled heading like the usable arm"
        )
        assert err_z > err_u + math.radians(3.0), (
            f"{kind}: near-zero magnetometer pulled heading like the usable arm"
        )


# ---------------------------------------------------------------------------
# C. Absolute yaw
# ---------------------------------------------------------------------------


def test_yaw_pi_and_minus_pi_both_fuse_same_heading():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    none = extend_epochs(list(base), duration_s=2.0)
    plus = extend_epochs(
        list(base), duration_s=2.0, yaw_rad=math.pi, yaw_std=YAW_STD_RAD
    )
    minus = extend_epochs(
        list(base), duration_s=2.0, yaw_rad=-math.pi, yaw_std=YAW_STD_RAD
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        n = runner(aiding_site(lat, lon, h, none, origin_ecef=origin)).last()
        p = runner(aiding_site(lat, lon, h, plus, origin_ecef=origin)).last()
        m = runner(aiding_site(lat, lon, h, minus, origin_ecef=origin)).last()
        require_ready_solution(p, f"{kind} +pi")
        require_ready_solution(m, f"{kind} -pi")
        d_pm = abs(angle_diff_rad(p.rpy[2], m.rpy[2]))
        d_pn = abs(angle_diff_rad(p.rpy[2], n.rpy[2]))
        print(
            f"{kind}: yaw +pi={p.rpy[2]} -pi={m.rpy[2]} none={n.rpy[2]} d_pm={d_pm}",
            flush=True,
        )
        assert d_pm < math.radians(8.0), f"{kind}: +pi and -pi did not fuse as the same heading"
        assert d_pn > math.radians(20.0), f"{kind}: +pi was not distinguishable from no yaw"


def test_yaw_zero_to_two_pi_convention_accepted():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    target = 1.5 * math.pi
    wrapped = -0.5 * math.pi
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    none = extend_epochs(list(base), duration_s=2.0)
    a = extend_epochs(
        list(base), duration_s=2.0, yaw_rad=target, yaw_std=YAW_STD_RAD
    )
    b = extend_epochs(
        list(base), duration_s=2.0, yaw_rad=wrapped, yaw_std=YAW_STD_RAD
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        n = runner(aiding_site(lat, lon, h, none, origin_ecef=origin)).last()
        pa = runner(aiding_site(lat, lon, h, a, origin_ecef=origin)).last()
        pb = runner(aiding_site(lat, lon, h, b, origin_ecef=origin)).last()
        require_ready_solution(pa, f"{kind} 3pi/2")
        require_ready_solution(pb, f"{kind} -pi/2")
        d = abs(angle_diff_rad(pa.rpy[2], pb.rpy[2]))
        d_an = abs(angle_diff_rad(pa.rpy[2], n.rpy[2]))
        d_bn = abs(angle_diff_rad(pb.rpy[2], n.rpy[2]))
        err_a = abs(angle_diff_rad(pa.rpy[2], target))
        err_b = abs(angle_diff_rad(pb.rpy[2], wrapped))
        print(
            f"{kind}: 3pi/2 yaw={pa.rpy[2]} -pi/2 yaw={pb.rpy[2]} none={n.rpy[2]} "
            f"d={d} d_an={d_an} d_bn={d_bn}",
            flush=True,
        )
        assert d < math.radians(8.0), f"{kind}: [0, 2pi) and wrapped heading disagreed"
        assert err_a < math.radians(15.0), f"{kind}: 3pi/2 was not pulled toward the heading"
        assert err_b < math.radians(15.0), f"{kind}: -pi/2 was not pulled toward the heading"
        assert d_an > math.radians(20.0), f"{kind}: 3pi/2 was not distinguishable from no yaw"
        assert d_bn > math.radians(20.0), f"{kind}: -pi/2 was not distinguishable from no yaw"


def test_yaw_beyond_one_turn_dropped_invalid_counter():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    extra = 2.0 * math.pi + 0.7
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    hold = extend_epochs(list(base), duration_s=0.4)
    t_before = hold[-1].t_us
    bad = extend_epochs(
        list(hold), duration_s=0.8, yaw_rad=3.0 * math.pi, yaw_std=YAW_STD_RAD
    )
    extra_ep = extend_epochs(
        list(hold), duration_s=0.8, yaw_rad=extra, yaw_std=YAW_STD_RAD
    )
    good = extend_epochs(
        list(hold), duration_s=0.8, yaw_rad=math.pi, yaw_std=YAW_STD_RAD
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        run = runner(aiding_site(lat, lon, h, bad, origin_ecef=origin))
        before = run.at_or_after(t_before - 10_000)
        last = run.last()
        require_ready_solution(last, f"{kind} after 3pi")
        print(
            f"{kind}: yaw before={before.rpy[2]} after={last.rpy[2]} "
            f"invalid {before.n_invalid} -> {last.n_invalid}",
            flush=True,
        )
        assert abs(angle_diff_rad(last.rpy[2], math.pi)) > math.radians(20.0), (
            f"{kind}: 3pi was wrapped and fused as pi"
        )
        assert last.n_invalid > before.n_invalid, (
            f"{kind}: 3pi did not increment the invalid-input counter"
        )
        run2 = runner(aiding_site(lat, lon, h, extra_ep, origin_ecef=origin))
        last2 = run2.last()
        before2 = run2.at_or_after(t_before - 10_000)
        assert last2.n_invalid > before2.n_invalid, (
            f"{kind}: |yaw|>2pi did not increment the invalid-input counter"
        )
        grun = runner(aiding_site(lat, lon, h, good, origin_ecef=origin))
        g_before = grun.at_or_after(t_before - 10_000)
        g_last = grun.last()
        require_ready_solution(g_last, f"{kind} in-range yaw")
        err_g = abs(angle_diff_rad(g_last.rpy[2], math.pi))
        print(
            f"{kind}: in-range yaw={g_last.rpy[2]} err={err_g} "
            f"invalid {g_before.n_invalid}->{g_last.n_invalid}",
            flush=True,
        )
        assert err_g < math.radians(15.0), f"{kind}: in-range yaw was not pulled"
        assert g_last.n_invalid == g_before.n_invalid, (
            f"{kind}: in-range yaw incremented the invalid-input counter"
        )


def test_yaw_skipped_near_gimbal_lock():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    target = runtime_heading_rad()
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    level = extend_epochs(
        list(base), duration_s=2.0, yaw_rad=target, yaw_std=YAW_STD_RAD
    )
    pitched = list(base)
    omega = 0.72
    n = int(round(2.2 * 100))
    t0 = pitched[-1].t_us
    dt = 0.01
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        pitch = omega * i * dt
        pitched.append(
            AidingEpoch(
                t_us=t_us,
                dt_sec=dt,
                acc=still_level_acc(pitch),
                gyr=(0.0, omega, 0.0),
                gnss_ecef=origin if i % 100 == 0 else None,
                gnss_std=GNSS_STD_M if i % 100 == 0 else None,
            )
        )
    pitched = extend_epochs(
        pitched, duration_s=0.8, acc=still_level_acc(omega * 2.2), yaw_rad=target, yaw_std=YAW_STD_RAD
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        lv = runner(aiding_site(lat, lon, h, level, origin_ecef=origin)).last()
        pv = runner(aiding_site(lat, lon, h, pitched, origin_ecef=origin)).last()
        require_ready_solution(lv, f"{kind} level yaw")
        require_ready_solution(pv, f"{kind} high pitch")
        err_l = abs(angle_diff_rad(lv.rpy[2], target))
        err_p = abs(angle_diff_rad(pv.rpy[2], target))
        print(
            f"{kind}: level yaw={lv.rpy[2]} pitch={pv.rpy[1]} high-yaw={pv.rpy[2]} "
            f"err_l={err_l} err_p={err_p}",
            flush=True,
        )
        assert err_l < math.radians(15.0), f"{kind}: level arm was not pulled toward the yaw"
        assert err_p > err_l + math.radians(10.0), (
            f"{kind}: yaw near gimbal lock was fused like the level arm"
        )


# ---------------------------------------------------------------------------
# D. Scalar ground speed
# ---------------------------------------------------------------------------


def test_along_track_speed_error_pulled_toward_measurement():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    truth = 8.0
    biased = 10.0
    still = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    walked = extend_gnss_constant_vel(
        list(still), origin, (biased, 0.0, 0.0), duration_s=3.0
    )
    with_speed = extend_epochs(list(walked), duration_s=2.5, speed_mps=truth)
    no_speed = extend_epochs(list(walked), duration_s=2.5)
    kw = dict(origin_ecef=origin, auto_zupt_disable=True)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        s = runner(aiding_site(lat, lon, h, with_speed, **kw)).last()
        n = runner(aiding_site(lat, lon, h, no_speed, **kw)).last()
        require_ready_solution(s, f"{kind} speed")
        require_ready_solution(n, f"{kind} no speed")
        err_s = abs(s.vel_ned[0] - truth)
        err_n = abs(n.vel_ned[0] - truth)
        print(f"{kind}: vn with={s.vel_ned[0]} without={n.vel_ned[0]} truth={truth}", flush=True)
        assert err_s + 0.8 < err_n, f"{kind}: along-track speed was not pulled toward the measurement"


def test_sideways_velocity_error_not_corrected_by_speed():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    biased = 10.0
    truth = 6.0
    still = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    along_walked = extend_gnss_constant_vel(
        list(still), origin, (biased, 0.0, 0.0), duration_s=3.0
    )
    along_s = extend_epochs(list(along_walked), duration_s=2.5, speed_mps=truth)
    along_n = extend_epochs(list(along_walked), duration_s=2.5)
    side = gnss_stream(
        origin,
        duration_s=HAPPY_DURATION_S,
        gnss_vel=(0.0, biased, 0.0),
        gnss_vel_std=GNSS_VEL_STD,
    )
    side_s = extend_epochs(list(side), duration_s=2.5, speed_mps=biased)
    side_n = extend_epochs(list(side), duration_s=2.5)
    kw = dict(origin_ecef=origin, auto_zupt_disable=True)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        a = runner(aiding_site(lat, lon, h, along_s, **kw)).last()
        an = runner(aiding_site(lat, lon, h, along_n, **kw)).last()
        s = runner(aiding_site(lat, lon, h, side_s, **kw)).last()
        n = runner(aiding_site(lat, lon, h, side_n, **kw)).last()
        require_ready_solution(a, f"{kind} along")
        require_ready_solution(s, f"{kind} side")
        err_a = abs(a.vel_ned[0] - truth)
        err_an = abs(an.vel_ned[0] - truth)
        print(
            f"{kind}: along vn speed={a.vel_ned[0]} none={an.vel_ned[0]} "
            f"side vn={s.vel_ned[0]} ve={s.vel_ned[1]} no-speed vn={n.vel_ned[0]} ve={n.vel_ned[1]}",
            flush=True,
        )
        assert err_a + 0.8 < err_an, (
            f"{kind}: along-track arm was not pulled by speed (live baseline missing)"
        )
        assert abs(s.vel_ned[0]) < 3.0, (
            f"{kind}: scalar speed invented an along-track velocity from a sideways error"
        )
        assert abs(s.vel_ned[0] - n.vel_ned[0]) < 2.0, (
            f"{kind}: scalar speed steered the sideways arm's direction"
        )


def test_speed_sample_skipped_below_default_1_mps():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    low = 0.5
    fuse = 1.5
    speed_meas = 4.0
    kw = dict(origin_ecef=origin, auto_zupt_disable=True)

    def _pair(v):
        base = gnss_stream(
            origin,
            duration_s=HAPPY_DURATION_S,
            gnss_vel=(v, 0.0, 0.0),
            gnss_vel_std=GNSS_VEL_STD,
        )
        with_s = extend_epochs(list(base), duration_s=2.5, speed_mps=speed_meas)
        no_s = extend_epochs(list(base), duration_s=2.5)
        return with_s, no_s

    low_s, low_n = _pair(low)
    fuse_s, fuse_n = _pair(fuse)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        ls = runner(aiding_site(lat, lon, h, low_s, **kw)).last()
        ln = runner(aiding_site(lat, lon, h, low_n, **kw)).last()
        fs = runner(aiding_site(lat, lon, h, fuse_s, **kw)).last()
        fn = runner(aiding_site(lat, lon, h, fuse_n, **kw)).last()
        require_ready_solution(ls, f"{kind} low+speed")
        require_ready_solution(fs, f"{kind} fuse+speed")
        d_low = abs(ls.vel_ned[0] - ln.vel_ned[0])
        d_fuse = abs(fs.vel_ned[0] - fn.vel_ned[0])
        print(
            f"{kind}: low vn speed={ls.vel_ned[0]} none={ln.vel_ned[0]} d={d_low}; "
            f"fuse vn speed={fs.vel_ned[0]} none={fn.vel_ned[0]} d={d_fuse}",
            flush=True,
        )
        assert d_fuse > 0.25, f"{kind}: just-over-1 m/s speed did not pull along-track"
        assert d_low < d_fuse * 0.5, (
            f"{kind}: below-1 m/s sample pulled like the just-over-1 arm"
        )


# ---------------------------------------------------------------------------
# E. Barometric height inside INS
# ---------------------------------------------------------------------------

GNSS_OFFSET_STD = (5.0, 5.0, 5.0)


def _baro_gnss_offset(origin, pad, north_m, down_m, *, duration_s=6.0):
    """Pad GNSS, then a static GNSS NED offset with covariance that still fuses."""
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S, baro_pa=pad)
    shifted = ecef_plus_ned(origin, north_m, 0.0, down_m)
    return extend_epochs(
        list(base),
        duration_s=duration_s,
        gnss_ecef=shifted,
        gnss_std=GNSS_OFFSET_STD,
        gnss_hz=LOCAL_HZ,
        baro_pa=pad,
    )


def test_baro_height_source_restricts_gnss_to_horizontal():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    pad = isa_pressure_pa(h)
    dn, dd = 12.0, -14.0
    both = _baro_gnss_offset(origin, pad, dn, dd)
    off = aiding_site(
        lat, lon, h, both, origin_ecef=origin, baro_height_disable=False, auto_zupt_disable=True
    )
    on = aiding_site(
        lat, lon, h, both, origin_ecef=origin, baro_height_disable=True, auto_zupt_disable=True
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        a = runner(off).last()
        b = runner(on).last()
        require_ready_solution(a, f"{kind} baro source")
        require_ready_solution(b, f"{kind} GNSS height")
        print(
            f"{kind}: baro-src ned={a.ned} gnss-src ned={b.ned} target n={dn} d={dd}",
            flush=True,
        )
        assert abs(a.ned[0] - dn) < 10.0, (
            f"{kind}: GNSS north offset was dropped with the barometer selected"
        )
        assert abs(a.ned[2]) < 8.0, f"{kind}: vertical followed GNSS while baro was the source"
        assert abs(b.ned[2] - dd) < 8.0, f"{kind}: disable switch did not force GNSS height"
        assert abs(a.ned[2] - b.ned[2]) > 8.0, (
            f"{kind}: disable switch did not change the vertical source"
        )


def test_gnss_outage_keeps_usable_vertical_with_baro_default():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    pad = isa_pressure_pa(h)
    offset = _baro_gnss_offset(origin, pad, 0.0, -14.0)
    outage = extend_epochs(list(offset), duration_s=3.5, baro_pa=pad)
    off = aiding_site(
        lat, lon, h, outage, origin_ecef=origin, baro_height_disable=False, auto_zupt_disable=True
    )
    on = aiding_site(
        lat, lon, h, outage, origin_ecef=origin, baro_height_disable=True, auto_zupt_disable=True
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        a = runner(off).last()
        b = runner(on).last()
        require_ready_solution(a, f"{kind} outage baro")
        require_ready_solution(b, f"{kind} outage GNSS-height")
        print(f"{kind}: outage baro-src down={a.ned[2]} gnss-src down={b.ned[2]}", flush=True)
        assert abs(a.ned[2]) < 8.0, f"{kind}: baro source did not keep a usable pad vertical"
        assert abs(a.ned[2] - b.ned[2]) > 6.0, (
            f"{kind}: GNSS-height outage matched the barometer-maintained vertical"
        )


def test_baro_height_disable_forces_gnss_height():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    pad = isa_pressure_pa(h)
    both = _baro_gnss_offset(origin, pad, 6.0, -14.0)
    on = aiding_site(
        lat, lon, h, both, origin_ecef=origin, baro_height_disable=True, auto_zupt_disable=True
    )
    off = aiding_site(
        lat, lon, h, both, origin_ecef=origin, baro_height_disable=False, auto_zupt_disable=True
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        forced = runner(on).last()
        baro = runner(off).last()
        require_ready_solution(forced, f"{kind} disable on")
        print(
            f"{kind}: disable-on down={forced.ned[2]} disable-off down={baro.ned[2]}",
            flush=True,
        )
        assert abs(forced.ned[2] + 14.0) < 8.0, f"{kind}: disable did not follow GNSS vertical"
        assert abs(baro.ned[2]) < abs(forced.ned[2]) - 4.0, (
            f"{kind}: disable-off vertical was not the barometer"
        )


def test_local_pos_bootstrap_keeps_tracker_height_with_baro():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    other = isa_pressure_pa(h + 45.0)
    epochs = local_stream(TRACKER_NAMED_NED, baro_pa=other)
    scen = aiding_site(lat, lon, h, epochs, origin_ecef=origin)
    for kind, run in _langs(scen):
        last = run.last()
        require_ready_solution(last, f"{kind} local+baro")
        _assert_ned_matches(last.ned, TRACKER_NAMED_NED, f"{kind} tracker with baro")
        print(f"{kind}: local+baro down={last.ned[2]}", flush=True)
        assert abs(last.ned[2]) < 1.0, f"{kind}: local bootstrap vertical followed the barometer"


# ---------------------------------------------------------------------------
# F. Explicit and automatic ZUPT/ZARU
# ---------------------------------------------------------------------------


def _one_interval_flag_runs(runner, lat, lon, h, base, t_flag, kw, *, gyr, zupt=False, zaru=False):
    """Standstill flags inside one filter-update interval, located by n_predict.

    An unflagged twin is run first. Its public ``n_predict`` counter marks the
    filter-update epochs; the burst is every IMU epoch strictly between the
    first two consecutive filter-update epochs after *t_flag* that enclose at
    least two epochs. ``one`` flags only the first epoch of that burst,
    ``dense`` flags all of them. When every IMU epoch is a filter-update epoch
    no such interval exists, the burst is a single epoch, and dense equals one.
    Returns the last snapshots of (none, one, dense) and the burst size.
    """
    tail = extend_epochs(list(base), duration_s=0.6, gyr=gyr)
    none_run = runner(aiding_site(lat, lon, h, tail, **kw))
    after = [sn for sn in none_run.snaps if sn.t_us > t_flag]
    preds = [sn.n_predict for sn in after]
    assert after and all(p >= 0 for p in preds), "n_predict diagnostic was not readable"
    search_end = t_flag + 300_000
    burst: list[int] = []
    for i in range(1, len(after)):
        if after[i].t_us > search_end:
            break
        if preds[i] > preds[i - 1]:
            j = i + 1
            while j < len(after) and preds[j] == preds[i]:
                j += 1
            if j - (i + 1) >= 2:
                burst = [after[k].t_us for k in range(i + 1, j)]
                break
    if not burst:
        burst = [after[0].t_us]
    on = set(burst)
    one_eps = [
        replace(e, zupt=bool(zupt and e.t_us == burst[0]), zaru=bool(zaru and e.t_us == burst[0]))
        for e in tail
    ]
    dense_eps = [
        replace(e, zupt=bool(zupt and e.t_us in on), zaru=bool(zaru and e.t_us in on))
        for e in tail
    ]
    one_run = runner(aiding_site(lat, lon, h, one_eps, **kw))
    dense_run = runner(aiding_site(lat, lon, h, dense_eps, **kw))
    pred_none = {sn.t_us: sn.n_predict for sn in after}
    pred_dense = {sn.t_us: sn.n_predict for sn in dense_run.snaps if sn.t_us in on}
    assert all(pred_dense.get(t) == pred_none[t] for t in burst), (
        "standstill flags changed which epochs were filter-update epochs"
    )
    return none_run.last(), one_run.last(), dense_run.last(), len(burst)


def test_explicit_zupt_holds_velocity_near_zero():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    base = gnss_stream(
        origin,
        duration_s=HAPPY_DURATION_S,
        gnss_vel=(3.5, 0.0, 0.0),
        gnss_vel_std=GNSS_VEL_STD,
    )
    t_flag = base[-1].t_us
    flagged = extend_epochs(list(base), duration_s=2.0, zupt=True)
    clear = extend_epochs(list(base), duration_s=2.0)
    kw = dict(origin_ecef=origin, auto_zupt_disable=True)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        z = runner(aiding_site(lat, lon, h, flagged, **kw)).last()
        c = runner(aiding_site(lat, lon, h, clear, **kw)).last()
        require_ready_solution(z, f"{kind} ZUPT")
        require_ready_solution(c, f"{kind} no ZUPT")
        zs, ns = horiz_speed(z.vel_ned), horiz_speed(c.vel_ned)
        print(f"{kind}: |v| ZUPT={zs} none={ns}", flush=True)
        assert zs < 0.6, f"{kind}: explicit ZUPT did not hold velocity near zero"
        assert ns > zs + 1.0, f"{kind}: no-flag arm was held like explicit ZUPT"
        none, one, dense, n_burst = _one_interval_flag_runs(
            runner, lat, lon, h, base, t_flag, kw, gyr=(0.0, 0.0, 0.0), zupt=True
        )
        require_ready_solution(none, f"{kind} ZUPT unflagged twin")
        require_ready_solution(dense, f"{kind} ZUPT dense flags")
        require_ready_solution(one, f"{kind} ZUPT one flag")
        hs_n = horiz_speed(none.vel_ned)
        hs_d, hs_1 = horiz_speed(dense.vel_ned), horiz_speed(one.vel_ned)
        print(
            f"{kind}: |v| none={hs_n} dense-flags={hs_d} one-flag={hs_1} burst={n_burst}",
            flush=True,
        )
        assert hs_1 + 0.5 < hs_n, (
            f"{kind}: a single explicit ZUPT in the interval did not fuse"
        )
        assert abs(hs_d - hs_1) < 0.4, (
            f"{kind}: extra explicit ZUPT flags in one filter-update interval "
            f"pulled harder than one fusion"
        )


def test_explicit_zaru_measures_still_body_gyro_bias():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    bias = (0.0, 0.0, 0.04)
    base = gnss_stream(origin, duration_s=HAPPY_DURATION_S, gyr=bias)
    t_flag = base[-1].t_us
    flagged = extend_epochs(list(base), duration_s=2.5, gyr=bias, zaru=True)
    clear = extend_epochs(list(base), duration_s=2.5, gyr=bias)
    kw = dict(origin_ecef=origin, auto_zupt_disable=True)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        z = runner(aiding_site(lat, lon, h, flagged, **kw)).last()
        c = runner(aiding_site(lat, lon, h, clear, **kw)).last()
        require_ready_solution(z, f"{kind} ZARU")
        require_ready_solution(c, f"{kind} no ZARU")
        assert z.bias_gyr is not None and c.bias_gyr is not None
        err_z = abs(z.bias_gyr[2] - bias[2])
        err_c = abs(c.bias_gyr[2] - bias[2])
        print(
            f"{kind}: gyr bias z={z.bias_gyr[2]} none={c.bias_gyr[2]} true={bias[2]}",
            flush=True,
        )
        assert err_z + 0.005 < err_c, f"{kind}: explicit ZARU did not pull gyro bias"
        none, one, dense, n_burst = _one_interval_flag_runs(
            runner, lat, lon, h, base, t_flag, kw, gyr=bias, zaru=True
        )
        require_ready_solution(none, f"{kind} ZARU unflagged twin")
        require_ready_solution(dense, f"{kind} ZARU dense flags")
        require_ready_solution(one, f"{kind} ZARU one flag")
        assert none.bias_gyr is not None
        assert dense.bias_gyr is not None and one.bias_gyr is not None
        err_n = abs(none.bias_gyr[2] - bias[2])
        err_d = abs(dense.bias_gyr[2] - bias[2])
        err_1 = abs(one.bias_gyr[2] - bias[2])
        print(
            f"{kind}: gyr bias none={none.bias_gyr[2]} dense={dense.bias_gyr[2]} "
            f"one={one.bias_gyr[2]} burst={n_burst}",
            flush=True,
        )
        assert err_1 + 0.003 < err_n, (
            f"{kind}: a single explicit ZARU in the interval did not fuse"
        )
        assert abs(err_d - err_1) < 0.004, (
            f"{kind}: extra explicit ZARU flags in one filter-update interval "
            f"pulled harder than one fusion"
        )


def test_auto_detector_stationary_after_dwell_not_on_turntable():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    moving = gnss_stream(origin, duration_s=HAPPY_DURATION_S, gyr=(0.0, 0.0, TURN_RPS))
    still = extend_wobble(list(moving), duration_s=1.0)
    t_wobble = still[-1].t_us
    still = extend_epochs(list(still), duration_s=2.0)
    table = extend_epochs(list(moving), duration_s=1.5, gyr=(0.0, 0.0, TURN_RPS))
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        srun = runner(aiding_site(lat, lon, h, still, origin_ecef=origin))
        trun = runner(aiding_site(lat, lon, h, table, origin_ecef=origin))
        first = srun.at_or_after(t_wobble + 10_000)
        handful = srun.at_or_after(t_wobble + 50_000)
        later = srun.at_or_after(t_wobble + 1_200_000)
        tlast = trun.last()
        print(
            f"{kind}: still first={first.stationary} handful={handful.stationary} "
            f"later={later.stationary} turntable={tlast.stationary}",
            flush=True,
        )
        require_ready_solution(srun.last(), f"{kind} still")
        assert not first.stationary, f"{kind}: first still sample was already stationary"
        assert not handful.stationary, f"{kind}: a handful of samples already reported stationary"
        assert later.stationary, f"{kind}: still IMU after the dwell was not stationary"
        assert not tlast.stationary, f"{kind}: constant-rate turntable reported stationary"


def test_auto_zupt_fuses_zero_velocity_without_explicit_flag():
    # Accurate GNSS cruising at constant speed from the first epoch, with a
    # still IMU (constant velocity looks like stillness to the IMU); the filter
    # bootstraps on it, then the GNSS stops. While GNSS velocity is recent the
    # speed gate holds the detector off; once it has aged out (the PRD bounds
    # "recent" at 3 s) the still IMU alone is stillness and the detector fuses
    # zero velocity. The end of a long still segment is read, so an early
    # pre-bootstrap ZUPT cannot pass.
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    cruise_mps = 3.2
    first = gnss_stream(origin, duration_s=0.01)
    cruise = extend_gnss_constant_vel(
        list(first),
        origin,
        (cruise_mps, 0.0, 0.0),
        duration_s=HAPPY_DURATION_S + 2.0,
        gnss_vel_std=GNSS_VEL_STD,
    )
    t_gnss_end = cruise[-1].t_us
    epochs = extend_epochs(list(cruise), duration_s=7.0)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        on_run = runner(
            aiding_site(lat, lon, h, epochs, origin_ecef=origin, auto_zupt_disable=False)
        )
        off_run = runner(
            aiding_site(lat, lon, h, epochs, origin_ecef=origin, auto_zupt_disable=True)
        )
        cruising = on_run.at_or_after(t_gnss_end)
        on, off = on_run.last(), off_run.last()
        require_ready_solution(cruising, f"{kind} auto on, end of GNSS")
        require_ready_solution(on, f"{kind} auto on")
        require_ready_solution(off, f"{kind} auto off")
        hs_cruise = horiz_speed(cruising.vel_ned)
        hs_on, hs_off = horiz_speed(on.vel_ned), horiz_speed(off.vel_ned)
        print(
            f"{kind}: |v| end-of-GNSS={hs_cruise} segment-end auto-on={hs_on} "
            f"auto-off={hs_off}",
            flush=True,
        )
        assert hs_cruise > 2.0, (
            f"{kind}: filter did not follow accurate GNSS cruising speed while the "
            f"speed gate should hold the detector off"
        )
        assert hs_on < 1.0, f"{kind}: auto ZUPT did not hold velocity near zero"
        assert hs_off > hs_on + 1.0, f"{kind}: auto-off arm was held like automatic ZUPT"


def test_auto_zupt_ignores_filter_velocity_on_biased_imu():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    gyr = (0.0, 0.0, 0.015)
    acc = (0.12, 0.0, -9.81)
    moving = gnss_stream(
        origin,
        duration_s=HAPPY_DURATION_S,
        gyr=(0.0, 0.0, TURN_RPS),
        gnss_vel=(3.5, 0.0, 0.0),
        gnss_vel_std=GNSS_VEL_STD,
    )
    t0 = moving[-1].t_us
    biased = extend_epochs(list(moving), duration_s=4.0, acc=acc, gyr=gyr)
    kw_on = dict(origin_ecef=origin, auto_zupt_disable=False)
    kw_off = dict(origin_ecef=origin, auto_zupt_disable=True)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        on_run = runner(aiding_site(lat, lon, h, biased, **kw_on))
        off_run = runner(aiding_site(lat, lon, h, biased, **kw_off))
        # 50 ms is this suite's handful (still short of a dwell). The after-dwell
        # arm is the first stationary diagnostic after that handful. Whether the
        # first automatic ZUPT is fused in that same epoch is not specified, so
        # the filter's own speed is read on the epoch just before it: the
        # detector declared stillness while that speed was above the gate.
        after = on_run.first_stationary_after(t0 + 50_000)
        # Walk back to the onset of that stationary verdict; the epoch just
        # before the onset carries the filter speed the detector ignored.
        snaps = [s for s in on_run.snaps if s.vel_ned is not None]
        k = next(i for i, s in enumerate(snaps) if s.t_us == after.t_us)
        while k > 0 and snaps[k - 1].stationary:
            k -= 1
        assert k > 0, f"{kind}: stationary from the first published epoch"
        pre = snaps[k - 1]
        later = on_run.last()
        off = off_run.last()
        require_ready_solution(later, f"{kind} biased still")
        require_ready_solution(off, f"{kind} auto-off twin")
        hs_after = horiz_speed(pre.vel_ned)
        hs_on = horiz_speed(later.vel_ned)
        hs_off = horiz_speed(off.vel_ned)
        print(
            f"{kind}: after-dwell dt_ms={(after.t_us - t0) / 1000.0} "
            f"|v|={hs_after} stationary={after.stationary} "
            f"later |v|={hs_on} stationary={later.stationary} auto-off |v|={hs_off}",
            flush=True,
        )
        assert after.stationary, (
            f"{kind}: detector gated on filter velocity: no stationary "
            f"verdict after the dwell while the still IMU was biased"
        )
        assert hs_after > SPEED_MIN_MPS, (
            f"{kind}: filter speed was not above the speed gate on the epoch before "
            f"the detector first reported stationary after the dwell"
        )
        assert later.stationary, (
            f"{kind}: biased still IMU was not stationary (detector gated on filter velocity)"
        )
        assert hs_off > SPEED_MIN_MPS, (
            f"{kind}: auto-off twin did not keep filter speed above the speed gate"
        )
        assert hs_off > hs_on + 1.0, (
            f"{kind}: auto-off twin was held like automatic ZUPT"
        )


def test_auto_zupt_gnss_speed_gate_blocks_when_moving():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    still_imu = SPECIFIC_FORCE_LEVEL
    rest = gnss_stream(
        origin,
        duration_s=HAPPY_DURATION_S + 1.5,
        acc=still_imu,
        gnss_vel=(0.05, 0.0, 0.0),
        gnss_vel_std=GNSS_VEL_STD,
    )
    move = gnss_stream(
        origin,
        duration_s=HAPPY_DURATION_S + 1.5,
        acc=still_imu,
        gnss_vel=(4.0, 0.0, 0.0),
        gnss_vel_std=GNSS_VEL_STD,
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        r = runner(aiding_site(lat, lon, h, rest, origin_ecef=origin)).last()
        m = runner(aiding_site(lat, lon, h, move, origin_ecef=origin)).last()
        require_ready_solution(r, f"{kind} GNSS rest")
        require_ready_solution(m, f"{kind} GNSS moving")
        print(f"{kind}: stationary rest={r.stationary} moving={m.stationary}", flush=True)
        assert r.stationary, f"{kind}: near-zero GNSS speed blocked stationary"
        assert not m.stationary, f"{kind}: several m/s GNSS speed still reported stationary"


def test_auto_zupt_not_on_single_sample_no_imu_leaves_latch():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    moving = gnss_stream(origin, duration_s=HAPPY_DURATION_S, gyr=(0.0, 0.0, TURN_RPS))
    wobble = extend_wobble(list(moving), duration_s=1.0)
    t_wobble = wobble[-1].t_us
    still = extend_epochs(list(wobble), duration_s=1.2)
    latched = extend_epochs(list(still), duration_s=0.05)
    no_imu = extend_epochs(
        list(latched), duration_s=0.3, acc_valid=False, gyr_valid=False
    )
    resumed = extend_epochs(list(no_imu), duration_s=0.08)
    turn = extend_epochs(
        list(latched), duration_s=0.3, gyr=(0.0, 0.0, TURN_RPS)
    )
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        srun = runner(aiding_site(lat, lon, h, still, origin_ecef=origin))
        first = srun.at_or_after(t_wobble + 10_000)
        handful = srun.at_or_after(t_wobble + 50_000)
        assert not first.stationary, f"{kind}: first still sample after motion was already stationary"
        assert not handful.stationary, f"{kind}: a handful of samples already reported stationary"
        trun = runner(aiding_site(lat, lon, h, turn, origin_ecef=origin))
        after_turn = trun.last()
        assert not after_turn.stationary, f"{kind}: turntable IMU left the latch set"
        if kind == "c":
            rrun = runner(aiding_site(lat, lon, h, resumed, origin_ecef=origin))
            latched_snap = srun.last()
            after_gap = rrun.last()
            print(
                f"{kind}: latch={latched_snap.stationary} resumed={after_gap.stationary} "
                f"turn={after_turn.stationary}",
                flush=True,
            )
            assert latched_snap.stationary, f"{kind}: dwell did not latch stationary"
            assert after_gap.stationary, (
                f"{kind}: stillness window was reset by a no-IMU gap "
                "(first still IMU after the gap was not immediately stationary)"
            )
        else:
            print(f"{kind}: turntable after latch={after_turn.stationary}", flush=True)


def test_auto_disable_does_not_block_explicit_flags():
    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    base = gnss_stream(
        origin,
        duration_s=HAPPY_DURATION_S,
        gnss_vel=(3.0, 0.0, 0.0),
        gnss_vel_std=GNSS_VEL_STD,
    )
    still = extend_epochs(list(base), duration_s=1.5)
    flagged = extend_epochs(list(base), duration_s=1.5, zupt=True)
    kw_off = dict(origin_ecef=origin, auto_zupt_disable=True)
    for kind, runner in (("c", c_aiding_run), ("py", py_aiding_run)):
        off = runner(aiding_site(lat, lon, h, still, **kw_off)).last()
        z = runner(aiding_site(lat, lon, h, flagged, **kw_off)).last()
        require_ready_solution(off, f"{kind} disabled")
        require_ready_solution(z, f"{kind} disabled+ZUPT")
        print(
            f"{kind}: disabled stationary={off.stationary} |v|={horiz_speed(off.vel_ned)} "
            f"ZUPT |v|={horiz_speed(z.vel_ned)}",
            flush=True,
        )
        assert not off.stationary, f"{kind}: detector stayed on while disabled"
        assert horiz_speed(z.vel_ned) < 0.6, f"{kind}: disable blocked explicit ZUPT"
        assert horiz_speed(off.vel_ned) > horiz_speed(z.vel_ned) + 1.0

    # Runtime disable then re-enable requires a fresh dwell (C public switch).
    moving = gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    c_epochs = extend_epochs(
        list(moving), duration_s=0.05, auto_zupt_disable=1, gnss_ecef=origin, gnss_std=GNSS_STD_M
    )
    c_epochs = extend_epochs(
        list(c_epochs), duration_s=0.6, gnss_ecef=origin, gnss_std=GNSS_STD_M
    )
    t_re = c_epochs[len(moving)].t_us
    c_epochs = extend_epochs(
        list(c_epochs), duration_s=0.05, auto_zupt_disable=0, gnss_ecef=origin, gnss_std=GNSS_STD_M
    )
    c_epochs = extend_epochs(
        list(c_epochs), duration_s=0.08, gnss_ecef=origin, gnss_std=GNSS_STD_M
    )
    t_just = c_epochs[-1].t_us
    c_epochs = extend_epochs(
        list(c_epochs), duration_s=2.0, gnss_ecef=origin, gnss_std=GNSS_STD_M
    )
    print(f"c runtime epochs={len(c_epochs)}", flush=True)
    assert len(c_epochs) > 1000, f"runtime disable stream too short: {len(c_epochs)}"
    crun = c_aiding_run(aiding_site(lat, lon, h, c_epochs, origin_ecef=origin))
    disabled = crun.at_or_after(t_re)
    just = crun.at_or_after(t_just)
    later = crun.last()
    print(
        f"c runtime: disabled stationary={disabled.stationary} "
        f"just-after-enable={just.stationary} later={later.stationary}",
        flush=True,
    )
    assert not disabled.stationary
    assert not just.stationary, "re-enable reported stationary immediately"
    assert later.stationary, "re-enable never became stationary after a fresh dwell"


def test_published_aiding_snapshots_are_well_formed():
    """Published values are finite, attitude is not published without its
    1-sigma, ``ins_get_diag`` is available on a live instance and its counters
    are non-negative -- on every aiding snapshot parsed in this session and on
    a GNSS pad of its own. A violation fails this test only.
    """
    from _harness import require_no_product_issues

    lat, lon, h = runtime_wmm_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    scen = aiding_site(lat, lon, h, gnss_stream(origin, duration_s=HAPPY_DURATION_S), origin_ecef=origin)
    for runner in (c_aiding_run, py_aiding_run):
        run = runner(scen)
        assert run.snaps, "pad produced no snapshots"
    require_no_product_issues("F03", "aiding snapshots (F03)")
