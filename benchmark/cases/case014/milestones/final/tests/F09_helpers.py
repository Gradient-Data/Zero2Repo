# feature: F09
"""Observation helpers for FP-09 input sanitization, outliers, and fail-safe.

C probes compile through the sealed harness. Python observations run in a
child interpreter. This module does not import the product in the pytest
process. Expected ECEF comes from the GNSS the test fed (sealed WGS84).
Barometric short-window direction uses the sealed tropospheric ISA.
Heading contrasts use already-published yaw, never an internal gate table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from _harness import (
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
from F01_helpers import hypot3, require_probe_success
from F02_helpers import (
    DT_SEC,
    ECEF_MATCH_M,
    GNSS_HZ,
    GNSS_STD_M,
    HAPPY_DURATION_S,
    IMU_HZ,
    LONG_TIMEOUT,
    SPECIFIC_FORCE_LEVEL,
    _ecef_to_geodetic,
    _parse_flag,
    _parse_int,
    ecef_from_llh_deg,
    ecef_plus_ned,
)
from F03_helpers import (
    G_MPS2,
    WMM_YEAR as _WMM_YEAR,
    angle_diff_rad,
    ned_field_from_independent_wmm as _ned_field_from_independent_wmm,
    still_level_acc,
)
from F06_helpers import ahrs_std
from F07_helpers import level_quat

HYGIENE_TIMEOUT = LONG_TIMEOUT
SHORT_WINDOW_S = 2.0
LONG_WINDOW_S = 7.0
ABSURD_NORTH_ACC = (3.2, 0.0, -G_MPS2)
ABSURD_Z_RATE_RPS = 0.55
LARGE_IMU_PSD = 40.0
YAW_TIGHT_STD_RAD = math.radians(1.2)
MAG_VAR = (1.0, 1.0, 1.0)
LOCAL_STD_M = (0.03, 0.03, 0.03)
SPEED_STD_MPS = 0.15
CANNED_ORIGIN = (0.0, 0.0, 0.0)
EARTH_RADIUS_M = 6.0e6
# Fuse magnetometer every sample (C: negative delay; not the 1 Hz default).
MAG_EVERY_SAMPLE_MS = -1

_C_PROBE = r"""
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "ins.h"
#include "ahrs.h"
#include "baro_alt.h"
#include "nav_suite.h"

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

static int parse_chi2_token(const char *s, int *omit, float *chi2f)
{
    if (s == NULL) {
        return 0;
    }
    if (strcmp(s, "omit") == 0) {
        *omit = 1;
        *chi2f = 0.0f;
        return 1;
    }
    *omit = 0;
    return parse_f(s, chi2f);
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

static void print_vec_ok(const char *key, int ok, const float *v)
{
    if (ok) {
        printf(" %s=%.9g,%.9g,%.9g", key, v[0], v[1], v[2]);
    } else {
        printf(" %s=-", key);
    }
}

static void print_ins_snap(const ins_t *f, long long t_us)
{
    double ecef[3];
    float ned[3], vel[3], roll, pitch, yaw, bacc[3], bgyr[3];
    int pos = ins_get_position_ecef(f, ecef) ? 1 : 0;
    int vel_ok = ins_get_velocity_ned(f, vel) ? 1 : 0;
    int rpy_ok = ins_get_rpy(f, &roll, &pitch, &yaw) ? 1 : 0;
    int ned_ok = ins_get_position_local(f, ned) ? 1 : 0;
    int bacc_ok = ins_get_bias_acc(f, bacc) ? 1 : 0;
    int bgyr_ok = ins_get_bias_gyr(f, bgyr) ? 1 : 0;
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
    print_vec_ok("nedpos", ned_ok, ned);
    print_vec_ok("velned", vel_ok, vel);
    if (rpy_ok) {
        printf(" att=%.9g,%.9g,%.9g", roll, pitch, yaw);
    } else {
        printf(" att=-");
    }
    print_vec_ok("biasacc", bacc_ok, bacc);
    print_vec_ok("biasgyr", bgyr_ok, bgyr);
    printf(" n_invalid=%u n_downweighted=%u n_gate=%u n_fusion=%u n_time=%u n_auto_zupt=%u\n",
           d->n_invalid_input, d->n_downweighted, d->n_gnss_rejected_noise,
           d->n_fuse_fail, d->n_time_backward, d->n_auto_zupt);
}

static int fill_meas(ins_measurements_t *m, char **tok, int n)
{
    if (n != 72) {
        return 0;
    }
    memset(m, 0, sizeof *m);
    long long t_us = 0;
    double dt;
    float ax, ay, az, gx, gy, gz, av, gv;
    float ap0, ap1, ap2, gp0, gp1, gp2;
    float gpf, sn, se, sd, velf, vn, ve, vd, vsn, vse, vsd;
    float mgf, mx, my, mz, mvx, mvy, mvz;
    float ywf, yaw, ystd, lpf, ln, le, ld, lsn, lse, lsd;
    float spf, speed, sstd, brf, pa, zuptf, zaruf;
    float lx, ly, lz, xcf, brokenf, qne, qnd, qed;
    double e0, e1, e2;
    float xc[9];
    int i;
    if (!parse_ll(tok[1], &t_us) || !parse_d(tok[2], &dt) ||
        !parse_f(tok[3], &ax) || !parse_f(tok[4], &ay) || !parse_f(tok[5], &az) ||
        !parse_f(tok[6], &gx) || !parse_f(tok[7], &gy) || !parse_f(tok[8], &gz) ||
        !parse_f(tok[9], &av) || !parse_f(tok[10], &gv) ||
        !parse_f(tok[11], &ap0) || !parse_f(tok[12], &ap1) || !parse_f(tok[13], &ap2) ||
        !parse_f(tok[14], &gp0) || !parse_f(tok[15], &gp1) || !parse_f(tok[16], &gp2) ||
        !parse_f(tok[17], &gpf) || !parse_d(tok[18], &e0) || !parse_d(tok[19], &e1) ||
        !parse_d(tok[20], &e2) || !parse_f(tok[21], &sn) || !parse_f(tok[22], &se) ||
        !parse_f(tok[23], &sd) || !parse_f(tok[24], &velf) || !parse_f(tok[25], &vn) ||
        !parse_f(tok[26], &ve) || !parse_f(tok[27], &vd) || !parse_f(tok[28], &vsn) ||
        !parse_f(tok[29], &vse) || !parse_f(tok[30], &vsd) || !parse_f(tok[31], &mgf) ||
        !parse_f(tok[32], &mx) || !parse_f(tok[33], &my) || !parse_f(tok[34], &mz) ||
        !parse_f(tok[35], &mvx) || !parse_f(tok[36], &mvy) || !parse_f(tok[37], &mvz) ||
        !parse_f(tok[38], &ywf) || !parse_f(tok[39], &yaw) || !parse_f(tok[40], &ystd) ||
        !parse_f(tok[41], &lpf) || !parse_f(tok[42], &ln) || !parse_f(tok[43], &le) ||
        !parse_f(tok[44], &ld) || !parse_f(tok[45], &lsn) || !parse_f(tok[46], &lse) ||
        !parse_f(tok[47], &lsd) || !parse_f(tok[48], &spf) || !parse_f(tok[49], &speed) ||
        !parse_f(tok[50], &sstd) || !parse_f(tok[51], &brf) || !parse_f(tok[52], &pa) ||
        !parse_f(tok[53], &zuptf) || !parse_f(tok[54], &zaruf) ||
        !parse_f(tok[55], &lx) || !parse_f(tok[56], &ly) || !parse_f(tok[57], &lz) ||
        !parse_f(tok[58], &xcf) || !parse_f(tok[68], &brokenf) ||
        !parse_f(tok[69], &qne) || !parse_f(tok[70], &qnd) || !parse_f(tok[71], &qed)) {
        return 0;
    }
    for (i = 0; i < 9; i++) {
        if (!parse_f(tok[59 + i], &xc[i])) {
            return 0;
        }
    }
    m->timestamp = (ins_time_us_t)t_us;
    m->strapdown_dt_sec = (float)dt;
    m->acc.is_valid = ((int)av) ? true : false;
    m->gyr.is_valid = ((int)gv) ? true : false;
    m->acc.data[0] = ax;
    m->acc.data[1] = ay;
    m->acc.data[2] = az;
    m->gyr.data[0] = gx;
    m->gyr.data[1] = gy;
    m->gyr.data[2] = gz;
    m->acc.Qll_diag[0] = ap0;
    m->acc.Qll_diag[1] = ap1;
    m->acc.Qll_diag[2] = ap2;
    m->gyr.Qll_diag[0] = gp0;
    m->gyr.Qll_diag[1] = gp1;
    m->gyr.Qll_diag[2] = gp2;
    if ((int)gpf) {
        m->gnss_pos.is_valid = true;
        m->gnss_pos.xyz_ecef[0] = e0;
        m->gnss_pos.xyz_ecef[1] = e1;
        m->gnss_pos.xyz_ecef[2] = e2;
        m->gnss_pos.Qll_ned[0] = sn * sn;
        m->gnss_pos.Qll_ned[4] = se * se;
        m->gnss_pos.Qll_ned[8] = sd * sd;
        m->gnss_pos.Qll_ned[1] = qne;
        m->gnss_pos.Qll_ned[3] = qne;
        m->gnss_pos.Qll_ned[2] = qnd;
        m->gnss_pos.Qll_ned[6] = qnd;
        m->gnss_pos.Qll_ned[5] = qed;
        m->gnss_pos.Qll_ned[7] = qed;
        if ((int)brokenf) {
            m->gnss_pos.Qll_ned[0] = 0.0f;
        }
    }
    if ((int)velf) {
        m->gnss_vel.is_valid = true;
        m->gnss_vel.vel_ned[0] = vn;
        m->gnss_vel.vel_ned[1] = ve;
        m->gnss_vel.vel_ned[2] = vd;
        m->gnss_vel.Qll_ned[0] = vsn * vsn;
        m->gnss_vel.Qll_ned[4] = vse * vse;
        m->gnss_vel.Qll_ned[8] = vsd * vsd;
    }
    if ((int)mgf) {
        m->mag.is_valid = true;
        m->mag.data[0] = mx;
        m->mag.data[1] = my;
        m->mag.data[2] = mz;
        m->mag.Qll_diag[0] = mvx;
        m->mag.Qll_diag[1] = mvy;
        m->mag.Qll_diag[2] = mvz;
    }
    if ((int)ywf) {
        m->yaw.is_valid = true;
        m->yaw.yaw_rad = yaw;
        m->yaw.stddev_rad = ystd;
    }
    if ((int)lpf) {
        m->local_pos.is_valid = true;
        m->local_pos.pos_ned[0] = ln;
        m->local_pos.pos_ned[1] = le;
        m->local_pos.pos_ned[2] = ld;
        m->local_pos.Qll_ned[0] = lsn * lsn;
        m->local_pos.Qll_ned[4] = lse * lse;
        m->local_pos.Qll_ned[8] = lsd * lsd;
    }
    if ((int)spf) {
        m->speed.is_valid = true;
        m->speed.speed_mps = speed;
        m->speed.stddev_mps = sstd;
    }
    if ((int)brf) {
        m->baro.is_valid = true;
        m->baro.pressure_pa = pa;
    }
    m->zero_velocity_update = ((int)zuptf) ? true : false;
    m->zero_rotation_update = ((int)zaruf) ? true : false;
    m->gnss_leverarm_b[0] = lx;
    m->gnss_leverarm_b[1] = ly;
    m->gnss_leverarm_b[2] = lz;
    if ((int)xcf) {
        for (i = 0; i < 9; i++) {
            m->gnss_Qll_pos_vel_ned[i] = xc[i];
        }
    }
    return 1;
}

static int run_ins(void)
{
    char line[8192];
    char *tok[80];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("ins cfg");
    }
    int n = split_ws(line, tok, 80);
    if (n != 17) {
        return fail_read("ins cfg fields");
    }
    double lat, lon, h, ox, oy, oz, mag0, mag1, mag2, wlat, wlon, wyear;
    float chi2f, zuptf, delayf, wmmf;
    int chi2_omit = 0;
    if (!parse_d(tok[0], &lat) || !parse_d(tok[1], &lon) || !parse_d(tok[2], &h) ||
        !parse_d(tok[3], &ox) || !parse_d(tok[4], &oy) || !parse_d(tok[5], &oz) ||
        !parse_chi2_token(tok[6], &chi2_omit, &chi2f) || !parse_f(tok[7], &zuptf) ||
        !parse_f(tok[8], &delayf) || !parse_d(tok[9], &mag0) ||
        !parse_d(tok[10], &mag1) || !parse_d(tok[11], &mag2) ||
        !parse_f(tok[12], &wmmf) || !parse_d(tok[13], &wlat) ||
        !parse_d(tok[14], &wlon) || !parse_d(tok[15], &wyear)) {
        return fail_read("ins cfg numbers");
    }
    ins_t ins;
    memset(&ins, 0, sizeof ins);
    ins_init_t init;
    memset(&init, 0, sizeof init);
    ins_options_t opt;
    memset(&opt, 0, sizeof opt);
    init.x_ecef[0] = ox;
    init.x_ecef[1] = oy;
    init.x_ecef[2] = oz;
    init.magnetic_n[0] = (float)mag0;
    init.magnetic_n[1] = (float)mag1;
    init.magnetic_n[2] = (float)mag2;
    opt.auto_init = true;
    if (!chi2_omit) {
        opt.chi2_disable = ((int)chi2f) ? true : false;
    }
    opt.auto_zupt_disable = ((int)zuptf) ? true : false;
    opt.magnetometer_min_delay_ms = (int)delayf;
    int rc = ins_init(&ins, &init, &opt);
    printf("INIT rc=%d\n", rc);
    print_ins_snap(&ins, 0);
    if (rc != 0) {
        return 0;
    }
    if ((int)wmmf) {
        ins_set_magnetic_model_from_position(&ins, wlat * M_PI / 180.0,
                                             wlon * M_PI / 180.0, (float)wyear);
    }
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 80);
        if (n < 1 || tok[0][0] != 'E') {
            return fail_read("ins epoch tag");
        }
        ins_measurements_t m;
        if (!fill_meas(&m, tok, n)) {
            return fail_read("ins epoch fields");
        }
        ins_update(&ins, &m);
        print_ins_snap(&ins, (long long)m.timestamp);
    }
    return 0;
}

static int run_ahrs(void)
{
    char line[4096];
    char *tok[24];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("ahrs cfg");
    }
    int n = split_ws(line, tok, 24);
    if (n != 8) {
        return fail_read("ahrs cfg fields");
    }
    long long t_init = 0;
    float chi2f, rpy[3], std[3];
    if (!parse_ll(tok[0], &t_init) || !parse_f(tok[1], &chi2f) ||
        !parse_f(tok[2], &rpy[0]) || !parse_f(tok[3], &rpy[1]) ||
        !parse_f(tok[4], &rpy[2]) || !parse_f(tok[5], &std[0]) ||
        !parse_f(tok[6], &std[1]) || !parse_f(tok[7], &std[2])) {
        return fail_read("ahrs cfg numbers");
    }
    ahrs_t a;
    memset(&a, 0, sizeof a);
    ahrs_config_t cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.mode = AHRS_MODE_AHRS;
    cfg.rpy_init_rad[0] = rpy[0];
    cfg.rpy_init_rad[1] = rpy[1];
    cfg.rpy_init_rad[2] = rpy[2];
    cfg.rpy_init_stddev_rad[0] = std[0];
    cfg.rpy_init_stddev_rad[1] = std[1];
    cfg.rpy_init_stddev_rad[2] = std[2];
    cfg.chi2_disable = ((int)chi2f) ? true : false;
    int rc = ahrs_init(&a, &cfg, (ahrs_time_us_t)t_init);
    printf("INIT rc=%d\n", rc);
    {
        float roll = 0.0f, pitch = 0.0f, yaw = 0.0f;
        int rpy_ok = ahrs_get_rpy(&a, &roll, &pitch, &yaw) ? 1 : 0;
        printf("SNAP t_us=%lld rpy=%d", t_init, rpy_ok);
        if (rpy_ok) {
            printf(" att=%.9g,%.9g,%.9g", roll, pitch, yaw);
        } else {
            printf(" att=-");
        }
        printf(" n_invalid=%u n_downweighted=%u\n", a.n_invalid_input, a.n_downweighted);
    }
    if (rc != 0) {
        return 0;
    }
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 24);
        if (n != 12) {
            return fail_read("ahrs epoch fields");
        }
        long long t_us = 0;
        float ax, ay, az, gx, gy, gz, magf, mx, my, mz;
        if (tok[0][0] != 'E' || !parse_ll(tok[1], &t_us) ||
            !parse_f(tok[2], &ax) || !parse_f(tok[3], &ay) || !parse_f(tok[4], &az) ||
            !parse_f(tok[5], &gx) || !parse_f(tok[6], &gy) || !parse_f(tok[7], &gz) ||
            !parse_f(tok[8], &magf) || !parse_f(tok[9], &mx) ||
            !parse_f(tok[10], &my) || !parse_f(tok[11], &mz)) {
            return fail_read("ahrs epoch numbers");
        }
        float acc[3] = {ax, ay, az};
        float gyr[3] = {gx, gy, gz};
        float mag[3] = {mx, my, mz};
        const float *magp = ((int)magf) ? mag : NULL;
        ahrs_update(&a, (ahrs_time_us_t)t_us, gyr, acc, magp, false);
        float roll = 0.0f, pitch = 0.0f, yaw = 0.0f;
        int rpy_ok = ahrs_get_rpy(&a, &roll, &pitch, &yaw) ? 1 : 0;
        printf("SNAP t_us=%lld rpy=%d", t_us, rpy_ok);
        if (rpy_ok) {
            printf(" att=%.9g,%.9g,%.9g", roll, pitch, yaw);
        } else {
            printf(" att=-");
        }
        printf(" n_invalid=%u n_downweighted=%u\n", a.n_invalid_input, a.n_downweighted);
    }
    return 0;
}

static int run_baro(void)
{
    char line[4096];
    char *tok[20];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("baro cfg");
    }
    int n = split_ws(line, tok, 20);
    if (n != 5) {
        return fail_read("baro cfg fields");
    }
    long long t_init = 0;
    float chi2f, pressure, h_init, h_std;
    if (!parse_ll(tok[0], &t_init) || !parse_f(tok[1], &chi2f) ||
        !parse_f(tok[2], &pressure) || !parse_f(tok[3], &h_init) ||
        !parse_f(tok[4], &h_std)) {
        return fail_read("baro cfg numbers");
    }
    baro_alt_t b;
    memset(&b, 0, sizeof b);
    baro_alt_config_t cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.chi2_disable = ((int)chi2f) ? true : false;
    int rc = baro_alt_init(&b, &cfg, (baro_alt_time_us_t)t_init, pressure, h_init,
                           h_std);
    printf("INIT rc=%d\n", rc);
    {
        float h = 0.0f;
        int h_ok = baro_alt_get_height(&b, &h) ? 1 : 0;
        printf("SNAP t_us=%lld h_ok=%d", t_init, h_ok);
        if (h_ok) {
            printf(" h=%.9g", h);
        } else {
            printf(" h=-");
        }
        printf(" n_invalid=%u n_downweighted=%u\n", b.n_invalid_input, b.n_downweighted);
    }
    if (rc != 0) {
        return 0;
    }
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 20);
        if (n != 12) {
            return fail_read("baro epoch fields");
        }
        long long t_us = 0;
        float ax, ay, az, qw, qx, qy, qz, p, barof;
        if (tok[0][0] != 'E' || !parse_ll(tok[1], &t_us) ||
            !parse_f(tok[2], &ax) || !parse_f(tok[3], &ay) || !parse_f(tok[4], &az) ||
            !parse_f(tok[5], &qw) || !parse_f(tok[6], &qx) || !parse_f(tok[7], &qy) ||
            !parse_f(tok[8], &qz) || !parse_f(tok[9], &p) || !parse_f(tok[10], &barof)) {
            return fail_read("baro epoch numbers");
        }
        (void)tok[11];
        float acc[3] = {ax, ay, az};
        float q[4] = {qw, qx, qy, qz};
        baro_alt_update(&b, (baro_alt_time_us_t)t_us, acc, q, p, 0.0f,
                        ((int)barof) ? true : false);
        float h = 0.0f;
        int h_ok = baro_alt_get_height(&b, &h) ? 1 : 0;
        printf("SNAP t_us=%lld h_ok=%d", t_us, h_ok);
        if (h_ok) {
            printf(" h=%.9g", h);
        } else {
            printf(" h=-");
        }
        printf(" n_invalid=%u n_downweighted=%u\n", b.n_invalid_input, b.n_downweighted);
    }
    return 0;
}

static int run_suite(void)
{
    char line[8192];
    char *tok[80];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("suite cfg");
    }
    int n = split_ws(line, tok, 80);
    if (n != 17) {
        return fail_read("suite cfg fields");
    }
    double lat, lon, h, ox, oy, oz, mag0, mag1, mag2, wlat, wlon, wyear;
    float chi2f, zuptf, delayf, wmmf;
    int chi2_omit = 0;
    if (!parse_d(tok[0], &lat) || !parse_d(tok[1], &lon) || !parse_d(tok[2], &h) ||
        !parse_d(tok[3], &ox) || !parse_d(tok[4], &oy) || !parse_d(tok[5], &oz) ||
        !parse_chi2_token(tok[6], &chi2_omit, &chi2f) || !parse_f(tok[7], &zuptf) ||
        !parse_f(tok[8], &delayf) || !parse_d(tok[9], &mag0) ||
        !parse_d(tok[10], &mag1) || !parse_d(tok[11], &mag2) ||
        !parse_f(tok[12], &wmmf) || !parse_d(tok[13], &wlat) ||
        !parse_d(tok[14], &wlon) || !parse_d(tok[15], &wyear)) {
        return fail_read("suite cfg numbers");
    }
    (void)delayf;
    (void)wmmf;
    (void)wlat;
    (void)wlon;
    (void)wyear;
    nav_suite_t s;
    memset(&s, 0, sizeof s);
    ins_init_t init;
    memset(&init, 0, sizeof init);
    ins_options_t opt;
    memset(&opt, 0, sizeof opt);
    init.x_ecef[0] = ox;
    init.x_ecef[1] = oy;
    init.x_ecef[2] = oz;
    init.magnetic_n[0] = (float)mag0;
    init.magnetic_n[1] = (float)mag1;
    init.magnetic_n[2] = (float)mag2;
    opt.auto_init = true;
    if (!chi2_omit) {
        opt.chi2_disable = ((int)chi2f) ? true : false;
    }
    opt.auto_zupt_disable = ((int)zuptf) ? true : false;
    int rc = nav_suite_init(&s, &init, &opt);
    printf("INIT rc=%d\n", rc);
    {
        const ins_diag_t *d = ins_get_diag(&s.ins);
        if (d == NULL) {
            fprintf(stderr, "suite diag query failed\n");
            return 2;
        }
        double ecef[3];
        float roll, pitch, yaw, hgt = 0.0f;
        int pos = ins_get_position_ecef(&s.ins, ecef) ? 1 : 0;
        int rpy_ok = nav_suite_get_rpy(&s, &roll, &pitch, &yaw) ? 1 : 0;
        int h_ok = nav_suite_get_height(&s, &hgt) ? 1 : 0;
        printf("SNAP t_us=0 ready=%d pos=%d rpy=%d", ins_is_ready(&s.ins) ? 1 : 0, pos,
               rpy_ok);
        if (pos) {
            printf(" ecef=%.17g,%.17g,%.17g", ecef[0], ecef[1], ecef[2]);
        } else {
            printf(" ecef=-");
        }
        if (rpy_ok) {
            printf(" att=%.9g,%.9g,%.9g", roll, pitch, yaw);
        } else {
            printf(" att=-");
        }
        printf(" h_ok=%d", h_ok);
        if (h_ok) {
            printf(" h=%.9g", hgt);
        } else {
            printf(" h=-");
        }
        printf(" n_invalid=%u n_downweighted=%u n_gate=%u n_fusion=%u n_time=%u n_auto_zupt=%u\n",
               d->n_invalid_input, d->n_downweighted, d->n_gnss_rejected_noise,
               d->n_fuse_fail, d->n_time_backward, d->n_auto_zupt);
    }
    if (rc != 0) {
        return 0;
    }
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 80);
        if (n < 1 || tok[0][0] != 'E') {
            return fail_read("suite epoch tag");
        }
        ins_measurements_t m;
        if (!fill_meas(&m, tok, n)) {
            return fail_read("suite epoch fields");
        }
        nav_suite_update(&s, &m);
        const ins_diag_t *d = ins_get_diag(&s.ins);
        if (d == NULL) {
            fprintf(stderr, "suite diag query failed\n");
            return 2;
        }
        double ecef[3];
        float roll, pitch, yaw, hgt = 0.0f;
        int pos = ins_get_position_ecef(&s.ins, ecef) ? 1 : 0;
        int rpy_ok = nav_suite_get_rpy(&s, &roll, &pitch, &yaw) ? 1 : 0;
        int h_ok = nav_suite_get_height(&s, &hgt) ? 1 : 0;
        printf("SNAP t_us=%lld ready=%d pos=%d rpy=%d", (long long)m.timestamp,
               ins_is_ready(&s.ins) ? 1 : 0, pos, rpy_ok);
        if (pos) {
            printf(" ecef=%.17g,%.17g,%.17g", ecef[0], ecef[1], ecef[2]);
        } else {
            printf(" ecef=-");
        }
        if (rpy_ok) {
            printf(" att=%.9g,%.9g,%.9g", roll, pitch, yaw);
        } else {
            printf(" att=-");
        }
        printf(" h_ok=%d", h_ok);
        if (h_ok) {
            printf(" h=%.9g", hgt);
        } else {
            printf(" h=-");
        }
        printf(" n_invalid=%u n_downweighted=%u n_gate=%u n_fusion=%u n_time=%u n_auto_zupt=%u\n",
               d->n_invalid_input, d->n_downweighted, d->n_gnss_rejected_noise,
               d->n_fuse_fail, d->n_time_backward, d->n_auto_zupt);
    }
    return 0;
}

int main(void)
{
    char line[256];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("kind");
    }
    if (strncmp(line, "INS", 3) == 0) {
        return run_ins();
    }
    if (strncmp(line, "AHRS", 4) == 0) {
        return run_ahrs();
    }
    if (strncmp(line, "BARO", 4) == 0) {
        return run_baro();
    }
    if (strncmp(line, "SUITE", 5) == 0) {
        return run_suite();
    }
    return fail_read("kind token");
}
"""

_PY_INS_PROBE = r"""
import math
import sys

from __PKG__ import Config, Ins

def tok_float(s):
    return float(s)

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
    pos = 1 if ecef is not None else 0
    vel_ok = 1 if vel is not None else 0
    rpy_ok = 1 if rpy is not None else 0
    ned_ok = 1 if ned is not None else 0
    bacc_ok = 1 if bacc is not None else 0
    bgyr_ok = 1 if bgyr is not None else 0
    def fmt(ok, vec):
        if not ok or vec is None:
            return "-"
        return "%.17g,%.17g,%.17g" % tuple(vec)
    n_invalid = _cnt(diag, "n_invalid_input")
    n_dw = _cnt(diag, "n_downweighted")
    n_gate = _cnt(diag, "n_gnss_rejected_noise")
    n_fusion = _cnt(diag, "n_fuse_fail")
    n_time = _cnt(diag, "n_time_backward")
    n_auto = _cnt(diag, "n_auto_zupt")
    line = (
        "SNAP t_us=%d ready=%d pos=%d vel=%d rpy=%d ned=%d bacc=%d bgyr=%d"
        % (t_us, ready, pos, vel_ok, rpy_ok, ned_ok, bacc_ok, bgyr_ok)
    )
    line += " ecef=" + (fmt(pos, ecef) if pos else "-")
    line += " nedpos=" + fmt(ned_ok, ned)
    line += " velned=" + fmt(vel_ok, vel)
    line += " att=" + fmt(rpy_ok, rpy)
    line += " biasacc=" + fmt(bacc_ok, bacc)
    line += " biasgyr=" + fmt(bgyr_ok, bgyr)
    line += " n_invalid=%d n_downweighted=%d n_gate=%d n_fusion=%d n_time=%d n_auto_zupt=%d" % (
        n_invalid, n_dw, n_gate, n_fusion, n_time, n_auto,
    )
    print(line)

kind = sys.stdin.readline()
if not kind or not kind.startswith("INS"):
    raise SystemExit("kind")
cfg_line = sys.stdin.readline()
if not cfg_line:
    raise SystemExit("missing cfg")
parts = cfg_line.split()
if len(parts) != 17:
    raise SystemExit("cfg fields")
lat, lon, h = [float(x) for x in parts[0:3]]
ox, oy, oz = [float(x) for x in parts[3:6]]
chi2_omit = parts[6] == "omit"
zupt_off = int(float(parts[7]))
delay = int(float(parts[8]))
mag_n = (float(parts[9]), float(parts[10]), float(parts[11]))
wmm = int(float(parts[12]))
wlat, wlon, wyear = [float(x) for x in parts[13:16]]
cfg_kw = dict(
    auto_init=True,
    lat_rad=math.radians(lat),
    lon_rad=math.radians(lon),
    h_m=h,
    auto_zupt_disable=bool(zupt_off),
    magnetometer_min_delay_ms=delay,
    magnetic_n=mag_n,
)
if not chi2_omit:
    cfg_kw["chi2_disable"] = bool(int(float(parts[6])))
try:
    nav = Ins(Config(**cfg_kw))
except ValueError:
    print("INIT rc=-1")
    print(
        "SNAP t_us=0 ready=0 pos=0 vel=0 rpy=0 ned=0 bacc=0 bgyr=0 "
        "ecef=- nedpos=- velned=- att=- biasacc=- biasgyr=- "
        "n_invalid=0 n_downweighted=0 n_gate=0 n_fusion=0 n_time=0 n_auto_zupt=0"
    )
    raise SystemExit(0)
print("INIT rc=0")
_ = (ox, oy, oz)
if wmm:
    nav.set_magnetic_model(math.radians(wlat), math.radians(wlon), wyear)
emit(nav, 0)
for raw in sys.stdin:
    if not raw.strip() or raw.startswith("#"):
        continue
    tok = raw.split()
    if tok[0] != "E" or len(tok) != 72:
        raise SystemExit("epoch fields %d" % len(tok))
    t_us = int(tok[1])
    dt = float(tok[2])
    acc = (tok_float(tok[3]), tok_float(tok[4]), tok_float(tok[5]))
    gyr = (tok_float(tok[6]), tok_float(tok[7]), tok_float(tok[8]))
    acc_psd = (tok_float(tok[11]), tok_float(tok[12]), tok_float(tok[13]))
    gyr_psd = (tok_float(tok[14]), tok_float(tok[15]), tok_float(tok[16]))
    gp = int(float(tok[17]))
    ecef = (tok_float(tok[18]), tok_float(tok[19]), tok_float(tok[20]))
    std = (tok_float(tok[21]), tok_float(tok[22]), tok_float(tok[23]))
    gv = int(float(tok[24]))
    vel = (tok_float(tok[25]), tok_float(tok[26]), tok_float(tok[27]))
    vstd = (tok_float(tok[28]), tok_float(tok[29]), tok_float(tok[30]))
    mg = int(float(tok[31]))
    mag = (tok_float(tok[32]), tok_float(tok[33]), tok_float(tok[34]))
    mvar = (tok_float(tok[35]), tok_float(tok[36]), tok_float(tok[37]))
    yw = int(float(tok[38]))
    yaw = tok_float(tok[39])
    ystd = tok_float(tok[40])
    lp = int(float(tok[41]))
    local = (tok_float(tok[42]), tok_float(tok[43]), tok_float(tok[44]))
    lstd = (tok_float(tok[45]), tok_float(tok[46]), tok_float(tok[47]))
    sp = int(float(tok[48]))
    speed = tok_float(tok[49])
    sstd = tok_float(tok[50])
    br = int(float(tok[51]))
    pa = tok_float(tok[52])
    zupt = int(float(tok[53]))
    zaru = int(float(tok[54]))
    lever = (tok_float(tok[55]), tok_float(tok[56]), tok_float(tok[57]))
    xcflag = int(float(tok[58]))
    xc = [tok_float(tok[59 + i]) for i in range(9)]
    broken = int(float(tok[68]))
    qne = tok_float(tok[69])
    qnd = tok_float(tok[70])
    qed = tok_float(tok[71])
    nav.imu(t_us, dt, acc, gyr, acc_var=acc_psd, gyr_var=gyr_psd)
    if gp:
        nn = 0.0 if broken else std[0] * std[0]
        ee = std[1] * std[1]
        dd = std[2] * std[2]
        nav.gnss_pos(
            ecef,
            [
                [nn, qne, qnd],
                [qne, ee, qed],
                [qnd, qed, dd],
            ],
        )
    if gv:
        varv = (vstd[0] * vstd[0], vstd[1] * vstd[1], vstd[2] * vstd[2])
        nav.gnss_vel(vel, varv)
    if xcflag:
        cov = [xc[i] for i in range(9)]
        nav.gnss_pos_vel_cov(
            [
                [cov[0], cov[1], cov[2]],
                [cov[3], cov[4], cov[5]],
                [cov[6], cov[7], cov[8]],
            ]
        )
    if lever != (0.0, 0.0, 0.0) or any(not math.isfinite(v) for v in lever):
        nav.gnss_leverarm(lever)
    if mg:
        nav.mag(mag, mvar)
    if yw:
        nav.yaw(yaw, ystd)
    if lp:
        varl = (lstd[0] * lstd[0], lstd[1] * lstd[1], lstd[2] * lstd[2])
        nav.local_pos(local, varl)
    if sp:
        nav.speed(speed, sstd)
    if br:
        nav.baro(pa)
    if zupt:
        nav.zupt(True)
    if zaru:
        nav.zaru(True)
    nav.update()
    emit(nav, t_us)
"""

_PY_SUITE_PROBE = r"""
import math
import sys

from __PKG__ import Config, Navigator

def tok_float(s):
    return float(s)

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
    rpy = nav.rpy()
    diag = nav.diag()
    pos = 1 if ecef is not None else 0
    rpy_ok = 1 if rpy is not None else 0
    n_invalid = _cnt(diag, "n_invalid_input")
    n_dw = _cnt(diag, "n_downweighted")
    n_gate = _cnt(diag, "n_gnss_rejected_noise")
    n_fusion = _cnt(diag, "n_fuse_fail")
    n_time = _cnt(diag, "n_time_backward")
    n_auto = _cnt(diag, "n_auto_zupt")
    h = nav.height()
    h_ok = 1 if h is not None else 0
    line = "SNAP t_us=%d ready=%d pos=%d rpy=%d" % (t_us, ready, pos, rpy_ok)
    if pos:
        line += " ecef=%.17g,%.17g,%.17g" % tuple(ecef)
    else:
        line += " ecef=-"
    if rpy_ok:
        line += " att=%.9g,%.9g,%.9g" % tuple(rpy)
    else:
        line += " att=-"
    line += " h_ok=%d" % h_ok
    if h_ok:
        line += " h=%.9g" % h
    else:
        line += " h=-"
    line += " n_invalid=%d n_downweighted=%d n_gate=%d n_fusion=%d n_time=%d n_auto_zupt=%d" % (
        n_invalid, n_dw, n_gate, n_fusion, n_time, n_auto,
    )
    print(line)

kind = sys.stdin.readline()
if not kind or not kind.startswith("SUITE"):
    raise SystemExit("kind")
cfg_line = sys.stdin.readline()
if not cfg_line:
    raise SystemExit("missing cfg")
parts = cfg_line.split()
if len(parts) != 17:
    raise SystemExit("cfg fields")
lat, lon, h = [float(x) for x in parts[0:3]]
chi2_omit = parts[6] == "omit"
zupt_off = int(float(parts[7]))
delay = int(float(parts[8]))
mag_n = (float(parts[9]), float(parts[10]), float(parts[11]))
cfg_kw = dict(
    auto_init=True,
    lat_rad=math.radians(lat),
    lon_rad=math.radians(lon),
    h_m=h,
    auto_zupt_disable=bool(zupt_off),
    magnetometer_min_delay_ms=delay,
    magnetic_n=mag_n,
)
if not chi2_omit:
    cfg_kw["chi2_disable"] = bool(int(float(parts[6])))
try:
    nav = Navigator(Config(**cfg_kw))
except ValueError:
    print("INIT rc=-1")
    print(
        "SNAP t_us=0 ready=0 pos=0 rpy=0 ecef=- att=- h_ok=0 h=- "
        "n_invalid=0 n_downweighted=0 n_gate=0 n_fusion=0 n_time=0 n_auto_zupt=0"
    )
    raise SystemExit(0)
print("INIT rc=0")
emit(nav, 0)
for raw in sys.stdin:
    if not raw.strip() or raw.startswith("#"):
        continue
    tok = raw.split()
    if tok[0] != "E" or len(tok) != 72:
        raise SystemExit("epoch fields")
    t_us = int(tok[1])
    dt = float(tok[2])
    acc = (tok_float(tok[3]), tok_float(tok[4]), tok_float(tok[5]))
    gyr = (tok_float(tok[6]), tok_float(tok[7]), tok_float(tok[8]))
    acc_psd = (tok_float(tok[11]), tok_float(tok[12]), tok_float(tok[13]))
    gyr_psd = (tok_float(tok[14]), tok_float(tok[15]), tok_float(tok[16]))
    gp = int(float(tok[17]))
    ecef = (tok_float(tok[18]), tok_float(tok[19]), tok_float(tok[20]))
    std = (tok_float(tok[21]), tok_float(tok[22]), tok_float(tok[23]))
    broken = int(float(tok[68]))
    nav.imu(t_us, dt, acc, gyr, acc_var=acc_psd, gyr_var=gyr_psd)
    if gp:
        if broken:
            var = (0.0, std[1] * std[1], std[2] * std[2])
        else:
            var = (std[0] * std[0], std[1] * std[1], std[2] * std[2])
        nav.gnss_pos(ecef, var)
    nav.update()
    emit(nav, t_us)
"""


def hygiene_token(v: float) -> str:
    """Encode a float for probe stdin, including non-finite tokens."""
    x = float(v)
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0.0 else "-inf"
    return f"{x:.17g}"


def runtime_outlier_north_m() -> float:
    """Runtime GNSS north offset, hundreds of metres vs the 2 m 1-sigma pad."""
    u = runtime_uuid_int()
    north = 90.0 + (u % 90)
    print(f"runtime outlier north m={north}", flush=True)
    return float(north)


def runtime_local_step_m() -> float:
    """Small persistent local north step: fused, not a high-rate glitch."""
    u = runtime_uuid_int()
    north = 0.08 + (u % 8) / 100.0
    print(f"runtime local step m={north}", flush=True)
    return float(north)


def runtime_local_glitch_ned() -> tuple[float, float, float]:
    """One-sample high-rate local glitch, metres away from a centimetre tracker."""
    u = runtime_uuid_int()
    north = 14.0 + (u % 12)
    east = 8.0 + ((u // 12) % 10)
    down = 3.0 + ((u // 120) % 5)
    print(f"runtime local glitch n={north} e={east} d={down}", flush=True)
    return float(north), float(east), float(down)


def runtime_hygiene_weather_isa_m() -> float:
    """Runtime weather step of tens of metres on the independent ISA."""
    u = runtime_uuid_int()
    h = 28.0 + (u % 40)
    print(f"runtime hygiene weather ISA m={h}", flush=True)
    return float(h)


def runtime_hygiene_cross_vel_mps() -> float:
    """Runtime north velocity large enough that a pos/vel cross-term can move ECEF."""
    u = runtime_uuid_int()
    vn = 2.4 + (u % 16) / 10.0
    print(f"runtime hygiene cross vel mps={vn}", flush=True)
    return float(vn)


def runtime_yaw_outlier_rad(pad_yaw: float) -> float:
    """In-range finite heading far from the pad heading (not a 3-pi wrap)."""
    u = runtime_uuid_int()
    delta = 1.6 + (u % 80) / 100.0
    yaw = pad_yaw + delta
    while yaw > math.pi:
        yaw -= 2.0 * math.pi
    while yaw < -math.pi:
        yaw += 2.0 * math.pi
    if abs(angle_diff_rad(yaw, pad_yaw)) < 1.0:
        yaw = pad_yaw + 2.1
        if yaw > math.pi:
            yaw -= 2.0 * math.pi
    if abs(yaw) < 0.2:
        yaw = 1.4 if pad_yaw < 0.0 else -1.4
    print(f"runtime yaw outlier rad={yaw} pad={pad_yaw}", flush=True)
    return float(yaw)


def _triple(v: Sequence[float] | None, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if v is None:
        return default
    return (float(v[0]), float(v[1]), float(v[2]))


@dataclass
class HygieneEpoch:
    t_us: int
    dt_sec: float = DT_SEC
    acc: tuple[float, float, float] = SPECIFIC_FORCE_LEVEL
    gyr: tuple[float, float, float] = (0.0, 0.0, 0.0)
    acc_valid: bool = True
    gyr_valid: bool = True
    acc_psd: tuple[float, float, float] = (0.0, 0.0, 0.0)
    gyr_psd: tuple[float, float, float] = (0.0, 0.0, 0.0)
    gnss_ecef: tuple[float, float, float] | None = None
    gnss_std: tuple[float, float, float] | None = None
    gnss_broken: bool = False
    gnss_vel: tuple[float, float, float] | None = None
    gnss_vel_std: tuple[float, float, float] | None = None
    mag: tuple[float, float, float] | None = None
    mag_var: tuple[float, float, float] | None = None
    yaw_rad: float | None = None
    yaw_std: float | None = None
    local_ned: tuple[float, float, float] | None = None
    local_std: tuple[float, float, float] | None = None
    speed_mps: float | None = None
    speed_std: float | None = None
    baro_pa: float | None = None
    zupt: bool = False
    zaru: bool = False
    lever: tuple[float, float, float] = (0.0, 0.0, 0.0)
    cross_cov: tuple[float, ...] | None = None
    gnss_pos_offdiag: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class HygieneScenario:
    lat_deg: float
    lon_deg: float
    h_m: float
    origin_ecef: tuple[float, float, float]
    epochs: list[HygieneEpoch] = field(default_factory=list)
    chi2_disable: bool = False
    chi2_omit: bool = False
    auto_zupt_disable: bool = True
    mag_delay_ms: int = 0
    magnetic_n: tuple[float, float, float] = (0.0, 0.0, 0.0)
    arm_wmm: bool = False


@dataclass
class HygieneSnapshot:
    t_us: int
    ready: bool
    pos_ok: bool
    vel_ok: bool
    rpy_ok: bool
    ned_ok: bool
    bacc_ok: bool
    bgyr_ok: bool
    ecef: tuple[float, float, float] | None
    ned: tuple[float, float, float] | None
    vel: tuple[float, float, float] | None
    att: tuple[float, float, float] | None
    bias_acc: tuple[float, float, float] | None
    bias_gyr: tuple[float, float, float] | None
    n_invalid: int
    n_downweighted: int
    n_gate: int
    n_fusion: int
    n_time: int
    n_auto_zupt: int
    h_ok: bool = False
    h: float | None = None


@dataclass
class HygieneRun:
    init_ok: bool
    snaps: list[HygieneSnapshot]

    def last(self) -> HygieneSnapshot:
        if not self.snaps:
            raise HarnessError("hygiene run has no snapshots")
        return self.snaps[-1]


@dataclass
class AttOverrideSnapshot:
    t_us: int
    rpy_ok: bool
    att: tuple[float, float, float] | None
    n_invalid: int
    n_downweighted: int


@dataclass
class AttOverrideRun:
    init_ok: bool
    snaps: list[AttOverrideSnapshot]

    def last(self) -> AttOverrideSnapshot:
        if not self.snaps:
            raise HarnessError("AHRS override run has no snapshots")
        return self.snaps[-1]


@dataclass
class VertOverrideSnapshot:
    t_us: int
    h_ok: bool
    h: float | None
    n_invalid: int
    n_downweighted: int


@dataclass
class VertOverrideRun:
    init_ok: bool
    snaps: list[VertOverrideSnapshot]

    def last(self) -> VertOverrideSnapshot:
        if not self.snaps:
            raise HarnessError("baro override run has no snapshots")
        return self.snaps[-1]


def encode_epoch(e: HygieneEpoch) -> str:
    acc = _triple(e.acc, SPECIFIC_FORCE_LEVEL)
    gyr = _triple(e.gyr, (0.0, 0.0, 0.0))
    ap = _triple(e.acc_psd, (0.0, 0.0, 0.0))
    gp = _triple(e.gyr_psd, (0.0, 0.0, 0.0))
    ge = _triple(e.gnss_ecef, (0.0, 0.0, 0.0))
    gs = _triple(e.gnss_std, GNSS_STD_M)
    vel = _triple(e.gnss_vel, (0.0, 0.0, 0.0))
    vs = _triple(e.gnss_vel_std, (1.5, 1.5, 1.5))
    mag = _triple(e.mag, (0.0, 0.0, 0.0))
    mv = _triple(e.mag_var, MAG_VAR)
    loc = _triple(e.local_ned, (0.0, 0.0, 0.0))
    ls = _triple(e.local_std, LOCAL_STD_M)
    lever = _triple(e.lever, (0.0, 0.0, 0.0))
    xc = e.cross_cov if e.cross_cov is not None else (0.0,) * 9
    if len(xc) != 9:
        raise HarnessError("cross-covariance must have 9 entries")
    parts = [
        "E",
        str(e.t_us),
        hygiene_token(e.dt_sec),
        hygiene_token(acc[0]),
        hygiene_token(acc[1]),
        hygiene_token(acc[2]),
        hygiene_token(gyr[0]),
        hygiene_token(gyr[1]),
        hygiene_token(gyr[2]),
        "1" if e.acc_valid else "0",
        "1" if e.gyr_valid else "0",
        hygiene_token(ap[0]),
        hygiene_token(ap[1]),
        hygiene_token(ap[2]),
        hygiene_token(gp[0]),
        hygiene_token(gp[1]),
        hygiene_token(gp[2]),
        "1" if e.gnss_ecef is not None else "0",
        hygiene_token(ge[0]),
        hygiene_token(ge[1]),
        hygiene_token(ge[2]),
        hygiene_token(gs[0]),
        hygiene_token(gs[1]),
        hygiene_token(gs[2]),
        "1" if e.gnss_vel is not None else "0",
        hygiene_token(vel[0]),
        hygiene_token(vel[1]),
        hygiene_token(vel[2]),
        hygiene_token(vs[0]),
        hygiene_token(vs[1]),
        hygiene_token(vs[2]),
        "1" if e.mag is not None else "0",
        hygiene_token(mag[0]),
        hygiene_token(mag[1]),
        hygiene_token(mag[2]),
        hygiene_token(mv[0]),
        hygiene_token(mv[1]),
        hygiene_token(mv[2]),
        "1" if e.yaw_rad is not None else "0",
        hygiene_token(0.0 if e.yaw_rad is None else e.yaw_rad),
        hygiene_token(0.0 if e.yaw_std is None else e.yaw_std),
        "1" if e.local_ned is not None else "0",
        hygiene_token(loc[0]),
        hygiene_token(loc[1]),
        hygiene_token(loc[2]),
        hygiene_token(ls[0]),
        hygiene_token(ls[1]),
        hygiene_token(ls[2]),
        "1" if e.speed_mps is not None else "0",
        hygiene_token(0.0 if e.speed_mps is None else e.speed_mps),
        hygiene_token(SPEED_STD_MPS if e.speed_std is None else e.speed_std),
        "1" if e.baro_pa is not None else "0",
        hygiene_token(0.0 if e.baro_pa is None else e.baro_pa),
        "1" if e.zupt else "0",
        "1" if e.zaru else "0",
        hygiene_token(lever[0]),
        hygiene_token(lever[1]),
        hygiene_token(lever[2]),
        "1" if e.cross_cov is not None else "0",
    ]
    parts.extend(hygiene_token(float(x)) for x in xc)
    parts.append("1" if e.gnss_broken else "0")
    off = _triple(e.gnss_pos_offdiag, (0.0, 0.0, 0.0))
    parts.extend((hygiene_token(off[0]), hygiene_token(off[1]), hygiene_token(off[2])))
    return " ".join(parts)


def encode_hygiene(scen: HygieneScenario, kind: str) -> str:
    mag = scen.magnetic_n
    lines = [
        kind,
        " ".join(
            [
                hygiene_token(scen.lat_deg),
                hygiene_token(scen.lon_deg),
                hygiene_token(scen.h_m),
                hygiene_token(scen.origin_ecef[0]),
                hygiene_token(scen.origin_ecef[1]),
                hygiene_token(scen.origin_ecef[2]),
                "omit" if scen.chi2_omit else ("1" if scen.chi2_disable else "0"),
                "1" if scen.auto_zupt_disable else "0",
                str(int(scen.mag_delay_ms)),
                hygiene_token(mag[0]),
                hygiene_token(mag[1]),
                hygiene_token(mag[2]),
                "1" if scen.arm_wmm else "0",
                hygiene_token(scen.lat_deg),
                hygiene_token(scen.lon_deg),
                hygiene_token(_WMM_YEAR),
                "0",
            ]
        ),
    ]
    for e in scen.epochs:
        lines.append(encode_epoch(e))
    return "\n".join(lines) + "\n"


def parse_hygiene_vec(fields: dict[str, str], key: str, present: bool) -> tuple[float, float, float] | None:
    """Parse a printed triple, including a successful non-finite publish.

    A successful accessor that writes Inf/NaN is a classified observation for
    FP-09 (the published solution was not finite). Treat that as data. Missing
    keys, a dash when the flag is set, or a non-triple still raise.
    """
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


def parse_hygiene_optional_float(fields: dict[str, str], key: str) -> float | None:
    """Parse an optional printed float, including a successful non-finite publish."""
    if key not in fields:
        raise HarnessError(f"snapshot missing {key}")
    raw = fields[key]
    if raw == "-":
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise HarnessError(f"{key} not a float: {raw!r}") from exc


def parse_hygiene_snapshot(line: str) -> HygieneSnapshot:
    if not line.startswith("SNAP "):
        raise HarnessError(f"not a SNAP line: {line!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad SNAP token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    rpy_ok = _parse_flag(fields, "rpy")
    pos_ok = _parse_flag(fields, "pos")
    vel_ok = _parse_flag(fields, "vel") if "vel" in fields else False
    ned_ok = _parse_flag(fields, "ned") if "ned" in fields else False
    bacc_ok = _parse_flag(fields, "bacc") if "bacc" in fields else False
    bgyr_ok = _parse_flag(fields, "bgyr") if "bgyr" in fields else False
    if fields.get("diag") == "0":
        note_product_issue("F09", f"ins_get_diag returned NULL for a live instance: {line}")
    for _key in ("n_invalid", "n_downweighted", "n_gate", "n_fusion", "n_time", "n_auto_zupt"):
        if _parse_int(fields, _key) < 0:
            note_product_issue("F09", f"diagnostic counter {_key}={fields[_key]} missing or negative: {line}")
    return HygieneSnapshot(
        t_us=_parse_int(fields, "t_us"),
        ready=_parse_flag(fields, "ready"),
        pos_ok=pos_ok,
        vel_ok=vel_ok,
        rpy_ok=rpy_ok,
        ned_ok=ned_ok,
        bacc_ok=bacc_ok,
        bgyr_ok=bgyr_ok,
        ecef=parse_hygiene_vec(fields, "ecef", pos_ok),
        ned=parse_hygiene_vec(fields, "nedpos", ned_ok) if "nedpos" in fields else None,
        vel=parse_hygiene_vec(fields, "velned", vel_ok) if "velned" in fields else None,
        att=parse_hygiene_vec(fields, "att", rpy_ok),
        bias_acc=parse_hygiene_vec(fields, "biasacc", bacc_ok) if "biasacc" in fields else None,
        bias_gyr=parse_hygiene_vec(fields, "biasgyr", bgyr_ok) if "biasgyr" in fields else None,
        n_invalid=_parse_int(fields, "n_invalid"),
        n_downweighted=_parse_int(fields, "n_downweighted"),
        n_gate=_parse_int(fields, "n_gate"),
        n_fusion=_parse_int(fields, "n_fusion"),
        n_time=_parse_int(fields, "n_time"),
        n_auto_zupt=_parse_int(fields, "n_auto_zupt"),
        h_ok=_parse_flag(fields, "h_ok") if "h_ok" in fields else False,
        h=parse_hygiene_optional_float(fields, "h") if "h_ok" in fields else None,
    )


def parse_hygiene_run(text: str) -> HygieneRun:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    init_lines = [ln for ln in lines if ln.startswith("INIT ")]
    if not init_lines:
        raise HarnessError(f"probe stdout missing INIT: {text[:200]!r}")
    if len(init_lines) != 1:
        raise HarnessError(f"probe stdout has {len(init_lines)} INIT lines")
    init_fields = dict(
        token.split("=", 1) for token in init_lines[0][5:].split() if "=" in token
    )
    if "rc" not in init_fields:
        raise HarnessError(f"INIT missing rc: {init_lines[0]!r}")
    try:
        rc = int(init_fields["rc"])
    except ValueError as exc:
        raise HarnessError(f"INIT rc not an int: {init_lines[0]!r}") from exc
    snaps = [parse_hygiene_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    return HygieneRun(init_ok=(rc == 0), snaps=snaps)


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


def _ins_py_source(ident) -> str:
    """Python INS probe that imports the package ``make pylib`` wrote."""
    source = _PY_INS_PROBE.replace("__PKG__", ident.package_name)
    if "__PKG__" in source:
        raise HarnessError("INS probe did not receive the compiled package name")
    return source


def _suite_py_source(ident) -> str:
    """Python navigator probe that imports the package ``make pylib`` wrote."""
    source = _PY_SUITE_PROBE.replace("__PKG__", ident.package_name)
    if "__PKG__" in source:
        raise HarnessError("suite probe did not receive the compiled package name")
    return source


def _invoke_c(stdin: str):
    """C probe linked to the shared object ``make pylib`` wrote."""
    ident = _require_compiled_product()
    assert ident.library is not None and ident.library_stem == ident.package_name
    return invoke(
        _C_PROBE, stdin=stdin, timeout=HYGIENE_TIMEOUT, root=repo_root()
    )


def _run_hygiene(kind: str, scen: HygieneScenario) -> HygieneRun:
    payload = encode_hygiene(scen, "INS")
    ident = _require_compiled_product()
    if kind == "c":
        result = _invoke_c(payload)
    elif kind == "py":
        result = run_python(
            _ins_py_source(ident),
            stdin=payload,
            timeout=HYGIENE_TIMEOUT,
            root=repo_root(),
        )
    else:
        raise HarnessError(f"unknown probe kind {kind!r}")
    text = require_probe_success(result)
    run = parse_hygiene_run(text)
    last = run.last() if run.snaps else None
    print(
        f"{kind} hygiene init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"ready={None if last is None else last.ready} "
        f"n_invalid={None if last is None else last.n_invalid} "
        f"n_downweighted={None if last is None else last.n_downweighted}",
        flush=True,
    )
    return run


def c_hygiene_run(scen: HygieneScenario) -> HygieneRun:
    return _run_hygiene("c", scen)


def py_hygiene_run(scen: HygieneScenario) -> HygieneRun:
    return _run_hygiene("py", scen)


def hygiene_langs(scen: HygieneScenario, *, include_py: bool = True):
    pairs = [("c", c_hygiene_run(scen))]
    if include_py:
        pairs.append(("py", py_hygiene_run(scen)))
    return pairs


def c_suite_hygiene_run(scen: HygieneScenario) -> HygieneRun:
    payload = encode_hygiene(scen, "SUITE")
    result = _invoke_c(payload)
    text = require_probe_success(result)
    run = parse_hygiene_run(text)
    print(
        f"c suite hygiene init_ok={run.init_ok} snaps={len(run.snaps)}",
        flush=True,
    )
    return run


def py_suite_hygiene_run(scen: HygieneScenario) -> HygieneRun:
    payload = encode_hygiene(scen, "SUITE")
    ident = _require_compiled_product()
    result = run_python(
        _suite_py_source(ident),
        stdin=payload,
        timeout=HYGIENE_TIMEOUT,
        root=repo_root(),
    )
    text = require_probe_success(result)
    run = parse_hygiene_run(text)
    print(
        f"py suite hygiene init_ok={run.init_ok} snaps={len(run.snaps)}",
        flush=True,
    )
    return run


def suite_hygiene_langs(scen: HygieneScenario, *, include_py: bool = True):
    pairs = [("c", c_suite_hygiene_run(scen))]
    if include_py:
        pairs.append(("py", py_suite_hygiene_run(scen)))
    return pairs


def c_att_override_run(
    *,
    chi2_disable: bool,
    rpy: Sequence[float],
    cmds: list[tuple[int, Sequence[float], Sequence[float], Sequence[float] | None]],
) -> AttOverrideRun:
    std = ahrs_std()
    lines = [
        "AHRS",
        f"0 {1 if chi2_disable else 0} {hygiene_token(rpy[0])} {hygiene_token(rpy[1])} "
        f"{hygiene_token(rpy[2])} {hygiene_token(std[0])} {hygiene_token(std[1])} "
        f"{hygiene_token(std[2])}",
    ]
    for t_us, acc, gyr, mag in cmds:
        mag_t = (0.0, 0.0, 0.0) if mag is None else (float(mag[0]), float(mag[1]), float(mag[2]))
        lines.append(
            "E %d %s %s %s %s %s %s %d %s %s %s"
            % (
                t_us,
                hygiene_token(acc[0]),
                hygiene_token(acc[1]),
                hygiene_token(acc[2]),
                hygiene_token(gyr[0]),
                hygiene_token(gyr[1]),
                hygiene_token(gyr[2]),
                0 if mag is None else 1,
                hygiene_token(mag_t[0]),
                hygiene_token(mag_t[1]),
                hygiene_token(mag_t[2]),
            )
        )
    payload = "\n".join(lines) + "\n"
    result = _invoke_c(payload)
    text = require_probe_success(result)
    lines_out = [ln.strip() for ln in text.splitlines() if ln.strip()]
    init_lines = [ln for ln in lines_out if ln.startswith("INIT ")]
    if len(init_lines) != 1:
        raise HarnessError(f"AHRS override missing INIT: {text[:200]!r}")
    rc = int(init_lines[0].split("=", 1)[1].split()[0])
    snaps: list[AttOverrideSnapshot] = []
    for ln in lines_out:
        if not ln.startswith("SNAP "):
            continue
        fields: dict[str, str] = {}
        for token in ln[5:].split():
            key, value = token.split("=", 1)
            fields[key] = value
        rpy_ok = _parse_flag(fields, "rpy")
        snaps.append(
            AttOverrideSnapshot(
                t_us=_parse_int(fields, "t_us"),
                rpy_ok=rpy_ok,
                att=parse_hygiene_vec(fields, "att", rpy_ok),
                n_invalid=_parse_int(fields, "n_invalid"),
                n_downweighted=_parse_int(fields, "n_downweighted"),
            )
        )
    print(
        f"c ahrs override chi2={chi2_disable} init_ok={rc == 0} snaps={len(snaps)}",
        flush=True,
    )
    return AttOverrideRun(init_ok=(rc == 0), snaps=snaps)


def c_vert_override_run(
    *,
    chi2_disable: bool,
    t_init: int,
    pressure: float,
    cmds: list[tuple[int, Sequence[float], float, bool]],
) -> VertOverrideRun:
    q = level_quat()
    lines = [
        "BARO",
        f"{t_init} {1 if chi2_disable else 0} {hygiene_token(pressure)} 0 0",
    ]
    acc0 = still_level_acc()
    for t_us, acc, pa, baro_valid in cmds:
        a = acc if acc is not None else acc0
        lines.append(
            "E %d %s %s %s %s %s %s %s %s %d 0"
            % (
                t_us,
                hygiene_token(a[0]),
                hygiene_token(a[1]),
                hygiene_token(a[2]),
                hygiene_token(q[0]),
                hygiene_token(q[1]),
                hygiene_token(q[2]),
                hygiene_token(q[3]),
                hygiene_token(pa),
                1 if baro_valid else 0,
            )
        )
    payload = "\n".join(lines) + "\n"
    result = _invoke_c(payload)
    text = require_probe_success(result)
    lines_out = [ln.strip() for ln in text.splitlines() if ln.strip()]
    init_lines = [ln for ln in lines_out if ln.startswith("INIT ")]
    if len(init_lines) != 1:
        raise HarnessError(f"baro override missing INIT: {text[:200]!r}")
    rc = int(init_lines[0].split("=", 1)[1].split()[0])
    snaps: list[VertOverrideSnapshot] = []
    for ln in lines_out:
        if not ln.startswith("SNAP "):
            continue
        fields: dict[str, str] = {}
        for token in ln[5:].split():
            key, value = token.split("=", 1)
            fields[key] = value
        h_ok = _parse_flag(fields, "h_ok")
        snaps.append(
            VertOverrideSnapshot(
                t_us=_parse_int(fields, "t_us"),
                h_ok=h_ok,
                h=parse_hygiene_optional_float(fields, "h"),
                n_invalid=_parse_int(fields, "n_invalid"),
                n_downweighted=_parse_int(fields, "n_downweighted"),
            )
        )
    print(
        f"c baro override chi2={chi2_disable} init_ok={rc == 0} snaps={len(snaps)}",
        flush=True,
    )
    return VertOverrideRun(init_ok=(rc == 0), snaps=snaps)


def hygiene_site(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    epochs: list[HygieneEpoch],
    **kwargs,
) -> HygieneScenario:
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    mag_n = kwargs.pop("magnetic_n", None)
    if mag_n is None:
        mag_n = _ned_field_from_independent_wmm(lat_deg, lon_deg, _WMM_YEAR)
    return HygieneScenario(
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        h_m=h_m,
        origin_ecef=origin,
        epochs=epochs,
        magnetic_n=mag_n,
        **kwargs,
    )


def hygiene_append(
    epochs: list[HygieneEpoch],
    *,
    duration_s: float,
    origin: Sequence[float],
    imu_hz: int = IMU_HZ,
    gnss_hz: int = GNSS_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_ecef: Sequence[float] | None = None,
    gnss_std: Sequence[float] = GNSS_STD_M,
    gnss_vel: Sequence[float] | None = None,
    gnss_broken: bool = False,
    mag: Sequence[float] | None = None,
    yaw_rad: float | None = None,
    yaw_std: float | None = None,
    local_ned: Sequence[float] | None = None,
    speed_mps: float | None = None,
    baro_pa: float | None = None,
    zupt: bool = False,
    zaru: bool = False,
    lever: Sequence[float] = (0.0, 0.0, 0.0),
    acc_psd: Sequence[float] = (0.0, 0.0, 0.0),
    gyr_psd: Sequence[float] = (0.0, 0.0, 0.0),
    cross_cov: tuple[float, ...] | None = None,
    gnss_pos_offdiag: Sequence[float] = (0.0, 0.0, 0.0),
    gnss_at=None,
    mag_var: Sequence[float] | None = None,
    gnss_vel_std: Sequence[float] | None = None,
) -> list[HygieneEpoch]:
    if duration_s <= 0.0 or imu_hz <= 0:
        raise HarnessError("hygiene stream needs a positive duration and rate")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    if n <= 0:
        raise HarnessError("hygiene stream produced no epochs")
    attach_gnss = gnss_ecef is not None or gnss_at is not None or gnss_vel is not None
    every = max(1, int(round(imu_hz / gnss_hz))) if attach_gnss else None
    t0 = epochs[-1].t_us if epochs else 0
    out = list(epochs)
    acc_t = (float(acc[0]), float(acc[1]), float(acc[2]))
    gyr_t = (float(gyr[0]), float(gyr[1]), float(gyr[2]))
    lever_t = (float(lever[0]), float(lever[1]), float(lever[2]))
    ap = (float(acc_psd[0]), float(acc_psd[1]), float(acc_psd[2]))
    gp = (float(gyr_psd[0]), float(gyr_psd[1]), float(gyr_psd[2]))
    for i in range(1, n + 1):
        t_us = t0 + int(round(i * dt * 1e6))
        ecef = None
        std = None
        vel = None
        broken = False
        if every is not None and i % every == 0:
            if gnss_at is not None:
                ecef, std, vel, broken = gnss_at(t_us, i)
            else:
                if gnss_ecef is not None:
                    ecef = tuple(gnss_ecef)
                    std = tuple(gnss_std)
                    broken = gnss_broken
                vel = None if gnss_vel is None else tuple(gnss_vel)
        out.append(
            HygieneEpoch(
                t_us=t_us,
                dt_sec=dt,
                acc=acc_t,
                gyr=gyr_t,
                acc_psd=ap,
                gyr_psd=gp,
                gnss_ecef=None if ecef is None else (float(ecef[0]), float(ecef[1]), float(ecef[2])),
                gnss_std=None if std is None else (float(std[0]), float(std[1]), float(std[2])),
                gnss_vel=None if vel is None else (float(vel[0]), float(vel[1]), float(vel[2])),
                gnss_broken=broken,
                mag=None if mag is None else (float(mag[0]), float(mag[1]), float(mag[2])),
                mag_var=None if mag is None else (
                    (float(mag_var[0]), float(mag_var[1]), float(mag_var[2]))
                    if mag_var is not None
                    else MAG_VAR
                ),
                yaw_rad=yaw_rad,
                yaw_std=yaw_std,
                local_ned=None if local_ned is None else (float(local_ned[0]), float(local_ned[1]), float(local_ned[2])),
                local_std=None if local_ned is None else LOCAL_STD_M,
                speed_mps=speed_mps,
                baro_pa=baro_pa,
                zupt=zupt,
                zaru=zaru,
                lever=lever_t,
                cross_cov=cross_cov,
                gnss_pos_offdiag=(
                    float(gnss_pos_offdiag[0]),
                    float(gnss_pos_offdiag[1]),
                    float(gnss_pos_offdiag[2]),
                ),
                gnss_vel_std=(
                    None
                    if vel is None
                    else (
                        (float(gnss_vel_std[0]), float(gnss_vel_std[1]), float(gnss_vel_std[2]))
                        if gnss_vel_std is not None
                        else (1.5, 1.5, 1.5)
                    )
                ),
            )
        )
    return out


def hygiene_pad(origin: Sequence[float], *, duration_s: float = HAPPY_DURATION_S, **kwargs) -> list[HygieneEpoch]:
    return hygiene_append([], duration_s=duration_s, origin=origin, gnss_ecef=origin, **kwargs)


def window_mean(snaps, t_from_us: int, t_to_us: int | None, err, what: str) -> float:
    """Mean of ``err(snap)`` over every snapshot with ``t_from < t_us <= t_to``.

    Used for "which arm follows a step more" contrasts: a full-weight arm
    may overshoot the step at a single late instant while still following
    it far closer over the whole post-step window than a downweighted arm.
    Every snapshot in the window must be scorable (``err`` not None); an
    unpublished solution inside the window is a failure, not a skip.
    """
    vals: list[float] = []
    for snap in snaps:
        if snap.t_us <= t_from_us:
            continue
        if t_to_us is not None and snap.t_us > t_to_us:
            continue
        v = err(snap)
        assert v is not None and math.isfinite(v), (
            f"{what}: unpublished or non-finite solution at t_us={snap.t_us} "
            "inside the post-step window"
        )
        vals.append(float(v))
    assert vals, f"{what}: no snapshot inside the post-step window"
    return sum(vals) / len(vals)


def window_min(snaps, t_from_us: int, t_to_us: int | None, err, what: str) -> float:
    """Closest approach: smallest ``err(snap)`` over the post-step window.

    For an aiding stream fused only a few times inside the window (a rate
    limited magnetometer) the mean is diluted by the epochs before the first
    fusion; the closest approach is the furthest either arm got toward the
    step, and an overshoot after reaching it cannot flip the comparison.
    Every snapshot in the window must be scorable.
    """
    vals: list[float] = []
    for snap in snaps:
        if snap.t_us <= t_from_us:
            continue
        if t_to_us is not None and snap.t_us > t_to_us:
            continue
        v = err(snap)
        assert v is not None and math.isfinite(v), (
            f"{what}: unpublished or non-finite solution at t_us={snap.t_us} "
            "inside the post-step window"
        )
        vals.append(float(v))
    assert vals, f"{what}: no snapshot inside the post-step window"
    return min(vals)


def snap_at(run: HygieneRun, t_us: int) -> HygieneSnapshot:
    for snap in run.snaps:
        if snap.t_us == t_us:
            return snap
    raise HarnessError(f"no snapshot at t_us={t_us}")


def last_at_or_before(run: HygieneRun, t_us: int) -> HygieneSnapshot:
    found = None
    for snap in run.snaps:
        if snap.t_us <= t_us and snap.t_us > 0:
            found = snap
    if found is None:
        raise HarnessError(f"no snapshot at or before t_us={t_us}")
    return found


def require_ready_hygiene(snap: HygieneSnapshot, origin: Sequence[float], what: str) -> tuple[float, float, float]:
    if not snap.ready:
        raise AssertionError(f"{what}: expected ready at t={snap.t_us}")
    if not snap.pos_ok or snap.ecef is None:
        raise AssertionError(f"{what}: position accessor failed at t={snap.t_us}")
    err = hypot3(snap.ecef, origin)
    if err > ECEF_MATCH_M:
        raise AssertionError(f"{what}: ECEF {err} m from pad, bound {ECEF_MATCH_M}")
    return snap.ecef


def require_finite_published(snap: HygieneSnapshot, what: str) -> None:
    assert snap.pos_ok and snap.ecef is not None, f"{what}: position accessor failed"
    assert snap.vel_ok and snap.vel is not None, f"{what}: velocity accessor failed"
    assert snap.rpy_ok and snap.att is not None, f"{what}: attitude accessor failed"
    assert all(math.isfinite(v) for v in snap.ecef), (
        f"{what}: published ECEF is not finite: {snap.ecef!r}"
    )
    assert all(math.isfinite(v) for v in snap.vel), (
        f"{what}: published velocity is not finite: {snap.vel!r}"
    )
    assert all(math.isfinite(v) for v in snap.att), (
        f"{what}: published attitude is not finite: {snap.att!r}"
    )


def wrap_pi(yaw: float) -> float:
    y = float(yaw)
    while y > math.pi:
        y -= 2.0 * math.pi
    while y < -math.pi:
        y += 2.0 * math.pi
    return y


def write_outlier_replay_dataset(
    ws: Workspace,
    *,
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    north_m: float,
    override: bool,
    relpath: str,
) -> Path:
    """Write IMU+GNSS CSVs and config.yaml for a pad then a north GNSS offset.

    The yaml carries the same global outlier-rejection override as the filter
    options. The key spelling is the replay schema, not an asserted
    stdout token.
    """
    dest = ws.resolve(relpath)
    dest.mkdir(parents=True, exist_ok=True)
    origin = ecef_from_llh_deg(lat_deg, lon_deg, h_m)
    offset = ecef_plus_ned(origin, north_m, 0.0, 0.0)
    olat, olon, oh = _ecef_to_geodetic(offset[0], offset[1], offset[2])
    olat_d = math.degrees(olat)
    olon_d = math.degrees(olon)
    imu_hz = IMU_HZ
    gnss_hz = GNSS_HZ
    dt = 1.0 / imu_hz
    pad_s = HAPPY_DURATION_S
    hold_s = SHORT_WINDOW_S
    n = int(round((pad_s + hold_s) * imu_hz))
    pos_var = 4.0
    vel_var = 0.04
    imu_lines = [
        "# t_us, gyr_frd_x [rad/s], gyr_frd_y [rad/s], gyr_frd_z [rad/s], "
        "acc_frd_x [m/s^2], acc_frd_y [m/s^2], acc_frd_z [m/s^2]\n"
    ]
    ref_lines = [
        "# t_us, lat_deg, lon_deg, h_m, roll_deg, pitch_deg, yaw_deg, "
        "vn_mps, ve_mps, vd_mps\n"
    ]
    gnss_lines = [
        "# t_us, lat_deg, lon_deg, h_m, cov_pos_ned nn,ne,nd,ee,ed,dd [m^2], "
        "vn, ve, vd [m/s], cov_vel_ned nn,ne,nd,ee,ed,dd [(m/s)^2], vel_ok\n"
    ]
    gnss_every = max(1, imu_hz // gnss_hz)
    ref_every = max(1, imu_hz // 10)
    fz = -G_MPS2
    for k in range(n + 1):
        t_s = k * dt
        t_us = int(round(t_s * 1e6))
        imu_lines.append(f"{t_us},0,0,0,0,0,{fz:.9g}\n")
        if k % ref_every == 0:
            ref_lines.append(
                f"{t_us},{lat_deg:.10f},{lon_deg:.10f},{h_m:.6f},0,0,0,0,0,0\n"
            )
        if k % gnss_every == 0:
            if t_s <= pad_s:
                la, lo, hh = lat_deg, lon_deg, h_m
            else:
                la, lo, hh = olat_d, olon_d, oh
            gnss_lines.append(
                f"{t_us},{la:.10f},{lo:.10f},{hh:.6f},"
                f"{pos_var},0,0,{pos_var},0,{pos_var},"
                f"0,0,0,"
                f"{vel_var},0,0,{vel_var},0,{vel_var},1\n"
            )
    (dest / "imu.csv").write_text("".join(imu_lines), encoding="utf-8")
    (dest / "ref.csv").write_text("".join(ref_lines), encoding="utf-8")
    (dest / "gnss.csv").write_text("".join(gnss_lines), encoding="utf-8")
    switch = 1 if override else 0
    (dest / "config.yaml").write_text(
        "\n".join(
            [
                "name: f09-outlier-override",
                "aiding: gnss",
                "init: auto",
                f"chi2_disable: {switch}",
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
                # gnss.csv carries a positive covariance on every fix, so no
                # fallback 1-sigma is used. The position-fallback key is left
                # out: its value shape (scalar or horizontal/vertical pair)
                # is not what this override contrast scores.
                "  vel_stddev_fallback_mps: 0.25",
                "mag:",
                "  enable: 0",
                "baro:",
                "  enable: 0",
                "score:",
                "  warmup_sec: 1",
                "  min_epochs: 0",
                "  ahrs: 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return dest


def _published_llh(line: str) -> tuple[float, float, float] | None:
    """lat/lon/h of one dump data row, or None when that epoch is unpublished.

    Contract: an unpublished epoch writes no row. An empty or non-finite
    lat/lon/h cell is read the same way, so the dump's spelling of "no value"
    never decides a result. A short or non-numeric row is still malformed.
    """
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 4:
        note_product_issue("F09", f"--dump-solution row is short: {line}")
        return None
    cells = parts[1:4]
    if any(c == "" for c in cells):
        return None
    try:
        lat, lon, h = (float(c) for c in cells)
    except ValueError:
        note_product_issue("F09", f"--dump-solution row is not numeric: {line}")
        return None
    if not all(math.isfinite(v) for v in (lat, lon, h)):
        return None
    return lat, lon, h


def replay_ecef_rows(dataset: Path, dump_path: Path) -> list[tuple[float, float, float]]:
    """Replay a dataset directory dumping every IMU epoch; ECEF of each data row.

    ``--dump-solution-hz=0`` dumps every IMU epoch (contract). Rows are
    returned in file order; the time field's unit is not read.
    """
    _require_compiled_product()
    result = run_replay(
        dataset,
        ["--dump-solution", str(dump_path), "--dump-solution-hz=0"],
        timeout=DEFAULT_REPLAY_TIMEOUT,
        root=repo_root(),
    )
    if result.returncode != 0:
        err = ""
        try:
            err = result.stderr_text
        except HarnessError:
            err = "<stderr not utf-8>"
        raise HarnessError(
            f"replay exited {result.returncode} stderr={err!r} "
            f"stdout={result.stdout_text[-1500:]!r}"
        )
    if not dump_path.is_file():
        raise HarnessError(f"replay wrote no solution file at {dump_path}")
    rows: list[tuple[float, float, float]] = []
    for raw in dump_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        llh = _published_llh(line)
        if llh is None:
            continue
        rows.append(ecef_from_llh_deg(*llh))
    if not rows:
        raise HarnessError(
            "replay solution dump had no data rows; stdout was:\n"
            + result.stdout_text[-1500:]
        )
    return rows


def outlier_replay_step_rows() -> int:
    """IMU epochs of ``write_outlier_replay_dataset`` after the GNSS step."""
    return int(round(SHORT_WINDOW_S * IMU_HZ))


def replay_last_ecef(dataset: Path, dump_path: Path) -> tuple[float, float, float]:
    """Replay a dataset directory and return the last dumped ECEF. Raises on silence."""
    _require_compiled_product()
    result = run_replay(
        dataset,
        ["--dump-solution", str(dump_path), "--dump-solution-hz=1"],
        timeout=DEFAULT_REPLAY_TIMEOUT,
        root=repo_root(),
    )
    if result.returncode != 0:
        err = ""
        try:
            err = result.stderr_text
        except HarnessError:
            err = "<stderr not utf-8>"
        raise HarnessError(
            f"replay exited {result.returncode} stderr={err!r} "
            f"stdout={result.stdout_text[-1500:]!r}"
        )
    if not dump_path.is_file():
        raise HarnessError(f"replay wrote no solution file at {dump_path}")
    last = None
    for raw in dump_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        llh = _published_llh(line)
        if llh is None:
            continue
        last = llh
    if last is None:
        raise HarnessError(
            "replay solution dump had no data rows; stdout was:\n"
            + result.stdout_text[-1500:]
        )
    return ecef_from_llh_deg(last[0], last[1], last[2])

