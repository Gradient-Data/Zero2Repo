# feature: F06
"""Observation helpers for FP-06 standalone ARS / AHRS attitude.

C probes compile through the sealed harness. Python observations run in a
child interpreter. This module does not import the product in the pytest
process. Expected headings and declination come from independent ZYX
geometry and the sealed F01 WMM, never from the library's own fusion.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
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
    run_python,
)
from F01_helpers import (
    independent_wmm,
    is_public_wmm_row,
    require_probe_success,
)
from F02_helpers import (
    DT_SEC,
    IMU_HZ,
    LONG_TIMEOUT,
    SPECIFIC_FORCE_LEVEL,
    _parse_flag,
    _parse_int,
    _parse_vec,
    runtime_site,
)
from F03_helpers import (
    angle_diff_rad,
    body_mag_for_yaw,
    ned_field_from_independent_wmm,
    still_level_acc,
)

# Fixed inputs and tolerances for FP-06.
REF_GYR_PSD = 0.0001
REF_ACC_NOISE = 0.05
REF_BIAS_DPS = (1.0, -2.0, 0.0)
REF_INIT_ERR_DEG = 3.0
REF_RP_LIM_DEG = 0.2
REF_BIAS_LIM_DPS = 0.1
REF_DURATION_S = 10.0
GAP_INSIDE_S = 0.15
GAP_OUTSIDE_S = 0.25
FIELD_TOL_NAMED = 0.30
ATT_YEAR = 2025.0
MODE_ARS = 0
MODE_AHRS = 1
MANDATORY_STD_RAD = math.radians(10.0)
AHRS_YAW_STD_RAD = math.radians(30.0)
ATT_TIMEOUT = LONG_TIMEOUT

_C_PROBE = r"""
#define _GNU_SOURCE
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "ahrs.h"
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

/* Vehicle velocity on the published attitude solution.
   The attitude instance's published readers are ahrs_get_rpy (roll,
   pitch, yaw), ahrs_get_rpy_stddev (their 1-sigma) and ahrs_get_bias_gyr
   (gyro bias); none of them is a velocity, so this read is absent. The
   navigation-filter velocity is a different read on the same stream. */
static int attitude_solution_velocity(const ahrs_t *a, float out[3])
{
    if (a == NULL || out == NULL) {
        fprintf(stderr, "attitude velocity channel: no attitude solution to read\n");
        exit(2);
    }
    return 0;
}

static void print_filter_snap(const ahrs_t *a, long long t_us)
{
    float roll = 0.0f, pitch = 0.0f, yaw = 0.0f, bias[3];
    int rpy = ahrs_get_rpy(a, &roll, &pitch, &yaw) ? 1 : 0;
    int b_ok = ahrs_get_bias_gyr(a, bias) ? 1 : 0;
    if (rpy) {
    }
    if (b_ok) {
    }
    float rs = 0.0f, ps = 0.0f, ys = 0.0f;
    int s_ok = ahrs_get_rpy_stddev(a, &rs, &ps, &ys) ? 1 : 0;
    printf("SNAP t_us=%lld rpy=%d", t_us, rpy);
    if (rpy) {
        printf(" att=%.9g,%.9g,%.9g", roll, pitch, yaw);
    } else {
        printf(" att=-");
    }
    printf(" bias=%d", b_ok);
    if (b_ok) {
        printf(" gyr=%.9g,%.9g,%.9g", bias[0], bias[1], bias[2]);
    } else {
        printf(" gyr=-");
    }
    printf(" std=%d", s_ok);
    if (s_ok) {
        printf(" att_std=%.9g,%.9g,%.9g", rs, ps, ys);
    } else {
        printf(" att_std=-");
    }
    float att_v[3];
    int att_vel = 0;
    if (rpy) {
        att_vel = attitude_solution_velocity(a, att_v);
    }
    printf(" vel=%d", att_vel);
    if (att_vel) {
        printf(" att_vel=%.9g,%.9g,%.9g", att_v[0], att_v[1], att_v[2]);
    } else {
        printf(" att_vel=-");
    }
    printf(" n_invalid=%u\n", a->n_invalid_input);
}

static void print_suite_snap(const nav_suite_t *s, long long t_us)
{
    float ar[3], ah[3];
    int ars = nav_suite_get_rpy_ars(s, &ar[0], &ar[1], &ar[2]) ? 1 : 0;
    int ahrs = nav_suite_get_rpy_ahrs(s, &ah[0], &ah[1], &ah[2]) ? 1 : 0;
    float ars_s[3] = {0.0f, 0.0f, 0.0f};
    float ahrs_s[3] = {0.0f, 0.0f, 0.0f};
    int ars_std = ahrs_get_rpy_stddev(&s->ars, &ars_s[0], &ars_s[1], &ars_s[2]) ? 1 : 0;
    int ahrs_std = ahrs_get_rpy_stddev(&s->ahrs, &ahrs_s[0], &ahrs_s[1], &ahrs_s[2]) ? 1 : 0;
    printf("SNAP t_us=%lld ars=%d ahrs=%d", t_us, ars, ahrs);
    if (ars) {
        printf(" ars_att=%.9g,%.9g,%.9g", ar[0], ar[1], ar[2]);
    } else {
        printf(" ars_att=-");
    }
    if (ahrs) {
        printf(" ahrs_att=%.9g,%.9g,%.9g", ah[0], ah[1], ah[2]);
    } else {
        printf(" ahrs_att=-");
    }
    printf(" ars_std=%d", ars_std);
    if (ars_std) {
        printf(" ars_att_std=%.9g,%.9g,%.9g", ars_s[0], ars_s[1], ars_s[2]);
    } else {
        printf(" ars_att_std=-");
    }
    printf(" ahrs_std=%d", ahrs_std);
    if (ahrs_std) {
        printf(" ahrs_att_std=%.9g,%.9g,%.9g", ahrs_s[0], ahrs_s[1], ahrs_s[2]);
    } else {
        printf(" ahrs_att_std=-");
    }
    float ars_b[3] = {0.0f, 0.0f, 0.0f};
    float ahrs_b[3] = {0.0f, 0.0f, 0.0f};
    float vel[3] = {0.0f, 0.0f, 0.0f};
    int ars_bias = ahrs_get_bias_gyr(&s->ars, ars_b) ? 1 : 0;
    int ahrs_bias = ahrs_get_bias_gyr(&s->ahrs, ahrs_b) ? 1 : 0;
    int vel_ok = ins_get_velocity_ned(&s->ins, vel) ? 1 : 0;
    int zaru = nav_suite_get_zaru_active(s) ? 1 : 0;
    printf(" zaru=%d vel=%d", zaru, vel_ok);
    if (vel_ok) {
        printf(" vel_ned=%.9g,%.9g,%.9g", vel[0], vel[1], vel[2]);
    } else {
        printf(" vel_ned=-");
    }
    printf(" ars_bias=%d", ars_bias);
    if (ars_bias) {
        printf(" ars_gyr=%.9g,%.9g,%.9g", ars_b[0], ars_b[1], ars_b[2]);
    } else {
        printf(" ars_gyr=-");
    }
    printf(" ahrs_bias=%d", ahrs_bias);
    if (ahrs_bias) {
        printf(" ahrs_gyr=%.9g,%.9g,%.9g", ahrs_b[0], ahrs_b[1], ahrs_b[2]);
    } else {
        printf(" ahrs_gyr=-");
    }
    /* Ask each attitude instance whether its published solution includes
       a velocity. The three angles above are not that question. */
    float ars_v[3], ahrs_v[3];
    int ars_vel = 0, ahrs_vel = 0;
    if (ars) {
        ars_vel = attitude_solution_velocity(&s->ars, ars_v);
    }
    if (ahrs) {
        ahrs_vel = attitude_solution_velocity(&s->ahrs, ahrs_v);
    }
    printf(" ars_vel=%d", ars_vel);
    if (ars_vel) {
        printf(" ars_vned=%.9g,%.9g,%.9g", ars_v[0], ars_v[1], ars_v[2]);
    } else {
        printf(" ars_vned=-");
    }
    printf(" ahrs_vel=%d", ahrs_vel);
    if (ahrs_vel) {
        printf(" ahrs_vned=%.9g,%.9g,%.9g", ahrs_v[0], ahrs_v[1], ahrs_v[2]);
    } else {
        printf(" ahrs_vned=-");
    }
    /* ARS attitude instance's published invalid-input counter (not the
       navigation filter's invalid-input diagnostic). */
    printf(" ars_n_invalid=%u\n", s->ars.n_invalid_input);
}

static int run_filter(void)
{
    char line[4096];
    char *tok[16];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("filter cfg");
    }
    int n = split_ws(line, tok, 16);
    if (n != 3 && n != 8) {
        return fail_read("filter cfg fields");
    }
    int mode = 0, mag_check = 0;
    float mag_tol = 0.0f;
    float mf = 0.0f, mc = 0.0f;
    if (!parse_f(tok[0], &mf) || !parse_f(tok[1], &mc) || !parse_f(tok[2], &mag_tol)) {
        return fail_read("filter cfg numbers");
    }
    mode = (int)mf;
    mag_check = (int)mc;
    /* Optional precision-restart watchdog fields of ahrs_config_t:
       disable flag, per-axis 1-sigma thresholds (0 = default, < 0 = axis
       unchecked), warm-up seconds (0 = default). Absent = all zero. */
    float rs_dis = 0.0f, rs_thr[3] = {0.0f, 0.0f, 0.0f}, rs_warm = 0.0f;
    if (n == 8) {
        if (!parse_f(tok[3], &rs_dis) || !parse_f(tok[4], &rs_thr[0]) ||
            !parse_f(tok[5], &rs_thr[1]) || !parse_f(tok[6], &rs_thr[2]) ||
            !parse_f(tok[7], &rs_warm)) {
            return fail_read("filter cfg restart numbers");
        }
    }
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("filter init");
    }
    n = split_ws(line, tok, 16);
    if (n != 7) {
        return fail_read("filter init fields");
    }
    long long t_init = 0;
    float rpy[3], std[3];
    if (!parse_ll(tok[0], &t_init) || !parse_f(tok[1], &rpy[0]) ||
        !parse_f(tok[2], &rpy[1]) || !parse_f(tok[3], &rpy[2]) ||
        !parse_f(tok[4], &std[0]) || !parse_f(tok[5], &std[1]) ||
        !parse_f(tok[6], &std[2])) {
        return fail_read("filter init numbers");
    }

    ahrs_t a;
    memset(&a, 0, sizeof a);
    ahrs_config_t cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.mode = (mode == 1) ? AHRS_MODE_AHRS : AHRS_MODE_ARS;
    cfg.rpy_init_rad[0] = rpy[0];
    cfg.rpy_init_rad[1] = rpy[1];
    cfg.rpy_init_rad[2] = rpy[2];
    cfg.rpy_init_stddev_rad[0] = std[0];
    cfg.rpy_init_stddev_rad[1] = std[1];
    cfg.rpy_init_stddev_rad[2] = std[2];
    if (mag_check) {
        cfg.mag_field_check_enable = true;
    }
    cfg.mag_field_tolerance = mag_tol;
    cfg.precision_restart_disable = ((int)rs_dis) ? true : false;
    cfg.restart_att_stddev_rad[0] = rs_thr[0];
    cfg.restart_att_stddev_rad[1] = rs_thr[1];
    cfg.restart_att_stddev_rad[2] = rs_thr[2];
    cfg.restart_warmup_sec = rs_warm;

    int rc = ahrs_init(&a, &cfg, (ahrs_time_us_t)t_init);
    printf("INIT rc=%d\n", rc);
    print_filter_snap(&a, t_init);
    if (rc != 0) {
        return 0;
    }

    long long last_t = t_init;
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 16);
        if (n < 1) {
            continue;
        }
        if (tok[0][0] == 'P' && tok[0][1] == '\0') {
            if (n != 4) {
                return fail_read("POS fields");
            }
            double lat = 0.0, lon = 0.0, year = 0.0;
            if (!parse_d(tok[1], &lat) || !parse_d(tok[2], &lon) ||
                !parse_d(tok[3], &year)) {
                return fail_read("POS numbers");
            }
            ahrs_set_position(&a, (float)(lat * M_PI / 180.0),
                              (float)(lon * M_PI / 180.0), (float)year);
            print_filter_snap(&a, last_t);
            continue;
        }
        if (tok[0][0] != 'E' || tok[0][1] != '\0') {
            return fail_read("epoch tag");
        }
        if (n != 14) {
            return fail_read("epoch fields");
        }
        long long t_us = 0;
        float accf, ax, ay, az, gx, gy, gz, mx, my, mz, magf, zaruf;
        if (!parse_ll(tok[1], &t_us) || !parse_f(tok[2], &accf) ||
            !parse_f(tok[3], &ax) || !parse_f(tok[4], &ay) ||
            !parse_f(tok[5], &az) || !parse_f(tok[6], &gx) ||
            !parse_f(tok[7], &gy) || !parse_f(tok[8], &gz) ||
            !parse_f(tok[9], &magf) || !parse_f(tok[10], &mx) ||
            !parse_f(tok[11], &my) || !parse_f(tok[12], &mz) ||
            !parse_f(tok[13], &zaruf)) {
            return fail_read("epoch numbers");
        }
        {
            float gyr[3] = {gx, gy, gz};
            float acc[3] = {ax, ay, az};
            float mag[3] = {mx, my, mz};
            const float *magp = ((int)magf) ? mag : NULL;
            /* accf == 0: this epoch has a gyro and no accelerometer sample.
               The stored triple is a placeholder, not a specific-force
               measurement, so it is not passed into the update. */
            const float *accp = ((int)accf) ? acc : NULL;
            ahrs_update(&a, (ahrs_time_us_t)t_us, gyr, accp, magp,
                        ((int)zaruf) ? true : false);
        }
        last_t = t_us;
        print_filter_snap(&a, t_us);
    }
    return 0;
}

static int run_level(void)
{
    char line[4096];
    char *tok[8];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("level");
    }
    int n = split_ws(line, tok, 8);
    if (n != 3) {
        return fail_read("level fields");
    }
    float acc[3];
    if (!parse_f(tok[0], &acc[0]) || !parse_f(tok[1], &acc[1]) ||
        !parse_f(tok[2], &acc[2])) {
        return fail_read("level numbers");
    }
    float roll = 0.0f, pitch = 0.0f;
    ahrs_leveling_from_acc(acc, &roll, &pitch);
    if (!isfinite(roll) || !isfinite(pitch)) {
        fprintf(stderr, "leveling helper returned a non-finite attitude\n");
        return 2;
    }
    printf("LEVEL roll=%.17g pitch=%.17g\n", roll, pitch);
    return 0;
}

static int run_head(void)
{
    char line[4096];
    char *tok[8];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("head");
    }
    int n = split_ws(line, tok, 8);
    if (n != 5) {
        return fail_read("head fields");
    }
    float mag[3], roll, pitch;
    if (!parse_f(tok[0], &mag[0]) || !parse_f(tok[1], &mag[1]) ||
        !parse_f(tok[2], &mag[2]) || !parse_f(tok[3], &roll) ||
        !parse_f(tok[4], &pitch)) {
        return fail_read("head numbers");
    }
    float yaw = ahrs_mag_heading(mag, roll, pitch);
    if (!isfinite(yaw)) {
        fprintf(stderr, "heading helper returned a non-finite yaw\n");
        return 2;
    }
    printf("HEAD yaw=%.17g\n", yaw);
    return 0;
}

static int run_suite(void)
{
    char line[4096];
    char *tok[24];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("suite cfg");
    }
    int n = split_ws(line, tok, 24);
    if (n != 8) {
        return fail_read("suite cfg fields");
    }
    double lat = 0.0, lon = 0.0, h = 0.0, yaw_hint = 0.0, yaw_std = 0.0;
    float auto_f = 0.0f, presc_f = 0.0f, blind_f = 0.0f;
    if (!parse_d(tok[0], &lat) || !parse_d(tok[1], &lon) || !parse_d(tok[2], &h) ||
        !parse_f(tok[3], &auto_f) || !parse_f(tok[4], &presc_f) ||
        !parse_d(tok[5], &yaw_hint) || !parse_d(tok[6], &yaw_std) ||
        !parse_f(tok[7], &blind_f)) {
        return fail_read("suite cfg numbers");
    }

    static nav_suite_t s;
    memset(&s, 0, sizeof s);
    ins_init_t init;
    memset(&init, 0, sizeof init);
    ins_options_t opt;
    memset(&opt, 0, sizeof opt);
    init.time = 0;
    ins_latlonh_to_ecef(lat * M_PI / 180.0, lon * M_PI / 180.0, h, init.x_ecef);
    init.pos_init_stddev_m = 1.0f;
    init.vel_init_stddev_mps = 0.1f;
    init.rpy_init_stddev_rad[0] = 3.0f * (float)M_PI / 180.0f;
    init.rpy_init_stddev_rad[1] = 3.0f * (float)M_PI / 180.0f;
    init.rpy_init_stddev_rad[2] = 3.0f * (float)M_PI / 180.0f;
    init.acc_bias_init_stddev_mps2 = 0.05f;
    init.gyr_bias_init_stddev_rps = 0.05f * (float)M_PI / 180.0f;
    opt.allow_unlimited_deadreckoning = true;
    opt.auto_zupt_velocity_blind_disable = (int)blind_f ? true : false;
    if ((int)presc_f) {
        opt.auto_init = false;
        init.rpy_init_rad[2] = (float)yaw_hint;
    } else {
        opt.auto_init = true;
    }
    int rc = nav_suite_init(&s, &init, &opt);
    printf("INIT rc=%d\n", rc);
    if (rc != 0) {
        print_suite_snap(&s, 0);
        return 0;
    }
    if (!(int)presc_f && yaw_std > 0.0) {
        nav_suite_set_init_att_hint(&s, 0.0f, 0.0f, 0.0f, (float)yaw_hint,
                                    (float)yaw_std);
    }
    print_suite_snap(&s, 0);

    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 24);
        if (n < 1 || tok[0][0] != 'E') {
            return fail_read("suite epoch tag");
        }
        if (n != 13 && n != 17 && n != 21) {
            return fail_read("suite epoch fields");
        }
        long long t_us = 0;
        float accf, ax, ay, az, gx, gy, gz, magf, mx, my, mz;
        float gnssf = 0.0f, vn = 0.0f, ve = 0.0f, vd = 0.0f;
        float posf = 0.0f;
        double px = 0.0, py = 0.0, pz = 0.0;
        if (!parse_ll(tok[1], &t_us) || !parse_f(tok[2], &accf) ||
            !parse_f(tok[3], &ax) || !parse_f(tok[4], &ay) ||
            !parse_f(tok[5], &az) || !parse_f(tok[6], &gx) ||
            !parse_f(tok[7], &gy) || !parse_f(tok[8], &gz) ||
            !parse_f(tok[9], &magf) || !parse_f(tok[10], &mx) ||
            !parse_f(tok[11], &my) || !parse_f(tok[12], &mz)) {
            return fail_read("suite epoch numbers");
        }
        if ((n == 17 || n == 21) &&
            (!parse_f(tok[13], &gnssf) || !parse_f(tok[14], &vn) ||
             !parse_f(tok[15], &ve) || !parse_f(tok[16], &vd))) {
            return fail_read("suite gnss numbers");
        }
        if (n == 21 &&
            (!parse_f(tok[17], &posf) || !parse_d(tok[18], &px) ||
             !parse_d(tok[19], &py) || !parse_d(tok[20], &pz))) {
            return fail_read("suite position numbers");
        }
        ins_measurements_t m;
        memset(&m, 0, sizeof m);
        m.timestamp = (ins_time_us_t)t_us;
        m.strapdown_dt_sec = 0.01f;
        /* accf == 0: the finite triple stays in the bundle and is not a
           sample. A non-finite triple is a different epoch, the drop. */
        m.acc.is_valid = ((int)accf) ? true : false;
        m.gyr.is_valid = true;
        m.acc.data[0] = ax;
        m.acc.data[1] = ay;
        m.acc.data[2] = az;
        m.gyr.data[0] = gx;
        m.gyr.data[1] = gy;
        m.gyr.data[2] = gz;
        if ((int)magf) {
            m.mag.is_valid = true;
            m.mag.data[0] = mx;
            m.mag.data[1] = my;
            m.mag.data[2] = mz;
            m.mag.Qll_diag[0] = m.mag.Qll_diag[1] = m.mag.Qll_diag[2] = 1.0f;
        }
        if ((int)gnssf) {
            m.gnss_vel.is_valid = true;
            m.gnss_vel.vel_ned[0] = vn;
            m.gnss_vel.vel_ned[1] = ve;
            m.gnss_vel.vel_ned[2] = vd;
            m.gnss_vel.Qll_ned[0] = 0.04f;
            m.gnss_vel.Qll_ned[4] = 0.04f;
            m.gnss_vel.Qll_ned[8] = 0.04f;
        }
        if ((int)posf) {
            m.gnss_pos.is_valid = true;
            m.gnss_pos.xyz_ecef[0] = px;
            m.gnss_pos.xyz_ecef[1] = py;
            m.gnss_pos.xyz_ecef[2] = pz;
            m.gnss_pos.Qll_ned[0] = 1.0f;
            m.gnss_pos.Qll_ned[4] = 1.0f;
            m.gnss_pos.Qll_ned[8] = 1.0f;
        }
        nav_suite_update(&s, &m);
        print_suite_snap(&s, t_us);
    }
    return 0;
}

int main(void)
{
    char line[256];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("kind");
    }
    if (strncmp(line, "FILTER", 6) == 0) {
        return run_filter();
    }
    if (strncmp(line, "LEVEL", 5) == 0) {
        return run_level();
    }
    if (strncmp(line, "HEAD", 4) == 0) {
        return run_head();
    }
    if (strncmp(line, "SUITE", 5) == 0) {
        return run_suite();
    }
    return fail_read("kind token");
}
"""

_PY_HEAD_PROBE = r"""
import math
import sys

from geodetic_toolbox import mag_heading

line = sys.stdin.readline()
if not line:
    raise SystemExit("missing heading input")
parts = line.split()
if len(parts) != 5:
    raise SystemExit("heading fields")
mx, my, mz, roll, pitch = [float(x) for x in parts]
yaw = mag_heading((mx, my, mz), roll, pitch)
print("HEAD yaw=%.17g" % yaw)
"""

_PY_SUITE_PROBE = r"""
import math
import sys

from __PKG__ import Config, Navigator


def _take_velocity(found, vec, what):
    if vec is None:
        return found
    if found is not None and found != vec:
        # A second, different attitude velocity: keep the first (see the C probe).
        return found
    return vec


def _as_attitude(rpy, what):
    # Roll, pitch, and yaw are the attitude. Another 3-vector on this
    # result is a velocity only when that result carries a velocity.
    # Three angles, gyro bias, and any other non-velocity 3-vector are not.
    if rpy is None:
        return None, None
    if isinstance(rpy, (str, bytes)):
        raise SystemExit("%s attitude result is not roll/pitch/yaw" % what)
    try:
        vals = tuple(rpy)
    except TypeError as exc:
        raise SystemExit("%s attitude result is not roll/pitch/yaw" % what) from exc
    if len(vals) < 3 or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals[:3]
    ):
        raise SystemExit(
            "%s attitude result has no roll/pitch/yaw" % what
        )
    if len(vals) != 3:
        # The published attitude reader is roll, pitch, yaw and nothing else.
        raise SystemExit("%s attitude result is not exactly roll/pitch/yaw" % what)
    angles = (float(vals[0]), float(vals[1]), float(vals[2]))
    return angles, None


def emit(nav, t_us):
    ars_raw = nav.rpy_ars()
    ahrs_raw = nav.rpy_ahrs()
    ars, ars_vel = _as_attitude(ars_raw, "ARS")
    ahrs, ahrs_vel = _as_attitude(ahrs_raw, "AHRS")
    ars_std = nav.rpy_stddev_ars()
    ahrs_std = nav.rpy_stddev_ahrs()
    ars_bias = nav.bias_gyr_ars()
    ahrs_bias = nav.bias_gyr_ahrs()
    vel = nav.velocity_ned()
    ars_ok = 1 if ars is not None else 0
    ahrs_ok = 1 if ahrs is not None else 0
    ars_vel_ok = 1 if ars_vel is not None else 0
    ahrs_vel_ok = 1 if ahrs_vel is not None else 0
    ars_std_ok = 1 if ars_std is not None else 0
    ahrs_std_ok = 1 if ahrs_std is not None else 0
    ars_bias_ok = 1 if ars_bias is not None else 0
    ahrs_bias_ok = 1 if ahrs_bias is not None else 0
    vel_ok = 1 if vel is not None else 0
    zaru = 1 if nav.zaru_active() else 0
    def fmt(ok, vec):
        if not ok:
            return "-"
        return "%.9g,%.9g,%.9g" % (vec[0], vec[1], vec[2])
    # The navigator does not publish the attitude filter's error-state
    # count or its invalid-input counter. Leave ars_n / ahrs_n /
    # ars_n_invalid off this line. The C suite probe reports the
    # error-state count and the ARS instance's invalid-input counter.
    # Do not invent either from the angle read.
    print(
        "SNAP t_us=%d ars=%d ahrs=%d ars_att=%s ahrs_att=%s "
        "ars_std=%d ars_att_std=%s ahrs_std=%d ahrs_att_std=%s "
        "zaru=%d vel=%d vel_ned=%s ars_bias=%d ars_gyr=%s "
        "ahrs_bias=%d ahrs_gyr=%s "
        "ars_vel=%d ars_vned=%s ahrs_vel=%d ahrs_vned=%s"
        % (
            t_us,
            ars_ok,
            ahrs_ok,
            fmt(ars_ok, ars),
            fmt(ahrs_ok, ahrs),
            ars_std_ok,
            fmt(ars_std_ok, ars_std),
            ahrs_std_ok,
            fmt(ahrs_std_ok, ahrs_std),
            zaru,
            vel_ok,
            fmt(vel_ok, vel),
            ars_bias_ok,
            fmt(ars_bias_ok, ars_bias),
            ahrs_bias_ok,
            fmt(ahrs_bias_ok, ahrs_bias),
            ars_vel_ok,
            fmt(ars_vel_ok, ars_vel),
            ahrs_vel_ok,
            fmt(ahrs_vel_ok, ahrs_vel),
        )
    )

header = sys.stdin.readline()
if not header:
    raise SystemExit("missing suite cfg")
parts = header.split()
if len(parts) != 8:
    raise SystemExit("suite cfg fields")
lat, lon, h = [float(x) for x in parts[0:3]]
auto_init = int(float(parts[3]))
prescribed = int(float(parts[4]))
yaw_hint = float(parts[5])
yaw_std = float(parts[6])
velocity_blind_disable = int(float(parts[7]))
cfg_kw = dict(
    auto_init=bool(auto_init) and not prescribed,
    lat_rad=math.radians(lat),
    lon_rad=math.radians(lon),
    h_m=h,
    allow_unlimited_deadreckoning=True,
    auto_zupt_velocity_blind_disable=bool(velocity_blind_disable),
)
if prescribed:
    cfg_kw["auto_init"] = False
    cfg_kw["rpy_init_rad"] = (0.0, 0.0, yaw_hint)
try:
    nav = Navigator(Config(**cfg_kw))
except ValueError:
    print("INIT rc=-1")
    print(
        "SNAP t_us=0 ars=0 ahrs=0 ars_att=- ahrs_att=- "
        "ars_std=0 ars_att_std=- ahrs_std=0 ahrs_att_std=- "
        "zaru=0 vel=0 vel_ned=- ars_bias=0 ars_gyr=- "
        "ahrs_bias=0 ahrs_gyr=- "
        "ars_vel=0 ars_vned=- ahrs_vel=0 ahrs_vned=-"
    )
    raise SystemExit(0)
print("INIT rc=0")
if (not prescribed) and yaw_std > 0.0:
    nav.set_init_att_hint(yaw_rad=yaw_hint, stddev_yaw_rad=yaw_std)
emit(nav, 0)
for raw in sys.stdin:
    if not raw.strip() or raw.startswith("#"):
        continue
    tok = raw.split()
    if not tok or tok[0] != "E":
        raise SystemExit("suite epoch tag")
    if len(tok) not in (13, 17, 21):
        raise SystemExit("suite epoch fields")
    t_us = int(tok[1])
    acc_flag = int(float(tok[2]))
    acc = (float(tok[3]), float(tok[4]), float(tok[5]))
    gyr = (float(tok[6]), float(tok[7]), float(tok[8]))
    mag_flag = int(float(tok[9]))
    mag = (float(tok[10]), float(tok[11]), float(tok[12]))
    if acc_flag not in (0, 1):
        raise SystemExit("accelerometer flag")
    # imu() writes the specific-force sample and the gyro together, both
    # present. It cannot mark a finite triple as not a sample, and a
    # non-finite triple is the drop, not that withhold. Epochs that run
    # here push the sample they were given, then update and read.
    if not acc_flag:
        raise SystemExit(
            "published navigator push cannot withhold a specific-force sample"
        )
    nav.imu(t_us, 0.01, acc, gyr)
    if mag_flag:
        nav.mag(mag, (1.0, 1.0, 1.0))
    if len(tok) in (17, 21) and int(float(tok[13])):
        nav.gnss_vel(
            (float(tok[14]), float(tok[15]), float(tok[16])),
            (0.04, 0.04, 0.04),
        )
    if len(tok) == 21 and int(float(tok[17])):
        nav.gnss_pos(
            (float(tok[18]), float(tok[19]), float(tok[20])),
            (1.0, 1.0, 1.0),
        )
    nav.update()
    emit(nav, t_us)
"""


def _tok(v: float) -> str:
    if math.isnan(v):
        return "nan"
    if math.isinf(v):
        return "inf" if v > 0.0 else "-inf"
    return f"{v:.17g}"


@dataclass
class AttCmd:
    tag: str
    t_us: int = 0
    acc: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # False: this epoch has no accelerometer sample. The placeholder acc
    # triple is not fed to the filter.
    acc_valid: bool = True
    gyr: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mag: tuple[float, float, float] | None = None
    zaru: bool = False
    lat_deg: float = 0.0
    lon_deg: float = 0.0
    year: float = 0.0


@dataclass
class AttScenario:
    mode: int
    rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)
    std: tuple[float, float, float] = (MANDATORY_STD_RAD, MANDATORY_STD_RAD, 0.0)
    t_init: int = 0
    mag_check: bool = False
    mag_tol: float = 0.0
    cmds: list[AttCmd] = field(default_factory=list)
    # Precision-restart watchdog fields of ahrs_config_t. All zero is the
    # zeroed config (watchdog on, documented default thresholds/warm-up).
    restart_disable: bool = False
    restart_att_std: tuple[float, float, float] = (0.0, 0.0, 0.0)
    restart_warmup_s: float = 0.0


@dataclass
class AttSnapshot:
    t_us: int
    rpy_ok: bool
    att: tuple[float, float, float] | None
    bias_ok: bool
    gyr_bias: tuple[float, float, float] | None
    std_ok: bool
    att_std: tuple[float, float, float] | None
    n_invalid: int
    vel_ok: bool
    att_vel: tuple[float, float, float] | None


@dataclass
class AttRun:
    init_ok: bool
    snaps: list[AttSnapshot]

    def last(self) -> AttSnapshot:
        if not self.snaps:
            raise HarnessError("attitude run has no snapshots")
        return self.snaps[-1]


@dataclass
class SuiteEpoch:
    t_us: int
    acc: tuple[float, float, float]
    gyr: tuple[float, float, float]
    # False: this epoch has no accelerometer sample.
    acc_valid: bool = True
    mag: tuple[float, float, float] | None = None
    # GNSS velocity in north, east, down [m/s]. Absent means no GNSS sample.
    gnss_vel: tuple[float, float, float] | None = None
    # GNSS position in ECEF [m]. Absent means no position sample.
    gnss_ecef: tuple[float, float, float] | None = None


@dataclass
class SuiteScenario:
    lat_deg: float
    lon_deg: float
    h_m: float
    auto_init: bool = True
    prescribed: bool = False
    yaw_hint: float = 0.0
    yaw_std: float = 0.0
    # Drop the velocity-blind ARS/AHRS stillness detector so the published
    # zero-rotation flag is the INS standstill detector (or the caller flag).
    velocity_blind_disable: bool = False
    epochs: list[SuiteEpoch] = field(default_factory=list)


@dataclass
class SuiteSnapshot:
    t_us: int
    ars_ok: bool
    ahrs_ok: bool
    ars_att: tuple[float, float, float] | None
    ahrs_att: tuple[float, float, float] | None
    ars_std_ok: bool
    ahrs_std_ok: bool
    ars_std: tuple[float, float, float] | None
    ahrs_std: tuple[float, float, float] | None
    zaru: bool
    vel_ok: bool
    vel_ned: tuple[float, float, float] | None
    ars_bias_ok: bool
    ars_bias: tuple[float, float, float] | None
    ahrs_bias_ok: bool
    ahrs_bias: tuple[float, float, float] | None
    # Velocity published on the attitude solution itself, or None when
    # that solution did not carry one. Not the navigation-filter velocity.
    ars_att_vel: tuple[float, float, float] | None
    ahrs_att_vel: tuple[float, float, float] | None
    # Active error-state count from the C suite instance, or None when the
    # Python navigator did not report one.
    ars_n: int | None
    ahrs_n: int | None
    # ARS attitude instance's invalid-input counter from the C suite
    # probe, or None when this line did not carry that field. The Python
    # navigator does not publish it. Not the error-state size.
    ars_n_invalid: int | None = None


@dataclass
class SuiteRun:
    init_ok: bool
    snaps: list[SuiteSnapshot]

    def last(self) -> SuiteSnapshot:
        if not self.snaps:
            raise HarnessError("suite run has no snapshots")
        return self.snaps[-1]


def att_hold(
    *,
    t0_us: int,
    duration_s: float,
    acc: Sequence[float] | None,
    gyr: Sequence[float],
    mag: Sequence[float] | None = None,
    zaru: bool = False,
    acc_at=None,
    imu_hz: int = IMU_HZ,
) -> list[AttCmd]:
    if imu_hz <= 0 or duration_s <= 0.0:
        raise HarnessError("attitude hold needs a positive rate and duration")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    if n <= 0:
        raise HarnessError("attitude hold produced no epochs")
    acc_present = acc is not None or acc_at is not None
    if acc is None:
        acc_t = (0.0, 0.0, 0.0)
    else:
        acc_t = (float(acc[0]), float(acc[1]), float(acc[2]))
    gyr_t = (float(gyr[0]), float(gyr[1]), float(gyr[2]))
    mag_t = None if mag is None else (float(mag[0]), float(mag[1]), float(mag[2]))
    out: list[AttCmd] = []
    for i in range(1, n + 1):
        t_us = t0_us + int(round(i * dt * 1e6))
        if acc_at is None:
            acc_i = acc_t
            present = acc_present
        else:
            acc_i = tuple(float(v) for v in acc_at(i))
            present = True
        out.append(
            AttCmd(
                tag="E",
                t_us=t_us,
                acc=acc_i,
                acc_valid=present,
                gyr=gyr_t,
                mag=mag_t,
                zaru=zaru,
            )
        )
    return out


def mag_zrate_hold(
    *,
    duration_s: float,
    omega_z: float,
    mag_yaw: float,
    mag_ned: Sequence[float] = (22.0, 0.0, 40.0),
    t0_us: int = 0,
) -> list[AttCmd]:
    """Level specific force, one constant z-rate, one magnetometer heading."""
    mag = body_mag_for_yaw(0.0, 0.0, mag_yaw, mag_ned)
    return att_hold(
        t0_us=t0_us,
        duration_s=duration_s,
        acc=SPECIFIC_FORCE_LEVEL,
        gyr=(0.0, 0.0, omega_z),
        mag=mag,
    )


def att_pos(lat_deg: float, lon_deg: float, year: float) -> AttCmd:
    return AttCmd(tag="P", lat_deg=lat_deg, lon_deg=lon_deg, year=year)


def encode_att(scen: AttScenario) -> str:
    cfg_line = f"{scen.mode} {int(scen.mag_check)} {_tok(scen.mag_tol)}"
    if (
        scen.restart_disable
        or any(float(v) != 0.0 for v in scen.restart_att_std)
        or float(scen.restart_warmup_s) != 0.0
    ):
        cfg_line += (
            f" {int(scen.restart_disable)} {_tok(scen.restart_att_std[0])} "
            f"{_tok(scen.restart_att_std[1])} {_tok(scen.restart_att_std[2])} "
            f"{_tok(scen.restart_warmup_s)}"
        )
    lines = [
        "FILTER",
        cfg_line,
        f"{scen.t_init} {_tok(scen.rpy[0])} {_tok(scen.rpy[1])} {_tok(scen.rpy[2])} "
        f"{_tok(scen.std[0])} {_tok(scen.std[1])} {_tok(scen.std[2])}",
    ]
    for cmd in scen.cmds:
        if cmd.tag == "P":
            lines.append(
                f"P {_tok(cmd.lat_deg)} {_tok(cmd.lon_deg)} {_tok(cmd.year)}"
            )
            continue
        mag = cmd.mag if cmd.mag is not None else (0.0, 0.0, 0.0)
        mag_flag = 1 if cmd.mag is not None else 0
        acc_flag = 1 if cmd.acc_valid else 0
        lines.append(
            "E %d %d %s %s %s %s %s %s %d %s %s %s %d"
            % (
                cmd.t_us,
                acc_flag,
                _tok(cmd.acc[0]),
                _tok(cmd.acc[1]),
                _tok(cmd.acc[2]),
                _tok(cmd.gyr[0]),
                _tok(cmd.gyr[1]),
                _tok(cmd.gyr[2]),
                mag_flag,
                _tok(mag[0]),
                _tok(mag[1]),
                _tok(mag[2]),
                int(cmd.zaru),
            )
        )
    return "\n".join(lines) + "\n"


def parse_att_snapshot(line: str) -> AttSnapshot:
    if not line.startswith("SNAP "):
        raise HarnessError(f"not a SNAP line: {line!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad SNAP token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    rpy_ok = _parse_flag(fields, "rpy")
    bias_ok = _parse_flag(fields, "bias")
    std_ok = _parse_flag(fields, "std")
    n_invalid = _parse_int(fields, "n_invalid")
    if n_invalid < 0:
        note_product_issue("F06", f"n_invalid missing or negative: {line}")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F06', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F06', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F06', f"ins_get_diag returned NULL for a live instance: {line}")
    vel_ok = _parse_flag(fields, "vel")
    return AttSnapshot(
        t_us=_parse_int(fields, "t_us"),
        rpy_ok=rpy_ok,
        att=_parse_vec(fields, "att", rpy_ok),
        bias_ok=bias_ok,
        gyr_bias=_parse_vec(fields, "gyr", bias_ok),
        std_ok=std_ok,
        att_std=_parse_vec(fields, "att_std", std_ok),
        n_invalid=n_invalid,
        vel_ok=vel_ok,
        att_vel=_parse_vec(fields, "att_vel", vel_ok),
    )


def parse_att_run(text: str) -> AttRun:
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
    snaps = [parse_att_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    return AttRun(init_ok=(rc == 0), snaps=snaps)


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


def _c_string_token(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


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


def _attitude_c_source(ident) -> str:
    """C probe linked to the shared object ``make pylib`` wrote.

    The attitude survey keeps the loaded object whose basename is that
    file. A missing object fails inside the test, not at collection.
    """
    library = ident.library
    assert library is not None and library.is_file()
    return _C_PROBE


def _suite_py_source(ident) -> str:
    """Python suite probe that imports the package ``make pylib`` wrote."""
    source = _PY_SUITE_PROBE.replace("__PKG__", ident.package_name)
    if "__PKG__" in source:
        raise HarnessError("suite probe did not receive the compiled package name")
    return source


def _invoke_c(stdin: str):
    ident = _require_compiled_product()
    return invoke(_attitude_c_source(ident), stdin=stdin, timeout=ATT_TIMEOUT)


def c_att_run(scen: AttScenario) -> AttRun:
    result = _invoke_c(encode_att(scen))
    text = require_probe_success(result)
    run = parse_att_run(text)
    print(
        f"att init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_rpy={run.last().rpy_ok if run.snaps else None}",
        flush=True,
    )
    return run


def c_leveling(acc: Sequence[float]) -> tuple[float, float]:
    payload = f"LEVEL\n{_tok(float(acc[0]))} {_tok(float(acc[1]))} {_tok(float(acc[2]))}\n"
    result = _invoke_c(payload)
    text = require_probe_success(result).strip()
    if not text.startswith("LEVEL "):
        raise HarnessError(f"leveling probe stdout is not LEVEL: {text!r}")
    fields: dict[str, str] = {}
    for token in text[6:].split():
        if "=" not in token:
            raise HarnessError(f"bad LEVEL token {token!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    if "roll" not in fields or "pitch" not in fields:
        raise HarnessError(f"LEVEL missing roll/pitch: {text!r}")
    try:
        roll = float(fields["roll"])
        pitch = float(fields["pitch"])
    except ValueError as exc:
        raise HarnessError(f"LEVEL not floats: {text!r}") from exc
    if not math.isfinite(roll) or not math.isfinite(pitch):
        raise HarnessError(f"LEVEL non-finite: {text!r}")
    print(f"leveling roll={roll} pitch={pitch}", flush=True)
    return roll, pitch


def _parse_heading_line(text: str) -> float:
    line = text.strip()
    if not line.startswith("HEAD "):
        raise HarnessError(f"heading probe stdout is not HEAD: {text!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad HEAD token {token!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    if "yaw" not in fields:
        raise HarnessError(f"HEAD missing yaw: {text!r}")
    try:
        yaw = float(fields["yaw"])
    except ValueError as exc:
        raise HarnessError(f"HEAD yaw not a float: {text!r}") from exc
    if not math.isfinite(yaw):
        raise AssertionError(f"heading helper returned a non-finite yaw: {text!r}")
    return yaw


def heading_ignoring_tilt(mag: Sequence[float]) -> float:
    """Heading of the body sample read as if roll and pitch were zero.

    This is not tilt compensation. It raises when the horizontal field
    vanishes or the result is not finite, so a failed read is not a yaw.
    """
    if len(mag) != 3:
        raise HarnessError("magnetometer sample must have 3 components")
    mx, my, mz = (float(mag[0]), float(mag[1]), float(mag[2]))
    if not all(math.isfinite(v) for v in (mx, my, mz)):
        raise HarnessError("magnetometer sample is not finite")
    if mx == 0.0 and my == 0.0:
        raise HarnessError(
            "heading that ignored the tilt is undefined: horizontal field vanished"
        )
    yaw = math.atan2(-my, mx)
    if not math.isfinite(yaw):
        raise HarnessError("heading that ignored the tilt is not finite")
    return yaw


def c_mag_heading(
    mag: Sequence[float], roll: float, pitch: float
) -> float:
    payload = (
        f"HEAD\n{_tok(float(mag[0]))} {_tok(float(mag[1]))} {_tok(float(mag[2]))} "
        f"{_tok(roll)} {_tok(pitch)}\n"
    )
    result = _invoke_c(payload)
    yaw = _parse_heading_line(require_probe_success(result))
    print(f"C heading yaw={yaw}", flush=True)
    return yaw


def py_mag_heading(
    mag: Sequence[float], roll: float, pitch: float
) -> float:
    payload = (
        f"{_tok(float(mag[0]))} {_tok(float(mag[1]))} {_tok(float(mag[2]))} "
        f"{_tok(roll)} {_tok(pitch)}\n"
    )
    _require_compiled_product()
    result = run_python(_PY_HEAD_PROBE, stdin=payload, timeout=ATT_TIMEOUT)
    yaw = _parse_heading_line(require_probe_success(result))
    print(f"Python heading yaw={yaw}", flush=True)
    return yaw


def encode_suite(scen: SuiteScenario) -> str:
    lines = [
        "SUITE",
        f"{scen.lat_deg:.17g} {scen.lon_deg:.17g} {scen.h_m:.17g} "
        f"{int(scen.auto_init)} {int(scen.prescribed)} {_tok(scen.yaw_hint)} "
        f"{_tok(scen.yaw_std)} {int(scen.velocity_blind_disable)}",
    ]
    for e in scen.epochs:
        mag = e.mag if e.mag is not None else (0.0, 0.0, 0.0)
        mag_flag = 1 if e.mag is not None else 0
        acc_flag = 1 if e.acc_valid else 0
        if e.gnss_vel is None:
            gnss = (0, 0.0, 0.0, 0.0)
        else:
            gnss = (1, float(e.gnss_vel[0]), float(e.gnss_vel[1]), float(e.gnss_vel[2]))
        base = (
            "E %d %d %s %s %s %s %s %s %d %s %s %s"
            % (
                e.t_us,
                acc_flag,
                _tok(e.acc[0]),
                _tok(e.acc[1]),
                _tok(e.acc[2]),
                _tok(e.gyr[0]),
                _tok(e.gyr[1]),
                _tok(e.gyr[2]),
                mag_flag,
                _tok(mag[0]),
                _tok(mag[1]),
                _tok(mag[2]),
            )
        )
        if e.gnss_ecef is not None or e.gnss_vel is not None:
            base += " %d %s %s %s" % (
                gnss[0],
                _tok(gnss[1]),
                _tok(gnss[2]),
                _tok(gnss[3]),
            )
        if e.gnss_ecef is not None:
            base += " 1 %s %s %s" % (
                _tok(e.gnss_ecef[0]),
                _tok(e.gnss_ecef[1]),
                _tok(e.gnss_ecef[2]),
            )
        lines.append(base)
    return "\n".join(lines) + "\n"


def parse_suite_snapshot(line: str) -> SuiteSnapshot:
    if not line.startswith("SNAP "):
        raise HarnessError(f"not a SNAP line: {line!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad SNAP token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    ars_ok = _parse_flag(fields, "ars")
    ahrs_ok = _parse_flag(fields, "ahrs")
    ars_std_ok = _parse_flag(fields, "ars_std")
    ahrs_std_ok = _parse_flag(fields, "ahrs_std")
    vel_ok = _parse_flag(fields, "vel")
    ars_bias_ok = _parse_flag(fields, "ars_bias")
    ahrs_bias_ok = _parse_flag(fields, "ahrs_bias")
    ars_att_vel_ok = _parse_flag(fields, "ars_vel")
    ahrs_att_vel_ok = _parse_flag(fields, "ahrs_vel")
    ars_n = _parse_int(fields, "ars_n") if "ars_n" in fields else None
    ahrs_n = _parse_int(fields, "ahrs_n") if "ahrs_n" in fields else None
    ars_n_invalid = None
    if "ars_n_invalid" in fields:
        ars_n_invalid = _parse_int(fields, "ars_n_invalid")
        if ars_n_invalid < 0:
            note_product_issue("F06", f"ars_n_invalid missing or negative: {line}")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F06', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F06', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F06', f"ins_get_diag returned NULL for a live instance: {line}")
    return SuiteSnapshot(
        t_us=_parse_int(fields, "t_us"),
        ars_ok=ars_ok,
        ahrs_ok=ahrs_ok,
        ars_att=_parse_vec(fields, "ars_att", ars_ok),
        ahrs_att=_parse_vec(fields, "ahrs_att", ahrs_ok),
        ars_std_ok=ars_std_ok,
        ahrs_std_ok=ahrs_std_ok,
        ars_std=_parse_vec(fields, "ars_att_std", ars_std_ok),
        ahrs_std=_parse_vec(fields, "ahrs_att_std", ahrs_std_ok),
        zaru=_parse_flag(fields, "zaru"),
        vel_ok=vel_ok,
        vel_ned=_parse_vec(fields, "vel_ned", vel_ok),
        ars_bias_ok=ars_bias_ok,
        ars_bias=_parse_vec(fields, "ars_gyr", ars_bias_ok),
        ahrs_bias_ok=ahrs_bias_ok,
        ahrs_bias=_parse_vec(fields, "ahrs_gyr", ahrs_bias_ok),
        ars_att_vel=_parse_vec(fields, "ars_vned", ars_att_vel_ok),
        ahrs_att_vel=_parse_vec(fields, "ahrs_vned", ahrs_att_vel_ok),
        ars_n=ars_n,
        ahrs_n=ahrs_n,
        ars_n_invalid=ars_n_invalid,
    )


def parse_suite_run(text: str) -> SuiteRun:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    init_lines = [ln for ln in lines if ln.startswith("INIT ")]
    if len(init_lines) != 1:
        raise HarnessError(f"suite stdout has {len(init_lines)} INIT lines")
    fields = dict(
        token.split("=", 1) for token in init_lines[0][5:].split() if "=" in token
    )
    if "rc" not in fields:
        raise HarnessError(f"INIT missing rc: {init_lines[0]!r}")
    try:
        rc = int(fields["rc"])
    except ValueError as exc:
        raise HarnessError(f"INIT rc not an int: {init_lines[0]!r}") from exc
    snaps = [parse_suite_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    return SuiteRun(init_ok=(rc == 0), snaps=snaps)


def _run_suite(kind: str, scen: SuiteScenario) -> SuiteRun:
    payload = encode_suite(scen)
    ident = _require_compiled_product()
    if kind == "c":
        result = invoke(_attitude_c_source(ident), stdin=payload, timeout=ATT_TIMEOUT)
    elif kind == "py":
        # Python child consumes the SUITE header's following cfg line as stdin.
        body = "\n".join(payload.splitlines()[1:]) + "\n"
        result = run_python(_suite_py_source(ident), stdin=body, timeout=ATT_TIMEOUT)
    else:
        raise HarnessError(f"unknown suite probe kind {kind!r}")
    text = require_probe_success(result)
    run = parse_suite_run(text)
    print(
        f"{kind} suite init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_ars={run.last().ars_ok if run.snaps else None} "
        f"last_ahrs={run.last().ahrs_ok if run.snaps else None}",
        flush=True,
    )
    return run


def c_suite_run(scen: SuiteScenario) -> SuiteRun:
    return _run_suite("c", scen)


def py_suite_run(scen: SuiteScenario) -> SuiteRun:
    return _run_suite("py", scen)


def suite_known_heading_scenarios(
    lat_deg: float,
    lon_deg: float,
    h_m: float,
    yaw_rad: float,
    epochs: list[SuiteEpoch],
    *,
    yaw_std: float,
) -> tuple[SuiteScenario, SuiteScenario, SuiteScenario]:
    """No heading, a prescribed attitude, and a static yaw hint on one IMU stream."""
    auto = SuiteScenario(lat_deg=lat_deg, lon_deg=lon_deg, h_m=h_m, epochs=epochs)
    prescribed = SuiteScenario(
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        h_m=h_m,
        auto_init=False,
        prescribed=True,
        yaw_hint=yaw_rad,
        epochs=epochs,
    )
    hinted = SuiteScenario(
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        h_m=h_m,
        yaw_hint=yaw_rad,
        yaw_std=yaw_std,
        epochs=epochs,
    )
    return auto, prescribed, hinted


def suite_imu_stream(
    *,
    duration_s: float,
    acc: Sequence[float] | None = SPECIFIC_FORCE_LEVEL,
    gyr: Sequence[float] = (0.0, 0.0, 0.0),
    mag: Sequence[float] | None = None,
    gnss_vel: Sequence[float] | None = None,
    gnss_ecef: Sequence[float] | None = None,
    acc_at=None,
    t0_us: int = 0,
    imu_hz: int = IMU_HZ,
) -> list[SuiteEpoch]:
    if imu_hz <= 0 or duration_s <= 0.0:
        raise HarnessError("suite stream needs a positive rate and duration")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    acc_present = acc is not None or acc_at is not None
    if acc is None:
        acc_t = (0.0, 0.0, 0.0)
    else:
        acc_t = (float(acc[0]), float(acc[1]), float(acc[2]))
    gyr_t = (float(gyr[0]), float(gyr[1]), float(gyr[2]))
    mag_t = None if mag is None else (float(mag[0]), float(mag[1]), float(mag[2]))
    vel_t = None if gnss_vel is None else (
        float(gnss_vel[0]), float(gnss_vel[1]), float(gnss_vel[2])
    )
    ecef_t = None if gnss_ecef is None else (
        float(gnss_ecef[0]), float(gnss_ecef[1]), float(gnss_ecef[2])
    )
    out: list[SuiteEpoch] = []
    for i in range(1, n + 1):
        t_us = t0_us + int(round(i * dt * 1e6))
        if acc_at is None:
            acc_i = acc_t
            present = acc_present
        else:
            acc_i = tuple(float(v) for v in acc_at(i))
            present = True
        out.append(
            SuiteEpoch(
                t_us=t_us,
                acc=acc_i,
                acc_valid=present,
                gyr=gyr_t,
                mag=mag_t,
                gnss_vel=vel_t,
                gnss_ecef=ecef_t,
            )
        )
    return out


def ahrs_std() -> tuple[float, float, float]:
    return (MANDATORY_STD_RAD, MANDATORY_STD_RAD, AHRS_YAW_STD_RAD)


def ars_std() -> tuple[float, float, float]:
    return (MANDATORY_STD_RAD, MANDATORY_STD_RAD, 0.0)


def require_snap_at(snaps: Sequence[AttSnapshot], t_us: int, what: str) -> AttSnapshot:
    """The snapshot published at one timestamp.

    A missing snapshot is not an attitude. Callers that name a dropped
    epoch must not ask for that timestamp: a drop leaves no attitude there.
    """
    found = [snap for snap in snaps if snap.t_us == t_us]
    if not found:
        raise HarnessError(f"{what}: no snapshot at t_us={t_us}")
    return found[0]


def require_att(snap: AttSnapshot, what: str) -> tuple[float, float, float]:
    if not snap.rpy_ok or snap.att is None:
        raise AssertionError(f"{what}: attitude accessors failed")
    return snap.att


def require_bias(snap: AttSnapshot, what: str) -> tuple[float, float, float]:
    if not snap.bias_ok or snap.gyr_bias is None:
        raise AssertionError(f"{what}: gyro-bias accessors failed")
    return snap.gyr_bias


def yaw_separations(yaw: float, anchor: float, other: float) -> tuple[float, float]:
    """Angular distance of a published yaw to two reference headings.

    A non-finite angle is not a separation. Callers assert which distance
    is smaller; this helper does not pick a tolerance.
    """
    for name, value in (("yaw", yaw), ("anchor", anchor), ("other", other)):
        if not math.isfinite(value):
            raise HarnessError(f"yaw separation: {name} is not finite")
    to_anchor = abs(angle_diff_rad(yaw, anchor))
    to_other = abs(angle_diff_rad(yaw, other))
    if not math.isfinite(to_anchor) or not math.isfinite(to_other):
        raise HarnessError("yaw separation: result is not finite")
    return to_anchor, to_other


def suite_ars_as_att(snaps: Sequence[SuiteSnapshot], what: str) -> list[AttSnapshot]:
    """Suite ARS attitude and z-bias in the attitude-snapshot shape.

    A snapshot that published neither ARS attitude nor ARS bias is not an
    epoch of this integral. A published attitude with no bias stays in the
    list so the bias accessor fails instead of being treated as zero.
    """
    views: list[AttSnapshot] = []
    for snap in snaps:
        published = snap.ars_ok or snap.ars_bias_ok
        if not published:
            continue
        views.append(
            AttSnapshot(
                t_us=snap.t_us,
                rpy_ok=snap.ars_ok and snap.ars_att is not None,
                att=snap.ars_att,
                bias_ok=snap.ars_bias_ok and snap.ars_bias is not None,
                gyr_bias=snap.ars_bias,
                std_ok=False,
                att_std=None,
                n_invalid=0,
                vel_ok=False,
                att_vel=None,
            )
        )
    if len(views) < 2:
        raise HarnessError(f"{what}: need at least two published ARS snapshots")
    return views


def bias_corrected_z_integral(snaps: Sequence[AttSnapshot], omega_z: float) -> float:
    """Integrate (z-rate − this run's published z-bias) from t = 0.

    Each step uses the z-bias published on that snapshot. A missing bias
    is not treated as zero.
    """
    if not snaps:
        raise HarnessError("bias-corrected integral: no snapshots")
    total = 0.0
    prev_t = 0
    n = 0
    for snap in snaps:
        bz = require_bias(snap, "bias-corrected integral")[2]
        if snap.t_us < prev_t:
            raise HarnessError("bias-corrected integral: time went backwards")
        dt = (snap.t_us - prev_t) / 1e6
        total += (float(omega_z) - bz) * dt
        prev_t = snap.t_us
        n += 1
    if n < 2:
        raise HarnessError("bias-corrected integral: need at least two published biases")
    if not math.isfinite(total):
        raise HarnessError("bias-corrected integral: result is not finite")
    return total


def gauss(rng: random.Random) -> float:
    u1 = rng.random()
    u2 = rng.random()
    if u1 < 1e-12:
        u1 = 1e-12
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def ned_horiz_rotate_scale(
    ned: Sequence[float], phi_rad: float, k: float
) -> tuple[float, float, float]:
    n, e, d = float(ned[0]), float(ned[1]), float(ned[2])
    c, s = math.cos(phi_rad), math.sin(phi_rad)
    out = (k * (c * n - s * e), k * (s * n + c * e), k * d)
    if not all(math.isfinite(v) for v in out):
        raise HarnessError("rotated NED field is not finite")
    return out


def longitude_same_latitude_without_declination(
    lat_deg: float, year: float
) -> tuple[float, float]:
    """Longitude at this latitude whose declination stays near zero.

    Supplying that position is the same call as supplying a site that
    switches declination: same latitude, same year, no new sensor sample.
    The declination change on that call is not a switch.
    """
    best_lon = None
    best_decl = None
    for step in range(360):
        lon = -180.0 + step
        if is_public_wmm_row(lat_deg, lon):
            continue
        decl, _incl, _f = independent_wmm(lat_deg, lon, year)
        if best_decl is None or abs(decl) < abs(best_decl):
            best_lon = lon
            best_decl = decl
        if abs(decl) <= 0.5:
            print(
                f"no-switch longitude lat={lat_deg} lon={lon} D={decl}",
                flush=True,
            )
            return lon, decl
    if best_lon is None or best_decl is None or abs(best_decl) > 1.0:
        raise HarnessError(
            "could not find a same-latitude longitude that does not switch declination"
        )
    print(
        f"no-switch longitude lat={lat_deg} lon={best_lon} D={best_decl}",
        flush=True,
    )
    return best_lon, best_decl


def runtime_declination_site() -> tuple[float, float, float, float]:
    """Mid-latitude site with a usable |D|, not a public WMM table row.

    F02 ``runtime_site`` stays in the Mediterranean, where 2025 |D| is only a
    few degrees — too small to tell magnetic north from true north. Sample
    globally around bands that actually have a usable declination.
    """
    u = runtime_uuid_int()
    bands = (
        (39.0, -105.0),
        (45.5, -68.0),
        (48.5, -123.0),
        (40.5, -90.0),
        (-26.0, 28.0),
        (-33.5, 151.0),
        (-34.5, -58.5),
        (50.0, 30.0),
        (43.0, 141.0),
        (21.0, -158.0),
    )
    for i in range(64):
        base_lat, base_lon = bands[i % len(bands)]
        lat = base_lat + ((u // (i + 1)) % 700) / 100.0 - 3.5
        lon = base_lon + ((u // (i + 3)) % 900) / 100.0 - 4.5
        if abs(lat) > 54.0:
            lat = 50.0 if lat > 0.0 else -50.0
        h = 40.0 + float((u // (i + 7)) % 450)
        if is_public_wmm_row(lat, lon):
            continue
        decl, incl, f_ut = independent_wmm(lat, lon, ATT_YEAR)
        horiz = f_ut * abs(math.cos(math.radians(incl)))
        if abs(decl) >= 6.0 and horiz >= 8.0 and abs(lat) < 55.0:
            print(
                f"declination site lat={lat} lon={lon} D={decl} I={incl} F={f_ut}",
                flush=True,
            )
            return lat, lon, h, decl
    raise HarnessError("could not find a mid-latitude site with usable declination")


def runtime_z_rate_rps() -> float:
    u = runtime_uuid_int()
    dps = 8.0 + (u % 70) / 10.0
    if abs(dps - 10.0) < 0.15:
        dps = 12.4
    print(f"runtime z-rate dps={dps}", flush=True)
    return math.radians(dps)


def runtime_att_yaw_rad() -> float:
    u = runtime_uuid_int()
    yaw = 0.45 + (u % 160) / 100.0
    if abs(math.degrees(yaw) - 60.0) < 3.0:
        yaw = math.radians(41.0)
    print(f"runtime att yaw rad={yaw}", flush=True)
    return yaw


def runtime_noise_seeds() -> tuple[int, int]:
    u = runtime_uuid_int()
    a = 1 + (u % 40_000)
    b = 50_000 + ((u // 40_000) % 40_000)
    print(f"runtime noise seeds {a} {b}", flush=True)
    return a, b


def runtime_tilt_rad() -> float:
    u = runtime_uuid_int()
    deg = 8.0 + (u % 80) / 10.0
    print(f"runtime tilt deg={deg}", flush=True)
    return math.radians(deg)


def reference_stream(seed: int, *, truth_rpy=(0.0, 0.0, 0.0)) -> list[AttCmd]:
    """100 Hz static IMU with the named 10 s noise model."""
    rng = random.Random(seed)
    gyr_sigma = REF_GYR_PSD * math.sqrt(float(IMU_HZ))
    bias = tuple(math.radians(v) for v in REF_BIAS_DPS)
    acc_true = still_level_acc(truth_rpy[1], truth_rpy[0])
    dt = DT_SEC
    n = int(round(REF_DURATION_S * IMU_HZ))
    cmds: list[AttCmd] = []
    for i in range(1, n + 1):
        t_us = int(round(i * dt * 1e6))
        gyr = (
            bias[0] + gyr_sigma * gauss(rng),
            bias[1] + gyr_sigma * gauss(rng),
            bias[2] + gyr_sigma * gauss(rng),
        )
        acc = (
            acc_true[0] + REF_ACC_NOISE * gauss(rng),
            acc_true[1] + REF_ACC_NOISE * gauss(rng),
            acc_true[2] + REF_ACC_NOISE * gauss(rng),
        )
        cmds.append(AttCmd(tag="E", t_us=t_us, acc=acc, gyr=gyr))
    return cmds
