# feature: F07
"""Standalone barometric vertical channel (FP-07).

Assertions stay at the PRD's precision: a static pad holds near-anchor
datum height and near-zero climb; tropospheric ISA maps 101325 Pa to
zero and a few hundred metres within one metre; a pressure drop raises
ISA and datum-relative height in the same direction; between barometer
samples, height and climb follow specific force after gravity is
removed, using the supplied attitude; the barometer observes height only
and is not a direct climb-rate measurement; a slow additive acceleration
correction is absorbed so an IMU-only stretch after a baro pad does not
run away; local height plus the offset tracks ellipsoid height and
still converts during a GNSS gap; pairs without a positive GNSS
vertical variance are skipped; implausible barometer innovations are
downweighted, not dropped, and an all-zero config fills a 2 m default
altitude 1-sigma; vertical ZUPT is a direct zero climb-rate measurement
not gated on the filter's own velocity; non-finite pressure or IMU is
dropped and processing continues; init fails on a non-finite or negative
(ISA-undefined) anchor and succeeds on sea-level-standard and ordinary
tropospheric positive pressure; a backwards timestamp skips that epoch; a forward gap just
under 0.5 s still integrates IMU height, a named 0.3 s gap is not an
outage, and a gap just over 0.5 s skips IMU integration while still
fusing a barometer sample; after a published solution whose height or
climb-rate 1-sigma stays implausibly large, those accessors fail, the
suite re-bootstraps without a caller re-init, and a standalone instance
stays unpublished until the caller re-inits.

Message text, exception types, internal state-index spellings, the
product's rounded ISA scale/exponent, a numeric 1-sigma restart
threshold, and suite mode names are not pinned.
"""

from __future__ import annotations

import math

from F01_helpers import hamilton_zyx_quaternion
from F02_helpers import DT_SEC, SPECIFIC_FORCE_LEVEL
from F03_helpers import G_MPS2, still_level_acc
from F07_helpers import (
    BARO_1SIGMA_DEFAULT_M,
    GAP_BACKWARDS_S,
    GAP_JUST_OVER_S,
    GAP_JUST_UNDER_S,
    GAP_NAMED_NOT_OUTAGE_S,
    ISA_FEW_HUNDRED_TOL_M,
    ISA_P0_PA,
    ChanSuiteScenario,
    OffCmd,
    OffScenario,
    VertCmd,
    VertScenario,
    c_chan_suite_run,
    c_offset_run,
    c_vert_run,
    chan_suite_stream,
    kinematics_climb_mps,
    kinematics_height_m,
    level_quat,
    require_published_vert,
    require_unpublished_vert,
    runtime_a_up_alt_mps2,
    runtime_a_up_mps2,
    runtime_acc_bias_mps2,
    runtime_climb_m,
    runtime_h_init_m,
    runtime_isa_band_heights,
    runtime_local_height_m,
    runtime_offset_pair,
    runtime_pad_isa_m,
    runtime_spike_isa_m,
    runtime_suite_site,
    runtime_tight_baro_std_m,
    runtime_vert_tilt_rad,
    runtime_weather_isa_m,
    tropospheric_isa_altitude_m,
    tropospheric_isa_pressure_pa,
    up_specific_force,
    vert_stream,
)

_US = 1_000_000


def _last_cmd_t(cmds) -> int:
    if not cmds:
        return 0
    return cmds[-1].t_us


# ---------------------------------------------------------------------------
# A. Pad near zero; climb same-sign
# ---------------------------------------------------------------------------


def test_static_pad_holds_near_anchor_height_and_zero_climb():
    """realistic pad pressure plus a level IMU holds near-anchor height and near-zero climb."""
    pad_h = runtime_pad_isa_m()
    climb = runtime_climb_m()
    p_pad = tropospheric_isa_pressure_pa(pad_h)
    p_up = tropospheric_isa_pressure_pa(pad_h + climb)
    pad = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            cmds=vert_stream(duration_s=4.0, pressure_pa=p_pad),
        )
    )
    up = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            cmds=(
                vert_stream(duration_s=1.5, pressure_pa=p_pad)
                + vert_stream(
                    duration_s=3.0,
                    t0_us=int(1.5 * _US),
                    pressure_pa=p_up,
                )
            ),
        )
    )
    assert pad.init_ok and up.init_ok, "pad/climb init was refused"
    require_published_vert(pad.last(), "pad")
    require_published_vert(up.last(), "climb")
    print(
        f"pad h={pad.last().h} v={pad.last().v} climb_h={up.last().h} "
        f"climb={climb}",
        flush=True,
    )
    assert abs(up.last().h) > 2.0 * max(abs(pad.last().h), 0.05), (
        "pad height was not distinguishable from a several-metre climb"
    )
    assert abs(pad.last().h) < 0.45 * abs(up.last().h), (
        "pad height did not stay near the zero anchor relative to the climb"
    )
    assert abs(pad.last().v) < 0.6, "pad climb rate was not near zero"


def test_pressure_drop_raises_isa_and_datum_height_same_sign():
    """a pressure drop raises ISA and datum height; a pressure rise lowers both."""
    pad_h = runtime_pad_isa_m()
    climb_a = runtime_climb_m()
    climb_b = runtime_climb_m() + 2.5
    p_pad = tropospheric_isa_pressure_pa(pad_h)
    p_up = tropospheric_isa_pressure_pa(pad_h + climb_a)
    p_down = tropospheric_isa_pressure_pa(max(pad_h - climb_b, 30.0))

    def _run(p_hold: float) -> tuple[float, float, float, float]:
        pad = vert_stream(duration_s=2.0, pressure_pa=p_pad)
        hold = vert_stream(
            duration_s=6.0, t0_us=_last_cmd_t(pad), pressure_pa=p_hold
        )
        run = c_vert_run(
            VertScenario(t_init=0, pressure_pa=p_pad, cmds=pad + hold)
        )
        assert run.init_ok, "climb init was refused"
        require_published_vert(run.last(), "pressure step")
        at_pad = [s for s in run.snaps if s.t_us <= _last_cmd_t(pad) and s.h_ok]
        assert at_pad, "pad produced no published snapshot"
        return at_pad[-1].h, run.last().h, run.last().isa, run.last().v

    h0_up, h1_up, isa_up, v_up = _run(p_up)
    h0_dn, h1_dn, isa_dn, v_dn = _run(p_down)
    isa0 = tropospheric_isa_altitude_m(p_pad)
    print(
        f"drop dh={h1_up - h0_up} d_isa={isa_up - isa0} "
        f"rise dh={h1_dn - h0_dn} v_after={v_up}",
        flush=True,
    )
    assert (h1_up - h0_up) > 1.0, "pressure drop did not raise datum height"
    assert (isa_up - isa0) > 1.0, "pressure drop did not raise ISA altitude"
    assert (h1_up - h0_up) * (isa_up - isa0) > 0.0, (
        "datum height and ISA altitude disagreed in sign on a climb"
    )
    assert (h1_dn - h0_dn) < -1.0, "pressure rise did not lower datum height"
    assert (isa_dn - isa0) < -1.0, "pressure rise did not lower ISA altitude"


# ---------------------------------------------------------------------------
# B. Tropospheric ISA
# ---------------------------------------------------------------------------


def test_sea_level_standard_pressure_maps_to_zero_isa():
    """101325 Pa maps to zero ISA altitude."""
    run = c_vert_run(
        VertScenario(t_init=0, pressure_pa=ISA_P0_PA, cmds=[])
    )
    assert run.init_ok, "sea-level init was refused"
    require_published_vert(run.last(), "sea-level ISA")
    print(f"101325 Pa ISA={run.last().isa} h={run.last().h}", flush=True)
    assert abs(run.last().isa) < 0.5, "101325 Pa did not map to near-zero ISA altitude"
    assert abs(run.last().h) < 0.5, "h_init=0 did not start the datum near zero"


def test_tropospheric_isa_few_hundred_metres_within_one_metre():
    """two distinct few-hundred-metre pressures each yield that altitude within 1 m."""
    h_a, h_b = runtime_isa_band_heights()
    for h_true in (h_a, h_b):
        p = tropospheric_isa_pressure_pa(h_true)
        run = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=[]))
        assert run.init_ok, f"ISA init refused at {h_true} m"
        require_published_vert(run.last(), f"ISA {h_true}")
        err = abs(run.last().isa - h_true)
        print(f"ISA h_true={h_true} published={run.last().isa} err={err}", flush=True)
        assert err <= ISA_FEW_HUNDRED_TOL_M, (
            f"ISA altitude {run.last().isa} was not within 1 m of {h_true}"
        )
    assert abs(h_a - h_b) > 30.0, "the two ISA sites were not distinct"


def test_isa_altitude_readable_separately_from_datum_height():
    """ISA altitude is readable separately; init height is the datum."""
    pad_h = runtime_pad_isa_m()
    h_init = runtime_h_init_m()
    climb = runtime_climb_m()
    p_pad = tropospheric_isa_pressure_pa(pad_h)
    p_up = tropospheric_isa_pressure_pa(pad_h + climb)
    pad = vert_stream(duration_s=2.0, pressure_pa=p_pad)
    hold = vert_stream(duration_s=3.0, t0_us=_last_cmd_t(pad), pressure_pa=p_up)
    run = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            h_init=h_init,
            cmds=pad + hold,
        )
    )
    assert run.init_ok, "datum-aligned init was refused"
    require_published_vert(run.snaps[0], "init")
    require_published_vert(run.last(), "after climb")
    isa_anchor = tropospheric_isa_altitude_m(p_pad)
    print(
        f"init h={run.snaps[0].h} isa={run.snaps[0].isa} h_init={h_init} "
        f"isa_anchor={isa_anchor} after isa-h={run.last().isa - run.last().h}",
        flush=True,
    )
    assert abs(run.snaps[0].h - h_init) < 0.8, "datum-relative height did not start at h_init"
    assert abs(run.snaps[0].isa - isa_anchor) < ISA_FEW_HUNDRED_TOL_M, (
        "ISA altitude at init did not match the anchor pressure"
    )
    assert abs(run.snaps[0].isa - run.snaps[0].h) > 8.0, (
        "ISA altitude was not readable separately from datum-relative height"
    )
    split = run.last().isa - run.last().h
    expect_split = isa_anchor - h_init
    assert abs(split - expect_split) < 1.5, (
        "ISA minus local height did not keep the init datum split after a climb"
    )


# ---------------------------------------------------------------------------
# C. IMU between baro samples; attitude; slow accel correction
# ---------------------------------------------------------------------------


def test_imu_between_baro_samples_follows_specific_force_minus_gravity():
    """with no further barometer, height and climb follow gravity-removed specific force."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    dt = 0.40
    a1 = runtime_a_up_mps2()
    a2 = runtime_a_up_alt_mps2()

    def _arm(a_up: float):
        acc = up_specific_force(a_up) if abs(a_up) > 1e-9 else SPECIFIC_FORCE_LEVEL
        run = c_vert_run(
            VertScenario(
                t_init=0,
                pressure_pa=p,
                cmds=vert_stream(
                    duration_s=dt,
                    acc=acc,
                    pressure_pa=p,
                    baro_valid=False,
                ),
            )
        )
        assert run.init_ok, "IMU-only init was refused"
        require_published_vert(run.last(), "IMU-only")
        return run.last()

    pad = _arm(0.0)
    acc1 = _arm(a1)
    acc2 = _arm(a2)
    dh1 = acc1.h - pad.h
    dv1 = acc1.v - pad.v
    expect_h = kinematics_height_m(a1, dt)
    expect_v = kinematics_climb_mps(a1, dt)
    print(
        f"pad h={pad.h} acc h={acc1.h} dh={dh1} expect={expect_h} "
        f"dv={dv1} expect_v={expect_v}",
        flush=True,
    )
    assert dh1 * expect_h > 0.0, "height change disagreed in sign with 0.5·a·t²"
    assert abs(dh1) > 5.0 * max(abs(pad.h), 0.02), (
        "accelerating arm was not distinguishable from the level pad"
    )
    assert abs(dh1) > 0.35 * abs(expect_h), "height change was far below independent kinematics"
    assert dv1 * expect_v > 0.0, "climb-rate change disagreed in sign with a·t"
    dh2 = acc2.h - pad.h
    assert abs(dh2) > abs(dh1), "a larger up-acceleration did not raise height more"


def test_supplied_attitude_rotates_specific_force():
    """the supplied body-to-NED attitude is used to rotate specific force."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    # 12–24° leaves body acc[2] close to −g, so taking specific force as
    # already NED still looks like a still pad. A large floor makes
    # gravity-removal fail unless the supplied body-to-NED rotation is used.
    tilt = math.radians(45.0) + runtime_vert_tilt_rad()
    # still_level_acc(roll) is body specific force for that Tait-Bryan roll;
    # baro_alt rotates with R_b_to_n, so the matching Hamilton roll is negated.
    q = hamilton_zyx_quaternion(-tilt, 0.0, 0.0)
    acc_still = still_level_acc(0.0, tilt)
    still = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p,
            cmds=vert_stream(
                duration_s=2.5,
                acc=acc_still,
                quat=q,
                pressure_pa=p,
                baro_valid=False,
            ),
        )
    )
    wrong = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p,
            cmds=vert_stream(
                duration_s=2.5,
                acc=SPECIFIC_FORCE_LEVEL,
                quat=q,
                pressure_pa=p,
                baro_valid=False,
            ),
        )
    )
    assert still.init_ok and wrong.init_ok, "attitude-rotation init was refused"
    require_published_vert(still.last(), "tilted still")
    require_published_vert(wrong.last(), "unrotated specific force")
    print(
        f"tilt_deg={math.degrees(tilt)} "
        f"tilted-still h={still.last().h} v={still.last().v} "
        f"unrotated h={wrong.last().h} v={wrong.last().v}",
        flush=True,
    )
    assert abs(still.last().h) < 1.5, "tilted still pad did not hold near the anchor"
    assert abs(still.last().v) < 1.0, "tilted still pad climb rate was not near zero"
    assert abs(wrong.last().h) > 1.5 or abs(wrong.last().v) > 1.0, (
        "unrotated specific force still looked like a still pad"
    )
    assert abs(wrong.last().h - still.last().h) > 0.8 or abs(
        wrong.last().v - still.last().v
    ) > 0.4, "unrotated specific force was not distinguishable from the rotated still pad"


def test_slow_accel_correction_holds_pad_under_accel_bias():
    """a slow additive correction is absorbed; IMU-only after a baro pad does not run away."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    bias = runtime_acc_bias_mps2()
    acc = up_specific_force(bias)
    pad_s = 10.0
    imu_s = 5.0
    # The precision-restart watchdog is not the subject here (it is scored
    # in the section I tests). The never-baro twin integrates the biased
    # accelerometer from init for 15 s; whether its height/climb 1-sigma
    # stays under the 20 m / 10 m/s defaults depends on default noise and
    # accel-bias tuning the contract leaves to the implementer, so both
    # arms switch the watchdog off through the public config field.
    learned = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p,
            cmds=(
                vert_stream(duration_s=pad_s, acc=acc, pressure_pa=p, baro_valid=True)
                + vert_stream(
                    duration_s=imu_s,
                    t0_us=int(pad_s * _US),
                    acc=acc,
                    pressure_pa=p,
                    baro_valid=False,
                )
            ),
            restart_disable=True,
        )
    )
    never = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p,
            cmds=vert_stream(
                duration_s=pad_s + imu_s,
                acc=acc,
                pressure_pa=p,
                baro_valid=False,
            ),
            restart_disable=True,
        )
    )
    assert learned.init_ok and never.init_ok, "bias-correction init was refused"
    t_pad = int(pad_s * _US)
    at_pad = [s for s in learned.snaps if s.t_us <= t_pad and s.h_ok]
    after = [s for s in learned.snaps if s.t_us > t_pad and s.h_ok]
    assert at_pad and after, "learned arm missing pad or IMU-only snapshots"
    require_published_vert(at_pad[-1], "baro pad under bias")
    require_published_vert(after[-1], "IMU-only after pad")
    require_published_vert(never.last(), "never-baro twin")
    print(
        f"pad h={at_pad[-1].h} v={at_pad[-1].v} after-IMU v={after[-1].v} "
        f"never v={never.last().v} bias={bias}",
        flush=True,
    )
    assert abs(at_pad[-1].h) < 1.5, "baro pad under accel bias did not hold near the anchor"
    assert abs(at_pad[-1].v) < 0.7, "baro pad under accel bias did not hold climb near zero"
    assert abs(after[-1].v - at_pad[-1].v) < 0.55, (
        "IMU-only stretch after a baro pad ran away — correction was not absorbed"
    )
    assert abs(never.last().v) > 2.0 * max(abs(after[-1].v), 0.20), (
        "never-baro twin did not accumulate climb under the same accel bias"
    )


def test_barometer_observes_height_only_not_climb_rate():
    """the barometer observes height only; it is not a direct climb-rate measurement."""
    pad_h = runtime_pad_isa_m()
    climb = runtime_climb_m()
    p_pad = tropospheric_isa_pressure_pa(pad_h)
    p_up = tropospheric_isa_pressure_pa(pad_h + climb)
    pad = vert_stream(duration_s=2.0, pressure_pa=p_pad)
    t_pad = _last_cmd_t(pad)
    hold = vert_stream(duration_s=6.0, t0_us=t_pad, pressure_pa=p_up)
    baro = c_vert_run(
        VertScenario(t_init=0, pressure_pa=p_pad, cmds=pad + hold)
    )
    # ZUPT is the PRD's direct zero climb-rate measurement. Same
    # still IMU and duration, pad pressure held, no new barometer altitude.
    zupt = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            cmds=vert_stream(
                duration_s=8.0, pressure_pa=p_pad, baro_valid=False, zupt=True
            ),
            # 8 s without a barometer reaches the watchdog warm-up; the
            # watchdog is not this contrast.
            restart_disable=True,
        )
    )
    assert baro.init_ok and zupt.init_ok, "height-only contrast init was refused"
    at_pad = [s for s in baro.snaps if s.t_us <= t_pad and s.h_ok]
    assert at_pad, "baro arm produced no pad snapshot"
    require_published_vert(at_pad[-1], "baro pad")
    require_published_vert(baro.last(), "baro hold")
    require_published_vert(zupt.last(), "ZUPT twin")
    dh_baro = baro.last().h - at_pad[-1].h
    print(
        f"baro dh={dh_baro} v={baro.last().v} "
        f"zupt h={zupt.last().h} v={zupt.last().v} climb={climb}",
        flush=True,
    )
    assert dh_baro > 1.0, (
        "held new pressure did not raise datum height — baro did not observe height"
    )
    # How fast the climb rate settles after a several-metre pressure step is
    # tuning the PRD leaves open (large innovations are downweighted), so it
    # is not asserted here; the height-only contrast is the ZUPT twin below.
    assert abs(zupt.last().v) < 0.25, (
        "ZUPT twin did not hold climb near zero — live climb-rate baseline missing"
    )
    assert abs(zupt.last().h) < 1.5, (
        "ZUPT twin relocated height as if it had observed a new barometric altitude"
    )
    assert dh_baro > abs(zupt.last().h) + 1.0, (
        "baro hold and ZUPT were not distinguishable: a climb-rate-only fusion "
        "would zero climb without moving the datum to the new pressure"
    )


# ---------------------------------------------------------------------------
# D. Local-to-ellipsoid offset
# ---------------------------------------------------------------------------


def _offset_pairs(h_local, local_std, offset, gnss_std, *, t0_us, count, dt_us):
    cmds = []
    t = t0_us
    for _ in range(count):
        t += dt_us
        cmds.append(
            OffCmd(
                tag="E",
                t_us=t,
                h_local=h_local,
                local_std=local_std,
                h_ell=h_local + offset,
                gnss_std=gnss_std,
            )
        )
    return cmds


# Consistent pairs fed after the true offset changes. How fast the offset
# tracks is the implementer's, so the stream is about an hour of
# 11 s pairs: long enough that any tracking filter has crossed the midpoint
# between the old and the new offset, whatever its time constant or its
# downweighting of the large first innovations.
_TRACK_PAIRS = 330


def test_local_plus_offset_tracks_ellipsoid_height():
    """after the true offset changes, local height plus the published offset tracks the new ellipsoid."""
    off_a, off_b = runtime_offset_pair()
    h_local = runtime_local_height_m()
    local_std = 0.25
    gnss_std = 0.6
    dt_us = 11 * _US
    cmds = _offset_pairs(
        h_local, local_std, off_b, gnss_std, t0_us=0, count=_TRACK_PAIRS, dt_us=dt_us
    )
    run = c_offset_run(
        OffScenario(
            t_init=0,
            h_local=h_local,
            local_std=local_std,
            h_ell=h_local + off_a,
            gnss_std=gnss_std,
            cmds=cmds,
        )
    )
    frozen = c_offset_run(
        OffScenario(
            t_init=0,
            h_local=h_local,
            local_std=local_std,
            h_ell=h_local + off_a,
            gnss_std=gnss_std,
            cmds=[],
        )
    )
    assert run.init_ok, "offset init was refused"
    assert frozen.last().get_ok and frozen.last().offset is not None
    first = run.snaps[0]
    assert first.get_ok and first.offset is not None, "first pair did not publish an offset"
    last = run.last()
    assert last.get_ok and last.offset is not None, (
        "offset accessor failed after the pair stream"
    )
    reconstructed = h_local + last.offset
    frozen_off = frozen.last().offset
    print(
        f"first={first.offset} last={last.offset} frozen={frozen_off} A={off_a} B={off_b} "
        f"local+off={reconstructed} ell_B={h_local + off_b}",
        flush=True,
    )
    # The published offset moved from the first pair toward the new offset.
    assert (last.offset - first.offset) * (off_b - off_a) > 0.0, (
        "published offset never moved from the first pair toward the new offset"
    )
    # Not frozen: nearer the new offset than the same instance given no
    # further pair (the first pair's offset).
    assert abs(last.offset - off_b) < abs(frozen_off - off_b), (
        "offset was frozen at the first pair: not nearer the new offset than "
        "the twin that saw no further pair"
    )
    assert abs(reconstructed - (h_local + off_b)) < abs(reconstructed - (h_local + off_a)), (
        "local plus offset stayed closer to the first ellipsoid than to the new one"
    )


def test_offset_converts_local_height_during_gnss_gap():
    """during a GNSS gap the instance offset still converts a new local height."""
    off_a, off_b = runtime_offset_pair()
    h_local = runtime_local_height_m()
    h_gap = h_local + runtime_climb_m() + 5.0
    local_std = 0.25
    gnss_std = 0.6
    dt_us = 11 * _US
    cmds = _offset_pairs(
        h_local, local_std, off_b, gnss_std, t0_us=0, count=_TRACK_PAIRS, dt_us=dt_us
    )
    t_gap = cmds[-1].t_us + _US
    cmds.append(OffCmd(tag="G", t_us=t_gap))
    run = c_offset_run(
        OffScenario(
            t_init=0,
            h_local=h_local,
            local_std=local_std,
            h_ell=h_local + off_a,
            gnss_std=gnss_std,
            cmds=cmds,
        )
    )
    assert run.init_ok, "offset init was refused"
    gap = [s for s in run.snaps if s.t_us == t_gap]
    assert gap, "instance was not re-read during the GNSS gap"
    snap = gap[-1]
    assert snap.get_ok and snap.offset is not None, (
        "offset accessor failed during the GNSS gap"
    )
    converted = h_gap + snap.offset
    truth = h_gap + off_b
    stale = h_gap + off_a
    print(
        f"gap offset={snap.offset} converted={converted} truth={truth} stale={stale}",
        flush=True,
    )
    assert abs(converted - truth) < abs(converted - stale), (
        "gap conversion stayed closer to the first-pair ellipsoid than to the tracked one"
    )


def test_pairs_without_positive_gnss_vertical_variance_skipped():
    """pairs without a positive GNSS vertical variance are skipped; a positive pair must move the offset."""
    off_a, off_b = runtime_offset_pair()
    off_c = off_b + 18.0
    h_local = runtime_local_height_m()
    local_std = 0.25
    gnss_std = 0.6
    dt_us = 11 * _US
    prefix = _offset_pairs(
        h_local, local_std, off_b, gnss_std, t0_us=0, count=24, dt_us=dt_us
    )
    t_step = prefix[-1].t_us + dt_us
    pull_cmd = OffCmd(
        tag="E",
        t_us=t_step,
        h_local=h_local,
        local_std=local_std,
        h_ell=h_local + off_c,
        gnss_std=gnss_std,
    )
    skip_cmd = OffCmd(
        tag="E",
        t_us=t_step,
        h_local=h_local,
        local_std=local_std,
        h_ell=h_local + off_c,
        gnss_std=0.0,
    )
    pulled = c_offset_run(
        OffScenario(
            t_init=0,
            h_local=h_local,
            local_std=local_std,
            h_ell=h_local + off_a,
            gnss_std=gnss_std,
            cmds=prefix + [pull_cmd],
        )
    )
    skipped = c_offset_run(
        OffScenario(
            t_init=0,
            h_local=h_local,
            local_std=local_std,
            h_ell=h_local + off_a,
            gnss_std=gnss_std,
            cmds=prefix + [skip_cmd],
        )
    )
    assert pulled.init_ok and skipped.init_ok, "offset init was refused"
    before = [s for s in pulled.snaps if s.t_us == prefix[-1].t_us]
    skip_before = [s for s in skipped.snaps if s.t_us == prefix[-1].t_us]
    assert before and before[-1].get_ok and before[-1].offset is not None
    assert skip_before and skip_before[-1].get_ok and skip_before[-1].offset is not None
    first_off = pulled.snaps[0].offset
    assert first_off is not None, "first pair did not publish an offset"
    off_before = before[-1].offset
    # Rate-free (PRD: how fast the offset tracks is not scored): the
    # positive-variance prefix moved the offset from the first pair toward
    # the new offset, by any amount.
    assert (off_before - first_off) * (off_b - off_a) > 0.0, (
        "positive-variance pairs never moved the offset toward their offset "
        "before the skip contrast"
    )
    assert skip_before[-1].offset == off_before, (
        "skip twin diverged before the contrast pair on identical bytes"
    )
    pull_last = pulled.last()
    skip_last = skipped.last()
    assert pull_last.get_ok and skip_last.get_ok
    d_pull = pull_last.offset - off_before
    d_skip = skip_last.offset - off_before
    toward = 1.0 if off_c > off_before else -1.0
    print(
        f"first={first_off} before={off_before} pull={pull_last.offset} "
        f"skip={skip_last.offset} C={off_c} d_pull={d_pull} d_skip={d_skip}",
        flush=True,
    )
    # Differential against the zero-variance twin of the same pair: the
    # positive-variance pair moves the offset toward its own offset, the
    # skipped pair does not move it, and the pull is strictly larger than
    # whatever the skipped twin did. No rate is frozen.
    assert d_pull * toward > 0.0, (
        "a further positive-variance pair did not move the offset toward that pair's offset"
    )
    assert abs(d_skip) < abs(d_pull), (
        "a non-positive GNSS vertical variance pair moved the offset as much as "
        "the positive-variance twin"
    )
    assert abs(d_skip) < 0.25, (
        "a non-positive GNSS vertical variance pair still moved the offset"
    )

    bad = c_offset_run(
        OffScenario(
            t_init=0,
            h_local=h_local,
            local_std=local_std,
            h_ell=h_local + off_a,
            gnss_std=0.0,
            cmds=[],
        )
    )
    pair_off = off_a
    print(f"first-pair non-positive init_ok={bad.init_ok} get_ok={bad.last().get_ok}", flush=True)
    if bad.last().get_ok and bad.last().offset is not None:
        assert abs(bad.last().offset - pair_off) > 1.0, (
            "a non-positive first pair still published that pair's offset"
        )
    else:
        assert not bad.last().get_ok, "non-positive first pair published an offset"


# ---------------------------------------------------------------------------
# E. Downweight, not drop; 2 m default
# ---------------------------------------------------------------------------


def test_baro_spike_downweighted_height_does_not_jump():
    """a one-sample pressure glitch does not become the datum."""
    pad_h = runtime_pad_isa_m()
    spike = runtime_spike_isa_m()
    p_pad = tropospheric_isa_pressure_pa(pad_h)
    p_spike = tropospheric_isa_pressure_pa(pad_h + spike)
    pad = vert_stream(duration_s=3.0, pressure_pa=p_pad)
    t_spike = _last_cmd_t(pad) + int(DT_SEC * _US)
    spike_cmd = VertCmd(
        tag="E",
        t_us=t_spike,
        acc=SPECIFIC_FORCE_LEVEL,
        quat=level_quat(),
        pressure_pa=p_spike,
        baro_valid=True,
    )
    recover = vert_stream(duration_s=1.5, t0_us=t_spike, pressure_pa=p_pad)
    glitch = c_vert_run(
        VertScenario(t_init=0, pressure_pa=p_pad, cmds=pad + [spike_cmd] + recover)
    )
    held = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            cmds=pad
            + vert_stream(duration_s=8.0, t0_us=_last_cmd_t(pad), pressure_pa=p_spike),
        )
    )
    assert glitch.init_ok and held.init_ok, "spike init was refused"
    require_published_vert(glitch.last(), "glitch recover")
    require_published_vert(held.last(), "held spike")
    at_pad = [s for s in glitch.snaps if s.t_us <= _last_cmd_t(pad) and s.h_ok]
    assert at_pad
    print(
        f"pad h={at_pad[-1].h} after-glitch h={glitch.last().h} "
        f"held h={held.last().h} spike={spike}",
        flush=True,
    )
    assert abs(glitch.last().h - at_pad[-1].h) < 0.35 * spike, (
        "a one-sample pressure glitch jumped height toward the spike"
    )
    assert abs(held.last().h - at_pad[-1].h) > 2.0, (
        "holding the spike pressure never left the pad — live baseline missing"
    )


def test_persistent_weather_offset_does_not_deadlock():
    """a persistent weather offset is followed; downweight is not a hard drop."""
    pad_h = runtime_pad_isa_m()
    weather = runtime_weather_isa_m() + 4.0
    p_pad = tropospheric_isa_pressure_pa(pad_h)
    p_new = tropospheric_isa_pressure_pa(pad_h + weather)
    pad = vert_stream(duration_s=2.5, pressure_pa=p_pad)
    persist = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            cmds=pad
            + vert_stream(duration_s=10.0, t0_us=_last_cmd_t(pad), pressure_pa=p_new),
        )
    )
    # 10 s without a barometer past the 8 s watchdog warm-up: the watchdog
    # is not the subject of this contrast (default-tuning dependent), so
    # the never-feed twin switches it off through the public config field.
    never = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            cmds=pad
            + vert_stream(
                duration_s=10.0,
                t0_us=_last_cmd_t(pad),
                pressure_pa=p_new,
                baro_valid=False,
            ),
            restart_disable=True,
        )
    )
    first = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            cmds=pad
            + [
                VertCmd(
                    tag="E",
                    t_us=_last_cmd_t(pad) + int(DT_SEC * _US),
                    acc=SPECIFIC_FORCE_LEVEL,
                    quat=level_quat(),
                    pressure_pa=p_new,
                    baro_valid=True,
                )
            ],
        )
    )
    assert persist.init_ok and never.init_ok and first.init_ok
    require_published_vert(persist.last(), "persistent weather")
    require_published_vert(never.last(), "never-feed")
    require_published_vert(first.last(), "first new sample")
    t_pad = _last_cmd_t(pad)
    pad_h_pub = [s for s in persist.snaps if s.t_us <= t_pad and s.h_ok][-1].h
    print(
        f"persist h={persist.last().h} never h={never.last().h} "
        f"first h={first.last().h} weather={weather}",
        flush=True,
    )
    assert persist.last().h - pad_h_pub > 1.5, (
        "persistent new pressure did not pull height off the pad"
    )
    assert abs(persist.last().h - never.last().h) > 1.0, (
        "persistent weather arm was not distinguishable from never feeding the new pressure"
    )
    assert abs(first.last().h - pad_h_pub) < 0.45 * weather, (
        "the first new-pressure sample jumped height to the weather step"
    )


def _first_baro_pull(baro_std: float, pad_h: float, step: float) -> float:
    """Compare measurement noise with the same explicit initial uncertainty."""
    run = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=tropospheric_isa_pressure_pa(pad_h),
            h_init_std=2.0,
            baro_std=baro_std,
            cmds=vert_stream(
                duration_s=DT_SEC, t0_us=0,
                pressure_pa=tropospheric_isa_pressure_pa(pad_h + step),
            ),
        )
    )
    assert run.init_ok, "barometer noise comparison init was refused"
    at_init = [s for s in run.snaps if s.t_us <= 0 and s.h_ok]
    after = [s for s in run.snaps if s.t_us > 0 and s.h_ok]
    assert at_init and after
    assert after[-1].n_invalid == at_init[-1].n_invalid
    return after[-1].h - at_init[-1].h


def test_all_zero_config_default_baro_altitude_1sigma_is_2m():
    """The default measurement noise equals the explicitly specified 2 m."""
    pad_h = runtime_pad_isa_m()
    step = 1.05 + (runtime_weather_isa_m() % 0.20)
    dh_omit = _first_baro_pull(0.0, pad_h, step)
    dh_2m = _first_baro_pull(BARO_1SIGMA_DEFAULT_M, pad_h, step)
    print(f"first-update dh omit={dh_omit} explicit_2m={dh_2m}", flush=True)
    assert dh_2m > 0.0, "explicit measurement did not move height toward the observation"
    assert math.isclose(dh_omit, dh_2m, rel_tol=1e-5, abs_tol=1e-6), (
        "omitted barometer noise differs from explicit 2 m under identical initial conditions"
    )


def test_baro_measurement_noise_changes_weight_with_fixed_initial_uncertainty():
    """Only measurement noise changes; no prescribed first-update gain ratio."""
    pad_h = runtime_pad_isa_m()
    # This innovation is below the explicit 2 m initial uncertainty. Unlike
    # an omitted initial uncertainty, it does not shrink with measurement noise.
    step = 1.05 + (runtime_weather_isa_m() % 0.20)
    tight = runtime_tight_baro_std_m()
    dh_2m = _first_baro_pull(BARO_1SIGMA_DEFAULT_M, pad_h, step)
    dh_tight = _first_baro_pull(tight, pad_h, step)
    print(f"fixed-prior dh explicit_2m={dh_2m} tight={dh_tight} std={tight}", flush=True)
    assert 0.0 < dh_2m < dh_tight, (
        "lower measurement uncertainty did not increase its weight with the same initial state"
    )


# ---------------------------------------------------------------------------
# F. Vertical ZUPT
# ---------------------------------------------------------------------------


def test_vertical_zupt_holds_climb_near_zero_on_still_pad():
    """on a still pad, ZUPT holds climb rate near zero; without it, biased accel leaves zero."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    bias = runtime_acc_bias_mps2()
    acc = up_specific_force(bias)
    free = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p,
            cmds=vert_stream(
                duration_s=3.0, acc=acc, pressure_pa=p, baro_valid=False, zupt=False
            ),
        )
    )
    held = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p,
            cmds=vert_stream(
                duration_s=3.0, acc=acc, pressure_pa=p, baro_valid=False, zupt=True
            ),
        )
    )
    assert free.init_ok and held.init_ok
    require_published_vert(free.last(), "no ZUPT")
    require_published_vert(held.last(), "ZUPT")
    print(f"no-ZUPT v={free.last().v} ZUPT v={held.last().v} bias={bias}", flush=True)
    assert abs(free.last().v) > 0.4, "no-ZUPT arm did not leave zero climb — live baseline missing"
    assert abs(held.last().v) < 0.25, "ZUPT did not hold climb rate near zero"
    assert abs(held.last().v) < 0.35 * abs(free.last().v), (
        "ZUPT arm was not distinguishable from the no-ZUPT twin"
    )


def test_vertical_zupt_not_gated_on_filter_velocity():
    """ZUPT is not gated on the filter's own climb rate."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    a_up = runtime_a_up_mps2()
    acc = up_specific_force(a_up)
    spin = vert_stream(duration_s=0.40, acc=acc, pressure_pa=p, baro_valid=False)
    t0 = _last_cmd_t(spin)
    # After climb is already large, both arms go still. The only remaining
    # difference is whether ZUPT is called — keeping the absurd accel on
    # during ZUPT fights the (chi²-downweighted) zero-velocity measurement.
    still = SPECIFIC_FORCE_LEVEL
    zupt = vert_stream(
        duration_s=2.5, t0_us=t0, acc=still, pressure_pa=p, baro_valid=False, zupt=True
    )
    coast = vert_stream(
        duration_s=2.5, t0_us=t0, acc=still, pressure_pa=p, baro_valid=False, zupt=False
    )
    armed = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=spin + zupt))
    twin = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=spin + coast))
    assert armed.init_ok and twin.init_ok
    at_spin = [s for s in armed.snaps if s.t_us == t0 and s.v_ok]
    assert at_spin and abs(at_spin[-1].v) > 1.5, (
        "climb rate was not yet large enough that a |v| gate would matter"
    )
    require_published_vert(armed.last(), "ZUPT while fast")
    require_published_vert(twin.last(), "no ZUPT while fast")
    print(
        f"pre v={at_spin[-1].v} ZUPT v={armed.last().v} twin v={twin.last().v}",
        flush=True,
    )
    assert abs(armed.last().v) < abs(twin.last().v) - 0.4, (
        "ZUPT while climb rate was large was not distinguishable from skipping it"
    )
    assert abs(armed.last().v) < abs(at_spin[-1].v), (
        "ZUPT did not pull climb toward zero"
    )


# ---------------------------------------------------------------------------
# G. Non-finite drop; init refuse
# ---------------------------------------------------------------------------


def test_nonfinite_pressure_dropped_filter_continues():
    """a non-finite pressure is dropped and processing continues."""
    pad_h = runtime_pad_isa_m()
    climb = runtime_climb_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    p_up = tropospheric_isa_pressure_pa(pad_h + climb)
    pad = vert_stream(duration_s=2.0, pressure_pa=p)
    t_pad = _last_cmd_t(pad)
    t_bad = t_pad + int(DT_SEC * _US)
    for token, label in ((float("nan"), "NaN"), (float("inf"), "Inf")):
        bad = VertCmd(
            tag="E",
            t_us=t_bad,
            acc=SPECIFIC_FORCE_LEVEL,
            quat=level_quat(),
            pressure_pa=token,
            baro_valid=True,
        )
        after = vert_stream(duration_s=6.0, t0_us=t_bad, pressure_pa=p_up)
        run = c_vert_run(
            VertScenario(t_init=0, pressure_pa=p, cmds=pad + [bad] + after)
        )
        assert run.init_ok, f"{label} pressure run init refused"
        before = [s for s in run.snaps if s.t_us == t_pad]
        at_bad = [s for s in run.snaps if s.t_us == t_bad]
        assert before and at_bad
        require_published_vert(before[-1], f"before {label} pressure")
        require_published_vert(at_bad[-1], f"{label} pressure epoch")
        require_published_vert(run.last(), f"after {label} pressure")
        h_pad = before[-1].h
        h_drop = at_bad[-1].h
        h_later = run.last().h
        print(
            f"{label} pressure h pad={h_pad} drop={h_drop} later={h_later} "
            f"climb={climb}",
            flush=True,
        )
        assert math.isfinite(h_drop), (
            f"{label} pressure epoch published a non-finite height"
        )
        assert math.isfinite(h_later), (
            f"{label} pressure permanently disabled the filter"
        )
        # Relative order only: the drop epoch stays with the pad; a later
        # climb-consistent pressure must move height relative to that pad.
        # Accessor success or a return to the same pad pressure is not enough.
        assert abs(h_drop - h_pad) < abs(h_later - h_pad), (
            f"{label} pressure jumped height as if it had been treated as metres, "
            "or later valid pressure never moved height relative to the post-drop pad"
        )
        assert (h_later - h_pad) * climb > 0.0, (
            f"{label} later climb-consistent pressure did not raise height "
            "relative to the post-drop pad"
        )


def test_nonfinite_imu_dropped_filter_continues():
    """a non-finite IMU sample is dropped; a NaN pressure still consumes finite IMU."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    a_up = runtime_a_up_mps2()
    pad = vert_stream(duration_s=2.0, pressure_pa=p)
    t_bad = _last_cmd_t(pad) + int(0.20 * _US)
    nan_imu = VertCmd(
        tag="E",
        t_us=t_bad,
        acc=(float("nan"), 0.0, -(G_MPS2 + a_up)),
        quat=level_quat(),
        pressure_pa=p,
        baro_valid=True,
    )
    nan_p = VertCmd(
        tag="E",
        t_us=t_bad,
        acc=up_specific_force(a_up),
        quat=level_quat(),
        pressure_pa=float("nan"),
        baro_valid=True,
    )
    after = vert_stream(duration_s=0.20, t0_us=t_bad, pressure_pa=p)
    imu_run = c_vert_run(
        VertScenario(t_init=0, pressure_pa=p, cmds=pad + [nan_imu] + after)
    )
    p_run = c_vert_run(
        VertScenario(t_init=0, pressure_pa=p, cmds=pad + [nan_p] + after)
    )
    assert imu_run.init_ok and p_run.init_ok
    imu_before = [s for s in imu_run.snaps if s.t_us == _last_cmd_t(pad)][-1]
    imu_bad = [s for s in imu_run.snaps if s.t_us == t_bad][-1]
    p_before = [s for s in p_run.snaps if s.t_us == _last_cmd_t(pad)][-1]
    p_bad = [s for s in p_run.snaps if s.t_us == t_bad][-1]
    require_published_vert(imu_bad, "NaN IMU epoch")
    require_published_vert(p_bad, "NaN pressure finite IMU")
    require_published_vert(imu_run.last(), "after NaN IMU")
    print(
        f"NaN IMU dh={imu_bad.h - imu_before.h} "
        f"NaN P dh={p_bad.h - p_before.h}",
        flush=True,
    )
    expect = kinematics_height_m(a_up, 0.20)
    assert abs(imu_bad.h - imu_before.h) < 0.35 * abs(expect), (
        "non-finite IMU still integrated the fake acceleration"
    )
    assert (p_bad.h - p_before.h) * expect > 0.0 and abs(p_bad.h - p_before.h) > 0.35 * abs(
        expect
    ), "finite IMU with NaN pressure did not still integrate specific force"
    assert abs((p_bad.h - p_before.h) - (imu_bad.h - imu_before.h)) > 0.5 * abs(
        expect
    ), "NaN IMU and NaN pressure were not distinguishable"


def test_init_refuses_nonfinite_or_implausible_anchor_pressure():
    """init itself fails on a non-finite or negative (ISA-undefined) anchor and succeeds on sea-level-standard and ordinary tropospheric positive pressure."""
    good_p = tropospheric_isa_pressure_pa(runtime_pad_isa_m())
    neg_p = -(50.0 + runtime_pad_isa_m())
    for p, label in ((ISA_P0_PA, "101325"), (good_p, "ordinary tropospheric")):
        run = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=[]))
        print(f"{label} init_ok={run.init_ok}", flush=True)
        assert run.init_ok, f"{label} anchor was refused"
    for p, label in (
        (float("nan"), "NaN"),
        (float("inf"), "Inf"),
        (neg_p, "negative"),
    ):
        run = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=[]))
        print(f"{label} init_ok={run.init_ok} p={p}", flush=True)
        assert not run.init_ok, f"{label} anchor pressure was accepted"


# ---------------------------------------------------------------------------
# H. Time anomalies
# ---------------------------------------------------------------------------


def test_backwards_timestamp_skips_epoch():
    """a backwards timestamp skips that epoch; later increasing timestamps continue."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    a_up = runtime_a_up_mps2()
    pad = vert_stream(duration_s=1.5, pressure_pa=p)
    t_last = _last_cmd_t(pad)
    # Reverse gap must be long enough that integrating |dt| exceeds the skip
    # bound (0.5·a·(50 ms)² sits under 0.35·max(expect, 0.1)), yet shorter
    # than 0.5 s so an |dt| integrator still predicts instead of treating
    # the reverse as a forward outage. Resume's first step is this gap plus
    # one IMU period, which must also stay under the 0.5 s IMU-skip cap.
    back = VertCmd(
        tag="E",
        t_us=t_last - int(GAP_BACKWARDS_S * _US),
        acc=up_specific_force(a_up),
        quat=level_quat(),
        pressure_pa=p,
        baro_valid=False,
    )
    after_s = 0.30
    after = vert_stream(
        duration_s=after_s,
        t0_us=t_last,
        acc=up_specific_force(a_up),
        pressure_pa=p,
        baro_valid=False,
    )
    run = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=pad + [back] + after))
    assert run.init_ok
    before = [s for s in run.snaps if s.t_us == t_last][-1]
    at_back = [s for s in run.snaps if s.t_us == back.t_us][-1]
    require_published_vert(before, "before reverse")
    require_published_vert(at_back, "reverse epoch")
    require_published_vert(run.last(), "after reverse")
    expect_h = kinematics_height_m(a_up, GAP_BACKWARDS_S)
    expect_v = kinematics_climb_mps(a_up, GAP_BACKWARDS_S)
    expect_after = kinematics_height_m(a_up, after_s)
    print(
        f"before h={before.h} v={before.v} back h={at_back.h} v={at_back.v} "
        f"after h={run.last().h} expect_h={expect_h}",
        flush=True,
    )
    assert abs(at_back.h - before.h) < 0.35 * abs(expect_h), (
        "a backwards epoch with absurd specific force still integrated height"
    )
    assert abs(at_back.v - before.v) < 0.35 * abs(expect_v), (
        "a backwards epoch with absurd specific force still integrated climb rate"
    )
    dh_after = run.last().h - before.h
    assert dh_after * a_up > 0.0, (
        "later increasing timestamps did not resume IMU integration"
    )
    assert abs(dh_after) > 0.25 * abs(expect_after), (
        "later increasing timestamps did not visibly resume IMU height integration"
    )


def test_forward_gap_just_under_0_5s_still_integrates():
    """a forward gap just under 0.5 s with absurd vertical specific force still integrates."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    a_up = runtime_a_up_mps2()
    pad = vert_stream(duration_s=1.0, pressure_pa=p)
    t0 = _last_cmd_t(pad)
    gap = VertCmd(
        tag="E",
        t_us=t0 + int(GAP_JUST_UNDER_S * _US),
        acc=up_specific_force(a_up),
        quat=level_quat(),
        pressure_pa=p,
        baro_valid=False,
    )
    run = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=pad + [gap]))
    assert run.init_ok
    before = [s for s in run.snaps if s.t_us == t0][-1]
    after = [s for s in run.snaps if s.t_us == gap.t_us][-1]
    require_published_vert(before, "before 0.48 s gap")
    require_published_vert(after, "0.48 s gap")
    dh = after.h - before.h
    expect = kinematics_height_m(a_up, GAP_JUST_UNDER_S)
    print(f"0.48 s dh={dh} expect={expect} a_up={a_up}", flush=True)
    assert dh * expect > 0.0, "just-under-0.5 s gap did not integrate in the kinematics sign"
    assert abs(dh) > 0.25 * abs(expect), "just-under-0.5 s gap did not visibly integrate IMU height"


def test_named_0_3s_gap_is_not_an_outage():
    """a 0.3 s gap is not treated as an outage; IMU height still integrates."""
    pad_h = runtime_pad_isa_m()
    p = tropospheric_isa_pressure_pa(pad_h)
    a_up = runtime_a_up_mps2()
    pad = vert_stream(duration_s=1.0, pressure_pa=p)
    t0 = _last_cmd_t(pad)
    gap = VertCmd(
        tag="E",
        t_us=t0 + int(GAP_NAMED_NOT_OUTAGE_S * _US),
        acc=up_specific_force(a_up),
        quat=level_quat(),
        pressure_pa=p,
        baro_valid=False,
    )
    run = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=pad + [gap]))
    assert run.init_ok
    before = [s for s in run.snaps if s.t_us == t0][-1]
    after = [s for s in run.snaps if s.t_us == gap.t_us][-1]
    require_published_vert(after, "0.3 s gap")
    dh = after.h - before.h
    expect = kinematics_height_m(a_up, GAP_NAMED_NOT_OUTAGE_S)
    print(f"0.3 s dh={dh} expect={expect}", flush=True)
    assert dh * expect > 0.0 and abs(dh) > 0.25 * abs(expect), (
        "a 0.3 s gap was treated as an outage so IMU height was not integrated"
    )


def test_forward_gap_just_over_0_5s_skips_imu_but_still_fuses_baro():
    """just over 0.5 s skips IMU height integration; a barometer sample on that epoch still fuses."""
    pad_h = runtime_pad_isa_m()
    climb = 2.2 + runtime_climb_m() * 0.05
    p = tropospheric_isa_pressure_pa(pad_h)
    p_up = tropospheric_isa_pressure_pa(pad_h + climb)
    a_up = runtime_a_up_mps2()
    pad = vert_stream(duration_s=0.20, pressure_pa=p)
    t0 = _last_cmd_t(pad)
    t_gap = t0 + int(GAP_JUST_OVER_S * _US)
    no_baro = VertCmd(
        tag="E",
        t_us=t_gap,
        acc=up_specific_force(a_up),
        quat=level_quat(),
        pressure_pa=p,
        baro_valid=False,
    )
    with_baro = VertCmd(
        tag="E",
        t_us=t_gap,
        acc=up_specific_force(a_up),
        quat=level_quat(),
        pressure_pa=p_up,
        baro_valid=True,
    )
    skipped = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=pad + [no_baro]))
    fused = c_vert_run(VertScenario(t_init=0, pressure_pa=p, cmds=pad + [with_baro]))
    under = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p,
            cmds=pad
            + [
                VertCmd(
                    tag="E",
                    t_us=t0 + int(GAP_JUST_UNDER_S * _US),
                    acc=up_specific_force(a_up),
                    quat=level_quat(),
                    pressure_pa=p,
                    baro_valid=False,
                )
            ],
        )
    )
    assert skipped.init_ok and fused.init_ok and under.init_ok
    b0 = [s for s in skipped.snaps if s.t_us == t0][-1]
    skip_snap = [s for s in skipped.snaps if s.t_us == t_gap][-1]
    fuse_snap = [s for s in fused.snaps if s.t_us == t_gap][-1]
    under_before = [s for s in under.snaps if s.t_us == t0][-1]
    under_after = under.last()
    require_published_vert(skip_snap, "0.52 s no baro")
    require_published_vert(fuse_snap, "0.52 s with baro")
    dh_skip = skip_snap.h - b0.h
    dh_under = under_after.h - under_before.h
    expect = kinematics_height_m(a_up, GAP_JUST_OVER_S)
    print(
        f"0.52 s no-baro dh={dh_skip} 0.48 s dh={dh_under} fused h={fuse_snap.h} "
        f"expect_imu={expect}",
        flush=True,
    )
    assert abs(dh_skip) < 0.25 * abs(expect), (
        "just-over-0.5 s gap still integrated IMU height"
    )
    assert abs(dh_under) > abs(dh_skip) + 0.15, (
        "just-over and just-under gap arms were not distinguishable"
    )
    assert fuse_snap.h - skip_snap.h > 0.025, (
            "a barometer sample on the over-gap epoch was not fused"
        )
    assert (fuse_snap.h - skip_snap.h) * climb > 0.0, (
        "the fused over-gap barometer sample pulled height the wrong way"
    )


# ---------------------------------------------------------------------------
# I. Later unpublished; suite re-bootstrap
# ---------------------------------------------------------------------------


def test_standalone_stays_unpublished_until_reinit_after_implausible_1sigma():
    """after accessors fail, standalone stays unpublished until the caller re-inits."""
    pad_h = runtime_pad_isa_m()
    climb = runtime_climb_m()
    p_pad = tropospheric_isa_pressure_pa(pad_h)
    p_up = tropospheric_isa_pressure_pa(pad_h + climb)
    pad = vert_stream(duration_s=2.0, pressure_pa=p_pad)
    rise = vert_stream(duration_s=4.0, t0_us=_last_cmd_t(pad), pressure_pa=p_up)
    t_pub = _last_cmd_t(rise)
    outage = vert_stream(
        duration_s=180.0,
        t0_us=t_pub,
        imu_hz=10,
        pressure_pa=p_up,
        baro_valid=False,
    )
    t_fail_budget = _last_cmd_t(outage)
    restore = vert_stream(
        duration_s=2.0, t0_us=t_fail_budget, pressure_pa=p_up, baro_valid=True
    )
    t_re = _last_cmd_t(restore) + int(0.05 * _US)
    reinit = VertCmd(tag="R", t_us=t_re, pressure_pa=p_up, h_init=0.0)
    after = vert_stream(duration_s=1.0, t0_us=t_re, pressure_pa=p_up)
    run = c_vert_run(
        VertScenario(
            t_init=0,
            pressure_pa=p_pad,
            cmds=pad + rise + outage + restore + [reinit] + after,
        )
    )
    assert run.init_ok, "standalone init was refused"
    climbed = [s for s in run.snaps if s.t_us <= t_pub and s.h_ok and s.isa_ok]
    assert climbed, "standalone never published"
    assert climbed[-1].h > 1.0 and climbed[-1].isa > tropospheric_isa_altitude_m(p_pad) + 1.0, (
        "first segment did not follow the pressure climb — not yet a published solution"
    )
    failed = [s for s in run.snaps if t_pub < s.t_us <= t_fail_budget and not s.h_ok]
    assert failed, (
        "standalone kept publishing after the barometer outage budget — "
        "height/climb accessors never failed"
    )
    assert failed[0].t_us > climbed[0].t_us, "accessors failed before a solution was produced"
    require_unpublished_vert(failed[0], "standalone degraded 1-sigma")
    assert all(not s.v_ok for s in failed), (
        "climb-rate accessors did not fail in the same degraded 1-sigma condition"
    )
    restored = [s for s in run.snaps if t_fail_budget < s.t_us < t_re]
    assert restored, "no snapshots while barometer was restored without re-init"
    assert all(not s.h_ok and not s.v_ok for s in restored), (
        "standalone recovered without the caller re-initing"
    )
    assert run.reinit_ok and run.reinit_ok[-1], "caller re-init was refused"
    after_re = [s for s in run.snaps if s.t_us >= t_re]
    assert after_re, "no snapshots after re-init"
    published_after = [s for s in after_re if s.h_ok]
    assert published_after, "standalone stayed unpublished after the caller re-inited"
    require_published_vert(published_after[-1], "after re-init")
    print(
        f"standalone fail at t={failed[0].t_us} restore_n={len(restored)} "
        f"reinit_h={published_after[-1].h}",
        flush=True,
    )


def test_suite_rebootstrap_after_implausible_height_or_climb_1sigma():
    """the suite re-bootstraps this channel without a caller re-init; a healthy twin stays published."""
    lat, lon, h = runtime_suite_site()
    pad_h = runtime_pad_isa_m()
    climb = runtime_climb_m()
    p_pad = tropospheric_isa_pressure_pa(pad_h)
    p_up = tropospheric_isa_pressure_pa(pad_h + climb)
    boot = chan_suite_stream(duration_s=1.2, pressure_pa=p_pad, baro_valid=True)
    rise = chan_suite_stream(
        duration_s=4.0, t0_us=_last_cmd_t(boot), pressure_pa=p_up, baro_valid=True
    )
    t_pub = _last_cmd_t(rise)
    outage = chan_suite_stream(
        duration_s=180.0,
        t0_us=t_pub,
        imu_hz=10,
        pressure_pa=p_up,
        baro_valid=False,
    )
    t_budget = _last_cmd_t(outage)
    recover = chan_suite_stream(
        duration_s=2.0, t0_us=t_budget, pressure_pa=p_up, baro_valid=True
    )
    degraded = c_chan_suite_run(
        ChanSuiteScenario(
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            epochs=boot + rise + outage + recover,
        )
    )
    healthy = c_chan_suite_run(
        ChanSuiteScenario(
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            epochs=chan_suite_stream(
                duration_s=1.2 + 4.0 + 180.0 + 2.0,
                imu_hz=10,
                pressure_pa=p_up,
                baro_valid=True,
            ),
        )
    )
    assert degraded.init_ok and healthy.init_ok, "suite init failed"
    climbed = [s for s in degraded.snaps if s.t_us <= t_pub and s.h_ok and s.h is not None]
    assert climbed, "suite vertical channel never published"
    assert climbed[-1].h > 0.8, (
        "suite first segment did not follow the pressure climb "
        "(a constant-zero publisher would pass an accessors-only check)"
    )
    failed = [s for s in degraded.snaps if t_pub < s.t_us <= t_budget and not s.h_ok]
    assert failed, (
        "suite channel kept publishing through the barometer outage budget"
    )
    assert all(not s.v_ok for s in failed), (
        "suite climb-rate accessors did not fail in the same degraded 1-sigma condition"
    )
    healthy_live = [s for s in healthy.snaps if s.t_us > 0 and s.h_ok]
    assert healthy_live, "healthy suite twin never published this channel"
    nxt = [s for s in degraded.snaps if s.t_us > t_budget]
    assert nxt, "suite produced no epochs after the outage"
    recovered = [s for s in nxt if s.h_ok and s.v_ok]
    print(
        f"suite climb h={climbed[-1].h} fail_t={failed[0].t_us} "
        f"recovered={bool(recovered)} n_healthy={len(healthy_live)}",
        flush=True,
    )
    assert recovered, (
        "suite vertical-channel accessors did not succeed again without a caller re-init"
    )
    assert recovered[0].h is not None and math.isfinite(recovered[0].h)


def test_published_vertical_snapshots_are_well_formed():
    """Published height, climb rate, ISA altitude and offset values are finite
    and the invalid-input counters are non-negative -- on every vertical and
    offset snapshot parsed in this session and on a pad of its own. A
    violation fails this test only.
    """
    from _harness import require_no_product_issues

    p = tropospheric_isa_pressure_pa(runtime_pad_isa_m())
    run = c_vert_run(
        VertScenario(t_init=0, pressure_pa=p, cmds=vert_stream(duration_s=5.0, pressure_pa=p))
    )
    assert run.init_ok and run.snaps, "pad produced no snapshots"
    require_no_product_issues("F07", "vertical-channel snapshots (F07)")
