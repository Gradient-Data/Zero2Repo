# feature: F12
"""Generator and native async contracts observed through the public CLI."""
from F03_helpers import check_types


def test_generator_channels_and_delegation():
    check_types('''
        from typing import Generator, assert_type
        def child(flag: bool) -> Generator[int, str, bytes]:
            sent = yield 7
            assert_type(sent, str)
            assert_type(sent, int)  # E: inference_failure
            yield sent  # E: incompatible_yield
            if flag:
                return b'done'
            return 'wrong'  # E: incompatible_return_value
        def parent() -> Generator[int, str, bytes]:
            result = yield from child(True)
            assert_type(result, bytes)
            assert_type(result, str)  # E: inference_failure
            return result
        def wrong_elements() -> Generator[str, str, bytes]:
            result = yield from child(True)  # E: incompatible_yield
            assert_type(result, bytes)
            return result
        def wrong_send() -> Generator[int, int, bytes]:
            result = yield from child(True)  # E: incompatible_yield
            return result
    ''')


def test_generator_declarations_and_completion():
    check_types('''
        from typing import Generator, Iterable, Iterator, assert_type
        def invalid() -> int:  # E: generator_return
            yield 3
        def iterable(flag: bool) -> Iterable[int]:
            sent = yield 3
            assert_type(sent, None)
            yield 'bad'  # E: incompatible_yield
            if flag:
                return
            return 8  # E: incompatible_return_value
        def iterator() -> Iterator[str]:
            yield 'item'
            return
        def complete(flag: bool) -> Generator[int, None, bytes]:
            yield 3
            if flag:
                return b'yes'
            return b'no'
        def incomplete(flag: bool) -> Generator[int, None, bytes]:  # E: missing_return
            yield 3
            if flag:
                return b'yes'
        def raises(flag: bool) -> Generator[int, None, bytes]:
            yield 3
            if flag:
                return b'yes'
            raise ValueError('stopped')
    ''')


def test_await_results_and_consumption():
    check_types('''
        from typing import Awaitable, assert_type
        async def number() -> int:
            return 17
        async def text() -> str:
            return 'ready'
        def take_number(task: Awaitable[int]) -> None:
            pass
        def take_text(task: Awaitable[str]) -> None:
            pass
        def forward() -> Awaitable[int]:
            return number()
        async def use() -> None:
            task = number()
            take_number(task)
            take_text(task)  # E: incompatible_argument
            result = await task
            assert_type(result, int)
            assert_type(result, str)  # E: inference_failure
            other = await text()
            assert_type(other, str)
            take_text(text())
            number()  # E: missing_await
            await 12  # E: unsupported_operation
            await number()
    ''')


def test_async_generators_and_iteration():
    check_types('''
        from typing import AsyncGenerator, AsyncIterable, AsyncIterator, assert_type
        async def stream() -> AsyncGenerator[int, str]:
            sent = yield 4
            assert_type(sent, str)
            assert_type(sent, int)  # E: inference_failure
            yield sent  # E: incompatible_yield
        async def labels() -> AsyncIterator[str]:
            yield 'label'
            yield 5  # E: incompatible_yield
        async def iterable() -> AsyncIterable[bytes]:
            yield b'item'
        async def invalid() -> int:  # E: generator_return
            yield 4
        class Cursor:
            def __aiter__(self) -> 'Cursor':
                return self
            async def __anext__(self) -> bytes:
                return b'item'
        async def use() -> None:
            async for item in stream():
                assert_type(item, int)
                assert_type(item, str)  # E: inference_failure
            async for label in labels():
                assert_type(label, str)
            async for data in Cursor():
                assert_type(data, bytes)
            async for data in iterable():
                assert_type(data, bytes)
            async for invalid in [1, 2]:  # E: unsupported_operation
                pass
    ''')


def test_async_context_manager_contracts():
    check_types('''
        from typing import Union, assert_type
        class Numbers:
            async def __aenter__(self) -> int:
                return 6
            async def __aexit__(self, typ, value, traceback) -> None:
                pass
        class Labels:
            async def __aenter__(self) -> str:
                return 'label'
            async def __aexit__(self, typ, value, traceback) -> None:
                pass
        class EntryOnly:
            async def __aenter__(self) -> int:
                return 6
        class SyncExit:
            async def __aenter__(self) -> int:
                return 6
            def __aexit__(self, typ, value, traceback) -> None:
                pass
        class SyncEntry:
            def __aenter__(self) -> int:
                return 6
            async def __aexit__(self, typ, value, traceback) -> None:
                pass
        async def use(valid: Union[Numbers, Labels], missing: Union[Numbers, EntryOnly],
                      bad_exit: Union[Numbers, SyncExit], bad_entry: Union[Numbers, SyncEntry]):
            async with Numbers() as value:
                assert_type(value, int)
                assert_type(value, str)  # E: inference_failure
            async with valid as value:
                assert_type(value, Union[int, str])
                assert_type(value, int)  # E: inference_failure
            async with missing:  # E: invalid_context_manager
                pass
            async with bad_exit:  # E: invalid_context_manager
                pass
            async with bad_entry:  # E: invalid_context_manager
                pass
    ''')
