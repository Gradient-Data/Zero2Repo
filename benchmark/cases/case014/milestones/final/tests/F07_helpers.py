# feature: F07
"""Observation helpers for FP-07 standalone barometric vertical channel.

C probes compile through the sealed harness. This module does not import
the product in the pytest process. ISA expectations come from the
tropospheric international standard atmosphere named in the PRD, never
from the library's own pressure-to-altitude helper.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from _harness import (
    HarnessError,
    invoke,
    runtime_uuid_int,
    nonfinite_fields,
    note_product_issue,
)
from F01_helpers import hamilton_zyx_quaternion, require_probe_success
from F02_helpers import (
    DT_SEC,
    IMU_HZ,
    LONG_TIMEOUT,
    SPECIFIC_FORCE_LEVEL,
    _parse_flag,
    _parse_int,
    _parse_optional_float,
    runtime_site,
)
from F03_helpers import G_MPS2, still_level_acc

# Fixed inputs and tolerances for FP-07.
ISA_P0_PA = 101325.0
ISA_FEW_HUNDRED_TOL_M = 1.0
BARO_1SIGMA_DEFAULT_M = 2.0
GAP_NAMED_NOT_OUTAGE_S = 0.3
GAP_JUST_UNDER_S = 0.48
GAP_JUST_OVER_S = 0.52
# Reverse-epoch gap: long enough that 0.5·a·Δt² exceeds the skip bound, short
# of the 0.5 s forward-outage cap so an |dt| integrator still predicts.
GAP_BACKWARDS_S = 0.40
VERT_TIMEOUT = LONG_TIMEOUT

# Independent tropospheric ISA constants. Not the product's rounded
# scale/exponent pair.
_ISA_T0_K = 288.15
_ISA_LAPSE_K_PER_M = 0.0065
_ISA_G0_MPS2 = 9.80665
_ISA_R_J_PER_KG_K = 287.05287

_IDENTITY_QUAT = hamilton_zyx_quaternion(0.0, 0.0, 0.0)

_C_PROBE = r"""
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "baro_alt.h"
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

static void print_vert_snap(const baro_alt_t *b, long long t_us)
{
    float h = 0.0f, v = 0.0f, isa = 0.0f;
    int h_ok = baro_alt_get_height(b, &h) ? 1 : 0;
    int v_ok = baro_alt_get_velocity(b, &v) ? 1 : 0;
    int isa_ok = baro_alt_get_isa_altitude(b, &isa) ? 1 : 0;
    printf("SNAP t_us=%lld h_ok=%d v_ok=%d isa_ok=%d", t_us, h_ok, v_ok, isa_ok);
    if (h_ok) {
        printf(" h=%.9g", h);
    } else {
        printf(" h=-");
    }
    if (v_ok) {
        printf(" v=%.9g", v);
    } else {
        printf(" v=-");
    }
    if (isa_ok) {
        printf(" isa=%.9g", isa);
    } else {
        printf(" isa=-");
    }
    printf(" n_invalid=%u\n", b->n_invalid_input);
}

static void print_off_snap(const local_gnss_alt_t *g, long long t_us)
{
    float off = 0.0f, std = 0.0f;
    int ok = local_gnss_alt_get(g, &off, &std) ? 1 : 0;
    if (ok) {
    }
    printf("SNAP t_us=%lld get_ok=%d", t_us, ok);
    if (ok) {
        printf(" offset=%.9g std=%.9g", off, std);
    } else {
        printf(" offset=- std=-");
    }
    printf(" n_invalid=%u\n", g->n_invalid_input);
}

static void print_chan_snap(const nav_suite_t *s, long long t_us)
{
    float h = 0.0f, v = 0.0f;
    int h_ok = baro_alt_get_height(&s->baro_alt, &h) ? 1 : 0;
    int v_ok = baro_alt_get_velocity(&s->baro_alt, &v) ? 1 : 0;
    printf("SNAP t_us=%lld h_ok=%d v_ok=%d", t_us, h_ok, v_ok);
    if (h_ok) {
        printf(" h=%.9g", h);
    } else {
        printf(" h=-");
    }
    if (v_ok) {
        printf(" v=%.9g", v);
    } else {
        printf(" v=-");
    }
    printf("\n");
}

static int run_filter(void)
{
    char line[4096];
    char *tok[16];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("filter init");
    }
    int n = split_ws(line, tok, 16);
    if (n != 5 && n != 6) {
        return fail_read("filter init fields");
    }
    long long t_init = 0;
    float pressure = 0.0f, h_init = 0.0f, h_std = 0.0f, baro_std = 0.0f;
    if (!parse_ll(tok[0], &t_init) || !parse_f(tok[1], &pressure) ||
        !parse_f(tok[2], &h_init) || !parse_f(tok[3], &h_std) ||
        !parse_f(tok[4], &baro_std)) {
        return fail_read("filter init numbers");
    }
    /* Optional 6th field: baro_alt_config_t precision_restart_disable. */
    float restart_off = 0.0f;
    if (n == 6 && !parse_f(tok[5], &restart_off)) {
        return fail_read("filter init restart flag");
    }

    baro_alt_t b;
    memset(&b, 0, sizeof b);
    baro_alt_config_t cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.baro_stddev_m = baro_std;
    cfg.precision_restart_disable = ((int)restart_off) ? true : false;
    int rc = baro_alt_init(&b, &cfg, (baro_alt_time_us_t)t_init, pressure, h_init, h_std);
    printf("INIT rc=%d\n", rc);
    print_vert_snap(&b, t_init);
    if (rc != 0) {
        /* A refused init still accepts later REINIT / epoch lines so a
           caller-reinit arm can share one process. Epochs on a refused
           instance are classified by accessors, not by a probe abort. */
    }

    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 16);
        if (n < 1) {
            continue;
        }
        if (tok[0][0] == 'R' && tok[0][1] == '\0') {
            if (n != 4) {
                return fail_read("reinit fields");
            }
            long long t_us = 0;
            float p = 0.0f, h0 = 0.0f;
            if (!parse_ll(tok[1], &t_us) || !parse_f(tok[2], &p) ||
                !parse_f(tok[3], &h0)) {
                return fail_read("reinit numbers");
            }
            rc = baro_alt_init(&b, &cfg, (baro_alt_time_us_t)t_us, p, h0, h_std);
            printf("REINIT rc=%d\n", rc);
            print_vert_snap(&b, t_us);
            continue;
        }
        if (tok[0][0] != 'E' || tok[0][1] != '\0') {
            return fail_read("epoch tag");
        }
        if (n != 12) {
            return fail_read("epoch fields");
        }
        long long t_us = 0;
        float ax, ay, az, qw, qx, qy, qz, p, barof, zuptf;
        if (!parse_ll(tok[1], &t_us) || !parse_f(tok[2], &ax) ||
            !parse_f(tok[3], &ay) || !parse_f(tok[4], &az) ||
            !parse_f(tok[5], &qw) || !parse_f(tok[6], &qx) ||
            !parse_f(tok[7], &qy) || !parse_f(tok[8], &qz) ||
            !parse_f(tok[9], &p) || !parse_f(tok[10], &barof) ||
            !parse_f(tok[11], &zuptf)) {
            return fail_read("epoch numbers");
        }
        float acc[3] = {ax, ay, az};
        float q[4] = {qw, qx, qy, qz};
        baro_alt_update(&b, (baro_alt_time_us_t)t_us, acc, q, p, 0.0f,
                        ((int)barof) ? true : false);
        if ((int)zuptf) {
            baro_alt_zero_velocity_update(&b, 0.0f);
        }
        print_vert_snap(&b, t_us);
    }
    return 0;
}

static int run_offset(void)
{
    char line[4096];
    char *tok[16];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("offset init");
    }
    int n = split_ws(line, tok, 16);
    if (n != 5) {
        return fail_read("offset init fields");
    }
    long long t_init = 0;
    float h_local = 0.0f, local_std = 0.0f, h_ell = 0.0f, gnss_std = 0.0f;
    if (!parse_ll(tok[0], &t_init) || !parse_f(tok[1], &h_local) ||
        !parse_f(tok[2], &local_std) || !parse_f(tok[3], &h_ell) ||
        !parse_f(tok[4], &gnss_std)) {
        return fail_read("offset init numbers");
    }

    local_gnss_alt_t g;
    memset(&g, 0, sizeof g);
    local_gnss_alt_config_t cfg;
    memset(&cfg, 0, sizeof cfg);
    int rc = local_gnss_alt_init(&g, &cfg, (baro_alt_time_us_t)t_init, h_local,
                                 local_std, h_ell, gnss_std);
    printf("INIT rc=%d\n", rc);
    print_off_snap(&g, t_init);

    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 16);
        if (n < 1) {
            continue;
        }
        if (tok[0][0] == 'G' && tok[0][1] == '\0') {
            if (n != 2) {
                return fail_read("offset get fields");
            }
            long long t_us = 0;
            if (!parse_ll(tok[1], &t_us)) {
                return fail_read("offset get time");
            }
            print_off_snap(&g, t_us);
            continue;
        }
        if (tok[0][0] != 'E' || tok[0][1] != '\0') {
            return fail_read("offset epoch tag");
        }
        if (n != 6) {
            return fail_read("offset epoch fields");
        }
        long long t_us = 0;
        if (!parse_ll(tok[1], &t_us) || !parse_f(tok[2], &h_local) ||
            !parse_f(tok[3], &local_std) || !parse_f(tok[4], &h_ell) ||
            !parse_f(tok[5], &gnss_std)) {
            return fail_read("offset epoch numbers");
        }
        local_gnss_alt_update(&g, (baro_alt_time_us_t)t_us, h_local, local_std,
                              h_ell, gnss_std);
        print_off_snap(&g, t_us);
    }
    return 0;
}

static int run_suite(void)
{
    char line[4096];
    char *tok[16];
    if (!fgets(line, sizeof line, stdin)) {
        return fail_read("suite cfg");
    }
    int n = split_ws(line, tok, 16);
    if (n != 3) {
        return fail_read("suite cfg fields");
    }
    double lat = 0.0, lon = 0.0, h = 0.0;
    if (!parse_d(tok[0], &lat) || !parse_d(tok[1], &lon) || !parse_d(tok[2], &h)) {
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
    opt.auto_init = true;
    opt.allow_unlimited_deadreckoning = true;
    /* This slice observes the vertical channel on IMU+baro. Suite
       standstill detection would ZUPT the channel and hide the
       accelerometer-only 1-sigma growth PRD names. */
    opt.auto_zupt_disable = true;
    opt.auto_zupt_velocity_blind_disable = true;
    int rc = nav_suite_init(&s, &init, &opt);
    printf("INIT rc=%d\n", rc);
    print_chan_snap(&s, 0);
    if (rc != 0) {
        return 0;
    }

    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#') {
            continue;
        }
        n = split_ws(line, tok, 16);
        if (n < 1 || tok[0][0] != 'E') {
            return fail_read("suite epoch tag");
        }
        if (n != 10) {
            return fail_read("suite epoch fields");
        }
        long long t_us = 0;
        float ax, ay, az, gx, gy, gz, barof, p;
        if (!parse_ll(tok[1], &t_us) || !parse_f(tok[2], &ax) ||
            !parse_f(tok[3], &ay) || !parse_f(tok[4], &az) ||
            !parse_f(tok[5], &gx) || !parse_f(tok[6], &gy) ||
            !parse_f(tok[7], &gz) || !parse_f(tok[8], &barof) ||
            !parse_f(tok[9], &p)) {
            return fail_read("suite epoch numbers");
        }
        ins_measurements_t m;
        memset(&m, 0, sizeof m);
        m.timestamp = (ins_time_us_t)t_us;
        m.strapdown_dt_sec = 0.01f;
        m.acc.is_valid = true;
        m.gyr.is_valid = true;
        m.acc.data[0] = ax;
        m.acc.data[1] = ay;
        m.acc.data[2] = az;
        m.gyr.data[0] = gx;
        m.gyr.data[1] = gy;
        m.gyr.data[2] = gz;
        if ((int)barof) {
            m.baro.is_valid = true;
            m.baro.pressure_pa = p;
        }
        nav_suite_update(&s, &m);
        print_chan_snap(&s, t_us);
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
    if (strncmp(line, "OFFSET", 6) == 0) {
        return run_offset();
    }
    if (strncmp(line, "SUITE", 5) == 0) {
        return run_suite();
    }
    return fail_read("kind token");
}
"""


def vert_token(v: float) -> str:
    """Encode a float for probe stdin, including non-finite tokens."""
    x = float(v)
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0.0 else "-inf"
    return f"{x:.17g}"


def tropospheric_isa_altitude_m(pressure_pa: float) -> float:
    """Independent tropospheric ISA altitude from static pressure."""
    p = float(pressure_pa)
    if not math.isfinite(p) or p <= 0.0:
        raise HarnessError(f"ISA pressure {p} is not a positive finite value")
    exponent = (_ISA_R_J_PER_KG_K * _ISA_LAPSE_K_PER_M) / _ISA_G0_MPS2
    ratio = p / ISA_P0_PA
    if ratio <= 0.0:
        raise HarnessError(f"ISA pressure ratio {ratio} is not positive")
    height = (_ISA_T0_K / _ISA_LAPSE_K_PER_M) * (1.0 - ratio**exponent)
    if not math.isfinite(height):
        raise HarnessError(f"ISA altitude is not finite for p={p}")
    return height


def tropospheric_isa_pressure_pa(height_m: float) -> float:
    """Independent tropospheric ISA static pressure from altitude."""
    h = float(height_m)
    if not math.isfinite(h):
        raise HarnessError(f"ISA height {h} is not finite")
    frac = 1.0 - h * _ISA_LAPSE_K_PER_M / _ISA_T0_K
    if frac <= 0.0:
        raise HarnessError(f"ISA height {h} is above the troposphere model")
    exponent = _ISA_G0_MPS2 / (_ISA_R_J_PER_KG_K * _ISA_LAPSE_K_PER_M)
    pressure = ISA_P0_PA * (frac**exponent)
    if not math.isfinite(pressure) or pressure <= 0.0:
        raise HarnessError(f"ISA pressure is not a positive finite value for h={h}")
    return pressure


def level_quat() -> tuple[float, float, float, float]:
    return _IDENTITY_QUAT


def up_specific_force(a_up_mps2: float) -> tuple[float, float, float]:
    """Level-body specific force whose gravity-removed up-acceleration is a_up."""
    return (0.0, 0.0, -(G_MPS2 + float(a_up_mps2)))


def kinematics_height_m(a_up_mps2: float, dt_s: float) -> float:
    """Independent constant-acceleration height change, positive up."""
    return 0.5 * float(a_up_mps2) * float(dt_s) * float(dt_s)


def kinematics_climb_mps(a_up_mps2: float, dt_s: float) -> float:
    return float(a_up_mps2) * float(dt_s)


# ---------------------------------------------------------------------------
# Standalone vertical-channel probe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VertCmd:
    tag: str
    t_us: int
    acc: tuple[float, float, float] = SPECIFIC_FORCE_LEVEL
    quat: tuple[float, float, float, float] = _IDENTITY_QUAT
    pressure_pa: float = 0.0
    baro_valid: bool = False
    zupt: bool = False
    h_init: float = 0.0


@dataclass
class VertScenario:
    t_init: int
    pressure_pa: float
    h_init: float = 0.0
    h_init_std: float = 0.0
    baro_std: float = 0.0
    cmds: list[VertCmd] = field(default_factory=list)
    # baro_alt_config_t precision_restart_disable. False is the zeroed
    # config (watchdog on at its documented defaults).
    restart_disable: bool = False


@dataclass(frozen=True)
class VertSnapshot:
    t_us: int
    h_ok: bool
    v_ok: bool
    isa_ok: bool
    h: float | None
    v: float | None
    isa: float | None
    n_invalid: int


@dataclass
class VertRun:
    init_ok: bool
    snaps: list[VertSnapshot]
    reinit_ok: list[bool] = field(default_factory=list)

    def last(self) -> VertSnapshot:
        if not self.snaps:
            raise HarnessError("vertical-channel run has no snapshots")
        return self.snaps[-1]


def encode_vert(scen: VertScenario) -> str:
    init_line = (
        f"{scen.t_init} {vert_token(scen.pressure_pa)} {vert_token(scen.h_init)} "
        f"{vert_token(scen.h_init_std)} {vert_token(scen.baro_std)}"
    )
    if scen.restart_disable:
        init_line += " 1"
    lines = [
        "FILTER",
        init_line,
    ]
    for cmd in scen.cmds:
        if cmd.tag == "R":
            lines.append(
                f"R {cmd.t_us} {vert_token(cmd.pressure_pa)} {vert_token(cmd.h_init)}"
            )
            continue
        lines.append(
            "E %d %s %s %s %s %s %s %s %s %d %d"
            % (
                cmd.t_us,
                vert_token(cmd.acc[0]),
                vert_token(cmd.acc[1]),
                vert_token(cmd.acc[2]),
                vert_token(cmd.quat[0]),
                vert_token(cmd.quat[1]),
                vert_token(cmd.quat[2]),
                vert_token(cmd.quat[3]),
                vert_token(cmd.pressure_pa),
                int(cmd.baro_valid),
                int(cmd.zupt),
            )
        )
    return "\n".join(lines) + "\n"


def _marked_float(fields: dict[str, str], flag: bool, key: str) -> float | None:
    value = _parse_optional_float(fields, key)
    if flag and value is None:
        raise HarnessError(f"{key} marked present but value is absent")
    if (not flag) and value is not None:
        raise HarnessError(f"{key} marked absent but a value was printed")
    return value


def parse_vert_snapshot(line: str) -> VertSnapshot:
    if not line.startswith("SNAP "):
        raise HarnessError(f"not a SNAP line: {line!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad SNAP token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    h_ok = _parse_flag(fields, "h_ok")
    v_ok = _parse_flag(fields, "v_ok")
    isa_ok = _parse_flag(fields, "isa_ok")
    n_invalid = _parse_int(fields, "n_invalid")
    if n_invalid < 0:
        note_product_issue("F07", f"n_invalid missing or negative: {line}")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F07', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F07', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F07', f"ins_get_diag returned NULL for a live instance: {line}")
    return VertSnapshot(
        t_us=_parse_int(fields, "t_us"),
        h_ok=h_ok,
        v_ok=v_ok,
        isa_ok=isa_ok,
        h=_marked_float(fields, h_ok, "h"),
        v=_marked_float(fields, v_ok, "v"),
        isa=_marked_float(fields, isa_ok, "isa"),
        n_invalid=n_invalid,
    )


def parse_vert_run(text: str) -> VertRun:
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
    reinit_ok: list[bool] = []
    for ln in lines:
        if not ln.startswith("REINIT "):
            continue
        rfields = dict(token.split("=", 1) for token in ln[7:].split() if "=" in token)
        if "rc" not in rfields:
            raise HarnessError(f"REINIT missing rc: {ln!r}")
        try:
            rrc = int(rfields["rc"])
        except ValueError as exc:
            raise HarnessError(f"REINIT rc not an int: {ln!r}") from exc
        reinit_ok.append(rrc == 0)
    snaps = [parse_vert_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    if not snaps:
        raise HarnessError("vertical-channel probe produced no SNAP lines")
    return VertRun(init_ok=(rc == 0), snaps=snaps, reinit_ok=reinit_ok)


def c_vert_run(scen: VertScenario) -> VertRun:
    result = invoke(_C_PROBE, stdin=encode_vert(scen), timeout=VERT_TIMEOUT)
    text = require_probe_success(result)
    run = parse_vert_run(text)
    print(
        f"vert init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_h_ok={run.last().h_ok}",
        flush=True,
    )
    return run


def require_published_vert(snap: VertSnapshot, what: str) -> None:
    assert snap.h_ok and snap.h is not None, f"{what}: height accessor failed"
    assert snap.v_ok and snap.v is not None, f"{what}: climb accessor failed"
    assert snap.isa_ok and snap.isa is not None, f"{what}: ISA accessor failed"


def require_unpublished_vert(snap: VertSnapshot, what: str) -> None:
    assert not snap.h_ok and snap.h is None, f"{what}: height accessor still succeeded"
    assert not snap.v_ok and snap.v is None, f"{what}: climb accessor still succeeded"


def vert_stream(
    *,
    duration_s: float,
    t0_us: int = 0,
    imu_hz: int = IMU_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    quat: Sequence[float] | None = None,
    pressure_pa: float = 0.0,
    baro_valid: bool = True,
    zupt: bool = False,
    pressure_at=None,
) -> list[VertCmd]:
    if duration_s <= 0.0 or imu_hz <= 0:
        raise HarnessError("vertical stream needs a positive duration and rate")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    if n <= 0:
        raise HarnessError("vertical stream produced no epochs")
    q = tuple(quat) if quat is not None else _IDENTITY_QUAT
    acc_t = (float(acc[0]), float(acc[1]), float(acc[2]))
    out: list[VertCmd] = []
    for i in range(1, n + 1):
        t_us = t0_us + int(round(i * dt * 1e6))
        p = float(pressure_at(t_us)) if pressure_at is not None else float(pressure_pa)
        out.append(
            VertCmd(
                tag="E",
                t_us=t_us,
                acc=acc_t,
                quat=q,
                pressure_pa=p,
                baro_valid=baro_valid,
                zupt=zupt,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Local-to-ellipsoid offset probe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OffCmd:
    tag: str
    t_us: int
    h_local: float = 0.0
    local_std: float = 0.0
    h_ell: float = 0.0
    gnss_std: float = 0.0


@dataclass
class OffScenario:
    t_init: int
    h_local: float
    local_std: float
    h_ell: float
    gnss_std: float
    cmds: list[OffCmd] = field(default_factory=list)


@dataclass(frozen=True)
class OffSnapshot:
    t_us: int
    get_ok: bool
    offset: float | None
    std: float | None
    n_invalid: int


@dataclass
class OffRun:
    init_ok: bool
    snaps: list[OffSnapshot]

    def last(self) -> OffSnapshot:
        if not self.snaps:
            raise HarnessError("offset run has no snapshots")
        return self.snaps[-1]


def encode_offset(scen: OffScenario) -> str:
    lines = [
        "OFFSET",
        f"{scen.t_init} {vert_token(scen.h_local)} {vert_token(scen.local_std)} "
        f"{vert_token(scen.h_ell)} {vert_token(scen.gnss_std)}",
    ]
    for cmd in scen.cmds:
        if cmd.tag == "G":
            lines.append(f"G {cmd.t_us}")
            continue
        lines.append(
            "E %d %s %s %s %s"
            % (
                cmd.t_us,
                vert_token(cmd.h_local),
                vert_token(cmd.local_std),
                vert_token(cmd.h_ell),
                vert_token(cmd.gnss_std),
            )
        )
    return "\n".join(lines) + "\n"


def parse_off_snapshot(line: str) -> OffSnapshot:
    if not line.startswith("SNAP "):
        raise HarnessError(f"not a SNAP line: {line!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad SNAP token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    get_ok = _parse_flag(fields, "get_ok")
    n_invalid = _parse_int(fields, "n_invalid")
    if n_invalid < 0:
        note_product_issue("F07", f"n_invalid missing or negative: {line}")
    for _tok in nonfinite_fields(fields):
        note_product_issue('F07', f"non-finite published value {_tok}: {line}")
    if fields.get("attnostd") == "1":
        note_product_issue('F07', f"attitude published without its 1-sigma: {line}")
    if fields.get("diag") == "0":
        note_product_issue('F07', f"ins_get_diag returned NULL for a live instance: {line}")
    return OffSnapshot(
        t_us=_parse_int(fields, "t_us"),
        get_ok=get_ok,
        offset=_marked_float(fields, get_ok, "offset"),
        std=_marked_float(fields, get_ok, "std"),
        n_invalid=n_invalid,
    )


def parse_off_run(text: str) -> OffRun:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    init_lines = [ln for ln in lines if ln.startswith("INIT ")]
    if len(init_lines) != 1:
        raise HarnessError(f"offset probe stdout has {len(init_lines)} INIT lines")
    fields = dict(
        token.split("=", 1) for token in init_lines[0][5:].split() if "=" in token
    )
    if "rc" not in fields:
        raise HarnessError(f"INIT missing rc: {init_lines[0]!r}")
    try:
        rc = int(fields["rc"])
    except ValueError as exc:
        raise HarnessError(f"INIT rc not an int: {init_lines[0]!r}") from exc
    snaps = [parse_off_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    if not snaps:
        raise HarnessError("offset probe produced no SNAP lines")
    return OffRun(init_ok=(rc == 0), snaps=snaps)


def c_offset_run(scen: OffScenario) -> OffRun:
    result = invoke(_C_PROBE, stdin=encode_offset(scen), timeout=VERT_TIMEOUT)
    text = require_probe_success(result)
    run = parse_off_run(text)
    print(
        f"offset init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_get={run.last().get_ok}",
        flush=True,
    )
    return run


# ---------------------------------------------------------------------------
# Suite channel probe (this filter's accessors, not arbitrated height)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChanSuiteEpoch:
    t_us: int
    acc: tuple[float, float, float] = SPECIFIC_FORCE_LEVEL
    gyr: tuple[float, float, float] = (0.0, 0.0, 0.0)
    pressure_pa: float = 0.0
    baro_valid: bool = False


@dataclass
class ChanSuiteScenario:
    lat_deg: float
    lon_deg: float
    h_m: float
    epochs: list[ChanSuiteEpoch] = field(default_factory=list)


@dataclass(frozen=True)
class ChanSuiteSnapshot:
    t_us: int
    h_ok: bool
    v_ok: bool
    h: float | None
    v: float | None


@dataclass
class ChanSuiteRun:
    init_ok: bool
    snaps: list[ChanSuiteSnapshot]

    def last(self) -> ChanSuiteSnapshot:
        if not self.snaps:
            raise HarnessError("channel-suite run has no snapshots")
        return self.snaps[-1]


def encode_chan_suite(scen: ChanSuiteScenario) -> str:
    lines = [
        "SUITE",
        f"{scen.lat_deg:.17g} {scen.lon_deg:.17g} {scen.h_m:.17g}",
    ]
    for e in scen.epochs:
        lines.append(
            "E %d %s %s %s %s %s %s %d %s"
            % (
                e.t_us,
                vert_token(e.acc[0]),
                vert_token(e.acc[1]),
                vert_token(e.acc[2]),
                vert_token(e.gyr[0]),
                vert_token(e.gyr[1]),
                vert_token(e.gyr[2]),
                int(e.baro_valid),
                vert_token(e.pressure_pa),
            )
        )
    return "\n".join(lines) + "\n"


def parse_chan_suite_snapshot(line: str) -> ChanSuiteSnapshot:
    if not line.startswith("SNAP "):
        raise HarnessError(f"not a SNAP line: {line!r}")
    fields: dict[str, str] = {}
    for token in line[5:].split():
        if "=" not in token:
            raise HarnessError(f"bad SNAP token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        fields[key] = value
    h_ok = _parse_flag(fields, "h_ok")
    v_ok = _parse_flag(fields, "v_ok")
    return ChanSuiteSnapshot(
        t_us=_parse_int(fields, "t_us"),
        h_ok=h_ok,
        v_ok=v_ok,
        h=_marked_float(fields, h_ok, "h"),
        v=_marked_float(fields, v_ok, "v"),
    )


def parse_chan_suite_run(text: str) -> ChanSuiteRun:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    init_lines = [ln for ln in lines if ln.startswith("INIT ")]
    if len(init_lines) != 1:
        raise HarnessError(f"suite probe stdout has {len(init_lines)} INIT lines")
    fields = dict(
        token.split("=", 1) for token in init_lines[0][5:].split() if "=" in token
    )
    if "rc" not in fields:
        raise HarnessError(f"INIT missing rc: {init_lines[0]!r}")
    try:
        rc = int(fields["rc"])
    except ValueError as exc:
        raise HarnessError(f"INIT rc not an int: {init_lines[0]!r}") from exc
    snaps = [parse_chan_suite_snapshot(ln) for ln in lines if ln.startswith("SNAP ")]
    if not snaps:
        raise HarnessError("channel-suite probe produced no SNAP lines")
    return ChanSuiteRun(init_ok=(rc == 0), snaps=snaps)


def c_chan_suite_run(scen: ChanSuiteScenario) -> ChanSuiteRun:
    result = invoke(_C_PROBE, stdin=encode_chan_suite(scen), timeout=VERT_TIMEOUT)
    text = require_probe_success(result)
    run = parse_chan_suite_run(text)
    print(
        f"chan-suite init_ok={run.init_ok} snaps={len(run.snaps)} "
        f"last_h_ok={run.last().h_ok}",
        flush=True,
    )
    return run


def chan_suite_stream(
    *,
    duration_s: float,
    t0_us: int = 0,
    imu_hz: int = IMU_HZ,
    acc: Sequence[float] = SPECIFIC_FORCE_LEVEL,
    pressure_pa: float = 0.0,
    baro_valid: bool = True,
    pressure_at=None,
) -> list[ChanSuiteEpoch]:
    if duration_s <= 0.0 or imu_hz <= 0:
        raise HarnessError("channel-suite stream needs a positive duration and rate")
    dt = 1.0 / imu_hz
    n = int(round(duration_s * imu_hz))
    if n <= 0:
        raise HarnessError("channel-suite stream produced no epochs")
    acc_t = (float(acc[0]), float(acc[1]), float(acc[2]))
    out: list[ChanSuiteEpoch] = []
    for i in range(1, n + 1):
        t_us = t0_us + int(round(i * dt * 1e6))
        p = float(pressure_at(t_us)) if pressure_at is not None else float(pressure_pa)
        out.append(
            ChanSuiteEpoch(
                t_us=t_us,
                acc=acc_t,
                pressure_pa=p,
                baro_valid=baro_valid,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Runtime seeds (avoid a single public tutorial constant)
# ---------------------------------------------------------------------------


def runtime_pad_isa_m() -> float:
    """Pad ISA altitude in the few-hundred-metre band, not sea level."""
    u = runtime_uuid_int()
    h = 220.0 + (u % 280)
    print(f"runtime pad ISA m={h}", flush=True)
    return float(h)


def runtime_climb_m() -> float:
    """Climb of several metres, not a fixed 3.00 m tutorial step."""
    u = runtime_uuid_int()
    h = 4.5 + (u % 90) / 10.0
    if abs(h - 3.0) < 0.4:
        h = 7.2
    print(f"runtime climb m={h}", flush=True)
    return float(h)


def runtime_h_init_m() -> float:
    u = runtime_uuid_int()
    h = 12.0 + (u % 28)
    if abs(h - 25.0) < 0.5:
        h = 31.0
    print(f"runtime h_init m={h}", flush=True)
    return float(h)


def runtime_isa_band_heights() -> tuple[float, float]:
    """Two distinct tropospheric heights inside 300–800 m."""
    u = runtime_uuid_int()
    a = 320.0 + (u % 160)
    b = 560.0 + ((u // 160) % 200)
    if abs(a - b) < 40.0:
        b = a + 90.0
    if a < 300.0 or a > 800.0 or b < 300.0 or b > 800.0:
        raise HarnessError(f"ISA band heights left 300–800 m: {a}, {b}")
    print(f"runtime ISA band heights {a} {b}", flush=True)
    return float(a), float(b)


def runtime_a_up_mps2() -> float:
    u = runtime_uuid_int()
    a = 8.0 + (u % 50) / 10.0
    print(f"runtime a_up={a}", flush=True)
    return float(a)


def runtime_a_up_alt_mps2() -> float:
    u = runtime_uuid_int()
    a = 14.0 + (u % 40) / 10.0
    print(f"runtime a_up alt={a}", flush=True)
    return float(a)


def runtime_acc_bias_mps2() -> float:
    u = runtime_uuid_int()
    b = 0.16 + (u % 18) / 100.0
    print(f"runtime acc bias={b}", flush=True)
    return float(b)


def runtime_vert_tilt_rad() -> float:
    u = runtime_uuid_int()
    deg = 12.0 + (u % 120) / 10.0
    print(f"runtime vert tilt deg={deg}", flush=True)
    return math.radians(deg)


def runtime_offset_pair() -> tuple[float, float]:
    """Two distinct local-to-ellipsoid offsets, not 0/100.

    The gap is tens of metres (enough to tell A from B) but not so large
    that a single step is only ever a heavily downweighted outlier.
    """
    u = runtime_uuid_int()
    a = 20.0 + (u % 16)
    b = a + 18.0 + ((u // 16) % 12)
    print(f"runtime offsets A={a} B={b}", flush=True)
    return float(a), float(b)


def runtime_local_height_m() -> float:
    u = runtime_uuid_int()
    h = 6.0 + (u % 35)
    print(f"runtime local height m={h}", flush=True)
    return float(h)


def runtime_spike_isa_m() -> float:
    u = runtime_uuid_int()
    h = 45.0 + (u % 70)
    print(f"runtime spike ISA m={h}", flush=True)
    return float(h)


def runtime_weather_isa_m() -> float:
    u = runtime_uuid_int()
    h = 6.0 + (u % 50) / 10.0
    print(f"runtime weather ISA m={h}", flush=True)
    return float(h)


def runtime_tight_baro_std_m() -> float:
    u = runtime_uuid_int()
    s = 0.12 + (u % 10) / 100.0
    print(f"runtime tight baro 1-sigma={s}", flush=True)
    return float(s)


def runtime_suite_site() -> tuple[float, float, float]:
    return runtime_site()
