# feature: F05
"""Observation helpers for FP-05 quality gates, coasting, and re-acquisition.

C probes compile through the sealed harness. Python observations run in a
child interpreter. This module does not import the product in the pytest
process. Expected ECEF/NED come from the GNSS or tracker the test fed and
from independent WGS84 geometry, never from the library's own gate or
freeze internals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Sequence

from _harness import (
    HarnessError,
    importable_package_name,
    invoke,
    run_python,
    runtime_uuid_int,
    nonfinite_fields,
    note_product_issue,
)
from F01_helpers import hypot3, require_probe_success
from F02_helpers import (
    DT_SEC,
    GNSS_STD_M,
    HAPPY_DURATION_S,
    IMU_HZ,
    SPECIFIC_FORCE_LEVEL,
    _parse_flag,
    _parse_int,
    _parse_vec,
    ecef_from_llh_deg,
    ecef_plus_ned,
    ned_offset_from_two_ecef,
    runtime_gnss_step_m,
)
from F03_helpers import (
    CM_STD_M,
    LOCAL_HZ,
    TRACKER_NAMED_NED,
    YAW_STD_RAD,
    angle_diff_rad,
    isa_pressure_pa,
)

# Fixed inputs and tolerances for FP-05.
NAMED_10M_STD = (10.0, 10.0, 10.0)
ENTRY_POS_STD = GNSS_STD_M  # 2/2/2, inside 2 m / 3 m
BETWEEN_POS_STD = (4.0, 4.0, 4.0)  # worse than entry, better than exit
EXIT_POS_BAD = NAMED_10M_STD
UNDER_CAP_STD = (40.0, 40.0, 40.0)  # tens of metres, still below 120 m
# One non-positive diagonal: the F02-proven unfusable covariance.
UNFUSABLE_POS_STD = (0.0, 2.0, 2.0)
ENTRY_VEL_STD = (0.10, 0.10, 0.10)  # inside 0.25 / 0.30
VEL_H_BAD_STD = (1.00, 1.00, 0.10)  # horiz worse than 0.25, vert inside 0.30
VEL_V_BAD_STD = (0.10, 0.10, 1.00)  # vert worse than 0.30
EXIT_VEL_BAD_STD = (1.00, 1.00, 1.00)  # worse than 0.4 / 0.5
# Mid-cap velocity 1-sigma: worse than entry 0.25/0.30, still below 60 m/s.
UNDER_VEL_CAP_STD = (8.0, 8.0, 8.0)
ZERO_VEL = (0.0, 0.0, 0.0)
FEW_HZ = 4  # 250 ms > 100 ms rate limit, still several hertz
GNSS_50HZ = 50
OUTAGE_3S = 3.0
OUTAGE_7S = 7.0
FREEZE_11S = 11.0
EXIT_DWELL_S = 10.0
RAISED_ENTRY_M = 15.0
CAP_M = 120.0
CAP_VEL_MPS = 60.0
NORTH_ACCEL = 0.18  # body-x specific-force increment for a visible DR walk
YAW_RATE_RPS = 0.35
READY_PAD_S = HAPPY_DURATION_S
GATE_TIMEOUT = 120.0
OVER_CAP_STD = (200.0, 200.0, 200.0)

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
    /* The C INS publishes attitude 1-sigma only (ins_get_rpy_stddev).
       Position, velocity, and bias 1-sigma are published by the Python
       wrapper's stddev(); the C arm reports them as unpublished. */
    printf(" posstd=- velstd=- baccstd=- bgyrstd=- stdpub=0");
    {
        /* Raw return; the parser checks it against the published convention. */
        printf(" dr=%d", ins_deadreckoning_ms(f));
    }
    printf(" n_seen=%u n_used=%u n_rate=%u\n", d->n_gnss_seen, d->n_gnss_used,
           d->n_gnss_rate_limited);
}

int main(void)
{
    char line[8192];
    double ox = 0.0, oy = 0.0, oz = 0.0;
    int auto_init = 1, zupt_off = 1, unlimited = 0, dwell_off = 0, stop_off = 0;
    int ready_only = 0, baro_off = 0, chi2_off = 0;
    float fusion_h = 0.0f, fusion_v = 0.0f, fusion_hv = 0.0f, fusion_vv = 0.0f;
    float entry_h = 0.0f, entry_v = 0.0f, entry_hv = 0.0f, entry_vv = 0.0f;
    float exit_h = 0.0f, exit_v = 0.0f, exit_hv = 0.0f, exit_vv = 0.0f;
    float coast_sec = 0.0f, rpy0 = 0.0f, rpy1 = 0.0f, rpy2 = 0.0f;
    int pos_decimation = 0;
    double lat_deg = 0.0, lon_deg = 0.0, h_m = 0.0;
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("header1");
    }
    if (sscanf(line, "%lf %lf %lf %d %d %d %d %d %d %d %d", &ox, &oy, &oz, &auto_init,
               &zupt_off, &unlimited, &dwell_off, &stop_off, &ready_only,
               &baro_off, &chi2_off) != 11) {
        return fail_read("header1 fields");
    }
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("header2");
    }
    if (sscanf(line, "%f %f %f %f %f %f %f %f %f %f %f %f", &fusion_h, &fusion_v,
               &fusion_hv, &fusion_vv, &entry_h, &entry_v, &entry_hv, &entry_vv,
               &exit_h, &exit_v, &exit_hv, &exit_vv) != 12) {
        return fail_read("header2 fields");
    }
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("header3");
    }
    if (sscanf(line, "%f %d %f %f %f %lf %lf %lf", &coast_sec, &pos_decimation, &rpy0,
               &rpy1, &rpy2, &lat_deg, &lon_deg, &h_m) != 8) {
        return fail_read("header3 fields");
    }
    (void)lat_deg;
    (void)lon_deg;
    (void)h_m;

    ins_t ins = {0};
    ins_init_t init = {0};
    ins_options_t opt = {0};
    opt.auto_init = auto_init ? true : false;
    opt.auto_zupt_disable = zupt_off ? true : false;
    opt.allow_unlimited_deadreckoning = unlimited ? true : false;
    opt.gnss_init_dwell_disable = dwell_off ? true : false;
    opt.gnss_stop_disable = stop_off ? true : false;
    opt.auto_reacquire_disable = ready_only ? true : false;
    opt.baro_height_disable = baro_off ? true : false;
    opt.chi2_disable = chi2_off ? true : false;
    init.x_ecef[0] = ox;
    init.x_ecef[1] = oy;
    init.x_ecef[2] = oz;
    init.rpy_init_rad[0] = rpy0;
    init.rpy_init_rad[1] = rpy1;
    init.rpy_init_rad[2] = rpy2;
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
    if (entry_h > 0.0f) {
        opt.gnss_start_max_horizontal_pos_stddev_m = entry_h;
    }
    if (entry_v > 0.0f) {
        opt.gnss_start_max_vertical_pos_stddev_m = entry_v;
    }
    if (entry_hv > 0.0f) {
        opt.gnss_start_max_horizontal_vel_stddev_mps = entry_hv;
    }
    if (entry_vv > 0.0f) {
        opt.gnss_start_max_vertical_vel_stddev_mps = entry_vv;
    }
    if (exit_h > 0.0f) {
        opt.gnss_stop_max_horizontal_pos_stddev_m = exit_h;
    }
    if (exit_v > 0.0f) {
        opt.gnss_stop_max_vertical_pos_stddev_m = exit_v;
    }
    if (exit_hv > 0.0f) {
        opt.gnss_stop_max_horizontal_vel_stddev_mps = exit_hv;
    }
    if (exit_vv > 0.0f) {
        opt.gnss_stop_max_vertical_vel_stddev_mps = exit_vv;
    }
    if (coast_sec > 0.0f) {
        opt.max_deadreckoning_sec = coast_sec;
    }
    if (pos_decimation != 0) {
        opt.gnss_pos_decimation = pos_decimation;
    }

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
        int yw;
        double yaw_rad, ystd;
        int br;
        double pa;
        int broken_pos, broken_vel;
        if (sscanf(line,
                   "E %lld %lf %lf %lf %lf %lf %lf %lf %d %d %d %lf %lf %lf %lf "
                   "%lf %lf %d %lf %lf %lf %lf %lf %lf %lf %lf %lf %d %lf %lf "
                   "%lf %lf %lf %lf %d %lf %lf %d %lf %d %d",
                   &t_us, &dt, &ax, &ay, &az, &gx, &gy, &gz, &acc_v, &gyr_v, &gp,
                   &e0, &e1, &e2, &sn, &se, &sd, &gv, &vn, &ve, &vd, &vsn, &vse,
                   &vsd, &lx, &ly, &lz, &lp, &ln, &le, &ld, &lsn, &lse, &lsd, &yw,
                   &yaw_rad, &ystd, &br, &pa, &broken_pos, &broken_vel) != 41) {
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
            if (broken_pos) {
                m.gnss_pos.Qll_ned[0] = -1.0f;
                m.gnss_pos.Qll_ned[4] = -1.0f;
                m.gnss_pos.Qll_ned[8] = -1.0f;
            } else {
                m.gnss_pos.Qll_ned[0] = (float)(sn * sn);
                m.gnss_pos.Qll_ned[4] = (float)(se * se);
                m.gnss_pos.Qll_ned[8] = (float)(sd * sd);
            }
        }
        if (gv) {
            m.gnss_vel.is_valid = true;
            m.gnss_vel.vel_ned[0] = (float)vn;
            m.gnss_vel.vel_ned[1] = (float)ve;
            m.gnss_vel.vel_ned[2] = (float)vd;
            if (broken_vel) {
                m.gnss_vel.Qll_ned[0] = -1.0f;
                m.gnss_vel.Qll_ned[4] = -1.0f;
                m.gnss_vel.Qll_ned[8] = -1.0f;
            } else {
                m.gnss_vel.Qll_ned[0] = (float)(vsn * vsn);
                m.gnss_vel.Qll_ned[4] = (float)(vse * vse);
                m.gnss_vel.Qll_ned[8] = (float)(vsd * vsd);
            }
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
        if (yw) {
            m.yaw.is_valid = true;
            m.yaw.yaw_rad = (float)yaw_rad;
            m.yaw.stddev_rad = (float)ystd;
        }
        if (br) {
            m.baro.is_valid = true;
            m.baro.pressure_pa = (float)pa;
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
    pos_std = vel_std = bacc_std = bgyr_std = None
    if sd is not None:
        rpy_std = tuple(sd["rpy"])
        pos_std = tuple(sd["pos_ned"])
        vel_std = tuple(sd["vel_ned"])
        bacc_std = tuple(sd["acc_bias"])
        bgyr_std = tuple(sd["gyr_bias"])
    def fmt(ok, vec):
        if not ok:
            return "-"
        return "%.17g,%.17g,%.17g" % vec
    n_seen = _cnt(diag, "n_gnss_seen")
    n_used = _cnt(diag, "n_gnss_used")
    # used > seen prints a negative skip count; the parser records it.
    skipped = n_seen - n_used
    dr = nav.deadreckoning_ms()
    line = (
        "SNAP t_us=%d ready=%d pos=%d vel=%d rpy=%d ned=%d bacc=%d bgyr=%d"
        % (t_us, ready, pos, vel_ok, rpy_ok, ned_ok, bacc_ok, bgyr_ok)
    )
    line += " ecef=" + (fmt(pos, tuple(ecef)) if pos else "-")
    line += " nedpos=" + (fmt(ned_ok, tuple(ned)) if ned_ok else "-")
    line += " velned=" + (fmt(vel_ok, tuple(vel)) if vel_ok else "-")
    line += " att=" + (fmt(rpy_ok, tuple(rpy)) if rpy_ok else "-")
    line += " attstd=" + (fmt(rpy_std is not None, rpy_std) if rpy_std is not None else "-")
    line += " biasacc=" + (fmt(bacc_ok, tuple(bacc)) if bacc_ok else "-")
    line += " biasgyr=" + (fmt(bgyr_ok, tuple(bgyr)) if bgyr_ok else "-")
    line += " posstd=" + (fmt(pos_std is not None, pos_std) if pos_std is not None else "-")
    line += " velstd=" + (fmt(vel_std is not None, vel_std) if vel_std is not None else "-")
    line += " baccstd=" + (fmt(bacc_std is not None, bacc_std) if bacc_std is not None else "-")
    line += " bgyrstd=" + (fmt(bgyr_std is not None, bgyr_std) if bgyr_std is not None else "-")
    if isinstance(dr, int) and not isinstance(dr, bool):
        line += " dr=%d" % dr
    else:
        line += " dr=?"  # the reader returned something other than an int
    line += " n_seen=%d n_used=%d n_rate=%d" % (n_seen, n_used, skipped)
    print(line)

header1 = sys.stdin.readline()
if not header1:
    raise SystemExit("missing header1")
p1 = header1.split()
if len(p1) != 11:
    raise SystemExit("header1 fields")
ox, oy, oz = [float(x) for x in p1[0:3]]
auto_init, zupt_off, unlimited, dwell_off, stop_off, ready_only, baro_off, chi2_off = [
    int(x) for x in p1[3:11]
]
header2 = sys.stdin.readline()
if not header2:
    raise SystemExit("missing header2")
p2 = header2.split()
if len(p2) != 12:
    raise SystemExit("header2 fields")
fusion_h, fusion_v, fusion_hv, fusion_vv = [float(x) for x in p2[0:4]]
entry_h, entry_v, entry_hv, entry_vv = [float(x) for x in p2[4:8]]
exit_h, exit_v, exit_hv, exit_vv = [float(x) for x in p2[8:12]]
header3 = sys.stdin.readline()
if not header3:
    raise SystemExit("missing header3")
p3 = header3.split()
if len(p3) != 8:
    raise SystemExit("header3 fields")
coast_sec = float(p3[0])
pos_decimation = int(p3[1])
rpy0, rpy1, rpy2 = [float(x) for x in p3[2:5]]
lat_deg, lon_deg, h_m = [float(x) for x in p3[5:8]]

cfg_kw = dict(
    auto_init=bool(auto_init),
    auto_zupt_disable=bool(zupt_off),
    allow_unlimited_deadreckoning=bool(unlimited),
    gnss_init_dwell_disable=bool(dwell_off),
    gnss_stop_disable=bool(stop_off),
    baro_height_disable=bool(baro_off),
    chi2_disable=bool(chi2_off),
    lat_rad=math.radians(lat_deg),
    lon_rad=math.radians(lon_deg),
    h_m=h_m,
    gnss_max_horizontal_pos_stddev_m=fusion_h,
    gnss_max_vertical_pos_stddev_m=fusion_v,
    gnss_max_horizontal_vel_stddev_mps=fusion_hv,
    gnss_max_vertical_vel_stddev_mps=fusion_vv,
    gnss_start_max_horizontal_pos_stddev_m=entry_h,
    gnss_start_max_vertical_pos_stddev_m=entry_v,
    gnss_start_max_horizontal_vel_stddev_mps=entry_hv,
    gnss_start_max_vertical_vel_stddev_mps=entry_vv,
    gnss_stop_max_horizontal_pos_stddev_m=exit_h,
    gnss_stop_max_vertical_pos_stddev_m=exit_v,
    gnss_stop_max_horizontal_vel_stddev_mps=exit_hv,
    gnss_stop_max_vertical_vel_stddev_mps=exit_vv,
    max_deadreckoning_sec=coast_sec,
    rpy_init_rad=(rpy0, rpy1, rpy2),
)
# 0 in the scenario header means the knob was omitted (C leaves the
# option block at zero). Passing 0 here would still *set* the field and
# would not exercise the default-off path.
if pos_decimation != 0:
    cfg_kw["gnss_pos_decimation"] = pos_decimation
_ = ready_only  # C-only switch; Python Config does not expose it
_ = (ox, oy, oz)

try:
    nav = Ins(Config(**cfg_kw))
except ValueError as exc:
    print("INIT rc=-1")
    print("SNAP t_us=0 ready=0 pos=0 vel=0 rpy=0 ned=0 bacc=0 bgyr=0 "
          "ecef=- nedpos=- velned=- att=- attstd=- biasacc=- biasgyr=- "
          "posstd=- velstd=- baccstd=- bgyrstd=- dr=- "
          "n_seen=0 n_used=0 n_rate=0")
    raise SystemExit(0) from exc

print("INIT rc=0")

for raw in sys.stdin:
    if not raw.strip() or raw.startswith("#"):
        continue
    if not raw.startswith("E "):
        raise SystemExit("epoch tag")
    tok = raw.split()
    if len(tok) != 42:
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
    yw = int(tok[35])
    yaw_rad = float(tok[36])
    ystd = float(tok[37])
    br = int(tok[38])
    pa = float(tok[39])
    broken_pos = int(tok[40])
    broken_vel = int(tok[41])
    nav.imu(t_us, dt, acc, gyr)
    if gp:
        if broken_pos:
            var = (0.0, 0.0, 0.0)
        else:
            var = (std[0] * std[0], std[1] * std[1], std[2] * std[2])
        nav.gnss_pos(ecef, var)
    if gv:
        if broken_vel:
            varv = (0.0, 0.0, 0.0)
        else:
            varv = (vstd[0] * vstd[0], vstd[1] * vstd[1], vstd[2] * vstd[2])
        nav.gnss_vel(vel, varv)
    if lever != (0.0, 0.0, 0.0):
        nav.gnss_leverarm(lever)
    if lp:
        lvar = (lstd[0] * lstd[0], lstd[1] * lstd[1], lstd[2] * lstd[2])
        nav.local_pos(local, lvar)
    if yw:
        nav.yaw(yaw_rad, ystd)
    if br:
        nav.baro(pa)
    nav.update()
    emit(nav, t_us)
"""


@dataclass
class GateEpoch:
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
    yaw_rad: float | None = None
    yaw_std: float | None = None
    baro_pa: float | None = None
    gnss_broken: bool = False
    vel_broken: bool = False


@dataclass
class GateScenario:
    origin_ecef: tuple[float, float, float]
    lat_deg: float
    lon_deg: float
    h_m: float
    epochs: list[GateEpoch] = field(default_factory=list)
    auto_init: bool = True
    auto_zupt_disable: bool = True
    unlimited: bool = False
    dwell_disable: bool = False
    stop_disable: bool = False
    ready_only: bool = False
    baro_height_disable: bool = False
    # Public ins_options_t.chi2_disable / Config(chi2_disable=...): probes
    # that are not about outlier handling turn the (unspecified-strength)
    # downweighting off so it cannot decide their result.
    chi2_disable: bool = False
    fusion_h: float = 0.0
    fusion_v: float = 0.0
    fusion_hv: float = 0.0
    fusion_vv: float = 0.0
    entry_h: float = 0.0
    entry_v: float = 0.0
    entry_hv: float = 0.0
    entry_vv: float = 0.0
    exit_h: float = 0.0
    exit_v: float = 0.0
    exit_hv: float = 0.0
    exit_vv: float = 0.0
    coast_sec: float = 0.0
    pos_decimation: int = 0
    rpy_init: tuple[float, float, float] = (0.0, 0.0, 0.0)
    timeout: float = GATE_TIMEOUT


@dataclass
class GateSnapshot:
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
    pos_std: tuple[float, float, float] | None
    vel_std: tuple[float, float, float] | None
    bias_acc_std: tuple[float, float, float] | None
    bias_gyr_std: tuple[float, float, float] | None
    dr_ms: int | None
    n_seen: int
    n_used: int
    n_rate: int
    # Raw ins_deadreckoning_ms / deadreckoning_ms return (None: not an int,
    # or the no-instance line). dr_ms is the published age (raw >= 0).
    dr_raw: int | None = None


@dataclass
class GateRun:
    init_ok: bool
    snaps: list[GateSnapshot]

    def last(self) -> GateSnapshot:
        if not self.snaps:
            raise HarnessError("run produced no snapshots")
        return self.snaps[-1]

    def first_initialized(self) -> GateSnapshot | None:
        for snap in self.snaps:
            if snap.pos_ok:
                return snap
        return None

    def first_ready(self) -> GateSnapshot | None:
        for snap in self.snaps:
            if snap.ready:
                return snap
        return None

    def at_or_before(self, t_us: int) -> GateSnapshot:
        chosen = None
        for snap in self.snaps:
            if snap.t_us <= t_us:
                chosen = snap
        if chosen is None:
            raise HarnessError(f"no snapshot at or before t={t_us}")
        return chosen

    def at_or_after(self, t_us: int) -> GateSnapshot:
        for snap in self.snaps:
            if snap.t_us >= t_us:
                return snap
        raise HarnessError(f"no snapshot at or after t={t_us}")


def encode_gate(scen: GateScenario) -> str:
    ox, oy, oz = scen.origin_ecef
    r0, r1, r2 = scen.rpy_init
    lines = [
        f"{ox:.17g} {oy:.17g} {oz:.17g} {int(scen.auto_init)} "
        f"{int(scen.auto_zupt_disable)} {int(scen.unlimited)} "
        f"{int(scen.dwell_disable)} {int(scen.stop_disable)} "
        f"{int(scen.ready_only)} {int(scen.baro_height_disable)} "
        f"{int(scen.chi2_disable)}",
        f"{scen.fusion_h:.17g} {scen.fusion_v:.17g} {scen.fusion_hv:.17g} "
        f"{scen.fusion_vv:.17g} {scen.entry_h:.17g} {scen.entry_v:.17g} "
        f"{scen.entry_hv:.17g} {scen.entry_vv:.17g} {scen.exit_h:.17g} "
        f"{scen.exit_v:.17g} {scen.exit_hv:.17g} {scen.exit_vv:.17g}",
        f"{scen.coast_sec:.17g} {scen.pos_decimation} {r0:.17g} {r1:.17g} "
        f"{r2:.17g} {scen.lat_deg:.17g} {scen.lon_deg:.17g} {scen.h_m:.17g}",
    ]
    for e in scen.epochs:
        gp = 1 if e.gnss_ecef is not None else 0
        ecef = e.gnss_ecef if e.gnss_ecef is not None else (0.0, 0.0, 0.0)
        std = e.gnss_std if e.gnss_std is not None else (0.0, 0.0, 0.0)
        if e.gnss_broken:
            # Keep a 0 on one axis even if the broken flag is ignored: Q = σ² = 0.
            std = (0.0, std[1] if std[1] > 0.0 else 2.0, std[2] if std[2] > 0.0 else 2.0)
        gv = 1 if e.gnss_vel is not None else 0
        vel = e.gnss_vel if e.gnss_vel is not None else (0.0, 0.0, 0.0)
        vstd = e.gnss_vel_std if e.gnss_vel_std is not None else ENTRY_VEL_STD
        lp = 1 if e.local_ned is not None else 0
        local = e.local_ned if e.local_ned is not None else (0.0, 0.0, 0.0)
        lstd = e.local_std if e.local_std is not None else (CM_STD_M, CM_STD_M, CM_STD_M)
        yw = 1 if e.yaw_rad is not None else 0
        yaw = e.yaw_rad if e.yaw_rad is not None else 0.0
        ystd = e.yaw_std if e.yaw_std is not None else YAW_STD_RAD
        br = 1 if e.baro_pa is not None else 0
        pa = e.baro_pa if e.baro_pa is not None else 0.0
        lines.append(
            "E %d %.17g %.17g %.17g %.17g %.17g %.17g %.17g %d %d %d "
            "%.17g %.17g %.17g %.17g %.17g %.17g %d %.17g %.17g %.17g "
            "%.17g %.17g %.17g %.17g %.17g %.17g %d %.17g %.17g %.17g "
            "%.17g %.17g %.17g %d %.17g %.17g %d %.17g %d %d"
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
                yw,
                yaw,
                ystd,
                br,
                pa,
                int(e.gnss_broken),
                int(e.vel_broken),
            )
        )
    return "\n".join(lines) + "\n"


def _parse_optional_int(fields: dict[str, str], key: str) -> int | None:
    if key not in fields:
        raise HarnessError(f"snapshot missing {key}")
    raw = fields[key]
    if raw == "-":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise HarnessError(f"{key} not an int: {raw!r}") from exc


def parse_gate_snapshot(line: str) -> GateSnapshot:
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
    if "posstd" not in fields:
        raise HarnessError("snapshot missing posstd")
    pos_std_ok = fields["posstd"] != "-"
    pos_std = _parse_vec(fields, "posstd", pos_std_ok)
    if "velstd" not in fields:
        raise HarnessError("snapshot missing velstd")
    vel_std_ok = fields["velstd"] != "-"
    vel_std = _parse_vec(fields, "velstd", vel_std_ok)
    if "baccstd" not in fields:
        raise HarnessError("snapshot missing baccstd")
    bacc_std_ok = fields["baccstd"] != "-"
    bacc_std = _parse_vec(fields, "baccstd", bacc_std_ok)
    if "bgyrstd" not in fields:
        raise HarnessError("snapshot missing bgyrstd")
    bgyr_std_ok = fields["bgyrstd"] != "-"
    bgyr_std = _parse_vec(fields, "bgyrstd", bgyr_std_ok)
    if "dr" not in fields:
        raise HarnessError("snapshot missing dr")
    dr_tok = fields["dr"]
    dr_read = dr_tok != "-"  # "-" only on the no-instance line after a refused init
    dr_raw: int | None = None
    if dr_read and dr_tok != "?":
        try:
            dr_raw = int(dr_tok)
        except ValueError as exc:
            raise HarnessError(f"dr is not an int: {dr_tok!r}") from exc
    dr_ms = dr_raw if (dr_raw is not None and dr_raw >= 0) else None
    n_seen = _parse_int(fields, "n_seen")
    n_used = _parse_int(fields, "n_used")
    n_rate = _parse_int(fields, "n_rate")
    # Product invariants are recorded for the dedicated tests, never raised
    # here: one such value must not abort every run that parses the snapshot.
    if n_seen < 0 or n_used < 0:
        note_product_issue("F05", f"GNSS counters missing or negative: {line}")
    if n_rate < 0:
        note_product_issue("F05", f"GNSS used exceeds GNSS seen: {line}")
    # stdpub=0: the C arm, whose INS publishes attitude 1-sigma only.
    std_published = fields.get("stdpub", "1") != "0"
    if std_published and pos_ok and (
        pos_std is None or vel_std is None or bacc_std is None or bgyr_std is None
    ):
        note_product_issue("F05", f"initialized snapshot missing published 1-sigma: {line}")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F05', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F05', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F05', f"ins_get_diag returned NULL for a live instance: {line}")
    if pos_ok and dr_ms is None:
        note_product_issue("F05.dr", f"initialized, but no dead-reckoning age (dr={dr_tok}): {line}")
    if (not pos_ok) and dr_read and dr_raw != -1:
        note_product_issue(
            "F05.dr", f"not initialized, but the age reader returned {dr_tok} instead of -1: {line}"
        )
    return GateSnapshot(
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
        pos_std=pos_std,
        vel_std=vel_std,
        bias_acc_std=bacc_std,
        bias_gyr_std=bgyr_std,
        dr_ms=dr_ms,
        dr_raw=dr_raw,
        n_seen=n_seen,
        n_used=n_used,
        n_rate=n_rate,
    )


def parse_gate_run(text: str) -> GateRun:
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
    snaps = [parse_gate_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    return GateRun(init_ok=(rc == 0), snaps=snaps)


def _run_gate(kind: str, scen: GateScenario) -> GateRun:
    payload = encode_gate(scen)
    timeout = scen.timeout if scen.timeout else GATE_TIMEOUT
    if kind == "c":
        result = invoke(_C_PROBE, stdin=payload, timeout=timeout)
    elif kind == "py":
        package = importable_package_name()
        result = run_python(
            _PY_PROBE.replace("__PKG__", package),
            stdin=payload,
            timeout=timeout,
        )
    else:
        raise HarnessError(f"unknown probe kind {kind!r}")
    text = require_probe_success(result)
    run = parse_gate_run(text)
    print(
        f"{kind} init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_ready={run.last().ready if run.snaps else None} "
        f"last_pos={run.last().pos_ok if run.snaps else None} "
        f"last_dr={run.last().dr_ms if run.snaps else None}",
        flush=True,
    )
    return run


def c_gate_run(scen: GateScenario) -> GateRun:
    return _run_gate("c", scen)


def py_gate_run(scen: GateScenario) -> GateRun:
    return _run_gate("py", scen)


def gate_langs(scen: GateScenario, *, include_py: bool = True):
    pairs = [("c", c_gate_run(scen))]
    if include_py:
        pairs.append(("py", py_gate_run(scen)))
    return pairs


def require_initialized(snap: GateSnapshot, what: str) -> None:
    if not snap.pos_ok:
        raise AssertionError(f"{what}: expected initialized (position published) at t={snap.t_us}")
    if not snap.vel_ok:
        raise AssertionError(f"{what}: velocity accessor failed while initialized at t={snap.t_us}")
    if snap.ecef is None:
        raise AssertionError(f"{what}: initialized snapshot has no ECEF")


def require_not_initialized(snap: GateSnapshot, what: str) -> None:
    if snap.pos_ok:
        raise AssertionError(f"{what}: expected accessors to fail at t={snap.t_us}")
    if snap.vel_ok:
        raise AssertionError(f"{what}: velocity still published at t={snap.t_us}")
    if snap.ecef is not None:
        raise AssertionError(f"{what}: unpublished position still printed an ECEF")


def require_ready_gate(snap: GateSnapshot, what: str) -> None:
    if not snap.ready:
        raise AssertionError(f"{what}: expected ready at t={snap.t_us}")
    require_initialized(snap, what)


def gate_site(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    epochs: list[GateEpoch],
    **kwargs,
) -> GateScenario:
    origin = kwargs.pop("origin_ecef", None)
    if origin is None:
        origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    return GateScenario(
        origin_ecef=origin,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        h_m=h_m,
        epochs=epochs,
        **kwargs,
    )


def _gate_epoch(
    t_us: int,
    *,
    dt_sec: float = DT_SEC,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    **kwargs,
) -> GateEpoch:
    return GateEpoch(
        t_us=t_us,
        dt_sec=dt_sec,
        acc=(float(acc[0]), float(acc[1]), float(acc[2])),
        gyr=(float(gyr[0]), float(gyr[1]), float(gyr[2])),
        **kwargs,
    )


def _gnss_every(imu_hz: int, gnss_hz: int) -> int:
    if imu_hz <= 0 or gnss_hz <= 0:
        raise HarnessError("rates must be positive")
    every = imu_hz // gnss_hz
    if every <= 0:
        raise HarnessError("GNSS rate cannot exceed IMU rate")
    return every


def append_stream(
    epochs: list[GateEpoch],
    *,
    duration_s: float,
    origin: Sequence[float],
    gnss_ecef: Sequence[float] | None,
    gnss_std: Sequence[float] | None = ENTRY_POS_STD,
    gnss_vel: Sequence[float] | None = ZERO_VEL,
    gnss_vel_std: Sequence[float] | None = ENTRY_VEL_STD,
    imu_hz: int = IMU_HZ,
    gnss_hz: int = FEW_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    local_ned: Sequence[float] | None = None,
    local_std: Sequence[float] | None = None,
    local_hz: int = LOCAL_HZ,
    yaw_rad: float | None = None,
    yaw_std: float | None = None,
    baro_pa: float | None = None,
    gnss_broken: bool = False,
    vel_broken: bool = False,
    gnss_at=None,
) -> list[GateEpoch]:
    """Append IMU plus optional GNSS / local / yaw / baro. Timestamps continue."""
    if duration_s <= 0.0:
        raise HarnessError("stream duration must be positive")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    if n <= 0:
        raise HarnessError("stream produced no epochs")
    every = _gnss_every(imu_hz, gnss_hz) if gnss_ecef is not None or gnss_at is not None else None
    local_every = _gnss_every(imu_hz, local_hz) if local_ned is not None else None
    t0 = epochs[-1].t_us if epochs else 0
    out = list(epochs)
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        has_gnss = False
        ecef = None
        std = None
        vel = None
        vstd = None
        if every is not None and i % every == 0:
            has_gnss = True
            if gnss_at is not None:
                ecef, std, vel, vstd = gnss_at(t_us, i)
            else:
                ecef = tuple(gnss_ecef) if gnss_ecef is not None else None
                std = tuple(gnss_std) if gnss_std is not None else None
                vel = tuple(gnss_vel) if gnss_vel is not None else None
                vstd = tuple(gnss_vel_std) if (gnss_vel is not None and gnss_vel_std is not None) else None
        has_local = local_every is not None and i % local_every == 0
        out.append(
            _gate_epoch(
                t_us,
                dt_sec=dt,
                acc=acc,
                gyr=gyr,
                gnss_ecef=ecef if has_gnss else None,
                gnss_std=std if has_gnss else None,
                gnss_vel=vel if has_gnss else None,
                gnss_vel_std=vstd if has_gnss else None,
                local_ned=tuple(local_ned) if has_local else None,
                local_std=tuple(local_std) if has_local else None,
                yaw_rad=yaw_rad if has_gnss and yaw_rad is not None else None,
                yaw_std=yaw_std if (has_gnss and yaw_rad is not None) else None,
                baro_pa=baro_pa if (has_gnss or has_local) else None,
                gnss_broken=gnss_broken if has_gnss else False,
                vel_broken=vel_broken if (has_gnss and vel is not None) else False,
            )
        )
        _ = origin
    return out


def pad_ready(
    origin: Sequence[float],
    *,
    duration_s: float = READY_PAD_S,
    gnss_std: Sequence[float] = ENTRY_POS_STD,
    gnss_ecef: Sequence[float] | None = None,
    gnss_hz: int = FEW_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    yaw_rad: float | None = None,
    baro_pa: float | None = None,
) -> list[GateEpoch]:
    fix = tuple(gnss_ecef) if gnss_ecef is not None else tuple(origin)
    return append_stream(
        [],
        duration_s=duration_s,
        origin=origin,
        gnss_ecef=fix,
        gnss_std=gnss_std,
        gnss_hz=gnss_hz,
        acc=acc,
        gyr=gyr,
        yaw_rad=yaw_rad,
        yaw_std=YAW_STD_RAD if yaw_rad is not None else None,
        baro_pa=baro_pa,
    )


def coast_imu(
    epochs: list[GateEpoch],
    *,
    duration_s: float,
    acc: Sequence[float] = (NORTH_ACCEL, 0.0, -9.81),
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
) -> list[GateEpoch]:
    return append_stream(
        epochs,
        duration_s=duration_s,
        origin=(0.0, 0.0, 0.0),
        gnss_ecef=None,
        acc=acc,
        gyr=gyr,
    )


def runtime_coarse_sigma_m() -> float:
    """Fusable but not entry-quality, and not the named 10 m row."""
    u = runtime_uuid_int()
    sigma = 7.2 + (u % 90) / 50.0
    if abs(sigma - 10.0) < 0.4:
        sigma = 8.1
    print(f"runtime coarse sigma={sigma} m", flush=True)
    return sigma


def runtime_between_gate_sigma_m() -> float:
    u = runtime_uuid_int()
    sigma = 3.6 + (u % 80) / 100.0
    if sigma >= 4.8:
        sigma = 4.1
    if sigma <= 3.05:
        sigma = 3.7
    print(f"runtime between-gate sigma={sigma} m", flush=True)
    return sigma


def runtime_under_cap_sigma_m() -> float:
    u = runtime_uuid_int()
    sigma = 28.0 + (u % 250) / 10.0
    if sigma <= 12.0:
        sigma = 35.0
    if sigma >= 100.0:
        sigma = 55.0
    print(f"runtime under-cap sigma={sigma} m", flush=True)
    return sigma


def runtime_under_vel_cap_sigma_mps() -> float:
    """Worse than entry 0.25/0.30 m/s, still below the named 60 m/s fusion cap."""
    u = runtime_uuid_int()
    sigma = 4.0 + (u % 180) / 20.0
    if sigma <= 1.0:
        sigma = 6.0
    if sigma >= 50.0:
        sigma = 12.0
    print(f"runtime under-vel-cap sigma={sigma} m/s", flush=True)
    return sigma


def runtime_in_window_outage_s() -> float:
    u = runtime_uuid_int()
    sec = 1.6 + (u % 70) / 100.0
    print(f"runtime in-window outage={sec} s", flush=True)
    return sec


def runtime_north_offset_m() -> float:
    n, _e, _d = runtime_gnss_step_m()
    if n < 1.5:
        n = 3.2
    print(f"runtime north offset={n} m", flush=True)
    return n


def runtime_decimation_n() -> int:
    u = runtime_uuid_int()
    n = 3 if (u % 2) == 0 else 3
    print(f"runtime decimation N={n}", flush=True)
    return 3


def north_of(origin: Sequence[float], north_m: float) -> tuple[float, float, float]:
    return ecef_plus_ned(origin, north_m, 0.0, 0.0)


def append_combined_north_steps(
    epochs: list[GateEpoch],
    *,
    origin: Sequence[float],
    step_m: float,
    duration_s: float = 2.0,
    gnss_hz: int = FEW_HZ,
    gnss_vel: Sequence[float] = ZERO_VEL,
    gnss_std: Sequence[float] = ENTRY_POS_STD,
    gnss_vel_std: Sequence[float] = ENTRY_VEL_STD,
) -> list[GateEpoch]:
    """Few-Hz combined GNSS whose position steps north on every epoch.

    Each offered epoch carries both position and velocity. A position fuse
    on that epoch pulls north by a visible fraction of ``step_m``; a skip
    or a velocity-only fuse on a still pad does not. Interval is above the
    100 ms rate limit so pacing is not in play.
    """
    every = _gnss_every(IMU_HZ, gnss_hz)
    vel = (float(gnss_vel[0]), float(gnss_vel[1]), float(gnss_vel[2]))
    std = (float(gnss_std[0]), float(gnss_std[1]), float(gnss_std[2]))
    vstd = (float(gnss_vel_std[0]), float(gnss_vel_std[1]), float(gnss_vel_std[2]))

    def gnss_at(_t_us: int, i: int):
        k = i // every
        return north_of(origin, k * step_m), std, vel, vstd

    return append_stream(
        epochs,
        duration_s=duration_s,
        origin=origin,
        gnss_ecef=origin,
        gnss_hz=gnss_hz,
        gnss_at=gnss_at,
    )


def east_of(origin: Sequence[float], east_m: float) -> tuple[float, float, float]:
    return ecef_plus_ned(origin, 0.0, east_m, 0.0)


def north_pull_m(origin: Sequence[float], ecef: Sequence[float]) -> float:
    return ned_offset_from_two_ecef(origin, ecef)[0]


def east_pull_m(origin: Sequence[float], ecef: Sequence[float]) -> float:
    return ned_offset_from_two_ecef(origin, ecef)[1]


def runtime_east_vel_mps() -> float:
    u = runtime_uuid_int()
    vel = 2.5 + (u % 90) / 30.0
    print(f"runtime east vel={vel} m/s", flush=True)
    return vel


def north_increments(
    origin: Sequence[float],
    run: GateRun,
    times: Sequence[int],
    t0: int,
) -> list[float]:
    """North increment at each GNSS time, relative to the previous snapshot."""
    base = run.at_or_before(t0)
    if base.ecef is None:
        raise HarnessError(f"no ECEF at t0={t0} from which to measure north increments")
    prev = north_pull_m(origin, base.ecef)
    out: list[float] = []
    for t in times:
        snap = run.at_or_after(t)
        if snap.ecef is None:
            raise HarnessError(f"no ECEF at t={t} while measuring north increments")
        now = north_pull_m(origin, snap.ecef)
        out.append(now - prev)
        prev = now
    return out


def dist_m(a: Sequence[float], b: Sequence[float]) -> float:
    return hypot3(a, b)


def coast_acc() -> tuple[float, float, float]:
    return (NORTH_ACCEL, 0.0, -9.81)


def yaw_gyr() -> tuple[float, float, float]:
    return (0.0, 0.0, YAW_RATE_RPS)
