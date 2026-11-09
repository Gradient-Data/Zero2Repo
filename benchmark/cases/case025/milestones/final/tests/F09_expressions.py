# feature: F09
"""Expression and collection acceptance through checked source."""
from F03_helpers import check_types


def test_collection_displays_comprehensions_and_unpacking():
    check_types('''
        from typing import assert_type, Literal
        def use(n: int, s: str, nums: list[int], words: dict[str, int]):
            assert_type([n][0], int)
            assert_type((n, s)[1], str)
            for element in {n}:
                assert_type(element, int)
            assert_type({'key': n}['key'], int)
            for element in [x for x in nums]:
                assert_type(element, int)
            for element in {x for x in nums}:
                assert_type(element, int)
            assert_type({k: v for k, v in words.items()}, dict[str, int])
            for element in [*nums]:
                assert_type(element, int)
            for element in {*nums}:
                assert_type(element, int)
            assert_type({**words}, dict[str, int])
            seq = [n, s]
            assert_type(seq[0], int)
            assert_type(seq[1], str)
            pair = (*('tag',), n)
            first, second = pair
            assert_type(first, Literal['tag'])
            assert_type(second, int)
            left, *middle, right = (n, s, s, n)
            assert_type(left, int)
            assert_type(middle[0], str)
            assert_type(middle[1], str)
            assert_type(right, int)
            mapping = {**{'name': s}, 'count': n}
            assert_type(mapping['name'], str)
            assert_type(mapping['count'], int)
            a, b = (n, s, n)  # E: bad_unpack
            c, d, *rest = (n,)  # E: bad_unpack
            e, f = n  # E: bad_unpack
            [*n]  # E: unsupported_operation
            {**n}  # E: unsupported_operation
            assert_type(second, str)  # E: inference_failure
    ''')


def test_operand_protocols_and_results():
    check_types('''
        from typing import assert_type
        class Forward:
            def __add__(self, other: int) -> str:
                return 'result'
            def __neg__(self) -> bytes:
                return b'result'
            def __getitem__(self, index: int) -> bytes:
                return b'item'
        class Reflected:
            def __radd__(self, other: int) -> bytes:
                return b'result'
        def use(n: int, s: str, xs: list[int], f: Forward, r: Reflected):
            assert_type(n + n, int)
            assert_type(n / n, float)
            assert_type(n & n, int)
            assert_type(n << n, int)
            assert_type(n < n, bool)
            assert_type(-n, int)
            assert_type(~n, int)
            assert_type(not n, bool)
            n += 1
            assert_type(n, int)
            assert_type(n in xs, bool)
            assert_type(xs[n], int)
            assert_type(xs[1:], list[int])
            assert_type(f + n, str)
            assert_type(n + r, bytes)
            assert_type(-f, bytes)
            assert_type(f[n], bytes)
            f + s  # E: unsupported_operation
            s + r  # E: unsupported_operation
            f[s]  # E: incompatible_argument
            f[1:]  # E: incompatible_argument
            n + s  # E: unsupported_operation
            n & s  # E: unsupported_operation
            n < s  # E: unsupported_operation
            ~s  # E: unsupported_operation
            n += s  # E: unsupported_operation
            n in n  # E: unsupported_operation
            xs[s]  # E: unsupported_operation|incompatible_argument
            assert_type(n + r, str)  # E: inference_failure
    ''')


def test_collection_mutation_and_conversion():
    check_types('''
        from typing import assert_type
        def use(nums: list[int], words: list[str], data: dict[str, int], number: int):
            good: list[int] = list(nums)
            bad: list[int] = list(words)  # E: incompatible_assignment
            nums.append(2)
            nums.append('bad')  # E: incompatible_argument
            nums.extend([3, 4])
            nums.extend(words)  # E: incompatible_argument
            data['good'] = number
            data['wrong'] = 'bad'  # E: incompatible_argument
            data[6] = 7  # E: incompatible_argument
            assert_type(nums[0], int)
            assert_type(nums[1:], list[int])
            assert_type(nums.copy(), list[int])
            assert_type(list(nums), list[int])
            assert_type(tuple(nums), tuple[int, ...])
            assert_type(set(nums), set[int])
            assert_type(data.copy(), dict[str, int])
            assert_type(data['good'], int)
            for item in nums:
                assert_type(item, int)
            for key, value in data.items():
                assert_type(key, str)
                assert_type(value, int)
            assert_type(nums.copy(), list[str])  # E: inference_failure
    ''')


def test_known_keys_hashability_and_tuple_bounds():
    check_types('''
        from typing import assert_type, Literal
        def use(n: int, s: str):
            {'same': n, 'same': s}  # E: duplicate_dict_key
            {[]: n}  # E: unhashable_key
            {[]}  # E: unhashable_key
            {(n, s): n}
            {(n, s)}
            {'first': n, 'second': s}
            pair = (n, s)
            assert_type(pair[0], int)
            assert_type(pair[-1], str)
            pair[2]  # E: incompatible_call
            pair[-3]  # E: incompatible_call
            present = {'count': n}
            assert_type(present.pop('count'), int)
            absent = {'count': n}
            absent.pop('missing')  # E: incompatible_argument
            defaulted = {'count': n}
            assert_type(defaulted.pop('missing', 'fallback'), Literal['fallback'])
    ''')


def test_synchronous_context_manager_contracts():
    check_types('''
        from typing import assert_type
        class IntegerManager:
            def __enter__(self) -> int:
                return 1
            def __exit__(self, typ, value, traceback) -> None:
                pass
        class TextManager:
            def __enter__(self) -> str:
                return 'text'
            def __exit__(self, typ, value, traceback) -> None:
                pass
        class EnterOnly:
            def __enter__(self) -> int:
                return 1
        class BadEnter:
            def __enter__(self, extra: int) -> int:
                return extra
            def __exit__(self, typ, value, traceback) -> None:
                pass
        class BadExit:
            def __enter__(self) -> int:
                return 1
            def __exit__(self) -> None:
                pass
        def use(valid: IntegerManager | TextManager, invalid: IntegerManager | EnterOnly):
            with IntegerManager() as number:
                assert_type(number, int)
                assert_type(number, str)  # E: inference_failure
            with valid as item:
                assert_type(item, int | str)
            with EnterOnly():  # E: invalid_context_manager
                pass
            with BadEnter():  # E: invalid_context_manager
                pass
            with BadExit():  # E: invalid_context_manager
                pass
            with invalid:  # E: invalid_context_manager
                pass
    ''')


def test_disjoint_equality_and_permitted_overlap():
    check_types('''
        from typing import Literal, overload
        class Flexible:
            @overload
            def __eq__(self, other: int) -> Literal[False]: ...
            @overload
            def __eq__(self, other: str) -> Literal[False]: ...
            def __eq__(self, other: object) -> bool:
                return False
        def use(n: int, s: str, ns: list[int], ss: list[str],
                a: int | str, b: str | bytes, custom: Flexible):
            print(n == s)  # E: unsafe_comparison
            print(n != s)  # E: unsafe_comparison
            print(ns == ss)  # E: unsafe_comparison
            print(a == b)
            print(n == None)
            print(None == s)
            print(custom == n)
            print(n == custom)
            print(custom == s)
            print(n == n)
    ''')
