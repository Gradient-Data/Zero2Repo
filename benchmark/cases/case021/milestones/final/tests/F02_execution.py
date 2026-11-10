# feature: F02
"""Python behaviour observed through compiled, Python-visible definitions."""
from F02_helpers import check_python_execution


def test_f02_t01():
    check_python_execution('''
        def compute(a, b, items):
            trace = []
            total = 0
            for x in items:
                if x < 0:
                    continue
                if x > 20:
                    break
                total += x
                trace.append(x)
            else:
                trace.append('exhausted')
            n = len(items)
            while n:
                n -= 1
                total -= n
            return (a+b, a-b, a*b, a/b, a//b, a%b, a**2,
                    a < b, a == b, a != b, a >= b, a <= b, a > b,
                    a and b, a or b, not a, total, trace)
        def complex_math(a, b):
            return a+b, a-b, a*b, a/b, a == b
    ''', '''
        def exercise(s):
            return ([s.compute(a,b,x) for a,b,x in
                     [(0,3,[]), (-7,3,[1,-2,4]), (2.5,-0.5,[2,23,5]),
                      (2**90,7,[0,3,6])]],
                    s.complex_math(2+3j, -1+2j))
    ''')


def test_f02_t02():
    check_python_execution('''
        import math
        def containers(values, state, text, raw):
            first, *middle, last = values
            squares = [x*x for x in values if x % 2]
            mapping = {x: x+first for x in values}
            unique = {x % 3 for x in values}
            fixed = frozenset(unique)
            pair = (first, last)
            mutable = bytearray(raw)
            mutable[1:3] = b'XY'
            state['calls'] += 1
            state['items'].extend(middle)
            values[1:2] = [last, first]
            return (squares, mapping, unique, fixed, pair, values[-1],
                    values[::-2], text[1:-1], text.upper(), raw[::2], mutable,
                    math.isqrt(last*last), state, values)
    ''', '''
        def exercise(s):
            return [s.containers(v, {'calls': 2, 'items': [9]}, t, b'abcdef')
                    for v,t in [([2,5,7,11], 'aλ猫z'), ([4,4,6], 'short')]]
    ''')


def test_f02_t03():
    check_python_execution('''
        def collect(a, /, b=5, *args, c, d=8, **kwargs):
            return a, b, args, c, d, kwargs
        def strict(a, /, b, *, c):
            return a, b, c
    ''', '''
        def exercise(s):
            result = [s.collect(2,c=7), s.collect(3,4,9,10,c=6,d=1,z=12),
                      s.collect(2,b=3,c=4,a=9), s.strict(1,b=2,c=3)]
            calls = [lambda: s.strict(1,2), lambda: s.strict(1,2,b=3,c=4),
                     lambda: s.strict(1,2,c=3,extra=4),
                     lambda: s.strict(a=1,b=2,c=3), lambda: s.strict(1,2,3),
                     lambda: s.strict(1,c=3)]
            for call in calls:
                try:
                    call()
                except TypeError:
                    result.append('invalid-call')
                else:
                    raise AssertionError('Invalid call was accepted')
            return result
    ''')


def test_f02_t04():
    check_python_execution('''
        def decorate(fn):
            def wrapped(self, amount):
                return fn(self, amount) * 2
            return wrapped
        class Base:
            def __init__(self, value):
                self.value = value
            def step(self, amount):
                self.value += amount
                return self.value
        class Child(Base):
            @decorate
            def step(self, amount):
                return super().step(amount) + 1
        def counter(initial):
            value = initial
            def advance(delta):
                nonlocal value
                value += delta
                return value
            def read():
                return value
            return advance, read
        def attributes(obj, value):
            setattr(obj, 'extra', value)
            before = getattr(obj, 'extra')
            delattr(obj, 'extra')
            return before, hasattr(obj, 'extra')
    ''', '''
        def exercise(s):
            obj = s.Child(5)
            advance, read = s.counter(10)
            other, other_read = s.counter(-2)
            return (obj.step(3), obj.step(-1), obj.value,
                    s.attributes(obj, [4,8]), advance(2), read(), other(9),
                    advance(-5), read(), other_read())
    ''')


def test_f02_t05():
    source = '''
        def attached(self, value):
            return self.offset + value
    '''
    driver = '''
        def exercise(s):
            class Owner:
                offset = 17
                action = s.attached
            obj = Owner()
            results = [Owner.action(obj, 4)]
            try:
                results.append(obj.action(6))
            except TypeError:
                results.append('unbound-call')
            results.append(obj.action(obj, 8) if UNBOUND else Owner.action(obj, 8))
            return results
    '''
    assert check_python_execution(source, driver.replace('UNBOUND', 'False'),
                                  reference=False) == [21, 23, 25]
    assert check_python_execution(source, driver.replace('UNBOUND', 'True'),
                                  options=('-X', 'binding=False'),
                                  reference=False) == [21, 'unbound-call', 25]


def test_f02_t06():
    check_python_execution('''
        def child(log):
            try:
                value = yield 3
                log.append(('sent', value))
                try:
                    yield value * 2
                except ValueError as error:
                    log.append(('caught', error.args))
                    yield 11
                return 29
            finally:
                log.append('child-cleanup')
        def parent(log):
            try:
                result = yield from child(log)
                yield ('returned', result)
                return 41
            finally:
                log.append('parent-cleanup')
    ''', '''
        def exercise(s):
            log = []
            g = s.parent(log)
            result = [next(g), g.send(7), g.throw(ValueError('signal')), next(g)]
            try:
                next(g)
            except StopIteration as done:
                result.append(done.value)
            else:
                raise AssertionError('Generator did not terminate')
            result.append(list(log))
            closed = []
            g = s.parent(closed)
            result.append(next(g))
            g.close()
            result.append(closed)
            failed = []
            g = s.parent(failed)
            next(g)
            try:
                g.throw(KeyError('abort'))
            except KeyError as error:
                result.append(error.args)
            else:
                raise AssertionError('Exception was swallowed')
            return result, failed
    ''')


def test_f02_t07():
    check_python_execution('''
        import asyncio
        async def task(value, log):
            log.append('before')
            await asyncio.sleep(0)
            log.append('after')
            return value * 3
        async def stream(log):
            try:
                yield 2
                await asyncio.sleep(0)
                try:
                    yield 5
                except ValueError:
                    log.append('handled')
                    yield 9
            finally:
                await asyncio.sleep(0)
                log.append('closed')
    ''', '''
        import asyncio
        async def drive(s):
            log = []
            task = asyncio.create_task(s.task(7,log))
            await asyncio.sleep(0)
            during = list(log)
            result = await task
            g = s.stream(log)
            values = [await anext(g), await anext(g),
                      await g.athrow(ValueError('resume'))]
            await g.aclose()
            failed = s.stream(log)
            await anext(failed)
            try:
                await failed.athrow(KeyError('abort'))
            except KeyError as error:
                values.append(error.args)
            else:
                raise AssertionError('Async exception was swallowed')
            exhausted = [x async for x in s.stream(log)]
            return during, result, values, exhausted, log
        def exercise(s):
            return asyncio.run(drive(s))
    ''')


def test_f02_t08():
    check_python_execution('''
        class Manager:
            def __init__(self, log, suppress):
                self.log, self.suppress = log, suppress
            def __enter__(self):
                self.log.append('enter')
                return 13
            def __exit__(self, kind, value, tb):
                self.log.append(('exit', None if kind is None else kind.__name__))
                return self.suppress
            async def __aenter__(self):
                return self.__enter__()
            async def __aexit__(self, kind, value, tb):
                return self.__exit__(kind, value, tb)
        def sync(log, suppress, fail):
            with Manager(log, suppress) as value:
                log.append(value)
                if fail:
                    raise ValueError('body')
            return 'finished'
        async def asynchronous(log, suppress, fail):
            async with Manager(log, suppress) as value:
                log.append(value)
                if fail:
                    raise ValueError('body')
            return 'finished'
    ''', '''
        import asyncio
        def exercise(s):
            results = []
            for async_mode in (False, True):
                for suppress, fail in [(False,False), (False,True), (True,True)]:
                    log = []
                    try:
                        value = (asyncio.run(s.asynchronous(log,suppress,fail))
                                 if async_mode else s.sync(log,suppress,fail))
                    except ValueError as error:
                        value = ('propagated', error.args)
                    results.append((value,log))
            return results
    ''')


def test_f02_t09():
    check_python_execution('''
        def handled(mode, log):
            try:
                if mode == 'operation':
                    return {}['absent']
                if mode == 'explicit':
                    raise ValueError('payload')
                return 7
            except KeyError as error:
                log.append(('key', error.args))
                return 11
            except ValueError as error:
                log.append(('value', error.args))
                raise
            finally:
                log.append('cleanup')
        def uncaught():
            raise LookupError('application')
    ''', '''
        import traceback
        def exercise(s):
            results = []
            for mode in ('normal', 'operation', 'explicit'):
                log = []
                try:
                    value = s.handled(mode, log)
                except ValueError as error:
                    value = ('raised', error.args)
                results.append((value, log))
            try:
                s.uncaught()
            except LookupError as error:
                frames = traceback.extract_tb(error.__traceback__)
                frame = frames[-1]
                assert frame.filename.endswith('execution_subject.pyx'), frames
                assert frame.name.endswith('uncaught'), frames
                results.append((type(error).__name__, error.args, frame.lineno))
            else:
                raise AssertionError('Uncaught application exception was swallowed')
            return results
    ''')


def test_f02_t10():
    source = '''
        def semantics(a, b):
            return a / b, type('text').__name__, type(u'text').__name__
    '''
    driver = '''
        def exercise(s):
            return [s.semantics(a,b) for a,b in [(7,2),(-7,2),(7,-2)]]
    '''
    for options in [(), ('-X','language_level=3'), ('-X','language_level=3str')]:
        check_python_execution(source, driver, options=options)
    # Legacy floor division is supported for statically declared integer operands.
    result = check_python_execution(source.replace('semantics(a, b)',
                                                'semantics(int a, int b)') + '''
        def output(value):
            print value
    ''', '''
        import contextlib, io
        def exercise(s):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                s.output(37)
            return [s.semantics(a,b)[0] for a,b in [(7,2),(-7,2),(7,-2)]], out.getvalue()
    ''', options=('-X','language_level=2'), reference=False)
    assert result == ([3,-4,-4], '37\n')
