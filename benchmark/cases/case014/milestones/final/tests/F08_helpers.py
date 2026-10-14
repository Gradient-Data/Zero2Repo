# feature: F08
"""Observation helpers for FP-08 navigation suite and graceful degradation.

C probes compile through the sealed harness. Python observations run in a
child interpreter driving the navigator (not the lean INS wrapper). This
module does not import the product in the pytest process. Expected ECEF
comes from the GNSS that was fed (sealed WGS84). Baro steps use the sealed
tropospheric ISA. Yaw-carry expectations use already-published INS and ARS
yaw, never an internal carry struct.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Sequence

from _harness import (
    nonfinite_fields,
    note_product_issue,
    runtime_uuid_int,
    HarnessError,
    RunResult,
    compile_repository,
    invoke,
    product_identity,
    repo_root,
    run_python,
)
from F01_helpers import hypot3, require_probe_success
from F02_helpers import (
    DT_SEC,
    ECEF_MATCH_M,
    ENTRY_DWELL_S,
    GNSS_HZ,
    GNSS_STD_M,
    HAPPY_DURATION_S,
    IMU_HZ,
    LONG_TIMEOUT,
    READY_WAIT_S,
    SPECIFIC_FORCE_LEVEL,
    _parse_flag,
    _parse_int,
    _parse_optional_float,
    _parse_vec,
    ecef_from_llh_deg,
    ecef_plus_ned,
    runtime_gnss_step_m,
    runtime_site,
)
from F03_helpers import (
    CM_STD_M,
    G_MPS2,
    LOCAL_HZ,
    angle_diff_rad,
    body_mag_for_yaw,
    ned_field_from_independent_wmm,
    runtime_tracker_ned,
    still_level_acc,
)
from F05_helpers import EXIT_DWELL_S, EXIT_POS_BAD, FREEZE_11S, UNFUSABLE_POS_STD
from F06_helpers import _tok, runtime_att_yaw_rad, runtime_z_rate_rps
from F07_helpers import runtime_climb_m, tropospheric_isa_pressure_pa

# Fixed inputs and tolerances for FP-08 and sealed
# instruments from FP-02 / FP-05.
OUTAGE_3S = 3.0
AIDING_FULL_S = 1.9
AIDING_EQUAL_S = 2.0
AIDING_JUST_OVER_S = 2.03  # a few 100 Hz samples past 2.0 s, not 2.1 s
ZERO_VEL = (0.0, 0.0, 0.0)
ENTRY_VEL_STD = (0.10, 0.10, 0.10)
YAW_AID_STD = math.radians(3.0)
HINT_YAW_STD = math.radians(5.0)
MAG_YEAR = 2025.0
MAG_VAR = (1.0, 1.0, 1.0)
ABSURD_NORTH_ACC = (3.2, 0.0, -G_MPS2)
# The spec leaves the default stillness magnitude bounds to the implementer
#, so the standstill test sets them through the public INS options
# and keeps its residual inside them.
STILL_GYR_BOUND_RPS = math.radians(5.0)
STILL_ACC_BOUND_MPS2 = 0.5
STILL_Z_RATE_RPS = math.radians(2.3)
STILL_VERT_ACC = (0.0, 0.0, -(G_MPS2 + 0.35))
# Observe quality-loss after the named 10 s dwell, not on the exact boundary sample.
QUALITY_LOSS_S = EXIT_DWELL_S + 1.0
# Long enough that a runtime 8–15 deg/s z-rate splits INS yaw-aid from free-integrating ARS.
SPLIT_YAW_S = 6.0
NAV_TIMEOUT = LONG_TIMEOUT
MODE_FULL = "FULL"
MODE_COASTING = "COASTING"
MODE_ATTITUDE_ONLY = "ATTITUDE_ONLY"
MODE_NONE = "NONE"

_C_PROBE = r"""
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "nav_suite.h"
#include "geodetic_toolbox.h"

static int fail_read(const char *what)
{
    fprintf(stderr, "probe stdin: %s\n", what);
    return 2;
}

static int split_ws(char *line, char **tok, int max)
{
    int n = 0;
    char *p = line;
    while (*p && n < max) {
        while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') {
            p++;
        }
        if (*p == '\0') {
            break;
        }
        tok[n++] = p;
        while (*p && *p != ' ' && *p != '\t' && *p != '\r' && *p != '\n') {
            p++;
        }
        if (*p) {
            *p = '\0';
            p++;
        }
    }
    return n;
}

static int parse_f(const char *s, float *out)
{
    char *end = NULL;
    *out = strtof(s, &end);
    if (end == s) {
        return 0;
    }
    return 1;
}

static int parse_d(const char *s, double *out)
{
    char *end = NULL;
    *out = strtod(s, &end);
    if (end == s) {
        return 0;
    }
    return 1;
}

static int parse_ll(const char *s, long long *out)
{
    char *end = NULL;
    *out = strtoll(s, &end, 10);
    if (end == s) {
        return 0;
    }
    return 1;
}

static void print_triple(const char *key, int ok, const float *v)
{
    if (ok) {
        printf(" %s=%.9g,%.9g,%.9g", key, v[0], v[1], v[2]);
    } else {
        printf(" %s=-", key);
    }
}

/* Mode name from the four published nav_suite_mode_t constants. */
static const char *mode_text(nav_suite_mode_t m)
{
    if (m == NAV_SUITE_MODE_FULL) {
        return "FULL";
    }
    if (m == NAV_SUITE_MODE_COASTING) {
        return "COASTING";
    }
    if (m == NAV_SUITE_MODE_ATTITUDE_ONLY) {
        return "ATTITUDE_ONLY";
    }
    if (m == NAV_SUITE_MODE_NONE) {
        return "NONE";
    }
    return "?";
}

static void print_snap(const nav_suite_t *s, long long t_us)
{
    nav_suite_mode_t mode_v = nav_suite_get_mode(s);
    int mode = (int)mode_v;
    int ready = 0, pos = 0, vel_ok = 0, ned_ok = 0;
    int best = 0, ins_att = 0, ars = 0, ahrs = 0;
    int h_ok = 0, ell_ok = 0, baro_ok = 0, ars_b = 0, ahrs_b = 0;
    double ecef[3] = {0.0, 0.0, 0.0};
    float ned[3] = {0.0f, 0.0f, 0.0f};
    float vel[3] = {0.0f, 0.0f, 0.0f};
    float brpy[3] = {0.0f, 0.0f, 0.0f};
    float irpy[3] = {0.0f, 0.0f, 0.0f};
    float arpy[3] = {0.0f, 0.0f, 0.0f};
    float hrpy[3] = {0.0f, 0.0f, 0.0f};
    float ars_bias[3] = {0.0f, 0.0f, 0.0f};
    float ahrs_bias[3] = {0.0f, 0.0f, 0.0f};
    float h_m = 0.0f, ell = 0.0f, bh = 0.0f, bv = 0.0f;

    if (s != NULL) {
        ready = ins_is_ready(&s->ins) ? 1 : 0;
        pos = ins_get_position_ecef(&s->ins, ecef) ? 1 : 0;
        vel_ok = ins_get_velocity_ned(&s->ins, vel) ? 1 : 0;
        ned_ok = ins_get_position_local(&s->ins, ned) ? 1 : 0;
        best = nav_suite_get_rpy(s, &brpy[0], &brpy[1], &brpy[2]) ? 1 : 0;
        ins_att = nav_suite_get_rpy_ins(s, &irpy[0], &irpy[1], &irpy[2]) ? 1 : 0;
        ars = nav_suite_get_rpy_ars(s, &arpy[0], &arpy[1], &arpy[2]) ? 1 : 0;
        ahrs = nav_suite_get_rpy_ahrs(s, &hrpy[0], &hrpy[1], &hrpy[2]) ? 1 : 0;
        h_ok = nav_suite_get_height(s, &h_m) ? 1 : 0;
        ell_ok = nav_suite_get_height_ellipsoid(s, &ell) ? 1 : 0;
        baro_ok = nav_suite_get_baro_alt(s, &bh, &bv) ? 1 : 0;
        ars_b = ahrs_get_bias_gyr(&s->ars, ars_bias) ? 1 : 0;
        ahrs_b = ahrs_get_bias_gyr(&s->ahrs, ahrs_bias) ? 1 : 0;
    }
    printf("SNAP t_us=%lld mode=%d mode_name=%s ready=%d pos=%d vel=%d ned=%d",
           t_us, mode, mode_text(mode_v), ready, pos, vel_ok, ned_ok);
    printf(" best=%d ins_att=%d ars=%d ahrs=%d h_ok=%d ell_ok=%d baro=%d",
           best, ins_att, ars, ahrs, h_ok, ell_ok, baro_ok);
    printf(" ars_b=%d ahrs_b=%d", ars_b, ahrs_b);
    if (pos) {
        printf(" ecef=%.17g,%.17g,%.17g", ecef[0], ecef[1], ecef[2]);
    } else {
        printf(" ecef=-");
    }
    print_triple("nedpos", ned_ok, ned);
    print_triple("velned", vel_ok, vel);
    print_triple("att", best, brpy);
    print_triple("ins_att_v", ins_att, irpy);
    print_triple("ars_att", ars, arpy);
    print_triple("ahrs_att", ahrs, hrpy);
    print_triple("ars_gyr", ars_b, ars_bias);
    print_triple("ahrs_gyr", ahrs_b, ahrs_bias);
    if (h_ok) {
        printf(" h=%.9g", h_m);
    } else {
        printf(" h=-");
    }
    if (ell_ok) {
        printf(" ell=%.9g", ell);
    } else {
        printf(" ell=-");
    }
    if (baro_ok) {
        printf(" baro_h=%.9g baro_v=%.9g", bh, bv);
    } else {
        printf(" baro_h=- baro_v=-");
    }
    printf("\n");
}

static int read_cfg(double *lat, double *lon, double *h, int *auto_init,
                    int *chi2, int *zupt_off, int *unlimited, double *yaw_hint,
                    double *yaw_std, float *still_gyr, float *still_acc)
{
    char line[4096];
    char *tok[16];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("cfg");
    }
    int n = split_ws(line, tok, 16);
    if (n != 11) {
        return fail_read("cfg fields");
    }
    if (!parse_f(tok[9], still_gyr) || !parse_f(tok[10], still_acc)) {
        return fail_read("cfg stillness");
    }
    float auto_f, chi2_f, zupt_f, unl_f;
    if (!parse_d(tok[0], lat) || !parse_d(tok[1], lon) || !parse_d(tok[2], h) ||
        !parse_f(tok[3], &auto_f) || !parse_f(tok[4], &chi2_f) ||
        !parse_f(tok[5], &zupt_f) || !parse_f(tok[6], &unl_f) ||
        !parse_d(tok[7], yaw_hint) || !parse_d(tok[8], yaw_std)) {
        return fail_read("cfg numbers");
    }
    *auto_init = (int)auto_f;
    *chi2 = (int)chi2_f;
    *zupt_off = (int)zupt_f;
    *unlimited = (int)unl_f;
    return 0;
}

static int init_suite(nav_suite_t *s, double lat, double lon, double h,
                      int auto_init, int chi2, int zupt_off, int unlimited,
                      double yaw_hint, double yaw_std, float still_gyr,
                      float still_acc)
{
    memset(s, 0, sizeof *s);
    ins_init_t init;
    memset(&init, 0, sizeof init);
    ins_options_t opt;
    memset(&opt, 0, sizeof opt);
    init.time = 0;
    ins_latlonh_to_ecef(lat * M_PI / 180.0, lon * M_PI / 180.0, h, init.x_ecef);
    opt.auto_init = auto_init ? true : false;
    opt.chi2_disable = chi2 ? true : false;
    opt.auto_zupt_disable = zupt_off ? true : false;
    opt.auto_zupt_static_gyr_rps = still_gyr;
    opt.auto_zupt_static_acc_mps2 = still_acc;
    opt.allow_unlimited_deadreckoning = unlimited ? true : false;
    int rc = nav_suite_init(s, &init, &opt);
    printf("INIT rc=%d\n", rc);
    if (rc != 0) {
        print_snap(s, 0);
        return rc;
    }
    if (yaw_std > 0.0) {
        nav_suite_set_init_att_hint(s, 0.0f, 0.0f, 0.0f, (float)yaw_hint,
                                    (float)yaw_std);
    }
    return 0;
}

static int consume_epochs(nav_suite_t *s)
{
    char line[8192];
    char *tok[48];
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        int n = split_ws(line, tok, 48);
        if (n < 1 || tok[0][0] != 'E') {
            return fail_read("epoch tag");
        }
        if (n != 42) {
            return fail_read("epoch fields");
        }
        long long t_us = 0;
        double dt;
        float ax, ay, az, gx, gy, gz;
        float gp, sn, se, sd;
        double e0, e1, e2;
        float gv, vn, ve, vd, vsn, vse, vsd;
        float magf, mx, my, mz, br, pa;
        float lp, ln, le, ld, lsn, lse, lsd;
        float yw, yaw, ystd, zuptf, zaruf, stepf;
        if (!parse_ll(tok[1], &t_us) || !parse_d(tok[2], &dt) ||
            !parse_f(tok[3], &ax) || !parse_f(tok[4], &ay) ||
            !parse_f(tok[5], &az) || !parse_f(tok[6], &gx) ||
            !parse_f(tok[7], &gy) || !parse_f(tok[8], &gz) ||
            !parse_f(tok[9], &gp) || !parse_d(tok[10], &e0) ||
            !parse_d(tok[11], &e1) || !parse_d(tok[12], &e2) ||
            !parse_f(tok[13], &sn) || !parse_f(tok[14], &se) ||
            !parse_f(tok[15], &sd) || !parse_f(tok[16], &gv) ||
            !parse_f(tok[17], &vn) || !parse_f(tok[18], &ve) ||
            !parse_f(tok[19], &vd) || !parse_f(tok[20], &vsn) ||
            !parse_f(tok[21], &vse) || !parse_f(tok[22], &vsd) ||
            !parse_f(tok[23], &magf) || !parse_f(tok[24], &mx) ||
            !parse_f(tok[25], &my) || !parse_f(tok[26], &mz) ||
            !parse_f(tok[27], &br) || !parse_f(tok[28], &pa) ||
            !parse_f(tok[29], &lp) || !parse_f(tok[30], &ln) ||
            !parse_f(tok[31], &le) || !parse_f(tok[32], &ld) ||
            !parse_f(tok[33], &lsn) || !parse_f(tok[34], &lse) ||
            !parse_f(tok[35], &lsd) || !parse_f(tok[36], &yw) ||
            !parse_f(tok[37], &yaw) || !parse_f(tok[38], &ystd) ||
            !parse_f(tok[39], &zuptf) || !parse_f(tok[40], &zaruf) ||
            !parse_f(tok[41], &stepf)) {
            return fail_read("epoch numbers");
        }
        ins_measurements_t m;
        memset(&m, 0, sizeof m);
        m.timestamp = (ins_time_us_t)t_us;
        m.strapdown_dt_sec = (float)dt;
        m.acc.is_valid = true;
        m.gyr.is_valid = true;
        m.acc.data[0] = ax;
        m.acc.data[1] = ay;
        m.acc.data[2] = az;
        m.gyr.data[0] = gx;
        m.gyr.data[1] = gy;
        m.gyr.data[2] = gz;
        if ((int)gp) {
            m.gnss_pos.is_valid = true;
            m.gnss_pos.xyz_ecef[0] = e0;
            m.gnss_pos.xyz_ecef[1] = e1;
            m.gnss_pos.xyz_ecef[2] = e2;
            m.gnss_pos.Qll_ned[0] = sn * sn;
            m.gnss_pos.Qll_ned[4] = se * se;
            m.gnss_pos.Qll_ned[8] = sd * sd;
        }
        if ((int)gv) {
            m.gnss_vel.is_valid = true;
            m.gnss_vel.vel_ned[0] = vn;
            m.gnss_vel.vel_ned[1] = ve;
            m.gnss_vel.vel_ned[2] = vd;
            m.gnss_vel.Qll_ned[0] = vsn * vsn;
            m.gnss_vel.Qll_ned[4] = vse * vse;
            m.gnss_vel.Qll_ned[8] = vsd * vsd;
        }
        if ((int)magf) {
            m.mag.is_valid = true;
            m.mag.data[0] = mx;
            m.mag.data[1] = my;
            m.mag.data[2] = mz;
            m.mag.Qll_diag[0] = m.mag.Qll_diag[1] = m.mag.Qll_diag[2] = 1.0f;
        }
        if ((int)br) {
            m.baro.is_valid = true;
            m.baro.pressure_pa = pa;
        }
        if ((int)lp) {
            m.local_pos.is_valid = true;
            m.local_pos.pos_ned[0] = ln;
            m.local_pos.pos_ned[1] = le;
            m.local_pos.pos_ned[2] = ld;
            m.local_pos.Qll_ned[0] = lsn * lsn;
            m.local_pos.Qll_ned[4] = lse * lse;
            m.local_pos.Qll_ned[8] = lsd * lsd;
        }
        if ((int)yw) {
            m.yaw.is_valid = true;
            m.yaw.yaw_rad = yaw;
            m.yaw.stddev_rad = ystd;
        }
        if ((int)zuptf) {
            m.zero_velocity_update = true;
        }
        if ((int)zaruf) {
            m.zero_rotation_update = true;
        }
        if ((int)stepf) {
            nav_suite_update(s, &m);
        }
        print_snap(s, t_us);
    }
    return 0;
}

static int run_nav(void)
{
    double lat = 0.0, lon = 0.0, h = 0.0, yaw_hint = 0.0, yaw_std = 0.0;
    int auto_init = 1, chi2 = 0, zupt_off = 0, unlimited = 0;
    float still_gyr = 0.0f, still_acc = 0.0f;
    int cfg = read_cfg(&lat, &lon, &h, &auto_init, &chi2, &zupt_off, &unlimited,
                       &yaw_hint, &yaw_std, &still_gyr, &still_acc);
    if (cfg != 0) {
        return cfg;
    }
    static nav_suite_t s;
    int rc = init_suite(&s, lat, lon, h, auto_init, chi2, zupt_off, unlimited,
                        yaw_hint, yaw_std, still_gyr, still_acc);
    if (rc != 0) {
        return 0;
    }
    return consume_epochs(&s);
}

static int run_unused(void)
{
    double lat = 0.0, lon = 0.0, h = 0.0, yaw_hint = 0.0, yaw_std = 0.0;
    int auto_init = 1, chi2 = 0, zupt_off = 0, unlimited = 0;
    float still_gyr = 0.0f, still_acc = 0.0f;
    int cfg = read_cfg(&lat, &lon, &h, &auto_init, &chi2, &zupt_off, &unlimited,
                       &yaw_hint, &yaw_std, &still_gyr, &still_acc);
    if (cfg != 0) {
        return cfg;
    }
    static nav_suite_t s;
    int rc = init_suite(&s, lat, lon, h, auto_init, chi2, zupt_off, unlimited,
                        yaw_hint, yaw_std, still_gyr, still_acc);
    if (rc != 0) {
        return 0;
    }
    print_snap(&s, 0);
    return 0;
}

static int run_null(void)
{
    printf("INIT rc=0\n");
    print_snap(NULL, 0);
    return 0;
}

int main(void)
{
    char line[256];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("kind");
    }
    if (strncmp(line, "NULL", 4) == 0) {
        return run_null();
    }
    if (strncmp(line, "UNUSED", 6) == 0) {
        return run_unused();
    }
    if (strncmp(line, "RUN", 3) == 0) {
        return run_nav();
    }
    return fail_read("kind token");
}
"""

_PY_PROBE = r"""
import math
import sys

from __PKG__ import Config, Navigator

def fmt3(ok, vec):
    if not ok or vec is None:
        return "-"
    return "%.9g,%.9g,%.9g" % (vec[0], vec[1], vec[2])

def emit(nav, t_us):
    mode_name = nav.mode_name()
    # One token whatever the reader returns; a name outside the four is
    # recorded by the parser, it must not break the line.
    mode_name = str(mode_name).replace(" ", "~").replace("=", "~") or "<empty>"
    ready = 1 if nav.is_ready() else 0
    ecef = nav.position_ecef()
    ned = nav.position_local()
    vel = nav.velocity_ned()
    best = nav.rpy()
    ins_att = nav.rpy_ins()
    ars = nav.rpy_ars()
    ahrs = nav.rpy_ahrs()
    ars_b = nav.bias_gyr_ars()
    ahrs_b = nav.bias_gyr_ahrs()
    h = nav.height()
    ell = nav.height_ellipsoid()
    baro = nav.baro_alt()
    pos = 1 if ecef is not None else 0
    vel_ok = 1 if vel is not None else 0
    ned_ok = 1 if ned is not None else 0
    best_ok = 1 if best is not None else 0
    ins_ok = 1 if ins_att is not None else 0
    ars_ok = 1 if ars is not None else 0
    ahrs_ok = 1 if ahrs is not None else 0
    ars_b_ok = 1 if ars_b is not None else 0
    ahrs_b_ok = 1 if ahrs_b is not None else 0
    h_ok = 1 if h is not None else 0
    ell_ok = 1 if ell is not None else 0
    baro_ok = 1 if baro is not None else 0
    line = (
        "SNAP t_us=%d mode=- mode_name=%s ready=%d pos=%d vel=%d ned=%d "
        "best=%d ins_att=%d ars=%d ahrs=%d h_ok=%d ell_ok=%d baro=%d "
        "ars_b=%d ahrs_b=%d"
        % (
            t_us, mode_name, ready, pos, vel_ok, ned_ok,
            best_ok, ins_ok, ars_ok, ahrs_ok, h_ok, ell_ok, baro_ok,
            ars_b_ok, ahrs_b_ok,
        )
    )
    if pos:
        line += " ecef=%.17g,%.17g,%.17g" % tuple(ecef)
    else:
        line += " ecef=-"
    line += " nedpos=" + fmt3(ned_ok, ned)
    line += " velned=" + fmt3(vel_ok, vel)
    line += " att=" + fmt3(best_ok, best)
    line += " ins_att_v=" + fmt3(ins_ok, ins_att)
    line += " ars_att=" + fmt3(ars_ok, ars)
    line += " ahrs_att=" + fmt3(ahrs_ok, ahrs)
    line += " ars_gyr=" + fmt3(ars_b_ok, ars_b)
    line += " ahrs_gyr=" + fmt3(ahrs_b_ok, ahrs_b)
    if h_ok:
        line += " h=%.9g" % h
    else:
        line += " h=-"
    if ell_ok:
        line += " ell=%.9g" % ell
    else:
        line += " ell=-"
    if baro_ok:
        line += " baro_h=%.9g baro_v=%.9g" % (baro[0], baro[1])
    else:
        line += " baro_h=- baro_v=-"
    print(line)

def read_cfg():
    header = sys.stdin.readline()
    if not header:
        raise SystemExit("missing cfg")
    parts = header.split()
    if len(parts) != 11:
        raise SystemExit("cfg fields")
    # Config has no public stillness-bound keywords; only the C driver sets them.
    if float(parts[9]) or float(parts[10]):
        raise SystemExit("stillness bounds are C-only")
    lat, lon, h = [float(x) for x in parts[0:3]]
    auto_init = int(float(parts[3]))
    chi2 = int(float(parts[4]))
    zupt_off = int(float(parts[5]))
    unlimited = int(float(parts[6]))
    yaw_hint = float(parts[7])
    yaw_std = float(parts[8])
    return lat, lon, h, auto_init, chi2, zupt_off, unlimited, yaw_hint, yaw_std

def make_nav(lat, lon, h, auto_init, chi2, zupt_off, unlimited, yaw_hint, yaw_std):
    cfg_kw = dict(
        auto_init=bool(auto_init),
        lat_rad=math.radians(lat),
        lon_rad=math.radians(lon),
        h_m=h,
        allow_unlimited_deadreckoning=bool(unlimited),
        chi2_disable=bool(chi2),
        auto_zupt_disable=bool(zupt_off),
        gnss_max_horizontal_pos_stddev_m=0.0,
        gnss_max_vertical_pos_stddev_m=0.0,
        gnss_max_horizontal_vel_stddev_mps=0.0,
        gnss_max_vertical_vel_stddev_mps=0.0,
    )
    nav = Navigator(Config(**cfg_kw))
    if yaw_std > 0.0:
        nav.set_init_att_hint(yaw_rad=yaw_hint, stddev_yaw_rad=yaw_std)
    return nav

def consume(nav):
    for raw in sys.stdin:
        if not raw.strip() or raw.startswith("#"):
            continue
        tok = raw.split()
        if not tok or tok[0] != "E":
            raise SystemExit("epoch tag")
        if len(tok) != 42:
            raise SystemExit("epoch fields")
        t_us = int(tok[1])
        dt = float(tok[2])
        acc = (float(tok[3]), float(tok[4]), float(tok[5]))
        gyr = (float(tok[6]), float(tok[7]), float(tok[8]))
        gp = int(float(tok[9]))
        ecef = (float(tok[10]), float(tok[11]), float(tok[12]))
        std = (float(tok[13]), float(tok[14]), float(tok[15]))
        gv = int(float(tok[16]))
        vel = (float(tok[17]), float(tok[18]), float(tok[19]))
        vstd = (float(tok[20]), float(tok[21]), float(tok[22]))
        magf = int(float(tok[23]))
        mag = (float(tok[24]), float(tok[25]), float(tok[26]))
        br = int(float(tok[27]))
        pa = float(tok[28])
        lp = int(float(tok[29]))
        local = (float(tok[30]), float(tok[31]), float(tok[32]))
        lstd = (float(tok[33]), float(tok[34]), float(tok[35]))
        yw = int(float(tok[36]))
        yaw = float(tok[37])
        ystd = float(tok[38])
        zupt = int(float(tok[39]))
        zaru = int(float(tok[40]))
        step = int(float(tok[41]))
        nav.imu(t_us, dt, acc, gyr)
        if gp:
            var = (std[0] * std[0], std[1] * std[1], std[2] * std[2])
            nav.gnss_pos(ecef, var)
        if gv:
            varv = (vstd[0] * vstd[0], vstd[1] * vstd[1], vstd[2] * vstd[2])
            nav.gnss_vel(vel, varv)
        if magf:
            nav.mag(mag, (1.0, 1.0, 1.0))
        if br:
            nav.baro(pa)
        if lp:
            varl = (lstd[0] * lstd[0], lstd[1] * lstd[1], lstd[2] * lstd[2])
            nav.local_pos(local, varl)
        if yw:
            nav.yaw(yaw, ystd)
        if zupt:
            nav.zupt(True)
        if zaru:
            nav.zaru(True)
        if step:
            nav.update()
        emit(nav, t_us)

kind = sys.stdin.readline()
if not kind:
    raise SystemExit("missing kind")
cfg = read_cfg()
try:
    nav = make_nav(*cfg)
except ValueError:
    print("INIT rc=-1")
    print(
        "SNAP t_us=0 mode=- mode_name=NONE ready=0 pos=0 vel=0 ned=0 "
        "best=0 ins_att=0 ars=0 ahrs=0 h_ok=0 ell_ok=0 baro=0 ars_b=0 ahrs_b=0 "
        "ecef=- nedpos=- velned=- att=- ins_att_v=- ars_att=- ahrs_att=- "
        "ars_gyr=- ahrs_gyr=- h=- ell=- baro_h=- baro_v=-"
    )
    raise SystemExit(0)
print("INIT rc=0")
if kind.startswith("UNUSED") or kind.startswith("NULL"):
    emit(nav, 0)
    raise SystemExit(0)
consume(nav)
"""


@dataclass
class NavEpoch:
    t_us: int
    dt_sec: float = DT_SEC
    acc: tuple[float, float, float] = SPECIFIC_FORCE_LEVEL
    gyr: tuple[float, float, float] = (0.0, 0.0, 0.0)
    gnss_ecef: tuple[float, float, float] | None = None
    gnss_std: tuple[float, float, float] | None = None
    gnss_vel: tuple[float, float, float] | None = None
    gnss_vel_std: tuple[float, float, float] | None = None
    mag: tuple[float, float, float] | None = None
    baro_pa: float | None = None
    local_ned: tuple[float, float, float] | None = None
    local_std: tuple[float, float, float] | None = None
    yaw_rad: float | None = None
    yaw_std: float | None = None
    zupt: bool = False
    zaru: bool = False
    step: bool = True


@dataclass
class NavScenario:
    lat_deg: float
    lon_deg: float
    h_m: float
    epochs: list[NavEpoch] = field(default_factory=list)
    kind: str = "run"
    auto_init: bool = True
    chi2_disable: bool = False
    auto_zupt_disable: bool = False
    unlimited: bool = False
    yaw_hint: float = 0.0
    yaw_std: float = 0.0
    # Public ins_options_t stillness magnitude bounds; 0 keeps the default.
    auto_zupt_static_gyr_rps: float = 0.0
    auto_zupt_static_acc_mps2: float = 0.0
    timeout: float = NAV_TIMEOUT


@dataclass
class NavSnapshot:
    t_us: int
    mode: int | None
    mode_name: str | None
    ready: bool
    pos_ok: bool
    vel_ok: bool
    ned_ok: bool
    best_ok: bool
    ins_att_ok: bool
    ars_ok: bool
    ahrs_ok: bool
    h_ok: bool
    ell_ok: bool
    baro_ok: bool
    ars_bias_ok: bool
    ahrs_bias_ok: bool
    ecef: tuple[float, float, float] | None
    ned: tuple[float, float, float] | None
    vel_ned: tuple[float, float, float] | None
    best: tuple[float, float, float] | None
    ins_att: tuple[float, float, float] | None
    ars_att: tuple[float, float, float] | None
    ahrs_att: tuple[float, float, float] | None
    ars_gyr: tuple[float, float, float] | None
    ahrs_gyr: tuple[float, float, float] | None
    h: float | None
    ell: float | None
    baro_h: float | None
    baro_v: float | None


@dataclass
class NavRun:
    init_ok: bool
    snaps: list[NavSnapshot]

    def last(self) -> NavSnapshot:
        if not self.snaps:
            raise HarnessError("nav run has no snapshots")
        return self.snaps[-1]

    def at_or_before(self, t_us: int) -> NavSnapshot:
        chosen = None
        for snap in self.snaps:
            if snap.t_us <= t_us:
                chosen = snap
        if chosen is None:
            raise HarnessError(f"no snapshot at or before t={t_us}")
        return chosen

    def last_ready(self) -> NavSnapshot:
        chosen = None
        for snap in self.snaps:
            if snap.ready and snap.pos_ok:
                chosen = snap
        if chosen is None:
            raise HarnessError("nav run has no ready snapshot")
        return chosen

    def at_or_after(self, t_us: int) -> NavSnapshot:
        for snap in self.snaps:
            if snap.t_us >= t_us:
                return snap
        raise HarnessError(f"no snapshot at or after t={t_us}")


def _every(imu_hz: int, src_hz: int) -> int:
    if imu_hz <= 0 or src_hz <= 0:
        raise HarnessError("rates must be positive")
    every = imu_hz // src_hz
    if every <= 0:
        raise HarnessError("source rate cannot exceed IMU rate")
    return every


def encode_nav(scen: NavScenario) -> str:
    if scen.kind == "null":
        return "NULL\n"
    cfg = (
        f"{_tok(scen.lat_deg)} {_tok(scen.lon_deg)} {_tok(scen.h_m)} "
        f"{int(scen.auto_init)} {int(scen.chi2_disable)} "
        f"{int(scen.auto_zupt_disable)} {int(scen.unlimited)} "
        f"{_tok(scen.yaw_hint)} {_tok(scen.yaw_std)} "
        f"{_tok(scen.auto_zupt_static_gyr_rps)} {_tok(scen.auto_zupt_static_acc_mps2)}"
    )
    if scen.kind == "unused":
        return f"UNUSED\n{cfg}\n"
    lines = ["RUN", cfg]
    for e in scen.epochs:
        gp = 1 if e.gnss_ecef is not None else 0
        ecef = e.gnss_ecef if e.gnss_ecef is not None else (0.0, 0.0, 0.0)
        std = e.gnss_std if e.gnss_std is not None else (0.0, 0.0, 0.0)
        gv = 1 if e.gnss_vel is not None else 0
        vel = e.gnss_vel if e.gnss_vel is not None else (0.0, 0.0, 0.0)
        vstd = e.gnss_vel_std if e.gnss_vel_std is not None else (0.0, 0.0, 0.0)
        magf = 1 if e.mag is not None else 0
        mag = e.mag if e.mag is not None else (0.0, 0.0, 0.0)
        br = 1 if e.baro_pa is not None else 0
        pa = float(e.baro_pa) if e.baro_pa is not None else 0.0
        lp = 1 if e.local_ned is not None else 0
        loc = e.local_ned if e.local_ned is not None else (0.0, 0.0, 0.0)
        lstd = e.local_std if e.local_std is not None else (0.0, 0.0, 0.0)
        yw = 1 if e.yaw_rad is not None else 0
        yaw = float(e.yaw_rad) if e.yaw_rad is not None else 0.0
        ystd = float(e.yaw_std) if e.yaw_std is not None else 0.0
        lines.append(
            "E %d %s %s %s %s %s %s %s %d %s %s %s %s %s %s %d %s %s %s %s %s %s "
            "%d %s %s %s %d %s %d %s %s %s %s %s %s %d %s %s %d %d %d"
            % (
                e.t_us,
                _tok(e.dt_sec),
                _tok(e.acc[0]),
                _tok(e.acc[1]),
                _tok(e.acc[2]),
                _tok(e.gyr[0]),
                _tok(e.gyr[1]),
                _tok(e.gyr[2]),
                gp,
                _tok(ecef[0]),
                _tok(ecef[1]),
                _tok(ecef[2]),
                _tok(std[0]),
                _tok(std[1]),
                _tok(std[2]),
                gv,
                _tok(vel[0]),
                _tok(vel[1]),
                _tok(vel[2]),
                _tok(vstd[0]),
                _tok(vstd[1]),
                _tok(vstd[2]),
                magf,
                _tok(mag[0]),
                _tok(mag[1]),
                _tok(mag[2]),
                br,
                _tok(pa),
                lp,
                _tok(loc[0]),
                _tok(loc[1]),
                _tok(loc[2]),
                _tok(lstd[0]),
                _tok(lstd[1]),
                _tok(lstd[2]),
                yw,
                _tok(yaw),
                _tok(ystd),
                int(e.zupt),
                int(e.zaru),
                int(e.step),
            )
        )
    return "\n".join(lines) + "\n"


def parse_nav_snapshot(line: str) -> NavSnapshot:
    if not line.startswith("SNAP "):
        raise HarnessError(f"not a SNAP line: {line!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad SNAP token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    pos_ok = _parse_flag(fields, "pos")
    vel_ok = _parse_flag(fields, "vel")
    ned_ok = _parse_flag(fields, "ned")
    best_ok = _parse_flag(fields, "best")
    ins_ok = _parse_flag(fields, "ins_att")
    ars_ok = _parse_flag(fields, "ars")
    ahrs_ok = _parse_flag(fields, "ahrs")
    h_ok = _parse_flag(fields, "h_ok")
    ell_ok = _parse_flag(fields, "ell_ok")
    baro_ok = _parse_flag(fields, "baro")
    ars_b_ok = _parse_flag(fields, "ars_b")
    ahrs_b_ok = _parse_flag(fields, "ahrs_b")
    mode_raw = fields.get("mode")
    if mode_raw is None or mode_raw == "-":
        mode_value = None
    else:
        mode_value = _parse_int(fields, "mode")
    mode_name_raw = fields.get("mode_name")
    if mode_name_raw is None:
        raise HarnessError(f"snapshot missing mode_name: {line!r}")
    mode_name = None if mode_name_raw == "-" else mode_name_raw
    if mode_name is not None and mode_name not in (
        MODE_FULL,
        MODE_COASTING,
        MODE_ATTITUDE_ONLY,
        MODE_NONE,
    ):
        note_product_issue("F08", f"mode name {mode_name!r} is not one of the four: {line}")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F08', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F08', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F08', f"ins_get_diag returned NULL for a live instance: {line}")
    h_val = _parse_optional_float(fields, "h")
    ell_val = _parse_optional_float(fields, "ell")
    if h_ok and h_val is None:
        raise HarnessError(f"local height marked published without a value: {line!r}")
    if (not h_ok) and h_val is not None:
        raise HarnessError(f"local height marked unpublished but a value was printed: {line!r}")
    if ell_ok and ell_val is None:
        raise HarnessError(f"ellipsoid height marked published without a value: {line!r}")
    if (not ell_ok) and ell_val is not None:
        raise HarnessError(f"ellipsoid marked unpublished but a value was printed: {line!r}")
    baro_h = _parse_optional_float(fields, "baro_h")
    baro_v = _parse_optional_float(fields, "baro_v")
    if baro_ok and (baro_h is None or baro_v is None):
        raise HarnessError(f"baro marked published without height/climb: {line!r}")
    if (not baro_ok) and (baro_h is not None or baro_v is not None):
        raise HarnessError(f"baro marked unpublished but values were printed: {line!r}")
    return NavSnapshot(
        t_us=_parse_int(fields, "t_us"),
        mode=mode_value,
        mode_name=mode_name,
        ready=_parse_flag(fields, "ready"),
        pos_ok=pos_ok,
        vel_ok=vel_ok,
        ned_ok=ned_ok,
        best_ok=best_ok,
        ins_att_ok=ins_ok,
        ars_ok=ars_ok,
        ahrs_ok=ahrs_ok,
        h_ok=h_ok,
        ell_ok=ell_ok,
        baro_ok=baro_ok,
        ars_bias_ok=ars_b_ok,
        ahrs_bias_ok=ahrs_b_ok,
        ecef=_parse_vec(fields, "ecef", pos_ok),
        ned=_parse_vec(fields, "nedpos", ned_ok),
        vel_ned=_parse_vec(fields, "velned", vel_ok),
        best=_parse_vec(fields, "att", best_ok),
        ins_att=_parse_vec(fields, "ins_att_v", ins_ok),
        ars_att=_parse_vec(fields, "ars_att", ars_ok),
        ahrs_att=_parse_vec(fields, "ahrs_att", ahrs_ok),
        ars_gyr=_parse_vec(fields, "ars_gyr", ars_b_ok),
        ahrs_gyr=_parse_vec(fields, "ahrs_gyr", ahrs_b_ok),
        h=h_val,
        ell=ell_val,
        baro_h=baro_h,
        baro_v=baro_v,
    )


def parse_nav_run(text: str) -> NavRun:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    init_lines = [ln for ln in lines if ln.startswith("INIT ")]
    if len(init_lines) != 1:
        raise HarnessError(f"probe stdout has {len(init_lines)} INIT lines")
    fields = dict(
        token.split("=", 1) for token in init_lines[0][5:].split() if "=" in token
    )
    if "rc" not in fields:
        raise HarnessError(f"INIT missing rc: {init_lines[0]!r}")
    try:
        rc = int(fields["rc"])
    except ValueError as exc:
        raise HarnessError(f"INIT rc not an int: {init_lines[0]!r}") from exc
    snaps = [parse_nav_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    return NavRun(init_ok=(rc == 0), snaps=snaps)


_COMPILE_DONE = False
_COMPILE_RESULT: RunResult | None = None
_COMPILE_ERROR: BaseException | None = None


def _compile_detail(result: RunResult | None) -> str:
    """Text of ``make pylib replay`` attached to a failed observation."""
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


def _navigator_py_source(ident) -> str:
    """Python navigator probe that imports the package ``make pylib`` wrote."""
    source = _PY_PROBE.replace("__PKG__", ident.package_name)
    if "__PKG__" in source:
        raise HarnessError(
            "navigator probe did not receive the compiled package name"
        )
    return source


def _run_nav(kind: str, scen: NavScenario) -> NavRun:
    payload = encode_nav(scen)
    timeout = scen.timeout if scen.timeout else NAV_TIMEOUT
    ident = _require_compiled_product()
    if kind == "c":
        result = invoke(
            _C_PROBE, stdin=payload, timeout=timeout, root=repo_root()
        )
    elif kind == "py":
        result = run_python(
            _navigator_py_source(ident),
            stdin=payload,
            timeout=timeout,
            root=repo_root(),
        )
    else:
        raise HarnessError(f"unknown probe kind {kind!r}")
    text = require_probe_success(result)
    run = parse_nav_run(text)
    last = run.last() if run.snaps else None
    print(
        f"{kind} init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_mode={None if last is None else last.mode} "
        f"last_name={None if last is None else last.mode_name} "
        f"ready={None if last is None else last.ready} "
        f"pos={None if last is None else last.pos_ok}",
        flush=True,
    )
    return run


def c_nav_run(scen: NavScenario) -> NavRun:
    return _run_nav("c", scen)


def py_nav_run(scen: NavScenario) -> NavRun:
    return _run_nav("py", scen)


def nav_langs(scen: NavScenario, *, include_py: bool = True):
    pairs = [("c", c_nav_run(scen))]
    if include_py:
        pairs.append(("py", py_nav_run(scen)))
    return pairs


def require_ready_full(snap: NavSnapshot, what: str) -> None:
    if not snap.ready:
        raise AssertionError(f"{what}: expected INS ready at t={snap.t_us}")
    if not snap.pos_ok or snap.ecef is None:
        raise AssertionError(f"{what}: INS position accessor failed at t={snap.t_us}")


def require_positions_fail(snap: NavSnapshot, what: str) -> None:
    if snap.pos_ok or snap.ecef is not None:
        raise AssertionError(f"{what}: INS position still published at t={snap.t_us}")


def require_best_attitude(snap: NavSnapshot, what: str) -> tuple[float, float, float]:
    if not snap.best_ok or snap.best is None:
        raise AssertionError(f"{what}: best attitude was not published at t={snap.t_us}")
    if not all(math.isfinite(v) for v in snap.best):
        raise AssertionError(f"{what}: best attitude is not finite")
    return snap.best


def require_ahrs_attitude(snap: NavSnapshot, what: str) -> tuple[float, float, float]:
    if not snap.ahrs_ok or snap.ahrs_att is None:
        raise AssertionError(f"{what}: AHRS attitude was not published at t={snap.t_us}")
    if not all(math.isfinite(v) for v in snap.ahrs_att):
        raise AssertionError(f"{what}: AHRS attitude is not finite")
    return snap.ahrs_att


def require_local_height(snap: NavSnapshot, what: str) -> float:
    if not snap.h_ok or snap.h is None:
        raise AssertionError(f"{what}: local height accessor failed at t={snap.t_us}")
    return snap.h


def require_ellipsoid(snap: NavSnapshot, what: str) -> float:
    if not snap.ell_ok or snap.ell is None:
        raise AssertionError(f"{what}: ellipsoid height accessor failed at t={snap.t_us}")
    return snap.ell


def require_unpublished_ellipsoid(snap: NavSnapshot, what: str) -> None:
    if snap.ell_ok or snap.ell is not None:
        raise AssertionError(
            f"{what}: ellipsoid height was published at t={snap.t_us} value={snap.ell}"
        )


def indoor_ellipsoid_matches_init_origin(snap: NavSnapshot, origin_h_m: float) -> bool:
    """True when a published ellipsoid height is the prescribed init origin height.

    PRD's indoor hollow reports that origin as WGS84 ellipsoid height.
    Accessor-fail / NaN / None is not a match. A non-finite published value
    is a probe failure, not absence.
    """
    if not math.isfinite(origin_h_m):
        raise HarnessError(f"prescribed init origin height is not finite: {origin_h_m}")
    if not snap.ell_ok and snap.ell is None:
        return False
    if snap.ell is None or not math.isfinite(snap.ell):
        raise HarnessError(
            f"indoor ellipsoid marked published without a finite value: "
            f"ell_ok={snap.ell_ok} ell={snap.ell}"
        )
    scale = max(abs(origin_h_m), 8.0)
    return abs(snap.ell - origin_h_m) < 0.45 * scale


def require_indoor_ellipsoid_not_init_origin(
    snap: NavSnapshot, origin_h_m: float, what: str
) -> None:
    """indoor run does not report the prescribed init origin as WGS84 ellipsoid height."""
    print(
        f"{what}: ell_ok={snap.ell_ok} ell={snap.ell} init_origin_h={origin_h_m}",
        flush=True,
    )
    if indoor_ellipsoid_matches_init_origin(snap, origin_h_m):
        raise AssertionError(
            f"{what}: indoor ellipsoid {snap.ell} is the prescribed init origin height {origin_h_m}"
        )


def py_mode(snap: NavSnapshot, what: str) -> str:
    """Mode name: Python mode_name(), or the C mode read through the
    published nav_suite_mode_t constants."""
    if snap.mode_name is None:
        raise HarnessError(f"{what}: snapshot has no mode name")
    return snap.mode_name


def site_nav(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    epochs: list[NavEpoch],
    **kwargs,
) -> NavScenario:
    return NavScenario(
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        h_m=h_m,
        epochs=epochs,
        **kwargs,
    )


def mag_body(
    lat_deg: float,
    lon_deg: float,
    yaw_rad: float = 0.0,
    *,
    roll: float = 0.0,
    pitch: float = 0.0,
) -> tuple[float, float, float]:
    ned = ned_field_from_independent_wmm(lat_deg, lon_deg, MAG_YEAR)
    return body_mag_for_yaw(roll, pitch, yaw_rad, ned)


def nav_epoch(t_us: int, **kwargs) -> NavEpoch:
    acc = kwargs.pop("acc", SPECIFIC_FORCE_LEVEL)
    gyr = kwargs.pop("gyr", (0.0, 0.0, 0.0))
    return NavEpoch(
        t_us=t_us,
        acc=(float(acc[0]), float(acc[1]), float(acc[2])),
        gyr=(float(gyr[0]), float(gyr[1]), float(gyr[2])),
        **kwargs,
    )


def nav_append(
    epochs: list[NavEpoch],
    *,
    duration_s: float,
    gnss_ecef: Sequence[float] | None = None,
    gnss_std: Sequence[float] | None = GNSS_STD_M,
    gnss_vel: Sequence[float] | None = ZERO_VEL,
    gnss_vel_std: Sequence[float] | None = ENTRY_VEL_STD,
    imu_hz: int = IMU_HZ,
    gnss_hz: int = GNSS_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    mag: Sequence[float] | None = None,
    baro_pa: float | None = None,
    local_ned: Sequence[float] | None = None,
    local_std: Sequence[float] | None = None,
    local_hz: int = LOCAL_HZ,
    yaw_rad: float | None = None,
    yaw_std: float | None = None,
    zupt: bool = False,
    zaru: bool = False,
    step: bool = True,
    gnss_at=None,
    local_at=None,
    baro_at=None,
    mag_at=None,
) -> list[NavEpoch]:
    if duration_s <= 0.0:
        raise HarnessError("stream duration must be positive")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    if n <= 0:
        raise HarnessError("stream produced no epochs")
    every = _every(imu_hz, gnss_hz) if (gnss_ecef is not None or gnss_at is not None) else None
    local_every = _every(imu_hz, local_hz) if (local_ned is not None or local_at is not None) else None
    t0 = epochs[-1].t_us if epochs else 0
    out = list(epochs)
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        ecef = None
        std = None
        vel = None
        vstd = None
        if every is not None and i % every == 0:
            if gnss_at is not None:
                ecef, std, vel, vstd = gnss_at(t_us, i)
            else:
                ecef = tuple(gnss_ecef) if gnss_ecef is not None else None
                std = tuple(gnss_std) if gnss_std is not None else None
                vel = tuple(gnss_vel) if gnss_vel is not None else None
                vstd = (
                    tuple(gnss_vel_std)
                    if (gnss_vel is not None and gnss_vel_std is not None)
                    else None
                )
        loc = None
        lstd = None
        if local_every is not None and i % local_every == 0:
            if local_at is not None:
                loc, lstd = local_at(t_us, i)
            else:
                loc = tuple(local_ned) if local_ned is not None else None
                lstd = tuple(local_std) if local_std is not None else None
        pa = baro_at(t_us, i) if baro_at is not None else baro_pa
        mag_s = mag_at(t_us, i) if mag_at is not None else (tuple(mag) if mag is not None else None)
        out.append(
            nav_epoch(
                t_us,
                dt_sec=dt,
                acc=acc,
                gyr=gyr,
                gnss_ecef=ecef,
                gnss_std=std,
                gnss_vel=vel,
                gnss_vel_std=vstd,
                mag=mag_s,
                baro_pa=pa,
                local_ned=loc,
                local_std=lstd,
                yaw_rad=yaw_rad,
                yaw_std=yaw_std if yaw_rad is not None else None,
                zupt=zupt,
                zaru=zaru,
                step=step,
            )
        )
    return out


def pad_full(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    origin: Sequence[float],
    *,
    duration_s: float = HAPPY_DURATION_S,
    baro: bool = True,
    mag: bool = True,
    mag_yaw: float = 0.0,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_ecef: Sequence[float] | None = None,
    gnss_std: Sequence[float] = GNSS_STD_M,
    yaw_rad: float | None = None,
    baro_h_m: float | None = None,
) -> list[NavEpoch]:
    fix = tuple(gnss_ecef) if gnss_ecef is not None else tuple(origin)
    pa = None
    if baro:
        href = h_m if baro_h_m is None else float(baro_h_m)
        pa = tropospheric_isa_pressure_pa(href)
    mag_s = mag_body(lat_deg, lon_deg, mag_yaw) if mag else None
    return nav_append(
        [],
        duration_s=duration_s,
        gnss_ecef=fix,
        gnss_std=gnss_std,
        acc=acc,
        gyr=gyr,
        mag=mag_s,
        baro_pa=pa,
        yaw_rad=yaw_rad,
        yaw_std=YAW_AID_STD if yaw_rad is not None else None,
    )


def imu_only(
    epochs: list[NavEpoch],
    *,
    duration_s: float,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    mag: Sequence[float] | None = None,
    baro_pa: float | None = None,
    yaw_rad: float | None = None,
    zupt: bool = False,
    zaru: bool = False,
    step: bool = True,
) -> list[NavEpoch]:
    return nav_append(
        epochs,
        duration_s=duration_s,
        gnss_ecef=None,
        acc=acc,
        gyr=gyr,
        mag=mag,
        baro_pa=baro_pa,
        yaw_rad=yaw_rad,
        yaw_std=YAW_AID_STD if yaw_rad is not None else None,
        zupt=zupt,
        zaru=zaru,
        step=step,
    )


def with_steps(epochs: list[NavEpoch], step: bool) -> list[NavEpoch]:
    return [replace(e, step=step) for e in epochs]


def runtime_second_site() -> tuple[float, float, float]:
    lat, lon, h = runtime_site()
    lat2 = lat + 1.3 if lat < 45.0 else lat - 1.3
    lon2 = lon - 2.7
    h2 = h + 35.0
    print(f"runtime second site lat={lat2} lon={lon2} h={h2}", flush=True)
    return lat2, lon2, h2


def runtime_mocap_delta_m() -> float:
    """Centimetre-scale north step, fusion-usable at 1 cm 1-sigma (not a skip)."""
    u = runtime_uuid_int()
    dn = 0.028 + (u % 12) / 1000.0
    print(f"runtime mocap delta north={dn}", flush=True)
    return float(dn)


def runtime_mag_offset_rad() -> float:
    u = runtime_uuid_int()
    yaw = 0.70 + (u % 90) / 100.0
    print(f"runtime mag offset rad={yaw}", flush=True)
    return float(yaw)


def ecef_err_m(got: Sequence[float], fix: Sequence[float]) -> float:
    err = hypot3(got, fix)
    if not math.isfinite(err):
        raise HarnessError("ECEF error is not finite")
    return err


def later_fix_ecef(
    origin: Sequence[float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Runtime NED offset applied to a GNSS ECEF (PRD later-fix).

    Uses the sealed post-ready GNSS step so a 2 m 1-sigma fix remains
    fusion-usable, while staying well off the origin and above ECEF_MATCH_M.
    """
    dn, de, dd = runtime_gnss_step_m()
    dn = 2.2 + abs(dn) * 0.2
    if dn > 3.2:
        dn = 3.2
    fix = ecef_plus_ned(origin, dn, de, dd)
    print(f"later fix NED n={dn} e={de} d={dd}", flush=True)
    return fix, (dn, de, dd)


def imu_only_after_door(
    epochs: list[NavEpoch],
    *,
    force_s: float,
    acc: Sequence[float] = ABSURD_NORTH_ACC,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    mag: Sequence[float] | None = None,
    baro_pa: float | None = None,
) -> tuple[list[NavEpoch], int]:
    """Level IMU through the 2 s FULL door, then apply `acc` only while already COASTING."""
    door = imu_only(
        epochs,
        duration_s=AIDING_JUST_OVER_S,
        mag=mag,
        baro_pa=baro_pa,
        gyr=gyr,
    )
    t_door = door[-1].t_us
    forced = imu_only(
        door,
        duration_s=force_s,
        acc=acc,
        gyr=gyr,
        mag=mag,
        baro_pa=baro_pa,
    )
    return forced, t_door
