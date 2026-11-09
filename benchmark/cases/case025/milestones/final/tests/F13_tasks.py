# feature: F13
"""Task framework contracts through real source checking."""
from F03_helpers import check_types
from F13_helpers import check_task_methods


def test_task_calls_and_callable_contracts():
    check_types('''
        from asynq import asynq, AsyncTask
        from typing import assert_type
        from velnora.extensions import AsynqCallable
        @asynq()
        def number(x: int) -> int:
            return x
        @asynq()
        def label(x: int) -> str:
            return str(x)
        @asynq()
        def wrong_input(x: str) -> int:
            return len(x)
        def ordinary(x: int) -> int:
            return x
        def take(fn: AsynqCallable[[int], int]):
            assert_type(fn(2), int)
            assert_type(fn(2), str)  # E: inference_failure
        def use():
            assert_type(number(3), int)
            assert_type(number(3), str)  # E: inference_failure
            task = number.asynq(3)
            value: int = task  # E: incompatible_assignment
            take(number)
            take(label)  # E: incompatible_argument
            take(wrong_input)  # E: incompatible_argument
            take(ordinary)  # E: incompatible_argument
        @asynq()
        def consume(fn: AsynqCallable[[int], int]):
            value = yield fn.asynq(4)
            assert_type(value, int)
            assert_type(value, str)  # E: inference_failure
            text = yield label.asynq(value)
            assert_type(text, str)
            assert_type(text, int)  # E: inference_failure
    ''')


def test_yielded_results_and_nested_collections():
    check_types('''
        from asynq import asynq, ConstFuture, FutureBase
        from typing import assert_type, Literal
        @asynq()
        def number() -> int:
            return 9
        @asynq()
        def label() -> str:
            return 'ready'
        @asynq()
        def consume():
            yield FutureBase()
            future = yield ConstFuture(7)
            assert_type(future, Literal[7])
            assert_type(future, str)  # E: inference_failure
            empty = yield None
            assert_type(empty, None)
            assert_type(empty, int)  # E: inference_failure
            nested = yield {'items': [number.asynq(), (label.asynq(), None)]}
            assert_type(nested['items'][0], int)
            assert_type(nested['items'][0], str)  # E: inference_failure
            assert_type(nested['items'][1], tuple[str, None])
            assert_type(nested['items'][1][0], str)
            assert_type(nested['items'][1][1], None)
            assert_type(nested['items'][1], tuple[int, None])  # E: inference_failure
            mapping: dict[str, list[int | tuple[str, None]]] = nested
            wrong_shape: tuple[int, tuple[str, None]] = nested['items']  # E: incompatible_assignment
            yield 12  # E: bad_async_yield
            yield [number.asynq(), 'bad']  # E: bad_async_yield
            yield  # E: yield_without_value
    ''')


def test_task_consumption_and_method_discipline():
    check_types('''
        from asynq import asynq, ConstFuture
        @asynq()
        def number() -> int:
            return 8
        @asynq()
        def returned(): return number.asynq()  # E: task_needs_yield
        @asynq()
        def future_returned(): return ConstFuture(8)  # E: task_needs_yield
        @asynq()
        def discarded():
            number.asynq()  # E: task_needs_yield
        @asynq()
        def direct():
            return number()  # E: impure_async_call
        @asynq()
        def valid():
            value = yield number.asynq()
            return value
        def ordinary():
            return number()
    ''')
    check_task_methods()


def test_yield_dependencies_duplicates_and_declarations():
    check_types('''
        from asynq import asynq
        @asynq()
        def number(x: int) -> int:
            return x
        @asynq()
        def duplicate(x: int):
            yield number.asynq(x), number.asynq(x)  # E: duplicate_yield
            yield number.asynq(x), number.asynq(x + 1)
        @asynq()
        def independent():
            first = yield number.asynq(1)
            second = yield number.asynq(2)  # E: unnecessary_yield
            return first + second
        @asynq()
        def dependent():
            first = yield number.asynq(1)
            second = yield number.asynq(first)
            return second
        @asynq()
        def read_between():
            first = yield number.asynq(1)
            print(first)
            second = yield number.asynq(2)
            return second
        def missing():
            yield number.asynq(3)  # E: missing_asynq
        def ordinary():
            yield 3
    ''')
