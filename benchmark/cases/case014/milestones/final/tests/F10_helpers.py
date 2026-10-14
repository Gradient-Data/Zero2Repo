# feature: F10
"""Observation helpers for FP-10 dataset replay and the YAML CSV runner.

Replay observations go through the sealed harness entries (directory or
config.yaml path for Python, the same directory for C, a different YAML for
the runner). This module does not import the product in the pytest process.
Expected positions come from the lat/lon/height written into the CSVs and
from independent WGS84 / tropospheric ISA / WMM geometry.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from _harness import (
    note_product_issue,
    runtime_hex,
    DEFAULT_REPLAY_TIMEOUT,
    HarnessError,
    RunResult,
    Workspace,
    run_c_replay,
    run_replay,
    run_runner,
)
from F01_helpers import angle_diff_deg, hypot3
from F02_helpers import (
    ENTRY_DWELL_S,
    GNSS_HZ,
    HAPPY_DURATION_S,
    IMU_HZ,
    READY_WAIT_S,
    SPECIFIC_FORCE_LEVEL,
    _ecef_to_geodetic,
    ecef_from_llh_deg,
    ecef_plus_ned,
)
from F03_helpers import G_MPS2, still_level_acc
from F08_helpers import MODE_FULL

# Named 30 s mixed-unit pad. Dump/series observation is an instrument
# channel, not a stdout spelling contract.
NAMED_PAD_S = 30.0
PAD_NEAR_M = 25.0
OTHER_SITE_M = 5.0e4
SERIES_MIN_FRAC = 0.08
UNKNOWN_AIDING = "not-a-mode"
DUMP_EVERY_EPOCH = ["--dump-solution-hz=0"]
# Shared known-schema radio-link block. Input schema
# for the foreign section both harnesses accept and ignore; not a stdout
# spelling contract. Original-world name; C0 rewrites identity.
RADIO_LINK_SECTION = "crazyflie"

_IMU_HEADER = (
    "# t_us, gyr_frd_x [rad/s], gyr_frd_y [rad/s], gyr_frd_z [rad/s], "
    "acc_frd_x [m/s^2], acc_frd_y [m/s^2], acc_frd_z [m/s^2]\n"
)
_IMU_HEADER_TEMP = (
    "# t_us, gyr_frd_x [rad/s], gyr_frd_y [rad/s], gyr_frd_z [rad/s], "
    "acc_frd_x [m/s^2], acc_frd_y [m/s^2], acc_frd_z [m/s^2], imu_temp_c\n"
)
_REF_HEADER = (
    "# t_us, lat_deg, lon_deg, h_m, roll_deg, pitch_deg, yaw_deg, "
    "vn_mps, ve_mps, vd_mps\n"
)
_GNSS_HEADER = (
    "# t_us, lat_deg, lon_deg, h_m, cov_pos_ned nn,ne,nd,ee,ed,dd [m^2], "
    "vn, ve, vd [m/s], cov_vel_ned nn,ne,nd,ee,ed,dd [(m/s)^2], vel_ok\n"
)
_MAG_HEADER = "# t_us, mag_frd_x, mag_frd_y, mag_frd_z\n"
_BARO_HEADER = "# t_us, static pressure [Pa]\n"
_SPEED_HEADER = "# t_us, speed_mps\n"

_MODE_NAMES = {MODE_FULL, "COASTING", "ATTITUDE_ONLY", "NONE"}


@dataclass(frozen=True)
class SeriesPoint:
    t_us: int
    lat_deg: float
    lon_deg: float
    h_m: float
    roll_deg: float | None
    pitch_deg: float | None
    yaw_deg: float | None
    vel_ned: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class ReplaySeries:
    points: tuple[SeriesPoint, ...]
    result: RunResult

    def ecef_at(self, index: int) -> tuple[float, float, float]:
        p = self.points[index]
        return ecef_from_llh_deg(p.lat_deg, p.lon_deg, p.h_m)


@dataclass(frozen=True)
class RunnerEpoch:
    t_us: int
    mode: str
    lat_deg: float | None
    lon_deg: float | None
    h_m: float | None
    ned_pos: tuple[float, float, float] | None
    ned_vel: tuple[float, float, float] | None
    roll_deg: float | None
    pitch_deg: float | None
    yaw_deg: float | None
    arb_height_m: float | None


def runtime_filename(prefix: str = "stream") -> str:
    """Runtime CSV name that is not a conventional imu/gnss/ref token."""
    token = runtime_hex(10)
    name = f"{prefix}_{token}.csv"
    print(f"runtime filename {name}", flush=True)
    return name


def runtime_unknown_key(prefix: str = "owned") -> str:
    token = runtime_hex(8)
    key = f"{prefix}_typo_{token}"
    print(f"runtime unknown key {key}", flush=True)
    return key


def llh_offset_north(
    lat_deg: float, lon_deg: float, h_m: float, north_m: float
) -> tuple[float, float, float]:
    return llh_offset_ned(lat_deg, lon_deg, h_m, north_m, 0.0, 0.0)


def llh_offset_ned(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    north_m: float,
    east_m: float = 0.0,
    down_m: float = 0.0,
) -> tuple[float, float, float]:
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    offset = ecef_plus_ned(origin, north_m, east_m, down_m)
    olat, olon, oh = _ecef_to_geodetic(offset[0], offset[1], offset[2])
    return math.degrees(olat), math.degrees(olon), oh


def reporting_text(result: RunResult) -> str:
    """Stdout union stderr. Non-UTF-8 is an observation failure, not silence."""
    try:
        out = result.stdout_text
    except HarnessError as exc:
        raise HarnessError(f"stdout is not utf-8: {exc}") from exc
    try:
        err = result.stderr_text
    except HarnessError as exc:
        raise HarnessError(f"stderr is not utf-8: {exc}") from exc
    return out + "\n" + err


def require_nonzero_and_names(result: RunResult, token: str) -> None:
    """Non-zero exit and the written offender appears on the report channel."""
    text = reporting_text(result)
    print(
        f"nonzero-and-names token={token!r} rc={result.returncode} "
        f"tail={text[-800:]!r}",
        flush=True,
    )
    assert result.returncode != 0, (
        f"expected a non-zero exit that names {token!r}, got {result.returncode} "
        f"report={text[-1500:]!r}"
    )
    assert token in text, (
        f"report channel did not name the written offender {token!r}: "
        f"{text[-1500:]!r}"
    )


def require_nonzero(result: RunResult, what: str) -> None:
    text = reporting_text(result)
    print(f"{what}: rc={result.returncode} tail={text[-600:]!r}", flush=True)
    assert result.returncode != 0, (
        f"{what}: expected a non-zero exit, got {result.returncode} "
        f"report={text[-1500:]!r}"
    )


def _fmt_yaml_float(value: float) -> str:
    text = f"{value:.10g}"
    if ("e" in text or "E" in text) and "." not in text.split("e")[0].split("E")[0]:
        mant, _, exp = text.replace("E", "e").partition("e")
        text = mant + ".0e" + exp
    return text


def write_replay_dataset(
    ws: Workspace,
    *,
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    relpath: str,
    duration_s: float = HAPPY_DURATION_S,
    aiding: str = "gnss",
    init: str = "auto",
    write_imu: bool = True,
    write_ref: bool = True,
    write_gnss: bool | None = None,
    write_mag: bool = False,
    write_baro: bool = False,
    write_speed: bool = False,
    imu_name: str = "imu.csv",
    ref_name: str = "ref.csv",
    gnss_name: str = "gnss.csv",
    inputs: dict[str, str] | None = None,
    decoy_gnss_llh: tuple[float, float, float] | None = None,
    decoy_imu: bool = False,
    gnss_north_m: float = 0.0,
    gnss_north_after_s: float | None = None,
    zero_pos_diag: bool = False,
    zero_vel_diag: bool = False,
    pos_fallback_m: Sequence[float] | None = (2.0, 3.0),
    vel_fallback_mps: float | None = 0.25,
    imu_temp: bool = False,
    imu_temp_c: float = 1000.0,
    imu_gyr: Sequence[float] = (0.0, 0.0, 0.0),
    comment_and_junk: bool = False,
    junk_then_north_m: float = 0.0,
    min_epochs: int | None = 5,
    warmup_sec: float = 1.0,
    lim_pos_rms_m: float | None = 80.0,
    lim_att_bias_deg: float | None = None,
    lim_yaw_bias_deg: float | None = None,
    score_attitude: int = 0,
    score_ahrs: int = 0,
    spectral_zero: bool = False,
    omit_spectral: bool = False,
    extra_top_key: str | None = None,
    extra_imu_key: str | None = None,
    dt_us: int | None = None,
    extra_imu_s: float = 0.0,
    gap_north_acc: float = 0.0,
    gap_east_acc: float = 0.0,
    gap_z_acc: float | None = None,
    mag_frd: Sequence[float] | None = None,
    baro_pa: float | None = None,
    baro_hz: int = 10,
    speed_mps: float = 0.0,
    pos_cov6: Sequence[float] | None = None,
    vel_cov6: Sequence[float] | None = None,
    vel_cov_after_s: float | None = None,
    vel_cov_after6: Sequence[float] | None = None,
    vel_ok: int = 1,
    gnss_vel_ned: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_vel_after_s: float | None = None,
    gnss_vel_after_ned: Sequence[float] | None = None,
    ref_rpy_deg: Sequence[float] = (0.0, 0.0, 0.0),
    ref_vel_ned: Sequence[float] = (0.0, 0.0, 0.0),
    origin_section: bool = False,
    radio_link_section: bool = False,
    omit_optional: bool = False,
    ref_h_m: float | None = None,
    ref_ned_m: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_ned_m: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_motion_ned: Sequence[float] = (0.0, 0.0, 0.0),
    baro_after_s: float | None = None,
    baro_after_pa: float | None = None,
    speed_after_s: float | None = None,
    speed_after_mps: float | None = None,
    speed_delay_ms: float | None = None,
    speed_stddev_mps: float | None = None,
    speed_extra_columns: bool = False,
    lim_baro_rms_m: float | None = None,
    rotate_specific_force: bool = False,
) -> Path:
    """Write config.yaml plus named CSVs under the workspace.

    Keys written here are the replay input schema, not a stdout contract.
    """
    dest = ws.resolve(relpath)
    dest.mkdir(parents=True, exist_ok=True)
    if write_gnss is None:
        write_gnss = aiding == "gnss"
    imu_hz = IMU_HZ
    gnss_hz = GNSS_HZ
    step_us = 10_000 if dt_us is None else int(dt_us)
    dt_s = step_us / 1.0e6
    n_pad = int(round(duration_s / dt_s))
    n_extra = int(round(extra_imu_s / dt_s)) if extra_imu_s > 0.0 else 0
    n = n_pad + n_extra
    acc = list(SPECIFIC_FORCE_LEVEL)
    gyr = (
        float(imu_gyr[0]),
        float(imu_gyr[1]),
        float(imu_gyr[2]),
    )
    gnss_llh = (lat_deg, lon_deg, h_m)
    if gnss_north_after_s is None:
        if any(float(v) for v in gnss_ned_m):
            gnss_llh = llh_offset_ned(
                lat_deg,
                lon_deg,
                h_m,
                float(gnss_ned_m[0]),
                float(gnss_ned_m[1]),
                float(gnss_ned_m[2]),
            )
        elif gnss_north_m:
            gnss_llh = llh_offset_north(lat_deg, lon_deg, h_m, gnss_north_m)
    if pos_cov6 is None:
        if zero_pos_diag:
            pos_cov6 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        else:
            pos_cov6 = (4.0, 0.0, 0.0, 4.0, 0.0, 4.0)
    if vel_cov6 is None:
        if zero_vel_diag:
            vel_cov6 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        else:
            vel_cov6 = (0.04, 0.0, 0.0, 0.04, 0.0, 0.04)
    gnss_every = max(1, int(round(1.0 / (gnss_hz * dt_s))))
    ref_every = max(1, int(round(1.0 / (10.0 * dt_s))))
    baro_every = max(1, int(round(1.0 / (baro_hz * dt_s))))
    mag_every = max(1, int(round(1.0 / (10.0 * dt_s))))
    junk_at = n_pad // 2 if comment_and_junk else None
    ref_height = float(h_m) if ref_h_m is None else float(ref_h_m)
    ref_lat, ref_lon, ref_height = llh_offset_ned(
        lat_deg,
        lon_deg,
        ref_height,
        float(ref_ned_m[0]),
        float(ref_ned_m[1]),
        float(ref_ned_m[2]),
    )
    imu_lines = [_IMU_HEADER_TEMP if imu_temp else _IMU_HEADER]
    ref_lines = [_REF_HEADER]
    gnss_lines = [_GNSS_HEADER]
    mag_lines = [_MAG_HEADER]
    baro_lines = [_BARO_HEADER]
    speed_lines = [_SPEED_HEADER]
    imu_times: list[int] = []
    for k in range(n + 1):
        t_us = k * step_us
        t_s = t_us / 1.0e6
        imu_times.append(t_us)
        acc_now = list(acc)
        if extra_imu_s > 0.0 and t_s > duration_s + 1.0e-9:
            acc_now[0] = float(gap_north_acc)
            acc_now[1] = float(gap_east_acc)
            if gap_z_acc is not None:
                acc_now[2] = float(gap_z_acc)
        gx, gy, gz = gyr
        if rotate_specific_force:
            acc_now = list(still_level_acc(pitch_rad=gy * t_s, roll=gx * t_s))
        if imu_temp:
            imu_lines.append(
                f"{t_us},{gx:.9g},{gy:.9g},{gz:.9g},{acc_now[0]:.9g},"
                f"{acc_now[1]:.9g},{acc_now[2]:.9g},{float(imu_temp_c):.9g}\n"
            )
        else:
            imu_lines.append(
                f"{t_us},{gx:.9g},{gy:.9g},{gz:.9g},{acc_now[0]:.9g},"
                f"{acc_now[1]:.9g},{acc_now[2]:.9g}\n"
            )
        if junk_at is not None and k == junk_at:
            imu_lines.append("# comment line inside the IMU stream\n")
            imu_lines.append("not-a-number,junk,row\n")
        if k % ref_every == 0:
            ref_lines.append(
                f"{t_us},{ref_lat:.10f},{ref_lon:.10f},{ref_height:.6f},"
                f"{ref_rpy_deg[0]:.6f},{ref_rpy_deg[1]:.6f},{ref_rpy_deg[2]:.6f},"
                f"{ref_vel_ned[0]:.6f},{ref_vel_ned[1]:.6f},{ref_vel_ned[2]:.6f}\n"
            )
        on_gnss = k % gnss_every == 0 and t_s <= duration_s + 1.0e-9
        if on_gnss:
            la, lo, hh = gnss_llh
            if gnss_north_after_s is not None and t_s + 1.0e-12 >= gnss_north_after_s:
                if any(float(v) for v in gnss_ned_m):
                    la, lo, hh = llh_offset_ned(
                        lat_deg,
                        lon_deg,
                        h_m,
                        float(gnss_ned_m[0]),
                        float(gnss_ned_m[1]),
                        float(gnss_ned_m[2]),
                    )
                else:
                    la, lo, hh = llh_offset_north(
                        lat_deg, lon_deg, h_m, gnss_north_m
                    )
            if any(float(v) for v in gnss_motion_ned):
                origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
                moved = ecef_plus_ned(
                    origin,
                    float(gnss_motion_ned[0]) * t_s,
                    float(gnss_motion_ned[1]) * t_s,
                    float(gnss_motion_ned[2]) * t_s,
                )
                mlat, mlon, mh = _ecef_to_geodetic(moved[0], moved[1], moved[2])
                la, lo, hh = math.degrees(mlat), math.degrees(mlon), mh
            if junk_then_north_m and junk_at is not None and k > junk_at:
                la, lo, hh = llh_offset_north(
                    lat_deg, lon_deg, h_m, junk_then_north_m
                )
            vn, ve, vd = (
                float(gnss_vel_ned[0]),
                float(gnss_vel_ned[1]),
                float(gnss_vel_ned[2]),
            )
            if (
                gnss_vel_after_s is not None
                and gnss_vel_after_ned is not None
                and t_s + 1.0e-12 >= gnss_vel_after_s
            ):
                vn = float(gnss_vel_after_ned[0])
                ve = float(gnss_vel_after_ned[1])
                vd = float(gnss_vel_after_ned[2])
            vc = vel_cov6
            if (
                vel_cov_after_s is not None
                and vel_cov_after6 is not None
                and t_s + 1.0e-12 >= vel_cov_after_s
            ):
                vc = vel_cov_after6
            gnss_lines.append(
                f"{t_us},{la:.10f},{lo:.10f},{hh:.6f},"
                f"{pos_cov6[0]},{pos_cov6[1]},{pos_cov6[2]},"
                f"{pos_cov6[3]},{pos_cov6[4]},{pos_cov6[5]},"
                f"{vn},{ve},{vd},"
                f"{vc[0]},{vc[1]},{vc[2]},"
                f"{vc[3]},{vc[4]},{vc[5]},{vel_ok}\n"
            )
            if junk_at is not None and k == junk_at:
                gnss_lines.append("# comment line inside the GNSS stream\n")
                gnss_lines.append("bad,gnss,row\n")
        if write_mag and mag_frd is not None and k % mag_every == 0:
            mag_lines.append(
                f"{t_us},{mag_frd[0]:.9g},{mag_frd[1]:.9g},{mag_frd[2]:.9g}\n"
            )
        if write_baro and baro_pa is not None and k % baro_every == 0:
            p_now = float(baro_pa)
            if (
                baro_after_s is not None
                and baro_after_pa is not None
                and t_s + 1.0e-12 >= baro_after_s
            ):
                p_now = float(baro_after_pa)
            baro_lines.append(f"{t_us},{p_now:.6f}\n")
        if write_speed and k % gnss_every == 0:
            v_now = float(speed_mps)
            if (
                speed_after_s is not None
                and speed_after_mps is not None
                and t_s + 1.0e-12 >= speed_after_s
            ):
                v_now = float(speed_after_mps)
            if speed_extra_columns:
                speed_lines.append(f"{t_us},{v_now:.6f},8000,0.0001\n")
            else:
                speed_lines.append(f"{t_us},{v_now:.6f}\n")
    if write_imu:
        (dest / imu_name).write_text("".join(imu_lines), encoding="utf-8")
    if write_ref:
        (dest / ref_name).write_text("".join(ref_lines), encoding="utf-8")
    if write_gnss:
        (dest / gnss_name).write_text("".join(gnss_lines), encoding="utf-8")
    if write_mag:
        (dest / "mag.csv").write_text("".join(mag_lines), encoding="utf-8")
    if write_baro:
        (dest / "baro.csv").write_text("".join(baro_lines), encoding="utf-8")
    if write_speed:
        (dest / "speed.csv").write_text("".join(speed_lines), encoding="utf-8")
    if decoy_gnss_llh is not None:
        dlat, dlon, dh = decoy_gnss_llh
        decoy = [_GNSS_HEADER]
        for k in range(0, n_pad + 1, gnss_every):
            t_us = k * step_us
            decoy.append(
                f"{t_us},{dlat:.10f},{dlon:.10f},{dh:.6f},"
                f"4,0,0,4,0,4,0,0,0,0.04,0,0,0.04,0,0.04,1\n"
            )
        (dest / "gnss.csv").write_text("".join(decoy), encoding="utf-8")
    if decoy_imu:
        decoy_imu_lines = [_IMU_HEADER, "0,0,0,0,0,0,-9.81\n"]
        (dest / "imu.csv").write_text("".join(decoy_imu_lines), encoding="utf-8")
    cfg: list[str] = [f"name: {relpath}", f"aiding: {aiding}", f"init: {init}"]
    if extra_top_key:
        cfg.append(f"{extra_top_key}: 1")
    if origin_section:
        # PRD names this foreign block as the local-frame origin section.
        cfg.extend(
            [
                "origin:",
                f"  lat_deg: {_fmt_yaml_float(float(lat_deg))}",
                f"  lon_deg: {_fmt_yaml_float(float(lon_deg))}",
                f"  h_m: {_fmt_yaml_float(float(h_m))}",
            ]
        )
    if radio_link_section:
        # PRD names this foreign block as the radio-link section: accepted
        # and ignored. Nested keys are unused by either replay harness.
        cfg.extend(
            [
                f"{RADIO_LINK_SECTION}:",
                "  uri: radio://0/80/2M/00AABBCCDD",
            ]
        )
    cfg.extend(
        [
            "chi2_disable: 1",
            "imu:",
        ]
    )
    if not omit_optional:
        cfg.insert(-1, "allow_unlimited_deadreckoning: 0")
    if omit_spectral:
        cfg.append("  auto_zupt_disable: 1")
    elif spectral_zero:
        cfg.extend(
            [
                "  gyr_psd: 0",
                "  acc_psd: 0",
                "  auto_zupt_disable: 1",
            ]
        )
    else:
        cfg.extend(
            [
                "  gyr_psd: 2.5e-09",
                "  acc_psd: 4.0e-06",
                "  gyr_bias_rw: 3.0e-06",
                "  acc_bias_rw: 0.0001",
                "  auto_zupt_disable: 1",
            ]
        )
    if extra_imu_key:
        cfg.append(f"  {extra_imu_key}: 1")
    cfg.append("gnss:")
    if not omit_optional:
        cfg.append("  delay_ms: 0")
    cfg.append("  leverarm_frd: [0.0, 0.0, 0.0]")
    if pos_fallback_m is not None:
        cfg.append(
            "  pos_stddev_fallback_m: "
            f"[{_fmt_yaml_float(float(pos_fallback_m[0]))}, "
            f"{_fmt_yaml_float(float(pos_fallback_m[1]))}]"
        )
    if vel_fallback_mps is not None:
        cfg.append(f"  vel_stddev_fallback_mps: {_fmt_yaml_float(float(vel_fallback_mps))}")
    cfg.extend(
        [
            "mag:",
            f"  enable: {1 if write_mag else 0}",
            "baro:",
            f"  enable: {1 if write_baro else 0}",
            "speed:",
            f"  enable: {1 if write_speed else 0}",
        ]
    )
    if speed_delay_ms is not None:
        cfg.append(f"  delay_ms: {_fmt_yaml_float(float(speed_delay_ms))}")
    if speed_stddev_mps is not None:
        cfg.append(f"  stddev_mps: {_fmt_yaml_float(float(speed_stddev_mps))}")
    cfg.extend(
        [
            "score:",
            f"  warmup_sec: {_fmt_yaml_float(float(warmup_sec))}",
        ]
    )
    if min_epochs is not None:
        cfg.append(f"  min_epochs: {int(min_epochs)}")
    cfg.append(f"  ahrs: {int(score_ahrs)}")
    cfg.append(f"  attitude: {int(score_attitude)}")
    if lim_pos_rms_m is not None:
        cfg.append(f"  lim_pos_rms_m: {_fmt_yaml_float(float(lim_pos_rms_m))}")
    if lim_baro_rms_m is not None:
        cfg.append(f"  lim_baro_rms_m: {_fmt_yaml_float(float(lim_baro_rms_m))}")
    if lim_att_bias_deg is not None:
        cfg.append(f"  lim_att_bias_deg: {_fmt_yaml_float(float(lim_att_bias_deg))}")
        cfg.append("  lim_att_std_deg: 45")
        yaw_lim = float(lim_att_bias_deg) if lim_yaw_bias_deg is None else float(lim_yaw_bias_deg)
        cfg.append(f"  lim_yaw_bias_deg: {_fmt_yaml_float(yaw_lim)}")
        cfg.append("  lim_yaw_std_deg: 45")
    elif lim_yaw_bias_deg is not None:
        cfg.append(f"  lim_yaw_bias_deg: {_fmt_yaml_float(float(lim_yaw_bias_deg))}")
        cfg.append("  lim_yaw_std_deg: 45")
    if score_ahrs:
        cfg.extend(
            [
                "  lim_ars_att_bias_deg: 45",
                "  lim_ars_roll_std_deg: 45",
                "  lim_ars_pitch_std_deg: 45",
                "  lim_ars_yaw_drift_deg_min: 180",
            ]
        )
    if inputs:
        cfg.append("inputs:")
        for stream, name in inputs.items():
            cfg.append(f"  {stream}: {name}")
    cfg.append("")
    (dest / "config.yaml").write_text("\n".join(cfg), encoding="utf-8")
    (dest / "_imu_times.txt").write_text(
        "\n".join(str(t) for t in imu_times) + "\n", encoding="utf-8"
    )
    return dest


def imu_times_from_dataset(dataset: Path) -> list[int]:
    stamp = dataset / "_imu_times.txt"
    if stamp.is_file():
        rows = []
        for line in stamp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(int(line))
        if not rows:
            raise HarnessError(f"imu time list is empty in {stamp}")
        return rows
    imu_path = dataset / "imu.csv"
    if not imu_path.is_file():
        raise HarnessError(f"dataset has no IMU stream at {imu_path}")
    times = []
    for raw in imu_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            times.append(int(float(line.split(",")[0])))
        except ValueError:
            continue
    if not times:
        raise HarnessError(f"IMU stream has no numeric timestamps in {imu_path}")
    return times


def _dump_cells(parts: Sequence[str], lo: int, hi: int, line: str, what: str):
    """Cells [lo, hi) as floats, or None when that group is unpublished.

    The Contract says an epoch whose solution is unpublished writes no row.
    An empty cell or a non-finite value in a written row is read the same
    way (unpublished), so the dump's spelling of "no value" never decides a
    result. Text that is not a number is still a malformed dump.
    """
    cells = parts[lo:hi]
    if len(cells) < hi - lo:
        return None
    values = []
    for cell in cells:
        if cell == "":
            return None
        try:
            values.append(float(cell))
        except ValueError:
            note_product_issue("F10", f"--dump-solution {what} is not numeric: {line}")
            return None
    if not all(math.isfinite(v) for v in values):
        return None
    return tuple(values)


def parse_replay_series(path: Path) -> tuple[SeriesPoint, ...]:
    """Read a dumped solution series: the published epochs only.

    Missing file, short or non-numeric rows raise. A row whose lat/lon/h is
    empty or non-finite is an unpublished epoch, the same as an omitted row.
    """
    if not path.is_file():
        raise HarnessError(f"replay wrote no solution file at {path}")
    points: list[SeriesPoint] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            note_product_issue("F10", f"--dump-solution row is short: {line}")
            continue
        try:
            t_us = int(float(parts[0]))
        except ValueError:
            note_product_issue("F10", f"--dump-solution time field is not numeric: {line}")
            continue
        llh = _dump_cells(parts, 1, 4, line, "lat/lon/h")
        if llh is None:
            continue
        lat, lon, h = llh
        roll = pitch = yaw = None
        vel_ned = None
        rpy = _dump_cells(parts, 4, 7, line, "attitude")
        if rpy is not None:
            roll, pitch, yaw = rpy
        vel = _dump_cells(parts, 7, 10, line, "NED velocity")
        if vel is not None:
            vel_ned = vel
        points.append(
            SeriesPoint(
                t_us=t_us,
                lat_deg=lat,
                lon_deg=lon,
                h_m=h,
                roll_deg=roll,
                pitch_deg=pitch,
                yaw_deg=yaw,
                vel_ned=vel_ned,
            )
        )
    return tuple(points)


def python_replay_series(
    dataset: Path,
    dump_path: Path,
    *,
    target: str | Path | None = None,
    timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
) -> ReplaySeries:
    """Run Python replay and return the whole dumped series. Non-zero raises."""
    entry = target if target is not None else dataset
    result = run_replay(
        entry,
        ["--dump-solution", str(dump_path), *DUMP_EVERY_EPOCH],
        timeout=timeout,
    )
    if result.returncode != 0:
        text = reporting_text(result)
        raise HarnessError(
            f"python replay exited {result.returncode} report={text[-1800:]!r}"
        )
    points = parse_replay_series(dump_path)
    if not points:
        text = reporting_text(result)
        raise HarnessError(
            "python replay wrote no solution rows; report was:\n" + text[-1800:]
        )
    print(
        f"python series n={len(points)} t0={points[0].t_us} t1={points[-1].t_us} "
        f"last_llh={points[-1].lat_deg:.8f},{points[-1].lon_deg:.8f},{points[-1].h_m:.3f}",
        flush=True,
    )
    return ReplaySeries(points=points, result=result)


def python_replay_result(
    dataset: Path,
    *,
    target: str | Path | None = None,
    dump_path: Path | None = None,
    timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
) -> RunResult:
    """Run Python replay without turning a non-zero product exit into silence."""
    entry = target if target is not None else dataset
    args: list[str] = []
    if dump_path is not None:
        args.extend(["--dump-solution", str(dump_path), *DUMP_EVERY_EPOCH])
    return run_replay(entry, args or None, timeout=timeout)


def c_replay(
    dataset: Path,
    *,
    errdump: Path | None = None,
    timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
) -> RunResult:
    """Run the C harness. A missing binary raises FileNotFoundError (no skip)."""
    args = [str(errdump)] if errdump is not None else None
    result = run_c_replay(dataset, args, timeout=timeout)
    text = reporting_text(result)
    print(
        f"c replay rc={result.returncode} dataset={dataset} tail={text[-500:]!r}",
        flush=True,
    )
    return result


def series_covers_imu_log(series: ReplaySeries, imu_times: Sequence[int]) -> None:
    """Published series reaches the IMU-log end and is not a one- or two-point fixture.

    Fused lat/lon/height is only written once 3D exists (after the entry dwell),
    so the first dumped sample is not required to sit at the first IMU stamp.
    """
    if not imu_times:
        raise HarnessError("IMU time list is empty")
    pts = series.points
    imu0, imu1 = imu_times[0], imu_times[-1]
    span = max(imu1 - imu0, 1)
    print(
        f"cover imu n={len(imu_times)} [{imu0},{imu1}] "
        f"sol n={len(pts)} [{pts[0].t_us},{pts[-1].t_us}]",
        flush=True,
    )
    assert pts[-1].t_us >= imu1 - span // 20, (
        f"solution ends before the IMU log band: sol1={pts[-1].t_us} imu1={imu1}"
    )
    assert pts[0].t_us < pts[-1].t_us, "solution series has no time span"
    assert len(pts) > 2, f"solution is not a log-length series: n={len(pts)}"
    assert len(pts) >= max(8, int(len(imu_times) * SERIES_MIN_FRAC)), (
        f"solution count {len(pts)} is not in the IMU-log band of {len(imu_times)}"
    )


def series_near_llh(
    series: ReplaySeries,
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    what: str,
    max_m: float = PAD_NEAR_M,
    tail_frac: float = 0.25,
) -> float:
    """Mean ECEF error of the converged tail versus a written lat/lon/height."""
    want = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    pts = series.points
    start = max(0, int(len(pts) * (1.0 - tail_frac)))
    tail = pts[start:]
    errors = [hypot3(ecef_from_llh_deg(p.lat_deg, p.lon_deg, p.h_m), want) for p in tail]
    err = sum(errors) / len(errors)
    print(f"{what}: tail ecef err={err:.3f} m (n={len(tail)})", flush=True)
    assert err < max_m, f"{what}: fused tail is {err:.3f} m from the written pad"
    return err


def finite_rpy(series: ReplaySeries, what: str) -> None:
    n = 0
    for p in series.points:
        if p.roll_deg is None or p.pitch_deg is None:
            continue
        if not (math.isfinite(p.roll_deg) and math.isfinite(p.pitch_deg)):
            raise HarnessError(f"{what}: attitude is not finite at t={p.t_us}")
        n += 1
    print(f"{what}: finite roll/pitch rows={n}", flush=True)
    assert n > 2, f"{what}: ARS attitude was not published across the log"


def _header_index(header: Sequence[str], name: str) -> int | None:
    """Index of the column whose header is exactly *name* (Contract section 6)."""
    names = [h.strip() for h in header]
    return names.index(name) if name in names else None


def _finite_cell(row: Sequence[str], index: int | None) -> float | None:
    if index is None or index >= len(row):
        return None
    raw = row[index].strip()
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        # Contract: an unpublished value is an empty cell; other text is
        # recorded for the dedicated test and read as unpublished here.
        note_product_issue("F10", f"runner cell {raw!r} is neither a number nor empty")
        return None
    if not math.isfinite(value):
        # Contract: an unpublished value is an empty cell. A non-finite
        # value is read the same way so the spelling never decides a result.
        return None
    return value


def parse_runner_solution(path: Path) -> tuple[RunnerEpoch, ...]:
    """Read the runner CSV. Missing mode / lat-lon-h / NED / attitude / height raises."""
    if not path.is_file():
        raise HarnessError(f"runner wrote no solution file at {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise HarnessError(f"runner solution file is empty: {path}")
    start = 0
    header: list[str] | None = None
    first = rows[0]
    if first and first[0].strip().startswith("#"):
        start = 1
        first = rows[start] if start < len(rows) else []
    if first:
        try:
            float(first[0])
        except ValueError:
            header = [c.strip() for c in first]
            start += 1
    if header is None:
        raise HarnessError(
            f"runner solution has no header naming mode/lat/lon/height: {path}"
        )
    i_mode = _header_index(header, "mode")
    i_t = _header_index(header, "t_us")
    i_lat = _header_index(header, "lat_deg")
    i_lon = _header_index(header, "lon_deg")
    i_h = _header_index(header, "h_ell_m")
    i_n = _header_index(header, "pos_n_m")
    i_e = _header_index(header, "pos_e_m")
    i_d = _header_index(header, "pos_d_m")
    i_vn = _header_index(header, "vel_n_mps")
    i_ve = _header_index(header, "vel_e_mps")
    i_vd = _header_index(header, "vel_d_mps")
    i_roll = _header_index(header, "roll_deg")
    i_pitch = _header_index(header, "pitch_deg")
    i_yaw = _header_index(header, "yaw_deg")
    i_arb = _header_index(header, "height_m")
    missing = []
    if i_t is None:
        missing.append("t_us")
    if i_mode is None:
        missing.append("mode")
    if i_lat is None or i_lon is None or i_h is None:
        missing.append("lat/lon/h")
    if i_n is None or i_e is None or i_d is None:
        missing.append("NED position")
    if i_vn is None or i_ve is None or i_vd is None:
        missing.append("NED velocity")
    if i_roll is None or i_pitch is None or i_yaw is None:
        missing.append("roll/pitch/yaw")
    if i_arb is None:
        missing.append("arbitrated height")
    if missing:
        raise HarnessError(
            f"runner solution is missing {missing} (header={header!r})"
        )
    epochs: list[RunnerEpoch] = []
    for raw in rows[start:]:
        if not raw or (raw[0].strip().startswith("#")):
            continue
        mode = raw[i_mode].strip() if i_mode < len(raw) else ""
        if not mode:
            note_product_issue("F10", f"runner row has no mode: {raw!r}")
        t_raw = raw[i_t].strip() if i_t < len(raw) else ""
        try:
            t_us = int(float(t_raw))
        except ValueError as exc:
            raise HarnessError(f"runner time is not numeric: {t_raw!r}") from exc
        lat = _finite_cell(raw, i_lat)
        lon = _finite_cell(raw, i_lon)
        h = _finite_cell(raw, i_h)
        n = _finite_cell(raw, i_n)
        e = _finite_cell(raw, i_e)
        d = _finite_cell(raw, i_d)
        vn = _finite_cell(raw, i_vn)
        ve = _finite_cell(raw, i_ve)
        vd = _finite_cell(raw, i_vd)
        roll = _finite_cell(raw, i_roll)
        pitch = _finite_cell(raw, i_pitch)
        yaw = _finite_cell(raw, i_yaw)
        arb = _finite_cell(raw, i_arb)
        ned_pos = (n, e, d) if None not in (n, e, d) else None
        ned_vel = (vn, ve, vd) if None not in (vn, ve, vd) else None
        epochs.append(
            RunnerEpoch(
                t_us=t_us,
                mode=mode,
                lat_deg=lat,
                lon_deg=lon,
                h_m=h,
                ned_pos=ned_pos,
                ned_vel=ned_vel,
                roll_deg=roll,
                pitch_deg=pitch,
                yaw_deg=yaw,
                arb_height_m=arb,
            )
        )
    if not epochs:
        raise HarnessError(f"runner solution had no data rows at {path}")
    print(f"runner solution n={len(epochs)} last_mode={epochs[-1].mode}", flush=True)
    return tuple(epochs)


def write_runner_mapping(
    ws: Workspace,
    *,
    relpath: str,
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    duration_s: float = NAMED_PAD_S,
    time_unit: str = "s",
    gyro_unit: str = "deg/s",
    accel_unit: str = "m/s2",
    pressure_unit: str = "hPa",
    mag_unit: str = "uT",
    gnss_format: str = "llh_deg",
    imu_hz: int = IMU_HZ,
    gnss_hz: int = GNSS_HZ,
    baro_hz: int = 10,
    mag_hz: int = 10,
    gyro_z: float = 0.0,
    mag_frd: Sequence[float] = (0.0, 0.0, 0.0),
    pressure_pa: float = 101325.0,
    swap_time_lat: bool = False,
    swap_time_gyro: bool = False,
    gnss_north_after_s: float | None = None,
    gnss_north_m: float = 0.0,
    n_imu: int | None = None,
    time_scale: float | None = None,
    include_mag: bool = True,
    include_baro: bool = True,
    include_gnss: bool = True,
    acc_frd: Sequence[float] | None = None,
    pressure_after_s: float | None = None,
    pressure_after_pa: float | None = None,
    mag_after_s: float | None = None,
    mag_after_frd: Sequence[float] | None = None,
    disable_auto_zupt: bool = False,
    extra_imu_s: float = 0.0,
    gap_north_acc: float = 0.0,
    gnss_vel_ned: Sequence[float] | None = None,
) -> tuple[Path, Path]:
    """Write arbitrary CSVs plus a runner YAML. Returns (yaml path, solution path)."""
    dest = ws.resolve(relpath)
    dest.mkdir(parents=True, exist_ok=True)
    extra_n = int(round(extra_imu_s * imu_hz)) if extra_imu_s > 0.0 else 0
    if n_imu is None:
        n_imu = int(round(duration_s * imu_hz)) + extra_n
        dt = 1.0 / imu_hz
    else:
        dt = duration_s / float(n_imu) if duration_s > 0.0 else 1.0 / imu_hz
    if time_scale is None:
        lowered = time_unit.lower().replace("µ", "u").replace("μ", "u")
        if lowered in ("s", "sec"):
            time_scale = 1.0
        elif lowered in ("ms",):
            time_scale = 1.0e3
        else:
            time_scale = 1.0e6
    g0 = G_MPS2
    acc_si = SPECIFIC_FORCE_LEVEL
    if acc_frd is not None:
        acc_csv = (float(acc_frd[0]), float(acc_frd[1]), float(acc_frd[2]))
    elif accel_unit.lower() in ("g",):
        acc_csv = (acc_si[0] / g0, acc_si[1] / g0, acc_si[2] / g0)
    else:
        acc_csv = acc_si
    gyro_csv = (0.0, 0.0, gyro_z)
    mag_scale = {
        "ut": 1.0,
        "µt": 1.0,
        "μt": 1.0,
        "gauss": 1.0 / 100.0,
        "milligauss": 10.0,
        "mgauss": 10.0,
        "nt": 1000.0,
    }
    key = mag_unit.lower().replace("µ", "u").replace("μ", "u")
    mscale = mag_scale.get(key, mag_scale.get(mag_unit.lower(), 1.0))
    mag_csv = (mag_frd[0] * mscale, mag_frd[1] * mscale, mag_frd[2] * mscale)
    pscale = {
        "pa": 1.0,
        "hpa": 0.01,
        "mbar": 0.01,
        "kpa": 0.001,
    }
    pkey = pressure_unit.lower()
    pressure_csv = pressure_pa * pscale.get(pkey, 1.0)
    imu_path = dest / "imu.csv"
    gnss_path = dest / "gnss.csv"
    baro_path = dest / "baro.csv"
    mag_path = dest / "mag.csv"
    sol_path = dest / "solution.csv"
    imu_rows: list[list[str]] = []
    imu_header = ["t", "gx", "gy", "gz", "ax", "ay", "az"]
    acc_gap = (float(gap_north_acc), acc_csv[1], acc_csv[2])
    for k in range(n_imu):
        t_s = k * dt
        t_val = t_s * time_scale
        acc_now = acc_gap if extra_imu_s > 0.0 and t_s > duration_s + 1.0e-9 else acc_csv
        row = [
            f"{t_val:.9g}",
            f"{gyro_csv[0]:.9g}",
            f"{gyro_csv[1]:.9g}",
            f"{gyro_csv[2]:.9g}",
            f"{acc_now[0]:.9g}",
            f"{acc_now[1]:.9g}",
            f"{acc_now[2]:.9g}",
        ]
        imu_rows.append(row)
    if swap_time_gyro:
        imu_header = ["gx", "gy", "gz", "t", "ax", "ay", "az"]
        swapped = []
        for row in imu_rows:
            swapped.append([row[1], row[2], row[3], row[0], row[4], row[5], row[6]])
        imu_rows = swapped
        time_col: str | int = "t"
        gyr_cols: list[str | int] = ["gx", "gy", "gz"]
    else:
        time_col = 0
        gyr_cols = [1, 2, 3]
    with imu_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(imu_header)
        writer.writerows(imu_rows)
    gnss_header = ["t", "lat", "lon", "h", "sn", "se", "sd"]
    gnss_rows: list[list[str]] = []
    n_gnss = max(1, int(round(duration_s * gnss_hz)))
    for k in range(n_gnss):
        t_s = (k + 0.5) / gnss_hz
        la, lo, hh = lat_deg, lon_deg, h_m
        if gnss_north_after_s is not None and t_s + 1.0e-12 >= gnss_north_after_s:
            la, lo, hh = llh_offset_north(lat_deg, lon_deg, h_m, gnss_north_m)
        t_val = t_s * time_scale
        if gnss_format == "llh_rad":
            pos = (math.radians(la), math.radians(lo), hh)
        elif gnss_format == "ecef":
            pos = ecef_from_llh_deg(la, lo, hh)
        else:
            pos = (la, lo, hh)
        row = [
            f"{t_val:.9g}",
            f"{pos[0]:.12g}",
            f"{pos[1]:.12g}",
            f"{pos[2]:.12g}",
            "2.0",
            "2.0",
            "2.0",
        ]
        if gnss_vel_ned is not None:
            row.extend(
                [
                    f"{float(gnss_vel_ned[0]):.9g}",
                    f"{float(gnss_vel_ned[1]):.9g}",
                    f"{float(gnss_vel_ned[2]):.9g}",
                ]
            )
        gnss_rows.append(row)
    if gnss_vel_ned is not None:
        gnss_header = gnss_header + ["vn", "ve", "vd"]
    if swap_time_lat:
        gnss_header = ["lat", "t", "lon", "h", "sn", "se", "sd"]
        swapped_g = []
        for row in gnss_rows:
            swapped_g.append([row[1], row[0], row[2], row[3], row[4], row[5], row[6]])
        gnss_rows = swapped_g
        gnss_time_col: str | int = "t"
        pos_cols: list[str | int] = ["lat", "lon", "h"]
    else:
        gnss_time_col = 0
        pos_cols = [1, 2, 3]
    with gnss_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(gnss_header)
        writer.writerows(gnss_rows)
    with baro_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["t", "p"])
        n_baro = max(1, int(round(duration_s * baro_hz)))
        for k in range(n_baro):
            t_s = k / baro_hz
            p_now = pressure_csv
            if (
                pressure_after_s is not None
                and pressure_after_pa is not None
                and t_s + 1.0e-12 >= pressure_after_s
            ):
                p_now = pressure_after_pa * pscale.get(pkey, 1.0)
            writer.writerow([f"{t_s * time_scale:.9g}", f"{p_now:.9g}"])
    mag_after_csv = None
    if mag_after_frd is not None:
        mag_after_csv = (
            mag_after_frd[0] * mscale,
            mag_after_frd[1] * mscale,
            mag_after_frd[2] * mscale,
        )
    with mag_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["t", "mx", "my", "mz"])
        n_mag = max(1, int(round(duration_s * mag_hz)))
        for k in range(n_mag):
            t_s = k / mag_hz
            mx, my, mz = mag_csv
            if mag_after_csv is not None and mag_after_s is not None and t_s + 1.0e-12 >= mag_after_s:
                mx, my, mz = mag_after_csv
            writer.writerow(
                [
                    f"{t_s * time_scale:.9g}",
                    f"{mx:.9g}",
                    f"{my:.9g}",
                    f"{mz:.9g}",
                ]
            )
    if swap_time_gyro:
        gyr_yaml = (
            f"{{cols: [{gyr_cols[0]}, {gyr_cols[1]}, {gyr_cols[2]}], "
            f"unit: {json.dumps(gyro_unit)}}}"
        )
        time_yaml = f"{{col: {json.dumps(time_col) if isinstance(time_col, str) else time_col}, unit: {json.dumps(time_unit)}}}"
        acc_yaml = "{cols: [ax, ay, az], unit: " + json.dumps(accel_unit) + "}"
    else:
        gyr_yaml = f"{{cols: [1, 2, 3], unit: {json.dumps(gyro_unit)}}}"
        time_yaml = f"{{col: 0, unit: {json.dumps(time_unit)}}}"
        acc_yaml = "{cols: [4, 5, 6], unit: " + json.dumps(accel_unit) + "}"
    if swap_time_lat:
        gnss_time_yaml = (
            f"{{col: {json.dumps(gnss_time_col) if isinstance(gnss_time_col, str) else gnss_time_col}, "
            f"unit: {json.dumps(time_unit)}}}"
        )
        pos_yaml = f"{{cols: [{json.dumps(pos_cols[0])}, {json.dumps(pos_cols[1])}, {json.dumps(pos_cols[2])}]}}"
    else:
        gnss_time_yaml = f"{{col: 0, unit: {json.dumps(time_unit)}}}"
        pos_yaml = "{cols: [1, 2, 3]}"
    vel_yaml = ""
    if gnss_vel_ned is not None and not swap_time_lat:
        vel_yaml = "  vel_ned: {cols: [7, 8, 9], unit: m/s}"
    yaml_lines = [
        "imu:",
        "  file: imu.csv",
        f"  time: {time_yaml}",
        f"  gyr:  {gyr_yaml}",
        f"  acc:  {acc_yaml}",
    ]
    if include_gnss:
        yaml_lines.extend(
            [
                "gnss:",
                "  file: gnss.csv",
                f"  format: {gnss_format}",
                f"  time: {gnss_time_yaml}",
                f"  pos:  {pos_yaml}",
                "  stddev_ned: {cols: [4, 5, 6], unit: m}",
            ]
        )
        if vel_yaml:
            yaml_lines.append(vel_yaml)
    if include_baro:
        yaml_lines.extend(
            [
                "baro:",
                "  file: baro.csv",
                f"  time: {{col: 0, unit: {json.dumps(time_unit)}}}",
                f"  pressure: {{col: 1, unit: {json.dumps(pressure_unit)}}}",
            ]
        )
    if include_mag:
        yaml_lines.extend(
            [
                "mag:",
                "  file: mag.csv",
                f"  time: {{col: 0, unit: {json.dumps(time_unit)}}}",
                f"  mag: {{cols: [1, 2, 3], unit: {json.dumps(mag_unit)}}}",
            ]
        )
    yaml_lines.extend(
        [
            "wmm:",
            "  year: 2026.5",
        ]
    )
    if disable_auto_zupt:
        yaml_lines.extend(
            [
                "filter:",
                "  auto_zupt_disable: 1",
            ]
        )
    yaml_lines.extend(
        [
            "output:",
            "  plotjuggler: false",
            "  mavlink: false",
            "  csv: solution.csv",
            "  csv_hz: 0",
            "",
        ]
    )
    yaml_text = "\n".join(yaml_lines)
    yaml_path = dest / "run.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    return yaml_path, sol_path


def run_mapped_runner(
    yaml_path: Path,
    sol_path: Path,
    *,
    timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
) -> tuple[RunResult, tuple[RunnerEpoch, ...]]:
    result = run_runner(yaml_path, timeout=timeout)
    if result.returncode != 0:
        text = reporting_text(result)
        raise HarnessError(
            f"yaml runner exited {result.returncode} report={text[-1800:]!r}"
        )
    epochs = parse_runner_solution(sol_path)
    return result, epochs


def runner_tail_full_near(
    epochs: Sequence[RunnerEpoch],
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    what: str,
    max_m: float = PAD_NEAR_M,
    imu_count: int | None = None,
) -> float:
    if imu_count is not None:
        print(f"{what}: rows={len(epochs)} imu={imu_count}", flush=True)
        assert len(epochs) > 2, f"{what}: runner did not write one row per epoch"
        assert len(epochs) >= max(8, int(imu_count * SERIES_MIN_FRAC)), (
            f"{what}: row count {len(epochs)} is not in the IMU-epoch band {imu_count}"
        )
        if imu_count >= 8:
            assert abs(len(epochs) - imu_count) <= max(2, imu_count // 20), (
                f"{what}: row count {len(epochs)} is not one-per-IMU-epoch ({imu_count})"
            )
    start = max(0, int(len(epochs) * 0.75))
    tail = epochs[start:]
    full = [e for e in tail if e.mode == MODE_FULL]
    print(f"{what}: tail={len(tail)} full={len(full)} last={epochs[-1].mode}", flush=True)
    assert full, f"{what}: converged tail never published {MODE_FULL}"
    want = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    errors = []
    for e in full:
        if e.lat_deg is None or e.lon_deg is None or e.h_m is None:
            raise HarnessError(f"{what}: FULL row is missing lat/lon/h")
        errors.append(hypot3(ecef_from_llh_deg(e.lat_deg, e.lon_deg, e.h_m), want))
        if e.ned_pos is None or e.ned_vel is None:
            raise HarnessError(f"{what}: FULL row is missing NED position/velocity")
        if e.roll_deg is None or e.pitch_deg is None or e.yaw_deg is None:
            raise HarnessError(f"{what}: FULL row is missing roll/pitch/yaw")
        if e.arb_height_m is None:
            raise HarnessError(f"{what}: FULL row is missing arbitrated height")
    err = sum(errors) / len(errors)
    print(f"{what}: FULL tail ecef err={err:.3f} m", flush=True)
    assert err < max_m, f"{what}: FULL tail is {err:.3f} m from the GNSS pad"
    return err


def runner_last_at_or_before(
    epochs: Sequence[RunnerEpoch], t_us: int
) -> RunnerEpoch:
    last = None
    for e in epochs:
        if e.t_us <= t_us:
            last = e
        else:
            break
    if last is None:
        raise HarnessError(f"no runner epoch at or before {t_us}")
    return last


def yaw_abs_diff_deg(a: float, b: float) -> float:
    return abs(angle_diff_deg(a, b))


def mean_abs_yaw_step_deg(
    epochs: Sequence[RunnerEpoch], t0_us: int, t1_us: int
) -> float:
    """Mean |Δyaw| between consecutive samples in [t0, t1]. Wrap-safe; not a heading pin."""
    rows = [e for e in epochs if t0_us <= e.t_us <= t1_us and e.yaw_deg is not None]
    if len(rows) < 8:
        raise HarnessError(
            f"not enough yaw samples in [{t0_us},{t1_us}] n={len(rows)}"
        )
    steps = [
        abs(angle_diff_deg(b.yaw_deg, a.yaw_deg)) for a, b in zip(rows, rows[1:])
    ]
    mean = sum(steps) / len(steps)
    print(
        f"mean abs yaw step [{t0_us},{t1_us}]={mean:.4f} deg n={len(steps)}",
        flush=True,
    )
    return mean


def classified_unpublished_3d(
    dump_path: Path,
    result: RunResult,
    what: str,
) -> tuple[SeriesPoint, ...]:
    """Replay succeeded and the dump is unpublished 3D — not a missing/malformed sentinel."""
    text = reporting_text(result)
    if result.returncode != 0:
        raise AssertionError(
            f"{what}: replay exited {result.returncode}; cannot classify unpublished 3D: "
            f"{text[-1500:]!r}"
        )
    if not dump_path.is_file() or not dump_path.read_text(encoding="utf-8").strip():
        raise AssertionError(
            f"{what}: dump is missing or empty; cannot classify unpublished 3D"
        )
    points = parse_replay_series(dump_path)
    if points:
        last = points[-1]
        print(
            f"{what}: published 3D n={len(points)} last="
            f"{last.lat_deg:.6f},{last.lon_deg:.6f},{last.h_m:.3f}",
            flush=True,
        )
        raise AssertionError(
            f"{what}: INS published a 3D series (n={len(points)}); "
            "expected unpublished 3D for the whole log"
        )
    print(f"{what}: classified unpublished 3D (parsed dump, no published rows)", flush=True)
    return points


def classified_non_full_runner(
    sol_path: Path,
    result: RunResult,
    what: str,
) -> tuple[RunnerEpoch, ...]:
    """Runner succeeded and the parsed series has no FULL row — not an empty sentinel."""
    text = reporting_text(result)
    if result.returncode != 0:
        raise AssertionError(
            f"{what}: runner exited {result.returncode}; cannot classify non-FULL: "
            f"{text[-1500:]!r}"
        )
    epochs = parse_runner_solution(sol_path)
    if not epochs:
        raise AssertionError(
            f"{what}: solution file parsed to zero rows; cannot classify non-FULL"
        )
    full = [e for e in epochs if e.mode == MODE_FULL]
    print(f"{what}: parsed n={len(epochs)} FULL={len(full)} last={epochs[-1].mode}", flush=True)
    assert not full, f"{what}: short span still reached {MODE_FULL} ({len(full)} rows)"
    return epochs


_FINAL_MODE_RE = re.compile(
    r"^\s*final nav_suite mode:\s*(FULL|COASTING|ATTITUDE_ONLY|NONE)\s*$",
    re.MULTILINE,
)


def reported_final_mode(result: RunResult, what: str) -> str:
    """The suite's final mode from the pinned ``final nav_suite mode: NAME`` line.

    Contract (replay.py): the report states the final solution mode on that
    one line. Free text elsewhere in the report is never searched for a mode
    name, so an unrelated word such as "FULL" in a summary cannot decide it.
    """
    text = reporting_text(result)
    found = _FINAL_MODE_RE.findall(text)
    print(f"{what}: final-mode lines={found} tail={text[-400:]!r}", flush=True)
    assert found, (
        f"{what}: report has no 'final nav_suite mode: NAME' line: {text[-1200:]!r}"
    )
    return found[-1]


def report_names_mode(result: RunResult, mode: str, what: str) -> None:
    final = reported_final_mode(result, what)
    assert final == mode, f"{what}: final nav_suite mode is {final!r}, expected {mode!r}"


def finite_ars_roll_pitch_from_errdump(path: Path, what: str) -> tuple[float, float]:
    """Read finite ARS roll/pitch from a C errdump. Missing/unparsable raises."""
    if not path.is_file():
        raise HarnessError(f"{what}: C errdump was not written at {path}")
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9:
            raise HarnessError(f"{what}: errdump row is short: {line!r}")
        try:
            roll = float(parts[6])
            pitch = float(parts[7])
        except ValueError as exc:
            raise HarnessError(f"{what}: errdump ARS cells are not numeric: {line!r}") from exc
        if not (math.isfinite(roll) and math.isfinite(pitch)):
            raise HarnessError(f"{what}: errdump ARS roll/pitch is not finite: {line!r}")
        rows.append((roll, pitch))
    print(f"{what}: ARS errdump rows={len(rows)}", flush=True)
    assert rows, f"{what}: ARS attitude was not published on the C errdump"
    return rows[-1]


def require_still_pad_ars(path: Path, what: str, *, max_deg: float = 15.0) -> tuple[float, float]:
    """ARS on a still level pad: finite roll/pitch error stays on that pad."""
    roll, pitch = finite_ars_roll_pitch_from_errdump(path, what)
    print(f"{what}: still-pad ARS roll={roll:.3f} pitch={pitch:.3f}", flush=True)
    assert abs(roll) < max_deg and abs(pitch) < max_deg, (
        f"{what}: ARS dump is not this still pad (roll={roll:.3f} pitch={pitch:.3f})"
    )
    return roll, pitch


def require_errdump_not_written(path: Path, what: str) -> None:
    """A refusal must not write the ARS dump a legal none run produces."""
    if not path.is_file():
        print(f"{what}: dump path absent", flush=True)
        return
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(line)
    print(f"{what}: dump data rows={len(rows)}", flush=True)
    assert not rows, (
        f"{what}: unknown-aiding refusal wrote an ARS dump ({len(rows)} rows)"
    )


def runner_published_local_height_m(
    epochs: Sequence[RunnerEpoch], what: str
) -> float:
    """Last published arbitrated/local height. Missing is observation failure."""
    published = [e.arb_height_m for e in epochs if e.arb_height_m is not None]
    if not published:
        raise HarnessError(f"{what}: local height was not published")
    height = published[-1]
    print(
        f"{what}: published local height={height:.3f} m n={len(published)}",
        flush=True,
    )
    return height


def gap_peak_from_series(
    series: ReplaySeries,
    zoh_llh: tuple[float, float, float],
    after_us: int,
    what: str,
) -> float:
    """Peak ECEF distance of IMU-only samples after after_us from a held LLH."""
    zoh = ecef_from_llh_deg(*zoh_llh)
    gap = [p for p in series.points if p.t_us > after_us]
    assert gap, f"{what}: no IMU-only samples after {after_us}"
    moved = [
        hypot3(ecef_from_llh_deg(p.lat_deg, p.lon_deg, p.h_m), zoh) for p in gap
    ]
    peak = max(moved)
    print(f"{what}: gap vs ZOH peak={peak:.3f} m n={len(gap)}", flush=True)
    return peak


def gap_peak_from_runner(
    epochs: Sequence[RunnerEpoch],
    zoh_llh: tuple[float, float, float],
    after_us: int,
    what: str,
) -> float:
    """Peak ECEF distance of runner samples after after_us from a held LLH."""
    zoh = ecef_from_llh_deg(*zoh_llh)
    gap = [
        e
        for e in epochs
        if e.t_us > after_us and e.lat_deg is not None and e.lon_deg is not None and e.h_m is not None
    ]
    assert gap, f"{what}: no runner samples after {after_us}"
    moved = [hypot3(ecef_from_llh_deg(e.lat_deg, e.lon_deg, e.h_m), zoh) for e in gap]
    peak = max(moved)
    print(f"{what}: runner gap vs ZOH peak={peak:.3f} m n={len(gap)}", flush=True)
    return peak


def require_leading_hash_header(path: Path, what: str) -> None:
    """Conventional stream starts with a # header line. Missing file raises."""
    if not path.is_file():
        raise HarnessError(f"{what}: missing stream at {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise HarnessError(f"{what}: stream is empty at {path}")
    first = text.splitlines()[0]
    print(f"{what}: first line={first[:96]!r}", flush=True)
    assert first.lstrip().startswith("#"), (
        f"{what}: conventional stream has no leading # header line"
    )




def yaw_excursion_deg(epochs: Sequence[RunnerEpoch], what: str) -> float:
    """|Δyaw| from first FULL yaw to last FULL yaw. Wrap-safe; not a heading pin."""
    full = [e for e in epochs if e.mode == MODE_FULL and e.yaw_deg is not None]
    assert full, f"{what}: no FULL yaw to measure excursion"
    exc = yaw_abs_diff_deg(full[0].yaw_deg, full[-1].yaw_deg)
    print(
        f"{what}: yaw excursion={exc:.3f} deg first={full[0].yaw_deg:.3f} "
        f"last={full[-1].yaw_deg:.3f}",
        flush=True,
    )
    return exc

