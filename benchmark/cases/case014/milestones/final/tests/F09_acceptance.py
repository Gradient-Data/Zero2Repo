# feature: F09
"""Input sanitization, outliers, and fail-safe outputs (FP-09).

Assertions stay at the PRD's precision: non-finite payloads are dropped and
counted as invalid input; the next finite epoch still produces a finite ready
solution; persistent absolute references are downweighted rather than rejected;
the override fuses at nominal variance with no downweight increment; zero-velocity
and zero-rotation updates are not statistically gated; diagnostic classes are
readable and distinguishable and are not acted on. Message text, exception
types, counter field spellings, chi-square thresholds, and this checkout's
500 m table are not pinned.
"""

from __future__ import annotations

import math

from F01_helpers import hypot3
from F02_helpers import (
    DT_SEC,
    IMU_HZ,
    LEVER_RIGHT_15CM,
    SPECIFIC_FORCE_LEVEL,
    ecef_from_llh_deg,
    ecef_plus_ned,
    runtime_gnss_step_m,
    runtime_site,
)
from F03_helpers import (
    G_MPS2,
    WMM_YEAR,
    angle_diff_rad,
    body_mag_for_yaw,
    ned_field_from_independent_wmm,
    runtime_heading_rad,
    still_level_acc,
)
from F05_helpers import FREEZE_11S, UNFUSABLE_POS_STD, dist_m, north_of
from F06_helpers import runtime_att_yaw_rad
from F07_helpers import tropospheric_isa_pressure_pa
from F09_helpers import (
    ABSURD_NORTH_ACC,
    ABSURD_Z_RATE_RPS,
    LARGE_IMU_PSD,
    LONG_WINDOW_S,
    MAG_EVERY_SAMPLE_MS,
    MAG_VAR,
    SHORT_WINDOW_S,
    YAW_TIGHT_STD_RAD,
    HygieneEpoch,
    c_att_override_run,
    c_hygiene_run,
    c_suite_hygiene_run,
    c_vert_override_run,
    hygiene_append,
    hygiene_pad,
    hygiene_site,
    last_at_or_before,
    py_hygiene_run,
    replay_ecef_rows,
    outlier_replay_step_rows,
    require_finite_published,
    require_ready_hygiene,
    runtime_hygiene_cross_vel_mps,
    runtime_hygiene_weather_isa_m,
    runtime_local_glitch_ned,
    runtime_local_step_m,
    runtime_outlier_north_m,
    runtime_yaw_outlier_rad,
    snap_at,
    suite_hygiene_langs,
    window_mean,
    window_min,
    wrap_pi,
    write_outlier_replay_dataset,
)
from _harness import workspace


_LANGS = (("c", c_hygiene_run), ("py", py_hygiene_run))


# Full-weight (override) versus downweighted arms are scored on the mean
# error over the whole post-step window, not at one final instant: a
# nominal-variance fusion of a large step may overshoot the step late in
# the window (the static IMU drives the velocity state) while following it
# far closer than the downweighted arm over the window. An override that
# does not change fusion leaves the two means equal and still fails.


def _ecef_err(target):
    def err(snap):
        return None if snap.ecef is None else dist_m(snap.ecef, target)
    return err


def _yaw_err(target):
    def err(snap):
        return None if snap.att is None else abs(angle_diff_rad(snap.att[2], target))
    return err


def _h_err(target):
    def err(snap):
        return None if (not snap.h_ok or snap.h is None) else abs(snap.h - target)
    return err


def _site():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    print(f"F09 site lat={lat} lon={lon} h={h}", flush=True)
    return lat, lon, h, origin


def _step_ecef(origin):
    dn, de, dd = runtime_gnss_step_m()
    stepped = ecef_plus_ned(origin, dn, de, dd)
    print(f"F09 GNSS step n={dn} e={de} d={dd}", flush=True)
    return stepped


def _continue(epochs, origin, gnss_ecef, duration_s=2.0, **kwargs):
    return hygiene_append(
        epochs, duration_s=duration_s, origin=origin, gnss_ecef=gnss_ecef, **kwargs
    )


def _insert_epoch(epochs, **kwargs) -> tuple[list, int]:
    t_us = epochs[-1].t_us + int(round(DT_SEC * 1e6))
    one = HygieneEpoch(t_us=t_us, dt_sec=DT_SEC, **kwargs)
    return epochs + [one], t_us


def _imu_only_burst(epochs, origin, *, acc, gyr=(0.0, 0.0, 0.0), duration_s=0.40):
    """A short GNSS-free burst so a dropped IMU payload is distinguishable from eating it."""
    burst = hygiene_append(
        list(epochs),
        duration_s=duration_s,
        origin=origin,
        gnss_ecef=None,
        acc=acc,
        gyr=gyr,
    )
    return burst, burst[-1].t_us


def test_nan_accelerometer_dropped_counter_increases_later_ready_finite():
    """One NaN accelerometer sample is dropped."""
    lat, lon, h, origin = _site()
    nan = float("nan")
    acc_drop = (ABSURD_NORTH_ACC[0], ABSURD_NORTH_ACC[1], nan)
    acc_finite = ABSURD_NORTH_ACC
    stepped = _step_ecef(origin)
    for kind, run_fn in _LANGS:
        pad = hygiene_pad(origin)
        t_pad = pad[-1].t_us
        drop_epochs, t_bad = _imu_only_burst(pad, origin, acc=acc_drop)
        drop_epochs = _continue(drop_epochs, origin, stepped)
        finite_epochs, t_finite = _imu_only_burst(list(pad), origin, acc=acc_finite)
        drop = run_fn(hygiene_site(lat, lon, h, drop_epochs))
        finite = run_fn(hygiene_site(lat, lon, h, finite_epochs))
        assert drop.init_ok, f"{kind}: drop arm failed init"
        assert finite.init_ok, f"{kind}: finite twin failed init"
        before = last_at_or_before(drop, t_pad)
        require_ready_hygiene(before, origin, f"{kind} pad before NaN acc")
        after_bad = snap_at(drop, t_bad)
        after_finite = snap_at(finite, t_finite)
        print(
            f"{kind} nan-acc invalid {before.n_invalid}->{after_bad.n_invalid} "
            f"drop_err={dist_m(after_bad.ecef, origin) if after_bad.ecef else None} "
            f"finite_err={dist_m(after_finite.ecef, origin) if after_finite.ecef else None}",
            flush=True,
        )
        assert after_bad.n_invalid > before.n_invalid, f"{kind}: invalid-input did not increase"
        require_finite_published(after_bad, f"{kind} after NaN acc")
        assert after_bad.ecef is not None and after_finite.ecef is not None
        assert dist_m(after_finite.ecef, origin) > dist_m(after_bad.ecef, origin) + 0.05, (
            f"{kind}: finite absurd specific force did not twist the solution relative to the drop"
        )
        last = drop.last()
        require_finite_published(last, f"{kind} later finite after NaN acc")
        frozen = dist_m(before.ecef, stepped)
        moved = dist_m(last.ecef, stepped)
        print(f"{kind} later GNSS pull frozen={frozen} moved={moved}", flush=True)
        assert moved + 0.2 < frozen, f"{kind}: later GNSS did not pull after the dropped sample"


def test_inf_and_nan_imu_components_dropped_filter_continues():
    lat, lon, h, origin = _site()
    stepped = _step_ecef(origin)
    inf = float("inf")
    nan = float("nan")
    cases = (
        ("inf-acc", (ABSURD_NORTH_ACC[0], inf, ABSURD_NORTH_ACC[2]), (0.0, 0.0, 0.0)),
        ("nan-gyr", SPECIFIC_FORCE_LEVEL, (nan, 0.0, ABSURD_Z_RATE_RPS)),
        ("inf-gyr", SPECIFIC_FORCE_LEVEL, (0.0, inf, ABSURD_Z_RATE_RPS)),
        ("all-nan-acc", (nan, nan, nan), (0.0, 0.0, 0.0)),
    )
    for kind, run_fn in _LANGS:
        for name, acc_bad, gyr_bad in cases:
            if name == "all-nan-acc":
                acc_fin = (0.0, 0.0, 0.0)
            elif acc_bad != SPECIFIC_FORCE_LEVEL:
                acc_fin = ABSURD_NORTH_ACC
            else:
                acc_fin = SPECIFIC_FORCE_LEVEL
            gyr_fin = (
                (0.0, 0.0, ABSURD_Z_RATE_RPS)
                if gyr_bad != (0.0, 0.0, 0.0)
                else (0.0, 0.0, 0.0)
            )
            pad = hygiene_pad(origin)
            t_pad = pad[-1].t_us
            drop_epochs, t_bad = _imu_only_burst(pad, origin, acc=acc_bad, gyr=gyr_bad)
            drop_epochs = _continue(drop_epochs, origin, stepped)
            fin_epochs, t_fin = _imu_only_burst(list(pad), origin, acc=acc_fin, gyr=gyr_fin)
            drop = run_fn(hygiene_site(lat, lon, h, drop_epochs))
            finite = run_fn(hygiene_site(lat, lon, h, fin_epochs))
            before = last_at_or_before(drop, t_pad)
            after = snap_at(drop, t_bad)
            after_fin = snap_at(finite, t_fin)
            print(
                f"{kind} {name} invalid {before.n_invalid}->{after.n_invalid}",
                flush=True,
            )
            assert after.n_invalid > before.n_invalid, f"{kind} {name}: invalid-input did not increase"
            require_finite_published(after, f"{kind} {name} after drop")
            if acc_bad != SPECIFIC_FORCE_LEVEL:
                assert after.ecef is not None and after_fin.ecef is not None
                if name != "all-nan-acc":
                    hs_drop = math.hypot(after.vel[0], after.vel[1]) if after.vel else 0.0
                    hs_fin = math.hypot(after_fin.vel[0], after_fin.vel[1]) if after_fin.vel else 0.0
                    print(
                        f"{kind} {name} hs_drop={hs_drop} hs_fin={hs_fin} "
                        f"d_drop={dist_m(after.ecef, origin)} d_fin={dist_m(after_fin.ecef, origin)}",
                        flush=True,
                    )
                    assert hs_fin > hs_drop + 0.15, (
                        f"{kind} {name}: finite fake specific force was not eaten on the twin"
                    )
                    assert dist_m(after_fin.ecef, origin) > dist_m(after.ecef, origin) + 0.05, (
                        f"{kind} {name}: finite fake specific force did not twist ECEF relative to the drop"
                    )
            if gyr_bad != (0.0, 0.0, 0.0):
                assert after.att is not None and after_fin.att is not None and before.att is not None
                dy_drop = abs(angle_diff_rad(after.att[2], before.att[2]))
                dy_fin = abs(angle_diff_rad(after_fin.att[2], before.att[2]))
                print(f"{kind} {name} dYaw drop={dy_drop} finite={dy_fin}", flush=True)
                assert dy_fin > dy_drop + 0.05, (
                    f"{kind} {name}: finite fake gyro was not eaten on the twin"
                )
            last = drop.last()
            require_finite_published(last, f"{kind} {name} later")
            assert dist_m(last.ecef, stepped) + 0.2 < dist_m(before.ecef, stepped), (
                f"{kind} {name}: later GNSS did not pull"
            )


def test_nonfinite_gnss_payload_dropped_not_downweighted():
    lat, lon, h, origin = _site()
    nan = float("nan")
    inf = float("inf")
    fake = north_of(origin, runtime_outlier_north_m())
    stepped = _step_ecef(origin)
    payloads = (
        ("nan-x", (nan, fake[1], fake[2])),
        ("inf-y", (fake[0], inf, fake[2])),
    )
    for kind, run_fn in _LANGS:
        for name, ecef_bad in payloads:
            pad = hygiene_pad(origin)
            drop_epochs, t_bad = _insert_epoch(
                pad, acc=SPECIFIC_FORCE_LEVEL, gnss_ecef=ecef_bad, gnss_std=(2.0, 2.0, 2.0)
            )
            drop_epochs = _continue(drop_epochs, origin, stepped)
            drop = run_fn(hygiene_site(lat, lon, h, drop_epochs))
            before = last_at_or_before(drop, t_bad - 1)
            after = snap_at(drop, t_bad)
            print(
                f"{kind} {name} invalid {before.n_invalid}->{after.n_invalid} "
                f"dw {before.n_downweighted}->{after.n_downweighted} "
                f"err={dist_m(after.ecef, origin) if after.ecef else None}",
                flush=True,
            )
            assert after.n_invalid > before.n_invalid, f"{kind} {name}: invalid-input did not increase"
            assert after.n_downweighted == before.n_downweighted, (
                f"{kind} {name}: non-finite GNSS was scored as a downweight"
            )
            require_ready_hygiene(after, origin, f"{kind} {name} stayed on pad")
            last = drop.last()
            assert dist_m(last.ecef, stepped) + 0.2 < dist_m(after.ecef, stepped), (
                f"{kind} {name}: later finite GNSS did not pull"
            )


def test_ins_nonfinite_aiding_payloads_dropped_and_counted():
    lat, lon, h, origin = _site()
    nan = float("nan")
    inf = float("inf")
    heading = runtime_heading_rad()
    mag_ned = ned_field_from_independent_wmm(lat, lon, WMM_YEAR)
    mag_pad = body_mag_for_yaw(0.0, 0.0, heading, mag_ned)
    mag_wrong = body_mag_for_yaw(0.0, 0.0, wrap_pi(heading + 1.8), mag_ned)
    mag_nan = (nan, mag_wrong[1], mag_wrong[2])
    stepped = _step_ecef(origin)
    local_fake = (0.45, nan, 0.0)
    local_fin = (0.45, 0.0, 0.0)
    cases = (
        ("gnss-vel", dict(gnss_vel=(3.0, nan, 0.0)), dict(gnss_vel=(3.0, 0.0, 0.0))),
        ("mag", dict(mag=mag_nan), dict(mag=mag_wrong)),
        ("yaw", dict(yaw_rad=nan, yaw_std=YAW_TIGHT_STD_RAD), dict(yaw_rad=0.0, yaw_std=YAW_TIGHT_STD_RAD)),
        ("local", dict(local_ned=local_fake), dict(local_ned=local_fin)),
        ("speed", dict(speed_mps=nan), dict(speed_mps=0.0)),
        ("vel-inf", dict(gnss_vel=(inf, 2.5, 0.0)), dict(gnss_vel=(0.0, 2.5, 0.0))),
    )
    for kind, run_fn in _LANGS:
        for name, bad_kw, fin_kw in cases:
            pad = hygiene_pad(origin, yaw_rad=heading, yaw_std=YAW_TIGHT_STD_RAD, mag=mag_pad)
            t_pad = pad[-1].t_us
            if name in ("gnss-vel", "vel-inf"):
                # Default GNSS fusion is rate-limited (~100 ms). A 10 ms insert
                # after a pad fix is skipped whole, so the finite twin never
                # eats the remaining finite axis. Coast past that window, then
                # offer velocity-only at the rate limit (no simultaneous origin
                # position, which would pin velocity).
                coast = hygiene_append(
                    list(pad), duration_s=0.20, origin=origin, gnss_ecef=None
                )
                drop_epochs = hygiene_append(
                    list(coast),
                    duration_s=1.20,
                    origin=origin,
                    gnss_ecef=origin,
                    gnss_hz=10,
                    gnss_vel_std=(0.4, 0.4, 0.4),
                    **bad_kw,
                )
                fin_epochs = hygiene_append(
                    list(coast),
                    duration_s=1.20,
                    origin=origin,
                    gnss_ecef=origin,
                    gnss_hz=10,
                    gnss_vel_std=(0.4, 0.4, 0.4),
                    **fin_kw,
                )
                t_bad = drop_epochs[-1].t_us
                t_fin = fin_epochs[-1].t_us
            elif name == "local":
                drop_epochs = hygiene_append(
                    list(pad), duration_s=0.80, origin=origin, gnss_ecef=origin, **bad_kw
                )
                fin_epochs = hygiene_append(
                    list(pad), duration_s=0.80, origin=origin, gnss_ecef=origin, **fin_kw
                )
                t_bad = drop_epochs[-1].t_us
                t_fin = fin_epochs[-1].t_us
            elif name in ("yaw", "mag"):
                hold_s = 2.0 if name == "yaw" else 0.80
                drop_epochs = hygiene_append(
                    list(pad), duration_s=hold_s, origin=origin, gnss_ecef=origin, **bad_kw
                )
                fin_epochs = hygiene_append(
                    list(pad), duration_s=hold_s, origin=origin, gnss_ecef=origin, **fin_kw
                )
                t_bad = drop_epochs[-1].t_us
                t_fin = fin_epochs[-1].t_us
            else:
                drop_epochs, t_bad = _insert_epoch(
                    pad, acc=SPECIFIC_FORCE_LEVEL, gnss_ecef=origin, **bad_kw
                )
                fin_epochs, t_fin = _insert_epoch(
                    list(pad), acc=SPECIFIC_FORCE_LEVEL, gnss_ecef=origin, **fin_kw
                )
            drop_epochs = _continue(
                drop_epochs, origin, stepped, yaw_rad=heading, yaw_std=YAW_TIGHT_STD_RAD, mag=mag_pad
            )
            # Velocity-only 3 m/s is a large innovation after a tight pad; the
            # sanitization contrast is NaN vs finite, so both arms fuse at
            # nominal variance. Mag/yaw keep the default gate.
            vel_override = name in ("gnss-vel", "vel-inf", "yaw", "local")
            drop = run_fn(
                hygiene_site(
                    lat,
                    lon,
                    h,
                    drop_epochs,
                    mag_delay_ms=MAG_EVERY_SAMPLE_MS,
                    chi2_disable=vel_override,
                )
            )
            finite = run_fn(
                hygiene_site(
                    lat,
                    lon,
                    h,
                    fin_epochs,
                    mag_delay_ms=MAG_EVERY_SAMPLE_MS,
                    chi2_disable=vel_override,
                )
            )
            before = last_at_or_before(drop, t_pad)
            after = snap_at(drop, t_bad)
            after_fin = snap_at(finite, t_fin)
            print(
                f"{kind} {name} invalid {before.n_invalid}->{after.n_invalid}",
                flush=True,
            )
            assert after.n_invalid > before.n_invalid, f"{kind} {name}: invalid-input did not increase"
            require_finite_published(after, f"{kind} {name} after drop")
            if name in ("gnss-vel", "vel-inf"):
                assert after.vel is not None and after_fin.vel is not None
                drop_speed = math.hypot(after.vel[0], after.vel[1])
                fin_speed = math.hypot(after_fin.vel[0], after_fin.vel[1])
                print(f"{kind} {name} |v| drop={drop_speed} finite={fin_speed}", flush=True)
                assert fin_speed > drop_speed + 0.08, (
                    f"{kind} {name}: finite fake GNSS velocity was not eaten on the twin"
                )
            if name == "local":
                assert after.ecef is not None and after_fin.ecef is not None
                fin_h = math.hypot((after_fin.ned or (0, 0, 0))[0], (after_fin.ned or (0, 0, 0))[1])
                drop_h = math.hypot((after.ned or (0.0, 0.0, 0.0))[0], (after.ned or (0.0, 0.0, 0.0))[1])
                print(f"{kind} {name} |ned| drop={drop_h} finite={fin_h}", flush=True)
                assert fin_h > 0.08, f"{kind} {name}: finite fake local twin did not move"
                assert drop_h + 0.05 < fin_h, (
                    f"{kind} {name}: dropped local still jumped like the finite fake"
                )
            if name in ("yaw", "mag"):
                assert after.att is not None and after_fin.att is not None and before.att is not None
                drop_dyaw = abs(angle_diff_rad(after.att[2], before.att[2]))
                fin_dyaw = abs(angle_diff_rad(after_fin.att[2], before.att[2]))
                print(f"{kind} {name} dYaw drop={drop_dyaw} finite={fin_dyaw}", flush=True)
                if name == "yaw":
                    assert fin_dyaw > drop_dyaw + 0.03, (
                        f"{kind} yaw: eating 0 did not move heading relative to drop"
                    )
            last = drop.last()
            require_finite_published(last, f"{kind} {name} later")
            assert dist_m(last.ecef, stepped) + 0.2 < dist_m(before.ecef, stepped), (
                f"{kind} {name}: later GNSS did not pull"
            )


def test_suite_successful_read_after_dropped_nan_is_finite():
    lat, lon, h, origin = _site()
    nan = float("nan")
    acc_drop = (ABSURD_NORTH_ACC[0], nan, ABSURD_NORTH_ACC[2])
    stepped = _step_ecef(origin)
    pad = hygiene_pad(origin)
    drop_epochs, t_bad = _imu_only_burst(pad, origin, acc=acc_drop)
    drop_epochs = _continue(drop_epochs, origin, stepped)
    fin_epochs, t_fin = _imu_only_burst(list(pad), origin, acc=ABSURD_NORTH_ACC)
    drop_runs = dict(suite_hygiene_langs(hygiene_site(lat, lon, h, drop_epochs)))
    fin_runs = dict(suite_hygiene_langs(hygiene_site(lat, lon, h, fin_epochs)))
    for kind, run in drop_runs.items():
        fin = fin_runs[kind]
        before = last_at_or_before(run, pad[-1].t_us)
        after = snap_at(run, t_bad)
        after_fin = snap_at(fin, t_fin)
        print(
            f"{kind} suite invalid {before.n_invalid}->{after.n_invalid} "
            f"pos={after.pos_ok} rpy={after.rpy_ok}",
            flush=True,
        )
        assert after.n_invalid > before.n_invalid, f"{kind}: suite invalid-input did not increase"
        assert after.pos_ok and after.ecef is not None, f"{kind}: suite position unpublished after drop"
        assert after.rpy_ok and after.att is not None, f"{kind}: suite attitude unpublished after drop"
        assert all(math.isfinite(v) for v in after.ecef), f"{kind}: suite ECEF after drop was not finite"
        assert all(math.isfinite(v) for v in after.att), f"{kind}: suite attitude after drop was not finite"
        assert dist_m(after_fin.ecef, origin) > dist_m(after.ecef, origin) + 0.05, (
            f"{kind}: suite finite absurd specific force did not twist relative to the drop"
        )
        last = run.last()
        assert last.pos_ok and last.ecef is not None
        assert last.rpy_ok and last.att is not None
        assert all(math.isfinite(v) for v in last.ecef), f"{kind}: later suite ECEF was not finite"
        assert all(math.isfinite(v) for v in last.att), f"{kind}: later suite attitude was not finite"
        assert dist_m(last.ecef, stepped) + 0.2 < dist_m(before.ecef, stepped), (
            f"{kind}: suite later GNSS did not pull"
        )


def _offset_triplet(lat, lon, h, origin, north_m, chi2, duration_s, skip=False, omit=False):
    pad = hygiene_pad(origin)
    offset = north_of(origin, north_m)
    gnss = origin if skip else offset
    epochs = _continue(pad, origin, gnss, duration_s=duration_s)
    return hygiene_site(
        lat, lon, h, epochs, chi2_disable=chi2, chi2_omit=omit, auto_zupt_disable=True
    )


def test_persistent_gnss_offset_downweighted_not_deadlocked():
    lat, lon, h, origin = _site()
    north = runtime_outlier_north_m()
    offset = north_of(origin, north)
    for kind, run_fn in _LANGS:
        skip_s = run_fn(_offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S, skip=True))
        down_s = run_fn(_offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S, skip=False))
        full_s = run_fn(_offset_triplet(lat, lon, h, origin, north, True, SHORT_WINDOW_S, skip=False))
        skip_l = run_fn(_offset_triplet(lat, lon, h, origin, north, False, LONG_WINDOW_S, skip=True))
        down_l = run_fn(_offset_triplet(lat, lon, h, origin, north, False, LONG_WINDOW_S, skip=False))
        for run, what in ((skip_s, "skip"), (down_s, "down"), (full_s, "full")):
            assert run.init_ok and run.last().ready, f"{kind} {what} short not ready"
            require_finite_published(run.last(), f"{kind} {what} short")
        d_skip = dist_m(skip_s.last().ecef, offset)
        d_down = dist_m(down_s.last().ecef, offset)
        d_full = dist_m(full_s.last().ecef, offset)
        t_pad = hygiene_pad(origin)[-1].t_us
        m_down = window_mean(down_s.snaps, t_pad, None, _ecef_err(offset), f"{kind} down")
        m_full = window_mean(full_s.snaps, t_pad, None, _ecef_err(offset), f"{kind} full")
        print(
            f"{kind} short GNSS d_skip={d_skip} d_down={d_down} d_full={d_full} "
            f"window mean down={m_down} full={m_full}",
            flush=True,
        )
        assert d_down + 0.5 < d_skip, f"{kind}: default arm was a hard reject (same as skip)"
        assert m_full + 1.0 < m_down, f"{kind}: override did not fuse the offset heavier than default"
        d_skip_l = dist_m(skip_l.last().ecef, offset)
        d_down_l = dist_m(down_l.last().ecef, offset)
        print(f"{kind} long GNSS d_skip={d_skip_l} d_down={d_down_l}", flush=True)
        assert d_down_l + 2.0 < d_skip_l, f"{kind}: persistent offset deadlocked like a skip"


def test_finite_gnss_outlier_increments_downweight_not_invalid_input():
    lat, lon, h, origin = _site()
    north = runtime_outlier_north_m()
    for kind, run_fn in _LANGS:
        pad = hygiene_pad(origin)
        t_pad = pad[-1].t_us
        scen = _offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S)
        run = run_fn(scen)
        before = last_at_or_before(run, t_pad)
        after = run.last()
        print(
            f"{kind} finite GNSS dw {before.n_downweighted}->{after.n_downweighted} "
            f"invalid {before.n_invalid}->{after.n_invalid}",
            flush=True,
        )
        assert after.n_downweighted > before.n_downweighted, f"{kind}: downweight did not increase"
        assert after.n_invalid == before.n_invalid, f"{kind}: finite outlier incremented invalid-input"


def test_persistent_yaw_offset_downweighted_not_rejected():
    lat, lon, h, origin = _site()
    pad_yaw = runtime_heading_rad()
    bad_yaw = runtime_yaw_outlier_rad(pad_yaw)
    print(f"F09 yaw offset pad={pad_yaw} bad={bad_yaw}", flush=True)
    for kind, run_fn in _LANGS:
        pad = hygiene_pad(origin, yaw_rad=pad_yaw, yaw_std=YAW_TIGHT_STD_RAD)
        skip = _continue(list(pad), origin, origin, duration_s=SHORT_WINDOW_S)
        down = _continue(
            list(pad), origin, origin, duration_s=SHORT_WINDOW_S, yaw_rad=bad_yaw, yaw_std=math.radians(8.0)
        )
        full = _continue(
            list(pad), origin, origin, duration_s=SHORT_WINDOW_S, yaw_rad=bad_yaw, yaw_std=math.radians(8.0)
        )
        skip_r = run_fn(hygiene_site(lat, lon, h, skip))
        down_r = run_fn(hygiene_site(lat, lon, h, down))
        full_r = run_fn(hygiene_site(lat, lon, h, full, chi2_disable=True))
        ys = skip_r.last().att[2]
        yd = down_r.last().att[2]
        yf = full_r.last().att[2]
        e_skip = abs(angle_diff_rad(ys, bad_yaw))
        e_down = abs(angle_diff_rad(yd, bad_yaw))
        e_full = abs(angle_diff_rad(yf, bad_yaw))
        t_pad = pad[-1].t_us
        m_down = window_mean(down_r.snaps, t_pad, None, _yaw_err(bad_yaw), f"{kind} yaw down")
        m_full = window_mean(full_r.snaps, t_pad, None, _yaw_err(bad_yaw), f"{kind} yaw full")
        print(
            f"{kind} yaw e_skip={e_skip} e_down={e_down} e_full={e_full} "
            f"window mean down={m_down} full={m_full}",
            flush=True,
        )
        assert e_down + 0.02 < e_skip, f"{kind}: yaw offset was a hard reject"
        assert m_full + 0.04 < m_down, f"{kind}: override did not follow the yaw offset more than default"


def test_persistent_mag_heading_error_downweighted_not_rejected():
    lat, lon, h, origin = _site()
    pad_yaw = runtime_heading_rad()
    mild_yaw = wrap_pi(pad_yaw + 0.55)
    harsh_yaw = runtime_yaw_outlier_rad(pad_yaw)
    mag_ned = ned_field_from_independent_wmm(lat, lon, WMM_YEAR)
    mag_pad = body_mag_for_yaw(0.0, 0.0, pad_yaw, mag_ned)
    mag_mild = body_mag_for_yaw(0.0, 0.0, mild_yaw, mag_ned)
    mag_harsh = body_mag_for_yaw(0.0, 0.0, harsh_yaw, mag_ned)
    mild_var = (6.0, 6.0, 6.0)
    print(f"F09 mag mild={mild_yaw} harsh={harsh_yaw} pad={pad_yaw}", flush=True)
    kw = dict(arm_wmm=False, auto_zupt_disable=True)

    def _arms(mag_after, mag_var, chi2):
        pad = hygiene_pad(
            origin, mag=mag_pad, mag_var=mag_var, yaw_rad=pad_yaw, yaw_std=math.radians(8.0)
        )
        stream = _continue(
            list(pad), origin, origin, duration_s=SHORT_WINDOW_S, mag=mag_after, mag_var=mag_var
        )
        return run_fn(hygiene_site(lat, lon, h, stream, chi2_disable=chi2, **kw))

    for kind, run_fn in _LANGS:
        skip = _arms(mag_pad, mild_var, False)
        down_m = _arms(mag_mild, mild_var, False)
        down_h = _arms(mag_harsh, MAG_VAR, False)
        full_h = _arms(mag_harsh, MAG_VAR, True)
        e_skip = abs(angle_diff_rad(skip.last().att[2], mild_yaw))
        e_down_m = abs(angle_diff_rad(down_m.last().att[2], mild_yaw))
        e_down_h = abs(angle_diff_rad(down_h.last().att[2], harsh_yaw))
        e_full_h = abs(angle_diff_rad(full_h.last().att[2], harsh_yaw))
        t_pad = hygiene_pad(origin)[-1].t_us
        # The magnetometer is fused at its default 1 s interval, so the 2 s
        # window holds only a couple of fusions: score the closest approach
        # of each arm to the harsh heading rather than one final instant.
        m_down_h = window_min(down_h.snaps, t_pad, None, _yaw_err(harsh_yaw), f"{kind} mag down")
        m_full_h = window_min(full_h.snaps, t_pad, None, _yaw_err(harsh_yaw), f"{kind} mag full")
        print(
            f"{kind} mag mild e_skip={e_skip} e_down={e_down_m} "
            f"harsh e_down={e_down_h} e_full={e_full_h} "
            f"dw mild={down_m.last().n_downweighted} harsh={down_h.last().n_downweighted} "
            f"full={full_h.last().n_downweighted} skip={skip.last().n_downweighted} "
            f"harsh closest approach down={m_down_h} full={m_full_h}",
            flush=True,
        )
        assert down_m.last().n_downweighted > skip.last().n_downweighted, (
            f"{kind}: persistent mag error was not scored as a downweight"
        )
        assert e_down_m + 0.012 < e_skip, f"{kind}: mag heading error was a hard reject"
        assert down_h.last().n_downweighted > full_h.last().n_downweighted, (
            f"{kind}: harsh mag override still incremented downweight"
        )
        assert m_full_h + 0.04 < m_down_h, (
            f"{kind}: override did not follow the mag heading more than default"
        )


def test_high_rate_local_glitch_skipped_not_downweighted():
    """High-rate glitchy local-position is skipped, not downweighted (PRD / FP-03)."""
    lat, lon, h, origin = _site()
    tracker = (0.0, 0.0, 0.0)
    step_n = runtime_local_step_m()
    glitch = runtime_local_glitch_ned()
    step = (step_n, 0.0, 0.0)
    pad = hygiene_pad(origin)
    t_pad = pad[-1].t_us
    lock = hygiene_append(
        list(pad), duration_s=1.0, origin=origin, gnss_ecef=None, local_ned=tracker
    )
    t_lock = lock[-1].t_us
    fused_epochs = hygiene_append(
        list(lock), duration_s=1.2, origin=origin, gnss_ecef=None, local_ned=step
    )
    glitch_epochs = hygiene_append(
        list(lock), duration_s=1.2, origin=origin, gnss_ecef=None, local_ned=tracker
    )
    poked = False
    for epoch in glitch_epochs:
        if epoch.t_us > t_lock and epoch.local_ned is not None:
            epoch.local_ned = glitch
            poked = True
            break
    assert poked, "no high-rate local sample after the lock to plant a glitch"
    for kind, run_fn in _LANGS:
        fused = run_fn(hygiene_site(lat, lon, h, fused_epochs, auto_zupt_disable=True))
        glitch_run = run_fn(hygiene_site(lat, lon, h, glitch_epochs, auto_zupt_disable=True))
        lock_snap = snap_at(fused, t_lock)
        fused_last = fused.last()
        gl_before = snap_at(glitch_run, t_lock)
        gl_last = glitch_run.last()
        require_ready_hygiene(last_at_or_before(fused, t_pad), origin, f"{kind} pad")
        assert fused_last.ned is not None and lock_snap.ned is not None
        assert gl_last.ned is not None
        print(
            f"{kind} local fused_n={fused_last.ned[0]} lock_n={lock_snap.ned[0]} "
            f"glitch_n={gl_last.ned[0]} glitch={glitch} "
            f"dw {gl_before.n_downweighted}->{gl_last.n_downweighted}",
            flush=True,
        )
        assert fused_last.ned[0] > lock_snap.ned[0] + 0.02, (
            f"{kind}: persistent local offset was not fused (live baseline missing)"
        )
        assert hypot3(gl_last.ned, glitch) > 5.0, f"{kind}: published NED jumped to the glitch"
        assert hypot3(gl_last.ned, tracker) < 0.6, (
            f"{kind}: glitch stream left the tracker"
        )
        assert gl_last.n_downweighted <= gl_before.n_downweighted, (
            f"{kind}: high-rate local glitch incremented downweight instead of skipping"
        )


def test_override_fuses_gnss_outlier_at_full_weight_no_downweight_increment():
    lat, lon, h, origin = _site()
    north = runtime_outlier_north_m()
    offset = north_of(origin, north)
    for kind, run_fn in _LANGS:
        pad = hygiene_pad(origin)
        t_pad = pad[-1].t_us
        off = run_fn(_offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S))
        on = run_fn(_offset_triplet(lat, lon, h, origin, north, True, SHORT_WINDOW_S))
        before_off = last_at_or_before(off, t_pad)
        before_on = last_at_or_before(on, t_pad)
        print(
            f"{kind} override dw off {before_off.n_downweighted}->{off.last().n_downweighted} "
            f"on {before_on.n_downweighted}->{on.last().n_downweighted}",
            flush=True,
        )
        assert off.last().n_downweighted > before_off.n_downweighted, (
            f"{kind}: default arm did not downweight (live baseline missing)"
        )
        assert on.last().n_downweighted == before_on.n_downweighted, (
            f"{kind}: override still incremented downweight"
        )
        m_off = window_mean(off.snaps, t_pad, None, _ecef_err(offset), f"{kind} override off")
        m_on = window_mean(on.snaps, t_pad, None, _ecef_err(offset), f"{kind} override on")
        print(f"{kind} override window mean off={m_off} on={m_on}", flush=True)
        assert m_on + 1.0 < m_off, f"{kind}: override was not closer to the offset than default"


def test_override_default_off_still_downweights():
    lat, lon, h, origin = _site()
    north = runtime_outlier_north_m()
    offset = north_of(origin, north)
    pad = hygiene_pad(origin)
    t_pad = pad[-1].t_us
    omitted = _offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S, omit=True)
    explicit_on = _offset_triplet(lat, lon, h, origin, north, True, SHORT_WINDOW_S)
    for kind, run_fn in _LANGS:
        got = run_fn(omitted)
        on = run_fn(explicit_on)
        before = last_at_or_before(got, t_pad)
        after = got.last()
        d_omit = dist_m(after.ecef, offset)
        d_on = dist_m(on.last().ecef, offset)
        m_omit = window_mean(got.snaps, t_pad, None, _ecef_err(offset), f"{kind} knob omitted")
        m_on = window_mean(on.snaps, t_pad, None, _ecef_err(offset), f"{kind} explicit on")
        print(
            f"{kind} knob-omitted dw {before.n_downweighted}->{after.n_downweighted} "
            f"d_omit={d_omit} d_on={d_on} window mean omit={m_omit} on={m_on}",
            flush=True,
        )
        assert after.n_downweighted > before.n_downweighted, (
            f"{kind}: omitted switch did not downweight"
        )
        assert on.last().n_downweighted == last_at_or_before(on, t_pad).n_downweighted, (
            f"{kind}: explicit-on arm still incremented downweight"
        )
        assert d_omit > 5.0, f"{kind}: omitted switch fused the outlier at full weight"
        assert m_on + 1.0 < m_omit, (
            f"{kind}: omitted switch was not farther from the offset than explicit-on"
        )


def test_standalone_ahrs_override_fuses_mag_at_nominal_variance():
    pad_yaw = runtime_att_yaw_rad()
    bad_yaw = runtime_yaw_outlier_rad(pad_yaw)
    lat, lon, h = runtime_site()
    mag_ned = ned_field_from_independent_wmm(lat, lon, WMM_YEAR)
    mag_pad = body_mag_for_yaw(0.0, 0.0, pad_yaw, mag_ned)
    mag_bad = body_mag_for_yaw(0.0, 0.0, bad_yaw, mag_ned)
    acc = still_level_acc()
    gyr = (0.0, 0.0, 0.0)
    dt = 1.0 / IMU_HZ
    lock_n = int(round(2.5 * IMU_HZ))
    step_n = int(round(SHORT_WINDOW_S * IMU_HZ))

    def cmds(mag_after):
        out = []
        for i in range(1, lock_n + 1):
            out.append((int(round(i * dt * 1e6)), acc, gyr, mag_pad))
        t0 = out[-1][0]
        for i in range(1, step_n + 1):
            out.append((t0 + int(round(i * dt * 1e6)), acc, gyr, mag_after))
        return out, t0

    off_cmds, t_lock = cmds(mag_bad)
    on_cmds, _ = cmds(mag_bad)
    off = c_att_override_run(chi2_disable=False, rpy=(0.0, 0.0, pad_yaw), cmds=off_cmds)
    on = c_att_override_run(chi2_disable=True, rpy=(0.0, 0.0, pad_yaw), cmds=on_cmds)
    assert off.init_ok and on.init_ok
    off_before = next(s for s in off.snaps if s.t_us == t_lock)
    on_before = next(s for s in on.snaps if s.t_us == t_lock)
    assert off.last().rpy_ok and on.last().rpy_ok
    e_off = abs(angle_diff_rad(off.last().att[2], bad_yaw))
    e_on = abs(angle_diff_rad(on.last().att[2], bad_yaw))
    m_off = window_mean(off.snaps, t_lock, None, _yaw_err(bad_yaw), "AHRS override off")
    m_on = window_mean(on.snaps, t_lock, None, _yaw_err(bad_yaw), "AHRS override on")
    print(
        f"ahrs dw off {off_before.n_downweighted}->{off.last().n_downweighted} "
        f"on {on_before.n_downweighted}->{on.last().n_downweighted} e_off={e_off} e_on={e_on} "
        f"window mean off={m_off} on={m_on}",
        flush=True,
    )
    assert off.last().n_downweighted > off_before.n_downweighted, "AHRS off arm did not downweight"
    assert on.last().n_downweighted == on_before.n_downweighted, "AHRS override still downweighted"
    assert m_on + 0.05 < m_off, "AHRS override did not follow the mag step more than default"


def test_standalone_baro_override_fuses_weather_step_at_nominal_variance():
    weather_h = runtime_hygiene_weather_isa_m()
    p_pad = tropospheric_isa_pressure_pa(0.0)
    p_wx = tropospheric_isa_pressure_pa(weather_h)
    acc = still_level_acc()
    dt = 1.0 / IMU_HZ
    pad_n = int(round(3.0 * IMU_HZ))
    step_n = int(round(SHORT_WINDOW_S * IMU_HZ))

    def cmds(pressure_after):
        out = []
        for i in range(1, pad_n + 1):
            out.append((int(round(i * dt * 1e6)), acc, p_pad, True))
        t0 = out[-1][0]
        for i in range(1, step_n + 1):
            out.append((t0 + int(round(i * dt * 1e6)), acc, pressure_after, True))
        return out, t0

    off_cmds, t_pad = cmds(p_wx)
    on_cmds, _ = cmds(p_wx)
    off = c_vert_override_run(chi2_disable=False, t_init=0, pressure=p_pad, cmds=off_cmds)
    on = c_vert_override_run(chi2_disable=True, t_init=0, pressure=p_pad, cmds=on_cmds)
    assert off.init_ok and on.init_ok
    off_before = next(s for s in off.snaps if s.t_us == t_pad)
    on_before = next(s for s in on.snaps if s.t_us == t_pad)
    assert off.last().h_ok and on.last().h_ok
    e_off = abs(off.last().h - weather_h)
    e_on = abs(on.last().h - weather_h)
    m_off = window_mean(off.snaps, t_pad, None, _h_err(weather_h), "baro override off")
    m_on = window_mean(on.snaps, t_pad, None, _h_err(weather_h), "baro override on")
    print(
        f"baro dw off {off_before.n_downweighted}->{off.last().n_downweighted} "
        f"on {on_before.n_downweighted}->{on.last().n_downweighted} e_off={e_off} e_on={e_on} "
        f"window mean off={m_off} on={m_on}",
        flush=True,
    )
    assert off.last().n_downweighted > off_before.n_downweighted, "baro off arm did not downweight"
    assert on.last().n_downweighted == on_before.n_downweighted, "baro override still downweighted"
    assert m_on + 0.5 < m_off, "baro override did not follow the weather step more than default"


def test_explicit_zupt_not_statistically_gated():
    lat, lon, h, origin = _site()
    pad = hygiene_pad(origin)
    built = hygiene_append(
        list(pad), duration_s=1.2, origin=origin, gnss_ecef=None, acc=ABSURD_NORTH_ACC
    )
    t_built = built[-1].t_us
    no_flag = hygiene_append(
        list(built), duration_s=1.0, origin=origin, gnss_ecef=None, acc=SPECIFIC_FORCE_LEVEL
    )
    flagged = hygiene_append(
        list(built),
        duration_s=1.0,
        origin=origin,
        gnss_ecef=None,
        acc=SPECIFIC_FORCE_LEVEL,
        zupt=True,
    )
    for kind, run_fn in _LANGS:
        none = run_fn(hygiene_site(lat, lon, h, no_flag, auto_zupt_disable=True))
        zupt = run_fn(hygiene_site(lat, lon, h, flagged, auto_zupt_disable=True))
        zupt_on = run_fn(
            hygiene_site(lat, lon, h, flagged, auto_zupt_disable=True, chi2_disable=True)
        )
        before = last_at_or_before(zupt, t_built)
        after = zupt.last()
        none_last = none.last()
        vn_z = abs(after.vel[0]) if after.vel else 1e9
        vn_n = abs(none_last.vel[0]) if none_last.vel else 0.0
        print(
            f"{kind} zupt vn_flag={vn_z} vn_none={vn_n} "
            f"dw {before.n_downweighted}->{after.n_downweighted} "
            f"on {zupt_on.last().n_downweighted}",
            flush=True,
        )
        assert vn_n > 0.4, f"{kind}: no-flag twin did not keep a large velocity (live baseline)"
        assert vn_z + 0.15 < vn_n, f"{kind}: explicit ZUPT did not pull velocity toward 0"
        assert after.n_downweighted == before.n_downweighted, f"{kind}: ZUPT incremented downweight"
        vn_on = abs(zupt_on.last().vel[0]) if zupt_on.last().vel else 1e9
        assert abs(vn_on - vn_z) < 0.2, f"{kind}: ZUPT with override on was a different class"
        assert zupt_on.last().n_downweighted == after.n_downweighted, (
            f"{kind}: ZUPT with override on was a different class"
        )


def test_explicit_zaru_not_statistically_gated():
    lat, lon, h, origin = _site()
    pad = hygiene_pad(origin)
    rate = (0.0, 0.0, ABSURD_Z_RATE_RPS)
    none_e = hygiene_append(list(pad), duration_s=1.5, origin=origin, gnss_ecef=origin, gyr=rate)
    flag_e = hygiene_append(
        list(pad), duration_s=1.5, origin=origin, gnss_ecef=origin, gyr=rate, zaru=True
    )
    t_pad = pad[-1].t_us
    for kind, run_fn in _LANGS:
        none = run_fn(hygiene_site(lat, lon, h, none_e, auto_zupt_disable=True))
        zaru = run_fn(hygiene_site(lat, lon, h, flag_e, auto_zupt_disable=True))
        zaru_on = run_fn(
            hygiene_site(lat, lon, h, flag_e, auto_zupt_disable=True, chi2_disable=True)
        )
        before = last_at_or_before(zaru, t_pad)
        after = zaru.last()
        assert after.bias_gyr is not None and none.last().bias_gyr is not None, (
            f"{kind}: gyro bias unpublished"
        )
        bz = after.bias_gyr[2]
        bn = none.last().bias_gyr[2]
        pad_att = last_at_or_before(none, t_pad).att
        assert pad_att is not None and none.last().att is not None and after.att is not None
        t_late = t_pad + int(1.2 * 1e6)
        none_late = last_at_or_before(none, t_late)
        flag_late = last_at_or_before(zaru, t_late)
        dy_none_tail = abs(angle_diff_rad(none.last().att[2], none_late.att[2]))
        dy_flag_tail = abs(angle_diff_rad(after.att[2], flag_late.att[2]))
        print(
            f"{kind} zaru bias_z flag={bz} none={bn} "
            f"dyaw_tail_none={dy_none_tail} dyaw_tail_flag={dy_flag_tail} "
            f"dw {before.n_downweighted}->{after.n_downweighted}",
            flush=True,
        )
        assert abs(bz - ABSURD_Z_RATE_RPS) + 0.05 < abs(bn - ABSURD_Z_RATE_RPS), (
            f"{kind}: explicit ZARU did not pull z-bias toward the reading"
        )
        assert dy_none_tail > dy_flag_tail + 0.04, (
            f"{kind}: flagged ZARU still integrated z-rate after the bias had time to catch"
        )
        assert after.n_downweighted == before.n_downweighted, f"{kind}: ZARU incremented downweight"
        assert abs((zaru_on.last().bias_gyr[2] if zaru_on.last().bias_gyr else 0.0) - bz) < 0.08
        assert zaru_on.last().n_downweighted == after.n_downweighted


def test_nonfinite_noise_densities_fall_back_to_defaults():
    lat, lon, h, origin = _site()
    nan = float("nan")
    inf = float("inf")
    step = ecef_plus_ned(origin, 40.0, 0.0, 0.0)

    def stream(psd):
        pad = hygiene_pad(origin)
        coast = hygiene_append(
            pad,
            duration_s=3.0,
            origin=origin,
            gnss_ecef=None,
            acc_psd=psd,
            gyr_psd=psd,
        )
        stepped = hygiene_append(
            coast,
            duration_s=1.2,
            origin=origin,
            gnss_ecef=step,
            gnss_std=(2.0, 2.0, 2.0),
            acc_psd=psd,
            gyr_psd=psd,
        )
        return hygiene_append(
            stepped,
            duration_s=0.4,
            origin=origin,
            gnss_ecef=None,
            acc_psd=psd,
            gyr_psd=psd,
        )

    zero = (0.0, 0.0, 0.0)
    huge = (LARGE_IMU_PSD, LARGE_IMU_PSD, LARGE_IMU_PSD)
    nan_p = (nan, nan, nan)
    inf_p = (inf, inf, inf)
    z = c_hygiene_run(hygiene_site(lat, lon, h, stream(zero), chi2_disable=True))
    n = c_hygiene_run(hygiene_site(lat, lon, h, stream(nan_p), chi2_disable=True))
    i = c_hygiene_run(hygiene_site(lat, lon, h, stream(inf_p), chi2_disable=True))
    hge = c_hygiene_run(hygiene_site(lat, lon, h, stream(huge), chi2_disable=True))
    for run, name in ((z, "zero"), (n, "nan"), (i, "inf"), (hge, "huge")):
        assert run.init_ok and run.last().ready, f"{name} density arm failed ready"
        require_finite_published(run.last(), name)
    d_z = dist_m(z.last().ecef, step)
    d_n = dist_m(n.last().ecef, step)
    d_i = dist_m(i.last().ecef, step)
    d_h = dist_m(hge.last().ecef, step)
    print(f"density d_zero={d_z} d_nan={d_n} d_inf={d_i} d_huge={d_h}", flush=True)
    assert abs(d_h - d_z) > 1.0, "finite non-default density did not change GNSS pull vs all-zero"
    assert abs(d_n - d_z) < 0.35, "NaN density was not the same class as all-zero defaults"
    assert abs(d_i - d_z) < 0.35, "Inf density was not the same class as all-zero defaults"


def test_nonfinite_lever_arm_treated_as_zero():
    lat, lon, h, origin = _site()
    nan = float("nan")
    inf = float("inf")
    rate = (0.0, 0.0, 0.35)
    pad = hygiene_pad(origin)
    t_pad = pad[-1].t_us

    def arm(lever):
        epochs = hygiene_append(
            list(pad), duration_s=2.5, origin=origin, gnss_ecef=origin, gyr=rate, lever=lever
        )
        return hygiene_site(lat, lon, h, epochs)

    z = c_hygiene_run(arm((0.0, 0.0, 0.0)))
    n = c_hygiene_run(arm((nan, nan, nan)))
    i = c_hygiene_run(arm((inf, 0.0, 0.0)))
    r = c_hygiene_run(arm(LEVER_RIGHT_15CM))
    u_lever = (0.0, 0.11, 0.0)
    u = c_hygiene_run(arm(u_lever))
    for run, name in ((z, "zero"), (n, "nan"), (i, "inf"), (r, "15cm"), (u, "runtime")):
        assert run.init_ok and run.last().ready, f"{name} lever failed ready"
    after_z = z.last()
    after_n = n.last()
    after_r = r.last()
    d_zr = dist_m(after_z.ecef, after_r.ecef)
    d_zn = dist_m(after_z.ecef, after_n.ecef)
    d_nr = dist_m(after_n.ecef, after_r.ecef)
    d_zu = dist_m(after_z.ecef, u.last().ecef)
    d_zi = dist_m(after_z.ecef, i.last().ecef)
    d_ir = dist_m(i.last().ecef, after_r.ecef)
    print(
        f"lever d_zero_15={d_zr} d_zero_nan={d_zn} d_nan_15={d_nr} "
        f"d_zero_inf={d_zi} d_inf_15={d_ir} d_zero_rt={d_zu}",
        flush=True,
    )
    assert d_zr > 0.04, "finite 15 cm lever was not distinguishable from zero (live baseline)"
    assert d_zu > 0.02, "runtime finite lever was not used"
    assert d_zn < 0.03, "NaN lever was distinguishable from zero"
    assert d_nr > d_zn, "NaN lever matched the finite 15 cm arm"
    assert d_zi < 0.03, "Inf lever was distinguishable from zero"
    assert d_ir > d_zi, "Inf lever matched the finite 15 cm arm"


def test_nonfinite_cross_covariance_treated_as_zero():
    lat, lon, h, origin = _site()
    nan = float("nan")
    inf = float("inf")
    pad = hygiene_pad(origin)
    t_pad = pad[-1].t_us
    vn = runtime_hygiene_cross_vel_mps()
    pos_std = 2.0
    vel_std = 0.40
    # Finite non-zero pos/vel cross term, still a valid correlation.
    cross_nn = 0.85 * pos_std * vel_std

    def arm(xc):
        coast = hygiene_append(list(pad), duration_s=0.20, origin=origin, gnss_ecef=None)
        epochs = hygiene_append(
            coast,
            duration_s=2.0,
            origin=origin,
            gnss_ecef=origin,
            gnss_hz=10,
            gnss_std=(pos_std, pos_std, pos_std),
            gnss_vel=(vn, 0.0, 0.0),
            gnss_vel_std=(vel_std, vel_std, vel_std),
            cross_cov=xc,
        )
        return hygiene_site(lat, lon, h, epochs, chi2_disable=True)

    z = c_hygiene_run(arm((0.0,) * 9))
    n = c_hygiene_run(arm((nan,) * 9))
    i = c_hygiene_run(arm((inf,) * 9))
    finite = c_hygiene_run(arm((cross_nn, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
    for run, name in ((z, "zero"), (n, "nan"), (i, "inf")):
        require_ready_hygiene(last_at_or_before(run, t_pad), origin, f"{name} pad")
        assert run.last().ready, f"{name}: not ready after the contrast stream"
        require_finite_published(run.last(), name)
    require_finite_published(finite.last(), "finite")
    assert finite.last().ready and finite.last().ecef is not None
    d_zn = dist_m(z.last().ecef, n.last().ecef)
    d_zi = dist_m(z.last().ecef, i.last().ecef)
    d_zf = dist_m(z.last().ecef, finite.last().ecef)
    d_nf = dist_m(n.last().ecef, finite.last().ecef)
    d_if = dist_m(i.last().ecef, finite.last().ecef)
    print(
        f"cross-cov d_nan={d_zn} d_inf={d_zi} d_finite={d_zf} "
        f"d_nan_finite={d_nf} d_inf_finite={d_if} vn={vn} xc={cross_nn}",
        flush=True,
    )
    assert d_zf > 0.08, "finite non-zero cross-covariance did not move ECEF vs explicit zero"
    assert d_zn < 0.05, "NaN cross-covariance was distinguishable from explicit zero"
    assert d_zi < 0.05, "Inf cross-covariance was distinguishable from explicit zero"
    assert d_zn < d_nf, "NaN cross-covariance matched the finite arm rather than explicit zero"
    assert d_zi < d_if, "Inf cross-covariance matched the finite arm rather than explicit zero"


def test_invalid_input_and_downweight_counters_distinguishable():
    lat, lon, h, origin = _site()
    nan = float("nan")
    north = runtime_outlier_north_m()
    pad = hygiene_pad(origin)
    t_pad = pad[-1].t_us
    acc_epochs, t_bad = _insert_epoch(list(pad), acc=(ABSURD_NORTH_ACC[0], nan, -G_MPS2), gnss_ecef=origin)
    acc_epochs = _continue(acc_epochs, origin, origin)
    gnss = _offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S)
    for kind, run_fn in _LANGS:
        inv = run_fn(hygiene_site(lat, lon, h, acc_epochs))
        dw = run_fn(gnss)
        b_inv = last_at_or_before(inv, t_pad)
        a_inv = snap_at(inv, t_bad)
        b_dw = last_at_or_before(dw, t_pad)
        a_dw = dw.last()
        print(
            f"{kind} invalid dI={a_inv.n_invalid - b_inv.n_invalid} "
            f"dD={a_inv.n_downweighted - b_inv.n_downweighted} "
            f"gnss dI={a_dw.n_invalid - b_dw.n_invalid} "
            f"dD={a_dw.n_downweighted - b_dw.n_downweighted}",
            flush=True,
        )
        assert a_inv.n_invalid > b_inv.n_invalid
        assert a_inv.n_downweighted == b_inv.n_downweighted, (
            f"{kind}: NaN accelerometer also incremented downweight"
        )
        assert a_dw.n_downweighted > b_dw.n_downweighted
        assert a_dw.n_invalid == b_dw.n_invalid, (
            f"{kind}: finite GNSS outlier also incremented invalid-input"
        )


def test_skipped_vs_fused_gnss_diagnostics_distinguishable():
    lat, lon, h, origin = _site()
    dn, de, dd = runtime_gnss_step_m()
    stepped = ecef_plus_ned(origin, dn, de, dd)
    pad = hygiene_pad(origin)
    t_pad = pad[-1].t_us
    fused = _continue(list(pad), origin, stepped, duration_s=SHORT_WINDOW_S)
    skipped = _continue(
        list(pad), origin, stepped, duration_s=SHORT_WINDOW_S, gnss_broken=True, gnss_std=UNFUSABLE_POS_STD
    )
    for kind, run_fn in _LANGS:
        f = run_fn(hygiene_site(lat, lon, h, fused))
        s = run_fn(hygiene_site(lat, lon, h, skipped))
        bf = last_at_or_before(f, t_pad)
        bs = last_at_or_before(s, t_pad)
        af = f.last()
        as_ = s.last()
        d_gate_s = as_.n_gate - bs.n_gate
        d_inv_s = as_.n_invalid - bs.n_invalid
        d_dw_s = as_.n_downweighted - bs.n_downweighted
        d_gate_f = af.n_gate - bf.n_gate
        print(
            f"{kind} skip d_gate={d_gate_s} d_inv={d_inv_s} d_dw={d_dw_s} fused d_gate={d_gate_f}",
            flush=True,
        )
        assert d_gate_s > 0, f"{kind}: skip arm had no positive gate increment"
        assert d_gate_s != d_inv_s or d_inv_s == 0, f"{kind}: skip class collapsed into invalid-input"
        assert d_dw_s == 0, f"{kind}: skip class collapsed into downweight"
        assert d_gate_s != d_gate_f or d_gate_f == 0, (
            f"{kind}: fused arm used the same gate increment as the skip"
        )


def test_timing_anomaly_counter_distinct_from_invalid_and_downweight():
    """INS backwards timestamp: timing-anomaly class, skip that extra IMU, later finite epochs proceed."""
    pad_yaw = runtime_att_yaw_rad()
    lat, lon, h = runtime_site()
    mag_ned = ned_field_from_independent_wmm(lat, lon, WMM_YEAR)
    mag_pad = body_mag_for_yaw(0.0, 0.0, pad_yaw, mag_ned)
    acc = still_level_acc()
    dt = 1.0 / IMU_HZ
    lock_n = int(round(2.5 * IMU_HZ))
    pad_cmds = []
    for i in range(1, lock_n + 1):
        pad_cmds.append((int(round(i * dt * 1e6)), acc, (0.0, 0.0, 0.0), mag_pad))
    t_lock = pad_cmds[-1][0]
    rate = (0.0, 0.0, ABSURD_Z_RATE_RPS)
    back_cmds = list(pad_cmds)
    back_cmds.append((t_lock - 50_000, acc, rate, None))
    mono_cmds = list(pad_cmds)
    mono_cmds.append((t_lock + 50_000, acc, rate, None))
    back = c_att_override_run(chi2_disable=False, rpy=(0.0, 0.0, pad_yaw), cmds=back_cmds)
    mono = c_att_override_run(chi2_disable=False, rpy=(0.0, 0.0, pad_yaw), cmds=mono_cmds)
    assert back.init_ok and mono.init_ok
    before = next(s for s in back.snaps if s.t_us == t_lock)
    after = back.last()
    mb = next(s for s in mono.snaps if s.t_us == t_lock)
    ma = mono.last()
    assert after.att is not None and before.att is not None
    assert ma.att is not None and mb.att is not None
    dy_back = abs(angle_diff_rad(after.att[2], before.att[2]))
    dy_mono = abs(angle_diff_rad(ma.att[2], mb.att[2]))
    print(
        f"ahrs time skip dYaw_back={dy_back} dYaw_mono={dy_mono} "
        f"dI={after.n_invalid - before.n_invalid} "
        f"dD={after.n_downweighted - before.n_downweighted} "
        f"mono dI={ma.n_invalid - mb.n_invalid}",
        flush=True,
    )
    assert dy_mono > dy_back + 0.01, "AHRS backwards timestamp was not skipped relative to a monotonic twin"
    assert after.n_invalid == before.n_invalid, "AHRS backwards timestamp collapsed into invalid-input"
    assert after.n_downweighted == before.n_downweighted, (
        "AHRS backwards timestamp collapsed into downweight"
    )
    assert ma.n_invalid == mb.n_invalid, "AHRS monotonic twin incremented invalid-input"

    # INS backwards timestamp is the timing-anomaly class.
    # AHRS standalone has no such counter; the skip above is the PRD carrier.
    lat, lon, h, origin = _site()
    stepped = _step_ecef(origin)
    pad = hygiene_pad(origin)
    t_pad = pad[-1].t_us
    # 50 ms off the pad, plus 1 us so the timestamp is not a pad sample.
    back_us = 50_001
    t_back = t_pad - back_us
    t_fwd = t_pad + back_us
    extra_dt = 0.05
    extra_gyr = (0.0, 0.0, ABSURD_Z_RATE_RPS)
    extra_back = HygieneEpoch(
        t_us=t_back, dt_sec=extra_dt, acc=SPECIFIC_FORCE_LEVEL, gyr=extra_gyr
    )
    extra_fwd = HygieneEpoch(
        t_us=t_fwd, dt_sec=extra_dt, acc=SPECIFIC_FORCE_LEVEL, gyr=extra_gyr
    )
    continued = _continue(list(pad) + [extra_fwd], origin, stepped, duration_s=2.0)
    after_fwd = [e for e in continued if e.t_us > t_fwd]
    back_ins = list(pad) + [extra_back, extra_fwd] + after_fwd
    mono_ins = list(pad) + [extra_fwd]
    for kind, run_fn in _LANGS:
        br = run_fn(hygiene_site(lat, lon, h, back_ins, auto_zupt_disable=True))
        mr = run_fn(hygiene_site(lat, lon, h, mono_ins, auto_zupt_disable=True))
        ins_before = snap_at(br, t_pad)
        after_back = snap_at(br, t_back)
        after_same = snap_at(br, t_fwd)
        last = br.last()
        mb_ins = snap_at(mr, t_pad)
        ma_ins = snap_at(mr, t_fwd)
        d_time = after_back.n_time - ins_before.n_time
        d_inv = after_back.n_invalid - ins_before.n_invalid
        d_dw = after_back.n_downweighted - ins_before.n_downweighted
        d_time_mono = ma_ins.n_time - mb_ins.n_time
        d_time_later = after_same.n_time - after_back.n_time
        assert after_back.att is not None and ins_before.att is not None
        assert ma_ins.att is not None and mb_ins.att is not None
        dy_back = abs(angle_diff_rad(after_back.att[2], ins_before.att[2]))
        dy_mono = abs(angle_diff_rad(ma_ins.att[2], mb_ins.att[2]))
        print(
            f"{kind} ins time skip d_time={d_time} d_inv={d_inv} d_dw={d_dw} "
            f"mono d_time={d_time_mono} later d_time={d_time_later} "
            f"dYaw_back={dy_back} dYaw_mono={dy_mono}",
            flush=True,
        )
        assert d_time > 0, f"{kind}: backwards INS epoch did not increment timing-anomaly"
        assert d_inv == 0, f"{kind}: INS timing skip collapsed into invalid-input"
        assert d_dw == 0, f"{kind}: INS timing skip collapsed into downweight"
        assert d_time_mono == 0, f"{kind}: monotonic INS twin incremented timing-anomaly"
        assert dy_mono > dy_back + 0.01, (
            f"{kind}: backwards extra IMU was applied (yaw moved like the increasing twin)"
        )
        assert d_time_later == 0, (
            f"{kind}: later increasing timestamp of the same extra IMU incremented timing-anomaly"
        )
        require_finite_published(last, f"{kind} later finite after INS backwards timestamp")
        assert last.ready, f"{kind}: later finite epoch was not ready after the INS backwards timestamp"
        assert last.ecef is not None and after_back.ecef is not None
        d_later = dist_m(last.ecef, stepped)
        d_skip = dist_m(after_back.ecef, stepped)
        print(f"{kind} later GNSS pull after skip d_later={d_later} d_skip={d_skip}", flush=True)
        assert d_later + 0.2 < d_skip, (
            f"{kind}: later finite epochs did not proceed after the INS backwards timestamp"
        )


def test_auto_zupt_trigger_counter_readable():
    lat, lon, h, origin = _site()
    still = hygiene_pad(origin)
    spin = hygiene_pad(origin, gyr=(0.0, 0.0, 0.25))
    for kind, run_fn in _LANGS:
        s = run_fn(hygiene_site(lat, lon, h, still, auto_zupt_disable=False))
        t = run_fn(hygiene_site(lat, lon, h, spin, auto_zupt_disable=False))
        print(
            f"{kind} auto-zupt still={s.last().n_auto_zupt} spin={t.last().n_auto_zupt}",
            flush=True,
        )
        assert s.last().n_auto_zupt > 0, f"{kind}: still pad did not increment auto-ZUPT"
        assert t.last().n_auto_zupt < s.last().n_auto_zupt, (
            f"{kind}: turntable twin incremented auto-ZUPT the same as standstill"
        )


def test_diagnostic_counters_are_not_acted_on():
    lat, lon, h, origin = _site()
    nan = float("nan")
    north = runtime_outlier_north_m()
    stepped = _step_ecef(origin)
    pad = hygiene_pad(origin)
    dirty, _ = _insert_epoch(list(pad), acc=(ABSURD_NORTH_ACC[0], nan, -G_MPS2), gnss_ecef=origin)
    dirty = _continue(dirty, origin, north_of(origin, north), duration_s=SHORT_WINDOW_S)
    t_dirty = dirty[-1].t_us
    later = _continue(list(dirty), origin, stepped, duration_s=2.0)
    skip_later = list(dirty)
    for kind, run_fn in _LANGS:
        with_fix = run_fn(hygiene_site(lat, lon, h, later))
        without = run_fn(hygiene_site(lat, lon, h, skip_later))
        before = last_at_or_before(with_fix, t_dirty)
        after = with_fix.last()
        print(
            f"{kind} counters-not-acted invalid={before.n_invalid} dw={before.n_downweighted} "
            f"d_before={dist_m(before.ecef, stepped)} d_after={dist_m(after.ecef, stepped)} "
            f"d_skip={dist_m(without.last().ecef, stepped)}",
            flush=True,
        )
        assert before.n_invalid > 0 and before.n_downweighted > 0, (
            f"{kind}: history did not contain both invalid-input and downweight"
        )
        assert dist_m(after.ecef, stepped) + 0.3 < dist_m(before.ecef, stepped), (
            f"{kind}: later good GNSS was not fused after the counters had risen"
        )
        assert dist_m(after.ecef, stepped) + 0.3 < dist_m(without.last().ecef, stepped), (
            f"{kind}: the later-GNSS contrast was not the later fix"
        )


def test_override_same_switch_on_config_yaml():
    """the global outlier-rejection override is the same switch on filter options and config.yaml."""
    lat, lon, h, origin = _site()
    north = runtime_outlier_north_m()
    offset = north_of(origin, north)
    with workspace() as ws:
        yaml_on_dir = write_outlier_replay_dataset(
            ws, lat_deg=lat, lon_deg=lon, h_m=h, north_m=north, override=True, relpath="yaml-on"
        )
        yaml_off_dir = write_outlier_replay_dataset(
            ws, lat_deg=lat, lon_deg=lon, h_m=h, north_m=north, override=False, relpath="yaml-off"
        )
        rows_yaml_on = replay_ecef_rows(yaml_on_dir, ws.resolve("sol-on.csv"))
        rows_yaml_off = replay_ecef_rows(yaml_off_dir, ws.resolve("sol-off.csv"))
    opt_off = c_hygiene_run(_offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S))
    opt_on = c_hygiene_run(_offset_triplet(lat, lon, h, origin, north, True, SHORT_WINDOW_S))
    # Replay dumps every IMU epoch; the last rows are the post-step window.
    n_step = outlier_replay_step_rows()
    for rows, name in ((rows_yaml_on, "on"), (rows_yaml_off, "off")):
        assert len(rows) >= n_step, (
            f"config.yaml {name}: replay dumped fewer rows than the post-step epochs"
        )
    d_yaml_on = sum(dist_m(e, offset) for e in rows_yaml_on[-n_step:]) / n_step
    d_yaml_off = sum(dist_m(e, offset) for e in rows_yaml_off[-n_step:]) / n_step
    t_pad = hygiene_pad(origin)[-1].t_us
    d_opt_on = window_mean(opt_on.snaps, t_pad, None, _ecef_err(offset), "options on")
    d_opt_off = window_mean(opt_off.snaps, t_pad, None, _ecef_err(offset), "options off")
    print(
        f"window mean yaml-on={d_yaml_on} yaml-off={d_yaml_off} "
        f"opt-on={d_opt_on} opt-off={d_opt_off}",
        flush=True,
    )
    assert opt_off.last().n_downweighted > 0, "filter-options off arm did not downweight"
    assert opt_on.last().n_downweighted == 0, "filter-options on arm still downweighted"
    assert d_opt_on + 1.0 < d_opt_off, "filter-options on was not heavier fusion"
    assert d_yaml_on + 1.0 < d_yaml_off, (
        "config.yaml override did not fuse the outlier heavier than config.yaml off"
    )


def test_suite_override_disables_downweighting_across_filters():
    """constructing the suite with the switch on fuses every tested measurement at nominal variance."""
    lat, lon, h, origin = _site()
    north = runtime_outlier_north_m()
    offset = north_of(origin, north)
    heading = runtime_heading_rad()
    mag_ned = ned_field_from_independent_wmm(lat, lon, WMM_YEAR)
    mag_pad = body_mag_for_yaw(0.0, 0.0, heading, mag_ned)
    bad_yaw = runtime_yaw_outlier_rad(heading)
    mag_bad = body_mag_for_yaw(0.0, 0.0, bad_yaw, mag_ned)
    p_pad = tropospheric_isa_pressure_pa(0.0)
    weather_h = runtime_hygiene_weather_isa_m()
    p_wx = tropospheric_isa_pressure_pa(weather_h)

    gnss_off = dict(suite_hygiene_langs(_offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S)))
    gnss_on = dict(suite_hygiene_langs(_offset_triplet(lat, lon, h, origin, north, True, SHORT_WINDOW_S)))
    for kind in gnss_off:
        off = gnss_off[kind]
        on = gnss_on[kind]
        pad_t = hygiene_pad(origin)[-1].t_us
        before_off = last_at_or_before(off, pad_t)
        before_on = last_at_or_before(on, pad_t)
        d_off = window_mean(off.snaps, pad_t, None, _ecef_err(offset), f"{kind} suite GNSS off")
        d_on = window_mean(on.snaps, pad_t, None, _ecef_err(offset), f"{kind} suite GNSS on")
        print(
            f"{kind} suite GNSS dw off {before_off.n_downweighted}->{off.last().n_downweighted} "
            f"on {before_on.n_downweighted}->{on.last().n_downweighted} "
            f"window mean d_off={d_off} d_on={d_on}",
            flush=True,
        )
        assert off.last().n_downweighted > before_off.n_downweighted, (
            f"{kind}: suite default did not downweight GNSS"
        )
        assert on.last().n_downweighted == before_on.n_downweighted, (
            f"{kind}: suite override still downweighted GNSS"
        )
        assert d_on + 1.0 < d_off, f"{kind}: suite override did not fuse GNSS at nominal variance"

    pad = hygiene_pad(origin, mag=mag_pad, mag_var=MAG_VAR, baro_pa=p_pad, yaw_rad=heading, yaw_std=YAW_TIGHT_STD_RAD)
    frozen = hygiene_append(
        list(pad),
        duration_s=FREEZE_11S,
        origin=origin,
        gnss_ecef=None,
        mag=mag_pad,
        mag_var=MAG_VAR,
        baro_pa=p_pad,
    )
    mag_step = hygiene_append(
        list(frozen),
        duration_s=SHORT_WINDOW_S,
        origin=origin,
        gnss_ecef=None,
        mag=mag_bad,
        mag_var=MAG_VAR,
        baro_pa=p_pad,
    )
    baro_step = hygiene_append(
        list(frozen),
        duration_s=SHORT_WINDOW_S,
        origin=origin,
        gnss_ecef=None,
        mag=mag_pad,
        mag_var=MAG_VAR,
        baro_pa=p_wx,
    )
    mag_kw = dict(mag_delay_ms=MAG_EVERY_SAMPLE_MS, auto_zupt_disable=True)
    mag_off = c_suite_hygiene_run(hygiene_site(lat, lon, h, mag_step, chi2_disable=False, **mag_kw))
    mag_on = c_suite_hygiene_run(hygiene_site(lat, lon, h, mag_step, chi2_disable=True, **mag_kw))
    baro_off = c_suite_hygiene_run(hygiene_site(lat, lon, h, baro_step, chi2_disable=False, auto_zupt_disable=True))
    baro_on = c_suite_hygiene_run(hygiene_site(lat, lon, h, baro_step, chi2_disable=True, auto_zupt_disable=True))
    assert mag_off.last().att is not None and mag_on.last().att is not None
    t_frozen = frozen[-1].t_us
    e_mag_off = window_mean(mag_off.snaps, t_frozen, None, _yaw_err(bad_yaw), "suite mag off")
    e_mag_on = window_mean(mag_on.snaps, t_frozen, None, _yaw_err(bad_yaw), "suite mag on")
    print(f"suite mag window mean e_off={e_mag_off} e_on={e_mag_on}", flush=True)
    assert e_mag_on + 0.05 < e_mag_off, "suite override did not fuse magnetometer at nominal variance"
    assert baro_off.last().h_ok and baro_on.last().h_ok, "suite height unpublished after freeze"
    e_baro_off = window_mean(baro_off.snaps, t_frozen, None, _h_err(weather_h), "suite baro off")
    e_baro_on = window_mean(baro_on.snaps, t_frozen, None, _h_err(weather_h), "suite baro on")
    print(
        f"suite baro window mean e_off={e_baro_off} e_on={e_baro_on} weather={weather_h} "
        f"last off={baro_off.last().h} on={baro_on.last().h}",
        flush=True,
    )
    assert e_baro_on + 0.5 < e_baro_off, "suite override did not fuse barometer at nominal variance"


def test_fusion_failure_diagnostic_readable_as_own_class():
    """a positive-diagonal, not-PD GNSS position covariance is its own class."""
    lat, lon, h, origin = _site()
    nan = float("nan")
    north = runtime_outlier_north_m()
    stepped = _step_ecef(origin)
    pad = hygiene_pad(origin)
    t_pad = pad[-1].t_us
    acc_epochs, t_bad = _insert_epoch(
        list(pad), acc=(ABSURD_NORTH_ACC[0], nan, -G_MPS2), gnss_ecef=origin
    )
    acc_epochs = _continue(acc_epochs, origin, origin)
    gnss = _offset_triplet(lat, lon, h, origin, north, False, SHORT_WINDOW_S)
    skipped = _continue(
        list(pad), origin, origin, duration_s=SHORT_WINDOW_S, gnss_broken=True, gnss_std=UNFUSABLE_POS_STD
    )
    # Diagonals stay the pad 2 m 1-sigma (positive, so the FP-05 fusion gate
    # does not reject a broken covariance). The N-E term is larger than the
    # geometric mean of those diagonals, so the matrix is not positive definite.
    pos_std = 2.0
    var = pos_std * pos_std
    off_ne = var + 1.0
    coast = hygiene_append(list(pad), duration_s=0.20, origin=origin, gnss_ecef=None)
    illegal_epochs = hygiene_append(
        list(coast),
        duration_s=1.2,
        origin=origin,
        gnss_ecef=stepped,
        gnss_std=(pos_std, pos_std, pos_std),
        gnss_pos_offdiag=(off_ne, 0.0, 0.0),
    )
    t_illegal = illegal_epochs[-1].t_us
    later = _continue(list(illegal_epochs), origin, stepped)
    valid_epochs = hygiene_append(
        list(coast),
        duration_s=1.2,
        origin=origin,
        gnss_ecef=stepped,
        gnss_std=(pos_std, pos_std, pos_std),
    )
    for kind, run_fn in _LANGS:
        inv = run_fn(hygiene_site(lat, lon, h, acc_epochs))
        dw = run_fn(gnss)
        gate = run_fn(hygiene_site(lat, lon, h, skipped))
        illegal = run_fn(hygiene_site(lat, lon, h, later))
        valid = run_fn(hygiene_site(lat, lon, h, valid_epochs))
        b_inv = last_at_or_before(inv, t_pad)
        a_inv = snap_at(inv, t_bad)
        b_dw = last_at_or_before(dw, t_pad)
        a_dw = dw.last()
        b_gate = last_at_or_before(gate, t_pad)
        a_gate = gate.last()
        b_ff = last_at_or_before(illegal, t_pad)
        a_ff = last_at_or_before(illegal, t_illegal)
        print(
            f"{kind} fusion-fail inv {b_inv.n_fusion}->{a_inv.n_fusion} "
            f"dw {b_dw.n_fusion}->{a_dw.n_fusion} gate {b_gate.n_fusion}->{a_gate.n_fusion} "
            f"named {b_ff.n_fusion}->{a_ff.n_fusion} "
            f"dI={a_inv.n_invalid - b_inv.n_invalid} dD={a_dw.n_downweighted - b_dw.n_downweighted} "
            f"dG={a_gate.n_gate - b_gate.n_gate} "
            f"named dI={a_ff.n_invalid - b_ff.n_invalid} dG={a_ff.n_gate - b_ff.n_gate}",
            flush=True,
        )
        assert a_inv.n_invalid > b_inv.n_invalid
        assert a_inv.n_fusion == b_inv.n_fusion, f"{kind}: fusion-failure aliased invalid-input"
        assert a_dw.n_downweighted > b_dw.n_downweighted
        assert a_dw.n_fusion == b_dw.n_fusion, f"{kind}: fusion-failure aliased downweight"
        assert a_gate.n_gate > b_gate.n_gate
        assert a_gate.n_fusion == b_gate.n_fusion, f"{kind}: fusion-failure aliased GNSS gating"
        assert a_ff.n_fusion > b_ff.n_fusion, (
            f"{kind}: not-PD GNSS covariance did not increment fusion-failure"
        )
        assert a_ff.n_invalid == b_ff.n_invalid, (
            f"{kind}: not-PD GNSS covariance incremented invalid-input"
        )
        assert a_ff.n_gate == b_ff.n_gate, (
            f"{kind}: not-PD GNSS covariance incremented GNSS gating"
        )
        assert a_ff.ecef is not None and valid.last().ecef is not None
        d_illegal = dist_m(a_ff.ecef, stepped)
        d_valid = dist_m(valid.last().ecef, stepped)
        d_pad = dist_m(b_ff.ecef, stepped)
        print(
            f"{kind} not-fused d_illegal={d_illegal} d_valid={d_valid} d_pad={d_pad}",
            flush=True,
        )
        assert d_valid + 0.15 < d_illegal, (
            f"{kind}: not-PD GNSS covariance was fused like a valid twin"
        )
        assert abs(d_illegal - d_pad) < 0.25, (
            f"{kind}: not-PD GNSS covariance still moved off the pad"
        )
        last = illegal.last()
        require_finite_published(last, f"{kind} later after fusion-failure")
        assert last.ready, f"{kind}: later finite epoch was not ready after the fusion failure"
        assert dist_m(last.ecef, stepped) + 0.2 < d_illegal, (
            f"{kind}: later finite GNSS did not proceed after the fusion failure"
        )


def test_hygiene_diagnostics_are_available_and_non_negative():
    """``ins_get_diag`` / ``diag`` are available on a live instance and the
    invalid-input, downweight, gate, fusion, time and auto-ZUPT counters are
    non-negative; ``--dump-solution`` rows read here are well formed -- on
    every snapshot and dump row parsed in this session and on a pad of its
    own. (Non-finite published values are FP-09 data here, not violations.)
    A violation fails this test only.
    """
    from _harness import require_no_product_issues

    lat, lon, h, origin = _site()
    for _kind, run_fn in _LANGS:
        run = run_fn(hygiene_site(lat, lon, h, hygiene_pad(origin)))
        assert run.init_ok and run.snaps, "pad produced no snapshots"
    require_no_product_issues("F09", "hygiene snapshots (F09)")
