# feature: F05
"""Quality gates, coasting, and re-acquisition (FP-05).

Assertions stay at the PRD's precision: a 10 m 1-sigma stream stays fusable
but does not start 3D under the default entry gate; a 5 s dwell of
entry-quality fixes does start 3D; 10 s of exit-quality-or-worse fixes
re-arm so ready is false and position/velocity accessors fail until a
full re-bootstrap through the entry gate. A 3 s GNSS outage inside the
10 s window keeps ready true with a dead-reckoning age about 3000 ms;
11 s of IMU-only (unlimited off) freezes the instance so ready is false
and the state no longer integrates; the next fusion-usable fix re-anchors
and ready is true on that epoch. Unlimited dead reckoning keeps ready
true through that 11 s and treats the next fix as ordinary fusion. Default
GNSS rate limiting does not fuse every sample of a 50 Hz stream and is
suspended while the coasting window is expired. Omitting the
position-decimation option spends every combined position-and-velocity
epoch as a position fuse. Message text, exception types, unpublished
cadence knobs, and millimetre gold values are not pinned.
"""

from __future__ import annotations

from F01_helpers import hypot3
from F02_helpers import ENTRY_DWELL_S, READY_WAIT_S, ecef_from_llh_deg, runtime_site
from F03_helpers import TRACKER_NAMED_NED, angle_diff_rad, isa_pressure_pa
from F05_helpers import (
    BETWEEN_POS_STD,
    ENTRY_POS_STD,
    ENTRY_VEL_STD,
    EXIT_VEL_BAD_STD,
    FEW_HZ,
    FREEZE_11S,
    GNSS_50HZ,
    NAMED_10M_STD,
    NORTH_ACCEL,
    OUTAGE_3S,
    OUTAGE_7S,
    RAISED_ENTRY_M,
    READY_PAD_S,
    SPECIFIC_FORCE_LEVEL,
    UNFUSABLE_POS_STD,
    UNDER_CAP_STD,
    UNDER_VEL_CAP_STD,
    VEL_H_BAD_STD,
    VEL_V_BAD_STD,
    ZERO_VEL,
    _gate_epoch,
    append_combined_north_steps,
    append_stream,
    coast_acc,
    coast_imu,
    dist_m,
    c_gate_run,
    gate_langs,
    gate_site,
    north_increments,
    north_of,
    north_pull_m,
    pad_ready,
    runtime_east_vel_mps,
    require_initialized,
    require_not_initialized,
    require_ready_gate,
    runtime_between_gate_sigma_m,
    runtime_coarse_sigma_m,
    runtime_in_window_outage_s,
    runtime_north_offset_m,
    runtime_under_cap_sigma_m,
    runtime_under_vel_cap_sigma_mps,
    yaw_gyr,
)


def _site():
    lat, lon, h = runtime_site()
    origin = ecef_from_llh_deg(lat, lon, h)
    return lat, lon, h, origin


def _scen(lat, lon, h, epochs, origin, **kwargs):
    return gate_site(lat, lon, h, epochs, origin_ecef=origin, **kwargs)


def _assert_follows_north(origin, ecef, north_m, what, *, min_frac=0.15):
    got = north_pull_m(origin, ecef)
    print(f"{what}: north={got} m target={north_m} m", flush=True)
    assert got * north_m > 0.0, f"{what}: published north {got} did not follow {north_m} m"
    assert abs(got) > abs(north_m) * min_frac, (
        f"{what}: published north {got} m is not a visible pull toward {north_m} m"
    )


def _assert_not_at_offset(origin, ecef, north_m, what):
    got = north_pull_m(origin, ecef)
    print(f"{what}: north={got} m (must not sit on {north_m} m)", flush=True)
    assert abs(got - north_m) > abs(north_m) * 0.4, (
        f"{what}: published north {got} m sat on the offset {north_m} m"
    )


def _counted_skip(start, last, what):
    """Skip count after stripping diagnostic field names.

    PRD counts skipped extras; it does not name a dedicated rate-limit
    field. Offered-minus-fused is one remaining sortable integer.
    """
    offered = last.n_seen - start.n_seen
    fused = last.n_used - start.n_used
    assert offered >= 0, f"{what}: offered GNSS count went backwards ({offered})"
    assert fused >= 0, f"{what}: fused GNSS count went backwards ({fused})"
    skip = offered - fused
    assert skip >= 0, f"{what}: fused {fused} exceeds offered {offered}"
    return offered, fused, skip


def _assert_gate_langs(scen, what):
    """Same-file wrapper so an empty language list cannot finish green."""
    pairs = list(gate_langs(scen))
    assert pairs, f"{what}: expected C/Python observations, got none"
    return pairs


def _assert_initialized(snap, what):
    require_initialized(snap, what)
    assert snap.pos_ok, f"{what}: position accessors did not succeed (3D not started)"
    assert snap.vel_ok, f"{what}: velocity accessors failed while initialized"
    assert snap.ecef is not None, f"{what}: initialized snapshot has no ECEF"


def _assert_not_initialized(snap, what):
    require_not_initialized(snap, what)
    assert not snap.pos_ok, f"{what}: position accessors still succeeded"
    assert not snap.vel_ok, f"{what}: velocity accessors still succeeded"
    assert not snap.ready, f"{what}: ready stayed true while uninitialized"


def _assert_ready_gate(snap, what):
    require_ready_gate(snap, what)
    assert snap.ready, f"{what}: ready was false"
    assert snap.pos_ok, f"{what}: position accessors failed while ready"


# ---------------------------------------------------------------------------
# A. Three gates: fusion vs entry vs dwell
# ---------------------------------------------------------------------------


def test_10m_sigma_fusable_but_not_3d_under_default_entry():
    lat, lon, h, origin = _site()
    coarse = pad_ready(origin, duration_s=READY_PAD_S, gnss_std=NAMED_10M_STD)
    good = pad_ready(origin, duration_s=READY_PAD_S, gnss_std=ENTRY_POS_STD)
    runtime = runtime_coarse_sigma_m()
    runtime_epochs = pad_ready(
        origin, duration_s=READY_PAD_S, gnss_std=(runtime, runtime, runtime)
    )
    for kind, run in gate_langs(_scen(lat, lon, h, coarse, origin)):
        last = run.last()
        print(f"{kind} 10 m last ready={last.ready} pos={last.pos_ok}", flush=True)
        assert not last.ready, f"{kind}: 10 m stream became ready 3D under default entry"
        require_not_initialized(last, f"{kind} 10 m default entry")
    for kind, run in gate_langs(_scen(lat, lon, h, good, origin)):
        last = run.last()
        print(f"{kind} entry-quality last ready={last.ready} pos={last.pos_ok}", flush=True)
        require_initialized(last, f"{kind} entry-quality baseline")
        assert run.first_initialized() is not None
    for kind, run in gate_langs(_scen(lat, lon, h, runtime_epochs, origin)):
        last = run.last()
        print(f"{kind} runtime {runtime} m pos={last.pos_ok}", flush=True)
        require_not_initialized(last, f"{kind} runtime coarse sigma")


def test_coarse_sigma_consumed_during_cold_start():
    lat, lon, h, origin = _site()
    gnss_n = sum(
        1
        for e in pad_ready(origin, duration_s=READY_PAD_S, gnss_std=NAMED_10M_STD)
        if e.gnss_ecef is not None
    )
    print(f"cold-start 10 m GNSS epochs offered={gnss_n}", flush=True)
    assert gnss_n > 5
    coarse = pad_ready(origin, duration_s=READY_PAD_S, gnss_std=NAMED_10M_STD)
    broken = pad_ready(origin, duration_s=READY_PAD_S, gnss_std=UNFUSABLE_POS_STD)
    raised = _scen(
        lat,
        lon,
        h,
        coarse,
        origin,
        entry_h=RAISED_ENTRY_M,
        entry_v=RAISED_ENTRY_M,
    )
    default = _scen(lat, lon, h, coarse, origin)
    unfusable_raised = _scen(
        lat,
        lon,
        h,
        broken,
        origin,
        entry_h=RAISED_ENTRY_M,
        entry_v=RAISED_ENTRY_M,
    )
    for kind, run in gate_langs(default):
        last = run.last()
        mid = run.at_or_before(int((READY_PAD_S * 0.5) * 1e6))
        print(
            f"{kind} cold-start 10 m mid pos={mid.pos_ok} last pos={last.pos_ok} "
            f"seen={last.n_seen} used={last.n_used}",
            flush=True,
        )
        require_not_initialized(mid, f"{kind} 10 m still collecting mid-stream")
        require_not_initialized(last, f"{kind} 10 m never started 3D")
        assert last.t_us >= coarse[-1].t_us - 20000, (
            f"{kind}: instance stopped taking 10 m epochs before the stream ended"
        )
        assert len(run.snaps) >= len(coarse) - 2, (
            f"{kind}: default entry dropped the 10 m stream "
            f"({len(run.snaps)} snapshots for {len(coarse)} epochs)"
        )
    for kind, run in gate_langs(raised):
        last = run.last()
        print(f"{kind} same 10 m with raised entry pos={last.pos_ok}", flush=True)
        require_initialized(last, f"{kind} 10 m consumed: raising entry starts 3D")
    for kind, run in gate_langs(unfusable_raised):
        last = run.last()
        print(f"{kind} unfusable with raised entry pos={last.pos_ok}", flush=True)
        require_not_initialized(last, f"{kind} broken covariance was not consumed as fusable")


def test_coarse_sigma_consumed_after_3d():
    lat, lon, h, origin = _site()
    north = runtime_north_offset_m()
    offset = north_of(origin, north)
    tens = runtime_under_cap_sigma_m()
    for std, label in (
        (NAMED_10M_STD, "10 m"),
        ((tens, tens, tens), f"{tens:.1f} m under cap"),
    ):
        # Position-only: a tight v=0 would fight the 10 m / tens-of-metres
        # position pull. Duration is long enough for a 47 m 1-sigma to still
        # move relative to a non-positive twin.
        follow_s = 8.0
        fused = pad_ready(origin)
        fused = append_stream(
            fused,
            duration_s=follow_s,
            origin=origin,
            gnss_ecef=offset,
            gnss_std=std,
            gnss_vel=None,
        )
        broken = pad_ready(origin)
        broken = append_stream(
            broken,
            duration_s=follow_s,
            origin=origin,
            gnss_ecef=offset,
            gnss_std=UNFUSABLE_POS_STD,
            gnss_vel=None,
        )
        fused_runs = list(gate_langs(_scen(lat, lon, h, fused, origin)))
        broken_runs = list(gate_langs(_scen(lat, lon, h, broken, origin)))
        for (kind, run), (_, br) in zip(fused_runs, broken_runs):
            require_ready_gate(run.at_or_before(int(READY_PAD_S * 1e6)), f"{kind} {label} pad")
            last = run.last()
            require_ready_gate(last, f"{kind} {label} fused")
            require_initialized(br.last(), f"{kind} {label} broken still 3D")
            fn = north_pull_m(origin, last.ecef)
            bn = north_pull_m(origin, br.last().ecef)
            print(
                f"{kind} {label} fused north={fn} m broken={bn} m target={north} m",
                flush=True,
            )
            assert fn * north > 0.0, f"{kind} {label}: fused ECEF did not follow the offset"
            assert abs(fn) > abs(bn) + 0.08, (
                f"{kind} {label}: fused north {fn} m is not past the non-positive twin {bn} m"
            )
            _assert_not_at_offset(origin, br.last().ecef, north, f"{kind} {label} broken")


def test_mid_cap_velocity_fused_after_3d():
    """unconfigured fusion-velocity defaults equal the 60 m/s cap.

    After 3D, a GNSS velocity whose reported 1-sigma is worse than the
    entry numbers (0.25 / 0.30 m/s) but still below that cap must still
    fuse: published NED velocity moves toward the GNSS velocity. A twin
    that differs only by a non-positive velocity-covariance diagonal must
    not. Fusion limits stay at the unconfigured default (zeroed options).
    """
    lat, lon, h, origin = _site()
    east_vel = runtime_east_vel_mps()
    named = UNDER_VEL_CAP_STD
    runtime = runtime_under_vel_cap_sigma_mps()
    gnss_vel = (0.0, east_vel, 0.0)
    follow_s = 6.0
    inflate_s = 2.0
    for vstd, label in (named, "named mid-cap"), ((runtime, runtime, runtime), f"{runtime:.1f} m/s under vel cap"):
        fused = pad_ready(origin)
        fused = append_stream(
            fused,
            duration_s=inflate_s,
            origin=origin,
            gnss_ecef=origin,
            gnss_std=ENTRY_POS_STD,
            gnss_vel=None,
        )
        fused = append_stream(
            fused,
            duration_s=follow_s,
            origin=origin,
            gnss_ecef=origin,
            gnss_std=ENTRY_POS_STD,
            gnss_vel=gnss_vel,
            gnss_vel_std=vstd,
        )
        broken = pad_ready(origin)
        broken = append_stream(
            broken,
            duration_s=inflate_s,
            origin=origin,
            gnss_ecef=origin,
            gnss_std=ENTRY_POS_STD,
            gnss_vel=None,
        )
        broken = append_stream(
            broken,
            duration_s=follow_s,
            origin=origin,
            gnss_ecef=origin,
            gnss_std=ENTRY_POS_STD,
            gnss_vel=gnss_vel,
            gnss_vel_std=vstd,
            vel_broken=True,
        )
        fused_runs = list(gate_langs(_scen(lat, lon, h, fused, origin)))
        broken_runs = list(gate_langs(_scen(lat, lon, h, broken, origin)))
        for (kind, run), (_, br) in zip(fused_runs, broken_runs):
            require_ready_gate(run.at_or_before(int(READY_PAD_S * 1e6)), f"{kind} {label} pad")
            last = run.last()
            require_ready_gate(last, f"{kind} {label} fused velocity")
            require_ready_gate(br.last(), f"{kind} {label} broken still 3D")
            assert last.vel_ned is not None, f"{kind} {label}: fused snapshot has no NED velocity"
            assert br.last().vel_ned is not None, f"{kind} {label}: broken snapshot has no NED velocity"
            ve_f = last.vel_ned[1]
            ve_b = br.last().vel_ned[1]
            print(
                f"{kind} {label} fused east-vel={ve_f} m/s broken={ve_b} m/s "
                f"target={east_vel} m/s sigma={vstd}",
                flush=True,
            )
            assert ve_f * east_vel > 0.0, (
                f"{kind} {label}: fused east velocity {ve_f} did not follow GNSS {east_vel} m/s"
            )
            assert abs(ve_f) > abs(ve_b), (
                f"{kind} {label}: fused east velocity {ve_f} m/s is not past the "
                f"non-positive-covariance twin {ve_b} m/s"
            )


def test_raising_entry_gate_starts_3d_on_10m_stream():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin, duration_s=READY_PAD_S, gnss_std=NAMED_10M_STD)
    raised = _scen(
        lat,
        lon,
        h,
        epochs,
        origin,
        entry_h=RAISED_ENTRY_M,
        entry_v=RAISED_ENTRY_M,
    )
    default = _scen(lat, lon, h, epochs, origin)
    for kind, run in _assert_gate_langs(raised, "raised entry on 10 m"):
        last = run.last()
        print(f"{kind} raised entry pos={last.pos_ok}", flush=True)
        _assert_initialized(last, f"{kind} raised entry on 10 m")
    for kind, run in _assert_gate_langs(default, "default entry on 10 m"):
        last = run.last()
        print(f"{kind} default entry on same 10 m pos={last.pos_ok}", flush=True)
        _assert_not_initialized(last, f"{kind} default entry on 10 m")


def test_improving_stream_to_entry_quality_starts_3d():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin, duration_s=4.2, gnss_std=NAMED_10M_STD)
    mid_t = epochs[-1].t_us
    epochs = append_stream(
        epochs,
        duration_s=ENTRY_DWELL_S + READY_WAIT_S + 0.4,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
    )
    for kind, run in gate_langs(_scen(lat, lon, h, epochs, origin)):
        before = run.at_or_before(mid_t)
        print(f"{kind} before improve pos={before.pos_ok} t={before.t_us}", flush=True)
        require_not_initialized(before, f"{kind} still 10 m")
        first_good = None
        for snap in run.snaps:
            if snap.t_us > mid_t and snap.pos_ok:
                first_good = snap
                break
        assert first_good is not None, f"{kind}: improved stream never started 3D"
        wait_s = (first_good.t_us - mid_t) / 1e6
        print(f"{kind} 3D at +{wait_s} s after improve", flush=True)
        assert wait_s > 4.5, (
            f"{kind}: 3D started {wait_s} s after 1-sigma improved; "
            "must re-earn the 5 s entry dwell"
        )
        require_initialized(run.last(), f"{kind} after improved dwell")


def test_default_5s_entry_dwell_starts_3d():
    lat, lon, h, origin = _site()
    short = pad_ready(origin, duration_s=4.2, gnss_std=ENTRY_POS_STD)
    long = pad_ready(origin, duration_s=ENTRY_DWELL_S + 2.0, gnss_std=ENTRY_POS_STD)
    n_short = sum(1 for e in short if e.gnss_ecef is not None)
    n_long = sum(1 for e in long if e.gnss_ecef is not None)
    print(f"short arm GNSS samples={n_short} long={n_long} (must be >5)", flush=True)
    assert n_short > 5
    assert n_long > n_short
    for kind, run in gate_langs(_scen(lat, lon, h, short, origin)):
        last = run.last()
        print(f"{kind} ~4 s pos={last.pos_ok} ready={last.ready}", flush=True)
        require_not_initialized(last, f"{kind} ~4 s of entry quality")
    for kind, run in gate_langs(_scen(lat, lon, h, long, origin)):
        last = run.last()
        print(f"{kind} >=5 s pos={last.pos_ok} ready={last.ready}", flush=True)
        require_initialized(last, f"{kind} >=5 s entry dwell")


def test_entry_dwell_broken_by_coarse_sample():
    lat, lon, h, origin = _site()
    spike_t = int(2.5e6)

    def gnss_at(t_us, _i):
        if t_us == spike_t:
            return origin, NAMED_10M_STD, ZERO_VEL, ENTRY_VEL_STD
        return origin, ENTRY_POS_STD, ZERO_VEL, ENTRY_VEL_STD

    gapped = append_stream(
        [],
        duration_s=ENTRY_DWELL_S + 0.4,
        origin=origin,
        gnss_ecef=origin,
        gnss_at=gnss_at,
    )
    recovered = append_stream(
        gapped,
        duration_s=ENTRY_DWELL_S + 0.4,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
    )
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, recovered, origin), "dwell broken by coarse sample"
    ):
        at_gap_end = run.at_or_before(gapped[-1].t_us)
        print(f"{kind} after gapped 5 s pos={at_gap_end.pos_ok}", flush=True)
        _assert_not_initialized(at_gap_end, f"{kind} dwell broken by one coarse fix")
        _assert_initialized(run.last(), f"{kind} after a fresh uninterrupted 5 s")


def test_cold_start_between_gates_does_not_start_3d():
    lat, lon, h, origin = _site()
    named = pad_ready(origin, duration_s=READY_PAD_S, gnss_std=BETWEEN_POS_STD)
    runtime = runtime_between_gate_sigma_m()
    runtime_epochs = pad_ready(
        origin, duration_s=READY_PAD_S, gnss_std=(runtime, runtime, runtime)
    )
    good = pad_ready(origin, duration_s=READY_PAD_S, gnss_std=ENTRY_POS_STD)
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, named, origin), "~4 m cold start"
    ):
        _assert_not_initialized(run.last(), f"{kind} ~4 m cold start")
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, runtime_epochs, origin), "runtime between-gate cold start"
    ):
        _assert_not_initialized(run.last(), f"{kind} runtime between-gate cold start")
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, good, origin), "2/2/2 still starts 3D"
    ):
        _assert_initialized(run.last(), f"{kind} 2/2/2 still starts 3D")


def test_velocity_worse_than_entry_does_not_start_3d():
    lat, lon, h, origin = _site()
    bad = append_stream(
        [],
        duration_s=READY_PAD_S,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
        gnss_vel=ZERO_VEL,
        gnss_vel_std=VEL_H_BAD_STD,
    )
    good = pad_ready(origin, duration_s=READY_PAD_S)
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, bad, origin), "horizontal velocity worse than entry"
    ):
        print(f"{kind} horiz vel bad pos={run.last().pos_ok}", flush=True)
        _assert_not_initialized(run.last(), f"{kind} horizontal velocity worse than entry")
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, good, origin), "velocity inside entry"
    ):
        _assert_initialized(run.last(), f"{kind} velocity inside entry")


def test_vertical_velocity_worse_than_entry_does_not_start_3d():
    lat, lon, h, origin = _site()
    bad = append_stream(
        [],
        duration_s=READY_PAD_S,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
        gnss_vel=ZERO_VEL,
        gnss_vel_std=VEL_V_BAD_STD,
    )
    good = pad_ready(origin, duration_s=READY_PAD_S)
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, bad, origin), "vertical velocity worse than entry"
    ):
        print(f"{kind} vert vel bad pos={run.last().pos_ok}", flush=True)
        _assert_not_initialized(run.last(), f"{kind} vertical velocity worse than entry")
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, good, origin), "vertical velocity inside entry"
    ):
        _assert_initialized(run.last(), f"{kind} vertical velocity inside entry")


# ---------------------------------------------------------------------------
# B. Exit gate
# ---------------------------------------------------------------------------


def test_exit_quality_for_10s_rearms_accessors_fail():
    lat, lon, h, origin = _site()
    runtime = runtime_coarse_sigma_m()
    if runtime < 6.0:
        runtime = 8.4
    for std, label in ((NAMED_10M_STD, "10 m"), ((runtime, runtime, runtime), "runtime worse than exit")):
        epochs = pad_ready(origin)
        t_ready = epochs[-1].t_us
        mid = append_stream(
            epochs,
            duration_s=7.0,
            origin=origin,
            gnss_ecef=origin,
            gnss_std=std,
        )
        full = append_stream(
            mid,
            duration_s=4.5,
            origin=origin,
            gnss_ecef=origin,
            gnss_std=std,
        )
        for kind, run in gate_langs(_scen(lat, lon, h, full, origin)):
            require_ready_gate(run.at_or_before(t_ready), f"{kind} {label} before exit")
            mid_snap = run.at_or_before(mid[-1].t_us)
            print(
                f"{kind} {label} at 7 s of bad ready={mid_snap.ready} pos={mid_snap.pos_ok}",
                flush=True,
            )
            require_initialized(mid_snap, f"{kind} {label} still 3D before 10 s")
            last = run.last()
            print(f"{kind} {label} after 10 s ready={last.ready} pos={last.pos_ok}", flush=True)
            assert not last.ready, f"{kind}: {label} still ready after 10 s of exit quality"
            require_not_initialized(last, f"{kind} {label} quality-loss re-arm")


def test_exit_rearm_carries_inflated_bias_uncertainty():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin, duration_s=READY_PAD_S, acc=coast_acc(), gyr=yaw_gyr())
    t_ready = epochs[-1].t_us
    bad = append_stream(
        epochs,
        duration_s=11.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=NAMED_10M_STD,
        acc=coast_acc(),
        gyr=yaw_gyr(),
    )
    t_rearm = bad[-1].t_us
    back = append_stream(
        bad,
        duration_s=ENTRY_DWELL_S + READY_WAIT_S + 0.4,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
        acc=SPECIFIC_FORCE_LEVEL,
        gyr=(0.0, 0.0, 0.0),
    )
    for kind, run in gate_langs(_scen(lat, lon, h, back, origin)):
        ready = run.at_or_before(t_ready)
        rearm = run.at_or_before(t_rearm)
        last = run.last()
        require_ready_gate(ready, f"{kind} before quality-loss")
        require_not_initialized(rearm, f"{kind} quality-loss re-arm")
        first_back = None
        for snap in run.snaps:
            if snap.t_us > t_rearm and snap.pos_ok:
                first_back = snap
                break
        assert first_back is not None, f"{kind}: no re-bootstrap snapshot after quality-loss"
        require_initialized(first_back, f"{kind} re-bootstrap after quality-loss")
        require_initialized(last, f"{kind} still 3D after re-bootstrap")
        assert ready.bias_acc is not None and first_back.bias_acc is not None
        assert ready.bias_gyr is not None and first_back.bias_gyr is not None
        d_acc = hypot3(first_back.bias_acc, ready.bias_acc)
        d_gyr = hypot3(first_back.bias_gyr, ready.bias_gyr)
        print(
            f"{kind} bias carry dacc={d_acc} dgyr={d_gyr} "
            f"pre accstd={ready.bias_acc_std} post={first_back.bias_acc_std} "
            f"pre gyrstd={ready.bias_gyr_std} post={first_back.bias_gyr_std}",
            flush=True,
        )
        assert d_acc < 0.35, f"{kind}: accelerometer bias was not carried into re-bootstrap ({d_acc})"
        assert d_gyr < 0.15, f"{kind}: gyro bias was not carried into re-bootstrap ({d_gyr})"
        if kind == "c":
            # Bias 1-sigma is published by the Python wrapper's stddev();
            # the C INS has no public bias 1-sigma accessor.
            continue
        assert ready.bias_acc_std is not None and first_back.bias_acc_std is not None
        assert ready.bias_gyr_std is not None and first_back.bias_gyr_std is not None
        pre_a = hypot3(ready.bias_acc_std, (0.0, 0.0, 0.0))
        post_a = hypot3(first_back.bias_acc_std, (0.0, 0.0, 0.0))
        pre_g = hypot3(ready.bias_gyr_std, (0.0, 0.0, 0.0))
        post_g = hypot3(first_back.bias_gyr_std, (0.0, 0.0, 0.0))
        assert post_a > pre_a or post_g > pre_g, (
            f"{kind}: IMU-bias uncertainty was not inflated on quality-loss re-bootstrap "
            f"(acc {pre_a}->{post_a}, gyr {pre_g}->{post_g})"
        )


def test_exit_velocity_for_10s_rearms():
    lat, lon, h, origin = _site()
    bad = pad_ready(origin)
    bad = append_stream(
        bad,
        duration_s=11.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
        gnss_vel=ZERO_VEL,
        gnss_vel_std=EXIT_VEL_BAD_STD,
    )
    good = pad_ready(origin)
    good = append_stream(
        good,
        duration_s=11.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
        gnss_vel=ZERO_VEL,
        gnss_vel_std=ENTRY_VEL_STD,
    )
    for kind, run in gate_langs(_scen(lat, lon, h, bad, origin)):
        last = run.last()
        print(f"{kind} exit vel ready={last.ready} pos={last.pos_ok}", flush=True)
        assert not last.ready
        require_not_initialized(last, f"{kind} exit-quality velocity")
    for kind, run in gate_langs(_scen(lat, lon, h, good, origin)):
        last = run.last()
        print(f"{kind} stay vel ready={last.ready} pos={last.pos_ok}", flush=True)
        require_ready_gate(last, f"{kind} velocity still inside exit")


def test_between_entry_and_exit_stays_in_3d():
    lat, lon, h, origin = _site()
    runtime = runtime_between_gate_sigma_m()
    epochs = pad_ready(origin)
    epochs = append_stream(
        epochs,
        duration_s=11.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=(runtime, runtime, runtime),
    )
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, epochs, origin), "between entry and exit"
    ):
        last = run.last()
        print(f"{kind} between-gate 10 s ready={last.ready} pos={last.pos_ok}", flush=True)
        _assert_ready_gate(last, f"{kind} between entry and exit")


def test_quality_loss_return_needs_entry_dwell():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin)
    epochs = append_stream(
        epochs,
        duration_s=11.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=NAMED_10M_STD,
    )
    t_rearm = epochs[-1].t_us
    short = append_stream(
        epochs,
        duration_s=3.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
    )
    ten_m = append_stream(
        short,
        duration_s=ENTRY_DWELL_S + 0.3,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=NAMED_10M_STD,
    )
    back = append_stream(
        ten_m,
        duration_s=ENTRY_DWELL_S + 0.4,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
    )
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, back, origin), "quality-loss return needs entry dwell"
    ):
        _assert_not_initialized(run.at_or_before(t_rearm), f"{kind} after quality loss")
        _assert_not_initialized(run.at_or_before(short[-1].t_us), f"{kind} short entry return")
        _assert_not_initialized(run.at_or_before(ten_m[-1].t_us), f"{kind} 10 m for 5 s still not 3D")
        _assert_initialized(run.last(), f"{kind} full entry-quality re-bootstrap")


# ---------------------------------------------------------------------------
# C. Switches and prescribed init
# ---------------------------------------------------------------------------


def test_entry_dwell_disable_starts_3d_on_first_good_fix():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin, duration_s=0.8, gnss_std=ENTRY_POS_STD)
    off = _scen(lat, lon, h, epochs, origin, dwell_disable=True)
    on = _scen(lat, lon, h, epochs, origin, dwell_disable=False)
    for kind, run in _assert_gate_langs(off, "dwell disabled"):
        last = run.last()
        print(f"{kind} dwell off pos={last.pos_ok} ready={last.ready}", flush=True)
        _assert_initialized(last, f"{kind} dwell disabled")
    for kind, run in _assert_gate_langs(on, "dwell still on"):
        last = run.last()
        print(f"{kind} dwell on short pos={last.pos_ok}", flush=True)
        _assert_not_initialized(last, f"{kind} dwell still on")


def test_prescribed_init_not_held_at_entry_dwell():
    lat, lon, h, origin = _site()
    rpy = (0.28, -0.16, 0.95)
    epochs = pad_ready(origin, duration_s=2.2, gnss_std=ENTRY_POS_STD)
    prescribed = _scen(
        lat, lon, h, epochs, origin, auto_init=False, rpy_init=rpy, dwell_disable=False
    )
    auto = _scen(lat, lon, h, epochs, origin, auto_init=True)
    for kind, run in gate_langs(prescribed):
        first = run.first_initialized()
        assert first is not None, f"{kind}: prescribed init never published a position"
        wait_s = first.t_us / 1e6
        print(
            f"{kind} prescribed first 3D at {wait_s} s pos={first.pos_ok} att={first.rpy}",
            flush=True,
        )
        assert wait_s < 4.5, f"{kind}: prescribed init waited {wait_s} s (entry dwell)"
        require_initialized(first, f"{kind} prescribed init")
        require_initialized(run.last(), f"{kind} prescribed still 3D before 5 s")
        assert first.rpy is not None
        roll, pitch, yaw = first.rpy
        print(
            f"{kind} prescribed rpy=({roll},{pitch},{yaw}) vs {rpy}",
            flush=True,
        )
        assert abs(angle_diff_rad(roll, rpy[0])) < 0.12, f"{kind}: roll not the prescribed value"
        assert abs(angle_diff_rad(pitch, rpy[1])) < 0.12, f"{kind}: pitch not the prescribed value"
        assert abs(roll) > 0.08 and abs(pitch) > 0.08, f"{kind}: attitude looks accelerometer-leveled"
        assert dist_m(first.ecef, origin) < 8.0, f"{kind}: prescribed ECEF left the asserted origin"
    for kind, run in gate_langs(auto):
        require_not_initialized(run.last(), f"{kind} auto-init still held at the dwell")


def test_exit_disable_never_leaves_3d_on_quality():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin)
    epochs = append_stream(
        epochs,
        duration_s=11.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=NAMED_10M_STD,
    )
    disabled = _scen(lat, lon, h, epochs, origin, stop_disable=True)
    armed = _scen(lat, lon, h, epochs, origin, stop_disable=False)
    for kind, run in _assert_gate_langs(disabled, "exit disabled"):
        last = run.last()
        print(f"{kind} exit off ready={last.ready} pos={last.pos_ok}", flush=True)
        _assert_ready_gate(last, f"{kind} exit disabled")
    for kind, run in _assert_gate_langs(armed, "default exit re-arm"):
        last = run.last()
        print(f"{kind} exit on ready={last.ready} pos={last.pos_ok}", flush=True)
        _assert_not_initialized(last, f"{kind} default exit re-arm")


def test_ready_only_switch_clears_ready_without_rearm():
    lat, lon, h, origin = _site()
    north = runtime_north_offset_m()
    offset = north_of(origin, north)
    epochs = pad_ready(origin)
    epochs = append_stream(
        epochs,
        duration_s=11.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=NAMED_10M_STD,
    )
    t_clear = epochs[-1].t_us
    moved = append_stream(
        epochs,
        duration_s=4.0,
        origin=origin,
        gnss_ecef=offset,
        gnss_std=NAMED_10M_STD,
        gnss_vel=None,
    )
    # Twin: the same bytes up to the exit, then IMU only (no further fixes).
    silent = append_stream(
        epochs,
        duration_s=4.0,
        origin=origin,
        gnss_ecef=None,
    )
    hold = _scen(lat, lon, h, moved, origin, ready_only=True)
    hold_silent = _scen(lat, lon, h, silent, origin, ready_only=True)
    rearm = _scen(lat, lon, h, moved, origin, ready_only=False)
    for kind, run, twin in (("c", c_gate_run(hold), c_gate_run(hold_silent)),):
        cleared = run.at_or_before(t_clear)
        print(
            f"{kind} ready-only after exit ready={cleared.ready} pos={cleared.pos_ok}",
            flush=True,
        )
        assert not cleared.ready, f"{kind}: ready-only switch left ready true"
        require_initialized(cleared, f"{kind} ready-only still initialized")
        last = run.last()
        require_initialized(last, f"{kind} ready-only still running")
        twin_last = twin.last()
        require_initialized(twin_last, f"{kind} ready-only IMU-only twin")
        # the filter keeps running. How far 10 m fixes pull it in 4 s
        # depends on unstated process noise, so observe the running filter
        # directly: it keeps spending fixes, and it moved toward the offset
        # beyond the IMU-only twin of the same bytes.
        got = north_pull_m(origin, last.ecef)
        twin_got = north_pull_m(origin, twin_last.ecef)
        print(
            f"{kind} ready-only used {cleared.n_used}->{last.n_used}; "
            f"north={got} m IMU-only twin north={twin_got} m target={north} m",
            flush=True,
        )
        assert last.n_used > cleared.n_used, (
            f"{kind}: ready-only filter stopped fusing after the exit "
            f"(used {cleared.n_used}->{last.n_used})"
        )
        assert (got - twin_got) * north > 0.0 and abs(got - twin_got) > 0.01 * abs(north), (
            f"{kind}: ready-only filter did not move toward the {north} m offset beyond "
            f"its IMU-only twin (north {got} vs twin {twin_got} m)"
        )
    for kind, run in gate_langs(rearm):
        last = run.last()
        require_not_initialized(last, f"{kind} default re-arm")
    freeze_cut = pad_ready(origin)
    frozen_at = coast_imu(freeze_cut, duration_s=FREEZE_11S)
    t_fr = frozen_at[-1].t_us
    more = coast_imu(frozen_at, duration_s=2.0)
    for kind, run in gate_langs(_scen(lat, lon, h, more, origin)):
        fr = run.at_or_before(t_fr)
        last = run.last()
        require_initialized(fr, f"{kind} freeze snapshot")
        assert not fr.ready
        dn = dist_m(last.ecef, fr.ecef)
        print(f"{kind} freeze extra IMU moved {dn} m", flush=True)
        assert dn < 0.35, f"{kind}: freeze kept integrating ({dn} m)"


# ---------------------------------------------------------------------------
# D. Coasting window
# ---------------------------------------------------------------------------


def test_3s_outage_inside_window_ready_age_about_3000ms():
    lat, lon, h, origin = _site()
    runtime_s = runtime_in_window_outage_s()
    epochs = pad_ready(origin)
    t_cut = epochs[-1].t_us
    named = coast_imu(epochs, duration_s=OUTAGE_3S)
    runtime = coast_imu(list(epochs), duration_s=runtime_s)
    for kind, run in gate_langs(_scen(lat, lon, h, named, origin)):
        cut = run.at_or_before(t_cut)
        last = run.last()
        require_ready_gate(cut, f"{kind} before 3 s outage")
        require_ready_gate(last, f"{kind} 3 s outage")
        assert last.dr_ms is not None
        print(f"{kind} 3 s age={last.dr_ms} ms", flush=True)
        assert 1500 < last.dr_ms < 8000, f"{kind}: age {last.dr_ms} ms is not about 3000 ms"
        assert last.dr_ms < 10000
        dn = dist_m(last.ecef, cut.ecef)
        print(f"{kind} 3 s walk {dn} m", flush=True)
        assert dn > 0.15, f"{kind}: in-window IMU did not integrate ({dn} m)"
    for kind, run in gate_langs(_scen(lat, lon, h, runtime, origin)):
        last = run.last()
        require_ready_gate(last, f"{kind} runtime in-window outage")
        assert last.dr_ms is not None
        print(f"{kind} runtime {runtime_s} s age={last.dr_ms} ms", flush=True)
        assert abs(last.dr_ms / 1000.0 - runtime_s) < 1.2


def test_in_window_outage_past_5s_still_ready():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin)
    t_cut = epochs[-1].t_us
    epochs = coast_imu(epochs, duration_s=OUTAGE_7S)
    for kind, run in gate_langs(_scen(lat, lon, h, epochs, origin)):
        cut = run.at_or_before(t_cut)
        last = run.last()
        print(f"{kind} 7 s IMU-only ready={last.ready} pos={last.pos_ok} dr={last.dr_ms}", flush=True)
        require_ready_gate(last, f"{kind} 5–10 s still inside the window")
        assert last.dr_ms is not None and last.dr_ms < 10000
        assert dist_m(last.ecef, cut.ecef) > 0.4, f"{kind}: 7 s IMU-only did not integrate"


def test_11s_imu_only_freezes_and_stops_integrating():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin, gyr=yaw_gyr())
    t_cut = epochs[-1].t_us
    frozen = coast_imu(epochs, duration_s=FREEZE_11S, acc=coast_acc(), gyr=yaw_gyr())
    t_fr = frozen[-1].t_us
    more = coast_imu(frozen, duration_s=2.5, acc=coast_acc(), gyr=yaw_gyr())
    extra_s = (more[-1].t_us - t_fr) / 1e6
    for kind, run in gate_langs(_scen(lat, lon, h, more, origin)):
        cut = run.at_or_before(t_cut)
        fr = run.at_or_before(t_fr)
        last = run.last()
        print(
            f"{kind} freeze ready={fr.ready} pos={fr.pos_ok} extra {dist_m(last.ecef, fr.ecef)} m",
            flush=True,
        )
        assert not fr.ready, f"{kind}: 11 s IMU-only left ready true"
        require_initialized(fr, f"{kind} freeze still publishes")
        require_initialized(last, f"{kind} freeze accessors")
        assert not last.ready
        dn = dist_m(last.ecef, fr.ecef)
        assert fr.rpy is not None and last.rpy is not None
        droll = abs(angle_diff_rad(last.rpy[0], fr.rpy[0]))
        dpitch = abs(angle_diff_rad(last.rpy[1], fr.rpy[1]))
        dyaw = abs(angle_diff_rad(last.rpy[2], fr.rpy[2]))
        print(f"{kind} freeze hold dn={dn} m datt=({droll},{dpitch},{dyaw}) rad", flush=True)
        assert dn < 0.35, f"{kind}: frozen ECEF still integrated ({dn} m)"
        assert droll < 0.08 and dpitch < 0.08 and dyaw < 0.08, (
            f"{kind}: frozen attitude still integrated ({droll},{dpitch},{dyaw})"
        )
        assert fr.rpy_std is not None and last.rpy_std is not None
        d_att_std = hypot3(last.rpy_std, fr.rpy_std)
        # Position, velocity, and bias 1-sigma: Python stddev() publishes
        # them; the C INS publishes attitude 1-sigma only.
        d_pos_std = None
        if kind == "py":
            assert fr.pos_std is not None and last.pos_std is not None
            d_pos_std = hypot3(last.pos_std, fr.pos_std)
        print(
            f"{kind} freeze cov dattstd={d_att_std} dposstd={d_pos_std} "
            f"fr attstd={fr.rpy_std} last={last.rpy_std}",
            flush=True,
        )
        assert d_att_std < 1e-4, f"{kind}: frozen attitude covariance still walked ({d_att_std})"
        if d_pos_std is not None:
            assert d_pos_std < 1e-4, f"{kind}: frozen position covariance still walked ({d_pos_std})"
        if kind == "py":
            assert fr.vel_std is not None and last.vel_std is not None
            d_vel_std = hypot3(last.vel_std, fr.vel_std)
            print(f"{kind} freeze cov dvelstd={d_vel_std}", flush=True)
            assert d_vel_std < 1e-4, f"{kind}: frozen velocity covariance still walked ({d_vel_std})"
        assert fr.bias_acc is not None and last.bias_acc is not None
        assert fr.bias_gyr is not None and last.bias_gyr is not None
        db_acc = hypot3(last.bias_acc, fr.bias_acc)
        db_gyr = hypot3(last.bias_gyr, fr.bias_gyr)
        print(f"{kind} freeze bias dacc={db_acc} dgyr={db_gyr}", flush=True)
        assert db_acc < 0.05, f"{kind}: frozen accel bias still walked ({db_acc})"
        assert db_gyr < 0.05, f"{kind}: frozen gyro bias still walked ({db_gyr})"
        if kind == "py":
            assert fr.bias_acc_std is not None and last.bias_acc_std is not None
            assert fr.bias_gyr_std is not None and last.bias_gyr_std is not None
            d_bacc_std = hypot3(last.bias_acc_std, fr.bias_acc_std)
            d_bgyr_std = hypot3(last.bias_gyr_std, fr.bias_gyr_std)
            print(f"{kind} freeze bias-std dacc={d_bacc_std} dgyr={d_bgyr_std}", flush=True)
            assert d_bacc_std < 1e-4, f"{kind}: frozen accel-bias covariance still walked ({d_bacc_std})"
            assert d_bgyr_std < 1e-4, f"{kind}: frozen gyro-bias covariance still walked ({d_bgyr_std})"
        assert cut.vel_ned is not None, f"{kind}: pad-end snapshot has no published NED velocity"
        assert fr.vel_ned is not None, f"{kind}: freeze snapshot has no published NED velocity"
        assert last.vel_ned is not None, f"{kind}: extra-IMU snapshot has no published NED velocity"
        dv_coast = hypot3(fr.vel_ned, cut.vel_ned)
        dv_hold = hypot3(last.vel_ned, fr.vel_ned)
        would_keep = dv_coast * (extra_s / FREEZE_11S)
        print(
            f"{kind} freeze vel hold dcoast={dv_coast} dhold={dv_hold} "
            f"would_keep={would_keep} extra_s={extra_s} "
            f"cut={cut.vel_ned} fr={fr.vel_ned} last={last.vel_ned}",
            flush=True,
        )
        assert dv_hold < would_keep, (
            f"{kind}: frozen NED velocity still walked under further IMU "
            f"(hold {dv_hold} vs in-window-rate continuation {would_keep})"
        )


def test_local_position_resets_deadreckoning_age():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin)
    outage = coast_imu(epochs, duration_s=2.5)
    t_old = outage[-1].t_us
    with_local = append_stream(
        outage,
        duration_s=0.6,
        origin=origin,
        gnss_ecef=None,
        local_ned=TRACKER_NAMED_NED,
        local_std=(0.01, 0.01, 0.01),
        local_hz=10,
    )
    twin = coast_imu(list(outage), duration_s=0.6)
    for kind, run in gate_langs(_scen(lat, lon, h, with_local, origin)):
        aged = run.at_or_before(t_old)
        last = run.last()
        print(f"{kind} age before local={aged.dr_ms} after={last.dr_ms}", flush=True)
        assert aged.dr_ms is not None and aged.dr_ms > 1500
        assert last.dr_ms is not None
        assert last.dr_ms < aged.dr_ms * 0.35, (
            f"{kind}: local position did not reset dead-reckoning age "
            f"{aged.dr_ms} -> {last.dr_ms}"
        )
    for kind, run in gate_langs(_scen(lat, lon, h, twin, origin)):
        last = run.last()
        print(f"{kind} IMU-only twin age={last.dr_ms}", flush=True)
        assert last.dr_ms is not None and last.dr_ms > 2000


def test_in_window_restore_keeps_ready():
    lat, lon, h, origin = _site()
    yaw0 = 0.4
    epochs = pad_ready(origin, yaw_rad=yaw0)
    t_cut = epochs[-1].t_us
    outage = coast_imu(epochs, duration_s=OUTAGE_3S, acc=SPECIFIC_FORCE_LEVEL, gyr=(0.0, 0.0, 0.0))
    t_outage = outage[-1].t_us
    restored = append_stream(
        outage,
        duration_s=1.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
    )
    for kind, run in gate_langs(_scen(lat, lon, h, restored, origin)):
        cut = run.at_or_before(t_cut)
        aged = run.at_or_before(t_outage)
        last = run.last()
        require_ready_gate(cut, f"{kind} before in-window outage")
        require_ready_gate(aged, f"{kind} 3 s IMU-only still inside the window")
        require_ready_gate(last, f"{kind} in-window restore")
        assert cut.dr_ms is not None, f"{kind}: aided baseline has no dead-reckoning age"
        assert aged.dr_ms is not None, f"{kind}: outage-end snapshot has no dead-reckoning age"
        assert last.dr_ms is not None, f"{kind}: restore snapshot has no dead-reckoning age"
        print(
            f"{kind} in-window restore ready={last.ready} pos={last.pos_ok} "
            f"age baseline={cut.dr_ms} outage_end={aged.dr_ms} after_restore={last.dr_ms}",
            flush=True,
        )
        assert aged.dr_ms > cut.dr_ms, (
            f"{kind}: dead-reckoning age did not grow during the 3 s outage "
            f"({cut.dr_ms} -> {aged.dr_ms})"
        )
        assert 1500 < aged.dr_ms < 8000, (
            f"{kind}: outage-end age {aged.dr_ms} ms is not about 3000 ms"
        )
        assert aged.dr_ms < 10000, (
            f"{kind}: outage-end age {aged.dr_ms} ms reached the 10 s window"
        )
        assert last.dr_ms < aged.dr_ms, (
            f"{kind}: restored GNSS did not refresh dead-reckoning age "
            f"({aged.dr_ms} -> {last.dr_ms})"
        )


# ---------------------------------------------------------------------------
# E. Unlimited dead reckoning
# ---------------------------------------------------------------------------


def test_unlimited_dead_reckoning_keeps_ready_through_11s():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin)
    t_cut = epochs[-1].t_us
    epochs = coast_imu(epochs, duration_s=FREEZE_11S)
    unlimited = _scen(lat, lon, h, epochs, origin, unlimited=True)
    limited = _scen(lat, lon, h, epochs, origin, unlimited=False)
    for kind, run in gate_langs(unlimited):
        cut = run.at_or_before(t_cut)
        last = run.last()
        print(f"{kind} unlimited 11 s ready={last.ready} walk={dist_m(last.ecef, cut.ecef)}", flush=True)
        require_ready_gate(last, f"{kind} unlimited 11 s")
        assert dist_m(last.ecef, cut.ecef) > 0.8, f"{kind}: unlimited 11 s did not keep integrating"
    for kind, run in gate_langs(limited):
        last = run.last()
        assert not last.ready
        require_initialized(last, f"{kind} default freeze contrast")


def test_unlimited_next_fix_is_ordinary_fusion():
    lat, lon, h, origin = _site()
    north = runtime_north_offset_m()
    offset = north_of(origin, north)
    yaw0 = 0.35
    base = pad_ready(origin, yaw_rad=yaw0)
    t_aid = base[-1].t_us
    gapped = coast_imu(base, duration_s=FREEZE_11S, acc=(0.0, 0.0, -9.81), gyr=(0.0, 0.0, 0.0))
    t_gap = gapped[-1].t_us
    nxt = append_stream(
        gapped,
        duration_s=2.5,
        origin=origin,
        gnss_ecef=offset,
        gnss_std=NAMED_10M_STD,
        acc=(0.0, 0.0, -9.81),
        gyr=(0.0, 0.0, 0.0),
    )
    skipped = append_stream(
        gapped,
        duration_s=2.5,
        origin=origin,
        gnss_ecef=None,
        acc=(0.0, 0.0, -9.81),
        gyr=(0.0, 0.0, 0.0),
    )
    unlimited = _scen(lat, lon, h, nxt, origin, unlimited=True)
    limited = _scen(lat, lon, h, nxt, origin, unlimited=False)
    skip_scen = _scen(lat, lon, h, skipped, origin, unlimited=True)
    freeze_pull = []
    live_pull = []
    skip_pull = []
    freeze_yaw = []
    live_yaw = []
    for kind, run in gate_langs(unlimited):
        require_ready_gate(run.at_or_before(t_gap), f"{kind} unlimited still ready")
        last = run.last()
        require_ready_gate(last, f"{kind} unlimited next fix")
        live_pull.append(dist_m(last.ecef, offset))
        aided = run.at_or_before(t_aid)
        assert aided.rpy_std is not None and last.rpy_std is not None
        live_yaw.append((aided.rpy_std[2], last.rpy_std[2]))
        print(
            f"{kind} unlimited |ecef-offset|={live_pull[-1]} yawstd {live_yaw[-1]}",
            flush=True,
        )
    for kind, run in gate_langs(limited):
        last = run.last()
        require_ready_gate(last, f"{kind} freeze reanchor")
        freeze_pull.append(dist_m(last.ecef, offset))
        aided = run.at_or_before(t_aid)
        assert aided.rpy_std is not None and last.rpy_std is not None
        freeze_yaw.append((aided.rpy_std[2], last.rpy_std[2]))
        print(
            f"{kind} freeze |ecef-offset|={freeze_pull[-1]} yawstd {freeze_yaw[-1]}",
            flush=True,
        )
    for kind, run in gate_langs(skip_scen):
        last = run.last()
        require_ready_gate(last, f"{kind} skip twin still ready")
        skip_pull.append(dist_m(last.ecef, offset))
        print(f"{kind} skip |ecef-offset|={skip_pull[-1]}", flush=True)
    assert live_pull and freeze_pull and skip_pull
    for live, frozen, skipped_d in zip(live_pull, freeze_pull, skip_pull):
        print(
            f"ordinary-fusion split live={live} skip={skipped_d} freeze={frozen}",
            flush=True,
        )
        assert live < skipped_d, (
            f"unlimited next fix did not move toward the offset relative to skipping "
            f"those bytes (live {live} m vs skip {skipped_d} m from the offset)"
        )
        assert live > frozen, (
            f"unlimited next fix snapped like a freeze re-anchor "
            f"(live {live} m vs freeze {frozen} m from the offset)"
        )
    for (a0, a1), (f0, f1) in zip(live_yaw, freeze_yaw):
        print(f"yaw std live {a0}->{a1} freeze {f0}->{f1}", flush=True)
        assert a1 < f1, (
            f"unlimited next fix reset yaw uncertainty like freeze ({a1} vs {f1})"
        )
        assert a0 > 0.0 and f0 > 0.0, "pre-gap yaw 1-sigma was not published"
        assert a1 / a0 < f1 / f0, (
            f"unlimited yaw 1-sigma left the pre-gap scale the way freeze jumps "
            f"to unknown (live {a0}->{a1}, freeze {f0}->{f1})"
        )


def test_unlimited_large_forward_gap_skips_then_continues():
    lat, lon, h, origin = _site()
    epochs = pad_ready(origin)
    t_before = epochs[-1].t_us
    dt_jump = 4.0
    epochs = list(epochs)
    epochs.append(
        _gate_epoch(
            t_before + int(dt_jump * 1e6),
            dt_sec=dt_jump,
            acc=coast_acc(),
            gyr=(0.0, 0.0, 0.0),
        )
    )
    t_jump = epochs[-1].t_us
    epochs = coast_imu(epochs, duration_s=2.0)
    scen = _scen(lat, lon, h, epochs, origin, unlimited=True)
    would_move = 0.5 * NORTH_ACCEL * dt_jump * dt_jump
    for kind, run in gate_langs(scen):
        before = run.at_or_before(t_before)
        at_jump = run.at_or_before(t_jump)
        last = run.last()
        jump_dn = dist_m(at_jump.ecef, before.ecef)
        after_dn = dist_m(last.ecef, at_jump.ecef)
        print(
            f"{kind} jump moved {jump_dn} m (strapdown would be ~{would_move} m); "
            f"later walk {after_dn} m",
            flush=True,
        )
        require_ready_gate(last, f"{kind} after large gap")
        assert jump_dn < would_move * 0.35, (
            f"{kind}: large dt was integrated ({jump_dn} m vs ~{would_move} m)"
        )
        assert after_dn > 0.15, f"{kind}: instance stayed stuck after the skipped jump"


# ---------------------------------------------------------------------------
# F. Freeze re-acquisition
# ---------------------------------------------------------------------------


def test_first_fusion_usable_fix_after_freeze_reanchors_ready_same_epoch():
    lat, lon, h, origin = _site()
    north = runtime_north_offset_m()
    offset = north_of(origin, north)
    runtime = runtime_under_cap_sigma_m()
    if runtime > 80.0:
        runtime = 45.0
    epochs = pad_ready(origin)
    frozen = coast_imu(epochs, duration_s=FREEZE_11S)
    t_fr = frozen[-1].t_us
    t_bad = t_fr + 250000
    t_good = t_fr + 500000
    seq = list(frozen)
    seq.append(
        _gate_epoch(
            t_bad,
            dt_sec=0.01,
            gnss_ecef=offset,
            gnss_std=UNFUSABLE_POS_STD,
        )
    )
    seq.append(
        _gate_epoch(
            t_good,
            dt_sec=0.01,
            gnss_ecef=offset,
            gnss_std=NAMED_10M_STD,
        )
    )
    alt = list(frozen)
    alt.append(
        _gate_epoch(
            t_bad,
            dt_sec=0.01,
            gnss_ecef=offset,
            gnss_std=UNFUSABLE_POS_STD,
        )
    )
    alt.append(
        _gate_epoch(
            t_good,
            dt_sec=0.01,
            gnss_ecef=offset,
            gnss_std=(runtime, runtime, runtime),
        )
    )
    for kind, run in gate_langs(_scen(lat, lon, h, seq, origin)):
        fr = run.at_or_before(t_fr)
        bad_snap = run.at_or_before(t_bad)
        last = run.at_or_after(t_good)
        print(
            f"{kind} freeze ready={fr.ready} after bad={bad_snap.ready} "
            f"after good={last.ready} pos={last.pos_ok}",
            flush=True,
        )
        assert not fr.ready
        require_initialized(fr, f"{kind} freeze")
        assert not bad_snap.ready, f"{kind}: unfusable sample re-anchored"
        require_initialized(bad_snap, f"{kind} freeze still published after unfusable")
        stay = dist_m(bad_snap.ecef, fr.ecef)
        print(f"{kind} unfusable moved {stay} m from freeze", flush=True)
        assert stay < 0.35, f"{kind}: unfusable sample moved the frozen ECEF by {stay} m"
        require_ready_gate(last, f"{kind} first usable fix after freeze")
        wait_s = (last.t_us - t_bad) / 1e6
        assert wait_s < 2.0, f"{kind}: re-anchor waited {wait_s} s (must not re-earn 5 s)"
        _assert_follows_north(origin, last.ecef, north, f"{kind} freeze re-anchor", min_frac=0.08)
    for kind, run in gate_langs(_scen(lat, lon, h, alt, origin)):
        last = run.last()
        require_ready_gate(last, f"{kind} runtime fusable sigma after freeze")


def test_freeze_reaquire_keeps_attitude_and_biases():
    lat, lon, h, origin = _site()
    turned = pad_ready(origin, duration_s=READY_PAD_S, gyr=yaw_gyr())
    frozen = coast_imu(turned, duration_s=FREEZE_11S, acc=(0.0, 0.0, -9.81), gyr=yaw_gyr())
    t_fr = frozen[-1].t_us
    reacq = append_stream(
        frozen,
        duration_s=0.5,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=NAMED_10M_STD,
        acc=(0.0, 0.0, -9.81),
        gyr=(0.0, 0.0, 0.0),
    )
    for kind, run in gate_langs(_scen(lat, lon, h, reacq, origin)):
        fr = run.at_or_before(t_fr)
        last = run.last()
        print(
            f"{kind} freeze ready={fr.ready} pos={fr.pos_ok} "
            f"reanchor ready={last.ready} pos={last.pos_ok}",
            flush=True,
        )
        assert not fr.ready, (
            f"{kind}: freeze snapshot still ready — instance never froze, so "
            f"keep-across-freeze is unobserved"
        )
        require_initialized(fr, f"{kind} freeze still publishes")
        require_ready_gate(last, f"{kind} re-anchor")
        assert fr.rpy is not None and last.rpy is not None
        dyaw = abs(angle_diff_rad(last.rpy[2], fr.rpy[2]))
        droll = abs(angle_diff_rad(last.rpy[0], fr.rpy[0]))
        dpitch = abs(angle_diff_rad(last.rpy[1], fr.rpy[1]))
        print(
            f"{kind} freeze att={fr.rpy} reanchor att={last.rpy} "
            f"droll={droll} dpitch={dpitch} dyaw={dyaw}",
            flush=True,
        )
        assert abs(fr.rpy[2]) > 0.15, f"{kind}: freeze yaw was still near zero"
        assert dyaw < 0.12, f"{kind}: re-anchor re-levelled yaw ({dyaw} rad)"
        assert droll < 0.12 and dpitch < 0.12
        assert fr.bias_gyr is not None and last.bias_gyr is not None
        db = hypot3(last.bias_gyr, fr.bias_gyr)
        bz = abs(fr.bias_gyr[2])
        print(f"{kind} freeze bgyr={fr.bias_gyr} after={last.bias_gyr} db={db}", flush=True)
        assert db < 0.08, f"{kind}: gyro bias was cleared on re-anchor"
        assert hypot3(last.bias_gyr, (0.0, 0.0, 0.0)) > min(0.01, bz * 0.3) or bz < 0.005


def test_freeze_reaquire_resets_yaw_uncertainty_without_heading_hint():
    lat, lon, h, origin = _site()
    yaw0 = 0.45
    epochs = pad_ready(origin, yaw_rad=yaw0)
    t_aid = epochs[-1].t_us
    frozen = coast_imu(epochs, duration_s=FREEZE_11S, acc=(0.0, 0.0, -9.81))
    reacq = append_stream(
        frozen,
        duration_s=0.5,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=NAMED_10M_STD,
    )
    for kind, run in gate_langs(_scen(lat, lon, h, reacq, origin)):
        aided = run.at_or_before(t_aid)
        last = run.last()
        require_ready_gate(last, f"{kind} re-anchor")
        assert aided.rpy_std is not None and last.rpy_std is not None
        y0, y1 = aided.rpy_std[2], last.rpy_std[2]
        print(f"{kind} yaw std {y0} -> {y1}", flush=True)
        assert y1 > y0 * 3.0, f"{kind}: yaw uncertainty did not return toward unknown ({y0} -> {y1})"


# ---------------------------------------------------------------------------
# G. Rate limit and decimation
# ---------------------------------------------------------------------------


def test_50hz_gnss_not_fused_every_sample_default_rate_limit():
    lat, lon, h, origin = _site()
    north = runtime_north_offset_m()
    offset = north_of(origin, north)
    pad = pad_ready(origin)
    t0 = pad[-1].t_us
    few = append_stream(
        list(pad),
        duration_s=1.2,
        origin=origin,
        gnss_ecef=offset,
        gnss_std=ENTRY_POS_STD,
        gnss_hz=FEW_HZ,
    )

    def spike_at(t_us, _i):
        slot = (t_us - t0) % 100000
        if slot < 25000:
            return origin, ENTRY_POS_STD, ZERO_VEL, ENTRY_VEL_STD
        return offset, ENTRY_POS_STD, ZERO_VEL, ENTRY_VEL_STD

    fast = append_stream(
        list(pad),
        duration_s=1.2,
        origin=origin,
        gnss_ecef=offset,
        gnss_hz=GNSS_50HZ,
        gnss_at=spike_at,
    )
    few_skip = {}
    for kind, run in gate_langs(_scen(lat, lon, h, few, origin)):
        last = run.last()
        require_ready_gate(last, f"{kind} few-Hz baseline")
        _assert_follows_north(origin, last.ecef, north, f"{kind} few-Hz every-sample")
        start = run.at_or_before(t0)
        offered, fused, skip = _counted_skip(start, last, f"{kind} few-Hz")
        print(
            f"{kind} few-Hz offered={offered} fused={fused} skip={skip}",
            flush=True,
        )
        few_skip[kind] = skip
    assert few_skip, "few-Hz baseline: expected C/Python observations, got none"
    for kind, run in gate_langs(_scen(lat, lon, h, fast, origin)):
        last = run.last()
        require_ready_gate(last, f"{kind} 50 Hz")
        _assert_not_at_offset(origin, last.ecef, north, f"{kind} 50 Hz skipped slots")
        start = run.at_or_before(t0)
        offered, fused, skip = _counted_skip(start, last, f"{kind} 50 Hz")
        print(
            f"{kind} 50 Hz offered={offered} fused={fused} skip={skip} "
            f"few-Hz skip={few_skip[kind]}",
            flush=True,
        )
        assert fused < offered, (
            f"{kind}: 50 Hz fused every offered sample "
            f"(offered {offered} fused {fused})"
        )
        assert skip > few_skip[kind], (
            f"{kind}: skip count did not increase on the 50 Hz arm "
            f"relative to few-Hz (50 Hz {skip} few-Hz {few_skip[kind]})"
        )


def test_rate_limit_suspended_when_coasting_window_expired():
    lat, lon, h, origin = _site()
    north = runtime_north_offset_m()
    offset = north_of(origin, north)
    east_vel = runtime_east_vel_mps()
    epochs = pad_ready(origin)
    frozen = coast_imu(epochs, duration_s=FREEZE_11S)
    t_fr = frozen[-1].t_us
    t1 = t_fr + 20000
    t2 = t_fr + 40000
    seq = list(frozen)
    seq.append(
        _gate_epoch(
            t1,
            dt_sec=0.02,
            gnss_vel=(0.0, east_vel, 0.0),
            gnss_vel_std=ENTRY_VEL_STD,
        )
    )
    seq.append(
        _gate_epoch(
            t2,
            dt_sec=0.02,
            gnss_ecef=offset,
            gnss_std=NAMED_10M_STD,
        )
    )
    for kind, run in gate_langs(_scen(lat, lon, h, seq, origin)):
        fr = run.at_or_before(t_fr)
        after_first = run.at_or_before(t1)
        last = run.at_or_after(t2)
        ve0 = 0.0 if fr.vel_ned is None else fr.vel_ned[1]
        ve1 = 0.0 if after_first.vel_ned is None else after_first.vel_ned[1]
        print(
            f"{kind} freeze ready={fr.ready} used={fr.n_used} ve={ve0}; "
            f"after first usable ready={after_first.ready} used={after_first.n_used} ve={ve1}; "
            f"after second ready={last.ready} used={last.n_used}",
            flush=True,
        )
        assert not fr.ready
        require_initialized(after_first, f"{kind} freeze still published after first usable")
        assert not after_first.ready, f"{kind}: velocity-only usable sample re-anchored"
        assert after_first.n_used > fr.n_used, (
            f"{kind}: first fusion-usable sample inside the expired window was not fused "
            f"(used {fr.n_used}->{after_first.n_used}; a skip would leave the limiter slot free)"
        )
        assert abs(ve1 - ve0) > abs(east_vel) * 0.04, (
            f"{kind}: first fusion-usable velocity did not change the state "
            f"(ve {ve0}->{ve1})"
        )
        require_ready_gate(last, f"{kind} second fusable inside 100 ms")
        assert last.n_used > after_first.n_used, (
            f"{kind}: second fusion-usable sample inside 100 ms was not fused "
            f"(used {after_first.n_used}->{last.n_used}; still-on limiter would skip it)"
        )
        _assert_follows_north(
            origin, last.ecef, north, f"{kind} second usable after freeze", min_frac=0.05
        )


def test_omitted_position_decimation_fuses_position_every_combined_epoch():
    """omitting the position-decimation knob (default off) spends
    every combined position-and-velocity epoch as a position fuse.

    The GNSS position steps north on each combined epoch so a later
    epoch still has a visible pull — a constant offset would converge
    after the first two fuses and hide a cheat that only position-fuses
    those two. An explicit N=1 is not this path.
    """
    lat, lon, h, origin = _site()
    step = runtime_north_offset_m()
    pad = pad_ready(origin)
    t0 = pad[-1].t_us
    combined = append_combined_north_steps(
        list(pad),
        origin=origin,
        step_m=step,
        duration_s=2.0,
        gnss_vel=ZERO_VEL,
    )
    gnss_times = [e.t_us for e in combined if e.gnss_ecef is not None and e.t_us > t0]
    assert len(gnss_times) >= 4, (
        f"omitted-knob stream must offer more than two combined epochs; got {len(gnss_times)}"
    )
    for e in combined:
        if e.t_us <= t0 or e.gnss_ecef is None:
            continue
        assert e.gnss_vel is not None, "combined epoch must offer GNSS velocity as well as position"

    # Do not pass pos_decimation: that is the omitted-knob path.
    for kind, run in gate_langs(_scen(lat, lon, h, combined, origin)):
        incs = north_increments(origin, run, gnss_times, t0)
        print(
            f"{kind} omitted-knob combined epochs={len(incs)} increments={incs}",
            flush=True,
        )
        require_ready_gate(run.last(), f"{kind} omitted decimation")
        quiet = abs(step) * 0.04
        missed = [
            (k, inc)
            for k, inc in enumerate(incs, start=1)
            if not (inc * step > quiet)
        ]
        assert not missed, (
            f"{kind}: omitting position-decimation did not spend every combined "
            f"position-and-velocity epoch as a position fuse; quiet-or-wrong "
            f"epochs={missed}; increments={incs}"
        )


def test_position_decimation_fuses_velocity_only_on_non_nth():
    lat, lon, h, origin = _site()
    north = runtime_north_offset_m()
    offset = north_of(origin, north)
    east_vel = runtime_east_vel_mps()
    gnss_vel = (0.0, east_vel, 0.0)
    pad = pad_ready(origin)
    t0 = pad[-1].t_us
    jumped = append_stream(
        list(pad),
        duration_s=1.0,
        origin=origin,
        gnss_ecef=offset,
        gnss_std=ENTRY_POS_STD,
        gnss_vel=gnss_vel,
        gnss_vel_std=ENTRY_VEL_STD,
        gnss_hz=FEW_HZ,
    )
    # The velocity step is many sigma from the ready filter's velocity, so
    # outlier downweighting (on by default, strength unspecified) would decide
    # how visible a velocity-only fuse is. It is not under test here and is
    # turned off through the public switch in every arm.
    off = _scen(lat, lon, h, jumped, origin, pos_decimation=0, chi2_disable=True)
    n2 = _scen(lat, lon, h, jumped, origin, pos_decimation=2, chi2_disable=True)
    n3 = _scen(lat, lon, h, jumped, origin, pos_decimation=3, chi2_disable=True)
    gnss_times = [e.t_us for e in jumped if e.gnss_ecef is not None and e.t_us > t0]
    assert len(gnss_times) >= 3

    for kind, run in gate_langs(off):
        incs = north_increments(origin, run, gnss_times[:2], t0)
        print(f"{kind} decim off increments={incs}", flush=True)
        require_ready_gate(run.last(), f"{kind} decim off")
        assert all(inc * north > 0.0 for inc in incs), (
            f"{kind}: default decimation skipped a position fuse; increments={incs}"
        )
    for kind, run in gate_langs(n2):
        incs = north_increments(origin, run, gnss_times[:2], t0)
        print(f"{kind} N=2 increments={incs}", flush=True)
        require_ready_gate(run.last(), f"{kind} N=2")
        toward = [inc * north > abs(north) * 0.04 for inc in incs]
        quiet = [abs(inc) < abs(north) * 0.04 for inc in incs]
        assert any(toward) and any(quiet), (
            f"{kind} N=2: expected one of two combined epochs to spend "
            f"position and one velocity-only; increments={incs}"
        )
        vel_only = False
        prev_ve = 0.0 if run.at_or_before(t0).vel_ned is None else run.at_or_before(t0).vel_ned[1]
        for t, inc in zip(gnss_times[:2], incs):
            snap = run.at_or_after(t)
            assert snap.vel_ned is not None
            quiet_pos = abs(inc) < abs(north) * 0.04
            ve = snap.vel_ned[1]
            dve = ve - prev_ve
            print(f"{kind} N=2 t={t} inc={inc} ve={ve} dve={dve}", flush=True)
            if quiet_pos and abs(dve) > 0.08:
                vel_only = True
            prev_ve = ve
        assert vel_only, (
            f"{kind} N=2: non-Nth combined epoch had no velocity-only effect "
            f"(a skip would also leave north quiet); increments={incs}"
        )
    for kind, run in gate_langs(n3):
        incs = north_increments(origin, run, gnss_times[:3], t0)
        print(f"{kind} N=3 increments={incs}", flush=True)
        require_ready_gate(run.last(), f"{kind} N=3")
        toward = [inc * north > abs(north) * 0.04 for inc in incs]
        quiet = [abs(inc) < abs(north) * 0.04 for inc in incs]
        assert any(toward) and any(quiet), (
            f"{kind} N=3: expected mixed position/velocity-only fuses; increments={incs}"
        )
        vel_only = False
        prev_ve = 0.0 if run.at_or_before(t0).vel_ned is None else run.at_or_before(t0).vel_ned[1]
        for t, inc in zip(gnss_times[:3], incs):
            snap = run.at_or_after(t)
            assert snap.vel_ned is not None
            quiet_pos = abs(inc) < abs(north) * 0.04
            ve = snap.vel_ned[1]
            dve = ve - prev_ve
            print(f"{kind} N=3 t={t} inc={inc} ve={ve} dve={dve}", flush=True)
            if quiet_pos and abs(dve) > 0.08:
                vel_only = True
            prev_ve = ve
        assert vel_only, (
            f"{kind} N=3: non-Nth combined epoch had no velocity-only effect; increments={incs}"
        )


# ---------------------------------------------------------------------------
# H. Barometric height source vs GNSS vertical rows
# ---------------------------------------------------------------------------


def test_entry_gate_still_grades_gnss_vertical_at_bootstrap():
    lat, lon, h, origin = _site()
    pa = isa_pressure_pa(h)
    bad_v = append_stream(
        [],
        duration_s=READY_PAD_S,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=(2.0, 2.0, 10.0),
        baro_pa=pa,
    )
    good_v = append_stream(
        [],
        duration_s=READY_PAD_S,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
        baro_pa=pa,
    )
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, bad_v, origin), "entry still grades GNSS vertical"
    ):
        print(f"{kind} baro + 10 m vertical pos={run.last().pos_ok}", flush=True)
        _assert_not_initialized(run.last(), f"{kind} entry still grades GNSS vertical")
    for kind, run in _assert_gate_langs(
        _scen(lat, lon, h, good_v, origin), "baro + entry-quality vertical"
    ):
        _assert_initialized(run.last(), f"{kind} baro + entry-quality vertical")


def test_baro_height_ignores_gnss_vertical_on_exit():
    lat, lon, h, origin = _site()
    pa = isa_pressure_pa(h)
    epochs = append_stream(
        [],
        duration_s=READY_PAD_S,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
        baro_pa=pa,
    )
    epochs = append_stream(
        epochs,
        duration_s=11.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=(2.0, 2.0, 10.0),
        baro_pa=pa,
    )
    baro = _scen(lat, lon, h, epochs, origin, baro_height_disable=False)
    gnss_h = _scen(lat, lon, h, epochs, origin, baro_height_disable=True)
    for kind, run in _assert_gate_langs(baro, "baro ignores GNSS vertical on exit"):
        last = run.last()
        print(f"{kind} baro height source ready={last.ready} pos={last.pos_ok}", flush=True)
        _assert_ready_gate(last, f"{kind} baro ignores GNSS vertical on exit")
    for kind, run in _assert_gate_langs(gnss_h, "GNSS height still exits on vertical"):
        last = run.last()
        print(f"{kind} GNSS height source ready={last.ready} pos={last.pos_ok}", flush=True)
        _assert_not_initialized(last, f"{kind} GNSS height still exits on vertical")


def test_baro_height_ignores_gnss_vertical_on_fusion_gate():
    lat, lon, h, origin = _site()
    pa = isa_pressure_pa(h)
    north = runtime_north_offset_m()
    offset = north_of(origin, north)
    pad = append_stream(
        [],
        duration_s=READY_PAD_S,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=ENTRY_POS_STD,
        baro_pa=pa,
    )
    jumped = append_stream(
        pad,
        duration_s=2.5,
        origin=origin,
        gnss_ecef=offset,
        gnss_std=(2.0, 2.0, 10.0),
        baro_pa=pa,
    )
    baro = _scen(
        lat,
        lon,
        h,
        jumped,
        origin,
        fusion_v=5.0,
        fusion_h=20.0,
        baro_height_disable=False,
    )
    gnss_h = _scen(
        lat,
        lon,
        h,
        jumped,
        origin,
        fusion_v=5.0,
        fusion_h=20.0,
        baro_height_disable=True,
    )
    baro_pairs = list(_assert_gate_langs(baro, "baro fusion"))
    gnss_pairs = list(_assert_gate_langs(gnss_h, "GNSS-height fusion twin"))
    assert len(baro_pairs) == len(gnss_pairs), (
        "baro and GNSS-height arms must yield the same language observations"
    )
    for (kind, run), (_, gnss_run) in zip(baro_pairs, gnss_pairs):
        last = run.last()
        require_ready_gate(last, f"{kind} baro fusion")
        _assert_follows_north(origin, last.ecef, north, f"{kind} baro still fuses horizontal")
        gnss_last = gnss_run.last()
        require_initialized(gnss_last, f"{kind} GNSS-height fusion twin")
        baro_n = north_pull_m(origin, last.ecef)
        gnss_n = north_pull_m(origin, gnss_last.ecef)
        print(
            f"{kind} fusion-gate north baro={baro_n} m gnss-height={gnss_n} m "
            f"offset={north} m",
            flush=True,
        )
        _assert_not_at_offset(
            origin, gnss_last.ecef, north, f"{kind} GNSS height vertical over-limit"
        )
        assert abs(gnss_n) < abs(baro_n), (
            f"{kind}: GNSS-height north pull {gnss_n} m was not strictly smaller "
            f"than baro-height {baro_n} m; an over-limit vertical row was not graded"
        )


def test_deadreckoning_age_published_exactly_while_initialized():
    """PRD / Contract ``ins_deadreckoning_ms``: while INS is not initialized
    (collecting before its bootstrap, or re-armed after a GNSS quality loss)
    no age is published and both the C getter and the Python ``Ins`` reader
    return -1. While it is initialized -- ready, coasting, or frozen after the
    window expired -- they return an age of 0 ms or more. Checked on runs of
    its own and on every gate snapshot parsed in this session; a violation
    fails this test only.
    """
    from _harness import require_no_product_issues

    lat, lon, h, origin = _site()
    pad = pad_ready(origin)
    frozen = coast_imu(pad, duration_s=FREEZE_11S)
    rearmed = append_stream(
        pad,
        duration_s=15.0,
        origin=origin,
        gnss_ecef=origin,
        gnss_std=NAMED_10M_STD,
    )
    for label, epochs in (("coast into freeze", frozen), ("quality-loss re-arm", rearmed)):
        for kind, run in gate_langs(_scen(lat, lon, h, epochs, origin)):
            init = [s for s in run.snaps if s.pos_ok]
            uninit = [s for s in run.snaps if not s.pos_ok]
            print(
                f"{kind} {label}: initialized={len(init)} uninitialized={len(uninit)} "
                f"first/last raw age={run.snaps[0].dr_raw}/{run.snaps[-1].dr_raw}",
                flush=True,
            )
            assert init and uninit, f"{kind} {label}: run must cover both states"
            bad_u = [(s.t_us, s.dr_raw) for s in uninit if s.dr_raw != -1]
            bad_i = [(s.t_us, s.dr_raw) for s in init if s.dr_ms is None]
            assert not bad_u, (
                f"{kind} {label}: not initialized, but the age reader did not return -1 "
                f"(t_us, value): {bad_u[:4]}"
            )
            assert not bad_i, (
                f"{kind} {label}: initialized, but no age of 0 ms or more (t_us, value): {bad_i[:4]}"
            )
        if label == "quality-loss re-arm":
            assert not run.last().pos_ok, f"{kind}: re-arm scenario did not end uninitialized"
    require_no_product_issues("F05.dr", "dead-reckoning age on F05 gate snapshots")


def test_published_gate_snapshots_are_well_formed():
    """While INS is initialized its position, velocity, and bias 1-sigma are
    published (Python: ``stddev``; the C INS publishes attitude 1-sigma), every
    published value is finite, ``ins_get_diag`` / ``diag`` are available, the
    GNSS counters are non-negative and used never exceeds seen. Checked on a
    coast of its own and on every gate snapshot parsed in this session; a
    violation fails this test only.
    """
    from _harness import require_no_product_issues

    lat, lon, h, origin = _site()
    epochs = coast_imu(pad_ready(origin), duration_s=3.0)
    for kind, run in gate_langs(_scen(lat, lon, h, epochs, origin)):
        assert any(s.pos_ok for s in run.snaps), f"{kind}: pad never initialized"
    require_no_product_issues("F05", "F05 gate snapshots")
