# feature: F03
"""Observation helpers for FP-03 aiding beyond GNSS.

C probes compile through the sealed harness. Python observations run in a
child interpreter. This module does not import the product in the pytest
process. Expected NED, heading, and ISA-derived *inputs* come from the tracker
or magnetometer the test fed and from independent WMM / ZYX geometry, never
from the library's own fusion matrices.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
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
    angle_diff_deg,
    hamilton_zyx_quaternion,
    independent_wmm,
    require_probe_success,
)
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
    runtime_site,
)

# Fixed indoor tracker inputs and tolerances.
TRACKER_NAMED_NED = (1.5, 0.0, 0.0)
LOCAL_HZ = 10
CM_STD_M = 0.01
MAG_DEFAULT_DELAY_MS = 1000
SPEED_MIN_MPS = 1.0
YAW_STD_RAD = math.radians(3.0)
WMM_YEAR = 2026.5
ISA_P0_PA = 101325.0
ISA_SCALE_M = 44330.0
ISA_EXP = 5.255
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
    printf(" n_invalid=%u n_downweighted=%u n_fuse_fail=%u n_auto_zupt=%u n_predict=%u stationary=%d\n",
           d->n_invalid_input, d->n_downweighted, d->n_fuse_fail, d->n_auto_zupt,
           d->n_predict, ins_auto_zupt_active(f) ? 1 : 0);
}

int main(void)
{
    char line[8192];
    double ox = 0.0, oy = 0.0, oz = 0.0;
    int mag_delay_ms = 0, auto_zupt_disable = 0, baro_height_disable = 0;
    double mag_n0 = 0.0, mag_n1 = 0.0, mag_n2 = 0.0;
    double lat_deg = 0.0, lon_deg = 0.0, h_m = 0.0;
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("header1");
    }
    if (sscanf(line, "%lf %lf %lf %d %d %d %lf %lf %lf", &ox, &oy, &oz,
               &mag_delay_ms, &auto_zupt_disable, &baro_height_disable, &mag_n0,
               &mag_n1, &mag_n2) != 9) {
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
    opt.auto_init = true;
    init.x_ecef[0] = ox;
    init.x_ecef[1] = oy;
    init.x_ecef[2] = oz;
    init.magnetic_n[0] = (float)mag_n0;
    init.magnetic_n[1] = (float)mag_n1;
    init.magnetic_n[2] = (float)mag_n2;
    opt.magnetometer_min_delay_ms = mag_delay_ms;
    opt.auto_zupt_disable = auto_zupt_disable ? true : false;
    opt.baro_height_disable = baro_height_disable ? true : false;

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
        double vn, ve, vd, vsn, vse, vsd, lx, ly, lz;
        int lp;
        double ln, le, ld, lsn, lse, lsd;
        int mg;
        double mx, my, mz, mvx, mvy, mvz;
        int yw;
        double yaw_rad, ystd;
        int sp;
        double speed;
        int br;
        double pa;
        int zupt, zaru, wmm;
        double wlat, wlon, wyear;
        int azd;
        if (sscanf(line,
                   "E %lld %lf %lf %lf %lf %lf %lf %lf %d %d %d %lf %lf %lf %lf "
                   "%lf %lf %d %lf %lf %lf %lf %lf %lf %lf %lf %lf %d %lf %lf "
                   "%lf %lf %lf %lf %d %lf %lf %lf %lf %lf %lf %d %lf %lf %d %lf "
                   "%d %lf %d %d %d %lf %lf %lf %d",
                   &t_us, &dt, &ax, &ay, &az, &gx, &gy, &gz, &acc_v, &gyr_v, &gp,
                   &e0, &e1, &e2, &sn, &se, &sd, &gv, &vn, &ve, &vd, &vsn, &vse,
                   &vsd, &lx, &ly, &lz, &lp, &ln, &le, &ld, &lsn, &lse, &lsd, &mg,
                   &mx, &my, &mz, &mvx, &mvy, &mvz, &yw, &yaw_rad, &ystd, &sp,
                   &speed, &br, &pa, &zupt, &zaru, &wmm, &wlat, &wlon, &wyear,
                   &azd) != 55) {
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
        if (lp) {
            m.local_pos.is_valid = true;
            m.local_pos.pos_ned[0] = (float)ln;
            m.local_pos.pos_ned[1] = (float)le;
            m.local_pos.pos_ned[2] = (float)ld;
            m.local_pos.Qll_ned[0] = (float)(lsn * lsn);
            m.local_pos.Qll_ned[4] = (float)(lse * lse);
            m.local_pos.Qll_ned[8] = (float)(lsd * lsd);
        }
        if (mg) {
            m.mag.is_valid = true;
            m.mag.data[0] = (float)mx;
            m.mag.data[1] = (float)my;
            m.mag.data[2] = (float)mz;
            m.mag.Qll_diag[0] = (float)mvx;
            m.mag.Qll_diag[1] = (float)mvy;
            m.mag.Qll_diag[2] = (float)mvz;
        }
        if (yw) {
            m.yaw.is_valid = true;
            m.yaw.yaw_rad = (float)yaw_rad;
            m.yaw.stddev_rad = (float)ystd;
        }
        if (sp) {
            m.speed.is_valid = true;
            m.speed.speed_mps = (float)speed;
        }
        if (br) {
            m.baro.is_valid = true;
            m.baro.pressure_pa = (float)pa;
        }
        m.zero_velocity_update = zupt ? true : false;
        m.zero_rotation_update = zaru ? true : false;
        if (wmm) {
            ins_set_magnetic_model_from_position(&ins, wlat * (3.14159265358979323846 / 180.0),
                                                   wlon * (3.14159265358979323846 / 180.0),
                                                   (float)wyear);
        }
        if (azd >= 0) {
            ins_set_auto_zupt_disable(&ins, azd ? true : false);
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
    n_invalid = _cnt(diag, "n_invalid_input")
    n_dw = _cnt(diag, "n_downweighted")
    n_ff = _cnt(diag, "n_fuse_fail")
    n_az = _cnt(diag, "n_auto_zupt")
    n_pr = _cnt(diag, "n_predict")
    stationary = 1 if nav.auto_zupt_active() else 0
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
    line += " n_invalid=%d n_downweighted=%d n_fuse_fail=%d n_auto_zupt=%d n_predict=%d stationary=%d" % (
        n_invalid, n_dw, n_ff, n_az, n_pr, stationary
    )
    print(line)

header1 = sys.stdin.readline()
if not header1:
    raise SystemExit("missing header1")
parts = header1.split()
if len(parts) != 9:
    raise SystemExit("header1 fields")
ox, oy, oz = [float(x) for x in parts[0:3]]
mag_delay_ms = int(parts[3])
auto_zupt_disable = int(parts[4])
baro_height_disable = int(parts[5])
mag_n = (float(parts[6]), float(parts[7]), float(parts[8]))
header2 = sys.stdin.readline()
if not header2:
    raise SystemExit("missing header2")
h2 = header2.split()
if len(h2) != 3:
    raise SystemExit("header2 fields")
lat_deg, lon_deg, h_m = [float(x) for x in h2[0:3]]

cfg_kw = dict(
    auto_init=True,
    lat_rad=math.radians(lat_deg),
    lon_rad=math.radians(lon_deg),
    h_m=h_m,
    magnetometer_min_delay_ms=mag_delay_ms,
    auto_zupt_disable=bool(auto_zupt_disable),
    baro_height_disable=bool(baro_height_disable),
    magnetic_n=mag_n,
)
try:
    nav = Ins(Config(**cfg_kw))
except ValueError as exc:
    print("INIT rc=-1")
    print("SNAP t_us=0 ready=0 pos=0 vel=0 rpy=0 ned=0 bacc=0 bgyr=0 "
          "ecef=- nedpos=- velned=- att=- attstd=- biasacc=- biasgyr=- "
          "n_invalid=0 n_downweighted=0 n_fuse_fail=0 n_auto_zupt=0 stationary=0")
    raise SystemExit(0) from exc

print("INIT rc=0")
_ = (ox, oy, oz)

for raw in sys.stdin:
    if not raw.strip() or raw.startswith("#"):
        continue
    if not raw.startswith("E "):
        raise SystemExit("epoch tag")
    tok = raw.split()
    if len(tok) != 56:
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
    lp = int(tok[28])
    local = (float(tok[29]), float(tok[30]), float(tok[31]))
    lstd = (float(tok[32]), float(tok[33]), float(tok[34]))
    mg = int(tok[35])
    mag = (float(tok[36]), float(tok[37]), float(tok[38]))
    mag_var = (float(tok[39]), float(tok[40]), float(tok[41]))
    yw = int(tok[42])
    yaw_rad = float(tok[43])
    ystd = float(tok[44])
    sp = int(tok[45])
    speed = float(tok[46])
    br = int(tok[47])
    pa = float(tok[48])
    zupt = int(tok[49])
    zaru = int(tok[50])
    wmm = int(tok[51])
    wlat, wlon, wyear = float(tok[52]), float(tok[53]), float(tok[54])
    azd = int(tok[55])
    nav.imu(t_us, dt, acc, gyr)
    if gp:
        var = (std[0] * std[0], std[1] * std[1], std[2] * std[2])
        nav.gnss_pos(ecef, var)
    if gv:
        varv = (vstd[0] * vstd[0], vstd[1] * vstd[1], vstd[2] * vstd[2])
        nav.gnss_vel(vel, varv)
    if lever != (0.0, 0.0, 0.0):
        nav.gnss_leverarm(lever)
    if lp:
        lvar = (lstd[0] * lstd[0], lstd[1] * lstd[1], lstd[2] * lstd[2])
        nav.local_pos(local, lvar)
    if mg:
        nav.mag(mag, mag_var)
    if yw:
        nav.yaw(yaw_rad, ystd)
    if sp:
        nav.speed(speed)
    if br:
        nav.baro(pa)
    if zupt:
        nav.zupt(True)
    if zaru:
        nav.zaru(True)
    if wmm:
        nav.set_magnetic_model(math.radians(wlat), math.radians(wlon), wyear)
    nav.update()
    emit(nav, t_us)
"""


@dataclass
class AidingEpoch:
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
    local_ned: tuple[float, float, float] | None = None
    local_std: tuple[float, float, float] | None = None
    mag: tuple[float, float, float] | None = None
    mag_var: tuple[float, float, float] | None = None
    yaw_rad: float | None = None
    yaw_std: float | None = None
    speed_mps: float | None = None
    baro_pa: float | None = None
    zupt: bool = False
    zaru: bool = False
    arm_wmm: tuple[float, float, float] | None = None
    auto_zupt_disable: int | None = None


@dataclass
class AidingScenario:
    origin_ecef: tuple[float, float, float]
    lat_deg: float
    lon_deg: float
    h_m: float
    epochs: list[AidingEpoch] = field(default_factory=list)
    mag_min_delay_ms: int = 0
    auto_zupt_disable: bool = False
    baro_height_disable: bool = False
    magnetic_n: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class AidingSnapshot:
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
    n_invalid: int
    n_downweighted: int
    n_fuse_fail: int
    n_auto_zupt: int
    stationary: bool
    n_predict: int = -1


@dataclass
class AidingRun:
    init_ok: bool
    snaps: list[AidingSnapshot]

    def last(self) -> AidingSnapshot:
        if not self.snaps:
            raise HarnessError("run produced no snapshots")
        return self.snaps[-1]

    def first_ready(self) -> AidingSnapshot | None:
        for snap in self.snaps:
            if snap.ready:
                return snap
        return None

    def at_or_after(self, t_us: int) -> AidingSnapshot:
        for snap in self.snaps:
            if snap.t_us >= t_us and snap.pos_ok:
                return snap
        raise HarnessError(f"no initialized snapshot at or after t={t_us}")

    def first_stationary_after(self, t_us: int) -> AidingSnapshot:
        """First initialized stationary snapshot at or after *t_us*.

        Used for the after-dwell auto-ZUPT arm: the public diagnostic after
        the variance window, not a handful of IMU samples. A missing
        diagnostic is a failed observation, not an absent flag.
        """
        for snap in self.snaps:
            if snap.t_us < t_us:
                continue
            if not (snap.pos_ok and snap.vel_ok):
                continue
            if snap.vel_ned is None:
                raise HarnessError(
                    f"snapshot t={snap.t_us} marked vel_ok but velocity is missing"
                )
            if snap.stationary:
                return snap
        raise HarnessError(
            f"no stationary initialized snapshot at or after t={t_us}"
        )


def ned_field_from_independent_wmm(
    lat_deg: float, lon_deg: float, year: float
) -> tuple[float, float, float]:
    """D/I/F from the sealed NOAA harmonic → NED field (µT). Raises on failure."""
    decl_deg, incl_deg, f_ut = independent_wmm(lat_deg, lon_deg, year)
    incl = math.radians(incl_deg)
    decl = math.radians(decl_deg)
    horiz = f_ut * math.cos(incl)
    bn = horiz * math.cos(decl)
    be = horiz * math.sin(decl)
    bd = f_ut * math.sin(incl)
    if not all(math.isfinite(v) for v in (bn, be, bd)):
        raise HarnessError(f"WMM NED field is not finite at {lat_deg},{lon_deg}")
    return bn, be, bd


def magnetic_north_ned(lat_deg: float, lon_deg: float, year: float) -> tuple[float, float, float]:
    """Same total/inclination as the site WMM, but declination stripped (magnetic north)."""
    bn, be, bd = ned_field_from_independent_wmm(lat_deg, lon_deg, year)
    horiz = math.hypot(bn, be)
    if horiz < 1.0e-3:
        raise HarnessError(f"horizontal field too small to form magnetic north at {lat_deg},{lon_deg}")
    return horiz, 0.0, bd


def body_mag_for_yaw(
    roll: float,
    pitch: float,
    yaw: float,
    mag_ned: Sequence[float],
) -> tuple[float, float, float]:
    """Independent ZYX: NED field rotated into body. Raises if the result is not finite."""
    if len(mag_ned) != 3:
        raise HarnessError("NED field must have 3 components")
    q = hamilton_zyx_quaternion(roll, pitch, yaw)
    w, x, y, z = q
    r00 = 1.0 - 2.0 * (y * y + z * z)
    r01 = 2.0 * (x * y - w * z)
    r02 = 2.0 * (x * z + w * y)
    r10 = 2.0 * (x * y + w * z)
    r11 = 1.0 - 2.0 * (x * x + z * z)
    r12 = 2.0 * (y * z - w * x)
    r20 = 2.0 * (x * z - w * y)
    r21 = 2.0 * (y * z + w * x)
    r22 = 1.0 - 2.0 * (x * x + y * y)
    n0, n1, n2 = float(mag_ned[0]), float(mag_ned[1]), float(mag_ned[2])
    bx = r00 * n0 + r10 * n1 + r20 * n2
    by = r01 * n0 + r11 * n1 + r21 * n2
    bz = r02 * n0 + r12 * n1 + r22 * n2
    if not all(math.isfinite(v) for v in (bx, by, bz)):
        raise HarnessError("body magnetometer sample is not finite")
    return bx, by, bz


def isa_pressure_pa(height_m: float) -> float:
    """International Standard Atmosphere static pressure from height (input generator)."""
    frac = 1.0 - height_m / ISA_SCALE_M
    if frac <= 0.0:
        raise HarnessError(f"ISA height {height_m} is above the tropopause model")
    pressure = ISA_P0_PA * (frac ** ISA_EXP)
    if not math.isfinite(pressure) or pressure <= 0.0:
        raise HarnessError(f"ISA pressure is not a positive finite value for h={height_m}")
    return pressure


def angle_diff_rad(a: float, b: float) -> float:
    return math.radians(angle_diff_deg(math.degrees(a), math.degrees(b)))


def horiz_speed(vel: Sequence[float]) -> float:
    if len(vel) < 2:
        raise HarnessError("velocity must have at least north/east")
    s = math.hypot(float(vel[0]), float(vel[1]))
    if not math.isfinite(s):
        raise HarnessError("horizontal speed is not finite")
    return s


def with_leading_standstill_flags(
    epochs: list[AidingEpoch],
    *,
    after_t_us: int,
    count: int,
    zupt: bool = False,
    zaru: bool = False,
) -> list[AidingEpoch]:
    """Keep standstill flags on only the first *count* epochs after *after_t_us*."""
    if count < 0:
        raise HarnessError("leading flag count must be non-negative")
    out: list[AidingEpoch] = []
    seen = 0
    for e in epochs:
        if e.t_us <= after_t_us:
            out.append(e)
            continue
        seen += 1
        on = seen <= count
        out.append(replace(e, zupt=bool(zupt and on), zaru=bool(zaru and on)))
    return out


def runtime_tracker_ned() -> tuple[float, float, float]:
    """Runtime centimetre-scale NED well away from the named (1.5, 0, 0) sample."""
    u = runtime_uuid_int()
    north = 3.6 + (u % 160) / 100.0
    east = 1.1 + ((u // 160) % 140) / 100.0
    down = ((u // 22400) % 21) / 100.0 - 0.1
    print(f"runtime tracker n={north} e={east} d={down}", flush=True)
    return north, east, down


def runtime_heading_rad() -> float:
    u = runtime_uuid_int()
    yaw = 0.35 + (u % 220) / 100.0
    if abs(abs(yaw) - math.pi) < 0.15:
        yaw = 1.1
    print(f"runtime heading rad={yaw}", flush=True)
    return yaw


def runtime_wmm_site() -> tuple[float, float, float]:
    """Runtime mid-latitude site with a usable declination, not the tutorial city."""
    for _ in range(24):
        lat, lon, h = runtime_site()
        decl, incl, f_ut = independent_wmm(lat, lon, WMM_YEAR)
        horiz = f_ut * abs(math.cos(math.radians(incl)))
        if abs(decl) >= 3.0 and horiz >= 8.0 and abs(lat) < 60.0:
            print(f"runtime WMM site lat={lat} lon={lon} D={decl} I={incl} F={f_ut}", flush=True)
            return lat, lon, h
    raise HarnessError("could not find a mid-latitude site with usable declination")


def runtime_near_vertical_site() -> tuple[float, float, float]:
    """High-latitude site whose independent WMM inclination is near vertical."""
    u = runtime_uuid_int()
    lat = 88.2 + (u % 12) / 10.0
    lon = -40.0 + ((u // 12) % 80)
    h = 40.0
    decl, incl, f_ut = independent_wmm(lat, lon, WMM_YEAR)
    print(f"near-vertical site lat={lat} lon={lon} D={decl} I={incl} F={f_ut}", flush=True)
    if abs(incl) < 70.0:
        raise HarnessError(f"high-latitude site inclination {incl} deg is not near vertical")
    return lat, lon, h


def encode_aiding(scen: AidingScenario) -> str:
    ox, oy, oz = scen.origin_ecef
    mn = scen.magnetic_n
    lines = [
        f"{ox:.17g} {oy:.17g} {oz:.17g} {scen.mag_min_delay_ms} "
        f"{int(scen.auto_zupt_disable)} {int(scen.baro_height_disable)} "
        f"{mn[0]:.17g} {mn[1]:.17g} {mn[2]:.17g}",
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
        mg = 1 if e.mag is not None else 0
        mag = e.mag if e.mag is not None else (0.0, 0.0, 0.0)
        mag_var = e.mag_var if e.mag_var is not None else (0.0, 0.0, 0.0)
        yw = 1 if e.yaw_rad is not None else 0
        yaw = e.yaw_rad if e.yaw_rad is not None else 0.0
        ystd = e.yaw_std if e.yaw_std is not None else 0.0
        sp = 1 if e.speed_mps is not None else 0
        speed = e.speed_mps if e.speed_mps is not None else 0.0
        br = 1 if e.baro_pa is not None else 0
        pa = e.baro_pa if e.baro_pa is not None else 0.0
        wmm = 1 if e.arm_wmm is not None else 0
        wlat, wlon, wyear = e.arm_wmm if e.arm_wmm is not None else (0.0, 0.0, 0.0)
        azd = -1 if e.auto_zupt_disable is None else int(e.auto_zupt_disable)
        lines.append(
            "E %d %.17g %.17g %.17g %.17g %.17g %.17g %.17g %d %d %d "
            "%.17g %.17g %.17g %.17g %.17g %.17g %d %.17g %.17g %.17g "
            "%.17g %.17g %.17g %.17g %.17g %.17g %d %.17g %.17g %.17g "
            "%.17g %.17g %.17g %d %.17g %.17g %.17g %.17g %.17g %.17g "
            "%d %.17g %.17g %d %.17g %d %.17g %d %d %d %.17g %.17g %.17g %d"
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
                lp,
                local[0],
                local[1],
                local[2],
                lstd[0],
                lstd[1],
                lstd[2],
                mg,
                mag[0],
                mag[1],
                mag[2],
                mag_var[0],
                mag_var[1],
                mag_var[2],
                yw,
                yaw,
                ystd,
                sp,
                speed,
                br,
                pa,
                int(e.zupt),
                int(e.zaru),
                wmm,
                wlat,
                wlon,
                wyear,
                azd,
            )
        )
    return "\n".join(lines) + "\n"


def parse_aiding_snapshot(line: str) -> AidingSnapshot:
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
    n_invalid = _parse_int(fields, "n_invalid")
    n_dw = _parse_int(fields, "n_downweighted")
    n_ff = _parse_int(fields, "n_fuse_fail")
    n_az = _parse_int(fields, "n_auto_zupt")
    n_pr = _parse_int(fields, "n_predict") if "n_predict" in fields else -1
    stationary = _parse_flag(fields, "stationary")
    if n_invalid < 0 or n_dw < 0 or n_ff < 0 or n_az < 0:
        note_product_issue("F03", f"diagnostic counters missing or negative: {line}")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F03', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F03', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F03', f"ins_get_diag returned NULL for a live instance: {line}")
    return AidingSnapshot(
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
        n_invalid=n_invalid,
        n_downweighted=n_dw,
        n_fuse_fail=n_ff,
        n_auto_zupt=n_az,
        stationary=stationary,
        n_predict=n_pr,
    )


def parse_aiding_run(text: str) -> AidingRun:
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
    snaps = [parse_aiding_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    return AidingRun(init_ok=(rc == 0), snaps=snaps)


def _run_aiding(kind: str, scen: AidingScenario) -> AidingRun:
    payload = encode_aiding(scen)
    if kind == "c":
        result = invoke(_C_PROBE, stdin=payload, timeout=LONG_TIMEOUT)
    elif kind == "py":
        ident = product_identity()
        assert ident is not None, "python package directory was not found after make pylib"
        assert ident.library is not None, "shared library is missing after make pylib"
        package = ident.package_name
        assert package.isidentifier(), f"discovered package name is not importable: {package!r}"
        result = run_python(
            _PY_PROBE.replace("__PKG__", package),
            stdin=payload,
            timeout=LONG_TIMEOUT,
        )
    else:
        raise HarnessError(f"unknown probe kind {kind!r}")
    text = require_probe_success(result)
    run = parse_aiding_run(text)
    print(
        f"{kind} init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_ready={run.last().ready if run.snaps else None}",
        flush=True,
    )
    return run


def c_aiding_run(scen: AidingScenario) -> AidingRun:
    return _run_aiding("c", scen)


def py_aiding_run(scen: AidingScenario) -> AidingRun:
    return _run_aiding("py", scen)


def require_ready_solution(snap: AidingSnapshot, what: str) -> None:
    if not snap.ready:
        raise AssertionError(f"{what}: expected ready at t={snap.t_us}")
    if not (snap.pos_ok and snap.vel_ok and snap.rpy_ok and snap.ned_ok):
        raise AssertionError(
            f"{what}: accessors not all successful pos={snap.pos_ok} "
            f"vel={snap.vel_ok} rpy={snap.rpy_ok} ned={snap.ned_ok}"
        )
    if snap.ecef is None or snap.ned is None or snap.vel_ned is None or snap.rpy is None:
        raise AssertionError(f"{what}: successful accessors returned no vectors")


def aiding_site(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    epochs: list[AidingEpoch],
    **kwargs,
) -> AidingScenario:
    origin = kwargs.pop("origin_ecef", None)
    if origin is None:
        origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    return AidingScenario(
        origin_ecef=origin,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        h_m=h_m,
        epochs=epochs,
        **kwargs,
    )


def _epoch(
    t_us: int,
    *,
    dt_sec: float = DT_SEC,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    **kwargs,
) -> AidingEpoch:
    return AidingEpoch(
        t_us=t_us,
        dt_sec=dt_sec,
        acc=(float(acc[0]), float(acc[1]), float(acc[2])),
        gyr=(float(gyr[0]), float(gyr[1]), float(gyr[2])),
        **kwargs,
    )


def local_stream(
    tracker: Sequence[float],
    *,
    duration_s: float = HAPPY_DURATION_S,
    imu_hz: int = IMU_HZ,
    local_hz: int = LOCAL_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    local_std: Sequence[float] = (CM_STD_M, CM_STD_M, CM_STD_M),
    baro_pa: float | None = None,
    tracker_at=None,
    **kwargs,
) -> list[AidingEpoch]:
    """100 Hz IMU + 10 Hz local NED. Optional per-epoch tracker override."""
    if imu_hz <= 0 or local_hz <= 0:
        raise HarnessError("rates must be positive")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    every = imu_hz // local_hz
    if every <= 0:
        raise HarnessError("local rate cannot exceed IMU rate")
    epochs: list[AidingEpoch] = []
    for k in range(1, n + 1):
        t_us = int(round(k * dt * 1e6))
        has_local = k % every == 0
        pos = None
        std = None
        if has_local:
            pos = tuple(tracker_at(t_us, k)) if tracker_at is not None else tuple(tracker)
            std = tuple(local_std)
        epochs.append(
            _epoch(
                t_us,
                dt_sec=dt,
                acc=acc,
                gyr=gyr,
                local_ned=pos,
                local_std=std,
                baro_pa=baro_pa if has_local else None,
                **kwargs,
            )
        )
    return epochs


def gnss_stream(
    gnss_ecef: Sequence[float],
    *,
    duration_s: float = HAPPY_DURATION_S,
    imu_hz: int = IMU_HZ,
    gnss_hz: int = GNSS_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_std: Sequence[float] = GNSS_STD_M,
    gnss_vel: Sequence[float] | None = None,
    gnss_vel_std: Sequence[float] | None = None,
    baro_pa: float | None = None,
    mag: Sequence[float] | None = None,
    mag_var: Sequence[float] | None = None,
    **kwargs,
) -> list[AidingEpoch]:
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    every = imu_hz // gnss_hz
    if every <= 0:
        raise HarnessError("GNSS rate cannot exceed IMU rate")
    epochs: list[AidingEpoch] = []
    for k in range(1, n + 1):
        t_us = int(round(k * dt * 1e6))
        has_gnss = k % every == 0
        epochs.append(
            _epoch(
                t_us,
                dt_sec=dt,
                acc=acc,
                gyr=gyr,
                gnss_ecef=tuple(gnss_ecef) if has_gnss else None,
                gnss_std=tuple(gnss_std) if has_gnss else None,
                gnss_vel=tuple(gnss_vel) if (has_gnss and gnss_vel is not None) else None,
                gnss_vel_std=tuple(gnss_vel_std) if (has_gnss and gnss_vel is not None) else None,
                mag=tuple(mag) if mag is not None else None,
                mag_var=tuple(mag_var) if (mag is not None and mag_var is not None) else None,
                baro_pa=baro_pa if (has_gnss and baro_pa is not None) else None,
                **kwargs,
            )
        )
    return epochs


def extend_gnss_constant_vel(
    epochs: list[AidingEpoch],
    origin: Sequence[float],
    vel_ned: Sequence[float],
    *,
    duration_s: float,
    start_ned: Sequence[float] = (0.0, 0.0, 0.0),
    imu_hz: int = IMU_HZ,
    gnss_hz: int = LOCAL_HZ,
    gnss_std: Sequence[float] = GNSS_STD_M,
    gnss_vel_std: Sequence[float] = (1.5, 1.5, 1.5),
) -> list[AidingEpoch]:
    """Append GNSS that walks at constant NED velocity from start_ned."""
    if not epochs:
        raise HarnessError("extend_gnss_constant_vel needs a preceding stream")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    every = imu_hz // gnss_hz
    if every <= 0:
        raise HarnessError("GNSS rate cannot exceed IMU rate")
    vn, ve, vd = float(vel_ned[0]), float(vel_ned[1]), float(vel_ned[2])
    n0, e0, d0 = float(start_ned[0]), float(start_ned[1]), float(start_ned[2])
    t0 = epochs[-1].t_us
    out = list(epochs)
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        t_s = i * dt
        has_gnss = i % every == 0
        ecef = None
        std = None
        vel = None
        vstd = None
        if has_gnss:
            ecef = ecef_plus_ned(origin, n0 + vn * t_s, e0 + ve * t_s, d0 + vd * t_s)
            std = tuple(gnss_std)
            vel = (vn, ve, vd)
            vstd = tuple(gnss_vel_std)
        out.append(
            _epoch(
                t_us,
                dt_sec=dt,
                gnss_ecef=ecef,
                gnss_std=std,
                gnss_vel=vel,
                gnss_vel_std=vstd,
            )
        )
    return out


def extend_epochs(
    epochs: list[AidingEpoch],
    *,
    duration_s: float,
    imu_hz: int = IMU_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    acc_valid: bool = True,
    gyr_valid: bool = True,
    local_ned: Sequence[float] | None = None,
    local_std: Sequence[float] | None = None,
    local_hz: int = LOCAL_HZ,
    gnss_ecef: Sequence[float] | None = None,
    gnss_std: Sequence[float] | None = None,
    gnss_vel: Sequence[float] | None = None,
    gnss_vel_std: Sequence[float] | None = None,
    gnss_hz: int = GNSS_HZ,
    mag: Sequence[float] | None = None,
    mag_var: Sequence[float] | None = None,
    baro_pa: float | None = None,
    baro_hz: int = LOCAL_HZ,
    yaw_rad: float | None = None,
    yaw_std: float | None = None,
    speed_mps: float | None = None,
    zupt: bool = False,
    zaru: bool = False,
    arm_wmm: tuple[float, float, float] | None = None,
    auto_zupt_disable: int | None = None,
) -> list[AidingEpoch]:
    """Append *duration_s* of IMU, attaching optional aiding on their own rates.

    Barometer / local / GNSS flags are set only on those cadence slots so a
    latched sample is not re-fused every IMU epoch.
    """
    if not epochs:
        raise HarnessError("extend needs a preceding stream")
    if imu_hz <= 0:
        raise HarnessError("IMU rate must be positive")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    t0 = epochs[-1].t_us
    out = list(epochs)
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        has_local = local_ned is not None and (i % max(imu_hz // local_hz, 1) == 0)
        has_gnss = gnss_ecef is not None and (i % max(imu_hz // gnss_hz, 1) == 0)
        has_baro = baro_pa is not None and (i % max(imu_hz // baro_hz, 1) == 0)
        out.append(
            _epoch(
                t_us,
                dt_sec=dt,
                acc=acc,
                gyr=gyr,
                acc_valid=acc_valid,
                gyr_valid=gyr_valid,
                gnss_ecef=tuple(gnss_ecef) if has_gnss else None,
                gnss_std=tuple(gnss_std) if has_gnss else None,
                gnss_vel=tuple(gnss_vel) if (has_gnss and gnss_vel is not None) else None,
                gnss_vel_std=tuple(gnss_vel_std)
                if (has_gnss and gnss_vel is not None)
                else None,
                local_ned=tuple(local_ned) if has_local else None,
                local_std=tuple(local_std) if has_local else None,
                mag=tuple(mag) if mag is not None else None,
                mag_var=tuple(mag_var) if (mag is not None and mag_var is not None) else None,
                baro_pa=baro_pa if has_baro else None,
                yaw_rad=yaw_rad,
                yaw_std=yaw_std if yaw_rad is not None else None,
                speed_mps=speed_mps,
                zupt=zupt,
                zaru=zaru,
                arm_wmm=arm_wmm if i == 1 else None,
                auto_zupt_disable=auto_zupt_disable if i == 1 else None,
            )
        )
    return out


def lerp3(
    a: Sequence[float], b: Sequence[float], frac: float
) -> tuple[float, float, float]:
    if not 0.0 <= frac <= 1.0:
        raise HarnessError(f"lerp fraction {frac} is not in [0, 1]")
    return (
        float(a[0]) + (float(b[0]) - float(a[0])) * frac,
        float(a[1]) + (float(b[1]) - float(a[1])) * frac,
        float(a[2]) + (float(b[2]) - float(a[2])) * frac,
    )


def extend_local_ramp(
    epochs: list[AidingEpoch],
    start: Sequence[float],
    end: Sequence[float],
    *,
    duration_s: float,
    local_std: Sequence[float] = (0.03, 0.03, 0.03),
    imu_hz: int = IMU_HZ,
    local_hz: int = LOCAL_HZ,
) -> list[AidingEpoch]:
    """Move a centimetre tracker from start to end in small steps (not a glitch)."""
    if not epochs:
        raise HarnessError("extend_local_ramp needs a preceding stream")
    if imu_hz <= 0 or local_hz <= 0:
        raise HarnessError("rates must be positive")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    every = imu_hz // local_hz
    if every <= 0:
        raise HarnessError("local rate cannot exceed IMU rate")
    n_local = max(n // every, 1)
    t0 = epochs[-1].t_us
    out = list(epochs)
    k_local = 0
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        has_local = i % every == 0
        pos = None
        std = None
        if has_local:
            k_local += 1
            frac = k_local / float(n_local)
            pos = lerp3(start, end, frac)
            std = tuple(local_std)
        out.append(_epoch(t_us, dt_sec=dt, local_ned=pos, local_std=std))
    return out


def extend_wobble(
    epochs: list[AidingEpoch],
    *,
    duration_s: float,
    amp_rps: float = 0.45,
    freq_hz: float = 3.5,
    imu_hz: int = IMU_HZ,
) -> list[AidingEpoch]:
    """Append a high-variance yaw-rate IMU so the stillness variance window is dirty."""
    if not epochs:
        raise HarnessError("extend_wobble needs a preceding stream")
    if imu_hz <= 0 or freq_hz <= 0.0:
        raise HarnessError("rates must be positive")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    t0 = epochs[-1].t_us
    out = list(epochs)
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        gyr_z = amp_rps * math.sin(2.0 * math.pi * freq_hz * (i * dt))
        out.append(_epoch(t_us, dt_sec=dt, gyr=(0.0, 0.0, gyr_z)))
    return out


def still_level_acc(pitch_rad: float = 0.0, roll: float = 0.0) -> tuple[float, float, float]:
    """Specific force of a still body at the given Tait-Bryan attitude."""
    q = hamilton_zyx_quaternion(roll, pitch_rad, 0.0)
    w, x, y, z = q
    r02 = 2.0 * (x * z + w * y)
    r12 = 2.0 * (y * z - w * x)
    r22 = 1.0 - 2.0 * (x * x + y * y)
    fx = -G_MPS2 * r02
    fy = -G_MPS2 * r12
    fz = -G_MPS2 * r22
    if not all(math.isfinite(v) for v in (fx, fy, fz)):
        raise HarnessError("still-level specific force is not finite")
    return fx, fy, fz
