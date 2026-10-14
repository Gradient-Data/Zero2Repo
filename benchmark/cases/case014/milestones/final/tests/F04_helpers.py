# feature: F04
"""Observation helpers for FP-04 delayed aiding.

C probes compile through the sealed harness. Python observations run in a
child interpreter. The GNSS-latency estimator is driven through the Python
replay program. This module does not import the product in the pytest
process. Along-track truth is independent NED/ECEF geometry; estimator
expectation is the lag the test wrote into GNSS vertical velocity.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Sequence

from _harness import (
    nonfinite_fields,
    note_product_issue,
    runtime_uuid_int,
    DEFAULT_REPLAY_TIMEOUT,
    HarnessError,
    RunResult,
    Workspace,
    compile_repository,
    invoke,
    product_identity,
    repo_root,
    run_python,
    run_replay,
)
from F01_helpers import require_probe_success
from F02_helpers import (
    DT_SEC,
    GNSS_HZ,
    GNSS_STD_M,
    HAPPY_DURATION_S,
    IMU_HZ,
    LONG_TIMEOUT,
    SPECIFIC_FORCE_LEVEL,
    _parse_flag,
    _parse_int,
    _parse_vec,
    ecef_from_llh_deg,
    ecef_plus_ned,
    ned_offset_from_two_ecef,
    runtime_site,
)
from F03_helpers import (
    CM_STD_M,
    LOCAL_HZ,
    TRACKER_NAMED_NED,
    isa_pressure_pa,
)

DELAY_TIGHT_STD_M = (0.20, 0.20, 0.20)
DELAY_VEL_STD = (0.08, 0.08, 0.08)
NAMED_DELAY_200_MS = 200
NAMED_DELAY_80_MS = 80
NAMED_DELAY_500_MS = 500
NAMED_DELAY_600_MS = 600
IN_WINDOW_NO_HISTORY_MS = 400
PROBE_AFTER_PAD_S = HAPPY_DURATION_S
ACCEL_S = 2.0
MOTION_S = 4.0
STOP_CRUISE_S = 3.0
STOP_BRAKE_S = 0.15
SHALLOW_IMU = 6
SKIP_HOLD_IMU = 12
YAW_TIGHT_STD_RAD = 0.012
LOCAL_MOVE_STD = (CM_STD_M, CM_STD_M, CM_STD_M)
G_MPS2 = 9.81

_C_PROBE = r"""
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ins.h"

static int fail_read(const char *what)
{
    fprintf(stderr, "probe stdin: %s\n", what);
    return 2;
}

static void print_snap(const ins_t *f, long long t_us)
{
    double ecef[3];
    float ned[3], vel[3], roll, pitch, yaw, bacc[3], bgyr[3];
    int pos = ins_get_position_ecef(f, ecef) ? 1 : 0;
    int vel_ok = ins_get_velocity_ned(f, vel) ? 1 : 0;
    int rpy_ok = ins_get_rpy(f, &roll, &pitch, &yaw) ? 1 : 0;
    int bacc_ok = ins_get_bias_acc(f, bacc) ? 1 : 0;
    int bgyr_ok = ins_get_bias_gyr(f, bgyr) ? 1 : 0;
    int ned_ok = ins_get_position_local(f, ned) ? 1 : 0;
    static const ins_diag_t no_diag;
    const ins_diag_t *d = ins_get_diag(f);
    const int diag_ok = d != NULL ? 1 : 0;
    if (d == NULL) {
        d = &no_diag; /* printed as diag=0; the parser records it */
    }
    printf("SNAP t_us=%lld ready=%d pos=%d vel=%d rpy=%d ned=%d bacc=%d bgyr=%d",
           t_us, ins_is_ready(f) ? 1 : 0, pos, vel_ok, rpy_ok, ned_ok, bacc_ok,
           bgyr_ok);
    printf(" diag=%d", diag_ok);
    if (pos) {
        printf(" ecef=%.17g,%.17g,%.17g", ecef[0], ecef[1], ecef[2]);
    } else {
        printf(" ecef=-");
    }
    if (ned_ok) {
        printf(" nedpos=%.9g,%.9g,%.9g", ned[0], ned[1], ned[2]);
    } else {
        printf(" nedpos=-");
    }
    if (vel_ok) {
        printf(" velned=%.9g,%.9g,%.9g", vel[0], vel[1], vel[2]);
    } else {
        printf(" velned=-");
    }
    if (rpy_ok) {
        printf(" att=%.9g,%.9g,%.9g", roll, pitch, yaw);
    } else {
        printf(" att=-");
    }
    {
        float rsd = 0.0f, psd = 0.0f, ysd = 0.0f;
        int std_ok = ins_get_rpy_stddev(f, &rsd, &psd, &ysd) ? 1 : 0;
        if (std_ok) {
            printf(" attstd=%.9g,%.9g,%.9g", rsd, psd, ysd);
        } else {
            printf(" attstd=-");
        }
    }
    if (bacc_ok) {
        printf(" biasacc=%.9g,%.9g,%.9g", bacc[0], bacc[1], bacc[2]);
    } else {
        printf(" biasacc=-");
    }
    if (bgyr_ok) {
        printf(" biasgyr=%.9g,%.9g,%.9g", bgyr[0], bgyr[1], bgyr[2]);
    } else {
        printf(" biasgyr=-");
    }
    printf(" n_no_anchor=%u n_used=%u\n", d->n_gnss_no_anchor, d->n_gnss_used);
}

int main(void)
{
    char line[8192];
    double ox = 0.0, oy = 0.0, oz = 0.0;
    int auto_init = 1, auto_zupt_disable = 1, chi2_disable = 1;
    double lat_deg = 0.0, lon_deg = 0.0, h_m = 0.0;
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("header1");
    }
    if (sscanf(line, "%lf %lf %lf %d %d %d", &ox, &oy, &oz, &auto_init,
               &auto_zupt_disable, &chi2_disable) != 6) {
        return fail_read("header1 fields");
    }
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("header2");
    }
    if (sscanf(line, "%lf %lf %lf", &lat_deg, &lon_deg, &h_m) != 3) {
        return fail_read("header2 fields");
    }
    (void)lat_deg;
    (void)lon_deg;
    (void)h_m;

    ins_t ins = {0};
    ins_init_t init = {0};
    ins_options_t opt = {0};
    opt.auto_init = auto_init ? true : false;
    opt.auto_zupt_disable = auto_zupt_disable ? true : false;
    opt.chi2_disable = chi2_disable ? true : false;
    opt.gnss_min_delay_ms = -1;
    init.x_ecef[0] = ox;
    init.x_ecef[1] = oy;
    init.x_ecef[2] = oz;

    int rc = ins_init(&ins, &init, &opt);
    printf("INIT rc=%d\n", rc);
    if (rc != 0) {
        print_snap(&ins, 0);
        return 0;
    }

    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        if (line[0] != 'E') {
            return fail_read("epoch tag");
        }
        long long t_us = 0;
        double dt, ax, ay, az, gx, gy, gz;
        int acc_v, gyr_v, gp;
        double e0, e1, e2, sn, se, sd;
        int gv;
        double vn, ve, vd, vsn, vse, vsd;
        int gnss_delay, lp;
        double ln, le, ld, lsn, lse, lsd;
        int local_delay, yw;
        double yaw_rad, ystd;
        int yaw_delay;
        if (sscanf(line,
                   "E %lld %lf %lf %lf %lf %lf %lf %lf %d %d %d %lf %lf %lf %lf "
                   "%lf %lf %d %lf %lf %lf %lf %lf %lf %d %d %lf %lf %lf %lf "
                   "%lf %lf %d %d %lf %lf %d",
                   &t_us, &dt, &ax, &ay, &az, &gx, &gy, &gz, &acc_v, &gyr_v, &gp,
                   &e0, &e1, &e2, &sn, &se, &sd, &gv, &vn, &ve, &vd, &vsn, &vse,
                   &vsd, &gnss_delay, &lp, &ln, &le, &ld, &lsn, &lse, &lsd,
                   &local_delay, &yw, &yaw_rad, &ystd, &yaw_delay) != 37) {
            return fail_read("epoch fields");
        }
        ins_measurements_t m;
        memset(&m, 0, sizeof m);
        m.timestamp = (ins_time_us_t)t_us;
        m.strapdown_dt_sec = (float)dt;
        m.acc.is_valid = acc_v ? true : false;
        m.acc.data[0] = (float)ax;
        m.acc.data[1] = (float)ay;
        m.acc.data[2] = (float)az;
        m.gyr.is_valid = gyr_v ? true : false;
        m.gyr.data[0] = (float)gx;
        m.gyr.data[1] = (float)gy;
        m.gyr.data[2] = (float)gz;
        if (gp) {
            m.gnss_pos.is_valid = true;
            m.gnss_pos.xyz_ecef[0] = e0;
            m.gnss_pos.xyz_ecef[1] = e1;
            m.gnss_pos.xyz_ecef[2] = e2;
            m.gnss_pos.Qll_ned[0] = (float)(sn * sn);
            m.gnss_pos.Qll_ned[4] = (float)(se * se);
            m.gnss_pos.Qll_ned[8] = (float)(sd * sd);
            m.gnss_delay_ms = gnss_delay;
        }
        if (gv) {
            m.gnss_vel.is_valid = true;
            m.gnss_vel.vel_ned[0] = (float)vn;
            m.gnss_vel.vel_ned[1] = (float)ve;
            m.gnss_vel.vel_ned[2] = (float)vd;
            m.gnss_vel.Qll_ned[0] = (float)(vsn * vsn);
            m.gnss_vel.Qll_ned[4] = (float)(vse * vse);
            m.gnss_vel.Qll_ned[8] = (float)(vsd * vsd);
            if (gp) {
                m.gnss_delay_ms = gnss_delay;
            }
        }
        if (lp) {
            m.local_pos.is_valid = true;
            m.local_pos.pos_ned[0] = (float)ln;
            m.local_pos.pos_ned[1] = (float)le;
            m.local_pos.pos_ned[2] = (float)ld;
            m.local_pos.Qll_ned[0] = (float)(lsn * lsn);
            m.local_pos.Qll_ned[4] = (float)(lse * lse);
            m.local_pos.Qll_ned[8] = (float)(lsd * lsd);
            m.local_pos_delay_ms = local_delay;
        }
        if (yw) {
            m.yaw.is_valid = true;
            m.yaw.yaw_rad = (float)yaw_rad;
            m.yaw.stddev_rad = (float)ystd;
            m.yaw_delay_ms = yaw_delay;
        }
        ins_update(&ins, &m);
        print_snap(&ins, t_us);
    }
    return 0;
}
"""

_PY_PROBE = r"""
import math
import sys

from __PKG__ import Config, Ins

def parse_triple(token):
    if token == "-":
        return None
    parts = token.split(",")
    if len(parts) != 3:
        raise SystemExit("bad triple " + token)
    vals = [float(p) for p in parts]
    if not all(math.isfinite(v) for v in vals):
        raise SystemExit("non-finite triple " + token)
    return tuple(vals)

def _cnt(diag, key):
    # Contract ins_get_diag / diag: the mapping exists on every instance and
    # names these counters. A missing mapping or key prints -1, which the
    # parser records; it must not abort the run.
    try:
        value = diag[key]
    except (KeyError, TypeError, IndexError):
        return -1
    if isinstance(value, bool):
        return -1
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1

def emit(nav, t_us):
    ready = 1 if nav.is_ready() else 0
    ecef = nav.position_ecef()
    ned = nav.position_local()
    vel = nav.velocity_ned()
    rpy = nav.rpy()
    bacc = nav.bias_acc()
    bgyr = nav.bias_gyr()
    diag = nav.diag()
    sd = nav.stddev()
    pos = 1 if ecef is not None else 0
    vel_ok = 1 if vel is not None else 0
    rpy_ok = 1 if rpy is not None else 0
    ned_ok = 1 if ned is not None else 0
    bacc_ok = 1 if bacc is not None else 0
    bgyr_ok = 1 if bgyr is not None else 0
    rpy_std = None
    if sd is not None:
        rpy_std = tuple(sd["rpy"])
    # Attitude published without its 1-sigma (Contract rpy / stddev) is
    # printed as attnostd=1 and recorded by the parser; it must not abort
    # the run.
    attnostd = 1 if (rpy_ok and rpy_std is None) else 0
    def fmt(ok, vec):
        if not ok:
            return "-"
        return "%.17g,%.17g,%.17g" % vec
    n_no = _cnt(diag, "n_gnss_no_anchor")
    n_used = _cnt(diag, "n_gnss_used")
    line = (
        "SNAP t_us=%d ready=%d pos=%d vel=%d rpy=%d ned=%d bacc=%d bgyr=%d"
        % (t_us, ready, pos, vel_ok, rpy_ok, ned_ok, bacc_ok, bgyr_ok)
    )
    line += " attnostd=%d" % attnostd
    line += " ecef=" + (fmt(pos, tuple(ecef)) if pos else "-")
    line += " nedpos=" + (fmt(ned_ok, tuple(ned)) if ned_ok else "-")
    line += " velned=" + (fmt(vel_ok, tuple(vel)) if vel_ok else "-")
    line += " att=" + (fmt(rpy_ok, tuple(rpy)) if rpy_ok else "-")
    line += " attstd=" + (fmt(rpy_std is not None, rpy_std) if rpy_std is not None else "-")
    line += " biasacc=" + (fmt(bacc_ok, tuple(bacc)) if bacc_ok else "-")
    line += " biasgyr=" + (fmt(bgyr_ok, tuple(bgyr)) if bgyr_ok else "-")
    line += " n_no_anchor=%d n_used=%d" % (n_no, n_used)
    print(line)

header1 = sys.stdin.readline()
if not header1:
    raise SystemExit("missing header1")
parts = header1.split()
if len(parts) != 6:
    raise SystemExit("header1 fields")
ox, oy, oz = [float(x) for x in parts[0:3]]
auto_init = int(parts[3])
auto_zupt_disable = int(parts[4])
chi2_disable = int(parts[5])
header2 = sys.stdin.readline()
if not header2:
    raise SystemExit("missing header2")
h2 = header2.split()
if len(h2) != 3:
    raise SystemExit("header2 fields")
lat_deg, lon_deg, h_m = [float(x) for x in h2[0:3]]

cfg_kw = dict(
    auto_init=bool(auto_init),
    lat_rad=math.radians(lat_deg),
    lon_rad=math.radians(lon_deg),
    h_m=h_m,
    auto_zupt_disable=bool(auto_zupt_disable),
    chi2_disable=bool(chi2_disable),
    rpy_init_rad=(0.0, 0.0, 0.0),
    gnss_min_delay_ms=-1,
)
try:
    nav = Ins(Config(**cfg_kw))
except ValueError as exc:
    print("INIT rc=-1")
    print("SNAP t_us=0 ready=0 pos=0 vel=0 rpy=0 ned=0 bacc=0 bgyr=0 "
          "ecef=- nedpos=- velned=- att=- attstd=- biasacc=- biasgyr=- "
          "n_no_anchor=0 n_used=0")
    raise SystemExit(0) from exc

print("INIT rc=0")
_ = (ox, oy, oz)

for raw in sys.stdin:
    if not raw.strip() or raw.startswith("#"):
        continue
    if not raw.startswith("E "):
        raise SystemExit("epoch tag")
    tok = raw.split()
    if len(tok) != 38:
        raise SystemExit("epoch fields %d" % len(tok))
    t_us = int(tok[1])
    dt = float(tok[2])
    acc = (float(tok[3]), float(tok[4]), float(tok[5]))
    gyr = (float(tok[6]), float(tok[7]), float(tok[8]))
    acc_v = int(tok[9])
    gyr_v = int(tok[10])
    gp = int(tok[11])
    ecef = (float(tok[12]), float(tok[13]), float(tok[14]))
    std = (float(tok[15]), float(tok[16]), float(tok[17]))
    gv = int(tok[18])
    vel = (float(tok[19]), float(tok[20]), float(tok[21]))
    vstd = (float(tok[22]), float(tok[23]), float(tok[24]))
    gnss_delay = int(tok[25])
    lp = int(tok[26])
    local = (float(tok[27]), float(tok[28]), float(tok[29]))
    lstd = (float(tok[30]), float(tok[31]), float(tok[32]))
    local_delay = int(tok[33])
    yw = int(tok[34])
    yaw_rad = float(tok[35])
    ystd = float(tok[36])
    yaw_delay = int(tok[37])
    nav.imu(t_us, dt, acc, gyr)
    if gp:
        var = (std[0] * std[0], std[1] * std[1], std[2] * std[2])
        nav.gnss_pos(ecef, var, delay_ms=gnss_delay)
    if gv:
        varv = (vstd[0] * vstd[0], vstd[1] * vstd[1], vstd[2] * vstd[2])
        nav.gnss_vel(vel, varv)
    if lp:
        lvar = (lstd[0] * lstd[0], lstd[1] * lstd[1], lstd[2] * lstd[2])
        nav.local_pos(local, lvar, delay_ms=local_delay)
    if yw:
        nav.yaw(yaw_rad, ystd, delay_ms=yaw_delay)
    nav.update()
    emit(nav, t_us)
"""


@dataclass
class DelayEpoch:
    t_us: int
    dt_sec: float
    acc: tuple[float, float, float]
    gyr: tuple[float, float, float]
    acc_valid: bool = True
    gyr_valid: bool = True
    gnss_ecef: tuple[float, float, float] | None = None
    gnss_std: tuple[float, float, float] | None = None
    gnss_vel: tuple[float, float, float] | None = None
    gnss_vel_std: tuple[float, float, float] | None = None
    gnss_delay_ms: int = 0
    local_ned: tuple[float, float, float] | None = None
    local_std: tuple[float, float, float] | None = None
    local_delay_ms: int = 0
    yaw_rad: float | None = None
    yaw_std: float | None = None
    yaw_delay_ms: int = 0


@dataclass
class DelayScenario:
    origin_ecef: tuple[float, float, float]
    lat_deg: float
    lon_deg: float
    h_m: float
    epochs: list[DelayEpoch] = field(default_factory=list)
    auto_init: bool = True
    auto_zupt_disable: bool = True
    chi2_disable: bool = True
    probe_after_t_us: int = 0


@dataclass
class DelaySnapshot:
    t_us: int
    ready: bool
    pos_ok: bool
    vel_ok: bool
    rpy_ok: bool
    ned_ok: bool
    bias_acc_ok: bool
    bias_gyr_ok: bool
    ecef: tuple[float, float, float] | None
    ned: tuple[float, float, float] | None
    vel_ned: tuple[float, float, float] | None
    rpy: tuple[float, float, float] | None
    rpy_std: tuple[float, float, float] | None
    bias_acc: tuple[float, float, float] | None
    bias_gyr: tuple[float, float, float] | None
    n_no_anchor: int
    n_gnss_used: int


@dataclass
class DelayRun:
    init_ok: bool
    snaps: list[DelaySnapshot]

    def last(self) -> DelaySnapshot:
        if not self.snaps:
            raise HarnessError("run produced no snapshots")
        return self.snaps[-1]

    def at_or_after(self, t_us: int) -> DelaySnapshot:
        for snap in self.snaps:
            if snap.t_us >= t_us and snap.pos_ok:
                return snap
        raise HarnessError(f"no initialized snapshot at or after t={t_us}")

    def last_before(self, t_us: int) -> DelaySnapshot:
        found = None
        for snap in self.snaps:
            if snap.t_us < t_us and snap.pos_ok:
                found = snap
        if found is None:
            raise HarnessError(f"no initialized snapshot before t={t_us}")
        return found


def _delay_epoch(
    t_us: int,
    *,
    dt_sec: float = DT_SEC,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    **kwargs,
) -> DelayEpoch:
    return DelayEpoch(
        t_us=t_us,
        dt_sec=dt_sec,
        acc=(float(acc[0]), float(acc[1]), float(acc[2])),
        gyr=(float(gyr[0]), float(gyr[1]), float(gyr[2])),
        **kwargs,
    )


def delay_site(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    epochs: list[DelayEpoch],
    **kwargs,
) -> DelayScenario:
    origin = kwargs.pop("origin_ecef", None)
    if origin is None:
        origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    return DelayScenario(
        origin_ecef=origin,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        h_m=h_m,
        epochs=epochs,
        **kwargs,
    )


def moving_north_truth(
    origin: Sequence[float], north_m: float
) -> tuple[float, float, float]:
    """Independent geometry: origin plus a north displacement. Raises if not finite."""
    if not math.isfinite(north_m):
        raise HarnessError(f"north displacement is not finite: {north_m}")
    return ecef_plus_ned(origin, north_m, 0.0, 0.0)


def accel_then_cruise_ned(t_motion: float, v_north: float, accel_s: float = ACCEL_S) -> tuple[float, float]:
    """North position and speed after *t_motion* seconds of constant-accel then cruise."""
    if not all(math.isfinite(v) for v in (t_motion, v_north, accel_s)):
        raise HarnessError("accel/cruise inputs are not finite")
    if accel_s <= 0.0:
        raise HarnessError("accel duration must be positive")
    if t_motion <= 0.0:
        return 0.0, 0.0
    if t_motion < accel_s:
        a = v_north / accel_s
        return 0.5 * a * t_motion * t_motion, a * t_motion
    return 0.5 * v_north * accel_s + v_north * (t_motion - accel_s), v_north


def along_track_error_m(
    published_ecef: Sequence[float],
    truth_ecef: Sequence[float],
    origin: Sequence[float],
    track_ned: Sequence[float] = (1.0, 0.0, 0.0),
) -> float:
    """Signed along-track component of published-minus-truth. Raises on non-finite input."""
    if len(published_ecef) != 3 or len(truth_ecef) != 3 or len(origin) != 3:
        raise HarnessError("ECEF vectors must have 3 components")
    if not all(math.isfinite(v) for v in (*published_ecef, *truth_ecef, *origin, *track_ned)):
        raise HarnessError("along-track inputs are not finite")
    pub = ned_offset_from_two_ecef(origin, published_ecef)
    tru = ned_offset_from_two_ecef(origin, truth_ecef)
    err = (pub[0] - tru[0], pub[1] - tru[1], pub[2] - tru[2])
    tn = math.sqrt(sum(float(c) * float(c) for c in track_ned))
    if tn <= 0.0 or not math.isfinite(tn):
        raise HarnessError("track direction has no length")
    along = (err[0] * float(track_ned[0]) + err[1] * float(track_ned[1]) + err[2] * float(track_ned[2])) / tn
    if not math.isfinite(along):
        raise HarnessError("along-track error is not finite")
    return along


def runtime_north_speed() -> float:
    """Cruise speed whose v×delay is far above GNSS 1-sigma. Not the F02 ~0.2 m/s sample."""
    u = runtime_uuid_int()
    vn = 12.0 + (u % 90) / 10.0
    print(f"runtime north speed {vn}", flush=True)
    return vn


def runtime_in_window_delay_ms() -> int:
    """In-window delay that is not the named 200 ms sample, still covered by history."""
    u = runtime_uuid_int()
    delay = 110 + (u % 17) * 10
    if delay == NAMED_DELAY_200_MS:
        delay = 160
    print(f"runtime in-window delay_ms={delay}", flush=True)
    return delay


def runtime_offset_north_m() -> float:
    """Pad offset of several metres, larger than a sub-metre lock."""
    u = runtime_uuid_int()
    north = 4.2 + (u % 40) / 10.0
    print(f"runtime offset north={north}", flush=True)
    return north


def runtime_tracker_b() -> tuple[float, float, float]:
    """A second indoor tracker, not the named (1.5, 0, 0) lock."""
    u = runtime_uuid_int()
    n = 3.4 + (u % 20) / 10.0
    e = 1.1 + ((u // 20) % 15) / 10.0
    print(f"runtime tracker B n={n} e={e}", flush=True)
    return (n, e, 0.0)


def runtime_yaw_rad() -> float:
    u = runtime_uuid_int()
    yaw = 0.25 + (u % 40) / 100.0
    print(f"runtime yaw rad={yaw}", flush=True)
    return yaw


def runtime_yaw_rate() -> float:
    u = runtime_uuid_int()
    rate = 0.45 + (u % 20) / 100.0
    print(f"runtime yaw rate {rate} rad/s", flush=True)
    return rate


def runtime_unexplained_yaw_rad() -> float:
    """Heading offset the gyro cannot explain. Skip stays on integrated yaw."""
    u = runtime_uuid_int()
    yaw = 0.35 + (u % 20) / 100.0
    print(f"runtime unexplained yaw offset {yaw} rad", flush=True)
    return yaw


def encode_delay(scen: DelayScenario) -> str:
    ox, oy, oz = scen.origin_ecef
    lines = [
        f"{ox:.17g} {oy:.17g} {oz:.17g} {int(scen.auto_init)} "
        f"{int(scen.auto_zupt_disable)} {int(scen.chi2_disable)}",
        f"{scen.lat_deg:.17g} {scen.lon_deg:.17g} {scen.h_m:.17g}",
    ]
    for e in scen.epochs:
        gp = 1 if e.gnss_ecef is not None else 0
        ecef = e.gnss_ecef if e.gnss_ecef is not None else (0.0, 0.0, 0.0)
        std = e.gnss_std if e.gnss_std is not None else (0.0, 0.0, 0.0)
        gv = 1 if e.gnss_vel is not None else 0
        vel = e.gnss_vel if e.gnss_vel is not None else (0.0, 0.0, 0.0)
        vstd = e.gnss_vel_std if e.gnss_vel_std is not None else (0.1, 0.1, 0.1)
        lp = 1 if e.local_ned is not None else 0
        local = e.local_ned if e.local_ned is not None else (0.0, 0.0, 0.0)
        lstd = e.local_std if e.local_std is not None else (0.0, 0.0, 0.0)
        yw = 1 if e.yaw_rad is not None else 0
        yaw = e.yaw_rad if e.yaw_rad is not None else 0.0
        ystd = e.yaw_std if e.yaw_std is not None else 0.0
        lines.append(
            "E %d %.17g %.17g %.17g %.17g %.17g %.17g %.17g %d %d %d "
            "%.17g %.17g %.17g %.17g %.17g %.17g %d %.17g %.17g %.17g "
            "%.17g %.17g %.17g %d %d %.17g %.17g %.17g %.17g %.17g %.17g "
            "%d %d %.17g %.17g %d"
            % (
                e.t_us,
                e.dt_sec,
                e.acc[0],
                e.acc[1],
                e.acc[2],
                e.gyr[0],
                e.gyr[1],
                e.gyr[2],
                int(e.acc_valid),
                int(e.gyr_valid),
                gp,
                ecef[0],
                ecef[1],
                ecef[2],
                std[0],
                std[1],
                std[2],
                gv,
                vel[0],
                vel[1],
                vel[2],
                vstd[0],
                vstd[1],
                vstd[2],
                int(e.gnss_delay_ms),
                lp,
                local[0],
                local[1],
                local[2],
                lstd[0],
                lstd[1],
                lstd[2],
                int(e.local_delay_ms),
                yw,
                yaw,
                ystd,
                int(e.yaw_delay_ms),
            )
        )
    return "\n".join(lines) + "\n"


def parse_delay_snapshot(line: str) -> DelaySnapshot:
    if not line.startswith("SNAP "):
        raise HarnessError(f"not a SNAP line: {line!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad SNAP token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    t_us = _parse_int(fields, "t_us")
    ready = _parse_flag(fields, "ready")
    pos_ok = _parse_flag(fields, "pos")
    vel_ok = _parse_flag(fields, "vel")
    rpy_ok = _parse_flag(fields, "rpy")
    ned_ok = _parse_flag(fields, "ned")
    bacc_ok = _parse_flag(fields, "bacc")
    bgyr_ok = _parse_flag(fields, "bgyr")
    ecef = _parse_vec(fields, "ecef", pos_ok)
    ned = _parse_vec(fields, "nedpos", ned_ok)
    vel = _parse_vec(fields, "velned", vel_ok)
    rpy = _parse_vec(fields, "att", rpy_ok)
    if "attstd" not in fields:
        raise HarnessError("snapshot missing attstd")
    rpy_std_ok = fields["attstd"] != "-"
    rpy_std = _parse_vec(fields, "attstd", rpy_std_ok)
    bacc = _parse_vec(fields, "biasacc", bacc_ok)
    bgyr = _parse_vec(fields, "biasgyr", bgyr_ok)
    n_no = _parse_int(fields, "n_no_anchor")
    n_used = _parse_int(fields, "n_used")
    if n_no < 0:
        note_product_issue("F04", f"n_no_anchor missing or negative: {line}")
    if n_used < 0:
        note_product_issue("F04", f"n_used missing or negative: {line}")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F04', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F04', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F04', f"ins_get_diag returned NULL for a live instance: {line}")
    return DelaySnapshot(
        t_us=t_us,
        ready=ready,
        pos_ok=pos_ok,
        vel_ok=vel_ok,
        rpy_ok=rpy_ok,
        ned_ok=ned_ok,
        bias_acc_ok=bacc_ok,
        bias_gyr_ok=bgyr_ok,
        ecef=ecef,
        ned=ned,
        vel_ned=vel,
        rpy=rpy,
        rpy_std=rpy_std,
        bias_acc=bacc,
        bias_gyr=bgyr,
        n_no_anchor=n_no,
        n_gnss_used=n_used,
    )


def parse_delay_run(text: str) -> DelayRun:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    init_lines = [ln for ln in lines if ln.startswith("INIT ")]
    if not init_lines:
        raise HarnessError(f"probe stdout missing INIT: {text[:200]!r}")
    if len(init_lines) != 1:
        raise HarnessError(f"probe stdout has {len(init_lines)} INIT lines")
    init_line = init_lines[0]
    init_fields = dict(
        token.split("=", 1) for token in init_line[5:].split() if "=" in token
    )
    if "rc" not in init_fields:
        raise HarnessError(f"INIT missing rc: {init_line!r}")
    try:
        rc = int(init_fields["rc"])
    except ValueError as exc:
        raise HarnessError(f"INIT rc not an int: {init_line!r}") from exc
    snaps = [parse_delay_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    return DelayRun(init_ok=(rc == 0), snaps=snaps)


_COMPILE_DONE = False
_COMPILE_RESULT: RunResult | None = None
_COMPILE_ERROR: BaseException | None = None


def _compile_detail(result: RunResult | None) -> str:
    """Text of the session ``make pylib replay`` attached to a failed observation."""
    if result is None:
        return (
            "make pylib replay produced no result "
            "(no Makefile in the product root)"
        )

    def _dec(blob: bytes) -> str:
        try:
            return blob.decode("utf-8")
        except UnicodeDecodeError:
            return blob.decode("utf-8", errors="replace")

    return (
        f"make pylib replay exit={result.returncode}\n"
        f"--- stdout ---\n{_dec(result.stdout)[-4000:]}\n"
        f"--- stderr ---\n{_dec(result.stderr)[-4000:]}"
    )


def _compile_product_once() -> RunResult | None:
    """Run ``make pylib replay`` once per process, before any library load.

    Does not run at import. A missing Makefile or a non-zero make status
    is stored and asserted by the test that needs the library; neither
    skips the test nor aborts collection.
    """
    global _COMPILE_DONE, _COMPILE_RESULT, _COMPILE_ERROR
    if not _COMPILE_DONE:
        try:
            _COMPILE_RESULT = compile_repository()
        except BaseException as exc:
            _COMPILE_ERROR = exc
            raise
        finally:
            _COMPILE_DONE = True
    if _COMPILE_ERROR is not None:
        raise _COMPILE_ERROR
    return _COMPILE_RESULT


def _require_compiled_product():
    """Resolve the package and shared object ``make pylib`` wrote.

    The package name is whatever directory the compile created. Callers
    import that name and link the shared object whose stem equals it.
    A failed compile, or a missing package or shared object afterwards,
    is an assertion failure carrying the make output.
    """
    result = _compile_product_once()
    detail = _compile_detail(result)
    assert result is not None, (
        "make pylib replay did not run\n" + detail
    )
    assert result.returncode == 0, (
        "make pylib replay failed\n" + detail
    )
    ident = product_identity()
    assert ident is not None, (
        "python package directory was not found after make pylib replay\n" + detail
    )
    assert ident.library is not None and ident.library.is_file(), (
        "shared library is missing after make pylib replay\n" + detail
    )
    assert ident.library_stem == ident.package_name, (
        f"shared-object stem {ident.library_stem!r} does not equal the "
        f"compiled package {ident.package_name!r}\n" + detail
    )
    assert ident.package_name.isidentifier(), (
        f"discovered package name is not importable: {ident.package_name!r}\n"
        + detail
    )
    return ident


def _run_delay(kind: str, scen: DelayScenario) -> DelayRun:
    payload = encode_delay(scen)
    ident = _require_compiled_product()
    if kind == "c":
        result = invoke(_C_PROBE, stdin=payload, timeout=LONG_TIMEOUT, root=repo_root())
    elif kind == "py":
        result = run_python(
            _PY_PROBE.replace("__PKG__", ident.package_name),
            stdin=payload,
            timeout=LONG_TIMEOUT,
            root=repo_root(),
        )
    else:
        raise HarnessError(f"unknown probe kind {kind!r}")
    text = require_probe_success(result)
    run = parse_delay_run(text)
    last = run.last() if run.snaps else None
    print(
        f"{kind} init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_ready={last.ready if last else None} "
        f"n_no_anchor={last.n_no_anchor if last else None}",
        flush=True,
    )
    return run


def c_delay_run(scen: DelayScenario) -> DelayRun:
    return _run_delay("c", scen)


def py_delay_run(scen: DelayScenario) -> DelayRun:
    return _run_delay("py", scen)


def require_initialized_solution(snap: DelaySnapshot, what: str) -> None:
    if not (snap.pos_ok and snap.ned_ok and snap.rpy_ok):
        raise AssertionError(
            f"{what}: accessors not successful pos={snap.pos_ok} "
            f"ned={snap.ned_ok} rpy={snap.rpy_ok} at t={snap.t_us}"
        )
    if snap.ecef is None or snap.ned is None or snap.rpy is None:
        raise AssertionError(f"{what}: successful accessors returned no vectors")


def require_ready_delay(snap: DelaySnapshot, what: str) -> None:
    if not snap.ready:
        raise AssertionError(f"{what}: expected ready at t={snap.t_us}")
    require_initialized_solution(snap, what)
    if not snap.vel_ok or snap.vel_ned is None:
        raise AssertionError(f"{what}: velocity not published at t={snap.t_us}")


def apply_delay_after(
    scen: DelayScenario,
    t_us: int,
    *,
    gnss_ms: int | None = None,
    local_ms: int | None = None,
    yaw_ms: int | None = None,
) -> DelayScenario:
    """Set delay fields on samples at or after *t_us*. Earlier epochs keep theirs."""
    out: list[DelayEpoch] = []
    for e in scen.epochs:
        if e.t_us < t_us:
            out.append(e)
            continue
        gnss_delay = e.gnss_delay_ms
        local_delay = e.local_delay_ms
        yaw_delay = e.yaw_delay_ms
        if gnss_ms is not None and e.gnss_ecef is not None:
            gnss_delay = gnss_ms
        if local_ms is not None and e.local_ned is not None:
            local_delay = local_ms
        if yaw_ms is not None and e.yaw_rad is not None:
            yaw_delay = yaw_ms
        out.append(
            replace(
                e,
                gnss_delay_ms=gnss_delay,
                local_delay_ms=local_delay,
                yaw_delay_ms=yaw_delay,
            )
        )
    return replace(scen, epochs=out)


def _imu_pad(
    origin: Sequence[float],
    *,
    duration_s: float,
    imu_hz: int,
    gnss_hz: int,
    gnss_std: Sequence[float],
    gnss_vel: Sequence[float] | None,
    gnss_vel_std: Sequence[float] | None,
    local_ned: Sequence[float] | None = None,
    local_std: Sequence[float] | None = None,
    local_hz: int = LOCAL_HZ,
    yaw_rad: float | None = None,
    yaw_std: float | None = None,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
) -> list[DelayEpoch]:
    if imu_hz <= 0:
        raise HarnessError("IMU rate must be positive")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    gnss_every = imu_hz // gnss_hz if gnss_hz > 0 else n + 1
    local_every = imu_hz // local_hz if local_hz > 0 else n + 1
    epochs: list[DelayEpoch] = []
    for k in range(1, n + 1):
        t_us = int(round(k * dt * 1e6))
        has_gnss = gnss_hz > 0 and k % gnss_every == 0
        has_local = local_ned is not None and k % local_every == 0
        has_yaw = yaw_rad is not None and k % local_every == 0
        epochs.append(
            _delay_epoch(
                t_us,
                dt_sec=dt,
                acc=acc,
                gyr=gyr,
                gnss_ecef=tuple(origin) if has_gnss else None,
                gnss_std=tuple(gnss_std) if has_gnss else None,
                gnss_vel=tuple(gnss_vel) if (has_gnss and gnss_vel is not None) else None,
                gnss_vel_std=tuple(gnss_vel_std)
                if (has_gnss and gnss_vel is not None)
                else None,
                local_ned=tuple(local_ned) if has_local else None,
                local_std=tuple(local_std) if has_local else None,
                yaw_rad=float(yaw_rad) if has_yaw else None,
                yaw_std=float(yaw_std) if has_yaw else None,
            )
        )
    return epochs


def pad_then_moving_gnss(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    delay_ms: int,
    v_north: float,
    with_gnss_vel: bool = True,
    motion_s: float = MOTION_S,
    gnss_std: Sequence[float] = DELAY_TIGHT_STD_M,
    north_offset_m: float = 0.0,
) -> DelayScenario:
    """Stationary auto-init pad, then constant-north cruise.

    GNSS bytes are validity-time IMU geometry plus *north_offset_m*, an
    along-track offset strapdown cannot explain. Skip of the delayed sample
    stays on the IMU path; fusion at time of validity pulls toward the offset.
    """
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    imu_hz = IMU_HZ
    dt = 1.0 / imu_hz
    pad = _imu_pad(
        origin,
        duration_s=PROBE_AFTER_PAD_S,
        imu_hz=imu_hz,
        gnss_hz=GNSS_HZ,
        gnss_std=gnss_std,
        gnss_vel=(0.0, 0.0, 0.0),
        gnss_vel_std=DELAY_VEL_STD,
    )
    t0 = pad[-1].t_us
    probe_after = t0
    accel_s = ACCEL_S
    a_n = v_north / accel_s
    n_accel = int(round(accel_s * imu_hz))
    for i in range(1, n_accel + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        pad.append(_delay_epoch(t_us, dt_sec=dt, acc=(a_n, 0.0, -G_MPS2)))
    t1 = pad[-1].t_us
    n = int(round(motion_s * imu_hz))
    gnss_every = imu_hz // GNSS_HZ
    delay_s = delay_ms * 1.0e-3
    for i in range(1, n + 1):
        t_us = t1 + int(round(i * dt * 1e6))
        t_motion = accel_s + i * dt
        t_valid = t_motion - delay_s
        if t_valid < 0.0:
            t_valid = 0.0
        north, vn = accel_then_cruise_ned(t_valid, v_north, accel_s)
        ecef = moving_north_truth(origin, north + north_offset_m)
        has_gnss = i % gnss_every == 0
        # Do not put a delayed sample on the first IMU of the cruise.
        if i == 1:
            has_gnss = False
        vel = (vn, 0.0, 0.0) if with_gnss_vel else None
        pad.append(
            _delay_epoch(
                t_us,
                dt_sec=dt,
                acc=(0.0, 0.0, -G_MPS2),
                gnss_ecef=ecef if has_gnss else None,
                gnss_std=tuple(gnss_std) if has_gnss else None,
                gnss_vel=vel if has_gnss else None,
                gnss_vel_std=tuple(DELAY_VEL_STD) if (has_gnss and vel is not None) else None,
                gnss_delay_ms=delay_ms if has_gnss else 0,
            )
        )
    return delay_site(
        lat_deg,
        lon_deg,
        h_m,
        pad,
        origin_ecef=origin,
        probe_after_t_us=probe_after,
    )


def pad_then_stop_expired_gnss(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    delay_ms: int,
    v_north: float,
    gnss_std: Sequence[float] = DELAY_TIGHT_STD_M,
    north_offset_m: float = 0.0,
) -> DelayScenario:
    """Cruise, IMU-only brake to rest, then one expired position (no velocity).

    The expired GNSS bytes are validity-time IMU geometry plus *north_offset_m*,
    an along-track offset strapdown cannot explain. Skip of that delayed sample
    stays at the IMU stop; fusion at time of validity pulls toward the offset.
    The brake is IMU-only so the delayed sample is not dropped by the default
    GNSS fusion interval.
    """
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    imu_hz = IMU_HZ
    dt = 1.0 / imu_hz
    pad = _imu_pad(
        origin,
        duration_s=PROBE_AFTER_PAD_S,
        imu_hz=imu_hz,
        gnss_hz=GNSS_HZ,
        gnss_std=gnss_std,
        gnss_vel=(0.0, 0.0, 0.0),
        gnss_vel_std=DELAY_VEL_STD,
    )
    t0 = pad[-1].t_us
    motion_s = STOP_CRUISE_S
    accel_s = ACCEL_S
    a_n = v_north / accel_s
    n_accel = int(round(accel_s * imu_hz))
    for i in range(1, n_accel + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        pad.append(_delay_epoch(t_us, dt_sec=dt, acc=(a_n, 0.0, -G_MPS2)))
    t1 = pad[-1].t_us
    n_move = int(round(motion_s * imu_hz))
    gnss_every = imu_hz // GNSS_HZ
    delay_s = delay_ms * 1.0e-3
    for i in range(1, n_move + 1):
        t_us = t1 + int(round(i * dt * 1e6))
        t_motion = accel_s + i * dt
        north, vn = accel_then_cruise_ned(t_motion, v_north, accel_s)
        ecef = moving_north_truth(origin, north)
        has_gnss = i % gnss_every == 0 and i > 1
        pad.append(
            _delay_epoch(
                t_us,
                dt_sec=dt,
                acc=(0.0, 0.0, -G_MPS2),
                gnss_ecef=ecef if has_gnss else None,
                gnss_std=tuple(gnss_std) if has_gnss else None,
                gnss_vel=(vn, 0.0, 0.0) if has_gnss else None,
                gnss_vel_std=tuple(DELAY_VEL_STD) if has_gnss else None,
                gnss_delay_ms=0,
            )
        )
    # IMU-only brake: last cruise GNSS is then older than the default
    # fusion interval, so the delayed sample is not rate-limited away.
    brake_s = STOP_BRAKE_S
    a_brake = -v_north / brake_s
    n_brake = int(round(brake_s * imu_hz))
    t_br0 = pad[-1].t_us
    for i in range(1, n_brake + 1):
        t_us = t_br0 + int(round(i * dt * 1e6))
        pad.append(_delay_epoch(t_us, dt_sec=dt, acc=(a_brake, 0.0, -G_MPS2)))
    t_probe = pad[-1].t_us + int(round(dt * 1e6))
    t_valid_s = (t_probe - t0) * 1.0e-6 - delay_s
    north_valid, _ = accel_then_cruise_ned(min(t_valid_s, accel_s + motion_s), v_north, accel_s)
    expired = moving_north_truth(origin, north_valid + north_offset_m)
    pad.append(
        _delay_epoch(
            t_probe,
            dt_sec=dt,
            acc=(0.0, 0.0, -G_MPS2),
            gnss_ecef=expired,
            gnss_std=tuple(gnss_std),
            gnss_delay_ms=delay_ms,
        )
    )
    return delay_site(
        lat_deg,
        lon_deg,
        h_m,
        pad,
        origin_ecef=origin,
        probe_after_t_us=t_probe,
    )


def pad_then_offset_gnss(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    delay_ms: int,
    north_m: float,
    extra_s: float = 2.0,
    then_delay_ms: int | None = None,
    then_north_m: float | None = None,
    then_s: float = 2.0,
    gnss_std: Sequence[float] = DELAY_TIGHT_STD_M,
) -> DelayScenario:
    """Ready pad, then GNSS at a north offset with *delay_ms*. Optional second delay/offset."""
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    imu_hz = IMU_HZ
    dt = 1.0 / imu_hz
    pad = _imu_pad(
        origin,
        duration_s=PROBE_AFTER_PAD_S,
        imu_hz=imu_hz,
        gnss_hz=GNSS_HZ,
        gnss_std=gnss_std,
        gnss_vel=(0.0, 0.0, 0.0),
        gnss_vel_std=DELAY_VEL_STD,
    )
    t0 = pad[-1].t_us
    offset = moving_north_truth(origin, north_m)
    gnss_every = imu_hz // GNSS_HZ
    n = int(round(extra_s * imu_hz))
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        has_gnss = i % gnss_every == 0
        pad.append(
            _delay_epoch(
                t_us,
                dt_sec=dt,
                gnss_ecef=offset if has_gnss else None,
                gnss_std=tuple(gnss_std) if has_gnss else None,
                gnss_vel=(0.0, 0.0, 0.0) if has_gnss else None,
                gnss_vel_std=tuple(DELAY_VEL_STD) if has_gnss else None,
                gnss_delay_ms=delay_ms if has_gnss else 0,
            )
        )
    if then_delay_ms is not None:
        t1 = pad[-1].t_us
        north2 = then_north_m if then_north_m is not None else north_m
        second = moving_north_truth(origin, north2)
        n2 = int(round(then_s * imu_hz))
        for i in range(1, n2 + 1):
            t_us = t1 + int(round(i * dt * 1e6))
            has_gnss = i % gnss_every == 0
            pad.append(
                _delay_epoch(
                    t_us,
                    dt_sec=dt,
                    gnss_ecef=second if has_gnss else None,
                    gnss_std=tuple(gnss_std) if has_gnss else None,
                    gnss_vel=(0.0, 0.0, 0.0) if has_gnss else None,
                    gnss_vel_std=tuple(DELAY_VEL_STD) if has_gnss else None,
                    gnss_delay_ms=then_delay_ms if has_gnss else 0,
                )
            )
    return delay_site(
        lat_deg,
        lon_deg,
        h_m,
        pad,
        origin_ecef=origin,
        probe_after_t_us=t0,
    )


def shallow_prescribed_gnss(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    delay_ms: int,
    north_m: float,
    imu_count: int = SHALLOW_IMU,
    then_fill_s: float = 0.0,
    then_same_delay: bool = False,
    gnss_std: Sequence[float] = DELAY_TIGHT_STD_M,
) -> DelayScenario:
    """Prescribed init, a few IMU samples, then an in-window delayed offset GNSS."""
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    dt = DT_SEC
    offset = moving_north_truth(origin, north_m)
    epochs: list[DelayEpoch] = [
        _delay_epoch(
            int(round(dt * 1e6)),
            dt_sec=dt,
            gnss_ecef=tuple(origin),
            gnss_std=tuple(gnss_std),
            gnss_vel=(0.0, 0.0, 0.0),
            gnss_vel_std=DELAY_VEL_STD,
            gnss_delay_ms=0,
        )
    ]
    for i in range(2, imu_count + 1):
        epochs.append(_delay_epoch(int(round(i * dt * 1e6)), dt_sec=dt))
    t_probe = int(round((imu_count + 1) * dt * 1e6))
    epochs.append(
        _delay_epoch(
            t_probe,
            dt_sec=dt,
            gnss_ecef=offset,
            gnss_std=tuple(gnss_std),
            gnss_delay_ms=delay_ms,
        )
    )
    if then_fill_s > 0.0:
        n_fill = int(round(then_fill_s * IMU_HZ))
        t1 = epochs[-1].t_us
        for i in range(1, n_fill + 1):
            epochs.append(_delay_epoch(t1 + int(round(i * dt * 1e6)), dt_sec=dt))
        if then_same_delay:
            t2 = epochs[-1].t_us + int(round(dt * 1e6))
            epochs.append(
                _delay_epoch(
                    t2,
                    dt_sec=dt,
                    gnss_ecef=offset,
                    gnss_std=tuple(gnss_std),
                    gnss_delay_ms=delay_ms,
                )
            )
    return delay_site(
        lat_deg,
        lon_deg,
        h_m,
        epochs,
        origin_ecef=origin,
        auto_init=False,
        probe_after_t_us=t_probe,
    )


def pad_local(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    tracker: Sequence[float],
    *,
    duration_s: float = HAPPY_DURATION_S,
    yaw_rad: float | None = None,
    yaw_std: float | None = None,
) -> list[DelayEpoch]:
    return _imu_pad(
        ecef_from_llh_deg(lat_deg, lon_deg, h_m),
        duration_s=duration_s,
        imu_hz=IMU_HZ,
        gnss_hz=0,
        gnss_std=GNSS_STD_M,
        gnss_vel=None,
        gnss_vel_std=None,
        local_ned=tracker,
        local_std=LOCAL_MOVE_STD,
        yaw_rad=yaw_rad,
        yaw_std=yaw_std if yaw_rad is not None else None,
    )


def _append_hold(
    epochs: list[DelayEpoch],
    t0_us: int,
    dt: float,
    n: int,
    **kwargs,
) -> None:
    for i in range(1, n + 1):
        epochs.append(_delay_epoch(t0_us + int(round(i * dt * 1e6)), dt_sec=dt, **kwargs))


def local_skip_scenario(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    tracker_a: Sequence[float],
    tracker_b: Sequence[float],
    *,
    delay_ms: int,
    shallow: bool,
) -> DelayScenario:
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    dt = DT_SEC
    if shallow:
        epochs = [
            _delay_epoch(
                int(round(dt * 1e6)),
                dt_sec=dt,
                local_ned=tuple(tracker_a),
                local_std=LOCAL_MOVE_STD,
                local_delay_ms=0,
            )
        ]
        for i in range(2, SHALLOW_IMU + 1):
            epochs.append(
                _delay_epoch(
                    int(round(i * dt * 1e6)),
                    dt_sec=dt,
                    local_ned=tuple(tracker_a),
                    local_std=LOCAL_MOVE_STD,
                    local_delay_ms=0,
                )
            )
        t_probe = int(round((SHALLOW_IMU + 1) * dt * 1e6))
        epochs.append(
            _delay_epoch(
                t_probe,
                dt_sec=dt,
                local_ned=tuple(tracker_b),
                local_std=LOCAL_MOVE_STD,
                local_delay_ms=delay_ms,
            )
        )
        _append_hold(
            epochs,
            t_probe,
            dt,
            SKIP_HOLD_IMU,
            local_ned=tuple(tracker_b),
            local_std=LOCAL_MOVE_STD,
            local_delay_ms=delay_ms,
        )
        return delay_site(
            lat_deg,
            lon_deg,
            h_m,
            epochs,
            origin_ecef=origin,
            auto_init=False,
            probe_after_t_us=t_probe,
        )
    epochs = pad_local(lat_deg, lon_deg, h_m, tracker_a)
    t0 = epochs[-1].t_us
    t_probe = t0 + int(round(dt * 1e6))
    epochs.append(
        _delay_epoch(
            t_probe,
            dt_sec=dt,
            local_ned=tuple(tracker_b),
            local_std=LOCAL_MOVE_STD,
            local_delay_ms=delay_ms,
        )
    )
    _append_hold(
        epochs,
        t_probe,
        dt,
        SKIP_HOLD_IMU,
        local_ned=tuple(tracker_b),
        local_std=LOCAL_MOVE_STD,
        local_delay_ms=delay_ms,
    )
    return delay_site(
        lat_deg,
        lon_deg,
        h_m,
        epochs,
        origin_ecef=origin,
        probe_after_t_us=t_probe,
    )


def yaw_skip_scenario(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    yaw_lock: float,
    yaw_new: float,
    *,
    delay_ms: int,
    shallow: bool,
) -> DelayScenario:
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    dt = DT_SEC
    if shallow:
        epochs = [
            _delay_epoch(
                int(round(dt * 1e6)),
                dt_sec=dt,
                gnss_ecef=tuple(origin),
                gnss_std=tuple(GNSS_STD_M),
                gnss_vel=(0.0, 0.0, 0.0),
                gnss_vel_std=DELAY_VEL_STD,
                yaw_rad=yaw_lock,
                yaw_std=YAW_TIGHT_STD_RAD,
            )
        ]
        for i in range(2, SHALLOW_IMU + 1):
            epochs.append(
                _delay_epoch(
                    int(round(i * dt * 1e6)),
                    dt_sec=dt,
                    gnss_ecef=tuple(origin),
                    gnss_std=tuple(GNSS_STD_M),
                    gnss_vel=(0.0, 0.0, 0.0),
                    gnss_vel_std=DELAY_VEL_STD,
                    yaw_rad=yaw_lock,
                    yaw_std=YAW_TIGHT_STD_RAD,
                )
            )
        t_probe = int(round((SHALLOW_IMU + 1) * dt * 1e6))
        epochs.append(
            _delay_epoch(
                t_probe,
                dt_sec=dt,
                yaw_rad=yaw_new,
                yaw_std=YAW_TIGHT_STD_RAD,
                yaw_delay_ms=delay_ms,
            )
        )
        _append_hold(
            epochs,
            t_probe,
            dt,
            SKIP_HOLD_IMU,
            gnss_ecef=tuple(origin),
            gnss_std=tuple(GNSS_STD_M),
            gnss_vel=(0.0, 0.0, 0.0),
            gnss_vel_std=DELAY_VEL_STD,
            yaw_rad=yaw_new,
            yaw_std=YAW_TIGHT_STD_RAD,
            yaw_delay_ms=delay_ms,
        )
        return delay_site(
            lat_deg,
            lon_deg,
            h_m,
            epochs,
            origin_ecef=origin,
            auto_init=False,
            probe_after_t_us=t_probe,
        )
    epochs = _imu_pad(
        origin,
        duration_s=HAPPY_DURATION_S,
        imu_hz=IMU_HZ,
        gnss_hz=GNSS_HZ,
        gnss_std=GNSS_STD_M,
        gnss_vel=(0.0, 0.0, 0.0),
        gnss_vel_std=DELAY_VEL_STD,
        yaw_rad=yaw_lock,
        yaw_std=YAW_TIGHT_STD_RAD,
    )
    t0 = epochs[-1].t_us
    t_probe = t0 + int(round(dt * 1e6))
    epochs.append(
        _delay_epoch(
            t_probe,
            dt_sec=dt,
            yaw_rad=yaw_new,
            yaw_std=YAW_TIGHT_STD_RAD,
            yaw_delay_ms=delay_ms,
        )
    )
    _append_hold(
        epochs,
        t_probe,
        dt,
        SKIP_HOLD_IMU,
        gnss_ecef=tuple(origin),
        gnss_std=tuple(GNSS_STD_M),
        gnss_vel=(0.0, 0.0, 0.0),
        gnss_vel_std=DELAY_VEL_STD,
        yaw_rad=yaw_new,
        yaw_std=YAW_TIGHT_STD_RAD,
        yaw_delay_ms=delay_ms,
    )
    return delay_site(
        lat_deg,
        lon_deg,
        h_m,
        epochs,
        origin_ecef=origin,
        probe_after_t_us=t_probe,
    )


def moving_local_scenario(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    delay_ms: int,
    v_north: float,
    motion_s: float = 3.0,
    north_offset_m: float = 0.0,
    local_std: Sequence[float] = LOCAL_MOVE_STD,
) -> DelayScenario:
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    start = TRACKER_NAMED_NED
    epochs = pad_local(lat_deg, lon_deg, h_m, start)
    t0 = epochs[-1].t_us
    imu_hz = IMU_HZ
    dt = 1.0 / imu_hz
    every = imu_hz // LOCAL_HZ
    delay_s = delay_ms * 1.0e-3
    accel_s = ACCEL_S
    a_n = v_north / accel_s
    n_accel = int(round(accel_s * imu_hz))
    for i in range(1, n_accel + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        epochs.append(_delay_epoch(t_us, dt_sec=dt, acc=(a_n, 0.0, -G_MPS2)))
    t1 = epochs[-1].t_us
    n = int(round(motion_s * imu_hz))
    for i in range(1, n + 1):
        t_us = t1 + int(round(i * dt * 1e6))
        t_motion = accel_s + i * dt
        t_valid = max(t_motion - delay_s, 0.0)
        north, _ = accel_then_cruise_ned(t_valid, v_north, accel_s)
        pos = (start[0] + north + north_offset_m, start[1], start[2])
        has_local = i % every == 0 and i > 1
        epochs.append(
            _delay_epoch(
                t_us,
                dt_sec=dt,
                acc=(0.0, 0.0, -G_MPS2),
                local_ned=pos if has_local else None,
                local_std=tuple(local_std) if has_local else None,
                local_delay_ms=delay_ms if has_local else 0,
            )
        )
    return delay_site(
        lat_deg,
        lon_deg,
        h_m,
        epochs,
        origin_ecef=origin,
        probe_after_t_us=t0,
    )


def turning_yaw_scenario(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    delay_ms: int,
    yaw0: float,
    rate: float,
    turn_s: float = 2.5,
    yaw_offset_rad: float = 0.0,
    yaw_std: float = YAW_TIGHT_STD_RAD,
) -> DelayScenario:
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    epochs = _imu_pad(
        origin,
        duration_s=HAPPY_DURATION_S,
        imu_hz=IMU_HZ,
        gnss_hz=GNSS_HZ,
        gnss_std=GNSS_STD_M,
        gnss_vel=(0.0, 0.0, 0.0),
        gnss_vel_std=DELAY_VEL_STD,
        yaw_rad=yaw0,
        yaw_std=YAW_TIGHT_STD_RAD,
    )
    t0 = epochs[-1].t_us
    imu_hz = IMU_HZ
    dt = 1.0 / imu_hz
    every = imu_hz // LOCAL_HZ
    delay_s = delay_ms * 1.0e-3
    n = int(round(turn_s * imu_hz))
    gyr = (0.0, 0.0, rate)
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        t_turn = i * dt
        t_valid = max(t_turn - delay_s, 0.0)
        yaw_meas = yaw0 + rate * t_valid + yaw_offset_rad
        has_yaw = i % every == 0 and i > 1
        has_gnss = i % (imu_hz // GNSS_HZ) == 0
        epochs.append(
            _delay_epoch(
                t_us,
                dt_sec=dt,
                gyr=gyr,
                gnss_ecef=tuple(origin) if has_gnss else None,
                gnss_std=tuple(GNSS_STD_M) if has_gnss else None,
                gnss_vel=(0.0, 0.0, 0.0) if has_gnss else None,
                gnss_vel_std=tuple(DELAY_VEL_STD) if has_gnss else None,
                yaw_rad=yaw_meas if has_yaw else None,
                yaw_std=float(yaw_std) if has_yaw else None,
                yaw_delay_ms=delay_ms if has_yaw else 0,
            )
        )
    return delay_site(
        lat_deg,
        lon_deg,
        h_m,
        epochs,
        origin_ecef=origin,
        probe_after_t_us=t0,
    )


def write_climb_dataset(
    ws: Workspace,
    *,
    lat_deg: float,
    lon_deg: float,
    h0_m: float,
    lag_s: float,
    relpath: str = "climb",
    pad_s: float = 6.0,
    motion_s: float = 20.0,
    amp_m: float = 14.0,
    freq_hz: float = 0.05,
) -> Path:
    """Write IMU/baro/GNSS/ref + config.yaml. Config delay stays 0; lag is GNSS vertical velocity only."""
    if lag_s < 0.0 or not math.isfinite(lag_s):
        raise HarnessError(f"constructed lag is not a non-negative finite value: {lag_s}")
    dest = ws.resolve(relpath)
    dest.mkdir(parents=True, exist_ok=True)
    imu_hz = IMU_HZ
    gnss_hz = 10
    baro_hz = 50
    dt = 1.0 / imu_hz
    n = int(round((pad_s + motion_s) * imu_hz))
    omega = 2.0 * math.pi * freq_hz

    def height_at(t_s: float) -> float:
        if t_s <= pad_s:
            return h0_m
        tau = t_s - pad_s
        return h0_m + amp_m * (1.0 - math.cos(omega * tau))

    def vel_up_at(t_s: float) -> float:
        if t_s <= pad_s:
            return 0.0
        tau = t_s - pad_s
        return amp_m * omega * math.sin(omega * tau)

    def acc_up_at(t_s: float) -> float:
        if t_s <= pad_s:
            return 0.0
        tau = t_s - pad_s
        return amp_m * omega * omega * math.cos(omega * tau)

    imu_lines = [
        "# t_us, gyr_frd_x [rad/s], gyr_frd_y [rad/s], gyr_frd_z [rad/s], "
        "acc_frd_x [m/s^2], acc_frd_y [m/s^2], acc_frd_z [m/s^2]\n"
    ]
    ref_lines = [
        "# t_us, lat_deg, lon_deg, h_m, roll_deg, pitch_deg, yaw_deg, vn_mps, ve_mps, vd_mps\n"
    ]
    baro_lines = ["# t_us, static pressure [Pa]\n"]
    gnss_lines = [
        "# t_us, lat_deg, lon_deg, h_m, cov_pos_ned nn,ne,nd,ee,ed,dd [m^2], "
        "vn, ve, vd [m/s], cov_vel_ned nn,ne,nd,ee,ed,dd [(m/s)^2], vel_ok\n"
    ]
    gnss_every = imu_hz // gnss_hz
    baro_every = imu_hz // baro_hz
    pos_var = 1.0
    vel_var = 0.04
    for k in range(n + 1):
        t_s = k * dt
        t_us = int(round(t_s * 1e6))
        h = height_at(t_s)
        vu = vel_up_at(t_s)
        au = acc_up_at(t_s)
        fz = -G_MPS2 - au
        imu_lines.append(f"{t_us},0,0,0,0,0,{fz:.9g}\n")
        if k % max(imu_hz // 10, 1) == 0:
            ref_lines.append(
                f"{t_us},{lat_deg:.10f},{lon_deg:.10f},{h:.6f},0,0,0,0,0,{-vu:.6f}\n"
            )
        if k % baro_every == 0:
            baro_lines.append(f"{t_us},{isa_pressure_pa(h):.6f}\n")
        if k % gnss_every == 0:
            t_lag = t_s - lag_s
            if t_lag < 0.0:
                t_lag = 0.0
            vd = -vel_up_at(t_lag)
            gnss_lines.append(
                f"{t_us},{lat_deg:.10f},{lon_deg:.10f},{h:.6f},"
                f"{pos_var},0,0,{pos_var},0,{pos_var},"
                f"0,0,{vd:.6f},"
                f"{vel_var},0,0,{vel_var},0,{vel_var},1\n"
            )
    (dest / "imu.csv").write_text("".join(imu_lines), encoding="utf-8")
    (dest / "ref.csv").write_text("".join(ref_lines), encoding="utf-8")
    (dest / "baro.csv").write_text("".join(baro_lines), encoding="utf-8")
    (dest / "gnss.csv").write_text("".join(gnss_lines), encoding="utf-8")
    (dest / "config.yaml").write_text(
        "\n".join(
            [
                "name: climb-lag",
                "aiding: gnss",
                "init: auto",
                "chi2_disable: 1",
                "allow_unlimited_deadreckoning: 0",
                "imu:",
                "  gyr_psd: 2.5e-09",
                "  acc_psd: 4.0e-06",
                "  gyr_bias_rw: 3.0e-06",
                "  acc_bias_rw: 0.0001",
                "  auto_zupt_disable: 1",
                "gnss:",
                "  delay_ms: 0",
                "  leverarm_frd: [0.0, 0.0, 0.0]",
                "  pos_stddev_fallback_m: [2.0, 3.0]",
                "  vel_stddev_fallback_mps: 0.25",
                "baro:",
                "  enable: 1",
                "mag:",
                "  enable: 0",
                "score:",
                "  warmup_sec: 3",
                "  min_epochs: 0",
                "  ahrs: 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return dest


_LAG_NUM = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
# Contract (replay.py): the forced estimator prints the estimate on its own
# line, "gnss delay estimate: <N> ms". Only that line is read; the rest of the
# report is not pinned and is never searched for a number.
_ESTIMATE_LINE_RE = re.compile(
    rf"^\s*gnss delay estimate:\s*({_LAG_NUM})\s*ms\b",
    re.IGNORECASE | re.MULTILINE,
)


def parse_forced_lag_ms(text: str) -> float:
    """Lag in milliseconds from the pinned ``gnss delay estimate: <N> ms`` line.

    A missing line, or one without a number of milliseconds, is silence: a
    failed observation. The last such line wins.
    """
    found = _ESTIMATE_LINE_RE.findall(text)
    if not found:
        raise AssertionError(
            "forced estimator printed no 'gnss delay estimate: <N> ms' line; "
            "stdout was:\n" + text[-2000:]
        )
    value = float(found[-1])
    if not math.isfinite(value):
        raise AssertionError(f"forced estimator lag is not finite: {found[-1]!r}")
    return value


def forced_replay_lag_ms(
    dataset: str | Path,
    *,
    plot_hz: float = 50.0,
    timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
) -> float:
    """Run the Python replay estimator with force-on. Missing numeric lag asserts."""
    _require_compiled_product()
    result = run_replay(
        dataset,
        ["--estimate-gnss-delay", f"--plot-hz={plot_hz}"],
        timeout=timeout,
        root=repo_root(),
    )
    if result.returncode != 0:
        err = ""
        try:
            err = result.stderr_text
        except HarnessError:
            err = "<stderr not utf-8>"
        raise HarnessError(
            f"replay estimator exited {result.returncode} stderr={err!r} "
            f"stdout={result.stdout_text[-1500:]!r}"
        )
    text = result.stdout_text
    print(f"replay stdout tail={text[-1200:]!r}", flush=True)
    return parse_forced_lag_ms(text)
