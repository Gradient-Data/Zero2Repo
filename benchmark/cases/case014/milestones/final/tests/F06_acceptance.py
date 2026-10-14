# feature: F06
"""Standalone ARS and AHRS attitude (FP-06).

Assertions stay at the PRD's precision: ARS yaw free-integrates the
bias-corrected z-rate even when a magnetometer is present; AHRS yaw is
pulled toward the magnetic (or true-north) reference without tilting
roll/pitch; the named 10 s static scenario meets 0.2° / 0.1 °/s;
supplying a geographic position steps published yaw by the WMM
declination without jumping the gyro-bias estimate; the leveling helper
on (0, 0, −g) is near zero and distinguishable from a tilted sample;
standalone init refuses a non-positive mandatory standard deviation or a
non-finite initial attitude and accepts a zero attitude; non-finite IMU
samples drop the epoch, non-finite magnetometer samples are ignored;
backwards time skips that epoch; a forward gap larger than 0.2 s skips
attitude integration; unusable fields skip heading fusion; the optional
field-strength gate downweights rather than drops; suite ARS starts on
IMU alone with yaw 0 unless a known heading was supplied, and suite AHRS
waits for the first magnetometer sample. Once the watchdog warm-up has
elapsed, a reported attitude 1-sigma above its documented threshold
(10 deg roll/pitch, 90 deg AHRS yaw by default, or the configured value)
fails attitude accessors, the suite re-bootstraps on the next suitable
epoch, and a standalone instance stays unpublished until the caller
re-inits; when that happens is read from the implementation's own
reported 1-sigma, not from assumed noise tuning. Message text, exception
types, internal mode spellings, unpublished fusion periods, and default
noise tuning are not pinned.
"""

from __future__ import annotations

import math

from F01_helpers import hypot3
from F02_helpers import (
    ENTRY_DWELL_S,
    READY_WAIT_S,
    SPECIFIC_FORCE_LEVEL,
    ecef_from_llh_deg,
)
from F03_helpers import (
    G_MPS2,
    angle_diff_rad,
    body_mag_for_yaw,
    ned_field_from_independent_wmm,
    still_level_acc,
)
from F06_helpers import (
    ATT_YEAR,
    FIELD_TOL_NAMED,
    GAP_INSIDE_S,
    GAP_OUTSIDE_S,
    MANDATORY_STD_RAD,
    MODE_AHRS,
    MODE_ARS,
    REF_BIAS_DPS,
    REF_BIAS_LIM_DPS,
    REF_DURATION_S,
    REF_INIT_ERR_DEG,
    REF_RP_LIM_DEG,
    AttCmd,
    AttScenario,
    SuiteScenario,
    ahrs_std,
    ars_std,
    att_hold,
    att_pos,
    bias_corrected_z_integral,
    c_att_run,
    c_leveling,
    c_mag_heading,
    heading_ignoring_tilt,
    c_suite_run,
    longitude_same_latitude_without_declination,
    mag_zrate_hold,
    ned_horiz_rotate_scale,
    py_mag_heading,
    py_suite_run,
    reference_stream,
    require_att,
    require_bias,
    require_snap_at,
    runtime_att_yaw_rad,
    suite_known_heading_scenarios,
    runtime_declination_site,
    runtime_noise_seeds,
    runtime_site,
    runtime_tilt_rad,
    runtime_z_rate_rps,
    suite_ars_as_att,
    suite_imu_stream,
    yaw_separations,
)

# Independent WGS84 sidereal rate. Used only to size an Earth-rate-removed
# yaw prediction so "Earth rate is not corrected" is distinguishable from a
# free z-rate integral. Not a product pin and not a frozen 15 °/h golden.
_WGS84_OMEGA_RPS = 7.2921151467e-5


# Cases that are not the zero-attitude acceptance use a finite roll.
# Exact (0, 0, 0) is a legal initial attitude; a refusal of that one
# value must show up on the acceptance case, not as an init outage of
# every other case. Yaw stays 0 so a z-rate integral still starts there.
_CASE_ROLL_RAD = 1.0e-4


# The precision-restart watchdog (accessors fail once a reported attitude
# 1-sigma exceeds its threshold after the warm-up) is scored only in
# test_suite_rebootstrap_after_uninitialized, against the reported 1-sigma
# and the documented thresholds. Every other standalone scenario here turns
# it off through the public ahrs_config_t switch: a long stretch without a
# correcting sensor (no magnetometer, skipped heading fusion) grows the
# reported 1-sigma at a rate set by default noise tuning the contract leaves
# to the implementer, and that growth is not what those scenarios score.


def _ahrs(rpy=(_CASE_ROLL_RAD, 0.0, 0.0), cmds=None, std=None, **kwargs) -> AttScenario:
    kwargs.setdefault("restart_disable", True)
    return AttScenario(
        mode=MODE_AHRS,
        rpy=rpy,
        std=ahrs_std() if std is None else std,
        cmds=list(cmds or []),
        **kwargs,
    )


def _ars(rpy=(_CASE_ROLL_RAD, 0.0, 0.0), cmds=None, std=None, **kwargs) -> AttScenario:
    kwargs.setdefault("restart_disable", True)
    return AttScenario(
        mode=MODE_ARS,
        rpy=rpy,
        std=ars_std() if std is None else std,
        cmds=list(cmds or []),
        **kwargs,
    )


def _assert_init_ok(run, what):
    """Init succeeded.

    A run that never reaches a measurement epoch is graded only as success
    versus failure. Attitude accessors before the first epoch are not part
    of that grade. Once an epoch has run, the last snapshot is that epoch.
    """
    assert run.init_ok, f"{what}: init was refused"
    measured = [s for s in run.snaps if s.t_us > 0]
    if not measured:
        return
    snap = run.last()
    assert snap.rpy_ok, f"{what}: attitude accessors failed after a successful init"
    assert snap.att is not None, f"{what}: published attitude missing"


def _assert_init_refused(run, what):
    # Init itself does not succeed. A refusal does not have to publish a
    # snapshot, and accessor state after a refused init is the later
    # implausibly-large 1-sigma path, not this refusal.
    assert not run.init_ok, f"{what}: init succeeded"


def _unwrapped_yaw(snaps, what):
    """Accumulate published yaw in unwrapped counts (not a single wrap)."""
    total = None
    last = None
    n = 0
    for snap in snaps:
        if not snap.rpy_ok or snap.att is None:
            continue
        y = snap.att[2]
        if last is None:
            total = y
        else:
            total += angle_diff_rad(y, last)
        last = y
        n += 1
    assert n >= 2, f"{what}: need at least two published yaws to unwrap"
    return total


def _score_against_bias_corrected(yaw_unwrapped, corrected, earth, what):
    """Score unwrapped yaw on this run's bias-corrected integral.

    PRD: yaw is the integral of the bias-corrected z-rate and Earth
    rate is not corrected. The bias-corrected integral must fit the
    published yaw strictly better than the same integral shifted by the
    Earth-rate effect in either direction, i.e. the residual stays inside
    half the Earth-rate effect. That comparison is unconditional: a
    residual as large as the Earth-rate effect (Earth rate applied, or a
    yaw that is not this run's bias-corrected integral) fails instead of
    skipping the comparison.
    """
    assert earth > 0.0, f"{what}: Earth-rate effect is not positive"
    err = abs(yaw_unwrapped - corrected)
    err_minus = abs(yaw_unwrapped - (corrected - earth))
    err_plus = abs(yaw_unwrapped - (corrected + earth))
    print(
        f"{what}: unwrapped={math.degrees(yaw_unwrapped)} "
        f"corrected={math.degrees(corrected)} earth={math.degrees(earth)} "
        f"err={math.degrees(err)} err_minus={math.degrees(err_minus)} "
        f"err_plus={math.degrees(err_plus)} deg "
        f"margin={math.degrees(0.5 * earth - err)} deg",
        flush=True,
    )
    assert err < err_minus, (
        f"{what}: published yaw is not nearer the bias-corrected z-rate "
        "integral than an Earth-rate-subtracted integral"
    )
    assert err < err_plus, (
        f"{what}: published yaw is not nearer the bias-corrected z-rate "
        "integral than an Earth-rate-added integral"
    )
    return err


def _duration_wrapped_away_from_zero(omega, *, min_s=110.0):
    """Long enough that Earth-rate is distinguishable; wrapped free ≠ 0."""
    target_wrap = 0.5 * math.pi
    k = 0
    duration_s = (2.0 * math.pi * k + target_wrap) / abs(omega)
    while duration_s < min_s:
        k += 1
        duration_s = (2.0 * math.pi * k + target_wrap) / abs(omega)
    return duration_s


# ---------------------------------------------------------------------------
# A. ARS vs AHRS
# ---------------------------------------------------------------------------


def test_ars_constant_z_rate_integrates_yaw():
    """constant z-rate integrates as this run's bias-corrected integral.

    Roll and pitch are corrected from the accelerometer against gravity.
    No fraction of the raw rate-times-time and no fixed level band.
    """
    duration_s = 4.0
    acc_level = SPECIFIC_FORCE_LEVEL
    tilt = runtime_tilt_rad()
    acc_tilt = still_level_acc(0.0, tilt)
    for omega in (runtime_z_rate_rps(), runtime_z_rate_rps()):
        gyr = (0.0, 0.0, omega)
        level = c_att_run(
            _ars(cmds=att_hold(t0_us=0, duration_s=duration_s, acc=acc_level, gyr=gyr))
        )
        tilted = c_att_run(
            _ars(cmds=att_hold(t0_us=0, duration_s=duration_s, acc=acc_tilt, gyr=gyr))
        )
        _assert_init_ok(level, "ARS z-rate")
        _assert_init_ok(tilted, "ARS z-rate tilted twin")
        roll, pitch, _yaw = require_att(level.last(), "ARS z-rate")
        tr, tp, _ty = require_att(tilted.last(), "ARS z-rate tilted twin")
        level_off = math.hypot(roll, pitch)
        tilt_off = math.hypot(tr, tp)
        corrected = bias_corrected_z_integral(level.snaps, omega)
        yaw_unwrapped = _unwrapped_yaw(level.snaps, "ARS z-rate")
        err = abs(yaw_unwrapped - corrected)
        print(
            f"ARS z-rate: roll={math.degrees(roll)} pitch={math.degrees(pitch)} "
            f"tilt_roll={math.degrees(tr)} tilt_pitch={math.degrees(tp)} "
            f"level_off={math.degrees(level_off)} tilt_off={math.degrees(tilt_off)} "
            f"unwrapped={math.degrees(yaw_unwrapped)} "
            f"corrected={math.degrees(corrected)} err={math.degrees(err)} deg",
            flush=True,
        )
        # nearer level than the same z-rate on a tilted specific force.
        assert level_off < tilt_off, (
            "level specific force did not leave roll and pitch nearer level "
            "than the tilted twin"
        )
        # nearer this run's bias-corrected integral than a heading
        # that did not integrate. Not a fraction of the raw rate-times-time.
        assert abs(corrected) > 0.0, (
            "bias-corrected z-rate integral is not distinguishable from a heading that did not integrate"
        )
        assert err < abs(corrected), (
            "published yaw is nearer a heading that did not integrate "
            "than this run's bias-corrected z-rate integral"
        )
        # Absent magnetometer: the epoch still ran (the integral above),
        # and the invalid-input counter did not grow from initialization.
        n0 = level.snaps[0].n_invalid
        n1 = level.last().n_invalid
        print(f"ARS z-rate: n_invalid init={n0} after={n1}", flush=True)
        assert n1 <= n0, (
            "ARS z-rate: invalid-input counter grew across the "
            f"absent-magnetometer stretch ({n0} -> {n1})"
        )


def test_ars_earth_rate_is_not_corrected():
    """ARS yaw is the integral of the bias-corrected z-rate; Earth rate is not corrected.

    Roll and pitch are corrected from the accelerometer against gravity.
    No frozen level band: the level arm only has to sit nearer level than
    the same run on a tilted specific force.
    """
    acc = SPECIFIC_FORCE_LEVEL
    omega = runtime_z_rate_rps()
    # Wrapped free heading must sit away from 0. A 120 s run at ~9 °/s wraps
    # to 0° (1080°), so a constant-zero yaw looks like the free integral
    # through wrapped angle_diff. Compare in unwrapped counts instead.
    duration_s = _duration_wrapped_away_from_zero(omega)
    gyr = (0.0, 0.0, omega)
    tilt = runtime_tilt_rad()
    acc_tilt = still_level_acc(0.0, tilt)
    run = c_att_run(
        _ars(cmds=att_hold(t0_us=0, duration_s=duration_s, acc=acc, gyr=gyr))
    )
    tilted = c_att_run(
        _ars(cmds=att_hold(t0_us=0, duration_s=duration_s, acc=acc_tilt, gyr=gyr))
    )
    _assert_init_ok(run, "ARS Earth-rate")
    _assert_init_ok(tilted, "ARS Earth-rate tilted twin")
    roll, pitch, yaw = require_att(run.last(), "ARS Earth-rate")
    tr, tp, _ty = require_att(tilted.last(), "ARS Earth-rate tilted twin")
    level_off = math.hypot(roll, pitch)
    tilt_off = math.hypot(tr, tp)
    dt_s = run.last().t_us / 1e6
    free = omega * dt_s
    corrected = bias_corrected_z_integral(run.snaps, omega)
    earth = _WGS84_OMEGA_RPS * dt_s
    wrapped_free = angle_diff_rad(free, 0.0)
    yaw_unwrapped = _unwrapped_yaw(run.snaps, "ARS Earth-rate")
    print(
        f"ARS Earth-rate: roll={math.degrees(roll)} pitch={math.degrees(pitch)} "
        f"tilt_roll={math.degrees(tr)} tilt_pitch={math.degrees(tp)} "
        f"level_off={math.degrees(level_off)} tilt_off={math.degrees(tilt_off)} "
        f"last={math.degrees(yaw)} unwrapped={math.degrees(yaw_unwrapped)} "
        f"free={math.degrees(free)} corrected={math.degrees(corrected)} "
        f"wrapped_free={math.degrees(wrapped_free)} earth={math.degrees(earth)} deg",
        flush=True,
    )
    # nearer level than the same z-rate on a tilted specific force.
    # No frozen degree band.
    assert level_off < tilt_off, (
        "level specific force did not leave roll and pitch nearer level "
        "than the tilted twin"
    )
    assert earth > math.radians(0.4), (
        "Earth-rate-removed prediction is not distinguishable from the free integral"
    )
    # Hold the wrapped free heading away from 0. A wrap-to-zero free integral
    # (e.g. 9 °/s × 120 s = 1080°) makes identity yaw look like the free
    # prediction through wrapped angle_diff.
    assert abs(wrapped_free) > math.radians(40.0), (
        "wrapped free heading is not distinguishable from 0"
    )
    # Score this run's bias-corrected integral: it must fit strictly better
    # than the same integral shifted by the Earth-rate effect either way.
    # No fixed angle and no fraction of the integral.
    _score_against_bias_corrected(
        yaw_unwrapped, corrected, earth, "ARS Earth-rate"
    )
    n0 = run.snaps[0].n_invalid
    n1 = run.last().n_invalid
    print(f"ARS Earth-rate: n_invalid init={n0} after={n1}", flush=True)
    assert n1 <= n0, (
        "ARS Earth-rate: invalid-input counter grew across the "
        f"absent-magnetometer stretch ({n0} -> {n1})"
    )


def test_ars_ignores_magnetometer_when_present():
    """roll and pitch come from the accelerometer against gravity.

    The sentence names no degree band. The with-magnetometer arm only has
    to finish nearer level than the same z-rate on a tilted specific force.
    Yaw is the integral of the bias-corrected z-rate and is never
    measurement-corrected. The no-magnetometer arm is scored on this run's
    bias-corrected integral, not a fraction of the raw rate times time.
    The same non-correction is a suite epoch: the unaided arm pushes no
    magnetometer. The Python navigator scores that yaw. The C suite probe
    scores the same unaided yaw and the ARS instance's invalid-input
    counter. The with-magnetometer yaw stays nearer the unaided yaw than
    the magnetometer heading.
    """
    omega = runtime_z_rate_rps()
    duration_s = 4.0
    acc = SPECIFIC_FORCE_LEVEL
    mag_yaw = runtime_att_yaw_rad()
    integrated_guess = omega * duration_s
    # Offset mag heading from the free integral, not from 0. Mag-from-zero
    # is the wrong "not pulled" scale once yaw has integrated.
    if abs(angle_diff_rad(mag_yaw, integrated_guess)) < math.radians(50.0):
        mag_yaw = integrated_guess + math.radians(70.0)
    mag = body_mag_for_yaw(0.0, 0.0, mag_yaw, (20.0, 0.0, 44.0))
    gyr = (0.0, 0.0, omega)
    tilt = runtime_tilt_rad()
    acc_tilt = still_level_acc(0.0, tilt)
    none = c_att_run(
        _ars(cmds=att_hold(t0_us=0, duration_s=duration_s, acc=acc, gyr=gyr))
    )
    with_mag = c_att_run(
        _ars(
            cmds=att_hold(
                t0_us=0, duration_s=duration_s, acc=acc, gyr=gyr, mag=mag
            )
        )
    )
    tilted = c_att_run(
        _ars(
            cmds=att_hold(
                t0_us=0, duration_s=duration_s, acc=acc_tilt, gyr=gyr, mag=mag
            )
        )
    )
    _assert_init_ok(none, "ARS no-mag")
    _assert_init_ok(with_mag, "ARS with-mag")
    _assert_init_ok(tilted, "ARS with-mag tilted twin")
    y0 = require_att(none.last(), "ARS no-mag")[2]
    y1 = require_att(with_mag.last(), "ARS with-mag")[2]
    roll, pitch, _ = require_att(with_mag.last(), "ARS with-mag")
    tr, tp, _ty = require_att(tilted.last(), "ARS with-mag tilted twin")
    level_off = math.hypot(roll, pitch)
    tilt_off = math.hypot(tr, tp)
    print(
        f"ARS with-mag level: roll={math.degrees(roll)} pitch={math.degrees(pitch)} "
        f"tilt_roll={math.degrees(tr)} tilt_pitch={math.degrees(tp)} "
        f"level_off={math.degrees(level_off)} tilt_off={math.degrees(tilt_off)} deg",
        flush=True,
    )
    # nearer level than the same z-rate on a tilted specific force.
    # No frozen degree band.
    assert level_off < tilt_off, (
        "with-magnetometer level specific force did not leave roll and pitch "
        "nearer level than the tilted twin"
    )
    # the no-magnetometer arm is this run's bias-corrected z-rate
    # integral. A fraction of the raw rate times time, or of an angular
    # floor, is not that integral.
    corrected = bias_corrected_z_integral(none.snaps, omega)
    unwrapped = _unwrapped_yaw(none.snaps, "ARS no-mag")
    err = abs(unwrapped - corrected)
    print(
        f"ARS no-mag: unwrapped={math.degrees(unwrapped)} "
        f"corrected={math.degrees(corrected)} err={math.degrees(err)} deg",
        flush=True,
    )
    assert abs(corrected) > 0.0, (
        "ARS no-mag: bias-corrected z-rate integral is not distinguishable "
        "from a heading that did not integrate"
    )
    assert err < abs(corrected), (
        "ARS no-mag: published yaw is nearer a heading that did not integrate "
        "than this run's bias-corrected z-rate integral"
    )
    n0 = none.snaps[0].n_invalid
    n1 = none.last().n_invalid
    print(f"ARS no-mag: n_invalid init={n0} after={n1}", flush=True)
    assert n1 <= n0, (
        "ARS no-mag: invalid-input counter grew across the "
        f"absent-magnetometer stretch ({n0} -> {n1})"
    )
    between, to_mag = yaw_separations(y1, y0, mag_yaw)
    gap = abs(angle_diff_rad(y0, mag_yaw))
    print(
        f"ARS mag-ignore: y0={math.degrees(y0)} y1={math.degrees(y1)} "
        f"mag={math.degrees(mag_yaw)} between={math.degrees(between)} "
        f"to_mag={math.degrees(to_mag)} gap={math.degrees(gap)} deg",
        flush=True,
    )
    assert gap > math.radians(40.0), (
        "magnetometer heading is not distinguishable from the free-integral yaw"
    )
    # Never measurement-corrected: the mag arm stays nearer the no-mag twin
    # than the magnetometer heading. No fraction of the integral or the gap.
    assert between < to_mag, (
        "ARS with a magnetometer is nearer the magnetometer heading than the no-mag twin"
    )
    # PRD on the suite path: the navigator pushes this magnetometer, then
    # the published suite ARS yaw is read. The unaided twin never pushes one.
    # A navigator with no magnetometer push cannot run the aided epoch.
    lat, lon, h = runtime_site()
    plain = suite_imu_stream(duration_s=duration_s, acc=acc, gyr=gyr)
    aided = suite_imu_stream(duration_s=duration_s, acc=acc, gyr=gyr, mag=mag)
    bare = py_suite_run(SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=plain))
    pushed = py_suite_run(SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=aided))
    assert bare.init_ok and pushed.init_ok, "Python suite init failed"
    y_bare = bare.last().ars_att
    y_pushed = pushed.last().ars_att
    assert y_bare is not None and y_pushed is not None, (
        "Python: suite ARS did not publish"
    )
    bare_views = suite_ars_as_att(bare.snaps, "Python ARS no magnetometer")
    suite_corrected = bias_corrected_z_integral(bare_views, omega)
    suite_unwrapped = _unwrapped_yaw(bare_views, "Python ARS no magnetometer")
    suite_err = abs(suite_unwrapped - suite_corrected)
    print(
        f"Python ARS no magnetometer: unwrapped={math.degrees(suite_unwrapped)} "
        f"corrected={math.degrees(suite_corrected)} err={math.degrees(suite_err)} deg",
        flush=True,
    )
    assert abs(suite_corrected) > 0.0, (
        "Python ARS no magnetometer: bias-corrected z-rate integral is not "
        "distinguishable from a heading that did not integrate"
    )
    assert suite_err < abs(suite_corrected), (
        "Python ARS no magnetometer: published yaw is nearer a heading that "
        "did not integrate than this run's bias-corrected z-rate integral"
    )
    # The Python navigator does not publish the attitude filter's
    # invalid-input counter. The unaided epoch is read again on the C
    # suite probe, which prints the ARS instance's own counter.
    c_bare = c_suite_run(
        SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=plain)
    )
    assert c_bare.init_ok, "C suite init failed"
    assert c_bare.last().ars_att is not None, "C: suite ARS did not publish"
    c_views = suite_ars_as_att(c_bare.snaps, "C ARS no magnetometer")
    c_corrected = bias_corrected_z_integral(c_views, omega)
    c_unwrapped = _unwrapped_yaw(c_views, "C ARS no magnetometer")
    c_err = abs(c_unwrapped - c_corrected)
    print(
        f"C ARS no magnetometer: unwrapped={math.degrees(c_unwrapped)} "
        f"corrected={math.degrees(c_corrected)} err={math.degrees(c_err)} deg",
        flush=True,
    )
    assert abs(c_corrected) > 0.0, (
        "C ARS no magnetometer: bias-corrected z-rate integral is not "
        "distinguishable from a heading that did not integrate"
    )
    assert c_err < abs(c_corrected), (
        "C ARS no magnetometer: published yaw is nearer a heading that "
        "did not integrate than this run's bias-corrected z-rate integral"
    )
    c_n0 = c_bare.snaps[0].ars_n_invalid
    c_n1 = c_bare.last().ars_n_invalid
    assert c_n0 is not None and c_n1 is not None, (
        "C ARS no magnetometer: suite snapshot did not carry the ARS "
        "invalid-input counter"
    )
    print(
        f"C ARS no magnetometer: ars_n_invalid init={c_n0} after={c_n1}",
        flush=True,
    )
    assert c_n1 <= c_n0, (
        "C ARS no magnetometer: invalid-input counter grew across the "
        f"absent-magnetometer stretch ({c_n0} -> {c_n1})"
    )
    suite_between, suite_to_mag = yaw_separations(y_pushed[2], y_bare[2], mag_yaw)
    suite_gap = abs(angle_diff_rad(y_bare[2], mag_yaw))
    print(
        f"Python suite mag-ignore: y0={math.degrees(y_bare[2])} "
        f"y1={math.degrees(y_pushed[2])} mag={math.degrees(mag_yaw)} "
        f"between={math.degrees(suite_between)} "
        f"to_mag={math.degrees(suite_to_mag)} gap={math.degrees(suite_gap)} deg",
        flush=True,
    )
    assert suite_gap > math.radians(40.0), (
        "Python: magnetometer heading is not distinguishable from the "
        "unaided suite ARS yaw"
    )
    assert suite_between < suite_to_mag, (
        "Python: suite ARS yaw with a magnetometer is nearer the magnetometer "
        "heading than the no-magnetometer twin"
    )


def test_ars_yaw_integral_removes_estimated_z_bias():
    """the z-rate that is integrated has the estimated z-axis gyro bias removed."""
    omega = runtime_z_rate_rps()
    acc = SPECIFIC_FORCE_LEVEL
    learn_s = 4.0
    coast_s = 2.0
    learn = att_hold(
        t0_us=0, duration_s=learn_s, acc=acc, gyr=(0.0, 0.0, omega), zaru=True
    )
    coast = att_hold(
        t0_us=learn[-1].t_us,
        duration_s=coast_s,
        acc=acc,
        gyr=(0.0, 0.0, omega),
        zaru=False,
    )
    run = c_att_run(_ars(cmds=[*learn, *coast]))
    _assert_init_ok(run, "bias-corrected integral")
    at_learn = [s for s in run.snaps if s.t_us == learn[-1].t_us]
    assert at_learn, "bias-corrected integral: missing coast boundary"
    y0 = require_att(at_learn[0], "after bias learn")[2]
    bz = require_bias(at_learn[0], "after bias learn")[2]
    y1 = require_att(run.last(), "after coast")[2]
    dt = (run.last().t_us - learn[-1].t_us) / 1e6
    dy = angle_diff_rad(y1, y0)
    corrected = (omega - bz) * dt
    raw = omega * dt
    print(
        f"bias integral: bz={math.degrees(bz)} omega={math.degrees(omega)} "
        f"dy={math.degrees(dy)} corrected={math.degrees(corrected)} "
        f"raw={math.degrees(raw)} deg",
        flush=True,
    )
    # the coast is the integral of (z-rate minus the published z-bias).
    # Nearer that integral than the raw z-rate integral. The bias need not
    # have crossed the midpoint, and the residual is not a fixed angle or
    # a fraction of the separation.
    to_corrected, to_raw = yaw_separations(dy, corrected, raw)
    print(
        f"bias integral to_corrected={math.degrees(to_corrected)} "
        f"to_raw={math.degrees(to_raw)} deg",
        flush=True,
    )
    assert to_corrected < to_raw, (
        "coast yaw change is nearer the raw z-rate integral than "
        "(z-rate minus the published z-bias) times the coast length"
    )
    n0 = run.snaps[0].n_invalid
    n1 = run.last().n_invalid
    print(
        f"bias-corrected coast: n_invalid init={n0} after={n1}",
        flush=True,
    )
    assert n1 <= n0, (
        "bias-corrected coast: invalid-input counter grew across the "
        f"absent-magnetometer stretch ({n0} -> {n1})"
    )
    twin = c_att_run(
        _ars(
            cmds=att_hold(
                t0_us=0,
                duration_s=learn_s + coast_s,
                acc=acc,
                gyr=(0.0, 0.0, omega),
            )
        )
    )
    _assert_init_ok(twin, "no-flag twin")
    # gyro bias is estimated online even when the zero-rotation flag
    # is not raised. Score this twin on its own bias-corrected integral.
    # A frozen fraction of the raw rate-times-time is not that integral.
    twin_corrected = bias_corrected_z_integral(twin.snaps, omega)
    twin_unwrapped = _unwrapped_yaw(twin.snaps, "no-flag twin")
    twin_err = abs(twin_unwrapped - twin_corrected)
    print(
        f"no-flag twin: unwrapped={math.degrees(twin_unwrapped)} "
        f"corrected={math.degrees(twin_corrected)} err={math.degrees(twin_err)} deg",
        flush=True,
    )
    assert abs(twin_corrected) > 0.0, (
        "no-flag twin: bias-corrected z-rate integral is not distinguishable "
        "from a heading that did not integrate"
    )
    assert twin_err < abs(twin_corrected), (
        "no-flag twin: published yaw is nearer a heading that did not integrate "
        "than this run's bias-corrected z-rate integral"
    )
    twin_n0 = twin.snaps[0].n_invalid
    twin_n1 = twin.last().n_invalid
    print(
        f"no-flag twin: n_invalid init={twin_n0} after={twin_n1}",
        flush=True,
    )
    assert twin_n1 <= twin_n0, (
        "no-flag twin: invalid-input counter grew across the "
        f"absent-magnetometer stretch ({twin_n0} -> {twin_n1})"
    )


def test_ahrs_estimates_gyro_bias_online():
    """AHRS estimates gyro bias online the same way ARS does."""
    bx = runtime_z_rate_rps() * 0.08
    yaw_ref = runtime_att_yaw_rad()
    acc = SPECIFIC_FORCE_LEVEL
    mag = body_mag_for_yaw(0.0, 0.0, yaw_ref, (21.0, 0.0, 40.0))
    duration_s = 10.0
    biased = c_att_run(
        _ahrs(
            cmds=att_hold(
                t0_us=0,
                duration_s=duration_s,
                acc=acc,
                gyr=(bx, 0.0, 0.0),
                mag=mag,
            )
        )
    )
    still = c_att_run(
        _ahrs(
            cmds=att_hold(
                t0_us=0,
                duration_s=duration_s,
                acc=acc,
                gyr=(0.0, 0.0, 0.0),
                mag=mag,
            )
        )
    )
    _assert_init_ok(biased, "AHRS online bias")
    _assert_init_ok(still, "AHRS zero-gyro twin")
    est = require_bias(biased.last(), "AHRS online bias")[0]
    est_still = require_bias(still.last(), "AHRS zero-gyro twin")[0]
    print(
        f"AHRS bias: est={math.degrees(est)} still={math.degrees(est_still)} "
        f"truth={math.degrees(bx)} deg/s",
        flush=True,
    )
    # estimated online. The zero-gyro twin is the contrast.
    # Nearer the injected rate than that twin is enough; crossing the
    # midpoint between zero and the injected rate is not required.
    assert abs(est - bx) < abs(est_still - bx), (
        "AHRS x-bias on a biased gyro was not closer to the truth than the zero-gyro twin"
    )


def test_ahrs_earth_rate_is_not_corrected():
    """AHRS does not correct Earth rate. Same contrast as ARS, no magnetometer.

    Roll and pitch are corrected from the accelerometer against gravity.
    No frozen level band: the level arm only has to sit nearer level than
    the same run on a tilted specific force.
    """
    acc = SPECIFIC_FORCE_LEVEL
    omega = runtime_z_rate_rps()
    # Long enough for the Earth-rate adjustment to exceed integration residual.
    # The yaw-variance restart watchdog is not the subject of this arm (_ahrs
    # switches it off), so an unaided yaw 1-sigma cannot end the run early.
    duration_s = 36.0
    gyr = (0.0, 0.0, omega)
    tilt = runtime_tilt_rad()
    acc_tilt = still_level_acc(0.0, tilt)
    run = c_att_run(
        _ahrs(cmds=att_hold(t0_us=0, duration_s=duration_s, acc=acc, gyr=gyr))
    )
    tilted = c_att_run(
        _ahrs(cmds=att_hold(t0_us=0, duration_s=duration_s, acc=acc_tilt, gyr=gyr))
    )
    _assert_init_ok(run, "AHRS Earth-rate")
    _assert_init_ok(tilted, "AHRS Earth-rate tilted twin")
    roll, pitch, yaw = require_att(run.last(), "AHRS Earth-rate")
    tr, tp, _ty = require_att(tilted.last(), "AHRS Earth-rate tilted twin")
    level_off = math.hypot(roll, pitch)
    tilt_off = math.hypot(tr, tp)
    dt_s = run.last().t_us / 1e6
    corrected = bias_corrected_z_integral(run.snaps, omega)
    earth = _WGS84_OMEGA_RPS * dt_s
    yaw_unwrapped = _unwrapped_yaw(run.snaps, "AHRS Earth-rate")
    print(
        f"AHRS Earth-rate: roll={math.degrees(roll)} pitch={math.degrees(pitch)} "
        f"tilt_roll={math.degrees(tr)} tilt_pitch={math.degrees(tp)} "
        f"level_off={math.degrees(level_off)} tilt_off={math.degrees(tilt_off)} "
        f"last={math.degrees(yaw)} "
        f"corrected={math.degrees(corrected)} earth={math.degrees(earth)} deg",
        flush=True,
    )
    # nearer level than the same z-rate on a tilted specific force.
    # No frozen degree band.
    assert level_off < tilt_off, (
        "level specific force did not leave roll and pitch nearer level "
        "than the tilted twin"
    )
    assert earth > math.radians(0.05), (
        "Earth-rate adjustment is not distinguishable from zero on this run"
    )
    # Same unconditional comparison as the ARS arm: the bias-corrected
    # integral fits strictly better than an Earth-rate-shifted one.
    _score_against_bias_corrected(
        yaw_unwrapped, corrected, earth, "AHRS Earth-rate"
    )


def test_ars_gnss_measurement_does_not_correct_yaw():
    """a GNSS measurement on the ARS instance does not correct published yaw."""
    omega = runtime_z_rate_rps()
    duration_s = 4.0
    acc = SPECIFIC_FORCE_LEVEL
    integrated = omega * duration_s
    course = runtime_att_yaw_rad()
    if abs(angle_diff_rad(course, integrated)) < math.radians(50.0):
        course = integrated + math.radians(70.0)
    speed = 8.0
    vel = (speed * math.cos(course), speed * math.sin(course), 0.0)
    gyr = (0.0, 0.0, omega)
    lat, lon, h = runtime_site()
    plain = suite_imu_stream(duration_s=duration_s, acc=acc, gyr=gyr)
    aided = suite_imu_stream(duration_s=duration_s, acc=acc, gyr=gyr, gnss_vel=vel)
    for kind, runner in (("C", c_suite_run), ("Python", py_suite_run)):
        bare = runner(SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=plain))
        gnss = runner(SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=aided))
        assert bare.init_ok and gnss.init_ok, f"{kind} suite init failed"
        y0 = bare.last().ars_att
        y1 = gnss.last().ars_att
        assert y0 is not None and y1 is not None, f"{kind}: suite ARS did not publish"
        # the no-GNSS arm is this run's bias-corrected z-rate integral.
        # A fraction of the raw rate times time, or of an angular floor, is not.
        bare_views = suite_ars_as_att(bare.snaps, f"{kind} ARS no GNSS")
        corrected = bias_corrected_z_integral(bare_views, omega)
        unwrapped = _unwrapped_yaw(bare_views, f"{kind} ARS no GNSS")
        err = abs(unwrapped - corrected)
        print(
            f"{kind} ARS no GNSS: unwrapped={math.degrees(unwrapped)} "
            f"corrected={math.degrees(corrected)} err={math.degrees(err)} deg",
            flush=True,
        )
        assert abs(corrected) > 0.0, (
            f"{kind} ARS no GNSS: bias-corrected z-rate integral is not "
            "distinguishable from a heading that did not integrate"
        )
        assert err < abs(corrected), (
            f"{kind} ARS no GNSS: published yaw is nearer a heading that did "
            "not integrate than this run's bias-corrected z-rate integral"
        )
        between, to_course = yaw_separations(y1[2], y0[2], course)
        gap = abs(angle_diff_rad(y0[2], course))
        print(
            f"{kind} GNSS-ignore: y0={math.degrees(y0[2])} y1={math.degrees(y1[2])} "
            f"course={math.degrees(course)} between={math.degrees(between)} "
            f"to_course={math.degrees(to_course)} gap={math.degrees(gap)} deg",
            flush=True,
        )
        assert gap > math.radians(40.0), (
            f"{kind}: GNSS course is not distinguishable from the no-GNSS twin"
        )
        # No GNSS correction: the aided arm stays nearer the bare twin than
        # the course. No fraction of the integral or the gap.
        assert between < to_course, (
            f"{kind}: ARS yaw with GNSS is nearer the GNSS course than the no-GNSS twin"
        )


def test_ahrs_persistent_heading_error_pulled_to_mag():
    yaw_ref = runtime_att_yaw_rad()
    acc = still_level_acc(0.0, 0.0)
    mag = body_mag_for_yaw(0.0, 0.0, yaw_ref, (22.0, 0.0, 40.0))
    duration_s = 12.0
    cmds = att_hold(
        t0_us=0, duration_s=duration_s, acc=acc, gyr=(0.0, 0.0, 0.0), mag=mag
    )
    ahrs = c_att_run(_ahrs(cmds=cmds))
    ars = c_att_run(_ars(cmds=cmds))
    _assert_init_ok(ahrs, "AHRS mag pull")
    _assert_init_ok(ars, "ARS mag twin")
    y_ahrs = require_att(ahrs.last(), "AHRS mag pull")[2]
    y_ars = require_att(ars.last(), "ARS mag twin")[2]
    err_ahrs = abs(angle_diff_rad(y_ahrs, yaw_ref))
    err_ars = abs(angle_diff_rad(y_ars, yaw_ref))
    err0 = abs(angle_diff_rad(0.0, yaw_ref))
    print(
        f"AHRS pull: y={math.degrees(y_ahrs)} ars={math.degrees(y_ars)} "
        f"ref={math.degrees(yaw_ref)} err_ahrs={math.degrees(err_ahrs)} "
        f"err_ars={math.degrees(err_ars)} deg",
        flush=True,
    )
    # pulled toward the magnetic reference means strictly nearer
    # that heading than the ARS twin. No degree window is frozen.
    assert err_ahrs < err_ars, (
        "AHRS yaw was not nearer that magnetometer heading than the ARS twin"
    )


def _epoch_at(cmds, t_s, what):
    target = int(round(t_s * 1e6))
    chosen = None
    for cmd in cmds:
        if cmd.tag == "E" and cmd.t_us >= target:
            chosen = cmd
            break
    assert chosen is not None, f"{what}: no epoch at or after {t_s} s"
    return chosen


def _yaw_at(run, t_us, what):
    hits = [s for s in run.snaps if s.t_us == t_us and s.rpy_ok and s.att is not None]
    assert len(hits) == 1, f"{what}: expected one published attitude at {t_us}, saw {len(hits)}"
    return hits[0].att[2]


def test_ars_yaw_drifts_with_residual_z_bias():
    """ARS yaw moves with a residual z-bias; AHRS is pulled to the mag heading.

    The drift rate is not scored. A heading that stays put fails. The
    size of that move is not compared to the heading error AHRS still
    has. An ARS yaw that is not farther from the magnetometer heading
    than AHRS fails.
    """
    mag_yaw = runtime_att_yaw_rad()
    omega = -abs(runtime_z_rate_rps()) * 0.15
    duration_s = 16.0
    cmds = mag_zrate_hold(duration_s=duration_s, omega_z=omega, mag_yaw=mag_yaw)
    ars = c_att_run(_ars(cmds=cmds))
    ahrs = c_att_run(_ahrs(cmds=cmds))
    _assert_init_ok(ars, "ARS residual z-bias")
    _assert_init_ok(ahrs, "AHRS residual z-bias")
    y0 = require_att(ars.snaps[0], "ARS residual open")[2]
    y_ars = require_att(ars.last(), "ARS residual end")[2]
    y_ahrs = require_att(ahrs.last(), "AHRS residual end")[2]
    moved = abs(angle_diff_rad(y_ars, y0))
    ahrs_miss = abs(angle_diff_rad(y_ahrs, mag_yaw))
    ars_miss = abs(angle_diff_rad(y_ars, mag_yaw))
    print(
        f"residual z-bias: ars0={math.degrees(y0)} ars={math.degrees(y_ars)} "
        f"ahrs={math.degrees(y_ahrs)} mag={math.degrees(mag_yaw)} "
        f"moved={math.degrees(moved)} ahrs_miss={math.degrees(ahrs_miss)} "
        f"ars_miss={math.degrees(ars_miss)}",
        flush=True,
    )
    # residual z-bias can stay small because the bias is
    # estimated online. The move only has to be a move. It does not have
    # to exceed the heading error AHRS still has.
    assert moved > 0.0, (
        "ARS yaw held a fixed heading instead of moving with the residual z-bias"
    )
    # Pulled to the magnetometer reference means strictly nearer that
    # heading than the drifting ARS twin.
    assert ars_miss > ahrs_miss, (
        "AHRS yaw was not nearer the magnetometer heading than ARS"
    )


def test_modes_stay_distinct_across_epochs():
    """mode is fixed per instance.

    The same magnetometer sample pulls AHRS yaw toward that heading and
    does not measurement-correct ARS. At each epoch AHRS is strictly
    nearer that heading than ARS. No degree band is frozen: the integral
    may pass nearer the heading, and AHRS need not already sit inside a
    fixed window of it.
    """
    mag_yaw = runtime_att_yaw_rad()
    omega = -abs(runtime_z_rate_rps()) * 0.15
    duration_s = 18.0
    cmds = mag_zrate_hold(duration_s=duration_s, omega_z=omega, mag_yaw=mag_yaw)
    early = _epoch_at(cmds, 12.0, "mode split")
    late = _epoch_at(cmds, duration_s, "mode split")
    ars = c_att_run(_ars(cmds=cmds))
    ahrs = c_att_run(_ahrs(cmds=cmds))
    _assert_init_ok(ars, "ARS mode fixed")
    _assert_init_ok(ahrs, "AHRS mode fixed")
    for label, t_us in (("early", early.t_us), ("late", late.t_us)):
        y_ars = _yaw_at(ars, t_us, f"ARS {label}")
        y_ahrs = _yaw_at(ahrs, t_us, f"AHRS {label}")
        dist_ars = abs(angle_diff_rad(y_ars, mag_yaw))
        dist_ahrs = abs(angle_diff_rad(y_ahrs, mag_yaw))
        print(
            f"mode {label}: ars={math.degrees(y_ars)} ahrs={math.degrees(y_ahrs)} "
            f"mag={math.degrees(mag_yaw)} d_ars={math.degrees(dist_ars)} "
            f"d_ahrs={math.degrees(dist_ahrs)}",
            flush=True,
        )
        assert dist_ahrs < dist_ars, (
            f"AHRS yaw was not strictly nearer the magnetometer heading than ARS "
            f"at the {label} epoch"
        )


def test_ahrs_magnetic_disturbance_does_not_tilt_roll_pitch():
    yaw_ref = runtime_att_yaw_rad()
    # The sample is built from a known Tait-Bryan tilt, not from the
    # leveling helper (that helper is only promised on static (0, 0, −g)).
    # The constructor returns R*(0, 0, −g), so the gravity reaction of the
    # vector is the negated argument. Init is a near-zero roll, so echoing
    # the initial attitude is not this tilt.
    roll0 = runtime_tilt_rad()
    pitch0 = 0.0
    held_roll = -roll0
    held_pitch = -pitch0
    acc = still_level_acc(pitch0, roll0)
    mag_n = (22.0, 0.0, 40.0)
    mag = body_mag_for_yaw(held_roll, held_pitch, yaw_ref, mag_n)
    disturb_n = ned_horiz_rotate_scale(mag_n, math.radians(80.0), 1.0)
    disturb_n = (disturb_n[0], disturb_n[1] + 18.0, disturb_n[2] + 12.0)
    mag_d = body_mag_for_yaw(held_roll, held_pitch, yaw_ref, disturb_n)
    duration_s = 14.0
    hold_kw = dict(t0_us=0, duration_s=duration_s, acc=acc, gyr=(0.0, 0.0, 0.0))
    clean = c_att_run(_ahrs(cmds=att_hold(**hold_kw, mag=mag)))
    dist = c_att_run(_ahrs(cmds=att_hold(**hold_kw, mag=mag_d)))
    ars = c_att_run(_ars(cmds=att_hold(**hold_kw)))
    _assert_init_ok(clean, "AHRS clean mag")
    _assert_init_ok(dist, "AHRS disturbed mag")
    _assert_init_ok(ars, "ARS tilted static")
    rc, pc, _yc = require_att(clean.last(), "AHRS clean mag")
    rd, pd, _yd = require_att(dist.last(), "AHRS disturbed mag")
    ra, pa, _ya = require_att(ars.last(), "ARS tilted static")
    # Initial attitude is the near-zero roll this case boots with. Pitch's
    # generating tilt is that same initial pitch, so the other side of the
    # pitch contrast is the magnetometer heading the sample was built from.
    init_roll = _CASE_ROLL_RAD
    init_pitch = 0.0
    print(
        f"disturbance tilt: clean=({math.degrees(rc)},{math.degrees(pc)}) "
        f"dist=({math.degrees(rd)},{math.degrees(pd)}) "
        f"ars=({math.degrees(ra)},{math.degrees(pa)}) "
        f"held=({math.degrees(held_roll)},{math.degrees(held_pitch)}) "
        f"heading={math.degrees(yaw_ref)} "
        f"droll={math.degrees(rd - rc)} dpitch={math.degrees(pd - pc)} deg",
        flush=True,
    )

    def _nearer(published: float, target: float, other: float) -> bool:
        return abs(angle_diff_rad(published, target)) < abs(
            angle_diff_rad(published, other)
        )

    # roll and pitch are corrected from the accelerometer against
    # gravity. Nearer that specific-force tilt than the attitude the run
    # started from. Pitch's tilt is the initial pitch, so its other side
    # is the magnetometer heading. No degree band is frozen.
    assert _nearer(rc, held_roll, init_roll), (
        "clean AHRS roll was not nearer the specific-force tilt than the initial roll"
    )
    assert _nearer(pc, held_pitch, yaw_ref), (
        "clean AHRS pitch sat on the magnetometer heading rather than the specific-force tilt"
    )
    assert _nearer(ra, held_roll, init_roll), (
        "ARS roll was not nearer the specific-force tilt than the initial roll"
    )
    assert _nearer(pa, held_pitch, yaw_ref), (
        "ARS pitch sat on the magnetometer heading rather than the specific-force tilt"
    )
    # magnetic disturbances do not tilt roll/pitch. The disturbed arm
    # stays on the clean arm rather than on the magnetometer heading.
    assert _nearer(rd, rc, yaw_ref), (
        "disturbed AHRS roll sat on the magnetometer heading rather than the clean arm"
    )
    assert _nearer(pd, pc, yaw_ref), (
        "disturbed AHRS pitch sat on the magnetometer heading rather than the clean arm"
    )


# ---------------------------------------------------------------------------
# B. Named 10 s reference scenario
# ---------------------------------------------------------------------------


def test_reference_scenario_converges_in_10s():
    seeds = runtime_noise_seeds()
    init_rpy = (
        math.radians(REF_INIT_ERR_DEG),
        math.radians(REF_INIT_ERR_DEG),
        0.0,
    )
    for seed in seeds:
        run = c_att_run(_ars(rpy=init_rpy, cmds=reference_stream(seed)))
        _assert_init_ok(run, f"reference seed {seed}")
        last = require_att(run.last(), f"reference seed {seed} 10s")
        bias = require_bias(run.last(), f"reference seed {seed} bias")
        e_r = abs(math.degrees(last[0]))
        e_p = abs(math.degrees(last[1]))
        bx = math.degrees(bias[0])
        by = math.degrees(bias[1])
        print(
            f"reference seed={seed} rp_err={e_r},{e_p} bias_dps={bx},{by}",
            flush=True,
        )
        assert e_r <= REF_RP_LIM_DEG, f"roll error {e_r} deg exceeds 0.2°"
        assert e_p <= REF_RP_LIM_DEG, f"pitch error {e_p} deg exceeds 0.2°"
        assert e_r < REF_INIT_ERR_DEG - REF_RP_LIM_DEG, (
            f"reference scenario stayed at the 3° initial roll error ({e_r} deg)"
        )
        assert e_p < REF_INIT_ERR_DEG - REF_RP_LIM_DEG, (
            f"reference scenario stayed at the 3° initial pitch error ({e_p} deg)"
        )
        assert abs(bx - REF_BIAS_DPS[0]) <= REF_BIAS_LIM_DPS, (
            f"x gyro bias {bx} °/s is not within 0.1 °/s of 1 °/s"
        )
        assert abs(by - REF_BIAS_DPS[1]) <= REF_BIAS_LIM_DPS, (
            f"y gyro bias {by} °/s is not within 0.1 °/s of -2 °/s"
        )


# ---------------------------------------------------------------------------
# C. WMM declination step
# ---------------------------------------------------------------------------


def _true_yaw_body_mag(lat, lon, true_yaw):
    mag_n = ned_field_from_independent_wmm(lat, lon, ATT_YEAR)
    acc = still_level_acc(0.0, 0.0)
    mag = body_mag_for_yaw(0.0, 0.0, true_yaw, mag_n)
    return acc, mag, mag_n


def test_ahrs_yaw_magnetic_until_position_supplied():
    lat, lon, _h, decl_deg = runtime_declination_site()
    true_yaw = runtime_att_yaw_rad()
    acc, mag, _ = _true_yaw_body_mag(lat, lon, true_yaw)
    mag_yaw = true_yaw - math.radians(decl_deg)
    cmds = att_hold(
        t0_us=0, duration_s=12.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=mag
    )
    # A non-finite component is not a supplied geographic position or decimal
    # year. Declination applies only when both are supplied together.
    pos_only = c_att_run(
        _ahrs(cmds=[att_pos(lat, lon, float("nan")), *cmds])
    )
    year_only = c_att_run(
        _ahrs(cmds=[att_pos(float("nan"), float("nan"), ATT_YEAR), *cmds])
    )
    no_pos = c_att_run(_ahrs(cmds=cmds))
    with_pos = c_att_run(
        _ahrs(cmds=[att_pos(lat, lon, ATT_YEAR), *cmds])
    )
    _assert_init_ok(pos_only, "AHRS position without year")
    _assert_init_ok(year_only, "AHRS year without position")
    _assert_init_ok(no_pos, "AHRS magnetic")
    _assert_init_ok(with_pos, "AHRS true-north")
    y_pos = require_att(pos_only.last(), "AHRS position without year")[2]
    y_year = require_att(year_only.last(), "AHRS year without position")[2]
    y_m = require_att(no_pos.last(), "AHRS magnetic")[2]
    y_t = require_att(with_pos.last(), "AHRS true-north")[2]
    err_pos = abs(angle_diff_rad(y_pos, mag_yaw))
    err_year = abs(angle_diff_rad(y_year, mag_yaw))
    err_m = abs(angle_diff_rad(y_m, mag_yaw))
    err_t = abs(angle_diff_rad(y_t, true_yaw))
    err_t_as_mag = abs(angle_diff_rad(y_t, mag_yaw))
    err_m_as_true = abs(angle_diff_rad(y_m, true_yaw))
    err_pos_as_true = abs(angle_diff_rad(y_pos, true_yaw))
    err_year_as_true = abs(angle_diff_rad(y_year, true_yaw))
    print(
        f"mag vs true: y_m={math.degrees(y_m)} y_t={math.degrees(y_t)} "
        f"y_pos={math.degrees(y_pos)} y_year={math.degrees(y_year)} "
        f"D={decl_deg} err_m={math.degrees(err_m)} "
        f"err_m_as_true={math.degrees(err_m_as_true)} "
        f"err_t={math.degrees(err_t)} err_t_as_mag={math.degrees(err_t_as_mag)} deg",
        flush=True,
    )
    # yaw stays magnetic until a geographic position and a decimal year
    # are both supplied, and is true-north only after both are supplied.
    # Each incomplete arm is nearer magnetic north than true north; the
    # both-supplied arm is the reverse. No arrival window and no fraction
    # of the local declination are frozen.
    assert err_m < err_m_as_true, (
        "without position, yaw was not nearer magnetic north than true north"
    )
    assert err_pos < err_pos_as_true, (
        "with a position and no decimal year, yaw was not nearer magnetic north than true north"
    )
    assert err_year < err_year_as_true, (
        "with a decimal year and no position, yaw was not nearer magnetic north than true north"
    )
    assert err_t < err_t_as_mag, (
        "with position and year, yaw was not nearer true north than magnetic north"
    )


def test_ahrs_persistent_error_pulled_to_true_north():
    """a persistent heading error is pulled toward the active reference.

    After a geographic position and a decimal year are both supplied, that
    reference is true north, so the pull sits nearer true north than
    magnetic north. The same bytes without a position stay nearer magnetic
    north. No arrival window and no fraction of the local declination are
    frozen.
    """
    lat, lon, _h, decl_deg = runtime_declination_site()
    decl = math.radians(decl_deg)
    true_yaw = runtime_att_yaw_rad()
    acc, mag, _ = _true_yaw_body_mag(lat, lon, true_yaw)
    mag_yaw = true_yaw - decl
    quiet = att_hold(t0_us=0, duration_s=2.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=None)
    pulled = att_hold(
        t0_us=quiet[-1].t_us,
        duration_s=14.0,
        acc=acc,
        gyr=(0.0, 0.0, 0.0),
        mag=mag,
    )
    with_pos = c_att_run(_ahrs(cmds=[att_pos(lat, lon, ATT_YEAR), *quiet, *pulled]))
    no_pos = c_att_run(_ahrs(cmds=[*quiet, *pulled]))
    _assert_init_ok(with_pos, "AHRS true-north pull")
    _assert_init_ok(no_pos, "AHRS magnetic pull")
    y_true = require_att(with_pos.last(), "AHRS true-north pull")[2]
    y_mag = require_att(no_pos.last(), "AHRS magnetic pull")[2]
    err_true = abs(angle_diff_rad(y_true, true_yaw))
    err_as_mag = abs(angle_diff_rad(y_true, mag_yaw))
    err_mag = abs(angle_diff_rad(y_mag, mag_yaw))
    err_mag_as_true = abs(angle_diff_rad(y_mag, true_yaw))
    print(
        f"true-north pull: y_pos={math.degrees(y_true)} y_mag={math.degrees(y_mag)} "
        f"true={math.degrees(true_yaw)} magnetic={math.degrees(mag_yaw)} "
        f"D={decl_deg} err_true={math.degrees(err_true)} "
        f"err_as_mag={math.degrees(err_as_mag)} err_mag={math.degrees(err_mag)}",
        flush=True,
    )
    # nearer the named north than the other one. A pull that
    # is only just on that side still matches; 8° and 0.4 of declination
    # are not part of the sentence.
    assert err_true < err_as_mag, (
        "after a position and year were supplied, yaw was not nearer true north than magnetic north"
    )
    assert err_mag < err_mag_as_true, (
        "without a position, yaw was not nearer magnetic north than true north"
    )


def test_supplying_position_steps_yaw_by_declination_without_bias_jump():
    sites = [runtime_declination_site(), runtime_declination_site()]
    for lat, lon, _h, decl_deg in sites:
        true_yaw = runtime_att_yaw_rad()
        acc, mag, _ = _true_yaw_body_mag(lat, lon, true_yaw)
        cmds = att_hold(
            t0_us=0, duration_s=12.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=mag
        )
        # Same sensor history, then one position call and no new sample.
        # The step arm's position switches declination. The twin's position
        # is the same latitude and year at a longitude whose declination is
        # near zero, so that call does not switch declination.
        quiet_lon, _quiet_decl = longitude_same_latitude_without_declination(
            lat, ATT_YEAR
        )
        run = c_att_run(_ahrs(cmds=[*cmds, att_pos(lat, lon, ATT_YEAR)]))
        twin = c_att_run(_ahrs(cmds=[*cmds, att_pos(lat, quiet_lon, ATT_YEAR)]))
        _assert_init_ok(run, "AHRS declination step")
        _assert_init_ok(twin, "AHRS no declination switch")
        assert len(run.snaps) >= 3, "declination step run is missing snapshots"
        assert len(twin.snaps) >= 3, "declination twin is missing snapshots"
        before = run.snaps[-2]
        after = run.snaps[-1]
        y0 = require_att(before, "before position")[2]
        y1 = require_att(after, "after position")[2]
        b0 = require_bias(before, "before position")
        b1 = require_bias(after, "after position")
        twin_before = twin.snaps[-2]
        twin_after = twin.snaps[-1]
        ty0 = require_att(twin_before, "twin before the same update")[2]
        ty1 = require_att(twin_after, "twin after the same update")[2]
        tb0 = require_bias(twin_before, "twin before the same update")
        tb1 = require_bias(twin_after, "twin after the same update")
        step = angle_diff_rad(y1, y0)
        twin_step = angle_diff_rad(ty1, ty0)
        decl = math.radians(decl_deg)
        align = abs(angle_diff_rad(step, decl))
        twin_align = abs(angle_diff_rad(twin_step, decl))
        jump = hypot3(b1, b0)
        twin_jump = hypot3(tb1, tb0)
        print(
            f"step D={decl_deg} step={math.degrees(step)} align={math.degrees(align)} "
            f"twin_step={math.degrees(twin_step)} twin_align={math.degrees(twin_align)} "
            f"bias_jump={jump} twin_jump={twin_jump} "
            f"y0={math.degrees(y0)} y1={math.degrees(y1)}",
            flush=True,
        )
        # the switching arm's yaw change is nearer the declination
        # change than the non-switching twin's yaw change on the same update.
        # No fraction, floor, or multiple of the local declination is frozen.
        assert align < twin_align, (
            "switching declination did not leave the yaw step nearer the declination "
            "than the update that does not switch"
        )
        assert twin_align > abs(twin_step), (
            "the update that does not switch declination still stepped yaw by it"
        )
        # No degree-per-second ceiling. The step arm fails only when its
        # bias change is a jump the non-switching twin does not show.
        assert jump <= twin_jump, (
            "gyro-bias estimate jumped when declination was switched "
            "and did not jump on the same update without that switch"
        )


# ---------------------------------------------------------------------------
# D. Helpers and standalone init
# ---------------------------------------------------------------------------


def test_leveling_helper_zero_on_minus_g():
    r0, p0 = c_leveling((0.0, 0.0, -G_MPS2))
    tilt = runtime_tilt_rad()
    acc_t = still_level_acc(0.0, tilt)
    r1, p1 = c_leveling(acc_t)
    print(
        f"leveling minus-g rp={math.degrees(r0)},{math.degrees(p0)} "
        f"tilted={math.degrees(r1)},{math.degrees(p1)} deg",
        flush=True,
    )
    assert abs(r1) > math.radians(REF_INIT_ERR_DEG), (
        "tilted specific force still reported near-zero roll"
    )
    # (0, 0, −g) is near-zero. PRD's 0.2° is the 10 s filter's
    # arrived roll and pitch, not this helper. 3° is that scenario's
    # initial error. A reading has left that neighborhood when it is
    # closer to zero than to the initial error (2.9° has not; 1° has).
    # No frozen 0.2°.
    left = math.radians(REF_INIT_ERR_DEG) / 2.0
    assert abs(r0) < left, (
        "minus-g roll stayed in the 3° initial-error neighborhood"
    )
    assert abs(p0) < left, (
        "minus-g pitch stayed in the 3° initial-error neighborhood"
    )
    # The level sample sits nearer zero than the tilted sample.
    assert math.hypot(r0, p0) < math.hypot(r1, p1), (
        "minus-g leveling was not nearer zero than the tilted sample"
    )


def test_tilt_compensated_mag_heading_helper():
    """yaw from a tilt-compensated magnetometer sample.

    No degree window. The published heading only has to sit nearer the
    yaw the sample was built from than a heading that ignored the tilt.
    """
    mag_n = (21.0, 0.0, 42.0)
    # A few degrees of tilt can leave the untilted heading almost on the
    # generating yaw, so a compensated heading a few degrees off would
    # lose to it. A larger tilt makes "ignored the tilt" the worse reading.
    roll = runtime_tilt_rad() + 0.25 * math.pi
    cases = [
        (roll, -0.4 * roll, runtime_att_yaw_rad()),
        (-0.5 * roll, 0.4 * roll, runtime_att_yaw_rad()),
    ]
    for roll_i, pitch_i, true_yaw in cases:
        mag = body_mag_for_yaw(roll_i, pitch_i, true_yaw, mag_n)
        ignored = heading_ignoring_tilt(mag)
        err_ignored = abs(angle_diff_rad(ignored, true_yaw))
        assert err_ignored > 0.0, (
            "a heading that ignored the tilt is not distinguishable "
            "from the yaw the sample was built from"
        )
        for label, published in (
            ("C", c_mag_heading(mag, roll_i, pitch_i)),
            ("Python", py_mag_heading(mag, roll_i, pitch_i)),
        ):
            err = abs(angle_diff_rad(published, true_yaw))
            print(
                f"heading helper {label} "
                f"rpy={[math.degrees(x) for x in (roll_i, pitch_i, true_yaw)]} "
                f"err={math.degrees(err)} err_ignored={math.degrees(err_ignored)} deg",
                flush=True,
            )
            assert err < err_ignored, (
                f"{label} tilt-compensated heading is not nearer the yaw "
                "the sample was built from than a heading that ignored the tilt"
            )


def test_standalone_init_accepts_zero_attitude():
    """a zero initial attitude is accepted, not refused."""
    zero = (0.0, 0.0, 0.0)
    for scen, name in ((_ars(rpy=zero), "ARS"), (_ahrs(rpy=zero), "AHRS")):
        run = c_att_run(scen)
        print(f"{name} zero-attitude init_ok={run.init_ok}", flush=True)
        _assert_init_ok(run, f"{name} zero attitude")


def test_ars_init_accepts_zero_yaw_stddev():
    ok = c_att_run(_ars(std=(MANDATORY_STD_RAD, MANDATORY_STD_RAD, 0.0)))
    bad = c_att_run(_ahrs(std=(MANDATORY_STD_RAD, MANDATORY_STD_RAD, 0.0)))
    _assert_init_ok(ok, "ARS yaw stddev 0")
    _assert_init_refused(bad, "AHRS yaw stddev 0")


def test_init_refuses_non_positive_mandatory_stddev():
    baseline = c_att_run(_ars())
    _assert_init_ok(baseline, "positive stddev")
    cases = [
        (_ars(std=(0.0, MANDATORY_STD_RAD, 0.0)), "ARS roll stddev 0"),
        (_ars(std=(MANDATORY_STD_RAD, 0.0, 0.0)), "ARS pitch stddev 0"),
        (_ars(std=(-MANDATORY_STD_RAD, MANDATORY_STD_RAD, 0.0)), "ARS negative roll stddev"),
        (_ahrs(std=(MANDATORY_STD_RAD, MANDATORY_STD_RAD, 0.0)), "AHRS yaw stddev 0"),
    ]
    for scen, name in cases:
        run = c_att_run(scen)
        _assert_init_refused(run, name)


def test_init_refuses_nonfinite_attitude_or_stddev():
    baseline = c_att_run(_ahrs())
    _assert_init_ok(baseline, "finite init")
    nan = float("nan")
    inf = float("inf")
    cases = [
        (_ars(rpy=(nan, 0.0, 0.0)), "NaN roll"),
        (_ahrs(rpy=(0.0, inf, 0.0)), "Inf pitch"),
        (_ars(std=(nan, MANDATORY_STD_RAD, 0.0)), "NaN roll stddev"),
        (_ahrs(std=(MANDATORY_STD_RAD, MANDATORY_STD_RAD, inf)), "Inf yaw stddev"),
    ]
    for scen, name in cases:
        run = c_att_run(scen)
        _assert_init_refused(run, name)


# ---------------------------------------------------------------------------
# E. Non-finite input, time gaps, unusable fields, field-strength gate
# ---------------------------------------------------------------------------


def test_nonfinite_gyro_acc_drops_epoch_counter_increases():
    acc = SPECIFIC_FORCE_LEVEL
    pad = att_hold(t0_us=0, duration_s=1.0, acc=acc, gyr=(0.0, 0.0, 0.0))
    dt_bad = 0.01
    dt_next = 0.05
    t_bad = pad[-1].t_us + int(round(dt_bad * 1e6))
    t_ok = t_bad + int(round(dt_next * 1e6))
    # Finite z on the bad sample: coercing a non-finite component to zero and
    # still integrating that z-rate moves yaw. Dropping the epoch does not.
    # The following step is scored on this run's bias-corrected integral, not
    # on a fraction of the raw z-rate times the span.
    omega_bad = runtime_z_rate_rps() * 80.0
    omega_next = runtime_z_rate_rps() * 8.0
    nan = float("nan")
    inf = float("inf")
    gyro_nan = AttCmd(
        tag="E",
        t_us=t_bad,
        acc=acc,
        gyr=(nan, 0.0, omega_bad),
        mag=(20.0, 0.0, 40.0),
    )
    acc_inf = AttCmd(
        tag="E",
        t_us=t_bad,
        acc=(acc[0], inf, acc[2]),
        gyr=(0.0, 0.0, omega_bad),
    )
    recover = AttCmd(
        tag="E",
        t_us=t_ok,
        acc=acc,
        gyr=(0.0, 0.0, omega_next),
    )
    # A dropped epoch does not advance the clock, so the next epoch's interval
    # spans the gap. The rate that shows up is this epoch's z-rate, not the
    # rate that was on the dropped sample. Both products use this run's
    # published z-bias; a fraction of the raw rate times the span is not scored.
    span = (t_ok - pad[-1].t_us) / 1e6
    for bad, name in ((gyro_nan, "NaN gyro"), (acc_inf, "Inf accelerometer")):
        run = c_att_run(_ahrs(cmds=[*pad, bad, recover]))
        _assert_init_ok(run, name)
        # A dropped non-finite gyro or accelerometer epoch need not publish
        # an attitude at that timestamp. The counter and the held yaw are
        # read on the last accepted epoch and the following valid epoch.
        accepted = require_snap_at(run.snaps, pad[-1].t_us, f"{name} last accepted")
        following = require_snap_at(run.snaps, t_ok, f"{name} following")
        y_held = require_att(accepted, f"{name} last accepted")[2]
        y_next = require_att(following, f"{name} following")[2]
        signed = angle_diff_rad(y_next, y_held)
        bz = require_bias(following, f"{name} following")[2]
        corrected = (omega_next - bz) * span
        dropped = (omega_bad - bz) * dt_bad
        to_corrected, to_dropped = yaw_separations(signed, corrected, dropped)
        to_still = abs(angle_diff_rad(signed, 0.0))
        print(
            f"{name}: n0={accepted.n_invalid} n1={following.n_invalid} "
            f"signed={math.degrees(signed)} bz={math.degrees(bz)} "
            f"corrected={math.degrees(corrected)} dropped={math.degrees(dropped)} "
            f"to_corrected={math.degrees(to_corrected)} "
            f"to_dropped={math.degrees(to_dropped)} to_still={math.degrees(to_still)}",
            flush=True,
        )
        assert following.n_invalid > accepted.n_invalid, (
            f"{name}: invalid-input counter did not increase"
        )
        # the following epoch proceeds. Score that move on this run's
        # bias-corrected integral of the following z-rate, nearer that integral
        # than a heading that did not move. No fraction of the raw product.
        assert math.isfinite(corrected) and abs(corrected) > 0.0, (
            f"{name}: bias-corrected integral of the following z-rate is not "
            "distinguishable from a heading that did not move"
        )
        assert abs(angle_diff_rad(corrected, dropped)) > 0.0, (
            f"{name}: dropped rate is not distinguishable from the following "
            "bias-corrected integral"
        )
        assert to_corrected < to_still, (
            f"{name}: the following epoch did not move nearer this run's "
            "bias-corrected integral than a heading that stayed still"
        )
        # The dropped sample's rate did not move yaw: the same step sits
        # nearer the following bias-corrected integral than the dropped rate.
        assert to_corrected < to_dropped, (
            f"{name}: yaw after the bad epoch tracked the dropped rate, "
            "not this run's bias-corrected integral of the following z-rate"
        )
        assert all(math.isfinite(v) for v in require_att(following, f"{name} following")), (
            f"{name}: later finite epoch lost a finite attitude"
        )


def test_nonfinite_mag_ignored_imu_still_consumed():
    omega = runtime_z_rate_rps()
    acc = SPECIFIC_FORCE_LEVEL
    duration_s = 1.5
    pad = att_hold(t0_us=0, duration_s=0.5, acc=acc, gyr=(0.0, 0.0, 0.0))
    t0 = pad[-1].t_us
    n = int(round(duration_s * 100))
    nan = float("nan")
    mag_nan: list[AttCmd] = []
    gyro_nan: list[AttCmd] = []
    for i in range(1, n + 1):
        t_us = t0 + i * 10_000
        mag_nan.append(
            AttCmd(
                tag="E",
                t_us=t_us,
                acc=acc,
                gyr=(0.0, 0.0, omega),
                mag=(nan, 0.0, 40.0),
            )
        )
        gyro_nan.append(
            AttCmd(
                tag="E",
                t_us=t_us,
                acc=acc,
                gyr=(nan, 0.0, omega),
                mag=(20.0, 0.0, 40.0),
            )
        )
    imu = c_att_run(_ahrs(cmds=[*pad, *mag_nan]))
    dropped = c_att_run(_ahrs(cmds=[*pad, *gyro_nan]))
    _assert_init_ok(imu, "NaN mag")
    # The last snapshot is a dropped non-finite gyro timestamp. Init must
    # succeed; that timestamp need not publish an attitude.
    assert dropped.init_ok, "NaN gyro twin: init was refused"
    # A non-finite magnetometer sample is ignored, so the IMU epoch is still
    # consumed and a yaw is published on those timestamps. How close that yaw
    # sits to the raw rate times time is not scored.
    pad_imu = require_snap_at(imu.snaps, t0, "NaN mag pad")
    y0 = require_att(pad_imu, "NaN mag pad")[2]
    y_imu = require_att(imu.last(), "NaN mag")[2]
    moved = abs(angle_diff_rad(y_imu, y0))
    # A non-finite gyro drops the epoch. That timestamp need not publish an
    # attitude. Movement is read only from attitudes that were published
    # there; none published means the dropped stretch added no yaw.
    drop_times = {cmd.t_us for cmd in gyro_nan}
    published = [
        snap
        for snap in dropped.snaps
        if snap.t_us in drop_times and snap.rpy_ok and snap.att is not None
    ]
    y_pad = require_att(
        require_snap_at(dropped.snaps, t0, "NaN gyro pad"), "NaN gyro pad"
    )[2]
    if published:
        held = abs(angle_diff_rad(published[-1].att[2], y_pad))
    else:
        held = 0.0
    n0 = pad_imu.n_invalid
    print(
        f"NaN mag vs NaN gyro: y_imu={math.degrees(y_imu)} moved={math.degrees(moved)} "
        f"held={math.degrees(held)} published_on_drop={len(published)} "
        f"n_invalid {n0}->{imu.last().n_invalid}",
        flush=True,
    )
    assert imu.last().n_invalid > n0, "NaN magnetometer did not increment the invalid-input counter"
    assert moved > held, (
        "NaN magnetometer did not keep the IMU epoch moving relative to the NaN-gyro drop"
    )


def _finite_mag_after_nan_gyro(yaw_ref: float) -> None:
    acc = SPECIFIC_FORCE_LEVEL
    mag = body_mag_for_yaw(0.0, 0.0, yaw_ref, (20.0, 0.0, 40.0))
    nan = float("nan")
    # IMU-only pad so published yaw starts near 0. Mag arrives only after NaN.
    pad = att_hold(t0_us=0, duration_s=0.4, acc=acc, gyr=(0.0, 0.0, 0.0))
    t0 = pad[-1].t_us
    bad = [
        AttCmd(tag="E", t_us=t0 + i * 10_000, acc=acc, gyr=(nan, 0.0, 0.0), mag=mag)
        for i in range(1, 8)
    ]
    good = att_hold(
        t0_us=bad[-1].t_us, duration_s=8.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=mag
    )
    run = c_att_run(_ahrs(cmds=[*pad, *bad, *good]))
    _assert_init_ok(run, "finite mag after NaN gyro")
    before = [s for s in run.snaps if s.t_us == t0]
    nan_snaps = [s for s in run.snaps if t0 < s.t_us <= bad[-1].t_us]
    assert before and nan_snaps, "finite mag after NaN gyro: missing snapshots"
    print(
        f"NaN-then-mag: n0={before[0].n_invalid} n_nan={nan_snaps[-1].n_invalid} "
        f"n_end={run.last().n_invalid}",
        flush=True,
    )
    assert nan_snaps[-1].n_invalid > before[0].n_invalid, (
        "NaN gyro stretch did not increment the invalid-input counter"
    )
    att = require_att(run.last(), "finite mag after NaN gyro")
    print(
        f"NaN-then-mag: att={[math.degrees(v) for v in att]} "
        f"ref={math.degrees(yaw_ref)} deg",
        flush=True,
    )
    assert all(math.isfinite(v) for v in att), (
        "finite mag after NaN gyro published a non-finite attitude"
    )


def test_finite_mag_after_nan_gyro_still_finite_attitude():
    yaw_a = runtime_att_yaw_rad()
    yaw_b = runtime_att_yaw_rad()
    if abs(angle_diff_rad(yaw_a, yaw_b)) < math.radians(40.0):
        yaw_b = yaw_a + math.radians(70.0)
    _finite_mag_after_nan_gyro(yaw_a)
    _finite_mag_after_nan_gyro(yaw_b)


def _continuing_integral(anchor, later, omega, what):
    """Bias-corrected z integral along later snapshots that move forward.

    A step whose timestamp does not increase is the skipped epoch, not part
    of the integral. A missing bias is not treated as zero.
    """
    total = 0.0
    prev_t = anchor.t_us
    for snap in later:
        bz = require_bias(snap, what)[2]
        if snap.t_us > prev_t:
            total += (float(omega) - bz) * (snap.t_us - prev_t) / 1e6
        prev_t = snap.t_us
    if not math.isfinite(total):
        raise AssertionError(f"{what}: bias-corrected integral is not finite")
    return total


def test_backwards_timestamp_skips_epoch():
    """a backwards timestamp skips that epoch; later timestamps continue.

    The forward epoch is a live baseline scored on this run's bias-corrected
    integral. The resume is scored on its own bias-corrected integral. The
    backwards step stays nearer the last accepted yaw than that baseline.
    No fraction of the raw rate times time.
    """
    omega = runtime_z_rate_rps()
    acc = SPECIFIC_FORCE_LEVEL
    pad = att_hold(t0_us=0, duration_s=1.0, acc=acc, gyr=(0.0, 0.0, omega))
    t_last = pad[-1].t_us
    # Same rate on the pad, the backwards epoch, and a forward twin. Dropping
    # only a larger gyro would not explain a skip at this rate.
    fwd = AttCmd(tag="E", t_us=t_last + 10_000, acc=acc, gyr=(0.0, 0.0, omega))
    fwd_run = c_att_run(_ars(cmds=[*pad, fwd]))
    _assert_init_ok(fwd_run, "forward twin")
    fwd_pad = require_snap_at(fwd_run.snaps, t_last, "forward pad")
    y_fwd_pad = require_att(fwd_pad, "forward pad")[2]
    y_fwd = require_att(fwd_run.last(), "forward twin")[2]
    bz_fwd = require_bias(fwd_run.last(), "forward twin")[2]
    dt_fwd = (fwd.t_us - t_last) / 1e6
    dy_fwd = angle_diff_rad(y_fwd, y_fwd_pad)
    corrected_fwd = (omega - bz_fwd) * dt_fwd
    to_fwd, still_fwd = yaw_separations(dy_fwd, corrected_fwd, 0.0)
    # PRD live baseline: one forward epoch moved. Nearer this run's
    # bias-corrected integral than a heading that did not move. Not a
    # fraction of the raw rate times 10 ms.
    assert math.isfinite(corrected_fwd) and abs(corrected_fwd) > 0.0, (
        "forward epoch: bias-corrected integral is not distinguishable "
        "from a heading that did not move"
    )
    assert to_fwd < still_fwd, (
        "forward epoch did not move nearer this run's bias-corrected "
        "integral than a heading that stayed still"
    )
    # Off the 10 ms pad grid so the reverse SNAP is uniquely keyed.
    back = AttCmd(
        tag="E",
        t_us=t_last // 2 + 7,
        acc=acc,
        gyr=(0.0, 0.0, omega),
    )
    resume = att_hold(
        t0_us=back.t_us, duration_s=1.0, acc=acc, gyr=(0.0, 0.0, omega)
    )
    run = c_att_run(_ars(cmds=[*pad, back, *resume]))
    _assert_init_ok(run, "backwards timestamp")
    # The skipped timestamp need not publish an attitude. The last accepted
    # epoch is the pad; later increasing timestamps are the resume.
    accepted = [
        s for s in run.snaps if s.t_us == t_last and s.rpy_ok and s.att is not None
    ]
    assert accepted, "last accepted epoch published no attitude"
    resume_times = {cmd.t_us for cmd in resume}
    later = [
        s
        for s in run.snaps
        if s.t_us in resume_times and s.rpy_ok and s.att is not None
    ]
    assert later, "later increasing timestamps published no attitude"
    y_pad = require_att(accepted[0], "last accepted epoch")[2]
    y_first = require_att(later[0], "first later increasing timestamp")[2]
    y_end = require_att(later[-1], "later increasing timestamps")[2]
    dy_first = angle_diff_rad(y_first, y_pad)
    # Distance of the next increasing timestamp from the last accepted yaw,
    # against how far the live forward epoch moved. Still sitting on that
    # yaw is nearer than the baseline; moving only as far as the baseline
    # is the one continued step. Farther than the baseline means the
    # skipped epoch was integrated.
    to_accepted, baseline = yaw_separations(0.0, dy_first, dy_fwd)
    signed = angle_diff_rad(y_end, y_pad)
    corrected = _continuing_integral(accepted[0], later, omega, "backwards resume")
    to_resume, still_resume = yaw_separations(signed, corrected, 0.0)
    print(
        f"backwards: y_pad={math.degrees(y_pad)} y_first={math.degrees(y_first)} "
        f"y_end={math.degrees(y_end)} dy_first={math.degrees(dy_first)} "
        f"dy_fwd={math.degrees(dy_fwd)} to_accepted={math.degrees(to_accepted)} "
        f"signed={math.degrees(signed)} corrected={math.degrees(corrected)} "
        f"to_resume={math.degrees(to_resume)} still={math.degrees(still_resume)} deg",
        flush=True,
    )
    assert baseline > 0.0 and math.isfinite(baseline), (
        "forward epoch: live baseline did not move"
    )
    assert to_accepted <= baseline, (
        "backwards step is farther from the last accepted yaw than the "
        "live forward baseline"
    )
    # Later increasing timestamps continue. Score that coast on this run's
    # bias-corrected integral, not a fraction of the raw rate times time.
    # The 1 s resume at the runtime z-rate makes that integral several
    # degrees, so the comparison with a heading that did not move is always
    # made (no branch that skips it).
    assert abs(angle_diff_rad(corrected, 0.0)) > math.radians(1.0), (
        "backwards resume: bias-corrected integral is not distinguishable "
        "from a heading that did not move"
    )
    assert to_resume < still_resume, (
        "later increasing timestamps are nearer a heading that did not "
        "move than this run's bias-corrected integral"
    )


def test_forward_gap_over_0_2s_skips_attitude_integration():
    omega = runtime_z_rate_rps()
    acc = SPECIFIC_FORCE_LEVEL
    pad = att_hold(t0_us=0, duration_s=0.8, acc=acc, gyr=(0.0, 0.0, omega))
    t0 = pad[-1].t_us

    def _gap(dt_s: float):
        jump = AttCmd(
            tag="E",
            t_us=t0 + int(round(dt_s * 1e6)),
            acc=acc,
            gyr=(0.0, 0.0, omega),
        )
        return c_att_run(_ars(cmds=[*pad, jump]))

    inside = _gap(GAP_INSIDE_S)
    outside = _gap(GAP_OUTSIDE_S)
    _assert_init_ok(inside, "0.15 s gap")
    _assert_init_ok(outside, "0.25 s gap")

    def _gap_step(run, dt_s, label):
        pad = [s for s in run.snaps if s.t_us == t0]
        assert pad, f"{label}: missing pre-gap snapshot"
        y_pad = require_att(pad[0], f"{label} pad")[2]
        bz = require_bias(pad[0], f"{label} pad")[2]
        y = require_att(run.last(), f"{label} gap")[2]
        dy = angle_diff_rad(y, y_pad)
        corrected = (omega - bz) * dt_s
        if not math.isfinite(corrected) or not math.isfinite(dy):
            raise AssertionError(f"{label}: bias-corrected integral is not finite")
        return dy, corrected

    dy_in, corrected_in = _gap_step(inside, GAP_INSIDE_S, "0.15 s")
    dy_out, corrected_out = _gap_step(outside, GAP_OUTSIDE_S, "0.25 s")
    to_in, still_in = yaw_separations(dy_in, corrected_in, 0.0)
    to_out, still_out = yaw_separations(dy_out, corrected_out, 0.0)
    print(
        f"gap: dy_in={math.degrees(dy_in)} corrected_in={math.degrees(corrected_in)} "
        f"to_in={math.degrees(to_in)} still_in={math.degrees(still_in)} "
        f"dy_out={math.degrees(dy_out)} corrected_out={math.degrees(corrected_out)} "
        f"to_out={math.degrees(to_out)} still_out={math.degrees(still_out)} deg",
        flush=True,
    )
    # Shorter than 0.2 s still integrates. The live baseline is this run's
    # bias-corrected integral, not a fraction of the raw rate times the gap.
    assert abs(corrected_in) > 0.0, (
        "0.15 s gap: bias-corrected integral is not distinguishable from a heading that did not move"
    )
    assert to_in < still_in, (
        "0.15 s gap: yaw change is nearer a heading that did not integrate "
        "than this run's bias-corrected integral"
    )
    # Longer than 0.2 s skips that epoch. Published yaw stays nearer the
    # pre-gap heading than the bias-corrected integral of the same gap.
    assert abs(corrected_out) > 0.0, (
        "0.25 s gap: bias-corrected integral is not distinguishable from the pre-gap yaw"
    )
    assert still_out < to_out, (
        "0.25 s gap: yaw is nearer the bias-corrected integral than the pre-gap yaw"
    )


def test_mag_fusion_skipped_for_unusable_fields_and_gimbal_lock():
    yaw_a = runtime_att_yaw_rad()
    yaw_b = runtime_att_yaw_rad()
    if abs(angle_diff_rad(yaw_a, yaw_b)) < math.radians(25.0):
        yaw_b = yaw_a + math.radians(50.0)
    mag_n = (22.0, 0.0, 38.0)
    acc = SPECIFIC_FORCE_LEVEL
    mag_a = body_mag_for_yaw(0.0, 0.0, yaw_a, mag_n)
    mag_b = body_mag_for_yaw(0.0, 0.0, yaw_b, mag_n)
    baseline = att_hold(
        t0_us=0, duration_s=6.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=mag_a
    )
    live = c_att_run(_ahrs(cmds=baseline))
    _assert_init_ok(live, "usable mag baseline")
    y_live = require_att(live.last(), "usable mag baseline")[2]
    y_init = _ahrs().rpy[2]
    to_sample = abs(angle_diff_rad(y_live, yaw_a))
    to_init = abs(angle_diff_rad(y_live, y_init))
    print(
        f"usable mag: y={math.degrees(y_live)} A={math.degrees(yaw_a)} "
        f"to_sample={math.degrees(to_sample)} to_init={math.degrees(to_init)} deg",
        flush=True,
    )
    # a usable heading is fused. Nearer that heading than the yaw
    # this run started from. No arrival angle is frozen.
    assert to_sample < to_init, (
        "usable magnetometer left yaw nearer the initial heading than that sample's heading"
    )

    window_s = 70.0

    def _window(mag, name):
        cmds = att_hold(
            t0_us=baseline[-1].t_us,
            duration_s=window_s,
            acc=acc,
            gyr=(0.0, 0.0, 0.0),
            mag=mag,
        )
        run = c_att_run(_ahrs(cmds=[*baseline, *cmds]))
        _assert_init_ok(run, name)
        att = require_att(run.last(), name)
        assert all(math.isfinite(v) for v in att), f"{name}: attitude was not finite"
        return att

    att_use = _window(mag_b, "usable heading contrast")
    y_use = att_use[2]
    gap = abs(angle_diff_rad(yaw_b, y_live))
    left = abs(angle_diff_rad(y_use, y_live))
    to_b = abs(angle_diff_rad(y_use, yaw_b))
    prog_use = gap - to_b
    print(
        f"usable contrast: y={math.degrees(y_use)} live={math.degrees(y_live)} "
        f"B={math.degrees(yaw_b)} left={math.degrees(left)} to_b={math.degrees(to_b)} "
        f"gap={math.degrees(gap)} progress={math.degrees(prog_use)}",
        flush=True,
    )
    # A usable heading is fused: yaw ends nearer the new heading than it
    # started. How far it gets in the window is the downweighting/tuning the
    # PRD leaves open (a large persistent heading step may be downweighted),
    # so no halfway point is required. The skipped arms below are scored
    # against this run's own progress instead.
    assert gap > math.radians(20.0), "new heading is not distinguishable from the prior yaw"
    assert prog_use > 0.0, "usable heading did not move yaw toward the new heading"

    def _stayed(att, name, prog_ref):
        assert all(math.isfinite(v) for v in att), f"{name}: attitude was not finite"
        stayed = abs(angle_diff_rad(att[2], y_live))
        to_new = abs(angle_diff_rad(att[2], yaw_b))
        prog = gap - to_new
        print(
            f"{name}: y={math.degrees(att[2])} pitch={math.degrees(att[1])} "
            f"live={math.degrees(y_live)} stay={math.degrees(stayed)} "
            f"to_new={math.degrees(to_new)} progress={math.degrees(prog)} "
            f"fused_progress={math.degrees(prog_ref)}",
            flush=True,
        )
        # Skip does not freeze yaw: residual z-rate may move it. It must
        # stay nearer the prior usable heading than the rejected sample.
        assert stayed < to_new, (
            f"{name}: skipped fusion moved nearer the new heading than the prior heading"
        )
        # Rate-independent contrast with the fused twin of the same bytes
        # and duration: a skipped sample closes less than half of the gap
        # the usable sample closed. A slow fusion that never skipped moves
        # as far as its fused twin and fails here.
        assert prog < 0.5 * prog_ref, (
            f"{name}: skipped fusion moved toward the new heading as far as the fused twin"
        )
        return stayed

    y_zero = _window((0.0, 0.0, 0.0), "near-zero field")
    y_vert = _window(
        body_mag_for_yaw(0.0, 0.0, yaw_b, (0.2, 0.0, 48.0)),
        "vertical field",
    )
    _stayed(y_zero, "near-zero", prog_use)
    _stayed(y_vert, "vertical", prog_use)

    def _held_pitch(pitch, name):
        # Specific force of this pitch, read back through the leveling
        # helper so the held attitude is the one that force actually is.
        # The magnetometer sample is built at that same attitude. Published
        # pitch is not scored: the sentence only says whether heading fusion ran.
        acc = still_level_acc(pitch, 0.0)
        _roll, held = c_leveling(acc)
        mag = body_mag_for_yaw(0.0, held, yaw_b, mag_n)
        cmds = att_hold(
            t0_us=0,
            duration_s=window_s,
            acc=acc,
            gyr=(0.0, 0.0, 0.0),
            mag=mag,
        )
        run = c_att_run(_ahrs(rpy=(0.0, held, y_live), cmds=cmds))
        _assert_init_ok(run, name)
        att = require_att(run.last(), name)
        assert all(math.isfinite(v) for v in att), f"{name}: attitude was not finite"
        print(
            f"{name}: y={math.degrees(att[2])} pitch={math.degrees(att[1])} "
            f"held_pitch={math.degrees(held)}",
            flush=True,
        )
        return att

    # Exact ±90° folds the heading into roll, so published yaw is not the
    # fusion observable. One degree off the lock is still the lock for a
    # skip that only covers a few degrees of ±90°, and yaw is still the
    # heading. The open pitch is a few degrees, not an intermediate band.
    pitch_clear = runtime_tilt_rad()
    pitch_lock = (math.pi / 2.0) - math.radians(1.0)
    for sign, name in ((1.0, "gimbal +"), (-1.0, "gimbal -")):
        att_open = _held_pitch(sign * pitch_clear, f"{name} open")
        to_open = abs(angle_diff_rad(att_open[2], yaw_b))
        left_open = abs(angle_diff_rad(att_open[2], y_live))
        # Same rate-independent reading as the level arms: the open pitch
        # fuses (ends nearer the new heading than it started); how far it
        # gets in the window is not frozen.
        prog_open = gap - to_open
        assert prog_open > 0.0, (
            f"{name}: open pitch did not move yaw toward the new heading"
        )
        att = _held_pitch(sign * pitch_lock, name)
        stayed = abs(angle_diff_rad(att[2], y_live))
        to_locked = abs(angle_diff_rad(att[2], yaw_b))
        prog_lock = gap - to_locked
        print(
            f"{name}: stay={math.degrees(stayed)} to_new={math.degrees(to_locked)} "
            f"open_to_new={math.degrees(to_open)} open_left={math.degrees(left_open)} "
            f"open_progress={math.degrees(prog_open)} lock_progress={math.degrees(prog_lock)}",
            flush=True,
        )
        assert stayed < to_locked, (
            f"{name}: pitch at gimbal lock moved nearer the new heading than the prior heading"
        )
        assert prog_lock < 0.5 * prog_open, (
            f"{name}: pitch at gimbal lock moved toward the new heading as far as the open pitch"
        )


def test_field_strength_gate_downweights_not_drops():
    lat, lon, _h, _d = runtime_declination_site()
    true_yaw = runtime_att_yaw_rad()
    mag_n = ned_field_from_independent_wmm(lat, lon, ATT_YEAR)
    acc = SPECIFIC_FORCE_LEVEL
    mag = body_mag_for_yaw(0.0, 0.0, true_yaw, mag_n)
    phi = math.radians(48.0 + (abs(hash((lat, lon))) % 25))
    dist3 = body_mag_for_yaw(0.0, 0.0, true_yaw, ned_horiz_rotate_scale(mag_n, phi, 3.0))
    dist5 = body_mag_for_yaw(0.0, 0.0, true_yaw, ned_horiz_rotate_scale(mag_n, phi, 1.20))
    # 45% magnitude error is outside the documented 30% tolerance; 20% is inside it
    # and outside a numeric-zero tolerance.
    # Scale 1 keeps the heading disturbance at full weight so fusion can finish.
    dist_head = body_mag_for_yaw(
        0.0, 0.0, true_yaw, ned_horiz_rotate_scale(mag_n, phi, 1.0)
    )
    dist_out = body_mag_for_yaw(
        0.0, 0.0, true_yaw, ned_horiz_rotate_scale(mag_n, phi, 1.45)
    )
    pad = att_hold(t0_us=0, duration_s=8.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=mag)
    t1 = pad[-1].t_us
    disturb = att_hold(t0_us=t1, duration_s=8.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=dist3)
    none = att_hold(t0_us=t1, duration_s=8.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=None)
    mild = att_hold(t0_us=t1, duration_s=12.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=dist5)
    # Cold start: an already-converged heading treats a sudden large azimuth
    # change as an outlier, so the full-weight pull is observed from init.
    cold_head = att_hold(t0_us=0, duration_s=12.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=dist_head)
    cold_mild = att_hold(t0_us=0, duration_s=12.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=dist5)
    cold_out = att_hold(t0_us=0, duration_s=12.0, acc=acc, gyr=(0.0, 0.0, 0.0), mag=dist_out)
    pos = att_pos(lat, lon, ATT_YEAR)

    def _run(cmds, mag_check, mag_tol, with_pos):
        kw = dict(cmds=([pos] if with_pos else []) + cmds, mag_tol=mag_tol)
        if mag_check is not None:
            kw["mag_check"] = mag_check
        scen = _ahrs(**kw)
        run = c_att_run(scen)
        _assert_init_ok(run, "field gate")
        return require_att(run.last(), "field gate")[2]

    # Omit the enable knob (do not pass mag_check) — default off, not explicit False.
    y_omit = _run([*pad, *disturb], None, 0.0, True)
    y_off = _run([*pad, *disturb], False, 0.0, True)
    y_on = _run([*pad, *disturb], True, 0.0, True)
    y_on_explicit = _run([*pad, *disturb], True, FIELD_TOL_NAMED, True)
    y_none = _run([*pad, *none], True, 0.0, True)
    y_off_np = _run(cold_head, False, 0.0, False)
    y_on_np = _run(cold_head, True, 0.0, False)
    y_mild = _run([*pad, *mild], True, 0.0, True)
    y_full_mild = _run(cold_mild, False, 0.0, True)
    y_in0 = _run(cold_mild, True, 0.0, True)
    y_in30 = _run(cold_mild, True, FIELD_TOL_NAMED, True)
    y_out0 = _run(cold_out, True, 0.0, True)
    y_out30 = _run(cold_out, True, FIELD_TOL_NAMED, True)
    d_omit = abs(angle_diff_rad(y_omit, true_yaw))
    d_off = abs(angle_diff_rad(y_off, true_yaw))
    d_on = abs(angle_diff_rad(y_on, true_yaw))
    d_none = abs(angle_diff_rad(y_none, true_yaw))
    d_mild = abs(angle_diff_rad(y_mild, true_yaw))
    d_exp = abs(angle_diff_rad(y_on_explicit, y_on))
    d_npos = abs(angle_diff_rad(y_on_np, y_off_np))
    print(
        f"gate: d_omit={math.degrees(d_omit)} d_off={math.degrees(d_off)} "
        f"d_on={math.degrees(d_on)} d_none={math.degrees(d_none)} "
        f"d_npos={math.degrees(d_npos)} d_mild={math.degrees(d_mild)} "
        f"d_0_vs_30={math.degrees(d_exp)} deg",
        flush=True,
    )
    assert d_omit > d_on, (
        "omitting the field-strength enable knob did not leave the gate off"
    )
    assert d_off > d_on, "enabling the field-strength gate did not reduce the disturbance pull"
    # Downweight, not drop: published yaw of the gated arm lies strictly
    # between the full-weight arm and the no-magnetometer arm. Any residual
    # pull in that direction counts; a frozen angular floor does not.
    span = angle_diff_rad(y_off, y_none)
    pull = angle_diff_rad(y_on, y_none)
    assert span * pull > 0.0 and abs(pull) < abs(span), (
        "enabled field-strength gate did not leave published yaw strictly "
        "between the full-weight arm and the no-magnetometer arm"
    )
    # No-position agreement is not scored in degrees. Without a position the
    # gate stays off: each arm only has to lie on the disturbed heading's
    # side of the initial heading, and enabling the knob must not separate
    # the two arms by as much as that pull. Crossing halfway from the
    # initial heading is not required.
    assert d_mild > d_on, "a magnitude error inside 30% was treated like the 3× disturbance"
    # No position publishes magnetic heading. The body sample was built at
    # true_yaw in a field rotated by phi, so that heading is true yaw minus
    # the local declination minus phi.
    disturbed_mag = angle_diff_rad(true_yaw - math.radians(_d) - phi, 0.0)
    signed_off = angle_diff_rad(y_off_np, 0.0)
    signed_on = angle_diff_rad(y_on_np, 0.0)
    print(
        f"gate npos: disturbed={math.degrees(disturbed_mag)} "
        f"off={math.degrees(y_off_np)} on={math.degrees(y_on_np)} "
        f"split={math.degrees(abs(angle_diff_rad(y_on_np, y_off_np)))}",
        flush=True,
    )
    assert signed_off * disturbed_mag > 0.0, (
        "gate-off arm without position did not pull toward the disturbed heading"
    )
    assert signed_on * disturbed_mag > 0.0, (
        "gate-on arm without position did not pull toward the disturbed heading"
    )
    assert abs(angle_diff_rad(y_on_np, y_off_np)) < abs(signed_off), (
        "enabling the field-strength gate without a position reduced the heading pull"
    )
    assert abs(angle_diff_rad(y_on_np, y_off_np)) < abs(signed_on), (
        "enabling the field-strength gate without a position reduced the heading pull"
    )
    # Inside 30% stays nearer full weight than the same heading outside 30%,
    # for a zeroed tolerance and for an explicit 30%. How close to the
    # heading disturbance is not frozen.
    d_in0 = abs(angle_diff_rad(y_in0, y_full_mild))
    d_in30 = abs(angle_diff_rad(y_in30, y_full_mild))
    d_out0 = abs(angle_diff_rad(y_out0, y_full_mild))
    d_out30 = abs(angle_diff_rad(y_out30, y_full_mild))
    d_out_pair = abs(angle_diff_rad(y_out0, y_out30))
    print(
        f"gate tol: in0={math.degrees(d_in0)} in30={math.degrees(d_in30)} "
        f"out0={math.degrees(d_out0)} out30={math.degrees(d_out30)} "
        f"out_pair={math.degrees(d_out_pair)}",
        flush=True,
    )
    assert abs(phi) > math.radians(30.0), (
        "heading disturbance is not large enough to see full weight"
    )
    assert d_in0 < d_out0, (
        "a magnitude error inside 30% with tolerance left at 0 was not nearer full weight "
        "than the same heading outside 30%"
    )
    assert d_in30 < d_out30, (
        "a magnitude error inside 30% with an explicit 30% tolerance was not nearer full weight "
        "than the same heading outside 30%"
    )
    # Inside tolerance only has to stay nearer the full-weight arm than the
    # outside-tolerance arm. Crossing halfway from the initial heading of
    # zero is not required.
    assert d_out_pair < d_out0, (
        "tolerance left at 0 and an explicit 30% did not downweight the same outside-30% sample"
    )


# ---------------------------------------------------------------------------
# F. Explicit zero-rotation flag
# ---------------------------------------------------------------------------


def test_explicit_zero_rotation_flag_fuses_gyro_bias():
    omega = runtime_z_rate_rps()
    acc = SPECIFIC_FORCE_LEVEL
    duration_s = 3.0
    off = c_att_run(
        _ars(cmds=att_hold(t0_us=0, duration_s=duration_s, acc=acc, gyr=(0.0, 0.0, omega)))
    )
    on = c_att_run(
        _ars(
            cmds=att_hold(
                t0_us=0,
                duration_s=duration_s,
                acc=acc,
                gyr=(0.0, 0.0, omega),
                zaru=True,
            )
        )
    )
    _assert_init_ok(off, "ZARU flag off")
    _assert_init_ok(on, "ZARU flag on")
    y_off = require_att(off.last(), "ZARU off")[2]
    y_on = require_att(on.last(), "ZARU on")[2]
    b_off = require_bias(off.last(), "ZARU off")[2]
    b_on = require_bias(on.last(), "ZARU on")[2]
    print(
        f"ZARU flag: y_off={math.degrees(y_off)} y_on={math.degrees(y_on)} "
        f"bz_off={math.degrees(b_off)} bz_on={math.degrees(b_on)} "
        f"omega={math.degrees(omega)} deg/s",
        flush=True,
    )
    # the flag is opt-in. Flag-off yaw is the integral of the
    # bias-corrected z-rate, so a run that has already removed part of the
    # z-bias is still correct. Do not freeze a fraction of the raw rate
    # times time. The direct fusion is the contrast below.
    assert abs(b_on - omega) < abs(b_off - omega), (
        "explicit zero-rotation flag did not pull z-bias nearer the gyro "
        "reading than the flag-off estimate"
    )


def _assert_attitude_solution_has_no_velocity(att, bias, att_vel, nav_vel, what, *, nav=True):
    """While roll and pitch are published, the attitude solution has no velocity.

    That absence is a different observation from the navigation filter's
    velocity on the same stream, which is published. Gyro bias is a separate
    published 3-vector. Another finite 3-vector that is not a velocity — on
    the navigator, or hanging off the attitude result — is not this failure.
    A count of private estimate components is the implementer's and is not scored.
    """
    assert att is not None, f"{what}: attitude solution was not published"
    vals = tuple(att)
    assert len(vals) == 3, (
        f"{what}: attitude result carried components beyond roll/pitch/yaw"
    )
    assert math.isfinite(vals[0]) and math.isfinite(vals[1]), (
        f"{what}: roll and pitch are not available on the attitude solution"
    )
    if nav:
        assert nav_vel is not None and len(tuple(nav_vel)) == 3, (
            f"{what}: navigation filter published no velocity on this stream"
        )
        assert all(math.isfinite(v) for v in nav_vel), (
            f"{what}: navigation-filter velocity is not finite"
        )
    if att_vel is not None:
        copied = (
            nav
            and nav_vel is not None
            and tuple(att_vel) == tuple(nav_vel)
        )
        assert not copied, (
            f"{what}: attitude solution velocity is the navigation-filter velocity"
        )
        assert False, (
            f"{what}: attitude solution carried a velocity while roll and pitch are published"
        )
    assert bias is not None and len(tuple(bias)) == 3, (
        f"{what}: gyro bias was not published with the attitude solution"
    )
    assert all(math.isfinite(v) for v in bias), f"{what}: gyro bias is not finite"


def test_suite_standstill_fuses_bias_and_attitude_has_no_velocity():
    """the suite raises zero-rotation from INS standstill and fuses gyro bias.

    While roll and pitch are already available, the published attitude
    solution itself has no velocity. A zero GNSS speed raises the flag; a
    fast GNSS speed on the same still IMU does not.
    """
    lat, lon, h = _suite_site()
    mag = body_mag_for_yaw(0.0, 0.0, runtime_att_yaw_rad(), (20.0, 0.0, 40.0))
    bare_epochs = suite_imu_stream(
        duration_s=1.0, acc=SPECIFIC_FORCE_LEVEL, mag=mag
    )
    for run, name in (
        (c_suite_run(SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=bare_epochs)), "C"),
        (py_suite_run(SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=bare_epochs)), "Python"),
    ):
        assert run.init_ok, f"{name} suite init failed"
        last = run.last()
        assert last.ars_ok and last.ars_att is not None, f"{name}: suite ARS did not publish"
        assert last.ahrs_ok and last.ahrs_att is not None, f"{name}: suite AHRS did not publish"
        assert all(math.isfinite(v) for v in last.ars_att), f"{name}: ARS attitude not finite"
        assert all(math.isfinite(v) for v in last.ahrs_att), f"{name}: AHRS attitude not finite"
        print(
            f"{name} attitude solution ars_n={last.ars_n} ahrs_n={last.ahrs_n} "
            f"zaru={last.zaru}",
            flush=True,
        )
        _assert_attitude_solution_has_no_velocity(
            last.ars_att, last.ars_bias, last.ars_att_vel, last.vel_ned,
            f"{name} ARS", nav=False,
        )
        _assert_attitude_solution_has_no_velocity(
            last.ahrs_att, last.ahrs_bias, last.ahrs_att_vel, last.vel_ned,
            f"{name} AHRS", nav=False,
        )

    omega = abs(runtime_z_rate_rps()) * 0.08
    ecef = ecef_from_llh_deg(lat, lon, h)
    duration_s = ENTRY_DWELL_S + READY_WAIT_S + 4.0
    still_epochs = suite_imu_stream(
        duration_s=duration_s,
        acc=SPECIFIC_FORCE_LEVEL,
        gyr=(0.0, 0.0, omega),
        mag=mag,
        gnss_vel=(0.0, 0.0, 0.0),
        gnss_ecef=ecef,
    )
    fast_epochs = suite_imu_stream(
        duration_s=duration_s,
        acc=SPECIFIC_FORCE_LEVEL,
        gyr=(0.0, 0.0, omega),
        mag=mag,
        gnss_vel=(8.0, 0.0, 0.0),
        gnss_ecef=ecef,
    )
    for runner, name in ((c_suite_run, "C"), (py_suite_run, "Python")):
        still = runner(
            SuiteScenario(
                lat_deg=lat, lon_deg=lon, h_m=h,
                velocity_blind_disable=True, epochs=still_epochs,
            )
        )
        fast = runner(
            SuiteScenario(
                lat_deg=lat, lon_deg=lon, h_m=h,
                velocity_blind_disable=True, epochs=fast_epochs,
            )
        )
        assert still.init_ok and fast.init_ok, f"{name} suite init failed"
        s_last = still.last()
        f_last = fast.last()
        print(
            f"{name} standstill zaru={s_last.zaru} fast_zaru={f_last.zaru} "
            f"ars_n={s_last.ars_n} ahrs_n={s_last.ahrs_n} "
            f"ars_bias={s_last.ars_bias} ahrs_bias={s_last.ahrs_bias} "
            f"fast_ars_bias={f_last.ars_bias} fast_ahrs_bias={f_last.ahrs_bias}",
            flush=True,
        )
        assert s_last.zaru, (
            f"{name}: suite standstill did not raise the zero-rotation flag"
        )
        assert not f_last.zaru, (
            f"{name}: a fast GNSS velocity still raised the suite zero-rotation flag"
        )
        _assert_attitude_solution_has_no_velocity(
            s_last.ars_att, s_last.ars_bias, s_last.ars_att_vel, s_last.vel_ned,
            f"{name} still ARS",
        )
        _assert_attitude_solution_has_no_velocity(
            s_last.ahrs_att, s_last.ahrs_bias, s_last.ahrs_att_vel, s_last.vel_ned,
            f"{name} still AHRS",
        )
        _assert_attitude_solution_has_no_velocity(
            f_last.ars_att, f_last.ars_bias, f_last.ars_att_vel, f_last.vel_ned,
            f"{name} fast ARS",
        )
        _assert_attitude_solution_has_no_velocity(
            f_last.ahrs_att, f_last.ahrs_bias, f_last.ahrs_att_vel, f_last.vel_ned,
            f"{name} fast AHRS",
        )
        assert s_last.ars_bias_ok and s_last.ars_bias is not None, (
            f"{name}: suite ARS did not publish a gyro bias on the zero-speed run"
        )
        assert s_last.ahrs_bias_ok and s_last.ahrs_bias is not None, (
            f"{name}: suite AHRS did not publish a gyro bias on the zero-speed run"
        )
        assert f_last.ars_bias_ok and f_last.ars_bias is not None, (
            f"{name}: suite ARS did not publish a gyro bias on the fast-speed run"
        )
        assert f_last.ahrs_bias_ok and f_last.ahrs_bias is not None, (
            f"{name}: suite AHRS did not publish a gyro bias on the fast-speed run"
        )
        for label, still_b, fast_b in (
            ("ARS", s_last.ars_bias[2], f_last.ars_bias[2]),
            ("AHRS", s_last.ahrs_bias[2], f_last.ahrs_bias[2]),
        ):
            still_err = abs(still_b - omega)
            fast_err = abs(fast_b - omega)
            print(
                f"{name} {label} still_bz={math.degrees(still_b)} "
                f"fast_bz={math.degrees(fast_b)} omega={math.degrees(omega)} "
                f"still_err={math.degrees(still_err)} fast_err={math.degrees(fast_err)}",
                flush=True,
            )
            assert still_err < fast_err, (
                f"{name}: {label} zero-speed z-bias was not closer to the gyro rate "
                "than the fast-speed z-bias on the same IMU"
            )


# ---------------------------------------------------------------------------
# G. Suite bootstrap
# ---------------------------------------------------------------------------


def _suite_site():
    return runtime_site()


def _assert_suite_ars_yaw_follows_known_heading(y0, yp, yh, yaw, name):
    """No-heading yaw stays nearer 0; each known heading stays nearer that heading than 0.

    PRD names yaw 0 unless a prescribed attitude or a static yaw hint was
    supplied. It freezes no degree window, so the arms are scored against
    each other.
    """
    d0 = abs(angle_diff_rad(y0, 0.0))
    presc_from_heading = abs(angle_diff_rad(yp, yaw))
    presc_from_zero = abs(angle_diff_rad(yp, 0.0))
    hint_from_heading = abs(angle_diff_rad(yh, yaw))
    hint_from_zero = abs(angle_diff_rad(yh, 0.0))
    print(
        f"{name} suite ARS yaw auto={math.degrees(y0)} "
        f"prescribed={math.degrees(yp)} hint={math.degrees(yh)} "
        f"known={math.degrees(yaw)} "
        f"d0={math.degrees(d0)} "
        f"presc_h={math.degrees(presc_from_heading)} "
        f"hint_h={math.degrees(hint_from_heading)} deg",
        flush=True,
    )
    assert d0 < presc_from_zero and d0 < hint_from_zero, (
        f"{name}: no-heading suite ARS yaw was not nearer 0 than both known-heading arms"
    )
    assert presc_from_heading < presc_from_zero, (
        f"{name}: prescribed INS attitude was not nearer the supplied heading than 0"
    )
    assert hint_from_heading < hint_from_zero, (
        f"{name}: static yaw hint was not nearer the supplied heading than 0"
    )


def test_suite_ars_starts_on_imu_alone():
    """suite ARS bootstraps roll and pitch from the first valid IMU.

    That sentence names no degree band. The level IMU only has to leave
    published roll and pitch nearer level than the same suite entry fed a
    tilted specific force. Yaw stays 0 unless a known heading was supplied.
    """
    lat, lon, h = _suite_site()
    yaw = runtime_att_yaw_rad()
    epochs = suite_imu_stream(duration_s=1.0, acc=SPECIFIC_FORCE_LEVEL)
    tilt = runtime_tilt_rad()
    tilted_epochs = suite_imu_stream(
        duration_s=1.0, acc=still_level_acc(0.0, tilt)
    )
    auto_scen, presc_scen, hint_scen = suite_known_heading_scenarios(
        lat, lon, h, yaw, epochs, yaw_std=math.radians(5.0)
    )
    tilt_scen = SuiteScenario(
        lat_deg=lat, lon_deg=lon, h_m=h, epochs=tilted_epochs
    )
    for run_suite, name in ((c_suite_run, "C"), (py_suite_run, "Python")):
        run = run_suite(auto_scen)
        assert run.init_ok, f"{name} suite init failed"
        last = run.last()
        print(f"{name} IMU-only ars={last.ars_ok} ahrs={last.ahrs_ok}", flush=True)
        assert last.ars_ok and last.ars_att is not None, f"{name}: suite ARS did not start on IMU alone"
        assert all(math.isfinite(v) for v in last.ars_att), (
            f"{name}: suite ARS attitude not finite"
        )
        tilted = run_suite(tilt_scen)
        assert tilted.init_ok, f"{name} tilted suite init failed"
        t_last = tilted.last()
        assert t_last.ars_ok and t_last.ars_att is not None, (
            f"{name}: tilted twin did not publish suite ARS on the first valid IMU"
        )
        assert all(math.isfinite(v) for v in t_last.ars_att), (
            f"{name}: tilted twin suite ARS attitude not finite"
        )
        level_off = math.hypot(last.ars_att[0], last.ars_att[1])
        tilt_off = math.hypot(t_last.ars_att[0], t_last.ars_att[1])
        print(
            f"{name} suite ARS level_rp={math.degrees(last.ars_att[0])},"
            f"{math.degrees(last.ars_att[1])} "
            f"tilt_rp={math.degrees(t_last.ars_att[0])},"
            f"{math.degrees(t_last.ars_att[1])} "
            f"level_off={math.degrees(level_off)} tilt_off={math.degrees(tilt_off)} deg",
            flush=True,
        )
        assert level_off < tilt_off, (
            f"{name}: suite ARS roll and pitch on the level IMU were not "
            "nearer level than the tilted twin on the same suite entry"
        )
        assert not last.ahrs_ok, f"{name}: suite AHRS started without a magnetometer sample"
        presc = run_suite(presc_scen)
        hint = run_suite(hint_scen)
        assert presc.init_ok and hint.init_ok, f"{name} suite init failed"
        yp = presc.last().ars_att
        yh = hint.last().ars_att
        assert yp is not None and yh is not None, (
            f"{name}: known-heading suite ARS did not publish on the IMU-only start"
        )
        _assert_suite_ars_yaw_follows_known_heading(
            last.ars_att[2], yp[2], yh[2], yaw, f"{name} IMU-only"
        )


def test_suite_ahrs_waits_for_first_mag_sample():
    lat, lon, h = _suite_site()
    mag = body_mag_for_yaw(0.0, 0.0, runtime_att_yaw_rad(), (20.0, 0.0, 40.0))
    imu = suite_imu_stream(duration_s=0.8, acc=SPECIFIC_FORCE_LEVEL)
    both = suite_imu_stream(
        duration_s=1.2,
        acc=SPECIFIC_FORCE_LEVEL,
        mag=mag,
        t0_us=imu[-1].t_us,
    )
    scen = SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=[*imu, *both])
    for run, name in ((c_suite_run(scen), "C"), (py_suite_run(scen), "Python")):
        assert run.init_ok, f"{name} suite init failed"
        t_imu = imu[-1].t_us
        mid = [s for s in run.snaps if s.t_us == t_imu]
        assert mid, f"{name}: missing IMU-only snapshot"
        assert mid[0].ars_ok and not mid[0].ahrs_ok, (
            f"{name}: AHRS published before the first magnetometer sample"
        )
        last = run.last()
        print(f"{name} after mag ars={last.ars_ok} ahrs={last.ahrs_ok}", flush=True)
        assert last.ars_ok, f"{name}: suite ARS stopped after magnetometer samples"
        assert last.ahrs_ok and last.ahrs_att is not None, (
            f"{name}: suite AHRS did not start after the first magnetometer sample"
        )
        assert all(math.isfinite(v) for v in last.ahrs_att), f"{name}: suite AHRS attitude not finite"


def test_suite_publishes_ars_and_ahrs_together():
    """one suite run publishes the ARS instance and the AHRS instance together."""
    lat, lon, h = _suite_site()
    mag = body_mag_for_yaw(0.0, 0.0, runtime_att_yaw_rad(), (20.0, 0.0, 40.0))
    epochs = suite_imu_stream(duration_s=1.2, acc=SPECIFIC_FORCE_LEVEL, mag=mag)
    scen = SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=epochs)
    for run, name in ((c_suite_run(scen), "C"), (py_suite_run(scen), "Python")):
        assert run.init_ok, f"{name} suite init failed"
        last = run.last()
        print(
            f"{name} parallel ars={last.ars_ok} ahrs={last.ahrs_ok}",
            flush=True,
        )
        assert last.ars_ok and last.ars_att is not None, (
            f"{name}: suite did not publish ARS beside AHRS"
        )
        assert last.ahrs_ok and last.ahrs_att is not None, (
            f"{name}: suite did not publish AHRS beside ARS"
        )
        assert math.isfinite(last.ars_att[0]) and math.isfinite(last.ars_att[1]), (
            f"{name}: ARS roll/pitch were not published with AHRS"
        )
        assert math.isfinite(last.ahrs_att[0]) and math.isfinite(last.ahrs_att[1]), (
            f"{name}: AHRS roll/pitch were not published with ARS"
        )


def test_suite_ars_yaw_zero_unless_known_heading():
    lat, lon, h = _suite_site()
    yaw = runtime_att_yaw_rad()
    epochs = suite_imu_stream(duration_s=1.0, acc=SPECIFIC_FORCE_LEVEL)
    auto_scen, presc_scen, hint_scen = suite_known_heading_scenarios(
        lat, lon, h, yaw, epochs, yaw_std=math.radians(5.0)
    )
    for run_suite, name in ((c_suite_run, "C"), (py_suite_run, "Python")):
        auto = run_suite(auto_scen)
        presc = run_suite(presc_scen)
        hint = run_suite(hint_scen)
        assert auto.init_ok and presc.init_ok and hint.init_ok, f"{name} suite init failed"
        y0 = auto.last().ars_att
        yp = presc.last().ars_att
        yh = hint.last().ars_att
        assert y0 is not None and yp is not None and yh is not None, (
            f"{name}: suite ARS did not publish"
        )
        _assert_suite_ars_yaw_follows_known_heading(y0[2], yp[2], yh[2], yaw, name)


# ---------------------------------------------------------------------------
# Precision-restart watchdog
# ---------------------------------------------------------------------------
#
# Documented ahrs_config_t defaults of the watchdog (zero field -> default):
# once restart_warmup_sec (10 s) has elapsed since init, a reported roll or
# pitch 1-sigma above 10 deg, or an AHRS yaw 1-sigma above 90 deg, makes the
# instance uninitialized (attitude accessors fail). ARS has no yaw threshold.
# A negative threshold leaves that axis unchecked; precision_restart_disable
# turns the watchdog off. The suite re-bootstraps on its next suitable epoch;
# a standalone caller must re-init.
_P1_WARMUP_S = 10.0
_P1_RP_RAD = math.radians(10.0)
_P1_YAW_RAD = math.radians(90.0)
# Float tolerance on "exceeds": a reported 1-sigma a hair above a threshold
# is float rounding of the same number, not an implausibly large one.
_P1_REL_TOL = 1.0e-4
# Watchdog streams run at 10 Hz: every epoch is well inside the 0.2 s
# forward-gap limit, so integration and covariance propagation are normal.
_P1_HZ = 10
# One epoch either side of the predicted trip: a check made before or after
# that epoch's fusion step, and float rounding of the warm-up boundary.
_P1_EPOCH_US = 1_000_000 // _P1_HZ


def _rp_1sigma(std):
    """Largest roll/pitch 1-sigma. ARS does not measurement-correct yaw."""
    return max(abs(std[0]), abs(std[1]))


def _reported_sigma(snap, read_std, reduce):
    """Reported attitude 1-sigma, or None when that snapshot did not report one."""
    std_ok, std = read_std(snap)
    if not std_ok or std is None:
        return None
    return reduce(std)


def _assert_short_omission_publishes(snaps, t0, t1, published, read_std, reduce, t_boot, what):
    """A short omission inside the warm-up keeps publishing and reporting 1-sigma.

    The watchdog is not checked before the warm-up has elapsed, so every
    snapshot of the omission window must stay published, whatever its
    1-sigma. No comparison against an earlier report can excuse a failure.
    """
    assert (t1 - t_boot) / 1e6 < _P1_WARMUP_S - 1.0, (
        f"{what}: scenario error, short omission is not inside the warm-up"
    )
    window = [s for s in snaps if t0 < s.t_us <= t1]
    assert window, f"{what}: short omission produced no snapshot"
    sigmas = []
    for snap in window:
        assert published(snap), (
            f"{what}: accessors failed at t={snap.t_us / 1e6} s during a short "
            "omission inside the watchdog warm-up"
        )
        sig = _reported_sigma(snap, read_std, reduce)
        assert sig is not None, (
            f"{what}: published attitude reported no 1-sigma during the short omission"
        )
        sigmas.append(sig)
    return max(sigmas)


def _p1_ratio(std, *, rp_thr, yaw_thr):
    """Largest reported 1-sigma as a fraction of its threshold (unchecked axes skipped)."""
    ratios = [0.0]
    if rp_thr > 0.0:
        ratios.append(_rp_1sigma(std) / rp_thr)
    if yaw_thr > 0.0:
        ratios.append(abs(std[2]) / yaw_thr)
    return max(ratios)


def _p1_trip_time(times, sigma_at, t_init, *, rp_thr, yaw_thr, warmup_s):
    """First epoch whose reported 1-sigma P1 says ends publication, or None.

    ``sigma_at`` maps an epoch time to the 1-sigma a watchdog-off twin of the
    same bytes reported there.
    """
    for t in times:
        if (t - t_init) / 1e6 < warmup_s:
            continue
        if _p1_ratio(sigma_at[t], rp_thr=rp_thr, yaw_thr=yaw_thr) > 1.0 + _P1_REL_TOL:
            return t
    return None


def _assert_trip(run, times, t_trip, what):
    """Published before ``t_trip`` and unpublished from just after it to the end.

    ``t_trip`` None means P1 never ends publication on this stream. One epoch
    either side of the trip is not scored. A standalone instance has no
    re-init in ``times``, so "to the end" includes later magnetometer epochs.
    """
    by_t = {s.t_us: s for s in run.snaps}
    missing = [t for t in times if t not in by_t]
    assert not missing, f"{what}: no snapshot at t={missing[0] / 1e6} s"
    for t in times:
        snap = by_t[t]
        pub = snap.rpy_ok and snap.att is not None
        if t_trip is None or t < t_trip - _P1_EPOCH_US:
            assert pub, (
                f"{what}: accessors failed at t={t / 1e6} s although no reported "
                "1-sigma had exceeded its threshold after the warm-up"
            )
        elif t > t_trip + _P1_EPOCH_US:
            assert not pub, (
                f"{what}: still publishing at t={t / 1e6} s after the reported "
                f"1-sigma exceeded its threshold at t={t_trip / 1e6} s "
                "(a standalone instance stays unpublished until re-init)"
            )


def _suite_yaw_stream(acc, gyr, mag, out_s):
    settle = suite_imu_stream(duration_s=4.0, acc=acc, gyr=gyr, mag=mag, imu_hz=_P1_HZ)
    short = suite_imu_stream(
        duration_s=0.5, acc=acc, gyr=gyr, mag=None, t0_us=settle[-1].t_us, imu_hz=_P1_HZ
    )
    long_ = suite_imu_stream(
        duration_s=out_s, acc=acc, gyr=gyr, mag=None, t0_us=short[-1].t_us, imu_hz=_P1_HZ
    )
    back = suite_imu_stream(
        duration_s=0.5, acc=acc, gyr=gyr, mag=mag, t0_us=long_[-1].t_us, imu_hz=_P1_HZ
    )
    marks = {
        "boot": settle[0].t_us,
        "pre": settle[-1].t_us,
        "short": short[-1].t_us,
        "back": back[0].t_us,
    }
    return [*settle, *short, *long_, *back], marks


def _assert_suite_ahrs_yaw_grows_below_threshold(run, marks, pre_sigma, what):
    """Suite AHRS on a magnetometer outage too short to reach the 90 deg default.

    The reported yaw 1-sigma grows through the outage (clearly above its
    pre-outage value), every outage epoch keeps publishing while that
    1-sigma stays below its threshold, and the returning magnetometer epoch
    publishes.
    """
    t_short, t_back = marks["short"], marks["back"]

    def pub(s):
        return s.ahrs_ok and s.ahrs_att is not None

    outage = [s for s in run.snaps if t_short < s.t_us < t_back]
    assert outage, f"{what}: no snapshot during the magnetometer outage"
    dropped = [s for s in outage if not pub(s)]
    assert not dropped, (
        f"{what}: stopped publishing at t={dropped[0].t_us / 1e6} s while the "
        "reported 1-sigma had not reached its threshold"
    )
    last = outage[-1]
    assert last.ahrs_std_ok and last.ahrs_std is not None, (
        f"{what}: no 1-sigma reported at the end of the magnetometer outage"
    )
    ratio = _p1_ratio(last.ahrs_std, rp_thr=_P1_RP_RAD, yaw_thr=_P1_YAW_RAD)
    assert ratio <= 1.0 + _P1_REL_TOL, (
        f"{what}: kept publishing with 1-sigma "
        f"{[round(math.degrees(v), 3) for v in last.ahrs_std]} deg above the "
        "10/10/90 deg default thresholds"
    )
    s_end = abs(last.ahrs_std[2])
    print(
        f"{what}: yaw 1-sigma pre={math.degrees(pre_sigma)} deg "
        f"end of outage={math.degrees(s_end)} deg",
        flush=True,
    )
    assert s_end > 1.25 * pre_sigma, (
        f"{what}: yaw 1-sigma did not grow during the magnetometer outage "
        f"({math.degrees(pre_sigma)} -> {math.degrees(s_end)} deg)"
    )
    back = [s for s in run.snaps if s.t_us >= t_back]
    assert back and pub(back[0]), (
        f"{what}: suite AHRS did not publish on the returning magnetometer sample"
    )


def _assert_suite_ahrs_p1(run, marks, what):
    """Suite AHRS under the default watchdog on a long magnetometer outage.

    Published through the warm-up; after it, never publishes a 1-sigma above
    its threshold; stops publishing once the reported 1-sigma reaches that
    threshold (not earlier); stays unpublished while no magnetometer arrives;
    publishes again on the next magnetometer epoch without a caller re-init.
    """
    t_boot, t_short, t_back = marks["boot"], marks["short"], marks["back"]

    def pub(s):
        return s.ahrs_ok and s.ahrs_att is not None

    first = [s for s in run.snaps if s.t_us == t_boot]
    assert first and pub(first[0]), f"{what}: suite AHRS did not start on the first magnetometer sample"
    live = [s for s in run.snaps if t_boot <= s.t_us < t_back]
    for s in live:
        if not pub(s):
            continue
        assert s.ahrs_std_ok and s.ahrs_std is not None, (
            f"{what}: published attitude reported no 1-sigma at t={s.t_us / 1e6} s"
        )
        if (s.t_us - t_boot) / 1e6 >= _P1_WARMUP_S + _P1_EPOCH_US / 1e6:
            ratio = _p1_ratio(s.ahrs_std, rp_thr=_P1_RP_RAD, yaw_thr=_P1_YAW_RAD)
            assert ratio <= 1.0 + _P1_REL_TOL, (
                f"{what}: kept publishing at t={s.t_us / 1e6} s with 1-sigma "
                f"{[round(math.degrees(v), 3) for v in s.ahrs_std]} deg above the "
                "10/10/90 deg default thresholds after the warm-up"
            )
    fails = [s for s in live if s.t_us > t_short and not pub(s)]
    pubs = [s for s in live if pub(s)]
    last_sig = pubs[-1].ahrs_std if pubs else None
    assert fails, (
        f"{what}: suite AHRS never stopped publishing during the magnetometer "
        f"outage (last reported 1-sigma {last_sig})"
    )
    t_fail = fails[0].t_us
    early = [s for s in live if s.t_us < t_fail]
    assert all(pub(s) for s in early), (
        f"{what}: suite AHRS stopped publishing before t={t_fail / 1e6} s and came back "
        "without a magnetometer epoch"
    )
    tail = early[-20:]
    ratios = [_p1_ratio(s.ahrs_std, rp_thr=_P1_RP_RAD, yaw_thr=_P1_YAW_RAD) for s in tail]
    step = max([b - a for a, b in zip(ratios, ratios[1:])] + [0.0])
    print(
        f"{what}: first unpublished t={t_fail / 1e6} s last published 1-sigma="
        f"{[round(math.degrees(v), 3) for v in tail[-1].ahrs_std]} deg "
        f"ratio={ratios[-1]} step={step}",
        flush=True,
    )
    # The trip belongs to the threshold: the last published 1-sigma is within
    # a few epochs' growth of it. An earlier stop is not this watchdog.
    assert ratios[-1] >= 1.0 - 3.0 * step - 0.01, (
        f"{what}: accessors failed at t={t_fail / 1e6} s while the reported "
        f"1-sigma was {ratios[-1]:.3f} of its threshold"
    )
    stuck = [s for s in live if s.t_us >= t_fail and pub(s)]
    assert not stuck, (
        f"{what}: suite AHRS published again at t={stuck[0].t_us / 1e6} s without "
        "a magnetometer epoch"
    )
    back = [s for s in run.snaps if s.t_us >= t_back]
    assert back and pub(back[0]), (
        f"{what}: suite AHRS did not publish again on the next magnetometer "
        "sample without a caller re-init"
    )
    assert back[0].ahrs_std_ok and back[0].ahrs_std is not None
    assert _p1_ratio(back[0].ahrs_std, rp_thr=_P1_RP_RAD, yaw_thr=_P1_YAW_RAD) <= 1.0 + _P1_REL_TOL, (
        f"{what}: re-bootstrapped AHRS published a 1-sigma above its threshold"
    )
    return t_fail


def test_suite_rebootstrap_after_uninitialized():
    """accessors fail once a reported 1-sigma exceeds its threshold.

    First-start arms stay: suite ARS on the first valid IMU, suite AHRS once
    a magnetometer sample has been seen. Inside the watchdog warm-up a short
    omission, a specific-force stretch far from g that only withholds
    leveling, and a wide initial roll/pitch standard deviation keep
    publishing. After the warm-up, a published attitude never carries a
    1-sigma above its documented threshold (10 deg roll/pitch, 90 deg AHRS
    yaw, or the explicit ahrs_config_t value): once the reported 1-sigma
    crosses it, accessors fail. The suite publishes again on the next
    magnetometer epoch without the caller re-initing; a standalone instance
    stays unpublished until the caller re-inits. The crossing time is read
    from this implementation's own reported 1-sigma (a watchdog-off twin of
    the same bytes), so no noise tuning is assumed. A dropped epoch, skipped
    fusion, and a far-from-g sample after the warm-up keep publishing. A
    finite specific-force sample marked not a sample stays on the
    measurement bundle; a non-finite accelerometer is the drop, not that
    contrast.
    """
    lat, lon, h = _suite_site()
    mag = body_mag_for_yaw(0.0, 0.0, runtime_att_yaw_rad(), (20.0, 0.0, 40.0))
    first = suite_imu_stream(duration_s=1.0, acc=SPECIFIC_FORCE_LEVEL, mag=mag)
    scen = SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=first)
    t_first = first[0].t_us
    for run, name in ((c_suite_run(scen), "C"), (py_suite_run(scen), "Python")):
        assert run.init_ok, f"{name} suite init failed"
        at_first = [s for s in run.snaps if s.t_us == t_first]
        assert at_first, f"{name}: missing first-bootstrap snapshot"
        print(
            f"{name} first-start: ars={at_first[0].ars_ok} ahrs={at_first[0].ahrs_ok}",
            flush=True,
        )
        assert at_first[0].ars_ok and at_first[0].ars_att is not None, (
            f"{name}: suite ARS did not publish on the first suitable IMU"
        )
        assert at_first[0].ahrs_ok and at_first[0].ahrs_att is not None, (
            f"{name}: suite AHRS did not publish on the first magnetometer sample"
        )

    acc = SPECIFIC_FORCE_LEVEL
    gyr_still = (0.0, 0.0, 0.0)
    far = (0.0, 0.0, -3.0 * G_MPS2)

    def _suite_ars_std(snap):
        return snap.ars_std_ok, snap.ars_std

    def _suite_ahrs_std(snap):
        return snap.ahrs_std_ok, snap.ahrs_std

    def _att_std(snap):
        return snap.std_ok, snap.att_std

    def _pre_sigma(snaps, t_cut, published, read_std, reduce, what):
        before = [s for s in snaps if 0 < s.t_us <= t_cut and published(s)]
        assert before, f"{what}: nothing was published before the outage"
        sig = _reported_sigma(before[-1], read_std, reduce)
        assert sig is not None and sig > 0.0, (
            f"{what}: no attitude 1-sigma on the last pre-outage publication"
        )
        return sig

    def _finish_when_sigma_stays(snaps, t_after, published, what):
        """Far-from-g inside the warm-up only withholds leveling: accessors stay up."""
        tail = [s for s in snaps if s.t_us > t_after]
        assert tail, f"{what}: far-from-g withhold produced no snapshot"
        assert tail[-1].t_us / 1e6 < _P1_WARMUP_S - 1.0, (
            f"{what}: scenario error, far-from-g stretch is not inside the warm-up"
        )
        assert all(published(s) for s in tail), (
            f"{what}: a far-from-g sample that only withholds leveling "
            "failed attitude accessors"
        )

    # Roll/pitch carve-out. A level settle publishes a reduced 1-sigma.
    # A short accelerometer omission inside the warm-up keeps publishing.
    # A far-from-g stretch only withholds leveling: accessors stay up for
    # the whole stretch, and that withhold is not the fail-then-recover
    # contrast. The omission is an accelerometer marked not a sample. The
    # published navigator push cannot do that, so the Python epochs that run
    # are the finite specific-force samples only. A non-finite accelerometer
    # is not this omission and is not the withheld-finite contrast below.
    settle = suite_imu_stream(duration_s=0.4, acc=acc, gyr=gyr_still, imu_hz=20)
    omitted = suite_imu_stream(
        duration_s=0.4, acc=None, gyr=gyr_still, t0_us=settle[-1].t_us, imu_hz=20
    )
    withheld = suite_imu_stream(
        duration_s=4.0, acc=far, gyr=gyr_still, t0_us=omitted[-1].t_us, imu_hz=10
    )
    t_pre = settle[-1].t_us
    t_omit_end = omitted[-1].t_us
    c_ars = SuiteScenario(
        lat_deg=lat, lon_deg=lon, h_m=h, epochs=[*settle, *omitted, *withheld],
    )
    py_far = suite_imu_stream(
        duration_s=4.0, acc=far, gyr=gyr_still, t0_us=settle[-1].t_us, imu_hz=10,
    )
    py_ars = SuiteScenario(
        lat_deg=lat, lon_deg=lon, h_m=h, epochs=[*settle, *py_far],
    )
    assert all(
        e.acc_valid and all(math.isfinite(v) for v in e.acc) for e in py_ars.epochs
    ), "Python suite epoch that runs has no finite specific-force sample"
    c_run = c_suite_run(c_ars)
    assert c_run.init_ok, "C suite init failed"
    pre = _pre_sigma(
        c_run.snaps, t_pre, lambda s: s.ars_ok, _suite_ars_std, _rp_1sigma, "C ARS"
    )
    _assert_short_omission_publishes(
        c_run.snaps, t_pre, t_omit_end, lambda s: s.ars_ok,
        _suite_ars_std, _rp_1sigma, settle[0].t_us, "C ARS accelerometer omission",
    )
    _finish_when_sigma_stays(
        c_run.snaps, t_omit_end, lambda s: s.ars_ok, "C ARS far-from-g"
    )
    print(f"C ARS far-from-g kept publishing pre={math.degrees(pre)}", flush=True)
    py_run = py_suite_run(py_ars)
    assert py_run.init_ok, "Python suite init failed"
    pre = _pre_sigma(
        py_run.snaps, t_pre, lambda s: s.ars_ok, _suite_ars_std, _rp_1sigma,
        "Python ARS",
    )
    _finish_when_sigma_stays(
        py_run.snaps, t_pre, lambda s: s.ars_ok, "Python ARS far-from-g"
    )
    print(f"Python ARS far-from-g kept publishing pre={math.degrees(pre)}", flush=True)

    # Same finite tilt on both arms. The withheld arm marks the accelerometer
    # as not a sample while the triple stays in the measurement bundle. The
    # delivered arm consumes that triple. The withheld arm still emits a
    # snapshot, and its roll/pitch stay nearer the pre-stretch attitude.
    # Skipping the attitude step and keeping the last publication is the
    # pass. A non-finite accelerometer is not this arm: the published
    # navigator push cannot mark a finite triple as not a sample.
    tilt_acc = still_level_acc(0.0, runtime_tilt_rad())
    assert all(math.isfinite(v) for v in tilt_acc), "withheld tilt is not finite"
    tilt_base = suite_imu_stream(duration_s=0.4, acc=acc, gyr=gyr_still, imu_hz=20)
    tilt_present = suite_imu_stream(
        duration_s=2.0, acc=tilt_acc, gyr=gyr_still,
        t0_us=tilt_base[-1].t_us, imu_hz=20,
    )
    tilt_omitted = suite_imu_stream(
        duration_s=2.0, acc=tilt_acc, gyr=gyr_still,
        t0_us=tilt_base[-1].t_us, imu_hz=20,
    )
    for epoch in tilt_omitted:
        epoch.acc_valid = False
    assert all(
        (not e.acc_valid) and e.acc == tilt_acc and all(math.isfinite(v) for v in e.acc)
        for e in tilt_omitted
    ), "withheld arm is not a finite triple marked not a sample"
    assert all(e.acc_valid and e.acc == tilt_acc for e in tilt_present), (
        "delivered arm did not keep the same finite specific-force sample"
    )
    t_tilt_pre = tilt_base[-1].t_us

    def _rp_moved(att, pre):
        return abs(angle_diff_rad(att[0], pre[0])) + abs(angle_diff_rad(att[1], pre[1]))

    omitted_run = c_suite_run(
        SuiteScenario(
            lat_deg=lat, lon_deg=lon, h_m=h, epochs=[*tilt_base, *tilt_omitted],
        )
    )
    present_run = c_suite_run(
        SuiteScenario(
            lat_deg=lat, lon_deg=lon, h_m=h, epochs=[*tilt_base, *tilt_present],
        )
    )
    assert omitted_run.init_ok and present_run.init_ok, "C suite init failed"
    omit_times = [e.t_us for e in tilt_omitted]
    by_om = {s.t_us: s for s in omitted_run.snaps}
    by_pr = {s.t_us: s for s in present_run.snaps}
    missing = [t for t in omit_times if t not in by_om]
    assert not missing, (
        "gyro epoch with the accelerometer withheld did not emit a snapshot"
    )
    assert all(
        by_om[t].ars_ok and by_om[t].ars_att is not None for t in omit_times
    ), (
        "gyro epoch with the accelerometer withheld dropped the published attitude"
    )
    assert t_tilt_pre in by_om and t_tilt_pre in by_pr, (
        "missing the attitude published before the tilt stretch"
    )
    pre_om = by_om[t_tilt_pre]
    pre_pr = by_pr[t_tilt_pre]
    present = by_pr[tilt_present[-1].t_us]
    assert (
        pre_om.ars_ok and pre_om.ars_att is not None
        and pre_pr.ars_ok and pre_pr.ars_att is not None
        and present.ars_ok and present.ars_att is not None
    ), "tilt contrast published no roll/pitch"
    moved_om = _rp_moved(by_om[omit_times[-1]].ars_att, pre_om.ars_att)
    moved_pr = _rp_moved(present.ars_att, pre_pr.ars_att)
    print(
        f"C withheld-acc moved={math.degrees(moved_om)} "
        f"present={math.degrees(moved_pr)}",
        flush=True,
    )
    assert moved_pr > moved_om, (
        "withheld finite specific-force sample was treated as present"
    )

    # Suite AHRS yaw under the default watchdog. Magnetometer present long
    # enough to publish a reduced yaw 1-sigma, a short omission inside the
    # warm-up, then a magnetometer outage during a steady turn (10 Hz, no
    # forward gaps) until the reported yaw 1-sigma crosses the documented
    # 90 deg default, then the magnetometer returns. The outage length is
    # read from this implementation's own reported 1-sigma growth: when the
    # first run ends below the threshold, the outage is extended by a
    # conservative (variance-linear) extrapolation of that growth. The PRD
    # does not fix how fast yaw 1-sigma grows (default gyro noise is not
    # documented), so when the extrapolated crossing lies beyond what a test
    # run can replay, only the parts that hold at any growth rate are
    # checked: the yaw 1-sigma grows through the outage, and the accessors
    # keep publishing while it stays below the threshold.
    gyr_turn = (0.0, 0.0, runtime_z_rate_rps())
    out_budget_s = 3600.0
    out_s = 600.0
    c_yaw = None
    marks = None
    epochs = None
    crossing_replayed = True
    for _attempt in range(3):
        epochs, marks = _suite_yaw_stream(acc, gyr_turn, mag, out_s)
        c_yaw = c_suite_run(SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=epochs))
        assert c_yaw.init_ok, "C suite init failed"
        outage = [s for s in c_yaw.snaps if marks["short"] < s.t_us < marks["back"]]
        if any(not s.ahrs_ok for s in outage):
            break
        pubs = [
            (s.t_us, abs(s.ahrs_std[2]))
            for s in outage
            if s.ahrs_ok and s.ahrs_std_ok and s.ahrs_std is not None
        ]
        assert len(pubs) >= 4, "C suite AHRS reported no yaw 1-sigma during the outage"
        t_mid, s_mid = pubs[len(pubs) // 2]
        t_end, s_end = pubs[-1]
        rate = (s_end * s_end - s_mid * s_mid) / ((t_end - t_mid) / 1e6)
        print(
            f"C suite AHRS outage {out_s} s ended published: yaw 1-sigma "
            f"{math.degrees(s_end)} deg, variance rate {rate}",
            flush=True,
        )
        assert rate > 0.0, (
            "C suite AHRS yaw 1-sigma did not grow during a magnetometer outage"
        )
        need = (_P1_YAW_RAD * _P1_YAW_RAD - s_end * s_end) / rate
        next_out_s = out_s + 1.3 * need + 30.0
        if next_out_s > out_budget_s:
            print(
                f"C suite AHRS 90 deg crossing extrapolated at {next_out_s} s of "
                f"outage, beyond the {out_budget_s} s replay budget",
                flush=True,
            )
            crossing_replayed = False
            break
        out_s = next_out_s
    py_yaw = py_suite_run(SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=epochs))
    assert py_yaw.init_ok, "Python suite init failed"
    if crossing_replayed:
        t_fail_c = _assert_suite_ahrs_p1(c_yaw, marks, "C suite AHRS")
        t_fail_py = _assert_suite_ahrs_p1(py_yaw, marks, "Python suite AHRS")
    for run, name in ((c_yaw, "C"), (py_yaw, "Python")):
        pre = _pre_sigma(
            run.snaps, marks["pre"], lambda s: s.ahrs_ok, _suite_ahrs_std,
            lambda std: abs(std[2]), f"{name} AHRS",
        )
        short_sig = _assert_short_omission_publishes(
            run.snaps, marks["pre"], marks["short"], lambda s: s.ahrs_ok,
            _suite_ahrs_std, lambda std: abs(std[2]), marks["boot"],
            f"{name} AHRS short magnetometer omission",
        )
        print(
            f"{name} AHRS pre={math.degrees(pre)} short={math.degrees(short_sig)} "
            f"outage={out_s} s",
            flush=True,
        )
        if not crossing_replayed:
            _assert_suite_ahrs_yaw_grows_below_threshold(run, marks, pre, f"{name} suite AHRS")
    if crossing_replayed:
        print(f"suite AHRS trip C={t_fail_c / 1e6} s Python={t_fail_py / 1e6} s", flush=True)

    # AHRS roll/pitch. Far-from-g only withholds leveling: accessors stay
    # up for the whole stretch. That withhold is not the fail-then-recover.
    ahrs_settle = suite_imu_stream(
        duration_s=0.4, acc=acc, gyr=gyr_still, mag=mag, imu_hz=20
    )
    ahrs_withheld = suite_imu_stream(
        duration_s=4.0, acc=far, gyr=gyr_still, mag=mag,
        t0_us=ahrs_settle[-1].t_us, imu_hz=10,
    )
    t_ahrs_pre = ahrs_settle[-1].t_us
    ahrs_scen = SuiteScenario(
        lat_deg=lat, lon_deg=lon, h_m=h,
        epochs=[*ahrs_settle, *ahrs_withheld],
    )
    for run, name in ((c_suite_run(ahrs_scen), "C"), (py_suite_run(ahrs_scen), "Python")):
        assert run.init_ok, f"{name} suite init failed"
        pre = _pre_sigma(
            run.snaps, t_ahrs_pre, lambda s: s.ahrs_ok, _suite_ahrs_std, _rp_1sigma,
            f"{name} AHRS roll/pitch",
        )
        _finish_when_sigma_stays(
            run.snaps, t_ahrs_pre, lambda s: s.ahrs_ok, f"{name} AHRS far-from-g"
        )
        print(f"{name} AHRS far-from-g kept publishing pre={math.degrees(pre)}", flush=True)

    # Standalone roll/pitch. Far-from-g after a reduced solution only
    # withholds leveling, so accessors stay up. That withhold is not the
    # implausibly-large 1-sigma outage, including when the initial
    # roll/pitch standard deviation was left wide. Watchdog at its defaults.
    std_ars = ars_std()
    st = att_hold(t0_us=0, duration_s=0.4, acc=acc, gyr=gyr_still, imu_hz=20)
    wh = att_hold(t0_us=st[-1].t_us, duration_s=4.0, acc=far, gyr=gyr_still, imu_hz=10)
    carve_ars = c_att_run(_ars(std=std_ars, cmds=[*st, *wh], restart_disable=False))
    pre = _pre_sigma(
        carve_ars.snaps, st[-1].t_us, lambda s: s.rpy_ok, _att_std, _rp_1sigma,
        "standalone ARS",
    )
    _finish_when_sigma_stays(
        carve_ars.snaps, st[-1].t_us, lambda s: s.rpy_ok, "standalone ARS far-from-g"
    )
    print(f"standalone ARS far-from-g kept publishing pre={math.degrees(pre)}", flush=True)

    wide = (4.0 * MANDATORY_STD_RAD, 4.0 * MANDATORY_STD_RAD, 0.0)
    wide_level = att_hold(t0_us=0, duration_s=0.4, acc=acc, gyr=gyr_still, imu_hz=20)
    wide_far = att_hold(
        t0_us=wide_level[-1].t_us, duration_s=4.0, acc=far, gyr=gyr_still, imu_hz=10
    )
    wide_run = c_att_run(_ars(std=wide, cmds=[*wide_level, *wide_far], restart_disable=False))
    _finish_when_sigma_stays(
        wide_run.snaps, wide_level[-1].t_us, lambda s: s.rpy_ok,
        "standalone ARS wide far-from-g",
    )
    print("standalone ARS wide far-from-g kept publishing", flush=True)
    reinit_ars = c_att_run(
        _ars(
            std=std_ars,
            cmds=att_hold(t0_us=0, duration_s=0.4, acc=acc, gyr=gyr_still, imu_hz=20),
            restart_disable=False,
        )
    )
    _assert_init_ok(reinit_ars, "standalone ARS re-init")
    require_att(reinit_ars.last(), "standalone ARS re-init")

    # ARS has no yaw threshold: a near-zero yaw threshold on an ARS instance
    # past the warm-up, with roll/pitch leveled, keeps publishing.
    ars_long = att_hold(
        t0_us=0, duration_s=_P1_WARMUP_S + 3.0, acc=acc, gyr=gyr_turn, imu_hz=_P1_HZ
    )
    ars_yaw_thr = c_att_run(
        _ars(
            std=std_ars, cmds=ars_long, restart_disable=False,
            restart_att_std=(0.0, 0.0, 1.0e-6),
        )
    )
    ars_ref = c_att_run(_ars(std=std_ars, cmds=ars_long, restart_disable=True))
    _assert_init_ok(ars_ref, "standalone ARS watchdog off")
    ars_sig = {s.t_us: s.att_std for s in ars_ref.snaps if s.std_ok and s.att_std is not None}
    ars_times = [c.t_us for c in ars_long]
    assert all(t in ars_sig for t in ars_times), "standalone ARS reported no 1-sigma"
    _assert_trip(
        ars_yaw_thr, ars_times,
        _p1_trip_time(ars_times, ars_sig, 0, rp_thr=_P1_RP_RAD, yaw_thr=0.0, warmup_s=_P1_WARMUP_S),
        "standalone ARS with a near-zero yaw threshold",
    )

    # Standalone AHRS yaw. The same magnetometer-then-outage stream is run
    # with the watchdog off (the reference 1-sigma of these bytes), with an
    # explicit yaw threshold the reference crosses mid-outage, at the
    # documented defaults, and with a threshold below every reported yaw
    # 1-sigma (explicit and default warm-up). Each armed run must publish
    # until the reference 1-sigma crosses its threshold after the warm-up,
    # then stay unpublished, including over the later magnetometer epochs:
    # a standalone caller must re-init.
    std_ahrs = ahrs_std()
    ah_on = att_hold(t0_us=0, duration_s=4.0, acc=acc, gyr=gyr_turn, mag=mag, imu_hz=_P1_HZ)
    ah_off = att_hold(
        t0_us=ah_on[-1].t_us, duration_s=120.0, acc=acc, gyr=gyr_turn, mag=None, imu_hz=_P1_HZ
    )
    ah_back = att_hold(
        t0_us=ah_off[-1].t_us, duration_s=0.5, acc=acc, gyr=gyr_turn, mag=mag, imu_hz=_P1_HZ
    )
    yaw_cmds = [*ah_on, *ah_off, *ah_back]
    yaw_times = [c.t_us for c in yaw_cmds]
    off_times = [c.t_us for c in ah_off]
    ref = c_att_run(_ahrs(std=std_ahrs, cmds=yaw_cmds, restart_disable=True))
    _assert_init_ok(ref, "standalone AHRS watchdog off")
    ref_by_t = {s.t_us: s for s in ref.snaps}
    assert all(
        t in ref_by_t and ref_by_t[t].rpy_ok and ref_by_t[t].std_ok
        and ref_by_t[t].att_std is not None
        for t in yaw_times
    ), "precision_restart_disable: standalone AHRS stopped publishing attitude or 1-sigma"
    sig = {t: ref_by_t[t].att_std for t in yaw_times}
    y_start = abs(sig[off_times[0]][2])
    y_end = abs(sig[off_times[-1]][2])
    print(
        f"standalone AHRS reference yaw 1-sigma outage start={math.degrees(y_start)} "
        f"end={math.degrees(y_end)} deg",
        flush=True,
    )
    assert y_end > y_start * (1.0 + 2.0e-3), (
        "a withheld magnetometer left the reported yaw 1-sigma from growing"
    )
    # Explicit yaw threshold crossed mid-outage (roll/pitch unchecked).
    t_lo = max(int((_P1_WARMUP_S + 1.0) * 1e6), off_times[0] + 1_000_000)
    t_hi = off_times[-1] - 1_000_000
    t_x = t_lo + (t_hi - t_lo) // 2
    k_t = next(t for t in off_times if t >= t_x)
    s_k = abs(sig[k_t][2])
    j_t = next(
        (t for t in off_times if t > k_t and abs(sig[t][2]) > s_k * (1.0 + 2.0e-3)), None
    )
    assert j_t is not None, "reference yaw 1-sigma stopped growing in the second half of the outage"
    thr = 0.5 * (s_k + abs(sig[j_t][2]))
    armed = c_att_run(
        _ahrs(
            std=std_ahrs, cmds=yaw_cmds, restart_disable=False,
            restart_att_std=(-1.0, -1.0, thr),
        )
    )
    assert armed.init_ok, "standalone AHRS explicit yaw threshold: init was refused"
    t_thr = _p1_trip_time(yaw_times, sig, 0, rp_thr=0.0, yaw_thr=thr, warmup_s=_P1_WARMUP_S)
    assert t_thr is not None
    print(
        f"standalone AHRS explicit threshold {math.degrees(thr)} deg crossed at "
        f"t={t_thr / 1e6} s",
        flush=True,
    )
    _assert_trip(armed, yaw_times, t_thr, "standalone AHRS explicit yaw threshold")

    # Documented defaults (all watchdog fields zero).
    dflt = c_att_run(_ahrs(std=std_ahrs, cmds=yaw_cmds, restart_disable=False))
    assert dflt.init_ok, "standalone AHRS default watchdog: init was refused"
    # A short magnetometer omission inside the warm-up keeps publishing.
    short_sig = _assert_short_omission_publishes(
        dflt.snaps, ah_on[-1].t_us, ah_on[-1].t_us + 500_000, lambda s: s.rpy_ok,
        _att_std, lambda std: abs(std[2]), 0, "standalone AHRS short magnetometer omission",
    )
    print(f"standalone AHRS short omission 1-sigma={math.degrees(short_sig)}", flush=True)
    t_dflt = _p1_trip_time(
        yaw_times, sig, 0, rp_thr=_P1_RP_RAD, yaw_thr=_P1_YAW_RAD, warmup_s=_P1_WARMUP_S
    )
    print(
        f"standalone AHRS default watchdog trip={None if t_dflt is None else t_dflt / 1e6}",
        flush=True,
    )
    _assert_trip(dflt, yaw_times, t_dflt, "standalone AHRS default watchdog")

    # Warm-up: a yaw threshold below every reported yaw 1-sigma trips on the
    # first epoch once the warm-up has elapsed, not before.
    tiny = 0.5 * min(abs(sig[t][2]) for t in yaw_times)
    for warm, label in ((3.0, "explicit 3 s"), (0.0, "default")):
        span_s = (warm if warm > 0.0 else _P1_WARMUP_S) + 3.0
        w_cmds = [c for c in yaw_cmds if c.t_us <= int(span_s * 1e6)]
        w_times = [c.t_us for c in w_cmds]
        w_run = c_att_run(
            _ahrs(
                std=std_ahrs, cmds=w_cmds, restart_disable=False,
                restart_att_std=(-1.0, -1.0, tiny), restart_warmup_s=warm,
            )
        )
        assert w_run.init_ok, f"standalone AHRS warm-up {label}: init was refused"
        t_w = _p1_trip_time(
            w_times, sig, 0, rp_thr=0.0, yaw_thr=tiny,
            warmup_s=warm if warm > 0.0 else _P1_WARMUP_S,
        )
        assert t_w is not None
        _assert_trip(w_run, w_times, t_w, f"standalone AHRS warm-up {label}")

    ah_level = att_hold(t0_us=0, duration_s=0.4, acc=acc, gyr=gyr_still, mag=mag, imu_hz=20)
    ah_far = att_hold(
        t0_us=ah_level[-1].t_us, duration_s=4.0, acc=far, gyr=gyr_still, mag=mag, imu_hz=10
    )
    carve_ahrs = c_att_run(
        _ahrs(std=std_ahrs, cmds=[*ah_level, *ah_far], restart_disable=False)
    )
    pre = _pre_sigma(
        carve_ahrs.snaps, ah_level[-1].t_us, lambda s: s.rpy_ok, _att_std, _rp_1sigma,
        "standalone AHRS roll/pitch",
    )
    _finish_when_sigma_stays(
        carve_ahrs.snaps, ah_level[-1].t_us, lambda s: s.rpy_ok,
        "standalone AHRS far-from-g",
    )
    print(f"standalone AHRS far-from-g kept publishing pre={math.degrees(pre)}", flush=True)
    wide_ahrs = (4.0 * MANDATORY_STD_RAD, 4.0 * MANDATORY_STD_RAD, MANDATORY_STD_RAD)
    wide_ah_level = att_hold(
        t0_us=0, duration_s=0.4, acc=acc, gyr=gyr_still, mag=mag, imu_hz=20
    )
    wide_ah_far = att_hold(
        t0_us=wide_ah_level[-1].t_us, duration_s=4.0, acc=far, gyr=gyr_still, mag=mag, imu_hz=10
    )
    wide_ah_run = c_att_run(
        _ahrs(std=wide_ahrs, cmds=[*wide_ah_level, *wide_ah_far], restart_disable=False)
    )
    _finish_when_sigma_stays(
        wide_ah_run.snaps, wide_ah_level[-1].t_us, lambda s: s.rpy_ok,
        "standalone AHRS wide far-from-g",
    )
    print("standalone AHRS wide far-from-g kept publishing", flush=True)
    reinit = c_att_run(
        _ahrs(
            std=std_ahrs,
            cmds=att_hold(t0_us=0, duration_s=0.5, acc=acc, gyr=gyr_still, mag=mag, imu_hz=20),
            restart_disable=False,
        )
    )
    _assert_init_ok(reinit, "standalone AHRS re-init")
    require_att(reinit.last(), "standalone AHRS re-init")

    # Carve-outs past the warm-up, watchdog at its defaults: a dropped epoch,
    # skipped magnetometer fusion, and one far-from-g sample that only
    # withholds leveling do not by themselves fail attitude accessors.
    settled = att_hold(
        t0_us=0, duration_s=12.0, acc=acc, gyr=gyr_still, imu_hz=20
    )
    dropped = AttCmd(
        tag="E",
        t_us=settled[-1].t_us + 50_000,
        acc=acc,
        gyr=(float("nan"), 0.0, 0.0),
    )
    drop_run = c_att_run(_ars(std=std_ars, cmds=[*settled, dropped], restart_disable=False))
    _assert_init_ok(drop_run, "dropped epoch")
    assert drop_run.last().rpy_ok, "a dropped epoch failed attitude accessors"
    far = AttCmd(
        tag="E",
        t_us=settled[-1].t_us + 50_000,
        acc=(0.0, 0.0, -3.0 * G_MPS2),
        gyr=gyr_still,
    )
    far_run = c_att_run(_ars(std=std_ars, cmds=[*settled, far], restart_disable=False))
    _assert_init_ok(far_run, "far-from-g sample")
    assert far_run.last().rpy_ok, (
        "a far-from-g sample that only withholds leveling failed attitude accessors"
    )
    mag_settled = att_hold(
        t0_us=0, duration_s=12.0, acc=acc, gyr=gyr_still, mag=mag, imu_hz=20
    )
    skipped = att_hold(
        t0_us=mag_settled[-1].t_us,
        duration_s=0.2,
        acc=acc,
        gyr=gyr_still,
        mag=(0.0, 0.0, 0.0),
        imu_hz=20,
    )
    skip_run = c_att_run(
        _ahrs(std=std_ahrs, cmds=[*mag_settled, *skipped], restart_disable=False)
    )
    _assert_init_ok(skip_run, "skipped magnetometer fusion")
    assert skip_run.last().rpy_ok, (
        "skipped magnetometer fusion failed attitude accessors"
    )


def test_published_attitude_snapshots_are_well_formed():
    """Published ARS / AHRS attitude, 1-sigma, gyro bias and velocity values
    are finite and the invalid-input counters are non-negative -- on every
    attitude and suite snapshot parsed in this session and on a suite run of
    its own. A violation fails this test only.
    """
    from _harness import require_no_product_issues

    lat, lon, h = _suite_site()
    mag = body_mag_for_yaw(0.0, 0.0, runtime_att_yaw_rad(), (20.0, 0.0, 40.0))
    epochs = suite_imu_stream(duration_s=2.0, acc=SPECIFIC_FORCE_LEVEL, mag=mag)
    scen = SuiteScenario(lat_deg=lat, lon_deg=lon, h_m=h, epochs=epochs)
    for run in (c_suite_run(scen), py_suite_run(scen)):
        assert run.init_ok and run.snaps, "suite run produced no snapshots"
    require_no_product_issues("F06", "attitude snapshots (F06)")
