# feature: F04
"""Delayed aiding (FP-04).

Assertions stay at the PRD's precision: a GNSS, local-position, or yaw sample
that is older than the current IMU epoch is fused against the state that was
valid at that time of validity, not as if it had arrived now. On a moving
path a stated 200 ms GNSS delay has a smaller along-track error than the same
bytes fused at delay zero, and the delayed sample is fused rather than
skipped (an IMU-unexplained offset the skip path cannot take);
an in-window runtime delay does the same; after the vehicle has stopped,
a stated delay does not pull the published position back the way delay-zero
fusion of the expired position does, and that expired sample is fused
against an IMU-unexplained GNSS offset the skip path cannot take.
Delays up to 500 ms (including an 80 ms Python GNSS push) are fused this way
when history still holds the validity time; a 600 ms sample is not applied
as a current-time update and GNSS of that kind raises the no-anchor
diagnostic; an in-window delay with no history match is likewise not applied
as current-time, and GNSS of that kind also raises the diagnostic;
local-position and yaw of either skip stay on the locked tracker / heading
and do not raise that count; a later in-window sample with a history match
fuses (the skip is per sample). The Python replay estimator, forced on a
climb with usable GNSS vertical velocity and a barometer, reports a lag
matching the constructed lag between barometric vertical velocity and GNSS
vertical velocity, not silence, and a zero-lag climb is distinguishable.
Message text, exception types, history grid spacing, and millimetre gold
values are not pinned.
"""

from __future__ import annotations

from _harness import workspace
from F01_helpers import hypot3
from F02_helpers import ecef_from_llh_deg, runtime_site
from F03_helpers import TRACKER_NAMED_NED, angle_diff_rad
from F04_helpers import (
    ACCEL_S,
    IN_WINDOW_NO_HISTORY_MS,
    MOTION_S,
    NAMED_DELAY_80_MS,
    NAMED_DELAY_200_MS,
    NAMED_DELAY_500_MS,
    NAMED_DELAY_600_MS,
    STOP_BRAKE_S,
    STOP_CRUISE_S,
    accel_then_cruise_ned,
    along_track_error_m,
    apply_delay_after,
    c_delay_run,
    forced_replay_lag_ms,
    local_skip_scenario,
    moving_local_scenario,
    moving_north_truth,
    pad_then_moving_gnss,
    pad_then_offset_gnss,
    pad_then_stop_expired_gnss,
    py_delay_run,
    require_initialized_solution,
    require_ready_delay,
    runtime_in_window_delay_ms,
    runtime_north_speed,
    runtime_offset_north_m,
    runtime_tracker_b,
    runtime_unexplained_yaw_rad,
    runtime_yaw_rad,
    runtime_yaw_rate,
    shallow_prescribed_gnss,
    turning_yaw_scenario,
    write_climb_dataset,
    yaw_skip_scenario,
)


def _langs(scen):
    return (("c", c_delay_run(scen)), ("py", py_delay_run(scen)))


def _assert_stated_beats_zero(
    stated_err: float,
    zero_err: float,
    v_times_delay: float,
    what: str,
) -> None:
    """Delay-zero must be resolvable as v×delay; stated delay must be smaller."""
    a0 = abs(zero_err)
    a1 = abs(stated_err)
    print(
        f"{what}: |err_stated|={a1:.3f} m |err_zero|={a0:.3f} m "
        f"v*delay={v_times_delay:.3f} m",
        flush=True,
    )
    assert a0 > 0.35 * v_times_delay, (
        f"{what}: delay-zero along-track error {a0:.3f} m is not resolvable "
        f"against v×delay {v_times_delay:.3f} m"
    )
    assert a1 < a0, (
        f"{what}: stated delay error {a1:.3f} m is not smaller than delay-zero {a0:.3f} m"
    )


def _assert_offset_fused_not_skipped(
    stated_err: float,
    offset_span: float,
    what: str,
    max_frac: float = 0.45,
) -> None:
    """Skip of a delayed sample cannot take an IMU-unexplained offset."""
    span = abs(offset_span)
    a = abs(stated_err)
    print(
        f"{what}: |err_stated|={a:.4f} unexplained_offset={span:.4f} "
        f"max_frac={max_frac}",
        flush=True,
    )
    assert span > 0.0, f"{what}: IMU-unexplained offset must be non-zero"
    assert a < max_frac * span, (
        f"{what}: stated error {a:.4f} is not inside {max_frac} of the "
        f"IMU-unexplained offset {span:.4f}; delayed sample looks skipped"
    )


def _last_ready(run, what: str):
    snap = run.last()
    require_ready_delay(snap, what)
    return snap


# ---------------------------------------------------------------------------
# A. Moving GNSS, stated delay vs delay zero
# ---------------------------------------------------------------------------


def test_stated_200ms_gnss_delay_beats_delay_zero_on_moving_path():
    lat, lon, h = runtime_site()
    v = runtime_north_speed()
    delay_ms = NAMED_DELAY_200_MS
    offset = runtime_offset_north_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    stated = pad_then_moving_gnss(
        lat, lon, h, delay_ms=delay_ms, v_north=v, north_offset_m=offset
    )
    zero = apply_delay_after(stated, stated.probe_after_t_us, gnss_ms=0)
    t_s = (stated.epochs[-1].t_us - stated.probe_after_t_us) * 1.0e-6
    north, _ = accel_then_cruise_ned(t_s, v)
    truth = moving_north_truth(origin, north + offset)
    imu_path = moving_north_truth(origin, north)
    vdt = v * delay_ms * 1.0e-3
    for kind, run in _langs(stated):
        snap = _last_ready(run, f"{kind} 200 ms stated")
        err = along_track_error_m(snap.ecef, truth, origin)
        zrun = c_delay_run(zero) if kind == "c" else py_delay_run(zero)
        zsnap = _last_ready(zrun, f"{kind} 200 ms delay-zero")
        zerr = along_track_error_m(zsnap.ecef, truth, origin)
        _assert_stated_beats_zero(err, zerr, vdt, f"{kind} 200 ms GNSS")
        d_gnss = hypot3(snap.ecef, truth)
        d_imu = hypot3(snap.ecef, imu_path)
        print(
            f"{kind} 200 ms GNSS: |ecef-offset-path|={d_gnss:.3f} "
            f"|ecef-imu|={d_imu:.3f}",
            flush=True,
        )
        assert d_gnss < d_imu, (
            f"{kind}: 200 ms stated delay stayed on the IMU path "
            f"({d_gnss:.3f} m from GNSS offset, {d_imu:.3f} m from IMU); "
            "delayed sample looks skipped"
        )
        _assert_offset_fused_not_skipped(err, offset, f"{kind} 200 ms GNSS")


def test_runtime_in_window_gnss_delay_beats_delay_zero():
    lat, lon, h = runtime_site()
    v = runtime_north_speed()
    delay_ms = runtime_in_window_delay_ms()
    offset = runtime_offset_north_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    stated = pad_then_moving_gnss(
        lat, lon, h, delay_ms=delay_ms, v_north=v, north_offset_m=offset
    )
    zero = apply_delay_after(stated, stated.probe_after_t_us, gnss_ms=0)
    t_s = (stated.epochs[-1].t_us - stated.probe_after_t_us) * 1.0e-6
    north, _ = accel_then_cruise_ned(t_s, v)
    truth = moving_north_truth(origin, north + offset)
    imu_path = moving_north_truth(origin, north)
    vdt = v * delay_ms * 1.0e-3
    for kind, run in _langs(stated):
        snap = _last_ready(run, f"{kind} runtime stated")
        err = along_track_error_m(snap.ecef, truth, origin)
        zrun = c_delay_run(zero) if kind == "c" else py_delay_run(zero)
        zsnap = _last_ready(zrun, f"{kind} runtime delay-zero")
        zerr = along_track_error_m(zsnap.ecef, truth, origin)
        _assert_stated_beats_zero(err, zerr, vdt, f"{kind} runtime in-window GNSS")
        d_gnss = hypot3(snap.ecef, truth)
        d_imu = hypot3(snap.ecef, imu_path)
        print(
            f"{kind} runtime GNSS: |ecef-offset-path|={d_gnss:.3f} "
            f"|ecef-imu|={d_imu:.3f}",
            flush=True,
        )
        assert d_gnss < d_imu, (
            f"{kind}: in-window stated delay stayed on the IMU path; "
            "delayed sample looks skipped"
        )
        _assert_offset_fused_not_skipped(err, offset, f"{kind} runtime in-window GNSS")


def test_stated_delay_after_stop_does_not_pull_like_delay_zero():
    lat, lon, h = runtime_site()
    v = runtime_north_speed()
    delay_ms = NAMED_DELAY_200_MS
    offset = runtime_offset_north_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    stated = pad_then_stop_expired_gnss(
        lat, lon, h, delay_ms=delay_ms, v_north=v, north_offset_m=offset
    )
    zero = apply_delay_after(stated, stated.probe_after_t_us, gnss_ms=0)
    north_cruise, _ = accel_then_cruise_ned(ACCEL_S + STOP_CRUISE_S, v)
    north_stop = north_cruise + 0.5 * v * STOP_BRAKE_S
    truth_stop = moving_north_truth(origin, north_stop)
    truth_fused = moving_north_truth(origin, north_stop + offset)
    vdt = v * delay_ms * 1.0e-3
    for kind, run in _langs(stated):
        snap = _last_ready(run, f"{kind} after-stop stated")
        err = along_track_error_m(snap.ecef, truth_fused, origin)
        zrun = c_delay_run(zero) if kind == "c" else py_delay_run(zero)
        zsnap = _last_ready(zrun, f"{kind} after-stop delay-zero")
        zerr = along_track_error_m(zsnap.ecef, truth_fused, origin)
        d_off = hypot3(snap.ecef, truth_fused)
        d_imu = hypot3(snap.ecef, truth_stop)
        print(
            f"{kind} after-stop: stated_err={err:.3f} zero_err={zerr:.3f} "
            f"v*delay={vdt:.3f} offset={offset:.3f} "
            f"|ecef-offset|={d_off:.3f} |ecef-imu|={d_imu:.3f} "
            f"n_no_anchor stated={snap.n_no_anchor} zero={zsnap.n_no_anchor}",
            flush=True,
        )
        assert abs(zerr) > 0.20 * vdt, (
            f"{kind}: delay-zero after stop did not pull toward the expired "
            f"position (error {zerr:.3f} m vs {vdt:.3f} m)"
        )
        assert abs(err) < abs(zerr), (
            f"{kind}: stated delay after stop pulled like delay-zero "
            f"({err:.3f} vs {zerr:.3f} m)"
        )
        # One delayed sample: skip stays at the IMU stop (error ≈ offset).
        # Fusion takes a visible fraction of that offset; 0.80 leaves room
        # for a single-update Kalman pull while still failing a skip.
        _assert_offset_fused_not_skipped(
            err, offset, f"{kind} after-stop GNSS", max_frac=0.80
        )


# ---------------------------------------------------------------------------
# B. 80 / 500 / 600 ms
# ---------------------------------------------------------------------------


def test_python_80ms_delayed_gnss_is_accepted():
    lat, lon, h = runtime_site()
    north = runtime_offset_north_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    offset = moving_north_truth(origin, north)
    scen = pad_then_offset_gnss(lat, lon, h, delay_ms=NAMED_DELAY_80_MS, north_m=north)
    # Python is the named entry; C must accept 80 ms the same way.
    for kind, run in (("py", py_delay_run(scen)), ("c", c_delay_run(scen))):
        pad = run.last_before(scen.probe_after_t_us)
        last = _last_ready(run, f"{kind} 80 ms")
        d_off = hypot3(last.ecef, offset)
        d_pad = hypot3(last.ecef, origin)
        d_pad_to_off = hypot3(origin, offset)
        print(
            f"{kind} 80 ms: |ecef-offset|={d_off:.3f} |ecef-pad|={d_pad:.3f} "
            f"pad-offset={d_pad_to_off:.3f} n_no_anchor pad={pad.n_no_anchor} "
            f"last={last.n_no_anchor}",
            flush=True,
        )
        assert d_off < d_pad, (
            f"{kind}: 80 ms delayed GNSS did not pull toward the offset "
            f"relative to the unmoved pad"
        )
        assert d_off < 0.55 * d_pad_to_off, (
            f"{kind}: 80 ms delayed GNSS stayed {d_off:.3f} m from the offset"
        )
        assert last.n_no_anchor == pad.n_no_anchor, (
            f"{kind}: 80 ms in-window GNSS raised no-anchor "
            f"{pad.n_no_anchor} -> {last.n_no_anchor}"
        )


def test_500ms_delay_beats_delay_zero_on_moving_path():
    lat, lon, h = runtime_site()
    v = runtime_north_speed()
    delay_ms = NAMED_DELAY_500_MS
    offset = runtime_offset_north_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    stated = pad_then_moving_gnss(
        lat,
        lon,
        h,
        delay_ms=delay_ms,
        v_north=v,
        motion_s=MOTION_S,
        north_offset_m=offset,
    )
    zero = apply_delay_after(stated, stated.probe_after_t_us, gnss_ms=0)
    t_s = (stated.epochs[-1].t_us - stated.probe_after_t_us) * 1.0e-6
    north, _ = accel_then_cruise_ned(t_s, v)
    truth = moving_north_truth(origin, north + offset)
    imu_path = moving_north_truth(origin, north)
    vdt = v * delay_ms * 1.0e-3
    for kind, run in _langs(stated):
        snap = _last_ready(run, f"{kind} 500 ms stated")
        err = along_track_error_m(snap.ecef, truth, origin)
        zrun = c_delay_run(zero) if kind == "c" else py_delay_run(zero)
        zsnap = _last_ready(zrun, f"{kind} 500 ms delay-zero")
        zerr = along_track_error_m(zsnap.ecef, truth, origin)
        _assert_stated_beats_zero(err, zerr, vdt, f"{kind} 500 ms GNSS")
        d_gnss = hypot3(snap.ecef, truth)
        d_imu = hypot3(snap.ecef, imu_path)
        print(
            f"{kind} 500 ms GNSS: |ecef-offset-path|={d_gnss:.3f} "
            f"|ecef-imu|={d_imu:.3f}",
            flush=True,
        )
        assert d_gnss < d_imu, (
            f"{kind}: 500 ms stated delay stayed on the IMU path; "
            "delayed sample looks skipped"
        )
        _assert_offset_fused_not_skipped(err, offset, f"{kind} 500 ms GNSS")


def test_600ms_gnss_not_applied_as_current_no_anchor():
    lat, lon, h = runtime_site()
    north = runtime_offset_north_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    offset = moving_north_truth(origin, north)
    over = pad_then_offset_gnss(
        lat, lon, h, delay_ms=NAMED_DELAY_600_MS, north_m=north, extra_s=2.0
    )
    live = pad_then_offset_gnss(
        lat, lon, h, delay_ms=0, north_m=north, extra_s=2.0
    )
    for kind in ("c", "py"):
        skipped = c_delay_run(over) if kind == "c" else py_delay_run(over)
        pulled = c_delay_run(live) if kind == "c" else py_delay_run(live)
        before = skipped.last_before(over.probe_after_t_us)
        after = skipped.last()
        live_last = _last_ready(pulled, f"{kind} 600 live delay-zero")
        require_initialized_solution(after, f"{kind} 600 skip")
        d_skip = hypot3(after.ecef, offset)
        d_live = hypot3(live_last.ecef, offset)
        d_pad = hypot3(after.ecef, origin)
        span = hypot3(origin, offset)
        print(
            f"{kind} 600 ms: skip|offset|={d_skip:.3f} live|offset|={d_live:.3f} "
            f"skip|pad|={d_pad:.3f} span={span:.3f} "
            f"no_anchor {before.n_no_anchor}->{after.n_no_anchor} "
            f"live_no_anchor={live_last.n_no_anchor}",
            flush=True,
        )
        assert d_live < 0.45 * span, (
            f"{kind}: delay-zero did not pull toward the offset ({d_live:.3f} m of {span:.3f} m)"
        )
        assert d_skip > 0.55 * span, (
            f"{kind}: 600 ms was applied as a current-time update "
            f"({d_skip:.3f} m from the offset, span {span:.3f} m)"
        )
        assert after.n_no_anchor > before.n_no_anchor, (
            f"{kind}: 600 ms GNSS did not raise the no-anchor diagnostic "
            f"({before.n_no_anchor} -> {after.n_no_anchor})"
        )


def test_in_window_sample_fuses_after_600ms_drop():
    lat, lon, h = runtime_site()
    north_drop = runtime_offset_north_m()
    north_ok = north_drop + 3.5
    origin = ecef_from_llh_deg(lat, lon, h)
    later = moving_north_truth(origin, north_ok)
    scen = pad_then_offset_gnss(
        lat,
        lon,
        h,
        delay_ms=NAMED_DELAY_600_MS,
        north_m=north_drop,
        extra_s=1.2,
        then_delay_ms=NAMED_DELAY_80_MS,
        then_north_m=north_ok,
        then_s=2.0,
    )
    for kind, run in _langs(scen):
        last = _last_ready(run, f"{kind} after 600 recover")
        d_later = hypot3(last.ecef, later)
        d_pad = hypot3(last.ecef, origin)
        print(
            f"{kind} recover after 600: |ecef-later|={d_later:.3f} "
            f"|ecef-pad|={d_pad:.3f} n_no_anchor={last.n_no_anchor}",
            flush=True,
        )
        assert d_later < d_pad, (
            f"{kind}: in-window sample after a 600 ms drop did not fuse "
            f"(stayed {d_later:.3f} m from the new offset, {d_pad:.3f} m from the pad)"
        )


# ---------------------------------------------------------------------------
# C. In-window, no history; local / yaw skip; later fuse
# ---------------------------------------------------------------------------


def test_in_window_gnss_without_history_not_current_no_anchor():
    lat, lon, h = runtime_site()
    north = runtime_offset_north_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    offset = moving_north_truth(origin, north)
    delay_ms = IN_WINDOW_NO_HISTORY_MS
    delayed = shallow_prescribed_gnss(
        lat, lon, h, delay_ms=delay_ms, north_m=north
    )
    current = apply_delay_after(delayed, delayed.probe_after_t_us, gnss_ms=0)
    for kind in ("c", "py"):
        skip = c_delay_run(delayed) if kind == "c" else py_delay_run(delayed)
        live = c_delay_run(current) if kind == "c" else py_delay_run(current)
        require_initialized_solution(skip.last(), f"{kind} no-history skip")
        require_initialized_solution(live.last(), f"{kind} no-history live")
        before = skip.last_before(delayed.probe_after_t_us)
        after = skip.last()
        d_skip = hypot3(after.ecef, offset)
        d_live = hypot3(live.last().ecef, offset)
        print(
            f"{kind} in-window no history: skip|offset|={d_skip:.3f} "
            f"live|offset|={d_live:.3f} no_anchor {before.n_no_anchor}->{after.n_no_anchor} "
            f"live_no_anchor={live.last().n_no_anchor}",
            flush=True,
        )
        assert d_live < d_skip, (
            f"{kind}: delay-zero on the same shallow history did not pull toward "
            f"the offset"
        )
        assert after.n_no_anchor > before.n_no_anchor, (
            f"{kind}: in-window GNSS with no history match did not raise no-anchor"
        )


def test_local_skip_without_no_anchor():
    lat, lon, h = runtime_site()
    tracker_b = runtime_tracker_b()
    a = TRACKER_NAMED_NED
    cases = (
        ("no-match", True, IN_WINDOW_NO_HISTORY_MS),
        ("over-max", False, NAMED_DELAY_600_MS),
    )
    for kind_name, shallow, delay_ms in cases:
        skip_scen = local_skip_scenario(
            lat, lon, h, a, tracker_b, delay_ms=delay_ms, shallow=shallow
        )
        live_scen = apply_delay_after(skip_scen, skip_scen.probe_after_t_us, local_ms=0)
        for kind in ("c", "py"):
            skipped = c_delay_run(skip_scen) if kind == "c" else py_delay_run(skip_scen)
            live = c_delay_run(live_scen) if kind == "c" else py_delay_run(live_scen)
            before = skipped.last_before(skip_scen.probe_after_t_us)
            after = skipped.last()
            require_initialized_solution(after, f"{kind} local skip {kind_name}")
            require_initialized_solution(live.last(), f"{kind} local live {kind_name}")
            d_skip_a = hypot3(after.ned, a)
            d_skip_b = hypot3(after.ned, tracker_b)
            d_live_b = hypot3(live.last().ned, tracker_b)
            d_live_a = hypot3(live.last().ned, a)
            print(
                f"{kind} local {kind_name}: skip|A|={d_skip_a:.4f} skip|B|={d_skip_b:.4f} "
                f"live|B|={d_live_b:.4f} live|A|={d_live_a:.4f} "
                f"no_anchor {before.n_no_anchor}->{after.n_no_anchor}",
                flush=True,
            )
            assert d_live_b < d_live_a, (
                f"{kind} local {kind_name}: delay-zero did not follow tracker B"
            )
            assert d_skip_a < d_skip_b, (
                f"{kind} local {kind_name}: skip did not stay closer to A than B"
            )
            assert d_skip_a < d_live_b + 0.25, (
                f"{kind} local {kind_name}: skip drifted off A "
                f"({d_skip_a:.3f} m) more than delay-zero followed B ({d_live_b:.3f} m)"
            )
            assert after.n_no_anchor == before.n_no_anchor, (
                f"{kind} local {kind_name}: skip raised no-anchor "
                f"{before.n_no_anchor} -> {after.n_no_anchor}"
            )


def test_yaw_skip_without_no_anchor():
    lat, lon, h = runtime_site()
    yaw0 = runtime_yaw_rad()
    yaw1 = yaw0 + 0.85
    cases = (
        ("no-match", True, IN_WINDOW_NO_HISTORY_MS),
        ("over-max", False, NAMED_DELAY_600_MS),
    )
    for kind_name, shallow, delay_ms in cases:
        skip_scen = yaw_skip_scenario(
            lat, lon, h, yaw0, yaw1, delay_ms=delay_ms, shallow=shallow
        )
        live_scen = apply_delay_after(skip_scen, skip_scen.probe_after_t_us, yaw_ms=0)
        for kind in ("c", "py"):
            skipped = c_delay_run(skip_scen) if kind == "c" else py_delay_run(skip_scen)
            live = c_delay_run(live_scen) if kind == "c" else py_delay_run(live_scen)
            before = skipped.last_before(skip_scen.probe_after_t_us)
            after = skipped.last()
            require_initialized_solution(after, f"{kind} yaw skip {kind_name}")
            require_initialized_solution(live.last(), f"{kind} yaw live {kind_name}")
            d_skip_old = abs(angle_diff_rad(after.rpy[2], yaw0))
            d_skip_new = abs(angle_diff_rad(after.rpy[2], yaw1))
            d_live_new = abs(angle_diff_rad(live.last().rpy[2], yaw1))
            d_live_old = abs(angle_diff_rad(live.last().rpy[2], yaw0))
            print(
                f"{kind} yaw {kind_name}: skip|old|={d_skip_old:.4f} "
                f"skip|new|={d_skip_new:.4f} live|new|={d_live_new:.4f} "
                f"live|old|={d_live_old:.4f} no_anchor "
                f"{before.n_no_anchor}->{after.n_no_anchor}",
                flush=True,
            )
            assert d_live_new < d_live_old, (
                f"{kind} yaw {kind_name}: delay-zero did not follow the new heading"
            )
            assert d_skip_old < d_skip_new, (
                f"{kind} yaw {kind_name}: skip did not stay closer to the locked heading"
            )
            assert d_skip_old < d_live_new + 0.15, (
                f"{kind} yaw {kind_name}: skip drifted off the locked heading"
            )
            assert after.n_no_anchor == before.n_no_anchor, (
                f"{kind} yaw {kind_name}: skip raised no-anchor"
            )


def test_later_in_window_sample_fuses_after_skip():
    lat, lon, h = runtime_site()
    north = runtime_offset_north_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    offset = moving_north_truth(origin, north)
    delay_ms = IN_WINDOW_NO_HISTORY_MS
    scen = shallow_prescribed_gnss(
        lat,
        lon,
        h,
        delay_ms=delay_ms,
        north_m=north,
        then_fill_s=0.8,
        then_same_delay=True,
    )
    for kind, run in _langs(scen):
        last = run.last()
        require_initialized_solution(last, f"{kind} later in-window")
        d_off = hypot3(last.ecef, offset)
        d_pad = hypot3(last.ecef, origin)
        print(
            f"{kind} later in-window: |ecef-offset|={d_off:.3f} |ecef-pad|={d_pad:.3f} "
            f"n_no_anchor={last.n_no_anchor}",
            flush=True,
        )
        assert d_off < d_pad, (
            f"{kind}: later in-window sample with a history match did not fuse"
        )


# ---------------------------------------------------------------------------
# D. Local position and yaw fused at time of validity
# ---------------------------------------------------------------------------


def test_stated_local_pos_delay_beats_delay_zero_when_moving():
    lat, lon, h = runtime_site()
    v = 1.8 + runtime_north_speed() * 0.02
    delay_ms = NAMED_DELAY_200_MS
    # Several tenths of a metre, well above the tracker 1-sigma, small enough
    # that a delayed fuse is not an indoor-glitch skip of a 5 m / 1 cm step.
    offset = 0.85 + runtime_offset_north_m() * 0.05
    start = TRACKER_NAMED_NED
    stated = moving_local_scenario(
        lat,
        lon,
        h,
        delay_ms=delay_ms,
        v_north=v,
        north_offset_m=offset,
        local_std=(0.12, 0.12, 0.12),
    )
    zero = apply_delay_after(stated, stated.probe_after_t_us, local_ms=0)
    t_s = (stated.epochs[-1].t_us - stated.probe_after_t_us) * 1.0e-6
    north, _ = accel_then_cruise_ned(t_s, v)
    truth = (start[0] + north + offset, start[1], start[2])
    imu_n = start[0] + north
    vdt = v * delay_ms * 1.0e-3
    for kind, run in _langs(stated):
        snap = _last_ready(run, f"{kind} local stated")
        err = snap.ned[0] - truth[0]
        zrun = c_delay_run(zero) if kind == "c" else py_delay_run(zero)
        zsnap = _last_ready(zrun, f"{kind} local delay-zero")
        zerr = zsnap.ned[0] - truth[0]
        print(
            f"{kind} local moving: stated_n_err={err:.3f} zero_n_err={zerr:.3f} "
            f"v*delay={vdt:.3f} n={snap.ned[0]:.3f} imu_n={imu_n:.3f} "
            f"offset={offset:.3f}",
            flush=True,
        )
        assert abs(zerr) > 0.30 * vdt, (
            f"{kind}: local delay-zero along-track error {zerr:.3f} m is not "
            f"resolvable against v×delay {vdt:.3f} m"
        )
        assert abs(err) < abs(zerr), (
            f"{kind}: stated local delay was not closer to the moving tracker"
        )
        assert abs(snap.ned[0] - truth[0]) < abs(snap.ned[0] - imu_n), (
            f"{kind}: stated local delay stayed on the IMU tracker path; "
            "delayed sample looks skipped"
        )
        _assert_offset_fused_not_skipped(err, offset, f"{kind} local moving")


def test_stated_yaw_delay_beats_delay_zero_while_turning():
    lat, lon, h = runtime_site()
    yaw0 = runtime_yaw_rad()
    rate = runtime_yaw_rate()
    delay_ms = NAMED_DELAY_200_MS
    # Larger than yaw 1-sigma, smaller than rate×delay so delay-zero's lag
    # versus current true heading stays resolvable.
    yaw_off = 0.055 + (runtime_unexplained_yaw_rad() - 0.35) * 0.10
    stated = turning_yaw_scenario(
        lat,
        lon,
        h,
        delay_ms=delay_ms,
        yaw0=yaw0,
        rate=rate,
        yaw_offset_rad=yaw_off,
        yaw_std=0.012,
    )
    zero = apply_delay_after(stated, stated.probe_after_t_us, yaw_ms=0)
    t_s = (stated.epochs[-1].t_us - stated.probe_after_t_us) * 1.0e-6
    yaw_gyro = yaw0 + rate * t_s
    yaw_fused = yaw_gyro + yaw_off
    lag = rate * delay_ms * 1.0e-3
    for kind, run in _langs(stated):
        snap = _last_ready(run, f"{kind} yaw stated")
        err_gyro = abs(angle_diff_rad(snap.rpy[2], yaw_gyro))
        err_off = abs(angle_diff_rad(snap.rpy[2], yaw_fused))
        zrun = c_delay_run(zero) if kind == "c" else py_delay_run(zero)
        zsnap = _last_ready(zrun, f"{kind} yaw delay-zero")
        zerr_gyro = abs(angle_diff_rad(zsnap.rpy[2], yaw_gyro))
        zerr_off = abs(angle_diff_rad(zsnap.rpy[2], yaw_fused))
        print(
            f"{kind} yaw turning: stated|gyro|={err_gyro:.4f} "
            f"stated|offset-hdg|={err_off:.4f} zero|gyro|={zerr_gyro:.4f} "
            f"zero|offset-hdg|={zerr_off:.4f} rate*delay={lag:.4f} "
            f"offset={yaw_off:.4f}",
            flush=True,
        )
        # Live baseline: delay-zero is lagged by about rate×delay from the
        # current offset heading, not from gyro-only heading (|offset−lag|).
        assert zerr_off > 0.35 * lag, (
            f"{kind}: delay-zero yaw is not lagged by about rate×delay "
            f"({zerr_off:.4f} vs {lag:.4f} rad) relative to current true heading"
        )
        assert err_off < err_gyro, (
            f"{kind}: stated yaw delay stayed on gyro integration; "
            "delayed sample looks skipped"
        )
        _assert_offset_fused_not_skipped(err_off, yaw_off, f"{kind} yaw turning")
        assert err_off < zerr_off, (
            f"{kind}: stated yaw delay is not closer to the time-of-validity "
            f"heading than delay-zero"
        )


# ---------------------------------------------------------------------------
# E. Replay GNSS-latency estimator
# ---------------------------------------------------------------------------


def test_replay_estimator_reports_peak_lag_on_climb():
    lat, lon, h = runtime_site()
    constructed_ms = float(NAMED_DELAY_200_MS)
    with workspace() as ws:
        dest = write_climb_dataset(
            ws, lat_deg=lat, lon_deg=lon, h0_m=h, lag_s=constructed_ms * 1.0e-3
        )
        lag = forced_replay_lag_ms(dest)
    print(
        f"climb estimator lag={lag} constructed={constructed_ms}",
        flush=True,
    )
    assert abs(lag) > 40.0, (
        f"forced estimator reported {lag}, which is silence-or-zero on a climb"
    )
    assert abs(lag - constructed_ms) < 80.0, (
        f"forced estimator lag {lag} does not match the constructed "
        f"{constructed_ms} GNSS vertical-velocity lag"
    )


def test_replay_estimator_lag_tracks_constructed_gnss_lag():
    lat, lon, h = runtime_site()
    delay_ms = runtime_in_window_delay_ms()
    with workspace() as ws:
        delayed = write_climb_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h0_m=h,
            lag_s=delay_ms * 1.0e-3,
            relpath="climb-delay",
        )
        aligned = write_climb_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h0_m=h,
            lag_s=0.0,
            relpath="climb-aligned",
        )
        lag_d = forced_replay_lag_ms(delayed)
        lag_0 = forced_replay_lag_ms(aligned)
    print(
        f"constructed={delay_ms} reported_delay={lag_d} reported_zero={lag_0}",
        flush=True,
    )
    assert abs(lag_d - delay_ms) < 80.0, (
        f"estimator {lag_d} does not track constructed lag {delay_ms}"
    )
    assert abs(lag_0 - lag_d) > 40.0, (
        f"zero-lag climb still reported {lag_0}, not distinguishable from {lag_d}"
    )
    assert abs(lag_0) < abs(lag_d), (
        f"zero-lag climb reported {lag_0} which is not smaller than the "
        f"delayed report {lag_d}"
    )


def test_published_delay_snapshots_are_well_formed():
    """Published values are finite, attitude is not published without its
    1-sigma, ``ins_get_diag`` / ``diag`` expose non-negative counters
    (``n_gnss_no_anchor``, ``n_gnss_used``) -- on every delay snapshot parsed
    in this session and on a delayed-GNSS run of its own. A violation fails
    this test only.
    """
    from _harness import require_no_product_issues

    lat, lon, h = runtime_site()
    scen = pad_then_moving_gnss(
        lat,
        lon,
        h,
        delay_ms=NAMED_DELAY_200_MS,
        v_north=runtime_north_speed(),
        north_offset_m=runtime_offset_north_m(),
    )
    for _kind, run in _langs(scen):
        assert run.snaps, "delayed-GNSS run produced no snapshots"
    require_no_product_issues("F04", "delay snapshots (F04)")
