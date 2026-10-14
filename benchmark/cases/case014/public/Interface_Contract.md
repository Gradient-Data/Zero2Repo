# NAVFILTER — Interface Contract

This document is the complete outside shell of NAVFILTER: where every entry lives, how it is called, what it accepts, and the form of everything it puts out. What the product computes, and under which conditions, is specified in the PRD. Any part of a form that this document does not state is the implementer's choice.

## 1. Conventions used throughout

- **Units in names.** `_rad` radians, `_deg` degrees, `_m` metres, `_mps` metres per second, `_mps2` metres per second squared, `_rps` radians per second, `_uT` microtesla, `_pa` pascals, `_sec` seconds, `_ms` milliseconds, `_us` microseconds. A name ending in `stddev…` is a 1-sigma in that unit; a name ending in `Qll…` or `var` is a variance (square of the unit).
- **Frames.** Body vectors are FRD (x forward, y right, z down). Navigation vectors are NED (north, east, down), ordered `[north, east, down]`. Attitude quaternions are Hamilton, body-to-NED, scalar first: `[w, x, y, z]`. Roll, pitch, yaw are Tait-Bryan ZYX. ECEF positions are WGS84 metres, `double`.
- **3×3 arrays** of 9 elements are column-major: element (row, col) is at index `row + 3*col`.
- **Time.** `ins_time_us_t`, `ahrs_time_us_t`, and `baro_alt_time_us_t` are signed 64-bit integer microsecond timestamps.
- **`bool` accessors.** An accessor that returns `bool` returns true when its value is published and then writes it to the outputs; it returns false while the value is unpublished (including a NULL instance or an instance that is not initialized), and its outputs are then unspecified.
- **`int` initializers.** Return 0 on success and -1 when the start is refused.
- **Configuration fields.** A field documented as "0 → default" selects the PRD's built-in value when it is 0. Configuration and measurement structs are zero-filled by the caller, who then sets only the members listed here; any further members are the implementer's choice.
- **Instance types** (`ins_t`, `ahrs_t`, `baro_alt_t`, `local_gnss_alt_t`, `nav_suite_t`) are complete struct types that the caller declares (on the stack or statically) and zero-fills before the initializer. Their layout is the implementer's choice, except for the members this document lists.
- **Python readers** take no arguments and never run the filter. A reader whose C counterpart is a `bool` accessor yields `None` while unpublished, otherwise a float or a tuple/list of floats.

## 2. Repository layout and build

- A `Makefile` at the repository root. `make pylib replay`, run from the repository root without network access, builds everything below.
  - `make pylib` writes the shared library `python/NAVFILTER/libNAVFILTER.so`.
  - `make replay` writes the executable C replay program `build/replay`.
- **C headers** live in `src/`: `ins.h`, `ahrs.h`, `baro_alt.h`, `nav_suite.h`, `geodetic_toolbox.h`, `magnetic_model.h`. Each header compiles when included alone or together with the others, in any order. Any further include directory the headers need is `NavCore/c/` (the implementer's choice whether it exists).
- A C caller compiles with `cc -std=c11 -D_GNU_SOURCE -Isrc` (plus `-INavCore/c` when that directory exists) and links `python/NAVFILTER/libNAVFILTER.so` and `-lm`. Every C function listed in section 3 is exported from that shared library.
- **Python package** `NAVFILTER` is the directory `python/NAVFILTER/` (with `__init__.py`); it is importable when `python/` is on the import path and loads `libNAVFILTER.so` from its own directory. The module `python/geodetic_toolbox.py` sits beside the package and is importable from the same path.
- **Python replay program:** `python/replay.py` (section 5).
- **Custom-CSV runner:** `python -m NAVFILTER <mapping.yaml>` (section 6).

## 3. C library

### 3.1 `geodetic_toolbox.h` — frames and WGS84

```
void  ins_quat_from_rpy(float roll_rad, float pitch_rad, float yaw_rad, float q[4]);
void  ins_quat_to_rotmat(const float q[4], float R_b_to_n[9]);
void  ins_rotmat_to_rpy(const float R_b_to_n[9], float* roll_rad, float* pitch_rad, float* yaw_rad);
void  ins_quat_normalize(float q[4]);
void  ins_latlonh_to_ecef(double lat_rad, double lon_rad, double height_m, double xyz[3]);
void  ins_ecef_to_latlonh(const double xyz[3], double* lat_rad, double* lon_rad, double* height_m);
void  ins_dned_to_dlatlonh(const float dxyz_n[3], double lat_rad, double height_m, double dlatlonh[3]);
void  ins_dlatlonh_to_dned(const double dlatlonh[3], double lat_rad, double height_m, float dxyz_n[3]);
void  ins_calc_omega_n_in(double lat_rad, double height_m, const float vel_ned[3],
                          float omega_n_in[3], float omega_n_ie_out[3], float omega_n_en_out[3]);
```

- `ins_quat_from_rpy` writes the body-to-NED quaternion `[w, x, y, z]` for the given angles.
- `ins_quat_to_rotmat` writes the body-to-NED rotation matrix (column-major); `ins_rotmat_to_rpy` writes the roll, pitch, yaw of such a matrix.
- `ins_quat_normalize` normalizes `q` in place.
- `ins_latlonh_to_ecef` writes the ECEF position of a geodetic latitude, longitude (radians) and ellipsoid height (metres); `ins_ecef_to_latlonh` is its inverse.
- `ins_dned_to_dlatlonh` converts a small NED displacement (metres) at the given latitude and height into a latitude/longitude/height delta (radians, radians, metres); `ins_dlatlonh_to_dned` is its inverse.
- `ins_calc_omega_n_in` writes three NED angular rates in rad/s for the given latitude, height, and NED velocity: the rate of the navigation frame relative to inertial space (`omega_n_in`), its Earth-rotation part (`omega_n_ie_out`), and its transport-rate part (`omega_n_en_out`).

### 3.2 `magnetic_model.h` — World Magnetic Model

```
float magnetic_declination_deg(float lat_deg, float lon_deg, float year);
float magnetic_inclination_deg(float lat_deg, float lon_deg);
float magnetic_field_strength_uT(float lat_deg, float lon_deg);
void  magnetic_field_ned_uT(float lat_deg, float lon_deg, float year, float b_ned_uT[3]);
```

Latitude and longitude in degrees, `year` a decimal year. Returns: declination in degrees (positive east), inclination in degrees (positive down), total field in µT; `magnetic_field_ned_uT` writes the NED field `[north, east, down]` in µT. The two-argument entries use a year of the implementer's choice within the model epoch (2025.0 to 2030.0); the total field then equals the magnitude of `magnetic_field_ned_uT` at that year.

### 3.3 `ins.h` — INS filter

**Types.**

`ins_init_t` (zero-filled by the caller), members:

| member | type | meaning |
| --- | --- | --- |
| `time` | `ins_time_us_t` | init timestamp, µs |
| `x_ecef` | `double[3]` | ECEF origin of the local NED frame, m |
| `rpy_init_rad` | `float[3]` | initial roll, pitch, yaw for a prescribed (non-auto) init, rad |
| `pos_init_stddev_m` | `float` | initial position 1-sigma, 0 → default |
| `vel_init_stddev_mps` | `float` | initial velocity 1-sigma, 0 → default |
| `rpy_init_stddev_rad` | `float[3]` | initial roll/pitch/yaw 1-sigma, 0 → default |
| `acc_bias_init_stddev_mps2` | `float` | initial accelerometer-bias 1-sigma, 0 → default |
| `gyr_bias_init_stddev_rps` | `float` | initial gyro-bias 1-sigma, 0 → default |
| `magnetic_n` | `float[3]` | NED magnetic reference field for magnetometer fusion, µT (all 0 → none until set) |

`ins_options_t` (zero-filled by the caller; an all-zero block is valid), members:

| member | type | meaning |
| --- | --- | --- |
| `auto_init` | `bool` | bootstrap from the stream (auto-init) |
| `auto_init_window_sec` | `float` | leveling window, s; 0 → default |
| `gnss_max_horizontal_pos_stddev_m`, `gnss_max_vertical_pos_stddev_m` | `float` | fusion gate, position 1-sigma, m; 0 → default |
| `gnss_max_horizontal_vel_stddev_mps`, `gnss_max_vertical_vel_stddev_mps` | `float` | fusion gate, velocity 1-sigma, m/s; 0 → default |
| `gnss_start_max_horizontal_pos_stddev_m`, `gnss_start_max_vertical_pos_stddev_m` | `float` | entry gate, position 1-sigma, m; 0 → default |
| `gnss_start_max_horizontal_vel_stddev_mps`, `gnss_start_max_vertical_vel_stddev_mps` | `float` | entry gate, velocity 1-sigma, m/s; 0 → default |
| `gnss_init_dwell_sec` | `float` | entry dwell, s; 0 → default |
| `gnss_init_dwell_disable` | `bool` | no entry dwell |
| `gnss_stop_max_horizontal_pos_stddev_m`, `gnss_stop_max_vertical_pos_stddev_m` | `float` | exit gate, position 1-sigma, m; 0 → default |
| `gnss_stop_max_horizontal_vel_stddev_mps`, `gnss_stop_max_vertical_vel_stddev_mps` | `float` | exit gate, velocity 1-sigma, m/s; 0 → default |
| `gnss_stop_dwell_sec` | `float` | exit dwell, s; 0 → default |
| `gnss_stop_disable` | `bool` | never leave 3D on GNSS quality |
| `auto_reacquire_disable` | `bool` | on exit-gate dwell, clear ready only (no re-arm) |
| `max_deadreckoning_sec` | `float` | coasting window, s; 0 → default |
| `allow_unlimited_deadreckoning` | `bool` | unlimited dead reckoning |
| `gnss_min_delay_ms` | `int` | GNSS fusion minimum interval, ms; 0 → default, negative → no limit |
| `gnss_pos_decimation` | `int` | N of the position decimation; ≤ 1 → off |
| `magnetometer_min_delay_ms` | `int` | magnetometer fusion minimum interval, ms; 0 → default, negative → no limit |
| `auto_zupt_disable` | `bool` | automatic ZUPT/ZARU detector off |
| `auto_zupt_static_gyr_rps` | `float` | stillness bound on gyro magnitude, rad/s; 0 → default |
| `auto_zupt_static_acc_mps2` | `float` | stillness bound on the deviation of the specific-force magnitude from g, m/s²; 0 → default |
| `auto_zupt_dwell_sec` | `float` | stillness dwell, s; 0 → default |
| `auto_zupt_velocity_blind_disable` | `bool` | suite attitude filters use only the INS standstill decision |
| `speed_min_mps` | `float` | minimum filter speed for scalar-speed fusion, m/s; 0 → default |
| `baro_height_disable` | `bool` | force GNSS height instead of barometric height |
| `chi2_disable` | `bool` | global outlier-downweighting override |

`ins_meas3_t`: `float data[3]` (sample, unit of the channel), `float Qll_diag[3]` (per-axis noise: for accelerometer and gyroscope a spectral density, for the magnetometer a variance; all 0 → default), `bool is_valid`.

`ins_meas_gnss_pos_t`: `double xyz_ecef[3]` (m), `float Qll_ned[9]` (NED covariance, m², column-major), `bool is_valid`.

`ins_meas_gnss_vel_t`: `float vel_ned[3]` (m/s), `float Qll_ned[9]` (NED covariance, (m/s)², column-major), `bool is_valid`.

`ins_meas_local_pos_t`: `float pos_ned[3]` (m, local NED frame), `float Qll_ned[9]` (m², column-major), `bool is_valid`.

`ins_meas_yaw_t`: `float yaw_rad`, `float stddev_rad`, `bool is_valid`.

`ins_meas_baro_t`: `float pressure_pa`, `float stddev_m` (altitude 1-sigma; 0 → default), `bool is_valid`.

`ins_meas_speed_t`: `float speed_mps`, `float stddev_mps` (0 → default), `bool is_valid`.

`ins_measurements_t` (one epoch; zero-filled, then the present parts are set):

| member | type | meaning |
| --- | --- | --- |
| `timestamp` | `ins_time_us_t` | epoch time, µs |
| `strapdown_dt_sec` | `float` | IMU interval, s |
| `acc` | `ins_meas3_t` | specific force, FRD, m/s² |
| `gyr` | `ins_meas3_t` | angular rate, FRD, rad/s |
| `mag` | `ins_meas3_t` | magnetic field, FRD, µT |
| `gnss_pos` | `ins_meas_gnss_pos_t` | GNSS position |
| `gnss_vel` | `ins_meas_gnss_vel_t` | GNSS velocity |
| `gnss_Qll_pos_vel_ned` | `float[9]` | GNSS position–velocity cross-covariance, column-major |
| `gnss_leverarm_b` | `float[3]` | GNSS antenna lever arm, FRD, m |
| `gnss_delay_ms` | `int` | age of the GNSS sample relative to `timestamp`, ms |
| `local_pos` | `ins_meas_local_pos_t` | local NED position |
| `local_pos_delay_ms` | `int` | age of the local-position sample, ms |
| `yaw` | `ins_meas_yaw_t` | absolute yaw |
| `yaw_delay_ms` | `int` | age of the yaw sample, ms |
| `baro` | `ins_meas_baro_t` | static pressure |
| `speed` | `ins_meas_speed_t` | scalar ground speed |
| `speed_delay_ms` | `int` | age of the scalar-speed sample, ms |
| `zero_velocity_update` | `bool` | explicit ZUPT flag |
| `zero_rotation_update` | `bool` | explicit ZARU flag |

`ins_diag_t` (read-only counters, all `uint32_t` unless noted; further members are the implementer's choice):

| member | counts |
| --- | --- |
| `n_predict` | filter-update (covariance prediction) epochs run |
| `n_time_backward` | epochs skipped as timing anomalies (backwards timestamp) |
| `n_gnss_seen` | epochs offering a valid GNSS position or velocity |
| `n_gnss_used` | epochs on which GNSS was fused |
| `n_gnss_rejected_noise` | GNSS samples rejected by the fusion (accuracy) gate |
| `n_gnss_rate_limited` | GNSS epochs skipped by the fusion rate limit |
| `n_gnss_no_anchor` | GNSS samples skipped for lack of a usable time-of-validity history |
| `n_fuse_fail` | fusion failures |
| `n_invalid_input` | measurement blocks dropped as invalid input |
| `n_downweighted` | fusions that were downweighted as outliers |
| `n_auto_zupt` | epochs on which the automatic standstill detector fired |
| `last_gnss_pos_residual_m` (`float`) | magnitude of the position residual at the last GNSS fusion, m |

**Functions.**

```
int  ins_init(ins_t* f, const ins_init_t* init, const ins_options_t* opt);
void ins_update(ins_t* f, const ins_measurements_t* m);
bool ins_is_ready(const ins_t* f);
bool ins_get_position_ecef(const ins_t* f, double pos_ecef[3]);
bool ins_get_position_local(const ins_t* f, float pos_ned[3]);
bool ins_get_velocity_ned(const ins_t* f, float vel_ned[3]);
bool ins_get_rpy(const ins_t* f, float* roll_rad, float* pitch_rad, float* yaw_rad);
bool ins_get_rpy_stddev(const ins_t* f, float* roll_stddev_rad, float* pitch_stddev_rad, float* yaw_stddev_rad);
bool ins_get_bias_acc(const ins_t* f, float acc_bias_mps2[3]);
bool ins_get_bias_gyr(const ins_t* f, float gyr_bias_rps[3]);
int  ins_deadreckoning_ms(const ins_t* f);
bool ins_auto_zupt_active(const ins_t* f);
void ins_set_auto_zupt_disable(ins_t* f, bool disable);
void ins_set_magnetic_model_from_position(ins_t* f, double lat_rad, double lon_rad, float year);
const ins_diag_t* ins_get_diag(const ins_t* f);
```

- `ins_init` starts a zeroed instance; 0 or -1. All three pointers are required.
- `ins_update` consumes one epoch.
- `ins_is_ready` returns the ready flag. The position, velocity, attitude, attitude 1-sigma, and bias accessors are `bool` accessors (section 1).
- `ins_deadreckoning_ms` returns the coasting age in whole milliseconds (0 or more) while the age is published, and -1 otherwise (including a NULL instance).
- `ins_auto_zupt_active` returns the automatic standstill detector's current verdict (false while not initialized). `ins_set_auto_zupt_disable` switches the detector off (`true`) or on (`false`) at runtime.
- `ins_set_magnetic_model_from_position` arms the World Magnetic Model reference from a geographic position (radians) and decimal year.
- `ins_get_diag` returns a pointer to the instance's diagnostic counters; it is non-NULL for every non-NULL instance, initialized or not.

### 3.4 `ahrs.h` — ARS / AHRS attitude filter

`ahrs_mode_t` has the two values `AHRS_MODE_ARS` and `AHRS_MODE_AHRS`.

`ahrs_config_t` (zero-filled by the caller), members:

| member | type | meaning |
| --- | --- | --- |
| `mode` | `ahrs_mode_t` | ARS or AHRS |
| `rpy_init_rad` | `float[3]` | initial roll, pitch, yaw, rad |
| `rpy_init_stddev_rad` | `float[3]` | initial roll, pitch, yaw 1-sigma, rad (mandatory as stated in the PRD) |
| `mag_field_check_enable` | `bool` | enable the field-strength gate |
| `mag_field_tolerance` | `float` | relative tolerance of that gate; 0 → default |
| `precision_restart_disable` | `bool` | switch the precision-restart check off |
| `restart_att_stddev_rad` | `float[3]` | roll, pitch, yaw restart thresholds, rad; 0 → default, negative → axis unchecked |
| `restart_warmup_sec` | `float` | time after init before the check applies, s; 0 → default |
| `chi2_disable` | `bool` | outlier-downweighting override |

`ahrs_t` publishes two members that callers read: `uint32_t n_invalid_input`, the count of epochs or samples the instance dropped as invalid input, and `uint32_t n_downweighted`, the count of fusions it downweighted as outliers.

```
int   ahrs_init(ahrs_t* a, const ahrs_config_t* cfg, ahrs_time_us_t t);
void  ahrs_update(ahrs_t* a, ahrs_time_us_t t, const float gyr_rps[3], const float acc_mps2[3],
                  const float mag_b[3], bool zero_rotation_update);
bool  ahrs_get_rpy(const ahrs_t* a, float* roll_rad, float* pitch_rad, float* yaw_rad);
bool  ahrs_get_rpy_stddev(const ahrs_t* a, float* roll_stddev_rad, float* pitch_stddev_rad, float* yaw_stddev_rad);
bool  ahrs_get_bias_gyr(const ahrs_t* a, float gyr_bias_rps[3]);
void  ahrs_set_position(ahrs_t* a, float lat_rad, float lon_rad, float year);
void  ahrs_leveling_from_acc(const float acc_mps2[3], float* roll_rad, float* pitch_rad);
float ahrs_mag_heading(const float mag_b[3], float roll_rad, float pitch_rad);
```

- `ahrs_init`: 0 or -1. `ahrs_update` consumes one epoch: gyro (FRD, rad/s), specific force (FRD, m/s²), magnetometer (FRD, µT; `NULL` when no sample), and the explicit zero-rotation flag.
- `ahrs_set_position` supplies a geographic position (radians) and decimal year for the World Magnetic Model.
- `ahrs_leveling_from_acc` writes roll and pitch (rad) for one specific-force sample. `ahrs_mag_heading` returns a yaw in radians for one magnetometer sample and the given roll and pitch.

### 3.5 `baro_alt.h` — barometric vertical channel and local-to-ellipsoid offset

`baro_alt_config_t` (zero-filled; all-zero is valid), members:

| member | type | meaning |
| --- | --- | --- |
| `baro_stddev_m` | `float` | barometer altitude 1-sigma, m; 0 → default |
| `precision_restart_disable` | `bool` | switch the precision-restart check off |
| `restart_h_stddev_m` | `float` | height 1-sigma threshold, m; 0 → default, negative → unchecked |
| `restart_v_stddev_mps` | `float` | vertical-velocity 1-sigma threshold, m/s; 0 → default, negative → unchecked |
| `restart_warmup_sec` | `float` | time after init before the check applies, s; 0 → default |
| `chi2_disable` | `bool` | outlier-downweighting override |

`local_gnss_alt_config_t` (zero-filled; all-zero is valid), members: `chi2_disable` (`bool`).

`baro_alt_t` publishes two members that callers read: `uint32_t n_invalid_input`, the count of epochs or samples dropped as invalid input, and `uint32_t n_downweighted`, the count of barometer fusions downweighted as outliers. `local_gnss_alt_t` publishes one member that callers read: `uint32_t n_invalid_input`, the count of height pairs dropped as invalid input.

```
int  baro_alt_init(baro_alt_t* b, const baro_alt_config_t* cfg, baro_alt_time_us_t t,
                   float pressure_pa, float h_init_m, float h_init_stddev_m);
void baro_alt_update(baro_alt_t* b, baro_alt_time_us_t t, const float acc_mps2[3], const float q_bn[4],
                     float pressure_pa, float baro_stddev_m, bool baro_valid);
void baro_alt_zero_velocity_update(baro_alt_t* b, float stddev_mps);
bool baro_alt_get_height(const baro_alt_t* b, float* h_m);
bool baro_alt_get_velocity(const baro_alt_t* b, float* v_mps);
bool baro_alt_get_isa_altitude(const baro_alt_t* b, float* h_isa_m);

int  local_gnss_alt_init(local_gnss_alt_t* g, const local_gnss_alt_config_t* cfg, baro_alt_time_us_t t,
                         float h_local_m, float local_stddev_m, float h_gnss_ell_m, float gnss_stddev_m);
void local_gnss_alt_update(local_gnss_alt_t* g, baro_alt_time_us_t t, float h_local_m, float local_stddev_m,
                           float h_gnss_ell_m, float gnss_stddev_m);
bool local_gnss_alt_get(const local_gnss_alt_t* g, float* offset_m, float* stddev_m);
```

- `baro_alt_init`: anchor pressure (Pa), the height assigned to it (m), and that height's 1-sigma (m; 0 → default); 0 or -1.
- `baro_alt_update`: specific force (FRD, m/s²), body-to-NED quaternion, pressure (Pa), per-sample altitude 1-sigma (m; 0 → configured value), and whether the pressure is present.
- `baro_alt_zero_velocity_update` fuses a zero climb rate with the given 1-sigma (m/s; 0 → default).
- Heights and climb rate are positive up: `baro_alt_get_height` (datum height, m), `baro_alt_get_velocity` (m/s), `baro_alt_get_isa_altitude` (ISA altitude, m).
- `local_gnss_alt_*`: local height above the datum (m) and GNSS ellipsoid height (m), each with its 1-sigma (m); `local_gnss_alt_get` writes the offset (ellipsoid height minus local height, m) and its 1-sigma.

### 3.6 `nav_suite.h` — navigation suite

`nav_suite_t` publishes four members to callers: `ins` (`ins_t`), `ars` (`ahrs_t`, ARS mode), `ahrs` (`ahrs_t`, AHRS mode), and `baro_alt` (`baro_alt_t`). A caller may pass their addresses to the read accessors of sections 3.3–3.5.

`nav_suite_mode_t` has the four values `NAV_SUITE_MODE_NONE`, `NAV_SUITE_MODE_ATTITUDE_ONLY`, `NAV_SUITE_MODE_COASTING`, `NAV_SUITE_MODE_FULL`; their numeric values are the implementer's choice.

```
int  nav_suite_init(nav_suite_t* s, const ins_init_t* init, const ins_options_t* opt);
void nav_suite_update(nav_suite_t* s, const ins_measurements_t* m);
void nav_suite_set_init_att_hint(nav_suite_t* s, float roll_rad, float pitch_rad, float stddev_roll_pitch_rad,
                                 float yaw_rad, float stddev_yaw_rad);
nav_suite_mode_t nav_suite_get_mode(const nav_suite_t* s);
bool nav_suite_get_rpy(const nav_suite_t* s, float* roll_rad, float* pitch_rad, float* yaw_rad);
bool nav_suite_get_rpy_ins(const nav_suite_t* s, float* roll_rad, float* pitch_rad, float* yaw_rad);
bool nav_suite_get_rpy_ars(const nav_suite_t* s, float* roll_rad, float* pitch_rad, float* yaw_rad);
bool nav_suite_get_rpy_ahrs(const nav_suite_t* s, float* roll_rad, float* pitch_rad, float* yaw_rad);
bool nav_suite_get_height(const nav_suite_t* s, float* h_m);
bool nav_suite_get_height_ellipsoid(const nav_suite_t* s, float* h_ell_m);
bool nav_suite_get_baro_alt(const nav_suite_t* s, float* h_m, float* v_mps);
bool nav_suite_get_zaru_active(const nav_suite_t* s);
```

- `nav_suite_init`: 0 or -1 (a NULL `init` or `opt` is refused). `nav_suite_update` consumes one epoch for all sub-filters.
- `nav_suite_set_init_att_hint` arms the static initial-attitude hint: roll and pitch with one shared 1-sigma (≤ 0 → no roll/pitch hint), yaw with its 1-sigma (≤ 0 → no yaw hint).
- `nav_suite_get_mode` returns the solution mode; a NULL suite returns `NAV_SUITE_MODE_NONE`.
- `nav_suite_get_rpy` is the best-available attitude; `_ins`, `_ars`, `_ahrs` are the individual filters'.
- `nav_suite_get_height` is the local (datum) height, `nav_suite_get_height_ellipsoid` the ellipsoid height, `nav_suite_get_baro_alt` the barometric vertical channel's height and climb rate; all metres or m/s, positive up.
- `nav_suite_get_zaru_active` returns the suite's zero-rotation flag for the current epoch.

## 4. Python package `NAVFILTER`

### 4.1 Package-root functions and `geodetic_toolbox`

```
from NAVFILTER import rpy_to_quat, llh_to_ecef, ecef_to_llh, wmm_field_ned
from geodetic_toolbox import mag_heading
```

- `rpy_to_quat(roll, pitch, yaw)` → 4-tuple `(w, x, y, z)`; angles in radians.
- `llh_to_ecef(lat_rad, lon_rad, h_m)` → 3-tuple ECEF metres.
- `ecef_to_llh(x, y, z)` → `(lat_rad, lon_rad, h_m)`.
- `wmm_field_ned(lat_deg, lon_deg, year)` → 3-tuple `(north, east, down)` in µT.
- `mag_heading(mag_b, roll_rad, pitch_rad)` → yaw in radians; same arguments as `ahrs_mag_heading`.

### 4.2 `Config`, `Ins`, `Navigator`

```
from NAVFILTER import Config, Ins, Navigator
nav = Ins(Config(...))
nav = Navigator(Config(...))
```

`Config` keyword arguments (all optional; omitted ones keep the default path): `auto_init` (bool), `lat_rad`, `lon_rad` (geodetic origin, radians), `h_m` (ellipsoid height of the origin, m), `rpy_init_rad` (3-sequence, rad), `magnetic_n` (3-sequence, NED µT), and the following, each with the meaning of the `ins_options_t` member of the same name: `gnss_max_horizontal_pos_stddev_m`, `gnss_max_vertical_pos_stddev_m`, `gnss_max_horizontal_vel_stddev_mps`, `gnss_max_vertical_vel_stddev_mps`, `gnss_start_max_horizontal_pos_stddev_m`, `gnss_start_max_vertical_pos_stddev_m`, `gnss_start_max_horizontal_vel_stddev_mps`, `gnss_start_max_vertical_vel_stddev_mps`, `gnss_stop_max_horizontal_pos_stddev_m`, `gnss_stop_max_vertical_pos_stddev_m`, `gnss_stop_max_horizontal_vel_stddev_mps`, `gnss_stop_max_vertical_vel_stddev_mps`, `gnss_init_dwell_disable`, `gnss_stop_disable`, `max_deadreckoning_sec`, `allow_unlimited_deadreckoning`, `gnss_min_delay_ms`, `gnss_pos_decimation`, `magnetometer_min_delay_ms`, `auto_zupt_disable`, `auto_zupt_velocity_blind_disable`, `auto_zupt_static_gyr_rps`, `auto_zupt_static_acc_mps2`, `baro_height_disable`, `chi2_disable`.

`Ins(Config(...))` starts the INS wrapper; `Navigator(Config(...))` starts the navigation suite. A refused start raises `ValueError`.

**Pushes** (on both `Ins` and `Navigator`; none runs the filter):

```
nav.imu(t_us, dt_sec, acc, gyr, acc_var=..., gyr_var=...)   # begins the epoch
nav.gnss_pos(ecef, var_or_cov, delay_ms=0)
nav.gnss_vel(vel_ned, var_or_cov)
nav.gnss_pos_vel_cov(cov)
nav.gnss_leverarm(lever_b)
nav.local_pos(pos_ned, var_ned, delay_ms=0)
nav.mag(field_b, var)
nav.yaw(yaw_rad, stddev_rad, delay_ms=0)
nav.speed(speed_mps, stddev_mps=0.0, delay_ms=0)
nav.baro(pressure_pa)
nav.zupt(flag)
nav.zaru(flag)
nav.set_magnetic_model(lat_rad, lon_rad, year)
nav.update()                                                  # runs the epoch
```

`acc`, `gyr`, `field_b`, `lever_b` are FRD 3-sequences in m/s², rad/s, µT, m. `acc_var`, `gyr_var` are per-axis spectral densities (all 0 → default). `var_or_cov` is either a 3-sequence of NED diagonal variances or a 3-by-3 NED covariance (nested sequences). `cov` is the 3-by-3 NED position–velocity cross-covariance. `delay_ms` is the sample's age relative to the epoch, ms. `var` / `var_ned` are 3-sequences of variances (all 0 → default).

**Readers on both `Ins` and `Navigator`** (the `Navigator` ones report the suite's INS):

| reader | form |
| --- | --- |
| `is_ready()` | bool |
| `position_ecef()` | ECEF 3-sequence, m, or `None` |
| `position_local()` | NED 3-sequence, m, or `None` |
| `velocity_ned()` | NED 3-sequence, m/s, or `None` |
| `rpy()` on `Ins` | roll, pitch, yaw, rad, or `None` |
| `bias_acc()`, `bias_gyr()` | FRD 3-sequence, m/s² / rad/s, or `None` |
| `stddev()` | `None` while not initialized, else a mapping with keys `pos_ned`, `vel_ned`, `rpy`, `acc_bias`, `gyr_bias`, each a 3-sequence of 1-sigma (m, m/s, rad, m/s², rad/s) |
| `diag()` | mapping, available on every started instance, with integer values under the keys `n_predict`, `n_time_backward`, `n_gnss_seen`, `n_gnss_used`, `n_gnss_rejected_noise`, `n_gnss_no_anchor`, `n_fuse_fail`, `n_invalid_input`, `n_downweighted`, `n_auto_zupt` (meanings as `ins_diag_t`) |
| `deadreckoning_ms()` | int, same meaning as `ins_deadreckoning_ms` (-1 included) |
| `auto_zupt_active()` | bool |

**Readers on `Navigator` only:**

| reader | form |
| --- | --- |
| `mode_name()` | one of the strings `FULL`, `COASTING`, `ATTITUDE_ONLY`, `NONE` |
| `rpy()` | best-available roll, pitch, yaw, rad, or `None` |
| `rpy_ins()`, `rpy_ars()`, `rpy_ahrs()` | the individual filters' roll, pitch, yaw: a sequence of three floats, or `None` |
| `rpy_stddev_ars()`, `rpy_stddev_ahrs()` | 3-sequence of 1-sigma, rad, or `None` |
| `bias_gyr_ars()`, `bias_gyr_ahrs()` | 3-sequence, rad/s, or `None` |
| `height()` | local (datum) height, m, or `None` |
| `height_ellipsoid()` | ellipsoid height, m, or `None` |
| `baro_alt()` | `(height_m, climb_mps)` of the barometric vertical channel, or `None` |
| `zaru_active()` | bool, the suite's zero-rotation flag |

`Navigator.set_init_att_hint(roll_rad=0.0, pitch_rad=0.0, stddev_roll_pitch_rad=0.0, yaw_rad=0.0, stddev_yaw_rad=0.0)` has the meaning of `nav_suite_set_init_att_hint`.

## 5. Dataset replay programs

### 5.1 Dataset directory

A dataset directory holds the CSV streams named in the PRD (FP-10), each beginning with a `#` header line, comma-separated, first column `t_us` (integer microseconds), plus one `config.yaml`. `config.yaml` is nested (section, then key); the accepted keys and their value forms are:

| key | value |
| --- | --- |
| `name` | text |
| `aiding` | `gnss`, `ref`, or `none` |
| `init` | `auto` or `ref` |
| `chi2_disable` | 0/1 |
| `allow_unlimited_deadreckoning` | 0/1 |
| `imu.gyr_psd` | gyro spectral density, (rad/s)²/Hz |
| `imu.acc_psd` | accelerometer spectral density, (m/s²)²/Hz |
| `imu.gyr_bias_rw` | rad/s/√s |
| `imu.acc_bias_rw` | m/s²/√s |
| `imu.auto_zupt_disable` | 0/1 |
| `gnss.pos_stddev_fallback_m` | two-element list `[horizontal, vertical]`, m |
| `gnss.vel_stddev_fallback_mps` | one number, m/s |
| `gnss.delay_ms` | ms |
| `gnss.leverarm_frd` | three-element list, m, FRD |
| `mag.enable`, `baro.enable`, `speed.enable` | 0/1 |
| `speed.delay_ms` | ms |
| `speed.stddev_mps` | m/s |
| `inputs.imu`, `inputs.ref`, `inputs.gnss`, `inputs.mag`, `inputs.baro`, `inputs.speed` | file name relative to the `config.yaml` directory |
| `score.warmup_sec` | s |
| `score.min_epochs` | whole count |
| `score.attitude`, `score.ahrs` | 0/1 (attitude evaluation on, ARS evaluation on) |
| `score.lim_pos_rms_m`, `score.lim_baro_rms_m` | m |
| `score.lim_att_bias_deg`, `score.lim_att_std_deg`, `score.lim_yaw_bias_deg`, `score.lim_yaw_std_deg` | degrees |
| `score.lim_ars_att_bias_deg`, `score.lim_ars_roll_std_deg`, `score.lim_ars_pitch_std_deg` | degrees |
| `score.lim_ars_yaw_drift_deg_min` | degrees per minute |
| `origin.lat_deg`, `origin.lon_deg`, `origin.h_m` | degrees, metres (accepted and ignored) |
| `crazyflie.uri` | text (accepted and ignored) |

### 5.2 Python replay: `python/replay.py`

```
python3 python/replay.py <dataset>
python3 python/replay.py <dataset> --dump-solution FILE --dump-solution-hz=<rate>
python3 python/replay.py <dataset> --estimate-gnss-delay --plot-hz=<rate>
```

- `<dataset>` is the dataset directory or the path of its `config.yaml`.
- `--dump-solution FILE` writes the fused solution to `FILE`. Lines that begin with `#` are comments. Each data row has ten comma-separated numeric fields: the epoch's IMU timestamp `t_us` as an integer number of microseconds (the same time base as the dataset CSVs), latitude in degrees, longitude in degrees, ellipsoid height in metres, roll, pitch, and yaw in degrees, then north, east, and down velocity in m/s. A row is written only at an epoch where INS position, INS attitude, and NED velocity are all published; no row carries empty or non-finite cells.
- `--dump-solution-hz=<rate>` is the dump rate in Hz; `0` writes every IMU epoch that qualifies. A default rate applies when omitted.
- `--estimate-gnss-delay` forces the GNSS-latency estimator; `--plot-hz=<rate>` is the plot rate (plot output is the implementer's choice).
- **Standard output** carries, when the run finishes, one line `final nav_suite mode: <NAME>`, `<NAME>` being one of `FULL`, `COASTING`, `ATTITUDE_ONLY`, `NONE`. With the estimator forced and a lag found, it also carries one line that begins with `gnss delay estimate:` (any letter case), followed by the lag as a number and the token `ms`. The rest of the report is free text.
- **Exit status:** 0 when the replay ran to the end. A refused run (missing required stream, missing or non-positive required key, unknown key, unknown aiding value) exits non-zero before writing any solution row and writes a message on standard error that contains the offending key or value.

### 5.3 C replay: `build/replay`

```
build/replay <dataset> [ERRDUMP]
```

- `<dataset>` is the dataset directory (or the path of its `config.yaml`).
- `ERRDUMP`, when given, is written with a per-epoch error dump: lines that begin with `#` are comments; each data row has nine comma-separated numeric fields — seconds since the first GNSS fix (since the first reference sample when aiding is not `gnss`), reference ground speed in m/s, INS roll, pitch, and yaw error against the reference in degrees, INS position error in metres, then ARS roll, pitch, and yaw error in degrees. A row is written at each reference epoch where INS is ready or, with `score.ahrs: 1`, the suite's ARS attitude is published; the fields of a filter that is not published at that epoch are 0. A refused run writes no data row.
- **Exit status:** 0 when the replay ran to the end and every configured limit passed; non-zero when any limit failed; non-zero for a refused run (the refusals of the Python replay, plus a missing or non-positive `score.min_epochs`), which also writes a message on standard error containing the offending key or value. The rest of the report on standard output is free text.

## 6. Custom-CSV runner: `python -m NAVFILTER <mapping.yaml>`

The argument is a nested mapping YAML (distinct from a dataset `config.yaml`). Relative file paths resolve against the YAML's directory.

Sections and keys:

- `imu`: `file`, `time`, `gyr`, `acc`.
- `gnss`: `file`, `format`, `time`, `pos`, `stddev_ned`, optional `vel_ned`. `format` is `llh_deg` (geodetic degrees and metres), `llh_rad` (radians and metres), or `ecef` (ECEF metres).
- `baro`: `file`, `time`, `pressure`.
- `mag`: `file`, `time`, `mag`.
- `wmm`: `year` (decimal year).
- `filter`: `auto_zupt_disable` (0/1).
- `output`: `csv` (solution file path), `csv_hz` (rows per second; 0 → one row per IMU epoch), and the booleans `plotjuggler` and `mavlink`.

A column map for time or a scalar is `{col: <c>, unit: <u>}`; for a 3-vector `{cols: [<c>, <c>, <c>], unit: <u>}`. GNSS `pos` takes `{cols: [...]}` with its frame given by `format`. Each column is a 0-based index or a header-row name. Unit tokens (letter case ignored): time `s`, `ms`, `us`; gyro `deg/s`, `rad/s`; accelerometer `m/s2`, `g`; pressure `Pa`, `hPa`, `mbar`, `kPa`; magnetometer `uT`, `gauss`, `mGauss`, `nT`; GNSS `stddev_ned` `m`; GNSS `vel_ned` `m/s`.

**Solution CSV.** The first row is a header row of column names; one data row per written epoch follows. The columns below are present under exactly these names (further columns and the column order are the implementer's choice); an unpublished value is an empty cell:

| column | value |
| --- | --- |
| `t_us` | epoch time, integer microseconds |
| `mode` | one of `FULL`, `COASTING`, `ATTITUDE_ONLY`, `NONE` |
| `lat_deg`, `lon_deg` | degrees |
| `h_ell_m` | ellipsoid height, m |
| `pos_n_m`, `pos_e_m`, `pos_d_m` | local NED position, m |
| `vel_n_mps`, `vel_e_mps`, `vel_d_mps` | NED velocity, m/s |
| `roll_deg`, `pitch_deg`, `yaw_deg` | degrees |
| `height_m` | arbitrated local height, m |

**Exit status:** 0 when the run completed and the solution file was written; non-zero, with a message on standard error, when the mapping cannot be used.
