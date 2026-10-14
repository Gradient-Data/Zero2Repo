# feature: F02
"""INS 3D navigation from IMU and GNSS (FP-02).

Assertions stay at the PRD's precision: a zeroed options block starts; an ECEF
origin below 1 km (a neighbourhood of the zero vector) does not; a missing
required pointer does not start an instance; the stationary 100 Hz / 1 Hz
2/2/2 stream becomes ready with ECEF matching the fed fix to well under a
metre and near-level roll/pitch; a coarse origin is refined so ECEF follows
the GNSS fix rather than remaining at the init ECEF; accelerometer leveling
follows specific force on roll and pitch; a 15 cm
right FRD lever arm (plus a runtime variant) changes the position innovation
under a yaw rate; ready stays false until both four filter-update epochs and
1.5 s after initialization; accessors fail before initialization and succeed
after; invalid IMU is not a strapdown step; non-positive GNSS variance and a
fix beyond the fusion gate are not fused and do not disable the filter; the
Python wrapper is a push / epoch / read loop whose readers do not run the
filter; skipping the epoch step leaves ready false. An IMU-only epoch is a
normal accepted step on the 100 Hz / 1 Hz stream: a post-init IMU-only
yaw-rate changes published yaw relative to skipping those epochs. Default auto-init with
neither absolute yaw nor magnetometer leaves yaw unknown with a
correspondingly large uncertainty relative to leveled roll and pitch.
Message text, exception types, unpublished cadence knobs, and unpublished
numeric yaw bounds are not pinned.
"""

from __future__ import annotations

import math

from F01_helpers import angle_diff_deg, hypot3
from F02_helpers import (
    ECEF_MATCH_M,
    EARTH_ECEF_NORM_M,
    ENTRY_DWELL_S,
    GNSS_HZ,
    GNSS_STD_M,
    HAPPY_DURATION_S,
    IMU_HZ,
    LEVER_RIGHT_15CM,
    LEVEL_RAD,
    ORIGIN_NORM_MIN_M,
    POST_INIT_SPARSE,
    READY_WAIT_S,
    SPARSE_DT_S,
    SPARSE_MORE,
    SPECIFIC_FORCE_LEVEL,
    STILL_VEL_MPS,
    append_imu_only,
    append_sparse_imu,
    c_ins_run,
    clip_through_initialized,
    ecef_from_llh_deg,
    ecef_norm,
    ecef_plus_ned,
    happy_scenario,
    py_ins_run,
    require_finite_solution,
    retimed,
    runtime_gnss_step_m,
    runtime_lever,
    runtime_ned_shift_m,
    runtime_north_vel,
    runtime_pitch_fx,
    runtime_roll_fy,
    runtime_site,
    runtime_sub_km_ecef,
    site_scenario,
    stationary_imu_gnss_stream,
)


def _assert_ecef_matches(got, fix, what):
    err = hypot3(got, fix)
    print(f"{what}: |ecef-fix|={err} m (limit {ECEF_MATCH_M})", flush=True)
    assert err < ECEF_MATCH_M, f"{what}: ECEF error {err} m is not well under a metre"


def _assert_near_level(rpy, what):
    roll, pitch, _yaw = rpy
    print(
        f"{what}: roll={math.degrees(roll)} deg pitch={math.degrees(pitch)} deg "
        f"limit={math.degrees(LEVEL_RAD)} deg",
        flush=True,
    )
    assert abs(roll) < LEVEL_RAD, f"{what}: |roll| {math.degrees(roll)} deg not well under 0.5 deg"
    assert abs(pitch) < LEVEL_RAD, (
        f"{what}: |pitch| {math.degrees(pitch)} deg not well under 0.5 deg"
    )


def _assert_not_init_ecef(sol_ecef, origin, what):
    err = hypot3(sol_ecef, origin)
    print(f"{what}: |ecef-origin|={err} m", flush=True)
    assert err > ECEF_MATCH_M, f"{what}: solution stayed at the init ECEF ({err} m)"


def _deg(rad: float) -> float:
    return math.degrees(rad)


# ---------------------------------------------------------------------------
# A. Construction
# ---------------------------------------------------------------------------


def test_zeroed_options_auto_init_starts_c():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    n = ecef_norm(origin)
    print(f"origin norm={n} m (Earth-scale {EARTH_ECEF_NORM_M})", flush=True)
    assert n > ORIGIN_NORM_MIN_M
    assert n > 1.0e6
    scen = happy_scenario(lat, lon, h, duration_s=0.05)
    run = c_ins_run(scen)
    print(f"init_ok={run.init_ok}", flush=True)
    assert run.init_ok, "zeroed options with auto-init and a ground ECEF origin must start"


def test_ecef_origin_below_1_km_init_fails():
    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h, duration_s=0.05, origin_ecef=(0.0, 0.0, 0.0))
    run = c_ins_run(scen)
    print(f"(0,0,0) init_ok={run.init_ok} snaps={len(run.snaps)}", flush=True)
    assert not run.init_ok, "a (0,0,0) ECEF origin must not start an instance"
    last = run.last()
    assert not last.pos_ok, "position accessors must fail on an unstarted instance"
    assert not last.ready


def test_runtime_sub_1_km_origin_init_fails():
    lat, lon, h = runtime_site()
    origin = runtime_sub_km_ecef()
    n = ecef_norm(origin)
    print(f"sub-km origin norm={n}", flush=True)
    assert n < ORIGIN_NORM_MIN_M
    scen = happy_scenario(lat, lon, h, duration_s=0.05, origin_ecef=origin)
    run = c_ins_run(scen)
    print(f"sub-km init_ok={run.init_ok}", flush=True)
    assert not run.init_ok
    assert not run.last().pos_ok
    ground = ecef_from_llh_deg(lat, lon, h)
    ok = c_ins_run(happy_scenario(lat, lon, h, duration_s=0.05, origin_ecef=ground))
    print(f"ground init_ok={ok.init_ok} norm={ecef_norm(ground)}", flush=True)
    assert ok.init_ok


def test_missing_required_pointer_init_fails():
    lat, lon, h = runtime_site()
    for missing, label in ((1, "init"), (2, "opt")):
        scen = happy_scenario(lat, lon, h, duration_s=0.05, missing=missing)
        run = c_ins_run(scen)
        print(f"missing {label} init_ok={run.init_ok} pos_ok={run.last().pos_ok}", flush=True)
        assert not run.init_ok, f"a missing {label} pointer must fail init"
        assert not run.last().pos_ok, "the instance must not start"


def test_python_auto_init_constructs():
    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h, duration_s=0.05)
    run = py_ins_run(scen)
    print(f"python init_ok={run.init_ok}", flush=True)
    assert run.init_ok, "Python auto-init wrapper with a ground geodetic anchor must start"


# ---------------------------------------------------------------------------
# B. Stationary 100 Hz IMU + 1 Hz 2/2/2 GNSS
# ---------------------------------------------------------------------------


def _assert_happy_ready(run, fix, origin, what):
    last = run.last()
    print(
        f"{what}: ready={last.ready} pos_ok={last.pos_ok} t_us={last.t_us} "
        f"n_used={last.n_gnss_used} n_pred={last.n_predict}",
        flush=True,
    )
    assert run.init_ok
    assert last.ready, f"{what}: ready must be true after dwell + 1.5 s"
    require_finite_solution(last)
    _assert_ecef_matches(last.ecef, fix, what)
    _assert_near_level(last.rpy, what)
    speed = math.sqrt(sum(v * v for v in last.vel_ned))
    print(f"{what}: |v_ned|={speed} m/s", flush=True)
    assert speed < STILL_VEL_MPS, f"{what}: stationary NED speed {speed} is not near rest"
    _ = origin


def test_stationary_2m_gnss_becomes_ready_ecef_level_c_and_python():
    lat, lon, h = runtime_site()
    fix = ecef_from_llh_deg(lat, lon, h)
    scen = happy_scenario(lat, lon, h)
    c_run = c_ins_run(scen)
    py_run = py_ins_run(scen)
    _assert_happy_ready(c_run, fix, fix, "C")
    _assert_happy_ready(py_run, fix, fix, "Python")


def test_coarse_origin_refined_to_gnss_not_init_ecef():
    lat, lon, h = runtime_site()
    gnss = ecef_from_llh_deg(lat, lon, h)
    dn, de, dd = runtime_ned_shift_m()
    origin = ecef_plus_ned(gnss, dn, de, dd)
    print(f"origin shift NED inject=({dn},{de},{dd})", flush=True)
    scen = happy_scenario(lat, lon, h, origin_ecef=origin, gnss_ecef=gnss)
    for kind, runner in (("C", c_ins_run), ("Python", py_ins_run)):
        run = runner(scen)
        last = run.last()
        print(f"{kind} ready={last.ready} ecef={last.ecef} ned={last.ned}", flush=True)
        assert last.ready
        require_finite_solution(last)
        _assert_ecef_matches(last.ecef, gnss, f"{kind} coarse-origin ECEF")
        _assert_not_init_ecef(last.ecef, origin, f"{kind} coarse-origin")


def _assert_post_init_imu_only_accessors(scen, run, kind):
    first = run.first_initialized()
    assert first is not None, f"{kind}: IMU-only stream never initialized"
    after_init_imu_only = 0
    for epoch, snap in zip(scen.epochs, run.snaps):
        if epoch.gnss_ecef is not None or snap.t_us < first.t_us:
            continue
        after_init_imu_only += 1
        assert snap.pos_ok, (
            f"{kind}: IMU-only epoch at t={snap.t_us} was not a normal step "
            "(position accessors failed)"
        )
    print(f"{kind} post-init IMU-only steps={after_init_imu_only}", flush=True)
    assert after_init_imu_only > 0, f"{kind}: no IMU-only epoch after initialization"


def test_imu_only_epoch_is_normal_on_100hz_1hz_stream():
    lat, lon, h = runtime_site()
    mixed = happy_scenario(lat, lon, h)
    imu_only = [e for e in mixed.epochs if e.gnss_ecef is None]
    with_gnss = [e for e in mixed.epochs if e.gnss_ecef is not None]
    print(
        f"stream imu_hz={IMU_HZ} gnss_hz={GNSS_HZ} "
        f"imu_only={len(imu_only)} gnss={len(with_gnss)} total={len(mixed.epochs)}",
        flush=True,
    )
    assert imu_only, "100 Hz / 1 Hz stream has no IMU-only epochs"
    assert len(imu_only) > len(with_gnss), "IMU-only epochs are not the 100 Hz majority"
    # Post-init IMU-only yaw-rate stretch. Skipping those epochs must not
    # produce the same published yaw as processing them (PRD: IMU-only is a
    # normal step). No unpublished numeric yaw bound is pinned.
    yaw_rate = 0.35
    imu_only_count = 40
    processed = site_scenario(
        lat,
        lon,
        h,
        append_imu_only(
            mixed.epochs,
            count=imu_only_count,
            dt_s=1.0 / IMU_HZ,
            gyr=(0.0, 0.0, yaw_rate),
        ),
        origin_ecef=mixed.origin_ecef,
    )
    print(
        f"post-init IMU-only yaw-rate={yaw_rate} rad/s count={imu_only_count}",
        flush=True,
    )
    for kind, runner in (("C", c_ins_run), ("Python", py_ins_run)):
        skipped_run = runner(mixed)
        processed_run = runner(processed)
        skipped = skipped_run.last()
        last = processed_run.last()
        print(
            f"{kind} mixed ready={skipped.ready} pos={skipped.pos_ok} "
            f"yaw={None if skipped.rpy is None else skipped.rpy[2]} | "
            f"processed pos={last.pos_ok} yaw={None if last.rpy is None else last.rpy[2]}",
            flush=True,
        )
        assert skipped_run.init_ok, f"{kind}: IMU-only stream failed construction"
        assert processed_run.init_ok, f"{kind}: IMU-only yaw-rate stretch failed construction"
        assert skipped.ready, (
            f"{kind}: 100 Hz / 1 Hz stream with IMU-only epochs never became ready"
        )
        _assert_post_init_imu_only_accessors(mixed, skipped_run, f"{kind} mixed")
        _assert_post_init_imu_only_accessors(processed, processed_run, f"{kind} processed")
        assert skipped.rpy_ok and skipped.rpy is not None, (
            f"{kind}: mixed stream did not publish attitude"
        )
        assert last.rpy_ok and last.rpy is not None, (
            f"{kind}: IMU-only stretch did not publish attitude"
        )
        dyaw_deg = abs(angle_diff_deg(math.degrees(last.rpy[2]), math.degrees(skipped.rpy[2])))
        print(f"{kind} |yaw_processed - yaw_skipped|={dyaw_deg} deg", flush=True)
        assert dyaw_deg != 0.0, (
            f"{kind}: post-init IMU-only yaw-rate did not change published yaw "
            "relative to skipping those epochs"
        )


def _assert_yaw_unknown_vs_level_axes(snap, what):
    if snap.rpy_std is None:
        raise AssertionError(f"{what}: attitude uncertainty was not published")
    roll_s, pitch_s, yaw_s = snap.rpy_std
    print(
        f"{what}: rpy_std roll={math.degrees(roll_s)} deg "
        f"pitch={math.degrees(pitch_s)} deg yaw={math.degrees(yaw_s)} deg",
        flush=True,
    )
    assert yaw_s > roll_s, (
        f"{what}: unaided yaw uncertainty {yaw_s} is not larger than roll {roll_s}"
    )
    assert yaw_s > pitch_s, (
        f"{what}: unaided yaw uncertainty {yaw_s} is not larger than pitch {pitch_s}"
    )


def test_auto_init_without_heading_leaves_yaw_unknown():
    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h)
    for kind, runner in (("C", c_ins_run), ("Python", py_ins_run)):
        run = runner(scen)
        last = run.last()
        print(f"{kind} ready={last.ready} rpy={last.rpy} rpy_std={last.rpy_std}", flush=True)
        assert last.ready, f"{kind}: default auto-init never became ready"
        assert last.rpy_ok, f"{kind}: attitude was not published after auto-init"
        _assert_yaw_unknown_vs_level_axes(last, f"{kind} unaided yaw")


def test_accel_leveling_follows_specific_force():
    lat, lon, h = runtime_site()
    fy = runtime_roll_fy()
    fx = runtime_pitch_fx()
    level = c_ins_run(happy_scenario(lat, lon, h, acc=SPECIFIC_FORCE_LEVEL))
    roll_arm = c_ins_run(happy_scenario(lat, lon, h, acc=(0.0, fy, -9.81)))
    pitch_arm = c_ins_run(happy_scenario(lat, lon, h, acc=(fx, 0.0, -9.81)))
    for name, run in (("level", level), ("roll", roll_arm), ("pitch", pitch_arm)):
        last = run.last()
        print(f"{name} ready={last.ready} rpy={last.rpy}", flush=True)
        assert last.ready, f"{name} arm must complete auto-init"
        require_finite_solution(last)
    _assert_near_level(level.last().rpy, "level")
    roll_delta = roll_arm.last().rpy[0] - level.last().rpy[0]
    pitch_on_roll_arm = abs(roll_arm.last().rpy[1] - level.last().rpy[1])
    print(f"roll contrast d_roll={_deg(roll_delta)} deg fy={fy}", flush=True)
    assert abs(roll_delta) > LEVEL_RAD, "roll arm is not distinguishable from level"
    # Geometry: at rest, a more-negative body-y specific force is a positive roll.
    if fy < 0.0:
        assert roll_delta > 0.0, "roll sign does not follow a negative fy"
    else:
        assert roll_delta < 0.0, "roll sign does not follow a positive fy"
    _ = pitch_on_roll_arm
    pitch_delta = pitch_arm.last().rpy[1] - level.last().rpy[1]
    print(f"pitch contrast d_pitch={_deg(pitch_delta)} deg fx={fx}", flush=True)
    assert abs(pitch_delta) > LEVEL_RAD, "pitch arm is not distinguishable from level"
    # Geometry: at rest, a more-positive body-x specific force is a positive pitch.
    if fx > 0.0:
        assert pitch_delta > 0.0, "pitch sign does not follow a positive fx"
    else:
        assert pitch_delta < 0.0, "pitch sign does not follow a negative fx"


def test_zeroed_process_noise_still_fuses_later_gnss():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    dn, de, dd = runtime_gnss_step_m()
    stepped = ecef_plus_ned(origin, dn, de, dd)
    warm = stationary_imu_gnss_stream(origin, duration_s=HAPPY_DURATION_S)
    follow = stationary_imu_gnss_stream(
        stepped, duration_s=6.0, gnss_std=GNSS_STD_M
    )
    scen = site_scenario(lat, lon, h, warm + retimed(follow, warm[-1].t_us))
    run = c_ins_run(scen)
    last = run.last()
    print(
        f"after step ready={last.ready} |ecef-old|={hypot3(last.ecef, origin)} "
        f"|ecef-new|={hypot3(last.ecef, stepped)}",
        flush=True,
    )
    assert last.ready
    require_finite_solution(last)
    dist_new = hypot3(last.ecef, stepped)
    dist_old = hypot3(last.ecef, origin)
    assert dist_new < dist_old, "zeroed options locked the filter against later GNSS"
    assert dist_new < ECEF_MATCH_M * 8.0, "later GNSS did not move ECEF toward the new fix"


# ---------------------------------------------------------------------------
# C. Lever arm
# ---------------------------------------------------------------------------


def _yaw_rate_after_ready(lat, lon, h, lever, yaw_rate=0.25, yaw_s=3.0):
    origin = ecef_from_llh_deg(lat, lon, h)
    warm = stationary_imu_gnss_stream(origin, duration_s=HAPPY_DURATION_S, lever=lever)
    yaw = stationary_imu_gnss_stream(
        origin, duration_s=yaw_s, gyr=(0.0, 0.0, yaw_rate), lever=lever
    )
    return site_scenario(lat, lon, h, warm + retimed(yaw, warm[-1].t_us))


def _innovation_or_ned(run):
    last = run.last()
    require_finite_solution(last)
    return last.residual_m, last.ecef, last.ned


def test_lever_arm_changes_gnss_innovation_under_yaw_rate():
    lat, lon, h = runtime_site()
    zero = _yaw_rate_after_ready(lat, lon, h, (0.0, 0.0, 0.0))
    right = _yaw_rate_after_ready(lat, lon, h, LEVER_RIGHT_15CM)
    for kind, runner in (("C", c_ins_run), ("Python", py_ins_run)):
        z = runner(zero)
        r = runner(right)
        z_res, z_ecef, z_ned = _innovation_or_ned(z)
        r_res, r_ecef, r_ned = _innovation_or_ned(r)
        print(
            f"{kind} zero residual={z_res} ecef={z_ecef} ned={z_ned} | "
            f"right residual={r_res} ecef={r_ecef} ned={r_ned}",
            flush=True,
        )
        if z_res is not None and r_res is not None:
            assert z_res != r_res, f"{kind}: 15 cm right lever left the GNSS residual unchanged"
        # GNSS locates the antenna; the filter reports the body. With the
        # antenna fix held at the pad, the body sits at the fix minus the
        # lever rotated into NED by the published yaw (Contract
        # gnss_leverarm_b, body FRD). Check that offset's size and direction.
        yaw = r.last().rpy[2]
        lx, ly, _lz = LEVER_RIGHT_15CM
        want_n = -(lx * math.cos(yaw) - ly * math.sin(yaw))
        want_e = -(lx * math.sin(yaw) + ly * math.cos(yaw))
        got_n = r_ned[0] - z_ned[0]
        got_e = r_ned[1] - z_ned[1]
        got = math.hypot(got_n, got_e)
        want = math.hypot(want_n, want_e)
        cos = (got_n * want_n + got_e * want_e) / (got * want) if got > 0.0 else -1.0
        print(
            f"{kind} body offset right-zero NE=({got_n:+.4f},{got_e:+.4f}) |{got:.4f}| "
            f"want -R(yaw)*lever=({want_n:+.4f},{want_e:+.4f}) cos={cos:+.3f}",
            flush=True,
        )
        assert 0.05 < got < 0.30, (
            f"{kind}: body offset between zero and 15 cm right lever runs is {got:.3f} m, "
            "not the lever's size"
        )
        assert cos > 0.5, (
            f"{kind}: body offset is not on the side opposite the rotated lever "
            f"(cos={cos:+.3f}); lever arm ignored, sign-flipped or in the wrong frame"
        )


def test_runtime_lever_arm_changes_innovation():
    lat, lon, h = runtime_site()
    lever = runtime_lever()
    zero = _yaw_rate_after_ready(lat, lon, h, (0.0, 0.0, 0.0))
    other = _yaw_rate_after_ready(lat, lon, h, lever)
    for kind, runner in (("C", c_ins_run), ("Python", py_ins_run)):
        z = runner(zero)
        o = runner(other)
        z_res, z_ecef, z_ned = _innovation_or_ned(z)
        o_res, o_ecef, o_ned = _innovation_or_ned(o)
        print(
            f"{kind} runtime lever {lever} residual {z_res} vs {o_res} "
            f"|ecef|={hypot3(z_ecef, o_ecef)} |ned|={hypot3(z_ned, o_ned)}",
            flush=True,
        )
        distinguishable = False
        if z_res is not None and o_res is not None and z_res != o_res:
            distinguishable = True
        if hypot3(z_ecef, o_ecef) > 1e-4 or hypot3(z_ned, o_ned) > 1e-4:
            distinguishable = True
        assert distinguishable, f"{kind}: runtime lever was treated as zero under yaw rate"


# ---------------------------------------------------------------------------
# D. Ready dual gate and accessors
# ---------------------------------------------------------------------------


def test_accessors_fail_before_initialized():
    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h, duration_s=1.0)
    run = c_ins_run(scen)
    last = run.last()
    print(
        f"pre-init ready={last.ready} pos={last.pos_ok} vel={last.vel_ok} rpy={last.rpy_ok}",
        flush=True,
    )
    assert run.init_ok
    assert not last.ready
    assert not last.pos_ok, "position accessors must fail before initialization"
    assert not last.vel_ok
    assert not last.rpy_ok


def test_accessors_succeed_after_init_while_ready_false():
    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h, duration_s=HAPPY_DURATION_S)
    run = c_ins_run(scen)
    first = run.first_initialized()
    last = run.last()
    print(
        f"first t_us={None if first is None else first.t_us} "
        f"first_ready={None if first is None else first.ready} last_ready={last.ready}",
        flush=True,
    )
    assert first is not None, "auto-init never published accessors"
    require_finite_solution(first)
    assert not first.ready, "the first initialized epoch must not already be ready"
    assert last.ready, "later the same stream must become ready (live baseline)"


def test_ready_false_until_1_5_s_after_initialization():
    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h, duration_s=ENTRY_DWELL_S + 3.0)
    run = c_ins_run(scen)
    first = run.first_initialized()
    assert first is not None
    t0 = first.t_us
    early = None
    late = None
    for snap in run.snaps:
        if not snap.pos_ok:
            continue
        age = (snap.t_us - t0) * 1e-6
        if age <= 1.40:
            early = snap
        if age >= READY_WAIT_S:
            late = snap
            break
    print(
        f"t_init={t0} early_age={None if early is None else (early.t_us - t0) * 1e-6} "
        f"early_ready={None if early is None else early.ready} "
        f"late_ready={None if late is None else late.ready}",
        flush=True,
    )
    assert early is not None
    assert not early.ready, "ready was true before 1.5 s after initialization"
    assert late is not None and late.ready, "ready did not become true once 1.5 s and updates elapsed"
    assert run.last().ready


def test_ready_false_until_four_filter_updates():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    warm = happy_scenario(lat, lon, h, duration_s=ENTRY_DWELL_S + 1.4)
    probe = c_ins_run(scen := warm)
    first = probe.first_initialized()
    assert first is not None
    kept = clip_through_initialized(scen.epochs, first.t_us)
    few = append_sparse_imu(kept, count=POST_INIT_SPARSE, dt_s=SPARSE_DT_S, gnss_ecef=origin)
    age = (few[-1].t_us - first.t_us) * 1e-6
    print(f"sparse age={age}s n_post={POST_INIT_SPARSE}", flush=True)
    assert age >= READY_WAIT_S - 1e-6
    few_run = c_ins_run(site_scenario(lat, lon, h, few))
    last_few = few_run.last()
    print(
        f"few ready={last_few.ready} pos={last_few.pos_ok} n_pred={last_few.n_predict}",
        flush=True,
    )
    assert last_few.pos_ok, "accessors must succeed once initialized even if not ready"
    assert not last_few.ready, "ready was true with fewer than four post-init filter updates"
    enough = append_sparse_imu(few, count=SPARSE_MORE, dt_s=SPARSE_DT_S, gnss_ecef=origin)
    enough_run = c_ins_run(site_scenario(lat, lon, h, enough))
    last_ok = enough_run.last()
    print(f"enough ready={last_ok.ready} n_pred={last_ok.n_predict}", flush=True)
    assert last_ok.ready, "ready stayed false after both time and four-update conditions"


def test_first_epoch_not_ready():
    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h, duration_s=0.01)
    run = c_ins_run(scen)
    last = run.last()
    print(f"first-epoch ready={last.ready} pos={last.pos_ok} n={len(run.snaps)}", flush=True)
    assert run.init_ok
    assert not last.ready, "ready was true on the first epoch"


# ---------------------------------------------------------------------------
# E. Invalid IMU, GNSS sub-measurements, fusion gate
# ---------------------------------------------------------------------------


def _run_from_initialized(lat, lon, h, extra_epochs):
    origin = ecef_from_llh_deg(lat, lon, h)
    warm = happy_scenario(lat, lon, h, duration_s=ENTRY_DWELL_S + 1.4)
    first = c_ins_run(warm).first_initialized()
    assert first is not None
    kept = clip_through_initialized(warm.epochs, first.t_us)
    return origin, first, kept, extra_epochs


def test_invalid_gyro_is_not_strapdown_later_imu_continues():
    lat, lon, h = runtime_site()
    origin, first, kept, _ = _run_from_initialized(lat, lon, h, None)
    yaw_rate = 0.35
    valid = append_sparse_imu(
        kept, count=4, dt_s=0.05, gnss_ecef=origin, gyr=(0.0, 0.0, yaw_rate), gyr_valid=True
    )
    invalid = append_sparse_imu(
        kept, count=4, dt_s=0.05, gnss_ecef=origin, gyr=(0.0, 0.0, yaw_rate), gyr_valid=False
    )
    # Keep specific force at the level rest sample so the invalid-gyro arm
    # cannot look "alive" from accelerometer leveling.
    v_run = c_ins_run(site_scenario(lat, lon, h, valid))
    i_run = c_ins_run(site_scenario(lat, lon, h, invalid))
    v_last = v_run.last()
    i_last = i_run.last()
    v0 = next(s for s in v_run.snaps if s.t_us == first.t_us)
    i0 = next(s for s in i_run.snaps if s.t_us == first.t_us)
    print(
        f"gyro valid yaw {v0.rpy[2]} -> {v_last.rpy[2]} | "
        f"invalid {i0.rpy[2]} -> {i_last.rpy[2]}",
        flush=True,
    )
    require_finite_solution(v_last)
    require_finite_solution(i_last)
    dy_valid = abs(v_last.rpy[2] - v0.rpy[2])
    dy_invalid = abs(i_last.rpy[2] - i0.rpy[2])
    assert dy_valid > dy_invalid + math.radians(0.2), (
        "invalid gyro still took the yaw-rate strapdown step"
    )
    continued = append_sparse_imu(
        invalid, count=4, dt_s=0.05, gnss_ecef=origin, gyr=(0.0, 0.0, 0.0), gyr_valid=True
    )
    c_run = c_ins_run(site_scenario(lat, lon, h, continued))
    print(f"later valid imu pos_ok={c_run.last().pos_ok}", flush=True)
    assert c_run.last().pos_ok, "filter died after an invalid gyro epoch"


def test_invalid_accel_is_not_strapdown_later_imu_continues():
    lat, lon, h = runtime_site()
    origin, first, kept, _ = _run_from_initialized(lat, lon, h, None)
    tilted = (2.0, 0.0, -9.81)
    valid = append_sparse_imu(
        kept, count=8, dt_s=0.05, gnss_ecef=origin, acc=tilted, acc_valid=True
    )
    invalid = append_sparse_imu(
        kept, count=8, dt_s=0.05, gnss_ecef=origin, acc=tilted, acc_valid=False
    )
    # The automatic standstill detector (on by default, tuning unspecified)
    # is not under test: a latched stationary verdict would clamp the VALID
    # control arm. Both arms turn it off through the public option.
    v_run = c_ins_run(site_scenario(lat, lon, h, valid, auto_zupt_disable=True))
    i_run = c_ins_run(site_scenario(lat, lon, h, invalid, auto_zupt_disable=True))
    v0 = next(s for s in v_run.snaps if s.t_us == first.t_us)
    i0 = next(s for s in i_run.snaps if s.t_us == first.t_us)
    v_last, i_last = v_run.last(), i_run.last()
    print(
        f"accel valid vel {v0.vel_ned} -> {v_last.vel_ned} | "
        f"invalid {i0.vel_ned} -> {i_last.vel_ned}",
        flush=True,
    )
    require_finite_solution(v_last)
    require_finite_solution(i_last)
    dv_valid = hypot3(v_last.vel_ned, v0.vel_ned)
    dv_invalid = hypot3(i_last.vel_ned, i0.vel_ned)
    assert dv_valid > dv_invalid + 0.05, "invalid accel still took the strapdown step"
    continued = append_sparse_imu(
        invalid, count=4, dt_s=0.05, gnss_ecef=origin, acc=SPECIFIC_FORCE_LEVEL, acc_valid=True
    )
    c_run = c_ins_run(site_scenario(lat, lon, h, continued, auto_zupt_disable=True))
    assert c_run.last().pos_ok, "filter died after an invalid accel epoch"


def _gnss_step_stream(lat, lon, h, std, offset_ned, duration_follow_s=6.0):
    origin = ecef_from_llh_deg(lat, lon, h)
    stepped = ecef_plus_ned(origin, *offset_ned)
    warm = happy_scenario(lat, lon, h, duration_s=HAPPY_DURATION_S)
    first_ready = None
    base = c_ins_run(warm)
    for snap in base.snaps:
        if snap.ready:
            first_ready = snap
            break
    assert first_ready is not None
    kept = [e for e in warm.epochs if e.t_us <= first_ready.t_us]
    follow = stationary_imu_gnss_stream(stepped, duration_s=duration_follow_s, gnss_std=std)
    return origin, stepped, site_scenario(lat, lon, h, kept + retimed(follow, kept[-1].t_us))


def test_nonpositive_gnss_variance_not_fused_filter_stays_up():
    lat, lon, h = runtime_site()
    offset = runtime_gnss_step_m()
    origin, stepped, good = _gnss_step_stream(lat, lon, h, GNSS_STD_M, offset)
    _, _, bad = _gnss_step_stream(lat, lon, h, (0.0, 2.0, 2.0), offset)
    good_run = c_ins_run(good)
    bad_run = c_ins_run(bad)
    g, b = good_run.last(), bad_run.last()
    print(
        f"good |ecef-new|={hypot3(g.ecef, stepped)} |ecef-old|={hypot3(g.ecef, origin)} "
        f"bad |ecef-new|={hypot3(b.ecef, stepped)} |ecef-old|={hypot3(b.ecef, origin)} "
        f"used {g.n_gnss_used} vs {b.n_gnss_used}",
        flush=True,
    )
    require_finite_solution(g)
    require_finite_solution(b)
    assert hypot3(g.ecef, stepped) < hypot3(g.ecef, origin)
    assert hypot3(b.ecef, origin) < hypot3(b.ecef, stepped), (
        "non-positive GNSS variance was fused"
    )
    # Subsequent good GNSS still moves the filter (not shut down).
    recover_epochs = append_sparse_imu(
        bad.epochs, count=8, dt_s=0.5, gnss_ecef=stepped, gnss_std=GNSS_STD_M
    )
    rec = c_ins_run(site_scenario(lat, lon, h, recover_epochs))
    print(f"recover |ecef-new|={hypot3(rec.last().ecef, stepped)} pos={rec.last().pos_ok}", flush=True)
    assert rec.last().pos_ok
    assert hypot3(rec.last().ecef, stepped) < hypot3(rec.last().ecef, origin)


def test_gnss_beyond_fusion_gate_not_fused_filter_stays_up():
    lat, lon, h = runtime_site()
    offset = runtime_gnss_step_m()
    origin = ecef_from_llh_deg(lat, lon, h)
    stepped = ecef_plus_ned(origin, *offset)
    gate = 3.0
    coarse_std = (12.0, 12.0, 12.0)
    warm = happy_scenario(lat, lon, h, duration_s=HAPPY_DURATION_S, fusion_h=gate, fusion_v=gate)
    base = c_ins_run(warm)
    first_ready = next(s for s in base.snaps if s.ready)
    kept = [e for e in warm.epochs if e.t_us <= first_ready.t_us]
    follow = stationary_imu_gnss_stream(stepped, duration_s=3.0, gnss_std=coarse_std)
    gated = site_scenario(
        lat, lon, h, kept + retimed(follow, kept[-1].t_us), fusion_h=gate, fusion_v=gate
    )
    run = c_ins_run(gated)
    last = run.last()
    print(
        f"gated |ecef-old|={hypot3(last.ecef, origin)} |ecef-new|={hypot3(last.ecef, stepped)} "
        f"n_rej={last.n_gnss_rejected_noise}",
        flush=True,
    )
    require_finite_solution(last)
    assert hypot3(last.ecef, origin) < hypot3(last.ecef, stepped), (
        "a fix coarser than the fusion gate was fused"
    )
    gated_to_new = hypot3(last.ecef, stepped)
    rec_follow = stationary_imu_gnss_stream(stepped, duration_s=8.0, gnss_std=GNSS_STD_M)
    rec = c_ins_run(
        site_scenario(
            lat,
            lon,
            h,
            gated.epochs + retimed(rec_follow, gated.epochs[-1].t_us),
            fusion_h=gate,
            fusion_v=gate,
        )
    )
    rec_to_new = hypot3(rec.last().ecef, stepped)
    print(
        f"inside-gate |ecef-new|={rec_to_new} was {gated_to_new} pos={rec.last().pos_ok}",
        flush=True,
    )
    assert rec.last().pos_ok
    assert rec_to_new < gated_to_new, (
        "an in-gate fix after a gated rejection did not move the still-live filter"
    )


def test_gnss_diagonal_covariance_fuses():
    lat, lon, h = runtime_site()
    fix = ecef_from_llh_deg(lat, lon, h)
    scen = happy_scenario(lat, lon, h)
    run = c_ins_run(scen)
    last = run.last()
    print(f"diag 3x3 ready={last.ready} used={last.n_gnss_used}", flush=True)
    assert last.ready
    _assert_ecef_matches(last.ecef, fix, "explicit diagonal 3x3")


def test_c_gnss_velocity_ned_distinguishable():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    vn = runtime_north_vel()
    warm = happy_scenario(lat, lon, h, duration_s=HAPPY_DURATION_S)
    base = c_ins_run(warm)
    first_ready = next(s for s in base.snaps if s.ready)
    kept = [e for e in warm.epochs if e.t_us <= first_ready.t_us]
    # Same turning IMU on both arms so automatic standstill aiding (FP-03,
    # default on) does not pin velocity to zero and hide GNSS velocity.
    turning = (0.0, 0.0, 0.20)
    pos_only = stationary_imu_gnss_stream(origin, duration_s=5.0, gyr=turning)
    with_vel = stationary_imu_gnss_stream(
        origin,
        duration_s=5.0,
        gyr=turning,
        gnss_vel=(vn, 0.0, 0.0),
        gnss_vel_std=(0.08, 0.08, 0.08),
    )
    pos_run = c_ins_run(site_scenario(lat, lon, h, kept + retimed(pos_only, kept[-1].t_us)))
    vel_run = c_ins_run(site_scenario(lat, lon, h, kept + retimed(with_vel, kept[-1].t_us)))
    pv, vv = pos_run.last().vel_ned, vel_run.last().vel_ned
    print(f"pos-only vel={pv} with-north vel={vv} inject={vn}", flush=True)
    require_finite_solution(pos_run.last())
    require_finite_solution(vel_run.last())
    delta = hypot3(pv, vv)
    north_pull = (vv[0] - pv[0]) * (1.0 if vn > 0.0 else -1.0)
    print(f"C vel contrast |d|={delta} north_pull={north_pull}", flush=True)
    assert delta > 1e-3, "C GNSS velocity did not change published NED velocity"
    assert north_pull > 5e-4, "C GNSS north velocity did not pull published north speed"


# ---------------------------------------------------------------------------
# F. Python three-move loop
# ---------------------------------------------------------------------------


def test_python_three_move_loop_becomes_ready():
    lat, lon, h = runtime_site()
    fix = ecef_from_llh_deg(lat, lon, h)
    run = py_ins_run(happy_scenario(lat, lon, h))
    _assert_happy_ready(run, fix, fix, "Python three-move")


def test_python_skip_epoch_never_ready():
    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h, skip_epoch=True)
    run = py_ins_run(scen)
    last = run.last()
    print(f"skip-epoch ready={last.ready} pos={last.pos_ok}", flush=True)
    assert run.init_ok
    assert not last.ready, "skipping the epoch step still became ready"


def test_python_reader_does_not_advance_filter():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    warm = happy_scenario(lat, lon, h, duration_s=ENTRY_DWELL_S + 1.4)
    first = py_ins_run(warm).first_initialized()
    assert first is not None
    kept = clip_through_initialized(warm.epochs, first.t_us)
    few = append_sparse_imu(kept, count=POST_INIT_SPARSE, dt_s=SPARSE_DT_S, gnss_ecef=origin)
    unread = py_ins_run(site_scenario(lat, lon, h, few))
    print(f"before reads ready={unread.last().ready} pos={unread.last().pos_ok}", flush=True)
    assert unread.last().pos_ok
    assert not unread.last().ready
    read_only = py_ins_run(site_scenario(lat, lon, h, few, extra_reads=12))
    print(f"after reads ready={read_only.last().ready}", flush=True)
    assert not read_only.last().ready, "reader calls themselves advanced the filter to ready"
    enough = append_sparse_imu(few, count=SPARSE_MORE, dt_s=SPARSE_DT_S, gnss_ecef=origin)
    done = py_ins_run(site_scenario(lat, lon, h, enough))
    print(f"after push+epoch ready={done.last().ready}", flush=True)
    assert done.last().ready, "push+epoch after the four-update remainder never became ready"


def test_python_gnss_accepts_diagonal_and_full_covariance():
    lat, lon, h = runtime_site()
    fix = ecef_from_llh_deg(lat, lon, h)
    diag = py_ins_run(happy_scenario(lat, lon, h, py_full_cov=False))
    full = py_ins_run(happy_scenario(lat, lon, h, py_full_cov=True))
    _assert_happy_ready(diag, fix, fix, "Python diagonal cov")
    _assert_happy_ready(full, fix, fix, "Python full 3x3 cov")


def test_python_gnss_velocity_is_ned():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    vn = runtime_north_vel()
    warm = happy_scenario(lat, lon, h, duration_s=HAPPY_DURATION_S)
    base = py_ins_run(warm)
    first_ready = next(s for s in base.snaps if s.ready)
    kept = [e for e in warm.epochs if e.t_us <= first_ready.t_us]
    turning = (0.0, 0.0, 0.20)
    pos_only = stationary_imu_gnss_stream(origin, duration_s=5.0, gyr=turning)
    with_vel = stationary_imu_gnss_stream(
        origin,
        duration_s=5.0,
        gyr=turning,
        gnss_vel=(vn, 0.0, 0.0),
        gnss_vel_std=(0.08, 0.08, 0.08),
    )
    pos_run = py_ins_run(site_scenario(lat, lon, h, kept + retimed(pos_only, kept[-1].t_us)))
    vel_run = py_ins_run(site_scenario(lat, lon, h, kept + retimed(with_vel, kept[-1].t_us)))
    print(
        f"python pos-only vel={pos_run.last().vel_ned} with-vel={vel_run.last().vel_ned}",
        flush=True,
    )
    require_finite_solution(pos_run.last())
    require_finite_solution(vel_run.last())
    pv, vv = pos_run.last().vel_ned, vel_run.last().vel_ned
    delta = hypot3(pv, vv)
    north_pull = (vv[0] - pv[0]) * (1.0 if vn > 0.0 else -1.0)
    print(f"Python vel contrast |d|={delta} north_pull={north_pull}", flush=True)
    assert delta > 1e-3, "Python GNSS velocity did not change published NED velocity"
    assert north_pull > 5e-4, "Python GNSS north velocity did not pull published north speed"


def test_published_ins_snapshots_are_well_formed():
    """Contract accessors on the INS wrapper and filter: a published value is
    finite, attitude is not published without its 1-sigma (Python ``rpy`` /
    ``stddev``), and the diagnostic counters exist and are non-negative
    (``ins_get_diag`` / ``diag``). Checked on every INS snapshot parsed in this
    session -- the other tests of this file included -- and on a pad of its
    own. A violation fails this test only, not every test that parses one.
    """
    from _harness import require_no_product_issues

    lat, lon, h = runtime_site()
    scen = happy_scenario(lat, lon, h)
    for runner in (c_ins_run, py_ins_run):
        run = runner(scen)
        assert run.snaps, "pad produced no snapshots"
    require_no_product_issues("F02", "INS snapshots (F02)")
