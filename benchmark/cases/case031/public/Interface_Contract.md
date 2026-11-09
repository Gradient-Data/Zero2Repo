# Interface Contract

Public component data uses pandas labeled tables; selectors and assignments use their `loc`, `at`, `iloc`, `index` and `columns` interfaces.

Consistency diagnostics are Python logging records. Their public carriers include `levelno` and `name`; warning diagnostics have level `WARNING` on `velmora.consistency`.

Optimisation batch diagnostics use `velmora.optimization.mga` and a `WARNING` or higher level.

Static graphical paths expose `vertices` as numeric coordinate pairs and `codes` as either `None` for a connected straight path or a matching integer array. Path codes use `1` for a subpath start, `2` for a line endpoint, `3` for quadratic-curve control and endpoint pairs, `4` for cubic-curve control/control/endpoint triples, `79` for subpath closure and `0` for path termination. Filled boundaries include the closing edge of each subpath.

## `velmora`

Import `Network` and `NetworkCollection` from `velmora`.

## `velmora.consistency`

`velmora.consistency` is an importable module.

## `velmora.consistency.ConsistencyError`

`ConsistencyError` is an exception class importable from `velmora.consistency`.

## `velmora.Network`

`Network()` and `Network(name=<str>, meta=<dict>)` construct a network. `name` is a readable and assignable string; `meta` is a readable and assignable dictionary supporting nested mappings.

`snapshots` is a pandas `Index`, or a `MultiIndex` with levels `period` and `timestep`. `periods` is the investment-period `Index`. `snapshot_weightings` is an assignable snapshot-indexed `DataFrame` with numeric columns `objective`, `generators` and `stores`. `investment_period_weightings` is an assignable period-indexed `DataFrame` with numeric columns `objective` and `years`.

`scenarios` is a pandas `Index`. `scenario_weightings` is a scenario-indexed `DataFrame` with numeric column `weight`. `has_scenarios` is a boolean. `crs` exposes the coordinate reference system as a CRS object supporting equality.

`objective` is a numeric scalar reporting the objective of the solved network. `model` exposes the editable optimisation model. `optimize`, `cluster`, `statistics`, `plot` and `explore` are public access paths.

## `velmora.Network.c`

`c` is the component store. `c[<component>]` and `components[<component>]` select a category by its class name or list name; category attributes on `c` use the list name. The names are:

| Class name | List name |
| --- | --- |
| `Bus` | `buses` |
| `Carrier` | `carriers` |
| `Generator` | `generators` |
| `Load` | `loads` |
| `Line` | `lines` |
| `Transformer` | `transformers` |
| `Link` | `links` |
| `Process` | `processes` |
| `StorageUnit` | `storage_units` |
| `Store` | `stores` |
| `ShuntImpedance` | `shunt_impedances` |
| `GlobalConstraint` | `global_constraints` |
| `Shape` | `shapes` |
| `LineType` | `line_types` |
| `TransformerType` | `transformer_types` |

Each selected category exposes `static`, an asset-indexed pandas `DataFrame`; `dynamic`, a mapping of attribute names to snapshot-by-asset `DataFrame` objects, also supporting attribute access; and `piecewise`, a mapping of characteristic names to breakpoint-indexed `DataFrame` objects. Table cells and entire dynamic tables support labeled assignment. With scenarios, static rows and dynamic columns use a `MultiIndex` named `scenario`, `name`. Piecewise columns use levels `name`, `attribute`, where `p_pu` is the operating quantity coordinate and the characteristic name identifies its paired values. Ragged curves represent missing trailing pairs as missing numeric cells.

Static capacity fields are numeric: `p_nom`, `e_nom`, `s_nom` denote nominal power, energy and apparent-power capacity. The concrete fields `p_nom_min`, `p_nom_max`, `p_nom_set`, `p_nom_mod`, `p_nom_opt`, `p_nom_extendable`, `e_nom_min`, `e_nom_max`, `e_nom_set`, `e_nom_mod`, `e_nom_opt`, `e_nom_extendable`, `s_nom_min`, `s_nom_max`, `s_nom_set`, `s_nom_mod`, `s_nom_opt`, `s_nom_extendable` denote corresponding lower bounds, upper bounds, fixed targets, module sizes, solved capacities and boolean investment eligibility. Generator, storage-unit, link and process capacities use `p_nom`; stores use `e_nom`; lines and transformers use `s_nom`.

Shared static input fields include string `carrier`, numeric `build_year`, `lifetime`, `capital_cost`, `overnight_cost`, `discount_rate`, `fom_cost`, `length`, `weight`, `sign`, and boolean `active`. These identify the carrier, commissioning year, asset lifetime, annualised investment coefficient, overnight investment coefficient, financing rate, fixed operating coefficient, geographic length, aggregation weight, injection sign and activity eligibility. `description` is descriptive text. Caller-supplied descriptive column names and values remain accessible as columns.

Bus static fields are numeric `v_nom`, `x`, `y`, `v_mag_pu_set`, `v_mag_pu_min`, `v_mag_pu_max`; string `carrier`, `unit`, `country`, `location`, `control` and `sub_network`. These carry nominal voltage, coordinates, voltage target and bounds, carrier, unit and grouping labels, bus control and subnetwork identity. The electrical-carrier spellings are `AC` and `DC`; control spellings are `PQ`, `PV` and `Slack`. A cleared control designation is an empty string.

One-port component connections use string `bus`; branches use string `bus0`, `bus1`, `bus2`, `bus3` for their connected port buses. Static operational fields include numeric `p_set`, `q_set`, `p_min_pu`, `p_max_pu`, `efficiency`, `e_sum_min`, `e_sum_max`, `p_init`, `ramp_limit_up`, `ramp_limit_down`, `ramp_limit_start_up`, `ramp_limit_shut_down`, `marginal_cost`, `marginal_cost_quadratic`, `marginal_cost_storage`, `spill_cost`. These denote prescribed active/reactive power, availability bounds, conversion efficiency, cumulative energy bounds, initial dispatch, ordinary and transition ramp bounds, and operating-cost coefficients. Missing fixed generator dispatch is represented by a missing numeric cell.

Storage-unit fields include numeric `max_hours`, `state_of_charge_initial`, `state_of_charge_set`, `efficiency_store`, `efficiency_dispatch`, `p_store_set`, `p_dispatch_set`, `inflow`, `standing_loss`, and boolean `cyclic_state_of_charge`, `cyclic_state_of_charge_per_period`, `state_of_charge_initial_per_period`. These carry energy duration, initial/target energy, charging/discharging conversion, charging/discharging targets, inflow, standing loss, and boundary-condition selections. Store fields include numeric `e_initial`, `e_set`, `e_min_pu`, `e_max_pu`, `standing_loss`, and boolean `e_cyclic`, `e_cyclic_per_period`, `e_initial_per_period` for their corresponding energy inputs.

Link conversion fields are numeric `efficiency`, `efficiency2`, `efficiency3`, `delay`, `delay2`, with boolean `cyclic_delay`. Process conversion fields are numeric `rate0`, `rate1`, `rate2`, `rate3`, `delay0`, `delay1`, `delay2`, with boolean `cyclic_delay1`. Rates and efficiencies describe the corresponding port conversion; delays are elapsed delivery delays and cyclic fields select the delivery boundary form.

Scheduling inputs on generators, links and processes include boolean `committable`, `maintainable`; numeric `min_up_time`, `min_down_time`, `up_time_before`, `down_time_before`, `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `maintenance_duration`, `maintenance_events`, `maintenance_pu`. They carry minimum operating/rest durations, preceding operating/rest history, transition and standby cost coefficients, maintenance duration/count and unavailable capacity fraction.

Passive-branch input columns include numeric `r`, `x`, `g`, `b`, `s_min_pu`, `s_max_pu`, `num_parallel`, `terrain_factor`, `v_ang_min`, `v_ang_max`, and string `type`. They carry series resistance/reactance, shunt conductance/susceptance, flow availability bounds, circuit count, terrain multiplier, angle bounds and electrical-type identity. Transformer fields additionally include numeric `tap_ratio`, `tap_side`, `tap_position`, `phase_shift`, `phase_shift_min`, `phase_shift_max`, and string `model`, whose circuit-form spellings are `t` and `pi`. Shunt impedances expose numeric `g`, `b`.

Line-type columns are numeric `r_per_length`, `x_per_length`, `c_per_length`, `f_nom`, giving length-specific electrical characteristics and frequency. Transformer-type columns are numeric `s_nom`, `v_nom_0`, `v_nom_1`, `vsc`, `vscr`, `pfe`, `i0`, `phase_shift`, `tap_side`, `tap_neutral`, `tap_step`, giving rated capacity and voltages, short-circuit and no-load characteristics, phase and tap information.

Carrier fields include numeric `co2_emissions`, `max_growth`, `max_relative_growth`, and string `color`, `nice_name` for emission coefficient, growth limits, colour and display label. Global-constraint fields are string `type`, `carrier_attribute`, `sense`, `bus`; numeric `constant`, `investment_period`, `mu` for constraint selection, carrier attribute selector, comparison, scope, right-hand side, period scope and solved shadow value. The type spellings used here are `primary_energy`, `operational_limit`, `transmission_volume_expansion_limit`, `transmission_expansion_cost_limit`, `tech_capacity_expansion_limit`; comparison spellings are `<=`, `>=`, `==`. A transmission carrier selection in `carrier_attribute` is a comma-separated string of carrier names.

Shape static rows expose `geometry` as a shapely geometry object, `component` as a component-category string, and `idx` as its associated asset identity. `sub_networks.static` exposes `obj`; each subnetwork object has string `slack_generator`, identifying its slack generator.

Calculated dynamic tables use numeric `p`, `q` for active/reactive power, `v_ang`, `v_mag_pu` for bus voltage, `p0`, `p1`, `p2`, `p3`, `q0`, `q1` for terminal active/reactive powers, `e` for store energy, `state_of_charge` for storage-unit energy, `p_store`, `p_dispatch` for charging/discharging power, `spill` for spilled inflow, `status`, `start_up`, `shut_down`, `maintenance_start`, `maintenance` for scheduling results, `marginal_price`, `mu_upper` for prices and shadow values, and `phase_shift_opt` for realised transformer phase shift. `marginal_cost_piecewise_opt` is the realised unit operating-cost value; static `capital_cost_piecewise_opt` is the realised unit investment-cost value.

## `velmora.Network.components`

`components` exposes the same category-selection interface and component tables as `c`; `components[<component>]` uses the component class name or list name.

## `velmora.Network.add`

`add(class_name, name, overwrite=<bool>, **kwargs)` accepts a component-category string and either one string/integer asset name or a sequence of names. Attribute keyword arguments accept scalars, per-asset sequences or Series, and snapshot-indexed time series. For a single asset a time series can be a sequence or Series; for multiple assets it can be a snapshot-by-asset DataFrame or two-dimensional array. A characteristic can be a mapping from numeric quantity breakpoint to numeric value. Rejected binding raises `ValueError`; unsupported data combinations raise `NotImplementedError`. Curve refusal uses the documented exception from either `add` or `optimize`.

## `velmora.Network.remove`

`remove(class_name, name)` accepts a component-category string and one asset name or a sequence of names. Results are observed in the component tables. Removal refusal raises `KeyError`.

## `velmora.Network.rename_component_names`

`rename_component_names(component, **kwargs)` accepts a component-category string and keyword mappings from existing names to replacement strings. Results are observed in component identities, connection fields and dynamic column labels.

## `velmora.Network.copy`

`copy()` returns a `Network`, including its public component tables, `name` and `meta`.

## `velmora.Network.slice_network`

`slice_network(buses=<sequence>)` and `slice_network(snapshots=<sequence of integer positions>)` return a `Network`. Its component tables, `snapshots`, `periods` and `snapshot_weightings` expose the selected data. It also exposes `investment_period_weightings`, a `DataFrame` indexed by its periods with `objective` and `years` columns.

## `velmora.Network.merge`

`merge(other, with_time=<bool>)` accepts another `Network` and returns a `Network`. The returned component tables, `name`, `meta`, `snapshots`, `snapshot_weightings`, `line_types` and `transformer_types` are readable. A rejected merge raises `ValueError`.

## `velmora.Network.set_snapshots`

`set_snapshots(snapshots, default_snapshot_weightings=<float>, weightings_from_timedelta=<bool>)` accepts a label sequence, pandas Index, DatetimeIndex or MultiIndex. The assigned axes, weights and input series are read through `snapshots`, `snapshot_weightings` and component `dynamic` tables. A refused axis raises `ValueError`.

## `velmora.Network.set_investment_periods`

`set_investment_periods(periods)` accepts a sequence of investment-period labels. The result is exposed through `snapshots`, `periods`, component `dynamic` tables, `snapshot_weightings` and `investment_period_weightings`. Refused assignments use `ValueError`; unsupported reduction of an established period axis uses `NotImplementedError`.

## `velmora.Network.set_scenarios`

`set_scenarios(scenarios)` accepts a sequence of scenario names or a mapping from names to numeric probabilities. Results are exposed through `scenarios`, `scenario_weightings` and scenario-labeled component tables. Rejected probabilities raise `ValueError`. Unsupported assignment or data combination raises `NotImplementedError`.

## `velmora.Network.get_scenario`

`get_scenario(scenario)` accepts a scenario-name string and returns a `Network`, with readable `has_scenarios`, component tables, snapshots and weights.

## `velmora.Network.set_risk_preference`

`set_risk_preference(alpha=<float>, omega=<float>)` accepts confidence and risk weight. Refusal raises `ValueError`, either from this binding call or the subsequent optimisation. Results are exposed by scenario-labeled solved tables and scalar `objective`.

## `velmora.Network.get_switchable_as_dense`

`get_switchable_as_dense(component, attr)` accepts component-category and attribute strings and returns a pandas DataFrame indexed by snapshots with asset-name columns containing the effective attribute values.

## `velmora.Network.adjacency_matrix`

`adjacency_matrix(branch_components=<sequence of category strings>, busorder=<Index>, return_dataframe=True)` returns a numeric pandas `DataFrame` whose rows and columns use the supplied bus order. An entry indicates the directed connection from its row bus to its column bus; numeric `1` means connected and `0` means absent.

## `velmora.Network.c.lines.apply_seasonal_rating`

`apply_seasonal_rating(ratings, summer_months=<sequence of integers>, compose=<bool>)` is available at `c.lines.apply_seasonal_rating`. `ratings` is a line-indexed DataFrame with numeric `summer` and `winter` columns. Results appear in `c.lines.dynamic.s_max_pu`, indexed by snapshots and line names. Refusals use `TypeError` for snapshot type, `KeyError` for missing identity or column, and `ValueError` for rejected numeric values or month selection.

## `velmora.Network.calculate_dependent_values`

`calculate_dependent_values()` exposes electrical values through line and transformer `static` tables. A refused electrical type raises `ValueError`.

## `velmora.Network.consistency_check`

`consistency_check(strict=<None or sequence of check names>)` reports diagnostics as logging records. Refusal of inconsistent data raises `velmora.consistency.ConsistencyError`; an unrecognised check selector raises `ValueError`. The check-name strings are `unknown_buses`, `unknown_carriers`, `disconnected_buses`, `zero_impedances`, `static_power_attrs`, `time_series_power_attrs`, `phase_shift_bounds`, `scenario_invariant_attrs`, `line_types`, `transformer_types`, `dispatch_delays` and `maintenance`.

## `velmora.Network.consistency_check_plots`

`consistency_check_plots(strict=<sequence of check names>)` accepts the selector `missing_carrier_colors`. Refusal raises `ConsistencyError`.

## `velmora.Network.determine_network_topology`

`determine_network_topology()` exposes subnetwork identifiers through `c.buses.static` column `sub_network`.

## `velmora.Network.incidence_matrix`

`incidence_matrix(branch_components=<sequence of category strings>, busorder=<Index>)` returns a numeric matrix supporting `toarray()`. Rows follow `busorder`; columns follow the selected category's public static asset order. The incidence encoding is `+1` at `bus0` and `-1` at `bus1`, with `0` for an unconnected bus.

## `velmora.Network.lpf`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `velmora.Network.lpf_contingency`

`lpf_contingency(snapshots=<sequence>, branch_outages=<optional sequence of (component, name) pairs>)` returns a numeric DataFrame with a two-level branch row index `(component, name)`. Column `base` carries the base flow; each tuple-labeled outage column `(<component>, <name>)` carries the corresponding sending-terminal flow. Identity-selection refusal raises `KeyError`.

## `velmora.Network.model`

The editable `model` returned by `create_model()` exposes `variables`, keyed by variable name. The dispatch variable key `Generator-p` supports `sel(name=<asset>)`. Variables and expressions support arithmetic, unary negation, and comparison operators `==`, `>=` and `<=` to form relations.

The model exposes `add_variables(lower=<number>, upper=<number>, name=<str>)` returning a variable, `add_constraints(<relation>, name=<str>)`, and `add_objective(<expression>, overwrite=True)`. `objective.expression` exposes the current objective expression. A variable or selected expression exposes `solution.item()` as its solved numeric scalar.

Piecewise total-cost variables use keys `<Component>-marginal_cost_piecewise` and `<Component>-capital_cost_piecewise`; selection uses `sel(name=<asset>)`.

## `velmora.Network.optimize.add_load_shedding`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `velmora.Network.optimize.create_model`

`create_model(piecewise_options=<optional list of mappings>)` returns the editable model also available as `Network.model`.

## `velmora.Network.optimize.fix_optimal_capacities`

`fix_optimal_capacities()` exposes fixed nominal capacities and investment flags through component `static` columns `p_nom`, `e_nom`, `s_nom`, `p_nom_extendable`, `e_nom_extendable` and `s_nom_extendable`.

## `velmora.Network.optimize`

`optimize(snapshots=<optional sequence>, solver_name=<str>, solver_options=<dict>, multi_investment_periods=<bool>, linearized_unit_commitment=<bool>, assign_all_duals=<bool>, include_objective_constant=<bool>, transmission_losses=<selection>, piecewise_options=<list of mappings>)` is callable on a network. `solver_name` accepts `highs`. `solver_options` accepts numeric `threads`. Options can be omitted individually.

The return value is a pair of strings `(<status>, <termination_condition>)`: `('ok', 'optimal')` denotes an optimal solution; `('warning', 'infeasible')` denotes infeasible termination. Solved quantities are exposed through `objective` and the component static and dynamic result tables. Public validation refusals use `ValueError` or `ConsistencyError`; unsupported characteristic data uses `NotImplementedError`. Curve-related refusal can occur in `add` or this call.

`transmission_losses` accepts a boolean or a mapping. Mapping fields are string `mode`, numeric `atol`, `rtol` and integer `segments`. The mode spellings are `secants` and `tangents`, selecting the upper and lower loss-approximation interfaces; `atol` and `rtol` express absolute and relative error requests, and `segments` expresses resolution.

Each `piecewise_options` mapping has `component` and `attribute` string selectors, `sign` as a comparison string, and boolean `cumulative_attr`. The comparison spelling `==` requests equality.

## `velmora.Network.optimize.optimize_mga`

`optimize_mga(weights=<mapping>, sense=<str>, slack=<float>, solver_name=<str>, solver_options=<dict>)` returns a two-string optimisation status pair. `weights` has form `{<component>: {<variable>: <coefficients>}}`; capacity coefficients are mappings from asset names to numbers and operating coefficients are snapshot-by-asset DataFrames. Capacity and operating variable selectors include `p_nom` and `p`. `sense` spellings are `min` and `max`. Results expose component tables, scalar `objective` for the signed alternative objective, and `meta['slack']` for the relative cost allowance. Refusal raises `ValueError`.

## `velmora.Network.optimize.optimize_mga_in_direction`

`optimize_mga_in_direction(direction=<mapping>, dimensions=<mapping>, slack=<float>, solver_name=<str>, solver_options=<dict>)` accepts `direction` mapping dimension names to numeric weights and `dimensions` mapping dimension names to component/variable/coefficient mappings. It returns `(<status>, <termination_condition>, coordinates)`, where `coordinates` is a numeric Series indexed by dimension name. The network exposes the corresponding solved data and signed alternative `objective`. Refusal raises `ValueError`.

## `velmora.Network.optimize.optimize_mga_in_multiple_directions`

`optimize_mga_in_multiple_directions(directions=<list of mappings>, dimensions=<mapping>, slack=<float>, max_parallel=<int>, solver_name=<str>, solver_options=<dict>)` returns `(<directions>, <coordinates>)`, two DataFrames sharing a row index, with dimension names as columns. The first table carries the requested direction coefficients for each returned row; the second carries the associated projection coordinates. A wholly refused batch returns two empty DataFrames and emits a `WARNING`-or-higher logging record on `velmora.optimization.mga`.

## `velmora.Network.optimize.optimize_security_constrained`

`optimize_security_constrained(branch_outages=<optional selection>, multi_investment_periods=<bool>, solver_name=<str>, solver_options=<dict>)` accepts line-name sequences or a pandas MultiIndex of `(component, name)` outage labels. It returns the two-string optimisation status pair and exposes solved component results and `objective`. Refused selections raise `ValueError`.

## `velmora.Network.optimize.optimize_transmission_expansion_iteratively`

`optimize_transmission_expansion_iteratively(solver_name=<str>, solver_options=<dict>, max_iterations=<int>, line_unit_size=<number>, link_unit_size=<mapping>, line_threshold=<number>, link_threshold=<mapping>, fractional_last_unit_size=<bool>)` returns the two-string optimisation status pair. Link option mappings use carrier strings as keys and numeric values. Results appear in branch static capacity and electrical fields, terminal-power tables and generator dispatch.

## `velmora.Network.optimize.optimize_with_rolling_horizon`

`optimize_with_rolling_horizon(snapshots=<optional snapshot index>, horizon=<int>, overlap=<int>, solver_name=<str>, solver_options=<dict>)` returns the supplied `Network` object, exposing its populated component result tables. `horizon` and `overlap` are lengths measured in snapshots. Refusal raises `ValueError`.

## `velmora.Network.optimize.solve_model`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `velmora.Network.pf`

`pf(snapshots=<optional sequence>, x_tol=<float>, distribute_slack=<bool>, slack_weights=<selection>)` returns a mapping with `converged` and `error`. Both are DataFrames indexed by requested snapshots with subnetwork identifiers as columns. `converged` contains booleans indicating convergence; `error` contains numeric remaining power mismatch, including nonfinite numeric values for arithmetic divergence. Component result tables expose bus voltages and active/reactive injection, generator/load/shunt active/reactive power and both passive-branch terminal powers. `slack_weights` accepts strings `p_set`, `p_nom`, `p_nom_opt`, or a dictionary keyed by subnetwork identifier whose values are bus-indexed or generator-indexed numeric Series. Generator-indexed participation Series use index name `name`. Refused participation raises `ValueError`.

## `velmora.Network.optimize.expressions.capacity`

`expressions.capacity(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>)` is available through `optimize.expressions` and returns a decision-linked expression for nominal capacity. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving.

## `velmora.Network.optimize.expressions.capex`

`expressions.capex(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>)` is available through `optimize.expressions` and returns a decision-linked expression for capital expenditure. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving.

## `velmora.Network.optimize.expressions.opex`

`expressions.opex(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>, groupby_time=<str>)` is available through `optimize.expressions` and returns a decision-linked expression for operating expenditure. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving. The time-aggregation spelling is `sum`.

## `velmora.Network.optimize.expressions.operation`

`expressions.operation(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>, groupby_time=<str>)` is available through `optimize.expressions` and returns a decision-linked expression for operation quantity. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving. The time-aggregation spelling is `sum`.

## `velmora.Network.optimize.expressions.curtailment`

`expressions.curtailment(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>, groupby_time=<str>)` is available through `optimize.expressions` and returns a decision-linked expression for curtailed generation. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving. The time-aggregation spelling is `sum`.

## `velmora.Network.optimize.expressions.energy_balance`

`expressions.energy_balance(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>, groupby_time=<str>, bus_carrier=<str>, at_port=<sequence of port names>)` is available through `optimize.expressions` and returns a decision-linked expression for signed energy balance. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving. The time-aggregation spelling is `sum`. Port-name selectors use `bus0` and `bus1`.

## `velmora.Network.optimize.expressions.supply`

`expressions.supply(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>, groupby_time=<str>, bus_carrier=<str>, at_port=<sequence of port names>)` is available through `optimize.expressions` and returns a decision-linked expression for supply. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving. The time-aggregation spelling is `sum`. Port-name selectors use `bus0` and `bus1`.

## `velmora.Network.optimize.expressions.withdrawal`

`expressions.withdrawal(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>, groupby_time=<str>, bus_carrier=<str>, at_port=<sequence of port names>)` is available through `optimize.expressions` and returns a decision-linked expression for withdrawal. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving. The time-aggregation spelling is `sum`. Port-name selectors use `bus0` and `bus1`.

## `velmora.Network.optimize.expressions.transmission`

`expressions.transmission(components=<sequence of strings>, groupby=<sequence of strings>, carrier=<str>, nice_names=<bool>, groupby_time=<str>, bus_carrier=<str>, at_port=<sequence of port names>)` is available through `optimize.expressions` and returns a decision-linked expression for transmission. Group selection supports `unstack('group').sel(component=<category>, carrier=<carrier>, bus=<bus>)`. A selected expression participates in model arithmetic and comparisons and exposes numeric `solution.item()` after solving. The time-aggregation spelling is `sum`. Port-name selectors use `bus0` and `bus1`.

## `velmora.Network.export_to_csv_folder`

`export_to_csv_folder(path)` accepts a caller-supplied string or path object naming a directory. The operation writes the network in the named format. Results are read from the written data. Unsupported export raises `NotImplementedError`.

## `velmora.Network.import_from_csv_folder`

`import_from_csv_folder(path)` accepts a caller-supplied string or path object naming a directory. The operation exposes the imported network through component tables, `name`, `meta`, `snapshots` and weight tables.

## `velmora.Network.export_to_netcdf`

`export_to_netcdf(path)` accepts a caller-supplied string or path object naming a file. The operation writes the network in the named format. Results are read from the written data.

## `velmora.Network.import_from_netcdf`

`import_from_netcdf(path)` accepts a caller-supplied string or path object naming a file. The operation exposes the imported network through component tables, `name`, `meta`, `snapshots` and weight tables.

## `velmora.Network.export_to_hdf5`

`export_to_hdf5(path)` accepts a caller-supplied string or path object naming a file. The operation writes the network in the named format. Results are read from the written data. Unsupported export raises `NotImplementedError`. Missing optional writing support can be reported by `ImportError` with nonempty explanatory text; a working writer exposes HDF5 data in the stated storage form.

## `velmora.Network.import_from_hdf5`

`import_from_hdf5(path)` accepts a caller-supplied string or path object naming a file. The operation exposes the imported network through component tables, `name`, `meta`, `snapshots` and weight tables.

## `velmora.Network.export_to_excel`

`export_to_excel(path)` accepts a caller-supplied string or path object naming a file. The operation writes the network in the named format. Results are read from the written data. Unsupported export raises `NotImplementedError`. Missing optional writing support can be reported by `ImportError` with nonempty explanatory text; a working writer exposes an actual Excel workbook.

## `velmora.Network.import_from_excel`

`import_from_excel(path)` accepts a caller-supplied string or path object naming a file. The operation exposes the imported network through component tables, `name`, `meta`, `snapshots` and weight tables.

## `csv_folder`

The caller supplies the directory path to `export_to_csv_folder` or `import_from_csv_folder`. Component list names used in these data are `buses`, `generators`, `loads`, `lines`, `transformers`, `links`, `stores` and `storage_units`. Static attribute names are the corresponding public component-table column names.

Static data is in `<component>.csv` with asset identity as the first indexed column, named `name`. Time series are in `<component>-<attribute>.csv`, with a snapshot-row index followed by asset-name columns. Piecewise data is in `<component>-<attribute>-pw.csv`, with a breakpoint row index and two column-header levels, asset `name` and `attribute`. The curve coordinate and characteristic columns include `p_pu` and `marginal_cost`.

`snapshots.csv` contains `snapshot` for a single snapshot axis, or `period` and `timestep` for a period axis, together with numeric `objective`, `generators` and `stores` weighting columns. `meta.json` contains a JSON object carrying network metadata.

`network.csv` carries the network `name`. `investment_periods.csv` is indexed by `period` with numeric `objective` and `years` columns.

## `netcdf`

The caller supplies a netCDF file path to `export_to_netcdf` or `import_from_netcdf`. Component list names used in these data are `buses`, `generators`, `loads`, `lines`, `transformers`, `links`, `stores` and `storage_units`. Static attribute names are the corresponding public component-table column names.

A deterministic dataset uses asset coordinates `<component>_i` and static variables `<component>_<attribute>` on that coordinate. Dynamic variables `<component>_t_<attribute>` use dimensions `snapshots` and `<component>_t_<attribute>_i`, with the latter carrying asset names. Concrete carriers include `buses_i`, `buses_v_nom`, `generators_i`, `generators_bus`, `generators_p_nom`, `loads_i`, `loads_bus`, `loads_t_p_set` and `loads_t_p_set_i`.

Snapshot coordinates use `snapshots_snapshot` for a single axis or `snapshots_period` for the investment-period label, on dimension `snapshots`. Snapshot weight variables are `snapshots_objective`, `snapshots_generators` and `snapshots_stores`. Investment-period weights include `investment_periods_years`. The dataset attribute `meta` contains JSON-encoded network metadata.

A piecewise variable `<component>_pw_<attribute>` has dimensions `breakpoint`, `<component>_pw_<attribute>_i` and `<component>_pw_<attribute>_attr_i`; the latter two coordinate axes identify assets and paired attribute names. Concrete names are `generators_pw_marginal_cost`, `generators_pw_marginal_cost_i` and `generators_pw_marginal_cost_attr_i`, with paired `p_pu` and `marginal_cost` values.

Scenario data uses coordinate `scenario` and numeric variable `scenario_weight`. Static variables carry an additional `scenario` dimension; dynamic variables carry `snapshots`, `scenario` and their asset coordinate. Shape identity is `shapes_i` and geometry is WKT text in `shapes_geometry`. Dataset attribute `crs` is JSON with `_crs` carrying WKT for the coordinate reference system.

Dataset attribute `network_name` carries the network name. `snapshots_timestep` carries period-axis timesteps; `investment_periods` carries period labels and `investment_periods_objective` carries their objective weights.

## `hdf5`

The caller supplies an HDF5 path to `export_to_hdf5` or `import_from_hdf5`. Data is readable as pandas HDFStore tables and Series. Component list names used in these data are `buses`, `generators`, `loads`, `lines`, `transformers`, `links`, `stores` and `storage_units`. Static attribute names are the corresponding public component-table column names.

Static table keys have form `/<component>` and a `name` column. Time-series keys have form `/<component>_t/<attribute>`; rows correspond to snapshots and integer columns refer to positions in the stored component table. Piecewise Series keys have form `/<component>_p/<attribute>`, with index levels `breakpoint`, `name` and `attribute`. Characteristic fields include `p_pu` and `marginal_cost`.

`/network` identifies the network by `name`, represented as an index or column. `/snapshots` carries `snapshot` for a single axis, or `period` and `timestep`, with `objective`, `generators` and `stores` weights.

`/investment_periods` has a `period` index with numeric `objective` and `years` columns. `/meta` is a one-element Series containing JSON metadata.

## `excel`

The caller supplies a workbook path to `export_to_excel` or `import_from_excel`. Component list names used in these data are `buses`, `generators`, `loads`, `lines`, `transformers`, `links`, `stores` and `storage_units`. Static attribute names are the corresponding public component-table column names.

Static worksheet names are `<component>` and carry an asset-identity column `name` followed by static attributes. Time-series worksheets are `<component>-<attribute>` with a snapshot-row index and asset-name columns. Piecewise worksheets are `<component>-<attribute>-pw` with `breakpoint`, `attribute` and asset-name columns; the characteristic coordinate and value labels include `p_pu` and `marginal_cost`.

Worksheet `snapshots` carries `snapshot` for a single axis, or `period` and `timestep`, with `objective`, `generators` and `stores` weights.

Worksheet `network` carries the network `name`. Worksheet `investment_periods` uses a `period` index with numeric `objective` and `years` columns. Worksheet `meta` carries columns `Key` and `Value`; nested dictionary values are JSON text.

## `velmora.Network.import_from_pypower_ppc`

`import_from_pypower_ppc(ppc, overwrite_zero_s_nom=<optional number>)` accepts a case mapping with keys `version`, `baseMVA`, `bus`, `gen` and `branch`. `version` uses the string spelling `2`; `baseMVA` is numeric; the tables are two-dimensional numeric arrays in PYPOWER's version-two exchange format.

Bus rows exchange identifier, bus-control code, active/reactive demand, active/reactive shunt power, area, voltage magnitude and angle, voltage base, zone and voltage bounds. Generator rows exchange bus identity, active/reactive dispatch, reactive bounds, voltage target, base power, status, and active-power bounds. Branch rows exchange terminal bus identifiers, series resistance/reactance, shunt susceptance, rating columns, tap ratio, phase shift, status and angle bounds. Imported bus names are string bus identifiers; generated names use `L<ordinal>` for loads and lines in their separate categories, `G<ordinal>` for generators, `T<ordinal>` for transformers and `S<ordinal>` for shunts. Ordinals use decimal notation beginning at `0`.

The numeric array columns use zero-based positions. `bus` columns are: `0` bus identifier, `1` control code, `2` active demand, `3` reactive demand, `4` active shunt power, `5` reactive shunt power, `6` area, `7` voltage magnitude, `8` voltage angle, `9` nominal voltage, `10` zone, `11` maximum voltage, `12` minimum voltage. `gen` columns are: `0` connected bus, `1` prescribed active output, `2` prescribed reactive output, `3` maximum reactive output, `4` minimum reactive output, `5` voltage target, `6` machine base power, `7` service status, `8` maximum active output, `9` minimum active output. `branch` columns are: `0` first bus, `1` second bus, `2` resistance, `3` reactance, `4` susceptance, `5` first rating, `6` second rating, `7` third rating, `8` tap ratio, `9` phase shift, `10` service status, `11` minimum angle, `12` maximum angle.

## `velmora.Network.import_from_pandapower_net`

`import_from_pandapower_net(net)` accepts a pandapower network object with tabular `bus`, `gen`, `sgen`, `load`, `ext_grid`, `shunt`, `line` and `trafo` data. Each table has a `name` column carrying asset names. Bus references are values from the source `bus` table index. Imported data is exposed through the Network component static tables.

Source columns have these forms:

| Table | Columns |
| --- | --- |
| `bus` | `name`: asset name; `vn_kv`: numeric nominal voltage in kV |
| `gen` | `name`: asset name; `bus`: source bus reference; `p_mw`: numeric active power in MW; `scaling`: numeric power multiplier; `vm_pu`: numeric voltage target in per unit |
| `sgen`, `load` | `name`: asset name; `bus`: source bus reference; `p_mw`, `q_mvar`: numeric active/reactive power in MW/Mvar; `scaling`: numeric power multiplier |
| `ext_grid` | `name`: asset name; `bus`: source bus reference; `vm_pu`: numeric voltage target in per unit |
| `shunt` | `name`: asset name; `bus`: source bus reference; `p_mw`, `q_mvar`: numeric active/reactive power in MW/Mvar; `vn_kv`: numeric nominal voltage in kV |
| `line` | `name`: asset name; `from_bus`, `to_bus`: source bus references; `std_type`: electrical-type name; `length_km`: numeric length in km; `parallel`: numeric circuit count |
| `trafo` | `name`: asset name; `hv_bus`, `lv_bus`: source bus references; `std_type`: electrical-type name |

## `velmora.NetworkCollection`

`NetworkCollection(networks, index=<labels>)` is importable from `velmora`. `networks` accepts a sequence of Network objects or a pandas Series of Network objects with its own index. `index` accepts a pandas Index, MultiIndex or label sequence. `index` on the collection exposes those labels, including caller-supplied level names. `networks` on the collection is a pandas Series of member networks indexed by those labels and supports `groupby(level=<level name>)`. A rejected label assignment raises `ValueError`.

`c` exposes combined component tables. Static row levels are the collection's named label levels followed by `scenario` when present, then asset `name`. In particular, `c.generators.static` exposes numeric `p_nom`. `statistics` exposes the statistics calls and chart accessors on the collection.

Label lookup `collection[<label>]` returns a member Network. Selection by a collection-indexed boolean Series returns a NetworkCollection with a corresponding `index`.

## `velmora.NetworkCollection.get_network`

`get_network(collection)` accepts a collection member label, including a tuple for a MultiIndex, and returns the corresponding Network object.

## `velmora.Network.statistics`

`statistics` is available on Network and NetworkCollection. Each metric is callable with keyword arguments. Common keyword forms are `components=<sequence of category strings>`, `groupby=<False, string, sequence or callable>`, `nice_names=<bool>`, `drop_zero=<bool>` and `round=<integer decimal places>`. Component-independent aggregation uses `aggregate_across_components=<bool>`. Carrier selection uses `carrier=<string or sequence>` and `bus_carrier=<string or sequence>`. Port selection uses `at_port=<string or sequence>`; port spellings include `all`, `bus0` and `bus1`.

Built-in grouping selectors are `carrier`, `bus`, `bus_carrier`, `country`, `location`, `name` and `unit`. A supplied component static column name is also a grouping selector. A grouping callable receives the network, component category, port suffix and `nice_names` keyword and returns an asset-indexed Series of group labels with its group-level name. Such callables can also appear inside a grouping sequence.

A metric result is a numeric pandas Series indexed first by `component`, followed by collection label levels when applicable, `scenario` when applicable, and asset `name` or the requested group levels. With `aggregate_across_components=True` the component level is absent. Results with retained snapshots or investment periods are DataFrames with the same row labels and snapshot or period columns. `groupby_time=False` retains snapshot columns; `sum` and `mean` are time-aggregation spellings.

## `velmora.Network.statistics.installed_capacity`

`statistics.installed_capacity(**kwargs)` returns installed nominal capacity through the common labeled statistics result form. It additionally accepts `storage=<bool>` to select storage-energy capacity.

## `velmora.Network.statistics.optimal_capacity`

`statistics.optimal_capacity(**kwargs)` returns solved nominal capacity through the common labeled statistics result form. It additionally accepts `storage=<bool>` to select storage-energy capacity.

## `velmora.Network.statistics.expanded_capacity`

`statistics.expanded_capacity(**kwargs)` returns added nominal capacity through the common labeled statistics result form.

## `velmora.Network.statistics.capex`

`statistics.capex(**kwargs)` returns optimal capital expenditure through the common labeled statistics result form.

## `velmora.Network.statistics.installed_capex`

`statistics.installed_capex(**kwargs)` returns installed capital expenditure through the common labeled statistics result form.

## `velmora.Network.statistics.expanded_capex`

`statistics.expanded_capex(**kwargs)` returns change in capital expenditure through the common labeled statistics result form.

## `velmora.Network.statistics.overnight_cost`

`statistics.overnight_cost(**kwargs)` returns overnight investment expenditure through the common labeled statistics result form.

## `velmora.Network.statistics.fom`

`statistics.fom(**kwargs)` returns fixed operating and maintenance expenditure through the common labeled statistics result form.

## `velmora.Network.statistics.opex`

`statistics.opex(**kwargs)` returns operating expenditure through the common labeled statistics result form. It additionally accepts `cost_types=<sequence of strings>`. Cost-type selectors used here are `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `marginal_cost_storage` and `spill_cost`.

## `velmora.Network.statistics.system_cost`

`statistics.system_cost(**kwargs)` returns system cost through the common labeled statistics result form.

## `velmora.Network.statistics.supply`

`statistics.supply(**kwargs)` returns energy supply through the common labeled statistics result form.

## `velmora.Network.statistics.withdrawal`

`statistics.withdrawal(**kwargs)` returns energy withdrawal through the common labeled statistics result form.

## `velmora.Network.statistics.energy_balance`

`statistics.energy_balance(**kwargs)` returns signed energy balance through the common labeled statistics result form.

## `velmora.Network.statistics.curtailment`

`statistics.curtailment(**kwargs)` returns curtailed generation through the common labeled statistics result form.

## `velmora.Network.statistics.capacity_factor`

`statistics.capacity_factor(**kwargs)` returns capacity utilisation through the common labeled statistics result form.

## `velmora.Network.statistics.revenue`

`statistics.revenue(**kwargs)` returns energy revenue through the common labeled statistics result form.

## `velmora.Network.statistics.market_value`

`statistics.market_value(**kwargs)` returns market value per unit operation through the common labeled statistics result form.

## `velmora.Network.statistics.transmission`

`statistics.transmission(**kwargs)` returns signed transmission quantity through the common labeled statistics result form.

## `velmora.Network.statistics.prices`

`statistics.prices(groupby=<False or grouping string>, weighting=<str>, groupby_time=<bool>)` returns a numeric Series indexed by bus name or requested bus group, or a bus-by-snapshot DataFrame with time retained. `weighting` spellings are `load` and `time`. Grouping uses `bus_carrier`.

## `velmora.Network.cluster`

`cluster` exposes `spatial` and `temporal` accessors on Network.

## `velmora.Network.cluster.spatial.get_clustering_from_busmap`

`get_clustering_from_busmap(busmap, aggregate_generators_weighted=<bool>, aggregate_generators_carriers=<sequence>, aggregate_one_ports=<sequence>, generator_strategies=<mapping>, custom_line_groupers=<sequence>, line_length_factor=<number>, scale_link_capital_costs=<bool>)` is callable through `cluster.spatial`. `busmap` is a pandas Series indexed by original bus labels with aggregate bus labels as values. Carrier and component selections use their string names. Strategy mappings associate attribute names with aggregation-operation names such as `max`; line groupers are static attribute names.

The returned object exposes `n`, the aggregate Network; `busmap`, a source-bus-to-result-bus Series; and `linemap`, a Series indexed by retained source lines with aggregate line identities as values. The aggregate network uses the public component-table forms. Refused aggregation raises `ValueError`.

## `velmora.Network.cluster.spatial.busmap_by_kmeans`

`busmap_by_kmeans(bus_weightings, n_clusters=<int>, random_state=<int>)` is available through `cluster.spatial`; bus_weightings is a numeric Series indexed by selected source buses. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `velmora.Network.cluster.spatial.busmap_by_hac`

`busmap_by_hac(n_clusters=<int>, feature=<DataFrame>, buses_i=<optional Index>)` is available through `cluster.spatial`; feature is a bus-indexed feature table and buses_i identifies the selected buses. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `velmora.Network.cluster.spatial.busmap_by_greedy_modularity`

`busmap_by_greedy_modularity(n_clusters=<int>)` is available through `cluster.spatial`; n_clusters is the requested group count. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `velmora.Network.cluster.temporal.get_resample_result`

`get_resample_result(offset, aggregation_rules=<optional mapping>)` is available through `cluster.temporal`; offset is a resampling-interval string. `aggregation_rules` maps attribute names to aggregation-operation strings, including `sum`, `mean`, `min` and `max`. The result exposes `n`, a Network with representative snapshots and the public component and weighting tables, and `snapshot_map`, a Series indexed by original snapshots with representative snapshot labels as values. Unsupported network forms raise `NotImplementedError`.

## `velmora.Network.cluster.temporal.get_downsample_result`

`get_downsample_result(stride)` is available through `cluster.temporal`; stride is an integer snapshot stride. The result exposes `n`, a Network with representative snapshots and the public component and weighting tables, and `snapshot_map`, a Series indexed by original snapshots with representative snapshot labels as values. Unsupported network forms raise `NotImplementedError`. Refused arguments raise `ValueError`.

## `velmora.Network.cluster.temporal.get_from_snapshot_map_result`

`get_from_snapshot_map_result(snapshot_map, aggregation_rules=<optional mapping>)` is available through `cluster.temporal`; snapshot_map is a Series indexed by source snapshots with representative labels as values. `aggregation_rules` maps attribute names to aggregation-operation strings, including `sum`, `mean`, `min` and `max`. The result exposes `n`, a Network with representative snapshots and the public component and weighting tables, and `snapshot_map`, a Series indexed by original snapshots with representative snapshot labels as values. Unsupported network forms raise `NotImplementedError`. Refused arguments raise `ValueError`.

## `velmora.Network.cluster.temporal.get_segment_result`

`get_segment_result(num_segments, exclude_attrs=<optional list of strings>)` is available through `cluster.temporal`; num_segments is an integer segment count and exclude_attrs identifies attributes. The result exposes `n`, a Network with representative snapshots and the public component and weighting tables, and `snapshot_map`, a Series indexed by original snapshots with representative snapshot labels as values. Unsupported network forms raise `NotImplementedError`. Refused arguments raise `ValueError`. Unavailable optional segmentation support raises `ModuleNotFoundError` with nonempty explanatory text.

## `velmora.Network.plot`

`plot(ax=<Axes>, geomap=<bool>, bus_size=<Series>, bus_color=<str or Series>, bus_cmap=<str>, bus_cmap_norm=<Normalize>, auto_scale_branches=<bool>, line_flow=<snapshot>, line_width=<number>, line_color=<str>, transformer_flow=<snapshot>, transformer_width=<number>, transformer_color=<str>, link_flow=<snapshot>, link_width=<number>, link_color=<str>)` accepts geographic display choices. A bus-size Series is indexed by bus or by `(bus, carrier)` for composition. Numeric bus colours are bus-indexed; `bus_cmap_norm` exposes the requested colour normalisation.

The return is a dictionary with `nodes`, `branches` and `flows`, each keyed by component category. `nodes['Bus']` exposes bus paths and face colours. `branches` exposes `Line`, `Transformer` and `Link` collections; `get_segments()` returns coordinate arrays, `get_linewidths()` numeric widths and `get_colors()` RGBA rows. `flows` exposes branch-arrow collections. `get_paths()` returns paths with numeric `vertices` arrays of coordinate pairs. `get_facecolors()` returns matching RGBA rows for bus paths. RGBA rows contain red, green, blue and alpha channels.

## `velmora.Network.explore`

`explore(tooltip=<bool>, bus_size=<Series>, bus_alpha=<number>, bus_color=<str>, line_flow=<Series>, line_width=<Series>, line_color=<str>, transformer_flow=<Series>, transformer_width=<Series>, transformer_color=<str>, link_flow=<Series>, link_width=<Series>, link_color=<str>)` returns an interactive geographic object. Bus-size Series use bus labels or `(bus, carrier)` pairs; branch Series use asset names.

The result exposes `layers`. Each layer exposes `type` and `data`, a list of records. `ScatterplotLayer` bus records expose numeric `x`, `y` and `size`. `PathLayer` branch records expose string `name`, `bus0`, `bus1`, numeric-coordinate `path`, numeric `width` and colour-channel array `rgba`. `PolygonLayer` arrow records expose `name`, signed numeric `flow_pdk` and `arrow` as a coordinate sequence. Composition records in `PolygonLayer` expose carrier `label`, numeric `size`, RGBA `color` and coordinate sequence `polygon`; a composition polygon starts and ends at the bus location, with its arc vertices in between. Interactive colour channels use integer values from `0` through `255`.

## `velmora.Network.statistics.installed_capacity.plot.bar`

`statistics.installed_capacity.plot.bar(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>, query=<optional expression string>)` is available on Network and NetworkCollection. Column selectors include `carrier` and `value`. A facet dimension is a caller-supplied collection-index level name. It returns `(Figure, Axes, FacetGrid)`; with facets the Axes position is an array of axes. The grid exposes `data`, a DataFrame with `carrier`, numeric `value` and collection dimension columns when applicable; `axes_dict` maps facet labels to their axes. The metric-axis label is `Installed Capacity [MW]`. Axes expose `patches` with numeric `get_height()`, `get_x()` and `get_width()`; `get_xticks()` returns matching numeric tick positions; `get_xticklabels()` and `get_yticklabels()` expose label objects with `get_text()`. Axes expose `get_ylabel()` for their metric label. A refused plotting consistency check raises `ConsistencyError`.

## `velmora.Network.statistics.installed_capacity.plot.line`

`statistics.installed_capacity.plot.line(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>)` is available on Network and NetworkCollection. Column selectors include `carrier` and `value`. A facet dimension is a caller-supplied collection-index level name. It returns `(Figure, Axes, FacetGrid)`; with facets the Axes position is an array of axes. The grid exposes `data`, a DataFrame with `carrier`, numeric `value` and collection dimension columns when applicable; `axes_dict` maps facet labels to their axes. The metric-axis label is `Installed Capacity [MW]`. Axes expose `lines` with `get_ydata()` and `get_color()`. Axes expose `get_ylabel()` for their metric label.

## `velmora.Network.statistics.installed_capacity.plot.scatter`

`statistics.installed_capacity.plot.scatter(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>)` is available on Network and NetworkCollection. Column selectors include `carrier` and `value`. A facet dimension is a caller-supplied collection-index level name. It returns `(Figure, Axes, FacetGrid)`; with facets the Axes position is an array of axes. The grid exposes `data`, a DataFrame with `carrier`, numeric `value` and collection dimension columns when applicable; `axes_dict` maps facet labels to their axes. The metric-axis label is `Installed Capacity [MW]`. Axes expose `collections` whose `get_offsets()` returns plotted coordinate pairs. Axes expose `get_ylabel()` for their metric label.

## `velmora.Network.statistics.installed_capacity.plot.box`

`statistics.installed_capacity.plot.box(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>)` is available on Network and NetworkCollection. Column selectors include `carrier` and `value`. A facet dimension is a caller-supplied collection-index level name. It returns `(Figure, Axes, FacetGrid)`; with facets the Axes position is an array of axes. The grid exposes `data`, a DataFrame with `carrier`, numeric `value` and collection dimension columns when applicable; `axes_dict` maps facet labels to their axes. The metric-axis label is `Installed Capacity [MW]`. Axes expose rendered artists through `lines`, `patches` and `collections`. Axes expose `get_ylabel()` for their metric label.

## `velmora.Network.statistics.installed_capacity.plot.violin`

`statistics.installed_capacity.plot.violin(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>)` is available on Network and NetworkCollection. Column selectors include `carrier` and `value`. A facet dimension is a caller-supplied collection-index level name. It returns `(Figure, Axes, FacetGrid)`; with facets the Axes position is an array of axes. The grid exposes `data`, a DataFrame with `carrier`, numeric `value` and collection dimension columns when applicable; `axes_dict` maps facet labels to their axes. The metric-axis label is `Installed Capacity [MW]`. Axes expose rendered artists through `lines`, `patches` and `collections`. Axes expose `get_ylabel()` for their metric label.

## `velmora.Network.statistics.installed_capacity.plot.histogram`

`statistics.installed_capacity.plot.histogram(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>)` is available on Network and NetworkCollection. Column selectors include `carrier` and `value`. A facet dimension is a caller-supplied collection-index level name. It returns `(Figure, Axes, FacetGrid)`; with facets the Axes position is an array of axes. The grid exposes `data`, a DataFrame with `carrier`, numeric `value` and collection dimension columns when applicable; `axes_dict` maps facet labels to their axes. The metric-axis label is `Installed Capacity [MW]`. Axes expose rendered artists through `lines`, `patches` and `collections`. Axes expose `get_ylabel()` for their metric label.

## `velmora.Network.statistics.supply.plot.area`

`statistics.supply.plot.area(components=<sequence>, facet_col=<optional dimension name>)` is available on Network and NetworkCollection. It returns `(Figure, Axes, FacetGrid)`, with an array of axes for facets. `data` on the grid has `carrier`, `snapshot`, numeric `value` and collection-dimension columns when applicable. `axes_dict` maps facet labels to axes. Axis `collections` expose paths via `get_paths()` and their numeric coordinate-pair `vertices`, and fill colours as RGBA rows via `get_facecolors()`. Snapshot positions are exposed by matching `get_xticks()` and `get_xticklabels()`, with label text read through `get_text()`.

## `velmora.Network.statistics.installed_capacity.plot.map`

`statistics.installed_capacity.plot.map(geomap=<bool>, carrier=<sequence of strings>, bus_carrier=<str>)` on Network returns `(Figure, Axes)`. The Figure exposes Legend objects through `get_children()`; each legend exposes text through `get_texts()` and `get_text()`. Axes expose `collections`, including coloured PatchCollection paths with `get_paths()`, numeric coordinate-pair `vertices` and corresponding `get_facecolors()` RGBA rows.

## `velmora.Network.statistics.installed_capacity.iplot.bar`

`statistics.installed_capacity.iplot.bar(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>, col_order=<optional label sequence>)` is available on Network and NetworkCollection. Column selectors include `carrier` and `value`. It returns a Figure with `data` traces exposing `type`, `x`, `y` and `xaxis`. The trace type is `bar`. The metric-axis title is read from `layout.yaxis.title.text` and is `Installed Capacity [MW]`. Facet annotations expose `text` of form `<dimension>=<member>` through `layout.annotations`. `col_order` associates successive facet labels with x-axis identifiers `x` and `x2`.

## `velmora.Network.statistics.installed_capacity.iplot.line`

`statistics.installed_capacity.iplot.line(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>, col_order=<optional label sequence>)` is available on Network and NetworkCollection. Column selectors include `carrier` and `value`. It returns a Figure with `data` traces exposing `type`, `x`, `y` and `xaxis`. The trace type is `scatter`. The metric-axis title is read from `layout.yaxis.title.text` and is `Installed Capacity [MW]`. Facet annotations expose `text` of form `<dimension>=<member>` through `layout.annotations`. `col_order` associates successive facet labels with x-axis identifiers `x` and `x2`.

## `velmora.Network.statistics.supply.iplot.area`

`statistics.supply.iplot.area(components=<sequence>, x=<column name>, y=<column name>, color=<column name>, facet_col=<optional dimension name>, col_order=<optional label sequence>)` is available on Network and NetworkCollection. Column selectors include `snapshot`, `value` and `carrier`. The Figure's `data` traces expose `type` as `scatter`, `name` as the category label, `x` as snapshot coordinates, `y` as numeric supply, `xaxis` as facet-axis identity, and `stackgroup` with spelling `positive` for the positive stack. `col_order` associates successive facet labels with `x` and `x2`.

## `Network`

Stated under `velmora.Network`.

## `NetworkCollection`

Stated under `velmora.NetworkCollection`.

## `WARNING`

Public component data uses pandas labeled tables; selectors and assignments use their `loc`, `at`, `iloc`, `index` and `columns` interfaces.

Consistency diagnostics are Python logging records. Their public carriers include `levelno` and `name`; warning diagnostics have level `WARNING` on `velmora.consistency`.

Optimisation batch diagnostics use `velmora.optimization.mga` and a `WARNING` or higher level.

Static graphical paths expose `vertices` as numeric coordinate pairs and `codes` as either `None` for a connected straight path or a matching integer array. Path codes use `1` for a subpath start, `2` for a line endpoint, `3` for quadratic-curve control and endpoint pairs, `4` for cubic-curve control/control/endpoint triples, `79` for subpath closure and `0` for path termination. Filled boundaries include the closing edge of each subpath.

## `at`

Stated under `WARNING`.

## `columns`

Stated under `WARNING`.

## `iloc`

Stated under `WARNING`.

## `index`

Stated under `WARNING`.

## `levelno`

Stated under `WARNING`.

## `loc`

Stated under `WARNING`.

## `name`

Stated under `WARNING`.

## `velmora.optimization.mga`

Stated under `WARNING`.

## `attribute`

Stated under `excel`.

## `buses`

`determine_network_topology()` exposes subnetwork identifiers through `c.buses.static` column `sub_network`.

## `generators`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `lines`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `links`

Stated under `excel`.

## `loads`

Stated under `excel`.

## `marginal_cost`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `objective`

`set_risk_preference(alpha=<float>, omega=<float>)` accepts confidence and risk weight. Refusal raises `ValueError`, either from this binding call or the subsequent optimisation. Results are exposed by scenario-labeled solved tables and scalar `objective`.

## `p_pu`

Stated under `excel`.

## `period`

Stated under `velmora.Network`.

## `snapshot`

Stated under `velmora.Network.optimize.optimize_with_rolling_horizon`.

## `storage_units`

Stated under `excel`.

## `stores`

Stated under `velmora.Network`.

## `transformers`

Stated under `excel`.

## `meta.json`

Stated under `csv_folder`.

## `export_to_excel`

Stated under `velmora.Network.export_to_excel`.

## `breakpoint`

Stated under `excel`.

## `snapshots`

`import_from_hdf5(path)` accepts a caller-supplied string or path object naming a file. The operation exposes the imported network through component tables, `name`, `meta`, `snapshots` and weight tables.

## `/network`

Stated under `hdf5`.

## `/snapshots`

Stated under `hdf5`.

## `export_to_netcdf`

`export_to_netcdf(path)` accepts a caller-supplied string or path object naming a file. The operation writes the network in the named format. Results are read from the written data.

## `_crs`

Stated under `netcdf`.

## `buses_i`

`busmap_by_hac(n_clusters=<int>, feature=<DataFrame>, buses_i=<optional Index>)` is available through `cluster.spatial`; feature is a bus-indexed feature table and buses_i identifies the selected buses. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `buses_v_nom`

Stated under `netcdf`.

## `crs`

Stated under `velmora.Network`.

## `generators_bus`

Stated under `netcdf`.

## `generators_i`

Stated under `netcdf`.

## `generators_p_nom`

Stated under `netcdf`.

## `generators_pw_marginal_cost`

Stated under `netcdf`.

## `generators_pw_marginal_cost_attr_i`

Stated under `netcdf`.

## `generators_pw_marginal_cost_i`

Stated under `netcdf`.

## `investment_periods_years`

Stated under `netcdf`.

## `loads_bus`

Stated under `netcdf`.

## `loads_i`

Stated under `netcdf`.

## `loads_t_p_set`

Stated under `netcdf`.

## `loads_t_p_set_i`

Stated under `netcdf`.

## `meta`

`copy()` returns a `Network`, including its public component tables, `name` and `meta`.

## `scenario`

`get_scenario(scenario)` accepts a scenario-name string and returns a `Network`, with readable `has_scenarios`, component tables, snapshots and weights.

## `scenario_weight`

Stated under `netcdf`.

## `shapes_geometry`

Stated under `netcdf`.

## `shapes_i`

Stated under `netcdf`.

## `snapshots_generators`

Stated under `netcdf`.

## `snapshots_objective`

Stated under `netcdf`.

## `snapshots_period`

Stated under `netcdf`.

## `snapshots_snapshot`

Stated under `netcdf`.

## `snapshots_stores`

Stated under `netcdf`.

## `cluster`

`cluster` exposes `spatial` and `temporal` accessors on Network.

## `explore`

Stated under `velmora.Network.explore`.

## `has_scenarios`

`get_scenario(scenario)` accepts a scenario-name string and returns a `Network`, with readable `has_scenarios`, component tables, snapshots and weights.

## `investment_period_weightings`

Stated under `velmora.Network.slice_network`.

## `model`

Stated under `velmora.Network.model`.

## `optimize`

Stated under `velmora.Network.optimize`.

## `periods`

Stated under `velmora.Network.slice_network`.

## `plot`

Stated under `velmora.Network.plot`.

## `scenario_weightings`

Stated under `velmora.Network.set_scenarios`.

## `scenarios`

Stated under `velmora.Network.set_scenarios`.

## `snapshot_weightings`

`merge(other, with_time=<bool>)` accepts another `Network` and returns a `Network`. The returned component tables, `name`, `meta`, `snapshots`, `snapshot_weightings`, `line_types` and `transformer_types` are readable. A rejected merge raises `ValueError`.

## `statistics`

Stated under `velmora.Network.statistics`.

## `weight`

Stated under `velmora.Network`.

## `years`

Stated under `velmora.Network.slice_network`.

## `add`

Stated under `velmora.Network.add`.

## `adjacency_matrix`

Stated under `velmora.Network.adjacency_matrix`.

## `DataFrame`

`busmap_by_hac(n_clusters=<int>, feature=<DataFrame>, buses_i=<optional Index>)` is available through `cluster.spatial`; feature is a bus-indexed feature table and buses_i identifies the selected buses. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `Index`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `branch_components`

Stated under `velmora.Network.incidence_matrix`.

## `busorder`

Stated under `velmora.Network.incidence_matrix`.

## `return_dataframe`

Stated under `velmora.Network.adjacency_matrix`.

## `Bus`

Stated under `velmora.Network.plot`.

## `Carrier`

Stated under `velmora.Network.c`.

## `Generator`

Stated under `velmora.Network.model`.

## `GlobalConstraint`

Stated under `velmora.Network.c`.

## `Line`

Stated under `velmora.Network.plot`.

## `LineType`

Stated under `velmora.Network.c`.

## `Link`

Stated under `velmora.Network.plot`.

## `Load`

Stated under `velmora.Network.c`.

## `Process`

Stated under `velmora.Network.c`.

## `Shape`

Stated under `velmora.Network.c`.

## `ShuntImpedance`

Stated under `velmora.Network.c`.

## `StorageUnit`

Stated under `velmora.Network.c`.

## `Store`

Stated under `velmora.Network.c`.

## `Transformer`

Stated under `velmora.Network.plot`.

## `TransformerType`

Stated under `velmora.Network.c`.

## `AC`

Stated under `velmora.Network.c`.

## `DC`

Stated under `velmora.Network.c`.

## `MultiIndex`

Stated under `velmora.Network`.

## `PQ`

Stated under `velmora.Network.c`.

## `PV`

Stated under `velmora.Network.c`.

## `Slack`

Stated under `velmora.Network.c`.

## `active`

Stated under `velmora.Network.c`.

## `b`

Stated under `velmora.Network.c`.

## `build_year`

Stated under `velmora.Network.c`.

## `bus`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `bus0`

Stated under `velmora.Network.incidence_matrix`.

## `bus1`

Stated under `velmora.Network.incidence_matrix`.

## `bus2`

Stated under `velmora.Network.c`.

## `bus3`

Stated under `velmora.Network.c`.

## `c`

Stated under `velmora.Network.c`.

## `c_per_length`

Stated under `velmora.Network.c`.

## `capital_cost`

Stated under `velmora.Network.c`.

## `capital_cost_piecewise_opt`

Stated under `velmora.Network.c`.

## `carrier`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `carrier_attribute`

Stated under `velmora.Network.c`.

## `carriers`

Stated under `velmora.Network.c`.

## `co2_emissions`

Stated under `velmora.Network.c`.

## `color`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `committable`

Stated under `velmora.Network.c`.

## `component`

`components` exposes the same category-selection interface and component tables as `c`; `components[<component>]` uses the component class name or list name.

## `components`

`components` exposes the same category-selection interface and component tables as `c`; `components[<component>]` uses the component class name or list name.

## `constant`

Stated under `velmora.Network.c`.

## `control`

Stated under `velmora.Network.c`.

## `country`

Stated under `velmora.Network.statistics`.

## `cyclic_delay`

Stated under `velmora.Network.c`.

## `cyclic_delay1`

Stated under `velmora.Network.c`.

## `cyclic_state_of_charge`

Stated under `velmora.Network.c`.

## `delay`

Stated under `velmora.Network.c`.

## `delay0`

Stated under `velmora.Network.c`.

## `delay1`

Stated under `velmora.Network.c`.

## `delay2`

Stated under `velmora.Network.c`.

## `description`

Stated under `velmora.Network.c`.

## `discount_rate`

`annuity(discount_rate, lifetime)` is importable from `velmora.costs`. For scalar numeric inputs it returns a numeric annual financing factor multiplying overnight cost. Refused lifetime input raises `ValueError`.

## `down_time_before`

Stated under `velmora.Network.c`.

## `dynamic`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `e`

Stated under `velmora.Network.c`.

## `e_cyclic`

Stated under `velmora.Network.c`.

## `e_initial`

Stated under `velmora.Network.c`.

## `e_max_pu`

Stated under `velmora.Network.c`.

## `e_min_pu`

Stated under `velmora.Network.c`.

## `e_nom`

`fix_optimal_capacities()` exposes fixed nominal capacities and investment flags through component `static` columns `p_nom`, `e_nom`, `s_nom`, `p_nom_extendable`, `e_nom_extendable` and `s_nom_extendable`.

## `e_nom_extendable`

`fix_optimal_capacities()` exposes fixed nominal capacities and investment flags through component `static` columns `p_nom`, `e_nom`, `s_nom`, `p_nom_extendable`, `e_nom_extendable` and `s_nom_extendable`.

## `e_nom_max`

Stated under `velmora.Network.c`.

## `e_nom_min`

Stated under `velmora.Network.c`.

## `e_nom_mod`

Stated under `velmora.Network.c`.

## `e_nom_opt`

Stated under `velmora.Network.c`.

## `e_nom_set`

Stated under `velmora.Network.c`.

## `e_set`

Stated under `velmora.Network.c`.

## `e_sum_max`

Stated under `velmora.Network.c`.

## `e_sum_min`

Stated under `velmora.Network.c`.

## `efficiency`

Stated under `velmora.Network.c`.

## `efficiency2`

Stated under `velmora.Network.c`.

## `efficiency3`

Stated under `velmora.Network.c`.

## `efficiency_dispatch`

Stated under `velmora.Network.c`.

## `efficiency_store`

Stated under `velmora.Network.c`.

## `f_nom`

Stated under `velmora.Network.c`.

## `fom_cost`

Stated under `velmora.Network.c`.

## `g`

Stated under `velmora.Network.c`.

## `geometry`

Stated under `velmora.Network.c`.

## `global_constraints`

Stated under `velmora.Network.c`.

## `i0`

Stated under `velmora.Network.c`.

## `idx`

Stated under `velmora.Network.c`.

## `inflow`

Stated under `velmora.Network.c`.

## `investment_period`

Stated under `velmora.Network.c`.

## `length`

Stated under `velmora.Network.c`.

## `lifetime`

`annuity(discount_rate, lifetime)` is importable from `velmora.costs`. For scalar numeric inputs it returns a numeric annual financing factor multiplying overnight cost. Refused lifetime input raises `ValueError`.

## `line_types`

`merge(other, with_time=<bool>)` accepts another `Network` and returns a `Network`. The returned component tables, `name`, `meta`, `snapshots`, `snapshot_weightings`, `line_types` and `transformer_types` are readable. A rejected merge raises `ValueError`.

## `location`

Stated under `velmora.Network.statistics`.

## `maintainable`

Stated under `velmora.Network.c`.

## `maintenance`

Stated under `velmora.Network.consistency_check`.

## `maintenance_duration`

Stated under `velmora.Network.c`.

## `maintenance_events`

Stated under `velmora.Network.c`.

## `maintenance_pu`

Stated under `velmora.Network.c`.

## `maintenance_start`

Stated under `velmora.Network.c`.

## `marginal_cost_piecewise_opt`

Stated under `velmora.Network.c`.

## `marginal_cost_quadratic`

Stated under `velmora.Network.c`.

## `marginal_cost_storage`

`statistics.opex(**kwargs)` returns operating expenditure through the common labeled statistics result form. It additionally accepts `cost_types=<sequence of strings>`. Cost-type selectors used here are `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `marginal_cost_storage` and `spill_cost`.

## `marginal_price`

Stated under `velmora.Network.c`.

## `max_growth`

Stated under `velmora.Network.c`.

## `max_hours`

Stated under `velmora.Network.c`.

## `max_relative_growth`

Stated under `velmora.Network.c`.

## `min_down_time`

Stated under `velmora.Network.c`.

## `min_up_time`

Stated under `velmora.Network.c`.

## `mu`

Stated under `velmora.Network.c`.

## `mu_upper`

Stated under `velmora.Network.c`.

## `nice_name`

Stated under `velmora.Network.c`.

## `num_parallel`

Stated under `velmora.Network.c`.

## `obj`

Stated under `velmora.Network.c`.

## `operational_limit`

Stated under `velmora.Network.c`.

## `overnight_cost`

`statistics.overnight_cost(**kwargs)` returns overnight investment expenditure through the common labeled statistics result form.

## `p`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `p0`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `p1`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `p2`

Stated under `velmora.Network.c`.

## `p3`

Stated under `velmora.Network.c`.

## `p_dispatch`

Stated under `velmora.Network.c`.

## `p_dispatch_set`

Stated under `velmora.Network.c`.

## `p_init`

Stated under `velmora.Network.c`.

## `p_max_pu`

Stated under `velmora.Network.c`.

## `p_min_pu`

Stated under `velmora.Network.c`.

## `p_nom`

`fix_optimal_capacities()` exposes fixed nominal capacities and investment flags through component `static` columns `p_nom`, `e_nom`, `s_nom`, `p_nom_extendable`, `e_nom_extendable` and `s_nom_extendable`.

## `p_nom_extendable`

`fix_optimal_capacities()` exposes fixed nominal capacities and investment flags through component `static` columns `p_nom`, `e_nom`, `s_nom`, `p_nom_extendable`, `e_nom_extendable` and `s_nom_extendable`.

## `p_nom_max`

Stated under `velmora.Network.c`.

## `p_nom_min`

Stated under `velmora.Network.c`.

## `p_nom_mod`

Stated under `velmora.Network.c`.

## `p_nom_opt`

Stated under `velmora.Network.pf`.

## `p_nom_set`

Stated under `velmora.Network.c`.

## `p_set`

Stated under `velmora.Network.pf`.

## `p_store`

Stated under `velmora.Network.c`.

## `p_store_set`

Stated under `velmora.Network.c`.

## `pfe`

Stated under `velmora.Network.c`.

## `phase_shift`

Stated under `velmora.Network.c`.

## `phase_shift_max`

Stated under `velmora.Network.c`.

## `phase_shift_min`

Stated under `velmora.Network.c`.

## `phase_shift_opt`

Stated under `velmora.Network.c`.

## `pi`

Stated under `velmora.Network.c`.

## `piecewise`

Stated under `velmora.Network.c`.

## `primary_energy`

Stated under `velmora.Network.c`.

## `processes`

Stated under `velmora.Network.c`.

## `q`

Stated under `velmora.Network.c`.

## `q_set`

Stated under `velmora.Network.c`.

## `r`

Stated under `velmora.Network.c`.

## `r_per_length`

Stated under `velmora.Network.c`.

## `ramp_limit_down`

Stated under `velmora.Network.c`.

## `ramp_limit_shut_down`

Stated under `velmora.Network.c`.

## `ramp_limit_start_up`

Stated under `velmora.Network.c`.

## `ramp_limit_up`

Stated under `velmora.Network.c`.

## `rate0`

Stated under `velmora.Network.c`.

## `rate1`

Stated under `velmora.Network.c`.

## `rate2`

Stated under `velmora.Network.c`.

## `rate3`

Stated under `velmora.Network.c`.

## `s_max_pu`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `s_min_pu`

Stated under `velmora.Network.c`.

## `s_nom`

`fix_optimal_capacities()` exposes fixed nominal capacities and investment flags through component `static` columns `p_nom`, `e_nom`, `s_nom`, `p_nom_extendable`, `e_nom_extendable` and `s_nom_extendable`.

## `s_nom_extendable`

`fix_optimal_capacities()` exposes fixed nominal capacities and investment flags through component `static` columns `p_nom`, `e_nom`, `s_nom`, `p_nom_extendable`, `e_nom_extendable` and `s_nom_extendable`.

## `s_nom_max`

Stated under `velmora.Network.c`.

## `s_nom_min`

Stated under `velmora.Network.c`.

## `s_nom_mod`

Stated under `velmora.Network.c`.

## `s_nom_opt`

Stated under `velmora.Network.c`.

## `s_nom_set`

Stated under `velmora.Network.c`.

## `sense`

Stated under `velmora.Network.optimize.optimize_mga`.

## `shapes`

Stated under `velmora.Network.c`.

## `shunt_impedances`

Stated under `velmora.Network.c`.

## `shut_down`

Stated under `velmora.Network.c`.

## `shut_down_cost`

`statistics.opex(**kwargs)` returns operating expenditure through the common labeled statistics result form. It additionally accepts `cost_types=<sequence of strings>`. Cost-type selectors used here are `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `marginal_cost_storage` and `spill_cost`.

## `sign`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `slack_generator`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `spill`

Stated under `velmora.Network.c`.

## `spill_cost`

`statistics.opex(**kwargs)` returns operating expenditure through the common labeled statistics result form. It additionally accepts `cost_types=<sequence of strings>`. Cost-type selectors used here are `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `marginal_cost_storage` and `spill_cost`.

## `stand_by_cost`

`statistics.opex(**kwargs)` returns operating expenditure through the common labeled statistics result form. It additionally accepts `cost_types=<sequence of strings>`. Cost-type selectors used here are `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `marginal_cost_storage` and `spill_cost`.

## `standing_loss`

Stated under `velmora.Network.c`.

## `start_up`

Stated under `velmora.Network.c`.

## `start_up_cost`

`statistics.opex(**kwargs)` returns operating expenditure through the common labeled statistics result form. It additionally accepts `cost_types=<sequence of strings>`. Cost-type selectors used here are `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `marginal_cost_storage` and `spill_cost`.

## `state_of_charge`

Stated under `velmora.Network.c`.

## `state_of_charge_initial`

Stated under `velmora.Network.c`.

## `state_of_charge_set`

Stated under `velmora.Network.c`.

## `static`

`determine_network_topology()` exposes subnetwork identifiers through `c.buses.static` column `sub_network`.

## `status`

Stated under `velmora.Network.optimize.optimize_mga_in_direction`.

## `sub_network`

`determine_network_topology()` exposes subnetwork identifiers through `c.buses.static` column `sub_network`.

## `sub_networks`

Stated under `velmora.Network.c`.

## `t`

Stated under `velmora.Network.c`.

## `tap_neutral`

Stated under `velmora.Network.c`.

## `tap_position`

Stated under `velmora.Network.c`.

## `tap_ratio`

Stated under `velmora.Network.c`.

## `tap_side`

Stated under `velmora.Network.c`.

## `tap_step`

Stated under `velmora.Network.c`.

## `tech_capacity_expansion_limit`

Stated under `velmora.Network.c`.

## `terrain_factor`

Stated under `velmora.Network.c`.

## `transformer_types`

`merge(other, with_time=<bool>)` accepts another `Network` and returns a `Network`. The returned component tables, `name`, `meta`, `snapshots`, `snapshot_weightings`, `line_types` and `transformer_types` are readable. A rejected merge raises `ValueError`.

## `transmission_expansion_cost_limit`

Stated under `velmora.Network.c`.

## `transmission_volume_expansion_limit`

Stated under `velmora.Network.c`.

## `type`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `unit`

Stated under `velmora.Network.statistics`.

## `up_time_before`

Stated under `velmora.Network.c`.

## `v_ang`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `v_ang_max`

Stated under `velmora.Network.c`.

## `v_ang_min`

Stated under `velmora.Network.c`.

## `v_mag_pu`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `v_mag_pu_max`

Stated under `velmora.Network.c`.

## `v_mag_pu_min`

Stated under `velmora.Network.c`.

## `v_mag_pu_set`

Stated under `velmora.Network.c`.

## `v_nom`

Stated under `velmora.Network.c`.

## `v_nom_0`

Stated under `velmora.Network.c`.

## `v_nom_1`

Stated under `velmora.Network.c`.

## `vsc`

Stated under `velmora.Network.c`.

## `vscr`

Stated under `velmora.Network.c`.

## `x`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `x_per_length`

Stated under `velmora.Network.c`.

## `y`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `<=`

Stated under `velmora.Network.model`.

## `==`

Stated under `velmora.Network.model`.

## `>=`

Stated under `velmora.Network.model`.

## `apply_seasonal_rating`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `KeyError`

`remove(class_name, name)` accepts a component-category string and one asset name or a sequence of names. Results are observed in the component tables. Removal refusal raises `KeyError`.

## `TypeError`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `ValueError`

`calculate_dependent_values()` exposes electrical values through line and transformer `static` tables. A refused electrical type raises `ValueError`.

## `c.lines.apply_seasonal_rating`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `c.lines.dynamic.s_max_pu`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `compose`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `ratings`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `summer`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `summer_months`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `winter`

Stated under `velmora.Network.c.lines.apply_seasonal_rating`.

## `calculate_dependent_values`

`calculate_dependent_values()` exposes electrical values through line and transformer `static` tables. A refused electrical type raises `ValueError`.

## `spatial`

`cluster` exposes `spatial` and `temporal` accessors on Network.

## `temporal`

`cluster` exposes `spatial` and `temporal` accessors on Network.

## `busmap_by_greedy_modularity`

`busmap_by_greedy_modularity(n_clusters=<int>)` is available through `cluster.spatial`; n_clusters is the requested group count. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `n_clusters`

`busmap_by_greedy_modularity(n_clusters=<int>)` is available through `cluster.spatial`; n_clusters is the requested group count. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `busmap_by_hac`

`busmap_by_hac(n_clusters=<int>, feature=<DataFrame>, buses_i=<optional Index>)` is available through `cluster.spatial`; feature is a bus-indexed feature table and buses_i identifies the selected buses. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `feature`

`busmap_by_hac(n_clusters=<int>, feature=<DataFrame>, buses_i=<optional Index>)` is available through `cluster.spatial`; feature is a bus-indexed feature table and buses_i identifies the selected buses. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `busmap_by_kmeans`

`busmap_by_kmeans(bus_weightings, n_clusters=<int>, random_state=<int>)` is available through `cluster.spatial`; bus_weightings is a numeric Series indexed by selected source buses. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `random_state`

`busmap_by_kmeans(bus_weightings, n_clusters=<int>, random_state=<int>)` is available through `cluster.spatial`; bus_weightings is a numeric Series indexed by selected source buses. It returns a pandas Series indexed by selected source bus labels, containing group labels.

## `get_clustering_from_busmap`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `aggregate_generators_carriers`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `aggregate_generators_weighted`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `aggregate_one_ports`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `busmap`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `custom_line_groupers`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `generator_strategies`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `line_length_factor`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `linemap`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `max`

Stated under `velmora.Network.cluster.temporal.get_resample_result`.

## `n`

Stated under `velmora.Network.cluster.temporal.get_downsample_result`.

## `scale_link_capital_costs`

Stated under `velmora.Network.cluster.spatial.get_clustering_from_busmap`.

## `get_downsample_result`

Stated under `velmora.Network.cluster.temporal.get_downsample_result`.

## `NotImplementedError`

`export_to_csv_folder(path)` accepts a caller-supplied string or path object naming a directory. The operation writes the network in the named format. Results are read from the written data. Unsupported export raises `NotImplementedError`.

## `snapshot_map`

Stated under `velmora.Network.cluster.temporal.get_downsample_result`.

## `stride`

Stated under `velmora.Network.cluster.temporal.get_downsample_result`.

## `get_from_snapshot_map_result`

Stated under `velmora.Network.cluster.temporal.get_from_snapshot_map_result`.

## `aggregation_rules`

Stated under `velmora.Network.cluster.temporal.get_resample_result`.

## `mean`

Stated under `velmora.Network.cluster.temporal.get_resample_result`.

## `min`

Stated under `velmora.Network.cluster.temporal.get_resample_result`.

## `sum`

Stated under `velmora.Network.optimize.expressions.opex`.

## `get_resample_result`

Stated under `velmora.Network.cluster.temporal.get_resample_result`.

## `get_segment_result`

Stated under `velmora.Network.cluster.temporal.get_segment_result`.

## `ModuleNotFoundError`

Stated under `velmora.Network.cluster.temporal.get_segment_result`.

## `exclude_attrs`

Stated under `velmora.Network.cluster.temporal.get_segment_result`.

## `consistency_check`

Stated under `velmora.Network.consistency_check`.

## `disconnected_buses`

Stated under `velmora.Network.consistency_check`.

## `dispatch_delays`

Stated under `velmora.Network.consistency_check`.

## `phase_shift_bounds`

Stated under `velmora.Network.consistency_check`.

## `scenario_invariant_attrs`

Stated under `velmora.Network.consistency_check`.

## `static_power_attrs`

Stated under `velmora.Network.consistency_check`.

## `strict`

`consistency_check_plots(strict=<sequence of check names>)` accepts the selector `missing_carrier_colors`. Refusal raises `ConsistencyError`.

## `time_series_power_attrs`

Stated under `velmora.Network.consistency_check`.

## `unknown_buses`

Stated under `velmora.Network.consistency_check`.

## `unknown_carriers`

Stated under `velmora.Network.consistency_check`.

## `zero_impedances`

Stated under `velmora.Network.consistency_check`.

## `consistency_check_plots`

`consistency_check_plots(strict=<sequence of check names>)` accepts the selector `missing_carrier_colors`. Refusal raises `ConsistencyError`.

## `ConsistencyError`

`ConsistencyError` is an exception class importable from `velmora.consistency`.

## `missing_carrier_colors`

`consistency_check_plots(strict=<sequence of check names>)` accepts the selector `missing_carrier_colors`. Refusal raises `ConsistencyError`.

## `copy`

`copy()` returns a `Network`, including its public component tables, `name` and `meta`.

## `determine_network_topology`

`determine_network_topology()` exposes subnetwork identifiers through `c.buses.static` column `sub_network`.

## `c.buses.static`

`determine_network_topology()` exposes subnetwork identifiers through `c.buses.static` column `sub_network`.

## `PathLayer`

Stated under `velmora.Network.explore`.

## `PolygonLayer`

Stated under `velmora.Network.explore`.

## `ScatterplotLayer`

Stated under `velmora.Network.explore`.

## `arrow`

Stated under `velmora.Network.explore`.

## `bus_alpha`

Stated under `velmora.Network.explore`.

## `bus_color`

Stated under `velmora.Network.explore`.

## `bus_size`

Stated under `velmora.Network.explore`.

## `data`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `flow_pdk`

Stated under `velmora.Network.explore`.

## `label`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `layers`

Stated under `velmora.Network.explore`.

## `path`

`export_to_netcdf(path)` accepts a caller-supplied string or path object naming a file. The operation writes the network in the named format. Results are read from the written data.

## `polygon`

Stated under `velmora.Network.explore`.

## `rgba`

Stated under `velmora.Network.explore`.

## `size`

Stated under `velmora.Network.explore`.

## `tooltip`

Stated under `velmora.Network.explore`.

## `width`

Stated under `velmora.Network.explore`.

## `ImportError`

Stated under `velmora.Network.export_to_excel`.

## `get_scenario`

`get_scenario(scenario)` accepts a scenario-name string and returns a `Network`, with readable `has_scenarios`, component tables, snapshots and weights.

## `get_switchable_as_dense`

`get_switchable_as_dense(component, attr)` accepts component-category and attribute strings and returns a pandas DataFrame indexed by snapshots with asset-name columns containing the effective attribute values.

## `import_from_pypower_ppc`

Stated under `velmora.Network.import_from_pypower_ppc`.

## `baseMVA`

Stated under `velmora.Network.import_from_pypower_ppc`.

## `branch`

Stated under `velmora.Network.import_from_pypower_ppc`.

## `gen`

Stated under `velmora.Network.import_from_pandapower_net`.

## `overwrite_zero_s_nom`

Stated under `velmora.Network.import_from_pypower_ppc`.

## `ppc`

Stated under `velmora.Network.import_from_pypower_ppc`.

## `version`

Stated under `velmora.Network.import_from_pypower_ppc`.

## `incidence_matrix`

Stated under `velmora.Network.incidence_matrix`.

## `toarray`

Stated under `velmora.Network.incidence_matrix`.

## `lpf`

`lpf(snapshots=<optional sequence>)` exposes results through component `dynamic` tables: bus `p`, `v_ang`, `v_mag_pu`; line and transformer `p0` and `p1`; generator and load `p`. Subnetwork objects expose `slack_generator`.

## `lpf_contingency`

Stated under `velmora.Network.lpf_contingency`.

## `base`

Stated under `velmora.Network.lpf_contingency`.

## `branch_outages`

Stated under `velmora.Network.lpf_contingency`.

## `merge`

`merge(other, with_time=<bool>)` accepts another `Network` and returns a `Network`. The returned component tables, `name`, `meta`, `snapshots`, `snapshot_weightings`, `line_types` and `transformer_types` are readable. A rejected merge raises `ValueError`.

## `with_time`

`merge(other, with_time=<bool>)` accepts another `Network` and returns a `Network`. The returned component tables, `name`, `meta`, `snapshots`, `snapshot_weightings`, `line_types` and `transformer_types` are readable. A rejected merge raises `ValueError`.

## `Generator-p`

Stated under `velmora.Network.model`.

## `add_constraints`

Stated under `velmora.Network.model`.

## `add_objective`

Stated under `velmora.Network.model`.

## `add_variables`

Stated under `velmora.Network.model`.

## `create_model`

`create_model(piecewise_options=<optional list of mappings>)` returns the editable model also available as `Network.model`.

## `expression`

Stated under `velmora.Network.model`.

## `lower`

Stated under `velmora.Network.model`.

## `objective.expression`

Stated under `velmora.Network.model`.

## `overwrite`

Stated under `velmora.Network.add`.

## `sel`

Stated under `velmora.Network.optimize.expressions.capacity`.

## `solution.item`

Stated under `velmora.Network.optimize.expressions.capacity`.

## `upper`

Stated under `velmora.Network.model`.

## `variables`

Stated under `velmora.Network.model`.

## `assign_all_duals`

Stated under `velmora.Network.optimize`.

## `atol`

Stated under `velmora.Network.optimize`.

## `cumulative_attr`

Stated under `velmora.Network.optimize`.

## `highs`

Stated under `velmora.Network.optimize`.

## `include_objective_constant`

Stated under `velmora.Network.optimize`.

## `linearized_unit_commitment`

Stated under `velmora.Network.optimize`.

## `mode`

Stated under `velmora.Network.optimize`.

## `multi_investment_periods`

Stated under `velmora.Network.optimize.optimize_security_constrained`.

## `piecewise_options`

`create_model(piecewise_options=<optional list of mappings>)` returns the editable model also available as `Network.model`.

## `rtol`

Stated under `velmora.Network.optimize`.

## `secants`

Stated under `velmora.Network.optimize`.

## `segments`

Stated under `velmora.Network.optimize`.

## `solver_name`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `solver_options`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `tangents`

Stated under `velmora.Network.optimize`.

## `threads`

Stated under `velmora.Network.optimize`.

## `transmission_losses`

Stated under `velmora.Network.optimize`.

## `infeasible`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `ok`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `optimal`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `warning`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `add_load_shedding`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `c.generators.dynamic.p`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `c.generators.static`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `suffix`

`add_load_shedding(suffix=<str>, buses=<Index>, sign=<number>, marginal_cost=<number>, p_nom=<number>)` exposes generator rows through `c.generators.static` and solved dispatch through `c.generators.dynamic.p`. Their names have the form `<bus><suffix>`.

## `capacity`

Stated under `velmora.Network.optimize.expressions.capacity`.

## `expressions`

Stated under `velmora.Network.optimize.expressions.capacity`.

## `group`

Stated under `velmora.Network.optimize.expressions.capacity`.

## `groupby`

`statistics.prices(groupby=<False or grouping string>, weighting=<str>, groupby_time=<bool>)` returns a numeric Series indexed by bus name or requested bus group, or a bus-by-snapshot DataFrame with time retained. `weighting` spellings are `load` and `time`. Grouping uses `bus_carrier`.

## `item`

Stated under `velmora.Network.optimize.expressions.capacity`.

## `nice_names`

Stated under `velmora.Network.optimize.expressions.capacity`.

## `solution`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `capex`

`statistics.capex(**kwargs)` returns optimal capital expenditure through the common labeled statistics result form.

## `curtailment`

`statistics.curtailment(**kwargs)` returns curtailed generation through the common labeled statistics result form.

## `groupby_time`

`statistics.prices(groupby=<False or grouping string>, weighting=<str>, groupby_time=<bool>)` returns a numeric Series indexed by bus name or requested bus group, or a bus-by-snapshot DataFrame with time retained. `weighting` spellings are `load` and `time`. Grouping uses `bus_carrier`.

## `energy_balance`

`statistics.energy_balance(**kwargs)` returns signed energy balance through the common labeled statistics result form.

## `at_port`

Stated under `velmora.Network.optimize.expressions.supply`.

## `bus_carrier`

`statistics.prices(groupby=<False or grouping string>, weighting=<str>, groupby_time=<bool>)` returns a numeric Series indexed by bus name or requested bus group, or a bus-by-snapshot DataFrame with time retained. `weighting` spellings are `load` and `time`. Grouping uses `bus_carrier`.

## `operation`

Stated under `velmora.Network.optimize.expressions.operation`.

## `opex`

`statistics.opex(**kwargs)` returns operating expenditure through the common labeled statistics result form. It additionally accepts `cost_types=<sequence of strings>`. Cost-type selectors used here are `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `marginal_cost_storage` and `spill_cost`.

## `supply`

`statistics.supply(**kwargs)` returns energy supply through the common labeled statistics result form.

## `transmission`

`statistics.transmission(**kwargs)` returns signed transmission quantity through the common labeled statistics result form.

## `withdrawal`

`statistics.withdrawal(**kwargs)` returns energy withdrawal through the common labeled statistics result form.

## `fix_optimal_capacities`

`fix_optimal_capacities()` exposes fixed nominal capacities and investment flags through component `static` columns `p_nom`, `e_nom`, `s_nom`, `p_nom_extendable`, `e_nom_extendable` and `s_nom_extendable`.

## `optimize_mga`

Stated under `velmora.Network.optimize.optimize_mga`.

## `slack`

Stated under `velmora.Network.optimize.optimize_mga_in_direction`.

## `weights`

Stated under `velmora.Network.optimize.optimize_mga`.

## `optimize_mga_in_direction`

Stated under `velmora.Network.optimize.optimize_mga_in_direction`.

## `dimensions`

Stated under `velmora.Network.optimize.optimize_mga_in_direction`.

## `direction`

Stated under `velmora.Network.optimize.optimize_mga_in_direction`.

## `optimize_mga_in_multiple_directions`

Stated under `velmora.Network.optimize.optimize_mga_in_multiple_directions`.

## `directions`

Stated under `velmora.Network.optimize.optimize_mga_in_multiple_directions`.

## `max_parallel`

Stated under `velmora.Network.optimize.optimize_mga_in_multiple_directions`.

## `optimize_security_constrained`

Stated under `velmora.Network.optimize.optimize_security_constrained`.

## `optimize_transmission_expansion_iteratively`

Stated under `velmora.Network.optimize.optimize_transmission_expansion_iteratively`.

## `fractional_last_unit_size`

Stated under `velmora.Network.optimize.optimize_transmission_expansion_iteratively`.

## `line_threshold`

Stated under `velmora.Network.optimize.optimize_transmission_expansion_iteratively`.

## `line_unit_size`

Stated under `velmora.Network.optimize.optimize_transmission_expansion_iteratively`.

## `link_threshold`

Stated under `velmora.Network.optimize.optimize_transmission_expansion_iteratively`.

## `link_unit_size`

Stated under `velmora.Network.optimize.optimize_transmission_expansion_iteratively`.

## `max_iterations`

Stated under `velmora.Network.optimize.optimize_transmission_expansion_iteratively`.

## `optimize_with_rolling_horizon`

Stated under `velmora.Network.optimize.optimize_with_rolling_horizon`.

## `horizon`

Stated under `velmora.Network.optimize.optimize_with_rolling_horizon`.

## `overlap`

Stated under `velmora.Network.optimize.optimize_with_rolling_horizon`.

## `solve_model`

`solve_model(solver_name=<str>, solver_options=<dict>)` returns the same two-string status form as `optimize`, including `('ok', 'optimal')` and `('warning', 'infeasible')`. Solutions are available through model variable/expression `solution` and network result tables.

## `pf`

Stated under `velmora.Network.pf`.

## `converged`

Stated under `velmora.Network.pf`.

## `distribute_slack`

Stated under `velmora.Network.pf`.

## `error`

Stated under `velmora.Network.pf`.

## `slack_weights`

Stated under `velmora.Network.pf`.

## `x_tol`

Stated under `velmora.Network.pf`.

## `auto_scale_branches`

Stated under `velmora.Network.plot`.

## `ax`

Stated under `velmora.Network.plot`.

## `branches`

Stated under `velmora.Network.plot`.

## `bus_cmap`

Stated under `velmora.Network.plot`.

## `bus_cmap_norm`

Stated under `velmora.Network.plot`.

## `flows`

Stated under `velmora.Network.plot`.

## `geomap`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `get_colors`

Stated under `velmora.Network.plot`.

## `get_facecolors`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `get_linewidths`

Stated under `velmora.Network.plot`.

## `get_paths`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `get_segments`

Stated under `velmora.Network.plot`.

## `nodes`

Stated under `velmora.Network.plot`.

## `vertices`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `remove`

`remove(class_name, name)` accepts a component-category string and one asset name or a sequence of names. Results are observed in the component tables. Removal refusal raises `KeyError`.

## `rename_component_names`

`rename_component_names(component, **kwargs)` accepts a component-category string and keyword mappings from existing names to replacement strings. Results are observed in component identities, connection fields and dynamic column labels.

## `set_investment_periods`

Stated under `velmora.Network.set_investment_periods`.

## `set_risk_preference`

`set_risk_preference(alpha=<float>, omega=<float>)` accepts confidence and risk weight. Refusal raises `ValueError`, either from this binding call or the subsequent optimisation. Results are exposed by scenario-labeled solved tables and scalar `objective`.

## `set_scenarios`

Stated under `velmora.Network.set_scenarios`.

## `set_snapshots`

Stated under `velmora.Network.set_snapshots`.

## `default_snapshot_weightings`

Stated under `velmora.Network.set_snapshots`.

## `weightings_from_timedelta`

Stated under `velmora.Network.set_snapshots`.

## `slice_network`

Stated under `velmora.Network.slice_network`.

## `aggregate_across_components`

Stated under `velmora.Network.statistics`.

## `all`

Stated under `velmora.Network.statistics`.

## `drop_zero`

Stated under `velmora.Network.statistics`.

## `round`

Stated under `velmora.Network.statistics`.

## `capacity_factor`

`statistics.capacity_factor(**kwargs)` returns capacity utilisation through the common labeled statistics result form.

## `expanded_capacity`

`statistics.expanded_capacity(**kwargs)` returns added nominal capacity through the common labeled statistics result form.

## `expanded_capex`

`statistics.expanded_capex(**kwargs)` returns change in capital expenditure through the common labeled statistics result form.

## `fom`

`statistics.fom(**kwargs)` returns fixed operating and maintenance expenditure through the common labeled statistics result form.

## `installed_capacity`

`statistics.installed_capacity(**kwargs)` returns installed nominal capacity through the common labeled statistics result form. It additionally accepts `storage=<bool>` to select storage-energy capacity.

## `storage`

`statistics.optimal_capacity(**kwargs)` returns solved nominal capacity through the common labeled statistics result form. It additionally accepts `storage=<bool>` to select storage-energy capacity.

## `bar`

Stated under `velmora.Network.statistics.installed_capacity.iplot.bar`.

## `annotations`

Stated under `velmora.Network.statistics.installed_capacity.iplot.bar`.

## `col_order`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `facet_col`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `layout`

Stated under `velmora.Network.statistics.installed_capacity.iplot.bar`.

## `text`

Stated under `velmora.Network.statistics.installed_capacity.iplot.bar`.

## `title`

Stated under `velmora.Network.statistics.installed_capacity.iplot.bar`.

## `value`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `x2`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `xaxis`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `yaxis`

Stated under `velmora.Network.statistics.installed_capacity.iplot.bar`.

## `Installed Capacity [MW]`

Stated under `velmora.Network.statistics.installed_capacity.iplot.bar`.

## `line`

Stated under `velmora.Network.statistics.installed_capacity.iplot.line`.

## `scatter`

Stated under `velmora.Network.statistics.installed_capacity.plot.scatter`.

## `axes_dict`

Stated under `velmora.Network.statistics.supply.plot.area`.

## `get_height`

Stated under `velmora.Network.statistics.installed_capacity.plot.bar`.

## `get_text`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `get_xticklabels`

Stated under `velmora.Network.statistics.supply.plot.area`.

## `get_ylabel`

Stated under `velmora.Network.statistics.installed_capacity.plot.line`.

## `get_yticklabels`

Stated under `velmora.Network.statistics.installed_capacity.plot.bar`.

## `patches`

Stated under `velmora.Network.statistics.installed_capacity.plot.box`.

## `query`

Stated under `velmora.Network.statistics.installed_capacity.plot.bar`.

## `box`

Stated under `velmora.Network.statistics.installed_capacity.plot.box`.

## `collections`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `histogram`

Stated under `velmora.Network.statistics.installed_capacity.plot.histogram`.

## `get_color`

Stated under `velmora.Network.statistics.installed_capacity.plot.line`.

## `get_ydata`

Stated under `velmora.Network.statistics.installed_capacity.plot.line`.

## `map`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `get_children`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `get_texts`

Stated under `velmora.Network.statistics.installed_capacity.plot.map`.

## `get_offsets`

Stated under `velmora.Network.statistics.installed_capacity.plot.scatter`.

## `violin`

Stated under `velmora.Network.statistics.installed_capacity.plot.violin`.

## `installed_capex`

`statistics.installed_capex(**kwargs)` returns installed capital expenditure through the common labeled statistics result form.

## `market_value`

`statistics.market_value(**kwargs)` returns market value per unit operation through the common labeled statistics result form.

## `cost_types`

`statistics.opex(**kwargs)` returns operating expenditure through the common labeled statistics result form. It additionally accepts `cost_types=<sequence of strings>`. Cost-type selectors used here are `start_up_cost`, `shut_down_cost`, `stand_by_cost`, `marginal_cost_storage` and `spill_cost`.

## `optimal_capacity`

`statistics.optimal_capacity(**kwargs)` returns solved nominal capacity through the common labeled statistics result form. It additionally accepts `storage=<bool>` to select storage-energy capacity.

## `prices`

`statistics.prices(groupby=<False or grouping string>, weighting=<str>, groupby_time=<bool>)` returns a numeric Series indexed by bus name or requested bus group, or a bus-by-snapshot DataFrame with time retained. `weighting` spellings are `load` and `time`. Grouping uses `bus_carrier`.

## `load`

`statistics.prices(groupby=<False or grouping string>, weighting=<str>, groupby_time=<bool>)` returns a numeric Series indexed by bus name or requested bus group, or a bus-by-snapshot DataFrame with time retained. `weighting` spellings are `load` and `time`. Grouping uses `bus_carrier`.

## `time`

`statistics.prices(groupby=<False or grouping string>, weighting=<str>, groupby_time=<bool>)` returns a numeric Series indexed by bus name or requested bus group, or a bus-by-snapshot DataFrame with time retained. `weighting` spellings are `load` and `time`. Grouping uses `bus_carrier`.

## `weighting`

`statistics.prices(groupby=<False or grouping string>, weighting=<str>, groupby_time=<bool>)` returns a numeric Series indexed by bus name or requested bus group, or a bus-by-snapshot DataFrame with time retained. `weighting` spellings are `load` and `time`. Grouping uses `bus_carrier`.

## `revenue`

`statistics.revenue(**kwargs)` returns energy revenue through the common labeled statistics result form.

## `area`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `positive`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `stackgroup`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `get_xticks`

Stated under `velmora.Network.statistics.supply.plot.area`.

## `system_cost`

`statistics.system_cost(**kwargs)` returns system cost through the common labeled statistics result form.

## `level`

Stated under `velmora.NetworkCollection`.

## `networks`

Stated under `velmora.NetworkCollection`.

## `get_network`

`get_network(collection)` accepts a collection member label, including a tuple for a MultiIndex, and returns the corresponding Network object.

## `import_from_pandapower_net`

Stated under `velmora.Network.import_from_pandapower_net`.

## `net`

Stated under `velmora.Network.import_from_pandapower_net`.

## `sgen`

Stated under `velmora.Network.import_from_pandapower_net`.

## `ext_grid`

Stated under `velmora.Network.import_from_pandapower_net`.

## `shunt`

Stated under `velmora.Network.import_from_pandapower_net`.

## `vn_kv`

Stated under `velmora.Network.import_from_pandapower_net`.

## `p_mw`

Stated under `velmora.Network.import_from_pandapower_net`.

## `q_mvar`

Stated under `velmora.Network.import_from_pandapower_net`.

## `scaling`

Stated under `velmora.Network.import_from_pandapower_net`.

## `vm_pu`

Stated under `velmora.Network.import_from_pandapower_net`.

## `std_type`

Stated under `velmora.Network.import_from_pandapower_net`.

## `length_km`

Stated under `velmora.Network.import_from_pandapower_net`.

## `parallel`

Stated under `velmora.Network.import_from_pandapower_net`.

## `unstack`

Stated under `velmora.Network.optimize.expressions.capacity`.

## `iplot`

Stated under `velmora.Network.statistics.supply.iplot.area`.

## `alpha`

`set_risk_preference(alpha=<float>, omega=<float>)` accepts confidence and risk weight. Refusal raises `ValueError`, either from this binding call or the subsequent optimisation. Results are exposed by scenario-labeled solved tables and scalar `objective`.

## `omega`

`set_risk_preference(alpha=<float>, omega=<float>)` accepts confidence and risk weight. Refusal raises `ValueError`, either from this binding call or the subsequent optimisation. Results are exposed by scenario-labeled solved tables and scalar `objective`.

## `Normalize`

Stated under `velmora.Network.plot`.

## `Series`

Stated under `velmora.Network.explore`.

## `velmora.costs.annuity`

`annuity(discount_rate, lifetime)` is importable from `velmora.costs`. For scalar numeric inputs it returns a numeric annual financing factor multiplying overnight cost. Refused lifetime input raises `ValueError`.

## `get_x`

Stated under `velmora.Network.statistics.installed_capacity.plot.bar`.

## `get_width`

Stated under `velmora.Network.statistics.installed_capacity.plot.bar`.

## `annuity`

`annuity(discount_rate, lifetime)` is importable from `velmora.costs`. For scalar numeric inputs it returns a numeric annual financing factor multiplying overnight cost. Refused lifetime input raises `ValueError`.

## `codes`

Stated under `WARNING`.
