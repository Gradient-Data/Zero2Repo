# feature: F02
"""Observation helpers for FP-02 INS IMU-plus-GNSS fusion.

C probes compile through the sealed harness. Python observations run in a
child interpreter. This module does not import the product in the pytest
process. Expected ECEF/NED values come from the GNSS the test fed and from
independent WGS84 geometry, never from the library's own origin-refresh
formula.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from _harness import (
    HarnessError,
    invoke,
    product_identity,
    run_python,
    runtime_uuid_int,
    nonfinite_fields,
    note_product_issue,
)
from F01_helpers import (
    require_probe_success as _require_probe_success,
    wgs84_ecef_from_geodetic as _wgs84_ecef_from_geodetic,
)

# ---------------------------------------------------------------------------
# Fixed inputs and tolerances
# ---------------------------------------------------------------------------

ORIGIN_NORM_MIN_M = 1000.0
EARTH_ECEF_NORM_M = 6.4e6
IMU_HZ = 100
GNSS_HZ = 1
DT_SEC = 0.01
SPECIFIC_FORCE_LEVEL = (0.0, 0.0, -9.81)
GNSS_STD_M = (2.0, 2.0, 2.0)
LEVER_RIGHT_15CM = (0.0, 0.15, 0.0)
READY_WAIT_S = 1.5
ENTRY_DWELL_S = 5.0
# Default dwell starts at the first 1 Hz fix (t=1 s) so bootstrap is near 6 s;
# ready needs 1.5 s after that. 8 s of 100 Hz covers the happy path with margin.
HAPPY_DURATION_S = 8.0
ECEF_MATCH_M = 0.5  # "well under a metre"
LEVEL_RAD = math.radians(0.4)  # "well under half a degree"
STILL_VEL_MPS = 1.0
LONG_TIMEOUT = 90.0
SPARSE_DT_S = 0.5  # at the published max-prediction default, not an unpublished cadence knob
POST_INIT_SPARSE = 3
SPARSE_MORE = 5
MUNICH_LAT_DEG = 48.1372
MUNICH_LON_DEG = 11.5756

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
    const ins_diag_t *d = ins_get_diag(f);
    unsigned n_used = d ? d->n_gnss_used : 0;
    unsigned n_pred = d ? d->n_predict : 0;
    unsigned n_seen = d ? d->n_gnss_seen : 0;
    unsigned n_rej = d ? d->n_gnss_rejected_noise : 0;
    float residual = d ? d->last_gnss_pos_residual_m : 0.0f;
    int residual_ok = d ? 1 : 0;
    printf("SNAP t_us=%lld ready=%d pos=%d vel=%d rpy=%d ned=%d bacc=%d bgyr=%d",
           t_us, ins_is_ready(f) ? 1 : 0, pos, vel_ok, rpy_ok, ned_ok, bacc_ok,
           bgyr_ok);
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
    if (residual_ok) {
        printf(" residual=%.9g", residual);
    } else {
        printf(" residual=-");
    }
    printf(" n_used=%u n_pred=%u n_seen=%u n_rej=%u\n", n_used, n_pred, n_seen,
           n_rej);
}

int main(void)
{
    char line[4096];
    int missing = 0;
    float fusion_h = 0.0f, fusion_v = 0.0f, fusion_hv = 0.0f, fusion_vv = 0.0f;
    double ox = 0.0, oy = 0.0, oz = 0.0;
    double lat_deg = 0.0, lon_deg = 0.0, h_m = 0.0;
    int skip_epoch = 0, extra_reads = 0, py_full = 0, zupt_off = 0;
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("header1");
    }
    if (sscanf(line, "%d %f %f %f %f %lf %lf %lf", &missing, &fusion_h, &fusion_v,
               &fusion_hv, &fusion_vv, &ox, &oy, &oz) != 8) {
        return fail_read("header1 fields");
    }
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("header2");
    }
    if (sscanf(line, "%lf %lf %lf %d %d %d %d", &lat_deg, &lon_deg, &h_m, &skip_epoch,
               &extra_reads, &py_full, &zupt_off) != 7) {
        return fail_read("header2 fields");
    }
    (void)lat_deg;
    (void)lon_deg;
    (void)h_m;
    (void)skip_epoch;
    (void)py_full;

    ins_t ins = {0};
    ins_init_t init = {0};
    ins_options_t opt = {0};
    opt.auto_init = true;
    opt.auto_zupt_disable = zupt_off ? true : false;
    init.x_ecef[0] = ox;
    init.x_ecef[1] = oy;
    init.x_ecef[2] = oz;
    if (fusion_h > 0.0f) {
        opt.gnss_max_horizontal_pos_stddev_m = fusion_h;
    }
    if (fusion_v > 0.0f) {
        opt.gnss_max_vertical_pos_stddev_m = fusion_v;
    }
    if (fusion_hv > 0.0f) {
        opt.gnss_max_horizontal_vel_stddev_mps = fusion_hv;
    }
    if (fusion_vv > 0.0f) {
        opt.gnss_max_vertical_vel_stddev_mps = fusion_vv;
    }

    int rc;
    if (missing == 1) {
        rc = ins_init(&ins, NULL, &opt);
    } else if (missing == 2) {
        rc = ins_init(&ins, &init, NULL);
    } else {
        rc = ins_init(&ins, &init, &opt);
    }
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
        int acc_v, gyr_v, gp, gv;
        double e0, e1, e2, sn, se, sd, vn, ve, vd, vsn, vse, vsd, lx, ly, lz;
        if (sscanf(line,
                   "E %lld %lf %lf %lf %lf %lf %lf %lf %d %d %d %lf %lf %lf %lf "
                   "%lf %lf %d %lf %lf %lf %lf %lf %lf %lf %lf %lf",
                   &t_us, &dt, &ax, &ay, &az, &gx, &gy, &gz, &acc_v, &gyr_v, &gp, &e0,
                   &e1, &e2, &sn, &se, &sd, &gv, &vn, &ve, &vd, &vsn, &vse, &vsd,
                   &lx, &ly, &lz) != 27) {
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
        }
        if (gv) {
            m.gnss_vel.is_valid = true;
            m.gnss_vel.vel_ned[0] = (float)vn;
            m.gnss_vel.vel_ned[1] = (float)ve;
            m.gnss_vel.vel_ned[2] = (float)vd;
            m.gnss_vel.Qll_ned[0] = (float)(vsn * vsn);
            m.gnss_vel.Qll_ned[4] = (float)(vse * vse);
            m.gnss_vel.Qll_ned[8] = (float)(vsd * vsd);
        }
        m.gnss_leverarm_b[0] = (float)lx;
        m.gnss_leverarm_b[1] = (float)ly;
        m.gnss_leverarm_b[2] = (float)lz;
        ins_update(&ins, &m);
        print_snap(&ins, t_us);
    }
    {
        int i;
        for (i = 0; i < extra_reads; ++i) {
            (void)ins_is_ready(&ins);
            double ecef[3];
            float r, p, y;
            (void)ins_get_position_ecef(&ins, ecef);
            (void)ins_get_rpy(&ins, &r, &p, &y);
        }
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
    residual = "-"
    n_used = _cnt(diag, "n_gnss_used")
    n_pred = _cnt(diag, "n_predict")
    n_seen = _cnt(diag, "n_gnss_seen")
    n_rej = _cnt(diag, "n_gnss_rejected_noise")
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
    line += " residual=" + residual
    line += " n_used=%d n_pred=%d n_seen=%d n_rej=%d" % (n_used, n_pred, n_seen, n_rej)
    print(line)

header1 = sys.stdin.readline()
if not header1:
    raise SystemExit("missing header1")
parts = header1.split()
if len(parts) != 8:
    raise SystemExit("header1 fields")
missing = int(parts[0])
fusion_h, fusion_v, fusion_hv, fusion_vv = [float(x) for x in parts[1:5]]
ox, oy, oz = [float(x) for x in parts[5:8]]
header2 = sys.stdin.readline()
if not header2:
    raise SystemExit("missing header2")
h2 = header2.split()
if len(h2) != 7:
    raise SystemExit("header2 fields")
lat_deg, lon_deg, h_m = [float(x) for x in h2[0:3]]
skip_epoch = int(h2[3])
extra_reads = int(h2[4])
py_full = int(h2[5])
zupt_off = int(h2[6])

cfg_kw = dict(
    auto_init=True,
    lat_rad=math.radians(lat_deg),
    lon_rad=math.radians(lon_deg),
    h_m=h_m,
)
if zupt_off:
    cfg_kw["auto_zupt_disable"] = True
if fusion_h > 0.0:
    cfg_kw["gnss_max_horizontal_pos_stddev_m"] = fusion_h
if fusion_v > 0.0:
    cfg_kw["gnss_max_vertical_pos_stddev_m"] = fusion_v
if fusion_hv > 0.0:
    cfg_kw["gnss_max_horizontal_vel_stddev_mps"] = fusion_hv
if fusion_vv > 0.0:
    cfg_kw["gnss_max_vertical_vel_stddev_mps"] = fusion_vv

try:
    nav = Ins(Config(**cfg_kw))
except ValueError as exc:
    print("INIT rc=-1")
    print("SNAP t_us=0 ready=0 pos=0 vel=0 rpy=0 ned=0 bacc=0 bgyr=0 "
          "ecef=- nedpos=- velned=- att=- attstd=- biasacc=- biasgyr=- residual=- "
          "n_used=0 n_pred=0 n_seen=0 n_rej=0")
    raise SystemExit(0) from exc

print("INIT rc=0")
# Keep origin bytes on the payload so a GNSS-smoother that ignores the
# Config anchor cannot pretend the header was unused.
_ = (ox, oy, oz, missing)

last_t = 0
for raw in sys.stdin:
    if not raw.strip() or raw.startswith("#"):
        continue
    if not raw.startswith("E "):
        raise SystemExit("epoch tag")
    tok = raw.split()
    if len(tok) != 28:
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
    lever = (float(tok[25]), float(tok[26]), float(tok[27]))
    last_t = t_us
    if acc_v and gyr_v:
        nav.imu(t_us, dt, acc, gyr)
    elif acc_v or gyr_v:
        # Still begin the epoch; the wrapper requires an IMU push. Validity
        # of a sub-measurement is a C-side flag; the Python wrapper always
        # pushes the sample it is given. Invalid-IMU tests are C-side.
        nav.imu(t_us, dt, acc, gyr)
    else:
        nav.imu(t_us, dt, acc, gyr)
    if gp:
        var = (std[0] * std[0], std[1] * std[1], std[2] * std[2])
        if py_full:
            cov = [[var[0], 0.0, 0.0], [0.0, var[1], 0.0], [0.0, 0.0, var[2]]]
            nav.gnss_pos(ecef, cov)
        else:
            nav.gnss_pos(ecef, var)
    if gv:
        varv = (vstd[0] * vstd[0], vstd[1] * vstd[1], vstd[2] * vstd[2])
        if py_full:
            covv = [[varv[0], 0.0, 0.0], [0.0, varv[1], 0.0], [0.0, 0.0, varv[2]]]
            nav.gnss_vel(vel, covv)
        else:
            nav.gnss_vel(vel, varv)
    if lever != (0.0, 0.0, 0.0):
        nav.gnss_leverarm(lever)
    if not skip_epoch:
        nav.update()
    emit(nav, t_us)

for _ in range(extra_reads):
    nav.is_ready()
    nav.position_ecef()
    nav.rpy()
if extra_reads:
    emit(nav, last_t)
"""


@dataclass
class Epoch:
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
    lever: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class InsScenario:
    origin_ecef: tuple[float, float, float]
    lat_deg: float
    lon_deg: float
    h_m: float
    epochs: list[Epoch] = field(default_factory=list)
    missing: int = 0  # 0 none, 1 null init, 2 null opt
    fusion_h: float = 0.0
    fusion_v: float = 0.0
    fusion_hv: float = 0.0
    fusion_vv: float = 0.0
    skip_epoch: bool = False
    extra_reads: int = 0
    py_full_cov: bool = False
    # Public ins_options_t.auto_zupt_disable / Config(auto_zupt_disable=...):
    # probes that are not about the standstill detector turn it off so its
    # (unspecified) tuning cannot decide their result.
    auto_zupt_disable: bool = False


@dataclass
class InsSnapshot:
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
    residual_m: float | None
    n_gnss_used: int
    n_predict: int
    n_gnss_seen: int
    n_gnss_rejected_noise: int


@dataclass
class InsRun:
    init_ok: bool
    snaps: list[InsSnapshot]

    def last(self) -> InsSnapshot:
        if not self.snaps:
            raise HarnessError("run produced no snapshots")
        return self.snaps[-1]

    def first_initialized(self) -> InsSnapshot | None:
        for snap in self.snaps:
            if snap.pos_ok:
                return snap
        return None


def ecef_from_llh_deg(lat_deg: float, lon_deg: float, height_m: float) -> tuple[float, float, float]:
    """Independent WGS84 geodetic → ECEF. Raises if the result is not finite."""
    xyz = _wgs84_ecef_from_geodetic(
        math.radians(lat_deg), math.radians(lon_deg), height_m
    )
    if not all(math.isfinite(v) for v in xyz):
        raise HarnessError(f"independent ECEF is not finite for {lat_deg},{lon_deg},{height_m}")
    return xyz


def _ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Closed-form Bowring ECEF → geodetic. Does not call the product."""
    a = 6378137.0
    e2 = 6.69437999014e-3
    b = a * math.sqrt(1.0 - e2)
    r = math.hypot(x, y)
    if r == 0.0 and z == 0.0:
        raise HarnessError("ECEF origin has no geodetic latitude")
    eb2 = (a * a - b * b) / (b * b)
    theta = math.atan2(z * a, r * b)
    lat = math.atan2(
        z + eb2 * b * math.sin(theta) ** 3, r - e2 * a * math.cos(theta) ** 3
    )
    lon = math.atan2(y, x)
    slat = math.sin(lat)
    n = a / math.sqrt(1.0 - e2 * slat * slat)
    height = r / math.cos(lat) - n if abs(math.cos(lat)) > 1e-12 else abs(z) - b * math.sqrt(1.0 - e2)
    if not (math.isfinite(lat) and math.isfinite(lon) and math.isfinite(height)):
        raise HarnessError(f"geodetic inverse not finite for ECEF {x},{y},{z}")
    return lat, lon, height


def ned_offset_from_two_ecef(
    origin: Sequence[float], point: Sequence[float]
) -> tuple[float, float, float]:
    """ECEF difference expressed in NED at the origin. Raises, never returns a zero sentinel."""
    if len(origin) != 3 or len(point) != 3:
        raise HarnessError("ECEF vectors must have 3 components")
    lat, lon, _h = _ecef_to_geodetic(origin[0], origin[1], origin[2])
    dx = point[0] - origin[0]
    dy = point[1] - origin[1]
    dz = point[2] - origin[2]
    slat, clat = math.sin(lat), math.cos(lat)
    slon, clon = math.sin(lon), math.cos(lon)
    north = -slat * clon * dx - slat * slon * dy + clat * dz
    east = -slon * dx + clon * dy
    down = -clat * clon * dx - clat * slon * dy - slat * dz
    if not (math.isfinite(north) and math.isfinite(east) and math.isfinite(down)):
        raise HarnessError("NED offset is not finite")
    return north, east, down


def ecef_plus_ned(
    origin: Sequence[float], dn: float, de: float, dd: float
) -> tuple[float, float, float]:
    """Add a NED displacement to an ECEF origin (independent geometry)."""
    lat, lon, _h = _ecef_to_geodetic(origin[0], origin[1], origin[2])
    slat, clat = math.sin(lat), math.cos(lat)
    slon, clon = math.sin(lon), math.cos(lon)
    dx = -slat * clon * dn - slon * de - clat * clon * dd
    dy = -slat * slon * dn + clon * de - clat * slon * dd
    dz = clat * dn - slat * dd
    out = (origin[0] + dx, origin[1] + dy, origin[2] + dz)
    if not all(math.isfinite(v) for v in out):
        raise HarnessError("ECEF+NED is not finite")
    return out


def runtime_site() -> tuple[float, float, float]:
    """Runtime geodetic site that is not the tutorial Munich row."""
    u = runtime_uuid_int()
    lat = 36.0 + (u % 900) / 80.0
    lon = -5.0 + ((u // 900) % 2000) / 80.0
    h = 40.0 + ((u // 1_800_000) % 450)
    if abs(lat - MUNICH_LAT_DEG) < 0.4 and abs(lon - MUNICH_LON_DEG) < 0.4:
        lat += 1.7
        lon -= 2.1
    print(f"runtime site lat={lat} lon={lon} h={h}", flush=True)
    return lat, lon, float(h)


def runtime_sub_km_ecef() -> tuple[float, float, float]:
    """Non-zero ECEF inside the 1 km neighbourhood, not a 500 m axis sample."""
    u = runtime_uuid_int()
    az = (u % 360) * math.pi / 180.0
    el = (((u // 360) % 80) - 40) * math.pi / 180.0
    r = 120.0 + ((u // 28800) % 700)
    x = r * math.cos(el) * math.cos(az)
    y = r * math.cos(el) * math.sin(az)
    z = r * math.sin(el)
    nrm = math.sqrt(x * x + y * y + z * z)
    if nrm >= ORIGIN_NORM_MIN_M or nrm < 50.0:
        raise HarnessError(f"runtime sub-km origin has norm {nrm}")
    if abs(x) < 1.0 and abs(y) < 1.0 and abs(z) < 1.0:
        x += 80.0
    print(f"runtime sub-km origin {x},{y},{z} norm={nrm}", flush=True)
    return x, y, z


def runtime_lever() -> tuple[float, float, float]:
    """Non-zero lever that is not the named 15 cm right sample."""
    u = runtime_uuid_int()
    length = 0.04 + ((u % 90) / 1000.0)
    if abs(length - 0.15) < 0.01:
        length = 0.07
    axis = (u // 90) % 2
    if axis == 0:
        lever = (length, 0.0, 0.0)
    else:
        lever = (0.0, 0.0, length)
    print(f"runtime lever {lever}", flush=True)
    return lever


def runtime_roll_fy() -> float:
    """Specific-force y increment for the roll-leveling arm (not a table row)."""
    u = runtime_uuid_int()
    mag = 0.45 + (u % 70) / 100.0
    sign = -1.0 if (u // 70) % 2 == 0 else 1.0
    fy = sign * mag
    print(f"runtime roll fy={fy}", flush=True)
    return fy


def runtime_pitch_fx() -> float:
    u = runtime_uuid_int()
    mag = 0.40 + (u % 80) / 100.0
    sign = 1.0 if (u // 80) % 2 == 0 else -1.0
    fx = sign * mag
    print(f"runtime pitch fx={fx}", flush=True)
    return fx


def runtime_ned_shift_m() -> tuple[float, float, float]:
    """Coarse-origin offset. Auto-init rebases onto GNSS, so this is not a
    post-ready jump and may be tens of metres."""
    u = runtime_uuid_int()
    north = 6.0 + (u % 250) / 10.0
    east = -18.0 + ((u // 250) % 300) / 10.0
    down = ((u // 75000) % 21) / 10.0 - 1.0
    print(f"runtime NED shift n={north} e={east} d={down}", flush=True)
    return north, east, down


def runtime_gnss_step_m() -> tuple[float, float, float]:
    """Post-ready GNSS step small enough that a 2 m 1-sigma fix is not an
    outlier, but still larger than the sub-metre ECEF match bound."""
    u = runtime_uuid_int()
    north = 1.8 + (u % 16) / 10.0
    east = 0.7 + ((u // 16) % 14) / 10.0
    down = ((u // 224) % 9) / 20.0 - 0.2
    print(f"runtime GNSS step n={north} e={east} d={down}", flush=True)
    return north, east, down


def runtime_north_vel() -> float:
    u = runtime_uuid_int()
    vn = 0.18 + (u % 25) / 100.0
    print(f"runtime north vel {vn}", flush=True)
    return vn


def ecef_norm(xyz: Sequence[float]) -> float:
    n = math.sqrt(sum(v * v for v in xyz))
    if not math.isfinite(n):
        raise HarnessError("ECEF norm is not finite")
    return n


def stationary_imu_gnss_stream(
    gnss_ecef: Sequence[float],
    *,
    duration_s: float = HAPPY_DURATION_S,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_std: Sequence[float] = GNSS_STD_M,
    lever: Sequence[float] = (0.0, 0.0, 0.0),
    imu_hz: int = IMU_HZ,
    gnss_hz: int = GNSS_HZ,
    acc_valid: bool = True,
    gyr_valid: bool = True,
    gnss_vel: Sequence[float] | None = None,
    gnss_vel_std: Sequence[float] | None = None,
    gnss_ecef_override: Sequence[float] | None = None,
) -> list[Epoch]:
    """100 Hz IMU + 1 Hz GNSS stream. Site is caller-supplied."""
    if imu_hz <= 0 or gnss_hz <= 0:
        raise HarnessError("rates must be positive")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    gnss_every = imu_hz // gnss_hz
    if gnss_every <= 0:
        raise HarnessError("GNSS rate cannot exceed IMU rate")
    fix = tuple(gnss_ecef_override) if gnss_ecef_override is not None else tuple(gnss_ecef)
    epochs: list[Epoch] = []
    for k in range(1, n + 1):
        t_us = int(round(k * dt * 1e6))
        has_gnss = k % gnss_every == 0
        epochs.append(
            Epoch(
                t_us=t_us,
                dt_sec=dt,
                acc=(float(acc[0]), float(acc[1]), float(acc[2])),
                gyr=(float(gyr[0]), float(gyr[1]), float(gyr[2])),
                acc_valid=acc_valid,
                gyr_valid=gyr_valid,
                gnss_ecef=fix if has_gnss else None,
                gnss_std=tuple(gnss_std) if has_gnss else None,
                gnss_vel=tuple(gnss_vel) if (has_gnss and gnss_vel is not None) else None,
                gnss_vel_std=tuple(gnss_vel_std)
                if (has_gnss and gnss_vel is not None)
                else None,
                lever=tuple(lever),
            )
        )
    return epochs


def append_imu_only(
    epochs: list[Epoch],
    *,
    count: int,
    dt_s: float = DT_SEC,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    lever: Sequence[float] = (0.0, 0.0, 0.0),
    acc_valid: bool = True,
    gyr_valid: bool = True,
) -> list[Epoch]:
    """Append *count* IMU-only epochs (no GNSS) after the last timestamp."""
    if not epochs:
        raise HarnessError("IMU-only append needs a preceding stream")
    if count <= 0:
        raise HarnessError("IMU-only append count must be positive")
    if dt_s <= 0.0:
        raise HarnessError("IMU-only append dt must be positive")
    t0 = epochs[-1].t_us
    out = list(epochs)
    for i in range(1, count + 1):
        t_us = t0 + int(round(i * dt_s * 1e6))
        out.append(
            Epoch(
                t_us=t_us,
                dt_sec=dt_s,
                acc=(float(acc[0]), float(acc[1]), float(acc[2])),
                gyr=(float(gyr[0]), float(gyr[1]), float(gyr[2])),
                acc_valid=acc_valid,
                gyr_valid=gyr_valid,
                gnss_ecef=None,
                gnss_std=None,
                lever=tuple(lever),
            )
        )
    return out


def append_sparse_imu(
    epochs: list[Epoch],
    *,
    count: int,
    dt_s: float = SPARSE_DT_S,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_ecef: Sequence[float],
    gnss_std: Sequence[float] = GNSS_STD_M,
    lever: Sequence[float] = (0.0, 0.0, 0.0),
    acc_valid: bool = True,
    gyr_valid: bool = True,
) -> list[Epoch]:
    """Append *count* IMU(+GNSS) epochs spaced by *dt_s* after the last timestamp."""
    if not epochs:
        raise HarnessError("sparse append needs a preceding stream")
    t0 = epochs[-1].t_us
    out = list(epochs)
    for i in range(1, count + 1):
        t_us = t0 + int(round(i * dt_s * 1e6))
        out.append(
            Epoch(
                t_us=t_us,
                dt_sec=dt_s,
                acc=(float(acc[0]), float(acc[1]), float(acc[2])),
                gyr=(float(gyr[0]), float(gyr[1]), float(gyr[2])),
                acc_valid=acc_valid,
                gyr_valid=gyr_valid,
                gnss_ecef=tuple(gnss_ecef),
                gnss_std=tuple(gnss_std),
                lever=tuple(lever),
            )
        )
    return out


def clip_through_initialized(epochs: list[Epoch], t_init_us: int) -> list[Epoch]:
    kept = [e for e in epochs if e.t_us <= t_init_us]
    if not kept:
        raise HarnessError("no epoch at or before initialized timestamp")
    return kept


def encode_scenario(scen: InsScenario) -> str:
    ox, oy, oz = scen.origin_ecef
    lines = [
        f"{scen.missing} {scen.fusion_h} {scen.fusion_v} {scen.fusion_hv} "
        f"{scen.fusion_vv} {ox:.17g} {oy:.17g} {oz:.17g}",
        f"{scen.lat_deg:.17g} {scen.lon_deg:.17g} {scen.h_m:.17g} "
        f"{int(scen.skip_epoch)} {scen.extra_reads} {int(scen.py_full_cov)} "
        f"{int(scen.auto_zupt_disable)}",
    ]
    for e in scen.epochs:
        gp = 1 if e.gnss_ecef is not None else 0
        ecef = e.gnss_ecef if e.gnss_ecef is not None else (0.0, 0.0, 0.0)
        std = e.gnss_std if e.gnss_std is not None else (0.0, 0.0, 0.0)
        gv = 1 if e.gnss_vel is not None else 0
        vel = e.gnss_vel if e.gnss_vel is not None else (0.0, 0.0, 0.0)
        vstd = e.gnss_vel_std if e.gnss_vel_std is not None else (0.1, 0.1, 0.1)
        lines.append(
            "E %d %.17g %.17g %.17g %.17g %.17g %.17g %.17g %d %d %d "
            "%.17g %.17g %.17g %.17g %.17g %.17g %d %.17g %.17g %.17g "
            "%.17g %.17g %.17g %.17g %.17g %.17g"
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
                e.lever[0],
                e.lever[1],
                e.lever[2],
            )
        )
    return "\n".join(lines) + "\n"


def _parse_flag(fields: dict[str, str], key: str) -> bool:
    if key not in fields:
        raise HarnessError(f"snapshot missing {key}")
    raw = fields[key]
    if raw not in ("0", "1"):
        raise HarnessError(f"{key} is not 0/1: {raw!r}")
    return raw == "1"


def _parse_vec(fields: dict[str, str], key: str, present: bool) -> tuple[float, float, float] | None:
    if key not in fields:
        raise HarnessError(f"snapshot missing {key}")
    raw = fields[key]
    if raw == "-":
        if present:
            raise HarnessError(f"{key} marked present but value is absent")
        return None
    parts = raw.split(",")
    if len(parts) != 3:
        raise HarnessError(f"{key} is not a triple: {raw!r}")
    try:
        vals = (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError as exc:
        raise HarnessError(f"{key} not floats: {raw!r}") from exc
    if not present:
        raise HarnessError(f"{key} marked absent but a triple was printed")
    return vals


def _parse_optional_float(fields: dict[str, str], key: str) -> float | None:
    if key not in fields:
        raise HarnessError(f"snapshot missing {key}")
    raw = fields[key]
    if raw == "-":
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise HarnessError(f"{key} not a float: {raw!r}") from exc
    return value


def _parse_int(fields: dict[str, str], key: str) -> int:
    if key not in fields:
        raise HarnessError(f"snapshot missing {key}")
    try:
        return int(fields[key])
    except ValueError as exc:
        raise HarnessError(f"{key} not an int: {fields[key]!r}") from exc


def parse_snapshot_line(line: str) -> InsSnapshot:
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
    residual = _parse_optional_float(fields, "residual")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F02', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F02', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F02', f"ins_get_diag returned NULL for a live instance: {line}")
    for _key in ("n_used", "n_pred", "n_seen", "n_rej"):
        if _parse_int(fields, _key) < 0:
            note_product_issue("F02", f"diagnostic counter {_key}={fields[_key]} missing or negative: {line}")
    return InsSnapshot(
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
        residual_m=residual,
        n_gnss_used=_parse_int(fields, "n_used"),
        n_predict=_parse_int(fields, "n_pred"),
        n_gnss_seen=_parse_int(fields, "n_seen"),
        n_gnss_rejected_noise=_parse_int(fields, "n_rej"),
    )


def parse_run(text: str) -> InsRun:
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
    snaps = [parse_snapshot_line(ln) for ln in lines if ln.startswith("SNAP ")]
    return InsRun(init_ok=(rc == 0), snaps=snaps)


def _run_probe(kind: str, scen: InsScenario) -> InsRun:
    payload = encode_scenario(scen)
    if kind == "c":
        result = invoke(_C_PROBE, stdin=payload, timeout=LONG_TIMEOUT)
    elif kind == "py":
        ident = product_identity()
        assert ident is not None, "python package directory was not found after make pylib"
        package = ident.package_name
        assert package.isidentifier(), f"discovered package name is not importable: {package!r}"
        result = run_python(
            _PY_PROBE.replace("__PKG__", package),
            stdin=payload,
            timeout=LONG_TIMEOUT,
        )
    else:
        raise HarnessError(f"unknown probe kind {kind!r}")
    text = _require_probe_success(result)
    run = parse_run(text)
    print(
        f"{kind} init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_ready={run.last().ready if run.snaps else None}",
        flush=True,
    )
    return run


def c_ins_run(scen: InsScenario) -> InsRun:
    return _run_probe("c", scen)


def py_ins_run(scen: InsScenario) -> InsRun:
    return _run_probe("py", scen)


def _config_llh(origin: tuple[float, float, float], lat_deg: float, lon_deg: float, h_m: float):
    """Python Config is a geodetic origin. Below 1 km the inverse is undefined."""
    if ecef_norm(origin) < ORIGIN_NORM_MIN_M:
        return lat_deg, lon_deg, h_m
    olat, olon, oh = _ecef_to_geodetic(origin[0], origin[1], origin[2])
    return math.degrees(olat), math.degrees(olon), oh


def site_scenario(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    epochs: list[Epoch],
    *,
    origin_ecef: tuple[float, float, float] | None = None,
    **kwargs,
) -> InsScenario:
    origin = origin_ecef if origin_ecef is not None else ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    clat, clon, ch = _config_llh(origin, lat_deg, lon_deg, h_m)
    return InsScenario(
        origin_ecef=origin,
        lat_deg=clat,
        lon_deg=clon,
        h_m=ch,
        epochs=epochs,
        **kwargs,
    )


def retimed(epochs: list[Epoch], t_off_us: int) -> list[Epoch]:
    from dataclasses import replace

    return [replace(e, t_us=e.t_us + t_off_us) for e in epochs]


def happy_scenario(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    *,
    duration_s: float = HAPPY_DURATION_S,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    origin_ecef: tuple[float, float, float] | None = None,
    gnss_ecef: Sequence[float] | None = None,
    gnss_std: Sequence[float] = GNSS_STD_M,
    lever: Sequence[float] = (0.0, 0.0, 0.0),
    **kwargs,
) -> InsScenario:
    ecef = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    origin = origin_ecef if origin_ecef is not None else ecef
    fix = tuple(gnss_ecef) if gnss_ecef is not None else ecef
    epochs = stationary_imu_gnss_stream(
        fix,
        duration_s=duration_s,
        acc=acc,
        gyr=gyr,
        gnss_std=gnss_std,
        lever=lever,
    )
    return site_scenario(lat_deg, lon_deg, h_m, epochs, origin_ecef=origin, **kwargs)


def require_finite_solution(snap: InsSnapshot) -> None:
    if not (snap.pos_ok and snap.vel_ok and snap.rpy_ok and snap.ned_ok):
        raise AssertionError(
            f"accessors not all successful at t={snap.t_us} "
            f"pos={snap.pos_ok} vel={snap.vel_ok} rpy={snap.rpy_ok} ned={snap.ned_ok}"
        )
    if snap.ecef is None or snap.ned is None or snap.vel_ned is None or snap.rpy is None:
        raise AssertionError("successful accessors returned no vectors")
    if not snap.bias_acc_ok or not snap.bias_gyr_ok:
        raise AssertionError("bias accessors failed after initialization")
    if snap.bias_acc is None or snap.bias_gyr is None:
        raise AssertionError("bias accessors succeeded without values")
