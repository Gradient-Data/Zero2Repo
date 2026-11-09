# Interface Contract

The Python package is imported as `velunex`. Its submodules are importable as `velunex.config`, `velunex.flatsys`, `velunex.optimal`, and `velunex.phaseplot`. Public functions return Python objects; numeric arrays support NumPy indexing, shape inspection, and conversion.

Python exceptions are raised to the caller. Notifications use Python warnings with category `UserWarning`. Plotting results expose Matplotlib figures, axes, and artists, including with the `Agg` backend.

Call forms below use square brackets to mark optional arguments and `...` for caller-supplied values. Array dimensions are described using signal counts and sample counts.

## `velunex.StateSpace`

A `StateSpace` model exposes numeric matrices `A`, `B`, `C`, and `D`, with shapes `(nstates, nstates)`, `(nstates, ninputs)`, `(noutputs, nstates)`, and `(noutputs, ninputs)`. `nstates`, `ninputs`, and `noutputs` are integer counts. `name` is a string; `state_labels`, `input_labels`, and `output_labels` are lists of signal-name strings.

`dt` is a timebase: `None` denotes unspecified time, `0` continuous time, `True` discrete time with unspecified period, and a positive number a discrete sampling period.

`dynamics(t, x, u)` and `output(t, x, u)` accept numeric time and state/input vectors and return one-dimensional numeric arrays of state updates and outputs, respectively.

Calling a model as `model(x, squeeze=False)` accepts complex evaluation points and returns a complex array indexed by output, input, and point. A SISO call with a scalar point and omitted `squeeze` returns a scalar; a SISO vector call returns a vector.

Channel subscription is `model[output_spec, input_spec]`; each selector may be an integer, name, list of names, or slice. It returns a `StateSpace` with selected channel labels. Selection failure raises `ValueError`.

Model addition (`+`) returns a model; incompatible timebase addition raises `ValueError`. Unary negation (`-`) returns a model.

## `velunex.TransferFunction`

A `TransferFunction` exposes `num[output][input]` and `den[output][input]`, each a one-dimensional numeric sequence of polynomial coefficients in descending powers. `ninputs` and `noutputs` are integer counts; `name` is a string; `input_labels` and `output_labels` are lists of signal names.

`dt` uses the timebase representation described for `StateSpace`. Calling a model with complex points as `model(x, squeeze=False)` returns a complex array indexed by output, input, point. With omitted `squeeze`, a SISO scalar call returns a scalar and a SISO vector call returns a vector.

Subscription `model[output_spec, input_spec]` accepts integer, name, list-of-names, or slice selectors and returns a transfer-function model with channel labels. Selection failure raises `ValueError`.

The operators `+`, `-`, `*`, `/`, `**`, and unary `-` accept model operands and numeric scalar operands in scalar transfer expressions; the exponent is an integer. Results are transfer-function models. Incompatible timebase addition raises `ValueError`.

`poles()` and `zeros()` return one-dimensional complex root arrays.

## `velunex.ss`

Call `ss(A, B, C, D[, dt], **kwargs)` with numeric scalar or array-like matrices, or `ss(sys)` with a linear model. It returns a `StateSpace`.

Keyword arguments are `dt`, `name`, `inputs`, `outputs`, and `states`. Signal descriptions are integer counts, a single string, or lists of strings; `name` is a string. Empty array-like matrices represent absent state dimensions.

Rejected model or signal descriptions raise `ValueError`.

## `velunex.tf`

Call `tf(num, den[, dt], **kwargs)` with scalar-channel coefficient vectors or nested coefficient vectors indexed by output and input. `tf('s')` supplies the continuous transfer-variable model. The return is a `TransferFunction`.

Keyword arguments are `dt`, `name`, `inputs`, and `outputs`. Signal descriptions accept counts, a single name, or lists of names.

Rejected descriptions raise `ValueError`.

## `velunex.zpk`

`zpk(zeros, poles, gain)` accepts root sequences and a scalar gain, and returns a `TransferFunction`.

## `velunex.rss`

`rss(states, outputs, inputs[, strictly_proper=...])` accepts integer signal counts and a boolean `strictly_proper`. It returns a `StateSpace`.

A rejected dimension raises `ValueError` or `TypeError`.

## `velunex.drss`

`drss(states, outputs, inputs[, strictly_proper=...])` accepts integer signal counts and a boolean `strictly_proper`. It returns a `StateSpace`.

A rejected dimension raises `ValueError` or `TypeError`.

## `velunex.frd`

`frd(frdata, omega, **kwargs)` accepts complex samples as a vector or an array indexed by output, input, frequency, together with a real frequency vector. `frd(sys, omega)` accepts a linear model and frequency vector. Both return `FrequencyResponseData`.

Keyword arguments are `smooth` and `squeeze` (booleans), `name` (string), and `inputs` and `outputs` (signal-name lists). Rejected sample dimensions raise `TypeError`; rejected interpolation construction raises `ValueError`.

## `velunex.FrequencyResponseData`

`FrequencyResponseData` exposes `omega`, a one-dimensional real angular-frequency array, and `frdata`, a complex array indexed by output, input, frequency. `ninputs` and `noutputs` are integer channel counts. `input_labels` and `output_labels` are signal-name lists.

`magnitude` and `phase` carry absolute gain and phase in radians. With `squeeze=False`, both have axes output, input, frequency.

`eval(omega, squeeze=False)` accepts a real frequency vector and returns a complex array indexed by output, input, requested frequency. Evaluation refusal raises `ValueError`.

Subscription `model[output_name, input_name]` returns a frequency-data model with output, input, frequency axes.

## `velunex.nlsys`

`nlsys(updfcn[, outfcn], **kwargs)` returns a `NonlinearIOSystem`. The callbacks have the form `updfcn(t, x, u, params)` and `outfcn(t, x, u, params)`, returning state-update and output vectors. `updfcn` and `outfcn` can be `None`.

Keywords are `states`, `inputs`, `outputs` (integer counts, single names, or name lists), `name` (string), `dt` (timebase), and `params` (mapping). Rejected model descriptions raise `ValueError`.

## `velunex.NonlinearIOSystem`

A `NonlinearIOSystem` exposes integer `nstates`, `ninputs`, `noutputs`; string `name`; and signal-name lists `state_labels`, `input_labels`, `output_labels`. Its readable and assignable `dt` uses the timebase representation described for `StateSpace`.

`dynamics(t, x, u[, params=...])` and `output(t, x, u[, params=...])` accept time, state and input vectors, and an optional parameter mapping. They return one-dimensional numeric state-update and output arrays, including empty arrays for empty signal dimensions.

A static model is callable as `model(u, squeeze=False)` and returns its output vector. Unsupported input-only evaluation raises `TypeError`. Unary negation (`-`) returns an input/output model.

## `velunex.flatsys.BasisFamily`

`BasisFamily(N)` constructs a trajectory basis. `N` is an integer coefficient count.

A basis is callable as `basis(i, t[, var=...])`. `eval_deriv(i, k, t[, var=...])` accepts an element index, derivative order, a time vector, and optional variable index; its numeric result is indexed by time. `eval(coeffs, tlist[, var=...])` accepts coefficients and a time vector and returns values indexed by time.

`var_ncoefs(var)` returns the integer coefficient count for a variable.

The base constructor is also callable as `super().__init__(N)`. Subclassing `BasisFamily` supports overriding `eval_deriv(self, i, k, t, var=None)` for the inherited callable and coefficient-evaluation interfaces.

## `velunex.flatsys.PolyFamily`

`PolyFamily(N[, T=...])` constructs a trajectory basis. `N` is an integer coefficient count. `T` is a numeric time scale.

A basis is callable as `basis(i, t[, var=...])`. `eval_deriv(i, k, t[, var=...])` accepts an element index, derivative order, a time vector, and optional variable index; its numeric result is indexed by time. `eval(coeffs, tlist[, var=...])` accepts coefficients and a time vector and returns values indexed by time.

`var_ncoefs(var)` returns the integer coefficient count for a variable.

## `velunex.flatsys.BezierFamily`

`BezierFamily(N[, T=...])` constructs a trajectory basis. `N` is an integer coefficient count. `T` is a numeric time scale.

A basis is callable as `basis(i, t[, var=...])`. `eval_deriv(i, k, t[, var=...])` accepts an element index, derivative order, a time vector, and optional variable index; its numeric result is indexed by time. `eval(coeffs, tlist[, var=...])` accepts coefficients and a time vector and returns values indexed by time.

## `velunex.flatsys.BSplineFamily`

`BSplineFamily(breakpoints, degree[, smoothness=..., vars=...])` constructs a trajectory basis. `breakpoints` is a time sequence; `degree` and `smoothness` are integers or per-variable integer sequences; `vars` is a variable count.

A basis is callable as `basis(i, t[, var=...])`. `eval_deriv(i, k, t[, var=...])` accepts an element index, derivative order, a time vector, and optional variable index; its numeric result is indexed by time. `eval(coeffs, tlist[, var=...])` accepts coefficients and a time vector and returns values indexed by time. For multiple variables without a selected `var`, concatenated per-variable coefficient vectors yield an array indexed by variable, time.

`var_ncoefs(var)` returns the integer coefficient count for a variable.

Rejected descriptions raise `ValueError` or `TypeError`; unsupported descriptions raise `NotImplementedError`.

## `velunex.series`

`series(*sys)` accepts positional models and numeric scalar or matrix gains and returns the connected model, exposed through the linear-model or input/output-model interface.

Dimension refusal raises `ValueError`. Incompatible sampled-frequency connection raises `NotImplementedError`.

## `velunex.parallel`

`parallel(*sys)` accepts positional models and numeric scalar or matrix gains and returns the connected model, exposed through the linear-model or input/output-model interface.

Dimension refusal raises `ValueError`. Incompatible sampled-frequency connection raises `NotImplementedError`.

## `velunex.append`

`append(*sys)` accepts positional linear models and returns a model exposed through the linear-model interface.

## `velunex.feedback`

`feedback(sys1[, sys2][, sign=...])` accepts forward and feedback models, with numeric gains accepted as operands. `sign` uses `-1` for negative feedback and `1` for positive feedback. It returns the connected model.

Connection refusal raises `ValueError`; unsupported model or sampled-frequency connection raises `NotImplementedError`.

## `velunex.interconnect`

`interconnect(syslist, **kwargs)` accepts a list of input/output models. Keywords are `connections`, `inplist`, `outlist`, `check_unused`, `ignore_inputs`, and `ignore_outputs`. The result is an input/output model; a linear network is also a `StateSpace`.

A named signal reference is `<system-name>.<signal-name>`. A weighted source reference is `(system_name, signal_name, gain)`. Each `connections` entry is a list containing a destination input followed by source outputs. `connections=None` selects automatic name routing; `connections=False` denotes no internal connections. Each `inplist` element is an input reference or a list of input references; `outlist` is a list of output references. Unqualified signal-name strings are accepted in `inplist`. `ignore_inputs` and `ignore_outputs` are lists of named signal references. `check_unused` is boolean.

Rejected references or connections raise `ValueError`. Unused-signal diagnostics are Python `UserWarning` records labeled `Unused input(s) in InterconnectedSystem: ` or `Unused output(s) in InterconnectedSystem: `. After the label, entries are separated by `; `. An input entry ends with `=<system-name>.<signal-name>`; an output entry ends with ` : <system-name>.<signal-name>`.

## `velunex.summing_junction`

`summing_junction(inputs=..., output=...[, dimension=...])` accepts a list of input-name strings, an output-name string, and an optional integer vector dimension. An input name may carry a leading `-` sign. It returns a static state-space model whose `output(t, [], u)` returns an output vector. Vector input groups occupy consecutive segments of `u` in the supplied name order.

## `velunex.combine_tf`

`combine_tf(tf_array)` accepts a nested array of single-channel transfer-function models indexed by output and input. It returns a transfer-function matrix model.

## `velunex.split_tf`

`split_tf(transfer_function)` returns a two-dimensional array of single-channel transfer-function models, indexed by output and input. The array exposes `shape` and supports two-index subscription.

## `velunex.ss2tf`

`ss2tf(sys)` accepts a linear model and returns a `TransferFunction` with a `dt` timebase.

## `velunex.tf2ss`

`tf2ss(sys)` accepts a linear model and returns a `StateSpace` with a `dt` timebase.

Rejected conversion raises `ValueError`.

## `velunex.similarity_transform`

`similarity_transform(xsys, T[, timescale=..., inverse=...])` accepts a state-space model, numeric coordinate matrix, optional numeric time scale, and optional boolean direction selector. It returns a `StateSpace`.

## `velunex.canonical_form`

`canonical_form(xsys[, form=...])` accepts a state-space model and returns `(model, T)`: a `StateSpace` and a real two-dimensional state-coordinate map. `form` is a string naming the coordinate form: `reachable`, `observable`, or `modal`.

Unsupported conversion raises `VelunexNotImplemented`; rejected conversion raises `ValueError`.

## `velunex.reachable_form`

`reachable_form(xsys)` accepts a state-space model and returns `(model, T)`: a `StateSpace` and a real two-dimensional state-coordinate map.

Unsupported conversion raises `VelunexNotImplemented`; rejected conversion raises `ValueError`.

## `velunex.observable_form`

`observable_form(xsys)` accepts a state-space model and returns `(model, T)`: a `StateSpace` and a real two-dimensional state-coordinate map.

Unsupported conversion raises `VelunexNotImplemented`; rejected conversion raises `ValueError`.

## `velunex.modal_form`

`modal_form(xsys)` accepts a state-space model and returns `(model, T)`: a `StateSpace` and a real two-dimensional state-coordinate map.

## `velunex.sample_system`

`sample_system(sysc, Ts[, method=..., alpha=..., prewarp_frequency=...])` accepts a linear model, numeric sampling period, optional method-name string, numeric weight, and angular prewarp frequency. It returns a `StateSpace` or `TransferFunction` with numeric `dt`.

Method spellings are `zoh` (zero-order hold), `foh` (first-order hold), `gbt` (generalized bilinear), `bilinear`, `euler` (forward difference), `backward_diff` (backward difference), `impulse` (impulse-invariant), and `matched` (matched poles and zeros).

Rejected sampling requests raise `ValueError`; unsupported transfer-matrix sampling raises `VelunexMIMONotImplemented`. A prewarp notification uses `UserWarning`.

## `velunex.pade`

`pade(T[, n=..., numdeg=...])` accepts a numeric delay and integer polynomial-order arguments. It returns `(num, den)`, two real coefficient sequences in descending powers. Rejected arguments raise `ValueError`.

## `velunex.ctrb`

`ctrb(A, B[, t=...])` accepts numeric matrices and an optional integer horizon. It returns a two-dimensional real array with axes `(state, returned horizon length times input)`. Dimension refusal raises `VelunexDimension`.

## `velunex.obsv`

`obsv(A, C[, t=...])` accepts numeric matrices and an optional integer horizon. It returns a two-dimensional real array with axes `(returned horizon length times output, state)`. Dimension refusal raises `VelunexDimension`.

## `velunex.gram`

`gram(sys, type)` accepts a state-space model and a string selector: `c`, `o`, `cf`, or `of`, identifying controllability Gramian, observability Gramian, controllability factor, or observability factor. It returns a real square array indexed by state. Rejected systems raise `ValueError`.

## `velunex.lyap`

`lyap(A, Q[, C, E])` accepts numeric matrices, with `C` and `E` also accepted as keywords or `None`. It returns a real solution matrix, square for a Lyapunov equation and indexed by left and right dimensions for a Sylvester equation.

Dimension refusal raises `VelunexDimension`; argument refusal raises `VelunexArgument`.

## `velunex.dlyap`

`dlyap(A, Q[, C, E])` accepts numeric matrices, with `C` and `E` also accepted as keywords or `None`. It returns a real solution matrix, square for a Lyapunov equation and indexed by left and right dimensions for a Sylvester equation.

Dimension refusal raises `VelunexDimension`; argument refusal raises `VelunexArgument`.

## `velunex.care`

`care(A, B, Q[, R, S, E], stabilizing=..., method=...)` accepts numeric matrices; optional `S` and `E` can be passed by keyword. `stabilizing` is boolean and `method` is an optional string selector, including `scipy`. Both keyword selectors may be omitted.

The return is `(X, L, G)`: a real solution matrix `(state, state)`, a complex eigenvalue vector `(state,)`, and a real feedback gain `(input, state)`.

Dimension refusal raises `VelunexDimension`; symmetry or argument refusal raises `VelunexArgument`; an unsolved equation can raise `numpy.linalg.LinAlgError`.

## `velunex.dare`

`dare(A, B, Q, R[, S, E], stabilizing=..., method=...)` accepts numeric matrices; optional `S` and `E` can be passed by keyword. `stabilizing` is boolean and `method` is an optional string selector, including `scipy`. Both keyword selectors may be omitted.

The return is `(X, L, G)`: a real solution matrix `(state, state)`, a complex eigenvalue vector `(state,)`, and a real feedback gain `(input, state)`.

Dimension refusal raises `VelunexDimension`; symmetry or argument refusal raises `VelunexArgument`; an unsolved equation can raise `numpy.linalg.LinAlgError`.

## `velunex.VelunexDimension`

`VelunexDimension` is an exception class derived from `ValueError`, signaling dimension refusal.

## `velunex.VelunexArgument`

`VelunexArgument` is an exception class derived from `TypeError`, signaling argument refusal.

## `velunex.VelunexMIMONotImplemented`

`VelunexMIMONotImplemented` is an exception class derived from `NotImplementedError`, signaling unsupported multiple-channel operation.

## `velunex.VelunexNotImplemented`

`VelunexNotImplemented` is an exception class derived from `NotImplementedError`, signaling unsupported operation.

## `velunex.TimeResponseData`

`TimeResponseData(time, outputs, inputs=...)` accepts a one-dimensional time vector and numeric input/output histories. Histories use signal, time axes, with a vector also accepted for a single signal.

Returned time-response objects expose `time` as a vector and `states`, `inputs`, `outputs` as numeric arrays. With `squeeze=False`, forced, initial-condition, and input/output simulation histories use signal, time axes; step and impulse histories use signal, excitation-trace, time axes, including a singleton excitation axis for a single or selected input. Combined response histories use signal, trace, time axes. With omitted squeeze, SISO outputs can be a time vector.

`input_labels`, `output_labels`, and `trace_labels` are lists of strings. `sysname` is the originating system's name string. `success` is boolean; an unsuccessful response carries a nonempty reason string in `message`.

## `velunex.forced_response`

`forced_response(sysdata[, timepts, inputs, initial_state], **kwargs)` accepts a linear model, an optional time vector, an input history, and an initial-state vector or scalar. `timepts` can be `None`. Inputs may be a numeric scalar, SISO time vector, or an array indexed by input, time.

The keywords `X0` (initial state), `squeeze`, and `interpolate` are accepted; the latter two are booleans. `interpolate=True` selects the system-period output grid; `False` selects the supplied output grid. The return is `TimeResponseData`. Rejected dimensions or time grids raise `ValueError`.

## `velunex.step_response`

`step_response(sysdata[, timepts], input=..., output=..., squeeze=...)` accepts a linear model or a list of linear models and an optional time vector. `input` and `output` are optional integer channel selectors. `squeeze` is an optional boolean. The return is `TimeResponseData`, or a list of responses for a list of models.

## `velunex.impulse_response`

`impulse_response(sysdata[, timepts], input=..., output=..., squeeze=...)` accepts a linear model or a list of linear models and an optional time vector. `input` and `output` are optional integer channel selectors. `squeeze` is an optional boolean. The return is `TimeResponseData`, or a list of responses for a list of models.

An impulse notification is emitted as `UserWarning`.

## `velunex.initial_response`

`initial_response(sysdata[, timepts], X0=..., squeeze=...)` accepts a linear model or a list of linear models and an optional time vector. `X0` accepts a scalar or state vector. `squeeze` is an optional boolean. The return is `TimeResponseData`, or a list of responses for a list of models.

## `velunex.input_output_response`

`input_output_response(sys, timepts[, inputs, initial_state], **kwargs)` accepts an input/output model, input sample times, a numeric input history, and scalar or vector initial state. Inputs can be a scalar, a SISO time vector, or an array indexed by input, time.

Keywords are `X0` or `initial_state` for initial state, `params` for a parameter mapping, `t_eval` for a separate evaluation-time vector, `squeeze` and `ignore_errors` for boolean options, and `solve_ivp_kwargs` for a mapping. The latter accepts numeric `rtol` and `atol` controls. The result is `TimeResponseData`.

Simulation failure is represented by `RuntimeError`, or by an unsuccessful response when `ignore_errors=True` is requested. That response has `success=False`, a nonempty string `message`, a `time` vector, and a `states` array. Rejected time grids raise `ValueError`. An unresolved connection loop raises `RuntimeError`.

## `velunex.combine_time_responses`

`combine_time_responses(response_list[, trace_labels=...])` accepts a list of time responses and an optional list of trace-name strings. It returns `TimeResponseData` with signal, trace, time arrays for `inputs`, `states`, and `outputs`, a `time` vector, and `input_labels`, `output_labels`, `trace_labels`, `sysname` metadata.

Combination refusal raises `ValueError`.

## `velunex.step_info`

`step_info(sysdata[, timepts], final_output=..., SettlingTimeThreshold=..., RiseTimeLimits=...)` accepts a model or sampled step-response data. Sampled MIMO data use output, input, time axes. `timepts` is a time vector. The optional `final_output` is a scalar or output-by-input array; `SettlingTimeThreshold` is numeric and `RiseTimeLimits` is a pair of numbers.

The return is a dictionary for SISO or a nested list indexed by output and input for MIMO. Each dictionary contains numeric fields: `RiseTime` (rise duration), `SettlingTime` (settling time), `SettlingMin` and `SettlingMax` (post-rise extrema), `Overshoot` and `Undershoot` (percentages), `Peak` (absolute peak), `PeakTime` (peak time), and `SteadyStateValue` (final output).

## `velunex.VelunexPlot`

Plot functions return a `VelunexPlot` exposing `lines`, `axes`, and `figure`. Except for the phase-plane and describing-function layouts specified at their entries, `lines` is a two-dimensional object array whose cells contain lists of Matplotlib line artists; it supports `shape`, `flat`, and indexing. `axes` is a two-dimensional array of Matplotlib axes; `figure` is a Matplotlib figure.

A line exposes `get_xdata()` and `get_ydata()` coordinate arrays, `get_label()` for its string identity, and `get_transform()` for its coordinate transform. Coordinates can be masked arrays. Axes expose `get_children()`, `get_xlabel()`, `get_ylabel()`, `get_title()`, `get_xlim()`, `get_ylim()`, `lines`, `texts`, `figure`, and `transData`. Figure text artists are available through `figure.texts`, with `get_text()` and `get_position()` accessors.

Axes supplied through `ax` are Matplotlib axes or the axes array returned by a plot. The figure supports `canvas.draw()` and public `canvas.callbacks.process` event delivery. A left-button `button_release_event` carries canvas coordinates and the corresponding `xdata`, `ydata`, and `inaxes`.

## `velunex.time_response_plot`

`time_response_plot(data[, plot_inputs=..., overlay_traces=..., add_initial_zero=..., ax=...])` accepts a time response, boolean plot options, and optional Matplotlib axes. It returns `VelunexPlot`.

Each response line carries time in `get_xdata()` and the corresponding input or output signal in `get_ydata()`. `get_label()` identifies the plotted signal, trace, and system. The result's `lines` contains the lines for that call; for a single output-only response its line is at `lines[0, 0][0]`. With overlaid traces, the line list represents the trace sequence.

## `velunex.frequency_response`

`frequency_response(sysdata[, omega], omega_limits=..., omega_num=..., squeeze=...)` accepts a linear model, optional angular-frequency vector, optional pair of frequency limits, optional integer point count, and optional boolean squeeze option. It returns `FrequencyResponseData`.

Frequency-range notifications are `UserWarning` records.

## `velunex.bode_plot`

`bode_plot(data[, omega], dB=..., deg=..., Hz=..., label=...)` accepts a linear model, a list of models, or frequency-response data, plus an optional frequency vector. `dB`, `deg`, and `Hz` are boolean unit selectors. `label` accepts a list of strings. It returns `VelunexPlot`.

`lines[2*output, input][system]` is the magnitude line, and `lines[2*output+1, input][system]` is the phase line. The x coordinates carry frequency. Magnitude y coordinates are absolute gain or decibels; phase y coordinates are radians or degrees. Caller-supplied labels are available through `get_label()`.

Axis labels are `Magnitude` or `Magnitude [dB]`, `Phase [rad]` or `Phase [deg]`, and `Frequency [rad/s]` or `Frequency [Hz]`. Input-column titles have the form `From <input-name>`, and figure text for output rows has the form `To <output-name>`.

## `velunex.nichols_plot`

`nichols_plot(data[, omega], grid=..., label=...)` accepts a linear model, list of models, or frequency-response data, an optional frequency vector, a boolean grid option, and optional label strings. It returns `VelunexPlot`.

Flattened `lines` cells contain the system curves in model-list sequence. Line x coordinates carry phase in degrees and y coordinates carry magnitude in decibels. The axes are labeled `Phase [deg]` and `Magnitude [dB]`. Caller-supplied labels are returned by `get_label()`.

Unsupported channel dimensions raise `NotImplementedError`.

## `velunex.singular_values_response`

`singular_values_response(sysdata, omega)` accepts a linear model and angular-frequency vector. It returns `FrequencyResponseData` whose `omega` is a frequency vector and whose `frdata` has axes singular-value index, singleton input axis, frequency.

## `velunex.singular_values_plot`

`singular_values_plot(data, dB=..., Hz=...)` accepts singular-value response data and boolean magnitude/frequency unit selectors. It returns `VelunexPlot`. Flattened `lines` cells contain one curve per singular-value index, with frequency x coordinates and singular-value gain y coordinates in the selected units.

## `velunex.NyquistResponseData`

A `NyquistResponseData` exposes `contour`, a one-dimensional complex array of evaluation points; `response`, an aligned one-dimensional complex response array; and `count`, the integer encirclement count.

## `velunex.nyquist_response`

`nyquist_response(sysdata, omega)` accepts a single-channel linear model and an angular-frequency vector. It returns `NyquistResponseData`. An unreliable-count notification is a `UserWarning`.

## `velunex.nyquist_plot`

`nyquist_plot(data[, max_curve_magnitude=..., arrows=...])` accepts Nyquist response data, or frequency-response data. `max_curve_magnitude` is numeric and `arrows` accepts a boolean. It returns `VelunexPlot`.

`lines[system, 0]` contains the primary unscaled curve and `lines[system, 2]` the mirror unscaled curve. Each cell is a list of line artists with real-part x and imaginary-part y coordinates. Coordinates may use masked arrays.

Unsupported channel dimensions raise `NotImplementedError`.

## `velunex.gangof4_response`

`gangof4_response(P, C[, omega])` accepts plant and controller models and a frequency vector, also accepted as keyword `omega`. It returns `FrequencyResponseData`. The output/input channel positions carry complementary sensitivity at `[0, 0]`, plant-times-sensitivity at `[0, 1]`, controller-times-sensitivity at `[1, 0]`, and sensitivity at `[1, 1]`.

Unsupported channel dimensions raise `VelunexMIMONotImplemented`.

## `velunex.gangof4_plot`

`gangof4_plot(P, C, omega=..., dB=..., Hz=...)` accepts plant/controller models, a frequency vector, and boolean unit selectors. It returns `VelunexPlot` with `lines[output, input]` lists of gain-versus-frequency line artists. Channel positions have the same meanings as in `gangof4_response`.

## `velunex.dcgain`

`dcgain(sys)` accepts a linear model and returns its numeric zero-frequency gain: a scalar for SISO, or an array indexed by output and input.

## `velunex.bandwidth`

`bandwidth(sys[, dbdrop=...])` accepts a single-channel model and optional numeric decibel-drop parameter. It returns a scalar angular frequency. Unbounded bandwidth is represented by positive infinity; undefined bandwidth by NaN.

Argument refusal raises `ValueError`; channel-dimension refusal raises `TypeError`.

## `velunex.stability_margins`

`stability_margins(sysdata[, returnall=...])` accepts a rational model or frequency-data model and an optional boolean. It returns `(gm, pm, sm, wpc, wgc, wms)`: gain margin, phase margin in degrees, stability distance, phase-crossover frequency, gain-crossover frequency, and frequency of minimum distance. Frequencies are angular frequencies.

With `returnall=True`, the six entries are one-dimensional numeric arrays; otherwise each is scalar. Each frequency array is paired with its corresponding margin array. Missing limiting margins use positive infinity and missing limiting frequencies use NaN.

## `velunex.phase_crossover_frequencies`

`phase_crossover_frequencies(sys)` returns `(frequencies, gains)`: paired one-dimensional numeric arrays of angular frequencies and signed real-axis response gains. Unsupported channel dimensions raise `VelunexMIMONotImplemented`.

## `velunex.disk_margins`

`disk_margins(L, omega[, skew=..., returnall=...])` accepts a loop model, frequency vector, numeric skew, and boolean result-layout selector. It returns `(DM, DGM, DPM)`: disk margin, gain margin in decibels, and phase margin in degrees. With `returnall=True` each is a one-dimensional array aligned with frequency; otherwise each is a scalar limiting margin.

Rejected channel dimensions raise `ValueError`.

## `velunex.system_norm`

`system_norm(system, p)` accepts a linear model and norm selector `2` or `'inf'`. It returns a real scalar, including positive infinity for an infinite norm. Divergence notifications are `UserWarning` records. Unsupported norm requests raise `VelunexArgument`.

## `velunex.ispassive`

`ispassive(sys[, ofp_index=..., ifp_index=...])` accepts a linear model and optional numeric output-feedback and input-feedforward indices. It returns a boolean feasibility result.

## `velunex.get_input_ff_index`

`get_input_ff_index(sys)` accepts a linear model and returns a real scalar passivity index.

## `velunex.get_output_fb_index`

`get_output_fb_index(sys)` accepts a linear model and returns a real scalar passivity index.

## `velunex.solve_passivity_LMI`

`solve_passivity_LMI(sys, rho=..., nu=...)` accepts a linear model and output-feedback/input-feedforward index arguments, each numeric or `None`. Argument refusal raises `VelunexArgument`; channel-dimension refusal raises `VelunexDimension`.

## `velunex.poles`

`poles(sys)` accepts a linear model and returns a one-dimensional complex root array.

## `velunex.zeros`

`zeros(sys)` accepts a linear model and returns a one-dimensional complex root array.

## `velunex.damp`

`damp(sys, doprint=False)` returns `(wn, zeta, poles)`: one-dimensional arrays of natural angular frequencies, damping ratios, and complex poles. Entries across the arrays refer to the same pole. Undefined damping is represented by NaN.

## `velunex.PoleZeroData`

A `PoleZeroData` exposes one-dimensional complex `poles` and `zeros` arrays. Root-locus data also expose numeric `gains` with shape `(gain,)` and complex `loci` with shape `(gain, branch)`.

## `velunex.pole_zero_map`

`pole_zero_map(sysdata)` accepts a list of models and returns a list of `PoleZeroData` objects.

## `velunex.pole_zero_plot`

`pole_zero_plot(data, grid=..., label=...)` accepts a list of pole-zero data, a boolean grid option, and caller labels. It returns `VelunexPlot`. `lines[system, 0]` holds pole line artists and `lines[system, 1]` holds zero line artists. Their x and y coordinates are real and imaginary root components. Pole labels identify the supplied system labels.

## `velunex.root_locus_map`

`root_locus_map(sysdata[, gains=...])` accepts a single-channel model and optional numeric gain vector, including `gains=None`. It returns `PoleZeroData` with `gains`, `loci`, `poles`, and `zeros`. Unsupported channel dimensions raise `VelunexMIMONotImplemented`.

## `velunex.root_locus_plot`

`root_locus_plot(sysdata[, grid=..., interactive=..., xlim=..., ylim=...])` accepts a model or root-locus data, boolean options, and numeric pairs of axis limits. It returns `VelunexPlot`. `lines[system, 0]`, `lines[system, 1]`, and `lines[system, 2]` contain lists of pole, zero, and locus lines, respectively. Locus line coordinates are real and imaginary pole components indexed along the gain sequence. Unsupported channel dimensions raise `VelunexMIMONotImplemented`.

The interactive axes are `axes[0, 0]`. A left-button `button_release_event` is accepted through the figure canvas. A selected gain is carried once in the axes title as `gain = <number>`, with a signed decimal or scientific-notation number. Line artists labeled `_gain_point` carry selected pole coordinates.

## `velunex.sisotool`

`sisotool(sys[, initial_gain=..., dB=..., deg=..., Hz=..., margins_bode=..., xlim_rlocus=..., ylim_rlocus=...])` accepts a model, numeric initial gain, boolean display options, and pairs of root-locus axis limits.

The display is the current Matplotlib figure. Its axes are identified by titles `Bode magnitude`, `Bode phase`, `Root locus`, and `Step response`. Each response axes contains one response line whose `get_transform()` equals `ax.transData`; it exposes frequency/magnitude, frequency/phase, or time/output coordinates as appropriate. Axis-spanning reference artists have different transforms.

Selection uses a left-button `button_release_event` on the root-locus axes. The figure text carries one `gain = <number>` field with a signed decimal or scientific-notation number. Root-locus line artists labeled `_gain_point` carry selected poles. Unsupported dimensions raise `VelunexMIMONotImplemented`.

## `velunex.rootlocus_pid_designer`

`rootlocus_pid_designer(plant[, gain=..., input_signal=..., Kp0=..., Ki0=..., C_ff=..., deltaK=..., plot=...])` accepts a plant, string selectors, numeric nominal proportional/integral gains, a numeric or model feedforward term, numeric gain perturbation, and a boolean display option.

`gain` uses `'P'` or `'I'` for the selected controller term; `input_signal` uses `'r'` or `'d'` for reference or disturbance. The returned object is a `StateSpace` for the nominal closed loop.

The displayed design view is the current Matplotlib figure with the axes and curve carriers described for `sisotool`, including `Step response`, `Root locus`, and `_gain_point`.

## `velunex.OperatingPoint`

An `OperatingPoint` exposes `states`, `inputs`, and `outputs` as one-dimensional numeric vectors for a reported point. The `result` object exposes boolean `success`. Unsuccessful point results can instead have `states=None` and `inputs=None`; an explicitly requested candidate uses vectors with an unsuccessful `result.success`.

## `velunex.find_operating_point`

`find_operating_point(sys, initial_state, inputs[, outputs], **kwargs)` accepts an input/output model, state/input guess vectors, and an optional desired-output vector. Keywords `state_indices`, `input_indices`, `output_indices`, and `deriv_indices` accept index lists; `derivs` accepts a state-update vector. `return_result` is boolean and selects candidate-result access.

The return is an `OperatingPoint`.

## `velunex.linearize`

`linearize(sys, xeq, ueq[, t=..., params=...])` accepts an input/output model, state and input vectors, optional time, and optional parameter mapping. It returns a `StateSpace` with `A`, `B`, `C`, `D` matrices and `dt`.

## `velunex.phase_plane_plot`

`phase_plane_plot(sys, pointdata[, timedata=..., gridtype=..., gridspec=..., dir=..., ax=..., plot_streamlines=..., plot_vectorfield=..., plot_streamplot=..., plot_equilpoints=..., plot_separatrices=...])` accepts an input/output model and a region `[xmin, xmax, ymin, ymax]` or an array of point rows `(point, 2)`. `timedata` is a numeric trajectory duration. `ax` is a Matplotlib axes.

`gridtype` names `meshgrid`, `boxgrid`, or `circlegrid`, or is `None` for supplied points. `gridspec` is a pair of grid counts or a radius/count pair for circles. `dir` names `forward`, `reverse`, or `both`. The five `plot_streamlines`, `plot_vectorfield`, `plot_streamplot`, `plot_equilpoints`, and `plot_separatrices` options are booleans.

The return is `VelunexPlot`. `lines[0]` contains a list of trajectory/separatrix line artists. `lines[1]` is a Matplotlib Quiver or `None`; its `X` and `Y` arrays carry point positions and `U` and `V` carry vector components. `lines[2]` contains equilibrium line artists or `None`. Line x/y data are state coordinates. The supplied axes expose region limits through `get_xlim()` and `get_ylim()`.

Rejected state dimensions raise `ValueError`.

## `velunex.meshgrid`

`meshgrid(xvals, yvals)` accepts coordinate sequences and returns a numeric array of point rows with shape `(point, 2)`; each row contains x and y coordinates.

## `velunex.phaseplot.meshgrid`

`velunex.phaseplot.meshgrid` exposes `meshgrid(xvals, yvals)` with the point-array interface described at `velunex.meshgrid`.

## `velunex.boxgrid`

`boxgrid(xvals, yvals)` accepts coordinate sequences and returns a numeric array of point rows with shape `(point, 2)`; each row contains x and y coordinates.

## `velunex.phaseplot.boxgrid`

`velunex.phaseplot.boxgrid` exposes `boxgrid(xvals, yvals)` with the point-array interface described at `velunex.boxgrid`.

## `velunex.circlegrid`

`circlegrid(centers, radius, num)` accepts an array of center points, numeric radius, and integer point count and returns a numeric array of point rows with shape `(point, 2)`; each row contains x and y coordinates.

## `velunex.phaseplot.circlegrid`

`velunex.phaseplot.circlegrid` exposes `circlegrid(centers, radius, num)` with the point-array interface described at `velunex.circlegrid`.

## `velunex.equilpoints`

`equilpoints(sys, pointdata[, gridspec=..., ax=...])` accepts a model, region `[xmin, xmax, ymin, ymax]`, optional grid-count pair, and Matplotlib axes. It returns a list of Matplotlib line artists whose `get_xdata()` and `get_ydata()` arrays contain equilibrium coordinates.

## `velunex.phaseplot.equilpoints`

`velunex.phaseplot.equilpoints` exposes `equilpoints(sys, pointdata[, gridspec=..., ax=...])` with the line-list interface described at `velunex.equilpoints`.

## `velunex.separatrices`

`separatrices(sys, pointdata[, timedata=..., gridspec=..., ax=...])` accepts a model, region `[xmin, xmax, ymin, ymax]`, optional grid-count pair, and Matplotlib axes. `timedata` is a numeric duration. It returns a list of Matplotlib line artists whose `get_xdata()` and `get_ydata()` arrays contain separatrix state coordinates.

## `velunex.phaseplot.separatrices`

`velunex.phaseplot.separatrices` exposes `separatrices(sys, pointdata[, timedata=..., gridspec=..., ax=...])` with the line-list interface described at `velunex.separatrices`.

## `velunex.place`

`place(A, B, p)` accepts numeric system matrices and a requested complex pole vector. It returns a real gain array indexed by input, state. Rejected placement raises `ValueError`.

## `velunex.place_acker`

`place_acker(A, B, poles)` accepts numeric system matrices and a requested complex pole vector. It returns a real gain array indexed by input, state. Rejected placement raises `ValueError`.

## `velunex.place_varga`

`place_varga(A, B, p[, dtime=..., alpha=...])` accepts numeric system matrices and a requested complex pole vector. It returns a real gain array indexed by input, state. `dtime` is boolean; `alpha` is a numeric stability-region boundary.

## `velunex.lqr`

`lqr(A, B, Q, R[, N], integral_action=...)` or `lqr(sys, Q, R[, N])` accepts numeric matrices or a state-space model and numeric weights. The optional `integral_action` is a numeric state-selection matrix.

The return is `(K, S, E)`: real feedback gain `(input, state including integral state)`, real cost-to-go matrix indexed by the same state dimensions, and a corresponding complex eigenvalue vector.

Dimension refusal raises `VelunexDimension`. Argument refusal raises `VelunexArgument`.

## `velunex.dlqr`

`dlqr(A, B, Q, R[, N], integral_action=...)` or `dlqr(sys, Q, R[, N])` accepts numeric matrices or a state-space model and numeric weights. The optional `integral_action` is a numeric state-selection matrix.

The return is `(K, S, E)`: real feedback gain `(input, state including integral state)`, real cost-to-go matrix indexed by the same state dimensions, and a corresponding complex eigenvalue vector.

Dimension refusal raises `VelunexDimension`. Argument refusal raises `VelunexArgument`.

## `velunex.white_noise`

`white_noise(T, Q[, dt=...])` accepts a real sample-time vector, a numeric noise-intensity matrix, and optional timebase. It returns a numeric array indexed by noise channel, sample. Rejected grids or intensity dimensions raise `ValueError`.

## `velunex.correlation`

`correlation(T, X[, Y], squeeze=False)` accepts a real time vector and signal histories indexed by channel, time. `Y` may be `None`. It returns `(lags, correlation)`, where `lags` is a one-dimensional vector and the correlation array has axes second signal's channel, first signal's channel, lag. Rejected grids or dimensions raise `ValueError`.

## `velunex.lqe`

`lqe(A, G, C, QN, RN[, NN])` accepts numeric dynamics, disturbance influence, measurement and covariance matrices. `lqe(sys, QN, RN)` also accepts a state-space model.

The return is `(L, P, E)`: estimator gain `(state, measurement)`, covariance `(state, state)`, and complex pole vector `(state,)`.

Covariance refusal raises `VelunexDimension` or `VelunexArgument`; an unsupported covariance request raises `VelunexNotImplemented`.

## `velunex.dlqe`

`dlqe(A, G, C, QN, RN[, NN])` accepts numeric dynamics, disturbance influence, measurement and covariance matrices.

The return is `(L, P, E)`: estimator gain `(state, measurement)`, covariance `(state, state)`, and complex pole vector `(state,)`.

Covariance refusal raises `VelunexDimension` or `VelunexArgument`; an unsupported covariance request raises `VelunexNotImplemented`.

## `velunex.create_estimator_iosystem`

`create_estimator_iosystem(sys, QN, RN[, P0=..., G=..., C=..., control_indices=..., disturbance_indices=..., estimate_labels=..., covariance_labels=...])` accepts a state-space model, covariance matrices, optional initial covariance, numeric disturbance and measurement matrices, channel selections, and label lists. Channel selections are lists of indices or signal names.

It returns an input/output estimator model. Its input vector contains measurements followed by known controls. The state vector contains the state estimate followed by covariance entries in row-major order. Output is the state-estimate vector. `state_labels` contains estimate labels followed by covariance labels; `output_labels` contains estimate labels.

`dynamics(t, x, u, params=...)` accepts a `params` mapping with boolean `correct`. The returned derivative or next-state vector uses the same state-estimate/covariance layout. Simulated `states` and `outputs` use these rows with time as their last axis.

Unsupported construction raises `NotImplementedError`. Rejected measurement selection raises `ValueError`; dimension refusal raises `VelunexDimension`.

## `velunex.create_statefbk_iosystem`

`create_statefbk_iosystem(sys, gain[, feedfwd_gain=..., feedfwd_pattern=..., integral_action=..., estimator=..., gainsched_indices=..., gainsched_method=..., control_indices=..., state_indices=...])` returns `(controller, closed_loop)`, both input/output models.

`gain` accepts a numeric feedback matrix, a schedule tuple `(gains, points)` containing gain matrices and operating-point coordinates, or an input/output controller model. `feedfwd_gain` is numeric; `integral_action` is a numeric matrix; `estimator` is an input/output model. `control_indices`, `state_indices`, and `gainsched_indices` accept lists of indices or signal names. `feedfwd_pattern` spells trajectory tracking as `trajgen` and the reference-gain form as `refgain`; `gainsched_method` spells the interpolation choices as `nearest`, `linear`, and `cubic`.

The trajectory-form controller input vector contains desired states, desired inputs, then measured or estimated states. The reference-gain form contains references followed by measured or estimated states. Controller `output(t, x, u)` is an actuation vector; `dynamics(t, x, u)` carries controller state updates, including integral states.

Closed-loop external inputs contain desired states, desired inputs, then unused plant input channels for trajectory form; reference form exposes references. Closed-loop outputs contain plant outputs followed by applied actuation inputs. Simulation exposes these through `outputs` with channel, time axes when `squeeze=False`.

Rejected construction raises `VelunexArgument` or `ValueError`.

## `velunex.h2syn`

`h2syn(P, nmeas, ncon)` accepts a generalized state-space plant and integer measurement and actuation channel counts. It returns a controller `StateSpace`, with input dimension `nmeas` and output dimension `ncon`.

The last `nmeas` output channels are measurements and the last `ncon` input channels are actuation; preceding channels are performance outputs and disturbances.

## `velunex.hinfsyn`

`hinfsyn(P, nmeas, ncon)` accepts a generalized state-space plant and integer channel counts. It returns a four-element tuple: controller `StateSpace`, closed-loop `StateSpace`, scalar achieved gain, and condition estimates.

The last `nmeas` output channels are measurements and the last `ncon` input channels are actuation; preceding channels are performance outputs and disturbances.

## `velunex.augw`

`augw(g[, w1, w2, w3])` accepts a plant and optional weight models or `None`. It returns a generalized `StateSpace` with inputs ordered as reference channels then actuation channels. Its outputs are the supplied weighted error, weighted actuation, and weighted plant-output groups, followed by unweighted error channels.

Rejected weighting requests raise `ValueError`.

## `velunex.mixsyn`

`mixsyn(g[, w1, w2, w3])` accepts a plant and optional weight models or `None`. It returns `(controller, closed_loop, info)`. The first two entries are `StateSpace` models; `info` is a pair containing scalar achieved gain and condition estimates. Closed-loop output groups are supplied weighted error, weighted actuation, and weighted plant output.

Rejected weighting requests raise `ValueError`.

## `velunex.minimal_realization`

`minimal_realization(sys[, tol=..., verbose=...])` accepts a linear model, optional numeric tolerance, and boolean verbosity selector. It returns a linear model exposing `nstates` for state space or `den[output][input]` coefficient vectors for transfer functions, and the corresponding complex-evaluation interface.

## `velunex.model_reduction`

`model_reduction(sys[, elim_states], method=..., elim_inputs=..., elim_outputs=..., keep_states=..., keep_inputs=..., keep_outputs=...)` accepts a state-space model, optional index lists selecting eliminated or retained signals, and optional string `method`. Method spellings are `truncate` and `matchdc`.

The return is a `StateSpace` with integer `nstates`, `ninputs`, `noutputs` and the complex-evaluation interface. Rejected reduction raises `ValueError`; unsupported reduction raises `NotImplementedError`.

## `velunex.hankel_singular_values`

`hankel_singular_values(sys)` accepts a state-space model and returns a one-dimensional numeric array of Hankel singular values.

## `velunex.balanced_reduction`

`balanced_reduction(sys, orders[, method=...])` accepts a state-space model, an integer order or list of integer orders, and an optional string method selector `truncate` or `matchdc`. It returns a `StateSpace` for an integer order or a list of `StateSpace` models corresponding to the order list.

## `velunex.eigensys_realization`

`eigensys_realization(arg, r[, dt=...])` accepts a numeric impulse-data array with output, input, time axes, an integer realization order, and optional discrete timebase. It returns `(model, singular_values)`: a `StateSpace` exposing `A`, `B`, `C`, `D`, `nstates`, `dt`, and a one-dimensional singular-value array.

Rejected observations raise `ValueError`.

## `velunex.markov`

`markov(Y, U[, m], dt=..., truncate=...)` accepts output and input histories indexed by signal, time, with SISO vectors also supported. `markov(response[, m])` accepts a `TimeResponseData` record. `m` is an optional integer coefficient count; `dt` an optional numeric period; `truncate` an optional boolean.

The return is a numeric array with axes output, input, coefficient, or a one-dimensional coefficient vector for SISO records. Dimension refusal raises `VelunexDimension`. An underdetermination notification is a `UserWarning`.

## `velunex.saturation_nonlinearity`

`saturation_nonlinearity([ub, lb])` constructs a callable scalar nonlinearity from numeric parameters. A call `model(x)` accepts a numeric scalar and returns a real scalar. Constructor parameters can also be supplied by their keyword names.

## `velunex.relay_hysteresis_nonlinearity`

`relay_hysteresis_nonlinearity(b, c)` constructs a callable scalar nonlinearity from numeric parameters. A call `model(x)` accepts a numeric scalar and returns a real scalar. Constructor parameters can also be supplied by their keyword names.

## `velunex.friction_backlash_nonlinearity`

`friction_backlash_nonlinearity(b)` constructs a callable scalar nonlinearity from numeric parameters. A call `model(x)` accepts a numeric scalar and returns a real scalar. Constructor parameters can also be supplied by their keyword names.

## `velunex.describing_function`

`describing_function(F, A)` accepts a scalar callable and an amplitude vector. It returns a complex numeric array aligned with the amplitudes. Undefined gains are represented by NaN. Amplitude refusal raises `ValueError`.

## `velunex.DescribingFunctionResponse`

A `DescribingFunctionResponse` exposes `intersections` as a sequence of `(amplitude, angular_frequency)` pairs and `positions` as the corresponding complex-plane position sequence. `N_vals` is a complex array of negative reciprocal describing gains. `response` is a Nyquist response object exposing complex `contour` and `response` arrays.

## `velunex.describing_function_response`

`describing_function_response(H, F, A, omega)` accepts a linear model, scalar nonlinearity callable, amplitude vector, and angular-frequency vector. It returns `DescribingFunctionResponse`.

## `velunex.describing_function_plot`

`describing_function_plot(response[, max_curve_magnitude=..., arrows=...])` accepts describing-function response data, a numeric curve-display bound, and a boolean arrow selector. It returns `VelunexPlot` with a one-dimensional object array `lines` whose cells contain line-artist lists. `lines[0][0]` is the primary linear curve and `lines[1][0]` the nonlinear curve; both expose real-part x and imaginary-part y coordinates. Intersection annotations are text artists in `axes[0, 0].texts`; `get_position()` returns their complex-plane coordinate pairs.

## `velunex.flatsys.FlatSystem`

`FlatSystem(forward, reverse, outfcn=..., states=..., inputs=..., outputs=..., params=...)` accepts mapping callbacks, an optional output callback, signal counts, and a parameter mapping. It returns a flat input/output model.

The forward callback and model method are `forward(x, u, params)` and return a list of one-dimensional derivative arrays, one per flat output. The reverse callback and model method are `reverse(zflag, params)` and return `(x, u)`, a state vector and input vector. `params` accepts a mapping or `None`. The output callback is `outfcn(t, x, u, params)` and returns an output vector.

## `velunex.flatsys.LinearFlatSystem`

`LinearFlatSystem(linsys)` accepts a state-space model and returns a flat model. Its `forward(x, u, params)` and `reverse(zflag, params)` methods have the derivative-list and state/input-vector forms described for `FlatSystem`.

Unsupported conversion raises `VelunexNotImplemented`; rejected conversion raises `ValueError`.

## `velunex.flatsys.flatsys`

`flatsys(forward, reverse, outfcn=..., states=..., inputs=..., outputs=..., params=...)` accepts flat mapping callbacks and the model-description keywords described for `FlatSystem`. `flatsys(linsys)` accepts a linear state-space model. It returns a flat model with `forward` and `reverse` methods.

Unsupported linear conversion raises `VelunexNotImplemented`; rejected conversion raises `ValueError`.

## `velunex.flatsys.SystemTrajectory`

A `SystemTrajectory` exposes `eval(tlist)`, returning `(states, inputs)`. For a supplied time vector, both results are numeric two-dimensional arrays, with axes state/input signal, time.

`basis` is a trajectory basis exposing `var_ncoefs(var)` and `eval_deriv(i, k, t, var=...)`. `coeffs` is a list of coefficient vectors, one per flat output.

An optimization trajectory exposes boolean `success` and numeric `cost`. `response(timepts, squeeze=False)` returns a `TimeResponseData` with `time`, `states`, `inputs`, and `outputs`, using signal, time arrays.

## `velunex.flatsys.point_to_point`

`point_to_point(sys, timepts, initial_state, initial_input, final_state, final_input[, basis=..., params=..., integral_cost=..., trajectory_constraints=..., minimize_options=...])` accepts a flat model, time vector, endpoint state/input vectors, optional basis, and parameter mapping. `integral_cost(x, u)` is a scalar-valued callable.

`trajectory_constraints` is a list of tuples: `(LinearConstraint, A, lb, ub)` or `(NonlinearConstraint, fun, lb, ub)`. The type markers are `scipy.optimize.LinearConstraint` and `scipy.optimize.NonlinearConstraint`. Numeric linear rows address the concatenated state/input vector; `fun(x, u)` returns constraint values; `lb` and `ub` are numeric bounds. `minimize_options` is a mapping accepting numeric `ftol` and integer `maxiter`.

The return is `SystemTrajectory`. Rejected bases raise `ValueError`. Planning and optimization notifications use `UserWarning`.

## `velunex.flatsys.solve_flat_optimal`

`solve_flat_optimal(sys, timepts, initial_state, initial_input[, integral_cost=..., terminal_cost=..., basis=..., trajectory_constraints=..., minimize_method=..., minimize_options=...])` accepts a flat model, time vector, and initial state/input vectors. `integral_cost(x, u)` and `terminal_cost(x, u)` return numeric scalar costs. `basis` accepts a trajectory basis.

Constraints use `(LinearConstraint, A, lb, ub)` or `(NonlinearConstraint, fun, lb, ub)` tuples; their markers, argument layouts, and bounds use the forms described for `point_to_point`. `minimize_method` is a string option accepting `SLSQP`; `minimize_options` is a mapping accepting `ftol` and `maxiter`.

The return is `SystemTrajectory`. A missing-cost refusal raises `TypeError`; basis refusal raises `ValueError`. Optimization notifications use `UserWarning`.

## `velunex.optimal.OptimalControlResult`

An `OptimalControlResult` exposes `time` as a numeric time vector, `states` as a numeric array indexed by state and time, and `inputs` as a numeric array indexed by input and time when `squeeze=False`. `cost` is the scalar achieved objective; `success` is boolean; `message` is a string carrying the outcome reason.

An unsuccessful result carries `success=False` and a nonempty `message`, together with the candidate `time`, `states`, and `inputs` arrays.

## `velunex.optimal.solve_optimal_trajectory`

`solve_optimal_trajectory(sys, timepts, initial_state, integral_cost, **kwargs)` accepts an input/output model, a numeric time vector, an initial-state vector, and a callback `integral_cost(x, u)` returning a numeric scalar.

Optional keywords are `terminal_cost` (scalar callback with state/input arguments), `trajectory_constraints` and `terminal_constraints` (constraint lists), `basis` (trajectory basis), `initial_guess` (input-by-time array), `squeeze` and `print_summary` (booleans), `minimize_method` (string option accepting `SLSQP`), `minimize_options` (mapping with `ftol` and `maxiter`), `trajectory_method` (string option accepting `shooting`), and `solve_ivp_kwargs` (mapping with `rtol` and `atol`).

Constraint tuples use `(LinearConstraint, A, lb, ub)` or `(NonlinearConstraint, fun, lb, ub)`, with markers from `scipy.optimize`. Linear rows address the concatenated state/input vector. A nonlinear callback `fun(x, u)` returns constraint values. Bounds are numeric scalars or arrays. The constraint conveniences in `velunex.optimal` produce values accepted in these lists.

The return is `OptimalControlResult`. Rejected initial-guess dimensions raise `ValueError`. Optimization notifications use `UserWarning`.

## `velunex.optimal.OptimalControlProblem`

`OptimalControlProblem(sys, timepts, integral_cost[, terminal_cost=..., minimize_method=..., minimize_options=...])` accepts an input/output model, time vector, scalar state/input cost callbacks, string option `SLSQP`, and an options mapping with `ftol` and `maxiter`.

`create_mpc_iosystem([name=..., inputs=..., outputs=...])` returns an input/output controller model, accepting optional system and signal names. It exposes integer `nstates`. Its input is the measured state vector and its output is the actuation vector. It can be supplied to `input_output_response` and `interconnect`.

Unsupported controller creation raises `VelunexNotImplemented`.

## `velunex.optimal.quadratic_cost`

`quadratic_cost(sys, Q, R[, x0, u0])` accepts a model, scalar or matrix weights (or `None`), and optional reference state/input vectors. References are also accepted as `x0` and `u0` keywords.

The return is a callable `cost(x, u)` taking state and input vectors and returning a numeric scalar. Rejected weight dimensions raise `ValueError`.

## `velunex.optimal.state_range_constraint`

`state_range_constraint(sys, lb, ub)` accepts a model and numeric lower and upper bound vectors. It returns a constraint accepted by `solve_optimal_trajectory` in `trajectory_constraints` or `terminal_constraints`. Rejected constraint dimensions raise `ValueError`.

## `velunex.optimal.state_poly_constraint`

`state_poly_constraint(sys, A, b)` accepts a model and a numeric constraint matrix and upper-bound vector. It returns a constraint accepted by `solve_optimal_trajectory` in `trajectory_constraints`. Rejected constraint dimensions raise `ValueError`.

## `velunex.optimal.input_range_constraint`

`input_range_constraint(sys, lb, ub)` accepts a model and numeric lower and upper bound vectors. It returns a constraint accepted by `solve_optimal_trajectory` in `trajectory_constraints`. Rejected constraint dimensions raise `ValueError`.

## `velunex.optimal.input_poly_constraint`

`input_poly_constraint(sys, A, b)` accepts a model and a numeric constraint matrix and upper-bound vector. It returns a constraint accepted by `solve_optimal_trajectory` in `trajectory_constraints`. Rejected constraint dimensions raise `ValueError`.

## `velunex.optimal.output_range_constraint`

`output_range_constraint(sys, lb, ub)` accepts a model and numeric lower and upper bound vectors. It returns a constraint accepted by `solve_optimal_trajectory` in `trajectory_constraints`. Rejected constraint dimensions raise `ValueError`.

## `velunex.optimal.output_poly_constraint`

`output_poly_constraint(sys, A, b)` accepts a model and a numeric constraint matrix and upper-bound vector. It returns a constraint accepted by `solve_optimal_trajectory` in `trajectory_constraints`. Rejected constraint dimensions raise `ValueError`.

## `velunex.optimal.OptimalEstimationResult`

An `OptimalEstimationResult` exposes `time` as a time vector; `states` as estimated states; `inputs` as estimated disturbances; and `outputs` as estimated measurement-noise values. With `squeeze=False`, these arrays have signal, time axes. `cost` is a numeric scalar objective; `success` is boolean; `message` is a reason string.

An unsuccessful result carries `success=False` and a nonempty `message`.

## `velunex.optimal.solve_optimal_estimate`

`solve_optimal_estimate(sys, timepts, outputs, inputs, integral_cost, **kwargs)` accepts an input/output model, time vector, measured-output and known-input histories indexed by signal and time, and a scalar callback `integral_cost(x, u, v, w)`. Callback arguments are state, known actuation, disturbance, and measurement-noise vectors.

Optional keywords are `control_indices` and `disturbance_indices` (channel-index lists), `initial_state` (prior vector), `terminal_cost` (scalar callback receiving initial state and prior), `trajectory_constraints`, `initial_guess` (pair of state-history and disturbance-history arrays, or `None`), `squeeze` and `print_summary` (booleans), `minimize_method` (string option accepting `SLSQP`), and `minimize_options` (mapping with `ftol` and `maxiter`).

`trajectory_constraints` accepts `scipy.optimize.LinearConstraint` and `scipy.optimize.NonlinearConstraint` instances. Linear rows address a concatenation of state, known actuation, disturbance, and measurement-noise vectors. Nonlinear constraint callables receive these four vectors separately. Bounds are numeric arrays. `disturbance_range_constraint` returns a compatible constraint.

The return is `OptimalEstimationResult`. Rejected history or guess dimensions raise `ValueError`. Optimization notifications use `UserWarning`.

## `velunex.optimal.gaussian_likelihood_cost`

`gaussian_likelihood_cost(sys, Rv, Rw)` accepts a model and scalar or matrix disturbance and measurement-noise covariances; either covariance can be `None`. It returns a scalar-valued callable `cost(x, u, v, w)` whose vector arguments are state, known actuation, disturbance, and measurement noise.

## `velunex.optimal.disturbance_range_constraint`

`disturbance_range_constraint(sys, lb, ub)` accepts a model and numeric lower/upper disturbance-bound vectors. It returns a constraint accepted in `solve_optimal_estimate` through `trajectory_constraints`.

## `velunex.optimal.OptimalEstimationProblem`

`OptimalEstimationProblem(sys, timepts, integral_cost[, terminal_cost=..., control_indices=..., disturbance_indices=..., minimize_method=..., minimize_options=...])` accepts a model, time vector, a scalar estimation-cost callback, an optional initial-state/prior cost callback, channel-index lists, string option `SLSQP`, and options mapping with `ftol` and `maxiter`.

`create_mhe_iosystem()` returns an input/output estimator whose input vector contains measurements followed by known controls, and whose output is a state-prediction vector. The estimator can be supplied to `input_output_response`.

Unsupported estimator creation raises `VelunexNotImplemented`.

## `velunex.config.defaults`

`velunex.config.defaults` is a mutable mapping supporting conversion to `dict`, deep copying, `clear()`, and `update(mapping)`.

Boolean keys `freqplot.dB`, `freqplot.deg`, and `freqplot.Hz` select magnitude, phase, and frequency display units. `velunex.squeeze_time_response` is a boolean shape option for time responses.

## `velunex.config`

`velunex.config` exposes the mutable configuration mapping `defaults`.

## `velunex`

`velunex` exposes the following public names:

`VelunexArgument`, `VelunexDimension`, `VelunexMIMONotImplemented`, `VelunexNotImplemented`, `StateSpace`, `TimeResponseData`, `TransferFunction`, `append`, `augw`, `balanced_reduction`, `bandwidth`, `bode_plot`, `boxgrid`, `canonical_form`, `care`, `circlegrid`, `combine_tf`, `combine_time_responses`, `config`, `correlation`, `create_estimator_iosystem`, `create_statefbk_iosystem`, `ctrb`, `damp`, `dare`, `dcgain`, `describing_function`, `describing_function_plot`, `describing_function_response`, `disk_margins`, `dlqe`, `dlqr`, `dlyap`, `drss`, `eigensys_realization`, `equilpoints`, `feedback`, `find_operating_point`, `forced_response`, `frd`, `frequency_response`, `friction_backlash_nonlinearity`, `gangof4_plot`, `gangof4_response`, `get_input_ff_index`, `get_output_fb_index`, `gram`, `h2syn`, `hankel_singular_values`, `hinfsyn`, `impulse_response`, `initial_response`, `input_output_response`, `interconnect`, `ispassive`, `linearize`, `lqe`, `lqr`, `lyap`, `markov`, `meshgrid`, `minimal_realization`, `mixsyn`, `modal_form`, `model_reduction`, `nichols_plot`, `nlsys`, `nyquist_plot`, `nyquist_response`, `observable_form`, `obsv`, `pade`, `parallel`, `phase_crossover_frequencies`, `phase_plane_plot`, `phaseplot`, `place`, `place_acker`, `place_varga`, `pole_zero_map`, `pole_zero_plot`, `poles`, `reachable_form`, `relay_hysteresis_nonlinearity`, `root_locus_map`, `root_locus_plot`, `rootlocus_pid_designer`, `rss`, `sample_system`, `saturation_nonlinearity`, `separatrices`, `series`, `similarity_transform`, `singular_values_plot`, `singular_values_response`, `sisotool`, `solve_passivity_LMI`, `split_tf`, `ss`, `ss2tf`, `stability_margins`, `step_info`, `step_response`, `summing_junction`, `system_norm`, `tf`, `tf2ss`, `time_response_plot`, `white_noise`, `zeros`, `zpk`.

## `velunex.flatsys`

`velunex.flatsys` exposes the following public names:

`BSplineFamily`, `BasisFamily`, `BezierFamily`, `FlatSystem`, `LinearFlatSystem`, `PolyFamily`, `flatsys`, `point_to_point`, `solve_flat_optimal`.

## `velunex.optimal`

`velunex.optimal` exposes the following public names:

`OptimalControlProblem`, `OptimalEstimationProblem`, `disturbance_range_constraint`, `gaussian_likelihood_cost`, `input_poly_constraint`, `input_range_constraint`, `output_poly_constraint`, `output_range_constraint`, `quadratic_cost`, `solve_optimal_estimate`, `solve_optimal_trajectory`, `state_poly_constraint`, `state_range_constraint`.

Constraint factory names have the form `<signal>_<kind>_constraint`: the signal components are `state`, `input`, and `output`, and the kind components are `range` and `poly`.

## `velunex.phaseplot`

`velunex.phaseplot` exposes `meshgrid`, `boxgrid`, `circlegrid`, `equilpoints`, and `separatrices`. These functions are also accessible directly from `velunex`.
