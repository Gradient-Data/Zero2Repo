# feature: F10
"""Dataset CSV + config.yaml replay, and the YAML custom-CSV runner (FP-10).

Assertions stay at the PRD's precision: both harnesses consume a directory of
conventional t_us CSVs plus config.yaml; the published series covers the IMU
log and is a fused trajectory, not a copy of the reference or of GNSS; aiding
gnss/ref/none and init auto/ref; missing IMU/reference/GNSS-when-gnss fail
non-zero; unknown owned keys and unknown aiding name the offender; C reads
configured regression limits and refuses a non-positive scoring minimum-epoch
count while Python still solves; comments and malformed rows are skipped;
the YAML runner converts mixed units, follows column mapping, merges
at-or-before, and writes one row per IMU epoch. Message text, exception
types, dump flag spellings, scoring-key spellings as stdout, and RMS gold
values are not pinned.
"""

from __future__ import annotations

import math

from _harness import DEFAULT_REPLAY_TIMEOUT, run_runner, workspace
from F01_helpers import hypot3
from F02_helpers import (
    HAPPY_DURATION_S,
    IMU_HZ,
    SPECIFIC_FORCE_LEVEL,
    ecef_from_llh_deg,
    runtime_ned_shift_m,
    runtime_site,
)
from F03_helpers import WMM_YEAR, body_mag_for_yaw, ned_field_from_independent_wmm
from F07_helpers import tropospheric_isa_altitude_m, tropospheric_isa_pressure_pa
from F08_helpers import MODE_ATTITUDE_ONLY, MODE_FULL
from F10_helpers import (
    NAMED_PAD_S,
    PAD_NEAR_M,
    UNKNOWN_AIDING,
    ReplaySeries,
    c_replay,
    classified_non_full_runner,
    classified_unpublished_3d,
    finite_ars_roll_pitch_from_errdump,
    gap_peak_from_runner,
    gap_peak_from_series,
    imu_times_from_dataset,
    llh_offset_ned,
    llh_offset_north,
    python_replay_result,
    python_replay_series,
    report_names_mode,
    reported_final_mode,
    reporting_text,
    require_errdump_not_written,
    require_leading_hash_header,
    require_nonzero,
    require_nonzero_and_names,
    require_still_pad_ars,
    run_mapped_runner,
    runner_last_at_or_before,
    runner_published_local_height_m,
    runner_tail_full_near,
    runtime_filename,
    runtime_unknown_key,
    series_covers_imu_log,
    series_near_llh,
    write_replay_dataset,
    write_runner_mapping,
    yaw_abs_diff_deg,
    mean_abs_yaw_step_deg,
)


def _site():
    lat, lon, h = runtime_site()
    return lat, lon, h, ecef_from_llh_deg(lat, lon, h)


def _north_m():
    north, _east, _down = runtime_ned_shift_m()
    north = abs(north)
    if north < 4.0:
        north = 8.0
    if north > 25.0:
        north = 12.0 + (north % 8.0)
    print(f"runtime gnss north offset {north} m", flush=True)
    return north


def _east_m():
    _north, east, _down = runtime_ned_shift_m()
    east = abs(east)
    if east < 4.0:
        east = 9.0
    if east > 25.0:
        east = 11.0 + (east % 8.0)
    print(f"runtime gnss east offset {east} m", flush=True)
    return east


def _arb_climb(before, after, what: str) -> float:
    assert before.arb_height_m is not None and after.arb_height_m is not None, (
        f"{what}: named arbitrated height was not published"
    )
    climb = after.arb_height_m - before.arb_height_m
    print(f"{what}: arb height climb={climb:.3f} m", flush=True)
    return climb


# ---------------------------------------------------------------------------
# A. Same directory, fused series, not a copy
# ---------------------------------------------------------------------------


def test_gnss_aided_dataset_fused_not_copy_of_ref_or_gnss():
    """GNSS-aided directory yields a log-length fused series, not ref or GNSS."""
    lat, lon, h, origin = _site()
    north = _north_m()
    gap_acc = 1.4
    with workspace() as ws:
        aligned = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aligned",
            extra_imu_s=2.0,
            gap_north_acc=gap_acc,
        )
        offset = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="offset",
            gnss_north_m=north,
            extra_imu_s=2.0,
            gap_north_acc=gap_acc,
        )
        aligned_series = python_replay_series(aligned, ws.resolve("sol-aligned.csv"))
        offset_series = python_replay_series(offset, ws.resolve("sol-offset.csv"))
        report_names_mode(aligned_series.result, MODE_FULL, "aligned GNSS-aided replay")
        report_names_mode(offset_series.result, MODE_FULL, "offset GNSS-aided replay")
        c_aligned = c_replay(aligned)
        c_offset = c_replay(offset)
        imu_aligned = imu_times_from_dataset(aligned)
        imu_offset = imu_times_from_dataset(offset)
    series_covers_imu_log(aligned_series, imu_aligned)
    series_near_llh(aligned_series, lat, lon, h, what="aligned fused")
    print(f"c aligned rc={c_aligned.returncode} offset rc={c_offset.returncode}", flush=True)
    assert c_aligned.returncode == 0, (
        f"C harness did not accept the in-limit aligned directory: "
        f"{reporting_text(c_aligned)[-1200:]!r}"
    )
    # Offset GNSS is fused (not a copy of ref) and is not the reference series.
    gnss_llh = llh_offset_north(lat, lon, h, north)
    gnss_ecef = ecef_from_llh_deg(*gnss_llh)
    ref_ecef = origin
    series_covers_imu_log(offset_series, imu_offset)
    d_gnss = series_near_llh(
        offset_series, gnss_llh[0], gnss_llh[1], gnss_llh[2], what="offset fused vs GNSS"
    )
    last = offset_series.points[-1]
    last_ecef = ecef_from_llh_deg(last.lat_deg, last.lon_deg, last.h_m)
    d_ref = hypot3(last_ecef, ref_ecef)
    print(f"offset last vs ref={d_ref:.3f} vs gnss={hypot3(last_ecef, gnss_ecef):.3f}", flush=True)
    assert d_ref > 1.0, "fused series is indistinguishable from the reference pad"
    assert hypot3(last_ecef, gnss_ecef) + 1.0 < d_ref, (
        "fused series was not pulled toward the offset GNSS relative to the reference"
    )
    # Not a copy of raw GNSS / ZOH GNSS: after GNSS ends, IMU motion moves the series.
    gnss_end_us = int(round(HAPPY_DURATION_S * 1.0e6))
    gap = [p for p in offset_series.points if p.t_us > gnss_end_us]
    assert gap, "no IMU-only samples after the GNSS stream ended"
    zoh = ecef_from_llh_deg(*gnss_llh)
    moved = []
    for p in gap:
        moved.append(hypot3(ecef_from_llh_deg(p.lat_deg, p.lon_deg, p.h_m), zoh))
    peak = max(moved)
    print(f"gap vs ZOH GNSS peak={peak:.3f} m n={len(gap)}", flush=True)
    assert peak > 0.4, (
        "gap IMU samples did not move relative to holding the last GNSS (ZOH copy)"
    )


def test_python_replay_accepts_directory_or_config_path():
    """Python replay accepts the directory or the config.yaml path."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        dest = write_replay_dataset(
            ws, lat_deg=lat, lon_deg=lon, h_m=h, relpath="either"
        )
        by_dir = python_replay_series(dest, ws.resolve("sol-dir.csv"))
        by_cfg = python_replay_series(
            dest,
            ws.resolve("sol-cfg.csv"),
            target=dest / "config.yaml",
        )
        imu_times = imu_times_from_dataset(dest)
    series_covers_imu_log(by_dir, imu_times)
    series_covers_imu_log(by_cfg, imu_times)
    series_near_llh(by_dir, lat, lon, h, what="directory")
    series_near_llh(by_cfg, lat, lon, h, what="config.yaml path")


def test_both_harnesses_consume_the_same_directory():
    """C and Python both consume the same GNSS-aided directory."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        dest = write_replay_dataset(
            ws, lat_deg=lat, lon_deg=lon, h_m=h, relpath="both"
        )
        py = python_replay_series(dest, ws.resolve("sol-both.csv"))
        c_res = c_replay(dest)
        imu_times = imu_times_from_dataset(dest)
    series_covers_imu_log(py, imu_times)
    series_near_llh(py, lat, lon, h, what="python same-dir")
    assert c_res.returncode == 0, (
        f"C harness could not consume the same directory: "
        f"{reporting_text(c_res)[-1200:]!r}"
    )


def test_t_us_span_not_row_clock():
    """same row count, only the timestamp span changes; only the long span fuses."""
    lat, lon, h, origin = _site()
    n = int(round(HAPPY_DURATION_S * IMU_HZ))
    long_dt = 10_000
    short_dt = 100
    with workspace() as ws:
        long_dir = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="span-long",
            duration_s=HAPPY_DURATION_S,
            dt_us=long_dt,
        )
        short_dir = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="span-short",
            duration_s=n * short_dt / 1.0e6,
            dt_us=short_dt,
        )
        long_series = python_replay_series(long_dir, ws.resolve("sol-long.csv"))
        short_dump = ws.resolve("sol-short.csv")
        short_res = python_replay_result(short_dir, dump_path=short_dump)
        classified_unpublished_3d(short_dump, short_res, "short t_us span")
        series_covers_imu_log(long_series, imu_times_from_dataset(long_dir))
        series_near_llh(long_series, lat, lon, h, what="long t_us span")


def test_optional_imu_temperature_column_ignored():
    """optional eighth-column IMU temperature is ignored by both harnesses."""
    lat, lon, h, _origin = _site()
    gap_acc = 1.4
    extra_s = 2.0
    gnss_end_us = int(round(HAPPY_DURATION_S * 1.0e6))
    zoh = (lat, lon, h)
    with workspace() as ws:
        plain = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="imu7",
            extra_imu_s=extra_s,
            gap_north_acc=gap_acc,
        )
        with_temp = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="imu8",
            extra_imu_s=extra_s,
            gap_north_acc=gap_acc,
            imu_temp=True,
            imu_temp_c=1000.0,
        )
        s7 = python_replay_series(plain, ws.resolve("sol-7.csv"))
        s8 = python_replay_series(with_temp, ws.resolve("sol-8.csv"))
        c7 = c_replay(plain)
        c8 = c_replay(with_temp)
    pre7 = tuple(p for p in s7.points if p.t_us <= gnss_end_us)
    assert pre7, "seven-column series has no fused samples before the GNSS gap"
    series_near_llh(
        ReplaySeries(pre7, s7.result),
        lat,
        lon,
        h,
        what="seven-column fused tail at the pad before the gap",
    )
    peak7 = gap_peak_from_series(s7, zoh, gnss_end_us, "seven-column IMU")
    peak8 = gap_peak_from_series(s8, zoh, gnss_end_us, "eight-column IMU")
    assert peak7 > 0.4, (
        "seven-column gap IMU samples did not move relative to holding GNSS "
        "(IMU columns were not consumed)"
    )
    last7 = ecef_from_llh_deg(
        s7.points[-1].lat_deg, s7.points[-1].lon_deg, s7.points[-1].h_m
    )
    last8 = ecef_from_llh_deg(
        s8.points[-1].lat_deg, s8.points[-1].lon_deg, s8.points[-1].h_m
    )
    d78 = hypot3(last7, last8)
    print(f"temp column last 7-vs-8={d78:.3f} m peak7={peak7:.3f} peak8={peak8:.3f}", flush=True)
    assert peak8 > 0.4, (
        "eight-column gap IMU samples did not move with the IMU-driven baseline"
    )
    assert d78 < 5.0, (
        "eighth IMU temperature cell changed the IMU-driven series "
        f"(7-vs-8 last ECEF {d78:.3f} m)"
    )
    assert c7.returncode == 0 and c8.returncode == 0, (
        f"C did not accept both temperature arms: {c7.returncode} {c8.returncode}"
    )


def test_inputs_section_overrides_filenames():
    """inputs: overrides filenames; unset keeps the conventional name."""
    lat, lon, h, _origin = _site()
    decoy = runtime_site()
    gnss_name = runtime_filename("gnss")
    imu_name = runtime_filename("imu")
    with workspace() as ws:
        covered = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="inputs-on",
            imu_name=imu_name,
            gnss_name=gnss_name,
            inputs={"imu": imu_name, "gnss": gnss_name},
            decoy_gnss_llh=decoy,
            decoy_imu=True,
        )
        renamed = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="inputs-off",
            imu_name=imu_name,
            gnss_name=gnss_name,
            inputs=None,
        )
        (renamed / "imu.csv").unlink(missing_ok=True)
        (renamed / "gnss.csv").unlink(missing_ok=True)
        series = python_replay_series(covered, ws.resolve("sol-in.csv"))
        missing = python_replay_result(renamed)
        c_missing = c_replay(renamed)
        c_covered = c_replay(covered)
    series_near_llh(series, lat, lon, h, what="inputs override")
    decoy_ecef = ecef_from_llh_deg(*decoy)
    last = ecef_from_llh_deg(
        series.points[-1].lat_deg, series.points[-1].lon_deg, series.points[-1].h_m
    )
    pad = ecef_from_llh_deg(lat, lon, h)
    print(
        f"inputs last vs pad={hypot3(last, pad):.3f} vs decoy={hypot3(last, decoy_ecef):.3f}",
        flush=True,
    )
    assert hypot3(last, pad) + 100.0 < hypot3(last, decoy_ecef), (
        "replay fused the conventional-name decoy instead of the inputs: override"
    )
    require_nonzero(missing, "python rename without inputs")
    require_nonzero(c_missing, "C rename without inputs")
    assert c_covered.returncode == 0, (
        "C did not run the renamed streams named under inputs: "
        f"{reporting_text(c_covered)[-1200:]!r}"
    )


def test_zero_gnss_diagonal_replaced_by_config_fallback():
    """zero GNSS diagonal is unknown and is replaced by the config fallback."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        loose = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="diag-loose",
            zero_pos_diag=True,
            zero_vel_diag=True,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
        )
        coarse = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="diag-coarse",
            zero_pos_diag=True,
            zero_vel_diag=True,
            pos_fallback_m=(10.0, 12.0),
            vel_fallback_mps=2.0,
        )
        loose_series = python_replay_series(loose, ws.resolve("sol-loose.csv"))
        coarse_dump = ws.resolve("sol-coarse.csv")
        coarse_res = python_replay_result(coarse, dump_path=coarse_dump)
        classified_unpublished_3d(coarse_dump, coarse_res, "coarse GNSS fallback")
        series_near_llh(loose_series, lat, lon, h, what="zero-diag loose fallback")


# ---------------------------------------------------------------------------
# B. aiding / init / missing streams / unknown keys
# ---------------------------------------------------------------------------


def test_aiding_ref_synthesizes_fix_without_gnss_stream():
    """aiding: ref synthesizes a fix from the reference; GNSS is not required."""
    lat, lon, h, origin = _site()
    with workspace() as ws:
        ref_dir = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aiding-ref",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
        )
        no_fallback = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aiding-ref-nofb",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=None,
            vel_fallback_mps=None,
        )
        zero_fallback = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aiding-ref-zerofb",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=(0.0, 0.0),
            vel_fallback_mps=0.0,
        )
        zero_vertical = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aiding-ref-zero-ver",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=(2.0, 0.0),
            vel_fallback_mps=0.25,
        )
        zero_velocity = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aiding-ref-zero-vel",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.0,
        )
        as_gnss = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aiding-ref-as-gnss",
            aiding="gnss",
            write_gnss=False,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
        )
        north = _north_m()
        gnss_off = llh_offset_north(lat, lon, h, north)
        from_gnss = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aiding-gnss-cov",
            aiding="gnss",
            gnss_north_m=north,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
        )
        from_ref = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="aiding-ref-ignores-gnss",
            aiding="ref",
            gnss_north_m=north,
            write_gnss=True,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
        )
        series = python_replay_series(ref_dir, ws.resolve("sol-ref.csv"))
        s_gnss_cov = python_replay_series(from_gnss, ws.resolve("sol-gnss-cov.csv"))
        s_ref_ign = python_replay_series(from_ref, ws.resolve("sol-ref-ign.csv"))
        py_gnss = python_replay_result(as_gnss)
        py_nofb = python_replay_result(no_fallback)
        py_zerofb = python_replay_result(zero_fallback)
        py_zero_ver = python_replay_result(zero_vertical)
        py_zero_vel = python_replay_result(zero_velocity)
        imu_times = imu_times_from_dataset(ref_dir)
        series_covers_imu_log(series, imu_times)
        series_near_llh(series, lat, lon, h, what="aiding ref near reference")
        series_near_llh(
            s_gnss_cov, gnss_off[0], gnss_off[1], gnss_off[2], what="aiding gnss uses gnss.csv"
        )
        series_near_llh(s_ref_ign, lat, lon, h, what="aiding ref stays on the reference")
        last_ref = s_ref_ign.points[-1]
        last_g = s_gnss_cov.points[-1]
        g_ecef = ecef_from_llh_deg(*gnss_off)
        last_ref_ecef = ecef_from_llh_deg(last_ref.lat_deg, last_ref.lon_deg, last_ref.h_m)
        last_g_ecef = ecef_from_llh_deg(last_g.lat_deg, last_g.lon_deg, last_g.h_m)
        d_ref_to_g = hypot3(last_ref_ecef, g_ecef)
        d_g_to_g = hypot3(last_g_ecef, g_ecef)
        d_ref_to_pad = hypot3(last_ref_ecef, origin)
        d_g_to_pad = hypot3(last_g_ecef, origin)
        print(
            f"aiding gnss vs ref: gnss-arm vs offset={d_g_to_g:.3f} "
            f"ref-arm vs offset={d_ref_to_g:.3f} "
            f"gnss-arm vs pad={d_g_to_pad:.3f} ref-arm vs pad={d_ref_to_pad:.3f}",
            flush=True,
        )
        assert d_g_to_g + 1.0 < d_ref_to_g, (
            "aiding gnss synthesized the fix from the reference instead of "
            "consuming gnss.csv covariance/position"
        )
        assert d_ref_to_pad + 1.0 < d_g_to_pad, (
            "aiding ref followed gnss.csv instead of synthesizing the fix from ref.csv"
        )
        require_nonzero(py_gnss, "aiding gnss without GNSS stream (python)")
        require_nonzero(py_nofb, "aiding ref without GNSS fallback")
        require_nonzero(py_zerofb, "aiding ref with written-zero GNSS fallback")
        require_nonzero(py_zero_ver, "aiding ref with a written-zero vertical position fallback")
        require_nonzero(py_zero_vel, "aiding ref with a written-zero velocity fallback")
        c_gnss = c_replay(as_gnss)
        c_zerofb = c_replay(zero_fallback)
        c_zero_ver = c_replay(zero_vertical)
        c_zero_vel = c_replay(zero_velocity)
        c_nofb = c_replay(no_fallback)
        c_ref = c_replay(ref_dir)
    require_nonzero(c_gnss, "aiding gnss without GNSS stream (C)")
    require_nonzero(c_zerofb, "C aiding ref with written-zero GNSS fallback")
    require_nonzero(c_zero_ver, "C aiding ref with a written-zero vertical position fallback")
    require_nonzero(c_zero_vel, "C aiding ref with a written-zero velocity fallback")
    require_nonzero(c_nofb, "C aiding ref without GNSS fallback")
    print(f"aiding ref C rc={c_ref.returncode}", flush=True)
    assert c_ref.returncode == 0, (
        f"C did not accept aiding ref: {reporting_text(c_ref)[-1200:]!r}"
    )


def test_aiding_ref_positive_written_gnss_fallback_runs():
    """a positive written GNSS fallback under aiding ref lets the directory run."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        present = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-pos-fb",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
        )
        series = python_replay_series(present, ws.resolve("sol-pos-fb.csv"))
        imu_times = imu_times_from_dataset(present)
        series_covers_imu_log(series, imu_times)
        series_near_llh(
            series, lat, lon, h, what="positive written GNSS fallbacks under aiding ref"
        )
        c_res = c_replay(present)
    print(
        f"positive GNSS fallback python rc={series.result.returncode} "
        f"c rc={c_res.returncode} n={len(series.points)}",
        flush=True,
    )
    assert series.result.returncode == 0, (
        "positive written GNSS fallback under aiding ref did not let Python run "
        f"report={reporting_text(series.result)[-1200:]!r}"
    )
    assert c_res.returncode == 0, (
        "positive written GNSS fallback under aiding ref did not let C run "
        f"report={reporting_text(c_res)[-1200:]!r}"
    )


def test_aiding_none_ins_uninitialized_ars_attitude_exists():
    """aiding: none keeps INS unpublished; ARS attitude and baro still run."""
    lat, lon, h, _origin = _site()
    p = tropospheric_isa_pressure_pa(h if 0.0 <= h < 2000.0 else 150.0)
    with workspace() as ws:
        gnss_dir = write_replay_dataset(
            ws, lat_deg=lat, lon_deg=lon, h_m=h, relpath="none-gnss"
        )
        none_dir = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="none-aid",
            aiding="none",
            score_ahrs=1,
            write_baro=True,
            baro_pa=p,
        )
        gnss_series = python_replay_series(gnss_dir, ws.resolve("sol-g.csv"))
        none_dump = ws.resolve("sol-n.csv")
        none_res = python_replay_result(none_dir, dump_path=none_dump)
        classified_unpublished_3d(none_dump, none_res, "aiding none python")
        report_names_mode(none_res, MODE_ATTITUDE_ONLY, "aiding none python")
        c_none = c_replay(none_dir, errdump=ws.resolve("none.err.csv"))
        finite_ars_roll_pitch_from_errdump(ws.resolve("none.err.csv"), "aiding none C")
    series_near_llh(gnss_series, lat, lon, h, what="gnss twin 3D")
    report_names_mode(gnss_series.result, MODE_FULL, "gnss twin")
    print(f"aiding none python rc={none_res.returncode} c rc={c_none.returncode}", flush=True)
    assert reported_final_mode(none_res, "aiding none python") != MODE_FULL, (
        "aiding none still reported FULL as the final suite mode"
    )


def test_c_harness_accepts_aiding_none_as_a_run():
    """C treats none as a run, not as an unknown aiding value."""
    lat, lon, h, _origin = _site()
    pad_h = h if 0.0 <= h < 2000.0 else 150.0
    p = tropospheric_isa_pressure_pa(pad_h)
    p_climb = tropospheric_isa_pressure_pa(pad_h + 80.0)
    dh_isa = tropospheric_isa_altitude_m(p_climb) - tropospheric_isa_altitude_m(p)
    with workspace() as ws:
        none_dir = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="c-none",
            aiding="none",
            score_ahrs=1,
            write_baro=True,
            baro_pa=p,
            lim_baro_rms_m=8.0,
        )
        none_no_baro = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="c-none-nobaro",
            aiding="none",
            score_ahrs=1,
            write_baro=False,
            lim_baro_rms_m=8.0,
        )
        bad_dir = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="c-bad-aid",
            aiding=UNKNOWN_AIDING,
            score_ahrs=1,
            write_baro=True,
            baro_pa=p,
        )
        none_dump = ws.resolve("c-none-py.csv")
        py_none = python_replay_result(none_dir, dump_path=none_dump)
        classified_unpublished_3d(none_dump, py_none, "C-none python twin")
        report_names_mode(py_none, MODE_ATTITUDE_ONLY, "C-none python twin")
        py_nobaro_dump = ws.resolve("c-none-nobaro.csv")
        py_nobaro = python_replay_result(none_no_baro, dump_path=py_nobaro_dump)
        classified_unpublished_3d(py_nobaro_dump, py_nobaro, "C-none no-baro python")
        none_err = ws.resolve("c-none.err.csv")
        bad_err = ws.resolve("c-bad.err.csv")
        c_none = c_replay(none_dir, errdump=none_err)
        c_bad = c_replay(bad_dir, errdump=bad_err)
        py_bad = python_replay_result(bad_dir)
        none_text = reporting_text(c_none)
        require_still_pad_ars(none_err, "C none ARS")
        require_errdump_not_written(bad_err, "unknown-aiding twin of the none directory")
        # Present barometer on none: published local height.
        # Dataset dump does not write that column; the YAML runner does.
        # No GNSS = no absolute position aiding, same duty as aiding none.
        # This contrast is not the C none process exit.
        match_yaml, match_sol = write_runner_mapping(
            ws,
            relpath="none-baro-match",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            pressure_unit="Pa",
            pressure_pa=p,
            include_gnss=False,
            include_mag=False,
            include_baro=True,
        )
        climb_yaml, climb_sol = write_runner_mapping(
            ws,
            relpath="none-baro-climb",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            pressure_unit="Pa",
            pressure_pa=p,
            pressure_after_s=3.0,
            pressure_after_pa=p_climb,
            include_gnss=False,
            include_mag=False,
            include_baro=True,
        )
        match_res, match_e = run_mapped_runner(match_yaml, match_sol)
        climb_res, climb_e = run_mapped_runner(climb_yaml, climb_sol)
        classified_non_full_runner(match_sol, match_res, "none-like matching pad")
        classified_non_full_runner(climb_sol, climb_res, "none-like climb pressure")
        h_match = runner_published_local_height_m(match_e, "none-like matching pad")
        h_climb = runner_published_local_height_m(climb_e, "none-like climb pressure")
        before = runner_last_at_or_before(climb_e, int((3.0 - 0.4) * 1.0e6))
        assert before.arb_height_m is not None, (
            "climb arm had no local height before the pressure drop"
        )
        h_before = before.arb_height_m
    require_nonzero_and_names(c_bad, UNKNOWN_AIDING)
    require_nonzero_and_names(py_bad, UNKNOWN_AIDING)
    print(f"c none rc={c_none.returncode} tail={none_text[-400:]!r}", flush=True)
    assert UNKNOWN_AIDING not in none_text, "none arm reused the unknown-aiding offender"
    assert reported_final_mode(py_none, "C-none python twin") != MODE_FULL, (
        "aiding none still reported FULL as the final suite mode"
    )
    # C none is a legal aiding value: ARS from this still pad is dumped.
    # Unknown aiding on the same streams returns before that dump. Scoring
    # may still be non-zero (INS never publishes scored epochs). Missing
    # baro stays a legal optional omit on python.
    assert py_none.returncode == 0, (
        f"python none with a present baro stream aborted: "
        f"{reporting_text(py_none)[-1200:]!r}"
    )
    assert py_nobaro.returncode == 0, (
        f"python none without a baro stream aborted: "
        f"{reporting_text(py_nobaro)[-1200:]!r}"
    )
    print(
        f"none-like local height match={h_match:.3f} before={h_before:.3f} "
        f"climb={h_climb:.3f} isa_dh={dh_isa:.3f}",
        flush=True,
    )
    assert abs(h_match) < 25.0, (
        f"matching pad pressure did not stay near the pad "
        f"(local height={h_match:.3f})"
    )
    assert abs(h_before) < 25.0, (
        f"climb arm was not near the pad before the pressure drop "
        f"(local height={h_before:.3f})"
    )
    assert (h_climb - h_before) * dh_isa > 0.0, (
        "climb-pressure local height is not the same sign as the ISA "
        f"altitude change (before={h_before:.3f} climb={h_climb:.3f} "
        f"isa_dh={dh_isa:.3f})"
    )
    assert h_climb > h_before, (
        "pressure drop did not raise published local height "
        f"(before={h_before:.3f} climb={h_climb:.3f})"
    )
    assert h_climb > h_match, (
        "matching-pad and climb-pressure local heights are indistinguishable "
        f"(match={h_match:.3f} climb={h_climb:.3f})"
    )


def test_unknown_aiding_exits_nonzero_and_names_offender():
    """aiding: not-a-mode exits non-zero and names that value."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="bad-aid",
            aiding=UNKNOWN_AIDING,
        )
        py = python_replay_result(dest)
        c_res = c_replay(dest)
    require_nonzero_and_names(py, UNKNOWN_AIDING)
    require_nonzero_and_names(c_res, UNKNOWN_AIDING)


def test_init_auto_and_ref_both_accepted():
    """init auto and init ref both run a legal GNSS-aided directory."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        auto_dir = write_replay_dataset(
            ws, lat_deg=lat, lon_deg=lon, h_m=h, relpath="init-auto", init="auto"
        )
        ref_dir = write_replay_dataset(
            ws, lat_deg=lat, lon_deg=lon, h_m=h, relpath="init-ref", init="ref"
        )
        s_auto = python_replay_series(auto_dir, ws.resolve("sol-ia.csv"))
        s_ref = python_replay_series(ref_dir, ws.resolve("sol-ir.csv"))
        c_auto = c_replay(auto_dir)
        c_ref = c_replay(ref_dir)
        imu_auto = imu_times_from_dataset(auto_dir)
        imu_ref = imu_times_from_dataset(ref_dir)
    series_near_llh(s_auto, lat, lon, h, what="init auto")
    series_near_llh(s_ref, lat, lon, h, what="init ref")
    series_covers_imu_log(s_auto, imu_auto)
    series_covers_imu_log(s_ref, imu_ref)
    assert c_auto.returncode == 0 and c_ref.returncode == 0, (
        f"C rejected an accepted init value: auto={c_auto.returncode} ref={c_ref.returncode}"
    )


def test_missing_imu_stream_fails():
    """missing IMU stream: the run does not succeed.

    Differential: the same directory with the IMU stream written runs on
    both harnesses, so the refusal is caused by the missing stream and not
    by anything else in the directory.
    """
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="no-imu",
            write_imu=False,
        )
        twin = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="with-imu",
        )
        py = python_replay_result(dest)
        c_res = c_replay(dest)
        py_twin = python_replay_series(twin, ws.resolve("sol-with-imu.csv"))
        c_twin = c_replay(twin)
    require_nonzero(py, "python missing IMU")
    require_nonzero(c_res, "C missing IMU")
    series_near_llh(py_twin, lat, lon, h, what="IMU-present twin")
    assert c_twin.returncode == 0, (
        f"C did not run the IMU-present twin: {reporting_text(c_twin)[-1200:]!r}"
    )


def test_missing_reference_trajectory_fails():
    """missing reference trajectory: the run does not succeed."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="no-ref",
            write_ref=False,
        )
        twin = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="with-ref",
        )
        py = python_replay_result(dest)
        c_res = c_replay(dest)
        py_twin = python_replay_series(twin, ws.resolve("sol-with-ref.csv"))
        c_twin = c_replay(twin)
    require_nonzero(py, "python missing reference")
    require_nonzero(c_res, "C missing reference")
    # Differential: the same directory with ref.csv written runs on both.
    series_near_llh(py_twin, lat, lon, h, what="reference-present twin")
    assert c_twin.returncode == 0, (
        f"C did not run the reference-present twin: {reporting_text(c_twin)[-1200:]!r}"
    )


def test_aiding_gnss_without_gnss_stream_exits_nonzero():
    """aiding: gnss without a GNSS stream exits non-zero."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gnss-aid-no-stream",
            aiding="gnss",
            write_gnss=False,
        )
        twin = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gnss-aid-with-stream",
            aiding="gnss",
            write_gnss=True,
        )
        py = python_replay_result(dest)
        c_res = c_replay(dest)
        py_twin = python_replay_series(twin, ws.resolve("sol-gnss-stream.csv"))
        c_twin = c_replay(twin)
    require_nonzero(py, "python gnss aiding without GNSS")
    require_nonzero(c_res, "C gnss aiding without GNSS")
    # Differential: the same directory with gnss.csv written runs on both.
    series_near_llh(py_twin, lat, lon, h, what="GNSS-present twin")
    assert c_twin.returncode == 0, (
        f"C did not run the GNSS-present twin: {reporting_text(c_twin)[-1200:]!r}"
    )


def test_unknown_config_key_exits_nonzero_and_names_offender():
    """unknown owned config.yaml key is refused and named."""
    lat, lon, h, _origin = _site()
    key = runtime_unknown_key("cfg")
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="unk-key",
            extra_top_key=key,
        )
        py = python_replay_result(dest)
        c_res = c_replay(dest)
    require_nonzero_and_names(py, key)
    require_nonzero_and_names(c_res, key)


def test_misspelled_imu_noise_key_aborts_before_score():
    """a misspelled IMU noise key aborts before a score."""
    lat, lon, h, _origin = _site()
    key = runtime_unknown_key("gyr")
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="imu-typo",
            extra_imu_key=key,
            lim_pos_rms_m=80.0,
        )
        py = python_replay_result(dest)
        c_res = c_replay(dest)
    require_nonzero_and_names(py, key)
    require_nonzero_and_names(c_res, key)
    assert c_res.returncode != 0, "C scored a dataset whose owned IMU section had a typo"


def test_required_imu_spectral_densities_present_or_zero_default():
    """required IMU densities must be written and positive; omit or 0 aborts."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        missing = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="psd-miss",
            omit_spectral=True,
        )
        zeroed = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="psd-zero",
            spectral_zero=True,
        )
        present = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="psd-pos",
        )
        py_miss = python_replay_result(missing)
        py_zero = python_replay_result(zeroed)
        series = python_replay_series(present, ws.resolve("sol-psd-pos.csv"))
        imu_times = imu_times_from_dataset(present)
        require_nonzero(py_miss, "python omitted IMU densities")
        require_nonzero(py_zero, "python wrote 0 for required IMU densities")
        series_covers_imu_log(series, imu_times)
        series_near_llh(series, lat, lon, h, what="positive written IMU densities")
        c_miss = c_replay(missing)
        c_zero = c_replay(zeroed)
        c_present = c_replay(present)
    require_nonzero(c_miss, "C omitted IMU densities")
    require_nonzero(c_zero, "C wrote 0 for required IMU densities")
    assert c_present.returncode == 0, (
        "positive written IMU densities did not let C run: "
        f"{reporting_text(c_present)[-1200:]!r}"
    )


# ---------------------------------------------------------------------------
# C. C scoring gate, comments, mixed rates
# ---------------------------------------------------------------------------


def test_c_harness_reads_configured_regression_limit():
    """same directory and error, only the limit number changes: loose 0, tight non-zero."""
    lat, lon, h, _origin = _site()
    north = _north_m()
    with workspace() as ws:
        loose = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="lim-loose",
            gnss_north_m=north,
            lim_pos_rms_m=80.0,
        )
        tight = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="lim-tight",
            gnss_north_m=north,
            lim_pos_rms_m=0.05,
        )
        py_loose = python_replay_series(loose, ws.resolve("sol-ll.csv"))
        c_loose = c_replay(loose)
        c_tight = c_replay(tight)
        imu_loose = imu_times_from_dataset(loose)
    series_covers_imu_log(py_loose, imu_loose)
    print(f"C limits loose={c_loose.returncode} tight={c_tight.returncode}", flush=True)
    assert c_loose.returncode == 0, (
        f"loose configured limit did not pass C: {reporting_text(c_loose)[-1200:]!r}"
    )
    assert c_tight.returncode != 0, (
        f"tight configured limit still passed C: {reporting_text(c_tight)[-1200:]!r}"
    )


def test_c_refuses_nonpositive_min_epoch_python_zero_default_still_solves():
    """C refuses a non-positive scoring minimum-epoch count; Python still writes a series."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        zeroed = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="min0",
            min_epochs=0,
        )
        omitted = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="min-omit",
            min_epochs=None,
        )
        positive = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="min-pos",
            min_epochs=2,
        )
        py0 = python_replay_series(zeroed, ws.resolve("sol-min0.csv"))
        py_omit = python_replay_series(omitted, ws.resolve("sol-mino.csv"))
        c0 = c_replay(zeroed)
        c_omit = c_replay(omitted)
        c_pos = c_replay(positive)
        imu_zeroed = imu_times_from_dataset(zeroed)
    series_near_llh(py0, lat, lon, h, what="python min_epochs=0")
    series_covers_imu_log(py0, imu_zeroed)
    series_near_llh(py_omit, lat, lon, h, what="python omitted min_epochs")
    require_nonzero(c0, "C min_epochs=0")
    require_nonzero(c_omit, "C omitted min_epochs")
    assert c_pos.returncode == 0, (
        f"C with a positive min-epoch count did not pass: "
        f"{reporting_text(c_pos)[-1200:]!r}"
    )


def test_comment_and_malformed_csv_lines_skipped():
    """comment and malformed rows are skipped; the series still covers the later motion."""
    lat, lon, h, origin = _site()
    north = _north_m()
    with workspace() as ws:
        dirty = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="junk",
            comment_and_junk=True,
            junk_then_north_m=north,
        )
        clean = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="clean",
            gnss_north_after_s=HAPPY_DURATION_S * 0.5,
            gnss_north_m=north,
        )
        s_dirty = python_replay_series(dirty, ws.resolve("sol-j.csv"))
        s_clean = python_replay_series(clean, ws.resolve("sol-c.csv"))
        imu_dirty = imu_times_from_dataset(dirty)
        imu_clean = imu_times_from_dataset(clean)
    series_covers_imu_log(s_dirty, imu_dirty)
    series_covers_imu_log(s_clean, imu_clean)
    later = llh_offset_north(lat, lon, h, north)
    series_near_llh(s_dirty, later[0], later[1], later[2], what="junk after later GNSS")
    span_d = s_dirty.points[-1].t_us - s_dirty.points[0].t_us
    span_c = s_clean.points[-1].t_us - s_clean.points[0].t_us
    print(f"junk span={span_d} clean span={span_c}", flush=True)
    assert span_d + span_d // 10 >= span_c, "junk rows truncated the solution span"
    last_dirty = ecef_from_llh_deg(
        s_dirty.points[-1].lat_deg, s_dirty.points[-1].lon_deg, s_dirty.points[-1].h_m
    )
    assert hypot3(last_dirty, origin) > 2.0, (
        "parser stopped at the junk row and never reached the later GNSS site"
    )


def test_mixed_sample_rates_allowed():
    """mixed sample rates are allowed; optional 10 Hz baro and two-column speed do not abort."""
    lat, lon, h, _origin = _site()
    p = tropospheric_isa_pressure_pa(h if h < 2000 else 120.0)
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="mixed-hz",
            write_baro=True,
            write_speed=True,
            baro_pa=p,
            baro_hz=10,
            speed_mps=0.0,
        )
        series = python_replay_series(dest, ws.resolve("sol-mix.csv"))
        c_res = c_replay(dest)
    series_near_llh(series, lat, lon, h, what="mixed-rate pad")
    assert c_res.returncode == 0, (
        f"C rejected mixed sample rates: {reporting_text(c_res)[-1200:]!r}"
    )


# ---------------------------------------------------------------------------
# D. YAML runner
# ---------------------------------------------------------------------------


def _runner_mag(lat, lon):
    ned = ned_field_from_independent_wmm(lat, lon, WMM_YEAR)
    return body_mag_for_yaw(0.0, 0.0, 0.0, ned), ned


def test_runner_mixed_unit_static_pad_full_near_gnss():
    """30 s mixed-unit IMU+GNSS pad writes FULL near the GNSS pad."""
    lat, lon, h, _origin = _site()
    mag, _ned = _runner_mag(lat, lon)
    p0 = tropospheric_isa_pressure_pa(150.0)
    n_imu = int(round(NAMED_PAD_S * IMU_HZ))
    with workspace() as ws:
        yaml_path, sol_path = write_runner_mapping(
            ws,
            relpath="mix30",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=NAMED_PAD_S,
            time_unit="s",
            gyro_unit="deg/s",
            accel_unit="m/s2",
            pressure_unit="hPa",
            mag_unit="mGauss",
            mag_frd=mag,
            pressure_pa=p0,
        )
        si_yaml, si_sol = write_runner_mapping(
            ws,
            relpath="mix30-si",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=NAMED_PAD_S,
            time_unit="s",
            gyro_unit="rad/s",
            accel_unit="m/s2",
            pressure_unit="Pa",
            mag_unit="uT",
            mag_frd=mag,
            pressure_pa=p0,
        )
        _res, epochs = run_mapped_runner(yaml_path, sol_path, timeout=DEFAULT_REPLAY_TIMEOUT)
        _si, si_epochs = run_mapped_runner(si_yaml, si_sol, timeout=DEFAULT_REPLAY_TIMEOUT)
    runner_tail_full_near(
        epochs, lat, lon, h, what="mixed 30 s pad", imu_count=n_imu
    )
    runner_tail_full_near(si_epochs, lat, lon, h, what="SI twin pad", imu_count=n_imu)


def test_runner_time_unit_span_not_row_clock():
    """runner time unit s/ms/µs; same row count, only the span reaches FULL."""
    lat, lon, h, _origin = _site()
    mag, _ned = _runner_mag(lat, lon)
    p = tropospheric_isa_pressure_pa(150.0)
    n = int(round(HAPPY_DURATION_S * IMU_HZ))
    with workspace() as ws:
        long_yaml, long_sol = write_runner_mapping(
            ws,
            relpath="run-span-s",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            time_unit="s",
            mag_frd=mag,
            pressure_pa=p,
        )
        short_yaml, short_sol = write_runner_mapping(
            ws,
            relpath="run-span-short",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=n * 0.0001,
            time_unit="s",
            n_imu=n,
            mag_frd=mag,
            pressure_pa=p,
        )
        _r, long_e = run_mapped_runner(long_yaml, long_sol)
        short_res = run_runner(short_yaml, timeout=DEFAULT_REPLAY_TIMEOUT)
        classified_non_full_runner(short_sol, short_res, "short seconds span")
        ms_same_yaml, ms_same_sol = write_runner_mapping(
            ws,
            relpath="run-span-ms-same",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            time_unit="ms",
            time_scale=1.0,
            mag_frd=mag,
            pressure_pa=p,
        )
        us_same_yaml, us_same_sol = write_runner_mapping(
            ws,
            relpath="run-span-us-same",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            time_unit="us",
            time_scale=1.0,
            mag_frd=mag,
            pressure_pa=p,
        )
        ms_same_res = run_runner(ms_same_yaml, timeout=DEFAULT_REPLAY_TIMEOUT)
        us_same_res = run_runner(us_same_yaml, timeout=DEFAULT_REPLAY_TIMEOUT)
        classified_non_full_runner(
            ms_same_sol, ms_same_res, "ms mapping of the same second counts"
        )
        classified_non_full_runner(
            us_same_sol, us_same_res, "us mapping of the same second counts"
        )
    runner_tail_full_near(long_e, lat, lon, h, what="time unit s", imu_count=n)


def test_runner_gyro_accel_unit_conversion():
    """gyro deg/s vs rad/s and accelerometer m/s² vs g change the converted quantity."""
    lat, lon, h, _origin = _site()
    dps = 12.0
    with workspace() as ws:
        deg_yaml, deg_sol = write_runner_mapping(
            ws,
            relpath="gyr-deg",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            gyro_unit="deg/s",
            gyro_z=dps,
            include_mag=False,
            include_baro=False,
        )
        rad_yaml, rad_sol = write_runner_mapping(
            ws,
            relpath="gyr-rad",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            gyro_unit="rad/s",
            gyro_z=math.radians(dps),
            include_mag=False,
            include_baro=False,
        )
        raw_yaml, raw_sol = write_runner_mapping(
            ws,
            relpath="gyr-raw",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            gyro_unit="rad/s",
            gyro_z=dps,
            include_mag=False,
            include_baro=False,
        )
        g_yaml, g_sol = write_runner_mapping(
            ws,
            relpath="acc-g",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            accel_unit="g",
            include_mag=False,
            include_baro=False,
        )
        si_yaml, si_sol = write_runner_mapping(
            ws,
            relpath="acc-si",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            accel_unit="m/s2",
            include_mag=False,
            include_baro=False,
        )
        raw_g_yaml, raw_g_sol = write_runner_mapping(
            ws,
            relpath="acc-raw-g",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            accel_unit="m/s2",
            acc_frd=(0.0, 0.0, -1.0),
            include_mag=False,
            include_baro=False,
        )
        _r, deg_e = run_mapped_runner(deg_yaml, deg_sol)
        _r, rad_e = run_mapped_runner(rad_yaml, rad_sol)
        _r, raw_e = run_mapped_runner(raw_yaml, raw_sol)
        _r, g_e = run_mapped_runner(g_yaml, g_sol)
        _r, si_e = run_mapped_runner(si_yaml, si_sol)
        _r, raw_g_e = run_mapped_runner(raw_g_yaml, raw_g_sol)
    runner_tail_full_near(deg_e, lat, lon, h, what="gyro deg/s")
    runner_tail_full_near(rad_e, lat, lon, h, what="gyro rad/s")
    runner_tail_full_near(g_e, lat, lon, h, what="accel g")
    runner_tail_full_near(si_e, lat, lon, h, what="accel m/s2")
    t0 = int(5.5 * 1.0e6)
    t1 = int(HAPPY_DURATION_S * 1.0e6)
    step_deg = mean_abs_yaw_step_deg(deg_e, t0, t1)
    step_rad = mean_abs_yaw_step_deg(rad_e, t0, t1)
    step_raw = mean_abs_yaw_step_deg(raw_e, t0, t1)
    print(
        f"gyro step deg={step_deg:.4f} rad={step_rad:.4f} unconverted={step_raw:.4f}",
        flush=True,
    )
    assert abs(step_deg - step_rad) < 0.05, (
        "deg/s and rad/s twins did not convert to the same yaw rate"
    )
    assert step_raw > 1.0, "unconverted deg/s counts still matched the converted yaw rate"
    roll_g = g_e[-1].roll_deg
    pitch_g = g_e[-1].pitch_deg
    roll_si = si_e[-1].roll_deg
    pitch_si = si_e[-1].pitch_deg
    roll_raw = raw_g_e[-1].roll_deg
    pitch_raw = raw_g_e[-1].pitch_deg
    assert None not in (roll_g, pitch_g, roll_si, pitch_si)
    tilt_g = abs(roll_g) + abs(pitch_g)
    tilt_si = abs(roll_si) + abs(pitch_si)
    print(
        f"g vs m/s2 tilt {tilt_g:.3f} {tilt_si:.3f} unconverted roll={roll_raw} pitch={pitch_raw}",
        flush=True,
    )
    assert tilt_g < 12.0 and tilt_si < 12.0, "g accelerometer was not a level pad"
    last_raw = raw_g_e[-1]
    last_si = si_e[-1]
    assert last_si.lat_deg is not None
    err_si = hypot3(
        ecef_from_llh_deg(last_si.lat_deg, last_si.lon_deg, last_si.h_m or h),
        ecef_from_llh_deg(lat, lon, h),
    )
    if last_raw.lat_deg is None:
        # Unconverted g counts (about 1 m/s^2 of specific force) are not a
        # still pad: publishing no position at all is one correct outcome.
        print(f"unconverted-g: no position published; SI pad err={err_si:.3f}", flush=True)
        return
    err_raw = hypot3(
        ecef_from_llh_deg(last_raw.lat_deg, last_raw.lon_deg, last_raw.h_m or h),
        ecef_from_llh_deg(lat, lon, h),
    )
    print(f"unconverted-g pad err={err_raw:.3f} SI={err_si:.3f}", flush=True)
    assert err_raw > 5.0 and err_raw > err_si + 5.0, (
        "unconverted g counts still stayed on the level pad"
    )


def test_runner_pressure_unit_tokens():
    """Pa / hPa / mbar / kPa are accepted; conversion matches a live climb, not local 0."""
    lat, lon, h, _origin = _site()
    p0 = tropospheric_isa_pressure_pa(150.0)
    p1 = tropospheric_isa_pressure_pa(350.0)
    climb_s = 12.0
    tokens = ("Pa", "hPa", "mbar", "kPa")
    climbs = {}
    with workspace() as ws:
        for token in tokens:
            yaml_path, sol_path = write_runner_mapping(
                ws,
                relpath=f"p-{token}",
                lat_deg=lat,
                lon_deg=lon,
                h_m=h,
                duration_s=NAMED_PAD_S,
                pressure_unit=token,
                pressure_pa=p0,
                pressure_after_s=climb_s,
                pressure_after_pa=p1,
                include_mag=False,
                disable_auto_zupt=True,
            )
            _r, epochs = run_mapped_runner(yaml_path, sol_path)
            full = [e for e in epochs if e.mode == MODE_FULL]
            assert full, f"pressure {token}: never published FULL"
            before = runner_last_at_or_before(epochs, int((climb_s - 0.4) * 1.0e6))
            after = epochs[-1]
            climbs[token] = _arb_climb(before, after, f"pressure {token}")
        raw_yaml, raw_sol = write_runner_mapping(
            ws,
            relpath="p-raw-hpa",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=NAMED_PAD_S,
            pressure_unit="Pa",
            pressure_pa=p0 * 0.01,
            pressure_after_s=climb_s,
            pressure_after_pa=p1 * 0.01,
            include_mag=False,
            disable_auto_zupt=True,
        )
        _r, raw_e = run_mapped_runner(raw_yaml, raw_sol)
        raw_full = [e for e in raw_e if e.mode == MODE_FULL]
        assert raw_full, "unconverted hPa: never published FULL"
        cut = int((climb_s - 0.4) * 1.0e6)
        raw_before = runner_last_at_or_before(raw_e, cut)
        raw_climb = _arb_climb(raw_before, raw_e[-1], "unconverted hPa counts")
    print(f"pressure arb climbs {climbs} unconverted-hPa={raw_climb:.3f}", flush=True)
    for token, value in climbs.items():
        assert value > 2.0, (
            f"{token} arbitrated height did not climb {value:.3f} after converted pressure drop "
            f"climbs={climbs} raw={raw_climb:.3f}"
        )
        assert abs(value - climbs["Pa"]) < 40.0, (
            f"{token} arb climb {value} is not in the Pa band {climbs['Pa']} climbs={climbs}"
        )
    assert abs(climbs["hPa"] - raw_climb) > 1.5, (
        f"unconverted hPa counts still matched converted Pa climb "
        f"hPa={climbs['hPa']:.3f} raw={raw_climb:.3f} climbs={climbs}"
    )


def test_runner_mag_unit_tokens():
    """mag tokens µT/gauss/mGauss/nT are accepted; FULL rows carry named NED.

    Milligauss-scale conversion onto the microtesla convention is stated but
    not scored on those named columns; do not restore a heading split.
    """
    lat, lon, h, _origin = _site()
    north = _north_m()
    mag, _ned = _runner_mag(lat, lon)
    jump_s = 6.0
    vn = 1.2
    tokens = ("uT", "gauss", "mGauss", "nT")
    with workspace() as ws:
        for token in tokens:
            yaml_path, sol_path = write_runner_mapping(
                ws,
                relpath=f"mag-{token}",
                lat_deg=lat,
                lon_deg=lon,
                h_m=h,
                duration_s=HAPPY_DURATION_S,
                mag_unit=token,
                mag_frd=mag,
                include_baro=False,
                disable_auto_zupt=True,
            )
            _r, epochs = run_mapped_runner(yaml_path, sol_path)
            runner_tail_full_near(epochs, lat, lon, h, what=f"mag {token}")
            full = [e for e in epochs if e.mode == MODE_FULL and e.yaw_deg is not None]
            assert full, f"mag {token}: no FULL yaw"
        ned_yaml, ned_sol = write_runner_mapping(
            ws,
            relpath="mag-ned-cols",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            mag_unit="mGauss",
            mag_frd=mag,
            include_baro=False,
            disable_auto_zupt=True,
            gnss_north_after_s=jump_s,
            gnss_north_m=north,
            gnss_vel_ned=(vn, 0.0, 0.0),
        )
        _r, ned_e = run_mapped_runner(ned_yaml, ned_sol)
        runner_tail_full_near(
            ned_e, *llh_offset_north(lat, lon, h, north), what="mGauss NED columns"
        )
        full = [e for e in ned_e if e.mode == MODE_FULL]
        assert full, "mGauss NED mapping wrote no FULL row"
        last = full[-1]
        assert last.ned_pos is not None and last.ned_vel is not None, (
            "FULL row is missing NED position or NED velocity"
        )
        pos, vel = last.ned_pos, last.ned_vel
    print(f"mGauss FULL NED pos={pos} vel={vel} north={north} vn={vn}", flush=True)
    assert abs(pos[0]) > 2.0, (
        f"FULL NED-north was unused (pos={pos}); GNSS north jump {north} m was not published"
    )
    assert abs(pos[0]) > abs(pos[1]), (
        f"FULL NED position did not follow the north GNSS jump pos={pos}"
    )
    assert abs(vel[0]) > 0.3, (
        f"FULL NED-north velocity was unused (vel={vel}); GNSS vn={vn} was not published"
    )
    assert abs(vel[0]) > abs(vel[1]), (
        f"FULL NED velocity did not follow GNSS north speed vel={vel}"
    )


def test_runner_gnss_geodetic_radians_and_ecef():
    """GNSS geodetic degrees, radians, and ECEF; unconverted radians would sit near (0,0)."""
    lat, lon, h, origin = _site()
    mag, _ned = _runner_mag(lat, lon)
    p = tropospheric_isa_pressure_pa(150.0)
    with workspace() as ws:
        deg_yaml, deg_sol = write_runner_mapping(
            ws,
            relpath="gnss-deg",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            gnss_format="llh_deg",
            mag_frd=mag,
            pressure_pa=p,
        )
        rad_yaml, rad_sol = write_runner_mapping(
            ws,
            relpath="gnss-rad",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            gnss_format="llh_rad",
            mag_frd=mag,
            pressure_pa=p,
        )
        ecef_yaml, ecef_sol = write_runner_mapping(
            ws,
            relpath="gnss-ecef",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            gnss_format="ecef",
            mag_frd=mag,
            pressure_pa=p,
        )
        _r, deg_e = run_mapped_runner(deg_yaml, deg_sol)
        _r, rad_e = run_mapped_runner(rad_yaml, rad_sol)
        _r, ecef_e = run_mapped_runner(ecef_yaml, ecef_sol)
    runner_tail_full_near(deg_e, lat, lon, h, what="gnss llh_deg")
    runner_tail_full_near(rad_e, lat, lon, h, what="gnss llh_rad")
    runner_tail_full_near(ecef_e, lat, lon, h, what="gnss ecef")
    zero = ecef_from_llh_deg(0.0, 0.0, 0.0)
    last_rad = ecef_from_llh_deg(rad_e[-1].lat_deg, rad_e[-1].lon_deg, rad_e[-1].h_m)
    print(f"radians arm vs pad={hypot3(last_rad, origin):.3f} vs (0,0)={hypot3(last_rad, zero):.3f}", flush=True)
    assert hypot3(last_rad, origin) + 1000.0 < hypot3(last_rad, zero), (
        "radians GNSS was read as degrees and sat near (0,0) instead of the pad"
    )


def test_runner_column_mapping_follows_yaml():
    """column mapping follows the YAML, not a fixed tutorial layout."""
    lat, lon, h, _origin = _site()
    mag, _ned = _runner_mag(lat, lon)
    p = tropospheric_isa_pressure_pa(150.0)
    n = int(round(HAPPY_DURATION_S * IMU_HZ))
    with workspace() as ws:
        plain_yaml, plain_sol = write_runner_mapping(
            ws,
            relpath="map-plain",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            mag_frd=mag,
            pressure_pa=p,
        )
        swap_yaml, swap_sol = write_runner_mapping(
            ws,
            relpath="map-swap",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            mag_frd=mag,
            pressure_pa=p,
            swap_time_lat=True,
            swap_time_gyro=True,
        )
        _r, plain_e = run_mapped_runner(plain_yaml, plain_sol)
        _r, swap_e = run_mapped_runner(swap_yaml, swap_sol)
    runner_tail_full_near(plain_e, lat, lon, h, what="mapped default columns", imu_count=n)
    runner_tail_full_near(swap_e, lat, lon, h, what="mapped swapped columns", imu_count=n)


def test_runner_merges_latest_sample_at_or_before_imu_epoch():
    """IMU begins the epoch; the latest GNSS at or before t is attached, not the next.

    Differential against a twin whose GNSS never jumps: every epoch before the
    jump must be the twin's epoch (a later sample was not attached early), and
    the epochs after it must sit nearer the new fix than the twin's do. How far
    one fused jump moves the solution is not scored.
    """
    lat, lon, h, origin = _site()
    mag, _ned = _runner_mag(lat, lon)
    p = tropospheric_isa_pressure_pa(150.0)
    north = _north_m()
    # First fix at 0.5 s + 5 s entry dwell + 1.5 s ready wait (PRD /
    # PRD): published by 7 s under any reading of the dwell boundary. The
    # jump sits on a later 1 Hz fix.
    jump_s = 9.5
    duration_s = jump_s + 2.5
    with workspace() as ws:
        yaml_path, sol_path = write_runner_mapping(
            ws,
            relpath="merge",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=duration_s,
            mag_frd=mag,
            pressure_pa=p,
            gnss_north_after_s=jump_s,
            gnss_north_m=north,
        )
        twin_yaml, twin_sol = write_runner_mapping(
            ws,
            relpath="merge-twin",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=duration_s,
            mag_frd=mag,
            pressure_pa=p,
        )
        _r, epochs = run_mapped_runner(yaml_path, sol_path)
        _t, twin = run_mapped_runner(twin_yaml, twin_sol)
    jump_us = int(round(jump_s * 1.0e6))

    def _ecef(e):
        return ecef_from_llh_deg(e.lat_deg, e.lon_deg, e.h_m if e.h_m is not None else h)

    twin_by_t = {e.t_us: e for e in twin if e.lat_deg is not None}
    early = [e for e in epochs if e.t_us < jump_us and e.lat_deg is not None]
    paired = [(e, twin_by_t[e.t_us]) for e in early if e.t_us in twin_by_t]
    assert len(paired) >= 50, (
        f"too few published epochs before the jump to compare with the twin ({len(paired)})"
    )
    worst = max(hypot3(_ecef(e), _ecef(t)) for e, t in paired)
    before = runner_last_at_or_before(epochs, jump_us - 200_000)
    after = runner_last_at_or_before(epochs, jump_us + 1_200_000)
    twin_after = runner_last_at_or_before(twin, jump_us + 1_200_000)
    assert before.lat_deg is not None and after.lat_deg is not None
    assert twin_after.lat_deg is not None
    later = ecef_from_llh_deg(*llh_offset_north(lat, lon, h, north))
    d_after = hypot3(_ecef(after), later)
    d_twin = hypot3(_ecef(twin_after), later)
    print(
        f"merge pre-jump max diff vs twin={worst:.6f} m over n={len(paired)}; "
        f"before vs pad={hypot3(_ecef(before), origin):.3f} "
        f"after vs new={d_after:.3f} twin-after vs new={d_twin:.3f}",
        flush=True,
    )
    assert worst < 1.0e-3, (
        "an epoch before the GNSS jump differs from the no-jump twin: a later "
        f"sample was attached early (max {worst:.4f} m)"
    )
    assert hypot3(_ecef(before), origin) + 1.0 < hypot3(_ecef(before), later), (
        "epoch before the GNSS jump was closer to the new fix than to the old pad"
    )
    assert d_after + 0.1 < d_twin, (
        "epochs after the GNSS jump were not pulled toward the new fix "
        f"relative to the no-jump twin ({d_after:.3f} vs {d_twin:.3f} m)"
    )


def test_magnetometer_optional_directory_still_runs():
    """both harnesses require IMU and the reference; magnetometer is optional."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="no-mag",
            write_mag=False,
        )
        assert not (dest / "mag.csv").is_file(), "fixture accidentally wrote mag.csv"
        series = python_replay_series(dest, ws.resolve("sol-no-mag.csv"))
        c_res = c_replay(dest)
        imu_times = imu_times_from_dataset(dest)
    series_covers_imu_log(series, imu_times)
    series_near_llh(series, lat, lon, h, what="no mag.csv")
    report_names_mode(series.result, MODE_FULL, "no mag.csv")
    print(f"no mag.csv python n={len(series.points)} c rc={c_res.returncode}", flush=True)
    assert c_res.returncode == 0, (
        f"C harness aborted a legal directory with no mag.csv: "
        f"{reporting_text(c_res)[-1200:]!r}"
    )


def test_ref_csv_geodetic_attitude_ned_velocity_consumed():
    """ref.csv lat/lon/height m, roll/pitch/yaw deg, and NED velocity are the reference."""
    lat, lon, h, origin = _site()
    with workspace() as ws:
        match = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-match",
            extra_imu_s=2.0,
            score_attitude=1,
            lim_att_bias_deg=45.0,
        )
        high = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-high",
            ref_h_m=h + 80.0,
            lim_pos_rms_m=5.0,
            score_attitude=0,
        )
        high_loose = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-high-loose",
            extra_imu_s=2.0,
            ref_h_m=h + 80.0,
            lim_pos_rms_m=200.0,
            score_attitude=0,
        )
        north_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-north",
            ref_ned_m=(80.0, 0.0, 0.0),
            lim_pos_rms_m=5.0,
            score_attitude=0,
        )
        north_loose = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-north-loose",
            extra_imu_s=2.0,
            ref_ned_m=(80.0, 0.0, 0.0),
            lim_pos_rms_m=200.0,
            score_attitude=0,
        )
        east_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-east",
            ref_ned_m=(0.0, 80.0, 0.0),
            lim_pos_rms_m=5.0,
            score_attitude=0,
        )
        east_loose = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-east-loose",
            extra_imu_s=2.0,
            ref_ned_m=(0.0, 80.0, 0.0),
            lim_pos_rms_m=200.0,
            score_attitude=0,
        )
        tilted = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-tilt",
            ref_rpy_deg=(40.0, 0.0, 0.0),
            score_attitude=1,
            lim_att_bias_deg=5.0,
            lim_yaw_bias_deg=45.0,
        )
        pitched = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-pitch",
            ref_rpy_deg=(0.0, 40.0, 0.0),
            score_attitude=1,
            lim_att_bias_deg=5.0,
            lim_yaw_bias_deg=45.0,
        )
        yawed = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-yaw",
            ref_rpy_deg=(0.0, 0.0, 40.0),
            score_attitude=1,
            lim_att_bias_deg=45.0,
            lim_yaw_bias_deg=5.0,
        )
        vel_ref = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-vel",
            ref_vel_ned=(6.0, 0.0, 0.0),
        )
        aid_vn = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-aid-vn",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
            ref_vel_ned=(4.0, 0.0, 0.0),
        )
        aid_ve = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-aid-ve",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
            ref_vel_ned=(0.0, 4.0, 0.0),
        )
        aid_vd = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="ref-aid-vd",
            aiding="ref",
            write_gnss=False,
            pos_fallback_m=(2.0, 3.0),
            vel_fallback_mps=0.25,
            ref_vel_ned=(0.0, 0.0, 4.0),
        )
        match_series = python_replay_series(match, ws.resolve("sol-ref-match.csv"))
        vel_series = python_replay_series(vel_ref, ws.resolve("sol-ref-vel.csv"))
        s_vn = python_replay_series(aid_vn, ws.resolve("sol-aid-vn.csv"))
        s_ve = python_replay_series(aid_ve, ws.resolve("sol-aid-ve.csv"))
        s_vd = python_replay_series(aid_vd, ws.resolve("sol-aid-vd.csv"))
        c_match = c_replay(match)
        c_high = c_replay(high)
        c_high_loose = c_replay(high_loose)
        c_north = c_replay(north_off)
        c_north_loose = c_replay(north_loose)
        c_east = c_replay(east_off)
        c_east_loose = c_replay(east_loose)
        c_tilt = c_replay(tilted)
        c_pitch = c_replay(pitched)
        c_yaw = c_replay(yawed)
        c_vn = c_replay(aid_vn)
        c_ve = c_replay(aid_ve)
        c_vd = c_replay(aid_vd)
    series_near_llh(match_series, lat, lon, h, what="matching reference")
    print(
        f"ref C match={c_match.returncode} high={c_high.returncode} "
        f"high_loose={c_high_loose.returncode} north={c_north.returncode} "
        f"north_loose={c_north_loose.returncode} east={c_east.returncode} "
        f"east_loose={c_east_loose.returncode} tilt={c_tilt.returncode} "
        f"pitch={c_pitch.returncode} yaw={c_yaw.returncode} "
        f"aid_vn={c_vn.returncode} aid_ve={c_ve.returncode} aid_vd={c_vd.returncode}",
        flush=True,
    )
    assert c_match.returncode == 0, (
        f"C rejected a matching geodetic/attitude reference: "
        f"{reporting_text(c_match)[-1200:]!r}"
    )
    assert c_high.returncode != 0, (
        "C still passed when ref.csv height was 80 m off the fused height"
    )
    assert c_high_loose.returncode == 0, (
        f"C failed the same height-offset directory under a loose position limit: "
        f"{reporting_text(c_high_loose)[-1200:]!r}"
    )
    assert c_north.returncode != 0, (
        "C still passed when ref.csv latitude was 80 m north of the fused position"
    )
    assert c_north_loose.returncode == 0, (
        f"C failed the same latitude-offset directory under a loose position limit: "
        f"{reporting_text(c_north_loose)[-1200:]!r}"
    )
    assert c_east.returncode != 0, (
        "C still passed when ref.csv longitude was 80 m east of the fused position"
    )
    assert c_east_loose.returncode == 0, (
        f"C failed the same longitude-offset directory under a loose position limit: "
        f"{reporting_text(c_east_loose)[-1200:]!r}"
    )
    assert c_tilt.returncode != 0, (
        "C still passed when ref.csv roll was 40 deg off a level IMU"
    )
    assert c_pitch.returncode != 0, (
        "C still passed when ref.csv pitch was 40 deg off a level IMU"
    )
    assert c_yaw.returncode != 0, (
        "C still passed when ref.csv yaw was 40 deg off a level IMU"
    )
    last_v = vel_series.points[-1].vel_ned
    assert last_v is not None, "dump has no NED velocity"
    print(f"fused vel vs ref-copied 6 m/s north: {last_v}", flush=True)
    assert abs(last_v[0]) < 2.0, "fused north velocity copied the 6 m/s reference column"
    assert abs(last_v[1]) < 2.0, "fused east velocity is not a stationary pad"
    vn_last = s_vn.points[-1].vel_ned
    ve_last = s_ve.points[-1].vel_ned
    vd_last = s_vd.points[-1].vel_ned
    assert vn_last is not None and ve_last is not None and vd_last is not None
    print(f"aiding-ref synthesized vel N={vn_last} E={ve_last} D={vd_last}", flush=True)
    assert abs(vn_last[0]) > abs(ve_last[0]), (
        "aiding ref did not consume ref.csv north velocity as the synthesized fix"
    )
    assert abs(ve_last[1]) > abs(vn_last[1]), (
        "aiding ref did not consume ref.csv east velocity as the synthesized fix"
    )
    assert abs(vd_last[2]) > abs(vn_last[2]), (
        "aiding ref did not consume ref.csv down velocity as the synthesized fix"
    )
    assert c_vn.returncode == 0 and c_ve.returncode == 0 and c_vd.returncode == 0, (
        f"C aborted aiding-ref velocity directories: "
        f"{c_vn.returncode} {c_ve.returncode} {c_vd.returncode}"
    )


def test_gnss_packed_covariance_velocity_and_valid_flag():
    """gnss.csv packed NED pos/vel covariance order, NED velocity, and vel_ok."""
    lat, lon, h, origin = _site()
    north = _north_m()
    east = _east_m()
    gnss_llh = llh_offset_north(lat, lon, h, north)
    gnss_ecef = ecef_from_llh_deg(*gnss_llh)
    ne_llh = llh_offset_ned(lat, lon, h, north, east, 0.0)
    nd_llh = llh_offset_ned(lat, lon, h, north, 0.0, 12.0)
    ed_llh = llh_offset_ned(lat, lon, h, 0.0, east, 12.0)
    dd_llh = llh_offset_ned(lat, lon, h, 0.0, 0.0, 12.0)
    with workspace() as ws:
        tight_n = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-nn",
            gnss_north_m=north,
            gnss_north_after_s=7.0,
            pos_cov6=(0.25, 0.0, 0.0, 4.0, 0.0, 4.0),
        )
        tight_e = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-ee",
            gnss_north_m=north,
            gnss_north_after_s=7.0,
            pos_cov6=(4.0, 0.0, 0.0, 0.25, 0.0, 4.0),
        )
        vn = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="vel-n",
            gnss_vel_ned=(2.0, 0.0, 0.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
        )
        ve = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="vel-e",
            gnss_vel_ned=(0.0, 2.0, 0.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
        )
        vn_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="vel-off",
            gnss_vel_ned=(2.0, 0.0, 0.0),
            vel_ok=0,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
        )
        ne_on = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-ne",
            gnss_ned_m=(north, 0.0, 0.0),
            gnss_north_after_s=7.0,
            pos_cov6=(4.0, 3.5, 0.0, 4.0, 0.0, 4.0),
        )
        ne_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-ne0",
            gnss_ned_m=(north, 0.0, 0.0),
            gnss_north_after_s=7.0,
            pos_cov6=(4.0, 0.0, 0.0, 4.0, 0.0, 4.0),
        )
        nd_on = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-nd",
            gnss_ned_m=(north, 0.0, 0.0),
            gnss_north_after_s=7.0,
            pos_cov6=(4.0, 0.0, 3.5, 4.0, 0.0, 4.0),
        )
        nd_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-nd0",
            gnss_ned_m=(north, 0.0, 0.0),
            gnss_north_after_s=7.0,
            pos_cov6=(4.0, 0.0, 0.0, 4.0, 0.0, 4.0),
        )
        ed_on = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-ed",
            gnss_ned_m=(0.0, east, 0.0),
            gnss_north_after_s=7.0,
            pos_cov6=(4.0, 0.0, 0.0, 4.0, 3.5, 4.0),
        )
        ed_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-ed0",
            gnss_ned_m=(0.0, east, 0.0),
            gnss_north_after_s=7.0,
            pos_cov6=(4.0, 0.0, 0.0, 4.0, 0.0, 4.0),
        )
        tight_dd = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-dd",
            gnss_ned_m=(0.0, 0.0, 12.0),
            gnss_north_after_s=7.0,
            pos_cov6=(4.0, 0.0, 0.0, 4.0, 0.0, 0.25),
        )
        tight_nn_h = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="cov-nn-h",
            gnss_ned_m=(0.0, 0.0, 12.0),
            gnss_north_after_s=7.0,
            pos_cov6=(0.25, 0.0, 0.0, 4.0, 0.0, 4.0),
        )
        # Packed vel nn/ee under the 3D entry velocity 1-sigma are both
        # so tight that a 2 m/s north sample is fused fully either way.
        # Enter with isotropic 0.04, then after FULL swap a tight 0.01
        # north slot against a 4 (m/s)^2 east slot (and the reverse).
        vel_nn = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-nn",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(2.0, 0.0, 0.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(0.01, 0.0, 0.0, 4.0, 0.0, 0.04),
        )
        vel_ee = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-ee",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(2.0, 0.0, 0.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(4.0, 0.0, 0.0, 0.01, 0.0, 0.04),
        )
        iso_lat = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gnss-lat",
            gnss_ned_m=(north, 0.0, 0.0),
        )
        iso_lon = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gnss-lon",
            gnss_ned_m=(0.0, east, 0.0),
        )
        iso_h = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gnss-h",
            gnss_ned_m=(0.0, 0.0, 12.0),
        )
        vd = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="vel-d",
            gnss_vel_ned=(0.0, 0.0, 2.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
        )
        vel_ne_on = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-ne",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(2.0, 2.0, 0.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(0.04, 0.03, 0.0, 0.04, 0.0, 0.04),
        )
        vel_ne_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-ne0",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(2.0, 2.0, 0.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
        )
        vel_nd_on = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-nd",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(2.0, 0.0, 2.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(0.04, 0.0, 0.03, 0.04, 0.0, 0.04),
        )
        vel_nd_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-nd0",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(2.0, 0.0, 2.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
        )
        vel_ed_on = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-ed",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(0.0, 2.0, 2.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(0.04, 0.0, 0.0, 0.04, 0.03, 0.04),
        )
        vel_ed_off = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-ed0",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(0.0, 2.0, 2.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
        )
        vel_dd = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-dd",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(0.0, 0.0, 2.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(4.0, 0.0, 0.0, 4.0, 0.0, 0.01),
        )
        vel_dd_nn = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="velcov-dd-nn",
            gnss_vel_ned=(0.0, 0.0, 0.0),
            gnss_vel_after_s=6.0,
            gnss_vel_after_ned=(0.0, 0.0, 2.0),
            vel_ok=1,
            vel_cov6=(0.04, 0.0, 0.0, 0.04, 0.0, 0.04),
            vel_cov_after_s=7.0,
            vel_cov_after6=(0.01, 0.0, 0.0, 4.0, 0.0, 4.0),
        )
        s_nn = python_replay_series(tight_n, ws.resolve("sol-nn.csv"))
        s_ee = python_replay_series(tight_e, ws.resolve("sol-ee.csv"))
        s_vn = python_replay_series(vn, ws.resolve("sol-vn.csv"))
        s_ve = python_replay_series(ve, ws.resolve("sol-ve.csv"))
        s_off = python_replay_series(vn_off, ws.resolve("sol-voff.csv"))
        s_ne = python_replay_series(ne_on, ws.resolve("sol-ne.csv"))
        s_ne0 = python_replay_series(ne_off, ws.resolve("sol-ne0.csv"))
        s_nd = python_replay_series(nd_on, ws.resolve("sol-nd.csv"))
        s_nd0 = python_replay_series(nd_off, ws.resolve("sol-nd0.csv"))
        s_ed = python_replay_series(ed_on, ws.resolve("sol-ed.csv"))
        s_ed0 = python_replay_series(ed_off, ws.resolve("sol-ed0.csv"))
        s_dd = python_replay_series(tight_dd, ws.resolve("sol-dd.csv"))
        s_nnh = python_replay_series(tight_nn_h, ws.resolve("sol-nnh.csv"))
        s_vcn = python_replay_series(vel_nn, ws.resolve("sol-vcn.csv"))
        s_vce = python_replay_series(vel_ee, ws.resolve("sol-vce.csv"))
        s_lat = python_replay_series(iso_lat, ws.resolve("sol-glat.csv"))
        s_lon = python_replay_series(iso_lon, ws.resolve("sol-glon.csv"))
        s_hgt = python_replay_series(iso_h, ws.resolve("sol-gh.csv"))
        s_vd = python_replay_series(vd, ws.resolve("sol-vd.csv"))
        s_vne = python_replay_series(vel_ne_on, ws.resolve("sol-vne.csv"))
        s_vne0 = python_replay_series(vel_ne_off, ws.resolve("sol-vne0.csv"))
        s_vnd = python_replay_series(vel_nd_on, ws.resolve("sol-vnd.csv"))
        s_vnd0 = python_replay_series(vel_nd_off, ws.resolve("sol-vnd0.csv"))
        s_ved = python_replay_series(vel_ed_on, ws.resolve("sol-ved.csv"))
        s_ved0 = python_replay_series(vel_ed_off, ws.resolve("sol-ved0.csv"))
        s_vdd = python_replay_series(vel_dd, ws.resolve("sol-vdd.csv"))
        s_vddn = python_replay_series(vel_dd_nn, ws.resolve("sol-vddn.csv"))
    last_nn = ecef_from_llh_deg(s_nn.points[-1].lat_deg, s_nn.points[-1].lon_deg, s_nn.points[-1].h_m)
    last_ee = ecef_from_llh_deg(s_ee.points[-1].lat_deg, s_ee.points[-1].lon_deg, s_ee.points[-1].h_m)
    d_nn = hypot3(last_nn, gnss_ecef)
    d_ee = hypot3(last_ee, gnss_ecef)
    vn_last = s_vn.points[-1].vel_ned
    ve_last = s_ve.points[-1].vel_ned
    off_last = s_off.points[-1].vel_ned
    assert vn_last is not None and ve_last is not None
    assert off_last is not None
    ne_last = ecef_from_llh_deg(s_ne.points[-1].lat_deg, s_ne.points[-1].lon_deg, s_ne.points[-1].h_m)
    ne0_last = ecef_from_llh_deg(
        s_ne0.points[-1].lat_deg, s_ne0.points[-1].lon_deg, s_ne0.points[-1].h_m
    )
    d_ne_pair = hypot3(ne_last, ne0_last)
    nd_last = ecef_from_llh_deg(s_nd.points[-1].lat_deg, s_nd.points[-1].lon_deg, s_nd.points[-1].h_m)
    nd0_last = ecef_from_llh_deg(
        s_nd0.points[-1].lat_deg, s_nd0.points[-1].lon_deg, s_nd0.points[-1].h_m
    )
    d_nd_pair = hypot3(nd_last, nd0_last)
    dh_nd = abs(s_nd.points[-1].h_m - s_nd0.points[-1].h_m)
    ed_last = ecef_from_llh_deg(s_ed.points[-1].lat_deg, s_ed.points[-1].lon_deg, s_ed.points[-1].h_m)
    ed0_last = ecef_from_llh_deg(
        s_ed0.points[-1].lat_deg, s_ed0.points[-1].lon_deg, s_ed0.points[-1].h_m
    )
    d_ed_pair = hypot3(ed_last, ed0_last)
    dh_ed = abs(s_ed.points[-1].h_m - s_ed0.points[-1].h_m)
    dd_ecef = ecef_from_llh_deg(*dd_llh)
    d_dd = hypot3(
        ecef_from_llh_deg(s_dd.points[-1].lat_deg, s_dd.points[-1].lon_deg, s_dd.points[-1].h_m),
        dd_ecef,
    )
    d_nnh = hypot3(
        ecef_from_llh_deg(s_nnh.points[-1].lat_deg, s_nnh.points[-1].lon_deg, s_nnh.points[-1].h_m),
        dd_ecef,
    )
    vcn = s_vcn.points[-1].vel_ned
    vce = s_vce.points[-1].vel_ned
    assert vcn is not None and vce is not None
    print(
        f"packed nn={d_nn:.4f} ee={d_ee:.4f} NE={d_ne_pair:.4f} "
        f"ND={d_nd_pair:.4f}/{dh_nd:.4f} ED={d_ed_pair:.4f}/{dh_ed:.4f} "
        f"DD={d_dd:.4f} NNh={d_nnh:.4f} velN={vn_last} velE={ve_last} "
        f"vel_ok0={off_last} vcovN={vcn} vcovE={vce}",
        flush=True,
    )
    assert d_nn < d_ee, (
        f"swapping packed pos nn/ee did not change pull nn={d_nn:.3f} ee={d_ee:.3f}"
    )
    assert abs(vn_last[0]) > abs(ve_last[0]), "north GNSS velocity was not consumed"
    assert abs(ve_last[1]) > abs(vn_last[1]), "east GNSS velocity was not consumed"
    assert abs(vn_last[0]) > abs(off_last[0]), (
        "velocity-valid flag 0 still fused the same north speed as flag 1"
    )
    assert d_ne_pair > 1.0e-3, (
        f"packed north-east covariance slot did not change the solution ({d_ne_pair:.4f} m)"
    )
    assert d_nd_pair > 1.0e-3 or dh_nd > 1.0e-3, (
        f"packed north-down covariance slot did not change the solution "
        f"({d_nd_pair:.4f} m dh={dh_nd:.4f})"
    )
    assert d_ed_pair > 1.0e-3 or dh_ed > 1.0e-3, (
        f"packed east-down covariance slot did not change the solution "
        f"({d_ed_pair:.4f} m dh={dh_ed:.4f})"
    )
    assert d_dd < d_nnh, (
        f"swapping packed pos dd/nn did not change height pull dd={d_dd:.3f} nn={d_nnh:.3f}"
    )
    # The tight north slot must hold north velocity nearer the measured 2 m/s
    # than the loose one does. (Position fixes stay on the pad, so how a loose
    # velocity arm resolves that conflict -- lagging below or overshooting
    # above 2 m/s -- depends on tuning; distance to the measurement does not.)
    v_meas = 2.0
    assert abs(vcn[0] - v_meas) + 0.05 < abs(vce[0] - v_meas), (
        "swapping packed velocity nn/ee did not change north-velocity pull "
        f"(tight-north {vcn[0]:.3f}, loose-north {vce[0]:.3f} vs {v_meas} m/s)"
    )
    lat_ecef = ecef_from_llh_deg(*gnss_llh)
    lon_llh = llh_offset_ned(lat, lon, h, 0.0, east, 0.0)
    lon_ecef = ecef_from_llh_deg(*lon_llh)
    last_lat = ecef_from_llh_deg(
        s_lat.points[-1].lat_deg, s_lat.points[-1].lon_deg, s_lat.points[-1].h_m
    )
    last_lon = ecef_from_llh_deg(
        s_lon.points[-1].lat_deg, s_lon.points[-1].lon_deg, s_lon.points[-1].h_m
    )
    last_hgt = ecef_from_llh_deg(
        s_hgt.points[-1].lat_deg, s_hgt.points[-1].lon_deg, s_hgt.points[-1].h_m
    )
    d_lat_to_lat = hypot3(last_lat, lat_ecef)
    d_lon_to_lat = hypot3(last_lon, lat_ecef)
    d_lon_to_lon = hypot3(last_lon, lon_ecef)
    d_lat_to_lon = hypot3(last_lat, lon_ecef)
    d_h_to_h = hypot3(last_hgt, ecef_from_llh_deg(*dd_llh))
    d_lat_to_h = hypot3(last_lat, ecef_from_llh_deg(*dd_llh))
    vd_last = s_vd.points[-1].vel_ned
    assert vd_last is not None
    vne = s_vne.points[-1].vel_ned
    vne0 = s_vne0.points[-1].vel_ned
    vnd = s_vnd.points[-1].vel_ned
    vnd0 = s_vnd0.points[-1].vel_ned
    ved = s_ved.points[-1].vel_ned
    ved0 = s_ved0.points[-1].vel_ned
    vdd = s_vdd.points[-1].vel_ned
    vddn = s_vddn.points[-1].vel_ned
    assert vne is not None and vne0 is not None
    assert vnd is not None and vnd0 is not None
    assert ved is not None and ved0 is not None
    assert vdd is not None and vddn is not None
    dve_ne = math.hypot(vne[0] - vne0[0], vne[1] - vne0[1])
    dve_nd = math.hypot(vnd[0] - vnd0[0], vnd[2] - vnd0[2])
    dve_ed = math.hypot(ved[1] - ved0[1], ved[2] - ved0[2])
    print(
        f"gnss lat/lon/h dlat={d_lat_to_lat:.3f}/{d_lon_to_lat:.3f} "
        f"dlon={d_lon_to_lon:.3f}/{d_lat_to_lon:.3f} "
        f"dh={d_h_to_h:.3f}/{d_lat_to_h:.3f} vd={vd_last} "
        f"velNE={dve_ne:.4f} velND={dve_nd:.4f} velED={dve_ed:.4f} "
        f"velDD={vdd[2]:.3f}/{vddn[2]:.3f}",
        flush=True,
    )
    assert d_lat_to_lat < d_lon_to_lat, (
        "gnss.csv latitude was unused as GNSS position "
        f"(north-site {d_lat_to_lat:.3f} vs east-arm {d_lon_to_lat:.3f})"
    )
    assert d_lon_to_lon < d_lat_to_lon, (
        "gnss.csv longitude was unused as GNSS position "
        f"(east-site {d_lon_to_lon:.3f} vs north-arm {d_lat_to_lon:.3f})"
    )
    assert d_h_to_h < d_lat_to_h, (
        "gnss.csv height was unused as GNSS position "
        f"(down-site {d_h_to_h:.3f} vs north-arm {d_lat_to_h:.3f})"
    )
    assert abs(vd_last[2]) > abs(vn_last[2]), (
        "down GNSS velocity was not consumed"
    )
    assert abs(vd_last[2]) > abs(ve_last[2]), (
        "down GNSS velocity was not distinguishable from east GNSS velocity"
    )
    assert dve_ne > 1.0e-3, (
        f"packed velocity north-east covariance slot did not change the solution ({dve_ne:.4f})"
    )
    assert dve_nd > 1.0e-3, (
        f"packed velocity north-down covariance slot did not change the solution ({dve_nd:.4f})"
    )
    assert dve_ed > 1.0e-3, (
        f"packed velocity east-down covariance slot did not change the solution ({dve_ed:.4f})"
    )
    # Same distance-to-measurement form as the north check above: a tight dd
    # slot holds down velocity nearer the 2 m/s measurement than a loose one.
    assert abs(vdd[2] - v_meas) + 0.05 < abs(vddn[2] - v_meas), (
        "swapping packed velocity dd/nn did not change down-velocity pull "
        f"(tight-down {vdd[2]:.3f}, loose-down {vddn[2]:.3f} vs {v_meas} m/s)"
    )


def test_dataset_mag_csv_frd_microtesla_consumed():
    """a present mag.csv of FRD magnetometer in microtesla is consumed."""
    lat, lon, h, _origin = _site()
    ned = ned_field_from_independent_wmm(lat, lon, WMM_YEAR)
    mag0 = body_mag_for_yaw(0.0, 0.0, 0.0, ned)
    mag70 = body_mag_for_yaw(0.0, 0.0, math.radians(70.0), ned)
    with workspace() as ws:
        d0 = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="mag0",
            write_mag=True,
            mag_frd=mag0,
        )
        d70 = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="mag70",
            write_mag=True,
            mag_frd=mag70,
        )
        s0 = python_replay_series(d0, ws.resolve("sol-mag0.csv"))
        s70 = python_replay_series(d70, ws.resolve("sol-mag70.csv"))
        c0 = c_replay(d0)
        c70 = c_replay(d70)
    y0 = s0.points[-1].yaw_deg
    y70 = s70.points[-1].yaw_deg
    assert y0 is not None and y70 is not None
    dyaw = yaw_abs_diff_deg(y0, y70)
    print(f"dataset mag yaw0={y0:.2f} yaw70={y70:.2f} dyaw={dyaw:.2f}", flush=True)
    assert dyaw > 4.0, "two FRD microtesla mag.csv headings produced the same fused yaw"
    assert c0.returncode == 0 and c70.returncode == 0, (
        f"C aborted a legal mag.csv directory: {c0.returncode} {c70.returncode}"
    )


def test_origin_section_and_optional_zero_as_default():
    """origin section is ignored; optional keys treat written 0 as the default."""
    lat, lon, h, _origin = _site()
    typo = runtime_unknown_key()
    with workspace() as ws:
        origin_zero = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="origin-zero",
            origin_section=True,
            omit_optional=False,
        )
        origin_omit = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="origin-omit",
            origin_section=True,
            omit_optional=True,
        )
        owned_typo = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="owned-typo",
            origin_section=True,
            extra_imu_key=typo,
        )
        s_zero = python_replay_series(origin_zero, ws.resolve("sol-oz.csv"))
        s_omit = python_replay_series(origin_omit, ws.resolve("sol-oo.csv"))
        c_zero = c_replay(origin_zero)
        c_omit = c_replay(origin_omit)
        py_typo = python_replay_result(owned_typo)
        c_typo = c_replay(owned_typo)
        imu_times = imu_times_from_dataset(origin_zero)
    series_covers_imu_log(s_zero, imu_times)
    series_near_llh(s_zero, lat, lon, h, what="origin plus optional zeros")
    series_near_llh(s_omit, lat, lon, h, what="origin plus omitted optionals")
    print(
        f"origin C zero={c_zero.returncode} omit={c_omit.returncode} "
        f"typo py={py_typo.returncode} c={c_typo.returncode}",
        flush=True,
    )
    assert c_zero.returncode == 0, (
        f"origin section plus optional zeros aborted C: {reporting_text(c_zero)[-1200:]!r}"
    )
    assert c_omit.returncode == 0, (
        f"origin section plus omitted optionals aborted C: {reporting_text(c_omit)[-1200:]!r}"
    )
    require_nonzero_and_names(py_typo, typo)
    require_nonzero_and_names(c_typo, typo)


def test_radio_link_section_accepted_and_ignored():
    """a radio-link section is accepted and ignored, not an owned typo."""
    lat, lon, h, _origin = _site()
    typo = runtime_unknown_key()
    with workspace() as ws:
        radio = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="radio-link",
            radio_link_section=True,
        )
        owned_typo = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="radio-owned-typo",
            radio_link_section=True,
            extra_imu_key=typo,
        )
        series = python_replay_series(radio, ws.resolve("sol-radio.csv"))
        c_ok = c_replay(radio)
        py_typo = python_replay_result(owned_typo)
        c_typo = c_replay(owned_typo)
        imu_times = imu_times_from_dataset(radio)
    series_covers_imu_log(series, imu_times)
    series_near_llh(series, lat, lon, h, what="radio-link section")
    report_names_mode(series.result, MODE_FULL, "radio-link section")
    print(
        f"radio-link python rc={series.result.returncode} C rc={c_ok.returncode} "
        f"owned typo py={py_typo.returncode} c={c_typo.returncode}",
        flush=True,
    )
    assert series.result.returncode == 0, (
        f"radio-link section aborted python replay: "
        f"{reporting_text(series.result)[-1200:]!r}"
    )
    assert c_ok.returncode == 0, (
        f"radio-link section aborted C replay: {reporting_text(c_ok)[-1200:]!r}"
    )
    require_nonzero_and_names(py_typo, typo)
    require_nonzero_and_names(c_typo, typo)


def test_runner_merges_latest_baro_and_mag_at_or_before():
    """latest barometer and magnetometer samples at or before t are attached."""
    lat, lon, h, _origin = _site()
    ned = ned_field_from_independent_wmm(lat, lon, WMM_YEAR)
    mag0 = body_mag_for_yaw(0.0, 0.0, 0.0, ned)
    mag70 = body_mag_for_yaw(0.0, 0.0, math.radians(70.0), ned)
    p0 = tropospheric_isa_pressure_pa(150.0)
    p1 = tropospheric_isa_pressure_pa(350.0)
    mag_s = 8.0
    climb_s = 12.0
    with workspace() as ws:
        yaml_path, sol_path = write_runner_mapping(
            ws,
            relpath="merge-baro-mag",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=NAMED_PAD_S,
            mag_frd=mag0,
            mag_after_s=mag_s,
            mag_after_frd=mag70,
            pressure_pa=p0,
            pressure_after_s=climb_s,
            pressure_after_pa=p1,
            disable_auto_zupt=True,
        )
        _r, epochs = run_mapped_runner(yaml_path, sol_path)
    before_mag = runner_last_at_or_before(epochs, int((mag_s - 0.2) * 1.0e6))
    after_mag = epochs[-1]
    before_baro = runner_last_at_or_before(epochs, int((climb_s - 0.2) * 1.0e6))
    after_baro = epochs[-1]
    assert before_mag.yaw_deg is not None and after_mag.yaw_deg is not None
    dyaw = yaw_abs_diff_deg(after_mag.yaw_deg, before_mag.yaw_deg)
    print(
        f"mag attach yaw before={before_mag.yaw_deg:.2f} after={after_mag.yaw_deg:.2f} "
        f"dyaw={dyaw:.2f}",
        flush=True,
    )
    assert dyaw > 5.0, "epochs at or after the mag jump did not attach the new sample"
    climb = _arb_climb(before_baro, after_baro, "baro attach")
    assert climb > 2.0, "epochs at or after the pressure jump did not attach the new baro sample"
    pre_full = [
        e
        for e in epochs
        if e.mode == MODE_FULL
        and e.t_us <= int((climb_s - 0.2) * 1.0e6)
        and e.arb_height_m is not None
    ]
    assert pre_full, "no FULL arbitrated-height epoch before the pressure drop"
    early_climb = _arb_climb(pre_full[0], pre_full[-1], "baro before drop")
    assert early_climb < climb, (
        "epoch before the pressure drop already attached the later barometer sample"
    )


def test_runner_maps_into_the_same_navigator_loop():
    """YAML runner maps custom CSVs into the same IMU-consuming navigator loop."""
    lat, lon, h, _origin = _site()
    mag, _ned = _runner_mag(lat, lon)
    p = tropospheric_isa_pressure_pa(150.0)
    extra_s = 2.0
    gap_acc = 1.4
    gnss_end_us = int(round(HAPPY_DURATION_S * 1.0e6))
    zoh = (lat, lon, h)
    with workspace() as ws:
        yaml_path, sol_path = write_runner_mapping(
            ws,
            relpath="runner-loop",
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            duration_s=HAPPY_DURATION_S,
            mag_frd=mag,
            pressure_pa=p,
            extra_imu_s=extra_s,
            gap_north_acc=gap_acc,
            disable_auto_zupt=True,
        )
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="dataset-loop",
            extra_imu_s=extra_s,
            gap_north_acc=gap_acc,
        )
        _r, epochs = run_mapped_runner(yaml_path, sol_path)
        series = python_replay_series(dest, ws.resolve("sol-loop.csv"))
        c_res = c_replay(dest)
    n_imu = int(round((HAPPY_DURATION_S + extra_s) * IMU_HZ))
    pre = [e for e in epochs if e.t_us <= gnss_end_us]
    assert pre, "runner wrote no samples before the GNSS gap"
    runner_tail_full_near(pre, lat, lon, h, what="yaml runner same-loop pad before gap")
    print(f"same-loop runner rows={len(epochs)} imu={n_imu}", flush=True)
    assert len(epochs) > 2, "runner did not write one row per epoch"
    peak_r = gap_peak_from_runner(epochs, zoh, gnss_end_us, "yaml runner same-loop gap")
    pre_ds = tuple(p for p in series.points if p.t_us <= gnss_end_us)
    assert pre_ds, "dataset twin has no fused samples before the GNSS gap"
    series_near_llh(
        ReplaySeries(pre_ds, series.result),
        lat,
        lon,
        h,
        what="dataset same-loop pad before gap",
    )
    peak_d = gap_peak_from_series(series, zoh, gnss_end_us, "dataset same-loop gap")
    report_names_mode(series.result, MODE_FULL, "dataset same-loop pad")
    print(
        f"same-loop C rc={c_res.returncode} peak_runner={peak_r:.3f} peak_dataset={peak_d:.3f}",
        flush=True,
    )
    assert peak_r > 0.4, (
        "runner gap IMU samples did not move relative to holding GNSS "
        "(mapping did not drive the IMU-consuming loop)"
    )
    assert peak_d > 0.4, (
        "dataset twin gap IMU samples did not move relative to holding GNSS"
    )
    assert c_res.returncode == 0, (
        f"dataset twin of the runner pad aborted C: {reporting_text(c_res)[-1200:]!r}"
    )


def test_dataset_baro_csv_consumed_as_pressure():
    """a present baro.csv is static pressure in pascals, not already-altitude."""
    lat, lon, h, origin = _site()
    p_true = tropospheric_isa_pressure_pa(h if 0.0 <= h < 2000.0 else 150.0)
    p_climb = tropospheric_isa_pressure_pa((h if 0.0 <= h < 2000.0 else 150.0) + 40.0)
    with workspace() as ws:
        as_pa = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="baro-as-pa",
            extra_imu_s=2.0,
            write_baro=True,
            baro_pa=p_true,
            lim_baro_rms_m=8.0,
        )
        climb = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="baro-climb",
            extra_imu_s=2.0,
            write_baro=True,
            baro_pa=p_true,
            baro_after_s=3.0,
            baro_after_pa=p_climb,
            lim_baro_rms_m=8.0,
        )
        s_pa = python_replay_series(as_pa, ws.resolve("sol-baro-pa.csv"))
        c_pa = c_replay(as_pa)
        c_climb = c_replay(climb)
    series_near_llh(s_pa, lat, lon, h, what="baro.csv written as pascals")
    print(
        f"baro as-Pa C={c_pa.returncode} pressure-drop C={c_climb.returncode}",
        flush=True,
    )
    assert c_pa.returncode == 0, (
        f"true-pascal baro.csv failed C baro scoring: "
        f"{reporting_text(c_pa)[-1200:]!r}"
    )
    assert c_climb.returncode != 0, (
        "an ISA pressure drop in baro.csv left C baro scoring passing "
        "against a flat reference (baro.csv was not consumed as pressure)"
    )


def test_speed_csv_scalar_from_config_not_extra_columns():
    """speed.csv is scalar m/s; uncertainty and delay come from config.yaml."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        no_speed = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="speed-off",
            write_speed=False,
            gnss_vel_ned=(4.0, 0.0, 0.0),
            vel_ok=1,
        )
        two_col = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="speed-two",
            write_speed=True,
            speed_mps=8.0,
            speed_delay_ms=0.0,
            gnss_vel_ned=(4.0, 0.0, 0.0),
            vel_ok=1,
        )
        extra = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="speed-extra",
            write_speed=True,
            speed_mps=8.0,
            speed_delay_ms=0.0,
            speed_extra_columns=True,
            gnss_vel_ned=(4.0, 0.0, 0.0),
            vel_ok=1,
        )
        delay0 = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="speed-d0",
            extra_imu_s=6.0,
            gap_north_acc=1.5,
            write_speed=True,
            speed_mps=8.0,
            speed_delay_ms=0.0,
            vel_ok=0,
        )
        delay4 = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="speed-d4",
            extra_imu_s=6.0,
            gap_north_acc=1.5,
            write_speed=True,
            speed_mps=8.0,
            speed_delay_ms=3000.0,
            vel_ok=0,
        )
        s_off = python_replay_series(no_speed, ws.resolve("sol-soff.csv"))
        s_two = python_replay_series(two_col, ws.resolve("sol-stwo.csv"))
        s_extra = python_replay_series(extra, ws.resolve("sol-sx.csv"))
        s_d0 = python_replay_series(delay0, ws.resolve("sol-sd0.csv"))
        s_d4 = python_replay_series(delay4, ws.resolve("sol-sd4.csv"))
        c_two = c_replay(two_col)
        c_extra = c_replay(extra)
    v_off = s_off.points[-1].vel_ned
    v_two = s_two.points[-1].vel_ned
    v_extra = s_extra.points[-1].vel_ned
    assert v_off is not None and v_two is not None and v_extra is not None
    sped_off = math.hypot(v_off[0], v_off[1])
    sped_two = math.hypot(v_two[0], v_two[1])
    sped_extra = math.hypot(v_extra[0], v_extra[1])
    print(
        f"speed |vh| off={sped_off:.3f} two={sped_two:.3f} extra={sped_extra:.3f} "
        f"c_two={c_two.returncode} c_extra={c_extra.returncode}",
        flush=True,
    )
    assert sped_two > sped_off + 0.4, (
        "speed.csv scalar was not consumed (fused horizontal speed matches no-speed)"
    )
    assert abs(sped_two - sped_extra) < 0.3, (
        "extra speed.csv columns changed the fused speed (delay/uncertainty "
        "were not taken from config.yaml alone)"
    )
    d0 = s_d0.points[-1]
    d4 = s_d4.points[-1]
    assert d0.vel_ned is not None and d4.vel_ned is not None
    h0 = math.hypot(d0.vel_ned[0], d0.vel_ned[1])
    h4 = math.hypot(d4.vel_ned[0], d4.vel_ned[1])
    print(
        f"speed config delay after coast |vh| delay0={h0:.3f} delay3s={h4:.3f}",
        flush=True,
    )
    assert abs(h0 - h4) > 0.3, (
        "config.yaml speed delay did not change when the CSV bytes were identical"
    )
    assert c_two.returncode == 0 and c_extra.returncode == 0, (
        f"C aborted a legal speed.csv directory: {c_two.returncode} {c_extra.returncode}"
    )


def test_speed_csv_uncertainty_from_config():
    """identical speed.csv bytes with a different configured uncertainty change fused speed."""
    lat, lon, h, _origin = _site()
    with workspace() as ws:
        tight = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="speed-u-tight",
            write_speed=True,
            speed_mps=8.0,
            speed_delay_ms=0.0,
            speed_stddev_mps=0.05,
            gnss_vel_ned=(4.0, 0.0, 0.0),
            vel_ok=1,
        )
        loose = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="speed-u-loose",
            write_speed=True,
            speed_mps=8.0,
            speed_delay_ms=0.0,
            speed_stddev_mps=20.0,
            gnss_vel_ned=(4.0, 0.0, 0.0),
            vel_ok=1,
        )
        speed_tight = (tight / "speed.csv").read_text(encoding="utf-8")
        speed_loose = (loose / "speed.csv").read_text(encoding="utf-8")
        assert speed_tight == speed_loose, "speed.csv bytes must match across uncertainty arms"
        s_tight = python_replay_series(tight, ws.resolve("sol-u-tight.csv"))
        s_loose = python_replay_series(loose, ws.resolve("sol-u-loose.csv"))
    v_tight = s_tight.points[-1].vel_ned
    v_loose = s_loose.points[-1].vel_ned
    assert v_tight is not None and v_loose is not None, (
        "fused NED velocity was not published on a speed.csv uncertainty arm"
    )
    h_tight = math.hypot(v_tight[0], v_tight[1])
    h_loose = math.hypot(v_loose[0], v_loose[1])
    print(
        f"speed config uncertainty |vh| tight={h_tight:.3f} loose={h_loose:.3f}",
        flush=True,
    )
    assert abs(h_tight - h_loose) > 0.3, (
        "identical speed.csv bytes with a different configured uncertainty "
        "did not change fused speed"
    )


def test_speed_optional_and_hash_header_accepted():
    """speed.csv is optional; a leading # header is the header, not a data row."""
    lat, lon, h, _origin = _site()
    mag, _ned = _runner_mag(lat, lon)
    p = tropospheric_isa_pressure_pa(h if 0.0 <= h < 2000.0 else 150.0)
    with workspace() as ws:
        dest = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="no-speed-hash",
            write_speed=False,
            write_mag=True,
            mag_frd=mag,
            write_baro=True,
            baro_pa=p,
        )
        assert not (dest / "speed.csv").is_file(), "fixture accidentally wrote speed.csv"
        require_leading_hash_header(dest / "imu.csv", "imu.csv")
        require_leading_hash_header(dest / "ref.csv", "ref.csv")
        require_leading_hash_header(dest / "gnss.csv", "gnss.csv")
        require_leading_hash_header(dest / "mag.csv", "mag.csv")
        require_leading_hash_header(dest / "baro.csv", "baro.csv")
        series = python_replay_series(dest, ws.resolve("sol-no-speed.csv"))
        c_res = c_replay(dest)
        imu_times = imu_times_from_dataset(dest)
    series_covers_imu_log(series, imu_times)
    series_near_llh(series, lat, lon, h, what="no speed.csv with # headers")
    report_names_mode(series.result, MODE_FULL, "no speed.csv")
    print(
        f"no speed.csv python n={len(series.points)} c rc={c_res.returncode}",
        flush=True,
    )
    assert c_res.returncode == 0, (
        f"C aborted a legal directory with no speed.csv and leading # headers: "
        f"{reporting_text(c_res)[-1200:]!r}"
    )
    assert series.result.returncode == 0, (
        f"python aborted a legal directory with no speed.csv and leading # headers: "
        f"{reporting_text(series.result)[-1200:]!r}"
    )


def test_imu_csv_gyro_frd_consumed():
    """imu.csv gyro FRD x/y/z in rad/s is consumed, distinguishable from unused."""
    lat, lon, h, _origin = _site()
    rate = 0.05
    with workspace() as ws:
        still = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gyro-still",
            imu_gyr=(0.0, 0.0, 0.0),
        )
        gx = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gyro-x",
            imu_gyr=(rate, 0.0, 0.0),
            rotate_specific_force=True,
        )
        gy = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gyro-y",
            imu_gyr=(0.0, rate, 0.0),
            rotate_specific_force=True,
        )
        gz = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="gyro-z",
            imu_gyr=(0.0, 0.0, rate),
        )
        s0 = python_replay_series(still, ws.resolve("sol-g0.csv"))
        sx = python_replay_series(gx, ws.resolve("sol-gx.csv"))
        sy = python_replay_series(gy, ws.resolve("sol-gy.csv"))
        sz = python_replay_series(gz, ws.resolve("sol-gz.csv"))
        c0 = c_replay(still)
        cz = c_replay(gz)
    r0, p0, y0 = s0.points[-1].roll_deg, s0.points[-1].pitch_deg, s0.points[-1].yaw_deg
    rx, px, yx = sx.points[-1].roll_deg, sx.points[-1].pitch_deg, sx.points[-1].yaw_deg
    ry, py, yy = sy.points[-1].roll_deg, sy.points[-1].pitch_deg, sy.points[-1].yaw_deg
    rz, pz, yz = sz.points[-1].roll_deg, sz.points[-1].pitch_deg, sz.points[-1].yaw_deg
    assert None not in (r0, p0, y0, rx, px, yx, ry, py, yy, rz, pz, yz)
    droll_x = yaw_abs_diff_deg(r0, rx)
    dpitch_y = yaw_abs_diff_deg(p0, py)
    dyaw_z = yaw_abs_diff_deg(y0, yz)
    print(
        f"gyro FRD still rpy=({r0:.2f},{p0:.2f},{y0:.2f}) "
        f"x droll={droll_x:.2f} y dpitch={dpitch_y:.2f} z dyaw={dyaw_z:.2f}",
        flush=True,
    )
    assert droll_x > 4.0, (
        "imu.csv gyro FRD x was unused (last roll matched the zero-rate arm)"
    )
    assert dpitch_y > 4.0, (
        "imu.csv gyro FRD y was unused (last pitch matched the zero-rate arm)"
    )
    assert dyaw_z > 4.0, (
        "imu.csv gyro FRD z was unused (last yaw matched the zero-rate arm)"
    )
    assert c0.returncode == 0 and cz.returncode == 0, (
        f"C aborted a legal gyro-FRD directory: {c0.returncode} {cz.returncode}"
    )


def test_imu_csv_accelerometer_frd_yz_consumed():
    """imu.csv accelerometer FRD x/y/z in m/s² is consumed, distinguishable from unused."""
    lat, lon, h, _origin = _site()
    extra_s = 2.0
    gnss_end_us = int(round(HAPPY_DURATION_S * 1.0e6))
    gap_acc = 1.4
    with workspace() as ws:
        still = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="acc-still",
            extra_imu_s=extra_s,
        )
        ax = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="acc-x",
            extra_imu_s=extra_s,
            gap_north_acc=gap_acc,
        )
        ay = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="acc-y",
            extra_imu_s=extra_s,
            gap_east_acc=gap_acc,
        )
        az = write_replay_dataset(
            ws,
            lat_deg=lat,
            lon_deg=lon,
            h_m=h,
            relpath="acc-z",
            extra_imu_s=extra_s,
            gap_z_acc=float(SPECIFIC_FORCE_LEVEL[2]) + gap_acc,
        )
        s0 = python_replay_series(still, ws.resolve("sol-a0.csv"))
        sx = python_replay_series(ax, ws.resolve("sol-ax.csv"))
        sy = python_replay_series(ay, ws.resolve("sol-ay.csv"))
        sz = python_replay_series(az, ws.resolve("sol-az.csv"))
        c0 = c_replay(still)
        cx = c_replay(ax)
        cy = c_replay(ay)
    pre0 = tuple(p for p in s0.points if p.t_us <= gnss_end_us)
    assert pre0, "level accelerometer series has no fused samples before the GNSS gap"
    series_near_llh(
        ReplaySeries(pre0, s0.result),
        lat,
        lon,
        h,
        what="level accelerometer fused tail at the pad before the gap",
    )
    last0 = ecef_from_llh_deg(
        s0.points[-1].lat_deg, s0.points[-1].lon_deg, s0.points[-1].h_m
    )
    lastx = ecef_from_llh_deg(
        sx.points[-1].lat_deg, sx.points[-1].lon_deg, sx.points[-1].h_m
    )
    lasty = ecef_from_llh_deg(
        sy.points[-1].lat_deg, sy.points[-1].lon_deg, sy.points[-1].h_m
    )
    lastz = ecef_from_llh_deg(
        sz.points[-1].lat_deg, sz.points[-1].lon_deg, sz.points[-1].h_m
    )
    dx = hypot3(lastx, last0)
    dy = hypot3(lasty, last0)
    dz = hypot3(lastz, last0)
    dxy = hypot3(lastx, lasty)
    dxz = hypot3(lastx, lastz)
    print(
        f"accel FRD x last-vs-still={dx:.3f} m y last-vs-still={dy:.3f} m "
        f"z last-vs-still={dz:.3f} m x-vs-y={dxy:.3f} m x-vs-z={dxz:.3f} m "
        f"c_still={c0.returncode} c_x={cx.returncode} c_y={cy.returncode}",
        flush=True,
    )
    assert dx > 0.4, (
        "imu.csv accelerometer FRD x was unused (gap north specific-force "
        "matched the level-x twin)"
    )
    assert dy > 0.4, (
        "imu.csv accelerometer FRD y was unused (gap east specific-force "
        "matched the level-y twin)"
    )
    assert dz > 0.4, (
        "imu.csv accelerometer FRD z was unused (gap vertical specific-force "
        "matched the level-z twin)"
    )
    assert dxy > 0.2, (
        "imu.csv accelerometer FRD x was not a distinct axis from y "
        "(north-gap last point matched the east-gap twin)"
    )
    assert dxz > 0.2, (
        "imu.csv accelerometer FRD x was not a distinct axis from z "
        "(north-gap last point matched the vertical-gap twin)"
    )
    assert c0.returncode == 0 and cx.returncode == 0 and cy.returncode == 0, (
        f"C aborted a legal accelerometer-FRD directory: "
        f"{c0.returncode} {cx.returncode} {cy.returncode}"
    )


def test_replay_and_runner_outputs_are_well_formed():
    """Contract: every runner row names a mode, and a runner cell or a
    ``--dump-solution`` field is either a number or (runner) empty for an
    unpublished value -- on every runner file and dump parsed in this session
    and on a pad of its own. Other tests read such a row or cell as
    unpublished; this test fails when one was seen.
    """
    from _harness import require_no_product_issues

    lat, lon, h, _origin = _site()
    mag, _ned = _runner_mag(lat, lon)
    p = tropospheric_isa_pressure_pa(150.0)
    with workspace() as ws:
        yaml_path, sol_path = write_runner_mapping(
            ws, relpath="well-formed", lat_deg=lat, lon_deg=lon, h_m=h,
            duration_s=HAPPY_DURATION_S, mag_frd=mag, pressure_pa=p,
        )
        _r, epochs = run_mapped_runner(yaml_path, sol_path)
        dest = write_replay_dataset(ws, lat_deg=lat, lon_deg=lon, h_m=h, relpath="well-formed-ds")
        series = python_replay_series(dest, ws.resolve("sol-well-formed.csv"))
    assert epochs and series.points, "runner or replay produced nothing to read"
    require_no_product_issues("F10", "runner / replay outputs (F10)")
