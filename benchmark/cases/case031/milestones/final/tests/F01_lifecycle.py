# feature: F01
"""Acceptance checks for public network construction and lifecycle operations."""

import pandas as pd
import pytest
from shapely.geometry import Point

from velmora import Network
from _helpers import invoke, read_table


def test_component_categories_and_identity():
    n = Network()
    n.add("Bus", ["hub", "remote"], v_nom=[110, 20])
    n.add("Carrier", "hub", co2_emissions=0.27)
    entries = [
        ("Generator", {"bus": "hub", "p_nom": 13}),
        ("Load", {"bus": "hub", "p_set": 7}),
        ("Line", {"bus0": "hub", "bus1": "remote", "x": 0.12}),
        ("Transformer", {"bus0": "hub", "bus1": "remote", "s_nom": 23}),
        ("Link", {"bus0": "hub", "bus1": "remote", "efficiency": 0.8}),
        ("Process", {"bus0": "hub", "bus1": "remote", "rate1": 0.6}),
        ("StorageUnit", {"bus": "hub", "p_nom": 17}),
        ("Store", {"bus": "hub", "e_nom": 29}),
        ("ShuntImpedance", {"bus": "hub", "g": 0.02}),
        ("GlobalConstraint", {"constant": 31}),
        ("Shape", {"geometry": Point(2, 3), "component": "Bus", "idx": "hub"}),
        ("LineType", {"r_per_length": 0.14, "x_per_length": 0.3}),
        ("TransformerType", {"s_nom": 37, "v_nom_0": 110, "v_nom_1": 20}),
    ]
    for component, attrs in entries:
        n.add(component, "hub", **attrs)
        row = read_table(n.c[component].static, rows=["hub"], columns=list(attrs))
        for attr, expected in attrs.items():
            assert row.at["hub", attr] == expected, (component, attr)
    n.add("Generator", "sector-user", bus="remote", carrier="hub", p_nom=19)
    assert set(n.c.buses.static.index) == {"hub", "remote"}
    assert n.c.buses.static.at["hub", "v_nom"] == 110
    assert n.c.carriers.static.at["hub", "co2_emissions"] == 0.27
    assert n.c.generators.static.at["sector-user", "carrier"] == "hub"
    assert n.c.generators.static.at["hub", "p_nom"] == 13


def test_individual_batch_attributes_and_duplicate_refusal():
    n = Network()
    n.add("Bus", ["north", "south"])
    n.add("Generator", "single", bus="north", p_nom=11, efficiency=0.7)
    n.add("Generator", ["first", "second"], bus=["south", "north"],
          p_nom=[23, 41], efficiency=0.9, carrier="custom-sector")
    expected = {
        "single": ("north", 11, 0.7),
        "first": ("south", 23, 0.9),
        "second": ("north", 41, 0.9),
    }
    for name, values in expected.items():
        assert tuple(n.c.generators.static.loc[name, ["bus", "p_nom", "efficiency"]]) == values
    assert n.c.generators.static.loc[["first", "second"], "carrier"].tolist() == ["custom-sector"] * 2
    result = invoke(n.add, "Generator", ["repeated", "repeated"],
                    kwargs={"bus": "north", "p_nom": [3, 5]},
                    expected_exceptions=(ValueError,))
    assert isinstance(result.exception, ValueError)
    assert "repeated" not in n.c.generators.static.index


def test_retention_and_explicit_replacement():
    n = Network()
    n.set_snapshots([0, 1, 2])
    n.add("Bus", "bus")
    n.add("Generator", "keep", bus="bus", p_nom=19, marginal_cost=4,
          p_max_pu=[0.2, 0.5, 0.8])
    n.add("Generator", "replace", bus="bus", p_nom=11, marginal_cost=9, efficiency=0.71,
          p_max_pu=[0.1, 0.3, 0.7], p_min_pu=[0.01, 0.02, 0.03])
    n.add("Generator", "replace", bus="bus", p_nom=73, p_max_pu=[1, 1, 1])
    assert n.c.generators.static.at["replace", "p_nom"] == 11
    assert n.c.generators.static.at["replace", "marginal_cost"] == 9
    assert n.c.generators.dynamic.p_max_pu["replace"].tolist() == [0.1, 0.3, 0.7]
    n.add("Generator", "replace", overwrite=True, bus="bus", p_nom=43,
          marginal_cost=6, p_max_pu=0.6, p_min_pu=0.04)
    assert n.c.generators.static.at["replace", "p_nom"] == 43
    assert n.c.generators.static.at["replace", "efficiency"] == 1
    assert n.c.generators.static.at["replace", "marginal_cost"] == 6
    assert n.c.generators.static.at["replace", "p_max_pu"] == 0.6
    assert n.c.generators.static.at["replace", "p_min_pu"] == 0.04
    for attribute, value in [('p_max_pu', 0.6), ('p_min_pu', 0.04)]:
        effective = n.get_switchable_as_dense('Generator', attribute)
        assert effective['replace'].tolist() == [value] * len(n.snapshots)
    # Replacing with static inputs must remove the old time-series override.
    # Observe that effect after another static edit, independently of storage.
    n.c.generators.static.at['replace', 'p_max_pu'] = 0.55
    n.c.generators.static.at['replace', 'p_min_pu'] = 0.03
    for attribute, value in [('p_max_pu', 0.55), ('p_min_pu', 0.03)]:
        assert n.get_switchable_as_dense('Generator', attribute)['replace'].tolist() == [value] * len(n.snapshots)
    assert n.c.generators.static.at["keep", "p_nom"] == 19
    assert n.c.generators.dynamic.p_max_pu["keep"].tolist() == [0.2, 0.5, 0.8]
    # A group addition overlapping an existing asset still adds the new assets.
    n.add("Generator", ["keep", "fresh"], bus="bus", p_nom=[61, 67], marginal_cost=[2, 3])
    assert n.c.generators.static.at["keep", "p_nom"] == 19
    assert n.c.generators.static.at["keep", "marginal_cost"] == 4
    assert n.c.generators.static.at["fresh", "p_nom"] == 67
    assert n.c.generators.static.at["fresh", "marginal_cost"] == 3
    n.add("Generator", "replace", overwrite=True, bus="bus", p_nom=47,
          p_max_pu=[0.9, 0.8, 0.4])
    assert n.c.generators.dynamic.p_max_pu["replace"].tolist() == [0.9, 0.8, 0.4]


def test_removal_including_all_scenarios():
    for stochastic in (False, True):
        n = Network()
        n.set_snapshots([0, 1, 2])
        n.add("Bus", "bus")
        n.add("Generator", ["a", "b", "survivor"], bus="bus", p_nom=[7, 13, 29],
              p_max_pu=pd.DataFrame({"a": [0.2, 0.4, 0.6], "b": [0.3, 0.5, 0.7],
                                     "survivor": [0.9, 0.8, 0.7]}, index=n.snapshots),
              marginal_cost=pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6],
                                          "survivor": [7, 8, 9]}, index=n.snapshots))
        if stochastic:
            n.set_scenarios(["mild", "severe"])
        n.remove("Generator", "a")
        n.remove("Generator", ["b"])
        expected_names = {("mild", "survivor"), ("severe", "survivor")} if stochastic else {"survivor"}
        assert set(n.c.generators.static.index) == expected_names
        assert set(n.c.generators.dynamic.p_max_pu.columns) == expected_names
        assert set(n.c.generators.dynamic.marginal_cost.columns) == expected_names
        for name in expected_names:
            assert n.c.generators.static.at[name, "p_nom"] == 29
            assert n.c.generators.dynamic.p_max_pu[name].tolist() == [0.9, 0.8, 0.7]
            assert n.c.generators.dynamic.marginal_cost[name].tolist() == [7, 8, 9]
        result = invoke(n.remove, "Generator", "a", expected_exceptions=(KeyError,))
        assert isinstance(result.exception, KeyError)
        # A refused removal that also names a present asset leaves it in place.
        result = invoke(n.remove, "Generator", ["survivor", "a"], expected_exceptions=(KeyError,))
        assert isinstance(result.exception, KeyError)
        assert set(n.c.generators.static.index) == expected_names
        assert set(n.c.generators.dynamic.p_max_pu.columns) == expected_names


def test_renaming_updates_data_and_references():
    n = Network()
    n.set_snapshots([0, 1])
    n.add("Carrier", "fuel")
    n.add("Bus", "old", carrier="fuel", v_mag_pu_set=[1.01, 1.02])
    n.add("Bus", "other")
    for component in ("Generator", "Load", "Store", "StorageUnit", "ShuntImpedance"):
        n.add(component, "asset", bus="old")
    for component in ("Line", "Transformer", "Link", "Process"):
        n.add(component, ["outgoing", "incoming"], bus0=["old", "other"],
              bus1=["other", "old"])
    n.add("Link", "multi", bus0="other", bus1="other", bus2="old", carrier="fuel")
    n.add("Generator", "timed", bus="old", carrier="fuel", p_max_pu=[0.3, 0.7])
    n.add("GlobalConstraint", "limit", bus="old", constant=5)
    # Names equal to the bus name in other roles are not bus references.
    n.add("Carrier", "old")
    n.add("Generator", "old", bus="other", carrier="old")
    n.rename_component_names("Bus", old="renamed")
    assert set(n.c.buses.static.index) == {"renamed", "other"}
    assert 'old' not in n.c.buses.dynamic.v_mag_pu_set.columns
    effective = n.get_switchable_as_dense('Bus', 'v_mag_pu_set')
    assert set(effective.columns) == {'renamed', 'other'}
    assert effective['other'].tolist() == [1., 1.]
    assert n.c.buses.dynamic.v_mag_pu_set["renamed"].tolist() == [1.01, 1.02]
    for component in ("Generator", "Load", "Store", "StorageUnit", "ShuntImpedance"):
        assert n.c[component].static.at["asset", "bus"] == "renamed"
    for component in ("Line", "Transformer", "Link", "Process"):
        table = n.c[component].static
        assert table.at["outgoing", "bus0"] == "renamed"
        assert table.at["outgoing", "bus1"] == "other"
        assert table.at["incoming", "bus0"] == "other"
        assert table.at["incoming", "bus1"] == "renamed"
    assert n.c.links.static.at["multi", "bus2"] == "renamed"
    assert n.c.generators.static.at["timed", "bus"] == "renamed"
    assert n.c.generators.dynamic.p_max_pu["timed"].tolist() == [0.3, 0.7]
    assert n.c.global_constraints.static.at["limit", "bus"] == "renamed"
    assert set(n.c.carriers.static.index) == {"fuel", "old"}
    assert n.c.generators.static.at["old", "bus"] == "other"
    assert n.c.generators.static.at["old", "carrier"] == "old"
    assert n.c.generators.static.at["timed", "carrier"] == "fuel"


def test_independent_copy_and_bus_selection():
    n = Network(name="Study", meta={"study": {"revision": 2}})
    n.set_snapshots([0, 1])
    n.add("Bus", ["a", "b", "outside"])
    for component in ("Generator", "Load", "Store", "StorageUnit", "ShuntImpedance"):
        n.add(component, ["inside", "outside"], bus=["a", "outside"])
    n.add("Generator", "profile", bus="b", p_nom=17, p_max_pu=[0.4, 0.8])
    for component in ("Line", "Transformer", "Link", "Process"):
        n.add(component, ["inside", "crossing", "outside"],
              bus0=["a", "a", "outside"], bus1=["b", "outside", "outside"])
    copied = n.copy()
    assert copied.name == "Study"
    assert copied.meta == {"study": {"revision": 2}}
    for component in ("Bus", "Generator", "Load", "Store", "StorageUnit", "ShuntImpedance",
                      "Line", "Transformer", "Link", "Process"):
        pd.testing.assert_frame_equal(copied.c[component].static.sort_index(), n.c[component].static.sort_index(), check_dtype=False, check_names=False, check_like=True, check_frame_type=False, check_index_type=False, check_column_type=False)
    assert copied.c.generators.dynamic.p_max_pu["profile"].tolist() == [0.4, 0.8]
    copied.name = "Edited"
    copied.meta["study"]["revision"] = 3
    copied.c.generators.static.at["profile", "p_nom"] = 91
    copied.c.generators.dynamic.p_max_pu.at[0, "profile"] = 0.1
    assert n.name == "Study"
    assert n.meta == {"study": {"revision": 2}}
    assert n.c.generators.static.at["profile", "p_nom"] == 17
    assert n.c.generators.dynamic.p_max_pu["profile"].tolist() == [0.4, 0.8]
    selected = n.slice_network(buses=["a", "b"])
    assert set(selected.c.buses.static.index) == {"a", "b"}
    for component in ("Load", "Store", "StorageUnit", "ShuntImpedance", "Line", "Transformer", "Link", "Process"):
        assert set(selected.c[component].static.index) == {"inside"}
    assert set(selected.c.generators.static.index) == {"inside", "profile"}
    assert selected.c.generators.static.at["profile", "p_nom"] == 17
    assert selected.c.generators.static.at["profile", "bus"] == "b"
    for component in ("Load", "Store", "StorageUnit", "ShuntImpedance"):
        assert selected.c[component].static.at["inside", "bus"] == "a"
    for component in ("Line", "Transformer", "Link", "Process"):
        assert tuple(selected.c[component].static.loc["inside", ["bus0", "bus1"]]) == ("a", "b")
    assert selected.c.generators.dynamic.p_max_pu["profile"].tolist() == [0.4, 0.8]
    selected.c.generators.dynamic.p_max_pu.at[0, "profile"] = 0.2
    assert n.c.generators.dynamic.p_max_pu["profile"].tolist() == [0.4, 0.8]


def test_merge_data_and_conflict_refusal():
    left = Network(name="Receiving study", meta={"study": {"revision": 2}})
    right = Network(name="Incoming study", meta={"study": {"revision": 9}})
    for n, resistance, rating in ((left, 0.17, 31), (right, 0.41, 73)):
        n.add("LineType", "study-line", r_per_length=resistance, x_per_length=0.3)
        n.add("TransformerType", "study-transformer", s_nom=rating,
              v_nom_0=110, v_nom_1=20)
    for n, prefix, capacity, profile in ((left, "left", 13, [0.2, 0.6]), (right, "right", 37, [0.9, 0.4])):
        n.set_snapshots([0, 1])
        n.add("Bus", prefix, v_nom=110)
        n.add("Generator", prefix, bus=prefix, p_nom=capacity, p_max_pu=profile,
              description=prefix + " generation")
    right.add("Store", "right-store", bus="right", e_nom=43, e_max_pu=[0.5, 0.25])
    right.add("Link", "right-link", bus0="right", bus1="right", p_nom=53, efficiency=0.35,
              marginal_cost=[3, 4])
    merged = left.merge(right)
    assert merged.name == "Receiving study"
    assert merged.meta == {"study": {"revision": 2}}
    assert merged.c.line_types.static.at["study-line", "r_per_length"] == 0.17
    assert merged.c.line_types.static.at["study-line", "x_per_length"] == 0.3
    assert merged.c.transformer_types.static.at["study-transformer", "s_nom"] == 31
    assert merged.c.transformer_types.static.at["study-transformer", "v_nom_0"] == 110
    assert merged.c.transformer_types.static.at["study-transformer", "v_nom_1"] == 20
    assert set(merged.c.buses.static.index) == {"left", "right"}
    assert set(merged.c.generators.static.index) == {"left", "right"}
    for name, capacity, profile in (("left", 13, [0.2, 0.6]), ("right", 37, [0.9, 0.4])):
        assert merged.c.generators.static.at[name, "p_nom"] == capacity
        assert merged.c.generators.static.at[name, "bus"] == name
        assert merged.c.generators.static.at[name, "description"] == name + " generation"
        assert merged.c.generators.dynamic.p_max_pu[name].tolist() == profile
    assert merged.c.stores.static.at["right-store", "e_nom"] == 43
    assert merged.c.stores.static.at["right-store", "bus"] == "right"
    assert merged.c.stores.dynamic.e_max_pu["right-store"].tolist() == [0.5, 0.25]
    assert tuple(merged.c.links.static.loc["right-link", ["bus0", "bus1", "p_nom", "efficiency"]]) == (
        "right", "right", 53, 0.35)
    assert merged.c.links.dynamic.marginal_cost["right-link"].tolist() == [3, 4]
    assert set(left.c.generators.static.index) == {"left"}
    assert left.c.stores.static.empty and left.c.links.static.empty
    assert set(right.c.generators.static.index) == {"right"}
    overlap = Network()
    overlap.set_snapshots([0, 1])
    overlap.add("Bus", "separate")
    overlap.add("Generator", "left", bus="separate", p_nom=7)
    with pytest.raises(ValueError):
        left.merge(overlap)
    bus_overlap = Network()
    bus_overlap.set_snapshots([0, 1])
    bus_overlap.add("Bus", "left")
    bus_overlap.add("Store", "separate", bus="left", e_nom=3)
    with pytest.raises(ValueError):
        left.merge(bus_overlap)
    different_time = right.copy()
    different_time.set_snapshots([2, 3, 4])
    with pytest.raises(ValueError):
        left.merge(different_time, with_time=True)
    static_only = left.merge(different_time, with_time=False)
    assert set(static_only.c.generators.static.index) == {"left", "right"}
    assert static_only.c.generators.static.at["right", "p_nom"] == 37
    assert static_only.snapshots.tolist() == [0, 1]
    assert static_only.c.stores.static.at["right-store", "e_nom"] == 43
    assert static_only.c.links.static.at["right-link", "efficiency"] == 0.35
    for weighting in ("objective", "generators", "stores"):
        different_weights = right.copy()
        different_weights.snapshot_weightings.loc[0, weighting] = 3
        with pytest.raises(ValueError):
            left.merge(different_weights, with_time=True)


def test_initial_defaults_and_descriptive_attributes():
    n = Network()
    assert len(n.snapshots) == 1
    for component in ("Bus", "Carrier", "Generator", "Load", "Line", "Transformer", "Link", "Process",
                      "StorageUnit", "Store", "ShuntImpedance", "GlobalConstraint", "Shape"):
        assert n.c[component].static.empty, component
    n.add("Bus", "bus", site_description="Coastal site")
    n.add("Load", "load", bus="bus")
    n.add("Generator", "gen", bus="bus", owner_note="Community asset")
    assert n.c.loads.static.at["load", "p_set"] == 0
    assert n.c.loads.static.at["load", "q_set"] == 0
    assert pd.isna(n.c.generators.static.at["gen", "p_set"])
    assert n.get_switchable_as_dense('Generator', 'p_set')['gen'].isna().all()
    assert n.c.generators.static.at["gen", "q_set"] == 0
    assert n.c.generators.static.at["gen", "efficiency"] == 1
    assert n.c.buses.static.at["bus", "v_nom"] == 1
    assert n.c.buses.static.at["bus", "carrier"] == "AC"
    assert n.c.buses.static.at["bus", "site_description"] == "Coastal site"
    assert n.c.generators.static.at["gen", "owner_note"] == "Community asset"
    for component, capacity in (("Generator", "p_nom"), ("Link", "p_nom"), ("Process", "p_nom"),
                                ("StorageUnit", "p_nom"), ("Store", "e_nom"),
                                ("Line", "s_nom"), ("Transformer", "s_nom")):
        if component != "Generator":
            ports = {"bus0": "bus", "bus1": "bus"} if component in ("Link", "Process", "Line", "Transformer") else {"bus": "bus"}
            n.add(component, "gen", **ports)
        row = n.c[component].static.loc["gen"]
        assert row[capacity] == 0, component
        assert bool(row["active"]) is True, component
        assert bool(row[capacity + "_extendable"]) is False, component
        if component in ("Generator", "Link", "Process"):
            assert bool(row["committable"]) is False, component
            assert bool(row["maintainable"]) is False, component
