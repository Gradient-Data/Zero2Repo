# feature: F08
"""Navigation suite and graceful degradation (FP-08).

Assertions stay at the PRD's precision: four distinguishable modes FULL /
COASTING / ATTITUDE_ONLY / NONE; the 2 s aiding-age split; a 3 s in-window
outage stays COASTING with attitude and local height; window expiry is
ATTITUDE_ONLY with frozen INS; the next fusion-usable fix is FULL on that
epoch; quality-loss unpublishes INS positions while attitude continues;
best attitude is INS when ready else AHRS else ARS, with ARS fallback yaw
equal to last-ready INS plus subsequent ARS change; local height is
continuous and the barometer is the outage-surviving reference when both
sources ran; ellipsoid height is refused until a real GNSS WGS84 anchor;
mocap owns NED by a constant offset (Δ in → Δ out); a static attitude hint
seeds INS until init and does not bias later re-acquisition; outlier
override and standstill from INS options reach the parallel filters.

Python mode names are the four named strings. C mode values are only
required to be pairwise different. Message text, exception types, C enum
integers, dead-reckoning millisecond fields, and offset-accessor spellings
are not pinned.
"""

from __future__ import annotations

import math

from F02_helpers import (
    ECEF_MATCH_M,
    GNSS_STD_M,
    HAPPY_DURATION_S,
    ecef_from_llh_deg,
    ecef_plus_ned,
    runtime_site,
)
from F03_helpers import CM_STD_M, G_MPS2, angle_diff_rad, runtime_tracker_ned, still_level_acc
from F05_helpers import EXIT_POS_BAD, FREEZE_11S, UNFUSABLE_POS_STD
from F06_helpers import runtime_att_yaw_rad, runtime_z_rate_rps
from F07_helpers import (
    runtime_climb_m,
    tropospheric_isa_altitude_m,
    tropospheric_isa_pressure_pa,
)
from F08_helpers import (
    ABSURD_NORTH_ACC,
    AIDING_EQUAL_S,
    AIDING_FULL_S,
    AIDING_JUST_OVER_S,
    ENTRY_VEL_STD,
    HINT_YAW_STD,
    MODE_ATTITUDE_ONLY,
    MODE_COASTING,
    MODE_FULL,
    MODE_NONE,
    OUTAGE_3S,
    QUALITY_LOSS_S,
    SPLIT_YAW_S,
    STILL_ACC_BOUND_MPS2,
    STILL_GYR_BOUND_RPS,
    STILL_VERT_ACC,
    STILL_Z_RATE_RPS,
    ZERO_VEL,
    NavScenario,
    c_nav_run,
    ecef_err_m,
    imu_only,
    imu_only_after_door,
    later_fix_ecef,
    mag_body,
    nav_append,
    nav_epoch,
    nav_langs,
    pad_full,
    py_mode,
    py_nav_run,
    require_ahrs_attitude,
    require_best_attitude,
    indoor_ellipsoid_matches_init_origin,
    require_ellipsoid,
    require_indoor_ellipsoid_not_init_origin,
    require_local_height,
    require_positions_fail,
    require_ready_full,
    require_unpublished_ellipsoid,
    runtime_mag_offset_rad,
    runtime_mocap_delta_m,
    runtime_second_site,
    site_nav,
    with_steps,
)


def _site():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    return lat, lon, h, origin


def _assert_py_mode(snap, name, what):
    got = py_mode(snap, what)
    print(f"{what}: mode_name={got} want={name} ready={snap.ready}", flush=True)
    assert got == name, f"{what}: mode_name {got!r} is not {name!r}"


def _assert_modes_pairwise_different(values, labels):
    for i, (a, la) in enumerate(zip(values, labels)):
        for b, lb in zip(values[i + 1 :], labels[i + 1 :]):
            assert a != b, f"C mode values for {la} and {lb} were not distinguishable ({a})"


# ---------------------------------------------------------------------------
# A. Python navigator pad FULL; skip-epoch NONE; read does not solve
# ---------------------------------------------------------------------------


def test_python_navigator_pad_reports_full_matching_fix():
    """100 Hz IMU + 1 Hz 2/2/2 m GNSS after dwell and 1.5 s ready is FULL."""
    for label, site in (("site-a", _site()), ("site-b", (*runtime_second_site(), None))):
        if site[3] is None:
            lat, lon, h = site[0], site[1], site[2]
            origin = ecef_from_llh_deg(lat, lon, h)
        else:
            lat, lon, h, origin = site
        epochs = pad_full(lat, lon, h, origin, baro=True, mag=True)
        pad_pa = tropospheric_isa_pressure_pa(h)
        isa_alt = tropospheric_isa_altitude_m(pad_pa)
        scen = site_nav(lat, lon, h, epochs)
        for kind, run in nav_langs(scen):
            assert run.init_ok, f"{kind} {label} init failed"
            last = run.last()
            print(
                f"{kind} {label} mode={last.mode} name={last.mode_name} "
                f"ready={last.ready} pos={last.pos_ok}",
                flush=True,
            )
            _assert_py_mode(last, MODE_FULL, f"{kind} {label} pad")
            require_ready_full(last, f"{kind} {label} pad")
            err = ecef_err_m(last.ecef, origin)
            print(f"{kind} {label} |ecef-fix|={err} m", flush=True)
            assert err < ECEF_MATCH_M, (
                f"{kind} {label}: ECEF error {err} m is not well under a metre"
            )
            require_best_attitude(last, f"{kind} {label} pad attitude")
            assert last.ned_ok and last.vel_ok, f"{kind} {label}: local/velocity unpublished"
            h_loc = require_local_height(last, f"{kind} {label} pad local height")
            ell = require_ellipsoid(last, f"{kind} {label} pad ellipsoid")
            print(
                f"{kind} {label} local_h={h_loc} ell={ell} isa={isa_alt} site_h={h}",
                flush=True,
            )
            assert abs(h_loc) < 2.5, (
                f"{kind} {label}: origin-pad datum/local height {h_loc} m is not near 0"
            )
            assert abs(h_loc - ell) > 0.45 * max(abs(ell), 8.0), (
                f"{kind} {label}: datum height {h_loc} is not distinguishable from ellipsoid {ell}"
            )
            assert abs(h_loc - isa_alt) > 0.45 * max(abs(isa_alt), 8.0), (
                f"{kind} {label}: datum height {h_loc} is not distinguishable from ISA {isa_alt}"
            )


def test_unified_solution_follows_later_gnss_not_first_fix():
    """after FULL, a later fusion-usable GNSS is followed, not the first pad fix."""
    lat, lon, h, origin = _site()
    pad = pad_full(lat, lon, h, origin, baro=True, mag=True)
    mag = mag_body(lat, lon, 0.0)
    later, ned_off = later_fix_ecef(origin)
    t0 = pad[-1].t_us
    moved = nav_append(
        list(pad),
        duration_s=12.0,
        gnss_ecef=later,
        mag=mag,
        baro_pa=tropospheric_isa_pressure_pa(h),
    )
    for kind, run in nav_langs(site_nav(lat, lon, h, moved)):
        pre = run.at_or_before(t0)
        last = run.last()
        require_ready_full(pre, f"{kind} pad before later GNSS")
        require_ready_full(last, f"{kind} after later GNSS")
        err_old = ecef_err_m(last.ecef, origin)
        err_new = ecef_err_m(last.ecef, later)
        shift = math.hypot(ned_off[0], ned_off[1], ned_off[2])
        print(
            f"{kind} later-GNSS err_old={err_old} err_new={err_new} shift={shift} "
            f"ned0={None if last.ned is None else last.ned[0]}",
            flush=True,
        )
        assert err_new < err_old, (
            f"{kind}: published ECEF stayed with the first pad GNSS ({err_old} vs {err_new})"
        )
        assert err_new < 0.55 * shift, (
            f"{kind}: published ECEF did not follow the later fix (err {err_new} m, shift {shift} m)"
        )
        assert last.ned is not None
        assert abs(last.ned[0]) > 1.5, (
            f"{kind}: later-GNSS published local stayed at the origin ({last.ned})"
        )


def test_skipping_epoch_leaves_mode_none():
    """pushing IMU+GNSS+baro+mag without running the epoch stays NONE."""
    lat, lon, h, origin = _site()
    epochs = with_steps(pad_full(lat, lon, h, origin, baro=True, mag=True), False)
    scen = site_nav(lat, lon, h, epochs)
    unused_c = c_nav_run(NavScenario(lat_deg=lat, lon_deg=lon, h_m=h, kind="unused"))
    unused_none = unused_c.last().mode
    for kind, run in nav_langs(scen):
        assert run.init_ok, f"{kind} skip-epoch init failed"
        last = run.last()
        print(
            f"{kind} skip-epoch mode={last.mode} name={last.mode_name} ready={last.ready}",
            flush=True,
        )
        _assert_py_mode(last, MODE_NONE, f"{kind} skip-epoch")
        if kind == "c":
            assert last.mode == unused_none, (
                f"C skip-epoch mode {last.mode} was not the unused NONE value {unused_none}"
            )
        assert not last.ready, f"{kind}: skip-epoch reported ready"


def test_solution_read_does_not_advance_filter():
    """reads-only after FULL stay FULL; the same IMU with epochs run is COASTING."""
    lat, lon, h, origin = _site()
    pad = pad_full(lat, lon, h, origin, baro=True, mag=True)
    reads = imu_only(list(pad), duration_s=3.2, step=False)
    ran = imu_only(list(pad), duration_s=3.2, step=True)
    t_pad = pad[-1].t_us
    for kind, held in nav_langs(site_nav(lat, lon, h, reads)):
        assert held.init_ok
        at_full = held.at_or_before(t_pad)
        last = held.last()
        _assert_py_mode(at_full, MODE_FULL, f"{kind} pre-read")
        _assert_py_mode(last, MODE_FULL, f"{kind} reads-only")
        require_ready_full(last, f"{kind} reads-only still ready")
        print(f"{kind} reads-only stayed mode={last.mode} name={last.mode_name}", flush=True)
    for kind, twin in nav_langs(site_nav(lat, lon, h, ran)):
        last = twin.last()
        _assert_py_mode(last, MODE_COASTING, f"{kind} epoch-run twin")
        assert last.ready, f"{kind}: 3 s IMU-only left INS not ready"
        print(f"{kind} epoch-run twin mode={last.mode} name={last.mode_name}", flush=True)
        if kind == "c":
            held_c = c_nav_run(site_nav(lat, lon, h, reads))
            assert held_c.last().mode != last.mode, (
                "C read-only and epoch-run twins produced the same mode value"
            )


def test_unused_or_null_instance_is_none():
    """unused and C NULL instances are NONE."""
    lat, lon, h = runtime_site()
    unused = NavScenario(lat_deg=lat, lon_deg=lon, h_m=h, kind="unused")
    for kind, run in nav_langs(unused):
        assert run.init_ok, f"{kind} unused init failed"
        last = run.last()
        print(f"{kind} unused mode={last.mode} name={last.mode_name} ready={last.ready}", flush=True)
        _assert_py_mode(last, MODE_NONE, f"{kind} unused")
        assert not last.ready
    null = c_nav_run(NavScenario(lat_deg=lat, lon_deg=lon, h_m=h, kind="null"))
    assert null.init_ok
    print(f"c null mode={null.last().mode} ready={null.last().ready}", flush=True)
    unused_c = c_nav_run(unused)
    assert unused_c.last().mode == null.last().mode, (
        "C unused and NULL instances were not the same NONE value"
    )


# ---------------------------------------------------------------------------
# B. Four modes; 2 s split; 3 s outage; expiry; pre-init ATTITUDE_ONLY
# ---------------------------------------------------------------------------


def test_aiding_age_split_full_vs_coasting():
    """1.9 s and 2.0 s stay FULL; just over 2.0 s is COASTING, still ready."""
    lat, lon, h, origin = _site()
    pad = pad_full(lat, lon, h, origin, baro=True, mag=True)
    arms = {
        "1.9": imu_only(list(pad), duration_s=AIDING_FULL_S),
        "2.0": imu_only(list(pad), duration_s=AIDING_EQUAL_S),
        "just-over": imu_only(list(pad), duration_s=AIDING_JUST_OVER_S),
    }
    c_modes = {}
    for tag, epochs in arms.items():
        for kind, run in nav_langs(site_nav(lat, lon, h, epochs)):
            last = run.last()
            print(
                f"{kind} {tag}s mode={last.mode} name={last.mode_name} ready={last.ready}",
                flush=True,
            )
            assert last.ready, f"{kind} {tag}s: INS ready became false"
            want = MODE_COASTING if tag == "just-over" else MODE_FULL
            _assert_py_mode(last, want, f"{kind} {tag}s")
            if kind == "c":
                c_modes[tag] = last.mode
    assert c_modes["1.9"] == c_modes["2.0"], "C 1.9 s and 2.0 s were not the same FULL value"
    assert c_modes["just-over"] != c_modes["2.0"], (
        "C just-over-2 s was not distinguishable from the 2.0 s FULL value"
    )


def test_three_second_outage_inside_window_is_coasting():
    """3 s GNSS gap is COASTING; not immediately NONE with no attitude."""
    lat, lon, h, origin = _site()
    pad = pad_full(lat, lon, h, origin, baro=True, mag=True)
    baro_pa = tropospheric_isa_pressure_pa(h)
    mag = mag_body(lat, lon, 0.0)
    with_baro = imu_only(list(pad), duration_s=OUTAGE_3S, baro_pa=baro_pa, mag=mag)
    no_baro = imu_only(list(pad), duration_s=OUTAGE_3S, mag=mag)
    unused_none = c_nav_run(NavScenario(lat_deg=lat, lon_deg=lon, h_m=h, kind="unused")).last().mode
    for tag, epochs in (("baro", with_baro), ("no-baro", no_baro)):
        for kind, run in nav_langs(site_nav(lat, lon, h, epochs)):
            last = run.last()
            print(
                f"{kind} 3s {tag} mode={last.mode} name={last.mode_name} "
                f"ready={last.ready} h_ok={last.h_ok} best={last.best_ok}",
                flush=True,
            )
            _assert_py_mode(last, MODE_COASTING, f"{kind} 3s {tag}")
            assert last.mode_name != MODE_NONE, (
                f"{kind} 3s {tag}: in-window GNSS outage was immediately NONE"
            )
            if kind == "c":
                assert last.mode != unused_none, (
                    f"C 3s {tag}: in-window GNSS outage was the unused NONE value"
                )
            assert last.ready, f"{kind} 3s {tag}: INS ready became false inside the window"
            require_best_attitude(last, f"{kind} 3s {tag} attitude")
            require_local_height(last, f"{kind} 3s {tag} local height")


def test_expired_window_is_attitude_only_ins_frozen():
    """post-2 s COASTING still integrates; 11 s freeze holds."""
    lat, lon, h, origin = _site()
    pad = pad_full(lat, lon, h, origin, baro=False, mag=False)
    force_s = 3.0
    in_window, t_door = imu_only_after_door(list(pad), force_s=force_s)
    remain_to_11 = FREEZE_11S - AIDING_JUST_OVER_S
    to_freeze, t_door_b = imu_only_after_door(list(pad), force_s=remain_to_11)
    extra = imu_only(list(to_freeze), duration_s=force_s, acc=ABSURD_NORTH_ACC)
    t_fr = to_freeze[-1].t_us
    assert t_door == t_door_b
    live_dn = {}
    for kind, run in nav_langs(site_nav(lat, lon, h, in_window)):
        door = run.at_or_before(t_door)
        last = run.last()
        print(
            f"{kind} post-door COASTING mode={last.mode_name} ready={last.ready} "
            f"door_pos={door.pos_ok} last_pos={last.pos_ok}",
            flush=True,
        )
        _assert_py_mode(door, MODE_COASTING, f"{kind} just-over-2 door")
        _assert_py_mode(last, MODE_COASTING, f"{kind} in-window force")
        assert door.ready and last.ready, f"{kind}: in-window INS ready became false"
        require_ready_full(door, f"{kind} door still publishes")
        require_ready_full(last, f"{kind} in-window still publishes")
        require_best_attitude(last, f"{kind} in-window attitude")
        live_dn[kind] = ecef_err_m(last.ecef, door.ecef)
        print(f"{kind} post-door in-window |Δecef|={live_dn[kind]} m", flush=True)
    for kind, run in nav_langs(site_nav(lat, lon, h, extra)):
        fr = run.at_or_before(t_fr)
        last = run.last()
        print(
            f"{kind} expiry mode={fr.mode} name={fr.mode_name} ready={fr.ready} "
            f"pos={fr.pos_ok}",
            flush=True,
        )
        _assert_py_mode(fr, MODE_ATTITUDE_ONLY, f"{kind} expiry")
        _assert_py_mode(last, MODE_ATTITUDE_ONLY, f"{kind} freeze extra")
        assert not fr.ready, f"{kind}: 11 s IMU-only left ready true"
        assert fr.pos_ok and fr.ecef is not None, f"{kind}: freeze unpublished INS positions"
        assert last.pos_ok and last.ecef is not None
        require_best_attitude(fr, f"{kind} expiry attitude")
        extra_dn = ecef_err_m(last.ecef, fr.ecef)
        print(
            f"{kind} freeze extra |Δecef|={extra_dn} m vs post-door in-window {live_dn[kind]} m",
            flush=True,
        )
        assert live_dn[kind] > extra_dn, (
            f"{kind}: post-door in-window change {live_dn[kind]} m did not exceed "
            f"freeze extra {extra_dn} m"
        )


def test_pre_init_ars_is_attitude_only():
    """IMU-only after ARS starts, before any absolute position, is ATTITUDE_ONLY."""
    lat, lon, h, origin = _site()
    imu = imu_only([], duration_s=1.2)
    imu_mag = imu_only([], duration_s=1.2, mag=mag_body(lat, lon, 0.0))
    unused = c_nav_run(NavScenario(lat_deg=lat, lon_deg=lon, h_m=h, kind="unused"))
    pad = pad_full(lat, lon, h, origin, baro=False, mag=False)
    expired = c_nav_run(site_nav(lat, lon, h, imu_only(list(pad), duration_s=FREEZE_11S)))
    expired_mode = expired.last().mode
    for tag, epochs in (("imu", imu), ("imu+mag", imu_mag)):
        for kind, run in nav_langs(site_nav(lat, lon, h, epochs)):
            last = run.last()
            print(
                f"{kind} pre-init {tag} mode={last.mode} name={last.mode_name} "
                f"best={last.best_ok} pos={last.pos_ok}",
                flush=True,
            )
            _assert_py_mode(last, MODE_ATTITUDE_ONLY, f"{kind} pre-init {tag}")
            assert not last.ready, f"{kind} pre-init {tag}: ready before any 3D"
            require_best_attitude(last, f"{kind} pre-init {tag}")
            assert math.isfinite(last.best[0]) and math.isfinite(last.best[1])
            if kind == "c":
                assert last.mode != unused.last().mode, (
                    f"C pre-init {tag} was not distinguishable from unused NONE"
                )
                assert last.mode == expired_mode, (
                    f"C pre-init {tag} mode {last.mode} was not the expired-window "
                    f"ATTITUDE_ONLY value {expired_mode}"
                )


# ---------------------------------------------------------------------------
# C. Re-acquire FULL that epoch; quality-loss unpublished positions
# ---------------------------------------------------------------------------


def test_first_usable_fix_after_expired_window_is_full_that_epoch():
    """next fusion-usable fix after freeze is FULL on that epoch; unfusable is ATTITUDE_ONLY."""
    lat, lon, h, origin = _site()
    pad = pad_full(lat, lon, h, origin, baro=False, mag=False)
    frozen = imu_only(list(pad), duration_s=FREEZE_11S)
    t_fr = frozen[-1].t_us
    dt = 0.01
    epochs = list(frozen)
    t_bad = t_good = None
    for i in range(1, 51):
        t_us = t_fr + int(round(i * dt * 1e6))
        kwargs = {}
        if i == 25:
            t_bad = t_us
            kwargs.update(
                gnss_ecef=tuple(origin),
                gnss_std=UNFUSABLE_POS_STD,
                gnss_vel=ZERO_VEL,
                gnss_vel_std=ENTRY_VEL_STD,
            )
        elif i == 50:
            t_good = t_us
            kwargs.update(
                gnss_ecef=tuple(origin),
                gnss_std=GNSS_STD_M,
                gnss_vel=ZERO_VEL,
                gnss_vel_std=ENTRY_VEL_STD,
            )
        epochs.append(nav_epoch(t_us, dt_sec=dt, **kwargs))
    assert t_bad is not None and t_good is not None
    for kind, run in nav_langs(site_nav(lat, lon, h, epochs)):
        fr = run.at_or_before(t_fr)
        bad = run.at_or_before(t_bad)
        good = run.at_or_after(t_good)
        print(
            f"{kind} freeze name={fr.mode_name} bad={bad.mode_name} "
            f"good={good.mode_name} good_ready={good.ready} good_t={good.t_us} want={t_good}",
            flush=True,
        )
        _assert_py_mode(fr, MODE_ATTITUDE_ONLY, f"{kind} freeze")
        _assert_py_mode(bad, MODE_ATTITUDE_ONLY, f"{kind} unfusable return")
        _assert_py_mode(good, MODE_FULL, f"{kind} first usable")
        assert not fr.ready and not bad.ready
        require_best_attitude(bad, f"{kind} unfusable still has attitude")
        require_ready_full(good, f"{kind} first usable after freeze")
        assert good.t_us == t_good, (
            f"{kind}: FULL was not read at the usable sample timestamp "
            f"(got {good.t_us}, sample {t_good})"
        )


def test_quality_loss_unpublishes_ins_positions_attitude_continues():
    """10 s of worse-than-exit GNSS is ATTITUDE_ONLY; positions fail; attitude remains."""
    lat, lon, h, origin = _site()
    yaw = runtime_att_yaw_rad()
    mag = mag_body(lat, lon, yaw)
    pad = pad_full(lat, lon, h, origin, baro=False, mag=True, mag_yaw=yaw)
    bad = nav_append(
        list(pad),
        duration_s=QUALITY_LOSS_S,
        gnss_ecef=origin,
        gnss_std=EXIT_POS_BAD,
        mag=mag,
    )
    freeze = imu_only(list(pad), duration_s=FREEZE_11S, mag=mag)
    qloss = {}
    for kind, run in nav_langs(site_nav(lat, lon, h, bad)):
        last = run.last()
        print(
            f"{kind} quality-loss mode={last.mode} name={last.mode_name} "
            f"ready={last.ready} pos={last.pos_ok} best={last.best_ok} ahrs={last.ahrs_ok}",
            flush=True,
        )
        _assert_py_mode(last, MODE_ATTITUDE_ONLY, f"{kind} quality-loss")
        assert not last.ready
        require_positions_fail(last, f"{kind} quality-loss")
        require_best_attitude(last, f"{kind} quality-loss attitude")
        require_ahrs_attitude(last, f"{kind} quality-loss AHRS")
        qloss[kind] = last
    for kind, run in nav_langs(site_nav(lat, lon, h, freeze)):
        last = run.last()
        assert last.pos_ok, f"{kind}: freeze unpublished positions (must stay distinct)"
        assert last.ecef is not None
        _assert_py_mode(last, MODE_ATTITUDE_ONLY, f"{kind} freeze")
        q = qloss[kind]
        print(
            f"{kind} freeze vs quality-loss pos_ok {last.pos_ok} vs {q.pos_ok} "
            f"modes {last.mode} vs {q.mode}",
            flush=True,
        )
        assert q.pos_ok is False
        assert last.pos_ok is True


# ---------------------------------------------------------------------------
# D. Best attitude: INS, else AHRS, else ARS carry
# ---------------------------------------------------------------------------


def test_best_attitude_is_ins_while_ready():
    """while INS is ready, best yaw is INS, not raw ARS — on FULL and on COASTING."""
    lat, lon, h, origin = _site()
    yaw = runtime_att_yaw_rad()
    ars_seed = yaw + runtime_mag_offset_rad()
    pad = pad_full(lat, lon, h, origin, baro=False, mag=False, yaw_rad=yaw)
    t_full = pad[-1].t_us
    coast = imu_only(list(pad), duration_s=OUTAGE_3S, yaw_rad=yaw)
    scen = site_nav(lat, lon, h, coast, yaw_hint=ars_seed, yaw_std=HINT_YAW_STD)

    def _ins_not_ars(snap, kind, tag):
        require_ready_full(snap, f"{kind} {tag}")
        best = require_best_attitude(snap, f"{kind} {tag} best")
        assert snap.ins_att is not None and snap.ars_att is not None
        d_ins = abs(angle_diff_rad(best[2], snap.ins_att[2]))
        d_ars = abs(angle_diff_rad(best[2], snap.ars_att[2]))
        gap = abs(angle_diff_rad(snap.ins_att[2], snap.ars_att[2]))
        print(
            f"{kind} {tag} best={best[2]} ins={snap.ins_att[2]} ars={snap.ars_att[2]} "
            f"d_ins={d_ins} d_ars={d_ars} gap={gap}",
            flush=True,
        )
        assert gap > math.radians(8.0), f"{kind} {tag}: INS and ARS yaw were not yet split"
        assert d_ins < 0.35 * gap, f"{kind} {tag}: best yaw was not the INS yaw"
        assert d_ars > d_ins, f"{kind} {tag}: best yaw was as close to ARS as to INS"

    for kind, run in nav_langs(scen):
        full = run.at_or_before(t_full)
        last = run.last()
        _assert_py_mode(full, MODE_FULL, f"{kind} INS-ready FULL")
        _assert_py_mode(last, MODE_COASTING, f"{kind} INS-ready COASTING")
        _ins_not_ars(full, kind, "FULL")
        _ins_not_ars(last, kind, "COASTING")


def test_best_attitude_falls_back_to_ahrs_then_ars():
    """when INS is not ready, best is mag AHRS; without mag, live ARS vs frozen INS."""
    lat, lon, h, origin = _site()
    y_ins = runtime_att_yaw_rad()
    y_mag = y_ins + runtime_mag_offset_rad()
    mag = mag_body(lat, lon, y_mag)
    rate = runtime_z_rate_rps()
    pad = pad_full(lat, lon, h, origin, baro=False, mag=False, yaw_rad=y_ins)
    # The magnetometer arrives only after the coasting window has expired:
    # the frozen INS fuses nothing (FP-05), so its yaw stays at y_ins while
    # the suite AHRS starts on the first magnetometer sample at y_mag. Fed
    # earlier, a live INS may legitimately pull its own yaw toward the
    # magnetometer at a rate the PRD leaves open, which would erase the split.
    frozen_imu = imu_only(list(pad), duration_s=FREEZE_11S)
    with_mag = imu_only(list(frozen_imu), duration_s=2.5, mag=mag)
    pad_ars = pad_full(lat, lon, h, origin, baro=False, mag=False, yaw_rad=y_ins)
    to_freeze = imu_only(list(pad_ars), duration_s=FREEZE_11S, gyr=(0.0, 0.0, rate))
    t_fr = to_freeze[-1].t_us
    ars_only = imu_only(list(to_freeze), duration_s=2.5, gyr=(0.0, 0.0, rate))
    for kind, run in nav_langs(site_nav(lat, lon, h, with_mag, yaw_hint=y_ins, yaw_std=HINT_YAW_STD)):
        last = run.last()
        _assert_py_mode(last, MODE_ATTITUDE_ONLY, f"{kind} AHRS fallback")
        assert not last.ready
        best = require_best_attitude(last, f"{kind} AHRS fallback")
        ahrs = require_ahrs_attitude(last, f"{kind} AHRS fallback")
        d_ahrs = abs(angle_diff_rad(best[2], ahrs[2]))
        assert last.ins_att is not None, f"{kind}: frozen INS attitude unpublished"
        gap = abs(angle_diff_rad(ahrs[2], last.ins_att[2]))
        d_ins = abs(angle_diff_rad(best[2], last.ins_att[2]))
        print(
            f"{kind} AHRS-fallback best={best[2]} ahrs={ahrs[2]} ins={last.ins_att[2]} "
            f"d_ahrs={d_ahrs} d_ins={d_ins} gap={gap}",
            flush=True,
        )
        assert gap > math.radians(10.0), (
            f"{kind}: AHRS yaw and frozen INS yaw were not split although the "
            "magnetometer only arrived after INS froze"
        )
        assert d_ahrs < 0.5 * gap, f"{kind}: best yaw was not the AHRS yaw"
        assert d_ins > d_ahrs, f"{kind}: best yaw was as close to frozen INS as to AHRS"
    for kind, run in nav_langs(site_nav(lat, lon, h, ars_only, yaw_hint=y_ins, yaw_std=HINT_YAW_STD)):
        frozen = run.at_or_before(t_fr)
        last = run.last()
        _assert_py_mode(last, MODE_ATTITUDE_ONLY, f"{kind} ARS-only")
        assert not last.ready
        best = require_best_attitude(last, f"{kind} ARS-only")
        assert last.ars_ok and last.ars_att is not None
        assert frozen.ins_att is not None
        d_ars = abs(angle_diff_rad(best[2], last.ars_att[2]))
        d_ins = abs(angle_diff_rad(best[2], frozen.ins_att[2]))
        walked = abs(
            angle_diff_rad(
                last.ars_att[2],
                frozen.ars_att[2] if frozen.ars_att is not None else last.ars_att[2],
            )
        )
        print(
            f"{kind} ARS-only best={best[2]} ars={last.ars_att[2]} frozen_ins={frozen.ins_att[2]} "
            f"d_ars={d_ars} d_ins={d_ins} ars_walked={walked}",
            flush=True,
        )
        assert walked > math.radians(8.0), f"{kind}: ARS did not keep integrating after freeze"
        assert d_ars < d_ins, f"{kind}: best yaw stayed with frozen INS instead of live ARS"
        assert d_ins > math.radians(8.0), f"{kind}: best yaw was not far from frozen INS"


def test_ars_fallback_yaw_is_last_ins_plus_ars_change():
    """after INS once converged, fallback yaw is last INS + ARS change, not ARS raw or 0."""
    lat, lon, h, origin = _site()
    y_ins = runtime_att_yaw_rad()
    ars_seed = y_ins + runtime_mag_offset_rad()
    rate = runtime_z_rate_rps()
    pad = pad_full(lat, lon, h, origin, baro=False, mag=False, yaw_rad=y_ins)
    to_freeze = imu_only(list(pad), duration_s=FREEZE_11S, gyr=(0.0, 0.0, rate))
    expired = imu_only(list(to_freeze), duration_s=2.5, gyr=(0.0, 0.0, rate))
    # Plain ARS from 0, short enough that it cannot walk onto the ±π branch
    # cut. Matching the once-converged z-rate duration would let both arms
    # land near the same principal value after any wrap of the carry sum.
    never = imu_only([], duration_s=1.2)
    scen = site_nav(lat, lon, h, expired, yaw_hint=ars_seed, yaw_std=HINT_YAW_STD)
    carry_best = {}
    for kind, run in nav_langs(scen):
        split_snap = run.last_ready()
        last = run.last()
        require_ready_full(split_snap, f"{kind} last-ready")
        _assert_py_mode(last, MODE_ATTITUDE_ONLY, f"{kind} ARS fallback")
        assert not last.ready, (
            f"{kind}: fallback snapshot was still INS-ready; carry was never a fallback"
        )
        assert split_snap.ins_att is not None and split_snap.ars_att is not None
        y_ins_r = split_snap.ins_att[2]
        y_ars_r = split_snap.ars_att[2]
        gap = abs(angle_diff_rad(y_ins_r, y_ars_r))
        print(f"{kind} last-ready ins={y_ins_r} ars={y_ars_r} gap={gap}", flush=True)
        assert gap > math.radians(8.0), f"{kind}: last-ready INS/ARS were not split"
        best = require_best_attitude(last, f"{kind} ARS fallback")
        assert last.ars_att is not None
        y_ars_now = last.ars_att[2]
        ars_change = abs(angle_diff_rad(y_ars_now, y_ars_r))
        print(f"{kind} ARS change after last-ready={ars_change}", flush=True)
        assert ars_change > math.radians(8.0), (
            f"{kind}: ARS yaw did not change after last-ready; carry degenerates to still-INS"
        )
        # Last-INS plus the ARS change, compared as headings. Do not wrap
        # that sum through difference-against-zero or atan2(sin, cos) and
        # demand a principal-value representative: π and −π are one heading.
        carry_sum = y_ins_r + angle_diff_rad(y_ars_now, y_ars_r)
        d_carry = abs(angle_diff_rad(best[2], carry_sum))
        d_raw = abs(angle_diff_rad(best[2], y_ars_now))
        d_zero = abs(angle_diff_rad(best[2], 0.0))
        print(
            f"{kind} fallback best={best[2]} carry_sum={carry_sum} raw={y_ars_now} "
            f"d_carry={d_carry} d_raw={d_raw} d_zero={d_zero}",
            flush=True,
        )
        assert d_carry < 0.35 * gap, f"{kind}: fallback yaw was not last-INS plus ARS change"
        assert d_raw > d_carry, f"{kind}: fallback yaw matched ARS raw"
        assert d_zero > math.radians(8.0), f"{kind}: fallback yaw sat at 0"
        carry_best[kind] = best[2]
    for kind, run in nav_langs(site_nav(lat, lon, h, never)):
        last = run.last()
        best = require_best_attitude(last, f"{kind} never-FULL ARS")
        print(f"{kind} never-FULL best_yaw={best[2]} once={carry_best[kind]}", flush=True)
        assert last.ars_ok and last.ars_att is not None, f"{kind}: never-FULL ARS unpublished"
        d_plain = abs(angle_diff_rad(best[2], last.ars_att[2]))
        assert d_plain < math.radians(8.0), (
            f"{kind}: never-FULL best yaw was not plain ARS (the path with no INS carry)"
        )
        d_once = abs(angle_diff_rad(best[2], carry_best[kind]))
        assert d_once > math.radians(8.0), (
            f"{kind}: never-FULL ARS yaw was not distinguishable from the once-converged fallback"
        )


# ---------------------------------------------------------------------------
# E. Local height continuity and baro as outage reference
# ---------------------------------------------------------------------------


def test_local_height_continuous_when_second_source_arrives():
    """first source fixes the datum; a later source conforms, no jump."""
    lat, lon, h, origin = _site()
    climb = runtime_climb_m()
    p0 = tropospheric_isa_pressure_pa(h)
    p1 = tropospheric_isa_pressure_pa(h + climb)
    mag = mag_body(lat, lon, 0.0)
    # Arm 1: GNSS FULL first, then baro whose ISA differs by several metres.
    gnss_first = pad_full(lat, lon, h, origin, baro=False, mag=True)
    t0 = gnss_first[-1].t_us
    h0_scen = site_nav(lat, lon, h, gnss_first)
    with_baro = nav_append(
        list(gnss_first),
        duration_s=2.0,
        gnss_ecef=origin,
        mag=mag,
        baro_pa=p1,
    )
    for kind, run in nav_langs(site_nav(lat, lon, h, with_baro)):
        pre = run.at_or_before(t0)
        last = run.last()
        h_pre = require_local_height(pre, f"{kind} GNSS-first H0")
        h_post = require_local_height(last, f"{kind} after baro")
        jump = abs(h_post - h_pre)
        print(
            f"{kind} GNSS-then-baro H0={h_pre} after={h_post} jump={jump} isa_step={climb}",
            flush=True,
        )
        assert abs(h_pre) < 2.5, (
            f"{kind}: GNSS-first H0 {h_pre} m is not near the origin-pad datum 0"
        )
        assert abs(h_pre) < 0.45 * climb, (
            f"{kind}: GNSS-first H0 {h_pre} m was not distinguishable from the later ISA step {climb} m"
        )
        assert jump < 0.45 * climb, (
            f"{kind}: baro arrival jumped local height by {jump} m toward the ISA step"
        )
    # Arm 2: baro first with a pressure step (Hb distinguishable from 0), then GNSS.
    baro_pad = nav_append([], duration_s=2.0, mag=mag, baro_pa=p0)
    baro_step = nav_append(
        list(baro_pad),
        duration_s=3.0,
        mag=mag,
        baro_pa=p1,
    )
    t_p0 = baro_pad[-1].t_us
    t_b = baro_step[-1].t_us
    then_gnss = nav_append(
        list(baro_step),
        duration_s=HAPPY_DURATION_S,
        gnss_ecef=origin,
        mag=mag,
        baro_pa=p1,
    )
    for kind, run in nav_langs(site_nav(lat, lon, h, then_gnss)):
        at_p0 = run.at_or_before(t_p0)
        pre = run.at_or_before(t_b)
        last = run.last()
        h_p0 = require_local_height(at_p0, f"{kind} baro-first p0 pad")
        hb = require_local_height(pre, f"{kind} baro-first Hb")
        h_gnss = require_local_height(last, f"{kind} GNSS appearance")
        print(
            f"{kind} baro-first p0={h_p0} Hb={hb} after GNSS={h_gnss} climb={climb}",
            flush=True,
        )
        assert (hb - h_p0) * climb > 0.0, (
            f"{kind}: baro-first height did not move from the p0 pad in the climb direction"
        )
        assert abs(hb) > 1.5, f"{kind}: baro-first Hb was not distinguishable from origin 0"
        assert abs(h_gnss) > 0.45 * abs(hb), (
            f"{kind}: GNSS appearance yanked local height toward 0 (Hb={hb}, now={h_gnss})"
        )


def test_baro_is_outage_surviving_local_height_when_both_present():
    """PRD: with GNSS+baro, outage local height follows a baro step; GNSS return does not yank it."""
    lat, lon, h, origin = _site()
    climb = runtime_climb_m()
    if climb > 3.2:
        climb = 3.2
    p0 = tropospheric_isa_pressure_pa(h)
    p1 = tropospheric_isa_pressure_pa(h + climb)
    mag = mag_body(lat, lon, 0.0)
    pad = nav_append(
        [],
        duration_s=HAPPY_DURATION_S,
        gnss_ecef=origin,
        mag=mag,
        baro_pa=p0,
    )
    t0 = pad[-1].t_us
    def _baro_ramp(_t_us, _i):
        frac = (_t_us - t0) / (OUTAGE_3S * 1e6)
        frac = 0.0 if frac < 0.0 else 1.0 if frac > 1.0 else frac
        return p0 + (p1 - p0) * frac

    stepped = nav_append(
        list(pad),
        duration_s=OUTAGE_3S,
        mag=mag,
        baro_at=_baro_ramp,
    )
    held = imu_only(list(pad), duration_s=OUTAGE_3S, baro_pa=p0, mag=mag)
    t_out = stepped[-1].t_us
    restored = nav_append(
        list(stepped),
        duration_s=1.2,
        gnss_ecef=origin,
        mag=mag,
        baro_pa=p1,
    )
    dh_step = {}
    dh_hold = {}
    for kind, run in nav_langs(site_nav(lat, lon, h, stepped, auto_zupt_disable=True)):
        pre = run.at_or_before(t0)
        last = run.last()
        _assert_py_mode(last, MODE_COASTING, f"{kind} baro outage")
        h_pre = require_local_height(pre, f"{kind} H0")
        h_out = require_local_height(last, f"{kind} outage baro")
        dh_step[kind] = h_out - h_pre
        print(f"{kind} outage H0={h_pre} H={h_out} climb={climb} dh={dh_step[kind]}", flush=True)
        assert dh_step[kind] * climb > 0.0, (
            f"{kind}: outage local height did not rise with the baro step"
        )
    for kind, run in nav_langs(site_nav(lat, lon, h, held, auto_zupt_disable=True)):
        pre = run.at_or_before(t0)
        last = run.last()
        h_pre = require_local_height(pre, f"{kind} hold H0")
        h_out = require_local_height(last, f"{kind} hold outage")
        dh_hold[kind] = h_out - h_pre
        print(f"{kind} hold H0={h_pre} H={h_out} dh={dh_hold[kind]}", flush=True)
        assert abs(dh_hold[kind]) < 1.2, f"{kind}: unchanged-pressure outage walked local height"
        assert abs(dh_step[kind]) > abs(dh_hold[kind]) + 0.08, (
            f"{kind}: outage local height did not follow the baro step "
            f"(step dh={dh_step[kind]}, hold dh={dh_hold[kind]})"
        )
    for kind, run in nav_langs(site_nav(lat, lon, h, restored, auto_zupt_disable=True)):
        late = run.at_or_before(t_out)
        last = run.last()
        _assert_py_mode(last, MODE_FULL, f"{kind} GNSS return")
        h_late = require_local_height(late, f"{kind} late-outage")
        h_ret = require_local_height(last, f"{kind} GNSS-return")
        print(f"{kind} return late={h_late} now={h_ret}", flush=True)
        assert abs(h_ret - h_late) < 0.45 * climb, (
            f"{kind}: GNSS return yanked local height away from the late-outage baro height"
        )


# ---------------------------------------------------------------------------
# F. Ellipsoid gating; mocap owns NED
# ---------------------------------------------------------------------------


def test_mocap_only_full_refuses_ellipsoid_height():
    """indoor local-position FULL publishes local, refuses ellipsoid,
    and does not report the prescribed init origin as WGS84 ellipsoid height."""
    lat_a, lon_a, h_a, origin_a = _site()
    # Second prescribed init height follows the first origin, before either
    # navigator is called. A fixed offset above 8 m keeps the contrast.
    h_b = h_a + 35.0
    lat_b, lon_b = runtime_second_site()[:2]
    origin_b = ecef_from_llh_deg(lat_b, lon_b, h_b)
    dh_origin = abs(h_b - h_a)
    assert dh_origin > 8.0, (
        f"indoor origin heights {h_a} and {h_b} are not distinguishable"
    )
    p0 = runtime_tracker_ned()
    p1 = (p0[0] + runtime_mocap_delta_m(), p0[1], p0[2])
    origin_p0: dict[str, list[tuple[float, object]]] = {}
    cases = (
        ("p0-a", p0, lat_a, lon_a, h_a, origin_a),
        ("p1-a", p1, lat_a, lon_a, h_a, origin_a),
        ("p0-b", p0, lat_b, lon_b, h_b, origin_b),
    )
    for tag, pose, lat, lon, h, _origin in cases:
        epochs = nav_append(
            [],
            duration_s=HAPPY_DURATION_S,
            local_ned=pose,
            local_std=(CM_STD_M, CM_STD_M, CM_STD_M),
        )
        for kind, run in nav_langs(site_nav(lat, lon, h, epochs)):
            last = run.last()
            print(
                f"{kind} mocap {tag} mode={last.mode} name={last.mode_name} "
                f"ned={last.ned_ok} ell_ok={last.ell_ok} ready={last.ready} "
                f"init_h={h}",
                flush=True,
            )
            _assert_py_mode(last, MODE_FULL, f"{kind} mocap {tag}")
            assert last.ready, f"{kind} mocap {tag}: not ready with fresh local aiding"
            assert last.ned_ok and last.ned is not None, f"{kind} mocap {tag}: local unpublished"
            # PRD first: a hollow that publishes the prescribed init origin as
            # ellipsoid is this sentence, not merely "some ellipsoid leaked".
            require_indoor_ellipsoid_not_init_origin(
                last, h, f"{kind} mocap {tag} PRD"
            )
            require_unpublished_ellipsoid(last, f"{kind} mocap {tag}")
            if tag.startswith("p0-"):
                origin_p0.setdefault(kind, []).append((h, last))
    for kind, pairs in origin_p0.items():
        assert len(pairs) == 2, f"{kind}: missing the second indoor origin"
        (h1, s1), (h2, s2) = pairs
        tracked = (
            indoor_ellipsoid_matches_init_origin(s1, h1)
            and indoor_ellipsoid_matches_init_origin(s2, h2)
        )
        print(
            f"{kind} PRD origin contrast h {h1}->{h2} ell {s1.ell}->{s2.ell} "
            f"tracked={tracked}",
            flush=True,
        )
        assert not tracked, (
            f"{kind}: indoor ellipsoid tracked the prescribed init origins "
            f"({s1.ell} vs {s2.ell} for h {h1} vs {h2})"
        )


def test_ellipsoid_from_ins_under_gnss_and_local_plus_offset_in_outage():
    """under GNSS ellipsoid matches GNSS height; in an outage it follows local + held offset."""
    lat, lon, h, origin = _site()
    climb = runtime_climb_m()
    p0 = tropospheric_isa_pressure_pa(h)
    p1 = tropospheric_isa_pressure_pa(h + climb)
    mag = mag_body(lat, lon, 0.0)
    pad = nav_append(
        [],
        duration_s=HAPPY_DURATION_S,
        gnss_ecef=origin,
        mag=mag,
        baro_pa=p0,
    )
    t0 = pad[-1].t_us
    gap = imu_only(list(pad), duration_s=OUTAGE_3S, baro_pa=p1, mag=mag)
    for kind, run in nav_langs(site_nav(lat, lon, h, pad)):
        last = run.last()
        _assert_py_mode(last, MODE_FULL, f"{kind} GNSS ellipsoid")
        ell = require_ellipsoid(last, f"{kind} GNSS ellipsoid")
        print(f"{kind} GNSS ell={ell} site_h={h}", flush=True)
        assert abs(ell - h) < 2.5, f"{kind}: ellipsoid under GNSS was not near GNSS height"
    for kind, run in nav_langs(site_nav(lat, lon, h, gap)):
        pre = run.at_or_before(t0)
        last = run.last()
        h_pre = require_local_height(pre, f"{kind} pre-gap local")
        ell_pre = require_ellipsoid(pre, f"{kind} pre-gap ell")
        h_now = require_local_height(last, f"{kind} gap local")
        ell_now = require_ellipsoid(last, f"{kind} gap ell")
        off_pre = ell_pre - h_pre
        off_now = ell_now - h_now
        print(
            f"{kind} gap h {h_pre}->{h_now} ell {ell_pre}->{ell_now} "
            f"off {off_pre}->{off_now} climb={climb}",
            flush=True,
        )
        assert (h_now - h_pre) * climb > 0.0, f"{kind}: gap local height did not follow the baro step"
        assert abs((ell_now - ell_pre) - (h_now - h_pre)) < 0.55 * climb, (
            f"{kind}: gap ellipsoid did not follow local height at a held offset"
        )
        assert abs(off_now - off_pre) < 0.55 * climb, (
            f"{kind}: gap offset was not held while local height moved"
        )


def test_mocap_owns_ned_constant_offset_not_shifted_origin():
    """GNSS-first then mocap keeps the INS origin; indoor Δ in → Δ out; baro keeps ellipsoid unpublished."""
    lat, lon, h, origin = _site()
    p0 = runtime_tracker_ned()
    dn = runtime_mocap_delta_m()
    p1 = (p0[0] + dn, p0[1], p0[2])
    mag = mag_body(lat, lon, 0.0)
    pad = pad_full(lat, lon, h, origin, baro=False, mag=True)
    later, _ned = later_fix_ecef(origin)
    moved_gnss = nav_append(
        list(pad),
        duration_s=12.0,
        gnss_ecef=later,
        mag=mag,
    )
    t_l0 = moved_gnss[-1].t_us
    mocap_hold = nav_append(
        list(moved_gnss),
        duration_s=2.0,
        local_ned=p0,
        local_std=GNSS_STD_M,
        mag=mag,
    )
    t_hold = mocap_hold[-1].t_us
    mocap_delta = nav_append(
        list(mocap_hold),
        duration_s=2.0,
        local_ned=p1,
        local_std=GNSS_STD_M,
        mag=mag,
    )
    for kind, run in nav_langs(site_nav(lat, lon, h, mocap_delta)):
        l0 = run.at_or_before(t_l0)
        hold = run.at_or_before(t_hold)
        last = run.last()
        require_ready_full(l0, f"{kind} GNSS-first L0")
        assert l0.ned is not None and hold.ned is not None and last.ned is not None
        assert l0.ecef is not None and hold.ecef is not None
        print(
            f"{kind} GNSS-first L0={l0.ned} hold={hold.ned} afterΔ={last.ned} "
            f"P0={p0} dP={dn} E0={l0.ecef} Ehold={hold.ecef}",
            flush=True,
        )
        assert abs(l0.ned[0]) > 1.5, (
            f"{kind}: GNSS-first published local was still the origin ({l0.ned})"
        )
        # The NED origin is the init anchor (FP-03) and mocap owns that frame:
        # the suite subtracts a constant offset from mocap samples instead of
        # shifting the INS origin (FP-08). Which constant is not specified, so
        # where the published local lands is free; what must hold is that the
        # published ECEF stays the init anchor plus the published local NED.
        # Shifting the origin onto mocap (or to the current position) breaks
        # that by about the shift, |P0 - L0| (or |L0|).
        res_l0 = [
            g - e for g, e in zip(l0.ecef, ecef_plus_ned(origin, *l0.ned))
        ]
        res_hold = [
            g - e for g, e in zip(hold.ecef, ecef_plus_ned(origin, *hold.ned))
        ]
        origin_shift = math.sqrt(sum((a - b) ** 2 for a, b in zip(res_hold, res_l0)))
        shift_scale = min(
            math.hypot(l0.ned[0] - p0[0], l0.ned[1] - p0[1], l0.ned[2] - p0[2]),
            math.hypot(l0.ned[0], l0.ned[1], l0.ned[2]),
        )
        print(
            f"{kind} GNSS-first origin shift={origin_shift} scale={shift_scale} "
            f"afterΔ_n={last.ned[0] - hold.ned[0]}",
            flush=True,
        )
        assert origin_shift < 0.45 * shift_scale, (
            f"{kind}: NED origin implied by published ECEF and local moved by "
            f"{origin_shift} m when mocap started"
        )
    indoor0 = nav_append(
        [],
        duration_s=HAPPY_DURATION_S,
        local_ned=p0,
        local_std=(CM_STD_M, CM_STD_M, CM_STD_M),
    )
    t_i0 = indoor0[-1].t_us

    def _mocap_ramp(t_us, _i):
        frac = (t_us - t_i0) / (2.0 * 1e6)
        frac = 0.0 if frac < 0.0 else 1.0 if frac > 1.0 else frac
        pose = (p0[0] + dn * frac, p0[1], p0[2])
        return pose, (CM_STD_M, CM_STD_M, CM_STD_M)

    indoor1 = nav_append(
        list(indoor0),
        duration_s=2.0,
        local_at=_mocap_ramp,
    )
    t_i1 = indoor1[-1].t_us
    p_baro = tropospheric_isa_pressure_pa(h + runtime_climb_m())
    indoor_baro = nav_append(
        list(indoor1),
        duration_s=2.0,
        local_ned=p1,
        local_std=(CM_STD_M, CM_STD_M, CM_STD_M),
        baro_pa=p_baro,
    )
    # The IMU stays perfectly still while the tracker creeps by centimetres,
    # so the automatic standstill detector would legitimately fuse zero
    # velocity against the mocap ramp (FP-03); how strongly is tuning the
    # PRD leaves open. This arm is about the constant offset (delta in ->
    # delta out), so the detector is switched off through its public option.
    indoor_scen = site_nav(lat, lon, h, indoor_baro, auto_zupt_disable=True)
    for kind, run in nav_langs(indoor_scen):
        a = run.at_or_before(t_i0)
        b = run.at_or_before(t_i1)
        last = run.last()
        _assert_py_mode(a, MODE_FULL, f"{kind} indoor mocap FULL")
        assert a.ned is not None and b.ned is not None
        d_pub = b.ned[0] - a.ned[0]
        print(
            f"{kind} indoor Δin={dn} Δout={d_pub} n0={a.ned[0]} n1={b.ned[0]} "
            f"ell_ok={last.ell_ok}",
            flush=True,
        )
        assert abs(d_pub - dn) < 0.35 * abs(dn), (
            f"{kind}: indoor published north change {d_pub} was not about the mocap Δ {dn}"
        )
        require_indoor_ellipsoid_not_init_origin(a, h, f"{kind} indoor PRD")
        require_unpublished_ellipsoid(a, f"{kind} indoor ellipsoid")
        require_indoor_ellipsoid_not_init_origin(
            last, h, f"{kind} indoor baro-after-mocap PRD"
        )
        require_unpublished_ellipsoid(last, f"{kind} indoor baro-after-mocap ellipsoid")


# ---------------------------------------------------------------------------
# G. Static initial-attitude hint
# ---------------------------------------------------------------------------


def test_static_attitude_hint_seeds_ins_until_init():
    """a static yaw hint seeds ARS yaw until INS initializes, and INS yaw after FULL."""
    lat, lon, h, origin = _site()
    yaw = runtime_att_yaw_rad()
    pre_imu = imu_only([], duration_s=1.2)
    t_pre = pre_imu[-1].t_us
    epochs = nav_append(
        list(pre_imu),
        duration_s=HAPPY_DURATION_S,
        gnss_ecef=origin,
        gnss_std=GNSS_STD_M,
        gnss_vel=ZERO_VEL,
        gnss_vel_std=ENTRY_VEL_STD,
    )
    scen = site_nav(lat, lon, h, epochs, yaw_hint=yaw, yaw_std=HINT_YAW_STD)
    for kind, run in nav_langs(scen):
        pre = run.at_or_before(t_pre)
        last = run.last()
        print(
            f"{kind} pre-INS ready={pre.ready} ars_ok={pre.ars_ok} "
            f"ars={None if pre.ars_att is None else pre.ars_att[2]} hint={yaw}",
            flush=True,
        )
        assert not pre.ready, f"{kind}: INS was already ready before the first GNSS"
        assert pre.ars_ok and pre.ars_att is not None, (
            f"{kind}: ARS unpublished before INS init; cannot observe the yaw seed"
        )
        d_ars_hint = abs(angle_diff_rad(pre.ars_att[2], yaw))
        d_ars_zero = abs(angle_diff_rad(pre.ars_att[2], 0.0))
        print(
            f"{kind} ARS-seed d_hint={d_ars_hint} d_zero={d_ars_zero}",
            flush=True,
        )
        assert d_ars_zero > math.radians(8.0), (
            f"{kind}: ARS yaw stayed near 0 despite the static hint, before INS initialized"
        )
        assert d_ars_hint < 0.45 * d_ars_zero, (
            f"{kind}: ARS yaw was not near the static hint before INS initialized"
        )
        require_ready_full(last, f"{kind} hint pad")
        assert last.ins_att is not None
        d_hint = abs(angle_diff_rad(last.ins_att[2], yaw))
        d_zero = abs(angle_diff_rad(last.ins_att[2], 0.0))
        print(
            f"{kind} hint={yaw} ins_yaw={last.ins_att[2]} d_hint={d_hint} d_zero={d_zero}",
            flush=True,
        )
        assert d_zero > math.radians(8.0), f"{kind}: INS yaw stayed near 0 despite the hint"
        assert d_hint < 0.45 * d_zero, f"{kind}: INS yaw was not near the static hint"


def test_static_attitude_hint_does_not_bias_later_reacquisition():
    """after freeze re-acquire, yaw does not snap back to the stale static hint."""
    lat, lon, h, origin = _site()
    hint = runtime_att_yaw_rad() + 0.8
    y_mag = hint + runtime_mag_offset_rad()
    mag = mag_body(lat, lon, y_mag)
    rate = runtime_z_rate_rps()
    pad = pad_full(lat, lon, h, origin, baro=False, mag=False, yaw_rad=hint)
    walked = nav_append(
        list(pad),
        duration_s=SPLIT_YAW_S,
        gnss_ecef=origin,
        gnss_vel=None,
        gyr=(0.0, 0.0, rate),
    )
    t_ready = walked[-1].t_us
    expired = imu_only(list(walked), duration_s=FREEZE_11S, mag=mag, gyr=(0.0, 0.0, rate))
    t_fr = expired[-1].t_us
    reacq = nav_append(
        list(expired),
        duration_s=1.2,
        gnss_ecef=origin,
        mag=mag,
    )
    scen = site_nav(lat, lon, h, reacq, yaw_hint=hint, yaw_std=HINT_YAW_STD)
    for kind, run in nav_langs(scen):
        ready = run.at_or_before(t_ready)
        fr = run.at_or_before(t_fr)
        last = run.last()
        require_ready_full(ready, f"{kind} last-ready before freeze")
        _assert_py_mode(fr, MODE_ATTITUDE_ONLY, f"{kind} freeze before reacquire")
        assert not fr.ready, (
            f"{kind}: freeze snapshot was still INS-ready; re-acquire never left INS"
        )
        require_ready_full(last, f"{kind} reacquire")
        ahrs = require_ahrs_attitude(fr, f"{kind} freeze AHRS")
        assert ready.ins_att is not None
        last_ins = ready.ins_att[2]
        d_hint_ready = abs(angle_diff_rad(last_ins, hint))
        d_ahrs_hint = abs(angle_diff_rad(ahrs[2], hint))
        print(
            f"{kind} last-ready ins={last_ins} hint={hint} d_hint={d_hint_ready} "
            f"ahrs={ahrs[2]} d_ahrs_hint={d_ahrs_hint}",
            flush=True,
        )
        assert d_hint_ready > math.radians(10.0), (
            f"{kind}: last-ready INS had not walked off the static hint"
        )
        assert d_ahrs_hint > math.radians(10.0), (
            f"{kind}: parallel AHRS had not walked off the static hint"
        )
        best = require_best_attitude(last, f"{kind} reacquire best")
        d_hint = abs(angle_diff_rad(best[2], hint))
        ins_yaw = last.ins_att[2] if last.ins_att is not None else best[2]
        d_ins_hint = abs(angle_diff_rad(ins_yaw, hint))
        print(
            f"{kind} reacq best={best[2]} ins={ins_yaw} hint={hint} "
            f"d_hint={d_hint} d_ins_hint={d_ins_hint} fr_name={fr.mode_name}",
            flush=True,
        )
        assert d_ins_hint > math.radians(10.0), (
            f"{kind}: post-reacquire INS yaw snapped back to the static hint"
        )


# ---------------------------------------------------------------------------
# H. INS-options outlier override and standstill copy onto parallel filters
# ---------------------------------------------------------------------------


def test_outlier_override_from_ins_options_reaches_parallel_filters():
    """INS-options chi² override reaches baro (after INS is not live), AHRS, and ARS, short horizon."""
    lat, lon, h, origin = _site()
    climb = runtime_climb_m() + 8.0
    p0 = tropospheric_isa_pressure_pa(h)
    p1 = tropospheric_isa_pressure_pa(h + climb)
    y0 = 0.0
    y1 = runtime_att_yaw_rad() + 0.9
    mag0 = mag_body(lat, lon, y0)
    mag1 = mag_body(lat, lon, y1)
    pad = nav_append(
        [],
        duration_s=HAPPY_DURATION_S,
        gnss_ecef=origin,
        mag=mag0,
        baro_pa=p0,
    )
    frozen = imu_only(list(pad), duration_s=FREEZE_11S, mag=mag0, baro_pa=p0)
    t_fr = frozen[-1].t_us
    short_s = 1.6
    baro_step = imu_only(list(frozen), duration_s=short_s, mag=mag0, baro_pa=p1)
    mag_step = imu_only(list(frozen), duration_s=short_s, mag=mag1, baro_pa=p0)
    roll_step = runtime_mag_offset_rad()
    acc_roll = still_level_acc(roll=roll_step)
    ars_step = imu_only(list(frozen), duration_s=short_s, acc=acc_roll, baro_pa=p0)

    def _baro(override: bool):
        run = c_nav_run(site_nav(lat, lon, h, baro_step, chi2_disable=override))
        pre = run.at_or_before(t_fr)
        last = run.last()
        assert not pre.ready, "outlier baro arm: INS was still a live height source"
        h_pre = require_local_height(pre, "baro override pre")
        h_now = require_local_height(last, "baro override post")
        return h_now - h_pre

    def _ahrs(override: bool):
        run = c_nav_run(site_nav(lat, lon, h, mag_step, chi2_disable=override))
        last = run.last()
        ahrs = require_ahrs_attitude(last, f"AHRS override={override}")
        return ahrs[2]

    def _ars(override: bool):
        run = c_nav_run(site_nav(lat, lon, h, ars_step, chi2_disable=override))
        last = run.last()
        assert not last.ready, "outlier ARS arm: INS was still ready"
        assert last.ars_ok and last.ars_att is not None, (
            f"ARS unpublished on chi² override={override}"
        )
        return last.ars_att[0]

    dh_off = _baro(False)
    dh_on = _baro(True)
    yaw_off = _ahrs(False)
    yaw_on = _ahrs(True)
    roll_off = _ars(False)
    roll_on = _ars(True)
    print(
        f"override baro dh_off={dh_off} dh_on={dh_on} climb={climb} "
        f"yaw_off={yaw_off} yaw_on={yaw_on} y1={y1} "
        f"ars_roll_off={roll_off} ars_roll_on={roll_on} roll_step={roll_step}",
        flush=True,
    )
    assert abs(dh_on) > abs(dh_off), (
        "chi² override did not let suite local height track the baro step tighter "
        "after INS stopped being a live height source"
    )
    d_off = abs(angle_diff_rad(yaw_off, y1))
    d_on = abs(angle_diff_rad(yaw_on, y1))
    assert d_on < d_off, (
        "chi² override did not let suite AHRS yaw track the mag step tighter"
    )
    d_ars_off = abs(roll_off)
    d_ars_on = abs(roll_on)
    print(
        f"override ARS |roll|_off={d_ars_off} |roll|_on={d_ars_on} roll_step={roll_step}",
        flush=True,
    )
    assert d_ars_on > d_ars_off, (
        "chi² override from INS options did not reach ARS: published ARS roll "
        "did not move farther toward the accelerometer step than default-off"
    )


def test_standstill_definition_from_ins_options_reaches_ars_and_baro():
    """disabling INS standstill releases ARS/AHRS yaw hold and baro height hold after INS is not live."""
    lat, lon, h, origin = _site()
    mag = mag_body(lat, lon, 0.0)
    p0 = tropospheric_isa_pressure_pa(h)
    z_rate = STILL_Z_RATE_RPS
    acc_vert = STILL_VERT_ACC
    pad_ars = nav_append(
        [],
        duration_s=HAPPY_DURATION_S,
        gnss_ecef=origin,
        baro_pa=p0,
    )
    # Residual starts at GNSS drop so the stillness accumulator is the residual,
    # not an 11 s still run diluted with zeros, then a late residual.
    ars_probe = imu_only(
        list(pad_ars),
        duration_s=FREEZE_11S + 5.0,
        baro_pa=p0,
        gyr=(0.0, 0.0, z_rate),
        acc=acc_vert,
    )
    pad_ahrs = nav_append(
        [],
        duration_s=HAPPY_DURATION_S,
        gnss_ecef=origin,
        mag=mag,
        baro_pa=p0,
    )
    ahrs_probe = imu_only(
        list(pad_ahrs),
        duration_s=FREEZE_11S + 5.0,
        mag=None,
        baro_pa=p0,
        gyr=(0.0, 0.0, z_rate),
        acc=acc_vert,
    )

    def _last(disable: bool, epochs):
        run = c_nav_run(
            site_nav(
                lat,
                lon,
                h,
                epochs,
                auto_zupt_disable=disable,
                auto_zupt_static_gyr_rps=STILL_GYR_BOUND_RPS,
                auto_zupt_static_acc_mps2=STILL_ACC_BOUND_MPS2,
            )
        )
        last = run.last()
        assert not last.ready, "standstill arm: INS was still ready"
        return last

    ars_held = _last(False, ars_probe)
    ars_rel = _last(True, ars_probe)
    ahrs_held = _last(False, ahrs_probe)
    ahrs_rel = _last(True, ahrs_probe)
    baro_held = ars_held
    baro_rel = ars_rel
    require_best_attitude(ars_held, "ARS standstill held")
    require_best_attitude(ars_rel, "ARS standstill released")
    ahrs_h = require_ahrs_attitude(ahrs_held, "AHRS standstill held")
    ahrs_r = require_ahrs_attitude(ahrs_rel, "AHRS standstill released")
    h_held = require_local_height(baro_held, "baro standstill held")
    h_rel = require_local_height(baro_rel, "baro standstill released")
    y_held = ars_held.best[2]
    y_rel = ars_rel.best[2]
    print(
        f"standstill ARS best held={y_held} released={y_rel} "
        f"AHRS held={ahrs_h[2]} released={ahrs_r[2]} "
        f"local_h held={h_held} released={h_rel}",
        flush=True,
    )
    assert abs(y_rel) > abs(y_held) + math.radians(1.5), (
        "disabling INS standstill still held ARS/best yaw against the residual z-rate"
    )
    d_ahrs = abs(angle_diff_rad(ahrs_r[2], ahrs_h[2]))
    assert d_ahrs > math.radians(1.5), (
        "disabling INS standstill still held AHRS yaw against the residual z-rate"
    )
    assert abs(h_rel - h_held) > 0.04, (
        "disabling INS standstill still held unified local height against the vertical residual"
    )


def test_four_mode_values_are_pairwise_different():
    """C values for the four named conditions are pairwise different."""
    lat, lon, h, origin = _site()
    pad = pad_full(lat, lon, h, origin, baro=True, mag=True)
    full = c_nav_run(site_nav(lat, lon, h, pad))
    coast = c_nav_run(site_nav(lat, lon, h, imu_only(list(pad), duration_s=OUTAGE_3S)))
    att = c_nav_run(site_nav(lat, lon, h, imu_only(list(pad), duration_s=FREEZE_11S)))
    none = c_nav_run(NavScenario(lat_deg=lat, lon_deg=lon, h_m=h, kind="unused"))
    values = [full.last().mode, coast.last().mode, att.last().mode, none.last().mode]
    print(f"C mode values FULL/COASTING/ATTITUDE_ONLY/NONE={values}", flush=True)
    _assert_modes_pairwise_different(
        values, ("FULL", "COASTING", "ATTITUDE_ONLY", "NONE")
    )
    py_full = py_nav_run(site_nav(lat, lon, h, pad))
    py_coast = py_nav_run(site_nav(lat, lon, h, imu_only(list(pad), duration_s=OUTAGE_3S)))
    py_att = py_nav_run(site_nav(lat, lon, h, imu_only(list(pad), duration_s=FREEZE_11S)))
    py_none = py_nav_run(NavScenario(lat_deg=lat, lon_deg=lon, h_m=h, kind="unused"))
    names = [
        py_mode(py_full.last(), "py FULL"),
        py_mode(py_coast.last(), "py COASTING"),
        py_mode(py_att.last(), "py ATTITUDE_ONLY"),
        py_mode(py_none.last(), "py NONE"),
    ]
    print(f"Python mode names={names}", flush=True)
    assert names == [MODE_FULL, MODE_COASTING, MODE_ATTITUDE_ONLY, MODE_NONE]


def test_published_suite_snapshots_are_well_formed():
    """The suite mode name is one of FULL, COASTING, ATTITUDE_ONLY, NONE, and
    every published position, attitude and height value is finite -- on every
    suite snapshot parsed in this session and on a pad of its own. A
    violation fails this test only.
    """
    from _harness import require_no_product_issues

    lat, lon, h, origin = _site()
    pad = pad_full(lat, lon, h, origin, baro=False, mag=True)
    for _kind, run in nav_langs(site_nav(lat, lon, h, pad)):
        assert run.snaps, "pad produced no snapshots"
    require_no_product_issues("F08", "suite snapshots (F08)")
