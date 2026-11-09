# feature: F09
"""Acceptance of translated classes, reference semantics, and operators."""
import operator
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from F00_oracle import host_numpy as np
from _helpers import write_text
from F01_helpers import translate_and_observe
from F02_helpers import python_namespace
from F05_helpers import interactive_session, load_session_module, require_exception
from F09_helpers import OBJECT_SOURCE, REFERENCE_SOURCE, OPERATOR_SPECS, operator_program


def test_class_initialization_methods_and_properties(tmp_path):
    for language in ('c', 'fortran'):
        root = tmp_path / language
        root.mkdir()
        path = write_text(root, 'state_input.py', OBJECT_SOURCE)

        def exercise(ezelvori):
            reference = load_session_module(path)
            single = ezelvori(reference.State, language=language, folder='single')
            module = ezelvori(reference, language=language, folder='module')
            for cls in (single, module.State):
                for value, size in ((4, 3), (-2, 5)):
                    obj = cls(value, size)
                    expected = reference.State(value, size)
                    for amount in (0, 6, -3):
                        obj.update(amount)
                        expected.update(amount)
                        assert (obj.value, obj.extra, obj.total) == (
                            expected.value, expected.extra, expected.total)
                        np.testing.assert_array_equal(obj.data, expected.data)
                    obj.initialize(7)
                    expected.initialize(7)
                    assert obj.extra == expected.extra
                    assert obj.total == expected.total

        interactive_session(root / 'session', exercise)


def test_read_only_property_rejects_write(tmp_path):
    def exercise(module):
        obj = module.State(8, 4)
        assert obj.total == 33
        with require_exception(AttributeError):
            obj.total = -91
        assert (obj.value, obj.extra, obj.total) == (8, 25, 33)
        np.testing.assert_array_equal(obj.data, [8, 8, 8, 8])
        obj.update(3)
        assert (obj.value, obj.extra, obj.total) == (11, 22, 33)

    for language in ('c', 'fortran'):
        translate_and_observe(OBJECT_SOURCE, language, tmp_path / language, exercise)


def test_object_references_and_shared_array_attributes(tmp_path):
    def exercise(module):
        data = np.array([2., -4., 6., 8.])
        obj = module.make(data)
        alias = module.identity(obj)
        holder = module.Holder(obj)
        returned = holder.get()
        assert obj.edits == 0
        module.change(alias, 1, 19.)
        for item in (obj, alias, returned, holder.item):
            assert item.edits == 1
            np.testing.assert_array_equal(item.data, [2., 19., 6., 8.])
        np.testing.assert_array_equal(data, [2., 19., 6., 8.])
        holder.change(3, -7.)
        np.testing.assert_array_equal(obj.data, [2., 19., 6., -7.])
        np.testing.assert_array_equal(data, [2., 19., 6., -7.])
        for item in (obj, alias, returned, holder.item):
            assert item.edits == 2
        data[0] = 31.
        for item in (obj, alias, returned, holder.item):
            np.testing.assert_array_equal(item.data, [31., 19., 6., -7.])
        returned.change(2, 23.)
        np.testing.assert_array_equal(data, [31., 19., 23., -7.])
        np.testing.assert_array_equal(obj.data, data)
        for item in (obj, alias, returned, holder.item):
            assert item.edits == 3

    for language in ('c', 'fortran'):
        translate_and_observe(REFERENCE_SOURCE, language, tmp_path / language, exercise)


def test_user_operators_and_collection_behavior(tmp_path):
    source = operator_program()
    reference = python_namespace(source)

    def exercise(module):
        for name, _ in OPERATOR_SPECS:
            binary = getattr(operator, name if name not in ('and', 'or') else name + '_')
            inplace = getattr(operator, 'i' + name)
            for value, other in ((4, 2), (3, 3)):
                # Power methods are tested below through translated calls:
                # the original does not publish Python power operator slots.
                if name != 'pow':
                    obj = module.Number(value)
                    expected = reference['Number'](value)
                    result = binary(obj, other)
                    assert result.value == binary(expected, other).value
                    assert obj.value == value
                    updated = inplace(obj, other)
                    expected = inplace(expected, other)
                    assert updated.value == expected.value
                    assert obj.value == expected.value
                for prefix in ('direct', 'reflected', 'inplace'):
                    entry = prefix + '_' + name
                    assert getattr(module, entry)(value, other) == reference[entry](value, other)
        for value, index, item in ((4, 0, 5), (3, 2, 8)):
            obj = module.Number(value)
            expected = reference['Number'](value)
            assert len(obj) == len(expected)
            assert obj[index] == expected[index]
            assert module.collection(value, index, item) == reference['collection'](value, index, item)

    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_constructor_requires_single_argument_types(tmp_path):
    for language in ('c', 'fortran'):
        def exercise(ezelvori):
            from zelvori.errors.errors import ZelvoriSemanticError
            good = ezelvori('''
class Item:
    def __init__(self, value: int):
        self.value = value
''', language=language, folder='valid')
            for value in (-6, 13):
                assert good.Item(value).value == value
            declarations = (
                ('', "'int | float'"),
                ('from typing import TypeVar\nT = TypeVar("T", int, float)\n', 'T'),
            )
            for index, (header, annotation) in enumerate(declarations):
                source = header + f'''
class Item:
    def __init__(self, value: {annotation}):
        self.value = value
'''
                with require_exception(ZelvoriSemanticError):
                    ezelvori(source, language=language, folder=f'invalid_{index}')

        interactive_session(tmp_path / language, exercise)
