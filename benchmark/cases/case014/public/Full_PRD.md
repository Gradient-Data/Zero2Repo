# NAVFILTER — Full Product Requirements Document

## Product overview

**NAVFILTER** is a portable C11 library for 3D navigation state estimation. Its core is a set of Kalman filters that fuse an inertial measurement unit (IMU: accelerometer and gyroscope) with aiding sensors — GNSS/GPS, barometer, magnetometer, local position references (lighthouse / UWB / motion capture), absolute yaw references, scalar ground speed, and zero-velocity / zero-rotation information — into one estimate of **where the body is** and **which way it is pointing**.

A first-time integrator zeros one caller-owned filter instance, hands it a coarse Earth anchor and options (almost every field left at zero picks a conservative consumer-MEMS default), then feeds a stream of IMU epochs with whatever aiding is present that epoch. After a short warm-up the filter reports a ready navigation solution: WGS84 position, local NED velocity, and body-to-NED attitude. A UAV that loses GNSS does not go silent: the navigation suite keeps publishing inertial-fused altitude through the parallel barometric vertical channel and full attitude from the independent attitude filters. A platform that only needs roll and pitch, with freely integrated yaw, can run the standalone ARS from IMU data alone and skip the magnetometer.

Typical uses advertised by the product: drones and autonomous vehicles, robotics, aerospace, cars, embedded tracking, and post-processing of recorded flights or drives. The same filters are reachable from C and from a Python package that wraps the compiled library. Recorded trials are replayed from a dataset directory of CSV streams plus one `config.yaml`.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, call spellings, and header paths belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished NAVFILTER product. Feature points are ordered so foundational capabilities come first; a later feature point may depend on an earlier one, never the reverse.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **INS** | The 3D navigation filter. It estimates local NED position and velocity, body-to-NED attitude, accelerometer bias, and gyroscope bias. |
| **AHRS** | The attitude-and-heading reference filter. Two modes are fixed per instance, listed under FP-06: ARS and AHRS. |
| **ARS** | The roll/pitch attitude filter whose yaw is the integral of the bias-corrected z-rate and is never measurement-corrected (directional gyro). |
| **Barometric vertical channel** | The independent barometer-plus-accelerometer vertical filter: height above a datum (positive up), vertical velocity (positive up), and a slow vertical-acceleration correction. |
| **Navigation suite** | The wrapper that runs INS, one ARS, one magnetometer AHRS, and the barometric vertical channel from the same measurement stream and publishes a best-available solution with an explicit mode. |
| **Python navigator** | The Python high-level entry that drives the navigation suite. Push sensors, run one epoch, read a unified solution. |
| **Python INS wrapper** | The lean Python entry that drives INS alone, without AHRS/baro fallback. |
| **Epoch** | One time-stamped measurement bundle. The IMU sample begins the epoch; aiding fields present on that epoch are fused with it. |
| **Ready** | The INS flag that means position and velocity are currently usable. False during warm-up, after an expired coasting window (unless unlimited dead reckoning is on), and after a GNSS quality-loss exit. |
| **Initialized** | The INS has bootstrapped and holds a 3D state. Position accessors succeed while initialized even if ready is false (for example a frozen coast). Quality-loss re-arm clears this, so those accessors then fail. |
| **Solution mode** | The suite’s four-valued status: FULL, COASTING, ATTITUDE_ONLY, or NONE. Defined in FP-08. |
| **FRD** | Body frame: x forward, y right, z down, right-handed. Every IMU, magnetometer, and lever arm is in this frame. |
| **NED** | Navigation frame: north, east, down. Local positions and velocities are in NED relative to an origin fixed at init. |
| **ECEF** | WGS84 Earth-centred Earth-fixed Cartesian coordinates, metres. GNSS positions arrive in ECEF. Double precision is used for this Earth anchor; the filter hot path is otherwise 32-bit float. |
| **Hamilton quaternion** | Attitude as body-to-NED, scalar-first: real part then vector part. |
| **Tait-Bryan ZYX** | Roll, pitch, yaw of the body relative to NED. Angles in radians unless a file format below says degrees. |
| **Timestamp** | Monotonic integer microseconds. |
| **Specific force** | Accelerometer reading. At rest and level in FRD, the sample is approximately (0, 0, −g): gravity appears as +g along −z. |
| **Aiding** | Any measurement other than the IMU that corrects the INS: GNSS position/velocity, local NED position, magnetometer, absolute yaw, scalar speed, barometric height, zero-velocity, zero-rotation. |
| **Coasting / dead reckoning** | IMU-only propagation after the last absolute position aiding (GNSS or local position). |
| **Coasting window** | Configurable IMU-only budget after which INS ready becomes false and the instance freezes. Default 10 seconds. Unlimited dead reckoning disables this. |
| **Entry gate / exit gate** | Two GNSS quality threshold sets. The entry gate plus its dwell decide whether the 3D solution may start. The exit gate plus its dwell decide whether the 3D solution is given up. Distinct from the per-fix fusion gate. |
| **World Magnetic Model (WMM)** | Built-in lookup of magnetic declination, inclination, total field, and the NED reference field for a geographic position and decimal year. |
| **Local height** | Height above the NED origin, positive up, zero at the origin. Shared by INS and the barometric vertical channel. |
| **Ellipsoid height** | Absolute WGS84 height. Available from INS under GNSS, or as local height plus the estimated local-to-ellipsoid offset during an outage. |
| **ISA altitude** | Barometric altitude from the international standard atmosphere formula, carrying weather offset and model error; not an absolute height. |
| **ZUPT** | Zero-velocity update: a known-standstill velocity measurement. |
| **ZARU** | Zero-rotation update: a known-standstill gyro-bias measurement. |
| **Lever arm** | Body-FRD offset from the IMU to an aiding sensor (GNSS antenna, local-position sensor). |
| **Dataset directory** | A folder of CSV streams plus one `config.yaml`, consumed by both replay harnesses. Layout in FP-10. |

## Public surface inventory

NAVFILTER is a **library** with two language entries and a post-processing harness. Integrators compile the C sources into their firmware or desktop program, or build the shared library and use the Python package. There is no network stack inside the filters themselves.

The public surfaces, grouped by feature point, are:

- Frame conventions, WGS84 ECEF ↔ geodetic conversions, Hamilton / Tait-Bryan mapping, and the World Magnetic Model lookup (FP-01).
- The INS filter: init, per-epoch IMU-plus-GNSS fusion, auto-init, ready flag, position / velocity / attitude / bias accessors (FP-02).
- Further aiding on the same epoch bundle: magnetometer, local NED position, absolute yaw, scalar speed, barometric height inside INS, explicit and automatic ZUPT/ZARU (FP-03).
- Delayed GNSS, local-position, and yaw measurements, including the replay delay estimator (FP-04).
- GNSS entry/exit quality, the coasting window, freeze, re-acquisition, and unlimited dead reckoning (FP-05).
- Standalone ARS and AHRS attitude filters (FP-06).
- Standalone barometric vertical channel and the three height systems (FP-07).
- The navigation suite and Python navigator: parallel filters, mode arbitration FULL → COASTING → ATTITUDE_ONLY → NONE, continuous local and ellipsoid height (FP-08).
- Non-finite input drop, outlier downweighting, the global outlier-rejection override, and fail-safe (never publish a non-finite solution) (FP-09).
- Dataset replay from CSV plus `config.yaml`, and the YAML-configured custom-CSV runner (FP-10).

Feature points below group these entries by capability. They do not invent additional product surfaces.

## Non-functional constraints

- **Form factor:** A C11 library with no heap and no operating-system calls in the core filters. All filter state lives in caller-owned instance structs of fixed size. The same sources build for bare-metal microcontrollers and for a desktop host.
- **Dependencies:** The core needs a C11 compiler, GNU make, and libm. No GPU, no accelerator, no runtime third-party C libraries. Optional Python bindings and replay helpers need CPython 3.8 or newer plus PyYAML and NumPy.
- **Precision:** The per-epoch hot path is 32-bit IEEE-754 float. Double precision is reserved for the WGS84 ECEF / lat-lon-height anchor.
- **Determinism:** Per-epoch work has a bounded worst-case execution time: no unbounded loops, no recursion, no iteration counts that depend on measurement values.
- **Platforms:** POSIX and Windows are both intended. The product must build and run on Linux x86_64 with a C11 compiler.
- **Hardware:** CPU-only. There is no accelerator requirement.
- **Conventions:** Body FRD, navigation NED, Hamilton quaternion (scalar first), timestamps in integer microseconds, filter angles in radians. Matrices are column-major.
- **Defaults:** A configuration field left at zero (or an all-zero list) means “use the built-in default”, never “inject zero noise”. An all-zero options block is a working, conservative filter.
- **Error text:** Wording of log lines and messages is the implementer’s. What the product reports is success versus failure, ready versus not, which solution mode, whether a value is published, and its diagnostic counters.
- **Identity of the product:** The library, the Python package, the shared object, and the dataset configuration keys use the spelling **NAVFILTER**.

## Required substance (global)

Every feature point below is a core capability of the CPU library. Each is provided by the NAVFILTER filters, suite, and harnesses themselves: the navigation solution is computed by fusing the IMU with the supplied aiding, and the replay harnesses compute it from the dataset's streams.

## Non-goals

- A public reference-board firmware. The hardware protocol and calibration GUIs exist as host tools around a board whose firmware is not part of this product surface.
- Live UDP ingest, PlotJuggler / MAVLink telemetry streaming, Google Earth model packaging, multi-page plot export, and the post-processing Qt GUI as product capabilities. Replay that produces a navigation solution from CSV is FP-10; live sockets, plots, and interactive windows are not.
- IMU-TK / Allan-variance host utilities, u-blox receiver configuration scripts, OBD-II dongles, and SPARTN key loading.
- Requirements-database machinery, sanitizer builds, coverage HTML, and Doxygen as product capabilities.
- Claiming Galileo HAS, SPARTN, or RTK as filter features: those are receiver-side accuracy sources. NAVFILTER consumes whatever ECEF fix and covariance the caller supplies.
- Optional magnetometer hard-iron bias estimation, IMU/magnetometer calibration matrices consumed by the filter, and automotive course-over-ground yaw. They exist in the library but are outside the ten feature points of this document.
- Heap allocation, threads, or an operating-system abstraction inside the core filters.
- 64-bit FPU as a requirement of the hot path.

---

## Feature points

### FP-01: Frames, geodetic conversions, and the World Magnetic Model

**Public entry:** The geodetic / quaternion helpers shipped with the C library and re-exported by the Python package, plus the World Magnetic Model lookup. These run without constructing an INS instance. Filter-facing use of the same conventions is FP-02 through FP-08.

**Normal behavior:**

- Body quantities are FRD. Navigation quantities are NED: the first component of a local position or velocity is north, the second east, the third down. A specific-force sample of a vehicle sitting still on a level pad is near (0, 0, −g) in FRD.
- Attitude is a Hamilton quaternion mapping body to NED, scalar first. Roll, pitch, yaw are Tait-Bryan ZYX in radians: the body-to-NED rotation is R = Rz(yaw) · Ry(pitch) · Rx(roll). The quaternion produced from roll, pitch, and yaw matches that composition to 1e-5 on each component. Converting roll, pitch, and yaw to a quaternion and back recovers the angles to 1e-5 rad for attitudes away from gimbal lock. The C and Python conversions agree to 1e-5 on every quaternion component.
- Geodetic positions use the WGS84 ellipsoid (semi-major axis 6378137.0 m, flattening 1/298.257223563), not a sphere. Geodetic → ECEF → geodetic recovers latitude and longitude to 1e-10 rad and height to 1e-4 m anywhere on the ellipsoid; ECEF → geodetic → ECEF is consistent to 1e-4 m (3-D distance). The C and Python conversions follow the same ellipsoid and the same tolerances.
- Small local displacements convert to geodetic deltas consistently with NED: a northward displacement changes latitude only, an eastward one changes longitude only, and an upward one (negative down) raises height by the same amount.
- The NED transport rate of the navigation frame depends on the east velocity, and every output of the transport-rate helper stays finite at every latitude for any finite velocity. A quaternion whose norm does not exceed 1e-10 (including the zero quaternion) normalizes to the identity (real part 1, vector part 0) rather than NaN.
- The World Magnetic Model lookup implements the WMM2025 model (degree and order 12 with its secular variation). Given latitude, longitude, and a decimal year, it returns magnetic declination in degrees (positive east), inclination in degrees (positive down in the northern hemisphere), total field in microtesla, and a three-axis NED reference field in microtesla. Declination agrees with WMM2025 to within 0.15° at mid-latitude sites away from the geomagnetic poles, and to within 0.6° at absolute latitudes above 88°. Inclination agrees with WMM2025 to within 15° and total field to within 20 µT. The decimal year is a real input: different years give the model's different values.
- The assembled NED field is self-consistent: its horizontal heading (east over north) equals the declination to 0.05°, and its magnitude equals the total field to a relative 1e-3. The C library exposes all four quantities. The Python package re-exports the NED field with the same self-consistency against the C declination and total field.

**Boundary / error behavior:**

- Latitude is clamped to [−90°, +90°]. Longitude is wrapped modulo 360° into (−180°, +180°], so longitudes that differ by whole turns give the same result to 1e-3°, and every finite longitude yields finite outputs. Years outside the model epoch are extrapolated with the secular variation rather than refused or clamped.
- A gimbal-lock pitch (near ±π/2) still yields finite roll/pitch/yaw; the mapping does not abort and does not produce NaN.

---

### FP-02: INS 3D navigation from IMU and GNSS

**Public entry:** The C INS instance and the Python INS wrapper. The caller zeros the instance, supplies an initial Earth anchor and options, then feeds epochs (IMU plus optional GNSS) and reads position, velocity, attitude, and biases. Auto-init, quality gates, and coasting lifecycle details that refine when ready is true are scoped in FP-05. Extra aiding sensors are FP-03. Delay is FP-04. The suite that wraps INS is FP-08.

**This feature point uses FP-01.** Positions, attitudes, and timestamps follow FP-01.

**Normal behavior:**

- Construction requires a coarse WGS84 ECEF origin (the local NED origin). A zeroed options block with auto-init enabled is valid. Fields left at zero resolve to conservative consumer-MEMS defaults; they do not lock the corresponding process noise at zero.
- The INS estimates, continuously after bootstrap: local NED position relative to that origin, NED velocity, body-to-NED attitude, body-frame accelerometer bias, and body-frame gyroscope bias, each with its 1-sigma uncertainty.
- Each epoch is one bundle. The caller marks which sub-measurements are valid. An epoch that carries only IMU is normal. A GNSS position, when present, is ECEF metres with a 3×3 NED covariance (a diagonal receiver fills the three diagonal entries and leaves the rest zero). A GNSS velocity, when present, is NED metres per second with a NED covariance. The Python sensor-push calls accept either the three NED diagonal variances or a full 3-by-3 NED covariance.
- Auto-init (the default happy path): the filter bootstraps from the stream. Roll and pitch come from accelerometer leveling over a window (by default the most recent 0.1 s of IMU samples). Yaw comes from an absolute yaw measurement if present, else the magnetometer, else it is left unknown with a correspondingly large uncertainty. Position and velocity come from the first usable GNSS (or local-position, FP-03) fix that also satisfies the entry gate and dwell of FP-05. A coarse origin guess is enough; the first real fix refines the solution.
- Once a stationary IMU has been fed together with GNSS fixes inside the default entry gate for longer than the entry dwell plus the ready wait below, the INS is ready, its published ECEF position is within 0.5 m of the fixes, and roll and pitch are level to within 0.4°.
- The GNSS antenna lever arm in body FRD is applied: a non-zero lever arm couples attitude into the position residual at the measurement’s time of validity, so under rotation the position residual depends on the lever arm.
- **Filter-update epochs and IMU intervals:** a filter-update epoch is a valid IMU epoch on which the INS propagates its uncertainty (covariance prediction). How often the filter updates at high IMU rates is the implementer's choice, but a valid IMU epoch that comes 0.1 s or more after the previous filter-update epoch is always a filter-update epoch. An interval of up to 0.5 s since the previous filter-update epoch is an ordinary strapdown and filter-update step. With unlimited dead reckoning off, a longer forward gap resets the INS: it becomes uninitialized, its accessors fail, and with auto-init on (and re-acquire not disabled) it bootstraps again from the stream. With unlimited dead reckoning on, such a gap skips that epoch (FP-05).
- Ready is false until both a minimum of four filter-update epochs and 1.5 seconds of runtime have elapsed after the instance is initialized, even if a fix is already in. Reading the solution for use as a navigation answer is gated on ready. Accessors for position, velocity, and attitude succeed as soon as the filter is initialized, including during a later freeze (FP-05); they fail when the instance is not initialized.
- The Python INS wrapper uses the same conventions and the same three-move loop: push IMU (and any GNSS), run the epoch, then read. Readers do not themselves run the filter. Forgetting the epoch step leaves ready false.

**Boundary / error behavior:**

- Init fails (no instance is started) when the supplied ECEF origin has Euclidean norm below 1 km — a neighbourhood of (0, 0, 0), not a point on the Earth.
- Init fails if a required pointer is missing: the instance, its init block, and its options block are all required (a zeroed options block is valid; a missing one is not).
- An IMU epoch whose accelerometer or gyroscope is marked invalid is not a strapdown step. Processing continues with later valid IMU.
- GNSS with a non-positive covariance diagonal is not fused. A fix whose reported accuracy exceeds the fusion gate of FP-05 is not fused. Neither case disables the filter.

---

### FP-03: Aiding beyond GNSS

**Public entry:** The same INS epoch bundle and Python sensor-push calls as FP-02, with additional valid fields: magnetometer, local NED position, absolute yaw, scalar ground speed, barometric static pressure (as an INS height source), and explicit zero-velocity / zero-rotation flags. Automatic standstill detection is part of this feature point. The standalone barometric vertical channel is FP-07. Suite-level height arbitration is FP-08.

**This feature point uses FP-02.** GNSS-only fusion remains available; this FP adds the other aiding the same instance accepts.

**Normal behavior:**

- **Local NED position** (lighthouse, UWB, motion capture, total station): the sample is already in the filter’s NED frame (origin = the init Earth anchor). Aligning the tracker’s frame is the caller’s job. A local-position stream whose covariance is inside the entry gate, together with a stationary IMU, bootstraps a ready 3D solution without any GNSS, and the published local position then matches the tracker. Outliers on this channel are skipped, never downweighted: an implausible sample is omitted from fusion rather than fused at reduced weight.
- **Magnetometer:** fused so that only heading is corrected — a disturbed field must not tilt roll or pitch. Fusion is rate-limited; the default minimum interval is 1 second (a long-term yaw anchor, not a per-epoch yaw sensor). A negative interval disables the limit. A sample supplied without per-axis variance uses the library’s own weak default, never a zero-noise measurement. After the World Magnetic Model is armed from a geographic position and decimal year (FP-01), estimated yaw is relative to true north; until then the magnetic reference is magnetic north.
- **Absolute yaw** (dual-antenna GNSS, mocap pose, gyro compass): a scalar heading in radians. Any single-turn value is accepted and normalized.
- Fusion of absolute yaw is skipped near gimbal lock (pitch approaching ±90°).
- **Scalar ground speed** (OBD-II, wheel odometry, Doppler log): the magnitude of velocity, with no direction. It observes speed only, not heading: an along-track speed error is pulled toward the measurement, a purely sideways velocity error is not. If the filter’s own speed is below a minimum (default 1 m/s), the sample is skipped.
- **Barometric height inside INS:** when barometer samples are supplied and the barometric height source is selected, INS uses the barometer for the vertical channel and restricts GNSS position fusion to the horizontal. With both GNSS and barometer wired and the disable switch off (the default), the barometer is the height source, so a usable vertical solution survives a GNSS outage. Setting the barometric-height disable switch forces GNSS height instead. A local-position bootstrap keeps tracker height even when a barometer is present.
- **Explicit ZUPT / ZARU:** a caller who knows the platform is standing still flags zero-velocity and/or zero-rotation on that epoch. The filter then fuses a direct velocity measurement of zero and/or a direct gyro-bias measurement of a still body. The flags do not themselves create filter-update epochs (FP-02), and each kind is fused at most once between two consecutive filter-update epochs, however many epochs in between carry the flag.
- **Automatic ZUPT / ZARU:** enabled by default. The detector declares stillness from the IMU sample spread over a short window (bias does not trip it) plus magnitude bounds (by default, a bias-corrected rotation rate above 5 °/s is never stillness, so a steady turn is not stillness) and, when a recent accurate GNSS velocity exists, a speed gate. A GNSS velocity stays recent for at least 1 s and at most 3 s after its epoch; once older it no longer gates, so after GNSS stops a still IMU alone decides stillness. It does not gate on the filter’s own velocity. A public diagnostic reports whether the detector currently considers the platform stationary. A runtime disable switch turns the detector off without affecting explicit ZUPT/ZARU flags; re-enabling requires a fresh stillness run.

**Boundary / error behavior:**

- An absolute yaw whose magnitude exceeds one full turn is treated as a unit or unwrapping mistake: it is not fused, and the invalid-input diagnostic counter increments. It is not wrapped into a plausible but wrong heading.
- Magnetometer fusion is skipped when the horizontal reference field is unusable (near-zero or near-vertical field).
- Local-position samples whose covariance is degenerate are not fused.
- Automatic ZUPT does not fire on a single IMU sample: the variance window must cover both a minimum duration and a minimum sample count before the first verdict. An epoch with no IMU leaves the window and the latched verdict untouched. The verdict must then hold for the stillness dwell (default 0.2 s) before the detector reports stationary. The window's minimum duration and sample count are the implementer's choice, provided that with the default dwell a platform that has come to rest is reported stationary within 1 s.

---

### FP-04: Delayed aiding

**Public entry:** The delay fields on GNSS position/velocity, local position, absolute yaw, and scalar ground speed in the same epoch bundle as FP-02 / FP-03 (and the matching Python delay argument). The Python replay harness’s GNSS-latency estimator is the offline measurement of that delay from a dataset. History depth and what happens when a delay is too old are this feature point. Quality gates that decide whether a fix is used at all remain FP-05.

**This feature point uses FP-02 and FP-03.**

**Normal behavior:**

- A GNSS, local-position, yaw, or scalar-speed measurement may be older than the current IMU epoch by a known latency. The filter fuses that sample against the navigation state that was valid at the measurement’s time of validity, not as if it had arrived at the current IMU timestamp. This is the path GNSS receivers need: processing, internal filtering, and serial transport commonly add 100–200 ms.
- Delays up to 500 ms are fused this way when the history still holds that time of validity. A delay of zero is current-time fusion (the usual case).
- On a moving trajectory, a late GNSS position fused with its delay stated produces a smaller along-track position error than the same sample fused as if it were current.
- The Python replay estimator, given a dataset that has IMU, barometer, and GNSS with usable vertical velocity, plus a real climb or descent, reports a latency matching the lag between the near-zero-latency barometric vertical velocity and GNSS vertical velocity. Forcing the estimator on a dataset that meets those inputs produces a lag, not silence.

**Boundary / error behavior:**

- A measurement older than 500 ms is not fused as a delayed update and is not applied as a current-time update. The same skip applies when the delay is still within 500 ms but the history does not hold that time of validity. GNSS of either kind increments the no-anchor diagnostic; local-position, yaw, and scalar-speed samples are skipped without that count. A later in-window sample with a history match fuses; the skip is per sample.

---

### FP-05: Quality gates, coasting, and re-acquisition

**Public entry:** INS options (and the matching `config.yaml` / Python config fields) that set GNSS fusion / entry / exit thresholds, the coasting window, unlimited dead reckoning, and the re-acquire / stop-disable switches. Its effects show in the ready flag, whether position accessors still succeed, the dead-reckoning age, and — when the caller is the suite of FP-08 — the solution mode.

**This feature point uses FP-02.** It refines when the 3D solution of FP-02 is entered, held, frozen, or given up. Suite mode names are defined in FP-08; this FP states the INS-side conditions those modes read.

**Normal behavior:**

- Three distinct GNSS quality questions:
  1. **Fusion gate:** may this one fix be fused. Default limits equal the accuracy caps (120 m position, 60 m/s velocity), so an unconfigured filter does not reject a fix for reported accuracy alone; it caps and fuses. A broken (non-positive) covariance is always rejected. A caller who wants a hard accuracy gate sets the fusion limits below the caps.
  2. **Entry gate:** may the 3D solution start. Defaults: 2 m horizontal and 3 m vertical position 1-sigma, 0.25 m/s horizontal and 0.30 m/s vertical velocity 1-sigma, held for a 5 s dwell (the dwell can be disabled so the first good fix starts 3D). Fixes that are fusable but coarser than this keep being consumed without ever starting 3D.
  3. **Exit gate:** must the 3D solution be given up. Defaults: 5 m / 7 m position, 0.4 / 0.5 m/s velocity, for a 10 s dwell. When the dwell of bad fixes elapses, INS re-arms into collecting: initialized becomes false, position and velocity accessors fail (nothing keeps drifting off bad fixes), and a later return is a full re-bootstrap through the entry gate. IMU biases are carried into that re-bootstrap with their uncertainty inflated. The exit can be disabled so the filter never leaves 3D on GNSS quality alone. Setting the re-acquire disable switch, when that dwell of bad fixes elapses, keeps the filter running and only clears ready, without a full re-arm, so ready is false while the instance stays initialized and position accessors still succeed.
- **Coasting window:** INS tracks the time since the last absolute position aiding (GNSS or local position) and publishes that age in whole milliseconds while it is initialized; an INS that is not initialized publishes no age. While the age is within the window (default 10 s) and INS is otherwise ready, ready stays true: this is IMU-only dead reckoning with a drifting position. Once the age exceeds the window, ready becomes false and the whole instance freezes — strapdown, covariance (every 1-sigma), attitude, biases, position, and velocity hold their last value — until re-acquisition. A fusion-usable GNSS velocity that arrives inside the expired window without a usable position is still fused into that held state: it does not re-anchor, ready stays false, and the coasting age keeps counting. Unlimited dead reckoning disables the window: ready does not degrade on IMU-only time, and freeze / re-acquire do not apply. With unlimited dead reckoning, the first fusion-usable GNSS fix after an IMU-only gap longer than the window is fused as an ordinary measurement update: the published position moves toward that fix by the update's weight rather than snapping to it, and the yaw uncertainty is not reset.
- **Re-acquisition** after an expired window (unlimited off): the next usable position fix that passes the fusion gate re-anchors the 3D solution and ready is true on that epoch — not an entry-dwell bootstrap. Attitude and IMU biases are kept across the freeze; yaw uncertainty is reset to unknown unless a heading hint is supplied. With the navigation suite (FP-08), that hint is the parallel AHRS/ARS.
- **GNSS fusion rate limit:** by default at most one fused GNSS epoch per 100 ms. Faster streams are skipped whole and counted. A negative interval disables the limit. The limit is suspended while the coasting window is expired so a tunnel exit is not paced. A related position-decimation option, default off, spends only every Nth combined position-and-velocity epoch as a position fuse (the rest fuse velocity alone) to avoid double-counting a receiver’s internally coupled solution.

**Boundary / error behavior:**

- A prescribed (non-auto) init is the caller’s assertion and is not held at the entry dwell.
- Vertical position rows that the height-source choice of FP-03 has dropped are ignored by the fusion and exit gates, not the entry gate: a barometric-height run does not leave 3D because GNSS vertical accuracy is poor. The entry gate still grades GNSS vertical accuracy at bootstrap, before the height source is latched.
- When unlimited dead reckoning is on, a forward time gap longer than 0.5 s (FP-02) skips that epoch; subsequent normal-rate epochs run again rather than remaining stuck on the same jump.

---

### FP-06: ARS and AHRS attitude

**Public entry:** The standalone attitude-filter instance, in either ARS or AHRS mode, and the two instances the navigation suite (FP-08) runs in parallel. Helpers that estimate roll/pitch from a static accelerometer sample and yaw from a tilt-compensated magnetometer sample are part of this surface. INS attitude is FP-02; this FP is the IMU-only (plus optional magnetometer) attitude path.

**This feature point uses FP-01.** True-north yaw uses the WMM of FP-01.

**Normal behavior:**

- Exactly two modes, fixed per instance:
  - **ARS:** roll and pitch are corrected from the accelerometer against gravity; yaw is the integral of the bias-corrected z-rate and is never measurement-corrected. Gyro bias is estimated online. Earth rate is not corrected.
  - **AHRS:** as ARS, plus yaw is stabilized with tilt-compensated magnetometer heading. Magnetic disturbances do not tilt roll/pitch. Until a geographic position and decimal year are supplied, yaw is relative to magnetic north; after they are supplied, WMM declination is applied and yaw is relative to true north. Switching declination steps the published yaw by the declination change (it does not slew there through magnetometer fusion). The published gyro-bias estimate does not jump. A position call with any non-finite argument is ignored as a whole.
- Configuration fields left at zero take documented defaults. For a standalone instance the initial-attitude standard deviations are mandatory (roll and pitch; yaw too in AHRS mode); a non-positive or non-finite standard deviation, or a non-finite initial attitude, is refused at init. A zero initial attitude is valid, and an ARS instance accepts a zero yaw standard deviation.
- For a static body sampled at 100 Hz or faster, with gyro noise density up to 1e-4 (rad/s)/√Hz, accelerometer noise up to 0.05 m/s², a constant gyro bias of up to 5 °/s per axis, and an initial roll/pitch error of up to 5°, the filter converges within 10 s to roll and pitch within 0.2° of truth and to x/y gyro bias within 0.1 °/s.
- In ARS mode, a constant z-rate integrates into yaw with no magnetometer or GNSS correction, even when a magnetometer is present on the instance (the instance is ARS). In AHRS mode, a persistent heading error is pulled toward the magnetic (or true-north) reference.
- The static leveling helper returns the roll and pitch of a body at rest whose accelerometer measures the given specific force (level for a sample along −z). The magnetometer heading helper returns the yaw of a body with the given roll and pitch whose magnetometer measures the given field, relative to the field’s horizontal direction.
- An explicit zero-rotation flag is opt-in: the caller (or the suite, using INS’s standstill detector) flags known zero body rate; the filter then fuses a direct gyro-bias measurement. The attitude solution publishes roll, pitch, yaw, their 1-sigma, and the gyro bias; it carries no velocity, unlike the navigation filter on the same stream.
- The suite’s ARS bootstraps roll/pitch from the first valid IMU; its yaw is 0 unless a known heading was supplied (prescribed INS attitude or a static yaw hint). The suite’s AHRS waits for the first magnetometer sample before starting. If after an ARS or AHRS instance has been producing a solution the reported attitude 1-sigma stays implausibly large (for example after a long outage of the correcting sensor left that 1-sigma unreduced), that instance’s attitude accessors fail. Implausibly large means above the attitude filter's precision-restart thresholds — by default 10° roll or pitch, or 90° yaw (AHRS only), once 10 s have passed since init; a configured threshold replaces the default for its axis and a negative one leaves that axis unchecked, and the check can be switched off. An ARS instance never checks yaw, even when a yaw threshold is configured. The suite then re-bootstraps on the next suitable epoch — IMU for ARS, a magnetometer sample for AHRS — so those accessors succeed again without the caller re-initing; a standalone caller must re-init.

**Boundary / error behavior:**

- Non-finite gyro or accelerometer samples drop the epoch; a non-finite magnetometer sample is ignored; both increment the instance’s invalid-input counter. The next valid epoch proceeds.
- A backwards timestamp skips that epoch; later increasing timestamps continue. A forward gap larger than 0.2 s skips attitude integration for that epoch (sensor-outage semantics).
- Magnetometer heading fusion is skipped near gimbal lock, for near-zero fields, and when the de-tilted horizontal field is unusable.
- An optional field-strength gate (off by default), when enabled and a position is known, downweights (does not drop) a heading sample whose magnitude disagrees with the WMM total field by more than a tolerance (default 30%).

---

### FP-07: Barometric vertical channel

**Public entry:** The standalone barometric vertical-channel instance, and the same filter inside the navigation suite (FP-08). INS-internal barometric height selection is FP-03; this FP is the independent vertical filter and the three height systems.

**This feature point uses FP-01** for timestamps and the body-to-NED rotation supplied each epoch.

**Normal behavior:**

- The filter estimates three quantities: height above its start anchor (positive up), vertical velocity (positive up), and a slow additive correction to measured vertical acceleration. Between barometer samples, a level IMU plus the supplied attitude keeps height and climb rate consistent with specific force after gravity is removed. The barometer observes height only.
- Static pressure in pascals is converted to altitude with the tropospheric international standard atmosphere (sea-level standard pressure 101325 Pa maps to zero altitude, and tropospheric pressures map to the standard-atmosphere altitude within a metre), then anchored at the init pressure so that the height passed in at init (zero = “height above start”) is the datum. Implausible barometer innovations are downweighted, not dropped, so a persistent weather offset cannot deadlock the filter and a single spike does not make the height jump to it.
- A separate offset estimate tracks the slowly varying difference between a local height (above the caller’s vertical datum) and GNSS ellipsoid height — the ellipsoid height of the datum origin. Local height plus that offset is an absolute height, also during a GNSS outage. How fast that offset tracks is the implementer’s choice. Pairs without a positive GNSS vertical variance are skipped.
- After a few seconds of realistic pressure around a pad plus a level IMU, height stays near the anchor (zero if started at zero) and vertical velocity stays near zero. Climbing then holding a new pressure yields a higher local height of the same sign as the ISA altitude change.
- ISA altitude is readable separately from the datum-relative height; it still carries weather and model error.
- A vertical zero-velocity update, when triggered, fuses a direct zero climb-rate measurement and is not gated on the filter’s own velocity.
- If after the instance has been producing a solution the reported height or vertical-velocity 1-sigma stays implausibly large (for example after a long barometer outage left it integrating on the accelerometer alone), height and climb-rate accessors fail. Implausibly large means above the vertical channel's precision-restart thresholds — by default 20 m height or 10 m/s vertical-velocity 1-sigma, once 8 s have passed since init; a configured threshold replaces the default, a negative one leaves that quantity unchecked, and the check can be switched off. The suite then re-bootstraps so those accessors succeed again without the caller re-initing; a standalone caller must re-init.

**Boundary / error behavior:**

- Non-finite pressure or IMU samples are dropped; processing continues. Init itself reports success or failure: a non-finite anchor pressure fails; a negative anchor pressure, which the tropospheric standard atmosphere cannot map to a finite altitude, fails; sea-level-standard pressure and ordinary tropospheric positive pressure succeed. Whether finite positive pressures map onto a capped high-altitude limit or a floor below sea level is the implementer’s choice; every finite, non-negative pressure sample maps to a finite ISA altitude.
- A backwards timestamp skips that epoch; later increasing timestamps continue. A forward gap larger than 0.5 s skips IMU-driven height integration for that epoch (sensor-outage semantics) while a barometer sample on that same epoch is still fused; a gap of 0.5 s or less is integrated.
- An all-zero config is valid and fills defaults (including a 2 m default barometer altitude 1-sigma). A per-sample altitude 1-sigma of zero uses the configured value.

---

### FP-08: Navigation suite and graceful degradation

**Public entry:** The C navigation suite and the Python navigator. One epoch call drives INS (FP-02, FP-03, FP-05), ARS and AHRS (FP-06), the barometric vertical channel (FP-07), and the local-to-ellipsoid offset (FP-07). The caller reads one unified solution: mode, ready, best attitude, positions, velocity, and heights.

**This feature point uses FP-02, FP-05, FP-06, and FP-07.** It does not replace them: INS-only callers still exist. This FP is the arbitration and the parallel operation.

**Normal behavior:**

- Exactly four solution modes, each reported as a distinct value:
  - **FULL:** INS is ready and the last absolute position aiding is no older than 2 seconds.
  - **COASTING:** INS is ready but the last absolute position aiding is older than 2 seconds (IMU-only, position drifting inside the coasting window of FP-05).
  - **ATTITUDE_ONLY:** INS position/velocity is not usable (not initialized, quality-loss re-arm, or expired coasting window), but ARS or AHRS is initialized so roll/pitch/yaw remain available.
  - **NONE:** nothing usable yet.
- Best-available attitude is INS when INS is ready, else the magnetometer AHRS, else ARS. A consumer keeps receiving an attitude through a GNSS outage. When the suite falls back to ARS after INS was once converged, yaw is the last good INS heading plus the yaw *change* the ARS free-integrated since — not an arbitrary zero.
- Local height (positive up, zero at the NED origin) is available whenever any local height source is running, including the barometric vertical channel during a GNSS outage. The first source to start fixes the datum; a later source conforms so height is continuous (no jump) when a source arrives or leaves. With GNSS and barometer both present, the barometer is the outage-surviving local-height reference (FP-03). An external local-position (mocap) system owns the NED frame: the suite does not shift the INS origin out from under it; it subtracts a constant offset from every local-position sample instead.
- Ellipsoid height is reported only after a real GNSS fix has anchored the origin to WGS84. Indoor local-position-only runs do not pass off the prescribed init origin as ellipsoid height. Under GNSS, ellipsoid height comes from INS; during an outage it is local height plus the offset of FP-07. The suite reports whether an absolute height is currently available.
- The suite raises its zero-rotation flag from INS’s standstill detector (FP-03, including its GNSS-speed gate) and passes it to ARS and AHRS; the suite reports whether that flag is raised on the current epoch. A suite option makes ARS and AHRS rely only on that INS decision, never on stillness detection of their own.
- The Python navigator exposes the same four mode names as text, a ready flag, roll/pitch/yaw, ECEF and local position, NED velocity, datum height, and ellipsoid height, with the same three-move loop as FP-02. On a stationary IMU with GNSS inside the default entry gate, after the entry dwell and the ready wait, it reports mode FULL, ready true, and a position within 0.5 m of the fixes. Readers do not run the filter; skipping the epoch step leaves mode NONE.
- Outlier-rejection disable and the definition of standstill are one decision for the whole suite: constructing the suite from INS options applies those two settings to INS, ARS, AHRS, and the barometric vertical channel, so they do not have to be restated per filter.

**Boundary / error behavior:**

- Mode NONE on a null or unused instance.
- After GNSS quality-loss re-arm (FP-05), mode is ATTITUDE_ONLY; INS position accessors fail; suite attitude remains the AHRS/ARS value.
- After the coasting window expires, mode is ATTITUDE_ONLY while ARS/AHRS live; INS ready is false; INS is frozen (FP-05). The next fusion-usable position fix returns the suite to FULL on that epoch.
- A static initial-attitude hint, armed after suite init and before the first epoch, seeds INS auto-init and ARS yaw only until INS itself initializes; it does not bias a later re-acquisition.

---

### FP-09: Input sanitization, outliers, and fail-safe outputs

**Public entry:** Every per-epoch update on INS, AHRS/ARS, the barometric vertical channel, and the suite, plus the diagnostic counters and the global outlier-rejection override (the same switch on the filter options and on `config.yaml`). Fusion behavior of healthy measurements is FP-02 through FP-08; this FP is what happens when inputs or published outputs are not healthy.

**Normal behavior:**

- Non-finite measurement payloads (NaN or Inf) are dropped at the API boundary and counted in the invalid-input diagnostic. A single corrupt sample does not disable the filter; the next valid epoch proceeds. Non-finite noise densities fall back to defaults. Non-finite optional fields (lever arms, cross-covariance) are treated as zero.
- Aiding measurements that are statistically implausible do not corrupt the state. Persistent absolute references (GNSS, yaw, magnetometer, barometer) are downweighted rather than rejected, so a persistent offset cannot deadlock the filter. High-rate glitchy local-position samples are skipped instead (FP-03).
- A single configuration switch disables that downweighting across every fusion filter in the suite: every measurement is fused at its nominal variance, and the downweight diagnostic does not increase. Off by default. Standalone INS / AHRS / barometric-vertical-channel instances have the same switch on their own config.
- The system never publishes a non-finite navigation solution: a successful position, velocity, or attitude read after a dropped non-finite sample is finite.
- Diagnostic counters for silent reject/skip paths (timing anomalies, GNSS gating, fusion failures, auto-ZUPT triggers, invalid inputs, downweights) are readable and are not acted on by the filter. A GNSS position covariance whose diagonal entries are positive — so the fusion gate of FP-05 does not reject it as a broken (non-positive) covariance — but that is not positive definite is a fusion failure: that diagnostic increases, GNSS gating and invalid-input do not, the sample is not fused, and the next valid epoch proceeds. A backwards timestamp on INS is a timing anomaly: that diagnostic increases, invalid-input and downweight do not, and the epoch is skipped. Only the backwards sample itself is counted; processing resumes with the next increasing timestamp.

**Boundary / error behavior:**

- Zero-velocity and zero-rotation updates are not statistically gated.

---

### FP-10: Dataset replay from CSV and config.yaml

**Public entry:** The C replay harness and the Python replay program, both consuming a dataset directory; and the Python YAML runner that maps custom CSVs into the same navigator loop. Live UDP and the Qt GUI are non-goals. Filter semantics of what is replayed are FP-02 through FP-09.

**This feature point uses FP-08** (it drives the navigation suite). The file layout and harness behavior are this FP.

**Normal behavior:**

- A dataset directory contains one `config.yaml` and CSV streams. Both replay harnesses require the IMU stream and the reference trajectory; GNSS is required when aiding is `gnss`; magnetometer, barometer, and speed are optional. Conventional names, each with a leading `#` header line and a first column `t_us` in microseconds, then:
  - `imu.csv` — gyro FRD x/y/z [rad/s], accelerometer FRD x/y/z [m/s²]; an optional eighth column IMU die temperature [°C] is ignored by both harnesses.
  - `ref.csv` — latitude [deg], longitude [deg], height [m], roll/pitch/yaw [deg], NED velocity north/east/down.
  - `gnss.csv` — latitude [deg], longitude [deg], height [m]; the six unique NED position-covariance entries in the order north-north, north-east, north-down, east-east, east-down, down-down [m²]; NED velocity north/east/down; the six unique NED velocity-covariance entries in that same packed order [(m/s)²]; and a velocity-valid flag. Zero diagonal means “unknown” and is replaced at replay time by the config fallback: the horizontal position fallback for north and east, the vertical one for down, and the velocity fallback for each velocity axis. Under aiding `ref` the synthesized fix carries exactly those fallback variances.
  - `mag.csv` — magnetometer FRD x/y/z [µT].
  - `baro.csv` — static pressure [Pa].
  - `speed.csv` — scalar ground speed [m/s]; per-sample uncertainty and delay come from `config.yaml`, not extra columns.
- An `inputs:` section may override those filenames per stream, relative to the `config.yaml` directory. Unset keeps the conventional name.
- `config.yaml` tells the harness how to run: aiding mode, init mode, IMU noise model (required), lever arms, gates, calibration, and regression limits. Every key is optional except the IMU gyro and accelerometer spectral densities (and, when aiding is `ref`, the GNSS fallback standard deviations: a horizontal-and-vertical position pair and one velocity value). Those required values must be written and positive: omitting one or writing 0 for any of them, including either element of the position pair, aborts the run before any solution is produced; a positive written value lets the same directory run. The C harness also requires the scoring minimum count of evaluated epochs, written and positive, on the same terms; for the Python replay that key is optional. Optional keys still treat 0 as the built-in default. Both harnesses reject an unknown key and name it: a typo must not produce a full run. Two sections used only by other tools in the same directory — the local-frame origin block and the radio-link block — are accepted and ignored by both replay harnesses.
- `aiding` is exactly one of: `gnss` (real per-epoch covariance from `gnss.csv`), `ref` (fix synthesized from `ref.csv`), `none` (no absolute position aiding). Unrecognized aiding values are refused with a non-zero exit; `none` is not that refusal. On `none`, INS stays uninitialized for the whole log and ARS attitude still exists. Omitting the optional barometer is legal. A present barometer still runs the vertical channel, observed as published local height: matching pad pressure stays near the pad, and a pressure drop consistent with a climb yields a higher local height of the same sign as that altitude change. `init` is `auto` or `ref`.
- Replaying a dataset directory that includes IMU, GNSS, and the reference trajectory produces a navigation solution for the length of the log: modes move through FULL when GNSS is present, and the published lat/lon/height is a fused INS solution, not a copy of the reference or of the raw GNSS. The Python replay reports the suite's final solution mode when the run ends.
- The C harness is the regression gate: it compares the solution with the reference trajectory and exits non-zero when any configured limit is violated. It requires a positive minimum count of evaluated epochs; the Python replay fills a zero default and still produces a solution. Evaluation starts a configurable warm-up time after the first GNSS fix (after the first reference sample when aiding is not `gnss`) and uses each reference epoch from then on. Each limit is a pass when the measured quantity is strictly below it:
  - minimum epochs: the number of evaluated epochs at which INS is ready must reach the configured count;
  - position: the root-mean-square, over evaluated epochs where INS is ready, of the 3-D distance between the INS position and the reference position;
  - attitude bias and spread (when attitude evaluation is on, the default): the absolute mean and the standard deviation, over those epochs, of the INS roll error and of the pitch error against the reference (each error wrapped into ±180°); the yaw bias and spread limits measure the same for yaw;
  - barometer height (only when the barometer is enabled and the limit is positive): the root-mean-square, over evaluated epochs where the barometric vertical channel publishes, of the difference between the change of its height since its first published epoch and the change of the reference height over the same span, so a constant offset between the two does not count;
  - ARS (only when ARS evaluation is on): the absolute mean of the ARS roll and pitch errors, the standard deviation of each, and the absolute yaw drift — the change of the ARS yaw error between the first and the last evaluated epoch divided by the elapsed minutes.
- The Python replay additionally accepts the directory or the `config.yaml` path, can write the fused solution to a file at a chosen rate, and can estimate GNSS delay (FP-04). Optional plot and Google Earth export exist on the Python replay; they are outside this product's requirements (see Non-goals).
- The Python YAML runner reads a different YAML that names *arbitrary* CSV files and column mappings. Time unit is one of s / ms / µs. Gyro is deg/s or rad/s. Accelerometer is m/s² or g. Pressure is Pa, hPa, mbar, or kPa. Magnetometer is µT, gauss, mGauss, or nT; every listed unit is converted onto microtesla. GNSS position is geodetic degrees, radians, or ECEF. It merges streams by timestamp (IMU begins each epoch; the latest GNSS/baro/mag sample at or before t is attached) and writes a solution CSV with one row per epoch: mode, lat/lon/h, NED position and velocity, roll/pitch/yaw, arbitrated heights. Mapped streams in any of the listed units yield the same navigation solution as the same data in SI units.

**Boundary / error behavior:**

- Missing IMU stream or missing reference trajectory: the run does not succeed.
- `aiding: gnss` without a GNSS stream: the run does not succeed.
- Unknown `config.yaml` keys and unknown `aiding` values fail the run with a non-zero exit and identify the offender. Keys that belong to other tools in the same directory are accepted when they are on the shared known-schema list and ignored by that harness; a typo *inside* a section the harness owns remains an error. The two foreign sections named above are on that list.
- Comment lines and malformed CSV lines are skipped; mixed sample rates are allowed.
